"""B2 (I-deepfix-001 #1344) — per-section boundary-conditions / counter-evidence line tests.

FAIL-LOUD: proves a lower-weight qualifying basket's already-verified span is SURFACED as a boundary
line (a real effect on section output), firing even WITHOUT a refuter cluster, and NOT firing when no
qualifying lower-weight basket exists. RED before src/polaris_graph/generator/boundary_conditions.py
existed. Offline, $0.
"""
from __future__ import annotations

import importlib
from dataclasses import dataclass, field

bc = importlib.import_module("src.polaris_graph.generator.boundary_conditions")


@dataclass
class _Member:
    evidence_id: str
    direct_quote: str = ""
    span_verdict: str = "SUPPORTS"
    source_url: str = ""
    source_tier: str = ""


@dataclass
class _Basket:
    claim_cluster_id: str
    claim_text: str
    subject: str = ""
    predicate: str = ""
    weight_mass: float = 0.0
    refuter_cluster_ids: tuple = ()
    supporting_members: list = field(default_factory=list)


def _headline():
    return _Basket(
        claim_cluster_id="h",
        claim_text="Semaglutide reduces body weight in adults with obesity",
        subject="semaglutide weight reduction",
        weight_mass=9.0,
        supporting_members=[_Member("ev_h", "Semaglutide reduced body weight by 15%.", source_url="https://nejm.org/a", source_tier="T1")],
    )


def _lower_weight_qualifier():
    # shares content words (semaglutide, body, weight), LOWER weight, carries "only ... in patients with"
    return _Basket(
        claim_cluster_id="q",
        claim_text="Semaglutide reduces body weight only in patients with baseline BMI above 30",
        subject="semaglutide subgroup",
        weight_mass=2.0,
        supporting_members=[_Member(
            "ev_q",
            "Weight loss with semaglutide was significant only in patients with baseline BMI above 30.",
            source_url="https://smalljournal.org/b",
            source_tier="T4",
        )],
    )


def test_boundary_line_fires_from_lower_weight_basket_without_refuter_cluster():
    """The headline has NO refuter_cluster_ids, yet a lower-weight qualifying basket bounds it — the
    boundary line must fire and quote the lower-weight source's already-verified span."""
    headline = _headline()
    qualifier = _lower_weight_qualifier()
    assert headline.refuter_cluster_ids == ()  # fires WITHOUT a refuter cluster
    line = bc.synthesize_boundary_line([headline, qualifier], [headline, qualifier])
    assert line, "expected a boundary-conditions line"
    assert "Boundary conditions" in line
    # quotes the LOWER-WEIGHT member's own verified span (faithful-by-quotation)
    assert "only in patients with baseline BMI above 30" in line
    # attributes the lower-weight source
    assert "smalljournal.org" in line


def test_no_qualifying_basket_returns_empty():
    """A section with only the headline (no lower-weight qualifier) emits no boundary line."""
    headline = _headline()
    line = bc.synthesize_boundary_line([headline], [headline])
    assert line == ""


def test_higher_or_equal_weight_basket_is_not_a_qualifier():
    """A same-topic basket at HIGHER weight is not surfaced as a bounding counter-evidence line
    (weight-in: the boundary line comes from LOWER-weight dissent, never a stronger co-headline)."""
    headline = _headline()
    stronger = _Basket(
        claim_cluster_id="s",
        claim_text="Semaglutide reduces body weight substantially in adults",
        subject="semaglutide",
        weight_mass=12.0,  # higher than headline
        supporting_members=[_Member("ev_s", "Body weight fell markedly.", span_verdict="SUPPORTS")],
    )
    assert bc.find_qualifying_lower_weight_basket(headline, [stronger]) is None


def test_qualifier_needs_a_span_verified_member():
    """A lower-weight basket whose only member is UNSUPPORTED cannot be quoted (no verified span) —
    so it is never surfaced, keeping the line faithful-by-quotation."""
    headline = _headline()
    unverified = _Basket(
        claim_cluster_id="u",
        claim_text="Semaglutide body weight effect only in a narrow subgroup",
        subject="semaglutide",
        weight_mass=1.0,
        supporting_members=[_Member("ev_u", "some text", span_verdict="UNSUPPORTED")],
    )
    assert bc.find_qualifying_lower_weight_basket(headline, [unverified]) is None
    assert bc.synthesize_boundary_line([headline], [headline, unverified]) == ""


