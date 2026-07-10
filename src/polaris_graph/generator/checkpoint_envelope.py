"""Design 6 / MASTER_EXECUTION_PLAN §5 — one shared checkpoint envelope for all 8
section-boundary checkpoints (``cp0``..``cp6`` + the terminal S7 artifacts) plus the
per-run traceability ledger ``checkpoint_index.json``.

WHY THIS MODULE EXISTS
    The sweep already writes five stage snapshots (``fetch_snapshot.json``,
    ``corpus_snapshot.json``, ``postgen_checkpoint.json``, ``postverify_checkpoint.json``,
    ``generation_snapshot.json``) but each has its OWN ad-hoc header and only two are real
    re-ENTRY points. Design 6 generalizes the seam: every section boundary writes the SAME
    envelope so (a) a resume resolver can walk one hash-chain to find where a run died and
    what is trustworthy, and (b) new boundaries (cp0 intake / cp3 baskets / cp4 outline) drop
    in without inventing a fourth header shape.

HARD INVARIANT (CLAUDE.md §-1.3, ABSOLUTE — identical to corpus_snapshot.py /
generation_snapshot.py, extended here to EVERY checkpoint):
    A checkpoint stores DATA, NEVER A VERDICT.
    The envelope ``payload`` carries stage DATA only (rows / baskets / plans / drafts /
    accounting). It stores NO faithfulness verdict at ANY nesting depth — the recursive
    forbidden-verdict-key guard runs on BOTH save (refuse to persist a leaked decision) and
    load (refuse to load one). On a ``--resume`` the caller reloads DATA and RE-RUNS every
    faithfulness gate (strict_verify / NLI / 4-role / D8 / span-grounding) from scratch. This
    module makes replaying a stored verdict structurally impossible.

FAIL-LOUD IDENTITY (LAW II — no silent downgrade):
    schema_version pin + question SHA (GATE0 identity) + flag-slate + run_config SHA. A stale
    or mismatched checkpoint REFUSES to load; it never silently degrades. Atomic write (temp +
    ``os.replace``); sorted-keys deterministic bytes so the same stage on any of the 128 cores
    produces the same sha256 (cross-core determinism check).

The envelope is a plain JSON document (no pickle, no code execution on load).
"""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Bump on any incompatible envelope-shape change. A load that sees a different version FAILS
# LOUD (refuses to resume) rather than silently feeding a stale-shaped checkpoint downstream.
ENVELOPE_SCHEMA_VERSION = 1

# The per-run traceability ledger. Append-ordered list of one entry per written checkpoint
# (section boundaries AND intra-section files). The forensic monitor and the resume resolver
# read ONLY this file to know where a run died and what is trustworthy.
CHECKPOINT_INDEX_FILENAME = "checkpoint_index.json"

# The 8 section stage ids (Design 6 §2 / MASTER_EXECUTION_PLAN §2). S7 is terminal — never a
# resumable-past point (D8 verdicts are never checkpoint-replayed), so it has no cpN envelope.
STAGE_S0_INTAKE = "s0_intake"
STAGE_S1_FETCH = "s1_fetch"
STAGE_S2_SELECT = "s2_select"
STAGE_S3_CONSOLIDATE = "s3_consolidate"
STAGE_S4_OUTLINE = "s4_outline"
STAGE_S5_COMPOSE = "s5_compose"
STAGE_S6_VERIFY = "s6_verify"

# Resume ladder order — a "nearest checkpoint" resolve picks the LATEST present stage; the
# validity matrix (run_config.assert_adjustment_valid) keys the "earliest valid entry" of each
# knob class against this same order. S7 is deliberately absent (never resumable-past).
STAGE_ORDER: tuple[str, ...] = (
    STAGE_S0_INTAKE,
    STAGE_S1_FETCH,
    STAGE_S2_SELECT,
    STAGE_S3_CONSOLIDATE,
    STAGE_S4_OUTLINE,
    STAGE_S5_COMPOSE,
    STAGE_S6_VERIFY,
)

