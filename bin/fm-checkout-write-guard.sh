#!/usr/bin/env bash
# fm-checkout-write-guard.sh - refuse a test that writes into the repository
# checkout it runs from.
#
# WHY THIS EXISTS (read this before removing or weakening it).
#
# A test suite's scripts are assumed isolated from each other by temporary
# directories, ports and process boundaries. The repository checkout is the one
# sharing channel none of those cover: it is a single mutable directory every
# script runs from, and anything a script leaves behind there is visible to
# every script that follows.
#
# That is not theoretical. tests/fm-backend.test.sh carried an assertion whose
# verdict was a pure function of whether a gitignored `state/` directory existed
# inside the checkout - deterministic in both directions, measured alone in a
# single process, nothing to do with parallelism or load. Fourteen unrelated
# test scripts create that directory as a side effect of doing their own job and
# a fifteenth does it intermittently, so the assertion reported which neighbour
# had run first and dressed the answer up as a fact about symlinked project
# prefixes. It also reproduced the oldest complaint in software: a developer's
# working copy silently grows that directory the first time they run the suite
# and never mentions it, so the case passes on the maintainer's machine and
# fails on a fresh runner.
#
# The guarantee is therefore a prohibition, not a report: a test script may not
# create, remove, or modify any path under the checkout. Its own state belongs
# in a temporary directory it owns.
#
# Three consequences that are part of the contract, not accidents:
#   - Refusal is the point. A check that can only agree with itself is green
#     forever and worth nothing. tests/fm-checkout-write-guard.test.sh proves
#     by mutation that a writing script is genuinely refused and the same script
#     without the write is not.
#   - Leaks that predate the guard are PINNED, one script at a time, with a
#     reason and the exact paths allowed (pin_table below). A pin is recorded
#     debt, not an exemption: a script writes only what its pin names, an
#     unpinned script writes nothing at all, and every pin removed is a test
#     that stopped reporting on its neighbours. Do not add a pin to make a new
#     script pass; give the script a home of its own instead.
#   - A few paths under the checkout belong to something other than the test and
#     can change while the suite runs - the validation pipeline's own evidence,
#     for one. Those are structurally exempt rather than pinned, and reported
#     under their own marker, because blaming them on whichever script happened
#     to be running would be wrong rather than lenient (structural_exemption
#     below).
#
# Usage:
#   fm-checkout-write-guard.sh snapshot <file> [--root <dir>]
#   fm-checkout-write-guard.sh compare <before> <after> [options]
#   fm-checkout-write-guard.sh run [options] -- <command> [args...]
#   fm-checkout-write-guard.sh --list-pins
#   fm-checkout-write-guard.sh -h | --help
#
# Options:
#   --root <dir>   checkout to guard (default: this script's repository root)
#   --label <name> name reported in refusals, and the key looked up in the pin
#                  table. The test runner passes the script's basename.
#   --allow <glob> additionally tolerate paths matching <glob>, relative to the
#                  root and written as `./x` (repeatable). Caller-supplied
#                  tolerance for a deliberate write; it never widens a pin.
#   --also-pinned <label>
#                  additionally tolerate the paths already pinned for <label>
#                  (repeatable). It resolves through the same pin table as
#                  --label and can therefore tolerate nothing that is not
#                  already recorded debt. It exists for the one case where a
#                  write cannot be attributed to a single script: the test
#                  runner's concurrent phase, where several scripts share one
#                  checkout, names the phase rather than a script, and passes
#                  the label of every script admitted to that phase. A path no
#                  admitted script is pinned for is still a violation.
#
# Environment:
#   FM_CHECKOUT_WRITE_GUARD=off   disable the guard. It reports that it is off
#                  rather than passing silently, so a run that skipped the
#                  guarantee cannot be mistaken for one that satisfied it. The
#                  escape hatch exists so a blocked caller edits one variable
#                  instead of deleting the enforcement.
#
# Markers (stdout, `compare` and `run`):
#   FM_CHECKOUT_WRITE <label> <created|removed|modified> <path>
#   FM_CHECKOUT_WRITE_PINNED <label> <created|removed|modified> <path>
#   FM_CHECKOUT_WRITE_EXEMPT <label> <created|removed|modified> <path>
#   FM_CHECKOUT_WRITE_GUARD_OFF <label>
#
# Exit status:
#   0  no unpinned change under the checkout (or the guard is off)
#   1  the guarded command changed the checkout outside its pins, or the
#      command itself failed under `run` (its status is preserved)
#   2  usage or snapshot error
#
# What it detects: any created, removed, or resized/retimed path under the
# checkout, `.git` excluded, including inside gitignored directories - which is
# where the original defect lived and where `git status` alone cannot see it.
# Tracked-file edits are additionally caught by content, via git; when git
# cannot be consulted - not a repository, or its index momentarily locked - that
# extra check is skipped and detection falls back to the path/size/mtime
# inventory rather than reporting a change nobody made. The one residual gap is
# a same-size, same-mtime rewrite of an already-present untracked file; a test
# doing that is not the defect class this guards.
set -eu

SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEFAULT_ROOT="$(cd "$SELF_DIR/.." && pwd)"

ROOT=$DEFAULT_ROOT
LABEL=
ALLOWS=()
ALSO_PINNED=()

die() {
  printf 'fm-checkout-write-guard: %s\n' "$*" >&2
  exit 2
}

usage() {
  awk '
    NR == 1 { next }
    /^#/ { sub(/^# ?/, ""); print; next }
    { exit }
  ' "$0" >&2
}

# Leaks that predate this guard, one row per test script: the script, the exact
# paths it may still touch, and why. This table is the only place that data
# lives; --list-pins prints it.
#
# A pin is recorded debt, not an exemption. A pinned script writes only what its
# row names and an unpinned script writes nothing at all, so the table can only
# shrink. Clear a row by giving that test a home of its own - see
# docs/fm-checkout-write-guard.md - never by widening its globs, and never add a
# row to make a newly written script pass.
#
# Nearly every row leaks for one reason: the script drives a firstmate script
# with FM_HOME unset or cleared, and bin/fm-wake-lib.sh creates "$FM_HOME/state"
# at source time, which then resolves to the checkout.
#
# Rows are TAB-separated: <script>\t<space-separated globs>\t<reason>
pin_table() {
  cat <<'EOF'
fm-afk-inject-herdr-e2e.test.sh	./state ./state/*	Herdr-driving; UNMEASURED, pinned so the Herdr lane cannot go red on a pre-existing leak
fm-afk-launch.test.sh	./state ./state/*	Herdr-driving; UNMEASURED, pinned so the Herdr lane cannot go red on a pre-existing leak
fm-backend-autodetect-smoke.test.sh	./state ./state/*	Herdr-driving; UNMEASURED, pinned so the Herdr lane cannot go red on a pre-existing leak
fm-backend-herdr-eventwait-smoke.test.sh	./state ./state/*	Herdr-driving; UNMEASURED, pinned so the Herdr lane cannot go red on a pre-existing leak
fm-backend-herdr-focus-flash-e2e.test.sh	./state ./state/*	Herdr-driving; UNMEASURED, pinned so the Herdr lane cannot go red on a pre-existing leak
fm-backend-herdr-launcher-workspace-e2e.test.sh	./state ./state/*	Herdr-driving; UNMEASURED, pinned so the Herdr lane cannot go red on a pre-existing leak
fm-backend-herdr-presentation-e2e.test.sh	./state ./state/*	Herdr-driving; UNMEASURED, pinned so the Herdr lane cannot go red on a pre-existing leak
fm-backend-herdr-prune-safety-e2e.test.sh	./state ./state/*	Herdr-driving; UNMEASURED, pinned so the Herdr lane cannot go red on a pre-existing leak
fm-backend-herdr-respawn-idem-e2e.test.sh	./state ./state/*	Herdr-driving; UNMEASURED, pinned so the Herdr lane cannot go red on a pre-existing leak
fm-backend-herdr-smoke.test.sh	./state ./state/*	Herdr-driving; UNMEASURED, pinned so the Herdr lane cannot go red on a pre-existing leak
fm-backend-herdr-workspace-per-home-e2e.test.sh	./state ./state/*	Herdr-driving; UNMEASURED, pinned so the Herdr lane cannot go red on a pre-existing leak
fm-backend-herdr.test.sh	./state ./state/*	Herdr-driving; UNMEASURED, pinned so the Herdr lane cannot go red on a pre-existing leak
fm-backend-orca.test.sh	./state	creates state/ with FM_HOME unset (measured 2026-09-09)
fm-backlog-handoff.test.sh	./state	creates state/ with FM_HOME unset (measured 2026-09-09)
fm-control-herdr-smoke.test.sh	./state ./state/*	Herdr-driving; UNMEASURED, pinned so the Herdr lane cannot go red on a pre-existing leak
fm-control-relaunch.test.sh	./state ./state/*	creates state/ with FM_HOME unset (2026-09-09 census, not re-measured)
fm-control.test.sh	./state	creates state/ with FM_HOME unset (measured 2026-09-09)
fm-gate-refuse.test.sh	./state	creates state/ with FM_HOME unset (measured 2026-09-09)
fm-herdr-lab.test.sh	./state ./state/*	Herdr-driving; UNMEASURED, pinned so the Herdr lane cannot go red on a pre-existing leak
fm-herdr-session-cleanup-e2e.test.sh	./state ./state/*	Herdr-driving; UNMEASURED, pinned so the Herdr lane cannot go red on a pre-existing leak
fm-herdr-session-cleanup.test.sh	./state ./state/*	Herdr-driving; UNMEASURED, pinned so the Herdr lane cannot go red on a pre-existing leak
fm-omp-harness.test.sh	./state	creates state/ with FM_HOME unset (measured 2026-09-09)
fm-pending-reply.test.sh	./state	creates state/ with FM_HOME unset (measured 2026-09-09)
fm-procevent-quota.test.sh	./state	creates state/ with FM_HOME unset (measured 2026-09-09)
fm-procevent.test.sh	./state	creates state/ with FM_HOME unset (measured 2026-09-09)
fm-public-followup.test.sh	./state	creates state/ with FM_HOME unset (measured 2026-09-09)
fm-secondmate-harness.test.sh	./state	creates state/ with FM_HOME unset (measured 2026-09-09)
fm-secondmate-lifecycle-e2e.test.sh	./state	creates state/ with FM_HOME unset (measured 2026-09-09)
fm-secondmate-reconcile.test.sh	./state	creates state/ with FM_HOME unset (measured 2026-09-09)
fm-secondmate-safety.test.sh	./state	creates state/ with FM_HOME unset (measured 2026-09-09)
fm-send-inbox.test.sh	./state	creates state/ with FM_HOME unset (measured 2026-09-09)
fm-send-remote-delivery.test.sh	./state	creates state/ with FM_HOME unset (measured 2026-09-09)
fm-send-resolve-key.test.sh	./state	creates state/ with FM_HOME unset (measured 2026-09-09)
fm-send-secondmate-marker.test.sh	./state	creates state/ with FM_HOME unset (measured 2026-09-09)
fm-spawn-batch.test.sh	./state	creates state/ with FM_HOME unset (measured 2026-09-09)
fm-startup-memory-budget.test.sh	./state	creates state/ with FM_HOME unset (measured 2026-09-09)
fm-teardown-endpoint-safety.test.sh	./state	creates state/ with FM_HOME unset (measured 2026-09-09)
fm-teardown.test.sh	./state	creates state/ with FM_HOME unset (measured 2026-09-09)
fm-voice-relay.test.sh	./bin/__pycache__ ./bin/__pycache__/*	python bytecode cache written by running bin/*.py from the checkout; clear it with PYTHONDONTWRITEBYTECODE=1 in that test
fm-watch-triage.test.sh	./state ./state/*	creates state/ with FM_HOME unset (2026-09-09 census, not re-measured)
EOF
}

pinned_paths() {  # <label> -> its globs, one per line; non-zero when unpinned
  local row
  row=$(pin_table | awk -F'\t' -v want="$1" '$1 == want { print $2; exit }')
  [ -n "$row" ] || return 1
  # Deliberate word splitting: the field holds space-separated globs, and they
  # must stay unquoted patterns for the caller's `case` to match against.
  # shellcheck disable=SC2086
  printf '%s\n' $row
}

pin_reason() {  # <label>
  local row
  row=$(pin_table | awk -F'\t' -v want="$1" '$1 == want { print $3; exit }')
  [ -n "$row" ] || return 1
  printf '%s\n' "$row"
}

list_pins() {
  pin_table
}

resolve_stat_cmd() {
  local cand
  for cand in /usr/bin/stat /bin/stat "$(command -v stat 2>/dev/null || true)"; do
    [ -n "$cand" ] && [ -x "$cand" ] || continue
    if "$cand" -f '%z' . >/dev/null 2>&1; then
      STAT_CMD=("$cand" -f '%z	%m	%N')
      return 0
    fi
    if "$cand" -c '%s' . >/dev/null 2>&1; then
      STAT_CMD=("$cand" -c '%s	%Y	%n')
      return 0
    fi
  done
  return 1
}
STAT_CMD=()
resolve_stat_cmd || die 'no usable stat(1): cannot inventory the checkout'

# One line per path under <root>, `.git` pruned:
#   d\t-\t-\t<path>        directories (mtime deliberately omitted: it moves
#                          whenever a child appears, which the child's own line
#                          already records)
#   f\t<size>\t<mtime>\t<path>   everything else
# A path carrying a tab or a newline cannot be represented on one line, so the
# inventory refuses rather than silently mis-parsing it into a wrong verdict.
snapshot() {  # <root> <out>
  local root=$1 out=$2 tmp bad
  [ -d "$root" ] || die "root is not a directory: $root"
  tmp="${out}.partial"
  : >"$tmp"
  (
    cd "$root" || exit 1
    find . -name .git -prune -o -type d -print | sed 's/^/d	-	-	/'
    find . -name .git -prune -o ! -type d -exec "${STAT_CMD[@]}" {} + | sed 's/^/f	/'
  ) >>"$tmp" || die "could not inventory $root"
  bad=$(awk -F'	' 'NF != 4 { print NR; exit }' "$tmp")
  [ -z "$bad" ] || die "unrepresentable path in $root (tab or newline) at inventory line $bad"
  LC_ALL=C sort "$tmp" -o "$tmp"
  mv "$tmp" "$out"
}

# Tracked-file content divergence, so an in-place edit of a tracked file that
# preserves size and mtime is still caught.
git_snapshot() {  # <root>
  git -C "$1" status --porcelain 2>/dev/null | LC_ALL=C sort || true
}

# Paths under the checkout that belong to something OTHER than the test and can
# legitimately change while the suite runs. These are not pins: no test is
# expected to touch them, and attributing them to whichever script happened to
# be running would be wrong rather than lenient.
#   ./.no-mistakes  the validation pipeline's own evidence, written by the
#                   no-mistakes daemon while it is driving this very suite.
#   .DS_Store       created by the operating system's file browser, never by a
#                   test, and only ever on a developer's machine.
structural_exemption() {  # <path>
  case "$1" in
    ./.no-mistakes|./.no-mistakes/*) return 0 ;;
    ./.DS_Store|*/.DS_Store) return 0 ;;
  esac
  return 1
}

