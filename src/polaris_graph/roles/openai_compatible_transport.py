"""Real `RoleTransport` for the 3 self-hosted verifier roles (I-meta-002 PR-7 / M1).

This is the first LIVE serving piece of the 4-role architecture. It implements the
sub-PR-4 `RoleTransport` Protocol for the Mirror / Sentinel / Judge roles, which the lock
serves on self-hosted vLLM (`serving_route: vast_self_host*`). It POSTs an OpenAI-compatible
`/v1/chat/completions` to a PER-ROLE `base_url`.

The GENERATOR is HARD-EXCLUDED: it already runs live on OpenRouter via the async
`openrouter_client.py` path and is upstream of the per-claim pipeline, so it is never routed
through this transport. `role_endpoint('generator')` raises.

No-spend / no-network-in-tests boundary: the HTTP client is DEPENDENCY-INJECTED via the
constructor (an `httpx.Client`). Tests pass `httpx.Client(transport=httpx.MockTransport(...))`
returning canned responses — there is NO network in any code path pytest exercises. The
SAME `httpx` library `openrouter_client.py` uses is reused here (sync `httpx.Client` mirrors
the per-axis synchronous `live_judge.py` shape the Protocol was designed against).

Plain-vLLM model-visibility contract (iter-3/iter-4, Codex P1): a plain vLLM
`/v1/chat/completions` model reads ONLY `messages`; a top-level `documents` / `pass2_input` /
`citations` key is NOT guaranteed model-visible. So during normalization the transport
RENDERS the role's full model-visible serving contract INTO the normalized messages —
the evidence documents, the Mirror pass-2 binding (`pass2_input` = pass-1 answer +
`content_hash`), AND (for Mirror pass-1) the explicit `<co>covered text</co:doc_id>`
citation-output instruction. The same allowlisted params are ALSO kept as top-level body keys
(for a managed server that consumes them + for contract/test introspection), but the messages
are the source of truth for what the model reads. The SAME normalized messages go to the HTTP
body AND to `capture_llm_call`, so a prompt-only role never sends/captures an empty payload.

Citation invariant (iter-2, Codex P1): for the self-host path the transport returns
`raw_text` AS-IS (any `<co>` tags intact) with `citations=None`. `mirror_adapter` owns the
`<co>` parse + tag-strip + offset alignment — returning parsed citations alongside
un-stripped `raw_text` would break the Mirror offset contract.

Fail loud (LAW II): a non-200 HTTP status or a malformed body raises `RoleTransportError` —
never a silent empty `RoleResponse` a downstream fail-closed parser would mis-handle.
"""

from __future__ import annotations

import json
import os
from typing import Any

import httpx

from src.polaris_graph.benchmark import pathB_capture as _pathb_capture
from src.polaris_graph.roles.role_transport import (
    RoleRequest,
    RoleResponse,
)

# The OpenAI-compatible chat-completions path appended to each role's base_url.
_CHAT_COMPLETIONS_PATH = "/v1/chat/completions"

# Reuse the openrouter_client timeout default knob (LAW VI): same env var, same fallback.
_TIMEOUT_SECONDS = int(os.getenv("PG_LLM_TIMEOUT_SECONDS", "90"))

# The generator is NOT served here — it runs live on OpenRouter, upstream of this transport.
_EXCLUDED_ROLE = "generator"

# Roles this transport serves. Sourced from the lock at resolve time; this is the static
# guard set so an unknown / excluded role fails before any endpoint lookup.
_SERVED_ROLES = ("mirror", "sentinel", "judge")

# Per-role env var stems: PG_<ROLE>_BASE_URL / PG_<ROLE>_API_KEY (LAW VI: zero hard-coding).
_BASE_URL_ENV_TEMPLATE = "PG_{role}_BASE_URL"
_API_KEY_ENV_TEMPLATE = "PG_{role}_API_KEY"

# Body keys passed through from params as TOP-LEVEL request keys (explicit allowlist — NEVER
# a blind dump of params, so POLARIS-internal keys like `pass2_input` / `citations` never
# reach the vLLM body). `documents` rides at top level for a managed server AND is rendered
# into messages for a plain vLLM model.
_PASSTHROUGH_PARAM_KEYS = (
    "structured_outputs",
    "response_format",
    "documents",
    "max_tokens",
)

# Param keys consumed by message-rendering (model-visibility), NOT sent as body keys.
_DOCUMENTS_KEY = "documents"
_PASS2_INPUT_KEY = "pass2_input"
_CITATIONS_KEY = "citations"
_SYSTEM_KEY = "system"

