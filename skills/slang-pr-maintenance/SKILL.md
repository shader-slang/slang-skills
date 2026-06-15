---
name: slang-pr-maintenance
license: MIT
description: "Reconcile open shader-slang PRs toward their correct GitHub ProjectsV2 board state with a bundled gh-only Python script (scripts/pr_sweep.py): classify each PR, advance its board Status, assign owners + reviewers, and emit a once-daily report of items needing attention (optionally with Discord mentions). Use for PR-board maintenance, triaging the PR queue, reviewer assignment, stale-PR follow-up, or a scheduled PR sweep."
provides: []
argument-hint: "--maintainer LOGIN [--apply] [--recipient-map PATH]"
allowed-tools: Bash Read Grep Glob
---

# Slang PR Maintenance Sweep

Drives every open PR one step toward its correct board state and emits a
once-daily, assignee-grouped report of items needing human attention. The
script is the deterministic engine; the agent only surfaces the report and
resolves a few flagged judgment calls.

> All GitHub work goes through `gh` (reads + writes). There is no dependency on
> MCP, Discord, or a nanoclaw container — the script runs anywhere `gh` is
> authenticated, including against a local checkout.

## Quick start

Everything except the flags (org, board id, teams, status/source names,
thresholds) is a constant at the top of `pr_sweep.py`; edit it there if it ever
moves. The board id (`PVT_kwDOAb2kZs4BSJKy`, "Slang PR Tracking") is hard-coded.

**Normal skill invocation — all three flags:** compute a fresh plan, apply it,
and render notifying mentions. This is what a scheduled run should use.

```bash
python3 scripts/pr_sweep.py --maintainer <login> --apply --recipient-map <path>
```

`--maintainer LOGIN` is the current Slang Maintainer (rotates every two weeks —
no default). The other two flags may each be dropped, but only for a specific
reason:

```bash
# DRY RUN / debugging — omit --apply: compute, print the summary + report, and
# write a replayable plan to ./.pr-sweep-plan.json. No GitHub writes.
python3 scripts/pr_sweep.py --maintainer <login> --recipient-map <path>

# REPLAY — omit --maintainer (keep --apply): apply the last saved plan as-is, no
# recompute. (--recipient-map has no effect here; the plan's report is baked in.)
python3 scripts/pr_sweep.py --apply

# No mapping file (absent / corrupt / testing) — omit --recipient-map: the report
# renders every login as inert `backticks`, so nobody is pinged. Otherwise normal.
python3 scripts/pr_sweep.py --maintainer <login> --apply
```

The plan/apply split lets a maintainer eyeball (or diff) `./.pr-sweep-plan.json`
before anything is written — especially useful for the large first run. A saved
plan can go stale; idempotency means a later one-shot self-corrects any drift.

**One-shot is literally plan + apply.** Planning (`run_sweep`) is side-effect-free
and embeds the post-sweep `state` (stall clocks + `last_report_at`) in the plan
file; a single apply step performs the GitHub writes and persists that state. So
one-shot and plan-then-replay leave identical on-disk state — any `--apply`
advances the state, and only plan-only writes nothing but the plan.

**This is a long-running process — do not kill it.** An org-wide sweep takes a
few minutes (≈5-6s per repo page, plus a one-time owner-ranking query per
unassigned PR on a backlog run). It streams progress to **stderr** — a start
banner, a line per repo page, and a line per PR it ranks — so it is never
silent; **stdout** carries only the summary + report. Run it with a generous
timeout and treat the stderr heartbeats as liveness: **do not kill the process
for apparent inactivity** — wait for it to exit (`0` = nothing to surface,
`10` = the daily report is due).

Under WSL the script prefers `gh.exe` and stops if `gh` is missing rather than
falling back to a different toolchain.

## What the script does

