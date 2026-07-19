"""Tests for the self-host verifier RoleTransport (I-meta-002 PR-7 / M1).

ALL with an INJECTED `httpx.Client(transport=httpx.MockTransport(...))` — NO network, no
spend. Each test wires a canned-response handler that records the request it saw, so we can
assert per-role base_url routing, payload normalization (prompt -> messages), model-visibility
of params rendered into the messages (Mirror pass-2 content_hash, pass-1 <co> citation
instruction, evidence doc_ids), the Cohere <co> raw-text-as-is invariant, the served-endpoint
capture for M4, and the fail-loud `RoleTransportError` contract.

Also extends the build_response_metadata test family to prove the additive `endpoint` key
surfaces from `_pathb_served` when present and is DROPPED when absent (backward compatible).
"""

from __future__ import annotations

import json

import httpx
import pytest

from src.polaris_graph.benchmark import benchmark_run_capture as pc
from src.polaris_graph.roles.openai_compatible_transport import (
    OpenAICompatibleRoleTransport,
    RoleTransportError,
    _sanitize_raw_for_capture,
    role_endpoint,
)
from src.polaris_graph.roles.role_transport import RoleRequest, RoleResponse

# Lock-pinned slugs (config/architecture/polaris_runtime_lock.yaml). I-run11-004: Mirror
# z-ai/glm-5.1, Sentinel CERTIFIED minimax/minimax-m2 (decomposition), Judge qwen.
_MIRROR_SLUG = "z-ai/glm-5.1"
_SENTINEL_SLUG = "minimax/minimax-m2"
_JUDGE_SLUG = "qwen/qwen3.6-35b-a3b"

_MIRROR_BASE = "http://mirror.internal:8001"
_SENTINEL_BASE = "http://sentinel.internal:8002"
_JUDGE_BASE = "http://judge.internal:8003"


@pytest.fixture(autouse=True)
def _role_endpoints(monkeypatch):
    """Configure per-role base_url + api_key env for every test (LAW VI)."""
    monkeypatch.setenv("PG_MIRROR_BASE_URL", _MIRROR_BASE)
    monkeypatch.setenv("PG_SENTINEL_BASE_URL", _SENTINEL_BASE)
    monkeypatch.setenv("PG_JUDGE_BASE_URL", _JUDGE_BASE)
    monkeypatch.setenv("PG_MIRROR_API_KEY", "mirror-key")
    monkeypatch.setenv("PG_SENTINEL_API_KEY", "sentinel-key")
    # Judge sets NO own key. OPENROUTER_API_KEY is present in the env but (Codex M3 no-leak,
    # P2 #3) the verifier transport must NEVER fall back to it — judge resolves to "" and
    # complete() omits the Authorization header entirely.
    monkeypatch.delenv("PG_JUDGE_API_KEY", raising=False)
    monkeypatch.setenv("OPENROUTER_API_KEY", "fallback-key")
    yield


@pytest.fixture(autouse=True)
def _clean_capture():
    pc.clear_pathB_capture()
    yield
    pc.clear_pathB_capture()


def _make_transport(handler) -> OpenAICompatibleRoleTransport:
    """Build a transport with an INJECTED MockTransport client (no network)."""
    client = httpx.Client(transport=httpx.MockTransport(handler))
    return OpenAICompatibleRoleTransport(client)


def _recording_handler(*, served_model: str, content: str, status_code: int = 200):
    """A MockTransport handler that records each request and returns a canned completion."""
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["headers"] = dict(request.headers)
        seen["body"] = json.loads(request.content.decode("utf-8"))
        payload = {
            "model": served_model,
            "choices": [{"message": {"role": "assistant", "content": content}}],
            "usage": {"prompt_tokens": 7, "completion_tokens": 3},
        }
        return httpx.Response(status_code, json=payload)

    return handler, seen


