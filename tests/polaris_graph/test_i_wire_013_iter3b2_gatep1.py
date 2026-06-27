"""I-wire-013 (#1327) iter-3b-2 — close the two iter-3b GATE P1s. Fully offline; every unit
under test is PURE (no model, no network).

P1-A (CONTRADICTION — fabricated-number path). A UNIT-LESS number that sits inside a
bibliographic identifier — a DOI suffix, a page range, an ISSN, or an arXiv id — is a citation
artifact, never a measured metric value. The pre-existing bibliographic screen
(``contradiction_detector._BIBLIOGRAPHIC_ID_RE`` lines ~315-329, wired into ``_find_value_generic``
at ~line 391) already rejects it; the iter-3b delta only added the leading-dash YEAR screen in
``_looks_like_year_or_count``. These tests are the per-class END-TO-END proof the gate asked for:
one case PER class (DOI suffix / page-range / ISSN / arXiv) yields NO ``possible_metric_mismatch``,
while a real shared-metric disagreement (47% vs 32% unemployment) STILL surfaces. Faithfulness
engine (strict_verify / NLI / 4-role D8 / provenance / span-grounding) is untouched.

P1-C (QUANTIFIED no-op fail-loud). The Phase-7 quantified silent no-op is now (a) logged at ERROR
level via the shared ``QUANTIFIED_SILENT_NO_OP_MESSAGE`` constant and (b) catchable BEFORE a real
run by a GATING assertion (``assert_no_quantified_silent_no_op`` with ``gating=True``) — while
staying ADVISORY in production (``gating=False`` never raises; the run is never held). The
behavioral preflight check ``assert_quantified_not_silent_no_op`` reads the manifest field the
canary stamps and FAILS on a no-op.
"""
from __future__ import annotations

import pytest

from scripts.iwire002_backhalf_replay_preflight import (
    assert_quantified_not_silent_no_op,
)
from scripts.run_honest_sweep_r3 import (
    QUANTIFIED_SILENT_NO_OP_MESSAGE,
    QuantifiedSilentNoOpError,
    assert_no_quantified_silent_no_op,
    quantified_silent_no_op_canary,
)
from src.polaris_graph.retrieval.contradiction_detector import (
    POSSIBLE_METRIC_MISMATCH_MARKER,
    detect_contradictions,
    extract_numeric_claims,
)

# Tight thresholds so ANY surviving numeric gap WOULD surface — proving the rejection is what
# suppresses the mismatch, not a slack threshold.
_REL = 0.0001
_ABS = 1.0


def _mismatch_records(evidence: list[dict]) -> list:
    """Run the full non-clinical path: extract_numeric_claims -> detect_contradictions."""
    claims = extract_numeric_claims(evidence, domain="economics")
    return detect_contradictions(
        claims, rel_threshold=_REL, abs_threshold=_ABS, is_clinical=False
    )


# ── P1-A: per-class bibliographic-identifier rejection (end-to-end) ───────────
def test_doi_suffix_pair_not_emitted_as_metric_mismatch():
    """DOI suffix (the exact task example 10.54254/2754-1169/2025.IEMS.06 — the 2754/1169/2025
    parts must NOT be lifted): two rows sharing a metric cue whose only numbers live in DOI
    suffixes yield NO possible_metric_mismatch."""
    evidence = [
        {"evidence_id": "a", "tier": "T5",
         "direct_quote": "The growth rate analysis in 10.54254/2754-1169/2025.IEMS.06 is open."},
        {"evidence_id": "b", "tier": "T5",
         "direct_quote": "The growth rate dataset 10.1038/s41586-024-07123 is referenced."},
    ]
    records = _mismatch_records(evidence)
    assert records == []
    assert not any(POSSIBLE_METRIC_MISMATCH_MARKER in (r.predicate or "") for r in records)


def test_page_range_pair_not_emitted_as_metric_mismatch():
    """Page-range context (pp. 12-19, pages 412-419): page numbers are never a metric value."""
    evidence = [
        {"evidence_id": "a", "tier": "T5",
         "direct_quote": "The coverage rate review appears on pp. 412-419 of the volume."},
        {"evidence_id": "b", "tier": "T5",
         "direct_quote": "The coverage rate summary is on pages 12-19 of the appendix."},
    ]
    assert _mismatch_records(evidence) == []


def test_issn_pair_not_emitted_as_metric_mismatch():
    """ISSN context: an ISSN's digits are a serial identifier, never a metric value."""
    evidence = [
        {"evidence_id": "a", "tier": "T5",
         "direct_quote": "The adoption rate piece in ISSN 2754-1169 is cited here."},
        {"evidence_id": "b", "tier": "T5",
         "direct_quote": "The adoption rate article under ISSN 0028-0836 is noted there."},
    ]
    assert _mismatch_records(evidence) == []


def test_arxiv_pair_not_emitted_as_metric_mismatch():
    """arXiv id context: an arXiv id (NNNN.NNNNN[vN]) is a preprint identifier, never a metric."""
    evidence = [
        {"evidence_id": "a", "tier": "T5",
         "direct_quote": "The accuracy ratio in arXiv:2401.12345v2 is described."},
        {"evidence_id": "b", "tier": "T5",
         "direct_quote": "The accuracy ratio of arXiv:2310.06825 is given."},
    ]
    assert _mismatch_records(evidence) == []


