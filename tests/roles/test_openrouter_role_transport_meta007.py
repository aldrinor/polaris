"""Tests for the benchmark-stage OpenRouter verifier RoleTransport (I-meta-007d).

SPEND-FREE: every test injects an `httpx.Client(transport=httpx.MockTransport(...))` (or feeds a
faked OpenRouter catalog through the same), so there is NO socket / NO real LLM / NO spend in any
path pytest exercises — the OpenRouter HTTP is monkeypatched at the transport layer.

Asserts the I-meta-007d contract (P1-1..P1-4 + P2 fixes, diff-gate iter-1):
  (a) the transport sends each verifier role's BENCHMARK lineup slug (Mirror `z-ai/glm-5.1`,
      Sentinel `ibm-granite/granite-4.1-8b`, Judge `qwen/qwen3.6-35b-a3b` — NOT the lock's
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
      4-distinct-family check over the deepseek/z-ai/ibm-granite/qwen benchmark lineup.

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
    OpenAICompatibleRoleTransport,
    RoleTransportError,
)
from src.polaris_graph.roles.openrouter_role_transport import (
    OpenRouterRoleTransport,
    benchmark_verifier_lineup,
    openrouter_role_endpoint,
)
from src.polaris_graph.roles.role_transport import RoleRequest, RoleResponse

# BENCHMARK-STAGE OpenRouter lineup slugs (P1-1 — role_selection_final.md, NOT the lock's
# self-host slugs). Mirror + Sentinel differ from the lock (cohere / granite-GUARDIAN are not on
# OpenRouter); Judge is identical to the lock.
_MIRROR_SLUG = "z-ai/glm-5.1"
_SENTINEL_SLUG = "ibm-granite/granite-4.1-8b"
_JUDGE_SLUG = "qwen/qwen3.6-35b-a3b"

# Writer/generator (unchanged in the lock + benchmark lineup) — referenced by the preflight
# catalog fixtures so the 4th OpenRouter entry is realistic.
_WRITER_SLUG = "deepseek/deepseek-v4-pro"

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
    # Codex iter-2 P1: reasoning is PER-ROLE. The Sentinel classifier sends NEITHER reasoning nor
    # provider/require_parameters (its OpenRouter slug does not advertise `reasoning`, so those
    # params would break routing). The deliberative verifiers (Mirror/Judge) send BOTH.
    if role == "sentinel":
        assert "reasoning" not in body
        assert "provider" not in body
    else:
        # P1-2 MAX reasoning: enabled + effort "xhigh" (OpenRouter's documented MAXIMUM effort).
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
    """P1-1: the transport's served slug == the benchmark lineup == verifier_model_slugs (pinned),
    and the active families are deepseek/z-ai/ibm-granite/qwen (4 distinct)."""
    lineup = benchmark_verifier_lineup()
    assert lineup == {
        "mirror": _MIRROR_SLUG,        # z-ai/glm-5.1
        "sentinel": _SENTINEL_SLUG,    # ibm-granite/granite-4.1-8b
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
    # LAW VI: effort is env-overridable. The module reads the env at import; reload to pick it up.
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
        assert seen["body"]["reasoning"] == {"enabled": True, "effort": "medium"}
    finally:
        # Restore the module to its default-effort state for the rest of the suite.
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
    # P1-1: the preflight resolves the BENCHMARK lineup slugs (z-ai/glm-5.1, granite-4.1-8b,
    # qwen3.6-35b-a3b) against the catalog — NOT the lock self-host slugs.
    catalog = [
        {
            "id": _MIRROR_SLUG,
            "canonical_slug": "z-ai/glm-5.1-20260520",
            "supported_parameters": ["reasoning", "max_tokens"],
        },
        {"id": _SENTINEL_SLUG, "canonical_slug": _SENTINEL_SLUG},
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
        {"id": _SENTINEL_SLUG},
        {"id": _JUDGE_SLUG, "supported_parameters": ["reasoning", "max_tokens"]},
    ]
    resolved = run_gate_b.preflight_openrouter_roles(http_client=_catalog_client(catalog))
    assert resolved["mirror"] == _MIRROR_SLUG


def test_preflight_openrouter_missing_slug_fails_loud():
    # Judge slug absent from the catalog (neither id nor canonical_slug) -> fail loud.
    # Mirror advertises `reasoning` so its executability check passes and the loop reaches the
    # missing Judge, where the PRESENCE failure (match="judge") fires.
    catalog = [
        {"id": _MIRROR_SLUG, "supported_parameters": ["reasoning"]},
        {"id": _SENTINEL_SLUG},
    ]
    with pytest.raises(RuntimeError, match="judge"):
        run_gate_b.preflight_openrouter_roles(http_client=_catalog_client(catalog))


def test_preflight_openrouter_fails_when_reasoning_role_lacks_reasoning_support():
    # Codex iter-2 P1: a reasoning-enabled role (Mirror) whose slug does NOT advertise `reasoning`
    # must fail preflight — with require_parameters=True OpenRouter would refuse to route. Sentinel
    # is reasoning-disabled so its lack of `reasoning` is fine; Judge advertises it.
    catalog = [
        {"id": _MIRROR_SLUG, "supported_parameters": ["max_tokens"]},
        {"id": _SENTINEL_SLUG, "supported_parameters": ["max_tokens"]},
        {"id": _JUDGE_SLUG, "supported_parameters": ["reasoning", "max_tokens"]},
    ]
    with pytest.raises(RuntimeError, match="(?i)mirror|reasoning"):
        run_gate_b.preflight_openrouter_roles(http_client=_catalog_client(catalog))


def test_preflight_openrouter_sentinel_without_reasoning_passes():
    # The Sentinel classifier is reasoning-DISABLED, so its slug not advertising `reasoning` must
    # NOT fail preflight (only reasoning-enabled roles get the executability check). Mirror+Judge
    # advertise `reasoning`; Sentinel does not -> the preflight still resolves.
    catalog = [
        {"id": _MIRROR_SLUG, "supported_parameters": ["reasoning", "max_tokens"]},
        {"id": _SENTINEL_SLUG, "supported_parameters": ["max_tokens", "temperature"]},
        {"id": _JUDGE_SLUG, "supported_parameters": ["reasoning", "max_tokens"]},
    ]
    resolved = run_gate_b.preflight_openrouter_roles(http_client=_catalog_client(catalog))
    assert resolved == {
        "mirror": _MIRROR_SLUG,
        "sentinel": _SENTINEL_SLUG,
        "judge": _JUDGE_SLUG,
    }


def test_preflight_openrouter_non_200_fails_loud():
    catalog = [{"id": _MIRROR_SLUG}, {"id": _SENTINEL_SLUG}, {"id": _JUDGE_SLUG}]
    with pytest.raises(RuntimeError, match="HTTP 503"):
        run_gate_b.preflight_openrouter_roles(
            http_client=_catalog_client(catalog, status_code=503)
        )


def test_family_check_passes_on_benchmark_lineup(monkeypatch):
    # P1-1: in openrouter mode the 4-distinct-family check asserts on the ACTIVE benchmark
    # families (generator deepseek from the lock + benchmark verifiers z-ai/ibm-granite/qwen),
    # which are 4 distinct lineages — it must PASS (no collision).
    monkeypatch.delenv("PG_FOUR_ROLE_TRANSPORT", raising=False)  # default openrouter
    fams = run_gate_b.assert_four_role_families_distinct()
    assert fams == {
        "generator": "deepseek",
        "mirror": "z-ai",
        "sentinel": "ibm-granite",
        "judge": "qwen",
    }
    assert len(set(fams.values())) == 4


def test_family_check_fails_loud_on_cross_family_override(monkeypatch):
    # P1-1 clinical-lethal guard: a PG_<ROLE>_MODEL override that leaves the role's family lane
    # must FAIL LOUD (not silently pass on a static family map). PG_JUDGE_MODEL=z-ai/glm-5.1 would
    # serve Judge AND Mirror as z-ai (same family self-verifying) — the active-family-from-slug
    # derivation must catch it. This reproduces the hole a static-map family check would miss.
    monkeypatch.delenv("PG_FOUR_ROLE_TRANSPORT", raising=False)  # default openrouter
    monkeypatch.setenv("PG_JUDGE_MODEL", "z-ai/glm-5.1")
    with pytest.raises((RuntimeError, ValueError), match="(?i)judge|lane|collision"):
        run_gate_b.assert_four_role_families_distinct()


def test_family_check_passes_on_in_lane_override(monkeypatch):
    # An IN-LANE override (same provider prefix as the default) is accepted — only a cross-family
    # re-pick is rejected. PG_MIRROR_MODEL=z-ai/glm-5.1-pro stays in the z-ai lane.
    monkeypatch.delenv("PG_FOUR_ROLE_TRANSPORT", raising=False)
    monkeypatch.setenv("PG_MIRROR_MODEL", "z-ai/glm-5.1-pro")
    fams = run_gate_b.assert_four_role_families_distinct()
    assert fams["mirror"] == "z-ai"
    assert len(set(fams.values())) == 4


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
        "sentinel": "ibm-granite",
        "judge": "qwen",
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
# max_tokens (default 16384), NOT have it popped — effort=xhigh allocates ~95% to reasoning and
# max_tokens must be strictly higher so the bare verdict has room (popping it starved the verdict to
# empty). Sentinel gets an explicit classifier budget instead of pop-and-hope on the provider default.
# --------------------------------------------------------------------------------------
@pytest.mark.parametrize("role,slug", [("judge", _JUDGE_SLUG), ("mirror", _MIRROR_SLUG)])
def test_reasoning_role_sets_generous_max_tokens(role, slug):
    # The Judge adapter sets _DEFAULT_MAX_TOKENS=16; the transport must OVERRIDE it to the generous
    # verifier budget (16384) so xhigh reasoning AND the bare verdict both fit.
    handler, seen = _recording_handler(served_model=slug, message={"content": "VERIFIED"})
    _make_transport(handler).complete(
        RoleRequest(role=role, model_slug=slug, prompt="decide", params={"max_tokens": 16})
    )
    assert seen["body"]["max_tokens"] == 16384, f"{role}: reasoning role must get the generous verifier budget"
    # reasoning is still requested at MAX effort.
    assert seen["body"]["reasoning"] == {"enabled": True, "effort": "xhigh"}


def test_reasoning_role_max_tokens_env_overridable(monkeypatch):
    # LAW VI: the verifier reasoning budget is env-overridable.
    monkeypatch.setenv("PG_VERIFIER_REASONING_MAX_TOKENS", "8192")
    handler, seen = _recording_handler(served_model=_JUDGE_SLUG, message={"content": "VERIFIED"})
    _make_transport(handler).complete(
        RoleRequest(role="judge", model_slug=_JUDGE_SLUG, prompt="decide", params={"max_tokens": 16})
    )
    assert seen["body"]["max_tokens"] == 8192


def test_sentinel_gets_explicit_classifier_budget():
    # Sentinel is reasoning-disabled (a classifier); it gets an explicit output budget (default 256),
    # not a pop-and-hope on the provider default, and no reasoning param is sent.
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
    assert seen["body"]["max_tokens"] == 256
    assert "reasoning" not in seen["body"]
