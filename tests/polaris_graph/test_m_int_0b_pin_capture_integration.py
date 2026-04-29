"""M-INT-0b — Pin capture on every sweep run + --replay-from-pin CLI.

Acceptance bar (per docs/full_online_plan_FINAL.md M-INT-0b):
  1. Substrate IS imported by scripts/run_honest_sweep_r3.py
     (capture_pin, build_replay_plan, apply_replay_plan, etc.)
  2. Substrate IS invoked at run-loop callsite (_capture_run_pin
     called after each run_one_query)
  3. Run-log evidence: model_pin.json written to run_dir; valid
     ModelPin shape; round-trips through pin_from_json
  4. PG_CAPTURE_PIN=0 actually disables the write
  5. --replay-from-pin CLI loads + applies pin's env snapshot
"""

from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path

import pytest


# Ensure repo root is on sys.path for `scripts.` import.
_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))


# ---------------------------------------------------------------------------
# Acceptance bar #1 — substrate IS imported
# ---------------------------------------------------------------------------


def test_sweep_module_imports_pin_substrates() -> None:
    sweep = importlib.import_module("scripts.run_honest_sweep_r3")
    assert hasattr(sweep, "capture_pin")
    assert hasattr(sweep, "pin_from_json")
    assert hasattr(sweep, "pin_to_json")
    assert hasattr(sweep, "build_replay_plan")
    assert hasattr(sweep, "apply_replay_plan")
    assert hasattr(sweep, "DEFAULT_REPLAY_ENV_VARS")


def test_sweep_module_exposes_capture_helper() -> None:
    sweep = importlib.import_module("scripts.run_honest_sweep_r3")
    assert callable(sweep._capture_run_pin)


# ---------------------------------------------------------------------------
# Acceptance bar #2/#3 — capture writes valid pin
# ---------------------------------------------------------------------------


def test_capture_run_pin_writes_pin_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENROUTER_DEFAULT_MODEL", "test/model-x")
    monkeypatch.setenv("PG_CAPTURE_PIN", "1")
    sweep = importlib.import_module("scripts.run_honest_sweep_r3")
    run_dir = tmp_path / "run1"
    run_dir.mkdir()

    pin_path = sweep._capture_run_pin(
        "TEST_RUN_001", run_dir, notes="unit test",
    )
    assert pin_path is not None
    assert pin_path.exists()
    assert pin_path.name == "model_pin.json"
    text = pin_path.read_text(encoding="utf-8")
    pin = sweep.pin_from_json(text)
    assert pin.run_id == "TEST_RUN_001"
    assert pin.llm_models["generator"] == "test/model-x"
    assert pin.notes == "unit test"


