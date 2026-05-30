"""Sentinel (IBM Granite Guardian 4.1) adapter — request builder + FAIL-CLOSED caller.

Granite Guardian groundedness calling convention (F3, I-meta-002 iter-2): an assistant turn
carrying the claim to be checked, then a FINAL user `<guardian>` groundedness block, plus the
`documents`. The model emits `<score>yes|no</score>` (NOT JSON), so the request carries NO
structured-output spec — the score is parsed by `parse_sentinel_score`.

FAIL CLOSED (lethal-inversion guard): a malformed/empty output OR a transport error yields
`SentinelResult(UNGROUNDED, parsed_ok=False)`. There is NO path that returns GROUNDED on bad
or missing output. `yes=UNGROUNDED` polarity lives in the contract, never re-derived here.
"""

from __future__ import annotations

from src.polaris_graph.roles.role_transport import (
    EvidenceDocument,
    RoleCallRecord,
    RoleRequest,
    RoleResponse,
    RoleTransport,
)
from src.polaris_graph.roles.sentinel_contract import (
    SentinelResult,
    SentinelVerdict,
    parse_sentinel_score,
)

_ROLE = "sentinel"

# The prescribed groundedness instruction wrapped in the final user `<guardian>` block.
# Documents are carried separately in params["documents"] (Granite's `documents` channel),
# NOT inlined here, so the calling convention stays auditable.
_GUARDIAN_BLOCK = (
    "<guardian>groundedness</guardian>\n"
    "Assess whether the assistant's claim is grounded in the provided documents. "
    "Respond with exactly <score>yes</score> if the claim is NOT grounded (risk present) "
    "or <score>no</score> if it IS grounded (no risk). Output only the score element."
)

# The fail-closed result returned on transport error / malformed output. NEVER GROUNDED.
_FAIL_CLOSED = SentinelResult(SentinelVerdict.UNGROUNDED, parsed_ok=False)


def build_sentinel_request(
    claim: str,
    evidence_documents: list[EvidenceDocument],
    *,
    model_slug: str,
) -> RoleRequest:
    """Build a Granite Guardian groundedness request.

    Layout (F3): assistant turn = the claim under check; final user turn = the `<guardian>`
    groundedness block. The documents ride in `params["documents"]` (Granite's documents
    channel). NO structured-output spec — Granite emits a `<score>` element, not JSON.
    """
    messages = [
        {"role": "assistant", "content": claim},
        {"role": "user", "content": _GUARDIAN_BLOCK},
    ]
    params = {
        "documents": [
            {"doc_id": doc.doc_id, "text": doc.text} for doc in evidence_documents
        ],
    }
    return RoleRequest(
        role=_ROLE,
        model_slug=model_slug,
        messages=messages,
        params=params,
    )


def run_sentinel(
    transport: RoleTransport,
    claim: str,
    evidence_documents: list[EvidenceDocument],
    *,
    model_slug: str,
) -> tuple[SentinelResult, list[RoleCallRecord]]:
    """Call the transport once and parse the Granite Guardian score, FAIL CLOSED.

    Returns the `SentinelResult` and a 1-element `RoleCallRecord` list (one record per
    completion, iter-3 P1-a). A transport error OR a malformed/empty `raw_text` both yield
    `SentinelResult(UNGROUNDED, parsed_ok=False)` — never GROUNDED.
    """
    request = build_sentinel_request(claim, evidence_documents, model_slug=model_slug)
    try:
        response: RoleResponse = transport.complete(request)
        result = parse_sentinel_score(response.raw_text)
        served_model = response.served_model
        raw_text = response.raw_text
    except Exception as exc:  # noqa: BLE001 — deliberate fail-closed; see comment below.
        # FAIL CLOSED: a transport-layer fault must not be read as GROUNDED. We capture a
        # record with the safe (UNGROUNDED, parsed_ok=False) result and the error text as
        # the raw payload so sub-PR-5 can surface the fault rather than silently masking it.
        record = RoleCallRecord(
            role=_ROLE,
            model_slug=model_slug,
            served_model=None,
            raw_text=f"<transport_error>{exc}</transport_error>",
            parsed=_FAIL_CLOSED,
        )
        return _FAIL_CLOSED, [record]

    record = RoleCallRecord(
        role=_ROLE,
        model_slug=model_slug,
        served_model=served_model,
        raw_text=raw_text,
        parsed=result,
    )
    return result, [record]