1. **Collect** (batched `gh` GraphQL): **one paginated query per repo**
   (`DEFAULT_PR_PAGE_SIZE`, default 25) returns every open PR with everything the
   sweep needs in a single shot — core fields, author type, assignees,
   requested reviewers, CI (`statusCheckRollup` contexts → `ci_state` +
   `coverage_passed`), reviews (→ `last_review_at`/`change_requested`),
   `mergeQueueEntry`, linked-issue assignees, and changed files (for signal).
   Plus the board `Status` + `Source` per PR (a separate ProjectsV2 query). This
   replaces the old per-PR REST fan-out (check-runs / reviews / merge-queue /
   linked-issues / files), so `gh` spawns scale with repos+pages, not open PRs.
2. **Synthesize** (pure, in-memory): resolve each PR's `Source` (classify when
   the board has none), compute the single board transition it warrants, pick
   the source-appropriate owner + reviewers when needed, update each PR's stall
   clock, and build the assignee-grouped **report** from the per-source ladders.
   Emit a self-contained **plan** (`./.pr-sweep-plan.json`).
3. **Act** (`--apply`): replay the plan — set `Source` (when newly classified),
   set `Status`, set assignee, request reviewers, post PR comments — each
   idempotent (never repeats an action whose effect is already present) — then
   persist the plan's `state` (stall clocks + `last_report_at`).
4. **Emit**: a human summary + the assignee-grouped report on stdout, and the
   full machine-readable plan/summary at `./.pr-sweep-plan.json`. Exit code `10`
   means "the daily report is due to surface"; `0` means nothing to surface.

## State machine (board `Status` field)

`Revising -> Todo -> In Progress -> Done`

- **Revising** — waiting on CI, a bot, or a bot reviewer, before any human
  involvement.
- **Todo** — ready for a human; assignee set. This + the board view IS the
  reviewer's "needs review" signal (no message is sent for the routine case).
- **In Progress** — human-set when a reviewer starts. The script never sets it.
- **Done** — merged or closed (usually board automation; ensured here).

## PR sources (board `Source` field) and per-source behavior

Every PR carries a board **`Source`** single-select — **`Internal` / `Community`
/ `Bot`** — which the sweep **reads** (authoritative when set) and **classifies +
sets when empty**: `Bot` if the author is a bot (`--bot-authors`), else
`Internal` if the author can commit to the target repo, else `Community`. All
three sources are handled; behavior differs by source:

| Behavior | **Internal** | **Community** | **Bot** |
|---|---|---|---|
| Assignee | the **author** (drives it) | signal owner from `--owners-team` (`pr-owners`) | signal owner from `--bot-owners-team` |
| Board lifecycle (`Revising`→`Todo`, auto-corrections) | yes | yes | yes |
| Auto-request reviewer (top collaborator-not-owner) | **no** (author picks own) | **yes** | yes |
| Report predicate ladder | **none** (excluded) | `COMMUNITY_LADDER` (incl. `needs CI approval`, `changes requested`) | `BOT_LADDER` (no CI-approval/changes rungs) |
| Drafts | exempt (author "not ready") | exempt (author "not ready") | **not exempt → `Todo` + owner** |

**One-liner:** Internal = *self-managed* (assign the author, keep the board
honest, then hands-off — no reviewer auto-request, no maintainer oversight);
Community = *bot-managed oversight*; Bot = the bot lane — a bot PR (**including a
draft**) goes to `Todo` + owner + reviewer so a human owner shepherds it to
ready-for-review (a draft never gets the "ready" comment). This is deliberately
different from human drafts (which are exempt). A coverage check gates the
promotion **only if `DEFAULT_COVERAGE_CHECK` is configured**; otherwise the human
owner is the gate. Fix-iteration is `/slang-github-webhook`'s job.

Assignee chain for Community/Bot (the source picks the owner pool): an owner
assigned to the PR's linked issue → highest-signal committer who is an owner →
`--maintainer`. Blocking review feedback returns any PR to `Revising`.

**Auto-corrections (board vs reality).** Before the normal lifecycle, the sweep
fixes contradictory board states rather than flagging them:

- **Open PR not on the board** -> add it (`addProjectV2ItemById`); the flow picks
  it up next sweep. (Org-wide: every off-board open PR in the swept repos is
  added.)
- **Open PR in `Done`** -> left alone only if it is **in the merge queue**;
  otherwise bounced back — `Revising` if changes were requested, else `Todo`
  (repos without a merge queue always bounce, since they never have a queue
  entry).
