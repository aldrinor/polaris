"""Offline smoke for I-cred-013 (#1163): the SUPER-HEAVY behavioral pre-spend preflight.

NO network, NO spend: every live probe (canary, generator-slug, verifier-slug, credibility-judge,
STORM, chromium) and the false-alarm runtime asserts are DEPENDENCY-INJECTED, so the fail-closed
logic is exercised with faked alive/dead results. Each new probe's dead path is asserted to raise
GateError INDIVIDUALLY, and a fully-green path returns the machine-readable summary.

Hermetic env (mirrors tests/dr_benchmark/test_behavioral_canary_canary01_iready017.py conventions).
"""
from __future__ import annotations

import asyncio
import os

import pytest

from scripts.dr_benchmark.pathB_run_gate import GateError
from scripts.dr_benchmark.super_heavy_preflight import (
    _CREDIBILITY_REDESIGN_FLAG,
    credibility_redesign_active,
    super_heavy_preflight,
)


@pytest.fixture(autouse=True)
def _isolate_env():
    snap = dict(os.environ)
    try:
        yield
    finally:
        os.environ.clear()
        os.environ.update(snap)


# --------------------------------------------------------------------------- all-green fakes
async def _canary_ok() -> None:
    return None


async def _gen_ok() -> bool:
    return True


def _verifiers_ok() -> dict[str, str]:
    return {"mirror": "z-ai/glm-5.1", "sentinel": "minimax/minimax-m2", "judge": "qwen/qwen3.6-35b-a3b"}


def _cred_inactive() -> None:
    return None


def _cred_alive() -> str:
    return "z-ai/glm-5.1"


async def _storm_ok() -> int:
    return 2


async def _chromium_ok() -> None:
    return None


def _false_alarms_ok() -> list[str]:
    return ["fa1", "fa2", "fa3", "fa4", "fa5"]


def _all_green_kwargs(**overrides):
    base = dict(
        canary=_canary_ok,
        generator_slug_probe=_gen_ok,
        verifier_slug_probe=_verifiers_ok,
        credibility_judge_probe=_cred_inactive,
        storm_probe=_storm_ok,
        chromium_probe=_chromium_ok,
        false_alarm_asserts=_false_alarms_ok,
    )
    base.update(overrides)
    return base


# --------------------------------------------------------------------------- green path
def test_super_heavy_preflight_all_green_returns_summary(capsys):
    summary = asyncio.run(super_heavy_preflight(**_all_green_kwargs()))
    assert "SUPER_HEAVY_PREFLIGHT_OK" in capsys.readouterr().out
    assert summary["false_alarm_locks_passed"] == ["fa1", "fa2", "fa3", "fa4", "fa5"]
    assert summary["chromium"] == "present_or_intentionally_off"
    assert summary["behavioral_canary"] == "ok"
    assert summary["generator_slug"] == "alive"
    assert summary["verifier_slugs_alive"]["sentinel"] == "minimax/minimax-m2"
    assert summary["credibility_judge"] == "inactive_this_run"
    assert summary["storm_personas"] == 2


def test_super_heavy_preflight_reports_active_credibility_slug():
    summary = asyncio.run(super_heavy_preflight(**_all_green_kwargs(credibility_judge_probe=_cred_alive)))
    assert summary["credibility_judge"] == "z-ai/glm-5.1"


# --------------------------------------------------------------------------- each dead path -> GateError
def test_fails_closed_when_a_false_alarm_regresses():
    def _fa_regressed() -> list[str]:
        raise GateError("false-alarm regression lock test_fa1 FAILED at run time")

    with pytest.raises(GateError, match="false-alarm"):
        asyncio.run(super_heavy_preflight(**_all_green_kwargs(false_alarm_asserts=_fa_regressed)))


def test_fails_closed_when_chromium_dead():
    async def _chromium_dead() -> None:
        raise GateError("chromium browser-fetch tier is DEAD on this host")

    with pytest.raises(GateError, match="chromium"):
        asyncio.run(super_heavy_preflight(**_all_green_kwargs(chromium_probe=_chromium_dead)))


