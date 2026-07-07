"""Vocabulary-expansion tests for the verified-only summary-table renderer
(I-deepfix-001, #1344).

The summary table surfaces a Country/Region, Application-Area/Occupation or Key-Risks
term ONLY when that term appears VERBATIM as a WHOLE WORD in the source's OWN verified
span text (via ``_word_boundary_search`` — the anti-fabrication core). The curated
vocabularies were labor-market-narrow, so a verified source whose span literally says
"Belgium" still rendered "—". This suite proves the EXPANDED vocabularies:

* surface genuinely-present new countries / domains / risks (verbatim, whole-word);
* NEVER surface a term as a SUBSTRING of a larger word ("poland" not from
  "lapland"/"upland", "india" not from "indiana", "bahrain" not from a larger token,
  "bias" not from "biased", "cost" not from "costume", "sales" not from "wholesales");
* NEVER surface a term that is verbatim-ABSENT — that cell renders the "—" disclosed
  gap, nothing inferred (faithfulness-neutral: expansion adds candidate vocab, it never
  injects a term not present in the verified evidence);
* are consulted ONLY when the table renders — with ``PG_RENDER_SUMMARY_TABLE=0`` the
  renderer is a byte-identical no-op.

The 14 drb_72 study countries motivated the 5 missing additions (Belgium, Netherlands,
Poland, Saudi Arabia, Bahrain); the vocab itself is a GENERAL comprehensive list (no
study title, no study->country mapping anywhere).
"""

from __future__ import annotations

import pytest

from src.polaris_graph.generator.summary_table import (
    GAP_CELL,
    _DOMAIN_PHRASES,
    _GEO_ABBREV,
    _GEO_PHRASES,
    _RISK_PHRASES,
    _match_geography,
    _match_terms_ci,
    render_requested_summary_table,
)

# A DRB72-style prompt that requests a titled 5-column summary table (so
# ``parse_requested_headers`` returns >= 2 headers and the renderer fires).
TABLE_QUESTION = (
    "Please write a research report on the labor-market impact of Generative AI. At the "
    "end, create a summary table. The table column headers should be \"Research "
    "Literature\", \"Country/Region\", \"Application Area/Occupation\", \"Specific "
    "Applications and Impacts\", and \"Key Risks and Limitations\"."
)


def _member(eid, quote, verdict="SUPPORTS"):
    return {"evidence_id": eid, "span_verdict": verdict, "direct_quote": quote}


def _one_source_bib(eid, quote, *, num=1, title="A verified study", authors=("Author A",)):
    """A single numbered bibliography row whose OWN basket member carries ``quote`` as a
    verified (span_verdict==SUPPORTS) direct_quote."""
    return [{
        "num": num,
        "evidence_id": eid,
        "source_title": title,
        "authors": list(authors),
        "tier": "T1",
        "baskets": [{
            "claim_cluster_id": f"cc_{eid}",
            "verified_support_origin_count": 1,
            "claim_text": "synthesized cluster claim (never rendered)",
            "supporting_members": [_member(eid, quote)],
        }],
    }]


def _section_claim(eid, sentence):
    return {
        "evidence_id": eid,
        "sentence": f"{sentence} [#ev:{eid}:0-200].",
        "span_verdict": "SUPPORTS",
        "is_verified": True,
    }


def _render_single(eid, quote, sentence=None):
    """Render a one-row table for a source whose verified span is ``quote`` (and, when
    given, a clean kept-sentence ``sentence``). Returns the SummaryTableResult."""
    section_claims = [_section_claim(eid, sentence)] if sentence else []
    return render_requested_summary_table(
        research_question=TABLE_QUESTION,
        bibliography=_one_source_bib(eid, quote),
        section_claims=section_claims,
        existing_report_md="",
        appendix_boundary_marker="",
    )


def _data_rows(text):
    rows = [ln for ln in text.splitlines() if ln.lstrip().startswith("|")]
    return rows[2:]  # skip header + separator


def _cells(row):
    return [c.strip() for c in row.strip().strip("|").split("|")]


# Column ROLE order for the drb_72 headers: LIT, GEO, DOMAIN, CLAIM, RISK.
GEO_COL, DOMAIN_COL, RISK_COL = 1, 2, 4


# ---------------------------------------------------------------------------
# The expansion is present (the 5 drb_72-missing countries + a broad general set)
# ---------------------------------------------------------------------------
def test_five_drb72_missing_countries_now_in_vocab():
    displays = {d for _, d in _GEO_PHRASES}
    for country in ("Belgium", "Netherlands", "Poland", "Saudi Arabia", "Bahrain"):
        assert country in displays, country


