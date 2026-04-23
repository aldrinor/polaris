"""M-61 (2026-04-23): V30 hybrid human/licensed completion (Path B).

V30 Report Contract Architecture Layer 4d. Codex plan review #6:
  "replace free-text-only `consent_proof` with a structured
   provenance object. Minimum fields: curator_id, source_type,
   source_locator (DOI + page range or equivalent), acquired_at,
   artifact_sha256 of the retained PDF/page image/snippet,
   artifact_retention_path or audit pointer, quote_page_range,
   attestation."

M-61 accepts operator-provided direct_quote content for entities
that M-56 couldn't retrieve (paywalled-no-OA-no-abstract). The
completion file schema REQUIRES structured provenance, not just
a free-text consent string, so a fabricated quote cannot
self-consistently pass without retained-artifact evidence.

## Two-sided interface

Input 1 (from M-60): human_gap_tasks.json — list of tasks per
curator-actionable gap entry (what M-60.compose_human_completion_tasks
emits).

Input 2 (operator-authored): human_gap_completions.json — list
of HumanCompletionRecord objects matching the task list.

M-61:
  load_completions(path) → tuple[HumanCompletionRecord, ...]
  validate_against_tasks(completions, tasks) →
    (accepted, rejected: list[tuple[record, reason]])
  to_frame_rows(accepted, contract) → tuple[FrameRow, ...]
    — produces provenance_class=HUMAN_CURATED FrameRow objects
    that integrate with the rest of the pipeline as if M-56 had
    retrieved them, but with the permanent human_curated flag.

## Fraud/fabrication defense

Per Codex review #6: `strict_verify` cannot detect a fabricated
quote that self-consistently matches its claimed source_span.
Defense-in-depth:

  1. artifact_sha256 required — references a retained file on
     the operator's system that can be independently recomputed
     and compared at audit time.
  2. artifact_retention_path required — where the retained PDF
     / page image / text snippet lives for audit retrieval.
  3. curator_id required — who asserted this.
  4. acquired_at required — when (ISO-8601).
  5. attestation required — curator's signed statement of
     licensed access.
  6. doi match with the task required — operator cannot
     substitute content from a different paper.
  7. provenance_class=HUMAN_CURATED is a PERMANENT flag on the
     FrameRow. Downstream rendering MUST surface this in the
     report's Methods section and in every citation marker.

## Entity-type-agnostic (Codex rev #7)

No branching on entity_type. statute / dft_primary / any domain
works — the completion schema is the same.

## Pure functions

All M-61 public functions are pure given their JSON / dict
inputs. I/O (reading completion files, writing FrameRows to
evidence pool) happens at the integration layer.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .frame_fetcher import FrameRow, ProvenanceClass


class CompletionSchemaError(ValueError):
    """Raised when a completion record is malformed or missing
    required provenance fields."""

    def __init__(self, record_index: int, reason: str) -> None:
        super().__init__(
            f"completion record [{record_index}] schema error: "
            f"{reason}"
        )
        self.record_index = record_index
        self.reason = reason


@dataclass(frozen=True)
class StructuredProvenance:
    """Codex plan review #6 minimum fields for human-curated
    provenance. All fields required — no free-text fallback.

    Field definitions:

    curator_id: opaque identifier for who asserted this. Required
      so the audit log can trace every human-curated row to a
      curator account.
    source_type: one of 'licensed_institutional_access' |
      'licensed_personal_subscription' | 'author_communication' |
      'pre-print_accessed_legally' | 'other'. Limited vocabulary.
    source_locator: DOI + page range (e.g. "10.1016/S0140-6736(21)01443-4 pp.1811-1824"),
      or equivalent stable reference (PMC ID, URL at permanent
      archive, etc). Must uniquely identify the cited passage.
    acquired_at: ISO-8601 UTC timestamp when operator accessed the
      source. Must be timezone-aware AND offset=UTC (+00:00 or 'Z').
      Codex M-61 audit Nit: non-UTC offsets were silently accepted.
    artifact_sha256: hex digest of the retained file (PDF page
      image / text snippet / screenshot). Independently
      recomputable at audit time. Hex chars only, 64 long.
    artifact_retention_path: pointer to where the retained file
      lives — operator's audit share, institutional repository,
      etc. Not a public URL.
    quote_page_range: "p.1811" or "pp.1811-1812" style citation
      within the source. Allows audit to locate the exact passage.
    attestation: curator's signed statement of licensed access.
      Free-text but structured — "I hereby certify that ..."
      form. Audit-logged.
    other_justification: required IFF source_type='other'. Codex
      M-61 audit Medium: the `other` pressure valve needs a
      justification so it doesn't become an unaudited bucket.
    """

    curator_id: str
    source_type: str
    source_locator: str
    acquired_at: str                    # ISO-8601 UTC
    artifact_sha256: str                # 64 hex chars
    artifact_retention_path: str
    quote_page_range: str
    attestation: str
    other_justification: str | None = None

    def to_dict(self) -> dict[str, str]:
        """Serialize to plain dict for FrameRow.human_curated_provenance
        threading (avoids circular import between frame_fetcher
        and human_gap_completion)."""
        out = {
            "curator_id": self.curator_id,
            "source_type": self.source_type,
            "source_locator": self.source_locator,
            "acquired_at": self.acquired_at,
            "artifact_sha256": self.artifact_sha256,
            "artifact_retention_path": self.artifact_retention_path,
            "quote_page_range": self.quote_page_range,
            "attestation": self.attestation,
        }
        if self.other_justification is not None:
            out["other_justification"] = self.other_justification
        return out


@dataclass(frozen=True)
class HumanCompletionRecord:
    """One operator-provided completion for a gap entity."""

    entity_id: str
    doi: str | None                     # may be None for entities
                                        # without DOI (statute, URL-only)
    direct_quote: str
    provenance: StructuredProvenance
    # Optional echo of source_span the operator believes backs the
    # quote; M-58 anti-fabrication check still enforces value == span
    # at slot-fill time. Absent = the whole direct_quote is the span.
    source_span: str | None = None


# ─────────────────────────────────────────────────────────────────────
# Validation
# ─────────────────────────────────────────────────────────────────────
_ALLOWED_SOURCE_TYPES = frozenset({
    "licensed_institutional_access",
    "licensed_personal_subscription",
    "author_communication",
    "pre-print_accessed_legally",
    "other",
})

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")

# Codex M-61 audit Medium: the schema must be closed against
# legacy free-text channels. An `other` source_type must carry
# a justification field so the allowlist's pressure valve doesn't
# become an unaudited bucket. Legacy `consent_proof` key is
# explicitly rejected at parse.
_ALLOWED_COMPLETION_KEYS = frozenset({
    "entity_id", "doi", "direct_quote", "source_span", "provenance",
})
_ALLOWED_PROVENANCE_KEYS_BASE = frozenset({
    "curator_id", "source_type", "source_locator", "acquired_at",
    "artifact_sha256", "artifact_retention_path",
    "quote_page_range", "attestation",
})
# Extra key permitted ONLY when source_type="other".
_OTHER_JUSTIFICATION_KEY = "other_justification"


def parse_completion(
    raw: dict[str, Any], record_index: int,
) -> HumanCompletionRecord:
    """Parse one raw JSON record into HumanCompletionRecord.

    Codex M-61 audit Medium: schema is now CLOSED against legacy
    free-text channels. Any key outside _ALLOWED_COMPLETION_KEYS
    (e.g. legacy `consent_proof`) raises CompletionSchemaError.

    Raises CompletionSchemaError with record_index on any
    malformation, missing required provenance field, or
    unknown key.
    """
    if not isinstance(raw, dict):
        raise CompletionSchemaError(
            record_index, f"expected dict, got {type(raw).__name__}"
        )

    # Codex M-61 audit Medium: explicit unknown-key rejection.
    unknown = set(raw.keys()) - _ALLOWED_COMPLETION_KEYS
    if unknown:
        raise CompletionSchemaError(
            record_index,
            f"unknown keys: {sorted(unknown)}. Legacy free-text "
            f"channels (e.g. 'consent_proof') are rejected — "
            f"use the structured `provenance` object.",
        )

    entity_id = raw.get("entity_id")
    if not isinstance(entity_id, str) or not entity_id.strip():
        raise CompletionSchemaError(
            record_index, "entity_id must be non-empty string"
        )

    doi = raw.get("doi")
    if doi is not None and not isinstance(doi, str):
        raise CompletionSchemaError(
            record_index,
            f"doi must be str or null, got {type(doi).__name__}",
        )

    direct_quote = raw.get("direct_quote")
    if not isinstance(direct_quote, str) or not direct_quote.strip():
        raise CompletionSchemaError(
            record_index, "direct_quote must be non-empty string"
        )

    source_span = raw.get("source_span")
    if source_span is not None and not isinstance(source_span, str):
        raise CompletionSchemaError(
            record_index,
            f"source_span must be str or null, got "
            f"{type(source_span).__name__}",
        )

    provenance_raw = raw.get("provenance")
    if not isinstance(provenance_raw, dict):
        raise CompletionSchemaError(
            record_index,
            "provenance object required (structured per Codex plan "
            "review #6) — free-text consent_proof no longer "
            "accepted",
        )
    provenance = _parse_provenance(provenance_raw, record_index)

    return HumanCompletionRecord(
        entity_id=entity_id,
        doi=doi if doi and doi.strip() else None,
        direct_quote=direct_quote,
        provenance=provenance,
        source_span=(
            source_span if source_span and source_span.strip()
            else None
        ),
    )


def _parse_provenance(
    raw: dict[str, Any], record_index: int,
) -> StructuredProvenance:
    # Codex M-61 audit: unknown-key rejection plus conditional
    # other_justification enforcement.
    allowed_keys = set(_ALLOWED_PROVENANCE_KEYS_BASE)
    source_type_raw = raw.get("source_type")
    if source_type_raw == "other":
        allowed_keys.add(_OTHER_JUSTIFICATION_KEY)
    unknown = set(raw.keys()) - allowed_keys
    if unknown:
        raise CompletionSchemaError(
            record_index,
            f"provenance unknown keys: {sorted(unknown)}",
        )

    required = set(_ALLOWED_PROVENANCE_KEYS_BASE)
    missing = required - set(raw.keys())
    if missing:
        raise CompletionSchemaError(
            record_index,
            f"provenance missing required fields: {sorted(missing)}",
        )
    for key in required:
        value = raw[key]
        if not isinstance(value, str) or not value.strip():
            raise CompletionSchemaError(
                record_index,
                f"provenance.{key} must be non-empty string",
            )

    source_type = raw["source_type"]
    if source_type not in _ALLOWED_SOURCE_TYPES:
        raise CompletionSchemaError(
            record_index,
            f"provenance.source_type={source_type!r} not in "
            f"allowed set {sorted(_ALLOWED_SOURCE_TYPES)}",
        )

    # Codex M-61 audit Medium: source_type='other' MUST carry
    # other_justification. The pressure valve needs an audit hook.
    other_justification = None
    if source_type == "other":
        oj = raw.get(_OTHER_JUSTIFICATION_KEY)
        if not isinstance(oj, str) or not oj.strip():
            raise CompletionSchemaError(
                record_index,
                "provenance.other_justification required when "
                "source_type='other' (non-empty string)",
            )
        other_justification = oj

    artifact_sha256 = raw["artifact_sha256"].lower()
    if not _SHA256_RE.match(artifact_sha256):
        raise CompletionSchemaError(
            record_index,
            "provenance.artifact_sha256 must be 64 hex chars "
            "(lowercase)",
        )

    # Codex M-61 audit Nit: enforce UTC offset specifically, not
    # just timezone-awareness. Non-UTC offsets are rejected so the
    # audit timeline is consistent.
    acquired_at = raw["acquired_at"]
    try:
        normalized = acquired_at.replace("Z", "+00:00")
        dt = datetime.fromisoformat(normalized)
        if dt.tzinfo is None:
            raise ValueError("naive datetime not allowed")
        if dt.utcoffset() != timezone.utc.utcoffset(None):
            raise ValueError(
                f"timezone offset must be UTC; got "
                f"{dt.utcoffset()}"
            )
    except (ValueError, TypeError) as exc:
        raise CompletionSchemaError(
            record_index,
            f"provenance.acquired_at must be ISO-8601 UTC datetime "
            f"('+00:00' or 'Z'); got {acquired_at!r} ({exc})",
        ) from exc

    return StructuredProvenance(
        curator_id=raw["curator_id"],
        source_type=source_type,
        source_locator=raw["source_locator"],
        acquired_at=acquired_at,
        artifact_sha256=artifact_sha256,
        artifact_retention_path=raw["artifact_retention_path"],
        quote_page_range=raw["quote_page_range"],
        attestation=raw["attestation"],
        other_justification=other_justification,
    )


def load_completions(
    path: str | Path,
) -> tuple[HumanCompletionRecord, ...]:
    """Load + parse a human_gap_completions.json file.

    Returns tuple of parsed records in input order.

    Raises:
        CompletionSchemaError: on any record-level malformation.
        FileNotFoundError: if the file doesn't exist.
        ValueError: if the file isn't a JSON array at the root.
    """
    p = Path(path)
    with p.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError(
            f"completion file {p} root must be JSON array, got "
            f"{type(data).__name__}"
        )
    return tuple(
        parse_completion(r, i) for i, r in enumerate(data)
    )


# ─────────────────────────────────────────────────────────────────────
# Cross-check against M-60 task list
# ─────────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class CompletionAcceptance:
    """Result of cross-checking completions against tasks."""

    accepted: tuple[HumanCompletionRecord, ...]
    rejected: tuple[tuple[HumanCompletionRecord, str], ...]


def validate_against_tasks(
    completions: tuple[HumanCompletionRecord, ...],
    tasks: list[dict[str, Any]],
) -> CompletionAcceptance:
    """Cross-check each completion against the corresponding
    M-60 task. A completion is accepted iff:

    1. entity_id matches a task in tasks[].
    2. DOI matches the task's doi EXACTLY — including DOI
       presence. If the task has a DOI, the completion MUST
       supply the same DOI. DOI omission is NOT a valid bypass
       (Codex M-61 audit Blocker 1).
    3. Only one completion per entity_id is accepted. Second
       and subsequent completions for the same entity are
       rejected (Codex M-61 audit Blocker 3 — prevents ambiguous
       audit trail).

    Operator cannot:
      - substitute content from a different paper (DOI mismatch)
      - bypass the paper-binding by omitting DOI on their side
      - supply multiple completions for the same entity
      - supply content for an entity that isn't curator-actionable
    """
    tasks_by_eid: dict[str, dict[str, Any]] = {
        t["entity_id"]: t for t in tasks
    }
    accepted: list[HumanCompletionRecord] = []
    rejected: list[tuple[HumanCompletionRecord, str]] = []
    seen_entity_ids: set[str] = set()
    for c in completions:
        if c.entity_id in seen_entity_ids:
            rejected.append((
                c,
                f"duplicate completion for entity_id="
                f"{c.entity_id!r} — only one completion per "
                f"entity is accepted (audit integrity)",
            ))
            continue
        seen_entity_ids.add(c.entity_id)

        task = tasks_by_eid.get(c.entity_id)
        if task is None:
            rejected.append((
                c,
                f"no task exists for entity_id={c.entity_id!r} — "
                f"operator cannot supply content for an entity "
                f"that's not curator-actionable",
            ))
            continue
        task_doi = task.get("doi")
        if task_doi:
            # Codex M-61 audit Blocker 1: task has a DOI →
            # completion MUST have the SAME DOI. None on the
            # completion side is no longer a free pass.
            if c.doi is None:
                rejected.append((
                    c,
                    f"completion.doi is None but task requires "
                    f"doi={task_doi!r} — operator cannot bypass "
                    f"paper-binding by omitting DOI",
                ))
                continue
            if task_doi != c.doi:
                rejected.append((
                    c,
                    f"doi mismatch: task.doi={task_doi!r} vs "
                    f"completion.doi={c.doi!r} — operator cannot "
                    f"substitute content from a different paper",
                ))
                continue
        else:
            # Task has no DOI (statute, URL-only regulatory) —
            # completion must also have no DOI, to prevent the
            # operator from claiming a DOI where the contract
            # doesn't have one.
            if c.doi is not None:
                rejected.append((
                    c,
                    f"task has no DOI but completion.doi="
                    f"{c.doi!r} — operator cannot add a DOI "
                    f"binding that the contract does not require",
                ))
                continue
        accepted.append(c)

    return CompletionAcceptance(
        accepted=tuple(accepted),
        rejected=tuple(rejected),
    )


# ─────────────────────────────────────────────────────────────────────
# Convert to FrameRow for pipeline integration
# ─────────────────────────────────────────────────────────────────────
# Legacy string marker kept for back-compat with callers reading
# row.quote_source. The AUTHORITATIVE permanent flag is now
# ProvenanceClass.HUMAN_CURATED on row.provenance_class. Codex
# M-61 audit Blocker 2 fix.
HUMAN_CURATED_PROVENANCE = "human_curated"


def to_frame_rows(
    accepted: tuple[HumanCompletionRecord, ...],
    entity_metadata: dict[str, dict[str, Any]],
) -> tuple[FrameRow, ...]:
    """Produce FrameRow objects for each accepted completion.

    Codex M-61 audit Blocker 2 fix: provenance_class is now
    ProvenanceClass.HUMAN_CURATED (new enum value). Downstream
    layers that branch on provenance_class will see the permanent
    human-curated marker. Legacy quote_source="human_curated"
    kept for back-compat.

    Codex M-61 audit Blocker 3 fix: structured provenance is now
    serialized into FrameRow.human_curated_provenance as a dict.
    Every field of StructuredProvenance survives the FrameRow
    boundary. Downstream manifest renderers can inline the
    audit evidence without needing an in-memory side channel.

    `entity_metadata` is a map of entity_id → {rendering_slot,
    entity_type, ...} pulled from ReportContract.entities_by_id()
    at integration time. We don't import ReportContract here to
    keep M-61 independent of M-54 schema.

    NOTE: M-58 SlotFillPayload + strict_verify still apply. A
    human-curated direct_quote must pass the same value==source_span
    verbatim check. The structured provenance is AUDIT evidence
    (independent of strict_verify) that the quote wasn't
    fabricated.
    """
    rows: list[FrameRow] = []
    for c in accepted:
        meta = entity_metadata.get(c.entity_id, {})
        rendering_slot = meta.get("rendering_slot", "")
        entity_type = meta.get("entity_type", "unknown")
        rows.append(FrameRow(
            entity_id=c.entity_id,
            entity_type=entity_type,
            rendering_slot=rendering_slot,
            provenance_class=ProvenanceClass.HUMAN_CURATED,
            direct_quote=c.direct_quote,
            quote_source=HUMAN_CURATED_PROVENANCE,
            doi=c.doi,
            pmid=None,
            oa_pdf_url=None,
            url=c.provenance.artifact_retention_path,
            title=None,
            authors=(),
            journal=None,
            year=None,
            failure_reason=None,
            retrieval_attempts=(),
            retrieval_timings=(),
            human_curated_provenance=c.provenance.to_dict(),
        ))
    return tuple(rows)


def compute_artifact_sha256(content: bytes) -> str:
    """Utility for operators: compute SHA-256 of a retained
    artifact to populate the `artifact_sha256` field. Same as
    hashlib.sha256(content).hexdigest() but wrapped so the
    canonical method is in one place."""
    return hashlib.sha256(content).hexdigest()


def compose_methods_disclosure_human_curated(
    n_retrieved: int, n_human_curated: int,
) -> str:
    """Methods-section snippet counting human-curated rows
    separately from retrieved rows. Per V30 plan: 'Tier
    disclosure ... counts human-curated rows separately from
    retrieved rows: "46 retrieved + 3 human-curated from
    licensed sources"'.

    Codex M-61 audit Medium fix: say "licensed or attested
    sources" since allowed source_type values include
    author_communication and preprint and other-with-
    justification, not strictly subscription.
    """
    if n_human_curated == 0:
        return f"Evidence basis: {n_retrieved} retrieved rows, 0 human-curated."
    return (
        f"Evidence basis: {n_retrieved} retrieved + {n_human_curated} "
        f"human-curated from licensed or attested sources (see "
        f"manifest.json frame_coverage_report.entries with "
        f"provenance_class={ProvenanceClass.HUMAN_CURATED.value!r} "
        f"for curator attribution + artifact_sha256 + "
        f"retention pointer)."
    )
