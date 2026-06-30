"""Tests for the benchmark-stage OpenRouter verifier RoleTransport (I-meta-007d).

SPEND-FREE: every test injects an `httpx.Client(transport=httpx.MockTransport(...))` (or feeds a
faked OpenRouter catalog through the same), so there is NO socket / NO real LLM / NO spend in any
path pytest exercises — the OpenRouter HTTP is monkeypatched at the transport layer.

Asserts the I-meta-007d contract (P1-1..P1-4 + P2 fixes, diff-gate iter-1) updated for I-run11-004
(the CERTIFIED MiniMax-M2 decomposition Sentinel — reasoning ON, max_tokens>=3000):
  (a) the transport sends each verifier role's BENCHMARK lineup slug (Mirror `z-ai/glm-5.1`,
      Sentinel `minimax/minimax-m2`, Judge `qwen/qwen3.6-35b-a3b` — NOT the lock's
      self-host slugs; P1-1) + the MAX-reasoning request param
      (`reasoning = {"enabled": True, "effort": "xhigh"}` — `xhigh` is OpenRouter's MAX; P1-2),
      and does NOT forward a top-level `documents` body key (P1-4);
  (b) verifier REASONING is captured SEPARATE from the bare verdict in the RoleResponse — the
      OpenRouter `message.reasoning` shape (P1-3), the `reasoning_content` field shape, and the
      inline leading `<think>` shape — and never leaks into the Path-B capture channel;
  (c) `served_model` is surfaced for identity (and the OpenRouter served provider/model is
      stashed for the Path-B M4 served==pinned gate);
  (d) `build_gate_b_transport` picks `OpenRouterRoleTransport` when PG_FOUR_ROLE_TRANSPORT is
      unset (default "openrouter") or "openrouter", and `OpenAICompatibleRoleTransport` when
      "self_host";
  (e) the openrouter preflight asserts each BENCHMARK lineup slug is present in a faked catalog
      (by `id` OR `canonical_slug`), fails LOUD on a missing slug, and keeps the
      4-distinct-family check over the deepseek/z-ai/minimax/qwen benchmark lineup.

NO network: the real OpenRouter endpoint is never hit; the `OpenAICompatibleRoleTransport`
self-host path is also never constructed against a live endpoint here.
"""

from __future__ import annotations

import json

import httpx
import pytest

from scripts.dr_benchmark import run_gate_b
from src.polaris_graph.benchmark import pathB_capture as pc
from src.polaris_graph.roles.openai_compatible_transport import (
    BlankVerdictError,
    OpenAICompatibleRoleTransport,
    RoleTransportError,
)
from src.polaris_graph.roles.openrouter_role_transport import (
    OpenRouterRoleTransport,
    benchmark_verifier_lineup,
    openrouter_role_endpoint,
)
from src.polaris_graph.roles.role_transport import RoleRequest, RoleResponse

# BENCHMARK-STAGE OpenRouter lineup slugs (P1-1). I-run11-004: lock + benchmark now converge —
# Mirror z-ai/glm-5.2, Sentinel CERTIFIED minimax/minimax-m2 (decomposition), Judge moonshotai/kimi-k2.6.
# I-beatboth-008 (#1285): all-GLM-5.2 — the Mirror is upgraded z-ai/glm-5.1 -> z-ai/glm-5.2 (the
# generator is also z-ai/glm-5.2 now; that gen+mirror collision is the operator-approved
# family_policy.allowed_collisions pair — see test_family_check_passes_on_benchmark_lineup).
# I-judge-kimi (2026-06-29, operator directive): the benchmark Judge swapped qwen/qwen3.6-35b-a3b
# -> moonshotai/kimi-k2.6 (21 OpenRouter endpoints vs qwen's 2 — the few-provider qwen 429-tore the
# D8 seam). The Judge family lane is therefore now `moonshotai` (4-distinct invariant holds).
_MIRROR_SLUG = "z-ai/glm-5.2"
_SENTINEL_SLUG = "minimax/minimax-m2"
_JUDGE_SLUG = "moonshotai/kimi-k2.6"

# Writer/generator — I-beatboth-008 (#1285): all-GLM-5.2 switched the generator
# deepseek/deepseek-v4-pro -> z-ai/glm-5.2 (same slug as the Mirror; the allowed_collisions pair).
# Referenced by the preflight catalog fixtures so the 4th OpenRouter entry is realistic.
_WRITER_SLUG = "z-ai/glm-5.2"

_ALL_ROLES = (
    ("mirror", _MIRROR_SLUG),
    ("sentinel", _SENTINEL_SLUG),
    ("judge", _JUDGE_SLUG),
)

_OPENROUTER_BASE = "https://openrouter.ai/api/v1"


@pytest.fixture(autouse=True)
def _openrouter_env(monkeypatch):
    """Provide the OpenRouter key (LAW VI) and clear any inherited transport-mode override so
    each test controls PG_FOUR_ROLE_TRANSPORT explicitly. Also restore the default base URL and
    clear the per-role benchmark-lineup overrides so the DEFAULT role_selection_final slugs are
    used (P1-1)."""
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-or-key")
    monkeypatch.delenv("PG_FOUR_ROLE_TRANSPORT", raising=False)
    monkeypatch.delenv("OPENROUTER_BASE_URL", raising=False)
    monkeypatch.delenv("PG_FOUR_ROLE_REASONING_EFFORT", raising=False)
    monkeypatch.delenv("PG_MIRROR_MODEL", raising=False)
    monkeypatch.delenv("PG_SENTINEL_MODEL", raising=False)
    monkeypatch.delenv("PG_JUDGE_MODEL", raising=False)
    yield


@pytest.fixture(autouse=True)
def _clean_capture():
    pc.clear_pathB_capture()
    yield
    pc.clear_pathB_capture()


def _make_transport(handler) -> OpenRouterRoleTransport:
    """Build the OpenRouter transport with an INJECTED MockTransport client (no network)."""
    client = httpx.Client(transport=httpx.MockTransport(handler))
    return OpenRouterRoleTransport(client)


def _recording_handler(*, served_model: str, message: dict, provider: str = "DeepInfra"):
    """A MockTransport handler that records each request and returns a canned OpenRouter-shaped
    completion (top-level served `provider`/`model`, the canned assistant `message`)."""
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["headers"] = dict(request.headers)
        seen["body"] = json.loads(request.content.decode("utf-8"))
        payload = {
            "model": served_model,
            "provider": provider,
            "choices": [{"message": {"role": "assistant", **message}}],
            "usage": {"prompt_tokens": 11, "completion_tokens": 5},
        }
        return httpx.Response(200, json=payload)

    return handler, seen


