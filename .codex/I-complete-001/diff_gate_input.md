HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

Output schema (end your review with these fields; the LAST `verdict:` line is parsed by CI):

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

---

# I-complete-001 (#1182) — combined DIFF gate: 3 completeness fixes

You are reviewing a single combined diff that implements three independent completeness fixes (D-1, D-5, D-2) found in the I-ready-017 / beat-both forensic audit. The umbrella goal of I-complete-001 is to close COMPLETENESS gaps (POLARIS dropping/under-counting content vs Gemini/ChatGPT) WITHOUT fabricating any content and WITHOUT weakening any faithfulness gate.

VERIFY EACH FIX INDEPENDENTLY against the diff below. Do not assume; read the code. Reserve P0/P1 for real execution/faithfulness risks.

## Hard constraints (faithfulness — non-negotiable; flag P0 if any is violated)
- No fix may weaken `strict_verify`, the 4-role verifier, the redactor, or the FX-01 reasoning->content promotion guard (which REFUSES to ship a model's reasoning scratchpad as content).
- No fix may fabricate quantified or narrative content.
- No magic numbers (LAW VI): every threshold/budget must be a named, env-overridable constant or named module constant.
- Metadata-honesty fixes (D-5) must change ONLY counts/disclosure, never generated prose.

## Fix-by-fix summary (what to verify)

### D-1 — content max_tokens raised via a named env-overridable constant
Files: `src/polaris_graph/generator/multi_section_generator.py`, `src/polaris_graph/generator/analyst_synthesis.py`.
- The prior hardcoded content ceilings (`4000` in analyst-synthesis, `2400`/`4000` in multi-section, `6000` contract-slot floor) are replaced with named module constants `PG_SECTION_MAX_TOKENS` (default 24000) and `PG_CONTRACT_SLOT_MIN_MAX_TOKENS` (default 6000), both `os.getenv`-overridable.
- Rationale: the default writer (deepseek/deepseek-v4-pro) is REASONING-FIRST; it burns 6k-42k reasoning tokens before content, so a small content ceiling caused finish_reason=length truncation, after which the FX-01 guard correctly REFUSED the scratchpad and DROPPED whole sections (a completeness loss).
- VERIFY: (a) the truncation GUARD itself is UNTOUCHED (the diff only widens the requested budget, it does NOT disable the refusal-to-ship-scratchpad guard); (b) no magic number remains for content budget; (c) faithfulness untouched.

IMPORTANT NUANCE TO ADJUDICATE (do not let me pre-judge this; you decide if it is a blocker):
`openrouter_client` clamps every reasoning-first request: it FLOORS UP requests below `PG_REASONING_FIRST_MIN_MAX_TOKENS` (default 16384) and CLAMPS DOWN requests above `PG_REASONING_FIRST_HARD_CAP` (default 16384). The relevant code is pasted at the bottom under "EVIDENCE: openrouter clamp". Consequence on the DEFAULT provider: a reasoning-first content call receives 16384 whether the kwarg is the old 4000 or the new 24000 — i.e. for the reasoning-first content sites, D-1 may be a NO-OP on the deployed default config, taking effect only once an operator points the writer at a higher-tier endpoint AND raises `PG_REASONING_FIRST_HARD_CAP`. The diff comments openly concede this ("forward-compat HEADROOM, not active room"). The OPEN QUESTIONS for you:
  1. Is D-1 effectively a no-op on the default provider at the reasoning-first content sites (analyst-synthesis call, per-section call, section signature default)? Trace whether each of those calls enables reasoning and hits the clamp branch. NOTE the old hardcoded 4000 was ALSO below the 16384 floor, so it too was floored up to 16384 — meaning the *effective* budget on the default provider may be UNCHANGED by D-1 at those sites.
  2. Does the contract-slot site `max(section_max_tokens, PG_CONTRACT_SLOT_MIN_MAX_TOKENS)` behave any differently (e.g. non-reasoning or JSON path) such that D-1 DOES change effective budget there?
  3. Given the above, does "forward-compat headroom only" satisfy the COMPLETENESS intent of I-complete-001 D-1, or is the real fix elsewhere (e.g. the operator must also raise PG_REASONING_FIRST_HARD_CAP, or the writer must be pointed at a higher endpoint)? Decide whether shipping D-1 as-is (named constant + headroom + honest comments) is acceptable, or whether it is a P1 "claims to fix truncation but is inert on the deployed config." It is your call, not mine.

### D-5 — sections_kept count excludes 0-verified gap stubs (metadata honesty)
Files: `scripts/run_honest_sweep_r3.py` (3 sites: strict_verify.section_completed `global` flag, Methods parallel-section count, manifest `generator.sections_kept`) + NEW UNTRACKED FILE `.codex/beatboth5/build_forensic_input.py` (D-5 consumer disclosure).
- A 0-verified gap stub ships `dropped_due_to_failure=False` with non-empty disclosure `verified_text` and `sentences_verified=0`. The OLD count (`not dropped_due_to_failure`) therefore counted gap stubs as kept/verified sections, inflating POLARIS's section count vs Gemini/ChatGPT on the §-1.1 beat-both surface.
- The fix replaces the bare not-dropped check with the UNIVERSAL SURVIVOR SIGNAL: `not dropped_due_to_failure and not getattr(s, "is_gap_stub", False) and getattr(s, "sentences_verified", 1) > 0`.
- VERIFY: (a) this is the SAME survivor signal already used by the existing consumer `key_findings.py` (which skips when `is_gap_stub or sentences_verified == 0`) — confirm semantic equivalence so the count matches what already renders as verified prose; (b) the change is METADATA-ONLY (counts + disclosure), no generated content changes; (c) the `getattr(..., 1)` default of 1 is safe for objects predating the attribute (i.e. a real section without the attr is NOT wrongly excluded); (d) all three run_honest_sweep_r3.py sites + build_forensic_input use the same signal consistently.
- NOTE: `.codex/beatboth5/build_forensic_input.py` is an UNTRACKED new file (will NOT appear in `git diff`). Its D-5 region is pasted in full below under "EVIDENCE: build_forensic_input.py (untracked, D-5 region)". Review it there.

### D-2 — quantified differentiator no-op is LOUD, not a fabricated fix
Files: `src/polaris_graph/generator/quantified_analysis.py`, `tests/polaris_graph/synthesis/test_quantified_tradeoff_phase7.py`.
- This is a DOCUMENTED, LOUD instrumentation change — NOT a forced fix and NOT fabricated quantified content. It adds a single-field `telem["firing_status"]` set at EVERY return point of `run_quantified_section`, so a `spec_produced=False` / `fired=False` manifest names WHERE the differentiator died instead of being silent.
- Distinct statuses: `started` (default), `spec_provider_error` (Writer/transport raised), `no_spec_returned` (spec_provider returned non-dict — caller collapses transport-failure AND legitimate decline into None, so this status is honestly ambiguous), `spec_validation_rejected` (dict failed build_quantified_spec), `execution_failed` (sandbox), `no_verified_sentences` (Regime C dropped all), `fired` (landed).
- VERIFY: (a) this introduces NO fabricated content — `firing_status` is pure telemetry, the `return None, telem` early-exits are unchanged in control flow (no path that previously returned None now returns a section, and vice versa); (b) the consumer `quantified_degradation_disclosure` in run_honest_sweep_r3.py already reads `telemetry.get("firing_status")` so this is wiring a previously-unpopulated field, not inventing a surface; (c) the `no_spec_returned` comment honestly concedes ambiguity rather than guessing a confident reason; (d) tests assert each status path.

## Cross-cutting checks (flag P0/P1 if violated)
- No fix weakens strict_verify / 4-role verifier / redactor / FX-01 promotion guard.
- No faithfulness regression anywhere.
- All new constants are named + env-overridable (LAW VI).
- D-5 is metadata-only; D-2 is telemetry-only; neither alters generated prose.

## Known minor (already classified P3 by me; confirm or downgrade)
- `multi_section_generator.py` line ~4842: a DOCSTRING still says "default section_max_tokens=2400 budget" — stale documentation drift now that the default is `PG_SECTION_MAX_TOKENS` (24000). Comment-only, not active code. P3 doc-nit.

## Smoke evidence
- `tests/polaris_graph/synthesis/test_quantified_tradeoff_phase7.py`: 32 passed (incl. 3 new D-2 firing_status tests + the existing end-to-end `fired` assertion).

---

## DIFF (tracked files)

```diff
diff --git a/scripts/run_honest_sweep_r3.py b/scripts/run_honest_sweep_r3.py
index 5193f25c..261e4a18 100644
--- a/scripts/run_honest_sweep_r3.py
+++ b/scripts/run_honest_sweep_r3.py
@@ -5645,7 +5645,16 @@ async def run_one_query(
                 emit_event(_ext, "strict_verify.section_completed", {
                     "section": sr.title,
                     "local": sr.sentences_verified > 0,
-                    "global": (not sr.dropped_due_to_failure and bool(sr.verified_text)),
+                    # D-5 (#1182): a 0-verified gap stub ships dropped_due_to_failure=False
+                    # with non-empty disclosure verified_text, so the old global signal
+                    # (not dropped and bool(verified_text)) counted gap stubs as globally
+                    # verified content. Exclude them via the SAME universal survivor signal
+                    # filter_verified_sections uses (not is_gap_stub + sentences_verified>0).
+                    "global": (
+                        not sr.dropped_due_to_failure
+                        and not getattr(sr, "is_gap_stub", False)
+                        and getattr(sr, "sentences_verified", 1) > 0
+                    ),
                 })
                 emit_event(_ext, "generator.section_completed", {
                     "section": sr.title,
@@ -6073,7 +6082,11 @@ async def run_one_query(
             f"{retrieval.notes[-1] if retrieval.notes else 'none'}).\n"
             f"{retrieval_fetch_disclosure(_ret_fetched, _ret_failed, _ret_total)}"
             f"Generator model: {PG_GENERATOR_MODEL} (multi-section: outline + "
-            f"{len([s for s in multi.sections if not s.dropped_due_to_failure])} "
+            # D-5 (#1182): exclude 0-verified gap stubs from the Methods parallel-section
+            # count using the SAME universal survivor signal filter_verified_sections uses
+            # — a gap stub ships dropped_due_to_failure=False with non-empty disclosure
+            # text, so the bare not-dropped check over-stated the section count.
+            f"{len([s for s in multi.sections if not s.dropped_due_to_failure and not getattr(s, 'is_gap_stub', False) and getattr(s, 'sentences_verified', 1) > 0])} "
             f"parallel sections + strict_verify + regen-on-failure).\n"
             f"Evaluator model: {PG_EVALUATOR_MODEL} (different family).\n"
             f"Sources classified using T1-T7 tier taxonomy.\n"
@@ -6689,8 +6702,18 @@ async def run_one_query(
             "contradictions_found": len(contradictions),
             "generator": {
                 "outline_sections": [p.title for p in multi.outline],
-                "sections_kept": sum(1 for s in multi.sections
-                                     if not s.dropped_due_to_failure),
+                # D-5 (#1182): sections_kept feeds the §-1.1 beat-both scoring surface
+                # (.codex/beatboth5/build_forensic_input.py). A 0-verified gap stub ships
+                # dropped_due_to_failure=False with non-empty disclosure verified_text, so
+                # the bare not-dropped count inflated POLARIS's section count vs Gemini/
+                # ChatGPT. Exclude gap stubs via the SAME universal survivor signal
+                # filter_verified_sections uses. Metadata honesty — not a content change.
+                "sections_kept": sum(
+                    1 for s in multi.sections
+                    if not s.dropped_due_to_failure
+                    and not getattr(s, "is_gap_stub", False)
+                    and getattr(s, "sentences_verified", 1) > 0
+                ),
                 "words": multi.total_words,
                 # I-bug-105 two-layer reporting: distinguish verified
                 # word count from analyst-synthesis word count so
diff --git a/src/polaris_graph/generator/analyst_synthesis.py b/src/polaris_graph/generator/analyst_synthesis.py
index f6ed1888..3d422fe7 100644
--- a/src/polaris_graph/generator/analyst_synthesis.py
+++ b/src/polaris_graph/generator/analyst_synthesis.py
@@ -37,6 +37,28 @@ from typing import Any
 logger = logging.getLogger(__name__)
 
 
+# D-1 / I-ready-017 (#1182): analyst-synthesis CONTENT token budget.
+#
+# The default writer (deepseek/deepseek-v4-pro per I-cd-009 Carney lock) is
+# REASONING-FIRST: it emits 6k-42k+ reasoning tokens BEFORE the synthesis prose.
+# The prior hardcoded `4000` ceiling starved the content phase, so
+# finish_reason=length truncated mid-planning and the FX-01 (#1105)
+# reasoning->content promotion guard correctly REFUSED to ship the scratchpad,
+# omitting the synthesis. Per LAW VI this is a NAMED, env-overridable module
+# constant (no magic number), defaulting generous so the writer has room to
+# FINISH planning AND write the 1500-3000-word synthesis.
+#
+# IMPORTANT (scope honesty): openrouter_client clamps every reasoning-first
+# request to PG_REASONING_FIRST_HARD_CAP (default 16384, DeepInfra's verified
+# deepseek-v4-pro cap). So on the DEFAULT provider this constant above 16384 is
+# forward-compat HEADROOM, not active room (>16384 clamps down to 16384; <16384
+# floors UP to 16384). It only takes effect once an operator points the writer at
+# a higher-tier endpoint AND raises PG_REASONING_FIRST_HARD_CAP above the model's
+# reasoning burn. The truncation GUARD lives in openrouter_client's promotion
+# path and is untouched here — we only widen the requested content budget.
+PG_SECTION_MAX_TOKENS: int = int(os.getenv("PG_SECTION_MAX_TOKENS", "24000"))
+
+
 # Disclosure preamble (Codex iter-1 suggested rewrite, verbatim).
 ANALYST_SYNTHESIS_DISCLOSURE = (
     "This section is analyst synthesis: interpretive commentary based on "
@@ -422,7 +444,11 @@ async def generate_analyst_synthesis(
     research_question: str,
     prior_verified_context: list[dict[str, Any]] | None = None,
     model: str = "deepseek/deepseek-v4-pro",
-    max_tokens: int = 4000,
+    # D-1 / I-ready-017 (#1182): was a hardcoded 4000; the reasoning-first writer
+    # needs room to finish planning before the synthesis prose. Named, env-overridable
+    # default (openrouter_client clamps reasoning-first to PG_REASONING_FIRST_HARD_CAP
+    # =16384 on the default provider — see the module-level PG_SECTION_MAX_TOKENS note).
+    max_tokens: int = PG_SECTION_MAX_TOKENS,
     temperature: float = 0.3,
 ) -> tuple[str, int, int]:
     """Generate the Analyst Synthesis section.
diff --git a/src/polaris_graph/generator/multi_section_generator.py b/src/polaris_graph/generator/multi_section_generator.py
index db09e632..de2a9182 100644
--- a/src/polaris_graph/generator/multi_section_generator.py
+++ b/src/polaris_graph/generator/multi_section_generator.py
@@ -54,6 +54,39 @@ from src.polaris_graph.generator.provenance_generator import (
 logger = logging.getLogger("polaris_graph.multi_section")
 
 
+# D-1 / I-ready-017 (#1182): per-section + analyst-synthesis CONTENT token budget.
+#
+# The default generator (deepseek/deepseek-v4-pro per I-cd-009 Carney lock) is
+# REASONING-FIRST: it emits 6k-42k+ reasoning tokens BEFORE any content. A small
+# hardcoded ceiling (the prior magic `4000`) starved the content phase, so
+# finish_reason=length truncated and the FX-01 (#1105) reasoning->content
+# promotion guard correctly REFUSED to ship the scratchpad — dropping whole
+# narrative sections. Per LAW VI this is a NAMED, env-overridable module constant
+# (no magic number). Default is deliberately generous so a reasoning-first writer
+# has room to FINISH planning AND write the cited paragraph.
+#
+# IMPORTANT (scope honesty): openrouter_client clamps every reasoning-first
+# request to PG_REASONING_FIRST_HARD_CAP (default 16384, DeepInfra's verified
+# deepseek-v4-pro provider cap — 16385 → 404). So on the DEFAULT provider this
+# constant above 16384 is forward-compat HEADROOM, not active room: any value
+# >16384 is clamped down to 16384, and any value <16384 is floored UP to 16384.
+# Raising this constant only takes effect once an operator points the writer at a
+# higher-tier endpoint AND raises PG_REASONING_FIRST_HARD_CAP above the model's
+# reasoning burn. The truncation GUARD (FX-01 promotion path in openrouter_client)
+# is untouched here — we only widen the requested content budget, never disable
+# the refusal-to-ship-scratchpad guard.
+PG_SECTION_MAX_TOKENS: int = int(os.getenv("PG_SECTION_MAX_TOKENS", "24000"))
+
+# V30 Phase-2 contract-slot extraction floor (M-66 run-5): contract slots echo
+# long regulatory prose spans as JSON; they need at least this much budget even
+# if a caller passes a smaller per-section value. Used as max(section_max_tokens,
+# floor). Named per LAW VI; openrouter_client still clamps reasoning-first to
+# PG_REASONING_FIRST_HARD_CAP.
+PG_CONTRACT_SLOT_MIN_MAX_TOKENS: int = int(
+    os.getenv("PG_CONTRACT_SLOT_MIN_MAX_TOKENS", "6000")
+)
+
+
 # Allowed section labels. The outline call is constrained to pick from
 # this list; prevents the model from inventing off-topic section titles.
 # OFF-PATH ONLY (legacy clinical path, retained byte-identically for the true
@@ -4469,7 +4502,12 @@ async def generate_multi_section_report(
     outline_temperature: float = 0.2,
     section_temperature: float = 0.3,
     outline_max_tokens: int = 2500,    # M-24 fix: was 800, JSON truncated with 12-20 ev_ids per section (V10 FATAL)
-    section_max_tokens: int = 2400,    # M-24 fix: was 1200, bumped for 10-18 sentence target
+    # D-1 / I-ready-017 (#1182): was a hardcoded 2400; reasoning-first writer (V4 Pro)
+    # burned the whole budget on planning -> finish_reason=length -> guard dropped the
+    # section. Now the named, env-overridable PG_SECTION_MAX_TOKENS (generous default;
+    # openrouter_client clamps reasoning-first to PG_REASONING_FIRST_HARD_CAP=16384 on
+    # the default provider — see the module-level constant note).
+    section_max_tokens: int = PG_SECTION_MAX_TOKENS,
     min_kept_fraction: float = 0.5,
     max_parallel_sections: int = 3,
     # R-1: pipeline telemetry for the Limitations synthesis call.
@@ -4826,7 +4864,7 @@ async def generate_multi_section_report(
                     "code fences, or any text outside the JSON "
                     "object."
                 ),
-                max_tokens=max(section_max_tokens, 6000),
+                max_tokens=max(section_max_tokens, PG_CONTRACT_SLOT_MIN_MAX_TOKENS),
                 temperature=section_temperature,
             )
         finally:
@@ -5594,7 +5632,14 @@ async def generate_multi_section_report(
                         research_question=research_question,
                         prior_verified_context=prior_verified_context,
                         model=gen_model,
-                        max_tokens=4000,
+                        # D-1 / I-ready-017 (#1182): was a hardcoded 4000; a
+                        # reasoning-first writer (V4 Pro) needs room to finish
+                        # planning before it writes the synthesis prose, else
+                        # finish_reason=length truncates and the FX-01 guard drops
+                        # the section. Named, env-overridable budget (openrouter_client
+                        # clamps reasoning-first to PG_REASONING_FIRST_HARD_CAP=16384
+                        # on the default provider — see PG_SECTION_MAX_TOKENS note).
+                        max_tokens=PG_SECTION_MAX_TOKENS,
                         temperature=0.3,
                     )
                 )
diff --git a/src/polaris_graph/generator/quantified_analysis.py b/src/polaris_graph/generator/quantified_analysis.py
index 01f4ad5a..98a879f8 100644
--- a/src/polaris_graph/generator/quantified_analysis.py
+++ b/src/polaris_graph/generator/quantified_analysis.py
@@ -333,10 +333,20 @@ async def run_quantified_section(
         extract_numbers_from_evidence,
     )
 
+    # FIX D-2 (#1182): ``firing_status`` is the LOUD, single-field reason the
+    # quantified differentiator did or did not land — set at EVERY return point so a
+    # ``spec_produced=False`` / ``fired=False`` manifest is never silent about WHERE it
+    # died. The consumer ``quantified_degradation_disclosure`` (run_honest_sweep_r3.py)
+    # already reads ``telemetry.get("firing_status")`` for its reader-facing disclosure,
+    # but this producer never populated it — so a no-op surfaced only as a buried log.
+    # Distinct values let a post-run audit tell "broken" (spec_provider_error /
+    # execution_failed) apart from "legitimately inapplicable" (no_spec_returned with a
+    # genuine Writer decline) without reading the raw log. Default = the pre-spec state.
     telem: dict[str, Any] = {
         "enabled": True, "spec_produced": False, "execution_success": False,
         "outputs": 0, "sourced_inputs": 0, "modeled_inputs": 0,
         "verified_sentences": 0, "dropped_sentences": 0, "conflicts": [],
+        "firing_status": "started",
     }
 
     sourced_numbers = extract_numbers_from_evidence(evidence_pool)
@@ -346,9 +356,29 @@ async def run_quantified_section(
     try:
         raw_spec = await spec_provider(question, sourced_numbers)
     except Exception as exc:
-        logger.warning("[quantified_analysis] spec_provider raised: %s", str(exc)[:160])
+        # UNAMBIGUOUSLY broken: the Writer/transport raised (e.g. a 404 on the
+        # generator route surfaced as an exception). Loud, distinct, non-aborting.
+        telem["firing_status"] = "spec_provider_error"
+        telem["firing_error"] = str(exc)[:200]
+        logger.warning(
+            "[quantified_analysis] NO-OP (spec_provider_error): spec_provider raised: %s",
+            str(exc)[:160],
+        )
         return None, telem
     if not isinstance(raw_spec, dict):
+        # AMBIGUOUS by construction: a prod ``spec_provider`` (the Writer closure in
+        # run_honest_sweep_r3.py) collapses BOTH a transport failure (404 / empty 200 →
+        # no JSON parsed) AND a legitimate Writer decline ({"model_id":"none"}) into a
+        # bare ``None`` before it reaches us. We CANNOT tell broken from inapplicable
+        # here — the caller lane must stop collapsing the two (see module summary). Tag
+        # it honestly rather than guess a confident reason we can't support.
+        telem["firing_status"] = "no_spec_returned"
+        logger.warning(
+            "[quantified_analysis] NO-OP (no_spec_returned): spec_provider returned "
+            "no dict (transport failure OR legitimate Writer decline — caller collapses "
+            "both into None; %d sourced numbers were available)",
+            len(sourced_numbers),
+        )
         return None, telem
 
     spec = build_quantified_spec(
@@ -356,6 +386,14 @@ async def run_quantified_section(
         spec_llm=lambda _q, _s: raw_spec,
     )
     if spec is None:
+        # The Writer returned a dict but it FAILED hard validation in
+        # build_quantified_spec (datapoint identity, formula AST, material-dependency,
+        # etc.). A defensible-but-rejected model, not a transport failure.
+        telem["firing_status"] = "spec_validation_rejected"
+        logger.warning(
+            "[quantified_analysis] NO-OP (spec_validation_rejected): Writer emitted a "
+            "spec dict but it failed build_quantified_spec validation (fail-closed)",
+        )
         return None, telem
     telem["spec_produced"] = True
     telem["model_id"] = spec.model_id
@@ -364,6 +402,12 @@ async def run_quantified_section(
 
     result = await execute_quantified_model(spec, evidence_pool, run_dir=run_dir)
     if result is None:
+        telem["firing_status"] = "execution_failed"
+        logger.warning(
+            "[quantified_analysis] NO-OP (execution_failed): spec validated but the "
+            "deterministic sandbox execution did not return clean outputs (model %s)",
+            spec.model_id,
+        )
         return None, telem
     telem["execution_success"] = True
     telem["outputs"] = len(spec.outputs)
@@ -376,6 +420,14 @@ async def run_quantified_section(
     telem["verified_sentences"] = report.total_kept
     telem["dropped_sentences"] = report.total_dropped
     if report.total_kept == 0:
+        # The spec executed but EVERY computed sentence failed Regime C (e.g. an
+        # unlabeled modeled assumption, a number≠display mismatch). No verified prose.
+        telem["firing_status"] = "no_verified_sentences"
+        logger.warning(
+            "[quantified_analysis] NO-OP (no_verified_sentences): %d computed "
+            "sentence(s) all failed Regime C verification (model %s)",
+            report.total_dropped, spec.model_id,
+        )
         return None, telem
 
     # I-cred-008b (#1162) SITE 4/4 (quantified trade-off): populate the advisory per-claim disclosure
@@ -400,6 +452,10 @@ async def run_quantified_section(
             for _sv in report.kept_sentences
         ]
 
+    # Reached only when a spec validated, executed, and ≥1 computed sentence survived
+    # Regime C — the differentiator actually FIRED.
+    telem["firing_status"] = "fired"
+
     rendered, _biblio = resolve_provenance_to_citations(
         report.kept_sentences, evidence_pool,
     )
diff --git a/tests/polaris_graph/synthesis/test_quantified_tradeoff_phase7.py b/tests/polaris_graph/synthesis/test_quantified_tradeoff_phase7.py
index d91fde79..6e9617e0 100644
--- a/tests/polaris_graph/synthesis/test_quantified_tradeoff_phase7.py
+++ b/tests/polaris_graph/synthesis/test_quantified_tradeoff_phase7.py
@@ -537,6 +537,8 @@ def test_p7_sweep_orchestrator_end_to_end():
     )
     assert telem["spec_produced"] and telem["execution_success"]
     assert telem["verified_sentences"] >= 1
+    # FIX D-2 (#1182): a section that lands carries the LOUD "fired" firing_status.
+    assert telem["firing_status"] == "fired"
     assert section is not None
     assert "Quantified Trade-off" in section
     assert "[#calc:" not in section                       # token stripped
@@ -557,6 +559,41 @@ def test_p7_sweep_orchestrator_no_spec_returns_none():
     )
     assert section is None and telem["spec_produced"] is False
+    # FIX D-2 (#1182): the no-spec no-op is now LOUD — firing_status names WHERE it
+    # died instead of leaving the manifest silent about the differentiator no-op.
+    assert telem["firing_status"] == "no_spec_returned"
+
+
+# ── FIX D-2 (#1182): firing_status names every no-op + fired path ─────────────
+def test_d2_firing_status_spec_provider_error():
+    rows = {"ev_1": {"statement": "x", "direct_quote": "x"}}
+
+    async def spec_provider(_q, _s):
+        raise RuntimeError("simulated 404 on generator route")
+
+    section, telem = asyncio.run(
+        run_quantified_section("q", rows, spec_provider=spec_provider)
+    )
+    assert section is None
+    assert telem["spec_produced"] is False
+    assert telem["firing_status"] == "spec_provider_error"
+    assert "simulated 404" in telem.get("firing_error", "")
+
+
+def test_d2_firing_status_spec_validation_rejected():
+    # Writer returns a dict, but it is structurally invalid (bad model_id) ->
+    # build_quantified_spec rejects -> spec_validation_rejected (NOT a transport fail).
+    rows = {"ev_1": {"statement": "x", "direct_quote": "x"}}
+
+    async def spec_provider(_q, _s):
+        return {"model_id": "has spaces", "title": "t", "inputs": [], "outputs": []}
+
+    section, telem = asyncio.run(
+        run_quantified_section("q", rows, spec_provider=spec_provider)
+    )
+    assert section is None
+    assert telem["spec_produced"] is False
+    assert telem["firing_status"] == "spec_validation_rejected"
 
 
 # ── P7-25 number-kind never scientific (Codex diff-gate iter2 P1) ────────────
```

---

## EVIDENCE: build_forensic_input.py (untracked new file — D-5 consumer region, lines ~92-114)

This file does NOT appear in the diff above because it is untracked (`git status` shows `??`). Review the D-5 disclosure block here:

```python
    # generator
    # D-5 (#1182): sections_kept is the POLARIS section count surfaced into the §-1.1
    # POLARIS-vs-Gemini/ChatGPT comparison. As of the D-5 fix, run_honest_sweep_r3.py
    # computes sections_kept EXCLUDING 0-verified gap stubs (the universal survivor
    # signal: not dropped_due_to_failure and not is_gap_stub and sentences_verified>0),
    # so this count no longer over-states POLARIS's verified section count. Manifests
    # produced BEFORE the D-5 fix may carry a stale-inflated sections_kept; the manifest
    # lacks per-section is_gap_stub / sentences_verified, so the corrected count can only
    # be re-derived by re-running the sweep on the fixed code (not recomputed here).
    lines.append("\n### generator")
    lines.append(
        "- (D-5 #1182: sections_kept EXCLUDES 0-verified gap stubs ONLY for manifests "
        "generated AFTER the D-5 fix landed; manifests generated BEFORE the fix may "
        "OVER-COUNT sections by including gap stubs, and that over-count cannot be "
        "corrected here — the manifest carries no per-section is_gap_stub / "
        "sentences_verified, so re-derivation requires re-running the sweep on fixed code.)"
    )
    for k in ['sections_kept','sentences_verified','sentences_dropped','verified_words','words','limitations_words','analyst_synthesis_words','analyst_synthesis_input_tokens','analyst_synthesis_output_tokens']:
        lines.append(f"- {k}: {g(m,'generator',k)}")
    lines.append(f"- outline_sections: {fmt(g(m,'generator','outline_sections'),300)}")
```

This is a read-only DISCLOSURE/annotation in the forensic-input builder — it does NOT recompute the count, it annotates that the count's meaning changed after the D-5 fix. Confirm it is purely additive disclosure (no recompute, no content change) and that the survivor-signal description it states matches the run_honest_sweep_r3.py implementation above.

---

## EVIDENCE: openrouter clamp (src/polaris_graph/llm/openrouter_client.py lines ~1680-1695) — for the D-1 nuance adjudication

```python
            # confirmed: at 20000, V4 Pro completed all 6 sections with
            # zero ReasoningFirstTruncationError.
            # I-bug-941 (#927): default LOWERED 20000 → 16384 to match DeepInfra's
            # deepseek-v4-pro provider cap (verified by binary search 2026-05-28: 16384
            # → 200, 16385 → 404 "No endpoints found"). Operators with higher-tier
            # endpoints can override via env. The 20000 floor produced a deterministic
            # 404 on every generation call against the default provider configuration.
            _min_tokens = int(os.getenv("PG_REASONING_FIRST_MIN_MAX_TOKENS", "16384"))
            if body.get("max_tokens", 0) < _min_tokens:
                body["max_tokens"] = _min_tokens
            # Hard ceiling at DeepInfra's verified cap for deepseek-v4-pro. The runner's
            # per-section/outline max_tokens kwargs can legally request higher (e.g. 24000
            # for V30 Phase-2 long-form sections); without this clamp those requests 404.
            _hard_cap = int(os.getenv("PG_REASONING_FIRST_HARD_CAP", "16384"))
            if body.get("max_tokens", 0) > _hard_cap:
                body["max_tokens"] = _hard_cap
```

---

## EVIDENCE: existing survivor-signal consumer key_findings.py (lines ~79-86) — for D-5 semantic-equivalence check

```python
        if getattr(sr, "dropped_due_to_failure", False):
            continue
        # I-gen-006 (#1178) BB5-C07/P07: a 0-verified gap DISCLOSURE renders disclosure
        # text in verified_text (the legacy is_gap_stub or a V30 contract gap) but is NOT
        # span-verified prose — it must never surface as a Key-Findings "span-verified
        # statement". Skip every gap disclosure (universal signal: sentences_verified == 0).
        if getattr(sr, "is_gap_stub", False) or getattr(sr, "sentences_verified", 1) == 0:
            continue
```

Note: key_findings.py skips when `is_gap_stub OR sentences_verified == 0`; D-5 keeps when `not is_gap_stub AND sentences_verified > 0` (it also requires `not dropped_due_to_failure`, which key_findings.py checks separately just above). Confirm these are the same survivor set so the count matches the rendered prose.

---

Produce your review now. End with the YAML schema block; the LAST `verdict:` line is parsed by CI. APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
