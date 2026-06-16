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

from src.polaris_graph.clinical_generator import strict_verify  # noqa: E402
from src.polaris_graph.generator.multi_section_generator import (  # noqa: E402
    _basket_repair_enabled,
    _basket_repair_max_cycles,
    _recover_via_sibling_basket,
)
from src.polaris_graph.generator.provenance_generator import (  # noqa: E402
    SentenceVerification,
    parse_provenance_tokens,
)


class _FakeEntailmentJudge:
    """Deterministic offline entailment judge: every span that reaches the judge
    (i.e. already passed the mechanical content/numeric checks) ENTAILS. The FIX-1
    spans are crafted so only the genuinely-supporting sibling (ev_good, span ==
    claim) clears the content-word floor and reaches the judge; non-supporting
    siblings (ev_bad / ev_fail) fail the floor mechanically and never call it. So a
    default-ENTAILED judge is sufficient AND faithful for these tests — no network,
    P2-2: every enforce-mode FIX-1 test installs this stub."""

    def judge(self, sentence: str, span: str):
        return "ENTAILED", "fake: default entailed (offline test stub)"


def _install_fake_judge(monkeypatch) -> _FakeEntailmentJudge:
    """Install the offline judge so verify_sentence_provenance's enforce-mode 6th
    check (strict_verify._get_judge().judge(...)) never hits OpenRouter. Mirrors the
    canonical pattern in test_strict_verify_entailment.py:_install_fake_judge."""
    fake = _FakeEntailmentJudge()
    monkeypatch.setattr(strict_verify, "_JUDGE_SINGLETON", fake, raising=False)
    monkeypatch.setattr(strict_verify, "_get_judge", lambda: fake)
    return fake


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


def test_fix1_master_gate_defaults_off(monkeypatch) -> None:
    """P1-2: PG_BASKET_REPAIR_ENABLED is the MASTER gate and defaults OFF when unset.
    The whole repair loop at the call sites no-ops in that state (byte-identical)."""
    monkeypatch.delenv("PG_BASKET_REPAIR_ENABLED", raising=False)
    assert _basket_repair_enabled() is False
    # The bound helper now defaults to the named cycles constant (only consulted
    # once ENABLED), so it alone is NOT the off-switch — the master gate is.
    monkeypatch.delenv("PG_BASKET_REPAIR_MAX_CYCLES", raising=False)
    assert _basket_repair_max_cycles() == 3
    for token in ("", "0", "false", "no", "off", "garbage"):
        monkeypatch.setenv("PG_BASKET_REPAIR_ENABLED", token)
        assert _basket_repair_enabled() is False
    for token in ("1", "true", "yes", "on", "TRUE", "On"):
        monkeypatch.setenv("PG_BASKET_REPAIR_ENABLED", token)
        assert _basket_repair_enabled() is True


def test_fix1_helper_honors_zero_max_cycles(monkeypatch) -> None:
    """The helper's own bound: max_cycles<=0 -> no re-anchor pass, dropped list
    returned unchanged (the helper is called directly here, so the master gate at
    the call sites is not exercised; this proves the internal bound is fail-safe)."""
    _install_fake_judge(monkeypatch)
    monkeypatch.setenv("PG_BASKET_REPAIR_MAX_CYCLES", "0")
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
    _install_fake_judge(monkeypatch)
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
    _install_fake_judge(monkeypatch)
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
    _install_fake_judge(monkeypatch)
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
    _install_fake_judge(monkeypatch)
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


def test_fix1_same_eid_multi_token_not_reanchored(monkeypatch) -> None:
    """P2-1 (Codex diff-gate): a sentence with TWO tokens of the SAME evidence_id is
    NOT eligible (len(tokens)==2, even though len(distinct_eids)==1). The old
    distinct-eid scope wrongly admitted it and collapsed both spans to one appended
    sibling token, silently dropping the second span's grounding. The token-count
    scope leaves it dropped."""
    _install_fake_judge(monkeypatch)
    monkeypatch.setenv("PG_BASKET_REPAIR_MAX_CYCLES", "3")
    monkeypatch.setenv("PG_STRICT_VERIFY_ENTAILMENT", "enforce")
    cred = _FakeCredAnalysis(
        baskets=[_FakeBasket("c1", [_FakeMember("ev_fail"), _FakeMember("ev_good")])],
        cluster_id_by_evidence={"ev_fail": ["c1"], "ev_good": ["c1"]},
    )
    # Same eid (ev_fail), TWO distinct spans -> two tokens, one distinct eid.
    multi_token = f"{_CLAIM_TEXT} [#ev:ev_fail:0-5] [#ev:ev_fail:6-10]"
    sv = _dropped_sv(multi_token)
    assert len({t.evidence_id for t in sv.tokens}) == 1  # one distinct eid
    assert len(sv.tokens) == 2  # but two tokens
    recovered, still = _recover_via_sibling_basket(
        [sv], _pool_with_supporting_sibling(), cred
    )
    assert recovered == []
    assert len(still) == 1
    assert still[0].is_verified is False


