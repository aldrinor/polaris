# POLARIS silent capability-downgrade audit — 2026-06-04 (I-cap-001 / #1059)

**Trigger:** operator caught POLARIS fetching only ~40 URLs when the design advertises "up to 1000
high-quality URLs." A 6-agent audit swept every capability dimension. **Operator directive: any
downgrade requires in-person approval; default posture is FULL capability.**

## Root finding
`config/settings/sota_parameters.yaml` documents the INTENDED depth (e.g. `max_sources_per_vector:
300`, `min_searches_per_vector: 100`, `url_timeout_seconds: 30`). **The code defaults hardcode far
lower values (40 / 20 / 20s) and ignore that config.** Multiple unit tests even ASSERT the SOTA
minimums (e.g. `PG_AGENTIC_PAGES_PER_ROUND >= 6`, `PG_AGENTIC_PAGE_CONTENT_CAP >= 15000`,
`PG_AGENTIC_FETCH_TIMEOUT >= 20`) — the code knows the right values but ships throttled. Net effect:
effective research depth ~40 URLs / 3 rounds / 10%-page-content vs the claimed frontier 1000 URLs /
12 rounds / full-page analysis.

Almost every knob is **env-overridable** — so lifting them needs NO code change, just env at run launch.

---

## TIER A — LIFT NOW (well-tested paths, just throttled; safe env overrides)

