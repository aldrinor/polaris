# PG_TEST_090 — Problem Inventory

**Subject:** `vector_id=PG_TEST_090`, query "What are the proven health benefits and risks of intermittent fasting based on clinical research and meta-analyses?"
**Run:** 2026-04-13 10:09 → 17:57 UTC+8 (7 h 48 min wall time, $4.73, 272 LLM calls)
**Deliverable:** `outputs/polaris_graph/PG_TEST_090_report.md` (13,246 words)
**Model:** `z-ai/glm-5.1` (except a few `z-ai/glm-5` calls visible in trace)

**Purpose of this file:** reconstruct the defect catalog that was built inline during the prior session and lost to context compaction. Every item here is sourced to a persisted artifact so coverage can be verified independently next session.

**Artifacts cross-referenced:**
- `outputs/polaris_graph/PG_TEST_090_report.md` (final markdown)
- `outputs/polaris_graph/PG_TEST_090.json` (pipeline state)
- `outputs/polaris_graph/PG_TEST_090_audit_v2.json` (10-dim audit, total 88.2/100)
- `outputs/polaris_graph/PG_TEST_090_geval.json` (G-Eval, 59.5/100)
- `logs/pg_test_061_run4.log` (2.5 MB run log)
- `logs/pg_trace_PG_TEST_090.jsonl` (31 MB structured trace)
- `logs/bug_log.md` §§ BUG-240CAP, BUG-FAITHLOG, BUG-BATCHTIMEOUT, BUG-BASH-BACKGROUND
- `logs/session_log.md` Session 58 entry (line 3144)

**Severity legend:** P0 blocks acceptance; P1 material quality loss; P2 noticeable but acceptable; P3 cosmetic; P4 noise.
**Status legend:**
- UNRESOLVED — no code/env change shipped
- DIAGNOSED — root cause identified with evidence (`docs/s3_root_cause_diagnosis.md`)
- VALIDATED — empirically proven mechanism (E4-LONG etc.)
- FIXED — shipped to code/env this session (commits referenced)

---

## Solution area S1 — Prose scaffolding / CoT leakage in report body
**Mechanism:** GLM-5.1 emits planning markers, self-talk, scratch pads, and mid-draft revisions into `content` even with regex scrubbers (FIX-GLM5-COT, FIX-071B).

| # | Defect | Severity | Evidence | Status |
|---|---|---|---|---|
| 1 | `Let me` / `Let me restructure` / `Let me make it good` — 3 occurrences in body | P1 | `report.md` lines 89, 99, 108, 118; `audit_v2 D1.details.examples[1-3]` | VALIDATED (S1 E4-LONG confirms `reasoning.exclude=true` gives 0 markers) |
| 2 | `wait,` (× 2) — self-correction in body | P1 | `report.md` line 99 "wait, let me restructure"; audit D1 examples | VALIDATED same |
| 3 | `Actually let me re-read: ...` — model talking to itself | P1 | `report.md` line 100; audit D1 example[2] | VALIDATED same |
| 4 | `I need to` (× 3) — analytic planning in prose | P1 | `report.md` grep-confirmed; audit D1 examples | VALIDATED same |
| 5 | `[N] - used` scratch-pad (× 24) — reference-tracking metacommentary | P1 | `report.md` grep: 24 occurrences | VALIDATED same |
| 6 | `One thing to fix: the bridging sentence.` — draft planning leaked | P1 | `report.md` line 118 | VALIDATED same |
| 7 | `First, while …` as paragraph opener (multiple sections) — regex list-style scaffolding | P1 | `audit_v2 D1.details.examples[0]` (line 34) | VALIDATED same |
| 8 | 13 CoT-leaked lines out of 539 (2.4 % rate) — D1 score 9.2/10 | P1 | `audit_v2 D1.details.leakage_rate=0.0241` | VALIDATED same |

**Blocker for shipping S1:** `openrouter_client.py:800-803` hard-replaces caller's `reasoning` dict; empirical test (E4-LONG) bypassed this by hitting OpenRouter directly. Must change override to merge before the fix lands in production.

---

## Solution area S2 — Post-synthesis quality gate failed; expansion loop broken
**Mechanism:** synthesizer emitted text below minimum quality thresholds but the expansion pass that should have retried/extended never ran.

