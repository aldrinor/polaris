"""S4 collapse fix (Fable push-to-ceiling) — deterministic parse + title-conform coverage.

The drb_72 collapse: the user asked for 4 required workforce sections; GLM emitted an evidence-
bearing PARAPHRASED-IMRaD outline; exact-title conform stranded all 4 required plans EMPTY. These
tests exercise the deterministic (no-LLM) parse + conform + retry-message segments that fix it:

  (i)   6-section paraphrased-IMRaD outline with ev_ids -> conform yields the 4 required titles
        carrying the model's facet ev_ids (14/14/20/14); the extras drop to the pool.
  (ii)  an exact-title outline is byte-identical to today (tier-2 overlap never fires, no disclosure).
  (iii) required_sections empty -> the legacy path is unchanged (off-list drop, conform is identity).
  (iv)  a genuinely-missing facet -> the empty undersupplied plan is preserved (disclosed gap).
  (v)   the ``required_title_mismatch`` reason code is emitted when a paraphrased section is kept.
  (vi)  the targeted-retry system message names the emitted titles AND the required titles verbatim.
"""

from __future__ import annotations

import json

from src.polaris_graph.generator.multi_section_generator import (
    OutlineParseResult,
    SectionPlan,
    _conform_plans_to_required,
    _parse_outline,
    _targeted_retry_system_message,
)

# The real drb_72 required sections (outputs/s4_hamster_i2/bank_plan.json deliverable).
_REQUIRED = [
    "Positive Views on Generative AI's Impact on Employment",
    "Negative Views on Generative AI's Impact on Employment",
    "Specific Challenges of Generative AI in the Labor Market",
    "Future Opportunities from Generative AI for Employment",
]


def _ids(prefix: str, n: int) -> list[str]:
    return [f"{prefix}{i}" for i in range(n)]


def _paraphrased_imrad_outline() -> tuple[str, set[str]]:
    """A 6-section paraphrased-IMRaD outline: 4 facet sections (14/14/20/14 ev_ids) under RENAMED
    headings whose ``focus`` carries the distinctive facet words, plus 2 evidence-bearing extras
    (Background / Limitations) that carry NO distinctive facet word. Returns (raw_json, allowed_ids)."""
    pos, neg, chal, opp = _ids("p", 14), _ids("n", 14), _ids("c", 20), _ids("o", 14)
    bg, lim = _ids("bg", 3), _ids("lim", 3)
    sections = [
        {"title": "Introduction and Optimistic Outlook",
         "focus": "Positive views and optimistic outlook on how generative AI augments jobs",
         "ev_ids": pos},
        {"title": "Adverse Effects and Displacement Risks",
         "focus": "Negative views on displacement and adverse effects of generative AI on jobs",
         "ev_ids": neg},
        {"title": "Implementation Barriers",
         "focus": "Specific challenges and barriers of generative AI in the labor market",
         "ev_ids": chal},
        {"title": "Forward-Looking Prospects",
         "focus": "Future opportunities and prospects generative AI creates for employment",
         "ev_ids": opp},
        {"title": "Background",
         "focus": "General context of the study and prior surveys",
         "ev_ids": bg},
        {"title": "Limitations",
         "focus": "Study caveats and methodological notes",
         "ev_ids": lim},
    ]
    allowed = {e for s in sections for e in s["ev_ids"]}
    return json.dumps({"sections": sections}), allowed


# ── (i) the exact repro: paraphrased outline conforms to the 4 required facets ──────────────────
def test_paraphrased_imrad_conforms_to_required_facets() -> None:
    raw, allowed = _paraphrased_imrad_outline()
    res = _parse_outline(
        raw, allowed_ev_ids=allowed, allowed_sections=_REQUIRED, required_sections=_REQUIRED,
    )
    # collapse fix 1(a): every evidence-bearing paraphrased section is KEPT (not dropped), so all 6
    # survive the parse and the mismatch is disclosed in the reason codes.
    assert len(res.plans) == 6
    assert any(c.startswith("required_title_mismatch:") for c in res.reason_codes)

    disclosure: list = []
    conformed = _conform_plans_to_required(res.plans, _REQUIRED, disclosure=disclosure)

    # collapse fix 1(b): the 4 required titles, in order, each carrying the model's facet ev_ids.
    assert [p.title for p in conformed] == _REQUIRED
    assert [len(p.ev_ids) for p in conformed] == [14, 14, 20, 14]
    assert all(not p.undersupplied for p in conformed)

    # disclosure records exactly the 4 overlap re-maps (§-1.3 disclosed, never silent).
    assert len(disclosure) == 4
    assert {d["required"] for d in disclosure} == set(_REQUIRED)
    assert all(d["score"] >= 1 and d["from_title"] for d in disclosure)

    # the 2 non-required extras drop from the outline; their evidence is NOT re-homed here.
    kept_ev = {e for p in conformed for e in p.ev_ids}
    for extra in _ids("bg", 3) + _ids("lim", 3):
        assert extra not in kept_ev