def test_unrelated_lower_weight_basket_does_not_qualify():
    """A lower-weight basket on a DIFFERENT topic (no content-word overlap) never bounds the
    headline — the line never fabricates unrelated opposition."""
    headline = _headline()
    unrelated = _Basket(
        claim_cluster_id="x",
        claim_text="Aspirin reduces cardiovascular risk only in primary prevention",
        subject="aspirin",
        weight_mass=1.0,
        supporting_members=[_Member("ev_x", "Aspirin lowered risk only in a subgroup.", span_verdict="SUPPORTS")],
    )
    assert bc.find_qualifying_lower_weight_basket(headline, [unrelated]) is None


def test_refuter_cluster_also_qualifies_even_without_marker():
    """A lower-weight basket referenced as a refuter qualifies even if its claim carries no explicit
    boundary marker (an outright dissent is surfaced at its weight)."""
    headline = _Basket(
        claim_cluster_id="h",
        claim_text="Drug X improves survival in the overall population",
        subject="drug x survival",
        weight_mass=8.0,
        refuter_cluster_ids=("r",),
        supporting_members=[_Member("ev_h", "Survival improved.", span_verdict="SUPPORTS")],
    )
    refuter = _Basket(
        claim_cluster_id="r",
        claim_text="Drug X survival benefit was not reproduced in the overall population",
        subject="drug x survival",
        weight_mass=3.0,
        supporting_members=[_Member("ev_r", "The survival benefit of drug X was not reproduced.", span_verdict="SUPPORTS")],
    )
    line = bc.synthesize_boundary_line([headline], [headline, refuter])
    assert "not reproduced" in line


# ════════════════════════════════════════════════════════════════════════════════════════════
# PRODUCTION-EFFECT (Codex P1, iter 1): drive the REAL multi_section_generator._run_section and
# prove the boundary line is APPENDED to the rendered section body — not just the pure helper.
#
# The verified-compose PRIMARY branch (PG_VERIFIED_COMPOSE) is the deterministic, NO-LLM section
# producer: it derives _vc_baskets from the REAL _section_baskets_for_compose and, at the render
# tail, appends synthesize_boundary_line(_vc_baskets, _vc_baskets) to verified_text. We drive that
# real path with only the heavy upstream seams (compose text, strict_verify, resolve, repair)
# stubbed offline — no network / GPU / LLM. _section_baskets_for_compose, the boundary-line block,
# and the boundary_conditions module all run for real, so the boundary line's presence in the
# returned SectionResult.verified_text is a genuine production effect, not a helper tautology.
# ════════════════════════════════════════════════════════════════════════════════════════════
import asyncio  # noqa: E402
import types  # noqa: E402

import pytest  # noqa: E402

from src.polaris_graph.generator import multi_section_generator as _msg  # noqa: E402
from src.polaris_graph.generator import sentence_repair as _sentence_repair  # noqa: E402
from src.polaris_graph.synthesis.credibility_pass import (  # noqa: E402
    BasketMember,
    ClaimBasket,
    CredibilityAnalysis,
    EvidenceCredibility,
)


def _covering(*evidence_ids):
    """credibility_by_evidence + origin_by_evidence covering every cited evidence_id (the fail-loud
    disclosure-coverage gate refuses to disclose a source the pass never scored)."""
    cred, origin = {}, {}
    for i, eid in enumerate(evidence_ids):
        origin[eid] = f"origin_{i}"
        cred[eid] = EvidenceCredibility(
            evidence_id=eid,
            credibility_weight=0.85,
            reliability_score=0.85,
            relevance_score=0.85,
            origin_cluster_id=f"origin_{i}",
            is_canonical_origin=True,
            certainty_downgrade=False,
            soft_warning=None,
        )
    return cred, origin