def test_geo_vocab_is_comprehensive_general_not_benchmark_narrow():
    # A GENERAL world-economies set: dozens of distinct display countries/regions.
    displays = {d for _, d in _GEO_PHRASES}
    assert len(displays) >= 50
    for country in ("Italy", "Spain", "Australia", "South Korea", "Brazil",
                    "Switzerland", "Sweden", "Ireland", "Israel", "Singapore",
                    "Austria", "Finland", "Norway", "Denmark"):
        assert country in displays, country


def test_new_domain_and_risk_terms_present():
    for phrase in ("scientific writing", "oral radiology", "dental education",
                   "organizational change", "office work", "employer flexibility",
                   "skills training", "recruitment"):
        assert phrase in _DOMAIN_PHRASES, phrase
    for phrase in ("bias", "gender bias", "data privacy", "over-reliance",
                   "high cost", "worker safety"):
        assert phrase in _RISK_PHRASES, phrase
    # The neutral/positive-polarity tokens were PRUNED (Codex P2 — goals/mechanisms,
    # not risks); they must no longer be in the vocab.
    for phrase in ("reliability", "accuracy", "transparency", "governance",
                   "compliance", "regulation", "regulatory", "cost", "safety",
                   "security", "ethics", "fairness", "well-being", "wellbeing",
                   "job quality", "accountability", "explainability", "oversight"):
        assert phrase not in _RISK_PHRASES, phrase


# ---------------------------------------------------------------------------
# Geography: verbatim whole-word present -> surfaced; substring -> NOT surfaced
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("phrase,display", [
    ("Belgium", "Belgium"),
    ("Belgian", "Belgium"),
    ("the Netherlands", "Netherlands"),
    ("Poland", "Poland"),
    ("Saudi Arabia", "Saudi Arabia"),
    ("Bahrain", "Bahrain"),
    ("Italy", "Italy"),
    ("South Korea", "South Korea"),
])
def test_geography_verbatim_present_is_surfaced(phrase, display):
    assert display in _match_geography(f"a field study conducted in {phrase} in 2024")


@pytest.mark.parametrize("text", [
    "the lapland and upland regions of the north",   # 'poland' is a substring here
    "a manufacturing plant in Indiana",              # 'india' is a substring here
    "the xbahrainite mineral deposit",               # 'bahrain' is a substring here
    "we discuss polands",                            # 'poland' as a prefix of a longer token
])
def test_geography_substring_never_surfaced(text):
    # No country term must be fabricated from a larger word.
    assert _match_geography(text) == []


def test_poland_not_from_lapland_but_yes_from_poland():
    assert _match_geography("lapland uplands") == []
    assert _match_geography("firms in Poland") == ["Poland"]


def test_india_not_from_indiana_preserved():
    assert _match_geography("a plant in Indiana") == []
    assert _match_geography("firms in India") == ["India"]


# ---------------------------------------------------------------------------
# Homograph PRUNE (Codex+Fable P1): the ambiguous nationality ADJECTIVES whose
# dominant English sense is non-geographic were removed from the vocab, so they no
# longer surface a Country/Region the verified span does not actually support. The
# full country NAMES stay, so genuine geography still resolves.
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("text", [
    "workers used ChatGPT to polish their cover letters",   # polish -> Poland (pruned)
    "American Indian respondents",                           # indian -> India (pruned)
    "Korean American employees",                             # korean -> South Korea (pruned)
    "a turkey processing plant",                             # turkey -> Turkey (pruned)
    "the caterer served a danish",                           # danish -> Denmark (pruned)
    "he ordered french fries",                               # french -> France (pruned)
    "she seasoned the dutch oven",                           # dutch -> Netherlands (pruned)
    "a slice of swiss cheese",                               # swiss -> Switzerland (pruned)
    "a greek yogurt brand",                                  # greek -> Greece (pruned)
    "an irish coffee recipe",                                # irish -> Ireland (pruned)
    "the chile pepper harvest",                              # chile -> Chile (bare token pruned)
])
def test_pruned_homograph_adjectives_no_longer_over_match(text):
    # The ambiguous adjective/bare-token must NOT fabricate a country from generic prose.
    assert _match_geography(text) == []


def test_african_asian_american_demonyms_do_not_surface_africa_or_asia():
    """'African'/'Asian' as US-demographic adjectives must NOT surface Africa/Asia. The
    pre-existing multi-word phrase 'american workers' legitimately still maps to the
    United States (a correct match, NOT the pruned homograph defect), so the exact
    'workers' phrasing is asserted only against Africa/Asia leakage; a variant without
    that phrase returns nothing."""
    result = _match_geography("African American and Asian American workers")
    assert "Africa" not in result
    assert "Asia" not in result
    assert _match_geography("African American and Asian American respondents") == []


