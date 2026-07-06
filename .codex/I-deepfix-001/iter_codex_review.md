## verdict

CONVERGE (Fable's proposal is sound, adopt with my refinements) because it correctly decouples prose composition from downstream sentence verification while keeping coverage co-equal, but it needs tighter citation-set policy, fallback semantics, and fired-path validation.

## critique_of_fable

**1. real_architecture**

Code-cites are mostly plausible from the inline root: `_section_baskets_for_compose`, `expert_facet_planner.py`, `credibility_pass.py`, `abstractive_writer.py`, `cross_source_synthesis.py`, `verified_compose.py`, and renderer hooks all match the named system shape. Logic is sound: global coherence must be created before verification; strict verification must filter sentences, not define composition granularity.

What breaks: Fable overstates "generation-time attribution" as sufficient. Writer-emitted `[#ev]` tokens are useful hints, not authority. The authoritative citation binding must be deterministic after drafting: parse sentence, candidate spans, provenance check, strict_verify, then rewrite/repair. Also, "arXiv 2604.01432" is not in the inline best-practice brief. NEEDS-CODE-CHECK: verify that cited paper/reference exists in the actual research pack before using it as support.

**2. composition_fix**

Code-cites are plausible: `_WRITER_SYSTEM`, `_build_writer_prompt`, `_compose_one_basket`, `_compose_section_per_basket`, `_run_section`, and `_rewrite_draft_with_spans` match the confirmed root. Logic is directionally correct: group writer primary, bounded repair, K-span only after exhausted repair.

What breaks: "kept verified sentences + K-span for uncovered facts" can still create choppy mixed prose if appended inside the same paragraph. Fallback must be section-local but visually and semantically separate: body paragraph from verified authored sentences, then a labeled evidence disclosure block. Also, "byte-identical" when `PG_SYNTH_PRIMARY=OFF` is plausible but NEEDS-CODE-CHECK: any new shared helper imports, default flag parsing, or renderer paths could perturb output.

**3. coverage_fix**

Code-cites are plausible from the inline root: `PG_BASKET_CONSUME_FINDING_DEDUP`, `finding_dedup`, `cross_source_synthesis.py`, `run_honest_sweep_r3.py`, `run_gate_b.py`, and wideners are all named. Logic is strong: multi-origin baskets must exist, cross-source synthesis must move into the body, and frontier wideners need fresh validation.

What breaks: `PG_FINDING_DEDUP_NLI` is risky if it merges "same topic" instead of "same finding." It must require bidirectional entailment for same-claim grouping, or explicit contradiction/extension edges for cross-source analysis without merging. Numeric comparator is good, but only if unit normalization is deterministic and refuses ambiguous denominators, time windows, populations, currencies, and baselines. NEEDS-CODE-CHECK: whether `ClaimGraph ContradictionEdge`, `entails_directional`, and `edges` at `multi_section_generator.py:4976/:5011` carry enough metadata for safe plan-driven pairing.

**4. traceability**

Code-cites are plausible but less confirmed: `_basket_corroboration_block`, `PG_SPAN_RESOLVER`, and provenance re-pointing were mentioned inline, but `citation_set_minimizer.py` is new. Logic is mostly sound, especially separating inline citations from corroboration weight.

What breaks: Fable's "KEEP every member that independently entails it" conflicts with the user's required "minimal independently-entailing citation set inline" and can hurt Source-Necessity. Better: inline the smallest sufficient set that independently entails the sentence and covers distinct factual clauses; demote redundant same-statement supporters to the weight channel. Thoroughness risk should be measured by the offline scorer, not preemptively solved by over-citing.

**5. faithfulness_approach**

Code-cites are plausible and the logic is mostly correct: strict_verify/NLI/D8/provenance remain unchanged, and repair changes the candidate text, not the gate. This is the right clinical safety posture.

What breaks: "K-span disclosure fallback is verbatim and trivially re-passes the gate" is too casual. Verbatim source excerpts can still be misleading if trimmed mid-scope, attached to the wrong claim, or rendered as answer prose. It must pass provenance/region checks and be rendered only as evidence disclosure, not a synthesized conclusion. NEEDS-CODE-CHECK: whether D8/report_redactor treats labeled disclosure blocks differently from body prose.

**6. build_and_validate_plan**

Code-cites are plausible. Logic is strong: default-OFF, parallel tracks, replay split, fresh front-half for wideners, offline scorer before paid judges, dual real Codex/Fable gates.

What breaks: too many flags in parallel can obscure causal attribution unless V1/V2/V3 are kept strict. The offline DeepTRACE scorer must be treated as a triage predictor, not a pass gate, because DeepTRACE uses full-source judgment and core/filler decomposition that local NLI may approximate poorly. NEEDS-CODE-CHECK: whether banked `corpus_snapshot.json` contains full fetched source text needed for F-matrix estimation.

**7. biggest_risk**

Logic is sound: repair non-convergence is the main operational failure mode. The de-risk is good: replay harness, fail-loud canary, logs, variant isolation.

What breaks: the biggest risk is broader than repair. The system can "fire" syntactically while still producing low-quality coherent prose that passes sentence entailment but lacks section-level argument, pro/con balance, or DRB-II analysis. Add a coherence/coverage audit over the actual rendered report, not just writer-path counts.

## faithfulness_check

Fable does not intentionally relax the clinical-safety gate. The proposal keeps strict_verify, NLI entailment, D8 4-role, provenance, region checks, and redaction downstream as hard filters.

K-span demotion is acceptable only with a hard distinction: exhausted repair may release verified/labeled source evidence, but not unverified authored prose. The "always release something" guarantee still holds if the released item is a provenance-checked disclosure quote and the report clearly avoids presenting it as synthesized clinical guidance. It does not hold if a K-span is stitched into body prose as a substitute paragraph.

The bounded repair loop is safe only if `PG_WRITER_REPAIR_MAX` is a strict finite cap, every attempt re-runs unchanged verification, and exhaustion cannot ship the failed generated sentence. No loop-forever, no judge-error bypass, no local-window rescue, no "mostly supported" prose.

Flagged relaxation risk: relation/connective licensing. Any cross-source sentence that makes an aggregate claim must be verified per factual clause, with the connective licensed by contradiction/agreement/arithmetic evidence. A pooled-source verification of an emergent sentence would be a faithfulness regression.

## my_architecture

PLAN: build a section/facet plan with explicit evidence baskets, expected recall claims, expected analysis claims, and pro/con slots for debate queries.

RETRIEVE: widen frontier with facet and subentity expansion, preserving weight-not-filter. Retrieval improves available evidence but never decides truth.

CONSOLIDATE: consume finding-dedup clusters into keep-all baskets, with strict same-finding grouping. Agreement, contradiction, and extension edges are metadata, not deletion rules.

SYNTHESIZE-coherent-prose-first: this is where global coherence is produced. The section writer drafts coherent paragraphs over planned basket groups and planned cross-basket analytical units. It may order, connect, compare, and hedge, but only from supplied evidence metadata.

ATTRIBUTE coarse-to-fine: after drafting, sentence boundaries are parsed and each factual clause is bound to candidate basket spans. Writer tokens are hints; deterministic provenance binding is authority.

VERIFY per-sentence downstream: strict_verify/NLI/provenance/D8 verify every factual sentence or clause after composition. This gate filters, repairs, drops, or converts to disclosure; it never re-fragments the writing process.

REPAIR: first re-attribute, then revise the whole paragraph using exact failure reasons, capped by `PG_WRITER_REPAIR_MAX`. Exhaustion drops failed authored claims and optionally emits labeled provenance-checked evidence excerpts.

RENDER: body contains only verified authored prose and deterministic tables. Inline citations are minimal independently-entailing sets. Extra corroborators appear as count+weights, not inline cites.

I agree with Fable's main architecture. I differ on citation minimization, deterministic post-hoc attribution authority, and stricter separation of fallback disclosure from body prose.

## composition_fix

Implement behind `PG_SYNTH_PRIMARY=0` default and `PG_WRITER_REPAIR_MAX=2`.

In `src/polaris_graph/generator/abstractive_writer.py`, change `_WRITER_SYSTEM` and `_build_writer_prompt` from one-sentence-per-span to one coherent paragraph per evidence group. Require every factual sentence to end with copied provenance token hints, preserve numbers/hedges, and forbid facts outside supplied spans.

In `src/polaris_graph/generator/verified_compose.py`, change `_compose_one_basket` so first failure does not break to K-span. Verify all sentences, collect failures, try CoF re-attribution first, then bounded paragraph-level repair with `revise_reasons`. After cap, keep only verified authored sentences; failed generated sentences are discarded.

In `src/polaris_graph/generator/multi_section_generator.py`, make the group writer the primary body path when `PG_SYNTH_PRIMARY` is on and entailment enforcement is active. The verified-span dump remains fallback-only for missing baskets or exhausted repair disclosure.

Keep exactly one render-chrome predicate, `is_render_chrome_or_unrenderable`, as pre-writer span hygiene and final render hygiene. Do not add more shape-specific denylists.

Refinement vs Fable: K-span fallback must render as a separate labeled evidence block, not appended prose; writer-emitted citations are hints, not binding authority.

## coverage_fix

Coverage is co-equal with composition.

In `src/polaris_graph/synthesis/credibility_pass.py`, slate-enable `PG_BASKET_CONSUME_FINDING_DEDUP` so baskets consume finding-dedup clusters with all members retained. Add `PG_FINDING_DEDUP_NLI` only if same-finding grouping requires strong bidirectional entailment; contradiction/extension should create edges, not merges.

In `cross_source_synthesis.py`, replace identical `subject|predicate` pairing with facet/section-plan candidates, contradiction edges, agreement edges, and extension edges. Keep `LICENSED_CONNECTIVES` closed and `relational_quantifier_guard` active.

Move `compose_cross_source_analytical_units` and `depth_synthesis.synthesize_cross_source_findings` from the advisory tail in `run_honest_sweep_r3.py` into the main section-body plan in `multi_section_generator.py`.

Add deterministic numeric analysis only when measure, unit, entity, denominator, time window, and baseline match. Otherwise fail closed to neutral wording.

Add `presentation_tables.py` behind `PG_PRESENTATION_TABLES=0`: render deterministic markdown tables from already verified numeric claims with citations.

Enable `PG_EXPERT_FACET_PLANNER` and `PG_SUBENTITY_QUERY_EXPANSION` in the paid winner slate and Gate-B full capability slate. These require fresh front-half validation, not corpus replay.

Extend Gate-B canaries: fail when eligible multi-origin baskets exist but zero analytical units/depth findings render; fail when finding-dedup has multi-member clusters but no multi-origin baskets reach composition.

## traceability

Inline citations should be the minimal independently-entailing set per sentence: every inline source must entail the exact sentence or its assigned factual clause, and the set should be no larger than needed to support all clauses. Do not inline every corroborator.

The consolidate-keep-all basket remains visible as a corroboration weight channel: count, tier/source weights, and agreement/contradiction metadata. These are not citation markers and should not be counted as support for that sentence.

For DeepTRACE Citation-Accuracy and Source-Necessity, prune non-entailing inline citations and demote redundant same-statement supporters. For Citation-Thoroughness, use the offline scorer to detect under-citation, then add only genuinely necessary independent supporters.

For debate queries, plan pro/con slots explicitly. Render at least one verified pro and one verified con when the corpus supports both, with hedged certainty. If counter-evidence is absent after widened retrieval, disclose that evidence asymmetry rather than fabricating balance.

## build_validate_plan

Build behind default-OFF flags in parallel where write sets do not overlap.

Corpus-replay-validatable: writer group contract, bounded repair, basket regrouping, cross-source synthesis moved into body, citation minimizer, corroboration weight render, presentation tables, and offline self-scorer. Replay real `corpus_snapshot.json` into real `report.md`; measure fallback rate, repair convergence, multi-origin baskets, analytical units, cited-source necessity, unsupported estimate, chrome rate, and actual prose quality.

Needs fresh front-half run: `PG_EXPERT_FACET_PLANNER`, `PG_SUBENTITY_QUERY_EXPANSION`, counter-evidence retrieval, and any claim that breadth/coverage improved. Resume-from-corpus skips fetch/frontier gates, so it is blind to these.

Build an offline ALCE-style DeepTRACE self-scorer before paid judges: parse statements and citations into C, estimate F with existing entailment over fetched full text, compute Accuracy, Thoroughness, Unsupported, and Source-Necessity approximation. Treat it as triage, not final truth.

Run V1 composition-only, V2 coverage-structural-only, V3 combined. Each build needs real Codex review and real Fable 5 review before paid DeepTRACE/DRB-II judging.

## biggest_risk

The biggest risk is a false-fired pipeline: flags are on, writer path logs activity, but the final report still lacks coherent section-level argument and cross-source analysis.

Concrete de-risk: add a rendered-report acceptance harness that checks actual paragraphs, not internal counters: writer prose shipped, fallback disclosure rate below threshold, eligible facets have verified analytical units, debate queries show verified two-sided treatment when evidence exists, and every authored sentence passes unchanged faithfulness gates.
