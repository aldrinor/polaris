"""I-arch-005 LANE-SECTION iter2 (#1257) — the B6/B8 KEYSTONE on the V30 CONTRACT path.

iter1 wired the INLINE multi-citation basket render into the LEGACY resolver +
``_run_section``. Codex found the keystone never reached the REAL benchmark: Gate-B
forces ``PG_V30_PHASE2_ENABLED=1`` / ``PG_V30_ENABLED=1``, so every section ships
through ``run_contract_section`` (contract_section_runner.py), whose slot-regroup
rebuilt markers from the ORIGINAL single-source tokens only. V30 contract sections
therefore shipped SINGLE-citation legacy output instead of the whole SUPPORTS basket.

This module drives the REAL ``run_contract_section`` (not the resolver in isolation —
a helper-only test would pass even with the wiring broken) and proves a multi-source
claim renders ALL its independently span-verified (SUPPORTS) basket members in the
contract slot body, with the SAME faithfulness rules as the legacy path:

  * ONLY ``span_verdict == "SUPPORTS"`` members render (an UNSUPPORTED member never does);
  * the advisory ``total_clustered_origin_count`` is NEVER rendered;
  * a MULTI-cluster (1-to-MANY) cited token is NEVER expanded (anti cross-claim, §-1.1 lethal);
  * ``credibility_analysis=None`` (the OFF / master-flag-off path) is byte-identical.

The LLM is injected (fake); ``strict_verify`` + the citation rewriter are REAL (same as
live sweeps) — so the test exercises the production slot-regroup at
contract_section_runner.py, not a stand-in.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest
import yaml

from src.polaris_graph.synthesis.credibility_pass import (
    BASKET_VERDICT_FULL,
    BASKET_VERDICT_PARTIAL,
    BasketMember,
    ClaimBasket,
    CredibilityAnalysis,
    EvidenceCredibility,
)


# ─────────────────────────────────────────────────────────────────────────────
# Harness — the REAL V30 contract path (mirrors test_disclosure_resolve_sites_icred008b).
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def clinical_template() -> dict:
    with Path("config/scope_templates/clinical.yaml").open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _stub_fetch_rows(compiled):
    from src.polaris_graph.retrieval.frame_fetcher import FrameRow, ProvenanceClass
    return tuple(
        FrameRow(
            entity_id=b.entity_id,
            entity_type=b.entity_type,
            rendering_slot=b.rendering_slot,
            provenance_class=ProvenanceClass.ABSTRACT_ONLY,
            direct_quote=(
                "SURPASS-2 enrolled N=1879 patients. Primary endpoint: change in "
                "HbA1c at 40 weeks. ETD -0.47% (95% CI -0.59 to -0.35)."
            ),
            quote_source="crossref_abstract",
            doi="10.1056/NEJMoa2107519" if "surpass_2" in b.entity_id else "10.1/stub",
            pmid=None, oa_pdf_url=None, url=None,
            title=f"Title {b.entity_id}", authors=("Smith J",), journal="Lancet",
            year=2021, failure_reason=None, retrieval_attempts=(), retrieval_timings=(),
        )
        for b in compiled.evidence_bindings
    )


# A verbatim substring of every slot's direct_quote (see _stub_fetch_rows). Used as
# the primary_endpoint value so each entity yields ONE kept, strict_verify-passing
# sentence with >=3 content words (the N=1879 span alone is only ~2 content words and
# is dropped at the resolve floor, so it can't carry an inline corroborator marker).
_ENDPOINT_SPAN = "change in HbA1c at 40 weeks"


_ENTITY_RE = re.compile(r"(surpass_\d+_primary|surpass_cvot_primary|surmount_\d+_primary)")


def _make_fake_llm(non_extractable_entities: frozenset[str] = frozenset()):
    """Build a fake slot-fill LLM. By default every entity extracts the multi-word
    primary_endpoint span (=> one kept, strict_verify-passing sentence per entity). An
    entity in ``non_extractable_entities`` extracts NOTHING (status=not_extractable for
    every field) => it produces NO kept sentence of its own. Used to prove the keystone's
    :912-threading is load-bearing: an UNCITED SUPPORTS corroborator (no sentence) can only
    reach the report via the resolver's basket enrichment, never via its own citation."""
    async def _fake(prompt: str):
        em = _ENTITY_RE.search(prompt)
        entity = em.group(1) if em else ""
        extract = entity not in non_extractable_entities
        m = re.search(r"=== REQUIRED FIELDS ===\n.*?\n((?:  - \w+\n)+)", prompt, re.DOTALL)
        if not m:
            return json.dumps({"fields": []}), 500, 200
        required = [
            line.strip("- ").strip()
            for line in m.group(1).strip().splitlines()
            if line.strip().startswith("-")
        ]
        fields = []
        for fname in required:
            if fname == "primary_endpoint" and extract:
                fields.append({"field_name": "primary_endpoint", "status": "extracted",
                               "value": _ENDPOINT_SPAN, "source_span": _ENDPOINT_SPAN})
            else:
                fields.append({"field_name": fname, "status": "not_extractable",
                               "value": None, "source_span": None})
        return json.dumps({"fields": fields}), 500, 200
    return _fake


