#!/usr/bin/env python3
"""Report where a Markdown draft breaks the Simple Technical English rules in SKILL.md.

Checks: sentence length (20 words for an instruction, 25 otherwise), paragraph length
(6 sentences), noun-cluster length (3 words, approximated by runs of capitalised or
hyphenated nouns), and the unapproved-word table, extended with the shared glossary's
unconditional Avoid spellings when skills/slang-glossary is present. Code blocks, inline code, headings,
tables, URLs and link targets are skipped. Prints one finding per line as
``line N: <rule>: <fix>``; exits 0, or 1 with ``--enforce`` when there are findings.
"""

from __future__ import annotations

import argparse
import os
import re
import sys

MAX_INSTRUCTION_WORDS = 20
MAX_SENTENCE_WORDS = 25
MAX_PARAGRAPH_SENTENCES = 6

UNAPPROVED = [
    (r"\butili[sz]e[sd]?\b", "use"),
    (r"\bleverag(e|es|ed|ing)\b", "use"),
    (r"\bcommenc(e|es|ed|ing)\b", "start"),
    (r"\binitiat(e|es|ed|ing)\b", "start"),
    (r"\bensur(e|es|ed|ing)\b", "make sure"),
    (r"\bprior to\b", "before"),
    (r"\bsubsequent to\b", "after"),
    (r"\bin order to\b", "to"),
    (r"\bapproximately\b", "about"),
    (r"\bfacilitat(e|es|ed|ing)\b", "help"),
    (r"\bterminat(e|es|ed|ing)\b", "stop"),
    (r"\bit is worth noting\b", "delete it; say the thing"),
    (r"\b(please )?note that\b", "delete it; say the thing"),
    (r"\bin this section,? we will\b", "delete it"),
    (r"\b(robust|comprehensive|seamless(ly)?|powerful|elegant)\b", "delete it; give the fact it stood for"),
    (r"\bit is (imperative|important|essential) (that|to)\b", "delete it; write the instruction"),
]
UNAPPROVED_RE = [(re.compile(p, re.IGNORECASE), fix) for p, fix in UNAPPROVED]

# The shared glossary (skills/slang-glossary) adds project words to the table: every
# unconditional `_Avoid_` spelling becomes an unapproved word whose fix is the canonical
# term. A conditional entry, one with a qualifier in parentheses such as "capability (when
# one atom is meant)", depends on the sense and stays guidance in the glossary text.
GLOSSARY_TERM_RE = re.compile(r"^\*\*(.+?)\*\*:\s*$")
GLOSSARY_AVOID_RE = re.compile(r"^_Avoid_:\s*(.*)$")


def default_glossary_dir() -> str | None:
    env = os.environ.get("SLANG_GLOSSARY_DIR")
    if env:
        return env
    here = os.path.dirname(os.path.abspath(__file__))
    candidate = os.path.normpath(os.path.join(here, "..", "..", "slang-glossary"))
    return candidate if os.path.isdir(candidate) else None


def split_avoid(text: str) -> list[str]:
    """Comma-separated entries, commas inside parentheses kept."""
    out, depth, cur = [], 0, ""
    for ch in text:
        depth += ch == "("
        depth -= ch == ")"
        if ch == "," and depth == 0:
            out.append(cur.strip())
            cur = ""
        else:
            cur += ch
    if cur.strip():
        out.append(cur.strip())
    return out


def glossary_unapproved(glossary_dir: str) -> list[tuple[re.Pattern, str]]:
    """(pattern, fix) for every unconditional Avoid spelling under `glossary_dir`'s GLOSSARY.md files."""
    terms_by_pattern: dict[str, list[str]] = {}
    for root, _dirs, files in os.walk(glossary_dir):
        if "GLOSSARY.md" not in files:
            continue
        term = None
        with open(os.path.join(root, "GLOSSARY.md"), encoding="utf-8") as fh:
            for raw in fh:
                m = GLOSSARY_TERM_RE.match(raw.strip())
                if m:
                    term = m.group(1)
                    continue
                m = GLOSSARY_AVOID_RE.match(raw.strip())
                if not m or not term:
                    continue
                for entry in split_avoid(m.group(1)):
                    if "(" in entry:
                        continue
                    words = [re.escape(w) for w in entry.split()]
                    if not words:
                        continue
                    pattern = r"(?<![\w-])" + r"\s+".join(words) + r"(?![\w-])"
                    names = terms_by_pattern.setdefault(pattern.lower(), [])
                    if term not in names:
                        names.append(term)
    # One finding per spelling: a word two terms both avoid names both of them.
    return [(re.compile(pat, re.IGNORECASE), "the glossary says " + " or ".join(names)) for pat, names in terms_by_pattern.items()]

