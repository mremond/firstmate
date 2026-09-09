"""Exercise rare Git failures through real spawn commands, with no Git shims."""
from pathlib import Path
import os
import shlex
import subprocess

ROOT = Path('/Users/mremond/.no-mistakes/worktrees/acf4a767348a/01M22J6W2BJAVGZZ9NSGWD23SR')
EVIDENCE = Path(__file__).parent
SCRATCH = ROOT/'.local-test-lock-naming'
ENV = {k:v for k,v in os.environ.items() if not k.startswith(('FM_', 'GIT_', 'TMUX', 'CLAUDE', 'CODEX', 'PI_'))}
ENV.update(HOME=str(SCRATCH/'user-home'), TMPDIR=str(SCRATCH/'tmp'), GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL='/dev/null', GIT_CEILING_DIRECTORIES=str(SCRATCH), FM_GATE_REFUSE_BYPASS='1', FM_SPAWN_NO_GUARD='1', FM_BACKEND='orca')
LOG = []

def command(args, cwd, env=ENV):
    p = subprocess.run([str(x) for x in args],cwd=cwd,env=env,text=True,capture_output=True,timeout=40)
    LOG.extend(['cwd='+str(cwd),'$ '+shlex.join([str(x) for x in args]),f'exit={p.returncode}','stdout: '+(p.stdout or '<empty>'),'stderr: '+(p.stderr or '<empty>')])
    return p

def world(name):
    d = SCRATCH/name
    for path in ('home/state','external-state','data','config','project','cwd'):
        (d/path).mkdir(parents=True)
    assert command(['git','init','-q','-b','main',d/'project'],d).returncode == 0
    return d

def spawn(d, label):
    script = ROOT/'bin/fm-spawn.sh' if label == 'target' else SCRATCH/'base/bin/fm-spawn.sh'
    env=dict(ENV,FM_HOME=str(d/'home'),FM_STATE_OVERRIDE=str(d/'external-state'),FM_DATA_OVERRIDE=str(d/'data'),FM_CONFIG_OVERRIDE=str(d/'config'))
    LOG.append(f'\n[{d.name} / {label}] FM_HOME={d}/home FM_STATE_OVERRIDE={d}/external-state FM_BACKEND=orca')
    return command([script,'lock-check',d/'project','--scout','--backend','tmux','--harness','codex'],d/'cwd',env)

def refused(d, expected):
    for label in ('base','target'):
        p=spawn(d,label)
        assert p.returncode == 1 and not p.stdout and 'could not resolve the shared Treehouse project lock' in p.stderr, p
        if label == 'target':
            assert expected in p.stderr, (expected,p.stderr)

def repaired(d):
    for label in ('base','target'):
        p=spawn(d,label)
        assert p.returncode == 1 and 'task lock-check has no brief' in p.stderr, p
        assert 'fm_treehouse_project_lock_path:' not in p.stderr
    LOG.append('After repairing only the named cause, both commands advanced to the missing-brief guard.')

try:
    d=world('real-hash-failure')
    (d/'cwd/.git').write_text('gitdir: absent-git-directory\n')
    refused(d,f'cannot hash the project lock identity, so git is unusable here: {d}/project')
    (d/'cwd/.git').unlink()
    repaired(d)

    d=world('real-vanished-worktree-top')
    assert command(['git','-C',d/'project','config','core.worktree',d/'vanished'],d/'cwd').returncode == 0
    p=command(['git','-C',d/'project','rev-parse','--show-toplevel'],d/'cwd')
    assert p.returncode == 0 and p.stdout.strip() == str(d/'vanished')
    refused(d,f'project worktree top cannot be entered: {d}/vanished')
    assert not (d/'vanished').exists()
    (d/'vanished').mkdir()
    repaired(d)

    d=world('real-missing-project')
    import shutil
    shutil.rmtree(d/'project')
    old,new=spawn(d,'base'),spawn(d,'target')
    assert old.returncode == new.returncode == 1
    assert str(d/'project') in old.stderr and str(d/'project') in new.stderr
    assert 'fm_treehouse_project_lock_path:' not in new.stderr
    assert not (d/'project').exists()
    LOG.append('Missing project remains refused by the earlier CLI path guard; no directory was created.')
finally:
    (EVIDENCE/'real-git-failures.log').write_text('\n'.join(LOG)+'\n')
print('Real Git hash failure, missing worktree top, and early missing-project refusal verified.')
