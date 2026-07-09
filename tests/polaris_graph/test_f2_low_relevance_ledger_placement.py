"""I-deepfix-001 F2 (#1371) — body-placement screen + Low-relevance ledger partition.

Fable's F2 fix: grounded-but-junk lines (page furniture that renders as a coherent
sentence, or an on-topic-looking sentence actually off the research question's topic)
self-entail their verbatim span, PASS the frozen strict_verify gate, and survive into
the raw carry-up surfaces (Verified Findings / Abstract / Key Findings / Conclusion /
Evidence base / CWF facet sections) — which had a FORM-chrome screen but NO topicality
screen. The fix makes body PLACEMENT respect the weight already computed: a furniture /
off-topic / judged-below-floor unit is MOVED BELOW the appendix boundary into a labelled
"Low-relevance evidence (kept at weight)" ledger. §-1.3 PLACEMENT, NEVER a drop — every
source stays in the pool, the bibliography, and the disclosure.

Two behavioral tests (both OFFLINE — no network / no GPU / no LLM; the frozen
faithfulness engine is untouched):

  (a) The unified placement predicate FLAGS the eight verbatim box2 junk lines (five
      FORM-chrome, three off-topic prose) and does NOT flag eight genuine on-topic
      finding lines carried verbatim from the drb_72 report.

  (b) A synthetic section: rows with judged relevance labels partition so the
      below-floor / furniture / confirmed-off rows land in the ledger (BELOW the
      appendix boundary, ABSENT from body prose) while STILL present in the union
      (bibliography / disclosure) — weight-not-filter proof that nothing is dropped.
"""
from __future__ import annotations

import pytest

from src.polaris_graph.generator import weighted_enrichment as we

# The verbatim drb_72 research question (first line of the shipped report). Its verbose
# report-instruction scaffolding ("comprehensive research report … credible sources …
# with columns …") is exactly why the off-topic prose lines below escaped a naive
# question-overlap screen — the placement reference strips that scaffolding.
_RESEARCH_QUESTION = (
    "Research report: I am researching the impact of Generative AI on the future labor "
    "market. Please write a comprehensive research report drawing on the most relevant "
    "and credible evidence available, with no restriction on publication date or source "
    "type, summarizing the positive views, negative views, specific challenges, and "
    "future opportunities regarding Generative AI's impact on employment. Structure the "
    "report with the four aspects (positive, negative, challenges, opportunities) as "
    "separate sections, and provide specific sources to support each point. End with a "
    "summary table detailing specific application cases of Generative AI in particular "
    "industries or occupations, the main impacts, and key risk points, with columns: "
    "Research Literature, Country/Region, Application Area/Occupation, Specific "
    "Applications and Impacts, and Key Risks and Limitations."
)

# ── Eight verbatim JUNK lines (Fable F2 spec) — each MUST be flagged for placement. ──
# Five are FORM-chrome (grant/ack back-matter, cookie-consent, media-player furniture,
# paywall unlock code, US-gov site banner + Crossref widget); three are grammatical
# OFF-TOPIC prose foreign to the Generative-AI-labor question (Slovak ethnology, an EU
# digitisation project, a Covid-corruption title fragment).
_JUNK_LINES = [
    # off-topic prose (Slovak ethnology)
    "Separately, a publication presents the first volume of the series Vyzvy a "
    "smerovania slovenskej etnologie a antropologie, and the book brings a comprehensive "
    "and theoretically grounded analysis of contemporary social and cultural issues.",
    # off-topic prose (EU digitisation project)
    "The Commission funded projects including TranScriptorium, which ran from 2013 to "
    "2015 with a budget of 2.4m as a consortium led by the Universitat Politecnica de "
    "Valencia.",
    # FORM-chrome: grant / corresponding-author back-matter
    "Council of Canada under Grant 435-2022-0296. (Corresponding author: Heather A.",
    # FORM-chrome: cookie-consent notice
    "A cookie called MGX_UC has a duration of 1 year and does not store any identifiable "
    "data.",
    # FORM-chrome: media-player reader furniture
    "A live stream with a 1x playback rate includes chapters and descriptions.",
    # FORM-chrome: paywall unlock-code token
    "An article on artificial intelligence in the workplace is accessible with an "
    "unlocked article code of 1.9Ew.v2lW.2L7jNgqGF9__.",
    # off-topic title fragment
    "Covid and Corruption-A Link.",
    # FORM-chrome: US-gov site banner + Crossref citation-count widget
    "An official website of the United States government Crossref 0 Crossref 0",
]

