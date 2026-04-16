# Wave 3 — Implementation summary (2026-04-14 → 2026-04-15)

## Context
Wave 3 closes the remaining 16 tasks from `docs/deployment_plan_all_45.md` after Wave 1 shipped (S1/S3/S7 plumbing + env fixes) and Wave 2 produced baseline PG_TEST_091 (B− grade per advisor-corrected forensic audit).

## Task outcomes

| ID | Defect | Fix | Files touched |
|----|--------|-----|---------------|
| W3.1 | S2#10 rubber-stamp verifier (G-Eval 4/10 vs pipeline 10/10) | `PG_REQUIRE_NLI_FOR_FAITHFUL` env (default tied to `PG_NLI_ENABLED`) — claim cannot be faithful without NLI cross-check when NLI is globally on | `agents/verifier.py` |
| W3.2 | S2#11 barely-passing 0.7308 declared synthesize | New `CONVERGENCE_MIN_FAITHFULNESS=0.80` — stricter than final-gate 0.70; iterate decision uses the new threshold | `state.py`, `agents/synthesizer.py` |
| W3.3 | S2#12 trace file append-across-sessions (9 starts / 2 ends) | Each `PipelineTracer` instance generates a UUID `session_id`, tags every event with `sid`, emits `session_start` marker | `tracing.py` |
| W3.4 | S5#23 only 4/8 STORM perspectives cited | Convergence requires `perspective_coverage >= PG_MIN_PERSPECTIVE_COVERAGE` (default 6/9) in addition to faithfulness | `agents/synthesizer.py` |
| W3.5 | S5#26 query-as-header with 0 words distorts D4 balance | `_score_d4_structure` drops zero-word entries before entropy calc | `audit/automated_deep_audit.py` |
| W3.6 | S8#34-35 SourceAnalysis quality/relevance null → flat 0.1 | Type-informed defaults: journal_article→0.75, government_report→0.65, …, web→0.30; relevance scales with atomic_facts count | `schemas.py` |
| W3.7 | S8#36 bronze=0 in PG_TEST_090 | Investigation only — no BRONZE filter exists; PG_TEST_091 shows 56 BRONZE; the 090 data pattern was composite-score dependent, not a bug |
| W3.8 | S8#38 NLI pair cap drops ~70% | `PG_MAX_CROSS_SOURCE_PAIRS` default 50→200 with top-N-by-relevance selection | `agents/nli_verifier.py` |
| W3.9 | S8#39 bibliography sim=1.0 duplicates | `_canonicalize_url` normalizes scheme/host/www/trailing-slash; strips only known tracking params (utm_*, fbclid, gclid, ref, …) while preserving identifier params (`abstract_id`, `term`, `doi`) so SSRN/PubMed/DOI papers stay distinct | `synthesis/citation_mapper.py` |
| W3.10 | S8#40 AgenticRoundAnalysis 3 validation errors × 6 | Coerce list fields from string/dict, `should_continue` from string/int, map `convergence_assessment` synonyms to canonical vocabulary | `schemas.py` |
| W3.11 | S9#42 dual source of truth (-1.0 vs 1.0) | `compute_faithfulness(claims)` canonical helper; `synthesize_report` recomputes when state holds sentinel; `analyze_gaps` uses the same helper | `agents/synthesizer.py` |
| W3.12 | S10#44 `PG_BUDGET_GUARD_USD=10` ignored; 481min > 240min | `budget_usd=budget_limit` now passed to `OpenRouterClient`; `PG_HARD_STOP_MULTIPLIER` env (default 2.0) controls the 1×/Nx timeout ratio | `graph.py` |
| W3.13 | S8#37 FIX-PRE-V 23% rejection at 0.35 | Review only — working as designed; `PG_VERIFY_RELEVANCE_GATE=0.35` saves verify cost on off-topic results |
| W3.14 | S4 section truncation + budget rebalance | Review only — W1.3 (reasoning_exclude on section_writer) + W3.16 (same on wiki_composer) cover both code paths |
| W3.15 | Final all-45 verification | PENDING — requires live PG_TEST_092 launch |
| W3.16 | Wiki path truncations (s02/s06/s08 in PG_TEST_091) | `wiki_composer._compose_one_section` and `_generate_abstract` now use `reasoning_exclude=True` + `PG_WIKI_COMPOSE_MAX_TOKENS=8192` + `PG_WIKI_ABSTRACT_MAX_TOKENS=1536` | `wiki/wiki_composer.py` |

## Validation
- All 10 modified files parse (`ast.parse` OK).
- All module imports resolve.
- `pg_smoke_test` 16/16 PASS (55-110s).
- Targeted smoke assertions for `compute_faithfulness`, `_canonicalize_url`, `SourceAnalysis` type-informed defaults, `AgenticRoundAnalysis` coercion all green.
- **pytest polaris_graph-focused suite: 488 passed** across forensic audit, perspective tracking, factscore, mesh (claim_extract / ingest / store / snowball / qa / lethal_retrieve / compose / snapshot / edge_discovery / entity), memory (cross_vector / evidence_hierarchy / session_feedback), domain_diversity, content_deduplicator, exception_handling, fix_048.
- Pre-existing failures in legacy modules (`src.functions`, `src.agents.verifier_agent`, `src.agents.analyst_agent`) confirmed present before W3 (`git stash` reproduces the same `ModuleNotFoundError`).
- Advisor follow-up items actioned: log strings in `graph.py:1665` and `graph.py:1700` no longer hardcode `* 2`; now format `_hard_stop_mult` and the computed minute count.