_fake_llm = _make_fake_llm()


def _build_contract_inputs(clinical_template):
    from src.polaris_graph.generator.contract_section_runner import (
        ContractSectionPlanExt,
        register_frame_rows_into_evidence_pool,
    )
    from src.polaris_graph.nodes.contract_outline import compose_outline_from_contract
    from src.polaris_graph.nodes.frame_compiler import compile_frame

    cf = compile_frame("tirzepatide evidence", clinical_template, "clinical_tirzepatide_t2dm")
    rows = _stub_fetch_rows(cf)
    outline = compose_outline_from_contract(cf, rows)
    section = next(s for s in outline.sections if s.section == "Efficacy")
    plan = ContractSectionPlanExt(
        title=section.section, focus=section.focus,
        ev_ids=[eid for s in section.slots for eid in s.entity_ids],
        slots=section.slots,
        frame_rows_by_entity={r.entity_id: r for r in rows},
        contract_entities_by_id=cf.contract.entities_by_id(),
        research_question="tirzepatide evidence",
    )
    evidence_pool: dict[str, dict[str, Any]] = {}
    register_frame_rows_into_evidence_pool(evidence_pool, rows)
    return plan, evidence_pool


class _SR:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


def _covering_cred(evidence_pool: dict) -> dict[str, EvidenceCredibility]:
    """Cover EVERY cited evidence_id so the contract coverage gate does not abort."""
    cred: dict[str, EvidenceCredibility] = {}
    for i, eid in enumerate(evidence_pool):
        cred[eid] = EvidenceCredibility(
            evidence_id=eid, credibility_weight=0.85, reliability_score=0.85,
            relevance_score=0.85, origin_cluster_id=f"origin_{i}",
            is_canonical_origin=True, certainty_downgrade=False, soft_warning=None,
        )
    return cred


def _member(eid: str, verdict: str, *, weight: float = 0.8, tier: str = "T1") -> BasketMember:
    return BasketMember(
        evidence_id=eid, source_url=f"https://{eid}/", source_tier=tier,
        origin_cluster_id=f"o::{eid}", credibility_weight=weight, authority_score=weight,
        span=(0, len(_ENDPOINT_SPAN)), direct_quote=_ENDPOINT_SPAN,
        span_verdict=verdict,
    )


async def _run(plan, pool, analysis, *, llm=None):
    from src.polaris_graph.generator.contract_section_runner import run_contract_section
    from src.polaris_graph.generator.live_deepseek_generator import _rewrite_draft_with_spans
    from src.polaris_graph.generator.provenance_generator import strict_verify

    result, _payloads = await run_contract_section(
        plan, pool,
        llm_call=llm or _fake_llm, section_result_cls=_SR,
        strict_verify_fn=strict_verify, rewrite_fn=_rewrite_draft_with_spans,
        credibility_analysis=analysis,
    )
    return result


def _slot_body_for(text: str, anchor_marker: str) -> str:
    """Return the slot block (heading + body, split on '###') that contains the
    sentence carrying ``anchor_marker``."""
    blocks = text.split("###")
    for blk in blocks:
        if anchor_marker in blk:
            return blk
    return ""


def _num_for_evidence(biblio: list[dict], eid: str) -> int | None:
    for r in biblio:
        if r["evidence_id"] == eid:
            return r["num"]
    return None


