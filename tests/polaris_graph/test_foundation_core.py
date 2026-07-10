"""Guard tests for the RunConfig + checkpoint foundation (WAVE 0).

Offline, pure-logic. Mirrors the five acceptance conditions proven by
scripts/foundation_selftest.py, plus the schema-time registry guards (§1.2 / §1.7).
"""

from __future__ import annotations

import pytest

from src.polaris_graph import checkpoint_envelope as ck
from src.polaris_graph import run_config as rc


@pytest.fixture(scope="module")
def registry():
    return rc.load_registry()


# --------------------------- registry / resolver ---------------------------


def test_registry_loads_and_validates(registry):
    assert len(registry) >= 30
    for spec in registry.values():
        assert spec.block in rc._LEGAL_BLOCKS
        assert spec.dna_class in rc._LEGAL_DNA_CLASSES
        assert spec.earliest_resume_checkpoint in rc.CHECKPOINT_ORDER


def test_precedence_panel_prompt_env_default(registry):
    env = {"PG_QGEN_FS_RESEARCHER_MAX_QUERIES": "45"}
    full = rc.RunConfig.from_sources(prompt_text="run 60 queries",
                                     panel_overrides={"query_count": 99}, registry=registry)
    assert rc.get(full, "query_count", registry=registry, env=env).source == rc.SOURCE_PANEL
    assert rc.get(full, "query_count", registry=registry, env=env).value == 99
    prompt_only = rc.RunConfig(prompt=dict(full.prompt))
    pp = rc.get(prompt_only, "query_count", registry=registry, env=env)
    assert (pp.source, pp.value) == (rc.SOURCE_PROMPT, 60) and pp.span
    pe = rc.get(rc.RunConfig(), "query_count", registry=registry, env=env)
    assert (pe.source, pe.value) == (rc.SOURCE_ENV, 45)
    pd = rc.get(rc.RunConfig(), "query_count", registry=registry, env={})
    assert (pd.source, pd.value) == (rc.SOURCE_DEFAULT, 35)


def test_empty_config_is_byte_identical_defaults(registry):
    empty = rc.RunConfig()
    for kid, spec in registry.items():
        p = rc.get(empty, kid, registry=registry, env={})
        assert p.source == rc.SOURCE_DEFAULT
        assert p.value == spec.code_default


def test_prompt_parse_is_anti_invention(registry):
    # a prompt with no directives sets nothing
    cfg = rc.RunConfig.from_sources(prompt_text="Tell me about diabetes.", registry=registry)
    assert cfg.prompt == {}
    # a directive carries a verbatim span
    cfg2 = rc.RunConfig.from_sources(prompt_text="Write an executive brief.", registry=registry)
    assert cfg2.prompt["tone"][0] == "executive_brief"
    assert "executive brief" in cfg2.prompt["tone"][1].lower()


def test_registry_rejects_day_waster(tmp_path):
    bad = tmp_path / "knobs.yaml"
    bad.write_text(
        "schema_version: 1\nknobs:\n"
        "  - {id: pg_breadth_canary_min, block: breadth, type: int, code_default: 1, "
        "env_var: null, earliest_resume_checkpoint: cp0, prompt_parseable: false, "
        "panel_widget: number, dna_class: breadth_budget}\n",
        encoding="utf-8",
    )
    with pytest.raises(rc.RunConfigError, match="day-waster"):
        rc.load_registry(bad)


def test_registry_rejects_model_token_env(tmp_path):
    bad = tmp_path / "knobs.yaml"
    bad.write_text(
        "schema_version: 1\nknobs:\n"
        "  - {id: generator, block: stages, type: str, code_default: null, "
        "env_var: PG_GENERATOR_MODEL, earliest_resume_checkpoint: cp0, prompt_parseable: false, "
        "panel_widget: text, dna_class: stage_tuning}\n",
        encoding="utf-8",
    )
    with pytest.raises(rc.RunConfigError, match="§1.7|model/token"):
        rc.load_registry(bad)


