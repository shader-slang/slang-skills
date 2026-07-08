#!/usr/bin/env bash
# Fetch Devin Review's analysis for a public GitHub PR via agent-browser.
# Output: <out>/devin-flags.md (extracted Bugs + Flags + commit-status freshness + Devin's narrative)
#
# Usage:
#   devin-fetch.sh --url <devin-review-url> --out <run-dir> [--poll-seconds 45] [--max-minutes 30]
#
# Returns 0 on success, 2 on auth-wall, 3 on timeout, 1 on any other error.
# The workflow treats failure as best-effort — Reviewer A still runs.

set -euo pipefail

URL=""
OUT=""
POLL=45
MAX_MIN=30

while (($#)); do
  case "$1" in
    --url) URL="$2"; shift 2 ;;
    --out) OUT="$2"; shift 2 ;;
    --poll-seconds) POLL="$2"; shift 2 ;;
    --max-minutes) MAX_MIN="$2"; shift 2 ;;
    *) echo "error: unknown flag $1" >&2; exit 1 ;;
  esac
done

[ -n "$URL" ] || { echo "error: --url required" >&2; exit 1; }
[ -n "$OUT" ] || { echo "error: --out required" >&2; exit 1; }
mkdir -p "$OUT"

# Normalize URL. Accept either a GitHub PR URL
# (https://github.com/<owner>/<repo>/pull/<n>) — which is what /slang-pr-review
# Step 2 produces — or an already-Devin URL
# (https://app.devin.ai/review/<owner>/<repo>/pull/<n>). If the input is GitHub,
# rewrite to the Devin review form so agent-browser opens the right page.
if [[ "$URL" =~ ^https?://github\.com/([^/]+)/([^/]+)/pull/([0-9]+) ]]; then
  OWNER="${BASH_REMATCH[1]}"
  REPO="${BASH_REMATCH[2]}"
  PR_NUM="${BASH_REMATCH[3]}"
  URL="https://app.devin.ai/review/${OWNER}/${REPO}/pull/${PR_NUM}"
  echo ">>> devin-fetch: rewrote GitHub URL → ${URL}"
fi

agent-browser open "$URL"
sleep 5

# Detect auth wall before polling. Use a tight regex that targets phrases unique
# to an auth-walled state (login modal / banner) — NOT a generic "sign in"
# substring, which fires false-positive on Devin's navbar "Sign in" link even
# when the page is otherwise loading content normally. The `i` flag in JS regex
# is case-insensitive; `\b` ensures whole-word match.
if agent-browser eval '(() => { const t=document.body.innerText; return /\b(log in to (?:view|access)|sign in to (?:view|access)|authentication required|please (?:log|sign) in to (?:view|access|continue))\b/i.test(t); })()' 2>/dev/null | grep -qi true; then
  echo "auth-wall: Devin requires login for this PR" > "$OUT/devin-error.txt"
  exit 2
fi

# Poll until analysis is done. Devin's UI does NOT render a literal
# "Analysis complete" string when finished — the in-progress state shows
# "PR analysis in progress" and the done state shows the "Devin's AI
# analysis" heading plus a Bugs/Flags summary ("N Bugs"/"N Flags"/"No
# flags") and/or the checks panel ("All checks passed"/"checks failed"
# /"Checks <pass>/<total>"). Treat absence-of-progress + presence-of-result
# as "done". The Bugs/Flags split is a 2026 UI change — previously these
# were a single "N Flags" toggle.
DONE_EXPR='(() => {
  const t = document.body.innerText;
  if (/PR analysis in progress/i.test(t)) return false;
  // The "Devin.s AI analysis" heading and a "No bugs"/"No flags" summary can
  // render while the panel is still streaming — it shows a "Generating…"/
  // "Generating..." placeholder and echoes the PR description. That is NOT a
  // finished verdict, so treat a still-streaming marker as NOT done and keep
  // polling (worst case → timeout, a best-effort skip). Guards against the
  // devin-fetch premature exit-0 incidents where a half-rendered page was
  // folded into the review as "clean".
  if (/Generating\s*(\.{2,}|…)/i.test(t)) return false;
  if (!/Devin.s AI analysis/i.test(t)) return false;
  return /\b\d+\s+Bugs?\b/.test(t) || /\b\d+\s+Flags?\b/.test(t) || /\bNo (bugs|flags)\b/i.test(t) || /All checks passed/i.test(t) || /checks? failed/i.test(t) || /Checks\s*\d+\s*\/\s*\d+/i.test(t);
})()'