# --------------------------------------------------------------------------------------
# (a) pinned slug + MAX reasoning request param + OpenRouter URL/auth
# --------------------------------------------------------------------------------------
@pytest.mark.parametrize("role,slug", _ALL_ROLES)
def test_sends_pinned_slug_and_max_reasoning(role, slug):
    handler, seen = _recording_handler(served_model=slug, message={"content": "VERIFIED"})
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
        req = RoleRequest(role=role, model_slug=slug, prompt="decide", params={})
    transport.complete(req)

    body = seen["body"]
    # P1-1: the BENCHMARK lineup slug is the body `model` (sourced from the benchmark lineup, NOT
    # the lock self-host slug, NOT the request). It also equals the pin verifier_model_slugs feeds
    # into RoleRequest.model_slug, so served == pinned (asserted in its own test below).
    assert body["model"] == slug
    # I-run11-004: reasoning is PER-ROLE and the Sentinel is now MODE-AWARE. The default
    # PG_SENTINEL_MODEL (minimax/minimax-m2) resolves to "decomposition" mode, which the
    # certification ran WITH reasoning ON (reasoning OFF / starved max_tokens truncates the JSON ->
    # all-UNGROUNDED collapse). So ALL THREE roles now send MAX reasoning + require_parameters.
    # P1-2 MAX reasoning: enabled + effort "xhigh" (OpenRouter's documented MAXIMUM effort) for the
    # effort-reasoning roles (Judge, decomposition Sentinel). I-run11-008 (#1053): the Mirror instead
    # sends a BOUNDED numeric reasoning cap (effort=xhigh is a no-op on GLM and unbounded thinking
    # exhausted the budget -> 47 blanks), so its reasoning block is a fixed max_tokens cap.
    if role == "mirror":
        # I-arch-003 (#1253): Mirror reasoning cap raised 4000 -> 100000 (kept << total max_tokens so
        # it never re-blanks; bake-off verified clean on all 5 fp8 providers).
        assert body["reasoning"] == {"max_tokens": 100000}
    elif role == "judge":
        # I-judge-kimi (2026-06-29): moonshotai/kimi-k2.6 advertises the `reasoning` parameter but
        # OMITS the supported-efforts list, so an `effort` key risks a 400 on its unpinned endpoints.
        # _judge_reasoning_block therefore sends a BARE {enabled: true} for the kimi Judge — reasoning
        # is ON at the model's native (max) depth, no effort field. (§9.1.8: never starve reasoning.)
        assert body["reasoning"] == {"enabled": True}
    else:
        # Sentinel (minimax/minimax-m2) is NOT kimi, so it keeps the MAX effort=xhigh.
        assert body["reasoning"] == {"enabled": True, "effort": "xhigh"}
    # require_parameters=True makes OpenRouter only route to a provider that HONORS reasoning
    # (otherwise the max-reasoning request could be silently ignored on a fallback provider).
    assert body["provider"] == {"require_parameters": True}
    # P1-4: a top-level `documents` key is NOT forwarded (OpenRouter's chat-completions schema
    # has no such param; with require_parameters=True it would fail routing). The evidence is
    # already rendered into `messages` by _normalize_messages, so model-visibility is preserved.
    assert "documents" not in body
    # OpenRouter URL: base already ends in /api/v1, so only /chat/completions is appended
    # (NOT a doubled /v1/chat/completions).
    assert seen["url"] == f"{_OPENROUTER_BASE}/chat/completions"
    assert "/v1/v1/" not in seen["url"]
    # Bearer auth with the OpenRouter key (httpx lowercases header keys via dict()).
    assert seen["headers"].get("authorization") == "Bearer test-or-key"


def test_benchmark_lineup_slugs_and_families():
    """P1-1: the transport's served slug == the benchmark lineup == verifier_model_slugs (pinned).
    I-beatboth-008 (#1285): the all-GLM-5.2 verifier lineup is z-ai/minimax/qwen (Mirror upgraded
    to z-ai/glm-5.2). The generator is also z-ai/glm-5.2 — that gen+mirror collision is the
    operator-approved allowed_collisions pair; the other roles stay distinct lineages."""
    lineup = benchmark_verifier_lineup()
    assert lineup == {
        "mirror": _MIRROR_SLUG,        # z-ai/glm-5.2
        "sentinel": _SENTINEL_SLUG,    # minimax/minimax-m2
        "judge": _JUDGE_SLUG,          # qwen/qwen3.6-35b-a3b
    }


def test_served_equals_pinned_on_openrouter(monkeypatch):
    """P1-1 served==pinned regression guard: the slug the transport POSTs as body['model'] equals
    the slug run_gate_b.verifier_model_slugs pins into RoleRequest.model_slug (openrouter mode)."""
    monkeypatch.delenv("PG_FOUR_ROLE_TRANSPORT", raising=False)  # default openrouter
    pinned = run_gate_b.verifier_model_slugs()
    for role, slug in _ALL_ROLES:
        handler, seen = _recording_handler(served_model=slug, message={"content": "VERIFIED"})
        if role == "sentinel":
            req = RoleRequest(
                role=role,
                model_slug=pinned[role],
                messages=[
                    {"role": "assistant", "content": "claim"},
                    {"role": "user", "content": "<guardian>g</guardian>"},
                ],
                params={"documents": [{"doc_id": "d1", "text": "ev"}]},
            )
        else:
            req = RoleRequest(role=role, model_slug=pinned[role], prompt="decide", params={})
        _make_transport(handler).complete(req)
        # Served (what the transport SENT as model) == pinned (what the gate/request carries).
        assert seen["body"]["model"] == pinned[role] == slug


def test_reasoning_effort_env_overridable(monkeypatch):
    # LAW VI: PG_FOUR_ROLE_REASONING_EFFORT is read at import. For the effort-honoring Sentinel
    # (minimax/minimax-m2, NOT kimi) the override flows through verbatim, proving the env knob works.
    import importlib

    import src.polaris_graph.roles.openrouter_role_transport as mod

    monkeypatch.setenv("PG_FOUR_ROLE_REASONING_EFFORT", "medium")
    importlib.reload(mod)
    try:
        handler, seen = _recording_handler(served_model=_SENTINEL_SLUG, message={"content": "VERIFIED"})
        client = httpx.Client(transport=httpx.MockTransport(handler))
        mod.OpenRouterRoleTransport(client).complete(
            RoleRequest(
                role="sentinel",
                model_slug=_SENTINEL_SLUG,
                messages=[
                    {"role": "assistant", "content": "claim"},
                    {"role": "user", "content": "<guardian>groundedness</guardian>"},
                ],
                params={"documents": [{"doc_id": "d1", "text": "evidence"}]},
            )
        )
        assert seen["body"]["reasoning"] == {"enabled": True, "effort": "medium"}
    finally:
        # Restore the module to its default-effort state for the rest of the suite.
        monkeypatch.delenv("PG_FOUR_ROLE_REASONING_EFFORT", raising=False)
        importlib.reload(mod)


def test_kimi_judge_strips_effort_to_bare_block(monkeypatch):
    # I-judge-kimi: the kimi-k2.6 Judge advertises NO supported efforts, so _judge_reasoning_block
    # STRIPS effort and sends a BARE {enabled: true} REGARDLESS of PG_FOUR_ROLE_REASONING_EFFORT —
    # pin that so a future effort tweak can never silently 400 the Judge on an unpinned kimi endpoint.
    import importlib

    import src.polaris_graph.roles.openrouter_role_transport as mod

    monkeypatch.setenv("PG_FOUR_ROLE_REASONING_EFFORT", "medium")
    importlib.reload(mod)
    try:
        handler, seen = _recording_handler(served_model=_JUDGE_SLUG, message={"content": "VERIFIED"})
        client = httpx.Client(transport=httpx.MockTransport(handler))
        mod.OpenRouterRoleTransport(client).complete(
            RoleRequest(role="judge", model_slug=_JUDGE_SLUG, prompt="x")
        )
        assert seen["body"]["reasoning"] == {"enabled": True}
    finally:
        monkeypatch.delenv("PG_FOUR_ROLE_REASONING_EFFORT", raising=False)
        importlib.reload(mod)


