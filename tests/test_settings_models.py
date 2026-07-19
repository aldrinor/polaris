"""Characterization test: ModelSettings resolves byte-identically to the current os.getenv behaviour.

Locks TODAY's resolution so the config migration is provably behaviour-preserving:
  * UNSET  -> the field equals ``os.getenv(KEY, default)`` (the exact current default),
  * SET    -> the field equals the env value (override honoured),
  * EMPTY  -> the field matches ``os.getenv``'s empty-string semantics.
"""

from __future__ import annotations

import os

from src.polaris_graph.settings import MODEL_KEY_DEFAULTS, ModelSettings


def test_unset_matches_getenv_default(monkeypatch):
    for key in MODEL_KEY_DEFAULTS:
        monkeypatch.delenv(key, raising=False)
    s = ModelSettings()
    for key, (field, default) in MODEL_KEY_DEFAULTS.items():
        assert getattr(s, field) == os.getenv(key, default), f"unset resolution differs for {key}"


def test_env_override_is_honoured(monkeypatch):
    for key in MODEL_KEY_DEFAULTS:
        monkeypatch.setenv(key, f"OVERRIDE::{key}")
    s = ModelSettings()
    for key, (field, _default) in MODEL_KEY_DEFAULTS.items():
        assert getattr(s, field) == os.getenv(key), f"override not honoured for {key}"


def test_empty_string_matches_getenv(monkeypatch):
    # os.getenv returns "" for an explicitly-empty var; ModelSettings must not silently coerce it.
    for key in MODEL_KEY_DEFAULTS:
        monkeypatch.setenv(key, "")
    s = ModelSettings()
    for key, (field, _default) in MODEL_KEY_DEFAULTS.items():
        assert getattr(s, field) == os.getenv(key), f"empty-string resolution differs for {key}"


def test_registry_matches_fields():
    # every registry entry maps to a real field, and the declared default equals the field default
    s = ModelSettings()  # env may be set in this process; only assert the field exists + is str|None
    for key, (field, default) in MODEL_KEY_DEFAULTS.items():
        assert hasattr(s, field), f"{key} -> missing field {field}"
        assert default is None or isinstance(default, str)


def test_fresh_read_reflects_env_change_like_getenv(monkeypatch):
    """get_model_settings() reads CURRENT env each call — byte-identical to os.getenv semantics."""
    from src.polaris_graph.settings import get_model_settings
    monkeypatch.delenv("PG_JUDGE_MODEL", raising=False)
    assert get_model_settings().judge_model == "qwen/qwen3.6-35b-a3b"
    monkeypatch.setenv("PG_JUDGE_MODEL", "override/model")
    assert get_model_settings().judge_model == "override/model"


def test_cached_instance_is_a_snapshot_use_accessor(monkeypatch):
    """A cached instance snapshots env (documented). The fresh accessor is the migration target."""
    from src.polaris_graph.settings import get_model_settings
    monkeypatch.delenv("PG_JUDGE_MODEL", raising=False)
    cached = ModelSettings()
    monkeypatch.setenv("PG_JUDGE_MODEL", "override/model")
    assert cached.judge_model == "qwen/qwen3.6-35b-a3b"
    assert get_model_settings().judge_model == "override/model"