# Canonical envelope filename per stage. cp1/cp2/cp5/cp6 have LEGACY filenames written by the
# existing ad-hoc writers (corpus_snapshot.py etc.); those files are registered into the ledger
# by ``register_legacy_snapshot`` WITHOUT rewriting the frozen writers (byte-identical OFF).
STAGE_FILENAMES: dict[str, str] = {
    STAGE_S0_INTAKE: "cp0_run_config.json",
    STAGE_S1_FETCH: "cp1_fetch_snapshot.json",
    STAGE_S2_SELECT: "cp2_corpus_snapshot.json",
    STAGE_S3_CONSOLIDATE: "cp3_basket_snapshot.json",
    STAGE_S4_OUTLINE: "cp4_outline_snapshot.json",
    STAGE_S5_COMPOSE: "cp5_generation_snapshot.json",
    STAGE_S6_VERIFY: "cp6_postverify_checkpoint.json",
}

# The legacy filename each stage's existing ad-hoc writer produces today. Registered into the
# ledger so a run that only wrote the legacy snapshots is still walkable by the resume resolver.
STAGE_LEGACY_FILENAMES: dict[str, str] = {
    STAGE_S1_FETCH: "fetch_snapshot.json",
    STAGE_S2_SELECT: "corpus_snapshot.json",
    STAGE_S5_COMPOSE: "generation_snapshot.json",
    STAGE_S6_VERIFY: "postverify_checkpoint.json",
}

