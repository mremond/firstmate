import pathlib,os,subprocess as sp,signal
R=pathlib.Path('/Users/mremond/.no-mistakes/worktrees/acf4a767348a/01M22Z7YQYD4K70MWCSC6FV3P4')
E=pathlib.Path('/Users/mremond/.no-mistakes/evidence/01M22Z7YQYD4K70MWCSC6FV3P4')
env={k:v for k,v in os.environ.items() if not k.startswith('FM_')};env.update(TMPDIR=str(R/'.test-phase/tmp'),FM_TEST_SKIP_ORPHAN_REAP='1',FM_HOME=str(R/'.test-phase/adjacent-home'))
for name,first,selectors in [
('fm-wake-queue.test.sh','test_self_held_lock_reclaims_instead_of_deadlocking',['test_self_held_lock_reclaims_instead_of_deadlocking']),
('fm-watch-arm.test.sh','test_attached_arm_reports_the_delivered_wake',['test_marker_publish_failure_retains_recovery_evidence']),
('fm-daemon.test.sh','test_afk_start_refuses_when_flag_cannot_be_written',['test_wedge_alarm_backgrounded_command_times_out_and_reaps_descendant'])]:
    src=(R/'tests'/name).read_text();prefix=src.split('\n'+first+'\n')[0];assert prefix!=src
    runner=R/'tests'/('.phase-adjacent-'+name);runner.write_text(prefix+'\n'+'\n'.join(selectors)+'\n')
    try:
        with open(E/('adjacent-'+name+'.log'),'w') as f:
            f.write('Selectors: '+', '.join(selectors)+'\n');f.flush()
            p=sp.Popen(['bash',str(runner)],env=env,cwd=R,stdout=f,stderr=sp.STDOUT,start_new_session=True)
            try:rc=p.wait(timeout=90)
            finally:
                try:os.killpg(p.pid,signal.SIGKILL)
                except ProcessLookupError:pass
        print(name, 'exit',rc,(E/('adjacent-'+name+'.log')).read_text(),flush=True);assert rc==0
    finally:runner.unlink(missing_ok=True)
