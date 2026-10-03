Target 0e1083e793462bd62a370a7d997d1fe9bd136401

Live validation used an isolated named Herdr lab and real Pi / Codex CLIs. Watcher and consumer entrypoints ran in fresh shell processes with real helpers and transport, without fake panes or replacement production functions. Pi loaded the production fm-spawn worker-extension template bound to this lab. Grace=0 accelerated due checks; the default busy maximum remained two.

See live-results.json for scope, pi-watcher-live.json for baseline/target behavior, pi-regressions-live.json for transitions, end-to-end-supervisor.txt for the delivered escalation, consumer-live.log for all six dispatch/fault-recovery cases, and mutation-results.json for target-versus-mutant results.

The initial consumer setup grouped three reasons for one endpoint; the real wake drain intentionally coalesced them to the newest reason. Each reason was then queued and delivered separately. consumer-setup-batch-attempt.log records the setup correction, not a product failure. Codex was tried as a busy worker but classified unknown codex-unverified; watcher-baseline-* and watcher-fixed-* are unsuccessful setup attempts, not busy proof. Pi supplied fresh busy proof.

Normal Claude authentication was confirmed without exposing credentials. Its worktree launch rendered claude-trust-blocker.txt. A local configuration lacked login. No trust store or credentials were changed. The supplied earlier Claude AskUserQuestion proof is historical; the watcher and inbox library are unchanged from that evidence commit.

pi-live-session.html is the actual Pi product export; pi-live-session.png is its browser screenshot, not a reconstructed terminal. Text captures show the live terminal and supervisor.

Only focused tests ran: no lint, formatter, static analysis, full suite, pipeline control, push, PR, or CI operations. Lab teardown returned zero and verified the default-session tripwire.