def test_fix1_none_credibility_analysis_noop(monkeypatch) -> None:
    """credibility_analysis is None (master flag OFF / always-release degrade) -> the
    recovery no-ops and returns the dropped list unchanged."""
    _install_fake_judge(monkeypatch)
    monkeypatch.setenv("PG_BASKET_REPAIR_MAX_CYCLES", "3")
    monkeypatch.setenv("PG_STRICT_VERIFY_ENTAILMENT", "enforce")
    dropped = [_dropped_sv(_DROPPED_SENTENCE)]
    recovered, still = _recover_via_sibling_basket(
        dropped, _pool_with_supporting_sibling(), None
    )
    assert recovered == []
    assert len(still) == 1


# ─────────────────────────────────────────────────────────────────────────────
# FIX 1 — CONTRACT-PATH integration. This is the path Gate-B forces
# (PG_V30_PHASE2_ENABLED=1) so EVERY section ships through run_contract_section —
# the path that actually fires on Q76. The isolated-helper tests above prove the
# re-anchor logic; THIS test proves the re-anchor genuinely engages INSIDE
# run_contract_section with the flag ON (stale_plan_risk #3: a legacy-only fix
# leaves Q76 unaffected). A fake strict_verify_fn injects ONE over-dropped
# deterministic-stream sentence carrying an inline [#ev:ev_fail:...] token; a basket
# sibling (ev_good) independently entails the FULL claim, so the recovery block
# between the combined-dropped assembly and the kept/dropped recompute re-anchors it.
# ─────────────────────────────────────────────────────────────────────────────

import asyncio  # noqa: E402

from src.polaris_graph.generator.provenance_generator import (  # noqa: E402
    StrictVerificationReport,
)

# The over-dropped sentence on the contract path cites a REAL slot entity
# (surpass_2_primary -> efficacy_surpass_2 slot). Because that eid IS slot-mapped,
# the P1-1 fix registers the re-anchored sibling (ev_good) under the SAME slot so
# the recovered claim renders in verified_text — the exact bug P2-2 guards.
_ORIG_CITED_EID = "surpass_2_primary"
_CONTRACT_DROPPED_SENTENCE = f"{_CLAIM_TEXT} [#ev:{_ORIG_CITED_EID}:0-5]"


def _contract_dropped_sv():
    """The over-dropped contract sentence. It carries a NUMERIC failure reason so
    the M-69 deterministic-stream rescue (which restores NON-numeric contract-entity
    drops independently of the re-anchor) DECLINES it — leaving the re-anchor leg as
    the sole path that can resurrect it. This makes the verified_text assertion a
    sound re-anchor discriminator (OFF -> stays dropped; ON -> re-anchored)."""
    return SentenceVerification(
        sentence=_CONTRACT_DROPPED_SENTENCE,
        tokens=parse_provenance_tokens(_CONTRACT_DROPPED_SENTENCE),
        is_verified=False,
        failure_reasons=[
            f"number_not_in_any_cited_span:{_ORIG_CITED_EID}:nums=[14]"
        ],
    )


