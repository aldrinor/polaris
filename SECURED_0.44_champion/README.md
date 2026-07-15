# POLARIS Champion — highest-scoring in-house pipeline

**Our best in-house deep-research pipeline to date.** DeepResearch Bench task 72 (literature review on AI's restructuring of the labor market).

| Metric | Score |
|---|---|
| **RACE (overall)** | **0.4447** — Comprehensiveness 0.4569 · Insight 0.4293 · Instruction-Following 0.4587 · Readability 0.4310 |
| **FACT (citation faithfulness)** | **0.9032** — 84 supported / 93 validated |
| Report | 3,875 words · 37 citations |
| Judge | RACE `openai/gpt-5.5` · FACT validator `openai/gpt-5.4-mini` |

- **Code lineage:** repo `aldrinor/polaris`, branch `bot/outline-agent-box`, commit `df4118a`.
- **Champion output:** `champion_0.4447_report.md` (this folder). Byte-identical mechanism artifact: `outputs/step3_control/report.md` (same sha256, `50bdf50c…`).

---

## What's in this folder

| File | What it is |
|---|---|
| `README.md` | this entry point |
| `champion_0.4447_report.md` | the scored champion report (3,875 words) |
| `champion_0.4447_score.txt` / `_scorelog.log` | RACE score + judge log |
| `champion_report_with_tables.md` | report variant with evidence tables |
| `PIPELINE_FULL_BODY.md` | **full end-to-end map** — every stage (query→report→score) with file:line, commands, env flags, load-bearing modules, the two-engine (Opus + Codex-terra) reconciliation, the reproducibility ledger, and the preservation punch-list |
| `citation_verify.md` | proof (from the mechanism artifact) of which cited sources came from cp4 vs live search |
| `MANIFEST.sha256` | identity lock — sha256 of the report, compose artifact, and reproduction corpus + code commit |
| `RECIPE.md` | the short reproduce recipe |
| `.env.template` | required credential names (no values) |
| `corpus/` | **bundled reproduction corpus** — `cp4` (compose input, 997 ev / 329 clusters), `cp3` (baskets), `cp2` (evidence pool), plus the external canonical `cp2` and raw Stage-A snapshot (the latter holds the 1106-row selector input + source-origin distribution). Self-contained; no dependency on `/workspace/POLARIS`. |
| `compose_artifact/` | the byte-identical champion compose output — `report.md`, `bibliography.json` (37 refs, marks which came from live search), `compose_summary.json`, outline, methods |

---

## End-to-end pipeline (query → report → score)

Seven stages. Data handoff: `query → raw sources → evidence rows (cp2) → selected pool → baskets (cp3) → compose corpus (cp4) → report.md → scores`.

| # | Stage | Entrypoint | Output |
|---|---|---|---|
| A | Query intake + query planning + raw retrieval | `scripts/dr_benchmark/run_gate_b.py:main()` | `corpus_snapshot.json` (1,061 sources) |
| B | Fetch/scrape → fulltext → span → evidence rows | `retrieval/live_retriever.py:run_live_retrieval()` | `data/cp2_evidence_pool_snapshot.json` (997 rows / 919 URLs) |
| C | Evidence selection (keep-all under redesign) | `retrieval/evidence_selector.py:select_evidence_for_generation()` | `evidence_for_gen` (~997) |
| D | Consolidation & clustering | `synthesis/finding_dedup.py:dedup_by_finding()` (cp3 serializer: `generator/generation_snapshot.py`) | `data/cp3_s3gear_329basket_snapshot.json` (329 baskets) |
| E | cp3 → cp4 join (deterministic) | `scripts/cp3_to_cp4_corpus.py:build_cp4_corpus()` | `data/cp4_corpus_s3gear_329.json` (997 ev, 329 clusters) |
| F | Compose + multi-section generation | `scripts/compose_agentic_report_s3gear329.py:main()` → `generator/multi_section_generator.py` | `outputs/agentic_report_<TS>/report.md` |
| G | Scoring (RACE + FACT) | `third_party/deep_research_bench/deepresearch_bench_race.py` + `utils/stat.py` | RACE 0.4447 / FACT 84/93 |

### Reproduce the back half (cp4 → report → score)

```bash
cd /home/polaris/wt/outline_agent && git checkout df4118a && set -a && . ./.env && set +a

# Stage F — compose (⚠ flag traps below)
PG_OUTLINE_AGENT=1 PG_SYNTHESIS_QUANT_DIRECTIVE=0 \
python scripts/compose_agentic_report_s3gear329.py \
  --corpus data/cp4_corpus_s3gear_329.json --rq-drb-task 72 --max-parallel 3

# Stage G — RACE
cd third_party/deep_research_bench && LLM_BACKEND=openrouter RACE_MODEL=openai/gpt-5.5 \
python deepresearch_bench_race.py polaris_step3_control \
  --raw_data_dir data/test_data/raw_data --query_file data/prompt_data/query_task72.jsonl \
  --output_dir results/race/polaris_step3_control --max_workers 4 --only_en --force

# Stage G — FACT valid_rate from preserved validated.jsonl
python -m utils.stat --input_path results/fact/polaris_step3_control/validated.jsonl \
  --output_path results/fact/polaris_step3_control/fact_result.txt   # -> 0.9032 = 84/93
```

### ⚠ Flag traps (most common repro mistakes)
- The driver `setdefault`s `PG_SYNTHESIS_QUANT_DIRECTIVE=1`, but the champion is **OFF** → you must export `=0`.
- `PG_OUTLINE_WEB_SEARCH` defaults **ON** ("champion path"). Add `PG_OUTLINE_WEB_SEARCH=0` for a frozen corpus-only run (different report).
- Models are a **mix**: outline agent `z-ai/glm-5.2`; outliner-code + generator `deepseek/deepseek-v4-pro`.

---

## Reproducibility status (honest)

| Part | Status |
|---|---|
| E (cp3→cp4) | ✅ deterministic — corpus bundled in `corpus/` |
| F (compose) | ⚠ reproduces to *distribution* (~0.43–0.45); stochastic + live-web on |
| G (RACE / FACT-stat) | ✅ given keys / from preserved `validated.jsonl` |
| A–D (query→cp3) | ❌ snapshot-only (live web, non-deterministic); inputs preserved in `corpus/` but not re-runnable bit-for-bit |

**The exact 0.4447 champion is a preserved OUTPUT, not a reproducible one.** During compose the outline agent fired live web-search (9 SERPER + 10 Semantic-Scholar rounds) and folded in **107 rows that were never dumped**; **23 of the 37 citations came from that live search**, not cp4. The pipeline code runs end-to-end, but that specific report cannot be regenerated bit-for-bit. Full evidence: `citation_verify.md`; full ledger + punch-list: `PIPELINE_FULL_BODY.md`.
