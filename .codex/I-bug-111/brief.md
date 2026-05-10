## §0 — HARD ITERATION CAP

```
HARD ITERATION CAP: 5. iter 1 of 5. Verdict APPROVE iff zero P0/P1.
```

## §1 — Issue + Acceptance

**GH#363 — I-bug-111: alert if synthesis [N] scrub count > 5 in single run.**

Issue body: "If synthesis hallucinates >5 [N] markers in a single run, log WARNING and tag manifest. Indicates synthesis prompt/bibliography degeneration. Acceptance: WARN log, manifest.synthesis_n_scrub_alert flag."

## §2 — Proposed change

| File | Δ |
|---|---|
| `src/polaris_graph/generator/analyst_synthesis.py` | +~40: `SYNTHESIS_SCRUB_ALERT_THRESHOLD = 5` constant; sticky `_SYNTHESIS_SCRUB_ALERT_FIRED` flag; `synthesis_scrub_alert_state()` reader; `reset_synthesis_scrub_alert()` resetter; `_scrub_invalid_n_markers` checks `if scrubbed > threshold` and trips flag + WARN log |
| `tests/polaris_graph/test_synthesis_alert.py` | NEW (+~95): 8 tests covering threshold value, no-alert at exactly threshold (strict >), alert at threshold+1, sticky-across-calls, reset clears, WARN log includes count+threshold, low-volume cumulative-but-not-per-call doesn't fire |

Net: +~135 lines. 45 tests pass (8 new + 8 telemetry + 29 analyst_synthesis).

## §3 — Threshold rationale

5 markers in a SINGLE call. Empirical: I-bug-108 incident scrubbed 6 in one call (mean over normal runs is 0; healthy run with one stray hallucination is 1-2). Strictly-greater (`> 5`, not `>=`) so exactly 5 does NOT fire — gives one buffer marker before alert.

## §4 — Sticky semantics

Flag is sticky across calls: once tripped within a process, stays True until `reset_synthesis_scrub_alert()`. Sweep orchestrators reset at start-of-run, read at end-of-run, surface as `manifest.synthesis_n_scrub_alert: bool`.

## §5 — Files clean

- `_scrub_invalid_n_markers` call site UNCHANGED — just adds the flag check inside the existing `if scrubbed > 0` block.
- Alert is independent of telemetry counters from I-bug-110; both can be observed independently.

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

Expected APPROVE iter 1.
