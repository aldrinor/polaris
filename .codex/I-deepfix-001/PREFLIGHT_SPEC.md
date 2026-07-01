# I-deepfix-001 — BEAT-BOTH PREFLIGHT SPEC (forensic, fail-loud, per-element)

**Purpose.** Before the paid A100 acceptance run, verify — element by element — that every fix is not merely committed but **behaviorally FIRES in a real rendered output**, and that every winner module is wired end-to-end. **If any check below fails, the paid run is ABORTED.** Operator standard (2026-07-01): "test against every tiny little element, to make sure our next generation has the highest possibility to fix all 6 residual issues and beat every single scoreboard — SOTA."

**Binding principles.**
- **Behavioral, not config.** A green flag / passing unit test / Codex APPROVE is necessary but NOT sufficient. Each element has an OUTPUT-side assertion (grep the rendered `report.md` / `manifest.json` / `verification_details.json` / canary telemetry). "In the slate ≠ fired in the output" (feedback_verify_feature_fired_in_output_not_config).
- **Fail-loud.** Every check is an assertion that HARD-FAILS the preflight (exit non-zero) on violation. No silent skip, no soft warn. A skipped check is logged as a FAIL.
- **Frozen engine untouched.** strict_verify / provenance_generator / nli_verifier / role_pipeline / judge_adapter / judge_contract / span_grounding / four_role / mirror_adapter / sentinel_adapter / credibility_pass — none edited. Preflight asserts `git diff --name-only <base>` over these is empty.
- **§-1.3.** No cap / floor / thinner / hard-filter was added to force a breadth number. Every change is a WEIGHT / CONSOLIDATION / SURFACING / DISCLOSURE / degrade-fix.
- **VM only.** Every heavy step (small-scale render, preflight render, the run) executes on the VM (2-card A100/RTX), never local (feedback_preflight_and_all_heavy_runs_on_vm_not_local).

---

## PHASE 0 — Static / config preconditions (offline, fast; abort the whole preflight if any fail)

| # | Element | Assertion | How |
|---|---|---|---|
| 0.1 | Frozen engine untouched | `git diff --name-only <base>` over the 11 engine files is EMPTY | git |
| 0.2 | Model lock — generator | generator resolves to GLM-5.2 (deepseek/glm family) | resolve config vs `polaris_runtime_lock.yaml` |
| 0.3 | Model lock — D8 terminal judge | judge resolves to `moonshotai/kimi-k2.6` (distinct family, 21 providers) — NOT GLM, NOT gemma | `openrouter_role_transport` default + `assert_four_role_families_distinct()` |
| 0.4 | Two-family safeguard | `assert_four_role_families_distinct()` PASSES: {generator:z-ai, mirror:z-ai, sentinel:minimax, judge:moonshotai}; `PG_PERMIT_GENERATOR_EVALUATOR_SAME_FAMILY=1` governs ONLY the disclosed all-GLM side surface (setting 0 would abort at `check_family_segregation`) | family guard |
| 0.5 | Token budgets MAX | `max_tokens` per model = the model's real OpenRouter cap (read the API, don't guess); reasoning effort = max (high/xhigh). No starved budget. | token-resolver + `GET /models` |
| 0.6 | GPU device split | `PG_EMBED_DEVICE=cuda:0`, `PG_RERANKER_DEVICE=cuda:1`, `PG_NLI_DEVICE=cuda:1`, `PG_CONSOLIDATION_NLI_DEVICE=cuda:1`, `PG_CONTENT_RELEVANCE_SCORE_CHUNK=2` set; co-residence preflight emits no OOM-risk warning for the real VRAM | `gpu_device_split.detect_coresidence_warnings` |
| 0.7 | Winner slate ON (paid path) | `apply_winner_slate_on_paid_path()` forces PG_CONSOLIDATION_NLI, PG_CONSOLIDATION_NLI_PROSE, PG_CROSS_SOURCE_SYNTHESIS, PG_BREADTH_ENRICHMENT_ENABLED = "1"; op-readiness preflight RED-blocks a slate-OFF paid launch | run_gate_b + operational_readiness_preflight |
| 0.8 | Residual-fix kill-switches ON | PG_FIGURE_CONSISTENCY_ANNOTATE, PG_CORROBORATION_COUNT_AUTHORITATIVE, PG_ENTITY_COVERAGE_CITATION_CREDIT, PG_BREADTH_EVIDENCE_BASE_SECTION, PG_NO_TOKEN_SENTENCE_REPAIR, PG_TIER_LLM_PARALLEL, PG_PROSE_CHROME_NORMALIZE (WS-7), PG_DOCUMENT_TYPE_WEIGHT (WS-8, journal-class) all = ON | env dump |
| 0.9 | Offline unit + replay suite GREEN | all `tests/polaris_graph/test_wave_b_*` (59) + WS-7 + WS-8 tests + `test_deepfix_wave_a_gate_fixes` (36) pass | pytest |

