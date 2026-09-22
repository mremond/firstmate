#!/usr/bin/env python3
"""Execute only the two requested regressions and their immediate neighbours.
Test definitions/assertions are unchanged. Dependencies use existing fixture fakes.
Temporary selectors and fixture roots stay in the worktree and are removed.
"""
from pathlib import Path
import os, subprocess, tempfile, shutil, sys, time, json
ROOT=Path('/Users/mremond/.no-mistakes/worktrees/acf4a767348a/01M34NDX8QZN4VKXAMPETHR74Q')
EVIDENCE=Path('/Users/mremond/.no-mistakes/evidence/01M34NDX8QZN4VKXAMPETHR74Q')
BASE='6f0f139962eadaea29487cafead418a0eb2ec6e4'
mode='base' if '--base' in sys.argv else 'target'
selections=[('fm-crew-state.test.sh','test_captured_axi_status_shapes',[
 'test_terminal_passed', 'test_terminal_passed_with_override',
 'test_terminal_passed_uses_matching_retirement_receipt_without_forge']),
 ('fm-teardown.test.sh','test_local_only_fork_remote_allows',[
 'test_parked_own_run_is_aborted_before_teardown',
 'test_parked_own_run_concludes_on_passed_with_override_after_abort',
 'test_parked_run_advanced_past_unfetched_head_is_still_aborted'])]
results=[]
with tempfile.TemporaryDirectory(prefix='.nm4522-targeted-',dir=ROOT) as tmp:
 scratch=Path(tmp)
 if mode=='base':
  basebin=scratch/'base'/'bin'; basebin.mkdir(parents=True)
  for path in (ROOT/'bin').iterdir():
   dst=basebin/path.name
   if path.name in ['fm-crew-state.sh','fm-teardown.sh']:
    dst.write_bytes(subprocess.check_output(['git','show',BASE+':bin/'+path.name],cwd=ROOT))
    dst.chmod(0o755)
   else: dst.symlink_to(path)
 for suite,footer,selected in selections:
  if mode=='base': selected=selected[1:2]
  source=(ROOT/'tests'/suite).read_text()
  definitions, sep, _=source.partition('\n'+footer+'\n')
  if not sep: raise RuntimeError('suite footer not found')
  instrument=r'''
# Evidence capture only; preserve the suite's existing executable calls and assertions.
if declare -F run_crew_state >/dev/null; then
  eval "$(declare -f run_crew_state | sed '1s/run_crew_state/nm_original_run_crew_state/')"
  run_crew_state() {
    local nm_out nm_rc=0
    nm_out=$(nm_original_run_crew_state "$@") || nm_rc=$?
    printf '\nFIXTURE AXI INPUT:\n%s\nPRODUCT OUTPUT (exit %s):\n%s\n' "$FM_FAKE_AXI_STATUS" "$nm_rc" "$nm_out" >&3
    printf '%s\n' "$nm_out"
    return "$nm_rc"
  }
fi
if declare -F run_teardown >/dev/null; then
  eval "$(declare -f run_teardown | sed '1s/run_teardown/nm_original_run_teardown/')"
  run_teardown() {
    local nm_rc=0
    printf '\nFIXTURE AXI INPUT:\n%s\nFIXTURE STATUS AFTER ABORT:\n%s\n' "${FM_FAKE_AXI_STATUS:-}" "${FM_FAKE_AXI_STATUS_AFTER_ABORT:-outcome: cancelled}" >&3
    nm_original_run_teardown "$@" > "$1/evidence-stdout" 2> "$1/evidence-stderr" || nm_rc=$?
    printf 'PRODUCT EXIT: %s\nPRODUCT STDOUT:\n' "$nm_rc" >&3
    cat "$1/evidence-stdout" >&3
    printf 'PRODUCT STDERR:\n' >&3
    cat "$1/evidence-stderr" >&3
    if [ -f "$1/nm-abort.log" ]; then
      printf 'FAKE NO-MISTAKES CALL LOG:\n' >&3
      cat "$1/nm-abort.log" >&3
    fi
    cat "$1/evidence-stdout"
    cat "$1/evidence-stderr" >&2
    return "$nm_rc"
  }
fi
'''
  if mode=='base':
   instrument += '\nCREW_STATE="'+str(basebin/'fm-crew-state.sh')+'"\nTEARDOWN="'+str(basebin/'fm-teardown.sh')+'"\n'
  body=definitions+'\nexec 3>&1\n'+instrument
  for name in selected: body+='\nprintf "\\nTEST: '+name+'\\n"\n'+name+'\n'
  selector=ROOT/'tests'/('.nm4522-selected-'+mode+'-'+suite)
  selector.write_text(body)
  env=os.environ.copy()
  for key in ['FM_HOME','FM_ROOT','FM_STATE_OVERRIDE','FM_DATA_OVERRIDE','FM_CONFIG_OVERRIDE','FM_ROOT_OVERRIDE','NM_HOME']:
   env.pop(key,None)
  home=scratch/(suite+'.home'); home.mkdir()
  env.update(TMPDIR=str(scratch),FM_HOME=str(home),FM_ROOT_OVERRIDE=str(ROOT),FM_TEST_SKIP_ORPHAN_REAP='1',NM_HOME=str(scratch/'nm-unused'))
  logfile=EVIDENCE/(suite+'.'+mode+'.txt')
  start=time.monotonic()
  print('Starting',mode,suite,selected,flush=True)
  try:
   with logfile.open('w') as log:
    log.write('FIXTURE-BASED BEHAVIORAL VALIDATION; NOT LIVE.\n'+mode+' '+suite+'\n');log.flush()
    result=subprocess.run(['bash',str(selector)],cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=540)
   record=dict(mode=mode,suite=suite,tests=selected,exit_code=result.returncode,seconds=round(time.monotonic()-start,2),log=str(logfile))
   results.append(record); print(json.dumps(record),flush=True)
  finally: selector.unlink(missing_ok=True)
(EVIDENCE/('results-'+mode+'.json')).write_text(json.dumps(results,indent=2)+'\n')
expected=1 if mode=='base' else 0
sys.exit(0 if all(r['exit_code']==expected for r in results) else 1)