def _build_contract_plan_and_pool():
    """Minimal real ContractSectionPlanExt + evidence_pool via the frame compiler,
    PLUS the ev_good sibling row + a basket whose sibling entails the dropped claim."""
    import yaml
    from pathlib import Path

    from src.polaris_graph.generator.contract_section_runner import (
        ContractSectionPlanExt,
        register_frame_rows_into_evidence_pool,
    )
    from src.polaris_graph.nodes.contract_outline import (
        compose_outline_from_contract,
    )
    from src.polaris_graph.nodes.frame_compiler import compile_frame
    from src.polaris_graph.retrieval.frame_fetcher import (
        FrameRow,
        ProvenanceClass,
    )

    with Path("config/scope_templates/clinical.yaml").open(
        "r", encoding="utf-8"
    ) as f:
        clinical_template = yaml.safe_load(f)

    cf = compile_frame(
        "tirzepatide evidence", clinical_template, "clinical_tirzepatide_t2dm",
    )
    rows = tuple(
        FrameRow(
            entity_id=b.entity_id,
            entity_type=b.entity_type,
            rendering_slot=b.rendering_slot,
            provenance_class=ProvenanceClass.ABSTRACT_ONLY,
            direct_quote=(
                "SURPASS-2 enrolled N=1879 patients. Primary endpoint: change "
                "in HbA1c at 40 weeks. ETD -0.47% (95% CI -0.59 to -0.35)."
            ),
            quote_source="crossref_abstract",
            doi="10.1/stub",
            pmid=None, oa_pdf_url=None, url=None,
            title=f"Title {b.entity_id}", authors=("Smith J",),
            journal="Lancet", year=2021, failure_reason=None,
            retrieval_attempts=(), retrieval_timings=(),
        )
        for b in cf.evidence_bindings
    )
    section = next(s for s in compose_outline_from_contract(cf, rows).sections
                   if s.section == "Efficacy")
    plan = ContractSectionPlanExt(
        title=section.section, focus=section.focus,
        ev_ids=[eid for s in section.slots for eid in s.entity_ids],
        slots=section.slots,
        frame_rows_by_entity={r.entity_id: r for r in rows},
        contract_entities_by_id=cf.contract.entities_by_id(),
        research_question="tirzepatide evidence",
    )
    evidence_pool: dict = {}
    register_frame_rows_into_evidence_pool(evidence_pool, rows)
    # The sibling that INDEPENDENTLY entails the dropped claim on its own span.
    evidence_pool["ev_good"] = {
        "evidence_id": "ev_good", "direct_quote": _CLAIM_TEXT,
        "url": "https://ex/good", "tier": "T1", "statement": _CLAIM_TEXT,
    }
    # The over-dropped sentence cites a REAL slot entity (surpass_2_primary, bound
    # to the efficacy_surpass_2 slot) — the realistic scenario where strict_verify
    # over-drops a slot's own claim and a basket sibling (ev_good) re-anchors it.
    # That original eid IS slot-mapped, so P1-1 registers ev_good under its slot.
    # A REAL CredibilityAnalysis so the contract path's apply_disclosure_to_svs (which
    # fail-loud requires credibility/origin coverage for every cited eid, incl. the
    # re-anchored ev_good) runs exactly as it does live — this is part of proving the
    # re-anchor engages on the genuine path, not a stub.
    from src.polaris_graph.synthesis.credibility_pass import (
        BasketMember,
        ClaimBasket,
        CredibilityAnalysis,
        EvidenceCredibility,
    )

    def _ec(eid):
        return EvidenceCredibility(
            evidence_id=eid, credibility_weight=0.9, reliability_score=0.9,
            relevance_score=0.9, origin_cluster_id=f"origin::{eid}",
            is_canonical_origin=True, certainty_downgrade=False, soft_warning=None,
        )

    span = evidence_pool["ev_good"]["direct_quote"]
    member = BasketMember(
        evidence_id="ev_good", source_url="https://ex/good", source_tier="T1",
        origin_cluster_id="origin::ev_good", credibility_weight=0.9,
        authority_score=0.9, span=(0, len(span)), direct_quote=span,
        span_verdict="SUPPORTS",
    )
    fail_member = BasketMember(
        evidence_id=_ORIG_CITED_EID, source_url="https://ex/fail", source_tier="T3",
        origin_cluster_id="origin::orig", credibility_weight=0.5,
        authority_score=0.5, span=(0, 10), direct_quote="Unrelated.",
        span_verdict="UNSUPPORTED",
    )
    basket = ClaimBasket(
        claim_cluster_id="c1", claim_text=_CLAIM_TEXT, subject="", predicate="",
        supporting_members=[fail_member, member], refuter_cluster_ids=(),
        weight_mass=0.9, total_clustered_origin_count=2,
        verified_support_origin_count=1, basket_verdict="partial",
    )
    cred = CredibilityAnalysis(
        credibility_by_evidence={
            "ev_good": _ec("ev_good"), _ORIG_CITED_EID: _ec(_ORIG_CITED_EID),
        },
        origin_by_evidence={
            "ev_good": "origin::ev_good", _ORIG_CITED_EID: "origin::orig",
        },
        claims=[], edges=[], weight_mass=[],
        baskets=[basket],
        cluster_id_by_evidence={_ORIG_CITED_EID: ["c1"], "ev_good": ["c1"]},
    )
    return plan, evidence_pool, cred


class _SR:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


async def _fake_llm(prompt):
    import re as _re
    m = _re.search(
        r"=== REQUIRED FIELDS ===\n.*?\n((?:  - \w+\n)+)", prompt, _re.DOTALL,
    )
    fields = []
    if m:
        for line in m.group(1).strip().splitlines():
            fname = line.strip("- ").strip()
            if fname == "N":
                fields.append({"field_name": "N", "status": "extracted",
                               "value": "N=1879", "source_span": "N=1879"})
            else:
                fields.append({"field_name": fname, "status": "not_extractable",
                               "value": None, "source_span": None})
    import json as _json
    return _json.dumps({"fields": fields}), 500, 200


