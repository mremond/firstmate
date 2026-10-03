import hashlib, json, os, shlex, shutil, subprocess, traceback
from pathlib import Path

ROOT = Path('/Users/mremond/.no-mistakes/worktrees/acf4a767348a/01M418J4Y0Z6WQQPFEBCJ3HQNR')
EVIDENCE = Path('/Users/mremond/.no-mistakes/evidence/01M418J4Y0Z6WQQPFEBCJ3HQNR')
QA = ROOT / '.qa-6319'
LIVE = QA / 'live'
LIVE.mkdir(parents=True, exist_ok=True)
TOOLS = LIVE / 'tools'
TOOLS.mkdir()
for name in ('bash','git','treehouse','jq','tasks-axi','node'):
    binary = shutil.which(name)
    assert binary, name
    (TOOLS / name).symlink_to(binary)
env = {k:v for k,v in os.environ.items() if not k.startswith(('FM_','TASKS_AXI_','GIT_','TREEHOUSE_')) and k not in ('TMUX','TMUX_PANE','HERDR_ENV','HERDR_SESSION','NO_MISTAKES_HOME','NM_HOME')}
env.update(PATH=f'{TOOLS}:/usr/bin:/bin:/usr/sbin:/sbin', TMPDIR=str(QA/'tmp'), GIT_CONFIG_GLOBAL='/dev/null', GIT_CONFIG_NOSYSTEM='1', GIT_CEILING_DIRECTORIES=str(ROOT), GIT_AUTHOR_NAME='Lab validation', GIT_AUTHOR_EMAIL='lab@example.invalid', GIT_COMMITTER_NAME='Lab validation', GIT_COMMITTER_EMAIL='lab@example.invalid', XDG_STATE_HOME=str(LIVE/'xdg-state'), XDG_CONFIG_HOME=str(LIVE/'xdg-config'), XDG_CACHE_HOME=str(LIVE/'xdg-cache'), FM_PROCEVENT_CLAIM_ROOT=str(LIVE/'claims'), FM_REMOTE_JOB_STATE_ROOT=str(LIVE/'remote-jobs'), NO_MISTAKES_GATE='test')
# Keep real commands, while hiding optional external pipeline/forge tools.
assert subprocess.run(['bash','-c','command -v no-mistakes || command -v gh-axi || command -v gh'],env=env,capture_output=True).returncode != 0
# Explicit OS guard: writes stay in the disposable workspace/evidence and
# signals may only reach children of the same invocation, never operator workers.
policy = f'''(version 1)
(allow default)
(deny file-write*)
(allow file-write* (subpath "{QA}") (subpath "{EVIDENCE}") (literal "/dev/null"))
(deny signal)
(allow signal (target same-sandbox))
(deny network*)
'''
transcript = (EVIDENCE/'live-cli-transcript.log').open('w')
results = []
def log(s):
    transcript.write(s+'\n'); transcript.flush()
def run(args, cwd=ROOT, check=True, guarded=False):
    args = list(map(str,args))
    log('$ '+('cd '+shlex.quote(str(cwd))+' && ' if cwd != ROOT else '')+shlex.join(args))
    command = ['/usr/bin/sandbox-exec','-p',policy,*args] if guarded else args
    p = subprocess.run(command,cwd=cwd,env=env,text=True,capture_output=True,timeout=90)
    log(p.stdout.rstrip()); log(p.stderr.rstrip()); log(f'[exit {p.returncode}]')
    if check and p.returncode:
        raise RuntimeError(f'{shlex.join(args)} exited {p.returncode}: {p.stderr[-1800:]}')
    return p

