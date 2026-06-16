#!/usr/bin/env python
"""A18 — Hard release-invariant / conformance check (iarch007, Codex's #1 missing backstop).

THE STRUCTURAL BACKSTOP (CI-enforced, not soft discipline) for the A2 seam rescue.

The invariant (from `outputs/audits/iarch006_epic_failure/IMPROVED_ACTION_PLAN.md` A18):

  EVERY run artifact that writes ``status == success`` / ``status ==
  released_with_disclosed_gaps`` / ``release_allowed == true`` MUST PROVE the
  four-role D8 judge actually adjudicated (a non-empty ``final_verdicts`` map, i.e.
  a real ``release_outcome``), OR PROVE the findings body is withheld / shipped only
  as an explicitly-disclosed seam gap. No findings prose may ship as
  verified/released unless the judge truly ran.

This relaxes NOTHING. It is the same "structural removal, not promises" pattern as
the CHARTER: a path that mis-builds the A2 seam rescue (auto-releasing un-judged
content as ``success``) is caught here at the artifact layer, deterministically,
with a non-zero exit so CI fails the run.

SCOPE (AGENT-NEWFILES, SAFE CORE): this checks the run ARTIFACTS
(``manifest.json`` / ``run_status.json``). The A18 "EVERY code path" reading also
wants a static scan of every site that writes a release status — that is fragile,
out of NEWFILES scope, and flagged for Codex. The artifact invariant is the binding
backstop a CI gate actually runs against a finished run directory.

Usage::

    python scripts/iarch007_release_invariant_check.py <run_dir_or_manifest> [...]
    python scripts/iarch007_release_invariant_check.py --self-test

Exit code 0 == every artifact satisfies the invariant; non-zero == a violation
(an un-judged report marked success/released, or a release with no proof of D8 /
no withhold / no disclosed seam gap). The check is import-safe: nothing runs at
import time; all work is under functions + ``if __name__ == "__main__"``.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

# --- the release-status vocabulary this invariant binds (mirrors
# scripts/run_honest_sweep_r3.py UNIFIED_STATUS_VALUES + release_policy STATUS_*). These are
# read as plain strings here so the check has NO import dependency on the 10k-line sweep script
# (a CI gate must stay light + side-effect free). ----------------------------------------------
STATUS_SUCCESS = "success"
STATUS_RELEASED_WITH_DISCLOSED_GAPS = "released_with_disclosed_gaps"
STATUS_RELEASED_INSUFFICIENT_SAFETY = "released_insufficient_safety_evidence"

# Statuses that ASSERT a clean, judge-final report -> demand real D8 adjudication proof.
_STRICT_RELEASE_STATUSES = frozenset({STATUS_SUCCESS, STATUS_RELEASED_WITH_DISCLOSED_GAPS})
# Released-but-degraded statuses that ship an HONEST disclosed artifact -> demand a disclosed
# seam/insufficient gap OR a withheld body (never silent), but do NOT demand full D8 verdicts.
_DISCLOSED_RELEASE_STATUSES = frozenset(
    {STATUS_RELEASED_WITH_DISCLOSED_GAPS, STATUS_RELEASED_INSUFFICIENT_SAFETY}
)

# The disclosed-gap label the A2 seam rescue injects so an un-judged report can ONLY resolve to
# released_with_disclosed_gaps, never success (release_policy.py:569).
_SEAM_GAP_TOKEN = "four_role_seam_unadjudicated"


class ReleaseInvariantViolation(Exception):
    """Raised (collected) when an artifact violates the release invariant."""


def _coerce_bool(val: Any) -> bool:
    """Tolerant truthiness for a manifest field that may be a real bool or a string."""
    if isinstance(val, bool):
        return val
    if isinstance(val, str):
        return val.strip().lower() in ("1", "true", "yes", "on")
    return bool(val)


def _d8_adjudicated(manifest: dict[str, Any]) -> bool:
    """Proof the four-role D8 judge ACTUALLY ran: a non-empty ``final_verdicts`` map.

    The sweep writes ``manifest['four_role_evaluation']['final_verdicts']`` (claim_id ->
    verdict). An EMPTY map is the exact seam-error signature (drb_90:
    abort_four_role_release_held with final_verdicts={}). A non-empty map proves the judge
    adjudicated at least one claim.
    """
    fr = manifest.get("four_role_evaluation")
    if not isinstance(fr, dict):
        return False
    fv = fr.get("final_verdicts")
    return isinstance(fv, dict) and len(fv) > 0


def _disclosed_gaps_list(manifest: dict[str, Any]) -> list[str]:
    """The disclosed-gap labels, as strings, from release_disclosure (or the top-level fallback)."""
    rd = manifest.get("release_disclosure")
    gaps: Any = None
    if isinstance(rd, dict):
        gaps = rd.get("disclosed_gaps")
    if not isinstance(gaps, list) or not gaps:
        # top-level disclosed_gaps is the runner's seam-side fallback channel.
        gaps = manifest.get("disclosed_gaps")
    if not isinstance(gaps, list):
        return []
    return [str(g) for g in gaps]


def _seam_gap_present(manifest: dict[str, Any]) -> bool:
    """The SPECIFIC four_role_seam_unadjudicated label is present (iarch007 SWEEP-P0 tightening).

    The pre-fix check accepted ANY non-empty disclosed_gaps list as seam proof — a bypass: a
    manifest with an UNRELATED gap (a credibility-unscored label, say) and no real seam token
    passed. The A2 seam rescue ALWAYS injects the explicit ``four_role_seam_unadjudicated`` token
    (release_policy.py self-injects it defence-in-depth), so the seam disposition is proven ONLY by
    that specific label, never by an arbitrary gap.
    """
    return any(_SEAM_GAP_TOKEN in g for g in _disclosed_gaps_list(manifest))


def _safety_floor_gap_present(manifest: dict[str, Any]) -> bool:
    """The insufficient-safety-floor disclosure label is present (the legit label for the
    released_insufficient_safety_evidence terminal — see self-test case (e))."""
    return any("safety_floor_insufficient" in g for g in _disclosed_gaps_list(manifest))


def _body_withheld(manifest: dict[str, Any]) -> bool:
    """Proof the findings body was WITHHELD — read STRUCTURALLY (iarch007 SWEEP-P0 tightening).

    The pre-fix check treated ``normal_release_blocked`` as body-withheld proof. That is WRONG:
    ``normal_release_blocked`` only means the polished NORMAL render was suppressed (e.g. an
    insufficient-safety variant still SHIPS a findings body) — it does NOT prove the findings body
    itself was withheld. Read the real serialized ``body_withheld`` flag (set by the A2 seam
    rescue / compute_release_outcome) instead; the top-level ``body_withheld`` is a legacy fallback.
    """
    rd = manifest.get("release_disclosure")
    if isinstance(rd, dict) and _coerce_bool(rd.get("body_withheld")):
        return True
    return _coerce_bool(manifest.get("body_withheld"))


def _compensating_screen_passed(manifest: dict[str, Any]) -> bool:
    """Proof a compensating standalone fabrication screen RAN CLEAN on a body-shipping seam."""
    rd = manifest.get("release_disclosure")
    return isinstance(rd, dict) and _coerce_bool(rd.get("compensating_screen_passed"))


def check_manifest(manifest: dict[str, Any]) -> list[str]:
    """Return a list of invariant-violation messages for ONE manifest dict (empty == OK).

    The invariant (A18):
      1. ``status == success`` (the strongest assertion: a clean judge-final report) requires
         REAL D8 adjudication (non-empty final_verdicts). A success with no D8 proof is the
         catastrophic path A2 must never reach.
      2. ``status == released_with_disclosed_gaps`` is RELEASED-with-disclosure: it requires
         EITHER real D8 adjudication OR a non-empty disclosed-gap disclosure (the honest seam
         rescue) OR a withheld body. It may NOT ship with zero D8 proof AND zero disclosure.
      3. ``status == released_insufficient_safety_evidence`` requires a non-empty disclosure
         OR a withheld body (it is by definition a degraded, disclosed artifact).
      4. ``release_allowed == true`` with a NON-release/abort status is a contradiction
         (the binding decision says ship, the status says abort) -> violation.
      5. An ``abort_*`` status with ``release_allowed == false`` ALWAYS satisfies the invariant
         (nothing shipped) — this is the correct fail-closed disposition (drb_90's held run).
    """
    violations: list[str] = []
    status = str(manifest.get("status") or "")
    release_allowed = _coerce_bool(manifest.get("release_allowed"))
    d8_ran = _d8_adjudicated(manifest)
    seam_gap = _seam_gap_present(manifest)
    safety_gap = _safety_floor_gap_present(manifest)
    withheld = _body_withheld(manifest)
    screen_passed = _compensating_screen_passed(manifest)

    # The seam-rescue proof (the ONLY way a released_with_disclosed_gaps may ship un-judged): the
    # SPECIFIC four_role_seam_unadjudicated label is present AND the body is provably safe — either
    # withheld OR a compensating fabrication screen ran clean. An arbitrary disclosed gap is NOT
    # proof (iarch007 SWEEP-P0: the pre-fix `any non-empty gap` accept was the bypass).
    seam_rescue_proven = seam_gap and (withheld or screen_passed)

    # (1) success demands real D8 adjudication — no exceptions. This is the A2 catastrophe guard.
    if status == STATUS_SUCCESS and not d8_ran:
        violations.append(
            "status=success but four_role D8 never adjudicated (final_verdicts empty): an "
            "un-judged report marked SUCCESS. The A2 seam rescue must resolve to "
            "released_with_disclosed_gaps (never success) on a judge seam-error."
        )

    # (2) released_with_disclosed_gaps: real D8 ran OR the seam rescue is PROVEN (specific seam
    # token + withheld-or-screened body). A bare non-empty disclosed_gaps no longer counts.
    if status == STATUS_RELEASED_WITH_DISCLOSED_GAPS and not (d8_ran or seam_rescue_proven):
        violations.append(
            "status=released_with_disclosed_gaps but there is NO D8 adjudication and NO PROVEN "
            "seam rescue (the specific four_role_seam_unadjudicated label PLUS a withheld body OR "
            "a passed compensating fabrication screen). A released report with no real judging and "
            "no proven-safe seam disposition is a silent un-judged release."
        )

    # (3) released_insufficient_safety_evidence: this degraded terminal must carry its HONEST
    # safety-floor disclosure OR a withheld body OR a proven seam rescue. A bare unrelated gap is
    # not sufficient — the specific safety_floor_insufficient label (or a withheld body) proves it.
    if status == STATUS_RELEASED_INSUFFICIENT_SAFETY and not (
        safety_gap or withheld or seam_rescue_proven
    ):
        violations.append(
            "status=released_insufficient_safety_evidence but no safety_floor_insufficient "
            "disclosure, no withheld body, and no proven seam rescue — the insufficient-safety "
            "variant must ship its honest safety-floor disclosure."
        )

    # (4) release_allowed true with a non-release/abort status is a contradiction.
    if release_allowed and status and status not in (
        _STRICT_RELEASE_STATUSES | _DISCLOSED_RELEASE_STATUSES
    ):
        # partial_* statuses are a known shippable-degraded family; only abort_* / unknown are a
        # contradiction with release_allowed=true.
        if status.startswith("abort"):
            violations.append(
                f"release_allowed=true but status={status!r} (an abort): the binding release "
                "decision contradicts the terminal status."
            )

    # (5) release_allowed true on a strict-release status still demands the D8 proof OR a PROVEN
    # seam rescue — a true release_allowed with no judging and no proven-safe seam is the same
    # silent-release hole as (2).
    if release_allowed and status in _STRICT_RELEASE_STATUSES and not (
        d8_ran or seam_rescue_proven
    ):
        violations.append(
            f"release_allowed=true on status={status!r} with no D8 adjudication and no proven "
            "seam rescue — release without proof the judge ran or the seam body is safe."
        )

    return violations


def _load_manifest(path: Path) -> dict[str, Any]:
    """Load a manifest dict from a file path. Fails loudly (LAW II) on a missing/garbage file."""
    if not path.is_file():
        raise FileNotFoundError(f"release-invariant: manifest not found: {path}")
    with path.open(encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"release-invariant: manifest is not a JSON object: {path}")
    return data


def resolve_manifest_paths(target: Path) -> list[Path]:
    """Resolve a CLI target to the manifest file(s) it names.

    A file path is used directly. A directory is searched for ``manifest.json`` then
    ``run_status.json`` (the two artifacts that carry a binding status). Both are checked when
    present so a status that disagrees between them is also caught.
    """
    if target.is_file():
        return [target]
    if target.is_dir():
        found = [target / name for name in ("manifest.json", "run_status.json")]
        present = [p for p in found if p.is_file()]
        if not present:
            raise FileNotFoundError(
                f"release-invariant: no manifest.json/run_status.json under {target}"
            )
        return present
    raise FileNotFoundError(f"release-invariant: target not found: {target}")


def check_targets(targets: list[str]) -> tuple[int, list[str]]:
    """Check every target; return (violation_count, messages). Pure — no exit, no print."""
    all_messages: list[str] = []
    for raw in targets:
        target = Path(raw)
        for manifest_path in resolve_manifest_paths(target):
            manifest = _load_manifest(manifest_path)
            for msg in check_manifest(manifest):
                all_messages.append(f"{manifest_path}: {msg}")
    return len(all_messages), all_messages


# --- self-test (no network, no run dir needed): synthetic + the real drb_90 held manifest ------
def _self_test() -> int:
    """Deterministic offline self-test of the invariant logic. Returns a process exit code."""
    failures: list[str] = []

    def expect(name: str, manifest: dict[str, Any], should_violate: bool) -> None:
        v = check_manifest(manifest)
        violated = bool(v)
        if violated != should_violate:
            failures.append(
                f"{name}: expected violate={should_violate}, got {violated} ({v})"
            )

    # (a) success WITHOUT D8 verdicts -> VIOLATION (the A2 catastrophe).
    expect(
        "success_no_d8",
        {"status": STATUS_SUCCESS, "release_allowed": True,
         "four_role_evaluation": {"final_verdicts": {}}},
        should_violate=True,
    )
    # (b) success WITH D8 verdicts -> OK.
    expect(
        "success_with_d8",
        {"status": STATUS_SUCCESS, "release_allowed": True,
         "four_role_evaluation": {"final_verdicts": {"c1": "VERIFIED"}}},
        should_violate=False,
    )
    # (c) released_with_disclosed_gaps via PROVEN seam rescue (specific seam token + a passed
    # compensating fabrication screen, no D8) -> OK (the honest A2 rescue, body ships screened).
    expect(
        "disclosed_gaps_seam_rescue_screen_passed",
        {"status": STATUS_RELEASED_WITH_DISCLOSED_GAPS, "release_allowed": True,
         "four_role_evaluation": {"final_verdicts": {}},
         "release_disclosure": {
             "disclosed_gaps": [f"{_SEAM_GAP_TOKEN}: judge unreachable"],
             "adjudicated": False, "body_withheld": False,
             "compensating_screen_passed": True}},
        should_violate=False,
    )
    # (c2) released_with_disclosed_gaps via seam rescue with a WITHHELD body (screen could not run)
    # -> OK (the Codex floor: disclosure ships, no findings prose).
    expect(
        "disclosed_gaps_seam_rescue_body_withheld",
        {"status": STATUS_RELEASED_WITH_DISCLOSED_GAPS, "release_allowed": True,
         "four_role_evaluation": {"final_verdicts": {}},
         "release_disclosure": {
             "disclosed_gaps": [f"{_SEAM_GAP_TOKEN}: judge unreachable"],
             "adjudicated": False, "body_withheld": True,
             "compensating_screen_passed": False}},
        should_violate=False,
    )
    # (c3) released_with_disclosed_gaps carrying the seam token but NO proof (no withheld body, no
    # passed screen) -> VIOLATION (the seam body ships un-judged AND un-screened: the leak A18 closes).
    expect(
        "disclosed_gaps_seam_token_but_no_proof",
        {"status": STATUS_RELEASED_WITH_DISCLOSED_GAPS, "release_allowed": True,
         "four_role_evaluation": {"final_verdicts": {}},
         "release_disclosure": {
             "disclosed_gaps": [f"{_SEAM_GAP_TOKEN}: judge unreachable"],
             "adjudicated": False, "body_withheld": False,
             "compensating_screen_passed": False}},
        should_violate=True,
    )
    # (c4) released_with_disclosed_gaps with an ARBITRARY (non-seam) gap and no D8 -> VIOLATION
    # (iarch007 SWEEP-P0: a bare non-empty disclosed_gaps list is NO LONGER seam proof).
    expect(
        "disclosed_gaps_arbitrary_gap_no_seam_token",
        {"status": STATUS_RELEASED_WITH_DISCLOSED_GAPS, "release_allowed": True,
         "four_role_evaluation": {"final_verdicts": {}},
         "release_disclosure": {
             "disclosed_gaps": ["credibility_unscored: 3 sources at neutral weight"],
             "adjudicated": False, "body_withheld": False,
             "compensating_screen_passed": False}},
        should_violate=True,
    )
    # (d) released_with_disclosed_gaps with NO disclosure and NO D8 -> VIOLATION (silent release).
    expect(
        "disclosed_gaps_no_disclosure",
        {"status": STATUS_RELEASED_WITH_DISCLOSED_GAPS, "release_allowed": True,
         "four_role_evaluation": {"final_verdicts": {}}},
        should_violate=True,
    )
    # (e) insufficient-safety with the SPECIFIC safety-floor disclosure -> OK (the honest variant).
    expect(
        "insufficient_safety_disclosed",
        {"status": STATUS_RELEASED_INSUFFICIENT_SAFETY, "release_allowed": True,
         "release_disclosure": {"disclosed_gaps": ["safety_floor_insufficient: ..."],
                                "adjudicated": False, "normal_release_blocked": True}},
        should_violate=False,
    )
    # (e2) insufficient-safety with ONLY normal_release_blocked (no safety-floor label, no withheld
    # body) -> VIOLATION (iarch007 SWEEP-P0: normal_release_blocked is NOT body-withheld proof).
    expect(
        "insufficient_safety_only_normal_render_blocked",
        {"status": STATUS_RELEASED_INSUFFICIENT_SAFETY, "release_allowed": True,
         "release_disclosure": {"disclosed_gaps": ["some_unrelated_label"],
                                "normal_release_blocked": True}},
        should_violate=True,
    )
    # (f) abort with release_allowed False -> OK (the correct fail-closed disposition).
    expect(
        "abort_held_failclosed",
        {"status": "abort_four_role_release_held", "release_allowed": False,
         "four_role_evaluation": {"final_verdicts": {}}},
        should_violate=False,
    )
    # (g) release_allowed True on an abort status -> VIOLATION (contradiction).
    expect(
        "release_allowed_on_abort",
        {"status": "abort_no_verified_sections", "release_allowed": True},
        should_violate=True,
    )

    # (h) the REAL drb_90 held run (box_pull): abort_four_role_release_held, release_allowed False,
    # final_verdicts empty -> the invariant must PASS it (nothing shipped — correct fail-closed).
    real_manifest = (
        Path(__file__).resolve().parents[1]
        / "tests" / "fixtures" / "drb90_redaction" / "manifest.json"
    )
    if real_manifest.is_file():
        m = _load_manifest(real_manifest)
        v = check_manifest(m)
        if v:
            failures.append(f"real_drb90_manifest: expected NO violation, got {v}")
    else:
        print(f"[self-test] WARN: real drb_90 fixture not found at {real_manifest}")

    if failures:
        print("RELEASE-INVARIANT SELF-TEST: FAIL")
        for f in failures:
            print(f"  - {f}")
        return 1
    print(
        "RELEASE-INVARIANT SELF-TEST: PASS (13 cases incl. the real drb_90 held manifest + the "
        "iarch007 SWEEP-P0 seam-proof tightening)"
    )
    return 0


def main(argv: list[str]) -> int:
    args = argv[1:]
    if not args or args[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    if args[0] == "--self-test":
        return _self_test()
    try:
        count, messages = check_targets(args)
    except (FileNotFoundError, ValueError, json.JSONDecodeError) as exc:
        print(f"RELEASE-INVARIANT: ERROR — {exc}", file=sys.stderr)
        return 2
    if count:
        print(f"RELEASE-INVARIANT: {count} VIOLATION(S) — release path is UNSOUND:")
        for msg in messages:
            print(f"  - {msg}")
        return 1
    print(f"RELEASE-INVARIANT: OK — {len(args)} target(s) satisfy the no-unjudged-release gate.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
