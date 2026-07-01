"""I-deepfix-001 WS-8 (D4) THIRD headline path — depth cross-source SYNTHESIS recency re-rank.

Codex found ``depth_synthesis.synthesize_cross_source_findings`` orders/consumes
``credibility_analysis.baskets`` DIRECTLY (the ``for basket in baskets`` loop), bypassing the
recency-ordered unbound-supports selection — so a very-old source can still headline the Analysis
section. This leg DEMOTES an older basket in the synthesis ORDER (a WEIGHT on ordering, NEVER a drop:
every basket is kept and still synthesized — §-1.3). Journal-class only; byte-identical when
off / non-journal-class / unknown-year.

Behavioral, OFFLINE (fixture baskets + injected synthesizer/verify_fn — zero spend, no GPU/model call).
Proves the helper curve, the basket-level newest-year, AND that the synthesis loop actually CONSUMES the
recency order (wiring guard).
"""
import inspect
import os
import sys
import types

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from src.polaris_graph.generator import depth_synthesis as ds  # noqa: E402


# ── fixtures ──────────────────────────────────────────────────────────────────────────────────────
class _FakeMember:
    def __init__(self, evidence_id, origin, quote="verified span text here", weight=1.0):
        self.evidence_id = evidence_id
        self.origin_cluster_id = origin
        self.direct_quote = quote
        self.span_verdict = "SUPPORTS"
        self.credibility_weight = weight
        self.source_url = ""
        self.source_tier = ""


class _FakeBasket:
    def __init__(self, cid, members):
        self.claim_cluster_id = cid
        self.claim_text = cid
        self.subject = cid
        self.supporting_members = members


def _two_origin_basket(cid, eid_a, eid_b):
    """A basket clearing the definitional >=2-distinct-origin floor (so it is a cross-source CANDIDATE)."""
    return _FakeBasket(cid, [_FakeMember(eid_a, "o_" + eid_a), _FakeMember(eid_b, "o_" + eid_b)])


def _clear(monkeypatch):
    for k in (
        "PG_DOCUMENT_TYPE_WEIGHT", "PG_DEPTH_RECENCY_RERANK",
        "PG_M2_RECENCY_GRACE_YEARS", "PG_M2_RECENCY_DECAY_PER_YEAR", "PG_M2_RECENCY_FLOOR",
    ):
        monkeypatch.delenv(k, raising=False)


# ── unit: gate / parse / curve ──────────────────────────────────────────────────────────────────
def test_enabled_only_for_journal_class(monkeypatch):
    _clear(monkeypatch)
    assert ds._depth_recency_rerank_enabled() is False, "OFF without PG_DOCUMENT_TYPE_WEIGHT (non-journal run)"
    monkeypatch.setenv("PG_DOCUMENT_TYPE_WEIGHT", "1")
    assert ds._depth_recency_rerank_enabled() is True, "ON for a journal-class run"
    monkeypatch.setenv("PG_DEPTH_RECENCY_RERANK", "0")
    assert ds._depth_recency_rerank_enabled() is False, "kill-switch OFF disables it even journal-class"


def test_publication_year_parse(monkeypatch):
    _clear(monkeypatch)
    assert ds._ds_publication_year({"year": 2024}) == 2024
    assert ds._ds_publication_year({"title": "Robotics, J. Operations Mgmt (1986)"}) == 1986
    assert ds._ds_publication_year({"url": "https://example.org/archive/1999/paper"}) == 1999
    assert ds._ds_publication_year({"doi": "10.1000/j.2015.03.001"}) == 2015
    assert ds._ds_publication_year({"statement": "no year here"}) is None
    assert ds._ds_publication_year(None) is None
    assert ds._ds_publication_year("not a dict") is None