# --------------------------------------------------------------------------------------
# role_endpoint resolver + generator exclusion
# --------------------------------------------------------------------------------------
def test_role_endpoint_resolves_per_role_base_url_and_lock_slug():
    base, key, slug = role_endpoint("mirror")
    assert base == _MIRROR_BASE
    assert key == "mirror-key"
    assert slug == _MIRROR_SLUG

    base, key, slug = role_endpoint("sentinel")
    assert base == _SENTINEL_BASE
    assert key == "sentinel-key"
    assert slug == _SENTINEL_SLUG


def test_role_endpoint_no_openrouter_fallback_when_key_unset():
    # No-leak (Codex M3 P2 #3): judge sets no PG_JUDGE_API_KEY and OPENROUTER_API_KEY is
    # present in env, but the verifier transport must NOT fall back to it — key resolves to "".
    base, key, slug = role_endpoint("judge")
    assert base == _JUDGE_BASE
    assert key == ""
    assert slug == _JUDGE_SLUG


def test_role_endpoint_generator_is_excluded():
    with pytest.raises(ValueError, match="generator"):
        role_endpoint("generator")


def test_role_endpoint_unknown_role_raises():
    with pytest.raises(ValueError):
        role_endpoint("evaluator")


def test_complete_generator_raises_before_any_http():
    handler, seen = _recording_handler(served_model="x", content="y")
    transport = _make_transport(handler)
    with pytest.raises(ValueError, match="generator"):
        transport.complete(RoleRequest(role="generator", model_slug="x", prompt="hi"))
    assert seen == {}  # no HTTP attempted


def test_role_endpoint_missing_base_url_fails_loud(monkeypatch):
    monkeypatch.delenv("PG_MIRROR_BASE_URL", raising=False)
    with pytest.raises(ValueError, match="PG_MIRROR_BASE_URL"):
        role_endpoint("mirror")


# --------------------------------------------------------------------------------------
# per-role base_url routing
# --------------------------------------------------------------------------------------
def test_per_role_base_url_routing():
    for role, base, slug in (
        ("mirror", _MIRROR_BASE, _MIRROR_SLUG),
        ("sentinel", _SENTINEL_BASE, _SENTINEL_SLUG),
        ("judge", _JUDGE_BASE, _JUDGE_SLUG),
    ):
        handler, seen = _recording_handler(served_model=slug, content="VERIFIED")
        transport = _make_transport(handler)
        if role == "sentinel":
            req = RoleRequest(
                role=role,
                model_slug=slug,
                messages=[
                    {"role": "assistant", "content": "claim"},
                    {"role": "user", "content": "<guardian>groundedness</guardian>"},
                ],
                params={"documents": [{"doc_id": "d1", "text": "evidence"}]},
            )
        else:
            req = RoleRequest(role=role, model_slug=slug, prompt="q", params={})
        transport.complete(req)
        assert seen["url"] == f"{base}/v1/chat/completions"
        assert seen["body"]["model"] == slug


# --------------------------------------------------------------------------------------
# No-leak Authorization-header contract (Codex M3 key_handling_ruling=hard_require, P2 #3)
# --------------------------------------------------------------------------------------
def test_per_role_key_sets_bearer_authorization():
    # A role with its own PG_<ROLE>_API_KEY sends `Authorization: Bearer <that key>`.
    handler, seen = _recording_handler(served_model=_MIRROR_SLUG, content="ok")
    transport = _make_transport(handler)
    transport.complete(RoleRequest(role="mirror", model_slug=_MIRROR_SLUG, prompt="q"))
    # httpx lowercases header keys when round-tripped through dict(request.headers).
    assert seen["headers"].get("authorization") == "Bearer mirror-key"


