"""Execute the actual new test cases against isolated diagnostic mutations."""
from pathlib import Path
import json
import os
import subprocess

ROOT = Path('/Users/mremond/.no-mistakes/worktrees/acf4a767348a/01M22J6W2BJAVGZZ9NSGWD23SR')
EVIDENCE = Path(__file__).parent
SCRATCH = ROOT/'.local-test-lock-naming'
ENV = {k:v for k,v in os.environ.items() if not k.startswith(('FM_', 'GIT_', 'TMUX'))}
ENV.update(HOME=str(SCRATCH/'user-home'), TMPDIR=str(SCRATCH/'tmp'), FM_HOME=str(SCRATCH/'user-home'), FM_STATE_OVERRIDE=str(SCRATCH/'state'), FM_BACKEND='orca', GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL='/dev/null', GIT_CEILING_DIRECTORIES=str(SCRATCH))
subject = (ROOT/'tests/fm-treehouse-lock-naming.test.sh').read_text()
# Keep the real definitions and fixtures; select one existing case per process.
definitions = subject.split('\ntest_missing_project_directory_is_named\n')[0]+'\n'
original = (ROOT/'bin/fm-wake-lib.sh').read_text()

def make_world(name, library, test=definitions):
    world = SCRATCH/name
    (world/'bin').mkdir(parents=True, exist_ok=True)
    (world/'tests').mkdir()
    for item in (ROOT/'bin').iterdir():
        dest = world/'bin'/item.name
        if item.name == 'fm-wake-lib.sh':
            dest.write_text(library)
        else:
            dest.symlink_to(item, target_is_directory=item.is_dir())
    for name in ('lib.sh', 'fixtures.sh'):
        (world/'tests'/name).write_bytes((ROOT/'tests'/name).read_bytes())
    testfile = world/'tests/fm-treehouse-lock-naming.test.sh'
    testfile.write_text(test)
    return testfile

silent = make_world('mutant-silent', original+'\n_fm_treehouse_lock_named() { :; }\n')
noisy = make_world('mutant-noisy', original+'\nprintf "fm_treehouse_project_lock_path: unconditional diagnosis\\n" >&2\n')
parent = make_world('regression-parent', subprocess.check_output(['git','show','2da46792:bin/fm-wake-lib.sh'],cwd=ROOT,text=True))
backend = make_world('mutant-unpinned-backend', original, definitions.replace('--scout --backend tmux', '--scout'))

cases = [
 ('test_missing_project_directory_is_named', 'absent project directory'),
 ('test_unresolvable_root_home_is_named', 'home it could not resolve'),
 ('test_broken_secondmate_parent_chain_names_the_home', 'home whose chain broke'),
 ('test_missing_recorded_parent_home_is_named', 'missing recorded parent home'),
 ('test_unenterable_absolute_origin_is_named', 'origin directory it could not enter'),
 ('test_unenterable_relative_origin_is_named', 'relative origin directory'),
 ('test_originless_non_git_project_is_named', 'no origin and no worktree'),
 ('test_unenterable_worktree_top_is_named', 'worktree top it could not enter'),
 ('test_unhashable_identity_is_named', 'project identity could not be hashed'),
 ('test_missing_root_state_directory_is_named', "home's missing state directory"),
 ('test_spawn_refusal_carries_the_named_cause', 'named cause to the operator'),
]
runs = [(silent, name, reason) for name, reason in cases]
runs += [(noisy,'test_resolved_lock_path_stays_silent','resolved lock path emitted a refusal diagnostic'), (parent,'test_missing_recorded_parent_home_is_named','missing recorded parent home'), (backend,'test_spawn_refusal_carries_the_named_cause','named cause to the operator')]
log = []
results = []
try:
    for test, selector, expected in runs:
        cmd = ['/bin/bash','-c','. "$1"; "$2"','_',str(test),selector]
        p = subprocess.run(cmd,cwd=ROOT,env=ENV,text=True,capture_output=True,timeout=90)
        out = p.stdout+p.stderr
        log.extend([f'\n[{test.parent.parent.name} / {selector}]',f'exit={p.returncode}',out])
        assert p.returncode == 1 and expected in out, out
        results.append({'mutation': test.parent.parent.name, 'case': selector, 'observed': out.strip(), 'result':'expected failure'})
finally:
    (EVIDENCE/'regression-sensitivity.log').write_text('\n'.join(log)+'\n')
    (EVIDENCE/'regression-sensitivity.json').write_text(json.dumps(results,indent=2)+'\n')
print(f'All {len(results)} selected regressions failed for their named reason.')
