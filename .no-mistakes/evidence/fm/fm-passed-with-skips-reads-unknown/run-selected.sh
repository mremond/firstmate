#!/usr/bin/env bash
set -u
export PHASE_ROOT="$PWD"
export TMPDIR="$PHASE_ROOT/.test-phase/tmp"
export FM_HOME="$PHASE_ROOT/.test-phase/home"
mkdir -p "$FM_HOME/state" "$FM_HOME/data" "$FM_HOME/config"
suite=$1
shift
. "$PHASE_ROOT/.test-phase/$suite-defs.sh"
if [ "${PHASE_BASE:-0}" = 1 ]; then
  CREW_STATE="$PHASE_ROOT/.test-phase/base/bin/fm-crew-state.sh"
  TEARDOWN="$PHASE_ROOT/.test-phase/base/bin/fm-teardown.sh"
fi
failures=0
for selected in "$@"; do
  printf '\nTEST %s (base=%s)\n' "$selected" "${PHASE_BASE:-0}"
  ( "$selected" ) || failures=$((failures + 1))
done
exit "$failures"