def test_missing_openrouter_key_fails_loud(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    handler, _ = _recording_handler(served_model=_JUDGE_SLUG, message={"content": "VERIFIED"})
    transport = _make_transport(handler)
    with pytest.raises(RoleTransportError, match="OPENROUTER_API_KEY"):
        transport.complete(RoleRequest(role="judge", model_slug=_JUDGE_SLUG, prompt="x"))


def test_generator_is_excluded():
    with pytest.raises(ValueError, match="generator"):
        openrouter_role_endpoint("generator")


def test_unknown_role_raises():
    with pytest.raises(ValueError, match="verifier"):
        openrouter_role_endpoint("evaluator")


# --------------------------------------------------------------------------------------
# (b) reasoning captured SEPARATE from the bare verdict text
# --------------------------------------------------------------------------------------
@pytest.mark.parametrize("role,slug", _ALL_ROLES)
def test_openrouter_message_reasoning_separate_from_verdict(role, slug):
    # P1-3: OpenRouter returns reasoning in `message.reasoning` (NOT reasoning_content, NOT
    # <think>). raw_text = bare verdict; reasoning = the message.reasoning field — kept apart.
    handler, _ = _recording_handler(
        served_model=slug,
        message={"content": "VERIFIED", "reasoning": "OpenRouter chain-of-thought here."},
    )
    transport = _make_transport(handler)
    resp = transport.complete(RoleRequest(role=role, model_slug=slug, prompt="decide"))
    assert isinstance(resp, RoleResponse)
    assert resp.raw_text == "VERIFIED"
    assert resp.reasoning == "OpenRouter chain-of-thought here."
    # The verdict text carries NO reasoning soap.
    assert "chain-of-thought" not in resp.raw_text


def test_openrouter_message_reasoning_not_leaked_to_capture():
    # P1-3 no-leak: the OpenRouter `message.reasoning` must be stripped from the Path-B capture
    # channel (the existing no-leak test only covered `reasoning_content`).
    pc.register_pathB_capture()
    handler, _ = _recording_handler(
        served_model=_JUDGE_SLUG,
        message={"content": "VERIFIED", "reasoning": "secret openrouter reasoning"},
    )
    transport = _make_transport(handler)
    transport.complete(RoleRequest(role="judge", model_slug=_JUDGE_SLUG, prompt="x"))
    blob = json.dumps(pc.collected_calls())
    assert "secret openrouter reasoning" not in blob


@pytest.mark.parametrize("role,slug", _ALL_ROLES)
def test_reasoning_content_field_separate_from_verdict(role, slug):
    # OpenRouter reasoning path: reasoning arrives in its OWN `reasoning_content` field; `content`
    # is the bare verdict. raw_text = bare verdict; reasoning = the field — kept apart.
    handler, _ = _recording_handler(
        served_model=slug,
        message={"content": "VERIFIED", "reasoning_content": "I weighed the cited span."},
    )
    transport = _make_transport(handler)
    resp = transport.complete(RoleRequest(role=role, model_slug=slug, prompt="decide"))
    assert isinstance(resp, RoleResponse)
    assert resp.raw_text == "VERIFIED"
    assert resp.reasoning == "I weighed the cited span."
    # The verdict text carries NO reasoning soap.
    assert "weighed" not in resp.raw_text


@pytest.mark.parametrize("role,slug", _ALL_ROLES)
def test_inline_think_block_separate_from_verdict(role, slug):
    # Inline path: a LEADING <think>...</think> block is split off `content`; raw_text is the bare
    # remainder, reasoning is the inner text.
    handler, _ = _recording_handler(
        served_model=slug, message={"content": "<think>step one; step two</think>PARTIAL"}
    )
    transport = _make_transport(handler)
    resp = transport.complete(RoleRequest(role=role, model_slug=slug, prompt="decide"))
    assert resp.raw_text == "PARTIAL"
    assert resp.reasoning == "step one; step two"


def test_no_reasoning_leaves_verdict_clean():
    handler, _ = _recording_handler(served_model=_JUDGE_SLUG, message={"content": "UNSUPPORTED"})
    transport = _make_transport(handler)
    resp = transport.complete(RoleRequest(role="judge", model_slug=_JUDGE_SLUG, prompt="x"))
    assert resp.raw_text == "UNSUPPORTED"
    assert resp.reasoning is None


def test_mirror_co_spans_preserved_and_citations_none():
    # Mirror <co> raw-text-as-is invariant: tags intact, citations=None (mirror_adapter owns the
    # parse/strip/offset alignment). A leading <think> split must not corrupt the following spans.
    co_text = "The drug <co>reduced HbA1c by 2.3 points</co:doc_a> in the trial."
    handler, _ = _recording_handler(
        served_model=_MIRROR_SLUG, message={"content": f"<think>grounding</think>{co_text}"}
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
    assert resp.raw_text == co_text
    assert "<co>" in resp.raw_text
    assert resp.reasoning == "grounding"
    assert resp.citations is None


def test_unterminated_think_block_fails_closed():
    handler, _ = _recording_handler(
        served_model=_JUDGE_SLUG, message={"content": "<think>never closes"}
    )
    transport = _make_transport(handler)
    with pytest.raises(RoleTransportError, match="no closing </think>"):
        transport.complete(RoleRequest(role="judge", model_slug=_JUDGE_SLUG, prompt="x"))


# --------------------------------------------------------------------------------------
# (c) served_model surfaced for identity + Path-B capture stashes OpenRouter served identity
# --------------------------------------------------------------------------------------
def test_served_model_surfaced_on_response():
    handler, _ = _recording_handler(served_model=_JUDGE_SLUG, message={"content": "VERIFIED"})
    transport = _make_transport(handler)
    resp = transport.complete(RoleRequest(role="judge", model_slug=_JUDGE_SLUG, prompt="x"))
    assert resp.served_model == _JUDGE_SLUG
    assert resp.usage == {"prompt_tokens": 11, "completion_tokens": 5}


def test_capture_carries_openrouter_served_provider_and_model():
    pc.register_pathB_capture()
    handler, _ = _recording_handler(
        served_model=_SENTINEL_SLUG, message={"content": "<score>no</score>"}, provider="Fireworks"
    )
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
    # OpenRouter served identity (provider + served model) for M4 served==pinned.
    assert meta["provider_name"] == "Fireworks"
    assert meta["model"] == _SENTINEL_SLUG
    # No self-host endpoint key on the OpenRouter path.
    assert "endpoint" not in meta


def test_capture_does_not_leak_reasoning():
    # No-leak: the captured response carries the BARE verdict and NO reasoning soap.
    pc.register_pathB_capture()
    handler, _ = _recording_handler(
        served_model=_JUDGE_SLUG,
        message={"content": "VERIFIED", "reasoning_content": "secret chain of thought"},
    )
    transport = _make_transport(handler)
    transport.complete(RoleRequest(role="judge", model_slug=_JUDGE_SLUG, prompt="x"))
    blob = json.dumps(pc.collected_calls())
    assert "secret chain of thought" not in blob


# --------------------------------------------------------------------------------------
# (d) build_gate_b_transport picks the right transport per PG_FOUR_ROLE_TRANSPORT
# --------------------------------------------------------------------------------------
def test_build_transport_defaults_to_openrouter(monkeypatch):
    monkeypatch.delenv("PG_FOUR_ROLE_TRANSPORT", raising=False)
    # P2: inject a MockTransport-backed client so no live httpx.Client/socket is built in tests.
    client = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, json={})))
    transport = run_gate_b.build_gate_b_transport(http_client=client)
    assert isinstance(transport, OpenRouterRoleTransport)


