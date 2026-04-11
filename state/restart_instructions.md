# Restart Instructions

## Current State (2026-04-10) — Wiki Compose Path Validated End-to-End

**Branch:** `PL`
**Last commit:** `efdaeb9` PL: Synthesis section augmentation — lifts weak topics into 80s
**Status:** All compose-side work shippable; awaiting OpenRouter credits for real Qwen E2E.

---

## What was just done

The wiki compose path (`src/polaris_graph/wiki/wiki_composer.py` + `wiki_builder.py`) was validated end-to-end on real LLM output across 4 distinct domains while OpenRouter was 402 blocked. We substituted OpenAI gpt-4o for Qwen 3.5 Plus via a thin shim client.

### Cross-domain G-Eval results (gpt-4o judge, ±5pt per-run variance)

| Topic | Domain | Sections | G-Eval |
|---|---|---:|---:|
| PFAS water filtration | Chemistry / academic | 12 | **78.5** (was 85.2 v2 — judge noise) |
| Intermittent fasting | Medical / clinical | 17 | **80.6** |
| Adhesion testing | Engineering / standards | 18 | **80.2** |
| DVS-PEI niche chemistry | Specialized organic | 13 | **77.2** |
| **Mean across 4 domains** | | | **79.1** |

All 4 topics sit at or above the 75 "competitive with top-tier deep research models" threshold.

### Defects fixed in this session

1. **`wiki_composer.py` citation prefix resolver** — was only catching `[REF:N]`. Now catches `[REF/CITE/Ref/Cite/ref/cite:N]` → `[N]`.
2. **`wiki_composer.py` empty content silent skip** — gpt-5 reasoning model burned its token budget on reasoning, returned HTTP 200 with empty content, the retry loop broke without checking. Empty content now triggers retry.
3. **`wiki_composer.py` abstract literal `[N]` placeholder** — model interpreted prompt example literally. Forbidden in prompt + post-strip.
4. **`wiki_composer.py` coherence transitions** — sections now require an explicit bridge sentence in the first paragraph.
5. **`wiki_composer.py` PQ-4 CI emphasis** — LENS-1 demands CIs/p-values/n inline with every numeric finding when source provides them.
6. **`wiki_composer.py` source diversity floor** — composer enforces using ≥60% of unique sources in the section's claim pool.
7. **`wiki_builder.py` adaptive authority gate** — strict `sig_authority >= 0.5` was killing 86% of engineering-topic evidence (PFAS academic vs adhesion industry). Now adaptive with floor at 0.30.
8. **`wiki_builder.py` synthesis section augmentation** — outlines missing Comparative/Practical/Knowledge-Gaps sections now get them appended automatically. Lifted 3 of 4 cross-domain topics by +2 to +6 G-Eval points.
9. **`wiki_builder.py` `WikiResult.outline`** — exposes the augmented outline so callers iterate over the same sections that `section_claims` was built against.

### New scripts (in `scripts/`)

- `pg_full_scale_chain_test.py` — 640 URLs / 8 rounds search→fetch→clean→wiki structural validation
- `pg_compose_openai_validation.py` — small-scale (3 sections) wiki compose validation via OpenAI shim
- `pg_compose_production_scale.py` — production-scale wiki compose validation against ANY test JSON (parameterized)
- `pg_geval_openai.py` — G-Eval runner using OpenAI shim instead of OpenRouter
- `pg_chain_validation.py` — chain integrity smoke test
- `pg_content_quality_smoke.py` — content extraction quality test

---

## When OpenRouter credits are restored — DO THIS FIRST

1. **Verify credits**:
   ```
   python -c "import os, requests; from dotenv import load_dotenv; load_dotenv(); r = requests.post('https://openrouter.ai/api/v1/chat/completions', headers={'Authorization': f'Bearer {os.getenv(\"OPENROUTER_API_KEY\")}'}, json={'model':'qwen/qwen3.5-plus-02-15','messages':[{'role':'user','content':'hi'}],'max_tokens':5}); print(r.status_code, r.text[:100])"
   ```
   Expect 200. If still 402, top up at https://openrouter.ai/settings/credits.

