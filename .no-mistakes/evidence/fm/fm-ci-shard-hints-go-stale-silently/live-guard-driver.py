import json, os, shlex, signal, subprocess, time
from pathlib import Path
root=Path.cwd()
ev=Path('/Users/mremond/.no-mistakes/evidence/01M20TE28ZPPZJ712ASRP3J3S9')
env=dict(os.environ, TMPDIR=str(root/'.test-phase-tmp'))
runner='bin/fm-test-run.sh'
families=subprocess.check_output([runner,'--list-families'],text=True,env=env).splitlines()
args=[runner,'--lane','portable-serial-5of6']
for family in families:
    if family!='pure-contract-unit':
        args += ['--exclude-family',family]
selected=subprocess.check_output([*args,'--list'],text=True,env=env).splitlines()
assert set(selected)=={'tests/fm-subagent-pretool-check.test.sh','tests/fm-trace-context-lib.test.sh'},selected
results={}
for name, pause_seconds in [('healthy',0),('paused',1082)]:
    artifact=ev/f'live-{name}.json'
    cmd=[*args,'--json',str(artifact)]
    with (ev/f'live-{name}.txt').open('w') as log:
        log.write('$ '+shlex.join(cmd)+'\n'); log.flush()
        p=subprocess.Popen(cmd,env=env,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,start_new_session=True)
        paused=False; resumed=False
        try:
            for line in p.stdout:
                log.write(line); log.flush()
                if pause_seconds and not paused and line.startswith('FM_TEST_BEGIN '):
                    os.killpg(p.pid,signal.SIGSTOP)
                    paused=True
                    started=time.monotonic()
                    state={'pid':p.pid,'pause_seconds':pause_seconds,'paused_at':time.time(),'resumes_at':time.time()+pause_seconds,'artifact':str(artifact)}
                    (ev/'live-pause-state.json').write_text(json.dumps(state,indent=2)+'\n')
                    log.write(f'[driver] SIGSTOP own process group {p.pid}; controlled delay {pause_seconds}s; wall clock unchanged.\n'); log.flush()
                    print(f'Paused isolated runner group {p.pid} for {pause_seconds}s after first FM_TEST_BEGIN.',flush=True)
                    while time.monotonic()-started < pause_seconds:
                        time.sleep(min(30,pause_seconds-(time.monotonic()-started)))
                        print(f'Controlled pause elapsed {time.monotonic()-started:.0f}/{pause_seconds}s',flush=True)
                    os.killpg(p.pid,signal.SIGCONT); resumed=True
                    log.write('[driver] SIGCONT; resumed own process group.\n'); log.flush()
            rc=p.wait(timeout=120)
        finally:
            if paused and not resumed and p.poll() is None:
                os.killpg(p.pid,signal.SIGCONT)
            if p.poll() is None:
                os.killpg(p.pid,signal.SIGTERM)
                p.wait(timeout=30)
        log.write(f'exit={rc}\n')
    assert rc==0,(name,rc)
    data=json.loads(artifact.read_text())
    assert data['summary']['total']==2 and data['summary']['failed']==0
    assert data['summary']['skipped_gate']==0
    assert data['selection'].startswith('lane=portable-serial-5of6;')
    cmd=[runner,'--check-shard-balance',str(artifact)]
    check=subprocess.run(cmd,env=env,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
    (ev/f'guard-{name}.txt').write_text('$ '+shlex.join(cmd)+'\n'+check.stdout+f'exit={check.returncode}\n')
    assert 'partial 1 of 6' in check.stdout
    if pause_seconds:
        assert 1080000<data['summary']['duration_ms']<1200000,data['summary']
        assert check.returncode==1
        assert 're-measure the scripts furthest over their hints' in check.stdout
        assert selected[0] in check.stdout
        assert '20 min job cap' in check.stdout
    else:
        assert check.returncode==0
        assert 'FM_TEST_SHARD_BALANCE ok shards=1' in check.stdout
        assert 'bound=20min' in check.stdout
    results[name]={'runner_exit':rc,'guard_exit':check.returncode,'wall_ms':data['summary']['duration_ms'],'artifact':str(artifact)}
    (ev/'live-results.json').write_text(json.dumps(results,indent=2)+'\n')
    print(check.stdout,flush=True)
print(json.dumps(results,indent=2),flush=True)
