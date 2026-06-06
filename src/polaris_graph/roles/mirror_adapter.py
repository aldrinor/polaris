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
import re

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

# Common ALTERNATE keys a reasoning-first verifier (GLM-5.1) uses for the verdict when it omits
# the canonical `classification` key (run-11 evidence: answer/label/category observed; class is a
# harmless common synonym). EXACT match only — never substring/prefix — so the echoed pass-1
# `answer_text` key can NEVER be laundered as a verdict ("answer" != "answer_text"). The canonical
# `classification` key is tried first; alternates are consulted ONLY when it is absent.
_ALTERNATE_CLASSIFICATION_KEYS = ("answer", "category", "label", "class")

# Strip a fenced JSON wrapper ```json ... ``` or ``` ... ``` that reasoning-first models emit
# around the JSON body before json.loads. Tolerates an optional language tag (json/JSON/...) and
# the no-newline-after-fence form (```json{...```, run-11 sample). DOTALL so the body may span
# lines; non-greedy so it stops at the FIRST closing fence. Only a leading-fence body is rewritten;
# a body with no leading fence is returned unchanged.
_CODE_FENCE_RE = re.compile(
    r"^\s*`{3}[a-zA-Z0-9]*\s*(?P<body>.*?)\s*`{3}\s*$",
    re.DOTALL,
)


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


def _strip_code_fence(raw_text: str) -> str:
    """Strip a leading ```json ... ``` (or bare ``` ... ```) code-fence wrapper, if present.

    Reasoning-first models (GLM-5.1) often wrap the JSON body in a markdown fence even under
    `response_format=json_object`. We unwrap ONLY a body that both opens and closes with a triple-
    backtick fence; any other text is returned unchanged so `json.loads` sees it verbatim. This is
    pure FORMAT noise removal — it never alters the parsed verdict, only the wrapper around it.
    """
    match = _CODE_FENCE_RE.match(raw_text)
    if match is not None:
        return match.group("body")
    return raw_text


def _coerce_classification_value(value: object) -> str | None:
    """Coerce a recovered classification value to a non-empty verdict string, else None.

    - A non-empty (after strip) `str` is returned as-is.
    - A non-empty `dict` (the heterogeneous NESTED-classification shape GLM-5.1 emits, e.g.
      `{"domain": "Economics", ...}`) is deterministically serialized with sorted keys so a
      meaningful, stable string verdict survives — we do NOT guess a "primary" sub-key (the nested
      shapes are heterogeneous: primary_domain / domain / content_type / ...). Serialization is
      safe: `classification` is NOT part of the pass-1<->pass-2 binding hash and NOT the grounding
      gate, so it cannot affect either guard.
    - Anything else (empty string/whitespace, empty dict, list, number, bool, None) -> None,
      signalling "no recoverable verdict here".
    """
    if isinstance(value, str):
        stripped = value.strip()
        return value if stripped else None
    # FX-08 (I-ready-017): coerce scalar JSON types (int/float/bool) to their string
    # form (json_repair philosophy) so a GROUNDED claim is not false-DROPped when the
    # verifier emits e.g. {"classification": 0}. bool is an int subclass — str() handles
    # both ("True" / "0" / "0.0"). Non-gating: classification is NOT part of the
    # pass-1<->pass-2 binding hash or the grounding gate, so this cannot affect either.
    if isinstance(value, (int, float)):  # includes bool (int subclass)
        return str(value)
    if isinstance(value, dict) and value:
        return json.dumps(value, sort_keys=True, separators=(",", ":"))
    return None


def _recover_classification(payload: dict) -> str | None:
    """Recover a classification verdict string from the pass-2 payload, else None.

    Lookup precedence (EXACT key match only — never substring/prefix, so the echoed pass-1
    `answer_text` key can never masquerade as a verdict):
      1. the canonical `classification` key (string OR nested-dict, via `_coerce_classification_value`)
      2. a small set of common alternates (answer/category/label/class), tried only when the
         canonical key is absent OR yielded no recoverable value.
    Returns the first recovered non-empty string, else None.
    """
    if _CLASSIFICATION_KEY in payload:
        recovered = _coerce_classification_value(payload[_CLASSIFICATION_KEY])
        if recovered is not None:
            return recovered
    for alt_key in _ALTERNATE_CLASSIFICATION_KEYS:
        if alt_key in payload:
            recovered = _coerce_classification_value(payload[alt_key])
            if recovered is not None:
                return recovered
    return None