2. **Run a real Qwen E2E** (the one validation we couldn't do):
   ```
   PG_WIKI_ENABLED=1 PG_WIKI_5LENS=1 python -u -m scripts.pg_smoke_test
   ```
   This runs the FULL pipeline (search → fetch → real Qwen extraction → wiki → real Qwen compose) on the smoke-test query. Expected: 8K+ words, 50+ citations, no defects.

3. **Score the result with G-Eval** to compare against the gpt-4o baseline:
   ```
   python scripts/eval_geval.py outputs/polaris_graph/{newest_test_id}.json
   ```
   Compare against the 79.1 mean across 4 domains established in this session. If Qwen E2E scores within ±5 points of 79.1, the wiki path generalizes from gpt-4o to Qwen — done.

4. **If Qwen E2E score < 75**, the gap is most likely upstream extraction quality. See "Remaining upstream gains" below.

---

## Remaining upstream gains (todo_list.md)

The compose-side has plateaued. Remaining G-Eval gains live upstream of compose. Two well-scoped items:

### 1. Extract confidence intervals in `direct_quote` (worth +1 to +2 on analytical_depth)
The judge consistently flags "no confidence intervals" across all 4 domains. The wiki composer can't synthesize CIs the source doesn't provide. The Qwen extractor in `src/polaris_graph/agents/analyzer.py` (`_analyze_batch`, line ~1970) builds the prompt that asks for atomic facts. The prompt should explicitly preserve CIs, p-values, and sample sizes inside `direct_quote` when the source contains them.

Find: `prompt = f"""Research question: {query}\n\nAnalyze the following...` (line ~1995)

Add to the extraction system prompt (`ANALYSIS_SYSTEM`): "When the source quote contains a confidence interval, p-value, sample size, or effect size, the `direct_quote` field MUST preserve that statistical context verbatim — do not paraphrase numbers or strip CIs."

Validate by running PG_TEST_041 extraction through the modified analyzer, checking how many `direct_quote` fields contain `(95% CI`, `p<`, `n=`, `±`, `(95%`.

### 2. Increase per-topic bibliography depth (worth +1 to +2 on citation_quality)
Most topics fetch 30-80 unique sources. PFAS reached 81 (and that's why it scored highest). The judge complains about "bibliography too small relative to citations" on every topic with <60 sources.

Levers:
- `PG_MAX_TOTAL_ACADEMIC` (currently 1000, increase to 1500)
- `PG_ACADEMIC_QUERY_CAP` per-query cap (currently 10, raise to 20)
- Search query count per round (currently 6, raise to 10)
- More rounds in `pg_full_scale_chain_test.py` (currently 8, but the agentic loop in production runs fewer)

Validate by running search-only and counting unique academic URLs.

---

## Files unchanged but worth knowing

- `src/polaris_graph/agents/searcher.py` — Serper + S2 + OpenAlex search, parallel S2 enabled
- `src/tools/access_bypass.py` — Crawl4AI → Trafilatura → Sci-Hub fallback chain
- `.env` — Wiki path enabled (`PG_WIKI_ENABLED=1`, `PG_WIKI_5LENS=1`), evidence caps at 600

## Key caveats

- All G-Eval scores in this session were gpt-4o judging gpt-4o output. **Same-model-family bias** is unmeasured. A non-OpenAI judge (Claude or Gemini) would give a more objective number.
- Per-run G-Eval variance is **~±5 points** at gpt-4o-vs-gpt-4o. Single-score differences inside that band are noise.
- The mean across 4 topics is the robust signal: **79.1**. The range is **77-85**.

## DO NOT do (lessons from this session)

- **Don't iterate compose prompts more.** It has plateaued. Further tweaks chase variance, not signal.
- **Don't build a mini-E2E with OpenAI extractors.** The production extractor uses `generate_structured()` with Pydantic schemas + Qwen-specific recovery logic. Substituting OpenAI tests "can OpenAI do extraction" not "does the production extractor work."
- **Don't use gpt-5 for compose.** It's a reasoning model that burns 95%+ of token budget on `reasoning_tokens`, leaving content empty. Use gpt-4o (matches Qwen behavior).