def test_unset_key_omits_authorization_and_does_not_use_openrouter():
    # Judge has NO own key; OPENROUTER_API_KEY is present in env (autouse fixture) but must
    # NOT be used. The Authorization header is OMITTED ENTIRELY — never `Bearer ` (empty) and
    # never the OpenRouter fallback key.
    handler, seen = _recording_handler(served_model=_JUDGE_SLUG, content="VERIFIED")
    transport = _make_transport(handler)
    transport.complete(RoleRequest(role="judge", model_slug=_JUDGE_SLUG, prompt="decide"))
    assert "authorization" not in seen["headers"]
    # Belt-and-suspenders: the OpenRouter fallback key never appears in ANY header value.
    assert "fallback-key" not in json.dumps(seen["headers"])


# --------------------------------------------------------------------------------------
# prompt-only normalization -> messages, SAME messages reach capture
# --------------------------------------------------------------------------------------
def test_prompt_only_normalizes_to_messages_and_capture_gets_same_messages():
    pc.register_pathB_capture()
    handler, seen = _recording_handler(served_model=_JUDGE_SLUG, content="VERIFIED")
    transport = _make_transport(handler)

    req = RoleRequest(
        role="judge",
        model_slug=_JUDGE_SLUG,
        prompt="Decide the verdict.",
        params={"structured_outputs": {"choice": ["VERIFIED"]}, "max_tokens": 16},
    )
    transport.complete(req)

    body_messages = seen["body"]["messages"]
    assert body_messages[-1] == {"role": "user", "content": "Decide the verdict."}

    calls = pc.collected_calls()
    assert len(calls) == 1
    assert calls[0]["role"] == "judge"
    # capture saw NON-EMPTY messages (not an empty prompt) — same request_hash as the body.
    assert calls[0]["prompt_messages_present"] is True
    assert calls[0]["request_hash"] == pc.request_hash(body_messages)


def test_judge_structured_outputs_and_max_tokens_passthrough():
    handler, seen = _recording_handler(served_model=_JUDGE_SLUG, content="PARTIAL")
    transport = _make_transport(handler)
    req = RoleRequest(
        role="judge",
        model_slug=_JUDGE_SLUG,
        prompt="decide",
        params={"structured_outputs": {"choice": ["VERIFIED", "PARTIAL"]}, "max_tokens": 16},
    )
    transport.complete(req)
    body = seen["body"]
    assert body["structured_outputs"] == {"choice": ["VERIFIED", "PARTIAL"]}
    assert body["max_tokens"] == 16  # Judge-set bound is honored, not dropped
    # POLARIS-internal-only keys never reach the body.
    assert "pass2_input" not in body
    assert "citations" not in body
    assert "system" not in body


# --------------------------------------------------------------------------------------
# Sentinel: messages preserved, evidence model-visible, guardian stays LAST (Codex P2)
# --------------------------------------------------------------------------------------
def test_sentinel_messages_documents_rendered_guardian_stays_last():
    handler, seen = _recording_handler(served_model=_SENTINEL_SLUG, content="<score>no</score>")
    transport = _make_transport(handler)
    guardian = {"role": "user", "content": "<guardian>groundedness</guardian> assess."}
    req = RoleRequest(
        role="sentinel",
        model_slug=_SENTINEL_SLUG,
        messages=[{"role": "assistant", "content": "HbA1c fell 2.3 points"}, guardian],
        params={"documents": [{"doc_id": "doc_surmount1", "text": "HbA1c fell 2.3 points."}]},
    )
    transport.complete(req)
    body_messages = seen["body"]["messages"]
    # Guardian block remains the LAST turn.
    assert body_messages[-1] == guardian
    # Evidence doc_id is rendered into an EARLIER (model-visible) message.
    serialized_prefix = json.dumps(body_messages[:-1])
    assert "doc_surmount1" in serialized_prefix
    # documents also ride at top level.
    assert seen["body"]["documents"] == [{"doc_id": "doc_surmount1", "text": "HbA1c fell 2.3 points."}]