# pass2_input field keys (mirror_contract.build_pass2_input shape).
_ANSWER_TEXT_KEY = "answer_text"
_CONTENT_HASH_KEY = "content_hash"


class RoleTransportError(RuntimeError):
    """A self-host verifier completion failed loudly.

    Raised on a non-200 HTTP status, a transport-layer error, or a malformed response body
    (no `choices` / no assistant content). The Sentinel adapter converts this to a fail-CLOSED
    `SentinelResult(UNGROUNDED)`; the Judge adapter lets it propagate (fail LOUD). Either way
    a downstream parser never sees a fabricated empty success.
    """


def role_endpoint(role: str) -> tuple[str, str, str]:
    """Resolve `(base_url, api_key, model_slug)` for a self-hosted verifier role.

    Reads `PG_<ROLE>_BASE_URL` + `PG_<ROLE>_API_KEY` ONLY and sources the pinned `model_slug`
    from the runtime architecture lock. The generator is HARD-EXCLUDED (it serves live on
    OpenRouter upstream of this transport): asking for it — or any role not in `_SERVED_ROLES`
    — raises `ValueError`.

    No-leak (Codex M3 key_handling_ruling = hard_require, P2 #3): there is NO
    `OPENROUTER_API_KEY` fallback. A self-host verifier must never receive the OpenRouter key.
    When `PG_<ROLE>_API_KEY` is unset, `api_key` is `""` and `complete()` OMITS the
    Authorization header entirely (a keyless self-host vLLM needs none) — it never sends an
    empty `Authorization: Bearer ` value. This mirrors the M2 `verify_serving_identity` probe.

    Fails loud (LAW II / LAW VI) when the role's `PG_<ROLE>_BASE_URL` is unset: a self-host
    role with no endpoint configured is a deployment error, never a silent default.
    """
    if role == _EXCLUDED_ROLE:
        raise ValueError(
            f"role {role!r} is not served by this transport — the generator runs live on "
            "OpenRouter (openrouter_client.py), upstream of the per-claim verifier path."
        )
    if role not in _SERVED_ROLES:
        raise ValueError(
            f"role {role!r} is not a self-hosted verifier role {_SERVED_ROLES}"
        )

    role_token = role.upper()
    base_url = os.getenv(_BASE_URL_ENV_TEMPLATE.format(role=role_token))
    if not base_url:
        raise ValueError(
            f"{_BASE_URL_ENV_TEMPLATE.format(role=role_token)} is not set; the self-hosted "
            f"{role!r} endpoint must be configured (LAW VI)."
        )
    # No-leak (P2 #3): PG_<ROLE>_API_KEY ONLY — NEVER an OPENROUTER_API_KEY fallback. Unset
    # -> "" -> complete() omits the Authorization header (keyless self-host vLLM is valid).
    api_key = os.getenv(_API_KEY_ENV_TEMPLATE.format(role=role_token), "")

    model_slug = _lock_model_slug(role)
    return base_url.rstrip("/"), api_key, model_slug


def _lock_model_slug(role: str) -> str:
    """Pinned `model_slug` for `role` from the runtime architecture lock.

    Imported lazily so importing this module never forces the lock loader (and its yaml read)
    at import time. The lock is the single machine-readable source of truth (LAW VI).
    """
    from scripts.architecture.verify_lock import load_lock

    lock = load_lock()
    return lock["required_roles"][role]["model_slug"]


def _render_documents_message(documents: list[dict]) -> dict | None:
    """Render `params['documents']` as an explicit, model-visible evidence message.

    Each document is serialized as `doc_id` + its text so a plain vLLM model actually reads
    the evidence (a top-level `documents` body key is not guaranteed model-visible). Returns
    None when there are no documents (nothing to render).
    """
    if not documents:
        return None
    lines = ["EVIDENCE DOCUMENTS (cite ONLY these doc_ids):"]
    for doc in documents:
        doc_id = doc.get("doc_id", "")
        text = doc.get("text", "")
        lines.append(f"[{doc_id}] {text}")
    return {"role": "user", "content": "\n".join(lines)}