# Verdict tokens a DATA-ONLY checkpoint may NEVER contain, at ANY nesting depth. The UNION of
# the two existing frozen sets (run_honest_sweep_r3._A12_FORBIDDEN_VERDICT_KEYS and
# generation_snapshot._FORBIDDEN_VERDICT_KEYS) so the shared envelope is at least as strict as
# every checkpoint it now covers. A leaked key = a smuggled decision = fail loud (§-1.3).
FORBIDDEN_VERDICT_KEYS = frozenset(
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
    """Raised when a checkpoint cannot be trusted (missing / corrupt / version-mismatched /
    identity-mismatched / verdict-leaked / broken hash-chain).

    FAIL LOUD (LAW II): a bad checkpoint must NEVER silently fall back to a fresh run or a
    silent default — the operator asked to resume; a silent restart would re-bill and mask the
    interruption. The caller surfaces this as a clean abort.
    """


def question_sha(question: str) -> str:
    """GATE0 identity digest of a research question (hex sha256 of its UTF-8 bytes)."""
    return hashlib.sha256((question or "").encode("utf-8")).hexdigest()


def _canonical_bytes(payload: dict[str, Any]) -> bytes:
    """Deterministic JSON bytes for a checkpoint (sorted keys, no ambiguous float/NaN).

    ``default=str`` matches the existing snapshot writers so a dataclass/Path round-trips the
    same way. Cross-core determinism relies on sorted keys + a trailing newline.
    """
    return (json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n").encode("utf-8")


def sha256_of_bytes(data: bytes) -> str:
    """Hex sha256 of a byte string (used for the deterministic-bytes content hash)."""
    return hashlib.sha256(data).hexdigest()


def sha256_of_file(path: Path) -> str:
    """Hex sha256 of a file's raw bytes (used to hash legacy snapshots into the ledger)."""
    path = Path(path)
    if not path.is_file():
        raise CheckpointEnvelopeError(f"cannot hash a non-existent checkpoint file: {path}")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def assert_no_verdict_keys_recursive(obj: Any, *, path: str = "<root>") -> None:
    """RECURSIVELY fail-loud if a forbidden verdict key appears at ANY nesting depth.

    Walks every dict key + every list/tuple element (a parsed JSON payload has no other
    container types, so the walk is total). Used on BOTH the save path (refuse to PERSIST a
    leaked verdict) and the load path (refuse to LOAD one).
    """
    if isinstance(obj, dict):
        leaked = sorted(FORBIDDEN_VERDICT_KEYS & set(obj.keys()))
        if leaked:
            raise CheckpointEnvelopeError(
                f"checkpoint at {path} contains FORBIDDEN verdict key(s) {leaked} — a checkpoint "
                "stores DATA ONLY (§-1.3); a resume re-runs every gate and can NEVER replay a "
                "stored decision. Refusing (recursive verdict-key guard)."
            )
        for key, value in obj.items():
            assert_no_verdict_keys_recursive(value, path=f"{path}.{key}")
    elif isinstance(obj, (list, tuple)):
        for index, value in enumerate(obj):
            assert_no_verdict_keys_recursive(value, path=f"{path}[{index}]")


def checkpoint_path(run_dir: Path, stage: str) -> Path:
    """Deterministic canonical envelope location for a stage inside a per-query run_dir."""
    if stage not in STAGE_FILENAMES:
        raise CheckpointEnvelopeError(
            f"unknown checkpoint stage {stage!r}; expected one of {sorted(STAGE_FILENAMES)}"
        )
    return Path(run_dir) / STAGE_FILENAMES[stage]


def checkpoint_index_path(run_dir: Path) -> Path:
    """Deterministic traceability-ledger location for a per-query run_dir."""
    return Path(run_dir) / CHECKPOINT_INDEX_FILENAME


def _utc_now_iso() -> str:
    """Current UTC timestamp, ISO-8601, second precision (ledger + envelope created_utc)."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def build_envelope(
    *,
    stage: str,
    run_id: str,
    slug: str,
    domain: str,
    question: str,
    payload: dict[str, Any],
    upstream_name: str | None = None,
    upstream_sha: str | None = None,
    flag_slate: dict[str, str] | None = None,
    run_config_sha: str | None = None,
    adjustments_applied: list[str] | None = None,
    created_utc: str | None = None,
) -> dict[str, Any]:
    """Assemble (but do not write) the checkpoint envelope dict for a stage.

    Fails loud if ``payload`` (or the whole envelope) smuggles a verdict key at any depth.
    ``created_utc`` is a parameter so the caller can pin a deterministic timestamp for a
    byte-determinism test; it defaults to now.
    """
    if stage not in STAGE_FILENAMES:
        raise CheckpointEnvelopeError(
            f"unknown checkpoint stage {stage!r}; expected one of {sorted(STAGE_FILENAMES)}"
        )
    if not isinstance(payload, dict):
        raise CheckpointEnvelopeError(
            f"checkpoint payload for stage {stage!r} must be a dict, got {type(payload).__name__}"
        )
    # Refuse to build an envelope around a leaked verdict (fail loud BEFORE any write).
    assert_no_verdict_keys_recursive(payload, path=f"<payload:{stage}>")
    envelope: dict[str, Any] = {
        "schema_version": ENVELOPE_SCHEMA_VERSION,
        "stage": stage,
        "run_id": str(run_id),
        "slug": str(slug),
        "domain": str(domain),
        "question": str(question),
        "question_sha": question_sha(question),
        "created_utc": created_utc or _utc_now_iso(),
        # Hash-chain: each checkpoint pins its input checkpoint's content hash.
        "upstream": {"name": upstream_name, "sha256": upstream_sha}
        if upstream_name is not None
        else None,
        # The generation/selection-affecting env flags active when written (drift = refuse).
        "flag_slate": dict(flag_slate or {}),
        # The pinned RunConfig content hash (resume refuses on RunConfig drift for run stages).
        "run_config_sha": run_config_sha,
        # Adjustment-spec sha256s folded into DOWNSTREAM config (empty on a fresh run).
        "adjustments_applied": list(adjustments_applied or []),
        # The stage DATA.
        "payload": payload,
        # EXPLICIT invariant marker so a §-1.1 auditor sees the contract on the artifact itself.
        "faithfulness_invariant": (
            "DATA ONLY; no verdict stored at any depth; a resume re-runs every faithfulness "
            "gate (strict_verify / NLI / 4-role / D8 / span-grounding) from this data."
        ),
    }
    return envelope


def save_checkpoint(
    run_dir: Path,
    *,
    stage: str,
    run_id: str,
    slug: str,
    domain: str,
    question: str,
    payload: dict[str, Any],
    upstream_stage: str | None = None,
    flag_slate: dict[str, str] | None = None,
    run_config_sha: str | None = None,
    adjustments_applied: list[str] | None = None,
    created_utc: str | None = None,
) -> tuple[Path, str]:
    """Write a stage's envelope atomically and append it to the traceability ledger.

    ``upstream_stage`` names the prior section boundary; its current on-disk content hash is
    read to pin the hash-chain. Returns (written_path, content_sha256). Atomic write (temp +
    ``os.replace``) so a kill DURING the write never leaves a half-file a later resume chokes on.

    Best-effort ledger append: the envelope is the source of truth; the ledger is a convenience
    index. A ledger write is still atomic, but a caller that only cares about the envelope bytes
    gets them regardless.
    """
    run_dir = Path(run_dir)
    upstream_name: str | None = None
    upstream_sha: str | None = None
    if upstream_stage is not None:
        upstream_name, upstream_sha = _resolve_upstream(run_dir, upstream_stage)
    envelope = build_envelope(
        stage=stage,
        run_id=run_id,
        slug=slug,
        domain=domain,
        question=question,
        payload=payload,
        upstream_name=upstream_name,
        upstream_sha=upstream_sha,
        flag_slate=flag_slate,
        run_config_sha=run_config_sha,
        adjustments_applied=adjustments_applied,
        created_utc=created_utc,
    )
    data = _canonical_bytes(envelope)
    content_sha = sha256_of_bytes(data)
    path = checkpoint_path(run_dir, stage)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)
    append_index_entry(
        run_dir,
        stage=stage,
        file=path.name,
        sha256=content_sha,
        created_utc=envelope["created_utc"],
        upstream_sha=upstream_sha,
    )
    return path, content_sha


def _resolve_upstream(run_dir: Path, upstream_stage: str) -> tuple[str, str]:
    """Find the upstream checkpoint file (canonical name first, then legacy) and hash it."""
    run_dir = Path(run_dir)
    canonical = STAGE_FILENAMES.get(upstream_stage)
    legacy = STAGE_LEGACY_FILENAMES.get(upstream_stage)
    for name in (canonical, legacy):
        if not name:
            continue
        candidate = run_dir / name
        if candidate.is_file():
            return name, sha256_of_file(candidate)
    raise CheckpointEnvelopeError(
        f"cannot pin the hash-chain: upstream stage {upstream_stage!r} has no checkpoint file in "
        f"{run_dir} (looked for {canonical!r} and {legacy!r})"
    )


def load_checkpoint(
    run_dir: Path,
    stage: str,
    *,
    expected_question_sha: str | None = None,
    expected_flag_slate: dict[str, str] | None = None,
    expected_run_config_sha: str | None = None,
) -> dict[str, Any]:
    """Reload + validate a stage envelope for a resume. Returns the parsed envelope dict.

    Fails loud on absent / corrupt / version-mismatched / verdict-leaked / identity-mismatched
    / flag-slate-drifted / run_config-drifted checkpoints. Returns DATA ONLY — the caller MUST
    re-run every faithfulness gate on ``envelope["payload"]``.
    """
    path = checkpoint_path(run_dir, stage)
    if not path.exists():
        raise CheckpointEnvelopeError(
            f"--resume: no checkpoint for stage {stage!r} at {path} (nothing to resume there)"
        )
    try:
        envelope = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CheckpointEnvelopeError(
            f"--resume: checkpoint at {path} is unreadable/corrupt: {exc}"
        ) from exc
    if not isinstance(envelope, dict):
        raise CheckpointEnvelopeError(f"--resume: checkpoint at {path} is not a JSON object")
    version = envelope.get("schema_version")
    if version != ENVELOPE_SCHEMA_VERSION:
        raise CheckpointEnvelopeError(
            f"--resume: checkpoint schema_version {version!r} != expected {ENVELOPE_SCHEMA_VERSION} "
            f"at {path}; refusing to resume on a stale-shaped checkpoint (re-run fresh)"
        )
    if envelope.get("stage") != stage:
        raise CheckpointEnvelopeError(
            f"--resume: checkpoint at {path} declares stage {envelope.get('stage')!r} but was "
            f"loaded as {stage!r}; refusing a mislabeled checkpoint"
        )
    # RECURSIVE verdict-key guard over the WHOLE envelope (payload is nested).
    assert_no_verdict_keys_recursive(envelope, path=str(path))
    if expected_question_sha is not None and envelope.get("question_sha") != expected_question_sha:
        raise CheckpointEnvelopeError(
            f"--resume: checkpoint at {path} was built for a DIFFERENT question "
            f"(question_sha {envelope.get('question_sha')!r} != active {expected_question_sha!r}); "
            "GATE0 identity mismatch — refusing to resume (a different question is a NEW run)"
        )
    if expected_flag_slate is not None:
        _assert_flag_slate_match(envelope.get("flag_slate"), expected_flag_slate, path)
    if expected_run_config_sha is not None and envelope.get("run_config_sha") != expected_run_config_sha:
        raise CheckpointEnvelopeError(
            f"--resume: checkpoint at {path} run_config_sha {envelope.get('run_config_sha')!r} != "
            f"active {expected_run_config_sha!r}; the RunConfig for an already-run stage drifted. "
            "Refusing to resume (re-run fresh, or resume from a checkpoint before the drift)."
        )
    if not isinstance(envelope.get("payload"), dict):
        raise CheckpointEnvelopeError(
            f"--resume: checkpoint at {path} has no payload dict; refusing to resume on empty data"
        )
    return envelope


def _assert_flag_slate_match(
    snapshot_slate: Any, expected: dict[str, str], path: Path
) -> None:
    """FAIL LOUD if any expected flag differs from the snapshot slate (no silent divergence)."""
    if not isinstance(snapshot_slate, dict):
        raise CheckpointEnvelopeError(
            f"--resume: checkpoint at {path} is missing its flag_slate; refusing to resume "
            "without the flag config that produced the checkpoint"
        )
    mismatches = {
        name: {"snapshot": snapshot_slate.get(name, ""), "active": value}
        for name, value in expected.items()
        if str(snapshot_slate.get(name, "")) != str(value)
    }
    if mismatches:
        raise CheckpointEnvelopeError(
            f"--resume: flag slate differs from the checkpoint at {path}: {mismatches}; a "
            "checkpoint is only a faithful input under the flag config that produced it. Refusing."
        )


def load_index(run_dir: Path) -> list[dict[str, Any]]:
    """Read the traceability ledger (append-ordered list of entries). [] if absent."""
    path = checkpoint_index_path(run_dir)
    if not path.exists():
        return []
    try:
        entries = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CheckpointEnvelopeError(
            f"checkpoint index at {path} is unreadable/corrupt: {exc}"
        ) from exc
    if not isinstance(entries, list):
        raise CheckpointEnvelopeError(f"checkpoint index at {path} is not a JSON list")
    return entries


def append_index_entry(
    run_dir: Path,
    *,
    stage: str,
    file: str,
    sha256: str,
    created_utc: str,
    upstream_sha: str | None,
    legacy: bool = False,
) -> None:
    """Append one entry to the traceability ledger (atomic rewrite of the whole list).

    De-dupes on (stage, file): a re-write of the same checkpoint replaces its prior entry in
    place (preserving order) rather than appending a duplicate — a resume that re-runs a stage
    supersedes, it does not accumulate stale rows.
    """
    run_dir = Path(run_dir)
    entries = load_index(run_dir)
    entry = {
        "stage": stage,
        "file": file,
        "sha256": sha256,
        "created_utc": created_utc,
        "upstream_sha": upstream_sha,
        "legacy": bool(legacy),
    }
    replaced = False
    for i, existing in enumerate(entries):
        if existing.get("stage") == stage and existing.get("file") == file:
            entries[i] = entry
            replaced = True
            break
    if not replaced:
        entries.append(entry)
    path = checkpoint_index_path(run_dir)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(entries, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    os.replace(tmp, path)


def register_legacy_snapshot(run_dir: Path, stage: str, *, upstream_sha: str | None = None) -> str:
    """Hash an EXISTING legacy snapshot (corpus_snapshot.json etc.) into the ledger WITHOUT
    rewriting the frozen ad-hoc writer.

    Design 6 build 1 calls for "additive cp1/cp2 migration"; the surgical, byte-identical-OFF
    realization is: the legacy writers keep writing their exact bytes, and this adapter records
    them in the traceability ledger so the resume resolver can walk them. Returns the file sha256.
    """
    run_dir = Path(run_dir)
    canonical = STAGE_FILENAMES.get(stage)
    legacy = STAGE_LEGACY_FILENAMES.get(stage)
    for name in (canonical, legacy):
        if not name:
            continue
        candidate = run_dir / name
        if candidate.is_file():
            sha = sha256_of_file(candidate)
            # created_utc from the file mtime keeps the ledger honest about when it was written.
            created = datetime.fromtimestamp(
                candidate.stat().st_mtime, tz=timezone.utc
            ).replace(microsecond=0).isoformat()
            append_index_entry(
                run_dir,
                stage=stage,
                file=name,
                sha256=sha,
                created_utc=created,
                upstream_sha=upstream_sha,
                legacy=(name == legacy and name != canonical),
            )
            return sha
    raise CheckpointEnvelopeError(
        f"register_legacy_snapshot: no file for stage {stage!r} in {run_dir}"
    )


def validate_hash_chain(run_dir: Path) -> list[dict[str, Any]]:
    """Walk the ledger in stage order; verify each entry's ``upstream_sha`` matches the prior
    present entry's ``sha256``. Returns the ordered, validated entries.

    A broken chain fails loud with the exact stage where trust ends (a §-1.1 auditor needs
    that). Entries whose ``upstream_sha`` is None (a chain root, e.g. cp0 or a legacy snapshot
    registered without an upstream) are chain roots and are not checked against a predecessor.
    """
    entries = load_index(run_dir)
    if not entries:
        return []
    order = {stage: i for i, stage in enumerate(STAGE_ORDER)}
    present = [e for e in entries if e.get("stage") in order]
    present.sort(key=lambda e: order[e["stage"]])
    prior_sha: str | None = None
    prior_stage: str | None = None
    for entry in present:
        up = entry.get("upstream_sha")
        if up is not None and prior_sha is not None and up != prior_sha:
            raise CheckpointEnvelopeError(
                f"checkpoint hash-chain BROKEN at stage {entry.get('stage')!r}: its upstream_sha "
                f"{up!r} does not match the prior stage {prior_stage!r} content sha256 {prior_sha!r}. "
                "Trust ends here — refusing to treat later checkpoints as valid."
            )
        prior_sha = entry.get("sha256")
        prior_stage = entry.get("stage")
    return present


def resolve_resume_stage(run_dir: Path, resume_from: str | None = None) -> str:
    """Pick the resume entry stage: an explicit ``resume_from`` (validated present) or the
    NEAREST (latest-present) stage in the ledger.

    Generalizes the existing "later-checkpoint-wins" rule over the 8-chain. Fails loud if the
    requested stage is absent, or if nothing is resumable.
    """
    present_stages = present_checkpoint_stages(run_dir)
    if not present_stages:
        raise CheckpointEnvelopeError(
            f"--resume: no resumable checkpoint found in {run_dir}"
        )
    if resume_from is not None:
        stage = _normalize_stage(resume_from)
        if stage not in present_stages:
            raise CheckpointEnvelopeError(
                f"--resume-from {resume_from!r} (stage {stage!r}) is not present in {run_dir}; "
                f"available: {present_stages}"
            )
        return stage
    order = {stage: i for i, stage in enumerate(STAGE_ORDER)}
    return max(present_stages, key=lambda s: order[s])


def present_checkpoint_stages(run_dir: Path) -> list[str]:
    """The stages that have a checkpoint file on disk (canonical OR legacy), in ladder order."""
    run_dir = Path(run_dir)
    present: list[str] = []
    for stage in STAGE_ORDER:
        canonical = STAGE_FILENAMES.get(stage)
        legacy = STAGE_LEGACY_FILENAMES.get(stage)
        if (canonical and (run_dir / canonical).is_file()) or (
            legacy and (run_dir / legacy).is_file()
        ):
            present.append(stage)
    return present


# Accept both a bare stage id ("s4_outline") and the "cpN" / "cpN_name" shorthand the CLI uses.
_CP_ALIASES: dict[str, str] = {}
for _stage, _fname in STAGE_FILENAMES.items():
    _cp = _fname.split("_", 1)[0]  # "cp4"
    _CP_ALIASES[_cp] = _stage
    _CP_ALIASES[_fname[: -len(".json")]] = _stage  # "cp4_outline_snapshot"
    _CP_ALIASES[_stage] = _stage


def _normalize_stage(token: str) -> str:
    """Map a CLI stage token (``s4_outline`` / ``cp4`` / ``cp4_outline``) to a canonical stage."""
    key = (token or "").strip().lower()
    # tolerate "cp4_outline" for "cp4_outline_snapshot"
    if key in _CP_ALIASES:
        return _CP_ALIASES[key]
    for cp_key, stage in _CP_ALIASES.items():
        if cp_key.startswith(key) or key.startswith(cp_key):
            return stage
    raise CheckpointEnvelopeError(
        f"--resume-from {token!r} does not name a known checkpoint stage "
        f"(expected one of {sorted(set(STAGE_FILENAMES))} or a cpN alias)"
    )