# --------------------------------------------------------------------------------------
# Mirror pass-2: content_hash + documents are model-visible IN the messages
# --------------------------------------------------------------------------------------
def test_mirror_pass2_content_hash_and_documents_in_messages():
    handler, seen = _recording_handler(
        served_model=_MIRROR_SLUG, content='{"classification": "VERIFIED", "content_hash": "abc123"}'
    )
    transport = _make_transport(handler)
    content_hash = "deadbeefcafe0001"
    req = RoleRequest(
        role="mirror",
        model_slug=_MIRROR_SLUG,
        prompt="Classify the bound pass-1 artifact and return JSON.",
        params={
            "response_format": {"type": "json_object"},
            "pass2_input": {"answer_text": "Grounded answer.", "content_hash": content_hash},
            "documents": [{"doc_id": "doc_a", "text": "supporting evidence"}],
        },
    )
    transport.complete(req)
    messages_blob = json.dumps(seen["body"]["messages"])
    # The pass-1 content_hash is a literal, model-visible substring (not just a params key).
    assert content_hash in messages_blob
    # Documents rendered into the messages too.
    assert "doc_a" in messages_blob
    # pass2_input is NOT a body key (POLARIS-internal).
    assert "pass2_input" not in seen["body"]
    # response_format DOES ride at top level for a managed server.
    assert seen["body"]["response_format"] == {"type": "json_object"}


# --------------------------------------------------------------------------------------
# Mirror pass-1: <co> citation-output instruction + documents model-visible (iter-4)
# --------------------------------------------------------------------------------------
def test_mirror_pass1_citation_instruction_and_documents_in_messages():
    handler, seen = _recording_handler(
        served_model=_MIRROR_SLUG, content="<co>HbA1c fell 2.3 points</co:doc_a>"
    )
    transport = _make_transport(handler)
    req = RoleRequest(
        role="mirror",
        model_slug=_MIRROR_SLUG,
        prompt="Is the claim grounded?",
        params={
            "documents": [
                {"doc_id": "doc_a", "text": "HbA1c fell 2.3 points."},
                {"doc_id": "doc_b", "text": "Weight fell 12%."},
            ],
            "citations": True,
        },
    )
    transport.complete(req)
    messages_blob = json.dumps(seen["body"]["messages"])
    # Both supplied doc_ids are model-visible.
    assert "doc_a" in messages_blob and "doc_b" in messages_blob
    # The EXACT self-host citation form is instructed.
    assert "<co>covered text</co:doc_id>" in messages_blob
    # `citations` flag is NOT forwarded as a body key.
    assert "citations" not in seen["body"]


# --------------------------------------------------------------------------------------
# Response parses to RoleResponse; Cohere <co> raw_text AS-IS + citations=None
# --------------------------------------------------------------------------------------
def test_response_parses_to_role_response():
    handler, _ = _recording_handler(served_model=_JUDGE_SLUG, content="VERIFIED")
    transport = _make_transport(handler)
    resp = transport.complete(RoleRequest(role="judge", model_slug=_JUDGE_SLUG, prompt="x"))
    assert isinstance(resp, RoleResponse)
    assert resp.raw_text == "VERIFIED"
    assert resp.served_model == _JUDGE_SLUG
    assert resp.usage == {"prompt_tokens": 7, "completion_tokens": 3}
    assert resp.citations is None


def test_cohere_co_response_returns_raw_text_as_is_citations_none():
    co_text = "The drug <co>reduced HbA1c by 2.3 points</co:doc_a> in the trial."
    handler, _ = _recording_handler(served_model=_MIRROR_SLUG, content=co_text)
    transport = _make_transport(handler)
    resp = transport.complete(
        RoleRequest(
            role="mirror",
            model_slug=_MIRROR_SLUG,
            prompt="ground it",
            params={"documents": [{"doc_id": "doc_a", "text": "..."}], "citations": True},
        )
    )
    # Tags intact, NOT pre-parsed/stripped — mirror_adapter owns parse/strip/offsets.
    assert resp.raw_text == co_text
    assert "<co>" in resp.raw_text
    assert resp.citations is None


