"""Mirror (Cohere Command-A+) adapter — two-pass RAG/JSON + citation-binding guard.

Cohere `response_format` (JSON mode) is incompatible with `documents`/`tools` (F2), so the
Mirror role is TWO PASS, each its own transport completion (iter-3 P1-a):
  pass-1: RAG-with-documents (citations on, NO response_format) -> grounded answer + spans
  pass-2: JSON classification (response_format ok, no documents), bound to pass-1 by hash

Citation normalization (iter-3 P1-b): pass-1 citations come from `RoleResponse.citations`
when the transport already normalized them (managed path), ELSE from `<co>...</co:doc_ids>`
spans parsed out of `raw_text` (self-host path, F2). BOTH sources flow through ONE validator.

Citation-binding guard (iter-4): every span must point at a `doc_id` actually present in the
supplied `evidence_documents`. A span with an empty doc_id, or citing a doc_id never
provided (hallucinated identity), or MIXING a real cite with a fabricated one, is REJECTED
whole. If NO valid grounded citation survives, raise `MirrorCitationError` (fail closed) —
a non-empty-but-ungrounded citation set must NOT satisfy the binding. Every Mirror claim in
this PR is grounding-required; there is no escape hatch.

Binding guard (pass-1<->pass-2): `verify_pass2_binding` MUST hold or `MirrorBindingError` is
raised — an unbound pass-2 is never trusted.
"""

from __future__ import annotations

import json

from src.polaris_graph.roles.mirror_contract import (
    CitationSpan,
    MirrorPass1,
    MirrorPass2,
    _CO_SPAN_RE,
    build_pass2_input,
    parse_cohere_citations,
    verify_pass2_binding,
)
from src.polaris_graph.roles.role_transport import (
    EvidenceDocument,
    RoleCallRecord,
    RoleRequest,
    RoleResponse,
    RoleTransport,
)

_ROLE = "mirror"

# Pass-2 JSON classification field keys.
_CLASSIFICATION_KEY = "classification"
_RATIONALE_KEY = "rationale"
_CONTENT_HASH_KEY = "content_hash"


class MirrorCitationError(ValueError):
    """Raised when pass-1 has NO valid grounded citation after binding validation.

    Fail closed: a missing, empty-doc_id, or hallucinated-identity citation set must not be
    laundered into an apparently-grounded MirrorPass1. Grounding integrity guard (iter-4).
    """


class MirrorBindingError(ValueError):
    """Raised when pass-2 does not bind to the pass-1 artifact (`verify_pass2_binding` False).

    Fail closed: an unbound pass-2 classification is never trusted.
    """


class MirrorParseError(ValueError):
    """Raised when pass-2 returns non-JSON or JSON missing the `classification` verdict.

    A VERDICT-level failure (the model DID respond — transport was fine — but the body cannot
    be parsed into a classification), so it drives the SAME fail-closed -> UNSUPPORTED path as
    MirrorCitationError/MirrorBindingError instead of crashing the whole 4-role run (#1028). A
    reasoning-first verifier (GLM-5.1) under `response_format=json_object` reliably returns JSON
    but sometimes omits keys; a missing `classification` is unrecoverable (fail closed), whereas
    a merely-omitted `content_hash` is recoverable (the caller knows the expected hash — see
    `_parse_pass2`).
    """


def _strip_co_tags(raw: str) -> str:
    """Strip `<co>...</co:doc_ids>` tags, leaving the covered text, so the cleaned answer
    text's offsets align with the spans `parse_cohere_citations` reports (which index into
    the TAG-STRIPPED text). Replacing each match with its covered group (group 1) mirrors
    exactly how the contract reconstructs cleaned-text offsets.
    """
    return _CO_SPAN_RE.sub(lambda m: m.group(1), raw)


