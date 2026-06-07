"""I-ready-018 FIX-A3 (#1143): a claimed number must be contained in the PRINTED cited span.

Regression lock for the drb_72 span-provenance misattribution: report claim 03-004
"...continuous R&D (50% versus 19%)" printed the token [#ev:ev_037:7500-8300], but
"50% versus 19%" is at index 8421 in ev_037 — OUTSIDE the cited span (a different metric:
the span is sales-growth; the claim's number is R&D-participation, ~121 chars past the span
end). The prior I-gen-005 local-window fallback "rescued" it by scanning the whole
direct_quote, so verify_sentence_provenance returned VERIFIED. FIX-A3 removes that
out-of-span rescue: a number absent from every cited span FAILS.

Design (CLAUDE.md §9.4 — no mocked evidence DB, no unittest.mock):
  * Uses the REAL frozen held-run evidence (tests/fixtures/drb72/evidence_pool.json, ev_037)
    and the REAL claim 03-004 sentence — not hand-typed data.
  * Drives the REAL production verifier verify_sentence_provenance.
  * Entailment judge forced OFF so the test is OFFLINE and isolates the mechanical
    numeric-in-span check.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from src.polaris_graph.generator.contract_section_runner import (  # noqa: E402
    _NUMERIC_DROP_PREFIXES,
    _drop_is_numeric,
)
from src.polaris_graph.generator.provenance_generator import (  # noqa: E402
    verify_sentence_provenance,
)

_FIXTURES = _REPO_ROOT / "tests" / "fixtures" / "drb72"

# The REAL claim 03-004 sentence + token from the held run (four_role_claim_audit.json).
_CLAIM_03_004 = (
    "AI-using firms in that sample reported higher sales growth "
    "(5.4% versus 3.7% for non-users) and were more likely to engage in "
    "continuous R&D (50% versus 19%) [#ev:ev_037:7500-8300]."
)


@pytest.fixture(autouse=True)
def _offline_entailment(monkeypatch):
    monkeypatch.setenv("PG_STRICT_VERIFY_ENTAILMENT", "off")
    monkeypatch.setenv("PG_VERIFICATION_MODE", "off")


def _ev037_direct_quote() -> str:
    pool = json.loads((_FIXTURES / "evidence_pool.json").read_text(encoding="utf-8"))
    ev = next(e for e in pool if e.get("evidence_id") == "ev_037")
    return ev.get("direct_quote") or ev.get("statement") or ""


def test_fixture_precondition_50_19_is_outside_the_cited_span():
    """Guard the fixture: '50% versus 19%' really is outside [7500:8300]."""
    dq = _ev037_direct_quote()
    idx = dq.find("50% versus 19%")
    assert idx >= 0, "fixture changed: '50% versus 19%' not in ev_037"
    assert not (7500 <= idx < 8300), f"expected out-of-span, got idx={idx}"
    # And neither 50 nor 19 appears INSIDE the cited span text.
    span = dq[7500:8300]
    assert "50" not in span and "19" not in span


def test_a3_real_03_004_misattribution_now_fails():
    """The real 03-004 claim FAILS: 50 / 19 are in no cited span, and the drop is a
    NUMERIC (un-rescuable) reason."""
    pool = {"ev_037": {"direct_quote": _ev037_direct_quote()}}
    sv = verify_sentence_provenance(_CLAIM_03_004, pool)
    assert sv.is_verified is False, "03-004 must drop — its number is outside the cited span"
    assert any(
        str(r).split(":", 1)[0] in _NUMERIC_DROP_PREFIXES for r in sv.failure_reasons
    ), sv.failure_reasons
    # Numeric drops are NOT rescue-eligible (cannot be laundered back into kept).
    assert _drop_is_numeric(sv) is True


def test_a3_false_drop_guard_number_genuinely_in_span_passes():
    """A number that IS inside its cited span must still pass (we did not over-tighten)."""
    span = (
        "The randomized cohort study measured the adverse event rate at "
        "42.5 percent among the treated participants."
    )
    pool = {"e1": {"direct_quote": span}}
    sentence = (
        "The cohort study adverse event rate was 42.5 percent "
        f"[#ev:e1:0-{len(span)}]."
    )
    sv = verify_sentence_provenance(sentence, pool)
    # Must NOT drop for a numeric reason (42.5 is inside the cited span).
    assert not any(
        str(r).split(":", 1)[0] in _NUMERIC_DROP_PREFIXES for r in sv.failure_reasons
    ), sv.failure_reasons
    assert sv.is_verified is True, sv.failure_reasons


def test_a3_structural_integers_beside_a_decimal_claim_do_not_false_drop():
    """Codex FIX-A3 iter-1 P1 guard: structural/admin integers (STEP 1, week 68, phase 3, 104
    weeks) sitting BESIDE a decimal claim must NOT be required in the cited span — only the
    decimal and any PERCENT-expressed integer are the claim. Prevents over-tightening that would
    false-drop legitimate clinical/report prose (e.g. trial/week/phase labels next to a result)."""
    span = (
        "In STEP 1 at week 68, the phase 3 trial of semaglutide over 104 weeks "
        "achieved a 14.9% mean weight loss."
    )
    pool = {"e": {"direct_quote": span}}
    sentence = (
        "In STEP 1, at week 68, the phase 3 trial achieved 14.9% reduction "
        f"[#ev:e:0-{len(span)}]."
    )
    sv = verify_sentence_provenance(sentence, pool)
    assert not any(
        str(r).split(":", 1)[0] in _NUMERIC_DROP_PREFIXES for r in sv.failure_reasons
    ), f"structural integers must not be required in the span: {sv.failure_reasons}"
    assert sv.is_verified is True, sv.failure_reasons


def test_a3_igen005_regression_number_in_unrelated_paragraph_still_fails():
    """The I-gen-005 'cancer 50% in an unrelated paragraph' class still FAILS: the number
    is in the evidence but outside the cited span, with no in-span support."""
    cited = (
        "The treatment cohort showed improved resolution outcomes over the "
        "control group across the measured endpoints."
    )
    far = " In an unrelated oncology section, cancer remission reached 50 percent."
    dq = cited + far
    pool = {"e2": {"direct_quote": dq}}
    sentence = (
        "The treatment cohort resolution improvement reached 50 percent "
        f"[#ev:e2:0-{len(cited)}]."
    )
    sv = verify_sentence_provenance(sentence, pool)
    assert sv.is_verified is False
    assert any(
        str(r).split(":", 1)[0] in _NUMERIC_DROP_PREFIXES for r in sv.failure_reasons
    ), sv.failure_reasons
