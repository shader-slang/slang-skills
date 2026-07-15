Generate a daily report draft for the Slang project. The report should be concise but comprehensive.

## Arguments (optional — defaults match the classic daily sweep)

- **time-range** — how far back to look. Default **`24h`**. Forms: `Nm` (minutes), `Nh` (hours), `Nd` (days) — e.g. `30m`, `48h`, `7d`.
- **output** — where the report goes. Default **`file`**. One of `file` | `terminal` | `both`.

Today's date is provided in the system context. Compute the window start `SINCE` (ISO 8601) by subtracting `time-range` from now — e.g. today `2026-02-17` with `time-range=24h` → `SINCE = "2026-02-16T00:00:00Z"`. Double-check the year is correct. Use `SINCE` everywhere a `since=` filter appears below.

Discord has no server-side time filter, so scale the fetch `limit` to the range and **filter client-side** to messages with `timestamp >= SINCE`:

| time-range | Discord `limit` |
|------------|-----------------|
| ≤ 60m      | 20 |
| ≤ 24h      | 50 (default) |
| ≤ 3d       | 100 |
| > 3d       | 100 — note in the report that results may be incomplete (API max is 100/channel) |

---

## Data Collection Instructions

You MUST query ALL of the following data sources. Make parallel calls where possible.

### 1. GitHub (owner: "shader-slang", repo: "slang")

**Issues — fetch ALL from the time range:**
- `github_list_issues` with state=OPEN, first=100, since=<SINCE>
  - If `hasNextPage` is true in the response, call again with `after=<endCursor>` and repeat until `hasNextPage` is false
- `github_list_issues` with state=CLOSED, first=100, since=<SINCE>
  - Same pagination logic

**Pull Requests — fetch recent activity:**
- `github_list_pull_requests` with state=open, per_page=30, sort=updated, direction=desc
- `github_list_pull_requests` with state=closed, per_page=30, sort=updated, direction=desc
- Additionally, use `github_search_issues` with q="repo:shader-slang/slang is:pr updated:>=YYYY-MM-DD" to catch any PRs missed by the list (replace YYYY-MM-DD with `SINCE`'s date)

**Discussions:**
- `github_get_discussions` with owner=shader-slang, repo=slang, first=10

### 2. GitLab (project_id: "6417")

- `gitlab_list_issues` with project_id="6417", state=opened, per_page=20, order_by=updated_at
- `gitlab_list_merge_requests` with project_id="6417", state=opened, per_page=20, order_by=updated_at

### 3. Discord (fetch ALL configured channels in parallel)

Call `discord_read_messages` with the range-scaled `limit` (see the table above) for each configured Discord channel, then filter client-side to messages with `timestamp >= SINCE`.

### 4. Slack

- `slack_get_channel_history` with the configured Slack channel_id, limit=100, since=<SINCE>

### 5. User ID Resolution

After collecting all data, gather all unique Slack user IDs found in messages.
- Resolve each via `slack_get_user_profile` — call them **sequentially** (not in parallel) to avoid rate limits
- The tool has built-in retry logic for rate limits, but spacing calls out helps

---

## Report Structure

### 1. Urgent Matters (limit to 3, prioritized):
   - 🚨 Critical issues requiring immediate attention
   - ⚠️ Blocking issues affecting team/development
   - 🔄 Time-sensitive updates/changes
   Include clear action items or owners when available

### 2. GitHub Activity (within the time range):
   - New issues opened: [number] with issue title and URL
   - Issues/PRs closed: [number] with title and URL
   - PRs requiring review: [number] with title and URL
   - Add 🚨 for high-priority items
   - Don't create tables, use only lists

### 3. GitLab Activity:
   - Open issues (notable/recent)
   - Open merge requests
   - Include links using GitLab base URL

### 4. Key Discussions (limit to 3 most impactful):
   - From Slack threads, Discord channels, and GitHub Discussions
   - Technical decisions/changes
   - Architecture discussions
   - Team process updates
   Include relevant context and next steps if any

### 5. Progress Updates:
   - Active Development:
     • Major features/changes in progress
     • Notable achievements/milestones
   - Infrastructure:
     • Build/CI status
     • Test results
     • System health indicators (nightly statuses from Slack)

### 6. Notes & Reminders:
   - Important announcements
   - Upcoming deadlines
   - Best practices/guidelines to follow

---

## Format Requirements
- Use clear hierarchical headings (##, ###)
- Use Unicode emoji characters (e.g. 🚨 ✅ ❌ ⚠️ 🔄), NOT Slack/GitHub shortcode style (e.g. :rotating_light: :white_check_mark:) — shortcodes only render on Slack/GitHub, not in markdown viewers or terminals
- Resolve user ids to names and email addresses when correlating identities across GitHub/Slack/etc.
- Include direct links to referenced items
- Keep tone professional but conversational
- Use bullet points for easy scanning
- Highlight action items or decisions needed
- Add timestamp of report generation

Only use full names and usernames which are present in the input data. If both are found, prefer full names.

## Output (honor the `output` argument; default `file`)

- **`file`** (default): save the report as `daily-report-YYYY-MM-DD.md` (date = `SINCE`'s date). If a report with that name already exists, overwrite it with the new version (append a `_updated` suffix only if you need to preserve both versions). Print the saved path.
- **`terminal`**: print the full report to the terminal only — do not write a file.
- **`both`**: print the full report AND save it (same path as `file`).

## Post to Slack (optional)

After the report is ready, **ask the user** whether to post it to Slack (use `AskUserQuestion`; default to **not** posting). Only if the user confirms, post in **two steps** so the channel stays scannable and the full report lives in a thread:

1. **Channel parent (short)** — `mcp__slang-mcp__slack_post_message` to the configured Slack channel (same channel used for collection; do **not** hardcode a channel ID inline — see [gotchas.md](./gotchas.md) → Configuration). Keep this to 1–3 lines, e.g. report date, time range, and a one-line highlight from **Urgent Matters** (or "nothing urgent" if empty). Example shape: `📋 Slang daily report — YYYY-MM-DD (last 24h) — 🚨 1 urgent item (see thread)`.
2. **Thread reply (full report)** — `mcp__slang-mcp__slack_reply_to_thread` with the same `channel_id`, `thread_ts` set to the parent message's `ts` from step 1, and `text` set to the full report body.

If step 1 succeeds but step 2 fails, tell the user the parent was posted and retry or paste the report manually into that thread. If the report exceeds Slack's message limit, split it across multiple thread replies in order (same `thread_ts`).

---

## Completeness Checklist

Before saving the report, verify you queried:
- [ ] GitHub issues (open + closed, with pagination)
- [ ] GitHub PRs (open + closed)
- [ ] GitHub Discussions
- [ ] GitLab issues and merge requests (project 6417)
- [ ] All configured Discord channels (range-scaled limit, client-side `>= SINCE` filter)
- [ ] Slack channel history (with `since=SINCE` filter)
- [ ] All Slack user IDs resolved to names

If any source failed or returned an error, note it in the report under "Data Collection Notes" at the bottom.
