"""Offline oracle tests for the RunConfig core (MASTER_EXECUTION_PLAN §1).

No LLM, no network — pure resolver / registry / validity-matrix / cp0-payload logic over the real
canonical registry and tmp_path fixtures. The load-bearing test is ``test_empty_runconfig_byte_
identity``: it IS the WP-0b acceptance bar (an empty RunConfig resolves every live knob to exactly
``os.getenv(env_var, code_default)``, and the code_default is the real read-site literal — never
the Gate-B slate value nor the operator-locked value).
"""

from __future__ import annotations

import json

import pytest

from src.polaris_graph import run_config as rc
from src.polaris_graph.generator import checkpoint_envelope as ce


# ── registry loads + structural validation ──────────────────────────────────────────────────────

def test_registry_loads_and_block_dna_class_is_consistent():
    reg = rc.default_registry()
    assert reg.version >= 1
    assert reg.ids(), "registry seeds at least one knob"
    for knob_id in reg.ids():
        spec = reg.spec(knob_id)
        # dna_class is derived from the block; block<->dna_class must be the 1:1 map.
        assert spec.dna_class == reg._block_dna_class[spec.block]
        assert spec.dna_class in rc.ALLOWED_DNA_CLASSES
        # affects_stage is a checkpointed section stage OR the terminal render stage (s7_render).
        assert spec.affects_stage in rc.RESUME_STAGE_ORDER


def test_existing_knobs_cite_a_read_site():
    reg = rc.default_registry()
    for knob_id in reg.ids():
        spec = reg.spec(knob_id)
        if spec.status == "existing":
            assert spec.read_site, f"existing knob {knob_id} must cite its real os.getenv read site"


def _write_registry(tmp_path, knobs, block_dna_class=None):
    doc = {
        "registry_version": 1,
        "block_dna_class": block_dna_class
        or {"breadth": "breadth_budget", "scope": "scope_constraint",
            "deliverable": "presentation", "stages": "stage_tuning"},
        "knobs": knobs,
    }
    path = tmp_path / "reg.yaml"
    path.write_text(json.dumps(doc), encoding="utf-8")  # JSON is valid YAML
    return path


def test_registry_rejects_bad_dna_class(tmp_path):
    path = _write_registry(
        tmp_path, knobs=[], block_dna_class={
            "breadth": "make_a_number_go_up", "scope": "scope_constraint",
            "deliverable": "presentation", "stages": "stage_tuning"},
    )
    with pytest.raises(rc.RunConfigError, match="dna_class"):
        rc.RunConfigRegistry.load(path)


def test_registry_rejects_day_waster_env(tmp_path):
    path = _write_registry(tmp_path, knobs=[{
        "id": "canary_min", "block": "breadth", "type": "int",
        "env_var": "PG_BREADTH_CANARY_MIN", "code_default": 5, "affects_stage": "s1_fetch",
    }])
    with pytest.raises(rc.RunConfigError, match="DAY-WASTER"):
        rc.RunConfigRegistry.load(path)


def test_registry_rejects_incomplete_block_map(tmp_path):
    path = _write_registry(tmp_path, knobs=[], block_dna_class={"breadth": "breadth_budget"})
    with pytest.raises(rc.RunConfigError, match="cover exactly"):
        rc.RunConfigRegistry.load(path)


# ── THE BAR: empty-RunConfig byte-identity, per live knob ────────────────────────────────────────

# (knob_id, env_unset_expected, env_set_string, env_set_expected). The env_unset_expected is the
# REAL read-site default literal — the trap-1 guard: it is NOT the slate value, NOT the locked value.
_LIVE_KNOBS = [
    ("bypass_max_inflight", 32, "14", 14),          # code_default 32 (access_bypass.py:1646); slate=14
    ("storm_concurrency", 4, "8", 8),               # code_default 4 (storm_interviews.py:1410); slate=8
    ("max_parallel_sections", 3, "6", 6),           # code_default 3 (run_honest_sweep_r3.py:15237); slate=6
    ("serper_total_per_query", 0, "40", 40),        # code_default 0 (run_honest_sweep_r3.py:5568)
    ("extract_user_constraints", False, "1", True), # code_default false (intake_constraint_extractor.py:130)
    ("extract_scope_constraints", False, "1", True),# code_default false (intake_constraint_extractor.py:782)
]


