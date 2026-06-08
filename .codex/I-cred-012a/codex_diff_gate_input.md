HARD ITERATION CAP: 5 per document. This is iter 1 of 5. Front-load ALL real findings; reserve P0/P1 for real execution blockers; classify cosmetic as P2/P3. APPROVE iff zero P0 AND zero P1.

# DIFF GATE — credibility redesign build phase (umbrella I-ready-021 #1148)

Review the NEW-MODULE diff below for code correctness against its plan-phase spec
(`docs/credibility_weighted_sourcing_redesign_plan_2026_06_07.md`). This is faithfulness-adjacent code.

## HARD CONSTRAINTS (operator-locked)
- **Default-OFF byte-identical:** the module must be inert unless explicitly invoked by a flag/caller; turning it OFF (or not wiring it) leaves existing behavior byte-identical. No production path is changed in this phase.
- **Faithfulness gates UNTOUCHED:** strict_verify (`provenance_generator.py`), 4-role D8, two-family segregation, corpus_approval are NOT edited or weakened. This phase is a NEW module only.
- **LAW VI:** no hardcoded thresholds/paths — config/env; snake_case; no magic numbers; no live data in unit tests (fixtures only).

## VERIFY SPECIFICALLY
1. The module implements its plan-phase spec correctly (read the named layer/phase in the plan).
2. **The phase invariant is actually enforced AND tested** (e.g. P4: a copied row joining a cluster — even higher-authority — cannot change the cluster set / canonical origin; P5: recall-first contradictions + conservative-singleton never over-merges; P3: retraction hard-penalty + config thresholds).
3. The unit tests are MEANINGFUL (not assertion-relaxed to pass) and the attached SMOKE result is green.
4. No faithfulness gate is touched; nothing in the production path changes with the module un-wired.

## SMOKE EVIDENCE (attached below the diff — the offline pytest result is the evidence, not a self-report)

## OUTPUT SCHEMA (YAML)
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]

