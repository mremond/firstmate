"""Exercise the real runner CLI; compare its output with independent CI artifacts.

Historical timing replay is supporting evidence, not a live CI job.
No implementation-source parsing is used as an assertion.
"""
import collections
import json
import os
from pathlib import Path
import shlex
import subprocess

ROOT = Path('/Users/mremond/.no-mistakes/worktrees/acf4a767348a/01M2GB01EQ2MPCJ200TG71Y9SV')
EVIDENCE = Path('/Users/mremond/.no-mistakes/evidence/01M2GB01EQ2MPCJ200TG71Y9SV')
RUNS = ['34413640474', '34413651260', '34413670094', '34439204619', '34466966385']
env = dict(os.environ, TMPDIR=str(ROOT / '.test-phase-tmp'))
records = []


def cli(args, expected=0, baseline=False):
    runner = 'bin/.test-phase-baseline-run.sh' if baseline else 'bin/fm-test-run.sh'
    command = ['/bin/bash', runner, *args]
    completed = subprocess.run(command, cwd=ROOT, env=env, text=True, capture_output=True)
    record = dict(command=shlex.join(command), exit=completed.returncode,
                  stdout=completed.stdout, stderr=completed.stderr)
    records.append(record)
    (EVIDENCE / 'live-cli-transcript.json').write_text(json.dumps(records, indent=2) + '\n')
    print(f"{record['command']} -> exit {completed.returncode}", flush=True)
    assert completed.returncode == expected, record
    return completed.stdout


def timing_rows(path):
    doc = json.loads(path.read_text())
    lanes = [x for x in doc['lanes'] if x['selection'].startswith('lane=portable-serial-')]
    assert len(lanes) == 5, path
    assert all(x['summary']['failed'] == 0 for x in lanes), path
    rows = [x for x in doc['scripts'] if x['lane_selection'].startswith('lane=portable-serial-')]
    assert all(x['exit'] == 0 for x in rows), path
    assert len({x['path'] for x in rows}) == len(rows), path
    return rows


weights = {}
provenance = {}
for run in RUNS:
    for row in timing_rows(EVIDENCE / 'source-runs' / run / 'fm-test-timing-aggregate.json'):
        path, duration = row['path'], row['duration_ms']
        if duration > weights.get(path, -1):
            weights[path] = duration
            provenance[path] = dict(run=run, duration_ms=duration)

coverage = cli(['--check-coverage'])
assert coverage.startswith('FM_TEST_COVERAGE ok '), coverage
fields = dict(item.split('=', 1) for item in coverage.split()[2:])
lanes = [x for x in cli(['--list-lanes']).splitlines() if x.startswith('portable-serial-')]
assert lanes == [f'portable-serial-{i}of5' for i in range(1, 6)], lanes
serial = cli(['--list', '--lane', 'portable-serial']).splitlines()
assert len(serial) == len(set(serial)) == int(fields['serial'])

# Two retained hints predate the five refresh runs; the remaining unknown
# scripts exercise the documented default weight. These contract inputs are
# explicit; the verifier never extracts constants from implementation source.
retained = {'tests/fm-agy-harness.test.sh': 11000,
            'tests/fm-agy-signals-live-e2e.test.sh': 23}
weight = {path: weights.get(path, retained.get(path, 27000)) for path in serial}
unhinted = sorted(set(serial) - set(weights) - set(retained))
assert len(unhinted) == int(fields['serial_unhinted'])
assert len(unhinted) * 100 <= len(serial) * 15
expected_bins = [[] for _ in lanes]
loads = [0 for _ in lanes]
for path in sorted(serial, key=lambda p: (-weight[p], p)):
    lane = min(range(len(lanes)), key=lambda i: (loads[i], i))
    expected_bins[lane].append(path)
    loads[lane] += weight[path]

actual_bins = []
for index, lane in enumerate(lanes):
    members = cli(['--list-scheduled', '--lane', lane]).splitlines()
    assert members == expected_bins[index], dict(lane=lane, expected=expected_bins[index], actual=members)
    actual_bins.append(members)
assert collections.Counter(p for lane in actual_bins for p in lane) == collections.Counter(serial)
assert cli(['--list-scheduled', '--lane', lanes[0]]).splitlines() == actual_bins[0]
assert max(loads) - min(loads) <= max(loads) * 0.01

for lane in ['portable-serial-1of4', 'portable-serial-0of5', 'portable-serial-6of5', 'portable-serial-1']:
    assert not cli(['--list', '--lane', lane], expected=2)
for lane in ['portable-serial', *lanes]:
    assert not cli(['--jobs', '2', '--lane', lane], expected=2)
    assert 'FM_TEST_BEGIN' not in records[-1]['stdout']

result = dict(target=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
              coverage=coverage.strip(), provenance=provenance,
              retained_hint_inputs=retained, unhinted=unhinted,
              shard_counts=list(map(len, actual_bins)), hint_loads_ms=loads,
              exact_assignment_matches_independent_ci_maxima=True,
              deterministic=True, partition_complete_and_disjoint=True,
              invalid_lane_and_concurrency_requests_refused_before_execution=True)

# Counterfactual: the previous executable operates on the same current
# inventory. Score both CLI-generated partitions with one held-out CI run.
old_bins = [cli(['--list-scheduled', '--lane', lane], baseline=True).splitlines() for lane in lanes]
assert old_bins != actual_bins, 'Baseline unexpectedly satisfies refreshed assignment oracle'
held_out = {r['path']: r['duration_ms'] for r in timing_rows(
    EVIDENCE / 'held-out/34447627189/fm-test-timing-aggregate.json')}
old_scores = [sum(held_out.get(p, 0) for p in lane) for lane in old_bins]
new_scores = [sum(held_out.get(p, 0) for p in lane) for lane in actual_bins]
assert max(new_scores) < max(old_scores), (old_scores, new_scores)
result['historical_replay_not_live_ci'] = dict(run='34447627189',
    base='036fec054283882c1cfaa3e66e6f8d16ff4f4b5f',
    baseline_assignment_rejected_by_refreshed_oracle=True,
    before_ms=old_scores, after_ms=new_scores,
    measured_scripts=len(set(serial) & set(held_out)),
    missing_from_held_out=sorted(set(serial) - set(held_out)),
    note='Partial historical script-time sums, not current job wall time; missing scripts excluded equally.')
(EVIDENCE / 'packing-verification.json').write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps({k: v for k, v in result.items() if k != 'provenance'}, indent=2), flush=True)
