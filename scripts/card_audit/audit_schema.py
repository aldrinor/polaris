"""Re-export the audit schema from its canonical home `src/schemas/evidence_card_audit.py`.

The plan pins the schema at that path, but the `src/schemas/` package carries a stale `__init__.py`
(it imports a POLARIS `phase_models` module that does not exist in this worktree). Importing the schema
through the package would execute that broken init, so we load the schema file DIRECTLY by path and
re-export its public names. One line changes if the package init is ever repaired: this file goes away.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_SCHEMA_PATH = Path(__file__).resolve().parents[2] / 'src' / 'schemas' / 'evidence_card_audit.py'
_spec = importlib.util.spec_from_file_location('evidence_card_audit_schema', _SCHEMA_PATH)
_mod = importlib.util.module_from_spec(_spec)
assert _spec and _spec.loader
# register BEFORE exec so @dataclass can resolve the module's namespace (dataclasses reads
# sys.modules[cls.__module__] to detect KW_ONLY/ClassVar sentinels).
sys.modules[_spec.name] = _mod
_spec.loader.exec_module(_mod)

globals().update({k: getattr(_mod, k) for k in dir(_mod) if not k.startswith('_')})