# ── Eight genuine ON-TOPIC finding lines carried verbatim from the drb_72 report. ──
# Each MUST NOT be flagged (they are the report's real Generative-AI-labor evidence).
_REAL_LINES = [
    # Acemoglu & Restrepo (JPE 2020) — robot exposure wage/employment effect
    "The estimated effect indicated that one more robot per thousand workers reduces the "
    "employment-to-population ratio by 0.2 percentage points and wages by 0.42%.",
    # Brynjolfsson et al. (QJE 2025) — 5,172-agent generative-AI field study
    "We study the staggered introduction of a generative AI–based conversational "
    "assistant using data from 5,172 customer-support agents.",
    # Eloundou et al. — LLM task-exposure estimate 1.8% -> 46%
    "Eloundou et al. estimated that roughly 1.8% of jobs could have over half their tasks "
    "affected by LLMs with simple interfaces and general training, but when accounting "
    "for current and likely future complementary software developments, this share rises "
    "to just over 46% of jobs.",
    # Goldman Sachs-style productivity projection
    "Generative AI could increase U.S. labor productivity by 0.5 to 0.9 percentage points "
    "annually through 2030.",
    # Acemoglu & Restrepo (JEP 2019) — displacement effect
    "Automation, which enables capital to replace labor in tasks it was previously "
    "engaged in, shifts the task content of production against labor because of a "
    "displacement effect.",
    # Acemoglu & Restrepo (JEP 2019) — reinstatement effect
    "The introduction of new tasks changes the task content of production in favor of "
    "labor because of a reinstatement effect, and always raises the labor share and labor "
    "demand.",
    # Frey & Osborne (TFSC 2017) — 702-occupation computerisation methodology
    "To assess this, we begin by implementing a novel methodology to estimate the "
    "probability of computerisation for 702 detailed occupations, using a Gaussian "
    "process classifier.",
    # Stanford Digital Economy Lab — young-worker AI-exposure employment decline
    "A Stanford Digital Economy Lab study found that workers ages 22–25 in AI-exposed "
    "occupations experienced 16% relative employment declines, controlling for firm-level "
    "characteristics.",
]


@pytest.fixture(autouse=True)
def _default_on_flags(monkeypatch):
    """The F2 screens are default-ON; pin the kill-switches ON so the test is stable even
    if the ambient environment turned one off."""
    monkeypatch.setenv("PG_RENDER_CHROME_SCREEN", "1")
    monkeypatch.setenv("PG_SOURCE_FURNITURE_CHROME", "1")
    monkeypatch.setenv("PG_LOW_RELEVANCE_LEDGER", "1")
    monkeypatch.delenv("PG_RELEVANCE_FLOOR", raising=False)  # default 0.30


# ─────────────────────────────────────────────────────────────────────────────
# Test (a): the unified placement predicate flags junk, keeps real findings.
# ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("line", _JUNK_LINES, ids=[f"junk{i}" for i in range(len(_JUNK_LINES))])
def test_junk_line_flagged_for_placement(line):
    assert we.is_offtopic_or_chrome_for_placement(
        line, research_question=_RESEARCH_QUESTION
    ) is True, f"junk line NOT flagged: {line!r}"


@pytest.mark.parametrize("line", _REAL_LINES, ids=[f"real{i}" for i in range(len(_REAL_LINES))])
def test_real_finding_not_flagged_for_placement(line):
    assert we.is_offtopic_or_chrome_for_placement(
        line, research_question=_RESEARCH_QUESTION
    ) is False, f"real on-topic finding WRONGLY flagged: {line!r}"


