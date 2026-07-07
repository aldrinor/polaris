"""I-deepfix-001 (#1369) drb_72 FIX WAVE — slate + anti-dark canary registration for the 6 fix flags.

The 6 fixwave flags are committed at 3fb659b7. This test proves the run_gate_b.py registration is correct
AND conservative:

  * SLATE: the 4 BOOLEAN default-ON fix kill-switches are force-ON (slate "1" + _BENCHMARK_FORCE_ON_FLAGS +
    _BENCHMARK_PREFLIGHT_REQUIRED_FLAGS + _WINNER_FLAG_ALLOWLIST). The 2 sub-1 FLOAT values are force-EXACT
    (PG_MIN_FETCH_YIELD=0.30, PG_CWF_PROMOTION_MIN_TOPICAL_OVERLAP=0.0) so the int-FLOOR slate path can NEVER
    truncate them to 0 (the PG_AMPLIFIER_SCOPE_FLOOR precedent).
  * CANARY: NONE of the 6 is a HARD _ActivationMarkerSpec — every marker fires on a CONDITIONAL seam
    (table-request / M5 partition / quantified stage / gap slot / junk withhold / fetch-runs), so a hard
    spec would false-CRASH a legitimate released report that skips the seam. They are LOG-READ-PROVEN.
  * ABSENCE-SAFETY: with the 6 flags ON but all EXISTING spec flags OFF, a resume-style log MISSING the
    fetch_yield_gate + search + the other 5 markers must NOT raise (the canary demands nothing for them).

EVERYTHING IS OFFLINE: no model / GPU / network / spend. Pure string + config logic.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
os.environ.setdefault("PG_VERIFICATION_MODE", "off")

import scripts.dr_benchmark.run_gate_b as rg  # noqa: E402

_CANARY = "PG_ACTIVATION_CANARY"
_PREFIX = "2026-07-07 12:00:00,123 INFO src.polaris_graph - "

# The 4 BOOLEAN default-ON fix kill-switches (force-ON quad-set). PG_CONTRACT_FALSE_GAP_KSPAN (fix4) is
# already quad-pinned from the INTEGRATION wave and is asserted separately below.
_FIXWAVE_BOOLEANS = (
    "PG_SUMMARY_TABLE_SOURCE_CONSOLIDATE",
    "PG_CWF_PROMOTION_TOPICAL_GATE",
    "PG_QUANTIFIED_PRUNE_UNREFERENCED_SOURCED",
    "PG_UNCOVERED_FACT_SUBJECT_GATE",
)
# The 2 sub-1 FLOAT force-EXACT values (flag -> expected exact slate value).
_FIXWAVE_FLOATS = {
    "PG_MIN_FETCH_YIELD": "0.30",
    "PG_CWF_PROMOTION_MIN_TOPICAL_OVERLAP": "0.0",
}
# All 6 fixwave flags (+ the already-registered fix4) whose markers must NEVER be a hard canary spec.
_FIXWAVE_ALL = _FIXWAVE_BOOLEANS + tuple(_FIXWAVE_FLOATS) + ("PG_CONTRACT_FALSE_GAP_KSPAN",)

# The realized-effect marker literal each flag emits (LOG-READ-PROVEN, not canary-demanded).
_FIXWAVE_MARKERS = {
    "PG_SUMMARY_TABLE_SOURCE_CONSOLIDATE": "[activation] summary_table_source_consolidate: clusters=1 rows_in=4 rows_out=3",
    "PG_CWF_PROMOTION_TOPICAL_GATE": "[activation] promotion_topical_gate: demoted=2 promoted=9",
    "PG_QUANTIFIED_PRUNE_UNREFERENCED_SOURCED": "[activation] quantified_prune_unreferenced_sourced: pruned=1",
    "PG_CONTRACT_FALSE_GAP_KSPAN": "[activation] contract_false_gap_kspan: slot=outlook kept=3 rendered=True",
    "PG_UNCOVERED_FACT_SUBJECT_GATE": "[activation] uncovered_fact_subject_gate: withheld=1",
    "PG_MIN_FETCH_YIELD": "[activation] fetch_yield_gate: rate=0.512 floor=0.30 -> pass",
}

# Every registered spec flag (main + WAVE3) — delenv'd to isolate the canary from the full slate.
_ALL_SPEC_FLAGS = tuple(
    s.env_flag for s in (*rg._ACTIVATION_MARKER_SPECS, *rg._ACTIVATION_MARKER_SPECS_WAVE3)
)


@pytest.fixture(autouse=True)
def _isolate_env():
    """Snapshot os.environ before each test and restore it after, so apply_full_capability_benchmark_slate
    (which mutates os.environ DIRECTLY, not via monkeypatch) never leaks the full slate into a sibling test
    file. Mirrors tests/dr_benchmark/test_purity_preflight_gates.py::_isolate_env."""
    snap = dict(os.environ)
    try:
        yield
    finally:
        os.environ.clear()
        os.environ.update(snap)


# ── SLATE registration ────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("flag", _FIXWAVE_BOOLEANS)
def test_boolean_flag_is_quad_pinned(flag):
    """Each BOOLEAN fix flag is force-ON in all four sets: slate "1" + force-on + preflight-required +
    winner-allowlist. A flag pinned in one set but missing from a sibling trips the SLATE-PURITY gate."""
    assert rg._FULL_CAPABILITY_BENCHMARK_SLATE.get(flag) == "1", f"{flag} not slate '1'"
    assert flag in rg._BENCHMARK_FORCE_ON_FLAGS, f"{flag} not in _BENCHMARK_FORCE_ON_FLAGS"
    assert flag in rg._BENCHMARK_PREFLIGHT_REQUIRED_FLAGS, f"{flag} not preflight-required"
    assert flag in rg._WINNER_FLAG_ALLOWLIST, f"{flag} not in _WINNER_FLAG_ALLOWLIST (SLATE-PURITY)"


@pytest.mark.parametrize("flag,value", list(_FIXWAVE_FLOATS.items()))
def test_float_flag_is_force_exact_not_floor_truncated(flag, value):
    """Each sub-1 FLOAT value is force-EXACT (in the slate dict AND _BENCHMARK_FORCE_EXACT_FLAGS), so the
    int-FLOOR slate path can never coerce 0.30 -> 0 / 0.0 -> 0. Force-EXACT floats are float-parseable =>
    SLATE-PURITY skips them, so they are correctly NOT force-on / required / allowlisted."""
    assert rg._FULL_CAPABILITY_BENCHMARK_SLATE.get(flag) == value, f"{flag} slate value != {value}"
    assert flag in rg._BENCHMARK_FORCE_EXACT_FLAGS, f"{flag} not force-EXACT (would int-truncate)"
    assert flag not in rg._BENCHMARK_FORCE_ON_FLAGS, f"{flag} is a value, not a boolean force-on"
    assert flag not in rg._WINNER_FLAG_ALLOWLIST, f"{flag} float should be purity-skipped, not allowlisted"


def test_apply_slate_does_not_truncate_the_float_values(monkeypatch):
    """The decisive regression guard for the int-FLOOR gotcha: after apply_full_capability_benchmark_slate,
    the two sub-1 floats hold their EXACT value (0.30 / 0.0), never a floor-truncated '0'."""
    # Clear any inherited value so the slate is the only source.
    for flag in _FIXWAVE_FLOATS:
        monkeypatch.delenv(flag, raising=False)
    rg.apply_full_capability_benchmark_slate()
    assert os.environ["PG_MIN_FETCH_YIELD"] == "0.30", "PG_MIN_FETCH_YIELD floor-truncated to 0 (fix DISABLED)"
    assert os.environ["PG_CWF_PROMOTION_MIN_TOPICAL_OVERLAP"] == "0.0", "topical threshold floor-truncated"
    # The 4 booleans are forced ON by the same apply.
    for flag in _FIXWAVE_BOOLEANS:
        assert os.environ[flag] == "1", f"{flag} not force-ON by apply_full_capability_benchmark_slate"


def test_fix4_already_registered_from_integration_wave():
    """PG_CONTRACT_FALSE_GAP_KSPAN (fix4) was quad-pinned by the INTEGRATION wave; assert it is still fully
    registered so this wave's edits did not disturb it."""
    assert rg._FULL_CAPABILITY_BENCHMARK_SLATE.get("PG_CONTRACT_FALSE_GAP_KSPAN") == "1"
    assert "PG_CONTRACT_FALSE_GAP_KSPAN" in rg._BENCHMARK_FORCE_ON_FLAGS
    assert "PG_CONTRACT_FALSE_GAP_KSPAN" in rg._BENCHMARK_PREFLIGHT_REQUIRED_FLAGS
    assert "PG_CONTRACT_FALSE_GAP_KSPAN" in rg._WINNER_FLAG_ALLOWLIST


