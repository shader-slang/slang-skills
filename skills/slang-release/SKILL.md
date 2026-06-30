---
name: slang-release
license: Apache-2.0
description: "Write-heavy Slang release engineering: update the SPIRV-Tools/SPIRV-Headers submodules and integrate GitHub master into the internal GitLab forks (the slang + slang-rhi + slangpy OptiX triad). Use when cutting a release, syncing SPIRV, or rebasing the GitLab nv-* branches. Invoke via /slang-release. This skill performs destructive git operations (force-pushes) and always confirms first. For read-only maintainer reporting (daily report, release notes drafting, issue prioritization), use slang-maintainer-tools instead."
provides: [release.spirv, release.gitlab]
argument-hint: "[task: update-spirv|update-gitlab|full-release]"
allowed-tools: Bash(git:*), Bash(cmake:*), Bash(python3:*), Bash(curl:*), Bash(gh:*), Read, Write, Edit, Grep, Glob
---

# Slang Release

**For**: the write-heavy release-engineering tasks that move released Slang into the internal GitLab forks. This is the counterpart to the read-only `slang-maintainer-tools` skill (which covers daily reports, release-notes drafting, issue prioritization, and review messages).

**Usage**:

```text
/slang-release [task]

  task  update-spirv   Update SPIRV-Tools + SPIRV-Headers submodules and regenerate files
        update-gitlab  Integrate GitHub release into the GitLab nv-* forks (3-repo OptiX triad)
        full-release   Run the release sequence end to end (report → notes → spirv → gitlab)
```

If no task is given, ask which one to run.

## Task → recipe

| Task | Recipe |
|------|--------|
| `update-spirv`  | [update-spirv.md](./update-spirv.md) |
| `update-gitlab` | [update-gitlab.md](./update-gitlab.md) |
| `full-release`  | [full-release.md](./full-release.md) |

Cross-cutting pitfalls (branch-protection asymmetry, pre-existing OV failures, GitLab pipeline checking, remote-naming, release-pinned rebase base): [gotchas.md](./gotchas.md).

## Safety contract (applies to every task)

- **Never force-push without explicit user confirmation.** Force-pushes here overwrite shared
  integration branches (`nv-master`, `nv-internal`, `nv-main`) that the whole team builds from.
- **Always create a `before-rebase-*` backup branch and push it** before any history rewrite, so the
  prior state is recoverable.
- **Validate before overwriting.** The OptiX ray-query path can only be verified on a machine with an
  NVIDIA GPU + CUDA + OptiX SDK. Do the rebase groundwork anywhere, but gate the force-push on a real
  GPU validation (see [gotchas.md](./gotchas.md)).
- **Check `git status` is clean** before major operations.

## WSL tool handling

This skill runs `git`, `cmake`, `python3`, `curl`, and `gh`. Detect WSL and select tools accordingly:

```bash
IS_WSL=0
if grep -qiE "(microsoft|wsl)" /proc/version 2>/dev/null; then IS_WSL=1; fi

if [ "$IS_WSL" = "1" ]; then
  GIT=git.exe; CMAKE=cmake.exe; PYTHON=python.exe; GH=gh.exe
else
  GIT=git; CMAKE=cmake; PYTHON=python3; GH=gh
fi
```

Under WSL, prefer the Windows-native `.exe` tools (`git.exe`, `cmake.exe`, `python.exe`, `gh.exe`) for
anything that touches a Windows-created worktree, builds with Visual Studio presets, or relies on
GitHub auth state — their WSL and Windows versions are materially different (a Windows worktree can be
incompatible with WSL `git`; WSL `cmake` does not recognize the VS presets). If a required Windows-native
tool is missing, **stop and report it** rather than silently falling back to the WSL-native tool. Use
WSL-native tools only when the user explicitly asks for a native WSL run.

## Reference documents (read fresh — layouts drift)

- SPIRV update process (GitHub): `docs/update_spirv.md` in the slang repo.
- GitLab integration process: lives on the GitLab `nv-master` branch at
  `gitlab-only/docs/update_gitlab.md` — read it first:
  `git show gitlab/nv-master:gitlab-only/docs/update_gitlab.md`. All GitLab-unique files live under
  the `gitlab-only/` directory.
- Release notes: `docs/scripts/release-note.sh` in the slang repo, or the MCP-based recipe in
  `slang-maintainer-tools/release-notes.md`.
