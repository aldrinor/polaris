"""Evidence Contract version migration registry (I-ecg-004).

When v2 lands, register `("1.0", "2.0"): _v1_to_v2` here. The migration
path walker chains entries; identity is short-circuited.
"""

from __future__ import annotations

from typing import Callable


class ContractMigrationError(Exception):
    """Raised when no migration path exists between two contract versions."""


MIGRATIONS: dict[tuple[str, str], Callable[[dict], dict]] = {}


def migrate_contract(raw: dict, target_version: str = "1.0") -> dict:
    """Migrate a contract dict from its declared version to target_version."""
    source = raw.get("contract_version")
    if not isinstance(source, str):
        raise ContractMigrationError(
            f"contract_version missing or non-string: {source!r}"
        )
    if source == target_version:
        return dict(raw)
    seen = {source}
    current = dict(raw)
    while current.get("contract_version") != target_version:
        cur_version = current.get("contract_version")
        next_step = next(
            (
                (frm, to, fn)
                for (frm, to), fn in MIGRATIONS.items()
                if frm == cur_version and frm != to and to not in seen
            ),
            None,
        )
        if next_step is None:
            raise ContractMigrationError(
                f"no migration path from {cur_version!r} to {target_version!r}"
            )
        _, to, fn = next_step
        current = fn(current)
        current["contract_version"] = to
        seen.add(to)
    return current
