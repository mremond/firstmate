#!/usr/bin/env python3
"""Drive the real assertion with isolated signal/cleanup mutations; never edit target."""
import os,pathlib,subprocess as sp,shutil,signal,time
R=pathlib.Path('/Users/mremond/.no-mistakes/worktrees/acf4a767348a/01M22Z7YQYD4K70MWCSC6FV3P4')
E=pathlib.Path('/Users/mremond/.no-mistakes/evidence/01M22Z7YQYD4K70MWCSC6FV3P4')
W=R/'.test-phase'; runtime=W/'diagnostic-runtime';shutil.copytree(R/'bin',runtime/'bin',dirs_exist_ok=True)
src=(runtime/'bin/fm-watch.sh').read_text()
# Both handler sites are mutated together. Returning from TERM deliberately keeps
# the watcher alive. Cleanup no-op leaves the real check's orphan available for
# the recorded-child diagnostic, whose parent exited before ps takes its snapshot.
src=src.replace("trap 'exit 1' HUP INT TERM", "trap 'echo injected-stop-refusal >&2; bash \"$FM_DIAG_TREE\" &' HUP INT TERM")
src=src.replace('fm_active_check_stop() {','fm_active_check_stop() {\n  return 0 # isolated diagnostic fault: leave orphan check descendant')
(runtime/'bin/fm-watch.sh').write_text(src)
leaf=W/'diagnostic-leaf.sh';leaf.write_text('sleep 90 &\nwait\n')
branch=W/'diagnostic-branch.sh';branch.write_text('bash "$FM_DIAG_LEAF" &\nwait\n')
base=(R/'tests/fm-pr-check-security.test.sh').read_text().split('\ntest_parser_matrix\n')[0]
# Preserve the 150-poll loop. Only prolong the intentionally orphaned fixture so
# the failure transcript can demonstrate the recorded pid after reparenting.
base=base.replace('for backend in installed-timeout fallback-timeout; do','for backend in fallback-timeout; do')
base=base.replace('select undef, undef, undef, 4; open my $sentinel','select undef, undef, undef, 90; open my $sentinel')
env={k:v for k,v in os.environ.items() if not k.startswith('FM_')}
env.update(TMPDIR=str(W/'tmp'),FM_TEST_SKIP_ORPHAN_REAP='1',FM_DIAG_TREE=str(branch),FM_DIAG_LEAF=str(leaf))
transcript=[]
for name,extra,expected in [
    ('diagnostic-live','', 'watcher did not stop after the direct check returned'),
    ('diagnostic-unknown', '''
# Inject a silent ps only into the test caller; production watcher keeps real ps.
ps() {
  if [ "${1:-}" = -p ] && [ "${3:-}" = -o ] && [ "${4:-}" = stat= ]; then return 0; fi
  command ps "$@"
}
''', 'watcher liveness was unreadable after the direct check returned')]:
    runner=R/'tests'/('.phase-'+name+'.sh')
    runner.write_text(base+'\nWATCH='+str(runtime/'bin/fm-watch.sh')+'\n'+extra+'''
phase_cleanup() {
  for f in "$TMP_ROOT"/*/descendant.pid; do
    [ -f "$f" ] || continue
    kill -KILL "$(cat "$f")" 2>/dev/null || true
  done
  fm_test_cleanup
}
trap phase_cleanup EXIT
set -e
test_returned_custom_check_descendants_are_drained
''')
    try:
        with open(E/(name+'.out'),'w') as out,open(E/(name+'.err'),'w') as err:
            p=sp.Popen(['bash',str(runner)],cwd=R,env=env,stdout=out,stderr=err,start_new_session=True)
            try:rc=p.wait(timeout=75)
            finally:
                try:os.killpg(p.pid,signal.SIGKILL)
                except ProcessLookupError:pass
        emitted=(E/(name+'.err')).read_text()
        msg=f'{name}: expected rejection exit={rc}\n{emitted}'
        print(msg,flush=True);transcript.append(msg)
        assert rc!=0 and expected in emitted
        assert '(150 polls)' in emitted and 'wchan args' in emitted and 'stderr tail:' in emitted
        assert 'recorded child pid' in emitted and 'injected-stop-refusal' in emitted
        assert 'diagnostic-branch.sh' in emitted and 'diagnostic-leaf.sh' in emitted
        # This inspects the emitted process table (public diagnostic output), not source.
        assert 'perl -e' in emitted, 'reparented recorded child omitted from emitted process table'
        if name=='diagnostic-unknown':assert 'UNKNOWN, not live' in emitted and 'still unreadable' in emitted
        else:assert 'still live' in emitted
    finally:runner.unlink(missing_ok=True)
(E/'diagnostic-transcript.txt').write_text('\n'.join(transcript))
