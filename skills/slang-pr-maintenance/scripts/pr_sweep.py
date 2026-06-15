#!/usr/bin/env python3
"""Reconcile open PRs on a GitHub ProjectsV2 board toward their correct state.

A single sweep (intended to run ~every 30-60 min) drives every open PR one step
toward its correct board Status and emits a throttled, assignee-grouped report
of items needing human attention.

The script is the deterministic half of the slang-pr-maintenance skill: it
collects PR + board + CI + review state, computes exactly one transition per
PR, and (under --apply) performs the idempotent GitHub-side writes. The agent
only surfaces the emitted report.

Portable: depends only on an authenticated `gh` (and, optionally, a local git
checkout as a fast path). No nanoclaw / MCP / container assumptions. All org
and infra constants are flags with shader-slang defaults.

State machine (board Status field):
    Revising -> Todo -> In Progress -> Done
  - Revising: waiting on CI / a bot / a bot reviewer, before human involvement.
  - Todo:     ready for a human (assignee set); appears in the reviewer inbox.
  - InProgress: human-set on review start (this script never sets it).
  - Done:     merged or closed (usually board automation; ensured here).

Pure decision functions (reconcile, working_hours_between, compute_stall, the
predicate ladders, build_report) take plain data and are covered by
test_pr_sweep.py with no live `gh` calls. The committer-signal ranking lives in
the pr_signal module.
"""
from __future__ import annotations

# This module is thin glue around the `gh` CLI and the untyped JSON it returns.
# Fully typing every GitHub payload (TypedDicts for PRs, reviews, ProjectsV2,
# check-runs, ...) would dwarf the logic and obscure it, so the strict
# "unknown/Any" type rules are relaxed for this file; the pure decision
# functions are covered by test_pr_sweep.py instead.
# pyright: reportAny=false, reportExplicitAny=false, reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnknownVariableType=false, reportUnknownParameterType=false, reportUnknownLambdaType=false, reportUnusedCallResult=false, reportImplicitStringConcatenation=false, reportUninitializedInstanceVariable=false, reportImplicitRelativeImport=false

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

import pr_signal

try:
    from zoneinfo import ZoneInfo
except Exception:  # pragma: no cover - zoneinfo is stdlib on 3.9+
    ZoneInfo = None


# ---------------------------------------------------------------------------
# Configuration — EDIT HERE.
#
# The command-line flags are `--maintainer LOGIN` (the current Slang Maintainer,
# who rotates every two weeks; no default on purpose), `--apply`, and
# `--recipient-map PATH`. Everything else is a constant below: change it here
# if the org/board/teams/thresholds ever move.
# ---------------------------------------------------------------------------

