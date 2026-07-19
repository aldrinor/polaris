# Config finding: env vars with CONFLICTING default fallbacks

**Status:** discovered during Phase 1C config migration (2026-07-19). Not yet resolved — each needs a product decision on the single correct default.

These PG_ environment variables are read via `os.getenv(KEY, default)` at multiple call sites, but with **different** hardcoded fallback defaults. When the env var is unset, behavior therefore depends on *which code path* reads it first — a latent inconsistency. They were deliberately EXCLUDED from the central `resolve()` registry (which holds one default per key) because there is no single byte-identical value to adopt.

Each must be resolved by choosing the intended default, setting it in `.env` / the registry, and collapsing all call sites to it.

| Key | Conflicting defaults seen | Note |
|-----|---------------------------|------|
| `PG_AGENTIC_MAX_ROUNDS` | '12', '2' |  |
| `PG_ANALYSIS_BATCH_TIMEOUT` | '180', '240.0' |  |
| `PG_ANALYSIS_PIPELINE` | '', '8phase' |  |
| `PG_CLUSTER_BATCH_TIMEOUT` | '300', '600' |  |
| `PG_CONTENT_PER_SOURCE` | '10000', '25000' |  |
| `PG_FAITHFULNESS_NLI_THRESHOLD` | '0.65', '0.75' | FAITHFULNESS-CRITICAL: the frozen-faithfulness gate runs at two strictnesses (0.65 vs 0.75) depending on path. |
| `PG_FETCH_CONCURRENCY` | '10', '5' |  |
| `PG_FETCH_TIMEOUT` | '20', '30' |  |
| `PG_GENERATOR_MODEL` | '', <none> |  |
| `PG_MAX_CITATION_FREQUENCY` | '5', '8' |  |
| `PG_MAX_CROSS_SOURCE_PAIRS` | '200', '50' |  |
| `PG_MAX_TOTAL_ACADEMIC` | '100', '500' |  |
| `PG_MAX_WORDS_PER_SECTION` | '1500', '2000' |  |
| `PG_MIN_EVIDENCE_PER_SECTION` | '3', '5', '8' | Three distinct defaults (3/5/8) — evidence floor varies by path. |
| `PG_MIN_EVIDENCE_UTILIZATION` | '0.30', '0.40' | Utilization gate 0.30 vs 0.40. |
| `PG_MIN_QUOTE_WORDS` | '15', '5' |  |
| `PG_MIN_TOTAL_WORDS` | '0', '10000' | 0 vs 10000 — one path effectively disables the floor. |
| `PG_REACT_INTERPRET_TIMEOUT` | '180', '240' |  |
| `PG_REDUNDANCY_JACCARD_THRESHOLD` | '0.45', '0.65' | Dedup threshold 0.45 vs 0.65. |
| `PG_TARGET_TOTAL_WORDS` | '12000', '8000' | Report length target differs 8000 vs 12000. |

**Recommendation:** treat the faithfulness/evidence-gate keys (top of table) as priority — a divergent faithfulness threshold can silently weaken the frozen-faithfulness guarantee on one path.
