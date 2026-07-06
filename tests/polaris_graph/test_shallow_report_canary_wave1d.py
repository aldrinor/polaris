"""I-deepfix-001 (#1344) Wave-1d — fail-loud SHALLOW-REPORT canaries (offline, no model / GPU / spend).

Two DETECTORS in ``scripts/dr_benchmark/run_gate_b.py`` guard against the "false-fired pipeline"
(winner slate ON, writer-path logs busy, yet the rendered report is still shallow/degraded):

  * ``assert_depth_synthesis_fired`` — the depth cross-source pass DRAFTED >=1 eligible
    high-corroboration basket yet kept ZERO synthesized findings (eligible-yet-zero).
  * ``assert_multi_origin_baskets_exist`` — finding_dedup grouped >=1 cluster with >=2 distinct
    origins yet ZERO baskets reached composition with verified_support_origin_count>=2 (the
    keystone silently not producing multi-origin baskets).

Both are STRUCTURAL detectors (an eligible-yet-zero contradiction), NEVER a word / citation / source
COUNT threshold (§-1.3). Both self-skip unless the opt-in ``PG_SHALLOW_REPORT_CANARY`` flag is on
(default OFF => byte-identical, canary never runs). The telemetry is stubbed as log strings — no
pipeline run, no model, no network. The frozen faithfulness engine is untouched (canaries only READ).
"""

from __future__ import annotations

from pathlib import Path

import pytest

import scripts.dr_benchmark.run_gate_b as rg

_FLAG = "PG_SHALLOW_REPORT_CANARY"
_REPO_ROOT = Path(__file__).resolve().parents[2]
_LAUNCHER = _REPO_ROOT / "scripts" / "run_honest_sweep_r3.py"
_GATE_B = _REPO_ROOT / "scripts" / "dr_benchmark" / "run_gate_b.py"

# ── stub telemetry lines (exactly the runtime shape of the real producers) ───────────────────────
_DEPTH_LINE = "[depth-synthesis] D8-thread: baskets_total={bt} drafted={d} kept_findings={k} (cross={c} single={s})"
_SHALLOW_LINE = "[shallow-canary] finding_dedup_multiorigin_clusters={x} multi_origin_baskets={y}"


def _depth(drafted: int, kept: int, *, baskets_total: int = 9, cross: int = 0) -> str:
    return _DEPTH_LINE.format(bt=baskets_total, d=drafted, k=kept, c=cross, s=max(0, kept - cross))


def _shallow(clusters: int, baskets: int) -> str:
    return _SHALLOW_LINE.format(x=clusters, y=baskets)


def _noise() -> str:
    return "some unrelated log line\n[retrieval] fetched 12 rows\n[multi_section] verified-compose PRIMARY: 4 baskets"


# ── OFF => byte-identical: the canary NEVER runs (no raise even on a would-fire log) ──────────────

def test_off_asserts_are_noop_on_would_fire_logs(monkeypatch):
    monkeypatch.delenv(_FLAG, raising=False)  # default OFF
    assert not rg._shallow_report_canary_enabled()
    # both logs WOULD fire if the flag were on — with it off, both asserts return None (no raise).
    rg.assert_depth_synthesis_fired(_depth(drafted=3, kept=0))
    rg.assert_multi_origin_baskets_exist(_shallow(clusters=4, baskets=0))


def test_off_wrapper_returns_skip_disabled(monkeypatch):
    monkeypatch.delenv(_FLAG, raising=False)
    out = rg._run_shallow_report_canary(
        _depth(drafted=3, kept=0) + "\n" + _shallow(clusters=4, baskets=0),
        "success", smoke_scale=False, domain="d", slug="s",
    )
    assert out == "skip:disabled"


def test_off_explicit_zero_is_off(monkeypatch):
    monkeypatch.setenv(_FLAG, "0")
    assert not rg._shallow_report_canary_enabled()
    rg.assert_depth_synthesis_fired(_depth(drafted=3, kept=0))  # no raise


# ── canary 1: depth-synthesis eligible-yet-zero ──────────────────────────────────────────────────

