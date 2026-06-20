"""Unit tests for the SURE-RAG per-citation relevance gate (I-beatboth-003, #1280).

Covers the new ``relevance_judge`` helper (taxonomy normalization, injectable judge,
always-release on judge error, OFF default) AND the demotion + minimum-retention wiring in
``provenance_generator.resolve_provenance_to_citations`` (per-citation demote, refuted
routing, never-strand guard, OFF byte-identity). The behavioral end-to-end §-1.4 assertions
live in ``scripts/iarch_beatboth003_relevance_gate_replay_harness.py``; these are the
focused unit checks.
"""

from __future__ import annotations

import os

import pytest

from src.polaris_graph.generator import relevance_judge as rj
from src.polaris_graph.generator import provenance_generator as pg


# ── relevance_judge helper ───────────────────────────────────────────────────
def test_gate_default_off(monkeypatch):
    monkeypatch.delenv("PG_RELEVANCE_GATE", raising=False)
    assert rj.relevance_gate_enabled() is False


def test_gate_on_truthy(monkeypatch):
    for v in ("1", "true", "on", "YES", "enabled"):
        monkeypatch.setenv("PG_RELEVANCE_GATE", v)
        assert rj.relevance_gate_enabled() is True


def test_normalize_label_canonical():
    assert rj.normalize_label("SUPPORTED") == rj.LABEL_SUPPORTED
    assert rj.normalize_label("insufficient") == rj.LABEL_INSUFFICIENT
    assert rj.normalize_label("Refuted") == rj.LABEL_REFUTED


def test_normalize_label_synonyms():
    assert rj.normalize_label("support") == rj.LABEL_SUPPORTED
    assert rj.normalize_label("irrelevant") == rj.LABEL_INSUFFICIENT
    assert rj.normalize_label("contradicted") == rj.LABEL_REFUTED


def test_normalize_label_unrecognized_is_none():
    assert rj.normalize_label("banana") is None
    assert rj.normalize_label("") is None
    assert rj.normalize_label(None) is None


def test_injected_judge_used():
    seen = {}

    def fake(claim, span):
        seen["claim"] = claim
        seen["span"] = span
        return (rj.LABEL_INSUFFICIENT, "wrong relation")

    label, reason = rj.judge_citation_relevance("the claim", "the span", relevance_judge_fn=fake)
    assert label == rj.LABEL_INSUFFICIENT
    assert reason == "wrong relation"
    assert seen == {"claim": "the claim", "span": "the span"}


def test_injected_judge_unparseable_keeps_cite():
    # An out-of-taxonomy verdict from an injected judge -> SUPPORTED keep (never strand).
    label, reason = rj.judge_citation_relevance(
        "c", "s", relevance_judge_fn=lambda c, s: ("maybe?", "unsure"),
    )
    assert label == rj.LABEL_SUPPORTED
    assert reason.startswith("judge_error:")


def test_injected_judge_raise_keeps_cite():
    def boom(claim, span):
        raise RuntimeError("transport down")

    label, reason = rj.judge_citation_relevance("c", "s", relevance_judge_fn=boom)
    assert label == rj.LABEL_SUPPORTED  # always-release: a judge fault never demotes
    assert reason.startswith("judge_error:")


# ── demotion + minimum-retention wiring in the resolver ──────────────────────
def _pool():
    return {
        "ev_ok": {
            "source_url": "u_ok", "tier": "T1",
            "statement": "Aspirin reduced clot formation by 40 percent in the trial.",
            "direct_quote": "Aspirin reduced clot formation by 40 percent in the trial.",
        },
        "ev_bad": {
            "source_url": "u_bad", "tier": "T3",
            "statement": "Aspirin was first synthesized in 1897 by Felix Hoffmann.",
            "direct_quote": "Aspirin was first synthesized in 1897 by Felix Hoffmann.",
        },
    }


def _sv(sentence, pool):
    pg.reset_relevance_telemetry()
    rep = pg.strict_verify(sentence, pool, require_number_match=True)
    return rep.kept_sentences


@pytest.fixture(autouse=True)
def _offline(monkeypatch):
    monkeypatch.setenv("PG_STRICT_VERIFY_ENTAILMENT", "off")
    monkeypatch.setenv("PG_PROVENANCE_REANCHOR", "0")
    monkeypatch.setenv("PG_SPAN_RESOLVER", "0")
    rj.reset_judge_singleton()
    yield