# ── CANARY: none of the 6 is HARD-registered (conditional-seam => log-read-proven) ─────────────────

@pytest.mark.parametrize("flag", _FIXWAVE_ALL)
def test_flag_is_not_a_hard_canary_spec(flag):
    """CONSERVATIVE: none of the 6 fixwave flags is registered as an _ActivationMarkerSpec env_flag — each
    marker fires on a conditional seam, so a hard spec would false-CRASH a legitimate released report that
    skips the seam. They are LOG-READ-PROVEN instead."""
    registered = {s.env_flag for s in (*rg._ACTIVATION_MARKER_SPECS, *rg._ACTIVATION_MARKER_SPECS_WAVE3)}
    assert flag not in registered, (
        f"{flag} was HARD-registered as a canary spec — but its marker is CONDITIONAL, so a hard spec "
        f"false-CRASHES a released report that skips the seam. Move it to log-read-proven."
    )


# ── ABSENCE-SAFETY: flags ON + conditional markers ABSENT => canary does NOT raise ─────────────────

def _isolate_all_specs_off(monkeypatch):
    """Enable the canary and turn EVERY registered spec OFF so the canary demands nothing — then the ONLY
    thing that could make it raise is a (wrongly) hard-registered fixwave flag."""
    monkeypatch.setenv(_CANARY, "1")
    for f in _ALL_SPEC_FLAGS:
        monkeypatch.delenv(f, raising=False)
    # default-ON blocklist siblings: an unset value reads ON at the canary, so force them explicit OFF.
    monkeypatch.setenv("PG_RENDER_SUMMARY_TABLE", "0")
    monkeypatch.setenv("PG_DEBATE_CON_BASKET_CONSOLIDATION", "0")


