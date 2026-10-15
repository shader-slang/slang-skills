#!/usr/bin/env bash
# Start a long inner review run detached from the caller and return at once.
#
# Usage: detach.sh <run-dir> -- <command> [args...]
#
# The command runs in its own session (setsid, or a python3 os.setsid()
# fallback where util-linux is absent), under nohup, with stdin from /dev/null
# and stdout+stderr appended to <run-dir>/run.log. A wrapper records its own
# pid in <run-dir>/pid and, once the command exits, its exit code in
# <run-dir>/exit-status (written to a temp name and renamed, so a reader never
# sees a partial file). wait-run.sh polls those two files.
#
# A new session is the point: the coworker's Bash tool kills the process group
# of a backgrounded job when the tool call hits its timeout, and the inner
# reviewer runs take longer than that limit. A process in a different session
# and process group is not reached by that kill, and nohup keeps the hangup the
# closing tool pipe sends from ending it either.
#
# The wrapper runs the command as a child and forwards SIGTERM/SIGINT/SIGHUP to
# it instead of dying with them, so a graceful container stop still yields an
# exit-status file (128 + signal) rather than a run that silently disappears.
# Only SIGKILL leaves no status behind; wait-run.sh reports that case from the
# pid file.
#
# Prints the run directory on stdout and exits 0 as soon as the wrapper has
# been started; the command's own exit code is what wait-run.sh returns later.
set -euo pipefail

usage() { sed -n '2,4p' "$0" >&2; exit 2; }

RUN_DIR="${1:-}"
[ -n "$RUN_DIR" ] || usage
shift
[ "${1:-}" = "--" ] || usage
shift
[ $# -gt 0 ] || usage

mkdir -p "$RUN_DIR"
# A fresh start must never be read against a previous run's status in the same
# directory.
rm -f "$RUN_DIR/exit-status" "$RUN_DIR/exit-status.tmp" "$RUN_DIR/pid"

# The wrapper body is plain POSIX-ish bash passed to `bash -c`; $1 is the run
# dir and the rest is the command. It writes its own pid because setsid forks
# when its caller is already a process-group leader, which makes `$!` in this
# script an unreliable handle on the wrapper.
read -r -d '' WRAPPER <<'EOF' || true
run_dir="$1"; shift
echo "$$" > "$run_dir/pid"
"$@" </dev/null >>"$run_dir/run.log" 2>&1 &
child=$!
trap 'kill -TERM "$child" 2>/dev/null' TERM INT HUP
rc=0
wait "$child" || rc=$?
# `wait` returns early (>128) when a trapped signal arrives; keep waiting until
# the child is really gone so the recorded status is the child's, not ours.
while kill -0 "$child" 2>/dev/null; do
  rc=0
  wait "$child" || rc=$?
done
echo "$rc" > "$run_dir/exit-status.tmp"
mv "$run_dir/exit-status.tmp" "$run_dir/exit-status"
EOF

if command -v setsid >/dev/null 2>&1; then
  setsid nohup bash -c "$WRAPPER" detach-wrapper "$RUN_DIR" "$@" \
    </dev/null >/dev/null 2>&1 &
else
  # macOS ships no setsid; python3 is already required by the runner scripts.
  nohup python3 -c 'import os, sys; os.setsid(); os.execvp(sys.argv[1], sys.argv[1:])' \
    bash -c "$WRAPPER" detach-wrapper "$RUN_DIR" "$@" \
    </dev/null >/dev/null 2>&1 &
fi
disown 2>/dev/null || true

echo "$RUN_DIR"
