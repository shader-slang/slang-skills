#!/usr/bin/env bash
# Block until a detached review run has finished, then exit with its exit code.
#
# Usage: wait-run.sh <run-dir> [--timeout S] [--poll S] [--tail N]
#
# <run-dir> is what detach.sh printed (compose-and-run.sh --detach,
# run-clarity.sh --detach). The run is finished when <run-dir>/exit-status
# exists; its content becomes this script's exit code, and on a nonzero code
# the last --tail lines of <run-dir>/run.log (default 40) go to stderr so the
# caller sees why without opening the log.
#
# Exit codes that are this script's own, chosen so they cannot be confused
# with the runner scripts' 0/1 and the claude CLI's small codes:
#   124  --timeout seconds (default 1200) passed and the run is still going;
#        call again to keep waiting
#   125  the wrapper process recorded in <run-dir>/pid is gone but no
#        exit-status was written (SIGKILL, OOM, reboot) — the run is dead
#     2  usage error or <run-dir> does not exist
#
# The default timeout is 20 minutes so that one call fits comfortably inside
# the coworker's Bash tool limit; the workflow loops on 124.
set -euo pipefail

usage() { sed -n '2,4p' "$0" >&2; exit 2; }

RUN_DIR=""
TIMEOUT=1200
POLL=30
TAIL=40
while (($#)); do
  case "$1" in
    --timeout) TIMEOUT="$2"; shift 2 ;;
    --poll) POLL="$2"; shift 2 ;;
    --tail) TAIL="$2"; shift 2 ;;
    -h|--help) sed -n '2,20p' "$0"; exit 0 ;;
    -*) echo "error: unknown flag $1" >&2; usage ;;
    *) [ -z "$RUN_DIR" ] || usage; RUN_DIR="$1"; shift ;;
  esac
done
[ -n "$RUN_DIR" ] || usage
for v in "$TIMEOUT" "$POLL" "$TAIL"; do
  case "$v" in ''|*[!0-9]*) echo "error: --timeout/--poll/--tail take whole seconds/lines (got: $v)" >&2; exit 2 ;; esac
done
[ "$POLL" -ge 1 ] || POLL=1
[ -d "$RUN_DIR" ] || { echo "error: run directory not found: $RUN_DIR" >&2; exit 2; }

STATUS="$RUN_DIR/exit-status"
PIDFILE="$RUN_DIR/pid"
LOG="$RUN_DIR/run.log"

show_tail() {
  if [ -f "$LOG" ]; then
    echo ">>> wait-run.sh: last $1 lines of $LOG:" >&2
    tail -n "$1" "$LOG" >&2 || true
  else
    echo ">>> wait-run.sh: no run.log in $RUN_DIR yet" >&2
  fi
}

deadline=$(( $(date +%s) + TIMEOUT ))
while :; do
  if [ -f "$STATUS" ]; then
    rc="$(tr -d '[:space:]' < "$STATUS")"
    case "$rc" in ''|*[!0-9]*) echo "error: unreadable exit-status '$rc' in $RUN_DIR" >&2; rc=1 ;; esac
    if [ "$rc" -ne 0 ]; then
      echo ">>> wait-run.sh: run in $RUN_DIR exited $rc" >&2
      show_tail "$TAIL"
    else
      echo ">>> wait-run.sh: run in $RUN_DIR finished (exit 0)"
    fi
    exit "$rc"
  fi

  if [ -f "$PIDFILE" ]; then
    pid="$(tr -d '[:space:]' < "$PIDFILE")"
    if [ -n "$pid" ] && ! kill -0 "$pid" 2>/dev/null; then
      # The wrapper writes exit-status before it exits, so a short grace sleep
      # separates "status being renamed into place" from "wrapper was killed".
      sleep 2
      [ -f "$STATUS" ] && continue
      echo ">>> wait-run.sh: process $pid of $RUN_DIR is gone and no exit-status was written — the run died" >&2
      show_tail "$TAIL"
      exit 125
    fi
  fi

  now=$(date +%s)
  if [ "$now" -ge "$deadline" ]; then
    echo ">>> wait-run.sh: $RUN_DIR still running after ${TIMEOUT}s; call again to keep waiting" >&2
    show_tail 5
    exit 124
  fi
  remaining=$(( deadline - now ))
  step="$POLL"
  [ "$step" -le "$remaining" ] || step="$remaining"
  sleep "$step"
done
