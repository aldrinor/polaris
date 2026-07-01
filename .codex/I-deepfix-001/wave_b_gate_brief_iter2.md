HARD ITERATION CAP: 5 per document. This is iter 2 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd on remaining non-P0/P1 findings; do not bank issues for iter 6.
- If you detect you are holding back a P1 for the next round — DON'T. Surface it now.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

# Codex consolidated diff gate — I-deepfix-001 beat-both Wave B, ITER 2 (re-gate after your iter-1 P1)

You reviewed Wave B at iter 1 and returned REQUEST_CHANGES with ZERO P0 and ONE P1. This iter reviews the FIX for that P1 plus re-confirms the rest is intact. Review the consolidated diff `.codex/I-deepfix-001/wave_b_consolidated.patch` (git diff of the whole of Wave B vs pre-Wave-B gated HEAD 73f3bb13). Read the touched files in the repo (root C:/POLARIS, read-only) for context.

## YOUR ITER-1 P1 AND HOW IT WAS FIXED — verify the resolution

**iter-1 P1:** "WS-3 Evidence base bypasses the frozen verification path. `_append_evidence_base_section` is called after strict-verify/remap and appends a `SectionResult` directly with `verified_text`, `biblio_slice=[]`, and no `kept_sentences_pre_resolve`; Gate-B/D8 later only reads `kept_sentences_pre_resolve`, so these rendered lines can ship outside strict_verify/D8."

**THE FIX (in `src/polaris_graph/generator/multi_section_generator.py`, `_append_evidence_base_section` ~line 5843):** the evidence-base block is now routed through the SAME `_rewrite_draft_with_spans` + `strict_verify` the sections use (the FIX-K verbatim-span pattern at ~line 4214):
1. Build the verbatim-span block via `build_evidence_base_section` (flag-gated, uncapped keep-all SUPPORTS surface).
2. Strip the block's own "## Evidence base" header + the leading "N. " display numbers → clean span sentences.
3. `_rewrite_draft_with_spans(draft, evidence_pool)` → resolves the `[ev_id]` markers to real `[#ev:...]` provenance tokens (exactly like FIX-K).
4. `strict_verify(rewritten, evidence_pool)` → the FROZEN gate. Only `is_verified` sentences survive; if none survive, the function returns False (NO section — no unverified breadth ships).
5. `resolve_provenance_to_citations_with_count(report.kept_sentences, evidence_pool)` → the standard resolver produces the cited text + a LOCAL bibliography.
6. Remap the LOCAL `[N]` onto the GLOBAL bibliography (the section is appended after the global remap), extending `global_biblio` for any newly-surfaced work (§-1.3 keep-all; never drops a source; reuses an existing global number for an already-cited source).
7. The `SectionResult` now carries `kept_sentences_pre_resolve=list(report.kept_sentences)` — the REAL strict_verify `SentenceVerification` objects, so `native_gate_b_inputs` (Gate-B) promotes each `is_verified` entry to a `FourRoleClaim` and the 4-role D8 gate judges it against its cited span.

**VERIFY (grep/read the real code):**
1. Is the evidence-base now genuinely routed through `strict_verify` (not a separate pre-verified append)? Confirm `kept_sentences_pre_resolve` is populated with real `report.kept_sentences` and that `native_gate_b_inputs.py` (~line 795) will therefore see + D8-judge these entries. Is the P1 fully resolved?
2. **Can the fix over-claim or mis-cite?** The verbatim SUPPORTS spans pass strict_verify by construction (the sentence IS the span → 100% overlap, all numerics present). Confirm this is HONEST (a real verbatim span attributed to its real source is a genuine verified claim), NOT a way to launder an unverified claim. A sentence that CANNOT ground must still be DROPPED by strict_verify (never padded/fabricated). Any path where the fix ships an unverified line, fabricates a binding, or mis-maps a local→global citation number to the WRONG source is a P0.
3. Confirm the "N. " display-number strip (`re.sub(r"(?m)^\s*\d+\.\s+", "", draft)`) cannot corrupt a legitimate verbatim span in a faithfulness-relevant way (it strips only the leading display index build_evidence_base_section itself prepends).
4. Frozen engine: `strict_verify` / `resolve_provenance_to_citations_with_count` / `_rewrite_draft_with_spans` are CALLED, never edited. Confirm `git diff --name-only 73f3bb13` over the engine (`strict_verify` / `provenance_generator` / `nli_verifier` / `role_pipeline` / `judge_adapter` / `judge_contract` / `span_grounding` / `four_role` / `mirror_adapter` / `sentinel_adapter` / `credibility_pass`) is EMPTY.

## RE-CONFIRM the rest of Wave B is intact (unchanged since iter-1 except the P1 fix)
- **WS-2** (run_honest_sweep_r3.py, operational_readiness_preflight.py): winner slate applied on the paid path via `apply_winner_slate_on_paid_path` (called ~:17093) + fail-loud slate-OFF preflight. Flags are merge-only/keep-all/additive — no source dropped.
- **WS-4** (native_gate_b_inputs.py, coverage_binder.py, required_entity_ledger.py): DOI-tolerant + basket-member coverage credit. A NON-verified claim can NEVER credit coverage; `verified_covered_ids` counts only VERIFIED claims; genuinely-uncovered entity stays uncovered; byte-identical when `PG_ENTITY_COVERAGE_CITATION_CREDIT` OFF. Any unverified-claim coverage credit is a P0.
- **WS-13** (credibility_llm_tiering.py): bounded-parallel tiering; a straggler DEGRADES to a rules-floor tier, never dropped; byte-identical when `PG_TIER_LLM_PARALLEL` OFF.
- Context: POLARIS is WEIGHT-and-CONSOLIDATE, never FILTER-and-DROP. The D8 terminal judge is moonshotai/kimi-k2.6 (operator-locked, distinct family from the GLM generator); `PG_PERMIT_GENERATOR_EVALUATOR_SAME_FAMILY` stays 1 governing only the disclosed all-GLM side surface — do NOT flag the kimi judge or PERMIT=1.
- Offline tests: all 4 `test_wave_b_*` = 59 passed; the WS-3 test now has a regression guard asserting non-empty, all-verified `kept_sentences_pre_resolve` (a revert to the bypass fails it). Confirm these are real behavioral asserts.

## Output schema (REQUIRED)
```yaml
verdict: APPROVE | REQUEST_CHANGES
frozen_engine_untouched: true | false
ws3_p1_resolved_evidence_base_through_strict_verify_and_d8: true | false
ws3_fix_cannot_launder_unverified_or_miscite: true | false
ws4_no_unverified_coverage_credit: true | false
s13_violations: [...]
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```
