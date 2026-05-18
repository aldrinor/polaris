"""Uploaded-document grounding for the v6 research pipeline (I-rdy-010 / #506).

The v6 worker actor resolves uploaded ``document_ids`` to content, then this
module does two things:

1. ``partition_uploads_by_sovereignty`` — splits resolved uploads into
   egress-allowed vs egress-blocked via the sovereignty router. The pipeline
   generator is an external LLM call, so only ``PUBLIC_SYNTHETIC`` documents
   may become evidence; ``CLIENT`` / ``CAN_REAL`` / ``PRIVATE`` / ``UNKNOWN``
   are ``EXTERNAL_LEAK_FORBIDDEN`` and never reach the generator.
2. ``build_upload_evidence_rows`` — turns sovereignty-cleared documents into
   the pipeline-A evidence dict-row shape (matching the V30-P2 contract rows
   at ``scripts/run_honest_sweep_r3.py:2044-2059``), so uploaded-document
   evidence is prepended onto ``evidence_for_gen`` and flows into the report
   bibliography + ``evidence_pool.json``.

Per CLAUDE.md LAW II: a forbidden classification reaching
``build_upload_evidence_rows`` raises rather than silently passing — the
actor-stage sovereignty filter is the gate, and this re-check is
belt-and-suspenders.
"""

from __future__ import annotations

from polaris_graph.sovereignty.router import filter_for_external_egress

# Only PUBLIC_SYNTHETIC uploads may become external-generator evidence;
# every other classification is EXTERNAL_LEAK_FORBIDDEN.
EGRESS_SAFE_CLASSIFICATION = "PUBLIC_SYNTHETIC"


class UploadSovereigntyError(RuntimeError):
    """Raised when a non-egress-safe uploaded document reaches evidence-row
    construction. A forbidden document here is a bug — the actor-stage
    sovereignty filter should have blocked it — never a silent pass."""


def partition_uploads_by_sovereignty(
    uploaded_documents: list[dict],
) -> tuple[list[dict], list[dict]]:
    """Split uploaded documents into (egress-allowed, egress-blocked).

    Each document is a dict carrying a ``classification`` key. Delegates to
    the sovereignty router (``filter_for_external_egress``, non-strict) so
    the EXTERNAL_LEAK_FORBIDDEN policy is enforced in exactly one place.
    """
    decision = filter_for_external_egress(uploaded_documents, strict=False)
    return list(decision.allowed), list(decision.blocked)


def build_upload_evidence_rows(uploaded_documents: list[dict]) -> list[dict]:
    """Build pipeline-A evidence dict rows from sovereignty-cleared uploads.

    Args:
        uploaded_documents: list of ``{document_id, classification,
            filename, chunks}`` — expected to be the *allowed* partition
            from ``partition_uploads_by_sovereignty``.

    Returns:
        One evidence dict row per non-empty chunk, shaped like the V30-P2
        contract rows so the generator + ``evidence_pool`` consume them.

    Raises:
        UploadSovereigntyError: if any document is not PUBLIC_SYNTHETIC.
    """
    rows: list[dict] = []
    for doc in uploaded_documents:
        classification = doc.get("classification")
        if classification != EGRESS_SAFE_CLASSIFICATION:
            raise UploadSovereigntyError(
                f"uploaded document {doc.get('document_id')!r} has "
                f"classification {classification!r}; only "
                f"{EGRESS_SAFE_CLASSIFICATION} may become external-generator "
                "evidence — the actor-stage sovereignty filter should have "
                "blocked this document."
            )
        document_id = doc["document_id"]
        filename = doc.get("filename") or "uploaded document"
        for chunk_index, chunk in enumerate(doc.get("chunks") or []):
            text = (chunk or "").strip()
            if not text:
                continue
            rows.append(
                {
                    "evidence_id": f"ev_upload_{document_id}_{chunk_index}",
                    "statement": text,
                    "direct_quote": text,
                    "source_url": f"upload://{document_id}",
                    "title": filename,
                    "authors": [],
                    "journal": "",
                    "year": None,
                    "doi": "",
                    "pmid": "",
                    "tier": "T2",
                    "uploaded_document": True,
                }
            )
    return rows
