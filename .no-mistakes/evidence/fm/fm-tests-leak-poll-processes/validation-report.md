# Test-phase evidence

Target: `3cea357284a5419aeacb0ad823b6e48091a4f826` (tree `3314fc6b5b81264c03689aa011cc25ba5ba2d6f9`).

The change prevents orphaned test polling from adding resident load that corrupts local duration measurements. Validation used only this worktree and run-owned processes; no existing fleet process was signalled.

## Observed behavior

| Scenario | Observations |
|---|---|
| Complete affected suites | Fixture cleanup, bearings renderer, and real Lavish 0.1.62 suites completed successfully. The subsequent process check found zero poll processes and zero board fixture roots in their isolated directories. |
| Real Lavish failure | Suite PID 80939; observed poll PIDs 3183, 3759, 3762. Suite exited 1; all recorded PIDs were absent, no target-matching poll remained, and the fixture home and target were removed. |
| Real Lavish sigterm | Suite PID 85201; observed poll PIDs 69527, 72160, 72167. Suite exited 143; all recorded PIDs were absent, no target-matching poll remained, and the fixture home and target were removed. |
| Own child accepted | Suite PID 40625 owned sleep PID 49693. The guard permitted teardown; PID 49693 was absent and its fixture was removed. |
| Foreign child refused | Suite PID 54747 recorded sleep PID 40604, owned by probe parent 32621. The guard refused; fixture cleanup ran and PID 40604 remained alive. The probe then terminated and reaped its own sleep. |
| Claim and marker boundaries | A real registered command source took its claim under the suite-owned root; no fallback XDG claim store appeared. Inherited claims survived child cleanup. Old live-owned and fresh unowned fixtures survived; old mismatched ownership was removed. |

## Execution

- `TMPDIR="$PWD/.test-phase/tmp" bin/fm-test-run.sh --jobs 1 tests/fm-test-fixture-cleanup.test.sh tests/fm-bearings-board-render.test.sh`
- With the isolated Lavish environment in `run-environment.json`: `TMPDIR="$PWD/.test-phase/tmp-live" bin/fm-test-run.sh --jobs 1 tests/fm-bearings-board-lavish-live-e2e.test.sh`
- `python3 guard-probe.py` (run from the worktree using the evidence script path).
- `python3 live-teardown-probe.py` (run from the worktree using the evidence script path).
- `TMPDIR="$PWD/.test-phase/storage-tmp" bash storage-boundary-probe.sh` (evidence script path).
- `python3 final-process-check.py` plus exact recorded-PID/process-group inspection and isolated-server shutdown.

The first live-suite attempt failed during board setup. The same suite passed after the isolated server was started explicitly and checked through `/health`. A scratch keeper session kept that test-only server available across subsequent probes. No repository changes were needed.

The ownership probes use Bash DEBUG instrumentation to pause the unchanged suite after it installs its actual EXIT trap. The live probes pause the unchanged live suite after the real board build, observe real `lavish-axi poll` processes, then inject a failure or SIGTERM. They do not replace teardown, mock the poll command, or assert implementation-source text. Round 5's injected failure/interruption proofs were not rerun.

No linter, formatter, static analysis, full repository suite, publication, or other gate phase ran. No UI content changed, so process and filesystem transcripts are the evidence for this change.

## Evidence

- [Live failure and interruption process records](live-teardown-probe.jsonl)
- [Child ownership guard](guard-probe.log)
- [Claim and marker state](storage-boundary-probe.log)
- [Completed-suite orphan check](completed-suite-process-check.json)
- [Final exact PID and group check](final-process-check.json)
- [Targeted suites](targeted-suites.log)
- [Successful live suite](live-suite-retry.log)
- [Initial live setup attempt](live-suite.log)
- [Environment cleanup](environment-cleanup.log)
