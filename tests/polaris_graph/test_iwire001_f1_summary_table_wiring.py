"""I-wire-001 F1 — missing-summary-table WIRING + dangling-citation prune (behavioral).

FAIL-LOUD: each test asserts a REAL EFFECT on rendered output (a GFM table header the
run-validity gate matches EXACTLY; a body-cited bibliography entry that stays listed), never
a flag read. Offline, $0. The faithfulness engine (strict_verify / NLI / 4-role D8 /
provenance) is untouched — this is presentation wiring only.

The three tests map to Fable's F1 acceptance spec:
  (a) the run-bound PARAPHRASE question + the drb_72 output CONTRACT render a 5-column GFM
      table whose header row run_validity_gate._table_header_rows matches EXACTLY against the
      YAML columns (the contract-scaffold validity gate would now PASS);
  (b) the GOLD-prompt phrasing (quoted headers) still parses to the same 5 headers (no
      regression);
  (c) the source-necessity prune never MOVES a bibliography entry whose [N] appears in the
      rendered body (no dangling citation), while it still quarantines a genuinely un-cited
      zero-support entry.
"""
from __future__ import annotations

import importlib

import pytest

from src.polaris_graph.generator.summary_table import (
    parse_requested_headers,
    render_requested_summary_table,
)

rvg = importlib.import_module("scripts.dr_benchmark.run_validity_gate")
sn = importlib.import_module("src.polaris_graph.synthesis.source_necessity")

# The run-bound PARAPHRASE the sweep actually launched for drb_72 (colon-list, NO quotes) —
# the exact wording Fable's spec names. It must recover the same 5 headers as the gold prompt.
PARAPHRASE_QUESTION = (
    "I am researching the impact of Generative AI on the future labor market, please help me "
    "complete a research report discussing the positive impacts, negative impacts, challenges, "
    "and opportunities as separate sections. End with a summary table detailing the specific "
    "application cases and impacts with columns: Research Literature, Country/Region, "
    "Application Area/Occupation, Specific Applications and Impacts, and Key Risks and Limitations."
)

# The GOLD-file phrasing (quoted headers, "The table column headers should be ...").
GOLD_QUESTION = (
    "I am researching the impact of Generative AI on the future labor market. At the end of the "
    "report, please create a summary table. The table column headers should be “Research "
    "Literature”, “Country/Region”, “Application Area/Occupation”, "
    "“Specific Applications and Impacts”, and “Key Risks and Limitations”."
)

FIVE_HEADERS = [
    "Research Literature",
    "Country/Region",
    "Application Area/Occupation",
    "Specific Applications and Impacts",
    "Key Risks and Limitations",
]


def _member(eid, quote, verdict="SUPPORTS"):
    return {"evidence_id": eid, "span_verdict": verdict, "direct_quote": quote}


# A compact 3-source bibliography, each carrying a verified basket + a clean section claim.
BIBLIOGRAPHY = [
    {
        "num": 1,
        "evidence_id": "autor_jobs",
        "source_title": "Why Are There Still So Many Jobs?",
        "authors": ["Autor D"],
        "tier": "T1",
        "baskets": [{
            "claim_cluster_id": "cc_autor",
            "verified_support_origin_count": 1,
            "claim_text": "Automation historically did not eliminate most jobs.",
            "supporting_members": [_member(
                "autor_jobs",
                "Automation has not wiped out a majority of jobs over the decades in the "
                "United States labor market.",
            )],
        }],
    },
    {
        "num": 4,
        "evidence_id": "acemoglu_robots",
        "source_title": "Robots and Jobs: Evidence from US Labor Markets",
        "authors": ["Acemoglu D", "Restrepo P"],
        "tier": "T1",
        "baskets": [{
            "claim_cluster_id": "cc_acemoglu",
            "verified_support_origin_count": 1,
            "claim_text": "Robots reduce employment and wages.",
            "supporting_members": [_member(
                "acemoglu_robots",
                "One more robot per thousand workers reduces the employment-to-population "
                "ratio by 0.2 percentage points across US labor markets, a job displacement risk.",
            )],
        }],
    },
    {
        "num": 6,
        "evidence_id": "brynjolfsson_genai",
        "source_title": "Generative AI at Work",
        "authors": ["Brynjolfsson E", "Li D", "Raymond L"],
        "tier": "T1",
        "baskets": [{
            "claim_cluster_id": "cc_bryn",
            "verified_support_origin_count": 1,
            "claim_text": "Generative AI raises customer-support productivity.",
            "supporting_members": [_member(
                "brynjolfsson_genai",
                "Access to a generative AI assistant increases customer support worker "
                "productivity by 15%.",
            )],
        }],
    },
]

