"""RED/GREEN for the I-deepfix-001 loss-risk run-validity gates (FIX-1 / FIX-2 / FIX-3).

FIX-1  the four scope+timeline ENFORCEMENT flags are wired into the Gate-B benchmark slate
       (force-ON) AND the pre-spend fail-closed required set (H1 scope gate DARK closed).
FIX-2  the render-time QUESTION-FIDELITY gate catches a report that answered a REFORMULATED prompt
       (the drb_72 "Fourth Industrial Revolution / English-language journal articles only" title
       that zeroed info_recall) + PG_BENCHMARK_OFFICIAL_QUESTION is required pre-spend.
FIX-3  the render-time CONTRACT-SCAFFOLD gate catches a report missing the task's stated output
       contract (task72 = four named sections + a final 5-column summary table).

NO network / NO spend / NO GPU: pure string predicates + tmp files + the module-level constants.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from scripts.dr_benchmark.run_validity_gate import (
    RunValidityGateError,
    check_contract_scaffold,
    check_question_fidelity,
    enforce_render_validity,
    evaluate_report_validity,
    extract_h1,
    load_task_output_contract,
    run_validity_gate_enabled,
)

# --------------------------------------------------------------------------- fixtures

_CANONICAL_QUESTION = (
    "I am researching the impact of Generative AI on the future labor market, please help me "
    "complete a research report ... positive views, negative views, specific challenges, and "
    "future opportunities."
)

# The I-safety-002b program prompt that SHARES the slug — legitimately carries the phrases that
# are a wrong-question tell only when they are ABSENT from the bound question.
_PROGRAM_QUESTION = (
    "Please write a literature review on the restructuring impact of Artificial Intelligence (AI) "
    "on the labor market ... key driver of the Fourth Industrial Revolution ... Ensure the review "
    "only cites high-quality, English-language journal articles."
)

_TABLE = (
    "| Research Literature | Country/Region | Application Area/Occupation | "
    "Specific Applications and Impacts | Key Risks and Limitations |\n"
    "|---|---|---|---|---|\n"
    "| Brynjolfsson 2023 | US | Call centres | +14% productivity | deskilling |\n"
)

_GOOD_REPORT = (
    "# Research report: The impact of Generative AI on the future labor market\n\n"
    "## Positive views\n\nGenerative AI raises productivity [1].\n\n"
    "## Negative views\n\nDisplacement risk in some occupations [2].\n\n"
    "## Specific challenges\n\nMeasurement and adoption lag [3].\n\n"
    "## Future opportunities\n\nNew task creation [4].\n\n"
    "## Summary table\n\n" + _TABLE
)

_WRONG_QUESTION_REPORT = (
    "# Research report: The restructuring impact of AI as a driver of the "
    "Fourth Industrial Revolution, citing only English-language journal articles\n\n"
    "## Findings\n\nSome prose.\n"
)


def _contract():
    """The real drb_72 contract from the shipped config (proves the config parses + is complete)."""
    c = load_task_output_contract("drb_72_ai_labor")
    assert c is not None, "drb_72_ai_labor contract must exist in config/benchmark/task_output_contracts.yaml"
    return c


# --------------------------------------------------------------------------- FIX-2 fidelity

def test_forbidden_reformulation_absent_from_bound_question_is_a_violation():
    # RED path: report reformulated to FIR / English-only, bound question is the canonical GenAI one.
    v = check_question_fidelity(_WRONG_QUESTION_REPORT, _CANONICAL_QUESTION, _contract())
    assert any("Fourth Industrial Revolution" in m for m in v)
    assert any("English-language journal articles" in m for m in v)


def test_forbidden_phrase_present_in_bound_question_is_not_flagged():
    # GREEN path: the program prompt legitimately contains those phrases -> NOT a reformulation flag
    # (an anchor-mismatch message may still quote the title verbatim; assert on the reformulation kind).
    v = check_question_fidelity(_WRONG_QUESTION_REPORT, _PROGRAM_QUESTION, _contract())
    assert not any("reformulation phrase" in m for m in v), v


def test_good_report_passes_question_fidelity():
    assert check_question_fidelity(_GOOD_REPORT, _CANONICAL_QUESTION, _contract()) == []


def test_missing_intent_anchor_in_title_is_a_violation():
    contract = {"intent_anchors": [["generative ai", "generative artificial intelligence"]]}
    report = "# Research report: A study of quantum computing hardware\n\nbody"
    v = check_question_fidelity(report, _CANONICAL_QUESTION, contract)
    assert any("intent anchors" in m for m in v)


def test_no_h1_title_is_a_violation_when_anchors_required():
    contract = {"intent_anchors": [["generative ai"]]}
    v = check_question_fidelity("no heading here at all", _CANONICAL_QUESTION, contract)
    assert any("NO level-1 title" in m for m in v)


def test_extract_h1_strips_stock_prefix():
    assert extract_h1("# Research report: Foo bar\n\n## Sec") == "Foo bar"
    assert extract_h1("## only h2\n") is None


# --------------------------------------------------------------------------- FIX-3 scaffold

def test_missing_required_section_is_a_violation():
    # Drop the "opportunities" section.
    report = _GOOD_REPORT.replace("## Future opportunities\n\nNew task creation [4].\n\n", "")
    v = check_contract_scaffold(report, _contract())
    assert any("opportunit" in m.lower() for m in v), v


def test_missing_required_table_is_a_violation():
    report = _GOOD_REPORT.replace(_TABLE, "no table here\n")
    v = check_contract_scaffold(report, _contract())
    assert any("summary table" in m for m in v), v


def test_wrong_table_columns_is_a_violation():
    bad_table = "| A | B | C |\n|---|---|---|\n| 1 | 2 | 3 |\n"
    report = _GOOD_REPORT.replace(_TABLE, bad_table)
    v = check_contract_scaffold(report, _contract())
    assert any("summary table" in m for m in v), v


def test_extra_sixth_column_is_a_violation():
    # RED-before-fix: a header carrying the 5 required columns PLUS a 6th extra column must FAIL the
    # EXACT-match contract (the old subset check wrongly PASSED it — the Codex P1 fail-open).
    extra_table = (
        "| Research Literature | Country/Region | Application Area/Occupation | "
        "Specific Applications and Impacts | Key Risks and Limitations | Notes |\n"
        "|---|---|---|---|---|---|\n"
        "| Brynjolfsson 2023 | US | Call centres | +14% productivity | deskilling | extra |\n"
    )
    report = _GOOD_REPORT.replace(_TABLE, extra_table)
    v = check_contract_scaffold(report, _contract())
    assert any("summary table" in m for m in v), v


def test_reordered_columns_is_a_violation():
    # RED-before-fix: the same 5 columns in a DIFFERENT order must FAIL the exact-order contract
    # (the old order-independent `all(any(...))` check wrongly PASSED it).
    reordered_table = (
        "| Country/Region | Research Literature | Application Area/Occupation | "
        "Specific Applications and Impacts | Key Risks and Limitations |\n"
        "|---|---|---|---|---|\n"
        "| US | Brynjolfsson 2023 | Call centres | +14% productivity | deskilling |\n"
    )
    report = _GOOD_REPORT.replace(_TABLE, reordered_table)
    v = check_contract_scaffold(report, _contract())
    assert any("summary table" in m for m in v), v


def test_substring_header_column_is_a_violation():
    # RED-before-fix: a substring header ("Research Literature Notes" superset of the required
    # "Research Literature") must FAIL the exact match (the old `rc in cell` check wrongly PASSED it).
    substring_table = (
        "| Research Literature Notes | Country/Region | Application Area/Occupation | "
        "Specific Applications and Impacts | Key Risks and Limitations |\n"
        "|---|---|---|---|---|\n"
        "| Brynjolfsson 2023 | US | Call centres | +14% productivity | deskilling |\n"
    )
    report = _GOOD_REPORT.replace(_TABLE, substring_table)
    v = check_contract_scaffold(report, _contract())
    assert any("summary table" in m for m in v), v


def test_blank_trailing_column_is_a_violation():
    # RED-before-fix (Codex P1 fail-open): a header carrying the 5 required columns PLUS a
    # trailing BLANK 6th cell (``| ... | |``) is a SIX-column row. The old
    # ``[c for c in _cells(line) if c]`` filter dropped the empty cell -> 5 cells -> wrongly
    # PASSED the exact 5-column match. Keeping the internal blank cell makes it a 6-column header
    # that does not equal the 5 required columns -> it must FAIL the contract.
    blank_col_table = (
        "| Research Literature | Country/Region | Application Area/Occupation | "
        "Specific Applications and Impacts | Key Risks and Limitations | |\n"
        "|---|---|---|---|---|---|\n"
        "| Brynjolfsson 2023 | US | Call centres | +14% productivity | deskilling | |\n"
    )
    report = _GOOD_REPORT.replace(_TABLE, blank_col_table)
    v = check_contract_scaffold(report, _contract())
    assert any("summary table" in m for m in v), v


def test_good_report_passes_contract_scaffold():
    assert check_contract_scaffold(_GOOD_REPORT, _contract()) == []


def test_full_valid_report_has_zero_violations():
    assert evaluate_report_validity(_GOOD_REPORT, _CANONICAL_QUESTION, _contract()) == []


def test_wrong_question_report_fails_both_dimensions():
    v = evaluate_report_validity(_WRONG_QUESTION_REPORT, _CANONICAL_QUESTION, _contract())
    assert any("reformulation" in m for m in v)         # FIX-2
    assert any("contract-scaffold" in m for m in v)     # FIX-3 (no sections / no table)


# --------------------------------------------------------------------------- config loader

def test_unknown_slug_has_no_contract():
    assert load_task_output_contract("drb_99_not_a_task") is None


def test_missing_config_file_returns_none(tmp_path):
    assert load_task_output_contract("drb_72_ai_labor", path=tmp_path / "nope.yaml") is None


# --------------------------------------------------------------------------- I/O enforcement

def _write_run(tmp_path: Path, report: str) -> Path:
    run_dir = tmp_path / "workforce" / "drb_72_ai_labor"
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "report.md").write_text(report, encoding="utf-8")
    (run_dir / "manifest.json").write_text(
        json.dumps({"status": "success"}) + "\n", encoding="utf-8"
    )
    return run_dir


def test_enforce_raises_and_quarantines_on_wrong_question(tmp_path, monkeypatch):
    monkeypatch.delenv("PG_RUN_VALIDITY_GATE", raising=False)
    run_dir = _write_run(tmp_path, _WRONG_QUESTION_REPORT)
    q = {"slug": "drb_72_ai_labor", "domain": "workforce", "question": _CANONICAL_QUESTION}
    with pytest.raises(RunValidityGateError):
        enforce_render_validity({"status": "success"}, q, run_dir)
    # Durable marker + manifest flip so a downstream scorer never ships it as success.
    marker = json.loads((run_dir / "run_validity_gate.json").read_text(encoding="utf-8"))
    assert marker["verdict"] == "FAILED" and marker["violations"]
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "abort_run_validity_gate"


def test_enforce_returns_empty_on_valid_report(tmp_path):
    run_dir = _write_run(tmp_path, _GOOD_REPORT)
    q = {"slug": "drb_72_ai_labor", "domain": "workforce", "question": _CANONICAL_QUESTION}
    assert enforce_render_validity({"status": "success"}, q, run_dir) == []


def test_enforce_noop_when_report_absent(tmp_path):
    run_dir = tmp_path / "workforce" / "drb_72_ai_labor"
    run_dir.mkdir(parents=True, exist_ok=True)
    q = {"slug": "drb_72_ai_labor", "domain": "workforce", "question": _CANONICAL_QUESTION}
    # Mocked run_one_query (offline seam test) writes no report.md -> documented no-op.
    assert enforce_render_validity({"status": "success"}, q, run_dir) is None


def test_enforce_noop_on_nonshipping_status(tmp_path):
    run_dir = _write_run(tmp_path, _WRONG_QUESTION_REPORT)
    q = {"slug": "drb_72_ai_labor", "domain": "workforce", "question": _CANONICAL_QUESTION}
    assert enforce_render_validity({"status": "abort_corpus_inadequate"}, q, run_dir) is None


def test_enforce_noop_for_uncontracted_slug(tmp_path):
    run_dir = tmp_path / "clinical" / "drb_90_adas_liability"
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "report.md").write_text(_WRONG_QUESTION_REPORT, encoding="utf-8")
    q = {"slug": "drb_90_adas_liability", "domain": "clinical", "question": "anything"}
    assert enforce_render_validity({"status": "success"}, q, run_dir) is None


def test_enforce_disabled_by_kill_switch(tmp_path, monkeypatch):
    monkeypatch.setenv("PG_RUN_VALIDITY_GATE", "0")
    assert run_validity_gate_enabled() is False
    run_dir = _write_run(tmp_path, _WRONG_QUESTION_REPORT)
    q = {"slug": "drb_72_ai_labor", "domain": "workforce", "question": _CANONICAL_QUESTION}
    assert enforce_render_validity({"status": "success"}, q, run_dir) is None


# --------------------------------------------------------------------------- FIX-1 wiring

def test_scope_flags_are_wired_into_the_slate_and_preflight():
    from scripts.dr_benchmark.run_gate_b import (
        _BENCHMARK_FORCE_ON_FLAGS,
        _BENCHMARK_PREFLIGHT_REQUIRED_FLAGS,
        _FULL_CAPABILITY_BENCHMARK_SLATE,
    )

    scope_flags = (
        "PG_SCOPE_CONSTRAINT_ENFORCE",
        "PG_EXTRACT_SCOPE_CONSTRAINTS",
        "PG_RELEVANCE_PRESERVE_ANCHORS",
        "PG_CORPUS_TIER_DISCLOSURE_MODE",
    )
    for flag in scope_flags:
        assert _FULL_CAPABILITY_BENCHMARK_SLATE.get(flag) == "1", flag
        assert flag in _BENCHMARK_FORCE_ON_FLAGS, flag
        assert flag in _BENCHMARK_PREFLIGHT_REQUIRED_FLAGS, flag


def test_official_question_is_preflight_required():
    from scripts.dr_benchmark.run_gate_b import _BENCHMARK_PREFLIGHT_REQUIRED_FLAGS

    assert "PG_BENCHMARK_OFFICIAL_QUESTION" in _BENCHMARK_PREFLIGHT_REQUIRED_FLAGS


def test_apply_slate_arms_the_four_scope_flags(monkeypatch):
    for flag in (
        "PG_SCOPE_CONSTRAINT_ENFORCE",
        "PG_EXTRACT_SCOPE_CONSTRAINTS",
        "PG_RELEVANCE_PRESERVE_ANCHORS",
        "PG_CORPUS_TIER_DISCLOSURE_MODE",
    ):
        monkeypatch.setenv(flag, "0")  # a stray operator =0 must NOT survive the force-on slate
    from scripts.dr_benchmark.run_gate_b import apply_full_capability_benchmark_slate

    apply_full_capability_benchmark_slate()
    for flag in (
        "PG_SCOPE_CONSTRAINT_ENFORCE",
        "PG_EXTRACT_SCOPE_CONSTRAINTS",
        "PG_RELEVANCE_PRESERVE_ANCHORS",
        "PG_CORPUS_TIER_DISCLOSURE_MODE",
    ):
        assert os.environ[flag] == "1", flag


def test_every_force_flag_is_still_a_slate_key():
    """The invariant the pre-spend assertion relies on must still hold after FIX-1 additions."""
    from scripts.dr_benchmark.run_gate_b import (
        _BENCHMARK_FORCE_EXACT_FLAGS,
        _BENCHMARK_FORCE_ON_FLAGS,
        _FULL_CAPABILITY_BENCHMARK_SLATE,
    )

    missing = sorted(
        (_BENCHMARK_FORCE_ON_FLAGS | _BENCHMARK_FORCE_EXACT_FLAGS)
        - set(_FULL_CAPABILITY_BENCHMARK_SLATE)
    )
    assert not missing, missing
