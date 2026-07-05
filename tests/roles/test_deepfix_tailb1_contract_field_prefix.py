"""I-deepfix-001 tail-B1 (#1344) finding #10 — leaked contract-field label prefix collapses twins.

RED/GREEN: two claims carrying the IDENTICAL verbatim figure but one with a leaked
"Effect estimate with uncertainty:" contract-field label prefix must (a) hash to the SAME claim_id
digest, (b) produce the SAME four-role dedup key so they collapse to ONE representative + ONE
consistent verdict, and (c) consolidate under fact-dedup even though both are intra-section. The
stripper must NEVER touch legitimate prose. Offline, $0.
"""
from __future__ import annotations

import importlib
import types

import pytest

cfp = importlib.import_module("src.polaris_graph.roles.contract_field_prefix")
ngb = importlib.import_module("src.polaris_graph.roles.native_gate_b_inputs")
si = importlib.import_module("src.polaris_graph.roles.sweep_integration")
rt = importlib.import_module("src.polaris_graph.roles.role_transport")
rpol = importlib.import_module("src.polaris_graph.roles.release_policy")
rp = importlib.import_module("src.polaris_graph.roles.role_pipeline")

_LEAKED = (
    "Effect estimate with uncertainty: One more robot per thousand workers reduces the "
    "employment-to-population ratio by 0.2 percentage points and wages by 0.42%."
)
_CLEAN = (
    "One more robot per thousand workers reduces the employment-to-population ratio by 0.2 "
    "percentage points and wages by 0.42%."
)


def test_strip_removes_leaked_label_prefix():
    """GREEN: the leaked label prefix is removed; the two twins become byte-identical."""
    assert cfp.strip_contract_field_prefix(_LEAKED) == _CLEAN
    assert cfp.strip_contract_field_prefix(_CLEAN) == _CLEAN  # no-op on the clean twin


def test_strip_never_touches_legitimate_prose():
    """The stripper only fires on a recognized LABEL at the very start followed by a colon."""
    # a sentence that merely mentions a label word mid-clause is untouched
    mid = "The primary endpoint was met at 12 months in the pivotal trial."
    assert cfp.strip_contract_field_prefix(mid) == mid
    # a label word without the colon delimiter is untouched
    no_colon = "Population characteristics were balanced across arms."
    assert cfp.strip_contract_field_prefix(no_colon) == no_colon
    # a colon that is not preceded by a recognized label is untouched
    other = "Table 1: baseline demographics of the enrolled cohort."
    assert cfp.strip_contract_field_prefix(other) == other


def test_normalize_sentence_hashes_twins_identically():
    """GREEN: `_normalize_sentence` strips the prefix so the twin claim_id digests match (was the
    01-002 vs 01-007 divergence — the leaked label produced two different ids for one fact)."""
    assert ngb._normalize_sentence(_LEAKED) == ngb._normalize_sentence(_CLEAN)


def _mk_result(claim_id: str, claim_text: str):
    """A stub ClaimPipelineResult whose verdict DEPENDS on the raw claim text — so if the twins were
    NOT collapsed they would receive DIVERGENT verdicts (the finding-#10 bug)."""
    verdict = "UNSUPPORTED" if "effect estimate" in claim_text.lower() else "VERIFIED"
    row = rpol.D8ClaimRow(
        claim_id=claim_id, severity="S3", verdict=verdict, citation_id="", s0_categories=[],
    )
    return rp.ClaimPipelineResult(
        d8_row=row, raw_judge_verdict=verdict, final_verdict=verdict, records=[],
        mirror_result=None, sentinel_result=None, judge_result=None,
    )


