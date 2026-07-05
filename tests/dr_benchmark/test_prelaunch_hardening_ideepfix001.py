"""I-deepfix-001 pre-launch hardening — the "serious-check won't-go-dark gap" (2026-07-05).

Offline, hermetic. NO network, NO spend, NO GPU, NO model load.

Covers the 22 ALWAYS-ON faithfulness / render / validity fixes that were BUILT default-ON in their
module but were NOT pinned onto the paid DRB-II slate — so a stray operator/.env =0 could SILENTLY
DARK the fix on a paid run. This build QUAD-wires each onto ``scripts/dr_benchmark/run_gate_b.py``
(slate "1" + force-on + preflight-required + winner-allowlist), exactly like the scope flags.

Two guarantees are asserted:
  * STRUCTURAL — every hardening flag is present in ALL FOUR collections (slate ="1", force-on,
    preflight-required, winner-allowlist). The slate membership is what makes the preflight-required
    membership SAFE (``apply_full_capability_benchmark_slate`` force-sets ``os.environ[name]="1"``);
    a preflight-required flag NOT in the slate would read ``os.getenv(...,"0")=="0"`` and FALSE-ABORT.
  * BEHAVIORAL — RED-before / GREEN-after: with the clean winners-only slate applied the offline
    preflight PASSES (no false-abort); with exactly ONE hardening flag forced =0 the fail-closed
    preflight RAISES ``RuntimeError`` naming that flag (so a silently-darked fix can never reach spend).

Mirrors tests/dr_benchmark/test_purity_preflight_gates.py + test_slate_readiness_flags_iready016b.py
conventions (the proven clean-slate + offline-preflight harness). The FROZEN faithfulness engine
(strict_verify / NLI / 4-role D8 / provenance / span-grounding) is NEVER touched here.
"""

from __future__ import annotations

import os
import sys
import types

import pytest

# The W4/W5 GPU probes only bind when offline=False, so an absent ``torch`` is irrelevant to these
# offline tests. But run_gate_b imports torch lazily on a few paths; stub a minimal cuda-present module
# ONLY if torch is genuinely uninstalled (probe importlib first so a REAL torch is never shadowed —
# the Codex P2-global-torch-stub-pollution guard from the purity test).
if "torch" not in sys.modules:  # pragma: no cover - only on a no-torch CI host
    import importlib.util as _importlib_util

    if _importlib_util.find_spec("torch") is None:
        _torch_stub = types.ModuleType("torch")
        _torch_stub.cuda = types.SimpleNamespace(is_available=lambda: True)
        sys.modules["torch"] = _torch_stub

from scripts.dr_benchmark import run_gate_b
from scripts.dr_benchmark.run_gate_b import (
    _BENCHMARK_FORCE_ON_FLAGS,
    _BENCHMARK_PREFLIGHT_REQUIRED_FLAGS,
    _BENCHMARK_PREFLIGHT_REQUIRED_OFF_FLAGS,
    _FULL_CAPABILITY_BENCHMARK_SLATE,
    _WINNER_FLAG_ALLOWLIST,
    apply_full_capability_benchmark_slate,
    preflight_full_capability,
)

# The 22 ALWAYS-ON faithfulness / render / validity fixes pinned by this build. Kept as an explicit
# literal (NOT derived from the slate) so a DROPPED pin fails this test LOUDLY instead of silently
# shrinking the asserted set.
_HARDENING_FLAGS: tuple[str, ...] = (
    "PG_RENDER_VERDICT_GATE",
    "PG_RENDER_SUMMARY_TABLE",
    "PG_SOURCE_NECESSITY_QUARANTINE",
    "PG_SNAP_MEMBER_BOUNDARY",
    "PG_S11_SEC8_DISCLOSURE_WEIGHT",
    "PG_S12_SEC8_D8_DEMOTE",
    "PG_S14_METHODS_TIER_FINAL",
    "PG_S15_CORROBORATED_HONEST_LABEL",
    "PG_S17_BIB_COHERENCE",
    "PG_S18_LOWWEIGHT_RECONCILE",
    "PG_QUANTIFIED_UNIT_COMPAT",
    "PG_QUANTIFIED_FILLER_SUPPRESS",
    "PG_ASPECT_OFFTOPIC_SLOT_GUARD",
    "PG_COMPLETENESS_COVERAGE_AGAINST_OUTPUT",
    "PG_UNIT_CONFLATION_GUARD",
    "PG_BLOCK_PAGE_CHROME_SCRUB",
    "PG_BLOCK_PAGE_CHROME_SCRUB_SHARED",
    "PG_PT03_WAIVED_HONEST",
    "PG_CONTRADICTION_RENDER_HONEST",
    "PG_CONTRADICTION_SUPPRESS_METRIC_MISMATCH",
    "PG_FACT_DEDUP_EXACT_INTRASECTION",
    "PG_RUN_VALIDITY_GATE",
)