def _validate_citation_binding(
    spans: list[CitationSpan],
    valid_doc_ids: set[str],
) -> list[CitationSpan]:
    """Keep only spans whose doc_ids ALL bind to a supplied evidence document.

    A span is REJECTED whole if it has no doc_ids (empty/missing) OR if ANY of its doc_ids
    is not in `valid_doc_ids` (a mixed real+hallucinated span is itself a fabrication signal,
    so it does not count as grounding). Returns the surviving grounded spans.
    """
    grounded: list[CitationSpan] = []
    for span in spans:
        if not span.doc_ids:
            continue  # empty/missing doc_id tuple -> not grounding
        # Reject a span if ANY of its doc_ids is empty/whitespace. An empty doc_id is never
        # grounding, even if the supplied evidence set happens to contain an
        # EvidenceDocument with an empty/whitespace doc_id (Codex diff iter-1 P1: such a
        # doc is excluded from valid_doc_ids, but guard here too — defense in depth).
        if any((not doc_id or not doc_id.strip()) for doc_id in span.doc_ids):
            continue
        if any(doc_id not in valid_doc_ids for doc_id in span.doc_ids):
            continue  # hallucinated (or mixed) identity -> reject whole span
        grounded.append(span)
    return grounded


def _extract_citations(
    response: RoleResponse,
    valid_doc_ids: set[str],
) -> list[CitationSpan]:
    """Normalize pass-1 citations from the explicit precedence, then bind-validate them.

    Source precedence (iter-3 P1-b): structured `RoleResponse.citations` (managed path) if
    present, ELSE `<co>` spans parsed from `raw_text` (self-host path). Both sources flow
    through the SINGLE `_validate_citation_binding` step (iter-4). Returns ONLY the spans
    that bind to a supplied evidence document.
    """
    if response.citations is not None:
        raw_spans = response.citations
    else:
        raw_spans = parse_cohere_citations(response.raw_text)
    return _validate_citation_binding(raw_spans, valid_doc_ids)


def build_mirror_pass1_request(
    claim: str,
    evidence_documents: list[EvidenceDocument],
    *,
    model_slug: str,
) -> RoleRequest:
    """Build the pass-1 RAG-with-documents request (citations on, NO response_format).

    Documents ride in `params["documents"]`; `params["citations"] = True` turns on citation
    emission. NO `response_format` — JSON mode is incompatible with documents (F2).
    """
    params = {
        "documents": [
            {"doc_id": doc.doc_id, "text": doc.text} for doc in evidence_documents
        ],
        "citations": True,
    }
    return RoleRequest(
        role=_ROLE,
        model_slug=model_slug,
        prompt=claim,
        params=params,
    )


def build_mirror_pass2_request(pass1: MirrorPass1, *, model_slug: str) -> RoleRequest:
    """Build the pass-2 JSON-classification request, embedding the pass-1 composite hash.

    Uses `build_pass2_input(pass1)` so the request carries the composite `content_hash`
    (answer text + ordered citation bindings). `response_format=json_object` is allowed now
    (no documents in this pass).
    """
    pass2_input = build_pass2_input(pass1)
    params = {
        "response_format": {"type": "json_object"},
        "pass2_input": pass2_input,
    }
    return RoleRequest(
        role=_ROLE,
        model_slug=model_slug,
        prompt="Classify the bound pass-1 artifact and return JSON.",
        params=params,
    )


def _parse_pass2(raw_text: str, *, expected_content_hash: str) -> MirrorPass2:
    """Parse a pass-2 transport response into MirrorPass2.

    The classification JSON must carry a `classification` (the verdict); an optional `rationale`
    is preserved. `content_hash` is the pass-1<->pass-2 binding the model is ASKED to echo, but
    `expected_content_hash` (the caller-computed `_compute_content_hash(pass1)`) is authoritative:
    in a synchronous single call the pass-2 response is necessarily about the pass-1 artifact we
    built, so when a reasoning-first verifier OMITS the redundant echo we fall back to the
    expected hash and the real classification is salvaged (#1028). A model-RETURNED hash is kept
    as-is so `verify_pass2_binding` still catches a present-but-MISMATCHED hash (a genuine mixup).

    A non-JSON body or a JSON missing `classification` is unrecoverable -> `MirrorParseError`
    (a VERDICT-level failure that drives the fail-closed -> UNSUPPORTED path, NOT a whole-run
    crash). Never fabricates a verdict.
    """
    try:
        payload = json.loads(raw_text)
    except (json.JSONDecodeError, ValueError) as exc:
        raise MirrorParseError(
            f"Mirror pass-2 returned a non-JSON body: {exc}"
        ) from exc
    if not isinstance(payload, dict) or _CLASSIFICATION_KEY not in payload:
        raise MirrorParseError(
            "Mirror pass-2 JSON is missing the required 'classification' verdict "
            f"(keys={list(payload) if isinstance(payload, dict) else type(payload).__name__})"
        )
    return MirrorPass2(
        # Salvage ONLY on genuine key ABSENCE. A PRESENT content_hash is kept verbatim — even an
        # empty string or any other falsy/wrong value — so verify_pass2_binding still catches a
        # present-but-MISMATCHED hash (Codex diff-gate P1: truthiness salvage would launder a
        # present-but-empty hash past the binding guard). Omission is the only salvage path.
        content_hash=(
            payload[_CONTENT_HASH_KEY]
            if _CONTENT_HASH_KEY in payload
            else expected_content_hash
        ),
        classification=payload[_CLASSIFICATION_KEY],
        rationale=payload.get(_RATIONALE_KEY),
    )


