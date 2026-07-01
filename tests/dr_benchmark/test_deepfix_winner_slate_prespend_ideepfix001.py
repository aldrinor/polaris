"""I-deepfix-001 (#1344) — section test for the three surgical Gate-B fixes:

  * FIX 1 — STORM is KILLED in the full-capability slate (both arms force-EXACT "0" + fail-closed).
  * FIX 2 — the PRE-SPEND winner-slate assertion (assert_full_capability_slate_applied) fails CLOSED
            when a force-on / force-exact WINNER is silently dark (esp. W2 PG_QGEN_FS_RESEARCHER).
  * FIX 3 — the W5 content-relevance score-chunk is slate-pinned to "2" (force-EXACT, not a floor) so a
            stray higher operator/.env value cannot re-open the one-pass co-resident OOM.

EVERYTHING IS OFFLINE: NO spend, NO network, NO GPU, NO model LOAD. Only the slate constants + the
env-only pre-spend assertion are exercised. The FROZEN faithfulness engine (strict_verify / NLI / 4-role
D8 / provenance / span-grounding) is NEVER touched — this is retrieval-orchestration wiring only.

Hermetic: the autouse fixture snapshots/restores os.environ so a forced flag never leaks into a sibling
test (mirrors tests/dr_benchmark/test_purity_preflight_gates.py conventions).
"""

from __future__ import annotations

import os

import pytest

from scripts.dr_benchmark.run_gate_b import (
    _BENCHMARK_FORCE_EXACT_FLAGS,
    _BENCHMARK_FORCE_ON_FLAGS,
    _BENCHMARK_PREFLIGHT_REQUIRED_OFF_FLAGS,
    _FULL_CAPABILITY_BENCHMARK_SLATE,
    apply_full_capability_benchmark_slate,
    assert_full_capability_slate_applied,
)


@pytest.fixture(autouse=True)
def _isolate_env():
    snap = dict(os.environ)
    try:
        yield
    finally:
        os.environ.clear()
        os.environ.update(snap)


# ── FIX 1 — STORM killed in the slate ────────────────────────────────────────────────────────────
def test_slate_kills_storm_both_arms_over_operator_rearm():
    """A stray operator/.env re-arm (=1) of EITHER STORM arm must be force-EXACTed back to "0" by the
    slate, and both arms must be structurally dead (force-EXACT + fail-closed REQUIRED-OFF)."""
    os.environ["PG_STORM_ENABLED_IN_BENCHMARK"] = "1"  # operator tries to re-arm the benchmark gate
    os.environ["PG_STORM_ENABLED"] = "1"               # ...and the storm_interviews module arm
    apply_full_capability_benchmark_slate()
    assert os.environ["PG_STORM_ENABLED_IN_BENCHMARK"] == "0"
    assert os.environ["PG_STORM_ENABLED"] == "0"
    # Structurally dead: slate "0" + force-EXACT + in the fail-closed REQUIRED-OFF set.
    for _arm in ("PG_STORM_ENABLED_IN_BENCHMARK", "PG_STORM_ENABLED"):
        assert _FULL_CAPABILITY_BENCHMARK_SLATE[_arm] == "0"
        assert _arm in _BENCHMARK_FORCE_EXACT_FLAGS
        assert _arm in _BENCHMARK_PREFLIGHT_REQUIRED_OFF_FLAGS


# ── FIX 3 — W5 score-chunk pinned to 2 (force-exact, beats a stray higher value) ───────────────────
def test_slate_pins_w5_score_chunk_to_2_over_stray_higher_value():
    """The W5 content-relevance score-chunk must be slate-pinned to "2" as a FORCE-EXACT value — a stray
    higher operator/.env value (a scratchpad launcher exports 8) would re-open the one-pass co-resident
    OOM that leaves W5 dark, so the pin must be exact, not a floor."""
    os.environ["PG_CONTENT_RELEVANCE_SCORE_CHUNK"] = "8"  # a stray higher value must NOT survive
    apply_full_capability_benchmark_slate()
    assert os.environ["PG_CONTENT_RELEVANCE_SCORE_CHUNK"] == "2"
    assert _FULL_CAPABILITY_BENCHMARK_SLATE["PG_CONTENT_RELEVANCE_SCORE_CHUNK"] == "2"
    assert "PG_CONTENT_RELEVANCE_SCORE_CHUNK" in _BENCHMARK_FORCE_EXACT_FLAGS


# ── FIX 2 — pre-spend winner-slate assertion ──────────────────────────────────────────────────────
def test_prespend_assertion_passes_on_clean_applied_slate():
    """POSITIVE: right after apply_full_capability_benchmark_slate, every force-on/force-exact winner is at
    its slate value, so the pre-spend assertion PASSES with no raise (the exact production order)."""
    apply_full_capability_benchmark_slate()
    assert_full_capability_slate_applied()  # must not raise


def test_prespend_assertion_raises_when_fs_researcher_is_dark():
    """NEGATIVE: with the W2 FS-Researcher winner silently dark (unset after the slate — the drb_72 class),
    the pre-spend assertion must FAIL CLOSED with a RuntimeError naming PG_QGEN_FS_RESEARCHER, BEFORE any
    spend."""
    apply_full_capability_benchmark_slate()
    os.environ.pop("PG_QGEN_FS_RESEARCHER", None)  # simulate the winner going dark
    with pytest.raises(RuntimeError) as exc:
        assert_full_capability_slate_applied()
    msg = str(exc.value)
    assert "WINNER-SLATE-DARK" in msg
    assert "PG_QGEN_FS_RESEARCHER" in msg


def test_prespend_assertion_raises_when_a_force_exact_winner_is_clobbered():
    """NEGATIVE: a stray override of a force-EXACT WINNER (the W5 reranker model) after the slate must also
    fail closed — the assertion covers the force-exact winner flags, not just the booleans."""
    apply_full_capability_benchmark_slate()
    os.environ["PG_CONTENT_RELEVANCE_RERANKER_MODEL"] = "sentence-transformers/all-MiniLM-L6-v2"
    with pytest.raises(RuntimeError) as exc:
        assert_full_capability_slate_applied()
    assert "PG_CONTENT_RELEVANCE_RERANKER_MODEL" in str(exc.value)


def test_prespend_assertion_kill_switch_default_on_and_disable_off():
    """The assertion is gated by the env kill-switch PG_WINNER_SLATE_PRESPEND_ASSERT, DEFAULT-ON (LAW VI).
    With it explicitly "0", even a dark winner does NOT raise (a deliberate operator experiment)."""
    apply_full_capability_benchmark_slate()
    os.environ.pop("PG_QGEN_FS_RESEARCHER", None)  # dark winner
    os.environ["PG_WINNER_SLATE_PRESPEND_ASSERT"] = "0"
    assert_full_capability_slate_applied()  # disabled => no raise


def test_every_force_flag_is_a_slate_key_so_the_assertion_governs_it():
    """Sanity invariant the assertion relies on: every force-on / force-exact flag is a key in the slate
    dict (so apply_full_capability_benchmark_slate genuinely force-sets it and the pre-spend assertion has
    a defined expected value for it). If this ever drifts, a winner could be force-listed but never set."""
    missing = sorted(
        (_BENCHMARK_FORCE_ON_FLAGS | _BENCHMARK_FORCE_EXACT_FLAGS)
        - set(_FULL_CAPABILITY_BENCHMARK_SLATE)
    )
    assert not missing, f"force-on/force-exact flags absent from the slate dict (never force-set): {missing}"