path_is_allowed() {  # <label> <path>
  local label=$1 path=$2 glob
  for glob in ${ALLOWS[@]+"${ALLOWS[@]}"}; do
    # shellcheck disable=SC2254  # the glob is meant to be a pattern
    case "$path" in $glob) return 0 ;; esac
  done
  local extra
  for extra in ${ALSO_PINNED[@]+"${ALSO_PINNED[@]}"}; do
    while IFS= read -r glob; do
      [ -n "$glob" ] || continue
      # shellcheck disable=SC2254  # the pin entry is meant to be a pattern
      case "$path" in $glob) return 0 ;; esac
    done < <(pinned_paths "$extra" || true)
  done
  [ -n "$label" ] || return 1
  while IFS= read -r glob; do
    [ -n "$glob" ] || continue
    # shellcheck disable=SC2254  # the pin entry is meant to be a pattern
    case "$path" in $glob) return 0 ;; esac
  done < <(pinned_paths "$label" || true)
  return 1
}

compare() {  # <before> <after> <git-before> <git-after>
  local before=$1 after=$2 gbefore=$3 gafter=$4
  local violations=0 pinned=0 line op path
  local diff_out
  diff_out=$(awk -F'\t' '
    NR == FNR { b[$4] = $0; next }
    { a[$4] = $0
      if (!($4 in b)) { print "created\t" $4 }
      else if (a[$4] != b[$4]) { print "modified\t" $4 } }
    END { for (p in b) if (!(p in a)) print "removed\t" p }
  ' "$before" "$after" | LC_ALL=C sort)

  if [ "$gbefore" != "$gafter" ]; then
    # A tracked path whose recorded status changed but whose size and mtime did
    # not; report it under the same contract.
    while IFS= read -r line; do
      [ -n "$line" ] || continue
      path="./${line#???}"
      case "$diff_out" in
        *"	$path"*) continue ;;
      esac
      diff_out="${diff_out}
modified	$path"
    done < <(comm -13 <(printf '%s\n' "$gbefore") <(printf '%s\n' "$gafter"))
  fi

  while IFS= read -r line; do
    [ -n "$line" ] || continue
    op=${line%%	*}
    path=${line#*	}
    if structural_exemption "$path"; then
      printf 'FM_CHECKOUT_WRITE_EXEMPT %s %s %s\n' "${LABEL:-<unlabelled>}" "$op" "$path"
      continue
    fi
    if path_is_allowed "$LABEL" "$path"; then
      printf 'FM_CHECKOUT_WRITE_PINNED %s %s %s\n' "${LABEL:-<unlabelled>}" "$op" "$path"
      pinned=$((pinned + 1))
      continue
    fi
    printf 'FM_CHECKOUT_WRITE %s %s %s\n' "${LABEL:-<unlabelled>}" "$op" "$path"
    violations=$((violations + 1))
  done < <(printf '%s\n' "$diff_out")

  if [ "$violations" -gt 0 ]; then
    printf 'fm-checkout-write-guard: %s changed %s path(s) under the repository checkout %s\n' \
      "${LABEL:-the guarded command}" "$violations" "$ROOT" >&2
    printf 'fm-checkout-write-guard: a test must keep its state in a temporary directory it owns; see this script'"'"'s header\n' >&2
    return 1
  fi
  [ "$pinned" -eq 0 ] || printf 'fm-checkout-write-guard: %s wrote %s pinned path(s); the pin is recorded debt, not an exemption\n' \
    "${LABEL:-the guarded command}" "$pinned" >&2
  return 0
}

guard_is_off() {
  [ "${FM_CHECKOUT_WRITE_GUARD:-on}" = off ]
}

# Options may precede or follow the mode word; `--` ends option parsing and
# hands everything after it to `run` as the guarded command.
MODE=
POSITIONAL=()
CMD=()
[ "$#" -gt 0 ] || { usage; exit 2; }
while [ "$#" -gt 0 ]; do
  case "$1" in
    --root) [ "$#" -gt 1 ] || die "--root requires a directory"; ROOT=$2; shift 2 ;;
    --root=*) ROOT=${1#--root=}; shift ;;
    --label) [ "$#" -gt 1 ] || die "--label requires a name"; LABEL=$2; shift 2 ;;
    --label=*) LABEL=${1#--label=}; shift ;;
    --allow) [ "$#" -gt 1 ] || die "--allow requires a glob"; ALLOWS+=("$2"); shift 2 ;;
    --allow=*) ALLOWS+=("${1#--allow=}"); shift ;;
    --also-pinned)
      [ "$#" -gt 1 ] || die "--also-pinned requires a label"
      ALSO_PINNED+=("$2"); shift 2 ;;
    --also-pinned=*) ALSO_PINNED+=("${1#--also-pinned=}"); shift ;;
    --list-pins) list_pins; exit 0 ;;
    -h|--help) usage; exit 0 ;;
    --) shift; CMD=("$@"); break ;;
    -*) die "unknown option: $1" ;;
    *)
      if [ -z "$MODE" ]; then MODE=$1; else POSITIONAL+=("$1"); fi
      shift
      ;;
  esac
