"""GH #1259 (FIX B) — POST-FETCH checkpoint for resume-from-nearest durability.

The honest-sweep pipeline has ONE checkpoint today: F04 ``corpus_snapshot.json``
(``corpus_snapshot.py``), written at the single pre-GENERATION seam — AFTER STORM +
fetch + every merge lane AND after the slow embedding-rerank / evidence selection. A
run killed DURING fetch or DURING the embedding-rerank (the costliest, network- and
CPU-bound stretch) lands BEFORE that single late checkpoint, so a 72-minute run is
lost entirely and ``--resume`` has nothing to reload.

This module adds the highest-value EARLIER checkpoint: it persists the RAW FETCHED
CORPUS at the post-fetch / post-merge seam — after ``run_live_retrieval`` returns and
the additive deepener/agentic/STORM merge lanes have folded in, but BEFORE the
embedding-rerank + ``select_evidence_for_generation``. On ``--resume`` the caller
reconstructs ``retrieval`` from this snapshot, SKIPS STORM + fetch + every merge lane,
and RE-RUNS the embedding-rerank + selection + generation on the reloaded corpus.

RESUME-FROM-NEAREST: the two checkpoints form a stage order
    post-fetch (fetch_snapshot)  <  post-selection (corpus_snapshot).
The runner prefers the LATER checkpoint when both exist (it skips strictly more work);
it falls back to the earlier fetch_snapshot when only that one was written (the kill
landed before selection completed). The two modules are independent files with
independent schema versions; this one is intentionally NARROWER (no ``evidence_for_gen``,
since selection has not run yet).

HARD INVARIANT (CLAUDE.md §-1.3, ABSOLUTE — enforced by design here):
    A checkpoint carries DATA, NEVER A VERDICT.
    The snapshot stores ONLY the retrieved/merged EVIDENCE corpus (classified sources +
    evidence rows as plain dict data) and the retrieval COUNTS for the manifest
    envelope. It stores NO faithfulness verdict, NO strict_verify result, NO
    NLI/4-role/D8 decision, NO "verified" flag, NO selected/billed pool (selection has
    not happened). On ``--resume`` the caller RE-RUNS selection + strict_verify / NLI /
    4-role / D8 on this DATA from scratch — exactly as a fresh run does. Restoring a
    cached faithfulness verdict would be a RELAXATION of the only hard gate and is an
    auto-P0; this module makes that impossible by never serializing a verdict.

The snapshot is a plain JSON document (schema_version pinned) so it is human-auditable
and forward/backward inspectable. The retrieval payload shape is IDENTICAL to the one
``corpus_snapshot._retrieval_payload`` writes, so ``corpus_snapshot.reconstruct_retrieval``
rebuilds the ``LiveRetrievalResult`` from either snapshot (shared, not duplicated). No
pickle, no code execution on load.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict
from pathlib import Path
from typing import Any

# Bump on any incompatible schema change. A reload that sees a different version FAILS
# LOUD (refuses to resume) rather than silently feeding a stale-shaped corpus to the
# downstream selection — LAW II no-silent-downgrade. Independent of corpus_snapshot's
# version: the two files evolve separately.
FETCH_SNAPSHOT_SCHEMA_VERSION = 1

# The canonical post-fetch snapshot filename inside a per-query run_dir. Distinct from
# corpus_snapshot.json so resume-from-nearest can detect each stage independently.
FETCH_SNAPSHOT_FILENAME = "fetch_snapshot.json"

# Stage pointer value. Only ``post_fetch`` is persisted by this module (the seam after
# fetch + merge, before embedding-rerank/selection).
STAGE_POST_FETCH = "post_fetch"


def fetch_snapshot_path(run_dir: Path) -> Path:
    """Deterministic post-fetch snapshot location for a per-query run_dir."""
    return Path(run_dir) / FETCH_SNAPSHOT_FILENAME


def _retrieval_payload(retrieval: Any) -> dict[str, Any]:
    """Serialize the retrieval fields the resume path + manifest envelope need.

    DATA ONLY — counts + the two evidence collections. ``classified_sources`` is a list
    of flat ``CorpusSource`` dataclasses (``asdict``-safe); ``evidence_rows`` is already
    ``list[dict]``. Every count is read with a default so a partial/test retrieval object
    round-trips. NO verdict, NO gate result. Field-for-field IDENTICAL to
    ``corpus_snapshot._retrieval_payload`` so ``reconstruct_retrieval`` is shared.
    """
    # I-wire-001 W2 (#1311) P1-1: corpus_asdict omits the W2 keys at default so the
    # fetch snapshot is byte-identical when W2 OFF (kill-switch contract).
    from src.polaris_graph.nodes.corpus_approval_gate import corpus_asdict
    return {
        "classified_sources": [corpus_asdict(s) for s in getattr(retrieval, "classified_sources", []) or []],
        "evidence_rows": list(getattr(retrieval, "evidence_rows", []) or []),
        "notes": list(getattr(retrieval, "notes", []) or []),
        "counts": {
            "total_candidates_pre_filter": getattr(retrieval, "total_candidates_pre_filter", 0),
            "candidates_kept_by_scope": getattr(retrieval, "candidates_kept_by_scope", 0),
            "candidates_kept_by_offtopic": getattr(retrieval, "candidates_kept_by_offtopic", 0),
            "candidates_fetched": getattr(retrieval, "candidates_fetched", 0),
            "candidates_failed_fetch": getattr(retrieval, "candidates_failed_fetch", 0),
            "candidates_total": getattr(retrieval, "candidates_total", 0),
            "candidates_processed": getattr(retrieval, "candidates_processed", 0),
            "extraction_finding_rows": getattr(retrieval, "extraction_finding_rows", 0),
            "corpus_truncated": bool(getattr(retrieval, "corpus_truncated", False)),
        },
        "api_calls": dict(getattr(retrieval, "api_calls", {}) or {}),
    }


def save_fetch_snapshot(
    run_dir: Path,
    *,
    run_id: str,
    question: str,
    slug: str,
    domain: str,
    retrieval: Any,
    journal_metadata_sidecar: dict[str, Any] | None = None,
    stage: str = STAGE_POST_FETCH,
) -> Path:
    """Persist the post-fetch corpus snapshot. Returns the written path.

    Atomic write (temp + os.replace) so a kill DURING the snapshot write never leaves a
    truncated/half-parsed file that a later --resume would choke on.

    NOTE: there is NO ``evidence_for_gen`` argument — selection has NOT run at this seam.
    On resume the caller RE-RUNS ``select_evidence_for_generation`` on the reconstructed
    corpus. Storing a billed/selected pool here would be wrong (it does not exist yet).

    GH #1259 (Codex diff-gate P1): ``journal_metadata_sidecar`` is the MERGED per-stage
    journal-article metadata (``dict[canonical_url -> meta_entry]``) the runner builds from
    the retrieval + expansion + deepener + agentic stages just before the journal_only
    filter. It is persisted as DATA so a ``journal_only`` fetch-resume reconstructs the SAME
    metadata a fresh run had; without it the reconstructed corpus carries no sidecar and the
    journal_only filter would reject every row as ``no_journal_metadata`` and ABORT instead
    of round-tripping. This is metadata ABOUT sources (peer-review/source-type/DOI signals),
    NOT a faithfulness verdict — it carries no strict_verify / NLI / 4-role / D8 decision and
    no ``verified`` flag. It defaults empty so a non-journal_only run round-trips unchanged.
    """
    run_dir = Path(run_dir)
    payload: dict[str, Any] = {
        "schema_version": FETCH_SNAPSHOT_SCHEMA_VERSION,
        "stage": stage,
        "run_id": run_id,
        "question": question,
        "slug": slug,
        "domain": domain,
        # DATA: the raw fetched + merged retrieval corpus + counts for manifest
        # reconstruction. NO selected pool, NO verdict.
        "retrieval": _retrieval_payload(retrieval),
        # DATA: the MERGED journal-article metadata sidecar (keyed by canonical URL) so a
        # journal_only fetch-resume sees identical per-source signals to a fresh run. This
        # is source metadata, NOT a faithfulness verdict.
        "journal_metadata_sidecar": dict(journal_metadata_sidecar or {}),
    }
    path = fetch_snapshot_path(run_dir)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    os.replace(tmp, path)
    return path


class FetchSnapshotError(RuntimeError):
    """Raised when a --resume reload cannot trust the on-disk post-fetch snapshot.

    FAIL LOUD (LAW II): a corrupt/version-mismatched/empty-corpus snapshot must NOT
    silently fall back to a fresh retrieval under --resume (the operator asked to resume
    an interrupted run; a silent restart would re-bill fetch and mask the interruption).
    The caller surfaces this as a clean abort.
    """


def load_fetch_snapshot(run_dir: Path) -> dict[str, Any]:
    """Reload + validate the post-fetch snapshot for --resume. Returns the parsed payload.

    Raises FetchSnapshotError on absent / malformed / version-mismatched / empty-corpus
    snapshots so the caller fails loud instead of resuming on bad data. Returns DATA ONLY
    — the caller MUST re-run selection + every faithfulness gate on it.

    The "non-empty corpus" predicate here is ``retrieval.evidence_rows`` (NOT
    ``evidence_for_gen`` — that key does not exist in a post-fetch snapshot, by design):
    a fetch snapshot with no evidence rows is nothing to resume from.
    """
    path = fetch_snapshot_path(run_dir)
    if not path.exists():
        raise FetchSnapshotError(
            f"--resume: no post-fetch snapshot at {path} (nothing to resume; run without "
            f"--resume for a fresh run)"
        )
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise FetchSnapshotError(
            f"--resume: post-fetch snapshot at {path} is unreadable/corrupt: {exc}"
        ) from exc
    if not isinstance(payload, dict):
        raise FetchSnapshotError(f"--resume: post-fetch snapshot at {path} is not a JSON object")
    version = payload.get("schema_version")
    if version != FETCH_SNAPSHOT_SCHEMA_VERSION:
        raise FetchSnapshotError(
            f"--resume: post-fetch snapshot schema_version {version!r} != expected "
            f"{FETCH_SNAPSHOT_SCHEMA_VERSION} at {path}; refusing to resume on a stale-shaped "
            f"corpus (re-run fresh)"
        )
    # Codex diff-gate P2-2: a malformed snapshot must FAIL LOUD at LOAD (LAW II), not later
    # as a generic no-source error deep in the resume path. Validate the stage pointer is the
    # one this module writes, so a corpus_snapshot (or any other staged checkpoint) handed to
    # the post-fetch loader is rejected explicitly rather than silently mis-reconstructed.
    stage = payload.get("stage")
    if stage != STAGE_POST_FETCH:
        raise FetchSnapshotError(
            f"--resume: post-fetch snapshot at {path} has stage {stage!r} != expected "
            f"{STAGE_POST_FETCH!r}; refusing to resume on a non-post-fetch checkpoint"
        )
    retrieval = payload.get("retrieval") or {}
    if not (isinstance(retrieval, dict) and retrieval.get("evidence_rows")):
        raise FetchSnapshotError(
            f"--resume: post-fetch snapshot at {path} has an empty retrieval corpus; refusing "
            f"to resume a run with no fetched evidence"
        )
    # Codex diff-gate P2-2: also require a non-empty, well-shaped ``classified_sources`` list.
    # reconstruct_retrieval rehydrates CorpusSource(**row) from these, so each entry must be a
    # mapping; an empty/malformed list would yield a source-less corpus that the adequacy +
    # journal_only gates can only reject downstream — fail loud here instead.
    sources = retrieval.get("classified_sources")
    if not (isinstance(sources, list) and sources):
        raise FetchSnapshotError(
            f"--resume: post-fetch snapshot at {path} has an empty/malformed classified_sources; "
            f"refusing to resume a run with no source corpus"
        )
    if not all(isinstance(s, dict) for s in sources):
        raise FetchSnapshotError(
            f"--resume: post-fetch snapshot at {path} has a malformed classified_sources entry "
            f"(every source must be a JSON object); refusing to resume on corrupt source data"
        )
    return payload
