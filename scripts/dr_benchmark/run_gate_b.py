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

# I-ready-018 (#1138, Codex iter-1 P1-1): install the import-root alias BEFORE any repo import. The
# beat-both run launches from repo-root WITHOUT PYTHONPATH=src, so src/sitecustomize.py does NOT
# auto-load here. The core run path is src.-consistent (unaffected), but the --upload-file path imports
# polaris_v6 internals via the BARE root, which would ModuleNotFoundError root-only. Installing the
# alias here makes any bare polaris_graph/polaris_v6 import resolve to its src. counterpart. Idempotent
# + a no-op when the alias is already installed (sitecustomize) or the canonical tree is absent.
from src._polaris_import_alias import install_import_root_alias

install_import_root_alias()


def enable_faulthandler() -> None:
    """GH #1260: dump a C+Python stack on the NEXT native crash instead of dying
    silently. A libxml2 SIGSEGV in any worker thread kills the process with no
    traceback; `faulthandler` installs a signal handler that prints the faulting
    stack (all threads) so the next crash is diagnosable rather than a mystery.

    Honors `PYTHONFAULTHANDLER` (already enabled by the interpreter then) and is
    idempotent — calling `faulthandler.enable` twice is safe."""
    import faulthandler

    try:
        faulthandler.enable(all_threads=True)
    except (RuntimeError, ValueError, OSError):
        # stderr redirected to a non-fileno stream (e.g. captured under a test
        # harness) — best-effort; never block the run on diagnostics setup.
        pass

from scripts.architecture.verify_lock import load_lock
# I-ready-017 FIX-JO (#1100): the canonical journal_only runtime-flag NAME. Imported (not
# re-hardcoded) so the per-slug activation below sets the SAME env the consumer reads in
# run_honest_sweep_r3.run_one_query -> journal_only_active (single source of truth, LAW VI).
# journal_only_filter imports only stdlib (os/dataclasses/urllib) — NO network/spend at import.
from src.polaris_graph.nodes.journal_only_filter import JOURNAL_ONLY_FLAG
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

# httpx client timeout knob (LAW VI). I-meta-008 FULL-POWER: use the generous verifier timeout
# (default 900s) so the client default never undercuts the reasoning verifiers' per-request budget.
_TIMEOUT_SECONDS = int(os.getenv("PG_VERIFIER_LLM_TIMEOUT_SECONDS", "900"))


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


