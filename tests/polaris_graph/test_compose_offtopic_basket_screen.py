"""N1-FIX-1 / N6-FIX-A (merged, I-deepfix-001 wave-2) — OFF-TOPIC BASKET SCREEN.

Pure Python, no network / GPU / LLM. Proves the merged screen (ONE flag
``PG_COMPOSE_OFFTOPIC_BASKET_SCREEN``, default OFF) WITHHOLDS an off-topic-ONLY basket from the
verified-compose set while keeping mixed / protected / unjudged / missing-row baskets, and proves
flag-OFF byte-identity. Also covers N1-FIX-2 boundary quote-hygiene V2 (``PG_BOUNDARY_QUOTE_HYGIENE_V2``):
markdown-link / URL-fragment quotes are skipped and the "on {subject}" suffix is dropped for a
single-token garbage subject — both default OFF byte-identical.
"""
from __future__ import annotations

import importlib
from types import SimpleNamespace

import pytest

vc = importlib.import_module("src.polaris_graph.generator.verified_compose")
bc = importlib.import_module("src.polaris_graph.generator.boundary_conditions")

_SCREEN_ENV = "PG_COMPOSE_OFFTOPIC_BASKET_SCREEN"


def _member(eid):
    return SimpleNamespace(evidence_id=eid)


def _basket(ccid, *eids):
    return SimpleNamespace(
        claim_cluster_id=ccid,
        supporting_members=[_member(e) for e in eids],
    )


def _pool():
    # the exact drb_72 shapes
    return {
        "ev_on": {"content_relevance_label": "relevant"},
        "ev_off1": {"topic_offtopic_demoted": True, "content_relevance_label": "demoted"},
        "ev_off2": {"topic_offtopic_demoted": True, "content_relevance_label": "demoted"},
        "ev_prot": {"topic_offtopic_demoted": True, "content_relevance_label": "escalated_relevant"},
        "ev_unjudged": {},
    }


def _baskets():
    a = _basket("A", "ev_on")                # on-topic
    b = _basket("B", "ev_off1", "ev_off2")   # off-topic-ONLY
    c = _basket("C", "ev_off1", "ev_on")     # mixed
    d = _basket("D", "ev_prot")              # protected (override)
    e = _basket("E", "ev_unjudged")          # unjudged
    return a, b, c, d, e


def _cred(baskets):
    return SimpleNamespace(baskets=list(baskets))


def _section():
    return SimpleNamespace(ev_ids=["ev_on", "ev_off1", "ev_off2", "ev_prot", "ev_unjudged"])


def test_flag_off_is_byte_identical_noop(monkeypatch):
    """(1) FLAG OFF (env unset): the call WITH the evidence_pool kwarg returns exactly the same
    basket sequence as the call WITHOUT it."""
    monkeypatch.delenv(_SCREEN_ENV, raising=False)
    a, b, c, d, e = _baskets()
    cred = _cred((a, b, c, d, e))
    section = _section()
    with_pool = vc._section_baskets_for_compose(section, cred, evidence_pool=_pool())
    without_pool = vc._section_baskets_for_compose(section, cred)
    assert with_pool == without_pool
    assert without_pool == [a, b, c, d, e]  # every basket kept when the screen is off


def test_flag_on_withholds_only_offtopic_only_basket(monkeypatch):
    """(2) FLAG ON: basket B (off-topic ONLY) is withheld; A, C (mixed), D (protected),
    E (unjudged) are all KEPT."""
    monkeypatch.setenv(_SCREEN_ENV, "1")
    a, b, c, d, e = _baskets()
    out = vc._section_baskets_for_compose(_section(), _cred((a, b, c, d, e)), evidence_pool=_pool())
    assert b not in out
    assert out == [a, c, d, e]


