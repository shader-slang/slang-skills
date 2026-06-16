#!/usr/bin/env python3
"""Board-free escalation report for open shader-slang PRs (the default entrypoint).

Computes a throttled, assignee-grouped report of open PRs needing human
attention entirely from **live GitHub state** — no GitHub ProjectsV2 access. It
reads PRs/CI/reviews/collaborators via `gh`, re-derives each PR's lifecycle
stage from those signals, and emits a once-daily, recipient-grouped report
(optionally with Discord/Slack mentions).

The report does not predict owners: a PR with no human assignee is surfaced
honestly under an "Unassigned" group (listed first), since assignment happens
elsewhere (pr_sweep.py / a GitHub Action). It therefore needs no maintainer flag
and no team-membership reads.

The companion pr_sweep.py is the ProjectsV2 state machine (board reconcile +
writes); the two share pr_common.py. This split lets the report run without any
ProjectsV2 scope, ahead of the state machine becoming GitHub Actions.

ProjectsV2 -> live-state mapping
--------------------------------
The board previously supplied three per-PR fields; here they are re-derived (or
dropped) from the live PR query:

  - board_status -> derive_stage(pr, cfg). The board Status was just a cached
    reconciliation of CI/review/draft/merge-queue signals, all present in the
    live PR query. Only Revising / Todo / Done are observable; "In Progress" is
    a human board action and collapses into Todo (lossless: the report's only
    consumer, _awaiting_review, already treated Todo and In Progress
    identically). The derivation is per source — the contributor fingerprint
    keys on draft + CI + changes-requested, the bot fingerprint on
    promotion_gate_passed.
  - source -> classify_source(pr, cfg, collaborators) (live, every run). A
    manual board Source override is ignored.
  - project_item_id -> dropped (only used for board writes).

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
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone, tzinfo
from collections.abc import Callable
from typing import Any

import pr_signal
from pr_common import (
    CI_ACTION_REQUIRED,
    CI_FAILED,
    CI_PASSED,
    BOT_DISCLAIMER,
    Config,
    Gh,
    PR,
    _progress,
    classify_source,
    collect_open_prs,
    collect_repo_collaborators,
    find_gh,
    list_org_repos,
    load_state,
    parse_iso,
    promotion_gate_passed,
    pr_state_entry,
    save_state,
    working_hours_between,
)


# Report rendering
ESCALATED_ICON = "\u2b06\ufe0f"   # up arrow: escalated/overdue (past the second rung)
COMMUNITY_ICON = "\U0001f310"     # globe
BOT_ICON = "\U0001f916"           # robot

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
    """Board-free analog of the board Status field, from live GitHub signals.

    Replaces the ProjectsV2 `Status` the report used to read. Only Revising /
    Todo / Done are observable without the board; "In Progress" is a human board
    action and collapses into Todo (the report treats them identically).

    Per source ("different fingerprints"):
      - Bot: promoted (Todo) whenever promotion_gate_passed holds (always,
        unless a coverage check is configured and failing); drafts are NOT
        exempt.
      - Contributor/Community: Revising while draft / changes-requested / CI
        failing (or not yet passed); promoted to Todo only once not a draft and
        CI has passed.
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
            and not pr_signal.classify_is_bot(r, cfg.bot_authors)
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
    """The predicate ladder for a PR's source (empty -> not surfaced)."""
    if pr.source == cfg.source_bot:
        return BOT_LADDER
    if pr.source == cfg.source_community:
        return COMMUNITY_LADDER
    return []  # Internal / unknown: no maintainer oversight


def source_icon(pr: PR, cfg: Config) -> str:
    if pr.source == cfg.source_bot:
        return BOT_ICON
    if pr.source == cfg.source_community:
        return COMMUNITY_ICON
    return ""


# --- Movement / stall clock ---------------------------------------------------

