#!/usr/bin/env python3
"""Run one inner review prompt on OpenCode for an open-weights group.

repro.sh (Reviewer A) and the clarity runner (Reviewer C) call this script in
place of `claude --print` when scripts/review-engine.sh selects OpenCode. It
takes the inputs the Claude path takes and writes the outputs the Claude path
writes, so the detach/wait contract, the post-run guards and the posting step
stay the same:

  inputs   the prompt file, the Claude tool allowlist (--allowed-tools syntax),
           the Claude MCP config, an optional system-prompt append, the turn limit
  outputs  <run-dir>/<output>          the last assistant text (the review)
           <run-dir>/stream.jsonl      OpenCode's raw JSON events
           <run-dir>/tool-uses.jsonl   one {"name", "input"} object per tool call
           <run-dir>/subagents/<call>.output   each subagent's returned text

Consider Reviewer A in an open-weights slang-reviewer container. The checkout's
CLAUDE.md imports AGENTS.md and .github/copilot-instructions.md, REVIEW.md
dispatches the six reviewers in .claude/agents/, and the allowlist permits
`Bash(git diff*)` and `Write(tmp/**)`. This script gives OpenCode the same
instruction files, registers the six reviewers as OpenCode subagents, turns the
allowlist into permission rules (`git diff*` allowed, other commands denied,
edits only under tmp/), and runs the prompt on the group's model
(OPENCODE_MODEL, for example openai/nvidia/zai-org/glm-5.3).

The inner run is isolated from the coworker's own OpenCode server, the way
claude-md-excludes.sh isolates the Claude path from the coworker document: its
own config, data and state directories under the run directory, no external
plugins (the coworker's hook bridge), no skills or instructions from the home
directory, and a config that replaces the OPENCODE_CONFIG_CONTENT the coworker's
server passes to every command it runs.

Limits: --max-turns becomes the build agent's `steps`. --max-budget-usd has no
OpenCode equivalent, so the caller only records it; the gateway's per-agent
budget bounds the spend of an open-weights run.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

# The non-secret API key the NanoClaw OpenCode runner configures
# (container/agent-runner/src/providers/opencode-auth.ts). The gateway in front
# of the endpoint replaces it with the group's credential; this script never
# reads or prints a real key.
CREDENTIAL_PLACEHOLDER = "nc-opencode-token-v1"

# Per-request budget for MCP servers, the same value the NanoClaw OpenCode
# runner uses: OpenCode 1.18 reads one `timeout` for connecting and for each
# request, and deepwiki answers can take minutes.
MCP_TIMEOUT_MS = 330_000

# Claude Code tool names (as an --allowed-tools list or an agent's `tools:`
# line names them) and the OpenCode permission each one maps to. A name that
# maps to None has no OpenCode equivalent and is skipped.
CLAUDE_TOOL_PERMISSIONS = {
    "Read": ["read", "list"],
    "View": ["read", "list"],
    "LS": ["list"],
    "Glob": ["glob"],
    "GlobTool": ["glob"],
    "Grep": ["grep"],
    "GrepTool": ["grep"],
    "Agent": ["task"],
    "Task": ["task"],
    "Skill": ["skill"],
    "Edit": ["edit"],
    "Write": ["edit"],
    "MultiEdit": ["edit"],
    "Bash": ["bash"],
    "WebFetch": ["webfetch"],
    "WebSearch": ["websearch"],
    "TodoWrite": ["todowrite"],
    "BatchTool": None,
}

ENGINE_NOTES = """\
This review runs on OpenCode, not Claude Code. The review instructions name
Claude Code tools; use the OpenCode tool with the same job:

- The Agent (Task) tool is `task`. Set `subagent_type` to the reviewer's name,
  for example `code-quality-reviewer`. Every reviewer in `.claude/agents/` is
  available as a subagent under its file's `name`.
- OpenCode has no `run_in_background`. Put all reviewer dispatches in one
  message.
- Read, Grep, Glob, Bash, Write and Edit are `read`, `grep`, `glob`, `bash`,
  `write` and `edit`. The Skill tool is `skill`.
