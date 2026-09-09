# Stop-path test evidence

Target: `f8819bf51500b7acd82a902a081f5e84a1eec334` (tree in [run-context.txt](run-context.txt)). Base: `40c50ea8843c5b6a5351db8352675537252b653e`. Real macOS CLI and kernel processes; isolated homes and claims in the assigned worktree.

| Scenario | Observed result | Evidence |
|---|---|---|
| Retire a healthy running source | Base attached start returned 137 (KILL); target returned 143 (TERM). Supplementary retirement measurements: 12,404 ms base, 4,474 ms target under heavy load. | [Base](baseline-healthy-corrected.trace.log), [target](core.trace.log) |
| Reconcile a removed registration | `stopped=1`, attached start 143, group absent, claim removed. | [CLI transcript](live-cli-transcript.log) |
| Retire a TERM-resistant child after its leader exits | Both actually absent and actual macOS zombie leaders were observed while the child survived; retirement then removed the child and returned 0. | [Executable selection](selected-core.sh), [kernel checks and CLI trace](core.trace.log) |
| Owning home stops refreshing its lease | Target removed the real TERM-resistant child. The original 2-second-lease case passed its 16-second assertion deadline. A matched 15-second-lease comparison also passed; base and both mutations failed at the same 42-second deadline, leaving live group members. The 42 seconds is the test's doubled load allowance over its nominal 21-second bound, not a claimed shipped deadline. | [Statuses](guard-15s-status.log), [target](guard-15s-current.trace.log), [base](guard-15s-baseline.trace.log), [no escalation](guard-15s-no-escalation.trace.log), [delayed guard](guard-15s-slow-guard.trace.log) |
| Retire a recorded live mismatched identity | Refused before signalling; group alive, claim unchanged, registration retained. | [Real CLI](manual-cli-v4.log) |
| Retire a recorded real nonleader PID | Kernel pgid differed from recorded pid; refused, group alive, claim unchanged, registration retained. | [Real CLI](manual-cli-v4.log) |
| Leader killed independently of stop | `retire` and `sweep-home` refused; `reconcile` reported `started=0 uncertain=1`; guard left the group alone over ten check intervals. All retained the original claim and registration. | [Real CLI](manual-cli-v2.log) |

The supplemental executable regressions passed for identity unreadable before TERM (refusal), identity/PGID unreadable after TERM (completed escalation), and mismatch/nonleader evidence before TERM (refusal). These intentionally replace `ps` with failure-injection shims; they are **not live proof of a genuine host inspection failure**. See [post-TERM trace](probes.trace.log) and [initial unreadable trace](initial-unreadable.trace.log).

The guard mutation runs used the same extracted executable assertions with a 15-second lease and one-second check. Only the isolated copies were mutated: [escalation removal](mutation-no-escalation.diff), [delayed guard](mutation-slow-guard.diff). No tracked product code changed. The copied base replaced both changed runtime files with their exact base versions.

## Setup corrections and limits

The first healthy-baseline selection omitted its supplementary clock helper; it was corrected and rerun, confirming status 137. Additional 2/5-second lease startups failed before reaching the guard scenario on this heavily loaded host, so the matched mutation comparison used 15 seconds for every version. The original current 2-second core scenario had already passed.

Early supplemental manual attempts observed readiness too soon; stopping a runner at that point could freeze its startup lock. Final manual checks waited for `/bin/sleep 180` and used an ordinarily live leader without stopping it. A Python cleanup probe also encountered macOS EPERM as an already-killed group vanished; the final helper handles this with `ps`, and an independent final inspection confirmed no remaining test process or claim group. The raw iteration logs remain available as `manual-cli.log`, `manual-cli-v2.log`, and `manual-cli-v3.log`; the successful final first-signal checks are in `manual-cli-v4.log`.

No complete repository suite, linters, formatters, static analyzers, publication phase, or other gate was run. This is a CLI-only change, so visual UI artifacts do not apply. Header/help byte contracts and unchanged `.agents/skills/` were checked separately in [unchanged-contracts.txt](unchanged-contracts.txt). Scratch homes, source copies, and test data were removed after [process cleanup inspection](cleanup-inspection.txt); evidence stays here. No source or permanent test edits were needed.
