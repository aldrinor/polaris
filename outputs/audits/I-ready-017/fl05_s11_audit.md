# FL-05 §-1.1 audit — run-health gate: force-enabled discovery feature not fired (#1124)

**Standard:** §-1.1 on the REAL held drb_72 `run_artifacts/manifest.json` feature-telemetry vs the
run status (run-time OUTPUT; the gating effect on a success run needs a fresh success run, so the
fix is proven by offline smoke + verified at RERUN).

## The bug condition, on the real artifact (line-by-line)
Held drb_72 manifest feature telemetry:
- `agentic_search`: enabled=True, firing_status=**fired** ✓.
- `storm_query_expansion`: enabled=True, firing_status=**attempted_empty**, fired=**False** ←
  STORM was FORCE-ENABLED but did NOT fire (the block ran, produced nothing → silent fallback to
  the Serper/S2 baseline).
- manifest had **NO `discovery_llm_degraded` field** and **NO run-health gate** — the degradation
  was advisory-only (a `run_log` warning via `feature_firing_warning`).

That run's status was `abort_four_role_release_held` (it aborted for an unrelated 4-role reason), so
FL-05 would not have changed THIS outcome. But it PROVES the bug condition is real: a force-enabled
discovery feature at `attempted_empty` with no degradation field and no gate. Had the 4-role gate
passed, the run would have shipped as **success** with STORM silently dead — exactly the
no-silent-downgrade violation FL-05 closes.

## The fix (fail-loud backstop; flag-gated; default byte-identical)
- New pure `compute_run_health_gate(discovery_telemetries, *, unified_status, gate_on)`: ALWAYS
  returns `discovery_llm_degraded: bool` + `discovery_rounds_on_fallback: int`; returns
  `override_status='abort_discovery_degraded'` IFF `gate_on` AND ≥1 force-enabled feature with
  firing_status in {attempted_empty, error} AND the run is success-bound.
- The success manifest tail emits the two fields ALWAYS (observability) and, behind
  `PG_RUN_HEALTH_GATE` (default OFF = byte-identical; benchmark slate forces ON), overrides a
  would-be success to `abort_discovery_degraded` BEFORE recording success. Promotes
  `feature_firing_warning` from advisory to gating. Pairs with CANARY-01 (pre-spend); FL-05 is the
  mid/post-run regression backstop.
- `abort_discovery_degraded` registered as a valid terminal status (mirroring
  `abort_verifier_degraded`): runner `UNIFIED_STATUS_VALUES`, `_SUMMARY_TO_UNIFIED` map,
  `regression_lab` severity (tier 2), and the manifest-contract taxonomy guard. Prefix-compliant
  (`abort_`).

## Offline smoke (proves the fix)
`pytest tests/polaris_graph/test_fl05_run_health_gate_iready017.py` → 7 passed:
- registration: `abort_discovery_degraded` ∈ `UNIFIED_STATUS_VALUES`, to_unified_status round-trips,
  `abort_` prefix; `regression_lab.KNOWN_STATUS_VALUES == UNIFIED_STATUS_VALUES` (the mirror invariant).
- gate decision matrix: force-enabled + {attempted_empty, error} + gate-on + success → override
  abort_discovery_degraded (degraded=True, rounds=1); healthy (fired) → no override; **gate-off →
  no override (byte-identical) but degraded field still emitted**; non-success → never overridden;
  disabled feature → not degraded.
- Regression: manifest_contract (13, incl. the taxonomy-drift guard updated) + m207 invariant
  coverage (11) + the broad status-registry/regression_lab suites — all green.

## Faithfulness check
Fail-loud, no-silent-downgrade backstop. Default OFF = byte-identical (no new abort on opt-in runs);
the benchmark slate turns it ON so a force-on discovery feature that didn't fire aborts rather than
shipping as success. Fail-CLOSED (refuses to record success on degradation) per LAW II. No grounding
/ strict_verify / 4-role-decision change — it only converts a degraded would-be-success into an
explicit `abort_discovery_degraded`.