---

## PHASE 1 — Winner modules FIRE in a real render (behavioral; the small-scale VM render)

Run a SMALL-SCALE fresh render on the VM (single realistic clinical query, real fetch, real GPU, real kimi judge, full slate ON). Assert on its `report.md` + `manifest.json` + telemetry:

| # | Winner | FIRING assertion (fail-loud) | Source |
|---|---|---|---|
| 1.1 | WS-2 consolidation (W10 NLI) | `consolidation.collapsed > 0` — at least one multi-source basket actually merged (not 0-collapse) | manifest / verification_details |
| 1.2 | WS-2 cross-source synthesis (M6) | `cross_source_analytical_units > 0` when ≥2 same-anchor baskets exist; the M6 firing canary (`assert_cross_source_synthesis_fired`) does NOT set overall_rc=1 | run_gate_b canary (captured stdout) |
| 1.3 | WS-2 + WS-3 breadth | rendered `## Evidence base` section present with N numbered `[k]` source entries, N well above the drb_72 "12 of 88"; breadth canary passes; `no_provenance_token` repaired count > 0 OR 0 (never a silent drop of a supported sentence) | report.md + weighted_enrichment breadth canary |
| 1.4 | WS-3 Evidence base VERIFIED (the P1 fix) | the Evidence base SectionResult carries NON-empty `kept_sentences_pre_resolve`, ALL `is_verified`; every entry appears in the 4-role D8 claim set (NOT shipped outside strict_verify/D8) | verification_details / four_role_evaluation |
| 1.5 | WS-13 parallel tiering | `retrieval_wall_hit == false` OR any straggler entered the corpus at a rules-floor/degraded tier (present, not dropped); bounded concurrency never exceeded cap | tiering telemetry |
| 1.6 | Semantic relevance NOT degraded | content-relevance ran on GPU (not lexical fallback); no OOM in the run log | run log + relevance telemetry |

---

## PHASE 2 — The 6 residual defects are GONE in the real render (behavioral; the single hard gate)

| # | Residual | GONE assertion (fail-loud) | Fix / source |
|---|---|---|---|
| 2.1 | **D1** — Eloundou "46%" caveat stripped in Conclusion | every re-lifted numeric sentence in Abstract/Conclusion that shares a span-identity+figure with a flagged claim carries its `[confidence: …]` marker; the governing conditional antecedent travels with the number | WS-5 (report_redactor span-identity re-key + overstatement_guard) |
| 2.2 | **D2** — "1 verified source" where `verified_support_origin_count=0` | printed corroboration count = `min(recompute, verified_support_origin_count)`; a 0-authoritative-count basket reads "0 verified independent source(s)" + routes to GROUNDED-BUT-WEAK; sources stay in the numbered Bibliography | WS-6 (corroboration block authoritative field) |
| 2.3 | **D3** — in-prose chrome leaks | ZERO in-prose chrome in `report.md`: no leading bare section-header word, no in-text `(1, 2)` ref markers that are not `[N]`/`[#ev]`, no boundary-truncated `(YYYY)` subject; the chrome canary scores PROSE units (not bullets-only) and passes; byte-identical repeated sentences deduped | WS-7 (prose-chrome normalizer + canary prose denominator) — **NEEDS the fresh render; banked replay is blind** |
| 2.4 | **D4** — off-topic / non-journal headline | no 1986 pre-AI / wrong-genre source headlines an AI-labor finding; M2 genre re-rank + publication-year recency leg FIRED (`document_type_preference: journal_article` active for the journal class); a demoted non-journal stays in the basket at low weight (NOT dropped — §-1.3) | WS-8 (journal-scope double-gate ON) — **NEEDS the fresh render; retrieval-time weighting** |
| 2.5 | **D5** — coverage 0.571 miscredit | a DOI-only VERIFIED entity is credited covered; `coverage_fraction` reflects real verified coverage (no verified entity listed as a gap); a NON-verified claim never credits coverage; D8 release gate no longer held solely by a false 0.571 | WS-4 (DOI-tolerant entity match + basket-member credit) |
| 2.6 | **D6** — contradiction count "1" vs 3 | the disclosure's disclosed + withheld total EQUALS `manifest.contradictions_found`; the all-withheld case still discloses the total | WS-9a (contradiction-count coherence) — DONE + gated |

