"""Offline RED->GREEN tests for the verified-only summary-table renderer
(I-deepfix-001 P7, #1344).

Fixtures are grounded in the real drb_72 run
(outputs/boxc_full/workforce/drb_72_ai_labor/): the prompt text, the numbered
bibliography rows (num / evidence_id / source_title / authors / tier / verified
baskets with per-member ``evidence_id`` / ``span_verdict`` / ``direct_quote``, exactly
the shape ``provenance_generator._basket_for_biblio`` projects) and the clean,
span-verified sentences from claim_disclosure.json.

The pipeline currently renders NO table (grep '^|' report.md = 0 rows), which fails
the DRB-II presentation rubric. These tests prove the renderer turns already-verified
findings into a 5-column GFM table WITHOUT fabricating any cell:

* attribute cells (geography / domain / risk) are WHOLE-WORD matches of that source's own
  verified spans — "mining" is never surfaced from "examining"/"determining"/"undermining"
  and "India" is never surfaced from "Indiana" (iter-2 Fable blocker);
* the no-clean-sentence fallback renders THIS source's OWN verified basket-member VERBATIM
  ``direct_quote`` (span_verdict==SUPPORTS), never the basket's synthesized/other-source
  ``claim_text`` (iter-2 Codex blocker).
"""

from __future__ import annotations

import re
import types

import pytest

from src.polaris_graph.generator.summary_table import (
    GAP_CELL,
    ROLE_CLAIM,
    ROLE_DOMAIN,
    ROLE_GEOGRAPHY,
    ROLE_LITERATURE,
    ROLE_RISK,
    TABLE_MARKER,
    assign_header_roles,
    build_summary_table_markdown,
    extract_section_claims,
    parse_requested_headers,
    render_requested_summary_table,
)

# --- the REAL drb_72 prompt (header list verbatim) --------------------------
DRB72_QUESTION = (
    "I am researching the impact of Generative AI on the future labor market, please "
    "help me complete a research report. ... At the end of the report, please create a "
    "summary table based on the information you have gathered, detailing specific "
    "application cases of Generative AI in particular industries or occupations, the "
    "main impacts brought about, and key risk points emphasized by researchers, as "
    "mentioned in different studies. The table column headers should be “Research "
    "Literature”, “Country/Region”, “Application Area/Occupation”, “Specific "
    "Applications and Impacts”, and “Key Risks and Limitations”."
)

DRB72_HEADERS = [
    "Research Literature",
    "Country/Region",
    "Application Area/Occupation",
    "Specific Applications and Impacts",
    "Key Risks and Limitations",
]


def _member(eid, quote, verdict="SUPPORTS"):
    """A basket ``supporting_members`` entry shaped like the production
    ``provenance_generator._basket_for_biblio`` projection."""
    return {"evidence_id": eid, "span_verdict": verdict, "direct_quote": quote}


# --- real bibliography rows (numbered, each with a verified basket) -----------
# Each basket carries its own ``supporting_members``. The basket-level ``claim_text`` is
# the SYNTHESIZED/consolidated cluster claim (may borrow a different source's wording); it
# must NEVER be rendered — the fallback uses the row's OWN member's verbatim direct_quote.
BIBLIOGRAPHY = [
    {
        "num": 1,
        "evidence_id": "autor_why_still_jobs",
        "source_title": "Why Are There Still So Many Jobs? The History and Future of Workplace Automation",
        "authors": ["Autor D"],
        "tier": "T1",
        "baskets": [{
            "claim_cluster_id": "cc_autor",
            "verified_support_origin_count": 1,
            "claim_text": "Automation has historically not eliminated the majority of jobs.",
            "supporting_members": [_member(
                "autor_why_still_jobs",
                "In this essay, I begin by identifying the reasons that automation has not "
                "wiped out a majority of jobs over the decades and centuries.",
            )],
        }],
    },
    {
        "num": 4,
        "evidence_id": "acemoglu_restrepo_robots_jobs",
        "source_title": "Robots and Jobs: Evidence from US Labor Markets",
        "authors": ["Acemoglu D", "Restrepo P"],
        "tier": "T1",
        "baskets": [{
            "claim_cluster_id": "cc_acemoglu",
            "verified_support_origin_count": 1,
            "claim_text": "Robots reduce employment and wages.",
            "supporting_members": [_member(
                "acemoglu_restrepo_robots_jobs",
                "We estimate that one more robot per thousand workers reduces the "
                "employment-to-population ratio by 0.2 percentage points and wages by 0.42% "
                "across US labor markets.",
            )],
        }],
    },
    {
        "num": 6,
        "evidence_id": "brynjolfsson_genai_at_work",
        "source_title": "Generative AI at Work",
        "authors": ["Brynjolfsson E", "Li D", "Raymond L"],
        "tier": "T1",
        "baskets": [{
            "claim_cluster_id": "cc_bryn",
            "verified_support_origin_count": 1,
            # Synthesized cluster claim (must NOT be the rendered fallback text).
            "claim_text": "Generative AI raises customer-support productivity.",
            "supporting_members": [_member(
                "brynjolfsson_genai_at_work",
                "We study the staggered introduction of a generative AI-based conversational "
                "assistant using data from 5,172 customer-support agents. Access to AI "
                "assistance increases worker productivity by 15%.",
            )],
        }],
    },
    # A cited source whose OWN member is NOT SUPPORTS and has no section claim -> no row
    # (don't invent; the SUPPORTS gate on the row's own member fails closed).
    {
        "num": 99,
        "evidence_id": "uncited_no_verified",
        "source_title": "A source with no verified claim",
        "authors": ["Nobody N"],
        "tier": "T7",
        "baskets": [{
            "claim_cluster_id": "cc_uncited",
            "verified_support_origin_count": 0,
            "claim_text": "unverified",
            "supporting_members": [_member(
                "uncited_no_verified", "An unverified context span.", verdict="UNSUPPORTED"
            )],
        }],
    },
]

