"""I-arch-004 F24 (#1255): `resolve_max_ev_to_gen` must give a DIRECT caller the full evidence
pool (or a LOUD operator-set cap), never the hardcoded default of 20.

The pre-F24 bug: every direct entry point read `int(os.getenv("PG_LIVE_MAX_EV_TO_GEN", "20"))`.
The Gate-B cert slate overrides it to 1500, so the 20-cap was LATENT on the cert path — but a
direct / bypass / flags-OFF caller silently capped the generator at 20 rows off ANY-size corpus.
A 20-row generation off a multi-hundred-source corpus is a starved generation (CLAUDE.md §-1.3 —
a silent thinner).

These tests pin the §-1.3-compliant contract:
  * env UNSET   -> the FULL corpus (no cap; the selector keeps every row when pool<=max_rows),
  * env SET     -> the operator cap (LAW VI), with a LOUD WARNING whenever it BINDS,
  * truncation is NEVER silent.
"""

import logging

import pytest

from src.polaris_graph.retrieval.evidence_selector import (
    _MAX_EV_TO_GEN_ENV,
    resolve_max_ev_to_gen,
)


def test_env_unset_returns_full_corpus_no_silent_20_cap(monkeypatch):
    """The headline fix: env UNSET feeds the FULL pool, NOT 20."""
    monkeypatch.delenv(_MAX_EV_TO_GEN_ENV, raising=False)
    assert resolve_max_ev_to_gen(457) == 457
    assert resolve_max_ev_to_gen(4758) == 4758
    # Crucially: never silently 20.
    assert resolve_max_ev_to_gen(500) != 20


def test_env_unset_small_corpus_returns_that_size(monkeypatch):
    monkeypatch.delenv(_MAX_EV_TO_GEN_ENV, raising=False)
    assert resolve_max_ev_to_gen(7) == 7
    assert resolve_max_ev_to_gen(0) == 0


def test_env_set_is_honored_law_vi(monkeypatch):
    """An explicit operator value wins (LAW VI) — e.g. the Gate-B slate's 1500."""
    monkeypatch.setenv(_MAX_EV_TO_GEN_ENV, "1500")
    assert resolve_max_ev_to_gen(4000) == 1500
    monkeypatch.setenv(_MAX_EV_TO_GEN_ENV, "20")
    assert resolve_max_ev_to_gen(4000) == 20


def test_binding_cap_logs_loud_warning_not_silent(monkeypatch, caplog):
    """When the operator cap BINDS (cap < corpus), it must be LOUD (never a silent thinner)."""
    monkeypatch.setenv(_MAX_EV_TO_GEN_ENV, "20")
    with caplog.at_level(logging.WARNING, logger="src.polaris_graph.retrieval.evidence_selector"):
        result = resolve_max_ev_to_gen(900)
    assert result == 20
    warnings = " ".join(r.getMessage() for r in caplog.records if r.levelno >= logging.WARNING)
    assert "F24" in warnings
    assert "BINDS" in warnings
    assert "880" in warnings  # 900 - 20 dropped, named explicitly


def test_non_binding_cap_does_not_warn(monkeypatch, caplog):
    """A cap >= corpus is non-binding — keeps everything, no spurious warning."""
    monkeypatch.setenv(_MAX_EV_TO_GEN_ENV, "1500")
    with caplog.at_level(logging.WARNING, logger="src.polaris_graph.retrieval.evidence_selector"):
        result = resolve_max_ev_to_gen(300)
    assert result == 1500  # honored; selector keeps all 300 since 300 <= 1500
    assert "BINDS" not in " ".join(r.getMessage() for r in caplog.records)


def test_garbage_env_falls_back_to_full_corpus_loud(monkeypatch, caplog):
    """An unparseable cap must NOT crash and must NOT silently starve — full corpus + warn."""
    monkeypatch.setenv(_MAX_EV_TO_GEN_ENV, "not-a-number")
    with caplog.at_level(logging.WARNING, logger="src.polaris_graph.retrieval.evidence_selector"):
        result = resolve_max_ev_to_gen(640)
    assert result == 640
    assert "F24" in " ".join(r.getMessage() for r in caplog.records)


def test_negative_pool_clamps_to_zero(monkeypatch):
    monkeypatch.delenv(_MAX_EV_TO_GEN_ENV, raising=False)
    assert resolve_max_ev_to_gen(-5) == 0


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
