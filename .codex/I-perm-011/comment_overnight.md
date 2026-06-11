## Overnight autonomous loop armed (operator asleep 2026-06-11, authorized)

Ledger: `state/overnight_starvation_loop.json`. ScheduleWakeup-driven loop (10-min cadence), state machine:

1. **Fix-iterate drb_76** until the generator loads a LARGE citation pool (checkpoint evidence_selected
   >= ~150 vs the starved 53; real gate = a substantively complete, NON-vacuous report) AND it releases
   AND stays §-1.1 faithful (Claude + Codex dual audit, zero fabrication). Each iteration: diagnose the
   binding throttle from the run's drop_reasons -> fix (flag-safe, Codex-gated) -> deploy to VM -> re-run
   drb_76 -> §-1.1 audit -> judge. If a lever doesn't move evidence in 2 tries, switch levers. Hard cap 6
   iterations, then HALT with a clear residual-diagnosis report (no infinite spend).
2. When drb_76 is fat + faithful -> **run the other 4 questions in PARALLEL** on the VM ($100/run cap).
3. Audit all 5 §-1.1 + beat-both vs gpt_5_5_pro / gemini_3_1_pro -> write the morning summary -> STOP.

Guardrails: faithfulness gates NEVER relaxed; §-1.1 audit every run (not green-status trust); Codex gate
every fix; PID-scoped cleanup only. Operator wakes to either DONE (5 questions fat+faithful+scored) or
HALTED (clear report of what was tried + the residual blocker) in the ledger's morning_summary.

In flight at arm-time: fix workflow wl0so23c1 (rerank cull 2689->740 + evidence collapse 524->58 + telemetry bug).