"""


def log(message: str) -> None:
    print(f">>> opencode-review: {message}", file=sys.stderr, flush=True)


def fail(message: str) -> None:
    print(f"error: {message}", file=sys.stderr, flush=True)
    sys.exit(1)


# --- Permissions -------------------------------------------------------------


def split_tool_list(text: str) -> list[str]:
    """Split a Claude tool list ("Read,Bash(git diff*),Glob" or "Glob, Grep")
    into entries, keeping commas inside parentheses."""
    entries, depth, current = [], 0, ""
    for ch in text:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if ch == "," and depth == 0:
            entries.append(current.strip())
            current = ""
        else:
            current += ch
    entries.append(current.strip())
    return [e for e in entries if e]


def add_rule(rules: dict, permission: str, pattern: str | None) -> None:
    """Allow `permission` for every input (pattern None) or for `pattern` only.
    A bare allow wins over any pattern list for the same permission."""
    if pattern is None:
        rules[permission] = "allow"
        return
    current = rules.get(permission)
    if current == "allow":
        return
    if not isinstance(current, dict):
        current = {"*": "deny"}
        rules[permission] = current
    current[pattern] = "allow"


def apply_claude_tools(rules: dict, entries: list[str]) -> None:
    """Add an allow rule to `rules` for each Claude tool entry.

    `Bash(git diff*)` allows bash commands that match `git diff*`,
    `Write(tmp/**)` allows edits to paths under tmp/, and
    `mcp__deepwiki__ask_question` allows OpenCode's `deepwiki_ask_question`.
    """
    for entry in entries:
        m = re.fullmatch(r"([A-Za-z_]+)\((.*)\)", entry)
        name, pattern = (m.group(1), m.group(2)) if m else (entry, None)
        if name.startswith("mcp__"):
            parts = name.split("__")
            if len(parts) != 3 or pattern is not None:
                fail(f"cannot map the MCP tool entry {entry!r}")
            add_rule(rules, re.sub(r"[^A-Za-z0-9_-]", "_", f"{parts[1]}_{parts[2]}"), None)
            continue
        if name not in CLAUDE_TOOL_PERMISSIONS:
            # Denied, the safe direction: the tool stays unavailable, as it would
            # be if the agent's definition did not list it.
            log(f"no OpenCode permission is known for the Claude tool {entry!r}; it stays denied")
            continue
        for permission in CLAUDE_TOOL_PERMISSIONS[name] or []:
            add_rule(rules, permission, pattern)


def session_permission(allowed: str) -> dict:
    """Return the top-level OpenCode permission rules for a Claude allowlist.

    OpenCode evaluates the last matching rule, so "*": "deny" comes first.
    The tools Claude Code runs without a permission prompt (reading, listing,
    searching, subagents, skills, todos) are allowed as they are on the Claude
    path; everything else needs an allowlist entry. Nothing is left at "ask":
    `opencode run` rejects an ask and would end the session.
    """
    rules: dict = {"*": "deny"}
    for permission in ("read", "list", "glob", "grep", "task", "skill", "todowrite", "external_directory", "doom_loop"):
        rules[permission] = "allow"
    rules["question"] = "deny"
    apply_claude_tools(rules, split_tool_list(allowed))
    return rules


def subagent_permission(tools: str) -> dict:
    """Return the permission rules of a subagent whose definition names `tools`."""
    rules: dict = {"*": "deny", "external_directory": "allow", "doom_loop": "allow", "question": "deny"}
    apply_claude_tools(rules, split_tool_list(tools))
    return rules


# --- Subagents and instructions -------------------------------------------------


def parse_frontmatter(text: str, path: Path) -> tuple[dict, str]:
    """Return the scalar frontmatter fields and the body of a Claude agent file."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        fail(f"{path} has no frontmatter")
    try:
        end = next(i for i in range(1, len(lines)) if lines[i].strip() == "---")
    except StopIteration:
        fail(f"{path} has unterminated frontmatter")
    fields: dict = {}
    key = None
    for line in lines[1:end]:
        m = re.match(r"^([A-Za-z_][A-Za-z0-9_-]*):\s*(.*)$", line)
        if m:
            key, value = m.group(1), m.group(2).strip()
            if value in ("|", ">", "|-", ">-"):
                value = ""
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                value = value[1:-1]
            fields[key] = value
        elif key and line.startswith((" ", "\t")):
            fields[key] = (fields[key] + " " + line.strip()).strip()
    return fields, "\n".join(lines[end + 1 :]).strip()


