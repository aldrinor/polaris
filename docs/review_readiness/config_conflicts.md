# Config conflicting-default keys — RESOLVED (19/20 collapsed) + 1 deferred

Each of these PG_ env vars was read with DIFFERENT hardcoded fallback defaults at different
call sites (a latent path-dependent bug). Collapsed to each key's **authoritative runtime
value**, byte-safe, faithfulness never weakened. Oracle replay stays byte-identical (golden
9c0a3d43); collection 16738/11; codex verdict CONFIG-COLLAPSE-SAFE.

## Collapsed (19)
**BYTE-SAFE (set in .env → env wins at runtime, only the unused fallback changed — byte-identical):**
PG_AGENTIC_MAX_ROUNDS, PG_ANALYSIS_BATCH_TIMEOUT, PG_CLUSTER_BATCH_TIMEOUT(600),
PG_CONTENT_PER_SOURCE(25000), **PG_FAITHFULNESS_NLI_THRESHOLD(0.75)**, PG_FETCH_CONCURRENCY(10),
PG_MAX_CITATION_FREQUENCY(10), PG_MAX_CROSS_SOURCE_PAIRS(50), PG_MAX_TOTAL_ACADEMIC(100),
PG_MAX_WORDS_PER_SECTION(3000), **PG_MIN_EVIDENCE_PER_SECTION(5)**, PG_MIN_EVIDENCE_UTILIZATION(0.40),
PG_MIN_QUOTE_WORDS(5), PG_MIN_TOTAL_WORDS(0), PG_REDUNDANCY_JACCARD_THRESHOLD(0.65),
PG_TARGET_TOTAL_WORDS(8000).

**SAFE-PRIMARY (not in .env; live-path value preserved, only a dead/unused constant aligned up):**
PG_ANALYSIS_PIPELINE('8phase'), PG_FETCH_TIMEOUT(live 30 kept), PG_REACT_INTERPRET_TIMEOUT(live 180 kept).

**Faithfulness note:** the 3 faithfulness-critical keys were verified NOT weakened — NLI threshold
0.75→0.75 (env authoritative), evidence-count 5→5 at runtime (env imposes 5), utilization 0.40→0.40.

## Deferred to owner (1)
- **PG_GENERATOR_MODEL** — `''` vs `<no default>` have different missing-env semantics; env dominance
  would make it byte-safe too, but the empty-vs-absent decision is left for the owner.
