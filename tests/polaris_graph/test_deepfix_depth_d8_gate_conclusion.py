"""I-deepfix-001 wave-3 (conclusion true-drop) — offline tests for the grounded DEPTH cross-source
findings being threaded through the 4-role D8 seam with a TRUE drop-not-sink.

FIXTURES ONLY — NO NETWORK, NO SPEND. Every LLM boundary (synthesizer, verify_fn, the 4-role seam)
is an injected fake / a directly-constructed row. Covers the four change sites with, for each, a
FORCED-POSITIVE (the fix acts), a NEGATIVE-CONTROL (a legit case untouched), and a byte-identical-OFF
assertion under ``PG_DEPTH_SYNTHESIS_D8_GATE=0``.

  CHANGE 1  depth_synthesis.synthesize_cross_source_findings carries audit_sentence + tokens (ON) and
            is byte-identical dict shape + byte-identical render (OFF).
  CHANGE 3  native_gate_b_inputs.build_native_gate_b_inputs emits S3/observe-only DS-* claims (ON) and
            is byte-identical to legacy (OFF / no synthesized_findings). Coverage denominator unchanged.
  RELEASE   apply_d8_release_policy: a DS-* S3 FABRICATED row is release-neutral; a section S1
            FABRICATED row DOES latch (proves the test is not a vacuous pass).
  CHANGE 4  run_honest_sweep_r3._depth_d8_true_drop: a non-VERIFIED / unjudged depth bullet is DROPPED
            to the visible gap (refuse-in-place); a VERIFIED depth bullet survives; the section verdicts
            are returned depth-stripped; a legacy audit_map (no is_synthesized) is byte-identical inert.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.polaris_graph.generator.depth_synthesis import (
    depth_synthesis_d8_gate_enabled,
    synthesize_cross_source_findings,
)
from src.polaris_graph.generator.key_findings import build_depth_layer
from src.polaris_graph.generator.provenance_generator import (
    ProvenanceToken,
    SentenceVerification,
)
from src.polaris_graph.roles.native_gate_b_inputs import (
    _depth_synthesis_d8_gate_enabled,
    build_native_gate_b_inputs,
)
from src.polaris_graph.roles.release_policy import (
    CoverageLedger,
    D8ClaimRow,
    D8PolicyConfig,
    apply_d8_release_policy,
)

_GATE_ENV = "PG_DEPTH_SYNTHESIS_D8_GATE"

_FIXTURE_TEMPLATE_PATH = (
    Path(__file__).resolve().parents[1] / "fixtures" / "native_gate_b_scope_template.json"
)
_FIXTURE_SLUG = "fixture_slug"


# ─────────────────────────────────────────────────────────────────────────────
# CHANGE 1 — synthesize_cross_source_findings carries the D8 inputs (ON), byte-identical (OFF)
# ─────────────────────────────────────────────────────────────────────────────
class _Member:
    def __init__(self, eid: str) -> None:
        self.evidence_id = eid
        self.span_verdict = "SUPPORTS"
        self.origin_cluster_id = eid
        self.credibility_weight = 1.0
        self.direct_quote = "some verified quote"


class _Basket:
    def __init__(self) -> None:
        self.supporting_members = [_Member("ev1"), _Member("ev2")]
        self.claim_cluster_id = "cluster_1"
        self.claim_text = "shared cross-source finding"


_AUDIT_SENTENCE = "AI adoption rose sharply in 2024 [#ev:ev1:0-20] [#ev:ev2:0-20]."


def _fake_synth(_basket, _pool) -> str:
    return _AUDIT_SENTENCE


def _fake_verify(_draft, _pool):
    sv = SentenceVerification(
        sentence=_AUDIT_SENTENCE,
        tokens=[
            ProvenanceToken("ev1", 0, 20, "[#ev:ev1:0-20]"),
            ProvenanceToken("ev2", 0, 20, "[#ev:ev2:0-20]"),
        ],
        is_verified=True,
    )
    return SimpleNamespace(kept_sentences=[sv])


def _run_synth():
    return synthesize_cross_source_findings(
        [_Basket()],
        {"ev1": {"direct_quote": "x"}, "ev2": {"direct_quote": "y"}},
        synthesizer=_fake_synth,
        verify_fn=_fake_verify,
        bib_num_by_evidence_id={"ev1": 5, "ev2": 6},
        chrome_screen=lambda _s: False,  # deterministic: never chrome-screen the fake
    )


def test_change1_positive_carries_audit_sentence_and_tokens(monkeypatch):
    monkeypatch.setenv(_GATE_ENV, "1")
    findings = _run_synth()
    assert len(findings) == 1
    f = findings[0]
    # RENDERED [N] form ships in report.md; the PRE-resolve audit sentence carries [#ev:...] tokens.
    assert f["sentence"] == "AI adoption rose sharply in 2024 [5] [6]."
    assert f["tier"] == "cross_source"
    assert "[#ev:" in f["audit_sentence"]
    assert f["audit_sentence"] == _AUDIT_SENTENCE
    assert len(f["tokens"]) == 2
    assert {t.evidence_id for t in f["tokens"]} == {"ev1", "ev2"}


def test_change1_negative_off_is_byte_identical_dict_and_render(monkeypatch):
    monkeypatch.setenv(_GATE_ENV, "1")
    on = _run_synth()
    monkeypatch.setenv(_GATE_ENV, "0")
    off = _run_synth()
    # OFF => the two extra keys are omitted; the dict is the pre-change shape exactly.
    assert set(off[0]) == {"sentence", "tier", "label"}
    assert "audit_sentence" not in off[0] and "tokens" not in off[0]
    # The extra keys are inert to the render: build_depth_layer is byte-identical ON vs OFF.
    monkeypatch.setenv("PG_SWEEP_DEPTH_LAYER", "1")
    assert build_depth_layer([], synthesized_findings=on) == build_depth_layer(
        [], synthesized_findings=off
    )


def test_change1_negative_control_non_supports_basket_yields_nothing(monkeypatch):
    """Do NOT re-introduce eligibility loosening: a basket with only non-SUPPORTS members yields 0
    findings (no synthesis on unverified members)."""
    monkeypatch.setenv(_GATE_ENV, "1")

    class _RefutesBasket:
        def __init__(self) -> None:
            m1 = _Member("ev1")
            m2 = _Member("ev2")
            m1.span_verdict = "REFUTES"
            m2.span_verdict = "NEUTRAL"
            self.supporting_members = [m1, m2]
            self.claim_cluster_id = "cluster_x"
            self.claim_text = "unverified"

    findings = synthesize_cross_source_findings(
        [_RefutesBasket()],
        {"ev1": {"direct_quote": "x"}, "ev2": {"direct_quote": "y"}},
        synthesizer=_fake_synth,
        verify_fn=_fake_verify,
        bib_num_by_evidence_id={"ev1": 5, "ev2": 6},
        chrome_screen=lambda _s: False,
    )
    assert findings == []


# ─────────────────────────────────────────────────────────────────────────────
# CHANGE 3 — native_gate_b_inputs emits S3 DS-* claims (ON), byte-identical (OFF / absent)
# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class FakeToken:
    evidence_id: str


@dataclass
class FakeSentence:
    sentence: str
    tokens: list
    is_verified: bool = True


@dataclass
class FakeSection:
    title: str
    kept_sentences_pre_resolve: list = field(default_factory=list)
    is_gap_stub: bool = False


@dataclass
class FakeMulti:
    sections: list
    synthesized_findings: list = field(default_factory=list)


def _model_slugs() -> dict:
    return {"mirror": "m/mirror", "sentinel": "m/sentinel", "judge": "m/judge"}


def _d8_config() -> D8PolicyConfig:
    return D8PolicyConfig(
        coverage_threshold=0.70,
        material_severities=["S0", "S1", "S2"],
        s0_must_cover_categories=["contraindications", "dosing_limits", "black_box_warnings"],
    )


def _evidence_lookup() -> dict:
    return {
        "ev_doi": {"doi": "10.1056/NEJMoa2107519", "text": "trial primary endpoint"},
        "ev_pmid": {"pmid": "37786396", "text": "second trial body text"},
        "ev_sec": {"url": "https://example.org/s", "text": "section body evidence"},
    }


def _load_template() -> dict:
    import json

    return json.loads(_FIXTURE_TEMPLATE_PATH.read_text(encoding="utf-8"))


def _base_section() -> FakeSection:
    # One strict_verify-VERIFIED section sentence so the base (legacy) claim set is non-empty.
    return FakeSection(
        title="Efficacy",
        kept_sentences_pre_resolve=[FakeSentence("The trial showed an effect", [FakeToken("ev_sec")])],
    )


def _depth_findings() -> list:
    return [
        {
            "sentence": "AI-side finding one [5] [6]",
            "tier": "cross_source",
            "label": "",
            "audit_sentence": "AI-side finding one [#ev:ev_doi:0-5] [#ev:ev_pmid:0-5]",
            "tokens": [FakeToken("ev_doi"), FakeToken("ev_pmid")],
        },
        {
            "sentence": "AI-side finding two [5]",
            "tier": "single_source",
            "label": "(single source)",
            "audit_sentence": "AI-side finding two [#ev:ev_doi:0-5]",
            "tokens": [FakeToken("ev_doi")],
        },
    ]


def _build(multi: FakeMulti):
    return build_native_gate_b_inputs(
        multi=multi,
        template=_load_template(),
        slug=_FIXTURE_SLUG,
        domain="clinical",
        evidence_lookup=_evidence_lookup(),
        model_slugs=_model_slugs(),
        d8_config=_d8_config(),
    )


def test_change3_positive_emits_s3_ds_claims_release_neutral(monkeypatch):
    monkeypatch.setenv(_GATE_ENV, "1")
    multi = FakeMulti(sections=[_base_section()], synthesized_findings=_depth_findings())
    bundle = _build(multi)

    ds_claims = [c for c in bundle.inputs.claims if c.claim_id.startswith("DS-")]
    assert len(ds_claims) == 2
    for c in ds_claims:
        assert c.severity == "S3"
        assert c.covered_element_ids == []  # never touches the coverage numerator
        assert c.s0_categories == []  # never touches the S0 must-cover gate
        assert "[#ev:" in c.claim_text  # judged against the PRE-resolve audit sentence
        assert len(c.evidence_documents) >= 1  # evidence resolved against the shared lookup

    # audit_map DS-* rows carry is_synthesized True + the RENDERED [N] sentence (report.md form).
    ds_ids = {c.claim_id for c in ds_claims}
    for cid in ds_ids:
        row = bundle.audit_map[cid]
        assert row["is_synthesized"] is True
        assert row["severity"] == "S3"
        assert "[#ev:" not in row["sentence"]  # rendered form, not the pre-resolve audit sentence
        assert row["sentence"].startswith("AI-side finding")

    # RELEASE-NEUTRAL: the coverage denominator + required S0 set are unchanged vs the no-synth build.
    legacy = _build(FakeMulti(sections=[_base_section()], synthesized_findings=[]))
    assert (
        bundle.inputs.coverage_ledger.required_element_ids
        == legacy.inputs.coverage_ledger.required_element_ids
    )
    assert bundle.inputs.coverage_ledger.covered_element_ids == set()
    assert bundle.inputs.required_s0_categories == legacy.inputs.required_s0_categories


def test_change3_negative_off_is_byte_identical_to_legacy(monkeypatch):
    monkeypatch.setenv(_GATE_ENV, "0")
    multi = FakeMulti(sections=[_base_section()], synthesized_findings=_depth_findings())
    off = _build(multi)
    legacy = _build(FakeMulti(sections=[_base_section()], synthesized_findings=[]))
    # No DS-* claims and identical claim_ids / audit_map keys => byte-identical to legacy.
    assert not any(c.claim_id.startswith("DS-") for c in off.inputs.claims)
    assert [c.claim_id for c in off.inputs.claims] == [c.claim_id for c in legacy.inputs.claims]
    assert set(off.audit_map) == set(legacy.audit_map)


def test_change3_negative_absent_findings_no_ds(monkeypatch):
    monkeypatch.setenv(_GATE_ENV, "1")
    # Flag ON but no synthesized_findings attached => builder no-ops (byte-identical to legacy).
    bundle = _build(FakeMulti(sections=[_base_section()], synthesized_findings=[]))
    assert not any(c.claim_id.startswith("DS-") for c in bundle.inputs.claims)


# ─────────────────────────────────────────────────────────────────────────────
# RELEASE-NEUTRALITY — a DS-* S3 FABRICATED row is release-neutral; an S1 row latches (control)
# ─────────────────────────────────────────────────────────────────────────────
def _release(rows):
    return apply_d8_release_policy(
        rows,
        required_s0_categories=[],
        coverage_ledger=CoverageLedger(required_element_ids=[]),  # fraction()==1.0, no coverage hold
        coverage_threshold=0.70,
        rewrite_already_attempted=True,
    )


def test_release_neutrality_ds_s3_fabricated_does_not_latch():
    decision = _release([D8ClaimRow(claim_id="DS-000-abc", severity="S3", verdict="FABRICATED")])
    assert decision.fabricated_occurrence_latched is False
    assert decision.release_allowed is True
    assert "DS-000-abc" not in decision.needs_rewrite


def test_release_neutrality_control_section_s1_fabricated_latches():
    decision = _release([D8ClaimRow(claim_id="00-000-sec", severity="S1", verdict="FABRICATED")])
    assert decision.fabricated_occurrence_latched is True
    assert decision.release_allowed is False


# ─────────────────────────────────────────────────────────────────────────────
# CHANGE 4 — _depth_d8_true_drop: non-VERIFIED/unjudged depth bullets DROPPED, VERIFIED survives
# ─────────────────────────────────────────────────────────────────────────────
def _import_true_drop():
    import importlib

    module = importlib.import_module("scripts.run_honest_sweep_r3")
    from src.polaris_graph.roles.report_redactor import _GAP_REPLACEMENT

    return module._depth_d8_true_drop, _GAP_REPLACEMENT


_REPORT_MD = """## Analytical synthesis

