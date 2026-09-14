#!/usr/bin/env python3
"""Drive the real seed CLIs and Git against disposable local homes; no shims."""
import hashlib
import io
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import tarfile
import tempfile

ROOT = Path('/Users/mremond/.no-mistakes/worktrees/acf4a767348a/01M2GQTYBGKJGSFTQPP3F8NX0G')
EVIDENCE = Path('/Users/mremond/.no-mistakes/evidence/01M2GQTYBGKJGSFTQPP3F8NX0G')
BASE = '80556bca2d728071cc14476b9bee60a8edf4159e'
TARGET = '4e5713f50d5f6216da75e16c9bdc23878e6f0b8e'
SOURCE = 'https://fm-fake-source-user:fm-fake-source-secret@fm-fake-source-host.invalid/fm-fake-source-path.git'
DEST = 'https://fm-fake-dest-user:fm-fake-dest-secret@fm-fake-dest-host.invalid/fm-fake-dest-path.git'
REFUSED = SOURCE.replace('.invalid/', '.invalid:notaport/')
PARTS = ['fm-fake-' + role + '-' + part for role in ['source', 'dest'] for part in ['user', 'secret', 'host', 'path']]
REGISTRY = '- alpha [direct-PR] - isolated validation project (added 2026-09-14)\n'
# Drop ambient Firstmate, agent, Git, and backlog routing settings. No user config writes.
ENV = {k: v for k, v in os.environ.items() if not k.startswith(('FM_', 'GIT_', 'TASKS_AXI_', 'BASH_', 'NO_MISTAKES')) and k not in ('ENV', 'BASH_ENV', 'SHELLOPTS', 'BASHOPTS')}
ENV.update(PATH='/usr/bin:/bin:/usr/sbin:/sbin:/opt/homebrew/bin', GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL='/dev/null', GIT_TERMINAL_PROMPT='0', GIT_AUTHOR_NAME='Local validation', GIT_AUTHOR_EMAIL='validation@example.invalid', GIT_COMMITTER_NAME='Local validation', GIT_COMMITTER_EMAIL='validation@example.invalid', LC_ALL='C')
os.umask(0o022)
SCRATCH = Path(tempfile.mkdtemp(prefix='.origin-live-check-', dir=ROOT))
(SCRATCH / 'tmp').mkdir()
ENV['TMPDIR'] = str(SCRATCH / 'tmp')
results = []
transcripts = {'target': [], 'baseline': []}
setup_lines = []

def command(args, *, env=ENV, cwd=ROOT):
    return subprocess.run([str(a) for a in args], cwd=cwd, env=env, text=True, capture_output=True, timeout=45)

def setup(args):
    p = command(args)
    setup_lines.append('$ ' + shlex.join([str(a) for a in args]) + '\n' + p.stdout + p.stderr + f'[exit {p.returncode}]\n')
    if p.returncode:
        raise RuntimeError(setup_lines[-1])
    return p.stdout.rstrip('\n')

def install(ref, name):
    dest = SCRATCH / name
    dest.mkdir()
    # Ordinary git archive: no access to any other clone and no worktree ref mutation.
    data = subprocess.check_output(['git', 'archive', ref, 'bin', 'AGENTS.md'], cwd=ROOT, env=ENV)
    with tarfile.open(fileobj=io.BytesIO(data)) as archive:
        archive.extractall(dest, filter='data')
    return dest

def world(runtime, name, *, remote=False):
    case = SCRATCH / name
    parent, child = case / 'parent home', case / 'seeded home'
    for leaf in ['data', 'state', 'config', 'projects']:
        (parent / leaf).mkdir(parents=True)
    (parent / 'data/projects.md').write_text(REGISTRY)
    env = dict(ENV, FM_HOME=str(parent), FM_SECONDMATE_CHARTER='Origin diagnostics validation', FM_SECONDMATE_SCOPE='Isolated local test')
    # Use the public charter scaffold, exactly as an operator can do before seeding.
    p = command([runtime / 'bin/fm-brief.sh', 'design', '--secondmate', 'alpha'], env=env)
    if p.returncode:
        raise RuntimeError(p.stderr)
    if not remote:
        shutil.copytree(runtime, child)
        (child / 'projects').mkdir()
    return parent, child, env

