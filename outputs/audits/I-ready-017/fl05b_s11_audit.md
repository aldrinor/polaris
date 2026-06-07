# §-1.1 line-by-line audit — I-ready-017 FL-05b (#1137)

**Subject:** activation of `PG_RUN_HEALTH_GATE` in the Gate-B full-capability slate
(`scripts/dr_benchmark/run_gate_b.py`). The FL-05 gate CODE (#1124) is unchanged; this audit
verifies that the *activation* produces the intended backfire-guard behavior on the REAL gate
function, claim-by-claim, against `scripts/run_honest_sweep_r3.py::compute_run_health_gate` and the
manifest-write abort site — NOT a metadata/string-presence check.

Branch: `bot/I-ready-017-faithfulness` @ 9b9ed188. Commit under audit: FL-05b activation.

---

## Claim 1 — "Activating the gate aborts a would-be-success run whose force-enabled discovery feature did not fire"

- **Cited code** (`run_honest_sweep_r3.py:310-314`):
  `override = "abort_discovery_degraded" if (gate_on and degraded and unified_status == "success") else None`
  where `degraded = [t for t in telemetries if t.get("enabled") and t.get("firing_status") in {"attempted_empty","error"}]` (306-309).
- **Behavioral evidence** (`test_activated_gate_aborts_would_be_success_degraded_run`): inputs = STORM
  `{enabled:True, firing_status:"attempted_empty"}` + agentic `{enabled:True, firing_status:"fired"}`,
  `unified_status="success"`, `gate_on=True` → `override_status == "abort_discovery_degraded"`,
  `discovery_llm_degraded is True`, `discovery_rounds_on_fallback == 1`. **PASS** (real function, no mock).
- **Verdict: VERIFIED.** The activation buys exactly the backfire-guard: the 2026-06-05 drb_72 smoke
  shape (STORM `attempted_empty`) no longer ships green when it would otherwise be a success.

## Claim 2 — "Before activation (gate OFF) the SAME degraded run ships as success (the silent downgrade FL-05b closes)"

- **Cited code:** same line 310-314; with `gate_on=False` the `override` is `None` regardless of degradation.
- **Behavioral evidence** (`test_gate_off_ships_degraded_run_as_success`): same degraded inputs,
  `gate_on=False` → `override_status is None`, but `discovery_llm_degraded is True` (observability still
  surfaced). **PASS.**
- **Verdict: VERIFIED.** Confirms the pre-FL-05b default was a real silent downgrade — the gate code
  existed but, OFF, did not bite. This is the gap the slate activation closes.

## Claim 3 — "Activation never overrides an already-held/abort status (no status clobber / double-abort)"

- **Cited code** (`run_honest_sweep_r3.py:302-303` docstring + `unified_status == "success"` guard on 312):
  the override only fires when the run is otherwise success-bound.
- **Behavioral evidence** (`test_activated_gate_never_overrides_an_already_held_status`): degraded inputs,
  `unified_status="abort_four_role_release_held"`, `gate_on=True` → `override_status is None`. **PASS.**
- **Verdict: VERIFIED.** The prior smoke ended `abort_four_role_release_held` (D8 gate held at 28.6%
  coverage); FL-05b activation would NOT have changed that outcome, and will not clobber any future
  abort/partial/error status. No interaction with the faithfulness D8 gate.

## Claim 4 — "Activation does not falsely abort a clean run"

- **Cited code:** `degraded` is empty when every enabled feature has `firing_status` not in the degraded set.
- **Behavioral evidence** (`test_activated_gate_passes_a_clean_run`): STORM + agentic both
  `{enabled:True, firing_status:"fired"}`, `gate_on=True` → `override_status is None`,
  `discovery_llm_degraded is False`. **PASS.**
- **Verdict: VERIFIED.** When STORM/agentic actually fire (the desired full-capability run, e.g. chromium
  present on the VM), the gate is inert — no false abort.

## Claim 5 — "The slate forces the flag ON over an explicit operator =0, and the preflight fails closed if it is off"

- **Cited code** (`run_gate_b.py:663-666`): `apply_full_capability_benchmark_slate` force-sets any slate
  key in `_BENCHMARK_FORCE_ON_FLAGS`; `PG_RUN_HEALTH_GATE` is in both. Preflight (`694-699`) requires every
  flag in `_BENCHMARK_PREFLIGHT_REQUIRED_FLAGS` (now incl. `PG_RUN_HEALTH_GATE`) to be truthy, else `RuntimeError`.
- **Behavioral evidence:** `test_slate_force_ons_run_health_gate_over_preset_zero` (preset "0" → "1" after
  slate); `test_run_gate_b_query_force_ons_run_health_gate` (force-on through the real query path, run_one_query
  faked, no spend); `test_preflight_fails_closed_when_run_health_gate_off` (RuntimeError names the flag). **PASS.**
- **Truthy-set consistency:** slate sets `"1"`; gate-on parse (`run_honest_sweep_r3.py:6295`) accepts
  `{"1","true","yes","on"}`; preflight required-flag parse accepts `("1","true","True")`. `"1"` satisfies both.
- **Verdict: VERIFIED.** A conservative `.env`/operator `PG_RUN_HEALTH_GATE=0` cannot silently re-disable the
  backstop on a paid run (the I-cap-005 P1-1 force-on pattern, applied consistently).

## Claim 6 — "No faithfulness path is touched; OFF-by-default behavior is byte-unchanged for non-Gate-B callers"

- **Scope check:** the diff is 18 inserted lines in `run_gate_b.py` (3 slate-structure additions + comments)
  + a new test file. `compute_run_health_gate`, the abort site (6292-6316), strict_verify, provenance,
  the 4-role seam, and two-family segregation are all unchanged.
- **Cross-ref:** `PG_RUN_HEALTH_GATE` has zero references in `src/`; it is a benchmark/sweep-only flag, read
  at call-time inside the manifest-write block (6295), not at import — so slate-before-sweep ordering suffices.
- **Verdict: VERIFIED.** This change can only STRENGTHEN (promote an advisory warning to a gating abort of a
  would-be success); it cannot weaken any gate.

---

## Summary

| Claim | Verdict |
|---|---|
| 1 — gate-on aborts degraded would-be-success | VERIFIED |
| 2 — gate-off ships it (the silent downgrade closed) | VERIFIED |
| 3 — never clobbers an already-held status | VERIFIED |
| 4 — no false abort on a clean run | VERIFIED |
| 5 — slate force-on over =0 + fail-closed preflight | VERIFIED |
| 6 — no faithfulness path touched / OFF byte-unchanged | VERIFIED |

**Conclusion:** FL-05b activation is behaviorally proven on the REAL `compute_run_health_gate` decision
(not a mock, not a string-presence check). It closes the exact silent-downgrade class the 2026-06-05
drb_72 smoke exposed (STORM `attempted_empty` would have shipped green on a success-bound run) while
leaving every faithfulness gate and every non-success status untouched.

**Operational coupling surfaced (not a defect):** with FL-05b active, a would-be-success run where
STORM/agentic do NOT fire (e.g. chromium missing on the VM) correctly aborts `abort_discovery_degraded`
+ `release_allowed=False`. Therefore chromium-on-VM (operator Q5) is a HARD precondition for a *successful*
full-capability run — without it the run is honestly aborted rather than shipping a silently-degraded report.
