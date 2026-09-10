#!/usr/bin/env python3
"""Run only origin secrecy regressions and real CLI scenarios in disposable homes."""
import hashlib, io, json, os, pathlib, shlex, shutil, subprocess, tarfile
ROOT = pathlib.Path('/Users/mremond/.no-mistakes/worktrees/acf4a767348a/01M25ATVD3PSSRADPY7RVSYKZM')
EVIDENCE = pathlib.Path('/Users/mremond/.no-mistakes/evidence/01M25ATVD3PSSRADPY7RVSYKZM')
SCRATCH = ROOT / '.origin-cli-validation'
BASE = 'b1ad702fafdd03d94e5ce47cd4ba86e589ad33d6'
TARGET = '4c4f2553d3c36ff59d3d571bdd8608ddd88effca'
assert not SCRATCH.exists(), 'scratch path already exists'
SCRATCH.mkdir()
(SCRATCH / 'tmp').mkdir()
env = {k:v for k,v in os.environ.items() if not k.startswith(('FM_', 'GIT_'))}
env.update(GIT_CONFIG_GLOBAL='/dev/null', GIT_CONFIG_NOSYSTEM='1', GIT_TERMINAL_PROMPT='0',
           GIT_AUTHOR_NAME='Origin CLI Test', GIT_AUTHOR_EMAIL='test@example.invalid',
           GIT_COMMITTER_NAME='Origin CLI Test', GIT_COMMITTER_EMAIL='test@example.invalid',
           GIT_CONFIG_COUNT='2', GIT_CONFIG_KEY_0='core.hooksPath', GIT_CONFIG_VALUE_0='/dev/null',
           GIT_CONFIG_KEY_1='init.defaultBranch', GIT_CONFIG_VALUE_1='main', TMPDIR=str(SCRATCH / 'tmp'))

def run(args, cwd=ROOT, extra=None, ok=True):
    p = subprocess.run([str(a) for a in args], cwd=cwd, env=env | (extra or {}), capture_output=True, text=True, timeout=90)
    if ok and p.returncode:
        raise RuntimeError(f'{shlex.join(map(str,args))}: {p.returncode}\n{p.stdout}\n{p.stderr}')
    return p

def git(*args, **kw): return run(['git', *args], **kw)

def snapshot(ref, label):
    code = SCRATCH / ('code-' + label)
    code.mkdir()
    raw = subprocess.check_output(['git', 'archive', ref], cwd=ROOT)
    with tarfile.open(fileobj=io.BytesIO(raw)) as archive:
        archive.extractall(code, filter='tar')
    # The snapshot becomes a standalone disposable repository so public seeding
    # and existing tests can clone it without reading the gate's bare repository.
    git('init', '-q', code)
    git('-C', code, 'add', '.')
    git('-C', code, 'commit', '-qm', 'Disposable product snapshot')
    return code

cases = [
 'test_home_seed_refuses_existing_remote_backed_project_with_wrong_origin',
 'test_home_seed_refuses_seeded_project_without_origin_without_printing_source',
 'test_remote_home_seed_refuses_supplied_origin_without_printing_it',
 'test_remote_home_seed_refuses_clone_origin_without_printing_it',
]
manifest = {'base':BASE, 'target':TARGET, 'tree':git('rev-parse', 'HEAD^{tree}').stdout.strip(), 'synthetic_credentials_only':True, 'runs':[]}

def focused_regressions(code):
    source = (code / 'tests/fm-secondmate-safety.test.sh').read_text()
    definitions, sep, _ = source.partition('\ntest_fm_home_parameterization\n')
    assert sep, 'No function-invocation boundary'
    # Only select invocations; preserve every test function and assertion.
    focused = code / 'tests/fm-origin-selected.test.sh'
    focused.write_text(definitions + '\n' + '\n'.join(cases) + '\n')
    p = run(['bash', code / 'bin/fm-test-run.sh', 'tests/fm-origin-selected.test.sh'], cwd=code, ok=False)
    (EVIDENCE/'selected-regressions.log').write_text('Selected unchanged functions from tests/fm-secondmate-safety.test.sh:\n' + '\n'.join(cases) + '\n\n' + p.stdout + p.stderr)
    manifest['selected_regressions'] = {'functions':cases, 'exit':p.returncode}
    assert p.returncode == 0, p.stdout + p.stderr

src_parts = ['synthetic-source-user', 'synthetic-source-password', 'source-host.invalid', '/source-private-repo.git']
dst_parts = ['synthetic-destination-user', 'synthetic-destination-password', 'destination-host.invalid', '/destination-private-repo.git']
src_origin = f'https://{src_parts[0]}:{src_parts[1]}@{src_parts[2]}{src_parts[3]}'
dst_origin = f'https://{dst_parts[0]}:{dst_parts[1]}@{dst_parts[2]}{dst_parts[3]}'
refused = src_origin.replace(src_parts[2], src_parts[2] + ':notaport')

def make_project(path, origin):
    path.mkdir(parents=True)
    git('init', '-q', path)
    (path/'README.md').write_text('Synthetic seeding validation repository.\n')
    git('-C', path, 'add', 'README.md')
    git('-C', path, 'commit', '-qm', 'Synthetic project')
    if origin: git('-C', path, 'remote', 'add', 'origin', origin)

def state_digest(project):
    files = ['.git/config', 'README.md']
    return {f: hashlib.sha256((project/f).read_bytes()).hexdigest() for f in files}