def compute_stall(pr: PR, cfg: Config, prior: dict[str, Any], now: datetime,
                  tz: tzinfo) -> tuple[dict[str, Any], float, int]:
    """Track when a PR last *moved* (derived stage / head SHA / last review
    changed) and how long it has been stalled. Returns (new_state, stall_wh,
    stall_days). Pure. First sight anchors to the PR's last activity so a stale
    backlog surfaces immediately.

    The derived stage (derive_stage) replaces the board Status that used to
    anchor movement: a contributor PR's CI going green and a bot PR's promotion
    each register as movement, per source, without the board."""
    fp = [derive_stage(pr, cfg), pr.head_sha,
          pr.last_review_at.isoformat() if pr.last_review_at else None]
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
    is surfaced honestly (assignment happens elsewhere: pr_sweep / a GitHub
    Action)."""
    for a in pr.assignees:
        if a and not pr_signal.classify_is_bot(a, cfg.bot_authors) and not a.lower().endswith("[bot]"):
            return a
    return UNASSIGNED


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
    """Order within an assignee's group: Community PRs before Bot PRs, and within
    each, escalated (up-arrow) before not-escalated. Stable on ties (preserves
    sweep order)."""
    if it.pr.source == cfg.source_community:
        src = 0
    elif it.pr.source == cfg.source_bot:
        src = 1
    else:
        src = 2
    return (src, 0 if it.escalated else 1)


def render_report(recipients: dict[str, list[ReportItem]], cfg: Config) -> str:
    """Render the assignee-grouped daily report. The Unassigned group is listed
    first, then named assignees sorted; an `escalated` item keeps its place and
    gains the overdue up-arrow."""
    if not recipients:
        return ""
    named = sorted(r for r in recipients if r != UNASSIGNED)
    order = ([UNASSIGNED] if UNASSIGNED in recipients else []) + named
    legend = (f"_{BOT_ICON} agent PR · {COMMUNITY_ICON} community PR · "
              f"{ESCALATED_ICON} escalated/overdue_")
    lines = ["## Slang PR Escalation Report", "", legend, ""]
    for recipient in order:
        header = "Unassigned" if recipient == UNASSIGNED else format_mention(recipient, cfg)
        lines.append(f"- **{header}**:")
        for it in sorted(recipients[recipient], key=lambda i: _item_sort_key(i, cfg)):
            prefix = (ESCALATED_ICON + " ") if it.escalated else ""
            icon = source_icon(it.pr, cfg)
            link = f"[{_repo_short(it.pr.repo)}#{it.pr.number}]({it.pr.url})"
            lines.append(f"  - {prefix}{icon} {link} — {it.reason}")
    lines.append("")
    lines.append(BOT_DISCLAIMER.strip())
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
# Collect (board-free) + report orchestration
# ---------------------------------------------------------------------------

def collect_prs_for_report(gh: Gh, cfg: Config,
                           repo_collaborators: Callable[[str], set[str]]) -> list[PR]:
    """All open PRs across cfg.repos, fully populated by the batched query, with
    Source classified live (no board). The report does not predict owners, so no
    committer-signal ranking is run here."""
    _progress(f"sweeping {len(cfg.repos)} repo(s) for the report — this typically takes a few minutes…")
    prs: list[PR] = []
    for repo in cfg.repos:
        for pr in collect_open_prs(gh, repo, cfg):
            # No board: classify Source live (reusing the repo's write+
            # collaborator set, fetched lazily).
            pr.source = classify_source(pr, cfg, repo_collaborators(repo))
            pr.is_bot = (pr.source == cfg.source_bot)
            prs.append(pr)
    _progress(f"collected {len(prs)} open PR(s) across {len(cfg.repos)} repo(s).")
    return prs


def run_report(gh: Gh, cfg: Config, now: datetime) -> dict[str, Any]:
    """Build the assignee-grouped report from live state and persist the per-PR
    stall clocks + last_report_at. No GitHub writes; the only side effect is the
    local state file (the report's own bookkeeping)."""
    state = load_state(cfg.state_file)

    # The write+ collaborator set is per-repo, memoized; used for live Source
    # classification (Internal iff the author can commit to the repo).
    collaborators_cache: dict[str, set[str]] = {}

    def repo_collaborators(repo: str) -> set[str]:
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

    # Assignee-grouped report.
    recipients = build_report(prs, cfg, stall_by_key)
    report = render_report(recipients, cfg)

    # Daily cadence: the report is surfaced at most once per interval. `report_due`
    # gates the exit code; `last_report_at` advances when a due report is surfaced.
    last_report = parse_iso(state.get("last_report_at"))
    report_due = bool(report) and (
        last_report is None
        or (now - last_report) >= timedelta(hours=cfg.report_interval_hours))
    if report_due:
        state["last_report_at"] = now.isoformat()

    # Persist the report's own state (stall clocks + last_report_at) every run so
    # the stall fingerprints stay current and the daily throttle advances.
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
            "Emit the board-free, assignee-grouped escalation report for open "
            "shader-slang PRs. Reads only live GitHub state (no ProjectsV2 "
            "access) and writes nothing to GitHub. All configuration except the "
            "flags below lives in the constants at the top of pr_common.py."
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
        due = " (due — surface today)" if summary.get("report_due") else " (not due yet)"
        print(f"\n--- report{due} ---\n")
        print(report)
    else:
        print("\n(no report — nothing needs attention this sweep)")


def main(argv: list[str]) -> int:
    args = parse_args(argv)

    gh = Gh(find_gh())
    gh.preflight()

    cfg = Config()
    if args.recipient_map:
        cfg.recipient_map = load_recipient_map(args.recipient_map)

    # Default scope: every non-archived repo in the org (DEFAULT_REPOS is empty).
    if not cfg.repos:
        cfg.repos = list_org_repos(gh, cfg.org)
        if not cfg.repos:
            raise SystemExit(f"No repositories found in org {cfg.org!r}.")

    now = datetime.now(timezone.utc)
    summary = run_report(gh, cfg, now)
    _print_summary(summary)

    # Exit 10 signals "the daily report is due to be surfaced" so a scheduler can
    # decide whether to wake the agent; 0 means nothing to surface this sweep.
    return 10 if summary.get("report_due") else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