def snapshot(wt, meta):
    return {'status':run(['git','-C',wt,'status','--porcelain']).stdout,'head':run(['git','-C',wt,'rev-parse','HEAD']).stdout.strip(),'branch':run(['git','-C',wt,'symbolic-ref','--short','HEAD']).stdout.strip(),'meta':hashlib.sha256(meta.read_bytes()).hexdigest(),'files':{str(p.relative_to(wt)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(wt.rglob('*')) if p.is_file() and p.name != '.git'}}

def passed(name, details):
    results.append({'name':name,'result':'pass','live':True,'details':details})
    log('OBSERVED: '+details)
    print('PASS: '+name,flush=True)

try:
    lab = LIVE/'brief-home'
    run([ROOT/'bin/fm-lab-home.sh','create',lab])
    env['FM_HOME']=str(lab)
    for mode in ('no-mistakes','direct-PR','local-only'):
        task='brief-'+mode.lower()
        run([ROOT/'bin/fm-brief.sh',task,'synthetic-project','--mode',mode],guarded=True)
        brief=(lab/'data'/task/'brief.md').read_text()
        (EVIDENCE/f'generated-ship-{mode}.md').write_text(brief)
        rules=brief.split('# Rules\n',1)[1].split('\n# ',1)[0]
        log(f'Generated {mode} Rules contract:\n{rules}')
        assert f'under `{lab}/data/{task}/` or a temporary directory' in rules
        assert 'Leave the worktree clean before reporting done.' in rules
        assert 'Outside the worktree, write only that task material and the status and steering-inbox records authorized below.' in rules
    passed('Generate ship instructions in all three delivery modes', 'The emitted worker contract names the correct task data directory, permits temporary scratch, limits outside writes, and requires a clean worktree before done in no-mistakes, direct-PR and local-only modes. This checks emitted instructions, not model compliance.')
    for mode in ('no-mistakes','local-only'):
        lab=LIVE/mode
        run([ROOT/'bin/fm-lab-home.sh','create',lab])
        env.update(FM_HOME=str(lab),TREEHOUSE_ROOT=str(lab/'pool'))
        # A finished worker's windowless record; no primary or model is launched.
        (lab/'config'/'backend').write_text('tmux\n')
        (lab/'data'/'backlog.md').write_text('# Backlog\n\n## In flight\n\n## Queued\n\n## Done\n')
        shutil.copyfile(ROOT/'.tasks.toml',lab/'.tasks.toml')
        run([ROOT/'bin/fm-tasks-axi.sh','add','task-x1','Synthetic scratch cleanup check','--kind','ship'],guarded=True)
        run([ROOT/'bin/fm-tasks-axi.sh','start','task-x1'],guarded=True)
        origin=lab/'origin.git'; project=lab/'projects'/'sample'
        run(['git','init','-q','--bare','-b','main',origin])
        run(['git','init','-q','-b','main',project])
        (project/'README.md').write_text('Synthetic project for cleanup validation.\n')
        run(['git','-C',project,'add','README.md'])
        run(['git','-C',project,'commit','-q','-m','Initial local fixture'])
        run(['git','-C',project,'remote','add','origin',origin])
        run(['git','-C',project,'push','-q','-u','origin','main'])
        run(['git','-C',project,'remote','set-head','origin','main'])
        alloc=run(['treehouse','get','--lease','--no-fetch','--json'],cwd=project,guarded=True)
        allocation=json.loads(alloc.stdout)
        log('Treehouse allocation: '+json.dumps(allocation))
        wt=Path(allocation.get('path') or allocation.get('worktree_path') or allocation.get('worktree'))
        assert wt.is_relative_to(lab), wt
        run(['git','-C',wt,'checkout','-q','-b','fm/task-x1'])
        (wt/'feature.txt').write_text('Landed feature.\n')
        run(['git','-C',wt,'add','feature.txt'])
        run(['git','-C',wt,'commit','-q','-m','Landed feature'])
        meta=lab/'state'/'task-x1.meta'
        meta.write_text(f'worktree={wt}\nproject={project}\nkind=ship\nmode={mode}\nharness=codex\n')
        # First confirm that clean but unlanded/unpushed work still refuses.
        before=snapshot(wt,meta)
        p=run([ROOT/'bin/fm-teardown.sh','task-x1'],check=False,guarded=True)
        assert p.returncode==1 and ('REFUSED:' in p.stderr), p.stderr
        assert 'commits' in p.stderr and 'untracked-only' not in p.stderr, p.stderr
        assert snapshot(wt,meta)==before
        passed(f'{mode}: refuse clean unpushed work', 'Exit 1; unlanded commit, task branch, file bytes, and metadata are preserved.')
        run(['git','-C',project,'merge','-q','--ff-only','fm/task-x1'])
        if mode=='no-mistakes':
            run(['git','-C',project,'push','-q','origin','main'])
        taskdata=lab/'data'/'task-x1'; taskdata.mkdir()
        (taskdata/'server.log').write_text('Manual server proof retained outside the task worktree.\n')
        (taskdata/'company.json').write_text('{"name":"Disposable QA company"}\n')
        (taskdata/'helper.sh').write_text('#!/bin/sh\nprintf "proof"\n')
        # Existing hook artifacts are exempt. Real Git still reports them.
        (wt/'.claude').mkdir(); (wt/'.claude'/'settings.local.json').write_text('{}\n')
        (wt/'.fm-grok-turnend').write_text('synthetic hook\n')
        (wt/'.fm-kimi-turnend').write_text('synthetic hook\n')
        scratch=wt/'00 proof scratch'; scratch.mkdir()
        (scratch/'server.log').write_text('Throwaway in-worktree server output.\n')
        for n in range(1,12): (wt/f'{n:02d}-scratch.txt').write_text(f'Scratch {n}\n')
        for kind in ('untracked','mixed','tracked'):
            if kind=='mixed':
                (wt/'feature.txt').write_text('Uncommitted tracked change.\n')
                if mode=='local-only': run(['git','-C',wt,'add','feature.txt'])
            if kind=='tracked':
                shutil.move(str(scratch),str(taskdata/'moved-proof-scratch'))
                for n in range(1,12): shutil.move(str(wt/f'{n:02d}-scratch.txt'),str(taskdata/f'{n:02d}-scratch.txt'))
            before=snapshot(wt,meta)
            p=run([ROOT/'bin/fm-teardown.sh','task-x1'],check=False,guarded=True)
            assert p.returncode==1, p.stderr
            classification='untracked-only leftovers' if kind=='untracked' else 'includes tracked edits'
            assert f'uncommitted changes present ({classification})' in p.stderr,p.stderr
            if kind!='tracked':
                assert '00 proof scratch/' in p.stderr and '  09-scratch.txt\n' in p.stderr
                assert 'additional untracked paths omitted' in p.stderr
                assert '10-scratch.txt' not in p.stderr and '11-scratch.txt' not in p.stderr
                listing=p.stderr.split('untracked paths (up to 10):\n')[1]
                assert '.claude/' not in listing and '.fm-grok-turnend' not in listing and '.fm-kimi-turnend' not in listing
            else: assert 'untracked paths' not in p.stderr
            assert snapshot(wt,meta)==before
            # Repeat scratch-only refusal to prove no implicit discard on retry.
            if kind=='untracked':
                retry=run([ROOT/'bin/fm-teardown.sh','task-x1'],check=False,guarded=True)
                assert retry.returncode==1 and classification in retry.stderr
                assert snapshot(wt,meta)==before
            passed(f'{mode}: {kind} dirt refuses without deleting work', f'Exit 1; {classification}; all file bytes, Git status, HEAD, branch and metadata unchanged. '+('Listing caps at ten non-exempt paths and reports overflow; repeated scratch-only cleanup also preserves everything.' if kind!='tracked' else 'No untracked paths are invented.'))
        # Discard only our deliberate fixture edit, after recording preservation;
        # keep every proof file in task data before the ordinary cleanup call.
        run(['git','-C',wt,'restore','--staged','--worktree','feature.txt'])
        expected={str(p.relative_to(taskdata)):hashlib.sha256(p.read_bytes()).hexdigest() for p in taskdata.rglob('*') if p.is_file()}
        p=run([ROOT/'bin/fm-teardown.sh','task-x1'],guarded=True)
        assert 'teardown task-x1 complete' in p.stdout
        assert not meta.exists()
        state=run([ROOT/'bin/fm-tasks-axi.sh','show','task-x1'],guarded=True).stdout
        assert 'state: done' in state,state
        after={str(p.relative_to(taskdata)):hashlib.sha256(p.read_bytes()).hexdigest() for p in taskdata.rglob('*') if p.is_file()}
        assert expected==after
        status=run(['treehouse','status'],cwd=project,guarded=True).stdout
        log('Retained task data SHA256:\n'+json.dumps(after,indent=2))
        passed(f'{mode}: clean landed task returns its real pool slot and retains proof', 'Ordinary cleanup exited 0 without --force or a discard decision, removed task metadata, closed the real tasks-axi backlog item, and retained every task-data proof file byte-for-byte. Real Treehouse status captured after return.')
except Exception as error:
    log(traceback.format_exc())
    results.append({'name':'live driver setup or assertion','result':'fail','live':False,'details':str(error)})
    print(traceback.format_exc(),flush=True)
    raise
finally:
    (EVIDENCE/'live-cli-results.json').write_text(json.dumps(results,indent=2)+'\n')
    shutil.rmtree(LIVE)
    log('Cleanup: removed all disposable live homes, repositories, pool directories and tool links.')
    transcript.close()