DEFAULT_ORG = "shader-slang"
# Empty -> every non-archived repo in DEFAULT_ORG. Set to a comma-separated
# "owner/name,owner/name" list to restrict the sweep to a subset.
DEFAULT_REPOS = ""
# The "Slang PR Tracking" ProjectsV2 board node ID.
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
# DEFAULT_FILE_MULTIPLIER. Edit per deployment or override with --file-multipliers.
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
    """Liveness heartbeat to stderr. The sweep is long-running (minutes) and
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
    # backticks. Populated from --recipient-map. See format_mention.
    recipient_map: dict[str, str] = field(default_factory=dict)

    def tzinfo(self):
        if ZoneInfo is not None:
            try:
                return ZoneInfo(self.workday_tz)
            except Exception:
                pass
        return timezone.utc


# ---------------------------------------------------------------------------
# Observable PR state and the decision shape (plain data, used by pure logic)
# ---------------------------------------------------------------------------

# CI states
CI_PASSED = "passed"
CI_FAILED = "failed"
CI_PENDING = "pending"
CI_ACTION_REQUIRED = "action_required"
CI_NONE = "none"

# Report rendering
ESCALATED_ICON = "\u2b06\ufe0f"   # up arrow: escalated to the maintainer
COMMUNITY_ICON = "\U0001f310"     # globe
BOT_ICON = "\U0001f916"           # robot


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
    # Selection results (computed in the sweep from the inputs above):
    assignee_pick: str | None = None
    review_requests: list[str] = field(default_factory=list)
    reviewers_to_remove: list[str] = field(default_factory=list)  # ignored reviewers present
    # board addressing for writes (filled during collect)
    project_item_id: str | None = None

    def key(self) -> str:
        return f"{self.repo}#{self.number}"


@dataclass
class Decision:
    pr: PR
    set_status: str | None = None
    set_assignee: str | None = None
    request_reviewers: list[str] = field(default_factory=list)
    remove_reviewers: list[str] = field(default_factory=list)  # unrequest (e.g. bmillsNV)
    add_to_project: bool = False
    comment_kind: str | None = None  # "ready" | None

    def is_noop(self) -> bool:
        return not (
            self.set_status or self.set_assignee or self.request_reviewers
            or self.remove_reviewers or self.add_to_project or self.comment_kind
        )


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
    escalated: bool = False   # reached the maintainer rung and the recipient isn't the assignee


# ---------------------------------------------------------------------------
# PURE LOGIC (no I/O) -- exercised directly by test_pr_sweep.py
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


def _ensure_assignee(d: Decision, pr: PR) -> None:
    """Always-have-an-assignee rule: when a PR is unassigned and an assignee was
    resolved (issue -> commit-signal -> maintainer), set it, request reviewers,
    and unrequest any auto-assigned non-approvers (e.g. bmillsNV)."""
    if (not pr.assignees) and pr.assignee_pick:
        d.set_assignee = pr.assignee_pick
        d.request_reviewers = list(pr.review_requests)
        d.remove_reviewers = list(pr.reviewers_to_remove)


# --- Board-vs-reality corrections -------------------------------------------
# Each returns a Decision when it applies to this PR (terminating reconcile,
# even if the Decision is a no-op), or None to defer to the next correction /
# the normal lifecycle. `_CORRECTIONS` is consulted in order.

def _correct_off_board(pr: PR, cfg: Config) -> Decision | None:
    if pr.project_item_id is None:
        return Decision(pr=pr, add_to_project=True)
    return None


def _correct_terminal_state(pr: PR, cfg: Config) -> Decision | None:
    # Defensive: the sweep only lists open PRs, so board automation normally
    # handles this already.
    if pr.state not in ("MERGED", "CLOSED"):
        return None
    d = Decision(pr=pr)
    if pr.board_status != cfg.status_done:
        d.set_status = cfg.status_done
    return d


def _correct_misplaced_draft(pr: PR, cfg: Config) -> Decision | None:
    # Drafts remain otherwise exempt: no assignment or maintainer follow-ups.
    if not (pr.is_draft and not pr.is_bot):
        return None
    d = Decision(pr=pr)
    if pr.board_status in (cfg.status_todo, cfg.status_inprogress, cfg.status_done):
        d.set_status = cfg.status_revising
    return d


def _correct_done_status(pr: PR, cfg: Config) -> Decision | None:
    # An open PR in Done is fine only while in the merge queue; if it was bumped
    # out (or the repo has no queue) bounce it back — Revising on changes
    # requested, else Todo (ready for a human again).
    if pr.board_status != cfg.status_done:
        return None
    d = Decision(pr=pr)
    if pr.in_merge_queue:
        return d
    if pr.review_decision == "CHANGES_REQUESTED":
        d.set_status = cfg.status_revising
    else:
        d.set_status = cfg.status_todo
        _ensure_assignee(d, pr)
    return d


def _correct_failing_ci(pr: PR, cfg: Config) -> Decision | None:
    # Bot PRs are owner-shepherded and may sit in Todo while iterating, so they
    # are not bounced here — that would oscillate against promotion.
    if (not pr.is_bot and pr.board_status in (cfg.status_todo, cfg.status_inprogress)
            and pr.ci_state == CI_FAILED):
        return Decision(pr=pr, set_status=cfg.status_revising)
    return None


def _correct_orphan_in_progress(pr: PR, cfg: Config) -> Decision | None:
    # In Progress with no assignee can't be legitimately "in progress".
    if pr.board_status == cfg.status_inprogress and not pr.assignees:
        d = Decision(pr=pr, set_status=cfg.status_todo)
        _ensure_assignee(d, pr)
        return d
    return None


_CORRECTIONS: list[Callable[[PR, Config], Decision | None]] = [
    _correct_off_board,
    _correct_terminal_state,
    _correct_misplaced_draft,
    _correct_done_status,
    _correct_failing_ci,
    _correct_orphan_in_progress,
]


def _normal_lifecycle(pr: PR, cfg: Config) -> Decision:
    """The steady-state lifecycle once board-vs-reality corrections don't apply:
    assign the owner, return on blocking feedback, otherwise promote on a passed
    gate."""
    d = Decision(pr=pr)

    # Assign the owner + request reviewers on ready, unassigned human PRs early.
    if not pr.is_bot:
        _ensure_assignee(d, pr)

    # Blocking review feedback returns the PR to Revising.
    if pr.change_requested:
        if pr.board_status != cfg.status_revising:
            d.set_status = cfg.status_revising
        return d

    # Promotion: automated gate passed -> Todo (ready for a human). Bot PRs
    # (incl. drafts) land here so a human owner shepherds them to ready.
    if promotion_gate_passed(pr, cfg):
        if pr.board_status not in (cfg.status_todo, cfg.status_inprogress, cfg.status_done):
            d.set_status = cfg.status_todo
            # A draft is not actually "ready for review" yet — the assignee makes
            # it ready — so the one-time ready comment is for non-drafts only.
            if cfg.ready_comment and not pr.is_draft:
                d.comment_kind = "ready"
        # Bot PRs get their assignee + reviewers at promotion (no assignee while
        # iterating in Revising).
        if pr.is_bot:
            _ensure_assignee(d, pr)
    elif not pr.board_status:
        # Not ready yet: ensure it is at least Revising if it has no status.
        # (In Progress is human-owned; never touched here.)
        d.set_status = cfg.status_revising

    return d


def reconcile(pr: PR, cfg: Config) -> Decision:
    """Compute the single board transition this PR warrants. Idempotent: never
    proposes a write whose effect is already present. Board-vs-reality
    corrections take precedence over the normal lifecycle."""
    for correction in _CORRECTIONS:
        d = correction(pr, cfg)
        if d is not None:
            return d
    return _normal_lifecycle(pr, cfg)


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
    # Only "awaiting review" when a real (approve-capable) reviewer is requested.
    return (pr.board_status in (cfg.status_todo, cfg.status_inprogress)
            and bool(_real_reviewers(pr, cfg))
            and pr.review_decision != "APPROVED")


# Ladder rung thresholds are weekday-hours since the PR last moved.
DAY = 24.0
WEEK = 7 * DAY

# Community: external author, internal assignee provides oversight.
COMMUNITY_LADDER: list[Predicate] = [
    Predicate("needs_ci_approval",
              lambda pr, cfg: pr.ci_state == CI_ACTION_REQUIRED,
              lambda pr, cfg, days: "needs CI approval",
              (("assignee", 0.0), ("maintainer", DAY))),
    Predicate("changes_requested",
              lambda pr, cfg: pr.change_requested,
              lambda pr, cfg, days: "changes requested — check if author is still active / needs help",
              (("assignee", WEEK), ("maintainer", 2 * WEEK))),
    Predicate("awaiting_review",
              _awaiting_review,
              lambda pr, cfg, days: f"awaiting review from: {_reviewers_text(pr, cfg)}",
              (("assignee", DAY), ("maintainer", 2 * DAY))),
    Predicate("ci_failing",
              lambda pr, cfg: pr.ci_state == CI_FAILED,
              lambda pr, cfg, days: "CI failing — needs fixes",
              (("assignee", DAY), ("maintainer", 2 * DAY))),
    Predicate("idle",
              lambda pr, cfg: True,
              lambda pr, cfg, days: f"idle for {days} days",
              (("assignee", DAY), ("maintainer", 2 * DAY))),
]

# Bot: bot-authored, owner shepherds; lower urgency, no fork CI gate.
BOT_LADDER: list[Predicate] = [
    Predicate("awaiting_review",
              _awaiting_review,
              lambda pr, cfg, days: f"awaiting review from: {_reviewers_text(pr, cfg)}",
              (("assignee", 2 * DAY), ("maintainer", WEEK))),
    Predicate("ci_failing",
              lambda pr, cfg: pr.ci_state == CI_FAILED,
              lambda pr, cfg, days: "CI failing — needs fixes",
              (("assignee", 2 * DAY), ("maintainer", WEEK))),
    Predicate("idle",
              lambda pr, cfg: True,
              lambda pr, cfg, days: f"idle for {days} days",
              (("assignee", 2 * DAY), ("maintainer", WEEK))),
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

def compute_stall(pr: PR, prior: dict[str, Any], now: datetime,
                  tz: tzinfo) -> tuple[dict[str, Any], float, int]:
    """Track when a PR last *moved* (board Status / head SHA / last review
    changed) and how long it has been stalled. Returns (new_state, stall_wh,
    stall_days). Pure. First sight anchors to the PR's last activity so a stale
    backlog surfaces immediately."""
    fp = [pr.board_status, pr.head_sha,
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

def apply_pending_to_pr(pr: PR, decision: "Decision") -> None:
    """Fold the plan's pending actions into `pr` so the report reflects the
    post-plan world (a planned Todo->Revising bounce changes which predicate
    fires; a planned assignee/reviewer set updates routing). The planned board
    transition counts as movement, resetting the stall clock."""
    if decision.set_status:
        pr.board_status = decision.set_status
    if decision.set_assignee:
        pr.assignees = [decision.set_assignee]
    if decision.request_reviewers or decision.remove_reviewers:
        removed = {r.lower() for r in decision.remove_reviewers}
        revs = [r for r in pr.existing_reviewers if r.lower() not in removed]
        for r in decision.request_reviewers:
            if r not in revs:
                revs.append(r)
        pr.existing_reviewers = revs


def effective_assignee(pr: PR, cfg: Config) -> str:
    """The human the report holds responsible: the first non-bot assignee (a bot
    like `Copilot` can't act on a notice), else the signal-chosen owner, else the
    maintainer."""
    for a in pr.assignees:
        if a and not pr_signal.classify_is_bot(a, cfg.bot_authors) and not a.lower().endswith("[bot]"):
            return a
    return pr.assignee_pick or cfg.maintainer


def build_report(prs: list[PR], cfg: Config,
                 stall_by_key: dict[str, tuple[float, int]],
                 ) -> dict[str, list[ReportItem]]:
    """Group each flagged PR under its assignee (assignee login -> [ReportItem]).
    A PR surfaces once it passes the predicate's assignee rung; passing the
    maintainer rung escalates it *in place* (the `escalated` up-arrow) rather
    than duplicating it into a separate maintainer section. Pure given the
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
            continue  # not yet at the first (assignee) rung -> not surfaced
        maintainer_after = rungs.get("maintainer")
        assignee = effective_assignee(pr, cfg)
        # Escalated == reached the maintainer rung. The arrow fires even when the
        # maintainer is the assignee: it's a public signal others can use to keep
        # them honest about their own stalled items.
        escalated = maintainer_after is not None and stall_wh >= maintainer_after
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
    """Render the assignee-grouped daily report (maintainer's own group first).
    Items are grouped under their assignee; an `escalated` item keeps its place
    and gains the up-arrow rather than being copied to a maintainer section."""
    if not recipients:
        return ""
    order = ([cfg.maintainer] if cfg.maintainer in recipients else []) + \
        sorted(r for r in recipients if r != cfg.maintainer)
    legend = (f"_{BOT_ICON} agent PR · {COMMUNITY_ICON} community PR · "
              f"{ESCALATED_ICON} escalated to maintainer_")
    lines = ["## Slang PR Escalation Report", "", legend, ""]
    for recipient in order:
        lines.append(f"- **{format_mention(recipient, cfg)}**:")
        for it in sorted(recipients[recipient], key=lambda i: _item_sort_key(i, cfg)):
            prefix = (ESCALATED_ICON + " ") if it.escalated else ""
            icon = source_icon(it.pr, cfg)
            link = f"[{_repo_short(it.pr.repo)}#{it.pr.number}]({it.pr.url})"
            lines.append(f"  - {prefix}{icon} {link} — {it.reason}")
    lines.append("")
    lines.append(BOT_DISCLAIMER.strip())
    return "\n".join(lines).strip()


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


# ---------------------------------------------------------------------------
# State file (per-PR stall clocks + last_report_at)
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


def save_plan(path: str, summary: dict[str, Any]) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, sort_keys=True)
    os.replace(tmp, path)