SECTION_CLAIMS = [
    {
        "evidence_id": "autor_jobs",
        "sentence": (
            "Automation has not wiped out a majority of jobs over the decades in the United "
            "States labor market [#ev:autor_jobs:0-120]."
        ),
        "span_verdict": "SUPPORTS",
        "is_verified": True,
    },
    {
        "evidence_id": "acemoglu_robots",
        "sentence": (
            "One more robot per thousand workers reduces the employment-to-population ratio by "
            "0.2 percentage points across US labor markets [#ev:acemoglu_robots:0-160]."
        ),
        "span_verdict": "SUPPORTS",
        "is_verified": True,
    },
    {
        "evidence_id": "brynjolfsson_genai",
        "sentence": (
            "Access to a generative AI assistant increases customer support worker productivity "
            "by 15% [#ev:brynjolfsson_genai:0-120]."
        ),
        "span_verdict": "SUPPORTS",
        "is_verified": True,
    },
]

# A minimal report body carrying the 4 contract sections + an H1 that reflects the bound
# question, so the FULL run-validity gate (question-fidelity + contract-scaffold) can be run.
REPORT_BODY = (
    "# Research report: impact of Generative AI on the future labor market\n\n"
    "## Positive Impacts\n\nGenerative AI raises productivity [6].\n\n"
    "## Negative Impacts\n\nRobots reduce employment [4].\n\n"
    "## Challenges\n\nAutomation reshapes work [1].\n\n"
    "## Opportunities\n\nReskilling pathways expand.\n\n"
    "## Bibliography\n\n"
    "[1] Autor D — Why Are There Still So Many Jobs? — https://ex.org/1 (tier T1)\n"
    "[4] Acemoglu D — Robots and Jobs — https://ex.org/4 (tier T1)\n"
    "[6] Brynjolfsson E — Generative AI at Work — https://ex.org/6 (tier T1)\n"
)


# ---------------------------------------------------------------------------
# (a) run-bound paraphrase + contract -> a table the validity gate matches EXACTLY
# ---------------------------------------------------------------------------
def test_a_paraphrase_plus_contract_renders_gate_matching_table():
    contract = rvg.load_task_output_contract("drb_72_ai_labor")
    assert contract is not None, "drb_72 contract must load"
    columns = contract["required_table"]["columns"]

    result = render_requested_summary_table(
        research_question=PARAPHRASE_QUESTION,
        bibliography=BIBLIOGRAPHY,
        section_claims=SECTION_CLAIMS,
        existing_report_md=REPORT_BODY,
        appendix_boundary_marker="## Bibliography",
        contract_headers=columns,
    )
    assert result.changed, "the table must render into the report body"
    assert result.headers == columns, "the contract columns are authoritative"
    assert result.rows == 3, "one row per verified source"

    rendered = result.text

    # A GFM header row EXACTLY equal (element-by-element, after _norm) to the YAML columns —
    # this is the precise check run_validity_gate.check_contract_scaffold enforces.
    required_n = [rvg._norm(c) for c in columns]
    header_rows = rvg._table_header_rows(rendered)
    assert any(row == required_n for row in header_rows), (
        f"no GFM header row matched {required_n!r}; found {header_rows!r}"
    )

    # The FULL run-validity gate (question-fidelity + contract-scaffold) now PASSES.
    violations = rvg.evaluate_report_validity(rendered, PARAPHRASE_QUESTION, contract)
    assert violations == [], f"expected zero validity violations, got {violations!r}"


def test_a_paraphrase_parses_to_five_headers_without_contract():
    """The belt-and-suspenders parser recovers the 5 headers from the UNQUOTED colon-list
    paraphrase even with NO contract supplied (the contract path is primary; this is the
    fallback the launch-time assert also relies on)."""
    assert parse_requested_headers(PARAPHRASE_QUESTION) == FIVE_HEADERS


# ---------------------------------------------------------------------------
# (b) gold-prompt (quoted) phrasing still parses to the same 5 headers (no regression)
# ---------------------------------------------------------------------------
def test_b_gold_quoted_phrasing_still_parses_five_headers():
    assert parse_requested_headers(GOLD_QUESTION) == FIVE_HEADERS


def test_b_no_cue_and_straight_quotes_unchanged():
    # broadened cue must not false-positive on a plain narrative prompt
    assert parse_requested_headers("Write a narrative report. No table is required.") == []
    # straight-quoted header lists still work
    assert parse_requested_headers(
        'Build a table. The columns should be "A name", "B place", "C thing".'
    ) == ["A name", "B place", "C thing"]


