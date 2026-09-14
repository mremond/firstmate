# Validation for issue 3215

Target: `622eb46201cb243e72bd2437c9fa76c90b38160b`  
Tree: `4f890e50d3ab369075b9134d59a15b03c9f47348`  
Base: `80556bca2d728071cc14476b9bee60a8edf4159e`

Targeted tests, artifact-backed replays, historical RED/GREEN checks, and the live uninitialized-worker fallback all passed.
This supports proceeding under the user's accepted captured-artifact approach.
It does not establish live coverage for the six compositions listed below.
No pipeline was initialized or controlled, and no source files were changed.
This is a CLI change; CLI transcripts are the reviewer-visible product evidence.

## Real evidence refreshed in this phase

- All six committed status captures match their original capture manifest hashes and retained original stdout.
- The five run-specific status commands were repeated through the real installed CLI and exited zero; uninitialized status exited one with the recorded error.
- Replacement and parked output differ only in elapsed-time information from the retained historical captures.
- A read-only transaction confirmed the same nine-row branch inventory, identical to the committed projection; this repository has 78 recorded runs and no branch with two live rows.
- The committed capped overview matches the emitted section retained from the earlier real-CLI capture against an isolated relocated database copy. That overview is recorded evidence, not a live run in this phase.
- Real tmux, `fm-busy-event.sh`, `no-mistakes axi status`, and `fm-crew-state.sh` preserved busy-event reporting and subsequent status-log reporting without an initialized gate. Events were driven directly through the product event CLI; no model session was launched.

## Required delivery-description disclosure

The following shapes remain UNTESTED LIVE. Passing replays are evidence for the explicit inputs, not proof that these histories occurred in a running pipeline.

| Shape | Real anchor | Exact absence and how live evidence could be obtained |
| --- | --- | --- |
| Superseded cancellation followed by a replacement parked at review on an unfetched rebased head | Genuine cancellation/successor history and a separate real parked test gate | The recorded successor is in CI, and the parked gate is at test on another branch. An already initialized isolated repository with the combined review-gate rerun history is needed; this phase cannot initialize or control another pipeline. |
| Two same-branch live identities, including a hidden candidate beyond ten rows and unrelated unusual branch metadata | Genuine capped overview and complete nine-row same-branch inventory | No real branch in the available inventory has two live rows. The hidden live competitor and unrelated unusual metadata are injected. Supply a genuine competing-live history for live corroboration. |
| A newer failure beside an older live run on the same branch | Genuine failed and live status outputs | Their required relative ordering is composed. An initialized isolated repository containing that actual ordered pair is needed. |
| Authority changes between inventory and ID-addressed reads, or identity/inventory cannot be verified | Genuine live and cancelled status formats | The race, mismatched identities, malformed records, and unreadable inventory are injected. Live proof needs an authorized isolated environment that can undergo those transitions or faults while reading state. |
| Development continues beyond a completed validation head | Genuine completed status | New commits and worker events are constructed in disposable repositories. Supply an initialized isolated worker repository with a completed run, then permit local development there. |
| Python or SQLite support unavailable during run selection | Genuine gate output and capped inventory | The host has both dependencies; dependency-limited PATH/import environments use replayed CLI inputs. Live corroboration needs an initialized isolated repository with complete and capped inventories while restricting only its process environment. No system dependency removal is needed. |

The uninitialized-worker fallback was driven live and passed.
All six remaining shapes have real artifact anchors where available and passing targeted replays, as explicitly requested by the user.
These absences must remain in the final PR/delivery description; this test phase does not own PR edits.

## Exact verification

- `bin/fm-test-run.sh tests/fm-crew-state.test.sh` passed on the target. Full transcript: [focused regressions](test-round2-regressions.log).
- [Live fallback driver](test-round2-live-fallback.sh) and [CLI transcript](test-round2-live-fallback.log).
- [RED/GREEN driver](test-round2-red-green.py) and [observable CLI results](test-round2-red-green.log): original supersession/ambiguity fail on the base; R1, R2, R3 and R5 fail on `5588b3ea1f86e662ef505aaf30d5ec03da9c4c31`; R6 cases fail on `97042be0`. Every unchanged assertion passes on the target.
- [Captured-input replays and fault controls](test-round2-captured-replay.log) include real successor IDs, review/test gate detail, both ambiguous IDs, wrong/missing identities, structural failures, read races, history fallbacks, optional dependency absence, and database non-mutation assertions.
- [Refreshed capture manifest](test-round2-anchors/manifest.json) and [read-only same-branch inventory](test-round2-anchors/same-branch-inventory.json).

No complete repository suite, linter, formatter, or static analyzer was run.
All scratch files and the private tmux endpoint created for this round were removed; evidence remains in the dedicated evidence directory.