def test_real_shared_metric_disagreement_still_emitted():
    """CONTROL: a genuine unit-bearing shared-metric disagreement (47% vs 32% unemployment) is
    STILL surfaced as a possible_metric_mismatch — the screen rejects identifiers, never real
    metrics (faithfulness unchanged)."""
    evidence = [
        {"evidence_id": "a", "tier": "T1",
         "direct_quote": "The unemployment rate is 47% in the region."},
        {"evidence_id": "b", "tier": "T2",
         "direct_quote": "The unemployment rate is 32% in the region."},
    ]
    records = _mismatch_records(evidence)
    assert len(records) == 1
    assert POSSIBLE_METRIC_MISMATCH_MARKER in (records[0].predicate or "")


def test_real_metric_survives_alongside_identifiers_in_same_row():
    """Mixed row: a real 47%/32% metric AND a page range in the SAME sentence — the metric still
    disagrees (emitted); the page numbers are screened out (do not become the value/key)."""
    evidence = [
        {"evidence_id": "a", "tier": "T1",
         "direct_quote": "The unemployment rate is 47% in the region, see pp. 412-419."},
        {"evidence_id": "b", "tier": "T2",
         "direct_quote": "The unemployment rate is 32% in the region, see pp. 12-19."},
    ]
    records = _mismatch_records(evidence)
    assert len(records) == 1
    # the surviving values are the real percentages, not the page numbers
    vals = {c.value for c in records[0].claims}
    assert vals == {47.0, 32.0}


# ── P1-C: quantified silent no-op is FAIL-LOUD (gating) but ADVISORY in prod ──
def _no_op_canary() -> dict:
    """A realistic no-op canary — the drb72/drb90 fixture shape the code documents
    (fired=False, firing_status=spec_provider_error)."""
    canary = quantified_silent_no_op_canary(
        {"fired": False, "verified_sentences": 0, "firing_status": "spec_provider_error"}
    )
    assert canary is not None  # precondition: this telemetry IS a no-op
    return canary


def test_gating_assertion_raises_on_no_op():
    """gating=True (preflight/test context): a quantified silent no-op RAISES so it is caught
    BEFORE a real run; the raised message carries the exact shared substring."""
    with pytest.raises(QuantifiedSilentNoOpError) as exc_info:
        assert_no_quantified_silent_no_op(_no_op_canary(), gating=True)
    assert QUANTIFIED_SILENT_NO_OP_MESSAGE in str(exc_info.value)
    assert "spec_provider_error" in str(exc_info.value)


def test_gating_assertion_advisory_in_production_never_raises():
    """gating=False (production default): the SAME no-op is advisory — returns None, never raises,
    so a real release run is not held (operator: never hold the report)."""
    assert assert_no_quantified_silent_no_op(_no_op_canary(), gating=False) is None


def test_gating_assertion_clean_when_block_fired_or_absent():
    """A fired block / a never-ran block yields canary=None -> clean pass even under gating."""
    fired = quantified_silent_no_op_canary({"fired": True, "verified_sentences": 3})
    assert fired is None
    assert assert_no_quantified_silent_no_op(fired, gating=True) is None
    assert assert_no_quantified_silent_no_op(None, gating=True) is None


def test_preflight_check_fails_on_no_op_manifest_passes_on_clean():
    """The behavioral preflight check reads manifest['quantified_silent_no_op'] and FAILS on a
    no-op (caught before a real run), PASSES when the field is absent (block fired / never ran)."""
    no_op_manifest = {"quantified_silent_no_op": _no_op_canary()}
    ok, msg = assert_quantified_not_silent_no_op(no_op_manifest)
    assert ok is False
    assert QUANTIFIED_SILENT_NO_OP_MESSAGE in msg

    clean_manifest = {"status": "success"}  # no canary field stamped
    ok_clean, _ = assert_quantified_not_silent_no_op(clean_manifest)
    assert ok_clean is True


def test_preflight_passes_honest_empty_no_op():
    """The preflight (h) mirrors _quantified_readiness_failed: a RAN-HONEST-EMPTY no-op (an
    explicit Writer decline / every sentence dropped by the faithfulness gate) is a legitimate
    non-fire that production discloses but never holds, so the preflight PASSES it — it does NOT
    block a run the production gate would itself allow. A BROKE no-op still FAILS."""
    honest_empty = quantified_silent_no_op_canary(
        {"fired": False, "verified_sentences": 0, "firing_status": "declined_no_spec"}
    )
    ok_honest, msg_honest = assert_quantified_not_silent_no_op(
        {"quantified_silent_no_op": honest_empty}
    )
    assert ok_honest is True
    assert "honest-empty" in msg_honest

    # contrast: a BROKE status (spec_provider_error) is a real defect -> NO-GO.
    broke = quantified_silent_no_op_canary(
        {"fired": False, "verified_sentences": 0, "firing_status": "spec_provider_error"}
    )
    ok_broke, _ = assert_quantified_not_silent_no_op({"quantified_silent_no_op": broke})
    assert ok_broke is False


def test_manifest_field_name_preserved():
    """The existing manifest field key (quantified_silent_no_op) is preserved — the preflight check
    keys on exactly that name."""
    canary = _no_op_canary()
    manifest = {"quantified_silent_no_op": canary}
    # the preflight reads this exact key; if it were renamed the check would silently pass
    ok, _ = assert_quantified_not_silent_no_op(manifest)
    assert ok is False
