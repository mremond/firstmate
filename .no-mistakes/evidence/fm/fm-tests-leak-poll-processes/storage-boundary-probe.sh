#!/usr/bin/env bash
set -u
. "$PWD/tests/lib.sh"
active=$(fm_test_tmproot fm-probe-active)
fresh=$(fm_test_tmproot fm-probe-fresh)
stale=$(fm_test_tmproot fm-probe-stale)
printf '%s\n%s\n' "$$" deliberately-obsolete-owner-identity > "$stale/.fm-test-fixture"
: > "$fresh/.fm-test-fixture"
touch -t 202001010000 "$active/.fm-test-fixture" "$stale/.fm-test-fixture"
fm_test_reap_orphans
[ -d "$active" ] && [ -d "$fresh" ] && [ ! -e "$stale" ] || fail 'age/ownership boundary failed'
printf 'owner_pid=%s old_live_owner_preserved=true fresh_unowned_preserved=true old_reused_identity_removed=true\n' "$$"
claim_root=$FM_PROCEVENT_CLAIM_ROOT
FM_INHERITED_EXPECTED="$claim_root" bash -c '. "$1"; [ "$FM_PROCEVENT_CLAIM_ROOT" = "$FM_INHERITED_EXPECTED" ] || exit 1; fm_test_cleanup; [ -d "$FM_INHERITED_EXPECTED" ] || exit 1' _ "$ROOT/tests/lib.sh" || fail 'inherited claim root was removed'
printf 'inherited_claim_root=%s child_cleanup_preserved_parent_root=true\n' "$claim_root"
fixture=$(fm_test_tmproot fm-probe-claim-store)
make_home() {
  mkdir -p "$fixture/home/state"
  fm_test_track_procevent_home "$fixture/home"
  printf '%s\n' "$fixture/home"
}
home=$(make_home)
export XDG_STATE_HOME="$fixture/xdg-state"
FM_HOME="$home" FM_STATE_OVERRIDE="$home/state" "$ROOT/bin/fm-procevent.sh" register lavish claim-store-probe -- /bin/sleep 120
FM_HOME="$home" FM_STATE_OVERRIDE="$home/state" "$ROOT/bin/fm-procevent.sh" reconcile
tries=0
while [ ! -s "$claim_root/claim-store-probe.claim" ] && [ "$tries" -lt 300 ]; do sleep 0.1; tries=$((tries + 1)); done
[ -s "$claim_root/claim-store-probe.claim" ] || fail 'real runner did not take its isolated claim'
[ ! -e "$XDG_STATE_HOME/firstmate/procevent-claims" ] || fail 'real runner escaped the suite claim root'
printf 'claim_path=%s/claim-store-probe.claim fallback_claim_store_exists=false\n' "$claim_root"
cat "$claim_root/claim-store-probe.claim"
fm_test_cleanup
[ ! -e "$fixture" ] && [ ! -e "$claim_root" ] || fail 'fixture teardown left owned roots'
printf 'after_cleanup fixture_exists=false claim_root_exists=false\n'
