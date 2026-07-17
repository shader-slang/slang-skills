#!/usr/bin/env python3
"""Escalation report for open shader-slang pull requests.

Generates an assignee-grouped report of open PRs that need human attention,
computed entirely from live GitHub state via `gh`: it reads
PRs/CI/reviews/collaborators, derives each PR's lifecycle stage from those
signals, and emits the report (optionally with Discord/Slack mentions). The
caller decides how often to run it — the script does not throttle.

The report makes no changes on GitHub — it only reads, plus persists a small
local state file for its stall clocks. A PR with no human assignee is surfaced
honestly under an "Unassigned" group rather than guessing an owner.

Portable: depends only on an authenticated `gh` and the Python stdlib. All org
and infra constants are defaults near the top of this file.

Pure decision functions (derive_stage, the predicate ladders, compute_stall,
build_report) take plain data and are covered by test_pr_report.py with no live
`gh` calls.
"""
from __future__ import annotations

# Thin glue around `gh` + untyped JSON; strict "unknown/Any" rules relaxed (the
# pure decision functions are covered by test_pr_report.py instead).
# pyright: reportAny=false, reportExplicitAny=false, reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnknownVariableType=false, reportUnknownParameterType=false, reportUnknownLambdaType=false, reportUnusedCallResult=false, reportImplicitStringConcatenation=false, reportImplicitRelativeImport=false

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone, tzinfo
from collections.abc import Callable
from typing import Any, final

try:
    from zoneinfo import ZoneInfo
except Exception:  # pragma: no cover - zoneinfo is stdlib on 3.9+
    ZoneInfo = None


# ---------------------------------------------------------------------------
# Configuration — EDIT HERE.
# ---------------------------------------------------------------------------

DEFAULT_ORG = "shader-slang"
# Empty -> every non-archived repo in DEFAULT_ORG. Set to a comma-separated
# "owner/name,owner/name" list to restrict the report to a subset.
DEFAULT_REPOS = ""
# Bot identities. `Copilot` is the GitHub Copilot coding-agent's assignee/
# reviewer login (GitHub types it as a User there, not a Bot, so it must be
# matched by name); `copilot-swe-agent` is its author form.
DEFAULT_BOT_AUTHORS = "nv-slang-bot,slang-coworker-nanoclaw,Copilot,copilot-swe-agent"
# Requested reviewers auto-added by repo automation who cannot actually approve,
# so they never count as real review coverage.
DEFAULT_IGNORED_REVIEWERS = "bmillsNV"
# Optional CI check that gates a bot PR's promotion to ready-for-review; while
# empty, bot PRs are treated as ready (a human owner is the gate).
DEFAULT_COVERAGE_CHECK = ""

# Internal lifecycle-stage labels (derived from live signals; see derive_stage).
DEFAULT_STATUS_REVISING = "Revising"
DEFAULT_STATUS_TODO = "Todo"
DEFAULT_STATUS_DONE = "Done"
# PR source categories. "Unknown" is used when the repo's collaborator set
# couldn't be read, so we can't tell Internal from Community (see classify_source).
DEFAULT_SOURCE_INTERNAL = "Internal"
DEFAULT_SOURCE_COMMUNITY = "Community"
DEFAULT_SOURCE_BOT = "Bot"
DEFAULT_SOURCE_UNKNOWN = "Unknown"

# Workday model for the stall clock (skips weekends).
DEFAULT_WORKDAY_TZ = "America/Los_Angeles"

# Where the per-PR stall / last-report state is written (cwd-relative).
STATE_FILE = "./.pr-report-state.json"

# PRs per GraphQL page (capped by server timeout, not budget: n=50 can return
# HTTP 504 on large repos, n=25 resolves in ~5-6s).
DEFAULT_PR_PAGE_SIZE = 25


def _split_csv(s: str) -> list[str]:
    return [x.strip() for x in s.split(",") if x.strip()]


def _progress(msg: str) -> None:
    """Liveness heartbeat to stderr. A run is long-running (minutes) and
    otherwise silent until the end; steady stderr output tells a runner it is
    alive. Kept off stdout, which carries only the summary + report."""
    print(msg, file=sys.stderr, flush=True)


@dataclass
class Config:
    repos: list[str] = field(default_factory=lambda: _split_csv(DEFAULT_REPOS))
    org: str = DEFAULT_ORG
    status_revising: str = DEFAULT_STATUS_REVISING
    status_todo: str = DEFAULT_STATUS_TODO
    status_done: str = DEFAULT_STATUS_DONE
    coverage_check: str = DEFAULT_COVERAGE_CHECK
    source_internal: str = DEFAULT_SOURCE_INTERNAL
    source_community: str = DEFAULT_SOURCE_COMMUNITY
    source_bot: str = DEFAULT_SOURCE_BOT
    source_unknown: str = DEFAULT_SOURCE_UNKNOWN
    bot_authors: list[str] = field(
        default_factory=lambda: _split_csv(DEFAULT_BOT_AUTHORS))
    ignored_reviewers: list[str] = field(
        default_factory=lambda: _split_csv(DEFAULT_IGNORED_REVIEWERS))
    workday_tz: str = DEFAULT_WORKDAY_TZ
    state_file: str = STATE_FILE
    # GitHub login (lowercased) -> destination user ID for report mentions.
    # Empty means nobody is mapped, so every login renders as inert backticks.
    recipient_map: dict[str, str] = field(default_factory=dict)

    def tzinfo(self):
        if ZoneInfo is not None:
            try:
                return ZoneInfo(self.workday_tz)
            except Exception:
                pass
        return timezone.utc