deadline=$(( $(date +%s) + MAX_MIN*60 ))
while [ "$(date +%s)" -lt "$deadline" ]; do
  if agent-browser eval "$DONE_EXPR" 2>/dev/null | grep -qi true; then
    break
  fi
  sleep "$POLL"
done

# Confirm complete (else timeout)
if ! agent-browser eval "$DONE_EXPR" 2>/dev/null | grep -qi true; then
  echo "timeout: Devin did not complete within ${MAX_MIN}m" > "$OUT/devin-error.txt"
  exit 3
fi

# Capture commit-status freshness BEFORE expanding panels (clicking other
# buttons can dismiss this popover). The header has a button labeled
# "Commit status"; clicking it opens a popover whose first line is one of
# "Analysis is up to date", "Analysis is out of date", "Analysis is
# behind" — followed by the commit list. We capture the first line into
# devin-commit-status.txt so the reviewer can caveat against force-push.
agent-browser eval '(() => {
  const btn = document.querySelector("button[aria-label=\"Commit status\"]");
  if (!btn) return "no-button";
  btn.click();
  return "clicked";
})()' >/dev/null 2>&1 || true
sleep 1
agent-browser eval '(() => {
  const popups = Array.from(document.querySelectorAll("[data-state=open], [role=tooltip], [role=dialog], [class*=popover]"));
  for (const el of popups) {
    const txt = (el.textContent || "").trim();
    const m = txt.match(/^Analysis is (up to date|out of date|behind|stale|ahead)/i);
    if (m) return m[0];
  }
  return "unknown";
})()' 2>/dev/null > "$OUT/devin-commit-status.txt" || true
# Close the popover by pressing Escape so the next click lands on Bugs/Flags.
agent-browser press Escape >/dev/null 2>&1 || true
sleep 1

# Expand both the Bugs and Flags panels. The 2026 UI splits these into
# two adjacent buttons ("N Bugs", "N Flags") instead of a single combined
# toggle. Click every matching button so neither panel is missed; also
# accept the legacy combined "<N> Flags / 1 Flag / No flags" form for
# back-compat with older Devin instances.
agent-browser eval '(() => {
  const targets = Array.from(document.querySelectorAll("button")).filter(
    (b) => /^(\d+\s+(Bugs?|Flags?)|No (bugs|flags))$/i.test((b.textContent || "").trim())
  );
  targets.forEach((b) => b.click());
  return targets.length;
})()' >/dev/null 2>&1 || true
sleep 2

# Extract narrative + flags. agent-browser eval emits a JSON-encoded string
# (the body text wrapped in quotes with literal \n escapes), so decode it back
# to a plain text file before parsing — otherwise newline-anchored regexes in
# the section splitter never match.
agent-browser eval 'document.body.innerText' 2>/dev/null \
  | python3 -c "import json,sys; raw=sys.stdin.read().strip(); print(json.loads(raw) if raw.startswith('\"') else raw)" \
  > "$OUT/devin-page.txt"
agent-browser screenshot "$OUT/devin-screenshot.png" 2>/dev/null || true

# Build a clean markdown extract: commit-status freshness + AI analysis + bugs + flags.
# Splits the page text on the section headers Devin renders. The legacy
# split was on "\n\s*\d+\s*Flags?\s*\n" which only matched the old combined
# Flags toggle — the 2026 UI has separate "N Bugs" and "N Flags" lines, so
# we walk both. The split is heuristic (Devin doesn't render machine-readable
# section markers); it falls back to the full page text if the headers move.
python3 - "$OUT/devin-page.txt" "$OUT/devin-commit-status.txt" > "$OUT/devin-flags.md" <<'PY'
import re, sys
from pathlib import Path

