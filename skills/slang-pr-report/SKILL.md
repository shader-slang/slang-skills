---
name: slang-pr-report
license: MIT
description: "Surface the open shader-slang PRs needing human attention with a bundled gh-only Python script (scripts/pr_report.py): an assignee-grouped escalation report computed entirely from live GitHub state (read-only; no writes; optional Discord/Slack mentions). Use for PR triage, the reviewer-attention report, stale-PR follow-up, or a scheduled report run."
provides: []
argument-hint: "[--recipient-map PATH]"
allowed-tools: Bash Read Grep Glob
---

# Slang PR Report

A deterministic, read-only engine that surfaces the open PRs needing human
attention as an assignee-grouped escalation report. The script does
all the work; the agent only surfaces the emitted report.

> All GitHub access goes through `gh` and is **read-only** — the script never
> writes to GitHub. It depends only on an authenticated `gh` and the Python
> stdlib (no MCP, no container assumptions).

## Quick start

Everything except the flag (org, source/stage names, bot identities, thresholds)
is a constant at the top of `pr_report.py`; edit it there if it ever moves.

```bash
# Render the assignee-grouped escalation report with notifying mentions.
python3 scripts/pr_report.py --recipient-map <path>

# No mapping file (absent / testing): every login renders as inert `backticks`
# so nobody is pinged. Otherwise identical.
python3 scripts/pr_report.py
```

The report reads only live GitHub state and keeps **no local state** — each
PR's staleness is derived fresh from event timestamps every run. It exits `10`
when there is a report to surface (`0` when nothing needs attention). The caller
decides how often to run it — the script does not throttle.

**This is a long-running process — do not kill it.** An org-wide run takes a few
minutes (≈5-6s per repo page). It streams progress to **stderr** (a start
banner, a line per repo page) so it is never silent; **stdout** carries only the
summary + report. Run it with a generous timeout and treat the stderr heartbeats
as liveness.

Under WSL the script prefers `gh.exe` and stops if `gh` is missing rather than
falling back to a different toolchain.

## What the script does

1. **Collect** (batched `gh` GraphQL): **one paginated query per repo**
   (`DEFAULT_PR_PAGE_SIZE`, default 25) returns every open PR with everything
   needed in a single shot — core fields, author type, assignees, requested
   reviewers, CI (`statusCheckRollup` → `ci_state` + `coverage_passed`, plus
   per-check timestamps), the head-commit date, reviews
   (→ `last_review_at`/`change_requested`), comments, the ready-for-review
   event, and `mergeQueueEntry`.
2. **Synthesize** (pure, in-memory): classify each PR's source, derive its
   lifecycle stage from the collected signals, compute each PR's stall from its
   event timestamps (see below), and build the assignee-grouped report from the
   per-source ladders.
3. **Emit**: a human summary + the assignee-grouped report on stdout. Exit code
   `10` means "there is a report to surface"; `0` means nothing needs attention.
   Nothing is written to disk.

### Lifecycle stage (derived from live signals)

Each PR's stage is derived from CI / reviews / draft / merge-queue signals (the
`derive_stage` function). Three stages are observable — `Revising` / `Todo`
(ready for a human) / `Done` — derived **per source** ("different fingerprints"):

- **Contributor/Community:** `Revising` while a draft, while changes are
  requested, or while CI is failing/not-yet-passed; promoted to `Todo` only once
  it is not a draft and CI has passed.
- **Bot:** promoted to `Todo` whenever its gate holds (always, unless a coverage
  check is configured and failing); drafts are **not** exempt.
- **Done:** merged/closed or in the merge queue.

The stage gates the "awaiting review" reason. Staleness itself is **event-
sourced** (see "Stall clock" below): the clock is anchored to the most recent
real, logged movement event, so a new commit, CI settling/being re-triggered,
a review, a ready-for-review, or a non-author-assignee comment each moves it.
A maintainer engaging (e.g. pinging the author) therefore resets the clock
rather than leaving the PR to keep resurfacing; assignee comments are matched by
unordered set membership (GitHub assignees are co-equal with no stable
"primary"), and the PR author is excluded even when also assigned, so an author
comment never resets the clock.

