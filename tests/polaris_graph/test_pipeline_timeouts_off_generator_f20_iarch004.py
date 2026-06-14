"""I-arch-004 F20 (#1255): the STORM interview wall, the deepener LLM-op wall, and the 4-role D8
seam wall must all be SIZED OFF the generator budget — not a small flat hardcode that gets killed
by a cheap clock before a reasoning-first call finishes. Each:

  * derives ``max(<historical floor>, <multiplier?> x LIVE generator timeout)`` when its env knob
    is UNSET (so the default can only GROW above the historical floor, never regress), AND
  * honors an explicit env override outright (LAW VI), AND
  * reads the LIVE generator timeout (``set_generator_timeout_seconds``) so the Gate-B slate is
    respected, not a value frozen at import.

These cover the three WALL derivations; the per-call ``reason()`` / ``generate_structured()``
derivations are proven in test_reason_structured_timeout_f20_iarch004.py.
"""

import pytest

from src.polaris_graph.llm.openrouter_client import (
    get_generator_timeout_seconds,
    set_generator_timeout_seconds,
)
from src.polaris_graph.agents.storm_interviews import (
    _STORM_INTERVIEW_TIMEOUT_FLOOR,
    _resolve_interview_timeout,
)
from src.polaris_graph.agents.evidence_deepener import _resolve_llm_op_timeout
from scripts.run_honest_sweep_r3 import (
    _FOUR_ROLE_SEAM_TIMEOUT_FLOOR,
    _resolve_four_role_seam_timeout,
)


@pytest.fixture
def _gen_timeout_guard():
    """Restore the module-global generator timeout after a test mutates it."""
    original = get_generator_timeout_seconds()
    yield
    set_generator_timeout_seconds(original)


# ───────────────────────── STORM interview wall ─────────────────────────

def test_storm_unset_derives_generator_timeout(monkeypatch, _gen_timeout_guard):
    monkeypatch.delenv("PG_STORM_INTERVIEW_TIMEOUT", raising=False)
    set_generator_timeout_seconds(6500)
    assert _resolve_interview_timeout() == 6500  # max(300 floor, 6500) = 6500


def test_storm_floor_never_regresses_below_300(monkeypatch, _gen_timeout_guard):
    """If the generator timeout were ever set tiny, the wall still can't drop below 300s."""
    monkeypatch.delenv("PG_STORM_INTERVIEW_TIMEOUT", raising=False)
    set_generator_timeout_seconds(50)
    assert _resolve_interview_timeout() == _STORM_INTERVIEW_TIMEOUT_FLOOR == 300


def test_storm_env_override_wins(monkeypatch, _gen_timeout_guard):
    monkeypatch.setenv("PG_STORM_INTERVIEW_TIMEOUT", "450")
    set_generator_timeout_seconds(6500)
    assert _resolve_interview_timeout() == 450  # LAW VI: explicit wins outright


def test_storm_reads_live_generator_timeout(monkeypatch, _gen_timeout_guard):
    monkeypatch.delenv("PG_STORM_INTERVIEW_TIMEOUT", raising=False)
    set_generator_timeout_seconds(9000)  # simulate Gate-B slate floor
    assert _resolve_interview_timeout() == 9000


# ───────────────────────── deepener LLM-op wall ─────────────────────────

def test_deepener_unset_derives_generator_timeout(monkeypatch, _gen_timeout_guard):
    monkeypatch.delenv("PG_DEEPENER_LLM_OP_TIMEOUT", raising=False)
    set_generator_timeout_seconds(6500)
    assert _resolve_llm_op_timeout(120) == 6500  # max(120 floor, 6500)


def test_deepener_floor_never_regresses_below_op_timeout(monkeypatch, _gen_timeout_guard):
    monkeypatch.delenv("PG_DEEPENER_LLM_OP_TIMEOUT", raising=False)
    set_generator_timeout_seconds(50)
    assert _resolve_llm_op_timeout(120) == 120  # never below the passed HTTP-op floor


def test_deepener_env_override_wins(monkeypatch, _gen_timeout_guard):
    monkeypatch.setenv("PG_DEEPENER_LLM_OP_TIMEOUT", "333")
    set_generator_timeout_seconds(6500)
    assert _resolve_llm_op_timeout(120) == 333


# ───────────────────────── 4-role D8 seam wall ─────────────────────────

def test_seam_unset_derives_multiple_of_generator_timeout(monkeypatch, _gen_timeout_guard):
    monkeypatch.delenv("PG_FOUR_ROLE_SEAM_TIMEOUT_SECONDS", raising=False)
    monkeypatch.delenv("PG_FOUR_ROLE_SEAM_GEN_MULTIPLE", raising=False)
    set_generator_timeout_seconds(6500)
    # default multiple 4 x 6500 = 26000 > 7200 floor
    assert _resolve_four_role_seam_timeout() == 26000.0


def test_seam_floor_never_regresses_below_7200(monkeypatch, _gen_timeout_guard):
    monkeypatch.delenv("PG_FOUR_ROLE_SEAM_TIMEOUT_SECONDS", raising=False)
    monkeypatch.delenv("PG_FOUR_ROLE_SEAM_GEN_MULTIPLE", raising=False)
    set_generator_timeout_seconds(100)  # 4 x 100 = 400 < 7200 floor
    assert _resolve_four_role_seam_timeout() == _FOUR_ROLE_SEAM_TIMEOUT_FLOOR == 7200.0


def test_seam_env_override_wins(monkeypatch, _gen_timeout_guard):
    monkeypatch.setenv("PG_FOUR_ROLE_SEAM_TIMEOUT_SECONDS", "5000")
    set_generator_timeout_seconds(6500)
    assert _resolve_four_role_seam_timeout() == 5000.0  # explicit wins (even below the derived)


def test_seam_multiple_env_is_honored(monkeypatch, _gen_timeout_guard):
    monkeypatch.delenv("PG_FOUR_ROLE_SEAM_TIMEOUT_SECONDS", raising=False)
    monkeypatch.setenv("PG_FOUR_ROLE_SEAM_GEN_MULTIPLE", "2")
    set_generator_timeout_seconds(6500)
    assert _resolve_four_role_seam_timeout() == 13000.0  # 2 x 6500


def test_seam_bad_multiple_falls_back_to_4(monkeypatch, _gen_timeout_guard):
    monkeypatch.delenv("PG_FOUR_ROLE_SEAM_TIMEOUT_SECONDS", raising=False)
    monkeypatch.setenv("PG_FOUR_ROLE_SEAM_GEN_MULTIPLE", "garbage")
    set_generator_timeout_seconds(6500)
    assert _resolve_four_role_seam_timeout() == 26000.0  # 4 x 6500 (fallback multiple)


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
