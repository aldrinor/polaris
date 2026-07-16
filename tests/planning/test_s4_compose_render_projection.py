"""S4 compose/render projection tests — offline + deterministic.

Assert the S4 compose-side acceptance (GATE_DESIGN_CONSOLIDATED §8 S4,
sol_gate_design §4 compose/render rows):

  * the contract's VOICE (tone/audience/pov/hedging) compiles into a PROSE-ONLY
    advisory string (never a fact, never a gate);
  * document_type is surfaced for skeleton selection;
  * the render plan carries required section titles IN ORDER (only exact-title-
    locked / explicit sections — a required topic is never a heading), plus the
    references-dedup-by-work policy and a length NOTE (never a cap);
  * fail-open: a None / degraded contract yields an empty projection (the caller
    keeps the byte-identical champion path);
  * no-invention: an inferred (preference) section title never becomes a required
    lock.
"""

from __future__ import annotations

from src.polaris_graph.planning.planning_gate_schema import contract_from_dict
from src.polaris_graph.planning import compose_render_projection as crp


PROMPT = (
    "Write a formal executive memo for policymakers on AI and labor. "
    "Use these sections in order: Background, Findings, Recommendations."
)


def _span(phrase: str) -> dict:
    i = PROMPT.find(phrase)
    assert i != -1, phrase
    return {"start": i, "end": i + len(phrase), "quote": phrase}


def _voice_contract():
    """A contract naming tone / audience / pov + three explicit ordered sections."""
    return contract_from_dict({
        "objective": [{
            "term_id": "objective.audience", "dimension": "objective.audience",
            "value": "policymakers", "origin": "explicit", "force": "preference",
            "spans": [_span("policymakers")],
        }],
        "deliverable": [
            {"term_id": "deliverable.kind", "dimension": "deliverable.kind",
             "value": "executive memo", "origin": "explicit", "force": "hard",
             "spans": [_span("executive memo")]},
            {"term_id": "deliverable.tone", "dimension": "deliverable.rhetoric.tone",
             "value": "formal", "origin": "explicit", "force": "preference",
             "spans": [_span("formal")]},
            {"term_id": "deliverable.pov",
             "dimension": "deliverable.rhetoric.point_of_view",
             "value": "third person", "origin": "inferred", "force": "preference"},
        ],
        "sections": [
            {"section_id": "s1", "order": 1,
             "title": {"term_id": "sec.bg", "dimension": "deliverable.section",
                       "value": "Background", "origin": "explicit", "force": "hard",
                       "spans": [_span("Background")]},
             "exact_title_lock": True},
            {"section_id": "s2", "order": 2,
             "title": {"term_id": "sec.find", "dimension": "deliverable.section",
                       "value": "Findings", "origin": "explicit", "force": "hard",
                       "spans": [_span("Findings")]},
             "exact_title_lock": True},
            {"section_id": "s3", "order": 3,
             "title": {"term_id": "sec.rec", "dimension": "deliverable.section",
                       "value": "Recommendations", "origin": "explicit",
                       "force": "hard", "spans": [_span("Recommendations")]},
             "exact_title_lock": True},
        ],
        "assumptions": [{
            "assumption_id": "a1", "statement": "pov inferred as third person",
            "affected_term_ids": ["deliverable.pov"], "origin": "inferred",
        }],
    })


def test_voice_advisory_is_prose_only_and_mentions_all_dims():
    proj = crp.from_contract(_voice_contract())
    assert proj.has_voice()
    adv = proj.voice_advisory()
    # every named voice dimension appears; the disclaimer marks it presentation-only.
    assert "policymakers" in adv
    assert "formal" in adv
    assert "third person" in adv
    assert "presentation only" in adv.lower()
    # PROSE ONLY: it must not fabricate a factual claim or a cap/threshold.
    assert "must not" not in adv.lower() or "do not add" in adv.lower()


def test_document_type_surfaced():
    proj = crp.from_contract(_voice_contract())
    assert proj.document_type() == "executive memo"
    assert proj.render_plan()["document_type"] == "executive memo"


def test_render_plan_required_titles_in_order():
    proj = crp.from_contract(_voice_contract())
    plan = proj.render_plan()
    assert plan["required_titles"] == ["Background", "Findings", "Recommendations"]
    assert plan["ordered"] is True
    assert plan["references_dedup_by_work"] is True


def test_required_topic_is_not_a_heading():
    """An inferred / non-exact-title-locked section must NOT become a required
    title (the round-1 coverage-to-heading bug the design forbids)."""
    contract = contract_from_dict({
        "sections": [
            {"section_id": "s1",
             "title": {"term_id": "t1", "dimension": "deliverable.section",
                       "value": "Some Inferred Heading", "origin": "inferred",
                       "force": "preference"},
             "exact_title_lock": True},  # claimed lock, but inferred origin
        ],
    })
    proj = crp.from_contract(contract)
    # schema downgrades an inferred exact_title_lock -> not required here.
    assert proj.render_plan()["required_titles"] == []
    assert proj.render_plan()["ordered"] is False


def test_failopen_none_and_empty():
    assert crp.from_contract(None).voice_advisory() == ""
    assert crp.from_contract(None).render_plan()["required_titles"] == []
    empty = crp.from_contract(contract_from_dict({}))
    assert empty.voice_advisory() == ""
    assert empty.has_voice() is False
    assert empty.document_type() == ""
    # the compose-side convenience entrypoint fails open on None / junk.
    assert crp.compose_voice_advisory(None) == ""
    assert crp.compose_voice_advisory(object()) == ""


def test_length_is_note_never_a_cap():
    contract = contract_from_dict({
        "deliverable": [{
            "term_id": "deliverable.length", "dimension": "deliverable.length.target",
            "value": "2000 words", "origin": "explicit", "force": "hard",
            "spans": [],  # value present; note is derived regardless
        }],
    })
    note = crp.from_contract(contract).render_plan()["length_note"]
    assert "planning context" in note.lower()
    assert "not a hard cap" in note.lower()