## PR sources and per-source behavior

Every PR is classified into a **source** — **`Internal` / `Community` / `Bot`** —
from live state: `Bot` if the author is a bot (`DEFAULT_BOT_AUTHORS`), else
`Internal` if the author can commit to the target repo (a write+ collaborator),
else `Community`. When the repo's collaborator set **can't be read** (the token
lacks push access there), a non-bot PR is classified **`Unknown`** rather than
silently assumed `Community` — we genuinely can't tell Internal from Community.
Behavior differs by source:

| Behavior | **Internal** | **Community** | **Bot** | **Unknown** |
|---|---|---|---|---|
| Report predicate ladder | **none** (excluded) | `COMMUNITY_LADDER` (incl. `needs CI approval`, `changes requested`) | `BOT_LADDER` (no CI-approval/changes rungs) | `COMMUNITY_LADDER` (surfaced, flagged `❓`) |
| Drafts | excluded (author "not ready") | excluded (author "not ready") | **not excluded** (bot drafts still surface) | excluded (treated like a contributor) |

Internal PRs are self-managed by their author and are not surfaced. Community and
Bot PRs are surfaced when stalled. `Unknown` PRs are surfaced like Community but
rendered with the `❓` icon, so a missing-access gap is visible rather than
silently mislabeled. A PR's reviewers in the "awaiting review"
reason are the currently-requested reviewers who can actually approve —
auto-assigned non-approvers (`DEFAULT_IGNORED_REVIEWERS`) and bots are excluded.

## Notification model: assignee-grouped report

The report is **grouped by assignee** (the caller decides how often to run and
surface it). Each section is one assignee's queue. GitHub assignees are
co-equal, so a PR with **multiple human assignees** appears in **each** of their
sections (every responsible person sees it in their own queue, and each is
pinged when a recipient map is supplied). PRs with **no human assignee** are
grouped under **Unassigned**, listed first — the report does not guess an owner
(assignment happens elsewhere). An item that passes the escalate rung is marked
overdue **in place** with the `⬆️` marker. Example:

```
## Slang PR Escalation Report

- **Unassigned**:
  - ⬆️ 🌐 [slang#334](…/pull/334) — idle for 1 days — needs CI approval
  - 🤖 [slang#9001](…/pull/9001) — idle for 3 days — awaiting review from: <@222>
- **`alice`**:
  - 🌐 [slang#777](…/pull/777) — idle for 9 days — changes requested, check if author is still active / needs help 👥
- **`bob`**:
  - 🌐 [slang#777](…/pull/777) — idle for 9 days — changes requested, check if author is still active / needs help 👥
```
- Every reason leads with the same **`idle for N days`** age phrase, then the specific condition (if any), so the day count always lands in the same spot for scanning.
- The report is titled **"Slang PR Escalation Report"**.
- **Unassigned** (PRs with no human assignee, incl. bot-only like `Copilot`) is listed first; named assignees follow, sorted. A PR with several human assignees is repeated under each. Escalations are marked identically in every group.
- **Within each group**, items are ordered Community (`🌐`), then Unknown (`❓`), then Bot (`🤖`), and within each source escalated (`⬆️`) before not-escalated.
- `⬆️` marks an item **escalated/overdue** past the second (escalate) rung.
- `👥` (tagged at the **end** of the line, after the reason) marks an item **shared** — surfaced under more than one human assignee (it appears in each of their sections), so a viewer knows they are not the sole owner.
- `🌐` Community, `🤖` Bot, `❓` source unknown (the repo's collaborators couldn't be read, so Internal-vs-Community is undetermined). Internal PRs and human drafts are excluded. PR refs are clickable links.
- **Mentions** (`--recipient-map`): a login present in the supplied map renders as a `<@id>` mention that pings on Discord (the format also fits Slack); every other login renders as inert `` `login` ``. **The invoker must pass `--recipient-map PATH`** to get pings. See the schema below.

