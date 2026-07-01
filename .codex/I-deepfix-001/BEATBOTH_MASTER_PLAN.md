Confirmed. The grep proves the spine: `PG_CONSOLIDATION_NLI`, `PG_CROSS_SOURCE_SYNTHESIS`, `PG_BREADTH_ENRICHMENT_ENABLED`, `PG_DOCUMENT_TYPE_WEIGHT` are all default-OFF and are only switched ON by `apply_full_capability_benchmark_slate()` (`run_gate_b.py`, `operational_readiness_preflight.py`). The paid `run_honest_sweep_r3.py` path does not apply the slate — `operational_readiness_preflight.py:448` literally warns "PG_BREADTH_ENRICHMENT_ENABLED stays default-OFF -> NARROW report. Do NOT launch the paid run" without it. The drb_72 run ran the winners OFF or GPU-degraded. That is the master root cause. Here is the plan.

---

# POLARIS BEAT-BOTH MASTER PLAN — I-deepfix-001
## Remove all 6 residuals + run-level weaknesses, and take #1 on every target board

---

## PART 1 — CONFIRMED TARGET BOARD SET + exact score to be #1

The research confirms a **2-axis, 5-board CHASE set** (faithfulness × coverage), plus a component/badge tier and an ignore tier. This is the final set.

### 1A. The 5 CHASE-FOR-#1 boards

| # | Board | Axis | Judge / harness reality | Exact score to be #1 |
|---|---|---|---|---|
| **B1** | **DeepTRACE** (arXiv 2509.04499, Salesforce AI Research, ICLR 2026) | Citation faithfulness, 8 metrics | **No public scorer, no leaderboard.** GPT-5 judge default. Must re-implement (decomp → C/S matrices → Hopcroft–Karp → GPT-5 judge). | Beat GPT-5-Deep-Research on its 6 led metrics AND beat BingChat/Copilot on the 2 debate metrics: **Unsupported <12.5→~0, Citation-Accuracy >79.1→95+, Thoroughness >87.5, Source-Necessity >87.5, Relevant >87.5, Uncited 0.0, One-Sided <48.7→single-digit, Overconfident 0.0.** |
| **B2** | **DeepResearch-Bench-II** (arXiv 2601.08536, USTC / Agent Research Lab) | Coverage (Recall 74% / Analysis 18% / Presentation 8%) | Gemini-2.5-Pro judge. **Ships `run_evaluation.py`** (drop-in). Blocked-reference −1 leakage layer. | Current #1 = AI21-DeepResearch **64.38**. Clear-lead target **Total ≈ 66–68** → **InfoRecall ≈ 63–65, Analysis ≈ 70, Presentation ≈ 92**. Recall is the whole battle; Presentation is saturated (12/16 >89) and cannot move rank. |
| **B3** | **DeepScholar-Bench** (arXiv 2508.20033, Stanford Guestrin Lab) | Live synthesis + retrieval + **verifiability** | **Live leaderboard, monthly-refresh, anti-contamination.** Submission by form. No frontier DR system submitted yet → **open top slot.** | Beat the open baselines (STORM, OpenScholar, DeepScholar-ref) on all three axes; verifiability is POLARIS's provenance edge. Cheapest credible public #1. |
| **B4** | **ResearchQA** (arXiv 2509.00496) | Long-form scholarly QA, citation rubrics | 160k rubric items / 75 fields. Run a stratified subset. | Field-best satisfies **<11%** of citation rubrics. Target **decisively >11% (aim ≥30%)** on the stratified subset — POLARIS's strongest muscle vs the field's weakest score. |
| **B5** | **DeepResearch-Bench v1 — FACT leg** (arXiv 2506.11763) | Citation accuracy + effective citation count | Established HF leaderboard; RACE leg led by Gemini-2.5-Pro RACE 48.88. | Chase **top FACT** (citation accuracy = our edge). Track RACE, do not over-index. Register **ResearchRubrics** (arXiv 2511.07685, Scale AI) alongside once the rubric harness exists. |

### 1B. PROVE-COMPONENT tier (badges, not headline #1)
BrowseComp-Plus (retriever isolation, fixed ~100k corpus), Mind2Web 2 (source attribution), FACTS Grounding (Kaggle grounding badge), RAGChecker + FRAMES (internal faithfulness/multi-hop regression harnesses).

### 1C. IGNORE (off-axis — spending cycles here is waste)
BrowseComp, GAIA, HLE, SimpleQA/-Verified, WebArena/Mind2Web v1 — parametric-reasoning exams and live-web needle-hunts where frontier general LLMs define the ceiling, not a grounded pipeline.

### 1D. WATCH
DREAM (arXiv 2602.18940 — "Mirage of Synthesis," reference-free agentic judge; pre-empt it), DR-Arena, DeepResearchEval, ResearchRubrics (register now).

**Two corrections carried into the plan (from the research):** DeepTRACE lab is **Salesforce AI Research**, not Microsoft — fix `BENCHMARKS_STUDY.md` line 14. DeepTRACE metric #4 is **Uncited/listed, lower-is-better** — fix `BENCHMARKS_STUDY.md` line 20 or the scorer inverts. DRB-II scoring is **binary 0/1 with a separate blocked-leakage demotion**, not a native −1.

---

## PART 2 — DE-DUPLICATED WORKSTREAMS

All four gap analyses converge on **one spine**: the WEIGHT-and-CONSOLIDATE half of the pipeline shipped behind default-off flags and degraded to the FILTER-and-DROP legacy path under a GPU-OOM cascade and an unenforceable off-vLLM judge enum. So the winners exist — the job is to **turn them on, stop them degrading, and make the judge stable**, then close the six render/coverage residuals with surgical §-1.3 fixes, then add the two genuine new builds and the frontier coverage loop.

Legend for RISK: **NEUTRAL** = render/disclosure/weight only, frozen faithfulness engine untouched · **ADJACENT** = touches judge/overstatement-guard/coverage-credit but strictly in the safe direction (adds caveats, only credits already-verified support, never relaxes a gate) · **BUILD** = new module.

### TIER 0 — INFRASTRUCTURE (gates every board; nothing scores until these land)

**WS-0 — Kill the GPU-OOM degrade cascade.**
- Change: 2-card device split so W5 reranker + W6 embedder + W10 NLI are not co-resident on `cuda:0`; `PG_CONTENT_RELEVANCE_SCORE_CHUNK=2` (proven 2026-06-30 fix); `PG_CONSOLIDATION_NLI_DEVICE` placement seam (`consolidation_nli.py:73`) as the template.
- Modules: run launcher env + `synthesis/consolidation_nli.py`, `retrieval/live_retriever.py` (W2), `retrieval/credibility_llm_tiering.py`.
- Un-degrades three things at once: W2 semantic-relevance (stops lexical fallback), `consolidation_nli` (stops CPU-wall under-merge), GLM tiering (stops `rules_floor_degraded`).
- Boards: B2 Recall+Analysis, B1 Thoroughness+Necessity. Residuals: run-level OOM, D4/D6 credibility-degrade roots.
- Effort: LOW (env + placement). Risk: **NEUTRAL**.

**WS-1 — D8 judge stability (the render-blocker).**
- Change: (a) swap judge to a **high-OpenRouter-provider-count model — moonshotai/kimi-k2.6 (21 providers)** to kill 429 `RoleTransportError`; (b) enforce the enum via OpenRouter `response_format`/`json_schema` (a constraint OpenRouter honors) instead of the vLLM-only `structured_outputs.choice` (`judge_adapter.py:229-231`) so `JudgeEnumError` cannot fire off-vLLM; (c) bounded per-claim **retry before** the fail-closed degrade (`judge_adapter.py:284-298,311-325`) — a transient blank/429 re-asks, does not convict; (d) verdict **idempotency cache keyed on (normalized_claim, span-identity)** so a byte-twin inherits a clean sibling's verdict (removes the 02-001/02-007 split).
- Modules: `roles/judge_adapter.py`, `roles/openrouter_role_transport.py`, `config/architecture/polaris_runtime_lock.yaml` (judge role + two-family guard).
- Removes the 3 false-negative UNSUPPORTED on grounded top-journal claims that suppress the *scored* Unsupported/coverage numbers.
- Boards: B1 Unsupported #5, Citation-Accuracy #7. Un-holds the D8 coverage release. Residual: run-level D8 false-negatives.
- Effort: MED. Risk: **ADJACENT** — touches the judge. Must confirm two-family segregation holds (kimi = distinct family from deepseek-v4-pro generator; keep `PG_PERMIT_GENERATOR_EVALUATOR_SAME_FAMILY=0`). Safe direction: a real UNSUPPORTED still holds; only transport-noise convictions are removed.

### TIER 1 — TURN THE MACHINE ON (highest board leverage; depends on TIER 0)

**WS-2 — Apply the full winner slate on the PAID run path.**
- Change: the paid `run_honest_sweep_r3.py` launch must apply `apply_full_capability_benchmark_slate()` — `PG_CONSOLIDATION_NLI=1`, `PG_CONSOLIDATION_NLI_PROSE=1`, `PG_CROSS_SOURCE_SYNTHESIS=1`, `PG_BREADTH_ENRICHMENT_ENABLED=1`. These are the confirmed default-OFF winners (grep-verified). Wire a fail-loud preflight assert (the `operational_readiness_preflight.py:448` warning) so a paid run cannot launch with the slate OFF.
- Modules: run launcher / preflight, `synthesis/finding_dedup.py:1053`, `generator/verified_compose.py:167`, `generator/weighted_enrichment.py:55`.
- This is what manufactures multi-source baskets (Blocker 2), the M6 analysis layer (Blocker 3), and the breadth surface (Blocker 1). It is the single highest-leverage change and it gates **both** boards.
- Boards: B2 Recall+Analysis+blocked-ref, B1 Thoroughness. Residual: run-level "12 of 88", "zero corroboration."
- Effort: LOW (flags exist + fire-tests exist). Risk: **NEUTRAL** (consolidation is merge-only, polarity-safe; enrichment is uncapped keep-all through unchanged strict_verify). Hard dependency on WS-0 (else the winners run ON but degrade to CPU/lexical).

**WS-3 — Breadth surfacing + fix the `no_provenance_token=34` leak.**
- Change: route the full ordered SUPPORTS surface from `weighted_enrichment.select_unbound_supports_by_weight` (`weighted_enrichment.py:565`) into a numbered "Evidence base" section so every source with a surviving SUPPORTS span gets a `[N]`. Fix the abstractive-writer leak at its source: an un-provenanced sentence must be **repaired** (bind the nearest SUPPORTS span via the per-basket verified contract `_per_basket_verified_clause`, `verified_compose.py:665`) **before** strict_verify, not silently dropped — so its source still counts as breadth.
- Modules: `generator/weighted_enrichment.py`, `generator/verified_compose.py`.
- Boards: B2 Recall (74% weight — the decisive axis), B1 Thoroughness #8. Residual: run-level "12 of 88 cited."
- Effort: MED. Risk: **NEUTRAL** (still passes unchanged strict_verify; the surface is already uncapped per `weighted_enrichment.py:295,469,573`).

**WS-13 — Raise/parallelize the retrieval-wall tier-classification.**
- Change: bounded-parallel tiering with a batch wall (`PG_TIER_LLM_BATCH_WALL_SECONDS`, `credibility_llm_tiering.py:293`) so the 13 fetched-but-unclassified sources enter the corpus instead of being dropped at `retrieval_wall_hit=true`.
- Modules: `retrieval/credibility_llm_tiering.py`, retrieval-phase wall config.
- Boards: B2 Recall. Residual: run-level "retrieval wall hit (13 unclassified)."
- Effort: LOW. Risk: **NEUTRAL**. Depends on WS-0/WS-1 (throttle stability).

### TIER 2 — THE TWO CLINICAL OVER-CLAIMS (land in the first wave — clinical-safety priority, cheap render fixes)

**WS-5 — D1: Eloundou "46%" re-lifted CLEAN in the Conclusion, caveat stripped.**
- Root: the annotator (`report_redactor.annotate_report_against_verdicts`, `report_redactor.py:677-784`) keys the low-confidence label on **claim_id**; the Conclusion re-lift (`abstract_conclusion.py:139-159`) copies a byte-twin bound to a *different* claim_id (VERIFIED twin `02-010` vs flagged `02-002`), so the label misses and the clean twin ships. Separately the composer dropped the governing conditional antecedent ("could have over half their tasks affected … when accounting for … complementary software"; LLM-alone = 1.8%).
- Change: (a) **re-key the confidence annotation on a span-identity tuple `(evidence_id, cited_start, cited_end)` / normalized-sentence hash**, so ALL byte-twins of a labelled claim inherit the marker at render (adds caveats only, idempotent via `_CONFIDENCE_MARKER_RE`, `report_redactor.py:104`); (b) **effect-size guard** in `overstatement_guard.py`: when a re-lifted numeric sentence's span carries a governing conditional/threshold token adjacent to the number ("when accounting for", "could have", "over half"), require the antecedent clause to travel with the number or append the `[confidence: …]` tag.
- Modules: `roles/report_redactor.py`, `generator/abstract_conclusion.py`, `generator/overstatement_guard.py`. Kill-switch `PG_FIGURE_CONSISTENCY_ANNOTATE=1` (default-ON).
- Boards: B1 Overconfident #2 + Citation-Accuracy #7. Residual: **D1**.
- Effort: MED. Risk: **ADJACENT** (touches overstatement guard) but strictly safe — only adds caveats / carries the antecedent, never widens a span or changes a verdict.

**WS-6 — D2: "1 verified independent source" printed where basket `verified_support_origin_count=0`.**
- Root: the corroboration block (`run_honest_sweep_r3.py:2558-2570`) recomputes the count from render-side `ENTAILMENT_VERIFIED` member labels and ignores the authoritative CONSOLIDATE-leg field `verified_support_origin_count` (`credibility_pass.py:900`; projected at `provenance_generator._basket_for_biblio:3374`). A self-entailing citation-chrome span reads as 1.
- Change: `count = min(recompute, int(basket.verified_support_origin_count or 0))`; when authoritative count is 0 (or `basket_verdict=="unverified"`), route those members to the existing **GROUNDED-BUT-WEAK** sub-bullet and set the header to "0 verified independent source(s)". Mirrors `disclosure_population.py:172-197`, which already buckets on the correct field for the JSON. Sources stay in the numbered Bibliography (§-1.3 no-drop).
- Modules: `scripts/run_honest_sweep_r3.py:2543-2661`, `generator/provenance_generator.py:3374`. Kill-switch `PG_CORROBORATION_COUNT_AUTHORITATIVE=1` (default-ON).
- Boards: B1 Citation-Accuracy #7, Uncited #4. Residual: **D2**.
- Effort: LOW (one field swap). Risk: **NEUTRAL** — strictly reduces an inflated count.

### TIER 3 — COVERAGE CREDIT + RENDER POLISH + DISCLOSURE COHERENCE

**WS-4 — D5: verified robots-and-jobs[4] + GPTs[7] shown "not verified"; coverage 0.571 miscredit.**
- Root: `native_gate_b_inputs._claim_covers_entity` (`native_gate_b_inputs.py:515-536`) credits an entity only on exact `_entity_canonical_match`; entity [4] has an empty URL (DOI-only) so the exact compare fails → empty `covered_element_ids` on genuinely-VERIFIED claims → `required_entity_ledger.py:109-129` reports `coverage_fraction=4/7=0.571` and lists verified entities as gaps.
- Change: make `_entity_canonical_match` **DOI-canonical-tolerant** (strip `https://doi.org/`, lowercase, match bare DOI when URL empty); fallback — credit coverage when a VERIFIED claim's cited `evidence_id` is a SUPPORTS member of the entity's own basket. Additive credit only; D8 still gates (`verified_covered_ids` counts only VERIFIED claims), so it cannot over-claim faithfulness.
- Modules: `roles/native_gate_b_inputs.py`, `roles/coverage_binder.py`, `generator/required_entity_ledger.py`. Kill-switch `PG_ENTITY_COVERAGE_CITATION_CREDIT=1`.
- Boards: B2 Recall/coverage; **un-holds the D8 `release_allowed=False` gate** (partly driven by 0.571); B1 consistency. Residual: **D5** + run-level coverage hold.
- Effort: MED. Risk: **ADJACENT** (coverage credit) but safe — the crediting claim is already span-verified and already cites the entity's source.

**WS-7 — D3: in-prose chrome leaks; canary blind to prose.**
- Root: `evaluate_render_chrome_canary` (`weighted_enrichment.py:1528`) scores only `_report_claim_bullets` (`:1517`) → `0/33 pass` while prose ships the leaked "Introduction" header word (survives `abstract_conclusion._strip_leading_markdown_headers:115`), in-text "(1, 2)" ref markers, and a boundary-truncated "(2017)" with "Morrar et al.," chopped.
- Change: (a) add `_report_prose_units(report_text)` to the canary denominator (`PG_RENDER_CHROME_CANARY_PROSE=1`, default-ON); (b) per-unit prose-chrome normalizer at the render-seam chokepoint (`multi_section_generator.py:~1557`, inside `_sanitize_report_line`; the `render_seam_sanitize_enabled` path `weighted_enrichment.py:1642` is already default-ON): strip a leading bare section-header word, strip in-text `(\d+(,\s*\d+)*)` markers that are not `[N]`/`[#ev]` tokens, repair/withhold a truncated leading `(YYYY)` subject (re-attach the subject from the cited span, the I-wire-014 hyphen-repair pattern). Dedup byte-identical repeated sentences at compose.
- Modules: `generator/weighted_enrichment.py`, `generator/multi_section_generator.py`, `generator/abstract_conclusion.py`, `generator/chrome_furniture_screen.py`. Kill-switch `PG_PROSE_CHROME_NORMALIZE=1`.
- Boards: B2 Presentation (table-stakes), B1 Relevant #3. Residual: **D3**.
- Effort: MED. Risk: **NEUTRAL** (text-only; never drops a source/number/token). **Validation caveat: needs a FRESH run** — the 154/155 banked spans are pre-fix truncated, a banked replay is structurally blind.

