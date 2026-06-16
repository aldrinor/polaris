"""FIX 1 + FIX 2 — basket sibling re-anchor (strict_verify over-drop) and Sentinel
transport-blank retry.

Both fixes default to current behavior (byte-identical OFF) and STRENGTHEN, never
relax, faithfulness:

FIX 2 (Sentinel transport-blank retry, PG_SENTINEL_BLANK_RETRIES, default 0):
  - default 0 -> a blank empty-200 falls straight into the parser -> _FAIL_CLOSED
    (UNGROUNDED, parsed_ok=False); record list stays 1 element (byte-identical).
  - >=1 -> a RAW-TEXT-BLANK empty-200 is retried up to N times; a real verdict on a
    later attempt is returned; each blank attempt is recorded for audit.
  - exhaustion stays UNGROUNDED parsed_ok=False (NEVER GROUNDED on a blank).
  - a NON-EMPTY-unparseable output and a genuine clean UNGROUNDED are NOT retried
    (the predicate is the raw-text blank, not parsed_ok).

FIX 1 (basket sibling re-anchor, PG_BASKET_REPAIR_MAX_CYCLES, default 0):
  - default 0 -> no re-anchor pass is constructed (dropped list unchanged).
  - >=1 + enforce entailment -> a single-cited, single-cluster dropped sentence is
    re-anchored to a basket sibling that INDEPENDENTLY passes the single-span
    isolation verify on the FULL claim; the shipped sentence is byte-identical to
    the verified one (re-pointed [#ev] token only).
  - a sibling that does NOT independently pass stays dropped (no laundering).
  - a multi-cluster cited token is never re-anchored (anti-cross-claim).

No network: a canned transport for FIX 2; a deterministic fake verifier for FIX 1.
"""

from __future__ import annotations

from src.polaris_graph.roles.role_transport import (
    EvidenceDocument,
    RoleRequest,
    RoleResponse,
)
from src.polaris_graph.roles.sentinel_adapter import run_sentinel
from src.polaris_graph.roles.sentinel_contract import SentinelVerdict

_MODEL = "ibm-granite/granite-4.1-8b"  # noninverted (benchmark) default mode
_CLAIM = "Tirzepatide lowered HbA1c by 2.3 points."
_DOCS = [
    EvidenceDocument(doc_id="doc1", text="HbA1c fell 2.3 points across arms."),
]


class _SequenceTransport:
    """Returns a fixed sequence of raw_text payloads, one per complete() call."""

    def __init__(self, payloads: list[str], served_model: str | None = _MODEL) -> None:
        self._payloads = list(payloads)
        self._served = served_model
        self.calls = 0

    def complete(self, request: RoleRequest) -> RoleResponse:
        idx = min(self.calls, len(self._payloads) - 1)
        self.calls += 1
        return RoleResponse(raw_text=self._payloads[idx], served_model=self._served)


# ─────────────────────────────────────────────────────────────────────────────
# FIX 2 — Sentinel transport-blank retry
# ─────────────────────────────────────────────────────────────────────────────


def test_fix2_off_default_blank_is_byte_identical(monkeypatch) -> None:
    """Default (flag unset) -> a blank empty-200 falls into the parser -> UNGROUNDED
    parsed_ok=False, exactly ONE transport call, exactly ONE record (byte-identical)."""
    monkeypatch.delenv("PG_SENTINEL_BLANK_RETRIES", raising=False)
    transport = _SequenceTransport(["", "GROUNDED"])  # 2nd would succeed IF retried
    result, records = run_sentinel(
        transport, _CLAIM, _DOCS, model_slug=_MODEL, mode="noninverted"
    )
    assert transport.calls == 1  # NO retry at default 0
    assert len(records) == 1  # 1-element record list (existing invariant)
    assert result.verdict == SentinelVerdict.UNGROUNDED
    assert result.parsed_ok is False  # fail-closed on the blank


def test_fix2_retry_recovers_real_verdict_on_later_attempt(monkeypatch) -> None:
    """With retries on, a blank empty-200 followed by a real GROUNDED returns the real
    verdict; the blank attempt is recorded so the retry is auditable."""
    monkeypatch.setenv("PG_SENTINEL_BLANK_RETRIES", "2")
    transport = _SequenceTransport(["", "GROUNDED"])
    result, records = run_sentinel(
        transport, _CLAIM, _DOCS, model_slug=_MODEL, mode="noninverted"
    )
    assert transport.calls == 2  # one retry consumed
    assert len(records) == 2  # blank attempt + final attempt both recorded
    assert result.verdict == SentinelVerdict.GROUNDED
    assert result.parsed_ok is True


