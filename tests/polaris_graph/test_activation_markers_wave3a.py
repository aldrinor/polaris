"""I-deepfix-001 Wave-3a (#1344) — activation FIRE-MARKER behavioral tests.

OFFLINE + ISOLATED: no paid API, no GPU, no live model. Every ``[activation] <module>:`` marker built
in Wave-3a U2 is proven, per module, to:
  (a) NOT emit when its flag is OFF (OFF byte-identical — the run_log carries no ``[activation]`` line);
  (b) emit with the RIGHT count + bool fields when its flag is ON on eligible input; and
  (c) flip its degraded / noop / build_ok / con-disclosed bool on the silent-fallback path.

The counts are STRUCTURAL presence signals (§-1.3), never thresholds: a count of 0 with the flag ON on
eligible input is itself a valid emission (the "eligible-yet-zero" canary signal).

Covered markers: finding_dedup_nli, basket_consume_finding_dedup, cross_source_body,
numeric_comparator, two_sided_debate.
"""
from __future__ import annotations

import logging
import os
import sys
import types
from pathlib import Path

import pytest

# Repo root on path (tests/polaris_graph/<this> -> parents[2] == repo root).
_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

# Offline: no judge calls, no network entailment, deterministic render-chrome behavior.
os.environ.setdefault("PG_VERIFICATION_MODE", "off")

from src.polaris_graph.synthesis import finding_dedup as fd  # noqa: E402
from src.polaris_graph.synthesis import credibility_pass as cp  # noqa: E402
from src.polaris_graph.generator import cross_source_synthesis as css  # noqa: E402
from src.polaris_graph.generator import numeric_comparator as ncmod  # noqa: E402
from src.polaris_graph.generator import multi_section_generator as msg  # noqa: E402
from src.polaris_graph.synthesis.credibility_pass import BasketMember, ClaimBasket  # noqa: E402


# ── log-capture helper ─────────────────────────────────────────────────────────────────────────────
def _marker_lines(caplog, name: str) -> list[str]:
    """Formatted log messages whose text is the ``[activation] <name>:`` marker."""
    prefix = f"[activation] {name}:"
    return [r.getMessage() for r in caplog.records if r.getMessage().startswith(prefix)]


# ── tiny basket builders (mirror the Wave-2a cross-source test) ─────────────────────────────────────
def _member(eid: str, quote: str) -> BasketMember:
    return BasketMember(
        evidence_id=eid, source_url="", source_tier="",
        origin_cluster_id=f"origin::{eid}", credibility_weight=1.0, authority_score=1.0,
        span=(0, len(quote)), direct_quote=quote, span_verdict="SUPPORTS",
    )


def _basket(cluster_id: str, subject: str, predicate: str, eids) -> ClaimBasket:
    members = [_member(e, f"{subject} {predicate} finding.") for e in eids]
    return ClaimBasket(
        claim_cluster_id=cluster_id, claim_text=f"{subject} {predicate}", subject=subject,
        predicate=predicate, supporting_members=members, refuter_cluster_ids=(),
        weight_mass=1.0, total_clustered_origin_count=len(members),
        verified_support_origin_count=len(members), basket_verdict="full",
    )


_CLAUSES = {
    "cA": "Study A reported an effect [#ev:eA:0-5].",
    "cC": "Study C reported a side effect [#ev:eC:0-5].",
}


def _stub_clause_builder(clause_by_cluster: dict):
    def _stub(basket, _pool, *, writer_fn, verify_fn):
        return clause_by_cluster.get(str(getattr(basket, "claim_cluster_id", "") or ""))
    return _stub


# ═══════════════════════════════════════════════════════════════════════════════════════════════════
# 1) finding_dedup_nli
# ═══════════════════════════════════════════════════════════════════════════════════════════════════
def _fd_rows(bodies):
    return [
        {
            "evidence_id": f"ev{i}",
            "source_url": f"https://host{i}.example.org/x",
            "direct_quote": body,
            "authority_score": 0.7,
            "selection_relevance": 0.7,
        }
        for i, body in enumerate(bodies)
    ]


def _fd_singletons(rows):
    return [[frozenset({rows[i]["direct_quote"]}), (), [i]] for i in range(len(rows))]