# --- real clean, span-verified sentences (from claim_disclosure.json) --------
SECTION_CLAIMS = [
    {
        "evidence_id": "autor_why_still_jobs",
        "sentence": (
            "Polarization evidence: one noticeable change has been a “polarization” of the "
            "labor market, in which wage gains went disproportionately to those at the top "
            "and at the bottom of the income and skill distribution, not to those in the "
            "middle [#ev:autor_why_still_jobs:200-1000]."
        ),
        "span_verdict": "SUPPORTS",
        "is_verified": True,
    },
    {
        "evidence_id": "acemoglu_restrepo_robots_jobs",
        "sentence": (
            "The study examined US labor markets, using an identification strategy based on "
            "variation in exposure to robots defined from industry-level advances in robotics "
            "and local industry employment [#ev:acemoglu_restrepo_robots_jobs:0-688]."
        ),
        "span_verdict": "SUPPORTS",
        "is_verified": True,
    },
    {
        "evidence_id": "acemoglu_restrepo_robots_jobs",
        "sentence": (
            "One more robot per thousand workers reduces the employment-to-population ratio by "
            "0.2 percentage points and wages by 0.42% [#ev:acemoglu_restrepo_robots_jobs:0-688]."
        ),
        "span_verdict": "SUPPORTS",
        "is_verified": True,
    },
    {
        "evidence_id": "brynjolfsson_genai_at_work",
        "sentence": (
            "Design: the staggered introduction of a generative AI-based conversational "
            "assistant using data from 5,172 customer-support agents "
            "[#ev:brynjolfsson_genai_at_work:0-800]."
        ),
        "span_verdict": "SUPPORTS",
        "is_verified": True,
    },
    {
        "evidence_id": "brynjolfsson_genai_at_work",
        "sentence": (
            "Access to AI assistance increases worker productivity, as measured by issues "
            "resolved per hour, by 15% on average [#ev:brynjolfsson_genai_at_work:0-800]."
        ),
        "span_verdict": "SUPPORTS",
        "is_verified": True,
    },
    # An UNverified sentence that must never enter the table.
    {
        "evidence_id": "acemoglu_restrepo_robots_jobs",
        "sentence": "A refuted fabrication [#ev:acemoglu_restrepo_robots_jobs:0-1].",
        "span_verdict": "REFUTES",
        "is_verified": False,
    },
]

APPENDIX_BOUNDARY = (
    "## Appendix: audit, disclosure, and weighting (not scored as report claims)"
)

# A trimmed pre-fix report body (NO table anywhere) + the audit-machinery appendix.
RED_REPORT = (
    "# Research report: impact of Generative AI on the future labor market\n\n"
    "## Abstract\n\nOne more robot per thousand workers reduces the employment-to-"
    "population ratio by 0.2 percentage points and wages by 0.42%.[4]\n\n"
    "## Key Findings\n\n- **Empirical Displacement.** ... [4]\n\n"
    "## Methods\nPre-registered protocol.json.\n\n"
    "## References\n\n1. Autor D. Why Are There Still So Many Jobs?\n\n"
    + APPENDIX_BOUNDARY
    + "\n\n_reliability machinery counts here._\n"
)


def _render():
    return render_requested_summary_table(
        research_question=DRB72_QUESTION,
        bibliography=BIBLIOGRAPHY,
        section_claims=SECTION_CLAIMS,
        existing_report_md=RED_REPORT,
        appendix_boundary_marker=APPENDIX_BOUNDARY,
    )


# ---------------------------------------------------------------------------
# Header parsing / role assignment
# ---------------------------------------------------------------------------
def test_parse_requested_headers_drb72_exact():
    assert parse_requested_headers(DRB72_QUESTION) == DRB72_HEADERS


def test_parse_requested_headers_straight_quotes():
    q = 'Please build a table. The columns should be "A name", "B place", "C thing".'
    assert parse_requested_headers(q) == ["A name", "B place", "C thing"]


def test_parse_no_headers_when_no_cue():
    q = "Write a narrative report on the labor market. No table is required."
    assert parse_requested_headers(q) == []


def test_assign_roles_maps_drb72_headers():
    roles = assign_header_roles(DRB72_HEADERS)
    assert roles == [ROLE_LITERATURE, ROLE_GEOGRAPHY, ROLE_DOMAIN, ROLE_CLAIM, ROLE_RISK]
    # Exactly one claim column.
    assert roles.count(ROLE_CLAIM) == 1


def test_assign_roles_promotes_claim_when_absent():
    roles = assign_header_roles(["Study", "Country", "Notes"])
    assert roles.count(ROLE_CLAIM) == 1  # last non-literature column promoted


# ---------------------------------------------------------------------------
# Verified-claim extraction from SentenceVerification-shaped objects
# ---------------------------------------------------------------------------
def _sv(sentence, eid, *, is_verified=True, verdict="SUPPORTS"):
    tok = types.SimpleNamespace(evidence_id=eid, start=0, end=10)
    return types.SimpleNamespace(
        sentence=sentence, tokens=[tok], is_verified=is_verified, span_verdict=verdict
    )


def test_extract_section_claims_reads_first_token_eid():
    sr = types.SimpleNamespace(
        dropped_due_to_failure=False,
        kept_sentences_pre_resolve=[
            _sv("A verified claim about robots.", "acemoglu_restrepo_robots_jobs"),
            _sv("", "brynjolfsson_genai_at_work"),  # empty sentence -> skipped
        ],
    )
    out = extract_section_claims([sr])
    assert len(out) == 1
    assert out[0]["evidence_id"] == "acemoglu_restrepo_robots_jobs"
    assert out[0]["is_verified"] is True


def test_extract_section_claims_skips_dropped_sections():
    sr = types.SimpleNamespace(
        dropped_due_to_failure=True,
        kept_sentences_pre_resolve=[_sv("dropped.", "x")],
    )
    assert extract_section_claims([sr]) == []


# ---------------------------------------------------------------------------
# RED -> GREEN
# ---------------------------------------------------------------------------
def test_red_baseline_report_has_no_table():
    # RED: the pre-fix report renders zero GFM table rows.
    table_rows = [ln for ln in RED_REPORT.splitlines() if ln.lstrip().startswith("|")]
    assert table_rows == []


def test_green_renders_five_column_table():
    res = _render()
    assert res.changed is True
    assert res.rows == 3  # nums 1, 4, 6 have verified claims; 99 does not
    text = res.text
    assert "## Summary table" in text
    # Header row + separator row + 3 data rows.
    table_rows = [ln for ln in text.splitlines() if ln.lstrip().startswith("|")]
    assert len(table_rows) == 5
    header_row = table_rows[0]
    for h in DRB72_HEADERS:
        assert h in header_row
    # GFM separator row present with the right column count.
    assert set(table_rows[1].replace("|", "").replace(" ", "")) <= set("-:")
    assert table_rows[1].count("|") == table_rows[0].count("|")
    # Every data row has exactly 5 columns (6 pipes for a leading+trailing bar).
    for row in table_rows[2:]:
        assert row.count("|") == header_row.count("|") == 6


