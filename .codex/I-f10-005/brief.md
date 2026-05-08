# Codex Brief Review — I-f10-005 (ITER 1 of 5)

```
HARD ITERATION CAP: 5 per document. This is iter N of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## What you are reviewing

You are reviewing this PLAN, NOT the working tree. Brief review = plan-soundness; diff review = code-matches-plan.

## Pre-flight

- **Issue:** I-f10-005 — Chart provenance schema. Scope: "every chart cites source data via Evidence Contract spans". Acceptance: "schema; tests". LOC estimate 100.
- **Existing substrate:** `src/polaris_v6/charts/spec_builder.py` already emits `polaris_provenance: { chart_type, evidence_ids, period_kind? }` on each chart spec. Tests at `tests/v6/test_charts.py` access these fields via dict lookups (no formal type validation).
- **What's missing:** a formal Pydantic schema for `polaris_provenance` + validator that round-trips dict↔model + adversarial tests for invalid inputs. This locks the contract that all future chart consumers (I-f10-006 click-through, I-f10-007 sandboxed exec) can depend on.
- **Honest framing per CLAUDE.md §9.4:** This Issue ships the SCHEMA + TESTS only. The richer "Evidence Contract spans" linkage (start/end byte offsets per datum, per I-f10-006 click-through) is a follow-up; this Issue locks the foundation (chart_type enum + evidence_ids list + period_kind constraint).

## Plan

### Backend

1. New module `src/polaris_v6/charts/provenance.py`:
   - `ChartType = Literal["forest_plot", "comparison_table", "timeline"]` (re-export from spec_builder).
   - `TimelinePeriodKind = Literal["date", "quarter", "year"]`.
   - `ChartProvenance(BaseModel)`:
     - `chart_type: ChartType`
     - `evidence_ids: list[str]` with `Field(min_length=1)` (every chart MUST cite ≥1 evidence_id).
     - `period_kind: TimelinePeriodKind | None = None` (only valid when chart_type==timeline).
     - `model_validator(mode="after")`: if `chart_type == "timeline"`, `period_kind` MUST be non-None; if `chart_type != "timeline"`, `period_kind` MUST be None. Raise `ValueError` on violation.
   - `validate_chart_provenance(spec: dict[str, Any]) -> ChartProvenance`:
     - Extracts `spec["polaris_provenance"]`.
     - If missing key, raises `ValueError("chart spec missing polaris_provenance")`.
     - Returns `ChartProvenance(**spec["polaris_provenance"])` (Pydantic validates field-level + cross-field).

2. `src/polaris_v6/charts/__init__.py`: add `from polaris_v6.charts.provenance import ChartProvenance, validate_chart_provenance` for clean import.

3. `src/polaris_v6/charts/spec_builder.py`: NO changes needed (existing dict output already conforms). The schema is a CONSUMER-side contract — builders produce dicts; consumers (this Issue's validator + future I-f10-006 click-through) parse them.

### Tests

4. `tests/v6/test_chart_provenance.py` (NEW):
   - `test_validate_forest_plot_provenance` — produces forest plot via existing `build_forest_plot`, validates with `validate_chart_provenance`, asserts model has correct `chart_type` + `evidence_ids` + `period_kind=None`.
   - `test_validate_comparison_table_provenance` — same shape for comparison table.
   - `test_validate_timeline_provenance` — timeline with `period_kind="quarter"`, asserts model has `period_kind="quarter"`.
   - `test_missing_polaris_provenance_raises` — empty dict → `ValueError("chart spec missing polaris_provenance")`.
   - `test_empty_evidence_ids_raises` — `polaris_provenance: { chart_type: "forest_plot", evidence_ids: [] }` → Pydantic ValidationError.
   - `test_unknown_chart_type_raises` — `chart_type: "scatter_plot"` → ValidationError.
   - `test_timeline_without_period_kind_raises` — `chart_type: "timeline"` without period_kind → ValidationError (cross-field validator).
   - `test_non_timeline_with_period_kind_raises` — `chart_type: "forest_plot"` with `period_kind: "quarter"` → ValidationError.

## Risks for Codex Red-Team

1. **Backward compatibility:** `ChartProvenance` model accepts the existing dict shape produced by `build_forest_plot` / `build_comparison_table` / `build_timeline` without modification. `extra = "allow"` could be set to permit future additive fields (e.g., `evidence_spans` per datum in I-f10-006); plan: leave Pydantic default (forbid extra) and add fields explicitly when later issues need them.
2. **`evidence_ids: list[str]` min_length=1:** every chart MUST cite ≥1 evidence_id. Empty-list rejection enforces "every chart cites source data" acceptance language.
3. **Cross-field validator:** timeline → period_kind required; non-timeline → period_kind forbidden. This locks the existing builder behavior (only timeline emits period_kind).
4. **No spec_builder changes:** existing dict output is already conformant. This Issue is consumer-side validation substrate.
5. **§9.4 N/A backend.**
6. **CHARTER §1 LOC cap:** estimated ~50 LOC schema + ~70 LOC tests + ~5 LOC __init__ = ~125. Under 200. Within issue_breakdown LOC estimate of 100 + slack.

## Acceptance criteria

1. New `ChartProvenance` Pydantic model in `src/polaris_v6/charts/provenance.py` with `chart_type`, `evidence_ids` (min_length=1), `period_kind`.
2. Cross-field validator: timeline ⇔ period_kind set; non-timeline ⇔ period_kind None.
3. `validate_chart_provenance(spec)` extracts and validates `polaris_provenance` from a Vega-Lite spec dict.
4. Tests cover all 3 chart types valid + 5 invalid cases (missing key, empty evidence_ids, unknown chart_type, timeline without period_kind, non-timeline with period_kind).
5. Existing `spec_builder.py` output passes the new validator (back-compat).
6. CHARTER §1 LOC cap respected (≤200 net).

**Forced enumeration:** before verdict, write one line per criterion 1-6.

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

APPROVE iff zero NOVEL P0 + zero continuing P0 + zero P1.