def test_placement_predicate_partitions_the_16_lines_cleanly():
    """The whole fixture at once: all eight junk flagged, none of the eight real flagged."""
    junk = [
        we.is_offtopic_or_chrome_for_placement(x, research_question=_RESEARCH_QUESTION)
        for x in _JUNK_LINES
    ]
    real = [
        we.is_offtopic_or_chrome_for_placement(x, research_question=_RESEARCH_QUESTION)
        for x in _REAL_LINES
    ]
    assert all(junk), f"some junk NOT flagged: {junk}"
    assert not any(real), f"some real finding flagged: {real}"


def test_empty_question_fails_open_for_topicality_leg():
    """No research question => the topicality leg is inert (byte-identical legacy): an
    off-topic prose line is NOT demoted (only FORM-chrome still fires)."""
    slovak = _JUNK_LINES[0]
    assert we.is_offtopic_or_chrome_for_placement(slovak, research_question="") is False
    # a FORM-chrome line still fires with no question (it is form, not topic)
    cookie = _JUNK_LINES[3]
    assert we.is_offtopic_or_chrome_for_placement(cookie, research_question="") is True


def test_chrome_screen_killswitch_off_disables_new_furniture(monkeypatch):
    """PG_RENDER_CHROME_SCREEN=0 => the NEW F2 furniture legs are inert (the base screen
    is byte-identical to legacy). A cookie-consent line is no longer FORM-flagged."""
    monkeypatch.setenv("PG_RENDER_CHROME_SCREEN", "0")
    cookie = _JUNK_LINES[3]
    # with the render-chrome screen OFF and no research question, nothing demotes it
    assert we.is_offtopic_or_chrome_for_placement(cookie, research_question="") is False


# ─────────────────────────────────────────────────────────────────────────────
# Test (b): the ledger partition routes below-floor / furniture / off rows below the
# appendix boundary while conserving every row (nothing dropped).
# ─────────────────────────────────────────────────────────────────────────────
def _synthetic_rows():
    """Rows with judged relevance labels + one furniture + one unjudged off-topic row."""
    return [
        # judged RELEVANT (positive label, high score) => BODY
        {
            "evidence_id": "A",
            "content_relevance_label": "relevant",
            "selection_relevance": 0.90,
            "weight_mass": 0.80,
            "statement": "Generative AI raised labor productivity and reshaped employment "
                         "across occupations.",
        },
        # judged escalated_relevant (positive) => BODY (positive-relevance-always-keeps)
        {
            "evidence_id": "B",
            "content_relevance_label": "escalated_relevant",
            "selection_relevance": 0.55,
            "weight_mass": 0.60,
            "statement": "Automation shifts labor demand within the market.",
        },
        # judged BELOW-FLOOR numeric relevance, no label => LEDGER (placement, not a drop)
        {
            "evidence_id": "C",
            "selection_relevance": 0.05,
            "weight_mass": 0.40,
            "statement": "The Commission funded the TranScriptorium consortium led by the "
                         "Universitat Politecnica de Valencia.",
        },
        # judged CONFIRMED-OFF label (even with a high score) => LEDGER
        {
            "evidence_id": "D",
            "content_relevance_label": "demoted",
            "selection_relevance": 0.70,
            "weight_mass": 0.50,
            "statement": "A study of Russian cosmetics market trends and consumer prices.",
        },
        # FURNITURE (grounded-but-junk cookie line) => LEDGER regardless of judgment
        {
            "evidence_id": "E",
            "weight_mass": 0.30,
            "statement": "A cookie called MGX_UC has a duration of 1 year and does not "
                         "store any identifiable data.",
        },
        # UNJUDGED off-topic prose => LEDGER via the lexical fallback
        {
            "evidence_id": "F",
            "weight_mass": 0.20,
            "statement": "Separately, a publication presents the first volume of the "
                         "series slovenskej etnologie and the book brings a grounded "
                         "analysis of contemporary cultural issues.",
        },
    ]


