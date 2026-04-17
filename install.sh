#!/usr/bin/env bash
# slang-skills installer — interactive skill installer for Claude Code
# Works on macOS, Linux, Windows (Git Bash/WSL)
# Requires bash 3.2+ (no associative arrays, no namerefs, no mapfile)

set -euo pipefail

# ─── Constants ──────────────────────────────────────────────────────────────

VERSION="1.0.0"
MANIFEST_FILE=".slang-skills-manifest"
DEFAULT_INSTALL_DIR="${HOME}/.claude/skills"

# Resolve SCRIPT_DIR portably (no readlink -f on macOS)
SOURCE="${BASH_SOURCE[0]}"
while [ -h "$SOURCE" ]; do
    DIR="$(cd -P "$(dirname "$SOURCE")" && pwd)"
    SOURCE="$(readlink "$SOURCE")"
    [[ "$SOURCE" != /* ]] && SOURCE="$DIR/$SOURCE"
done
SCRIPT_DIR="$(cd -P "$(dirname "$SOURCE")" && pwd)"
SKILLS_SRC_DIR="$SCRIPT_DIR/skills"

# ─── Defaults ───────────────────────────────────────────────────────────────

INSTALL_DIR="$DEFAULT_INSTALL_DIR"
PREFIX=""
COPY_MODE=false
UNINSTALL=false
STATUS=false
NON_INTERACTIVE=false
DRY_RUN=false
SELECTED_SKILLS=""  # comma-separated, empty = all

# ─── Skill metadata (parallel arrays for bash 3.2 compat) ──────────────────

SKILL_NAMES=()
SKILL_DESCS=()
SKILL_DIRS=()
SKILL_SELECTED=()

# ─── Dependency map (variable-name encoding for bash 3.2) ──────────────────

DEPS_slang_fix_bug="slang-investigate slang-build slang-run-tests slang-write-test"
DEPS_slang_analyze_coverage="slang-write-test"
DEPS_slang_test_feature="slang-build slang-run-tests slang-write-test slang-create-issue"
DEPS_slang_review_pr="slang-build"
DEPS_slang_investigate="slang-build slang-run-tests"

# ─── Platform detection ─────────────────────────────────────────────────────

PLATFORM="unknown"

detect_platform() {
    case "$(uname -s)" in
        Darwin)  PLATFORM="macos" ;;
        Linux)
            if grep -qi microsoft /proc/version 2>/dev/null; then
                PLATFORM="wsl"
            else
                PLATFORM="linux"
            fi ;;
        MINGW*|MSYS*|CYGWIN*) PLATFORM="gitbash" ;;
        *)  PLATFORM="unknown" ;;
    esac
}

# ─── Utility functions ──────────────────────────────────────────────────────

sed_inplace() {
    if [[ "$PLATFORM" == "macos" ]]; then
        sed -i '' "$@"
    else
        sed -i "$@"
    fi
}

print_color() {
    local color="$1" text="$2"
    case "$color" in
        red)    printf '\033[31m%b\033[0m' "$text" ;;
        green)  printf '\033[32m%b\033[0m' "$text" ;;
        yellow) printf '\033[33m%b\033[0m' "$text" ;;
        cyan)   printf '\033[36m%b\033[0m' "$text" ;;
        bold)   printf '\033[1m%b\033[0m' "$text" ;;
        dim)    printf '\033[2m%b\033[0m' "$text" ;;
        *)      printf '%b' "$text" ;;
    esac
}

# ─── Argument parsing ───────────────────────────────────────────────────────

usage() {
    cat <<USAGE
slang-skills installer v${VERSION}

Usage: install.sh [OPTIONS]

Options:
  --prefix PREFIX      Add a name prefix to skills (e.g., "jv-")
                       Implies copy mode (cannot prefix symlinks)
  --copy               Force copy mode instead of symlink
  --install-dir DIR    Install to DIR (default: ~/.claude/skills/)
  --uninstall          Remove skills installed by this script
  --status             List skills installed by this script and exit
  --non-interactive    Skip interactive UI, install all skills
  --skills=LIST        Comma-separated skill names to install (with --non-interactive)
  --dry-run            Show what would happen without making changes
  --help               Show this help message

Examples:
  ./install.sh                                  # Interactive selection
  ./install.sh --prefix jv-                     # Install all with "jv-" prefix
  ./install.sh --non-interactive                # Install all, no UI
  ./install.sh --skills=slang-build,slang-run-tests --non-interactive
  ./install.sh --uninstall                      # Remove installed skills
  ./install.sh --status                         # List installed skills
USAGE
    exit 0
}

parse_args() {
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --prefix)
                shift
                PREFIX="$1"
                COPY_MODE=true
                ;;
            --prefix=*)
                PREFIX="${1#*=}"
                COPY_MODE=true
                ;;
            --copy)
                COPY_MODE=true
                ;;
            --install-dir)
                shift
                INSTALL_DIR="$1"
                ;;
            --install-dir=*)
                INSTALL_DIR="${1#*=}"
                ;;
            --uninstall)
                UNINSTALL=true
                ;;
            --status)
                STATUS=true
                ;;
            --non-interactive)
                NON_INTERACTIVE=true
                ;;
            --skills=*)
                SELECTED_SKILLS="${1#*=}"
                NON_INTERACTIVE=true
                ;;
            --dry-run)
                DRY_RUN=true
                ;;
            --help|-h)
                usage
                ;;
            *)
                echo "Unknown option: $1"
                echo "Run with --help for usage."
                exit 1
                ;;
        esac
        shift
    done
}

# ─── Skill discovery ────────────────────────────────────────────────────────

discover_skills() {
    local skill_dir name desc
    for skill_dir in "$SKILLS_SRC_DIR"/*/; do
        [ -f "$skill_dir/SKILL.md" ] || continue
        name=$(basename "$skill_dir")

        # Extract description from YAML frontmatter (awk for macOS compat)
        desc=$(awk '/^---$/{n++; next} n==1 && /^description:/{sub(/^description: */, ""); sub(/\. .*/, ""); print; exit}' "$skill_dir/SKILL.md")
        [ -z "$desc" ] && desc="(no description)"

        SKILL_NAMES+=("$name")
        SKILL_DESCS+=("$desc")
        SKILL_DIRS+=("$skill_dir")
        SKILL_SELECTED+=(1)  # all selected by default
    done

    if [[ ${#SKILL_NAMES[@]} -eq 0 ]]; then
        echo "Error: No skills found in $SKILLS_SRC_DIR"
        exit 1
    fi

    # Apply --skills= filter if specified
    if [[ -n "$SELECTED_SKILLS" ]]; then
        local i
        for i in "${!SKILL_NAMES[@]}"; do
            if echo ",$SELECTED_SKILLS," | grep -q ",${SKILL_NAMES[$i]},"; then
                SKILL_SELECTED[$i]=1
            else
                SKILL_SELECTED[$i]=0
            fi
        done
    fi
}

# ─── Dependency checking ────────────────────────────────────────────────────

get_deps_for() {
    local skill="$1"
    local var_name="DEPS_$(echo "$skill" | tr '-' '_')"
    eval "echo \${$var_name:-}"
}

# Check if a skill name is selected
is_selected() {
    local name="$1" i
    for i in "${!SKILL_NAMES[@]}"; do
        if [[ "${SKILL_NAMES[$i]}" == "$name" && "${SKILL_SELECTED[$i]}" == "1" ]]; then
            return 0
        fi
    done
    return 1
}

# Returns warning text if deselecting this skill would break dependencies
check_deselect_impact() {
    local deselected="$1"
    local warnings=""
    local i
    for i in "${!SKILL_NAMES[@]}"; do
        if [[ "${SKILL_SELECTED[$i]}" == "1" ]]; then
            local deps
            deps=$(get_deps_for "${SKILL_NAMES[$i]}")
            if [[ " $deps " == *" $deselected "* ]]; then
                warnings="${warnings}    ${SKILL_NAMES[$i]} depends on $deselected\n"
            fi
        fi
    done
    echo -e "$warnings"
}

# Check all unresolved dependencies before install
check_all_dependencies() {
    local warnings="" i
    for i in "${!SKILL_NAMES[@]}"; do
        if [[ "${SKILL_SELECTED[$i]}" == "1" ]]; then
            local deps dep
            deps=$(get_deps_for "${SKILL_NAMES[$i]}")
            for dep in $deps; do
                if ! is_selected "$dep"; then
                    warnings="${warnings}  ${SKILL_NAMES[$i]} depends on $dep (not selected)\n"
                fi
            done
        fi
    done
    if [[ -n "$warnings" ]]; then
        print_color yellow "Warning: unresolved skill dependencies:\n"
        printf '%b' "$warnings"
        echo ""
        if [[ "$NON_INTERACTIVE" == true ]]; then
            echo "Continuing anyway (non-interactive mode)."
        else
            printf 'Install anyway? [Y/n] '
            local reply
            read -r reply
            if [[ "$reply" =~ ^[Nn] ]]; then
                echo "Aborted."
                exit 0
            fi
        fi
    fi
}

# ─── Interactive ASCII UI ───────────────────────────────────────────────────

CURSOR_POS=0
WARNING_MSG=""
WARNING_TTL=0
UI_LINES=0  # total lines rendered last frame (for cursor-up redraw)

cleanup_ui() {
    printf '\033[?25h'  # show cursor
    stty echo 2>/dev/null || true
}

read_key() {
    local key
    IFS= read -rsn1 key 2>/dev/null || true
    if [[ "$key" == $'\033' ]]; then
        local seq
        IFS= read -rsn2 -t 0.1 seq 2>/dev/null || true
        case "$seq" in
            '[A') echo "UP" ;;
            '[B') echo "DOWN" ;;
            *)    echo "ESC" ;;
        esac
    elif [[ "$key" == ' ' ]]; then
        echo "SPACE"
    elif [[ "$key" == '' ]]; then
        echo "ENTER"
    elif [[ "$key" == 'q' || "$key" == 'Q' ]]; then
        echo "QUIT"
    elif [[ "$key" == 'a' || "$key" == 'A' ]]; then
        echo "ALL"
    elif [[ "$key" == 'n' || "$key" == 'N' ]]; then
        echo "NONE"
    else
        echo ""
    fi
}

render_ui() {
    # Move cursor up to overwrite previous frame.
    # After a render the cursor sits at column 0 of the line BELOW the last
    # content line (because every content line ends with \n).  Moving up by
    # UI_LINES therefore lands exactly on the first content line.
    if [[ "$UI_LINES" -gt 0 ]]; then
        printf '\033[%dA\r' "$UI_LINES"
    fi

    local i count selected_count=0 lines=0
    count=${#SKILL_NAMES[@]}

    for i in "${!SKILL_NAMES[@]}"; do
        local mark=" "
        [[ "${SKILL_SELECTED[$i]}" == "1" ]] && mark="x" && ((selected_count++)) || true

        if [[ "$i" == "$CURSOR_POS" ]]; then
            printf '\033[7m'  # reverse video
        fi

        local desc="${SKILL_DESCS[$i]}"
        if [[ ${#desc} -gt 60 ]]; then
            desc="${desc:0:57}..."
        fi

        printf '  [%s] %-28s %s\033[0m\033[K\n' "$mark" "${SKILL_NAMES[$i]}" "$desc"
        ((lines++)) || true
    done

    # Blank + status
    printf '\033[K\n  %s/%s selected\033[K\n' "$selected_count" "$count"
    ((lines += 2)) || true

    # Warning
    if [[ -n "$WARNING_MSG" && "$WARNING_TTL" -gt 0 ]]; then
        printf '\033[33m  %s\033[0m\033[K\n' "$WARNING_MSG"
        ((WARNING_TTL--)) || true
    else
        WARNING_MSG=""
        printf '\033[K\n'
    fi
    ((lines++)) || true

    # Blank + help — help line ALSO ends with \n so cursor lands cleanly below
    printf '\033[K\n'
    printf '  \033[2m[Space]\033[0m Toggle  '
    printf '\033[2m[A]\033[0m All  '
    printf '\033[2m[N]\033[0m None  '
    printf '\033[2m[Enter]\033[0m Confirm  '
    printf '\033[2m[Q]\033[0m Quit\033[K\n'
    ((lines += 2)) || true

    UI_LINES=$lines
}

interactive_select() {
    local count=${#SKILL_NAMES[@]}

    trap cleanup_ui EXIT INT TERM
    printf '\033[?25l'  # hide cursor

    echo ""
    print_color bold "  slang-skills installer"
    echo ""
    echo "  Select skills to install:"
    echo ""

    # Initial render
    render_ui

    while true; do
        local key
        key=$(read_key)
        case "$key" in
            UP)
                if [[ "$CURSOR_POS" -gt 0 ]]; then
                    ((CURSOR_POS--)) || true
                fi
                ;;
            DOWN)
                if [[ "$CURSOR_POS" -lt $((count - 1)) ]]; then
                    ((CURSOR_POS++)) || true
                fi
                ;;
            SPACE)
                if [[ "${SKILL_SELECTED[$CURSOR_POS]}" == "1" ]]; then
                    # Deselecting — check dependencies
                    local impact
                    impact=$(check_deselect_impact "${SKILL_NAMES[$CURSOR_POS]}")
                    if [[ -n "$impact" ]]; then
                        WARNING_MSG="Warning: $(echo -e "$impact" | head -1 | sed 's/^  *//')"
                        WARNING_TTL=3
                    fi
                    SKILL_SELECTED[$CURSOR_POS]=0
                else
                    SKILL_SELECTED[$CURSOR_POS]=1
                fi
                ;;
            ALL)
                local i
                for i in "${!SKILL_SELECTED[@]}"; do
                    SKILL_SELECTED[$i]=1
                done
                ;;
            NONE)
                local i
                for i in "${!SKILL_SELECTED[@]}"; do
                    SKILL_SELECTED[$i]=0
                done
                ;;
            ENTER)
                # Check if anything is selected
                local any_selected=false
                for i in "${!SKILL_SELECTED[@]}"; do
                    [[ "${SKILL_SELECTED[$i]}" == "1" ]] && any_selected=true && break
                done
                if [[ "$any_selected" == false ]]; then
                    WARNING_MSG="No skills selected. Use [A] to select all or [Q] to quit."
                    WARNING_TTL=3
                else
                    break
                fi
                ;;
            QUIT|ESC)
                cleanup_ui
                echo ""
                echo "  Aborted."
                exit 0
                ;;
        esac
        render_ui
    done

    cleanup_ui
    # Clear the UI area and print summary
    printf '\n'
}

