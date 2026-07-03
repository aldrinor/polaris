"""I-deepfix-001 P3_dead_synthesis FIX-1 (#1344) — offline behavioral test for the deterministic
verified multi-cite span-join FALLBACK that revives the dead cross-source synthesis layer.

THE DEFECT (traced): the ~11 eligible multi-source baskets are synthesized by a LIVE LLM FREE
RE-DRAFT whose paraphrase is then re-grounded by the FROZEN ``strict_verify``, which drops every
sentence that reformats a number / moves a ``[#ev:]`` token / loses >=2-word overlap — so all fail
and ``synthesize_cross_source_findings`` returns ``[]`` (proven upstream: zero ``DS-*`` claims).

THE FIX (FIX-1): at the point a basket's LLM draft yields ZERO ``strict_verify`` survivors, fall
back to the DETERMINISTIC verbatim multi-cite span-join the BODY composer already emits
(``compose_basket_multicited_sentence`` with a NULL writer), re-grounded by the SAME ``verify_fn`` —
so the layer produces a real ``DS-*`` digest with >=2 distinct ``[N]`` instead of dropping.

RED/GREEN via the default-ON kill-switch (the flag OFF is the pre-fix code path, byte-identical):
  * ``PG_DEPTH_SYNTHESIS_SPANJOIN_FALLBACK=0`` => the dead-synthesis DROP reproduces (RED: ``[]``).
  * flag ON (default) => the deterministic span-join revives >=1 cross_source finding (GREEN).

The whole test is OFFLINE + deterministic: the LLM synthesizer is an injected fake that returns a
number-mismatch paraphrase (fails the FROZEN strict_verify), and ``verify_fn`` is the REAL
``strict_verify`` over an in-memory evidence pool whose rows carry the members' verbatim quotes — so
the fallback path is exercised end-to-end through the unchanged faithfulness engine, no network, no
model, no spend.

#1335 body-vs-DS duplicate guard: because the FIX-1 span-join reuses the SAME
``compose_basket_multicited_sentence`` the BODY composer runs on the SAME basket, a ``DS-*`` digest can
be text-identical to a body line — the guard drops the duplicate (keeps the body line) and can be made
to fail LOUD via ``PG_DEPTH_SYNTHESIS_BODY_DUP_HARD_ASSERT=1``.
"""

from __future__ import annotations

import re

import pytest

from src.polaris_graph.generator.depth_synthesis import synthesize_cross_source_findings
from src.polaris_graph.generator.provenance_generator import strict_verify

_FALLBACK_ENV = "PG_DEPTH_SYNTHESIS_SPANJOIN_FALLBACK"
_HARD_ASSERT_ENV = "PG_DEPTH_SYNTHESIS_BODY_DUP_HARD_ASSERT"

# Two independent sources stating the SAME qualitative finding in DIFFERENT words (the P3/P4 target
# claim: AI adoption is uneven / concentrated among large firms). Each quote is one clean declarative
# sentence, so its whole span is a verbatim, self-grounding K-span.
_QUOTE_BRYN = (
    "Artificial intelligence adoption remains concentrated among the largest firms in the economy."
)
_QUOTE_OECD = (
    "Uptake of artificial intelligence is uneven and dominated by a small number of very large companies."
)


class _Member:
    """A minimal BasketMember stand-in (duck-typed; the producers use getattr)."""

    def __init__(self, eid: str, quote: str) -> None:
        self.evidence_id = eid
        self.direct_quote = quote
        self.span_verdict = "SUPPORTS"
        self.origin_cluster_id = eid  # distinct origins => a genuine cross-source basket
        self.credibility_weight = 1.0
        self.source_url = f"https://example.org/{eid}"


class _Basket:
    def __init__(self) -> None:
        self.supporting_members = [
            _Member("ev_bryn", _QUOTE_BRYN),
            _Member("ev_oecd", _QUOTE_OECD),
        ]
        self.claim_cluster_id = "c_ai_adoption_uneven"
        self.claim_text = "AI adoption is uneven, concentrated among the largest firms"
        self.subject = self.claim_text
        self.verified_support_origin_count = 2


def _evidence_pool() -> dict:
    # strict_verify + the K-span producer read ``direct_quote`` (or ``statement``); the whole quote is
    # the span, so the emitted ``[#ev:eid:0-len]`` token grounds trivially.
    return {
        "ev_bryn": {"evidence_id": "ev_bryn", "direct_quote": _QUOTE_BRYN},
        "ev_oecd": {"evidence_id": "ev_oecd", "direct_quote": _QUOTE_OECD},
    }