| # | Defect | Severity | Evidence | Status |
|---|---|---|---|---|
| 9 | `quality_gate: below_minimum, expansion_passes=0` — gate failed, no retry | P0 | `trace.quality_gate` event | UNRESOLVED |
| 10 | G-Eval faithfulness 4/10 (vs pipeline 10/10) — 60 pp rubber-stamp gap | P1 | `_geval.json` faithfulness.score=4, per-section [6,5,4,4,4,3,2,1,2,4] | UNRESOLVED |
| 11 | Iteration #1 faithfulness 0.6774 → iterated → 0.7308 (second pipeline), declared "synthesize" anyway | P1 | `trace.iteration_decision` (× 2 runs) | UNRESOLVED |
| 12 | Trace file is append-across-sessions: 9 `pipeline_start` events but only 2 `pipeline_end` — 7 runs crashed/aborted without completion markers. Current `report.md` (mtime 2026-04-13 17:57) corresponds to the 2nd completion (7 h 48 min, 12,052 words logged, faith=0 logged), not the cleaner Apr-6 completion (14,223 words, faith=1.0). Trace aliasing makes trace-based audits ambiguous unless filtered by pipeline session. | P0 | `trace.pipeline_start` × 9, `pipeline_end` × 2 at `2026-04-06T04:03` and `2026-04-14T00:57` | UNRESOLVED |

---

## Solution area S3 — Analyzer batch failure at 73 %
**Mechanism:** 30 concurrent requests saturate Chutes fp8 provider; 120 s timeout fires before queued calls dispatch.

| # | Defect | Severity | Evidence | Status |
|---|---|---|---|---|
| 13 | 201 / 275 extraction batches produced no evidence (73 % failure rate) | P0 | `run_log` 74 "extracted … evidence" lines / 275 submitted; matches `BUG-BATCHTIMEOUT` | DIAGNOSED (`docs/s3_root_cause_diagnosis.md`) |
| 14 | Mass-simultaneous timeout at T+120 s (23 batches within 76 ms) — server queue fingerprint | P0 | `run_log` 13:22:39 cluster; advisor-confirmed | DIAGNOSED same |
| 15 | 120 s timeout below p99 (138 s) and max (172 s) of completed batches | P0 | SDK durations p50=29.8 s, p95=90.4 s, p99=138.4 s, max=171.8 s (151 completions) | DIAGNOSED same |
| 16 | `PG_ANALYSIS_CONCURRENCY=30` over-subscribes single-provider (Chutes fp8) | P0 | `.env`; no `OPENROUTER_PROVIDER_ORDER` constraint | DIAGNOSED same |
| 17 | ALWAYS_REASON override ignores caller `reasoning_enabled=False` — extraction reasons needlessly | P1 | `analyzer.py:1953` passes False; trace `llm_detail.reasoning_tokens=806-940` per extraction batch | DIAGNOSED same |
| 18 | Override hard-replaces entire `reasoning` dict → future `max_tokens=2048` or `exclude=true` from callers silently clobbered | P0 | `openrouter_client.py:800-803` | DIAGNOSED (advisor caught), not yet fixed |

---

## Solution area S4 — Section-level truncation
**Mechanism (revised, advisor 2026-04-14):** likely shares S1's root cause. Reasoning tokens and content tokens draw from the shared `max_tokens=16384` budget. With `reasoning.exclude=true` the server still reasons but reasoning_tokens no longer consume the content share — E4-LONG produced 1,292 clean words cleanly. Sections that burn 4,000+ reasoning tokens leave ~12 K for content; a 2,500-word section runs out mid-generation. **S4 very likely resolves when S1 lands** — the earlier "max_tokens clamp" theory was debunked (`PG_GLM5_MIN_MAX_TOKENS=4096` is a floor, not a ceiling). Keep S4 on the list pending re-test after S1 ships.

| # | Defect | Severity | Evidence | Status |
|---|---|---|---|---|
| 19 | Section 9 "Neurological Protection" ends mid-word `…maintain circ` | P0 | `report.md` section 9 tail | UNRESOLVED — replacement root cause not identified |
| 20 | Section 3 "Weight Loss" ends with a scratch-pad sentence `Let me make it good: "With the physiological mechanisms of intermittent fasting` — CoT + truncation compound | P0 | `report.md` line 118 | UNRESOLVED |
| 21 | Section 12 "General Safety" ends mid-sentence `…A critical safety consideration insufficient` | P1 | `report.md` section 12 tail | UNRESOLVED |
| 22 | G-Eval: Section 8 contains literal prompt artifact `"To write this Clinical Outcomes and Applications section properly, I would need…"` | P0 | `_geval.json coherence.reasoning` | UNRESOLVED |

---

## Solution area S5 — Perspective + section imbalance
**Mechanism:** STORM tags 8 perspectives but only a subset get evidence; section-write lengths spread wildly.