def test_table_inserted_before_audit_appendix():
    res = _render()
    assert res.text.index("## Summary table") < res.text.index(APPENDIX_BOUNDARY)
    # The audit machinery is still present and after the table.
    assert APPENDIX_BOUNDARY in res.text


# ---------------------------------------------------------------------------
# Faithfulness: every cell traceable, no fabrication, honest gaps
# ---------------------------------------------------------------------------
def _data_rows(text):
    rows = [ln for ln in text.splitlines() if ln.lstrip().startswith("|")]
    return rows[2:]  # skip header + separator


def _cells(row):
    return [c.strip() for c in row.strip().strip("|").split("|")]


def _num_of(row):
    return int(_cells(row)[3].rsplit("[", 1)[1].rstrip("]"))


def test_claim_cells_are_cited_to_a_real_bibliography_number():
    res = _render()
    valid_nums = {str(b["num"]) for b in BIBLIOGRAPHY}
    for row in _data_rows(res.text):
        claim_cell = _cells(row)[3]  # ROLE_CLAIM column index for drb_72 headers
        assert claim_cell.endswith("]")
        num = claim_cell.rsplit("[", 1)[1].rstrip("]")
        assert num in valid_nums


def test_claim_text_is_verbatim_from_a_verified_span():
    """No invented claim text: each claim cell's prose (minus ellipsis + citation) is a
    substring of one of that source's VERIFIED sentences."""
    res = _render()
    # Map num -> cleaned verified sentences.
    num_by_eid = {b["evidence_id"]: b["num"] for b in BIBLIOGRAPHY}
    verified_by_num: dict[int, list[str]] = {}
    for c in SECTION_CLAIMS:
        if not c["is_verified"]:
            continue
        n = num_by_eid.get(c["evidence_id"])
        clean = re.sub(r"\[#ev:[^\]]*\]", "", c["sentence"])
        clean = re.sub(r"\s+", " ", clean).strip()
        verified_by_num.setdefault(n, []).append(clean)
    for row in _data_rows(res.text):
        cells = _cells(row)
        claim_cell = cells[3]
        num = int(claim_cell.rsplit("[", 1)[1].rstrip("]"))
        prose = claim_cell.rsplit("[", 1)[0].strip().rstrip("…").strip()
        assert any(prose in s for s in verified_by_num[num]), (num, prose)


# ---------------------------------------------------------------------------
# INDEPENDENT attribute-cell traceability (replaces the prior CIRCULAR test that
# asserted a cell against the module's OWN matcher output). Here the whole-word
# grounding invariant is re-derived from the curated vocab CONSTANTS with the test's
# own regex, over each row's OWN verified span text (kept-sentences + its own SUPPORTS
# member direct_quotes) — never a call to _match_geography / _match_terms_ci.
# ---------------------------------------------------------------------------
def _own_verified_blob() -> dict[int, str]:
    """num -> that source's OWN verified span text: its verified kept-sentences PLUS its
    own basket members whose evidence_id matches the row AND span_verdict == SUPPORTS."""
    num_by_eid = {b["evidence_id"]: b["num"] for b in BIBLIOGRAPHY}
    blob: dict[int, str] = {}
    for c in SECTION_CLAIMS:
        if not c["is_verified"]:
            continue
        n = num_by_eid[c["evidence_id"]]
        blob[n] = blob.get(n, "") + " " + c["sentence"]
    for b in BIBLIOGRAPHY:
        for basket in b.get("baskets", []):
            for m in basket.get("supporting_members", []):
                if str(m.get("evidence_id") or "") == b["evidence_id"] and \
                        str(m.get("span_verdict") or "").upper() == "SUPPORTS":
                    blob[b["num"]] = blob.get(b["num"], "") + " " + str(m.get("direct_quote") or "")
    return blob


def _whole_word(needle: str, blob: str, *, ignore_case: bool) -> bool:
    flags = re.IGNORECASE if ignore_case else 0
    body = re.escape(needle.replace("-", " "))
    return re.search(r"(?<!\w)" + body + r"(?!\w)", blob.replace("-", " "), flags) is not None


def test_attribute_cells_are_whole_word_traceable_to_own_verified_spans():
    from src.polaris_graph.generator.summary_table import _GEO_PHRASES, _GEO_ABBREV
    res = _render()
    own_blob = _own_verified_blob()

    # display -> curated phrases (case-insensitive) / abbrev literals (case-sensitive).
    geo_ci: dict[str, list[str]] = {}
    for phrase, display in _GEO_PHRASES:
        geo_ci.setdefault(display, []).append(phrase)
    geo_cs: dict[str, list[str]] = {}
    for body, display in _GEO_ABBREV:
        geo_cs.setdefault(display, []).append(body.replace("\\", ""))  # "U\\.S\\." -> "U.S."

    for row in _data_rows(res.text):
        cells = _cells(row)
        num = _num_of(row)
        blob = own_blob.get(num, "")
        # Domain (col 2) + Risk (col 4): the display IS the verbatim phrase.
        for col in (2, 4):
            if cells[col] == GAP_CELL:
                continue
            for term in [t.strip() for t in cells[col].split(";")]:
                assert _whole_word(term, blob, ignore_case=True), (num, col, term)
        # Geography (col 1): some curated phrase/abbrev for the display is whole-word present.
        if cells[1] != GAP_CELL:
            for disp in [t.strip() for t in cells[1].split(";")]:
                ok = any(_whole_word(p, blob, ignore_case=True) for p in geo_ci.get(disp, []))
                ok = ok or any(_whole_word(tok, blob, ignore_case=False) for tok in geo_cs.get(disp, []))
                assert ok, (num, disp)


def test_specific_gap_and_filled_cells():
    res = _render()
    by_num = {_num_of(r): _cells(r) for r in _data_rows(res.text)}
    # [4] Acemoglu & Restrepo — span says "US labor markets" -> Country/Region filled.
    assert "United States" in by_num[4][1]
    # [6] Brynjolfsson — span says "customer-support agents" -> Application Area filled.
    assert "customer support" in by_num[6][2].lower()
    # [1] Autor — no geography term in its verified span -> disclosed gap.
    assert by_num[1][1] == GAP_CELL


def test_no_row_for_source_without_verified_claim():
    res = _render()
    nums = {_num_of(r) for r in _data_rows(res.text)}
    assert 99 not in nums  # the un-verified source earns no row


