"""S4 OUTLINE — cp4 output-boundary checkpoint (Design 5 §4 + master §5 envelope).

The S4 section boundary: ``cp3_basket_snapshot.json`` in -> ``cp4_outline_snapshot.json`` out.
This file holds the orchestrator's PRODUCT — the final section plans + the full revision audit
trail (every op, reason, round; rejected + deferred ops) + digest stats — as DATA ONLY. A
resume re-enters at section composition with these plans and RE-RUNS every faithfulness gate;
it can NEVER replay a stored decision (§-1.3 ABSOLUTE). The forbidden-verdict-key guard mirrors
``run_honest_sweep_r3.load_a12_checkpoint`` (``:6936-6974``) but recurses into nested dicts so a
verdict cannot hide inside the revision audit payload.

SEAM (WP-0a): when the shared ``generator/checkpoint_envelope.py`` (master §5) lands, the write/
load here delegate to it — this module already mirrors the §5 envelope field-for-field
(``schema_version`` / ``stage`` / ``question_sha`` / ``upstream`` hash-chain / ``flag_slate`` /
``run_config_sha`` / ``adjustments_applied`` / DATA-only payload) so that swap is a delegation,
not a schema change. Atomic write (temp + ``os.replace``), sorted-keys deterministic bytes.
Best-effort write (never abort a paid run); fail-loud read (corrupt / verdict-leaked never
silently loads — LAW II).
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Mapping, Sequence

CP4_OUTLINE_SNAPSHOT_FILENAME = "cp4_outline_snapshot.json"
CP4_SCHEMA_VERSION = 1
CP4_STAGE = "outline"

# The verdict tokens a DATA-ONLY checkpoint may NEVER contain, at ANY nesting depth.
# Mirrors _A12_FORBIDDEN_VERDICT_KEYS (run_honest_sweep_r3.py:6936) — a resume re-runs every
# gate from the reloaded DATA and can never replay a stored decision.
_CP4_FORBIDDEN_VERDICT_KEYS = frozenset(
    {
        "release_outcome",
        "release_allowed",
        "released",
        "verified",
        "is_verified",
        "final_verdicts",
        "d8_decision",
        "four_role_evaluation",
    }
)

_FAITHFULNESS_INVARIANT = (
    "DATA ONLY; no verdict/release_outcome stored anywhere in this checkpoint; a resume "
    "re-enters at section composition with these plans and MUST re-run every faithfulness "
    "gate (strict_verify / NLI / 4-role / D8) — it can never replay a stored decision."
)


def _assert_no_verdict_keys(obj: Any, path: str = "$") -> None:
    """Recursively refuse any forbidden verdict key anywhere in the payload (fail loud)."""
    if isinstance(obj, Mapping):
        leaked = sorted(_CP4_FORBIDDEN_VERDICT_KEYS & set(map(str, obj.keys())))
        if leaked:
            raise ValueError(
                f"cp4 outline checkpoint contains FORBIDDEN verdict key(s) {leaked} at {path} — "
                "a checkpoint stores DATA ONLY (§-1.3); a resume re-runs every gate and can NEVER "
                "replay a stored decision. Refusing."
            )
        for key, value in obj.items():
            _assert_no_verdict_keys(value, f"{path}.{key}")
    elif isinstance(obj, (list, tuple)):
        for idx, value in enumerate(obj):
            _assert_no_verdict_keys(value, f"{path}[{idx}]")


def build_cp4_payload(
    *,
    question_sha: str,
    upstream: Sequence[Mapping[str, str]] | None,
    run_config_sha: str,
    flag_slate: Mapping[str, str] | None,
    adjustments_applied: Sequence[Any] | None,
    final_plans: Sequence[Mapping[str, Any]],
    revision_audit: Mapping[str, Any] | None,
    digest_stats: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Assemble the cp4 payload (envelope §5 fields + DATA-only ``payload``). Rejects a verdict
    leak eagerly so a bad build fails at write time, not silently on the next resume."""
    payload = {
        "schema_version": CP4_SCHEMA_VERSION,
        "stage": CP4_STAGE,
        "question_sha": str(question_sha or ""),
        "upstream": [dict(u) for u in (upstream or [])],
        "run_config_sha": str(run_config_sha or ""),
        "flag_slate": dict(flag_slate or {}),
        "adjustments_applied": list(adjustments_applied or []),
        "payload": {
            "final_plans": [dict(p) for p in final_plans],
            "revision_audit": dict(revision_audit or {}),
            "digest_stats": dict(digest_stats or {}),
        },
        "faithfulness_invariant": _FAITHFULNESS_INVARIANT,
    }
    _assert_no_verdict_keys(payload)
    return payload


def write_cp4_outline_snapshot(run_dir: str | Path, payload: Mapping[str, Any]) -> Path | None:
    """Atomically write the cp4 snapshot (temp + ``os.replace``, sorted-keys). Best-effort:
    a write failure must NOT abort a paid run — returns None on failure. ``payload`` is validated
    for verdict leaks before any bytes hit disk."""
    try:
        _assert_no_verdict_keys(payload)
        target = Path(run_dir) / CP4_OUTLINE_SNAPSHOT_FILENAME
        tmp = target.with_suffix(target.suffix + ".tmp")
        tmp.write_text(
            json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n",
            encoding="utf-8",
        )
        os.replace(tmp, target)
        return target
    except Exception:  # noqa: BLE001 — checkpoint durability is best-effort, never a run blocker
        return None


def load_cp4_outline_snapshot(run_dir: str | Path) -> dict[str, Any] | None:
    """Load the cp4 snapshot as DATA ONLY. Returns None if absent. Fail-loud: corrupt JSON, a
    non-object payload, OR any forbidden verdict key (at any depth) raises — never a silent load."""
    path = Path(run_dir) / CP4_OUTLINE_SNAPSHOT_FILENAME
    if not path.is_file():
        return None
    with path.open(encoding="utf-8") as handle:
        data = json.load(handle)  # raises on corrupt JSON -> fail loud
    if not isinstance(data, dict):
        raise ValueError(f"cp4 outline checkpoint is not a JSON object: {path}")
    _assert_no_verdict_keys(data)
    return data
