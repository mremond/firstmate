"""Manual CLI verification; fixtures stay under the supplied gate worktree."""
import hashlib
import json
import os
from pathlib import Path
import shlex
import subprocess

ROOT = Path('/Users/mremond/.no-mistakes/worktrees/acf4a767348a/01M22J6W2BJAVGZZ9NSGWD23SR')
EVIDENCE = Path(__file__).parent
SCRATCH = ROOT / '.local-test-lock-naming'
WORLD = SCRATCH / 'live'
WORLD.mkdir()
ENV = {k: v for k, v in os.environ.items() if not k.startswith(('FM_', 'GIT_', 'TMUX', 'CLAUDE', 'CODEX', 'PI_'))}
ENV.update(HOME=str(SCRATCH/'user-home'), TMPDIR=str(SCRATCH/'tmp'), GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL='/dev/null', GIT_CEILING_DIRECTORIES=str(SCRATCH), FM_GATE_REFUSE_BYPASS='1', FM_SPAWN_NO_GUARD='1', FM_BACKEND='orca')
LIBS = {'base': SCRATCH/'base/bin/fm-wake-lib.sh', 'target': ROOT/'bin/fm-wake-lib.sh'}
LOG = []
RESULTS = []

def run(cmd, env=ENV):
    return subprocess.run([str(x) for x in cmd], cwd=ROOT, env=env, text=True, capture_output=True, timeout=40)

def git(*args):
    p = run(['git', *args])
    assert p.returncode == 0, p.stderr
    return p.stdout.strip()

def case(name, repo=True):
    d = WORLD/name
    for child in ('home/state', 'external-state', 'data', 'config', 'project'):
        (d/child).mkdir(parents=True, exist_ok=True)
    if repo:
        git('-C', d/'project', 'init', '-q', '-b', 'main')
    return d

def env_for(d, home):
    return dict(ENV, FM_HOME=str(home), FM_STATE_OVERRIDE=str(d/'external-state'), FM_DATA_OVERRIDE=str(d/'data'), FM_CONFIG_OVERRIDE=str(d/'config'), FM_PROJECTS_OVERRIDE=str(d/'projects'))

def invoke(d, home, label, interface='spawn'):
    env = env_for(d, home)
    if interface == 'spawn':
        cmd = [LIBS[label].parent/'fm-spawn.sh', 'lock-check', d/'project', '--scout', '--backend', 'tmux', '--harness', 'codex']
    else:
        cmd = ['/bin/bash', '-c', '. "$1"; fm_treehouse_project_lock_path "$2"', '_', LIBS[label], d/'project']
    p = run(cmd, env)
    LOG.extend([f'\n[{d.name} / {label} / {interface}]', 'Environment: '+shlex.join([f'{k}={env[k]}' for k in ('FM_HOME','FM_STATE_OVERRIDE','FM_DATA_OVERRIDE','FM_BACKEND')]), '$ '+shlex.join([str(x) for x in cmd]), f'exit={p.returncode}', 'stdout: '+(p.stdout or '<empty>'), 'stderr: '+(p.stderr or '<empty>')])
    return p

def refusal(d, expected, home=None, absent=()):
    home = home or d/'home'
    old = invoke(d, home, 'base')
    new = invoke(d, home, 'target')
    assert old.returncode == new.returncode == 1, (old, new)
    assert old.stdout == new.stdout == '', (old.stdout, new.stdout)
    assert 'could not resolve the shared Treehouse project lock' in old.stderr, old.stderr
    assert expected in new.stderr, (expected, new.stderr)
    assert 'could not resolve the shared Treehouse project lock' in new.stderr, new.stderr
    for path in absent:
        assert not path.exists(), path
        LOG.append(f'filesystem: {path} remains absent')
    assert not (d/'external-state/lock-check.meta').exists()
    RESULTS.append({'case': d.name, 'interface': 'real fm-spawn.sh CLI; no tool doubles', 'result': 'pass'})