# ---------------------------------------------------------------------------
# iter-2 Fable blocker: WORD-BOUNDARY matching (never a substring fabrication)
# ---------------------------------------------------------------------------
SUBSTRING_TRAP_BIB = [{
    "num": 8,
    "evidence_id": "substring_trap",
    "source_title": "A study examining and determining labor trends",
    "authors": ["Probe P"],
    "tier": "T2",
    "baskets": [{
        "claim_cluster_id": "cc_trap",
        "verified_support_origin_count": 1,
        "claim_text": "a synthesized trap claim",
        "supporting_members": [_member(
            "substring_trap",
            "Researchers are examining and determining broad labor trends, undermining "
            "prior conclusions across Indiana; the manufacturing sector adopted these tools.",
        )],
    }],
}]


def test_word_boundary_no_substring_fabrication():
    """"mining" must NOT be surfaced from examining/determining/undermining, and "india"
    must NOT be surfaced from "Indiana"; a real whole-word term ("manufacturing") still
    fills. Proves the anti-substring word-boundary fix."""
    res = render_requested_summary_table(
        research_question=DRB72_QUESTION,
        bibliography=SUBSTRING_TRAP_BIB,
        section_claims=[],
        existing_report_md="",
        appendix_boundary_marker="",
    )
    assert res.changed is True
    assert res.rows == 1  # the trap source has a SUPPORTS own member -> a row
    cells = _cells(_data_rows(res.text)[0])
    # Application Area/Occupation (domain): a REAL whole word fills, the substring trap does not.
    assert "manufacturing" in cells[2].lower()
    assert "Mining" not in cells[2]
    # Country/Region (geography): "Indiana" must NOT be read as "India" -> honest gap.
    assert cells[1] == GAP_CELL
    assert "India" not in cells[1]


# ---------------------------------------------------------------------------
# iter-2 Codex blocker: SUPPORTS-gated OWN-member VERBATIM fallback (mixed basket)
# ---------------------------------------------------------------------------
CROSS_SOURCE_UNSUPPORTED_BIB = [{
    "num": 7,
    "evidence_id": "own_unsupported",
    "source_title": "Source whose own member is not SUPPORTS",
    "authors": ["Own O"],
    "tier": "T3",
    "baskets": [{
        "claim_cluster_id": "cc_cross",
        "verified_support_origin_count": 1,
        # Synthesized cluster claim carrying the OTHER source's wording.
        "claim_text": "In Germany, radiologists doubled throughput using AI.",
        "supporting_members": [
            # A DIFFERENT source's SUPPORTS member — must NEVER be borrowed.
            _member("other_source", "In Germany, radiologists doubled throughput using AI."),
            # THIS row's OWN member, NOT verified-SUPPORTS.
            _member("own_unsupported", "This source's own span was not verified.",
                    verdict="UNSUPPORTED"),
        ],
    }],
}]


def test_mixed_basket_no_fallback_when_own_member_not_supports():
    """A source whose OWN basket member is not SUPPORTS (and has no kept-sentence) earns NO
    row: it must NOT borrow the co-basket OTHER source's SUPPORTS quote, nor render the
    synthesized cross-source claim_text."""
    res = render_requested_summary_table(
        research_question=DRB72_QUESTION,
        bibliography=CROSS_SOURCE_UNSUPPORTED_BIB,
        section_claims=[],
        existing_report_md="",
        appendix_boundary_marker="",
    )
    assert res.changed is False  # no verified OWN claim -> no rows -> no table
    assert "Germany" not in res.text
    assert "radiologist" not in res.text


MIXED_OWN_SUPPORTS_BIB = [{
    "num": 5,
    "evidence_id": "own_supports",
    "source_title": "Own SUPPORTS member inside a mixed basket",
    "authors": ["Own S"],
    "tier": "T2",
    "baskets": [{
        "claim_cluster_id": "cc_mixed",
        "verified_support_origin_count": 2,
        # Synthesized cluster claim (another source's wording) -> must NOT render.
        "claim_text": "In Germany, radiologists doubled throughput using AI.",
        "supporting_members": [
            _member("other_source", "In Germany, radiologists doubled throughput using AI."),
            _member(
                "own_supports",
                "A software developer completed several coding tasks 55% faster with the "
                "AI assistant.",
            ),
        ],
    }],
}]


def test_mixed_basket_renders_only_own_member_verbatim():
    """When the OWN member IS SUPPORTS in a mixed basket, the fallback renders THAT
    member's VERBATIM direct_quote only — never the co-basket source's quote nor the
    synthesized claim_text; attributes come only from the own span."""
    res = render_requested_summary_table(
        research_question=DRB72_QUESTION,
        bibliography=MIXED_OWN_SUPPORTS_BIB,
        section_claims=[],
        existing_report_md="",
        appendix_boundary_marker="",
    )
    assert res.rows == 1
    cells = _cells(_data_rows(res.text)[0])
    # Renders THIS source's OWN verbatim direct_quote.
    assert "software developer completed several coding tasks 55% faster" in cells[3].lower()
    # NEVER the co-basket OTHER source's span or the synthesized claim_text.
    assert "Germany" not in res.text
    assert "radiologist" not in res.text
    # Domain attribute is scanned from the OWN span only: "software developer" whole-word.
    assert "software developer" in cells[2].lower()


def test_own_member_verbatim_not_synthesized_claim_text():
    """The fallback claim is the member's VERBATIM direct_quote, distinct from the basket's
    synthesized claim_text (which is never rendered)."""
    res = render_requested_summary_table(
        research_question=DRB72_QUESTION,
        bibliography=BIBLIOGRAPHY,
        section_claims=[],  # force the fallback path for every row
        existing_report_md="",
        appendix_boundary_marker="",
    )
    assert res.changed is True
    assert res.rows == 3  # nums 1, 4, 6 have a SUPPORTS own member; 99 (UNSUPPORTED) does not
    # [6] renders its verbatim member span (mentions "5,172"), NOT the synthesized claim_text.
    assert "5,172" in res.text
    assert "Generative AI raises customer-support productivity" not in res.text
    # 99's own member is UNSUPPORTED -> excluded.
    nums = {_num_of(r) for r in _data_rows(res.text)}
    assert nums == {1, 4, 6}


