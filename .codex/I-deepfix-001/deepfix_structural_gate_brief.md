HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

# Codex diff gate — I-deepfix-002 (#1363) STRUCTURAL DRB-II rebuilds (M2/M3/M5/M6)

Review the consolidated diff of 22 files (~3595 lines) implementing 4 structural DRB-II improvements. Diff: `.codex/I-deepfix-001/deepfix_structural_consolidated.patch`. The two NEW core files are `src/polaris_graph/retrieval/document_type_classifier.py` (M2) and `src/polaris_graph/generator/cross_source_synthesis.py` (M6) — read them in full. The design they implement is `.codex/I-deepfix-001/STRUCTURAL_DESIGN_M2_M3_M5_M6.md`. Repo root `C:/POLARIS`.

These land on top of the already-committed I-deepfix-002 fix-now set (HEAD a3333536). They were built in 4 isolated worktrees and consolidated by file-copy + a `git merge-file` 3-way for the two shared files (`scripts/run_honest_sweep_r3.py` = M3+M5+M2; `multi_section_generator.py` = M5+M6); one conflict in the bibliography render was hand-resolved (M3a PMID-locator fallback + M2 genre tag both kept). All 22 files py_compile clean; all 5 wave tests pass on the consolidated tree (M3a 5/5, M3b 6/6, M5 all-assertions+conservation, M2 0-failures, M6 20/20).

## The §-1.3 law you are checking against
POLARIS is **WEIGHT-and-CONSOLIDATE, never FILTER-and-DROP**. The ONLY hard gate is the faithfulness engine, which is **FROZEN**: `strict_verify`, `verify_sentence_provenance`, NLI/entailment, the 4-role D8 adjudicator, span-grounding, provenance-token parsing must NOT be edited. (`git diff --name-only` over the engine files is empty — verify this holds.) Every new path is fetch/classify/select/render/compose-layer behind a LAW-VI kill-switch.

