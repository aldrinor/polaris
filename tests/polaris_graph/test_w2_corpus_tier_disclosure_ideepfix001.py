"""I-deepfix-001 (#1344) W2 — behavioral test for the corpus tier-deviation
ABORT -> DISCLOSURE conversion (delete a banned corpus-level filter-and-cap).

W2 SPEC (beatboth_comprehensive_plan.md §2): the ``corpus_approval_gate`` used to
abort the ENTIRE run (``abort_corpus_approval_denied``) when the corpus tier mix
deviated >=15pp from a per-domain ``expected_tier_distribution`` TARGET — a banned
filter-and-cap at corpus level. An off-template BUT FAITHFUL corpus scored ZERO.
W2 converts that ABORT into a non-blocking DISCLOSURE: the run PROCEEDS carrying the
corpus credibility PROFILE (per-tier counts + fractions + signed deviation), surfaced
to the user. The faithfulness engine (strict_verify / NLI / 4-role D8 / provenance /
span-grounding) stays the ONLY hard gate; a T5/T6-heavy claim carries a low DISCLOSED
weight, so clinical safety is unchanged.

These are FAIL-LOUD behavioral tests over the REAL approval-decision output of
``check_auto_approve_allowed`` — the single function the paid launcher
(run_honest_sweep_r3.py:10784) consults for the abort-vs-proceed decision:

  * RED  (mode OFF, default): a material-deviation corpus with no structured
          authorization DENIES (the banned whole-run abort still fires — the
          §6.2-approval kill-switch is OPT-IN, so OFF is byte-identical to pre-W2).
  * GREEN (mode ON): the SAME corpus PROCEEDS (ok=True) and the tier skew is
          SURFACED in the disclosure message + the credibility profile — never a
          silent accept, never a dropped source (WEIGHT-not-FILTER).

EVERYTHING IS OFFLINE: NO spend, NO network, NO GPU, NO model LOAD. The FROZEN
faithfulness engine is NEVER touched — this is corpus-approval wiring only.
"""

from __future__ import annotations

import ast
import importlib.util
import json
import os
from pathlib import Path

import pytest

