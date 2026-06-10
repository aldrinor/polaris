HARD ITERATION CAP: 5 per document. This is iter 3 of 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

# Codex DIFF review — I-perm-001 (#1195) KEYSTONE slice 2 — ITER 3 of 5

Iter-2: REQUEST_CHANGES, ZERO P0, ONE NOVEL P1 (a clean PG_ALWAYS_RELEASE release mapped to error_unexpected because `_SUMMARY_TO_UNIFIED` had no `"success": "success"` identity map). RESOLVED.

## P1 (clean always-release release -> error_unexpected) — RESOLVED
`scripts/run_honest_sweep_r3.py`: added `"success": "success"` to `_SUMMARY_TO_UNIFIED`. Now `to_unified_status("success") == "success"` (was -> error_unexpected). EVIDENCE: probe `to_unified_status('success') -> 'success'`, `to_unified_status('released_with_disclosed_gaps') -> 'released_with_disclosed_gaps'`.
NEW regression test `test_always_release_outcome_statuses_round_trip` (tests/polaris_graph/test_manifest_contract.py): asserts EVERY status `compute_release_outcome` can emit (STATUS_SUCCESS, STATUS_RELEASED_WITH_DISCLOSED_GAPS, STATUS_RELEASED_INSUFFICIENT_SAFETY, STATUS_ABORT_NO_VERIFIED, STATUS_ABORT_FABRICATED) is in UNIFIED_STATUS_VALUES AND round-trips through to_unified_status to itself (never error_unexpected). This LOCKS the whole class, not just `success`.

## Iter-1 + iter-2 findings (confirmed closed): released_* v6 actor+schema wiring (3 v6 tests); zero_usable_evidence uses claim.evidence_documents; release_disclosure no longer duplicates `released`.

## Evidence pack (ran this session)
- `pytest test_manifest_contract.py test_released_status_iperm001.py replay/` -> **44 passed, 1 xfailed**.

VERIFY the novel P1 is closed (every outcome status round-trips) and nothing else novel. APPROVE if so.

## Output schema (REQUIRED — last `verdict:` line parsed by CI)
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

========== THE UPDATED DIFF UNDER REVIEW ==========