def test_fails_closed_when_canary_fails():
    async def _canary_dead() -> None:
        raise GateError("behavioral canary: 1-query primary-backend search returned 0 live sources")

    with pytest.raises(GateError, match="canary"):
        asyncio.run(super_heavy_preflight(**_all_green_kwargs(canary=_canary_dead)))


def test_fails_closed_when_generator_slug_dead():
    async def _gen_dead() -> bool:
        return False

    with pytest.raises(GateError, match="generator slug"):
        asyncio.run(super_heavy_preflight(**_all_green_kwargs(generator_slug_probe=_gen_dead)))


def test_fails_closed_when_generator_probe_raises_404():
    async def _gen_404() -> bool:
        raise GateError("structured-output probe got NoEndpointError")

    with pytest.raises(GateError, match="NoEndpointError"):
        asyncio.run(super_heavy_preflight(**_all_green_kwargs(generator_slug_probe=_gen_404)))


def test_normalizes_arbitrary_generator_failure_to_gateerror():
    async def _gen_boom() -> bool:
        raise RuntimeError("network exploded")

    with pytest.raises(GateError, match="fail closed"):
        asyncio.run(super_heavy_preflight(**_all_green_kwargs(generator_slug_probe=_gen_boom)))


def test_fails_closed_when_a_verifier_slug_dead():
    def _verifier_dead() -> dict[str, str]:
        raise GateError("verifier role 'sentinel' slug 'minimax/minimax-m2' is NOT alive")

    with pytest.raises(GateError, match="sentinel"):
        asyncio.run(super_heavy_preflight(**_all_green_kwargs(verifier_slug_probe=_verifier_dead)))


def test_fails_closed_when_no_verifiers_alive():
    def _verifiers_empty() -> dict[str, str]:
        return {}

    with pytest.raises(GateError, match="no alive roles"):
        asyncio.run(super_heavy_preflight(**_all_green_kwargs(verifier_slug_probe=_verifiers_empty)))


def test_fails_closed_when_credibility_judge_dead():
    def _cred_dead() -> str:
        raise GateError("credibility judge slug 'z-ai/glm-5.1' is NOT alive in its production call shape")

    with pytest.raises(GateError, match="credibility judge"):
        asyncio.run(super_heavy_preflight(**_all_green_kwargs(credibility_judge_probe=_cred_dead)))


def test_fails_closed_when_storm_empty():
    async def _storm_empty() -> int:
        return 0

    with pytest.raises(GateError, match="0 personas"):
        asyncio.run(super_heavy_preflight(**_all_green_kwargs(storm_probe=_storm_empty)))


def test_normalizes_arbitrary_storm_failure_to_gateerror():
    async def _storm_boom() -> int:
        raise RuntimeError("storm exploded")

    with pytest.raises(GateError, match="fail closed"):
        asyncio.run(super_heavy_preflight(**_all_green_kwargs(storm_probe=_storm_boom)))


# --------------------------------------------------------------------------- credibility-activation read
def test_credibility_redesign_active_matches_runner_off_tokens():
    for off in ("", "0", "false", "off", "no", "FALSE", " Off "):
        os.environ[_CREDIBILITY_REDESIGN_FLAG] = off
        assert credibility_redesign_active() is False, f"{off!r} must read as OFF (matches the runner)"
    for on in ("1", "true", "on", "yes", "redesign"):
        os.environ[_CREDIBILITY_REDESIGN_FLAG] = on
        assert credibility_redesign_active() is True, f"{on!r} must read as ON (matches the runner)"


def test_credibility_redesign_active_default_off():
    os.environ.pop(_CREDIBILITY_REDESIGN_FLAG, None)
    assert credibility_redesign_active() is False


# --------------------------------------------------------------------------- real default probes wired
def test_default_chromium_probe_reuses_fx16_and_fails_closed(monkeypatch):
    """The real chromium default reuses pg_preflight's FX-16 probe and maps FAIL -> GateError (no
    network, no real browser — the FX-16 result is monkeypatched)."""
    import scripts.dr_benchmark.super_heavy_preflight as m
    import scripts.pg_preflight as pf

    async def _fake_fail():
        return pf.TestResult("chromium_browser_available", pf.FAIL, "playwright install chromium ...")

    monkeypatch.setattr(pf, "test_chromium_browser_available", _fake_fail)
    with pytest.raises(GateError, match="chromium"):
        asyncio.run(m._default_chromium_probe())