def subagents(repo_root: Path) -> dict:
    """Return OpenCode subagent definitions for the checkout's .claude/agents/*.md.

    The name, description, prompt and tool list carry over; the `model` field
    does not, so every reviewer runs on the group's model, which OpenCode uses
    for a subagent that names none.
    """
    agents: dict = {}
    for path in sorted((repo_root / ".claude" / "agents").glob("*.md")):
        fields, body = parse_frontmatter(path.read_text(encoding="utf-8"), path)
        name = fields.get("name") or path.stem
        agent: dict = {"mode": "subagent", "description": fields.get("description", name), "prompt": body}
        if fields.get("tools"):
            agent["permission"] = subagent_permission(fields["tools"])
        agents[name] = agent
    return agents


def strip_code(text: str) -> str:
    """Remove fenced code blocks and inline code spans, where @ is not an import."""
    text = re.sub(r"^(```|~~~).*?^\1", "", text, flags=re.S | re.M)
    return re.sub(r"`[^`\n]*`", "", text)


def claude_md_files(repo_root: Path) -> list[Path]:
    """Return the checkout's CLAUDE.md files and the files they import with @path.

    These are the instructions the Claude path loads (claude-md-excludes.sh keeps
    only the checkout's own). Imports resolve relative to the importing file, up
    to five levels deep as in Claude Code. An import outside the checkout, such
    as `@~/.claude/slang-instructions.md`, belongs to the user running the review
    and is not followed.
    """
    root = repo_root.resolve()
    found: list[Path] = []

    def visit(path: Path, depth: int) -> None:
        path = path.resolve()
        if path in found or depth > 5 or not path.is_file():
            return
        if path != root and root not in path.parents:
            return
        found.append(path)
        for m in re.finditer(r"(?:^|(?<=\s))@([^\s`]+)", strip_code(path.read_text(encoding="utf-8"))):
            ref = m.group(1).rstrip(".,;:)]}'\"")
            if not ref or ref.startswith("~"):
                continue
            visit(Path(ref) if os.path.isabs(ref) else path.parent / ref, depth + 1)

    for name in ("CLAUDE.md", ".claude/CLAUDE.md", "CLAUDE.local.md"):
        visit(root / name, 0)
    return found


def instruction_files(repo_root: Path, extra: list[Path]) -> list[str]:
    """Return the absolute instruction paths for the inner run.

    The checkout's CLAUDE.md files and their imports come first, then AGENTS.md
    (OpenCode's own instruction file) when no import already named it, then the
    runner's own files (the system-prompt append, the engine notes).
    """
    files = claude_md_files(repo_root)
    agents_md = (repo_root / "AGENTS.md").resolve()
    if agents_md.is_file() and agents_md not in files:
        files.append(agents_md)
    return [str(p) for p in files + extra]


# --- Provider, MCP and the whole config ------------------------------------------


def positive_int(env: dict, name: str) -> int | None:
    raw = (env.get(name) or "").strip()
    return int(raw) if raw.isdigit() and int(raw) > 0 else None