def test_build_transport_openrouter_explicit(monkeypatch):
    monkeypatch.setenv("PG_FOUR_ROLE_TRANSPORT", "openrouter")
    client = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, json={})))
    assert isinstance(
        run_gate_b.build_gate_b_transport(http_client=client), OpenRouterRoleTransport
    )


def test_build_transport_self_host(monkeypatch):
    monkeypatch.setenv("PG_FOUR_ROLE_TRANSPORT", "self_host")
    client = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, json={})))
    assert isinstance(
        run_gate_b.build_gate_b_transport(http_client=client), OpenAICompatibleRoleTransport
    )


def test_invalid_transport_mode_fails_loud(monkeypatch):
    monkeypatch.setenv("PG_FOUR_ROLE_TRANSPORT", "openai")
    with pytest.raises(ValueError, match="PG_FOUR_ROLE_TRANSPORT"):
        run_gate_b.four_role_transport_mode()


# --------------------------------------------------------------------------------------
# (e) openrouter preflight: catalog slug presence (id OR canonical_slug) + 4-family check
# --------------------------------------------------------------------------------------
def _catalog_client(catalog_data: list[dict], status_code: int = 200) -> httpx.Client:
    """A MockTransport client answering GET /models with the supplied catalog `data` (no net)."""

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/models")
        return httpx.Response(status_code, json={"data": catalog_data})

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_preflight_openrouter_resolves_all_slugs_present_as_id():
    # P1-1 / I-run11-004: the preflight resolves the BENCHMARK lineup slugs (z-ai/glm-5.1,
    # minimax/minimax-m2, qwen3.6-35b-a3b) against the catalog — NOT the lock self-host slugs.
    # The decomposition Sentinel is reasoning-enabled, so its catalog entry advertises `reasoning`.
    catalog = [
        {
            "id": _MIRROR_SLUG,
            "canonical_slug": "z-ai/glm-5.1-20260520",
            "supported_parameters": ["reasoning", "max_tokens"],
        },
        {
            "id": _SENTINEL_SLUG,
            "canonical_slug": _SENTINEL_SLUG,
            "supported_parameters": ["reasoning", "response_format", "max_tokens"],
        },
        {
            "id": _JUDGE_SLUG,
            "canonical_slug": _JUDGE_SLUG,
            "supported_parameters": ["reasoning", "max_tokens"],
        },
        {"id": _WRITER_SLUG},
    ]
    resolved = run_gate_b.preflight_openrouter_roles(http_client=_catalog_client(catalog))
    assert resolved == {
        "mirror": _MIRROR_SLUG,
        "sentinel": _SENTINEL_SLUG,
        "judge": _JUDGE_SLUG,
    }


def test_preflight_openrouter_matches_via_canonical_slug():
    # The benchmark slug appears ONLY as a `canonical_slug` (the entry `id` is a different alias).
    catalog = [
        {
            "id": "z-ai/glm-5.1-latest",
            "canonical_slug": _MIRROR_SLUG,
            "supported_parameters": ["reasoning", "max_tokens"],
        },
        {"id": _SENTINEL_SLUG, "supported_parameters": ["reasoning", "max_tokens"]},
        {"id": _JUDGE_SLUG, "supported_parameters": ["reasoning", "max_tokens"]},
    ]
    resolved = run_gate_b.preflight_openrouter_roles(http_client=_catalog_client(catalog))
    assert resolved["mirror"] == _MIRROR_SLUG


def test_preflight_openrouter_missing_slug_fails_loud():
    # Judge slug absent from the catalog (neither id nor canonical_slug) -> fail loud.
    # Mirror + Sentinel advertise `reasoning` so their executability checks pass and the loop
    # reaches the missing Judge, where the PRESENCE failure (match="judge") fires.
    catalog = [
        {"id": _MIRROR_SLUG, "supported_parameters": ["reasoning"]},
        {"id": _SENTINEL_SLUG, "supported_parameters": ["reasoning"]},
    ]
    with pytest.raises(RuntimeError, match="judge"):
        run_gate_b.preflight_openrouter_roles(http_client=_catalog_client(catalog))


def test_preflight_openrouter_fails_when_reasoning_role_lacks_reasoning_support():
    # Codex iter-2 P1: a reasoning-enabled role (Mirror) whose slug does NOT advertise `reasoning`
    # must fail preflight — with require_parameters=True OpenRouter would refuse to route. Sentinel
    # + Judge advertise it (Sentinel is now reasoning-ON in decomposition mode).
    catalog = [
        {"id": _MIRROR_SLUG, "supported_parameters": ["max_tokens"]},
        {"id": _SENTINEL_SLUG, "supported_parameters": ["reasoning", "max_tokens"]},
        {"id": _JUDGE_SLUG, "supported_parameters": ["reasoning", "max_tokens"]},
    ]
    with pytest.raises(RuntimeError, match="(?i)mirror|reasoning"):
        run_gate_b.preflight_openrouter_roles(http_client=_catalog_client(catalog))


def test_preflight_openrouter_decomposition_sentinel_lacking_reasoning_fails_loud():
    # I-run11-004: the DECOMPOSITION Sentinel (minimax/minimax-m2) is reasoning-ENABLED (certified
    # with reasoning ON). A catalog entry that does NOT advertise `reasoning` for it must FAIL the
    # preflight (with require_parameters=True OpenRouter would refuse to route). Mirror+Judge are
    # fine; only the Sentinel's missing `reasoning` trips the executability check.
    catalog = [
        {"id": _MIRROR_SLUG, "supported_parameters": ["reasoning", "max_tokens"]},
        {"id": _SENTINEL_SLUG, "supported_parameters": ["max_tokens", "response_format"]},
        {"id": _JUDGE_SLUG, "supported_parameters": ["reasoning", "max_tokens"]},
    ]
    with pytest.raises(RuntimeError, match="(?i)sentinel|reasoning"):
        run_gate_b.preflight_openrouter_roles(http_client=_catalog_client(catalog))


def test_preflight_openrouter_non_200_fails_loud():
    catalog = [{"id": _MIRROR_SLUG}, {"id": _SENTINEL_SLUG}, {"id": _JUDGE_SLUG}]
    with pytest.raises(RuntimeError, match="HTTP 503"):
        run_gate_b.preflight_openrouter_roles(
            http_client=_catalog_client(catalog, status_code=503)
        )


