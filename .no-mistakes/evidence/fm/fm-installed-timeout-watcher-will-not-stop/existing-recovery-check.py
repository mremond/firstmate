from pathlib import Path
# Reuse the live driver's process and home setup; execute no earlier scenarios.
helper=Path('/Users/mremond/.no-mistakes/evidence/01M2JEJPE43XFXJCGYM3KFAX75/live-watcher-checks.py')
exec(helper.read_text().split('\ntry:\n',1)[0])
results=json.loads((EVIDENCE/'live-watcher-results.json').read_text())
p=home('release-lock-existing'); state=p/'state'; marker=state/'.watcher-down'
try:
    r=run(p,'. "$1"; fm_recovery_marker_publish "$2" downtime',marker)
    assert r.returncode==0,r.stderr
    script='''set -T
trap 'if [ "${transition:-}" = release-lock-existing ]; then trap - DEBUG; printf "%s\\n" "$transition" > "$STATE/cleanup.ready"; kill -STOP "${BASHPID:-$$}"; fi' DEBUG
. "$1"
'''
    # $0 deliberately equals the real script path, retaining its executable
    # entry point while enabling a DEBUG trap only to pause the exit boundary.
    w=spawn(p,['bash','-c',script,WATCH,WATCH],'release-lock-existing',FM_WATCHER_SHUTDOWN_LOCK_SECS='300',FM_RECOVERY_MARKER_LOCK_TIMEOUT='300')
    wait_until(lambda: (state/'cleanup.ready').exists())
    assert read(state/'cleanup.ready')=='release-lock-existing'
    before=read(marker)
    holder=lock_holder(p,state/'.watcher-down.lock','release-existing-holder')
    t=time.monotonic(); w.send_signal(signal.SIGCONT); rc=w.wait(timeout=20); elapsed=round(time.monotonic()-t,3)
    err=read(EVIDENCE/'release-lock-existing.stderr.log'); out=read(EVIDENCE/'release-lock-existing.stdout.log')
    assert 'check: rearm-resurface' in out and 'within 5s' in err
    assert f'held by pid {holder.pid}' in err and holder.poll() is None
    assert read(marker)==before and read(state/'.watch.lock/pid')==str(w.pid)
    report('Recovery wake cleanup also times out and preserves the announced episode',result='pass',wake_output=out,transition='release-lock-existing',resume_to_exit_seconds=elapsed,watcher_exit=rc,diagnostic=err,ambient_values={'FM_WATCHER_SHUTDOWN_LOCK_SECS':'300','FM_RECOVERY_MARKER_LOCK_TIMEOUT':'300'},marker_before=before,marker_after=read(marker),holder_pid=holder.pid,holder_survived=True,stale_singleton_pid=read(state/'.watch.lock/pid'))
finally:
    for proc in procs:
        if proc.poll() is None:
            proc.kill(); proc.wait(timeout=5)
    for f in handles:f.close()