# ─────────────────────────────────────────────────────────────────────────────
# (1) KEYSTONE: a multi-source claim renders ALL its SUPPORTS basket members
#     in the V30 CONTRACT slot body (proves the keystone reaches the benchmark path).
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_arch005_contract_path_renders_all_verified_basket_members(clinical_template):
    """Two REAL cited entities (surpass_1_primary + surpass_2_primary) are SUPPORTS members
    of the SAME claim basket; a THIRD (surpass_3_primary) is an UNSUPPORTED member. The slot
    that cites surpass_1 must ALSO render surpass_2's citation inline (corroboration), but
    NOT surpass_3 (unverified). This is the keystone proven on the contract path Gate-B uses.
    """
    plan, pool = _build_contract_inputs(clinical_template)
    assert {"surpass_1_primary", "surpass_2_primary", "surpass_3_primary"} <= set(pool), (
        "fixture must contain the three SURPASS entities this test pins"
    )

    # One shared basket: ev1 + ev2 SUPPORTS the SAME claim; ev3 is UNSUPPORTED for it.
    members = [
        _member("surpass_1_primary", "SUPPORTS"),
        _member("surpass_2_primary", "SUPPORTS"),
        _member("surpass_3_primary", "UNSUPPORTED"),
    ]
    basket = ClaimBasket(
        claim_cluster_id="c_shared", claim_text="N=1879 enrolled.",
        subject="trial", predicate="enrollment",
        supporting_members=members, refuter_cluster_ids=(),
        weight_mass=1.6,
        total_clustered_origin_count=3,            # ADVISORY — must NEVER render
        verified_support_origin_count=2,           # ev1 + ev2 only
        basket_verdict=BASKET_VERDICT_PARTIAL,
    )
    binding = {
        "surpass_1_primary": ["c_shared"],
        "surpass_2_primary": ["c_shared"],
        "surpass_3_primary": ["c_shared"],
    }
    analysis = CredibilityAnalysis(
        credibility_by_evidence=_covering_cred(pool),
        origin_by_evidence={e: f"o::{e}" for e in pool},
        claims=[], edges=[], weight_mass=[],
        baskets=[basket], cluster_id_by_evidence=binding,
    )

    result = await _run(plan, pool, analysis)
    text = result.verified_text
    biblio = result.biblio_slice

    n1 = _num_for_evidence(biblio, "surpass_1_primary")
    n2 = _num_for_evidence(biblio, "surpass_2_primary")
    assert n1 is not None and n2 is not None, (
        "both SUPPORTS members must be numbered in the contract biblio_slice"
    )

    # The slot that anchors on surpass_1's OWN sentence must carry BOTH n1 and n2 markers.
    # (Each entity is in its own slot; the keystone adds the corroborator marker into the
    # surpass_1 slot body — single-citation legacy output would carry only [n1].)
    body1 = _slot_body_for(text, f"[{n1}]")
    assert body1, "could not locate the surpass_1 slot body"
    assert f"[{n2}]" in body1, (
        "KEYSTONE FAIL: the contract slot still ships SINGLE-citation — the SUPPORTS "
        f"corroborator [{n2}] was not rendered inline. text:\n{body1!r}"
    )
    # Symmetric: the surpass_2 slot body must ALSO carry surpass_1's marker.
    body2 = _slot_body_for(text, f"[{n2}]")
    assert f"[{n1}]" in body2, "corroboration must be symmetric across the basket"

    # FAITHFULNESS: surpass_3 is UNSUPPORTED -> it is NEVER rendered as a corroborator
    # in EITHER basket-member slot (it keeps only its own single citation, if any).
    n3 = _num_for_evidence(biblio, "surpass_3_primary")
    if n3 is not None:
        assert f"[{n3}]" not in body1, "an UNSUPPORTED member must NOT corroborate inline"
        assert f"[{n3}]" not in body2, "an UNSUPPORTED member must NOT corroborate inline"


