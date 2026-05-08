# Codex Brief Review — I-bug-084 (ITER 1 of 5)

```
HARD ITERATION CAP: 5 per document. This is iter N of 5.
APPROVE iff zero NOVEL P0 + zero continuing P0 + zero P1.
```

## Pre-flight

- **Issue:** I-bug-084 — coverage scorer keywords. Add `expected_pico_keywords`; scorer prefers keywords when set; falls back to anchors. Acceptance: aspirin/migraine with keywords scores 1.0; without keywords falls back. LOC estimate 90.
- **Substrate today:** `src/polaris_v6/benchmark/schema.py` defines `BenchmarkQuestion` with `expected_anchors: list[str]` field but no `expected_pico_keywords` field. No coverage scorer module exists.
- **Honest framing per CLAUDE.md §9.4:** ship deterministic substrate that (a) extends the Pydantic schema with `expected_pico_keywords: list[str] = []` and (b) provides a `score_response_coverage(question, response_text)` function that returns 1.0 when all keywords are present (or all anchors if no keywords set), 0.0 otherwise; with token-presence (case-insensitive substring) match.

## Plan

### `src/polaris_v6/benchmark/schema.py` (MODIFY, +5 LOC)

Add field to `BenchmarkQuestion`:
```python
expected_pico_keywords: list[str] = Field(
    default_factory=list,
    description="PICO keywords; if set, scorer uses these instead of anchors.",
)
```

### `src/polaris_v6/benchmark/coverage_scorer.py` (NEW, ~25 LOC)

```python
def score_response_coverage(question: BenchmarkQuestion, response_text: str) -> float:
    """1.0 if all keywords (or anchors fallback) are present in response_text
    (case-insensitive substring match); else 0.0.

    Empty keywords AND empty anchors → 0.0 (no expectations to score against).
    """
    targets = question.expected_pico_keywords or question.expected_anchors
    if not targets:
        return 0.0
    lower = response_text.lower()
    return 1.0 if all(t.lower() in lower for t in targets) else 0.0
```

### Tests `tests/v6/benchmark/test_coverage_scorer.py` (NEW, ~50 LOC, 5 tests)

1. `test_aspirin_migraine_with_keywords_scores_1` — keywords `["aspirin", "migraine"]`; response "aspirin reduces migraine symptoms" → 1.0.
2. `test_keywords_present_takes_precedence_over_anchors` — keywords AND anchors set; response covers keywords only → 1.0 (not 0.0).
3. `test_no_keywords_falls_back_to_anchors_pass` — no keywords; anchors `["foo", "bar"]`; response includes both → 1.0.
4. `test_no_keywords_falls_back_to_anchors_fail` — no keywords; anchors `["foo", "bar"]`; response missing one → 0.0.
5. `test_no_targets_returns_zero` — empty keywords + empty anchors → 0.0.

## Risks for Codex Red-Team

1. **Match semantics:** case-insensitive substring; documented in docstring. Real-world tuning (stem/lemma) is post-MVP.
2. **§9.4 hygiene:** clean.
3. **CHARTER §3 LOC cap:** ~80 LOC net. Under 200.
4. **Acceptance literal "aspirin/migraine":** test 1 spelled out exactly.

## Acceptance criteria

1. `expected_pico_keywords` field added to `BenchmarkQuestion`.
2. New `coverage_scorer.py` with `score_response_coverage`.
3. Keywords preferred over anchors when set.
4. 5 tests pass including the named aspirin/migraine acceptance.
5. CHARTER §3 LOC cap respected.

**Forced enumeration:** before verdict, write one line per criterion 1-5.
**Completeness check:** list files actually read.

## Output schema

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```
