"""Unit tests for the small-scale validation probe's PURE assertion logic
(I-deepfix-001 #1344). Tiny SYNTHETIC manifest fixtures in -> Check verdicts out.

These exercise ONLY the offline, pure assertion functions (no run, no model, no
network, no spend). The probe module is loaded by file path so the heavy
src.polaris_graph package __init__ never runs.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

_PROBE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "small_scale_validation_probe.py"


def _load_probe():
    spec = importlib.util.spec_from_file_location("small_scale_validation_probe_under_test", str(_PROBE_PATH))
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    # Register BEFORE exec: @dataclass resolves sys.modules[cls.__module__].__dict__, which is
    # None for an unregistered synthetic module (Py3.12+ dataclasses fail-loud otherwise).
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


probe = _load_probe()


def _by_name(checks):
    return {c.name: c for c in checks}


# --------------------------------------------------------------------------------------------
# BREADTH assertions
# --------------------------------------------------------------------------------------------

def _good_breadth_manifest():
    # discovered (1299) >> budget (200): dropped_pre_fetch == budget overflow, demote fired,
    # fetched (200) >> legacy 40.
    return {
        "retrieval": {
            "fetched": 200,
            "failed": 9,
            "retrieval_caps": {
                "candidates_discovered": 1299,
                "fetched": 200,
                "failed": 9,
                "dropped_pre_fetch": 1090,  # == max(0, 1299 - 200 - 9)
                "search_truncations": [
                    {"cap": "PG_LIVE_FETCH_CAP", "value": 200, "bit": True},
                ],
            },
            "relevance_gate": {
                "threshold": 0.30,
                "kept_on_topic": 140,
                "demoted_below_floor": 60,
                "demoted_fetched_to_fill": 60,
                "demoted_tail": 0,
                "fetched_budget": 200,
                "scorer": "semantic_v2",
            },
        }
    }


def test_breadth_good_manifest_all_green():
    checks = probe.breadth_manifest_checks(_good_breadth_manifest(), legacy_fetch_floor=40)
    by = _by_name(checks)
    assert by["breadth.relevance_gate_present"].passed
    assert by["breadth.demote_fired"].passed
    assert by["breadth.dropped_is_budget_not_floor"].passed
    assert by["breadth.fetched_above_legacy_40"].passed
    assert all(c.passed for c in checks)


def test_breadth_small_query_no_overflow_green():
    # A cheap query: discovered (55) < budget (200) -> dropped_pre_fetch == 0, demote still
    # fired (some below-floor sources fetched), fetched (55) > 40.
    m = {
        "retrieval": {
            "fetched": 55,
            "failed": 0,
            "retrieval_caps": {
                "candidates_discovered": 55,
                "fetched": 55,
                "failed": 0,
                "dropped_pre_fetch": 0,
                "search_truncations": [{"cap": "PG_LIVE_FETCH_CAP", "value": 200}],
            },
            "relevance_gate": {"threshold": 0.30, "demoted_fetched_to_fill": 12},
        }
    }
    checks = probe.breadth_manifest_checks(m, legacy_fetch_floor=40)
    assert all(c.passed for c in checks)


def test_breadth_missing_relevance_gate_red():
    m = {"retrieval": {"fetched": 200, "retrieval_caps": {"candidates_discovered": 300,
                                                          "dropped_pre_fetch": 0}}}
    by = _by_name(probe.breadth_manifest_checks(m))
    assert not by["breadth.relevance_gate_present"].passed
    assert not by["breadth.demote_fired"].passed


def test_breadth_demote_not_fired_red():
    m = _good_breadth_manifest()
    m["retrieval"]["relevance_gate"]["demoted_fetched_to_fill"] = 0
    by = _by_name(probe.breadth_manifest_checks(m))
    assert not by["breadth.demote_fired"].passed
    # the others still hold
    assert by["breadth.relevance_gate_present"].passed


def test_breadth_hard_floor_drop_red():
    # dropped_pre_fetch exceeds what the budget can explain -> a banned pre-fetch hard FILTER.
    m = _good_breadth_manifest()
    m["retrieval"]["retrieval_caps"]["dropped_pre_fetch"] = 1290  # > max(0, 1299-200-9)=1090
    by = _by_name(probe.breadth_manifest_checks(m))
    assert not by["breadth.dropped_is_budget_not_floor"].passed


def test_breadth_fetched_below_40_red():
    m = _good_breadth_manifest()
    m["retrieval"]["fetched"] = 30
    m["retrieval"]["retrieval_caps"]["fetched"] = 30
    by = _by_name(probe.breadth_manifest_checks(m))
    assert not by["breadth.fetched_above_legacy_40"].passed


# --------------------------------------------------------------------------------------------
# KIMI seam assertions
# --------------------------------------------------------------------------------------------

def _good_kimi_manifest():
    return {
        "status": "success",
        "four_role_seam_inert": False,
        "disclosed_gaps": [],
        "four_role_evaluation": {
            "held_reasons": [],
            "gaps": [],
            "final_verdicts": {"c1": "VERIFIED", "c2": "UNSUPPORTED", "c3": "VERIFIED"},
        },
    }


def _good_role_calls():
    return [
        {"claim_id": "c1", "role": "judge", "model_slug": "moonshotai/kimi-k2.6",
         "served_model": "moonshotai/kimi-k2.6", "raw_text": "VERDICT: VERIFIED"},
        {"claim_id": "c2", "role": "judge", "model_slug": "moonshotai/kimi-k2.6",
         "served_model": "moonshotai/kimi-k2.6", "raw_text": "VERDICT: UNSUPPORTED"},
        {"claim_id": "c3", "role": "mirror", "model_slug": "z-ai/glm-5.1",
         "served_model": "z-ai/glm-5.1", "raw_text": "ok"},
    ]


def test_kimi_good_seam_all_green():
    checks = probe.kimi_seam_checks(
        _good_kimi_manifest(),
        {"rate_limit_hits_total": 0, "claims_total": 3, "claims_certified": 2},
        _good_role_calls(),
        max_429=0,
    )
    assert all(c.passed for c in checks), {c.name: c.detail for c in checks if not c.passed}


def test_kimi_transport_exhausted_red():
    m = _good_kimi_manifest()
    m["status"] = "abort_role_transport_exhausted"
    by = _by_name(probe.kimi_seam_checks(m, {"rate_limit_hits_total": 0}, _good_role_calls()))
    assert not by["kimi.not_transport_exhausted"].passed


def test_kimi_seam_inert_red():
    m = _good_kimi_manifest()
    m["four_role_seam_inert"] = True
    by = _by_name(probe.kimi_seam_checks(m, {"rate_limit_hits_total": 0}, _good_role_calls()))
    assert not by["kimi.seam_not_inert"].passed


def test_kimi_seam_held_reason_red():
    m = _good_kimi_manifest()
    m["four_role_evaluation"]["held_reasons"] = ["seam_timeout"]
    by = _by_name(probe.kimi_seam_checks(m, {"rate_limit_hits_total": 0}, _good_role_calls()))
    assert not by["kimi.no_seam_held_reason"].passed


def test_kimi_unadjudicated_gap_red():
    m = _good_kimi_manifest()
    m["disclosed_gaps"] = ["four_role_seam_unadjudicated: the four-role D8 judge could not be reached"]
    by = _by_name(probe.kimi_seam_checks(m, {"rate_limit_hits_total": 0}, _good_role_calls()))
    assert not by["kimi.no_seam_unadjudicated_gap"].passed


def test_kimi_429_storm_red():
    by = _by_name(probe.kimi_seam_checks(
        _good_kimi_manifest(), {"rate_limit_hits_total": 7}, _good_role_calls(), max_429=0))
    assert not by["kimi.no_429_storm"].passed


def test_kimi_missing_telemetry_red():
    by = _by_name(probe.kimi_seam_checks(_good_kimi_manifest(), None, _good_role_calls()))
    assert not by["kimi.no_429_storm"].passed


def test_kimi_empty_verdicts_red():
    m = _good_kimi_manifest()
    m["four_role_evaluation"]["final_verdicts"] = {}
    by = _by_name(probe.kimi_seam_checks(m, {"rate_limit_hits_total": 0}, _good_role_calls()))
    assert not by["kimi.final_verdicts_nonempty"].passed


def test_kimi_blank_judge_call_red():
    rc = _good_role_calls()
    rc[0]["raw_text"] = ""  # a 400 / blank on the bare reasoning block
    by = _by_name(probe.kimi_seam_checks(_good_kimi_manifest(), {"rate_limit_hits_total": 0}, rc))
    assert not by["kimi.judge_calls_parseable"].passed


def test_kimi_role_label_fallback_to_all_calls():
    # If no record carries role=="judge", fall back to ALL role calls (still parseable here).
    rc = [{"claim_id": "c1", "role": "verifier", "served_model": "x", "raw_text": "VERIFIED"}]
    by = _by_name(probe.kimi_seam_checks(_good_kimi_manifest(), {"rate_limit_hits_total": 0}, rc))
    assert by["kimi.judge_calls_parseable"].passed


# --------------------------------------------------------------------------------------------
# LAUNCH-PATH: the kimi seam probe must launch via the SLATE-APPLYING run_gate_b.py, NOT
# run_honest_sweep_r3.py --pathB-gate (which skips the slate -> enrichment OFF -> narrow report).
# --------------------------------------------------------------------------------------------

def test_kimi_command_launches_via_run_gate_b_not_pathb_gate():
    cmd = probe.kimi_vm_command()
    assert "scripts/dr_benchmark/run_gate_b.py" in cmd, cmd
    assert "--pathB-gate" not in cmd, "the slate-SKIPPING --pathB-gate wrapper must not be used"
    assert "--resume" in cmd and "--only" in cmd, cmd


def test_breadth_command_uses_sweep_with_explicit_relevance_gate():
    cmd = probe.breadth_vm_command()
    # the FRONT-HALF breadth proof is fine via run_honest_sweep_r3.py (the §-1.3 demote lives in
    # retrieval, not the post-gen enrichment); it sets PG_RETRIEVAL_RELEVANCE_GATE=1 explicitly.
    assert "run_honest_sweep_r3.py" in cmd, cmd
    assert "PG_RETRIEVAL_RELEVANCE_GATE=1" in cmd, cmd
    assert "run_gate_b.py" not in cmd, cmd


# --------------------------------------------------------------------------------------------
# DICED-LEG / LAUNCH-PATH coupling (Codex P1 #1344 wave-3): the BREADTH probe (no-slate
# run_honest_sweep_r3.py) asserts the FRONT-HALF dice D3_relevance_gate_fetch_budget ONLY -- the
# back-half cite-breadth dice D2_composition_breadth would be a false-FAIL there (enrichment OFF).
# The KIMI probe (slate-applying run_gate_b.py) is the one that asserts D2_composition_breadth.
# --------------------------------------------------------------------------------------------

def _stub_diced_script(tmp_path: Path, statuses: dict[str, str]) -> Path:
    """A tiny stand-in for pipeline_diced_preflight.py: writes the same --json contract the probe
    consumes (an "offline" list of {name, status}). No run, no model -- pure I/O."""
    rows = ",".join(
        "{" + f"'name': {name!r}, 'status': {st!r}" + "}" for name, st in statuses.items()
    )
    stub = tmp_path / "stub_diced.py"
    stub.write_text(
        "import json, sys\n"
        "out = sys.argv[sys.argv.index('--json') + 1]\n"
        f"payload = {{'offline': [{rows}]}}\n"
        "open(out, 'w', encoding='utf-8').write(json.dumps(payload))\n",
        encoding="utf-8",
    )
    return stub


def test_diced_preflight_checks_selects_only_requested_dice(tmp_path):
    stub = _stub_diced_script(tmp_path, {
        "D2_composition_breadth": "GREEN",
        "D3_relevance_gate_fetch_budget": "RED",
    })
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    # breadth leg requests D3 ONLY -> exactly one check, named for D3, RED here.
    front = probe.diced_preflight_checks(run_dir, stub, ["D3_relevance_gate_fetch_budget"])
    assert [c.name for c in front] == ["diced.D3_relevance_gate_fetch_budget"]
    assert not front[0].passed
    # kimi leg requests D2 ONLY -> exactly one check, named for D2, GREEN here.
    back = probe.diced_preflight_checks(run_dir, stub, ["D2_composition_breadth"])
    assert [c.name for c in back] == ["diced.D2_composition_breadth"]
    assert back[0].passed


def test_assert_breadth_requests_only_front_half_d3(tmp_path, monkeypatch):
    captured = {}

    def _fake(run_dir, diced_path, dice_names):
        captured["names"] = list(dice_names)
        return []

    monkeypatch.setattr(probe, "diced_preflight_checks", _fake)
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "manifest.json").write_text(json.dumps(_good_breadth_manifest()), encoding="utf-8")
    probe.assert_breadth(run_dir, tmp_path / "diced.py")
    assert captured["names"] == ["D3_relevance_gate_fetch_budget"]
    assert "D2_composition_breadth" not in captured["names"]


def test_assert_kimi_requests_back_half_d2(tmp_path, monkeypatch):
    captured = {}

    def _fake(run_dir, diced_path, dice_names):
        captured["names"] = list(dice_names)
        return []

    monkeypatch.setattr(probe, "diced_preflight_checks", _fake)
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "manifest.json").write_text(json.dumps(_good_kimi_manifest()), encoding="utf-8")
    probe.assert_kimi(run_dir, tmp_path / "diced.py")
    assert captured["names"] == ["D2_composition_breadth"]
