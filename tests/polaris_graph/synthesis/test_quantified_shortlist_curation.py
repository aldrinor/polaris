"""U27 (#1344) — quantified-spec Writer shortlist curation.

BUG (drb_78 / drb_76 / drb_90 clinical class): the quantified trade-off analysis is
ENABLED but silently no-ops with ``firing_status=no_spec_returned`` even though 1358-2505
numbers were extracted and 0 were modeled. Root cause: the Writer (the only billed step)
received the FIRST N extracted datapoints in raw evidence-pool ITERATION ORDER
(``_sourced[:40]`` in run_honest_sweep_r3.py). On real large clinical corpora the LEADING
datapoints are scrape chrome / binary garbage — PDF object offsets ("%PDF- 13 0 obj"),
base64 auth blobs, CDN image dimensions ("382x200px" parsed as 204669%), and phone numbers
("tel:080 4669 4311") — so the Writer was handed an incoherent, absurd-valued set and
correctly returned {"model_id":"none"} -> no_spec_returned, while many clean modelable
clinical numbers (2.5% infections, carbidopa 99%, levodopa AUC +55%, half-life 1.5h) sat
buried deeper in the list.

FIX: curate the shortlist (``select_writer_candidate_numbers`` /
``is_junk_modelable_datapoint``) so clean, well-labeled, plausibly-valued datapoints reach
the spec LLM instead of raw iteration-order junk. INPUT HYGIENE only — the FULL pool still
flows to ``build_quantified_spec`` for datapoint matching, and every faithfulness gate
(strict_verify / Regime C / provenance) is untouched. If EVERY extracted number is junk, the
section surfaces a DISTINCT honest ``no_modelable_numbers`` status (disclosed) rather than the
ambiguous silent ``no_spec_returned``.

RED (pre-fix): the helpers do not exist (ImportError at collection) AND the legacy raw
``sourced[:limit]`` slice surfaces junk. GREEN (post-fix): the curated shortlist contains
every clean datapoint and ZERO junk, deterministically; the kill-switch reverts byte-identical.

SPEND-FREE / offline: no LLM, no network, no GPU. The fixture mirrors the exact drb_78 junk
shapes reproduced from the banked evidence pool; a bonus behavioral check runs over the real
banked corpus when it is present (skipped-not-faked when absent, LAW II).
"""
from __future__ import annotations

import asyncio
import os

import src.polaris_graph.generator.quantified_analysis as qa
from src.polaris_graph.generator.quantified_analysis import (
    QUANTIFIED_STATUS_DECLINED_NO_SPEC,
    is_junk_modelable_datapoint,
    run_quantified_section,
    select_writer_candidate_numbers,
)
from src.polaris_graph.tools.evidence_extractor import extract_numbers_from_evidence


# ── datapoint builder (mirrors evidence_extractor.extract_numbers_from_evidence shape) ──
def _dp(label, value, unit, context, ev_id="ev_x", data_type="percentage"):
    return {
        "data_type": data_type, "label": label, "value": str(value), "unit": unit,
        "year": "2024", "context": context, "evidence_id": ev_id,
        "source_url": "", "source_title": "",
    }


# ── CLEAN clinical datapoints (real drb_78 shapes — must ALL survive curation) ──
def _clean_datapoints():
    return [
        _dp("Had infections requiring system removal", "2.5", "%",
            "no permanent deficit. In follow-up, 2.5% had infections requiring system rem"),
        _dp("Infections requiring implantable pulse generator removal", "3.7", "%",
            "had infections requiring system removal, 3.7% had infections requiring implantabl"),
        _dp("Had misplaced leads", "12.5", "%",
            "removal, 12.5% had misplaced leads, and 26.2% had hardware complications"),
        _dp("Had hardware complications", "26.2", "%",
            "12.5% had misplaced leads, and 26.2% had hardware complications including"),
        _dp("Bioavailability of carbidopa from SINEMET tablets", "99", "%",
            "carbidopa from SINEMET tablets is approximately 99% relative to the concomitant"),
        _dp("Systemic exposure AUC of levodopa was increased", "55", "%",
            "exposure (AUC) of levodopa was increased by 55% in elderly subjects compared"),
        _dp("AUC of levodopa was increased in elderly patients", "28", "%",
            "AUC of levodopa was increased by 28% in elderly patients (>= 65 yr) compared"),
        _dp("The half-life of levodopa is increased to about", "1.5", "hours",
            "half-life of levodopa is increased to about 1.5 hours. At steady state",
            data_type="measurement"),
        _dp("Neurologic and surgical evaluations for an average", "17", "months",
            "surgical evaluations for an average of 17 months, ranging from 1 to 54 months",
            data_type="measurement"),
        _dp("Required to produce a given response by about", "75", "%",
            "produce a given response by about 75% and, when administered with levodopa"),
    ]


