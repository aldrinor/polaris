"""Serialize AuditIR (frozen dataclasses + MappingProxyType + Path) into JSON.

`dataclasses.asdict()` does an internal `deepcopy` that fails on
`MappingProxyType`. We walk the structure manually instead, which also
avoids unnecessary copies for the read-only IR.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping


def _coerce(value: Any) -> Any:
    """Recursively coerce IR-specific types to JSON-friendly equivalents."""
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (MappingProxyType, dict, Mapping)):
        return {str(k): _coerce(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_coerce(v) for v in value]
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {
            f.name: _coerce(getattr(value, f.name))
            for f in dataclasses.fields(value)
        }
    return value


def to_json_dict(ir_object: Any) -> Any:
    """Convert an AuditIR (or any frozen dataclass) into a JSON-safe dict."""
    return _coerce(ir_object)
