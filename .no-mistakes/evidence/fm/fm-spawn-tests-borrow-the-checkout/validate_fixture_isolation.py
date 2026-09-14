import json
import os
from pathlib import Path
import shutil
import subprocess
import time

ROOT = Path('/Users/mremond/.no-mistakes/worktrees/acf4a767348a/01M2GV0HN9PMBPA7YNVGGC9FSS')
EVIDENCE = Path('/Users/mremond/.no-mistakes/evidence/01M2GV0HN9PMBPA7YNVGGC9FSS')
BASE = '80556bca2d728071cc14476b9bee60a8edf4159e'
TARGET = 'a0eb3010963b43e9253d4d6b12fa902c800230a7'
scratch = ROOT / '.nm-fixture-validation'
base_full = ROOT / 'tests/.nm-base-fm-backend.test.sh'
base_focused = ROOT / 'tests/.nm-base-fm-backend-focused.sh'
target_focused = ROOT / 'tests/.nm-target-fm-backend-focused.sh'
state = ROOT / 'state'
for path in [scratch, base_full, base_focused, target_focused, state]:
    if path.exists() or path.is_symlink():
        raise SystemExit(f'Requires unused test paths and an initially absent checkout state directory: {path}')
scratch.mkdir()
(scratch / 'tmp').mkdir()
env = {key: value for key, value in os.environ.items() if not key.startswith(('FM_', 'HERDR_', 'CMUX_', 'TASKS_AXI_')) and key not in ('TMUX', 'TMUX_PANE', 'BASH_ENV', 'ENV', 'CLAUDE_CONFIG_DIR')}
env['TMPDIR'] = str(scratch / 'tmp')
env['GIT_CONFIG_GLOBAL'] = '/dev/null'
env['GIT_CONFIG_NOSYSTEM'] = '1'
records = []

# Select existing executable cases; no implementation-text assertions are added.
footer = '\ntest_backend_name_precedence\n'
capture = r'''
eval "$(declare -f expect_code | sed '1s/expect_code/nm_original_expect_code/')"
expect_code() {
  printf '\nCLI observation (expected exit %s, actual exit %s):\n%s\n' "$1" "$2" "$3"
  nm_original_expect_code "$@"
}
"$@"
nm_case_rc=$?
for nm_meta in "$TMP_ROOT"/*state*/*.meta; do
  [ -f "$nm_meta" ] || continue
  printf '\nPersisted task metadata: %s\n' "$nm_meta"
  cat "$nm_meta"
done
exit "$nm_case_rc"
'''

def run(label, args):
    before = state.exists()
    started = time.monotonic()
    result = subprocess.run(args, cwd=ROOT, env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    after = state.exists()
    record = dict(label=label, command=args, exit_code=result.returncode, checkout_state_before=before,
                  checkout_state_after=after, duration_seconds=round(time.monotonic()-started, 2),
                  live=False, log=str(EVIDENCE / (label + '.log')))
    (EVIDENCE / (label + '.log')).write_text(
        f'Base: {BASE}\nTarget: {TARGET}\nCommand: {args!r}\nFM_HOME: unset at process entry\n'
        f'Checkout state before: {before}\nBackend environment: existing fake tmux/Treehouse fixtures, not live\n\n'
        + result.stdout + f'\nExit: {result.returncode}\nCheckout state after: {after}\n')
    records.append(record)
    (EVIDENCE / 'fixture-isolation-results.json').write_text(json.dumps(records, indent=2) + '\n')
    print(json.dumps(record), flush=True)
    return result.returncode

try:
    baseline = subprocess.check_output(['git', 'show', BASE + ':tests/fm-backend.test.sh'], cwd=ROOT, text=True)
    target = (ROOT / 'tests/fm-backend.test.sh').read_text()
    base_full.write_text(baseline)
    base_focused.write_text(baseline.split(footer, 1)[0] + capture)
    target_focused.write_text(target.split(footer, 1)[0] + capture)
    cases = [
        ('symlink-physical', ['run_spawn_symlink_case', 'physical', 'physical']),
        ('symlink-logical', ['run_spawn_symlink_case', 'logical', 'logical']),
        ('default-tmux', ['test_spawn_default_backend_writes_no_meta_field']),
        ('explicit-tmux-herdr-env', ['test_spawn_explicit_backend_flag_beats_autodetect_herdr_env']),
        ('nested-tmux-herdr', ['test_spawn_autodetect_nesting_resolves_tmux_silently']),
    ]
    run('base-backend-script-state-absent', ['bash', str(base_full)])
    for label, selector in cases:
        run('base-' + label + '-state-absent', ['bash', str(base_focused), *selector])
    state.mkdir()
    run('base-symlink-physical-state-present', ['bash', str(base_focused), *cases[0][1]])
    state.rmdir()
    for label, selector in cases:
        run('target-' + label + '-state-absent', ['bash', str(target_focused), *selector])
    run('target-backend-script-state-absent', ['bin/fm-test-run.sh', 'tests/fm-backend.test.sh'])
    if state.exists():
        contents = sorted(str(path.relative_to(state)) for path in state.rglob('*'))
        (EVIDENCE / 'checkout-state-observation.txt').write_text(
            'Checkout state/ was initially absent. Each focused target case left it absent.\n'
            'The complete target script created state/, consistent with the deliberately unchanged refusal cases.\n'
            f'Contents after full target script: {contents!r}\n'
            'The empty directory was removed with rmdir after observation.\n')
        state.rmdir()
finally:
    for path in [base_full, base_focused, target_focused]:
        path.unlink(missing_ok=True)
    shutil.rmtree(scratch)