def test_insufficient_citation_demoted(monkeypatch):
    monkeypatch.setenv("PG_RELEVANCE_GATE", "1")
    pool = _pool()
    quote_ok = pool["ev_ok"]["direct_quote"]
    quote_bad = pool["ev_bad"]["direct_quote"]
    draft = (
        "Aspirin reduced clot formation by 40 percent "
        f"[#ev:ev_ok:0-{len(quote_ok)}][#ev:ev_bad:0-{len(quote_bad)}]."
    )
    kept = _sv(draft, pool)

    def judge(claim, span):
        if "reduced clot formation" in span:
            return (rj.LABEL_SUPPORTED, "ok")
        return (rj.LABEL_INSUFFICIENT, "off-topic history")

    text, biblio = pg.resolve_provenance_to_citations(kept, pool, relevance_judge_fn=judge)
    urls = {row["url"] for row in biblio}
    assert "u_ok" in urls           # genuine support kept
    assert "u_bad" not in urls      # INSUFFICIENT demoted out of the inline support set
    assert "reduced clot formation by 40 percent" in text  # always-release: it ships
    tel = pg.get_relevance_telemetry()
    assert tel["labeled_insufficient"] == 1
    assert tel["demoted_from_support"] == 1


def test_minimum_retention_never_strands(monkeypatch):
    monkeypatch.setenv("PG_RELEVANCE_GATE", "1")
    pool = _pool()
    quote_bad = pool["ev_bad"]["direct_quote"]
    # The ONLY citation is the off-topic one; demoting it would strand the statement.
    draft = (
        "Aspirin was first synthesized in 1897 by Felix Hoffmann "
        f"[#ev:ev_bad:0-{len(quote_bad)}]."
    )
    kept = _sv(draft, pool)
    text, biblio = pg.resolve_provenance_to_citations(
        kept, pool, relevance_judge_fn=lambda c, s: (rj.LABEL_INSUFFICIENT, "off"),
    )
    # Minimum-retention: the citation is KEPT (statement marked weak), never stranded.
    assert "u_bad" in {row["url"] for row in biblio}
    assert "[1]" in text
    tel = pg.get_relevance_telemetry()
    assert tel["sentences_marked_weak"] == 1
    assert tel["demoted_from_support"] == 0


# ── iter-2 (Codex diff-gate P1) persistence wiring ──────────────────────────
# These cover the three iter-2 P1 fixes: the per-citation LABEL side-output is
# PERSISTED (not computed-then-discarded), Refuted is kept SEPARATE from Insufficient
# (two distinct sets + a contradiction soft-warning), and the minimum-retention guard
# ACTUALLY marks the statement weak (a persisted soft-warning, not just telemetry).
def _refuter_pool():
    p = _pool()
    p["ev_ref"] = {
        "source_url": "u_ref", "tier": "T1",
        "statement": "Aspirin increased clot formation by 40 percent in a subgroup.",
        "direct_quote": "Aspirin increased clot formation by 40 percent in a subgroup.",
    }
    return p