# I-cap-005 (#1068): the FULL-CAPABILITY benchmark env slate, applied by Gate-B itself so a run is at
# full depth REGARDLESS of the operator's shell env (the prior throttle was caused by setting the DEAD
# `PG_LIVE_*` names instead of the real `PG_SWEEP_*` knobs, + STORM/tracker never enabled). Every value
# is `setdefault` so an explicit operator override still wins (LAW VI). The slate is applied BEFORE the
# sweep is imported so import-time module constants (caps/timeouts) also see the full values.
_FULL_CAPABILITY_BENCHMARK_SLATE: dict[str, str] = {
    # I-fetch-002 (#1168): the WHOLE run fetches ~1000 sites TOTAL per question, NOT 1000 + additive
    # lanes. The operator's ~1000 budget is SPLIT across the four real fetch lanes so they SUM to ~1000
    # (the prior 1000 here was the MAIN lane alone, on top of which agentic/deepener/R-6 each added more
    # — silently overshooting the budget). The four lanes, FLOOR-applied below (max(existing, slate)):
    #   PG_SWEEP_FETCH_CAP            740  main Serper/S2/OpenAlex lane (total URLs after dedup, /query)
    #   PG_AGENTIC_BENCHMARK_URL_CAP  100  agentic-discovery harvest (run_honest_sweep_r3.py:3162)
    #   PG_SWEEP_DEEPENER_URL_CAP      60  citation-snowball deepener (run_honest_sweep_r3.py:3038)
    #   PG_R6_EXPAND_FETCH_CAP         40  R-6 completeness re-expansion (run_honest_sweep_r3.py:2961)
    #   PG_STORM_URL_FETCH_CAP         60  STORM web-results seed lane (I-beatboth-fix-000 BB-006)
    #   --------------------------------------------------------------------------------------------
    #   SUM                          1000  ≈ the ~1000-site/question budget (operator no-overshoot).
    #   I-beatboth-fix-000 (Codex P1): main lane trimmed 800->740 to ABSORB the new STORM seed lane so
    #   the total fetch stays at the hard 1000 envelope (no ~1060 overshoot).
    # NOTE: PG_STORM_MAX_BENCHMARK_QUERIES (30) and PG_MAX_SUBQUERIES (15) below are QUERY-BREADTH
    # counts (how many search queries are issued), NOT URLs — they are deliberately NOT part of the
    # ~1000-URL sum. .env has no override for any of these (checked I-fetch-002), so the floor lands.
    # Retrieval breadth — the REAL run_one_query knobs (PG_SWEEP_*, default 12/12/40). NOT PG_LIVE_*.
    "PG_SWEEP_FETCH_CAP": "740",   # MAIN lane: total URLs/query (lane 1/4); 800->740 to absorb STORM seed lane (1000 total)
    "PG_SWEEP_MAX_SERPER": "100",
    "PG_SWEEP_MAX_S2": "100",
    # FX-17 (#1126): Serper `num` is a PAGE size (max ~20); breadth needs the new PAGINATION budget.
    # Without these the benchmark stays single-page (~20/query) despite MAX_SERPER=100. 60 over <=3
    # pages = up to 3 Serper pages/query.
    "PG_SERPER_TOTAL_PER_QUERY": "60",
    "PG_SERPER_MAX_PAGES": "3",
    # Feature activation that Gate-B previously MISSED (STORM was dead-by-config; deepener off).
    "PG_STORM_ENABLED_IN_BENCHMARK": "1",
    "PG_SWEEP_EVIDENCE_DEEPENER": "1",
    # Observability — MUST be on so each feature's firing is provable in manifest['tool_utilization'].
    "PG_ENABLE_TOOL_TRACKER": "1",
    # Import-time caps/timeouts (read at module load — applied before the sweep import below).
    "PG_LIVE_CONTENT_MAX": "50000",
    "PG_LIVE_HTTP_TIMEOUT": "30",
    "PG_LIVE_RETRIEVER_MAX_WORKERS": "16",
    # F01/F16 (A3): the global LLM concurrency cap. llm_provider.get_semaphore() reads this at
    # CALL time (per-loop rebind), so the slate value lands without an import-time freeze. FLOOR
    # semantics (max(existing, 5)): an operator may RAISE it but never silently drop below the
    # safe default of 5 (cloud rate-limit / GPU-OOM guard). NOT part of the ~1000-URL fetch sum —
    # it caps concurrent LLM calls, not URLs.
    "PG_MAX_CONCURRENT_LLM": "5",
    # I-ready-003 (#1074) P1: scale the post-fetch loop budget to the ~1000-URL cap. The live_retriever
    # now takes max(this, fetch_cap * PG_POST_FETCH_PER_URL_BUDGET) so the loop never silently truncates
    # the corpus mid-classification. 1000 URLs * 4s = 4000s.
    "PG_POST_FETCH_LOOP_BUDGET": "4000",
    "PG_POST_FETCH_PER_URL_BUDGET": "4",
    "PG_LLM_TIMEOUT_SECONDS": "180",
    # I-arch-004 A2 (#1248): section generation timeout + token budget, sized off the REAL 64000-token
    # section budget at the slow-band rate observed in the drb_72 run data (~15 tok/s for big sections).
    # These were ABSENT from the slate, so a real Gate-B run got the stale module defaults (section
    # wall-clock OFF -> hang-forever risk; generator timeout 1800s sized for the old 16384 ceiling). The
    # drb_72 death was the SMOKE wall-clock (600s) killing the V30 section mid-stream x2. FLOOR semantics
    # (max(existing, slate)): an operator may raise these but never lower below the legit floor.
    "PG_SECTION_MAX_TOKENS": "64000",            # generator chain serves >=384000 (I-arch-003 pin); 64000 = ~4x observed max
    "PG_GENERATOR_LLM_TIMEOUT_SECONDS": "6500",  # 1.5 x (64000 / 15 tok/s) ~= 6500s inner LLM timeout
    "PG_SECTION_WALLCLOCK_SECONDS": "9000",      # outer per-attempt section backstop (LLM 6500 + verify/rewrite headroom)
    # I-arch-005 B20 PREFLIGHT FIX (#1257): the RUN-LEVEL wall-clock backstop. The pre-run dual-audit
    # found the paid Gate-B path (run_gate_b_query) NEVER wrapped run_one_query in asyncio.wait_for, so a
    # HANG anywhere inside = PERMANENT silence (run_one_query's inner B11 finally cannot fire on a hang) —
    # the drb_76 3.5h hang. The default run_wall_clock_seconds (7200) is also BELOW the 9000 section
    # backstop = inverted ordering. Set the run-wall ABOVE the section backstop so the hierarchy is
    # per-call 6500 < section 9000 < run-wall 10800, and run_gate_b_query now wraps run_one_query in
    # wait_for(run_wall) + the B11 timeout-finalizer. KEEP gen 6500 / section 9000 (correctly sized for a
    # 64000-token worst-case section at ~15 tok/s = ~4267s; B24's 600/1800 MODULE defaults would TRUNCATE
    # real sections per the #1248 forensic + the real 86-min run, so the slate KEEPS the large per-call
    # values and fixes ONLY the missing run-level guard + the inverted run-wall ordering). A legit single-
    # query run is ~86 min, so 10800 (3h) clears it with margin yet still catches a total hang.
    "PG_RUN_WALL_CLOCK_SEC": "10800",
    # Evidence-extraction depth.
    "PG_MAX_EVIDENCE_TO_EXTRACT": "1500",
    "PG_DEEPENER_EVIDENCE_CAP": "500",
    "PG_MOST_MAX_EVIDENCE": "800",
    # I-ready-001 (#1070) P0: the GENERATOR-FACING pool cap. The I-cap-005 slate raised RETRIEVAL breadth
    # to ~1000 URLs but left PG_LIVE_MAX_EV_TO_GEN at its code default 20 (run_honest_sweep_r3.py:4524) —
    # so generation saw 20 of 1000+ rows (98% silently dropped), the same silent-throttle class as
    # I-cap-005 one stage downstream. The interim raise to 150 still dropped ~90% of a 1500-row pool.
    # OPERATOR DECISION 2026-06-10: this is the GLOBAL POOL the sections draw from, NOT a per-prompt size
    # — each section independently selects its own relevant rows (capped by PG_MAX_EV_PER_SECTION below),
    # so a global pool cap only STARVES niche sections of evidence ranked below the cut. There is no
    # provider/transport reason for it: the generator (deepseek-v4-pro) is a 1M-context model and a single
    # section prompt carries only PG_MAX_EV_PER_SECTION rows. So the pool cap is set to the FULL extracted
    # set (= PG_MAX_EVIDENCE_TO_EXTRACT) — no pre-section throttle; nothing is dropped before the sections
    # pick. This does NOT enlarge any single LLM prompt (no lost-in-the-middle risk); it only lets each
    # section choose its best rows from the full universe. FLOOR semantics (max(existing, 1500)).
    #
    # I-arch-005 B2/B3 (#1257): the per-section ROW cap is now DISSOLVED into a character
    # budget by DEFAULT (multi_section_generator `_section_budgets_enabled()`), so
    # PG_MAX_EV_PER_SECTION is INERT on the default path — each section keeps every assigned
    # row whose serialized text fits the generous PG_SECTION_EV_CHAR_BUDGET (~120K chars),
    # never a row count. The 40 is left here only as a no-op floor for the escape-hatch
    # PG_GEN_ROW_CAPS path (which the preflight FAILS on for a cert run). Historical origin:
    # the M-24 OpenRouter >100K-token-body 400 guard (multi_section_generator.py), STALE for
    # the 200K-1M-context current stack — exactly why the row cap is now a char budget.
    "PG_LIVE_MAX_EV_TO_GEN": "1500",
    "PG_MAX_EV_PER_SECTION": "40",
    # R-6 completeness-expansion breadth (the secondary throttle that was hardcoded 5/5/15/cap-4).
    "PG_R6_EXPAND_QUERY_CAP": "12",
    "PG_R6_EXPAND_MAX_SERPER": "20",
    "PG_R6_EXPAND_MAX_S2": "20",
    # I-fetch-002 (#1168): budget lane 4/4 — R-6 completeness re-expansion fetch cap. Lowered 60->40 so
    # the four fetch lanes SUM to ~1000 (read at run_honest_sweep_r3.py:2961, code default 15).
    "PG_R6_EXPAND_FETCH_CAP": "40",
    # I-fetch-002 (#1168): budget lane 2/4 — agentic-discovery URL harvest cap (read at
    # run_honest_sweep_r3.py:3162, code default 100). Explicit in the slate so it cannot silently drift.
    "PG_AGENTIC_BENCHMARK_URL_CAP": "100",
    # I-fetch-002 (#1168): budget lane 3/4 — citation-snowball deepener URL cap. Previously an UNGUARDED
    # default of 20 (run_honest_sweep_r3.py:3038); pin it to 60 so the lane is part of the ~1000 budget
    # and cannot silently drift below it.
    "PG_SWEEP_DEEPENER_URL_CAP": "60",
    # I-fetch-002 (#1168): two un-guarded QUERY-BREADTH knobs, pinned explicitly so they cannot silently
    # drift (NOT part of the ~1000-URL sum — these count search queries, not URLs). STORM benchmark-query
    # cap (read at run_honest_sweep_r3.py:2626) + sub-query decomposition cap (query_decomposer.py:39).
    # Both floor-guarded in _BENCHMARK_PREFLIGHT_FLOORS below.
    "PG_STORM_MAX_BENCHMARK_QUERIES": "30",
    "PG_MAX_SUBQUERIES": "15",
    # Agentic per-round web breadth (was stuck at 6 via the PG_WEB_PER_ROUND typo).
    "PG_AGENTIC_WEB_PER_ROUND": "10",
    # Budget cap (spend ceiling enforced per run).
    "PG_MAX_COST_PER_RUN": "25",
    # I-ready-002 (#1071) P0: BINDING faithfulness verifier. The entailment judge runs as a binding DROP
    # gate AND (Codex iter-1 fix) fails closed on a judge_error (the judge's fail-open "ENTAILED",
    # "judge_error:..." sentinel) when PG_STRICT_VERIFY_ENTAILMENT=enforce. Force it on so the benchmark's
    # binding gate enforces entailment + fails closed on error (STRENGTHENS faithfulness, never weakens).
    # NOTE (Codex iter-1 P1): we deliberately do NOT force PG_VERIFICATION_MODE=enforce — that ALSO enables
    # the Phase 0b RESCUE deltas (a separate faithfulness-WIDENING feature that passes some previously-
    # dropped claims), which is not in this benchmark's scope. judge_error fail-closed is now keyed on the
    # entailment mode (provenance_generator.py), independent of the rescue switch.
    "PG_STRICT_VERIFY_ENTAILMENT": "enforce",
    # Run-level guard: abort if the judge_error RATE across delivered sentences exceeds this (the verifier
    # was so degraded the run is not trustworthy). 0.10 = 10%. Surfaced to the manifest either way.
    "PG_MAX_JUDGE_ERROR_RATE": "0.10",
    # F03 (A3): verified-section-FRACTION floor. The success gate aborts at ZERO verified sections
    # (abort_no_verified_sections), but a report where most sections are gap stubs (only a couple
    # verify) previously shipped GREEN — a mostly-gap clinical report misrepresented as complete.
    # This is a COVERAGE-HONESTY floor (a sibling of the §9.2 per-section "≥40% sentences verified"
    # gate, lifted to the SECTION granularity): below it, run_one_query emits the NON-`partial`
    # abort_excessive_gap and Gate-B fails the run (query_status_ok). It is NOT a §-1.3 breadth
    # TARGET — it never forces a number up, it only refuses to call a gap report "complete". 0.4 =
    # the §9.2 0.40 per-unit honesty threshold at section granularity (grounded, not tuned). FLOAT in
    # [0,1] -> force-EXACT (the int FLOOR path would coerce 0.4 -> 0, silently disabling it, the exact
    # PG_RELEVANCE_FLOOR gotcha). Code default 0.0 => slate-absent runs are byte-identical; the slate
    # ACTIVATES it for the cert run (the PG_LIVE_MAX_EV_TO_GEN "built-it-then-left-it-off" lesson).
    "PG_MIN_VERIFIED_SECTION_FRACTION": "0.4",
    # I-ready-013 (#1080): benchmark report.md must be a verified-only surface.
    # The legacy Analyst Synthesis layer is interpretive and not span-verified /
    # 4-role gated, so Gate-B force-disables it instead of turning on the planner
    # or changing the verifier machinery.
    "PG_SWEEP_ANALYST_SYNTHESIS": "0",
    # I-ready-004 (#1078): finding-dedup. Collapse near-duplicate findings to one corroboration-counted
    # representative + apply a relevance floor. The legacy PG_USE_FINDING_DEDUP mode CONSOLIDATES (keeps
    # ALL sources per claim, multi-citation) — §-1.3 CONSOLIDATE-DON'T-DROP. PG_RELEVANCE_FLOOR is a FLOAT
    # in (0,1] — force-set as a string below (it must NOT ride the int FLOOR path, which coerces 0.30 -> 0;
    # Codex P1-2). 0.30 = the researched default (I-meta-005 Phase 5 #989).
    "PG_USE_FINDING_DEDUP": "1",
    # I-arch-007 #1264 DORMANT-CAP CLEANUP (operator: ZERO cap, §-1.3 BANNED number-forcing bolt-on). The
    # old PG_CAPPED_FINDING_DEDUP=1 re-truncated the consolidated relevance-floor pool back DOWN to
    # PG_LIVE_MAX_EV_TO_GEN (max_ev) at run_honest_sweep_r3.py:6937-6957 (+ the gap-round sibling at
    # ~L7683) — a CAP that fights the WEIGHT-AND-CONSOLIDATE architecture. It was already BYPASSED on the
    # live run because both re-cap blocks ALSO gate on `not _cred_redesign_on`, and PG_SWEEP_CREDIBILITY_
    # REDESIGN=1 here (so `_cred_redesign_on` is True -> the re-cap never fired). Setting it 0 removes the
    # cap UNCONDITIONALLY — verified at run_honest_sweep_r3.py:6937-6957 + :7683-7696 that `_capped_dedup`
    # falsy (0/""/non-"1") makes the boolean `and _capped_dedup` short-circuit, so BOTH `_capped_finding_
    # dedup_selection` re-cap-to-max_ev calls are skipped; PG_CAPPED_FINDING_DEDUP is read ONLY at those
    # two sites (run_honest_sweep_r3.py:6744 reader; no other consumer in src/ or scripts/), so 0 has ZERO
    # unintended behaviour — the consolidated keep-all floor pool flows to composition bounded only by the
    # per-section token budget + the UNCHANGED faithfulness gate. The live-run behaviour is byte-identical
    # to the prior =1 value (both bypassed via the redesign flag); 0 makes the no-cap intent explicit and
    # independent of the redesign flag. Removed from _BENCHMARK_FORCE_ON_FLAGS + _BENCHMARK_PREFLIGHT_
    # REQUIRED_FLAGS below (a required-truthy flag set to 0 would fail the preflight).
    "PG_CAPPED_FINDING_DEDUP": "0",
    "PG_RELEVANCE_FLOOR": "0.30",
    # I-arch-007 #1264 DORMANT-CAP CLEANUP (operator: ZERO cap, §-1.3 BANNED bolt-on). The per-source
    # citation cap (fact_dedup.py: drops over-concentrated citations from an already-verified section to
    # hit a per-source number). Default OFF already (unset/""/0/<=0 == no-op, byte-identical sections —
    # fact_dedup.py:63-94 `_read_span_cite_cap`), so it has never been ON on a benchmark run; pin it
    # EXPLICITLY to "0" (force-EXACT below) so a stray operator/.env PG_SPAN_PER_SOURCE_CITE_CAP=N can
    # never silently re-enable the cap on the paid run. FAITHFULNESS-NEUTRAL: the cap only ever DROPPED an
    # already-verified citation; OFF keeps every verified citation.
    "PG_SPAN_PER_SOURCE_CITE_CAP": "0",
    # I-perm-011 (#1205): max-over-subqueries relevance floor. `_row_relevance`
    # normalizes overlap by the WHOLE multi-part question token set, so a ~73-token
    # research question makes the 0.30 floor demand >=22 exact-word matches — which
    # over-drops on-topic top-tier papers whose domain vocabulary doesn't lexically
    # match the question's exact words (drb_76: 597->53 pre-select; 74 on-topic T1
    # shed). ON => each row is scored against the BEST-MATCHING decomposed sub-query
    # (q1d + planner facets, small per-facet denominators) and the floor uses
    # max(whole-question, best-facet) — MONOTONIC-UP, so it can only OPEN the
    # throttle (keeps a SUPERSET), never tighten it. PG_LIVE_MAX_EV_TO_GEN stays
    # 1500 (DELIBERATELY UNCHANGED): the post-fix surviving pool is <= the
    # pre-select total (597 for drb_76) which is < 1500, so the global pool cap is
    # non-binding by construction; the BINDING per-prompt guard is
    # PG_MAX_EV_PER_SECTION=40 (line 490). Lowering the pool cap would re-impose the
    # niche-section starvation the 2026-06-10 operator decision (lines 475-482)
    # explicitly removed — so the diagnosis's secondary "lower to 200" is NOT
    # applied here. Default OFF in code => slate-absent runs are byte-identical.
    "PG_SELECT_SUBQUERY_FLOOR": "1",
    # I-arch-005 PREFLIGHT FIX (#1257): the pre-run dual-audit (Claude Workflow + 3 Codex lanes,
    # outputs/audits/b1b10_redesign/PREFLIGHT_24FIX_FINDINGS.md) found these I-arch-005 fixes committed +
    # Codex-approved but DEAD on the benchmark because Gate-B never activated their (correctly default-off)
    # flags. All independently verified PRESENT + FAITHFULNESS-SAFE. Force them via the slate (FORCE_ON for
    # the booleans, FORCE_EXACT for the string scorer below) so an .env=0/lexical cannot win and apply()-only
    # callers (tests / super_heavy_preflight) stay consistent. PG_RELEVANCE_SCORER is also asserted
    # value-equals 'semantic_v2' in preflight_full_capability (fail-closed).
    "PG_RELEVANCE_SCORER": "semantic_v2",   # B1: lexical->embedding relevance scorer (else legacy lexical + keep-all)
    "PG_RETRIEVAL_RELEVANCE_GATE": "1",     # B4: relevance-threshold+fetch-budget rerank (else legacy _rerank_and_reserve)
    "PG_SWEEP_CREDIBILITY_REDESIGN": "1",   # B6/B8 KEYSTONE basket render + B12 credibility label/guard (else dark)
    "PG_REDACT_HELD_UNSUPPORTED": "1",      # B16 hardening: a stray operator =0 must not skip the held-unsupported quarantine
    # I-ready-017 FX-03 (#1107): the 4-role seam MUST judge each claim against the cited [start:end]
    # BOUNDED window, not the whole source doc (BUG-02 confirmed out-of-span false-accept, claim
    # 06-004). OFF feeds whole-record evidence to Sentinel/Judge so a claim can be VERIFIED on support
    # living ANYWHERE in the doc — a silent faithfulness downgrade on the AUTHORITATIVE release gate.
    # Force-on + required below so the paid run cannot fall back to whole-doc. Window matches
    # strict_verify's 400-byte local-window tolerance (ONE shared policy).
    "PG_GATE_B_CITED_SPAN": "1",
    "PG_GATE_B_SPAN_WINDOW_BYTES": "400",
    # I-perm-022 (#1214): LIGATURE-ONLY normalization of the cited SPAN (decompose the
    # presentation-form ligatures U+FB00..U+FB06 to their letters) BEFORE the four-role
    # evaluators read it, so a PDF-extraction ligature does not produce a false-negative
    # [confidence:low] on a genuinely-supported atom. RECOVERS true positives only — no
    # word-boundary change, ZERO digit modification, gate byte-untouched; flag-OFF
    # byte-identical. (De-hyphenation / zero-width were dropped as §-1.1-unsafe.)
    "PG_GATE_B_SPAN_NORMALIZE": "1",
    # I-ready-017 CANARY-01 (#1107/#1108): the BEHAVIORAL pre-spend canary MUST run on the real
    # Gate-B run — real call shapes (searcher/generator structured-output + 1-query live search) must
    # be ALIVE or the run fails closed before spend. OFF would let a dead-discovery run go green (the
    # drb_72 failure). Force-on + required below; the canary itself runs only on the live path.
    "PG_BEHAVIORAL_CANARY": "1",
    # I-cred-013 (#1163): the SUPER-HEAVY behavioral pre-spend preflight MUST run on the real beat-both
    # Gate-B run — it COMPOSES CANARY-01 with: EVERY model slug (generator + 3 verifiers + the
    # credibility judge when active) ALIVE in its production call shape, STORM/discovery non-empty,
    # host-local chromium present, and a RUNTIME re-assertion of the 5 recurring false-alarm regression
    # locks. OFF would drop back to the lighter canary alone and let a dead verifier/STORM/browser tier
    # ship a false-green paid run. Force-on + required below; the preflight runs only on the live path.
    "PG_SUPER_HEAVY_PREFLIGHT": "1",
    # I-ready-017 FX-14 (#1129): force the custody-lane honesty marker ON so the paid run emits
    # custody_lane_status.json (not_applicable_planner_lane) instead of a silently-empty
    # v29_primary_custody.json / m44_primary_citation_telemetry.json when primary-trial seeds reach
    # generation but the M-44/V29 custody block does not run in the planner lane. Telemetry-only.
    "PG_CUSTODY_LANE_MARKER": "1",
    # I-ready-017 FL-05b (#1137): activate the FL-05 (#1124) run-health backstop. FL-05's
    # compute_run_health_gate aborts a would-be-SUCCESS run to abort_discovery_degraded (+
    # release_allowed=False) when a FORCE-ENABLED discovery feature (STORM / agentic) was on but did NOT
    # fire (firing_status attempted_empty/error) — i.e. the run silently fell back to the Serper/S2
    # baseline. The gate is flag-gated PG_RUN_HEALTH_GATE (default OFF in run_honest_sweep_r3.py: status,
    # control-flow and the release decision are unchanged when off — only two additive observability
    # fields are written). The benchmark MUST run with it ON so a silently-degraded discovery cannot
    # ship green. Force-on + required below (an explicit operator =0 must not survive the slate). Pairs
    # with CANARY-01 (pre-spend); FL-05 is the mid/post-run regression backstop.
    "PG_RUN_HEALTH_GATE": "1",
    # I-fetch-002 (#1168): STORM UNDER-fire floor. FL-05 (#1124) aborts only when a force-enabled
    # discovery feature TOTALLY no-fires (firing_status attempted_empty/error). This floor extends the
    # SAME gate to the UNDER-fire case: STORM force-on FIRED but produced FEWER than this many effective
    # (post-validator) queries — a thin-corpus collapse that would otherwise ship green. Discovery-health
    # only (faithfulness-neutral). Read at the run_honest_sweep_r3.py compute_run_health_gate call site.
    "PG_STORM_MIN_EFFECTIVE_QUERIES": "12",
    # ─────────────────────────────────────────────────────────────────────────────────────────────
    # I-beatboth-fix-000 (#1171) RETRIEVAL-BREADTH cluster — widen DISCOVERY (candidates), and keep total
    # FETCH at the hard 1000 envelope by ABSORBING the new STORM seed lane into the budget: the FETCH
    # lanes are main 740 + agentic 100 + deepener 60 + R6 40 + STORM 60 = 1000 (main trimmed 800->740 per
    # Codex P1, no overshoot). All seven fixes are faithfulness-NEUTRAL (no strict_verify / NLI /
    # 4-role / provenance path touched). Several keys are STRING- or sub-1-FLOAT-valued and MUST ride
    # the force-exact path (the numeric FLOOR path would int()-truncate 0.08 -> 0, disabling the gate,
    # or crash on float("containment")) — they are listed in _BENCHMARK_FORCE_EXACT_FLAGS below.
    #
    # BB-001: the scope-validator floor + similarity measure. Symmetric Jaccard punishes short on-topic
    # queries against a 28-40-token anchor (the #1 chokepoint: 40->5 kept). containment (|q∩a|/min) +
    # a researched 0.08 floor keep short on-topic queries while still failing genuine drift (gate KEPT).
    "PG_AMPLIFIER_SCOPE_FLOOR": "0.08",
    "PG_SCOPE_SIM_MEASURE": "containment",
    # BB-002: Serper keeps offset-paging past a sub-per_page page (the unreliable end-of-results signal)
    # until budget / 0-new / PG_SERPER_MAX_PAGES. Discovery only — main-lane FETCH stays capped at 800.
    "PG_SERPER_STOP_ON_ZERO_NEW": "1",
    # BB-003: OpenAlex /works search at per_page=200 (API max) + cursor paging to cover PG_SWEEP_MAX_S2.
    # MAX_S2=100 fits in ONE 200-page, but allow 2 cursor pages as headroom (still discovery, not fetch).
    "PG_OPENALEX_PER_PAGE": "200",
    "PG_OPENALEX_MAX_PAGES": "2",
    # BB-005: harvest MORE of the ~1933 agentic-discovered URLs for DISCOVERY TELEMETRY
    # (urls_discovered_total) WITHOUT raising the agentic FETCH lane — the fetched subset stays
    # truncated to PG_AGENTIC_BENCHMARK_URL_CAP=100 (budget lane 2/4). Telemetry-only widening.
    "PG_AGENTIC_HARVEST_CAP": "800",
    # BB-006: ingest the STORM interview-search-result URLs (478/540 real web URLs previously discarded)
    # as URL-ONLY seed candidates (the synthesized STORM answer/key_findings text is NEVER ingested).
    # PG_STORM_URL_CAP bounds the harvest; PG_STORM_URL_FETCH_CAP (60) bounds the SEPARATE ADDITIVE
    # STORM fetch lane — disclosed for the operator's ~1000-fetch accounting (this is the one fix that
    # adds fetch beyond the four lanes; bounded small and surfaced, not silently overshooting).
    "PG_STORM_INGEST_WEB_RESULTS": "1",
    "PG_STORM_URL_CAP": "200",
    "PG_STORM_URL_FETCH_CAP": "60",
    # BB-007: a REAL Unpaywall contact email so the (default-ON) OA resolver actually fires — the
    # placeholder polaris@example.org is treated as resolver-UNAVAILABLE (fail-loud) by the resolver,
    # a hidden cause of the 67-72% fetch-fail rate. Real DOI-keyed OA full-text upgrades no_content stubs.
    "PG_UNPAYWALL_EMAIL": "research@polaris-dr.org",
    # ─────────────────────────────────────────────────────────────────────────────────────────────
    # I-cred-006b (#1170): REPLACE the corpus-level tier-COUNT / material-deviation REFUSAL with PROCEED
    # + a credibility-weighted disclosure (operator directive 2026-06-08: "we shall NOT have gate here,
    # we shall WEIGHT the source"). The drb_72 dry-run aborted abort_corpus_approval_denied because 50%
    # of 151 sources were T4 on an ECONOMICS question where NBER/Acemoglu working papers are legitimate
    # primary sources — a §-1.1-banned domain-blind tier-count refusal. ON: the corpus is accepted +
    # credibility-disclosed (weighted, domain-aware); the per-claim faithfulness floor (strict_verify +
    # 4-role D8) is UNCHANGED; the corpus-ZERO floor still aborts. Force-on + required below so a stray
    # operator =0 cannot survive the setdefault slate and silently restore the tier-count refusal on the
    # paid beat-both run (the I-cap-005 P1-1 force-on pattern).
    "PG_SWEEP_WEIGHTED_CORPUS_GATE": "1",
    # I-perm-000 permanent-fix activation (#1194). Each fix is DEFAULT OFF (byte-identical) and is
    # INERT in production unless the slate turns it on — the exact "fix built but not live" trap.
    # Force-on + required below so a stray operator =0 cannot survive the setdefault slate and
    # silently restore the pre-fix behaviour on the paid beat-both run.
    #   PG_ALWAYS_RELEASE         (#1195 keystone) WITHHOLD->ALWAYS-RELEASE+LABEL: a held report ships
    #                             with disclosed gaps instead of aborting (the drb_76 false hold).
    #   PG_SWEEP_NUMERIC_SANITIZER(#1201) drop DOI/URL/accession cruft parsed as clinical data.
    #   PG_SWEEP_SEMANTIC_CONTRAINDICATION (#1196) credit a faithful contraindication WARNING
    #                             ("not recommended"/"should be avoided") whose source never uses the
    #                             literal "contraindicated" — negation-guarded so an inverted claim
    #                             never over-credits; drb_76 then ships caveated-normal instead of
    #                             released_insufficient_safety_evidence.
    # NOT activated here: PG_SWEEP_SELECTION_SCALE (#1197) — the blueprint keeps it flag-OFF until
    # I-perm-007 grows a real large pool (it is preventative; on the current corpus it would scale
    # the budget ABOVE the #1070/#1078 evidence-to-generation cap and re-flood the generator).
    "PG_ALWAYS_RELEASE": "1",
    "PG_SWEEP_NUMERIC_SANITIZER": "1",
    "PG_SWEEP_SEMANTIC_CONTRAINDICATION": "1",
    # I-perm-004 (#1198) cited-recovery: re-anchor a wrongly-cited claim to the best ENTAILING span
    # (argmax) + re-point on the gap-#18 local-window rescue, instead of dropping / shipping a
    # mis-pointed citation. Slices 1-3 Codex-APPROVE'd.
    "PG_SPAN_RESOLVER": "1",
    # I-perm-004 #1180 widening: the EMPIRICALLY-PICKED widening-aware entailment prompt. The bake-off
    # (`scripts/dr_benchmark/widening_prompt_bakeoff.py --run` over `tests/fixtures/widening_labeled_set.json`)
    # scored widen_a/b/c at widening_neutral_recall=1.0 + entailed_precision=1.0 + zero
    # contradiction-acceptance (baseline missed the F02 strain->class widening); widen_c (the explicit
    # scope-then-support checklist) won. Force-exact so a stray .env cannot revert to baseline.
    "PG_ENTAILMENT_PROMPT_VARIANT": "widen_c",
    # I-perm-016 (#1209) KEYSTONE: the map-reduce evidence distiller. DEFAULT OFF
    # (byte-identical legacy) and INERT in production unless the slate turns it on
    # — the exact "fix built but not live" trap. Force-on + required below so a
    # stray operator =0 cannot survive the setdefault slate and silently restore
    # the single-pass raw-quote generation path on the paid beat-both run (the
    # I-cap-005 P1-1 force-on pattern). The distiller only TIGHTENS faithfulness
    # (every finding pre-validated by the SAME production verifier; the unchanged
    # strict_verify re-checks the REDUCE output) so forcing it on can never weaken
    # a gate.
    "PG_SECTION_DISTILL": "1",
    # I-perm-024 (#1216): force the beat-both scorer's extended claim-by-claim
    # metrics (faithfulness_precision / required_entity_recall / safety_floor_recall
    # / citation_support_rate / diversity_score + Claimify dedup) ON for the broad
    # run, so the archived scorecard carries the extended block (Codex brief-gate
    # iter-1 P2). MEASUREMENT-ONLY — it runs AFTER the report exists and touches no
    # generator / strict_verify / 4-role / D8 path; flag-OFF the scorecard is
    # byte-identical. Every metric is derived from the §-1.1 audit ledger + the
    # frozen rubric, never from raw report text.
    "PG_BENCH_EXTENDED_METRICS": "1",
    # I-perm-021 (#1213): force-on the RequiredEntityLedger — report-level required-entity
    # completeness accounting + honest "Coverage gaps" disclosure (inclusion + disclosure only;
    # no re-generation). Reuses the 4-role seam's covered_element_ids + the native required
    # entities; assigns NO new credit and touches NO gate; fail-soft. Surfacing honest coverage
    # gaps is a POLARIS differentiator for the beat-both run. Flag-OFF byte-identical.
    "PG_REQUIRED_ENTITY_LEDGER": "1",
    # I-perm-023 (#1215): force-on the constrained-greedy diversity-aware selection pass — a
    # post-floor, same-tier, COVERAGE-MONOTONE diversification on the safety-category +
    # evidence-class (+ jurisdiction-beyond-M41d) axes the existing floor stack does NOT cover.
    # FORWARD GUARD: a no-op until retrieval (#1204/#1207) grows the post-extraction pool past the
    # generator cap; at that scale it prevents a topical/safety monoculture in the selected evidence.
    # Touches NO floor / quota / protected row (parity by construction) and NO gate (selection only
    # changes the generator's candidate menu; strict_verify / 4-role / D8 re-check unchanged).
    # Flag-OFF byte-identical.
    "PG_SELECT_CONSTRAINED_GREEDY": "1",
    # ─────────────────────────────────────────────────────────────────────────────────────────────
    # I-arch-007 CONSOLIDATED DEATH-FORENSIC SLATE (GH #1264). Six death modes across the 5 dead runs
    # reconcile to 3 root mechanisms + 2 containment gaps. The slate WIRES the env knobs the keystone
    # fixes consume so a fix can never ship "built but not live" (the #1070 lesson). Every key here is
    # FAITHFULNESS-NEUTRAL: it touches an advisory-stage wall/parallelism, a D8-seam transport degrade
    # that fails CLOSED, a generation-skip that re-runs all gates, or process containment — NONE moves
    # strict_verify / NLI / 4-role D8 / span-grounding, the fail-closed sentinel, the 0.40 section floor,
    # or the cited-evidence set. See outputs/audits/iarch007_death_forensic/CONSOLIDATED_FIX_PLAN.md.
    #
    # ITEM 1 + 1b (Codex P2-1 — SIZE AS A PAIR): the advisory credibility pass is a SERIAL nested loop
    # over every basket member (~310 members on Q90 up to ~619 on Q72), each member running ONE binding-
    # entailment-judge call (~6-40s healthy). ITEM 1's PG_CREDIBILITY_PASS_WALL_S is the wall-deadline
    # that stops the run HANGING (the Q72/Q76/Q90 death); ITEM 1b's PG_CREDIBILITY_PASS_MAX_INFLIGHT is
    # the bounded parallelism that makes the pass actually COMPLETE within that wall. They MUST be sized
    # TOGETHER: a wall too short (or inflight too low) degrades a HEALTHY large-corpus pass to
    # credibility_analysis=None / sources-unscored (faithfulness-safe disclosure, but the WEIGHT half of
    # §-1.3 ships silently degraded). Sizing math for the WORST healthy large corpus (~619 members @ 40s):
    #   wall >= members * per_call / inflight  =>  619 * 40 / 16 ≈ 1548s < 3000s wall (clears with ~2x margin).
    #   a typical healthy pass (~310 members @ ~6s): 310 * 6 / 16 ≈ 116s — far under the wall.
    # CHOSEN PAIR: PG_CREDIBILITY_PASS_MAX_INFLIGHT=16, PG_CREDIBILITY_PASS_WALL_S=3000 — a healthy
    # ~600-member pass COMPLETES within the wall; an UNHEALTHY (trickle/blank-content) pass still
    # degrades-and-discloses at the wall instead of hanging. inflight 16 mirrors P2's existing
    # credibility-skill concurrency shape and stays at/under the LLM concurrency envelope.
    # I-arch-007 #1264 PREFLIGHT RE-SIZE (death NO-GO follow-up): the wall is RAISED 1800 -> 3000 to give
    # generous headroom for the LONGEST healthy credibility pass (the ~1548s worst-case @ 619 members /
    # 40s / inflight-16 had only ~250s slack against 1800; 3000 nearly doubles it so a slow-but-HEALTHY
    # large corpus completes-and-WEIGHTS instead of degrading at the wall). 3000s is still FAR under the
    # run-wall (10800s) so the credibility pass can never starve Stage-2 generation — the wall hierarchy
    # credibility 3000 << run-wall 10800 holds. The trickle-HANG itself is now bounded by the new per-call
    # total-deadline knobs below (PG_CREDIBILITY_JUDGE_TOTAL_S / PG_ROLE_TRANSPORT_TOTAL_S), so the wall
    # no longer has to be the ONLY backstop against a hang — it is the pass-level cap, the per-call walls
    # are the call-level cap.
    # NOTE: PG_CREDIBILITY_PASS_MAX_INFLIGHT stays at 1 (serial) in code until ITEM 2a (thread-safe judge
    # client) lands — the slate value is INERT until 1b's parallelism is enabled atop 2a (plan §8 PR-2).
    # FLOAT/INT values -> force-EXACT (the int-FLOOR path is wrong for the wall; force the chosen pair).
    "PG_CREDIBILITY_PASS_WALL_S": "3000",
    "PG_CREDIBILITY_PASS_MAX_INFLIGHT": "16",
    # ITEM 4 (deploy commit 376ac812): the sentinel transport-fault degrade-and-continue. A single
    # blank/non-JSON sentinel HTTP-200 used to tear down the WHOLE D8 seam -> coverage hardcoded 0.0 ->
    # curator_gap emptiness (~177 claims). ON marks ONLY that claim sentinel-unavailable (fail-CLOSED
    # UNGROUNDED, never GROUNDED) and the D8 seam CONTINUES with real coverage. Default-ON in code; the
    # slate force-ON-pins it so a stray operator =0 cannot survive and silently restore the whole-seam
    # zeroing on the paid run. FAITHFULNESS-NEUTRAL: a sentinel transport blip can never pass a fabrication
    # as grounded; it only stops one blip from zeroing the seam (faithfulness STRENGTHENED).
    "PG_SENTINEL_TRANSPORT_DEGRADE": "1",
    # I-arch-007 #1264 PREFLIGHT RE-GO (death NO-GO follow-up, death_gone=false): the residual
    # thread-level TRICKLE-HANG. The two sync-POST verifier sites were bounded ONLY by an httpx read-GAP
    # (a per-byte gap that a trickled keep-alive socket RESETS indefinitely — the same HANG-J3 mechanism
    # the entailment judge already fixed), with NO per-call TOTAL deadline. The sibling agents add the
    # PROVEN _post_with_total_deadline template (a ThreadPoolExecutor(max_workers=1).submit(post).result(
    # timeout=TOTAL_S) HARD wall that force-CLOSES the hung socket on timeout so the blocked read
    # unblocks, then a bounded retry rebuilds the client) to BOTH sites, gated by these two knobs. Force
    # them to the chosen 300s wall so the benchmark ALWAYS runs with the hard per-call total-deadlines on
    # (a stray operator value cannot leave a site unbounded). 300s comfortably exceeds the longest HEALTHY
    # verifier call (~6-40s observed) so a healthy call NEVER trips the wall — only a trickle-hang is force-
    # closed; OFF-path the per-call POST is byte-identical (the generous default never fires on a healthy
    # call). TRANSPORT-ONLY + FAITHFULNESS-NEUTRAL: on total-deadline exhaustion each site emits the SAME
    # fail-CLOSED sentinel its caller already handles (the verdict logic / strict_verify / NLI / 4-role D8 /
    # span-grounding / the fail-closed sentinel / the 0.40 floor are ALL UNTOUCHED) — the wall only bounds
    # the wall-clock, never changes a verdict. PG_CREDIBILITY_JUDGE_TOTAL_S bounds the per-member binding-
    # entailment-judge POST in the advisory credibility pass; PG_ROLE_TRANSPORT_TOTAL_S bounds the per-role
    # 4-role-seam verifier POST. Force-EXACT (these are wall-seconds, not capability floors).
    "PG_CREDIBILITY_JUDGE_TOTAL_S": "300",
    "PG_ROLE_TRANSPORT_TOTAL_S": "300",
    # I-arch-011 (verify-speed): provider-ROTATION on a blank/garbled 200. The mirror role pins ONE host
    # (z-ai) with allow_fallbacks:False; z-ai has intermittent empty-body-200 windows under account-QPS load
    # (measured 2026-06-19: a micro-test stormed with blank-200s during one window, then ran 100% clean ~40min
    # later — same host, same shape). OpenRouter does NOT auto-advance off a blank (it is an HTTP 200), so
    # every retry re-hit the SAME blanking host and the entailment judge_error sentinel DROPPED the sentence
    # in enforce mode -> a FAITHFUL-but-NARROW breadth collapse (the I-arch-011 symptom). ON makes the
    # entailment + credibility judges ADVANCE through the mirror chain (z-ai->baidu->novita->gmicloud, all
    # validated 100%-clean+correct on box4) on a blank/parse/bad-verdict fault, so the retry gets a REAL
    # verdict from a healthy host. FAITHFULNESS-NEUTRAL-to-IMPROVING: same glm-5.1 model on every host
    # (operator pre-approved judge host non-sovereignty 2026-06-13); a real baidu ENTAILED beats a z-ai-blank-
    # induced DROP, and a real NEUTRAL/CONTRADICTED still DROPS — the NLI gate logic, the fail-closed sentinel,
    # the section floor, and the cited-evidence set are ALL untouched. Force-ON so a stray operator =0 cannot
    # silently restore the single-host blank-storm on the paid run. Default-OFF in code (byte-identical pin).
    "PG_JUDGE_PROVIDER_ROTATE": "1",
    # I-arch-011 Codex diff-gate P2: the mirror chain has FOUR hosts (z-ai->baidu->novita->gmicloud) but the
    # default retry budget is 2 (= 3 attempts), so rotation could not reach gmicloud. Raise to 3 (= 4
    # attempts) so a blank on EVERY host before the last is still recoverable. Each extra attempt fires ONLY
    # on a fault (a healthy call returns on attempt 1), so this never slows a healthy run; it only widens the
    # rescue depth. Faithfulness-neutral (same fail-closed sentinel on exhaustion).
    "PG_ENTAILMENT_RETRIES": "3",
    "PG_CREDIBILITY_JUDGE_RETRIES": "3",
    # I-arch-007 ITEM 2 (#1264) BREADTH — force-ON the weighted unbound-SUPPORTS enrichment section so
    # the benchmark surfaces the ~437 span-verified sources the 5-entity contract funnel drops (the
    # 485->~13 collapse). §-1.3 WEIGHT-AND-CONSOLIDATE: the selection ORDERS by basket weight_mass and
    # offers the FULL list — NO cap / target / top-N; breadth EMERGES from how many survive the
    # UNCHANGED strict_verify in _run_section. Default-OFF in code so a non-benchmark run is byte-
    # identical; the slate force-ON-pins it so a stray operator =0 cannot silently keep the funnel.
    # FAITHFULNESS-NEUTRAL: every surfaced source re-passes the same strict_verify + section floor as
    # every other section; on a degraded pass (credibility_analysis is None) the selection is empty.
    "PG_BREADTH_ENRICHMENT_ENABLED": "1",
    # I-arch-011 (#1268): the COMPOSITION rebuild's default-OFF feature flags — slate-pinned "1" so
    # apply_full_capability_benchmark_slate() FORCE-SETS them (it iterates THIS dict) and a stray operator
    # =0 cannot keep the OLD composition. PR-a STORM-outline section scaffold / PR-b Argus keep-all
    # basket-corroboration render / PR-c per-basket verified-compose (+ verbatim K-span fallback) / PR-d
    # verbatim abstract+conclusion synthesis. Faithfulness-SAFE: strict_verify + the I-arch-010 tail engine
    # are UNTOUCHED; flag-OFF byte-identical in code. Also in _BENCHMARK_FORCE_ON_FLAGS (force) +
    # _BENCHMARK_PREFLIGHT_REQUIRED_FLAGS (fail-closed if any is off before spend).
    "PG_STORM_OUTLINE_SECTIONS": "1",
    "PG_BASKET_CORROBORATION_RENDER": "1",
    "PG_VERIFIED_COMPOSE": "1",
    "PG_SYNTHESIS_ABSTRACT_CONCLUSION": "1",
    # I-arch-011 run-5 794->9 collapse — two of the FOUR stacked breadth-restore conditions (the forensic
    # collapse_forensic_plan.json F4 + F5; F1 finding_key + F2 basket-decouple are code fixes). FAITHFULNESS-
    # NEUTRAL consolidation knobs — they MERGE/RENDER already-verified corroborators, never drop/cap.
    # F4: consume finding_dedup membership so the claim_graph singleton partition (build_merge_key fail-closes
    # to singletons on blank clinical dose/comparator/endpoint) re-merges into multi-citation baskets before
    # _assemble_baskets (group + edge-remap only; no member newly passes any gate). Default OFF in code =>
    # slate-absent byte-identical; force ON so the basket actually consolidates.
    "PG_BASKET_CONSUME_FINDING_DEDUP": "1",
    # F5 (FIX-K): render the surfaced basket's ALREADY-VERIFIED spans VERBATIM rather than LLM-regenerating
    # prose (~0 of which survives strict_verify). Without this the restored basket renders narrow. Was set
    # via the run ENV in run-5; pin in the slate so it cannot drift.
    "PG_BREADTH_ENRICHMENT_RENDER_VERIFIED_SPANS": "1",
    # I-arch-007 ITEM 6 (#1264) — A15 resume FETCH-SHELL re-fetch. On a --resume the frozen
    # corpus_snapshot reloads the crashed run's EMPTY-SHELL anchor rows (e.g. SAE J3016, UNECE ALKS,
    # PACER docket) untouched; empty cited spans -> strict_verify CORRECTLY drops -> the Q90
    # abort_excessive_gap 96% over-drop. Force-ON so a --resume RE-FETCHes those degraded rows through
    # the AccessBypass+Zyte cascade and re-grounds direct_quote with real content BEFORE generation. A
    # row still a shell after the cascade stays disclosed and the UNCHANGED strict_verify drops any
    # ungrounded claim (NO fabrication). Default OFF in code so a non-benchmark resume is byte-identical.
    # FAITHFULNESS-SAFE: fixes the INPUT (real spans), touches NO threshold and NO gate.
    "PG_RESUME_REFETCH_DEGRADED": "1",
    # I-arch-011 B19 (KEYSTONE — the distill_map hang fix): pin the per-call wall + parallelism so
    # they cannot silently drift. PG_DISTILL_MAP_CALL_WALL_S bounds each distill_map call END-TO-END
    # (asyncio.wait_for, above the 1475s healthy max, well under the 10800s run-wall) so a half-open
    # SSE socket can no longer hang the asyncio loop ~1.8h (the drb_78 death). PG_DISTILL_MAX_PARALLEL=8
    # widens the map fan-out (breadth-positive, not a throttle). Code defaults already equal these, so
    # slate-absent runs are byte-identical — pinned for clarity + drift-protection.
    "PG_DISTILL_MAP_CALL_WALL_S": "1800",
    "PG_DISTILL_MAX_PARALLEL": "8",
    # I-arch-011 FIX-C (run #6 enrichment-verify "freeze" — the wiring gap): the I-arch-006 fix#19
    # bounded-PARALLEL findings verify (provenance_generator._parallel_verify_workers) exists but was
    # NEVER set in the slate, so the 737-source breadth-enrichment section verified its ~1839
    # sentence-units SERIALLY. At a healthy ~5.7s/call that is ~173min for ONE section — it blows the
    # run wall and looks frozen (the run-#6 "deadlock" was this serial grind, NOT a per-call deadlock;
    # the per-call total-deadline was proven sound by scripts/iarch011_entailment_deadline_repro.py).
    # Cap concurrency at 16 (matches PG_CREDIBILITY_PASS_MAX_INFLIGHT). The per-call total-deadline in
    # entailment_judge (PG_ENTAILMENT_TOTAL_S=45) is what makes it HANG-SAFE — parallelism alone is not
    # (list(map())+shutdown(wait=True) would block on a never-returning future). FAITHFULNESS-NEUTRAL:
    # the parallel path copies the parent contextvars context and ``map`` preserves input order, so
    # kept/dropped is byte-identical to the serial loop (concurrency changes timing, not verdicts); a
    # worker exception still propagates fail-loud. Behavioral proof on the banked drb_78 corpus + REAL
    # glm-5.1 judge (scripts/iarch011_parallel_verify_gate.py): the enrichment verify COMPLETES in
    # 17.4min (was ~173min serial) and keeps 1746 cited / 657 distinct sources on the enforce path.
    "PG_PARALLEL_VERIFY": "16",
    # I-arch-011 B02/B04 (FETCH lane): re-fetch fetch_degraded rows through the live-retriever Zyte
    # cascade on the FRESH (non-resume) path too — PG_RESUME_REFETCH_DEGRADED above covers the
    # --resume path, and this is INERT on a resume (no live fetch runs). Default OFF in code so a
    # slate-absent run is byte-identical; force here so the FETCH lane is not dark on fresh runs.
    # FAITHFULNESS-SAFE: fixes the INPUT (real spans); a row still a shell after the cascade stays
    # disclosed and the UNCHANGED strict_verify drops any ungrounded claim. (ZYTE_API_KEY must be in
    # the run .env — without it the Zyte step is a logged no-op, never a silent stub-as-fulltext.)
    "PG_REFETCH_DEGRADED_VIA_ZYTE": "1",
    # ITEM 5 (postgen-resume reuse) — DELIBERATELY NOT slate-forced while ITEM 5a is deferred
    # (Codex build-gate iter-1 P1). The CONSUMER wiring (_load_postgen_reuse_reentry) is fully built
    # and fails LOUD, but the GENERATOR-side cached-draft hook
    # (multi_section_generator.generate_multi_section_report_from_reused_drafts) is the deferred ITEM
    # 5a — it does not exist yet. Force-ON-ing PG_RESUME_REUSE_POSTGEN here would make every --resume
    # HARD-FAIL: the dead runs never wrote a generation_snapshot in this NEW format
    # (load_generation_snapshot -> GenerationSnapshotError) and the generator hook is absent
    # (-> RuntimeError), and run_one_query calls the loader with no surrounding try/except. The plan's
    # ITEM-5 deferral clause is explicit that the deferred state is "Q78 simply RE-GENERATES from
    # corpus_snapshot like the other four" — GRACEFUL, not a crash. So leave the flag OFF on the slate:
    # the resume path stays byte-identical to today (fresh re-generate from corpus_snapshot), and the
    # ITEM 1 + 2a fixes still stop the re-wedge / over-drop on that fresh run. RE-ADD this slate pin in
    # the same PR that lands the ITEM 5a generator hook + a corpus/evidence-identity guard (so a reused
    # draft is proven to match the reloaded corpus before any binding gate re-runs on it).
    # ITEM 6 (Codex MODE 1 — force subprocess containment): trafilatura runs libxml2 (a C extension); a
    # libxml2 SIGSEGV on a pathological doc is NOT a catchable Python exception and silently kills the
    # whole sweep on the in-process path. The in-process door is open whenever PG_TRAFILATURA_SUBPROCESS
    # != "1". The prior run_gate_b_query setdefault left an operator override able to leave containment
    # OFF; FORCE it ON here (the slate force-EXACT path) so EVERY benchmark run is subprocess-contained
    # — a crash becomes a hard-killable child rc=-11/-9 the parent survives + a fetch-degraded row, never
    # a silent process death. FAITHFULNESS-NEUTRAL: affects fetch robustness/yield only — never a gate
    # verdict. PG_TRAFILATURA_SUBPROCESS_TIMEOUT_SECONDS bounds the contained child so a hung libxml2
    # child cannot wedge the fetch (an OOM/SIGKILL/timeout child exit is recorded LOUD by
    # safe_trafilatura_extract -> regex-fallback + fetch-degraded, not a silent gap).
    "PG_TRAFILATURA_SUBPROCESS": "1",
}