def _real_member(eid, quote, url, tier, verdict="SUPPORTS"):
    return BasketMember(
        evidence_id=eid,
        source_url=url,
        source_tier=tier,
        origin_cluster_id=eid,
        credibility_weight=None,
        authority_score=0.5,
        span=(0, len(quote)),
        direct_quote=quote,
        span_verdict=verdict,
    )


def _real_basket(ccid, claim_text, subject, weight, members, refuters=()):
    return ClaimBasket(
        claim_cluster_id=ccid,
        claim_text=claim_text,
        subject=subject,
        predicate="",
        supporting_members=list(members),
        refuter_cluster_ids=tuple(refuters),
        weight_mass=weight,
        total_clustered_origin_count=len(members),
        verified_support_origin_count=len(members),
        basket_verdict="full",
    )


def _credibility_with_headline_and_qualifier():
    """A headline basket (weight 9, ev_h) + a strictly-lower-weight qualifier basket (weight 2, ev_q)
    that shares content words and carries an 'only ... in patients with' boundary marker."""
    headline = _real_basket(
        "h",
        "Semaglutide reduces body weight in adults with obesity",
        "semaglutide weight reduction",
        9.0,
        [_real_member("ev_h", "Semaglutide reduced body weight by 15% in adults with obesity.",
                      "https://nejm.org/a", "T1")],
    )
    qualifier = _real_basket(
        "q",
        "Semaglutide reduces body weight only in patients with baseline BMI above 30",
        "semaglutide subgroup",
        2.0,
        [_real_member(
            "ev_q",
            "Weight loss with semaglutide was significant only in patients with baseline BMI above 30.",
            "https://smalljournal.org/b",
            "T4",
        )],
    )
    cred, origin = _covering("ev_h", "ev_q")
    return CredibilityAnalysis(
        credibility_by_evidence=cred,
        origin_by_evidence=origin,
        claims=[],
        edges=[],
        weight_mass=[],
        baskets=[headline, qualifier],
    )


class _FakeSV:
    def __init__(self, sentence: str, evidence_id: str):
        self.sentence = sentence
        self.tokens = [types.SimpleNamespace(evidence_id=evidence_id, start=0, end=10)]
        self.is_verified = True


class _FakeReport:
    def __init__(self, kept, dropped):
        self.kept_sentences = list(kept)
        self.dropped_sentences = list(dropped)
        self.total_kept = len(kept)
        self.total_dropped = len(dropped)
        self.total_in = len(kept)


class _FakeRepairTelem:
    attempts = successes = null_drops = token_set_violations = 0
    re_verify_failures = api_failures = input_tokens = output_tokens = 0
    recovery_rate = 0.0


def _install_compose_stubs(monkeypatch, *, resolve_text):
    """Stub ONLY the heavy upstream seams so _run_section reaches the REAL verified-compose branch
    + boundary-line block offline. _section_baskets_for_compose and the boundary block run for real."""
    monkeypatch.setenv("PG_VERIFIED_COMPOSE", "1")          # take the deterministic compose branch
    monkeypatch.setenv("PG_ABSTRACTIVE_WRITER", "0")        # Fix 2: default-ON now; pin OFF => NO LLM
    monkeypatch.setenv("PG_SYNTH_PRIMARY", "0")             # Fix 2: default-ON now; pin OFF => legacy body
    monkeypatch.delenv("PG_NUMERIC_CITE_ENFORCE", raising=False)
    monkeypatch.setattr(_msg, "_section_distill_enabled", lambda: False)
    # The compose machinery is a DIFFERENT track's scope; stub it deterministically. _vc_baskets is
    # still populated by the REAL _section_baskets_for_compose in the elif condition (not stubbed).
    monkeypatch.setattr(
        _msg, "_compose_section_per_basket",
        lambda *_a, **_k: ["Semaglutide reduces body weight [#ev:ev_h:0-20]."],
    )
    monkeypatch.setattr(_msg, "_repair_untokened_draft", lambda raw, *_a, **_k: raw)
    monkeypatch.setattr(_msg, "_rewrite_draft_with_spans", lambda raw, _pool: (raw, [], []))
    monkeypatch.setattr(
        _msg, "strict_verify",
        lambda _rewritten, _pool: _FakeReport([_FakeSV(resolve_text, "ev_h")], []),
    )
    # Disclosure population is a separate track's concern (I-cred-008b); pass the kept SVs through so
    # _run_section reaches the B2 boundary block without needing a full SentenceVerification dataclass.
    import src.polaris_graph.synthesis.credibility_pass as _cred_pass  # noqa: PLC0415
    monkeypatch.setattr(_cred_pass, "apply_disclosure_to_svs", lambda kept, *_a, **_k: kept)
    monkeypatch.setattr(_msg, "filter_underframed_trial_sentences", lambda svs: (list(svs), []))
    monkeypatch.setattr(_msg, "dedup_same_span_sentences", lambda svs: (list(svs), []))
    monkeypatch.setattr(
        _msg, "resolve_provenance_to_citations_with_count",
        lambda _kept, _pool, **_kw: (resolve_text, [{"n": 1}], 1),
    )

    async def _stub_repair(*, kept, dropped, evidence_pool, model, max_tokens, temperature):
        return kept, dropped, _FakeRepairTelem()

    monkeypatch.setattr(_sentence_repair, "repair_dropped_section_sentences", _stub_repair)