@pytest.fixture(autouse=True)
def _isolate_env():
    """Snapshot os.environ before each test and restore it after, so a forced flag (or the
    full-capability slate) does not leak into a sibling test."""
    snap = dict(os.environ)
    try:
        yield
    finally:
        os.environ.clear()
        os.environ.update(snap)


def _apply_clean_winners_only_slate() -> None:
    """Reproduce the production env state the run sees JUST BEFORE preflight_full_capability runs (the
    full-capability slate + the programmatic env-forces run_gate_b_query applies), then satisfy the
    COMPLETE required / required-off flag contract so a negative test isolates exactly the flag under
    test. Sourced verbatim from tests/dr_benchmark/test_purity_preflight_gates.py."""
    for _k in (
        "PG_STORM_ENABLED_IN_BENCHMARK", "PG_STORM_INGEST_WEB_RESULTS", "PG_STORM_ENABLED",
        "PG_STORM_OUTLINE_SECTIONS", "PG_STORM_MIN_EFFECTIVE_QUERIES",
        "PG_AGENTIC_SEARCH_IN_BENCHMARK", "PG_SWEEP_EVIDENCE_DEEPENER", "PG_SWEEP_QUERY_DECOMPOSE",
        "PG_QGEN_ITERRESEARCH", "PG_USE_RESEARCH_PLANNER",
        "PG_EMBED_MODEL", "PG_ENTAILMENT_MODEL", "PG_EVALUATOR_MODEL",
        "PG_W9_CONTENT_DEDUP", "PG_W9_DARK_ACK",
    ):
        os.environ.pop(_k, None)

    apply_full_capability_benchmark_slate()

    # F07 strict-gate faithfulness preflight (run_honest_sweep_r3.assert_faithfulness_slate_or_fail)
    # requires the entailment judge == the configured 4-role MIRROR (PG_MIRROR_MODEL). The slate
    # force-EXACTs PG_ENTAILMENT_MODEL to the GLM-5.2 arm; the real paid .env sets PG_MIRROR_MODEL to the
    # same GLM-5.2 arm so they match. Mirror that here so the clean slate genuinely passes F07 and a
    # negative test isolates exactly the hardening flag under test (this is environmental parity with the
    # paid run, NOT a faithfulness change — the mirror value equals the slate's own entailment pin).
    os.environ["PG_MIRROR_MODEL"] = os.environ.get(
        "PG_ENTAILMENT_MODEL", _FULL_CAPABILITY_BENCHMARK_SLATE.get("PG_ENTAILMENT_MODEL", "")
    )

    for _name, _value in {
        "PG_AGENTIC_SEARCH_IN_BENCHMARK": "0",
        "PG_DEPTH_ANNOTATION_IN_BENCHMARK": "1",
        "PG_NLI_IN_BENCHMARK": "1",
        "PG_USE_SAFETY_REFUSAL": "1",
        "PG_SWEEP_NLI_CONFLICT": "1",
        "PG_BENCHMARK_STRICT_GATES": "1",
        "PG_SWEEP_TABLE_CELL_VERIFY": "1",
        "PG_SECTION_DISTILL": "1",
        "PG_RELEVANCE_SCORER": "semantic_v2",
        "PG_TRAFILATURA_SUBPROCESS": "1",
        "PG_PERMIT_GENERATOR_EVALUATOR_SAME_FAMILY": "1",
    }.items():
        os.environ[_name] = _value

    for _flag in _BENCHMARK_PREFLIGHT_REQUIRED_FLAGS:
        os.environ[_flag] = "1"
    for _flag in _BENCHMARK_PREFLIGHT_REQUIRED_OFF_FLAGS:
        os.environ[_flag] = "0"
    os.environ["PG_STRICT_VERIFY_ENTAILMENT"] = "enforce"


