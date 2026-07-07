"""I-deepfix-001 (#1369) FIX 4 — the 3 FIX-A CWF chrome SUB-gates: default-ON
parse semantics + run_gate_b quad-registration.

Two defects fixed:
  (a) The ``enabled()`` helpers parsed truthy-ONLY, so an EMPTY-STRING env value
      DISABLED the gate (the opposite of the intended default-ON). They now use
      the shared default-ON pattern (enabled unless the value is an explicit OFF
      token), so UNSET and EMPTY-STRING both read ON.
  (b) The 3 gates lived ONLY in weighted_enrichment.py — not registered in
      run_gate_b.py — so a stray operator/.env =0 could silently ship chrome.
      They are now quad-pinned (slate "1" + force-ON + preflight-required +
      winner-allowlist) like the other boolean fix flags, and their conditional
      [activation] markers are log-read-proven (NOT hard canary specs).

Fully OFFLINE (pure string + config logic) per §8.4 — no model / GPU / network.
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

import src.polaris_graph.generator.weighted_enrichment as we  # noqa: E402
import scripts.dr_benchmark.run_gate_b as rg  # noqa: E402

# env flag -> its enabled() helper
_SUBGATES = {
    "PG_CWF_ISSN_CHROME": we.issn_chrome_gate_enabled,
    "PG_CWF_CHART_ALT_CHROME": we.chart_alt_chrome_gate_enabled,
    "PG_CWF_EMPTY_BULLET_DROP": we.empty_bullet_drop_enabled,
}


@pytest.fixture(autouse=True)
def _isolate_env():
    """Snapshot os.environ before each test and restore after, so
    apply_full_capability_benchmark_slate (which mutates os.environ DIRECTLY)
    never leaks the full slate into a sibling test."""
    snap = dict(os.environ)
    try:
        yield
    finally:
        os.environ.clear()
        os.environ.update(snap)


# ── (a) parse semantics: UNSET and EMPTY-STRING are ON; only explicit OFF disables ──
@pytest.mark.parametrize("flag,fn", list(_SUBGATES.items()))
def test_unset_reads_on(flag, fn, monkeypatch):
    monkeypatch.delenv(flag, raising=False)
    assert fn() is True


@pytest.mark.parametrize("flag,fn", list(_SUBGATES.items()))
def test_empty_string_reads_on(flag, fn, monkeypatch):
    """The exact bug: an empty-string value must NOT disable a default-ON gate."""
    monkeypatch.setenv(flag, "")
    assert fn() is True
    monkeypatch.setenv(flag, "   ")  # whitespace-only is also ON
    assert fn() is True


@pytest.mark.parametrize("flag,fn", list(_SUBGATES.items()))
@pytest.mark.parametrize("off_value", ["0", "false", "no", "off", "  Off  "])
def test_explicit_off_disables(flag, fn, off_value, monkeypatch):
    monkeypatch.setenv(flag, off_value)
    assert fn() is False


@pytest.mark.parametrize("flag,fn", list(_SUBGATES.items()))
@pytest.mark.parametrize("on_value", ["1", "true", "on", "yes"])
def test_explicit_on_enables(flag, fn, on_value, monkeypatch):
    monkeypatch.setenv(flag, on_value)
    assert fn() is True


# ── (b) run_gate_b quad-registration ──────────────────────────────────────────────
@pytest.mark.parametrize("flag", list(_SUBGATES))
def test_subgate_is_quad_pinned(flag):
    """Each FIX-A sub-gate is force-ON in all four sets so a stray =0 cannot
    silently disable chrome suppression on the paid run."""
    assert rg._FULL_CAPABILITY_BENCHMARK_SLATE.get(flag) == "1", f"{flag} not slate '1'"
    assert flag in rg._BENCHMARK_FORCE_ON_FLAGS, f"{flag} not in _BENCHMARK_FORCE_ON_FLAGS"
    assert flag in rg._BENCHMARK_PREFLIGHT_REQUIRED_FLAGS, f"{flag} not preflight-required"
    assert flag in rg._WINNER_FLAG_ALLOWLIST, f"{flag} not in _WINNER_FLAG_ALLOWLIST (SLATE-PURITY)"


@pytest.mark.parametrize("flag", list(_SUBGATES))
def test_subgate_is_not_a_hard_canary_spec(flag):
    """Each sub-gate marker fires on a CONDITIONAL seam (a matching chrome line),
    so a hard _ActivationMarkerSpec would false-CRASH a clean report that has no
    chrome. They are LOG-READ-PROVEN instead."""
    registered = {
        s.env_flag
        for s in (*rg._ACTIVATION_MARKER_SPECS, *rg._ACTIVATION_MARKER_SPECS_WAVE3)
    }
    assert flag not in registered, f"{flag} wrongly HARD-registered as a canary spec"


def test_slate_apply_forces_subgates_on(monkeypatch):
    """apply_full_capability_benchmark_slate force-sets each sub-gate ON even
    when the inherited value is an explicit OFF token."""
    for flag in _SUBGATES:
        monkeypatch.setenv(flag, "0")
    rg.apply_full_capability_benchmark_slate()
    for flag in _SUBGATES:
        assert os.environ[flag] == "1", f"{flag} not force-ON by the slate"


def test_producer_markers_exist_in_source():
    """The run-day grep needles in the canary comment table are real (not phantom)."""
    src = (_REPO_ROOT / "src/polaris_graph/generator/weighted_enrichment.py").read_text(
        encoding="utf-8"
    )
    assert "[activation] issn_masthead_chrome: fired=1" in src
    assert "[activation] chart_alt_chrome: fired=1" in src
    assert "[activation] empty_bullet_drop: dropped=%d" in src