| Param (env) | Default | Recommend | Sev | What it costs us today |
|---|---|---|---|---|
| `PG_LIVE_FETCH_CAP` | 40 | **300** | CRIT | THE bottleneck — total URLs fetched. run12 got 26. |
| `PG_LIVE_MAX_SERPER` | 20 | **100** | CRIT | web results per query |
| `PG_LIVE_MAX_S2` | 20 | **100** | CRIT | academic results per query |
| `PG_DOMAIN_MAX_HITS` | 10 | **50** | HIGH | per specialised backend (arXiv/SEC/policy/EuropePMC/OpenAlex/GitHub) |
| `PG_MAX_EVIDENCE_TO_EXTRACT` | 600 | **1500** | HIGH | stops extracting evidence after 600 rows |
| `PG_DEEPENER_EVIDENCE_CAP` | 150 | **500** | MED | citation-graph secondary discovery |
| `PG_MOST_MAX_EVIDENCE` | 300 | **800** | MED | evidence rows reaching synthesis |
| `PG_LIVE_CONTENT_MAX` | 25000 | **50000** | MED | chars kept per fetched doc (truncates papers) |
| `PG_LIVE_RETRIEVER_MAX_WORKERS` | 8 | **16** | LOW | fetch concurrency (needed once cap is 300) |
| `DEFAULT_MAX_SUBQUERIES` (hardcoded, query_decomposer.py:36) | 6 | **15** | CRIT | sub-queries per question (NO env override — needs code) |
| ~~`PG_AMPLIFICATION_VARIANTS`~~ | 3 | ~~**8**~~ | ~~HIGH~~ → **RETIRED** | **I-ready-017 FX-19 (#1127): legacy-static-path-only; INERT under `PG_AGENTIC_SEARCH_ENABLED=1` (early return at `searcher.py:291-292`). NOT a benchmark lever — agentic breadth comes from decomposer/STORM/agentic loop. Do not set it for the benchmark.** |
| `PG_AMPLIFIER_SCOPE_FLOOR` | 0.15 | **0.08** | HIGH | drops valid regional/temporal variants (run12 dropped 19, kept 5) |
| `PG_V3_MAX_GAP_SEARCHES` | 2 | **5** | MED | gap-fill iterations |
| `PG_LIVE_HTTP_TIMEOUT` | 20s | **30s** | CRIT | dropped 14/40 fetches in run12 |
| `PG_AGENTIC_FETCH_TIMEOUT` | 15s | **30s** | CRIT | test asserts >=20; drops slow PDFs |
| `PG_PLAN_TIMEOUT` | 30s | **300s** | CRIT | aborts complex decompositions |
| `PG_FRAME_FETCHER_TIMEOUT` | 15s | **30s** | MED | CrossRef/PubMed enrichment |
| `PG_LLM_TIMEOUT_SECONDS` | 90s | **180s** | MED | verifier time pressure |
| `PG_OPENALEX_ENRICH_DEADLINE` | 45s | **90s** | MED | authority enrichment |
| `PG_POST_FETCH_LOOP_BUDGET` | 900s | **2400s** | MED | WILL break at 200+ sources |
| `PG_MAX_COST_PER_RUN` | 10 | **25** | MED | budget abort on deep runs |
| Section prose `max_tokens` (multi_section_generator.py:4056) | 2400 | **5000** | HIGH | ~2 paragraphs max per section (depth cap) |
| Limitations `max_tokens` (multi_section_generator.py:4064) | 400 | **1500** | CRIT | can't transparently report corpus gaps (§-1.1) |
| Trial-table `max_tokens` | 800 | **1200** | MED | truncates multi-outcome tables |

## TIER B — DISABLED CAPABILITIES (turn ON, but VERIFY they're wired in the launch path first)
These are whole features switched OFF. The Q1 capability audit warned "depth/conflict/memory machinery
unwired from launch path" — so they may be off because they're not actually wired/tested, not just
conservative. **Enabling blindly could break the run.** Verify each is reachable before the full run.

| Param (env) | Default | Recommend | Sev | Capability |
|---|---|---|---|---|
| `PG_AGENTIC_SEARCH_ENABLED` | 0 (OFF) | **1** | CRIT | Gemini-style 12-round deep agentic loop (the primary depth pipeline) |
| `PG_AGENTIC_PAGES_PER_ROUND` | 3 | **6** | CRIT | pages/round (test asserts >=6) |
| `PG_AGENTIC_PAGE_CONTENT_CAP` | 5000 | **15000** | CRIT | per-page chars (test asserts >=15000) |
| `PG_AGENTIC_SUMMARY_MAX_TOKENS` | 2048 | **4096** | HIGH | page-summary depth (test asserts >=4096) |
| `PG_AGENTIC_MAX_NOTEBOOK_ENTRIES` | 30 | **100** | HIGH | cross-round research memory |
| `PG_NLI_ENABLED` | 0 (OFF) | **1** | CRIT | NLI verification: 75% acc + FREE + 20-50x faster vs LLM 54% (needs flan-t5 model present) |
| `PG_V3_DEPTH_GATE` | 0 (OFF) | **1** | HIGH | analytical-depth quality gate |
| `PG_STORM_ENABLED` | 0 (OFF) | decide | — | multi-perspective interviews (perspectives 8→15, rounds 4→8) |
| `PG_SYNTHESIS_MAX_EXPANSION_PASSES` | 2 | **3** | MED | report-expansion passes |

## TIER C — KEEP (legitimate safety/correctness caps, NOT downgrades)
`PG_MAX_EVIDENCE_PER_CLAIM=20`, `PG_MAX_EVIDENCE_PER_URL=5`, Judge `max_tokens=16` (single enum
arbiter — intentional), Sentinel decomposition floor `3000` (below it the certified JSON truncates →
all-UNGROUNDED), Sentinel classifier `256`, the blank-verdict effort ladder `(xhigh,low,None)`,
`PG_ROLE_TRANSPORT_RETRIES=2`, `PG_PROVIDER_BLANK_RETRIES=3`, generator timeout `1800s`, seam timeout
`7200s`, react timeout `900s`. The Mirror reasoning cap `4000` is the honest #1053 GLM-no-op fix
(documented tradeoff — could raise to 8000 or swap the model later).

---

## Proposed env slate for the full VM run (Tier A only, pending operator approval)
```
PG_LIVE_FETCH_CAP=300 PG_LIVE_MAX_SERPER=100 PG_LIVE_MAX_S2=100 PG_DOMAIN_MAX_HITS=50 \
PG_MAX_EVIDENCE_TO_EXTRACT=1500 PG_DEEPENER_EVIDENCE_CAP=500 PG_MOST_MAX_EVIDENCE=800 \
PG_LIVE_CONTENT_MAX=50000 PG_LIVE_RETRIEVER_MAX_WORKERS=16 \
# PG_AMPLIFICATION_VARIANTS RETIRED (I-ready-017 FX-19 #1127): legacy-static-path-only, inert under agentic; do NOT set for the benchmark. \
PG_AMPLIFIER_SCOPE_FLOOR=0.08 PG_V3_MAX_GAP_SEARCHES=5 PG_LIVE_HTTP_TIMEOUT=30 \
PG_AGENTIC_FETCH_TIMEOUT=30 PG_PLAN_TIMEOUT=300 PG_FRAME_FETCHER_TIMEOUT=30 \
PG_LLM_TIMEOUT_SECONDS=180 PG_OPENALEX_ENRICH_DEADLINE=90 PG_POST_FETCH_LOOP_BUDGET=2400 \
PG_MAX_COST_PER_RUN=25
```
(DEFAULT_MAX_SUBQUERIES + the section/limitations max_tokens are hardcoded → small code PR. Tier B
enables held for verification-first.)

**Status: NOT applied. Awaiting operator per-tier approval per the no-silent-downgrade rule.**