# ── JUNK datapoints (real drb_78 chrome/binary shapes — must ALL be dropped) ──
def _junk_datapoints():
    return [
        # PDF binary object offsets + replacement chars
        _dp("%PDF- ���� 13 0 obj <>>>/BBox[0 0 612 792]/Length", "1.5",
            "%", "%PDF-1.5\n%����\n13 0 obj\n<>>>/BBox[0 0 612 792]/Len"),
        # markdown image + tracking URL
        _dp("With instructions to retrieve your username ![Image", "2.0", "",
            "ng.com/action/0?ti=134596254&tm=al001&Ver=2&mid=12c55860-68e2", data_type="quantity"),
        # base64 auth blob as label
        _dp("eyJvYXV0aCI6eyJjbGllbnRfaWQiOiJjbGllbnQtY2hkcnR4NyJ9fQ", "80", "%",
            "Road, Bengaluru [080 4669 4311](tel:080%204669%204311) * ![Image 5: LBN-I-38"),
        # CDN image dimensions parsed as an absurd percentage
        _dp("Image 382x200px](https://cdn-assets-eu.frontify.co", "204669", "%",
            "Road, Bengaluru [080 4669 4311](tel:080%204669%204311) * ![Image 5: LBN-I-382 x"),
        _dp("LBN-I-382 x 200](https://cdn-assets-eu.frontify.co", "82972", "%",
            "LB Nagar, Hyderabad [082972 22222](tel:082972%2022222) * ![Image 6: LKP-I-382 x"),
        _dp("LKP-I-382 x 200](https://cdn-assets-eu.frontify.co", "206921", "%",
            "Hyderabad [040 6921 6060](tel:040%206921%206060) * ![Image 7: Best Hospital"),
        # tel: phone-derived plausible-looking percentages (value ok, context is chrome)
        _dp("In Parel, Mumbai](https://cdn-assets-eu.frontify.c", "22", "%",
            "Parel, Mumbai [022 6767 0202](tel:022%206767%200202) * ![Image 8: 382X200]"),
        _dp("9: Chennai home](https://cdn-assets-eu.frontify.co", "44", "%",
            "Chennai [044 4624 2424](tel:044%204624%202424) [ ](https://www.gleneagle"),
        # CDN crop fragment
        _dp("Gleneagles](https://www.gleneagleshospitals.co.in/", "0.5", "%",
            "width=80&amp;height=67&amp;crop=fp&amp;fp=0.5%2C0.5&amp;fp_zoom=1) Richmond Road"),
        # empty label — nothing to reason over
        _dp("", "5", "", "some fragment with a stray 5 and no describable quantity"),
        # www. host
        _dp("Contact www.example-hospital.com for", "40", "%",
            "for more info visit www.example-hospital.com booking 40% discount promo"),
        # HTML entity chrome
        _dp("height=67&amp;crop image sizing", "67", "",
            "width=80&amp;height=67&amp;crop=fp banner sizing metadata", data_type="quantity"),
    ]


def _mixed_fixture():
    """Junk FIRST (mirrors real iteration order where chrome leads), then clean — so the
    legacy ``fixture[:limit]`` slice surfaces junk while curation surfaces the clean set."""
    junk = _junk_datapoints()
    clean = _clean_datapoints()
    out = []
    # interleave with junk leading (6 junk, then alternate) to reproduce the drb_78 order
    out.extend(junk[:6])
    for i in range(max(len(junk[6:]), len(clean))):
        if i < len(clean):
            out.append(clean[i])
        if i < len(junk[6:]):
            out.append(junk[6:][i])
    return out


# ── (1) is_junk_modelable_datapoint: True for every junk, False for every clean ──
def test_junk_predicate_flags_all_junk_and_no_clean():
    for dp in _junk_datapoints():
        assert is_junk_modelable_datapoint(dp) is True, (
            f"junk NOT flagged: label={dp['label']!r} value={dp['value']} unit={dp['unit']!r}"
        )
    for dp in _clean_datapoints():
        assert is_junk_modelable_datapoint(dp) is False, (
            f"clean WRONGLY flagged: label={dp['label']!r} value={dp['value']}"
        )


# ── (2) GREEN: curated shortlist contains ALL clean and ZERO junk ──
def test_select_writer_candidates_keeps_all_clean_drops_all_junk():
    fixture = _mixed_fixture()
    clean = _clean_datapoints()
    curated = select_writer_candidate_numbers(fixture, limit=40)

    # every clean datapoint survived (identity by (label, value))
    clean_keys = {(d["label"], d["value"]) for d in clean}
    curated_keys = {(d["label"], d["value"]) for d in curated}
    assert clean_keys <= curated_keys, "curation dropped a clean clinical datapoint"
    # ZERO junk survived
    for d in curated:
        assert is_junk_modelable_datapoint(d) is False
    assert len(curated) == len(clean)


