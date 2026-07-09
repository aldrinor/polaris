"""N3 (I-deepfix-001 wave-2, #1370) — anchor the verified summary table INTO the body
section whose heading NAMES it, instead of the detached generic "## Summary table" heading.

Pure Python: no GPU / LLM / network. Proves:
* PG_SUMMARY_TABLE_ANCHOR_SECTION default OFF => byte-identical legacy output (T1, T3).
* Flag ON => the (heading-less) table renders DIRECTLY under the named body heading, before
  the section's existing prose, with the narrative prose KEPT (no content drop) (T2).
* No "summary table" heading in the body => graceful fallback to the legacy path (T3).
* The heading match is case-insensitive (T4).

Run: PYTHONIOENCODING=utf-8 python -m pytest tests/polaris_graph/test_summary_table_anchor_section.py -q
"""

from __future__ import annotations

from src.polaris_graph.generator.summary_table import (
    GAP_CELL,
    TABLE_MARKER,
    _find_summary_table_heading,
    render_requested_summary_table,
)

_ENV = "PG_SUMMARY_TABLE_ANCHOR_SECTION"

# The prompt's exact header-cue sentence (straight quotes) => 5 requested columns.
RESEARCH_QUESTION = (
    "Please help me complete a research report on Generative AI and the labor market, and at "
    "the end please create a summary table. The table column headers should be "
    '"Research Literature", "Country/Region", "Application Area/Occupation", '
    '"Specific Applications and Impacts", and "Key Risks and Limitations".'
)

BIBLIOGRAPHY = [
    {"evidence_id": "e1", "num": 1, "source_title": "Robots and Jobs", "url": "https://ex.org/a"},
    {"evidence_id": "e2", "num": 2, "source_title": "GPTs are GPTs", "url": "https://ex.org/b"},
]

SECTION_CLAIMS = [
    {
        "evidence_id": "e1",
        "sentence": (
            "One more robot per thousand workers in the United States reduces employment by "
            "0.2 percentage points."
        ),
        "span_verdict": "SUPPORTS",
        "is_verified": True,
    },
    {
        "evidence_id": "e2",
        "sentence": "Studies emphasize job displacement risk for paralegal occupations.",
        "span_verdict": "SUPPORTS",
        "is_verified": True,
    },
]

REPORT_MD = (
    "# Report\n\n"
    "### Industry Application Cases and Risk Summary Table\n\n"
    "Narrative prose sentence.\n\n"
    "### Another Section\n\n"
    "More prose.\n\n"
    "## Bibliography\n\n"
    "[1] x\n"
)

APPENDIX_BOUNDARY = "## Bibliography"


def _render(report_md: str = REPORT_MD):
    return render_requested_summary_table(
        research_question=RESEARCH_QUESTION,
        bibliography=BIBLIOGRAPHY,
        section_claims=SECTION_CLAIMS,
        existing_report_md=report_md,
        appendix_boundary_marker=APPENDIX_BOUNDARY,
    )


def _header_column_count(text: str) -> int:
    """Number of data columns in the GFM header row that starts '| Research Literature |'."""
    line = next(ln for ln in text.splitlines() if ln.startswith("| Research Literature |"))
    # a GFM row "| a | b | c |" has N cells and N+1 pipes -> split on '|' yields N+2 parts.
    return len([c for c in line.split("|")[1:-1]])


# ---------------------------------------------------------------------------
# T1 — flag OFF (unset): legacy detached "## Summary table" path, byte-identical.
# ---------------------------------------------------------------------------
def test_t1_flag_off_legacy_detached_heading(monkeypatch):
    monkeypatch.delenv(_ENV, raising=False)
    result = _render()
    assert result.changed
    assert "## Summary table" in result.text
    # legacy path inserts the table just before the appendix boundary => AFTER "### Another Section"
    assert result.text.index("| Research Literature") > result.text.index("### Another Section")
    # OFF byte-identical: unset == an explicit "0" call.
    monkeypatch.setenv(_ENV, "0")
    result_zero = _render()
    assert result.text == result_zero.text
    # telemetry is additive (not part of the byte-identity contract on .text)
    assert "anchored=False" in result.canary