# ---------------------------------------------------------------------------
# Morphological near-duplicate collapse within a cell
# ---------------------------------------------------------------------------
def test_morphological_near_duplicates_collapsed_in_cell():
    from src.polaris_graph.generator.summary_table import _match_terms_ci, _RISK_PHRASES
    # Both "displace" and "displacement" appear as whole words; they collapse to one form.
    terms = _match_terms_ci(
        "the reform risked displace outcomes and outright displacement of workers",
        _RISK_PHRASES,
    )
    lowered = [t.lower() for t in terms]
    assert lowered.count("displace") + lowered.count("displacement") == 1


def test_word_boundary_matcher_rejects_substrings_directly():
    from src.polaris_graph.generator.summary_table import (
        _match_terms_ci, _match_geography, _DOMAIN_PHRASES,
    )
    # "mining" inside examining/determining/undermining -> no domain term.
    assert _match_terms_ci("examining determining undermining", _DOMAIN_PHRASES) == []
    # "india" inside "Indiana"/"Indonesia" -> no geography term.
    assert _match_geography("Indiana and Indonesia") == []
    # but real whole words still match.
    assert "Mining" in _match_terms_ci("the mining sector", _DOMAIN_PHRASES)
    assert "India" in _match_geography("firms in India")


# --- a real drb_72 chrome source: a Cloudflare CAPTCHA interstitial ---------
CHROME_BIB = {
    "num": 23,
    "evidence_id": "cloudflare_interstitial",
    "source_title": "Just a moment...",
    "authors": [],
    "tier": "T7",
    "baskets": [{
        "claim_cluster_id": "cc_chrome",
        "verified_support_origin_count": 1,
        "claim_text": "To continue, complete the security check below.",
        "supporting_members": [_member(
            "cloudflare_interstitial", "To continue, complete the security check below."
        )],
    }],
}
CHROME_CLAIM = {
    "evidence_id": "cloudflare_interstitial",
    "sentence": "To continue, complete the security check below [#ev:cloudflare_interstitial:0-40].",
    "span_verdict": "SUPPORTS",
    "is_verified": True,
}


def test_chrome_only_source_yields_no_row_default_screen():
    """A CAPTCHA interstitial is not a research finding: the built-in chrome screen
    excludes it so it never renders as a "Research Literature" row (it still lives in
    the bibliography)."""
    res = render_requested_summary_table(
        research_question=DRB72_QUESTION,
        bibliography=BIBLIOGRAPHY + [CHROME_BIB],
        section_claims=SECTION_CLAIMS + [CHROME_CLAIM],
        existing_report_md="",
        appendix_boundary_marker="",
    )
    assert res.changed is True
    assert res.rows == 3  # the 3 real sources; the CAPTCHA row is excluded
    assert "Just a moment" not in res.text
    assert "complete the security check" not in res.text


def test_injected_chrome_screen_is_used():
    # A custom screen that flags every span -> no rows at all.
    res = render_requested_summary_table(
        research_question=DRB72_QUESTION,
        bibliography=BIBLIOGRAPHY,
        section_claims=SECTION_CLAIMS,
        existing_report_md=RED_REPORT,
        appendix_boundary_marker=APPENDIX_BOUNDARY,
        chrome_screen=lambda _t: True,
    )
    assert res.changed is False  # every claim screened out -> no verified rows


# ---------------------------------------------------------------------------
# iter-4 Codex (admits_unverified): the chrome predicate must screen the
# Research-Literature cell METADATA (source_title / authors) too — not only the
# claim cell. A source can carry a CLEAN verified claim (so the row IS emitted)
# yet a chrome/interstitial source_title (e.g. a Cloudflare "Just a moment…"
# title) or license/boilerplate authors; that chrome must NOT render in the cell.
# The verified claim/row is always kept — only the chrome metadata is dropped and
# the label falls back to a clean citation form (CLAUDE.md §-1.3: EVERY rendered
# cell must be verified-clean). The existing chrome tests only cover the
# chrome-CLAIM exclusion path, which leaves this metadata path uncovered.
# ---------------------------------------------------------------------------
# A CLEAN, span-verified claim but a CHROME source_title (Cloudflare interstitial);
# a real, clean author. The row IS emitted (clean claim); the chrome title must be
# screened OUT of the literature cell while the clean author is preserved.
CHROME_TITLE_META_BIB = {
    "num": 12,
    "evidence_id": "chrome_title_clean_claim",
    "source_title": "Just a moment...",  # Cloudflare interstitial title (chrome)
    "authors": ["Bloom N"],              # a real, clean author name (must survive)
    "tier": "T2",
    "baskets": [{
        "claim_cluster_id": "cc_chrome_title",
        "verified_support_origin_count": 1,
        "claim_text": "synthesized",
        "supporting_members": [_member(
            "chrome_title_clean_claim",
            "Working-from-home productivity rose by 13% in a large field experiment.",
        )],
    }],
}
CHROME_TITLE_META_CLAIM = {
    "evidence_id": "chrome_title_clean_claim",
    "sentence": (
        "Working-from-home productivity rose by 13% in a large field experiment "
        "[#ev:chrome_title_clean_claim:0-80]."
    ),
    "span_verdict": "SUPPORTS",
    "is_verified": True,
}

# A CLEAN source_title but license/BOILERPLATE authors; the row IS emitted (clean
# claim); the boilerplate author must be screened OUT while the clean title survives.
BOILER_AUTHOR_META_BIB = {
    "num": 14,
    "evidence_id": "clean_title_boiler_author",
    "source_title": "The Future of Work After Generative AI",  # clean title (must survive)
    "authors": ["© 2024 All rights reserved"],                 # license furniture (chrome)
    "tier": "T2",
    "baskets": [{
        "claim_cluster_id": "cc_boiler_author",
        "verified_support_origin_count": 1,
        "claim_text": "synthesized",
        "supporting_members": [_member(
            "clean_title_boiler_author",
            "Automation adoption accelerated across surveyed firms after 2015.",
        )],
    }],
}
BOILER_AUTHOR_META_CLAIM = {
    "evidence_id": "clean_title_boiler_author",
    "sentence": (
        "Automation adoption accelerated across surveyed firms after 2015 "
        "[#ev:clean_title_boiler_author:0-80]."
    ),
    "span_verdict": "SUPPORTS",
    "is_verified": True,
}


def _lit_cell_for_num(text, num):
    """The Research-Literature (col 0) cell for the data row cited to ``num``."""
    for row in _data_rows(text):
        if _num_of(row) == num:
            return _cells(row)[0]
    raise AssertionError(f"no data row for num {num}")