def _render_citation_instruction(documents: list[dict]) -> dict:
    """Render the Mirror pass-1 `<co>` citation-OUTPUT contract as a model-visible message.

    A plain vLLM model treats `params['citations']=True` as nothing — it returns plain prose,
    `parse_cohere_citations` finds no spans, and `MirrorCitationError` fails closed on every
    claim. So when citations are requested the transport explicitly INSTRUCTS the model to
    cite supported spans in the EXACT self-host form `<co>covered text</co:doc_id>` using ONLY
    the supplied doc_ids (iter-4, Codex P1).
    """
    doc_ids = [doc.get("doc_id", "") for doc in documents]
    doc_ids_rendered = ", ".join(doc_id for doc_id in doc_ids if doc_id)
    instruction = (
        "CITATION OUTPUT FORMAT (required): for every supported claim, wrap the covered "
        "text in the EXACT form <co>covered text</co:doc_id>, where doc_id is one of the "
        f"supplied evidence doc_ids ({doc_ids_rendered}). Cite ONLY these doc_ids; do not "
        "invent identifiers. Text that is not grounded in a supplied document must NOT be "
        "wrapped in a <co> span."
    )
    return {"role": "user", "content": instruction}


def _render_pass2_input_message(pass2_input: dict) -> dict:
    """Render the Mirror pass-2 binding (`pass2_input`) as a model-visible message.

    The pass-2 model must classify the SAME artifact pass-1 produced; the binding is the
    `content_hash` (over pass-1 answer + ordered citation bindings). A top-level `pass2_input`
    key is not model-visible, so the answer text AND the literal `content_hash` value are
    rendered into a message the model classifies (iter-3, Codex P1).
    """
    answer_text = pass2_input.get(_ANSWER_TEXT_KEY, "")
    content_hash = pass2_input.get(_CONTENT_HASH_KEY, "")
    content = (
        "PASS-2 CLASSIFICATION INPUT — classify EXACTLY this bound pass-1 artifact.\n"
        f"content_hash: {content_hash}\n"
        f"answer_text:\n{answer_text}"
    )
    return {"role": "user", "content": content}


def _normalize_messages(request: RoleRequest) -> list[dict]:
    """Build the normalized message list that is the source of truth for the model.

    Rules:
      - Evidence documents (`params['documents']`) are rendered FIRST as a leading evidence
        message so they are model-visible BEFORE the role's instruction/claim.
      - If `request.messages` is set (Sentinel), the rendered evidence is PREPENDED and the
        original messages follow UNCHANGED — so the final `<guardian>` user block stays LAST
        (Codex P2: rendered context model-visible, guardian remains the last turn).
      - Else build from `request.prompt`: optional system message (`params['system']`), the
        rendered evidence, the Mirror pass-1 `<co>` citation instruction (when
        `params['citations']` is true), the Mirror pass-2 binding message (when
        `params['pass2_input']` is present), then the prompt as the final user message.
    """
    params = request.params or {}
    documents = params.get(_DOCUMENTS_KEY) or []
    evidence_message = _render_documents_message(documents)

    if request.messages is not None:
        # Sentinel path: evidence first (model-visible), original turns last (guardian last).
        prefix = [evidence_message] if evidence_message is not None else []
        return [*prefix, *request.messages]

    # Prompt path (Judge, Mirror pass-1, Mirror pass-2).
    if request.prompt is None:
        raise RoleTransportError(
            f"role {request.role!r} request carries neither messages nor prompt"
        )

    messages: list[dict] = []
    system = params.get(_SYSTEM_KEY)
    if system:
        messages.append({"role": "system", "content": system})
    if evidence_message is not None:
        messages.append(evidence_message)
    if params.get(_CITATIONS_KEY):
        # Mirror pass-1: make the <co> output contract model-visible (iter-4).
        messages.append(_render_citation_instruction(documents))
    pass2_input = params.get(_PASS2_INPUT_KEY)
    if pass2_input:
        # Mirror pass-2: make the pass-1 binding (content_hash) model-visible (iter-3).
        messages.append(_render_pass2_input_message(pass2_input))
    messages.append({"role": "user", "content": request.prompt})
    return messages


def _build_body(
    request: RoleRequest, model_slug: str, normalized_messages: list[dict]
) -> dict[str, Any]:
    """Assemble the OpenAI-compatible request body.

    `model` is the lock-sourced slug from `role_endpoint` (single config source, LAW VI; the
    adapters pass the same slug as `request.model_slug`, so they coincide). The normalized
    messages are the SAME list passed to capture. Only the explicit `_PASSTHROUGH_PARAM_KEYS`
    allowlist is forwarded as top-level body keys — POLARIS-internal keys (`pass2_input`,
    `citations`, `system`) never reach the vLLM body.
    """
    body: dict[str, Any] = {
        "model": model_slug,
        "messages": normalized_messages,
    }
    params = request.params or {}
    for key in _PASSTHROUGH_PARAM_KEYS:
        if key in params and params[key] is not None:
            body[key] = params[key]
    return body


_THINK_OPEN = "<think>"
_THINK_CLOSE = "</think>"