- **Human draft sitting in `Todo`/`In Progress`/`Done`** -> back to `Revising`.
- **Human PR in `Todo`/`In Progress` with failing CI** -> back to `Revising`
  (bot PRs are owner-shepherded and stay put, so they don't oscillate against
  promotion).
- **`In Progress` with no assignee** -> demote to `Todo` and assign (an
  unassigned PR can't legitimately be in progress).

The "always have an assignee" rule applies wherever an unassigned PR lands
in/returns to a human lane: Internal → the author; Community/Bot → the source's
assignee chain (above). **PRs already in the merge queue are left alone** — no
assignee or reviewer is added, since they are past the point of needing one.

Reviewers (Community/Bot only) = the assignee plus the single highest-signal
committer who is a **write+ collaborator of the PR's repo** (`push`/`maintain`/
`admin`) but not in the owner pool; the PR author is never requested. The
collaborator pool is read per-repo, so it covers everyone with repo access — not
just an org-level team. Two reviewer rules keep the request meaningful:

- **No piling on:** if the PR already has a *real* reviewer requested, no
  reviewer is added. "Real" excludes bots and `DEFAULT_IGNORED_REVIEWERS`
  (auto-assigned non-approvers, e.g. `bmillsNV`), since they cannot approve.
- **Unrequest the placeholder:** when the sweep assigns a PR, it unrequests any
  `DEFAULT_IGNORED_REVIEWERS` (e.g. `bmillsNV`) that GitHub auto-added.

**Committer signal (weighted).** Owners/committers are ranked by a weighted file
signal, not raw recency:

1. Per-file signal = `max(additions, deletions)` of the PR's change to that file
   × `file_multiplier(path)` (directory-glob table; longest match wins, default
   `1.0`).
2. Take the **top `--signal-top-files`** (default 10) files by per-file signal
   and normalize them into relative **weights** (sum = 1).
3. **Cheap pass** — a **single batched GraphQL query** fetches, per top file, the
   last `--signal-commits` (default 5) default-branch commits within
   `--signal-horizon-days` (default 180), each with its `oid`, author,
   **commit-total** `max(add, del)`, and the associated PR's `APPROVED` reviews.
   Each commit's LOC is attributed to its **author** — or, if the author is a
   bot, unmapped, or **the current PR's author**, to the **last `APPROVED`
   reviewer** of the PR that introduced it (dropped if none). The PR author and
   bots are never credited, so an author's own past commits credit their
   reviewer instead. Overall signal =
   Σ over files of `weight(file) × LOC(committer, file)`; ranked highest-first.
4. **Tiebreak (hybrid)** — when the cheap top two are *close* (within
   `--signal-clear-margin`, default 1.5×), re-score just the top
   `--signal-finalists` (default 6) candidates using **true per-file LOC**
   (commit-detail fetches, deduped by commit SHA) and re-order them. Skipped on a
   clear winner. This pays the expensive per-file-LOC cost only on the handful of
   commits tied to contenders that could actually be #1.

Cost: the cheap pass is ~1 GraphQL call per unassigned PR (history + reviews in
one query), independent of file/committer count. The tiebreak adds commit-detail
calls only for finalists' commits, and only on close calls — typically a handful,
zero on a clear winner. The cheap pass approximates with *total* commit LOC; the
tiebreak restores exact per-file LOC for the candidates that matter.

A **run-scoped cache** holds the PR-independent *source* data — each file's
default-branch history (keyed `(repo, path)`) and each commit's per-file stats
(keyed `(repo, sha)`) — so a hot file or shared commit is fetched once per sweep
no matter how many PRs touch it (the cheap pass only queries files it hasn't
seen). Only raw source data is cached; the per-PR weighting and attribution are
always recomputed.

**Cost.** CI/review/merge-queue/issue/file reads are batched into the one
GraphQL query per repo page (the **Collect** step), so the dominant `gh`-spawn
overhead is ~O(repos + pages), not O(open PRs). Signal work runs only for
*unassigned* PRs (its per-file history fetches are cross-sweep cached), so it
falls away as PRs get owners. The batched query is heavier server-side
(~5-6s/page) but trades hundreds of fast spawns for a handful of slower ones.

