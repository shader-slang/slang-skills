# slang-skills

Experimental skills for AI tools for the [Slang](https://github.com/shader-slang/slang) shader compiler. Provides interactive installation of reusable skills to your `~/.claude/skills/` directory.

## Quick Start

**Install with gh skill:**

```bash
gh skill install https://github.com/shader-slang/slang-skills
```

**macOS / Linux / WSL / Git Bash:**

```bash
git clone https://github.com/shader-slang/slang-skills.git
cd slang-skills
./install.sh
```

**Windows (native PowerShell):**

```powershell
git clone https://github.com/shader-slang/slang-skills.git
cd slang-skills
.\install.ps1
```

The interactive installer lets you select which skills to install using arrow keys and spacebar.

## Skills

### Slang specific skills

| Skill | Description | Dependencies |
|-------|-------------|-------------|
| `slang-build` | Platform-aware build: OS detection, CMake presets, submodules | *(foundation)* |
| `slang-run-tests` | Platform-aware testing: skip detection, SPIRV validation | slang-build |
| `slang-write-test` | Test syntax reference: directives, diagnostic tests, compute tests | *(foundation)* |
| `slang-investigate` | Root cause investigation: classify, trace, design context | slang-build, slang-run-tests |
| `slang-create-issue` | Issue/PR templates, commit rules | *(standalone)* |
| `slang-fix-bug` | Bug fix workflow: intake, investigation, parallel fix exploration | slang-investigate, slang-build, slang-run-tests, slang-write-test |
| `slang-review-pr` | PR review: evaluate approach, address feedback, manage threads | slang-build |
| `slang-analyze-coverage` | Coverage analysis: gap identification, test value scoring | slang-write-test |
| `slang-test-feature` | End-to-end orchestrator: research, plan, parallel agents | slang-build, slang-run-tests, slang-write-test, slang-create-issue |
| `slang-evaluate-session` | Post-session skill effectiveness review | *(standalone)* |
| `slang-resolve-pr-comments` | Resolve PR review feedback: LLM threads, CI failures, rebase conflicts | *(standalone)* |

### General developer skills

| Skill | Description | Dependencies |
|-------|-------------|-------------|
| `tmux-agent-manager` | Manage multiple Claude Code agent sessions in tmux: status reporting, message delivery, health monitoring, and spawning new agents from GitHub issues or free-form prompts. Works on Linux, macOS, WSL, and Windows (Git Bash / PowerShell). | *(standalone)* |

## Installation Options

### Interactive (default)

```bash
./install.sh
```

Use arrow keys to navigate, Space to toggle, A for all, N for none, Enter to confirm.

### With a name prefix

```bash
./install.sh --prefix local-
```

Installs skills with a prefix (e.g., `local-slang-build`). Uses copy mode to modify the `name:` field.

### Specific skills only

```bash
./install.sh --non-interactive --skills=slang-build,slang-run-tests
```

### Custom install location

```bash
./install.sh --install-dir /path/to/skills
```

### Dry run

```bash
./install.sh --dry-run
```

Shows what would be installed without making changes.

### Copy mode

```bash
./install.sh --copy
```

Copies skill files instead of symlinking. Implied by `--prefix`.

## Status

```bash
./install.sh --status                # bash
.\install.ps1 -Status                # PowerShell
```

Lists skills tracked in the manifest with their mode (symlink vs copy) and health (OK / dangling / missing), followed by any skills available in this repo that are not yet installed.

## Uninstall

```bash
./install.sh --uninstall             # bash
.\install.ps1 -Uninstall             # PowerShell
```

Removes only skills installed by this script (tracked via manifest).

## Updating

Re-run `./install.sh` to change your selection. The installer detects the current installation, pre-ticks skills that are already installed, and on confirm installs any newly-ticked skills and removes any that were unticked. In symlink mode, installed skills automatically reflect changes when you `git pull` this repo — no re-run needed for code updates.

## Install Modes

| Mode | How | Auto-updates | Prefix support |
|------|-----|:---:|:---:|
| **Symlink** (default) | Creates directory, symlinks SKILL.md inside | Yes | No |
| **Copy** (`--copy`) | Copies SKILL.md into directory | No (re-run to update) | Yes |

## Platform Notes

| Platform | Script | Status |
|----------|--------|--------|
| **macOS** | `install.sh` | Works out of the box |
| **Linux** | `install.sh` | Works out of the box |
| **Windows (PowerShell)** | `install.ps1` | Requires PowerShell 5.1+ (ships with Windows 10). Symlinks require Developer Mode or an elevated shell; otherwise falls back to copy mode automatically. |
| **Windows (Git Bash)** | `install.sh` | Symlinks require Developer Mode or Administrator. Falls back to copy mode automatically. |
| **WSL** | `install.sh` | Works like Linux. Avoid installing to `/mnt/c/` paths with symlink mode. |

Both scripts share the same manifest format (`.slang-skills-manifest`), so you can install with one and uninstall with the other.

## All Options

**bash (`install.sh`)**

```
./install.sh [OPTIONS]

  --prefix PREFIX      Add a name prefix to skills (implies copy mode)
  --copy               Force copy mode instead of symlink
  --install-dir DIR    Install to DIR (default: ~/.claude/skills/)
  --uninstall          Remove skills installed by this script
  --status             List installed skills and their health
  --non-interactive    Skip interactive UI, install all skills
  --skills=LIST        Comma-separated skill names (with --non-interactive)
  --dry-run            Show what would happen without making changes
  --help               Show help
```

**PowerShell (`install.ps1`)**

```
.\install.ps1 [OPTIONS]

  -Prefix PREFIX       Add a name prefix to skills (implies copy mode)
  -Copy                Force copy mode instead of symlink
  -InstallDir DIR      Install to DIR (default: %USERPROFILE%\.claude\skills)
  -Uninstall           Remove skills installed by this script
  -Status              List installed skills and their health
  -NonInteractive      Skip interactive UI, install all skills
  -Skills "LIST"       Comma-separated skill names (with -NonInteractive)
  -DryRun              Show what would happen without making changes
  -Help                Show help
```

If you get an execution-policy error on Windows, run once with:
`powershell.exe -ExecutionPolicy Bypass -File .\install.ps1`