# Non-interactive fallback for dumb terminals
noninteractive_list() {
    echo ""
    echo "Skills available for installation:"
    echo ""
    local i
    for i in "${!SKILL_NAMES[@]}"; do
        local status="[x]"
        [[ "${SKILL_SELECTED[$i]}" == "0" ]] && status="[ ]"
        printf '  %s %s — %s\n' "$status" "${SKILL_NAMES[$i]}" "${SKILL_DESCS[$i]}"
    done
    echo ""
}

# ─── Symlink support check ──────────────────────────────────────────────────

SYMLINK_SUPPORTED=true

check_symlink_support() {
    if [[ "$PLATFORM" == "gitbash" ]]; then
        local test_dir
        test_dir=$(mktemp -d)
        touch "$test_dir/test_file"
        if ln -s "$test_dir/test_file" "$test_dir/test_link" 2>/dev/null; then
            rm -f "$test_dir/test_link"
            SYMLINK_SUPPORTED=true
        else
            SYMLINK_SUPPORTED=false
            print_color yellow "Warning: Symlinks not available (enable Developer Mode or run as Administrator).\n"
            echo "Falling back to copy mode."
            COPY_MODE=true
        fi
        rm -rf "$test_dir"
    fi

    if [[ "$PLATFORM" == "wsl" && "$INSTALL_DIR" == /mnt/[a-z]/* ]]; then
        print_color yellow "Warning: Install directory is on a Windows mount. Symlinks may not work.\n"
        echo "Consider using ~/.claude/skills/ (inside WSL) or --copy mode."
    fi
}

# ─── Install logic ──────────────────────────────────────────────────────────

install_skill_symlink() {
    local skill_name="$1"
    local src_dir="$SKILLS_SRC_DIR/$skill_name"
    local dest_dir="$INSTALL_DIR/$skill_name"

    if [[ "$DRY_RUN" == true ]]; then
        echo "  [dry-run] mkdir -p $dest_dir"
        echo "  [dry-run] ln -sf $src_dir/SKILL.md $dest_dir/SKILL.md"
        return
    fi

    mkdir -p "$dest_dir"
    ln -sf "$src_dir/SKILL.md" "$dest_dir/SKILL.md"
}

install_skill_copy() {
    local skill_name="$1"
    local dest_name="${PREFIX}${skill_name}"
    local src_dir="$SKILLS_SRC_DIR/$skill_name"
    local dest_dir="$INSTALL_DIR/$dest_name"

    if [[ "$DRY_RUN" == true ]]; then
        echo "  [dry-run] mkdir -p $dest_dir"
        echo "  [dry-run] cp $src_dir/SKILL.md $dest_dir/SKILL.md"
        [[ -n "$PREFIX" ]] && echo "  [dry-run] prefix name: field with '$PREFIX'"
        return
    fi

    mkdir -p "$dest_dir"
    cp "$src_dir/SKILL.md" "$dest_dir/SKILL.md"

    if [[ -n "$PREFIX" ]]; then
        sed_inplace "s/^name: /name: ${PREFIX}/" "$dest_dir/SKILL.md"
    fi
}

install_selected() {
    local i installed=0 skipped=0
    local mode="symlink"
    [[ "$COPY_MODE" == true ]] && mode="copy"

    echo ""
    [[ "$DRY_RUN" == true ]] && print_color yellow "=== DRY RUN ===\n"

    local manifest_entries=""

    for i in "${!SKILL_NAMES[@]}"; do
        [[ "${SKILL_SELECTED[$i]}" == "0" ]] && continue

        local skill_name="${SKILL_NAMES[$i]}"
        local dest_name="${PREFIX}${skill_name}"
        local dest_dir="$INSTALL_DIR/$dest_name"

        # Check for existing non-managed installation
        if [[ -d "$dest_dir" && "$DRY_RUN" == false ]]; then
            local manifest_path="$INSTALL_DIR/$MANIFEST_FILE"
            if [[ -f "$manifest_path" ]] && grep -q "^$dest_name:" "$manifest_path"; then
                # Managed by us — safe to overwrite
                :
            elif [[ -f "$manifest_path" ]]; then
                # Manifest exists but this skill isn't in it
                print_color yellow "  Skipping $dest_name (exists, not managed by this installer)\n"
                ((skipped++)) || true
                continue
            fi
            # No manifest at all — first install, proceed
        fi

        if [[ "$COPY_MODE" == true ]]; then
            install_skill_copy "$skill_name"
        else
            install_skill_symlink "$skill_name"
        fi

        manifest_entries="${manifest_entries}${dest_name}:${mode}:${SKILLS_SRC_DIR}/${skill_name}\n"
        ((installed++)) || true

        if [[ "$DRY_RUN" == false ]]; then
            print_color green "  ✓ "
            echo "$dest_name"
        fi
    done

    # Write manifest
    if [[ "$DRY_RUN" == false && "$installed" -gt 0 ]]; then
        local manifest_path="$INSTALL_DIR/$MANIFEST_FILE"
        {
            echo "# slang-skills manifest — do not edit manually"
            echo "# installed: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
            echo "# source: $SCRIPT_DIR"
            echo "# mode: $mode"
            [[ -n "$PREFIX" ]] && echo "# prefix: $PREFIX"
            printf '%b' "$manifest_entries"
        } > "$manifest_path"
    fi

    echo ""
    if [[ "$DRY_RUN" == true ]]; then
        echo "Dry run complete. $installed skill(s) would be installed."
    else
        echo "Installed $installed skill(s) to $INSTALL_DIR"
        [[ "$skipped" -gt 0 ]] && echo "Skipped $skipped skill(s) (already installed by another source)."
        echo ""
        print_color dim "Restart Claude Code to load the new skills.\n"
    fi
}

# ─── Uninstall logic ────────────────────────────────────────────────────────

uninstall_flow() {
    local manifest_path="$INSTALL_DIR/$MANIFEST_FILE"

    if [[ ! -f "$manifest_path" ]]; then
        echo "No manifest found at $manifest_path"
        echo "Cannot determine which skills were installed by this script."
        echo "You can manually remove skill directories from $INSTALL_DIR"
        exit 1
    fi

    echo ""
    echo "The following skills will be removed:"
    echo ""

    local skills_to_remove=()
    local modes_to_remove=()
    while IFS=: read -r name mode source_path; do
        [[ "$name" == "#"* || -z "$name" ]] && continue
        skills_to_remove+=("$name")
        modes_to_remove+=("$mode")
        echo "  $name ($mode)"
    done < "$manifest_path"

    if [[ ${#skills_to_remove[@]} -eq 0 ]]; then
        echo "  (none)"
        rm -f "$manifest_path"
        exit 0
    fi

    echo ""

    if [[ "$DRY_RUN" == true ]]; then
        echo "[dry-run] Would remove ${#skills_to_remove[@]} skill(s)."
        return
    fi

    if [[ "$NON_INTERACTIVE" == false ]]; then
        printf 'Proceed? [y/N] '
        local reply
        read -r reply
        if [[ ! "$reply" =~ ^[Yy] ]]; then
            echo "Aborted."
            exit 0
        fi
    fi

    local i removed=0
    for i in "${!skills_to_remove[@]}"; do
        local name="${skills_to_remove[$i]}"
        local dest_dir="$INSTALL_DIR/$name"

        if [[ -d "$dest_dir" ]]; then
            # Remove SKILL.md (handles both symlinks and regular files)
            rm -f "$dest_dir/SKILL.md"
            # Remove directory if empty
            rmdir "$dest_dir" 2>/dev/null || true
            if [[ -d "$dest_dir" ]]; then
                print_color yellow "  ~ $name (directory not empty, kept)\n"
            else
                print_color green "  ✓ "
                echo "Removed $name"
                ((removed++)) || true
            fi
        else
            print_color dim "  - $name (already gone)\n"
            ((removed++)) || true
        fi
    done

    rm -f "$manifest_path"
    echo ""
    echo "Removed $removed skill(s)."
    print_color dim "Restart Claude Code to apply changes.\n"
}

# ─── Status ─────────────────────────────────────────────────────────────────

status_flow() {
    local manifest_path="$INSTALL_DIR/$MANIFEST_FILE"

    echo ""
    print_color bold "  slang-skills status\n"
    echo "  ─────────────────────────────────────"
    echo "  Install dir: $INSTALL_DIR"

    if [[ ! -f "$manifest_path" ]]; then
        echo ""
        print_color dim "  No manifest at $manifest_path\n"
        echo "  No skills are tracked by this installer here."
        echo ""
        exit 0
    fi

    # Parse header comments for metadata
    local installed_at="" src_path="" mode="" prefix=""
    while IFS= read -r line; do
        case "$line" in
            "# installed: "*) installed_at="${line#\# installed: }" ;;
            "# source: "*)    src_path="${line#\# source: }" ;;
            "# mode: "*)      mode="${line#\# mode: }" ;;
            "# prefix: "*)    prefix="${line#\# prefix: }" ;;
        esac
    done < "$manifest_path"

    [[ -n "$installed_at" ]] && echo "  Installed:   $installed_at"
    [[ -n "$src_path" ]]     && echo "  Source:      $src_path"
    [[ -n "$mode" ]]         && echo "  Mode:        $mode"
    [[ -n "$prefix" ]]       && echo "  Prefix:      $prefix"
    echo "  ─────────────────────────────────────"
    echo ""

    local total=0 ok=0 broken=0
    while IFS=: read -r name entry_mode source_path; do
        [[ "$name" == "#"* || -z "$name" ]] && continue
        ((total++)) || true

        local dest_dir="$INSTALL_DIR/$name"
        local skill_md="$dest_dir/SKILL.md"
        local state status_color status_text

        if [[ "$entry_mode" == "symlink" ]]; then
            if [[ -L "$skill_md" ]]; then
                local target
                target=$(readlink "$skill_md")
                if [[ -e "$skill_md" ]]; then
                    state="ok (→ $target)"
                    status_color="green"
                    status_text="✓"
                    ((ok++)) || true
                else
                    state="dangling (→ $target)"
                    status_color="red"
                    status_text="✗"
                    ((broken++)) || true
                fi
            elif [[ -e "$skill_md" ]]; then
                state="not a symlink (mode changed?)"
                status_color="yellow"
                status_text="~"
                ((ok++)) || true
            else
                state="missing"
                status_color="red"
                status_text="✗"
                ((broken++)) || true
            fi
        else
            # copy mode
            if [[ -f "$skill_md" && ! -L "$skill_md" ]]; then
                state="ok (copied from $source_path)"
                status_color="green"
                status_text="✓"
                ((ok++)) || true
            elif [[ -e "$skill_md" ]]; then
                state="unexpected file type"
                status_color="yellow"
                status_text="~"
                ((ok++)) || true
            else
                state="missing"
                status_color="red"
                status_text="✗"
                ((broken++)) || true
            fi
        fi

        print_color "$status_color" "  $status_text "
        printf '%-32s ' "$name"
        print_color dim "$state"
        echo ""
    done < "$manifest_path"

    echo ""
    if [[ "$total" -eq 0 ]]; then
        echo "  No skills listed in manifest."
    elif [[ "$broken" -eq 0 ]]; then
        echo "  $total skill(s) installed, all healthy."
    else
        print_color yellow "  $total skill(s) installed, $broken broken.\n"
        echo "  Re-run ./install.sh to repair, or ./install.sh --uninstall to clear."
    fi
    echo ""
}

# ─── Confirmation prompt ────────────────────────────────────────────────────

confirm_install() {
    local mode="symlink"
    [[ "$COPY_MODE" == true ]] && mode="copy"

    local selected_count=0 i
    for i in "${!SKILL_SELECTED[@]}"; do
        [[ "${SKILL_SELECTED[$i]}" == "1" ]] && ((selected_count++)) || true
    done

    echo ""
    print_color bold "  Install summary\n"
    echo "  ─────────────────────────────────────"
    echo "  Skills:    $selected_count"
    echo "  Mode:      $mode"
    echo "  Target:    $INSTALL_DIR"
    [[ -n "$PREFIX" ]] && echo "  Prefix:    $PREFIX"
    echo "  ─────────────────────────────────────"
    echo ""

    if [[ "$NON_INTERACTIVE" == true || "$DRY_RUN" == true ]]; then
        return
    fi

    printf '  Proceed? [Y/n] '
    local reply
    read -r reply
    if [[ "$reply" =~ ^[Nn] ]]; then
        echo "  Aborted."
        exit 0
    fi
}

# ─── Main ───────────────────────────────────────────────────────────────────

main() {
    parse_args "$@"
    detect_platform

    # Expand ~ in INSTALL_DIR
    INSTALL_DIR="${INSTALL_DIR/#\~/$HOME}"

    if [[ "$STATUS" == true ]]; then
        status_flow
        exit 0
    fi

    if [[ "$UNINSTALL" == true ]]; then
        uninstall_flow
        exit 0
    fi

    # Discover available skills
    discover_skills

    # Check symlink support
    if [[ "$COPY_MODE" == false ]]; then
        check_symlink_support
    fi

    # Prefix implies copy mode
    if [[ -n "$PREFIX" && "$COPY_MODE" == false ]]; then
        print_color dim "Note: --prefix implies copy mode (cannot prefix symlinks)\n"
        COPY_MODE=true
    fi

    # Interactive or non-interactive selection
    if [[ "$NON_INTERACTIVE" == true ]]; then
        noninteractive_list
    elif [[ ! -t 0 ]] || [[ "${TERM:-dumb}" == "dumb" ]]; then
        echo "Non-interactive terminal detected. Installing all skills."
        echo "Use --skills=name1,name2 to select specific skills."
        NON_INTERACTIVE=true
        noninteractive_list
    else
        interactive_select
    fi

    # Check dependencies
    check_all_dependencies

    # Create install directory
    if [[ "$DRY_RUN" == false ]]; then
        mkdir -p "$INSTALL_DIR"
    fi

    # Confirm and install
    confirm_install
    install_selected
}

main "$@"
