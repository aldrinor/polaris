[HARD ITERATION CAP 5. Front-load ALL findings in iter 1, no drip-feeding. Same bar regardless of iter. Don't pick bone from egg — reserve P0/P1 for real execution risks. APPROVE iff zero P0 AND zero P1. Test results are the ground.]

# CODEX GATE — I-deepfix-006-compose (composition / synthesis fix)

You are the ONLY review gate for this diff. Review the diff `git diff 63ea46f0...bot/I-deepfix-006-compose` against the Fable plan `.codex/I-deepfix-006-compose/fable_compose_fix_plan_EXPANDED.md`. This is iter 1 of 5.

Output the schema in the last section. Verdict APPROVE iff zero P0 AND zero P1. This is a clinical-faithfulness pipeline — the whole review turns on whether the faithfulness engine is genuinely untouched and the additive entailment path genuinely still requires provenance + exact numeric match + entailment.

## What this change is (headline)

The report read like stitched verbatim quotes because the synthesis writer produced almost nothing and the pipeline fell back to the extractive verbatim-span body. This change wires an ADDITIVE entailment-grounded synthesis path (C1–C5) so faithful paraphrases survive, plus span-level junk strips (A–F) and two carry-over fixes (PT11 numeric-cite guarantee, PT13 lexicon v2). Every fix is a default-ON flag with a byte-identical OFF path. The frozen faithfulness engine is CALLED, never edited.

## Per-file summary of the diff vs the plan

**NEW `src/polaris_graph/synthesis/synthesis_entailment_verify.py` (288 lines) — C1 centerpiece.** The additive second verify leg. `entailment_verify(draft, pool, entails_fn)` keeps a synthesized sentence iff (a) it resolves >=1 provenance token to a cited span in the basket-scoped pool (`_resolve_spans` — a token whose evidence_id is absent from the scoped pool is skipped => fails CLOSED), (b) every number in it appears in the union of cited-span numbers (`_numbers_match` — reuses the frozen `_decimals_in` / `_numbers_in` / `_strip_dose_patterns` / `_PLACEBO_COMPARATOR_RE` / `_THRESHOLD_RE` / `_INTEGER_PERCENT_RE` imported UNCHANGED from provenance_generator), and (c) the span ENTAILS the sentence via `consolidation_nli.entails_directional` (span=premise, sentence=hypothesis) — IN PLACE OF the >=2-verbatim-content-word lexical leg only. On a judge DEGRADE (`None`) it falls back to the SAME strict >=2 content-word overlap the frozen engine uses (conservative — a degrade can never keep an ungrounded paraphrase). `make_entailment_union_verify_fn(base_verify_fn)` wraps strict_verify: it UNIONS strict_verify's kept sentences with the entailment leg's, deduped by normalized sentence; every strict_verify pass is kept; the entailment leg only ADDS. A fault in the entailment leg returns the base strict_verify report unchanged.

**`src/polaris_graph/generator/depth_synthesis.py` (+302/-120) — C1/C2/C3 wiring.** `synthesize_cross_source_findings` wraps the incoming `verify_fn` (= frozen strict_verify) with `make_entailment_union_verify_fn` when `PG_SYNTH_ENTAILMENT_VERIFY` on (C1). `single_source_synthesis_active()` (C2, requires C1 also on) lowers the eligibility floor from the definitional 2 to 1 so a 1-origin basket is synthesized and labeled "(single source)", never dropped; the cross-vs-single TIER boundary stays 2. `_collect` now carries `is_entailment` per sentence (read from the union wrapper's `synthesis_entailment_verified` soft-warning). C3: a finding carries `is_synth_entailment=True` when entailment-rescued, and the D8 seam keys are attached when the legacy gate is on OR (promote flag on AND entailment-rescued). The large −120/+... block near line 365 is a CRLF/whitespace re-touch of the existing COV-DECHROME-BASKETS block (identical text) plus the new floor logic — verify it is not a semantic change to dechrome.

**`src/polaris_graph/roles/native_gate_b_inputs.py` (+48) — C3 routing.** The DS-* second loop now fires when EITHER `PG_DEPTH_SYNTHESIS_D8_GATE` OR `PG_SYNTH_D8_PROMOTE` is on. Per-finding `route_d8 = _legacy_d8 or (_promote_d8 and is_synth_entailment)`; a non-routed finding is left entirely untouched (byte-identical to legacy-off). In the promote-only branch (legacy gate off) it calls `promote_synthesis_entailment_finding` as a FAIL-OPEN confirmation — a definitive non-entailment verdict skips promotion; any hook fault keeps the finding routed.

**`src/polaris_graph/generator/analyst_synthesis_deviation_check.py` (+24) — C3 hook.** `promote_synthesis_entailment_finding(audit_sentence, cited_rows, entails_fn)` — the entailment analog of the D3 `_frozen_engine_verifies_sentence` promote hook; delegates to C1's `entailment_grounds_sentence`. FAIL-CLOSED on a wiring fault (missing module => False, never silent True).

**`src/polaris_graph/generator/multi_section_generator.py` (+151) — C4 + PT11.** C4 `_reorder_synthesis_body_lead` (`PG_SYNTH_BODY_LEAD`): stable-partition so analytical sections LEAD and the verbatim `_EVIDENCE_BASE_TITLE` + `_LOW_RELEVANCE_LEDGER_TITLE` TRAIL as a labeled appendix — returns `body + supporting`, every section still present, original relative order preserved; applied LAST so only render/assembly order changes. PT11 `_suppress_uncited_decimal_sentences` (`PG_COMPOSE_NUMERIC_CITE_GUARANTEE`): a sentence carrying a decimal but no `[N]`/`[#ev:]` citation is removed and DISCLOSED (suppress-only, removing an uncited number is the safe direction); uses external_evaluator's abbreviation-aware boundary helper; fail-safe (import failure => text untouched, never blind-drop).

**`src/polaris_graph/generator/analyst_synthesis.py` (+78) — C5.** `_render_clean_synthesis` (`PG_SYNTH_RENDER_CLEAN`): dedupes the doubled section disclosure and lifts per-sentence `[confidence:…]` markers into one compact per-section note (bucket counts). Render-only, faithfulness-neutral; no claim upgraded or dropped.

**`src/polaris_graph/generator/weighted_enrichment.py` (+272) — A/B/C/D/E span strips.** A/B `strip_inline_furniture` (`PG_INLINE_FURNITURE_STRIP`): excises fixed-token furniture (gov banner, `Crossref N`, `N Minute Read Time`, `WP/\d+/\d+`, dd-mm-yyyy stamp) unconditionally; clause-form front-matter (IMF copyright, "Prepared by", "Authorized for distribution by", "would like to thank") only when the matched clause carries NO finding signal (fail-open — a real attribution with a finding is kept whole). C `strip_inline_markup` (`PG_INLINE_MARKUP_STRIP`): excises markdown-link remnants, bare URLs, URL-path query fragments, mid-line orphan headings (line-start numbered headers preserved), stray emphasis markers. Both wired into `_sanitize_report_line` and `_substantive_units`. D `is_shell_source_quote` (`PG_SHELL_SOURCE_INPUT_SCREEN`): a nav/search link-farm shell (ev_716 shape) is held OUT of the drafting INPUT only — the source stays in pool + bibliography + disclosure; FAIL-CLOSED to KEEP (finding signal or substantial residual prose => not a shell). E `_row_is_marketing_only_preamble` (`PG_EVIDENCE_BASE_FINDING_PREFERENCE`): an UNJUDGED marketing-only preamble (no finding signal) is DEMOTED to the low-relevance ledger (kept at weight), never dropped; a judged-relevant row always wins first (last-resort leg in `_row_routes_to_ledger`).

**`src/polaris_graph/generator/verified_compose.py` (+108) — F + C3 reformat.** F `_snap_window_to_whole_value` (`PG_FULL_QUOTE_WINDOW_SNAP`): snaps a verified span's window ends outward to whole-value token boundaries against the row's FULL direct_quote so a number/word is never cut mid-value (the P0 truncated-number fix). Extend-ONLY within the same row => a SUPERSET of the verified span => grounded by construction; bounded by `_MAX_WHOLE_VALUE_EXTEND=64` per end. C3 `_reformat_uncovered_disclosure` (`PG_UNCOVERED_DISCLOSURE_REFORMAT`): rewrites the raw `[uncovered supporting evidence for: …]` block into human prose at render time — subject + span preserved verbatim, NEVER deleted.

**`src/polaris_graph/generator/provenance_generator.py` (+91) — PT13 + splitter.** PT13 v2 `_detect_unhedged_superlative` (`PG_PT13_LEXICON_V2`): attribution verbs (warns/says/argues/predicts/…) count as source-anchoring hedges; a `top` that is a list rank ("top 10") or positional ("at the top") is skipped. Splitter `_SENTENCE_SPLIT_RE_V2` (`PG_SENTENCE_SPLIT_SYMBOL_BOUNDARY`): also splits after `.!?` before a hard furniture symbol (`* © •`, whitespace optional) or — with mandatory whitespace — a digit / opening quote; a decimal with no whitespace is NEVER split. **NOTE: strict_verify itself is NOT in the changed hunks of this file** — only the PT13 detector and the sentence splitter are edited. Confirm this.

## Binding constraints (verify each holds)

1. **Faithfulness engine untouched.** strict_verify / numeric leg / NLI / provenance / D8 / span-grounding are all CALLED, never edited. Confirm `def strict_verify` does not appear in any changed hunk of provenance_generator.py.
2. **Entailment path is ADDITIVE + still tightening.** A synthesized sentence still needs (a) a resolvable provenance token, (b) every number present in the cited span (the SAME numeric predicate the frozen engine applies), AND (c) span-entails-sentence. The union wrapper is a pure superset — it can never REMOVE a strict_verify pass. A number that moves/mangles fails leg (b) and is dropped. A non-entailed paraphrase fails leg (c) and is dropped. A judge degrade falls back to the strict >=2 verbatim overlap.
3. **C4 keeps the verbatim evidence base present as a labeled appendix, keep-all.** No section is dropped — only reordered.
4. **No strip deletes a source.** A/B/C excise text fragments only. D holds a shell OUT of drafting input, source stays in pool/bib/disclosure. E demotes to ledger (kept at weight). F extends a window (superset). Every strip is span-level suppress-only or a placement/weight change.
5. **Flags default-ON, byte-identical OFF.** Every new behavior is behind a `PG_*` kill-switch defaulting ON; OFF returns byte-identical legacy output. Each test file asserts both directions.
6. **No caps / targets / thinners.** No breadth number is forced. Confirm no hardcoded cap/target/thinner was added to make a number hit a goal (§-1.3 day-waster ban).

## TEST EVIDENCE (verified real by the gate author, LAW II)

89 offline tests PASS in 38.45s (I re-ran them; matches the claimed 40s). Breakdown:
- `test_synthesis_entailment_verify_ideepfix006` (8): entailed+number-matched paraphrase KEPT; mismatched number DROPPED; non-entailed DROPPED; degrade(None) falls back to verbatim overlap => DROPPED; cross-basket citation fails closed; union wrapper is ADDITIVE over strict_verify (base subset of union); promote hook.
- `test_single_source_synthesis_ideepfix006` (3): single-source synthesized+labeled when C1+C2 on; dropped when C2 off; requires C1.
- `test_synth_d8_promote_ideepfix006` (7): entailed routed when legacy off + promote on; non-entailment dropped by promote hook; promote off byte-identical; legacy on routes all.
- `test_ideepfix006_compose_synthrender` (9): C5 disclosure de-double + confidence-note; C4 evidence-base->appendix + off byte-identical; PT11 uncited-decimal removed+disclosed, integer-only/cited survive, off byte-identical.
- `test_deepfix006_span_strips` (26): A/B/C/D/E strips + every OFF byte-identical + fail-open cases (Prepared-by-with-finding kept, real numbered heading preserved, judged-relevant marketing row stays in body).
- `test_deepfix006_splitter_pt13` (14): splitter widening (decimal never split, glued closing quote not split), PT13 v2 (attributed superlative hedged, top-10 exempt, real superlative still flagged), both OFF byte-identical legacy.
- `test_deepfix006_compose_snap_reformat` (11): F window snap (mid-value number/word completed, decimal not cut, bounded), C3 uncovered-disclosure reformat (never deleted).
- `test_depth_synthesis` (11): existing suite green; the one edited test pins `PG_SYNTH_SINGLE_SOURCE=0` to assert the definitional >=2 OFF path.

## MOST CRITICAL to verify (the four that decide APPROVE)

1. The entailment verifier does NOT relax faithfulness — a synthesized sentence STILL needs a resolvable provenance token + every number present in the cited span + span-entails-sentence. Confirm leg (b) reuses the frozen numeric helpers unchanged and that a degrade cannot keep an ungrounded paraphrase.
2. `strict_verify` itself is not edited (only additive wrappers + PT13 detector + splitter in provenance_generator.py).
3. C4 keeps the evidence base present as an appendix (reorder, not drop).
4. No span strip deletes a whole source (A/B/C excise fragments; D input-hold keeps source in pool; E demotes to ledger; F extends window).

If any of the four is violated, that is a P0. A real-but-narrow correctness gap (e.g. a regex that over-strips a legitimate finding fragment, an off-by-one in the window snap, a floor that lets an ungrounded single-source paraphrase render un-adjudicated) is P1. Cosmetic / style is P2/P3 and does NOT block.

## Required output schema (§8.3.9) — last lines of your response

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

The final line MUST be `verdict: APPROVE` or `verdict: REQUEST_CHANGES`.