@pytest.mark.parametrize("knob_id,unset_expected,env_str,set_expected", _LIVE_KNOBS)
def test_empty_runconfig_byte_identity(knob_id, unset_expected, env_str, set_expected):
    reg = rc.default_registry()
    spec = reg.spec(knob_id)
    # env UNSET + no parsed/panel: get() must return the real code_default (the byte-identity bar).
    cfg_unset = rc.build_run_config(registry=reg, env={})
    assert cfg_unset.get(knob_id) == unset_expected
    assert cfg_unset.source(knob_id) == rc.SOURCE_DEFAULT
    assert cfg_unset.get(knob_id) == rc.coerce(spec.code_default, spec.type)
    # env SET (the slate layer): get() returns the env value coerced (env beats code default).
    cfg_env = rc.build_run_config(registry=reg, env={spec.env_var: env_str})
    assert cfg_env.get(knob_id) == set_expected
    assert cfg_env.source(knob_id) == rc.SOURCE_ENV


def test_bypass_default_is_not_the_locked_or_slate_value():
    # Explicit trap-1 regression: an empty config must NOT silently return the operator-locked 14
    # or the slate 20 — the slate/lock live at the ENV layer, not the registry default.
    cfg = rc.build_run_config(registry=rc.default_registry(), env={})
    assert cfg.get("bypass_max_inflight") == 32
    assert cfg.get("bypass_max_inflight") not in (14, 16, 20)


# ── precedence: panel > parsed > env > default (§1.3, R9) ────────────────────────────────────────

def test_full_precedence_matrix():
    reg = rc.default_registry()
    kid = "query_budget"
    env_var = reg.spec(kid).env_var
    # All four layers set the same knob to different values → panel wins.
    cfg = rc.build_run_config(
        registry=reg, env={env_var: "40"},
        parsed={kid: (60, "run at least 60 queries")}, panel={kid: 80},
    )
    assert cfg.get(kid) == 80 and cfg.source(kid) == rc.SOURCE_PANEL
    # Drop panel → parsed wins, and the verbatim span is recorded.
    cfg = rc.build_run_config(registry=reg, env={env_var: "40"}, parsed={kid: (60, "run at least 60 queries")})
    assert cfg.get(kid) == 60 and cfg.source(kid) == rc.SOURCE_PARSED
    assert cfg.provenance[kid].span == "run at least 60 queries"
    # Drop parsed → env wins.
    cfg = rc.build_run_config(registry=reg, env={env_var: "40"})
    assert cfg.get(kid) == 40 and cfg.source(kid) == rc.SOURCE_ENV
    # Drop env → code default wins.
    cfg = rc.build_run_config(registry=reg, env={})
    assert cfg.get(kid) == 35 and cfg.source(kid) == rc.SOURCE_DEFAULT


def test_panel_beats_parsed_for_one_knob():
    reg = rc.default_registry()
    kid = "breadth_class"
    cfg = rc.build_run_config(registry=reg, env={}, parsed={kid: ("WIDE", "comprehensive")}, panel={kid: "NARROW"})
    assert cfg.get(kid) == "NARROW" and cfg.source(kid) == rc.SOURCE_PANEL


def test_unknown_knob_in_surface_fails_loud():
    reg = rc.default_registry()
    with pytest.raises(rc.RunConfigError, match="unknown knob"):
        rc.build_run_config(registry=reg, env={}, panel={"not_a_real_knob": 1})


# ── sha + non-default disclosure ─────────────────────────────────────────────────────────────────

def test_sha_is_deterministic_and_value_sensitive():
    reg = rc.default_registry()
    a = rc.build_run_config(registry=reg, env={})
    b = rc.build_run_config(registry=reg, env={})
    assert a.sha() == b.sha()
    c = rc.build_run_config(registry=reg, env={}, panel={"query_budget": 99})
    assert c.sha() != a.sha()