def provider_config(env: dict) -> dict:
    """Return the model and provider keys of the config for the group's model.

    Mirrors resolveOpenCodeInference in the NanoClaw agent runner
    (container/agent-runner/src/providers/opencode-config.ts), so the inner run
    reaches the same endpoint with the same model as the coworker itself:
    OPENCODE_PROVIDER names the provider, OPENCODE_BASE_URL (else
    ANTHROPIC_BASE_URL, "native" for none) the endpoint, and the `openai`
    provider with a custom endpoint uses the Chat Completions transport.
    """
    provider = env.get("OPENCODE_PROVIDER") or "anthropic"
    model = env.get("OPENCODE_MODEL") or ""
    if not model:
        fail("OPENCODE_MODEL is not set; an open-weights review runs on the group's model")
    # OpenCode picks its own default small model when none is set, which need
    # not be an open-weights one; fall back to the group's main model.
    small = env.get("OPENCODE_SMALL_MODEL") or model
    if (env.get("OPENCODE_AUTH_MODE") or "api-key") != "api-key":
        fail(f"OPENCODE_AUTH_MODE={env.get('OPENCODE_AUTH_MODE')} is not supported; open-weights groups use api-key mode")
    endpoint = env["OPENCODE_BASE_URL"] if "OPENCODE_BASE_URL" in env else env.get("ANTHROPIC_BASE_URL")
    base_url = None if endpoint in (None, "", "native") else endpoint

    def strip(value: str) -> str:
        return value[len(provider) + 1 :] if value.startswith(provider + "/") else value

    context = positive_int(env, "OPENCODE_MODEL_CONTEXT_LIMIT")
    output = positive_int(env, "OPENCODE_MODEL_OUTPUT_LIMIT")
    models: dict = {}
    for mid in (strip(model), strip(small)):
        entry: dict = {"id": mid, "name": mid, "tool_call": True}
        if mid == strip(model) and context:
            entry["limit"] = {"context": context, **({"output": output} if output else {})}
        models.setdefault(mid, entry)
    options: dict = {"apiKey": CREDENTIAL_PLACEHOLDER}
    if base_url:
        options["baseURL"] = base_url
    settings: dict = {"options": options, "models": models}
    if provider == "openai" and base_url:
        settings["npm"] = "@ai-sdk/openai-compatible"
    return {"model": model, "small_model": small, "enabled_providers": [provider], "provider": {provider: settings}}


def mcp_servers(mcp_config: Path) -> dict:
    """Return OpenCode `mcp` entries for a Claude --mcp-config file."""
    servers = json.loads(mcp_config.read_text(encoding="utf-8")).get("mcpServers", {})
    out: dict = {}
    for name, server in servers.items():
        kind = server.get("type", "stdio")
        if kind in ("http", "sse"):
            entry: dict = {"type": "remote", "url": server["url"]}
            if server.get("headers"):
                entry["headers"] = server["headers"]
        elif kind == "stdio":
            entry = {"type": "local", "command": [server["command"], *server.get("args", [])]}
            if server.get("env"):
                entry["environment"] = server["env"]
        else:
            fail(f"MCP server {name} has unsupported type {kind!r}")
        entry.update(enabled=True, timeout=MCP_TIMEOUT_MS)
        out[name] = entry
    return out


def build_config(args: argparse.Namespace, env: dict, extra_instructions: list[Path]) -> dict:
    repo_root = Path(args.repo_root)
    agents = subagents(repo_root)
    agents["build"] = {"steps": args.max_turns}
    config = provider_config(env)
    skills_dir = repo_root / ".claude" / "skills"
    config.update(
        {
            "permission": session_permission(args.allowed),
            "agent": agents,
            "mcp": mcp_servers(Path(args.mcp_config)),
            "instructions": instruction_files(repo_root, extra_instructions),
            "skills": {"paths": [str(skills_dir.resolve())]} if skills_dir.is_dir() else {},
            "autoupdate": False,
            "snapshot": False,
            "share": "disabled",
            # A denied tool call returns an error to the model and the turn goes
            # on, as in Claude Code's print mode.
            "experimental": {"continue_loop_on_deny": True, "mcp_timeout": MCP_TIMEOUT_MS},
        }
    )
    if not config["skills"]:
        del config["skills"]
    return config


# --- Running ----------------------------------------------------------------------


def opencode_env(env: dict, run_dir: Path, config: dict) -> dict:
    """Return the environment of the inner `opencode run`.

    The coworker's OpenCode server passes its own config (OPENCODE_CONFIG_CONTENT)
    and data directory to every command it starts; the inner run replaces both
    and keeps its config, sessions and logs under <run-dir>/opencode/. OpenCode
    installs its plugin package into the new config directory on start (a few
    seconds); with --pure it loads no plugin from it.
    """
    out = dict(env)
    for name in ("OPENCODE_CONFIG", "OPENCODE_CONFIG_DIR"):
        out.pop(name, None)
    home = Path(env.get("HOME") or Path.home())
    old_config_home = Path(env.get("XDG_CONFIG_HOME") or home / ".config")
    # gh keeps reading its own settings when XDG_CONFIG_HOME moves.
    if "GH_CONFIG_DIR" not in env and (old_config_home / "gh").is_dir():
        out["GH_CONFIG_DIR"] = str(old_config_home / "gh")
    base = run_dir / "opencode"
    out.update(
        {
            "XDG_CONFIG_HOME": str(base / "config"),
            "XDG_DATA_HOME": str(base / "data"),
            "XDG_STATE_HOME": str(base / "state"),
            "OPENCODE_CONFIG_CONTENT": json.dumps(config),
            "OPENCODE_DISABLE_PROJECT_CONFIG": "true",
            "OPENCODE_DISABLE_EXTERNAL_SKILLS": "true",
            "OPENCODE_DISABLE_CLAUDE_CODE_PROMPT": "true",
            "OPENCODE_DISABLE_AUTOUPDATE": "true",
        }
    )
    out.setdefault("OPENCODE_DISABLE_MODELS_FETCH", "true")
    return out