def test_default_chromium_probe_passes_when_present(monkeypatch):
    import scripts.dr_benchmark.super_heavy_preflight as m
    import scripts.pg_preflight as pf

    async def _fake_pass():
        return pf.TestResult("chromium_browser_available", pf.PASS, "chromium present: /x/chrome")

    monkeypatch.setattr(pf, "test_chromium_browser_available", _fake_pass)
    assert asyncio.run(m._default_chromium_probe()) is None  # no raise


def test_default_chromium_probe_skip_intentionally_off_passes(monkeypatch):
    import scripts.dr_benchmark.super_heavy_preflight as m
    import scripts.pg_preflight as pf

    async def _fake_skip_off():
        return pf.TestResult(
            "chromium_browser_available", pf.SKIP, "PG_DISABLE_ACCESS_BYPASS=1 -- intentionally off"
        )

    monkeypatch.setattr(pf, "test_chromium_browser_available", _fake_skip_off)
    assert asyncio.run(m._default_chromium_probe()) is None  # intentionally-off SKIP passes


def test_default_chromium_probe_skip_would_fail_escalates(monkeypatch):
    """A DRY 'would FAIL in LIVE/paid' SKIP must ESCALATE to GateError — the super-heavy preflight is a
    paid-run gate, so a dead browser tier on the run host must fail closed."""
    import scripts.dr_benchmark.super_heavy_preflight as m
    import scripts.pg_preflight as pf

    async def _fake_skip_would_fail():
        return pf.TestResult(
            "chromium_browser_available", pf.SKIP, "[would FAIL in LIVE/paid mode] chromium absent"
        )

    monkeypatch.setattr(pf, "test_chromium_browser_available", _fake_skip_would_fail)
    with pytest.raises(GateError, match="would-fail remediation"):
        asyncio.run(m._default_chromium_probe())


def test_default_credibility_probe_noop_when_redesign_off():
    """When the redesign is OFF, the real default probe returns None WITHOUT importing/calling the live
    caller (no network) — probe-alive matches production activation."""
    import scripts.dr_benchmark.super_heavy_preflight as m

    os.environ.pop(_CREDIBILITY_REDESIGN_FLAG, None)
    assert m._default_credibility_judge_probe() is None


# --------------------------------------------------------------------------- slate wiring
def test_super_heavy_preflight_is_in_slate_force_on_and_required():
    """The super-heavy preflight must be force-on + required in the benchmark slate, so a paid run can
    NEVER silently drop back to the lighter canary alone."""
    from scripts.dr_benchmark.run_gate_b import (
        _BENCHMARK_FORCE_ON_FLAGS,
        _BENCHMARK_PREFLIGHT_REQUIRED_FLAGS,
        _FULL_CAPABILITY_BENCHMARK_SLATE,
    )

    flag = "PG_SUPER_HEAVY_PREFLIGHT"
    assert _FULL_CAPABILITY_BENCHMARK_SLATE.get(flag) == "1"
    assert flag in _BENCHMARK_FORCE_ON_FLAGS
    assert flag in _BENCHMARK_PREFLIGHT_REQUIRED_FLAGS


def test_super_heavy_preflight_force_on_over_preset_zero():
    from scripts.dr_benchmark.run_gate_b import apply_full_capability_benchmark_slate

    os.environ["PG_SUPER_HEAVY_PREFLIGHT"] = "0"
    apply_full_capability_benchmark_slate()
    assert os.environ.get("PG_SUPER_HEAVY_PREFLIGHT") == "1", "force-on did not override preset 0"


def test_preflight_fails_closed_when_super_heavy_off():
    from scripts.dr_benchmark.run_gate_b import (
        _BENCHMARK_PREFLIGHT_REQUIRED_FLAGS,
        apply_full_capability_benchmark_slate,
        preflight_full_capability,
    )

    apply_full_capability_benchmark_slate()
    for flag in _BENCHMARK_PREFLIGHT_REQUIRED_FLAGS:
        os.environ[flag] = "1"
    os.environ["PG_STRICT_VERIFY_ENTAILMENT"] = "enforce"
    os.environ["PG_SUPER_HEAVY_PREFLIGHT"] = "0"
    with pytest.raises(RuntimeError) as exc:
        preflight_full_capability()
    assert "PG_SUPER_HEAVY_PREFLIGHT" in str(exc.value)


