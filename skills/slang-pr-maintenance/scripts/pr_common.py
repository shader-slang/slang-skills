#!/usr/bin/env python3
"""Shared, board-agnostic library for the slang-pr-maintenance scripts.

Holds everything both entrypoints need: configuration + constants, the
observable PR shape, the `gh` I/O layer, the batched PR/CI/review collection,
org/team/collaborator reads, source classification, assignee/reviewer
selection, the committer-signal glue, and small time/JSON/state utilities.

Two entrypoints build on this:
  - pr_report.py  the default, board-free escalation report (no ProjectsV2).
  - pr_sweep.py   the ProjectsV2 state machine (board reconcile + writes).

Portable: depends only on an authenticated `gh` (and, optionally, a local git
checkout as a fast path) plus the stdlib and the pr_signal module. No nanoclaw /
MCP / container assumptions. All org and infra constants are defaults here with
shader-slang values.
"""
from __future__ import annotations

# This module is thin glue around the `gh` CLI and the untyped JSON it returns.
# Fully typing every GitHub payload (TypedDicts for PRs, reviews, ProjectsV2,
# check-runs, ...) would dwarf the logic and obscure it, so the strict
# "unknown/Any" type rules are relaxed for this file; the pure decision
# functions are covered by the test modules instead.
# pyright: reportAny=false, reportExplicitAny=false, reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnknownVariableType=false, reportUnknownParameterType=false, reportUnknownLambdaType=false, reportUnusedCallResult=false, reportImplicitStringConcatenation=false, reportUninitializedInstanceVariable=false, reportImplicitRelativeImport=false

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

import pr_signal

try:
    from zoneinfo import ZoneInfo
except Exception:  # pragma: no cover - zoneinfo is stdlib on 3.9+
    ZoneInfo = None


# ---------------------------------------------------------------------------
# Configuration — EDIT HERE.
#
# The command-line flags differ per entrypoint (see each script). Everything
# else is a constant below: change it here if the org/board/teams/thresholds
# ever move.
# ---------------------------------------------------------------------------

DEFAULT_ORG = "shader-slang"
# Empty -> every non-archived repo in DEFAULT_ORG. Set to a comma-separated
# "owner/name,owner/name" list to restrict the sweep to a subset.
DEFAULT_REPOS = ""
# The "Slang PR Tracking" ProjectsV2 board node ID (state machine only).
DEFAULT_PROJECT_ID = "PVT_kwDOAb2kZs4BSJKy"
# Bot identities. `Copilot` is the GitHub Copilot coding-agent's *assignee/
# reviewer* login (GitHub types it as a User there, not a Bot, so it must be
# matched by name); `copilot-swe-agent` is its author form.
DEFAULT_BOT_AUTHORS = "nv-slang-bot,slang-coworker-nanoclaw,Copilot,copilot-swe-agent"
# Reviewers auto-assigned by repo automation who cannot actually approve (so they
# never count as "review already covered"). They are unrequested when the sweep
# assigns a PR. GitHub's is_bot accounts (e.g. app/*) are ignored separately.
DEFAULT_IGNORED_REVIEWERS = "bmillsNV"
# Community PRs are assigned an owner from this team (parent of the bot-owners
# subteam; its member list includes the subteam's members).
DEFAULT_OWNERS_TEAM = "shader-slang/pr-owners"
# Bot PRs are assigned an owner from this (sub)team.
DEFAULT_BOT_OWNERS_TEAM = "shader-slang/bot-pr-owners"
# The draft-PR coverage check whose success gates Revising -> Todo; set per deployment.
DEFAULT_COVERAGE_CHECK = ""

# Committer-signal weighting (see collect_committer_signal). Per-file signal =
# max(additions, deletions) * file_multiplier. The table maps a directory glob
# to a multiplier; the longest (most specific) matching glob wins, else
# DEFAULT_FILE_MULTIPLIER. Edit per deployment.
DEFAULT_FILE_MULTIPLIERS: list[tuple[str, float]] = [
    ("source/slang/**", 3.0),
    ("source/**", 2.0),
    ("tools/**", 1.5),
    ("tests/**", 1.0),
    ("docs/**", 0.5),
]
DEFAULT_FILE_MULTIPLIER = 1.0       # unmatched paths
DEFAULT_SIGNAL_TOP_FILES = 10       # rank by the top-K most significant files
DEFAULT_SIGNAL_COMMITS = 5          # last N commits per file to sample
DEFAULT_SIGNAL_HORIZON_DAYS = 180   # only consider commits within this window
DEFAULT_SIGNAL_FINALISTS = pr_signal.DEFAULT_SIGNAL_FINALISTS        # top candidates re-scored by per-file LOC
DEFAULT_SIGNAL_CLEAR_MARGIN = pr_signal.DEFAULT_SIGNAL_CLEAR_MARGIN  # skip tiebreak when #1 leads #2 by this