@pytest.mark.parametrize("text,display", [
    ("the study was conducted in Poland", "Poland"),
    ("a survey of workers in the Netherlands", "Netherlands"),
    ("employers in Belgium", "Belgium"),
    ("a Saudi Arabia sample", "Saudi Arabia"),
    ("respondents in Bahrain", "Bahrain"),
])
def test_genuine_geography_still_surfaces_after_prune(text, display):
    # The 5 drb_72 target countries keep resolving via their full NAME phrase.
    assert display in _match_geography(text)


def test_retained_proper_adjectives_still_resolve():
    # Lower-hazard proper adjectives that were KEPT (chilean, turkish) plus the
    # untouched pre-session adjectives still resolve their country.
    assert "Chile" in _match_geography("a chilean labor-market survey")
    assert "Turkey" in _match_geography("turkish manufacturing firms")
    assert "China" in _match_geography("chinese enterprises")   # pre-session, untouched
    assert "Canada" in _match_geography("canadian employers")   # pre-session, untouched


# ---------------------------------------------------------------------------
# Neutral/positive-polarity RISK tokens were PRUNED (Codex P2): they name goals or
# mechanisms, not risks, and read wrong in a "Key Risks and Limitations" cell.
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("text", [
    "the system improved reliability",
    "gains in accuracy were reported",
    "the firm valued transparency",
    "strong governance and oversight",
    "regulatory compliance was ensured",
    "worker well-being improved",
    "the low cost of the tool",
    "better safety outcomes",
    "a fairness and accountability review",
])
def test_pruned_neutral_tokens_no_longer_surface_as_risks(text):
    # A goal/mechanism word must not fill the Key-Risks cell now that it is pruned.
    assert _match_terms_ci(text, _RISK_PHRASES) == [], text


def test_risk_framed_forms_retained_after_prune():
    # The risk-FRAMED counterparts of the pruned tokens still surface.
    assert "Lack of transparency" in _match_terms_ci(
        "a clear lack of transparency", _RISK_PHRASES)
    assert "High cost" in _match_terms_ci("the high cost of adoption", _RISK_PHRASES)
    assert "Worker safety" in _match_terms_ci("worker safety incidents", _RISK_PHRASES)
    # hyphens are normalised to spaces in the surfaced display form.
    assert "Well being harm" in _match_terms_ci("documented well-being harm", _RISK_PHRASES)
    assert "Data security" in _match_terms_ci("a data security breach", _RISK_PHRASES)


# ---------------------------------------------------------------------------
# Domain: verbatim whole-word present -> surfaced; substring -> NOT surfaced
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("phrase,display", [
    ("scientific writing", "Scientific writing"),
    ("oral radiology", "Oral radiology"),
    ("dental education", "Dental education"),
    ("organizational change", "Organizational change"),
    ("office work", "Office work"),
    ("recruitment", "Recruitment"),
    ("employer flexibility", "Employer flexibility"),
    ("skills training", "Skills training"),
])
def test_domain_verbatim_present_is_surfaced(phrase, display):
    assert display in _match_terms_ci(f"the study of {phrase} across firms", _DOMAIN_PHRASES)


def test_domain_substring_never_surfaced():
    # 'sales' must NOT be read from 'wholesales'; a real whole word still fills.
    assert "Sales" not in _match_terms_ci("wholesales figures rose", _DOMAIN_PHRASES)
    assert "Sales" in _match_terms_ci("the sales team grew", _DOMAIN_PHRASES)
    # 'mining' (existing) still never from 'examining' (preserves the anti-substring core).
    assert _match_terms_ci("examining determining undermining", _DOMAIN_PHRASES) == []


# ---------------------------------------------------------------------------
# Risk: verbatim whole-word present -> surfaced; substring -> NOT surfaced
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("phrase,display", [
    ("bias", "Bias"),
    ("gender bias", "Gender bias"),
    ("data privacy", "Data privacy"),
    ("lack of transparency", "Lack of transparency"),
    ("high cost", "High cost"),
    ("worker safety", "Worker safety"),
    ("over-reliance", "Over reliance"),
])
def test_risk_verbatim_present_is_surfaced(phrase, display):
    assert display in _match_terms_ci(f"researchers flagged {phrase} as a concern", _RISK_PHRASES)


def test_risk_substring_never_surfaced():
    # 'bias' must NOT be read from 'biased'; the retained 'high cost' must NOT be read
    # from 'costume'.
    assert "Bias" not in _match_terms_ci("a biased estimate", _RISK_PHRASES)
    assert "High cost" not in _match_terms_ci("wearing a costume", _RISK_PHRASES)
    # real whole words still fill.
    assert "Bias" in _match_terms_ci("clear gender bias exists", _RISK_PHRASES)
    # bare 'cost' was pruned (Codex P2); only the risk-framed 'high cost' surfaces.
    assert "High cost" in _match_terms_ci("the high cost of adoption", _RISK_PHRASES)
    assert "Cost" not in _match_terms_ci("the cost was high", _RISK_PHRASES)


