from pathlib import Path
import os,subprocess,json,signal,sys
unknown = len(sys.argv)>1 and sys.argv[1]=="unknown"
root=Path.cwd(); ev=Path('/Users/mremond/.no-mistakes/evidence/01M2JEJPE43XFXJCGYM3KFAX75')
s=(root/'tests/fm-pr-check-security.test.sh').read_text()
s=s[:s.rindex('\ntest_parser_matrix\n')]
s=s.replace('for backend in installed-timeout fallback-timeout; do','for backend in fallback-timeout; do')
s=s.replace('PATH="$fakebin:$BASE_PATH" "$WATCH"', 'PATH="$PATH" "$WATCH"')
# Fault injection: freeze the REAL watcher from its custom check after recording
# direct completion. The check returns normally; its child and grandchild stay
# alive so the unchanged stop assertion has an actual descendant tree to show.
old="perl -e '$SIG{TERM}=\"IGNORE\"; open my $ready, \">\", $ENV{FM_TEST_DESCENDANT_READY} or die $!; print {$ready} \"ready\\n\"; close $ready; select undef, undef, undef, 4; open my $sentinel, \">\", $ENV{FM_TEST_DESCENDANT_SENTINEL} or die $!; print {$sentinel} \"late\\n\"; close $sentinel; select undef, undef, undef, 1' &"
new="perl -e '$SIG{TERM}=\"IGNORE\"; my $g=fork; die $! unless defined $g; if (!$g) {sleep 60; exit} open my $gf, \">\", $ENV{NM_GRANDCHILD} or die $!; print {$gf} \"$g\\n\"; close $gf; open my $ready, \">\", $ENV{FM_TEST_DESCENDANT_READY} or die $!; print {$ready} \"ready\\n\"; close $ready; sleep 60' &"
if old not in s: raise SystemExit('fixture payload not found')
s=s.replace(old,new)
s=s.replace(': > "$FM_TEST_DIRECT_DONE"\nSH',': > "$FM_TEST_DIRECT_DONE"\nkill -STOP "$(cat "$FM_HOME/state/.watch.lock/pid")"\nSH')
# The stopped watcher cannot publish its post-drain .last-check. Readiness for
# this negative scenario is direct completion, already written by the check.
s=s.replace(' && [ -e "$state/.last-check" ]','')
s=s.replace('      && [ -e "$state/.last-check" ] \\\n','')
if unknown:
    s=s.replace('is_live_non_zombie \"$watcher_pid\" || watcher_state=$?', 'PATH=\"\" is_live_non_zombie \"$watcher_pid\" || watcher_state=$?')
s+='\ntest_returned_custom_check_descendants_are_drained\n'
p=root/'tests/.nm-phase-live-diagnostic.sh'; p.write_text(s)
e=os.environ.copy();e['TMPDIR']=str(root/'.nm-test-phase/tmp');e['NM_GRANDCHILD']=str(ev/'diagnostic-grandchild.pid')
try:
    r=subprocess.run(['bash',str(p)],env=e,capture_output=True,text=True,timeout=40)
    (ev/('live-unknown-diagnostic.log' if unknown else 'live-stop-diagnostic.log')).write_text(r.stdout+r.stderr)
    g=(ev/'diagnostic-grandchild.pid').read_text().strip()
    assert r.returncode==1 and ('watcher liveness was unreadable after the direct check returned' if unknown else 'watcher did not stop after the direct check returned') in r.stderr, r.stderr
    rows=[line for line in r.stderr.splitlines() if line.strip().split() and line.strip().split()[0].isdigit()]
    parsed={line.strip().split()[0]:line.strip().split() for line in rows}
    assert g in parsed, 'grandchild absent from actual process-tree output'
    parent=parsed[g][1]
    assert parent in parsed and parsed[parent][1]=='1', 'recorded child did not reparent as intended'
    result={'result':'pass','injection':'SIGSTOP to real watcher from direct custom check; no production files modified','ps_availability':'removed from command-scoped PATH' if unknown else 'host ps','assertion_exit':r.returncode,'grandchild_pid':g,'recorded_reparented_child_pid':parent,'reparented_child_ppid':parsed[parent][1],'diagnostic':r.stderr}
    (ev/('live-unknown-diagnostic.json' if unknown else 'live-stop-diagnostic.json')).write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k!='diagnostic'},indent=2))
finally:
    gp=ev/'diagnostic-grandchild.pid'
    if gp.exists():
        try: os.kill(int(gp.read_text()),signal.SIGKILL)
        except ProcessLookupError: pass