# --------------------------------------------------------------------------------------
# Capture carries served endpoint (base_url) for M4 + correct role
# --------------------------------------------------------------------------------------
def test_capture_carries_served_endpoint_for_m4():
    pc.register_pathB_capture()
    handler, _ = _recording_handler(served_model=_SENTINEL_SLUG, content="<score>no</score>")
    transport = _make_transport(handler)
    transport.complete(
        RoleRequest(
            role="sentinel",
            model_slug=_SENTINEL_SLUG,
            messages=[
                {"role": "assistant", "content": "claim"},
                {"role": "user", "content": "<guardian>groundedness</guardian>"},
            ],
            params={"documents": [{"doc_id": "d1", "text": "ev"}]},
        )
    )
    calls = pc.collected_calls()
    assert len(calls) == 1
    meta = calls[0]["response_metadata"]
    assert calls[0]["role"] == "sentinel"
    # M4 served==pinned for a self-host role consumes the endpoint + served model.
    assert meta["endpoint"] == _SENTINEL_BASE
    assert meta["model"] == _SENTINEL_SLUG
    # No fabricated provider_name for vLLM.
    assert "provider_name" not in meta


def test_capture_invoked_with_role_via_registered_sink():
    pc.register_pathB_capture()
    handler, _ = _recording_handler(served_model=_JUDGE_SLUG, content="UNSUPPORTED")
    transport = _make_transport(handler)
    transport.complete(RoleRequest(role="judge", model_slug=_JUDGE_SLUG, prompt="decide"))
    calls = pc.collected_calls()
    assert [c["role"] for c in calls] == ["judge"]
    assert calls[0]["response_metadata"]["endpoint"] == _JUDGE_BASE


# --------------------------------------------------------------------------------------
# Fail loud: non-200 + malformed body -> RoleTransportError (never silent empty)
# --------------------------------------------------------------------------------------
def test_http_500_raises_role_transport_error():
    handler, _ = _recording_handler(served_model=_JUDGE_SLUG, content="x", status_code=500)
    transport = _make_transport(handler)
    with pytest.raises(RoleTransportError, match="HTTP 500"):
        transport.complete(RoleRequest(role="judge", model_slug=_JUDGE_SLUG, prompt="x"))


def test_malformed_body_no_choices_raises():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"model": _JUDGE_SLUG, "choices": []})

    transport = _make_transport(handler)
    with pytest.raises(RoleTransportError, match="no choices"):
        transport.complete(RoleRequest(role="judge", model_slug=_JUDGE_SLUG, prompt="x"))


def test_malformed_body_non_json_raises():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"not json", headers={"Content-Type": "text/plain"})

    transport = _make_transport(handler)
    with pytest.raises(RoleTransportError, match="non-JSON"):
        transport.complete(RoleRequest(role="judge", model_slug=_JUDGE_SLUG, prompt="x"))


def test_missing_message_content_raises():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"model": _JUDGE_SLUG, "choices": [{"message": {}}]})

    transport = _make_transport(handler)
    with pytest.raises(RoleTransportError, match="no/blank message content"):
        transport.complete(RoleRequest(role="judge", model_slug=_JUDGE_SLUG, prompt="x"))


# (Codex diff P2) fail-loud hardening: non-dict choice + blank content
def test_non_dict_choice_raises_role_transport_error():
    # `choices: [null]` must raise RoleTransportError, NOT crash with AttributeError.
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"model": _JUDGE_SLUG, "choices": [None]})

    transport = _make_transport(handler)
    with pytest.raises(RoleTransportError, match="not an object"):
        transport.complete(RoleRequest(role="judge", model_slug=_JUDGE_SLUG, prompt="x"))