def scenario(code, label, name, origin=src_origin, destination=dst_origin, remote=False, supplied=False, success=False, expect_leak=False):
    loc = SCRATCH / (label + '-' + name)
    main = loc / 'main'
    main.mkdir(parents=True)
    for d in ['data', 'state', 'projects']: (main/d).mkdir()
    (main/'data/projects.md').write_text('- alpha [direct-PR] - synthetic validation project (added 2026-09-10)\n')
    project = main/'projects/alpha'
    make_project(project, origin)
    before_src = state_digest(project)
    extra = {'FM_HOME':str(main), 'FM_SECONDMATE_CHARTER':'Synthetic origin validation', 'FM_SECONDMATE_SCOPE':'Synthetic origin validation'}
    run([code/'bin/fm-brief.sh', 'origin-check', '--secondmate', 'alpha'], extra=extra)
    if remote:
        args = [code/'bin/fm-remote-home-seed.sh', 'origin-check', 'nonexistent-origin-validation-host', str(loc/'remote-code'), str(loc/'remote-home'), 'alpha='+origin if supplied else 'alpha']
    else:
        sub = loc/'seeded'
        git('clone', '--quiet', code, sub)
        dest = sub/'projects/alpha'
        make_project(dest, destination)
        before_dst = state_digest(dest)
        args = [code/'bin/fm-home-seed.sh', 'origin-check', sub, 'alpha']
    p = run(args, extra=extra, ok=False)
    output = p.stdout+p.stderr
    leaked = [part for part in src_parts+dst_parts if part in output]
    states_ok = state_digest(project) == before_src
    if not remote: states_ok = states_ok and state_digest(dest) == before_dst
    marker_ok = True
    if success:
        marker_ok = (sub/'.fm-secondmate-home').read_text().strip() == 'origin-check'
        marker_ok = marker_ok and 'origin-check' in (main/'data/secondmates.md').read_text()
        marker_ok = marker_ok and (sub/'data/charter.md').read_text() == (main/'data/origin-check/brief.md').read_text()
    else:
        marker_ok = not (main/'data/secondmates.md').exists()
        if not remote: marker_ok = marker_ok and not (sub/'.fm-secondmate-home').exists()
    expected_diag = 'home=' if success else ('not an accepted clone URL' if remote else ('has no origin remote' if destination is None else ('has origin' if expect_leak else 'has a different origin')))
    useful_diag = expected_diag in output
    if not expect_leak and not success:
        useful_diag = useful_diag and (('alpha=<origin-url>' in output) if remote and supplied else str(project) in output)
        if not remote: useful_diag = useful_diag and str(dest) in output
    passed = (p.returncode == (0 if success else 1)) and states_ok and marker_ok and useful_diag and (bool(leaked) if expect_leak else not leaked)
    result = {'label':label,'name':name,'exit':p.returncode,'command':shlex.join(map(str,args)), 'live':True,
              'passed':passed,'synthetic_origin_components_in_output':leaked,
              'source_and_destination_preserved':states_ok,'expected_registry_and_markers':marker_ok,'useful_diagnostic':useful_diag}
    transcript = f'Commit: {TARGET if label == "target" else BASE}\nSynthetic credentials only; no real account or server used.\n\n$ FM_HOME={shlex.quote(str(main))} {shlex.join(map(str,args))}\nexit: {p.returncode}\nstdout:\n{p.stdout or "(empty)\n"}\nstderr:\n{p.stderr or "(empty)\n"}\nChecks:\n' + json.dumps(result,indent=2) + '\n'
    if success:
        transcript += '\nPersisted secondmate registry:\n' + (main/'data/secondmates.md').read_text() + '\nPersisted identity marker:\n' + (sub/'.fm-secondmate-home').read_text()
    evidence = f'{label}-{name}.log'
    (EVIDENCE/evidence).write_text(transcript)
    result['evidence'] = evidence
    manifest['runs'].append(result)
    print(f'{label}/{name}: {"PASS" if passed else "FAIL"}, exit={p.returncode}, origin components printed={len(leaked)}', flush=True)
    return passed

try:
    target_code = snapshot(TARGET, 'target')
    focused_regressions(target_code)
    checks = []
    for label, code in [('target',target_code), ('base',snapshot(BASE, 'base'))]:
        baseline = label == 'base'
        checks.append(scenario(code,label,'two-credential-origin-mismatch',expect_leak=baseline))
        checks.append(scenario(code,label,'missing-destination-origin',destination=None,expect_leak=baseline))
        checks.append(scenario(code,label,'rejected-explicit-origin',origin=refused,remote=True,supplied=True,expect_leak=baseline))
        checks.append(scenario(code,label,'rejected-configured-origin',origin=refused,remote=True,expect_leak=baseline))
    checks.append(scenario(target_code,'target','matching-credential-origins',destination=src_origin,success=True))
    checks.append(scenario(target_code,'target','rejected-newline-origin',origin=refused+'\nSYNTHETIC-INJECTED-LINE',remote=True,supplied=True))
    assert 'SYNTHETIC-INJECTED-LINE' not in (EVIDENCE/'target-rejected-newline-origin.log').read_text().split('stdout:\n',1)[1].split('\nChecks:',1)[0]
    manifest['passed'] = all(checks)
finally:
    (EVIDENCE/'origin-validation-results.json').write_text(json.dumps(manifest,indent=2)+'\n')
    shutil.rmtree(SCRATCH)
    print('Disposable worktree layout removed.', flush=True)
assert manifest.get('passed'), 'A scenario failed; inspect evidence'