def project(parent, child=None, origin=SOURCE):
    src = parent / 'projects/alpha'
    setup(['git', 'init', '-q', '-b', 'main', src])
    (src / 'README.md').write_text('Disposable origin diagnostic validation\n')
    setup(['git', '-C', src, 'add', 'README.md'])
    setup(['git', '-C', src, 'commit', '-q', '-m', 'Fixture'])
    setup(['git', '-C', src, 'remote', 'add', 'origin', origin])
    dst = None
    if child:
        dst = child / 'projects/alpha'
        setup(['git', 'clone', '--quiet', src, dst])
    return src, dst

def origin_at(repo):
    p = command(['git', '-C', repo, 'remote', 'get-url', 'origin'])
    return p.stdout.rstrip('\n') if p.returncode == 0 else None

def drive(runtime, phase, name, scenario, kind, value=REFUSED):
    remote = kind.startswith('remote')
    parent, child, env = world(runtime, phase + '-' + name, remote=remote)
    src = dst = None
    if kind != 'remote-supplied':
        src, dst = project(parent, None if remote else child, value if remote else SOURCE)
    if kind == 'mismatch':
        setup(['git', '-C', dst, 'remote', 'set-url', 'origin', DEST])
    if kind == 'missing':
        setup(['git', '-C', dst, 'remote', 'remove', 'origin'])
    if kind == 'match':
        setup(['git', '-C', dst, 'remote', 'set-url', 'origin', SOURCE])
    before_origins = [origin_at(p) for p in [src, dst] if p]
    args = [runtime / 'bin/fm-home-seed.sh', 'design', child, 'alpha']
    if remote:
        args = [runtime / 'bin/fm-remote-home-seed.sh', 'design', 'remote-validation.invalid', SCRATCH / 'remote-root', SCRATCH / 'remote-home', 'alpha=' + value if kind == 'remote-supplied' else 'alpha']
    p = command(args, env=env)
    full = p.stdout + p.stderr
    leaked_parts = [part for part in PARTS if part in full]
    after_origins = [origin_at(q) for q in [src, dst] if q]
    checks = {'expected_exit': p.returncode == (0 if kind == 'match' else 1), 'origins_unchanged': before_origins == after_origins, 'origin_components_absent': not leaked_parts}
    state = []
    if kind == 'mismatch':
        checks['useful_diagnostic'] = (str(src) in p.stderr and str(dst) in p.stderr and 'different origin' in p.stderr and 'git remote get-url origin' in p.stderr)
    elif kind == 'missing':
        checks['useful_diagnostic'] = (str(src) in p.stderr and str(dst) in p.stderr and 'has no origin remote' in p.stderr)
    elif kind == 'remote-supplied':
        checks['useful_diagnostic'] = 'alpha=<origin-url>' in p.stderr and 'not an accepted clone URL' in p.stderr
    elif kind == 'remote-clone':
        checks['useful_diagnostic'] = str(src) in p.stderr and 'alpha=<origin-url>' in p.stderr and 'not an accepted clone URL' in p.stderr
    else:
        checks['useful_diagnostic'] = f'home={child}\n' in p.stdout
        for f in [parent / 'data/secondmates.md', child / '.fm-secondmate-home', child / '.fm-secondmate-parent', child / 'data/projects.md']:
            state.append(f'{f}:\n' + (f.read_text() if f.exists() else '<missing>\n'))
        checks['route_persisted'] = (parent / 'data/secondmates.md').exists() and f'home: {child};' in (parent / 'data/secondmates.md').read_text()
        checks['marker_persisted'] = (child / '.fm-secondmate-home').read_text() == 'design\n'
        checks['project_registered'] = (child / 'data/projects.md').read_text() == REGISTRY
        second = command(args, env=env)
        state.append('Idempotent reseed stdout:\n' + second.stdout + 'Idempotent reseed stderr:\n' + second.stderr + f'exit: {second.returncode}\n')
        checks['reseed_succeeds_without_leak'] = second.returncode == 0 and not any(part in second.stdout + second.stderr for part in PARTS)
        validate = command([runtime / 'bin/fm-home-seed.sh', 'validate'], env=env)
        checks['registry_validates'] = validate.returncode == 0
        state.append(f'fm-home-seed.sh validate: exit {validate.returncode}\n' + validate.stdout + validate.stderr)
    if kind != 'match':
        checks['no_route_published'] = not (parent / 'data/secondmates.md').exists()
        if not remote:
            checks['no_child_marker_published'] = not (child / '.fm-secondmate-home').exists()
            checks['existing_clone_preserved'] = (dst / 'README.md').read_text() == 'Disposable origin diagnostic validation\n'
        state.append('Route registry: ' + ('present' if (parent / 'data/secondmates.md').exists() else 'absent') + '\n')
    record = {'phase': phase, 'scenario': scenario, 'case': name, 'exit': p.returncode, 'checks': checks, 'leaked_synthetic_components': leaked_parts}
    if phase == 'baseline':
        record['expected_baseline_reproduction'] = p.returncode == 1 and bool(leaked_parts) and checks['origins_unchanged']
    else:
        record['pass'] = all(checks.values())
    results.append(record)
    transcripts[phase].append('\n=== ' + scenario + ' [' + name + '] ===\n$ FM_HOME=' + shlex.quote(str(parent)) + ' ' + shlex.join([str(a) for a in args]) + '\nstdout:\n' + (p.stdout or '<empty>\n') + 'stderr:\n' + (p.stderr or '<empty>\n') + f'exit: {p.returncode}\n' + '\n'.join(state) + 'Observed checks:\n' + json.dumps(record, indent=2) + '\n')
    print(phase + ' ' + name + ': ' + ('PASS' if record.get('pass') or record.get('expected_baseline_reproduction') else 'FAIL'), flush=True)

