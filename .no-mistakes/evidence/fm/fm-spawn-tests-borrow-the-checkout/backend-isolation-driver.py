import datetime
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess

ROOT = Path('/Users/mremond/.no-mistakes/worktrees/acf4a767348a/01M22CWXBPJDKDAMCBR4YS0HF6')
EVIDENCE = Path('/Users/mremond/.no-mistakes/evidence/01M22CWXBPJDKDAMCBR4YS0HF6')
BASE = '0fe226c93efdd12a38f1c3936d758571e40111b7'
TARGET = '28e89fb9221cf6f07918ca1c8c41b1649411d0de'
TMP = ROOT / '.nm-backend-validation-tmp'
BASE_FULL = ROOT / 'tests/.nm-backend-base-full.sh'
BASE_CASES = ROOT / 'tests/.nm-backend-base-cases.sh'
TARGET_CASES = ROOT / 'tests/.nm-backend-target-cases.sh'
log = (EVIDENCE / 'backend-isolation.log').open('x')
records = []

def emit(s):
    print(s, flush=True)
    log.write(s + '\n')
    log.flush()

def check_absent():
    if (ROOT / 'state').exists():
        raise RuntimeError('checkout state/ must be absent for this experiment')

for p in [TMP, BASE_FULL, BASE_CASES, TARGET_CASES, ROOT / 'state', ROOT / 'data', ROOT / 'config', ROOT / 'projects']:
    if p.exists() or p.is_symlink():
        raise RuntimeError(f'preexisting path must be preserved: {p}')
for task in ['spawnsymlinkphysical', 'spawnsymlinklogical', 'nobackendz3', 'explicitbackendz4', 'nestbackendz5', 'teardownconform1']:
    if Path('/tmp/fm-' + task).exists():
        raise RuntimeError(f'preexisting product temp directory for {task}; refusing test cleanup collision')
if subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip() != TARGET:
    raise RuntimeError('target mismatch')

# These derivative entry points retain every existing test function. Only the
# invocation trailer is replaced to run a named existing case independently.
# Assertions execute fm-spawn and inspect its output/state, never source text.
footer = r'''
eval "$(declare -f expect_code | sed '1s/expect_code/nm_expect_code/')"
expect_code() {
  printf 'PRODUCT RESULT: %s\nobserved exit=%s expected=%s\n' "$3" "$2" "$1"
  nm_expect_code "$@"
}
"$@"
nm_result=$?
[ "$nm_result" -eq 0 ] || exit "$nm_result"
for nm_home in "$TMP_ROOT"/case-home-*; do
  [ -d "$nm_home/state" ] || continue
  printf 'PRIVATE HOME EXISTS: %s/state\n' "$nm_home"
done
for nm_meta in "$TMP_ROOT"/*state*/*.meta; do
  [ -f "$nm_meta" ] || continue
  printf 'PERSISTED TASK METADATA: %s\n' "$nm_meta"
  cat "$nm_meta"
done
'''

def functions_only(source):
    prefix, sep, trailer = source.rpartition('\ntest_backend_name_precedence\n')
    if not sep:
        raise RuntimeError('test invocation trailer not found')
    return prefix + '\n' + footer

env = {k: v for k, v in os.environ.items() if not k.startswith(('FM_', 'HERDR_', 'CMUX_', 'ORCA_', 'ZELLIJ')) and k not in ('TMUX', 'TMUX_PANE', '__CFBundleIdentifier')}
env['TMPDIR'] = str(TMP)


def run(label, cmd, expected, absent=True):
    if absent:
        check_absent()
    emit(f'\nEXPERIMENT: {label}\nCOMMAND: {shlex.join(cmd)}\ncheckout state before={"present" if (ROOT / "state").exists() else "absent"}; FM_HOME unset; real tmux/Treehouse replaced by existing test fakes')
    proc = subprocess.run(cmd, cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=180)
    emit(proc.stdout.rstrip())
    state_after = (ROOT / 'state').exists()
    emit(f'EXIT: {proc.returncode}; checkout state after={"present" if state_after else "absent"}')
    result = {'label': label, 'command': shlex.join(cmd), 'exit': proc.returncode, 'expected_exit': expected, 'checkout_state_after': state_after, 'live': False}
    records.append(result)
    if proc.returncode != expected:
        raise RuntimeError(f'{label}: expected exit {expected}, observed {proc.returncode}')
    if expected == 1 and 'could not resolve the shared Treehouse project lock' not in proc.stdout:
        raise RuntimeError(f'{label}: failed for a different reason')
    if absent and state_after and label != 'target full portable backend script':
        raise RuntimeError(f'{label}: created checkout state')

try:
    TMP.mkdir()
    baseline = subprocess.check_output(['git', 'show', BASE + ':tests/fm-backend.test.sh'], cwd=ROOT, text=True)
    target = (ROOT / 'tests/fm-backend.test.sh').read_text()
    BASE_FULL.write_text(baseline)
    BASE_CASES.write_text(functions_only(baseline))
    TARGET_CASES.write_text(functions_only(target))
    emit(f'Started {datetime.datetime.now(datetime.timezone.utc).isoformat()}\nBASE={BASE}\nTARGET={TARGET}\nOnly tests changed. This transcript is non-live behavioral regression evidence.')
    run('baseline full portable backend script, fresh checkout', ['bash', str(BASE_FULL.relative_to(ROOT))], 1)
    cases = [
        ('symlink physical cwd', ['run_spawn_symlink_case', 'physical', 'physical']),
        ('symlink logical cwd', ['run_spawn_symlink_case', 'logical', 'logical']),
        ('explicit default tmux metadata', ['test_spawn_default_backend_writes_no_meta_field']),
        ('explicit tmux beats Herdr marker', ['test_spawn_explicit_backend_flag_beats_autodetect_herdr_env']),
        ('nested tmux autodetection stays silent', ['test_spawn_autodetect_nesting_resolves_tmux_silently']),
    ]
    for label, args in cases:
        run('baseline isolated: ' + label, ['bash', str(BASE_CASES.relative_to(ROOT)), *args], 1)
    (ROOT / 'state').mkdir()
    run('baseline counterfactual: symlink physical cwd with checkout state present', ['bash', str(BASE_CASES.relative_to(ROOT)), 'run_spawn_symlink_case', 'physical', 'physical'], 0, absent=False)
    shutil.rmtree(ROOT / 'state')
    for label, args in reversed(cases):
        run('target isolated: ' + label, ['bash', str(TARGET_CASES.relative_to(ROOT)), *args], 0)
    run('target full portable backend script', ['bin/fm-test-run.sh', '--jobs', '1', '--per-script-timeout-secs', '180', 'tests/fm-backend.test.sh'], 0)
    emit('Full-script checkout state inventory (deliberate default-home refusal cases):')
    if (ROOT / 'state').exists():
        for p in sorted((ROOT / 'state').rglob('*')):
            emit(str(p.relative_to(ROOT)))
    emit('All expected RED/GREEN observations confirmed. No Herdr-gated script executed.')
finally:
    for p in [BASE_FULL, BASE_CASES, TARGET_CASES]:
        if p.exists():
            p.unlink()
    for p in [TMP, ROOT / 'state', ROOT / 'data', ROOT / 'config', ROOT / 'projects']:
        if p.exists():
            shutil.rmtree(p)
    emit('Removed only the transient paths verified absent at experiment start; checkout state is absent again.')
    (EVIDENCE / 'backend-isolation-results.json').write_text(json.dumps({'base': BASE, 'target': TARGET, 'experiments': records}, indent=2) + '\n')
    log.close()
