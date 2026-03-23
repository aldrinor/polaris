# Restart Instructions

## Current State (2026-03-23)
**SESSION 51: Generate-Then-Attribute Architecture — READY TO IMPLEMENT**

### What Happened Last Session (Session 50-51)

**Session 50 (committed, 4 commits):**
- 27-defect fix plan fully implemented (5 WPs + 2 bug fixes)
- 204 tests pass, 3 smoke tests verified (mean 86/100, 0 phantoms, 0 bare items)
- 7-run evaluation completed (mean 83.5, 95% CI [57.1, 94.7])
- Full manual audit of all 14 interpretation outputs
- All documentation updated

**Session 51 (research + planning, no code committed):**
- Researched production RAG output quality (ACL 2024-2026, PaperQA2, Anthropic, CiteFix, ReClaim, STORM)
- Attempted 3 template patch iterations — ALL FAILED:
  1. "What evidence supports X's role in Y?" → leaked 20+ instances
  2. "How does X affect Y?" → DVS collapsed to 58/100 (too vague)
  3. "What specific findings describe X's impact on Y?" → leaked 25+ new instances
- **Root cause confirmed:** ANY distinctive phrase in qualitative claim template will echo. Template patching is a dead end.
- **Decision:** Generate-Then-Attribute architecture — separate prose generation from citation placement
- **Plan written and critically reviewed:** `C:\Users\msn\.claude\plans\cached-popping-locket.md`
- Experimental code changes REVERTED to clean committed state

### Next Step: Implement Generate-Then-Attribute

**Read the plan first:** `C:\Users\msn\.claude\plans\cached-popping-locket.md`

The plan has 6 critical issues identified and fixed, 2 moderate issues, realistic effort estimates (~190 min implementation + ~120 min validation), and a feature flag for safe rollback.

**Summary of the 3 changes:**
1. **CHANGE-1:** Strip `[CITE:ev_xxx]` from scaffold — replace with `(refs: ev_xxx)` metadata
2. **CHANGE-2:** Strip `[CITE:ev_xxx]` from write prompt — LLM writes clean prose
3. **CHANGE-3:** New `_attribute_citations()` — 3-strategy (number + keyword + embedding) citation placement at sentence boundaries

**Feature flag:** `PG_GENERATE_THEN_ATTRIBUTE=1` (default OFF for safe rollback)

### Key Baseline Numbers
- **Pre-fix mean:** 83.5/100 (7-run, 14 outputs)
- **DVS range:** 77-91
- **PFAS range:** 69-86
- **Defects eliminated (Session 50):** A1, A3, B5, C1, D1, D4 (all at 0/14 runs)
- **Defects remaining:** B1 (50%), B3 (14%), D2 (21%), grammar (93%), verbatim (29%)

### Key Commands
```bash
# Tests (204 expected, clean committed state)
python -m pytest tests/v3/test_react_agent.py -x -q

# Smoke test
python -u -m scripts.react_stress_test --fast --sets 1

# 7-run evaluation with baseline
python -u -m scripts.react_stress_test --fast --runs 7 --baseline outputs/stress_test_scores.json

# Preflight
python -u scripts/pg_preflight_v2.py
```

### Commits (Session 50, all on v3-rewrite branch)
- `353c9da` — file_directory.md update
- `d2407cc` — Session 50 documentation
- `3154f00` — 27-defect fix plan (main code change)
- `acf0877` — Wave 5 NLI + FIX-D2

### Critical Files
| File | Purpose |
|------|---------|
| `src/polaris_graph/tools/react_agent.py` | Main file — ALL changes go here |
| `tests/v3/test_react_agent.py` | 204 tests — need ~8 new + ~30 updated |
| `C:\Users\msn\.claude\plans\cached-popping-locket.md` | Full implementation plan with critical review |
