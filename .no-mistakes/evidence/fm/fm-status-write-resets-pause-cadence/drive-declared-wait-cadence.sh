#!/usr/bin/env bash
# Drives the real bin/fm-watch.sh (fake tmux pane, isolated FM_STATE_OVERRIDE) through:
# declared wait -> first stale wake -> ack -> no-change status write -> stale poll
# -> cadence elapsed -> changed declaration. Prints the wake queue after each step.
# Usage: drive-declared-wait-cadence.sh <checkout-root-with-tests>
R=$1
src=$(mktemp); awk 'NR<5240' "$R/tests/fm-watch-triage.test.sh" | sed "s#\$(dirname \"\${BASH_SOURCE\[0\]}\")#$R/tests#" > "$src"
. "$src"
q() { awk -F '\t' '$3=="stale"{print "    WAKE: "$5}' "$state/.wake-queue" 2>/dev/null; n=$(awk -F '\t' '$3=="stale"{n++}END{print n+0}' "$state/.wake-queue" 2>/dev/null); echo "    stale wakes queued (unacked): ${n:-0}"; }
for spec in 'paused|paused: waiting on validation run one|paused: waiting on validation run two' \
            'captain-held|captain-held [key=route]: awaiting the routing call|captain-held [key=route]: awaiting the release call'; do
  label=${spec%%|*}; spec=${spec#*|}; initial=${spec%%|*}; changed=${spec#*|}
  dir=$(make_case "drive-$label"); state="$dir/state"; fakebin="$dir/fakebin"; out="$dir/watch.out"; cap="$dir/pane.txt"; statusf="$state/held.status"; window=test:fm-held
  printf 'window=%s\nkind=ship\nharness=grok\nbackend=tmux\n' "$window" > "$state/held.meta"
  printf '%s\n' "$initial" > "$statusf"; set_mtime "$(( $(date +%s) - 500 ))" "$statusf"
  printf '%s' "$(seen_sig "$statusf")" > "$state/.seen-held_status"
  key=$(printf '%s' "$window" | tr ':/.' '___')
  printf 'idle after agent exit\n' > "$cap"; printf '%s' "$(hash_text 'idle after agent exit')" > "$state/.hash-$key"; printf '1\n' > "$state/.count-$key"
  echo "=== [$label] step 1: wait declared 500s ago -> first stale inspection (expect 1 wake)"
  absorbed_wait_round "$state" "$fakebin" "$out" "$cap" "$window" exit && echo "    watcher exited (surfaced)" || echo "    watcher did NOT surface"
  q; ack_stopped_cycle "$state" >/dev/null && echo "    (acked)"
  for write in "$initial" 'continuation of the same wait, nothing changed'; do
    echo "=== [$label] step 2: status write that keeps the wait: '$write' (expect 0 wakes before cadence)"
    printf '%s\n' "$write" >> "$statusf"; printf '%s' "$(seen_sig "$statusf")" > "$state/.seen-held_status"
    printf 'idle after write: %s\n' "$write" > "$cap"
    absorbed_wait_round "$state" "$fakebin" "$out" "$cap" "$window" absorb && echo "    watcher stayed in its poll loop (absorbed) for 4 cycles" || echo "    watcher EXITED/surfaced"
    q; ack_stopped_cycle "$state" >/dev/null 2>&1 && echo "    (acked a wake)"
  done
  echo "=== [$label] step 3: cadence elapsed (expect 1 recheck, age >= 500s, anchored on declaration)"
  set_mtime "$(( $(date +%s) - 2000 ))" "$state/.paused-resurfaced-$key"; printf 'idle once cadence elapsed\n' > "$cap"
  absorbed_wait_round "$state" "$fakebin" "$out" "$cap" "$window" exit && echo "    watcher exited (surfaced)" || echo "    watcher did NOT surface"
  q; ack_stopped_cycle "$state" >/dev/null 2>&1
  echo "=== [$label] step 4: changed declaration '$changed' (expect immediate wake)"
  printf '%s\n' "$changed" >> "$statusf"; printf '%s' "$(seen_sig "$statusf")" > "$state/.seen-held_status"; printf 'idle after changed\n' > "$cap"
  absorbed_wait_round "$state" "$fakebin" "$out" "$cap" "$window" exit && echo "    watcher exited (surfaced)" || echo "    watcher did NOT surface"
  q
done