# CI states
CI_PASSED = "passed"
CI_FAILED = "failed"
CI_PENDING = "pending"
CI_ACTION_REQUIRED = "action_required"
CI_NONE = "none"

def classify_is_bot(author: str, bot_authors: list[str]) -> bool:
    """True when an author should be treated as a bot (matches 'name',
    'name[bot]', or 'app/name' against the configured bot authors)."""
    a = author.lower()
    for b in bot_authors:
        b = b.strip().lower()
        if not b:
            continue
        base = a.replace("[bot]", "").replace("app/", "")
        if base == b or a == b:
            return True
    return False


@dataclass
class PR:
    repo: str
    number: int
    url: str = ""
    title: str = ""
    author: str = ""
    is_bot: bool = False
    is_draft: bool = False
    state: str = "OPEN"  # OPEN | MERGED | CLOSED
    source: str = ""     # Internal | Community | Bot (classified live)
    assignees: list[str] = field(default_factory=list)
    head_sha: str = ""
    review_decision: str = ""  # APPROVED | CHANGES_REQUESTED | REVIEW_REQUIRED | ""
    in_merge_queue: bool = False
    existing_reviewers: list[str] = field(default_factory=list)  # currently-requested reviewers
    ci_state: str = CI_NONE
    coverage_passed: bool = False
    last_review_at: datetime | None = None
    change_requested: bool = False
    last_activity_at: datetime | None = None
    # Latest issue-comment by a human assignee who is not the PR author. A
    # non-author assignee engaging via comment counts as movement (resets the
    # stall clock).
    last_assignee_comment_at: datetime | None = None

    def key(self) -> str:
        return f"{self.repo}#{self.number}"


# ---------------------------------------------------------------------------
# Shared pure helpers + gh I/O
# ---------------------------------------------------------------------------

def parse_iso(ts: str | None) -> datetime | None:
    """Parse an ISO-8601 timestamp (accepting a trailing Z) to an aware UTC datetime."""
    if not ts:
        return None
    s = ts.strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def working_hours_between(start: datetime | None, end: datetime | None, tz: tzinfo) -> float:
    """Hours falling on weekdays (Mon-Fri, in `tz`) between start and end."""
    if start is None or end is None or end <= start:
        return 0.0
    cur = start.astimezone(tz)
    stop = end.astimezone(tz)
    total = 0.0
    while cur < stop:
        next_midnight = (cur + timedelta(days=1)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        seg_end = min(next_midnight, stop)
        if cur.weekday() < 5:  # Monday=0 .. Friday=4
            total += (seg_end - cur).total_seconds()
        cur = seg_end
    return total / 3600.0


def promotion_gate_passed(pr: PR, cfg: Config) -> bool:
    """Whether a PR has cleared the automated gate to be ready for human review.

    Human PRs are ready on clean CI. Bot PRs are shepherded by a human owner, so
    they are ready regardless of draft state — unless a coverage check is
    configured, in which case it gates them."""
    if pr.is_bot:
        return pr.coverage_passed if cfg.coverage_check else True
    return pr.ci_state == CI_PASSED


def source_for(is_bot: bool, can_commit: bool, cfg: Config) -> str:
    """Source classification (pure): Bot if a bot authored it, else Internal if
    the author can commit to the target repo, else Community."""
    if is_bot:
        return cfg.source_bot
    return cfg.source_internal if can_commit else cfg.source_community


def classify_source(pr: PR, cfg: Config, collaborators: set[str] | None) -> str:
    """Classify a PR's source. Pure. `collaborators` is the repo's write+ set
    (Internal iff the author can commit to the repo), or None when that set
    couldn't be read — in which case a non-bot PR is `Unknown` (we can't tell
    Internal from Community) rather than being silently assumed Community. A bot
    PR is always `Bot` (bot detection doesn't need the collaborator set)."""
    if collaborators is None and not pr.is_bot:
        return cfg.source_unknown
    return source_for(pr.is_bot, collaborators is not None and pr.author in collaborators, cfg)


# --- State file (per-PR stall clocks) ----------------------------------------

def load_state(path: str) -> dict[str, Any]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, ValueError):
        return {"prs": {}}


def save_state(path: str, state: dict[str, Any]) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, sort_keys=True)
    os.replace(tmp, path)


def pr_state_entry(state: dict[str, Any], key: str) -> dict[str, Any]:
    return state.setdefault("prs", {}).setdefault(key, {})


def prune_state(state: dict[str, Any], seen_keys: set[str],
                scanned_repos: set[str]) -> dict[str, Any]:
    """Drop per-PR entries for PRs no longer open in the scanned repos, so the
    state file does not grow forever as PRs merge/close. Keeps entries for repos
    NOT scanned this run (so a subset run via DEFAULT_REPOS doesn't wipe other
    repos' clocks). Pure."""
    prs = state.get("prs", {})
    state["prs"] = {
        k: v for k, v in prs.items()
        if k in seen_keys or k.rsplit("#", 1)[0] not in scanned_repos
    }
    return state


# --- gh I/O layer (the only place that shells out) ---------------------------

