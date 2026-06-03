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

import os

# I-meta-008: the Sentinel fail-closed catch must NOT swallow a budget-cap breach. The hook in
# RecordingTransport.complete raises BudgetExceededError from inside transport.complete(); a
# typed re-raise guard ahead of the broad `except` keeps the cap a HARD ABORT (never a
# fail-closed UNGROUNDED verdict). Mirrors entailment_judge.py:255-258.
import src.polaris_graph.llm.openrouter_client as _orc

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
    parse_sentinel_grounded_token,
    parse_sentinel_score,
)

_ROLE = "sentinel"

# === GROUNDEDNESS MODE selection (I-run11-002 L1, LAW VI) ====================================
# Two distinct (prompt, parser) contracts, selected by `PG_SENTINEL_GROUNDEDNESS_MODE`:
#   - "noninverted" (DEFAULT for the OpenRouter/benchmark Sentinel): a DIRECT one-word
#     GROUNDED/UNGROUNDED prompt, parsed by `parse_sentinel_grounded_token`. Run 11 proved the
#     general `ibm-granite/granite-4.1-8b` ignores the inverted Guardian instruction and answers
#     naturally, so the inverted contract mislabeled every grounded claim as UNGROUNDED. The
#     non-inverted prompt discriminates cleanly on the same general granite model
#     (outputs/audits/I-run11-002/l1_groundedness_probe.md).
#   - "guardian" (the SOVEREIGN self-host Sentinel): the INVERTED `<guardian>` block + the strict
#     `<score>yes|no</score>` parser (yes=risk=UNGROUNDED). KEPT BYTE-FOR-BYTE because the
#     task-trained self-host `granite-guardian-4.1-8b` is trained on the yes=risk polarity.
#
# DEFAULT WIRING (the runtime-desync guard): when `PG_SENTINEL_GROUNDEDNESS_MODE` is unset, the
# mode is DERIVED from `PG_FOUR_ROLE_TRANSPORT` so the prompt can never silently desync from the
# served model — "self_host" (the sovereign granite-Guardian route) defaults to "guardian";
# "openrouter"/unset (the benchmark general-granite route) defaults to "noninverted". An explicit
# `PG_SENTINEL_GROUNDEDNESS_MODE` always overrides. Both read lazily (per call) so a post-import
# override is honored (mirrors `role_reasoning_enabled` / `four_role_transport_mode`).
_GROUNDEDNESS_MODE_ENV = "PG_SENTINEL_GROUNDEDNESS_MODE"
_MODE_NONINVERTED = "noninverted"
_MODE_GUARDIAN = "guardian"
# The transport env the default derives from (literals kept in sync with run_gate_b.py's
# `_FOUR_ROLE_TRANSPORT_ENV` / `_TRANSPORT_SELF_HOST`; NOT imported, to avoid a scripts->src cycle).
_FOUR_ROLE_TRANSPORT_ENV = "PG_FOUR_ROLE_TRANSPORT"
_TRANSPORT_SELF_HOST = "self_host"


def sentinel_groundedness_mode() -> str:
    """Resolve the active Sentinel groundedness mode (LAW VI). Returns "noninverted" | "guardian".

    Precedence: an explicit `PG_SENTINEL_GROUNDEDNESS_MODE` ("noninverted" | "guardian") wins.
    When unset (or set to an unrecognized value), DERIVE from `PG_FOUR_ROLE_TRANSPORT` so the
    prompt+parser never desync from the served model: "self_host" -> "guardian" (sovereign
    granite-Guardian); anything else (incl. the "openrouter" default) -> "noninverted" (benchmark
    general granite). The DEFAULT for the OpenRouter/benchmark Sentinel is therefore "noninverted".
    """
    override = os.getenv(_GROUNDEDNESS_MODE_ENV)
    if override is not None:
        token = override.strip().lower()
        if token in (_MODE_NONINVERTED, _MODE_GUARDIAN):
            return token
    # Unset/unrecognized: derive from the transport so the sovereign path gets guardian.
    transport = os.getenv(_FOUR_ROLE_TRANSPORT_ENV, "").strip().lower()
    if transport == _TRANSPORT_SELF_HOST:
        return _MODE_GUARDIAN
    return _MODE_NONINVERTED


# The prescribed groundedness instruction wrapped in the final user `<guardian>` block.
# Documents are carried separately in params["documents"] (Granite's `documents` channel),
# NOT inlined here, so the calling convention stays auditable. SOVEREIGN ("guardian") mode ONLY.
_GUARDIAN_BLOCK = (
    "<guardian>groundedness</guardian>\n"
    "Assess whether the assistant's claim is grounded in the provided documents. "
    "Respond with exactly <score>yes</score> if the claim is NOT grounded (risk present) "
    "or <score>no</score> if it IS grounded (no risk). Output only the score element."
)