# Board option names (Status / Source single-selects).
DEFAULT_STATUS_FIELD = "Status"
DEFAULT_STATUS_REVISING = "Revising"
DEFAULT_STATUS_TODO = "Todo"
DEFAULT_STATUS_INPROGRESS = "In Progress"
DEFAULT_STATUS_DONE = "Done"
DEFAULT_SOURCE_FIELD = "Source"
DEFAULT_SOURCE_INTERNAL = "Internal"
DEFAULT_SOURCE_COMMUNITY = "Community"
DEFAULT_SOURCE_BOT = "Bot"

# Oversight / noise-control thresholds.
DEFAULT_REPORT_INTERVAL_HOURS = 24.0  # the recipient-grouped report is surfaced at most this often
DEFAULT_WORKDAY_TZ = "America/Los_Angeles"
DEFAULT_READY_COMMENT = True        # post the one-time "ready for review" comment

# Where the computed plan and the per-PR stall / last-report state are written.
PLAN_FILE = "./.pr-sweep-plan.json"
STATE_FILE = "./.pr-sweep-state.json"


def _split_csv(s: str) -> list[str]:
    return [x.strip() for x in s.split(",") if x.strip()]


def _progress(msg: str) -> None:
    """Liveness heartbeat to stderr. A run is long-running (minutes) and
    otherwise silent until the end; steady stderr output tells a runner it is
    alive so the process is not killed for apparent inactivity. Kept off stdout,
    which carries only the summary + report the agent forwards."""
    print(msg, file=sys.stderr, flush=True)


@dataclass
class Config:
    repos: list[str] = field(default_factory=lambda: _split_csv(DEFAULT_REPOS))
    project_id: str = DEFAULT_PROJECT_ID
    org: str = DEFAULT_ORG
    status_field: str = DEFAULT_STATUS_FIELD
    status_revising: str = DEFAULT_STATUS_REVISING
    status_todo: str = DEFAULT_STATUS_TODO
    status_inprogress: str = DEFAULT_STATUS_INPROGRESS
    status_done: str = DEFAULT_STATUS_DONE
    coverage_check: str = DEFAULT_COVERAGE_CHECK
    owners_team: str = DEFAULT_OWNERS_TEAM
    bot_owners_team: str = DEFAULT_BOT_OWNERS_TEAM
    maintainer: str = ""
    source_field: str = DEFAULT_SOURCE_FIELD
    source_internal: str = DEFAULT_SOURCE_INTERNAL
    source_community: str = DEFAULT_SOURCE_COMMUNITY
    source_bot: str = DEFAULT_SOURCE_BOT
    file_multipliers: list[tuple[str, float]] = field(
        default_factory=lambda: list(DEFAULT_FILE_MULTIPLIERS))
    default_multiplier: float = DEFAULT_FILE_MULTIPLIER
    signal_top_files: int = DEFAULT_SIGNAL_TOP_FILES
    signal_commits: int = DEFAULT_SIGNAL_COMMITS
    signal_horizon_days: int = DEFAULT_SIGNAL_HORIZON_DAYS
    signal_finalists: int = DEFAULT_SIGNAL_FINALISTS
    signal_clear_margin: float = DEFAULT_SIGNAL_CLEAR_MARGIN
    bot_authors: list[str] = field(
        default_factory=lambda: _split_csv(DEFAULT_BOT_AUTHORS))
    ignored_reviewers: list[str] = field(
        default_factory=lambda: _split_csv(DEFAULT_IGNORED_REVIEWERS))
    report_interval_hours: float = DEFAULT_REPORT_INTERVAL_HOURS
    workday_tz: str = DEFAULT_WORKDAY_TZ
    ready_comment: bool = DEFAULT_READY_COMMENT
    apply: bool = False
    state_file: str = STATE_FILE
    plan_file: str = PLAN_FILE
    # GitHub login (lowercased) -> destination user ID for report mentions. Empty
    # (the default) means nobody is mapped, so every login renders as inert
    # backticks. Populated from --recipient-map. See pr_report.format_mention.
    recipient_map: dict[str, str] = field(default_factory=dict)

    def tzinfo(self):
        if ZoneInfo is not None:
            try:
                return ZoneInfo(self.workday_tz)
            except Exception:
                pass
        return timezone.utc


# ---------------------------------------------------------------------------
# Observable PR state (plain data, used by pure logic in both entrypoints)
# ---------------------------------------------------------------------------

