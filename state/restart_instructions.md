# Restart Instructions

## Current State (2026-03-25)
**SESSION 54: 15-Defect Fix Sprint — COMPLETE, TEST_068 PASSING 6/6**

### What Happened This Session

Fixed 15 output quality defects in polaris_graph pipeline. Root cause: CITATION_RULES injected [SRC-NNN] format into v1/v3 prompt expecting [CITE:evidence_id], causing 0 citations in all runs. Discovered by reading LLM reasoning traces. Additional fixes: academic filter, filler stripping, newlines, evidence dedup, diagrams.

### Current Pipeline State
- TEST_068: 6,910 words, 124 citations, 49 sources, 100% faithfulness, $2.06
- 0 cross-section repetition, 1 filler word, 480 newlines, 5/5 diagrams
- 35/49 academic sources (was 0 before synonym expansion fix)
- Commit: f0ee5cf (15 files, 2682 insertions)

### Immediate Next Task
**Evidence redistribution** — hard dedup gives section 1 the most evidence (1628w) while sections 2-9 get 580-740w each. Need balanced allocation algorithm.

### Key Commands
```bash
# Run all 49 micro tests (5 suites)
python -u scripts/pg_micro_test_edge.py
python -u scripts/pg_micro_test_assembler.py
python -u scripts/pg_micro_test_edge_v2.py
python -u scripts/pg_micro_test_final.py
python -u scripts/pg_micro_test_risks.py

# Run pipeline test
python -u scripts/pg_test_061.py  # Currently set to PG_TEST_068

# Check test output
cat outputs/polaris_graph/PG_TEST_068_report.md
```

### Critical Files
| File | Purpose |
|------|---------|
| `src/polaris_graph/retrieval/synthesis_prompts.py` | CITE_EVIDENCE_RULES (was CITATION_RULES) |
| `src/polaris_graph/synthesis/report_assembler.py` | Post-processing: filler, newlines, hedge, merge |
| `src/polaris_graph/synthesis/section_writer.py` | Hard evidence dedup, stats exclusion |
| `src/polaris_graph/agents/searcher.py` | Synonym expansion, Exa fix, OpenAlex fix |
| `src/polaris_graph/agents/analyzer.py` | Low-credibility domain list |
| `src/polaris_graph/schemas.py` | Schema normalization (ReportOutline, EvidenceCluster) |
| `.env` | PG_HARD_EVIDENCE_DEDUP=1, PG_V3_ANALYTICAL_PROMPT=1 |

### Known Remaining Issues
1. Hard dedup first-come bias starves later sections (next task)
2. Stats exclusion prompt ignored by model (hard dedup compensates)
3. ~6 marginal bibliography sources survive (epocrates, brokenscience)
4. Reasoning still 60% mechanical (model limitation, not fixable with prompts)

### Future Considerations
- Local model: Qwen 3.5 27B Claude-distilled (HF: Jackrong/Qwen3.5-27B-Claude-4.6-Opus-Reasoning-Distilled) — $0/run, no DNS, 16.5GB VRAM Q4_K_M
- ReWOO agent migration (memory: 90/100 score)