def test_blank_message_content_raises_role_transport_error():
    # A blank/whitespace completion is a transport failure for a verifier (never a valid empty
    # answer) -> RoleTransportError, not a misleading empty RoleResponse.
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"model": _JUDGE_SLUG, "choices": [{"message": {"content": "   "}}]}
        )

    transport = _make_transport(handler)
    with pytest.raises(RoleTransportError, match="no/blank message content"):
        transport.complete(RoleRequest(role="judge", model_slug=_JUDGE_SLUG, prompt="x"))


# --------------------------------------------------------------------------------------
# I-meta-002-q1b (#939): verifier REASONING is separated from the bare verdict/body so the
# verdict parsers never see "soap", AND the reasoning is captured (on RoleResponse) for the
# four_role_role_calls.jsonl line-by-line review. Three served-reasoning shapes × all 3 roles,
# plus the fail-closed cases.
# --------------------------------------------------------------------------------------
_ALL_ROLES = (
    ("mirror", _MIRROR_SLUG),
    ("sentinel", _SENTINEL_SLUG),
    ("judge", _JUDGE_SLUG),
)


def _message_handler(*, served_model: str, message: dict):
    """A MockTransport handler returning a canned `message` object verbatim (no network)."""

    def handler(request: httpx.Request) -> httpx.Response:
        payload = {
            "model": served_model,
            "choices": [{"message": {"role": "assistant", **message}}],
            "usage": {"prompt_tokens": 7, "completion_tokens": 3},
        }
        return httpx.Response(200, json=payload)

    return handler


@pytest.mark.parametrize("role,slug", _ALL_ROLES)
def test_separate_reasoning_content_field_kept_apart_from_verdict(role, slug):
    # vLLM reasoning-parser path: reasoning arrives in its OWN `reasoning_content` field and
    # `content` is already the bare verdict. raw_text = bare verdict; reasoning = the field.
    handler = _message_handler(
        served_model=slug,
        message={"content": "VERIFIED", "reasoning_content": "I weighed the evidence span."},
    )
    transport = _make_transport(handler)
    resp = transport.complete(RoleRequest(role=role, model_slug=slug, prompt="decide"))
    assert resp.raw_text == "VERIFIED"
    assert resp.reasoning == "I weighed the evidence span."


@pytest.mark.parametrize("role,slug", _ALL_ROLES)
def test_inline_leading_think_block_split_from_verdict(role, slug):
    # Inline path: a LEADING <think>...</think> block is split off `content`; raw_text is the
    # bare remainder, reasoning is the inner text. The verdict parser never sees the think block.
    handler = _message_handler(
        served_model=slug,
        message={"content": "<think>step one; step two</think>VERIFIED"},
    )
    transport = _make_transport(handler)
    resp = transport.complete(RoleRequest(role=role, model_slug=slug, prompt="decide"))
    assert resp.raw_text == "VERIFIED"
    assert resp.reasoning == "step one; step two"


@pytest.mark.parametrize("role,slug", _ALL_ROLES)
def test_no_reasoning_leaves_verdict_clean(role, slug):
    # No reasoning of any shape: raw_text is the content unchanged, reasoning is None.
    handler = _message_handler(served_model=slug, message={"content": "PARTIAL"})
    transport = _make_transport(handler)
    resp = transport.complete(RoleRequest(role=role, model_slug=slug, prompt="decide"))
    assert resp.raw_text == "PARTIAL"
    assert resp.reasoning is None


def test_unterminated_think_block_fails_closed():
    # A <think> opened with NO closing </think> is a malformed verifier response — raise rather
    # than feed a half-emitted reasoning block to a strict verdict parser.
    handler = _message_handler(
        served_model=_JUDGE_SLUG, message={"content": "<think>reasoning that never closes"}
    )
    transport = _make_transport(handler)
    with pytest.raises(RoleTransportError, match="no closing </think>"):
        transport.complete(RoleRequest(role="judge", model_slug=_JUDGE_SLUG, prompt="x"))