# CI states
CI_PASSED = "passed"
CI_FAILED = "failed"
CI_PENDING = "pending"
CI_ACTION_REQUIRED = "action_required"
CI_NONE = "none"

# Bot-transparency disclaimer appended to the report and to any PR comment.
BOT_DISCLAIMER = (
    "\n\n> <sub>\U0001f916 Generated by an automated Slang coworker — may be "
    "inaccurate. A human maintainer should verify.</sub>"
)


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
    node_id: str = ""    # GraphQL node id (for adding to the project board)
    source: str = ""     # board "Source": Internal | Community | Bot (resolved)
    source_unset: bool = False  # board had no Source -> classified + needs writing
    assignees: list[str] = field(default_factory=list)
    head_sha: str = ""
    review_decision: str = ""  # APPROVED | CHANGES_REQUESTED | REVIEW_REQUIRED | ""
    in_merge_queue: bool = False
    existing_reviewers: list[str] = field(default_factory=list)  # currently-requested reviewers
    created_at: datetime | None = None
    updated_at: datetime | None = None
    board_status: str | None = None
    ci_state: str = CI_NONE
    coverage_passed: bool = False
    last_review_at: datetime | None = None
    change_requested: bool = False
    last_activity_at: datetime | None = None
    # Selection inputs gathered during collect (for unassigned, non-exempt PRs):
    #  - committers_by_signal: candidate logins ranked by weighted file signal
    #    (highest first), excluding the author and bots.
    #  - issue_assignees: raw logins assigned to the PR's linked (closing) issue
    #    (filtered against the owner pool at selection time).
    committers_by_signal: list[str] = field(default_factory=list)
    issue_assignees: list[str] = field(default_factory=list)  # raw logins on linked issue(s)
    changed_files: dict[str, float] = field(default_factory=dict)  # path -> max(add, del)
    # Selection results (computed from the inputs above):
    assignee_pick: str | None = None
    review_requests: list[str] = field(default_factory=list)
    reviewers_to_remove: list[str] = field(default_factory=list)  # ignored reviewers present
    # board addressing for writes (filled during the state-machine collect)
    project_item_id: str | None = None

    def key(self) -> str:
        return f"{self.repo}#{self.number}"


# ---------------------------------------------------------------------------
# PURE LOGIC (no I/O) shared by both entrypoints
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
    """Whether the automated gate that promotes Revising -> Todo is satisfied.

    Human PRs promote on clean CI. Bot PRs are shepherded by a human owner, so
    they promote to Todo (with an assignee) regardless of draft state — unless a
    coverage check is configured, in which case it gates them.
    """
    if pr.is_bot:
        return pr.coverage_passed if cfg.coverage_check else True
    return pr.ci_state == CI_PASSED


def source_for(is_bot: bool, can_commit: bool, cfg: Config) -> str:
    """Source classification decision (pure): Bot if a bot authored it, else
    Internal if the author can commit to the target repo, else Community."""
    if is_bot:
        return cfg.source_bot
    return cfg.source_internal if can_commit else cfg.source_community


def classify_source(pr: PR, cfg: Config, collaborators: set[str]) -> str:
    """Classify a PR's Source. Pure: `collaborators` is the repo's write+ set
    (Internal iff the author can commit to the repo)."""
    return source_for(pr.is_bot, pr.author in collaborators, cfg)


def select_assignee_and_reviewers(
    issue_assignees: list[str],
    committers_by_signal: list[str],
    owners: set[str],
    collaborators: set[str],
    author: str,
    maintainer: str,
    existing_reviewers: list[str] | None = None,
    bot_authors: list[str] | None = None,
    ignored_reviewers: set[str] | None = None,
) -> tuple[str, list[str]]:
    """Decide the assignee + review-request set for a Community/Bot PR. Pure.

    Reviewers = the assignee, plus the single highest-signal committer who is a
    repo `collaborators` member but not `owners` (if any) — but only when the PR
    has no *real* reviewer already requested. A real reviewer excludes bots and
    `ignored_reviewers` (auto-assigned non-approvers like bmillsNV), since those
    cannot approve. The PR author is never requested. `committers_by_signal` is
    highest-signal-first and excludes author/bots; `issue_assignees` are raw
    logins filtered against `owners`."""
    bot_authors = bot_authors or []
    ignored_lower = {r.lower() for r in (ignored_reviewers or set())}
    excluded = author.lower()
    issue_owner_assignees = [
        a for a in issue_assignees
        if a in owners and a.lower() != excluded and not a.lower().endswith("[bot]")
    ]
    owner_committers = [c for c in committers_by_signal if c in owners]
    if issue_owner_assignees:
        assignee = issue_owner_assignees[0]
    elif owner_committers:
        assignee = owner_committers[0]
    else:
        assignee = maintainer

    # A reviewer who can actually approve already requested? Then add no more.
    real_existing = [
        r for r in (existing_reviewers or [])
        if r and r.lower() not in ignored_lower
        and not pr_signal.classify_is_bot(r, bot_authors)
        and not r.lower().endswith("[bot]")
    ]
    if real_existing:
        return assignee, []

    reviewers = [assignee]
    extra = [c for c in committers_by_signal if c in collaborators and c not in owners]
    if extra and extra[0] != assignee:
        reviewers.append(extra[0])
    # GitHub rejects requesting review from the PR author.
    reviewers = [r for r in reviewers if r and r.lower() != author.lower()]
    seen: set[str] = set()
    deduped: list[str] = []
    for r in reviewers:
        if r.lower() not in seen:
            seen.add(r.lower())
            deduped.append(r)
    return assignee, deduped