def is_wsl() -> bool:
    rel = platform.uname().release.lower()
    return "microsoft" in rel or "wsl" in rel


def find_gh() -> str:
    """Locate the GitHub CLI, honoring $GH and preferring gh.exe under WSL."""
    env = os.environ.get("GH")
    if env:
        return env
    if is_wsl():
        exe = shutil.which("gh.exe")
        if exe:
            return exe
        # On WSL we must not silently fall back to a different toolchain.
        raise SystemExit("gh.exe not found under WSL; install it or set $GH.")
    exe = shutil.which("gh")
    if not exe:
        raise SystemExit("gh not found on PATH; install GitHub CLI or set $GH.")
    return exe


@final
class Gh:
    def __init__(self, exe: str):
        self.exe = exe

    def run(self, args: list[str], check: bool = True) -> str:
        proc = subprocess.run(
            [self.exe] + args, capture_output=True, text=True
        )
        if check and proc.returncode != 0:
            raise RuntimeError(
                f"gh {' '.join(args)} failed ({proc.returncode}): {proc.stderr.strip()}"
            )
        return proc.stdout

    def json(self, args: list[str]) -> Any:
        out = self.run(args)
        return json.loads(out) if out.strip() else None

    def api(self, path: str, jq: str | None = None, paginate: bool = False):
        args = ["api", path]
        if paginate:
            args.append("--paginate")
        if jq:
            args += ["--jq", jq]
        return self.run(args, check=False)

    def api_lines(self, path: str, jq: str, paginate: bool = True) -> list[str] | None:
        """Run a `gh api` jq query and return its non-empty output lines, or
        `None` if the call failed. Lets callers distinguish "no access" (None)
        from "empty result" ([])."""
        args = ["api", path]
        if paginate:
            args.append("--paginate")
        args += ["--jq", jq]
        proc = subprocess.run([self.exe] + args, capture_output=True, text=True)
        if proc.returncode != 0:
            return None
        return [line.strip() for line in proc.stdout.splitlines() if line.strip()]

    def graphql(self, query: str, variables: dict[str, Any] | None = None) -> Any:
        args = ["api", "graphql", "-f", f"query={query}"]
        for k, v in (variables or {}).items():
            args += ["-F", f"{k}={v}"]
        out = self.run(args)
        return json.loads(out) if out.strip() else None

    def preflight(self, cfg: "Config") -> None:
        # Fail loudly if we cannot access what we are about to report on. We probe
        # a real resource (`gh api orgs/<org>`, or `gh api repos/<owner/name>` when
        # a repo subset is configured) rather than `gh auth status`. `gh auth
        # status` only inspects gh's locally stored credentials, which breaks when
        # the token is injected on the wire by a proxy (e.g. onecli) and gh has no
        # credentials of its own — yet real API calls still succeed. Probing the
        # actual target also gives a direct yes/no on access (and is token-type
        # agnostic: it works for a user PAT or a GitHub App token, unlike
        # `gh api user`, which 403s for App tokens).
        if cfg.repos:
            target, what = f"repos/{cfg.repos[0]}", f"repository {cfg.repos[0]!r}"
        else:
            target, what = f"orgs/{cfg.org}", f"org {cfg.org!r}"
        proc = subprocess.run(
            [self.exe, "api", target], capture_output=True, text=True)
        if proc.returncode != 0:
            raise SystemExit(
                f"gh cannot access {what} (`gh api {target}` failed). Check the "
                f"token and that it can read {what} (gh auth, GH_TOKEN, or a "
                f"token-injecting proxy such as onecli).\n{proc.stderr.strip()}"
            )


# ---------------------------------------------------------------------------
# Collect (bulk reads) + raw-state interpretation
# ---------------------------------------------------------------------------

def list_org_repos(gh: Gh, org: str) -> list[str]:
    """Every non-archived repo in `org` (owner/name), via `gh repo list`."""
    data = gh.json([
        "repo", "list", org, "--no-archived", "--limit", "1000",
        "--json", "nameWithOwner",
    ]) or []
    return [r["nameWithOwner"] for r in data if r.get("nameWithOwner")]


def collect_repo_collaborators(gh: Gh, repo: str) -> set[str] | None:
    """Logins with write+ access (push/maintain/admin) to `repo`, used to
    classify a PR's source (Internal iff the author can commit). Returns `None`
    when the call fails (the endpoint needs push access on the repo) so the
    caller can mark the source `Unknown` rather than assume Community; an empty
    set means the repo genuinely has no write+ collaborators."""
    lines = gh.api_lines(
        f"repos/{repo}/collaborators",
        ".[] | select(.permissions.push == true) | .login",
    )
    return set(lines) if lines is not None else None


# One batched query returns, per open PR, everything the report needs: core
# fields, CI rollup, reviews, comments, requested reviewers, assignees,
# merge-queue.
_PR_QUERY = """
query($owner: String!, $name: String!, $n: Int!, $cursor: String) {
  repository(owner: $owner, name: $name) {
    pullRequests(states: OPEN, first: $n, after: $cursor,
                 orderBy: {field: UPDATED_AT, direction: DESC}) {
      pageInfo { hasNextPage endCursor }
      nodes {
        number title url isDraft headRefOid updatedAt reviewDecision
        author { login __typename }
        assignees(first: 10) { nodes { login } }
        reviewRequests(first: 20) { nodes { requestedReviewer { __typename ... on User { login } } } }
        commits(last: 1) { nodes { commit { statusCheckRollup { contexts(first: 100) { nodes {
          __typename
          ... on CheckRun { name status conclusion }
          ... on StatusContext { context state }
        } } } } } }
        reviews(last: 50) { nodes { state submittedAt author { login } } }
        comments(last: 50) { nodes { createdAt author { login } } }
        mergeQueueEntry { id }
      }
    }
  }
}
"""