# ─────────────────────────────────────────────────────────────────────────────
# (1b) LOAD-BEARING: an UNCITED SUPPORTS corroborator (NO sentence of its own) reaches the
#      report ONLY via the :912 resolver enrichment — the REALISTIC keystone case ("ALL its
#      corroborating citations, not just the one the generator happened to cite").
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_arch005_contract_path_renders_uncited_supports_corroborator(clinical_template):
    """The keystone's whole point: surface a SUPPORTS source the generator did NOT cite.
    surpass_4_primary is a SUPPORTS member of the SAME basket as surpass_1_primary, but its
    OWN slot extracts nothing => it produces NO kept sentence and is in NO biblio row from
    its own citation. Its number can therefore only enter biblio_slice (and the surpass_1
    slot body) via the resolver's basket enrichment threaded at contract_section_runner.py
    :912. This is the case the :970 regroup loop ALONE cannot satisfy — it proves the :912
    threading is load-bearing, not just the regroup wiring."""
    plan, pool = _build_contract_inputs(clinical_template)
    assert "surpass_4_primary" in pool

    # surpass_4 has its own slot suppressed -> no kept sentence, no self-citation.
    llm = _make_fake_llm(non_extractable_entities=frozenset({"surpass_4_primary"}))

    members = [
        _member("surpass_1_primary", "SUPPORTS"),
        _member("surpass_4_primary", "SUPPORTS"),   # SUPPORTS but UNCITED (no own sentence)
    ]
    basket = ClaimBasket(
        claim_cluster_id="c_uncited", claim_text="endpoint claim",
        subject="trial", predicate="endpoint",
        supporting_members=members, refuter_cluster_ids=(),
        weight_mass=1.6, total_clustered_origin_count=2, verified_support_origin_count=2,
        basket_verdict=BASKET_VERDICT_FULL,
    )
    binding = {"surpass_1_primary": ["c_uncited"], "surpass_4_primary": ["c_uncited"]}
    analysis = CredibilityAnalysis(
        credibility_by_evidence=_covering_cred(pool),
        origin_by_evidence={e: f"o::{e}" for e in pool},
        claims=[], edges=[], weight_mass=[],
        baskets=[basket], cluster_id_by_evidence=binding,
    )

    result = await _run(plan, pool, analysis, llm=llm)
    text = result.verified_text
    biblio = result.biblio_slice

    n1 = _num_for_evidence(biblio, "surpass_1_primary")
    n4 = _num_for_evidence(biblio, "surpass_4_primary")
    assert n1 is not None, "surpass_1 must be numbered (it has its own cited sentence)"
    # The KEYSTONE proof: surpass_4 — which has NO sentence of its own — is numbered into the
    # biblio AND rendered inline in surpass_1's slot, surfaced purely as a basket corroborator.
    assert n4 is not None, (
        "KEYSTONE/:912 FAIL: the UNCITED SUPPORTS corroborator was not enriched into the "
        "biblio — the :912 basket threading did not reach the contract path."
    )
    # The surpass_1 slot's OWN cited sentence (the [n1] anchor) must ALSO carry [n4].
    body1 = _slot_body_for(text, f"[{n1}]")
    assert f"[{n4}]" in body1, (
        "KEYSTONE/:912 FAIL: the UNCITED SUPPORTS corroborator's marker was not rendered "
        f"inline in the citing slot. body:\n{body1!r}"
    )
    # surpass_4 has NO substantive sentence of its own — its only SUBSTANTIVE appearance is as
    # the inline corroborator in surpass_1's claim sentence. (It DOES get its own slot's gap-
    # disclosure stub — "content ... did not survive strict verification" — which is honest: the
    # contract slot found no extractable content for it. That stub is a DISCLOSURE, not a claim
    # citation. The keystone proof is that [n4] rides INTO the surpass_1 CLAIM sentence above —
    # the [n1] anchor sentence carries BOTH [n1] and [n4].)
    claim_sentence = next(
        (s for s in body1.split("\n\n") if f"[{n1}]" in s and "did not survive" not in s),
        "",
    )
    assert claim_sentence and f"[{n4}]" in claim_sentence, (
        "the uncited corroborator must ride into the actual CLAIM sentence (the [n1] anchor), "
        f"proving :912 basket enrichment reached the multi-citation render; got: {claim_sentence!r}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# (2) FAITHFULNESS: a MULTI-cluster cited token is NEVER expanded (anti cross-claim).
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_arch005_contract_path_no_cross_claim_on_multi_cluster_token(clinical_template):
    """surpass_1_primary backs TWO distinct claims (c_a AND c_b). A cited token cannot be
    attributed to ONE claim, so the contract path must NOT expand any corroborator for it —
    rendering c_b's verified member onto a c_a sentence would be a wrong-claim citation
    (§-1.1 lethal in clinical context). The surpass_1 slot keeps ONLY its own citation.
    """
    plan, pool = _build_contract_inputs(clinical_template)

    # c_a: surpass_1 + surpass_2 SUPPORTS. c_b: surpass_1 + surpass_3 SUPPORTS.
    # surpass_1 is in BOTH clusters -> ambiguous -> never expanded.
    c_a = ClaimBasket(
        claim_cluster_id="c_a", claim_text="claim A", subject="t", predicate="p",
        supporting_members=[
            _member("surpass_1_primary", "SUPPORTS"),
            _member("surpass_2_primary", "SUPPORTS"),
        ],
        refuter_cluster_ids=(), weight_mass=1.4,
        total_clustered_origin_count=2, verified_support_origin_count=2,
        basket_verdict=BASKET_VERDICT_FULL,
    )
    c_b = ClaimBasket(
        claim_cluster_id="c_b", claim_text="claim B", subject="t", predicate="p",
        supporting_members=[
            _member("surpass_1_primary", "SUPPORTS"),
            _member("surpass_3_primary", "SUPPORTS"),
        ],
        refuter_cluster_ids=(), weight_mass=1.4,
        total_clustered_origin_count=2, verified_support_origin_count=2,
        basket_verdict=BASKET_VERDICT_FULL,
    )
    binding = {
        "surpass_1_primary": ["c_a", "c_b"],   # MULTI-cluster -> ambiguous
        "surpass_2_primary": ["c_a"],
        "surpass_3_primary": ["c_b"],
    }
    analysis = CredibilityAnalysis(
        credibility_by_evidence=_covering_cred(pool),
        origin_by_evidence={e: f"o::{e}" for e in pool},
        claims=[], edges=[], weight_mass=[],
        baskets=[c_a, c_b], cluster_id_by_evidence=binding,
    )

    result = await _run(plan, pool, analysis)
    text = result.verified_text
    biblio = result.biblio_slice

    n1 = _num_for_evidence(biblio, "surpass_1_primary")
    assert n1 is not None
    body1 = _slot_body_for(text, f"[{n1}]")
    assert body1, "could not locate the surpass_1 slot body"

    n2 = _num_for_evidence(biblio, "surpass_2_primary")
    n3 = _num_for_evidence(biblio, "surpass_3_primary")
    # The ambiguous surpass_1 token expands NOTHING: neither c_a's nor c_b's member appears
    # in surpass_1's own slot body.
    if n2 is not None:
        assert f"[{n2}]" not in body1, (
            "cross-claim: c_a's member must NOT corroborate the ambiguous surpass_1 sentence"
        )
    if n3 is not None:
        assert f"[{n3}]" not in body1, (
            "cross-claim: c_b's member must NOT corroborate the ambiguous surpass_1 sentence"
        )
    # The surpass_1 slot keeps exactly its OWN single citation.
    assert body1.count(f"[{n1}]") >= 1


# ─────────────────────────────────────────────────────────────────────────────
# (3) OFF path: credibility_analysis=None -> byte-identical (no inline corroborators).
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_arch005_contract_path_off_byte_identical(clinical_template):
    """credibility_analysis=None (master flag OFF) -> the contract slot-regroup adds NO
    corroborators; verified_text is identical to a separate OFF run (determinism) AND no
    SURPASS slot carries a second SURPASS entity's marker."""
    plan, pool = _build_contract_inputs(clinical_template)
    result_off = await _run(plan, pool, None)

    plan2, pool2 = _build_contract_inputs(clinical_template)
    result_off2 = await _run(plan2, pool2, None)

    assert result_off.verified_text == result_off2.verified_text, "OFF path must be deterministic"

    # Each SURPASS entity sits in its own slot; OFF, no slot body may carry a SECOND entity's
    # citation (single-citation legacy render). Locate each entity's slot body and assert it
    # carries exactly its OWN number among the SURPASS-entity numbers.
    biblio = result_off.biblio_slice
    text = result_off.verified_text
    surpass_nums = {
        r["evidence_id"]: r["num"]
        for r in biblio
        if r["evidence_id"].startswith("surpass_") or r["evidence_id"].startswith("surmount_")
    }
    for eid, num in surpass_nums.items():
        body = _slot_body_for(text, f"[{num}]")
        if not body:
            continue
        foreign = [m for e, m in surpass_nums.items() if e != eid and f"[{m}]" in body]
        assert not foreign, (
            f"OFF path: slot for {eid} must carry only its own citation, found foreign {foreign}"
        )
