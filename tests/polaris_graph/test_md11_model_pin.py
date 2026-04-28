"""M-D11 phase 1 model-pin tests."""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from src.polaris_graph.audit_ir.model_pin import (
    ModelPin,
    ModelPinError,
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
        llm_model="qwen/qwen3.5-plus",
    )
    assert pin.run_id == "run_001"
    assert pin.llm_model == "qwen/qwen3.5-plus"
    assert pin.llm_provider == "openrouter"
    assert pin.captured_at > 0
    assert pin.prompt_version_hash == ""
    assert pin.retrieval_source_versions == {}
    assert pin.inductor_type is None
    assert pin.inductor_version_hash is None
    assert pin.validation_set_hash is None
    assert pin.notes == ""


def test_capture_pin_full() -> None:
    pin = capture_pin(
        run_id="run_002",
        llm_model="z-ai/glm-5.1",
        llm_provider="direct",
        system_prompt="You are a research router.",
        retrieval_source_versions={
            "crossref": "v1",
            "pubmed": "2024-12",
            "unpaywall": "v2",
        },
        inductor_type="LLMAugmentedInductor",
        inductor_profile_text="anchor: tirzepatide; support: t2dm",
        notes="Q1 2026 baseline",
    )
    assert pin.llm_provider == "direct"
    assert len(pin.prompt_version_hash) == 64  # SHA-256 hex
    assert pin.retrieval_source_versions["crossref"] == "v1"
    assert pin.inductor_type == "LLMAugmentedInductor"
    assert len(pin.inductor_version_hash or "") == 64
    assert pin.notes == "Q1 2026 baseline"


def test_capture_pin_rejects_empty_run_id() -> None:
    with pytest.raises(ModelPinError, match="run_id"):
        capture_pin(run_id="", llm_model="x")


def test_capture_pin_rejects_empty_model() -> None:
    with pytest.raises(ModelPinError, match="llm_model"):
        capture_pin(run_id="r", llm_model="")


def test_capture_pin_at_explicit_timestamp() -> None:
    pin = capture_pin(
        run_id="r", llm_model="m", captured_at=1700000000.0,
    )
    assert pin.captured_at == 1700000000.0


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
        llm_model="m",
        captured_at=1234567890.0,
        retrieval_source_versions={"a": "1"},
    )
    d = pin_to_dict(pin)
    pin2 = pin_from_dict(d)
    assert pin2 == pin


def test_pin_to_json_round_trips() -> None:
    pin = capture_pin(
        run_id="r2",
        llm_model="m",
        system_prompt="hello",
        inductor_profile_text="anchor: x",
    )
    text = pin_to_json(pin)
    pin2 = pin_from_json(text)
    assert pin2 == pin


def test_pin_to_json_stable_key_order() -> None:
    """Reproducible serialization: same pin → same JSON bytes."""
    pin = capture_pin(
        run_id="r3", llm_model="m", captured_at=100.0,
        retrieval_source_versions={"z": "1", "a": "2", "m": "3"},
    )
    j1 = pin_to_json(pin)
    j2 = pin_to_json(pin)
    assert j1 == j2


def test_pin_from_dict_missing_required_key() -> None:
    with pytest.raises(ModelPinError, match="missing required key"):
        pin_from_dict({"run_id": "r", "captured_at": 0.0})  # missing llm_model


def test_pin_from_dict_rejects_non_dict() -> None:
    with pytest.raises(ModelPinError, match="must be a dict"):
        pin_from_dict("not a dict")  # type: ignore[arg-type]


def test_pin_from_json_malformed() -> None:
    with pytest.raises(ModelPinError, match="JSON decode failed"):
        pin_from_json("not even json {")


# ---------------------------------------------------------------------------
# Replay equivalence
# ---------------------------------------------------------------------------


def test_pins_equivalent_for_replay_true_when_config_matches() -> None:
    pin_a = capture_pin(
        run_id="run_a", llm_model="m", captured_at=1.0,
        retrieval_source_versions={"x": "1"},
    )
    pin_b = capture_pin(
        run_id="run_b", llm_model="m", captured_at=2.0,  # different
        retrieval_source_versions={"x": "1"},
        notes="different notes",  # also different
    )
    # run_id, captured_at, notes excluded from equivalence.
    assert pins_equivalent_for_replay(pin_a, pin_b)


def test_pins_not_equivalent_on_model_change() -> None:
    pin_a = capture_pin(run_id="a", llm_model="qwen/qwen3.5-plus")
    pin_b = capture_pin(run_id="b", llm_model="z-ai/glm-5.1")
    assert not pins_equivalent_for_replay(pin_a, pin_b)


def test_pins_not_equivalent_on_inductor_change() -> None:
    pin_a = capture_pin(
        run_id="a", llm_model="m",
        inductor_profile_text="profile-v1",
    )
    pin_b = capture_pin(
        run_id="b", llm_model="m",
        inductor_profile_text="profile-v2",
    )
    assert not pins_equivalent_for_replay(pin_a, pin_b)


def test_pins_not_equivalent_on_retrieval_source_change() -> None:
    pin_a = capture_pin(
        run_id="a", llm_model="m",
        retrieval_source_versions={"crossref": "v1"},
    )
    pin_b = capture_pin(
        run_id="b", llm_model="m",
        retrieval_source_versions={"crossref": "v2"},  # version bumped
    )
    assert not pins_equivalent_for_replay(pin_a, pin_b)


def test_pins_not_equivalent_on_prompt_change() -> None:
    pin_a = capture_pin(run_id="a", llm_model="m", system_prompt="p1")
    pin_b = capture_pin(run_id="b", llm_model="m", system_prompt="p2")
    assert not pins_equivalent_for_replay(pin_a, pin_b)


# ---------------------------------------------------------------------------
# Validation set hashing integration
# ---------------------------------------------------------------------------


def test_capture_pin_with_validation_set_hash(tmp_path: Path) -> None:
    vs_path = tmp_path / "vs.yaml"
    vs_path.write_text("in_scope: []\n", encoding="utf-8")
    pin = capture_pin(
        run_id="r",
        llm_model="m",
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

    pin1 = capture_pin(run_id="a", llm_model="m", validation_set_path=vs1)
    pin2 = capture_pin(run_id="b", llm_model="m", validation_set_path=vs2)
    assert pin1.validation_set_hash != pin2.validation_set_hash
    assert not pins_equivalent_for_replay(pin1, pin2)