def events(stream: Path):
    for line in stream.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            yield json.loads(line)
        except json.JSONDecodeError:
            continue


def extract(stream: Path, run_dir: Path, output_name: str) -> int:
    """Write the review, tool-uses.jsonl and subagent outputs from the events.

    Returns the number of error events, which `opencode run` also reports
    through its exit code.
    """
    last_text, tool_uses, errors = "", [], 0
    sub_dir = run_dir / "subagents"
    sub_dir.mkdir(exist_ok=True)
    for rec in events(stream):
        kind, part = rec.get("type"), rec.get("part") or {}
        if kind == "text":
            last_text = part.get("text") or last_text
        elif kind == "tool_use":
            state = part.get("state") or {}
            tool_uses.append({"name": part.get("tool"), "input": state.get("input")})
            if part.get("tool") == "task" and state.get("status") == "completed":
                call = re.sub(r"[^A-Za-z0-9_.-]", "_", str(part.get("callID") or part.get("id") or len(tool_uses)))
                (sub_dir / f"{call}.output").write_text(str(state.get("output") or ""), encoding="utf-8")
        elif kind == "error":
            errors += 1
            log(f"error event: {json.dumps(rec.get('error'))[:500]}")
    (run_dir / output_name).write_text(last_text + "\n", encoding="utf-8")
    with open(run_dir / "tool-uses.jsonl", "w", encoding="utf-8") as f:
        for use in tool_uses:
            f.write(json.dumps(use) + "\n")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--repo-root", required=True)
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--prompt-file", required=True)
    parser.add_argument("--allowed", required=True, help="Claude --allowed-tools list")
    parser.add_argument("--mcp-config", required=True, help="Claude --mcp-config file")
    parser.add_argument("--system-append-file", help="text Claude gets through --append-system-prompt")
    parser.add_argument("--max-turns", type=int, default=500)
    parser.add_argument("--output", required=True, help="file name for the review in the run directory")
    parser.add_argument("--title", default="slang review")
    parser.add_argument("--print-config", action="store_true", help="print the OpenCode config and exit")
    args = parser.parse_args()

    run_dir = Path(args.run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ)

    notes = run_dir / "opencode-engine-notes.md"
    notes.write_text(ENGINE_NOTES, encoding="utf-8")
    extra = [notes]
    if args.system_append_file:
        extra.insert(0, Path(args.system_append_file).resolve())
    config = build_config(args, env, extra)
    if args.print_config:
        print(json.dumps(config, indent=2))
        return 0
    # The config holds the placeholder key and the endpoint URL, no secret.
    (run_dir / "opencode-config.json").write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")

    prompt = Path(args.prompt_file).read_text(encoding="utf-8")
    cmd = ["opencode", "run", "--pure", "--format", "json", "--title", args.title,
           "--model", config["model"], "--dir", args.repo_root, prompt]
    log(f"model={config['model']} steps={args.max_turns} config={run_dir / 'opencode-config.json'}")
    stream = run_dir / "stream.jsonl"
    proc = subprocess.Popen(
        cmd,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        env=opencode_env(env, run_dir, config),
        cwd=args.repo_root,
        text=True,
        bufsize=1,
    )
    assert proc.stdout is not None
    with open(stream, "w", encoding="utf-8") as out:
        for line in proc.stdout:
            out.write(line)
            out.flush()
            sys.stdout.write(line)
            sys.stdout.flush()
    rc = proc.wait()
    errors = extract(stream, run_dir, args.output)
    if rc == 0 and errors:
        rc = 1
    log(f"done (rc={rc})")
    return rc


if __name__ == "__main__":
    sys.exit(main())