## New env vars introduced in Wave 3
- `PG_CONVERGENCE_MIN_FAITHFULNESS` (default 0.80)
- `PG_MIN_PERSPECTIVE_COVERAGE` (default 6)
- `PG_REQUIRE_NLI_FOR_FAITHFUL` (default = PG_NLI_ENABLED value)
- `PG_HARD_STOP_MULTIPLIER` (default 2.0)
- `PG_WIKI_COMPOSE_MAX_TOKENS` (default 8192)
- `PG_WIKI_ABSTRACT_MAX_TOKENS` (default 1536)

## Unchanged (intentionally)
- `PG_MIN_FAITHFULNESS=0.70` (final quality gate)
- `PG_FAITHFULNESS_NLI_THRESHOLD=0.75`
- `PG_VERIFY_RELEVANCE_GATE=0.35`
- `PG_NLI_FAITHFULNESS_FLOOR=0.40`

## Next
Launch PG_TEST_092 to validate all 45 fixes together under production load. Expected improvements over PG_TEST_091:
- No wiki-path section truncations (W3.16)
- Single-source faithfulness_score (W3.11)
- Perspective coverage ≥ 6/9 before convergence (W3.4)
- No sim=1.0 bibliography duplicates (W3.9)
- Hard-stop respects configured budget (W3.12)
- Tight budget via `PG_BUDGET_GUARD_USD=10` actually enforced (W3.12)
- D4 balance no longer dragged down by 0-word query-as-heading (W3.5)

## PG_TEST_092 first-attempt result (2026-04-14 19:11–21:27, 136min)

**Status: `partial_failure` — NOT a Wave 3 regression. External OpenRouter account billing hit 402 during analyzer (20:50:33).**

Confirmed fix validations before 402:
- W3.16 — `CoT markers: NONE`, `Wiki truncation markers: NONE`
- W3.5 — `Zero-word sections: 0`
- W3.12 — stayed under $10 pipeline cap ($3.64 spent); OpenRouter account-level 402 is separate
- W3.10 — 7 AgenticRoundAnalysis calls parsed (with retries, all succeeded)

Two Wave 3 gaps surfaced by the aborted run — now fixed:
1. **W3.11 gap in wiki path**: `wiki_composer.compose_from_wiki` hardcoded `faithfulness_score=-1.0` sentinel. Fixed to call `compute_faithfulness(section_claims)`.
2. **W3.9 gap in wiki path**: `wiki_builder._build_bibliography` used raw `url` as dedup key (missed http/https and www variants of same paper). Fixed to use `_canonicalize_url` with one canonical→display mapping.

Both files now import the canonical helpers from `synthesizer` / `citation_mapper`.

## Re-run checklist
- [ ] Top up OpenRouter credits (account-level billing, `openrouter.ai/settings/credits`)
- [ ] Smoke test 16/16 once LLM calls succeed
- [ ] Relaunch `python scripts/pg_test_092.py`

## PG_TEST_092 line-by-line audit — complete findings (2026-04-14, advisor-corrected)

Forced by advisor to stop pattern-matching. 8 phases run, then 5 deep-dive checks
when pattern-matching missed real defects. Final defect inventory D1-D10:

### Already patched (done)
- **D9** — wiki bibliography http/https dup → `wiki_builder._build_bibliography` now uses `_canonicalize_url`.
- **D10** — wiki `faithfulness_score=-1.0` stub → `wiki_composer.compose_from_wiki` now calls `compute_faithfulness(section_claims)`.

### Fixed before re-run
- **D6** — `PG_CROSS_SOURCE_MIN_NLI=0.5→0.3` in `.env`. **Highest-impact change.** 95% of PG_TEST_092 claims were downgraded by cross-source despite NLI self-check median of 0.962. For topics where multiple papers cite overlapping meta-analyses, 0.5 was too strict.
- **D1** — `_assign_quality_tiers` not re-running after NLI populates `nli_self_check_score`. Added idempotent re-tier call in `graph.py:_verify` node after `_map_nli_scores_to_evidence`. 4/47 GOLD pieces in PG_TEST_092 would demote to SILVER with real NLI-based `sig_grounding`.

### NOT fixed (correct behavior or deferred)
- **D2** — 1:1 claim-to-evidence ratio. Design: wiki path's atomic facts live in `wiki_result.section_claims`, not top-level `claims`. Working as designed.
- **D3** — 12 evidence pieces with zero claims. Pre-V relevance gate + 402-aborted batches. Non-blocking.
- **D4** — max-iter fallback synthesizes at 0.0% faith. **Retracted.** Correct degradation for API outage; `convergence_reason="wiki_synthesis: failed: words=0<2000, citations=0<5"` correctly captures the failure state. Blocking synthesis here would eliminate diagnostic output.
- **D5** — Gap analysis yields 0 gaps when all claims `api_error`. Correct — can't generate gap queries from unverifiable claims.
- **D7** — 34% missing-author bibliography entries. Pre-existing analyzer prompt gap. Doesn't affect quality gates or faithfulness. Deferred to future wave.
- **D8** — 8.3% transient analyzer timeout rate (1.49% final fail). W1.1 already raised timeout 120s→210s. Two fully-failed sources are 22K-30K char payloads; raising further would block the concurrent queue. Leave.

### Complete action list for re-run
| # | Action | Status |
|---|--------|--------|
| 1 | Top up OpenRouter credits | **User action required** |
| 2 | `PG_CROSS_SOURCE_MIN_NLI=0.5→0.3` in `.env` | ✅ Done |
| 3 | Re-tier evidence after NLI (D1 code fix in `graph.py:_verify`) | ✅ Done |
| 4 | Smoke test 16/16 after credits restored | Pending |
| 5 | Relaunch `python scripts/pg_test_092.py` | Pending |

No more code changes. Validation mode — not development mode.
