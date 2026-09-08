# Alpha checkout test validation

## Scope and method

Base: b84e0e362face25f3dd8945297a3df1320d7668c. Target: fae1f6a76f29be62ca537d5e404aba12f1e06ec5.
The only changed file is `tests/fm-remote-secondmate-lifecycle-e2e.test.sh`: pin alpha's bare origin to main and require the checked-out README.md instead of a .git directory.
No production code changes are present. No source or test changes were retained by this phase.

These are automated execution results, not live remote-product validation: the existing lifecycle script uses fake SSH, readiness, and backend boundaries.
The focused copies retain the existing setup and execution through alpha's checkout assertion, print actual Git/checkout state, and stop after the alpha checkpoint.
The counterfactual removes only alpha's pin and retains the stronger assertion.
Git defaults are set per process with `GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=init.defaultBranch GIT_CONFIG_VALUE_0=<master|main>`; no user or global Git settings are changed.
All runs are serial. The complete repository test suite, linters, formatters, and other pipeline phases were not run.

## Focused observed results

- `unpinned-strong-master.log`: expected exit 1 at alpha. Origin HEAD and checkout HEAD both name master; .git exists but README.md is absent. Beta has README.md and both beta HEADs name master.
- `pinned-prefix-master.log`: exit 0 through alpha. Both alpha HEADs name main; README.md contains `alpha` and matches the committed version. Beta remains paired on master and has its committed README.md.
- `pinned-prefix-main.log`: exit 0 through alpha. Alpha and beta HEADs name main and both README.md files are present; alpha's file matches its commit.
- `current-full-master.log`: the complete lifecycle file passed alpha, then failed remote launch because a sanitized subprocess found the enclosing gate repository from its temporary working directory. The next attempt added a standalone Git boundary only to the disposable temporary directory; production guard code was not changed.

`run-targeted.py` records the exact commands and constructs the focused copies. The three `.driver.sh` artifacts preserve those copies for inspection. The second complete-file attempt uses `current-full-isolated master`: `git init -q -b main` on its disposable TMPDIR avoids the enclosing gate guard. This attempt passed inheritance, snapshot, and remote update, but exited 1 at the restart refusal assertion: the enclosing temporary repository changed the invalid-checkout diagnosis to "not a worktree root". This is a second setup effect, not evidence of a changed production failure. `current-full-native-temp master` uses the existing test helper's normal temporary-directory behavior, as permitted by the test-toolchain temp-write exception, to remove both setup effects.

## Required exclusions for the delivery description

Beta's bare-origin initialization remains ambient. Its counterpart origin pin at lifecycle line 467 belongs with the separate pin to `fm_git_init_commit` at `tests/lib.sh:416`; pinning either beta side alone would break their pairing. Both files' relevant lines remain unchanged by this delivery.

The eleven examined-and-unreachable fixtures remain unchanged. The author-provided inventory is:

- Nine already set HEAD through symbolic-ref: `tests/fm-secondmate-sync.test.sh:925`, `tests/fm-review-diff.test.sh:28`, `tests/fm-secondmate-restart.test.sh:181`, `tests/fm-remote-secondmate-parent-binding.test.sh:128` and `:133`, `tests/fm-update.test.sh:70`, `tests/fm-teardown.test.sh:171`, `tests/fm-gate-refuse.test.sh:294`, and `tests/fm-remote-secondmate-lifecycle-e2e.test.sh:104`.
- `tests/fm-teardown.test.sh:216` is an unpaired fork.git.
- `tests/fm-gate-refuse.test.sh:54` has an inert HEAD mismatch with no measured effect.

This phase checked the two-line diff and the beta pairing at runtime in the automated fixture; it did not repeat the historical eleven-site reachability investigation.

## Historical outcomes and unresolved causality

The supplied intent records that the blocked-inheritance failure reproduced on unchanged trunk, with an empty tracked diff and serial execution. The target commit message records an unchanged-base and patched-main blocked-inheritance failure, and a patched-master ledger-collection timeout. These historical reports are retained as author-supplied context; their original raw logs are not present in this evidence directory and those prior controls were not rerun here.

The snapshot failure has NOT been shown independent of this change and may be caused by it. It belongs to a separate investigation, and this delivery must be reopened if that investigation attributes the failure to this change. The unchanged-trunk control stopped before the snapshot check; absence of reproduction is not proof of absence. Fixture cleanup failures remain observations only, not suggested causes.

Neither the blocked-inheritance issue nor the snapshot issue was repaired in this phase. No full repository green result is claimed. The current complete lifecycle-file result is reported separately below; it does not rewrite the historical failures.


## Final complete-file result in this run

`python3 run-targeted.py current-full-native-temp master` executed the unchanged `bash tests/fm-remote-secondmate-lifecycle-e2e.test.sh` under a process-local master default with the existing helper's normal temporary-directory behavior.
It exited 0 after 421.30 seconds and printed `ALL TESTS PASSED` after the final remote retirement checkpoint.
The blocked inheritance, mixed-state snapshot, restart pre-stop refusal, startup, and retirement checkpoints all completed in this automated run.
This successful patched run does not prove the historical snapshot timeout independent of the change; the separate investigation and reopen condition remain in force.
The two earlier complete-file attempts remain recorded with their actual exit 1 outcomes and their setup-specific causes. They were not relabeled as passes or removed.
The complete-file transcripts also contain terminal-source retirement warnings. They remain observations only; this phase does not propose them as causes of the historical failures.

## Evidence files

- [Observed alpha and beta checkout comparison](alpha-checkout-comparison.log)
- [Final complete lifecycle-file transcript](current-full-native-temp-master.log)
- [First setup attempt: enclosing gate boundary](current-full-master.log)
- [Second setup attempt: enclosing temporary Git repository](current-full-isolated-master.log)
- [Reproduction driver and exact process-local environment](run-targeted.py)

Disposable test copies and scratch data created under the worktree were removed. The tracked worktree remains unchanged.
No screenshot was needed: this change affects only a shell test fixture and assertion and has no rendered UI surface.
