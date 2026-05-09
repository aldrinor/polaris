# Codex Brief Review — I-cj-004 (ITER 1 of 5)

```
HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — reserve P0/P1 for real execution risks.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## Pre-flight

- **Issue:** I-cj-004 — Zero-verified abort Crown Jewel test. Scope: assert `abort_no_verified_sections` fires when all sections fail. Acceptance: test green. LOC estimate 80.
- **Substrate today:** `src/polaris_graph/generator2/verified_report.py` ships:
  - `PipelineVerdict = Literal["success", "abort_no_verified_sections"]` (line 38).
  - `Section` with `section_status: SectionStatus = Literal["verified", "regenerated", "dropped"]`.
  - `VerifiedReport._verdict_consistency` model_validator (lines 466-487):
    - `verdict="success"` requires at least one non-dropped section → else `ValueError("requires at least one non-dropped section")`.
    - `verdict="abort_no_verified_sections"` requires every section be `dropped` (or empty) → else `ValueError("requires all sections (if any) to be dropped")`.
- **Honest framing per CLAUDE.md §9.4:** ship `tests/crown_jewels/test_cj_004_zero_verified_abort.py` that pins CLAUDE.md §9.1.4. Four tests:
  1. abort verdict + only dropped sections → constructs successfully (positive).
  2. abort verdict + empty sections list → constructs successfully (edge — corpus had no input).
  3. abort verdict + a kept (non-dropped) section → ValueError fires.
  4. success verdict + only dropped sections → ValueError fires (the symmetric tooth).
- Update `docs/crown_jewels.md` row 4: test path → `tests/crown_jewels/test_cj_004_zero_verified_abort.py`; bound function → `src/polaris_graph/generator2/verified_report.py::VerifiedReport._verdict_consistency`.

## Plan

### `tests/crown_jewels/test_cj_004_zero_verified_abort.py` (NEW, ~95 LOC, 4 tests)

```python
"""Crown Jewel I-cj-004 — Zero-verified abort invariant.

Per CLAUDE.md §9.1.4: if every section fails strict_verify, the report
verdict MUST be 'abort_no_verified_sections' (not a pseudo-success
report). Conversely, a 'success' verdict requires >=1 non-dropped
section.

Bound by VerifiedReport._verdict_consistency (model_validator).
"""

from __future__ import annotations
from datetime import datetime, timezone
import pytest
from pydantic import ValidationError
from src.polaris_graph.generator2.verified_report import (
    Section, VerifiedReport, VerifiedSentence,
)


def _dropped_section(sid: str = "sec_x") -> Section:
    return Section(
        section_id=sid, section_title="X",
        verified_sentences=[
            VerifiedSentence(
                section_id=sid, sentence_text="bad claim",
                provenance_tokens=[],
                verifier_pass=False, drop_reason="no_provenance_token",
            ),
        ],
        section_verify_pass_rate=0.0, section_status="dropped",
    )


def _kept_section(sid: str = "sec_x") -> Section:
    return Section(
        section_id=sid, section_title="X",
        verified_sentences=[
            VerifiedSentence(
                section_id=sid, sentence_text="claim [#ev:src-A:0-3].",
                provenance_tokens=["[#ev:src-A:0-3]"],
                verifier_pass=True, drop_reason=None,
            ),
        ],
        section_verify_pass_rate=1.0, section_status="verified",
    )


def _report_kwargs() -> dict:
    return dict(
        pool_id="p1", decision_id="d1",
        overall_verify_pass_rate=0.0,
        generator_model="g", evaluator_model="strict_verify_v1",
        verifier_pass_threshold=0.4,
        started_at_utc=datetime.now(timezone.utc),
        finished_at_utc=datetime.now(timezone.utc),
        latency_ms=0, cost_usd=0.0,
    )


def test_cj_004_abort_with_all_dropped_sections_constructs() -> None:
    rpt = VerifiedReport(
        sections=[_dropped_section("a"), _dropped_section("b")],
        pipeline_verdict="abort_no_verified_sections",
        **_report_kwargs(),
    )
    assert rpt.pipeline_verdict == "abort_no_verified_sections"
    assert rpt.kept_sections() == []


def test_cj_004_abort_with_empty_sections_constructs() -> None:
    rpt = VerifiedReport(
        sections=[],
        pipeline_verdict="abort_no_verified_sections",
        **_report_kwargs(),
    )
    assert rpt.pipeline_verdict == "abort_no_verified_sections"


def test_cj_004_abort_with_kept_section_raises() -> None:
    with pytest.raises(ValidationError, match="requires all sections.*dropped"):
        VerifiedReport(
            sections=[_dropped_section("a"), _kept_section("b")],
            pipeline_verdict="abort_no_verified_sections",
            **_report_kwargs(),
        )


def test_cj_004_success_with_only_dropped_sections_raises() -> None:
    with pytest.raises(ValidationError, match="requires at least one non-dropped"):
        VerifiedReport(
            sections=[_dropped_section("a")],
            pipeline_verdict="success",
            **_report_kwargs(),
        )
```

### `docs/crown_jewels.md` (MODIFY)

Update row 4: test path + bound `VerifiedReport._verdict_consistency`.

## Risks for Codex Red-Team

1. **ValidationError vs ValueError** — Pydantic v2 wraps model_validator ValueError in ValidationError; tests use `ValidationError` and match against the inner message via regex.
2. **Substrate-honest** — pure schema-validation pinning; no new functionality.
3. **§9.4 hygiene** — clean.
4. **CHARTER §3 LOC cap** — ~95 LOC under 200.

## Acceptance criteria

1. New `tests/crown_jewels/test_cj_004_zero_verified_abort.py` with 4 tests.
2. `docs/crown_jewels.md` row 4 updated.
3. All 4 tests pass.
4. CHARTER §3 LOC cap respected.

**Forced enumeration:** before verdict, write one line per criterion 1-4.

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