def load_plan(path: str) -> dict[str, Any] | None:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, ValueError):
        return None


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
                "Run `gh auth login` with repo + project scopes."
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
    team or access error (the sweep then flags PRs as needing a reviewer)."""
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

# One batched query returns, per open PR, everything the sweep needs: core
# fields, CI rollup, reviews, merge-queue membership, linked-issue assignees,
# requested reviewers, assignees, and changed files. Replaces the per-PR REST
# fan-out (check-runs / reviews / mergeQueueEntry / closingIssues / files).
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


def _project_items_query(status_field: str, source_field: str) -> str:
    return """
query($project: ID!, $cursor: String) {
  node(id: $project) {
    ... on ProjectV2 {
      items(first: 100, after: $cursor) {
        pageInfo { hasNextPage endCursor }
        nodes {
          id
          status: fieldValueByName(name: %s) {
            ... on ProjectV2ItemFieldSingleSelectValue { name }
          }
          source: fieldValueByName(name: %s) {
            ... on ProjectV2ItemFieldSingleSelectValue { name }
          }
          content {
            ... on PullRequest { number repository { nameWithOwner } }
          }
        }
      }
    }
  }
}
""" % (json.dumps(status_field), json.dumps(source_field))


def collect_board_status(gh: Gh, cfg: Config) -> dict[str, dict[str, Any]]:
    """Map "owner/repo#number" -> {status, source, item_id} for board items."""
    query = _project_items_query(cfg.status_field, cfg.source_field)
    result: dict[str, dict[str, Any]] = {}
    cursor = None
    while True:
        variables = {"project": cfg.project_id}
        if cursor:
            variables["cursor"] = cursor
        data = gh.graphql(query, variables)
        node = (((data or {}).get("data") or {}).get("node") or {})
        items = (node.get("items") or {})
        for n in items.get("nodes", []) or []:
            content = n.get("content") or {}
            if "number" not in content:
                continue
            repo = ((content.get("repository") or {}).get("nameWithOwner")) or ""
            key = f"{repo}#{content['number']}"
            result[key] = {
                "status": (n.get("status") or {}).get("name"),
                "source": (n.get("source") or {}).get("name"),
                "item_id": n.get("id"),
            }
        page = items.get("pageInfo") or {}
        if page.get("hasNextPage"):
            cursor = page.get("endCursor")
        else:
            break
    return result


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


# ---------------------------------------------------------------------------
# Apply (writes; only under --apply)
# ---------------------------------------------------------------------------

BOT_DISCLAIMER = (
    "\n\n> <sub>\U0001f916 Generated by an automated Slang coworker — may be "
    "inaccurate. A human maintainer should verify.</sub>"
)

READY_COMMENT = "This PR has passed automated checks and is ready for human review."


@final
class Applier:
    """Performs GitHub-side writes. Resolves the project Status field option ids lazily."""

    def __init__(self, gh: Gh, cfg: Config):
        self.gh = gh
        self.cfg = cfg
        # field name -> (field_id, {option_name: option_id}); resolved lazily.
        self._fields: dict[str, tuple[str, dict[str, str]]] = {}

    def _field(self, name: str) -> tuple[str, dict[str, str]]:
        if name in self._fields:
            return self._fields[name]
        query = """
        query($project: ID!) {
          node(id: $project) {
            ... on ProjectV2 {
              field(name: %s) {
                ... on ProjectV2SingleSelectField { id options { id name } }
              }
            }
          }
        }
        """ % json.dumps(name)
        data = self.gh.graphql(query, {"project": self.cfg.project_id})
        fld = ((((data or {}).get("data") or {}).get("node") or {}).get("field") or {})
        opts = {o["name"]: o["id"] for o in (fld.get("options") or [])}
        resolved = (fld.get("id") or "", opts)
        self._fields[name] = resolved
        return resolved

    def _set_single_select(self, pr: PR, field_name: str, value: str) -> None:
        if not pr.project_item_id:
            print(f"  ! {pr.key()} not on board; cannot set {field_name}", file=sys.stderr)
            return
        field_id, options = self._field(field_name)
        option_id = options.get(value)
        if not field_id or not option_id:
            print(f"  ! {field_name} option {value!r} not found on board", file=sys.stderr)
            return
        mutation = """
        mutation($project: ID!, $item: ID!, $field: ID!, $option: String!) {
          updateProjectV2ItemFieldValue(input: {
            projectId: $project, itemId: $item, fieldId: $field,
            value: { singleSelectOptionId: $option }
          }) { projectV2Item { id } }
        }
        """
        self.gh.graphql(mutation, {
            "project": self.cfg.project_id,
            "item": pr.project_item_id,
            "field": field_id,
            "option": option_id,
        })

    def add_to_project(self, pr: PR) -> None:
        if not pr.node_id:
            print(f"  ! {pr.key()} has no node id; cannot add to board", file=sys.stderr)
            return
        mutation = """
        mutation($project: ID!, $content: ID!) {
          addProjectV2ItemById(input: { projectId: $project, contentId: $content }) {
            item { id }
          }
        }
        """
        self.gh.graphql(mutation, {"project": self.cfg.project_id, "content": pr.node_id})

    def set_status(self, pr: PR, status: str) -> None:
        self._set_single_select(pr, self.cfg.status_field, status)

    def set_source(self, pr: PR, source: str) -> None:
        self._set_single_select(pr, self.cfg.source_field, source)

    def set_assignee(self, pr: PR, login: str) -> None:
        self.gh.run([
            "api", "-X", "POST",
            f"repos/{pr.repo}/issues/{pr.number}/assignees",
            "-f", f"assignees[]={login}",
        ], check=False)

    def request_reviewers(self, pr: PR, logins: list[str]) -> None:
        if not logins:
            return
        args = [
            "api", "-X", "POST",
            f"repos/{pr.repo}/pulls/{pr.number}/requested_reviewers",
        ]
        for login in logins:
            args += ["-f", f"reviewers[]={login}"]
        self.gh.run(args, check=False)

    def remove_reviewers(self, pr: PR, logins: list[str]) -> None:
        if not logins:
            return
        args = [
            "api", "-X", "DELETE",
            f"repos/{pr.repo}/pulls/{pr.number}/requested_reviewers",
        ]
        for login in logins:
            args += ["-f", f"reviewers[]={login}"]
        self.gh.run(args, check=False)

    def comment(self, pr: PR, body: str) -> None:
        self.gh.run([
            "pr", "comment", str(pr.number), "-R", pr.repo,
            "--body", body + BOT_DISCLAIMER,
        ], check=False)


# ---------------------------------------------------------------------------
# Sweep orchestration
# ---------------------------------------------------------------------------

def source_for(is_bot: bool, can_commit: bool, cfg: Config) -> str:
    """Source classification decision (pure): Bot if a bot authored it, else
    Internal if the author can commit to the target repo, else Community."""
    if is_bot:
        return cfg.source_bot
    return cfg.source_internal if can_commit else cfg.source_community


def classify_source(pr: PR, cfg: Config, collaborators: set[str]) -> str:
    """Classify a PR's Source when the board has none. Pure: `collaborators` is
    the repo's write+ set (Internal iff the author can commit to the repo)."""
    return source_for(pr.is_bot, pr.author in collaborators, cfg)