def test_fix2_exhaustion_stays_ungrounded_never_grounded(monkeypatch) -> None:
    """All attempts blank -> result STAYS UNGROUNDED parsed_ok=False. The retry NEVER
    converts a blank into GROUNDED (the A3 headline faithfulness invariant)."""
    monkeypatch.setenv("PG_SENTINEL_BLANK_RETRIES", "3")
    transport = _SequenceTransport(["", "   ", "\n", ""])  # always blank
    result, records = run_sentinel(
        transport, _CLAIM, _DOCS, model_slug=_MODEL, mode="noninverted"
    )
    assert transport.calls == 4  # initial + 3 retries
    assert result.verdict == SentinelVerdict.UNGROUNDED
    assert result.parsed_ok is False


def test_fix2_genuine_ungrounded_not_retried(monkeypatch) -> None:
    """A clean UNGROUNDED (parsed_ok=True, NOT blank) is NEVER retried even with
    retries on — the predicate is the raw-text blank, not parsed_ok==False."""
    monkeypatch.setenv("PG_SENTINEL_BLANK_RETRIES", "5")
    transport = _SequenceTransport(["UNGROUNDED", "GROUNDED"])
    result, records = run_sentinel(
        transport, _CLAIM, _DOCS, model_slug=_MODEL, mode="noninverted"
    )
    assert transport.calls == 1  # genuine UNGROUNDED not retried
    assert result.verdict == SentinelVerdict.UNGROUNDED
    assert result.parsed_ok is True


def test_fix2_nonempty_unparseable_not_retried(monkeypatch) -> None:
    """A NON-EMPTY but unparseable output (parsed_ok=False yet not blank) is NOT
    retried — only raw-text blanks are. It fails closed exactly as today."""
    monkeypatch.setenv("PG_SENTINEL_BLANK_RETRIES", "5")
    transport = _SequenceTransport(["maybe grounded?", "GROUNDED"])
    result, records = run_sentinel(
        transport, _CLAIM, _DOCS, model_slug=_MODEL, mode="noninverted"
    )
    assert transport.calls == 1  # unparseable-but-present not retried
    assert result.verdict == SentinelVerdict.UNGROUNDED
    assert result.parsed_ok is False


# ─────────────────────────────────────────────────────────────────────────────
# FIX 1 — basket sibling re-anchor
# ─────────────────────────────────────────────────────────────────────────────

from src.polaris_graph.generator.multi_section_generator import (  # noqa: E402
    _recover_via_sibling_basket,
)
from src.polaris_graph.generator.provenance_generator import (  # noqa: E402
    SentenceVerification,
    parse_provenance_tokens,
)


class _FakeBasket:
    def __init__(self, cluster_id, members):
        self.claim_cluster_id = cluster_id
        self.supporting_members = members


class _FakeMember:
    def __init__(self, evidence_id):
        self.evidence_id = evidence_id


class _FakeCredAnalysis:
    def __init__(self, baskets, cluster_id_by_evidence):
        self.baskets = baskets
        self.cluster_id_by_evidence = cluster_id_by_evidence


def _dropped_sv(sentence: str) -> SentenceVerification:
    return SentenceVerification(
        sentence=sentence,
        tokens=parse_provenance_tokens(sentence),
        is_verified=False,
        failure_reasons=["no_content_word_overlap_any_cited_span:ev_fail"],
    )


_CLAIM_TEXT = "Semaglutide reduced body weight by 14 percent."
# The dropped sentence cites ev_fail (its own span lacks the claim) — over-dropped.
_DROPPED_SENTENCE = f"{_CLAIM_TEXT} [#ev:ev_fail:0-5]"


def _pool_with_supporting_sibling():
    return {
        "ev_fail": {"evidence_id": "ev_fail", "direct_quote": "Other."},
        "ev_good": {
            "evidence_id": "ev_good",
            "direct_quote": _CLAIM_TEXT,  # the sibling span DOES contain the claim
        },
    }


def test_fix1_off_default_no_reanchor(monkeypatch) -> None:
    """Default (PG_BASKET_REPAIR_MAX_CYCLES unset) + enforce -> no re-anchor pass; the
    dropped list is returned unchanged (byte-identical OFF path)."""
    monkeypatch.delenv("PG_BASKET_REPAIR_MAX_CYCLES", raising=False)
    monkeypatch.setenv("PG_STRICT_VERIFY_ENTAILMENT", "enforce")
    cred = _FakeCredAnalysis(
        baskets=[_FakeBasket("c1", [_FakeMember("ev_fail"), _FakeMember("ev_good")])],
        cluster_id_by_evidence={"ev_fail": ["c1"], "ev_good": ["c1"]},
    )
    dropped = [_dropped_sv(_DROPPED_SENTENCE)]
    recovered, still = _recover_via_sibling_basket(
        dropped, _pool_with_supporting_sibling(), cred
    )
    assert recovered == []
    assert len(still) == 1
    assert still[0].is_verified is False  # untouched


