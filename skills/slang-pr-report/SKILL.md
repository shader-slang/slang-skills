---
name: slang-pr-report
license: MIT
description: "Surface the open shader-slang PRs needing human attention with a bundled gh-only Python script (scripts/pr_report.py): an assignee-grouped escalation report computed entirely from live GitHub state (read-only; no writes; optional Discord/Slack mentions). Use for PR triage, the reviewer-attention report, stale-PR follow-up, or a scheduled report run."
provides: []
argument-hint: "[--recipient-map PATH]"
allowed-tools: Bash Read Grep Glob
---

# Slang PR Report

A deterministic engine that surfaces the open PRs needing human attention as an
assignee-grouped escalation report. The script does all the work; the agent only
surfaces the emitted report.

> All GitHub access goes through `gh` and is **read-only** (never writes). Depends
> only on an authenticated `gh` and the Python stdlib (no MCP, no container).

## Quick start

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

**Long-running — do not kill it.** An org-wide run takes a few minutes; progress
streams to **stderr** (a line per repo page) while **stdout** carries only the
summary + report, so give it a generous timeout. Under WSL it prefers `gh.exe`
and stops if `gh` is missing rather than falling back to a different toolchain.

## What the script does

1. **Collect** (batched `gh` GraphQL): one paginated query per repo
   (`DEFAULT_PR_PAGE_SIZE`, default 25) returns every open PR with everything in
   one shot — core fields, author type, assignees, requested reviewers, CI
   rollup (with per-check timestamps), head-commit date, reviews, comments, the
   ready-for-review event, and `mergeQueueEntry`.
2. **Synthesize** (pure, in-memory): classify each PR's source, derive its
   lifecycle stage, compute its stall from the event timestamps (see below), and
   build the assignee-grouped report from the per-source ladders.
3. **Emit**: a human summary + the assignee-grouped report on stdout; exit `10`
   if there is a report to surface, else `0`.

### Lifecycle stage (derived from live signals)

Each PR's stage is derived from CI / reviews / draft / merge-queue signals (the
`derive_stage` function). Three stages are observable — `Revising` / `Todo`
(ready for a human) / `Done` — derived **per source**:

- **Contributor/Community:** `Revising` while a draft, while changes are
  requested, or while CI is failing/not-yet-passed; promoted to `Todo` only once
  it is not a draft and CI has passed.
- **Bot:** promoted to `Todo` whenever its gate holds (always, unless a coverage
  check is configured and failing); drafts are **not** exempt.
- **Done:** merged/closed or in the merge queue.

