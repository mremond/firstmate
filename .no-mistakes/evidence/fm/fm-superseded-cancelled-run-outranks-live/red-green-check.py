#!/usr/bin/env python3
"""Run unchanged behavioral assertions against historical and current executables.

The source extraction below only loads existing test definitions without their
unconditional suite entrypoint. Evidence comes from executing fm-crew-state,
never from assertions about implementation source. no-mistakes and tmux are
the existing suite's fakes; these checks are expressly NON-LIVE.
"""
import os
from pathlib import Path
import subprocess

ROOT = Path('/Users/mremond/.no-mistakes/worktrees/acf4a767348a/01M2GV0N1CJ7TGNYN3P76KK9TS')
EVIDENCE = Path('/Users/mremond/.no-mistakes/evidence/01M2GV0N1CJ7TGNYN3P76KK9TS')
SCRATCH = ROOT / '.test-3215'
os.chdir(ROOT)
(SCRATCH / 'tmp').mkdir(parents=True, exist_ok=True)
cases = {
    '80556bca2d728071cc14476b9bee60a8edf4159e': [
        'test_superseded_cancelled_run_preserves_replacement_gate',
        'test_competing_live_runs_report_unknown_with_both_ids',
    ],
    '5588b3ea1f86e662ef505aaf30d5ec03da9c4c31': [
        'test_live_to_terminal_inventory_disagreement_is_unknown',
        'test_uninitialized_busy_worker_uses_pane',
        'test_uninitialized_idle_worker_uses_status',
        'test_historical_inventory_uses_current_pane',
        'test_historical_inventory_uses_current_status',
        'test_complete_inventory_without_python_keeps_gate',
        'test_complete_ambiguity_without_python_names_both_ids',
    ],
    '97042be0': [
        'test_complete_inventory_ignores_unrelated_semantics',
        'test_requested_branch_has_no_character_whitelist',
        'test_capped_inventory_ignores_unrelated_semantics',
        'test_capped_requested_semantics_do_not_hide_ids',
        'test_capped_requested_branch_with_comma_names_both_ids',
    ],
}
wrapper = SCRATCH / 'capture-crew-state.sh'
wrapper.write_text('''#!/usr/bin/env bash
out=$("$FM3215_PRODUCT" "$@")
rc=$?
printf '$ bin/fm-crew-state.sh %s\n%s\n' "$*" "$out" >&2
printf '%s\n' "$out"
exit "$rc"
''')
wrapper.chmod(0o755)
definitions = (ROOT / 'tests/fm-crew-state.test.sh').read_text().split('\ntest_active_run_is_authoritative\n', 1)[0]
definitions = definitions.replace('. "$(dirname "${BASH_SOURCE[0]}")/lib.sh"', '. "$FM3215_REPO/tests/lib.sh"', 1)
runner = SCRATCH / 'selected-regressions.sh'
runner.write_text(definitions + '\nCREW_STATE="$FM3215_WRAPPER"\n"$FM3215_CASE"\n')
failures = []
with (EVIDENCE / 'red-green-cli-transcript.log').open('w') as log:
    log.write('NON-LIVE REGRESSION EVIDENCE: unchanged assertions, real fm-crew-state executable, fixture no-mistakes/tmux inputs.\n')
    for ref, names in cases.items():
        historical = SCRATCH / ('historical-' + ref[:8])
        historical.mkdir(exist_ok=True)
        archive = subprocess.check_output(['git', 'archive', ref, 'bin'])
        subprocess.run(['tar', '-x', '-C', str(historical)], input=archive, check=True)
        for name in names:
            for phase, product in [('RED', historical / 'bin/fm-crew-state.sh'), ('GREEN', ROOT / 'bin/fm-crew-state.sh')]:
                env = dict(os.environ, TMPDIR=str(SCRATCH / 'tmp'), FM3215_REPO=str(ROOT), FM3215_PRODUCT=str(product), FM3215_WRAPPER=str(wrapper), FM3215_CASE=name)
                result = subprocess.run(['bash', str(runner)], env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
                log.write(f'\n{phase} {name} against {ref if phase == "RED" else "7feb0272"}\n')
                log.write(result.stdout)
                log.write(f'exit: {result.returncode}\n')
                expected = result.returncode != 0 if phase == 'RED' else result.returncode == 0
                print(f'{phase} {name}: {"expected outcome" if expected else "UNEXPECTED"}', flush=True)
                if not expected:
                    failures.append(f'{phase}: {name}')
                log.flush()
if failures:
    raise SystemExit('\n'.join(failures))
