[HARD ITERATION CAP 5. Front-load ALL findings in iter 1, no drip-feeding. Same bar regardless of iter. Don't pick bone from egg — reserve P0/P1 for real execution risks. APPROVE iff zero P0 AND zero P1. Test results are the ground.]

# CODEX GATE r2 — I-deepfix-006-compose (composition / synthesis fix)

You are the review gate. Review the diff `git --no-pager diff 63ea46f0...bot/I-deepfix-006-compose`
against the design plan `.codex/I-deepfix-006-compose/fable_compose_fix_plan_EXPANDED.md`.
Branch `bot/I-deepfix-006-compose` is a 3-way merge of `comp-synthverify` (C1/C2/C3 + new
`synthesis_entailment_verify.py`), `comp-synthrender` (C4 body-lead + C5 render-clean + PT11), and
`comp-spanstrips` (A-F strips + full-quote snap + PT13 v2). 17 files, +2327/-120.

This is CLINICAL-CONTEXT faithfulness code. The ONE thing that must not happen is a relaxation of the
frozen faithfulness engine (strict_verify / numeric / NLI / provenance / span-grounding). Everything
in this diff is designed to be ADDITIVE, SUPPRESS-ONLY, RENDER-ONLY, or PLACEMENT-ONLY, each behind a
default-ON flag that is byte-identical when OFF. Your job is to VERIFY that claim holds and hunt for
any place it does not. The four verification targets below are the highest priority.

## THE FOUR MOST-CRITICAL VERIFICATION TARGETS (a real failure in any of these is a P0)

1. **The entailment verifier does NOT relax faithfulness.** File
   `src/polaris_graph/synthesis/synthesis_entailment_verify.py` (new). A synthesized sentence is kept
   by the entailment leg ONLY when ALL THREE hold: (a) it resolves >=1 provenance token to a cited
   span in the SAME basket-scoped pool (`_resolve_spans` — a token whose evidence_id is absent from
   the scoped pool is skipped => fails CLOSED), (b) every number in it appears in the cited span(s)
   via `_numbers_match`, which reuses the FROZEN engine's own helpers imported UNCHANGED from
   `provenance_generator` (`_strip_dose_patterns`, `_PLACEBO_COMPARATOR_RE`, `_THRESHOLD_RE`,
   `_decimals_in`, `_numbers_in`, `_INTEGER_PERCENT_RE`), and (c) the span ENTAILS the sentence via
   `consolidation_nli.entails_directional` (`_entails_or_degrade`) IN PLACE OF the >=2-verbatim-
   content-word test — never in ADDITION-relaxed. Confirm: entailment REPLACES only the lexical leg,
   never the numeric leg or the provenance leg. Confirm the union wrapper
   `make_entailment_union_verify_fn` is a pure SUPERSET — it starts from `base_verify_fn`'s
   (strict_verify's) kept sentences and only ADDS entailment-only sentences (dedup by normalized key);
   it can NEVER drop a strict_verify pass. Confirm the degrade path (`entails_fn` returns `None`, i.e.
   judge unavailable) FAILS CLOSED to the SAME >=2 content-word overlap the frozen engine uses — a
   degrade can never keep an ungrounded paraphrase. Confirm a number-moved/mangled paraphrase is
   DROPPED by the numeric leg. NOTE for your judgement: `_numbers_match` aggregates numbers across the
   UNION of the sentence's cited spans (a multi-span synthesized sentence cites several spans); assess
   whether "every asserted number appears in at least one cited span" is a faithful predicate here (it
   is the natural generalization of the single-span rule to a multi-cite fused sentence) or whether you
   consider it a relaxation.

2. **strict_verify itself is NOT edited.** `provenance_generator.strict_verify` (def at line ~3598) —
   confirm its body is unchanged by this diff. The provenance_generator diff touches only two shared
   helpers that strict_verify TRANSITIVELY calls: (i) `split_into_sentences` gains a v2 regex
   `_SENTENCE_SPLIT_RE_V2` (flag `PG_SENTENCE_SPLIT_SYMBOL_BOUNDARY`, default-ON, byte-identical OFF)
   that TIGHTENS segmentation (more/shorter units; a digit/quote split requires MANDATORY whitespace
   so a decimal like "3.75" is never split) — assess whether this can ever cause strict_verify to KEEP
   a sentence it would previously DROP (it should only ever split furniture off into an un-tokened unit
   that strict_verify then drops); and (ii) `_detect_unhedged_superlative` gains PT13 lexicon v2
   (`PG_PT13_LEXICON_V2`, default-ON) — confirm this is SOFT-WARNING-ONLY (the call site comment states
   "This does NOT drop the sentence — it emits a warning that the evaluator (PT13) can surface"), so it
   can NEVER change what strict_verify keeps/drops and is faithfulness-neutral.

3. **C4 keeps the verbatim evidence base PRESENT as a labeled appendix (keep-all).**
   `multi_section_generator._reorder_synthesis_body_lead` (flag `PG_SYNTH_BODY_LEAD`, default-ON).
   Confirm it is a STABLE PARTITION returning `body + supporting` — every section still present, only
   the render/assembly order changes; the "Evidence base" + "Low-relevance evidence (kept at weight)"
   sections TRAIL as an appendix, never dropped. Confirm no section content, verdict, or count is
   touched, and that when there is no breadth-surface section to move (or flag OFF) the SAME list is
   returned unchanged (byte-identical).

4. **No span strip DELETES a whole source.** `weighted_enrichment` A-F:
   - A/B `strip_inline_furniture` + C `strip_inline_markup`: EXCISE a boilerplate/markup FRAGMENT from
     inside a unit, keep the surrounding clause. Clause-form front-matter (IMF copyright / "Prepared
     by" / acknowledgements) is excised ONLY when the matched clause carries NO finding signal
     (`_strip_clause_if_no_finding` FAIL-OPENs to KEEP a clause with a decimal/percent/finding verb).
     Confirm these are suppress-only text edits, never a pool/bibliography mutation.
   - D `is_shell_source_quote` / `_is_shell_narration`: a nav/search SHELL source returns `[]` from
     `_substantive_units` so its spans are held OUT of the DRAFTING INPUT — confirm the source STAYS in
     the pool + bibliography + disclosure (the screen lives inside `_substantive_units`, which only
     produces drafting units, and the predicate FAILS CLOSED to KEEP: any finding signal, or
     substantial residual prose after link/URL removal, => not a shell).
   - E `_row_is_marketing_only_preamble` in `_row_routes_to_ledger`: DEMOTES an UNJUDGED marketing-only
     preamble to the "Low-relevance evidence (kept at weight)" ledger — kept at weight, NEVER dropped;
     a real judge (numeric/labeled relevance) always wins first.
   - PT11 `_suppress_uncited_decimal_sentences` (multi_section): SUPPRESSES a SENTENCE carrying a
     decimal with no `[N]`/`[#ev:]` citation, disclosed in the section — never a source. Confirm an
     `[#ev:]` provenance token counts as a citation (so a normal span sentence is never suppressed).

## PER-FILE SUMMARY OF THE DIFF (map to plan C1-C5 + A-F + PT11/PT13)

- **`src/polaris_graph/synthesis/synthesis_entailment_verify.py`** (NEW, +288) — C1. The additive
  entailment verify leg + `make_entailment_union_verify_fn` union wrapper + `entailment_grounds_sentence`
  (the C3 promote confirmation). See target 1.
- **`src/polaris_graph/generator/depth_synthesis.py`** (+302/-... ; note a large block of the diff is
  CRLF/whitespace re-emission of the unchanged COV-DECHROME section — verify it is a no-op churn, not a
  logic change) — C1 wrap (`verify_fn = make_entailment_union_verify_fn(verify_fn)` when
  `PG_SYNTH_ENTAILMENT_VERIFY` on; on exception keeps strict_verify only). C2 single-source:
  `eligibility_floor = 1 if single_source_synthesis_active()` in both `synthesize_cross_source_findings`
  and `depth_synthesis_pre_pass` and `_synthesize_one_basket`. CRITICAL to confirm: the TIER label stays
  at the definitional 2 origins — `tier = _TIER_CROSS_SOURCE if len(basket_origins) >= floor else
  _TIER_SINGLE_SOURCE` — so a 1-origin basket is labeled "(single source)", NEVER mislabeled
  "corroborated" (§-1.1: a misstated corroboration claim is lethal). C3: threads `is_entailment` through
  `_collect` (triple -> quad) and stamps `finding["is_synth_entailment"]=True` on a rescued paraphrase.
  `single_source_synthesis_active()` requires C1 AND C2 both on.
- **`src/polaris_graph/roles/native_gate_b_inputs.py`** (+48) — C3 consumer. The DS-* D8 loop fires
  when EITHER legacy `PG_DEPTH_SYNTHESIS_D8_GATE` OR C3 `PG_SYNTH_D8_PROMOTE` is on; per-finding
  `route_d8` keeps the legacy-gate-on path byte-identical while routing a rescued paraphrase into D8
  even when the legacy gate is off. In the promote-only branch it calls
  `promote_synthesis_entailment_finding` as a FAIL-OPEN grounding confirmation (an infra fault keeps
  the finding routed; a DEFINITIVE non-entailment verdict `is False` skips promotion => the fail-closed
  depth reconcile removes the rendered finding). Confirm a rescued paraphrase is NEVER rendered as body
  prose without D8 VERIFIED/UNSUPPORTED adjudication.
- **`src/polaris_graph/generator/analyst_synthesis_deviation_check.py`** (+24) — C3.
  `promote_synthesis_entailment_finding` — the entailment analog of the D3 `_frozen_engine_verifies_
  sentence` hook; delegates to `entailment_grounds_sentence`; FAIL-CLOSED on a wiring fault (returns
  False, never a silent True).
- **`src/polaris_graph/generator/multi_section_generator.py`** (+151) — C4 `_reorder_synthesis_body_
  lead` (target 3) + PT11 `_suppress_uncited_decimal_sentences` (target 4, suppress-only + disclosed;
  if EVERY span line was an uncited decimal the Evidence-base section is not emitted — assess whether
  that edge is acceptable given a normal span line always carries its `[#ev:]` token = a citation).
- **`src/polaris_graph/generator/analyst_synthesis.py`** (+78) — C5 `_render_clean_synthesis`
  (`PG_SYNTH_RENDER_CLEAN`, default-ON): dedupe the DOUBLED section disclosure + lift per-sentence
  `[confidence:…]` markers into ONE compact per-section note. RENDER-ONLY; confirm the section stays
  labeled interpretive (the renderer re-adds the canonical preamble) and no claim is upgraded/dropped —
  the labels are aggregated (Counter), not discarded.
- **`src/polaris_graph/generator/verified_compose.py`** (+108) — F full-quote-window snap
  `_snap_window_to_whole_value` (`PG_FULL_QUOTE_WINDOW_SNAP`): EXTEND-ONLY within the SAME evidence row
  so a number/word is never cut mid-value (the P0 truncated-number fix); bounded by
  `_MAX_WHOLE_VALUE_EXTEND=64`/end; `start,end,snap_end` AND `span_text` are all rebuilt from the
  widened slice so the emitted text and the `[#ev]` token bounds AGREE, and strict_verify re-checks the
  whole number is present. Confirm the widened slice is a verbatim SUPERSET of the verified span (never
  crosses rows / never fabricates). Plus C3 `_reformat_uncovered_disclosure`
  (`PG_UNCOVERED_DISCLOSURE_REFORMAT`): rewrites the raw "[uncovered supporting evidence for: …]" block
  into human prose at RENDER time only (after partition), preserving subject+span VERBATIM, NEVER
  deleting.
- **`src/polaris_graph/generator/provenance_generator.py`** (+91) — PT13 lexicon v2 + splitter v2
  (target 2). Both flag-gated default-ON, byte-identical OFF.
- **`src/polaris_graph/generator/weighted_enrichment.py`** (+272) — A-F strips (target 4).
- **Tests** (8 files, +1085): `test_synthesis_entailment_verify_ideepfix006` (8),
  `test_single_source_synthesis_ideepfix006` (3), `test_synth_d8_promote_ideepfix006` (7),
  `test_ideepfix006_compose_synthrender` (9), `test_deepfix006_span_strips` (26),
  `test_deepfix006_splitter_pt13` (14), `test_deepfix006_compose_snap_reformat` (11),
  `test_depth_synthesis` (11).

## BINDING CONSTRAINTS (the diff must not violate any)

- The FROZEN faithfulness engine (strict_verify / numeric leg / NLI / provenance / span-grounding /
  D8) is UNTOUCHED — every reference is CALLED, never edited.
- The entailment path is ADDITIVE + TIGHTENING: a synthesized sentence must carry a resolvable
  provenance token, match EVERY number in its cited span(s), AND be entailed by that span. Entailment
  replaces ONLY the >=2-verbatim-content-word lexical leg, never the numeric or provenance legs.
- C4 keeps the verbatim evidence base PRESENT as a labeled supporting appendix — keep-all placement,
  never a drop/cap/thin.
- No strip deletes a SOURCE. A/B/C excise text FRAGMENTS (keep the clause); D holds spans out of
  drafting INPUT (source stays in pool + bib + disclosure); E DEMOTES to the ledger (kept at weight);
  PT11 suppresses SENTENCES. Every deletion/suppression is DISCLOSED.
- Every flag defaults ON and is byte-identical when OFF (`0/false/off/no`). No caps / targets /
  thinners / breadth numbers (the §-1.3 day-waster ban).

## TEST EVIDENCE (the ground)

89 offline tests PASS in ~26-40s, re-run just now on this branch:

```
tests/polaris_graph/generator/test_depth_synthesis.py .......... (11)
tests/polaris_graph/roles/test_synth_d8_promote_ideepfix006.py ....... (7)
tests/polaris_graph/synthesis/test_single_source_synthesis_ideepfix006.py ... (3)
tests/polaris_graph/synthesis/test_synthesis_entailment_verify_ideepfix006.py ........ (8)
tests/polaris_graph/test_deepfix006_compose_snap_reformat.py ........... (11)
tests/polaris_graph/test_deepfix006_span_strips.py ........................... (26)
tests/polaris_graph/test_deepfix006_splitter_pt13.py .............. (14)
tests/polaris_graph/test_ideepfix006_compose_synthrender.py ......... (9)
============================= 89 passed =============================
```

## OUTPUT SCHEMA (§8.3.9 — emit EXACTLY this shape; the LAST `verdict:` line is parsed)

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

APPROVE iff zero P0 AND zero P1. Classify anything that is not a real execution/faithfulness risk as
P2/P3. Do not bank findings for a later iter — this is iter r2 of 5.
