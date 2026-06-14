"""I-arch-004 F04 (#539/#629): corpus-snapshot persistence for --resume durability.

The honest-sweep pipeline spends the bulk of its wall-clock and money in RETRIEVAL
(serper/s2/openalex discovery + fetch + tier-classification) and in the additive
deepener/agentic/STORM/saturation merge lanes. A run that is killed mid-GENERATION
(the drb_72-class ~473s blank-stream stall, an OOM, an operator Ctrl-C) currently
restarts ALL of that retrieval from zero — the F04 checkpoint gap that HARD-gates the
full Q1 certification sweep.

This module persists the EVIDENCE the generator is about to bill — the fully
constructed ``evidence_for_gen`` rows plus the ``retrieval`` corpus (classified
sources + evidence rows + the manifest-relevant retrieval counts) — at the single
pre-generation seam, AFTER selection + the saturation loop + every contract/upload
prepend, so a ``--resume`` reload skips retrieval entirely and re-enters at generation.

HARD INVARIANT (CLAUDE.md §-1.3, ABSOLUTE — enforced by design here):
    A checkpoint carries DATA, NEVER A VERDICT.
    The snapshot stores ONLY retrieved/selected EVIDENCE ROWS (dict data) and the
    retrieval COUNTS used for the manifest envelope. It stores NO faithfulness
    verdict, NO strict_verify result, NO NLI/4-role/D8 decision, NO "verified" flag.
    On ``--resume`` the caller reloads this DATA and RE-RUNS strict_verify / NLI /
    4-role / D8 on it from scratch — exactly as a fresh run does. Restoring a cached
    faithfulness verdict would be a RELAXATION of the only hard gate and is an
    auto-P0; this module makes that impossible by never serializing a verdict.

The snapshot is a plain JSON document (schema_version pinned) so it is human-
auditable and forward/backward inspectable. ``CorpusSource`` is a flat dataclass
(``asdict`` / ``CorpusSource(**d)`` round-trip); ``evidence_rows`` / ``evidence_for_gen``
are already ``list[dict]``. No pickle, no code execution on load.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict
from pathlib import Path
from typing import Any

# Bump on any incompatible schema change. A reload that sees a different version
# FAILS LOUD (refuses to resume) rather than silently feeding a stale-shaped corpus
# to the generator — LAW II no-silent-downgrade.
SNAPSHOT_SCHEMA_VERSION = 1

# The canonical snapshot filename inside a per-query run_dir.
SNAPSHOT_FILENAME = "corpus_snapshot.json"

# Stage pointer values. Only ``pre_generation`` is persisted today (the F04 spine
# seam); the constant is named so a future mid-generation stage pointer is explicit.
STAGE_PRE_GENERATION = "pre_generation"


def snapshot_path(run_dir: Path) -> Path:
    """Deterministic snapshot location for a per-query run_dir."""
    return Path(run_dir) / SNAPSHOT_FILENAME


def _retrieval_payload(retrieval: Any) -> dict[str, Any]:
    """Serialize the retrieval fields the resume path + manifest envelope need.

    DATA ONLY — counts + the two evidence collections. ``classified_sources`` is a
    list of flat ``CorpusSource`` dataclasses (``asdict``-safe); ``evidence_rows`` is
    already ``list[dict]``. Every count is read with a default so a pre-#958 / test
    retrieval object round-trips. NO verdict, NO gate result.
    """
    return {
        "classified_sources": [asdict(s) for s in getattr(retrieval, "classified_sources", []) or []],
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


def save_corpus_snapshot(
    run_dir: Path,
    *,
    run_id: str,
    question: str,
    slug: str,
    domain: str,
    evidence_for_gen: list[dict[str, Any]],
    retrieval: Any,
    section_drafts: dict[str, Any] | None = None,
    stage: str = STAGE_PRE_GENERATION,
) -> Path:
    """Persist the pre-generation corpus snapshot. Returns the written path.

    Atomic write (temp + os.replace) so a kill DURING the snapshot write never
    leaves a truncated/half-parsed file that a later --resume would choke on.

    ``section_drafts`` is the optional per-section draft layer (raw generator prose
    keyed by section heading). It carries DRAFT PROSE ONLY — never a verified flag.
    On resume the caller re-runs strict_verify on every reloaded draft; the snapshot
    cannot smuggle a cached verdict because none is stored.
    """
    run_dir = Path(run_dir)
    payload: dict[str, Any] = {
        "schema_version": SNAPSHOT_SCHEMA_VERSION,
        "stage": stage,
        "run_id": run_id,
        "question": question,
        "slug": slug,
        "domain": domain,
        # DATA: the rows the generator is about to bill (post selection + prepends).
        "evidence_for_gen": list(evidence_for_gen or []),
        # DATA: the retrieval corpus + counts for manifest reconstruction on resume.
        "retrieval": _retrieval_payload(retrieval),
        # DRAFT PROSE ONLY (re-verified on resume); default empty.
        "section_drafts": dict(section_drafts or {}),
    }
    path = snapshot_path(run_dir)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    os.replace(tmp, path)
    return path


class CorpusSnapshotError(RuntimeError):
    """Raised when a --resume reload cannot trust the on-disk snapshot.

    FAIL LOUD (LAW II): a missing/corrupt/version-mismatched snapshot must NOT
    silently fall back to a fresh retrieval under --resume (the operator asked to
    resume an interrupted run; a silent restart would re-bill retrieval and mask the
    interruption). The caller surfaces this as a clean abort.
    """


def load_corpus_snapshot(run_dir: Path) -> dict[str, Any]:
    """Reload + validate the corpus snapshot for --resume. Returns the parsed payload.

    Raises CorpusSnapshotError on absent / malformed / version-mismatched / empty-
    corpus snapshots so the caller fails loud instead of resuming on bad data.
    Returns DATA ONLY — the caller MUST re-run every faithfulness gate on it.
    """
    path = snapshot_path(run_dir)
    if not path.exists():
        raise CorpusSnapshotError(
            f"--resume: no corpus snapshot at {path} (nothing to resume; run without "
            f"--resume for a fresh run)"
        )
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CorpusSnapshotError(
            f"--resume: corpus snapshot at {path} is unreadable/corrupt: {exc}"
        ) from exc
    if not isinstance(payload, dict):
        raise CorpusSnapshotError(f"--resume: corpus snapshot at {path} is not a JSON object")
    version = payload.get("schema_version")
    if version != SNAPSHOT_SCHEMA_VERSION:
        raise CorpusSnapshotError(
            f"--resume: corpus snapshot schema_version {version!r} != expected "
            f"{SNAPSHOT_SCHEMA_VERSION} at {path}; refusing to resume on a stale-shaped "
            f"corpus (re-run fresh)"
        )
    if not payload.get("evidence_for_gen"):
        raise CorpusSnapshotError(
            f"--resume: corpus snapshot at {path} has an empty evidence_for_gen; refusing "
            f"to resume a run with no generator corpus"
        )
    return payload


def reconstruct_retrieval(payload: dict[str, Any]) -> Any:
    """Rebuild a lightweight LiveRetrievalResult from a reloaded snapshot payload.

    The reconstructed object carries the same ``classified_sources`` (rehydrated
    ``CorpusSource`` dataclasses), ``evidence_rows``, ``notes``, and retrieval counts
    the live run had at the pre-generation seam, so the downstream manifest envelope
    + adequacy/distribution re-derivation see an identical corpus. It carries NO
    verdict — gates re-run on the rows.
    """
    # Lazy imports keep this module import-light and avoid a cycle through the
    # retrieval package at module load.
    from src.polaris_graph.nodes.corpus_approval_gate import CorpusSource
    from src.polaris_graph.retrieval.live_retriever import LiveRetrievalResult

    retr = payload.get("retrieval") or {}
    counts = retr.get("counts") or {}
    sources = [
        CorpusSource(**{k: v for k, v in (row or {}).items() if k in CorpusSource.__dataclass_fields__})
        for row in (retr.get("classified_sources") or [])
    ]
    return LiveRetrievalResult(
        classified_sources=sources,
        evidence_rows=list(retr.get("evidence_rows") or []),
        total_candidates_pre_filter=int(counts.get("total_candidates_pre_filter", 0) or 0),
        candidates_kept_by_scope=int(counts.get("candidates_kept_by_scope", 0) or 0),
        candidates_kept_by_offtopic=int(counts.get("candidates_kept_by_offtopic", 0) or 0),
        candidates_fetched=int(counts.get("candidates_fetched", 0) or 0),
        candidates_failed_fetch=int(counts.get("candidates_failed_fetch", 0) or 0),
        api_calls=dict(retr.get("api_calls") or {}),
        notes=list(retr.get("notes") or []),
        corpus_truncated=bool(counts.get("corpus_truncated", False)),
        candidates_total=int(counts.get("candidates_total", 0) or 0),
        candidates_processed=int(counts.get("candidates_processed", 0) or 0),
        extraction_finding_rows=int(counts.get("extraction_finding_rows", 0) or 0),
    )