text = open(sys.argv[1]).read()
status = ""
if len(sys.argv) > 2:
    p = Path(sys.argv[2])
    if p.exists():
        status = p.read_text().strip().strip('"')

# Section split. Headers we care about (in order they appear on the page):
#   "Devin's AI analysis"   - prose narrative
#   "<N> Bugs" / "No bugs"  - bug list (2026 UI)
#   "<N> Flags" / "No flags"- flag list (2026 UI; also legacy combined name)
# Build a regex that captures section starts; walk matches to slice the body.
HEADER_RE = re.compile(
    r"\n\s*("
    r"Devin.s AI analysis"
    r"|\d+\s+Bugs?"
    r"|No bugs"
    r"|\d+\s+Flags?"
    r"|No flags"
    r")\s*\n",
    re.IGNORECASE,
)

# Find all header positions in the page text.
heads = [(m.start(), m.end(), m.group(1)) for m in HEADER_RE.finditer(text)]
sections = {}
ZERO_RE = re.compile(r"^(0\s+(Bugs?|Flags?)|No (bugs|flags))$", re.IGNORECASE)
for i, (s, e, name) in enumerate(heads):
    end = heads[i + 1][0] if i + 1 < len(heads) else len(text)
    body = text[e:end].strip()
    key = name.lower()
    # When the header itself indicates zero entries (e.g. "0 Bugs", "No flags"),
    # the content after it is sidebar/nav junk — explicitly emit a sentinel
    # so callers don't think the trailing labels are bug/flag bodies.
    if ZERO_RE.match(name.strip()):
        body = "(none reported)"
    if "ai analysis" in key:
        sections.setdefault("analysis", body)
    elif "bug" in key:
        sections.setdefault("bugs", body)
    elif "flag" in key:
        sections.setdefault("flags", body)

# Fall back: if no analysis header found, use whatever's before the first
# Bugs/Flags header, or the full text.
if "analysis" not in sections:
    if heads:
        sections["analysis"] = text[: heads[0][0]].strip()
    else:
        sections["analysis"] = text.strip()

print("# Devin Review\n")
if status and status.lower() != "unknown":
    print(f"_Commit status: **{status}**_\n")
print("## AI Analysis\n")
print(sections.get("analysis", "")[:5000])
print("\n## Bugs\n")
print(sections.get("bugs", "(none reported)")[:5000])
print("\n## Flags\n")
print(sections.get("flags", "(none reported)")[:5000])
PY

# Body-integrity guard: require a terminal status AND a non-trivial body before
# declaring success. A reachable page can pass the DONE poll while the panel is
# still streaming ("Generating…"/"Generating...") — the AI-Analysis section is
# then just the PR description echoed back with Bugs/Flags "(none reported)",
# which reads like a clean pass but is an *incomplete* analysis. Also guard
# against a truly empty scrape. Either case → inconclusive (exit 3, best-effort
# skip), never a silent exit-0 "clean" that folds a half-rendered page into the
# review. DEVIN_MIN_BYTES overrides the 200-byte floor.
if grep -qE 'Generating[[:space:]]*(\.{2,}|…)' "$OUT/devin-flags.md" 2>/dev/null; then
  echo "inconclusive: Devin analysis still generating at scrape time" > "$OUT/devin-error.txt"
  echo ">>> devin-fetch: still generating at scrape time — inconclusive (exit 3)" >&2
  exit 3
fi
ANALYSIS_BYTES=$(wc -c < "$OUT/devin-flags.md" 2>/dev/null | tr -d ' ')
: "${ANALYSIS_BYTES:=0}"
if [ "$ANALYSIS_BYTES" -lt "${DEVIN_MIN_BYTES:-200}" ]; then
  echo "inconclusive: Devin analysis body too short (${ANALYSIS_BYTES}B)" > "$OUT/devin-error.txt"
  echo ">>> devin-fetch: body too short (${ANALYSIS_BYTES}B) — inconclusive (exit 3)" >&2
  exit 3
fi

echo ">>> devin-fetch: ${OUT}/devin-flags.md ($(wc -l < "$OUT/devin-flags.md") lines)"