def test_default_false_alarm_asserts_runs_the_committed_checks():
    """The real default imports + runs the 5 SHARED false-alarm checks from the NON-test module (offline,
    deterministic). They pass on a clean tree, proving the runtime re-assertion is wired to the SAME
    checks CI enforces — and WITHOUT importing tests/ on the paid VM."""
    import scripts.dr_benchmark.super_heavy_preflight as m

    passed = m._default_false_alarm_asserts()
    assert passed == [
        "check_fa1_crlf_gitattributes_rule_committed",
        "check_fa2_competitor_outputs_present",
        "check_fa3_run_health_fail_loud_guard_present",
        "check_fa4_empty_response_failover_present",
        "check_fa5_journal_only_gated_by_source_restriction",
    ]


def test_false_alarm_runtime_assert_does_not_import_tests_module():
    """The production runtime assert must NOT depend on the tests/ package (paid-VM launch shape). The
    shared check logic lives in a NON-test module; importing it must NOT require tests.preflight."""
    import scripts.dr_benchmark.false_alarm_checks as fac

    assert hasattr(fac, "ALL_CHECKS") and len(fac.ALL_CHECKS) == 5
    assert "tests" not in fac.__name__


# --------------------------------------------------------------------------- live-loop regression
def test_real_chromium_default_runs_inside_running_event_loop(monkeypatch):
    """REGRESSION: super_heavy_preflight is awaited from run_gate_b_query's ALREADY-RUNNING event loop.
    The real _default_chromium_probe must NOT call asyncio.run (that raises 'cannot be called from a
    running event loop' and crashes every live run). Drive the REAL chromium default (FX-16 faked to
    PASS — no real browser) through an awaited super_heavy_preflight, all network probes faked, and
    assert it does NOT raise RuntimeError and reaches SUPER_HEAVY_PREFLIGHT_OK."""
    import scripts.pg_preflight as pf
    import scripts.dr_benchmark.super_heavy_preflight as m

    async def _fake_pass():
        return pf.TestResult("chromium_browser_available", pf.PASS, "chromium present: /x/chrome")

    monkeypatch.setattr(pf, "test_chromium_browser_available", _fake_pass)

    async def _drive():
        # NOTE: chromium_probe is NOT injected here — the REAL m._default_chromium_probe runs, awaited
        # from this running loop (the production shape). Only the FX-16 leaf is faked.
        return await super_heavy_preflight(
            **{k: v for k, v in _all_green_kwargs().items() if k != "chromium_probe"}
        )

    summary = asyncio.run(_drive())  # must NOT raise RuntimeError('running event loop')
    assert summary["chromium"] == "present_or_intentionally_off"


# --------------------------------------------------------------------------- REAL dead-slug -> GateError
# This is the test that proves the drb_72 fix: the _real_chat_completion_alive leaf maps a 404 (dead
# route / NoEndpoint) to GateError, driven through _default_verifier_slug_probe with a faked httpx
# transport — NO network, NO spend.
def _mock_404_client():
    import httpx

    def _handler(request):
        return httpx.Response(404, json={"error": {"message": "No endpoints found", "code": 404}})

    return httpx.Client(transport=httpx.MockTransport(_handler))


def _mock_200_client():
    import httpx

    def _handler(request):
        return httpx.Response(
            200, json={"choices": [{"message": {"content": "ok"}}], "model": "probe"}
        )

    return httpx.Client(transport=httpx.MockTransport(_handler))


def test_real_verifier_probe_maps_404_to_gateerror(monkeypatch):
    """A dead verifier slug (404 from the route) must FAIL CLOSED with a GateError naming the role+slug —
    the drb_72 silent-dead-route class. Driven through the REAL _real_chat_completion_alive leaf with a
    faked 404 transport (no network)."""
    import scripts.dr_benchmark.super_heavy_preflight as m
    import scripts.dr_benchmark.run_gate_b as rgb

    monkeypatch.setattr(rgb, "four_role_transport_mode", lambda: "openrouter")
    monkeypatch.setattr(rgb, "verifier_model_slugs", lambda: {"mirror": "z-ai/glm-5.1"})
    os.environ["OPENROUTER_API_KEY"] = "test-key"

    client = _mock_404_client()
    try:
        with pytest.raises(GateError, match=r"mirror.*z-ai/glm-5.1|z-ai/glm-5.1.*mirror|NOT alive"):
            m._default_verifier_slug_probe(http_client=client)
    finally:
        client.close()


