"""I-run11-010 (#1056) regression tests for the drb_72 beat-both quality degraders.

D1 evidence_value_extractor (anti-fabrication allow-list, restored),
D3 phase7 numeric extraction reads direct_quote (not the short statement),
D4 Sentinel over-broad except sites now fail loud / propagate transport faults,
S1 access-denial captcha stubs are content-starved,
S2 the verifiable-span floor constant for METADATA_ONLY frame rows.
"""

from __future__ import annotations

import pytest

from src.polaris_graph.generator.evidence_value_extractor import (
    EvidenceAllowList,
    build_allow_lists,
    format_allow_list_for_prompt,
)
from src.polaris_graph.tools.evidence_extractor import extract_numbers_from_evidence
from src.polaris_graph.retrieval.live_retriever import is_content_starved
from src.polaris_graph.roles.openai_compatible_transport import RoleTransportError
from src.polaris_graph.roles.role_transport import EvidenceDocument
from src.polaris_graph.roles.sentinel_adapter import run_sentinel
from src.polaris_graph.roles.sentinel_contract import SentinelVerdict


# ── D1: anti-fabrication allow-list (the never-committed module is restored) ──
def test_d1_build_allow_lists_extracts_numbers_trials_drugs():
    rows = [{
        "evidence_id": "ev_001",
        "direct_quote": "In SURPASS-2, tirzepatide 15 mg reduced HbA1c by 2.04% (95% CI: 1.82-2.26).",
        "statement": "Trial showed 82 kg reduction",
    }]
    al = build_allow_lists(rows)
    assert "ev_001" in al
    nums = al["ev_001"].numbers
    assert "2.04%" in nums and "1.82" in nums and "2.26" in nums and "82 kg" in nums
    assert "SURPASS-2" in al["ev_001"].trials
    assert "tirzepatide" in al["ev_001"].drugs


def test_d1_non_clinical_extracts_numbers_only():
    # The drb_72 AI/labor domain has no clinical trials/drugs — numbers still constrain.
    rows = [{"evidence_id": "ev_x",
             "direct_quote": "AI could automate 47% of US jobs; 9% are at high risk.",
             "statement": "AI and labor"}]
    al = build_allow_lists(rows)
    assert al["ev_x"].numbers == ["47%", "9%"] or set(["47%", "9%"]).issubset(set(al["ev_x"].numbers))
    assert al["ev_x"].trials == [] and al["ev_x"].drugs == []


def test_d1_purely_qualitative_row_is_omitted():
    rows = [{"evidence_id": "ev_q", "direct_quote": "A qualitative discussion of mechanism.",
             "statement": "no numbers"}]
    assert build_allow_lists(rows) == {}


def test_d1_format_block_lists_evidence_and_values():
    al = {"ev_001": EvidenceAllowList("ev_001", numbers=["2.04%"], trials=["SURPASS-2"], drugs=["tirzepatide"])}
    block = format_allow_list_for_prompt(al)
    assert "ev_001" in block and "2.04%" in block and "SURPASS-2" in block and "tirzepatide" in block
    assert format_allow_list_for_prompt({}) == ""


# ── D3: phase7 numeric extraction reads the FULL cited span (direct_quote) ──
def test_d3_extractor_reads_direct_quote_not_statement():
    # statement (the 71-char summary) has NO digits; the numbers live in direct_quote.
    store = {
        "ev_1": {"statement": "AI labor market review (title only)",
                 "direct_quote": "The study found 47% of occupations face high exposure and 9% are at risk.",
                 "source_url": "http://example.org/a"},
    }
    dps = extract_numbers_from_evidence(store)
    assert len(dps) >= 1, "must extract from direct_quote (pre-fix this returned 0)"
    assert all(dp["evidence_id"] == "ev_1" for dp in dps)


# ── S1: access-denial / captcha stubs are content-starved ──
def test_s1_captcha_stub_is_starved():
    stub = "Are you a robot? Please confirm you are a human by completing the captcha challenge." + " x" * 150
    assert is_content_starved(stub) is True


def test_s1_real_short_abstract_passes():
    abstract = ("Background: This study examines the impact of AI on labor markets across 500 "
                "occupations. Methods: we analyzed exposure scores. Results: 47% of tasks show high "
                "automation potential. Conclusion: policy readiness is uneven across sectors.")
    assert is_content_starved(abstract) is False


def test_s1_long_article_mentioning_captcha_not_false_dropped():
    article = "captcha " + ("AI-driven displacement of routine labor is examined in depth. " * 600)
    assert len(article) > 3000
    assert is_content_starved(article) is False


def test_rc_c_security_verification_interstitial_is_starved():
    """I-arch-011 BEAT-BOTH RC-C (TI-05/06): the run-#7 killer — a pivotal-RCT span grounded on a
    modern Cloudflare 'security verification' interstitial that the prior markers missed. A SHORT
    security-verification page is now caught."""
    page = ("Just a moment... example.com needs to review the security of your connection before "
            "proceeding. This process is automatic. " + "x " * 100)
    assert is_content_starved(page) is True


def test_rc_c_long_cloudflare_interstitial_caught_at_any_length():
    """RC-C: the 3000-char gate let a LONG Cloudflare interstitial / enrichment-concatenated shell
    through. The unambiguous co-occurrence signature (cloudflare + ray id) is caught at ANY length."""
    long_shell = ("Verifying you are human. " * 200) + " Performance & security by Cloudflare. Ray ID: 8a1f2c."
    assert len(long_shell) > 3000
    assert is_content_starved(long_shell) is True