def test_refuted_persists_contradiction_flag_and_separate_set(monkeypatch):
    # P1#1b + P1#2: a REFUTED citation is kept in the SEPARATE relevance_refuted_eids set
    # (NOT collapsed into relevance_demoted_eids) AND a persisted
    # relevance_refuted_contradiction soft-warning names it. The genuine support stays so the
    # refuter is cleanly removed (never the last cite -> no retention-guard interference).
    monkeypatch.setenv("PG_RELEVANCE_GATE", "1")
    pool = _refuter_pool()
    quote_ok = pool["ev_ok"]["direct_quote"]
    quote_ref = pool["ev_ref"]["direct_quote"]
    draft = (
        "Aspirin reduced clot formation by 40 percent "
        f"[#ev:ev_ok:0-{len(quote_ok)}][#ev:ev_ref:0-{len(quote_ref)}]."
    )
    kept = _sv(draft, pool)

    def judge(claim, span):
        if "reduced clot formation" in span:
            return (rj.LABEL_SUPPORTED, "ok")
        return (rj.LABEL_REFUTED, "contradicts: increased not reduced")

    text, biblio = pg.resolve_provenance_to_citations(kept, pool, relevance_judge_fn=judge)
    urls = {row["url"] for row in biblio}
    assert "u_ok" in urls            # genuine support kept
    assert "u_ref" not in urls       # REFUTED removed from inline support
    assert "reduced clot formation by 40 percent" in text  # always-release: it ships

    sv = kept[0]
    # Two DISTINCT sets: refuter in relevance_refuted_eids, NOT in relevance_demoted_eids.
    assert "ev_ref" in (sv.relevance_refuted_eids or frozenset())
    assert "ev_ref" not in (sv.relevance_demoted_eids or frozenset())
    # The structured per-citation label map is PERSISTED (P1#1a).
    assert (sv.relevance_labels or {}).get("ev_ref") == rj.LABEL_REFUTED
    assert (sv.relevance_labels or {}).get("ev_ok") == rj.LABEL_SUPPORTED
    # The contradiction FLAG is a persisted, inspectable soft-warning naming the refuter.
    assert any(
        w.startswith("relevance_refuted_contradiction") and "ev_ref" in w
        for w in sv.soft_warnings
    ), f"no persisted contradiction soft-warning: {sv.soft_warnings!r}"
    tel = pg.get_relevance_telemetry()
    assert tel["labeled_refuted"] == 1
    assert tel["contradiction_flagged"] == 1
    assert tel["demoted_from_support"] == 1  # the refuter removed from inline support


def test_insufficient_persists_label_and_demote_warning(monkeypatch):
    # P1#1a: the INSUFFICIENT label + its demote soft-warning are PERSISTED on the SV (the
    # side-output the pre-fix code computed then discarded). demoted set is Insufficient-only;
    # refuted set is empty.
    monkeypatch.setenv("PG_RELEVANCE_GATE", "1")
    pool = _pool()
    quote_ok = pool["ev_ok"]["direct_quote"]
    quote_bad = pool["ev_bad"]["direct_quote"]
    draft = (
        "Aspirin reduced clot formation by 40 percent "
        f"[#ev:ev_ok:0-{len(quote_ok)}][#ev:ev_bad:0-{len(quote_bad)}]."
    )
    kept = _sv(draft, pool)

    def judge(claim, span):
        if "reduced clot formation" in span:
            return (rj.LABEL_SUPPORTED, "ok")
        return (rj.LABEL_INSUFFICIENT, "off-topic history")

    pg.resolve_provenance_to_citations(kept, pool, relevance_judge_fn=judge)
    sv = kept[0]
    assert "ev_bad" in (sv.relevance_demoted_eids or frozenset())
    assert "ev_bad" not in (sv.relevance_refuted_eids or frozenset())
    assert (sv.relevance_labels or {}).get("ev_bad") == rj.LABEL_INSUFFICIENT
    assert any(
        w.startswith("relevance_demoted_insufficient") and "ev_bad" in w
        for w in sv.soft_warnings
    ), f"no persisted demote soft-warning: {sv.soft_warnings!r}"


def test_minimum_retention_persists_weak_mark(monkeypatch):
    # P1#3: when the retention guard fires (the last support would be demoted), the statement
    # is ACTUALLY MARKED WEAK via a persisted relevance_statement_weak soft-warning — not just
    # a telemetry bump. The cite is KEPT (never stranded).
    monkeypatch.setenv("PG_RELEVANCE_GATE", "1")
    pool = _pool()
    quote_bad = pool["ev_bad"]["direct_quote"]
    draft = (
        "Aspirin was first synthesized in 1897 by Felix Hoffmann "
        f"[#ev:ev_bad:0-{len(quote_bad)}]."
    )
    kept = _sv(draft, pool)
    text, biblio = pg.resolve_provenance_to_citations(
        kept, pool, relevance_judge_fn=lambda c, s: (rj.LABEL_INSUFFICIENT, "off"),
    )
    assert "u_bad" in {row["url"] for row in biblio}  # kept, never stranded
    assert "[1]" in text
    sv = kept[0]
    # The WEAK mark is PERSISTED on the SV (the P1#3 fix; pre-fix only telemetry bumped).
    assert any(
        w.startswith("relevance_statement_weak") for w in sv.soft_warnings
    ), f"no persisted weak mark: {sv.soft_warnings!r}"
    # Retention un-demoted: the demote/refute sets are empty (the cite was kept as support).
    assert not (sv.relevance_demoted_eids or frozenset())
    assert not (sv.relevance_refuted_eids or frozenset())
    # Internal consistency (Codex iter-2): the demote/refute ACTION soft-warnings must NOT be
    # present when the sets are empty (no action happened) — warnings must match the sets.
    assert not any(
        w.startswith("relevance_demoted_insufficient")
        or w.startswith("relevance_refuted_contradiction")
        for w in sv.soft_warnings
    ), f"stale action warning on a retained-weak sentence: {sv.soft_warnings!r}"
    # The honest verdict is still recorded in the label map (orthogonal to retention).
    assert (sv.relevance_labels or {}).get("ev_bad") == rj.LABEL_INSUFFICIENT
    tel = pg.get_relevance_telemetry()
    assert tel["sentences_marked_weak"] == 1
    assert tel["demoted_from_support"] == 0


