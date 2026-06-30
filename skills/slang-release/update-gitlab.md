# Update GitLab (`update-gitlab`)

Integrate a GitHub Slang release into the internal GitLab forks. Follow
`gitlab-only/docs/update_gitlab.md` (on the GitLab `nv-master` branch) as the source of truth —
**read it fresh first**, the layout has changed before and may change again:

```bash
git show gitlab/nv-master:gitlab-only/docs/update_gitlab.md
```

> **IMPORTANT — this is a THREE-repo integration.** Updating `slang/slang` is only one-third of the
> job. The OptiX ray-query end-to-end path spans three internal GitLab forks that must move together:
> `slang/slang` (`nv-master`), `slang/slang-rhi` (`nv-internal`), and `slang/slangpy` (`nv-main`).
> `slang-rhi` and `slangpy` are **internal forks**, not upstream-pinned submodules; each must be
> rebased (GitHub → GitLab) in the **same integration**. Both `slang/slang` AND `slang/slangpy` pin
> `external/slang-rhi`, so the rhi pin must be bumped in **both**. Skipping any of them breaks the
> OptiX ray-query end-to-end tests.

## Remote-naming caveat

The GitLab doc is written from a **GitLab clone**, so it calls GitLab `origin` and GitHub `github`. In
a GitHub-primary working copy the remotes are reversed — typically `gitlab` = the GitLab fork and
`upstream` (or `origin`) = GitHub. Map the doc's commands to your actual remote names (the doc's
`git rebase github/master` becomes `git rebase upstream/master`, etc.). The commands below assume a
GitHub-primary slang checkout with a `gitlab` remote.

## Prerequisites

```bash
git remote get-url gitlab 2>/dev/null || git remote add gitlab ssh://git@gitlab-master.nvidia.com:12051/slang/slang.git
```

## Step 1: Anchor to the release tag and fetch

Anchor the integration to the **release tag** (e.g. `v2026.12`), not a moving master tip:

```bash
git fetch --tags upstream master
git fetch --tags gitlab nv-master
git rev-list -n1 v2026.12        # the release commit you will rebase onto
```

## Step 2: Review the GitLab-unique commits

```bash
git log --oneline gitlab/nv-master --not v2026.12
```

Show these to the user. The known GitLab-unique commits (verify the live set — they drift):

- `Added micro mesh intrinsics support.` (cannot be upstreamed yet)
- `Squashed gitlab CI and build infrastructure`
- `Optix Ray Query`
- `Update slang-rhi submodule to nv-internal ...` (the submodule-pin bump)
- `docs(gitlab): document keeping the slang-rhi submodule in sync`
- `Temporarily ignore OV test failures in Slack notification`

GitLab-unique files all live under `gitlab-only/` (verify:
`git ls-tree -r --name-only gitlab/nv-master | grep '^gitlab-only/'`) — `gitlab-only/docs/`,
`gitlab-only/ci-*.yml`, `gitlab-only/*.sh`, `gitlab-only/slangbuild-win64.ps1`,
`gitlab-only/tests/expected-failure-gitlab-{linux,windows}.txt`, `gitlab-only/tests/nv-internal/`,
plus the top-level `.gitlab-ci.yml`.

## Step 3: Backup branch (safety net)

```bash
git checkout -B before-rebase-<DATE> gitlab/nv-master
git push gitlab before-rebase-<DATE>
```

## Step 4: Rebase slang/slang onto the release tag

```bash
git checkout -B wip-rebase-<DATE> gitlab/nv-master
git rebase v2026.12
```

During the rebase, `"BASE"` = GitHub release changes, `"REMOTE"` = GitLab nv-master changes. Resolve
conflicts, `git rebase --continue`. The `external/slang-rhi` submodule pointer will conflict — resolve
it to the validated rhi `nv-internal` commit from Step 5 (set it directly with
`git update-index --cacheinfo 160000,<rhi-sha>,external/slang-rhi`). If a later pure pin-bump commit
becomes redundant, `git rebase --skip` it.

## Step 5: Rebase the `slang-rhi` internal fork (do this first — others pin it)

`slang/slang-rhi` must equal **the upstream rhi commit the slang release pins + the GitLab-unique
OptiX ray-query commits**. Work in a **separate clone**.

