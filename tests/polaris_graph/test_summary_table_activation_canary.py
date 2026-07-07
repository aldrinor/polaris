"""SUMMARY-TABLE activation canary wiring (I-deepfix-001 Wave-5 RENDER #1344, ANTI-DARK Rule #2).

The deterministic verified-only summary-table renderer is already built + wired + quad-pinned
(``PG_RENDER_SUMMARY_TABLE``) and the render seam in ``run_honest_sweep_r3`` already emits a
realized-effect ``[activation] summary_table:`` marker. These tests prove the FAIL-LOUD half: a
matching ``_ActivationMarkerSpec`` is registered in the run_gate_b activation canary so a DARK
table (render seam removed / import broken / never reached) CRASHES the run instead of silently
shipping.

Contract (mirrors FF3-TRUNC-SEM, one deliberate difference):
  * flag ON + positive marker PRESENT with a parseable ``reached`` => PASS. rows>=0 is fine — an
    HONEST empty table (``reached=True rows=0 cols=0``) passes. There is NO count threshold and
    (unlike FF3) NO ``reached=True`` bool_check: the summary-table seam emits ``reached=True``
    unconditionally when it runs, so its DARK signal is MARKER-ABSENT, not ``reached=False``
    (§-1.3: never gate the report on a count).
  * flag ON + positive marker ABSENT (dark render) => canary RAISES (overall_rc=1).
  * ``unavailable_failopen`` present (render seam faulted) => canary REJECTS.

Pure / offline. The frozen faithfulness engine is untouched (the canary reads run telemetry only).
"""
from __future__ import annotations

import pytest

import scripts.dr_benchmark.run_gate_b as rg


_NAME = "summary_table"
_FLAG = "PG_RENDER_SUMMARY_TABLE"
_POSITIVE_ROWS3 = "[activation] summary_table: reached=True rows=3 cols=5"
_POSITIVE_EMPTY = "[activation] summary_table: reached=True rows=0 cols=0"
_FAILOPEN = "[activation] summary_table: unavailable_failopen"


def _spec():
    by_name = {s.name: s for s in rg._ACTIVATION_MARKER_SPECS_WAVE3}
    assert _NAME in by_name, f"{_NAME} spec missing from _ACTIVATION_MARKER_SPECS_WAVE3"
    return by_name[_NAME]


# ── (a) spec registered with the right flag + a liveness/count-shaped positive regex ──────────
def test_summary_table_spec_registered_in_wave3_registry():
    spec = _spec()
    assert spec.env_flag == _FLAG
    # positive_re matches a realized fire...
    assert spec.positive_re.search(_POSITIVE_ROWS3)
    # ...but NEVER an empty string (a dark render leaves no marker at all).
    assert not spec.positive_re.search("")


# ── (b) the fail-open degrade string is the registered absent-marker tripwire ─────────────────
def test_summary_table_failopen_is_absent_marker():
    spec = _spec()
    assert spec.absent_markers == (_FAILOPEN,)


# ── (c) an HONEST empty table (rows=0 cols=0) still matches the positive regex ────────────────
def test_summary_table_positive_re_accepts_reached_true_zero_rows():
    """§-1.3 no-threshold: an honest empty table (no titled table requested / no verified rows /
    already present) emits ``reached=True rows=0 cols=0`` — it MUST match the positive regex so the
    canary accepts it (a legitimate no-render is not a dark render)."""
    spec = _spec()
    assert spec.positive_re.search(_POSITIVE_EMPTY)


def test_summary_table_no_count_threshold_and_blocklist_predicate():
    """The deliberate FF3 divergence, locked: NO bool_check (a parseable ``reached`` passes, no
    ``reached=True`` demand) and NO exact_fields (no rows>0 count gate). ``flag_whitelist=None``
    (the blocklist default) reproduces the producer ``summary_table_enabled()`` predicate exactly."""
    spec = _spec()
    assert spec.bool_checks == ()
    assert spec.exact_fields == ()
    assert spec.flag_whitelist is None
    # Wave-6b P1 fix: the producer defaults ON, so the canary must too (unset => demand the marker).
    assert spec.flag_default_on is True