def test_non_default_knobs_disclosure_set():
    reg = rc.default_registry()
    cfg = rc.build_run_config(registry=reg, env={}, panel={"query_budget": 80, "tone": "executive_brief"})
    nd = cfg.non_default_knobs()
    assert set(nd) == {"query_budget", "tone"}
    assert all(p.source == rc.SOURCE_PANEL for p in nd.values())


# ── the two-sided resume validity matrix (§1.4) ─────────────────────────────────────────────────

def _valid_cps(cfg, knob_id):
    """The set of cpN aliases at which an adjustment for knob_id is accepted (no raise)."""
    ok = []
    for cp in ("cp0", "cp1", "cp2", "cp3", "cp4", "cp5", "cp6"):
        try:
            cfg.assert_adjustment_valid(knob_id, cp)
            ok.append(cp)
        except rc.RunConfigError:
            pass
    return ok


def test_validity_matrix_per_knob_anchors():
    cfg = rc.build_run_config(registry=rc.default_registry(), env={})
    # breadth (affects s1_fetch) → valid ONLY at cp0.
    assert _valid_cps(cfg, "query_budget") == ["cp0"]
    with pytest.raises(rc.RunConfigError, match="does NOT re-run"):
        cfg.assert_adjustment_valid("query_budget", "cp1")
    # scope (affects s2_select) → valid at cp0, cp1; scope-at-cp2/cp4 is a hard error.
    assert _valid_cps(cfg, "extract_user_constraints") == ["cp0", "cp1"]
    # deliverable STRUCTURE (affects s4_outline) → valid cp0..cp3 ("resume from the outline step").
    assert _valid_cps(cfg, "audience") == ["cp0", "cp1", "cp2", "cp3"]
    # deliverable TONE/LENGTH (affects s5_compose) → valid cp0..cp4 (compose re-runs).
    assert _valid_cps(cfg, "tone") == ["cp0", "cp1", "cp2", "cp3", "cp4"]
    assert _valid_cps(cfg, "length_target") == ["cp0", "cp1", "cp2", "cp3", "cp4"]
    # deliverable RENDER (affects s7_render) → valid at EVERY resume (render re-runs each time).
    assert _valid_cps(cfg, "reference_style") == ["cp0", "cp1", "cp2", "cp3", "cp4", "cp5", "cp6"]
    assert _valid_cps(cfg, "summary_first") == ["cp0", "cp1", "cp2", "cp3", "cp4", "cp5", "cp6"]


def test_earliest_resume_checkpoint_vocabulary():
    reg = rc.default_registry()
    assert reg.earliest_resume_checkpoint("query_budget") == ce.STAGE_S0_INTAKE       # s1 -> cp0
    assert reg.earliest_resume_checkpoint("extract_user_constraints") == ce.STAGE_S1_FETCH  # s2 -> cp1
    assert reg.earliest_resume_checkpoint("audience") == ce.STAGE_S3_CONSOLIDATE       # s4 -> cp3
    assert reg.earliest_resume_checkpoint("tone") == ce.STAGE_S4_OUTLINE               # s5 -> cp4
    assert reg.earliest_resume_checkpoint("reference_style") == ce.STAGE_S6_VERIFY     # render -> cp6


# ── --run-config override file intake ────────────────────────────────────────────────────────────

def test_load_overrides_file_good_and_malformed(tmp_path):
    good = tmp_path / "ov.json"
    good.write_text(json.dumps({"panel": {"query_budget": 80}}), encoding="utf-8")
    parsed = rc.load_overrides_file(good)
    assert parsed["panel"] == {"query_budget": 80}
    cfg = rc.build_run_config(registry=rc.default_registry(), env={}, **parsed)
    assert cfg.get("query_budget") == 80

    bare = tmp_path / "bare.json"
    bare.write_text(json.dumps({"query_budget": 50}), encoding="utf-8")
    assert rc.load_overrides_file(bare)["panel"] == {"query_budget": 50}

    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    with pytest.raises(rc.RunConfigError, match="unreadable/malformed"):
        rc.load_overrides_file(bad)

    with pytest.raises(rc.RunConfigError, match="not found"):
        rc.load_overrides_file(tmp_path / "missing.json")