def test_rc_c_real_article_mentioning_security_not_false_dropped():
    """RC-C must NOT false-drop a real long article that merely discusses data security."""
    article = ("This randomized controlled trial evaluated deep brain stimulation in Parkinson "
               "disease. " * 60) + " The registry used standard data security verification protocols."
    assert len(article) > 3000
    assert is_content_starved(article) is False


def test_s1_short_abstract_discussing_captcha_not_false_dropped():
    # Codex #1056 P2: a SHORT abstract that merely DISCUSSES captcha (bare word, <3000 chars) must
    # not be flagged — only the challenge-PAGE phrasing ("captcha challenge") signals access denial.
    abstract = ("This paper studies how captcha systems reshape labor in content-moderation work. "
                "We survey 200 annotators across three platforms and analyze task allocation, wage "
                "structures, and the displacement of routine verification work by automated captcha "
                "solvers, reporting a 12% productivity effect and a measurable shift in skill demand "
                "across the affected occupations over a two-year observation window.")
    assert 200 < len(abstract) < 3000
    assert is_content_starved(abstract) is False


# ── D4: Sentinel fail-loud — transport faults propagate, not fail-closed-UNGROUNDED ──
class _RaisingTransport:
    def __init__(self, exc: Exception):
        self._exc = exc

    def complete(self, request):  # noqa: ANN001 — matches RoleTransport protocol
        raise self._exc


def _doc():
    return [EvidenceDocument(doc_id="d1", text="evidence text")]


def test_d4_transport_error_degrades_then_continues_default():
    # B5/B7 (#1257, "nothing shall hold the report") supersedes #1056: a post-retry
    # RoleTransportError now marks ONLY the sentinel role unavailable for THIS claim
    # (fail-closed UNGROUNDED, parsed_ok=False — NEVER GROUNDED) so the parallel D8 seam
    # CONTINUES adjudicating every other claim, instead of propagating and tearing the whole
    # seam down to coverage=0. Default-ON.
    result, records = run_sentinel(_RaisingTransport(RoleTransportError("reset")), "claim",
                                   _doc(), model_slug="minimax/minimax-m2")
    assert result.verdict == SentinelVerdict.UNGROUNDED  # never GROUNDED on a transport fault
    assert result.parsed_ok is False
    assert len(records) == 1
    assert "sentinel_role_unavailable" in records[0].raw_text
    assert "RoleTransportError" in records[0].raw_text


def test_d4_transport_error_propagates_when_degrade_disabled(monkeypatch):
    # PG_SENTINEL_TRANSPORT_DEGRADE=0 restores the legacy #1056 propagate->HOLD verbatim
    # (byte-identical escape hatch): a post-retry RoleTransportError re-raises so the caller HOLDS.
    monkeypatch.setenv("PG_SENTINEL_TRANSPORT_DEGRADE", "0")
    with pytest.raises(RoleTransportError):
        run_sentinel(_RaisingTransport(RoleTransportError("reset")), "claim", _doc(),
                     model_slug="minimax/minimax-m2")


def test_d4_verdict_level_fault_still_fails_closed():
    # A genuine VERDICT-level fault (the model responded but the parser raised) stays fail-closed
    # UNGROUNDED — never GROUNDED.
    result, records = run_sentinel(_RaisingTransport(ValueError("unparseable verdict")), "claim",
                                   _doc(), model_slug="minimax/minimax-m2")
    assert result.verdict == SentinelVerdict.UNGROUNDED
    assert result.parsed_ok is False
    assert len(records) == 1


# ── S2: a METADATA_ONLY frame row with empty quote skips the LLM and emits not_extractable ──
@pytest.mark.asyncio
async def test_s2_metadata_only_empty_quote_routes_to_not_extractable():
    # Must NOT crash (compose_gap_payload hard-raises on non-gap provenance) and must NOT call the
    # LLM on an empty span — it emits an honest all-not_extractable payload instead.
    from src.polaris_graph.generator.contract_section_runner import _fill_one_slot
    from src.polaris_graph.nodes.contract_outline import ContractSlotPlan
    from src.polaris_graph.nodes.report_contract import RequiredEntity
    from src.polaris_graph.retrieval.frame_fetcher import FrameRow, ProvenanceClass

    slot = ContractSlotPlan(
        slot_id="s1", section="Foundational", subsection_title="Frey-Osborne",
        ordering=1, entity_ids=("frey_osborne",),
        provenance_classes=("metadata_only",), is_gap=False, is_partial=False,
    )
    row = FrameRow(
        entity_id="frey_osborne", entity_type="research", rendering_slot="s1",
        provenance_class=ProvenanceClass.METADATA_ONLY, direct_quote="", quote_source="none",
        doi=None, pmid=None, oa_pdf_url=None, url=None,
        title="The Future of Employment", authors=(), journal=None, year=2013,
        failure_reason=None, retrieval_attempts=(), retrieval_timings=(),
    )
    entity = RequiredEntity(
        id="frey_osborne", type="research", required_fields=("estimate", "method"),
        min_fields_for_completion=1, rendering_slot="s1", doi=None,
    )
    calls: list[str] = []

    async def _should_not_be_called(prompt: str):
        calls.append(prompt)
        return "{}", 0, 0

    payload, in_tok, out_tok = await _fill_one_slot(slot, "frey_osborne", row, entity, "q",
                                                    _should_not_be_called)
    assert calls == [], "an empty-span METADATA_ONLY row must not call the generator LLM"
    assert in_tok == 0 and out_tok == 0
    assert all(f.status == "not_extractable" for f in payload.fields)
