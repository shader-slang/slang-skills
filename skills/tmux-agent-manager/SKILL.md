---
name: tmux-agent-manager
description: >-
  Manage multiple Claude Code agent sessions running in tmux. Report a
  status summary of all sessions, deliver instructions to a specific agent
  via tmux send-keys, and automatically monitor the agent after each send
  to detect permission prompts, clarifying questions, or early-idle states.
  Use when the user wants to oversee concurrent Claude agents, check what
  sessions are doing, send a message to an agent, or monitor for sessions
  that need input or are stuck. Works on native Linux, macOS, WSL (inside),
  and Windows with WSL (Git Bash or PowerShell host).
argument-hint: "[status | send [session] <message> | monitor [interval_seconds] | new <issue_number_or_prompt>]"
allowed-tools:
  - Bash
---

# Tmux Agent Manager

Oversees multiple Claude Code sessions running in tmux.

---

## Environment Detection (run first, before any other step)

Run this once at the start of every skill invocation to set the variables
used throughout. Run it as a plain bash block (no subshell wrapper) so the
variables are available in your reasoning context for all subsequent steps:

```bash
# How to reach tmux
if command -v tmux &>/dev/null; then
    TMUX_EXEC="tmux"
    SH="bash -c"        # run inline shell commands
elif wsl tmux -V >/dev/null 2>&1; then
    # tmux not in PATH but available via WSL — Windows host
    TMUX_EXEC="wsl tmux"
    SH="wsl bash -c"
else
    echo "tmux is not available (native or via wsl tmux). Install tmux and retry."
    exit 1
fi

# Which git binary produces consistent paths
# Inside WSL, git.exe gives Windows-style paths that match the worktree list
if grep -qi microsoft /proc/version 2>/dev/null; then
    HOST="wsl_inside"
    GIT="git.exe"
elif [ "$TMUX_EXEC" = "wsl tmux" ]; then
    HOST="windows"
    GIT="git.exe"
else
    HOST="unix"         # native Linux or macOS
    GIT="git"
fi

echo "TMUX_EXEC=$TMUX_EXEC SH=$SH HOST=$HOST GIT=$GIT"
```

Re-declare `TMUX_EXEC`, `SH`, `HOST`, `GIT`, and `PREV_PANE_DIR` at the top of every subsequent
bash block that needs them, using the values printed above.

**Variable reference used in all steps below:**

| Variable | Windows/Git Bash | WSL inside | Native Linux/macOS |
|---|---|---|---|
| `TMUX_EXEC` | `wsl tmux` | `tmux` | `tmux` |
| `SH` | `wsl bash -c` | `bash -c` | `bash -c` |
| `GIT` | `git.exe` | `git.exe` | `git` |
| `HOST` | `windows` | `wsl_inside` | `unix` |

**Path helpers** — use these when building paths for tmux vs. for git:

- On `unix`: only one path form; no conversion needed.
- On `wsl_inside`: `git.exe` returns Windows paths (`D:/foo`); convert with `wslpath` before
  passing to tmux or bash. Shell path = `wslpath "D:/foo"` → `/mnt/d/foo`.
- On `windows`: `git.exe` returns Windows paths; convert with `wsl wslpath` before passing to
  `wsl tmux` or `wsl bash`. Windows path → WSL path: `wsl wslpath "D:/foo"` → `/mnt/d/foo`.

---

## Commands

- `/tmux-agent-manager` or `/tmux-agent-manager status` — snapshot of all sessions
- `/tmux-agent-manager send <session-name> <message>` — deliver instruction to an agent
- `/tmux-agent-manager monitor [interval_seconds]` — check all sessions, mark any
  needing attention in status output, and schedule the next check via ScheduleWakeup
  (default: cache_ttl − 60 s, currently 240 s)
- `/tmux-agent-manager new <issue_number>` — create worktree + tmux session for a GitHub
  issue and spawn a Claude agent to fix it