def _dead_llm_synthesizer(_basket, _pool) -> str:
    """The LLM free-redraft failure mode: a paraphrase that INJECTS a number absent from every span, so
    the FROZEN strict_verify drops it (number mismatch) — exactly the dead-synthesis drop FIX-1 cures."""
    end = len(_QUOTE_BRYN)
    return (
        "Artificial intelligence adoption reached 42% concentration among the largest firms "
        f"[#ev:ev_bryn:0-{end}]."
    )


def _bib_map() -> dict:
    return {"ev_bryn": 1, "ev_oecd": 2}


def _run(monkeypatch, *, fallback: str, body_sentences=None):
    monkeypatch.setenv(_FALLBACK_ENV, fallback)
    return synthesize_cross_source_findings(
        [_Basket()],
        _evidence_pool(),
        synthesizer=_dead_llm_synthesizer,
        verify_fn=strict_verify,
        bib_num_by_evidence_id=_bib_map(),
        chrome_screen=lambda _s: False,  # deterministic: the synthetic sentences are not chrome
        body_sentences=body_sentences,
    )


def _distinct_bracket_nums(sentence: str) -> set:
    return set(re.findall(r"\[(\d+)\]", sentence))


# ─────────────────────────────────────────────────────────────────────────────
# RED — flag OFF reproduces the pre-fix dead-synthesis DROP (this is what the fix cures)
# ─────────────────────────────────────────────────────────────────────────────
def test_fix1_off_reproduces_dead_synthesis_drop(monkeypatch):
    findings = _run(monkeypatch, fallback="0")
    assert findings == [], (
        "with the span-join fallback OFF the LLM draft's number-mismatch paraphrase is dropped by "
        "strict_verify and the layer returns [] — the dead-synthesis defect FIX-1 cures"
    )


# ─────────────────────────────────────────────────────────────────────────────
# GREEN — flag ON: the deterministic span-join revives a real cross-source finding
# ─────────────────────────────────────────────────────────────────────────────
def test_fix1_on_revives_cross_source_finding_via_spanjoin(monkeypatch):
    findings = _run(monkeypatch, fallback="1")
    assert len(findings) >= 1, "FIX-1 deterministic span-join must revive the dead basket"
    f = findings[0]
    assert f["tier"] == "cross_source", "two distinct surviving origins => an honest cross_source label"
    assert f["label"] == ""
    nums = _distinct_bracket_nums(f["sentence"])
    assert nums == {"1", "2"}, (
        f"the revived digest must carry BOTH sources' existing [N] (>=2 distinct); got {f['sentence']!r}"
    )
    # No raw provenance token may leak into the rendered sentence.
    assert "[#ev:" not in f["sentence"]


def test_fix1_default_is_on(monkeypatch):
    """Default-ON: with the env var UNSET the fallback fires (the cert slate ships it on)."""
    monkeypatch.delenv(_FALLBACK_ENV, raising=False)
    findings = synthesize_cross_source_findings(
        [_Basket()],
        _evidence_pool(),
        synthesizer=_dead_llm_synthesizer,
        verify_fn=strict_verify,
        bib_num_by_evidence_id=_bib_map(),
        chrome_screen=lambda _s: False,
    )
    assert len(findings) >= 1
    assert findings[0]["tier"] == "cross_source"


# ─────────────────────────────────────────────────────────────────────────────
# #1335 — body-vs-DS duplicate guard: a DS-* digest identical to a body line is dropped / fails loud
# ─────────────────────────────────────────────────────────────────────────────
def test_1335_ds_body_duplicate_is_deduped(monkeypatch):
    # First learn the exact revived digest text (no body dedup).
    baseline = _run(monkeypatch, fallback="1")
    assert baseline, "precondition: the fallback produced a digest"
    ds_line = baseline[0]["sentence"]

    # Now feed that SAME line as an already-rendered BODY sentence => the DS-* duplicate is dropped.
    deduped = _run(monkeypatch, fallback="1", body_sentences=[ds_line])
    assert deduped == [], "the DS-* digest identical to a body line must be dropped (body line kept)"


def test_1335_hard_assert_fails_loud(monkeypatch):
    baseline = _run(monkeypatch, fallback="1")
    ds_line = baseline[0]["sentence"]
    monkeypatch.setenv(_HARD_ASSERT_ENV, "1")
    with pytest.raises(RuntimeError, match="#1335"):
        _run(monkeypatch, fallback="1", body_sentences=[ds_line])


def test_1335_non_duplicate_body_does_not_drop(monkeypatch):
    """A body sentence that is NOT the digest must not suppress the finding (no over-dedup)."""
    findings = _run(
        monkeypatch, fallback="1", body_sentences=["An entirely unrelated body sentence [9]."]
    )
    assert len(findings) >= 1
    assert findings[0]["tier"] == "cross_source"