| # | Defect | Severity | Evidence | Status |
|---|---|---|---|---|
| 23 | Only 4 of 8 perspectives present in cited evidence (`Scientific 69, Public_Health 5, Methodological 14, Emerging_Trends 1`); `Regulatory, Industry, Economic, Historical, Regional` missing | P1 | `audit_v2 D7.details.perspective_distribution`; D7 score 6.3/10 | UNRESOLVED |
| 24 | Section "Cardiometabolic Benefits and Glycemic Control" = 36 words (stub) | P1 | `audit_v2 D4.details.word_counts` | UNRESOLVED |
| 25 | Section "Neurological Protection" = 2,506 words (bloat); 69× larger than stub above | P1 | same | UNRESOLVED |
| 26 | Header appears as its own "section" with 0 words (query string reproduced as heading) | P2 | `audit_v2 D4.details.word_counts` entry `"What are the proven health benefits…": 0` | UNRESOLVED |
| 27 | Abstract 192 w, Key Findings 248 w, Future Directions 276 w — all below 300 w floor | P2 | same | UNRESOLVED |

---

## Solution area S6 — Audit field alignment (fixed this session)

| # | Defect | Severity | Evidence | Status |
|---|---|---|---|---|
| 28 | `automated_deep_audit.py` read `evidence_chain` but pipeline wrote `evidence`; D7 scored 0.0 → total 81.9 instead of 88.2 | P1 | commit 3b17932 diff; post-fix total 88.2 confirmed | FIXED |
| 29 | D7 `perspective_origins` field vs older `perspective` key — same compat gap | P2 | commit 3b17932 | FIXED |

---

## Solution area S7 — Reasoning parameter plumbing (blocker for S1 / S3)
Already surfaced as #18. Separating here because the fix is structural (method signature + body builder), not env.

| # | Defect | Severity | Evidence | Status |
|---|---|---|---|---|
| 30 | `_ALWAYS_REASON_MODELS` override replaces entire `reasoning` dict — callers cannot pass `max_tokens` or `exclude` | P0 | `openrouter_client.py:800-803` | DIAGNOSED |
| 31 | `generate_structured()` / `generate()` method signatures do not accept `reasoning_max_tokens` or `reasoning_exclude` | P0 | signature inspection; caller must pass via internal `body` dict which is rebuilt | DIAGNOSED |
| 32 | OpenRouter rejects `reasoning.effort` + `reasoning.max_tokens` together (400 error: `Only one of … can be specified`) — any fix must pick one | P1 | E1 empirical test result | VALIDATED |
| 33 | `reasoning.effort=low` ignored by GLM-5.1 — 5,243 chars reasoning + 982 chars content, server reasons regardless | P2 | E2 empirical: reasoning_tokens=1,344, content_tokens=11 (11 tokens ≠ 982 chars, token accounting also broken) | VALIDATED |

---

## Solution area S8 — Evidence pool / scoring
**Mechanism:** 89 evidence pieces in final, but tier distribution is skewed; bronze=0 suggests over-filtering; many quality-signal defaults fire.

| # | Defect | Severity | Evidence | Status |
|---|---|---|---|---|
| 34 | `AREA-9: SourceAnalysis.source_quality is null` × 4 — LLM returned null, defaulted to 0.1 | P2 | `run_log` 14:46:58 (4 occurrences) | UNRESOLVED |
| 35 | `AREA-9: SourceAnalysis.overall_relevance is null` × 4 — same | P2 | same | UNRESOLVED |
| 36 | `quality_metrics.bronze_evidence = 0` while `silver_evidence = 61` — suspicious stratification, may indicate BRONZE filter removed everything | P2 | `PG_TEST_090.json quality_metrics` | UNRESOLVED |
| 37 | `FIX-PRE-V`: removed 19/81 evidence below 0.35 relevance in iteration 2 (23 % rejection) — suggests generation surfaces low-relevance material | P2 | `run_log` 17:23:18 | UNRESOLVED |
| 38 | `BUG-092`: NLI cross-source pairs capped 171→50 and 139→50 (×2) — arbitrary cap drops ~70 % of pairs | P2 | `run_log` 14:43:29, 17:25:15 | UNRESOLVED |
| 39 | Semantic duplication: 6 duplicate pairs including two with similarity=1.0 (bibliography entries duplicated verbatim) | P2 | `audit_v2 D3.details.worst_pairs` | UNRESOLVED |
| 40 | Structured parse failed × 6 — `AgenticRoundAnalysis` with 3 validation errors, retried | P3 | `run_log` 10:33:49 and 5 others | UNRESOLVED |

---