def test_canary1_fires_on_eligible_yet_zero(monkeypatch):
    monkeypatch.setenv(_FLAG, "1")
    with pytest.raises(RuntimeError, match="DEPTH-SYNTHESIS DARK"):
        rg.assert_depth_synthesis_fired(_depth(drafted=3, kept=0))


def test_canary1_silent_when_it_fired(monkeypatch):
    monkeypatch.setenv(_FLAG, "1")
    rg.assert_depth_synthesis_fired(_depth(drafted=3, kept=2))  # kept>=1 => fired, no raise


def test_canary1_silent_when_no_eligible_baskets(monkeypatch):
    monkeypatch.setenv(_FLAG, "1")
    # drafted==0 (no eligible high-corroboration baskets) — conditional absence, never FORCED (§-1.3).
    rg.assert_depth_synthesis_fired(_depth(drafted=0, kept=0, baskets_total=40))


def test_canary1_silent_when_no_depth_line(monkeypatch):
    monkeypatch.setenv(_FLAG, "1")
    rg.assert_depth_synthesis_fired(_noise())  # no D8-thread line => no data => no raise


def test_canary1_large_counts_alone_do_not_fire(monkeypatch):
    monkeypatch.setenv(_FLAG, "1")
    # huge magnitudes, but kept>=1 => genuinely fired. Magnitude alone decides nothing (structural).
    rg.assert_depth_synthesis_fired(_depth(drafted=100, kept=50))


# ── canary 2: finding_dedup multi-origin clusters yet zero multi-origin baskets ───────────────────

def test_canary2_fires_on_multiorigin_clusters_yet_zero_baskets(monkeypatch):
    monkeypatch.setenv(_FLAG, "1")
    with pytest.raises(RuntimeError, match="MULTI-ORIGIN BASKETS DARK"):
        rg.assert_multi_origin_baskets_exist(_shallow(clusters=4, baskets=0))


def test_canary2_silent_when_baskets_exist(monkeypatch):
    monkeypatch.setenv(_FLAG, "1")
    rg.assert_multi_origin_baskets_exist(_shallow(clusters=4, baskets=3))  # baskets>=1 => no raise


def test_canary2_silent_when_no_multiorigin_clusters(monkeypatch):
    monkeypatch.setenv(_FLAG, "1")
    # 0 multi-origin clusters (single-source / non-overlapping corpus) — never FORCED (§-1.3).
    rg.assert_multi_origin_baskets_exist(_shallow(clusters=0, baskets=0))


def test_canary2_silent_when_no_telemetry_line(monkeypatch):
    monkeypatch.setenv(_FLAG, "1")
    rg.assert_multi_origin_baskets_exist(_noise())  # no [shallow-canary] line => no data => no raise


def test_canary2_large_clusters_with_baskets_do_not_fire(monkeypatch):
    monkeypatch.setenv(_FLAG, "1")
    rg.assert_multi_origin_baskets_exist(_shallow(clusters=999, baskets=1))  # baskets>=1 => no raise


# ── STRUCTURAL-NOT-QUANTITY: only the eligible-yet-zero contradiction decides, never a magnitude ──

@pytest.mark.parametrize("drafted,kept,should_fire", [
    (0, 0, False),    # no eligible: conditional absence
    (1, 0, True),     # minimal eligible, zero kept: FIRE
    (3, 0, True),
    (100, 0, True),   # large eligible, still zero kept: FIRE (magnitude irrelevant)
    (3, 1, False),    # one kept: fired
    (100, 50, False), # large kept: fired
    (0, 5, False),    # kept without drafted (never happens, but: not eligible-yet-zero)
])
def test_canary1_decision_is_purely_structural(monkeypatch, drafted, kept, should_fire):
    monkeypatch.setenv(_FLAG, "1")
    log = _depth(drafted=drafted, kept=kept)
    if should_fire:
        with pytest.raises(RuntimeError):
            rg.assert_depth_synthesis_fired(log)
    else:
        rg.assert_depth_synthesis_fired(log)  # no raise


