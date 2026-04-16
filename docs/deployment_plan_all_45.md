# Deployment Plan — Fix All 45 Problems from PG_TEST_090

**Baseline:** `outputs/polaris_graph/PG_TEST_090_report.md` — 45 defects catalogued in `docs/pg_test_090_problem_inventory.md`.
**Target:** PG_TEST_092 audit v2 ≥ 93/100, G-Eval ≥ 80/100, 0 UNRESOLVED items.
**Strategy:** 3-wave deployment. Each wave lands code+config, runs a validation harness, then launches a production test before the next wave begins.

---

## Wave 1 — Ship diagnosed fixes (S1, S3, S7)

**Goal:** collapse the 18 items already diagnosed/validated. Depends only on local code + env.

### Task W1.1 — Env-only fixes (independent of code)
**File:** `.env`
```diff
- PG_ANALYSIS_CONCURRENCY=30
+ PG_ANALYSIS_CONCURRENCY=8
- PG_ANALYSIS_BATCH_TIMEOUT=120.0
+ PG_ANALYSIS_BATCH_TIMEOUT=900.0
```
**Covers:** S3 #13–16.
**Risk:** Lower concurrency → longer wall clock for extraction (estimated +10–15 min for 275 batches). Acceptable.
**Rollback:** revert `.env` lines.

### Task W1.2 — S7 reasoning-dict plumbing (BLOCKER for W1.3 + W1.4)
**File:** `src/polaris_graph/llm/openrouter_client.py:800-803`
**Current:**
```python
if self.model in _ALWAYS_REASON_MODELS:
    body["reasoning"] = {"effort": reasoning_effort or "high", "exclude": False}
```
**Change to merge-not-replace:**
```python
if self.model in _ALWAYS_REASON_MODELS:
    caller_reasoning = body.get("reasoning") or {}
    merged = {"effort": reasoning_effort or "high", "exclude": False}
    merged.update(caller_reasoning)      # caller wins
    # OpenRouter constraint: can't set both effort and max_tokens
    if "max_tokens" in merged and "effort" in merged:
        merged.pop("effort")
    body["reasoning"] = merged
```
**Method signature additions** on `generate_structured` / `generate` / `reason` / the underlying chat method:
```python
reasoning_max_tokens: int | None = None,
reasoning_exclude: bool | None = None,
```
When either is set, the caller writes `body["reasoning"] = {...}` *before* the ALWAYS_REASON merge block runs.
**Covers:** S7 #30–31.
**Risk:** breaks any caller that relied on the hardcoded defaults. None of the 32 call sites currently pass `reasoning_max_tokens` or `reasoning_exclude` (grep confirmed). Backward compatible.
**Rollback:** revert the method + body-builder changes.
**Test:** new `scripts/pg_smoke_reasoning_merge.py` that hits the client with `reasoning_max_tokens=2048` and `reasoning_exclude=True`, verifies the actual HTTP body contains what the caller asked for.