## Solution area S9 — Token / cost / log accounting
| # | Defect | Severity | Evidence | Status |
|---|---|---|---|---|
| 41 | `completion_tokens_details.reasoning_tokens` over-counts: 1,344 reasoning + 11 content sums to 1,355 but content is 982 chars (~245 real tokens) | P2 | E2 raw response; if any budget logic reads this, it's wrong | DIAGNOSED |
| 42 | `quality_metrics.faithfulness_score = -1.0` while state-level `faithfulness_score = 1.0` — dual source-of-truth | P2 | `PG_TEST_090.json` | UNRESOLVED |
| 43 | Pipeline final-line log prints `faithfulness=0.0%, coverage=0.0%` while state holds `1.0` (`BUG-FAITHLOG`) | P3 | `bug_log.md §BUG-FAITHLOG`; fixed partially in `graph.py:1535-1550` this session | PARTIAL FIX (code edited earlier) |

---

## Solution area S10 — Pipeline runtime governance
| # | Defect | Severity | Evidence | Status |
|---|---|---|---|---|
| 44 | `PG_MAX_EXECUTION_MINUTES=240` not enforced — run went 468 min (+95 %) (`BUG-240CAP`) | P2 | `bug_log.md §BUG-240CAP`; final trace elapsed=28,076 s | UNRESOLVED |
| 45 | `&` backgrounding bug — previous run #2 died silently at 00:13 due to shell disown (`BUG-BASH-BACKGROUND`) | P1 operational | `bug_log.md §BUG-BASH-BACKGROUND`; memory note added | MITIGATED (behavioral: use `run_in_background=true`, never `&`) |

---

## Coverage summary

| Area | # of items | Status |
|---|---|---|
| S1 prose CoT | 8 | VALIDATED mechanism, blocked on S7 |
| S2 quality gate | 4 | UNRESOLVED — no plan yet |
| S3 batch failure | 6 | DIAGNOSED — env fix ready, code fix blocked on S7 |
| S4 section truncation | 4 | UNRESOLVED — prior root cause debunked, replacement not found |
| S5 perspective/balance | 5 | UNRESOLVED |
| S6 audit fields | 2 | FIXED |
| S7 reasoning plumbing | 4 | DIAGNOSED (blocker for S1 + S3 code fixes) |
| S8 evidence/scoring | 7 | UNRESOLVED |
| S9 token/log accounting | 3 | DIAGNOSED / PARTIAL |
| S10 runtime governance | 2 | UNRESOLVED + MITIGATED |
| **TOTAL** | **45** | |

**As of 2026-04-14 (arithmetic reconciled per advisor):**
- FIXED: 2 (S6 #28-29)
- PARTIAL FIX: 1 (S9 #43)
- MITIGATED: 1 (S10 #45)
- VALIDATED empirically: 10 (S1 #1-8 all covered by E4-LONG; S7 #32-33)
- DIAGNOSED with evidence: 9 (S3 #13-18; S7 #30-31; S9 #41)
- UNRESOLVED: 22 (S2 × 4, S4 × 4, S5 × 5, S8 × 7, S9 #42, S10 #44)
- Check: 2 + 1 + 1 + 10 + 9 + 22 = 45 ✓

**Next actions (ordered by independence):**
1. Ship env fix `PG_ANALYSIS_CONCURRENCY=30→8`, `PG_ANALYSIS_BATCH_TIMEOUT=120→300` — independent of S7 blocker, highest impact on S3.
2. Fix S7 plumbing (merge-not-replace in `openrouter_client.py:800`, add `reasoning_max_tokens` / `reasoning_exclude` to method signatures) — unblocks S1 and S3 code fixes.
3. Apply S1 `reasoning_exclude=True` to section-write path; retire FIX-GLM5-COT regex. **Likely also resolves S4 truncation** because reasoning_tokens stop consuming the shared `max_tokens` budget (advisor observation). Verify by re-test before closing S4.
4. S2 quality gate review — why did `expansion_passes=0` despite `quality_gate: below_minimum`? Probably an early-exit bug in the expansion loop; independent of S1/S3.
5. S5 perspective imbalance — root cause probably in planner (only produces queries for 4 of 8 perspectives) or in evidence filter (PG_MIN_PERSPECTIVE_EVIDENCE cuts off small perspectives). Needs separate investigation.
6. S8 evidence/scoring items — null defaults (#34-35) suggest extraction prompt doesn't enforce non-null for quality fields; easy prompt change.
7. S10 #44 (`PG_MAX_EXECUTION_MINUTES` not enforced) — grep `graph.py` for the check; likely wired to wrong loop.
8. S9 #42 (dual `faithfulness_score` field) — delete one or alias them.