def test_ledger_partition_routes_below_floor_and_furniture_below_appendix():
    rows = _synthetic_rows()
    body, ledger = we.partition_body_and_low_relevance_ledger(
        rows, research_question=_RESEARCH_QUESTION
    )
    body_ids = [r["evidence_id"] for r in body]
    ledger_ids = [r["evidence_id"] for r in ledger]

    # judged-relevant rows stay in the body prose
    assert "A" in body_ids and "B" in body_ids
    # below-floor / confirmed-off / furniture / unjudged-off rows are demoted to the ledger
    for eid in ("C", "D", "E", "F"):
        assert eid in ledger_ids, f"{eid} not routed to the low-relevance ledger"
    # a ledger row is ABSENT from the body prose
    assert not (set(ledger_ids) & set(body_ids))
    # WEIGHT-NOT-FILTER: nothing dropped — every row survives in body ∪ ledger
    assert set(body_ids) | set(ledger_ids) == {"A", "B", "C", "D", "E", "F"}
    assert len(body) + len(ledger) == len(rows)


def test_ledger_orders_each_partition_by_weight_times_relevance_desc():
    rows = _synthetic_rows()
    _body, ledger = we.partition_body_and_low_relevance_ledger(
        rows, research_question=_RESEARCH_QUESTION
    )
    # D (0.50*0.70=0.35) outranks C (0.40*0.05=0.02); the unjudged E/F (sentinel relevance
    # => weight*0) trail. The ledger is ordered, not filtered.
    ledger_ids = [r["evidence_id"] for r in ledger]
    assert ledger_ids.index("D") < ledger_ids.index("C")
    assert ledger_ids.index("C") < ledger_ids.index("E")
    assert ledger_ids.index("C") < ledger_ids.index("F")


def test_ledger_killswitch_off_keeps_every_row_in_body():
    """PG_LOW_RELEVANCE_LEDGER=0 => byte-identical legacy: every row stays in the body,
    the ledger is empty (no placement change at all)."""
    import os

    prev = os.environ.get("PG_LOW_RELEVANCE_LEDGER")
    os.environ["PG_LOW_RELEVANCE_LEDGER"] = "0"
    try:
        rows = _synthetic_rows()
        body, ledger = we.partition_body_and_low_relevance_ledger(
            rows, research_question=_RESEARCH_QUESTION
        )
        assert ledger == []
        assert [r["evidence_id"] for r in body] == [r["evidence_id"] for r in rows]
    finally:
        if prev is None:
            os.environ.pop("PG_LOW_RELEVANCE_LEDGER", None)
        else:
            os.environ["PG_LOW_RELEVANCE_LEDGER"] = prev


# ─────────────────────────────────────────────────────────────────────────────
# Test (c): END-TO-END render — the off-topic grammatical span is MOVED below the
# appendix boundary into a real "Low-relevance evidence (kept at weight)" SECTION
# while the on-topic span renders in the "Evidence base" section above it. Both go
# through the SAME frozen strict_verify path (entailment forced OFF => deterministic
# mechanical checks only; a verbatim self-quote passes by construction).
# ─────────────────────────────────────────────────────────────────────────────
_ONTOPIC_SPAN = (
    "Generative AI raised labor productivity across employment sectors and many "
    "occupations in the observed firms."
)
_OFFTOPIC_SPAN = (
    "The Slovak ethnology monograph series presents a grounded scholarly analysis of "
    "contemporary cultural heritage and folklore traditions."
)


def _ontopic_offtopic_pool():
    return {
        "ev_on": {
            "direct_quote": _ONTOPIC_SPAN,
            "source_url": "https://journal.example/ai-labor",
            "source_tier": "T1",
        },
        # unjudged (no selection_relevance / label) => lexical fallback routes it to the ledger
        "ev_off": {
            "direct_quote": _OFFTOPIC_SPAN,
            "source_url": "https://ethnology.example/slovak",
            "source_tier": "T3",
        },
    }