def test_off_path_persists_no_relevance_sidecar(monkeypatch):
    # OFF byte-identity at the SV level: with the gate OFF the new side-output fields stay
    # None / empty and NO relevance soft-warning is added (additive default-OFF inert).
    monkeypatch.setenv("PG_RELEVANCE_GATE", "0")
    pool = _pool()
    quote_ok = pool["ev_ok"]["direct_quote"]
    quote_bad = pool["ev_bad"]["direct_quote"]
    draft = (
        "Aspirin reduced clot formation by 40 percent "
        f"[#ev:ev_ok:0-{len(quote_ok)}][#ev:ev_bad:0-{len(quote_bad)}]."
    )
    kept = _sv(draft, pool)

    def boom(claim, span):
        raise AssertionError("judge must NOT be called on the OFF path")

    pg.resolve_provenance_to_citations(kept, pool, relevance_judge_fn=boom)
    sv = kept[0]
    assert sv.relevance_demoted_eids is None
    assert sv.relevance_refuted_eids is None
    assert sv.relevance_labels is None
    assert not any(w.startswith("relevance_") for w in sv.soft_warnings)


def test_off_path_byte_identical(monkeypatch):
    monkeypatch.setenv("PG_RELEVANCE_GATE", "0")
    pool = _pool()
    quote_ok = pool["ev_ok"]["direct_quote"]
    quote_bad = pool["ev_bad"]["direct_quote"]
    draft = (
        "Aspirin reduced clot formation by 40 percent "
        f"[#ev:ev_ok:0-{len(quote_ok)}][#ev:ev_bad:0-{len(quote_bad)}]."
    )
    kept = _sv(draft, pool)

    def boom(claim, span):
        raise AssertionError("judge must NOT be called on the OFF path")

    text_off, biblio_off = pg.resolve_provenance_to_citations(
        kept, pool, relevance_judge_fn=boom,
    )
    kept2 = _sv(draft, pool)
    text_base, biblio_base = pg.resolve_provenance_to_citations(kept2, pool)
    assert text_off == text_base
    assert [r["url"] for r in biblio_off] == [r["url"] for r in biblio_base]
    # both original cites present on the OFF path
    assert "[1][2]" in text_off


# ── §-1.4 BEHAVIORAL proof on the PRODUCTION composer (V30 contract path) ─────
# The legacy resolver (above) is NOT the shipped body under Gate-B
# (PG_V30_PHASE2_ENABLED=1): every section ships through run_contract_section's
# slot-regroup, which has its OWN inline-citation loop. This test drives the REAL
# run_contract_section with the gate ON + a mock judge and proves the demoted citation
# is ABSENT from the shipped slot body (result.verified_text) — the "fired in the real
# output, not the discarded resolved_body" §-1.4 assertion.
import pytest as _pytest  # noqa: E402


