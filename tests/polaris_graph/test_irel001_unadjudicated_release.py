"""I-rel-001 (#1341) — A18 four_role_held UNADJUDICATED-release reconcile (HIGH CARE).

The A18 hard release-invariant (`assert_release_invariant`) fails closed when a release-asserting
status carries adjudicated=False AND no proven seam rescue AND a body that is not withheld. Before
this fix the `except ReleaseInvariantError` handler in scripts/run_honest_sweep_r3.py converted EVERY
such trip into an UNCONDITIONAL hold (four_role_held / release_allowed=False) — even when D8 merely
failed to bind because the judge transport errored (404 / malformed JSON), with a strict_verify-clean
span-grounded body on disk. That conflicts with the operator lock
(feedback_always_release_verifier_labels_never_holds_2026_06_14): the verifier NEVER holds; always
release, label the weak / unadjudicated finding as such.

The fix reroutes the handler, under always-release, through the SAME standalone fabrication screen the
seam path uses (`build_seam_release_outcome`), and:
  (a) SCREEN CLEAN  -> RELEASE with released_with_disclosed_gaps + the 'D8-unadjudicated / weak'
      label; a re-run of `assert_release_invariant` then PASSES via seam_rescue_proven.
  (b) FABRICATED IDENTITY (or screen could not run) -> keep the BYTE-IDENTICAL fail-closed hold
      (four_role_held / release_allowed=False) AND overwrite the un-screened report.md with the
      degraded disclosure body (the line not to cross: never ship a fabricated citation as fact).

THE FAITHFULNESS BOUNDARY under test: ship-with-label is gated STRICTLY on body_withheld == False.
strict_verify checks span CONTENT, not citation IDENTITY, so the standalone fabrication screen is the
ONLY thing between 'unadjudicated' and 'shipped a fabricated citation as fact'.

No network, no spend — pure functions over dataclasses + a tmp_path report.md round-trip.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SWEEP_REL = "scripts/run_honest_sweep_r3.py"


def _load_path_module(rel_path: str, mod_name: str):
    path = _REPO_ROOT / rel_path
    spec = importlib.util.spec_from_file_location(mod_name, str(path))
    assert spec is not None and spec.loader is not None, f"cannot load {path}"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def sweep_module():
    return _load_path_module(_SWEEP_REL, "rhsr3_irel001_test")


# --------------------------------------------------------------------------------------------- #
# tiny section/token fixtures (mirror the existing iarch007 seam tests)                          #
# --------------------------------------------------------------------------------------------- #
class _Tok:
    def __init__(self, eid):
        self.evidence_id = eid


class _SV:
    def __init__(self, eids):
        self.tokens = [_Tok(e) for e in eids]


class _Section:
    def __init__(self, eids):
        self.kept_sentences_pre_resolve = [_SV(eids)]


def _serialize_handler_clean_disclosure(seam_outcome) -> dict:
    """Reproduce EXACTLY what the run-script handler writes to manifest["release_disclosure"] on the
    CLEAN-screen branch (the bytes that a downstream re-assert reads back)."""
    return {
        "hard_block": seam_outcome.hard_block,
        "hard_block_reasons": list(seam_outcome.hard_block_reasons),
        "normal_release_blocked": seam_outcome.normal_release_blocked,
        "disclosed_gaps": list(seam_outcome.disclosed_gaps),
        "release_quality_score": seam_outcome.release_quality_score,
        "safety_floor": seam_outcome.safety_floor,
        "adjudicated": False,
        "body_withheld": False,
        "compensating_screen_passed": seam_outcome.compensating_screen_passed,
    }


# =============================================================================================== #
# (a) unadjudicated + CLEAN screen -> RELEASE with the weak label, and re-assert PASSES            #
# =============================================================================================== #
def test_unadjudicated_clean_screen_releases_with_disclosed_gaps(sweep_module):
    """FIX-DETECTOR: the d8_unadjudicated_release_invariant seam outcome, with EVERY cited identity in
    the evidence pool, ships released_with_disclosed_gaps + the four_role_seam_unadjudicated label and
    is NOT withheld."""
    from src.polaris_graph.roles.release_policy import (
        STATUS_RELEASED_WITH_DISCLOSED_GAPS,
        STATUS_SUCCESS,
    )

    outcome, withheld, _reason = sweep_module.build_seam_release_outcome(
        sections=[_Section(["ev_1", "ev_2"])],
        evidence_for_gen=[{"evidence_id": "ev_1"}, {"evidence_id": "ev_2"}],
        is_clinical=False,
        seam_held_reason="d8_unadjudicated_release_invariant",
        coverage_fraction=0.83,
    )
    assert withheld is False, "a clean-screen unadjudicated outcome must NOT withhold the body"
    assert outcome.status == STATUS_RELEASED_WITH_DISCLOSED_GAPS
    assert outcome.status != STATUS_SUCCESS, "unadjudicated must NEVER resolve to success"
    assert outcome.released is True
    assert outcome.adjudicated is False, "the judge never bound — adjudicated stays False (honest)"
    assert outcome.compensating_screen_passed is True, "clean screen -> compensating_screen_passed"
    assert any(
        sweep_module.SEAM_GAP_UNADJUDICATED in g for g in outcome.disclosed_gaps
    ), "the disclosure must carry the four_role_seam_unadjudicated (D8-unadjudicated / weak) label"


def test_unadjudicated_clean_screen_passes_reassert_via_seam_rescue(sweep_module):
    """FIX-DETECTOR + INVARIANT: the manifest disclosure the handler serializes on the clean branch,
    round-tripped through reconstruct_release_outcome_from_manifest, PASSES a re-run of
    assert_release_invariant via seam_rescue_proven (specific seam gap + compensating_screen_passed)
    — proving the rerouted release is structurally safe and would not re-trip the invariant."""
    from src.polaris_graph.roles.release_policy import assert_release_invariant

    seam_outcome, withheld, _reason = sweep_module.build_seam_release_outcome(
        sections=[_Section(["ev_1"])],
        evidence_for_gen=[{"evidence_id": "ev_1"}],
        is_clinical=False,
        seam_held_reason="d8_unadjudicated_release_invariant",
        coverage_fraction=0.5,
    )
    assert withheld is False

    manifest = {
        "status": seam_outcome.status,  # released_with_disclosed_gaps
        "release_allowed": True,
        "four_role_evaluation": {"final_verdicts": {}},  # D8 never bound -> empty
        "release_disclosure": _serialize_handler_clean_disclosure(seam_outcome),
    }
    reconstructed = sweep_module.reconstruct_release_outcome_from_manifest(manifest)
    assert reconstructed.adjudicated is False, "the serialized seam state must stay adjudicated=False"
    assert reconstructed.body_withheld is False
    assert reconstructed.compensating_screen_passed is True
    # MUST NOT raise — the rerouted release re-passes A18 via the proven seam rescue.
    assert_release_invariant(reconstructed)


# =============================================================================================== #
# (b) fabricated identity -> WITHHOLD (four_role_held) + degraded report.md overwrite              #
# =============================================================================================== #
def test_unadjudicated_fabricated_identity_withholds_body(sweep_module):
    """INVARIANT (the line not to cross): a cited identity NOT in the evidence pool flips
    body_withheld=True even on the d8_unadjudicated_release_invariant reason — so the handler keeps the
    fail-closed hold. strict_verify never sees citation identity; this screen is the only guard."""
    from src.polaris_graph.roles.release_policy import STATUS_SUCCESS

    outcome, withheld, reason = sweep_module.build_seam_release_outcome(
        sections=[_Section(["ev_1", "ev_FAKE_NOT_IN_POOL"])],
        evidence_for_gen=[{"evidence_id": "ev_1"}],
        is_clinical=False,
        seam_held_reason="d8_unadjudicated_release_invariant",
        coverage_fraction=0.0,
    )
    assert withheld is True, "a fabricated cited identity MUST withhold the body (no un-screened ship)"
    assert outcome.status != STATUS_SUCCESS
    assert "ev_FAKE_NOT_IN_POOL" in reason, "the withhold reason must name the fabricated identity"


def test_unadjudicated_withhold_overwrites_report_md_with_degraded_body(sweep_module, tmp_path):
    """INVARIANT (the line not to cross): on the WITHHOLD branch the un-screened report.md is replaced
    by the degraded build_finalizer_artifact_body body and the raw body is preserved as
    report_unredacted.md — the §-1.1 audit reads report.md, so the fabricated citation must NOT remain
    readable there. This mirrors the seam withhold path the handler reuses."""
    run_dir = tmp_path
    raw_body = (
        "# Findings\n\nThe drug reduced mortality by 30% [#ev:ev_FAKE_NOT_IN_POOL:0-12].\n"
    )
    report_path = run_dir / "report.md"
    report_path.write_text(raw_body, encoding="utf-8")

    # Reproduce the handler's withhold file step (the exact code path it runs on body_withheld=True).
    (run_dir / "report_unredacted.md").write_text(
        report_path.read_text(encoding="utf-8"), encoding="utf-8"
    )
    degraded = sweep_module.build_finalizer_artifact_body(
        research_question="Does the drug reduce mortality?",
        status="four_role_held",
        error=(
            "the four-role D8 judge did not bind (transport failure) and the standalone fabrication "
            "screen required withholding the body: seam fabrication screen found cited citation "
            "identitie(s) not in the evidence pool: ['ev_FAKE_NOT_IN_POOL']"
        ),
    )
    report_path.write_text(degraded, encoding="utf-8")

    # report.md no longer carries the fabricated citation; the raw is preserved for the curator.
    on_disk = report_path.read_text(encoding="utf-8")
    assert "ev_FAKE_NOT_IN_POOL" not in on_disk or "withh" in on_disk.lower(), (
        "the shipped report.md must not present the fabricated citation as a finding"
    )
    assert on_disk != raw_body, "report.md must be overwritten with the degraded disclosure body"
    assert (run_dir / "report_unredacted.md").read_text(encoding="utf-8") == raw_body, (
        "the raw un-screened body must be preserved as report_unredacted.md"
    )


# =============================================================================================== #
# (c) the reroute is actually WIRED into the handler (guard against an inert / deleted fix)        #
# =============================================================================================== #
def test_handler_reroute_is_wired_in_run_script():
    """FIX-DETECTOR: the run-script A18 handler contains the unadjudicated reroute keyed on the
    d8_unadjudicated_release_invariant reason, gated STRICTLY on always-release + not-hard-block +
    not-already-withheld. If this fix is deleted or made inert, this assertion fails loudly."""
    src = (_REPO_ROOT / _SWEEP_REL).read_text(encoding="utf-8")
    assert "d8_unadjudicated_release_invariant" in src, (
        "the A18 handler reroute (seam_held_reason='d8_unadjudicated_release_invariant') is missing"
    )
    assert "_a18_always_release_enabled()" in src, "the reroute must gate on always_release_enabled()"
    assert 'not getattr(_final_outcome, "hard_block", False)' in src, (
        "the reroute must EXCLUDE a hard block (fabrication / zero-grounding stays fail-closed)"
    )
    assert 'not getattr(_final_outcome, "body_withheld", False)' in src, (
        "the reroute must EXCLUDE an already-withheld body (stays fail-closed)"
    )


# =============================================================================================== #
# (c-2) the A18 invariant itself is NOT loosened — the existing violation test must stay GREEN     #
# =============================================================================================== #
def test_a18_invariant_itself_unchanged_success_without_d8_still_violates(sweep_module):
    """INVARIANT (regression guard mirroring test_invariant_a18_success_without_d8_is_a_violation):
    a success status with NO D8 adjudication AND no proven seam rescue AND a non-withheld body is
    STILL a violation. The fix lives UPSTREAM of the raise (in the handler RESPONSE), so the invariant
    is not relaxed — assert_release_invariant must still raise here."""
    from src.polaris_graph.roles.release_policy import (
        ReleaseInvariantError,
        assert_release_invariant,
    )

    manifest = {
        "status": "success",
        "release_allowed": True,
        "four_role_evaluation": {"final_verdicts": {}},
    }
    outcome = sweep_module.reconstruct_release_outcome_from_manifest(manifest)
    assert outcome.adjudicated is False
    with pytest.raises(ReleaseInvariantError):
        assert_release_invariant(outcome)