def run_mirror(
    transport: RoleTransport,
    claim: str,
    evidence_documents: list[EvidenceDocument],
    *,
    model_slug: str,
) -> tuple[MirrorPass2, list[RoleCallRecord]]:
    """Run the two Mirror passes and return MirrorPass2 + a 2-element RoleCallRecord list.

    Pass-1: RAG-with-documents; normalize + bind-validate citations (iter-4). If no grounded
    citation survives, raise `MirrorCitationError` (fail closed). Pass-2: JSON classification
    bound by hash; if `verify_pass2_binding` is False, raise `MirrorBindingError` (fail
    closed). BOTH completions get their own RoleCallRecord (iter-3 P1-a) so the Path-B gate
    can verify served==pinned per call.
    """
    # Build the citation-identity pool from supplied documents, EXCLUDING any empty/whitespace
    # doc_id so a citation with an empty doc_id can never bind (Codex diff iter-1 P1).
    valid_doc_ids = {
        doc.doc_id for doc in evidence_documents if doc.doc_id and doc.doc_id.strip()
    }

    # --- pass 1: RAG with documents + citations -------------------------------------
    pass1_request = build_mirror_pass1_request(
        claim, evidence_documents, model_slug=model_slug
    )
    pass1_response: RoleResponse = transport.complete(pass1_request)

    grounded_spans = _extract_citations(pass1_response, valid_doc_ids)
    if not grounded_spans:
        # Fail closed: no citation binds to a supplied document for this grounding-required
        # claim. A non-empty-but-ungrounded citation set lands here too (it was rejected).
        raise MirrorCitationError(
            "Mirror pass-1 produced no citation grounded in the supplied evidence documents "
            f"(claim={claim!r}); refusing to treat as grounded."
        )

    # On the self-host path, store the TAG-STRIPPED answer so the span offsets (which index
    # the cleaned text) align with the stored answer_text.
    if pass1_response.citations is not None:
        answer_text = pass1_response.raw_text
    else:
        answer_text = _strip_co_tags(pass1_response.raw_text)
    pass1 = MirrorPass1(answer_text=answer_text, citation_spans=grounded_spans)

    pass1_record = RoleCallRecord(
        role=_ROLE,
        model_slug=model_slug,
        served_model=pass1_response.served_model,
        raw_text=pass1_response.raw_text,
        parsed=pass1,
    )

    # --- pass 2: JSON classification bound to pass-1 --------------------------------
    pass2_request = build_mirror_pass2_request(pass1, model_slug=model_slug)
    pass2_response: RoleResponse = transport.complete(pass2_request)
    # The caller-authoritative expected hash (same value build_mirror_pass2_request embedded) is
    # passed so a verifier that omits the redundant content_hash echo doesn't lose the verdict.
    expected_content_hash = build_pass2_input(pass1)[_CONTENT_HASH_KEY]
    pass2 = _parse_pass2(pass2_response.raw_text, expected_content_hash=expected_content_hash)

    pass2_record = RoleCallRecord(
        role=_ROLE,
        model_slug=model_slug,
        served_model=pass2_response.served_model,
        raw_text=pass2_response.raw_text,
        parsed=pass2,
    )

    if not verify_pass2_binding(pass1, pass2):
        # Fail closed: pass-2 classified a different (answer+citations) artifact than pass-1.
        raise MirrorBindingError(
            "Mirror pass-2 content_hash does not bind to the pass-1 artifact; "
            "refusing to trust an unbound classification."
        )

    return pass2, [pass1_record, pass2_record]