def test_fix1_contract_path_reanchors_with_flag_on(monkeypatch) -> None:
    """END-TO-END on the LIVE benchmark path (run_contract_section): with the flag
    ON + enforce + a basket sibling that independently entails the FULL claim, an
    over-dropped deterministic-stream sentence is re-anchored to the sibling and the
    recovered claim REACHES verified_text / sentences_verified (NOT just biblio).
    Flag OFF -> it stays dropped.

    P2-2 (Codex diff-gate): the verified_text + sentences_verified assertions below
    are the load-bearing ones. The prior biblio-only check passed even with the
    P1-1 slot-attribution bug (the resolver numbers the citation into biblio before
    the slot regroup runs), so it MISSED that the recovered claim never rendered in
    the body. The verified_text assertion FAILS before the P1-1 entity_to_slot_id
    registration and PASSES after."""
    _install_fake_judge(monkeypatch)
    monkeypatch.setenv("PG_STRICT_VERIFY_ENTAILMENT", "enforce")
    from src.polaris_graph.generator.contract_section_runner import (
        run_contract_section,
    )
    from src.polaris_graph.generator.live_deepseek_generator import (
        _rewrite_draft_with_spans,
    )

    plan, evidence_pool, cred = _build_contract_plan_and_pool()

    # A fake strict_verify_fn that, the FIRST time it is called with a non-empty
    # draft (the deterministic stream), returns ONE over-dropped sentence carrying an
    # inline [#ev:ev_fail:...] token (a content-overlap false drop). Subsequent calls
    # (regulatory / narrative streams, here empty) return empty reports.
    state = {"injected": False}

    def _fake_strict_verify(draft, pool, **kwargs):
        if draft and draft.strip() and not state["injected"]:
            state["injected"] = True
            sv = _contract_dropped_sv()
            return StrictVerificationReport(
                kept_sentences=[], dropped_sentences=[sv],
                total_in=1, total_kept=0, total_dropped=1,
            )
        return StrictVerificationReport(
            kept_sentences=[], dropped_sentences=[],
            total_in=0, total_kept=0, total_dropped=0,
        )

    async def _run(*, enabled: bool):
        # P1-2: PG_BASKET_REPAIR_ENABLED is the MASTER gate. Both it and a positive
        # max-cycles bound must hold for the repair loop to run at the call site.
        if enabled:
            monkeypatch.setenv("PG_BASKET_REPAIR_ENABLED", "1")
            monkeypatch.setenv("PG_BASKET_REPAIR_MAX_CYCLES", "3")
        else:
            monkeypatch.delenv("PG_BASKET_REPAIR_ENABLED", raising=False)
            monkeypatch.delenv("PG_BASKET_REPAIR_MAX_CYCLES", raising=False)
        state["injected"] = False
        return await run_contract_section(
            plan, dict(evidence_pool),
            llm_call=_fake_llm,
            section_result_cls=_SR,
            strict_verify_fn=_fake_strict_verify,
            rewrite_fn=_rewrite_draft_with_spans,
            credibility_analysis=cred,
        )

    # FLAG ON: the dropped sentence is re-anchored to ev_good and ships in the BODY.
    result_on, _ = asyncio.run(_run(enabled=True))
    # P2-2 LOAD-BEARING: the recovered claim must render in verified_text (the slot
    # body), not just be numbered into the bibliography. Asserts both the claim
    # prose AND a non-zero sentences_verified count.
    assert _CLAIM_TEXT[:30] in (result_on.verified_text or ""), (
        "P1-1 REGRESSION: the re-anchored claim is absent from verified_text "
        f"(slot-attribution bug). verified_text={result_on.verified_text!r}"
    )
    assert (result_on.sentences_verified or 0) >= 1, (
        "P1-1 REGRESSION: the re-anchored claim did not increment "
        f"sentences_verified (got {result_on.sentences_verified!r})"
    )
    # And the re-anchored citation is numbered into the biblio (necessary, not
    # sufficient — the body check above is what P2-2 adds). NOTE: ev_good in biblio
    # alone is NOT a re-anchor signal — the existing B6/B8 basket-corroborator
    # render also numbers a SUPPORTS sibling of a normally-kept slot sentence into
    # the biblio. The re-anchor signal is the DROPPED CLAIM TEXT in verified_text.
    on_biblio_ids = {b["evidence_id"] for b in (result_on.biblio_slice or [])}
    assert "ev_good" in on_biblio_ids, (
        "FIX 1 did not engage on the contract path: the re-anchored sibling "
        f"ev_good is absent from biblio_slice {on_biblio_ids!r}"
    )

    # FLAG OFF (master gate unset): no re-anchor; the over-dropped CLAIM TEXT must
    # be absent from the body (byte-identical). The over-dropped sentence's prose
    # only ever reaches verified_text via the re-anchor leg, so verified_text is
    # the sound discriminator here (biblio is not — see the B6/B8 note above).
    result_off, _ = asyncio.run(_run(enabled=False))
    assert _CLAIM_TEXT[:30] not in (result_off.verified_text or ""), (
        "OFF path must be byte-identical: the re-anchored claim must NOT render "
        f"in verified_text. got {result_off.verified_text!r}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# FIX 1 — CONTRACT-PATH P1-1 DEEPER-EDGE slot-ATTRIBUTION tests (Codex iter-2 P1).
#
# The first P1-1 fix registered the re-anchored sibling's evidence_id into the
# GLOBAL `entity_to_slot_id` via setdefault. That mis-attributes a recovered claim
# in two edge cases the downstream slot-regroup (which buckets by tokens[0].
# evidence_id) cannot then disambiguate:
#   (a) the sibling eid is ALREADY slot-bound to a DIFFERENT slot — setdefault
#       no-ops, so the recovered claim renders under the sibling's existing slot.
#   (b) TWO dropped SVs from DIFFERENT original slots re-anchor to the SAME sibling
#       — the first setdefault wins, so BOTH claims render under the first's slot.
#
# The deeper-edge fix records each recovered SV's OWN original slot on a per-SV
# field (`reanchor_original_slot_id`) consulted FIRST in the slot regroup, so each
# recovered claim renders under ITS OWN original slot. These two tests FAIL on the
# global-setdefault implementation and PASS on the per-SV override.
# ─────────────────────────────────────────────────────────────────────────────

# Two DISTINCT over-dropped claims, each cites a DISTINCT real slot entity in the
# Efficacy section. The claim PREFIXES are unique so each can be located unambiguously
# inside its slot block in verified_text. Each carries a DISTINCT DECIMAL so the
# dropped SVs can carry a NUMERIC failure reason — the M-69 deterministic-stream rescue
# (which restores NON-numeric contract-entity drops) then DECLINES them, leaving the
# basket re-anchor as the SOLE resurrection path (the sound re-anchor discriminator).
# The entailing sibling spans below contain BOTH decimals so the isolation verify
# (which re-checks the number against the sibling span) passes for either claim.
_CLAIM_A = "Tirzepatide lowered fasting glucose by 2.7 in the alpha cohort."
_CLAIM_B = "Tirzepatide improved lipid markers by 3.9 in the beta cohort."
_EID_A = "surpass_2_primary"   # bound to the efficacy_surpass_2 rendering slot
_EID_B = "surpass_3_primary"   # bound to the efficacy_surpass_3 rendering slot


def _slot_block_for(verified_text: str, claim_prefix: str) -> str | None:
    """Return the `### <heading>` line of the slot block in `verified_text` that
    contains `claim_prefix`, or None if the claim does not render. verified_text is
    a sequence of `### <subsection>\\n\\n<body>` blocks joined by blank lines."""
    if not verified_text:
        return None
    current_heading: str | None = None
    for line in verified_text.splitlines():
        if line.startswith("### "):
            current_heading = line.strip()
        elif claim_prefix in line:
            return current_heading
    return None


def _expected_heading(plan, entity_id: str) -> str:
    """`### <subsection_title>` for the slot the given entity_id is bound to — the
    heading verified_text renders that slot's body under."""
    for slot in plan.slots:
        if entity_id in slot.entity_ids:
            return f"### {slot.subsection_title}"
    raise AssertionError(f"entity {entity_id!r} not found in any plan slot")


def _build_two_claim_plan_pool_cred(*, sibling_already_slot_bound: bool):
    """Build the real Efficacy ContractSectionPlanExt + pool + a CredibilityAnalysis
    for TWO distinct over-dropped claims (A cites _EID_A, B cites _EID_B), each in a
    DIFFERENT rendering slot.

    sibling_already_slot_bound=True  -> case (a): claim B re-anchors to _EID_A, a
        sibling that is ALREADY slot-bound (to efficacy_surpass_2). The OLD global
        setdefault would render B under efficacy_surpass_2, not efficacy_surpass_3.
    sibling_already_slot_bound=False -> case (b): BOTH claims re-anchor to the SAME
        fresh, un-slot-bound sibling `ev_shared`. The OLD global setdefault would
        render BOTH under whichever slot registered ev_shared first.
    """
    import yaml
    from pathlib import Path

    from src.polaris_graph.generator.contract_section_runner import (
        ContractSectionPlanExt,
        register_frame_rows_into_evidence_pool,
    )
    from src.polaris_graph.nodes.contract_outline import (
        compose_outline_from_contract,
    )
    from src.polaris_graph.nodes.frame_compiler import compile_frame
    from src.polaris_graph.retrieval.frame_fetcher import (
        FrameRow,
        ProvenanceClass,
    )

    with Path("config/scope_templates/clinical.yaml").open(
        "r", encoding="utf-8"
    ) as f:
        clinical_template = yaml.safe_load(f)

    cf = compile_frame(
        "tirzepatide evidence", clinical_template, "clinical_tirzepatide_t2dm",
    )
    # FILLER deterministic content (identical to the established contract-path test):
    # lets _fake_llm extract field N so the M-58 deterministic stream produces a
    # NON-EMPTY draft and `strict_verify_fn` is actually called (the injection hook).
    # The re-anchor SIBLING spans are set on the POOL rows AFTER registration below,
    # so the FrameRow filler here does not have to also carry the claim text.
    filler_quote = (
        "SURPASS-2 enrolled N=1879 patients. Primary endpoint: change "
        "in HbA1c at 40 weeks. ETD -0.47% (95% CI -0.59 to -0.35)."
    )
    rows = tuple(
        FrameRow(
            entity_id=b.entity_id,
            entity_type=b.entity_type,
            rendering_slot=b.rendering_slot,
            provenance_class=ProvenanceClass.ABSTRACT_ONLY,
            direct_quote=filler_quote,
            quote_source="crossref_abstract",
            doi="10.1/stub",
            pmid=None, oa_pdf_url=None, url=None,
            title=f"Title {b.entity_id}", authors=("Smith J",),
            journal="Lancet", year=2021, failure_reason=None,
            retrieval_attempts=(), retrieval_timings=(),
        )
        for b in cf.evidence_bindings
    )
    section = next(s for s in compose_outline_from_contract(cf, rows).sections
                   if s.section == "Efficacy")
    plan = ContractSectionPlanExt(
        title=section.section, focus=section.focus,
        ev_ids=[eid for s in section.slots for eid in s.entity_ids],
        slots=section.slots,
        frame_rows_by_entity={r.entity_id: r for r in rows},
        contract_entities_by_id=cf.contract.entities_by_id(),
        research_question="tirzepatide evidence",
    )
    evidence_pool: dict = {}
    register_frame_rows_into_evidence_pool(evidence_pool, rows)

    from src.polaris_graph.synthesis.credibility_pass import (
        BasketMember,
        ClaimBasket,
        CredibilityAnalysis,
        EvidenceCredibility,
    )

    def _ec(eid):
        return EvidenceCredibility(
            evidence_id=eid, credibility_weight=0.9, reliability_score=0.9,
            relevance_score=0.9, origin_cluster_id=f"origin::{eid}",
            is_canonical_origin=True, certainty_downgrade=False, soft_warning=None,
        )

    def _member(eid, span, verdict):
        return BasketMember(
            evidence_id=eid, source_url=f"https://ex/{eid}", source_tier="T1",
            origin_cluster_id=f"origin::{eid}", credibility_weight=0.9,
            authority_score=0.9, span=(0, len(span)), direct_quote=span,
            span_verdict=verdict,
        )

    cred_by_ev: dict = {_EID_A: _ec(_EID_A), _EID_B: _ec(_EID_B)}
    origin_by_ev: dict = {
        _EID_A: f"origin::{_EID_A}", _EID_B: f"origin::{_EID_B}",
    }
    cluster_id_by_evidence: dict = {}
    baskets: list = []

    if sibling_already_slot_bound:
        # Case (a): a SINGLE basket/cluster (c_b) for claim B. Its members are _EID_B
        # (the over-dropped own citation) and _EID_A (the entailing sibling that is
        # ALREADY slot-bound). Claim A is NOT over-dropped here (it is kept normally),
        # so only B exercises the re-anchor — onto an already-slot-bound sibling.
        # OVERWRITE _EID_A's POOL span with the claim text (the isolation verify reads
        # the POOL row's direct_quote): _EID_A stays slot-bound (the slot map is built
        # from plan.slots, NOT the pool span) yet its span now entails claim B. The
        # FrameRow filler kept the deterministic stream non-empty so the injection fires.
        sib_a_span = f"{_CLAIM_A} {_CLAIM_B}"
        evidence_pool[_EID_A]["direct_quote"] = sib_a_span
        baskets.append(ClaimBasket(
            claim_cluster_id="c_b", claim_text=_CLAIM_B, subject="", predicate="",
            supporting_members=[
                _member(_EID_B, "Unrelated.", "UNSUPPORTED"),
                _member(_EID_A, sib_a_span, "SUPPORTS"),
            ],
            refuter_cluster_ids=(), weight_mass=0.9,
            total_clustered_origin_count=2, verified_support_origin_count=1,
            basket_verdict="partial",
        ))
        cluster_id_by_evidence = {_EID_B: ["c_b"], _EID_A: ["c_b"]}
    else:
        # Case (b): a fresh, un-slot-bound shared sibling whose own span entails BOTH
        # claims. TWO baskets (one per claim/cluster), EACH containing ev_shared, so
        # claim A (cluster c_a, cites _EID_A) AND claim B (cluster c_b, cites _EID_B)
        # both re-anchor to the SAME ev_shared from DIFFERENT original slots.
        shared_span = f"{_CLAIM_A} {_CLAIM_B}"
        evidence_pool["ev_shared"] = {
            "evidence_id": "ev_shared", "direct_quote": shared_span,
            "url": "https://ex/shared", "tier": "T1", "statement": shared_span,
        }
        cred_by_ev["ev_shared"] = _ec("ev_shared")
        origin_by_ev["ev_shared"] = "origin::ev_shared"
        baskets.append(ClaimBasket(
            claim_cluster_id="c_a", claim_text=_CLAIM_A, subject="", predicate="",
            supporting_members=[
                _member(_EID_A, "Unrelated.", "UNSUPPORTED"),
                _member("ev_shared", shared_span, "SUPPORTS"),
            ],
            refuter_cluster_ids=(), weight_mass=0.9,
            total_clustered_origin_count=2, verified_support_origin_count=1,
            basket_verdict="partial",
        ))
        baskets.append(ClaimBasket(
            claim_cluster_id="c_b", claim_text=_CLAIM_B, subject="", predicate="",
            supporting_members=[
                _member(_EID_B, "Unrelated.", "UNSUPPORTED"),
                _member("ev_shared", shared_span, "SUPPORTS"),
            ],
            refuter_cluster_ids=(), weight_mass=0.9,
            total_clustered_origin_count=2, verified_support_origin_count=1,
            basket_verdict="partial",
        ))
        cluster_id_by_evidence = {
            _EID_A: ["c_a"], _EID_B: ["c_b"], "ev_shared": ["c_a", "c_b"],
        }

    cred = CredibilityAnalysis(
        credibility_by_evidence=cred_by_ev,
        origin_by_evidence=origin_by_ev,
        claims=[], edges=[], weight_mass=[],
        baskets=baskets,
        cluster_id_by_evidence=cluster_id_by_evidence,
    )
    return plan, evidence_pool, cred


def _dropped_contract_sv(claim_text: str, cited_eid: str) -> SentenceVerification:
    """An over-dropped single-token contract sentence citing `cited_eid`, carrying a
    NUMERIC failure reason so the M-69 deterministic-stream rescue (which restores
    NON-numeric contract-entity content-overlap drops) DECLINES it — leaving the
    basket re-anchor as the sole resurrection path (the sound re-anchor discriminator;
    same construction as the established contract-path test's `_contract_dropped_sv`)."""
    import re as _re_num
    nums = _re_num.findall(r"-?\d+\.\d+", claim_text) or ["0"]
    sentence = f"{claim_text} [#ev:{cited_eid}:0-5]"
    return SentenceVerification(
        sentence=sentence,
        tokens=parse_provenance_tokens(sentence),
        is_verified=False,
        failure_reasons=[
            f"number_not_in_any_cited_span:{cited_eid}:nums=[{nums[0]}]"
        ],
    )


def _run_contract_with_dropped(plan, evidence_pool, cred, dropped_svs):
    """Run run_contract_section injecting `dropped_svs` as the deterministic stream's
    strict_verify output, with the basket-repair master gate ON + enforce."""
    from src.polaris_graph.generator.contract_section_runner import (
        run_contract_section,
    )
    from src.polaris_graph.generator.live_deepseek_generator import (
        _rewrite_draft_with_spans,
    )

    state = {"injected": False}

    def _fake_strict_verify(draft, pool, **kwargs):
        if draft and draft.strip() and not state["injected"]:
            state["injected"] = True
            return StrictVerificationReport(
                kept_sentences=[], dropped_sentences=list(dropped_svs),
                total_in=len(dropped_svs), total_kept=0,
                total_dropped=len(dropped_svs),
            )
        return StrictVerificationReport(
            kept_sentences=[], dropped_sentences=[],
            total_in=0, total_kept=0, total_dropped=0,
        )

    return asyncio.run(run_contract_section(
        plan, dict(evidence_pool),
        llm_call=_fake_llm,
        section_result_cls=_SR,
        strict_verify_fn=_fake_strict_verify,
        rewrite_fn=_rewrite_draft_with_spans,
        credibility_analysis=cred,
    ))


def test_fix1_reanchor_to_already_slot_bound_sibling_keeps_own_slot(monkeypatch):
    """P1-1 deeper-edge (a): a dropped claim re-anchored to a sibling that is ALREADY
    slot-bound to a DIFFERENT slot must STILL render under its OWN original slot.

    Claim B cites _EID_B (efficacy_surpass_3) and re-anchors to _EID_A, which is
    already bound to efficacy_surpass_2. The OLD global-setdefault implementation
    rendered B under efficacy_surpass_2 (the sibling's existing binding); the per-SV
    override renders it under efficacy_surpass_3 (its own slot)."""
    _install_fake_judge(monkeypatch)
    monkeypatch.setenv("PG_STRICT_VERIFY_ENTAILMENT", "enforce")
    monkeypatch.setenv("PG_BASKET_REPAIR_ENABLED", "1")
    monkeypatch.setenv("PG_BASKET_REPAIR_MAX_CYCLES", "3")

    plan, evidence_pool, cred = _build_two_claim_plan_pool_cred(
        sibling_already_slot_bound=True,
    )
    dropped = [_dropped_contract_sv(_CLAIM_B, _EID_B)]
    result, _ = _run_contract_with_dropped(plan, evidence_pool, cred, dropped)

    vt = result.verified_text or ""
    claim_prefix = _CLAIM_B[:40]
    assert claim_prefix in vt, (
        "the re-anchored claim B must render in verified_text; "
        f"verified_text={vt!r}"
    )
    rendered_under = _slot_block_for(vt, claim_prefix)
    own_slot_heading = _expected_heading(plan, _EID_B)        # efficacy_surpass_3
    sibling_slot_heading = _expected_heading(plan, _EID_A)    # efficacy_surpass_2
    assert rendered_under == own_slot_heading, (
        "P1-1 DEEPER-EDGE REGRESSION (a): claim B rendered under "
        f"{rendered_under!r}, not its own slot heading {own_slot_heading!r}. "
        f"(sibling _EID_A's slot heading is {sibling_slot_heading!r})"
    )
    assert rendered_under != sibling_slot_heading


def test_fix1_two_dropped_svs_same_sibling_render_under_own_slots(monkeypatch):
    """P1-1 deeper-edge (b): TWO dropped claims from DIFFERENT original slots that
    BOTH re-anchor to the SAME sibling must EACH render under THEIR OWN slot.

    Claim A (cites _EID_A, efficacy_surpass_2) and claim B (cites _EID_B,
    efficacy_surpass_3) both re-anchor to the SAME fresh ev_shared. The OLD global
    setdefault rendered BOTH under whichever slot registered ev_shared first; the
    per-SV override renders A under efficacy_surpass_2 and B under
    efficacy_surpass_3."""
    _install_fake_judge(monkeypatch)
    monkeypatch.setenv("PG_STRICT_VERIFY_ENTAILMENT", "enforce")
    monkeypatch.setenv("PG_BASKET_REPAIR_ENABLED", "1")
    monkeypatch.setenv("PG_BASKET_REPAIR_MAX_CYCLES", "3")

    plan, evidence_pool, cred = _build_two_claim_plan_pool_cred(
        sibling_already_slot_bound=False,
    )
    dropped = [
        _dropped_contract_sv(_CLAIM_A, _EID_A),
        _dropped_contract_sv(_CLAIM_B, _EID_B),
    ]
    result, _ = _run_contract_with_dropped(plan, evidence_pool, cred, dropped)

    vt = result.verified_text or ""
    a_prefix, b_prefix = _CLAIM_A[:40], _CLAIM_B[:40]
    assert a_prefix in vt and b_prefix in vt, (
        "both re-anchored claims must render in verified_text; "
        f"verified_text={vt!r}"
    )
    a_under = _slot_block_for(vt, a_prefix)
    b_under = _slot_block_for(vt, b_prefix)
    a_expected = _expected_heading(plan, _EID_A)   # efficacy_surpass_2
    b_expected = _expected_heading(plan, _EID_B)   # efficacy_surpass_3
    assert a_under == a_expected, (
        "P1-1 DEEPER-EDGE REGRESSION (b): claim A rendered under "
        f"{a_under!r}, expected its own slot {a_expected!r}"
    )
    assert b_under == b_expected, (
        "P1-1 DEEPER-EDGE REGRESSION (b): claim B rendered under "
        f"{b_under!r}, expected its own slot {b_expected!r}"
    )
    # The decisive cross-claim check: the two recovered claims must land in DIFFERENT
    # slot blocks (the OLD setdefault collapsed both into one).
    assert a_under != b_under, (
        "P1-1 DEEPER-EDGE REGRESSION (b): both claims rendered under the SAME slot "
        f"block {a_under!r} (global-setdefault collapse)"
    )