def test_dedup_key_collapses_prefixed_twin_to_one_verdict(monkeypatch, tmp_path):
    """GREEN: two claims differing ONLY by the leaked prefix collapse to ONE pipeline run and ONE
    shared verdict. Pre-fix (no dedup-key prefix strip) they would run twice and diverge."""
    calls = {"n": 0}

    def _stub(transport, *, claim_id, claim, evidence_documents, severity, s0_categories,
              model_slugs, timestamp):
        calls["n"] += 1
        return _mk_result(claim_id, claim)

    monkeypatch.setattr(si, "run_claim_pipeline", _stub)
    monkeypatch.setattr(si, "_CLAIM_WORKERS", 1)

    doc = rt.EvidenceDocument(doc_id="ev_x", text="robots reduce employment by 0.2 pp and wages 0.42%")
    # The CLEAN twin (01-007, the one the source verbatim supports) is first, so it is the dedup
    # representative — mirroring the real pipeline where native_gate_b strips the label at build time.
    twin_clean = si.FourRoleClaim(
        claim_id="01-007-bbbb", claim_text=_CLEAN, evidence_documents=[doc],
        severity="S3", s0_categories=[],
    )
    twin_prefixed = si.FourRoleClaim(
        claim_id="01-002-aaaa", claim_text=_LEAKED, evidence_documents=[doc],
        severity="S3", s0_categories=[],
    )
    out = si._compute_claim_results(
        object(), claims=[twin_clean, twin_prefixed], model_slugs={}, timestamp="t", run_dir=tmp_path,
    )
    assert calls["n"] == 1, "the twin claims must collapse to ONE pipeline run"
    verdicts = {r.final_verdict for (r, _c) in out}
    # ONE consistent verdict (no VERIFIED/UNSUPPORTED split); the correct verbatim figure is not
    # tagged unverified.
    assert verdicts == {"VERIFIED"}, f"both twins must share ONE consistent verdict; got {verdicts}"
    # each twin keeps its OWN claim_id but carries the shared verdict
    assert {r.d8_row.claim_id for (r, _c) in out} == {"01-002-aaaa", "01-007-bbbb"}


def test_dedup_key_control_distinct_claims_do_not_collapse(monkeypatch, tmp_path):
    """Control: two genuinely-DIFFERENT claims are NOT collapsed (the fix is targeted, not a blanket
    merge) — so a distinct fact can never inherit another's verdict."""
    calls = {"n": 0}

    def _stub(transport, *, claim_id, claim, evidence_documents, severity, s0_categories,
              model_slugs, timestamp):
        calls["n"] += 1
        return _mk_result(claim_id, claim)

    monkeypatch.setattr(si, "run_claim_pipeline", _stub)
    monkeypatch.setattr(si, "_CLAIM_WORKERS", 1)
    doc = rt.EvidenceDocument(doc_id="ev_x", text="content")
    a = si.FourRoleClaim(claim_id="a", claim_text="Robots reduce employment by 0.2 pp.",
                         evidence_documents=[doc], severity="S3", s0_categories=[])
    b = si.FourRoleClaim(claim_id="b", claim_text="GenAI raised support-agent productivity 15%.",
                         evidence_documents=[doc], severity="S3", s0_categories=[])
    si._compute_claim_results(object(), claims=[a, b], model_slugs={}, timestamp="t", run_dir=tmp_path)
    assert calls["n"] == 2, "distinct claims must each run their own pipeline"


# ── fact_dedup: EXACT intra-section duplicate consolidation (finding #10 third leg) ──────────────
fd = importlib.import_module("src.polaris_graph.generator.fact_dedup")


def test_fact_dedup_consolidates_exact_intrasection_twins():
    """GREEN: the twins (one prefixed) sit in ONE section; after prefix-normalization they are EXACT
    duplicates and now form a RedundancyGroup (were excluded by the >=2-distinct-section gate)."""
    sections = {"Displacement": [_LEAKED, _CLEAN]}
    groups = fd.build_groups(sections)
    assert groups, "an EXACT intra-section duplicate pair must now be consolidated"
    g = groups[0]
    assert len(g.redundants) == 1, "one twin is primary, the other its redundant cross-reference"


def test_fact_dedup_exact_intrasection_killswitch_off(monkeypatch):
    """OFF => byte-identical to the pre-fix >=2-distinct-section gate (no intra-section group)."""
    monkeypatch.setenv("PG_FACT_DEDUP_EXACT_INTRASECTION", "0")
    sections = {"Displacement": [_LEAKED, _CLEAN]}
    assert fd.build_groups(sections) == []


def test_fact_dedup_does_not_consolidate_distinct_intrasection_sentences():
    """A mere overlap-signature match within a section is NOT consolidated — only EXACT dups are."""
    sections = {
        "S": [
            "Robots reduced employment by 0.2 percentage points in 2020.",
            "Robots reduced employment by 0.2 percentage points in 2020 among manufacturing firms.",
        ]
    }
    # different text (not exact dup) -> no intra-section consolidation
    assert fd.build_groups(sections) == []