def collect_open_prs(gh: Gh, repo: str, cfg: Config) -> list[PR]:
    """All open PRs for `repo`, fully populated, via the paginated batched query."""
    owner, name = repo.split("/", 1)
    prs: list[PR] = []
    cursor = None
    page_num = 0
    while True:
        variables: dict[str, Any] = {"owner": owner, "name": name, "n": DEFAULT_PR_PAGE_SIZE}
        if cursor:
            variables["cursor"] = cursor
        data = gh.graphql(_PR_QUERY, variables)
        conn = ((((data or {}).get("data") or {}).get("repository") or {})
                .get("pullRequests") or {})
        before = len(prs)
        for node in conn.get("nodes", []) or []:
            prs.append(parse_pr_node(node, repo, cfg))
        page_num += 1
        _progress(f"  {repo}: page {page_num} (+{len(prs) - before} open PRs, {len(prs)} total)")
        page = conn.get("pageInfo") or {}
        if page.get("hasNextPage"):
            cursor = page.get("endCursor")
        else:
            break
    return prs


def summarize_ci(runs: list[dict[str, Any]]) -> str:
    """Reduce check-runs to a single CI state. Pure given the run list."""
    if not runs:
        return CI_NONE
    any_pending = False
    any_failed = False
    for r in runs:
        if r.get("conclusion") == "action_required":
            return CI_ACTION_REQUIRED
        if r.get("status") != "completed":
            any_pending = True
            continue
        if r.get("conclusion") not in ("success", "neutral", "skipped"):
            any_failed = True
    if any_pending:
        return CI_PENDING
    if any_failed:
        return CI_FAILED
    return CI_PASSED


def ci_state_from_rollup(rollup: dict[str, Any] | None, cfg: Config) -> tuple[str, bool]:
    """Map a head commit's statusCheckRollup to (ci_state, coverage_passed),
    reusing summarize_ci. Null rollup -> (CI_NONE, False). Pure.

    Each context is a CheckRun (status/conclusion) or a legacy StatusContext
    (state); both are normalized to the {status, conclusion} shape summarize_ci
    consumes. coverage_passed is set from a CheckRun named cfg.coverage_check."""
    if not rollup:
        return CI_NONE, False
    contexts = ((rollup.get("contexts") or {}).get("nodes")) or []
    runs: list[dict[str, Any]] = []
    coverage_passed = False
    for c in contexts:
        if c.get("__typename") == "CheckRun":
            conclusion = (c.get("conclusion") or "").lower()
            runs.append({"status": (c.get("status") or "").lower(), "conclusion": conclusion})
            if cfg.coverage_check and c.get("name") == cfg.coverage_check:
                coverage_passed = conclusion == "success"
        else:  # StatusContext (legacy commit status)
            state = (c.get("state") or "").upper()
            if state == "SUCCESS":
                runs.append({"status": "completed", "conclusion": "success"})
            elif state in ("FAILURE", "ERROR"):
                runs.append({"status": "completed", "conclusion": "failure"})
            else:  # PENDING / EXPECTED
                runs.append({"status": "in_progress", "conclusion": None})
    return summarize_ci(runs), coverage_passed


def summarize_reviews(reviews: list[dict[str, Any]]) -> tuple[datetime | None, bool]:
    """(last_review_at, change_requested) from review nodes. Pure;
    case-insensitive on state. change_requested = the most recent decisive
    (APPROVED/CHANGES_REQUESTED) review requested changes."""
    dated = [r for r in reviews if r.get("submittedAt")]
    if not dated:
        return None, False
    dated.sort(key=lambda r: r["submittedAt"])
    last_review_at = parse_iso(dated[-1]["submittedAt"])
    decisive = [r for r in dated
                if (r.get("state") or "").upper() in ("APPROVED", "CHANGES_REQUESTED")]
    change_requested = bool(decisive) and (decisive[-1].get("state") or "").upper() == "CHANGES_REQUESTED"
    return last_review_at, change_requested


def first_human_assignee(assignees: list[str], cfg: Config) -> str | None:
    """The first non-bot assignee login (the human the report holds
    responsible), or None when there is no human assignee. Pure. Shared by
    effective_assignee and the assignee-comment movement signal."""
    for a in assignees:
        if a and not classify_is_bot(a, cfg.bot_authors) and not a.lower().endswith("[bot]"):
            return a
    return None


def latest_assignee_comment_at(comments: list[dict[str, Any]], assignees: list[str],
                               author: str, cfg: Config) -> datetime | None:
    """Most recent issue-comment authored by a human assignee who is NOT the PR
    author (bots and the author excluded), or None. Movement signal: a
    maintainer shepherding the PR engaging via a comment (e.g. pinging the
    author) counts as progress and resets the stall clock.

    Deliberately order-independent — a set-membership test over the assignees,
    not a positional pick — because GitHub assignees are a co-equal, unordered
    set with no "primary" and no stable ordering. The author is excluded even
    when they are also assigned, so an author comment never resets the clock.
    Pure; case-insensitive on login."""
    author_l = (author or "").lower()
    owners = {a.lower() for a in assignees
              if a and not classify_is_bot(a, cfg.bot_authors)
              and not a.lower().endswith("[bot]")
              and a.lower() != author_l}
    if not owners:
        return None
    dated: list[datetime] = []
    for c in comments:
        login = ((c.get("author") or {}).get("login") or "").lower()
        if login in owners:
            dt = parse_iso(c.get("createdAt"))
            if dt:
                dated.append(dt)
    return max(dated) if dated else None