# Minimum effective values the run MUST meet — the preflight FAILS CLOSED if any is below these (i.e.
# a silent throttle). Keyed by the env the run actually reads; floors are "full-capability" thresholds.
_BENCHMARK_PREFLIGHT_FLOORS: dict[str, int] = {
    "PG_SWEEP_FETCH_CAP": 500,
    "PG_SWEEP_MAX_SERPER": 50,
    "PG_SWEEP_MAX_S2": 50,
    # FX-17 (#1126): fail closed if the Serper pagination budget is below the floor — otherwise an
    # explicit operator override (or absence) leaves the run single-page (~20/query) and the
    # pagination fix is silently inert on the paid benchmark. TOTAL>=40 guarantees >1 page;
    # MAX_PAGES>=2 lets the budget be reached.
    "PG_SERPER_TOTAL_PER_QUERY": 40,
    "PG_SERPER_MAX_PAGES": 2,
    # I-fetch-002 (#1168): floor-guard the two un-guarded QUERY-BREADTH knobs so a conservative .env/
    # operator value cannot silently shrink the search-query fan-out below full capability. These are
    # query counts, NOT part of the ~1000-URL fetch sum. Floors == the slate values (30/15).
    "PG_STORM_MAX_BENCHMARK_QUERIES": 30,
    "PG_MAX_SUBQUERIES": 15,
}
# Flags that MUST be truthy for a full benchmark run (feature dead / unobservable otherwise).
# Codex diff-gate I-cap-005 P1-1: PG_SWEEP_EVIDENCE_DEEPENER MUST be required too — otherwise an
# explicit PG_SWEEP_EVIDENCE_DEEPENER=0 in the operator env survives the setdefault slate and the
# preflight still passes, letting the paid run go with the evidence deepener silently off.
_BENCHMARK_PREFLIGHT_REQUIRED_FLAGS = (
    "PG_STORM_ENABLED_IN_BENCHMARK",
    "PG_SWEEP_EVIDENCE_DEEPENER",
    "PG_DEPTH_ANNOTATION_IN_BENCHMARK",
    "PG_AGENTIC_SEARCH_IN_BENCHMARK",
    "PG_NLI_IN_BENCHMARK",
    "PG_ENABLE_TOOL_TRACKER",
    # I-ready-004 (#1078): finding-dedup must be ON for Gate-B — OFF wastes the budget on near-dups.
    # PG_CAPPED_FINDING_DEDUP is NO LONGER required-truthy: I-arch-007 #1264 sets it 0 (dormant-cap
    # cleanup, ZERO cap per §-1.3); a required-truthy flag set to 0 in the slate would fail the preflight.
    # The pool is consolidated keep-all (CONSOLIDATE-DON'T-DROP); the cap is GONE, not merely bypassed.
    "PG_USE_FINDING_DEDUP",
    # I-ready-016b (#1097): the 3 readiness faithfulness layers MUST be on for Gate-B — each only ADDS a
    # check (safety-refusal classifier / NLI semantic-conflict detection / table-cell numeric verify), so
    # OFF is a silent faithfulness downgrade. Force-on in run_gate_b_query; fail closed here if any is off.
    "PG_USE_SAFETY_REFUSAL",
    "PG_SWEEP_NLI_CONFLICT",
    "PG_SWEEP_TABLE_CELL_VERIFY",
    # I-ready-017 FX-03 (#1107): cited-span windowing on the authoritative 4-role seam — OFF is the
    # BUG-02 whole-doc out-of-span false-accept. Fail closed if it is not active for a paid run.
    "PG_GATE_B_CITED_SPAN",
    # I-perm-022 (#1214): LIGATURE-ONLY cited-span normalization on the same 4-role seam — OFF leaves a
    # PDF-extraction ligature to produce false-negative [confidence:low] on a genuinely-supported atom.
    # Fail closed if not active for a paid run (recovers TPs only; no word-boundary change; gate untouched).
    "PG_GATE_B_SPAN_NORMALIZE",
    # I-ready-017 CANARY-01 (#1108): the behavioral pre-spend canary must be ON for a paid run — OFF
    # would let a dead-discovery / structured-output-404 run go green (the drb_72 failure).
    "PG_BEHAVIORAL_CANARY",
    # I-cred-013 (#1163): the super-heavy behavioral preflight must be ON for a paid beat-both run — OFF
    # drops to the lighter canary alone and lets a dead verifier/STORM/credibility/browser tier or a
    # resurfaced false alarm ship a false-green paid run. Fail closed if it is not active.
    "PG_SUPER_HEAVY_PREFLIGHT",
    # I-ready-017 FX-14 (#1129): custody-lane honesty marker required — otherwise an explicit
    # PG_CUSTODY_LANE_MARKER=0 survives the slate setdefault (the I-cap-005 P1-1 pattern) and the paid
    # run silently writes empty v29/m44 custody telemetry with no not_applicable disambiguation.
    "PG_CUSTODY_LANE_MARKER",
    # I-ready-017 FL-05b (#1137): the run-health backstop must be ON for a paid run — OFF lets a
    # silently-degraded discovery (force-enabled STORM/agentic that did not fire, e.g. chromium missing
    # on the VM — the 2026-06-05 drb_72 smoke) ship as success. Fail closed if it is not active.
    "PG_RUN_HEALTH_GATE",
    # I-arch-011 (#1268): the COMPOSITION rebuild's feature flags must be ON for a paid Gate-B run —
    # OFF silently renders the OLD composition (no STORM outline scaffold / no keep-all basket render /
    # no per-basket verified-compose / no abstract+conclusion), wasting the run on the pre-rebuild
    # behaviour. Force-ON above; fail the run closed here if a stray operator =0 left any off.
    "PG_STORM_OUTLINE_SECTIONS",
    "PG_BASKET_CORROBORATION_RENDER",
    "PG_VERIFIED_COMPOSE",
    "PG_SYNTHESIS_ABSTRACT_CONCLUSION",
    # I-cred-006b (#1170): the weighted-corpus gate must be ON for the beat-both run — OFF restores the
    # §-1.1-banned tier-count / material-deviation corpus REFUSAL that aborted the drb_72 dry-run
    # (abort_corpus_approval_denied) on a tier-skewed-but-legitimate ECONOMICS corpus. Fail closed if it
    # is not active so a tier-mix refusal can never silently reach the paid run.
    "PG_SWEEP_WEIGHTED_CORPUS_GATE",
    # I-perm-000 permanent-fix (#1194): the keystone always-release + the numeric sanitizer + the
    # are DEFAULT OFF; required here so the preflight FAILS CLOSED if either is off, i.e. the paid
    # run can NEVER silently revert to the pre-fix withhold / DOI-cruft / literal-token behaviour.
    # (Selection-scale #1197 is deliberately NOT required — it stays flag-OFF until I-perm-007 grows
    # a real pool.)
    "PG_ALWAYS_RELEASE",
    "PG_SWEEP_NUMERIC_SANITIZER",
    "PG_SWEEP_SEMANTIC_CONTRAINDICATION",
    "PG_SPAN_RESOLVER",
    # I-perm-016 (#1209): the map-reduce evidence distiller must be ON for the
    # paid beat-both run — OFF silently restores the single-pass raw-quote
    # generation path the distiller was built to replace. Fail closed if it is
    # not active so a stray operator =0 can never reach the paid run.
    "PG_SECTION_DISTILL",
    # I-arch-005 PREFLIGHT FIX (#1257): B4 + B6/B8/B12 activations must be ON for the paid run — OFF
    # leaves B4 on the legacy fixed-top-K rerank and the B6/B8 keystone basket render + B12 credibility
    # label/guard DARK (the pre-run dual-audit NO-GO). Boolean flags -> safe in this truthy-required tuple.
    # (PG_RELEVANCE_SCORER is a string value -> asserted separately below, not here.)
    "PG_RETRIEVAL_RELEVANCE_GATE",
    "PG_SWEEP_CREDIBILITY_REDESIGN",
    # I-arch-007 ITEM 2 (#1264) CHOKE-FIX: the weighted unbound-SUPPORTS enrichment is the surface
    # that lifts the 485->~13 breadth collapse — OFF leaves the 5-entity contract funnel intact and
    # the ~437 span-verified unbound sources are never offered a citing slot. Fail CLOSED if it is
    # not active for a paid run so the funnel can never silently reach the benchmark. It reads the
    # credibility baskets, so PG_SWEEP_CREDIBILITY_REDESIGN above is its hard dependency.
    # FAITHFULNESS-NEUTRAL: every surfaced source re-passes the same strict_verify + section floor.
    "PG_BREADTH_ENRICHMENT_ENABLED",
)

# Codex diff-gate I-cap-005 P1-2: the minimum EFFECTIVE per-run budget cap. PG_MAX_COST_PER_RUN is an
# import-time constant in openrouter_client (cached at $10 default before Gate-B's slate runs), so the
# slate ALSO programmatically syncs it via set_max_cost_per_run(); the preflight then validates the live
# value via get_max_cost_per_run() so a stale-$10 cap cannot silently abort a full-depth paid run.
_BENCHMARK_MIN_COST_CAP_USD = 20.0

