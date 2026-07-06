# I-deepfix-001 — TRUE ROOT + SOLUTION (Codex + Fable co-equal review, wfah1knug / wf_58dfcd00-390, 2026-07-05)

## THE ONE ROOT (both reviewers agree, code-cited)
The unit of COMPOSITION was made identical to the unit of VERIFICATION — one sentence certified against one source span (the "atom"). Every downstream producer was then only ALLOWED to emit concatenations of independently-verified atoms.
- abstractive "writer" prompt = "You output exactly one sentence per span, nothing else" (abstractive_writer.py:358) → it is an atom POLISHER, not a synthesizer.
- _compose_one_basket: on FIRST failing sentence, breaks and falls back to a verbatim K-span (verified_compose.py:1281-1317).
- multi-source "synthesis" = _join_verified_clauses: glues clauses with a "SEMANTICALLY-NEUTRAL connective", asserts "NO emergent aggregate predicate" (verified_compose.py:1418-1459); relational_quantifier_guard STRIPS aggregate wording (1651).
- cross_source_synthesis only pairs baskets with an IDENTICAL subject|predicate anchor (cross_source_synthesis.py:85-94) → near self-annulling after consolidation-NLI merges.
- depth_synthesis is WITHIN-basket same-claim only, ≥2-distinct-origin eligibility; free-redraft drops every sentence that moves a token/number → returns [] (depth_synthesis.py:107-109, 636-637); "drafted 0" at run_honest_sweep_r3.py:16026-16031.

This ONE constraint mechanically causes BOTH symptoms:
(A) choppy, junk-prone prose (raw extractor atoms policed by per-shape denylists; no sentence may span sources or carry an integrative predicate).
(B) zero cross-source depth (no producer is ALLOWED to draft a claim integrating N sources).

strict_verify is NOT the culprit. The culprit is that SYNTHESIS is not the primary invariant of the report — it is optional/additive/fail-open to atoms.

## THE FIX — CO-EQUAL