def test_family_check_passes_on_benchmark_lineup(monkeypatch):
    # I-beatboth-008 (#1285) re-premise: all-GLM-5.2 — the generator is now z-ai/glm-5.2 (same
    # family as the Mirror). In openrouter mode the family check derives the generator family the
    # same provider-prefix way as the verifiers (z-ai), so generator==mirror=="z-ai". That single
    # collision is the operator-signed family_policy.allowed_collisions pair [[generator, mirror]]
    # in the lock, so the check must still PASS — but ONLY for that pair. The sentinel (minimax)
    # and judge (qwen) stay distinct lineages, so the active families are {z-ai, minimax, qwen} =
    # 3 distinct. The NEGATIVE case (an UNLISTED same-family collision RAISES) is the binding
    # invariant and is asserted by test_family_check_fails_loud_on_cross_family_override below.
    monkeypatch.delenv("PG_FOUR_ROLE_TRANSPORT", raising=False)  # default openrouter
    fams = run_gate_b.assert_four_role_families_distinct()
    # I-judge-kimi (2026-06-29): the benchmark Judge swapped qwen -> moonshotai/kimi-k2.6, so its
    # provider-prefix family lane is now `moonshotai` (a NEW distinct lane, not colliding with the
    # z-ai gen+mirror pair or the minimax Sentinel).
    assert fams == {
        "generator": "z-ai",
        "mirror": "z-ai",
        "sentinel": "minimax",
        "judge": "moonshotai",
    }
    # gen+mirror share the allowed_collisions z-ai lineage; the other two are distinct -> 3 families.
    assert fams["generator"] == fams["mirror"] == "z-ai"
    assert len(set(fams.values())) == 3


def test_family_check_fails_loud_on_cross_family_override(monkeypatch):
    # P1-1 clinical-lethal guard / the BINDING NEGATIVE case: an UNLISTED same-family collision
    # must FAIL LOUD even under the all-GLM-5.2 allowed_collisions relaxation. I-beatboth-008
    # (#1285): gen+mirror are BOTH z-ai (the operator-approved allowed_collisions pair), so a
    # benchmark-Judge override into the z-ai lineage puts a THIRD role into z-ai — the Judge would
    # then share z-ai with the generator+mirror (same family self-verifying). The (generator, judge)
    # pair is NOT in allowed_collisions, so the active-family-from-slug derivation must RAISE. This
    # proves the relaxation is scoped to ONLY the signed pair and the two-family invariant still
    # holds for every other role.
    # I-judge-kimi (2026-06-29): the benchmark Judge family is derived from PG_BENCHMARK_JUDGE_MODEL
    # (the dedicated benchmark env, DECOUPLED from the lock's PG_JUDGE_MODEL — gate P1-1). So the
    # collision must be forced through THAT env; PG_JUDGE_MODEL no longer reaches the benchmark Judge.
    monkeypatch.delenv("PG_FOUR_ROLE_TRANSPORT", raising=False)  # default openrouter
    monkeypatch.setenv("PG_BENCHMARK_JUDGE_MODEL", "z-ai/glm-5.1")
    with pytest.raises((RuntimeError, ValueError), match="(?i)judge|lane|collision"):
        run_gate_b.assert_four_role_families_distinct()


def test_family_check_passes_on_in_lane_override(monkeypatch):
    # An IN-LANE override (same provider prefix as the default) is accepted — only an UNLISTED
    # cross-family re-pick is rejected. PG_MIRROR_MODEL=z-ai/glm-5.2-pro stays in the z-ai lane.
    # I-beatboth-008 (#1285): all-GLM-5.2 — the generator is also z-ai now, so gen+mirror are the
    # allowed_collisions z-ai pair; with sentinel(minimax)+judge(qwen) distinct that is 3 families.
    monkeypatch.delenv("PG_FOUR_ROLE_TRANSPORT", raising=False)
    monkeypatch.setenv("PG_MIRROR_MODEL", "z-ai/glm-5.2-pro")
    fams = run_gate_b.assert_four_role_families_distinct()
    assert fams["mirror"] == "z-ai"
    assert fams["generator"] == fams["mirror"] == "z-ai"  # the allowed_collisions pair
    assert len(set(fams.values())) == 3


def test_stage_marker_records_benchmark_openrouter(monkeypatch, tmp_path):
    # P2: the machine-readable stage marker records stage=benchmark_openrouter + the active lineup
    # so a future gate can't mistake an OpenRouter benchmark run for the sovereign self-host path.
    monkeypatch.delenv("PG_FOUR_ROLE_TRANSPORT", raising=False)  # default openrouter
    marker = run_gate_b.four_role_stage_marker()
    assert marker["stage"] == "benchmark_openrouter"
    assert marker["transport_mode"] == "openrouter"
    assert marker["verifier_lineup"] == {
        "mirror": _MIRROR_SLUG,
        "sentinel": _SENTINEL_SLUG,
        "judge": _JUDGE_SLUG,
    }
    assert marker["verifier_families"] == {
        "mirror": "z-ai",
        "sentinel": "minimax",
        # I-judge-kimi (2026-06-29): Judge qwen -> moonshotai/kimi-k2.6 -> lane `moonshotai`.
        "judge": "moonshotai",
    }
    path = run_gate_b.write_four_role_stage_marker(tmp_path)
    assert path.exists()
    written = json.loads(path.read_text(encoding="utf-8"))
    assert written["stage"] == "benchmark_openrouter"


def test_stage_marker_self_host_distinguishes(monkeypatch, tmp_path):
    # P2: in self_host mode the stage is sovereign_self_host (NOT benchmark_openrouter).
    monkeypatch.setenv("PG_FOUR_ROLE_TRANSPORT", "self_host")
    marker = run_gate_b.four_role_stage_marker()
    assert marker["stage"] == "sovereign_self_host"
    assert marker["transport_mode"] == "self_host"


def test_preflight_openrouter_keeps_family_distinct_check(monkeypatch):
    # The 4-distinct-family assert still runs in the openrouter preflight: rig a collision and it
    # must fail BEFORE any catalog fetch (so the catalog client is never even called).
    fetched = {"count": 0}

    def _spy(http_client=None):
        fetched["count"] += 1
        return []

    monkeypatch.setattr(run_gate_b, "_fetch_openrouter_catalog", _spy)
    monkeypatch.setattr(
        run_gate_b,
        "assert_four_role_families_distinct",
        lambda: (_ for _ in ()).throw(RuntimeError("family collision")),
    )
    with pytest.raises(RuntimeError, match="family collision"):
        run_gate_b.preflight_openrouter_roles()
    assert fetched["count"] == 0  # family check gates BEFORE the catalog fetch


# --------------------------------------------------------------------------------------
# preflight dispatcher routes by the ENV-gated mode (no real network in either branch)
# --------------------------------------------------------------------------------------
def test_preflight_dispatcher_routes_to_openrouter(monkeypatch):
    monkeypatch.delenv("PG_FOUR_ROLE_TRANSPORT", raising=False)
    called = {"openrouter": False, "self_host": False}
    monkeypatch.setattr(
        run_gate_b, "preflight_openrouter_roles", lambda: called.__setitem__("openrouter", True) or {}
    )
    monkeypatch.setattr(
        run_gate_b, "preflight_self_host_roles", lambda: called.__setitem__("self_host", True) or {}
    )
    run_gate_b.preflight_four_role_transport()
    assert called == {"openrouter": True, "self_host": False}


def test_preflight_dispatcher_routes_to_self_host(monkeypatch):
    monkeypatch.setenv("PG_FOUR_ROLE_TRANSPORT", "self_host")
    called = {"openrouter": False, "self_host": False}
    monkeypatch.setattr(
        run_gate_b, "preflight_openrouter_roles", lambda: called.__setitem__("openrouter", True) or {}
    )
    monkeypatch.setattr(
        run_gate_b, "preflight_self_host_roles", lambda: called.__setitem__("self_host", True) or {}
    )
    run_gate_b.preflight_four_role_transport()
    assert called == {"openrouter": False, "self_host": True}