---

## PHASE 3 — Wiring chain unbroken (§-1.4; each hop fires in the render)

retrieval(embedder=Qwen3-Embedding-8B, real ID loaded — no silent MiniLM) → selection(relevance≠baseline) → baskets(tier classifier = weighting) → STORM outline routing → compose(verified, verbatim fallback fires on a failing sentence) → abstract/conclusion-last → strict_verify → render. Assert: the loaded embedder ID == the locked ID (Gate-B fail-closed); sections == the STORM outline; multi-source baskets exist; a verbatim fallback appears where a sentence failed; weak candidates are labeled never-as-support.

---

## PHASE 4 — Run-level acceptance gates (the beat-both bar)

| # | Gate | Threshold | Source |
|---|---|---|---|
| 4.1 | Faithfulness — fabrication | 0 fabricated claims (§-1.1 line-by-line, claim-vs-cited-span) | §-1.1 audit of report.md |
| 4.2 | Faithfulness — DeepTRACE proxy | unsupported ≤ 5%, citation-accuracy ≥ 90% (estimated via our re-impl scorer, judge substitution disclosed) | WS-14 scorer |
| 4.3 | Coverage — DRB-II | ≥ 66 (target; contention band ~62-64 without TTD-DR) via `run_evaluation.py` (Gemini judge) | WS-14 scorer |
| 4.4 | Corroboration | most claims carry ≥2 independent verified origins (multi-citation baskets) | corroboration block |
| 4.5 | Breadth | cited-source count well above 12; the majority of the corpus that carries a surviving SUPPORTS span is cited | report.md bibliography |
| 4.6 | No abort | manifest.status == success (not abort_* / error_*); D8 `release_allowed == true` (or a HONEST disclosed-gap, never a false success) | manifest |

---

## PHASE 5 — Preflight mechanics (how it runs, fail-loud)

1. **Stage A (offline, local-safe):** Phase 0 static checks + Phase 0.9 pytest. Fast. Abort on any fail.
2. **Stage B (VM small-scale render):** a single-query fresh render on the VM with the FULL production config (slate ON, kimi judge, device split). Then Phases 1-3 assertions grep its artifacts. This is the ONLY way to validate D3/D4 (banked replay is structurally blind). Abort on any fail.
3. **Stage C (§-1.1 audit of the small render):** line-by-line claim-vs-span audit of the small render's report.md (Phase 4.1). Abort on any fabrication.
4. **GO/NO-GO:** the preflight emits a single machine-readable verdict `{go: bool, failed_checks: [...]}`. **GO only if EVERY check passed.** NO-GO lists every failed element. The paid A100 acceptance run launches ONLY on GO.
5. **Forensic monitoring:** during the small render + the paid run, read every log/reasoning/source/output line every ~5 min (never offload to a background watcher); report the cited-source breadth estimate each tick.

## Open build dependencies before the preflight can run
- **WS-7 (D3) + WS-8 (D4)** must be built + Codex-gated (checks 2.3, 2.4 depend on them).
- **WS-14 scorers** (DeepTRACE re-impl + DRB-II `run_evaluation.py`) for checks 4.2/4.3 — or these run post-render as the scoring step.
- **Live A100 box** on the operator's vast.ai account for Stage B/C + the run.