def test_evidence_base_id_split_separates_ontopic_from_offtopic():
    pool = _ontopic_offtopic_pool()
    body, ledger = we.partition_evidence_base_ids_for_ledger(
        ["ev_on", "ev_off"], pool, research_question=_RESEARCH_QUESTION
    )
    assert body == ["ev_on"]
    assert ledger == ["ev_off"]


def test_ledger_section_renders_below_evidence_base(monkeypatch):
    """The render wiring: an on-topic span renders in 'Evidence base'; the off-topic span is MOVED into
    a 'Low-relevance evidence (kept at weight)' section AFTER it, and is ABSENT from the Evidence base
    body. Both sections carry real strict_verify SentenceVerification objects (no bypass)."""
    from src.polaris_graph.generator import multi_section_generator as msg
    from src.polaris_graph.generator.weighted_enrichment import (
        _LOW_RELEVANCE_LEDGER_TITLE,
    )

    monkeypatch.setenv("PG_BREADTH_EVIDENCE_BASE_SECTION", "1")
    monkeypatch.setenv("PG_LOW_RELEVANCE_LEDGER", "1")
    monkeypatch.setenv("PG_STRICT_VERIFY_ENTAILMENT", "off")  # deterministic mechanical checks only
    pool = _ontopic_offtopic_pool()

    body_ids, ledger_ids = we.partition_evidence_base_ids_for_ledger(
        ["ev_on", "ev_off"], pool, research_question=_RESEARCH_QUESTION
    )
    assert ledger_ids == ["ev_off"], "the off-topic span must route to the ledger"

    section_results: list = []
    global_biblio: list = []
    # mirror the multi_section_generator call site: Evidence base (body) THEN ledger (below)
    appended_body = msg._append_evidence_base_section(
        section_results, global_biblio, body_ids, pool, research_question=_RESEARCH_QUESTION
    )
    appended_ledger = msg._append_evidence_base_section(
        section_results, global_biblio, ledger_ids, pool,
        research_question=_RESEARCH_QUESTION,
        section_title=_LOW_RELEVANCE_LEDGER_TITLE,
        section_focus="ledger",
    )

    assert appended_body is True
    assert appended_ledger is True, "the off-topic span must still render (kept at weight, not dropped)"
    titles = [s.title for s in section_results]
    assert titles == ["Evidence base", _LOW_RELEVANCE_LEDGER_TITLE], titles

    eb = section_results[0]
    ledger = section_results[1]
    # the on-topic finding is in the Evidence base body; the off-topic one is NOT
    assert "labor productivity" in eb.verified_text
    assert "ethnology" not in eb.verified_text
    # the off-topic finding is present in the ledger section BELOW the appendix boundary
    assert "ethnology" in ledger.verified_text
    # PLACEMENT proof: the off-topic source is in the global bibliography (kept, never dropped)
    assert any(b.get("evidence_id") == "ev_off" for b in global_biblio)
    # NO bypass: the ledger entry carries real strict_verify SentenceVerification objects for D8
    assert ledger.kept_sentences_pre_resolve


def test_assembly_call_site_is_wired_to_the_ledger():
    """A future un-wiring FAILS: the multi_section assembly must split the Evidence base surface and
    append the ledger section."""
    import inspect

    from src.polaris_graph.generator import multi_section_generator as msg

    src = inspect.getsource(msg)
    assert "partition_evidence_base_ids_for_ledger" in src
    assert "_LOW_RELEVANCE_LEDGER_TITLE" in src


def test_evidence_base_id_partition_preserves_order_and_conserves():
    """The order-preserving ev-id split used by the render wiring: pool-resolved furniture /
    off-topic / below-floor ids route to the ledger; a pool-absent id stays in body; the
    incoming order is preserved within each partition; conservation holds."""
    pool = {r["evidence_id"]: r for r in _synthetic_rows()}
    ev_ids = ["A", "B", "C", "D", "E", "F", "Z"]  # Z is pool-absent
    body, ledger = we.partition_evidence_base_ids_for_ledger(
        ev_ids, pool, research_question=_RESEARCH_QUESTION
    )
    assert "A" in body and "B" in body
    assert "Z" in body  # pool-absent id left in body (render skips it as before)
    for eid in ("C", "D", "E", "F"):
        assert eid in ledger
    # order preserved within each partition (body keeps A,B,Z order; ledger keeps C,D,E,F)
    assert body == [e for e in ev_ids if e in body]
    assert ledger == [e for e in ev_ids if e in ledger]
    # conservation: nothing dropped, none duplicated
    assert set(body) | set(ledger) == set(ev_ids)
    assert not (set(body) & set(ledger))