def test_chrome_source_title_screened_from_literature_cell_but_row_kept():
    """RED before iter-4: a CLEAN verified claim whose source_title is a Cloudflare
    "Just a moment…" interstitial rendered that chrome in the Research-Literature cell.
    GREEN: the chrome title is screened out (built-in default screen) and the label falls
    back to a clean citation form, while the verified claim/row and the clean author are
    kept."""
    res = render_requested_summary_table(
        research_question=DRB72_QUESTION,
        bibliography=[CHROME_TITLE_META_BIB],
        section_claims=[CHROME_TITLE_META_CLAIM],
        existing_report_md="",
        appendix_boundary_marker="",
    )
    # The row IS emitted (the CLAIM is clean and verified) — chrome metadata never drops it.
    assert res.changed is True
    assert res.rows == 1
    assert "Working-from-home productivity rose by 13%" in res.text  # verified claim renders
    # The chrome source_title is screened OUT of the literature cell.
    assert "Just a moment" not in res.text
    lit = _lit_cell_for_num(res.text, 12)
    assert "Just a moment" not in lit
    # The clean author is preserved; the cell falls back to author + a single citation.
    assert lit == "Bloom N [12]"


def test_boilerplate_authors_screened_from_literature_cell_but_title_kept():
    """RED before iter-4: a CLEAN verified claim whose authors are license/boilerplate
    ("© … all rights reserved") rendered that furniture in the Research-Literature cell.
    GREEN: the boilerplate author is screened out while the clean title and the verified
    claim/row are kept."""
    res = render_requested_summary_table(
        research_question=DRB72_QUESTION,
        bibliography=[BOILER_AUTHOR_META_BIB],
        section_claims=[BOILER_AUTHOR_META_CLAIM],
        existing_report_md="",
        appendix_boundary_marker="",
    )
    assert res.changed is True
    assert res.rows == 1
    assert "Automation adoption accelerated" in res.text  # verified claim renders
    # The boilerplate author furniture is screened OUT of the cell.
    assert "All rights reserved" not in res.text
    assert "all rights reserved" not in res.text.lower()
    lit = _lit_cell_for_num(res.text, 14)
    assert "rights reserved" not in lit.lower()
    # The clean title survives (author dropped -> title-only literature label).
    assert lit == "The Future of Work After Generative AI [14]"


def test_injected_predicate_screens_literature_metadata_not_only_claim():
    """The INJECTED chrome predicate (the production ``is_render_chrome_or_unrenderable``)
    is applied to the source_title/authors cell metadata too, not only the claim cell. A
    sentinel-flagging predicate screens the sentinel title/author out of the literature
    cell while clean-metadata rows keep their real titles (proves it is not a blanket drop)
    and the sentinel row's verified claim is still rendered."""
    def screen(t):  # flags ONLY the sentinel token — a clean, deterministic injected screen
        return "ZZCHROMEZZ" in (t or "")

    sentinel_bib = {
        "num": 13,
        "evidence_id": "sentinel_meta",
        "source_title": "ZZCHROMEZZ scraped masthead",  # injected-chrome title
        "authors": ["ZZCHROMEZZ license line"],          # injected-chrome author
        "tier": "T2",
        "baskets": [{
            "claim_cluster_id": "cc_sentinel",
            "verified_support_origin_count": 1,
            "claim_text": "synthesized",
            "supporting_members": [_member(
                "sentinel_meta",
                "Adoption of AI tools rose across surveyed firms during the study period.",
            )],
        }],
    }
    sentinel_claim = {
        "evidence_id": "sentinel_meta",
        "sentence": (
            "Adoption of AI tools rose across surveyed firms during the study period "
            "[#ev:sentinel_meta:0-80]."
        ),
        "span_verdict": "SUPPORTS",
        "is_verified": True,
    }
    res = render_requested_summary_table(
        research_question=DRB72_QUESTION,
        bibliography=BIBLIOGRAPHY + [sentinel_bib],
        section_claims=SECTION_CLAIMS + [sentinel_claim],
        existing_report_md="",
        appendix_boundary_marker="",
        chrome_screen=screen,
    )
    assert res.changed is True
    assert res.rows == 4  # nums 1/4/6 (clean) + the sentinel row 13
    # Clean-metadata rows keep their REAL titles: the injected predicate is not a blanket drop.
    assert "Robots and Jobs" in res.text
    # The injected-chrome metadata is screened OUT of the literature cell...
    assert "ZZCHROMEZZ" not in res.text
    # ...but the sentinel row's verified CLAIM still renders (the row is NOT dropped)...
    assert "Adoption of AI tools rose" in res.text
    # ...and its literature cell falls back to a clean single citation.
    assert _lit_cell_for_num(res.text, 13) == "Source [13]"


# ---------------------------------------------------------------------------
# iter-5 Codex P2: the ``authors`` value must be NORMALIZED to a list before the
# per-author screening loop. Provenance may supply ``authors`` as a single STRING
# instead of a list; iterating a bare string would screen it CHARACTER-by-character
# (splitting "Bloom N" into "B et al." and defeating the whole-phrase chrome screen).
# A str => a ONE-element list (screened as ONE author); a list/tuple is kept as-is;
# None/other keeps the empty fallback. The verified claim/row is always kept.
# ---------------------------------------------------------------------------
# A CLEAN verified claim whose ``authors`` field is a single STRING (not a list). The
# string author must be screened as ONE entry and kept WHOLE — never iterated into chars.
STRING_AUTHOR_CLEAN_BIB = {
    "num": 15,
    "evidence_id": "string_author_clean",
    "source_title": "Generative AI and the Labor Market",
    "authors": "Bloom N",  # a single STRING author (NOT a list)
    "tier": "T2",
    "baskets": [{
        "claim_cluster_id": "cc_string_author_clean",
        "verified_support_origin_count": 1,
        "claim_text": "synthesized",
        "supporting_members": [_member(
            "string_author_clean",
            "Remote work adoption rose sharply across surveyed firms after 2020.",
        )],
    }],
}
STRING_AUTHOR_CLEAN_CLAIM = {
    "evidence_id": "string_author_clean",
    "sentence": (
        "Remote work adoption rose sharply across surveyed firms after 2020 "
        "[#ev:string_author_clean:0-80]."
    ),
    "span_verdict": "SUPPORTS",
    "is_verified": True,
}