def test_capture_run_pin_uses_default_replay_env_vars(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """env_snapshot should contain the keys from DEFAULT_REPLAY_ENV_VARS
    (None for unset, str for set)."""
    monkeypatch.setenv("OPENROUTER_DEFAULT_MODEL", "test/model")
    monkeypatch.setenv("PG_CAPTURE_PIN", "1")
    sweep = importlib.import_module("scripts.run_honest_sweep_r3")
    run_dir = tmp_path / "run2"
    run_dir.mkdir()

    pin_path = sweep._capture_run_pin("TEST_RUN_002", run_dir)
    assert pin_path is not None
    pin = sweep.pin_from_json(pin_path.read_text(encoding="utf-8"))
    # OPENROUTER_DEFAULT_MODEL is in DEFAULT_REPLAY_ENV_VARS,
    # so its value should be captured.
    assert "OPENROUTER_DEFAULT_MODEL" in pin.env_snapshot
    assert pin.env_snapshot["OPENROUTER_DEFAULT_MODEL"] == "test/model"


# ---------------------------------------------------------------------------
# Acceptance bar #4 — PG_CAPTURE_PIN=0 disables
# ---------------------------------------------------------------------------


def test_disabled_flag_skips_pin_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENROUTER_DEFAULT_MODEL", "test/model")
    monkeypatch.setenv("PG_CAPTURE_PIN", "0")
    sweep = importlib.import_module("scripts.run_honest_sweep_r3")
    run_dir = tmp_path / "run3"
    run_dir.mkdir()
    result = sweep._capture_run_pin("TEST_RUN_003", run_dir)
    assert result is None
    assert not (run_dir / "model_pin.json").exists()


def test_default_value_records(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """PG_CAPTURE_PIN unset defaults to capturing."""
    monkeypatch.delenv("PG_CAPTURE_PIN", raising=False)
    monkeypatch.setenv("OPENROUTER_DEFAULT_MODEL", "test/model")
    sweep = importlib.import_module("scripts.run_honest_sweep_r3")
    run_dir = tmp_path / "run4"
    run_dir.mkdir()
    pin_path = sweep._capture_run_pin("TEST_RUN_004", run_dir)
    assert pin_path is not None
    assert pin_path.exists()


# ---------------------------------------------------------------------------
# Capture failure does NOT raise
# ---------------------------------------------------------------------------


def test_capture_failure_does_not_raise(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Per LAW II + FINAL_PLAN risk #3: pin capture failure must
    not gate the sweep result."""
    monkeypatch.setenv("PG_CAPTURE_PIN", "1")
    monkeypatch.setenv("OPENROUTER_DEFAULT_MODEL", "test/model")
    sweep = importlib.import_module("scripts.run_honest_sweep_r3")

    def _raising_capture(*args, **kwargs):
        raise RuntimeError("simulated capture failure")

    monkeypatch.setattr(sweep, "capture_pin", _raising_capture)
    run_dir = tmp_path / "run_fail"
    run_dir.mkdir()
    # Should NOT raise; should return None.
    result = sweep._capture_run_pin("TEST_RUN_FAIL", run_dir)
    assert result is None
    assert not (run_dir / "model_pin.json").exists()


# ---------------------------------------------------------------------------
# Acceptance bar #5 — --replay-from-pin loads + applies pin
# ---------------------------------------------------------------------------


def test_replay_from_pin_round_trip(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Capture a pin, load it back, build replay plan, apply it.
    The plan should set OPENROUTER_DEFAULT_MODEL back to the
    captured value."""
    monkeypatch.setenv("PG_CAPTURE_PIN", "1")
    monkeypatch.setenv("OPENROUTER_DEFAULT_MODEL", "model-A")
    sweep = importlib.import_module("scripts.run_honest_sweep_r3")
    run_dir = tmp_path / "run_capture"
    run_dir.mkdir()
    pin_path = sweep._capture_run_pin("TEST_REPLAY", run_dir)
    assert pin_path is not None

    # Now change env, then apply_replay_plan should restore it.
    monkeypatch.setenv("OPENROUTER_DEFAULT_MODEL", "model-B-different")
    pin = sweep.pin_from_json(pin_path.read_text(encoding="utf-8"))
    plan = sweep.build_replay_plan(pin)
    with sweep.apply_replay_plan(plan):
        # Inside the context, env restored to captured value.
        assert os.environ["OPENROUTER_DEFAULT_MODEL"] == "model-A"
    # Outside the context, env is restored to pre-replay value.
    assert os.environ["OPENROUTER_DEFAULT_MODEL"] == "model-B-different"


def test_replay_invalid_pin_path_returns_error_code(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys,
) -> None:
    """--replay-from-pin <bad path> should print error and return 2."""
    monkeypatch.setenv("OPENROUTER_DEFAULT_MODEL", "test/model")
    monkeypatch.setattr(
        sys, "argv",
        ["run_honest_sweep_r3.py",
         "--replay-from-pin", str(tmp_path / "nope.json"),
         "--out-root", str(tmp_path / "out"),
         "--only", "doesnt_exist_either"],
    )
    sweep = importlib.import_module("scripts.run_honest_sweep_r3")
    import asyncio
    rc = asyncio.run(sweep.main_async())
    assert rc == 2
    captured = capsys.readouterr()
    assert "ERROR: --replay-from-pin path not found" in captured.out


def test_replay_malformed_pin_returns_error_code(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys,
) -> None:
    """--replay-from-pin <malformed file> should print error and return 2."""
    bad = tmp_path / "bad.json"
    bad.write_text("{not valid pin json}", encoding="utf-8")
    monkeypatch.setenv("OPENROUTER_DEFAULT_MODEL", "test/model")
    monkeypatch.setattr(
        sys, "argv",
        ["run_honest_sweep_r3.py",
         "--replay-from-pin", str(bad),
         "--out-root", str(tmp_path / "out"),
         "--only", "doesnt_exist_either"],
    )
    sweep = importlib.import_module("scripts.run_honest_sweep_r3")
    import asyncio
    rc = asyncio.run(sweep.main_async())
    assert rc == 2
    captured = capsys.readouterr()
    assert "malformed pin" in captured.out