The stage gates the "awaiting review" reason. Staleness is separate and
event-sourced (see [Stall clock](#stall-clock-event-sourced-stateless)); note
that a comment by a **non-author assignee** counts as movement — so a maintainer
pinging the author resets the clock — but the PR author's own comments never do.

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

Internal PRs are self-managed and not surfaced; Community/Bot/Unknown surface
when stalled (`Unknown` flagged `❓` so a missing-access gap is visible, not
silently mislabeled). In the "awaiting review" reason, reviewers are the
currently-requested ones who can actually approve — auto-assigned non-approvers
(`DEFAULT_IGNORED_REVIEWERS`) and bots are excluded.

## Notification model: assignee-grouped report

The report is **grouped by assignee** — each section is one assignee's queue.
GitHub assignees are co-equal, so a PR with **multiple human assignees** appears
under **each** of them (and pings each when a recipient map is supplied). PRs
with **no human assignee** go under **Unassigned** (listed first; the report
doesn't guess an owner). Example:

```
## Slang PR Escalation Report

- **Unassigned**:
  - ⬆️ 🌐 [slang#334](…/pull/334) — idle for 1 work days — needs CI approval
  - 🤖 [slang#9001](…/pull/9001) — idle for 3 work days — awaiting review from: <@222>
- **`alice`**:
  - 🌐 [slang#777](…/pull/777) — idle for 9 work days — changes requested, check if author is still active / needs help 👥
- **`bob`**:
  - 🌐 [slang#777](…/pull/777) — idle for 9 work days — changes requested, check if author is still active / needs help 👥
```
- Every reason leads with the same **`idle for N work days`** age phrase, then the specific condition (if any), so the count always lands in the same spot for scanning.
- **Unassigned** (PRs with no human assignee, incl. bot-only like `Copilot`) is listed first; named assignees follow, sorted. A PR with several human assignees is repeated under each (marked `👥`, tagged at the **end** of the line).
- **Within each group**, items are ordered Community (`🌐`), then Unknown (`❓`), then Bot (`🤖`), and within each source escalated (`⬆️`) before not-escalated.
- Icons: `⬆️` escalated/overdue (past the escalate rung), `👥` shared (multiple human assignees), `🌐` Community, `🤖` Bot, `❓` source unknown. Internal PRs and human drafts are excluded; PR refs are clickable links.
- **Mentions**: with `--recipient-map`, mapped logins render as pinging `<@id>` mentions; everyone else stays inert `` `login` `` — see [Recipient map](#recipient-map---recipient-map).

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

Surface/escalate thresholds are in **working hours** (weekends skipped), and the
reason shows whole **work days** (`working_hours ÷ 24`) — so the number you read
is on the same footing as the thresholds, not calendar time.

### Per-source predicate ladders (the single source of truth)
Each PR's **reason** is the first matching predicate in its source's ladder; its
**stall** (see above) selects the rung: it surfaces under each of its human
assignees (or Unassigned) once `stall >= assignee_after`, and is marked overdue
in place (`⬆️`) once `stall >= escalate_after`. Defined in `COMMUNITY_LADDER` /
`BOT_LADDER` in [scripts/pr_report.py](scripts/pr_report.py):

Each rung's reason renders as `idle for N work days — <condition>` (the `idle`
catch-all is just `idle for N work days`):

- **Community:** `needs CI approval` (surface 0h / escalate 24h) → `changes requested, check if author is still active / needs help` (1wk / 2wk) → `awaiting review from: …` (24h / 48h) → `CI failing, needs fixes` (24h / 48h) → `needs reviewer` (24h / 48h) → `idle` (24h / 48h).
- **Bot:** `awaiting review from: …` (48h / 1wk) → `CI failing, needs fixes` (48h / 1wk) → `needs reviewer` (48h / 1wk) → `idle` (48h / 1wk). No `needs CI approval` or `changes requested` rung.

The `needs reviewer` rung (a hint to the assignee to get one assigned) fires when a
surfaced PR has no approve-capable reviewer requested (auto-assigned non-approvers
in `DEFAULT_IGNORED_REVIEWERS` and bots don't count) and isn't already caught by an
earlier rung — so a bare `idle` now only means a reviewer *is* requested but the PR
still hasn't moved.

Edit the ladders to retune timeouts/audiences. The report is a **current-state**
list: an item keeps appearing until the PR moves (a newer event timestamp).
"awaiting review" only fires when the PR has
reached the derived `Todo` stage and a real (approve-capable) reviewer is
requested.

### Agent's job

The script does everything except delivery: run
`scripts/pr_report.py --recipient-map <path>`, and when the exit code is `10`
surface the emitted report to its recipients through whatever channel is
available (this skill is delivery-method-agnostic). Everything else is the
script's.

### Recipient map (`--recipient-map`)

Delivery is agnostic, but to **notify** people (e.g. on Discord/Slack) pass a
flat JSON object mapping **GitHub login -> destination user ID** (matched
case-insensitively):

```json
{ "alice": "123456789012345678", "bob": "987654321098765432" }
```

A mapped login renders as `<@id>` (pings on Discord; the shape also fits Slack);
any unmapped login (or no file) renders as inert `` `login` `` so it can never
notify the wrong person. The path is supplied by the invoker **each run** (no
auto-discovery) and affects the **report text only** — routing and bot detection
stay on GitHub logins.

## Configuration (top-of-file constants)

The only flag is `--recipient-map PATH`; everything else is a constant near the
top of `pr_report.py`:

| Constant | Value | Notes |
|------|---------|-------|
| `DEFAULT_ORG` | `shader-slang` | org scanned when `DEFAULT_REPOS` is empty |
| `DEFAULT_REPOS` | _(empty)_ | comma-separated `owner/name` subset; empty -> every non-archived repo in the org |
| `DEFAULT_STATUS_*` | `Revising`/`Todo`/`Done` | internal lifecycle-stage labels (derived; see `derive_stage`) |
| `DEFAULT_SOURCE_*` | `Internal`/`Community`/`Bot`/`Unknown` | source-classification labels (`Unknown` when the collaborator set can't be read) |
| `DEFAULT_COVERAGE_CHECK` | _(empty)_ | optional CI check gating a bot PR's promotion to ready; while empty, bot PRs are treated as ready |
| `DEFAULT_BOT_AUTHORS` | `nv-slang-bot,slang-coworker-nanoclaw,Copilot,copilot-swe-agent` | bot logins matched by name (plus GitHub's `is_bot`). `Copilot` is typed as a `User` on reviews/assignees, so it must be name-matched; bot-only-assigned PRs go to Unassigned |
| `DEFAULT_IGNORED_REVIEWERS` | `bmillsNV` | auto-assigned reviewers that can't approve; ignored when checking reviewer coverage |
| `DEFAULT_WORKDAY_TZ` | `America/Los_Angeles` | timezone for the workday model (stall clock skips weekends) |
| `DEFAULT_PR_PAGE_SIZE` | `25` | PRs per batched GraphQL page (capped by server timeout: n=50 can 504, n=25 resolves in ~5-6s). A failed page is retried with a shrinking size; if it still fails, that one repo is skipped (warned on stderr) rather than aborting the scan |

## Prerequisites

- An authenticated `gh`: a token via `gh auth login`, `GH_TOKEN`, or a
  token-injecting proxy (e.g. onecli). Preflight reads the target resource (not
  `gh auth status`, which misses wire-injected tokens) and is token-type
  agnostic: a repo subset probes `repos/<owner/name>` (REST); a whole-org scan
  probes the org via **GraphQL** (`organization(login)`), not REST `orgs/<org>`
  — some proxies (e.g. the OneCLI gateway) don't route `/orgs/*`. Fails loudly
  if the probe can't be read.
- **repo read** for the PR/CI/review/timeline GraphQL query (classic `repo`
  scope, or a GitHub App with Pull requests + Contents + Checks read; covers
  private repos). CI timing also reads check-suite/workflow-run metadata.
- **repo push access** to read `repos/{repo}/collaborators` (classifies source —
  Internal iff the author can commit). If it fails for a repo, that repo's
  non-bot PRs classify as `Unknown` (`❓`) and the report still runs.
- No writes, no GitHub Projects scope, and no local clone required (all via `gh api`).

## Scheduling

Any scheduler works (cron or CI); the script does not throttle, so the caller
owns cadence. A scheduler can gate on the exit code (`10` = report to surface,
`0` = nothing needed) to decide whether to wake the agent.

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