def test_real_verifier_probe_passes_on_200_envelope(monkeypatch):
    """A live slug returning a well-formed 200 choices envelope passes (returns the {role: slug} map),
    via the REAL leaf with a faked 200 transport (no network)."""
    import scripts.dr_benchmark.super_heavy_preflight as m
    import scripts.dr_benchmark.run_gate_b as rgb

    monkeypatch.setattr(rgb, "four_role_transport_mode", lambda: "openrouter")
    monkeypatch.setattr(
        rgb,
        "verifier_model_slugs",
        lambda: {"mirror": "z-ai/glm-5.1", "sentinel": "minimax/minimax-m2", "judge": "qwen/qwen3.6-35b-a3b"},
    )
    os.environ["OPENROUTER_API_KEY"] = "test-key"

    client = _mock_200_client()
    try:
        alive = m._default_verifier_slug_probe(http_client=client)
    finally:
        client.close()
    assert alive == {
        "mirror": "z-ai/glm-5.1",
        "sentinel": "minimax/minimax-m2",
        "judge": "qwen/qwen3.6-35b-a3b",
    }


# --------------------------------------------------------------------------- P1: probe MATCHES production
# These tests prove the I-cred-013 diff-gate P1 fix: the verifier-slug probe REUSES the production
# transports' OWN request construction, so it hits the SAME endpoint path, SAME auth presence/absence,
# and SAME body/provider/reasoning routing the production verifier call uses. The actual outgoing
# request is CAPTURED via a MockTransport handler (no network) and compared field-by-field against the
# production transport's request — NOT a blanket dict-equal (the probe legitimately clamps the token
# magnitudes), but field-scoped: endpoint, auth, model, provider, reasoning shape.
def _capturing_200_client(captured: dict):
    import httpx

    def _handler(request):
        captured["url"] = str(request.url)
        captured["headers"] = dict(request.headers)
        import json as _json

        captured["body"] = _json.loads(request.content.decode("utf-8"))
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}], "model": "probe"})

    return httpx.Client(transport=httpx.MockTransport(_handler))


def _production_openrouter_request(role: str, slug: str) -> tuple[str, dict, dict]:
    """Build the EXACT production OpenRouter verifier request (endpoint, headers, body) for `role` —
    the ground truth the probe must mirror on endpoint/auth/model/provider/reasoning."""
    from src.polaris_graph.roles.openai_compatible_transport import _normalize_messages
    from src.polaris_graph.roles.openrouter_role_transport import (
        _CHAT_COMPLETIONS_PATH,
        _build_openrouter_body,
        openrouter_role_endpoint,
    )
    from src.polaris_graph.roles.role_transport import RoleRequest

    base_url, api_key, model_slug = openrouter_role_endpoint(role)
    req = RoleRequest(role=role, model_slug=slug, prompt="ok", params={})
    body = _build_openrouter_body(req, model_slug, _normalize_messages(req))
    endpoint = f"{base_url}{_CHAT_COMPLETIONS_PATH}"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://polaris-research.ai",
        "X-Title": "polaris graph",
    }
    return endpoint, headers, body