def parse_pr_node(node: dict[str, Any], repo: str, cfg: Config) -> PR:
    """Build a fully-populated PR from one batched-query GraphQL node. Pure."""
    author = node.get("author") or {}
    login = author.get("login", "") or ""
    is_bot = author.get("__typename") == "Bot" or classify_is_bot(login, cfg.bot_authors)

    commits = ((node.get("commits") or {}).get("nodes")) or []
    rollup = (((commits[0].get("commit") or {}).get("statusCheckRollup")) if commits else None)
    ci_state, coverage_passed = ci_state_from_rollup(rollup, cfg)

    last_review_at, change_requested = summarize_reviews(
        ((node.get("reviews") or {}).get("nodes")) or [])

    existing_reviewers: list[str] = []
    for rr in ((node.get("reviewRequests") or {}).get("nodes")) or []:
        lg = (rr.get("requestedReviewer") or {}).get("login")
        if lg:
            existing_reviewers.append(lg)

    assignees = [a.get("login", "") for a in (((node.get("assignees") or {}).get("nodes")) or [])
                 if a.get("login")]

    last_assignee_comment_at = latest_assignee_comment_at(
        ((node.get("comments") or {}).get("nodes")) or [], assignees, login, cfg)

    return PR(
        repo=repo,
        number=node["number"],
        url=node.get("url", "") or "",
        title=node.get("title", "") or "",
        author=login,
        is_bot=is_bot,
        is_draft=bool(node.get("isDraft")),
        assignees=assignees,
        head_sha=node.get("headRefOid", "") or "",
        review_decision=node.get("reviewDecision", "") or "",
        existing_reviewers=existing_reviewers,
        in_merge_queue=(node.get("mergeQueueEntry") is not None),
        last_activity_at=parse_iso(node.get("updatedAt")),
        ci_state=ci_state,
        coverage_passed=coverage_passed,
        last_review_at=last_review_at,
        change_requested=change_requested,
        last_assignee_comment_at=last_assignee_comment_at,
    )


# Report rendering
ESCALATED_ICON = "\u2b06\ufe0f"   # up arrow: escalated/overdue (past the second rung)
COMMUNITY_ICON = "\U0001f310"     # globe
BOT_ICON = "\U0001f916"           # robot
UNKNOWN_ICON = "\u2753"           # red question mark: source couldn't be determined

# Group key for PRs with no human assignee. Parentheses can't appear in a GitHub
# login, so this never collides with a real assignee; rendered as "Unassigned".
UNASSIGNED = "(unassigned)"


@dataclass
class Predicate:
    """A reason a PR needs attention, with its render text and per-source
    escalation ladder. `applies` and `render` are pure over a PR."""
    key: str
    applies: "Callable[[PR, Config], bool]"
    render: "Callable[[PR, Config, int], str]"     # (pr, cfg, stall_days) -> reason text
    ladder: tuple[tuple[str, float], ...]          # ((audience, after_working_hours), ...)


@dataclass
class ReportItem:
    pr: PR
    reason: str
    assignee: str
    escalated: bool = False   # reached the escalate rung (overdue past the second threshold)


# ---------------------------------------------------------------------------
# PURE LOGIC (no I/O) -- exercised directly by test_pr_report.py
# ---------------------------------------------------------------------------

def derive_stage(pr: PR, cfg: Config) -> str:
    """Each PR's lifecycle stage, derived from live GitHub signals.

    Three observable stages — Revising / Todo (ready for a human) / Done —
    computed per source ("different fingerprints"):
      - Bot: Todo whenever promotion_gate_passed holds (always, unless a
        coverage check is configured and failing); drafts are NOT exempt.
      - Contributor/Community: Revising while draft / changes-requested / CI
        failing (or not yet passed); Todo only once not a draft and CI passed.
      - Done: merged/closed or in the merge queue.
    """
    if pr.state in ("MERGED", "CLOSED") or pr.in_merge_queue:
        return cfg.status_done
    if pr.is_bot:
        return cfg.status_todo if promotion_gate_passed(pr, cfg) else cfg.status_revising
    if pr.is_draft or pr.change_requested or pr.ci_state == CI_FAILED:
        return cfg.status_revising
    return cfg.status_todo if pr.ci_state == CI_PASSED else cfg.status_revising


# --- Predicate ladders (the "list of predicates", per source) ----------------

def format_mention(login: str, cfg: Config) -> str:
    """Render a GitHub login for the report. A login present in the recipient
    map becomes a `<@destId>` mention (pings on Discord/Slack); every other
    login (unmapped, or no map supplied) becomes inert `` `login` `` so it can
    never notify the wrong person. The map is consulted only here -- all routing
    and writes elsewhere stay on GitHub logins."""
    dest = cfg.recipient_map.get(login.lower()) if cfg.recipient_map else None
    return f"<@{dest}>" if dest else f"`{login}`"


