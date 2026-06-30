---
name: slang-maintainer-tools
license: MIT
description: "Bridge from /slang-maintain workflow steps to concrete slang-mcp tool calls. Read-only except an optional, user-confirmed post of the generated daily report to Slack. Task recipes live in sibling files."
provides: []
argument-hint: "[task: daily-report|release-notes|issue-prioritization|review-messages] [time-range: 24h|7d] [output: file|terminal|both]"
allowed-tools: Read Write Edit Grep Glob AskUserQuestion mcp__slang-mcp__github_list_pull_requests mcp__slang-mcp__github_get_pull_request mcp__slang-mcp__github_get_pull_request_comments mcp__slang-mcp__github_get_pull_request_reviews mcp__slang-mcp__github_list_issues mcp__slang-mcp__github_search_issues mcp__slang-mcp__github_get_issue mcp__slang-mcp__github_get_discussions mcp__slang-mcp__gitlab_list_merge_requests mcp__slang-mcp__gitlab_list_issues mcp__slang-mcp__gitlab_get_file_contents mcp__slang-mcp__discord_read_messages mcp__slang-mcp__slack_get_channel_history mcp__slang-mcp__slack_get_user_profile mcp__slang-mcp__slack_post_message
---

# Slang Maintainer Tools

Bridges `/slang-maintain` (WHAT) to concrete `slang-mcp` calls (HOW). Read-only, except `daily-report` may optionally post its finished report to Slack after explicit user confirmation.

## Pick a task

| Task | Recipe |
|------|--------|
| `daily-report`          | [daily-report.md](./daily-report.md) |
| `release-notes`         | [release-notes.md](./release-notes.md) |
| `issue-prioritization`  | [issue-prioritization.md](./issue-prioritization.md) |
| `review-messages`       | [review-messages.md](./review-messages.md) |

Each recipe is self-contained: data sources, pagination rules, output template.

## Step bridge

| `/slang-maintain` step | Where to look |
|------------------------|---------------|
| **Collect**     | the task's recipe file — "Data Collection" section |
| **Synthesize**  | the task's recipe file — categorization / dedup rules |
| **Deliver**     | the task's recipe file — "Report Structure" or "Output Format" |

Cross-cutting pitfalls (rate limits, pagination, user-id resolution, squash-merge quirks): [gotchas.md](./gotchas.md).