@pytest.mark.parametrize("role", ["mirror", "sentinel", "judge"])
def test_openrouter_probe_request_matches_production(monkeypatch, role):
    """OpenRouter mode (P1-2): the probe's CAPTURED outgoing request must match the production verifier
    request on endpoint path, Authorization, model, AND the provider + reasoning ROUTING keys (the
    `require_parameters`-filtered keys whose absence was the P1-2 false-pass). Only the token MAGNITUDES
    differ (the probe clamps them cheap)."""
    import scripts.dr_benchmark.super_heavy_preflight as m
    import scripts.dr_benchmark.run_gate_b as rgb

    slugs = {"mirror": "z-ai/glm-5.1", "sentinel": "minimax/minimax-m2", "judge": "qwen/qwen3.6-35b-a3b"}
    slug = slugs[role]
    monkeypatch.setattr(rgb, "four_role_transport_mode", lambda: "openrouter")
    os.environ["OPENROUTER_API_KEY"] = "test-key"

    prod_endpoint, prod_headers, prod_body = _production_openrouter_request(role, slug)

    captured: dict = {}
    client = _capturing_200_client(captured)
    try:
        ok = m._real_chat_completion_alive(role, slug, http_client=client)
    finally:
        client.close()
    assert ok is True

    # endpoint path identical to production
    assert captured["url"] == prod_endpoint
    # Authorization present + identical (OpenRouter ALWAYS requires the key)
    assert captured["headers"].get("authorization") == prod_headers["Authorization"]
    assert "polaris-research.ai" in captured["headers"].get("http-referer", "")
    # model + temperature + provider routing + reasoning SHAPE identical to production
    body = captured["body"]
    assert body["model"] == prod_body["model"] == slug
    assert body["temperature"] == prod_body["temperature"]
    assert body["provider"] == prod_body["provider"], "provider routing must match production EXACTLY"
    # reasoning shape: same KEYS as production (Mirror numeric cap / Judge+Sentinel effort), magnitude
    # of a numeric reasoning cap clamped but still STRICTLY below top-level max_tokens (production rule).
    assert set(body.get("reasoning", {}).keys()) == set(prod_body.get("reasoning", {}).keys())
    if "effort" in prod_body.get("reasoning", {}):
        assert body["reasoning"]["effort"] == prod_body["reasoning"]["effort"]
    if "max_tokens" in body.get("reasoning", {}):
        assert body["max_tokens"] > body["reasoning"]["max_tokens"], "top max_tokens must exceed cap"
    # token budgets are CLAMPED cheap (not the production 16k/24k) — proves ~free without changing shape
    assert body["max_tokens"] < prod_body["max_tokens"]


@pytest.mark.parametrize(
    "role,base_env,key_env",
    [
        ("mirror", "PG_MIRROR_BASE_URL", "PG_MIRROR_API_KEY"),
        ("sentinel", "PG_SENTINEL_BASE_URL", "PG_SENTINEL_API_KEY"),
        ("judge", "PG_JUDGE_BASE_URL", "PG_JUDGE_API_KEY"),
    ],
)
def test_self_host_probe_request_matches_production_keyed(monkeypatch, role, base_env, key_env):
    """self_host mode (P1-1) with a per-role key SET: the probe must POST to the `/v1/chat/completions`
    path (NOT the `/chat/completions` the old probe hardcoded) and send `Authorization: Bearer <key>` —
    EXACTLY as OpenAICompatibleRoleTransport.complete does."""
    import scripts.dr_benchmark.super_heavy_preflight as m
    import scripts.dr_benchmark.run_gate_b as rgb

    monkeypatch.setattr(rgb, "four_role_transport_mode", lambda: "self_host")
    os.environ[base_env] = "http://10.0.0.9:8000"
    os.environ[key_env] = "sk-self-host"

    captured: dict = {}
    client = _capturing_200_client(captured)
    try:
        ok = m._real_chat_completion_alive(role, "whatever/slug", http_client=client)
    finally:
        client.close()
    assert ok is True
    # P1-1: production self-host path appends /v1/chat/completions (the constant), NOT /chat/completions
    assert captured["url"] == "http://10.0.0.9:8000/v1/chat/completions"
    assert captured["headers"].get("authorization") == "Bearer sk-self-host"
    # self-host vLLM bodies carry NO OpenRouter provider/reasoning routing
    assert "provider" not in captured["body"]
    assert "reasoning" not in captured["body"]


