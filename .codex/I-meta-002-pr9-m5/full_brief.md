HARD ITERATION CAP: 5 per document. This is iter 1 of the M5 DIFF gate.
- Front-load ALL real findings; reserve P0/P1 for real execution/safety risks.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

## Output schema (emit this exact YAML block as your final output)
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
```

# Codex DIFF-gate — I-meta-002 PR-9/M5: evaluator_agrees per-claim manifest map

You APPROVED the M5 design (.codex/I-meta-002-pr9-m5/codex_design_verdict.txt): benchmark/sweep-path
manifest map only; writeback in run_one_query right after run_four_role_evaluation; safe rule
evaluator_agrees = (kept) AND final_verdict=="VERIFIED"; never True on non-VERIFIED or dropped; do NOT
synthesize a VerifiedSentence on the sweep path. This diff implements that ruling. NO SPEND / NO NETWORK.

## HARD CONSTRAINTS
- §-1.1 clinical safety: a non-VERIFIED verdict (PARTIAL/UNSUPPORTED/FABRICATED/UNREACHABLE/unknown/
  missing) must NEVER yield evaluator_agrees=True. Never True on a not-kept claim. Fail-safe default False.
- Frozen, no drift: claim_audit_scorer.py, runtime lock (NOT promoted), clinical_generator/strict_verify.py,
  verified_report.py (all OUT OF SCOPE per your ruling). M1/M2/M3/M4 committed code unchanged.
- D8 stays the single binding gate: M5 must NOT change release_allowed/status; evaluator_agrees is
  audit/inspector fidelity metadata only, strictly ADDITIVE to manifest['four_role_evaluation'].

## What to verify in the diff
1. `build_evaluator_agrees_map(final_verdicts, kept_claim_ids=None)` in sweep_integration.py delegates
   the verdict test to the EXISTING `evaluator_agrees_from_verdict` (== "VERIFIED"; single source of
   truth, not re-inlined); value = is_kept AND VERIFIED; is_kept = (kept_claim_ids is None or claim_id
   in kept_claim_ids); empty final_verdicts -> {}; keys are EXACTLY final_verdicts.keys() (kept_claim_ids
   only affects the boolean, never adds/removes keys — joinable to four_role_claim_audit.json).
2. run_one_query adds manifest['four_role_evaluation']['evaluator_agrees'] = build_evaluator_agrees_map(
   four_role_result.final_verdicts) — strictly ADDITIVE (existing keys release_allowed/held_reasons/
   coverage_fraction/final_verdicts/gaps/kg_path untouched); release_allowed/status logic unchanged.
   kept_claim_ids passed as None (sweep builds FourRoleClaim only from kept/is_verified sentences) —
   confirm this None-default cannot mark a NON-kept claim True (on this path all claims are kept; the
   safe rule still holds since value also requires VERIFIED).
3. Tests cover: True only for VERIFIED; False for PARTIAL/UNSUPPORTED/FABRICATED/UNREACHABLE/unknown/
   missing; empty -> {}; not-kept VERIFIED -> False; None treats all as kept; extra kept id not in
   final_verdicts adds no key.
4. No network/spend; no clinical_generator/frozen drift.

## SMOKE (build agent, this session)
- import scripts.run_honest_sweep_r3 — OK
- pytest tests/roles tests/dr_benchmark tests/architecture -q — 394 passed (test_sweep_integration 11->16).
- verify_lock --consistency — exit 0 (lock NOT promoted). gate_a_dry_run — OVERALL PASS, exit 0.
- tests/polaris_graph not re-run here (M5 touches only run_one_query manifest assembly + sweep_integration
  helper + its test; the 49 tests/polaris_graph failures are PRE-EXISTING per the M3b stash-comparison).

## DIFF (follows)

diff --git a/scripts/run_honest_sweep_r3.py b/scripts/run_honest_sweep_r3.py
index 2b93505f..5c025c26 100644
--- a/scripts/run_honest_sweep_r3.py
+++ b/scripts/run_honest_sweep_r3.py
@@ -3168,6 +3168,7 @@ async def run_one_query(
             # audit map next to the run. The builder closure is called HERE — AFTER generation —
             # so it sees the finished `multi` report; the sweep still synthesizes nothing itself.
             from src.polaris_graph.roles.sweep_integration import (  # noqa: E402
+                build_evaluator_agrees_map,
                 run_four_role_seam,
             )
             four_role_result = run_four_role_seam(
@@ -3222,6 +3223,16 @@ async def run_one_query(
                 ],
                 "kg_path": str(four_role_result.kg_path),
             }
+            # I-meta-002 PR-9/M5: ADDITIVE per-claim evaluator_agrees MAP for audit/inspector
+            # fidelity (NOT a release gate — D8 above stays the single binding gate). Joinable to
+            # four_role_claim_audit.json by claim_id. kept_claim_ids is None here: on the sweep
+            # path the FourRoleClaim set is built from KEPT (is_verified) sentences only, so every
+            # claim_id in final_verdicts is already a kept claim (invariant documented in the
+            # helper). The §-1.1 fail-safe rule (VERIFIED+kept -> True; every other verdict ->
+            # False) lives in build_evaluator_agrees_map -> evaluator_agrees_from_verdict.
+            manifest["four_role_evaluation"]["evaluator_agrees"] = (
+                build_evaluator_agrees_map(four_role_result.final_verdicts)
+            )
             _log(
                 f"[four_role]   release_allowed={four_role_result.release_allowed} "
                 f"coverage={four_role_result.coverage_fraction:.3f} "
diff --git a/src/polaris_graph/roles/sweep_integration.py b/src/polaris_graph/roles/sweep_integration.py
index b8cb249c..165082bc 100644
--- a/src/polaris_graph/roles/sweep_integration.py
+++ b/src/polaris_graph/roles/sweep_integration.py
@@ -32,8 +32,10 @@ Fail-closed contract (Codex P2 directives, binding):
 
 from __future__ import annotations
 
+import json
 from dataclasses import dataclass, field
 from pathlib import Path
+from typing import Callable
 
 from src.polaris_graph.roles.release_policy import (
     CoverageLedger,
@@ -129,6 +131,41 @@ def evaluator_agrees_from_verdict(final_verdict: str) -> bool:
     return final_verdict == _VERDICT_VERIFIED
 
 
+def build_evaluator_agrees_map(
+    final_verdicts: dict[str, str],
+    kept_claim_ids: set[str] | None = None,
+) -> dict[str, bool]:
+    """Build the per-claim `evaluator_agrees` MAP for the sweep manifest (I-meta-002 PR-9/M5).
+
+    Maps each `claim_id` in `final_verdicts` to the §-1.1 fail-safe boolean:
+
+        evaluator_agrees = (claim is kept) AND evaluator_agrees_from_verdict(final_verdict)
+
+    where `evaluator_agrees_from_verdict` is the SINGLE source of the verdict rule
+    (`final_verdict == "VERIFIED"`). Every other verdict — PARTIAL / UNSUPPORTED / FABRICATED /
+    UNREACHABLE / any unknown string — maps to False. The value is NEVER True before a VERIFIED
+    final verdict exists AND the claim is kept (a non-VERIFIED verdict must never read as
+    "evaluator agreed" in clinical context).
+
+    `kept_claim_ids` is the set of claim_ids that survived as kept/verified sentences
+    (`verifier_pass=True`). When it is None, ALL claim_ids in `final_verdicts` are treated as
+    kept — INVARIANT: on the sweep path the `FourRoleClaim` set is built (by the M3a builder)
+    from KEPT (is_verified) sentences only, so every claim_id in `final_verdicts` is already a
+    kept claim and passing None is correct there. When a set IS supplied, a claim_id absent from
+    it maps to False even if its verdict is VERIFIED (defensive: a not-kept claim can never agree).
+
+    Keys are EXACTLY `final_verdicts.keys()` (so the map is joinable to
+    `four_role_claim_audit.json` from M3b); `kept_claim_ids` affects only the boolean value and
+    never adds or removes keys. An empty `final_verdicts` yields `{}` (no error here; the sweep
+    branch's own fail-closed guards already handle empty claim sets upstream).
+    """
+    agrees_map: dict[str, bool] = {}
+    for claim_id, final_verdict in final_verdicts.items():
+        is_kept = kept_claim_ids is None or claim_id in kept_claim_ids
+        agrees_map[claim_id] = is_kept and evaluator_agrees_from_verdict(final_verdict)
+    return agrees_map
+
+
 def run_four_role_evaluation(
     transport: RoleTransport,
     *,
@@ -283,3 +320,99 @@ def run_four_role_evaluation(
         needs_rewrite=decision.needs_rewrite,
         kg_path=kg_path,
     )
+
+
+# --- M3b seam: the single thin core both the sweep branch and the offline test call --------
+# The builder is a KEYWORD-ARGUMENT closure that the SEAM calls AFTER generation with the
+# run-local objects (`multi`, `template`, `slug`, `domain`, `ev_pool`); it PRODUCES a bundle
+# with `.inputs` (FourRoleEvaluationInputs) and `.audit_map` (dict[str, dict]). It is wired in
+# scripts/dr_benchmark/run_gate_b.py over native_gate_b_inputs.build_native_gate_b_inputs +
+# the evidence normalization. The builder takes run-local objects (NOT captured at construction)
+# because `multi`/`ev_pool` only exist INSIDE run_one_query, after generation — the seam supplies
+# them. Kept as a structural `Callable` so this module never imports the builder (LAW VII CLI
+# isolation; the builder lives in roles/, the closure in scripts/).
+FourRoleBundleBuilder = Callable[..., object]
+
+# Filename of the per-claim audit map persisted next to the run (Codex M3 P2 #2). The SEAM
+# writes it; the builder does NO file I/O.
+FOUR_ROLE_CLAIM_AUDIT_FILENAME = "four_role_claim_audit.json"
+
+
+def run_four_role_seam(
+    transport: RoleTransport,
+    *,
+    run_dir: Path,
+    timestamp: str,
+    four_role_input_builder: FourRoleBundleBuilder | None = None,
+    four_role_inputs: FourRoleEvaluationInputs | None = None,
+    multi: object = None,
+    template: object = None,
+    slug: str | None = None,
+    domain: str | None = None,
+    ev_pool: object = None,
+) -> FourRoleEvaluationResult:
+    """Resolve the 4-role inputs (builder WINS), run the SINGLE binding D8 gate, persist audit.
+
+    This is the seam core extracted so BOTH the guarded `run_one_query` branch and the offline
+    seam test exercise the SAME code (no copy-paste of the override logic). Precedence (Codex
+    M3 P2 #1): if `four_role_input_builder` is provided it WINS — the SEAM calls it AFTER
+    generation with the run-local objects (`multi`, `template`, `slug`, `domain`, `ev_pool`) so
+    it PRODUCES the inputs+audit bundle from the finished report, and the SEAM writes
+    `bundle.audit_map` to `run_dir / FOUR_ROLE_CLAIM_AUDIT_FILENAME` (json, sorted keys) so every
+    claim_id is traceable alongside the run. Otherwise a directly-supplied static
+    `four_role_inputs` is used as-is (unit/static path; it carries no audit_map, so nothing is
+    written). If BOTH are None the branch fails closed (the sweep never synthesizes inputs).
+
+    The run-local objects are passed through (NOT captured by the closure at construction)
+    because `multi`/`ev_pool` only exist inside `run_one_query` after generation; the builder
+    cannot have closed over them when the caller constructed it. Duck-typed `object` here so this
+    seam never imports the generator's `MultiSectionResult` (LAW VII CLI isolation).
+
+    Pure orchestration over the INJECTED `transport` (no network, no spend) plus one JSON write.
+    """
+    if four_role_input_builder is not None:
+        # BUILDER WINS: produce the inputs+audit bundle from the finished report + native
+        # contract (supplied the run-local objects HERE), then run the gate over bundle.inputs.
+        bundle = four_role_input_builder(
+            multi=multi,
+            template=template,
+            slug=slug,
+            domain=domain,
+            ev_pool=ev_pool,
+        )
+        inputs = bundle.inputs
+        result = run_four_role_evaluation(
+            transport,
+            claims=inputs.claims,
+            run_dir=run_dir,
+            timestamp=timestamp,
+            coverage_ledger=inputs.coverage_ledger,
+            required_s0_categories=inputs.required_s0_categories,
+            model_slugs=inputs.model_slugs,
+            rewrite_already_attempted=inputs.rewrite_already_attempted,
+        )
+        # The SEAM (not the builder) persists the per-claim audit map alongside the run.
+        (run_dir / FOUR_ROLE_CLAIM_AUDIT_FILENAME).write_text(
+            json.dumps(bundle.audit_map, indent=2, sort_keys=True) + "\n",
+            encoding="utf-8",
+        )
+        return result
+
+    if four_role_inputs is None:
+        raise ValueError(
+            "run_four_role_seam: PG_FOUR_ROLE_MODE is on and a transport was injected, but "
+            "neither a four_role_input_builder nor static four_role_inputs was supplied; the "
+            "sweep does not synthesize them (fail-closed)."
+        )
+
+    # Static path (no builder): use the caller-supplied inputs as-is (no audit_map to persist).
+    return run_four_role_evaluation(
+        transport,
+        claims=four_role_inputs.claims,
+        run_dir=run_dir,
+        timestamp=timestamp,
+        coverage_ledger=four_role_inputs.coverage_ledger,
+        required_s0_categories=four_role_inputs.required_s0_categories,
+        model_slugs=four_role_inputs.model_slugs,
+        rewrite_already_attempted=four_role_inputs.rewrite_already_attempted,
+    )
diff --git a/tests/roles/test_sweep_integration.py b/tests/roles/test_sweep_integration.py
index 48b97fb4..35fbdc76 100644
--- a/tests/roles/test_sweep_integration.py
+++ b/tests/roles/test_sweep_integration.py
@@ -24,6 +24,7 @@ from src.polaris_graph.roles.role_transport import (
 )
 from src.polaris_graph.roles.sweep_integration import (
     FourRoleClaim,
+    build_evaluator_agrees_map,
     evaluator_agrees_from_verdict,
     run_four_role_evaluation,
 )
@@ -230,3 +231,65 @@ def test_coverage_credit_only_on_verified(tmp_path) -> None:
     # Only elem-1 credited; elem-2 uncovered -> fraction 0.5 < 0.70 -> held.
     assert result.coverage_fraction == pytest.approx(0.5)
     assert result.release_allowed is False
+
+
+# --- I-meta-002 PR-9/M5: build_evaluator_agrees_map §-1.1 safe-rule ---------------------------
+# evaluator_agrees = (claim kept) AND (final_verdict == "VERIFIED"); every other verdict -> False;
+# empty -> {}; a not-kept claim_id -> False even if VERIFIED. Audit metadata only (no release gate).
+
+
+def test_evaluator_agrees_map_true_only_for_verified() -> None:
+    """Across the full verdict alphabet, ONLY the VERIFIED claim maps to True; every other
+    verdict — PARTIAL / UNSUPPORTED / FABRICATED / UNREACHABLE and an unknown string — is False."""
+    final_verdicts = {
+        "c-verified": "VERIFIED",
+        "c-partial": "PARTIAL",
+        "c-unsupported": "UNSUPPORTED",
+        "c-fabricated": "FABRICATED",
+        "c-unreachable": "UNREACHABLE",
+        "c-unknown": "SOMETHING_ELSE",
+    }
+    agrees = build_evaluator_agrees_map(final_verdicts)
+    assert agrees == {
+        "c-verified": True,
+        "c-partial": False,
+        "c-unsupported": False,
+        "c-fabricated": False,
+        "c-unreachable": False,
+        "c-unknown": False,
+    }
+    # Keys are EXACTLY final_verdicts keys (joinable to four_role_claim_audit.json).
+    assert set(agrees) == set(final_verdicts)
+
+
+def test_evaluator_agrees_map_empty_is_empty_dict() -> None:
+    """An empty final_verdicts yields {} (no error; upstream guards handle empty claim sets)."""
+    assert build_evaluator_agrees_map({}) == {}
+
+
+def test_evaluator_agrees_map_not_kept_is_false_even_if_verified() -> None:
+    """The defensive kept-gate: a VERIFIED claim_id ABSENT from kept_claim_ids maps to False, and
+    a kept VERIFIED claim maps to True. This proves the kept-set actually gates the boolean — a
+    helper that ignored kept_claim_ids would still pass the verdict-mapping test above."""
+    final_verdicts = {"kept-ok": "VERIFIED", "dropped-but-verified": "VERIFIED"}
+    agrees = build_evaluator_agrees_map(final_verdicts, kept_claim_ids={"kept-ok"})
+    assert agrees == {"kept-ok": True, "dropped-but-verified": False}
+
+
+def test_evaluator_agrees_map_none_kept_set_treats_all_as_kept() -> None:
+    """kept_claim_ids=None treats ALL claim_ids as kept (the sweep-path invariant: final_verdicts
+    is built from KEPT/is_verified sentences only). It must NOT collapse to an empty set."""
+    final_verdicts = {"a": "VERIFIED", "b": "UNSUPPORTED"}
+    assert build_evaluator_agrees_map(final_verdicts, kept_claim_ids=None) == {
+        "a": True,
+        "b": False,
+    }
+
+
+def test_evaluator_agrees_map_extra_kept_id_does_not_add_key() -> None:
+    """A claim_id present in kept_claim_ids but ABSENT from final_verdicts must NOT appear in the
+    map; kept_claim_ids only affects the boolean value, never the key set (joinability invariant)."""
+    agrees = build_evaluator_agrees_map(
+        {"only-claim": "VERIFIED"}, kept_claim_ids={"only-claim", "ghost-id"}
+    )
+    assert agrees == {"only-claim": True}
