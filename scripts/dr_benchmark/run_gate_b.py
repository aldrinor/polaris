"""Gate-B production caller — wires the native 4-role evaluation into the honest sweep.

I-meta-002 PR-9/M3b. This is WIRING ONLY: it constructs the verifier `RoleTransport` for the
three verifier roles (Mirror / Sentinel / Judge — the generator stays on OpenRouter, upstream
of this transport), sets `PG_FOUR_ROLE_MODE`, builds a no-argument CLOSURE over the native
input builder (`build_native_gate_b_inputs`) + the deterministic evidence normalization, and
hands the transport + builder into `run_one_query`.

TRANSPORT ROUTING (I-meta-007d, operator directive 2026-06-01): the verifier transport is
ENV-GATED via `PG_FOUR_ROLE_TRANSPORT`:
  - "openrouter" (DEFAULT at THIS dev/benchmark stage): all 3 verifier roles route via
    OpenRouter with MAX reasoning (`OpenRouterRoleTransport`). This avoids standing up the
    self-hosted vLLM GPU fleet just to run the benchmark — it saves the Vast.ai GPU rental
    cost. SOVEREIGNTY: OpenRouter is a US router; this is acceptable for dev/benchmark ONLY,
    NOT for the sovereign demo (feedback_sovereignty_threat_model). The lock is NOT mutated —
    it still pins `serving_route: vast_self_host*`, which remains the FINAL SOVEREIGN
    destination; only the runtime routing is overridden, and only at this stage.
  - "self_host": the original `OpenAICompatibleRoleTransport` POSTing per-role
    `PG_<ROLE>_BASE_URL` self-hosted vLLM endpoints — the lock's sovereign serving route.

CONTAMINATION-CRITICAL (§-1.1, operator-locked): every input is built ONLY from NATIVE
config — the scope template's `per_query_report_contract[<slug>].required_entities` and the
D8 release-policy config. This module NEVER reads anything under `outputs/dr_benchmark/`
(gold rubric / freeze pin / competitor answers).

NO SPEND / NO NETWORK at import. The transport's `httpx.Client` is created INSIDE
`build_gate_b_transport` (not at module level), so importing this module never opens a client
or touches a socket. The Gate-B LIVE run (real endpoints + real spend) is the later
operator-authorized canary; this module is exercised offline by the seam test with a FAKE
transport injected in place of `build_gate_b_transport`'s output.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Callable, Mapping

import httpx

from scripts.architecture.verify_lock import load_lock
from src.polaris_graph.roles.native_gate_b_inputs import (
    NativeGateBBundle,
    build_native_gate_b_inputs,
    normalize_evidence_pool_lookup,
)
from src.polaris_graph.roles.openai_compatible_transport import (
    OpenAICompatibleRoleTransport,
)
from src.polaris_graph.roles.openrouter_role_transport import (
    FOUR_ROLE_STAGE,
    OpenRouterRoleTransport,
    benchmark_verifier_family,
    benchmark_verifier_lineup,
    openrouter_base_url,
    role_reasoning_enabled,
)
from src.polaris_graph.roles.release_policy import load_d8_policy_config

# The three verifier roles this caller serves (the generator is excluded — it runs live on
# OpenRouter, upstream of the per-claim verifier transport).
_VERIFIER_ROLES = ("mirror", "sentinel", "judge")

# Env flag the guarded sweep branch reads to activate the 4-role seam.
_FOUR_ROLE_MODE_ENV = "PG_FOUR_ROLE_MODE"

# I-meta-007d: which verifier transport to build (LAW VI env-gate). DEFAULT "openrouter" at the
# CURRENT dev/benchmark stage (saves GPU cost). "self_host" selects the lock's sovereign route.
_FOUR_ROLE_TRANSPORT_ENV = "PG_FOUR_ROLE_TRANSPORT"
_TRANSPORT_OPENROUTER = "openrouter"
_TRANSPORT_SELF_HOST = "self_host"
_FOUR_ROLE_TRANSPORT_DEFAULT = _TRANSPORT_OPENROUTER

# OpenRouter catalog endpoint (GET) for the benchmark-stage slug-resolution preflight.
_OPENROUTER_MODELS_PATH = "/models"

# httpx client timeout knob (LAW VI): same env var + fallback the transport uses.
_TIMEOUT_SECONDS = int(os.getenv("PG_LLM_TIMEOUT_SECONDS", "90"))


def four_role_transport_mode() -> str:
    """Resolve `PG_FOUR_ROLE_TRANSPORT` (I-meta-007d). DEFAULT "openrouter" at the dev/benchmark
    stage (saves GPU cost; OpenRouter is a US router — dev/benchmark ONLY, never the sovereign
    demo). "self_host" selects the lock's `vast_self_host*` route. Fails loud on an unknown value
    so a typo never silently picks the wrong (spend) route.
    """
    mode = os.getenv(_FOUR_ROLE_TRANSPORT_ENV, _FOUR_ROLE_TRANSPORT_DEFAULT).strip().lower()
    if mode not in (_TRANSPORT_OPENROUTER, _TRANSPORT_SELF_HOST):
        raise ValueError(
            f"{_FOUR_ROLE_TRANSPORT_ENV}={mode!r} is invalid; expected "
            f"{_TRANSPORT_OPENROUTER!r} (benchmark-stage OpenRouter, default) or "
            f"{_TRANSPORT_SELF_HOST!r} (lock sovereign self-host route)."
        )
    return mode


def build_gate_b_transport(
    http_client: httpx.Client | None = None,
) -> OpenRouterRoleTransport | OpenAICompatibleRoleTransport:
    """Construct the verifier transport (one shared sync `httpx.Client`), ENV-GATED per
    `PG_FOUR_ROLE_TRANSPORT` (I-meta-007d).

    Built INSIDE this function (never at module level) so importing `run_gate_b` opens no
    client and touches no socket.

    - "openrouter" (DEFAULT, dev/benchmark stage — saves GPU cost): returns an
      `OpenRouterRoleTransport` that, when invoked, POSTs `/chat/completions` to OpenRouter with
      each role's lock-pinned slug AND MAX reasoning. SOVEREIGNTY: OpenRouter is a US router —
      acceptable for dev/benchmark ONLY; the lock's `vast_self_host*` self-host route remains
      the FINAL SOVEREIGN destination (the lock is NOT mutated).
    - "self_host": returns the original `OpenAICompatibleRoleTransport` (per-role
      `PG_<ROLE>_BASE_URL` self-hosted vLLM) — the lock's sovereign serving route.

    `http_client` (P2): the live caller passes nothing, so a real `httpx.Client` is built here;
    tests inject a `MockTransport`-backed client so transport-selection is exercised with no live
    client and no socket. Resolved ONCE and handed to whichever transport is selected.

    The live invocation is the later operator-authorized Gate-B canary, never a test.
    """
    client = http_client if http_client is not None else httpx.Client(timeout=_TIMEOUT_SECONDS)
    if four_role_transport_mode() == _TRANSPORT_OPENROUTER:
        return OpenRouterRoleTransport(client)
    return OpenAICompatibleRoleTransport(client)


def verifier_model_slugs() -> dict[str, str]:
    """Return the pinned `{mirror,sentinel,judge: model_slug}` map for the ACTIVE transport mode.

    MODE-AWARE (I-meta-007d P1-1) so served == pinned on whichever route is active:
      - "openrouter" (benchmark, DEFAULT): the BENCHMARK lineup
        (`benchmark_verifier_lineup` — the operator-chosen OpenRouter slugs in
        role_selection_final.md: Mirror `z-ai/glm-5.1`, Sentinel `ibm-granite/granite-4.1-8b`,
        Judge `qwen/qwen3.6-35b-a3b`). The transport POSTs these exact slugs as `body["model"]`,
        so the pin the builder threads into `RoleRequest.model_slug` matches the served slug.
      - "self_host": the lock's self-host `model_slug`s (Mirror `cohere/command-a-plus`,
        Sentinel the granite-GUARDIAN, Judge `qwen/qwen3.6-35b-a3b`) — the sovereign serving
        route, served by `OpenAICompatibleRoleTransport` against `PG_<ROLE>_BASE_URL`.

    The single machine-readable source of truth per mode (LAW VI). The generator slug is
    intentionally excluded — it is not a per-claim verifier role.
    """
    if four_role_transport_mode() == _TRANSPORT_OPENROUTER:
        return benchmark_verifier_lineup()
    lock = load_lock()
    return {role: lock["required_roles"][role]["model_slug"] for role in _VERIFIER_ROLES}


def make_gate_b_input_builder(
    *,
    d8_config_path: str | Path | None = None,
) -> Callable[..., NativeGateBBundle]:
    """Return the Gate-B builder CLOSURE — a factory over RESOLUTION POLICY only.

    The closure captures ONLY the resolution policy (the optional `d8_config_path` + the
    normalization fn + the lock-slug source) — NOT the run-local report objects, which do not
    exist when the caller constructs the builder (they are produced inside `run_one_query` after
    generation). The SEAM calls the closure AFTER generation, passing the run-local objects
    (`multi`, `template`, `slug`, `domain`, `ev_pool`) as keyword args. The closure then OWNS
    resolution: it normalizes the run's raw `ev_pool` into the builder's
    `{evidence_id: {text, doi?, pmid?, url?}}` record contract (deterministic, no network — keys
    preserve the ProvenanceToken.evidence_id space), loads the D8 policy config, sources the
    pinned verifier slugs from the lock, and calls the native `build_native_gate_b_inputs`.
    NATIVE-ONLY: nothing here reads the gold rubric.
    """

    def _builder(
        *,
        multi: Any,
        template: dict,
        slug: str,
        domain: str,
        ev_pool: Mapping[str, Mapping[str, Any]],
    ) -> NativeGateBBundle:
        evidence_lookup = normalize_evidence_pool_lookup(ev_pool)
        d8_config = load_d8_policy_config(d8_config_path)
        model_slugs = verifier_model_slugs()
        return build_native_gate_b_inputs(
            multi=multi,
            template=template,
            slug=slug,
            domain=domain,
            evidence_lookup=evidence_lookup,
            model_slugs=model_slugs,
            d8_config=d8_config,
        )

    return _builder


def enable_four_role_mode() -> None:
    """Set `PG_FOUR_ROLE_MODE=1` in the process env so the guarded sweep branch activates.

    Wiring helper (LAW VI: env-driven activation). The Gate-B live run sets this before
    invoking the sweep; the offline seam test sets it via monkeypatch instead.
    """
    os.environ[_FOUR_ROLE_MODE_ENV] = "1"


def assert_four_role_families_distinct() -> dict[str, str]:
    """Assert the 4 roles (generator + the 3 verifiers) are all DISTINCT lineages for the
    ACTIVE transport mode (the N-way two-family invariant, CLAUDE.md §9.1 / family_policy:
    all_distinct). Fails LOUD (I-meta-007) — a collision would let one family self-verify.
    Returns the `{role: family}` map for telemetry.

    MODE-AWARE (I-meta-007d P1-1): the family check must run over the families ACTUALLY served:
      - "openrouter" (benchmark, DEFAULT): generator family from the lock (`deepseek` — the
        generator is unchanged + runs upstream on OpenRouter) UNION the 3 BENCHMARK verifier
        families (`benchmark_verifier_family`: Mirror `z-ai`, Sentinel `ibm-granite`, Judge
        `qwen`). These four — deepseek / z-ai / ibm-granite / qwen — are distinct. (Checking the
        LOCK's verifier families here would assert on `cohere`/`ibm-granite`/`qwen`, which are NOT
        the families served on this route.)
      - "self_host": the lock's families for all 4 roles (the sovereign route).
    """
    lock = load_lock()
    if four_role_transport_mode() == _TRANSPORT_OPENROUTER:
        fams = {"generator": str(lock["required_roles"]["generator"]["family"])}
        for role in _VERIFIER_ROLES:
            fams[role] = benchmark_verifier_family(role)
    else:
        roles = ("generator", *_VERIFIER_ROLES)
        fams = {r: str(lock["required_roles"][r]["family"]) for r in roles}
    if len(set(fams.values())) != len(fams):
        raise RuntimeError(
            "Gate-B preflight: 4-role family collision — all roles must be distinct "
            f"lineages for the active transport mode, got {fams}"
        )
    return fams


def preflight_self_host_roles() -> dict[str, str]:
    """LIVE-run preflight (self_host mode): resolve each self-hosted verifier endpoint up front
    so a missing `PG_<ROLE>_BASE_URL` fails BEFORE the sweep starts (not mid-run on the
    first claim's Mirror call), AND assert the 4 families are distinct. Returns the
    `{role: base_url}` map. ONLY called when building the real transport (skipped
    when a fake transport is injected for offline tests). I-meta-007.
    """
    from src.polaris_graph.roles.openai_compatible_transport import role_endpoint

    assert_four_role_families_distinct()
    endpoints: dict[str, str] = {}
    for role in _VERIFIER_ROLES:
        base_url, _api_key, _slug = role_endpoint(role)  # raises LOUD if unset
        endpoints[role] = base_url
    return endpoints


def _fetch_openrouter_catalog(http_client: httpx.Client | None = None) -> list[dict]:
    """Fetch the OpenRouter model catalog (`GET {base}/models`) and return its `data` list.

    The `http_client` is INJECTABLE so the preflight test feeds a faked catalog via
    `httpx.MockTransport` (no real network, no spend). When None, a real sync client is created
    against `OPENROUTER_BASE_URL` (LAW VI) — that path only runs on a live, operator-authorized
    benchmark run. Fails loud (LAW II) on a non-200 status or a body without a `data` list.
    """
    url = f"{openrouter_base_url()}{_OPENROUTER_MODELS_PATH}"
    own_client = http_client is None
    client = http_client or httpx.Client(timeout=_TIMEOUT_SECONDS)
    try:
        response = client.get(url, timeout=_TIMEOUT_SECONDS)
    finally:
        if own_client:
            client.close()
    if response.status_code != httpx.codes.OK:
        raise RuntimeError(
            f"OpenRouter catalog preflight: GET {url} returned HTTP {response.status_code}"
        )
    body = response.json()
    data = body.get("data")
    if not isinstance(data, list):
        raise RuntimeError(
            f"OpenRouter catalog preflight: GET {url} body has no `data` list (got "
            f"{type(data).__name__})"
        )
    return data


def preflight_openrouter_roles(http_client: httpx.Client | None = None) -> dict[str, str]:
    """LIVE-run preflight (openrouter mode, I-meta-007d): resolve each verifier role's BENCHMARK
    lineup slug against OpenRouter's catalog so a non-resolving slug fails BEFORE the sweep spends
    a token, AND assert the 4 families are distinct.

    Resolves each role's BENCHMARK slug (`benchmark_verifier_lineup` — the operator-chosen
    OpenRouter slugs in role_selection_final.md: Mirror `z-ai/glm-5.1`, Sentinel
    `ibm-granite/granite-4.1-8b`, Judge `qwen/qwen3.6-35b-a3b`; P1-1) — NOT the lock's self-host
    slugs (Cohere's Mirror + the granite-GUARDIAN Sentinel are not on OpenRouter). The same lineup
    the transport POSTs, so a slug that resolves here is the slug that gets served. Each is
    asserted present in the OpenRouter catalog as either an entry `id` OR its `canonical_slug`
    (OpenRouter exposes both; a slug may match either). Returns the `{role: benchmark_slug}` map.
    The `http_client` is INJECTABLE so the test feeds a faked catalog (no network). ONLY called
    when building the real transport (skipped when a fake transport is injected for offline tests).

    Fails LOUD (LAW II) on a missing slug or a family collision — never a silent skip.
    """
    assert_four_role_families_distinct()
    catalog = _fetch_openrouter_catalog(http_client)
    # Map EVERY catalog alias (entry `id` AND `canonical_slug`) -> that entry's
    # `supported_parameters` list. `setdefault` so the first occurrence of an alias wins (a later
    # duplicate id never clobbers it). A missing or non-list `supported_parameters` becomes `[]`,
    # which the executability check below reads as "advertises no reasoning".
    slug_params: dict[str, list] = {}
    for entry in catalog:
        if not isinstance(entry, dict):
            continue
        params = entry.get("supported_parameters")
        if not isinstance(params, list):
            params = []
        for key in ("id", "canonical_slug"):
            value = entry.get(key)
            if value:
                slug_params.setdefault(value, params)

    resolved: dict[str, str] = {}
    lineup = benchmark_verifier_lineup()
    for role in _VERIFIER_ROLES:
        slug = lineup[role]
        if slug not in slug_params:
            raise RuntimeError(
                f"OpenRouter catalog preflight: role {role!r} benchmark slug {slug!r} is NOT in "
                f"the OpenRouter catalog (neither as an entry `id` nor `canonical_slug`). The "
                "benchmark-stage OpenRouter route cannot serve it — fix the benchmark lineup "
                f"(PG_{role.upper()}_MODEL / role_selection_final.md) or select "
                f"{_FOUR_ROLE_TRANSPORT_ENV}={_TRANSPORT_SELF_HOST}."
            )
        # Executability check (Codex iter-2 P1): a reasoning-enabled role sends MAX reasoning with
        # `provider.require_parameters=True`. If its benchmark slug does NOT advertise `reasoning`
        # in OpenRouter `supported_parameters`, OpenRouter refuses to route (no provider honors the
        # param) and the FIRST call fails. Catch it here, before any token is spent.
        if role_reasoning_enabled(role) and "reasoning" not in slug_params[slug]:
            raise RuntimeError(
                f"OpenRouter catalog preflight: role {role!r} is reasoning-enabled (sends MAX "
                f"reasoning + provider.require_parameters=True), but its benchmark slug {slug!r} "
                f"does NOT advertise `reasoning` in OpenRouter `supported_parameters` (advertised: "
                f"{slug_params[slug]!r}); with require_parameters=True OpenRouter would fail routing "
                f"at the first {role!r} call. Fix the benchmark lineup (PG_{role.upper()}_MODEL) to "
                f"a reasoning-capable slug, disable reasoning for this role "
                f"(PG_{role.upper()}_REASONING=0), or select "
                f"{_FOUR_ROLE_TRANSPORT_ENV}={_TRANSPORT_SELF_HOST}."
            )
        resolved[role] = slug
    return resolved


def preflight_four_role_transport() -> dict[str, str]:
    """LIVE-run preflight dispatcher (I-meta-007d): run the preflight matching the ENV-gated
    transport mode. openrouter -> resolve slugs against the OpenRouter catalog; self_host ->
    resolve each `PG_<ROLE>_BASE_URL`. Both assert the 4-distinct-family invariant. Returns the
    mode's `{role: resolved}` map.
    """
    if four_role_transport_mode() == _TRANSPORT_OPENROUTER:
        return preflight_openrouter_roles()
    return preflight_self_host_roles()


# Filename of the machine-readable stage marker written next to a Gate-B run (P2, I-meta-007d
# diff-gate iter-1). A future gate/manifest reader checks `stage` to tell a benchmark OpenRouter
# run apart from the sovereign self-host serving path.
FOUR_ROLE_STAGE_MARKER_FILENAME = "four_role_stage.json"


def four_role_stage_marker() -> dict[str, object]:
    """Build the machine-readable stage marker for the ACTIVE transport mode (P2).

    For the OpenRouter benchmark route the `stage` is `FOUR_ROLE_STAGE` ("benchmark_openrouter")
    and the marker records the active verifier lineup slugs/families so a future gate can never
    mistake an OpenRouter benchmark run for the sovereign self-host serving path (the lock's
    `serving_route: vast_self_host*`). For the self_host route the `stage` is "sovereign_self_host".
    """
    mode = four_role_transport_mode()
    if mode == _TRANSPORT_OPENROUTER:
        return {
            "stage": FOUR_ROLE_STAGE,
            "transport_mode": mode,
            "verifier_lineup": benchmark_verifier_lineup(),
            "verifier_families": {r: benchmark_verifier_family(r) for r in _VERIFIER_ROLES},
            "note": (
                "benchmark-stage OpenRouter route (US router; dev/benchmark ONLY). The lock's "
                "self-host slugs (cohere Mirror, granite-GUARDIAN Sentinel) remain the SOVEREIGN "
                "destination — see role_selection_final.md + openrouter_role_transport docstring."
            ),
        }
    return {
        "stage": "sovereign_self_host",
        "transport_mode": mode,
        "verifier_lineup": verifier_model_slugs(),
    }


def write_four_role_stage_marker(out_root: Path) -> Path:
    """Persist the stage marker (P2) under `out_root`; return the written path.

    Idempotent file write (no network, no spend). Called from the Gate-B production entrypoint so
    every benchmark run records its stage. Skipped in offline tests that inject a fake transport
    and call the seam directly (this lives on the live `run_gate_b_query` path).
    """
    out_root.mkdir(parents=True, exist_ok=True)
    marker_path = out_root / FOUR_ROLE_STAGE_MARKER_FILENAME
    marker_path.write_text(
        json.dumps(four_role_stage_marker(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return marker_path


async def run_gate_b_query(
    q: dict,
    out_root: Path,
    *,
    transport: OpenRouterRoleTransport | OpenAICompatibleRoleTransport | None = None,
    d8_config_path: str | Path | None = None,
) -> dict:
    """Run ONE query through the honest sweep with the native 4-role Gate-B seam ACTIVE.

    WIRING ONLY (LAW VII CLI isolation): activates `PG_FOUR_ROLE_MODE`, builds the verifier
    `transport` (unless one is injected — the offline seam test injects a FAKE), builds the
    argument-taking Gate-B builder closure, and hands transport + builder into `run_one_query`.
    The seam calls the builder AFTER generation with the run-local objects.

    Transport routing is ENV-gated (`PG_FOUR_ROLE_TRANSPORT`, I-meta-007d): "openrouter"
    (DEFAULT, dev/benchmark — saves GPU cost; OpenRouter is a US router, dev/benchmark ONLY) or
    "self_host" (the lock's sovereign route). The LIVE preflight matches the mode
    (`preflight_four_role_transport`).

    This function is the Gate-B production entrypoint; its LIVE invocation (real endpoints + real
    spend) is the later operator-authorized canary. It is NEVER invoked against a live endpoint by
    any test — the seam test exercises `run_four_role_seam` with a fake transport directly.
    Imported lazily so this module's import never pulls the big sweep file.
    """
    from scripts.run_honest_sweep_r3 import run_one_query

    enable_four_role_mode()
    # I-meta-007: enable the verifiable quantified-trade-off calculator for the
    # benchmark/paid run ONLY here (gate-B entry), never globally — so the Phase-7
    # Regime-C-verified quantified section actually fires on the paid run.
    os.environ["PG_ENABLE_QUANTIFIED_ANALYSIS"] = "1"
    if transport is not None:
        active_transport = transport               # offline/test: injected fake
    else:
        # LIVE run: fail-fast (BEFORE the sweep spends a token) if the ENV-gated transport
        # cannot resolve — openrouter: a pinned slug missing from the catalog; self_host: a
        # missing PG_<ROLE>_BASE_URL; either: a 4-role family collision.
        preflight_four_role_transport()
        active_transport = build_gate_b_transport()
        # P2 (I-meta-007d): record the machine-readable stage marker so a future gate/manifest
        # reader can tell this benchmark OpenRouter run apart from the sovereign self-host path.
        write_four_role_stage_marker(out_root)
    builder = make_gate_b_input_builder(d8_config_path=d8_config_path)
    return await run_one_query(
        q,
        out_root,
        four_role_transport=active_transport,
        four_role_input_builder=builder,
    )