### Composition (make synthesize-verify-REPAIR the primary body path)
1. Change the writer contract (abstractive_writer.py _WRITER_SYSTEM ~344-359, _build_writer_prompt ~362+) from "one sentence per span" to "write a coherent multi-sentence narrative for this GROUP of verified spans; EVERY sentence ends with the exact [#ev:id:start-end] token for the span it rests on; every number verbatim; every hedge preserved."
2. In _compose_one_basket (verified_compose.py:1281-1335) + _compose_section_per_basket/_run_section (multi_section_generator.py:4924-5030): on a per-sentence verify FAILURE do NOT break-to-K-span; run a bounded RARR-style repair-in-place loop (re-prompt with the specific wrapper failure reasons — revise_reasons plumbing already exists) up to N tries; only after the repair budget is exhausted emit the K-span, LABELED as a disclosure quote, not body prose.
3. Keep ONE render-chrome hygiene screen (is_render_chrome_or_unrenderable) as pre-writer input + final-render hygiene (chrome self-entails; strict_verify can't classify junk). STOP adding new per-shape denylists / snap-span abbrev lists.
- All behind default-OFF flag (PG_SYNTH_PRIMARY) → OFF = byte-identical.

### Coverage + cross-source depth (equal weight — both a structural cause AND a starvation cause)
1. STRUCTURAL: flip keystone PG_BASKET_CONSUME_FINDING_DEDUP ON (credibility_pass.py:65-76) so the consolidator CONSUMES finding_dedup's same-finding grouping (~1781 singletons → ~99 clusters with member_indices) → multi-origin baskets with verified_support_origin_count≥2 actually EXIST; + finding_dedup NLI/qualitative grouping so paraphrases reach one basket.
2. MOVE cross_source_synthesis.compose_cross_source_analytical_units + depth_synthesis.synthesize_cross_source_findings OUT of the additive advisory tail (run_honest_sweep_r3.py ~15957-16038, 18880-18924) INTO the main section-body synthesis plan; each facet produces verified multi-source analysis with engine-LICENSED relation words (LICENSED_CONNECTIVES cross_source_synthesis.py:64-69 stays). Replace the anchor-equality pairing predicate with facet/section-plan/claim-graph-edge grouping. Treat "0 analytical units when eligible pairs exist" as a FAILED validation, never silently accepted.
3. STARVATION: flip frontier wideners ON — PG_EXPERT_FACET_PLANNER (expert_facet_planner.py:56) + PG_SUBENTITY_QUERY_EXPANSION (sub_entity_query_expander.py:62) — and add to the paid winner slate (run_honest_sweep_r3.py:20012-20023, currently forces consolidation/cross-source but NOT these) → ~35 facet queries not 7.

## FAITHFULNESS — UNTOUCHED (strengthened)
Only WHICH sentence gets drafted changes, never HOW it's verified. Every authored/synthesized sentence carries its [#ev] token(s), passes verify_sentence_provenance + strict_verify UNCHANGED (provenance_generator.py:2046-2060, 3510-3519). Writer verify wrapper stays STRICTER (judge-error→is_verified=False fail-closed, no local-window rescue, abstractive_writer.py:285-314). Cross-source: each factual clause keeps its OWN token + passes strict_verify PER CLAUSE (never one aggregate verified against a pool); relation word only from the NLI/D2-licensed closed set. D8 + report_redactor still drop settled non-VERIFIED prose. §-1.3 basket-faithfulness STRENGTHENED (claim decided against whole multi-source basket).

## TIME PLAN — FAST + PARALLEL (hours-to-a-day, not months)
- Build all behind default-OFF flags; hold current HEAD as scored baseline.
- Run scored variants in PARALLEL: V1 composition-only, V2 coverage-structural-only, V3 both — by REPLAYING banked corpus_snapshot.json corpora through the fixed render path (no fresh retrieval), REAL report.md, not proxies.
- Per corpus measure: chrome/junk rate (target 0), mid-word endings, K-span fallback rate, multi-origin basket count, multi-cited sentence count, cross-source analytical units, depth kept-findings, distinct cited sources in body, word count, rubric facet coverage; then run DeepTRACE + DRB-II judges on the ACTUAL outputs.
- SPLIT (I-wire-014 banked-replay-blind lesson): composition rewrite + basket-regroup + synthesis-move are replay-validatable (operate on on-disk corpus); the frontier wideners are NOT (banked corpora fetched with wideners OFF) → need ONE fresh small scored front-half run to prove the wider frontier + re-confirm the 1313-word/zero-unit artifact is gone.
- Extend the Gate-B M6 firing canary (dr_benchmark/run_gate_b.py:2431-2460) to also FAIL on composition fallback-rate and zero depth kept-findings when eligible baskets exist.
- Each build gated by BOTH real Codex CLI + real Fable 5.

## WHAT WE STOP DOING
Kill the whack-a-mole atom-edge patch stack: snap-span abbrev heuristics + per-shape chrome denylists (chrome_furniture_screen, block_page_chrome_scrub, _screen_fallback_chrome, _screen_fixk_render_chrome, _compose_junk_screen — keep ONE). Stop treating synthesis/depth as an advisory tail that fail-opens. Stop shipping keystone regroup + wideners default-OFF. Kill §-1.1-banned proxy gates (word/citation/source counts, string-presence PASS/FAIL, green offline tests as preflight, banked-replay as validation for fetch/frontier changes). ONLY acceptance = a fresh scored report passing a line-by-line §-1.1 read + DeepTRACE + DRB-II.

## RESIDUAL SPLITS (flagged for operator)
1. Codex frames HYBRID (synthesis attempted then fail-opens to atoms); Fable frames UNIFIED (composition-unit == verification-unit even on the happy path). Fable's is sharper/more actionable; Codex's "both attempt then degrade" means the fix is a primary-path REWRITE, not a flag-flip. Both true.
2. Fable names a SEPARABLE second coverage cause — retrieval frontier starvation (wideners default-OFF, 1313 words) — Codex under-weights. Must fix too or composition improves while coverage stays starved.
3. Codex honest objection (verified): HEAD already carries partial mitigations, so the 1313-word/zero-unit artifact must be re-confirmed on a FRESH scored run before+after; do NOT demote K-span until the bounded repair loop is proven reliable + bounded (clinical always-release must hold).

## STATUS
Symptom-patch campaign (I-deepfix-001 chrome/trunc/date fixes) HELD — 5 committed but they patch atom edges (do not commit the remaining 4; the FF1 chrome fix Fable just rejected for a NEW over-strip is the disease live). Await operator GO on this primary-path direction before building.