def test_finding_dedup_nli_telemetry_merge_and_not_degraded():
    """Real telemetry: a bidirectional-entailing pair MERGES => directional_merges=1, degraded=False."""
    a, b = "AI adoption is concentrated among the largest firms.", \
           "Uptake of these tools skews heavily toward big incumbents."
    rows = _fd_rows([a, b])
    tele: dict = {}
    out = fd._apply_finding_dedup_nli_grouping(
        rows, _fd_singletons(rows),
        entail_fn=lambda p, h: {(a, b): True, (b, a): True}.get((p, h), False),
        telemetry=tele,
    )
    assert any(len(c[2]) >= 2 for c in out), "bidirectional entail must merge"
    assert tele["directional_merges"] == 1
    assert tele["degraded"] is False
    assert tele["wall_truncated"] is False


def test_finding_dedup_nli_telemetry_degraded_on_infra_none():
    """Silent-fallback path: the cross-encoder returns None on NON-empty reps => degraded=True."""
    a, b = "Remote work raised measured output in knowledge roles.", \
           "Distributed teams recorded higher productivity in knowledge work."
    rows = _fd_rows([a, b])
    tele: dict = {}
    out = fd._apply_finding_dedup_nli_grouping(
        rows, _fd_singletons(rows),
        entail_fn=lambda p, h: {(a, b): True, (b, a): None}.get((p, h), False),  # reverse UNAVAILABLE
        telemetry=tele,
    )
    assert not any(len(c[2]) >= 2 for c in out), "an infra None must fail-closed (no merge)"
    assert tele["degraded"] is True, "a None verdict on non-empty reps is the degrade signal"
    assert tele["directional_merges"] == 0


def test_finding_dedup_nli_marker_off_no_emit(monkeypatch, caplog):
    monkeypatch.delenv("PG_FINDING_DEDUP_NLI", raising=False)
    monkeypatch.delenv("PG_CONSOLIDATION_NLI_QUALITATIVE", raising=False)
    with caplog.at_level(logging.INFO, logger="polaris_graph.finding_dedup"):
        fd._build_qualitative_groups([], [], set(), threshold=0.5)
    assert _marker_lines(caplog, "finding_dedup_nli") == [], "OFF must emit no [activation] line"


def test_finding_dedup_nli_marker_on_emits_fields(monkeypatch, caplog):
    monkeypatch.setenv("PG_FINDING_DEDUP_NLI", "1")
    monkeypatch.delenv("PG_CONSOLIDATION_NLI_QUALITATIVE", raising=False)

    def _stub_grouping(rows, clusters, *, entail_fn=None, telemetry=None):
        if telemetry is not None:
            telemetry.update(directional_merges=3, degraded=True, wall_truncated=False)
        return clusters

    monkeypatch.setattr(fd, "_apply_finding_dedup_nli_grouping", _stub_grouping)
    with caplog.at_level(logging.INFO, logger="polaris_graph.finding_dedup"):
        fd._build_qualitative_groups([], [], set(), threshold=0.5)
    lines = _marker_lines(caplog, "finding_dedup_nli")
    assert len(lines) == 1
    assert "invoked directional_merges=3" in lines[0]
    assert "degraded=True" in lines[0]
    assert "wall_truncated=False" in lines[0]


# ═══════════════════════════════════════════════════════════════════════════════════════════════════
# 2) basket_consume_finding_dedup
# ═══════════════════════════════════════════════════════════════════════════════════════════════════
def test_basket_consume_marker_off_no_emit(monkeypatch, caplog):
    monkeypatch.delenv("PG_BASKET_CONSUME_FINDING_DEDUP", raising=False)
    with caplog.at_level(logging.INFO, logger=cp.__name__):
        cp._emit_basket_consume_marker(5, noop=False)
    assert _marker_lines(caplog, "basket_consume_finding_dedup") == []


def test_basket_consume_marker_on_regrouped_and_noop_flip(monkeypatch, caplog):
    monkeypatch.setenv("PG_BASKET_CONSUME_FINDING_DEDUP", "1")
    with caplog.at_level(logging.INFO, logger=cp.__name__):
        cp._emit_basket_consume_marker(4, noop=False)
        cp._emit_basket_consume_marker(0, noop=True)
    lines = _marker_lines(caplog, "basket_consume_finding_dedup")
    assert len(lines) == 2
    assert "regrouped old_to_new=4 noop=False" in lines[0]
    assert "regrouped old_to_new=0 noop=True" in lines[1]