# The NON-INVERTED groundedness instruction (BENCHMARK / "noninverted" mode). VALIDATED VERBATIM
# by the L1 probe (scripts/diagnostics/sentinel_groundedness_probe.py `_NONINVERTED_BLOCK`):
# `ibm-granite/granite-4.1-8b` returned GROUNDED on the verbatim-quoted (grounded) fixture and
# UNGROUNDED on the on-topic-fabricated fixture under this exact wording. Asks for ONE word so
# `parse_sentinel_grounded_token` (word-boundary GROUNDED|UNGROUNDED) can read it. Documents are
# rendered model-visible by `_normalize_messages` (the leading evidence message), identical to the
# guardian path; only the FINAL user instruction differs.
_NONINVERTED_BLOCK = (
    "You are a strict groundedness checker. Decide whether the assistant's CLAIM is fully "
    "supported by (entailed by) the EVIDENCE DOCUMENTS shown above. A claim is GROUNDED only if "
    "every factual assertion in it — including any number, percentage, or named entity — is "
    "directly stated in or directly entailed by the documents. If the claim adds any fact, number, "
    "or detail not present in the documents, it is UNGROUNDED.\n"
    "Answer with EXACTLY one word: GROUNDED or UNGROUNDED. Output only that single word."
)

# The fail-closed result returned on transport error / malformed output. NEVER GROUNDED.
_FAIL_CLOSED = SentinelResult(SentinelVerdict.UNGROUNDED, parsed_ok=False)


def build_sentinel_request(
    claim: str,
    evidence_documents: list[EvidenceDocument],
    *,
    model_slug: str,
    mode: str | None = None,
) -> RoleRequest:
    """Build a Sentinel groundedness request for the active mode (I-run11-002 L1).

    Layout (F3, identical across modes): assistant turn = the claim under check; final user turn =
    the groundedness instruction; documents ride in `params["documents"]` (Granite's documents
    channel). NO structured-output spec — both modes emit free text the contract parses, not JSON.

    `mode` selects the FINAL user instruction:
      - "guardian"    -> the INVERTED `<guardian>` block (sovereign self-host granite-Guardian).
      - "noninverted" -> the DIRECT one-word GROUNDED/UNGROUNDED block (benchmark general granite).
    When `mode` is None it resolves from `sentinel_groundedness_mode()` (env-gated, LAW VI;
    DEFAULT "noninverted" for the OpenRouter/benchmark route, "guardian" for self_host).
    """
    resolved_mode = mode if mode is not None else sentinel_groundedness_mode()
    instruction = _GUARDIAN_BLOCK if resolved_mode == _MODE_GUARDIAN else _NONINVERTED_BLOCK
    messages = [
        {"role": "assistant", "content": claim},
        {"role": "user", "content": instruction},
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
    mode: str | None = None,
) -> tuple[SentinelResult, list[RoleCallRecord]]:
    """Call the transport once and parse the groundedness output, FAIL CLOSED.

    Returns the `SentinelResult` and a 1-element `RoleCallRecord` list (one record per
    completion, iter-3 P1-a). A transport error OR a malformed/empty `raw_text` both yield
    `SentinelResult(UNGROUNDED, parsed_ok=False)` — never GROUNDED, in EITHER mode.

    `mode` (None -> `sentinel_groundedness_mode()`, env-gated, LAW VI) selects BOTH the prompt
    (via `build_sentinel_request`) AND the parser, so they always pair correctly:
      - "guardian"    -> inverted `<score>yes|no</score>` parser (`parse_sentinel_score`).
      - "noninverted" -> direct GROUNDED/UNGROUNDED parser (`parse_sentinel_grounded_token`).
    """
    resolved_mode = mode if mode is not None else sentinel_groundedness_mode()
    parser = (
        parse_sentinel_score
        if resolved_mode == _MODE_GUARDIAN
        else parse_sentinel_grounded_token
    )
    request = build_sentinel_request(
        claim, evidence_documents, model_slug=model_slug, mode=resolved_mode
    )
    try:
        response: RoleResponse = transport.complete(request)
        result = parser(response.raw_text)
        served_model = response.served_model
        raw_text = response.raw_text
    except _orc.BudgetExceededError:
        # I-meta-008: a budget-cap breach (raised by the RecordingTransport cost hook inside
        # transport.complete) is a HARD ABORT, never a fail-closed UNGROUNDED verdict. Re-raise
        # BEFORE the broad except below so the cap actually bites on the Sentinel call.
        raise
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
