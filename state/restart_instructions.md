# Restart Instructions

## Current State (2026-03-26)
**SESSION 54 (continued): Output Quality Sprint — TEST_072 COMPLETE, PENDING FULL AUDIT**

### What Happened This Session

Massive output quality sprint across 12 commits. Started with 0 citations (TEST_062), ended at 78% of Gemini Deep Research quality (TEST_072). Key changes:

1. **Citation format fix** (root cause): CITATION_RULES [SRC-NNN] → [CITE:evidence_id]
2. **Model switch**: Qwen 3.5 Plus → GLM-5 (#1 open-source, Chatbot Arena 1451)
3. **FIX-GLM5**: Always-reason model handling (reasoning as content, CoT stripping)
4. **Evidence pipeline**: Synonym expansion (926 rejected papers → passing), hard dedup, fair-share redistribution
5. **Post-processing**: Filler strip, newline insertion, hedge replacement, table cleanup, transition injection disabled
6. **Quality features**: Depth gate, MoST reflector, GRADE standardization, per-section polish pass, academic gate, PDF extraction
7. **Schema fixes**: ReportOutline, SectionOutlineItem, EvidenceCluster normalization

### TEST_072 Results (NEEDS FULL LINE-BY-LINE AUDIT)
- 6/6 quality gates PASS
- 11,747 words, 136 citations, 41 sources, 12 sections, 5 diagrams
- 100% faithfulness, $3.04, 102 min
- 0 CoT leakage, 0 fillers, 532 newlines
- GRADE: 38/88 (43%) rated — up from 14% but skewed HIGH
- Polish pass: per-section chunking active
- Academic gate: active for clinical queries
- 85% academic sources (correctly classified)
- ONLY 4/12 sections read, 4/34 reasoning traces checked — INCOMPLETE AUDIT

### CRITICAL NEXT STEP: Full Audit of TEST_072
Read ALL 12 sections, ALL reasoning traces, ALL 5 diagrams, full bibliography. Compare against Gemini/ChatGPT PDFs at:
- `C:\Users\msn\OneDrive\桌面\Download\Intermittent Fasting in Clinical Research_ Benefits, Risks, Evidence Quality, and Practical Guidance.pdf` (Gemini)
- `C:\Users\msn\OneDrive\桌面\Download\Intermittent Fasting_ Benefits and Risks.pdf` (ChatGPT)

### Pipeline Test History This Session
| Test | Words | Citations | Sources | Model | Cost | Key Issue |
|------|-------|-----------|---------|-------|------|-----------|
| 062 | 1,455 | 0 | 0 | Qwen | $3.21 | Citation format + DNS |
| 063 | 13,027 | 118 | 48 | Qwen | $1.86 | 175 fillers, 0 newlines |
| 065 | 7,367 | 117 | 48 | Qwen | $1.74 | 82 fillers, 0 newlines |
| 067 | 7,658 | 134 | 46 | Qwen | $1.47 | 0 repeats, 0 fillers |
| 068 | 6,910 | 124 | 49 | Qwen | $2.06 | 35 academic, 5 diagrams |
| 069 | 2,234 | 27 | 12 | GLM-5 | $0.27 | 1/15 sections (dedup starved) |
| 070 | 12,632 | 148 | 52 | GLM-5 | $3.42 | 1 CoT leak in section 5 |
| 071 | 13,258 | 171 | 55 | GLM-5 | $2.91 | Polish failed, 14% GRADE |
| 072 | 11,747 | 136 | 41 | GLM-5 | $3.04 | PENDING FULL AUDIT |

### Commits This Session (12 total)
```
f0ee5cf  Fix 15 output quality defects
2ed31c7  Evidence redistribution
fb301e9  Close quality gap: depth gate, extraction, PDF, reasoning
2404b5e  Switch to GLM-5 + always-reason client handling
602b3ac  FIX-069: Pull from unclaimed pool when section has 0 evidence
eb1be38  FIX-GLM5-COT: Strip chain-of-thought prefix
2293d87  Close remaining quality gap: polish, academic gate, GRADE
10d99e6  Fix polish/GRADE for GLM-5: reason() + enhanced CoT parsing
ff34ceb  Polish pass truncation guard + scale tests
6a0a740  FIX-071: GRADE batch 5, chunked polish, diagram gate, domain list
3a5ae71  FIX-071B: CoT strip in reason() + retry for polish/GRADE
7216156  Fix diagram quality gate bypass on retry path
```

### Key Commands
```bash
# Run all micro test suites (7 suites, ~60 tests)
python -u scripts/pg_micro_test_edge.py
python -u scripts/pg_micro_test_assembler.py
python -u scripts/pg_micro_test_edge_v2.py
python -u scripts/pg_micro_test_final.py
python -u scripts/pg_micro_test_risks.py
python -u scripts/pg_micro_test_gaps.py
python -u scripts/pg_micro_test_071_fixes.py

# Run pipeline test
python -u scripts/pg_test_061.py  # Currently PG_TEST_072

# Check output
cat outputs/polaris_graph/PG_TEST_072_report.md
```

### Critical Config (.env)
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

### Remaining Known Issues
1. GRADE ratings skewed HIGH (32/38 rated HIGH) — needs calibration
2. Polish pass CoT strip sometimes fails on short prompts — retry guards in place
3. 2 trivial diagrams escaped quality gate on retry path — fixed in 7216156
4. Section 4 (glucose) thin at 351w — evidence gaps acknowledged honestly
5. GLM-5 verbosity concern not materialized (reasoning tokens cheap)
