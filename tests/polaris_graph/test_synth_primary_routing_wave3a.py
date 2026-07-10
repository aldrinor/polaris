"""I-deepfix-001 Wave-3a (#1344) — SYNTH_PRIMARY routing for the CORROBORATED core body.

Offline unit proof (NO real LLM, NO GPU, NO network — the writer is a STUB, the verifier returns real
``SentenceVerification`` dataclasses, the baskets are in-memory ``SimpleNamespace``) that:

  (a) OFF byte-identical routing — with ``PG_SYNTH_PRIMARY`` unset a corroborated (>=2 distinct-origin
      SUPPORTS) basket STILL routes to the multi-cited K-span co-location (``compose_basket_multicited_
      sentence``), NEVER the synth-primary composer — even when a group-capable ``redraft_fn`` is threaded
      (the flag gates the route, not redraft presence).
  (b) ON route — with ``PG_SYNTH_PRIMARY=1`` and a threaded ``redraft_fn`` the corroborated basket routes
      THROUGH ``compose_basket_multicited_synth_primary`` (the synth-primary group writer), and EVERY
      distinct-origin corroborator the authored prose did not itself cite is still surfaced as its own
      verbatim K-span (§-1.3 consolidate-keep-all — no corroborator citation is dropped).
  (c) Fire marker — ``[activation] synth_primary: authored_prose kept=<N>`` emits with the authored
      sentence count ONLY when authored prose survived, and is ABSENT on an empty / pure-disclosure return
      (Fable R5).

Faithfulness engine (strict_verify / provenance / span-grounding / the writer wrapper) is byte-untouched
by the routing change — these tests exercise WHICH composer runs + that no corroborator is dropped.
"""

from __future__ import annotations

import logging
from types import SimpleNamespace

import src.polaris_graph.generator.verified_compose as vc
from src.polaris_graph.generator.provenance_generator import SentenceVerification

_FAIL_MARKER = "FAILMEPLEASE"
_LOGGER_NAME = "src.polaris_graph.generator.verified_compose"

_Q1 = "Automation displaced routine manufacturing tasks over the decade."
_Q2 = "Reinstatement effects created new labor tasks in the services sector."


# ── fixtures (mirror the Wave-1a offline harness) ──────────────────────────────────────────────────
def _member(eid: str, quote: str, weight: float = 1.0):
    return SimpleNamespace(
        evidence_id=eid,
        direct_quote=quote,
        span_verdict="SUPPORTS",
        credibility_weight=weight,
        supporting_members=None,
    )


def _basket(members, subject="AI and labor market outcomes", cluster_id="clust_1"):
    return SimpleNamespace(
        supporting_members=members,
        subject=subject,
        claim_text=subject,
        claim_cluster_id=cluster_id,
    )


def _pool(*members):
    return {m.evidence_id: {"direct_quote": m.direct_quote} for m in members}


def _tok(eid: str, quote: str) -> str:
    return f"[#ev:{eid}:0-{len(quote)}]"


def _line(text: str, eid: str, quote: str) -> str:
    return f"{text} {_tok(eid, quote)}."


def _sv(sentence: str, *, is_verified: bool, reasons=None):
    return SentenceVerification(
        sentence=sentence,
        tokens=[],
        is_verified=is_verified,
        failure_reasons=list(reasons or []),
        judge_error=False,
    )


def _stub_verify(sentence, _scoped_pool, *args, **kwargs):
    """PASS every sentence WITHOUT the fail marker; the real own-region gate then gates the token."""
    if _FAIL_MARKER in sentence:
        return _sv(sentence, is_verified=False, reasons=["stub_entailment_fail"])
    return _sv(sentence, is_verified=True)


def _corroborated_basket():
    m1, m2 = _member("eva", _Q1), _member("evb", _Q2)
    return _basket([m1, m2]), _pool(m1, m2)


def _spy_both(monkeypatch):
    """Wrap BOTH corroborated composers so a test can assert WHICH one the routing chose."""
    calls = {"multicited": 0, "synth": 0}
    real_multi = vc.compose_basket_multicited_sentence
    real_synth = vc.compose_basket_multicited_synth_primary

    def spy_multi(*a, **k):
        calls["multicited"] += 1
        return real_multi(*a, **k)

    def spy_synth(*a, **k):
        calls["synth"] += 1
        return real_synth(*a, **k)

    monkeypatch.setattr(vc, "compose_basket_multicited_sentence", spy_multi)
    monkeypatch.setattr(vc, "compose_basket_multicited_synth_primary", spy_synth)
    return calls