def test_basket_consume_real_noop_path_emits_noop_true(monkeypatch, caplog):
    """The REAL silent-no-op path (an empty-claims graph returns the input UNCHANGED) => noop=True."""
    monkeypatch.setenv("PG_BASKET_CONSUME_FINDING_DEDUP", "1")
    graph = types.SimpleNamespace(claims=[], clusters={}, edges=[])
    with caplog.at_level(logging.INFO, logger=cp.__name__):
        out = cp._regroup_graph_by_finding_dedup(graph, [], gov_suffixes=(), domain=None)
    assert out is graph, "no-claims graph must be returned UNCHANGED (the no-op)"
    lines = _marker_lines(caplog, "basket_consume_finding_dedup")
    assert len(lines) == 1 and "noop=True" in lines[0]


# ═══════════════════════════════════════════════════════════════════════════════════════════════════
# 3) cross_source_body
# ═══════════════════════════════════════════════════════════════════════════════════════════════════
def test_cross_source_body_off_no_emit(monkeypatch, caplog):
    monkeypatch.delenv("PG_CROSS_SOURCE_BODY", raising=False)
    monkeypatch.delenv("PG_NUMERIC_COMPARATOR", raising=False)
    monkeypatch.setattr(css, "_first_verified_clause", _stub_clause_builder(_CLAUSES))
    a = _basket("cA", "drug x", "reduces a1c", ["eA"])
    c = _basket("cC", "drug x", "causes nausea", ["eC"])
    with caplog.at_level(logging.INFO, logger=css.__name__):
        css.compose_cross_source_analytical_units(
            [a, c], {}, writer_fn=lambda *_: "", verify_fn=lambda *_: None, entail_fn=lambda *_: None,
        )
    assert _marker_lines(caplog, "cross_source_body") == [], "OFF must emit no plan-driven/anchor marker"


def test_cross_source_body_on_plan_driven_degraded_when_not_threaded(monkeypatch, caplog):
    """ON + no equiv_clusters/agree_map threaded => input_threaded=False, degraded=True, pairs=1."""
    monkeypatch.setenv("PG_CROSS_SOURCE_BODY", "1")
    monkeypatch.delenv("PG_NUMERIC_COMPARATOR", raising=False)
    monkeypatch.setattr(css, "_first_verified_clause", _stub_clause_builder(_CLAUSES))
    a = _basket("cA", "drug x", "reduces a1c", ["eA"])
    c = _basket("cC", "drug x", "causes nausea", ["eC"])  # SAME subject => a plan-driven facet pair
    with caplog.at_level(logging.INFO, logger=css.__name__):
        css.compose_cross_source_analytical_units(
            [a, c], {}, writer_fn=lambda *_: "", verify_fn=lambda *_: None, entail_fn=lambda *_: None,
        )
    lines = _marker_lines(caplog, "cross_source_body")
    assert len(lines) == 1
    assert "plan_driven pairs=1" in lines[0]
    assert "input_threaded=False" in lines[0]
    assert "degraded=True" in lines[0]


def test_cross_source_body_on_input_threaded_not_degraded(monkeypatch, caplog):
    """ON + a threaded agree_map => input_threaded=True, degraded=False (the not-degraded field)."""
    monkeypatch.setenv("PG_CROSS_SOURCE_BODY", "1")
    monkeypatch.setattr(css, "_first_verified_clause", _stub_clause_builder(_CLAUSES))
    a = _basket("cA", "drug x", "reduces a1c", ["eA"])
    c = _basket("cC", "drug x", "causes nausea", ["eC"])
    with caplog.at_level(logging.INFO, logger=css.__name__):
        css.compose_cross_source_analytical_units(
            [a, c], {}, writer_fn=lambda *_: "", verify_fn=lambda *_: None, entail_fn=lambda *_: None,
            agree_map={("cA", "cC"): True},
        )
    lines = _marker_lines(caplog, "cross_source_body")
    assert len(lines) == 1
    assert "input_threaded=True" in lines[0]
    assert "degraded=False" in lines[0]


# ═══════════════════════════════════════════════════════════════════════════════════════════════════
# 4) numeric_comparator
# ═══════════════════════════════════════════════════════════════════════════════════════════════════
def test_numeric_comparator_off_no_emit(monkeypatch, caplog):
    monkeypatch.delenv("PG_NUMERIC_COMPARATOR", raising=False)
    with caplog.at_level(logging.INFO, logger=css.__name__):
        css.compose_cross_source_analytical_units(
            [], {}, writer_fn=lambda *_: "", verify_fn=lambda *_: None,
        )
    assert _marker_lines(caplog, "numeric_comparator") == []


