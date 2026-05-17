"""Source snapshot — collects every cited source's text into the bundle.

Per `.codex/slices/slice_004/architecture_proposal.md` §"snapshot_sources".

Walks every kept VerifiedSentence across every non-dropped Section in
the VerifiedReport, extracts the unique source_ids referenced by their
provenance tokens, then pulls the full_text (or snippet fallback) from
the EvidencePool.

The snapshotted text is what makes the bundle independently verifiable
offline: a third party can re-run strict_verify against the bundle's
content without re-fetching from the original source URLs (which may
have changed since retrieval).
"""

from __future__ import annotations

from typing import NamedTuple

from polaris_graph.clinical_generator.provenance import extract_tokens
from polaris_graph.clinical_generator.verified_report import VerifiedReport
from polaris_graph.retrieval2.evidence_pool import EvidencePool, Source


class SnapshotEntry(NamedTuple):
    """Snapshot text plus the reachable character count (excludes appended truncation note)."""

    text: str
    reachable_chars: int


# Cap each source's text to keep the bundle bounded. 200KB per source
# is enough for a typical full-text article; a Cochrane systematic
# review with all appendices may need more — adjust if production
# data shows truncation hits the audit_quality_gate.
MAX_SOURCE_TEXT_BYTES = 200 * 1024  # 200 KB

SOURCE_TRUNCATION_NOTE_TEMPLATE = (
    "\n\n[POLARIS audit-bundle truncation notice: source text truncated "
    "from {original_size} to {truncated_size} bytes per "
    "MAX_SOURCE_TEXT_BYTES policy.]"
)


def _cited_source_ids(report: VerifiedReport) -> set[str]:
    """Collect source_ids from provenance tokens of every kept sentence
    in every non-dropped section.

    Dropped sentences are excluded — we don't want to ship snapshots
    for sources that didn't survive verification.
    """
    out: set[str] = set()
    for section in report.sections:
        if section.section_status == "dropped":
            continue
        for sentence in section.verified_sentences:
            if not sentence.verifier_pass:
                continue
            for token_str in sentence.provenance_tokens:
                tokens = extract_tokens(token_str)
                for tok in tokens:
                    out.add(tok.source_id)
    return out


def _snapshot_text(source: Source) -> str:
    """Return the text to snapshot for one source.

    Prefers full_text; falls back to snippet. Truncates at
    MAX_SOURCE_TEXT_BYTES with an audit-visible note appended so
    re-verifiers see why the span may not resolve.
    """
    text = source.full_text if source.full_text is not None else source.snippet
    text_bytes = text.encode("utf-8")
    if len(text_bytes) <= MAX_SOURCE_TEXT_BYTES:
        return text

    # Truncate to MAX_SOURCE_TEXT_BYTES respecting UTF-8 boundaries.
    truncated = text_bytes[:MAX_SOURCE_TEXT_BYTES]
    # Walk back continuation bytes (10xxxxxx). The first non-continuation
    # byte we hit is either a single-byte ASCII char (0xxxxxxx, complete)
    # or a multi-byte start byte (11xxxxxx). If it's a start byte, the
    # codepoint is incomplete because we already trimmed the continuations
    # — drop the start byte too.
    while truncated and (truncated[-1] & 0xC0) == 0x80:
        truncated = truncated[:-1]
    if truncated and (truncated[-1] & 0x80) and (truncated[-1] & 0x40):
        truncated = truncated[:-1]
    note = SOURCE_TRUNCATION_NOTE_TEMPLATE.format(
        original_size=len(text_bytes),
        truncated_size=len(truncated),
    )
    return truncated.decode("utf-8") + note


def snapshot_sources(
    report: VerifiedReport,
    pool: EvidencePool,
) -> dict[str, str]:
    """Return {source_id: snapshot_text} for every source cited in the
    report's kept sentences.

    Source_ids that appear in tokens but are not present in the pool
    are silently skipped (strict_verify already rejected those sentences,
    so they shouldn't have made it through; defensive coding).
    """
    needed = _cited_source_ids(report)
    pool_index: dict[str, Source] = {s.source_id: s for s in pool.sources}

    out: dict[str, str] = {}
    for source_id in needed:
        source = pool_index.get(source_id)
        if source is None:
            # Should not happen post-strict-verify; defensive skip
            continue
        out[source_id] = _snapshot_text(source)
    return out


def snapshot_size_bytes(snapshots: dict[str, str]) -> int:
    """Total bytes across all snapshots — useful for bundle-size checks."""
    return sum(len(text.encode("utf-8")) for text in snapshots.values())


def _snapshot_entry(source: Source) -> SnapshotEntry:
    """Snapshot one source returning text + reachable_chars (excl. truncation note)."""
    text = source.full_text if source.full_text is not None else source.snippet
    text_bytes = text.encode("utf-8")
    if len(text_bytes) <= MAX_SOURCE_TEXT_BYTES:
        return SnapshotEntry(text=text, reachable_chars=len(text))
    truncated = text_bytes[:MAX_SOURCE_TEXT_BYTES]
    while truncated and (truncated[-1] & 0xC0) == 0x80:
        truncated = truncated[:-1]
    if truncated and (truncated[-1] & 0x80) and (truncated[-1] & 0x40):
        truncated = truncated[:-1]
    body = truncated.decode("utf-8")
    note = SOURCE_TRUNCATION_NOTE_TEMPLATE.format(
        original_size=len(text_bytes), truncated_size=len(truncated)
    )
    return SnapshotEntry(text=body + note, reachable_chars=len(body))


def snapshot_sources_with_reachable(
    report: VerifiedReport, pool: EvidencePool
) -> dict[str, SnapshotEntry]:
    """Like snapshot_sources but returns SnapshotEntry tuples (text + reachable_chars)."""
    needed = _cited_source_ids(report)
    pool_index: dict[str, Source] = {s.source_id: s for s in pool.sources}
    out: dict[str, SnapshotEntry] = {}
    for source_id in needed:
        source = pool_index.get(source_id)
        if source is None:
            continue
        out[source_id] = _snapshot_entry(source)
    return out
