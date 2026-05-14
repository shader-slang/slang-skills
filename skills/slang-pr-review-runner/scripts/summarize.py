#!/usr/bin/env python3
"""Summarize a slang-pr-review run directory.

Reads stream.jsonl, final-review.md, and the preserved subagent outputs.
Emits severity counts, per-subagent cost attribution, total cost, and a
drift signal: GitHub-write tool attempts must be 0 (the skill is
read-only). Non-zero indicates the allowlist leaked.
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path


def load_stream(stream_path: Path) -> list[dict]:
    events: list[dict] = []
    if not stream_path.exists():
        return events
    for line in stream_path.read_text().splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            events.append(json.loads(line))
        except Exception:
            continue
    return events


def severity_counts(text: str) -> dict[str, int]:
    """Count severity badges in markdown. Authoritative count is the Verdict line."""
    if not text:
        return {"bug": 0, "gap": 0, "question": 0}
    return {
        "bug": len(re.findall(r"🔴\s*\*\*Bug\*\*", text)),
        "gap": len(re.findall(r"🟡\s*\*\*Gap\*\*", text)),
        "question": len(re.findall(r"🔵\s*\*\*Question\*\*", text)),
    }


def parse_verdict_line(text: str) -> tuple[int, int, int] | None:
    """Find the 'Verdict: ... N bug(s), M gap(s), K question(s)' line if present."""
    if not text:
        return None
    m = re.search(
        r"\*\*Verdict\*\*.*?(\d+)\s*bug.*?(\d+)\s*gap(?:.*?(\d+)\s*question)?",
        text, re.IGNORECASE | re.DOTALL,
    )
    if not m:
        return None
    return (
        int(m.group(1) or 0),
        int(m.group(2) or 0),
        int(m.group(3) or 0),
    )


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: summarize.py <run_dir>", file=sys.stderr)
        return 1

    run_dir = Path(sys.argv[1])
    if not run_dir.is_dir():
        print(f"error: not a directory: {run_dir}", file=sys.stderr)
        return 1

    events = load_stream(run_dir / "stream.jsonl")
    final_md = (run_dir / "final-review.md").read_text() if (run_dir / "final-review.md").exists() else ""

    print(f"=== Run: {run_dir.name} ===")
    print()

    counts = severity_counts(final_md)
    verdict = parse_verdict_line(final_md)

    if verdict:
        b, g, q = verdict
        print(f"Verdict line: {b} bug(s), {g} gap(s), {q} question(s) [authoritative]")
    print(f"Inline-comment regex counts (lower bound):")
    print(f"  🔴 Bug:      {counts['bug']}")
    print(f"  🟡 Gap:      {counts['gap']}")
    print(f"  🔵 Question: {counts['question']}")

    print()

    # Tool-use breakdown
    name_counter: Counter[str] = Counter()
    write_attempts = 0
    for rec in events:
        if rec.get("type") != "assistant":
            continue
        for b in (rec.get("message") or {}).get("content", []):
            if b.get("type") != "tool_use":
                continue
            name = b.get("name", "?")
            name_counter[name] += 1
            if name in {
                "mcp__github__create_pending_pull_request_review",
                "mcp__github__add_comment_to_pending_review",
                "mcp__github__submit_pending_pull_request_review",
                "mcp__github__create_pull_request_review",
                "mcp__github__add_issue_comment",
                "mcp__github_inline_comment__create_inline_comment",
            }:
                write_attempts += 1

    print(f"Top tool calls:")
    for name, n in name_counter.most_common(12):
        print(f"  {n:4d}  {name}")
    print()
    print(f"GitHub-write tool attempts: {write_attempts}")
    print("  (must be 0 — the read-only allowlist excludes these tools; non-zero = drift)")
    print()

    # Subagent attribution
    subagents = run_dir / "subagents"
    if subagents.exists():
        files = sorted(subagents.glob("*.output"))
        print(f"Preserved subagent outputs: {len(files)}")
        for f in files:
            try:
                print(f"  {f.name}  ({f.stat().st_size} bytes)")
            except Exception:
                continue
        if not files:
            print("  (none — subagent /tmp output files were cleared before preservation)")
    print()

    # Per-subagent usage (from task_notification events)
    sub_usage: list[dict] = []
    for rec in events:
        if rec.get("type") == "system" and rec.get("subtype") == "task_notification":
            sub_usage.append({
                "id": rec.get("task_id", "?")[:9],
                "summary": (rec.get("summary") or "?")[:50],
                "tool_uses": (rec.get("usage") or {}).get("tool_uses", 0),
                "total_tokens": (rec.get("usage") or {}).get("total_tokens", 0),
                "duration_s": (rec.get("usage") or {}).get("duration_ms", 0) / 1000.0,
            })
    if sub_usage:
        print("Per-subagent usage:")
        print(f"  {'task':<10} {'tools':>5} {'tokens':>8} {'wall_s':>7}  summary")
        for s in sub_usage:
            print(f"  {s['id']:<10} {s['tool_uses']:>5} {s['total_tokens']:>8} {s['duration_s']:>7.0f}  {s['summary']}")
        print()

    # Total cost (from final result event)
    for rec in events:
        if rec.get("type") == "result":
            cost = rec.get("total_cost_usd")
            dur_ms = rec.get("duration_api_ms")
            err = rec.get("subtype", "success")
            if cost is not None:
                print(f"Run state:    {err}")
                print(f"Total cost:   ${cost:.2f}")
            if dur_ms:
                print(f"API wall:     {dur_ms / 60000:.1f} min (subagents overlap)")
            mu = rec.get("modelUsage") or {}
            if mu:
                print("Per-model cost:")
                for model, u in mu.items():
                    print(f"  {model:<60s} ${u.get('costUSD', 0):.2f}")
            break

    return 0


if __name__ == "__main__":
    sys.exit(main())