def collect_prs(gh: Gh, cfg: Config,
                repo_collaborators: Callable[[str], set[str]]) -> list[PR]:
    """All open PRs across cfg.repos, fully populated by the batched query, with
    Source resolved and (for unassigned, non-exempt PRs) committer signal."""
    _progress(f"sweeping {len(cfg.repos)} repo(s) — this typically takes a few minutes…")
    _progress("reading project board status…")
    board = collect_board_status(gh, cfg)
    # Run-scoped cache of PR-independent source data (file history, commit stats)
    # so hot files/commits are fetched once across the whole sweep. `since` is
    # computed once here for stable cache keys.
    signal_cache = pr_signal.SignalCache()
    signal_since = pr_signal.horizon_since(cfg.signal_horizon_days)
    prs: list[PR] = []
    for repo in cfg.repos:
        for pr in collect_open_prs(gh, repo, cfg):
            entry = board.get(pr.key())
            if entry:
                pr.board_status = entry.get("status")
                pr.project_item_id = entry.get("item_id")
                pr.source = entry.get("source") or ""
            # Source is authoritative when set; classify + mark for writing when
            # not (reusing the repo's write+ collaborator set, fetched lazily).
            if not pr.source:
                pr.source = classify_source(pr, cfg, repo_collaborators(repo))
                pr.source_unset = True
            pr.is_bot = (pr.source == cfg.source_bot)

            # Committer signal feeds assignee/reviewer selection — only needed
            # for unassigned PRs that aren't human-draft-exempt or merge-queued.
            human_draft = pr.is_draft and not pr.is_bot
            if not human_draft and not pr.assignees and not pr.in_merge_queue:
                _progress(f"  ranking owner/reviewers for {pr.key()}…")
                collect_committer_signal(gh, pr, cfg, signal_cache, signal_since)
            prs.append(pr)
    _progress(f"collected {len(prs)} open PR(s) across {len(cfg.repos)} repo(s).")
    return prs


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


