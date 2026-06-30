# Full Release (`full-release`)

Run the release sequence end to end. Pause and **ask the user to confirm** between each major step —
several steps are irreversible (force-pushes to shared branches).

## Sequence

1. **Daily report / status** *(read-only)* — optional situational awareness before cutting.
   Use the `slang-maintainer-tools` skill (`daily-report` recipe). Not part of this skill.

2. **Release notes** *(read-only)* — draft notes for the version being cut. Two options:
   - Script-based: `bash docs/scripts/release-note.sh --previous-hash <previous-tag>` in the slang repo
     (flags breaking changes via PR labels; falls back to raw git log if `gh` has auth/TLS issues).
   - MCP-based: the `slang-maintainer-tools` `release-notes` recipe.

3. **Update SPIRV** — [update-spirv.md](./update-spirv.md). Update the spirv-tools/headers submodules,
   regenerate, build, test, and open a `pr: non-breaking` PR against `shader-slang/slang`.

4. **Update GitLab** — [update-gitlab.md](./update-gitlab.md). The 3-repo OptiX triad: rebase
   `slang-rhi` (`nv-internal`) and `slangpy` (`nv-main`) onto the release-pinned bases, validate on a
   CUDA/OptiX box, then rebase `slang/slang` onto the release tag with both rhi pins bumped to the
   validated `nv-internal`. Force-push each integration branch only after validation + confirmation.

## Ordering notes

- Do the `slang-rhi` rebase **before** `slang/slang` and `slangpy`, because both of those pin
  `external/slang-rhi` and need the validated `nv-internal` SHA.
- The GPU/OptiX validation gates the rhi and slangpy force-pushes; the slang/slang force-push is gated
  on its GitLab CI being green (modulo the known pre-existing `test-ov-*` failures — see
  [gotchas.md](./gotchas.md)).
- See the SKILL's **Safety contract**: backups before every history rewrite, never force-push without
  explicit confirmation.