# ── canary end-to-end: present => pass, absent => raise, failopen => raise ─────────────────────
def _run_canary(monkeypatch, *marker_lines):
    """Drive ``rg.assert_activation_markers_fired`` over a run-log carrying ``marker_lines`` with the
    canary opt-in + ``PG_RENDER_SUMMARY_TABLE`` ON and EVERY OTHER activation flag (all main +
    wave3/4/5 siblings) OFF, so ONLY the summary_table spec is asserted."""
    monkeypatch.setenv("PG_ACTIVATION_CANARY", "1")
    monkeypatch.setenv(_FLAG, "1")
    for spec in (*rg._ACTIVATION_MARKER_SPECS, *rg._ACTIVATION_MARKER_SPECS_WAVE3):
        if spec.env_flag != _FLAG:
            monkeypatch.delenv(spec.env_flag, raising=False)
    log_text = "".join(
        "2026-07-06 12:00:00,000 INFO src.polaris_graph - " + m + "\n" for m in marker_lines
    )
    rg.assert_activation_markers_fired(log_text)


def test_canary_accepts_marker_present_realized(monkeypatch):
    """flag ON + positive marker PRESENT => the canary does NOT raise."""
    _run_canary(monkeypatch, _POSITIVE_ROWS3)


def test_canary_accepts_honest_empty_table(monkeypatch):
    """flag ON + honest empty table (reached=True rows=0 cols=0) => no raise (§-1.3 no threshold)."""
    _run_canary(monkeypatch, _POSITIVE_EMPTY)


def test_canary_accepts_parseable_reached_false(monkeypatch):
    """The literal contract: any parseable ``reached`` passes (no bool_check). The seam never emits
    ``reached=False`` — the summary-table DARK case is MARKER-ABSENT (below), not reached=False."""
    _run_canary(monkeypatch, "[activation] summary_table: reached=False rows=0 cols=0")


def test_canary_rejects_dark_absent_marker(monkeypatch):
    """flag ON but NO positive summary_table marker => a DARK render (seam removed / import broken /
    never reached) => the canary RAISES (MARKER ABSENT)."""
    with pytest.raises(RuntimeError):
        _run_canary(monkeypatch, "[activation] some_other_module: fired")


def test_canary_rejects_failopen(monkeypatch):
    """The distinct ``unavailable_failopen`` degrade (the render seam faulted) must FAIL the canary
    even though the positive marker co-occurs (the OLD/DEGRADE-MARKER-PRESENT leg)."""
    with pytest.raises(RuntimeError):
        _run_canary(monkeypatch, _POSITIVE_ROWS3, _FAILOPEN)


# ── Wave-6b P1: flag UNSET is treated as ON (producer default-ON parity) ───────────────────────
def _run_canary_flag_unset(monkeypatch, *marker_lines):
    """Like ``_run_canary`` but leaves PG_RENDER_SUMMARY_TABLE UNSET (the producer renders the table
    by default, so the canary must too via flag_default_on) with every OTHER activation flag OFF."""
    monkeypatch.setenv("PG_ACTIVATION_CANARY", "1")
    for spec in (*rg._ACTIVATION_MARKER_SPECS, *rg._ACTIVATION_MARKER_SPECS_WAVE3):
        monkeypatch.delenv(spec.env_flag, raising=False)  # incl. _FLAG => unset default-ON path
    log_text = "".join(
        "2026-07-06 12:00:00,000 INFO src.polaris_graph - " + m + "\n" for m in marker_lines
    )
    rg.assert_activation_markers_fired(log_text)


def test_canary_unset_flag_still_demands_marker_dark_caught(monkeypatch):
    """Wave-6b P1: with PG_RENDER_SUMMARY_TABLE UNSET the producer STILL renders (default ON), so a
    DARK render (marker absent) MUST raise — flag_default_on closes the escape the blocklist default left."""
    with pytest.raises(RuntimeError):
        _run_canary_flag_unset(monkeypatch, "[activation] some_other_module: fired")


def test_canary_unset_flag_accepts_marker_present(monkeypatch):
    """Wave-6b P1: unset flag + positive marker present => no raise (the table rendered honestly)."""
    _run_canary_flag_unset(monkeypatch, _POSITIVE_ROWS3)


def test_canary_explicit_off_flag_demands_nothing(monkeypatch):
    """Parity guard: an EXPLICIT PG_RENDER_SUMMARY_TABLE=0 (producer OFF => no table => no marker) must
    self-scope OFF and NOT raise even with no marker — flag_default_on flips ONLY the unset default."""
    monkeypatch.setenv("PG_ACTIVATION_CANARY", "1")
    for spec in (*rg._ACTIVATION_MARKER_SPECS, *rg._ACTIVATION_MARKER_SPECS_WAVE3):
        monkeypatch.delenv(spec.env_flag, raising=False)
    monkeypatch.setenv(_FLAG, "0")
    rg.assert_activation_markers_fired("2026-07-06 12:00:00,000 INFO src - nothing here\n")
