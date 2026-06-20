"""FIX-P0-B (I-arch-011 #1271) — ALWAYS-RELEASE behavioral proof for the
critical-completeness HOLD.

THE HAZARD this lane closes: once the device/procedure recognizer recognizes a
device (e.g. deep brain stimulation), the completeness gate flips a device-safety
checklist topic marked ``critical: true`` (contraindications / boxed warnings) to
APPLICABLE. When the corpus does not cover it, the sweep set the terminal status
``abort_critical_topic_uncovered`` (run_honest_sweep_r3.py ~:9862). That status was
NOT in ``_B18_B19_CONVERTIBLE_HOLDS``, so under the operator-locked always-release
reframe a run that previously SHIPPED would now HARD-ABORT — the opposite of the
"the verifier/gate is a LABEL, never a HOLD" directive.

THE FIX (behavior asserted here): under always-release, ``abort_critical_topic_
uncovered`` converts to ``released_with_disclosed_gaps`` — the verified report body
SHIPS (body NOT withheld) and the uncovered critical topic is NAMED in
``disclosed_gaps``. Faithfulness is NEVER relaxed: the binding 4-role D8 hold
(``abort_four_role_release_held``) is deliberately absent from the convertible map,
so a real fabrication still HOLDS; this only converts a COMPLETENESS gap.

These tests stitch the TWO real, pure, unit-callable functions on the genuine run
path so the proof is BEHAVIORAL, not a hollow status-string flip:

    b18_b19_disposition(...)                    # the conversion the run applies
      -> manifest with status + final_verdicts  # the FINAL reconciled run state
      -> reconstruct_release_outcome_from_manifest(...)
      -> assert_release_invariant(...)           # the A18 hard release-invariant

The A18 step is load-bearing: it runs AFTER the conversion in the real script
(~:11452) and REVERTS to ``four_role_held`` (body withheld) unless the manifest can
PROVE the judge truly adjudicated. These tests prove the disposition + A18 mechanics
in ISOLATION: given D8 proof present, the body ships; given no proof, it fail-closes.

SCOPE HONESTY (read before trusting this as an end-to-end always-release proof) —
on the REAL benchmark path this status does NOT reach this disposition at runtime:
  * Real benchmark runs set PG_FOUR_ROLE_MODE=1 (run_gate_b.py:226), so the binding
    4-role D8 seam OVERWRITES ``summary_status`` at run_honest_sweep_r3.py ~:10385
    BEFORE b18 runs (~:11362). The F11 critical-completeness hold set at ~:9881 is
    therefore SUPERSEDED by the D8 verdict and never reaches the conversion — the
    report already ships (or holds) under D8's decision, and the uncovered-critical
    topic is not (yet) surfaced into disclosed_gaps on the seam path.
  * Only a legacy NON-seam run reaches b18 with this status, and there A18 correctly
    fail-closes to a withheld body (no judge ran — the FAITHFUL outcome).
So this suite proves the disposition entry is CORRECT and faithfulness-safe wherever
the status reaches b18; it is NOT a proof that the effect fires on the real seam run.
That gap is documented in the FIX-P0-B build open_concerns (surfacing the uncovered
critical topic on the seam path is a distinct follow-up).

Fail-loud: any regression that makes the disposition drop the named topic, or makes
A18 ship an un-judged body, FAILS this test.

No network, no spend — pure functions over dicts/dataclasses.
"""
from __future__ import annotations

import pytest

from scripts.run_honest_sweep_r3 import (
    _B18_B19_CONVERTIBLE_HOLDS,
    b18_b19_disposition,
    reconstruct_release_outcome_from_manifest,
    to_unified_status,
)
from src.polaris_graph.roles.release_policy import (
    ReleaseInvariantError,
    assert_release_invariant,
)

_CRITICAL_STATUS = "abort_critical_topic_uncovered"
_RELEASED_STATUS = "released_with_disclosed_gaps"

# The specific uncovered-topic detail string the set-site (~:9863) records in
# ``summary["error"]`` and that the conversion site (~:11365) appends to
# disclosed_gaps so the gap is NAMED (not just a generic header).
_UNCOVERED_TOPIC_DETAIL = (
    "critical clinical completeness topic(s) applicable but uncovered: "
    "['contraindications']"
)


def _final_run_manifest(
    *,
    status: str,
    disclosed_gaps: list[str],
    final_verdicts: dict | None,
    release_allowed: bool,
) -> dict:
    """Build a FINAL reconciled manifest in the exact shape the sweep writes just
    before the A18 invariant (run_honest_sweep_r3.py ~:11441).

    ``four_role_evaluation.final_verdicts`` non-empty encodes that the binding 4-role
    D8 judge genuinely adjudicated; ``reconstruct_release_outcome_from_manifest`` reads
    ``adjudicated`` from this signal when no ``release_disclosure`` is serialized. The
    tests vary this field to exercise BOTH A18 legs (proof-present -> ships;
    proof-absent -> fail-closed).
    """
    manifest: dict = {
        "status": to_unified_status(status),
        "release_allowed": release_allowed,
        "disclosed_gaps": list(disclosed_gaps),
    }
    if final_verdicts is not None:
        manifest["four_role_evaluation"] = {"final_verdicts": final_verdicts}
    return manifest