============ THE DIFF + SMOKE EVIDENCE ============
## PHASE: I-cred-012a (#1164) — runner/generator INTEGRATION diff (Codex APPROVE'd approach A). Generator-internal credibility pass over the EFFECTIVE evidence_pool (a {evidence_id: row} DICT -> pass list(evidence_pool.values())), inserted right after the M-52/M-44 effective-pool assembly, BEFORE Stage-2 section generation. ADDITIVE: 2 new keyword params default None (byte-identical unpassed); MultiSectionResult gains credibility_analysis (default None); set in the return. FAIL-CLOSED: master-on but judge/gov_suffixes not threaded -> abort_credibility_pass_error (defense-in-depth; orchestrator also fails loud). READ-ONLY: orchestrator copies rows, evidence_pool unchanged (no pool shrink/downgrade). Lazy gated import (no top-level side effect). 008b will thread credibility_analysis to the per-section P8 render. NB Codex iter-1 note: confirm no live PG_SWEEP_DISSENT_RECALL runner hook yet — 010b adds it; until then dissent rows just aren't appended (no harm). SMOKE: 225 passed (4 wiring + full synthesis+authority chain, no regression); py_compile OK; flag-off byte-identical structural.
```diff
diff --git a/src/polaris_graph/generator/multi_section_generator.py b/src/polaris_graph/generator/multi_section_generator.py
index 54b76452..eac5f6bd 100644
--- a/src/polaris_graph/generator/multi_section_generator.py
+++ b/src/polaris_graph/generator/multi_section_generator.py
@@ -292,6 +292,9 @@ class MultiSectionResult:
     limitations_text: str = ""
     limitations_input_tokens: int = 0
     limitations_output_tokens: int = 0
+    # I-cred-012a (#1164): CredibilityAnalysis from the activated pass (None when the master flag is off
+    # => byte-identical). 008b consumes it for per-claim disclosure rendering.
+    credibility_analysis: Any = None
     # I-ready-017 FX-07b leg-2 (#1111): per-(slot_id, entity_id) strict_verify
     # telemetry aggregated from every contract SectionResult.slot_strict_verify,
     # keyed (slot_id, entity_id) -> {sentences_kept, sentences_generated_content,
@@ -4386,6 +4389,10 @@ async def generate_multi_section_report(
     # mechanically matched to THIS question's corpus). Passed through to the UNVERIFIED analyst layer
     # only; None/[] => no change. Never reaches the verified generator/strict_verify path.
     prior_verified_context: list[dict[str, Any]] | None = None,
+    # I-cred-012a (#1164): credibility-analysis pass inputs. Both None/empty => the pass is NOT run =>
+    # byte-identical. Threaded by the sweep runner ONLY when PG_SWEEP_CREDIBILITY_REDESIGN is on.
+    credibility_pass_judge: Any = None,
+    credibility_pass_gov_suffixes: tuple[str, ...] | None = None,
     model: Optional[str] = None,
     outline_temperature: float = 0.2,
     section_temperature: float = 0.3,
@@ -4674,6 +4681,25 @@ async def generate_multi_section_report(
                     len(m44_primary_by_anchor),
                 )
 
+    # I-cred-012a (#1164): ADVISORY credibility-analysis pass over the EFFECTIVE evidence_pool (after the
+    # M-52/M-44 effective-pool assembly above; evidence_pool is the {evidence_id: row} the report cites).
+    # default-OFF master flag => credibility_analysis stays None => byte-identical. FAIL-LOUD: master-on
+    # but no production judge/gov_suffixes threaded => abort, never a priors-only false-green. READ-ONLY:
+    # the pass annotates row COPIES; evidence_pool is unchanged (no capability downgrade / pool shrink).
+    credibility_analysis = None
+    from ..synthesis import credibility_pass as _credibility_pass
+    if _credibility_pass.credibility_redesign_enabled():
+        if credibility_pass_judge is None or not credibility_pass_gov_suffixes:
+            raise _credibility_pass.CredibilityPassError(
+                "abort_credibility_pass_error: PG_SWEEP_CREDIBILITY_REDESIGN is on but the production "
+                "credibility judge / gov_suffixes were not threaded into generation (fail-closed)"
+            )
+        credibility_analysis = _credibility_pass.run_credibility_analysis(
+            research_question, list(evidence_pool.values()),
+            gov_suffixes=tuple(credibility_pass_gov_suffixes), domain=None,
+            judge=credibility_pass_judge,
+        )
+
     # Stage 2: per-section generation (bounded parallelism)
     sem = asyncio.Semaphore(max_parallel_sections)
 
@@ -5712,6 +5738,8 @@ async def generate_multi_section_report(
         limitations_text=lim_text,
         limitations_input_tokens=lim_in_tok,
         limitations_output_tokens=lim_out_tok,
+        # I-cred-012a (#1164): advisory credibility analysis (None when the master flag is off)
+        credibility_analysis=credibility_analysis,
         # I-bug-105 two-layer report
         analyst_synthesis_text=analyst_synth_text,
         analyst_synthesis_input_tokens=analyst_synth_in_tok,
diff --git a/tests/polaris_graph/generator/test_credibility_pass_wiring_012a.py b/tests/polaris_graph/generator/test_credibility_pass_wiring_012a.py
new file mode 100644
index 00000000..51bea3b1
--- /dev/null
+++ b/tests/polaris_graph/generator/test_credibility_pass_wiring_012a.py
@@ -0,0 +1,38 @@
+"""I-cred-012a (#1164) — runner/generator wiring of the credibility pass. Offline, no LLM.
+
+Verifies the activation hook is ADDITIVE + flag-gated: the new generate_multi_section_report params
+default None (byte-identical when unpassed), MultiSectionResult carries the analysis field defaulting
+None, and the master flag is OFF by default (so the pass block is skipped)."""
+from __future__ import annotations
+
+import dataclasses
+import inspect
+
+import src.polaris_graph.generator.multi_section_generator as m
+from src.polaris_graph.synthesis import credibility_pass as cp
+
+
+def test_generate_has_additive_credibility_params_default_none():
+    sig = inspect.signature(m.generate_multi_section_report)
+    assert sig.parameters["credibility_pass_judge"].default is None
+    assert sig.parameters["credibility_pass_gov_suffixes"].default is None
+
+
+def test_result_carries_credibility_analysis_field_default_none():
+    fields = {f.name: f for f in dataclasses.fields(m.MultiSectionResult)}
+    assert "credibility_analysis" in fields
+    # default None -> byte-identical when the pass did not run
+    assert fields["credibility_analysis"].default is None
+
+
+def test_master_flag_off_by_default(monkeypatch):
+    monkeypatch.delenv("PG_SWEEP_CREDIBILITY_REDESIGN", raising=False)
+    assert cp.credibility_redesign_enabled() is False
+
+
+def test_effective_pool_is_values_not_dict():
+    # the generator's evidence_pool is a {evidence_id: row} dict; the pass must receive the ROWS.
+    # guard the call shape so a future edit can't pass the dict (which the orchestrator would mis-handle).
+    src = inspect.getsource(m.generate_multi_section_report)
+    assert "list(evidence_pool.values())" in src
+    assert "run_credibility_analysis" in src and "fail-closed" in src.lower()
```