def _real_reviewers(pr: PR, cfg: Config) -> list[str]:
    """Requested reviewers who can actually approve: excludes auto-assigned
    non-approvers (DEFAULT_IGNORED_REVIEWERS, e.g. bmillsNV) and bots."""
    ignored = {r.lower() for r in cfg.ignored_reviewers}
    return [r for r in pr.existing_reviewers
            if r and r.lower() not in ignored
            and not classify_is_bot(r, cfg.bot_authors)
            and not r.lower().endswith("[bot]")]


def _reviewers_text(pr: PR, cfg: Config) -> str:
    revs = _real_reviewers(pr, cfg)
    return ", ".join(format_mention(r, cfg) for r in revs) if revs else "(no reviewers requested)"


def _awaiting_review(pr: PR, cfg: Config) -> bool:
    # Only "awaiting review" when the PR has reached the human-ready stage
    # (derived Todo) and a real (approve-capable) reviewer is requested.
    return (derive_stage(pr, cfg) == cfg.status_todo
            and bool(_real_reviewers(pr, cfg))
            and pr.review_decision != "APPROVED")


# Ladder rung thresholds are weekday-hours since the PR last moved.
DAY = 24.0
WEEK = 7 * DAY

# Ladder rungs are (audience, after_working_hours): "assignee" is the surface
# threshold (when an item appears under its owner / the Unassigned group);
# "escalate" is the overdue threshold (when it gains the escalated up-arrow).

# Community: external author, internal assignee provides oversight.
COMMUNITY_LADDER: list[Predicate] = [
    Predicate("needs_ci_approval",
              lambda pr, cfg: pr.ci_state == CI_ACTION_REQUIRED,
              lambda pr, cfg, days: "needs CI approval",
              (("assignee", 0.0), ("escalate", DAY))),
    Predicate("changes_requested",
              lambda pr, cfg: pr.change_requested,
              lambda pr, cfg, days: "changes requested — check if author is still active / needs help",
              (("assignee", WEEK), ("escalate", 2 * WEEK))),
    Predicate("awaiting_review",
              _awaiting_review,
              lambda pr, cfg, days: f"awaiting review from: {_reviewers_text(pr, cfg)}",
              (("assignee", DAY), ("escalate", 2 * DAY))),
    Predicate("ci_failing",
              lambda pr, cfg: pr.ci_state == CI_FAILED,
              lambda pr, cfg, days: "CI failing — needs fixes",
              (("assignee", DAY), ("escalate", 2 * DAY))),
    Predicate("idle",
              lambda pr, cfg: True,
              lambda pr, cfg, days: f"idle for {days} days",
              (("assignee", DAY), ("escalate", 2 * DAY))),
]

# Bot: bot-authored, owner shepherds; lower urgency, no fork CI gate.
BOT_LADDER: list[Predicate] = [
    Predicate("awaiting_review",
              _awaiting_review,
              lambda pr, cfg, days: f"awaiting review from: {_reviewers_text(pr, cfg)}",
              (("assignee", 2 * DAY), ("escalate", WEEK))),
    Predicate("ci_failing",
              lambda pr, cfg: pr.ci_state == CI_FAILED,
              lambda pr, cfg, days: "CI failing — needs fixes",
              (("assignee", 2 * DAY), ("escalate", WEEK))),
    Predicate("idle",
              lambda pr, cfg: True,
              lambda pr, cfg, days: f"idle for {days} days",
              (("assignee", 2 * DAY), ("escalate", WEEK))),
]


def ladder_for(pr: PR, cfg: Config) -> list[Predicate]:
    """The predicate ladder for a PR's source (empty -> not surfaced).
    `Unknown` PRs (collaborator set unreadable, can't tell Internal from
    Community) are surfaced via the community ladder and flagged with the
    unknown icon, rather than being silently dropped or assumed Community."""
    if pr.source == cfg.source_bot:
        return BOT_LADDER
    if pr.source in (cfg.source_community, cfg.source_unknown):
        return COMMUNITY_LADDER
    return []  # Internal: not surfaced (author self-manages)


def source_icon(pr: PR, cfg: Config) -> str:
    if pr.source == cfg.source_bot:
        return BOT_ICON
    if pr.source == cfg.source_community:
        return COMMUNITY_ICON
    if pr.source == cfg.source_unknown:
        return UNKNOWN_ICON
    return ""


# --- Movement / stall clock ---------------------------------------------------

def compute_stall(pr: PR, cfg: Config, prior: dict[str, Any], now: datetime,
                  tz: tzinfo) -> tuple[dict[str, Any], float, int]:
    """Track when a PR last *moved* (derived stage / head SHA / last review /
    latest assignee comment changed) and how long it has been stalled. Returns
    (new_state, stall_wh, stall_days). Pure. First sight anchors to the PR's
    last activity so a stale backlog surfaces immediately.

    The derived stage anchors movement: a contributor PR's CI going green and a
    bot PR's promotion each register as movement, per source. A comment by a
    human assignee other than the author also counts as movement — a maintainer
    engaging (e.g. pinging the author) resets the clock so the report does not
    keep nagging them."""
    fp = [derive_stage(pr, cfg), pr.head_sha,
          pr.last_review_at.isoformat() if pr.last_review_at else None,
          pr.last_assignee_comment_at.isoformat() if pr.last_assignee_comment_at else None]
    prior_fp = prior.get("move_fingerprint")
    if prior_fp is None:
        last_moved = pr.last_activity_at or now
    elif prior_fp != fp:
        last_moved = now
    else:
        last_moved = parse_iso(prior.get("last_moved_at")) or now
    state = {"move_fingerprint": fp, "last_moved_at": last_moved.isoformat()}
    stall_wh = working_hours_between(last_moved, now, tz)
    stall_days = max(0, (now - last_moved).days)
    return state, stall_wh, stall_days