def _run_preflight_offline() -> None:
    """Call the preflight on the OFFLINE path — skips only the W4/W5 GPU-host probes; every STRUCTURAL
    check (incl. the required-flags loop) stays unconditional. No spend, no network, no GPU."""
    preflight_full_capability(offline=True)


# ── STRUCTURAL: every hardening flag is QUAD-wired ────────────────────────────────────────────────

@pytest.mark.parametrize("flag", _HARDENING_FLAGS, ids=list(_HARDENING_FLAGS))
def test_hardening_flag_is_quad_wired(flag):
    """Each pre-launch-hardening flag must be present in ALL FOUR collections: the slate (value "1"),
    force-on, preflight-required, and the winner allowlist. The slate="1" membership is what makes the
    preflight-required membership SAFE (apply_slate force-sets os.environ[flag]="1"); a preflight-required
    flag missing from the slate would read os.getenv=="0" and FALSE-ABORT the run before spend."""
    assert flag in _FULL_CAPABILITY_BENCHMARK_SLATE, f"{flag} not in the full-capability slate dict"
    assert _FULL_CAPABILITY_BENCHMARK_SLATE[flag] == "1", (
        f"{flag} slate value is {_FULL_CAPABILITY_BENCHMARK_SLATE[flag]!r}, expected '1'"
    )
    assert flag in _BENCHMARK_FORCE_ON_FLAGS, f"{flag} not in _BENCHMARK_FORCE_ON_FLAGS"
    assert flag in _BENCHMARK_PREFLIGHT_REQUIRED_FLAGS, (
        f"{flag} not in _BENCHMARK_PREFLIGHT_REQUIRED_FLAGS (no fail-closed pre-spend guard)"
    )
    assert flag in _WINNER_FLAG_ALLOWLIST, (
        f"{flag} not in _WINNER_FLAG_ALLOWLIST — SLATE-PURITY would fail closed on the force-on pin"
    )


def test_all_twenty_two_hardening_flags_present():
    """Guard the count so a silently-dropped pin is caught: exactly the 22 documented flags."""
    assert len(_HARDENING_FLAGS) == 22
    assert len(set(_HARDENING_FLAGS)) == 22, "duplicate flag in the hardening list"


# ── BEHAVIORAL: GREEN-after (no false-abort) ──────────────────────────────────────────────────────

def test_clean_slate_passes_offline_preflight_no_false_abort():
    """GREEN-after: with the clean winners-only slate applied (every hardening flag pinned ON by the
    slate), the offline preflight PASSES with NO raise. This proves adding the 22 flags to the
    preflight-required set does NOT false-abort a correctly-slated run."""
    _apply_clean_winners_only_slate()
    _run_preflight_offline()  # no raise == the clean slate (incl. all 22 hardening pins) passes
    # And every hardening flag is truthy "1" in the effective env after the slate (the force-on landed).
    for flag in _HARDENING_FLAGS:
        assert os.environ.get(flag) == "1", f"{flag} not force-set to '1' by the slate"


# ── BEHAVIORAL: RED-before (fail-closed per flag) ─────────────────────────────────────────────────

@pytest.mark.parametrize("off_flag", _HARDENING_FLAGS, ids=list(_HARDENING_FLAGS))
def test_preflight_fails_closed_when_a_hardening_flag_is_off(off_flag):
    """RED-before, ONE TEST PER FLAG: with the clean slate applied but exactly ONE hardening flag forced
    back OFF, the fail-closed preflight must raise RuntimeError naming that flag — so a silently-darked
    faithfulness / render / validity fix can never reach a paid run."""
    _apply_clean_winners_only_slate()
    os.environ[off_flag] = "0"  # turn OFF only the flag under test
    with pytest.raises(RuntimeError) as exc:
        _run_preflight_offline()
    assert off_flag in str(exc.value), (
        f"preflight raised but the message does not name {off_flag!r}: {str(exc.value)[:200]}"
    )
