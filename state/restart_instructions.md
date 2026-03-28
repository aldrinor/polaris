# Restart Instructions

## Current State (2026-03-27)
**SESSION 55: Evidence Deepening Loop — BUILD PHASE**

### What Happened Last Session (Session 54)
Two-day sprint: 21 commits, 12 pipeline runs (TEST_062→075), 60+ micro tests.
- Fixed citation format (root cause: [SRC-NNN] vs [CITE:evidence_id])
- Switched to GLM-5 (#1 open-source model)
- Added: hard evidence dedup, GRADE ratings, polish pass, academic gate, 
  meta-commentary scrubber, SO WHAT analytical prompt, multi-perspective check
- Output quality: 0 citations → 75% of Gemini Deep Research

### The Core Insight (WHY we're not at 90%)
The remaining 25% gap is NOT the LLM or the prompt — it's the EVIDENCE.
Gemini writes deeper because it READS deeper sources (specific RCTs, landmark studies).
Our pipeline searches for topics (meta-analyses) but never follows citation chains
to find the specific primary studies those meta-analyses reference.

### BUILD TASK: Evidence Deepening Loop + Mechanism Search

#### Architecture
```
Current: plan → search → fetch → analyze → verify → synthesize → done
                                                      (shallow evidence)

New: plan → search → fetch → analyze → verify → DEEPEN → synthesize → done
                                                   ↓
                                         1. Named study extraction
                                         2. S2 citation chasing
                                         3. S2 recommendations
                                         4. Mechanism keyword search
                                         5. PDF full-text fetch
                                         6. Re-analyze deeper sources
                                         7. Merge into evidence pool
```

#### Operation 1: Named Study Extraction
- LLM reads evidence statements, extracts author names, trial names, journal refs
- "Trepanowski et al. found..." → search S2 for "Trepanowski intermittent fasting"
- Cost: 1 LLM call

#### Operation 2: S2 Citation Chasing
- For each meta-analysis/review in evidence pool:
  GET /paper/{paperId}/references?fields=title,abstract,year,openAccessPdf&limit=20
- Filter by relevance to query, take top 5
- Need S2 paper ID resolution first: GET /paper/URL:{source_url}
- Cost: ~10-15 S2 API calls (free, 1/sec)

#### Operation 3: S2 Recommendations
- POST /recommendations/v1/papers with seed paper IDs
- Returns up to 500 related papers ranked by relevance
- Cost: 1 API call

#### Operation 4: Mechanism Search (addresses Loophole 3)
- 3-5 keyword queries targeting WHY/HOW:
  "intermittent fasting thyroid mechanism HPT axis"
  "fasting autophagy cellular pathway signaling"
  "caloric restriction circadian rhythm molecular"
- Via Serper + S2 — finds the basic science papers citation chasing misses
- Cost: 3-5 search queries

#### Operation 5: PDF Full-text Fetch
- For papers with openAccessPdf, use _extract_pdf_text()
- Already implemented in access_bypass.py
- Paywalled papers: use abstract only (permanent ~5% ceiling vs Gemini)

#### Known Loopholes (from deep analysis)
1. S2 paper ID gap — need URL-to-ID resolution (50 calls, ~50s)
2. Paywalled papers — no clean solution, work with abstracts
3. Mechanism gap — addressed by Operation 4 (topic search, not citation chase)
4. Gap identification — needs meta-analysis full text with reference list
5. Evidence pool explosion — cap at 150 with relevance sorting
6. Time budget — ~12 extra minutes, within 150min budget

#### Existing Code to Reuse
- `src/utils/citation_chainer.py` — legacy citation chasing (review, adapt)
- `_fetch_citation_references()` in searcher.py — S2 references API
- `_extract_pdf_text()` in access_bypass.py — PDF extraction
- `_prefilter_academic_results()` — synonym expansion for relevance filter

#### Where It Goes in the Graph
New node `deepen_evidence` between `verify` and `synthesize` in graph.py.
Feature-flagged: PG_EVIDENCE_DEEPENER=1 (default ON)

### Gemini/ChatGPT Comparison PDFs
- Gemini: `C:\Users\msn\OneDrive\桌面\Download\Intermittent Fasting in Clinical Research_ Benefits, Risks, Evidence Quality, and Practical Guidance.pdf`
- ChatGPT: `C:\Users\msn\OneDrive\桌面\Download\Intermittent Fasting_ Benefits and Risks.pdf`

### Key Commands
```bash
python -u scripts/pg_test_061.py  # Currently PG_TEST_075
python -u scripts/pg_micro_test_final.py  # 15/15
python -u scripts/pg_micro_test_071_fixes.py  # 10/10
git log --oneline -25  # See all 21 commits
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
PG_MAX_ITERATIONS=2
```

### TEST_075 Output (latest successful run)
- 11,006 words, 131 citations, 54 sources, 7 sections, 4 diagrams
- 100% faithfulness, $3.59, 186 min
- Section 1: polish reasoning contaminated (fix committed, untested in full run)
- Sections 4,5,7: strong analytical quality with SO WHAT interpretation
- Section 2: shallow mechanism listing (needs mechanism search)
