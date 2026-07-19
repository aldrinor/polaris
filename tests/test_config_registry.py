"""Characterization: resolve() is byte-identical to os.getenv for every registered key."""
from __future__ import annotations

import os

import pytest

from src.polaris_graph.config_defaults import CONFIG_DEFAULTS
from src.polaris_graph.settings import resolve


def test_resolve_matches_getenv_unset(monkeypatch):
    for key, default in CONFIG_DEFAULTS.items():
        monkeypatch.delenv(key, raising=False)
        assert resolve(key) == os.getenv(key, default), f"unset {key}"


def test_resolve_matches_getenv_override(monkeypatch):
    for key, default in CONFIG_DEFAULTS.items():
        monkeypatch.setenv(key, f"OVR::{key}")
        assert resolve(key) == os.getenv(key, default) == f"OVR::{key}", f"override {key}"


def test_unregistered_key_raises():
    with pytest.raises(KeyError):
        resolve("PG_DEFINITELY_NOT_A_REGISTERED_KEY_XYZ")