# A CLEAN verified claim whose ``authors`` field is a single CHROME/boilerplate STRING. It
# must be screened as ONE entry and dropped (never iterated into chars, which would also
# defeat the whole-phrase chrome screen); the label falls back to the clean title.
STRING_AUTHOR_CHROME_BIB = {
    "num": 16,
    "evidence_id": "string_author_chrome",
    "source_title": "The Economics of Automation",
    "authors": "© 2024 All rights reserved",  # a single CHROME string author
    "tier": "T2",
    "baskets": [{
        "claim_cluster_id": "cc_string_author_chrome",
        "verified_support_origin_count": 1,
        "claim_text": "synthesized",
        "supporting_members": [_member(
            "string_author_chrome",
            "Firm-level automation investment increased steadily over the past decade.",
        )],
    }],
}
STRING_AUTHOR_CHROME_CLAIM = {
    "evidence_id": "string_author_chrome",
    "sentence": (
        "Firm-level automation investment increased steadily over the past decade "
        "[#ev:string_author_chrome:0-80]."
    ),
    "span_verdict": "SUPPORTS",
    "is_verified": True,
}


def test_string_author_screened_as_one_entry_not_split_into_characters():
    """P2 (Codex iter-4): when provenance supplies ``authors`` as a single STRING instead of
    a list, it is normalized to a ONE-element list and screened as ONE author — never
    iterated character-by-character. RED before the iter-5 normalization: a bare string is
    iterated per-char, so a clean "Bloom N" corrupts into "B et al." and a chrome string
    slips past the whole-phrase screen. GREEN: the clean string author is kept whole; the
    chrome string author is dropped as one entry and the label falls back to the clean
    title. The verified claim/row is always kept."""
    res = render_requested_summary_table(
        research_question=DRB72_QUESTION,
        bibliography=[STRING_AUTHOR_CLEAN_BIB, STRING_AUTHOR_CHROME_BIB],
        section_claims=[STRING_AUTHOR_CLEAN_CLAIM, STRING_AUTHOR_CHROME_CLAIM],
        existing_report_md="",
        appendix_boundary_marker="",
    )
    # Both verified claims render their rows (metadata screening never drops a row).
    assert res.changed is True
    assert res.rows == 2
    # Clean single-string author kept as ONE whole author — NOT split into characters.
    lit_clean = _lit_cell_for_num(res.text, 15)
    assert lit_clean == "Bloom N — Generative AI and the Labor Market [15]"
    assert "et al." not in lit_clean  # a per-char iteration would corrupt "Bloom N" -> "B et al."
    assert "Remote work adoption rose sharply" in res.text  # verified claim renders
    # Chrome single-string author screened out as ONE entry; label falls back to clean title.
    lit_chrome = _lit_cell_for_num(res.text, 16)
    assert lit_chrome == "The Economics of Automation [16]"
    assert "rights reserved" not in lit_chrome.lower()
    assert "all rights reserved" not in res.text.lower()
    assert "Firm-level automation investment increased" in res.text  # verified claim renders


def test_list_authors_unchanged_by_normalization():
    """Control: the normalization does NOT change behavior for the normal list-of-authors
    path — a clean list author still renders exactly as before (proves it is not a blanket
    rewrite of the authors handling)."""
    res = render_requested_summary_table(
        research_question=DRB72_QUESTION,
        bibliography=BIBLIOGRAPHY,
        section_claims=SECTION_CLAIMS,
        existing_report_md="",
        appendix_boundary_marker="",
    )
    # [1] Autor D. supplied as ["Autor D"] -> the single list author renders whole.
    assert _lit_cell_for_num(res.text, 1).startswith("Autor D — ")
    # [4] Acemoglu D, Restrepo P. supplied as a 2-author list -> both names render.
    assert "Acemoglu D, Restrepo P" in _lit_cell_for_num(res.text, 4)


# ---------------------------------------------------------------------------
# Kill-switch / idempotency / no-request
# ---------------------------------------------------------------------------
def test_kill_switch_off_is_byte_identical(monkeypatch):
    monkeypatch.setenv("PG_RENDER_SUMMARY_TABLE", "0")
    res = _render()
    assert res.changed is False
    assert res.text == RED_REPORT


def test_idempotent_second_pass_is_noop(monkeypatch):
    monkeypatch.delenv("PG_RENDER_SUMMARY_TABLE", raising=False)
    first = _render()
    assert first.changed is True
    second = render_requested_summary_table(
        research_question=DRB72_QUESTION,
        bibliography=BIBLIOGRAPHY,
        section_claims=SECTION_CLAIMS,
        existing_report_md=first.text,
        appendix_boundary_marker=APPENDIX_BOUNDARY,
    )
    assert second.changed is False
    assert second.text == first.text
    assert TABLE_MARKER in first.text


def test_no_table_when_prompt_does_not_request_one():
    res = render_requested_summary_table(
        research_question="Write a narrative report, no table needed.",
        bibliography=BIBLIOGRAPHY,
        section_claims=SECTION_CLAIMS,
        existing_report_md=RED_REPORT,
        appendix_boundary_marker=APPENDIX_BOUNDARY,
    )
    assert res.changed is False
    assert res.text == RED_REPORT


def test_no_table_when_no_verified_rows():
    res = render_requested_summary_table(
        research_question=DRB72_QUESTION,
        bibliography=[BIBLIOGRAPHY[3]],  # only the un-verified source (UNSUPPORTED member)
        section_claims=[],
        existing_report_md=RED_REPORT,
        appendix_boundary_marker=APPENDIX_BOUNDARY,
    )
    assert res.changed is False


def test_build_markdown_standalone_shape():
    from src.polaris_graph.generator.summary_table import _build_rows
    rows = _build_rows(BIBLIOGRAPHY, SECTION_CLAIMS)
    md = build_summary_table_markdown(DRB72_HEADERS, rows)
    lines = [ln for ln in md.splitlines() if ln.startswith("|")]
    assert len(lines) == 2 + len(rows)  # header + separator + rows
    assert TABLE_MARKER in md