# ── (2b) RED contrast: the LEGACY raw slice surfaces junk (documents the bug) ──
def test_red_legacy_raw_slice_surfaces_junk_that_curation_removes():
    fixture = _mixed_fixture()
    # LEGACY behavior (the bug): raw iteration-order slice includes chrome/binary junk.
    legacy_slice = fixture[:40]
    legacy_junk = [d for d in legacy_slice if is_junk_modelable_datapoint(d)]
    assert legacy_junk, "fixture must reproduce the leading-junk bug for a meaningful RED"
    # GREEN behavior (the fix): the curated shortlist has none of it.
    curated = select_writer_candidate_numbers(fixture, limit=40)
    assert not [d for d in curated if is_junk_modelable_datapoint(d)]
    assert len(curated) < len(legacy_slice)  # junk was actually removed


# ── (3) determinism: identical input -> identical output order ──
def test_curation_is_deterministic():
    fixture = _mixed_fixture()
    a = select_writer_candidate_numbers(fixture, limit=40)
    b = select_writer_candidate_numbers(fixture, limit=40)
    assert a == b
    assert [d["value"] for d in a] == [d["value"] for d in b]


# ── (4) kill-switch OFF -> byte-identical legacy ``fixture[:limit]`` ──
def test_kill_switch_off_is_byte_identical_legacy_slice():
    fixture = _mixed_fixture()
    saved = qa._SHORTLIST_CLEAN_ENABLED
    try:
        qa._SHORTLIST_CLEAN_ENABLED = False
        out = select_writer_candidate_numbers(fixture, limit=40)
        assert out == fixture[:40]  # no curation whatsoever
        # and it still contains the junk the raw slice had (proves it is a pure revert)
        assert any(is_junk_modelable_datapoint(d) for d in out)
    finally:
        qa._SHORTLIST_CLEAN_ENABLED = saved


def test_limit_none_returns_all_clean():
    fixture = _mixed_fixture()
    out = select_writer_candidate_numbers(fixture)  # no limit
    assert len(out) == len(_clean_datapoints())
    assert not [d for d in out if is_junk_modelable_datapoint(d)]


# ── (5) run_quantified_section: honest disclosure, NOT silent no_spec_returned ──
def _all_junk_pool():
    """An evidence pool whose extracted numbers are ALL scrape chrome (drb_78 shape)."""
    return {
        "ev_pdf": {
            "direct_quote": (
                "%PDF-1.5 13 0 obj <>>>/BBox[0 0 612 792]/Length 204669 and image "
                "382x200px](https://cdn-assets-eu.frontify.co) [080 4669 4311]"
                "(tel:080%204669%204311) width=80&amp;height=67&amp;crop=fp&amp;fp_zoom=1"
            ),
            "source_url": "https://cdn-assets-eu.frontify.co/x", "tier": "T6",
        },
    }


def test_all_junk_pool_discloses_no_modelable_numbers_and_skips_writer():
    """With numbers present but ALL junk, the section surfaces the DISTINCT honest
    ``no_modelable_numbers`` status and NEVER bills the Writer — not the ambiguous
    silent ``no_spec_returned``. This is the U27 honest-disclosure branch."""
    rows = _all_junk_pool()
    # sanity: the extractor really produced junk numbers here (the bug precondition)
    dps = extract_numbers_from_evidence(rows)
    assert dps and all(is_junk_modelable_datapoint(d) for d in dps)

    calls = {"n": 0}

    async def spec_provider(_q, _s):
        calls["n"] += 1
        return {"model_id": "tco", "title": "T", "inputs": [], "outputs": []}

    section, telem = asyncio.run(
        run_quantified_section("q", rows, spec_provider=spec_provider)
    )
    assert section is None
    assert telem["firing_status"] == "no_modelable_numbers"      # honest, distinct
    assert telem["firing_status"] != "no_spec_returned"          # NOT the silent no-op
    assert telem.get("quantified_status") == QUANTIFIED_STATUS_DECLINED_NO_SPEC
    assert telem["writer_candidates"] == 0
    assert telem["sourced_numbers_junk"] == len(dps)
    assert calls["n"] == 0                                        # billed Writer skipped