# ---------------------------------------------------------------------------
# T2 — flag ON: the table anchors DIRECTLY under the named body heading.
# ---------------------------------------------------------------------------
def test_t2_flag_on_anchors_under_named_heading(monkeypatch):
    monkeypatch.setenv(_ENV, "1")
    result = _render()
    # (a) rendered
    assert result.changed
    # (b) heading < table header < the next section
    idx_heading = result.text.index("### Industry Application Cases and Risk Summary Table")
    idx_table_header = result.text.index("| Research Literature |")
    idx_another = result.text.index("### Another Section")
    assert idx_heading < idx_table_header < idx_another
    # (c) no detached generic heading
    assert "## Summary table" not in result.text
    # (d) the section's existing narrative prose is KEPT (no content drop)
    assert "Narrative prose sentence." in result.text
    # (e) exactly one table rendered
    assert result.text.count(TABLE_MARKER) == 1
    # (f) the header row carries exactly the 5 requested columns
    assert _header_column_count(result.text) == 5
    # (g) at least one honest disclosed-gap cell (no whole-table collapse)
    assert GAP_CELL in result.text
    # (h) resume-safe: a second call over the rendered text is an idempotent no-op
    second = render_requested_summary_table(
        research_question=RESEARCH_QUESTION,
        bibliography=BIBLIOGRAPHY,
        section_claims=SECTION_CLAIMS,
        existing_report_md=result.text,
        appendix_boundary_marker=APPENDIX_BOUNDARY,
    )
    assert second.changed is False
    assert second.canary == "already_present"
    # canary carries the anchored flag
    assert "anchored=True" in result.canary


# ---------------------------------------------------------------------------
# T3 — flag ON but NO "summary table" heading in the body: legacy fallback, byte-identical.
# ---------------------------------------------------------------------------
def test_t3_flag_on_no_heading_falls_back(monkeypatch):
    report_no_heading = (
        "# Report\n\n"
        "### Narrative Findings\n\n"
        "Some prose without a table heading.\n\n"
        "### Another Section\n\n"
        "More prose.\n\n"
        "## Bibliography\n\n"
        "[1] x\n"
    )
    monkeypatch.setenv(_ENV, "1")
    on_result = _render(report_no_heading)
    monkeypatch.delenv(_ENV, raising=False)
    off_result = _render(report_no_heading)
    # no anchor found => byte-identical to the OFF/legacy output
    assert on_result.text == off_result.text
    assert "## Summary table" in on_result.text


# ---------------------------------------------------------------------------
# T4 — the anchor heading match is case-insensitive.
# ---------------------------------------------------------------------------
def test_t4_anchor_is_case_insensitive(monkeypatch):
    report_lower = (
        "# Report\n\n"
        "### industry application cases and risk SUMMARY TABLE\n\n"
        "Narrative prose sentence.\n\n"
        "## Bibliography\n\n"
        "[1] x\n"
    )
    monkeypatch.setenv(_ENV, "1")
    result = _render(report_lower)
    assert result.changed
    idx_heading = result.text.index("### industry application cases and risk SUMMARY TABLE")
    idx_table_header = result.text.index("| Research Literature |")
    assert idx_heading < idx_table_header
    assert "## Summary table" not in result.text


# ---------------------------------------------------------------------------
# Unit: _find_summary_table_heading offset semantics.
# ---------------------------------------------------------------------------
def test_find_heading_returns_position_past_heading_and_blank():
    pos = _find_summary_table_heading(REPORT_MD, APPENDIX_BOUNDARY)
    assert pos is not None
    # the insertion point is exactly the start of the section's prose
    assert REPORT_MD[pos:].startswith("Narrative prose sentence.")


def test_find_heading_none_when_absent():
    body = "# Report\n\n### Nothing Here\n\nprose\n\n## Bibliography\n\n[1] x\n"
    assert _find_summary_table_heading(body, APPENDIX_BOUNDARY) is None


def test_find_heading_ignores_heading_inside_appendix():
    # a "summary table" heading that lives AFTER the appendix boundary must not anchor
    body = (
        "# Report\n\n### Plain Section\n\nprose\n\n"
        "## Bibliography\n\n[1] x\n\n"
        "### Appendix Summary Table\n\nmachinery\n"
    )
    assert _find_summary_table_heading(body, APPENDIX_BOUNDARY) is None