# ── (ii) exact-title outline -> byte-identical (no tier-2 overlap, no disclosure) ────────────────
def test_exact_title_outline_is_byte_identical() -> None:
    sections = [
        {"title": _REQUIRED[0], "focus": "positive", "ev_ids": _ids("p", 5)},
        {"title": _REQUIRED[1], "focus": "negative", "ev_ids": _ids("n", 5)},
        {"title": _REQUIRED[2], "focus": "challenges", "ev_ids": _ids("c", 5)},
        {"title": _REQUIRED[3], "focus": "opportunities", "ev_ids": _ids("o", 5)},
    ]
    allowed = {e for s in sections for e in s["ev_ids"]}
    raw = json.dumps({"sections": sections})
    res = _parse_outline(
        raw, allowed_ev_ids=allowed, allowed_sections=_REQUIRED, required_sections=_REQUIRED,
    )
    # no paraphrase kept -> no mismatch reason code
    assert not any(c.startswith("required_title_mismatch:") for c in res.reason_codes)

    disclosure: list = []
    conformed = _conform_plans_to_required(res.plans, _REQUIRED, disclosure=disclosure)
    assert [p.title for p in conformed] == _REQUIRED
    assert [len(p.ev_ids) for p in conformed] == [5, 5, 5, 5]
    # exact-match path records ZERO overlap re-maps (byte-identical to the pre-1(b) behaviour)
    assert disclosure == []


# ── (iii) required_sections empty -> legacy path unchanged ──────────────────────────────────────
def test_required_empty_is_legacy_unchanged() -> None:
    # conform with no required sections returns the input list unchanged (identity)
    plans = [SectionPlan(title="Efficacy", focus="f", ev_ids=["e1", "e2"])]
    assert _conform_plans_to_required(plans, []) is plans

    # parse with required empty keeps the legacy allow-list drop (off-list title dropped) and emits
    # NO required_title_mismatch reason code.
    raw = json.dumps({"sections": [
        {"title": "Efficacy", "focus": "f", "ev_ids": ["e1", "e2"]},
        {"title": "Bananas", "focus": "f", "ev_ids": ["e3", "e4"]},
        {"title": "Safety", "focus": "f", "ev_ids": ["e5", "e6"]},
    ]})
    res = _parse_outline(raw, allowed_ev_ids={"e1", "e2", "e3", "e4", "e5", "e6"})
    titles = [p.title for p in res.plans]
    assert "Bananas" not in titles
    assert "Efficacy" in titles and "Safety" in titles
    assert not any(c.startswith("required_title_mismatch:") for c in res.reason_codes)


# ── (iv) genuinely-missing facet -> empty undersupplied plan preserved ───────────────────────────
def test_missing_facet_yields_empty_undersupplied_plan() -> None:
    # only 3 facets present; NO section carries future/opportunities words -> req[3] cannot map.
    sections = [
        {"title": "Optimistic Outlook",
         "focus": "Positive views on generative AI augmenting jobs", "ev_ids": _ids("p", 6)},
        {"title": "Displacement Risks",
         "focus": "Negative views on generative AI displacing jobs", "ev_ids": _ids("n", 6)},
        {"title": "Implementation Barriers",
         "focus": "Specific challenges in the labor market", "ev_ids": _ids("c", 6)},
    ]
    allowed = {e for s in sections for e in s["ev_ids"]}
    raw = json.dumps({"sections": sections})
    res = _parse_outline(
        raw, allowed_ev_ids=allowed, allowed_sections=_REQUIRED, required_sections=_REQUIRED,
    )
    disclosure: list = []
    conformed = _conform_plans_to_required(res.plans, _REQUIRED, disclosure=disclosure)
    assert [p.title for p in conformed] == _REQUIRED
    # first 3 mapped; the 4th (Future Opportunities) is an EMPTY undersupplied disclosed gap.
    assert conformed[3].title == _REQUIRED[3]
    assert conformed[3].ev_ids == []
    assert conformed[3].undersupplied is True
    assert len(disclosure) == 3
    assert _REQUIRED[3] not in {d["required"] for d in disclosure}


# ── (v) required_title_mismatch reason code emitted ─────────────────────────────────────────────
def test_required_title_mismatch_reason_code_emitted() -> None:
    raw, allowed = _paraphrased_imrad_outline()
    res = _parse_outline(
        raw, allowed_ev_ids=allowed, allowed_sections=_REQUIRED, required_sections=_REQUIRED,
    )
    mismatches = [c for c in res.reason_codes if c.startswith("required_title_mismatch:")]
    # one per paraphrased emitted title (all 6 titles are non-required here)
    assert len(mismatches) == 6
    assert "required_title_mismatch:introduction and optimistic outlook" in res.reason_codes


# ── (vi) targeted-retry message names emitted + required titles verbatim ─────────────────────────
def test_targeted_retry_message_lists_required_titles_verbatim() -> None:
    emitted = ["Introduction and Optimistic Outlook", "Adverse Effects and Displacement Risks"]
    msg = _targeted_retry_system_message("BASE_SYSTEM", emitted, _REQUIRED, {"ev1", "ev2"})
    # names the model's own emitted titles
    for t in emitted:
        assert t in msg
    # each required title appears character-for-character, in order
    for t in _REQUIRED:
        assert t in msg
    assert "CHARACTER-FOR-CHARACTER" in msg
    # P1-2: the allowed pool is NO LONGER enumerated — a sorted[:100] slice forbade most of a >100-row
    # pool, contradicting the KEEP-your-assignments demand. The model is told to use only ev_ids from
    # the evidence menu; validation enforces the pool deterministically after the answer.
    assert "ev1" not in msg  # allowed-id set is NOT enumerated
    assert "appear in the evidence menu" in msg
    # ordering: required titles appear after the "REQUIRES EXACTLY" demand
    demand_idx = msg.index("REQUIRES EXACTLY")
    assert all(msg.index(t) > demand_idx for t in _REQUIRED)
