# Codex Diff Review — I-f10-005 (ITER 1 of 5)

```
HARD ITERATION CAP: 5 per document. This is iter N of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## Static review only — DO NOT spawn dev servers.

**Issue:** I-f10-005 — Chart provenance schema
**Brief:** APPROVED iter 1 (0/0/0/3 — all 3 P2 fixes applied in this diff)
**Canonical-diff-sha256:** `19d7ae9127f58a3e7c4c72268c073739698e51438e39138b182e967a0280bae6`
**LOC:** 175 net (under CHARTER §1 200-cap)

## Files

```
src/polaris_v6/charts/provenance.py    NEW +63 (ChartProvenance Pydantic model + validate_chart_provenance)
src/polaris_v6/charts/__init__.py      +14 -1 (re-export schema symbols)
tests/v6/test_chart_provenance.py      NEW +99 (11 tests covering 3 valid + 8 invalid cases)
```

## What changed

### `provenance.py` (NEW)
- `ChartType = Literal["forest_plot", "comparison_table", "timeline"]`.
- `TimelinePeriodKind = Literal["date", "quarter", "year"]`.
- `ChartProvenance(BaseModel)` with `model_config = ConfigDict(extra="forbid")` (per Codex iter-1 P2 — strict schema lock).
- Fields: `chart_type`, `evidence_ids: list[str] = Field(min_length=1)`, `period_kind: TimelinePeriodKind | None = None`.
- `field_validator("evidence_ids")` rejects blank strings (per Codex iter-1 P2 — non-blank evidence_id strings).
- `model_validator(mode="after")` enforces timeline ⇔ period_kind cross-field consistency.
- `validate_chart_provenance(spec: dict) -> ChartProvenance`:
  - Missing key → `ValueError("chart spec missing polaris_provenance")`.
  - Non-dict value → `ValueError(f"polaris_provenance must be a dict, got {type(raw).__name__}")` (per Codex iter-1 P2 — clean error on malformed containers).
  - Otherwise constructs and returns `ChartProvenance`.

### `__init__.py`
- Re-exports `ChartProvenance`, `ChartType`, `TimelinePeriodKind`, `validate_chart_provenance` from `polaris_v6.charts.provenance`.

### `test_chart_provenance.py` (NEW)
- Round-trip tests: each of `build_forest_plot` / `build_comparison_table` / `build_timeline` output → `validate_chart_provenance` returns valid model.
- Adversarial tests:
  - `test_missing_polaris_provenance_raises` — empty dict.
  - `test_polaris_provenance_not_dict_raises` — string value.
  - `test_empty_evidence_ids_raises` — `evidence_ids=[]`.
  - `test_blank_evidence_id_raises` — `evidence_ids=["ev1", "  "]`.
  - `test_unknown_chart_type_raises` — `chart_type="scatter_plot"`.
  - `test_timeline_without_period_kind_raises` — cross-field validator triggers.
  - `test_non_timeline_with_period_kind_raises` — cross-field validator triggers.
  - `test_extra_field_forbidden` — extra="forbid" rejects unknown fields.

## Verification
- `PYTHONPATH=src python -m pytest tests/v6/test_chart_provenance.py -v` → **11 passed in 1.39s**.
- Existing `test_charts.py` (forest plot, comparison table, timeline + meta-analysis adversarial) untouched.
- `validate_chart_provenance(build_*(...))` round-trips cleanly for all 3 chart types.

## Risks for Codex Red-Team

1. **Back-compat:** existing builders' dict outputs pass the new validator unchanged (round-trip tests prove this).
2. **`extra="forbid"`:** strict schema lock. Future Issues that add fields (e.g., `evidence_spans` per datum for I-f10-006) MUST update this model rather than silently injecting extras.
3. **Cross-field validator:** timeline ⇔ period_kind. Locks existing builder behavior.
4. **No spec_builder.py changes:** consumer-side schema only. Builders continue to emit dicts; validators parse them.
5. **§9.4 N/A backend.**
6. **CHARTER §1 LOC cap:** 175 net. Under 200.

## Output schema (mandatory)

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

APPROVE iff zero NOVEL P0 + zero continuing P0 + zero P1.