from src.polaris_graph.nodes.corpus_approval_gate import (
    PG_CORPUS_TIER_DISCLOSURE_MODE_ENV,
    AuthorizedSweep,
    CorpusApprovalDecision,
    CorpusSource,
    build_corpus_credibility_profile,
    check_auto_approve_allowed,
    compute_tier_distribution,
    corpus_tier_disclosure_mode_enabled,
    format_tier_deviation_disclosure,
    save_approval_decision,
    tier_disclosure_artifacts,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(autouse=True)
def _isolate_env():
    """Snapshot/restore os.environ so a forced flag never leaks into a sibling
    test (mirrors the dr_benchmark test conventions)."""
    snap = dict(os.environ)
    # Ensure a clean default: neither the W2 disclosure flag nor a structured
    # authorization is set unless a test opts in.
    os.environ.pop(PG_CORPUS_TIER_DISCLOSURE_MODE_ENV, None)
    os.environ.pop("PG_AUTHORIZED_SWEEP_APPROVAL", None)
    try:
        yield
    finally:
        os.environ.clear()
        os.environ.update(snap)


def _clinical_protocol() -> dict:
    return {
        "research_question": "Semaglutide for weight loss",
        "expected_tier_distribution": [
            {"tier": "T1", "min_fraction": 0.30, "max_fraction": 0.60},
            {"tier": "T2", "min_fraction": 0.15, "max_fraction": 0.40},
            {"tier": "T3", "min_fraction": 0.05, "max_fraction": 0.25},
            {"tier": "T5", "min_fraction": 0.00, "max_fraction": 0.15},
            {"tier": "T6", "min_fraction": 0.00, "max_fraction": 0.10},
        ],
    }


def _tier_skewed_but_faithful_corpus() -> list[CorpusSource]:
    """An off-template ECONOMICS-style corpus: 80% T5 (WEF / institute / reputable
    non-journal) + 20% T1. Materially deviates from the CLINICAL protocol's tier
    TARGET but every source is a real, faithful source — exactly the case W2 must
    let PROCEED under disclosure rather than abort at ZERO."""
    return [
        CorpusSource(url=f"https://weforum.org/{i}", tier="T5", domain="weforum.org")
        for i in range(8)
    ] + [
        CorpusSource(url="https://doi.org/r1", tier="T1", domain="doi.org"),
        CorpusSource(url="https://doi.org/r2", tier="T1", domain="doi.org"),
    ]


# ── the material-deviation precondition (shared by RED + GREEN) ────────────────────
def test_corpus_is_a_genuine_material_deviation() -> None:
    """Precondition: the fixture corpus IS a material deviation, so the RED/GREEN
    split below is exercising the real abort-vs-disclose branch."""
    report = compute_tier_distribution(
        _tier_skewed_but_faithful_corpus(), _clinical_protocol()
    )
    assert report.has_material_deviation is True
    assert report.total_sources == 10
    assert report.tier_fractions["T5"] == 0.80  # above protocol max 0.15


# ── RED: mode OFF (default) is byte-identical to the pre-W2 abort ──────────────────
def test_mode_off_material_deviation_still_denies_no_authorization() -> None:
    """DEFAULT (disclosure OFF, no structured authorization): the material-deviation
    corpus DENIES — the banned whole-run abort still fires. Proves W2 did not
    silently flip the canonical-pinned §9.1 invariant #5; the change is opt-in."""
    assert corpus_tier_disclosure_mode_enabled() is False
    report = compute_tier_distribution(
        _tier_skewed_but_faithful_corpus(), _clinical_protocol()
    )
    ok, err = check_auto_approve_allowed(report, authorization=None)
    assert ok is False
    assert "abort_corpus_approval_denied" in err


# ── GREEN: mode ON via the explicit arg — the run PROCEEDS + the skew is surfaced ──
def test_mode_on_arg_material_deviation_proceeds_and_discloses() -> None:
    """DISCLOSURE mode ON (explicit ``disclosure_mode=True``): the SAME material-
    deviation corpus PROCEEDS (ok=True) and the tier skew is SURFACED in the
    message — the abort is DELETED, replaced by a disclosure. No structured
    authorization is needed (the whole point: an honest off-template corpus should
    not need a rubber stamp)."""
    report = compute_tier_distribution(
        _tier_skewed_but_faithful_corpus(), _clinical_protocol()
    )
    ok, msg = check_auto_approve_allowed(
        report, authorization=None, disclosure_mode=True
    )
    assert ok is True, "W2 disclosure mode must PROCEED on a material deviation"
    # The skew is SURFACED, not silently accepted: the disclosure names the
    # materially-deviating tier (T5) and its actual fraction (80.0%).
    assert "DISCLOSURE" in msg
    assert "T5" in msg
    assert "80.0%" in msg
    # And it is honest that it PROCEEDED (did not abort).
    assert "abort_corpus_approval_denied" not in msg


# ── GREEN: mode ON via the env kill-switch (LAW VI config-driven) ─────────────────
def test_mode_on_env_material_deviation_proceeds() -> None:
    """The env kill-switch ``PG_CORPUS_TIER_DISCLOSURE_MODE=1`` alone (no explicit
    arg) flips the abort to a disclosure — LAW VI config-driven, no hard-code."""
    os.environ[PG_CORPUS_TIER_DISCLOSURE_MODE_ENV] = "1"
    assert corpus_tier_disclosure_mode_enabled() is True
    report = compute_tier_distribution(
        _tier_skewed_but_faithful_corpus(), _clinical_protocol()
    )
    ok, msg = check_auto_approve_allowed(report, authorization=None)
    assert ok is True
    assert "DISCLOSURE" in msg


# ── WEIGHT-not-FILTER: the profile surfaces the skew and drops ZERO sources ────────
def test_credibility_profile_surfaces_skew_and_drops_no_source() -> None:
    """The corpus credibility PROFILE surfaces every tier + the material-deviation
    flag while keeping ALL 10 sources — §-1.3 WEIGHT-not-FILTER: the skew is a
    DISCLOSED weight, never a drop/cap."""
    sources = _tier_skewed_but_faithful_corpus()
    report = compute_tier_distribution(sources, _clinical_protocol())
    profile = build_corpus_credibility_profile(report)
    # NO source dropped — total equals the full corpus.
    assert profile["total_sources"] == len(sources) == 10
    assert profile["material_deviation_present"] is True
    assert profile["tier_counts"]["T5"] == 8
    assert profile["tier_counts"]["T1"] == 2
    # The material tier is flagged in the surfaced per-tier deviations.
    t5 = next(d for d in profile["tier_deviations"] if d["tier"] == "T5")
    assert t5["is_material"] is True
    assert t5["actual_fraction"] == 0.80


# ── faithfulness-neutral guards: the change touches ONLY the material-deviation branch
def test_no_material_deviation_returns_ok_both_modes() -> None:
    """An on-protocol corpus auto-approves regardless of disclosure mode — the W2
    branch only engages when there is a material deviation."""
    on_protocol = [
        CorpusSource(url=f"https://doi.org/{i}", tier="T1", domain="doi.org")
        for i in range(4)  # 40% T1 (within 30-60%)
    ] + [
        CorpusSource(url=f"https://cochrane.org/{i}", tier="T2", domain="cochrane.org")
        for i in range(3)  # 30% T2 (within 15-40%)
    ] + [
        CorpusSource(url=f"https://fda.gov/{i}", tier="T3", domain="fda.gov")
        for i in range(2)  # 20% T3 (within 5-25%)
    ] + [
        CorpusSource(url="https://novomedlink.com/1", tier="T5", domain="novo"),  # 10% T5
    ]
    report = compute_tier_distribution(on_protocol, _clinical_protocol())
    assert report.has_material_deviation is False
    for mode in (False, True):
        ok, err = check_auto_approve_allowed(report, disclosure_mode=mode)
        assert ok is True
        assert err == ""


def test_structured_authorization_still_approves_when_mode_off() -> None:
    """A valid structured AuthorizedSweep still auto-approves a material deviation
    with disclosure mode OFF — W2 did not weaken the FX-05 credential path."""
    report = compute_tier_distribution(
        _tier_skewed_but_faithful_corpus(), _clinical_protocol()
    )
    auth = AuthorizedSweep(
        authorized_by="env:PG_AUTHORIZED_SWEEP_APPROVAL",
        authorized_at="2026-07-03T00:00:00Z",
        flag_source="env",
    )
    ok, err = check_auto_approve_allowed(report, authorization=auth, disclosure_mode=False)
    assert ok is True
    assert err == ""


def test_format_disclosure_names_material_tier() -> None:
    """The disclosure string is a plain-English surface of the material skew."""
    report = compute_tier_distribution(
        _tier_skewed_but_faithful_corpus(), _clinical_protocol()
    )
    text = format_tier_deviation_disclosure(report)
    assert "T5" in text
    assert "PROCEEDED" in text
    assert "faithfulness engine" in text


# ── PRODUCTION-PATH EFFECT: the disclosure + profile reach the PERSISTED artifacts ──
# The Codex gate P1: check_auto_approve_allowed returns ok=True + a disclosure message,
# but the paid launcher (run_honest_sweep_r3.py) kept that message only in a local
# variable read on the ABORT branch — so on an APPROVED W2 run the skew was NOT
# persisted (the note read "no structured authorization", the profile was never built
# in production). tier_disclosure_artifacts is the single helper the launcher now calls;
# these tests prove it makes the skew DURABLE in corpus_approval.json + the profile
# sidecar, and stays byte-identical (nothing attached) when the W2 path did not fire.


def test_tier_disclosure_artifacts_fires_on_approved_material_deviation() -> None:
    """When disclosure mode is ON, the run is approved, and the deviation is material,
    the helper returns BOTH the durable note and the keep-ALL profile."""
    report = compute_tier_distribution(
        _tier_skewed_but_faithful_corpus(), _clinical_protocol()
    )
    note, profile = tier_disclosure_artifacts(
        report, approved=True, disclosure_mode=True
    )
    assert note, "disclosure note must be non-empty on the fired path"
    assert "T5" in note and "DISCLOSURE" in note
    assert profile is not None
    assert profile["total_sources"] == 10  # WEIGHT-not-FILTER: no source dropped
    assert profile["material_deviation_present"] is True


def test_tier_disclosure_artifacts_inert_when_path_did_not_fire() -> None:
    """The helper returns ("", None) — attaching nothing — on every non-fired case:
    disclosure OFF, run denied, or no material deviation. This is the byte-identical
    W2-OFF guard for the persisted artifacts."""
    material = compute_tier_distribution(
        _tier_skewed_but_faithful_corpus(), _clinical_protocol()
    )
    # disclosure mode OFF (default) -> inert even though deviation is material + approved
    assert tier_disclosure_artifacts(material, approved=True, disclosure_mode=False) == ("", None)
    # run DENIED -> inert even with disclosure mode ON
    assert tier_disclosure_artifacts(material, approved=False, disclosure_mode=True) == ("", None)
    # no material deviation -> inert regardless of mode
    on_protocol = [
        CorpusSource(url=f"https://doi.org/{i}", tier="T1", domain="doi.org")
        for i in range(4)
    ] + [
        CorpusSource(url=f"https://cochrane.org/{i}", tier="T2", domain="cochrane.org")
        for i in range(3)
    ] + [
        CorpusSource(url=f"https://fda.gov/{i}", tier="T3", domain="fda.gov")
        for i in range(2)
    ] + [
        CorpusSource(url="https://novomedlink.com/1", tier="T5", domain="novo"),
    ]
    clean = compute_tier_distribution(on_protocol, _clinical_protocol())
    assert tier_disclosure_artifacts(clean, approved=True, disclosure_mode=True) == ("", None)


def _reconstruct_launcher_persist(report, *, approved, disclosure_mode, run_dir):
    """Reproduce EXACTLY the launcher's W2 persistence seam (run_honest_sweep_r3.py:
    the note append + save_approval_decision + the profile sidecar) so the test proves
    the persisted-artifact effect, not just the helper in isolation."""
    note = "R-3 sweep. Domain=labor. " + (
        "structured authorization present" if False else "no structured authorization"
    )
    disclosure_note, profile = tier_disclosure_artifacts(
        report, approved=approved, disclosure_mode=disclosure_mode
    )
    if disclosure_note:
        note = note + " | " + disclosure_note
    decision = CorpusApprovalDecision(
        run_id="w2_effect_test",
        decision_at_unix=0.0,
        decision_at_iso="2026-07-03T00:00:00Z",
        approved=approved,
        user_note=note,
    )
    save_approval_decision(decision, run_dir)
    if profile is not None:
        (Path(run_dir) / "corpus_tier_disclosure_profile.json").write_text(
            json.dumps(profile, indent=2, sort_keys=True, default=str) + "\n",
            encoding="utf-8",
        )


def test_persisted_approval_json_carries_disclosure_when_mode_on(tmp_path) -> None:
    """PRODUCTION-PATH EFFECT (fired): with disclosure mode ON + approved, the durable
    corpus_approval.json note carries the skew disclosure (no longer the misleading
    'no structured authorization' alone) AND the profile sidecar is written keeping ALL
    sources. This is the exact artifact a downstream audit / manifest reads."""
    report = compute_tier_distribution(
        _tier_skewed_but_faithful_corpus(), _clinical_protocol()
    )
    _reconstruct_launcher_persist(
        report, approved=True, disclosure_mode=True, run_dir=tmp_path
    )
    approval = json.loads((tmp_path / "corpus_approval.json").read_text(encoding="utf-8"))
    # FAIL LOUD if the disclosure did not reach the persisted note.
    assert "DISCLOSURE" in approval["user_note"]
    assert "T5" in approval["user_note"]
    assert "80.0%" in approval["user_note"]
    # The keep-ALL profile sidecar exists and drops no source.
    sidecar = tmp_path / "corpus_tier_disclosure_profile.json"
    assert sidecar.exists(), "W2 profile sidecar must be persisted on the fired path"
    profile = json.loads(sidecar.read_text(encoding="utf-8"))
    assert profile["total_sources"] == 10
    assert profile["material_deviation_present"] is True


def test_persisted_approval_json_byte_identical_when_mode_off(tmp_path) -> None:
    """PRODUCTION-PATH EFFECT (not fired): with disclosure mode OFF the persisted note
    is UNCHANGED (no disclosure text appended) and NO profile sidecar is written — the
    kill-switch keeps the artifacts byte-identical to pre-W2."""
    report = compute_tier_distribution(
        _tier_skewed_but_faithful_corpus(), _clinical_protocol()
    )
    # Denied on the OFF default (matches the launcher: approved=False when no auth).
    _reconstruct_launcher_persist(
        report, approved=False, disclosure_mode=False, run_dir=tmp_path
    )
    approval = json.loads((tmp_path / "corpus_approval.json").read_text(encoding="utf-8"))
    assert "DISCLOSURE" not in approval["user_note"]
    assert not (tmp_path / "corpus_tier_disclosure_profile.json").exists()


def test_launcher_module_imports_the_wiring_helper() -> None:
    """The paid launcher module actually imports tier_disclosure_artifacts — proves the
    production seam references the wiring helper (not a dangling unit-only function)."""
    path = _REPO_ROOT / "scripts" / "run_honest_sweep_r3.py"
    spec = importlib.util.spec_from_file_location("_rhs_w2_effect_test", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert hasattr(module, "tier_disclosure_artifacts"), (
        "run_honest_sweep_r3.py must import tier_disclosure_artifacts for the W2 wiring"
    )


# ── SOURCE-LEVEL PRODUCTION-SEAM PROOF (Codex iter-2 P1) ───────────────────────────
# The import test above is necessary but NOT sufficient: an import alone would survive
# even if the production CALL, the sidecar write, and the manifest attach were all
# deleted. Codex iter-2 P1: "add a source-level or production-seam assertion that fails
# unless tier_disclosure_artifacts is actually CALLED on the approved path and the
# success manifest attaches corpus_tier_disclosure_profile." These three AST tests parse
# run_honest_sweep_r3.py's real source and FAIL LOUD if any of the three production-seam
# statements is removed — so the W2 wiring cannot silently rot to import-only.


def _launcher_ast() -> ast.Module:
    """Parse the real launcher source (no import/exec, so no heavy deps load)."""
    path = _REPO_ROOT / "scripts" / "run_honest_sweep_r3.py"
    return ast.parse(path.read_text(encoding="utf-8"))


def _slice_constant(node: ast.Subscript):
    """Return the constant subscript key across 3.8 (ast.Index) and 3.9+ (bare node)."""
    sl = node.slice
    if isinstance(sl, ast.Index):  # pragma: no cover - Python <3.9 only
        sl = sl.value
    return sl.value if isinstance(sl, ast.Constant) else None


def test_launcher_source_CALLS_helper_and_binds_the_profile() -> None:
    """FAIL LOUD unless the launcher actually CALLS tier_disclosure_artifacts AND binds
    its second return into ``_w2_tier_disclosure_profile`` — the variable that drives the
    sidecar + manifest. Deleting the production call (leaving only the import) breaks this."""
    tree = _launcher_ast()
    # There is at least one real Call to the helper.
    called = any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "tier_disclosure_artifacts"
        for node in ast.walk(tree)
    )
    assert called, (
        "run_honest_sweep_r3.py must CALL tier_disclosure_artifacts on the approval path "
        "(an import with no call would leave the W2 disclosure un-wired in production)"
    )
    # The call result is BOUND to the profile var (a discarded result would persist nothing).
    bound = False
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Assign)
            and isinstance(node.value, ast.Call)
            and isinstance(node.value.func, ast.Name)
            and node.value.func.id == "tier_disclosure_artifacts"
        ):
            names: set[str] = set()
            for tgt in node.targets:
                elts = tgt.elts if isinstance(tgt, ast.Tuple) else [tgt]
                names |= {e.id for e in elts if isinstance(e, ast.Name)}
            if "_w2_tier_disclosure_profile" in names:
                bound = True
    assert bound, (
        "the tier_disclosure_artifacts result must be bound to _w2_tier_disclosure_profile "
        "(the var the sidecar write + success-manifest attach both read)"
    )