# Codex diff-gate iter-2: feature flags FORCED ON by the slate (a benchmark feature silently off via a
# conservative .env value is a capability downgrade). Everything else in the slate is a numeric FLOOR.
_BENCHMARK_FORCE_ON_FLAGS = frozenset({
    "PG_STORM_ENABLED_IN_BENCHMARK",
    "PG_SWEEP_EVIDENCE_DEEPENER",
    "PG_ENABLE_TOOL_TRACKER",
    # I-ready-002 (#1071) P0: binding verifier mode is non-numeric ("enforce") — force-set it directly
    # (the numeric-floor path would crash on float("enforce")). FORCE-ON keeps a benchmark from running
    # with the binding faithfulness verifier degraded. PG_VERIFICATION_MODE is intentionally NOT here
    # (Codex iter-1 P1: it enables Phase 0b rescue widening, out of scope).
    "PG_STRICT_VERIFY_ENTAILMENT",
    "PG_MAX_JUDGE_ERROR_RATE",
    # I-ready-004 (#1078): finding-dedup flag + the FLOAT relevance floor. Force-SET directly (string)
    # — the numeric FLOOR path int()-coerces, which would turn PG_RELEVANCE_FLOOR=0.30 into 0 and then
    # fail parse_relevance_floor (Codex brief P1-2). PG_RELEVANCE_FLOOR is validated as a float in (0,1]
    # in preflight_full_capability; PG_USE_FINDING_DEDUP is required in _BENCHMARK_PREFLIGHT_REQUIRED_FLAGS.
    # I-arch-007 #1264: PG_CAPPED_FINDING_DEDUP is NO LONGER force-ON — it is now force-EXACT to "0"
    # (dormant-cap cleanup, ZERO cap per §-1.3); see _BENCHMARK_FORCE_EXACT_FLAGS below.
    "PG_USE_FINDING_DEDUP",
    "PG_RELEVANCE_FLOOR",
    # I-arch-005 PREFLIGHT FIX (#1257): force-on the I-arch-005 activations the pre-run dual-audit found
    # dead-by-default on the benchmark — B4 relevance-gate, B6/B8+B12 credibility redesign, B16 redaction
    # kill-switch. All verified faithfulness-safe; OFF is a silent capability/visibility downgrade.
    "PG_RETRIEVAL_RELEVANCE_GATE",
    "PG_SWEEP_CREDIBILITY_REDESIGN",
    "PG_REDACT_HELD_UNSUPPORTED",
    # I-arch-007 ITEM 2 (#1264): force-on the weighted unbound-SUPPORTS enrichment so a stray operator
    # =0 cannot silently keep the 5-entity contract funnel that dropped ~437 verified sources. Depends
    # on PG_SWEEP_CREDIBILITY_REDESIGN (the baskets it reads). Faithfulness-neutral (strict_verify gates).
    "PG_BREADTH_ENRICHMENT_ENABLED",
    # I-arch-011 (#1268): force-on the COMPOSITION rebuild's default-OFF feature flags so a paid Gate-B run
    # actually EXERCISES the rebuild — else it renders the OLD composition (the "committed but not wired
    # into Gate-B" silent downgrade the I-arch-005 audit hit). PR-a STORM scaffold / PR-b basket-corroboration
    # render / PR-c per-basket verified-compose (+ verbatim K-span fallback) / PR-d verbatim abstract+conclusion.
    # Faithfulness-SAFE: strict_verify + the I-arch-010 tail engine UNTOUCHED. Each is also required-truthy in
    # _BENCHMARK_PREFLIGHT_REQUIRED_FLAGS so a stray operator =0 fails the run closed before spend.
    "PG_STORM_OUTLINE_SECTIONS",
    "PG_BASKET_CORROBORATION_RENDER",
    "PG_VERIFIED_COMPOSE",
    "PG_SYNTHESIS_ABSTRACT_CONCLUSION",
    # I-arch-007 ITEM 6 (#1264): force-on the A15 resume FETCH-SHELL re-fetch so an operator =0 cannot
    # survive the setdefault slate and silently let a --resume reload empty-shell anchors untouched (the
    # Q90 over-drop). Faithfulness-safe — re-fetches real content for the INPUT; touches no gate.
    "PG_RESUME_REFETCH_DEGRADED",
    # I-ready-017 FX-03 (#1107): force-on the cited-span windowing so an explicit operator =0 cannot
    # survive the setdefault slate and silently restore the whole-doc out-of-span false-accept.
    "PG_GATE_B_CITED_SPAN",
    # I-perm-022 (#1214): force-on the LIGATURE-ONLY cited-span normalization so an operator =0 cannot
    # survive the slate and silently leave a PDF-extraction ligature to produce false-negative
    # [confidence:low]. Recovers TPs only; no word-boundary change; ZERO digit modification; gate untouched.
    "PG_GATE_B_SPAN_NORMALIZE",
    # I-perm-024 (#1216): force-on the extended beat-both scorer metrics so a nonstandard operator
    # value (e.g. "2") cannot survive the setdefault slate and leave the archived scorecard without
    # the extended block (Codex diff-gate iter-4 P2). Measurement-only; no faithfulness path.
    "PG_BENCH_EXTENDED_METRICS",
    # I-perm-021 (#1213): force-on the RequiredEntityLedger so an operator =0 cannot survive the
    # slate and silently drop the honest "Coverage gaps" disclosure. Inclusion+disclosure only;
    # fail-soft; touches no gate. (NOT preflight-required: a missing audit on a non-4-role path is
    # a graceful no-op, never a fail-closed abort.)
    "PG_REQUIRED_ENTITY_LEDGER",
    # I-ready-017 CANARY-01 (#1108): force-on the behavioral pre-spend canary so an operator =0 cannot
    # survive the slate and let a dead-discovery run go green.
    "PG_BEHAVIORAL_CANARY",
    # I-cred-013 (#1163): force-on the super-heavy behavioral preflight so an operator =0 cannot survive
    # the slate and silently drop the paid run back to the lighter canary alone.
    "PG_SUPER_HEAVY_PREFLIGHT",
    # I-ready-017 FL-05b (#1137): force-on the run-health backstop so an explicit operator
    # PG_RUN_HEALTH_GATE=0 cannot survive the setdefault slate and silently restore the
    # ship-green-on-degraded-discovery behavior (the I-cap-005 P1-1 force-on pattern).
    "PG_RUN_HEALTH_GATE",
    # I-cred-006b (#1170): force-on the weighted-corpus gate so an explicit operator
    # PG_SWEEP_WEIGHTED_CORPUS_GATE=0 cannot survive the setdefault slate and silently restore the
    # §-1.1-banned tier-count corpus REFUSAL on the paid beat-both run (the I-cap-005 P1-1 pattern).
    "PG_SWEEP_WEIGHTED_CORPUS_GATE",
    # I-beatboth-fix-000 (#1171): force-on the two breadth feature flags so an explicit operator =0
    # cannot survive the setdefault slate and silently restore the breadth-collapse behaviour.
    # BB-002: keep Serper offset-paging past short pages (else the de-facto 10/query ceiling returns).
    "PG_SERPER_STOP_ON_ZERO_NEW",
    # BB-006: ingest the STORM interview-search-result URLs as URL-only seed candidates.
    "PG_STORM_INGEST_WEB_RESULTS",
    # I-perm-000 (#1194): force-on the ready permanent-fix flags so an explicit operator =0 cannot
    # survive the setdefault slate and silently revert to the pre-fix withhold / DOI-cruft /
    # literal-contraindicated behaviour. (PG_SWEEP_SELECTION_SCALE stays OFF until I-perm-007 grows
    # a real pool.)
    "PG_ALWAYS_RELEASE",
    "PG_SWEEP_NUMERIC_SANITIZER",
    "PG_SWEEP_SEMANTIC_CONTRAINDICATION",
    "PG_SPAN_RESOLVER",
    # I-perm-011 (#1205): force-on the max-over-subqueries relevance floor (exact
    # "1", not the numeric-floor path which would mangle a non-"1" string the same
    # way it would PG_RELEVANCE_FLOOR). The lift is CONFINED to the relevance-floor
    # selection path (the Gate-B path: PG_USE_FINDING_DEDUP + PG_RELEVANCE_FLOOR are
    # both on here), where it is MONOTONIC-UP (keeps a SUPERSET; faithfulness gates
    # untouched), so forcing it on can only OPEN the over-aggressive floor that shed
    # 74 on-topic T1 rows on drb_76 — never tighten it. (It does NOT apply to the
    # tier-balanced truncating path, where a score lift could reorder top-N.) NOT
    # added to _BENCHMARK_PREFLIGHT_REQUIRED_FLAGS (no fail-closed gate): a newly
    # introduced selection fix, kept active-by-slate but not yet a mandatory paid-
    # run precondition (the I-perm-003 selection-scale stance).
    "PG_SELECT_SUBQUERY_FLOOR",
    # I-perm-016 (#1209): force-on the map-reduce evidence distiller so an
    # explicit operator PG_SECTION_DISTILL=0 cannot survive the setdefault slate
    # and silently restore the single-pass raw-quote generation path on the paid
    # beat-both run (the I-cap-005 P1-1 force-on pattern).
    "PG_SECTION_DISTILL",
    # I-perm-023 (#1215): force-on the constrained-greedy diversity pass so a stray operator =0
    # cannot drop the anti-monoculture forward guard on the paid run. NOT preflight-required (a
    # no-op until the pool exceeds the cap; never a fail-closed precondition — the I-perm-003 stance).
    "PG_SELECT_CONSTRAINED_GREEDY",
    # I-arch-007 (#1264): force-on the three boolean death-forensic flags so a stray operator =0 cannot
    # survive the slate and silently restore a death mode. ITEM 4 (sentinel transport degrade — else one
    # blip zeros the D8 seam), ITEM 6 (trafilatura subprocess containment — else an uncatchable libxml2
    # SIGSEGV silently kills the sweep). All FAITHFULNESS-NEUTRAL per the consolidated plan §9. ITEM 6
    # was previously a run_gate_b_query setdefault (an operator override could leave containment OFF) —
    # promoted to a force-ON slate pin.
    # NOTE: ITEM 5 (PG_RESUME_REUSE_POSTGEN) is INTENTIONALLY NOT force-on'd here while ITEM 5a (the
    # generator-side cached-draft hook) is deferred — force-on would hard-fail every --resume instead of
    # gracefully re-generating from corpus_snapshot (Codex build-gate iter-1 P1). See the slate comment
    # above. Re-add this pin in the same PR that lands the ITEM 5a hook + the corpus-identity guard.
    "PG_SENTINEL_TRANSPORT_DEGRADE",
    "PG_TRAFILATURA_SUBPROCESS",
})

# Flags/modes that the benchmark slate force-sets to a specific value that is
# not "on". Kept separate from _BENCHMARK_FORCE_ON_FLAGS so tests and comments
# around capability-enabling flags keep their original meaning.
_BENCHMARK_FORCE_EXACT_FLAGS = frozenset({
    "PG_SWEEP_ANALYST_SYNTHESIS",
    # I-arch-005 PREFLIGHT FIX (#1257): B1 selects its scorer by a STRING value, not a boolean — force-EXACT
    # to 'semantic_v2' (the numeric FLOOR path would crash on float('semantic_v2')) so an .env='lexical'
    # cannot silently revert B1 to the legacy lexical scorer + bypass the restored relevance filter.
    "PG_RELEVANCE_SCORER",
    # I-ready-017 FX-03 (#1107) Codex iter-2 P1: the cited-span WINDOW SIZE must be FORCE-SET to the
    # 400-byte policy, not a setdefault floor. Otherwise an operator/.env PG_GATE_B_SPAN_WINDOW_BYTES=
    # 999999 survives the slate, the PG_GATE_B_CITED_SPAN preflight still passes, and _cited_window_text
    # expands to effectively the whole record — re-opening BUG-02 whole-doc evidence with the flag ON.
    "PG_GATE_B_SPAN_WINDOW_BYTES",
    # I-beatboth-fix-000 (#1171): these three are STRING- or sub-1-FLOAT-valued and MUST be force-EXACT
    # — the numeric FLOOR path (str(int(max(...)))) would int()-truncate PG_AMPLIFIER_SCOPE_FLOOR=0.08
    # to "0" (SILENTLY DISABLING the scope gate — sim>=0 always true) and crash on
    # float("containment") / float("research@..."). Force-exact sets the literal slate value.
    # BB-001: the researched containment-scale floor (0.08) + the containment similarity measure.
    "PG_AMPLIFIER_SCOPE_FLOOR",
    "PG_SCOPE_SIM_MEASURE",
    # BB-007: the real Unpaywall contact email (placeholder => resolver fails loud + no-ops).
    "PG_UNPAYWALL_EMAIL",
    # I-perm-004 #1180: the empirically-picked widening-aware entailment prompt variant (widen_c).
    # Force-exact so a stray PG_ENTAILMENT_PROMPT_VARIANT=baseline cannot silently revert the fix.
    "PG_ENTAILMENT_PROMPT_VARIANT",
    # F03 (A3): the verified-section-FRACTION floor is a FLOAT (0.4) — force-EXACT (the int FLOOR
    # path would coerce 0.4 -> 0 and silently disable the coverage-honesty gate, the PG_RELEVANCE_FLOOR
    # gotcha). A stray operator PG_MIN_VERIFIED_SECTION_FRACTION=0 must not survive the slate and let a
    # mostly-gap clinical report ship GREEN. Validated as a float in (0,1] in preflight_full_capability.
    "PG_MIN_VERIFIED_SECTION_FRACTION",
    # I-arch-007 (#1264) ITEM 1 + 1b — the credibility-pass wall/inflight PAIR. Force-EXACT (NOT the int
    # FLOOR path): the wall is a FLOAT-seconds value (1800) and the pair MUST stay pinned TOGETHER so the
    # sizing invariant (a healthy ~600-member pass completes within the wall) holds — a floor could leave
    # the wall slate value while an operator raised inflight (or vice versa), breaking the pair. Force the
    # chosen pair exactly so the pass both completes-when-healthy and degrades-not-hangs when unhealthy.
    "PG_CREDIBILITY_PASS_WALL_S",
    "PG_CREDIBILITY_PASS_MAX_INFLIGHT",
    # I-arch-007 #1264 PREFLIGHT RE-GO: the two per-call total-deadline walls (the residual trickle-hang
    # fix). Force-EXACT to "300" — these are wall-SECONDS, not capability floors (the int-FLOOR path's
    # max() is meaningless for a transport wall; a stray operator value must not raise OR lower them off
    # the chosen pair). 300s clears the longest HEALTHY verifier call (~6-40s) with wide margin; only a
    # trickle-hang trips it. TRANSPORT-ONLY + faithfulness-neutral (the fail-closed sentinel on exhaustion
    # is the SAME verdict the caller already handles).
    "PG_CREDIBILITY_JUDGE_TOTAL_S",
    "PG_ROLE_TRANSPORT_TOTAL_S",
    # I-arch-011 (verify-speed): the judge provider-rotation flag. Force-EXACT "1" so a stray operator =0
    # cannot silently restore the single-host z-ai blank-storm (which DROPS verified sentences in enforce
    # mode -> breadth collapse). Faithfulness-neutral-to-improving (same glm-5.1 model, next healthy host).
    "PG_JUDGE_PROVIDER_ROTATE",
    # I-arch-011 FIX-C (Codex P2): force the parallel-verify worker count EXACTLY to the slate value (16)
    # so a stray operator/.env PG_PARALLEL_VERIFY can neither exceed the intended 16-worker cap nor
    # silently revert to serial (=1, the bug that froze run #6). Concurrency knob only; verdicts unchanged.
    "PG_PARALLEL_VERIFY",
    # I-arch-007 #1264 DORMANT-CAP CLEANUP: pin both number-forcing caps EXACTLY OFF ("0") so a stray
    # operator/.env value can never silently re-enable them (operator: ZERO cap; §-1.3 BANNED bolt-ons).
    # PG_CAPPED_FINDING_DEDUP=0 removes the re-cap-to-max_ev (verified the ONLY consumer is the two
    # run_honest_sweep_r3 re-cap sites, both `and _capped_dedup`-gated); PG_SPAN_PER_SOURCE_CITE_CAP=0 is
    # the fact_dedup no-op default made explicit. Both faithfulness-neutral (a cap only ever DROPPED).
    "PG_CAPPED_FINDING_DEDUP",
    "PG_SPAN_PER_SOURCE_CITE_CAP",
})

# I-ready-017 FX-03 (#1107) Codex iter-2 P1: hard CEILING on the cited-span window (defense-in-depth on
# top of the force-exact above). The preflight fails closed if the EFFECTIVE window exceeds this, so a
# whole-record-sized window can never reach a paid Gate-B run even if the slate value is ever changed.
_BENCHMARK_SPAN_WINDOW_MAX_BYTES = 2000

_BENCHMARK_PREFLIGHT_REQUIRED_OFF_FLAGS = (
    "PG_SWEEP_ANALYST_SYNTHESIS",
)

# I-ready-002 (#1071) P0: env modes the preflight MUST see at "enforce" — the binding faithfulness gate
# is degraded (entailment not binding / judge_error fails open) at any other value. PG_VERIFICATION_MODE
# is NOT required here (rescue widening is out of scope; judge_error fail-closed keys on the entailment mode).
_BENCHMARK_PREFLIGHT_ENFORCE_MODES = ("PG_STRICT_VERIFY_ENTAILMENT",)

# BB5-C06 (#1178): entity types that KEEP the OA full-text path even under PG_FRAME_PREFER_ABSTRACT.
# frame_fetcher's default `_FULLTEXT_ENTITY_TYPES` is trial/review-only (pivotal_trial,clinical_trial,
# rct,systematic_review,meta_analysis), so under prefer-abstract EVERY narrative / source-critical entity
# (economic working paper, policy/CBO report, court decision, statute, regulatory label, mechanism study,
# cohort study, technical standard) skipped its OA full text and read only the ~500-char abstract
# (`skipped:prefer_abstract` in run 5; e.g. drb_72 frey_osborne OA full text on the Oxford repo was
# skipped). The substantive claims of those entities live in the BODY, not the abstract — so the benchmark
# must never skip an OA full text such an entity needs. We BROADEN the set to the full distinct entity-type
# inventory of the locked scope templates that need full text (verified via
# `grep "type: " config/scope_templates/*.yaml`). The clinical full-text types (already in the default) are
# RE-INCLUDED because PG_FRAME_FULLTEXT_ENTITY_TYPES replaces the whole value — dropping them would regress
# the M-66b-T clinical trial-roster path. prefer-abstract STAYS on (the clean deterministic abstract is the
# right source for the entities NOT in this set); this only stops the full-text SKIP for entities that need it.
_BENCHMARK_FULLTEXT_ENTITY_TYPES = ",".join((
    # original clinical full-text types (frame_fetcher default) — re-included; whole-value replacement
    "pivotal_trial", "clinical_trial", "rct", "systematic_review", "meta_analysis",
    # narrative / source-critical types that ALSO need full text (BB5-C06 broadening)
    "economic_report", "cbo_report", "policy_report", "mechanism_primary", "cohort_primary",
    "regulatory", "regulatory_ruling", "regulation", "court_decision", "legal_case", "statute",
    "technical_standard", "agency_report", "authoritative_source",
))

# Codex diff-gate iter-2 P1: import-time module CONSTANTS that the slate must have raised before the
# owning module was imported (env-only validation would miss a too-late slate). The preflight reads the
# LIVE constant and fails closed if it is below the floor. (module_path, attr, floor)
_BENCHMARK_IMPORT_TIME_CONSTANT_FLOORS = (
    ("src.polaris_graph.retrieval.live_retriever", "DEFAULT_CONTENT_MAX_CHARS", 50000),
    ("src.polaris_graph.retrieval.live_retriever", "DEFAULT_HTTP_TIMEOUT", 30),
    ("src.polaris_graph.state", "PG_AGENTIC_WEB_PER_ROUND", 10),
    # I-arch-004 A2 (#1248): GENERATOR_TIMEOUT_SECONDS is read at openrouter_client IMPORT (before the
    # slate runs), so a stale .env value freezes the module constant and the slate env cannot fix it.
    # Fail CLOSED if the live constant is below the data-grounded 6500s floor (the drb_72 generator
    # timeout class). Module default is now 6500, so an UNSET .env passes; an explicit low value fails.
    ("src.polaris_graph.llm.openrouter_client", "GENERATOR_TIMEOUT_SECONDS", 6500),
)
# Codex diff-gate iter-2 P1-1: additional CALL-TIME env floors that .env was silently winning over.
_BENCHMARK_EXTRA_ENV_FLOORS = {
    "PG_MOST_MAX_EVIDENCE": 800,
    # I-ready-001 (#1070) P0 + operator decision 2026-06-10: fail closed if the generator-facing pool cap
    # is below the FULL extracted set — catches any regression that re-introduces a pool throttle (the
    # original 98%-drop at 20, or the interim ~90%-drop at 150). The pool must equal the extracted corpus
    # so no source is dropped before per-section selection.
    "PG_LIVE_MAX_EV_TO_GEN": 1500,
    # I-arch-004 A2 (#1248): fail CLOSED if section sizing resolves below the data-grounded floor — this
    # is what makes a smoke value (e.g. PG_SECTION_WALLCLOCK_SECONDS=600, the drb_72 killer) impossible
    # to inherit into a paid run. The floor-slate raises them; these validate so a regression can't undo it.
    "PG_SECTION_MAX_TOKENS": 64000,
    "PG_GENERATOR_LLM_TIMEOUT_SECONDS": 6500,
    "PG_SECTION_WALLCLOCK_SECONDS": 9000,
    # I-arch-005 B20 PREFLIGHT FIX (#1257): the RUN-LEVEL wall-clock floor. The default
    # run_wall_clock_seconds (7200) is BELOW the 9000 section backstop = inverted ordering (a hang could
    # not be caught above the section level). Floor it ABOVE the section backstop so the hierarchy stays
    # per-call 6500 < section 9000 < run-wall 10800; the explicit ordering assertion in
    # preflight_full_capability fails closed if a future value inverts the hierarchy.
    "PG_RUN_WALL_CLOCK_SEC": 10800,
}