> **⚠️ REBASE ONTO THE rhi COMMIT THE SLANG RELEASE PINS — NOT rhi `main` tip.** The rhi base must be
> the exact `external/slang-rhi` commit `shader-slang/slang` pins at the release tag, so the GitLab
> pair is exactly "released slang + our deltas" paired with "released rhi + our deltas". Rebasing onto
> rhi `main` tip pulls in post-release upstream rhi commits the slang release was never validated
> against (seen 2026-06: main was 3 commits ahead of the pinned `687dc186`, including an `IQueryPool`
> API rename and a CUDA-surface rework). Find the base:
> `git -C <slang> ls-tree <release-tag> external/slang-rhi`.
>
> **CAUTION — re-evaluate every drop against the actual base.** Which GitLab-unique commits are
> already-upstreamed (drop) vs still-needed (keep) depends on the base: a fix `main` contained may be
> ABSENT from the older release-pinned commit, so a commit you would drop against `main` must be KEPT
> against the release base (seen 2026-06: the CUDA-swapchain `currentExtent` fix was empty/dropped
> onto main but had to be kept onto `687dc186`). Do NOT `rebase --onto` to transplant a main-based
> result — it silently carries the main-based drop decisions.

> **⚠️ BRANCH NAMES DIFFER FROM THE DOC.** The rhi fork's integration branch is **`nv-internal`**
> (NOT `nv-master`), and the rhi upstream default branch is **`main`** (NOT `master`). Verify live with
> `git branch -a` and `git remote show github | grep 'HEAD branch'`.

> **⚠️ THIS IS NOT A MECHANICAL REBASE — IT NEEDS A CUDA/OptiX BUILD ENVIRONMENT.** The fork's OptiX
> commits were written against an OptiX error-reporting API upstream has since refactored (old
> `file/int line/DeviceAdapter` → new `SourceLocation`/`Device*` via `reportNativeCallError`). Several
> interdependent commits touch `src/cuda/optix-api-impl.cpp/.h` and each needs **semantic** conflict
> resolution; then the OptiX ray-query tests must be built and run to verify. **OptiX/CUDA do not
> exist on macOS** — do the groundwork (clone, backup, identify already-upstreamed commits) anywhere,
> but resolve OptiX conflicts and force-push only on Linux/Windows with an NVIDIA GPU + OptiX SDK
> (ideally with the OptiX RQ commit author).

```bash
git clone ssh://git@gitlab-master.nvidia.com:12051/slang/slang-rhi.git
cd slang-rhi
git remote add github https://github.com/shader-slang/slang-rhi.git
git fetch --tags github main          # rhi upstream default = main
git fetch --tags origin nv-internal   # rhi integration branch = nv-internal
git checkout -B before-rebase-rhi-<DATE> && git reset --hard origin/nv-internal && git push origin before-rebase-rhi-<DATE>
git checkout -B wip-rebase-rhi-<DATE> && git reset --hard origin/nv-internal

# RHI_BASE = the rhi commit the slang release pins:
#   RHI_BASE=$(git -C <slang-repo> ls-tree <release-tag> external/slang-rhi | awk '{print $3}')
# Use a LINEAR rebase (NOT --rebase-merges): the fork history contains obsolete github-sync merge
# commits whose target sha is already in the base; --rebase-merges replays those dead merges and
# fights spurious conflicts. A plain rebase drops merges and replays only the substantive work.
git rebase $RHI_BASE
```

Handle each bubbled-up rhi-unique commit (upstream / drop / keep):

- **Drop (skip)** commits already upstreamed — recognizable by an upstream PR number in the subject
  (e.g. `(#755)`). Confirm the change is in the base, then `git rebase --skip`.
- **Keep** the OptiX/CUDA ray-query work (the reason the fork exists), plus: the CUDA backend
  advertising `Feature::RayQuery`, and the LSS inline ray-query runtime test (blocked on the public
  LSS language PR landing in a release before it can be upstreamed).
- Watch for slang↔rhi **API-sync drift** — e.g. RayQuery accessors renamed with an `NV` suffix in a
  newer slang; the rhi test shaders must match the slang the release ships.

After rhi builds and its tests pass **on a CUDA/OptiX box**, validate, then push and overwrite
`nv-internal` (force-push may need the protected branch temporarily opened — see
[gotchas.md](./gotchas.md)):

