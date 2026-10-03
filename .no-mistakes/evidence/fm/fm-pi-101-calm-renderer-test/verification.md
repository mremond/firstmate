# Pi Calm renderer compatibility validation

Target: `02ea4dbf351251a3bfba31f81c979f3131a4e2a7`, tree `b9621b9ccdc42ab6a79780f571b407a162d38d29`.
Base: `1f3e769616fdf9f31f85f4c3e6a9f71606634238`.
Environment: macOS, Node v25.9.0, npm 11.17.0, Chrome 154.0.8037.97.

| Check | Result and evidence |
| --- | --- |
| Original test on Pi 1.0.1 | Reproduced `grep disappeared from /export calm.html HTML while calm mode was on`; [baseline transcript](baseline-pi-1.0.1/test.log). |
| Target on Pi 1.0.1 | Complete targeted Calm suite passed without skips, including real terminal sessions and export; [transcript](target-pi-1.0.1-short/test.log), [actual product export](target-pi-1.0.1-short/calm-export.html), [Chrome screenshot](pi-1.0.1-export.png). |
| Target on Pi 1.0.0 | Same suite and native checks passed without skips; [transcript](pi-1.0.0/test.log), [actual product export](pi-1.0.0/calm-export.html), [Chrome screenshot](pi-1.0.0-export.png). |
| Adversarial remapped input on Pi 1.0.1 | With Alt+S configured as submit, Enter left the command in the editor, wrote no HTML, and kept tool output hidden across 20 observations; Alt+S then exported successfully. [Transcript](live-guard/test.log), [after Enter](live-guard/remapped-enter.txt), [after Alt+S](live-guard/export-settled.txt). |

Native checks used the real Pi CLI, Calm extension, renderer, exporter, and Chrome on synthetic session data and provider responses, with isolated settings and test-owned 180x44 tmux terminals.
[Extracted output](export-tool-output.json) retains actual grep, find, and watcher call/result HTML from all three successful native exports.
Both screenshots were visually inspected and show that content.
The suite also passed component assertions for `/share`, non-submit input, and renderer/lifecycle behavior on both versions; those component assertions are supporting evidence, not live GitHub publication.

## Reproduction

Installed each version locally with:

```sh
npm install --global --prefix "$PWD/.no-mistakes/test-lab/pi-1.0.1" --cache "$PWD/.no-mistakes/test-lab/npm-cache" --no-audit --no-fund @earendil-works/pi-coding-agent@1.0.1
npm install --global --prefix "$PWD/.no-mistakes/test-lab/pi-1.0.0" --cache "$PWD/.no-mistakes/test-lab/npm-cache" --no-audit --no-fund @earendil-works/pi-coding-agent@1.0.0
```

The retained [collector](run.py) selects the same version via PATH and FM_PI_PACKAGE_DIR, isolates temporary/config paths, clears fleet overrides, and invokes `bash bin/fm-test-run.sh tests/fm-calm-pi-extension.test.sh`.
Its exact invocations were:

```sh
python3 .no-mistakes/test-lab/run.py 1.0.1 baseline-pi-1.0.1 tests/.fm-calm-pi-baseline.test.sh
python3 .no-mistakes/test-lab/run.py 1.0.1 target-pi-1.0.1 tests/fm-calm-pi-extension.test.sh
python3 .no-mistakes/test-lab/run.py 1.0.1 target-pi-1.0.1-short tests/fm-calm-pi-extension.test.sh
python3 .no-mistakes/test-lab/run.py 1.0.0 pi-1.0.0 tests/fm-calm-pi-extension.test.sh
python3 .no-mistakes/test-lab/run.py 1.0.1 live-guard tests/.fm-calm-pi-live-guard.test.sh
```

The baseline file came from `git show 1f3e769616fdf9f31f85f4c3e6a9f71606634238:tests/fm-calm-pi-extension.test.sh`.
The extra native guard was a disposable copy of the existing interactive test; its [exact patch](live-guard-driver.patch) adds the non-submit observation and selects that native scenario.
The [screenshot driver](screenshot.py) captures the real exported pages with isolated headless Chrome profiles.
No production code or permanent test was edited.

## Resolved setup issues and limits

The first target run exported successfully but its very long disposable path wrapped the confirmation after `Session exported to:`, failing the existing single-line string assertion.
The [terminal transcript](target-pi-1.0.1/export.txt) proves export completed.
Shortening the temporary root from `.no-mistakes/test-lab/tmp/` to `.v/`, still inside the workspace, fixed setup; the unchanged suite then passed on Pi 1.0.1 in 54.2 seconds and on Pi 1.0.0 in 53.9 seconds.
The initial standalone Chrome screenshot succeeded but Chrome remained running until its 35-second timeout; the final driver stops its own process after capture and succeeded for both versions.

Only the assigned test phase ran: no linters, static analysis, full repository suite, remote CI, publication, or merge.
Pi 0.85.1 was not retested; the required regression and predecessor axes were Pi 1.0.1 and 1.0.0.
The outer executor owns remaining phases and CI; the maintainer owns merging.
Disposable installations, caches, fixture homes, browser profiles, and temporary test scripts were cleaned up; evidence is retained here.