def _separate_reasoning(content: object, model_repr: str) -> tuple[object, str | None]:
    """Split verifier REASONING from the bare verdict/body (I-meta-002-q1b #939).

    Returns `(bare, reasoning)`. A served reasoning-model can deliver its reasoning two ways:
    a separate `reasoning_content` field (handled by the caller) OR inline as a LEADING
    `<think>...</think>` block in `content`. Here we handle the inline case: only a LEADING
    block is split (never a mid-body search/replace) so any Mirror `<co>...</co:doc_id>` spans
    that FOLLOW are byte-preserved and the adapter's offset alignment over the returned bare
    text stays internally consistent.

    Fail loud (LAW II): a `<think>` opened with NO closing `</think>` is a malformed verifier
    response — raise rather than feed a half-emitted reasoning block to a strict verdict parser.
    """
    if not (isinstance(content, str) and content.lstrip().startswith(_THINK_OPEN)):
        return content, None
    stripped = content.lstrip()
    close_idx = stripped.find(_THINK_CLOSE)
    if close_idx == -1:
        raise RoleTransportError(
            f"self-host response content opened a <think> block with no closing </think> "
            f"(model={model_repr}); a half-emitted reasoning block is a malformed verifier "
            f"response (fail-closed, never parsed as a verdict)."
        )
    reasoning = stripped[len(_THINK_OPEN):close_idx].strip() or None
    bare = stripped[close_idx + len(_THINK_CLOSE):].strip()
    return bare, reasoning


def _sanitize_raw_for_capture(raw: dict, *, bare_text: object) -> dict:
    """Return a copy of `raw` with verifier REASONING removed, for Path-B capture (I-meta-002-q1b
    #939, Codex diff P1 no-leak). Drops any `reasoning_content` from the assistant message and
    replaces its `content` with the separated bare verdict, so reasoning is never persisted
    outside the dedicated `four_role_role_calls.jsonl`. Served-identity fields (`model`, `usage`,
    `_pathb_served`, `system_fingerprint`, provider) are preserved so M4 served==pinned is
    unaffected. The original `raw` is NOT mutated (shallow-copied along the touched path only).
    """
    sanitized = dict(raw)
    choices = raw.get("choices")
    if isinstance(choices, list) and choices and isinstance(choices[0], dict):
        first_choice = dict(choices[0])
        message = first_choice.get("message")
        if isinstance(message, dict):
            clean_message = dict(message)
            clean_message.pop("reasoning_content", None)
            clean_message["content"] = bare_text
            first_choice["message"] = clean_message
        sanitized["choices"] = [first_choice, *choices[1:]]
    return sanitized


def _parse_response(raw: dict) -> tuple[object, str | None, dict | None, str | None]:
    """Extract `(raw_text, served_model, usage, reasoning)` from an OpenAI-compatible body.

    Fail loud (LAW II): a missing `choices` array or an absent assistant `content` raises
    `RoleTransportError` rather than returning an empty string a fail-closed parser would
    mis-read as a (deliberately) empty completion. Verifier REASONING is separated from the
    bare verdict/body here (I-meta-002-q1b #939) so the verdict parsers only ever see the bare
    answer (no "soap") and the reasoning is captured for line-by-line review.
    """
    choices = raw.get("choices")
    if not choices:
        raise RoleTransportError(
            f"self-host response carried no choices (model={raw.get('model')!r})"
        )
    # (Codex diff P2) Harden to the fail-loud contract: a non-dict choice (e.g. `choices: [null]`)
    # must raise RoleTransportError, not crash with AttributeError; and a BLANK completion is a
    # transport failure for a verifier role (empty is never a valid Sentinel/Judge/Mirror answer),
    # so it raises rather than returning a misleading empty RoleResponse.
    first_choice = choices[0]
    if not isinstance(first_choice, dict):
        raise RoleTransportError(
            f"self-host response choice was not an object (model={raw.get('model')!r})"
        )
    message = first_choice.get("message")
    if not isinstance(message, dict):
        raise RoleTransportError(
            f"self-host response choice carried no message object (model={raw.get('model')!r})"
        )
    content = message.get("content")
    model_repr = f"{raw.get('model')!r}"
    # Two served-reasoning shapes. Prefer the explicit separate `reasoning_content` field (vLLM
    # reasoning-parser path: `content` is already the bare verdict). Otherwise split a leading
    # inline `<think>` block out of `content`.
    reasoning_field = message.get("reasoning_content")
    if isinstance(reasoning_field, str) and reasoning_field.strip():
        bare: object = content
        reasoning: str | None = reasoning_field
    else:
        bare, reasoning = _separate_reasoning(content, model_repr)
    # Post-split blank guard (Codex brief note): a verifier role MUST return a non-blank bare
    # verdict/body across BOTH paths. A reasoning-only / think-only / empty-content response is a
    # transport failure, never a deliberately-empty answer — fail loud identically either way.
    if bare is None or (isinstance(bare, str) and not bare.strip()):
        raise RoleTransportError(
            f"self-host response choice carried no/blank message content after reasoning "
            f"separation (model={model_repr})"
        )
    served_model = raw.get("model")
    usage = raw.get("usage")
    return bare, served_model, usage, reasoning