# --- Recipient-grouped report -------------------------------------------------

def effective_assignee(pr: PR, cfg: Config) -> str:
    """The human the report holds responsible: the first non-bot assignee (a bot
    like `Copilot` can't act on a notice). When there is no human assignee, the
    report does not predict an owner — it returns the UNASSIGNED group so the PR
    is surfaced honestly (assignment happens elsewhere, e.g. a GitHub Action)."""
    return first_human_assignee(pr.assignees, cfg) or UNASSIGNED


def build_report(prs: list[PR], cfg: Config,
                 stall_by_key: dict[str, tuple[float, int]],
                 ) -> dict[str, list[ReportItem]]:
    """Group each flagged PR under its assignee (assignee login -> [ReportItem]),
    with PRs that have no human assignee grouped under UNASSIGNED. A PR surfaces
    once it passes the predicate's assignee (surface) rung; passing the escalate
    rung marks it overdue *in place* (the `escalated` up-arrow). Pure given the
    stall map."""
    recipients: dict[str, list[ReportItem]] = {}
    for pr in prs:
        if pr.is_draft and not pr.is_bot:
            continue  # human drafts exempt
        ladder = ladder_for(pr, cfg)
        if not ladder:
            continue
        pred = next((p for p in ladder if p.applies(pr, cfg)), None)
        if pred is None:
            continue
        stall_wh, stall_days = stall_by_key.get(pr.key(), (0.0, 0))
        rungs = dict(pred.ladder)
        assignee_after = rungs.get("assignee")
        if assignee_after is None or stall_wh < assignee_after:
            continue  # not yet at the first (surface) rung -> not surfaced
        escalate_after = rungs.get("escalate")
        assignee = effective_assignee(pr, cfg)
        # Escalated == reached the escalate rung (overdue). Applies identically to
        # owned and Unassigned items.
        escalated = escalate_after is not None and stall_wh >= escalate_after
        reason = pred.render(pr, cfg, stall_days)
        recipients.setdefault(assignee, []).append(
            ReportItem(pr, reason, assignee, escalated))
    return recipients


def _repo_short(repo: str) -> str:
    return repo.split("/")[-1] if "/" in repo else repo


def _item_sort_key(it: ReportItem, cfg: Config) -> tuple[int, int]:
    """Order within an assignee's group: Community, then Unknown, then Bot; and
    within each, escalated (up-arrow) before not-escalated. Stable on ties
    (preserves input order)."""
    if it.pr.source == cfg.source_community:
        src = 0
    elif it.pr.source == cfg.source_unknown:
        src = 1
    elif it.pr.source == cfg.source_bot:
        src = 2
    else:
        src = 3
    return (src, 0 if it.escalated else 1)


def render_report(recipients: dict[str, list[ReportItem]], cfg: Config) -> str:
    """Render the assignee-grouped report. The Unassigned group is listed first,
    then named assignees sorted; an `escalated` item keeps its place and gains
    the overdue up-arrow."""
    if not recipients:
        return ""
    named = sorted(r for r in recipients if r != UNASSIGNED)
    order = ([UNASSIGNED] if UNASSIGNED in recipients else []) + named
    legend = (f"_{BOT_ICON} agent PR · {COMMUNITY_ICON} community PR · "
              f"{UNKNOWN_ICON} source unknown · {ESCALATED_ICON} escalated/overdue_")
    lines = ["## Slang PR Escalation Report", "", legend, ""]
    for recipient in order:
        header = "Unassigned" if recipient == UNASSIGNED else format_mention(recipient, cfg)
        lines.append(f"- **{header}**:")
        for it in sorted(recipients[recipient], key=lambda i: _item_sort_key(i, cfg)):
            prefix = (ESCALATED_ICON + " ") if it.escalated else ""
            icon = source_icon(it.pr, cfg)
            link = f"[{_repo_short(it.pr.repo)}#{it.pr.number}]({it.pr.url})"
            lines.append(f"  - {prefix}{icon} {link} — {it.reason}")
    return "\n".join(lines).strip()


# ---------------------------------------------------------------------------
# Recipient map
# ---------------------------------------------------------------------------

