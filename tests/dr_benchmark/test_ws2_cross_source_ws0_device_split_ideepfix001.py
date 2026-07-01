"""I-deepfix-001 (#1344) WS-2 + WS-0 behavioral replay-harness (offline, no GPU, no spend).

WS-2 — the full winner slate on the PAID path now carries M6 (PG_CROSS_SOURCE_SYNTHESIS):
  * it is in the slate dict, the force-on set, the preflight-required tuple, and the winner allowlist;
  * a stray operator =0 is FORCE-overridden to "1" by the slate (a slate-OFF launch is impossible);
  * the operational-readiness D-1 preflight RED-gates a slate-OFF launch for all THREE winner flags
    (PG_CONSOLIDATION_NLI / PG_CROSS_SOURCE_SYNTHESIS / PG_BREADTH_ENRICHMENT_ENABLED);
  * the post-run fail-loud M6 firing assertion raises when the run logged eligible pairs but 0 units.

WS-0 — the device-split launch config + the co-residence preflight WARN fire correctly.

These are PURE / config tests: no model load, no network, no paid call.
"""

from __future__ import annotations

import inspect

import pytest

import scripts.dr_benchmark.run_gate_b as rg
import scripts.operational_readiness_preflight as op
import scripts.dr_benchmark.gpu_device_split as gds

_CROSS = "PG_CROSS_SOURCE_SYNTHESIS"
_THREE_WINNERS = ("PG_CONSOLIDATION_NLI", _CROSS, "PG_BREADTH_ENRICHMENT_ENABLED")


# ── WS-2 (1): the slate + the three required/force/allowlist sets carry M6 ───────────────────────

def test_ws2_cross_source_in_slate_required_forceon_allowlist():
    assert rg._FULL_CAPABILITY_BENCHMARK_SLATE.get(_CROSS) == "1", "M6 not slate-pinned '1'"
    assert _CROSS in rg._BENCHMARK_PREFLIGHT_REQUIRED_FLAGS, "M6 not fail-closed pre-spend"
    assert _CROSS in rg._BENCHMARK_FORCE_ON_FLAGS, "M6 not force-on (a stray =0 could survive)"
    assert _CROSS in rg._WINNER_FLAG_ALLOWLIST, "M6 not allowlisted (SLATE-PURITY would fail closed)"
    # the two sibling winner flags this WS pairs M6 with are ALSO fail-closed pre-spend.
    assert "PG_CONSOLIDATION_NLI" in rg._BENCHMARK_PREFLIGHT_REQUIRED_FLAGS
    assert "PG_BREADTH_ENRICHMENT_ENABLED" in rg._BENCHMARK_PREFLIGHT_REQUIRED_FLAGS
    # WS-8 guard: PG_DOCUMENT_TYPE_WEIGHT (M2) must NOT be in the global slate (journal-only template only).
    assert "PG_DOCUMENT_TYPE_WEIGHT" not in rg._FULL_CAPABILITY_BENCHMARK_SLATE, "M2 leaked into the global slate"


# ── WS-2 (2): a slate-OFF launch is impossible — force-on overrides a stray operator =0 ───────────

def test_ws2_stray_operator_zero_is_force_overridden_to_one():
    meta = op.load_slate_meta()  # the REAL Gate-B slate constants
    assert _CROSS in meta.slate and _CROSS in meta.force_on, "real slate does not govern M6"
    eff = op.resolve_effective_config({_CROSS: "0"}, meta)  # replica of apply_slate's FORCE semantics
    assert eff[_CROSS] == "1", f"a stray {_CROSS}=0 was NOT force-overridden to '1' (slate-OFF would launch)"


# ── WS-2 (3): the paid-path readiness preflight RED-gates a slate-OFF launch ──────────────────────

def _d1_reds(cfg: dict, meta) -> list[str]:
    results = op.check_d1_flags(cfg, cfg, meta, four_role_mode_wired=True)
    return [r.check_id for r in results if r.is_red]


def test_ws2_paid_preflight_reds_slate_off_launch():
    meta = op.load_slate_meta()
    # slate-OFF launch: the three winner flags resolve OFF in the effective config.
    cfg_off = {f: "0" for f in _THREE_WINNERS}
    reds = _d1_reds(cfg_off, meta)
    for flag in _THREE_WINNERS:
        assert f"D-1.{flag}" in reds, f"paid preflight did NOT RED-gate a slate-OFF {flag}: {reds}"
    # slate-ON launch (resolved through the REAL slate) — none of the three RED.
    cfg_on = op.resolve_effective_config({}, meta)
    reds_on = _d1_reds(cfg_on, meta)
    for flag in _THREE_WINNERS:
        assert f"D-1.{flag}" not in reds_on, f"slate-applied {flag} spuriously RED: {reds_on}"


# ── WS-2 (4): the post-run fail-loud M6 firing assertion ─────────────────────────────────────────

_PRODUCER_SILENT_NOOP = (
    "[cross_source_synthesis] 3 anchored cross-source pair(s) but 0 analytical units survived "
    "per-clause re-verify/licensing — analytical layer produced nothing for this section"
)
_PRODUCER_FIRED = (
    "[cross_source_synthesis] composed 2 cross-source analytical unit(s) from 3 anchored pair(s)"
)


