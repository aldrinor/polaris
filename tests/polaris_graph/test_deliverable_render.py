"""Offline unit battery for the S7 deliverable-aware RENDER leg (master plan WP-3d, Design 3
consumers 3+4 + §1.3 disclosure). PURE, stdlib-only, no live corpus (that is the later VM hamster).

Proves the section's contract on FIXTURES:
  - empty / absent spec => inactive (the caller keeps the byte-identical numeric render);
  - reference-style resolution incl. unknown-style fallback + disclosure;
  - reference-entry formatting NEVER fabricates an author or a year (LAW II);
  - ordering re-positions the extractive wrappers only, summary_first=True == the default order;
  - Methods adherence + RunConfig disclosure blocks render / stay empty correctly.
"""

from __future__ import annotations

from src.polaris_graph.generator import deliverable_render as dr


# ── is_spec_active / OFF-path ─────────────────────────────────────────────────────────────────────
def test_empty_and_absent_spec_is_inactive():
    assert dr.is_spec_active(None) is False
    assert dr.is_spec_active({}) is False
    assert dr.is_spec_active({"source": "regex", "raw_directives": []}) is False
    assert dr.is_spec_active({"reference_style": None, "tone": None}) is False


def test_populated_spec_is_active_including_false_bool():
    assert dr.is_spec_active({"tone": "plain_language"}) is True
    # a deliberately-parsed False bool ("no top summary") is a real ask, not an empty spec.
    assert dr.is_spec_active({"summary_first": False}) is True
    assert dr.is_spec_active({"structure_slots": [{"title": "Risks"}]}) is True


# ── reference-style resolution ──────────────────────────────────────────────────────────────────────
def test_resolve_reference_style():
    assert dr.resolve_reference_style({}) == ("numeric", False)
    assert dr.resolve_reference_style({"reference_style": "numeric"}) == ("numeric", False)
    assert dr.resolve_reference_style({"reference_style": "Harvard"}) == ("harvard", False)
    assert dr.resolve_reference_style({"reference_style": "author-year"}) == ("author_year", False)
    assert dr.resolve_reference_style({"reference_style": "Vancouver"}) == ("vancouver", False)
    # an unknown named style falls back to numeric AND flags a disclosure (never a crash / guess).
    assert dr.resolve_reference_style({"reference_style": "chicago"}) == ("numeric", True)


# ── reference-entry formatting: real metadata only, never fabricated ─────────────────────────────────
def test_reference_entry_keeps_marker_and_tier():
    line = dr.format_reference_body(
        num=7, title="A study of X", locator="http://x", tier="T2", genre_tag="",
        row={"authors": ["Smith", "Jones"]}, year=2021, style="author_year", has_locator=True,
    )
    assert line.startswith("[7] ")
    assert "(tier T2)" in line
    assert "Smith, Jones (2021)." in line
    assert "http://x" in line


def test_reference_entry_no_authors_falls_back_to_title_year():
    line = dr.format_reference_body(
        num=3, title="Guideline update", locator="http://y", tier="T1", genre_tag="",
        row={}, year=2020, style="harvard", has_locator=True,
    )
    assert line == "[3] Guideline update (2020). http://y (tier T1)"


def test_reference_entry_never_fabricates_year_when_absent():
    line = dr.format_reference_body(
        num=5, title="Untitled review", locator="http://z", tier="T4", genre_tag="",
        row={}, year=None, style="apa", has_locator=True,
    )
    # no year captured => no parenthetical year at all; no invented number in the line.
    assert "(20" not in line and "(19" not in line
    assert line == "[5] Untitled review. http://z (tier T4)"


def test_reference_entry_junk_author_is_treated_as_absent():
    line = dr.format_reference_body(
        num=9, title="Report", locator="http://w", tier="T3", genre_tag="",
        row={"author": "Anonymous"}, year=2019, style="author_year", has_locator=True,
    )
    assert "Anonymous" not in line
    assert line == "[9] Report (2019). http://w (tier T3)"


def test_reference_entry_vancouver_numbered_shape_and_gap():
    line = dr.format_reference_body(
        num=2, title="Trial", locator="http://v", tier="T1", genre_tag="",
        row={"authors": ["A", "B", "C", "D"]}, year=2022, style="vancouver", has_locator=True,
    )
    # >3 authors folds to "First et al." (mirrors citation_mapper).
    assert line == "[2] A et al.. Trial. http://v; 2022 (tier T1)"
    gap = dr.format_reference_body(
        num=8, title="Missing", locator="no resolvable URL/DOI locator (disclosed evidence gap)",
        tier="T5", genre_tag="", row={}, year=None, style="vancouver", has_locator=False,
    )
    assert gap.startswith("[8] Missing. no resolvable URL/DOI locator")
    assert "(tier T5)" in gap


