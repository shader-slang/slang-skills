# Repository Guidance

## Skill Naming

Skill names use lowercase kebab-case. Slang-specific skills start with
`slang-`.

When a skill mirrors a `gh` command, preserve the `gh` command word order after
the `slang-` prefix. For example, `gh pr create` maps to `slang-pr-create`, not
`slang-create-pr`.

## WSL Tool Handling

Every new or updated skill that runs command-line tools must explicitly handle
WSL.

When running under WSL, use Windows-native tools with the `.exe` suffix by
default for tools whose Windows and WSL versions are materially different.

The critical tools are:
- `git.exe`: a worktree created or touched by Git for Windows can be
  incompatible with WSL `git`.
- `cmake.exe`: WSL `cmake` does not recognize the Visual Studio presets, which
  significantly limits Windows testing coverage.
- `slangc.exe` and `slang-test.exe`: when using the Windows-hosted build, these
  must match that build. Running WSL-native `slangc` or `slang-test` can test a
  different compiler build and hide Windows-specific behavior.

GitHub-oriented skills may also select `gh.exe` to avoid authentication-state
mismatches.

If a required Windows-native tool is unavailable, stop and report the missing
tool. Do not silently fall back to the WSL-native tool. Use WSL-native tools only
when the skill provides an explicit option, such as `--wsl`, or when the user
explicitly asks for a native WSL run.

Skills that use selected tools repeatedly should initialize variables such as
`GIT`, `GH`, `CMAKE`, `SLANGC`, or `SLANG_TEST` once, then use those variables
in every command example instead of raw `git`, `gh`, `cmake`, `slangc`, or
`slang-test`.
