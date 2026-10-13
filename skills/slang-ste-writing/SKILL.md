---
name: slang-ste-writing
license: Apache-2.0
description: "Writing rules for text that other people read: PR descriptions, issues, review and status comments, Discord and Slack posts, user documentation. A working subset of ASD-STE100 (Simplified Technical English), about 80% of the specification, with the unapproved words that generated text uses most. Load before posting any of those, or run /slang-ste-writing on a draft."
argument-hint: "[path-to-draft | --stdin]"
allowed-tools: Read Bash
---

# Simple Technical English for Slang

Text that other people read is written for the reader. The rules below are the part of ASD-STE100 that fits a compiler project:

- short sentences;
- one topic per paragraph;
- the same word for the same thing;
- active voice for instructions;
- a short list of words we do not use.

Identifiers, code spans and technical names are exempt from every rule.

Load this skill before you write a PR description, an issue, a comment, a chat post, or a documentation page. On a finished draft, run `scripts/ste_check.py <file>`. It reports; it does not block.

## Limits

| Unit | Limit |
| --- | --- |
| Instruction (imperative) sentence | 20 words |
| Descriptive sentence | 25 words |
| Paragraph | 6 sentences, one topic |
| Noun cluster (nouns in a row) | 3 words; split longer ones with "of" or a verb |
| Instructions in one sentence | 1, unless the actions are simultaneous |

Words inside backticks, URLs, numbers and identifiers do not count.

## Verb forms

Approved: the command form (`Compile the module.`), simple present, past and future, the infinitive, and the past participle as an adjective (`the compiled module`).

Not approved: the `-ing` form outside a technical name, and the perfect tenses (`has compiled`). An instruction is never passive: `the module must be compiled` becomes `compile the module`. Descriptive text may use the passive when the actor does not matter.

## Style

- Keep the articles: `the`, `a`, `this`. Do not write telegram style.
- Use the same word for the same thing every time. Do not vary for elegance.
- Put the instruction first and the condition second: `Run the tests before you push.`
- Use a vertical list when a sentence would carry more than two items.
- One idea per sentence; an example before its explanation; no preview of what the text is about to say.
- State the risk, then the consequence, when you warn: `Do not edit the generated file. The next build overwrites it.`

## Words we do not use

| Instead of | Write |
| --- | --- |
| utilize, leverage | use |
| commence, initiate | start |
| ensure | make sure |
| prior to | before |
| subsequent to | after |
| in order to | to |
| approximately | about |
| facilitate | help |
| terminate | stop, end |
| it is worth noting, please note, note that | (delete; say the thing) |
| in this section we will | (delete) |
| robust, comprehensive, seamless, powerful, elegant | (delete; give the fact the adjective stood for) |
| it is imperative that, it is important to | (delete; write the instruction) |

## Example

Not STE:

> It is imperative that the user ensures the module has been compiled prior to invoking the reflection API in order to avoid comprehensive validation failures.

STE:

> Compile the module before you call the reflection API. An uncompiled module fails validation.

## What we relax (the 20%)

ASD-STE100 allows about 900 general words plus a company dictionary. We do not enforce the dictionary: any word a Slang user knows is approved. Descriptive text may use the passive. Words inside code spans, links and identifiers do not count. The checker enforces only the limits and the word table above.

## Checker

```
python3 scripts/ste_check.py draft.md        # report
cat draft.md | python3 scripts/ste_check.py --stdin
python3 scripts/ste_check.py draft.md --enforce   # exit 1 on findings (for hooks)
```

Each finding names the line, the rule and the fix. Markdown headings, code blocks, tables and link targets are skipped.
