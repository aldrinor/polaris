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
    """Recursively coerce IR-specific types to JSON-friendly equivalents.

    Codex M-2 review fix #4: raises TypeError on unsupported leaf types
    rather than silently passing them through. This catches future fragility
    if the IR gains datetime/Enum/Decimal-like fields without an explicit
    coercion path.
    """
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
    raise TypeError(
        f"Unsupported leaf type for AuditIR serialization: "
        f"{type(value).__name__}; add an explicit coercion in serializer._coerce"
    )


def to_json_dict(ir_object: Any) -> Any:
    """Convert an AuditIR (or any frozen dataclass) into a JSON-safe dict."""
    return _coerce(ir_object)