```bash
git push origin <validated-sha>:nv-internal --force
```

## Step 5b: Rebase the `slangpy` internal fork (third leg of the triad)

`slang/slangpy` is an internal fork just like slang-rhi — do NOT skip it.

> **⚠️ `slang/slangpy` BRANCH NAMES.** Integration branch = **`nv-main`** (NOT `nv-master`/
> `nv-internal`); upstream github default = **`main`**.

Key relationships (verify each integration — they drift):

- **Both `slang/slang` and `slang/slangpy` pin `external/slang-rhi`** → both rhi pins must be bumped to
  the SAME validated rhi `nv-internal` commit. Bumping only slang/slang's pin and forgetting slangpy's
  leaves the triad inconsistent.
- `slang/slangpy` also pins `external/optix-dev` (GitLab) and bundles the OptiX-dev SDK.
- The GitLab-unique slangpy commits (seen 2026-06, 3 of them): "Enable CUDA/OptiX compute ray-query
  path in SlangPy", a pathtracer CLI/diagnostics commit, and "Bundle OptiX dev SDK + bump
  external/slang-rhi to optix-ray-query tip" (the rhi pin-bump — re-point it at the new nv-internal).

```bash
git clone ssh://git@gitlab-master.nvidia.com:12051/slang/slangpy.git
cd slangpy && git remote add github https://github.com/shader-slang/slangpy.git
git fetch --tags github main && git fetch --tags origin nv-main
git checkout -B before-rebase-slangpy-<DATE> && git reset --hard origin/nv-main && git push origin before-rebase-slangpy-<DATE>
git checkout -B wip-rebase-slangpy-<DATE> && git reset --hard origin/nv-main
git rebase github/main        # linear; handle upstream/drop/keep per commit
# Resolve the external/slang-rhi pin to the validated rhi nv-internal:
git update-index --cacheinfo 160000,<validated-rhi-sha>,external/slang-rhi
# (slangpy isn't pinned by the slang release, so rebasing onto github main tip is the natural base.)
```

> **NOTE — public slangpy vs the GitLab fork.** Don't confuse them: `gitlab-only/build-slangpy-pr.sh`
> clones **public** `github.com/shader-slang/slangpy` to test public PRs against GitLab slang — that
> is NOT the integration fork. The integration fork is GitLab `slang/slangpy` `nv-main`, which carries
> the OptiX deltas + rhi pin and must be rebased every integration.

Validate on a CUDA/OptiX box, then force-push `nv-main` to the validated tip.

## Step 6: Build, test, then push the slang/slang branch for CI

```bash
cmake --preset default && cmake --build --preset release >/dev/null 2>&1 || cmake --build --preset release
./build/Release/bin/slang-test -expected-failure-list gitlab-only/tests/expected-failure-gitlab.txt -use-test-server -server-count 8
./build/Release/bin/slang-test -expected-failure-list gitlab-only/tests/expected-failure-gitlab.txt gitlab-only/tests/nv-internal/*
git push gitlab wip-rebase-<DATE>
```

Tell the user to create an MR for review + CI. **DO NOT MERGE the MR** — it is a rebase workflow; the
MR will show conflicts (expected). You can also run the pipeline directly on the branch. See
[gotchas.md](./gotchas.md) for checking pipeline status and triaging failures (the `test-ov-*` jobs
fail pre-existingly).

## Step 7: Force-push the integration branches (irreversible — confirm first)

Only after CI is green (modulo the known pre-existing OV failures) and review is approved. Ask the user
explicitly. Push the release tag (the specific tag, never `git push --tags`) so the CMake build derives
its version, then overwrite each branch with its validated tip:

```bash
git push gitlab v2026.12                              # the release tag only
git push gitlab wip-rebase-<DATE>:nv-master --force   # slang/slang
# slang-rhi nv-internal and slangpy nv-main were force-pushed in Steps 5 / 5b after their validation
```

See [gotchas.md](./gotchas.md) for the branch-protection asymmetry (`nv-internal` is protected and
needs unprotect/re-protect; `nv-master`/`nv-main` accepted force-pushes directly).

## Step 8: Cleanup (ask first)

Delete the `wip-rebase-*` working branches once everything is stable; keep the `before-rebase-*`
backups until you are confident the integration is good.