- `/tmux-agent-manager new <free-form prompt>` — same, driven by a task description

Parse `$ARGUMENTS` to determine which command to run. If empty or "status", run status.

---

## Step 1 — Enumerate candidate agent panes, then filter to confirmed agents

```bash
$TMUX_EXEC list-sessions -F "#{session_name}" | sed 's/$/:0.0/'
```

This produces one `SESSION:0.0` candidate per session. After listing, **filter** to
only sessions whose pane tail shows Claude/Codex agent markers: a welcome banner,
a model-info line, or the `›` prompt pattern expected by Step 2. Discard sessions
that show none of these — they are unrelated tmux sessions and must not be targeted
for status classification, sends, or implicit target resolution.

Capture 250 lines of scrollback from each candidate and test against the agent-marker regex. Using scrollback ensures startup markers aren't lost even after verbose output, and including working-state markers catches busy sessions:

```bash
tail_output=$($TMUX_EXEC capture-pane -t "$SESSION:0.0" -p -S -250 | tail -250)
echo "$tail_output" \
  | grep -qE "(Claude Code|Codex|Model: claude-|›.*claude-|^›[[:space:]]*$|• (Ran|Read|Writing|Searching))" \
  && echo "AGENT" || echo "NOT_AGENT"
```

Discard any session that returns `NOT_AGENT`.

After the active agent set is known, purge orphaned state files so the cache directories don't accumulate stale entries indefinitely:

```bash
for state_dir in \
    "${HOME}/.cache/tmux-agent-manager/prev_pane" \
    "${HOME}/.cache/tmux-agent-manager/yolo_mode"; do
  [ -d "$state_dir" ] || continue
  for f in "$state_dir"/*; do
    [ -f "$f" ] || continue
    session_name=$(basename "$f")
    # Remove file if no active agent session has this sanitized name
    if ! echo "$ACTIVE_AGENT_SESSIONS" \
        | sed 's/[^a-zA-Z0-9.-]/_/g' \
        | grep -Fxq "$session_name"; then
      rm -f "$f"
    fi
  done
done
```

`ACTIVE_AGENT_SESSIONS` is the newline-separated list of confirmed AGENT session names produced by the filter above.

---

## Step 2 — Capture pane state

