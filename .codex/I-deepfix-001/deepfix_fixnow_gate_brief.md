HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

# Codex diff gate — I-deepfix-002 (#1363) consolidated fix-now set (drb_72 smoke quality fixes)

You are reviewing a consolidated diff of 12 files (~920 lines) that fixes quality defects found by a forensic §-1.1 line-by-line audit of the drb_72_ai_labor smoke report. The diff is at `.codex/I-deepfix-001/deepfix_fixnow_consolidated.patch`. Read it AND the touched source files for context. Repo root is `C:/POLARIS`.

## The non-negotiable architecture law you are checking against (§-1.3 + §9.1)

POLARIS is **WEIGHT-and-CONSOLIDATE, never FILTER-and-DROP**. The ONLY hard gate is the faithfulness engine, which is **FROZEN**: `strict_verify`, NLI entailment, the 4-role D8 adjudicator, span-grounding, and provenance-token validation must NOT be edited by any fix here. Every fix is a render-seam SUPPRESSION, a fetch/credibility CORRECTION, or a disclosure — never a faithfulness relaxation and never a hard-drop of a real source. Every fix is behind a default-ON env kill-switch (LAW VI) that reverts byte-identical when unset.

**Your P0 checklist across all 12 files:**
1. Confirm NONE of these files edits the faithfulness engine logic: `strict_verify`, `verify_sentence_provenance`, NLI/entailment scoring, the 4-role D8 adjudicator, span-bounds/numeric/content-overlap checks, provenance-token parsing. (Render/compose/fetch/credibility code may CALL them unchanged — that is fine.)
2. Confirm every new behavior is gated by a default-ON kill-switch and reverts byte-identical when the switch is OFF.
3. Confirm NO fix HARD-DROPS a real source from `evidence_pool` / `corpus_credibility_disclosure.json` / the bibliography. Suppression must be keep-and-disclose (the source stays in pool + disclosure; only its render placement / citation / corroboration-count changes).
4. Confirm no new disclosed/advisory field is read by an abort/approval/release gate.

## The fixes (anchored — verify each does what it claims, nothing more)

**Group A — `scripts/run_honest_sweep_r3.py`, `src/polaris_graph/generator/quantified_analysis.py`, `src/polaris_graph/synthesis/credibility_pass.py`:**
- **F1 (phantom corroborator)** in `run_honest_sweep_r3.py::_basket_corroboration_block`: gate `PG_CORROBORATION_BIBLIO_PRESENT` (default-ON). Instead of trusting `basket.get("verified_support_origin_count")`, it filters `verified` members to those whose evidence_id/url is actually present in the rendered `bibliography`, recomputes the count from distinct present origins, and SKIPS a basket that has no bibliography-present verified member. Verify: this only changes a DISPLAY corroboration count/skip; it does not touch strict_verify, does not delete a source.
- **F3 (quantified bibliography remap)** part-1 in `quantified_analysis.py::run_quantified_section` (`telem["section_biblio"]=_biblio`, additive) + part-2 in `run_honest_sweep_r3.py` quantified append (gate `PG_QUANTIFIED_BIBLIO_REMAP`, default-ON): folds the quantified section's input sources into `multi.bibliography` with real URL/tier/statement and remaps section-local `[N]` markers to global numbers. Verify: no dangling/duplicate citations; the remap maps to REAL sources, not invented ones.
- **F1-STRUCTURAL (basket-build chrome screen)** in `credibility_pass.py::_assemble_baskets` SUPPORTS branch: gate `PG_BASKET_CHROME_SCREEN` (default-ON). Each SUPPORTS member's `claim_local_span` and the cluster `head.text` are screened through the production predicate `weighted_enrichment.is_render_chrome_or_unrenderable`; a chrome/unrenderable span is excluded from `verified_origin_ids` (the member is still appended to the basket, never deleted). Fail-OPEN with a loud warning if the predicate import fails.

  **>>> FAITHFULNESS-ADJACENT — JUDGE THIS EXPLICITLY (the single most important review item):** on the real drb_72 corpus this chrome screen demotes 9 baskets — 1 phantom (correct) + 7 genuinely chrome (cookie banner, byline, foreign masthead, paywall, accessibility chrome, DOI-not-found page, journal-citation masthead — all correct A1–A10 cleanup). The 8th is the edge: `ev_016` (`clm_5c56d2ffb78b7bac`) is a REAL but mid-word-truncated span ("...firms—particularly small, owner-") whose corroboration count drops 1→0 because `is_render_chrome_or_unrenderable` folds a truncation arm. No source is dropped (member kept in pool + disclosure; a truncated span would not render as verified support anyway), but a corroboration COUNT on a real source is reduced. Is this acceptable under §-1.3 (weight/consolidate, the source is kept and disclosed, the truncated fragment is genuinely unrenderable) — or does screening the `head.text`/`claim_local_span` of a real-but-truncated source improperly relax consolidation? Give a clear verdict. Also assess: should the screen exclude the truncation arm (chrome-only) to avoid touching real-but-truncated spans?

