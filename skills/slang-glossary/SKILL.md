---
name: slang-glossary
license: Apache-2.0
description: "The shared vocabulary of the Slang ecosystem: one GLOSSARY.md per bounded context (Slang compiler, Slang language, SlangPy, slang-rhi, coworker operations) with canonical terms, short meanings and the spellings to avoid, plus the map that relates the contexts. Load it before writing or reviewing text about Slang: PR descriptions, review comments, issue replies, plans, explanations."
allowed-tools: Read
---

# Slang glossary

Every context has its own `GLOSSARY.md`; `GLOSSARY-MAP.md` lists them and the open ambiguities. The glossary follows the `domain-modeling` format: one canonical term, a one or two sentence meaning, and an `_Avoid_` list.

How to use it:

- Start at `GLOSSARY-MAP.md` and open the context your text belongs to. Compiler changes use the compiler glossary; user-facing text uses the language glossary.
- Write the canonical term in prose. Put a code identifier in backticks only when the identifier itself is meant.
- Never write a spelling listed under `_Avoid_`. An entry with a qualifier in parentheses applies only in that sense.
- When a concept has no entry, use the word the surrounding code and docs use. Say so in the PR text, so the term can be added.

The STE checker (`skills/slang-ste-writing/scripts/ste_check.py`) reads these files. It reports every unconditional Avoid spelling as an unapproved word. `EVIDENCE.md` records the usage counts behind each Avoid entry.