# I-arch-007 SMOKE scale-down. Applied (FORCE-SET, bypassing the ~1000-URL FLOOR) AFTER the
# full-capability slate ONLY when --smoke-scale is passed, so a PLUMBING smoke runs ~15-20 min and a
# HANG self-kills in ~40 min instead of 6h. INPUT BREADTH (the 5 fetch lanes + query-breadth counts)
# and timeout BACKSTOPS ONLY — the faithfulness engine (strict_verify / NLI / 4-role D8 / provenance),
# the A20 consolidate-keep-all funnel (PG_SWEEP_CREDIBILITY_REDESIGN), and the native 4-role seam are
# UNTOUCHED. A smaller HONEST run, never a relaxed one. Default OFF (the flag) => full run byte-identical.
# Values are small POSITIVE (never 0, which is "unlimited/disabled" for several lanes). Sum ≈ 45 URLs.
_SMOKE_SCALE_OVERRIDES: dict[str, str] = {
    # the 5 real fetch lanes (full sums to ~1000 URLs/query) -> a tiny smoke pool
    "PG_SWEEP_FETCH_CAP": "20",            # main Serper/S2/OpenAlex lane (was 740)
    "PG_SWEEP_DEEPENER_URL_CAP": "5",      # citation-snowball deepener (was 60)
    "PG_AGENTIC_BENCHMARK_URL_CAP": "5",   # agentic-discovery harvest (was 100)
    "PG_R6_EXPAND_FETCH_CAP": "5",         # R-6 completeness re-expansion (was 40)
    "PG_STORM_URL_FETCH_CAP": "10",        # STORM web-results seed lane (was 60)
    "PG_SWEEP_MAX_SERPER": "20",
    "PG_SWEEP_MAX_S2": "20",
    "PG_SERPER_TOTAL_PER_QUERY": "20",
    "PG_SERPER_MAX_PAGES": "1",
    # query-breadth COUNTS (how many search queries / STORM angles — not URLs)
    "PG_STORM_MAX_BENCHMARK_QUERIES": "4",   # was 30
    "PG_STORM_MIN_EFFECTIVE_QUERIES": "2",   # was 12 — lower the FLOOR too, else max(4)<min(12) -> abort_discovery_degraded
    "PG_MAX_SUBQUERIES": "4",                # was 15
    "PG_STORM_PERSPECTIVES_COUNT": "3",      # was 8
    "PG_STORM_ROUNDS_PER_PERSPECTIVE": "2",  # was 4
    # the SUPER-HEAVY pre-spend preflight requires discovery to return >= this many candidate URLs
    # (default 100); the smoke discovers ~20-40, so lower the floor or it aborts before the sweep.
    "PG_PREFLIGHT_MIN_BREADTH": "10",        # was 100
    # I-cred-008b basket-coverage gate scales with breadth; keep the super-heavy preflight's own
    # gates ON (faithfulness/behavioral) — only the BREADTH-count floor is lowered for the smoke.
    # timeout hierarchy — coherent per-call < generator < section < seam < run-wall, scaled so a HANG
    # is caught in ~40 min. A tiny smoke section finishes in minutes, well under these, so none
    # truncates a HEALTHY section (the arch-005 trap).
    "PG_VERIFIER_LLM_TIMEOUT_SECONDS": "300",    # per verifier LLM call (5 min)
    "PG_GENERATOR_LLM_TIMEOUT_SECONDS": "600",   # per generator call (10 min) — synced to live module below
    "PG_SECTION_WALLCLOCK_SECONDS": "900",       # per section (15 min)
    "PG_FOUR_ROLE_SEAM_TIMEOUT_SECONDS": "1800", # 4-role D8 seam (30 min)
    "PG_RUN_WALL_CLOCK_SEC": "2400",             # OUTER backstop (40 min)
    # modest cost cap for a smoke (synced to the live module below)
    "PG_MAX_COST_PER_RUN": "10",
    # CORRECTNESS (not scale-down): the GLM-5.1 Mirror blanks at xhigh effort and STALLS the 4-role
    # D8 seam (drb_72). Gate-B does NOT set this, so the smoke pins it to medium (returns content).
    "PG_FOUR_ROLE_REASONING_EFFORT": "medium",
    # FORENSIC: raw LLM-IO capture so the §-1.4 line-by-line monitor can read the real reasoning/IO.
    "PG_CAPTURE_RAW_LLM_IO": "1",
}


def apply_full_capability_benchmark_slate(smoke_scale: bool = False) -> None:
    """Make the full-capability slate AUTHORITATIVE over .env / conservative defaults (FLOOR semantics).

    ``smoke_scale=True`` (the --smoke-scale flag) force-applies ``_SMOKE_SCALE_OVERRIDES`` AFTER the
    floor loop (bypassing max()), shrinking INPUT breadth + timeout backstops for a ~15-20 min plumbing
    smoke. Faithfulness gates, the A20 funnel, and the 4-role seam are NOT touched. Default OFF.

    Codex diff-gate iter-2 P1-1: ``setdefault`` was WRONG. ``load_dotenv`` (openrouter_client import)
    puts .env values into ``os.environ`` BEFORE this slate runs, so a conservative .env default
    (e.g. ``PG_MOST_MAX_EVIDENCE=300``, ``PG_AGENTIC_WEB_PER_ROUND=6``) SURVIVED the setdefault and
    silently throttled the benchmark below the slate. Fix: every numeric key is a **FLOOR** —
    ``max(existing, slate)`` — so a HIGHER operator/.env value (more capability, e.g.
    ``PG_LLM_TIMEOUT_SECONDS=600`` in .env) is KEPT, but a LOWER default is RAISED to full capability.
    No silent downgrade in either direction (operator no-downgrade directive). Feature flags in
    ``_BENCHMARK_FORCE_ON_FLAGS`` are FORCED ON (a benchmark feature off is a capability downgrade).
    Exact-value flags in ``_BENCHMARK_FORCE_EXACT_FLAGS`` are forced to their slate value.

    Codex diff-gate iter-2 P1-2: MUST run BEFORE the sweep / live_retriever / state imports, which cache
    ``PG_LIVE_CONTENT_MAX`` / ``PG_LIVE_HTTP_TIMEOUT`` / ``PG_AGENTIC_WEB_PER_ROUND`` as import-time module
    constants. ``main()`` applies it before ``load_locked_questions()``; ``run_gate_b_query`` applies it
    before the sweep import. ``preflight_full_capability`` then validates the LIVE module constants so a
    too-late application is caught fail-closed.
    """
    for name, value in _FULL_CAPABILITY_BENCHMARK_SLATE.items():
        if name in _BENCHMARK_FORCE_ON_FLAGS or name in _BENCHMARK_FORCE_EXACT_FLAGS:
            os.environ[name] = value                       # force exact value — no silent benchmark drift
            continue
        try:
            current = float(os.environ.get(name, value))
        except (TypeError, ValueError):
            current = float(value)
        os.environ[name] = str(int(max(current, float(value))))   # FLOOR: raise-to-slate, keep-if-higher
    # I-arch-007 SMOKE: AFTER the full-capability floor, FORCE-SET the small-scale overrides (bypassing
    # the FLOOR's max()) so a --smoke-scale plumbing run is ~15-20 min. INPUT BREADTH + timeout BACKSTOPS
    # ONLY — no faithfulness gate / A20 funnel / 4-role seam touched. Placed BEFORE the two live-module
    # setters below so the smoke's small PG_MAX_COST_PER_RUN + PG_GENERATOR_LLM_TIMEOUT_SECONDS reach the
    # cached module globals (set_max_cost_per_run / set_generator_timeout_seconds) too, not just os.environ.
    if smoke_scale:
        for _smoke_name, _smoke_value in _SMOKE_SCALE_OVERRIDES.items():
            os.environ[_smoke_name] = _smoke_value
    # PG_MAX_COST_PER_RUN is an import-time constant in openrouter_client (cached before this slate via
    # the role import chain), so the floor above only fixes the env; sync the live module global too so
    # check_run_budget enforces the floored cap and run_one_query's manifest reads it (Codex iter-1 P1-2).
    from src.polaris_graph.llm.openrouter_client import set_max_cost_per_run
    set_max_cost_per_run(float(os.environ["PG_MAX_COST_PER_RUN"]))
    # I-arch-004 A2 (#1248) Codex A2-gate iter-1 P1: GENERATOR_TIMEOUT_SECONDS is ALSO an import-time
    # constant frozen before this slate runs; sync the live module global (same fix as the cost cap) so a
    # stale low PG_GENERATOR_LLM_TIMEOUT_SECONDS in .env cannot survive as the generator's ACTUAL timeout
    # while preflight's env check passes (the openrouter_client constant, not os.environ, is what _call uses).
    from src.polaris_graph.llm.openrouter_client import set_generator_timeout_seconds
    set_generator_timeout_seconds(int(os.environ["PG_GENERATOR_LLM_TIMEOUT_SECONDS"]))
    # I-arch-007: the 4-role OpenRouter transport freezes its reasoning effort + per-call timeout at
    # IMPORT (run_gate_b imports it before this slate runs), so a smoke override of
    # PG_FOUR_ROLE_REASONING_EFFORT / PG_VERIFIER_LLM_TIMEOUT_SECONDS would not reach the live 4-role
    # calls. Sync them to the module globals here (same fix class as the two setters above). Reading
    # os.environ means a full run with no override re-applies its own value (no behavior change).
    from src.polaris_graph.roles.openrouter_role_transport import (
        set_four_role_reasoning_effort,
        set_verifier_llm_timeout_seconds,
    )
    set_four_role_reasoning_effort(os.environ.get("PG_FOUR_ROLE_REASONING_EFFORT", "xhigh"))
    set_verifier_llm_timeout_seconds(int(os.environ.get("PG_VERIFIER_LLM_TIMEOUT_SECONDS", "900")))


def preflight_full_capability(smoke_scale: bool = False) -> None:
    """FAIL CLOSED if the effective benchmark config is below full capability or unobservable — so a
    silent throttle (the ~40-URL bug) can NEVER reach a paid run undetected. Raises RuntimeError.

    I-arch-007 ``smoke_scale=True`` (the --smoke-scale plumbing run) skips ONLY the CAPACITY floors —
    the breadth-knob floors, the min cost cap, the generator-timeout floor, and the extra-env capacity
    floors — because a smoke is DELIBERATELY below full breadth/cost. EVERY faithfulness check stays
    unconditional: the faithfulness slate, the section-fraction coverage floor, the required/required-off
    feature flags, the semantic_v2 relevance scorer, the cited-span window bound, the enforce-mode
    verifier, the row-cap ban, and the timeout-hierarchy ORDERING (which the smoke still satisfies).
    Default OFF = a full cert run validates every floor exactly as before."""
    # I-arch-004 F07 (#1249/#1252): fail-CLOSED faithfulness-slate assertion on the cert entry. The
    # Gate-B 4-role run goes through run_one_query (NOT run_honest_sweep_r3.main_async), so its
    # fail-closed preflight lives HERE. The slate above force-sets the binding-faithfulness env
    # (PG_BENCHMARK_STRICT_GATES / PG_SWEEP_NLI_CONFLICT / PG_STRICT_VERIFY_ENTAILMENT=enforce); this
    # REFUSES the paid run if an operator .env / mis-set left any of them advisory/misconfigured.
    from scripts.run_honest_sweep_r3 import (
        FaithfulnessSlatePreflightError as _FaithSlateErr,
        assert_faithfulness_slate_or_fail as _assert_faith_slate,
    )
    try:
        _assert_faith_slate()
    except _FaithSlateErr as _fse:
        raise RuntimeError(f"benchmark preflight FAILED: {_fse}") from _fse
    # F03 (A3): the verified-section-FRACTION coverage-honesty floor must be ACTIVE (a float in (0, 1])
    # for the cert run — a 0/absent value disables the gate and lets a mostly-gap clinical report ship
    # GREEN (the "built-it-then-left-it-off" failure). Checked FIRST (fail-fast on a faithfulness gate;
    # the slate force-sets it to 0.4). Code default is 0.0/inert for non-benchmark callers; this preflight
    # only runs on the Gate-B path.
    try:
        _msvf = float(os.getenv("PG_MIN_VERIFIED_SECTION_FRACTION", "0"))
    except ValueError:
        raise RuntimeError(
            "benchmark preflight FAILED: PG_MIN_VERIFIED_SECTION_FRACTION="
            f"{os.getenv('PG_MIN_VERIFIED_SECTION_FRACTION')!r} is not a float."
        )
    if not (0.0 < _msvf <= 1.0):
        raise RuntimeError(
            f"benchmark preflight FAILED: PG_MIN_VERIFIED_SECTION_FRACTION={_msvf} is not in (0, 1] — the "
            f"F03 coverage-honesty floor is DISABLED, so a mostly-gap-stubbed report would ship as success. "
            f"The slate force-sets it to 0.4; set it >0 (and <=1) before the run."
        )
    for name, floor in _BENCHMARK_PREFLIGHT_FLOORS.items():
        # mirror run_one_query's read of the real PG_SWEEP_* knob (defaults 12/12/40 if absent).
        _defaults = {"PG_SWEEP_FETCH_CAP": "40", "PG_SWEEP_MAX_SERPER": "12", "PG_SWEEP_MAX_S2": "12"}
        try:
            eff = int(os.getenv(name, _defaults.get(name, "0")))
        except ValueError:
            raise RuntimeError(f"benchmark preflight: {name}={os.getenv(name)!r} is not an int")
        if eff < floor and not smoke_scale:  # smoke: breadth floors are intentionally below full capability
            raise RuntimeError(
                f"benchmark preflight FAILED: {name}={eff} < full-capability floor {floor} — the run "
                f"would be SILENTLY THROTTLED (the ~40-URL bug). Set {name}>={floor} or fix the slate."
            )
    for flag in _BENCHMARK_PREFLIGHT_REQUIRED_FLAGS:
        if os.getenv(flag, "0").strip() not in ("1", "true", "True"):
            raise RuntimeError(
                f"benchmark preflight FAILED: {flag} is not enabled — the feature is dead-by-config "
                f"or its firing is unobservable (tracker off). Enable it before the run."
            )
    # I-arch-005 PREFLIGHT FIX (#1257): B1's relevance scorer is selected by a STRING value, not a
    # boolean, so it cannot ride the truthy-required loop above. Fail closed if it is not the embedding
    # scorer for a paid run — OFF/'lexical' silently reverts B1 to the legacy lexical scorer + bypasses
    # the restored relevance filter (keep-all). The slate force-sets it to 'semantic_v2' in run_gate_b_query.
    _scorer = os.getenv("PG_RELEVANCE_SCORER", "lexical").strip()
    if _scorer != "semantic_v2":
        raise RuntimeError(
            f"benchmark preflight FAILED: PG_RELEVANCE_SCORER={_scorer!r} is not 'semantic_v2' — the B1 "
            f"embedding-cosine relevance scorer + restored relevance filter are dead-by-config (legacy "
            f"lexical scorer runs instead). Set PG_RELEVANCE_SCORER=semantic_v2 before the run."
        )
    # I-ready-017 FX-03 (#1107) Codex iter-2 P1: the cited-span window must stay BOUNDED. An oversized
    # PG_GATE_B_SPAN_WINDOW_BYTES makes _cited_window_text expand to the whole direct_quote — BUG-02
    # whole-doc evidence WITH the cited-span flag on. The slate force-exacts it to the 400-byte policy;
    # this fails closed if it is ever outside (0, ceiling] (force-exact removed / slate value changed).
    if os.getenv("PG_GATE_B_CITED_SPAN", "0").strip() in ("1", "true", "True"):
        try:
            _win = int(os.getenv("PG_GATE_B_SPAN_WINDOW_BYTES", "400"))
        except ValueError:
            raise RuntimeError(
                "benchmark preflight FAILED: PG_GATE_B_SPAN_WINDOW_BYTES="
                f"{os.getenv('PG_GATE_B_SPAN_WINDOW_BYTES')!r} is not an int."
            )
        if _win <= 0 or _win > _BENCHMARK_SPAN_WINDOW_MAX_BYTES:
            raise RuntimeError(
                f"benchmark preflight FAILED: PG_GATE_B_SPAN_WINDOW_BYTES={_win} is outside "
                f"(0, {_BENCHMARK_SPAN_WINDOW_MAX_BYTES}] — an oversized cited-span window expands to the "
                f"whole record (BUG-02 whole-doc evidence with the cited-span flag on)."
            )
    for flag in _BENCHMARK_PREFLIGHT_REQUIRED_OFF_FLAGS:
        if os.getenv(flag, "1").strip() in ("1", "true", "True"):
            raise RuntimeError(
                f"benchmark preflight FAILED: {flag} is enabled — Gate-B report.md would include the "
                f"un-span-verified Analyst Synthesis layer. Set {flag}=0 for the verified-only benchmark."
            )
    # I-ready-002 (#1071) P0: the binding faithfulness verifier MUST be at "enforce" — otherwise the
    # entailment judge does not bind as a drop gate and/or a judge_error fails OPEN (unverified clinical
    # claims ship as "verified"). Fail closed before any spend.
    for mode_env in _BENCHMARK_PREFLIGHT_ENFORCE_MODES:
        if os.getenv(mode_env, "off").strip().lower() != "enforce":
            raise RuntimeError(
                f"benchmark preflight FAILED: {mode_env}={os.getenv(mode_env)!r} != 'enforce' — the "
                f"BINDING faithfulness verifier is degraded (entailment not binding or judge_error fails "
                f"OPEN). Set {mode_env}=enforce before the run."
            )
    # I-arch-005 B2/B3 (#1257): the per-section + outline ROW caps are now DISSOLVED into
    # character budgets by DEFAULT for every caller (multi_section_generator
    # `_section_budgets_enabled()`). The escape hatch PG_GEN_ROW_CAPS restores the legacy
    # 150/40 ROW caps — which would re-impose the WEIGHT-AND-CONSOLIDATE-violating row-count
    # truncation on the paid cert run (the §-1.3 day-waster). FAIL CLOSED if it is set on a
    # production run so a row cap can NEVER silently re-bind (the "built-it-then-left-it-off"
    # lesson, inverted: don't let an .env escape hatch silently turn the budget back OFF).
    if os.getenv("PG_GEN_ROW_CAPS", "").strip().lower() in ("1", "true", "yes", "on"):
        raise RuntimeError(
            "benchmark preflight FAILED: PG_GEN_ROW_CAPS is set — the legacy per-section / "
            "outline ROW caps (PG_MAX_EV_PER_SECTION / PG_OUTLINE_MAX_EV) would re-bind and "
            "silently truncate the evidence pool by row COUNT (the WEIGHT-AND-CONSOLIDATE DNA "
            "violation §-1.3 names). The character-budget path is the DEFAULT; unset "
            "PG_GEN_ROW_CAPS before the run."
        )

    # Codex diff-gate I-cap-005 P1-2: validate the EFFECTIVE (live) per-run budget cap — reads the
    # module global the guard actually enforces (synced by the slate via set_max_cost_per_run), NOT just
    # the env. Catches a stale-$10 cap that would silently abort a full-depth paid run mid-way.
    from src.polaris_graph.llm.openrouter_client import get_max_cost_per_run
    _eff_cap = get_max_cost_per_run()
    if _eff_cap < _BENCHMARK_MIN_COST_CAP_USD and not smoke_scale:
        raise RuntimeError(
            f"benchmark preflight FAILED: effective PG_MAX_COST_PER_RUN=${_eff_cap:.2f} < "
            f"${_BENCHMARK_MIN_COST_CAP_USD:.2f} floor — a full-depth run would abort early on the "
            f"stale default. The slate must call set_max_cost_per_run() before the guard enforces it."
        )
    # I-arch-004 A2 (#1248) Codex A2-gate iter-1 P1: validate the LIVE generator-timeout CONSTANT (synced
    # by the slate via set_generator_timeout_seconds), NOT just the env — a stale low value frozen at
    # openrouter_client import would otherwise pass the env-based _BENCHMARK_EXTRA_ENV_FLOORS check while
    # the generator still uses the frozen low timeout and dies mid-stream (the exact drb_72 class).
    from src.polaris_graph.llm.openrouter_client import get_generator_timeout_seconds
    _eff_gen_timeout = get_generator_timeout_seconds()
    _gen_timeout_floor = _BENCHMARK_EXTRA_ENV_FLOORS["PG_GENERATOR_LLM_TIMEOUT_SECONDS"]
    if _eff_gen_timeout < _gen_timeout_floor and not smoke_scale:
        raise RuntimeError(
            f"benchmark preflight FAILED: live GENERATOR_TIMEOUT_SECONDS={_eff_gen_timeout} < floor "
            f"{_gen_timeout_floor} — a stale PG_GENERATOR_LLM_TIMEOUT_SECONDS in .env froze the import-time "
            f"constant; the slate must call set_generator_timeout_seconds() to sync it before any spend."
        )
    # I-arch-005 B20 PREFLIGHT FIX (#1257): the timeout HIERARCHY must be strictly ordered
    # per-call < section-wall < run-wall, else a hang escapes the level meant to catch it (the drb_76
    # 3.5h hang had run-wall 3600 BELOW section 9000 = inverted, AND the paid Gate-B path had no run-level
    # asyncio.wait_for at all). Assert the ordering on the LIVE values so a future misconfig FAILS CLOSED
    # here, before any spend, rather than hanging silently on a paid run. run_gate_b_query now wraps
    # run_one_query in wait_for(PG_RUN_WALL_CLOCK_SEC) + the B11 timeout-finalizer (the missing guard).
    _eff_section_wall = int(os.getenv("PG_SECTION_WALLCLOCK_SECONDS", "0") or "0")
    _eff_run_wall = int(os.getenv("PG_RUN_WALL_CLOCK_SEC", "0") or "0")
    if not (_eff_gen_timeout < _eff_section_wall < _eff_run_wall):
        raise RuntimeError(
            "benchmark preflight FAILED: timeout hierarchy is not strictly ordered "
            f"per-call({_eff_gen_timeout}) < section-wall({_eff_section_wall}) < run-wall({_eff_run_wall}) "
            "— a hang would escape the level meant to catch it (the drb_76 inverted-ordering class). Set "
            "the slate so PG_GENERATOR_LLM_TIMEOUT_SECONDS < PG_SECTION_WALLCLOCK_SECONDS < "
            "PG_RUN_WALL_CLOCK_SEC before the run."
        )
    # Codex diff-gate iter-2 P1-1: extra CALL-TIME env floors that .env was silently winning over the
    # slate (e.g. PG_MOST_MAX_EVIDENCE=300 in .env survived the old setdefault). The floor-slate raised
    # them; validate so a regression cannot re-introduce the throttle.
    for name, floor in _BENCHMARK_EXTRA_ENV_FLOORS.items():
        try:
            eff = int(float(os.getenv(name, "0")))
        except ValueError:
            raise RuntimeError(f"benchmark preflight: {name}={os.getenv(name)!r} is not numeric")
        if eff < floor and not smoke_scale:  # smoke: capacity floors (evidence pool / section tokens / gen-timeout) intentionally below full
            raise RuntimeError(
                f"benchmark preflight FAILED: {name}={eff} < full-capability floor {floor} — .env was "
                f"silently throttling it. The floor-slate must raise it before the run."
            )
    # I-ready-004 (#1078) Codex brief P1-2: PG_RELEVANCE_FLOOR is a FLOAT in (0,1] (NOT an int floor — the
    # numeric-FLOOR slate path would coerce 0.30 -> 0). When capped finding-dedup is on (required above),
    # validate it via the canonical parser so a malformed/out-of-range value ("0", "1.5", "abc") fails
    # CLOSED before any spend rather than crashing mid-run or sending an unbounded pool. (None/empty ->
    # the parser's 0.30 default, which is valid.)
    if os.getenv("PG_CAPPED_FINDING_DEDUP", "0").strip() in ("1", "true", "True"):
        from src.polaris_graph.retrieval.evidence_selector import parse_relevance_floor
        try:
            parse_relevance_floor(os.getenv("PG_RELEVANCE_FLOOR"))
        except ValueError as _floor_exc:
            raise RuntimeError(
                f"benchmark preflight FAILED: {_floor_exc} — capped finding-dedup needs a parseable "
                f"PG_RELEVANCE_FLOOR in (0.0, 1.0] before the run."
            )
    # I-beatboth-fix-000 BB-001 (#1171): PG_AMPLIFIER_SCOPE_FLOOR is a sub-1 FLOAT — the numeric-FLOOR
    # slate path would int()-truncate 0.08 -> 0 and SILENTLY DISABLE the scope gate (sim >= 0 always
    # true). It rides _BENCHMARK_FORCE_EXACT_FLAGS, but validate the EFFECTIVE value here so a regression
    # (or a stray operator override that the force-exact ever stops covering) fails CLOSED rather than
    # shipping the gate disabled. Must be a float in (0.0, 1.0].
    try:
        _floor = float(os.getenv("PG_AMPLIFIER_SCOPE_FLOOR", "0.15"))
    except ValueError:
        raise RuntimeError(
            "benchmark preflight FAILED: PG_AMPLIFIER_SCOPE_FLOOR="
            f"{os.getenv('PG_AMPLIFIER_SCOPE_FLOOR')!r} is not a float."
        )
    if not (0.0 < _floor <= 1.0):
        raise RuntimeError(
            f"benchmark preflight FAILED: PG_AMPLIFIER_SCOPE_FLOOR={_floor} is outside (0.0, 1.0] — "
            f"a 0 floor DISABLES the scope gate (drops nothing); a >1 floor drops every query."
        )
    # I-beatboth-fix-000 BB-001 (#1171): the similarity MEASURE must be a recognised value — a typo'd
    # measure would otherwise fail loud only mid-run inside validate_amplified_queries. Validate the
    # canonical set here so it fails CLOSED before any spend.
    _measure = os.getenv("PG_SCOPE_SIM_MEASURE", "jaccard").strip().lower()
    if _measure not in ("jaccard", "containment"):
        raise RuntimeError(
            f"benchmark preflight FAILED: PG_SCOPE_SIM_MEASURE={_measure!r} is not a recognised "
            f"similarity measure (expected 'jaccard' or 'containment')."
        )