# ---------------------------------------------------------------------------
# End-to-end render: a source whose verified span literally names a new country/
# domain/risk surfaces them in the right cells; verbatim-absent -> disclosed gap.
# ---------------------------------------------------------------------------
def test_render_surfaces_new_country_domain_risk_from_own_verified_span():
    sentence = (
        "A field experiment conducted in Belgium found that generative AI improved "
        "scientific writing productivity, though researchers flagged data privacy and "
        "bias as key risks"
    )
    res = _render_single("study_belgium", sentence + ".", sentence=sentence)
    assert res.changed is True
    assert res.rows == 1
    cells = _cells(_data_rows(res.text)[0])
    # Country/Region: Belgium surfaced (was "—" before the expansion).
    assert "Belgium" in cells[GEO_COL]
    # A verbatim-ABSENT country is NOT surfaced (nothing inferred).
    assert "Netherlands" not in cells[GEO_COL]
    assert "France" not in cells[GEO_COL]
    # Application Area/Occupation: scientific writing surfaced.
    assert "scientific writing" in cells[DOMAIN_COL].lower()
    # Key Risks: data privacy and/or bias surfaced.
    assert "privacy" in cells[RISK_COL].lower() or "bias" in cells[RISK_COL].lower()


def test_render_office_work_poland_organizational_change():
    sentence = (
        "A study of office work in Poland examined organizational change and employer "
        "flexibility, noting over-reliance and high cost as limitations"
    )
    res = _render_single("study_poland", sentence + ".", sentence=sentence)
    assert res.rows == 1
    cells = _cells(_data_rows(res.text)[0])
    assert "Poland" in cells[GEO_COL]
    dom = cells[DOMAIN_COL].lower()
    assert "office work" in dom or "organizational change" in dom or "employer flexibility" in dom
    risk = cells[RISK_COL].lower()
    assert "over reliance" in risk or "cost" in risk


def test_verbatim_absent_term_yields_disclosed_gap():
    """A source whose verified span names NO curated country renders the "—" disclosed
    gap in the Country/Region cell — the expansion never infers a term that is not
    verbatim present in the verified evidence."""
    sentence = (
        "The analysis of remote work found that automation adoption rose steadily over "
        "the decade, with no single region dominating the sample"
    )
    res = _render_single("no_geo", sentence + ".", sentence=sentence)
    assert res.rows == 1
    cells = _cells(_data_rows(res.text)[0])
    assert cells[GEO_COL] == GAP_CELL  # no country term verbatim present -> honest gap


def test_expansion_does_not_leak_across_absent_terms():
    """Faithfulness-neutral: a span that names ONE country does not surface any OTHER
    country (no benchmark-gaming study->country mapping; only verbatim presence)."""
    res = _render_single(
        "only_italy",
        "The Italian survey covered a single national labor market.",
        sentence="The Italian survey covered a single national labor market",
    )
    cells = _cells(_data_rows(res.text)[0])
    assert cells[GEO_COL] == "Italy"  # exactly the verbatim-present country, nothing else


# ---------------------------------------------------------------------------
# Kill-switch OFF: the vocab is consulted ONLY when the table renders.
# ---------------------------------------------------------------------------
def test_kill_switch_off_is_byte_identical(monkeypatch):
    monkeypatch.setenv("PG_RENDER_SUMMARY_TABLE", "0")
    body = "# Report\n\nSome verified prose about a study in Belgium.[1]\n"
    res = render_requested_summary_table(
        research_question=TABLE_QUESTION,
        bibliography=_one_source_bib(
            "study_belgium", "A field experiment conducted in Belgium found gains."
        ),
        section_claims=[_section_claim(
            "study_belgium", "A field experiment conducted in Belgium found gains"
        )],
        existing_report_md=body,
        appendix_boundary_marker="",
    )
    assert res.changed is False
    assert res.text == body  # OFF => vocab never consulted => byte-identical report


# ---------------------------------------------------------------------------
# No collision-prone abbreviations were added to the case-insensitive geo set.
# ---------------------------------------------------------------------------
def test_no_bare_two_letter_ci_geo_abbreviations_added():
    # The case-INSENSITIVE phrase set carries no bare 2-letter token (which would
    # collide with common English words like "in"/"us"); such abbreviations remain
    # in the case-SENSITIVE _GEO_ABBREV set only (US/UK/EU, unchanged).
    for phrase, _ in _GEO_PHRASES:
        assert not (len(phrase) <= 2 and phrase.isalpha()), phrase
    assert {body for body, _ in _GEO_ABBREV} == {"US", r"U\.S\.", "UK", "EU"}
