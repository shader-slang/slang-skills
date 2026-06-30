# Slang Release — cross-cutting gotchas

Pitfalls that span `update-spirv` and `update-gitlab`. Read before a release.

## Rebase base: release-pin, not main tip

When the integration is anchored to a slang release tag, rebase the `slang-rhi` fork onto the exact
`external/slang-rhi` commit that `shader-slang/slang` pins at that tag — NOT rhi `main` tip. Otherwise
the GitLab pair runs a newer rhi than the slang release was validated against. Find the base:
`git -C <slang> ls-tree <release-tag> external/slang-rhi`.

## Re-evaluate drop/keep against the actual base

Whether a GitLab-unique commit is already-upstreamed (drop) or still-needed (keep) depends on the
rebase base. A fix that rhi `main` contained may be ABSENT from the older release-pinned commit — so a
commit you'd drop against `main` must be KEPT against the release base. Re-run the rebase from the
original `nv-internal` against the chosen base and re-evaluate each conflict; do **not** `git rebase
--onto` to transplant a main-based result, because that silently carries the main-based drop decisions
(and can lose a needed commit, e.g. the CUDA-swapchain `currentExtent` fix in 2026-06).

## Linear rebase, not `--rebase-merges`

The rhi fork history contains obsolete github-sync merge commits (`"sync-nv-internal-to-<sha>"`,
`"superseded by <sha>"`) whose target SHA is already in the base. `--rebase-merges` replays those dead
merges and fights spurious conflicts. A plain linear rebase drops all merge commits and replays only
the substantive work.

## OptiX error-API refactor (rhi)

Several rhi OptiX commits target an error-reporting API upstream refactored (old
`file/int line/DeviceAdapter` → new `SourceLocation`/`Device*` via `reportNativeCallError`). Resolving
those conflicts: keep upstream's refactored `reportOptixError`/`reportVulkanError`, add only the fork's
genuinely-new symbols, and drop obsolete helpers (e.g. `isOptixError`) that the refactor removed —
after confirming nothing still references them. This needs a real CUDA/OptiX build to verify.

## Branch-protection asymmetry

- `slang/slang-rhi` `nv-internal` is **force-protected**: a force-push is rejected
  (`pre-receive hook declined: not allowed to force push to a protected branch`) until the user toggles
  "Allowed to force push" ON in **Settings → Repository → Protected branches**, and should be
  re-protected immediately after.
- `slang/slang` `nv-master` and `slang/slangpy` `nv-main` accepted force-pushes **directly**.

Don't assume — if a force-push is rejected, ask the user to unprotect, push, then re-protect.

## Checking GitLab pipeline status

`glab` is typically authed only for `gitlab.com`, not `gitlab-master.nvidia.com`. Query the REST API
directly with a user-provided token (slang project id `6417`). Treat the token as a secret — use it
transiently, never write it to a file/commit/config.

```bash
TOK='<glpat-...>'; BASE='https://gitlab-master.nvidia.com/api/v4/projects/6417'
curl -s --header "PRIVATE-TOKEN: $TOK" "$BASE/pipelines/<PIPELINE_ID>"                  # status + ref
curl -s --header "PRIVATE-TOKEN: $TOK" "$BASE/pipelines/<PIPELINE_ID>/jobs?per_page=100" # per-job status
curl -s --header "PRIVATE-TOKEN: $TOK" "$BASE/jobs/<JOB_ID>/trace"                       # full job log
```

## Triage: pre-existing vs regression

A red pipeline does NOT mean the rebase broke something. Compare against the `nv-master` baseline
nightly — if the SAME job failed the same way before the rebase, it is pre-existing.

```bash
curl -s --header "PRIVATE-TOKEN: $TOK" "$BASE/pipelines?ref=nv-master&per_page=8"   # recent nightlies
# diff the failing job's trace against the same job in the latest nv-master nightly
```

- **`test-ov-*` (Omniverse) failures are KNOWN PRE-EXISTING** (seen 2026-06): `test-ov-linux-x64` and
  `test-ov-windows` fail on a Slang shader-compile error in
  `rtx/nrd/ReLAX/SpatialVarianceEstimation.cs.hlsl` (`fatal error[E40003]`), cascading to an
  `eMissingOutput` golden-image miss — identical on the pre-rebase nightly. That is exactly why the
  GitLab-unique commit `"Temporarily ignore OV test failures in Slack notification"` exists. If
  `test-slang-*` passes and `test-ov-*` shows the same baseline failure, the integration is sound.
- For genuinely new failures: add to `gitlab-only/tests/expected-failure-gitlab.txt` if appropriate
  (note separate `...-linux.txt` / `...-windows.txt` variants — check the live tree), fix real
  regressions, then force-push the updated branch.

## Run CI on the branch, not the tag

The pipeline must run on the `wip-rebase-<DATE>` branch (which carries the GitLab-unique commits + rhi
pin), NOT on the release tag (plain upstream, no GitLab commits). The tag only needs to be **present**
on GitLab so the CMake build derives the version via `git describe`.

## Tag push: the specific tag, never `--tags`

`git push --tags gitlab` would shove every local tag (incl. junk GitHub test tags) to GitLab. Push only
the release tag the build needs (`git push gitlab v2026.12`). `git describe` on `nv-master` then
resolves to e.g. `v2026.12-5-g<sha>`.

## `build-version.inc` git-describe abbrev (spirv)

CI's git defaults to `--abbrev=8`; macOS git may default to `--abbrev=9`, producing a `build-version.inc`
that mismatches CI. Regenerate it with `FORCED_BUILD_VERSION_DESCRIPTION` set from
`git describe --tags --abbrev=8` (see `update-spirv.md` Step 5).