def test_ws2_marker_stems_are_real_producer_substrings():
    """No phantom strings: both marker stems the post-run grep keys on MUST appear verbatim in the
    real producer source (cross_source_synthesis.compose_cross_source_analytical_units)."""
    src = inspect.getsource(
        __import__("src.polaris_graph.generator.cross_source_synthesis", fromlist=["x"])
    )
    assert rg._CROSS_SOURCE_FIRED_MARKER in src, "the FIRED marker stem is not in the producer source"
    assert rg._CROSS_SOURCE_SILENT_NOOP_MARKER in src, "the SILENT-NO-OP marker stem is not in the producer source"
    # and the stems must actually match the realistic producer lines below.
    assert rg._CROSS_SOURCE_FIRED_MARKER in _PRODUCER_FIRED
    assert rg._CROSS_SOURCE_SILENT_NOOP_MARKER in _PRODUCER_SILENT_NOOP


def test_ws2_m6_firing_assertion_raises_on_silent_noop(monkeypatch):
    monkeypatch.setenv(_CROSS, "1")  # slate ON
    log = "some earlier line\n" + _PRODUCER_SILENT_NOOP + "\nlater line"
    with pytest.raises(RuntimeError, match="WINNER-FIRES M6"):
        rg.assert_cross_source_synthesis_fired(log)


def test_ws2_m6_firing_assertion_silent_when_it_fired(monkeypatch):
    monkeypatch.setenv(_CROSS, "1")
    # a run that composed >=1 unit somewhere never raises, even if one section was barren.
    log = _PRODUCER_SILENT_NOOP + "\n" + _PRODUCER_FIRED
    rg.assert_cross_source_synthesis_fired(log)  # no raise


def test_ws2_m6_firing_assertion_silent_when_no_anchored_pairs(monkeypatch):
    monkeypatch.setenv(_CROSS, "1")
    rg.assert_cross_source_synthesis_fired("no cross_source lines at all\njust noise")  # conditional absence


def test_ws2_m6_firing_assertion_noop_when_flag_off(monkeypatch):
    monkeypatch.setenv(_CROSS, "0")  # kill-switch OFF -> the assertion disarms with the feature
    rg.assert_cross_source_synthesis_fired(_PRODUCER_SILENT_NOOP)  # no raise even with the silent-no-op line


# ── WS-0: the device-split launch config + co-residence preflight ────────────────────────────────

def test_ws0_recommended_split_covers_the_four_device_vars_plus_chunk():
    rec = gds.RECOMMENDED_DEVICE_SPLIT
    assert rec.get("PG_EMBED_DEVICE") == "cuda:0"
    assert rec.get("PG_RERANKER_DEVICE") == "cuda:1"
    assert rec.get("PG_NLI_DEVICE") == "cuda:1"
    assert rec.get("PG_CONSOLIDATION_NLI_DEVICE") == "cuda:1"
    assert rec.get("PG_CONTENT_RELEVANCE_SCORE_CHUNK") == "2"
    # genuinely SPLIT across two cards (not all on one).
    cards = {gds.resolve_gpu_card(rec[k]) for k in gds._HEAVY_MODEL_DEVICE_ENVS}
    assert cards == {0, 1}, f"the recommended split does not span 2 cards: {cards}"


def test_ws0_warns_when_all_heavy_models_coreside_on_one_card():
    env = {k: "cuda:0" for k in gds._HEAVY_MODEL_DEVICE_ENVS}
    env["PG_CONTENT_RELEVANCE_SCORE_CHUNK"] = "2"  # isolate the card-co-residence warning
    warns = gds.detect_coresidence_warnings(env, device_count=2)
    assert any("SINGLE card" in w for w in warns), f"no co-residence warning on all-cuda:0 / 2 cards: {warns}"


def test_ws0_unset_env_on_two_cards_warns_card_and_chunk():
    # every device env UNSET => module default cuda:0 => co-residence + one-pass OOM both fire.
    warns = gds.detect_coresidence_warnings({}, device_count=2)
    assert any("SINGLE card" in w for w in warns), warns
    assert any("PG_CONTENT_RELEVANCE_SCORE_CHUNK" in w for w in warns), warns


def test_ws0_recommended_split_is_silent_on_two_cards():
    warns = gds.detect_coresidence_warnings(gds.RECOMMENDED_DEVICE_SPLIT, device_count=2)
    assert warns == [], f"the recommended split still warned: {warns}"


def test_ws0_single_card_suppresses_card_warning_but_keeps_chunk_guard():
    # one GPU: a split cannot help, so no card warning; but the one-pass OOM guard still fires when unset.
    env = {k: "cuda:0" for k in gds._HEAVY_MODEL_DEVICE_ENVS}  # SCORE_CHUNK unset
    warns = gds.detect_coresidence_warnings(env, device_count=1)
    assert not any("SINGLE card" in w for w in warns), f"card warning should be suppressed on 1 GPU: {warns}"
    assert any("PG_CONTENT_RELEVANCE_SCORE_CHUNK" in w for w in warns), warns
    # with the chunk bound set, a single-card env is silent.
    env["PG_CONTENT_RELEVANCE_SCORE_CHUNK"] = "2"
    assert gds.detect_coresidence_warnings(env, device_count=1) == []


def test_ws0_export_lines_are_sourceable():
    text = gds.render_launch_template(as_export=True)
    for key, value in gds.RECOMMENDED_DEVICE_SPLIT.items():
        assert f"export {key}={value}" in text