class OpenAICompatibleRoleTransport:
    """Sync `RoleTransport` for the self-hosted Mirror / Sentinel / Judge verifier roles.

    The `httpx.Client` is INJECTED so tests pass an in-process stub (no network, no spend).
    Each `complete()` resolves the per-role endpoint, normalizes the payload (rendering the
    role's model-visible serving contract into messages), POSTs `/v1/chat/completions`,
    captures the call under the Path-B gate, and returns a `RoleResponse`.
    """

    def __init__(self, http_client: httpx.Client) -> None:
        self._http_client = http_client

    def complete(self, request: RoleRequest) -> RoleResponse:
        """Perform one self-host completion for `request`. SYNC. Fails loud on error.

        Generator requests raise via `role_endpoint`. The normalized messages are the SAME
        list POSTed to the body AND passed to `capture_llm_call` (so a prompt-only role never
        captures an empty payload). The captured raw is augmented with
        `_pathb_served={'endpoint': base_url, 'model': served_model}` so M4's served==pinned
        check can consume the endpoint (a self-host vLLM response carries no provider_name).
        """
        base_url, api_key, model_slug = role_endpoint(request.role)
        normalized_messages = _normalize_messages(request)
        body = _build_body(request, model_slug, normalized_messages)
        url = f"{base_url}{_CHAT_COMPLETIONS_PATH}"
        # No-leak (Codex M3 P2 #3): send Authorization ONLY when a per-role key is configured.
        # A keyless self-host vLLM (launched without --api-key) needs none; we never send an
        # empty `Authorization: Bearer ` value nor a foreign OpenRouter key. Mirrors the M2
        # verify_serving_identity probe's keyless behavior exactly.
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        with _pathb_capture.llm_role(request.role):
            try:
                http_response = self._http_client.post(
                    url, json=body, headers=headers, timeout=_TIMEOUT_SECONDS
                )
            except httpx.HTTPError as exc:
                raise RoleTransportError(
                    f"self-host {request.role!r} transport error at {url}: {exc}"
                ) from exc

            if http_response.status_code != httpx.codes.OK:
                raise RoleTransportError(
                    f"self-host {request.role!r} returned HTTP {http_response.status_code} "
                    f"at {url}"
                )
            try:
                raw = http_response.json()
            except (json.JSONDecodeError, ValueError) as exc:
                raise RoleTransportError(
                    f"self-host {request.role!r} returned a non-JSON body at {url}: {exc}"
                ) from exc

            # I-meta-002-q1b (#939): reasoning is separated from the bare verdict/body HERE so
            # the verdict parsers only ever see the bare answer (no "soap").
            raw_text, served_model, usage, reasoning = _parse_response(raw)

            # Augment the captured raw with the served block BEFORE capture so M4's
            # served==pinned check can read the endpoint a self-host role was served from
            # (no fabricated provider_name for vLLM).
            raw["_pathb_served"] = {"endpoint": base_url, "model": served_model}
            # I-meta-002-q1b (#939) no-leak (Codex diff P1): Path-B capture must NEVER carry
            # verifier reasoning. Sanitize the response for capture — drop `reasoning_content`
            # and replace the assistant content with the separated BARE verdict — so reasoning
            # lives ONLY in the RoleCallRecord + four_role_role_calls.jsonl, never in the capture
            # channel, regardless of what build_response_metadata happens to persist today.
            _pathb_capture.capture_llm_call(
                role=request.role,
                messages=normalized_messages,
                raw_response=_sanitize_raw_for_capture(raw, bare_text=raw_text),
            )

        # Self-host citation invariant (iter-2): return raw_text AS-IS (<co> tags intact),
        # citations=None — mirror_adapter owns the parse/strip/offset alignment. `reasoning`
        # rides alongside (never concatenated into raw_text) for separate persistence.
        return RoleResponse(
            raw_text=raw_text,
            served_model=served_model,
            usage=usage,
            citations=None,
            reasoning=reasoning,
        )