For each pane target `SESSION:W.P`, capture 250 lines of scrollback (so the `─ Worked for` separator and other signals aren't lost after verbose output):

```bash
$TMUX_EXEC capture-pane -t "SESSION:W.P" -p -S -250 | tail -250
```

**State detection rules** (apply to the captured tail):

| State | Signal in captured output |
|---|---|
| `idle` | `›` prompt at bottom with model info line and NO pending message text after `›`; `─ Worked for` separator may also be present (post-task) but is not required — a freshly started session waiting for its first prompt classifies as idle too |
| `working` | Lines contain `• Ran`, `• Read`, `• Writing`, `• Searching`, spinner chars, or active build/test output |
| `needs_approval` | Lines near bottom contain "Do you want to", "Allow", "(y/n)", "Yes/No", or "approve" |
| `pending_message` | `›` prompt followed by user message text (received but not yet processed) |
| `stuck` | Pane content identical across two consecutive polls AND state is not `idle`; **monitor-loop only** — store previous pane snapshot in `PREV_PANE_DIR/<session>`; compare with current snapshot on each iteration; if unchanged and state ≠ `idle`, classify as `stuck` |
| `unknown` | None of the above — treat as working |

**Stuck detection — state management** (monitor-loop only):

Store per-session snapshots in a temp directory (portable; avoids `declare -A` which requires Bash 4.0+ and is unavailable on macOS's default Bash 3.2):

```bash
PREV_PANE_DIR="${HOME}/.cache/tmux-agent-manager/prev_pane"
mkdir -p "$PREV_PANE_DIR"

# Each iteration, after capturing current_tail for SESSION:
SAFE_SESSION=$(echo "$SESSION" | sed 's/[^a-zA-Z0-9.-]/_/g')
prev_tail=$(cat "$PREV_PANE_DIR/$SAFE_SESSION" 2>/dev/null || echo "")

if [ -n "$prev_tail" ] && [ "$current_tail" = "$prev_tail" ] && [ "$state" != "idle" ] && [ "$state" != "needs_approval" ]; then
    state="stuck"
fi

printf "%s\n" "$current_tail" > "$PREV_PANE_DIR/$SAFE_SESSION"
```

On the first iteration the file does not exist, so `prev_tail` is empty and no session is classified as `stuck` initially.

### YOLO mode detection

For each session, also check whether Claude Code was started with
`--dangerously-skip-permissions`. Without this flag, every tool call triggers a
permission prompt and the agent will stall repeatedly.

Scan the last 200 lines of the pane scrollback (which usually includes the startup banner):

```bash
$TMUX_EXEC capture-pane -t "SESSION:0.0" -p -S -200 \
  | grep -qE "dangerously-skip-permissions|Bypassing permission" \
  && echo "yolo" || echo "normal"
```

Claude Code prints `⚠️  Bypassing permission checks (--dangerously-skip-permissions)` in
its welcome banner when the flag is active. If that line is absent, classify the session
as `normal` (not in bypass mode).

Store the result per session using the same file-based pattern as `PREV_PANE_DIR` (portable; avoids associative arrays which require Bash 4.0+):

```bash
YOLO_MODE_DIR="${HOME}/.cache/tmux-agent-manager/yolo_mode"
mkdir -p "$YOLO_MODE_DIR"
SAFE_SESSION=$(echo "$SESSION" | sed 's/[^a-zA-Z0-9.-]/_/g')
echo "yolo_or_normal" > "$YOLO_MODE_DIR/$SAFE_SESSION"
```

To read: `YOLO=$(cat "$YOLO_MODE_DIR/$SAFE_SESSION" 2>/dev/null || echo "normal")`

---

## Step 3 — Status report

Present a compact table, one row per session:

```text
SESSION                   STATE           ETA        SUMMARY
add-skill-to-resolve-…    idle            —          Pushed commit 326730bd — waiting for next instruction
descheap-for-raytracing   working         ~20 min    Running slang-test on descriptor-heap-acceleration-structure.slang
wgsl-require-bab-load     needs_approval  ⚠ blocked  Waiting for permission prompt: "Allow bash command?"
fix-lambda-capture        working         ~2 min     Editing source/slang/slang-check-expr.cpp
```

Sessions created by Step 7 are capped at 40 chars. Sessions started outside this
skill may have longer names — truncate display names to 40 chars with `…` as needed
for table alignment. SUMMARY = last meaningful agent output line.

**YOLO mode warning** — after the table, list every session whose `YOLO_MODE` is `normal`
as a dedicated warning block:

```text
⚠ The following sessions are NOT running with --dangerously-skip-permissions:
  • <session-name>
  • <session-name>
These agents will pause and request approval for every tool call.
To restart with bypass mode: $TMUX_EXEC kill-session -t <name>, then
/tmux-agent-manager new <issue> (which always passes --dangerously-skip-permissions).
```

If all sessions are in YOLO mode, omit the warning block entirely.

**ETA estimation rules** — read the pane tail to classify the current activity, then apply:

| Activity detected in pane | ETA |
|---|---|
| State is `idle` | `—` (already stable) |
| State is `needs_approval` or `stuck` | `⚠ blocked` (won't progress without input) |
| State is `pending_message` | `~0 min` (about to start processing) |
| Running `cmake --build` or `cmake --workflow` | `~5–20 min` |
| Running `slang-test` (full suite) | `~15–30 min` |
| Running a single test file | `~1–3 min` |
| Editing/writing files, running short shell commands | `~1–5 min` |
| Waiting for CI (GitHub Actions, mentions "workflow run") | `~10–30 min` |
| Submodule init or large git operation | `~1–2 min` |
| Activity clearly just started (spinner, first tool call) | `~5–15 min` |
| Cannot determine from pane content | `?` |

When the pane output contains timestamps or progress indicators (e.g. `[12/240]` in a cmake build), use them to refine the estimate: remaining fraction × typical total time.

---

## Step 4 — Send instruction

Execution order: **4a** (pre-send checks) → **send** → **4b** (confirm delivery) → **4c** (monitor progress).

1. Parse `$ARGUMENTS` with two explicit forms:
   - `send <session-name> <message>` — session name provided explicitly (Case A in Step 4a)
   - `send <message>` — no session token; target resolved implicitly (Case B in Step 4a)
2. Run **Step 4a — Correlation check** before sending anything.
3. Send to the agent pane using a temp file to safely handle newlines and special characters:

```bash
if [ "$HOST" = "windows" ]; then
    TMP_PAYLOAD=$(wsl mktemp /tmp/agent_send_msg.XXXXXX)
    wsl bash -c "cat > '$TMP_PAYLOAD'" << 'EOF_TMUX_AGENT'
MESSAGE
EOF_TMUX_AGENT
else
    TMP_PAYLOAD=$(mktemp /tmp/agent_send_msg.XXXXXX)
    cat > "$TMP_PAYLOAD" << 'EOF_TMUX_AGENT'
MESSAGE
EOF_TMUX_AGENT
fi
PRE_SEND_TAIL=$($TMUX_EXEC capture-pane -t "SESSION:0.0" -p | tail -20)
$TMUX_EXEC load-buffer "$TMP_PAYLOAD"
$TMUX_EXEC paste-buffer -t "SESSION:0.0"
# Wait for the paste to land in the terminal before sending Enter.
# paste-buffer is async — sending Enter immediately risks the keystroke
# arriving before the pasted text and being swallowed.
sleep 1
$TMUX_EXEC send-keys -t "SESSION:0.0" Enter
# Do NOT rm TMP_PAYLOAD here — Step 4b may need it for a retry.
```

4. Run **Step 4b — Queue verification** to confirm the message was actually submitted.
5. Run **Step 4c — Post-send monitoring** before returning to the user.

---

## Step 4a — Correlation check

**Goal:** prevent sending a message intended for one agent to an agent working on a
different issue, and catch ambiguous targets before any message is delivered.

Run this check immediately after parsing `$ARGUMENTS`, before any `tmux send-keys`.

### 4a-i — Enumerate active sessions

```bash
$TMUX_EXEC list-sessions -F "#{session_name}"
```

Capture the session name and last 10 lines of pane 0.0 for each session.

### 4a-ii — Resolve the target session

**Case A — Session name was provided explicitly** (user wrote `send <name> <message>`):

1. Check that `<name>` exactly matches an active **agent** session (one that passed Step 1
   marker filtering). If not, list the active agent sessions and stop — **do not send**.
   If `<name>` exists in tmux but is `NOT_AGENT`, explicitly report that it is not a
   Claude/Codex agent pane and stop.
2. Continue to the mismatch check in 4a-iii.

**Case B — Implicit-target form** (`send <message>` with no session token):

1. If there is exactly one active **agent** session → treat it as the target; skip to 4a-iii.
2. If there are multiple active sessions → **ask the user**:

   > "There are N active agent sessions: [list names with one-line summaries].
   > Which session should receive this message?"

   Do **not** guess. Wait for the user's answer, then re-enter at Step 4.

### 4a-iii — Mismatch check (for Case A with an explicit session name)

Compare the user's stated intent (issue number, keywords, or description in the message)
against the target session's apparent task:

- **Session name** — the slug encodes the original issue or task (e.g. `fix-lambda-capture`,
  `descheap-for-raytracing`). Treat each `-`-separated word as a keyword.
- **Pane content** — the last 10 lines may show a file name, test name, or error message
  that reveals the task more precisely than the slug alone.

**Mismatch signals** — flag a mismatch when **any** of the following are true:

| Signal | Example |
|---|---|
| User references a GitHub issue number and the session name contains a different issue number | User says "#1234", session slug contains "1567" |
| User explicitly names a different issue/feature than the session slug describes | User says "lambda fix", session is `descheap-for-raytracing` |
| User says "the agent working on X" and the target session name contains none of X's keywords | User says "shader compiler crash", session is `fix-lambda-capture` |

**When a mismatch is detected**, stop and ask the user to confirm before sending:

> "⚠ The session `<name>` appears to be working on **<inferred task>**, but your message
> references **<user's described task>**. Active sessions:
> [list all sessions with one-line summaries]
> Did you mean to send to a different session, or should I proceed with `<name>`?"

Wait for explicit confirmation or a corrected session name before proceeding.

**When no mismatch is detected**, proceed directly to sending (Step 4, item 3).

### 4a-iv — Ambiguity heuristic

When the user's message contains strong issue-specific signals (an issue number, a unique
identifier, a distinctive file or function name) and there is more than one active session
whose slug partially matches those signals, treat this as ambiguous and ask:

> "Multiple sessions could match your description: [list candidates with summaries].
> Which one should receive this message?"

Do **not** guess. Always prefer asking over sending to the wrong agent.

---

## Step 4b — Queue verification

**Goal:** confirm that the message was received and submitted to the agent. Recover
automatically from two common failure modes: Enter not processed (text visible but stuck
in the input buffer) and paste failed silently (pane looks unchanged).

Run this immediately after the send block in Step 4, before Step 4c.

### Parameters

| Parameter | Default |
|---|---|
| `VERIFY_WAIT` | 2 s — wait before first check |
| `MAX_RETRIES` | 2 — total attempts before giving up |

### Algorithm

```text
attempt = 1

while attempt <= MAX_RETRIES:
    sleep VERIFY_WAIT
    tail = capture last 20 lines of SESSION:0.0
    classify state (idle / working / needs_approval / pending_message / unknown)

    if state == working or state == needs_approval or state == unknown:
        # Agent received the message and is acting on it (or needs approval).
        report "✓ Message queued — agent is processing."
        rm -f "$TMP_PAYLOAD"
        return  # proceed to Step 4c

    if state == pending_message:
        # Text is visible after › but Enter was not processed.
        # This is the "waiting for ENTER" failure mode.
        $TMUX_EXEC send-keys -t "SESSION:0.0" Enter
        attempt += 1
        continue

    if state == idle:
        if attempt == 1 and tail == PRE_SEND_TAIL:
            # Pane matches pre-send snapshot — paste failed silently.
            # Retry the full send sequence before giving up.
            $TMUX_EXEC load-buffer "$TMP_PAYLOAD"
            $TMUX_EXEC paste-buffer -t "SESSION:0.0"
            sleep 1
            $TMUX_EXEC send-keys -t "SESSION:0.0" Enter
            attempt += 1
            continue
        elif attempt == 1 and tail != PRE_SEND_TAIL:
            # Pane changed from pre-send — command ran and completed quickly.
            report "✓ Message queued — agent completed the task quickly."
            rm -f "$TMP_PAYLOAD"
            return
        else:
            # Second idle after retry — give up and report.
            ALERT: "⚠ Message delivery to SESSION failed after $MAX_RETRIES attempts.
                    The agent pane appears unchanged. Last 20 pane lines:"
            show tail
            rm -f "$TMP_PAYLOAD"
            return  # do NOT proceed to Step 4c

rm -f "$TMP_PAYLOAD"
ALERT: "⚠ Message delivery to SESSION failed after $MAX_RETRIES attempts.
        The message still appears pending (Enter may not be processing). Last 20 pane lines:"
show tail
return  # do NOT proceed to Step 4c
```

> **`pending_message` state detection**: the pane tail contains text after the last `›`
> prompt line that is not a model-info or separator line — i.e., the agent has typed input
> waiting to be submitted with Enter.

---

## Step 4c — Post-send monitoring

**Goal:** catch permission prompts, clarifying questions, and early-idle states before
the user moves on.

Run this after Step 4b confirms the message was queued. Applies to both regular `send`
and the initial prompt sent in Step 7h for new sessions.

### Parameters

| Parameter | Default | Meaning |
|---|---|---|
| `CHECK_INTERVAL` | 10 s | Seconds between pane polls |
| `MAX_WAIT` | 120 s | Stop monitoring after this many seconds |
| `WORKING_GRACE` | 20 s | Seconds after send before an `idle` return triggers an alert |

**Parameter overrides**: declare the variable before running the algorithm. For example, Step 7h uses a longer grace period for freshly-started sessions:

```bash
WORKING_GRACE=30  # new sessions need more time to initialize
# then run Step 4c algorithm
```

### Algorithm

```text
elapsed = 0
saw_working = false

loop every CHECK_INTERVAL until elapsed >= MAX_WAIT:
    capture 250 lines of scrollback from SESSION:0.0
    classify state (idle / working / needs_approval / unknown)

    if state == needs_approval:
        ALERT: "⚠ SESSION needs approval — agent is waiting for a permission prompt."
        if get_yolo_mode(SESSION) == "normal":  # cat "$YOLO_MODE_DIR/$SAFE_SESSION"
            ALERT (append): "⚠ This agent was NOT started with --dangerously-skip-permissions.
                             It will block on every tool call requiring approval.
                             Consider restarting it with bypass mode enabled."
        show the relevant pane lines
        return (stop monitoring)

    if state == working or state == unknown:
        saw_working = true
        if elapsed >= MAX_WAIT - CHECK_INTERVAL:
            report "✓ SESSION is working — monitoring complete."
            return

    if state == idle:
        if NOT saw_working AND elapsed < WORKING_GRACE:
            # Too soon to judge — the agent may still be thinking.
            sleep CHECK_INTERVAL
            elapsed += CHECK_INTERVAL
            continue
        if NOT saw_working:
            ALERT: "⚠ SESSION returned to idle without any visible tool activity.
                    The agent may be asking a clarifying question or encountered an error."
            show last 35 pane lines
            return
        else:
            # Agent finished quickly — that is fine.
            report "✓ SESSION completed the task and is now idle."
            return

    sleep CHECK_INTERVAL
    elapsed += CHECK_INTERVAL

# Timed out while still working — that is OK.
report "✓ SESSION is still working after MAX_WAIT s — no attention needed."
```

### Alert format

When emitting an alert, always include:
- Session name
- Detected state
- The last 250 lines of scrollback so the user can see the exact prompt or error

### After an alert

Do **not** automatically send any reply or click "Yes". Present the pane content to the
user and let them decide how to respond (e.g., use `send` to answer a question or approve
a permission prompt).

---

## Step 5 — Notifications

<!-- TODO: implement cross-platform notifications (osascript, notify-send, PowerShell toast) -->

When a session is in `needs_approval` or `stuck` state, skip the notification for now and
simply include a prominent `⚠ NEEDS ATTENTION` marker in the status report printed to the
user.

---

## Step 6 — Monitor loop

1. Run status workflow (Steps 1–3).
2. Mark every `needs_approval` or `stuck` session with `⚠ NEEDS ATTENTION` in the status table (notifications are not yet implemented — see Step 5).
3. Report status table to user.
4. Schedule next wakeup via ScheduleWakeup:
   - `delaySeconds`: interval from `$ARGUMENTS`; if not provided, pick `cache_ttl_seconds - 60`
     (default **240 s** at the current 5-minute cache TTL, giving a 60 s safety margin).
     Never use a value at or above the cache TTL — doing so forces a cold context re-read on
     every wakeup. If you know the cache TTL has changed, recalculate accordingly.
   - `prompt`: `/tmux-agent-manager monitor <interval>`
   - `reason`: "periodic tmux agent health check"

---

## Step 7 — Spawn a new agent session

When command is `new <args>`:

- If `<args>` is a bare integer → GitHub issue number
- Otherwise → free-form task prompt

### 7a — Determine slug and task prompt

> **Note:** When handling an issue number, run **Step 7b** (path discovery) first to populate `$REPO` before executing the `gh issue view` command below.

**Issue number path:**
```bash
gh issue view <number> --repo "$REPO" --json number,title,body,labels
```
- `slug` ← from `title`
- `branch prefix` ← labels: "bug"/"crash" → `fix/`; "feature"/"enhancement" → `feature/`; else `fix/`
- Claude prompt: issue title + body (truncated to 3000 chars) + instruction to fix, test, commit

**Free-form path:**
- `slug` ← from the prompt text
- `branch prefix` ← prompt contains "feature"/"add" → `feature/`; else `fix/`
- Claude prompt: the user's prompt verbatim + instruction to test and commit

**Slug rule:** lowercase → replace runs of non-alphanumeric chars with `-` → collapse
consecutive `-` → strip leading/trailing `-` → truncate to 40 chars → strip any
trailing `-` left by the truncation.

Keep the most meaningful words (usually the first few): a 40-char slug must still be
recognisable at a glance without needing further truncation in the status table.

Full branch: `<prefix><slug>` (e.g. `fix/getTypeNameHint-cr`)
Session/worktree name: `<slug>` (no prefix)

### 7b — Discover paths dynamically

Run this inside a single shell call (adapt prefix for HOST):

```bash
# Get the main worktree path (first entry — always the primary checkout)
MAIN_NATIVE=$($GIT worktree list --porcelain 2>/dev/null | sed -n 's/^worktree //p' | head -n 1 | tr -d '\r')
if [ -z "$MAIN_NATIVE" ]; then
    echo "Error: not in a git repository or could not determine main worktree."
    exit 1
fi

# Convert to the shell's native path if needed
if [ "$HOST" = "wsl_inside" ]; then
    MAIN_SHELL=$(wslpath "$MAIN_NATIVE")       # D:/foo → /mnt/d/foo
elif [ "$HOST" = "windows" ]; then
    MAIN_SHELL="$MAIN_NATIVE"                  # Git Bash handles Windows paths; convert to WSL path at call sites that need it
else
    MAIN_SHELL="$MAIN_NATIVE"                  # already a POSIX path
fi

PARENT_SHELL=$(dirname "$MAIN_SHELL")          # sibling worktrees live here
PARENT_NATIVE=$(dirname "$MAIN_NATIVE")

# Derive GitHub repo (owner/name) via gh CLI (robust across URL formats)
REPO=$(cd "$MAIN_SHELL" && gh repo view --json nameWithOwner -q .nameWithOwner 2>/dev/null)
if [ -z "$REPO" ]; then
    echo "Error: could not determine GitHub repository. Ensure gh is authenticated and the directory is a GitHub repo."
    exit 1
fi
```

New worktree paths:
- Shell path (for tmux `-c` and cd): `$PARENT_SHELL/<slug>`
- Native path (for `git worktree add`): `$PARENT_NATIVE/<slug>`

### 7c — Collision check

```bash
$TMUX_EXEC has-session -t "<slug>" 2>/dev/null && echo EXISTS || echo OK
test -d "$PARENT_SHELL/<slug>" && echo EXISTS || echo OK
```

Stop and tell the user if either returns `EXISTS`.

### 7d — Create the worktree

```bash
$GIT -C "$MAIN_NATIVE" worktree add "$PARENT_NATIVE/<slug>" -b "<branch>"
```

### 7e — Initialize submodules with local reference

`--reference` points git at the main worktree's object store so it copies blobs
locally instead of downloading them again — much faster on large repos:

```bash
cd "$PARENT_SHELL/<slug>"
$GIT submodule update --init --recursive --reference "$MAIN_NATIVE"
```

Tell the user this step is running; it may take up to a minute the first time.

### 7f — Create the tmux session

```bash
TMUX_C_PATH="$PARENT_SHELL/<slug>"
[ "$HOST" = "windows" ] && TMUX_C_PATH=$(wsl wslpath "$TMUX_C_PATH")
$TMUX_EXEC new-session -d -s "<slug>" -c "$TMUX_C_PATH"
```

### 7g — Start Claude Code (or Codex)

```bash
# Claude Code (default)
$TMUX_EXEC send-keys -t "<slug>:0.0" "claude --dangerously-skip-permissions" Enter

# Codex alternative
$TMUX_EXEC send-keys -t "<slug>:0.0" "codex --dangerously-bypass-approvals-and-sandbox" Enter
```

Use whichever agent the user requests; default to `claude` if unspecified.

Wait 8 seconds, then capture the pane tail and look for the `›` prompt or model info
line. Retry every 5 seconds up to 3 times. If Claude still hasn't started, show the raw
pane content to the user and stop.

Once the `›` prompt is confirmed, run the YOLO mode check from Step 2 against the new
session's scrollback:

```bash
$TMUX_EXEC capture-pane -t "<slug>:0.0" -p -S -200 \
  | grep -qE "dangerously-skip-permissions|Bypassing permission" \
  && echo "yolo" || echo "normal"
```

If the result is `normal`, emit a warning and continue immediately to Step 7h:

```text
⚠ Session '<slug>' is NOT running with --dangerously-skip-permissions.
  The agent will pause and request approval for every tool call.
  To fix: kill this session and restart claude with --dangerously-skip-permissions.
```

### 7h — Send the task prompt

Write to a temp file to safely handle newlines and special characters:

```bash
if [ "$HOST" = "windows" ]; then
    TMP_PAYLOAD=$(wsl mktemp /tmp/agent_prompt_<slug>.XXXXXX)
    wsl bash -c "cat > '$TMP_PAYLOAD'" << 'EOF_TMUX_AGENT'
<composed prompt text>
EOF_TMUX_AGENT
else
    TMP_PAYLOAD=$(mktemp /tmp/agent_prompt_<slug>.XXXXXX)
    cat > "$TMP_PAYLOAD" << 'EOF_TMUX_AGENT'
<composed prompt text>
EOF_TMUX_AGENT
fi

$TMUX_EXEC load-buffer "$TMP_PAYLOAD"
$TMUX_EXEC paste-buffer -t "<slug>:0.0"
sleep 1
$TMUX_EXEC send-keys -t "<slug>:0.0" Enter
# Do NOT rm TMP_PAYLOAD here — Step 4b may need it for a retry.
```

After sending, run **Step 4b — Queue verification** targeting `<slug>:0.0` to confirm
the prompt was actually submitted, then run **Step 4c — Post-send monitoring** to confirm
the agent starts working (not blocked on a permission prompt or asking questions).
Use `WORKING_GRACE=30` for new sessions since Claude Code takes a moment to start.

### 7i — Report to user

- Branch: `<branch>`
- Worktree: `$PARENT_NATIVE/<slug>`
- Tmux session: `<slug>` — attach with `$TMUX_EXEC attach -t <slug>`
- Agent is running with the task prompt

---

## Notes

- Session names are capped at 40 chars by the slug rule in Step 7a
- The Claude Code pane is always window 0, pane 0 unless the user specifies otherwise
- When a session has multiple windows, check window 0 for the agent; note other windows
  separately if they show interesting activity (build output, test results)
- Never kill or restart a session without explicit user confirmation
- If tmux is not found at all (neither native nor via `wsl tmux`), report that tmux must
  be installed and stop