CODE_SPAN_RE = re.compile(r"`[^`]*`")
URL_RE = re.compile(r"https?://\S+")
LINK_TARGET_RE = re.compile(r"\]\([^)]*\)")
SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z`(\"'])")
IMPERATIVE_RE = re.compile(
    r"^(Run|Use|Add|Remove|Set|Call|Compile|Build|Open|Close|Check|Make|Do|Write|Read|Keep|Put|Move|Delete|Start|Stop|Pass|Give|See|Install|Create|Update|Load|Save|Select|Click|Copy|Paste|Test|Verify|Confirm|Replace|Rename|Edit|Apply|Enable|Disable|Push|Pull|Merge|Rebase|Commit|Avoid|Prefer)\b"
)
NOUN_CLUSTER_RE = re.compile(r"\b(?:[A-Z][a-z]+(?:-[a-z]+)?\s+){3,}[A-Z][a-z]+\b")


def strip_markup(line: str) -> str:
    line = CODE_SPAN_RE.sub("`x`", line)
    line = URL_RE.sub("url", line)
    line = LINK_TARGET_RE.sub("]", line)
    return line


def words(sentence: str) -> int:
    return len([w for w in re.findall(r"[A-Za-z0-9'’-]+", sentence) if w != "x"])


def check_text(text: str, extra: list[tuple[re.Pattern, str]] | None = None) -> list[tuple[int, str]]:
    findings: list[tuple[int, str]] = []
    in_code = False
    para_sentences = 0
    para_start = 0
    all_lines = text.split("\n")
    # Skip YAML frontmatter (a leading `---` block).
    skip_until = 0
    if all_lines and all_lines[0].strip() == "---":
        skip_until = next((i for i in range(1, len(all_lines)) if all_lines[i].strip() == "---"), 0)
    for n, raw in enumerate(all_lines, 1):
        if n <= skip_until + 1 and skip_until:
            continue
        if raw.strip().startswith("```"):
            in_code = not in_code
            continue
        if in_code or raw.lstrip().startswith(("#", "|", ">", "<")) or raw.strip() == "---":
            continue
        if not raw.strip():
            if para_sentences > MAX_PARAGRAPH_SENTENCES:
                findings.append((para_start, f"paragraph has {para_sentences} sentences, max {MAX_PARAGRAPH_SENTENCES}: split it, one topic each"))
            para_sentences = 0
            continue
        is_item = bool(re.match(r"^\s*(?:[-*+]|\d+[.)])\s+", raw))
        if is_item:
            # Each list item is its own paragraph.
            if para_sentences > MAX_PARAGRAPH_SENTENCES:
                findings.append((para_start, f"paragraph has {para_sentences} sentences, max {MAX_PARAGRAPH_SENTENCES}: split it, one topic each"))
            para_sentences = 0
        if para_sentences == 0:
            para_start = n
        line = strip_markup(re.sub(r"^\s*(?:[-*+]|\d+[.)])\s+", "", raw.strip()))
        for sentence in SENTENCE_SPLIT_RE.split(line):
            if not sentence.strip():
                continue
            para_sentences += 1
            n_words = words(sentence)
            limit = MAX_INSTRUCTION_WORDS if IMPERATIVE_RE.match(sentence) else MAX_SENTENCE_WORDS
            if n_words > limit:
                findings.append((n, f"sentence has {n_words} words, max {limit}: split it"))
            for rx, fix in UNAPPROVED_RE + (extra or []):
                m = rx.search(sentence)
                if m:
                    findings.append((n, f"unapproved word '{m.group(0)}': {fix}"))
            m = NOUN_CLUSTER_RE.search(sentence)
            if m:
                findings.append((n, f"noun cluster '{m.group(0)}' is longer than 3 words: split it with 'of' or a verb"))
    if para_sentences > MAX_PARAGRAPH_SENTENCES:
        findings.append((para_start, f"paragraph has {para_sentences} sentences, max {MAX_PARAGRAPH_SENTENCES}: split it, one topic each"))
    return findings


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("path", nargs="?")
    ap.add_argument("--stdin", action="store_true")
    ap.add_argument("--enforce", action="store_true")
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--glossary", help="directory holding the shared GLOSSARY.md files (default: skills/slang-glossary next to this skill, or $SLANG_GLOSSARY_DIR)")
    ap.add_argument("--no-glossary", action="store_true", help="check without the glossary's Avoid spellings")
    args = ap.parse_args(argv)
    glossary_dir = None if args.no_glossary else (args.glossary or default_glossary_dir())
    extra = glossary_unapproved(glossary_dir) if glossary_dir and os.path.isdir(glossary_dir) else []
    if args.self_test:
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            os.makedirs(os.path.join(td, "ctx"))
            with open(os.path.join(td, "ctx", "GLOSSARY.md"), "w", encoding="utf-8") as fh:
                fh.write("# Ctx\n\n## Language\n\n**Borrow-in parameter**:\nA parameter.\n_Avoid_: ConstRef, const ref, capability (when one atom is meant)\n")
            table = glossary_unapproved(td)
            assert len(table) == 2, table
            f = check_text("The ConstRef path and a const  ref value.\n", table)
            assert len(f) == 2 and all("Borrow-in parameter" in m for _, m in f), f
            assert check_text("A capability is fine. `ConstRef` in code is fine.\n", table) == []
        bad = "It is imperative that the user ensures the module has been compiled prior to invoking the reflection API in order to avoid comprehensive validation failures.\n"
        f = check_text(bad)
        assert any("imperative" in m for _, m in f) and any("ensures" in m for _, m in f) and any("prior to" in m for _, m in f), f
        assert check_text("Compile the module before you call the reflection API. An uncompiled module fails validation.\n") == []
        assert check_text("```\nIt is imperative that x.\n```\n`ensure` is a word.\n") == []
        assert check_text("---\ndescription: It is imperative. A. B. C. D. E. F. G.\n---\nFine.\n") == []
        print("ok")
        return 0
    text = sys.stdin.read() if args.stdin or not args.path else open(args.path, encoding="utf-8").read()
    findings = check_text(text, extra)
    for n, msg in findings:
        print(f"line {n}: {msg}")
    if not findings:
        print("STE: no findings")
    return 1 if findings and args.enforce else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