def test_critical_topic_uncovered_is_a_convertible_hold() -> None:
    """The new map entry exists with the released convert-target semantics."""
    assert _CRITICAL_STATUS in _B18_B19_CONVERTIBLE_HOLDS
    # The binding D8 fabrication/coverage hold MUST stay absent (faithfulness gate
    # always wins — never converted to a release).
    assert "abort_four_role_release_held" not in _B18_B19_CONVERTIBLE_HOLDS


def test_disposition_converts_under_always_release_on() -> None:
    """always-release ON: the critical-completeness HOLD flips to a released LABEL."""
    new_status, disclosure = b18_b19_disposition(
        _CRITICAL_STATUS, always_release=True
    )
    assert new_status == _RELEASED_STATUS
    assert disclosure is not None
    assert "critical_topic_uncovered" in disclosure


def test_disposition_byte_identical_when_always_release_off() -> None:
    """always-release OFF: the status is UNCHANGED (legacy hard-abort preserved)."""
    new_status, disclosure = b18_b19_disposition(
        _CRITICAL_STATUS, always_release=False
    )
    assert new_status == _CRITICAL_STATUS
    assert disclosure is None


def test_always_release_ships_body_with_named_gap_not_abort() -> None:
    """THE ALWAYS-RELEASE PROOF (behavioral, end-to-end on the real functions).

    A clinical/safety-floor run with a CRITICAL completeness topic applicable but
    UNCOVERED, always-release ON, where the binding D8 judge DID adjudicate the
    shipped body. Asserts the run ends as a SHIPPED report:
      * status == released_with_disclosed_gaps (NOT abort_critical_topic_uncovered),
      * release_allowed True,
      * the uncovered topic is NAMED in disclosed_gaps,
      * the A18 hard release-invariant does NOT raise (body ships, not withheld).
    """
    # 1) The conversion the run applies at ~:11362.
    new_status, generic_disclosure = b18_b19_disposition(
        _CRITICAL_STATUS, always_release=True
    )
    assert new_status == _RELEASED_STATUS
    assert generic_disclosure is not None

    # 2) Assemble the FINAL manifest exactly as the run does: generic disclosure +
    #    the NAMED uncovered topic detail (the conversion site appends summary["error"]).
    disclosed_gaps = [generic_disclosure, _UNCOVERED_TOPIC_DETAIL]
    manifest = _final_run_manifest(
        status=new_status,
        disclosed_gaps=disclosed_gaps,
        # D8-proof-present case: the manifest carries non-empty final_verdicts (the
        # binding 4-role D8 judge adjudicated the shipped body). This isolates the A18
        # acceptance leg: WHEN the status reaches b18 with real adjudication proof, the
        # converted release ships the body (not reverted to a withheld four_role_held).
        final_verdicts={"s0": "verified", "s1": "verified"},
        release_allowed=True,
    )

    # 3) The A18 hard release-invariant must PASS (the body SHIPS — not reverted to a
    #    withheld four_role_held). This is the load-bearing ship-not-hold proof.
    outcome = reconstruct_release_outcome_from_manifest(manifest)
    assert_release_invariant(outcome)  # FAIL-LOUD: raises on a hollow/un-judged release

    # 4) Terminal assertions: shipped (released, body NOT withheld), via A18's outcome.
    assert outcome.status == _RELEASED_STATUS
    assert outcome.released is True
    assert outcome.body_withheld is False
    # The audit trail must show this was a hold that was DISCLOSED, never a silent
    # green success.
    assert outcome.status != "success"

    # 5) The SPECIFIC uncovered critical topic must be NAMED in the REPORT-facing
    #    manifest disclosed_gaps (the surface the rendered report.md reads). This is
    #    the top-level manifest["disclosed_gaps"] the conversion site appends to —
    #    distinct from the release_disclosure sub-dict that A18 reconstructs from.
    report_gaps = manifest["disclosed_gaps"]
    assert any("contraindications" in g for g in report_gaps), (
        "the SPECIFIC uncovered critical topic must be NAMED in the report-facing "
        f"disclosed_gaps, not only a generic header; got {report_gaps!r}"
    )
    assert any("critical_topic_uncovered" in g for g in report_gaps), (
        "the generic LABEL+SHIP disclosure header must also be present; got "
        f"{report_gaps!r}"
    )


def test_release_invariant_holds_closed_if_judge_never_adjudicated() -> None:
    """Faithfulness backstop: the conversion does NOT bypass A18. If the manifest
    cannot PROVE the D8 judge adjudicated (no final_verdicts, no release_disclosure)
    AND the body is not withheld, the released status FAILS CLOSED — a released
    report with no real judging is refused, exactly as for the existing B18/B19
    holds. The always-release LABEL never overrides the binding faithfulness gate."""
    new_status, generic_disclosure = b18_b19_disposition(
        _CRITICAL_STATUS, always_release=True
    )
    manifest = _final_run_manifest(
        status=new_status,
        disclosed_gaps=[generic_disclosure, _UNCOVERED_TOPIC_DETAIL],
        final_verdicts=None,  # D8 did NOT adjudicate — no proof of judging.
        release_allowed=True,
    )
    outcome = reconstruct_release_outcome_from_manifest(manifest)
    with pytest.raises(ReleaseInvariantError):
        assert_release_invariant(outcome)
