"""I-deepfix-001 FIX-13 — 4IR run-validity reformulation FALSE-POSITIVE fix.

The drb_72 run aborted because ``check_question_fidelity`` scanned the WHOLE normalized report
body with plain substring containment, so 3 legitimately-CITED evidence mentions of "Fourth
Industrial Revolution" (real T2/T4 sources) tripped the reformulation gate. The gate's intent is a
TITLE/FRAMING reformulation, not cited body evidence.

FIX-13 adds ``PG_RUN_VALIDITY_REFORMULATION_FRAMING_ONLY`` (default OFF, exact "1" = ON). ON => a
forbidden phrase counts ONLY in a FRAMING position (any heading OR an uncited body line); a line
carrying a ``[N]`` citation marker is CITED evidence and is EXCLUDED. OFF => the verbatim body-wide
containment (byte-identical).

Acceptance (spec):
  (a) report with 3 CITED "Fourth Industrial Revolution" mentions + on-question H1 does NOT abort
      under framing_only=ON.
  (b) report whose H1/heading is a real reformulation STILL aborts.
  (c) an UNCITED prose line adopting a forbidden phrase STILL aborts.
  (d) flag OFF reproduces the current abort on the cited-evidence case (byte-identical).

NO network / NO spend / NO GPU: pure string predicates + tmp files.
GREEN = ``python -m pytest tests/dr_benchmark/test_run_validity_framing_only_fix13.py -q``.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.dr_benchmark.run_validity_gate import (
    RunValidityGateError,
    _framing_violation,
    check_question_fidelity,
    enforce_render_validity,
    evaluate_report_validity,
    load_task_output_contract,
    run_validity_reformulation_framing_only_enabled,
)

_ENV = "PG_RUN_VALIDITY_REFORMULATION_FRAMING_ONLY"

# The canonical DRB-II idx-56 bound question — mentions NEITHER forbidden phrase, so a report
# carrying "Fourth Industrial Revolution" while the bound question does not is a reformulation tell
# under the OLD body-wide rule.
_CANONICAL_QUESTION = (
    "I am researching the impact of Generative AI on the future labor market, please help me "
    "complete a research report ... positive views, negative views, specific challenges, and "
    "future opportunities."
)

_TABLE = (
    "| Research Literature | Country/Region | Application Area/Occupation | "
    "Specific Applications and Impacts | Key Risks and Limitations |\n"
    "|---|---|---|---|---|\n"
    "| Brynjolfsson 2023 | US | Call centres | +14% productivity | deskilling |\n"
)


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    monkeypatch.delenv(_ENV, raising=False)
    monkeypatch.delenv("PG_RUN_VALIDITY_GATE", raising=False)
    yield


def _contract():
    c = load_task_output_contract("drb_72_ai_labor")
    assert c is not None, "drb_72_ai_labor contract must exist in config"
    return c


# ── fixtures: full valid reports differing only in WHERE the forbidden phrase sits ────────────

# (a) on-question H1; 3 legitimately-CITED evidence mentions of the forbidden phrase (each line
#     carries a [N] marker) — the drb_72 false-positive case.
_REPORT_CITED_FIR = (
    "# Research report: The impact of Generative AI on the future labor market\n\n"
    "## Positive views\n\n"
    "Economists situate generative AI within the Fourth Industrial Revolution [1].\n"
    "The Fourth Industrial Revolution framing recurs across policy analyses [2].\n\n"
    "## Negative views\n\n"
    "Displacement is discussed relative to the Fourth Industrial Revolution debate [3].\n\n"
    "## Specific challenges\n\nMeasurement and adoption lag [4].\n\n"
    "## Future opportunities\n\nNew task creation offsets some displacement [5].\n\n"
    "## Summary table\n\n" + _TABLE
)

# (b) H1 is itself a reformulation adopting the forbidden phrase.
_REPORT_H1_REFORMULATED = (
    "# Research report: The restructuring impact of AI as a driver of the "
    "Fourth Industrial Revolution\n\n"
    "## Positive views\n\nProductivity rises [1].\n\n"
    "## Negative views\n\nDisplacement risk [2].\n\n"
    "## Specific challenges\n\nAdoption lag [3].\n\n"
    "## Future opportunities\n\nNew tasks [4].\n\n"
    "## Summary table\n\n" + _TABLE
)

# (c) on-question H1, but an UNCITED prose line adopts the forbidden phrase (no [N]).
_REPORT_UNCITED_FIR = (
    "# Research report: The impact of Generative AI on the future labor market\n\n"
    "## Positive views\n\n"
    "The Fourth Industrial Revolution will transform every occupation and workflow.\n\n"
    "## Negative views\n\nDisplacement risk [1].\n\n"
    "## Specific challenges\n\nAdoption lag [2].\n\n"
    "## Future opportunities\n\nNew tasks [3].\n\n"
    "## Summary table\n\n" + _TABLE
)

_FIR = "fourth industrial revolution"


# ── flag reader: default OFF, ONLY exact "1" enables ─────────────────────────────────────────

def test_flag_default_off():
    assert run_validity_reformulation_framing_only_enabled() is False


def test_flag_on_only_for_exact_1(monkeypatch):
    monkeypatch.setenv(_ENV, "1")
    assert run_validity_reformulation_framing_only_enabled() is True


@pytest.mark.parametrize("val", ["0", "true", "yes", "on", "TRUE", " 1 x", "", "2"])
def test_flag_strict_only_1(monkeypatch, val):
    monkeypatch.setenv(_ENV, val)
    # Spec: ONLY the exact string "1" (after strip) enables. " 1 " strips to "1" (True); everything
    # else is OFF. Guards against a fuzzy truthy-parse accidentally arming a behaviour change.
    expected = val.strip() == "1"
    assert run_validity_reformulation_framing_only_enabled() is expected


# ── _framing_violation pure predicate ────────────────────────────────────────────────────────

def test_framing_predicate_cited_mentions_are_not_a_violation():
    # (a) every FIR mention is on a [N]-cited line => NOT a framing violation.
    assert _framing_violation(_REPORT_CITED_FIR, _FIR) is False


def test_framing_predicate_heading_reformulation_is_a_violation():
    # (b) FIR in the H1 heading => framing violation.
    assert _framing_violation(_REPORT_H1_REFORMULATED, _FIR) is True


def test_framing_predicate_uncited_prose_is_a_violation():
    # (c) FIR on an uncited body line => framing violation.
    assert _framing_violation(_REPORT_UNCITED_FIR, _FIR) is True


def test_framing_predicate_subsection_header_is_a_violation():
    md = (
        "# Research report: The impact of Generative AI on the future labor market\n\n"
        "## The Fourth Industrial Revolution lens\n\nProse [1].\n"
    )
    assert _framing_violation(md, _FIR) is True


def test_framing_predicate_empty_phrase_is_false():
    assert _framing_violation(_REPORT_H1_REFORMULATED, "") is False


# ── check_question_fidelity: framing_only=True suppresses the cited false-positive ───────────

def test_cited_evidence_not_flagged_under_framing_only():
    # (a) the drb_72 case: framing_only=ON => NO reformulation-phrase violation.
    v = check_question_fidelity(
        _REPORT_CITED_FIR, _CANONICAL_QUESTION, _contract(), framing_only=True
    )
    assert not any("reformulation phrase" in m for m in v), v


def test_cited_evidence_still_flagged_under_body_wide_default():
    # (d) framing_only=OFF (default) reproduces the current abort: FIR is body-wide-present.
    v = check_question_fidelity(
        _REPORT_CITED_FIR, _CANONICAL_QUESTION, _contract(), framing_only=False
    )
    assert any("reformulation phrase" in m and "Fourth Industrial Revolution" in m for m in v), v


def test_default_signature_matches_body_wide_off():
    # No framing_only kwarg => same as framing_only=False (byte-identical caller compat).
    v_default = check_question_fidelity(_REPORT_CITED_FIR, _CANONICAL_QUESTION, _contract())
    v_off = check_question_fidelity(
        _REPORT_CITED_FIR, _CANONICAL_QUESTION, _contract(), framing_only=False
    )
    assert v_default == v_off


def test_heading_reformulation_still_flagged_under_framing_only():
    # (b) even with framing_only=ON, a reformulated TITLE still aborts.
    v = check_question_fidelity(
        _REPORT_H1_REFORMULATED, _CANONICAL_QUESTION, _contract(), framing_only=True
    )
    assert any("reformulation phrase" in m for m in v), v


def test_uncited_prose_still_flagged_under_framing_only():
    # (c) uncited prose adopting the phrase still aborts under framing_only=ON.
    v = check_question_fidelity(
        _REPORT_UNCITED_FIR, _CANONICAL_QUESTION, _contract(), framing_only=True
    )
    assert any("reformulation phrase" in m for m in v), v


def test_phrase_in_bound_question_never_flagged_either_mode():
    program_q = (
        "Please write a literature review ... key driver of the Fourth Industrial Revolution ..."
    )
    for fo in (True, False):
        v = check_question_fidelity(
            _REPORT_H1_REFORMULATED, program_q, _contract(), framing_only=fo
        )
        assert not any("reformulation phrase" in m for m in v), (fo, v)


# ── evaluate_report_validity threads framing_only ────────────────────────────────────────────

def test_evaluate_cited_report_valid_under_framing_only():
    # (a) full report is VALID (sections + table + anchors) with framing_only=ON.
    assert evaluate_report_validity(
        _REPORT_CITED_FIR, _CANONICAL_QUESTION, _contract(), framing_only=True
    ) == []


def test_evaluate_cited_report_invalid_under_default_off():
    # (d) same report FAILS under body-wide default (the false positive we are fixing).
    v = evaluate_report_validity(_REPORT_CITED_FIR, _CANONICAL_QUESTION, _contract())
    assert any("reformulation" in m for m in v), v


# ── enforce_render_validity: env-driven end-to-end (I/O reads env once) ───────────────────────

def _write_run(tmp_path: Path, report: str) -> Path:
    run_dir = tmp_path / "workforce" / "drb_72_ai_labor"
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "report.md").write_text(report, encoding="utf-8")
    (run_dir / "manifest.json").write_text(
        json.dumps({"status": "success"}) + "\n", encoding="utf-8"
    )
    return run_dir


def test_enforce_framing_only_on_does_not_abort_cited_report(tmp_path, monkeypatch):
    # (a) end-to-end: PG_RUN_VALIDITY_REFORMULATION_FRAMING_ONLY=1 => the drb_72 cited report ships.
    monkeypatch.setenv(_ENV, "1")
    run_dir = _write_run(tmp_path, _REPORT_CITED_FIR)
    q = {"slug": "drb_72_ai_labor", "domain": "workforce", "question": _CANONICAL_QUESTION}
    assert enforce_render_validity({"status": "success"}, q, run_dir) == []


def test_enforce_default_off_aborts_cited_report(tmp_path, monkeypatch):
    # (d) end-to-end byte-identical: env unset => body-wide => the original abort fires.
    monkeypatch.delenv(_ENV, raising=False)
    run_dir = _write_run(tmp_path, _REPORT_CITED_FIR)
    q = {"slug": "drb_72_ai_labor", "domain": "workforce", "question": _CANONICAL_QUESTION}
    with pytest.raises(RunValidityGateError):
        enforce_render_validity({"status": "success"}, q, run_dir)


def test_enforce_framing_only_on_still_aborts_reformulated_title(tmp_path, monkeypatch):
    # (b) end-to-end: framing_only=ON still aborts a genuinely reformulated H1.
    monkeypatch.setenv(_ENV, "1")
    run_dir = _write_run(tmp_path, _REPORT_H1_REFORMULATED)
    q = {"slug": "drb_72_ai_labor", "domain": "workforce", "question": _CANONICAL_QUESTION}
    with pytest.raises(RunValidityGateError):
        enforce_render_validity({"status": "success"}, q, run_dir)


def test_enforce_framing_only_on_still_aborts_uncited_prose(tmp_path, monkeypatch):
    # (c) end-to-end: framing_only=ON still aborts uncited prose adopting the phrase.
    monkeypatch.setenv(_ENV, "1")
    run_dir = _write_run(tmp_path, _REPORT_UNCITED_FIR)
    q = {"slug": "drb_72_ai_labor", "domain": "workforce", "question": _CANONICAL_QUESTION}
    with pytest.raises(RunValidityGateError):
        enforce_render_validity({"status": "success"}, q, run_dir)