# ── (a) OFF byte-identical routing ─────────────────────────────────────────────────────────────────
def test_off_corroborated_routes_to_multicited_not_synth(monkeypatch):
    monkeypatch.setenv("PG_VERIFIED_COMPOSE_MULTICITED", "1")
    monkeypatch.delenv("PG_SYNTH_PRIMARY", raising=False)
    basket, pool = _corroborated_basket()
    calls = _spy_both(monkeypatch)

    # redraft_fn is threaded, yet with the flag OFF the corroborated basket MUST still take the
    # multi-cited co-location (the flag gates the route, not the presence of redraft_fn).
    vc._compose_section_per_basket(
        [basket], pool,
        writer_fn=lambda _b, _p: _line("Automation reshaped the labour market", "eva", _Q1),
        verify_fn=_stub_verify,
        redraft_fn=lambda _b, _p, *, revise_reasons=None: "",
    )
    assert calls["multicited"] == 1
    assert calls["synth"] == 0


def test_on_but_no_redraft_still_multicited(monkeypatch):
    """The synth-primary route requires BOTH the flag AND a threaded redraft_fn — flag alone keeps the
    corroborated basket on the multi-cited co-location (byte-identical)."""
    monkeypatch.setenv("PG_VERIFIED_COMPOSE_MULTICITED", "1")
    monkeypatch.setenv("PG_SYNTH_PRIMARY", "1")
    basket, pool = _corroborated_basket()
    calls = _spy_both(monkeypatch)

    vc._compose_section_per_basket(
        [basket], pool,
        writer_fn=lambda _b, _p: _line("Automation reshaped the labour market", "eva", _Q1),
        verify_fn=_stub_verify,
        # redraft_fn omitted (defaults None) => the AND-guard keeps the multi-cited path.
    )
    assert calls["multicited"] == 1
    assert calls["synth"] == 0


# ── (b) ON route + all-corroborator preservation ────────────────────────────────────────────────────
def test_on_corroborated_routes_to_synth_primary(monkeypatch):
    monkeypatch.setenv("PG_VERIFIED_COMPOSE_MULTICITED", "1")
    monkeypatch.setenv("PG_SYNTH_PRIMARY", "1")
    monkeypatch.setenv("PG_WRITER_REPAIR_MAX", "0")
    monkeypatch.setenv("PG_RENDER_CHROME_PROSE_SCREEN", "0")
    basket, pool = _corroborated_basket()
    calls = _spy_both(monkeypatch)

    authored = _line("Automation reshaped the labour market", "eva", _Q1)
    vc._compose_section_per_basket(
        [basket], pool,
        writer_fn=lambda _b, _p: authored,
        verify_fn=_stub_verify,
        redraft_fn=lambda _b, _p, *, revise_reasons=None: authored,
    )
    assert calls["synth"] == 1
    assert calls["multicited"] == 0  # the OLD multi-cited K-span path did NOT compose the core body


def test_synth_primary_preserves_every_corroborator_citation(monkeypatch):
    """Fix 2b (2026-07-10 compose gear-loop iter 2): the synth-primary authored body cites corroborator
    eva; evb (the un-cited corroborator) is kept as a CITATION attached to the authored prose (never a
    dumped verbatim K-span) so NO corroborating source is dropped (§-1.3 consolidate-keep-all)."""
    monkeypatch.setenv("PG_SYNTH_PRIMARY", "1")
    monkeypatch.setenv("PG_WRITER_REPAIR_MAX", "0")
    monkeypatch.setenv("PG_RENDER_CHROME_PROSE_SCREEN", "0")
    basket, pool = _corroborated_basket()

    authored = _line("Automation reshaped the labour market", "eva", _Q1)  # cites eva only
    out = vc.compose_basket_multicited_synth_primary(
        basket, pool,
        writer_fn=lambda _b, _p: authored,
        verify_fn=_stub_verify,
        redraft_fn=lambda _b, _p, *, revise_reasons=None: authored,
    )
    assert "Automation reshaped the labour market" in out  # the authored prose is the primary body
    assert "[#ev:eva:" in out       # corroborator eva (cited by the writer)
    assert "[#ev:evb:" in out       # corroborator evb kept as a CITATION attached to the body (Fix 2b)
    assert _FAIL_MARKER not in out