def test_recency_factor_curve(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("PG_DOCUMENT_TYPE_WEIGHT", "1")
    old = ds._depth_recency_factor(1986, 2024)
    recent = ds._depth_recency_factor(2023, 2024)
    assert recent == 1.0
    assert 0.0 < old < recent, "a 1986 basket is demoted in the ordering (never zero)"
    assert ds._depth_recency_factor(1500, 2024) >= 0.25, "floored — never dropped"


def test_recency_factor_byte_identical_when_off_or_unknown(monkeypatch):
    _clear(monkeypatch)
    # non-journal run => factor 1.0 regardless of age.
    assert ds._depth_recency_factor(1986, 2024) == 1.0
    monkeypatch.setenv("PG_DOCUMENT_TYPE_WEIGHT", "1")
    # journal-class but unknown year => 1.0 (never guessed).
    assert ds._depth_recency_factor(None, 2024) == 1.0
    # journal-class but no corpus reference year => 1.0.
    assert ds._depth_recency_factor(1986, None) == 1.0


def test_basket_newest_year(monkeypatch):
    _clear(monkeypatch)
    pool = {"a": {"year": 2010}, "b": {"year": 2024}, "c": {"statement": "no year"}}
    assert ds._basket_newest_year(_two_origin_basket("x", "a", "b"), pool) == 2024, "newest among members"
    assert ds._basket_newest_year(_two_origin_basket("y", "c", "c2"), pool) is None, "no parseable year => None"


# ── basket ordering: the headline demotion ───────────────────────────────────────────────────────
def _old_and_recent_baskets():
    old = _two_origin_basket("BASKET_OLD", "old1", "old2")     # newest 1986
    recent = _two_origin_basket("BASKET_RECENT", "new1", "new2")  # newest 2024
    pool = {
        "old1": {"year": 1986}, "old2": {"year": 1980},
        "new1": {"year": 2024}, "new2": {"year": 2020},
    }
    return old, recent, pool


def test_old_basket_sorts_after_recent_when_journal_class(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("PG_DOCUMENT_TYPE_WEIGHT", "1")
    old, recent, pool = _old_and_recent_baskets()
    ordered = ds._order_baskets_by_recency([old, recent], pool)
    assert [b.claim_cluster_id for b in ordered] == ["BASKET_RECENT", "BASKET_OLD"], (
        "the 1986 basket is demoted BELOW the 2024 basket in the synthesis order"
    )
    assert len(ordered) == 2 and old in ordered and recent in ordered, "both baskets KEPT (no drop — §-1.3)"


def test_byte_identical_order_when_off(monkeypatch):
    _clear(monkeypatch)  # journal-class OFF
    old, recent, pool = _old_and_recent_baskets()
    ordered = ds._order_baskets_by_recency([old, recent], pool)
    assert [b.claim_cluster_id for b in ordered] == ["BASKET_OLD", "BASKET_RECENT"], (
        "non-journal run => input order UNCHANGED (byte-identical)"
    )


def test_byte_identical_order_when_kill_switch_off(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("PG_DOCUMENT_TYPE_WEIGHT", "1")
    monkeypatch.setenv("PG_DEPTH_RECENCY_RERANK", "0")
    old, recent, pool = _old_and_recent_baskets()
    ordered = ds._order_baskets_by_recency([old, recent], pool)
    assert [b.claim_cluster_id for b in ordered] == ["BASKET_OLD", "BASKET_RECENT"], (
        "kill-switch OFF => input order UNCHANGED (byte-identical)"
    )


def test_byte_identical_order_when_unknown_year(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("PG_DOCUMENT_TYPE_WEIGHT", "1")
    old = _two_origin_basket("BASKET_A", "a1", "a2")
    other = _two_origin_basket("BASKET_B", "b1", "b2")
    pool = {"a1": {"statement": "no year"}, "a2": {}, "b1": {"title": "untitled"}, "b2": {}}
    ordered = ds._order_baskets_by_recency([old, other], pool)
    assert [b.claim_cluster_id for b in ordered] == ["BASKET_A", "BASKET_B"], (
        "no basket carries a parseable year => input order UNCHANGED (byte-identical)"
    )


# ── wiring guard: the synthesis loop actually CONSUMES the recency order ──────────────────────────
class _FakeVerified:
    def __init__(self, sentences):
        self.kept_sentences = [types.SimpleNamespace(sentence=s) for s in sentences]


def _fake_verify(draft, _scoped_pool):
    return _FakeVerified([draft])


def _fake_synth(basket, _pool):
    # ONE grounded sentence citing this basket's first member with a valid provenance token.
    m = basket.supporting_members[0]
    return f"Finding for {basket.claim_cluster_id} [#ev:{m.evidence_id}:0-5]"


def test_synthesize_consumes_recency_order_when_journal_class(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("PG_DOCUMENT_TYPE_WEIGHT", "1")
    old, recent, pool = _old_and_recent_baskets()
    findings = ds.synthesize_cross_source_findings(
        [old, recent], pool,
        synthesizer=_fake_synth, verify_fn=_fake_verify,
        chrome_screen=lambda s: False,  # isolate ordering from the chrome screen
    )
    order = [f["sentence"] for f in findings]
    assert len(order) == 2, "both baskets synthesized (no drop)"
    assert "BASKET_RECENT" in order[0] and "BASKET_OLD" in order[1], (
        "the 2024 basket's finding headlines; the 1986 basket's finding is demoted BELOW it"
    )


def test_synthesize_byte_identical_order_when_off(monkeypatch):
    _clear(monkeypatch)  # journal-class OFF
    old, recent, pool = _old_and_recent_baskets()
    findings = ds.synthesize_cross_source_findings(
        [old, recent], pool,
        synthesizer=_fake_synth, verify_fn=_fake_verify,
        chrome_screen=lambda s: False,
    )
    order = [f["sentence"] for f in findings]
    assert len(order) == 2
    assert "BASKET_OLD" in order[0] and "BASKET_RECENT" in order[1], (
        "non-journal run => the synthesis output preserves the input basket order (byte-identical)"
    )


def test_loop_uses_ordered_baskets_source_guard():
    """Wiring guard: the loop iterates recency-ordered baskets AND the re-order is CAP-GATED (cap<=0) —
    the P0 fix so a positive cap never turns an old-basket demotion into a DROP (§-1.3)."""
    src = inspect.getsource(ds.synthesize_cross_source_findings)
    assert "_order_baskets_by_recency(baskets, evidence_pool)" in src, (
        "the synthesis loop must be able to iterate recency-ordered baskets"
    )
    assert "for basket in ordered_baskets:" in src
    assert "if cap <= 0" in src, (
        "recency re-order must be CAP-GATED (cap<=0) so a positive cap never turns demotion into a drop"
    )


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-q"]))
