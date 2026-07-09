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


# ── N1-FIX-2 — boundary quote-hygiene V2 ─────────────────────────────────────────────────────────

_V2_ENV = "PG_BOUNDARY_QUOTE_HYGIENE_V2"
_STEP4_ENV = "PG_BOUNDARY_QUOTE_HYGIENE"

_CBS_LEAK = "ws.com/team/megan-cerullo/) Updated on: August 28, 2025 [Add CBS News on Google](https://www.goog"


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


def test_v2_drops_on_subject_suffix_for_single_token_subject(monkeypatch):
    """(5) V2 ON: a headline whose subject is the single token 'however' renders the BARE
    'Boundary conditions / counter-evidence:' label — no 'on however' suffix — and the clean quote
    still renders."""
    monkeypatch.setenv(_V2_ENV, "1")
    line = bc.synthesize_boundary_line([_headline_however()], [_clean_qualifier()])
    assert line
    assert "**Boundary conditions / counter-evidence:**" in line
    assert " on however" not in line
    assert "only in certain regions" in line  # clean quote renders


def test_v2_off_keeps_legacy_subject_suffix(monkeypatch):
    """V2 OFF byte-identical: the legacy ' on {subject}' suffix is present for the same inputs."""
    monkeypatch.delenv(_V2_ENV, raising=False)
    line = bc.synthesize_boundary_line([_headline_however()], [_clean_qualifier()])
    assert line
    assert " on however" in line


def test_v2_skips_markdown_url_fragment_quote(monkeypatch):
    """(5) V2 ON: a candidate whose member quote is a markdown-link / URL-fragment leak is skipped
    (no other candidate => empty line)."""
    monkeypatch.setenv(_V2_ENV, "1")
    monkeypatch.setenv(_STEP4_ENV, "0")  # isolate: only V2 governs the hygiene skip
    leak = _bbasket("L", "layoffs increased however only at some media companies", "media layoffs",
                    2.0, _CBS_LEAK)
    headline = _bbasket("hl", "layoffs increased across media companies", "media layoffs", 9.0,
                        "Layoffs increased across media companies.")
    assert bc.synthesize_boundary_line([headline], [leak]) == ""


def test_v2_off_renders_leak_quote_byte_identical(monkeypatch):
    """V2 OFF byte-identical: with BOTH hygiene flags off, the (unscreened) leak quote renders — the
    V2 rule is the only thing that would have skipped it."""
    monkeypatch.delenv(_V2_ENV, raising=False)
    monkeypatch.setenv(_STEP4_ENV, "0")
    leak = _bbasket("L", "layoffs increased however only at some media companies", "media layoffs",
                    2.0, _CBS_LEAK)
    headline = _bbasket("hl", "layoffs increased across media companies", "media layoffs", 9.0,
                        "Layoffs increased across media companies.")
    line = bc.synthesize_boundary_line([headline], [leak])
    assert line
    assert _CBS_LEAK in line


def test_v2_never_mutes_honest_low_weight_counterevidence(monkeypatch):
    """(4) V2 ON never mutes a genuine on-topic low-weight counter-evidence basket with a clean
    full-sentence quote."""
    monkeypatch.setenv(_V2_ENV, "1")
    headline = _bbasket("h2", "robots reduce employment substantially", "robots employment", 9.0,
                        "Robots reduced employment substantially.")
    g = _bbasket("g2", "robots reduce employment however only in some sectors", "robot subgroup", 2.0,
                 "However, robots reduced employment only in some sectors.")
    line = bc.synthesize_boundary_line([headline], [g])
    assert line
    assert "only in some sectors" in line


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