def preflight_import_time_constants() -> None:
    """FAIL CLOSED if an IMPORT-TIME module constant is below its full-capability floor — the regression
    guard for the import-order bug (Codex diff-gate iter-2 P1-2). ``live_retriever`` /``state`` cache
    ``PG_LIVE_CONTENT_MAX`` / ``PG_LIVE_HTTP_TIMEOUT`` / ``PG_AGENTIC_WEB_PER_ROUND`` at IMPORT, so reading
    os.getenv is NOT enough — if the slate ran AFTER the import the env is right but the constant is stale.

    Called ONLY on the REAL CLI path (``main()``), AFTER ``load_locked_questions()`` has done the import
    with the slate already applied — so it validates the production import order. It is intentionally NOT
    in ``preflight_full_capability`` (which tests call): in a pytest process those modules are pre-imported
    with defaults, which is a test artifact, not a production throttle."""
    import importlib
    for module_path, attr, floor in _BENCHMARK_IMPORT_TIME_CONSTANT_FLOORS:
        try:
            mod = importlib.import_module(module_path)
            eff = float(getattr(mod, attr))
        except (ImportError, AttributeError, TypeError, ValueError) as exc:
            raise RuntimeError(f"benchmark preflight: cannot read {module_path}.{attr}: {exc}")
        if eff < floor:
            raise RuntimeError(
                f"benchmark preflight FAILED: {module_path}.{attr}={eff:g} < full-capability floor "
                f"{floor} — the slate was applied AFTER that module was imported, so the import-time "
                f"constant is STALE. Apply the slate before that import (it runs before "
                f"load_locked_questions in main())."
            )


# I-ready-019 (#1146): EMPTY per the operator credibility-model directive (2026-06-07). FIX-JO
# (I-ready-017 #1100/#1134) originally placed drb_72_ai_labor here because that AI-labor LITERATURE
# REVIEW question's text says "only cites high-quality, English-language journal articles". The
# operator REVERSED that: "many things are not journal, but still credibility — mainstream news,
# gov, some credible sites; why you have tendency to make yourself into tunnel view." No benchmark
# question is journal-only. Credibility is multi-source and domain-aware (peer-reviewed journals +
# government statistics + working papers (NBER/IZA) + reputable institutes + quality news);
# faithfulness is enforced by the verify gates (strict_verify / 4-role D8 / provenance / two-family),
# NOT by source-type purity. The drb_72 paid re-run proved the harm: the GENERAL corpus was adequate
# ("adequacy=proceed uncovered=0"), but the journal-only distinct-journal COUNT floor (5<12 — itself a
# §-1.1-banned metadata-as-quality proxy) starved it and forced abort_corpus_inadequate.
# The NAMED-constant + apply_journal_only_for_slug() mechanism is KEPT but dormant (LAW VI): a future
# DELIBERATE, operator-approved journal-only question is re-enabled by appending its slug here (and
# giving its domain template a journal_only profile). journal_only_active() still requires BOTH this
# runtime flag AND the protocol field, so with an empty set nothing activates.
JOURNAL_ONLY_BENCHMARK_SLUGS: frozenset[str] = frozenset()


def apply_journal_only_for_slug(slug: str) -> bool:
    """DETERMINISTICALLY set/clear the journal_only runtime flag for ONE benchmark slug.

    Sets ``PG_SOURCE_RESTRICTION_JOURNAL_ONLY=1`` iff ``slug`` is a journal_only benchmark slug
    (``JOURNAL_ONLY_BENCHMARK_SLUGS``); otherwise it REMOVES the flag from the env so a value
    left over from a prior journal_only slug in the SAME process (e.g. the ``--all`` loop, or a
    conservative ``.env`` default) can NEVER carry into a non-journal slug. Returns True iff the
    flag was set ON for this slug.

    This is the per-question seam (mirrors how the slate is applied per ``run_gate_b_query``): it
    runs INSIDE ``run_gate_b_query`` so the flag is correct for exactly the question being run,
    NOT added to the always-on global ``_FULL_CAPABILITY_BENCHMARK_SLATE`` (which would blanket-
    activate journal_only for every workforce query and kill the generic T3 path). The downstream
    consumer (``run_honest_sweep_r3.run_one_query`` -> ``_jo_active`` -> ``journal_only_active``)
    reads ``JOURNAL_ONLY_FLAG`` from the env at run time AND requires the protocol's
    ``source_restriction: journal_only``, so setting it here before the ``run_one_query`` call is
    what makes journal_only fire for the journal-only slug only. Default non-journal runs are
    byte-identical (the flag is removed, not set).
    """
    if slug in JOURNAL_ONLY_BENCHMARK_SLUGS:
        os.environ[JOURNAL_ONLY_FLAG] = "1"
        return True
    os.environ.pop(JOURNAL_ONLY_FLAG, None)
    return False


# I-arch-007 ITEM 2 (#1264) CHOKE-FIX: the POST-RUN breadth-enrichment canary. The enrichment fix
# silently no-op'd in EVERY prior report (zero "appended weighted-enrichment section" log lines)
# because the call site only logged the success branch. This canary closes that hole at the
# benchmark boundary: after a SUCCESSFULLY-released run, it FAILS CLOSED if the rendered report.md
# does NOT contain the "Corroborated Weighted Findings" enrichment section with at least one cited
# source — i.e. the breadth surface silently emptied again. It is faithfulness-NEUTRAL: it READS the
# already-shipped report.md / manifest.json and asserts a breadth invariant; it never reads, alters,
# drops, or relabels any verified claim, evidence span, or gate verdict.
class BreadthEnrichmentCanaryError(RuntimeError):
    """The rendered report is missing the weighted-enrichment breadth surface on a released run."""


# Released statuses on which the enrichment MUST be present (the contract universe rendered, so the
# unbound-SUPPORTS basket should have been offered a section). A non-released abort (scope/corpus/
# safety) legitimately has no enrichment, so the canary does not apply.
_BREADTH_CANARY_RELEASED_STATUSES = frozenset({
    "success",
    "released_with_disclosed_gaps",
})

# Manifest signal that the advisory credibility pass DEGRADED (timeout / total judge failure under
# always-release) so it produced NO baskets. Codex P0 (choke-fix iter2): this is the EXACT choke the
# canary guards (no baskets -> empty enrichment), so it is NO LONGER a stand-down — it is read only to
# annotate the FAIL message with the degrade cause + remediation. The report still ships via
# always-release; the canary failing flags a choked datapoint to re-run (it never holds the report,
# never fabricates a section). A HEALTHY run with a MINOR per-source disclosed gap does not set this
# key and renders its enrichment, so it passes on the report-content check below.
_BREADTH_CANARY_CREDIBILITY_DEGRADE_KEYS = (
    "credibility_disclosed_gap",
)


