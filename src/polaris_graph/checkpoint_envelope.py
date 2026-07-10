"""checkpoint_envelope — one shared envelope for the 8-section checkpoint chain.

DESIGN 6 (06_checkpoint_resume_arch.md) + MASTER_EXECUTION_PLAN v2 §5. The pipeline is
8 sections S0..S7; the 7 SECTION-BOUNDARY checkpoints cp0..cp6 each carry a section's
DATA output under ONE uniform envelope, hash-chained through a per-run traceability
ledger (``checkpoint_index.json``). This module is the write/read API + the
resume-from-any-point resolver.

HARD INVARIANTS (inherited from corpus_snapshot.py / generation_snapshot.py, now uniform):
  * DATA ONLY (§-1.3 ABSOLUTE). A checkpoint stores DATA, NEVER a verdict. The recursive
    forbidden-verdict-key guard runs on BOTH save (refuse to persist a leaked verdict) and
    load (refuse to load one). A resume re-runs EVERY faithfulness gate from the reloaded
    DATA — it can never replay a stored decision.
  * FAIL-LOUD identity. schema_version pin + question_sha (GATE0) + flag_slate +
    run_config_sha. A stale / tampered / mismatched checkpoint REFUSES to load; it never
    silently degrades (LAW II).
  * Atomic write (temp + os.replace), sorted-keys deterministic bytes — the same stage on
    any core produces the same sha256 (cross-core determinism; byte-identical round-trip).
  * Best-effort write, fail-loud read: a checkpoint write failure never aborts a paid run;
    a corrupt/mismatched checkpoint never silently loads.

Resume contract (§5 / Design 6 §4): load N, adjust DOWNSTREAM only, re-run N+1..7. The
downstream adjustment is a RunConfig delta (run_config.apply_adjustment); an adjustment can
NEVER mutate a loaded checkpoint's payload — this module loads upstream DATA read-only and
the caller reconfigures the stages that re-run. Supersede-never-delete: superseded later
checkpoints move under ``superseded/<utc>/`` and are recorded in the index (traceability).

S7 (adjudicate+render) is deliberately NOT a resumable-past point: the D8 verdict is never
checkpoint-replayed. A resume at/after cp6 re-runs all of S7 as one unit.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

CHECKPOINT_SCHEMA_VERSION = 1

# The 7 section-boundary checkpoints, in pipeline order. Each: (cp_id, stage, filename).
# cp_id index == position in the chain (cp0 is the root; cpN pins cp(N-1) as upstream).
CHECKPOINT_STAGES: tuple[tuple[str, str, str], ...] = (
    ("cp0", "s0_intake", "cp0_run_config.json"),
    ("cp1", "s1_fetch", "cp1_fetch_snapshot.json"),
    ("cp2", "s2_select", "cp2_corpus_snapshot.json"),
    ("cp3", "s3_consolidate", "cp3_basket_snapshot.json"),
    ("cp4", "s4_outline", "cp4_outline_snapshot.json"),
    ("cp5", "s5_compose", "cp5_generation_snapshot.json"),
    ("cp6", "s6_verify", "cp6_postverify_checkpoint.json"),
)
_CP_IDS: tuple[str, ...] = tuple(c[0] for c in CHECKPOINT_STAGES)
_CP_TO_STAGE: dict[str, str] = {c[0]: c[1] for c in CHECKPOINT_STAGES}
_CP_TO_FILE: dict[str, str] = {c[0]: c[2] for c in CHECKPOINT_STAGES}

INDEX_FILENAME = "checkpoint_index.json"

# Verdict tokens a DATA-ONLY checkpoint may NEVER contain (mirrors the A12 forbidden set in
# generation_snapshot.py / run_honest_sweep_r3.py). Guarded RECURSIVELY at every depth.
_FORBIDDEN_VERDICT_KEYS = frozenset(
    {
        "release_outcome",
        "release_allowed",
        "released",
        "verified",
        "is_verified",
        "verified_text",
        "final_verdicts",
        "d8_decision",
        "four_role_evaluation",
        "strict_verify_result",
    }
)


class CheckpointEnvelopeError(RuntimeError):
    """A checkpoint write/read/resume error. FAIL LOUD (LAW II) — never silent."""


def cp_index(cp_id: str) -> int:
    if cp_id not in _CP_IDS:
        raise CheckpointEnvelopeError(f"unknown checkpoint id {cp_id!r} (expected {_CP_IDS})")
    return _CP_IDS.index(cp_id)


def question_sha(question: str) -> str:
    """GATE0 identity: sha256 of the exact question string."""
    return hashlib.sha256((question or "").encode("utf-8")).hexdigest()


def checkpoint_path(run_dir: Path, cp_id: str) -> Path:
    return Path(run_dir) / _CP_TO_FILE[cp_id]


def index_path(run_dir: Path) -> Path:
    return Path(run_dir) / INDEX_FILENAME


def _assert_no_verdict_keys_recursive(obj: Any, *, path: str = "<payload>") -> None:
    """Fail-loud if a forbidden verdict key appears at ANY nesting depth (dict/list walk)."""
    if isinstance(obj, dict):
        leaked = sorted(_FORBIDDEN_VERDICT_KEYS & set(obj.keys()))
        if leaked:
            raise CheckpointEnvelopeError(
                f"checkpoint payload at {path} contains FORBIDDEN verdict key(s) {leaked} — a "
                "checkpoint stores DATA ONLY (§-1.3); a resume re-runs every gate and can NEVER "
                "replay a stored decision. Refusing (recursive verdict-key guard)."
            )
        for key, value in obj.items():
            _assert_no_verdict_keys_recursive(value, path=f"{path}.{key}")
    elif isinstance(obj, (list, tuple)):
        for i, value in enumerate(obj):
            _assert_no_verdict_keys_recursive(value, path=f"{path}[{i}]")


def _now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return _sha256_bytes(Path(path).read_bytes())


# ---------------------------------------------------------------------------
# Envelope build / serialize (pure — deterministic bytes).
# ---------------------------------------------------------------------------


def build_envelope(
    *,
    cp_id: str,
    run_id: str,
    slug: str,
    domain: str,
    question: str,
    payload: dict[str, Any],
    upstream: dict[str, str] | None = None,
    flag_slate: dict[str, str] | None = None,
    run_config_sha: str | None = None,
    adjustments_applied: list[str] | None = None,
) -> dict[str, Any]:
    """Assemble the uniform envelope dict. Verdict-guards the payload (fail-loud on save)."""
    if cp_id not in _CP_IDS:
        raise CheckpointEnvelopeError(f"unknown checkpoint id {cp_id!r}")
    if not isinstance(payload, dict):
        raise CheckpointEnvelopeError(f"{cp_id}: payload must be a dict, got {type(payload).__name__}")
    _assert_no_verdict_keys_recursive(payload, path=f"{cp_id}.payload")
    return {
        "schema_version": CHECKPOINT_SCHEMA_VERSION,
        "stage": _CP_TO_STAGE[cp_id],
        "cp_id": cp_id,
        "run_id": run_id,
        "slug": slug,
        "domain": domain,
        "question": question,
        "question_sha": question_sha(question),
        "created_utc": _now_utc(),
        "upstream": dict(upstream) if upstream else None,
        "flag_slate": dict(flag_slate or {}),
        "run_config_sha": run_config_sha,
        "adjustments_applied": list(adjustments_applied or []),
        "payload": payload,
        "faithfulness_invariant": "DATA ONLY; no verdict stored; a resume re-runs every gate.",
    }


def serialize_envelope(envelope: dict[str, Any]) -> bytes:
    """Deterministic bytes for an envelope. ``created_utc`` is excluded from the SHA basis?
    No — it is part of the record. Determinism is over the SORTED-KEY JSON; two saves of the
    SAME envelope dict produce identical bytes (byte-identical round-trip)."""
    return (json.dumps(envelope, indent=2, sort_keys=True, default=str) + "\n").encode("utf-8")


# ---------------------------------------------------------------------------
# Save / load.
# ---------------------------------------------------------------------------


def save_checkpoint(
    run_dir: Path,
    *,
    cp_id: str,
    run_id: str,
    slug: str,
    domain: str,
    question: str,
    payload: dict[str, Any],
    flag_slate: dict[str, str] | None = None,
    run_config_sha: str | None = None,
    adjustments_applied: list[str] | None = None,
    upstream_cp: str | None = None,
) -> Path:
    """Write cp_id's checkpoint (atomic) + append the traceability index entry.

    The upstream link is pinned automatically: for cp_id != cp0 the highest existing
    checkpoint strictly below cp_id (per the on-disk index) is pinned by {name, sha256}.
    Pass ``upstream_cp`` to override the auto-pin (e.g. a section that legitimately skips a
    prior intra checkpoint). cp0 has no upstream (it is the chain root).
    """
    run_dir = Path(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)

    upstream: dict[str, str] | None = None
    if cp_index(cp_id) > 0:
        prev_cp = upstream_cp or _latest_present_below(run_dir, cp_id)
        if prev_cp is not None:
            prev_path = checkpoint_path(run_dir, prev_cp)
            if prev_path.exists():
                upstream = {"cp_id": prev_cp, "name": _CP_TO_FILE[prev_cp],
                            "sha256": sha256_file(prev_path)}

    envelope = build_envelope(
        cp_id=cp_id, run_id=run_id, slug=slug, domain=domain, question=question,
        payload=payload, upstream=upstream, flag_slate=flag_slate,
        run_config_sha=run_config_sha, adjustments_applied=adjustments_applied,
    )
    data = serialize_envelope(envelope)
    path = checkpoint_path(run_dir, cp_id)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)

    _append_index_entry(run_dir, {
        "cp_id": cp_id,
        "stage": _CP_TO_STAGE[cp_id],
        "file": _CP_TO_FILE[cp_id],
        "sha256": _sha256_bytes(data),
        "created_utc": envelope["created_utc"],
        "upstream_cp": (upstream or {}).get("cp_id"),
        "upstream_sha": (upstream or {}).get("sha256"),
        "event": "write",
    })
    return path


def load_checkpoint(
    run_dir: Path,
    cp_id: str,
    *,
    expected_question_sha: str | None = None,
    active_flag_slate: dict[str, str] | None = None,
    verify_index_sha: bool = True,
) -> dict[str, Any]:
    """Reload + fail-loud-validate cp_id's checkpoint. Returns the parsed ENVELOPE.

    Validations (all FAIL LOUD):
      * file exists + parses;
      * schema_version pin matches;
      * stage matches cp_id;
      * recursive verdict-key guard (refuse to LOAD a leaked verdict);
      * question_sha matches ``expected_question_sha`` when given (GATE0 identity);
      * flag_slate matches ``active_flag_slate`` when given (no silent divergence);
      * on-disk sha256 matches the index's recorded sha256 when ``verify_index_sha`` and an
        index exists (tamper detection).
    Returns DATA — the caller MUST re-run every faithfulness gate on ``envelope['payload']``.
    """
    path = checkpoint_path(run_dir, cp_id)
    if not path.exists():
        raise CheckpointEnvelopeError(f"resume: no {cp_id} checkpoint at {path}")
    raw = path.read_bytes()
    try:
        envelope = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CheckpointEnvelopeError(f"resume: {cp_id} at {path} is corrupt/unreadable: {exc}") from exc
    if not isinstance(envelope, dict):
        raise CheckpointEnvelopeError(f"resume: {cp_id} at {path} is not a JSON object")
    if envelope.get("schema_version") != CHECKPOINT_SCHEMA_VERSION:
        raise CheckpointEnvelopeError(
            f"resume: {cp_id} schema_version {envelope.get('schema_version')!r} != "
            f"{CHECKPOINT_SCHEMA_VERSION}; refusing a stale-shaped checkpoint (re-run fresh)"
        )
    if envelope.get("stage") != _CP_TO_STAGE[cp_id]:
        raise CheckpointEnvelopeError(
            f"resume: {cp_id} stage {envelope.get('stage')!r} != {_CP_TO_STAGE[cp_id]!r} "
            "(wrong checkpoint at this filename)"
        )
    _assert_no_verdict_keys_recursive(envelope.get("payload"), path=f"{cp_id}.payload")
    if expected_question_sha is not None and envelope.get("question_sha") != expected_question_sha:
        raise CheckpointEnvelopeError(
            f"resume: {cp_id} question_sha mismatch (checkpoint built for a DIFFERENT question) "
            "— GATE0 blocks; a question change is a NEW run, not a resume"
        )
    if active_flag_slate is not None:
        snap = envelope.get("flag_slate") or {}
        mismatches = {k: {"snapshot": snap.get(k, ""), "active": v}
                      for k, v in active_flag_slate.items() if str(snap.get(k, "")) != str(v)}
        if mismatches:
            raise CheckpointEnvelopeError(
                f"resume: {cp_id} flag_slate differs from active {mismatches}; refusing to resume "
                "under a divergent slate (re-run fresh)"
            )
    if verify_index_sha:
        recorded = _recorded_sha(run_dir, cp_id)
        if recorded is not None and recorded != _sha256_bytes(raw):
            raise CheckpointEnvelopeError(
                f"resume: {cp_id} on-disk sha256 does not match the index record — the checkpoint "
                "was TAMPERED after write. Refusing (traceability tamper guard)."
            )
    return envelope


# ---------------------------------------------------------------------------
# Traceability index (checkpoint_index.json) + hash-chain validation.
# ---------------------------------------------------------------------------


def read_index(run_dir: Path) -> list[dict[str, Any]]:
    p = index_path(run_dir)
    if not p.exists():
        return []
    try:
        doc = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CheckpointEnvelopeError(f"checkpoint_index at {p} is corrupt: {exc}") from exc
    entries = doc.get("entries") if isinstance(doc, dict) else doc
    return list(entries or [])


def _append_index_entry(run_dir: Path, entry: dict[str, Any]) -> None:
    """Append-ordered write of one index entry (atomic rewrite of the whole ledger)."""
    entries = read_index(run_dir)
    entries.append(entry)
    p = index_path(run_dir)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(
        json.dumps({"schema_version": CHECKPOINT_SCHEMA_VERSION, "entries": entries},
                   indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    os.replace(tmp, p)


def _latest_write_entry(run_dir: Path, cp_id: str) -> dict[str, Any] | None:
    latest = None
    for e in read_index(run_dir):
        if e.get("cp_id") == cp_id and e.get("event", "write") == "write":
            latest = e
    return latest


def _recorded_sha(run_dir: Path, cp_id: str) -> str | None:
    e = _latest_write_entry(run_dir, cp_id)
    return e.get("sha256") if e else None


def _latest_present_below(run_dir: Path, cp_id: str) -> str | None:
    """Highest cp strictly below cp_id whose file exists on disk (auto upstream pin)."""
    for cand in reversed(_CP_IDS[: cp_index(cp_id)]):
        if checkpoint_path(run_dir, cand).exists():
            return cand
    return None


def present_checkpoints(run_dir: Path) -> list[str]:
    """cp_ids whose checkpoint file exists on disk, in chain order."""
    return [cp for cp in _CP_IDS if checkpoint_path(run_dir, cp).exists()]


def validate_hash_chain(run_dir: Path, up_to: str | None = None) -> list[str]:
    """Walk the on-disk checkpoint chain; FAIL LOUD at the first broken link.

    For each present checkpoint (up to ``up_to`` if given): (1) its current on-disk sha256
    matches the index record (tamper), (2) its recorded ``upstream_sha`` matches the recorded
    sha256 of the pinned upstream checkpoint (chain continuity). Returns the validated cp_id
    list. A §-1.1 auditor gets the EXACT stage where trust ends.
    """
    present = present_checkpoints(run_dir)
    if up_to is not None:
        limit = cp_index(up_to)
        present = [cp for cp in present if cp_index(cp) <= limit]
    validated: list[str] = []
    for cp in present:
        path = checkpoint_path(run_dir, cp)
        on_disk = sha256_file(path)
        entry = _latest_write_entry(run_dir, cp)
        if entry is None:
            raise CheckpointEnvelopeError(f"chain: {cp} present on disk but has no index entry")
        if entry.get("sha256") != on_disk:
            raise CheckpointEnvelopeError(
                f"chain: {cp} on-disk sha256 != index record — TAMPERED after write"
            )
        up_cp = entry.get("upstream_cp")
        if up_cp is not None:
            up_entry = _latest_write_entry(run_dir, up_cp)
            if up_entry is None:
                raise CheckpointEnvelopeError(f"chain: {cp} pins upstream {up_cp} which has no index entry")
            if entry.get("upstream_sha") != up_entry.get("sha256"):
                raise CheckpointEnvelopeError(
                    f"chain BROKEN at {cp}: pinned upstream_sha != {up_cp}'s recorded sha256 "
                    f"(upstream changed after {cp} was written; trust ends at {up_cp})"
                )
        validated.append(cp)
    return validated


# ---------------------------------------------------------------------------
# Resume resolver: pick the entry checkpoint + supersede downstream.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ResumePlan:
    """The resolved resume entry + what re-runs. DATA for the orchestrator + disclosure."""

    entry_cp: str
    entry_index: int
    rerun_stages: tuple[str, ...]  # the cp-ids whose stages re-run (entry+1 .. cp6) + S7
    validated_chain: tuple[str, ...]


def resolve_resume_point(run_dir: Path, requested: str | None = None) -> ResumePlan:
    """Pick the resume entry: ``requested`` (must be present) or the nearest (highest present).

    Validates the hash-chain up to the entry; FAIL LOUD on a broken chain or an absent
    requested checkpoint. Returns a ResumePlan describing which stages re-run.
    """
    present = present_checkpoints(run_dir)
    if not present:
        raise CheckpointEnvelopeError(f"resume: no checkpoints present in {run_dir}")
    if requested is not None:
        if requested not in _CP_IDS:
            raise CheckpointEnvelopeError(f"resume: unknown checkpoint {requested!r}")
        if requested not in present:
            raise CheckpointEnvelopeError(
                f"resume: requested {requested} is not present (have {present})"
            )
        entry = requested
    else:
        entry = present[-1]  # later-wins: the highest present checkpoint
    validated = validate_hash_chain(run_dir, up_to=entry)
    if entry not in validated:
        raise CheckpointEnvelopeError(f"resume: chain does not validate up to {entry}")
    idx = cp_index(entry)
    rerun = tuple(cp for cp in _CP_IDS if cp_index(cp) > idx)
    return ResumePlan(entry_cp=entry, entry_index=idx, rerun_stages=rerun,
                      validated_chain=tuple(validated))


def supersede_downstream(run_dir: Path, entry_cp: str, *, adjustment_sha: str | None = None) -> Path | None:
    """Supersede-never-delete: move checkpoints LATER than entry_cp under superseded/<utc>/.

    Records the supersession (with the adjustment sha) in the index. Returns the archive dir
    (or None if nothing to supersede). Full lineage stays on disk — traceability.
    """
    run_dir = Path(run_dir)
    idx = cp_index(entry_cp)
    later = [cp for cp in present_checkpoints(run_dir) if cp_index(cp) > idx]
    if not later:
        return None
    archive = run_dir / "superseded" / _now_utc().replace(":", "")
    archive.mkdir(parents=True, exist_ok=True)
    for cp in later:
        src = checkpoint_path(run_dir, cp)
        shutil.move(str(src), str(archive / _CP_TO_FILE[cp]))
        _append_index_entry(run_dir, {
            "cp_id": cp,
            "stage": _CP_TO_STAGE[cp],
            "file": str((archive / _CP_TO_FILE[cp]).relative_to(run_dir)),
            "sha256": sha256_file(archive / _CP_TO_FILE[cp]),
            "created_utc": _now_utc(),
            "upstream_cp": None,
            "upstream_sha": None,
            "event": "superseded",
            "adjustment_sha": adjustment_sha,
        })
    return archive