### Stall clock (event-sourced, stateless)
`last_moved_at(pr)` is the **max** of the real, logged event timestamps: the
head-commit date, CI activity (`ci_activity_at` — see below), the last review,
the ready-for-review event, and the latest non-author-assignee comment. Stall is
the working-hours (weekends excluded) since then, computed fresh each run — the
script keeps no state file and never uses GitHub's noisy `updatedAt`.

`ci_activity_at` is itself the max of every per-check timestamp — `CheckRun`
`startedAt`/`completedAt`, its `checkSuite` `createdAt`/`updatedAt`, the
`workflowRun` `createdAt`, and legacy `StatusContext` `createdAt`. That captures
CI settling (pass/fail) via its completion time **and** a queued/awaiting-
approval or re-run/nag via the check-suite's creation time (the logged trigger),
which is deliberately decoupled from the commit — CI can be nagged to run days
later. Timestamps are never assumed to be ordered (GitHub returns non-monotonic
values), so everything is reduced with `max`.

### Per-source predicate ladders (the single source of truth)
Each PR's **reason** is the first matching predicate in its source's ladder; its
**stall** (see above) selects the rung: it surfaces under each of its human
assignees (or Unassigned) once `stall >= assignee_after`, and is marked overdue
in place (`⬆️`) once `stall >= escalate_after`. Defined in `COMMUNITY_LADDER` /
`BOT_LADDER` in [scripts/pr_report.py](scripts/pr_report.py):

Each rung's reason renders as `idle for N days — <condition>` (the `idle`
catch-all is just `idle for N days`):

- **Community:** `needs CI approval` (surface 0h / escalate 24h) → `changes requested, check if author is still active / needs help` (1wk / 2wk) → `awaiting review from: …` (24h / 48h) → `CI failing, needs fixes` (24h / 48h) → `idle` (24h / 48h).
- **Bot:** `awaiting review from: …` (48h / 1wk) → `CI failing, needs fixes` (48h / 1wk) → `idle` (48h / 1wk). No `needs CI approval` or `changes requested` rung.

Edit the ladders to retune timeouts/audiences. The report is a **current-state**
list: an item keeps appearing until the PR moves (a newer event timestamp).
"awaiting review" only fires when the PR has
reached the derived `Todo` stage and a real (approve-capable) reviewer is
requested.

### Surfacing the report (agent's job, method-agnostic)

The script only **emits** the report (stdout + exit code `10` when due). This
skill does NOT prescribe delivery — the agent uses whatever channel is available
at runtime. To make the report **notify** people (e.g. on Discord), pass
`--recipient-map PATH`.

### Recipient map (`--recipient-map`)

A flat JSON object mapping **GitHub login -> destination user ID** (matched
case-insensitively):

```json
{ "alice": "123456789012345678", "bob": "987654321098765432" }
```

- A login in the map renders as `<@id>` (pings on Discord; the shape also fits
  Slack). Any login **not** in the map (or when no file is passed) renders as
  inert `` `login` `` so it can never notify the wrong person.
- The path is supplied by the invoker **each run**; there is no auto-discovery.
- The mapping affects the **report text only**. All routing, stall state, and bot
  detection stay on GitHub logins.

## Agent's residual job

1. Run `scripts/pr_report.py --recipient-map <path>`.
2. When the exit code is `10`, surface the report to its recipients
   (method-agnostic).

Everything else is the script's.

## Configuration (top-of-file constants)

The only flag is `--recipient-map PATH` (the report mention table; see above).
Everything else is a constant near the top of `pr_report.py` — edit it there if
it moves:

| Constant | Value | Notes |
|------|---------|-------|
| `DEFAULT_ORG` | `shader-slang` | org scanned when `DEFAULT_REPOS` is empty |
| `DEFAULT_REPOS` | _(empty)_ | comma-separated `owner/name` subset; empty -> every non-archived repo in the org |
| `DEFAULT_STATUS_*` | `Revising`/`Todo`/`Done` | internal lifecycle-stage labels (derived; see `derive_stage`) |
| `DEFAULT_SOURCE_*` | `Internal`/`Community`/`Bot`/`Unknown` | source-classification labels (`Unknown` when the collaborator set can't be read) |
| `DEFAULT_COVERAGE_CHECK` | _(empty)_ | optional CI check gating a bot PR's promotion to ready; while empty, bot PRs are treated as ready |
| `DEFAULT_BOT_AUTHORS` | `nv-slang-bot,slang-coworker-nanoclaw,Copilot,copilot-swe-agent` | bot logins matched by name (GitHub's `is_bot`/`__typename` is also honored for authors). `Copilot` is the coding-agent's assignee/reviewer login — GitHub types it as a `User` there, so it must be name-matched; bot-only-assigned PRs route to the Unassigned group |
| `DEFAULT_IGNORED_REVIEWERS` | `bmillsNV` | auto-assigned reviewers that can't approve; ignored when checking reviewer coverage |
| `DEFAULT_WORKDAY_TZ` | `America/Los_Angeles` | timezone for the workday model (stall clock skips weekends) |
| `DEFAULT_PR_PAGE_SIZE` | `25` | PRs per batched GraphQL page (capped by server timeout: n=50 can return HTTP 504, n=25 resolves in ~5-6s) |

The report's delivery channel is intentionally not configured here — the script
emits the report and the agent decides where it goes.

## Prerequisites

- An authenticated `gh`: a usable token via `gh auth login`, `GH_TOKEN`, or a
  token-injecting proxy (e.g. onecli). The script preflights by reading the
  target resource rather than `gh auth status` — a direct yes/no on access that
  works with wire-injected tokens and is token-type agnostic (user PAT or GitHub
  App token). For a repo subset it probes `repos/<owner/name>` (REST); for a
  whole-org scan it probes the org via **GraphQL** (`organization(login)`), not
  REST `orgs/<org>`, because some token proxies (e.g. the OneCLI gateway) don't
  route the REST `/orgs/*` path even when the token can read org data. It fails
  loudly if the probe can't be read.
- **repo read** for the PR/CI/review/timeline GraphQL query (classic `repo`
  scope, or a GitHub App with Pull requests + Contents + Checks read; covers
  private repos). CI timing also reads check-suite/workflow-run metadata.
- **repo push access** to list the write+ collaborator pool
  (`repos/{repo}/collaborators`) — used to classify a PR's source (Internal iff
  the author can commit). If that call fails for a repo (no push access), its
  non-bot PRs classify as `Unknown` (`❓`) rather than `Community`; the report
  still runs.
- **No writes** are performed, and **no GitHub Projects scope** is required.
- A local clone is NOT required (all access goes through `gh api`).

## Scheduling

Any scheduler works (cron or CI). Run `pr_report.py --recipient-map <path>` on
whatever cadence you want — the script does not throttle, so the caller owns how
often the report is produced and surfaced (e.g. a daily cron). Exit code `10`
means "there is a report to surface" (`0` means nothing needs attention), which
a scheduler can use to decide whether to wake the agent.

## Tests

```bash
python3 scripts/test_pr_report.py
```

Covers the pure decision functions with no live `gh` calls: bot + source
classification, the per-source lifecycle-stage derivation, the predicate ladders
+ assignee-grouped report routing (including the Unassigned group), the
event-sourced stall clock (`last_moved_at` / `ci_activity_at_from_rollup`,
including the queued/awaiting-approval and non-monotonic-timestamp cases), and
CI summarization.