def assert_breadth_enrichment_rendered(
    summary: Mapping[str, Any],
    *,
    smoke_scale: bool = False,
) -> str:
    """FAIL CLOSED if a released benchmark run dropped the weighted-enrichment breadth surface.

    Returns a one-line status string for logging:
      - ``"present"``  — the enrichment section rendered with >=1 IN-SECTION cited source (healthy).
      - ``"skip:<reason>"`` — the canary legitimately does not apply (non-released status, smoke
        scale, no run_dir, or no report.md artifact).

    Raises ``BreadthEnrichmentCanaryError`` when the run released a full contract report yet the
    enrichment section is absent OR its SECTION BODY carries no citation marker — i.e. the §-1.3
    breadth funnel silently reasserted. Codex P0 (choke-fix iter2): a credibility TOTAL-degrade is NO
    LONGER a stand-down — it is the exact choke this canary guards, so a degraded run that rendered no
    enrichment FAILS CLOSED (the report still ships via always-release; the canary is a benchmark-
    quality gate, never a report hold). Reads ONLY the shipped artifacts; mutates nothing;
    faithfulness-neutral.
    """
    from src.polaris_graph.generator.weighted_enrichment import _ENRICHMENT_TITLE

    status = str(summary.get("status", "") or "")
    if status not in _BREADTH_CANARY_RELEASED_STATUSES:
        return f"skip:status={status or '<none>'}"
    # I-arch-007: the small-scale plumbing smoke deliberately runs a thin pool — it is NOT a breadth
    # assertion surface, so the canary stands down (the full paid run is the breadth gate).
    if smoke_scale:
        return "skip:smoke_scale"

    run_dir_raw = summary.get("run_dir")
    if not run_dir_raw:
        return "skip:no_run_dir"
    run_dir = Path(str(run_dir_raw))

    # Codex P0 (choke-fix iter2): a disclosed credibility TOTAL-degrade (the advisory pass produced NO
    # baskets -> credibility_analysis is None -> the enrichment is EMPTY) is EXACTLY the choke this
    # canary exists to catch — NOT a legitimate stand-down. The prior code RETURNED skip on that signal,
    # so the canary green-lit the very silent no-op it guards (the operator's "fix that fails to wire").
    # We now read the manifest ONLY to build a diagnostic HINT for the failure message and let the
    # rendered report.md decide: a HEALTHY run (credibility completed, enrichment fired) renders the
    # section + in-section citations and PASSES even if it disclosed a MINOR per-source gap; a totally-
    # degraded run renders NO enrichment and FAILS CLOSED. The report still SHIPS via always-release —
    # this canary is a benchmark-quality gate (a choked datapoint must be re-run), never a report hold.
    manifest = summary.get("manifest")
    if not isinstance(manifest, dict):
        _manifest_path = run_dir / "manifest.json"
        if _manifest_path.is_file():
            try:
                manifest = json.loads(_manifest_path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                manifest = None
    _degrade_hint = ""
    if isinstance(manifest, dict):
        for _k in _BREADTH_CANARY_CREDIBILITY_DEGRADE_KEYS:
            if manifest.get(_k):
                _degrade_hint = (
                    f" [manifest discloses a credibility total-degrade via {_k!r}: the advisory "
                    "credibility pass did NOT complete, so the unbound-SUPPORTS basket could not be "
                    "computed — raise PG_CREDIBILITY_PASS_WALL_S and/or fix the judge transport "
                    "(PG_ROLE_ALLOW_FALLBACKS) and RE-RUN this datapoint]"
                )
                break
        if not _degrade_hint:
            _gaps = manifest.get("disclosed_gaps")
            if isinstance(_gaps, list) and any(
                ("credibility_pass_unavailable" in str(g))
                or ("breadth_enrichment_unavailable" in str(g))
                for g in _gaps
            ):
                _degrade_hint = (
                    " [disclosed_gaps records a credibility/breadth total-degrade: the advisory "
                    "credibility pass did NOT complete -> empty enrichment; raise "
                    "PG_CREDIBILITY_PASS_WALL_S and/or fix the judge transport and RE-RUN]"
                )

    report_path = run_dir / "report.md"
    if not report_path.is_file():
        # No report.md on a released status is its own failure surface elsewhere; the canary does not
        # invent a verdict here — it only asserts the enrichment WHEN a report exists.
        return "skip:no_report"
    body = report_path.read_text(encoding="utf-8", errors="replace")

    if _ENRICHMENT_TITLE not in body:
        raise BreadthEnrichmentCanaryError(
            f"breadth-enrichment canary FAILED for run_dir={run_dir}: the released report.md does "
            f"NOT contain the weighted-enrichment section ('{_ENRICHMENT_TITLE}'). The §-1.3 breadth "
            "funnel silently reasserted (the unbound-SUPPORTS basket was never surfaced). "
            "PG_BREADTH_ENRICHMENT_ENABLED is force-required for the benchmark; investigate the "
            f"[multi_section] I-arch-007 breadth log line for the empty-exit reason.{_degrade_hint}"
        )

    # The section is present — assert it carries >=1 cited source (a `[N]` numeric marker) WITHIN the
    # enrichment SECTION body. Codex P1 (choke-fix iter2): the prior heading-to-EOF scan let a HOLLOW
    # enrichment heading pass on the strength of a downstream References/Bibliography section's `[N]`
    # markers. Bound the slice at the NEXT markdown heading after the enrichment title (or EOF) so only
    # citations the section ITSELF renders satisfy the gate.
    import re as _re
    _idx = body.find(_ENRICHMENT_TITLE)
    _after_title = body[_idx + len(_ENRICHMENT_TITLE):]
    _next_heading = _re.search(r"(?m)^\s*#{1,6}\s", _after_title)
    _section_body = _after_title[: _next_heading.start()] if _next_heading else _after_title
    if not _re.search(r"\[\d+\]", _section_body):
        raise BreadthEnrichmentCanaryError(
            f"breadth-enrichment canary FAILED for run_dir={run_dir}: the weighted-enrichment "
            f"section ('{_ENRICHMENT_TITLE}') rendered but its SECTION BODY carries NO citation "
            "marker (a heading-only enrichment; a trailing bibliography no longer counts) — no "
            "unbound SUPPORTS source survived strict_verify into a cited slot. On a released "
            "full-contract run with a healthy credibility pass this is the silent breadth funnel; "
            f"investigate the [multi_section] I-arch-007 breadth log line "
            f"(candidates / below_floor / pool_absent).{_degrade_hint}"
        )
    return "present"


async def run_gate_b_query(
    q: dict,
    out_root: Path,
    *,
    transport: OpenRouterRoleTransport | OpenAICompatibleRoleTransport | None = None,
    d8_config_path: str | Path | None = None,
    query_index: int | None = None,
    query_total: int | None = None,
    resume: bool = False,
    smoke_scale: bool = False,
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
    # I-cap-005 (#1068) KEYSTONE: apply the full-capability slate BEFORE importing the sweep, so the
    # sweep's IMPORT-TIME module constants (content cap / timeouts / workers) also see the full values
    # — not just the call-time PG_SWEEP_* knobs. This is what makes a Gate-B run full-depth regardless
    # of the operator's shell env (the prior ~40-URL throttle was a missing/wrong-named slate).
    apply_full_capability_benchmark_slate(smoke_scale=smoke_scale)

    from scripts.run_honest_sweep_r3 import run_one_query

    enable_four_role_mode()
    # I-meta-007: enable the verifiable quantified-trade-off calculator for the
    # benchmark/paid run ONLY here (gate-B entry), never globally — so the Phase-7
    # Regime-C-verified quantified section actually fires on the paid run.
    os.environ["PG_ENABLE_QUANTIFIED_ANALYSIS"] = "1"
    # I-meta-008 (#1030): activate the contract-driven generation path ONLY for the
    # Gate-B benchmark (entry-scoped, never global — mirrors the line above). Without
    # PG_V30_PHASE2_ENABLED the pre-generation block at run_honest_sweep_r3.py:2779
    # (compile_frame -> fetch_compiled_frame -> compose_outline_from_contract) never
    # fires, so run 5 (a) missed every canonical journal the workforce.yaml contract
    # names (Acemoglu/Autor/Frey-Osborne/Brynjolfsson/Eloundou) and (b) fell back to the
    # clinical default section labels (Efficacy/Safety/Dose Response) instead of the
    # contract section_order (Foundational_Theory/Empirical_Displacement/Generative_AI_Evidence).
    # The three working V30 launchers (run_full_scale_v30_phase2.py, run_phase_g_full_scale.py,
    # run_m_live_1_smoke.py) set this PAIR + the OA-fetch enhancers; we mirror them.
    os.environ["PG_V30_PHASE2_ENABLED"] = "1"   # contract outline + canonical-entity grounding
    os.environ["PG_V30_ENABLED"] = "1"          # V30 Phase-1 coverage report + Methods disclosure
    # OA-abstract / full-text yield enhancers the working launchers pair with the V30 path; the
    # canonical journals are paywalled, so Unpaywall (OA PDF) + Trafilatura (extraction) raise the
    # span-verifiable abstract yield. `setdefault` so an explicit operator override still wins (LAW VI).
    os.environ.setdefault("PG_UNPAYWALL_ENABLED", "1")
    os.environ.setdefault("PG_TRAFILATURA_ENABLED", "1")
    # GH #1260: trafilatura runs libxml2 (a C extension) in a ThreadPoolExecutor
    # worker; a libxml2 SIGSEGV on a pathological doc is NOT a catchable Python
    # exception and kills the whole sweep silently (2 of 5 live runs died this
    # way). Turning the backend ON without ON-ing the subprocess containment
    # leaves the guard as an in-process size-gate only — the SIGSEGV stays
    # uncatchable. Pair the two flags here so the hard-killable child process
    # IS the libxml2 door on the paid run, making a crash a contained child
    # rc=139 the parent survives.
    # I-arch-007 (#1264) ITEM 6: FORCE this ON (was setdefault). The slate already force-pins it
    # (apply_full_capability_benchmark_slate runs first), but a setdefault here would let a stray
    # operator override leave containment OFF on the in-process direct-call path that does not go
    # through the slate. An uncatchable libxml2 SIGSEGV that silently kills the whole sweep is the
    # MODE-1 containment gap; force-ON makes the hard-killable subprocess the only libxml2 door on
    # EVERY benchmark path. FAITHFULNESS-NEUTRAL: fetch robustness only — never a gate verdict. A
    # crashed/OOM/SIGKILL child is recorded LOUD by safe_trafilatura_extract (rc!=0 -> regex fallback
    # + fetch-degraded), never a silent gap.
    os.environ["PG_TRAFILATURA_SUBPROCESS"] = "1"
    # #1034: paywalled-journal OA fetches are non-deterministic + noisy (Sci-Hub HTML / Jina
    # landing-page markdown / intermittent CrossRef abstract). For frame-contract grounding the
    # clean, deterministic abstract (CrossRef/OpenAlex) is the correct source — contract fields
    # are abstract-level claims. Prefer it over the scrape; setdefault keeps the operator override.
    os.environ.setdefault("PG_FRAME_PREFER_ABSTRACT", "1")
    # BB5-C06 (#1178): prefer-abstract is RIGHT for entities whose contract fields are abstract-level, but
    # it was ALSO skipping the OA full text of narrative / source-critical entities whose substantive claims
    # live in the body (economic/policy/mechanism/cohort/regulatory/legal). Broaden the keep-full-text set so
    # those entities keep the OA full-text path even under prefer-abstract — "never skip an OA full text an
    # entity needs". MUST be set before the lazy frame_fetcher import (run_honest_sweep_r3.py:4567, inside the
    # per-query V30 block) freezes `_FULLTEXT_ENTITY_TYPES` from this env — that import fires AFTER this line,
    # so this placement (next to PG_FRAME_PREFER_ABSTRACT, both before the per-query import) is effective.
    # setdefault keeps an explicit operator override (LAW VI).
    os.environ.setdefault("PG_FRAME_FULLTEXT_ENTITY_TYPES", _BENCHMARK_FULLTEXT_ENTITY_TYPES)
    os.environ.setdefault("PG_OPENALEX_FRAME_FALLBACK", "1")
    # I-cap-002 feature 2/4 (#1060): turn on the ADVISORY analytical-depth annotation for the
    # benchmark/paid run ONLY here (gate-B entry), never globally — so manifest['analytical_depth_
    # advisory'] + analytical_depth.json actually emit on the paid run instead of staying silent.
    # The annotation is non-gating + fail-open, so it can NEVER withhold release. setdefault keeps
    # the operator override (LAW VI); mirrors the PG_ENABLE_QUANTIFIED_ANALYSIS / PG_V30_* lines.
    os.environ["PG_DEPTH_ANNOTATION_IN_BENCHMARK"] = "1"   # force-on (Codex iter-2 P1-1: .env=0 must not win)
    # I-cap-002 feature 3/4 (#1060): turn on agentic URL-DISCOVERY for the benchmark/paid run ONLY here.
    # The agentic loop discovers additional URLs that are fetched VERBATIM via the same seed_only
    # chokepoint + strict_verify + 4-role (notebook/summaries never become evidence). Budget-bounded
    # (content reading forced off + conservative envelope) and fail-open. setdefault keeps the operator
    # override (LAW VI).
    os.environ["PG_AGENTIC_SEARCH_IN_BENCHMARK"] = "1"     # force-on (Codex iter-2 P1-1: .env=0 must not win)
    # I-cap-002 feature 4/4 (#1060) + I-cap-003 (#1066): turn on the ADDITIVE NLI entailment annotation
    # for the benchmark. NLI is the second validator path (catches qualitative-negation hallucinations
    # strict_verify's regex misses); ADVISORY only (4-role D8 stays the single gate). The scoring
    # backend is the frontier LLM entailment judge (PG_ENTAILMENT_MODEL, default gemma-4-31b via
    # OpenRouter, family-segregated) — NOT flan-t5/minicheck. We do NOT pin PG_ENTAILMENT_MODEL here:
    # pathB preflight requires PG_ENTAILMENT_MODEL == PG_EVALUATOR_MODEL and the default already
    # satisfies it. setdefault keeps the operator override (LAW VI).
    os.environ["PG_NLI_IN_BENCHMARK"] = "1"                # force-on (Codex iter-2 P1-1: .env=0 must not win)
    # I-ready-016b (#1097): activate the 3 readiness faithfulness layers for the benchmark. Each only ADDS
    # a layer (safety-refusal classifier / NLI semantic-conflict detection / table-cell numeric verify) — a
    # gate is only ever STRENGTHENED, never weakened. Force-on so a conservative .env=0 cannot silently
    # downgrade the run (operator no-downgrade directive); validated fail-closed by preflight below.
    os.environ["PG_USE_SAFETY_REFUSAL"] = "1"              # force-on (Codex iter-2 P1-1: .env=0 must not win)
    os.environ["PG_SWEEP_NLI_CONFLICT"] = "1"              # force-on (Codex iter-2 P1-1: .env=0 must not win)
    # I-arch-004 F07 (#1249/#1252): ARM the shared benchmark strict-gates master flag. It turns the
    # four fail-open run-sweep gates (#1235/#1238/#1226/#1237) LOUD AND arms the cross-document
    # conflict-judge fail-CLOSED hold (a judge error -> run holds, never the fail-open 'neutral' 0.0
    # that silently drops a possible real contradiction). Without this the strict slate is only
    # CHECKED by the F07 preflight, never SET — the spec says the benchmark slate SETS strict gates
    # ON. Force-on (an operator .env=0 must not silently downgrade the cert run); the F07 preflight in
    # run_honest_sweep_r3.main_async fails closed if any binding-faithfulness env is misconfigured.
    os.environ["PG_BENCHMARK_STRICT_GATES"] = "1"          # force-on (F07: arm strict faithfulness gates)
    os.environ["PG_SWEEP_TABLE_CELL_VERIFY"] = "1"         # force-on (Codex iter-2 P1-1: .env=0 must not win)
    # I-perm-016 (#1209) KEYSTONE: activate the map-reduce evidence distiller for
    # the benchmark/paid run ONLY here (gate-B entry), never globally. The
    # distiller MAP-validates every finding against the SAME production verifier
    # and the unchanged strict_verify re-checks the REDUCE output, so it only
    # TIGHTENS faithfulness. Force-on (Codex iter-2 P1-1: an operator .env=0 must
    # not win); preflight_full_capability below fails closed if it is off.
    os.environ["PG_SECTION_DISTILL"] = "1"                 # force-on (Codex iter-2 P1-1: .env=0 must not win)
    # I-arch-005 PREFLIGHT FIX (#1257): the B1/B4/B6-8/B12 activations + the B16 hardening pin are set by
    # the FULL-CAPABILITY SLATE (apply_full_capability_benchmark_slate, via _FULL_CAPABILITY_BENCHMARK_SLATE
    # + _BENCHMARK_FORCE_ON_FLAGS / _BENCHMARK_FORCE_EXACT_FLAGS), NOT hand-set here — so apply()-only
    # callers (preflight tests, super_heavy_preflight) get them too and stay consistent. See the slate dict.
    # I-ready-019 (#1146): journal_only is DISABLED for the whole benchmark (empty
    # JOURNAL_ONLY_BENCHMARK_SLUGS) per the operator credibility-model directive (2026-06-07). With an
    # empty set this call DETERMINISTICALLY CLEARS the runtime flag for every slug, so no question is
    # journal-only and the broad credibility corpus + general adequacy govern (the drb_72 re-run showed
    # the general adequacy returns "proceed"; the journal-only COUNT floor had wrongly aborted it). The
    # mechanism stays so a future operator-approved journal-only question just appends a slug above.
    apply_journal_only_for_slug(q["slug"])
    # I-cap-005 (#1068) KEYSTONE: FAIL CLOSED here — AFTER every cap+flag is applied, BEFORE a single
    # token is spent. If any effective retrieval cap is below the full-capability floor, or any required
    # feature flag / the tool tracker is off, this raises RuntimeError and the run aborts. A silent throttle
    # (the ~40-URL bug) can therefore NEVER reach a paid run undetected (operator no-downgrade directive).
    preflight_full_capability(smoke_scale=smoke_scale)
    if transport is not None:
        active_transport = transport               # offline/test: injected fake
    else:
        # LIVE run: fail-fast (BEFORE the sweep spends a token) if the ENV-gated transport
        # cannot resolve — openrouter: a pinned slug missing from the catalog; self_host: a
        # missing PG_<ROLE>_BASE_URL; either: a 4-role family collision.
        preflight_four_role_transport()
        # I-cred-013 (#1163): the SUPER-HEAVY behavioral pre-spend preflight. COMPOSES the CANARY-01
        # behavioral canary (#1108 — structured-output on the searcher/generator slug = the FX-01-keystone
        # 404 class + a 1-query live search >0 sources) with the heavy pre-beat-both checks: EVERY model
        # slug (generator + the 3 verifiers + the credibility judge when active) ALIVE in its production
        # call shape, STORM/discovery non-empty, host-local chromium present, and a RUNTIME re-assertion
        # of the 5 recurring false-alarm regression locks. FAIL CLOSED before any sweep spend. Live-path
        # only (transport injected = offline test, no real calls); gated by PG_SUPER_HEAVY_PREFLIGHT
        # (slate force-on + required). When PG_SUPER_HEAVY_PREFLIGHT is off, fall back to the CANARY-01
        # behavioral canary alone (byte-unchanged from #1108).
        if os.getenv("PG_SUPER_HEAVY_PREFLIGHT", "0").strip().lower() in ("1", "true"):
            from scripts.dr_benchmark.super_heavy_preflight import super_heavy_preflight
            await super_heavy_preflight()
        else:
            from scripts.dr_benchmark.pathB_run_gate import behavioral_canary
            await behavioral_canary()
        active_transport = build_gate_b_transport()
        # P2 (I-meta-007d): record the machine-readable stage marker so a future gate/manifest
        # reader can tell this benchmark OpenRouter run apart from the sovereign self-host path.
        write_four_role_stage_marker(out_root)
    builder = make_gate_b_input_builder(d8_config_path=d8_config_path)
    # I-arch-005 B20 PREFLIGHT FIX (#1257): wrap run_one_query in the RUN-LEVEL wall-clock guard. The
    # paid Gate-B path previously awaited run_one_query DIRECTLY with NO asyncio.wait_for, so a hang
    # anywhere inside it (a wedged fetch, a judge that never returns) = PERMANENT silence — run_one_query's
    # inner B11 `finally` (the finalizer) cannot fire on a hang. Port the proven main_async pattern
    # (run_honest_sweep_r3.py B20): publish the run-scoped DEADLINE before wait_for so the inner B11
    # finalizer detects the wall-clock cancellation and emits a TIMEOUT-labeled artifact; on TimeoutError
    # here ALSO emit the B11 finalizer + a labeled timeout manifest so the run is NEVER silent. RETURN the
    # timeout summary (does NOT raise) so the caller's per-query isolation (F25) records it and the sweep
    # continues. Faithfulness untouched — a timeout asserts NO findings. Ordering: per-call 6500 <
    # section 9000 < run-wall (PG_RUN_WALL_CLOCK_SEC, slate 10800).
    import asyncio  # stdlib; local import preserves the module-top NO-SPEND / NO-NETWORK invariant
    import time as _time
    from scripts.run_honest_sweep_r3 import (
        _RUN_WALL_CLOCK_DEADLINE_CTX,
        _RUN_WALL_CLOCK_ENV,
        _base_manifest_envelope,
        finalize_run_artifact,
        run_wall_clock_seconds,
    )
    _wall = run_wall_clock_seconds()
    _run_dir = out_root / q["domain"] / q["slug"]
    _run_dir.mkdir(parents=True, exist_ok=True)
    _t0 = _time.time()
    _deadline_token = _RUN_WALL_CLOCK_DEADLINE_CTX.set(_time.monotonic() + _wall)
    try:
        return await asyncio.wait_for(
            run_one_query(
                q,
                out_root,
                four_role_transport=active_transport,
                four_role_input_builder=builder,
                query_index=query_index,
                query_total=query_total,
                resume=resume,  # GAP1: A3 replay-harness corpus-snapshot resume (back-half-only)
            ),
            timeout=_wall,
        )
    except (asyncio.TimeoutError, TimeoutError):
        # PERMANENT-SILENCE HANG caught (B20). Emit a labeled, non-empty timeout artifact + manifest so
        # the run is NEVER silent; RETURN the summary (the caller's F25 isolation records it + continues).
        _timeout_summary = {
            "slug": q.get("slug", ""),
            "domain": q.get("domain", ""),
            "question": q.get("question", ""),
            "status": "error_unexpected",  # downstream-registered; a hang IS an unexpected exit
            "error": (
                f"run-level wall-clock exceeded: run_one_query did not complete within "
                f"{_wall:.0f}s ({_RUN_WALL_CLOCK_ENV}); the run was terminated (hang)"
            ),
            "cost_usd": 0.0,
            "wall_time_seconds": round(_time.time() - _t0, 1),
            "run_dir": str(_run_dir),
            "run_id": "timeout",
        }
        try:
            finalize_run_artifact(
                _run_dir, _timeout_summary, q, timed_out=True, wall_clock_seconds=_wall,
            )
        except Exception as _fin_exc:  # noqa: BLE001 — never let the backstop break the run
            print(f"[finalizer]   gate-b timeout-artifact write failed: {_fin_exc}")
        try:
            _to_manifest = _base_manifest_envelope(
                run_id="timeout", q=q, retrieval=None, run_cost=0.0,
            )
            _to_manifest["status"] = "error_unexpected"
            _to_manifest["release_allowed"] = False
            _to_manifest["run_wall_clock_timeout"] = True
            _to_manifest["run_wall_clock_seconds"] = _wall
            _to_manifest["error"] = _timeout_summary["error"]
            (_run_dir / "manifest.json").write_text(
                json.dumps(_to_manifest, indent=2, sort_keys=True, default=str) + "\n",
                encoding="utf-8",
            )
            _timeout_summary["manifest"] = _to_manifest
        except Exception as _man_exc:  # noqa: BLE001 — manifest best-effort; artifact already shipped
            print(f"[finalizer]   gate-b timeout-manifest write failed: {_man_exc}")
        return _timeout_summary
    finally:
        try:
            _RUN_WALL_CLOCK_DEADLINE_CTX.reset(_deadline_token)
        except Exception:  # noqa: BLE001 — token reset is best-effort hygiene
            pass


# ---------------------------------------------------------------------------
# I-meta-008 (#1014): the Gate-B CLI launcher — make the native 4-role benchmark
# startable from the command line.
#
# AUDIT FINDING (#1014): this launcher is the ONLY way the 4-role benchmark
# pipeline runs. The legacy CLI (`run_honest_sweep_r3 --pathB-gate`), the worker,
# and the UI all leave `four_role_transport=None`, so the 4-role seam is INERT on
# those paths — they run the legacy single-evaluator gate. `run_one_query` now
# emits a loud guard line when `PG_FOUR_ROLE_MODE` is truthy yet no transport is
# injected, so a benchmark run started through a legacy entrypoint never silently
# degrades to the single-evaluator path unnoticed.
#
# NO SPEND / NO NETWORK at import (the module invariant): argparse, asyncio.run,
# and the live preflight stay strictly inside `main()` / under `__main__`.
# ---------------------------------------------------------------------------

# The 5 LOCKED golden DRB-EN benchmark slugs (the issue's scope boundary). These are
# the ONLY new literals — the question TEXT/domain is NOT duplicated here; it is
# resolved by filtering the EXISTING `SWEEP_QUERIES` registration (single source of
# truth, LAW VI + §4.2). Verbatim prompts pinned to .codex/I-safety-002b/
# golden_questions_locked.md (the drift-guard test pins prompt text test-time).
LOCKED_BENCHMARK_SLUGS: tuple[str, ...] = (
    "drb_72_ai_labor",
    "drb_75_metal_ions_cvd",
    "drb_76_gut_microbiota_crc",
    "drb_78_parkinsons_dbs",
    "drb_90_adas_liability",
)

# Default output root — the SAME default + `<out_root>/<domain>/<slug>` tree that
# `run_one_query` already uses (LAW VI).
DEFAULT_OUT_ROOT = "outputs/honest_sweep_r3"


def load_locked_questions(slugs: tuple[str, ...] | None = None) -> list[dict]:
    """Resolve the locked benchmark question(s) by FILTERING the existing `SWEEP_QUERIES`.

    `SWEEP_QUERIES` (in `scripts.run_honest_sweep_r3`) is the single runtime source of
    truth the sweep AND the routing tests already key off; this loader is a thin filter
    over it, NOT a new question source (§0 of the I-meta-007e brief). Imported LAZILY so
    importing `run_gate_b` opens no socket and pulls no big sweep file at module load.

    `slugs=None` resolves all 5 locked slugs (in `LOCKED_BENCHMARK_SLUGS` order); a tuple
    resolves that subset. Each requested slug must be one of the 5 locked slugs AND present
    in `SWEEP_QUERIES` exactly once with a `domain` — otherwise this fails LOUD (LAW II),
    never a silent skip / empty run.

    CALLER CONTRACT (env-preservation): importing `scripts.run_honest_sweep_r3` triggers
    `load_dotenv(override=False)` at its module top, which mutates `os.environ` from `.env`.
    The `--list` path (enumeration-only, NO spend) wraps the CALL to this loader in an
    os.environ snapshot/restore so it leaves the process env byte-identical; the real-run
    path (`--only`/`--all`) lets `.env` stand because the live run needs the keys.
    """
    requested = LOCKED_BENCHMARK_SLUGS if slugs is None else tuple(slugs)
    unknown = [s for s in requested if s not in LOCKED_BENCHMARK_SLUGS]
    if unknown:
        raise ValueError(
            f"load_locked_questions: slug(s) {unknown!r} are not locked benchmark slugs. "
            f"Valid locked slugs: {list(LOCKED_BENCHMARK_SLUGS)}."
        )

    from scripts.run_honest_sweep_r3 import SWEEP_QUERIES

    resolved: list[dict] = []
    for slug in requested:
        matches = [q for q in SWEEP_QUERIES if q.get("slug") == slug]
        if not matches:
            raise ValueError(
                f"load_locked_questions: locked slug {slug!r} is NOT registered in "
                f"SWEEP_QUERIES — the loader filters the existing registration (no hardcoded "
                f"slug->question fallback). Fix the SWEEP_QUERIES registration."
            )
        if len(matches) > 1:
            raise ValueError(
                f"load_locked_questions: locked slug {slug!r} is registered {len(matches)} "
                f"times in SWEEP_QUERIES; a benchmark slug must route to exactly one domain "
                f"(fail-closed)."
            )
        entry = matches[0]
        if not entry.get("domain"):
            raise ValueError(
                f"load_locked_questions: SWEEP_QUERIES entry for slug {slug!r} has no domain; "
                f"the 4-role builder keys the frozen contract by (domain template, slug) — a "
                f"domain-less registration cannot route (fail-closed)."
            )
        resolved.append(entry)
    return resolved


def _format_list_preview(questions: list[dict]) -> str:
    """Build the `--list` / `--dry-run` preview text — NO spend, NO network, NO env mutation.

    Uses ONLY the PURE readers (`four_role_transport_mode`, `verifier_model_slugs`,
    `assert_four_role_families_distinct`) — none opens a socket or mutates process env; each
    reads only the in-memory architecture lock / process env. It calls NONE of
    `run_gate_b_query` / `enable_four_role_mode` / `preflight_four_role_transport` /
    `build_gate_b_transport`. Surfaces, for the blind operator, exactly what a real run WOULD
    do before any money is authorized: the resolved questions, the active transport mode, the
    4 role slugs+families, and a DESCRIPTIVE preflight plan (not an executed preflight).
    """
    mode = four_role_transport_mode()
    families = assert_four_role_families_distinct()  # in-memory lock read; asserts 4 distinct
    verifier_slugs = verifier_model_slugs()
    generator_family = families.get("generator", "<unknown>")

    lines: list[str] = []
    lines.append("=" * 72)
    lines.append("GATE-B 4-ROLE BENCHMARK -- NO-SPEND PREVIEW (--list / --dry-run)")
    lines.append("NOTHING below spends money, opens a socket, or mutates the environment.")
    lines.append("=" * 72)
    lines.append(f"resolved questions: {len(questions)}")
    for q in questions:
        domain = q["domain"]
        slug = q["slug"]
        prompt = (q.get("question") or "").strip().replace("\n", " ")
        prompt_preview = prompt[:100] + ("..." if len(prompt) > 100 else "")
        has_amplified = bool(q.get("amplified"))
        amplified_note = (
            f"curated amplified set ({len(q['amplified'])} entries)"
            if has_amplified
            else "NO curated amplified set (no-amplified stub -- elevated abort_corpus_inadequate risk)"
        )
        lines.append("")
        lines.append(f"  - slug={slug}")
        lines.append(f"    domain={domain}")
        lines.append(f"    scope_template=config/scope_templates/{domain}.yaml")
        lines.append(f"    retrieval={amplified_note}")
        lines.append(f"    prompt={prompt_preview!r}")
    lines.append("")
    lines.append("-" * 72)
    lines.append(f"PG_FOUR_ROLE_TRANSPORT mode: {mode}")
    lines.append(f"  generator: family={generator_family} (runs upstream on OpenRouter; from lock)")
    for role in _VERIFIER_ROLES:
        lines.append(
            f"  {role}: slug={verifier_slugs[role]} family={families[role]}"
        )
    lines.append("")
    if mode == _TRANSPORT_OPENROUTER:
        plan = (
            "openrouter mode -> a REAL run would resolve the Mirror/Sentinel/Judge benchmark "
            "slugs against the OpenRouter /models catalog (incl. a reasoning-capability check) "
            "and assert the 4 families distinct, BEFORE spending any token."
        )
    else:
        plan = (
            "self_host mode -> a REAL run would resolve each PG_<ROLE>_BASE_URL self-hosted "
            "endpoint and assert the 4 families distinct, BEFORE the sweep starts."
        )
    lines.append(f"preflight plan (descriptive, NOT executed): {plan}")
    lines.append("-" * 72)
    return "\n".join(lines)


def _resolve_benchmark_upload(
    upload_file: str, classification: str
) -> tuple[list[dict], int]:
    """Ingest a local file and shape it as a Gate-B ``uploaded_documents`` entry.

    I-ready-010 (#1073). Returns ``(allowed, blocked_count)`` where ``allowed``
    is the sovereignty-cleared partition (the ONLY docs that may ground the
    external-generator benchmark) in the ``{document_id, classification,
    filename, chunks}`` shape the sweep injection
    (``scripts/run_honest_sweep_r3.py:3458``) + ``build_upload_evidence_rows``
    already consume, and ``blocked_count`` is the number the sovereignty router
    rejected.

    Mirrors the production worker resolver
    (``polaris_v6.api.runs._resolve_uploaded_documents``): same ``chunk_text``
    chunking, same dict shape, same fail-loud-on-empty (LAW II — a silent
    zero-evidence run would mislead the operator). Imports are LAZY so importing
    ``run_gate_b`` opens no socket and pulls neither ``document_ingester`` nor
    ``fastapi`` (the module's NO-SPEND/NO-NETWORK-at-import invariant); they load
    only when ``--upload-file`` is actually used.

    Raises:
        FileNotFoundError: the path does not exist.
        ValueError: the file yields no extractable text (empty/whitespace).
    """
    import asyncio
    from pathlib import Path

    # I-ready-018 (#1138): these stay BARE + LAZY (inside the resolver) — the NO-SPEND/NO-NETWORK-
    # at-import invariant (test_upload_imports_are_lazy_inside_the_resolver) requires the bare module
    # paths inside the function body, NOT hoisted to module top. They are root-safe because
    # ``install_import_root_alias()`` ran at module load (top of this file), so bare ``polaris_graph``/
    # ``polaris_v6`` alias to their ``src.`` counterparts even under the root-only run launch.
    from polaris_graph.document_ingester import (
        DocumentIngester,
        DocumentIngestionError,
    )
    from polaris_v6.adapters.upload_evidence import (
        partition_uploads_by_sovereignty,
    )
    from polaris_v6.api.upload import chunk_text

    path = Path(upload_file)
    if not path.exists():
        raise FileNotFoundError(f"--upload-file {upload_file!r} does not exist")

    try:
        result = asyncio.run(DocumentIngester().ingest(path))
    except DocumentIngestionError as exc:
        # I-ready-010 diff-gate iter-1 P2: an unsupported extension / oversized
        # file / missing parser dependency must FAIL LOUD as a clean pre-spend
        # rc2 (ValueError -> main's parser.error), never a raw traceback/rc1.
        raise ValueError(f"--upload-file {upload_file!r}: {exc}") from exc
    content = (result.get("content") or "").strip()
    if not content:
        raise ValueError(
            f"--upload-file {upload_file!r} yielded no extractable text "
            "(empty/whitespace extraction) — a zero-evidence benchmark run "
            "would mislead the operator (LAW II fail-loud)."
        )
    chunks = chunk_text(content)
    if not chunks:
        raise ValueError(
            f"--upload-file {upload_file!r} produced no grounding chunks."
        )

    doc = {
        "document_id": result["doc_id"],
        "classification": classification,
        "filename": path.name,
        "chunks": chunks,
    }
    allowed, blocked = partition_uploads_by_sovereignty([doc])
    return allowed, len(blocked)


def gate_b_allow_partial() -> bool:
    """F03 (A3) part 2: whether Gate-B treats a ``partial*`` (or any non-`success`)
    status as a PASS. Default FALSE — a non-success status makes the run FAIL
    (rc != 0). Set ``PG_GATE_B_ALLOW_PARTIAL=1`` to restore the legacy behavior
    where a ``partial*`` status returned rc=0 (a gap-stubbed clinical report
    shipping GREEN). Operator-gated escape hatch, not the default."""
    return os.getenv("PG_GATE_B_ALLOW_PARTIAL", "0").strip() in ("1", "true", "True")


def query_status_ok(status: str, *, allow_partial: bool) -> bool:
    """F03 (A3) part 2: pure predicate — does this per-query status count as a
    Gate-B PASS (overall_rc stays 0)? ``success`` always passes. A ``partial*``
    status passes ONLY when ``allow_partial`` is set; every other status
    (abort_*/error_*/fail_*) fails. Extracted so the rc policy is unit-testable
    without running a real query.

    Behavior change vs the pre-F03 code: previously ANY ``partial*`` status
    returned rc=0 unconditionally — so a mostly-gap-stubbed report (now
    ``abort_excessive_gap`` after F03 part 1, which is NOT a ``partial`` prefix)
    AND a genuine ``partial_saturation`` both shipped GREEN. Now non-`success`
    fails unless the operator explicitly opts into partials."""
    if status == "success":
        return True
    if allow_partial and str(status).startswith("partial"):
        return True
    return False


def abort_query_error_propagates() -> bool:
    """F25 (A3): whether a per-query EXCEPTION aborts the whole ``--all`` sweep.
    Default FALSE — one crashed question is logged, written as a failed-manifest
    record, counted as a failure (rc != 0), and the sweep CONTINUES to the next
    cert question. Set ``PG_ABORT_ON_QUERY_ERROR=1`` to re-raise and stop the
    sweep on the first exception (the legacy no-isolation behavior)."""
    return os.getenv("PG_ABORT_ON_QUERY_ERROR", "0").strip() in ("1", "true", "True")


def main(argv: list[str] | None = None) -> int:
    """Gate-B CLI launcher (I-meta-008 #1014). The ONLY entrypoint that runs the 4-role
    benchmark pipeline. NO SPEND / NO NETWORK at import — all runtime work is here.

    Exactly one of {--only, --all, --list} is required. `--list`/`--dry-run` previews the
    resolved config with NO spend, NO network, and NO env mutation. A real run
    (`--only <slug>` / `--all`) delegates ENTIRELY to `run_gate_b_query` per question (which
    owns the env-flips, the fail-loud preflight BEFORE any token, the stage marker, and
    `run_one_query`). Returns 0 on success, 2 on a usage/loader error, 1 if any question run
    does not reach a `success`/`partial_*` status.
    """
    # GH #1260: arm faulthandler FIRST so the next native (libxml2) crash leaves
    # a C+Python stack instead of a silent process death (2 of 5 live runs died
    # this way). Cheap, idempotent, no spend, no network.
    enable_faulthandler()

    import argparse

    parser = argparse.ArgumentParser(
        prog="run_gate_b",
        description=(
            "Gate-B 4-role benchmark launcher (I-meta-008 #1014) — the ONLY CLI that fires "
            "the native 4-role evaluation seam. Runs the LOCKED golden DRB-EN questions."
        ),
    )
    selection = parser.add_mutually_exclusive_group(required=True)
    selection.add_argument(
        "--only", type=str, default=None, metavar="SLUG",
        help=f"Run ONE locked question by slug. Valid: {', '.join(LOCKED_BENCHMARK_SLUGS)}.",
    )
    selection.add_argument(
        "--all", action="store_true",
        help="Run ALL 5 locked benchmark questions (sequentially, one at a time).",
    )
    selection.add_argument(
        "--list", "--dry-run", dest="list_only", action="store_true",
        help=(
            "NO-SPEND, NO-NETWORK, NO-ENV-MUTATION preview: print the resolved questions, the "
            "active PG_FOUR_ROLE_TRANSPORT mode, the 4 role slugs/families, and the preflight "
            "plan. Runs NO question and spends nothing."
        ),
    )
    parser.add_argument(
        "--out-root", type=str, default=DEFAULT_OUT_ROOT, metavar="DIR",
        help=f"Output root (tree <out_root>/<domain>/<slug>). Default: {DEFAULT_OUT_ROOT}.",
    )
    # I-ready-010 (#1073): attach an uploaded document to the benchmark questions so
    # the upload->citable-evidence capability is live + measurable on the beat-both
    # path. NOT in the selection group (combines with --only/--all; ignored by --list,
    # which returns before the real-run resolve).
    parser.add_argument(
        "--upload-file", type=str, default=None, metavar="PATH",
        help=(
            "Attach a local document as grounding evidence to EVERY benchmark question "
            "in this run. Ingested in-process via DocumentIngester; chunked + injected "
            "through the SAME build_upload_evidence_rows -> strict_verify -> 4-role path "
            "as the UI. Only PUBLIC_SYNTHETIC content clears the sovereignty router for "
            "the external generator."
        ),
    )
    parser.add_argument(
        "--upload-classification", type=str, default="UNKNOWN",
        choices=["PUBLIC_SYNTHETIC", "CAN_REAL", "PRIVATE", "CLIENT", "UNKNOWN"],
        metavar="CLASS",
        help=(
            "Sovereignty classification of --upload-file (default UNKNOWN, conservative). "
            "Only PUBLIC_SYNTHETIC clears the sovereignty router for the external generator; "
            "any other value fails loud (the doc could never become benchmark evidence)."
        ),
    )
    # GAP1 (I-arch-005): thread the corpus-snapshot resume through the Gate-B path so the A3
    # replay harness exercises the back half (selection/gen/verify/render/label + the native
    # 4-role D8 seam) WITHOUT re-fetching. `run_one_query(resume=...)` and the snapshot
    # reconstruct (`_resume_active`, run_honest_sweep_r3.py:3534) already exist + are tested;
    # the ONLY missing wire was that --resume lived only on run_honest_sweep_r3.py (no 4-role)
    # while the 4-role transport is injected ONLY by this caller (which had no --resume). Combines
    # with --only/--all; ignored by --list (which returns before the real-run resolve). Per-query
    # it is NOT an error if a slug has no snapshot — that query simply runs fresh + LOUD
    # (run_honest_sweep_r3.py:3523-3537). Default OFF = byte-identical to the prior cert path.
    parser.add_argument(
        "--resume", action="store_true", default=False,
        help=(
            "Resume each query from its post-fetch corpus_snapshot.json under "
            "<out_root>/<domain>/<slug>/ instead of re-retrieving (A3 replay harness). "
            "No snapshot for a slug => that query runs fresh + logs loud (no silent re-bill)."
        ),
    )
    parser.add_argument(
        "--smoke-scale", action="store_true", default=False,
        help=(
            "I-arch-007 SMOKE: small-scale FAST run (~15-20 min) for PLUMBING validation. After the "
            "full-capability floor slate, FORCE-SET (bypassing the ~1000-URL floor) the retrieval "
            "BREADTH knobs small (~45 URLs total) + a coherent short timeout hierarchy so a HANG is "
            "known in ~40 min, not 6h. INPUT-breadth + backstops ONLY — the faithfulness engine, the "
            "A20 consolidate funnel, and the 4-role D8 seam are UNCHANGED. Default OFF = full run "
            "byte-identical. Use to catch report-build/release/funnel/token-starvation bugs fast "
            "BEFORE the full-scale beat-both run."
        ),
    )
    args = parser.parse_args(argv)

    # --only validates against the locked slug set BEFORE any env-touching import (fail loud).
    if args.only is not None and args.only not in LOCKED_BENCHMARK_SLUGS:
        parser.error(
            f"--only {args.only!r} is not a locked benchmark slug. "
            f"Valid: {', '.join(LOCKED_BENCHMARK_SLUGS)}."
        )

    requested_slugs: tuple[str, ...] | None
    if args.only is not None:
        requested_slugs = (args.only,)
    else:
        requested_slugs = None  # --all and --list both resolve the full set

    if args.list_only:
        # ENUMERATION-ONLY path (AC-3): snapshot os.environ BEFORE importing the SWEEP_QUERIES
        # source (its `load_dotenv(override=False)` mutates env from `.env`), read the transport
        # mode + slugs/families WHILE `.env` is applied (so the preview reports what a real run
        # would use), then restore the full mapping in `finally` so `--list` leaves the process
        # environment byte-identical even on error.
        env_snapshot = dict(os.environ)
        try:
            questions = load_locked_questions(requested_slugs)
            preview = _format_list_preview(questions)
        finally:
            os.environ.clear()
            os.environ.update(env_snapshot)
        print(preview)
        return 0

    # --- REAL RUN (--only / --all): operator-authorized spend. `.env` may load normally. ---
    import asyncio
    import logging
    import time
    import traceback

    out_root = Path(args.out_root)
    # Codex diff-gate iter-2 P1-2: apply the full-capability FLOOR slate HERE — BEFORE
    # load_locked_questions() imports SWEEP_QUERIES -> run_honest_sweep_r3 -> live_retriever, which cache
    # PG_LIVE_CONTENT_MAX / PG_LIVE_HTTP_TIMEOUT / PG_AGENTIC_WEB_PER_ROUND as import-time module
    # constants. Applying it after that import would leave those constants at the low .env/defaults.
    # run_gate_b_query re-applies it (idempotent) for the direct-call path + per-query.
    apply_full_capability_benchmark_slate(smoke_scale=args.smoke_scale)
    questions = load_locked_questions(requested_slugs)
    # Codex diff-gate iter-2 P1-2: load_locked_questions has now imported the sweep -> live_retriever ->
    # state WITH the slate applied above, so the import-time constants are at full capability. Validate in
    # a FRESH SUBPROCESS (test_run_gate_b_import_order) rather than here — an in-process runtime gate would
    # false-fire under pytest where those modules are pre-imported with defaults. The slate-before-import
    # ORDER above is the fix; preflight_import_time_constants() is the assertion the subprocess test runs.
    # I-ready-010 (#1073): resolve the optional --upload-file ONCE (before the loop)
    # into the sovereignty-cleared `uploaded_documents` shape. FAIL LOUD here (before
    # any token is spent) on a missing/empty file or a non-PUBLIC_SYNTHETIC doc that the
    # external-generator benchmark could never use — never a silent zero-upload run.
    _attach_uploads: list[dict] = []
    _upload_blocked = 0
    if args.upload_file:
        try:
            _attach_uploads, _upload_blocked = _resolve_benchmark_upload(
                args.upload_file, args.upload_classification
            )
        except (FileNotFoundError, ValueError) as exc:
            parser.error(str(exc))
        if not _attach_uploads:
            parser.error(
                f"--upload-file {args.upload_file!r} classified "
                f"{args.upload_classification!r} is EXTERNAL_LEAK_FORBIDDEN — only "
                "PUBLIC_SYNTHETIC may ground the external-generator benchmark. "
                "Reclassify (--upload-classification PUBLIC_SYNTHETIC) or remove it."
            )
        print(
            f"attached upload: {args.upload_file} "
            f"({len(_attach_uploads[0]['chunks'])} chunk(s), "
            f"classification={args.upload_classification}, blocked={_upload_blocked})"
        )

    print("=" * 72)
    print(f"GATE-B 4-ROLE BENCHMARK RUN -- {len(questions)} question(s)")
    print(f"transport mode: {four_role_transport_mode()}")
    print(f"output root: {out_root}")
    print("=" * 72)

    overall_rc = 0
    _allow_partial = gate_b_allow_partial()           # F03 (A3) part 2
    _abort_on_error = abort_query_error_propagates()   # F25 (A3)
    _sweep_records: list[dict] = []                    # F25: incremental sweep summary
    out_root.mkdir(parents=True, exist_ok=True)
    _sweep_summary_path = out_root / "sweep_summary.json"

    def _persist_sweep_summary() -> None:
        # F25 (A3): write the running per-query roster after EVERY question (success,
        # non-success, or crash) so a sweep killed mid-run still leaves a durable
        # record of which cert questions ran and how each ended. Best-effort — a
        # summary-write failure must not mask a query result.
        try:
            _sweep_summary_path.write_text(
                json.dumps(
                    {
                        "out_root": str(out_root),
                        "total_questions": len(questions),
                        "completed": len(_sweep_records),
                        "overall_rc": overall_rc,
                        "allow_partial": _allow_partial,
                        "queries": _sweep_records,
                    },
                    indent=2,
                    sort_keys=True,
                    default=str,
                )
                + "\n",
                encoding="utf-8",
            )
        except OSError as _exc:
            logging.getLogger("run_gate_b").warning(
                "sweep_summary write failed: %s", _exc,
            )

    # I-obs-001 #1141 AC1: enumerate so the heartbeat can report "query N of 5".
    for query_index, q in enumerate(questions, 1):
        slug = q["slug"]
        domain = q["domain"]
        if _attach_uploads:
            # COPY — load_locked_questions returns the live SWEEP_QUERIES dict
            # (run_gate_b.py:886,893); mutating it would leak `uploaded_documents`
            # into the global registry, poisoning the routing tests + later runs in
            # the same process. `uploaded_documents` is a fresh key, read-only-consumed
            # by run_one_query -> build_upload_evidence_rows.
            q = dict(q)
            q["uploaded_documents"] = _attach_uploads
            q["uploaded_documents_blocked_count"] = _upload_blocked
        print(f"\n>>> {domain} / {slug}")
        # BUG-5 (I-arch-006 #1262): clear any STALE crash sidecar BEFORE the fresh attempt.
        # The except-path below writes gate_b_query_crash.json when a query crashes. If a
        # PRIOR failed attempt of this same domain/slug left that sidecar behind, a now-healthy
        # re-run that completes normally would still carry the old crash record on disk — a
        # post-run reader (sweep auditor / status tool) would misread the out-dir as "crashed"
        # even though THIS attempt succeeded. So on each fresh attempt, best-effort delete the
        # pre-existing sidecar; the except-path re-creates it ONLY if THIS attempt genuinely
        # crashes. Faithfulness is untouched: this is a stale-observability artifact removal in
        # the benchmark RUNNER's status sidecar — it never reads, alters, drops, or relabels any
        # verified claim, evidence span, or faithfulness-gate verdict (strict_verify / NLI /
        # 4-role / span-grounding all run unchanged inside run_gate_b_query). Best-effort: a
        # cleanup failure is logged and the attempt proceeds, never masking a query result.
        _crash_sidecar = out_root / domain / slug / "gate_b_query_crash.json"
        try:
            _crash_sidecar.unlink(missing_ok=True)
        except OSError as _stale_err:
            logging.getLogger("run_gate_b").warning(
                "stale crash-sidecar cleanup failed for %s/%s: %s", domain, slug, _stale_err,
            )
        # Sequential — one question at a time (CLAUDE.md §8.4 resource discipline; no parallel
        # runs). Each delegates entirely to the existing 4-role entrypoint.
        #
        # F25 (A3): per-query exception ISOLATION. asyncio.run(run_gate_b_query) had NO
        # try/except, so a single escaped exception (e.g. a transport RuntimeError) aborted
        # ALL remaining cert questions — the `--all` 5-Q run could not complete. Each query is
        # now wrapped: an exception is logged with traceback, written as a durable
        # failed-manifest record under out_root, counted as a FAILURE (rc!=0), and the sweep
        # CONTINUES (PG_ABORT_ON_QUERY_ERROR=1 re-raises after recording, for the strict mode).
        try:
            summary = asyncio.run(
                run_gate_b_query(
                    q, out_root, query_index=query_index, query_total=len(questions),
                    resume=args.resume,  # GAP1: A3 replay-harness corpus-snapshot resume
                    smoke_scale=args.smoke_scale,  # I-arch-007: small-scale fast plumbing smoke
                )
            )
            status = summary.get("status", "<no-status>")
            print(f"<<< {domain} / {slug}: status={status}")
            _status_ok = query_status_ok(status, allow_partial=_allow_partial)
            if not _status_ok:
                overall_rc = 1
            # I-arch-007 ITEM 2 (#1264) POST-RUN CANARY: on a released run (success OR
            # released_with_disclosed_gaps), FAIL CLOSED if the rendered report.md dropped the
            # weighted-enrichment breadth surface — so the §-1.3 breadth funnel can never again silently
            # reassert (the "zero appended weighted-enrichment section log lines in ALL reports"
            # symptom). Faithfulness-neutral (reads the shipped report/manifest, mutates nothing).
            # Codex P2 (iter2): the canary is invoked UNCONDITIONALLY (not gated on _status_ok) because
            # the always-release degrade ships `released_with_disclosed_gaps`, which query_status_ok may
            # mark not-ok — gating on _status_ok would make the canary's released_with_disclosed_gaps
            # coverage dead. The canary self-skips on non-released / smoke statuses (returns "skip:..."),
            # so calling it always only ADDS telemetry; a credibility-degraded run that dropped breadth
            # now FAILS CLOSED here (it no longer "stands down").
            _breadth_canary = None
            try:
                _breadth_canary = assert_breadth_enrichment_rendered(
                    summary, smoke_scale=args.smoke_scale,
                )
                print(f"<<< {domain} / {slug}: breadth-enrichment canary={_breadth_canary}")
            except BreadthEnrichmentCanaryError as _bc_exc:
                overall_rc = 1
                _breadth_canary = "FAILED"
                logging.getLogger("run_gate_b").error(
                    "breadth-enrichment canary FAILED for %s/%s: %s", domain, slug, _bc_exc,
                )
                print(f"<<< {domain} / {slug}: breadth-enrichment canary FAILED: {_bc_exc}")
            _sweep_records.append({
                "query_index": query_index,
                "slug": slug,
                "domain": domain,
                "status": status,
                "ok": _status_ok and _breadth_canary != "FAILED",
                "breadth_enrichment_canary": _breadth_canary,
                "cost_usd": summary.get("cost_usd"),
            })
        except Exception as exc:  # noqa: BLE001 — isolate ONE query; never abort the sweep silently
            tb = traceback.format_exc()
            overall_rc = 1
            logging.getLogger("run_gate_b").error(
                "query %d/%d %s/%s CRASHED: %s\n%s",
                query_index, len(questions), domain, slug, exc, tb,
            )
            print(f"<<< {domain} / {slug}: CRASHED ({type(exc).__name__}: {exc})")
            # Durable failed-manifest record so a crashed query is NOT indistinguishable
            # from one that never started (LAW II fail-loud; mirrors run_one_query's
            # BUG-B-101 exception-path manifest write).
            _fail_record = {
                "query_index": query_index,
                "slug": slug,
                "domain": domain,
                "status": "error_query_crashed",
                "ok": False,
                "error": str(exc)[:500],
                "traceback": tb[-4000:],
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            }
            _sweep_records.append(_fail_record)
            try:
                _fail_dir = out_root / domain / slug
                _fail_dir.mkdir(parents=True, exist_ok=True)
                # Codex diff-gate P2: the crash record ALWAYS goes to a dedicated SIDECAR
                # (gate_b_query_crash.json) — never collides with run_one_query's manifest.json.
                # We write manifest.json ONLY if run_one_query did not already produce one: if an
                # exception escaped AFTER run_one_query wrote a richer error manifest, that richer
                # artifact is PRESERVED (don't clobber it with this thinner outer record).
                (_fail_dir / "gate_b_query_crash.json").write_text(
                    json.dumps(_fail_record, indent=2, sort_keys=True, default=str) + "\n",
                    encoding="utf-8",
                )
                _manifest_path = _fail_dir / "manifest.json"
                if not _manifest_path.exists():
                    _manifest_path.write_text(
                        json.dumps(_fail_record, indent=2, sort_keys=True, default=str) + "\n",
                        encoding="utf-8",
                    )
            except OSError as _werr:
                logging.getLogger("run_gate_b").warning(
                    "failed-manifest write failed for %s/%s: %s", domain, slug, _werr,
                )
            if _abort_on_error:
                _persist_sweep_summary()
                raise
        _persist_sweep_summary()
    return overall_rc


if __name__ == "__main__":
    import sys

    sys.exit(main())