def _run(section, evidence_pool, analysis):
    return asyncio.run(
        _msg._run_section(
            section, evidence_pool,
            model="test/model", temperature=0.0,
            max_tokens_per_section=100, min_kept_fraction=0.0,
            credibility_analysis=analysis,
        )
    )


def test_run_section_appends_boundary_line_from_lower_weight_basket(monkeypatch):
    """PRODUCTION EFFECT: _run_section renders real verified prose AND appends the B2 boundary line
    quoting the lower-weight qualifier's own verified span (no refuter cluster needed)."""
    resolve_text = "Semaglutide reduces body weight in adults with obesity [1]."
    _install_compose_stubs(monkeypatch, resolve_text=resolve_text)
    section = _msg.SectionPlan(title="Efficacy", focus="f", ev_ids=["ev_h", "ev_q"], archetype="")
    evidence_pool = {
        "ev_h": {"text": "Semaglutide reduced body weight by 15% in adults with obesity.",
                 "url": "https://nejm.org/a"},
        "ev_q": {"text": "Weight loss with semaglutide was significant only in patients with baseline BMI above 30.",
                 "url": "https://smalljournal.org/b"},
    }

    sr = _run(section, evidence_pool, _credibility_with_headline_and_qualifier())

    assert sr.is_gap_stub is False, sr.verified_text
    assert resolve_text in sr.verified_text                         # the real prose still ships
    assert "Boundary conditions" in sr.verified_text                # the B2 line was appended
    assert "only in patients with baseline BMI above 30" in sr.verified_text  # lower-weight span quoted
    assert "smalljournal.org" in sr.verified_text                   # attributed at its weight


def test_run_section_boundary_line_kill_switch_off_is_byte_identical(monkeypatch):
    """Byte-identical-OFF: with PG_SECTION_BOUNDARY_CONDITIONS=0 the section renders the SAME verified
    prose with NO boundary line appended."""
    resolve_text = "Semaglutide reduces body weight in adults with obesity [1]."
    _install_compose_stubs(monkeypatch, resolve_text=resolve_text)
    monkeypatch.setenv("PG_SECTION_BOUNDARY_CONDITIONS", "0")
    section = _msg.SectionPlan(title="Efficacy", focus="f", ev_ids=["ev_h", "ev_q"], archetype="")
    evidence_pool = {
        "ev_h": {"text": "x", "url": "https://nejm.org/a"},
        "ev_q": {"text": "y", "url": "https://smalljournal.org/b"},
    }

    sr = _run(section, evidence_pool, _credibility_with_headline_and_qualifier())

    assert sr.is_gap_stub is False, sr.verified_text
    assert resolve_text in sr.verified_text
    assert "Boundary conditions" not in sr.verified_text
    assert "only in patients with baseline BMI above 30" not in sr.verified_text
