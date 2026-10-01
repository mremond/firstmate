import os, pathlib, subprocess, time, json
root = pathlib.Path.cwd()
evidence = pathlib.Path('/Users/mremond/.no-mistakes/evidence/01M3W1X8TZ8MMD0NJ8S8NAMZNR')
parent = root / '.test-phase-tmp' / 'guard-parent'
subprocess.run(['bin/fm-lab-home.sh','create',str(parent)],check=True)
sockdir = subprocess.check_output(['bin/fm-lab-home.sh','tmux-dir',str(parent)],text=True).strip()
env = os.environ.copy()
for key in ['FM_ROOT_OVERRIDE','FM_STATE_OVERRIDE','FM_DATA_OVERRIDE','FM_CONFIG_OVERRIDE','FM_PROJECTS_OVERRIDE','FM_GATE_REFUSE_BYPASS','NO_MISTAKES_GATE','TMUX','HERDR_SESSION']:
    env.pop(key,None)
env.update(FM_HOME=str(parent), TMPDIR=str(root/'.test-phase-tmp'), TMUX_TMPDIR=sockdir, FM_SEND_INBOX_SELECTOR_LIVE_E2E='1')
frames = evidence/'selector-frames'
frames.mkdir(exist_ok=True)
seen = set()
with (evidence/'selector-live.log').open('w') as output:
    proc = subprocess.Popen(['bash','tests/fm-send-inbox-claude-selector-live-e2e.test.sh'],env=env,stdout=output,stderr=subprocess.STDOUT)
    socket = 'fm-selector-live-'+str(proc.pid)
    (evidence/'selector-launch.json').write_text(json.dumps({'test':'tests/fm-send-inbox-claude-selector-live-e2e.test.sh','pid':proc.pid,'socket':socket,'tmux_tmpdir':sockdir,'FM_HOME':str(parent),'grid':'160x50','target':'e1a6b78cb5b8c21605eddaaa980d2b4a33814891'},indent=2))
    start=time.time()
    try:
        while proc.poll() is None and time.time()-start < 370:
            cap = subprocess.run(['tmux','-L',socket,'capture-pane','-p','-t','selectorlive:claude'],env=env,capture_output=True,text=True)
            if cap.returncode==0 and cap.stdout not in seen:
                seen.add(cap.stdout)
                idx=len(seen)
                (frames/f'{idx:03d}.txt').write_text(cap.stdout)
                ansi=subprocess.run(['tmux','-L',socket,'capture-pane','-e','-p','-t','selectorlive:claude'],env=env,capture_output=True,text=True)
                (frames/f'{idx:03d}.ansi').write_text(ansi.stdout)
            for lab in (root/'.test-phase-tmp').glob('fm-selector-live.*'):
                for name in ['send.out','send.err','input.log']:
                    f=lab/name
                    if f.exists() and f.stat().st_size:
                        data=f.read_text()
                        with (evidence/f'selector-observed-{name}').open('a') as target:
                            target.write(f'[{time.time()-start:.2f}s]\n'+data+'\n')
                for rec in (lab/'home/state/selector.inbox').glob('*.msg'):
                    (evidence/f'selector-retained-{rec.name}').write_bytes(rec.read_bytes())
            time.sleep(.25)
        if proc.poll() is None:
            proc.terminate()
            proc.wait(timeout=15)
        print('live guard exit:',proc.returncode,'frames:',len(seen),flush=True)
    finally:
        subprocess.run(['tmux','-L',socket,'kill-server'],env=env,capture_output=True)
        subprocess.run(['bin/fm-lab-home.sh','teardown',str(parent)],check=True)
        import shutil
        shutil.rmtree(parent)
print((evidence/'selector-live.log').read_text())
