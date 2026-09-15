# Targeted scanner selection

The baseline used the existing `tests/fm-prepush-voice-guard.test.sh` in a temporary adjacent copy named `tests/.voice-guard-scanner-only.test.sh`.
Only the final top-level call to `test_lint_default_path_runs_the_voice_guard` was replaced with an explicit not-run notice because this phase forbids executing linters.
All scanner cases and assertions were unchanged; this is not evidence that the lint integration test passed.

Command:

```sh
TMPDIR="$PWD/.voice-guard-live-check" bin/fm-test-run.sh --jobs 1 tests/.voice-guard-scanner-only.test.sh
```

The temporary adapter and all isolated Git repositories were removed after verification.
No tracked source or test file was modified.