# --------------------------------------------------------------------------------------
# (f) I-meta-008 FULL-POWER (CORRECTS #1017): a reasoning verifier must carry a GENEROUS top-level
# max_tokens, NOT have it popped — effort=xhigh allocates ~95% to reasoning and max_tokens must be
# strictly higher so the bare verdict has room (popping it starved the verdict to empty). Sentinel gets
# an explicit classifier budget instead of pop-and-hope on the provider default. I-arch-003 (#1253):
# the per-role defaults are now the MIN max_completion_tokens of each role's pinned provider chain
# (Mirror/Sentinel 131072, Judge 262140) so "max" never 400s under allow_fallbacks:false.
# --------------------------------------------------------------------------------------
@pytest.mark.parametrize("role,slug", [("judge", _JUDGE_SLUG), ("mirror", _MIRROR_SLUG)])
def test_reasoning_role_sets_generous_max_tokens(role, slug):
    # The Judge adapter sets _DEFAULT_MAX_TOKENS=16; the transport must OVERRIDE it to the generous
    # verifier budget (16384) so xhigh reasoning AND the bare verdict both fit.
    handler, seen = _recording_handler(served_model=slug, message={"content": "VERIFIED"})
    _make_transport(handler).complete(
        RoleRequest(role=role, model_slug=slug, prompt="decide", params={"max_tokens": 16})
    )
    if role == "mirror":
        # I-run11-008 (#1053): the Mirror uses BOUNDED reasoning — a NUMERIC reasoning.max_tokens cap
        # (effort=xhigh is a no-op on GLM, so unbounded thinking exhausted the budget -> 47 blanks) and
        # a generous total budget STRICTLY above the cap so the <co>+JSON verdict always has room.
        # I-arch-003 (#1253, "max max"): reasoning cap 4000 -> 100000, total 24000 -> 131072 (the
        # min max_completion_tokens across the re-pinned fp8 Mirror chain; invariant cap << total holds).
        assert seen["body"]["reasoning"] == {"max_tokens": 100000}
        assert seen["body"]["max_tokens"] == 131072
    else:
        # I-deepfix-001 (#1344, drb_72 FIX #2): the Judge verdict budget is PG_D8_VERDICT_MAX_TOKENS
        # (default 16384 — I-meta-008's generous-but-bounded value). The I-arch-003 "max max" raise to
        # 262140 over-reserved per call and blew the OpenRouter TPM/context ceiling (193x HTTP-429 + 67x
        # HTTP-400 "requested > context") timing out the D8 seam; 16384 leaves ample room for
        # effort=xhigh reasoning AND the bare verdict (never starves -> §9.1.8) while reserving ~16x
        # fewer tokens and staying well under the 262144 window (so A2-CLAMP never needs to fire and the
        # 400 can't recur).
        assert seen["body"]["max_tokens"] == 16384, (
            f"{role}: verdict budget must be the bounded PG_D8_VERDICT_MAX_TOKENS default (16384)"
        )
        assert seen["body"]["max_tokens"] < 262144  # well under the kimi serving window; no 400
        # I-judge-kimi (2026-06-29): moonshotai/kimi-k2.6 advertises `reasoning` but NO supported
        # efforts (live OpenRouter /endpoints 2026-06-29), so the Judge sends a BARE {enabled: True}
        # — reasoning ON at the model's native (max) depth, no effort key that could 400 an unpinned
        # kimi endpoint (§9.1.8: never starve reasoning).
        assert seen["body"]["reasoning"] == {"enabled": True}


def test_reasoning_role_max_tokens_env_overridable(monkeypatch):
    # LAW VI: the Judge verdict budget is env-overridable. I-deepfix-001 FIX #2 renamed the knob from
    # PG_VERIFIER_REASONING_MAX_TOKENS to PG_D8_VERDICT_MAX_TOKENS (8192 < chain-min, so no clamp).
    monkeypatch.setenv("PG_D8_VERDICT_MAX_TOKENS", "8192")
    handler, seen = _recording_handler(served_model=_JUDGE_SLUG, message={"content": "VERIFIED"})
    _make_transport(handler).complete(
        RoleRequest(role="judge", model_slug=_JUDGE_SLUG, prompt="decide", params={"max_tokens": 16})
    )
    assert seen["body"]["max_tokens"] == 8192


def test_env_override_clamped_to_provider_chain_min(monkeypatch):
    """I-arch-003 (#1253) Codex gate P2 hardening: a too-LARGE env override must clamp DOWN to the
    role's chain-min ceiling so it can never reintroduce a provider-cap 400 ("requested N > max M")."""
    # Judge: bad override 999_999 (via PG_D8_VERDICT_MAX_TOKENS, the FIX #2 knob) -> _build_openrouter_body
    # clamps to the chain min 262140, THEN the A2-CLAMP finalize_body() chokepoint clamps again DOWN
    # against the 262144 serving window so the prompt fits: 262144 - 4 ("decide") - 2048 margin = 260092
    # (RC2 HTTP-400 fix). The 400-proof chain-min backstop survives the verdict-budget rename.
    monkeypatch.setenv("PG_D8_VERDICT_MAX_TOKENS", "999999")
    handler, seen = _recording_handler(served_model=_JUDGE_SLUG, message={"content": "VERIFIED"})
    _make_transport(handler).complete(
        RoleRequest(role="judge", model_slug=_JUDGE_SLUG, prompt="decide", params={"max_tokens": 16})
    )
    assert seen["body"]["max_tokens"] == 260092
    assert seen["body"]["max_tokens"] < 262144  # RC2: never == the window
    monkeypatch.delenv("PG_D8_VERDICT_MAX_TOKENS", raising=False)

    # Mirror: bad total override 999_999 -> clamp to 131072; reasoning cap stays < total.
    monkeypatch.setenv("PG_MIRROR_MAX_TOKENS", "999999")
    monkeypatch.setenv("PG_MIRROR_REASONING_MAX_TOKENS", "999999")
    handler, seen = _recording_handler(served_model=_MIRROR_SLUG, message={"content": "VERIFIED"})
    _make_transport(handler).complete(
        RoleRequest(role="mirror", model_slug=_MIRROR_SLUG, prompt="decide", params={"max_tokens": 16})
    )
    assert seen["body"]["max_tokens"] == 131072
    assert seen["body"]["reasoning"]["max_tokens"] < seen["body"]["max_tokens"], (
        "Mirror reasoning cap must stay strictly below the (clamped) total so the verdict has room"
    )
    monkeypatch.delenv("PG_MIRROR_MAX_TOKENS", raising=False)
    monkeypatch.delenv("PG_MIRROR_REASONING_MAX_TOKENS", raising=False)

    # Sentinel decomposition: bad override 999_999 -> clamp to 131072.
    monkeypatch.setenv("PG_SENTINEL_DECOMPOSITION_MAX_TOKENS", "999999")
    handler, seen = _recording_handler(served_model=_SENTINEL_SLUG, message={"content": "VERIFIED"})
    _make_transport(handler).complete(
        RoleRequest(
            role="sentinel",
            model_slug=_SENTINEL_SLUG,
            messages=[{"role": "user", "content": "decompose"}],
            params={"response_format": {"type": "json_object"}},
        )
    )
    assert seen["body"]["max_tokens"] == 131072