def test_fix1_enforce_gate_no_reanchor_outside_enforce(monkeypatch) -> None:
    """Even with cycles>0, OFF/WARN entailment -> no re-anchor (the enforce-only accept
    gate: a search-for-a-passing-sibling outside enforce would launder a drop)."""
    monkeypatch.setenv("PG_BASKET_REPAIR_MAX_CYCLES", "3")
    monkeypatch.setenv("PG_STRICT_VERIFY_ENTAILMENT", "off")
    cred = _FakeCredAnalysis(
        baskets=[_FakeBasket("c1", [_FakeMember("ev_fail"), _FakeMember("ev_good")])],
        cluster_id_by_evidence={"ev_fail": ["c1"], "ev_good": ["c1"]},
    )
    recovered, still = _recover_via_sibling_basket(
        [_dropped_sv(_DROPPED_SENTENCE)], _pool_with_supporting_sibling(), cred
    )
    assert recovered == []
    assert len(still) == 1


def test_fix1_reanchors_to_independently_entailing_sibling(monkeypatch) -> None:
    """cycles>0 + enforce + a sibling whose own span independently entails the FULL
    claim -> the dropped sentence is re-anchored (re-cited to the sibling), KEPT, and
    the shipped sentence is byte-identical to the isolation-verified construction."""
    monkeypatch.setenv("PG_BASKET_REPAIR_MAX_CYCLES", "3")
    monkeypatch.setenv("PG_STRICT_VERIFY_ENTAILMENT", "enforce")
    cred = _FakeCredAnalysis(
        baskets=[_FakeBasket("c1", [_FakeMember("ev_fail"), _FakeMember("ev_good")])],
        cluster_id_by_evidence={"ev_fail": ["c1"], "ev_good": ["c1"]},
    )
    pool = _pool_with_supporting_sibling()
    recovered, still = _recover_via_sibling_basket(
        [_dropped_sv(_DROPPED_SENTENCE)], pool, cred
    )
    assert len(recovered) == 1
    assert still == []
    sv = recovered[0]
    assert sv.is_verified is True
    # SHIP-THE-SAME-ONE: byte-identical to the isolation-verified string.
    span_len = len(pool["ev_good"]["direct_quote"])
    assert sv.sentence == f"{_CLAIM_TEXT} [#ev:ev_good:0-{span_len}]"
    assert [t.evidence_id for t in sv.tokens] == ["ev_good"]
    assert any("FIX1_sibling_basket_reanchor" in w for w in sv.soft_warnings)


def test_fix1_no_sibling_passes_stays_dropped(monkeypatch) -> None:
    """When NO sibling independently entails the full claim, the sentence stays dropped
    (no laundering; the existing drop+disclose path is preserved)."""
    monkeypatch.setenv("PG_BASKET_REPAIR_MAX_CYCLES", "3")
    monkeypatch.setenv("PG_STRICT_VERIFY_ENTAILMENT", "enforce")
    cred = _FakeCredAnalysis(
        baskets=[_FakeBasket("c1", [_FakeMember("ev_fail"), _FakeMember("ev_bad")])],
        cluster_id_by_evidence={"ev_fail": ["c1"], "ev_bad": ["c1"]},
    )
    pool = {
        "ev_fail": {"evidence_id": "ev_fail", "direct_quote": "Other."},
        "ev_bad": {"evidence_id": "ev_bad", "direct_quote": "Unrelated content here."},
    }
    recovered, still = _recover_via_sibling_basket(
        [_dropped_sv(_DROPPED_SENTENCE)], pool, cred
    )
    assert recovered == []
    assert len(still) == 1
    assert still[0].is_verified is False


def test_fix1_multi_cluster_token_not_reanchored(monkeypatch) -> None:
    """A cited evidence_id mapping to MORE THAN ONE cluster is NEVER re-anchored
    (anti-cross-claim rule: a multi-cluster token can't be attributed to ONE claim)."""
    monkeypatch.setenv("PG_BASKET_REPAIR_MAX_CYCLES", "3")
    monkeypatch.setenv("PG_STRICT_VERIFY_ENTAILMENT", "enforce")
    cred = _FakeCredAnalysis(
        baskets=[_FakeBasket("c1", [_FakeMember("ev_fail"), _FakeMember("ev_good")])],
        # ev_fail maps to TWO clusters -> ambiguous -> skip.
        cluster_id_by_evidence={"ev_fail": ["c1", "c2"], "ev_good": ["c1"]},
    )
    recovered, still = _recover_via_sibling_basket(
        [_dropped_sv(_DROPPED_SENTENCE)], _pool_with_supporting_sibling(), cred
    )
    assert recovered == []
    assert len(still) == 1


def test_fix1_none_credibility_analysis_noop(monkeypatch) -> None:
    """credibility_analysis is None (master flag OFF / always-release degrade) -> the
    recovery no-ops and returns the dropped list unchanged."""
    monkeypatch.setenv("PG_BASKET_REPAIR_MAX_CYCLES", "3")
    monkeypatch.setenv("PG_STRICT_VERIFY_ENTAILMENT", "enforce")
    dropped = [_dropped_sv(_DROPPED_SENTENCE)]
    recovered, still = _recover_via_sibling_basket(
        dropped, _pool_with_supporting_sibling(), None
    )
    assert recovered == []
    assert len(still) == 1
