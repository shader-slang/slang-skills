# Coworker Operations

The fleet of NanoClaw-hosted agents that triage issues, fix bugs, and review pull requests for the Slang repositories. Also the machinery that composes, gates, evaluates, and pays for them.

## Coworkers and composition

**Coworker**:
One NanoClaw agent group with a role in the Slang fleet, such as triager, fixer, reviewer, or maintainer. It runs in its own container with its own memory.
_Avoid_: bot (for a coworker; the bot is the shared GitHub identity `nv-slang-bot`)

**Coworker type**:
A named entry in the lego registry, `coworker-types.yaml`, such as `slang-fixer`. It composes spine fragments, skills, workflows, overlays, and bindings; types inherit with `extends`.
_Avoid_: role template

**Orchestrator**:
The flat `main` admin coworker. It receives every webhook, routes work to coworkers, supervises issue chains, and alone has read-write access to `/workspace/shared`.
_Avoid_: main group, admin group

**Spine**:
A coworker's always-in-context `CLAUDE.md`, composed on every wake from spine fragments, skills, workflows, overlays, and trait bindings. Spine fragments, the identity, invariant, and context files under `container/spines/<project>/`, are its compose-time sources.
_Avoid_: provider document, system prompt (for the composed file)

**Trait**:
A dotted name, such as `repo.pr` or `code.edit`, for one ability in one of eight domains. Skills `provide` traits, workflows `require` them, and a coworker type binds each domain to the skill that provides it.
_Avoid_: capability name, capability (bare; a capability skill is a skill)

**Composer**:
The host module `src/claude-composer/` that renders a coworker type into its spine on every container wake and materializes each overlay's marker file. `npm run validate:templates` walks every leaf type through it to catch unresolved traits and unknown references.
_Avoid_: template system, spine renderer (for the whole module)

**Workflow**:
A compose-time step sequence, `WORKFLOW.md`, such as `plan` or `implement`, embedded into a coworker's `CLAUDE.md`. Steps carry `{#step-id}` anchors for overlays.

**Overlay**:
A compose-time gate protocol, `OVERLAY.md`, spliced into workflows at step anchors and materialized as a marker file the hooks read. Examples are `critique-gate` and `eval-sandbox`.

**Gate**:
A PreToolUse or Stop hook that refuses an action until a condition holds and names the rule it hit. A script gate is different: a scheduled task's pre-check that decides whether to wake the agent.

**Critique gate**:
The gate that refuses delivery markers such as `[Fix Report]` and `gh pr create` until every required `/codex-critique` stage is recorded with verdict approve.

**Buddy**:
The independent codex reviewer the `buddy-monitor` overlay enables: a PostToolUse hook watches the session and prepends concerns as `<buddy-note>` on the next turn. It runs entirely in the hook chain; the agent never invokes it and must answer every note.
_Avoid_: companion monitor

## Sessions and chains

**Agent group**:
The NanoClaw entity behind a coworker: a folder, `CLAUDE.md`, skills, container config, and database rows. "Group" alone means an agent group unless a messaging group is named.

**Thread**:
The shared topic key, `gh-issue-<owner>/<repo>-<num>` for GitHub work, carried by every coworker's session on that topic. A session is one coworker's private memory for a thread, not the conversation.
_Avoid_: session (for the shared topic)

**Chain**:
An in-flight issue: the set of coworker sessions sharing one issue thread, from webhook delivery to a merged fix or a recorded disposition.

**Nudge**:
A message the orchestrator sends into a stuck chain's owning session, as opposed to a fresh dispatch. A re-chase is a capped one-shot re-check of a parked chain.

**Stand-down**:
The note a coworker or the host posts on an issue to announce that it will not triage or fix it. It opens "Standing down on this one" and satisfies rule R6 of the Contributor AI Standard.

**Silent hold**:
An open, human-filed issue older than the stand-down window on which the bot has neither acted nor posted a stand-down note. It is a compliance failure.

**Opt-out label**:
One of `GoodFirstBug`, `HelpWanted`, or `no-bot` on an issue. It stops every bot session on that issue and blocks the bot's GitHub writes to it. The host adds `no-bot` when the author or a collaborator tells the bot to stop.
_Avoid_: newcomer label, bot-ok

## Evaluation

**Driver**:
The `eval-compliance` coworker in its eval-runner role. It dispatches trials, waits, scores, keeps spend under the cap, and never solves a task itself.
_Avoid_: harness

**Eval copy**:
A coworker deployed with the `eval-sandbox` overlay, so it works only on the `slang-coworkers/slang-eval` fork and writes answers to files instead of posting.
_Avoid_: evaluation copy

**Eval sandbox**:
The overlay and hook, `gate-eval-sandbox.sh`, that refuse every write outside `EVAL_ALLOWED_REPOS` and every message to a human, while reads stay allowed.
_Avoid_: gym, sandbox (bare)

**Bank**:
The `slang-eval-tasks` repository: one directory per task with `instruction.md`, `task.toml`, and a verifier, listed in `MANIFEST.json`.

**Task**:
In evaluation, one bank entry identified by task id and kind: triage, reply, review, or fixer. In NanoClaw, a scheduled job created with `ncl tasks create`; a one-shot task fires once with `--process-after`.

**Trial**:
One run of one task by an eval copy, named `<task-id>#r<k>`. It is dispatched as its own one-shot task with a fresh session and its own answer directory.
_Avoid_: attempt (an attempt is a retry of a trial)

**Repeat**:
One of the `--repeats` independent trials of a task, by default 3 for triage and reply and 2 for fixer and review. A job never cites a single repeat as a result.

**Variant**:
The label, `--variant`, naming what a job tests, such as a prompt or a skill version. A variant job is compared to a baseline job with a paired bootstrap interval.

**Baseline**:
The reference job, variant `baseline`, against which a variant job's per-task means are paired.

**Compliance check**:
The weekly read-only scoring of the bot's GitHub and Discord posts against the ten rules of the Contributor AI Standard. The `eval-compliance` coworker runs it and delivers an HTML report.

## Cost and delivery

**Cost cap**:
The per-group spend limit on a session. Tier 1 is the group's seven-day p90 and escalates to a human; Tier 2 is the ceiling, typically 150 USD, and hard-stops non-immortal sessions.
_Avoid_: budget (for the cap mechanism; a budget is an eval job's `--budget-usd`)

**Fork**:
Two meanings: a customized NanoClaw install defined by its skills recipe, and the `slang-coworkers/slang-eval` repository that eval copies push to. Say "eval fork" for the second.

**Deploy**:
Running `deploy/prod-deploy.sh` on a coworker box: merge the pending `nv-*` commits, retag the agent image, and restart the host so new containers run the new build. A deploy waits for idle groups and is logged under `deploy/logs/`.
_Avoid_: release (for a coworker box update), upgrade (bare)

## Shared knowledge and credentials

**Learning**:
One durable finding a coworker records with `append_learning` as a Markdown file under `/workspace/shared/learnings/`, readable by every coworker. It is immutable once written; a group's private `memory/` files are memory, not learnings.
_Avoid_: atom (the wiki's layer word for a raw learning file)

**Credential gateway**:
The HTTPS proxy, installed by setup behind the gateway provider seam, that holds secrets and injects them into a container's outbound requests. No credential enters a container; OneCLI's Agent Vault is the current provider, not the concept.
_Avoid_: OneCLI (for the concept; it is the current provider), vault, credential proxy
