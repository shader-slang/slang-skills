# Update SPIRV (`update-spirv`)

Update the vendored `external/spirv-tools` and `external/spirv-headers` submodules to their latest
versions and regenerate the dependent generated files. Follow `docs/update_spirv.md` in the slang repo
as the source of truth; the steps below capture the procedure plus hard-won gotchas.

Run from the root of a slang checkout. (Under WSL, use the `.exe` tools per the SKILL's WSL block.)

## Step 1: Update the SPIRV-Tools submodule

```bash
git submodule sync
git submodule update --init --recursive
git -C external/spirv-tools fetch
git -C external/spirv-tools checkout origin/main
```

## Step 2: Unshallow spirv-tools and fetch tags

**CRITICAL**: before building, ensure spirv-tools has full git history. If it is a shallow clone,
`git describe` falls back to the raw SHA instead of a tag-based string, causing `build-version.inc` to
mismatch what CI generates.

```bash
git -C external/spirv-tools fetch --unshallow origin 2>/dev/null || true
git -C external/spirv-tools fetch --tags origin
```

Verify `git describe` works (should output something like `v2026.1-23-ga8fa7f50`):

```bash
git -C external/spirv-tools describe --tags --abbrev=8
```

If it still fails (no tags reachable), the submodule may be on a detached commit not descended from any
tag — proceed, but note `build-version.inc` may need manual correction.

## Step 3: Build spirv-tools

On macOS/Linux use `python3`/`cmake`; on Windows/WSL use the `.exe` variants.

```bash
cd external/spirv-tools
python3 utils/git-sync-deps
cmake . -B build
cmake --build build --config Release
cd ../..
```

**Note**: `git-sync-deps` may require an SSH key registered at gitlab.khronos.org. If it fails, inform
the user. The build can take several minutes — run it in the background if possible.

## Step 4: Update SPIRV-Headers

Get the expected commit from the SPIRV-Tools `DEPS`, then check spirv-headers out to it:

```bash
grep spirv_headers_revision external/spirv-tools/DEPS
git -C external/spirv-headers fetch
git -C external/spirv-headers checkout <hash-from-DEPS>
```

## Step 5: Copy the generated files

```bash
rm external/spirv-tools-generated/*.h external/spirv-tools-generated/*.inc
cp external/spirv-tools/build/*.h external/spirv-tools-generated/
cp external/spirv-tools/build/*.inc external/spirv-tools-generated/
```

**⚠️ `build-version.inc` git-describe abbrev.** CI uses a git that defaults to `--abbrev=8`
(e.g. `v2026.1-23-ga8fa7f50`); macOS git may default to `--abbrev=9`
(e.g. `v2026.1-23-ga8fa7f503`). After copying, regenerate it with the CI-correct abbrev so the file
matches what CI produces:

```bash
EXPECTED=$(git -C external/spirv-tools describe --tags --abbrev=8)
FORCED_BUILD_VERSION_DESCRIPTION="$EXPECTED" \
  python3 external/spirv-tools/utils/update_build_version.py \
  external/spirv-tools/CHANGES \
  external/spirv-tools-generated/build-version.inc
cat external/spirv-tools-generated/build-version.inc   # verify
```

## Step 6: Validate (optional)

```bash
bash extras/check-spirv-generated.sh
```

**Warning**: this script runs `git submodule update`, which can revert spirv-tools. If you run it, you
may need to re-checkout the updated spirv-tools commit afterwards.

## Step 7: Build Slang and test

```bash
rm -rf build
cmake --preset default
# Redirect build output to null on the first attempt; re-run verbosely only on failure:
cmake --build --preset release >/dev/null 2>&1 || cmake --build --preset release
SLANG_RUN_SPIRV_VALIDATION=1 ./build/Release/bin/slang-test -use-test-server -server-count 8
```

GPU-backed (Vulkan) tests will fail/skip on a machine without a GPU — that is expected; the host/CPU
suite plus SPIRV validation is the meaningful local signal.

## Step 8: Commit and open a PR

Ask the user before committing. If yes:

```bash
git checkout -b update-spirv master
git add external/spirv-headers external/spirv-tools external/spirv-tools-generated
git commit -m "Update SPIRV-Tools and SPIRV-Headers to latest versions"
```

Open the PR against `shader-slang/slang` and label it `pr: non-breaking`. Do not stage stray build
artifacts (e.g. `*.dSYM/`).