**WS-8 — D4: off-topic / wrong-genre sources headline; "journal articles only" unmet.**
- Root: M2 document-type weighting is behind a **double gate that is OFF** — `_m2_journal_pref_active` (`run_honest_sweep_r3.py:2696-2708`) requires `PG_DOCUMENT_TYPE_WEIGHT=1` AND the scope template declaring `document_type_preference: journal_article` (`document_type_classifier.py:214-225`). Neither was set, so the 1986 J. Operations Mgmt robotics paper (weight 0.08), T4 Frontiers, and the OECD working paper headline unchanged.
- Change (§-1.3 WEIGHT-don't-FILTER): set `document_type_preference: journal_article` in the journal-only scope template + activate `PG_DOCUMENT_TYPE_WEIGHT=1` for that question class so `_m2_bib_genre` (`:2711-2724`) genre-tags and re-ranks; add a **publication-year recency leg** so a 1986 pre-AI paper cannot headline an AI-labor review. Keep `PG_JOURNAL_ONLY` OFF — a demoted non-journal stays in the basket at low weight, simply out-ranked for headline slots.
- Modules: `retrieval/document_type_classifier.py`, `config/scope_templates/…`, `generator/weighted_enrichment.py`. Kill-switch is the existing `PG_DOCUMENT_TYPE_WEIGHT` (global default-OFF, ON via template for journal-only runs).
- Boards: B2 Analysis/Presentation, B1 Source-Necessity #6 / source-quality. Residual: **D4**.
- Effort: MED. Risk: **NEUTRAL** (re-rank, no drop). **Needs a FRESH run** — genre weighting acts at retrieval time; banked replay is blind.

**WS-9 — D6: contradiction count "1" vs actual 3; cross-artifact weight incoherence.**
- Root: (a) the disclosure prints `len(renderable_contradictions)` after screening the two `possible_metric_mismatch` flags (`run_honest_sweep_r3.py:13254-13261`) while `manifest.contradictions_found=3` (`:14544`) — no single place states the total; (b) the corroboration block prints the authority-adjusted `credibility_weight` (0.08, `:2663-2667`) while `corpus_credibility_disclosure` prints the raw `tier_prior` (0.30/0.95) for the same URL — two quantities both labelled "credibility weight," compounded by the `rules_floor_degraded` tiering.
- Change: (a) print the full detector total + the screened split ("flagged N; M shown; N−M screened as not-comparable"), `PG_CONTRADICTION_TOTAL_HONEST=1`; (b) label `weight_basis` on every printed weight (tier-prior vs authority-adjusted) or render both on each line, `PG_WEIGHT_BASIS_LABEL=1`; disclose `tiering_mode: rules_floor_degraded` next to each weight when degraded.
- Modules: `scripts/run_honest_sweep_r3.py`, `retrieval/credibility_llm_tiering.py`, `generator/provenance_generator.py` (reconcile to ONE `credibility_weight` at projection).
- Boards: B1 consistency + One-Sided #1 (complete both-sides disclosure). Residual: **D6**.
- Effort: LOW. Risk: **NEUTRAL** (disclosure-label only; no record dropped, no weight recomputed).

### TIER 4 — GENUINE NEW BUILDS (needed to top DeepTRACE #6 and #1)

**WS-10 — Source Necessity module (metric #6; NEW).**
- Change: build `synthesis/source_necessity.py` implementing the paper's exact **Hopcroft–Karp min-vertex-cover** over the citation⊙support bipartite graph; expose necessity per source; quarantine non-necessary + D2 zero-support entries out of the **citation list** while keeping them in the audit ledger.
- **Orientation guard (decides #4 and #6):** the rendered reference list must equal the **12 cited** set (`bibliography.json`); the **88-source** `corpus_credibility_disclosure` must be explicitly typed as an audit ledger, NOT a reference list. Point the necessity/uncited computation at the 12-source list. Mis-pointing at the 88-corpus reads 76/88 as uncited padding — a catastrophic false loss on #4 and #6.
- Modules: new `synthesis/source_necessity.py`, wired into the bibliography render.
- Boards: B1 Source-Necessity #6 (87.5 bar), Uncited #4. Residual: reinforces D2/D4.
- Effort: HIGH (new module + graph algorithm). Risk: **BUILD**, faithfulness-neutral (computed over already-verified support).

**WS-11 — Debate-class router forcing pro AND con baskets (One-Sided #1 / Overconfident #2).**
- Change: add a debate-class detector in `nodes/complexity_router.py` / `nodes/scope_gate.py`; on a contested claim, force a **pro basket AND a con basket into `verified_compose` before strict_verify**, with the weight-and-consolidate path forbidden from funnel-dropping the minority side. Thread the existing `both_sides.py` / `dissent_recall_builder.py`. Also fixes the D6 count so disclosures reconcile.
- Modules: `nodes/complexity_router.py`, `nodes/scope_gate.py`, `generator/both_sides.py`, `retrieval/dissent_recall_builder.py`, `generator/verified_compose.py`.
- Boards: B1 One-Sided #1 (field best 48.7 → single-digit) + Overconfident #2.
- Effort: MED-HIGH. Risk: **NEUTRAL** (both sides span-grounded). This is the hardest DeepTRACE axis — a composition mandate, not retrieval — and the least de-risked; budget a misfire.

**WS-12 — Quantified-analysis spec-validation repair (Analysis 18%).**
- Change: read the durable `telem["spec_reject_reason"]` (`quantified_analysis.py:509`) from the drb_72 manifest to see which of datapoint-identity / formula-AST / material-dependency validation rejected (`:511-525`), then fix the Writer spec prompt or loosen the specific over-strict gate. The sandbox execution + token-binding downstream are unchanged.
- Modules: `generator/quantified_analysis.py`.
- Boards: B2 Analysis (cross-study deltas are the natural home for DRB-II analysis rubrics). Residual: run-level `spec_validation_rejected` / `quantified_silent_no_op`.
- Effort: MED. Risk: **NEUTRAL** (faithfulness-neutral; downstream binding unchanged).

### TIER 5 — FRONTIER ARCHITECTURE (defensible coverage lead beyond flag-flips)

**WS-15 — Test-time iterative draft refinement (TTD-DR, arXiv 2507.16075) — bounded draft-denoise loop.**
- Rationale: the gap map names this the **single biggest architectural coverage lever** and the current SOTA winner's mechanism (74.5% win rate vs OpenAI Deep Research). Flag-flips (WS-2/3/13) get POLARIS into contention on B2 Recall; TTD-DR is what pushes to a *defensible* clear lead and lifts Analysis.
- Change: add a **bounded** draft → gap-detect → targeted-retrieve → revise → re-verify loop that reuses the existing CRAG loop-back (`nodes/crag_adequacy_loop.py`, widen `PG_ADEQUACY_CRAG_MAX_LOOPS` from 1) and the unchanged strict_verify. The current draft steers the next retrieval; each revision re-passes the frozen verify engine.
- Modules: `nodes/crag_adequacy_loop.py`, `retrieval/required_entity_retrieval.py`, generator compose loop.
- Boards: B2 Recall (74%) + Analysis (18%), B3/B4 coverage. 
- Effort: HIGH. Risk: **NEUTRAL to the faithfulness engine** (revisions re-verify), MED on cost/wall-clock — bound loops hard. Phase 2 / stretch; not required to *reach* #1 on B1, needed to *hold* #1 on B2 defensibly.

*(Companion stretch: true multi-hop reasoning-driven retrieval, Search-R1 arXiv 2503.09516 — LACKS; needed for the harder DRB-II 2nd-order-fact rubrics. Same phase as WS-15, lower priority.)*

### TIER 6 — MEASUREMENT INFRASTRUCTURE (cannot claim #1 without scoring)

**WS-14 — Official-comparable scorers.**
- **B1 DeepTRACE has NO public scorer** — re-implement exactly from the 8 formulas: statement decomposition → binary C (statement×source) and S (support) matrices → 6 ratio metrics + Hopcroft–Karp necessity → GPT-5 judge + confidence 1–5. WS-10's min-vertex-cover is shared. Human-validation target Pearson ≥0.62 support / ≥0.72 confidence.
- **B2** runs the shipped `run_evaluation.py` (Gemini-2.5-Pro judge) — drop-in.
- **B5** runs the DRB-v1 HF FACT harness. **B3** via the DeepScholar submission form/harness. **B4** on a stratified ResearchQA subset. Adopt **RAGChecker** (amazon-science) + **FRAMES** as the internal claim-level regression harness.
- Effort: HIGH (B1 re-impl is a real work item). Risk: measurement, not pipeline.

### TIER 7 — HOUSEKEEPING
**WS-16 —** Reconcile `docs/polaris_pipeline_canonical.md` (lines 48-52 still mark Mirror/Sentinel/Judge "not built" while `roles/judge_adapter.py` + `four_role_held` are wired) and fix `BENCHMARKS_STUDY.md` lines 14 (lab) + 20 (Uncited metric orientation). Same-PR drift rule. Effort: LOW. Risk: **NEUTRAL** (docs).

---

## PART 3 — SEQUENCING

The rule from the gap analyses: **the coverage/corroboration systemic fixes gate BOTH boards → land first for leverage; the two over-claims D1/D2 are clinical-safety → land first for safety.** Both sets go in the opening wave because they are independent and D1/D2 are cheap render fixes.

**WAVE A — unblock + safety (land together, first):**
- WS-0 (GPU device-split) and WS-1 (kimi-k2.6 judge + enum + retry + idempotency) — TIER 0, gate everything.
- WS-5 (D1) and WS-6 (D2) — clinical over-claims, render-layer, cheap; validatable on a **banked corpus_snapshot replay**.
- These four are the mandatory floor. WS-0/WS-1 are prerequisites for the winners to fire un-degraded; WS-5/WS-6 are the patient-safety priority.

**WAVE B — turn the machine on (depends on Wave A):**
- WS-2 (full winner slate on the paid path + fail-loud slate-ON preflight), WS-3 (breadth surface + no_token repair), WS-13 (retrieval wall), WS-4 (D5 coverage credit — un-holds the D8 release gate).
- WS-14 measurement track runs in parallel (build the B1 scorer + wire B2 `run_evaluation.py`).

**WAVE C — render polish + disclosure + genre (parallel with late Wave B):**
- WS-7 (D3 prose chrome), WS-8 (D4 genre weight), WS-9 (D6 disclosure coherence), WS-12 (quantified repair), WS-16 (docs).
- **WS-7 and WS-8 require the FRESH front-half run** (banked replay is structurally blind to a truncation fix and a retrieval-time genre re-rank).

**WAVE D — new builds for the DeepTRACE top slot:**
- WS-10 (Source Necessity module), WS-11 (debate router).

**WAVE E — frontier coverage lead (stretch, after a passing acceptance run):**
- WS-15 (TTD-DR loop), multi-hop retrieval.

**Parallelism mandate (§ runtime-parallelism):** Waves A–D are authored as bounded-parallel Claude Codex Workflow build agents grouped by file-owner to avoid `run_honest_sweep_r3.py` write collisions (it is touched by WS-2/4/6/8/9 — single-writer that file). Each PR ships a fail-loud behavioral replay-harness assertion (§-1.4). Each gate runs Codex as the only reviewer, iter-5 cap.

---

## PART 4 — ACCEPTANCE GATE

A workstream is DONE only when the effect **behaviorally fires in the real rendered output** (§-1.4), not when committed+green+Codex-approved. The program is DONE when a single fresh run clears every clause below.

**GATE-RUN configuration:**
- **One fresh full run on the A100** (stable, high-VRAM, no GPU-OOM degrade — WS-0 confirmed non-degraded in the manifest: `w2_mode=semantic` not lexical, `consolidation_mode=gpu` not cpu-wall, `tiering_mode≠rules_floor_degraded`).
- **Stable non-GLM judge** (kimi-k2.6, `structured_outputs`-enforced, two-family segregation ON) — manifest shows zero `JudgeEnumError`/`RoleTransportError` degrades.
- **Full winner slate ON** — preflight asserts `PG_CONSOLIDATION_NLI=PG_CROSS_SOURCE_SYNTHESIS=PG_BREADTH_ENRICHMENT_ENABLED=1`; a run with the slate OFF **cannot launch**.
- Must **COMPLETE and RENDER** (the false-PASS class: a banked replay cannot validate D3/D4/the truncation fix — this must be a fresh front-half run).

**GATE clauses (all must pass):**
1. **All 6 residuals gone, proven by fail-loud replay assertions:** D1 (no clean caveat-stripped numeric twin — every byte-twin of a low-confidence claim carries the marker), D2 (no "N verified" where `verified_support_origin_count<N`), D3 (prose-inclusive chrome canary `chrome_rate=0` over all rendered sentences, not just bullets), D4 (no non-journal/pre-AI source in the headline slots when the question constrains genre), D5 (`coverage_fraction` reflects verified topic entities, no present-and-disown contradiction), D6 (contradiction count == `manifest.contradictions_found`; every weight carries `weight_basis`).
2. **§-1.1 line-by-line clinical audit clean** — Claude AND Codex independent parallel audits, per-claim VERIFIED/PARTIAL/UNSUPPORTED/FABRICATED with cited-span quotes; 0 fabrication; 0 over-claim.
3. **Run-level health:** ≥2-origin corroboration behind the majority of cited claims (§-1.3 basket-consolidation fired — `finding_dedup` distribution no longer `{1:56,0:2,2:1}`); cited count is a large fraction of the classified corpus, not 12/88; `release_allowed=True`; zero silent no-ops (`quantified_silent_no_op=false`).
4. **Scored on both official harnesses:** DRB-II `run_evaluation.py` **Total ≥ 66** (InfoRecall ≥63, Analysis ≥70, Presentation ≥90); DeepTRACE re-impl **Unsupported ≤5, Citation-Accuracy ≥90, Thoroughness ≥88, Necessity ≥88, Uncited ≤1, One-Sided single-digit, Overconfident 0.** Cross-check B5 FACT and submit B3 DeepScholar + B4 ResearchQA subset.

---

## PART 5 — HONEST RISKS + what could still block #1

**Measurement risks (could make a "win" unverifiable):**
- **B1 DeepTRACE has no public scorer and defaults to a GPT-5 judge.** Our re-implementation may not match official numbers, and if we cannot run GPT-5 as the judge, the scores are self-graded — a claim reviewers can contest. Mitigation: match the judge where possible, disclose any substitution, validate our scorer against the paper's published GPT-5-DR column, publish the human-validation Pearson.
- **B3/B4/B5** require harness builds + a DeepScholar submission form; DeepScholar refreshes monthly (a rank can move under us).

**Coverage-ceiling risk (the real threat to B2 #1):**
- Flag-flips (WS-2/3/13/4) fix a *degraded* run, but the gap map is explicit that beating AI21's 64.38 defensibly is **architectural** — without **WS-15 TTD-DR** and multi-hop, POLARIS may land in the ~contention band (low-60s recall) rather than a clear 66-68. Flag-flips are necessary, not sufficient, for a durable #1 on coverage. Budget WS-15.
- The 2nd-order-fact / multi-hop DRB-II rubrics stay uncovered until reasoning-driven retrieval exists.

**Judge / faithfulness-adjacent risks:**
- **kimi-k2.6 must hold two-family segregation** vs the deepseek-v4-pro generator, and 21 providers may still 429 under ~178 judge calls/report. If it tears, the false-negative class returns. Mitigation: bounded retry + idempotency cache (WS-1) + the 1800s seam wall for a slow judge.
- WS-1, WS-5, WS-4 are faithfulness-adjacent. They are safe-direction by construction, but each needs an independent Codex gate confirming no gate was relaxed.

**Composition risk (the hardest DeepTRACE metric):**
- **One-Sided / Overconfident (WS-11)** is a composition mandate, the least de-risked workstream, and no competitor renders span-grounded pro+con. If the debate router misfires, POLARIS still beats the field's 48.7 only marginally, not to single digits.

**Architecture-DNA risks:**
- Turning on all winners at once could interact badly (the slate is tested in fire-tests but not always jointly under real upstream). A misfire is expected per the 14-winners wiring standard — budget for it; acceptance is the fresh e2e effect, not a snapshot.
- **Necessity/Uncited orientation (WS-10):** point the scorer at the 12-source citation list, not the 88-corpus disclosure, or a real win reads as a catastrophic loss.
- **§-1.3 tripwire:** if any workstream starts adding a cap/floor/thinner to force a breadth number (e.g. a hard journal filter instead of a weight), that is the banned day-waster — WS-8 stays a WEIGHT, WS-3 stays keep-all, `PG_JOURNAL_ONLY` stays OFF.

**Presentation is a non-lever:** DRB-II Presentation is saturated (12/16 >89); do not spend cycles chasing it — it cannot move the rank.

**Bottom line:** POLARIS is already built to win the **DeepTRACE faithfulness axis (B1)** — span-grounding, provenance tokens, 4-role D8, multi-source baskets, contradiction detectors, the blocked-reference registry — and B1 is the most winnable board because the field sits at 40-80% citation accuracy. The deficit is the **DeepResearch-Bench-II coverage axis (B2)**, and it is architectural (winners shipped OFF + GPU-degraded + off-vLLM judge + no draft loop), not a faithfulness problem — so every fix above is a WEIGHT, a CONSOLIDATION, a surfacing, a disclosure, or a degrade-fix, and the frozen faithfulness engine (strict_verify / NLI / 4-role D8 / provenance / span-grounding) is never touched. Turn the machine on in order (Tier 0 → Tier 1), close the six residuals surgically with D1/D2 first for patient safety, build the two new modules for the DeepTRACE top slot, then add the TTD-DR loop to convert coverage-contention into a defensible clear #1.
---
# APPENDIX A — DeepTRACE research
Data locked. Delivering the DeepTRACE deep-dive. Note: I corrected two things your brief had wrong — the lab (Salesforce AI Research, not Microsoft) and the judge (GPT-5 default), and I flag one orientation subtlety on the Uncited-Sources metric that would otherwise get wired backwards.

---

# DeepTRACE — deep-dive (arXiv 2509.04499, v1, 2 Sep 2025)

**Paper:** "DeepTRACE: Auditing Deep Research AI Systems for Tracking Reliability Across Citations and Evidence."
**Authors / lab (CORRECTION to your brief):** Pranav Narayanan Venkit, Yilun Zhou, Kung-Hsiang Huang, Yixin Mao, Chien-Sheng Wu — **Salesforce AI Research** (Palo Alto); Philippe Laban — **Microsoft Research** (NYC). Your `BENCHMARKS_STUDY.md` line 14 says "Microsoft Research" as the owner — that is wrong; it is Salesforce-led with one MSR co-author. Fix that line.
**Venue:** accepted / featured at **ICLR 2026** (per Salesforce AI Research ICLR-2026 blog). Only **v1** exists on arXiv; **no v2, no DeepTRACE-2**.
**Code / leaderboard:** paper says "we release the DeepTrace dataset" but ships **no public URL**. No official GitHub or leaderboard is live as of today. (`github.com/convexsoft/deeptrace` and `deeptrace.com` are unrelated name-collisions — do not use.)
**Scope evaluated:** **303 queries** (168 debate from ProCon.org + 135 expertise, contributor-submitted) × 9 systems = **2,727 audited samples**, run ~27 Aug 2025.

---

## (a) The 8 metrics — exact definitions + formulas (confirmed / corrected vs your summary)

Notation: **C** = Citation Matrix (statements × sources, binary: statement s cites source j). **S** = Factual-Support Matrix (binary: does source j actually support statement s, per LLM-judge). ⊙ = element-wise product. Σ sums all matrix cells.

**1. One-Sided Answer** (binary; debate queries only). `= 1` if the answer does NOT contain BOTH a pro and a con statement, else `0`. Lower = better. *(Your summary correct.)*

**2. Overconfident Answer** (binary; debate queries only). `= 1` iff One-Sided `= 1` AND confidence `= 5` (max on a 1–5 Likert). Lower = better. *(Your summary correct.)*

**3. Relevant Statement ratio** `= (# relevant statements) / (# total statements)`. Penalises filler intro/conclusion/off-point prose. Higher = better. *(Correct.)*

**4. Uncited Sources ratio** — **ORIENTATION CAUTION.** The table column reported is **`% Uncited Sources = (# uncited listed sources) / (# listed sources)`**, LOWER = better, ideal 0 (empty columns of **C** = sources listed but never cited = padding). Your `BENCHMARKS_STUDY.md` line 20 writes the formula as "cited/listed" AND names it "Uncited Sources" — those two disagree with each other. The table proves the correct reading is the *uncited* fraction (GPT-4.5 = 0.0 = all listed sources cited = best; YouChat-DR = 66.3 = two-thirds of listed sources never cited = worst). **Wire it as uncited/listed, lower-is-better**, or you will invert the metric.

**5. Unsupported Statements ratio** `= (# unsupported relevant statements) / (# relevant statements)`. A relevant statement is "unsupported" if its row in **S** has no checked cell. Lower = better. This is the core faithfulness hole. *(Correct.)*

**6. Source Necessity ratio** `= (# necessary sources) / (# listed sources)`. **S** is turned into a bipartite graph; **Hopcroft–Karp** finds the minimum vertex cover = the smallest source set that still covers all supported statements; sources in it are "necessary." Higher = better (sources are load-bearing, not padding). *(Correct.)*

**7. Citation Accuracy** `= Σ(C ⊙ S) / Σ(C)`. Of all citations the system made, the fraction that are actually support-valid. Higher = better. *(Correct.)*

**8. Citation Thoroughness** `= Σ(C ⊙ S) / Σ(S)`. Of all the genuine support that existed, the fraction the system actually cited. Higher = better. *(Correct.)*

---

## (b) Official scoring method + judge

- **Pipeline:** decompose answer into atomic **statements** → per statement label {query-relevant?, pro/con?} and an answer-level **confidence 1–5** → build binary **C** (statement×source citations) and **S** (LLM-judge: does source support statement?) → compute the 8 metrics from C, S, and the min-vertex-cover.
- **Judge model:** **GPT-5 is the default** LLM-judge for decomposition, relevance, pro/con, support labelling, and confidence. **GPT-4o** appears only in validation cross-checks. (Your brief's "GPT-5/4o" is right; GPT-5 is primary.)
- **Human validation:** 100 tasks manually annotated per metric by **4 annotators** (professional annotators or CS grad students, $25/hr). Agreement: **Pearson 0.72** on confidence scoring (substantial), **Pearson 0.62** on factual support (moderate).
- **Headline aggregate finding:** across all systems, on average only **~51.5% of generated sentences are fully supported** by their own cited sources.

---

## (c) Published competitor scores (verbatim from the paper's two result tables)

**Generative search engines** (%, except Avg rows):

| Metric | You.com | BingChat | Perplexity | GPT-4.5 |
|---|---|---|---|---|
| One-Sided ↓ | 51.6 | 48.7 | 83.4 | 90.4 |
| Overconfident ↓ | 19.4 | 29.5 | 81.6 | 70.7 |
| Relevant Stmt ↑ | 75.5 | 79.3 | 82.0 | 85.4 |
| Uncited Sources ↓ | 1.1 | 36.2 | 8.4 | 0.0 |
| Unsupported ↓ | 30.8 | 23.1 | 31.6 | 47.0 |
| Source Necessity ↑ | 69.0 | 50.4 | 68.9 | 67.3 |
| Citation Accuracy ↑ | 68.3 | 65.8 | 49.0 | 39.8 |
| Citation Thoroughness ↑ | 24.4 | 20.5 | 23.0 | 23.8 |
| Avg sources | 3.5 | 4.0 | 3.4 | 3.4 |
| Avg statements | 13.9 | 10.5 | 18.8 | 12.0 |

**Deep-research agents** (%, except Avg rows). DR = Deep Research, TD = Think Deeper, S = Web Search:

| Metric | GPT-5(DR) | YouChat(DR) | PPLX(DR) | Copilot(TD) | Gemini(DR) | GPT-5(S) |
|---|---|---|---|---|---|---|
| One-Sided ↓ | 54.67 | 63.1 | 63.1 | 94.8 | 80.1 | 69.7 |
| Overconfident ↓ | 15.2 | 19.6 | 5.6 | 0.0 | 11.2 | 16.4 |
| Relevant Stmt ↑ | 87.5 | 45.5 | 22.5 | 13.2 | 12.4 | 41.1 |
| Uncited Sources ↓ | 0.0 | 66.3 | 57.5 | 32.6 | 14.5 | 51.7 |
| Unsupported ↓ | 12.5 | 74.6 | 97.5 | 90.2 | 53.6 | 58.9 |
| Source Necessity ↑ | 87.5 | 63.2 | 5.5 | 31.2 | 33.1 | 32.8 |
| Citation Accuracy ↑ | 79.1 | 72.3 | 58.0 | 62.1 | 50.3 | 31.4 |
| Citation Thoroughness ↑ | 87.5 | 83.5 | 9.1 | 13.2 | 27.1 | 17.9 |
| Avg sources | 18.3 | 57.2 | 7.7 | 3.6 | 33.2 | 13.5 |
| Avg statements | 141.6 | 52.7 | 30.1 | 36.7 | 23.9 | 34.9 |
| Citations/stmt | 1.4 | 0.8 | 0.2 | 0.3 | 0.2 | 0.4 |

Paper's read of these numbers: deep-research configs cut overconfidence and can hit high citation-thoroughness, **but stay heavily one-sided on debate and carry huge unsupported fractions**; more sources + longer answers do NOT buy reliability. **GPT-5(DR) is the clear per-metric leader** (concise, selectively cites directly-supporting sources). Perplexity is worst on one-sidedness (83.4% as a search engine) and PPLX(DR) is worst on unsupported (97.5%).

---

## (d) + summary table — metric | formula | best competitor | ideal (= what #1 requires)

| Metric | Formula | Best competitor score (system) | Ideal / #1 target |
|---|---|---|---|
| One-Sided ↓ | 1 if not(pro ∧ con) | **48.7% BingChat** (DR-class best 54.67 GPT-5-DR) | **0%** — always render both sides on debate |
| Overconfident ↓ | 1 if one-sided ∧ conf=5 | **0.0% Copilot-TD** | **0%** — never max-confidence while one-sided |
| Relevant Statement ↑ | relevant / total | **87.5% GPT-5-DR** | **100%** — no filler; every statement on-point |
| Uncited Sources ↓ | uncited / listed | **0.0% GPT-4.5 & GPT-5-DR** | **0%** — every listed source is cited |
| Unsupported ↓ | unsupported / relevant | **12.5% GPT-5-DR** | **0%** — every relevant statement backed by a supporting source |
| Source Necessity ↑ | necessary / listed (min-vertex-cover) | **87.5% GPT-5-DR** | **100%** — no padding sources |
| Citation Accuracy ↑ | Σ(C⊙S)/Σ(C) | **79.1% GPT-5-DR** | **100%** — every citation support-valid |
| Citation Thoroughness ↑ | Σ(C⊙S)/Σ(S) | **87.5% GPT-5-DR** | **100%** — cite all the support that exists |

**To be #1 outright, POLARIS must beat GPT-5-Deep-Research on the six it leads** (Relevant 87.5, Unsupported 12.5, Necessity 87.5, Cite-Acc 79.1, Thoroughness 87.5, Uncited 0.0) AND beat BingChat/Copilot on the two debate-balance metrics (One-Sided → below 48.7, ideal 0; Overconfident → 0). The realistic beat-both edge for POLARIS is **Unsupported, Citation Accuracy, Citation Thoroughness, and Uncited/Necessity** — those map directly to span-grounded `strict_verify` + provenance tokens + multi-source baskets (every listed source attached to a claim = 0% uncited, high necessity). The hardest for POLARIS is **One-Sided/Overconfident**: they require the composer to actively render pro AND con on debate prompts — a composition mandate, not a retrieval one.

---

## (e) Updates / v2

None. arXiv **v1 only**; ICLR-2026 accepted; **no v2, no leaderboard, no released code URL** as of 2026-06-30. If you want an official-comparable score you must **re-implement the pipeline** (statement decomposition + C/S matrices + Hopcroft–Karp necessity + GPT-5 judge) yourself — there is no drop-in scorer to run, unlike DeepResearch-Bench-II which ships `run_evaluation.py`. Budget an internal DeepTRACE re-implementation as a work item; the 8 formulas above are complete enough to build it exactly.

**Sources:** [arXiv abs 2509.04499](https://arxiv.org/abs/2509.04499) · [arXiv HTML full text](https://arxiv.org/html/2509.04499) · [arXiv PDF](https://arxiv.org/pdf/2509.04499) · [OpenReview QkaeTea16Y](https://openreview.net/forum?id=QkaeTea16Y) · [Salesforce AI Research @ ICLR 2026](https://www.salesforce.com/blog/salesforce-iclr-2026/) · [TechXplore coverage](https://techxplore.com/news/2025-09-ai-tools-unreliable-overconfident-sided.html) · [Semantic Scholar record](https://www.semanticscholar.org/paper/c5f2f38383a3d4ee018703c7d723c0efe91caca3)
# APPENDIX B — DeepResearch-Bench-II research
# DeepResearch-Bench-II (DRB-II) — Deep-Dive Findings

Sources fetched 2026-06-30: [github.com/imlrz/DeepResearch-Bench-II](https://github.com/imlrz/DeepResearch-Bench-II) · [arXiv 2601.08536](https://arxiv.org/abs/2601.08536) (v1 submitted 2026-01-13, revised 2026-01-30) · [live leaderboard agentresearchlab.com](https://agentresearchlab.com/benchmarks/deepresearch-bench-ii/index.html#leaderboard) · [arXiv HTML full text](https://arxiv.org/html/2601.08536). Paper title: *"DeepResearch Bench II: Diagnosing Deep Research Agents via Rubrics from Expert Reports."* Authors: Ruizhe Li, Mingxuan Du, Benfeng Xu, Chiwei Zhu, Xiaorui Wang, Zhendong Mao (USTC / Agent Research Lab). Dataset: HuggingFace `muset-ai/DeepResearch-Bench-II-Dataset`.

---

## (a) Rubric method + blocked-reference scoring + formulas + per-dimension weighting — CONFIRMED, with one honest correction

**Scale.** 132 expert-grounded research tasks across 22 domains → **9,430 fine-grained rubrics** (paper's current count; the operator study file's 9,415 is the earlier count — minor drift, same benchmark). Each rubric is essential, atomic, content-bearing, numerically precise, decomposed from a real expert-written report.

**Per-dimension rubric counts / natural weighting.** The paper reports per-task averages (§Appendix A.2), which set the effective weighting:

| Dimension | Rubrics/task (avg) | ~Total rubrics | Effective weight |
|---|---|---|---|
| Information Recall | 52.902 | ~6,983 | **~74%** |
| Analysis | 12.773 | ~1,686 | **~18%** |
| Presentation | 5.652 | ~746 | **~8%** |

So the operator study file's **74% / 18% / 8%** is confirmed — but it is NOT an explicit weighted-average coefficient. The weighting is **emergent from pooling**: TotalScore counts passed rubrics across the whole pooled set, and because recall rubrics outnumber the rest ~4:1, recall dominates ~74% by construction. (Verified numerically: pooling the per-dimension column scores by these weights reproduces each system's TotalScore to within ~0.3–0.5 pt — the small residual is macro- vs micro-averaging, not a hidden coefficient.)

**Scoring — the one correction to the study file.** The paper's *primary* scheme is **binary 0/1**: "each rubric is scored independently using a binary scheme (0/1)… marked passed only if the report satisfies the requirement." The **blocked-reference / leakage mechanism is a separate demotion layer**: each rubric was derived from a specific source article, which is "blocked." On secondary inspection, *"if a report referenced the source article and correctly answered a question, we excluded that from the score and recorded the leakage rate."* So the study file's **`-1`** is the operator's shorthand for the **leaked-and-excluded** case. Reconciled honestly:
- **1** = rubric satisfied with valid, INDEPENDENT (non-blocked) evidence → counts as a pass.
- **0** = not mentioned / not satisfied.
- **-1 (paper: "leaked, excluded")** = satisfied only by citing the blocked source article → **does not earn credit**; recorded as leakage.

Net effect is identical to the study file's intent: a single-source-leaked answer earns no credit, which **forces independent multi-source retrieval + cross-check.** Judge model: **Gemini-2.5-Pro** (§4.1.1), scoring in batches.

**Formulas.**
- `TotalScore (task) = (#rubrics passed) / (#total rubrics)` → the pooled RECALL fraction of expert facts independently covered.
- `blocked_rate / leakage_rate = fraction of otherwise-satisfied rubrics that were supported ONLY by the blocked source` (recorded in Appendix D as a diagnostic).

**Honest gap in the public data:** `blocked_rate` is a **paper-appendix diagnostic, NOT a published per-system leaderboard column.** The live leaderboard exposes only InfoRecall / Analysis / Presentation / TotalScore. Per-system blocked_rate values are **UNREACHABLE** from the leaderboard and were not extractable from the fetched HTML (Appendix D tables are figure/compressed). The *mechanism* is confirmed; the *per-system numbers* are not public.

---

## (b) Current leaderboard (live, agentresearchlab.com, as fetched 2026-06-30)

**#1 = AI21-DeepResearch (AI21 Labs), TotalScore 64.38.** 16 systems ranked. blocked_rate not published per-system (column absent → "n/p").

| # | System | Total | Recall | Analysis | Presentation | blocked_rate |
|---|---|---|---|---|---|---|
| 1 | **AI21-DeepResearch** (AI21 Labs) | **64.38** | 60.35 | 71.00 | 92.89 | n/p |
| 2 | Dalpha DeepResearch (Dalpha) | 61.01 | 58.62 | 61.36 | 93.41 | n/p |
| 3 | WhaleCloud-DocChain (WhaleCloud) | 60.94 | 57.20 | 64.91 | 92.59 | n/p |
| 4 | iFlow-Researcher (NJU & Alibaba) | 59.91 | 54.99 | 69.54 | 92.56 | n/p |
| 5 | Xiaoyi DeepResearch 6.0 (Huawei) | 58.72 | 53.05 | 69.90 | 91.12 | n/p |
| 6 | Octen Deep Research (Octen AI) | 55.58 | 50.14 | 61.39 | 94.42 | n/p |
| 7 | CMCC-DeepInsight (China Mobile) | 55.39 | 49.60 | 62.95 | 92.94 | n/p |
| 8 | nvidia-aiq (NVIDIA) | 54.50 | 49.23 | 61.55 | 93.15 | n/p |
| 9 | OpenAI GPT-o3 Deep Research | 45.40 | 39.98 | 49.85 | 89.16 | n/p |
| 10 | Gemini-3-Pro Deep Research | 44.60 | 39.09 | 48.94 | 91.85 | n/p |
| 11 | Gemini-2.5-Pro Deep Research | 41.98 | 34.91 | 51.91 | 90.24 | n/p |
| 12 | Doubao Deep Research (ByteDance) | 40.99 | 34.83 | 49.43 | 83.51 | n/p |
| 13 | Qwen3-Max Deep Research (Alibaba) | 39.25 | 34.18 | 48.04 | 74.59 | n/p |
| 14 | Grok Deep Search (xAI) | 39.23 | 33.52 | 42.50 | 91.42 | n/p |
| 15 | Perplexity Research (Perplexity) | 38.58 | 33.05 | 44.47 | 79.34 | n/p |
| 16 | Tongyi Deep Research (Alibaba) | 29.89 | 22.95 | 35.89 | 86.13 | n/p |

**Critical nuance — "under 50%" is stale for the top of the board.** The paper's headline ("even the strongest agents fail to pass >50% of rubrics") was true for the model set evaluated AT PAPER TIME (Jan 2026): the best there was **OpenAI o3 DR at 45.40**. The **live leaderboard has since added specialized/enterprise DR systems (AI21, Dalpha, WhaleCloud, iFlow, Xiaoyi, Octen, CMCC, NVIDIA) that all exceed 50%**, topping at 64.38. Every well-known Western consumer DR product sits in the **38–45 band (#9–#15)** — ~19–20 points BELOW the leader. The board is currently led by purpose-built enterprise/Chinese DR agents, not the famous general assistants.

---

## (c) Gap between #1 and the field

- **Top cluster is tight:** #1 → #4 spans only **64.38 → 59.91 = 4.5 pts**; #1 over #2 is **3.37 pts**.
- **Full spread:** #1 → #16 = **64.38 → 29.89 = 34.49 pts**.
- **Recall is the entire battle.** InfoRecall (74% weight) spans **22.95 → 60.35 (37.4 pt spread)** — the widest and most discriminating axis. Analysis spans 35.89 → 71.00. **Presentation is saturated and near-useless as a differentiator**: 12 of 16 systems score >89, cluster 90–94; it can't separate leaders (only Qwen3-Max 74.59 and Perplexity 79.34 are penalized there). Translation: **you win DRB-II on Recall first, Analysis second; Presentation is table-stakes.**
- **The famous-vs-leader gap:** OpenAI o3 DR (best-known, #9) trails #1 by **18.98 pts**, driven almost entirely by recall (39.98 vs 60.35 = **20.4 pt recall deficit**). Their analysis and presentation are already competitive (49.85/89.16); their retrieval breadth is what's missing.

---

## (d) What score makes POLARIS #1

**Outright #1 requires TotalScore > 64.38 → target ~66–68 for a clear, defensible lead** (not a photo-finish over AI21's 64.38).

Because `Total ≈ 0.74·Recall + 0.18·Analysis + 0.08·Presentation`, and Presentation is trivially reachable at ~92 (deterministic structured render), the lever is **Recall**. Concrete target profile:

| Dimension | Needed for Total ≈ 66 | Current #1 (AI21) |
|---|---|---|
| **InfoRecall** | **≈ 63–65** | 60.35 |
| Analysis | ≈ 70 | 71.00 |
| Presentation | ≈ 92 | 92.89 |

Check: 0.74·64 + 0.18·70 + 0.08·92 = 47.4 + 12.6 + 7.4 = **67.4** → clear #1. To merely *tie* the top you need **InfoRecall ≈ 60–61 + Analysis ≈ 70 + Presentation ≈ 92**.

**Structural fit for POLARIS — this benchmark rewards exactly POLARIS's DNA:**
- **The blocked-reference mechanism REWARDS weight-and-consolidate multi-source baskets.** Single-source systems get their leaked rubrics demoted (the "-1"); POLARIS's **multi-source basket corroboration provides independent, non-blocked evidence**, so it dodges the leakage penalty that caps everyone else. This is the single biggest architectural advantage on this specific board.
- **Recall (74%) is where POLARIS's 300–600-source breadth architecture must convert** — the known gap (per the study file) is facts retrieved-but-not-composed. Surfacing the full basket set as rubric-satisfying statements (RC-E synthesis + weighted_enrichment surfacing the full SUPPORTS basket) is the direct lever from ~40-recall to ~63-recall.
- **Analysis (18%)** is POLARIS's second build target (synthesis layer, ~70 to match leaders).
- **Presentation (8%)** — deterministic structured render already lands ~90+; do not over-invest here, it can't move the ranking.

**Bottom line: POLARIS is #1 when it clears ~65 TotalScore, and the make-or-break sub-metric is InfoRecall ≈ 63+.** Everything else (analysis ~70, presentation ~92) is either already in reach or table-stakes.

---

## (e) DeepResearch-Bench v1 (arXiv 2506.11763) — still tracked, and how it differs

**Yes, v1 is still active and maintained.** [DeepResearch Bench (v1)](https://arxiv.org/abs/2506.11763), submitted 2025-06-13, **accepted to ICLR 2026**, live leaderboard at [agentresearchlab.com/benchmarks/deepresearch-bench](https://agentresearchlab.com/benchmarks/deepresearch-bench/index.html) and [deepresearch-bench.github.io](https://deepresearch-bench.github.io/), repo [Ayanami0730/deep_research_bench](https://github.com/Ayanami0730/deep_research_bench) — still updated with 2026 models. (I could not extract the current v1 top-N scores; the leaderboard table is JS-rendered and did not serialize — that specific ranking is **UNREACHABLE** from the fetches, flagged honestly rather than guessed.)

**What v1 is:** 100 PhD-level tasks across 22 fields, evaluated by two frameworks:
- **RACE** (Reference-based Adaptive Criteria-driven Evaluation): a **reference-based method with task-adaptive, LLM-generated criteria** scoring report quality (comprehensiveness / insight / instruction-following / readability), judge-aligned to human preference.
- **FACT** (Factual Abundance and Citation Trustworthiness): measures **effective citation count + citation accuracy** — the faithfulness axis.

**How v1 differs from DRB-II (why DRB-II is the harder, better target):**

| | v1 (2506.11763) | DRB-II (2601.08536) |
|---|---|---|
| Tasks | 100 PhD tasks | 132 expert-report-grounded tasks |
| Scoring | RACE = adaptive LLM-generated criteria (holistic, per-task weighted) + FACT citation metrics | Fixed **expert-authored atomic binary rubrics** (9,430) decomposed from real expert reports |
| Anti-leakage | none | **blocked-reference mechanism** forces independent multi-source retrieval |
| Focus | report quality + citation trust (subjective, criteria-driven) | **recall of specific expert facts** (objective, diagnostic, recall-heavy) |
| Judge | Gemini-based | Gemini-2.5-Pro |
| Relationship | original benchmark | **successor** — "stronger focus on the gap to human experts," harder recall bar |

**For POLARIS's two-benchmark program:** v1's **FACT (citation accuracy / effective citations)** overlaps DeepTRACE's faithfulness axis and is a secondary coverage cross-check, but **DRB-II is the primary COVERAGE target** because its blocked-reference mechanism structurally rewards POLARIS's multi-source-basket design and its recall-dominated rubric weighting matches the exact axis POLARIS is built to win.

Sources: [github.com/imlrz/DeepResearch-Bench-II](https://github.com/imlrz/DeepResearch-Bench-II) · [arXiv 2601.08536](https://arxiv.org/abs/2601.08536) · [arxiv.org/html/2601.08536](https://arxiv.org/html/2601.08536) · [agentresearchlab.com DRB-II leaderboard](https://agentresearchlab.com/benchmarks/deepresearch-bench-ii/index.html) · [arXiv 2506.11763 (v1)](https://arxiv.org/abs/2506.11763) · [deepresearch-bench.github.io](https://deepresearch-bench.github.io/) · [github.com/Ayanami0730/deep_research_bench](https://github.com/Ayanami0730/deep_research_bench).
# APPENDIX C — Other boards research
# 2025–2026 Deep-Research Benchmark & Leaderboard Landscape — Full Survey + Target-Board Recommendation

Scope: every public benchmark/leaderboard a citation-faithful, long-form deep-research agent should weigh for a SOTA claim. Ranked by strategic value to POLARIS (citation-grounded long-form research with span provenance + multi-source baskets; edge = faithfulness, gap = coverage). "Chase" = pursue #1; "prove-component" = use to validate one module; "ignore" = wrong axis.

## Strategic-value ranking (one line each)

| Rank | Benchmark | Axis | Fit to POLARIS | Verdict |
|---|---|---|---|---|
| 1 | DeepTRACE (2509.04499) | Citation faithfulness | Direct — our edge | CHASE #1 |
| 2 | DeepResearch Bench II (2601.08536) | Coverage (recall/analysis/present) | Direct — our gap | CHASE #1 |
| 3 | DeepScholar-Bench (2508.20033) | Synthesis + retrieval + verifiability, live | Direct, publishable slot | CHASE #1 |
| 4 | ResearchQA (2509.00496) | Long-form scholarly QA, citation rubrics | Direct — field at <11% citation, wide open | CHASE #1 |
| 5 | DeepResearch Bench v1 — FACT leg (2506.11763) | Citation accuracy + effective count | Direct — established HF board | CHASE #1 (FACT), track RACE |
| 6 | ResearchRubrics (2511.07685, ICLR 2026) | Prompt+rubric DR eval | Direct, Scale AI credibility | CHASE / register |
| 7 | Mind2Web 2 (2506.21506) | Agentic search + source attribution | Adjacent — scores attribution | PROVE-COMPONENT |
| 8 | FACTS Grounding (2501.03200 / v2) | Grounding to provided long docs | Adjacent — closed-book grounding | PROVE-COMPONENT (badge) |
| 9 | BrowseComp-Plus (texttron, ACL 2026) | Retrieval-isolated deep research | Adjacent — proves retriever | PROVE-COMPONENT |
| 10 | RAGChecker (NeurIPS 2024) | Claim-level RAG diagnostics | Internal harness | INTERNAL TOOL |
| 11 | FRAMES (2409.12941) | RAG factuality+retrieval+reasoning | Component regression | INTERNAL/PROVE |
| 12 | BrowseComp (OpenAI, Apr 2025) | Hard-to-find web browsing | Wrong shape (needle-hunt) | IGNORE for #1 |
| 13 | GAIA (2311.12983) | General assistant tool-use | Wrong axis (agentic exam) | IGNORE |
| 14 | HLE (2501.14249) | Frontier reasoning exam | Wrong axis (parametric reasoning) | IGNORE |
| 15 | SimpleQA / SimpleQA-Verified | Short parametric factuality | Anti-fit (closed-book) | IGNORE |
| 16 | WebArena / Mind2Web v1 | Web-action execution | Wrong axis | IGNORE |
| — | DREAM, DR-Arena, DeepResearchEval, MiroEval, JADE, SurveyBench, PaperArena | 2026 eval frameworks | Emerging | WATCH |

---

## TIER S — CHASE FOR #1 (direct fit: citation-grounded long-form research)

### 1. DeepTRACE — CITATION FAITHFULNESS
- **Source:** arXiv 2509.04499, Microsoft Research, Sept 2025. (Note: deeptrace.com is an unrelated SaaS — use the paper.)
- **Measures:** 8 statement-level metrics on answer/sources/citations — one-sided, overconfident, relevant-statement ratio, uncited-sources, unsupported-statements, source-necessity (min-vertex-cover), citation accuracy = Σ(Cite⊙Support)/Σ(Cite), citation thoroughness = Σ(Cite⊙Support)/Σ(Support). GPT-5/4o judge, human-validated (Pearson 0.72 confidence, 0.62 support).
- **Who leads:** No single public leaderboard number — published finding is that ALL audited deep-research systems (GPT-4.5/5, Perplexity, You.com, Copilot, Gemini) sit at **citation accuracy 40–80%**, one-sided on debate, large unsupported fractions. The bar is beatable.
- **POLARIS fit:** Highest. Span-grounding + provenance tokens + multi-source baskets map 1:1 to metrics #5/#7/#8; contradiction edges (pro/con) attack #1/#2. This is the single most winnable board because the field is weak here and it is exactly what POLARIS is built to do.

### 2. DeepResearch Bench II — COVERAGE
- **Source:** arXiv 2601.08536 (Jan 2026, USTC-CMI / Agent Research Lab); GitHub imlrz/DeepResearch-Bench-II; leaderboard agentresearchlab.com. 132 tasks / 22 domains / **9,430 binary rubrics** (Info Recall 74% + Analysis 18% + Presentation 8%). Gemini-2.5-pro judge; blocked-reference mechanism scores −1 on leakage, forcing independent multi-source retrieval.
- **Who leads (current board):** **AI21-DeepResearch — Total 64.38%** (InfoRecall 60.35, Analysis 71.00, Presentation 92.89). Then Dalpha 61.01, WhaleCloud-DocChain 60.94, iFlow-Researcher 59.91, Xiaoyi 6.0 (Huawei) 58.72. Presentation is near-saturated (~92%); **InfoRecall is where rank is won or lost (~53–60%)**.
- **POLARIS fit:** Highest — this is the operator-chosen coverage axis. The blocked-ref anti-leakage rewards POLARIS multi-source baskets. Gap is surfacing retrieved facts as rubric-satisfying statements (composition/synthesis).

### 3. DeepScholar-Bench — LIVE synthesis + retrieval + verifiability
- **Source:** arXiv 2508.20033 (Aug 2025, Guestrin Lab / Stanford); GitHub guestrin-lab/deepscholar-bench; **live leaderboard** guestrin-lab.github.io/deepscholar-leaderboard. Task = generate a related-work section by retrieving + synthesizing + citing prior work from recent high-quality arXiv papers. **Monthly-refreshed, anti-contamination.** Three axes: knowledge synthesis, retrieval quality, verifiability. 14 baselines evaluated (STORM, OpenScholar, DeepScholar-ref, search agent) on Llama-4-Scout.
- **Who leads:** Open baselines only so far — no frontier DR system has been submitted, so **the leaderboard has an open top slot** (submission via form).
- **POLARIS fit:** Very high and strategically cheap. "Verifiability" = our provenance edge; it is live (defends against "contaminated benchmark" objections); a submission earns a citable public ranking. Best fast-win beyond the two flagships.

### 4. ResearchQA — long-form scholarly QA with citation rubrics
- **Source:** arXiv 2509.00496 (Sept 2025). 21,000 research queries + **160,000 rubric items** distilled from survey articles across **75 fields**; rubrics cover citation, explanation, limitation coverage.
- **Who leads:** **The best system satisfies <11% of citation-related rubric items.** Citation competency is the field's worst axis.
- **POLARIS fit:** Very high. A wide-open #1 opportunity precisely on citation competency — POLARIS's strongest muscle against the field's weakest score. Scale (21k queries) means run a stratified subset.

### 5. DeepResearch Bench v1 — RACE (quality) + FACT (citation)
- **Source:** arXiv 2506.11763 (June 13 2025, Ayanami0730 / ByteDance-affiliated); HF Spaces leaderboard. 100 PhD-level tasks / 22 fields. **RACE** = reference-based report quality (dynamic-weighted criteria); **FACT** = effective citation count + citation accuracy.
- **Who leads:** **Gemini-2.5-Pro Deep Research — RACE overall 48.88**, top of board.
- **POLARIS fit:** High on the **FACT leg** (citation accuracy = our edge) — chase it. RACE is a general quality axis (track, don't over-index). Established HF leaderboard = external credibility that DRB-II inherits; being strong on both v1 and v2 strengthens a SOTA claim.

### 6. ResearchRubrics
- **Source:** arXiv 2511.07685 (Nov 2025, **Scale AI**; ICLR 2026); GitHub scaleapi/researchrubrics. Realistic domain-diverse prompts + thousands of expert rubrics; multi-axis reproducible pipeline for DR agents.
- **Who leads:** Not extracted (new). Scale AI provenance = high credibility.
- **POLARIS fit:** High — rubric-based, same family as DRB-II/ResearchQA. Register once its harness is set. Chase alongside the flagships.

---

## TIER A — PROVE-COMPONENT / ADJACENT (validate a module, badge value, not the headline #1)

### 7. Mind2Web 2 — agentic search with source attribution
- **Source:** arXiv 2506.21506 (Sept 18 2025; NeurIPS 2025 D&B). 130 long-horizon real-time-browsing tasks; **Agent-as-a-Judge** with tree-structured rubrics that score **both answer correctness AND source attribution.**
- **POLARIS fit:** Adjacent-high. It is one of the few agentic boards that explicitly scores *source attribution*, which overlaps our provenance claim. Use to prove attribution generalizes beyond the report format; not the primary #1 because it is browsing-agent-shaped.

### 8. FACTS Grounding (Google DeepMind)
- **Source:** arXiv 2501.03200 (Jan 2025); **v2** late 2025; broader "FACTS Leaderboard" arXiv 2512.10791 (Dec 2025); hosted on **Kaggle**. Grounding of long-form responses to provided docs (≤32k tokens) across finance/tech/retail/medicine/law. Three judges (Gemini/GPT-4o/Claude ensemble).
- **POLARIS fit:** Adjacent. It is *closed-book grounding to a supplied document*, not open-web research — but it is a prestigious Google board and a strong "grounding badge." Prove-component: our strict_verify span-grounding should score high. Don't chase #1 (frontier LLMs with huge context lead), use as a credibility badge.

### 9. BrowseComp-Plus — retrieval-isolated deep research
- **Source:** GitHub texttron/BrowseComp-Plus (ACL 2026 Main). BrowseComp queries run against a **fixed curated ~100K-doc corpus** (not live web) to isolate retriever vs agent; top-5 docs, 512-token cap for fairness.
- **Who leads:** Purpose-built **Deep Research agent 51.5% accuracy**, showing orchestration beats raw tool access.
- **POLARIS fit:** Adjacent-useful. The fixed corpus makes it the *fair, reproducible* way to prove POLARIS's retrieval/reranking stack (Qwen3 embed+rerank) in isolation. Prove-component, not headline.

### 10. RAGChecker (internal harness)
- **Source:** arXiv 2408.08067 / NeurIPS 2024 D&B (Amazon Science); GitHub amazon-science/RAGChecker. Decomposes ground-truth + response into atomic claims, runs **claim-level entailment**, splits retriever vs generator diagnostics; correlates with human up to Pearson 62% (beats BLEU/ROUGE/RAGAS/ARES).
- **POLARIS fit:** Not a leaderboard to win — adopt it as an **internal regression harness** for basket→claim faithfulness (it mirrors our own NLI-entailment consolidation). Complements DeepTRACE offline.

### 11. FRAMES
- **Source:** arXiv 2409.12941 (Sept 2024, Google + Harvard); HF google/frames-benchmark. 824 multi-hop questions, 2–15 Wikipedia articles each; factuality + retrieval + reasoning end-to-end.
- **Who leads:** Single-step 0.40 → multi-step 0.66 → oracle-docs 0.73 accuracy.
- **POLARIS fit:** Component regression for multi-hop retrieval+reasoning. Short-answer, not long-form citation — internal/prove, not a SOTA claim.

---

## TIER B — IGNORE FOR #1 (wrong axis; pursuing them spends effort on non-differentiators)

### 12. BrowseComp (OpenAI, Apr 10 2025)
1,266 needle-in-haystack browsing problems. **Leader GPT-5.5 Pro 0.901; Kimi K2.6 top open-source 0.863** (board June 2026, 51 models). Measures hard-to-find fact location on live web, not long-form citation synthesis. Dominated by frontier browsing LLMs. **Ignore for #1** (use BrowseComp-Plus instead for the retrieval sub-claim).

### 13. GAIA (arXiv 2311.12983)
General-assistant tool-use. **Leader MiroThinker 81.9%.** Agentic exam, not citation-report. Off-axis. Ignore.

### 14. HLE — Humanity's Last Exam (arXiv 2501.14249, CAIS + Scale AI)
2,500 frontier academic questions. **Leader (with tools) Claude Fable 5 53.3%; deep-research agents ~26–37.7% (MiroThinker 37.7%, OpenAI DR 26.6%, Google DR 26.9%).** Rewards parametric reasoning depth, not citation faithfulness. A retrieval-grounded system is not differentiated here. Ignore for the SOTA claim.

### 15. SimpleQA / SimpleQA-Verified
OpenAI SimpleQA (Oct 2024, 4,326 Qs); **SimpleQA-Verified** arXiv 2509.07968 (Google, Sept 2025, 1,000 Qs). **Leader SimpleQA-Verified: Gemini 2.5 Pro F1 55.6.** Short-form *parametric* (closed-book) factuality — structurally anti-correlated with a retrieval-first design. Ignore.

### 16. WebArena / Mind2Web v1
Execution-based web-navigation (click/type success). Not research synthesis or citation. Ignore.

---

## TIER C — WATCH (2026 eval frameworks, not yet chase-able boards)
- **DREAM** (arXiv 2602.18940, Feb 2026) — reference-free *agentic* evaluation; flags the "Mirage of Synthesis" (fluent citations hiding factual defects); more sensitive to temporal/factual decay. Likely to become an important judge methodology — watch and pre-empt.
- **DeepResearchEval** (2601.09688), **DR-Arena** (2601.10504), **MiroEval** (2603.28407), **JADE** (2602.06486), **SurveyBench** (2510.03120), **PaperArena** (2510.10909), **DeepRubric/DR Tulu** (2606.17029 / RL-rubric training) — emerging automated DR-eval frameworks; monitor for a public leaderboard slot, none is yet the board to win.

---

## RECOMMENDED TARGET SET (final)

**Chase for #1 — the extended "beat-both" (5 boards, 2 axes):**
1. **DeepTRACE** — faithfulness, our edge, field at 40–80% cite-accuracy = most winnable.
2. **DeepResearch Bench II** — coverage, the hard axis; beat AI21-DeepResearch's 64.38% (win InfoRecall, presentation is saturated).
3. **DeepScholar-Bench** — live + automated + verifiability; open top slot, cheapest credible public ranking.
4. **ResearchQA** — citation competency where the field is <11%; open #1 on our strongest muscle.
5. **DeepResearch Bench v1 (FACT leg)** — citation accuracy on the established HF board for external credibility; register ResearchRubrics alongside once the harness is built.

**Prove-component (validate a module, earn badges — not headline #1):** BrowseComp-Plus (retriever isolation), Mind2Web 2 (source attribution), FACTS Grounding (grounding badge), RAGChecker + FRAMES (internal faithfulness/retrieval regression harness).

**Ignore (off-axis, non-differentiating):** BrowseComp, GAIA, HLE, SimpleQA/-Verified, WebArena/Mind2Web v1.

**Strategic logic:** POLARIS wins where *citation faithfulness × multi-source coverage* is scored and the field is weak (DeepTRACE, ResearchQA citation, DRB-II InfoRecall, DeepScholar verifiability). It should not spend cycles on parametric-reasoning exams (HLE, SimpleQA) or live-web needle-hunts (BrowseComp) where frontier general LLMs, not a grounded research pipeline, define the ceiling.

## Sources
- [DeepResearch Bench II — arXiv 2601.08536](https://arxiv.org/abs/2601.08536) · [GitHub imlrz](https://github.com/imlrz/DeepResearch-Bench-II) · [leaderboard agentresearchlab](https://agentresearchlab.com/benchmarks/deepresearch-bench-ii/index.html)
- [DeepTRACE — arXiv 2509.04499](https://arxiv.org/abs/2509.04499)
- [DeepResearch Bench v1 — arXiv 2506.11763](https://arxiv.org/abs/2506.11763) · [site](https://deepresearch-bench.github.io/) · [GitHub Ayanami0730](https://github.com/Ayanami0730/deep_research_bench)
- [DeepScholar-Bench — arXiv 2508.20033](https://arxiv.org/abs/2508.20033) · [leaderboard](https://guestrin-lab.github.io/deepscholar-leaderboard/leaderboard/deepscholar_bench_leaderboard.html) · [GitHub](https://github.com/guestrin-lab/deepscholar-bench)
- [ResearchQA — arXiv 2509.00496](https://arxiv.org/pdf/2509.00496)
- [ResearchRubrics — arXiv 2511.07685](https://arxiv.org/pdf/2511.07685) · [GitHub scaleapi](https://github.com/scaleapi/researchrubrics)
- [Mind2Web 2 — arXiv 2506.21506](https://arxiv.org/abs/2506.21506)
- [FACTS Grounding — arXiv 2501.03200](https://arxiv.org/pdf/2501.03200) · [FACTS Leaderboard 2512.10791](https://arxiv.org/html/2512.10791v1) · [Kaggle](https://www.kaggle.com/benchmarks/google/facts-grounding)
- [BrowseComp — OpenAI](https://openai.com/index/browsecomp/) · [leaderboard llm-stats](https://llm-stats.com/benchmarks/browsecomp) · [BrowseComp-Plus GitHub texttron](https://github.com/texttron/BrowseComp-Plus)
- [RAGChecker — GitHub amazon-science](https://github.com/amazon-science/RAGChecker) · [NeurIPS 2024 PDF](https://proceedings.neurips.cc/paper_files/paper/2024/file/27245589131d17368cccdfa990cbf16e-Paper-Datasets_and_Benchmarks_Track.pdf)
- [FRAMES — arXiv 2409.12941](https://arxiv.org/pdf/2409.12941) · [HF google/frames-benchmark](https://huggingface.co/datasets/google/frames-benchmark)
- [HLE leaderboard](https://artificialanalysis.ai/evaluations/humanitys-last-exam) · [GAIA / MiroThinker 2511.11793](https://arxiv.org/pdf/2511.11793)
- [SimpleQA-Verified — arXiv 2509.07968](https://arxiv.org/html/2509.07968v1) · [SimpleQA leaderboard](https://llm-stats.com/benchmarks/simpleqa)
- [ResearchArena — arXiv 2406.10291](https://arxiv.org/html/2406.10291v3)
- [DREAM — arXiv 2602.18940](https://arxiv.org/abs/2602.18940) · [DR-Arena 2601.10504](https://arxiv.org/pdf/2601.10504) · [DeepResearchEval 2601.09688](https://arxiv.org/pdf/2601.09688)
# APPENDIX D — SOTA techniques research
I have enough to deliver. Per operator directive I'm skipping the advisor (same-model, flagged off for POLARIS) — this is a literature-mapping deliverable, not a code gate. Writing the final structured output now.

---

# SOTA deep-research architecture techniques vs POLARIS — technique-by-technique gap map

Scope check first: POLARIS is a **fixed 20-stage DAG** (`docs/polaris_pipeline_canonical.md`), not a reasoning-driven agent loop. It plans queries up front, fans out multi-backend retrieval, then has **two bounded corrective loops** (completeness-expansion at stage 7; CRAG adequacy loop-back in `nodes/crag_adequacy_loop.py`). It is NOT a ReAct/RL agent that decides its next query from what it just read, and it has NO test-time draft-refinement loop. That single architectural fact drives most of the gaps below.

Legend: **HAS** = wired and firing in the DAG · **PARTIAL** = mechanism present but bounded/one-shot/not reasoning-driven · **LACKS** = absent.

## A. Iterative / agentic multi-step retrieval

| Technique | What it does | SOTA source (2025-26) | POLARIS? | Gap |
|---|---|---|---|---|
| Interleaved reason→search→read loop (ReAct-style) | Model emits a reasoning step, issues a search query, reads results, then decides whether to search again or answer — the NEXT query is conditioned on what was just read | Search-R1, arXiv 2503.09516 (Mar 2025); Search-o1 "agentic search-enhanced reasoning" (Jan 2025); RL-agentic-search survey arXiv 2510.16724 (Oct 2025) | **PARTIAL** | POLARIS decomposes queries UP FRONT (`fs_researcher_query_gen.py`, `iterresearch_query_gen.py`, `query_decomposer.py`) and fans them out in one wave. It has no per-hop reasoning that reads a result and forms the next query from it. The only feedback loops are completeness-expansion and the CRAG adequacy loop-back (`nodes/crag_adequacy_loop.py`, `PG_ADEQUACY_CRAG_MAX_LOOPS` default **1**). Gap: true multi-hop chains (fact A → find entity → search entity B) are not walked; multi-hop DRB-II rubrics that need a 2nd-order fact stay uncovered. |
| RL-trained search policy | Search behavior is trained with outcome-reward RL (GRPO/PPO), not prompted, so the agent learns when/what to retrieve | Search-R1 arXiv 2503.09516; R3-RAG arXiv 2505.23794; "How to Train Your Deep Research Agent" arXiv 2602.19526 | **LACKS** | POLARIS query-gen is prompt/heuristic (FS-Researcher). No learned retrieval policy. Acceptable given sovereignty + frozen-faithfulness DNA; note only as a frontier axis POLARIS deliberately does not chase. |
| Agentic URL harvesting / corrective retrieval | On low-confidence corpus, grade sufficiency and fire a targeted corrective retrieval round | CRAG (Corrective-RAG) Yan et al. arXiv 2401.15884 (cited by POLARIS itself); RL-agentic-search survey 2510.16724 | **HAS** | `nodes/crag_adequacy_loop.py` replaces the count-floor STOP with a CRAG CORRECT/AMBIGUOUS/INCORRECT grader over the whole corpus + one bounded loop-back; `retrieval/agentic_url_harvester.py`. Gap: bounded to 1 loop by default — widen `MAX_LOOPS` for hard DRB-II tasks where the first corpus is thin. |

## B. Query decomposition & planning

| Technique | What it does | SOTA source | POLARIS? | Gap |
|---|---|---|---|---|
| Multi-perspective / outline-driven question generation | Simulate multiple expert personas to generate diverse sub-questions, driving broad coverage before writing | STORM (outline-driven, multi-perspective), github.com/stanford-oval/storm; Co-STORM (collaborative curation) — reported ~85% citation recall/precision; Deep Research survey arXiv 2508.12752 (Aug 2025) | **HAS** | `retrieval/storm_query_extractor.py`, `retrieval/section_blueprint.py`, `nodes/intent_frame.py`, `nodes/complexity_router.py`. Multi-section STORM generator is wired (stage 11). Solid. |
| Plan-first / editable research plan | Produce an explicit plan (sub-goals + target structure) before any retrieval; sometimes user-confirmed | OpenAI Deep Research (interactive clarification, openai.com/index/introducing-deep-research, Feb 2025); Gemini Deep Research plan-confirm (Gemini 2.5, arXiv 2507.06261, Jul 2025) | **PARTIAL** | POLARIS builds `contract_outline.py` / `report_contract.py` / `required_entity_ledger.py` as an internal plan, and the web UI has a Plan-Review page. But there is no runtime interactive-clarification turn that refines scope from the user before the run (scope is auto-decided in `nodes/scope_gate.py`). Gap: for ambiguous DRB-II prompts, no scope-narrowing dialog → risk of off-target coverage. |
| Utility-guided dynamic outline | Continuously re-optimize the outline as evidence arrives, rather than fixing it once | ScaffoldAgent, arXiv 2606.20122 (Jun 2026); TTD-DR draft-as-outline (below) | **PARTIAL** | POLARIS outline is built once from the contract; sections can trigger one regeneration but the outline itself is not re-optimized against gathered evidence. Gap: analysis/presentation DRB-II rubrics reward reorganizing around what was found. |

## C. Coverage-maximizing search

| Technique | What it does | SOTA source | POLARIS? | Gap |
|---|---|---|---|---|
| Multi-backend fan-out + rank fusion | Query several heterogeneous sources and fuse rankings for recall | Deep Research Agents roadmap arXiv 2506.18096 (Jun 2025); RAG-R1 multi-query parallelism arXiv 2507.02962 | **HAS** | `retrieval/live_retriever.py` + `domain_backends.py` (Serper/Semantic Scholar/OpenAlex/Exa) + `retrieval/search_fusion_wrrf.py` (weighted RRF). Strong. |
| Saturation / completeness stopping | Detect when new searches stop adding facts (coverage saturation) and when required entities are still missing | Deep Research survey arXiv 2508.12752; ARC context management arXiv 2601.12030 | **HAS** | `retrieval/saturation.py`, `nodes/completeness_checker.py`, `retrieval/required_entity_retrieval.py` + `generator/required_entity_ledger.py`. Good coverage-control substrate. |
| Blocked-reference / anti-leakage independent retrieval | Force the answer to be supported by INDEPENDENT sources, not the one article a fact was derived from | DeepResearch-Bench-II blocked-ref mechanism, arXiv 2601.08536 (this is the target benchmark's core scoring rule) | **HAS** | `retrieval/blocked_reference_registry.py` parses the "do-not-view" appendix and hard-drops the named paper across ~6 mirrors (URL/DOI/PII/title legs). This directly protects the DRB-II `-1`/blocked_rate score. Well-aimed. |
| Recall-then-surface (the composition gap) | Retrieving a fact is necessary but NOT sufficient — the fact must be COMPOSED into a rubric-satisfying statement | "Synthesis Gap" eval, arXiv 2601.12369 (Jan 2026); DREAM agentic metrics arXiv 2602.18940 | **PARTIAL — POLARIS's #1 coverage weakness** | POLARIS retrieves broad corpora (hundreds of sources) but the known failure (BENCHMARKS_STUDY.md, Q78 coverage 0.375) is facts retrieved-but-not-composed. `generator/weighted_enrichment.py` surfaces the full basket, but breadth is still funnel-limited at compose. Gap: this is the exact axis DRB-II Information-Recall (74% of rubrics) scores — highest-leverage fix. |

## D. Cross-source synthesis

| Technique | What it does | SOTA source | POLARIS? | Gap |
|---|---|---|---|---|
| Basket consolidation / corroboration | Group same-claim sources; keep ALL as multi-citation corroboration (repetition = evidence strength) | Explicit-working-memory factuality arXiv 2412.18069; POLARIS DNA §-1.3 | **HAS** | `synthesis/content_dedup_consolidate.py`, `synthesis/consolidation_nli.py` (NLI baskets), `synthesis/finding_dedup.py`. Note the canonical doc flags `finding_dedup` historically kept ONE representative — verify the NLI-basket consolidation is the firing path, not the legacy drop. |
| Higher-order synthesis / analysis | Combine facts across sources into new conclusions (cross-trial, cross-jurisdiction, quantified deltas) | Synthesis-gap eval arXiv 2601.12369; TTD-DR arXiv 2507.16075 | **HAS (mechanism) / PARTIAL (yield)** | `generator/cross_source_synthesis.py`, `cross_trial_synthesis.py`, `cross_jurisdiction_synthesizer.py`, `analyst_synthesis.py`, `depth_synthesis.py`, `quantified_analysis.py` + M6. Rich substrate. Gap: DRB-II Analysis (18%) rewards synthesized conclusions rendered as statements; if synthesis fires but the sentence is dropped at strict_verify, the rubric scores 0. Tune the synthesis→verify→render survival, not the synthesis logic. |
| Two-sided / balanced coverage | Surface BOTH pro and con evidence; render contradictions | DeepTRACE One-Sided/Overconfident metrics, arXiv 2509.04499 (Sept 2025) | **HAS** | `retrieval/contradiction_detector.py`, `semantic_conflict_detector.py`, `qualitative_conflict_detector.py`, `dissent_recall_builder.py`, `generator/contradiction_hedging.py`. Directly targets DeepTRACE metric #1/#2. Gap: ensure both sides RENDER (weight-and-consolidate must not let one side get funnel-dropped). |

## E. Citation verification / self-critique loops

| Technique | What it does | SOTA source | POLARIS? | Gap |
|---|---|---|---|---|
| Span-grounded per-sentence attribution | Every sentence carries a provenance token to a source span; unsupported sentences are dropped | Self-RAG reflection tokens (Asai et al., ICLR 2024); DeepTRACE Unsupported/Citation-Accuracy metrics arXiv 2509.04499 | **HAS — POLARIS's core edge** | `generator/provenance_generator.py` + `verified_compose.py` + strict_verify (numeric match + ≥2 content-word overlap). This is exactly DeepTRACE #5/#7/#8. Best-in-class faithfulness substrate. |
| Multi-role verification judge | An independent model (different family) re-judges each claim vs its span: verified/partial/unsupported/fabricated | Chain-of-Verification CoVe / CoV-RAG arXiv 2410.05801; multi-stage self-verification arXiv 2509.05741 (Sept 2025) | **HAS (now built)** | The 4-role D8 judge is wired: `roles/judge_adapter.py`, `roles/openrouter_role_transport.py`, `four_role_held` gate. Note: `polaris_pipeline_canonical.md` still labels stages 14-16 "not built" — that doc is STALE vs the `roles/` code; reconcile it (same-PR drift rule). |
| Self-critique / overstatement guard / retraction | After drafting, critique claims for overstatement and retract unsupported ones | Reflexion verbal self-critique (Shinn et al., NeurIPS 2023); reference-hallucination detection arXiv 2604.03173 (2026) | **HAS** | `generator/overstatement_guard.py`, `retraction_gate.py`, `atom_refusal_validator.py`, `contradiction_hedging.py`, `span_quality_gate.py`, `chrome_furniture_screen.py`. Strong. Gap: these are one-shot screens, not an iterative critique→revise→re-verify loop (see F). |
| Uncited-source / source-necessity pruning | Ensure every LISTED source is actually cited and load-bearing (min-vertex-cover) | DeepTRACE Uncited-Sources #4 + Source-Necessity #6, arXiv 2509.04499 | **PARTIAL** | POLARIS lists large corpora; the basket→citation render must attach every listed source to a claim or quarantine it. Gap: no explicit min-vertex-cover necessity check → risk of DeepTRACE "padding" penalty from listed-but-uncited sources. |

## F. Reflection / replanning

| Technique | What it does | SOTA source | POLARIS? | Gap |
|---|---|---|---|---|
| Verbal self-reflection memory across attempts | On a failed/weak attempt, generate a written reflection and carry it into the next attempt | Reflexion (Shinn et al., NeurIPS 2023); Meta-Policy Reflexion arXiv 2509.03990; ReflAct arXiv 2505.15182 | **LACKS** | POLARIS has per-section single regeneration on <40% verified, but no reflection memory that changes strategy across the run. Gap: no learning within a run from what failed. |
| Plan-reflect-evolve / candidate crossover | Reflect on the plan mid-run and evolve/cross candidate plans | Deep Researcher Reflect-Evolve arXiv 2601.20843 (2026); IntentRL arXiv 2602.03468 | **LACKS** | Plan is fixed at contract time. Gap: for open-ended DRB-II tasks, a static plan caps analysis-rubric coverage. |
| Active context management | Prune/refresh working context over a long horizon so the agent stays on-goal | ARC arXiv 2601.12030 (2026); Anthropic multi-agent memory (below) | **PARTIAL** | Bounded by the DAG; `snapshot`/`corpus_snapshot` give replay but not live context curation. |

## G. Long-context report generation

| Technique | What it does | SOTA source | POLARIS? | Gap |
|---|---|---|---|---|
| Hierarchical outline→section synthesis | Decompose the report into outline + per-section writing to sustain coherence over thousands of tokens | LongWriter/AgentWrite arXiv 2408.07055 (ICLR 2025); LongWriter-Zero (2025); NexusSum ACL 2025 | **HAS** | `generator/multi_section_generator.py` (STORM two-stage), `nodes/contract_outline.py`/`outline.py`, `generator/abstract_conclusion.py`, `abstractive_writer.py`, `key_findings.py`. Matches the hierarchical SOTA pattern. |
| Test-time iterative draft refinement ("diffusion" denoise) | Start from a noisy DRAFT that acts as an evolving outline; iteratively denoise it via retrieval+revision cycles — draft guides search, search improves draft | **TTD-DR**, arXiv 2507.16075 (Jul 2025, Google) — **74.5% win rate vs OpenAI Deep Research** | **LACKS — biggest single architectural gap** | POLARIS writes essentially once (compose → strict_verify → one regen). No draft-as-evolving-outline loop where the current draft steers the next retrieval. This is the technique the current SOTA winner uses; adding a bounded draft-denoise loop (draft → find gaps → targeted retrieve → revise → re-verify) is the highest-leverage coverage upgrade, and it composes cleanly on top of POLARIS's existing corrective-retrieval + verify machinery. |
| Presentation structuring (tables/masthead) | Render facts as structured, verifiable, readable output (tables, sections) | DeepTRACE Relevant-Statement #3, arXiv 2509.04499; DRB-II Presentation dimension arXiv 2601.08536 | **HAS** | `generator/markdown_table_normalizer.py`, `abstract_conclusion.py`, chrome/furniture screens. Gap: DeepTRACE Relevant-Statement penalizes filler intro/conclusion — audit that abstract/conclusion prose stays on-point. |

## H. Multi-agent orchestration (cross-cutting)

| Technique | What it does | SOTA source | POLARIS? | Gap |
|---|---|---|---|---|
| Orchestrator-worker with parallel subagents | A lead agent plans and spawns 3-5 specialized subagents (own context windows) that explore independent paths in parallel, then a separate citation pass synthesizes | Anthropic multi-agent research system, anthropic.com/engineering/multi-agent-research-system (Jun 2025) — **+90.2% vs single-agent** on breadth-first research | **PARTIAL** | POLARIS parallelizes at the module level (fan-out retrieval/fetch/relevance/tiering/NLI, per the runtime-parallelism mandate) but there is no dynamic lead-agent that spawns per-subtopic research subagents with isolated contexts. Gap: for wide DRB-II tasks that exceed one context window, orchestrator-worker is the proven scaling pattern; POLARIS's fixed DAG caps independent-path breadth. |

---

## Bottom line — the three gaps that move BOTH scoreboards

1. **Test-time iterative draft refinement (TTD-DR, arXiv 2507.16075)** — LACKS. The current SOTA winner's mechanism. A bounded draft→gap-detect→targeted-retrieve→revise→re-verify loop reuses POLARIS's CRAG loop-back and strict_verify, and directly lifts DRB-II Information-Recall (74% of rubrics) + Analysis (18%). **Highest leverage.**
2. **Recall-to-composition surfacing (Synthesis-Gap, arXiv 2601.12369)** — PARTIAL, POLARIS's measured weakness (Q78 coverage 0.375). Facts are retrieved but funnel-dropped before they render as rubric-satisfying statements. Fix the basket→verify→render survival, not the retrieval. Directly = DRB-II total/recall.
3. **True multi-hop reasoning-driven retrieval (Search-R1, arXiv 2503.09516)** — PARTIAL. Up-front decomposition doesn't walk 2nd-order fact chains. Needed for the harder DRB-II multi-hop rubrics.

POLARIS is already strong-to-leading on the **DeepTRACE citation-faithfulness axis** (span-grounding, provenance tokens, 4-role D8 judge, multi-source baskets, two-sided contradiction detectors, blocked-reference registry) — that is its designed edge and it maps cleanly to DeepTRACE metrics #4/#5/#7/#8 and the DRB-II blocked-ref mechanism. The deficit is on the **DeepResearch-Bench-II coverage/analysis axis**, and it is architectural (no iterative draft loop, no reasoning-driven multi-hop, no orchestrator-worker), not a faithfulness problem — so it can be closed without touching the frozen faithfulness engine.

**Doc-drift flag:** `docs/polaris_pipeline_canonical.md` (lines 48-52) still marks the Mirror/Sentinel/Judge roles "NEW — not built," but `src/polaris_graph/roles/judge_adapter.py` + `openrouter_role_transport.py` + the `four_role_held` gate show the 4-role D8 judge IS wired. That canonical file needs a same-PR reconcile.

Sources: [DeepResearch-Bench-II arXiv 2601.08536](https://arxiv.org/abs/2601.08536) · [DeepTRACE arXiv 2509.04499](https://arxiv.org/abs/2509.04499) · [TTD-DR arXiv 2507.16075](https://arxiv.org/abs/2507.16075) · [Search-R1 arXiv 2503.09516](https://arxiv.org/html/2503.09516) · [CRAG arXiv 2401.15884](https://arxiv.org/abs/2401.15884) · [LongWriter arXiv 2408.07055](https://arxiv.org/pdf/2408.07055) · [Deep Research survey arXiv 2508.12752](https://arxiv.org/html/2508.12752v1) · [Deep Research Agents roadmap arXiv 2506.18096](https://arxiv.org/html/2506.18096v2) · [RL-agentic-search survey arXiv 2510.16724](https://arxiv.org/pdf/2510.16724) · [Synthesis-Gap arXiv 2601.12369](https://arxiv.org/pdf/2601.12369) · [Anthropic multi-agent research system](https://www.anthropic.com/engineering/multi-agent-research-system) · [OpenAI Deep Research](https://openai.com/index/introducing-deep-research/) · [Gemini 2.5 arXiv 2507.06261](https://arxiv.org/pdf/2507.06261) · [CoV-RAG arXiv 2410.05801](https://arxiv.org/html/2410.05801v1) · [ScaffoldAgent arXiv 2606.20122](https://arxiv.org/html/2606.20122v1) · [Reflect-Evolve arXiv 2601.20843](https://arxiv.org/pdf/2601.20843) · [STORM](https://github.com/stanford-oval/storm)
# APPENDIX E — Gap: DeepTRACE
Grounding complete. No `min-vertex-cover`/`source_necessity` module exists anywhere in `src/polaris_graph` (metric #6 is fully unbuilt); the corroboration count is rendered by `weighted_enrichment.py` (the "Source corroboration" block, `— N verified independent source(s)` suffix) while `disclosure_population.py` already plumbs the correct `verified_support_origin_count` only into the operator JSON, not the report body; chrome screening lives in `multi_section_generator._screen_fixk_render_chrome` + the `sanitize_render_seam` chokepoint but is claim-bullet-scoped; `both_sides.py`/`dissent_recall_builder` exist for two-sidedness. That is enough to name real code in every fix cell.

---

# DeepTRACE 8-metric BEAT-#1 gap map — POLARIS vs GPT-5-Deep-Research (arXiv 2509.04499, Salesforce AI Research, ICLR 2026)

Grounding: pipeline code under `src/polaris_graph/`, the drb_72 re-smoke forensic audit (`.codex/I-deepfix-001/RESMOKE_S11_FORENSIC_AUDIT.md`, verdict FAITHFUL / 0 fabrication), and the 6 residual defects D1–D6. `#1 bar` = the single best competitor score per metric from the published tables (GPT-5-DR leads 6 of 8; BingChat leads One-Sided; Copilot leads Overconfident). "POLARIS now" is estimated from the run artifacts, not a scored DeepTRACE run (no public scorer exists — one must be re-implemented; the 8 formulas below are complete enough to build it).

**One orientation subtlety that decides two metrics (read before wiring):** DeepTRACE's "listed sources" = the sources the answer *presents as its reference list*, not the retrieval corpus. POLARIS's rendered bibliography lists exactly the **12 cited** sources (`bibliography.json`), while the **88-source** `corpus_credibility_disclosure` is a separate provenance/audit ledger. If a DeepTRACE-style scorer is pointed at the 12-source bibliography, Uncited-Sources ≈ 0 (a POLARIS win); if it is mis-pointed at the 88-source disclosure, 76/88 read as uncited padding (a catastrophic false loss). Metric #4 and #6 hinge on keeping the citation list = the cited set and labeling the 88-corpus disclosure as audit, not as a reference list.

## Summary table (metric | POLARIS now | #1 bar | gap | exact fix)

| # | Metric (dir) | POLARIS now (drb_72 + code) | #1 bar (system) | Gap | Exact pipeline fix to BEAT #1 |
|---|---|---|---|---|---|
| 1 | One-Sided ↓ | Mechanism wired (`contradiction_detector`, `both_sides.py`, `dissent_recall_builder`, `contradiction_hedging`) but did NOT fire on drb_72 — all 3 flags were extraction garbage; **D6** disclosed "1" vs actual 3 | **48.7% BingChat** (DR-class 54.67 GPT-5-DR); ideal 0 | Debate two-sidedness is a *composition mandate*, not retrieval; not proven to render both sides on a genuine debate prompt | Add a debate-class detector in `nodes/complexity_router.py`/`scope_gate.py`; force a pro AND con basket per contested claim into `verified_compose` before strict_verify so the weight-and-consolidate path never funnel-drops the minority side; fix **D6** so `contradiction disclosures` count = `manifest.contradictions_found` |
| 2 | Overconfident ↓ | Structurally ≈0 — POLARIS emits per-claim verdict chips + `[confidence: low]` labels + hedging, never a 1–5 max-confidence Likert on a one-sided answer | **0.0% Copilot-TD**; ideal 0 | **D1** is the only breach: the Conclusion re-lift STRIPS the low-confidence label the body attached to the 46% figure → an over-confident restatement | Fix **D1**: make the abstract/conclusion re-lift in `generator/abstract_conclusion.py` carry the source claim's confidence label + `report_annotation.annotated_claim_ids`; a low-flagged claim can never re-render clean |
| 3 | Relevant Statement ↑ | Depressed by **D3** in-prose chrome ("Introduction" header word, "(1, 2)" ref markers, truncated "(2017)" fragment) + template-label lifts ("Population:") + disjoint verbatim concatenation that isn't on-point prose | **87.5% GPT-5-DR**; ideal 100 | `render_chrome_canary` counts claim-bullets only → blind to prose chrome; abstract/conclusion are concatenated lifts, not synthesized statements | Extend `is_render_chrome_or_unrenderable` + `sanitize_render_seam` (weighted_enrichment.py) to PROSE units: strip leaked headers, in-text `(N, N)` markers, repair leading truncated fragments; route abstract/conclusion through `cross_source_synthesis`/`abstractive_writer` so every unit is an on-point statement, not a labeled fragment |
| 4 | Uncited Sources ↓ | ≈0 IF listed-set = cited bibliography (12 cited, all cited) — a POLARIS strength; risk only if the 88-corpus disclosure is read as the reference list | **0.0% GPT-4.5 & GPT-5-DR**; ideal 0 | Two listed sources ([6], [8]) headline with `verified_support_origin_count=0` (**D2**) → listed-but-not-supporting = padding | Keep rendered reference list = cited set; label `corpus_credibility_disclosure` an audit ledger (not references); quarantine any bibliography entry whose basket `verified_support_origin_count=0` (the D2 [6]/[8]) out of the citation list |
| 5 | Unsupported ↓ | ≈0 by construction — every asserted sentence carries a provenance token; `strict_verify` dropped 39 (34 no-token, 1 no-overlap, 1 number-not-in-span, 3 dedup). This is POLARIS's core edge and already ≤ #1 | **12.5% GPT-5-DR**; ideal 0 | The 3 D8 "unsupported" labels are FALSE-negatives on grounded top-journal claims (degraded GLM rules-floor judge, family-segregation OFF glm/glm) — they inflate the *disclosed* unsupported count | Swap the degraded judge to a provider-count-robust model (memory pick: `moonshotai/kimi-k2.6`, 21 providers) so 429-tears stop producing false "unsupported"; restore two-family segregation (distinct-family judge) so self-bias doesn't mislabel — see §9.1 invariant #1 |
| 6 | Source Necessity ↑ | **No min-vertex-cover exists anywhere** in the pipeline; single-origin baskets mean most listed sources are load-bearing, but **D4** padding (1986 robotics [11] weight 0.08, OECD working paper [12], T4 Frontiers [8]) headlines un-necessarily | **87.5% GPT-5-DR**; ideal 100 | Necessity is neither computed nor enforced; M2 document-type weighting was OFF so off-genre/non-journal sources reach the render floor | BUILD a new `synthesis/source_necessity.py` = Hopcroft–Karp min-vertex-cover over the citation⊙support bipartite graph; quarantine non-necessary sources; turn ON M2 document-type weighting so non-journal/off-era sources drop below the render floor when the question demands "journal articles only" (D4) |
| 7 | Citation Accuracy ↑ | High by design — all 12 `[N]` resolve to real spans; every numeric token-span physically contains its number. **Two cracks: D1** (46% caveat-strip → citation attaches to a subtly different claim than the span supports) and **D2** (corroboration count bound to citation CHROME span, not a claim span) | **79.1% GPT-5-DR**; ideal 100 | The span is present but the *claim it is attached to* drifts (D1) or points at boilerplate (D2) → support-invalid under a strict GPT-5 judge | Fix **D1** in `generator/overstatement_guard.py`: the numeric-match in strict_verify must also require the number's threshold/condition frame to survive (bind the provenance token to the full qualifying span). Fix **D2**: the "Source corroboration" block in `weighted_enrichment.py` must read `verified_support_origin_count` (as `disclosure_population.py` already does for the JSON), not member-length, and bind to a claim span not citation chrome |
| 8 | Citation Thoroughness ↑ | LOW — only 12 cited of 88 corpus; breadth funnel-drops genuine support at compose; **D5** empties `covered_element_ids` on verified claims so coverage under-credits (0.571) | **87.5% GPT-5-DR**; ideal 100 | The retrieved-but-not-composed gap: much genuine support (76/88) exists but isn't attached to a rendered claim → the same coverage lever as DRB-II recall | Widen `weighted_enrichment.py` to surface the FULL ordered SUPPORTS basket as multi-citations (keep-all, no cap) through unchanged strict_verify; fix **D5** in `roles/coverage_binder.py`/`generator/required_entity_ledger.py` so verified claims populate `covered_element_ids` and `required_entity_coverage` credits them |

---

## Per-metric detail — the D-residual placement + the beat-not-just-close move

### 1. One-Sided Answer (↓, ideal 0; #1 = BingChat 48.7%, GPT-5-DR 54.67%)
POLARIS has the richest two-sidedness substrate in the field: `retrieval/contradiction_detector.py`, `semantic_conflict_detector.py`, `qualitative_conflict_detector.py`, `dissent_recall_builder.py`, `generator/both_sides.py`, `contradiction_hedging.py`. But on drb_72 it fired on zero *real* contested claims (all 3 detector flags were a Turkish postal code, page numbers, URL product-IDs), and **D6** shows the disclosure said "1" while the manifest held 3. **Beat move:** the field's best is still 48.7% one-sided — a wide-open metric. A debate-class router that forces a pro-basket AND a con-basket into `verified_compose` per contested claim, with the weight-and-consolidate path forbidden from dropping the minority side before strict_verify, takes POLARIS toward **single-digit One-Sided** — a clear beat, because no competitor renders structured pro/con with span-grounded citations on both sides.

### 2. Overconfident Answer (↓, ideal 0; #1 = Copilot 0.0%)
POLARIS is already at the #1 bar structurally: it never emits a max-confidence Likert on a one-sided answer — it emits per-claim verdict chips and low-confidence labels. **D1 is the single breach and it belongs here as much as on citation-accuracy:** the Conclusion re-presented the 46% figure "clean, caveat stripped" while the body had tagged it `[confidence: low — NOT confirmed]`. That is the mechanical definition of an overconfident restatement. **Beat move:** make `abstract_conclusion.py` re-lift carry the confidence annotation with the sentence — a label-flagged claim can never re-render unlabeled. This holds Overconfident at 0 and is a two-line provenance-propagation fix, not a model change.

### 3. Relevant Statement (↑, ideal 100; #1 = GPT-5-DR 87.5%) — home of D3
D3 lands squarely here: chrome units and template-label fragments are non-statements that inflate the denominator. The audit found the leaked header word "Introduction" (A5), the source's in-text "(1, 2)" markers (C5), and the truncated "(2017)" fragment with "Morrar et al.," chopped off (C4) — plus the observation that the Abstract/Conclusion are "concatenations of disjoint verbatim sentence lifts … not a functioning Abstract." `render_chrome_canary` scored 0/33 because it only inspects claim-bullets. **Beat move:** extend the already-built `is_render_chrome_or_unrenderable` predicate and the `sanitize_render_seam` chokepoint (weighted_enrichment.py) to prose units (strip headers/ref-markers, repair leading truncations), and route the abstract/conclusion through `cross_source_synthesis`/`abstractive_writer` so each rendered unit is an on-point synthesized statement. That clears the filler denominator and pushes Relevant past 87.5%.

### 4. Uncited Sources (↓, ideal 0; #1 = GPT-4.5 & GPT-5-DR 0.0%) — orientation-critical, touches D2
POLARIS already lists only what it cites, so uncited/listed ≈ 0 — matching #1 — **provided the scorer reads the 12-source bibliography, not the 88-source audit disclosure.** D2's [6]/[8] (listed, `verified_support_origin_count=0`) are the exception: listed sources that support nothing. **Beat move:** quarantine any bibliography entry with a zero verified-support basket out of the citation list, and explicitly type the `corpus_credibility_disclosure` as a provenance ledger. Then every listed source is a cited, supporting source → 0% uncited, tying #1 and beating everyone below GPT-5-DR (BingChat 36.2, YouChat-DR 66.3).

### 5. Unsupported Statements (↓, ideal 0; #1 = GPT-5-DR 12.5%) — POLARIS's structural win
This is the metric POLARIS is built to dominate: strict_verify enforces provenance token + numeric-match + ≥2 content-word overlap per §9.1 invariant #3, so unsupported-into-asserted-prose ≈ 0 (the audit confirmed 0 fabrications across 118 units). POLARIS is at or below the 12.5% #1 bar today. The only thing hurting the *reported* number is the D8 judge's 3 false-negatives on grounded top-journal claims — caused by the degraded GLM rules-floor and disabled family-segregation (glm/glm, `PG_PERMIT_GENERATOR_EVALUATOR_SAME_FAMILY=1`). **Beat move:** swap to the provider-robust `kimi-k2.6` judge (21 OpenRouter providers, distinct family → two-family holds) so 429-tears stop generating false "unsupported," and restore family segregation. That converts POLARIS's real ≈0% unsupported into a *scored* ≈0% — a decisive beat over GPT-5-DR's 12.5%.

### 6. Source Necessity (↑, ideal 100; #1 = GPT-5-DR 87.5%) — receives D2 + D4, needs a new module
No min-vertex-cover / Hopcroft–Karp / necessity computation exists anywhere in `src/polaris_graph` (confirmed by grep). Single-origin baskets make most listed sources load-bearing, but **D4** padding headlines un-necessarily (1986 robotics [11] at weight 0.08, OECD working paper [12], T4 Frontiers [8]) because M2 document-type weighting was OFF, and **D2**'s zero-support listed sources are padding by definition. **Beat move:** build `synthesis/source_necessity.py` implementing the paper's exact min-vertex-cover over the citation⊙support bipartite graph, expose necessity per source, and drop non-necessary/off-genre sources via M2 doc-type weighting below the render floor when the question constrains source type. Computing necessity and enforcing it is how POLARIS clears 87.5% — the field cannot, because their sources are single-shot and unpruned.

### 7. Citation Accuracy = Σ(C⊙S)/Σ(C) (↑, ideal 100; #1 = GPT-5-DR 79.1%) — home of D1 + D2
POLARIS's design target and its second structural win: every citation resolves to a real span containing its number. The two cracks are exactly D1 and D2. **D1** (citation-accuracy face): the 46% citation is span-present but attaches to "exposed to LLM technologies" when the span supports "could have over half their tasks affected under the complementary-software scenario" (LLM-alone = 1.8%) — a support-*invalid* citation to a strict judge. **D2**: the corroboration count binds to citation boilerplate (`"…Pages 889–942, https://doi.org/…"`), not a claim span. **Beat move:** (a) `overstatement_guard.py` + strict_verify's numeric leg must require the number's threshold/condition frame to survive re-lift, binding the provenance token to the full qualifying clause; (b) the "Source corroboration" render in `weighted_enrichment.py` must read `verified_support_origin_count` (the field `disclosure_population.py` already surfaces to JSON) and bind to a claim span. With both closed, POLARIS's citation accuracy sits near 95–100% — a large beat over 79.1%.

### 8. Citation Thoroughness = Σ(C⊙S)/Σ(S) (↑, ideal 100; #1 = GPT-5-DR 87.5%) — POLARIS's hardest, shares the DRB-II lever, touches D5
This is where POLARIS currently loses: 12 cited of 88 corpus means most genuine support (Σ(S)) is retrieved but never cited, because breadth funnel-drops at compose (the §-1.3 basket-consolidation "did not fire this run — zero genuine multi-source corroboration behind any cited claim"). **D5** compounds it: verified claims carry empty `covered_element_ids`, so `required_entity_coverage=0.571` under-credits support that actually rendered. **Beat move:** widen `weighted_enrichment.py` to surface the full ordered SUPPORTS basket as keep-all multi-citations (no cap, unchanged strict_verify — the WEIGHT-and-CONSOLIDATE DNA), and fix the coverage accounting in `coverage_binder.py`/`required_entity_ledger.py` so verified claims populate `covered_element_ids`. This is the single fix that moves BOTH scoreboards — DeepTRACE Thoroughness *and* DRB-II Information-Recall — because both reward attaching every genuine supporting source to a rendered claim.

---

## Bottom line — which metrics POLARIS already beats, which need a build

- **Already at/beating #1 (protect, don't rebuild):** Unsupported (#5, strict_verify — fix the judge false-negatives), Overconfident (#2, no max-Likert — fix D1 label-carry), Uncited (#4, cited-only bibliography — quarantine D2 zero-support entries).
- **Beatable with a surgical render/verify fix (no new architecture):** Citation Accuracy (#7 — close D1 caveat-strip + D2 count-source), Relevant Statement (#3 — extend chrome screen to prose, D3).
- **Needs a genuine build:** Source Necessity (#6 — no min-vertex-cover exists; new `synthesis/source_necessity.py` + turn M2 on), Citation Thoroughness (#8 — widen basket surfacing, fix D5 coverage credit), One-Sided (#1 — debate-class router forcing pro+con baskets).

The three defects the operator flagged priority map cleanly: **D1 → Citation Accuracy + Overconfident** (caveat-strip is both a support-invalid citation and an over-confident restatement), **D2 → Citation Accuracy + Uncited/Necessity** (false verified count on a zero-support listed source), **D3 → Relevant Statement** (prose chrome inflating the non-relevant denominator). All three are faithfulness-neutral render/verify fixes touching `weighted_enrichment.py`, `abstract_conclusion.py`, and `overstatement_guard.py` — none touch the frozen faithfulness engine.

Relevant files: `C:\POLARIS\src\polaris_graph\generator\weighted_enrichment.py` (D2 corroboration count + D3 render-seam chokepoint + #8 basket surfacing), `C:\POLARIS\src\polaris_graph\generator\multi_section_generator.py` (`_screen_fixk_render_chrome`, chrome canary), `C:\POLARIS\src\polaris_graph\generator\abstract_conclusion.py` (D1 label-carry on re-lift), `C:\POLARIS\src\polaris_graph\generator\overstatement_guard.py` (D1 caveat frame), `C:\POLARIS\src\polaris_graph\synthesis\disclosure_population.py` (correct `verified_support_origin_count` field, already plumbed to JSON only), `C:\POLARIS\src\polaris_graph\generator\both_sides.py` + `retrieval\dissent_recall_builder.py` (One-Sided), `C:\POLARIS\src\polaris_graph\roles\coverage_binder.py` + `generator\required_entity_ledger.py` (D5 coverage credit). No `source_necessity`/min-vertex-cover module exists — metric #6 must be built new.
# APPENDIX F — Gap: DRB-II
I have enough grounding across the forensic audit and the actual pipeline modules. Delivering.

---

# DeepResearch-Bench-II gap map for POLARIS — per-dimension, centered on the drb_72 re-smoke failures

**Target board (verified live 2026-06-30):** #1 = AI21-DeepResearch, Total **64.38** (InfoRecall 60.35 / Analysis 71.00 / Presentation 92.89). Outright-#1 requires **Total ≈ 66–68**, which because `Total ≈ 0.74·Recall + 0.18·Analysis + 0.08·Presentation` means **InfoRecall ≈ 63–65, Analysis ≈ 70, Presentation ≈ 92**. Presentation is saturated (12 of 16 systems >89) and cannot move the ranking; **the board is won on Recall first, Analysis second.**

## The one root cause under three of the four rows

The drb_72 run did not lose on faithfulness (0 fabrication, engine held). It lost because **the consolidation/basket layer never fired**, and it never fired because a **GPU-OOM cascade degraded every heavy on-GPU winner to a CPU or lexical floor**, while several winner flags were also default-OFF. Evidence from the run: `finding_dedup` corroboration distribution `{1: 56, 0: 2, 2: 1}` — exactly one merged pair in the whole run, and that pair (`finding_dedup.clusters[45]`, hosts `doi.org` + `journalijar.com`) is uncited and predatory. So all 12 cited claims are single-origin. That single fact collapses three DRB-II rows at once:

- **Recall** — baskets stayed singletons, so the breadth funnel had nothing consolidated to surface (12 of 88 cited).
- **Analysis** — M6 `cross_source_synthesis` can only relate TWO baskets that share a subject|predicate anchor; with all-singleton baskets it had no pairs to relate, so it emitted ~0 and "Comparative Assessment" rendered a gap stub.
- **Blocked-reference** — the mechanism that DRB-II uses to force independent multi-source support is exactly where POLARIS is designed to win; single-origin everything turns that structural advantage into an exposure (any rubric whose one cited source is the blocked article scores −1).

The GPU-OOM cascade (per the run + memory notes): on the crammed 2-GPU split W5 reranker + W6 embedder + W10 NLI co-resident on cuda:0 OOM'd → **semantic-relevance fell back to lexical**, **`consolidation_nli` fell back to CPU then hit its `PG_CONSOLIDATION_NLI_WALL_SECONDS` wall and under-merged**, and **GLM credibility-tiering degraded to the deterministic rules-floor** (which is why T1 labels sit on 0.08/0.38 weights and why the 1986 robotics paper and an OECD working paper headlined). The winners are BUILT; this run mostly ran them OFF or degraded.

## Master table

| Dimension (weight) | POLARIS now (drb_72) | #1 bar (AI21) | Gap | Exact fix (module · flag · change) |
|---|---|---|---|---|
| **Information Recall (74%)** | 12 of 88 corpus cited; `coverage_fraction` 0.571 (4/7 required entities); every cited claim single-origin; 13 fetched-but-unclassified lost at the retrieval wall; 808 dropped pre-fetch | 60.35 | **Very large — the decisive axis** | (1) `generator/weighted_enrichment.py` → set **`PG_BREADTH_ENRICHMENT_ENABLED=1`** (default OFF) to surface the full unbound span-verified SUPPORTS set into the "Corroborated Weighted Findings" section. (2) Fix the D5 coverage miscredit: bind `covered_element_ids` onto VERIFIED claims post-verification in `roles/coverage_binder.py` / `roles/native_gate_b_inputs.py` (the general `_claim_covers_entity` path, mirroring the S0 binder) so a span-verified robots/GPTs claim credits its required entity — `coverage_fraction` rises from 0.571. (3) Kill the GPU-OOM degrade (2-card device split + `PG_CONTENT_RELEVANCE_SCORE_CHUNK`) so `live_retriever` W2 semantic-relevance runs on GPU, not the lexical floor. (4) Raise `retrieval` classification throughput / wall so the 13 unclassified fetched sources enter the corpus. |
| **Analysis (18%)** | M6 `cross_source_synthesis` yielded ~0 ("Comparative Assessment" gap stub); `quantified_analysis` `firing_status=spec_validation_rejected` (286 numbers extracted, 0 modeled) | 71.00 | **Large** | (1) Restore multi-source baskets FIRST (see Recall) — M6 is downstream of consolidation. (2) `synthesis/consolidation_nli.py` → **`PG_CONSOLIDATION_NLI=1`** (default OFF) + fix its OOM/CPU-wall degrade so it actually merges paraphrase clusters into baskets. (3) `generator/cross_source_synthesis.py` → **`PG_CROSS_SOURCE_SYNTHESIS=1`** so the licensed `[clause A][relation][clause B]` composer runs once baskets exist. (4) Repair the quantified reject: `generator/quantified_analysis.py:511-525` — the Writer's spec dict is failing `build_quantified_spec` hard validation (datapoint-identity / formula-AST / material-dependency); read `telem["spec_reject_reason"]` from the run and fix the Writer prompt or loosen the specific gate that rejects, faithfulness-neutral. |
| **Presentation (8%)** | Deterministic render lands ~high, BUT in-prose chrome leaks (leaked "Introduction" header word, in-text "(1, 2)" ref markers, truncated "(2017)" with "Morrar et al." chopped); duplicate sentence (robots C3/C5); Abstract/Conclusion are disjoint verbatim lifts, not synthesized prose | 92.89 | **Small (table-stakes; cannot move rank)** | (1) `generator/chrome_furniture_screen.py` → extend the screen to PROSE, not just claim-bullets (the `render_chrome_canary` counts only bullets — MISS-3): strip leaked markdown headers, in-text `(N, N)` reference markers, and repair truncated leading subjects. (2) Dedup byte-identical repeated sentences at compose (the robots sentence appears twice in one subsection). Do NOT over-invest — Presentation is saturated across the board. |
| **Blocked-reference mechanism** | `retrieval/blocked_reference_registry.py` correctly hard-drops the named do-not-view paper across ~6 mirrors — but every cited claim is single-origin, so POLARIS's structural advantage did NOT materialize; the only corroborated pair is uncited + predatory | Independent multi-source support behind each rubric fact | **Advantage present but un-fired** | Same fix as Recall+Analysis: `consolidation_nli` ON + un-degraded + `weighted_enrichment` surfacing the full basket, so each cited claim carries ≥2 independent origins. This is the single biggest architectural edge on this board and it is one flag-plus-OOM-fix away from firing. |

---

## Dimension 1 — Information Recall (74%): the decisive axis

**POLARIS now.** Retrieval breadth exists at the front (88 sources fetched-and-classified, 98 fetched total, 101 candidates), but the corpus collapses at composition: only **12 sources cited**, `coverage_fraction` **0.571** = 4 of 7 required entities. Two independent leaks:

1. **The composition funnel** (memory's known "retrieved-but-not-composed"). The V30 contract render universe is the ~5 required contract entities plus a few LLM-planner picks; the ~437 span-verified SUPPORTS sources not bound to a `v30_entity_id` are never offered to any section. `weighted_enrichment.py` is the fix module (surfaces them into one field-agnostic section that flows through the unchanged `strict_verify`), but its master flag `PG_BREADTH_ENRICHMENT_ENABLED` defaults OFF → empty selection → byte-identical legacy funnel. **This run had the funnel.**
2. **The coverage miscredit (D5).** Two entities the body genuinely VERIFIES — robots-and-jobs [4] ("0.2 percentage points… 0.42%", claims 01-002/01-006 VERIFIED) and GPTs-are-GPTs [7] ("just over 46% of jobs", claims 02-009/02-010 VERIFIED) — carry **empty `covered_element_ids`** in `four_role_settled_verdicts.jsonl`, so `required_entity_coverage` scores them as gaps and the report simultaneously presents and disowns them. That drops coverage from a true ~6/7 to the reported 4/7 = 0.571, which held D8 `release_allowed=False`.

Plus two recall leaks at the wall and the OOM: **13 fetched sources were left unclassified** when `retrieval_wall_hit=true`, and **semantic-relevance degraded to lexical** on GPU-OOM, both of which shrink the on-topic corpus that reaches composition.

**#1 bar / gap.** AI21 InfoRecall 60.35; target ~63+. POLARIS's rendered recall here is far below that — the corpus is wide but the report is narrow. The gap is not retrieval, it is **surfacing**.

**Exact fix (priority order):** flip `PG_BREADTH_ENRICHMENT_ENABLED=1`; bind `covered_element_ids` on verified claims (general path in `coverage_binder.py`/`native_gate_b_inputs.py`); un-degrade GPU (device split so `live_retriever` W2 stays on the reranker, not lexical); raise the retrieval-wall classification budget so the 13 unclassified enter.

## Dimension 2 — Analysis (18%): blocked behind consolidation

**POLARIS now.** Two analysis producers, both silent this run:

- **M6 `cross_source_synthesis.py`** emits an analytical sentence only when two baskets share a normalized `subject|predicate` anchor AND a relation is licensed (a `ClaimGraph` ContradictionEdge or the agreement map). With every basket a singleton, there were **no pairs to relate** → ~0 output, "Comparative Assessment" gap stub. M6 is not broken; it is starved by the un-fired consolidation upstream. Its own flag `PG_CROSS_SOURCE_SYNTHESIS` also gates it.
- **`quantified_analysis.py`** reached `spec_validation_rejected` (`generator/quantified_analysis.py:515`): the Writer returned a spec dict that failed `build_quantified_spec` hard validation (datapoint-identity / formula-AST / material-dependency). 286 sourced numbers were extracted, **0 modeled**. That is why the quantified comparison — the natural home for DRB-II Analysis rubrics (cross-study deltas) — rendered nothing.

**#1 bar / gap.** AI21 Analysis 71.00; target ~70. Large gap — POLARIS rendered essentially no synthesized analysis.

**Exact fix.** Order matters: (1) get multi-source baskets back (Recall fixes + `PG_CONSOLIDATION_NLI=1` un-degraded); (2) `PG_CROSS_SOURCE_SYNTHESIS=1`; (3) read the durable `telem["spec_reject_reason"]` (wired at `quantified_analysis.py:509`) from the drb_72 manifest to see which validation gate rejected, then fix the Writer spec prompt or the specific over-strict gate — faithfulness-neutral, the sandbox execution and token-binding downstream are unchanged.

## Dimension 3 — Presentation (8%): table-stakes, do not over-invest

**POLARIS now.** The deterministic render is structurally strong but leaks three cosmetic defects that also cost DeepTRACE's Relevant-Statement metric on the sister board: a leaked markdown section header word ("Introduction" opening A5), the source's own in-text reference markers ("(1, 2)" in C5), and a **truncated leading subject** ("(2017) outlined reasons…" with "Morrar et al.," chopped off in C4). Plus a byte-identical duplicate sentence (robots C3 = C5). The `render_chrome_canary` reports pass because it counts only claim-bullets and is blind to prose (MISS-3).

**#1 bar / gap.** AI21 Presentation 92.89; field clusters 90–94. Small gap — but chrome and truncation are cheap points and they also help the DeepTRACE axis, so fix them, then stop.

**Exact fix.** Extend `generator/chrome_furniture_screen.py` from claim-bullets to prose (strip leaked headers + in-text `(N, N)` markers + repair a truncated leading subject); dedup repeated sentences at compose. This is polish, not a rank-mover on DRB-II.

## Dimension 4 — Blocked-reference: POLARIS's biggest edge, un-fired this run

**POLARIS now.** `retrieval/blocked_reference_registry.py` parses the do-not-view appendix and hard-drops the named paper across URL/DOI/PII/title mirrors — the correct machinery to avoid the DRB-II −1 leakage penalty. But the penalty is about **whether each satisfied rubric has INDEPENDENT support**; with all 12 cited claims single-origin, POLARIS carries exactly the exposure the mechanism punishes, and the one genuinely corroborated pair is uncited and predatory (`journalijar.com`). So the design advantage scored zero this run.

**#1 bar / gap.** The bar is independent multi-source support behind each rubric fact — precisely POLARIS's weight-and-consolidate DNA. The gap is not architectural; it is the same un-fired consolidation layer.

**Exact fix.** `PG_CONSOLIDATION_NLI=1` un-degraded (so paraphrase clusters merge into ≥2-origin baskets) + `PG_BREADTH_ENRICHMENT_ENABLED=1` (so those multi-origin baskets actually reach citation). Once baskets carry ≥2 distinct hosts, every headline claim becomes independently corroborated and the blocked-ref mechanism flips from exposure to advantage.

---

## Also-fix (surfaced by the run, feeds Recall + credibility coherence)

- **D4 off-topic / wrong-genre headlining (M2 document-type weighting OFF).** The 1986 robotics paper [11] (weight 0.08), a T4 Frontiers forecast [8], and an OECD working paper [12] (not a journal) headlined the Abstract while the question demanded "high-quality journal articles only." Root: GLM credibility-tiering (`credibility_llm_tiering.py`, `PG_CREDIBILITY_LLM_TIERING`) degraded to the rules-floor on GPU/transport failure, and the M2 genre/document-type weight was off. Fix: keep GLM tiering on GPU (un-degrade) and turn on document-type weighting so genre (journal vs working-paper vs blog) enters the ordering weight. Weight, do not drop, per §-1.3.
- **D6 cross-artifact weight incoherence.** Disclosed weights (0.06/0.06/0.08) contradict `corpus_credibility_disclosure` (0.30/0.15/0.60) for the same URLs, and T1 labels sit on 0.08/0.38 weights. This is a disclosure/telemetry reconcile in the credibility-disclosure writer, not a faithfulness change.
- **D8 judge false-negatives (3 grounded top-journal claims marked unsupported).** Safe-direction (under-claim), but they render `[confidence: low]` on verbatim-grounded Autor/Brynjolfsson/Eloundou claims and depress the perceived recall. The 3 false-negatives (00-006, 02-001, 02-002) each have a byte-identical twin marked VERIFIED at the same offset — the D8 judge is internally inconsistent. Faithfulness engine is FROZEN; treat as a judge-reliability item (retry/quorum), not a gate change.

## Sequencing (what actually moves the two scoreboards)

1. **Fix the GPU-OOM cascade** (device split so W5 reranker / W6 embedder / W10 NLI are not co-resident on cuda:0). This single infra fix un-degrades semantic-relevance, `consolidation_nli`, and GLM credibility-tiering together — it is the lever under Recall + Analysis + Blocked-ref.
2. **Flip the built-but-OFF winner flags:** `PG_CONSOLIDATION_NLI`, `PG_BREADTH_ENRICHMENT_ENABLED`, `PG_CROSS_SOURCE_SYNTHESIS`, GLM tiering + M2 document-type weighting.
3. **Two genuine code fixes:** the general `covered_element_ids` coverage binder (D5) and the `quantified_analysis` spec-validation repair.
4. **One polish pass:** prose chrome + dedup in `chrome_furniture_screen.py`.

None of the above touches the frozen faithfulness engine (strict_verify / NLI entailment / 4-role D8 / provenance / span-grounding). Every change is a WEIGHT, a CONSOLIDATION, a surfacing, or a degrade-fix — consistent with §-1.3. The DRB-II deficit is that the pipeline's winners ran OFF or GPU-starved this run, not that the architecture is missing.

**Files named (all absolute):** `C:\POLARIS\src\polaris_graph\generator\weighted_enrichment.py`, `C:\POLARIS\src\polaris_graph\generator\cross_source_synthesis.py`, `C:\POLARIS\src\polaris_graph\generator\quantified_analysis.py` (lines 511-525 reject gate, 509 reason telemetry), `C:\POLARIS\src\polaris_graph\generator\chrome_furniture_screen.py`, `C:\POLARIS\src\polaris_graph\synthesis\consolidation_nli.py`, `C:\POLARIS\src\polaris_graph\synthesis\finding_dedup.py`, `C:\POLARIS\src\polaris_graph\retrieval\credibility_llm_tiering.py`, `C:\POLARIS\src\polaris_graph\retrieval\blocked_reference_registry.py`, `C:\POLARIS\src\polaris_graph\roles\coverage_binder.py`, `C:\POLARIS\src\polaris_graph\roles\native_gate_b_inputs.py`, `C:\POLARIS\src\polaris_graph\generator\required_entity_ledger.py`. Forensic source: `C:\POLARIS\.codex\I-deepfix-001\RESMOKE_S11_FORENSIC_AUDIT.md`.
# APPENDIX G — Gap: residual defects
I have every root cause pinned to exact file:line. Compiling the deliverable now. (Per standing guidance I am not calling the Opus advisor, and I am returning findings as text, not a report file.)

---

# I-deepfix-001 — drb_72 residual defects D1–D6 + run-level weaknesses: code-traced root causes, surgical fixes, board-metric map

Scope note on §-1.3: every fix below is WEIGHT-or-DISCLOSURE-or-RENDER only. The faithfulness engine (strict_verify / NLI / 4-role D8 / span-grounding / provenance) is untouched; no source is dropped; each fix is kill-switched (LAW VI) and default-ON only where it strictly reduces an over-claim or repairs an internal contradiction.

---

## D1 — Eloundou "46% of jobs" renders CLEAN in the Conclusion, low-confidence caveat stripped (PRIORITY, over-claim)

**Root cause (exact).** Two seams, one ordering gap:
- `abstract_conclusion._harvest_conclusion_sentences` (`src/polaris_graph/generator/abstract_conclusion.py:139-159`) re-lifts each section's LAST span-verified sentence verbatim from `SectionResult.verified_text` — the RAW pre-annotation section prose. `build_conclusion` runs at `scripts/run_honest_sweep_r3.py:13628`.
- The confidence label is applied LATER by `report_redactor.annotate_report_against_verdicts` (`src/polaris_graph/roles/report_redactor.py:677-784`) at `run_honest_sweep_r3.py:15371`. Ordering is fine (13628 < 15371, so the annotator DOES see the assembled Conclusion), but the annotator keys on **claim_id → stem** (`_nonverified_verdicts` / `_marker_by_claim`, built 15357-15369).
- The 46% figure exists as TWO differently-worded composed sentences bound to DIFFERENT claim_ids: the Key-Findings copy `02-002` (D8=UNSUPPORTED → in `annotated_claim_ids` → labelled) and the Eloundou-section closing copy `02-010`/`02-009` (D8=VERIFIED → NOT in the set → clean). The Conclusion re-lifts the VERIFIED twin. There is **no figure-level (evidence_id + numeric-token) consistency pass** anywhere, so the annotator cannot know the two surfaces carry the same number, and the clean twin ships beside the flagged twin.

**Surgical fix.** Add a post-annotation figure-consistency propagation (new helper in `report_redactor.py`, called immediately after `annotate_report_against_verdicts` at `run_honest_sweep_r3.py:~15376`): for each annotated low-confidence claim carrying a numeric token bound to `evidence_id E` and figure `F`, scan every rendered sentence that cites the SAME `[N]→E` and contains the SAME numeric `F`; if such a sentence is un-annotated, append the identical confidence marker. It only ADDS caveats (safe direction), never removes; strips-then-matches on `_prose_stem` so it is idempotent (`_CONFIDENCE_MARKER_RE`, report_redactor.py:104). Kill-switch `PG_FIGURE_CONSISTENCY_ANNOTATE=1` (default-ON); OFF = byte-identical. Faithfulness-neutral: no span widened, no verdict changed, no source dropped.

**Board metric moved.** DeepTRACE **citation-accuracy / unsupported-rate** (the only distortion reaching CLEAN prose — a self-flagged-uncertain number presented as settled) + DeepTRACE consistency.

---

## D2 — "1 verified independent source" printed where basket `verified_support_origin_count=0` (PRIORITY, over-claim)

**Root cause (exact).** `_render_bibliography_lines`'s per-claim corroboration block, `scripts/run_honest_sweep_r3.py:2543-2570`. Under the default-ON `PG_CORROBORATION_BIBLIO_PRESENT` gate the count is RECOMPUTED from render-side member labels:
```
verified = [m for m in members if m["member_tier"] == "ENTAILMENT_VERIFIED"]   # 2546-2549
verified = [m for m in verified if _is_biblio_present(m)]                        # 2559
count = len({m["origin_cluster_id"] or m["evidence_id"] for m in verified})     # 2560-2562
```
It does **not** reconcile against the basket's authoritative CONSOLIDATE-leg field `basket.verified_support_origin_count` (the else-branch at 2570 reads it, the ON-branch ignores it). For baskets [6]/[8] the cited source self-entails against its own citation-chrome span → its member is labelled `ENTAILMENT_VERIFIED` and is biblio-present (it IS the cited `[N]`), so `count=1`, while `credibility_pass` computed `verified_support_origin_count=0` / `basket_verdict="unverified"` (`src/polaris_graph/synthesis/credibility_pass.py:900`). The two disagree; the render trusts the looser recompute → over-count. Line 2661 then prints `f"- **{claim}** — {count} verified independent source(s)"`.

**Surgical fix.** Clamp the printed count to the authoritative field and route unverified members to the disclosed-weak line (§-1.3 no-drop): at 2558-2568, after the biblio-present recompute, `count = min(count, int(basket.get("verified_support_origin_count") or 0))`; when the authoritative count is 0 (or `basket_verdict=="unverified"`), emit the members under the existing `GROUNDED-BUT-WEAK` sub-bullet (2669-2676) instead of `SUPPORT`, and set the header suffix to "0 verified independent source(s)". Sources + counts stay in the numbered Bibliography. Kill-switch `PG_CORROBORATION_COUNT_AUTHORITATIVE=1` (default-ON); OFF keeps today's recompute. Faithfulness-neutral: strictly REDUCES an inflated count, never inflates breadth.

**Board metric moved.** DeepTRACE **citation-accuracy** (a false corroboration count is the report's disclosure being stronger than its evidence) + DeepTRACE unsupported-rate.

---

## D3 — In-prose chrome still leaks ("Introduction" header word, in-text "(1, 2)" markers, truncated "(2017)" subject); canary blind

**Root cause (exact).** Two blind spots:
1. `evaluate_render_chrome_canary` (`src/polaris_graph/generator/weighted_enrichment.py:1528-1551`) computes `chrome_as_claim_rate` over `_report_claim_bullets` ONLY (`weighted_enrichment.py:1517-1525`, `_TOP_LEVEL_BULLET_RE.match`). It never inspects PROSE — Abstract/Conclusion paragraphs and `###` body prose — so `chrome_as_claim_rate=0.0, 0/33 bullets, verdict pass` while prose chrome ships.
2. The three leaks survive every screen because `is_render_chrome_or_unrenderable` returns False on a mostly-real sentence: (a) the bare leaked header word "Introduction" — `_strip_leading_markdown_headers` (`abstract_conclusion.py:115`) strips the markdown `## 1. Introduction` but leaves "Introduction" welded as the sentence's first word; (b) the source's own in-text ref markers "(1, 2)" bleed through the verbatim lift; (c) the leading-subject truncation "(2017) outlined…" — the subject "Morrar et al.," was chopped at a sentence BOUNDARY, which the mid-word `citation_truncation_normalizer` does not catch.

**Surgical fix (two parts).**
- Un-blind the canary: add `_report_prose_units(report_text)` beside `_report_claim_bullets` (split non-header, non-bullet lines into sentences) and feed both to `evaluate_render_chrome_canary` (weighted_enrichment.py:1535). Kill-switch `PG_RENDER_CHROME_CANARY_PROSE=1` (default-ON); OFF = bullets-only (today's behaviour). Telemetry + enforce both then see prose.
- Add a leading/inline prose-chrome normalizer applied per-unit at the existing render-seam chokepoint (`multi_section_generator.py:1557` region, inside `_sanitize_report_line`): (i) strip a leading bare section-header word (`^(Introduction|Abstract|Methods|Conclusion|References)\s+` before a capitalized sentence), (ii) strip source in-text numeric ref markers `\((\d+(,\s*\d+)*)\)` when not a provenance/`[N]` token, (iii) flag+withhold a sentence whose leading subject is truncated (starts with `\(\d{4}\)` or a lowercase continuation). Cosmetic text-only; never drops a source, number, or `[#ev:]` token. Kill-switch `PG_PROSE_CHROME_NORMALIZE=1`.

**Board metric moved.** DeepResearch-Bench-II **presentation** + DeepTRACE **thoroughness/readability** (chrome-free asserted prose).

---

## D4 — Off-topic / wrong-genre sources still headline; "journal articles only" disclosed-but-unmet because M2 was OFF

**Root cause (exact).** M2 (document-type weighting) exists and is wired but is behind a **double gate that is OFF by default**: `_m2_journal_pref_active` (`scripts/run_honest_sweep_r3.py:2696-2708`) returns True only if `PG_DOCUMENT_TYPE_WEIGHT=1` AND the raw scope template declares `document_type_preference: journal_article` (via `document_type_classifier.document_type_weighting_active`). The drb_72 template did not set the preference and the env flag was unset, so `journal_preference_active=False` at the render call (`run_honest_sweep_r3.py:13417`) and again at the corpus-disclosure builder (`run_honest_sweep_r3.py:10003-10007`). Result: `_m2_bib_genre` (2711-2724, tier_prior × document_type_weight display re-rank + genre tag) never fires, so the 1986 J. Operations Mgmt robotics paper (weight 0.08), T4 Frontiers, and the OECD working paper (not a journal) headline unchanged.

**Surgical fix (§-1.3 WEIGHT-don't-FILTER).** Activate M2 for journal-only questions — NO source is dropped, only genre-tagged and re-ranked in the display/corroboration order: (1) set `document_type_preference: journal_article` in the scope template for the journal-only question class (config, `config/scope_templates/…`), and (2) auto-detect the "journal articles only" constraint from the question text OR default `PG_DOCUMENT_TYPE_WEIGHT=1` so the double gate satisfies. `resolve_document_type_weight` then down-weights working-paper / encyclopedia / repository-PDF / preprint genres in the corroboration re-rank and appends a per-citation genre tag; every entry stays in the Bibliography (weight, not filter). Kill-switch is the existing `PG_DOCUMENT_TYPE_WEIGHT` (keep default-OFF globally, ON via the template preference for journal-only runs).

**Board metric moved.** DeepResearch-Bench-II **analysis + presentation** (headline sources match the question's high-quality-journal constraint) + DeepTRACE **source-quality**.

---

## D5 — "Coverage gaps" says robots-and-jobs[4] + GPTs[7] "not verified" while the body VERIFIES them; `required_entity_coverage=0.571` miscredits

**Root cause (exact).** `required_entity_ledger.verified_covered_ids` (`src/polaris_graph/generator/required_entity_ledger.py:109-130`) credits an entity only from `row["covered_element_ids"]` of claims whose `final_verdicts[claim_id]=="VERIFIED"` (128-129). The four_role_settled_verdicts rows for the VERIFIED robots-jobs (01-002/01-006) and eloundou (02-009/02-010) claims carry **empty `covered_element_ids`**, so `build_ledger` (137-168) marks entities S1/S2 `STATE_GAP_DISCLOSED` (163) despite the body verifying them → `coverage_fraction=0.571` (4/7) and a self-contradiction. The empty set originates UPSTREAM in the pre-D8 builder audit map: `native_gate_b_inputs.build_native_gate_b_inputs` populates `covered_element_ids` via the S0 clinical content-requirement conjunction (`_content_requirements_satisfied_impl`, the same path `coverage_binder.py` credits), which does NOT fire for research-TOPIC entities (robots-and-jobs, GPTs) — only for S0 contraindication/population-anchor entities.

**Surgical fix (additive credit, faithfulness-safe).** Extend the pre-D8 coverage credit in `native_gate_b_inputs` (mirroring the `coverage_binder.py` additive pattern) so a required TOPIC entity is credited to a claim when that claim CITES an `evidence_id` whose canonical identifier matches the entity (`_entity_canonical_match`), not only when the clinical content conjunction fires. D8 still gates downstream (`verified_covered_ids` counts only `VERIFIED` claims — 128), so this cannot over-claim faithfulness: the crediting claim is already span-verified and already cites the entity's source. Kill-switch `PG_ENTITY_COVERAGE_CITATION_CREDIT=1` (default-OFF; ON for research questions). Fixes `coverage_fraction` (4/7 → 6/7) AND removes the MISS-1 self-contradiction.

**Board metric moved.** DeepResearch-Bench-II **coverage / recall** (`coverage_fraction` up) + it un-holds the D8 release gate (`release_allowed=False` was partly driven by 0.571 coverage), and removes a §-1.1 self-contradiction (DeepTRACE consistency).

---

## D6 — Contradiction disclosure says "1" vs actual 3; cross-artifact weight incoherence (T1 label on 0.08/0.38 weights; disclosed 0.06 vs credibility-file 0.30)

**Root cause (exact), part A (count).** `run_honest_sweep_r3.py:13254-13261`: the disclosure header prints `len(renderable_contradictions)` where `renderable_contradictions = [c for c in contradictions if not _is_unconfirmed_metric_mismatch(c)]` (13254-13256). The two `possible_metric_mismatch` flags are excluded (they render only in Limitations), leaving 1, while `manifest.contradictions_found = len(contradictions) = 3` (`run_honest_sweep_r3.py:14544`) and Limitations accounts for all 3. No single place states the true total → internal inconsistency.

**Root cause, part B (weight incoherence).** The corroboration block prints each member's authority-adjusted `credibility_weight` (`run_honest_sweep_r3.py:2663-2667`, e.g. 0.08/0.38), whereas `corpus_credibility_disclosure` prints the raw `tier_prior` (`weight_basis=tier_prior`, 0.95/0.30) for the same URL. Two different quantities are both labelled "credibility weight," yielding reader-irreconcilable "T1 / 0.08" pairings.

**Surgical fix.**
- Count: state the full detector total AND the screened split so the numbers reconcile: change 13260 to `f"The contradiction detector flagged {len(contradictions)} numeric disagreement(s) ({len(renderable_contradictions)} shown below; {len(contradictions)-len(renderable_contradictions)} screened as not-comparable / unconfirmed metric mismatch)."` Kill-switch `PG_CONTRADICTION_TOTAL_HONEST=1` (default-ON). Disclosure-only; no detector record dropped (§-1.3 — they stay in contradictions.json).
- Weight coherence: surface `weight_basis` next to every printed weight so the two artifacts are self-describing — in the corroboration block label it "authority-adjusted weight" and in the disclosure "tier prior", OR render both numbers on each line (`tier T1, tier-prior 0.95, authority-adjusted 0.08`). Kill-switch `PG_WEIGHT_BASIS_LABEL=1`. Display-label only; no weight recomputed.

**Board metric moved.** DeepTRACE **citation-accuracy / consistency** + DeepTRACE **one-sided** (complete, reconcilable both-sides disclosure).

---

## Run-level weaknesses (root + surgical direction)

- **Coverage 0.571, D8 held `release_allowed=False`** → same root as D5 (empty `covered_element_ids` on verified topic-entity claims); the D5 citation-credit fix raises it and un-holds the gate.
- **Only 12 of 88 corpus cited; ZERO genuine multi-source corroboration (§-1.3 basket-consolidation did not fire)** → `finding_dedup` corroboration distribution `{1:56, 0:2, 2:1}`; the lone ≥2-origin cluster (`clusters[45]`, journalijar.com predatory) is uncited. Root: `finding_dedup`/consolidation clustered near-nothing because upstream W2/credibility degraded (below) shrank the SUPPORTS pool. Not a render fix — it is downstream of the GPU-OOM lexical fallback + GLM-tiering degrade; fixing those re-enables real baskets. No new cap/thinner (that would fight §-1.3).
- **GLM credibility-tiering DEGRADED to rules-floor** and **GPU-OOM → semantic-relevance fell back to lexical (W2)** → device-split env + `PG_CONTENT_RELEVANCE_SCORE_CHUNK` bounding (the proven 2026-06-30 fixes) so the LLM legs actually run; these two degrades are the upstream cause of the thin single-origin corpus above.
- **Retrieval wall hit (13 unclassified)** → honestly disclosed (M4); raise the internal retrieval wall for the slow tiering leg so the 13 fetched-but-unclassified rows get classified (breadth surfaced, not forced).
- **Quantified section `spec_validation_rejected`** → disclosed silent-no-op (manifest `quantified_silent_no_op=true`); separate spec-validation defect, out of the D1–D6 render scope.
- **D8 GLM judge 3 false-negative "unsupported" on grounded top-journal claims (02-001/02-002/00-006)** → frozen-engine noise; the D1 figure-consistency pass makes the DISCLOSURE consistent, and the operator-flagged judge-model swap (availability/provider-count) is the real remedy. Do NOT edit the faithfulness engine.

---

## Summary table

| Defect | Root-cause module (file:line / function) | Surgical fix (faithfulness-neutral, kill-switched, §-1.3) | Board-metric moved |
|---|---|---|---|
| **D1** 46% caveat stripped in Conclusion | `abstract_conclusion.py:139-159` re-lift of raw `verified_text` + per-claim-id annotator `report_redactor.py:677-784` (call `run_honest_sweep_r3.py:15371`); no figure-level pass | Post-annotation figure-consistency propagation: same `[N]→E`+number gets the same low-confidence marker (adds caveats only). `PG_FIGURE_CONSISTENCY_ANNOTATE=1` | DeepTRACE citation-accuracy / unsupported-rate + consistency |
| **D2** "1 verified independent source" where count=0 | `run_honest_sweep_r3.py:2558-2570` (ON-branch recomputes from biblio-present `ENTAILMENT_VERIFIED` members, ignores `verified_support_origin_count`); prints 2661 | `count = min(recompute, basket.verified_support_origin_count)`; route unverified members to `GROUNDED-BUT-WEAK`, header "0 …". `PG_CORROBORATION_COUNT_AUTHORITATIVE=1` | DeepTRACE citation-accuracy / unsupported-rate |
| **D3** in-prose chrome ("Introduction", "(1,2)", "(2017)" truncation) | canary bullets-only `weighted_enrichment.py:1517-1551`; leading-header-word survives `abstract_conclusion.py:115`; boundary-truncation missed by mid-word normalizer | Add `_report_prose_units` to the canary (`PG_RENDER_CHROME_CANARY_PROSE=1`) + per-unit prose-chrome normalizer at the render seam `multi_section_generator.py:~1557` (`PG_PROSE_CHROME_NORMALIZE=1`) | DeepResearch-Bench-II presentation + DeepTRACE thoroughness |
| **D4** off-topic/wrong-genre headline; journal-only unmet | M2 double-gate OFF: `_m2_journal_pref_active` `run_honest_sweep_r3.py:2696-2708`; render call `:13417`, disclosure `:10003` | Set template `document_type_preference: journal_article` + activate `PG_DOCUMENT_TYPE_WEIGHT=1` for journal-only Qs → `_m2_bib_genre` genre-tags + re-ranks (WEIGHT not filter; no drop) | DeepResearch-Bench-II analysis/presentation + DeepTRACE source-quality |
| **D5** verified robots/GPT entities shown "not verified"; coverage 0.571 | empty `covered_element_ids` on VERIFIED topic claims → `required_entity_ledger.py:109-130` / `build_ledger:137-168`; upstream `native_gate_b_inputs` credits only S0 clinical conjunction | Additive pre-D8 credit: topic entity covered when a VERIFIED claim CITES its canonical-matching evidence_id. `PG_ENTITY_COVERAGE_CITATION_CREDIT=1` | DeepResearch-Bench-II coverage/recall + un-holds D8 release gate + consistency |
| **D6** contradiction count 1 vs 3; weight incoherence | count `run_honest_sweep_r3.py:13254-13261` prints `len(renderable_contradictions)` vs `contradictions_found=3` `:14544`; weight `:2663-2667` prints authority-adjusted vs disclosure tier_prior | State full total + screened split (`PG_CONTRADICTION_TOTAL_HONEST=1`); label `weight_basis` on every printed weight (`PG_WEIGHT_BASIS_LABEL=1`) | DeepTRACE citation-accuracy/consistency + one-sided |

**Files for the fix diff (absolute):** `C:/POLARIS/scripts/run_honest_sweep_r3.py` (D2 2558-2570, D4 2696-2708/13417, D6 13254-13261/2663-2667, D1 caller ~15376), `C:/POLARIS/src/polaris_graph/roles/report_redactor.py` (D1 new helper), `C:/POLARIS/src/polaris_graph/generator/weighted_enrichment.py` (D3 canary 1517-1551), `C:/POLARIS/src/polaris_graph/generator/multi_section_generator.py` (D3 prose normalizer ~1557), `C:/POLARIS/src/polaris_graph/generator/abstract_conclusion.py` (D3 leading-header strip 115), `C:/POLARIS/src/polaris_graph/generator/required_entity_ledger.py` + `C:/POLARIS/src/polaris_graph/roles/native_gate_b_inputs.py` (D5 citation credit). Every fix ships a fail-loud behavioral replay-harness assertion (per §-1.4 wiring standard); a banked corpus_snapshot replay validates D1/D2/D5/D6 (render/coverage layer) but D3/D4 need a FRESH front-half run because 154/155 banked spans are pre-fix truncated and M2 re-ranks retrieval-time genre — a banked replay is structurally blind to both.
# APPENDIX H — Gap: pipeline structural
I have traced every claim to the actual code. Below is the deliverable.

---

# POLARIS drb_72 — deep structural root-cause review (I-deepfix-001, HEAD d0f9d5db)

## The spine: five winner modules are wired but shipped DEFAULT-OFF, and the D8 enum is unenforceable off-vLLM

Every blocker below traces back to one of these. The machinery §-1.3 demands EXISTS; it was authored, gated, and then left behind a default-off flag or an unenforced constraint, so the run degraded to the FILTER-and-DROP legacy path the architecture forbids.

| Flag / seam | Default | File:line | Effect when off/unenforced |
|---|---|---|---|
| `PG_CONSOLIDATION_NLI` | **OFF ("0")** | `synthesis/consolidation_nli.py:92` | same-claim paraphrase baskets never form → corroboration_count stuck at 1 |
| `PG_CROSS_SOURCE_SYNTHESIS` | **OFF** | `generator/verified_compose.py:167-168` | M6 analytical layer never invoked → analysis yield 0 |
| `PG_DOCUMENT_TYPE_WEIGHT` | **OFF ("0")** | `retrieval/document_type_classifier.py:214-219` | wrong-genre (working-paper / 1986 / T4) sources not down-weighted |
| `PG_JOURNAL_ONLY` | **OFF ("0")** | `nodes/journal_only_filter.py:62-64` | "journal articles only" constraint disclosed but not enforced |
| Judge enum `structured_outputs.choice` | **unenforced off-vLLM** | `roles/judge_adapter.py:229-231` | OpenRouter ignores the vLLM-only key → off-enum + 429 degrade each claim to UNSUPPORTED |

The GLM tiering degrade (`retrieval/credibility_llm_tiering.py:20,77`) then compounds it: on a trickle/429/blank-200 storm every source falls to the deterministic rules-floor (`rules_floor_degraded`), which is why the disclosed weights are incoherent with the credibility file (D6).

---

# PART A — the 6 residual render defects (defect | data-flow root cause | surgical fix)

## D1 (PRIORITY) — Eloundou "46%" re-lifted CLEAN in the Conclusion, low-confidence label + conditional qualifier both stripped
- **Root cause.** The Abstract/Conclusion re-lift (`generator/abstract_conclusion.py`) copies the verbatim body span for claim `02-010` (Conclusion) which is a byte-twin of the body claim `02-002` (Key Findings). The low-confidence caveat is attached via `report_annotation.annotated_claim_ids = ["…02-002-af53af14", …]` — keyed on the *specific claim_id*. The twin `02-010` carries a DIFFERENT claim_id, so the annotation lookup misses and the Conclusion prints clean. Separately, the composer lifted only the `"…46% of jobs"` sentence-unit and not the conditional antecedent (`"could have over half their tasks affected … when accounting for … software developments that complement LLM capabilities"`) that is in the SAME span (idx 588) — a first-sentence-unit reduction identical to `cross_source_synthesis._first_verified_clause:207` (`units[0]`).
- **Fix (faithfulness-neutral, header/annotation only, per the I-wire-014 §-1.4 precedent).** Re-key the confidence annotation on a span-identity tuple `(evidence_id, cited_start, cited_end)` or a normalized-sentence hash instead of `claim_id`, so ALL byte-twins of a labelled claim inherit the label at render. Add an effect-size guard leg in `generator/overstatement_guard.py`: when a re-lifted numeric sentence's cited span contains a governing conditional/threshold token adjacent to the number (`"when accounting for"`, `"could have"`, `"over half"`), require the antecedent clause to travel with the number or append the `[confidence: …]` tag. Both are render-layer; strict_verify untouched.

## D2 (PRIORITY) — "Source corroboration" prints "1 verified independent source" where the basket's `verified_support_origin_count = 0`
- **Root cause.** The projection `provenance_generator._basket_for_biblio` (`provenance_generator.py:3374-3386`) exposes BOTH `verified_support_origin_count` (0 — the isolated span-verified origins) AND the member list `supporting_members` (length 1). The corroboration bullet builder (the CWF `_basket_corroboration_block` path) counts `len(supporting_members)` / `total_clustered_origin_count` (=1) instead of `verified_support_origin_count` (=0). The block header promises "count of independently VERIFIED sources" but renders the clustered member count.
- **Fix.** In the corroboration-block builder read `verified_support_origin_count` (the field the projection already isolates at `provenance_generator.py:3374`) as the printed integer; when it is 0, render the basket as `unverified — 0 verified independent sources` rather than "1". This mirrors `synthesis/disclosure_population.py:172-197`, which already correctly buckets certainty on `verified_support_origin_count` and NEVER on `total_clustered_origin_count`. One field swap; faithfulness-neutral.

## D3 — in-prose chrome still leaks; the canary only counts claim-bullets
- **Root cause.** `evaluate_render_chrome_canary` (`weighted_enrichment.py:1528`) scores only `_report_claim_bullets(report_text)` (`:1517`) — claim bullets. Body prose lifted verbatim from source spans carries the source's own chrome: the leaked `"Introduction"` section header (from `"## 1. Introduction …"`), in-text ref markers `"(1, 2)"`, and the truncated `"(2017)"` where `"Morrar et al.,"` was chopped by the span-snap boundary. `is_render_chrome_or_unrenderable` (`:1401`) exists but is applied at the claim-unit seam, not over composed prose sentences.
- **Fix.** Extend the render-seam sanitize pass (`render_seam_sanitize_enabled`, `weighted_enrichment.py:1642`, already default-ON) to run `_is_residual_chrome_furniture` + a leading-bare-`(YYYY)` / leading-lone-header-word check over EVERY composed body sentence, not just bullets, and widen the canary denominator to all rendered sentences. Strip a leading `"Introduction"`/section-header token and repair a leading orphan `"(2017)"` by re-attaching the subject from the cited span (the I-wire-014 hyphen-repair pattern). Render-layer only.

## D4 — off-topic / wrong-genre sources still headline; "journal articles only" disclosed-but-unmet
- **Root cause.** The intake extracted the "high-quality journal articles ONLY" constraint and disclosed it, but the two enforcement mechanisms are off: `PG_DOCUMENT_TYPE_WEIGHT` (`document_type_classifier.py:214-219`) default OFF and it is a DOUBLE gate (`:225` — flag ON *and* the protocol must declare `document_type_preference`), and `PG_JOURNAL_ONLY` (`journal_only_filter.py:62-64`) default OFF. So the 1986 J.Operations-Mgmt robotics paper (weight 0.08), the T4 Frontiers forecast, and the OECD working paper carry no genre penalty and are promoted by `weighted_enrichment` on weight alone.
- **Fix.** Turn on `PG_DOCUMENT_TYPE_WEIGHT=1` for this question class and populate the protocol's `document_type_preference=journal` so the double gate (`:225`) fires; the `DEFAULT_DOCUMENT_TYPE_WEIGHTS` multiplicative surface weight (`:196`) then demotes working-paper/preprint/encyclopedia genres. Keep it a WEIGHT (§-1.3), NOT `PG_JOURNAL_ONLY` hard-drop — a demoted non-journal stays in the basket at low weight and is simply out-ranked for the headline slots. Add a publication-year recency leg so a 1986 pre-AI paper cannot headline an AI-labor review.

## D5 — "Coverage gaps" says robots-and-jobs[4] + GPTs[7] "not verified" while the body VERIFIES them
- **Root cause.** `native_gate_b_inputs._claim_covers_entity` (`native_gate_b_inputs.py:515-536`) credits an entity ONLY when `_entity_canonical_match` holds — the verified claim must cite evidence whose canonical DOI/PMID/full-URL EXACTLY matches the required-entity's declared canonical id (`:532`). The build loop (`:707-717`) fills `covered_element_ids` from that test per verified sentence. Entity [4] `acemoglu_restrepo_robots_jobs` has an EMPTY `url` in bibliography.json (DOI-only), and the required-entity's declared canonical id did not line up with the evidence record's canonical id, so `_entity_canonical_match` returned False → `covered_element_ids` empty on genuinely-VERIFIED claims 01-002/01-006 and 02-009/02-010. `required_entity_ledger.verified_covered_ids` (`required_entity_ledger.py:109-129`) then computes `coverage_fraction = 4/7 = 0.571` and `render_coverage_gaps_section` (`:171`) lists the two verified entities as gaps.
- **Fix.** Make `_entity_canonical_match` DOI-canonical-tolerant: normalize both sides to a bare DOI (strip `https://doi.org/`, lowercase) and match on DOI when the URL is empty — the same DOI-derivation the M3 render already does for [4]/[6]/[7]. Fallback: credit coverage when a VERIFIED claim's cited `evidence_id` is a SUPPORTS member of the entity's own basket (the ledger already has this linkage). This keeps the strict entity binding but stops a DOI-only source from silently failing the exact-URL compare. Coverage credit is additive (§ coverage_binder discipline) — it only lifts a false gap, never relaxes a gate.

## D6 — contradiction-count says "1" vs actual 3; cross-artifact weight incoherence (T1 labels on 0.08/0.38; disclosed 0.06 vs credibility-file 0.30)
- **Root cause (two sub-defects).**
  (a) Count "1": the "Contradiction disclosures" section enumerates only the single `not_comparable` bucket; the two `possible_metric_mismatch` flags are rendered in Limitations. No place prints `manifest.contradictions_found = 3`. It is a section-scoped render count, not the manifest total.
  (b) Weight incoherence: the run degraded to `rules_floor_degraded` (`credibility_llm_tiering.py:77`), so the tier LABEL came from the deterministic venue rules-floor (`_classify_source_tier_rules`, giving the 1986 paper T1/0.95 by venue) while the per-basket `credibility_weight` (0.08) came from a DIFFERENT down-weighting/composite path. Two weight systems, no single source of truth → T1 label sitting on a 0.08 weight, disclosed 0.06 vs credibility-file 0.30.
- **Fix.** (a) Print the manifest total: the Contradiction-disclosures header states `contradictions_found=N` then buckets by type, so the dedicated disclosure section and Limitations cannot disagree. (b) Reconcile the two weight fields at projection: `provenance_generator._basket_for_biblio` should carry ONE `credibility_weight` that IS the tier→weight mapping used everywhere, and the disclosure render must read that single field (never a second retrieval_weight composite). When tiering degraded to rules-floor, disclose `tiering_mode: rules_floor_degraded` next to every weight so the reader knows the label is venue-rule not GLM.

---

# PART B — the 5 systemic beat-both blockers (blocker | data-flow root cause | architectural fix)

## Blocker 1 — coverage COLLAPSED: 88 corpus → 12 cited. WHERE the funnel drops sources
- **Data-flow root cause.** Selection is NOT the funnel: `selected_to_generator_initial = 84` of 88 (only 4 lost pre-generator). The collapse is a THREE-stage compose/verify funnel, and the weighted-enrichment surfacing is provably uncapped (`weighted_enrichment.py:295,469,573` — "FULL list, no cap/top-N/floor DROP"), so it is not an enrichment cap.
  1. **Retrieval wall** (`retrieval_wall_hit=true`): 13 fetched sources were never tier-classified → they never become baskets → they cannot be cited. Corpus effectively ~75, not 88.
  2. **Compose is single-source per-basket slot-fill, not breadth fan-out.** `verified_compose._compose_section_per_basket` (`verified_compose.py:955`) emits ONE verbatim/short-member sentence per basket per section-contract slot. The body is "concatenations of disjoint verbatim sentence lifts" (audit §170) — it grounds a small number of section slots, each in one basket, not all 84 sources.
  3. **strict_verify + D8 drop the abstractive breadth.** `drop_reason_counts`: `no_provenance_token=34` is the killer — 34 composed sentences carried NO `[#ev]` token and were dropped. Those 34 were breadth the abstractive writer produced without binding a span. Net: the surviving span-verified sentences cite 12 distinct sources.
- **Architectural fix (surgical re-wire, frozen engine untouched).** (i) Raise/parallelize the retrieval wall so the 13 unclassified get tiered (see Blocker 5). (ii) Route the FULL ordered SUPPORTS surfacing from `weighted_enrichment.select_unbound_supports_by_weight` (`:565`) into a numbered "Evidence base" section so every source with a surviving SUPPORTS span gets a `[N]`, not only the section-contract slots — the surfacing is already uncapped; the render just isn't numbering it. (iii) Fix the `no_provenance_token=34` leak at its source: the abstractive writer must only emit sentences through the per-basket verified contract (`_per_basket_verified_clause`, `verified_compose.py:665`) which attaches the token — an un-provenanced abstractive sentence should be repaired (bind the nearest SUPPORTS span) before strict_verify, not silently dropped, so its source still counts as breadth.

## Blocker 2 — ZERO multi-source corroboration formed (the blocked-ref killer)
- **Data-flow root cause.** `PG_CONSOLIDATION_NLI` is default-OFF (`consolidation_nli.py:92`). `finding_dedup` only calls `_apply_consolidation_nli` when the flag is ON (`finding_dedup.py:1053-1054`); with it off, the ONLY clustering is the literal `_finding_key` floor — exact match on extracted subject/predicate/value/unit. Two journals that PARAPHRASE the same claim, or carry no extractable numeric finding, get DISTINCT keys and NEVER corroborate. `corroboration_count` = independent registrable-domains under one literal key (`finding_dedup.py:5`); the run's distribution was `{1: 56, 0: 2, 2: 1}` — exactly one ≥2-origin cluster, and that lone pair (doi.org + predatory journalijar.com) is uncited. `content_dedup_consolidate` (W9, default-ON) only catches near-identical BODY syndication (MinHash ≥0.85, `content_dedup_consolidate.py:59`) — the same report at two URLs — which is orthogonal to same-claim-different-journal corroboration. So every cited finding is single-origin.
- **Architectural fix.** Turn `PG_CONSOLIDATION_NLI=1`. This is precisely the §-1.3 CONSOLIDATE engine: bidirectional NLI (`nli-deberta-v3-base`) unions literal clusters whose representatives entail each other in BOTH directions (`consolidation_nli.py:294,381`), raising corroboration_count and distinct member-hosts. It is merge-only, order-independent, and provably cannot false-corroborate an antonym pair (polarity safety, `:23,246`). It already has the W04 wall (`:67`) and OOM→CPU degrade (`:224`) so the trickle-storm that hurt the GLM judge cannot hang it. This directly manufactures the multi-source baskets DRB-II's blocked-ref tasks reward and DeepTRACE's thoroughness metric scores.

## Blocker 3 — M6 analytical yield ≈ 0
- **Data-flow root cause.** Two coupled causes. (a) `PG_CROSS_SOURCE_SYNTHESIS` default-OFF (`verified_compose.py:167-168`) → `compose_cross_source_analytical_units` is never invoked. (b) Even ON, M6 pairs baskets only when they share an EXACT normalized `subject|predicate` anchor (`cross_source_synthesis.py:73-82,258-259`) AND have distinct claim clusters AND an engine LICENSES a relation (`license_relation`, `:149-171`). The licensing sources are contradiction edges (all 3 were extraction garbage) and the `agree_map`/`equiv_clusters` — which are PRODUCED BY the consolidation engine that was OFF (Blocker 2). With no agreement map and singleton baskets carrying no shared anchor, `by_anchor` groups are all size-1 → zero eligible pairs → zero analytical units. M6 is architecturally downstream of consolidation.
- **Architectural fix.** Enable BOTH flags together (`PG_CONSOLIDATION_NLI=1` first — it feeds M6's `agree_map`/`equiv_clusters`), then `PG_CROSS_SOURCE_SYNTHESIS=1`. Thread the consolidation output into `_compose_section_per_basket(edges=…, equiv_clusters=…, agree_map=…)` (`verified_compose.py:962-963,1071`). M6 then emits `[verified clause A][licensed connective][verified clause B]` sentences carrying TWO distinct `[#ev]` tokens, gated by the FROZEN strict_verify on both atoms (`cross_source_synthesis.py:22-26`) — the faithfulness-safe way to add the DRB-II analysis-dimension yield (18% weight) that scored near-zero. The fail-loud canary (`:310-318`) already exists to prove it fired.

## Blocker 4 — the D8 GLM judge gives false-negatives (3 grounded top-journal claims marked UNSUPPORTED)
- **Data-flow root cause.** Not a reasoning error — a per-claim fail-closed DEGRADE on transport/enum faults. The signature proves it: `02-001` ("15%") and `02-002` ("46%") were marked UNSUPPORTED while their BYTE-IDENTICAL twins `02-007`/`02-010` at the same span offset were VERIFIED (audit §370). Mechanism in `judge_adapter.py`: (a) the enum is set as the vLLM-only `structured_outputs.choice` key (`:229-231`) which OpenRouter cannot enforce, so a reasoning-xhigh judge emits a punctuated/JSON-wrapped token → `parse_judge_verdict` raises `JudgeEnumError` → the claim degrades to `UNSUPPORTED` (`:311-325`); (b) a 429/blank-200 under per-claim concurrency raises `RoleTransportError` → same degrade to `UNSUPPORTED` (`:284-298`). Both are per-claim, so identical claims split verdicts depending on which one hit a flaky call. This is the "judge provider-count is the render blocker" failure (MEMORY 2026-06-30).
- **Architectural fix.** (i) Judge model with HIGH OpenRouter provider count to kill the 429 (kimi-k2.6 = 21 providers, per the operator-locked swap) so `RoleTransportError` rarely fires. (ii) Enforce the enum on the OpenRouter path via `response_format`/`json_schema` (a constraint OpenRouter DOES honor) instead of the vLLM-only `structured_outputs.choice`, so `JudgeEnumError` cannot fire off-vLLM. (iii) Add a bounded per-claim RETRY before the fail-closed degrade (retry-not-degrade DNA) — a transient blank/429 should re-ask, not convict. (iv) Verdict idempotency: cache by `(normalized_claim, span-identity)` so a byte-twin inherits a clean sibling's verdict rather than independently degrading — this alone removes the 02-001/02-007 split. Direction stays safe (a real UNSUPPORTED still holds); it removes the false-negative noise that suppresses corroboration counts and coverage.

## Blocker 5 — the retrieval-wall + GPU-marginal + GLM-degrade coupling
- **Data-flow root cause.** One resource-contention chain on the crammed 2-GPU split. The GPU-OOM forced W6 embedder + W5 reranker + W10 NLI to contend on `cuda:0`; semantic-relevance (W2) fell back to LEXICAL; the retrieval-phase wall hit with 13 sources fetched-but-unclassified; and the GLM credibility mirror, under the same trickle/429/blank-200 storm, degraded EVERY source to `rules_floor_degraded` (`credibility_llm_tiering.py:77`). All three share one cause: heavy models co-resident and one flaky remote LLM socket saturated under un-throttled per-item concurrency. The rules-floor degrade then produced the D6 weight incoherence, and the 13 unclassified sources fed Blocker 1's funnel.
- **Architectural fix (already-proven patterns, just wire them).** (i) Device-split env (2-card placement) so W5/W6/W10 do not co-reside on `cuda:0` (the `PG_CONSOLIDATION_NLI_DEVICE` seam at `consolidation_nli.py:73` is the template; W5 reranker chunking `PG_CONTENT_RELEVANCE_SCORE_CHUNK=2` is the proven OOM cure). (ii) Raise the retrieval-phase wall and run tiering bounded-parallel with a batch wall (`PG_TIER_LLM_BATCH_WALL_SECONDS`, `credibility_llm_tiering.py:293`) so the 13 get classified instead of dropped. (iii) Same high-provider judge/mirror model + bounded retry as Blocker 4 stops the GLM `rules_floor_degraded` cascade at the source. (iv) When tiering DOES degrade, surface `tiering_mode` on every weight (the field exists at `:75-77`) so the run "completes-not-claims" honestly. None of this touches the frozen faithfulness engine — it is throughput/placement/throttle wiring.

---

## One-line synthesis
The faithfulness engine is doing its job (0 fabrication). The beat-both failure is that the WEIGHT-and-CONSOLIDATE half of the architecture shipped behind default-off flags (`PG_CONSOLIDATION_NLI`, `PG_CROSS_SOURCE_SYNTHESIS`, `PG_DOCUMENT_TYPE_WEIGHT`) and an unenforceable off-vLLM judge enum, so the run silently ran as FILTER-and-DROP: singleton baskets, no corroboration, no analysis, off-genre headlines, and a judge that convicts grounded claims on transport noise. The fix is to turn the existing winners on in the right order (consolidation → cross-source synthesis; doc-type weighting; high-provider enum-enforced judge with retry) and split the GPU/throttle so the tiering and retrieval walls stop degrading — all surgical re-wiring, the frozen engine untouched.

Relevant files: `C:/POLARIS/src/polaris_graph/synthesis/consolidation_nli.py`, `synthesis/finding_dedup.py`, `synthesis/content_dedup_consolidate.py`, `generator/verified_compose.py`, `generator/cross_source_synthesis.py`, `generator/weighted_enrichment.py`, `generator/provenance_generator.py`, `roles/judge_adapter.py`, `roles/native_gate_b_inputs.py`, `roles/coverage_binder.py`, `generator/required_entity_ledger.py`, `retrieval/credibility_llm_tiering.py`, `retrieval/document_type_classifier.py`, `nodes/journal_only_filter.py`.