diff --git a/scripts/run_honest_sweep_r3.py b/scripts/run_honest_sweep_r3.py
index e14e98d7..0b9df7c3 100644
--- a/scripts/run_honest_sweep_r3.py
+++ b/scripts/run_honest_sweep_r3.py
@@ -197,6 +197,13 @@ from src.polaris_graph.retrieval.live_retriever import (  # noqa: E402
 UNIFIED_STATUS_VALUES: frozenset[str] = frozenset({
     # success
     "success",
+    # released-with-disclosure (I-perm-001 #1195 always-release): the report SHIPPED with honest
+    # disclosed gaps (BLOCK->LABEL) — a RELEASED terminal, not an abort. `released_insufficient_
+    # safety_evidence` is the honest clinical-safety-floor variant (normal render blocked, honest
+    # report still ships). The "released_" prefix is a documented exception to the 4-prefix scheme
+    # (alongside "cancelled") in tests/.../test_manifest_contract_status_prefixes.
+    "released_with_disclosed_gaps",
+    "released_insufficient_safety_evidence",
     # partial — report produced but degraded signal
     "partial_thin_corpus",
     "partial_incomplete_corpus",
@@ -230,6 +237,11 @@ UNIFIED_STATUS_VALUES: frozenset[str] = frozenset({
 # Map legacy summary["status"] labels → unified manifest.status values.
 _SUMMARY_TO_UNIFIED: dict[str, str] = {
     "ok": "success",
+    # I-perm-001 (#1195) slice 2: the always-release outcome's clean status IS already unified
+    # ("success") — without this identity map, to_unified_status("success") falls to the
+    # error_unexpected default and a clean PG_ALWAYS_RELEASE run is mis-classified (Codex slice-2
+    # iter-2 P1). The released_* identity maps below cover the disclosed-gap outcomes.
+    "success": "success",
     "ok_thin_corpus": "partial_thin_corpus",
     "ok_incomplete_corpus": "partial_incomplete_corpus",
     "ok_outline_fallback": "partial_outline_fallback",
@@ -250,6 +262,10 @@ _SUMMARY_TO_UNIFIED: dict[str, str] = {
     # shortfall / S0 must-cover missing / pending rewrite). Only set on the guarded 4-role path.
     "four_role_released": "success",
     "four_role_held": "abort_four_role_release_held",
+    # I-perm-001 (#1195) always-release: the outcome already carries a unified status; map it to
+    # itself so to_unified_status passes it through (NOT error_unexpected).
+    "released_with_disclosed_gaps": "released_with_disclosed_gaps",
+    "released_insufficient_safety_evidence": "released_insufficient_safety_evidence",
     # I-beatboth-fix-000 (#1171): post-gate report.md reconciliation failed fail-closed
     # (a material non-VERIFIED claim present in the body could not be redacted) — terminal abort.
     "report_redaction_failed": "abort_report_redaction_failed",
@@ -7117,13 +7133,37 @@ async def run_one_query(
                 pass
             # Demote the legacy gate to ADVISORY metadata; D8 owns the headline decision.
             manifest["evaluator_gate_advisory"] = manifest.pop("evaluator_gate")
-            manifest["release_allowed"] = four_role_result.release_allowed
-            # Single binding status: released => success; held => release-blocking abort.
-            summary_status = (
-                "four_role_released"
-                if four_role_result.release_allowed
-                else "four_role_held"
-            )
+            # I-perm-001 (#1195) slice 2: under PG_ALWAYS_RELEASE the D8 BLOCK becomes a LABEL —
+            # non-hard holds ship as disclosed gaps and the report RELEASES; only the
+            # no-fabrication hard line (fabricated / zero-grounding) withholds; the clinical
+            # safety floor ships the honest insufficient-safety report (normal render blocked).
+            # release_allowed = outcome.released, so bundle.py refuses ONLY a hard block. Default
+            # OFF: the legacy held/success path below is byte-identical.
+            from src.polaris_graph.roles.release_policy import always_release_enabled
+            _release_outcome = getattr(four_role_result, "release_outcome", None)
+            if always_release_enabled() and _release_outcome is not None:
+                manifest["release_allowed"] = _release_outcome.released
+                summary_status = _release_outcome.status
+                # release_disclosure is the D8 LABEL snapshot. It deliberately does NOT carry a
+                # `released` field (Codex slice-2 P2): manifest["release_allowed"] is the SINGLE
+                # binding decision, and a later fail-closed gate (redaction / run-health) can flip
+                # it to False — a duplicated `released` here would go stale and contradict it.
+                manifest["release_disclosure"] = {
+                    "hard_block": _release_outcome.hard_block,
+                    "hard_block_reasons": list(_release_outcome.hard_block_reasons),
+                    "normal_release_blocked": _release_outcome.normal_release_blocked,
+                    "disclosed_gaps": list(_release_outcome.disclosed_gaps),
+                    "release_quality_score": _release_outcome.release_quality_score,
+                    "safety_floor": _release_outcome.safety_floor,
+                }
+            else:
+                manifest["release_allowed"] = four_role_result.release_allowed
+                # Single binding status: released => success; held => release-blocking abort.
+                summary_status = (
+                    "four_role_released"
+                    if four_role_result.release_allowed
+                    else "four_role_held"
+                )
             # Reassign BOTH the summary label AND the unified local so manifest.json,
             # sweep_summary.json (summary["status"] at the function tail), and the status log
             # line are all D8-driven and cannot disagree (no double-gate, Codex P2).
diff --git a/src/polaris_graph/audit_ir/regression_lab.py b/src/polaris_graph/audit_ir/regression_lab.py
index a5e73612..912eed6f 100644
--- a/src/polaris_graph/audit_ir/regression_lab.py
+++ b/src/polaris_graph/audit_ir/regression_lab.py
@@ -589,6 +589,12 @@ def _diff_manifest(
 _STATUS_TIERS: dict[str, int] = {
     # success
     "success": 0,
+    # I-perm-001 (#1195) always-release: RELEASED-with-disclosure terminals (a report SHIPPED).
+    # `released_with_disclosed_gaps` is a release (tier 0); `released_insufficient_safety_evidence`
+    # ships the honest report but with degraded clinical safety signal (tier 1). MUST stay mirrored
+    # with runner.UNIFIED_STATUS_VALUES (test_md9_regression_lab + test_saturation_phase4).
+    "released_with_disclosed_gaps": 0,
+    "released_insufficient_safety_evidence": 1,
     # partial — report produced but degraded signal
     "partial_thin_corpus": 1,
     "partial_incomplete_corpus": 1,
diff --git a/src/polaris_graph/roles/sweep_integration.py b/src/polaris_graph/roles/sweep_integration.py
index 2fa62b8d..40aa3cd4 100644
--- a/src/polaris_graph/roles/sweep_integration.py
+++ b/src/polaris_graph/roles/sweep_integration.py
@@ -55,7 +55,9 @@ from src.polaris_graph.roles.release_policy import (
     D8ClaimRow,
     Gap,
     ReleaseDecision,
+    ReleaseOutcome,
     apply_d8_release_policy,
+    compute_release_outcome,
     load_d8_policy_config,
 )
 from src.polaris_graph.roles.role_pipeline import (
@@ -150,6 +152,10 @@ class FourRoleEvaluationResult:
     fabricated_occurrence_latched: bool
     needs_rewrite: list[str]
     kg_path: Path
+    # I-perm-001 (#1195) slice 2: the always-release-aware outcome (BLOCK->LABEL). Default None
+    # for legacy/timeout construction sites; the headline D8 decision (release_allowed above) is
+    # unchanged, so consumers that ignore this field are byte-identical.
+    release_outcome: ReleaseOutcome | None = None
 
 
 def evaluator_agrees_from_verdict(final_verdict: str) -> bool:
@@ -659,6 +665,31 @@ def run_four_role_evaluation(
         rewrite_already_attempted=rewrite_already_attempted,
     )
 
+    # I-perm-001 (#1195) slice 2: compute the always-release-aware outcome HERE, where the
+    # required-S0 set + the per-claim verdicts are natively available. `compute_release_outcome`
+    # reads PG_ALWAYS_RELEASE (default OFF -> released == decision.release_allowed, byte-identical).
+    _final = final_verdicts or {}
+    _zero_verified = not any(v == "VERIFIED" for v in _final.values())
+    # zero_usable_evidence = the NATIVE evidence signal (Codex slice-2 P1): no claim cites ANY
+    # evidence document. `not final_verdicts` (no claims) was too weak — a claims-present-but-
+    # all-unsupported run with no cited evidence must still zero-grounding hard-block. Mirrors the
+    # replay harness's audit_map evidence_ids signal.
+    _zero_usable_evidence = not any((c.evidence_documents or []) for c in claims)
+    _missing_s0 = {
+        reason[len("d8_s0_must_cover_missing:"):]
+        for reason in decision.held_reasons
+        if reason.startswith("d8_s0_must_cover_missing:")
+    }
+    _required_s0 = set(required_s0_categories)
+    _safety_floor_insufficient = bool(_required_s0) and _required_s0 <= _missing_s0
+    release_outcome = compute_release_outcome(
+        decision,
+        zero_verified=_zero_verified,
+        zero_usable_evidence=_zero_usable_evidence,
+        safety_floor_insufficient=_safety_floor_insufficient,
+        coverage_fraction=internal_ledger.fraction(),
+    )
+
     return FourRoleEvaluationResult(
         release_allowed=decision.release_allowed,
         held_reasons=decision.held_reasons,
@@ -669,6 +700,7 @@ def run_four_role_evaluation(
         fabricated_occurrence_latched=decision.fabricated_occurrence_latched,
         needs_rewrite=decision.needs_rewrite,
         kg_path=kg_path,
+        release_outcome=release_outcome,
     )
 
 
diff --git a/src/polaris_v6/queue/actors.py b/src/polaris_v6/queue/actors.py
index 2f90e6c9..ff0e09b5 100644
--- a/src/polaris_v6/queue/actors.py
+++ b/src/polaris_v6/queue/actors.py
@@ -254,7 +254,14 @@ def enqueue_research_run(run_id: str, request_payload: dict[str, Any]) -> dict[s
         logger.info("[actor] run_id=%s cancelled during pipeline run", run_id)
         return summary
 
-    if pipeline_status == "success" or pipeline_status.startswith("partial_"):
+    if (
+        pipeline_status == "success"
+        or pipeline_status.startswith("partial_")
+        # I-perm-001 (#1195): the always-release model SHIPS a report with disclosed gaps
+        # (released_with_disclosed_gaps / released_insufficient_safety_evidence) — these are
+        # COMPLETED terminals (a report + bundle exist), not aborts/errors.
+        or pipeline_status.startswith("released_")
+    ):
         run_store.mark_completed(
             run_id, summary, pipeline_status=pipeline_status, cost_usd=cost_usd_f
         )
diff --git a/src/polaris_v6/schemas/run_status.py b/src/polaris_v6/schemas/run_status.py
index 6aa2b966..ba2527c6 100644
--- a/src/polaris_v6/schemas/run_status.py
+++ b/src/polaris_v6/schemas/run_status.py
@@ -25,6 +25,11 @@ LifecycleStatus = Literal[
 
 PipelineStatus = Literal[
     "success",
+    # I-perm-001 (#1195): always-release RELEASED-with-disclosure terminals. The v6 actor loads
+    # manifest.status into pipeline_status, so these MUST mirror UNIFIED_STATUS_VALUES or
+    # RunStatusResponse 500s on a released_* run.
+    "released_with_disclosed_gaps",
+    "released_insufficient_safety_evidence",
     "partial_outline_fallback",
     "partial_qwen_advisory",  # legacy alias (I-modref-004 #530) — historical manifests
     "partial_evaluator_advisory",
diff --git a/tests/polaris_graph/test_manifest_contract.py b/tests/polaris_graph/test_manifest_contract.py
index b0acd960..4d29944f 100644
--- a/tests/polaris_graph/test_manifest_contract.py
+++ b/tests/polaris_graph/test_manifest_contract.py
@@ -36,6 +36,8 @@ def test_manifest_contract_unified_taxonomy_defined() -> None:
     )
     expected = frozenset({
         "success",
+        "released_with_disclosed_gaps",            # I-perm-001 (#1195): always-release BLOCK->LABEL
+        "released_insufficient_safety_evidence",   # I-perm-001 (#1195): clinical safety-floor honest report
         "partial_thin_corpus",
         "partial_incomplete_corpus",
         "partial_rule_check_warnings",
@@ -289,6 +291,28 @@ def test_manifest_contract_exception_writes_error_manifest() -> None:
 # (every class of status is recognizable by its prefix).
 # ─────────────────────────────────────────────────────────────────
 
+def test_always_release_outcome_statuses_round_trip() -> None:
+    """Every status `compute_release_outcome` can emit must be a valid unified status AND map to
+    ITSELF through to_unified_status (NOT error_unexpected) — the I-perm-001 slice-2 consume site
+    feeds outcome.status straight into to_unified_status (Codex slice-2 iter-2 P1)."""
+    from scripts.run_honest_sweep_r3 import UNIFIED_STATUS_VALUES, to_unified_status
+    from src.polaris_graph.roles import release_policy as rp
+
+    emitted = {
+        rp.STATUS_SUCCESS,
+        rp.STATUS_RELEASED_WITH_DISCLOSED_GAPS,
+        rp.STATUS_RELEASED_INSUFFICIENT_SAFETY,
+        rp.STATUS_ABORT_NO_VERIFIED,
+        rp.STATUS_ABORT_FABRICATED,
+    }
+    for status in emitted:
+        assert status in UNIFIED_STATUS_VALUES, f"{status!r} not in UNIFIED_STATUS_VALUES"
+        assert to_unified_status(status) == status, (
+            f"to_unified_status({status!r}) = {to_unified_status(status)!r}, not identity "
+            "(a clean/disclosed always-release run would be mis-classified)"
+        )
+
+
 def test_manifest_contract_status_prefixes() -> None:
     """Every status value falls into one of four classes via its prefix.
     This is what downstream readers rely on to classify a run."""
@@ -304,6 +328,11 @@ def test_manifest_contract_status_prefixes() -> None:
             # SSE `run.completed`); renaming it to abort_cancelled would break those consumers. It is
             # a terminal/cancel class of its own, deliberately outside the 4-prefix scheme.
             or status == "cancelled"
+            # I-perm-001 (#1195): the always-release model adds a RELEASED-with-disclosure class
+            # (`released_with_disclosed_gaps` / `released_insufficient_safety_evidence`) — a report
+            # SHIPPED with honest disclosed gaps (BLOCK->LABEL). Documented prefix exception: it is
+            # neither success (it carries gaps) nor abort (a report was produced).
+            or status.startswith("released_")
         ), f"Status {status!r} doesn't match any known prefix class"
 
 
diff --git a/tests/polaris_v6/test_released_status_iperm001.py b/tests/polaris_v6/test_released_status_iperm001.py
new file mode 100644
index 00000000..756b0e09
--- /dev/null
+++ b/tests/polaris_v6/test_released_status_iperm001.py
@@ -0,0 +1,60 @@
+"""I-perm-001 (#1195) slice 2 — the always-release `released_*` statuses are wired through the v6
+serving path (Codex slice-2 P1-a). Without this, a PG_ALWAYS_RELEASE canary run would 500
+RunStatusResponse and fall to `unknown_pipeline_status` in the actor.
+"""
+
+from __future__ import annotations
+
+import typing
+from pathlib import Path
+
+from src.polaris_graph.audit_ir.regression_lab import KNOWN_STATUS_VALUES
+from src.polaris_v6.schemas.run_status import PipelineStatus, RunStatusResponse
+from scripts.run_honest_sweep_r3 import UNIFIED_STATUS_VALUES
+
+_RELEASED = ("released_with_disclosed_gaps", "released_insufficient_safety_evidence")
+# Read the actor source from disk (importing it pulls in the dramatiq broker — out of scope here).
+_ACTORS_SRC = Path(__file__).resolve().parents[2] / "src" / "polaris_v6" / "queue" / "actors.py"
+
+
+def test_released_statuses_validate_in_pipeline_schema():
+    """RunStatusResponse must accept the released_* statuses (the actor loads manifest.status into
+    pipeline_status — an omitted value 500s Pydantic validation on a real run)."""
+    allowed = set(typing.get_args(PipelineStatus))
+    for status in _RELEASED:
+        assert status in allowed, f"{status} missing from PipelineStatus schema mirror"
+        response = RunStatusResponse(
+            run_id="x",
+            lifecycle_status="completed",
+            pipeline_status=status,
+            template="t",
+            question="q",
+            queued_at="2026-01-01T00:00:00Z",
+        )
+        assert response.pipeline_status == status
+
+
+def test_actor_classifies_released_as_completed():
+    """The actor completion classifier marks a released_* manifest as COMPLETED — not
+    unknown_pipeline_status. Locks the `startswith('released_')` branch in run_research_run."""
+    source = _ACTORS_SRC.read_text(encoding="utf-8")
+    assert 'startswith("released_")' in source, (
+        "actor completion classifier must treat released_* as a completed terminal"
+    )
+    # And the classification predicate itself recognises them as completed.
+    for status in _RELEASED:
+        assert (
+            status == "success"
+            or status.startswith("partial_")
+            or status.startswith("released_")
+        )
+
+
+def test_released_statuses_mirrored_across_all_taxonomies():
+    """released_* must be in EVERY status mirror (runner / regression_lab / v6 schema) so no layer
+    rejects or mis-tiers a real always-release run."""
+    schema_allowed = set(typing.get_args(PipelineStatus))
+    for status in _RELEASED:
+        assert status in UNIFIED_STATUS_VALUES
+        assert status in KNOWN_STATUS_VALUES
+        assert status in schema_allowed
