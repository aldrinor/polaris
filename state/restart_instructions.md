# Restart Instructions

## Current State (2026-03-22)
**SESSION 50: 27-Defect Fix Plan — ALL 5 WPs IMPLEMENTED + 2 BUG FIXES**

### What Happened This Session
Implemented the full 27-defect fix plan from the 7-run stress test audit. 5 work packages across 3 files, plus 2 post-smoke-test bug fixes discovered during verification. 3 smoke tests confirmed all fixes work.

**WP-1: Neutralize Defect-Creating Post-Processor**
- WP-1.1: Transform B gated behind `PG_TRANSFORM_B_ENABLED` (default OFF) — both primary + fallback blocks
- WP-1.2: P7 decimal boundary fix + R3 expanded-decimal rejection (10+ digits) + standalone expanded-decimal detector
- WP-1.3: P2 orphaned punctuation cleanup + sentence-length guard + bare-item removal (moved unconditional to end of post-processor)
- WP-1.4: Citation token whitespace normalization before dedup

**WP-2: Strengthen Quality Gate**
- WP-2.1: Template echo detector (4 patterns), echo_ok gate, scrub-before-return fallback, parroted_count threshold raised to 5
- WP-2.2: Grammar integrity check (mid-word cites + 80-word run-on detection)
- WP-2.3: Phantom citation removal via `_strip_phantom_citations()` helper — runs in quality gate AND `_post_process_interpretation()`
- WP-2.4: Hygiene score as SEPARATE 15-point metric in stress test (not folded into main score)

**WP-3: Fix Broken WS-1 + WS-5**
- WP-3.1: `audit_citations()` made async, `await load_nli_model()` replaces `run_until_complete()`
- WP-3.2: CiteFix uses runtime `os.getenv()` at call site instead of import-time `_CITEFIX_ENABLED`

**WP-4: Timeout Fallback**
- Budget threshold 180s→90s, fast-path emergency retry for <2500 char outputs

**WP-5: Dead Stage Removal**
- PQ-3 filler removal removed (too aggressive)
- Fix 3b fabricated matrix scores removed (removed evidence-backed content)

**Post-Smoke-Test Bug Fixes**
- Bug 1: Phantom citations in appended sections — `_strip_phantom_citations()` added to `_post_process_interpretation()` end
- Bug 2: Bare items from LLM rankings — cleanup moved from inside `if removed_cites > 0:` to unconditional at end of post-processor

**Commits**
- `acf0877` — Wave 5 NLI + FIX-D2 (5 pre-existing files)
- `3154f00` — 27-defect fix plan (3 files: react_agent.py, react_stress_test.py, test_react_agent.py)

### Smoke Test Results (3 runs)
| Run | PFAS Score | DVS Score | Mean | Phantoms | Bare Items |
|-----|-----------|-----------|------|----------|------------|
| 1 (pre-bugfix) | 86 | 80 | 83 | 3 | 5 |
| 2 (bug2 fixed) | 92 | 76 | 84 | 3 | 0 |
| 3 (both fixed) | 91 | 81 | 86 | 0 | 0 |

### Next Steps
1. **Full 7-run evaluation**: `python -u -m scripts.react_stress_test --fast --runs 7 --baseline outputs/stress_test_scores.json`
2. **Manual audit**: Read 1 full run line-by-line, grep for surviving defects
3. **Follow-up fixes** (next cycle):
   - Broaden template echo patterns for non-DVS domains
   - Add expanded-decimal cleanup to `_post_process_interpretation()`
   - Address deferred defects: C2 (table rows), C3 (exec summary), C4 (conditional recs)

### Key Commands
```bash
# Run all tests (204 expected)
python -m pytest tests/v3/test_react_agent.py -x -q

# Fast smoke test (2 sets, 300s timeout)
python -u -m scripts.react_stress_test --fast --sets 1

# Full 7-run evaluation with baseline
python -u -m scripts.react_stress_test --fast --runs 7 --baseline outputs/stress_test_scores.json

# Preflight
python -u scripts/pg_preflight_v2.py
```

### All Modified Files (This Session)
| File | Changes |
|------|---------|
| `src/polaris_graph/tools/react_agent.py` | WP-1 through WP-5 + bug fixes (+2625/-230 lines) |
| `scripts/react_stress_test.py` | WP-2.4 hygiene score + WP-3.1 async fix (+409 lines) |
| `tests/v3/test_react_agent.py` | 20 new/updated tests (+2475 lines) |