@_pytest.mark.asyncio
async def test_contract_path_demotion_fires_in_shipped_slot_body(monkeypatch):
    # Reuse the REAL contract-path harness helpers (same machinery Gate-B uses).
    lane = _pytest.importorskip(
        "tests.polaris_graph.generator.test_lane_section_arch005_contract_path"
    )
    import yaml
    from pathlib import Path
    from src.polaris_graph.generator.contract_section_runner import run_contract_section
    from src.polaris_graph.generator.live_deepseek_generator import _rewrite_draft_with_spans
    from src.polaris_graph.generator.provenance_generator import strict_verify
    from src.polaris_graph.synthesis.credibility_pass import (
        BASKET_VERDICT_PARTIAL, BasketMember, ClaimBasket, CredibilityAnalysis,
    )

    monkeypatch.setenv("PG_STRICT_VERIFY_ENTAILMENT", "off")
    monkeypatch.setenv("PG_RELEVANCE_GATE", "1")
    rj.reset_judge_singleton()
    pg.reset_relevance_telemetry()

    with Path("config/scope_templates/clinical.yaml").open("r", encoding="utf-8") as f:
        clinical_template = yaml.safe_load(f)
    plan, pool = lane._build_contract_inputs(clinical_template)
    assert {"surpass_1_primary", "surpass_2_primary"} <= set(pool)

    # ev1 + ev2 SUPPORTS the SAME basket -> the contract slot for ev1 also renders ev2's
    # corroborator marker. ev2's basket member carries an OFF-TOPIC span so the mock judge
    # labels it INSUFFICIENT; it must be DEMOTED out of the shipped slot body — while ev1
    # (the genuine support, its own sentence span = the endpoint) stays (never stranded).
    _OFFTOPIC_SPAN = "Funding was provided by an unrelated educational grant."
    members = [
        lane._member("surpass_1_primary", "SUPPORTS"),
        BasketMember(
            evidence_id="surpass_2_primary", source_url="https://surpass_2_primary/",
            source_tier="T1", origin_cluster_id="o::surpass_2_primary",
            credibility_weight=0.8, authority_score=0.8,
            span=(0, len(_OFFTOPIC_SPAN)), direct_quote=_OFFTOPIC_SPAN,
            span_verdict="SUPPORTS",
        ),
    ]
    basket = ClaimBasket(
        claim_cluster_id="c_shared", claim_text="N=1879 enrolled.",
        subject="trial", predicate="enrollment",
        supporting_members=members, refuter_cluster_ids=(),
        weight_mass=1.6, total_clustered_origin_count=2,
        verified_support_origin_count=2, basket_verdict=BASKET_VERDICT_PARTIAL,
    )
    binding = {"surpass_1_primary": ["c_shared"], "surpass_2_primary": ["c_shared"]}
    analysis = CredibilityAnalysis(
        credibility_by_evidence=lane._covering_cred(pool),
        origin_by_evidence={e: f"o::{e}" for e in pool},
        claims=[], edges=[], weight_mass=[],
        baskets=[basket], cluster_id_by_evidence=binding,
    )

    def mock_judge(claim, span):
        # Deterministic by span CONTENT: ev1's own sentence span = the endpoint (SUPPORTED);
        # ev2's basket corroborator span = the off-topic funding sentence (INSUFFICIENT).
        if "Funding was provided" in span:
            return (rj.LABEL_INSUFFICIENT, "off-topic corroborator")
        return (rj.LABEL_SUPPORTED, "establishes the endpoint relation")

    class _SR:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    result, _payloads = await run_contract_section(
        plan, pool,
        llm_call=lane._fake_llm, section_result_cls=_SR,
        strict_verify_fn=strict_verify, rewrite_fn=_rewrite_draft_with_spans,
        credibility_analysis=analysis,
        relevance_judge_fn=mock_judge,
    )
    text = result.verified_text
    biblio = result.biblio_slice
    n1 = lane._num_for_evidence(biblio, "surpass_1_primary")
    assert n1 is not None, "primary support must be numbered + kept"
    # The gate FIRED: the judge was called on the real contract path.
    tel = pg.get_relevance_telemetry()
    assert tel["citations_judged"] >= 1, "relevance judge did NOT fire on the contract path"
    # Always-release: the section body ships and the genuine support [n1] is present.
    body1 = lane._slot_body_for(text, f"[{n1}]")
    assert body1, "the surpass_1 slot body must ship (always-release)"
    # The demoted INSUFFICIENT corroborator (ev2) must be ABSENT as inline support in the
    # surpass_1 slot body — proving demotion fired in the SHIPPED contract body.
    n2 = lane._num_for_evidence(biblio, "surpass_2_primary")
    if n2 is not None:
        assert f"[{n2}]" not in body1, (
            "CONTRACT-PATH NO-OP: the INSUFFICIENT corroborator still renders as inline "
            f"support in the shipped slot body. body={body1!r}"
        )