@pytest.mark.parametrize("clusters,baskets,should_fire", [
    (0, 0, False),    # no multi-origin clusters: conditional absence
    (1, 0, True),     # minimal cluster, zero baskets: FIRE
    (4, 0, True),
    (999, 0, True),   # large clusters, still zero baskets: FIRE (magnitude irrelevant)
    (4, 1, False),    # one basket: keystone fired
    (999, 500, False),
    (0, 5, False),    # baskets without clusters: not clusters-yet-zero
])
def test_canary2_decision_is_purely_structural(monkeypatch, clusters, baskets, should_fire):
    monkeypatch.setenv(_FLAG, "1")
    log = _shallow(clusters=clusters, baskets=baskets)
    if should_fire:
        with pytest.raises(RuntimeError):
            rg.assert_multi_origin_baskets_exist(log)
    else:
        rg.assert_multi_origin_baskets_exist(log)  # no raise


# ── the post-run wrapper (mirrors _run_m6_firing_canary) ─────────────────────────────────────────

def test_wrapper_fails_on_firing_log(monkeypatch):
    monkeypatch.setenv(_FLAG, "1")
    log = _depth(drafted=3, kept=0) + "\n" + _shallow(clusters=4, baskets=0)
    out = rg._run_shallow_report_canary(log, "success", smoke_scale=False, domain="d", slug="s")
    assert out == "FAILED"


def test_wrapper_fails_when_only_multiorigin_dark(monkeypatch):
    monkeypatch.setenv(_FLAG, "1")
    # depth healthy, but multi-origin keystone dark — the wrapper runs BOTH asserts, so it still FAILS.
    log = _depth(drafted=3, kept=2) + "\n" + _shallow(clusters=4, baskets=0)
    out = rg._run_shallow_report_canary(log, "success", smoke_scale=False, domain="d", slug="s")
    assert out == "FAILED"


def test_wrapper_ok_on_healthy_log(monkeypatch):
    monkeypatch.setenv(_FLAG, "1")
    log = _depth(drafted=3, kept=2) + "\n" + _shallow(clusters=4, baskets=3)
    out = rg._run_shallow_report_canary(log, "success", smoke_scale=False, domain="d", slug="s")
    assert out == "ok"


def test_wrapper_ok_on_released_with_disclosed_gaps(monkeypatch):
    monkeypatch.setenv(_FLAG, "1")
    log = _depth(drafted=0, kept=0) + "\n" + _shallow(clusters=0, baskets=0)  # conditional-absence run
    out = rg._run_shallow_report_canary(
        log, "released_with_disclosed_gaps", smoke_scale=False, domain="d", slug="s",
    )
    assert out == "ok"


def test_wrapper_skip_on_non_released_status(monkeypatch):
    monkeypatch.setenv(_FLAG, "1")
    log = _depth(drafted=3, kept=0) + "\n" + _shallow(clusters=4, baskets=0)  # would FAIL if released
    out = rg._run_shallow_report_canary(
        log, "abort_scope_rejected", smoke_scale=False, domain="d", slug="s",
    )
    assert out.startswith("skip:status=")


def test_wrapper_skip_on_smoke_scale(monkeypatch):
    monkeypatch.setenv(_FLAG, "1")
    log = _depth(drafted=3, kept=0) + "\n" + _shallow(clusters=4, baskets=0)
    out = rg._run_shallow_report_canary(log, "success", smoke_scale=True, domain="d", slug="s")
    assert out == "skip:smoke_scale"


def test_wrapper_released_status_universe_is_reused():
    # the wrapper reuses the breadth/M6 released-status set — success is released, an abort is not.
    assert "success" in rg._BREADTH_CANARY_RELEASED_STATUSES
    assert "released_with_disclosed_gaps" in rg._BREADTH_CANARY_RELEASED_STATUSES
    assert "abort_scope_rejected" not in rg._BREADTH_CANARY_RELEASED_STATUSES


# ── the canaries parse REAL producer lines (guards against producer/canary drift) ─────────────────