def test_basket_confirmed_offtopic_unit(monkeypatch):
    """(3) `_basket_confirmed_offtopic` unit: True ONLY for the off-topic-only basket; a basket
    whose member eid is absent from the pool fails open (False => KEEP)."""
    monkeypatch.setenv(_SCREEN_ENV, "1")  # helper reads the pool directly; flag not consulted here
    a, b, c, d, e = _baskets()
    pool = _pool()
    assert vc._basket_confirmed_offtopic(b, pool) is True
    assert vc._basket_confirmed_offtopic(a, pool) is False
    assert vc._basket_confirmed_offtopic(c, pool) is False
    assert vc._basket_confirmed_offtopic(d, pool) is False
    assert vc._basket_confirmed_offtopic(e, pool) is False
    missing = _basket("F", "ev_absent_from_pool")
    assert vc._basket_confirmed_offtopic(missing, pool) is False  # fail-open on missing row


def test_override_flag_off_still_withholds_but_not_protected(monkeypatch):
    """The screen never suppresses a W2-relevance-protected basket even while the topic flag fires,
    because it reuses _is_confirmed_offtopic's built-in override (default ON)."""
    monkeypatch.setenv(_SCREEN_ENV, "1")
    a, b, c, d, e = _baskets()
    out = vc._section_baskets_for_compose(_section(), _cred((d,)), evidence_pool=_pool())
    assert out == [d]  # protected basket survives


# ── Fix 1 (P0-1, 2026-07-10 compose gear-loop iter 2) — boundary line renders SYNTHESIS, not a quote ──
# The deleted N1-FIX-2 quote-hygiene V2 screens (`_quote_is_unrenderable`, PG_BOUNDARY_QUOTE_HYGIENE*)
# were mechanical lexical screens on RAW member text. They are removed: the boundary line no longer
# quotes raw member text AT ALL — it renders ONE LLM-synthesized qualifier sentence (passed by cluster
# id) plus a citation label, so there is nothing raw to screen. These tests replace the V2 suite.


def _bmember(eid, quote):
    return SimpleNamespace(
        evidence_id=eid, direct_quote=quote, span_verdict="SUPPORTS",
        source_url="https://example.org/x", source_tier="T5",
    )


def _bbasket(ccid, claim_text, subject, weight, quote):
    return SimpleNamespace(
        claim_cluster_id=ccid, claim_text=claim_text, subject=subject, predicate="",
        weight_mass=weight, refuter_cluster_ids=(),
        supporting_members=[_bmember(f"ev_{ccid}", quote)],
    )


def _headline_however():
    # subject is the single garbage token "however"; claim_text carries the real content words.
    return _bbasket("h", "automation reduces manufacturing employment", "however", 9.0,
                    "Automation reduced manufacturing employment overall.")


def _clean_qualifier():
    return _bbasket(
        "q", "automation reduces manufacturing employment only in certain regions however", "subgroup",
        2.0, "However, automation reduced manufacturing employment only in certain regions.",
    )


def test_boundary_line_renders_synthesis_and_bare_label_for_garbage_subject():
    """Fix 1 (P0-1): the boundary line renders the SYNTHESIZED sentence (passed by cluster id) with the
    BARE 'Boundary conditions / counter-evidence:' label — no ' on however' suffix for a single-token
    subject — and never a raw provenance token."""
    synth = {"q": "The reduction held only in certain regions [#ev:ev_q:0-10]."}
    line = bc.synthesize_boundary_line([_headline_however()], [_clean_qualifier()], synth)
    assert line
    assert "**Boundary conditions / counter-evidence:**" in line
    assert " on however" not in line
    assert "held only in certain regions" in line
    assert "[#ev:" not in line


def test_boundary_line_without_synthesis_never_quotes_raw_member():
    """Fix 1 (P0-1): with NO synthesized sentence available, the line is empty — the raw member quote is
    NEVER dumped (the class the deleted V2 screens were band-aiding)."""
    leak = "ws.com/team/megan-cerullo/) Updated on: August 28, 2025 [Add CBS News on Google](https://www.goog"
    lb = _bbasket("L", "layoffs increased however only at some media companies", "media layoffs", 2.0, leak)
    headline = _bbasket("hl", "layoffs increased across media companies", "media layoffs", 9.0,
                        "Layoffs increased across media companies.")
    line = bc.synthesize_boundary_line([headline], [lb])
    assert line == ""
    assert leak not in line


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