try:
    runtime = install(TARGET, 'runtime-target')
    baseline = install(BASE, 'runtime-baseline')
    scenarios = [
        ('mismatch-both', 'Mismatched credential-bearing source and seeded origins refuse with both clone paths and no URL', 'mismatch'),
        ('missing-origin', 'A seeded clone without an origin refuses without printing its credential-bearing source origin', 'missing'),
        ('rejected-argument', 'A rejected explicit remote origin identifies the argument without echoing its credentials', 'remote-supplied'),
        ('rejected-clone', 'A rejected origin read from a local clone identifies that clone without echoing its credentials', 'remote-clone'),
    ]
    for name, scenario, kind in scenarios:
        drive(baseline, 'baseline', name, scenario, kind)
        drive(runtime, 'target', name, scenario, kind)
    for kind in ['remote-supplied', 'remote-clone']:
        drive(runtime, 'target', kind + '-control', 'Rejected origins containing a newline cannot inject origin data into diagnostic output', kind, SOURCE + '\nfm-fake-source-secret')
    drive(runtime, 'target', 'matched-origins', 'Matching credential-bearing origins seed successfully, preserve origins, and allow reseeding', 'match')
finally:
    for phase in ['target', 'baseline']:
        (EVIDENCE / (phase + '-cli-transcript.txt')).write_text('Real Firstmate CLI and real Git, isolated local homes. Only conspicuously fake credentials were used.\nNo real credential-bearing origin was searched for or observed.\nRevision: ' + (TARGET if phase == 'target' else BASE) + '\n' + ''.join(transcripts[phase]))
    (EVIDENCE / 'scenario-results.json').write_text(json.dumps({'target': TARGET, 'target_tree': command(['git', 'rev-parse', TARGET + '^{tree}']).stdout.strip(), 'baseline': BASE, 'results': results}, indent=2) + '\n')
    (EVIDENCE / 'fixture-setup.txt').write_text('All listed origins are conspicuously fake. All repositories below were created solely for this run.\n' + ''.join(setup_lines))
    shutil.rmtree(SCRATCH)

assert len(results) == 11, 'A scenario did not finish'
assert all(r.get('pass', r.get('expected_baseline_reproduction')) for r in results), 'See scenario-results.json for failures'
print('All current-revision scenarios passed; four baseline diagnostics reproduced the synthetic exposure. Scratch environments removed.')