### Task W1.3 — S1 `reasoning_exclude=True` on section-write
**Files:**
- `src/polaris_graph/agents/synthesizer.py` — every call to `generate_structured` / `reason` that writes section prose: add `reasoning_exclude=True`. 4 call sites per memory note #7.
- Retire `FIX-GLM5-COT` regex scrubber in `openrouter_client.py:1491-1550` — mark removal with a migration comment; delete after PG_TEST_091 validates clean output.
**Covers:** S1 #1–8. Likely also S4 #19–22 (truncation) and S5 #24–25/27 (stub/bloat/short sections) via freed content budget.
**Risk:** if GLM-5.1 misroutes some calls (memory note #9: provider sometimes puts `generate()` output into `reasoning_content`), `exclude=true` could return empty content. Mitigation: keep the `reasoning_content` fallback extraction in `openrouter_client.py`.
**Test:** `scripts/pg_empirical_e4_long.py` (already passes at API level); re-run through production client after W1.2 lands.

### Task W1.4 — S3 `reasoning_max_tokens=2048` on extraction
**File:** `src/polaris_graph/agents/analyzer.py:1947-1954` (extraction `_analyze_batch` call)
```python
parsed = await client.generate_structured(
    prompt=prompt,
    schema=SourceAnalysisBatch,
    system=ANALYSIS_SYSTEM,
    max_tokens=int(os.getenv("PG_EXTRACTION_MAX_TOKENS", "16384")),
    timeout=180,
    reasoning_enabled=False,  # caller intent
    reasoning_max_tokens=2048, # NEW — caps runaway reasoning (seen: 10813 tokens)
)
```
Also apply to `analyzer.py:2113` and storm_interviews extraction calls (`:476, :718, :814`).
**Covers:** S3 #17–18.
**Risk:** if 2048 reasoning tokens is too tight for some extraction tasks, schema validation may fail more often. Monitor `structured parse failed` count; raise to 4096 if it spikes.

### Task W1.5 — Preflight + smoke validation
Run before launching PG_TEST_091:
1. `python -u -m scripts.pg_smoke_test` → 16/16 PASS
2. `python -u scripts/pg_empirical_e4_long.py` through production client → 0 scaffolding, ≥1000 words, ≥5 citations, clean ending
3. `python -u scripts/pg_smoke_reasoning_merge.py` (new, from W1.2) → caller-passed reasoning params appear in HTTP body
4. `pytest tests/unit/test_openrouter_client.py` → all existing tests still pass

---

## Wave 2 — Re-baseline with fresh production run

### Task W2.1 — Launch PG_TEST_091
**Command pattern** (per memory note BUG-BASH-BACKGROUND: never use `&`):
```bash
python -u -m scripts.pg_test_061 2>&1 | tee logs/pg_test_091_run1.log
```
with `run_in_background=true` on the Bash tool itself.
**Same query as PG_TEST_090** (IF clinical research) for apples-to-apples comparison.
**Expected deltas vs PG_TEST_090:**
- Extraction success rate: 27 % → ≥ 70 %
- Wall clock: 7 h 48 min → ≤ 4 h
- CoT markers in body: 13 → 0
- Section truncation: 4 sections → 0 sections
- Cost: $4.73 → likely lower due to capped reasoning tokens

### Task W2.2 — Audit PG_TEST_091 vs PG_TEST_090
```bash
python -u scripts/run_audit.py --result-file outputs/polaris_graph/PG_TEST_091.json
python -u scripts/run_geval.py --result-file outputs/polaris_graph/PG_TEST_091.json
```
Update `docs/pg_test_090_problem_inventory.md` — mark each item RESOLVED / STILL-OPEN. Items expected to resolve automatically:
- S4 #19, #20, #21, #22 (truncation — all 4 likely collapse from S1)
- S5 #24, #25, #27 (section budget rebalancing)
- S2 #9 (if gate was failing on CoT only)

Anything still open goes into Wave 3.

---

## Wave 3 — Parallel independent fixes for remaining UNRESOLVED items

These don't depend on Wave 1/2 and can be worked in parallel. Each is a bounded change.

| Task | File(s) | Change | Item |
|---|---|---|---|
| W3.1 | `.env`, `nli_verifier.py` | Raise `PG_NLI_FAITHFULNESS_FLOOR` from 0.15 → 0.4; require NLI confirm before `is_faithful=True` | S2 #10 |
| W3.2 | `.env` | `PG_CONVERGENCE_FAITHFULNESS=0.85` | S2 #11 |
| W3.3 | `src/polaris_graph/observability/tracer.py` | Add `session_id=uuid4()` on pipeline_start, thread into every event; reader filters by session | S2 #12 |
| W3.4 | `src/polaris_graph/agents/storm_interviews.py`, `searcher.py` | After first-pass, if any STORM perspective has 0 evidence, trigger gap-search with perspective-specific alternate queries | S5 #23 |
| W3.5 | `src/polaris_graph/agents/synthesizer.py` outline step | Filter outline: drop entries where `title == original_query` or target word_count ≤ 0 | S5 #26 |
| W3.6 | `src/polaris_graph/schemas.py`, analyzer prompt | Extraction prompt: "MUST return float 0–1, not null"; `SourceAnalysis` validator: reject null, do not default | S8 #34, 35 |
| W3.7 | tier scoring + pre-verify | Trace BRONZE tier: is it dropped at tier assignment or pre-verify gate? Fix whichever over-filters | S8 #36 |
| W3.8 | `.env`, `nli_verifier.py` | `PG_NLI_MAX_PAIRS=100` (was 50); keep relevance-weighted selection | S8 #38 |
| W3.9 | `src/polaris_graph/agents/citation_mapper.py` or synthesizer finalize | Dedup bibliography by canonical URL before emission | S8 #39 |
| W3.10 | `src/polaris_graph/schemas.py` `AgenticRoundAnalysis` | Mark optional fields `Field(default_factory=list/dict)`; add `@model_validator(mode="before")` for Qwen/GLM field-name normalization | S8 #40 |
| W3.11 | `src/polaris_graph/agents/synthesizer.py` | Delete `quality_metrics.faithfulness_score` OR set it from `state.faithfulness_score`; keep state as canonical | S9 #42 |
| W3.12 | `src/polaris_graph/graph.py` | Add wall-clock check at top of every LangGraph node; abort with CASE_4 when `PG_MAX_EXECUTION_MINUTES` exceeded | S10 #44 |
| W3.13 | review only | Confirm `PG_PRE_VERIFY_RELEVANCE=0.35` is the right threshold. If removed items were genuinely off-topic, mark "working as designed" | S8 #37 |
| W3.14 | verification | Verify S4 / S5-budget items resolved after W2. Any still open becomes a W3 task. | S4 #19–22, S5 #24–25/27, S2 #9 |

### Task W3.15 — Final PG_TEST_092 validation
- Run PG_TEST_092 with all W1 + W3 fixes applied.
- Automated audit v2 ≥ 93/100 (vs 88.2 baseline).
- G-Eval ≥ 80/100 (vs 59.5 baseline).
- Open items in inventory = 0.
- If any item still fails, reopen as separate task with diagnosis.

---

## Decision gates

**Before starting Wave 1:** user approval of this plan.
**Before W1.3/W1.4:** W1.2 smoke test (`pg_smoke_reasoning_merge.py`) must pass — caller's reasoning params must reach the HTTP body unchanged.
**Before W2.1:** all W1 smoke tests pass (W1.5 checklist).
**Before W3.1–W3.14:** PG_TEST_091 completed and audited. Tasks in W3 that cover resolved items auto-close.
**Before declaring done:** W3.15 metrics hit the bar on a run the user accepts.

---

## Rollback strategy

- Each Wave-1 change is a single file edit (env or one function). Revert by reverting the file.
- Wave-3 changes are independent of each other. Revert one without affecting others.
- Git commits should be 1-per-task to make rollback granular.

---

## Open risks

1. **`reasoning.exclude=true` may return empty content on misrouted providers** (memory note #9). Mitigation: `reasoning_content` fallback extraction already exists and stays. Monitor for empty-content rate spike in PG_TEST_091.
2. **W1 env changes extend extraction wall clock.** 275 batches ÷ 8 concurrency = 34 waves × 60 s avg = ~35 min. Within budget given 7 h 48 min → ≤ 4 h target.
3. **Bibliography dedup (W3.9) might remove legitimately distinct sources with identical URLs.** Shouldn't happen (canonical URLs are unique), but validate on PG_TEST_092.
4. **Wave 3 parallelism risk**: if two W3 tasks touch the same file, sequence them. Map:
   - `schemas.py`: W3.6 + W3.10 — sequence them.
   - `synthesizer.py`: W3.5 + W3.9 + W3.11 — sequence them.
   - `.env`: W3.1 + W3.2 + W3.8 — atomic (one edit batch).

---

## Success criteria (objective)

| Metric | PG_TEST_090 | Target PG_TEST_092 |
|---|---|---|
| Audit v2 total | 88.2 | ≥ 93 |
| G-Eval total | 59.5 | ≥ 80 |
| CoT leaked lines | 13 / 539 | 0 |
| Extraction success rate | 27 % | ≥ 80 % |
| Section truncation count | 4 | 0 |
| Wall clock | 7 h 48 min | ≤ 4 h |
| Inventory UNRESOLVED | 22 / 45 | 0 / 45 |
| Cost | $4.73 | ≤ $3.00 |

---

## Task index (TaskList IDs)

| Task | TaskID | Area |
|---|---|---|
| W1.1 env fixes | #18 | S3 env |
| W1.2 reasoning merge | #19 | S7 plumbing |
| W1.3 section-write exclude | #20 | S1 |
| W1.4 extraction cap | #21 | S3 code |
| W1.5 smoke | #22 | validation |
| W2.1 PG_TEST_091 | #23 | production run |
| W2.2 audit baseline | #24 | validation |
| W3.1 faithfulness gate | #25 | S2 #10 |
| W3.2 convergence threshold | #26 | S2 #11 |
| W3.3 trace session_id | #27 | S2 #12 |
| W3.4 perspective gap | #28 | S5 #23 |
| W3.5 empty outline filter | #29 | S5 #26 |
| W3.6 non-null fields | #30 | S8 #34-35 |
| W3.7 bronze investigation | #31 | S8 #36 |
| W3.8 NLI pair cap | #32 | S8 #38 |
| W3.9 biblio dedup | #33 | S8 #39 |
| W3.10 schema robust | #34 | S8 #40 |
| W3.11 faithfulness field | #35 | S9 #42 |
| W3.12 execution cap | #36 | S10 #44 |
| W3.13 PRE-V threshold | #37 | S8 #37 |
| W3.14 verify W1-cascade | #38 | S4 + budget |
| W3.15 final PG_TEST_092 | #39 | all-45 verification |

**22 tasks total. 45 inventory items covered.**