def test_numeric_comparator_on_build_ok_false_when_lookup_none(monkeypatch, caplog):
    """ON + numeric_key_by_cluster=None (the silent-swallow-made-loud signal) => build_ok=False."""
    monkeypatch.setenv("PG_NUMERIC_COMPARATOR", "1")
    with caplog.at_level(logging.INFO, logger=css.__name__):
        css.compose_cross_source_analytical_units(
            [], {}, writer_fn=lambda *_: "", verify_fn=lambda *_: None,
            numeric_key_by_cluster=None,
        )
    lines = _marker_lines(caplog, "numeric_comparator")
    assert len(lines) == 1
    assert "upgraded=0" in lines[0]
    assert "build_ok=False" in lines[0]


def test_numeric_comparator_on_counts_upgrades_build_ok_true(monkeypatch, caplog):
    """ON + a threaded key lookup + a NEUTRAL pair the comparator upgrades => upgraded=1, build_ok=True."""
    monkeypatch.setenv("PG_CROSS_SOURCE_BODY", "1")
    monkeypatch.setenv("PG_NUMERIC_COMPARATOR", "1")
    monkeypatch.setattr(css, "_first_verified_clause", _stub_clause_builder(_CLAUSES))
    # Force the deterministic comparator to license "comparison" for the neutral facet pair.
    monkeypatch.setattr(ncmod, "license_numeric_comparison", lambda ka, kb: "comparison")
    a = _basket("cA", "drug x", "reduces a1c", ["eA"])
    c = _basket("cC", "drug x", "causes nausea", ["eC"])
    keys = {"cA": ("k", 1.0), "cC": ("k", 2.0)}  # non-None => build_ok True
    with caplog.at_level(logging.INFO, logger=css.__name__):
        css.compose_cross_source_analytical_units(
            [a, c], {}, writer_fn=lambda *_: "", verify_fn=lambda *_: None, entail_fn=lambda *_: None,
            numeric_key_by_cluster=keys,
        )
    lines = _marker_lines(caplog, "numeric_comparator")
    assert len(lines) == 1
    assert "upgraded=1" in lines[0]
    assert "build_ok=True" in lines[0]


# ═══════════════════════════════════════════════════════════════════════════════════════════════════
# 5) two_sided_debate
# ═══════════════════════════════════════════════════════════════════════════════════════════════════
def test_two_sided_debate_marker_off_no_emit(monkeypatch, caplog):
    monkeypatch.delenv("PG_TWO_SIDED_DEBATE", raising=False)
    with caplog.at_level(logging.INFO, logger="polaris_graph.multi_section"):
        msg._emit_two_sided_debate_marker(7, 1)
    assert _marker_lines(caplog, "two_sided_debate") == []


def test_two_sided_debate_marker_on_con_disclosed_flip(monkeypatch, caplog):
    """ON: con_disclosed=1 is the one-sided-pro asymmetry-disclosed signal; con_disclosed=0 = balanced."""
    monkeypatch.setenv("PG_TWO_SIDED_DEBATE", "1")
    with caplog.at_level(logging.INFO, logger="polaris_graph.multi_section"):
        msg._emit_two_sided_debate_marker(9, 1)  # pro present, no con => one asymmetry disclosure
        msg._emit_two_sided_debate_marker(4, 0)  # both sides present => nothing disclosed
    lines = _marker_lines(caplog, "two_sided_debate")
    assert len(lines) == 2
    assert "leg2_inspected=9 con_disclosed=1" in lines[0]
    assert "leg2_inspected=4 con_disclosed=0" in lines[1]


def test_two_sided_debate_real_con_disclosure_when_pro_only(monkeypatch):
    """The REAL con-disclosure helper appends ONE honest asymmetry note when a verified pro but no
    verified con clause is present (the con_disclosed=1 the marker reports)."""
    section = types.SimpleNamespace(title="Benefits and risks", focus="pros and cons of drug x")
    pro_only_units = ["Drug x reduces a1c [#ev:eA:0-5]."]
    out = msg._maybe_two_sided_debate_disclosure(section, [], pro_only_units, [])
    assert len(out) == 1, "a one-sided-pro debate section must disclose exactly one asymmetry note"