def test_think_only_no_verdict_fails_closed():
    # A think-only message (empty verdict after the block) fails the SAME post-split blank guard
    # as a blank content — a verifier must return a non-blank bare verdict.
    handler = _message_handler(
        served_model=_JUDGE_SLUG, message={"content": "<think>only reasoning here</think>   "}
    )
    transport = _make_transport(handler)
    with pytest.raises(RoleTransportError, match="no/blank message content after reasoning"):
        transport.complete(RoleRequest(role="judge", model_slug=_JUDGE_SLUG, prompt="x"))


def test_separate_reasoning_field_but_blank_verdict_fails_closed():
    # Parity (Codex brief note): reasoning_content present but `content` blank must fail the SAME
    # way as a think-only inline message — never a deliberately-empty verdict.
    handler = _message_handler(
        served_model=_JUDGE_SLUG, message={"content": "  ", "reasoning_content": "I reasoned."}
    )
    transport = _make_transport(handler)
    with pytest.raises(RoleTransportError, match="no/blank message content after reasoning"):
        transport.complete(RoleRequest(role="judge", model_slug=_JUDGE_SLUG, prompt="x"))


def test_sanitize_raw_for_capture_strips_reasoning_keeps_served_identity():
    # No-leak (Codex diff P1): the response handed to Path-B capture must carry the BARE verdict
    # and NO reasoning — neither a `reasoning_content` field nor an inline <think> block — while
    # served-identity fields (model / usage / _pathb_served / system_fingerprint) are preserved.
    raw = {
        "model": _JUDGE_SLUG,
        "usage": {"prompt_tokens": 7, "completion_tokens": 3},
        "system_fingerprint": "fp_abc",
        "_pathb_served": {"endpoint": _JUDGE_BASE, "model": _JUDGE_SLUG},
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": "<think>chain of thought</think>VERIFIED",
                    "reasoning_content": "separate-field reasoning",
                }
            }
        ],
    }
    sanitized = _sanitize_raw_for_capture(raw, bare_text="VERIFIED")
    msg = sanitized["choices"][0]["message"]
    assert msg["content"] == "VERIFIED"
    assert "reasoning_content" not in msg
    # No reasoning text survives anywhere in the captured object.
    blob = json.dumps(sanitized)
    assert "chain of thought" not in blob
    assert "separate-field reasoning" not in blob
    # Served-identity fields preserved (M4 served==pinned must still work).
    assert sanitized["model"] == _JUDGE_SLUG
    assert sanitized["usage"] == {"prompt_tokens": 7, "completion_tokens": 3}
    assert sanitized["system_fingerprint"] == "fp_abc"
    assert sanitized["_pathb_served"] == {"endpoint": _JUDGE_BASE, "model": _JUDGE_SLUG}
    # The ORIGINAL raw is not mutated (still carries its reasoning for the record/jsonl path).
    assert raw["choices"][0]["message"]["reasoning_content"] == "separate-field reasoning"
    assert raw["choices"][0]["message"]["content"] == "<think>chain of thought</think>VERIFIED"


def test_mirror_inline_think_preserves_co_spans_after_split():
    # Splitting a LEADING <think> block must NOT corrupt Mirror's <co> spans that FOLLOW: the
    # bare raw_text keeps the tags intact and mirror_adapter aligns offsets over THIS raw_text.
    handler = _message_handler(
        served_model=_MIRROR_SLUG,
        message={
            "content": "<think>grounding check</think>The drug <co>reduced HbA1c</co:doc_a> in trial."
        },
    )
    transport = _make_transport(handler)
    resp = transport.complete(
        RoleRequest(
            role="mirror",
            model_slug=_MIRROR_SLUG,
            prompt="ground it",
            params={"documents": [{"doc_id": "doc_a", "text": "..."}], "citations": True},
        )
    )
    assert resp.raw_text == "The drug <co>reduced HbA1c</co:doc_a> in trial."
    assert resp.raw_text.startswith("The drug")
    assert "<co>" in resp.raw_text
    assert resp.reasoning == "grounding check"
    assert resp.citations is None