done

case "$MODE" in
  snapshot|compare|run) ;;
  '') die "no mode given (snapshot, compare, or run)" ;;
  *) die "unknown mode: $MODE" ;;
esac

ROOT=$(cd "$ROOT" 2>/dev/null && pwd) || die "root is not a directory: $ROOT"

case "$MODE" in
  snapshot)
    [ "${#POSITIONAL[@]}" -eq 1 ] || die "snapshot takes exactly one output path"
    if guard_is_off; then
      : >"${POSITIONAL[0]}"
      exit 0
    fi
    snapshot "$ROOT" "${POSITIONAL[0]}"
    git_snapshot "$ROOT" >"${POSITIONAL[0]}.git"
    ;;
  compare)
    [ "${#POSITIONAL[@]}" -eq 2 ] || die "compare takes exactly two snapshot paths"
    if guard_is_off; then
      printf 'FM_CHECKOUT_WRITE_GUARD_OFF %s\n' "${LABEL:-<unlabelled>}"
      exit 0
    fi
    for f in "${POSITIONAL[0]}" "${POSITIONAL[1]}"; do
      [ -f "$f" ] || die "snapshot not found: $f"
    done
    compare "${POSITIONAL[0]}" "${POSITIONAL[1]}" \
      "$(cat "${POSITIONAL[0]}.git" 2>/dev/null || true)" \
      "$(cat "${POSITIONAL[1]}.git" 2>/dev/null || true)"
    ;;
  run)
    [ "${#CMD[@]}" -gt 0 ] || die "run requires -- <command>"
    if guard_is_off; then
      printf 'FM_CHECKOUT_WRITE_GUARD_OFF %s\n' "${LABEL:-<unlabelled>}"
      "${CMD[@]}"
      exit $?
    fi
    WORK=$(mktemp -d "${TMPDIR:-/tmp}/fm-checkout-write-guard.XXXXXX")
    trap 'rm -rf "$WORK"' EXIT
    snapshot "$ROOT" "$WORK/before"
    git_snapshot "$ROOT" >"$WORK/before.git"
    set +e
    "${CMD[@]}"
    CMD_RC=$?
    set -e
    snapshot "$ROOT" "$WORK/after"
    git_snapshot "$ROOT" >"$WORK/after.git"
    set +e
    compare "$WORK/before" "$WORK/after" \
      "$(cat "$WORK/before.git")" "$(cat "$WORK/after.git")"
    GUARD_RC=$?
    set -e
    [ "$CMD_RC" -eq 0 ] || exit "$CMD_RC"
    exit "$GUARD_RC"
    ;;
esac
