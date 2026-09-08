# Bearings test phase — round 2

Target: fa83a5cee3349e6a64902705056b69192a16eed6

Fresh product checks used two disposable FM_HOME directories, actual tmux endpoints, busy-event state, PR registration, home-summary production, Bearings snapshots, the shipped board builder and a real isolated Lavish listener. No fake executables were used in this live path. Historical registration mtimes were backdated to exercise wait age; FM_BEARINGS_NOW advanced only the consumer clock. The board payload was composed from the fresh snapshot using the existing Bearings contract, with the shipped product design.

The CLI checks show distinct same-repository owners; recorded links on active, queued and delivered work; rejection of prose-only dependency links; approval-owed and resumed/failed/blocked/undeclared-done exclusions; same-PR wait preservation; declared wait survival after endpoint exit; and all overdue deliveries retained above the display bound when the consuming clock ages the same ledger. Invalid owner, link, waiting-age and absent-awaiting payloads refuse without replacing the published board.

The real browser displayed the board at desktop and 390px. The mobile exit-rule label fits at x=28..289. The 23-day delivery is a Captain's Call nudge. Selecting Leave it, queuing the answer and sending it through Lavish produced fm-bearings-nudge.v1 in the actual process-event capture; the nudge reader returns the request while task-answer and reconcile readers return nothing. The unrelated captain hold was unchanged.

Supporting checks: the complete focused board-render test file was rerun, along with the matching-poll/open-approval snapshot selector. These use stubs and are not live. The earlier round's targeted snapshot, validator and delivery-clock results remain baseline evidence; the only code change since that baseline is heading flex wrapping. No full repository suite, linters, formatters, static analysis, other gate phases or publication commands were run.

Limit: a completed no-mistakes run followed by a fresh unresolved approval is covered by the targeted regression, but could not be driven against an actual completed isolated run. This phase has no authority to create/control another pipeline, and no completed isolated run with matching task metadata was supplied. The outer executor can supply that state for a live rerun.

Setup corrections: disposable tasks needed existing worktree directories and PR re-registration after metadata edits; secondmate homes needed a sibling isolated code root. The Chrome wrapper lacks the required pageId in evaluate calls; the installed full Chromium stalled, so verification used the already-cached Chromium headless shell and CDP. Lavish's temporary layout-check overlay was dismissed through its Show anyway control before capturing evidence. Nothing was installed or globally configured.

The live counterfactual reproduced the original clipping: undoing only heading wrapping puts the label at x=155..415 at a 390px viewport; restoring shipped CSS places it at x=28..289. Both screenshots and the geometry transcript are retained.