def _select_assignee_reviewers(pr: PR, cfg: Config, owners_members: set[str],
                               bot_owners_members: set[str],
                               repo_collaborators: Callable[[str], set[str]]) -> None:
    """Fill pr.assignee_pick / review_requests / reviewers_to_remove for an
    unassigned, non-exempt PR. PRs already in the merge queue or human drafts
    are far enough along (or not-ready) that assigning adds only noise."""
    if pr.assignees or pr.in_merge_queue or (pr.is_draft and not pr.is_bot):
        return
    ignored_lower = {r.lower() for r in cfg.ignored_reviewers}
    pr.reviewers_to_remove = [
        r for r in pr.existing_reviewers if r.lower() in ignored_lower]
    if pr.source == cfg.source_internal:
        # Internal: the author drives; no auto-requested reviewers.
        pr.assignee_pick, pr.review_requests = pr.author, []
        return
    pool = bot_owners_members if pr.source == cfg.source_bot else owners_members
    pr.assignee_pick, pr.review_requests = select_assignee_and_reviewers(
        pr.issue_assignees, pr.committers_by_signal,
        pool, repo_collaborators(pr.repo), pr.author, cfg.maintainer,
        existing_reviewers=pr.existing_reviewers,
        bot_authors=cfg.bot_authors,
        ignored_reviewers=set(cfg.ignored_reviewers),
    )


# ---------------------------------------------------------------------------
# State file (per-PR stall clocks + last_report_at; also used by the
# state-machine apply step when a plan embeds state)
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# gh I/O layer (the only place that shells out)
# ---------------------------------------------------------------------------

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

    def graphql(self, query: str, variables: dict[str, Any] | None = None) -> Any:
        args = ["api", "graphql", "-f", f"query={query}"]
        for k, v in (variables or {}).items():
            args += ["-F", f"{k}={v}"]
        out = self.run(args)
        return json.loads(out) if out.strip() else None

    def preflight(self) -> None:
        # Fail loudly if unauthenticated.
        proc = subprocess.run([self.exe, "auth", "status"], capture_output=True, text=True)
        if proc.returncode != 0:
            raise SystemExit(
                "gh is not authenticated (gh auth status failed). "
                "Run `gh auth login` with the required scopes (see the skill's Prerequisites)."
            )


# ---------------------------------------------------------------------------
# Collect (bulk reads)
# ---------------------------------------------------------------------------

def list_org_repos(gh: Gh, org: str) -> list[str]:
    """Every non-archived repo in `org` (owner/name), via `gh repo list`."""
    data = gh.json([
        "repo", "list", org, "--no-archived", "--limit", "1000",
        "--json", "nameWithOwner",
    ]) or []
    return [r["nameWithOwner"] for r in data if r.get("nameWithOwner")]


def list_team_members(gh: Gh, team: str) -> set[str]:
    """Member logins of an org team given as 'org/slug'. Empty set on missing
    team or access error (callers then flag PRs as needing a reviewer)."""
    if "/" not in team:
        return set()
    org, slug = team.split("/", 1)
    raw = gh.api(f"orgs/{org}/teams/{slug}/members", jq=".[].login", paginate=True)
    return {line.strip() for line in (raw or "").splitlines() if line.strip()}


def collect_repo_collaborators(gh: Gh, repo: str) -> set[str]:
    """Logins with write+ access (push/maintain/admin) to `repo` — the
    extra-reviewer pool. Read-only collaborators are excluded. Empty set on
    access error (the endpoint needs push access on the repo)."""
    raw = gh.api(
        f"repos/{repo}/collaborators",
        jq=".[] | select(.permissions.push == true) | .login",
        paginate=True,
    )
    return {line.strip() for line in (raw or "").splitlines() if line.strip()}


