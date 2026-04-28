"""M-D11 phase 1 model-pin tests (schema v4)."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from src.polaris_graph.audit_ir.model_pin import (
    DEFAULT_REPLAY_ENV_VARS,
    DEFAULT_ROUTING_ENV_VARS,
    PIN_SCHEMA_VERSION,
    ModelPin,
    ModelPinError,
    capture_env_snapshot,
    capture_pin,
    hash_file,
    hash_inductor_profile,
    pin_from_dict,
    pin_from_json,
    pin_to_dict,
    pin_to_json,
    pins_equivalent_for_replay,
)


# ---------------------------------------------------------------------------
# Capture
# ---------------------------------------------------------------------------


def test_capture_pin_minimal() -> None:
    pin = capture_pin(
        run_id="run_001",
        llm_models={"generator": "qwen/qwen3.5-plus"},
    )
    assert pin.run_id == "run_001"
    assert pin.pin_schema_version == "v4"
    assert pin.llm_models == {"generator": "qwen/qwen3.5-plus"}
    assert pin.llm_providers == {"generator": "openrouter"}
    assert pin.prompt_version_hashes == {}
    assert pin.captured_at > 0
    assert pin.retrieval_source_versions == {}
    assert pin.inductor_type is None
    assert pin.inductor_version_hash is None
    assert pin.validation_set_hash is None
    assert pin.env_snapshot == {}
    assert pin.notes == ""


def test_capture_pin_full_multi_model() -> None:
    pin = capture_pin(
        run_id="run_002",
        llm_models={
            "generator": "z-ai/glm-5.1",
            "evaluator": "qwen/qwen3.5-plus",
            "judge": "anthropic/claude-haiku-4-5",
            "inductor_classifier": "z-ai/glm-5.1",
        },
        llm_providers={
            "generator": "openrouter",
            "evaluator": "direct",
        },
        role_prompts={
            "generator": "You are a research synthesizer.",
            "evaluator": "You judge faithfulness.",
        },
        retrieval_source_versions={
            "crossref": "v1",
            "pubmed": "2024-12",
            "unpaywall": "v2",
        },
        inductor_type="LLMAugmentedInductor",
        inductor_profile_text="anchor: tirzepatide; support: t2dm",
        env_snapshot={"OPENROUTER_BASE_URL": "https://openrouter.ai/api/v1"},
        notes="Q1 2026 baseline",
    )
    assert pin.llm_providers["generator"] == "openrouter"
    assert pin.llm_providers["evaluator"] == "direct"
    # Roles in models but not in providers got auto-filled openrouter.
    assert pin.llm_providers["judge"] == "openrouter"
    assert pin.llm_providers["inductor_classifier"] == "openrouter"
    assert len(pin.prompt_version_hashes["generator"]) == 64  # SHA-256 hex
    assert len(pin.prompt_version_hashes["evaluator"]) == 64
    # judge / inductor_classifier didn't have role_prompts → no hash.
    assert "judge" not in pin.prompt_version_hashes
    assert "inductor_classifier" not in pin.prompt_version_hashes
    assert pin.retrieval_source_versions["crossref"] == "v1"
    assert pin.inductor_type == "LLMAugmentedInductor"
    assert len(pin.inductor_version_hash or "") == 64
    assert pin.env_snapshot["OPENROUTER_BASE_URL"] == "https://openrouter.ai/api/v1"
    assert pin.notes == "Q1 2026 baseline"


def test_capture_pin_rejects_empty_run_id() -> None:
    with pytest.raises(ModelPinError, match="run_id"):
        capture_pin(run_id="", llm_models={"generator": "x"})


def test_capture_pin_rejects_empty_models() -> None:
    with pytest.raises(ModelPinError, match="llm_models"):
        capture_pin(run_id="r", llm_models={})


def test_capture_pin_rejects_empty_model_value() -> None:
    with pytest.raises(ModelPinError, match="llm_models"):
        capture_pin(run_id="r", llm_models={"generator": ""})


def test_capture_pin_rejects_whitespace_role() -> None:
    with pytest.raises(ModelPinError, match="llm_models"):
        capture_pin(run_id="r", llm_models={"   ": "m"})


def test_capture_pin_at_explicit_timestamp() -> None:
    pin = capture_pin(
        run_id="r",
        llm_models={"generator": "m"},
        captured_at=1700000000.0,
    )
    assert pin.captured_at == 1700000000.0


def test_capture_pin_provider_role_unknown_raises() -> None:
    with pytest.raises(ModelPinError, match="unknown roles"):
        capture_pin(
            run_id="r",
            llm_models={"generator": "m"},
            llm_providers={"evaluator": "openrouter"},  # not in models
        )


def test_capture_pin_role_prompts_unknown_raises() -> None:
    with pytest.raises(ModelPinError, match="role_prompts"):
        capture_pin(
            run_id="r",
            llm_models={"generator": "m"},
            role_prompts={"judge": "p"},  # judge not in models
        )


def test_capture_pin_env_snapshot_and_capture_names_mutually_exclusive() -> None:
    with pytest.raises(ModelPinError, match="not both"):
        capture_pin(
            run_id="r",
            llm_models={"generator": "m"},
            env_snapshot={"X": "1"},
            capture_env_var_names=["X"],
        )


def test_capture_pin_with_capture_env_var_names(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PG_TEST_PIN_VAR", "captured_value")
    monkeypatch.delenv("PG_TEST_PIN_MISSING", raising=False)
    pin = capture_pin(
        run_id="r",
        llm_models={"generator": "m"},
        capture_env_var_names=["PG_TEST_PIN_VAR", "PG_TEST_PIN_MISSING"],
    )
    assert pin.env_snapshot["PG_TEST_PIN_VAR"] == "captured_value"
    # v4: unset env var captured as None, NOT empty string.
    assert pin.env_snapshot["PG_TEST_PIN_MISSING"] is None


def test_capture_pin_default_schema_version() -> None:
    pin = capture_pin(run_id="r", llm_models={"generator": "m"})
    assert pin.pin_schema_version == PIN_SCHEMA_VERSION == "v4"


# ---------------------------------------------------------------------------
# capture_env_snapshot
# ---------------------------------------------------------------------------


def test_capture_env_snapshot_default_set_keys() -> None:
    snap = capture_env_snapshot()
    # Stable shape: every default name is present.
    for name in DEFAULT_REPLAY_ENV_VARS:
        assert name in snap


def test_capture_env_snapshot_missing_returns_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """v4: unset env var captured as None to distinguish from
    explicitly-empty (""). Phase 2 must DELETE the env var
    rather than set it to "" — many call sites do
    `int(os.getenv("X", "default"))` which would crash if the
    var were set to ""."""
    monkeypatch.delenv("PG_NOT_SET_FOR_TEST", raising=False)
    snap = capture_env_snapshot(["PG_NOT_SET_FOR_TEST"])
    assert snap["PG_NOT_SET_FOR_TEST"] is None


def test_capture_env_snapshot_explicit_empty_preserved(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """v4: a var set to "" stays as "" (distinct from unset)."""
    monkeypatch.setenv("PG_EXPLICIT_EMPTY_FOR_TEST", "")
    snap = capture_env_snapshot(["PG_EXPLICIT_EMPTY_FOR_TEST"])
    assert snap["PG_EXPLICIT_EMPTY_FOR_TEST"] == ""


def test_capture_env_snapshot_rejects_empty_name() -> None:
    with pytest.raises(ModelPinError, match="non-empty"):
        capture_env_snapshot(["", "OK"])


# ---------------------------------------------------------------------------
# Default env-var set verification (Codex round-2 fixes)
# ---------------------------------------------------------------------------


def test_default_replay_env_vars_uses_correct_fallbacks_var() -> None:
    """Round-2 fix: OPENROUTER_ALLOW_FALLBACKS is the actual var
    name used by openrouter_client; OPENROUTER_FALLBACKS doesn't
    exist in the codebase."""
    assert "OPENROUTER_ALLOW_FALLBACKS" in DEFAULT_REPLAY_ENV_VARS
    assert "OPENROUTER_FALLBACKS" not in DEFAULT_REPLAY_ENV_VARS


def test_default_replay_env_vars_includes_nli_knobs() -> None:
    """Round-2 fix: NLI faithfulness knobs alter verifier behavior
    and must be captured."""
    for name in (
        "PG_NLI_DISPUTE_THRESHOLD",
        "PG_NLI_CONTEXT_WINDOW",
        "PG_NLI_DOMAIN_ADAPTIVE",
        "PG_NLI_DOMAIN_FLOOR",
        "PG_FAITHFULNESS_NLI_THRESHOLD",
    ):
        assert name in DEFAULT_REPLAY_ENV_VARS, f"missing: {name}"


def test_default_replay_env_vars_includes_v3_toggles() -> None:
    """Round-2 fix: synthesis structural toggles change the prose
    surface and must be captured."""
    for name in (
        "PG_V3_SURFACE_ANALYSIS",
        "PG_V3_COMPARISON_TABLES",
        "PG_PHASE_5_ENABLED",
    ):
        assert name in DEFAULT_REPLAY_ENV_VARS, f"missing: {name}"


def test_default_replay_env_vars_includes_call_profile() -> None:
    """Round-2 fix: token-budget knobs alter generated outputs
    even when model + prompt are identical."""
    for name in (
        "PG_SECTION_WRITER_MAX_TOKENS",
        "PG_SECTION_CONTINUATION_MAX_TOKENS",
        "PG_GLM5_MIN_MAX_TOKENS",
    ):
        assert name in DEFAULT_REPLAY_ENV_VARS, f"missing: {name}"


def test_default_replay_env_vars_drops_dead_var() -> None:
    """Round-3 fix: OPENROUTER_PROVIDER_REQUIRE_PARAMETERS was
    only referenced in model_pin.py itself — dead var, removed."""
    assert (
        "OPENROUTER_PROVIDER_REQUIRE_PARAMETERS"
        not in DEFAULT_REPLAY_ENV_VARS
    )


def test_default_replay_env_vars_includes_round3_additions() -> None:
    """Round-3 fix: Codex flagged additional live behavior knobs
    that materially alter pipeline output."""
    for name in (
        # NLI model selection + faithfulness floor
        "PG_NLI_MODEL",
        "PG_FAITHLENS_MODEL",
        "PG_NLI_FAITHFULNESS_FLOOR",
        # Cross-source corroboration
        "PG_CROSS_SOURCE_ENABLED",
        "PG_CROSS_SOURCE_MIN_SIM",
        "PG_CROSS_SOURCE_MIN_NLI",
        "PG_CROSS_SOURCE_MAX_SOURCES",
        "PG_CROSS_SOURCE_SELF_CHECK_MIN",
        # Pipeline budgets / gap-fill
        "PG_V3_MAX_GAP_SEARCHES",
        "PG_V3_SYNTH_BUDGET_PCT",
        "PG_V3_ANALYSIS_ENABLED",
        "PG_STORM_ENABLED",
        # Additional max-token controls
        "PG_V3_SCOPE_MAX_TOKENS",
        "PG_V3_OUTLINE_MAX_TOKENS",
        "PG_VERIFY_MAX_TOKENS",
    ):
        assert name in DEFAULT_REPLAY_ENV_VARS, f"missing: {name}"


def test_default_replay_env_vars_includes_round4_additions() -> None:
    """Round-4 fix: Codex flagged headline replay-critical vars
    that should be in the seed list (rather than left to
    extension via capture_env_var_names)."""
    for name in (
        # Top-level run budget
        "PG_V3_TOTAL_BUDGET_SECONDS",
        # Verifier require-NLI gate
        "PG_REQUIRE_NLI_FOR_FAITHFUL",
        # Cross-source pair cap
        "PG_MAX_CROSS_SOURCE_PAIRS",
        # Contradiction detector binary + main threshold
        "PG_CONTRADICTION_ENABLED",
        "PG_CONTRADICTION_NLI_THRESHOLD",
        # STORM user-visible behavior knobs (beyond enable flag)
        "PG_STORM_PERSPECTIVES_COUNT",
        "PG_STORM_ROUNDS_PER_PERSPECTIVE",
        "PG_STORM_MAX_TIME_SECONDS",
        "PG_STORM_PERSONA_MAX_TOKENS",
    ):
        assert name in DEFAULT_REPLAY_ENV_VARS, f"missing: {name}"


def test_default_routing_env_vars_alias_to_replay_env_vars() -> None:
    """Backward-compat alias: imports of DEFAULT_ROUTING_ENV_VARS
    still resolve to the broader replay set."""
    assert DEFAULT_ROUTING_ENV_VARS == DEFAULT_REPLAY_ENV_VARS


# ---------------------------------------------------------------------------
# Symmetric retrieval_source_versions validation (Codex round-2 low finding)
# ---------------------------------------------------------------------------


def test_capture_pin_rejects_non_str_retrieval_value() -> None:
    with pytest.raises(ModelPinError, match="retrieval_source_versions"):
        capture_pin(
            run_id="r",
            llm_models={"generator": "m"},
            retrieval_source_versions={"crossref": 1},  # type: ignore[dict-item]
        )


def test_capture_pin_rejects_non_str_retrieval_key() -> None:
    with pytest.raises(ModelPinError, match="retrieval_source_versions"):
        capture_pin(
            run_id="r",
            llm_models={"generator": "m"},
            retrieval_source_versions={1: "v1"},  # type: ignore[dict-item]
        )


def test_capture_pin_rejects_empty_retrieval_key() -> None:
    with pytest.raises(ModelPinError, match="retrieval_source_versions"):
        capture_pin(
            run_id="r",
            llm_models={"generator": "m"},
            retrieval_source_versions={"  ": "v1"},
        )


# ---------------------------------------------------------------------------
# Hashing
# ---------------------------------------------------------------------------


def test_hash_inductor_profile_deterministic() -> None:
    h1 = hash_inductor_profile("anchor: foo; support: bar")
    h2 = hash_inductor_profile("anchor: foo; support: bar")
    assert h1 == h2
    assert len(h1) == 64


def test_hash_inductor_profile_changes_on_text_change() -> None:
    h1 = hash_inductor_profile("anchor: foo")
    h2 = hash_inductor_profile("anchor: foo;")  # extra char
    assert h1 != h2


def test_hash_file(tmp_path: Path) -> None:
    p = tmp_path / "test.txt"
    p.write_text("hello world", encoding="utf-8")
    h = hash_file(p)
    # SHA-256 of "hello world" is well-known.
    assert h == "b94d27b9934d3e08a52e52d7da7dabfac484efe37a5380ee9088f7ace2efcde9"


def test_hash_file_missing_raises(tmp_path: Path) -> None:
    with pytest.raises(ModelPinError, match="does not exist"):
        hash_file(tmp_path / "nonexistent.txt")


# ---------------------------------------------------------------------------
# Round-trip serialization
# ---------------------------------------------------------------------------


def test_pin_to_dict_round_trips() -> None:
    pin = capture_pin(
        run_id="r1",
        llm_models={"generator": "m1", "evaluator": "m2"},
        captured_at=1234567890.0,
        retrieval_source_versions={"a": "1"},
        env_snapshot={"OPENROUTER_BASE_URL": "https://example/api"},
    )
    d = pin_to_dict(pin)
    pin2 = pin_from_dict(d)
    assert pin2 == pin


def test_pin_to_json_round_trips() -> None:
    pin = capture_pin(
        run_id="r2",
        llm_models={"generator": "m"},
        role_prompts={"generator": "hello"},
        inductor_profile_text="anchor: x",
        env_snapshot={"PG_V3_ANALYTICAL_PROMPT": "1"},
    )
    text = pin_to_json(pin)
    pin2 = pin_from_json(text)
    assert pin2 == pin


def test_pin_to_json_stable_key_order() -> None:
    """Reproducible serialization: same pin → same JSON bytes."""
    pin = capture_pin(
        run_id="r3",
        llm_models={"generator": "m"},
        captured_at=100.0,
        retrieval_source_versions={"z": "1", "a": "2", "m": "3"},
        env_snapshot={"Z": "1", "A": "2"},
    )
    j1 = pin_to_json(pin)
    j2 = pin_to_json(pin)
    assert j1 == j2


def test_pin_to_dict_emits_schema_version() -> None:
    pin = capture_pin(run_id="r", llm_models={"generator": "m"})
    d = pin_to_dict(pin)
    assert d["pin_schema_version"] == "v4"


# ---------------------------------------------------------------------------
# pin_from_dict validation (re-applies invariants)
# ---------------------------------------------------------------------------


def test_pin_from_dict_rejects_v1_schema_no_version() -> None:
    """A v1-shaped dict (no pin_schema_version, llm_model singular)
    must not silently load."""
    v1_shape = {
        "run_id": "r",
        "captured_at": 0.0,
        "llm_model": "qwen/qwen3.5-plus",
        "llm_provider": "openrouter",
    }
    with pytest.raises(ModelPinError, match="pin_schema_version"):
        pin_from_dict(v1_shape)


def test_pin_from_dict_rejects_v2_schema() -> None:
    """A v2-shaped dict must not silently load under v4."""
    v2_shape = {
        "pin_schema_version": "v2",
        "run_id": "r",
        "captured_at": 0.0,
        "llm_models": {"generator": "m"},
        "llm_providers": {"generator": "openrouter"},
    }
    with pytest.raises(ModelPinError, match="pin_schema_version"):
        pin_from_dict(v2_shape)


def test_pin_from_dict_rejects_v3_schema() -> None:
    """A v3-shaped dict must not silently load under v4 (schema
    bumped after Codex round-3 review revised env capture set
    AND introduced None-vs-empty distinction)."""
    v3_shape = {
        "pin_schema_version": "v3",
        "run_id": "r",
        "captured_at": 0.0,
        "llm_models": {"generator": "m"},
        "llm_providers": {"generator": "openrouter"},
    }
    with pytest.raises(ModelPinError, match="pin_schema_version"):
        pin_from_dict(v3_shape)


def test_pin_from_dict_rejects_unknown_schema_version() -> None:
    with pytest.raises(ModelPinError, match="pin_schema_version"):
        pin_from_dict(
            {
                "pin_schema_version": "v99",
                "run_id": "r",
                "captured_at": 0.0,
                "llm_models": {"generator": "m"},
                "llm_providers": {"generator": "openrouter"},
            }
        )


def test_pin_from_dict_missing_llm_models() -> None:
    with pytest.raises(ModelPinError, match="missing required key"):
        pin_from_dict(
            {
                "pin_schema_version": "v4",
                "run_id": "r",
                "captured_at": 0.0,
            }
        )


def test_pin_from_dict_rejects_non_dict() -> None:
    with pytest.raises(ModelPinError, match="must be a dict"):
        pin_from_dict("not a dict")  # type: ignore[arg-type]


def test_pin_from_dict_re_validates_run_id_empty() -> None:
    """Symmetric with capture_pin: empty run_id is rejected."""
    with pytest.raises(ModelPinError, match="run_id"):
        pin_from_dict(
            {
                "pin_schema_version": "v4",
                "run_id": "",
                "captured_at": 0.0,
                "llm_models": {"generator": "m"},
                "llm_providers": {"generator": "openrouter"},
            }
        )


def test_pin_from_dict_re_validates_run_id_whitespace() -> None:
    with pytest.raises(ModelPinError, match="run_id"):
        pin_from_dict(
            {
                "pin_schema_version": "v4",
                "run_id": "   ",
                "captured_at": 0.0,
                "llm_models": {"generator": "m"},
                "llm_providers": {"generator": "openrouter"},
            }
        )


def test_pin_from_dict_re_validates_models_empty() -> None:
    with pytest.raises(ModelPinError, match="llm_models"):
        pin_from_dict(
            {
                "pin_schema_version": "v4",
                "run_id": "r",
                "captured_at": 0.0,
                "llm_models": {},
            }
        )


def test_pin_from_dict_re_validates_models_value_empty() -> None:
    with pytest.raises(ModelPinError, match="llm_models"):
        pin_from_dict(
            {
                "pin_schema_version": "v4",
                "run_id": "r",
                "captured_at": 0.0,
                "llm_models": {"generator": ""},
            }
        )


def test_pin_from_dict_provider_role_mismatch() -> None:
    """Provider declares a role not present in models."""
    with pytest.raises(ModelPinError, match="unknown roles"):
        pin_from_dict(
            {
                "pin_schema_version": "v4",
                "run_id": "r",
                "captured_at": 0.0,
                "llm_models": {"generator": "m"},
                "llm_providers": {
                    "generator": "openrouter",
                    "evaluator": "openrouter",  # not in models
                },
            }
        )


def test_pin_from_dict_provider_missing_role() -> None:
    """Every model role must have a provider on disk (no auto-fill
    on load — we require pins captured via capture_pin to be
    fully formed)."""
    with pytest.raises(ModelPinError, match="missing roles"):
        pin_from_dict(
            {
                "pin_schema_version": "v4",
                "run_id": "r",
                "captured_at": 0.0,
                "llm_models": {"generator": "m", "evaluator": "n"},
                "llm_providers": {"generator": "openrouter"},  # missing evaluator
            }
        )


def test_pin_from_dict_prompt_role_unknown() -> None:
    with pytest.raises(ModelPinError, match="prompt_version_hashes"):
        pin_from_dict(
            {
                "pin_schema_version": "v4",
                "run_id": "r",
                "captured_at": 0.0,
                "llm_models": {"generator": "m"},
                "llm_providers": {"generator": "openrouter"},
                "prompt_version_hashes": {"judge": "abc"},  # not in models
            }
        )


def test_pin_from_dict_env_snapshot_invalid_value_type() -> None:
    with pytest.raises(ModelPinError, match="env_snapshot"):
        pin_from_dict(
            {
                "pin_schema_version": "v4",
                "run_id": "r",
                "captured_at": 0.0,
                "llm_models": {"generator": "m"},
                "llm_providers": {"generator": "openrouter"},
                "env_snapshot": {"X": 123},  # int, not str
            }
        )


def test_pin_from_dict_retrieval_invalid_value() -> None:
    with pytest.raises(ModelPinError, match="retrieval_source_versions"):
        pin_from_dict(
            {
                "pin_schema_version": "v4",
                "run_id": "r",
                "captured_at": 0.0,
                "llm_models": {"generator": "m"},
                "llm_providers": {"generator": "openrouter"},
                "retrieval_source_versions": {"crossref": 1},  # int
            }
        )


def test_pin_from_json_malformed() -> None:
    with pytest.raises(ModelPinError, match="JSON decode failed"):
        pin_from_json("not even json {")


# ---------------------------------------------------------------------------
# Replay equivalence
# ---------------------------------------------------------------------------


def _baseline() -> ModelPin:
    return capture_pin(
        run_id="run_a",
        llm_models={"generator": "m"},
        captured_at=1.0,
        retrieval_source_versions={"x": "1"},
    )


def test_pins_equivalent_for_replay_true_when_config_matches() -> None:
    pin_a = capture_pin(
        run_id="run_a",
        llm_models={"generator": "m"},
        captured_at=1.0,
        retrieval_source_versions={"x": "1"},
    )
    pin_b = capture_pin(
        run_id="run_b",  # different
        llm_models={"generator": "m"},
        captured_at=2.0,  # different
        retrieval_source_versions={"x": "1"},
        notes="different notes",  # different
    )
    assert pins_equivalent_for_replay(pin_a, pin_b)


def test_pins_not_equivalent_on_model_change() -> None:
    pin_a = capture_pin(run_id="a", llm_models={"generator": "qwen/qwen3.5-plus"})
    pin_b = capture_pin(run_id="b", llm_models={"generator": "z-ai/glm-5.1"})
    assert not pins_equivalent_for_replay(pin_a, pin_b)


def test_pins_not_equivalent_on_role_addition() -> None:
    """Adding an evaluator role makes the pin non-equivalent."""
    pin_a = capture_pin(
        run_id="a", llm_models={"generator": "m"}
    )
    pin_b = capture_pin(
        run_id="b",
        llm_models={"generator": "m", "evaluator": "m2"},
    )
    assert not pins_equivalent_for_replay(pin_a, pin_b)


def test_pins_not_equivalent_on_provider_change() -> None:
    pin_a = capture_pin(
        run_id="a",
        llm_models={"generator": "m"},
        llm_providers={"generator": "openrouter"},
    )
    pin_b = capture_pin(
        run_id="b",
        llm_models={"generator": "m"},
        llm_providers={"generator": "direct"},
    )
    assert not pins_equivalent_for_replay(pin_a, pin_b)


def test_pins_not_equivalent_on_inductor_change() -> None:
    pin_a = capture_pin(
        run_id="a",
        llm_models={"generator": "m"},
        inductor_profile_text="profile-v1",
    )
    pin_b = capture_pin(
        run_id="b",
        llm_models={"generator": "m"},
        inductor_profile_text="profile-v2",
    )
    assert not pins_equivalent_for_replay(pin_a, pin_b)


def test_pins_not_equivalent_on_retrieval_source_change() -> None:
    pin_a = capture_pin(
        run_id="a",
        llm_models={"generator": "m"},
        retrieval_source_versions={"crossref": "v1"},
    )
    pin_b = capture_pin(
        run_id="b",
        llm_models={"generator": "m"},
        retrieval_source_versions={"crossref": "v2"},
    )
    assert not pins_equivalent_for_replay(pin_a, pin_b)


def test_pins_not_equivalent_on_per_role_prompt_change() -> None:
    pin_a = capture_pin(
        run_id="a",
        llm_models={"generator": "m"},
        role_prompts={"generator": "p1"},
    )
    pin_b = capture_pin(
        run_id="b",
        llm_models={"generator": "m"},
        role_prompts={"generator": "p2"},
    )
    assert not pins_equivalent_for_replay(pin_a, pin_b)


def test_pins_not_equivalent_on_env_snapshot_change() -> None:
    pin_a = capture_pin(
        run_id="a",
        llm_models={"generator": "m"},
        env_snapshot={"OPENROUTER_PROVIDER_ORDER": "a,b"},
    )
    pin_b = capture_pin(
        run_id="b",
        llm_models={"generator": "m"},
        env_snapshot={"OPENROUTER_PROVIDER_ORDER": "b,a"},  # reversed
    )
    assert not pins_equivalent_for_replay(pin_a, pin_b)


def test_pins_not_equivalent_when_env_var_unset_vs_empty() -> None:
    """v4 None-vs-empty distinction must propagate into replay
    equivalence: a pin that captured None (var unset) and a pin
    that captured "" (var set to "") are NOT replay-equivalent.
    Phase 2 must take different actions for each."""
    pin_unset = capture_pin(
        run_id="a",
        llm_models={"generator": "m"},
        env_snapshot={"PG_NLI_CONTEXT_WINDOW": None},
    )
    pin_empty = capture_pin(
        run_id="b",
        llm_models={"generator": "m"},
        env_snapshot={"PG_NLI_CONTEXT_WINDOW": ""},
    )
    assert not pins_equivalent_for_replay(pin_unset, pin_empty)


def test_pins_not_equivalent_on_schema_version_change() -> None:
    pin_a = capture_pin(run_id="a", llm_models={"generator": "m"})
    # Synthesize a different schema-version pin via dataclass replace
    # (frozen but replace returns new instance).
    pin_b = replace(pin_a, pin_schema_version="v99")
    assert not pins_equivalent_for_replay(pin_a, pin_b)


# ---------------------------------------------------------------------------
# Validation set hashing integration
# ---------------------------------------------------------------------------


def test_capture_pin_with_validation_set_hash(tmp_path: Path) -> None:
    vs_path = tmp_path / "vs.yaml"
    vs_path.write_text("in_scope: []\n", encoding="utf-8")
    pin = capture_pin(
        run_id="r",
        llm_models={"generator": "m"},
        validation_set_path=vs_path,
    )
    assert len(pin.validation_set_hash or "") == 64


def test_validation_set_hash_changes_on_content_change(
    tmp_path: Path,
) -> None:
    vs1 = tmp_path / "vs1.yaml"
    vs1.write_text("in_scope: []\n", encoding="utf-8")
    vs2 = tmp_path / "vs2.yaml"
    vs2.write_text("in_scope: [{case_id: x, query: q}]\n", encoding="utf-8")

    pin1 = capture_pin(
        run_id="a",
        llm_models={"generator": "m"},
        validation_set_path=vs1,
    )
    pin2 = capture_pin(
        run_id="b",
        llm_models={"generator": "m"},
        validation_set_path=vs2,
    )
    assert pin1.validation_set_hash != pin2.validation_set_hash
    assert not pins_equivalent_for_replay(pin1, pin2)


# ---------------------------------------------------------------------------
# JSON shape sanity
# ---------------------------------------------------------------------------


def test_json_shape_includes_v4_fields() -> None:
    pin = capture_pin(
        run_id="r",
        llm_models={"generator": "m"},
        env_snapshot={"OPENROUTER_BASE_URL": "https://example/api"},
    )
    text = pin_to_json(pin)
    parsed = json.loads(text)
    assert parsed["pin_schema_version"] == "v4"
    assert parsed["llm_models"] == {"generator": "m"}
    assert parsed["llm_providers"] == {"generator": "openrouter"}
    assert parsed["env_snapshot"]["OPENROUTER_BASE_URL"] == "https://example/api"