# --------------------------- adjustment validity ---------------------------


def test_adjustment_validity_matrix(registry):
    # deliverable knob valid at cp3, invalid at cp4 (its stage already ran)
    assert rc.adjustment_valid_at("tone", "cp3", registry) is True
    assert rc.adjustment_valid_at("tone", "cp4", registry) is False
    # breadth knob valid only at cp0
    assert rc.adjustment_valid_at("query_count", "cp0", registry) is True
    assert rc.adjustment_valid_at("query_count", "cp1", registry) is False


def test_apply_adjustment_downstream(registry):
    base = rc.RunConfig()
    adjusted = rc.apply_adjustment(base, {"tone": "executive_brief"}, "cp3", registry)
    p = rc.get(adjusted, "tone", registry=registry, env={})
    assert p.value == "executive_brief" and p.source == rc.SOURCE_ADJUST
    with pytest.raises(rc.RunConfigError):
        rc.apply_adjustment(base, {"query_count": 99}, "cp3", registry)


# --------------------------- checkpoint envelope ---------------------------


def _write_chain(run_dir):
    q = "Q?"
    for cp_id, _s, _f in ck.CHECKPOINT_STAGES:
        ck.save_checkpoint(run_dir, cp_id=cp_id, run_id="t", slug="s", domain="d",
                           question=q, payload={"data": [cp_id]}, flag_slate={"F": "0"})
    return q


def test_checkpoint_roundtrip_byte_identical(tmp_path):
    run_dir = tmp_path / "run"
    q = _write_chain(run_dir)
    for cp_id, _s, _f in ck.CHECKPOINT_STAGES:
        path = ck.checkpoint_path(run_dir, cp_id)
        raw = path.read_bytes()
        import json
        assert ck.serialize_envelope(json.loads(raw.decode())) == raw
        env = ck.load_checkpoint(run_dir, cp_id, expected_question_sha=ck.question_sha(q))
        assert env["payload"] == {"data": [cp_id]}


def test_checkpoint_chain_validates(tmp_path):
    run_dir = tmp_path / "run"
    _write_chain(run_dir)
    assert ck.validate_hash_chain(run_dir) == list(ck._CP_IDS)


def test_checkpoint_refuses_verdict_payload(tmp_path):
    with pytest.raises(ck.CheckpointEnvelopeError, match="FORBIDDEN verdict"):
        ck.build_envelope(cp_id="cp3", run_id="t", slug="s", domain="d", question="Q?",
                          payload={"nested": [{"is_verified": True}]})


def test_checkpoint_tamper_detected(tmp_path):
    run_dir = tmp_path / "run"
    _write_chain(run_dir)
    # tamper cp2 on disk after write
    p = ck.checkpoint_path(run_dir, "cp2")
    p.write_bytes(p.read_bytes().replace(b'"cp2"', b'"cp2"', 1) + b" ")
    with pytest.raises(ck.CheckpointEnvelopeError):
        ck.validate_hash_chain(run_dir)


def test_resume_wrong_question_refused(tmp_path):
    run_dir = tmp_path / "run"
    _write_chain(run_dir)
    with pytest.raises(ck.CheckpointEnvelopeError, match="question_sha"):
        ck.load_checkpoint(run_dir, "cp3", expected_question_sha="deadbeef")


def test_supersede_keeps_upstream(tmp_path):
    run_dir = tmp_path / "run"
    _write_chain(run_dir)
    before = {cp: ck.sha256_file(ck.checkpoint_path(run_dir, cp)) for cp in ("cp0", "cp1", "cp2", "cp3")}
    ck.supersede_downstream(run_dir, "cp3", adjustment_sha="x")
    after = {cp: ck.sha256_file(ck.checkpoint_path(run_dir, cp)) for cp in ("cp0", "cp1", "cp2", "cp3")}
    assert before == after
    assert not ck.checkpoint_path(run_dir, "cp4").exists()
    assert any(e.get("event") == "superseded" for e in ck.read_index(run_dir))