def _plan_item(pr: PR, decision: Decision) -> dict[str, Any] | None:
    """The self-contained, replayable action list for one PR, or None when
    there is nothing to write."""
    actions: dict[str, Any] = {}
    if decision.add_to_project:
        actions["add_to_project"] = True
    if pr.source_unset and pr.project_item_id:
        actions["set_source"] = pr.source
    if decision.set_status:
        actions["set_status"] = decision.set_status
    if decision.set_assignee:
        actions["set_assignee"] = decision.set_assignee
        actions["request_reviewers"] = list(decision.request_reviewers)
    if decision.remove_reviewers:
        actions["remove_reviewers"] = list(decision.remove_reviewers)
    if decision.comment_kind == "ready":
        actions["comment_kind"] = "ready"
    if not actions:
        return None
    return {
        "pr": pr.key(),
        "repo": pr.repo,
        "number": pr.number,
        "item_id": pr.project_item_id,
        "node_id": pr.node_id,
        **actions,
    }


def run_sweep(gh: Gh, cfg: Config, now: datetime) -> dict[str, Any]:
    state = load_state(cfg.state_file)
    owners_members = list_team_members(gh, cfg.owners_team)
    bot_owners_members = list_team_members(gh, cfg.bot_owners_team)

    # The write+ collaborator set is per-repo, memoized, and shared between source
    # classification (collect_prs) and the extra-reviewer pool (selection below).
    collaborators_cache: dict[str, set[str]] = {}

    def repo_collaborators(repo: str) -> set[str]:
        if repo not in collaborators_cache:
            collaborators_cache[repo] = collect_repo_collaborators(gh, repo)
        return collaborators_cache[repo]

    prs = collect_prs(gh, cfg, repo_collaborators)

    repo_stats: dict[str, dict[str, int]] = {}
    stall_by_key: dict[str, tuple[float, int]] = {}  # pr key -> (stall_wh, stall_days)
    plan: list[dict[str, Any]] = []  # self-contained, replayable action list

    for pr in prs:
        stats = repo_stats.setdefault(pr.repo, {"open": 0, "acted": 0})
        stats["open"] += 1

        entry = pr_state_entry(state, pr.key())

        _select_assignee_reviewers(
            pr, cfg, owners_members, bot_owners_members, repo_collaborators)

        decision = reconcile(pr, cfg)
        if not decision.is_noop() or pr.source_unset:
            stats["acted"] += 1

        item = _plan_item(pr, decision)
        if item is not None:
            plan.append(item)

        # Fold the plan's pending actions into the PR in-memory, then track
        # movement on the resulting state for the stall clock and report.
        apply_pending_to_pr(pr, decision)
        if pr.source != cfg.source_internal and not (pr.is_draft and not pr.is_bot):
            new_stall, stall_wh, stall_days = compute_stall(
                pr, entry.get("stall", {}), now, cfg.tzinfo())
            entry["stall"] = new_stall
            stall_by_key[pr.key()] = (stall_wh, stall_days)

    # Assignee-grouped report, built from the post-plan effective PRs.
    recipients = build_report(prs, cfg, stall_by_key)
    report = render_report(recipients, cfg)

    # Daily cadence: the report is surfaced at most once per interval. `report_due`
    # gates the exit code; `last_report_at` advances only on a real (apply) sweep.
    last_report = parse_iso(state.get("last_report_at"))
    report_due = bool(report) and (
        last_report is None
        or (now - last_report) >= timedelta(hours=cfg.report_interval_hours))
    if report_due:
        state["last_report_at"] = now.isoformat()

    summary: dict[str, Any] = {
        "generated_at": now.isoformat(),
        "repos": repo_stats,
        "report": report,
        "report_due": report_due,
        "plan": plan,
        # Post-sweep state (stall clocks + last_report_at). Persisted by the
        # apply step (apply_decisions), never by run_sweep itself, so planning
        # is pure: it reads the on-disk state but writes none.
        "state": state,
    }

    # Planning always writes the plan so an `--apply` pass can replay it.
    save_plan(cfg.plan_file, summary)
    return summary


