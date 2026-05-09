"""I-bug-097 — log warning once on unknown PG_STRICT_VERIFY_ENTAILMENT.

Captures the failure mode: operator types e.g. `=enforced` (verb form,
not in the valid set), `_entailment_mode()` falls back to 'off', and
the gate silently disables. With this fix, the operator sees a single
WARNING line per typo string per process so they can correct it.
"""

from __future__ import annotations

import logging

import pytest

from polaris_graph.generator2 import strict_verify


@pytest.fixture(autouse=True)
def _reset_warned_set(monkeypatch):
    """Each test starts with an empty warning-dedup set so the
    dedup-across-tests does not mask test logic.
    """
    monkeypatch.setattr(
        strict_verify, "_UNKNOWN_MODE_WARNED", set(), raising=False,
    )


def _warning_records(caplog) -> list[logging.LogRecord]:
    return [r for r in caplog.records if r.levelname == "WARNING"]


def test_unknown_mode_emits_warning_once_per_process(monkeypatch, caplog):
    """Three calls with the same typo emit exactly ONE WARNING.

    I-bug-095: unknown values now fall back to the production default
    (enforce), not 'off'. The dedup invariant is unchanged.
    """
    monkeypatch.setenv("PG_STRICT_VERIFY_ENTAILMENT", "enforced")
    with caplog.at_level("WARNING", logger=strict_verify.logger.name):
        m1 = strict_verify._entailment_mode()
        m2 = strict_verify._entailment_mode()
        m3 = strict_verify._entailment_mode()
    assert m1 == m2 == m3 == "enforce", (
        "unknown value falls back to default (enforce per I-bug-095)"
    )
    warns = [r for r in _warning_records(caplog) if "unrecognized" in r.message]
    assert len(warns) == 1, (
        f"expected exactly one WARNING for repeated typo, got {len(warns)}"
    )


def test_unknown_mode_warning_includes_value(monkeypatch, caplog):
    monkeypatch.setenv("PG_STRICT_VERIFY_ENTAILMENT", "enforcd")
    with caplog.at_level("WARNING", logger=strict_verify.logger.name):
        strict_verify._entailment_mode()
    warns = [r for r in _warning_records(caplog) if "unrecognized" in r.message]
    assert len(warns) == 1
    assert "'enforcd'" in warns[0].message, (
        "WARNING must include the typo string so the operator can find it"
    )


def test_unknown_mode_different_typos_each_warn_once(monkeypatch, caplog):
    """Two distinct typo strings = two separate WARNING records (each
    emitted once). Confirms dedup is keyed on the string, not a single
    sentinel.
    """
    with caplog.at_level("WARNING", logger=strict_verify.logger.name):
        monkeypatch.setenv("PG_STRICT_VERIFY_ENTAILMENT", "enfoce")
        strict_verify._entailment_mode()
        strict_verify._entailment_mode()  # repeat - should not re-warn
        monkeypatch.setenv("PG_STRICT_VERIFY_ENTAILMENT", "warning")
        strict_verify._entailment_mode()
        strict_verify._entailment_mode()  # repeat - should not re-warn
    warns = [r for r in _warning_records(caplog) if "unrecognized" in r.message]
    assert len(warns) == 2, f"expected 2 distinct typo warnings, got {len(warns)}"
    typos_seen = {w.message for w in warns}
    assert any("'enfoce'" in m for m in typos_seen)
    assert any("'warning'" in m for m in typos_seen)


@pytest.mark.parametrize("known_value", ["off", "warn", "enforce"])
def test_known_modes_emit_no_warning(monkeypatch, caplog, known_value):
    monkeypatch.setenv("PG_STRICT_VERIFY_ENTAILMENT", known_value)
    with caplog.at_level("WARNING", logger=strict_verify.logger.name):
        result = strict_verify._entailment_mode()
    assert result == known_value
    warns = [r for r in _warning_records(caplog) if "unrecognized" in r.message]
    assert warns == [], (
        f"known mode {known_value!r} must not log unrecognized warning"
    )


def test_empty_env_emits_no_warning(monkeypatch, caplog):
    """Empty env = unset = default (enforce per I-bug-095), NOT a
    misconfiguration. No warning.
    """
    monkeypatch.setenv("PG_STRICT_VERIFY_ENTAILMENT", "")
    with caplog.at_level("WARNING", logger=strict_verify.logger.name):
        result = strict_verify._entailment_mode()
    assert result == "enforce"
    warns = [r for r in _warning_records(caplog) if "unrecognized" in r.message]
    assert warns == []


def test_unset_env_emits_no_warning(monkeypatch, caplog):
    """I-bug-095: unset env returns the production default (enforce);
    no WARNING because that's the intended default, not a typo.
    """
    monkeypatch.delenv("PG_STRICT_VERIFY_ENTAILMENT", raising=False)
    with caplog.at_level("WARNING", logger=strict_verify.logger.name):
        result = strict_verify._entailment_mode()
    assert result == "enforce"
    warns = [r for r in _warning_records(caplog) if "unrecognized" in r.message]
    assert warns == []


def test_uppercase_recognized_via_lowercase_normalization(monkeypatch, caplog):
    """`ENFORCE` is normalized to `enforce` and recognized — no warning.

    The .lower() normalization in _entailment_mode is what saves
    operators from a SHOUTING-CASE typo; without it ENFORCE would
    otherwise look like an unknown value.
    """
    monkeypatch.setenv("PG_STRICT_VERIFY_ENTAILMENT", "ENFORCE")
    with caplog.at_level("WARNING", logger=strict_verify.logger.name):
        result = strict_verify._entailment_mode()
    assert result == "enforce"
    warns = [r for r in _warning_records(caplog) if "unrecognized" in r.message]
    assert warns == []