**P0 checklist across all 4 waves:**
1. Confirm NO faithfulness-engine file/function is edited (M6's composer CALLS `verify_sentence_provenance` via a passed `verify_fn` but must not modify it; M2 is a weight; M5 is routing; M3 is fetch coverage).
2. Confirm each kill-switch reverts byte-identical when OFF.
3. Confirm NO hard-drop of a real source; every wave keeps-and-discloses (M2 re-weights+labels, M3 adds coverage, M5 routes-to-disclosed, M6 adds sentences on top of keep-all atoms).
4. Confirm NO new disclosed/advisory value (M2 document-type weight, M5 disclosed_only, M6 analytical unit) is read by an abort/approval/release gate.

## The 4 waves (verify each does what it claims, nothing more)

**M3 — dropped canonical PDFs render (default-ON, fetch-side):**
- M3a: `provenance_generator._num_for` + `nodes/assemble._resolve_all_citations` now carry `doi`/`pmid` onto the bib row; `run_honest_sweep_r3._bib_entry_has_locator` returns True on a non-blank PMID; `_render_bibliography_lines` renders `https://doi.org/{doi}` then `https://pubmed.ncbi.nlm.nih.gov/{pmid}/` when url+doi blank. Gated by the pre-existing `PG_BIB_REQUIRE_LOCATOR`; the extra keys are additive (OFF byte-identical). NEVER fabricates — only renders a real id the row already carried.
- M3b: `frame_fetcher` — the OpenAlex abstract short-circuit is loosened (`PG_FRAME_MULTI_ABSTRACT` default-ON), and a Semantic-Scholar 3rd abstract source is added (`PG_FRAME_S2_ABSTRACT` default-ON), feeding the existing `_pick_richest_abstract` (longest wins). DOI-consistency guard rejects a wrong-paper abstract. No Sci-Hub, no full-text fabrication — abstract is the honest ceiling for a paywalled primary; the landed abstract still flows through UNCHANGED strict_verify.
- **VERIFY (the implementer flagged these):** (a) M3b keeps the full-text guard clause — it drops ONLY the abstract short-circuit, so a clinical full-text entity still skips OpenAlex; confirm "always consult OpenAlex" was correctly scoped to "always when no usable full text exists" (avoids a clinical-roster regression). (b) `test_m56_frame_fetcher.py` — 2 pre-existing tests were pinned to OFF flags via monkeypatch (they assert the legacy short-circuit, which OFF restores byte-identically; the ON path is covered by the new test). Confirm this is honest, not hiding a regression.

**M5 — non-journal single-origin cites (default-ON, select-side):** `weighted_enrichment.diagnose_unbound_supports_selection` partitions enrichment members into `promoted` vs `disclosed_only`. A member is PROMOTED if credibility_weight≥W (default 0.10) OR corroboration≥K (default 2 distinct verified origins) OR its host is a recognized journal venue; else routed to `disclosed_only` (kept in pool + disclosure + a dedicated `_cwf_disclosed_block` in the report, never dropped). `PG_CWF_PROMOTION_ELIGIBILITY` default-ON; OFF promotes-all (byte-identical). **VERIFY:** conservation (`promoted ∪ disclosed_only == original`); it keys on `credibility_weight`+corroboration+journal-venue, NEVER on `selection_relevance` (does not re-impose the banned B18 relevance floor); the journal carve-out fails CLOSED; fail-OPEN-to-promote-all on any exception.

**M2 — journal-scope document-type weighting (DEFAULT-OFF, classify-side, operator opt-in):** NEW `document_type_classifier.classify_document_type` (deterministic, offline, no LLM) assigns a per-citation genre + a multiplicative (0,1] SURFACE weight; carried through `tier_classifier` (additive None fields) → `live_retriever` → `weighted_corpus_gate.build_corpus_credibility_disclosure` (a SECOND disclosed `document_type_adjusted_mean`, raw `weighted_credibility_mean` untouched) → `run_honest_sweep_r3` render (genre bib tag + corroboration re-rank). DOUBLE gate: `PG_DOCUMENT_TYPE_WEIGHT=1` AND the workforce protocol `document_type_preference == journal_article`. Default-OFF byte-identical (the M2 test proved 0/64 disclosure mismatch OFF). **VERIFY:** the document-type weight / `document_type_adjusted_weight` is NEVER read by an abort/approval gate; it NEVER calls the reversed `journal_only` DROP machinery; the corroboration re-rank keeps the predatory venue in the list (re-ordered, not dropped).

**M6 — verified analytical synthesis (DEFAULT-OFF canary, compose-side; the faithfulness-critical one):** NEW `cross_source_synthesis.compose_cross_source_analytical_units` emits `[verified clause A][LICENSED connective][verified clause B]`. Each clause is built by the UNCHANGED `verified_compose._per_basket_verified_clause` (already strict_verify-PASSED, own `[#ev]` token); the connective is from a CLOSED set (`LICENSED_CONNECTIVES`) and LICENSED by `license_relation` from the certified engines (ContradictionEdge / consolidation-NLI / equivalence). `relational_quantifier_guard` gains a `licensed_relations` param that NEUTRALIZES any unlicensed connective to "; separately, ". Wired additively into `verified_compose._compose_section_per_basket` behind `PG_CROSS_SOURCE_SYNTHESIS` (default-OFF). Layer-2: `analyst_synthesis` reasoning-token default 16384→32768; `analyst_synthesis_deviation_check` gains a default-OFF `PG_ANALYST_SYNTHESIS_PROMOTE_GROUNDED` label-promote. **VERIFY (highest scrutiny):** the connective carries NO provenance token, so strict_verify still passes iff BOTH atoms pass (the engine remains the only gate); `license_relation` defaults to "neutral" and NEVER fabricates a relation (a wrong "in contrast" cannot render); fail-closed drops the unit (atoms survive = keep-all) if either clause fails re-verify; the additive append's idx8 footprint-dedup cannot collapse a 2-token analytical unit against a 1-token atom; the fail-loud canary fires if anchored pairs exist but 0 units survive.

## Known limitations I am flagging (confirm acceptable, not blockers)
- **M6 agreement leg is dark:** `multi_section_generator` threads only `edges` (the conflict source), not `equiv_clusters`/`agree_map`, so only "in contrast" (conflict) + "separately" (neutral) connectives can fire — "consistent with this" (agreement) is never licensed. This is fail-closed-safe (under-relaxes to neutral, never fabricates) but reduces analytical yield. Acceptable for the canary, or a P-level finding?
- M6 ships default-OFF; the re-smoke will set `PG_CROSS_SOURCE_SYNTHESIS=1` to exercise it (its yield depends on the F1-structural chrome screen forming ≥2-origin baskets — shipped together in the committed fix-now set).

## Output schema (REQUIRED)
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
m6_agreement_leg_dark_judgment: <acceptable for canary | P-level>
m3_fulltext_guard_scope_ok: true | false
faithfulness_engine_untouched: true | false
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```