def test_launcher_source_WRITES_the_profile_sidecar() -> None:
    """FAIL LOUD unless the launcher source writes the corpus_tier_disclosure_profile.json
    sidecar — deleting that write removes the durable per-tier profile the audit reads."""
    tree = _launcher_ast()
    consts = {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }
    assert "corpus_tier_disclosure_profile.json" in consts, (
        "run_honest_sweep_r3.py must write the corpus_tier_disclosure_profile.json sidecar "
        "on the fired W2 path (the persisted keep-ALL credibility profile)"
    )


def test_launcher_source_ATTACHES_profile_to_success_manifest() -> None:
    """FAIL LOUD unless the SUCCESS manifest attaches the W2 profile under
    manifest["corpus_tier_disclosure_profile"] = _w2_tier_disclosure_profile — the exact
    manifest attach Codex iter-2 P1 requires; deleting it must fail this test."""
    tree = _launcher_ast()
    attached = False
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        for tgt in node.targets:
            if (
                isinstance(tgt, ast.Subscript)
                and isinstance(tgt.value, ast.Name)
                and tgt.value.id == "manifest"
                and _slice_constant(tgt) == "corpus_tier_disclosure_profile"
                and isinstance(node.value, ast.Name)
                and node.value.id == "_w2_tier_disclosure_profile"
            ):
                attached = True
    assert attached, (
        "the success manifest must attach manifest['corpus_tier_disclosure_profile'] = "
        "_w2_tier_disclosure_profile (deleting this attach must break the W2 effect test)"
    )