def test_decomposition_sentinel_gets_reasoning_and_generous_max_tokens():
    # I-run11-004: the default Sentinel (minimax/minimax-m2) resolves to "decomposition" mode, which
    # the certification ran WITH reasoning ON + max_tokens>=3000 (a small budget truncates the JSON
    # {verdict, atoms} -> all-UNGROUNDED collapse). So the decomposition Sentinel sends reasoning
    # xhigh AND a generous max_tokens (default 16384), NOT the 256 classifier budget.
    handler, seen = _recording_handler(served_model=_SENTINEL_SLUG, message={"content": "VERIFIED"})
    _make_transport(handler).complete(
        RoleRequest(
            role="sentinel",
            model_slug=_SENTINEL_SLUG,
            messages=[{"role": "user", "content": "decompose this"}],
            params={"documents": [{"doc_id": "d1", "text": "ev"}],
                    "response_format": {"type": "json_object"}, "max_tokens": 16},
        )
    )
    assert seen["body"]["reasoning"] == {"enabled": True, "effort": "xhigh"}
    # I-arch-003 (#1253): decomposition Sentinel default 16384 -> 131072 (min of the minimax-m2 chain
    # google/atlas=196608, novita/minimax=131072 -> safe-on-all 131072).
    assert seen["body"]["max_tokens"] == 131072
    # The certified JSON response_format is forwarded to the body (the robust parser also handles
    # non-JSON-mode output, but the request asks for JSON).
    assert seen["body"]["response_format"] == {"type": "json_object"}


def test_decomposition_sentinel_max_tokens_floored_at_3000(monkeypatch):
    # LAW VI: the decomposition budget is env-overridable, but a too-small override is HARD-FLOORED
    # at 3000 so it can never re-introduce the run-12 JSON truncation.
    monkeypatch.setenv("PG_SENTINEL_DECOMPOSITION_MAX_TOKENS", "500")
    handler, seen = _recording_handler(served_model=_SENTINEL_SLUG, message={"content": "VERIFIED"})
    _make_transport(handler).complete(
        RoleRequest(
            role="sentinel",
            model_slug=_SENTINEL_SLUG,
            messages=[{"role": "user", "content": "decompose"}],
            params={"response_format": {"type": "json_object"}},
        )
    )
    assert seen["body"]["max_tokens"] == 3000


def test_sentinel_classifier_budget_when_reasoning_disabled(monkeypatch):
    # When the Sentinel mode is NOT decomposition (e.g. PG_SENTINEL_REASONING=0 forces it OFF), the
    # classifier path holds: an explicit output budget and no reasoning param. I-arch-003 (#1253)
    # raised the label budget 256 -> 4096 so a slightly verbose label can never truncate.
    monkeypatch.setenv("PG_SENTINEL_REASONING", "0")
    handler, seen = _recording_handler(served_model=_SENTINEL_SLUG, message={"content": "<score>no</score>"})
    _make_transport(handler).complete(
        RoleRequest(
            role="sentinel",
            model_slug=_SENTINEL_SLUG,
            messages=[
                {"role": "assistant", "content": "claim"},
                {"role": "user", "content": "<guardian>g</guardian>"},
            ],
            params={"documents": [{"doc_id": "d1", "text": "ev"}], "max_tokens": 16},
        )
    )
    assert seen["body"]["max_tokens"] == 4096
    assert "reasoning" not in seen["body"]


# --------------------------------------------------------------------------------------
# I-meta-008 / #1026: blank-verdict reasoning step-down ladder
#
# A reasoning-first verifier (GLM Mirror, minimax decomposition Sentinel, kimi Judge) under MAX
# reasoning can burn its whole reasoning budget WITHOUT converging and return blank content. The
# transport must NOT crash the whole 4-role run on that — for an effort-tier model it steps the
# reasoning effort DOWN and retries; for the kimi Judge (no OpenRouter effort tiers -> bare reasoning)
# the effort-step is inert and recovery is PURE PROVIDER ROTATION (the blanked provider is added to
# provider.ignore). Both paths fail-loud only if even the final reasoning-off rung blanks. (This
# reproduced the live drb_72 Mirror pass-2 abort.)
# --------------------------------------------------------------------------------------
def _sequenced_handler(responses: list[dict], *, served_model: str, provider: str = "DeepInfra"):
    """A MockTransport handler returning `responses[i]` for the i-th call (clamped to the last),
    recording every request body so the per-attempt reasoning config can be asserted."""
    seen: dict = {"bodies": []}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["bodies"].append(json.loads(request.content.decode("utf-8")))
        message = responses[min(len(seen["bodies"]) - 1, len(responses) - 1)]
        payload = {
            "model": served_model,
            "provider": provider,
            "choices": [{"message": {"role": "assistant", **message}}],
            "usage": {"prompt_tokens": 11, "completion_tokens": 5},
        }
        return httpx.Response(200, json=payload)

    return handler, seen


def test_blank_verdict_steps_down_reasoning_and_recovers():
    # I-judge-kimi (2026-06-29): the blank-verdict ladder for the kimi Judge recovers via PROVIDER
    # ROTATION, not effort-stepping. moonshotai/kimi-k2.6 advertises NO effort tiers, so
    # _judge_reasoning_block re-sends the SAME bare {enabled: True} on every rung — the effort-step
    # is INERT. The HONEST recovery is the ignore-list: the blanked provider (DeepInfra) is added to
    # provider.ignore so the paid retry load-balances onto a different healthy kimi endpoint (the
    # 21-provider spread is the whole point of the swap). First (DeepInfra) blanks-after-reasoning;
    # the rotated retry returns a real verdict. complete() must return it, NOT raise. (The
    # effort-reasoning step-down ladder is still exercised by the minimax decomposition Sentinel in
    # test_decomposition_sentinel_blank_steps_down_reasoning_and_recovers.)
    blank = {"content": "", "reasoning": "looped without converging on a verdict"}
    good = {"content": "VERIFIED"}
    handler, seen = _sequenced_handler([blank, good], served_model=_JUDGE_SLUG)
    resp = _make_transport(handler).complete(
        RoleRequest(role="judge", model_slug=_JUDGE_SLUG, prompt="decide")
    )
    assert resp.raw_text == "VERIFIED"
    assert len(seen["bodies"]) == 2, "should have retried exactly once after the blank"
    # BARE reasoning ON both attempts (no effort key -> never starved, §9.1.8).
    assert seen["bodies"][0]["reasoning"] == {"enabled": True}, "first attempt: bare reasoning ON"
    assert seen["bodies"][1]["reasoning"] == {"enabled": True}, "retry stays bare (effort-step inert)"
    # The RECOVERY mechanism is PROVIDER ROTATION: the blanked provider is in the retry's ignore list.
    assert "ignore" not in seen["bodies"][0].get("provider", {}), "first attempt: nothing ignored yet"
    assert "deepinfra" in seen["bodies"][1]["provider"]["ignore"], "blanked provider rotated out"