The ranking lives in [scripts/pr_signal.py](scripts/pr_signal.py); `pr_sweep.py`
calls it.
- **Draft human PRs are fully exempt** — no assignment, no nudges (draft = the
  author's "not ready" signal). They are still classified + carry a `Source`.

## Notification model: assignee-grouped report

The project-board inbox views are the passive reviewer inbox. Routine "ready for
review" is conveyed by `Todo` + assignee — not a message.

The script emits **one report, grouped by assignee**, surfaced at most once per
`DEFAULT_REPORT_INTERVAL_HOURS` (daily). Each section is one assignee's queue.
There is **no separate maintainer section**: an item that passes the maintainer
rung escalates **in place** — it stays under its assignee and gains the `⬆️`
marker. The maintainer scans the up-arrows (and sees their own owned PRs under
their own group). Example:

```
## Slang PR Escalation Report

- **<@111>**:
  - ⬆️ 🌐 [slang#334](…/pull/334) — needs CI approval
  - 🤖 [slang#9001](…/pull/9001) — awaiting review from: <@222>
- **`alice`**:
  - 🌐 [slang#777](…/pull/777) — changes requested — check if author is still active / needs help
```
- The report is titled **"Slang PR Escalation Report"**.
- **Within each assignee's group**, items are ordered Community (`🌐`) before Bot (`🤖`), and within each source escalated (`⬆️`) before not-escalated.
- `⬆️` marks an item **escalated** past the maintainer rung. The arrow fires even when the maintainer is the assignee — a public signal others can use to keep them honest about their own stalled items. Items are grouped under their assignee, so no `(@assignee)` tag is shown.
- `🌐` Community, `🤖` Bot. Internal PRs and human drafts are excluded. PR refs are clickable links.
- **Mentions** (`--recipient-map`): a login present in the supplied map renders as a `<@id>` mention that pings on Discord (the format also fits Slack); every other login — unmapped, or when no map is passed — renders as inert `` `login` `` so it never notifies the wrong person. The map is supplied per run; there is no auto-discovery, so **the invoker must pass `--recipient-map PATH`** to get pings. See the schema below.

### Per-source predicate ladders (the single source of truth)
Each PR's **reason** is the first matching predicate in its source's ladder; its
**stall** (working-hours since it last *moved* — board Status change / new commit
/ new review) selects the audience: it surfaces under its assignee once
`stall >= assignee_after`, and escalates in place (`⬆️`) once
`stall >= maintainer_after`. Defined in `LADDERS` (`COMMUNITY_LADDER` /
`BOT_LADDER`) in [scripts/pr_sweep.py](scripts/pr_sweep.py):

- **Community:** `needs CI approval` (assignee 0h / maintainer 24h) → `changes requested — check if author is still active / needs help` (1wk / 2wk) → `awaiting review from: …` (24h / 48h) → `CI failing — needs fixes` (24h / 48h) → `idle for N days` (24h / 48h).
- **Bot:** `awaiting review from: …` (48h / 1wk) → `CI failing — needs fixes` (48h / 1wk) → `idle for N days` (48h / 1wk). No `needs CI approval` (bots run in-repo, not fork-gated) or `changes requested` rung.

Edit the ladders to retune timeouts/audiences. The report is a **current-state**
list: an item keeps appearing until the PR moves (which resets its stall clock);
the daily cadence is the throttle.

The report describes the **post-plan** world: each PR's pending actions (status
transition, assignee, reviewer add/remove) are applied in-memory before
predicates run, so e.g. a PR the sweep is bouncing `Todo → Revising` shows its
real blocker rather than "awaiting review." Reviewer reasons list only
approve-capable reviewers — auto-assigned non-approvers (`DEFAULT_IGNORED_REVIEWERS`,
e.g. `bmillsNV`) and bots are excluded, and "awaiting review" only fires when a
real reviewer is requested.

### Surfacing the report (agent's job, method-agnostic)

