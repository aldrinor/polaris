# Claude architect audit — I-bug-084

## Issue scope
Coverage scorer keywords. Add `expected_pico_keywords` to BenchmarkQuestion; scorer prefers keywords when set; falls back to anchors.

## What landed
- `src/polaris_v6/benchmark/schema.py`: +5 LOC field.
- `src/polaris_v6/benchmark/coverage_scorer.py`: ~17 LOC pure function.
- `tests/v6/benchmark/test_coverage_scorer.py`: 5 tests including the named "aspirin/migraine with keywords scores 1.0" acceptance.

## Architectural alignment
- Plan §4.9b (coverage scorer keywords) per breakdown.
- §9.4 hygiene clean. CHARTER §3 LOC: 74 net.

## Verdict
Ready to merge. 5/5 pass. Codex brief + diff APPROVE iter 1.