def test_clean_pool_reaches_writer_with_curated_shortlist():
    """With a clean modelable number present, the Writer IS called and the shortlist it
    receives is curated (clean-only) — the numbers reach the LLM instead of being
    starved by leading junk. (The LLM then modeling them is a live outcome, not asserted
    offline; here we prove the clean candidate is delivered.)"""
    rows = {
        "ev_1": {
            "direct_quote": "The total program cost was $2.0 billion in fiscal 2024.",
            "statement": "The total program cost was $2.0 billion in fiscal 2024.",
            "source_url": "https://example.org/x", "tier": "T1",
        },
    }
    seen = {"sourced": None}

    async def spec_provider(_q, sourced):
        # the section passes the FULL pool; the prod closure curates to the shortlist.
        seen["sourced"] = list(sourced)
        return None  # decline is fine — we only assert the clean candidate was available

    section, telem = asyncio.run(
        run_quantified_section("q", rows, spec_provider=spec_provider)
    )
    # a clean modelable candidate existed -> NOT short-circuited as no_modelable_numbers
    assert telem["firing_status"] == "no_spec_returned"
    assert telem["writer_candidates"] >= 1
    # and the curated shortlist over what the section extracted is clean-only
    curated = select_writer_candidate_numbers(seen["sourced"], limit=40)
    assert curated and not [d for d in curated if is_junk_modelable_datapoint(d)]


def test_kill_switch_off_no_added_telem_keys():
    """PG_QUANTIFIED_SHORTLIST_CLEAN=0: no curation telem keys, no short-circuit — the
    all-junk pool falls through to the legacy Writer-decline path (byte-identical shape)."""
    rows = _all_junk_pool()
    saved = qa._SHORTLIST_CLEAN_ENABLED

    async def decline(_q, _s):
        return None

    try:
        qa._SHORTLIST_CLEAN_ENABLED = False
        section, telem = asyncio.run(run_quantified_section("q", rows, spec_provider=decline))
        assert section is None
        assert "writer_candidates" not in telem       # no curation telemetry
        assert "sourced_numbers_junk" not in telem
        assert telem["firing_status"] == "no_spec_returned"   # legacy path unchanged
    finally:
        qa._SHORTLIST_CLEAN_ENABLED = saved


# ── (6) behavioral replay over the real banked drb_78 corpus (skip if absent) ──
def test_behavioral_replay_drb78_curated_shortlist_is_clean():
    import json

    candidates = [
        os.path.join(
            os.path.dirname(__file__), "..", "..", "..",
            ".codex", "I-deepfix-001", "autopsy", "autopsy_43405118", "outputs",
            "fanout", "clinical", "drb_78_parkinsons_dbs", "evidence_pool.json",
        ),
        os.path.join(
            "C:/POLARIS", ".codex", "I-deepfix-001", "autopsy", "autopsy_43405118",
            "outputs", "fanout", "clinical", "drb_78_parkinsons_dbs", "evidence_pool.json",
        ),
    ]
    path = next((p for p in candidates if os.path.exists(p)), None)
    if path is None:
        import pytest
        pytest.skip("banked drb_78 evidence_pool.json not present (untracked autopsy artifact)")

    with open(path, encoding="utf-8") as fh:
        rows = json.load(fh)
    pool = {r["evidence_id"]: r for r in rows if isinstance(r, dict) and r.get("evidence_id")}
    dps = extract_numbers_from_evidence(pool)
    assert len(dps) > 100  # the real corpus yields thousands of extracted numbers

    # the legacy raw slice was junk-dominated (the reproduced bug)
    legacy = dps[:40]
    assert [d for d in legacy if is_junk_modelable_datapoint(d)], "expected leading junk"

    curated = select_writer_candidate_numbers(dps, limit=40)
    # ZERO chrome/binary signatures survive in the curated shortlist
    sigs = ("%pdf", "](http", "tel:", "cdn-assets", "�")
    for d in curated:
        blob = f"{d.get('label', '')}{d.get('context', '')}".lower()
        assert not any(s in blob for s in sigs), f"chrome survived curation: {d.get('label')!r}"
    # and at least one real clinical percentage/measurement is present
    assert any(d.get("unit") in ("%", "months", "hours") for d in curated)


def test_junk_markers_do_not_false_positive_clinical_prose():
    """I-deepfix-001 U27 iter2 (Codex): the removed over-broad substrings (' obj'/'stream') must not
    flag ordinary clinical prose as junk, while real PDF binary junk is still caught."""
    from src.polaris_graph.generator.quantified_analysis import is_junk_modelable_datapoint as j
    # clinical prose that INCIDENTALLY contains 'obj'/'stream' substrings -> NOT junk
    assert j({"label": "Objective: response rate", "context": "Objective: response rate was 42%", "value": 42, "unit": "%"}) is False
    assert j({"label": "bloodstream infections", "context": "bloodstream infections occurred in 2.5%", "value": 2.5, "unit": "%"}) is False
    assert j({"label": "income stream", "context": "a recurring income stream of 5%", "value": 5, "unit": "%"}) is False
    # real PDF binary junk -> STILL junk (object header + stream keywords)
    assert j({"label": "obj", "context": "13 0 obj << /Length 4096 >> stream", "value": 4096, "unit": None}) is True
    assert j({"label": "x", "context": "endstream endobj", "value": 1, "unit": None}) is True