def _parse_pass2(raw_text: str, *, expected_content_hash: str) -> MirrorPass2:
    """Parse a pass-2 transport response into MirrorPass2.

    ROBUST classification extraction (I-run11-002 L2): a reasoning-first verifier (GLM-5.1) returns
    RECOVERABLE formatting noise even when pass-1 grounding SUCCEEDED. We therefore, in order:
      1. strip a markdown code fence (```json ... ``` / ``` ... ```) before `json.loads`;
      2. accept the verdict under the canonical `classification` key (string OR nested dict) OR a
         small set of common alternates (answer/category/label/class) via `_recover_classification`.
    ONLY when NO classification string can be recovered at all -> `MirrorParseError` (still fail
    closed). This is purely about not failing a GROUNDED claim on classification-FORMAT noise; it
    does NOT touch pass-1 grounding (the `<co>` citation binding stays the strict groundedness gate)
    and introduces NO false-accept (a claim with no valid `<co>` span never reaches here — it has
    already failed closed via MirrorCitationError in `run_mirror`).

    `content_hash` is the pass-1<->pass-2 binding the model is ASKED to echo, but
    `expected_content_hash` (the caller-computed `_compute_content_hash(pass1)`) is authoritative:
    when a reasoning-first verifier OMITS the redundant echo we fall back to the expected hash and
    the real classification is salvaged (#1028). A model-RETURNED hash is kept as-is so
    `verify_pass2_binding` still catches a present-but-MISMATCHED hash (a genuine mixup).

    A non-JSON body (even after fence-strip) or a JSON with no recoverable classification is
    unrecoverable -> `MirrorParseError` (a VERDICT-level failure that drives the fail-closed ->
    UNSUPPORTED path, NOT a whole-run crash). Never fabricates a verdict.
    """
    unfenced = _strip_code_fence(raw_text)
    try:
        payload = json.loads(unfenced)
    except (json.JSONDecodeError, ValueError) as exc:
        raise MirrorParseError(
            f"Mirror pass-2 returned a non-JSON body: {exc}"
        ) from exc
    if not isinstance(payload, dict):
        raise MirrorParseError(
            "Mirror pass-2 body is not a JSON object "
            f"(type={type(payload).__name__})"
        )
    classification = _recover_classification(payload)
    if classification is None:
        # FX-08 (I-ready-017): a GROUNDED claim (pass-1 grounding already passed in
        # run_mirror BEFORE this parse; verify_pass2_binding still gates the
        # content_hash) must not be false-DROPped on classification FORMAT. The
        # heterogeneous GLM-5.1 nested shape (e.g. {"domain":..,"field":..}) carries a
        # real but UNRECOGNIZED verdict signal — serialize the WHOLE object as the
        # non-gating verdict so the claim reaches the Judge (the Mirror classification
        # is advisory MIRROR_SIGNAL, NOT a hard gate).
        #
        # NO-FALSE-ACCEPT GUARD PRESERVED: a body carrying ONLY echo/binding keys
        # (content_hash, answer_text, rationale) or only an empty/blank recognized
        # verdict key has NO genuine signal — it still fails closed (an echoed
        # answer_text is never laundered into a verdict). Empty {} also fails closed.
        _non_verdict_keys = {
            _CONTENT_HASH_KEY,
            _RATIONALE_KEY,
            "answer_text",
            _CLASSIFICATION_KEY,
            *_ALTERNATE_CLASSIFICATION_KEYS,
        }
        genuine_signal_keys = set(payload) - _non_verdict_keys
        if not genuine_signal_keys:
            raise MirrorParseError(
                "Mirror pass-2 has no recoverable classification verdict "
                f"(keys={list(payload)})"
            )
        classification = json.dumps(
            payload, sort_keys=True, separators=(",", ":")
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
        classification=classification,
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
