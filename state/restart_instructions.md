# Restart Instructions

## Current State (2026-03-27)
**SESSION 55: Evidence Deepening Loop — BUILT AND TESTED**

### What Was Built This Session
Evidence deepening loop — the key architectural change to close the 25% gap
to Gemini/ChatGPT Deep Research. The gap is in the evidence depth, not the model.

#### New Files
- `src/polaris_graph/agents/evidence_deepener.py` (~530 lines)
  - 6 operations: named study extraction, S2 citation chasing, S2 recommendations,
    mechanism keyword search, PDF full-text fetch, re-analyze and merge
  - Feature flag: `PG_EVIDENCE_DEEPENER=1` (default ON)
  - Only runs on first iteration (like STORM)
  - Evidence cap at 150 to prevent synthesis starvation
  - Time budget: 720s (12 min)
- `scripts/pg_micro_test_deepener.py` — 15/15 tests passing

#### Modified Files
- `src/polaris_graph/graph.py` — Added `deepen_evidence` node (9-node graph)
  - Placed between `verify` and `evaluate`
  - Merges new papers into `academic_results` for re-analysis on next iteration
  - Forces `needs_iteration=True` when new papers found
- `src/polaris_graph/state.py` — Added `deepened_papers`, `deepener_stats` fields
- `.env` — Added `PG_EVIDENCE_DEEPENER=1`
- `docs/todo_list.md`, `docs/file_directory.md` — Updated

#### Graph Flow
```
plan → search → storm → analyze → verify → DEEPEN → evaluate → synthesize
                                              ↓
                                    1. Named study extraction (LLM)
                                    2. S2 paper ID resolution
                                    3. S2 citation chasing + author search
                                    4. S2 recommendations
                                    5. Mechanism keyword search
                                    6. PDF full-text fetch
                                    → merge into academic_results
                                    → force next iteration
```

### Post-Build Fixes (4 fixes after initial build)
- FIX-DOI: URL-encoding in _s2_lookup() — `urllib.parse.quote(identifier, safe='')`. 3/4 DOIs resolve.
- FIX-MECH: Mechanism search relevance filter — `_filter_by_query_relevance()` added.
- FIX-FORWARD: Forward snowballing from legacy citation_chainer.py — `_fetch_citations()` via S2 /paper/{id}/citations.
- FIX-STATS: `_finalize()` uses `.get()` instead of `[]` for stats keys.

### Known Issues
- S2 DOI index incomplete (some papers only via PMID/ArXiv — Trepanowski 10.1001/jama.2017.3164)
- PO2 stochastic GLM-5 CoT leakage (pre-existing, not regression)
- No full pipeline run yet — 40/40 micro tests pass but integration untested

### Next Steps
1. **Run TEST_076** with deepening loop enabled
2. **Line-by-line audit** of output quality vs Gemini/ChatGPT
3. Tune mechanism query generation (may need domain-specific templates)

### Key Commands
```bash
python -u scripts/pg_test_061.py            # Full pipeline (currently PG_TEST_076)
python -u scripts/pg_micro_test_deepener.py # 15/15 deepener tests
python -u scripts/pg_micro_test_final.py    # 15/15 pre-launch tests
python -u scripts/pg_micro_test_071_fixes.py # 10/10 FIX-071 tests
```

### Config (.env)
```
OPENROUTER_DEFAULT_MODEL=z-ai/glm-5
PG_V3_ANALYTICAL_PROMPT=1
PG_V3_DEPTH_GATE=1
PG_MOST_ENABLED=1
PG_HARD_EVIDENCE_DEDUP=1
PG_SECTION_REASONING=1
PG_POLISH_PASS=1
PG_ACADEMIC_ONLY_GATE=1
PG_GRADE_STANDARDIZATION=1
PG_STORM_ENABLED=1
PG_EVIDENCE_DEEPENER=1
PG_MAX_ITERATIONS=2
```