# ---------------------------------------------------------------------------
# (c) source-necessity prune never moves a BODY-CITED entry (no dangling citation)
# ---------------------------------------------------------------------------
_BIBLIO_BLOCK = (
    "\n\n## Bibliography\n"
    "[1] Load-bearing study — https://ex.org/a (tier T1)\n"
    "[85] Table-only cited source — https://ex.org/b (tier T5)\n"
)


def test_c_body_cited_zero_support_entry_is_never_quarantined():
    support_by_num = {1: ["c1"], 85: []}  # 85 is cited but zero factual support
    cited = [1, 85]
    necessity = sn.compute_source_necessity(support_by_num, cited)

    # [85] appears in the rendered body (e.g. only in the summary table) -> protected.
    zero = sn.zero_support_bib_nums(support_by_num, cited, body_cited_nums={85})
    assert zero == set(), "a body-cited number must never be a quarantine target"

    out = sn.retype_bibliography_by_source_necessity(
        _BIBLIO_BLOCK, {85}, necessity, body_cited_nums={85}
    )
    # [85] must NOT be under the source-necessity audit ledger (its [N] would then dangle).
    head, _sep, ledger = out.partition(sn._LEDGER_HEADER)
    assert "[85]" not in ledger, "a body-cited entry must not move to the audit ledger"
    assert "[85] Table-only cited source" in head, "the body-cited entry must stay listed"


def test_c_contrast_without_guard_the_entry_would_dangle():
    """Proves the guard CHANGES behavior: without body_cited_nums the zero-support cited entry
    is moved to the ledger (the drb_72 dangling-citation defect)."""
    support_by_num = {1: ["c1"], 85: []}
    necessity = sn.compute_source_necessity(support_by_num, [1, 85])
    out = sn.retype_bibliography_by_source_necessity(_BIBLIO_BLOCK, {85}, necessity)
    _head, _sep, ledger = out.partition(sn._LEDGER_HEADER)
    assert "[85]" in ledger, "without the F1 guard the entry moves to the ledger (the defect)"


def test_c_guard_still_quarantines_a_genuinely_uncited_zero_support_entry():
    """The guard is scoped to BODY-CITED numbers only: a zero-support number that is NOT in the
    body-cited set is still quarantined, so the source-necessity signal is preserved."""
    support_by_num = {1: ["c1"], 85: []}
    necessity = sn.compute_source_necessity(support_by_num, [1, 85])
    # 85 is a quarantine target and is NOT protected (body_cited_nums excludes it).
    zero = sn.zero_support_bib_nums(support_by_num, [1, 85], body_cited_nums={1})
    assert zero == {85}
    out = sn.retype_bibliography_by_source_necessity(
        _BIBLIO_BLOCK, zero, necessity, body_cited_nums={1}
    )
    _head, _sep, ledger = out.partition(sn._LEDGER_HEADER)
    assert "[85]" in ledger


# ---------------------------------------------------------------------------
# F1 part 3 — launch-time contract-table assert (pre-spend, fail-loud)
# ---------------------------------------------------------------------------
def test_launch_assert_passes_for_drb72_contract():
    rgb = importlib.import_module("scripts.dr_benchmark.run_gate_b")
    # drb_72 contract supplies the 5 columns -> the assert passes silently.
    rgb.assert_table_contract_columns_available(
        {"slug": "drb_72_ai_labor", "question": PARAPHRASE_QUESTION}
    )


def test_launch_assert_raises_when_table_required_but_columns_unresolvable(tmp_path, monkeypatch):
    rgb = importlib.import_module("scripts.dr_benchmark.run_gate_b")
    # A synthetic contract that DECLARES a required table but supplies < 2 columns, for a
    # question that names no headers -> the builder would render no table -> fail loud.
    bad = tmp_path / "contracts.yaml"
    bad.write_text(
        "broken_slug:\n  required_table:\n    columns: []\n", encoding="utf-8"
    )
    monkeypatch.setenv("PG_TASK_OUTPUT_CONTRACT_PATH", str(bad))
    with pytest.raises(RuntimeError, match="TABLE-CONTRACT-UNRESOLVED"):
        rgb.assert_table_contract_columns_available(
            {"slug": "broken_slug", "question": "Write a narrative report. No table."}
        )


def test_launch_assert_noop_for_slug_without_contract(tmp_path, monkeypatch):
    rgb = importlib.import_module("scripts.dr_benchmark.run_gate_b")
    empty = tmp_path / "contracts.yaml"
    empty.write_text("some_other_slug:\n  required_sections: []\n", encoding="utf-8")
    monkeypatch.setenv("PG_TASK_OUTPUT_CONTRACT_PATH", str(empty))
    # No entry for this slug -> documented no-op (no raise).
    rgb.assert_table_contract_columns_available(
        {"slug": "unlisted_slug", "question": "anything"}
    )
