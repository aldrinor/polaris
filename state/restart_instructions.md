# Restart Instructions

## Current State (2026-04-01)
**SESSION 52: Claw Code Adoption — ALL 5 PHASES BUILT AND SMOKE TESTED**

### What Was Built This Session
5 phases from the Claw Code (Claude Code) architecture adoption plan, implementing
20 code changes across 3 source files + 6 config files. All 26 identified loopholes
addressed. 12/12 smoke tests passing, 223/223 existing tests passing.

#### Phase 2A: Evidence-Driven Outline (read-then-plan)
- `_summarize_evidence_clusters()` — LLM summarizes each cluster with specific findings
- `_generate_evidence_driven_outline()` — outline from evidence summaries, not query alone
- Feature flag: `PG_PHASE_2A_ENABLED=1`

#### Phase 2B: Focused Re-Extraction
- `_generate_section_questions()` — 2-3 focused questions per section
- `_focused_reextraction()` — per-section × per-question extraction from cached content
- Feature flag: `PG_PHASE_2B_ENABLED=1`

#### Phase 3A: Outline Critique Agent
- `_critique_outline()` — adversarial structural review, max 2 rounds
- Simple adjustments: merge thin sections, reorder, rename
- Feature flag: `PG_PHASE_3A_ENABLED=1`

#### Phase 3B: Sequential Writing with Quality Gates
- `PG_SECTION_WRITE_CONCURRENCY=1` (was 12)
- Per-section quality gate: word count >= 400, citations >= 2, no CoT
- Section summary generation for cross-referencing
- Covered claims cap: 20 stats + 50 claims

#### Phase 4: Post-Write Adversarial Review
- `_review_sections()` — per-section adversarial fact-checking
- `_apply_critical_fixes()` — regex/string fixes for CRITICAL issues only
- Feature flag: `PG_PHASE_4_ENABLED=1`

#### Phase 5: Modular Prompt Fragments
- 6 files in `config/prompts/`: base_rules, comparison, safety, mechanism, methodology, clinical
- `_detect_section_type()` — evidence-based type detection
- `_load_prompt_fragment()` — exclusive fragment injection per section
- Feature flag: `PG_PHASE_5_ENABLED=1`

### Modified Files
- `src/polaris_graph/agents/synthesizer.py` — Added 6 new async functions (~800 lines)
  - Phases 2A, 2B, 3A, 4 functions + synthesis flow wiring
- `src/polaris_graph/synthesis/section_writer.py` — Phase 3B quality gate, Phase 5 prompts (~150 lines)
- `src/polaris_graph/state.py` — Default concurrency 4→1
- `.env` — 6 new phase feature flags, concurrency=1
- `config/prompts/*.md` — 6 new prompt fragment files

### Synthesis Flow After Changes
```
synthesize_report():
    Filter evidence (relevance gate, faithfulness gate, over-removal guard)
    Step 1: Cluster evidence — UNCHANGED
    Step 1b: Assess cluster viability — UNCHANGED
    Step 2a: Phase 2A — Summarize clusters (NEW)
    Step 2b: Phase 2A — Evidence-driven outline (NEW) or legacy outline
    FIX-OUTLINE: Assign evidence to sections
    FIX-056: Trim empty sections
    Step 2c: Phase 3A — Outline critique (NEW)
    Step 2d: Phase 2B — Section questions + focused re-extraction (NEW)
    Step 3: Write sections (concurrency=1, Phase 3B quality gate, Phase 5 prompts)
    Step 3.5: Phase 4 — Post-write adversarial review (NEW)
    Step 4: Audit citations — UNCHANGED
    Step 5: Assemble report — UNCHANGED
```

### Next Step
Run TEST_083 to validate all 5 phases end-to-end with a real query.
Target: 80-85/100 (up from 75/100 baseline).

### How to Resume
1. Read CLAUDE.md
2. Read this file
3. Review .env for phase flags (all 5 enabled)
4. Run: `python -u -m scripts.pg_test_061 --query "your query here"`
5. Audit the output with `python scripts/run_audit.py --result-file <path>`
