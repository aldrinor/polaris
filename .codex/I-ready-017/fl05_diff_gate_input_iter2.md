# FL-05 (#1124) diff-gate — ITER 2 of 5

```
HARD ITERATION CAP: 5 per document. This is iter 2 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## Output schema (REQUIRED — reply with EXACTLY this YAML, nothing else)

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

## Scope
Fail-loud run-health backstop. Flag-gated `PG_RUN_HEALTH_GATE` (default OFF). Diff:
`.codex/I-ready-017/fl05_codex_diff.patch` (vs FX-18 verified tip `27697b3e`).

## Your iter-1 verdict (all 4 addressed)
- **P1 #1 (v6 schema):** `src/polaris_v6/schemas/run_status.py` `PipelineStatus` Literal omitted
  `abort_discovery_degraded` → RunStatusResponse 500 on a GET/list of an FL-05 abort.
- **P1 #2 (release_allowed):** override left `manifest.release_allowed` at the prior (often True)
  value → contradictory abort marked releasable.
- **P2 #1:** additive fields emitted even when gate OFF → "byte-identical default" claim untrue.
- **P2 #2:** `!= "0"` parse treated `false`/empty as ON for the default-OFF flag.

## What iter-2 changed
1. **P1 #1:** added `abort_discovery_degraded` to the v6 `PipelineStatus` Literal (the **5th**
   registration site, mirroring `abort_verifier_degraded`) + a `get_args(PipelineStatus)` membership
   test. Now UNIFIED_STATUS_VALUES + _SUMMARY_TO_UNIFIED + regression_lab + manifest-contract guard +
   v6 PipelineStatus all carry it.
2. **P1 #2:** the override now also sets `manifest['release_allowed'] = False` — status and the
   release flag can never contradict (mirrors the eval-gate invariant L5156-5158: a held status never
   reads as releasable).
3. **P2 #2:** robust truthy parse for the DEFAULT-OFF flag:
   `os.getenv("PG_RUN_HEALTH_GATE","0").strip().lower() in {"1","true","yes","on"}`.
4. **P2 #1:** kept always-emit (the FL-05 plan's observability intent — the 2 fields are additive,
   ignored by existing consumers, and the manifest-contract gate passes) and CORRECTED the claim: the
   default-OFF path leaves **status + control-flow + the release decision unchanged**; it is not
   "byte-identical" (it adds 2 observability fields). Comment, audit, and the test name all updated to
   say that precisely.

## Evidence
- **Offline smoke — `test_fl05_run_health_gate_iready017.py` → 8 passed** (added the v6
  `PipelineStatus` membership guard; renamed the default-OFF test to the accurate claim). Full gate
  decision matrix + the runner↔regression_lab mirror invariant retained.
- **Regression**: v6 `test_schemas` (5) + manifest_contract (13, taxonomy guard) — green.
- §-1.1: `outputs/audits/I-ready-017/fl05_s11_audit.md` (held storm attempted_empty; the 5-site
  registration + release_allowed + flag parse documented).

## Question
Are P1 #1 (v6 PipelineStatus + test) and P1 #2 (release_allowed=False on override) fully closed, the
flag parse robust, and the default-OFF behavior accurately described (status/control-flow/release
unchanged; 2 additive observability fields)? Anything blocking APPROVE?

## THE DIFF UNDER REVIEW (vs FX-18 verified tip 27697b3e)
```diff
diff --git a/scripts/run_honest_sweep_r3.py b/scripts/run_honest_sweep_r3.py
index c7a65123..5383ef03 100644
--- a/scripts/run_honest_sweep_r3.py
+++ b/scripts/run_honest_sweep_r3.py
@@ -197,6 +197,7 @@ UNIFIED_STATUS_VALUES: frozenset[str] = frozenset({
     "abort_evaluator_critical",      # BUG-M-205: PT08/PT11/PT12 integrity failure
     "abort_budget_exceeded",         # I-meta-008 (#1015): PG_MAX_COST_PER_RUN breached mid-run (generator OR 4-role verifier)
     "abort_verifier_degraded",       # I-ready-002 (#1071): judge_error_rate > PG_MAX_JUDGE_ERROR_RATE — binding verifier too degraded to trust
+    "abort_discovery_degraded",      # FL-05 (#1124): a FORCE-ENABLED discovery feature (STORM/agentic) was on but did NOT fire (firing_status attempted_empty/error) — silently degraded to baseline; refuse to ship as success (gated by PG_RUN_HEALTH_GATE)
     "abort_safety_refused",          # I-ready-007 (#1072): input harm-refusal — explicit harm-intent query refused BEFORE retrieval (PG_USE_SAFETY_REFUSAL); refuse-with-redirection, zero generator spend
     "abort_four_role_release_held",  # I-ready-016 (#1086): 4-role D8 held release (fabrication/coverage/S0/rewrite) — written via _SUMMARY_TO_UNIFIED["four_role_held"] at L4934/5065; was a real taxonomy gap
     "cancelled",                     # I-ready-016 (#1086): user-requested cancel terminal; _abort_if_cancelled writes manifest.status="cancelled" (consumed by v6 UI + SSE — value preserved, NOT renamed). Does NOT match the 4-prefix scheme — see the documented exception in test_manifest_contract_status_prefixes.
@@ -232,6 +233,8 @@ _SUMMARY_TO_UNIFIED: dict[str, str] = {
     "abort_budget_exceeded": "abort_budget_exceeded",
     # I-ready-002 (#1071): binding verifier degraded (judge_error_rate over cap) is a release-blocking abort.
     "abort_verifier_degraded": "abort_verifier_degraded",
+    # FL-05 (#1124): force-enabled discovery feature did not fire — run-health backstop abort.
+    "abort_discovery_degraded": "abort_discovery_degraded",
     # I-ready-007 (#1072): input harm-refusal — explicit harm-intent query refused before retrieval.
     "abort_safety_refused": "abort_safety_refused",
     "error": "error_unexpected",
@@ -271,6 +274,45 @@ def feature_firing_warning(telemetry: dict[str, Any]) -> str | None:
     return None
 
 
+# FL-05 (#1124): a force-enabled discovery feature with one of these firing states silently
+# degraded the run to the Serper/S2 baseline (block ran but produced nothing / errored).
+_FL05_DEGRADED_FIRING: frozenset[str] = frozenset({"attempted_empty", "error"})
+
+
+def compute_run_health_gate(
+    discovery_telemetries: list[dict[str, Any]],
+    *,
+    unified_status: str,
+    gate_on: bool,
+) -> dict[str, Any]:
+    """FL-05 (#1124): run-health backstop DECISION (pure, no I/O — testable). A FORCE-ENABLED
+    discovery feature (``enabled`` True) whose ``firing_status`` is in ``_FL05_DEGRADED_FIRING``
+    means the run silently fell back to the baseline. Returns the observability fields ALWAYS, plus
+    an ``override_status`` of ``abort_discovery_degraded`` IFF ``gate_on`` AND at least one degraded
+    force-enabled feature AND the run is otherwise success-bound. NEVER overrides a partial_/abort_/
+    error_ status (those are more specific) — only a would-be ``success``. This promotes
+    ``feature_firing_warning`` from advisory to gating (CANARY-01 is the pre-spend gate; FL-05 is the
+    mid/post-run regression backstop)."""
+    degraded = [
+        t for t in discovery_telemetries
+        if t.get("enabled") and t.get("firing_status") in _FL05_DEGRADED_FIRING
+    ]
+    override = (
+        "abort_discovery_degraded"
+        if (gate_on and degraded and unified_status == "success")
+        else None
+    )
+    return {
+        "discovery_llm_degraded": bool(degraded),
+        "discovery_rounds_on_fallback": len(degraded),
+        "degraded_features": [
+            {"feature": t.get("feature"), "firing_status": t.get("firing_status")}
+            for t in degraded
+        ],
+        "override_status": override,
+    }
+
+
 def _capped_finding_dedup_selection(
     *,
     base_rows: list[dict[str, Any]],
@@ -5758,6 +5800,42 @@ async def run_one_query(
         # write site and keeps the contract honest WITHOUT widening the gate's window (LAW II — not a
         # relaxation; `unified_status` is unchanged here).
         manifest["status"] = unified_status
+        # FL-05 (#1124): run-health backstop. A FORCE-ENABLED discovery feature (STORM / agentic)
+        # that was turned ON but did NOT fire (firing_status in {attempted_empty, error}) means the
+        # run silently degraded to the Serper/S2 baseline — it must NOT ship as success. ALWAYS emit
+        # the two additive degradation fields (observability — existing consumers ignore unknown
+        # keys); GATE the abort behind PG_RUN_HEALTH_GATE (default OFF: status + control-flow + the
+        # release decision are UNCHANGED — only the two additive observability fields are written; the
+        # benchmark slate forces it ON). Promotes run_log's advisory warning to a gating signal. Pairs
+        # with CANARY-01 (pre-spend) — FL-05 is the mid/post-run regression backstop. Only overrides a
+        # would-be SUCCESS (partial_* already signals degradation; aborts/errors are more specific).
+        # Codex iter-1 P2: robust truthy parse for this DEFAULT-OFF flag (so PG_RUN_HEALTH_GATE=false
+        # / empty does NOT accidentally enable it, unlike the bare `!= "0"` default-ON pattern).
+        _fl05 = compute_run_health_gate(
+            [_storm_telemetry, _agentic_telemetry],
+            unified_status=unified_status,
+            gate_on=os.getenv("PG_RUN_HEALTH_GATE", "0").strip().lower() in {"1", "true", "yes", "on"},
+        )
+        manifest["discovery_llm_degraded"] = _fl05["discovery_llm_degraded"]
+        manifest["discovery_rounds_on_fallback"] = _fl05["discovery_rounds_on_fallback"]
+        if _fl05["override_status"]:
+            _fl05_names = ", ".join(
+                f"{d['feature']}={d['firing_status']}" for d in _fl05["degraded_features"]
+            )
+            _log(
+                f"[run-health]  ABORT: force-enabled discovery feature(s) did not fire "
+                f"({_fl05_names}) — refusing to ship a silently-degraded run as success."
+            )
+            summary_status = _fl05["override_status"]
+            unified_status = to_unified_status(summary_status)
+            manifest["status"] = unified_status
+            # Codex iter-1 P1: a would-be-success carries release_allowed=True from the evaluator/D8
+            # gate. An abort_discovery_degraded manifest MUST also be non-releasable, or non-v6/UI/
+            # audit consumers keying on release_allowed would still treat the silently-degraded report
+            # as shippable. Keep status and release_allowed consistent (mirrors the eval-gate invariant
+            # at L5156-5158: a held status can never read as releasable).
+            manifest["release_allowed"] = False
+            manifest["discovery_degraded_features"] = _fl05["degraded_features"]
         # I-ready-006 (#1082): surface the complexity-routing decision on the SUCCESS manifest ONLY when
         # the router is ON (Codex brief P2-2 — byte-identical OFF: no field appears when
         # PG_COMPLEXITY_ROUTING is unset). Auditable: complexity, confidence, reasons, whether it was
diff --git a/src/polaris_graph/audit_ir/regression_lab.py b/src/polaris_graph/audit_ir/regression_lab.py
index f9cf0d44..91a0bac1 100644
--- a/src/polaris_graph/audit_ir/regression_lab.py
+++ b/src/polaris_graph/audit_ir/regression_lab.py
@@ -610,6 +610,9 @@ _STATUS_TIERS: dict[str, int] = {
     # I-ready-002 (#1071): binding verifier degraded (judge_error_rate over cap) — release-blocking
     # abort, no report. Added to UNIFIED_STATUS_VALUES by #1071 but never mirrored here until #1086.
     "abort_verifier_degraded": 2,
+    # FL-05 (#1124): force-enabled discovery feature (STORM/agentic) did not fire — run-health
+    # backstop abort, no trustworthy report (tier 2). MUST stay mirrored with runner.UNIFIED_STATUS_VALUES.
+    "abort_discovery_degraded": 2,
     # I-ready-007 (#1072): input harm-refusal — explicit harm-intent query refused before retrieval
     # (no report produced, tier 2). KNOWN_STATUS_VALUES MUST equal runner.UNIFIED_STATUS_VALUES.
     "abort_safety_refused": 2,
diff --git a/src/polaris_v6/schemas/run_status.py b/src/polaris_v6/schemas/run_status.py
index 5e6b6623..8b909163 100644
--- a/src/polaris_v6/schemas/run_status.py
+++ b/src/polaris_v6/schemas/run_status.py
@@ -43,6 +43,7 @@ PipelineStatus = Literal[
     "partial_saturation",            # I-meta-005 Phase 4 (#988)
     "abort_budget_exceeded",         # I-meta-008 (#1015)
     "abort_verifier_degraded",       # I-ready-002 (#1071)
+    "abort_discovery_degraded",      # FL-05 (#1124): force-enabled discovery feature did not fire (run-health backstop) — must mirror UNIFIED_STATUS_VALUES or the actor 500s RunStatusResponse on an FL-05 abort
     "abort_safety_refused",          # I-ready-007 (#1072): input harm-refusal before retrieval
     "abort_four_role_release_held",  # 4-role D8 held release
     "cancelled",                     # user-cancel terminal (_abort_if_cancelled writes manifest.status)
diff --git a/tests/polaris_graph/test_fl05_run_health_gate_iready017.py b/tests/polaris_graph/test_fl05_run_health_gate_iready017.py
new file mode 100644
index 00000000..621b81c9
--- /dev/null
+++ b/tests/polaris_graph/test_fl05_run_health_gate_iready017.py
@@ -0,0 +1,100 @@
+"""FL-05 (I-ready-017 #1124): run-health gate — force-enabled discovery feature not fired.
+
+A FORCE-ENABLED discovery feature (STORM / agentic) that was turned ON but did NOT fire
+(firing_status in {attempted_empty, error}) silently degrades the run to the Serper/S2 baseline; it
+must NOT ship as success. `compute_run_health_gate` is the pure decision (always emits the
+observability fields; overrides a would-be success → abort_discovery_degraded only when
+PG_RUN_HEALTH_GATE is on). Default OFF = byte-identical. Offline, no network.
+"""
+from __future__ import annotations
+
+from typing import get_args
+
+from scripts.run_honest_sweep_r3 import (
+    UNIFIED_STATUS_VALUES,
+    compute_run_health_gate,
+    to_unified_status,
+)
+from src.polaris_graph.audit_ir.regression_lab import KNOWN_STATUS_VALUES
+from src.polaris_v6.schemas.run_status import PipelineStatus
+
+
+def _feat(name, enabled, firing_status):
+    return {"feature": name, "enabled": enabled, "firing_status": firing_status, "fired": firing_status == "fired"}
+
+
+def test_abort_discovery_degraded_registered_and_prefix_compliant():
+    assert "abort_discovery_degraded" in UNIFIED_STATUS_VALUES
+    assert to_unified_status("abort_discovery_degraded") == "abort_discovery_degraded"
+    assert "abort_discovery_degraded".startswith("abort_")  # manifest-contract prefix scheme
+
+
+def test_regression_lab_known_statuses_mirror_runner():
+    # The documented invariant: regression_lab KNOWN_STATUS_VALUES MUST equal runner.UNIFIED_STATUS_VALUES.
+    assert KNOWN_STATUS_VALUES == UNIFIED_STATUS_VALUES
+    assert "abort_discovery_degraded" in KNOWN_STATUS_VALUES
+
+
+def test_abort_discovery_degraded_in_v6_pipeline_status():
+    # Codex iter-1 P1: the v6 actor stores manifest.status into pipeline_status for abort_* runs and
+    # RunStatusResponse validates against the PipelineStatus Literal — omitting the new status would
+    # 500 any GET/list query of an FL-05 abort. Pin it in the schema mirror.
+    assert "abort_discovery_degraded" in get_args(PipelineStatus)
+
+
+def test_force_enabled_not_fired_overrides_success_when_gated():
+    for bad in ("attempted_empty", "error"):
+        out = compute_run_health_gate(
+            [_feat("storm", True, bad), _feat("agentic_search", True, "fired")],
+            unified_status="success",
+            gate_on=True,
+        )
+        assert out["override_status"] == "abort_discovery_degraded", bad
+        assert out["discovery_llm_degraded"] is True
+        assert out["discovery_rounds_on_fallback"] == 1
+        assert out["degraded_features"] == [{"feature": "storm", "firing_status": bad}]
+
+
+def test_healthy_run_not_overridden():
+    out = compute_run_health_gate(
+        [_feat("storm", True, "fired"), _feat("agentic_search", True, "fired")],
+        unified_status="success",
+        gate_on=True,
+    )
+    assert out["override_status"] is None
+    assert out["discovery_llm_degraded"] is False
+    assert out["discovery_rounds_on_fallback"] == 0
+
+
+def test_gate_off_no_abort_but_degradation_observed():
+    # default (gate_on=False): status + control flow + the release decision are UNCHANGED (no
+    # override), but the degradation is still OBSERVED in the additive observability fields.
+    out = compute_run_health_gate(
+        [_feat("storm", True, "attempted_empty")],
+        unified_status="success",
+        gate_on=False,
+    )
+    assert out["override_status"] is None        # no new abort on the default path
+    assert out["discovery_llm_degraded"] is True  # but still surfaced for the operator
+
+
+def test_non_success_status_never_overridden():
+    # Only a would-be success is overridden; a partial_/abort_ is more specific and is left alone.
+    out = compute_run_health_gate(
+        [_feat("agentic_search", True, "error")],
+        unified_status="partial_thin_corpus",
+        gate_on=True,
+    )
+    assert out["override_status"] is None
+    assert out["discovery_llm_degraded"] is True
+
+
+def test_disabled_feature_is_not_degraded():
+    # A feature that was NOT force-enabled (enabled=False) is never a degradation, even if empty.
+    out = compute_run_health_gate(
+        [_feat("storm", False, "not_enabled"), _feat("agentic_search", False, "attempted_empty")],
+        unified_status="success",
+        gate_on=True,
+    )
+    assert out["override_status"] is None
+    assert out["discovery_llm_degraded"] is False
diff --git a/tests/polaris_graph/test_manifest_contract.py b/tests/polaris_graph/test_manifest_contract.py
index a80a8b49..7f8f6733 100644
--- a/tests/polaris_graph/test_manifest_contract.py
+++ b/tests/polaris_graph/test_manifest_contract.py
@@ -51,6 +51,7 @@ def test_manifest_contract_unified_taxonomy_defined() -> None:
         "abort_evaluator_critical",    # added by BUG-M-205 (R5)
         "abort_budget_exceeded",       # I-meta-008 (#1015): PG_MAX_COST_PER_RUN breach (generator OR 4-role verifier)
         "abort_verifier_degraded",     # I-ready-002 (#1071): binding verifier judge_error_rate over cap
+        "abort_discovery_degraded",    # FL-05 (#1124): force-enabled discovery feature did not fire (run-health backstop)
         "abort_safety_refused",        # I-ready-007 (#1072): input harm-refusal before retrieval
         "abort_four_role_release_held",  # I-ready-016 (#1086): 4-role D8 held release
         "cancelled",                   # I-ready-016 (#1086): user-cancel terminal manifest status
```