def test_blank_verdict_ladder_exhausted_fails_loud_with_reasoning_off_last():
    # Every attempt blanks -> fail loud after the ladder (3 attempts at the default cap). I-judge-kimi:
    # the kimi Judge sends BARE reasoning, so the first two rungs rotate provider (effort-step inert)
    # while the FINAL rung still disables reasoning entirely (no `reasoning` block) to force content;
    # when even that blanks the transport raises BlankVerdictError (a RoleTransportError subclass).
    blank = {"content": "", "reasoning": "never converges"}
    handler, seen = _sequenced_handler([blank], served_model=_JUDGE_SLUG)
    with pytest.raises(BlankVerdictError):
        _make_transport(handler).complete(
            RoleRequest(role="judge", model_slug=_JUDGE_SLUG, prompt="decide")
        )
    assert len(seen["bodies"]) == 3, "default ladder is (xhigh, low, off) = 3 attempts"
    # Rungs 1-2: bare reasoning (effort-step inert for kimi); recovery is provider rotation.
    assert seen["bodies"][0]["reasoning"] == {"enabled": True}
    assert seen["bodies"][1]["reasoning"] == {"enabled": True}
    assert "deepinfra" in seen["bodies"][1]["provider"]["ignore"], "blanked provider rotated out"
    # Final rung still disables reasoning entirely (a real change even for a bare-reasoning model) to
    # force content; even that blank -> genuine fail-loud (no synthesized verdict).
    assert "reasoning" not in seen["bodies"][2], "final resort disables reasoning to force content"
    # require_parameters pin is dropped once reasoning is off (it only forces reasoning honoring)
    assert "provider" not in seen["bodies"][2] or "require_parameters" not in seen["bodies"][2].get("provider", {})


def test_classifier_sentinel_blank_is_single_attempt_no_stepdown(monkeypatch):
    # A reasoning-DISABLED Sentinel (PG_SENTINEL_REASONING=0, the sovereign classifier path) has no
    # `reasoning` block to step down — it makes ONE attempt and a blank still fails loud (the ladder
    # is reasoning-roles-only).
    monkeypatch.setenv("PG_SENTINEL_REASONING", "0")
    handler, seen = _sequenced_handler([{"content": ""}], served_model=_SENTINEL_SLUG)
    with pytest.raises(RoleTransportError):
        _make_transport(handler).complete(
            RoleRequest(role="sentinel", model_slug=_SENTINEL_SLUG, prompt="x")
        )
    assert len(seen["bodies"]) == 1, "classifier Sentinel must NOT retry (no reasoning ladder)"


def test_decomposition_sentinel_blank_steps_down_reasoning_and_recovers():
    # I-run11-004: the reasoning-ON decomposition Sentinel DOES follow the blank-verdict step-down
    # ladder (xhigh -> low -> off) like the other reasoning verifiers — a non-converging xhigh blank
    # must not crash the run.
    blank = {"content": "", "reasoning": "looped without converging"}
    good = {"content": '{"verdict": "supported", "unsupported_atoms": 0, "atoms": []}'}
    handler, seen = _sequenced_handler([blank, good], served_model=_SENTINEL_SLUG)
    resp = _make_transport(handler).complete(
        RoleRequest(role="sentinel", model_slug=_SENTINEL_SLUG, prompt="decompose")
    )
    assert resp.raw_text == good["content"]
    assert len(seen["bodies"]) == 2, "decomposition Sentinel retries after a blank"
    assert seen["bodies"][0]["reasoning"]["effort"] == "xhigh"
    assert seen["bodies"][1]["reasoning"]["effort"] == "low"


def test_blank_attempt_bills_tokens_into_run_budget(monkeypatch):
    # Codex diff-gate P1: a DISCARDED blank attempt's tokens must be accounted into the shared
    # run-budget accumulator (RecordingTransport bills only the final returned response, so without
    # this the expensive xhigh blank attempt would bypass PG_MAX_COST_PER_RUN). The successful
    # attempt stays billed by RecordingTransport -> only the blank is billed here (no double-count).
    import src.polaris_graph.llm.openrouter_client as orc

    billed: list[float] = []
    checks: list[float] = []
    monkeypatch.setattr(orc, "_add_run_cost", lambda c: billed.append(c))
    monkeypatch.setattr(orc, "check_run_budget", lambda d=0.0: checks.append(d))

    blank = {"content": "", "reasoning": "looped without converging"}
    good = {"content": "VERIFIED"}
    handler, _seen = _sequenced_handler([blank, good], served_model=_JUDGE_SLUG)
    resp = _make_transport(handler).complete(
        RoleRequest(role="judge", model_slug=_JUDGE_SLUG, prompt="decide")
    )
    assert resp.raw_text == "VERIFIED"
    assert len(billed) == 1, "exactly the ONE blank attempt's tokens are billed inline"
    assert billed[0] > 0.0, "a blank xhigh attempt cost real tokens — must not bill $0"
    assert checks == [0], "the run budget is checked once, before the paid retry"


def test_blank_attempt_budget_exceeded_aborts_before_next_retry(monkeypatch):
    # The inline budget check must fail-fast: if accounting the blank attempt crosses the cap,
    # BudgetExceededError propagates and NO further (paid) retry is issued.
    import src.polaris_graph.llm.openrouter_client as orc

    monkeypatch.setattr(orc, "_add_run_cost", lambda c: None)

    def _over_cap(_delta=0.0):
        raise orc.BudgetExceededError("PG_MAX_COST_PER_RUN crossed by the blank retry")

    monkeypatch.setattr(orc, "check_run_budget", _over_cap)

    blank = {"content": "", "reasoning": "x"}
    good = {"content": "VERIFIED"}
    handler, seen = _sequenced_handler([blank, good], served_model=_MIRROR_SLUG)
    with pytest.raises(orc.BudgetExceededError):
        _make_transport(handler).complete(
            RoleRequest(role="mirror", model_slug=_MIRROR_SLUG, prompt="decide")
        )
    assert len(seen["bodies"]) == 1, "the cap abort must prevent the next paid retry"


# --------------------------------------------------------------------------------------
# I-run11-008 (#1053): transient transport failure (connection reset / WinError 10054) on a single
# role call is RETRIED (bounded), not allowed to abort the whole multi-hundred-call run.
# --------------------------------------------------------------------------------------
def test_transport_error_retries_then_recovers():
    # The first POST raises a connection reset; the bounded transport retry re-issues it and the
    # second POST returns a real verdict. complete() must return that verdict, NOT crash the run.
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            raise httpx.ConnectError("WinError 10054 connection reset by peer", request=request)
        return httpx.Response(
            200,
            json={
                "model": _JUDGE_SLUG,
                "provider": "DeepInfra",
                "choices": [{"message": {"role": "assistant", "content": "VERIFIED"}}],
                "usage": {"prompt_tokens": 11, "completion_tokens": 5},
            },
        )

    resp = _make_transport(handler).complete(
        RoleRequest(role="judge", model_slug=_JUDGE_SLUG, prompt="decide")
    )
    assert resp.raw_text == "VERIFIED"
    assert calls["n"] == 2, "the reset retried exactly once before succeeding"


def test_transport_error_exhausted_fails_loud(monkeypatch):
    # LAW II (fail loud, no silent fallback): when EVERY retry hits a transport error the transport
    # raises RoleTransportError — it never silently returns an empty/None verdict.
    monkeypatch.setenv("PG_ROLE_TRANSPORT_RETRIES", "1")
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        raise httpx.ConnectError("reset", request=request)

    with pytest.raises(RoleTransportError):
        _make_transport(handler).complete(
            RoleRequest(role="judge", model_slug=_JUDGE_SLUG, prompt="decide")
        )
    assert calls["n"] == 2, "PG_ROLE_TRANSPORT_RETRIES=1 -> 1 original + 1 retry = 2 attempts"