def test_reference_entry_preserves_genre_tag():
    line = dr.format_reference_body(
        num=1, title="Paper", locator="http://p", tier="T1",
        genre_tag=" — [peer-reviewed journal article]", row={}, year=2023,
        style="author_year", has_locator=True,
    )
    assert line.endswith("(tier T1) — [peer-reviewed journal article]")


# ── ordering ────────────────────────────────────────────────────────────────────────────────────────
def test_build_report_ordering():
    assert dr.build_report_ordering(None) is None
    assert dr.build_report_ordering({}) is None
    # a spec with no ordering-relevant field yields no ordering (=> default assembly).
    assert dr.build_report_ordering({"tone": "plain_language"}) is None
    o = dr.build_report_ordering({"summary_first": False})
    assert o == {"summary_first": False, "recommendations_last": True, "brief_shape": False}
    m = dr.build_report_ordering({"deliverable_type": "memo"})
    assert m["brief_shape"] is True and m["summary_first"] is True


def test_assemble_with_ordering_default_is_byte_identical():
    title, abstract, body, conclusion = "# T\n", "## Abstract\nA\n", "BODY\n", "## Conclusion\nC\n"
    default = title + abstract + body + conclusion
    assert dr.assemble_with_ordering(title, abstract, body, conclusion, None) == default
    # summary_first True must equal the default order exactly.
    assert dr.assemble_with_ordering(
        title, abstract, body, conclusion, {"summary_first": True}
    ) == default
    # summary_first False moves the abstract to trail the body; conclusion stays last.
    trailed = dr.assemble_with_ordering(
        title, abstract, body, conclusion, {"summary_first": False}
    )
    assert trailed == title + body + abstract + conclusion
    assert trailed.rstrip().endswith("C")


# ── Methods disclosure blocks ────────────────────────────────────────────────────────────────────────
def test_adherence_block_empty_for_no_spec():
    assert dr.render_deliverable_adherence_block(None) == ""
    assert dr.render_deliverable_adherence_block({}) == ""


def test_adherence_block_lists_directives_with_spans_and_status():
    spec = {
        "reference_style": "harvard",
        "summary_first": True,
        "audience": "executive",
        "length_target_words": 2000,
        "structure_slots": [{"title": "Risks"}],
        "raw_directives": [
            {"field": "reference_style", "span": "Harvard references"},
            {"field": "audience", "span": "for my board"},
        ],
    }
    block = dr.render_deliverable_adherence_block(spec, reference_fallback=False)
    assert "### Deliverable requirements" in block
    assert "Reference style: HONORED (harvard" in block
    assert '"Harvard references"' in block  # verbatim trigger span quoted
    assert "Executive summary placement: HONORED (summary leads)" in block
    assert 'Requested section "Risks"' in block
    # audience is NOT a render-controlled field => never asserted HONORED by the render leg.
    assert "Audience: requested (executive)" in block


def test_adherence_block_plain_string_directives_surface_verbatim():
    # Design 3 declares raw_directives as list[str]; the verbatim spans must still surface.
    spec = {"reference_style": "vancouver",
            "raw_directives": ["Vancouver style references", "keep it under 2 pages"]}
    block = dr.render_deliverable_adherence_block(spec)
    assert "Parsed directive spans (verbatim):" in block
    assert '"Vancouver style references"' in block
    assert '"keep it under 2 pages"' in block


def test_adherence_block_reference_fallback_is_partial():
    spec = {"reference_style": "chicago",
            "raw_directives": [{"field": "reference_style", "span": "Chicago style"}]}
    block = dr.render_deliverable_adherence_block(spec, reference_fallback=True)
    assert "PARTIAL" in block and "not a renderable style" in block


def test_run_config_disclosure_lists_non_default_only():
    rc = {"provenance": {
        "query_budget": {"value": 80, "source": "panel", "span": "comprehensive"},
        "serper_k": {"value": 12, "source": "default"},
        "reference_style": {"value": "harvard", "source": "parsed", "span": "Harvard references"},
    }}
    block = dr.render_run_config_disclosure_block(rc)
    assert "### Run configuration" in block
    assert "query_budget = 80 (source: panel; prompt: \"comprehensive\")" in block
    assert "reference_style = harvard (source: parsed" in block
    # a knob left at its default is NOT disclosed.
    assert "serper_k" not in block


def test_run_config_disclosure_empty_cases():
    assert dr.render_run_config_disclosure_block(None) == ""
    assert dr.render_run_config_disclosure_block({}) == ""
    assert dr.render_run_config_disclosure_block(
        {"provenance": {"x": {"value": 1, "source": "default"}}}
    ) == ""
