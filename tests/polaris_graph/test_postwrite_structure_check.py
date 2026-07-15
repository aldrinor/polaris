"""feat/intake-contract — unit tests for the POST-WRITE structure CHECKER (Part 3).

All PURE: no api/live markers, no LLM/network, no mocking. The checker is a pure
function and the flag gate is a plain env read. It never verifies faithfulness and
never enforces anything (``enforced`` is always False).
"""
from __future__ import annotations

import copy

from src.polaris_graph.generator.postwrite_structure_check import (
    build_floor_contract,
    check_report_against_contract,
    postwrite_check_enabled,
)

_REPORT = (
    "# Remote Work Report\n\n"
    "Intro prose here with a marker [1] and another [2].\n\n"
    "## Safety\n\nBody about safety [1].\n\n"
    "## Cost\n\nBody about cost [2].\n\n"
    "## References\n[1] a — http://x (tier A)\n[2] b — http://y (tier C)\n"
)


def test_missing_required_section_flagged() -> None:
    contract = {"required_sections": [{"entities": ["Governance"], "text": "a section on Governance"}]}
    out = check_report_against_contract(_REPORT, contract, [], 500)
    assert "Governance" in " ".join(out["sections"]["missing"])
    assert out["sections"]["status"] in ("PARTIAL", "MISSING")
    assert out["enforced"] is False


def test_present_section_satisfied() -> None:
    contract = {"required_sections": [{"entities": ["Safety"], "text": "cover Safety"}]}
    out = check_report_against_contract(_REPORT, contract, [], 500)
    assert "cover Safety" in out["sections"]["satisfied"] or "Safety" in " ".join(out["sections"]["satisfied"])
    assert out["sections"]["status"] == "PASS"


def test_length_under_band() -> None:
    out = check_report_against_contract(_REPORT, {"length": {"min": 1000, "max": 1500}}, [], 400)
    assert out["length"]["status"] == "UNDER"


def test_length_pass() -> None:
    out = check_report_against_contract(_REPORT, {"length": {"min": 100, "max": 900}}, [], 400)
    assert out["length"]["status"] == "PASS"


def test_length_unspecified_when_no_directive() -> None:
    out = check_report_against_contract(_REPORT, {}, [], 400)
    assert out["length"]["status"] == "UNSPECIFIED"


def test_citation_style_counts_markers_and_references() -> None:
    out = check_report_against_contract(_REPORT, {"citation_style": "numeric"}, [], 500)
    assert out["citation_style"]["observed_markers"] >= 2
    assert out["citation_style"]["has_references_section"] is True
    assert out["citation_style"]["status"] == "PASS"


def test_source_rule_journal_only_is_noted_not_enforced() -> None:
    biblio = [{"num": 1, "tier": "A"}, {"num": 2, "tier": "C"}]
    out = check_report_against_contract(_REPORT, {"journal_only": True}, biblio, 500)
    assert out["source_rules"]["status"] == "NOTED_NOT_ENFORCED"
    assert out["source_rules"]["rule"] == "journal_only"
    assert out["enforced"] is False


def test_date_window_is_noted_not_enforced() -> None:
    out = check_report_against_contract(_REPORT, {"date_window": {"end_year": 2020}}, [], 500)
    assert out["date_window"]["status"] == "NOTED_NOT_ENFORCED"


def test_empty_contract_is_na() -> None:
    out = check_report_against_contract(_REPORT, {}, [], 500)
    assert out["sections"]["status"] == "N/A"
    assert out["length"]["status"] == "UNSPECIFIED"
    assert out["enforced"] is False


def test_checker_does_not_mutate_inputs() -> None:
    report = str(_REPORT)
    contract = {"required_sections": [{"entities": ["Safety"]}], "journal_only": True}
    biblio = [{"num": 1, "tier": "A"}]
    r0, c0, b0 = copy.deepcopy(report), copy.deepcopy(contract), copy.deepcopy(biblio)
    check_report_against_contract(report, contract, biblio, 500)
    assert report == r0 and contract == c0 and biblio == b0


def test_only_level_2_headings_parsed() -> None:
    # The '# Remote Work Report' title must NOT appear in present_headings.
    out = check_report_against_contract(_REPORT, {"required_sections": [{"entities": ["Cost"]}]}, [], 500)
    assert "Remote Work Report" not in out["sections"]["present_headings"]
    assert "Safety" in out["sections"]["present_headings"]


def test_flag_default_off(monkeypatch) -> None:
    monkeypatch.delenv("PG_POSTWRITE_STRUCTURE_CHECK", raising=False)
    assert postwrite_check_enabled() is False
    monkeypatch.setenv("PG_POSTWRITE_STRUCTURE_CHECK", "1")
    assert postwrite_check_enabled() is True


def test_build_floor_contract_from_regex() -> None:
    rq = ("Compare A versus B. Only cite peer-reviewed journals. "
          "Write about 1200 words.")
    contract = build_floor_contract(rq)
    assert contract["contract_source"] == "floor_regex"
    assert contract.get("journal_only") is True
    assert contract.get("length", {}).get("min") and contract["length"]["max"]
    assert contract.get("instruction_slots")  # the A vs B comparison slot