# PRs per GraphQL page. Cost/nodes are tiny (4 pts / ~12k nodes at 25), but the
# deeply-nested query is heavy server-side: n=50 returns HTTP 504 on slang, while
# n=25 resolves in ~5-6s. So the cap here is server timeout, not budget.
DEFAULT_PR_PAGE_SIZE = 25

# One batched query returns, per open PR, everything callers need: core fields,
# CI rollup, reviews, merge-queue membership, linked-issue assignees, requested
# reviewers, assignees, and changed files.
_PR_QUERY = """
query($owner: String!, $name: String!, $n: Int!, $cursor: String) {
  repository(owner: $owner, name: $name) {
    pullRequests(states: OPEN, first: $n, after: $cursor,
                 orderBy: {field: UPDATED_AT, direction: DESC}) {
      pageInfo { hasNextPage endCursor }
      nodes {
        number title url id isDraft headRefOid createdAt updatedAt reviewDecision
        author { login __typename }
        assignees(first: 10) { nodes { login } }
        reviewRequests(first: 20) { nodes { requestedReviewer { __typename ... on User { login } } } }
        commits(last: 1) { nodes { commit { statusCheckRollup { contexts(first: 100) { nodes {
          __typename
          ... on CheckRun { name status conclusion }
          ... on StatusContext { context state }
        } } } } } }
        reviews(last: 50) { nodes { state submittedAt author { login } } }
        mergeQueueEntry { id }
        closingIssuesReferences(first: 10) { nodes { assignees(first: 20) { nodes { login } } } }
        files(first: 100) { nodes { path additions deletions } }
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


def parse_pr_node(node: dict[str, Any], repo: str, cfg: Config) -> PR:
    """Build a fully-populated PR from one batched-query GraphQL node. Pure."""
    author = node.get("author") or {}
    login = author.get("login", "") or ""
    is_bot = author.get("__typename") == "Bot" or pr_signal.classify_is_bot(login, cfg.bot_authors)

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

    issue_assignees: list[str] = []
    for iss in ((node.get("closingIssuesReferences") or {}).get("nodes")) or []:
        for a in ((iss.get("assignees") or {}).get("nodes")) or []:
            lg = a.get("login")
            if lg and lg not in issue_assignees:
                issue_assignees.append(lg)

    changed_files: dict[str, float] = {}
    for f in ((node.get("files") or {}).get("nodes")) or []:
        path = f.get("path")
        if path:
            changed_files[path] = float(max(f.get("additions", 0) or 0, f.get("deletions", 0) or 0))

    return PR(
        repo=repo,
        number=node["number"],
        url=node.get("url", "") or "",
        title=node.get("title", "") or "",
        author=login,
        is_bot=is_bot,
        is_draft=bool(node.get("isDraft")),
        node_id=node.get("id", "") or "",
        assignees=assignees,
        head_sha=node.get("headRefOid", "") or "",
        review_decision=node.get("reviewDecision", "") or "",
        existing_reviewers=existing_reviewers,
        in_merge_queue=(node.get("mergeQueueEntry") is not None),
        created_at=parse_iso(node.get("createdAt")),
        updated_at=parse_iso(node.get("updatedAt")),
        last_activity_at=parse_iso(node.get("updatedAt")),
        ci_state=ci_state,
        coverage_passed=coverage_passed,
        last_review_at=last_review_at,
        change_requested=change_requested,
        issue_assignees=issue_assignees,
        changed_files=changed_files,
    )


def collect_committer_signal(gh: Gh, pr: PR, cfg: Config,
                             cache: pr_signal.SignalCache, since: str) -> None:
    """Fill pr.committers_by_signal by delegating to the pr_signal ranking
    module (hybrid: cheap total-LOC GraphQL pass + per-file-LOC tiebreak). The
    run-scoped `cache` dedups PR-independent source fetches across PRs."""
    pr.committers_by_signal = pr_signal.compute_committer_ranking(
        gh, pr.repo, pr.author,
        loc_by_file=pr.changed_files,
        file_multipliers=cfg.file_multipliers,
        default_multiplier=cfg.default_multiplier,
        top_files=cfg.signal_top_files,
        commits=cfg.signal_commits,
        horizon_days=cfg.signal_horizon_days,
        bot_authors=cfg.bot_authors,
        finalists=cfg.signal_finalists,
        clear_margin=cfg.signal_clear_margin,
        since=since,
        cache=cache,
    )
