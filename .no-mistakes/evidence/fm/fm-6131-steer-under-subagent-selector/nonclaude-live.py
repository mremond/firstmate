import os,pathlib,subprocess,time,shlex,json
root=pathlib.Path.cwd(); evidence=pathlib.Path('/Users/mremond/.no-mistakes/evidence/01M3W1X8TZ8MMD0NJ8S8NAMZNR')
lab=root/'.test-phase-tmp/nonclaude-home'
subprocess.run(['bin/fm-lab-home.sh','create',str(lab)],check=True)
sockdir=subprocess.check_output(['bin/fm-lab-home.sh','tmux-dir',str(lab)],text=True).strip()
env=os.environ.copy()
for k in ['NO_MISTAKES_GATE','FM_GATE_REFUSE_BYPASS','FM_ROOT_OVERRIDE','FM_STATE_OVERRIDE','FM_DATA_OVERRIDE','FM_CONFIG_OVERRIDE','FM_PROJECTS_OVERRIDE','TMUX','HERDR_SESSION']:
    env.pop(k,None)
env.update(TMUX_TMPDIR=sockdir,FM_HOME=str(lab),FM_TASK_INBOX=str(lab/'state/worker.inbox'))
(lab/'state/worker.meta').write_text('window=primary:codex\nkind=ship\nharness=codex\n')
# The wrapper forwards every request to the real isolated server and records inputs.
shim=lab/'shim';shim.mkdir()
(shim/'tmux').write_text('#!/usr/bin/env bash\ncase "$1" in\n send-keys) printf "%s\\n" "$*" >> '+shlex.quote(str(lab/'input.log'))+' ;;\n capture-pane) if [ -e '+shlex.quote(str(lab/'fail-capture'))+' ]; then rm '+shlex.quote(str(lab/'fail-capture'))+'; echo "injected one capture failure" >&2; exit 1; fi ;;\nesac\nexec /opt/homebrew/bin/tmux -L fm-lab "$@"\n')
(shim/'tmux').chmod(0o755)
child_env=env.copy();child_env['PATH']=str(shim)+':'+env['PATH']
meta={'sockdir':sockdir,'lab':str(lab),'env_keys':{'TMUX_TMPDIR':sockdir,'FM_HOME':str(lab),'FM_TASK_INBOX':str(lab/'state/worker.inbox')}}
(lab/'driver.json').write_text(json.dumps(meta))
cmd=['tmux','-L','fm-lab','new-session','-d','-s','primary','-n','codex','-x','160','-y','50','-c',str(root),'-e','FM_HOME='+str(lab),'-e','FM_TASK_INBOX='+str(lab/'state/worker.inbox'),'codex --no-daemon --dangerously-bypass-approvals-and-sandbox --disable hooks']
subprocess.run(cmd,env=env,check=True)
for i in range(30):
    time.sleep(1)
    cap=subprocess.run(['tmux','-L','fm-lab','capture-pane','-p','-t','primary:codex'],env=env,capture_output=True,text=True)
    (evidence/'nonclaude-startup.txt').write_text(cap.stdout)
    if 'context left' in cap.stdout or 'Do you trust' in cap.stdout:
        break
print(cap.stdout)