def test_synth_primary_discloses_when_no_authored_prose(monkeypatch):
    """Fix 2a (2026-07-10 compose gear-loop iter 2): when synth-primary authors NO prose (every draft
    sentence fails verify) under NO_RAW_SPAN, the corroborated basket emits the labeled unverified-
    synthesis DISCLOSURE (the consolidated claim) — NEVER a verbatim whole-span quote-dump (the 4x-block
    / chrome / quote-dump root the fix removes)."""
    monkeypatch.setenv("PG_SYNTH_PRIMARY", "1")
    monkeypatch.setenv("PG_WRITER_REPAIR_MAX", "0")
    monkeypatch.setenv("PG_RENDER_CHROME_PROSE_SCREEN", "0")
    basket, pool = _corroborated_basket()

    bad = f"{_FAIL_MARKER} this authored sentence never verifies."
    out = vc.compose_basket_multicited_synth_primary(
        basket, pool,
        writer_fn=lambda _b, _p: bad,
        verify_fn=_stub_verify,
        redraft_fn=lambda _b, _p, *, revise_reasons=None: bad,
    )
    assert out.strip() != ""        # never a silent empty
    assert _FAIL_MARKER not in out  # the failed authored draft never ships
    # A labeled disclosure line ("[")-prefixed — NEVER a verbatim member span (no raw K-span / quote-dump).
    assert out.lstrip().startswith("[")
    assert "[#ev:" not in out       # no raw provenance token dumped in the held-aside disclosure


# ── (c) fire marker ─────────────────────────────────────────────────────────────────────────────────
def _synth_primary_markers(caplog) -> list[str]:
    return [
        r.getMessage()
        for r in caplog.records
        if "[activation] synth_primary:" in r.getMessage()
    ]


def test_fire_marker_emits_kept_count_on_authored_body(monkeypatch, caplog):
    monkeypatch.setenv("PG_SYNTH_PRIMARY", "1")
    monkeypatch.setenv("PG_WRITER_REPAIR_MAX", "0")
    monkeypatch.setenv("PG_RENDER_CHROME_PROSE_SCREEN", "0")
    basket, pool = _corroborated_basket()
    authored = _line("Automation reshaped the labour market", "eva", _Q1)

    with caplog.at_level(logging.INFO, logger=_LOGGER_NAME):
        vc.compose_basket_multicited_synth_primary(
            basket, pool,
            writer_fn=lambda _b, _p: authored,
            verify_fn=_stub_verify,
            redraft_fn=lambda _b, _p, *, revise_reasons=None: authored,
        )
    # exactly ONE authored sentence survived => kept=1 (structural count, never a threshold).
    assert _synth_primary_markers(caplog) == ["[activation] synth_primary: authored_prose kept=1"]


def test_fire_marker_absent_on_empty_authored_body(monkeypatch, caplog):
    """Fable R5: an empty / pure-disclosure return (no authored prose survived) must NOT fire the
    marker — else the canary would count a disclosure-only exhaustion as 'synth-primary produced prose'."""
    monkeypatch.setenv("PG_SYNTH_PRIMARY", "1")
    monkeypatch.setenv("PG_WRITER_REPAIR_MAX", "0")
    monkeypatch.setenv("PG_RENDER_CHROME_PROSE_SCREEN", "0")
    basket, pool = _corroborated_basket()
    bad = f"{_FAIL_MARKER} this authored sentence never verifies."

    with caplog.at_level(logging.INFO, logger=_LOGGER_NAME):
        vc.compose_basket_multicited_synth_primary(
            basket, pool,
            writer_fn=lambda _b, _p: bad,
            verify_fn=_stub_verify,
            redraft_fn=lambda _b, _p, *, revise_reasons=None: bad,
        )
    assert _synth_primary_markers(caplog) == []  # never fire on an empty authored body


def test_single_source_synth_primary_also_emits_marker(monkeypatch, caplog):
    """The refactored single-basket synth-primary path (_compose_one_basket -> _compose_one_basket_synth_
    primary) still emits the marker when it authors prose (kept=1), proving the marker fires on BOTH the
    single-source and corroborated composers."""
    monkeypatch.setenv("PG_SYNTH_PRIMARY", "1")
    monkeypatch.setenv("PG_WRITER_REPAIR_MAX", "0")
    monkeypatch.setenv("PG_RENDER_CHROME_PROSE_SCREEN", "0")
    m = _member("eva", _Q1)
    basket, pool = _basket([m]), _pool(m)
    authored = _line("Automation reshaped the labour market", "eva", _Q1)

    with caplog.at_level(logging.INFO, logger=_LOGGER_NAME):
        out = vc._compose_one_basket(
            basket, pool,
            writer_fn=lambda _b, _p: authored,
            verify_fn=_stub_verify,
            redraft_fn=lambda _b, _p, *, revise_reasons=None: authored,
        )
    assert out == authored
    assert _synth_primary_markers(caplog) == ["[activation] synth_primary: authored_prose kept=1"]