def load_recipient_map(path: str) -> dict[str, str]:
    """Load the GitHub-login -> destination-ID table for report mentions. A flat
    JSON object, e.g. {"jhelferty-nv": "123...", "bob": "987..."}. Keys are
    lowercased for case-insensitive lookup. Raises SystemExit on a missing file
    or anything that is not a flat object of scalar values."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        raise SystemExit(f"--recipient-map file not found: {path}")
    except ValueError as e:
        raise SystemExit(f"--recipient-map file is not valid JSON ({path}): {e}")
    if not isinstance(data, dict):
        raise SystemExit(
            f"--recipient-map must be a JSON object of \"githubLogin\": \"destId\" "
            f"({path})")
    result: dict[str, str] = {}
    for k, v in data.items():
        if isinstance(v, (dict, list)):
            raise SystemExit(
                f"--recipient-map value for {k!r} must be a scalar id, not "
                f"{type(v).__name__} ({path})")
        result[str(k).lower()] = str(v)
    return result


# ---------------------------------------------------------------------------
# Collect + report orchestration
# ---------------------------------------------------------------------------

def collect_prs_for_report(gh: Gh, cfg: Config,
                           repo_collaborators: Callable[[str], set[str] | None]) -> list[PR]:
    """All open PRs across cfg.repos, fully populated by the batched query, with
    Source classified live. The report does not predict owners, so no
    committer-signal ranking is run here."""
    _progress(f"scanning {len(cfg.repos)} repo(s) for the report — this typically takes a few minutes…")
    prs: list[PR] = []
    for repo in cfg.repos:
        for pr in collect_open_prs(gh, repo, cfg):
            # Classify Source live (reusing the repo's write+ collaborator set,
            # fetched lazily).
            pr.source = classify_source(pr, cfg, repo_collaborators(repo))
            pr.is_bot = (pr.source == cfg.source_bot)
            prs.append(pr)
    _progress(f"collected {len(prs)} open PR(s) across {len(cfg.repos)} repo(s).")
    return prs


def run_report(gh: Gh, cfg: Config, now: datetime) -> dict[str, Any]:
    """Build the assignee-grouped report from live state and persist the per-PR
    stall clocks. No GitHub writes; the only side effect is the local state file
    (the report's own bookkeeping)."""
    state = load_state(cfg.state_file)

    # The write+ collaborator set is per-repo, memoized; used for live Source
    # classification (Internal iff the author can commit to the repo). None means
    # the set couldn't be read -> non-bot PRs there are classified Unknown.
    collaborators_cache: dict[str, set[str] | None] = {}

    def repo_collaborators(repo: str) -> set[str] | None:
        if repo not in collaborators_cache:
            collaborators_cache[repo] = collect_repo_collaborators(gh, repo)
        return collaborators_cache[repo]

    prs = collect_prs_for_report(gh, cfg, repo_collaborators)

    repo_stats: dict[str, dict[str, int]] = {}
    stall_by_key: dict[str, tuple[float, int]] = {}  # pr key -> (stall_wh, stall_days)

    for pr in prs:
        stats = repo_stats.setdefault(pr.repo, {"open": 0})
        stats["open"] += 1

        entry = pr_state_entry(state, pr.key())

        if pr.source != cfg.source_internal and not (pr.is_draft and not pr.is_bot):
            new_stall, stall_wh, stall_days = compute_stall(
                pr, cfg, entry.get("stall", {}), now, cfg.tzinfo())
            entry["stall"] = new_stall
            stall_by_key[pr.key()] = (stall_wh, stall_days)

    # Assignee-grouped report. The caller decides cadence; `report_due` here just
    # means "there is something to surface" (drives the exit code).
    recipients = build_report(prs, cfg, stall_by_key)
    report = render_report(recipients, cfg)
    report_due = bool(report)

    # Drop stall clocks for PRs no longer open in the scanned repos, then persist
    # the report's own state (per-PR stall clocks) so fingerprints stay current.
    prune_state(state, {pr.key() for pr in prs}, set(cfg.repos))
    save_state(cfg.state_file, state)

    return {
        "generated_at": now.isoformat(),
        "repos": repo_stats,
        "report": report,
        "report_due": report_due,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=(
            "Emit the assignee-grouped escalation report for open shader-slang "
            "PRs. Reads only live GitHub state and writes nothing to GitHub. All "
            "configuration except the flag below lives in the constants at the "
            "top of this file."
        )
    )
    p.add_argument("--recipient-map", default="", metavar="PATH",
                   help="Path to a flat JSON object mapping GitHub login -> destination "
                        "user ID (e.g. Discord). Mapped logins render as <@id> mentions in "
                        "the report; unmapped logins (or no file) render as inert `backticks`.")
    return p.parse_args(argv)


def _print_summary(summary: dict[str, Any]) -> None:
    print(f"[REPORT] @ {summary['generated_at']}")
    for repo, st in sorted(summary["repos"].items()):
        print(f"  {repo}: {st['open']} open")
    report = summary.get("report") or ""
    if report:
        print("\n--- report ---\n")
        print(report)
    else:
        print("\n(no report — nothing needs attention this run)")


def main(argv: list[str]) -> int:
    args = parse_args(argv)

    gh = Gh(find_gh())

    cfg = Config()
    if args.recipient_map:
        cfg.recipient_map = load_recipient_map(args.recipient_map)

    # Verify access to the target org (or a configured repo) before doing work.
    gh.preflight(cfg)

    # Default scope: every non-archived repo in the org (DEFAULT_REPOS is empty).
    if not cfg.repos:
        cfg.repos = list_org_repos(gh, cfg.org)
        if not cfg.repos:
            raise SystemExit(f"No repositories found in org {cfg.org!r}.")

    now = datetime.now(timezone.utc)
    summary = run_report(gh, cfg, now)
    _print_summary(summary)

    # Exit 10 signals "there is a report to surface" so the caller can decide
    # whether to wake the agent; 0 means nothing needs attention this run. The
    # caller owns cadence — the script does not throttle.
    return 10 if summary.get("report_due") else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