**Group B — `src/polaris_graph/synthesis/tradeoff_modeler.py`, `src/polaris_graph/generator/quantified_analysis.py`, `src/polaris_graph/retrieval/credibility_llm_tiering.py`, `src/polaris_graph/generator/key_findings.py`:**
- **F2 (quantified span fix)** in `tradeoff_modeler.py::build_quantified_spec`: the context-window fallback now translates context offsets into the `ev_text` frame and only adopts a literal when it is UNIQUELY anchored; else fail-closes to the existing `no_unique_literal_span` reject. Verify: this tightens span-anchoring (never loosens) — a non-unique literal is rejected, not guessed.
- **FIX-2 (low-value filler suppression)** in `quantified_analysis.py`: `is_low_value_filler_output` predicate + `PG_QUANTIFIED_FILLER_SUPPRESS` (default-ON); render loop skips filler outputs; whole section withheld under `firing_status="suppressed_low_value_quantified"` when all outputs are filler. Verify: suppression is a render-skip, not a source delete.
- **B2 (uncorroborated top-tier cap)** in `credibility_llm_tiering.py`: `_cap_uncorroborated_top_tier` + `PG_TIER_REQUIRE_VENUE_CORROBORATION` (default-ON) caps a T1/T2 assignment that the LLM inferred from DOI/URL/title alone without a known scholarly venue; prompt hardened. Verify: this is a credibility-WEIGHT correction (caps an over-claimed tier), not a hard-drop; the source stays, at a more honest tier.
- **FIX-3 (headline dedup)** in `key_findings.py::build_depth_layer`: omits the per-section headline already owned by the front Key-Findings block, keeping distinct Challenges/Tension. Verify: cosmetic de-duplication of a repeated headline; no claim lost.

**Group C — `src/polaris_graph/retrieval/topic_relevance_gate.py`, `src/polaris_graph/generator/weighted_enrichment.py`, `src/polaris_graph/retrieval/evidence_selector.py`, `src/polaris_graph/retrieval/live_retriever.py`, `src/tools/access_bypass.py`, `src/polaris_graph/generator/multi_section_generator.py`:**
- **DEFER-1 (off-topic cite suppression)**: `topic_relevance_gate.py` flips `PG_SCOPE_TOPIC_GATE` default 0→1 (kill-switch kept). `weighted_enrichment.py` adds `offtopic_cite_suppress_enabled()` (`PG_OFFTOPIC_CITE_SUPPRESS` default-ON) + `_is_confirmed_offtopic(row)` keyed on `topic_offtopic_demoted`/`content_relevance_label∈{demoted,escalated_demoted}` (NEVER the raw lexical score) + an `offtopic_suppressed` field on `UnboundSupportsSelection`; off-topic SUPPORTS members are withheld from the enrichment `ev_ids` and recorded in `offtopic_suppressed`. `evidence_selector.py` carries the label additively. `multi_section_generator.py` logs the suppressed set loudly + a bibliography-numberer guard drops `[N]` for confirmed-off-topic eids (no dangling reference). Verify: off-topic decision keys on the GATE's demotion label, not a lexical threshold; the source stays in pool + disclosure; only the standalone cite is withheld.
- **F4 (recovered-content registry-error guard)**: `live_retriever.py` `_recovered_content_error_class()` — a B02/B04 RECOVERED span is adopted only if non-starved AND not a registry/error/block page; else it stays a disclosed gap. `access_bypass.py` `is_registry_error_page()` + `registry_error_guard_enabled()` (`PG_REGISTRY_ERROR_GUARD` default-ON) + signatures. Verify: this prevents a DOI-404/registry-error PAGE from being adopted as recovered body text (the ev_057 doi.org-404 case) — a fetch-quality correction, fail-closes to a disclosed gap, no fabrication.
- Note: **DEFER-4** residual chrome (`_is_residual_chrome_furniture` in `weighted_enrichment.py`) was already committed in HEAD `5734d55e`; it is present in the diff context, not a new change here.

## Cross-cutting things to verify
- The 3-way merge of `quantified_analysis.py` (Group A F3-part1 + Group B FIX-2) is coherent: BOTH `telem["section_biblio"]` (run_quantified_section) AND `is_low_value_filler_output`+suppression are present and non-conflicting.
- Every `PG_*` kill-switch defaults ON and the OFF path is byte-identical legacy.
- No off-by-one / dangling `[N]` in the bibliography after F1/F3/DEFER-1 marker remapping.
- `multi_section_generator.py` / `run_honest_sweep_r3.py` getattr-safe additive-attribute idiom is used (no hard attribute assumption that breaks a non-multi-section path).

## Output schema (REQUIRED — loose prose is rejected)
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
ev016_truncation_judgment: <your explicit §-1.3 verdict on the F1-STRUCTURAL ev_016 edge>
faithfulness_engine_untouched: true | false
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```