The script only **emits** the report (stdout + the plan JSON's `report` field);
exit code `10` means "the daily report is due to surface." This skill does NOT
prescribe delivery — the agent uses whatever channel is available at runtime.
Always keep the bot-transparency disclaimer the script appends.

To make the report actually **notify** people (e.g. on Discord), pass
`--recipient-map PATH` when computing the plan; logins in the map render as
`<@id>` mentions. Without it, every login renders as inert `` `login` `` and
nobody is pinged. See "Recipient map" below.

### Recipient map (`--recipient-map`)

A flat JSON object mapping **GitHub login -> destination user ID** (matched
case-insensitively):

```json
{ "jhelferty-nv": "123456789012345678", "bob": "987654321098765432" }
```

- A login in the map renders as `<@id>` — a user mention that pings on Discord
  (the `<@id>` shape also fits Slack, the only other target we keep in mind; it
  is not on the roadmap).
- Any login **not** in the map (or whenever no file is passed) renders as inert
  `` `login` `` so it can never notify the wrong person.
- The path is supplied by the invoker **each run** — there is no fixed location
  or auto-discovery. Pass it alongside `--maintainer` (plan/one-shot); a replayed
  plan already has its `report` text baked in, so the flag has no effect there.
- The mapping affects the **report text only**. All routing, assignment writes,
  stall state, and bot detection stay on GitHub logins.

## Agent's residual job

1. Run the script — normally the full one-shot
   (`--maintainer <login> --apply --recipient-map <path>`). On a backlog run,
   plan first (omit `--apply`), eyeball `./.pr-sweep-plan.json`, then apply.
2. When exit code is `10`, surface the report to its recipients (method-agnostic).
3. Resolve the small set of flagged judgment calls (reviewer ties, contradictory
   states) from the `judgment_calls` list in the plan file.

Everything else is the script's.

## Configuration (top-of-file constants)

A normal run passes all three flags: `--maintainer LOGIN` (no default; rotates
every two weeks), `--apply` (perform GitHub writes), and `--recipient-map PATH`
(report mention table; see above). The latter two are each technically optional
and dropped only for the documented exceptions (dry-run/debug; absent or corrupt
mapping). Everything else is a constant near the top of `pr_sweep.py` — edit it
there if it moves:

| Constant | Value | Notes |
|------|---------|-------|
| `DEFAULT_ORG` | `shader-slang` | org swept when `DEFAULT_REPOS` is empty |
| `DEFAULT_REPOS` | _(empty)_ | comma-separated `owner/name` subset; empty -> every non-archived repo in the org |
| `DEFAULT_PROJECT_ID` | `PVT_kwDOAb2kZs4BSJKy` | the "Slang PR Tracking" board (hard-coded) |
| `DEFAULT_STATUS_*` | `Status` / `Revising`/`Todo`/`In Progress`/`Done` | board option names |
| `DEFAULT_SOURCE_*` | `Source` / `Internal`/`Community`/`Bot` | source-classification option names |
| `DEFAULT_COVERAGE_CHECK` | _(empty)_ | optional draft-PR coverage check gating bot `Revising -> Todo`. While empty, bot PRs (incl. drafts) promote to `Todo` + owner without a gate (the human owner is the gate) |
| `DEFAULT_OWNERS_TEAM` | `shader-slang/pr-owners` | **Community** assignee pool (parent team; member list includes the `bot-pr-owners` subteam) |
| `DEFAULT_BOT_OWNERS_TEAM` | `shader-slang/bot-pr-owners` | **Bot** assignee pool (subteam of `pr-owners`) |
| extra-reviewer pool | per-repo | write+ collaborators of each PR's repo (`repos/{repo}/collaborators`, `permissions.push == true`); members not in the owner pool. Read-only collaborators excluded. |
| `DEFAULT_FILE_MULTIPLIERS` | _(built-in table)_ | directory-glob -> weight; longest match wins, else `DEFAULT_FILE_MULTIPLIER` |
| `DEFAULT_SIGNAL_TOP_FILES` | `10` | top files (by per-file signal) used to rank committers |
| `DEFAULT_SIGNAL_COMMITS` | `5` | commits sampled per file for committer signal |
| `DEFAULT_SIGNAL_HORIZON_DAYS` | `180` | only consider commits within this window |
| `DEFAULT_SIGNAL_FINALISTS` | `6` | top candidates re-scored by true per-file LOC in the tiebreak |
| `DEFAULT_SIGNAL_CLEAR_MARGIN` | `1.5` | skip the tiebreak when #1's signal >= margin x #2's |
| `DEFAULT_BOT_AUTHORS` | `nv-slang-bot,slang-coworker-nanoclaw,Copilot,copilot-swe-agent` | bot logins matched by name (GitHub's `is_bot`/`__typename` is also honored for authors). `Copilot` is the coding-agent's assignee/reviewer login — GitHub types it as a `User` there, so it must be name-matched; the report skips bot assignees and routes to the first non-bot assignee (else signal owner, else maintainer) |
| `DEFAULT_IGNORED_REVIEWERS` | `bmillsNV` | auto-assigned reviewers that can't approve; unrequested on assignment and ignored when checking existing reviewer coverage |
| `DEFAULT_REPORT_INTERVAL_HOURS` | `24` | the assignee-grouped report is surfaced at most this often (daily) |
| `LADDERS` (`COMMUNITY_LADDER` / `BOT_LADDER`) | _(see code)_ | per-source predicate ladders: reason text + `(audience, after_working_hours)` rungs |
| `DEFAULT_WORKDAY_TZ` | `America/Los_Angeles` | timezone for the workday model (stall clock skips weekends) |
| `PLAN_FILE` | `./.pr-sweep-plan.json` | the computed, replayable plan + summary (incl. the `report` text) |
| `STATE_FILE` | `./.pr-sweep-state.json` | per-PR stall clocks (`move_fingerprint` + `last_moved_at`) and `last_report_at` |
| `DEFAULT_PR_PAGE_SIZE` | `25` | PRs per batched GraphQL page (capped by server timeout, not budget: n=50 returns HTTP 504, n=25 resolves in ~5-6s) |

The report's delivery channel is intentionally not configured here — the script
emits the report and the agent decides where it goes.

## Prerequisites

- `gh` authenticated (`gh auth status`) with: repo read; ProjectsV2 read; and —
  for `--apply` — repo write (issues/comments/assignees) + ProjectsV2 write.
- `read:org` so the script can list `DEFAULT_OWNERS_TEAM` and
  `DEFAULT_BOT_OWNERS_TEAM` membership; without it the assignee falls back to
  `--maintainer`. Querying the parent owners team returns its members **plus**
  the `bot-pr-owners` subteam's members (GitHub's "List team members" includes
  child teams).
- Repo push access so the script can (a) list the extra-reviewer pool
  (`repos/{repo}/collaborators`) and (b) read the author's permission for source
  classification (`repos/{repo}/collaborators/{author}/permission`). On error the
  collaborator pool is empty (no extra reviewer) and the PR classifies as
  `Community`.
- The script fails loudly if `gh` is missing/unauthenticated.
- A local clone is NOT required (commit history / board access go through
  `gh api`); running inside a checkout is only a fast path.

## Scheduling

Any scheduler works (cron, CI, or — in nanoclaw — a `schedule_task` with this
script as the pre-check). Wire it to run the full one-shot `--maintainer <login>
--apply --recipient-map <path>` ~every 30-60 min to keep the board reconciled; the
**report** is throttled to
once per `DEFAULT_REPORT_INTERVAL_HOURS` (daily), and exit code `10` means "the
report is due to surface." State (stall clocks + `last_report_at`) advances on
any apply — one-shot or replay; a plan-only run is side-effect free.

## Tests

```bash
python3 scripts/test_pr_sweep.py
```

Covers the pure decision functions (bot + source classification, the state
machine, the predicate ladders + assignee-grouped report routing, the
movement/stall clock, CI summarization, the weighted committer signal —
multipliers, top-K weights, overall ranking — and assignee/reviewer selection)
with no live `gh` calls.