def apply_plan(gh: Gh, cfg: Config, plan: list[dict[str, Any]]) -> int:
    """Execute a previously computed plan (each item is self-contained). Reuses
    the same idempotent Applier the one-shot path uses. Returns item count."""
    applier = Applier(gh, cfg)
    for item in plan:
        pr = PR(
            repo=item["repo"],
            number=int(item["number"]),
            project_item_id=item.get("item_id"),
            node_id=item.get("node_id") or "",
        )
        if item.get("add_to_project"):
            applier.add_to_project(pr)
        if item.get("set_source"):
            applier.set_source(pr, item["set_source"])
        if item.get("set_status"):
            applier.set_status(pr, item["set_status"])
        if item.get("set_assignee"):
            applier.set_assignee(pr, item["set_assignee"])
            applier.request_reviewers(pr, item.get("request_reviewers") or [])
        if item.get("remove_reviewers"):
            applier.remove_reviewers(pr, item["remove_reviewers"])
        if item.get("comment_kind") == "ready":
            applier.comment(pr, READY_COMMENT)
    return len(plan)


def apply_decisions(gh: Gh, cfg: Config, doc: dict[str, Any]) -> int:
    """The single apply step shared by every apply path (one-shot and replay):
    execute the plan's GitHub writes, then persist the post-sweep state so the
    stall clocks and `last_report_at` advance on any apply. Returns
    the number of plan items executed."""
    n = apply_plan(gh, cfg, doc.get("plan") or [])
    state = doc.get("state")
    if isinstance(state, dict):
        save_state(cfg.state_file, state)
    return n


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=(
            "Reconcile open shader-slang PRs on the 'Slang PR Tracking' board. "
            "All configuration lives in the constants at the top of this file. "
            "Modes: '--maintainer LOGIN' plans (dry run, writes the plan file); "
            "'--apply' replays the saved plan; both together is a one-shot sweep."
        )
    )
    p.add_argument("--maintainer", default="",
                   help="Login of the current Slang Maintainer (the fallback assignee). "
                        "Required to compute a plan; not needed to --apply a saved plan.")
    p.add_argument("--apply", action="store_true",
                   help="Perform GitHub writes. Without --maintainer, replays the saved "
                        "plan file; with --maintainer, computes and applies in one shot.")
    p.add_argument("--recipient-map", default="", metavar="PATH",
                   help="Path to a flat JSON object mapping GitHub login -> destination "
                        "user ID (e.g. Discord). Mapped logins render as <@id> mentions in "
                        "the report; unmapped logins (or no file) render as inert `backticks`. "
                        "Applied when computing a plan (with --maintainer); a replayed plan "
                        "already has its report baked in.")
    return p.parse_args(argv)


