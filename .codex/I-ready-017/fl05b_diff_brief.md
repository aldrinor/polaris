HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

---

# Codex diff-gate — I-ready-017 FL-05b (#1137): activate PG_RUN_HEALTH_GATE in the Gate-B slate

## Output schema (REQUIRED — reply with exactly this YAML, last `verdict:` line authoritative)
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

## What this change is
A pure **flag-activation** change. The FL-05 run-health backstop CODE (#1124, already merged + Codex-APPROVE'd iter-2, commit 4b3ad982, on this branch) was flag-gated behind `PG_RUN_HEALTH_GATE` defaulting **OFF**, and was NOT wired into the Gate-B full-capability slate. So a paid beat-both run would run with the backstop OFF.

This change wires `PG_RUN_HEALTH_GATE` into the three slate structures in `scripts/dr_benchmark/run_gate_b.py` so the benchmark forces it ON and fails closed if it is off. **No logic in `compute_run_health_gate` or any faithfulness path is touched.**

## What FL-05 does (the gate being activated — for your context, NOT under review here; #1124 already APPROVE'd)
`scripts/run_honest_sweep_r3.py::compute_run_health_gate(discovery_telemetries, *, unified_status, gate_on)`:
- A discovery feature counts as **degraded** iff `enabled is True` AND `firing_status in {"attempted_empty","error"}` (force-enabled STORM/agentic that did not fire → run silently fell back to the Serper/S2 baseline).
- Returns `override_status="abort_discovery_degraded"` **iff** `gate_on AND degraded AND unified_status=="success"`. It ONLY overrides a would-be `success`; an `abort_*`/`partial_*`/`error_*` status is left untouched (those are more specific).
- The abort site (`run_honest_sweep_r3.py:6292-6316`) also sets `release_allowed=False` and always emits the two additive observability fields regardless of `gate_on`.

## The diff (`.codex/I-ready-017/fl05b_codex_diff.patch`)
In `scripts/dr_benchmark/run_gate_b.py`, `PG_RUN_HEALTH_GATE` is added to:
1. `_FULL_CAPABILITY_BENCHMARK_SLATE` = `"1"`,
2. `_BENCHMARK_FORCE_ON_FLAGS` (so an explicit operator `PG_RUN_HEALTH_GATE=0` cannot survive `apply_full_capability_benchmark_slate`, which force-sets any slate key in this set — lines 663-666),
3. `_BENCHMARK_PREFLIGHT_REQUIRED_FLAGS` (so `preflight_full_capability` raises before any spend if it is off — lines 694-699).
Plus a new offline test file `tests/dr_benchmark/test_slate_run_health_gate_fl05b_iready017.py` (8 tests).

## Acceptance criteria to VERIFY
- [ ] `PG_RUN_HEALTH_GATE` present in all three structures; the force-on parse value (`"1"`) matches the gate-on truthy set in `run_honest_sweep_r3.py:6295` (`{"1","true","yes","on"}`) AND the preflight required-flag truthy set (`("1","true","True")`, lines 694-695).
- [ ] OFF-by-default behavior of `run_honest_sweep_r3.py` for NON-Gate-B callers is byte-unchanged (the slate is the only thing turning it on; nothing in the sweep changed).
- [ ] No faithfulness path touched (strict_verify / provenance / 4-role seam / two-family). This change cannot weaken a gate — FL-05 only PROMOTES an advisory firing-warning to a gating abort of a would-be `success`.
- [ ] The §-1.1 behavioral tests actually exercise the real `compute_run_health_gate` decision (not a mock): gate-on aborts a would-be-success degraded run; gate-off ships it (the pre-fix silent downgrade); an already-held status is untouched; a clean run is not falsely aborted.

## Files I have ALSO checked and they're clean
- `scripts/run_honest_sweep_r3.py`: `PG_RUN_HEALTH_GATE` read sites are ONLY the gate-on parse (6295) + comments (203, 6285, 6290); `abort_discovery_degraded` is registered in `UNIFIED_STATUS_VALUES` (203) and `_SUMMARY_TO_UNIFIED` (243). No other consumer.
- `src/`: `PG_RUN_HEALTH_GATE` has ZERO references in `src/` (it is a benchmark/sweep-only flag; no web/UI consumer).
- `apply_full_capability_benchmark_slate` (663-666): force-on iterates the slate and force-sets keys in `_BENCHMARK_FORCE_ON_FLAGS` — so the new flag IS force-set (it is both in the slate and the set). Non-force keys take the numeric FLOOR path; `PG_RUN_HEALTH_GATE` is correctly a force-on flag, NOT a numeric floor (it would crash `float("1")`? no — `"1"` floats fine, but it is semantically a flag, so force-on is correct and avoids the int() coercion path).
- `preflight_full_capability` (694-699): the required-flag loop checks `os.getenv(flag,"0").strip() in ("1","true","True")`; the slate force-sets `"1"`, so it passes; an operator `=0` is overridden by force-on BEFORE preflight runs.
- Existing tests: `tests/polaris_graph/test_fl05_run_health_gate_iready017.py` (8, #1124 gate) + `tests/dr_benchmark/test_slate_readiness_flags_iready016b.py` (4) re-run GREEN with this change. Full `tests/dr_benchmark/` = 299 passed (1 pre-existing unrelated collection error in `test_benchmark_upload_wiring_iready010.py`, which imports `polaris_graph` instead of `src.polaris_graph` — NOT in this diff).

## Specific risks to adjudicate
1. **Coupling to chromium (Q5)**: with FL-05 active, a would-be-success run where STORM/agentic did not fire (e.g. chromium missing on the VM) aborts `abort_discovery_degraded`. Is that the correct no-silent-downgrade behavior, or an over-abort? (Operator intent: NO silent degradation may ship as success — so the abort is desired; chromium-on-VM is a separate operator-gated precondition.)
2. **Force-on vs numeric-floor classification**: confirm `PG_RUN_HEALTH_GATE` belongs in `_BENCHMARK_FORCE_ON_FLAGS` (a flag), not the numeric-floor path. If it rode the floor path, `int(max(float("1"), float("1")))` = 1 would still yield "1" — but force-on is the correct, explicit semantics and prevents an operator "0" from winning.
3. **Any path where the slate is applied but the sweep reads the flag BEFORE the slate runs** (import-time capture). `PG_RUN_HEALTH_GATE` is read at call-time inside the manifest-write block (6295), NOT at import — so slate-before-sweep ordering is sufficient. Confirm.