# ---------------------------------------------------------------------------
# iter-3 Codex P2: section-claim acceptance requires strict-verify-PASSED
# (is_verified), NOT span_verdict==SUPPORTS alone. A span can isolate-SUPPORT
# while the kept sentence still fails strict_verify (numeric-match / content-
# overlap / provenance) — such a claim must NOT seed a table cell.
# ---------------------------------------------------------------------------
# The source's OWN basket member is NOT SUPPORTS, so the verbatim-fallback path yields
# nothing — this ISOLATES the section-claim acceptance gate as the only way a row could
# appear, so the test keys purely on the is_verified gate.
SUPPORTS_BUT_UNVERIFIED_BIB = [{
    "num": 3,
    "evidence_id": "supports_but_unverified",
    "source_title": "Span isolate-SUPPORTS but strict_verify failed",
    "authors": ["Verify V"],
    "tier": "T2",
    "baskets": [{
        "claim_cluster_id": "cc_sv",
        "verified_support_origin_count": 0,
        "claim_text": "synthesized",
        "supporting_members": [_member(
            "supports_but_unverified", "This source's own span was not verified.",
            verdict="UNSUPPORTED",
        )],
    }],
}]
# A section claim whose span_verdict is SUPPORTS but which did NOT pass strict_verify.
SUPPORTS_BUT_UNVERIFIED_CLAIM = {
    "evidence_id": "supports_but_unverified",
    "sentence": (
        "An isolate-SUPPORTS span that did not pass strict_verify "
        "[#ev:supports_but_unverified:0-40]."
    ),
    "span_verdict": "SUPPORTS",
    "is_verified": False,
}


def test_section_claim_requires_is_verified_not_span_verdict_alone():
    """P2 (Codex iter-2): a section claim with span_verdict==SUPPORTS but is_verified==False
    is REJECTED. With the source's own basket member NOT SUPPORTS (no fallback), the source
    earns NO row — proving the gate keys on strict-verify-passed, not span_verdict alone.
    RED before the iter-3 tightening (``is_verified OR SUPPORTS`` would have accepted it)."""
    res = render_requested_summary_table(
        research_question=DRB72_QUESTION,
        bibliography=SUPPORTS_BUT_UNVERIFIED_BIB,
        section_claims=[SUPPORTS_BUT_UNVERIFIED_CLAIM],
        existing_report_md="",
        appendix_boundary_marker="",
    )
    assert res.changed is False  # is_verified False + own member not SUPPORTS -> no row
    assert "did not pass strict_verify" not in res.text  # unverified prose never leaks


def test_section_claim_accepted_when_is_verified_true():
    """Control: the SAME source + SAME SUPPORTS span but is_verified==True DOES seed a row,
    proving the tightening keys on ``is_verified`` and is not a blanket rejection."""
    verified_claim = dict(SUPPORTS_BUT_UNVERIFIED_CLAIM, is_verified=True)
    res = render_requested_summary_table(
        research_question=DRB72_QUESTION,
        bibliography=SUPPORTS_BUT_UNVERIFIED_BIB,
        section_claims=[verified_claim],
        existing_report_md="",
        appendix_boundary_marker="",
    )
    assert res.changed is True
    assert res.rows == 1


# ---------------------------------------------------------------------------
# iter-3 Codex P1: the wire-point in scripts/run_honest_sweep_r3.py inserts the
# prompt-requested table into the report.md ARTIFACT body. Exercises the REAL
# wired chain multi.sections -> extract_section_claims -> render_requested_summary_table
# on production-shaped SectionResult / SentenceVerification / bibliography objects.
# ---------------------------------------------------------------------------
# A body that already carries the "## Bibliography" boundary the wire-point inserts before.
WIRED_BODY = (
    "# Research report: impact of Generative AI on the future labor market\n\n"
    "## Key Findings\n\n- One more robot per thousand workers reduces employment.[4]\n\n"
    "## Bibliography\n\n"
    "1. Autor D. Why Are There Still So Many Jobs?\n"
    "4. Acemoglu D, Restrepo P. Robots and Jobs.\n"
    "6. Brynjolfsson E et al. Generative AI at Work.\n"
)


def test_wired_path_renders_table_into_report_artifact():
    """P1 (Codex iter-2): the summary-table renderer is WIRED into the real report path.
    ``scripts.run_honest_sweep_r3.render_summary_table_into_artifact`` extracts the verified
    section claims from the multi-section results and inserts the requested table into the
    report.md artifact body. Feeds production-shaped ``multi.sections`` (SectionResult-like
    with ``kept_sentences_pre_resolve`` of SentenceVerification-like SVs whose first token
    names the source) so the whole wired chain is exercised — the pre-fix path emitted no
    table at all."""
    import importlib
    sweep = importlib.import_module("scripts.run_honest_sweep_r3")

    sections = [
        types.SimpleNamespace(
            dropped_due_to_failure=False,
            kept_sentences_pre_resolve=[
                _sv(
                    "One more robot per thousand workers reduces the employment-to-population "
                    "ratio by 0.2 percentage points and wages by 0.42% "
                    "[#ev:acemoglu_restrepo_robots_jobs:0-688].",
                    "acemoglu_restrepo_robots_jobs",
                ),
                _sv(
                    "Access to AI assistance increases worker productivity, as measured by "
                    "issues resolved per hour, by 15% on average "
                    "[#ev:brynjolfsson_genai_at_work:0-800].",
                    "brynjolfsson_genai_at_work",
                ),
                # An UNVERIFIED SV (is_verified False) must never enter the table.
                _sv(
                    "A refuted fabrication [#ev:acemoglu_restrepo_robots_jobs:0-1].",
                    "acemoglu_restrepo_robots_jobs", is_verified=False, verdict="REFUTES",
                ),
            ],
        ),
    ]
    multi = types.SimpleNamespace(bibliography=BIBLIOGRAPHY, sections=sections)

    new_body, canary = sweep.render_summary_table_into_artifact(
        WIRED_BODY,
        research_question=DRB72_QUESTION,
        bibliography=multi.bibliography,
        sections=multi.sections,
    )

    # RED baseline: the input body has no table.
    assert not any(ln.lstrip().startswith("|") for ln in WIRED_BODY.splitlines())
    # GREEN: the wired chain rendered a table into the artifact body.
    assert new_body != WIRED_BODY
    assert "## Summary table" in new_body
    assert TABLE_MARKER in new_body
    assert canary.startswith("[summary_table]")
    # Inserted before the bibliography boundary (the table concludes the narrative).
    assert new_body.index("## Summary table") < new_body.index("## Bibliography")
    # Verified numbers render (cited); the refuted SV never appears.
    assert "0.42%" in new_body
    assert "15%" in new_body
    assert "refuted fabrication" not in new_body
    # header + 3 verified source rows (nums 1/4/6 in BIBLIOGRAPHY each carry a verified
    # claim: 4 & 6 from the section SVs, 1 from its own SUPPORTS basket-member fallback).
    body_rows = _data_rows(new_body)
    assert len(body_rows) == 3
    for row in body_rows:
        assert row.count("|") == 6  # exactly the 5 requested columns