def _print_summary(summary: dict[str, Any], cfg: Config, applying: bool) -> None:
    mode = "ONE-SHOT" if applying else "PLAN (dry run)"
    print(f"[{mode}] sweep @ {summary['generated_at']}")
    for repo, st in sorted(summary["repos"].items()):
        print(f"  {repo}: {st['open']} open, {st['acted']} actioned")
    plan = summary["plan"]
    def _count(key: str) -> int:
        return sum(1 for item in plan if item.get(key))
    print(f"  transitions={_count('set_status')} "
          f"assignments={_count('set_assignee')} "
          f"sources_set={_count('set_source')} "
          f"added_to_board={_count('add_to_project')}")
    print(f"  plan ({len(plan)} items) written to {cfg.plan_file}")
    report = summary.get("report") or ""
    if report:
        due = " (due — surface today)" if summary.get("report_due") else " (not due yet)"
        print(f"\n--- report{due} ---\n")
        print(report)
    else:
        print("\n(no report — nothing needs attention this sweep)")


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    maintainer = args.maintainer.strip().lstrip("@")

    gh = Gh(find_gh())
    gh.preflight()

    # Replay-apply: --apply with no maintainer -> apply the saved plan as-is.
    # This is the "apply half"; one-shot below runs the same apply step on a
    # freshly computed plan, so one-shot == plan + replay-apply.
    if args.apply and not maintainer:
        cfg = Config(apply=True)
        doc = load_plan(cfg.plan_file)
        if doc is None:
            raise SystemExit(
                f"No saved plan at {cfg.plan_file}. Run a plan pass first "
                "(`--maintainer LOGIN`), or pass --maintainer to compute + apply in one shot."
            )
        n = apply_decisions(gh, cfg, doc)
        print(f"[APPLY] executed {n} planned items from {cfg.plan_file} "
              f"(planned {doc.get('generated_at')})")
        return 0

    # Plan or one-shot: both require a maintainer (the fallback assignee).
    if not maintainer:
        raise SystemExit(
            "Pass --maintainer <login> (the current Slang Maintainer) to compute a "
            "plan, or --apply to replay the saved plan."
        )

    cfg = Config(maintainer=maintainer, apply=args.apply)
    if args.recipient_map:
        cfg.recipient_map = load_recipient_map(args.recipient_map)

    # Default scope: every non-archived repo in the org (DEFAULT_REPOS is empty).
    if not cfg.repos:
        cfg.repos = list_org_repos(gh, cfg.org)
        if not cfg.repos:
            raise SystemExit(f"No repositories found in org {cfg.org!r}.")

    now = datetime.now(timezone.utc)
    summary = run_sweep(gh, cfg, now)        # the "plan half"
    _print_summary(summary, cfg, applying=args.apply)

    if args.apply:                           # one-shot = plan + apply, same step
        n = apply_decisions(gh, cfg, summary)
        print(f"\n[APPLY] executed {n} planned items.")

    # Exit 10 signals "the daily report is due to be surfaced" so a scheduler can
    # decide whether to wake the agent; 0 means nothing to surface this sweep.
    return 10 if summary.get("report_due") else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