def test_resume_log_missing_fetch_and_search_markers_does_not_raise(monkeypatch):
    """The task's canonical case: a --resume run skips search/fetch, so the fetch_yield_gate marker (and the
    other 5 conditional markers) are ABSENT even though the flags are ON. With the fixwave flags ON and all
    real specs OFF, assert_activation_markers_fired must NOT raise for the unregistered fixwave flags."""
    _isolate_all_specs_off(monkeypatch)
    # All 6 fixwave flags ON (booleans) / value-pinned (floats) — as the released slate leaves them.
    for flag in _FIXWAVE_BOOLEANS + ("PG_CONTRACT_FALSE_GAP_KSPAN",):
        monkeypatch.setenv(flag, "1")
    for flag, value in _FIXWAVE_FLOATS.items():
        monkeypatch.setenv(flag, value)
    # A resume-style log: composition re-ran, but NO fetch_yield_gate / NO search / NONE of the 6 markers.
    resume_log = (
        _PREFIX + "[resume] reloaded corpus_snapshot: 893 members\n"
        + _PREFIX + "[multi_section] composed 6 sections\n"
        + _PREFIX + "[activation] some_unrelated_marker: x=1\n"
    )
    rg.assert_activation_markers_fired(resume_log)  # must NOT raise


def test_all_six_markers_present_also_does_not_raise(monkeypatch):
    """Symmetric case: even when every fixwave marker IS present (a fresh box2 run), the canary neither
    demands nor rejects them (they are not registered specs) — so no raise either way."""
    _isolate_all_specs_off(monkeypatch)
    for flag in _FIXWAVE_BOOLEANS + ("PG_CONTRACT_FALSE_GAP_KSPAN",):
        monkeypatch.setenv(flag, "1")
    for flag, value in _FIXWAVE_FLOATS.items():
        monkeypatch.setenv(flag, value)
    fresh_log = "".join(_PREFIX + m + "\n" for m in _FIXWAVE_MARKERS.values())
    rg.assert_activation_markers_fired(fresh_log)  # must NOT raise


# ── producer/canary drift guard: the marker literals live in the producers (LOG-READ needles) ──────

def test_producer_marker_literals_exist_in_source():
    """Each LOG-READ-PROVEN marker's format string exists verbatim in its producer, so the run-day grep
    needles in the canary comment block are real (not phantom)."""
    def _src(rel):
        return (_REPO_ROOT / rel).read_text(encoding="utf-8")

    assert "[activation] summary_table_source_consolidate: clusters=%d rows_in=%d rows_out=%d" in _src(
        "src/polaris_graph/generator/summary_table.py"
    )
    assert "[activation] promotion_topical_gate: demoted=%d promoted=%d" in _src(
        "src/polaris_graph/generator/weighted_enrichment.py"
    )
    assert "[activation] quantified_prune_unreferenced_sourced: pruned=%d" in _src(
        "src/polaris_graph/synthesis/tradeoff_modeler.py"
    )
    assert "[activation] contract_false_gap_kspan: slot=%s kept=%d rendered=%s" in _src(
        "src/polaris_graph/generator/contract_section_runner.py"
    )
    assert '[activation] uncovered_fact_subject_gate: withheld=%d' in _src(
        "src/polaris_graph/generator/verified_compose.py"
    )
    lr = _src("src/polaris_graph/retrieval/live_retriever.py")
    assert "[activation] fetch_yield_gate: rate=%.3f floor=%.2f -> HALT" in lr
    assert "[activation] fetch_yield_gate: rate=%.3f floor=%.2f -> pass" in lr