### Cross-source synthesis

_Each finding below consolidates >=2 corroborating sources._

- AI adoption rose sharply in 2024 [5] [6]
- Model accuracy improved substantially [7] [8]
- Cloud spending grew rapidly worldwide [9]

## Efficacy

The section body claim holds firmly across trials [2].
"""


def _audit_map() -> dict:
    return {
        "DS-000-aaaa": {
            "sentence": "AI adoption rose sharply in 2024 [5] [6]",
            "severity": "S3",
            "is_synthesized": True,
        },
        "DS-001-bbbb": {
            "sentence": "Model accuracy improved substantially [7] [8]",
            "severity": "S3",
            "is_synthesized": True,
        },
        "DS-002-cccc": {  # rendered but UNJUDGED (absent from final_verdicts) -> fail-closed drop
            "sentence": "Cloud spending grew rapidly worldwide [9]",
            "severity": "S3",
            "is_synthesized": True,
        },
        "00-000-sect": {
            "sentence": "The section body claim holds firmly across trials [2]",
            "severity": "S1",
        },
    }


def test_change4_positive_true_drop_and_survival(tmp_path):
    true_drop, gap = _import_true_drop()
    report_path = tmp_path / "report.md"
    report_path.write_text(_REPORT_MD, encoding="utf-8")
    final_verdicts = {
        "DS-000-aaaa": "UNSUPPORTED",  # depth non-VERIFIED -> dropped
        "DS-001-bbbb": "VERIFIED",     # depth VERIFIED -> survives verbatim
        "00-000-sect": "UNSUPPORTED",  # section non-VERIFIED -> NOT touched by depth-drop
    }
    manifest: dict = {}
    section_verdicts, section_nonverified = true_drop(
        report_path=report_path,
        final_verdicts=final_verdicts,
        audit_map=_audit_map(),
        manifest=manifest,
        research_question="q",
        log=lambda _m: None,
    )
    out = report_path.read_text(encoding="utf-8")

    # non-VERIFIED depth bullet DROPPED to the visible gap (NOT annotated with a confidence marker).
    assert "AI adoption rose sharply in 2024" not in out
    # rendered-but-unjudged depth bullet fail-closed DROPPED.
    assert "Cloud spending grew rapidly worldwide" not in out
    # VERIFIED depth bullet SURVIVES verbatim.
    assert "Model accuracy improved substantially" in out
    # SECTION claim is UNTOUCHED by the depth drop (its own annotate/reconcile runs next, in prod).
    assert "The section body claim holds firmly across trials" in out
    assert gap in out
    assert "[confidence:" not in out  # dropped, never labeled

    # Returned verdicts are SECTION-ONLY (every is_synthesized cid stripped).
    assert section_verdicts == {"00-000-sect": "UNSUPPORTED"}
    assert section_nonverified == {"00-000-sect": "UNSUPPORTED"}


def test_change4_negative_legacy_audit_map_is_inert(tmp_path):
    """A legacy audit_map with NO is_synthesized rows => the helper is a byte no-op on report.md and
    returns the verdicts unchanged (defense-in-depth byte-identical to the pre-change path)."""
    true_drop, _gap = _import_true_drop()
    report_path = tmp_path / "report.md"
    report_path.write_text(_REPORT_MD, encoding="utf-8")
    before = report_path.read_text(encoding="utf-8")
    legacy_audit = {
        "00-000-sect": {
            "sentence": "The section body claim holds firmly across trials [2]",
            "severity": "S1",
        }
    }
    final_verdicts = {"00-000-sect": "UNSUPPORTED"}
    section_verdicts, section_nonverified = true_drop(
        report_path=report_path,
        final_verdicts=dict(final_verdicts),
        audit_map=legacy_audit,
        manifest={},
        research_question="q",
        log=lambda _m: None,
    )
    assert report_path.read_text(encoding="utf-8") == before  # report untouched
    assert section_verdicts == final_verdicts
    assert section_nonverified == {"00-000-sect": "UNSUPPORTED"}


# ─────────────────────────────────────────────────────────────────────────────
# CHANGE 4 P1 (Codex) — OUTER-PATH (caller) regression: the caller's `if not _nonverified_verdicts`
# short-circuit must NOT skip the depth true-drop when a rendered is_synthesized DS-* row was NEVER
# judged (all other claims VERIFIED). Exercises the extracted caller helper
# `_depth_true_drop_when_all_verified`, which reads the audit_map from DISK (unlike the direct
# `_depth_d8_true_drop` tests above), so it is a genuine caller-path test.
# ─────────────────────────────────────────────────────────────────────────────
def _import_caller_all_verified():
    import importlib

    module = importlib.import_module("scripts.run_honest_sweep_r3")
    from src.polaris_graph.roles.report_redactor import _GAP_REPLACEMENT

    return module._depth_true_drop_when_all_verified, _GAP_REPLACEMENT


def _write_caller_fixtures(tmp_path, audit_map):
    import json

    report_path = tmp_path / "report.md"
    report_path.write_text(_REPORT_MD, encoding="utf-8")
    audit_map_path = tmp_path / "four_role_claim_audit.json"
    audit_map_path.write_text(json.dumps(audit_map), encoding="utf-8")
    return report_path, audit_map_path


def test_change4_p1_caller_all_verified_unjudged_synth_still_dropped(tmp_path, monkeypatch):
    """P1 outer-path (CALLER) regression: every JUDGED 4-role verdict is VERIFIED (so the caller's
    `if not _nonverified_verdicts` short-circuit fires) BUT a rendered is_synthesized DS-* row was
    NEVER judged (absent from final_verdicts). The depth true-drop MUST STILL run and DROP the
    un-adjudicated bullet — the reconcile is NOT gated on _nonverified_verdicts being non-empty.
    Before the fix the caller only logged skip and never called the helper, so this shipped."""
    monkeypatch.setenv(_GATE_ENV, "1")
    caller, gap = _import_caller_all_verified()
    report_path, audit_map_path = _write_caller_fixtures(tmp_path, _audit_map())

    # Every JUDGED claim VERIFIED (section + the two judged DS rows). DS-002-cccc is UNJUDGED (absent).
    final_verdicts = {
        "DS-000-aaaa": "VERIFIED",
        "DS-001-bbbb": "VERIFIED",
        "00-000-sect": "VERIFIED",
    }
    # Precondition mirrors the caller: _nonverified_verdicts is empty -> the buggy path would skip.
    assert {cid: v for cid, v in final_verdicts.items() if v != "VERIFIED"} == {}

    new_final, new_nonverified, ran = caller(
        report_path=report_path,
        audit_map_path=audit_map_path,
        final_verdicts=dict(final_verdicts),
        manifest={},
        research_question="q",
        log=lambda _m: None,
    )
    out = report_path.read_text(encoding="utf-8")

    # The caller no longer skips the depth reconcile when there are zero non-VERIFIED verdicts.
    assert ran is True
    # The UNJUDGED synthesized bullet is fail-closed DROPPED to the visible gap (never labeled).
    assert "Cloud spending grew rapidly worldwide" not in out
    assert gap in out
    assert "[confidence:" not in out
    # The VERIFIED synthesized bullets SURVIVE verbatim; the section claim is untouched.
    assert "AI adoption rose sharply in 2024" in out
    assert "Model accuracy improved substantially" in out
    assert "The section body claim holds firmly across trials" in out
    # Returned verdicts are SECTION-ONLY (every is_synthesized cid stripped); no non-verified section.
    assert new_final == {"00-000-sect": "VERIFIED"}
    assert new_nonverified == {}


def test_change4_p1_caller_off_is_byte_identical_noop(tmp_path, monkeypatch):
    """Gate OFF => even with an unjudged synthesized row present + zero non-VERIFIED verdicts, the
    caller helper is a byte no-op (ran False, report untouched): the byte-identical-OFF contract holds
    on the P1 path too."""
    monkeypatch.setenv(_GATE_ENV, "0")
    caller, _gap = _import_caller_all_verified()
    report_path, audit_map_path = _write_caller_fixtures(tmp_path, _audit_map())
    before = report_path.read_text(encoding="utf-8")
    final_verdicts = {
        "DS-000-aaaa": "VERIFIED",
        "DS-001-bbbb": "VERIFIED",
        "00-000-sect": "VERIFIED",
    }
    new_final, new_nonverified, ran = caller(
        report_path=report_path,
        audit_map_path=audit_map_path,
        final_verdicts=dict(final_verdicts),
        manifest={},
        research_question="q",
        log=lambda _m: None,
    )
    assert ran is False
    assert report_path.read_text(encoding="utf-8") == before  # report untouched
    assert new_final == final_verdicts
    assert new_nonverified == {}


def test_change4_p1_caller_no_droppable_synth_is_legacy_noop(tmp_path, monkeypatch):
    """Control: gate ON, every is_synthesized claim JUDGED and VERIFIED (none unjudged, none
    non-VERIFIED) => ran False, report untouched. Proves the fix only fires on a genuinely droppable
    row and preserves the legacy all-verified skip (no over-eager drop)."""
    monkeypatch.setenv(_GATE_ENV, "1")
    caller, _gap = _import_caller_all_verified()
    report_path, audit_map_path = _write_caller_fixtures(tmp_path, _audit_map())
    before = report_path.read_text(encoding="utf-8")
    # DS-002-cccc is now JUDGED VERIFIED -> no is_synthesized row is unjudged or non-VERIFIED.
    final_verdicts = {
        "DS-000-aaaa": "VERIFIED",
        "DS-001-bbbb": "VERIFIED",
        "DS-002-cccc": "VERIFIED",
        "00-000-sect": "VERIFIED",
    }
    new_final, new_nonverified, ran = caller(
        report_path=report_path,
        audit_map_path=audit_map_path,
        final_verdicts=dict(final_verdicts),
        manifest={},
        research_question="q",
        log=lambda _m: None,
    )
    assert ran is False
    assert report_path.read_text(encoding="utf-8") == before  # legacy all-verified no-op preserved
    # The synthesized bullets all stay (report untouched) since none was droppable.
    assert "Cloud spending grew rapidly worldwide" in report_path.read_text(encoding="utf-8")
    assert new_final == final_verdicts
    assert new_nonverified == {}


def test_change4_p1_caller_missing_artifact_is_noop(tmp_path, monkeypatch):
    """Control: gate ON + a droppable unjudged synthesized row, but the audit_map artifact is ABSENT
    on disk => ran False, report untouched (the caller cannot locate the bullet; matches the sibling
    `elif not _audit_map_path.is_file()` guard). No crash."""
    monkeypatch.setenv(_GATE_ENV, "1")
    caller, _gap = _import_caller_all_verified()
    report_path = tmp_path / "report.md"
    report_path.write_text(_REPORT_MD, encoding="utf-8")
    before = report_path.read_text(encoding="utf-8")
    audit_map_path = tmp_path / "four_role_claim_audit.json"  # deliberately NOT written
    final_verdicts = {"DS-000-aaaa": "VERIFIED", "00-000-sect": "VERIFIED"}
    new_final, new_nonverified, ran = caller(
        report_path=report_path,
        audit_map_path=audit_map_path,
        final_verdicts=dict(final_verdicts),
        manifest={},
        research_question="q",
        log=lambda _m: None,
    )
    assert ran is False
    assert report_path.read_text(encoding="utf-8") == before
    assert new_final == final_verdicts
    assert new_nonverified == {}


# ─────────────────────────────────────────────────────────────────────────────
# Flag-level default-ON / explicit-OFF (both readers agree on the same env var)
# ─────────────────────────────────────────────────────────────────────────────
def test_gate_readers_agree_default_on_and_explicit_off(monkeypatch):
    monkeypatch.delenv(_GATE_ENV, raising=False)
    assert depth_synthesis_d8_gate_enabled() is True
    assert _depth_synthesis_d8_gate_enabled() is True
    for off in ("0", "false", "off", "no", ""):
        monkeypatch.setenv(_GATE_ENV, off)
        assert depth_synthesis_d8_gate_enabled() is False
        assert _depth_synthesis_d8_gate_enabled() is False
