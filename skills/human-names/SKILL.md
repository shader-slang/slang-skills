---
name: human-names
description: >-
  Use whenever output will name a specific person: release notes, changelogs,
  contributor lists, commit or PR attribution, code comments, issue and review
  replies, docs credits, or any prose referring to a human. Governs where a name
  may come from and how to choose pronouns, so stale names from git history and
  gender guesses from model priors never reach the output.
---

# Naming people

## Names

Never write a human name recalled from training. Before using one, be able to say where it came from. If you cannot name the source, you do not have the name.

Resolve in this order:

1. If the context offers a lookup mechanism (profile API, directory, MCP tool, config file), use it.
2. In a git repository, `.mailmap` on the **default branch** overrides the author and committer fields of any commit. Commit metadata is a historical record, not a current identity.
3. If the name is still unknown, use the username or handle. A handle is always correct; a guessed name is not.

## Pronouns

Establish the human name first, then:

1. If pronouns were provided, use those.
2. Otherwise, if you have the human name and can infer pronouns from it with high confidence, use those.
3. Otherwise, use they/them.