@pytest.mark.parametrize(
    "role,base_env,key_env",
    [
        ("mirror", "PG_MIRROR_BASE_URL", "PG_MIRROR_API_KEY"),
        ("sentinel", "PG_SENTINEL_BASE_URL", "PG_SENTINEL_API_KEY"),
    ],
)
def test_self_host_probe_omits_auth_when_keyless(monkeypatch, role, base_env, key_env):
    """self_host mode (P1-1, THE false-fail the old probe caused): a KEYLESS self-host vLLM (no
    PG_<ROLE>_API_KEY) is VALID — production omits the Authorization header entirely (never an empty
    `Bearer `). The old probe ALWAYS sent `Bearer <empty>`, false-FAILing a valid keyless deployment.
    The captured probe request must carry NO Authorization header."""
    import scripts.dr_benchmark.super_heavy_preflight as m
    import scripts.dr_benchmark.run_gate_b as rgb

    monkeypatch.setattr(rgb, "four_role_transport_mode", lambda: "self_host")
    os.environ[base_env] = "http://10.0.0.9:8000"
    os.environ.pop(key_env, None)  # KEYLESS — the valid vLLM-without-api-key deployment

    captured: dict = {}
    client = _capturing_200_client(captured)
    try:
        ok = m._real_chat_completion_alive(role, "whatever/slug", http_client=client)
    finally:
        client.close()
    assert ok is True
    assert captured["url"] == "http://10.0.0.9:8000/v1/chat/completions"
    # THE fix: no Authorization header at all (not an empty `Bearer `)
    assert "authorization" not in captured["headers"]


def test_self_host_probe_fails_closed_on_unset_base_url(monkeypatch):
    """self_host mode: an UNSET PG_<ROLE>_BASE_URL is a deployment error — role_endpoint raises, and the
    probe normalizes it to a fail-closed GateError BEFORE spend (never a silent default endpoint)."""
    import scripts.dr_benchmark.super_heavy_preflight as m
    import scripts.dr_benchmark.run_gate_b as rgb

    monkeypatch.setattr(rgb, "four_role_transport_mode", lambda: "self_host")
    monkeypatch.setattr(rgb, "verifier_model_slugs", lambda: {"mirror": "cohere/command-a-plus"})
    os.environ.pop("PG_MIRROR_BASE_URL", None)  # unset -> role_endpoint raises ValueError

    with pytest.raises(GateError, match=r"mirror.*NOT alive|BASE_URL|not set"):
        m._default_verifier_slug_probe(http_client=_mock_200_client())


def test_self_host_404_fails_closed(monkeypatch):
    """self_host mode: a dead self-host slug (404) still fails closed with a GateError (the same
    fail-closed contract as the openrouter route), via the production /v1/chat/completions call shape."""
    import scripts.dr_benchmark.super_heavy_preflight as m
    import scripts.dr_benchmark.run_gate_b as rgb

    monkeypatch.setattr(rgb, "four_role_transport_mode", lambda: "self_host")
    monkeypatch.setattr(rgb, "verifier_model_slugs", lambda: {"mirror": "cohere/command-a-plus"})
    os.environ["PG_MIRROR_BASE_URL"] = "http://10.0.0.9:8000"
    os.environ.pop("PG_MIRROR_API_KEY", None)

    client = _mock_404_client()
    try:
        with pytest.raises(GateError, match=r"mirror|NOT alive"):
            m._default_verifier_slug_probe(http_client=client)
    finally:
        client.close()


def test_probe_budget_clamp_preserves_invariant():
    """Unit: _clamp_probe_budget shrinks token magnitudes but PRESERVES the production invariant
    (top-level max_tokens > a numeric reasoning cap) and KEEPS the routing keys (provider/reasoning)."""
    import scripts.dr_benchmark.super_heavy_preflight as m

    # numeric reasoning cap (Mirror shape)
    body = {"reasoning": {"max_tokens": 4000}, "provider": {"order": ["x"]}, "max_tokens": 24000}
    out = m._clamp_probe_budget(body)
    assert out["max_tokens"] > out["reasoning"]["max_tokens"]
    assert out["max_tokens"] < 24000 and out["reasoning"]["max_tokens"] < 4000
    assert out["provider"] == {"order": ["x"]}  # routing untouched

    # effort reasoning (Judge/Sentinel shape) — effort kept, only top-level lowered
    body2 = {"reasoning": {"enabled": True, "effort": "xhigh"}, "max_tokens": 16384}
    out2 = m._clamp_probe_budget(body2)
    assert out2["reasoning"] == {"enabled": True, "effort": "xhigh"}
    assert out2["max_tokens"] < 16384