def success(d, home=None):
    home = home or d/'home'
    for label in ('base', 'target'):
        p = invoke(d, home, label)
        assert p.returncode == 1 and 'task lock-check has no brief' in p.stderr, p.stderr
        assert 'fm_treehouse_project_lock_path:' not in p.stderr, p.stderr
        assert not (d/'external-state/lock-check.meta').exists()
    a, b = (invoke(d, home, label, 'library') for label in ('base','target'))
    assert a.returncode == b.returncode == 0
    assert a.stdout == b.stdout and a.stdout.endswith('.lock\n') and a.stderr == b.stderr == ''
    LOG.append('CLI advanced past the project guard to the independently missing brief; task creation never began. Old and new lock paths match byte-for-byte.')
    RESULTS.append({'case': d.name, 'interface': 'real spawn CLI plus direct lock resolution', 'result': 'pass'})

def parent(child, target):
    (child/'.fm-secondmate-parent').write_text(f'schema=fm-secondmate-parent.v1\nroute=local\nparent_home={target}\n')

try:
    d = case('root-state-absent')
    (d/'home/state').rmdir()
    refusal(d, f'the root firstmate home has no state directory: {d}/home/state', absent=[d/'home/state'])
    (d/'home/state').mkdir()
    success(d)

    d = case('root-home-absent')
    refusal(d, f'cannot resolve the root firstmate home from FM_HOME: {d}/missing home', home=d/'missing home', absent=[d/'missing home'])

    for depth in (1,2):
        d = case(f'parent-depth-{depth}')
        missing = d/'absent parent'
        holder = d/'home'
        if depth == 2:
            holder = d/'intermediate'
            holder.mkdir()
            parent(d/'home', holder)
        parent(holder, missing)
        refusal(d, f'cannot resolve the recorded parent firstmate home: {missing}', absent=[missing])
        missing.mkdir()
        refusal(d, f'the root firstmate home has no state directory: {missing}/state', absent=[missing/'state'])
        (missing/'state').mkdir()
        success(d)

    for relative in (False, True):
        d = case('relative-origin-permission' if relative else 'absolute-origin-permission')
        origin = d/'project/origin' if relative else d/'origin'
        origin.mkdir()
        git('-C', d/'project', 'remote', 'add', 'origin', 'origin' if relative else origin)
        origin.chmod(0)
        try:
            assert run(['/bin/bash','-c','cd -- "$1"','_',origin]).returncode != 0
            refusal(d, f'project origin directory cannot be entered: {origin}')
        finally:
            origin.chmod(0o755)
        success(d)

    d = case('not-a-git-project', repo=False)
    refusal(d, f'project has no origin and is not inside a git worktree: {d}/project')

    d = case('malformed-parent')
    (d/'home/.fm-secondmate-parent').write_text('route=invalid\n')
    refusal(d, f'cannot resolve the root firstmate home from FM_HOME: {d}/home')

    d = case('parent-cycle')
    (d/'other').mkdir()
    parent(d/'home', d/'other')
    parent(d/'other', d/'home')
    refusal(d, f'cannot resolve the root firstmate home from FM_HOME: {d}/home')

    d = case('remote-parent-terminates-locally')
    (d/'home/.fm-secondmate-parent').write_text('schema=fm-secondmate-parent.v1\nroute=remote\nparent_host=not-contacted.invalid\n')
    success(d)

    for origin in ('https://example.invalid/project.git', 'git@example.invalid:project.git', 'missing-relative-origin'):
        d = case('origin-'+str(len(RESULTS)))
        git('-C', d/'project', 'remote', 'add', 'origin', origin)
        success(d)
finally:
    (EVIDENCE/'live-cli-transcript.log').write_text('\n'.join(LOG)+'\n')
    (EVIDENCE/'live-cli-results.json').write_text(json.dumps(RESULTS, indent=2)+'\n')

print(f'Completed {len(RESULTS)} CLI observations; transcripts saved.')
