"""Single cached loader for all ``config/authority/*`` versioned data files.

Phase 0a (GH #983). LAW VI: every threshold/weight/map/pattern the authority
model uses is loaded from versioned DATA here, never inlined in a ``.py`` file
(the S4-grep test enforces zero host/suffix literals in code).

LAW II — fail-loud: a missing / empty / unparseable data file raises
``AuthorityDataError``; the loader NEVER returns a silent default.
"""
from __future__ import annotations

import functools
import os
from pathlib import Path
from typing import Any

import yaml
from src.polaris_graph.settings import resolve


class AuthorityDataError(RuntimeError):
    """Raised when a versioned authority data file is missing/empty/unparseable."""


# Resolve config/authority/ relative to the repo root (this file lives at
# src/polaris_graph/authority/data_loader.py -> repo root is parents[3]).
_DEFAULT_DATA_DIR = Path(__file__).resolve().parents[3] / "config" / "authority"


def _data_dir() -> Path:
    """Data dir, overridable via env for tests (LAW VI — no hardcode)."""
    override = resolve("PG_AUTHORITY_DATA_DIR")
    return Path(override) if override else _DEFAULT_DATA_DIR


def _require_file(name: str) -> Path:
    path = _data_dir() / name
    if not path.exists():
        raise AuthorityDataError(
            f"authority data file missing: {path} "
            f"(set PG_AUTHORITY_DATA_DIR or ship config/authority/{name})"
        )
    if path.stat().st_size == 0:
        raise AuthorityDataError(f"authority data file is empty: {path}")
    return path


def _load_yaml(name: str) -> dict[str, Any]:
    path = _require_file(name)
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise AuthorityDataError(f"authority data file unparseable: {path}: {exc}") from exc
    if not isinstance(data, dict) or not data:
        raise AuthorityDataError(f"authority data file empty/invalid mapping: {path}")
    return data


def _load_suffix_list(name: str) -> tuple[str, ...]:
    path = _require_file(name)
    suffixes: list[str] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        suffixes.append(line.lower())
    if not suffixes:
        raise AuthorityDataError(f"authority suffix list has no entries: {path}")
    # de-dup preserving order
    seen: set[str] = set()
    ordered: list[str] = []
    for s in suffixes:
        if s not in seen:
            seen.add(s)
            ordered.append(s)
    return tuple(ordered)


@functools.lru_cache(maxsize=1)
def _bundle_for_dir(data_dir: str) -> dict[str, Any]:
    """Load + cache the whole bundle for a specific data dir."""
    version_path = Path(data_dir) / "VERSION"
    if not version_path.exists() or version_path.stat().st_size == 0:
        raise AuthorityDataError(f"authority VERSION missing/empty: {version_path}")
    version = version_path.read_text(encoding="utf-8").strip()
    if not version:
        raise AuthorityDataError(f"authority VERSION blank: {version_path}")
    return {
        "version": version,
        "scholarly_weights": _load_yaml("scholarly_weights.yaml"),
        "ror_type_class_map": _load_yaml("ror_type_class_map.yaml"),
        "junk_patterns": _load_yaml("junk_patterns.yaml"),
        "recency_profile": _load_yaml("recency_profile.yaml"),
        "blend_weights": _load_yaml("blend_weights.yaml"),
        "clinical_view": _load_yaml("clinical_view.yaml"),
        "psl_gov_suffixes": _load_suffix_list("psl_gov_suffixes.txt"),
    }


def load_authority_data() -> dict[str, Any]:
    """Return the cached, validated authority data bundle (fail-loud)."""
    return _bundle_for_dir(str(_data_dir()))


def clear_cache() -> None:
    """Drop the cached bundle (tests that swap PG_AUTHORITY_DATA_DIR call this)."""
    _bundle_for_dir.cache_clear()