def test_producer_lines_exist_in_launcher_source():
    src = _LAUNCHER.read_text(encoding="utf-8")
    # canary 1 reads the EXISTING depth-synthesis D8-thread producer line.
    assert "[depth-synthesis] D8-thread:" in src
    assert "drafted=" in src
    assert "kept_findings=" in src
    # canary 2 reads the Wave-1d flag-gated telemetry producer line.
    assert "[shallow-canary] finding_dedup_multiorigin_clusters=" in src
    assert "multi_origin_baskets=" in src
    # the regexes actually match the runtime shape of those producer lines.
    assert rg._DEPTH_D8_THREAD_RE.search(_depth(drafted=3, kept=0)) is not None
    assert rg._SHALLOW_MULTIORIGIN_RE.search(_shallow(clusters=4, baskets=0)) is not None


def test_producer_emission_is_flag_gated_off_byte_identical():
    # the run_honest_sweep_r3 telemetry emission is gated by the canary flag => OFF writes NO line.
    src = _LAUNCHER.read_text(encoding="utf-8")
    idx = src.index("[shallow-canary] finding_dedup_multiorigin_clusters=")
    guard = 'if _env_flag("PG_SHALLOW_REPORT_CANARY", default=False):'
    gidx = src.rindex(guard, 0, idx)
    # the emission is within a few dozen lines of its flag guard (same gated block).
    assert 0 < (idx - gidx) < 2000, "the [shallow-canary] emission is not under the PG_SHALLOW_REPORT_CANARY guard"


# ── OFF-purity: the sweep record must NOT carry the new key when the flag is off (byte-identical) ─

def test_sweep_record_key_is_guarded_off_byte_identical():
    """FIX 1 (Codex+Fable P1): the base ``_record`` dict must NOT contain the Wave-1d
    ``shallow_report_canary`` key; it is added ONLY inside an ``if _shallow_canary is not None:`` guard,
    so a flag-OFF run's sweep_summary.json is byte-identical to the pre-Wave-1d baseline."""
    src = _GATE_B.read_text(encoding="utf-8")
    # the key is added via an explicit guarded assignment, not as a base-dict literal entry.
    assert 'if _shallow_canary is not None:' in src
    assert '_record["shallow_report_canary"] = _shallow_canary' in src
    # the base _record literal (from "_record = {" to the "if _shallow_canary is not None:" guard) has
    # NO shallow_report_canary key — that is the OFF-byte-identical property.
    start = src.index("_record = {")
    guard = src.index("if _shallow_canary is not None:", start)
    base_literal = src[start:guard]
    assert '"shallow_report_canary"' not in base_literal, "the OFF path would emit a null key"
    # the pre-existing m6 key is left as an unconditional base-dict entry (unchanged, not a Wave-1d key).
    assert '"m6_cross_source_canary": _m6_canary,' in base_literal


def test_no_data_path_records_skip_not_ok():
    """FIX 2 (Codex+Fable P2): when the run_log is missing/unreadable the code must NOT call the wrapper
    with "" (which returns "ok") — it records an explicit ``skip:no-run-log`` so the fail-loud detector
    never false-greens on no data."""
    src = _GATE_B.read_text(encoding="utf-8")
    assert '_shallow_canary = "skip:no-run-log"' in src
    # the no-data branch is keyed on the None sentinel (missing run_dir / missing file / read exception).
    assert 'if _sc_log_text is None:' in src


# ── smoke: the module + symbols import offline ───────────────────────────────────────────────────

def test_smoke_symbols_present():
    for name in (
        "_shallow_report_canary_enabled",
        "assert_depth_synthesis_fired",
        "assert_multi_origin_baskets_exist",
        "_run_shallow_report_canary",
        "_SHALLOW_REPORT_CANARY_ENV",
        "_DEPTH_D8_THREAD_RE",
        "_SHALLOW_MULTIORIGIN_RE",
    ):
        assert hasattr(rg, name), f"run_gate_b is missing {name}"
    assert rg._SHALLOW_REPORT_CANARY_ENV == _FLAG