# ─────────────────────────────────────────────────────────────────────────────
# Test (d): F2 gate iter-6 — the split is COUPLED to the render gate. The ledger
# partition renders ONLY through build_evidence_base_section, which is gated by
# PG_BREADTH_EVIDENCE_BASE_SECTION. When that flag is OFF the ledger section cannot
# render, so routing rows into it (while the CWF body-feed consumes only the body
# partition) would make those rows vanish from the report prose AND the bibliography
# — a §-1.3 DROP. The split must return (full-surface, []) so the move-half never
# fires without the place-half.
# ─────────────────────────────────────────────────────────────────────────────
def test_split_couples_to_render_gate_no_drop_when_eb_section_off(monkeypatch):
    """PG_BREADTH_EVIDENCE_BASE_SECTION=0 (ledger cannot render) + PG_LOW_RELEVANCE_LEDGER=1
    (default ON): the split returns (full-surface, []) so NO source is stripped into a section
    that never renders. Guards the decoupled-flag placement-becomes-DROP the F2 gate flagged."""
    monkeypatch.setenv("PG_LOW_RELEVANCE_LEDGER", "1")
    monkeypatch.setenv("PG_BREADTH_EVIDENCE_BASE_SECTION", "0")
    pool = {r["evidence_id"]: r for r in _synthetic_rows()}
    ev_ids = ["A", "B", "C", "D", "E", "F"]
    body, ledger = we.partition_evidence_base_ids_for_ledger(
        ev_ids, pool, research_question=_RESEARCH_QUESTION
    )
    # every row stays in the body (fed to CWF); nothing routed to the non-rendering ledger
    assert ledger == [], "no row may route to a ledger section that cannot render (would DROP it)"
    assert body == ev_ids, "EB section OFF => body = full surface, byte-identical legacy order"


def test_split_fires_when_both_flags_on(monkeypatch):
    """Positive control: with BOTH PG_LOW_RELEVANCE_LEDGER=1 and PG_BREADTH_EVIDENCE_BASE_SECTION=1
    the split routes furniture / off-topic / below-floor rows to the ledger (which renders)."""
    monkeypatch.setenv("PG_LOW_RELEVANCE_LEDGER", "1")
    monkeypatch.setenv("PG_BREADTH_EVIDENCE_BASE_SECTION", "1")
    pool = {r["evidence_id"]: r for r in _synthetic_rows()}
    body, ledger = we.partition_evidence_base_ids_for_ledger(
        ["A", "B", "C", "D", "E", "F"], pool, research_question=_RESEARCH_QUESTION
    )
    assert "A" in body and "B" in body
    for eid in ("C", "D", "E", "F"):
        assert eid in ledger, f"{eid} must route to the ledger when both flags are ON"


def test_moved_log_gated_on_ledger_append_return():
    """F2 gate iter-6 (P1-adjunct): the 'MOVED below the appendix boundary' placement log is emitted
    ONLY after the ledger _append_evidence_base_section returns True — never on `if _eb_ledger_ids:`
    alone (which mis-logs a no-op ledger append as a successful placement). A future regression that
    un-gates the log FAILS here."""
    import inspect

    from src.polaris_graph.generator import multi_section_generator as msg

    src = inspect.getsource(msg)
    assert "_eb_ledger_appended = _append_evidence_base_section(" in src, (
        "the ledger append return must be captured, not discarded"
    )
    assert "if _eb_ledger_appended:" in src, (
        "the MOVED placement log must be guarded by the ledger append return value"
    )
