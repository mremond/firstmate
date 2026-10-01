import os,pathlib,subprocess,time,json
root=pathlib.Path.cwd();lab=root/'.test-phase-tmp/nonclaude-home'; evidence=pathlib.Path('/Users/mremond/.no-mistakes/evidence/01M3W1X8TZ8MMD0NJ8S8NAMZNR')
meta=json.loads((lab/'driver.json').read_text());env=os.environ.copy()
for k in ['NO_MISTAKES_GATE','FM_GATE_REFUSE_BYPASS','FM_ROOT_OVERRIDE','FM_STATE_OVERRIDE','FM_DATA_OVERRIDE','FM_CONFIG_OVERRIDE','FM_PROJECTS_OVERRIDE','TMUX','HERDR_SESSION']:
    env.pop(k,None)
env.update(meta['env_keys']); env['PATH']=str(lab/'shim')+':'+env['PATH']
with (evidence/'nonclaude-sends.log').open('a') as output:
    for route,target in [('task-slash','worker'),('explicit-slash','primary:codex')]:
        (lab/'fail-capture').touch()
        r=subprocess.run(['bin/fm-send.sh',target,'/status'],env=env,capture_output=True,text=True)
        line=f'{route}: fm-send.sh {target} /status: exit={r.returncode}; first_capture_failure_consumed={not (lab/"fail-capture").exists()}\n{r.stdout}{r.stderr}'
        print(line);output.write(line);output.flush()
        time.sleep(1)
        cap=subprocess.check_output(['/opt/homebrew/bin/tmux','-L','fm-lab','capture-pane','-p','-t','primary:codex'],env=env,text=True)
        (evidence/f'nonclaude-{route}.txt').write_text(cap)
        print(cap[-1400:])
        assert r.returncode==0 and not (lab/'fail-capture').exists(),line
        # /status uses a dismissible info panel on this release.
        subprocess.run(['/opt/homebrew/bin/tmux','-L','fm-lab','send-keys','-t','primary:codex','Escape'],env=env,check=True)
        time.sleep(.5)
    (lab/'fail-capture').touch()
    message='This is an isolated Firstmate live test. The only authorized work is to create '+str(lab/'acted')+' containing LIVE_INBOX_ACK and then move this inbox record into its handled directory as instructed by the doorbell. Do not inspect or modify any other files, run supervision, or contact anyone. Reply LIVE_INBOX_ACK.'
    r=subprocess.run(['bin/fm-send.sh','worker',message],env=env,capture_output=True,text=True)
    line=f'inbox: fm-send.sh worker <test instruction>: exit={r.returncode}; first_capture_failure_consumed={not (lab/"fail-capture").exists()}\n{r.stdout}{r.stderr}'
    print(line);output.write(line);output.flush()
    assert r.returncode==0,line
    for i in range(180):
        time.sleep(1)
        cap=subprocess.check_output(['/opt/homebrew/bin/tmux','-L','fm-lab','capture-pane','-p','-t','primary:codex'],env=env,text=True)
        (evidence/'nonclaude-inbox-final.txt').write_text(cap)
        if (lab/'acted').exists() and (lab/'state/worker.inbox/handled/001.msg').exists():
            line='Inbox live result: acted='+str((lab/'acted').read_text().strip())+'; 001.msg moved to handled/001.msg\n'
            print(line);output.write(line)
            (evidence/'nonclaude-acted.txt').write_text((lab/'acted').read_text())
            (evidence/'nonclaude-handled-001.msg').write_bytes((lab/'state/worker.inbox/handled/001.msg').read_bytes())
            break
    else:
        output.write('Inbox live result: model did not act and acknowledge within 180 seconds\n')
        print(cap)
        raise SystemExit(1)
(evidence/'nonclaude-input.log').write_bytes((lab/'input.log').read_bytes())
