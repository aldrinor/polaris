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

# I-wire-014 (#1336): native-thread-safety clamp MUST run before ANY native import (torch/MKL/
# tokenizers read their thread-pool env vars once, at library-init time). Importing this standalone
# stdlib-only module IS the clamp (setdefault; LAW VI). Fixes the intermittent A15 re-fetch crash
# ``malloc(): unsorted double linked list corrupted`` — the MinerU VLM Predict racing on the glibc
# heap with leaked AccessBypass fetch daemon threads. Output-invariant (thread count != numerics).
# Codex gate P1: bootstrap the repo root onto sys.path FIRST so ``src.*`` imports whether this module
# is imported (run_gate_b_query) OR executed by path from repo root (sys.path[0]=scripts/dr_benchmark).
# This file is scripts/dr_benchmark/run_gate_b.py => repo root is parents[2] (NOT parents[1]).
import sys as _sys_clamp_bootstrap
from pathlib import Path as _Path_clamp_bootstrap

_sys_clamp_bootstrap.path.insert(0, str(_Path_clamp_bootstrap(__file__).resolve().parents[2]))
import src._polaris_native_thread_safety  # noqa: F401,E402  # import-time side effect: applies the clamp

import json
import logging
import os
from dataclasses import dataclass
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
    _family_from_slug,
    benchmark_verifier_family,
    benchmark_verifier_lineup,
    openrouter_base_url,
    role_reasoning_enabled,
)
# I-deepfix-001 Codex gate P0 (WS-1 judge cache run-scope): the judge verdict idempotency cache is a
# WITHIN-ONE-REPORT byte-twin dedup surface, but it is process-wide and (pre-fix) never reset — so a
# document-1 verdict leaked into document-2 in the same sequential sweep process. reset_judge_verdict_cache
# is called at the per-document boundary (top of run_gate_b_query) so each report's 4-role pass starts
# clean. judge_adapter imports only stdlib + the roles contracts at module top (no network/spend).
from src.polaris_graph.roles.judge_adapter import reset_judge_verdict_cache
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
        # I-beatboth-008 (#1285) P1-1: derive the generator family the SAME provider-prefix way
        # the verifiers do (`benchmark_verifier_family` -> `_family_from_slug` = slug.split("/")[0]),
        # from the generator's ACTIVE slug (PG_GENERATOR_MODEL override, else the lock's model_slug).
        # The prior code read the lock's `family` FIELD ('glm') for the generator while the verifiers
        # report the provider PREFIX ('z-ai' for z-ai/glm-5.2) — two inconsistent label spaces, so on
        # the all-GLM-5.2 stack gen='glm' vs mirror='z-ai' never matched by string and the
        # distinctness loop passed by ACCIDENT (it never consulted allowed_collisions). Deriving the
        # generator family the identical provider-prefix way makes gen='z-ai' == mirror='z-ai' -> the
        # real same-lineage collision is DETECTED -> the allowed_collisions [[generator, mirror]] pair
        # below is what permits it (emptying allowed_collisions now correctly RAISES).
        generator_slug = os.getenv("PG_GENERATOR_MODEL") or str(
            lock["required_roles"]["generator"]["model_slug"]
        )
        fams = {"generator": _family_from_slug(generator_slug)}
        for role in _VERIFIER_ROLES:
            fams[role] = benchmark_verifier_family(role)
    else:
        roles = ("generator", *_VERIFIER_ROLES)
        fams = {r: str(lock["required_roles"][r]["family"]) for r in roles}
    # I-beatboth-008 (#1285): honor the lock's family_policy.allowed_collisions instead of a
    # bare set-length distinctness check. On the all-GLM-5.2 stack the openrouter branch passes
    # only by LABEL MISMATCH — the generator's family is sourced from the lock ('glm') while the
    # mirror's benchmark slug 'z-ai/glm-5.2' yields the provider-prefix family 'z-ai' — i.e. the
    # same GLM-5.2 lineage carries two labels, so the old len(set)!=len() check passed by accident.
    # The self_host branch sources ALL four families from the lock, so gen+mirror are BOTH 'glm':
    # a real same-family collision that must be skipped ONLY for the operator-approved
    # allowed_collisions pair. A NON-listed same-family collision (e.g. a re-pick that puts the
    # Judge into the Mirror's family) still RAISES. Pattern mirrors validate_role_families
    # (openrouter_client.py:774-787): continue-without-recording so a THIRD same-family role raises.
    fp = lock.get("family_policy", {})
    allowed = {tuple(sorted(str(x) for x in pair)) for pair in fp.get("allowed_collisions", [])}
    seen = {}
    for role, fam in fams.items():
        if fam in seen:
            other_role = seen[fam]
            if tuple(sorted([role, other_role])) in allowed:
                continue
            raise RuntimeError(
                "Gate-B preflight: 4-role family collision — all roles must be distinct "
                f"lineages for the active transport mode (got {fams}); role {role!r} and "
                f"role {other_role!r} share family {fam!r} and the pair is not in "
                f"allowed_collisions={sorted(allowed)}"
            )
        seen[fam] = role
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
    # I-deepfix-001 (#1344): the pre-spend catalog probe must ride out a TRANSIENT OpenRouter
    # hiccup (HTTP 408/425/429/5xx or a connect/read timeout) instead of crashing the whole run to
    # a $0 abort on a single blip (observed: a lone 408 killed the run before retrieval started).
    # Bounded retry with capped exponential backoff; a GENUINE persistent failure STILL fails LOUD
    # (LAW II). Faithfulness-neutral (pre-spend liveness probe only, no spend, no gate touched).
    # PG_PREFLIGHT_CATALOG_RETRIES (default 5); the injected MockTransport test path returns 200 on
    # the first attempt so it is byte-identical.
    import time  # local import — module has no top-level `time` (mirrors the local imports elsewhere)
    try:
        _catalog_retries = max(1, int(os.getenv("PG_PREFLIGHT_CATALOG_RETRIES", "5")))
    except (TypeError, ValueError):
        _catalog_retries = 5
    _transient_status = {408, 425, 429, 500, 502, 503, 504}
    try:
        for _attempt in range(_catalog_retries):
            try:
                response = client.get(url, timeout=_TIMEOUT_SECONDS)
            except httpx.HTTPError as _exc:  # connect / read / pool timeout — transient transport fault
                if _attempt < _catalog_retries - 1:
                    time.sleep(min(2.0 * (2 ** _attempt), 30.0))
                    continue
                raise RuntimeError(
                    f"OpenRouter catalog preflight: GET {url} transport error after "
                    f"{_catalog_retries} attempts: {_exc}"
                ) from _exc
            if response.status_code == httpx.codes.OK:
                break
            if response.status_code in _transient_status and _attempt < _catalog_retries - 1:
                time.sleep(min(2.0 * (2 ** _attempt), 30.0))
                continue
            raise RuntimeError(
                f"OpenRouter catalog preflight: GET {url} returned HTTP {response.status_code}"
                + (f" after {_attempt + 1} attempts" if _attempt else "")
            )
    finally:
        if own_client:
            client.close()
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
    # I-deepfix-001 (#1344) PURITY BUILD: STORM is a LOSER — killed. STORM is the core loser the operator
    # saw fire (interview/query-expansion engine). Slate "0" + removed from FORCE_ON + REQUIRED + added to
    # FORCE_EXACT "0" + REQUIRED_OFF below so the preflight FAILS CLOSED if it is ever re-armed.
    # R1_deepener_enable: the citation-snowball evidence deepener (PG_SWEEP_EVIDENCE_DEEPENER) is NO LONGER
    # a killed loser — it is the recall lever for the blocked-reference / primary-starved corpus (task72:
    # T1+T2=14/182, the primaries behind a blocked systematic review never fetched). It is setdefault-ON
    # below (NOT force / NOT slate-dict floor — LAW VI: an operator PG_SWEEP_EVIDENCE_DEEPENER=0 still wins)
    # and REMOVED from FORCE_EXACT / REQUIRED_OFF / the NO-LOSER gate. WIDEN-ONLY (§-1.3): every discovered
    # URL routes through the UNCHANGED fetch->tier->strict_verify chokepoint, so the FROZEN faithfulness
    # engine re-grounds every claim (see the setdefault + key-passthrough block in
    # apply_full_capability_benchmark_slate).
    "PG_STORM_ENABLED_IN_BENCHMARK": "0",
    # I-deepfix-001 (#1344) PURITY — the remaining LOSER kill-switches that the slate previously did NOT
    # carry. force-EXACT "0" here (each is in _BENCHMARK_FORCE_EXACT_FLAGS) so a stray operator/.env value
    # cannot re-arm them past the slate; each is also asserted in _BENCHMARK_PREFLIGHT_REQUIRED_OFF_FLAGS
    # (the NO-LOSER gate fails CLOSED if any resolves truthy). PG_SWEEP_QUERY_DECOMPOSE defaults ON in the
    # run path (query_decomposer) so it MUST be slate-pinned 0 to die; the other two are dark-but-unguarded.
    "PG_SWEEP_QUERY_DECOMPOSE": "0",        # K9 legacy q1d query_decompose (default-ON consumer; kill at source)
    "PG_QGEN_ITERRESEARCH": "0",            # K10 IterResearch driver (superseded by FS-Researcher W2)
    "PG_USE_RESEARCH_PLANNER": "0",         # K11 legacy facet query-gen (dark, unguarded → pin off)
    # I-deepfix-001 (#1344) PURITY (Codex P2-agentic-force-exact-dead-metadata): K7 agentic URL-discovery
    # (STORM's twin loser) was force-EXACT-listed but was NOT a slate-dict member — so apply_slate's dict
    # loop never visited it and could NOT force-zero it (only the paid run_gate_b_query path force-set it
    # "0" at the os.environ line below). Add it to the slate dict as "0" so apply_full_capability_benchmark_
    # slate GENUINELY force-zeroes it (it is in _BENCHMARK_FORCE_EXACT_FLAGS → the dict loop hard-overrides),
    # making STANDALONE apply-slate callers (tests / the offline path) safe too — not just the paid path.
    # Also in _BENCHMARK_PREFLIGHT_REQUIRED_OFF_FLAGS (NO-LOSER fails CLOSED if re-armed).
    "PG_AGENTIC_SEARCH_IN_BENCHMARK": "0",  # K7 agentic URL-discovery (STORM's twin; slate force-zero)
    # I-deepfix-001 (#1344) PURITY — ALSO pin the storm_interviews MODULE flag off. The benchmark gate
    # PG_STORM_ENABLED_IN_BENCHMARK (above) is what the run-path guard keys on, but the module's own
    # PG_STORM_ENABLED (storm_interviews.py:42, read at import) is a SECOND arm — the operator .env carries
    # PG_STORM_ENABLED=1, which is HARMLESS on Gate-B (the run path keys on the benchmark gate, not this) but
    # leaves the module looking pre-armed. Pin it "0" so the engine is provably disarmed at BOTH arms; the
    # NO-LOSER gate asserts the EFFECTIVE env (the import-time module attr is a test-order artifact).
    "PG_STORM_ENABLED": "0",                # storm_interviews module flag (defense-in-depth dual-arm kill)
    # I-deepfix-001 (#1344) PURITY — the WINNER / mirror-model selectors the live consumer reads but the
    # slate left unpinned. PG_EMBED_MODEL (NOT PG_EMBEDDER_MODEL) is the var the live relevance/off-topic +
    # selection embedder loader reads; PG_ENTAILMENT_MODEL / PG_EVALUATOR_MODEL pin the live faithfulness
    # judge + external evaluator to the §9.1.8 locked mirror so a gemma slug can never drift in. force-EXACT
    # (in _BENCHMARK_FORCE_EXACT_FLAGS) + value-equals asserted in _BENCHMARK_WINNER_EXACT_VALUE_ASSERTIONS.
    # FAITHFULNESS-NEUTRAL: a model SELECTION; the FROZEN faithfulness engine re-checks every claim.
    "PG_EMBED_MODEL": "Qwen/Qwen3-Embedding-8B",   # K12 live relevance embedder (else silent MiniLM)
    "PG_ENTAILMENT_MODEL": "z-ai/glm-5.2",         # gemma-pin: live NLI / semantic-conflict judge mirror
    "PG_EVALUATOR_MODEL": "z-ai/glm-5.2",          # gemma-pin: external evaluator mirror
    # I-deepfix-001 loss-risk FIX-1 (H1 scope gate DARK): the SCOPE+TIMELINE ENFORCEMENT half of commit
    # 64c10a49 defaults OFF and was set NOWHERE on the Gate-B path, so the scope gate produced ZERO effect
    # on the paid benchmark run (selection byte-identical to pre-fix). Arm all four here (force-ON below +
    # preflight-required below) so a stray operator/.env =0 cannot leave the scope gate dark. §-1.3 WIDEN-
    # ONLY (arms an EXISTING weight/demote/disclose plan — no cap/target/thinner introduced); FAITHFULNESS-
    # NEUTRAL (every surfaced/demoted source re-passes the UNCHANGED strict_verify per claim; the tier-
    # deviation DISCLOSURE mode replaces a §-1.3-banned corpus REFUSAL with a disclosed-weight proceed).
    "PG_SCOPE_CONSTRAINT_ENFORCE": "1",      # constraint_enforcement: out-of-scope demote / restrict-to mask / user-pin (else empty plan)
    "PG_EXTRACT_SCOPE_CONSTRAINTS": "1",     # intake_constraint_extractor: parse the scope+timeline intent the enforcer consumes
    "PG_RELEVANCE_PRESERVE_ANCHORS": "1",    # evidence_selector: never cut a marquee/user-pinned anchor source
    "PG_CORPUS_TIER_DISCLOSURE_MODE": "1",   # corpus_approval_gate: material tier deviation PROCEEDS with a disclosed profile (not a §-1.3 refusal)
    # Observability — MUST be on so each feature's firing is provable in manifest['tool_utilization'].
    "PG_ENABLE_TOOL_TRACKER": "1",
    # Import-time caps/timeouts (read at module load — applied before the sweep import below).
    # I-deepfix-001 U31 (Codex P1): the slate previously pinned 50000, which ACTIVELY
    # TRUNCATED below the U31 code default (live_retriever.DEFAULT_CONTENT_MAX_CHARS =
    # getenv('PG_LIVE_CONTENT_MAX', '300000')) — so 100k-190k clinical papers were cut to
    # 50k on the paid run and the U31 fix was DARK. Match the code default (300000). FLOOR
    # entry: max(existing, 300000), so a memory-constrained operator cannot lower Gate-B
    # below the U31 cap, and a higher operator value is kept. Faithfulness-neutral (a fetch
    # length cap; strict_verify re-checks every claim regardless of body length).
    "PG_LIVE_CONTENT_MAX": "300000",
    "PG_LIVE_HTTP_TIMEOUT": "30",
    # SPEED LEVER L1 (dual-gated speed decision — both review gates APPROVE, with guards): raise the
    # global fetch-pool worker FLOOR 24 -> 48 to cut fetch wall-clock on the ~1000-URL corpus. This is a
    # FLOOR value (apply_full_capability_benchmark_slate: max(existing, slate)), NOT force-exact, so a
    # higher operator/.env value is still kept and never silently lowered. The per-HOST politeness cap
    # (PG_LIVE_RETRIEVER_PER_HOST_CONCURRENT below) STAYS 6, so same-host crawl rate is unchanged — only
    # cross-host fetch breadth widens. FAITHFULNESS-NEUTRAL: fetch concurrency only; strict_verify / NLI /
    # 4-role D8 / provenance re-check every claim regardless of worker count.
    # 429/BREADTH STEP-DOWN GUARD (correction 7 — now REAL, not a comment): the forensic monitor steps
    # 48 -> 36 -> 24 by setting PG_LIVE_RETRIEVER_MAX_WORKERS_STEPDOWN=<n> (no code edit) if run telemetry
    # shows a 429-rate rise or a cited-source breadth regression vs the 24-worker baseline. The
    # apply_full_capability_benchmark_slate() step-down block honors it as min(48, override) AFTER this
    # FLOOR (so the floor cannot raise a step-down back to 48). The per-host cap is the politeness
    # invariant (never raise it to compensate); the worker floor here is the ceiling the monitor steps DOWN
    # from. This "48" is the CEILING the step-down block reads via _FULL_CAPABILITY_BENCHMARK_SLATE.
    "PG_LIVE_RETRIEVER_MAX_WORKERS": "48",
    # I-beatboth-008 (#1285) commit-2 build A: per-HOST politeness concurrency for the parallel
    # fetch pool (live_retriever:4093 _env_int, CALL-time). 6 lets distinct hosts fetch wider while
    # same-host stays capped — concurrency only, faithfulness-neutral. Read at call time inside the
    # sweep chain (imported AFTER the slate), so the env-set lands without a rebind.
    "PG_LIVE_RETRIEVER_PER_HOST_CONCURRENT": "6",
    # F01/F16 (A3): the global LLM concurrency cap. llm_provider.get_semaphore() reads this at
    # CALL time (per-loop rebind), so the slate value lands without an import-time freeze. FLOOR
    # semantics (max(existing, 5)): an operator may RAISE it but never silently drop below the
    # safe default of 5 (cloud rate-limit / GPU-OOM guard). NOT part of the ~1000-URL fetch sum —
    # it caps concurrent LLM calls, not URLs.
    "PG_MAX_CONCURRENT_LLM": "8",
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
    # I-deepfix-001 (wallclock_guard): a REAL clinical back-half measured 10992s — over the old
    # 10800 wall, so a fully-rendered run got guillotined. Raise to 14400 (4h) so a healthy clinical
    # run clears with margin; still catches a true total hang. Cap, not target (billed by actual
    # usage). retrieval 5400 < section 9000 < seam 7200 < run-wall 14400 hierarchy holds.
    "PG_RUN_WALL_CLOCK_SEC": "14400",
    # I-deepfix-001 W02-retrieval-wall-activate (#1344): the SHARED per-question retrieval
    # wall. This is the ACTIVATION SWITCH for the entire staged retrieval-deadline class
    # (FIX-2 search-site deadline, BUG-A 5-outer-loop gates, the WALL-03 FS-Researcher qgen
    # gate, the W08 CRAG total-call clamp): the spine reads PG_RETRIEVAL_QUESTION_WALL_SECONDS
    # ONCE and anchors `_question_retrieval_deadline`; when UNSET that deadline is None and
    # EVERY one of those gates no-ops (deadline is None => never passed), so retrieval +
    # generation can cross the 10800s run-wall and the question dies as a TIMEOUT stub
    # instead of a report. Setting it < the run-wall (5400 < 10800) means the partial
    # corpus HANDS OFF (disclosed retrieval_wall_hit) WELL BEFORE the run-wall guillotines.
    # 5400s (90 min) is generous for retrieval+classification on the ~1000-URL cap yet
    # leaves the back half (generation, 4-role D8, render) ~90 min inside the 3h run-wall.
    # FLOOR semantics via the slate setdefault; the aggregate-fit preflight below FAILS
    # CLOSED if these inner budgets cannot fit the run-wall. SS-1.3: drops no source — the
    # partial corpus is handed off, never thinned.
    "PG_RETRIEVAL_QUESTION_WALL_SECONDS": "5400",
    # I-deepfix-001 W05-consolidation-nli-coldload-bound (#1344): bound the HuggingFace Hub
    # FIRST-LOAD network download of the consolidation cross-encoder (and any other
    # HF-downloaded model on a cold VM cache). Without a download timeout a stalled/throttled
    # Hub connection WEDGES the consolidation stage on a fresh cache with no bound. This env
    # var is read by huggingface_hub's file_download; a stalled download then fails fast and
    # the W05 degrade SKIPS the consolidation WEIGHT (skipping only under-merges => keeps MORE
    # baskets, §-1.3) rather than blocking. NOTE: the production VM should ALSO pre-stage the
    # cross-encoder into the image cache during preflight and set HF_HUB_OFFLINE=1 so the paid
    # path never touches the network — that is a VM-image concern, not a slate default (setting
    # HF_HUB_OFFLINE=1 here would break a legitimately-cold first run). FLOOR semantics: the
    # download timeout is forced exact via the string slate (a non-numeric value).
    "HF_HUB_DOWNLOAD_TIMEOUT": "30",
    # I-beatboth-011 #1290: BOUND the 4-role D8 seam in the FULL slate (was pinned ONLY in
    # _SMOKE_SCALE_OVERRIDES) so a full/--resume run cannot grind the default max(7200, 4*6500)=26000s
    # (~7.2h) the path-audit caught. The env wins outright in _resolve_four_role_seam_timeout
    # (run_honest_sweep_r3.py:437); rides _BENCHMARK_FORCE_EXACT_FLAGS so a stale operator .env cannot
    # restore the grind. 7200 < run-wall 10800 so the seam terminates inside the wall; the seam .result()
    # is ADDITIONALLY capped by the remaining run-wall budget at the call site. 7200 = the historical
    # floor, generous for the parallelized (PG_PARALLEL_VERIFY) per-claim 4-role verify.
    "PG_FOUR_ROLE_SEAM_TIMEOUT_SECONDS": "7200",
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
    "PG_STORM_MAX_BENCHMARK_QUERIES": "0",  # I-deepfix-001 (#1344) PURITY: STORM is dead — 0 the query cap (dies with the engine)
    "PG_MAX_SUBQUERIES": "15",
    # Agentic per-round web breadth (was stuck at 6 via the PG_WEB_PER_ROUND typo).
    "PG_AGENTIC_WEB_PER_ROUND": "10",
    # Budget cap (spend ceiling enforced per run). I-beatboth-011 idx52 (#1289): raised 25 -> 150.
    # At 25 the D8 4-role gate hard-stopped on BudgetExceededError mid-adjudication (gen ~$11 + full D8
    # ~$13 settles ~$24, and the budget-reservation admission control needs cap > settled_peak + the
    # 12-worker reservation ~$42 floor). 150 is HEADROOM, not a target — billing is by actual usage
    # (~$24-42/run); without it a fresh cert run aborts as judge_skipped_d8_binding before D8 finishes.
    "PG_MAX_COST_PER_RUN": "150",
    # I-ready-002 (#1071) P0: BINDING faithfulness verifier. The entailment judge runs as a binding DROP
    # gate AND (Codex iter-1 fix) fails closed on a judge_error (the judge's fail-open "ENTAILED",
    # "judge_error:..." sentinel) when PG_STRICT_VERIFY_ENTAILMENT=enforce. Force it on so the benchmark's
    # binding gate enforces entailment + fails closed on error (STRENGTHENS faithfulness, never weakens).
    # NOTE (Codex iter-1 P1): we deliberately do NOT force PG_VERIFICATION_MODE=enforce — that ALSO enables
    # the Phase 0b RESCUE deltas (a separate faithfulness-WIDENING feature that passes some previously-
    # dropped claims), which is not in this benchmark's scope. judge_error fail-closed is now keyed on the
    # entailment mode (provenance_generator.py), independent of the rescue switch.
    "PG_STRICT_VERIFY_ENTAILMENT": "enforce",
    # I-beatboth-011 §3.1 ROUTE C (#1289, operator keystone): the FAITHFUL ABSTRACTIVE WRITER as the
    # per-basket prose producer (multi_section_generator.py:3949). Replaces the deterministic short-writer
    # RENDER PROBE (which was only ever a render-path probe, never the real prose producer) with one
    # LLM-rephrased, RE-VERIFIED declarative sentence per basket. SAFE BY CONSTRUCTION: (a) fail-closed
    # activation requires PG_STRICT_VERIFY_ENTAILMENT=enforce (set ABOVE — both land); (b) every rewrite
    # is re-run through the UNCHANGED strict_verify + a STRICTER writer wrapper (no local-window rescue +
    # judge_error fail-closed + numeric-completeness), degrading to the verbatim K-span on any failure;
    # (c) §3.1 input-screen drops chrome members before the writer call. This is the producer that turns
    # the verbatim span-dump into plain declarative prose WITHOUT relaxing faithfulness. Default-OFF in
    # code => the slate ACTIVATES it for the cert run (force-ON below). Writer model = glm-5.2 generator
    # arm; the reasoning/concurrency/deadline budgets are TUNED below (not the slow module defaults).
    "PG_ABSTRACTIVE_WRITER": "1",
    # I-beatboth-011 (a) (#1289): writer reasoning/concurrency/deadline tuning so Route C FIRES under
    # load. The resume run timed out 22/44 baskets ("writer call exceeded 120s deadline") because the
    # writer's default reasoning budget is 8192 (GLM burns it) -> each rephrase ran slow; the §3.1 smoke
    # at reasoning=2048 completed in 3.2s. A rephrase is a copy-edit, not analysis (§9.1.8 forbids
    # STARVING reasoning into EMPTY content; 8192 here causes SLOWNESS, not starvation, and 2048 is
    # smoke-proven sufficient). Lower the reasoning budget + writer concurrency (cut all-GLM endpoint
    # self-contention vs the D8 verify fan-out) + modest deadline headroom. Timing-only; faithfulness-
    # neutral. Force-EXACT below so a stray .env cannot restore the slow 8192/8/120 defaults.
    "PG_ABSTRACTIVE_WRITER_REASONING_MAX_TOKENS": "2048",
    "PG_ABSTRACTIVE_WRITER_CONCURRENCY": "4",
    "PG_ABSTRACTIVE_WRITER_CALL_DEADLINE_S": "180",
    # I-wire-005 B-B (#1319): the Phase-7 quantified-spec Writer budgets. B4 (#1317) lived ONLY in
    # the run_honest_sweep_r3 closure default (32768) and was NEVER pinned in this slate — so a
    # partial deploy (or a stale operator .env) could leave the spec Writer at a starvation budget
    # while the preflight passed, the exact "built-it-then-left-it-off" / partial-deploy failure the
    # B-B re-run hypothesis names. Pin BOTH explicitly: the overall content budget (32768) AND the
    # reasoning cap (8192) that reserves content on the reasoning-first GLM-5.2 generator (the root
    # cause: effort=high with no reasoning cap burns the whole budget -> empty content -> spec_
    # produced=False). Both ride _BENCHMARK_FORCE_EXACT_FLAGS + floor-guarded below so neither can
    # silently drift below capability on the paid run. Faithfulness-neutral: the ModelSpec is
    # structured DATA validated downstream by build_quantified_spec, never verified prose; a generous
    # cap is billed by actual usage (free insurance), and bounding reasoning only guarantees the
    # model reaches the content phase.
    "PG_QUANTIFIED_SPEC_MAX_TOKENS": "32768",
    "PG_QUANTIFIED_SPEC_REASONING_MAX_TOKENS": "8192",
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
    # I-deepfix-001 BREADTH (§-1.3 DELETE the bolt-on, not just default-0): the per-source citation cap
    # `PG_SPAN_PER_SOURCE_CITE_CAP` (the operator's EXACT named §-1.3 BANNED bolt-on) has been DELETED
    # from fact_dedup.py — the knob + its drop path are gone, so there is no env to pin here any more.
    # The slate force-exact entry + the preflight-required entry below were removed with it.
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
    # I-deepfix-001 (#1344) PURITY: STORM is dead — 0 the under-fire floor so the INVERTED run-health
    # abort_discovery_degraded can never trip on a (correctly) absent STORM. PG_RUN_HEALTH_GATE stays ON.
    "PG_STORM_MIN_EFFECTIVE_QUERIES": "0",
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
    # I-deepfix-001 (#1344) PURITY: STORM is dead — 0 the seed-URL ingest lane (removed from FORCE_ON +
    # added to REQUIRED_OFF below). Dies with the engine; this also fails closed if it is ever re-armed.
    "PG_STORM_INGEST_WEB_RESULTS": "0",
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
    # drb_72 / I-deepfix-001 (#1344): the corpus_approval REFUSAL fix. run_gate_b force-sets
    # PG_BENCHMARK_STRICT_GATES=1 (below), which RE-IMPOSES the #1235 hard tier-COUNT refusal on a
    # MATERIAL tier deviation EVEN WHEN the weighted-corpus gate is ON — so an ADEQUATE workforce corpus
    # whose credible NON-JOURNAL think-tank sources (NBER/Brookings/HBS/McKinsey/OECD = tier T4) push T4
    # above the workforce-protocol expected-max is REFUSED (abort_corpus_approval_denied) with ZERO
    # generator tokens. That refusal is the §-1.3-banned FILTER-not-WEIGHT (it verifies NO individual
    # claim; the credible non-journals are legitimate primary sources at their real weight). The
    # purpose-built kill-switch PG_WEIGHTED_GATE_PROCEED_ON_SKEW (run_honest_sweep_r3.py:1518) relaxes
    # ONLY that hard tier-COUNT refusal into DISCLOSE-and-PROCEED via the credibility-weighted path, and
    # ONLY when the weighted gate is ON AND the corpus-ZERO floor passes (non-empty). The adequacy gate
    # (real insufficiency STILL aborts — §9.1.5), the corpus-ZERO floor (has_usable_corpus — an EMPTY
    # corpus STILL refuses), and the per-claim faithfulness engine (strict_verify / NLI / 4-role D8 /
    # provenance) are ALL untouched. Force-on + required + allowlisted below so a stray operator =0 cannot
    # silently re-impose the refusal on the paid run (I-cap-005 P1-1 force-on pattern; the exact slate
    # discipline PG_SWEEP_WEIGHTED_CORPUS_GATE itself carries above).
    "PG_WEIGHTED_GATE_PROCEED_ON_SKEW": "1",
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
    # I-beatboth-008 (#1285) commit-2 build A: raise the credibility-pass parallelism 16 -> 20. The
    # WALL_S sizing invariant still holds with margin (worst healthy ~619 members @ 40s / inflight-20 ≈
    # 1238s < 3000s wall, MORE headroom than the inflight-16 ≈ 1548s). Read at call time
    # (credibility_pass._pass_max_inflight, force-EXACT below). Concurrency only — verdicts unchanged.
    "PG_CREDIBILITY_PASS_MAX_INFLIGHT": "20",
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
    # I-deepfix-001 W07-credibility-tiering-batch-wall (#1344): a tiering BLANK is advisory
    # (the un-tiered source keeps the deterministic rules-floor — a WEIGHT, never a drop), so
    # the W5 tiering caller does NOT need the full retry budget the binding D8 verifier does.
    # Cap the total-deadline retries to 1 so a blank/trickle storm cannot multiply the per-call
    # budget across retries inside the batch wall. Force-exact (a wall/retry knob).
    "PG_CREDIBILITY_JUDGE_TOTAL_DEADLINE_RETRIES": "1",
    # The W5 LLM-tiering batch TOTAL wall (W07): even when the per-question retrieval wall is
    # threaded, this is the standalone batch cap so a mirror blank-200 storm cannot grind the
    # post-loop tiering batch (run_live_retrieval runs SYNC on the event loop, so the run-level
    # wall cannot preempt it). Generous; the un-returned sources keep the rules-floor.
    "PG_TIER_LLM_BATCH_WALL_SECONDS": "600",
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
    # I-deepfix-001 (#1344) PURITY: PG_STORM_OUTLINE_SECTIONS is a STORM consumer (the outline scaffold) —
    # killed to "0" (removed from FORCE_ON + REQUIRED below; NOT in the W14 winner allowlist). Section
    # structure reverts to research_plan/legacy, which KEEPS the compose=floor_abstractive winner #12
    # (PG_VERIFIED_COMPOSE) intact — composition is downstream of the scaffold and unchanged. The other 3
    # composition flags below ARE winners and STAY "1".
    "PG_STORM_OUTLINE_SECTIONS": "0",
    "PG_BASKET_CORROBORATION_RENDER": "1",
    "PG_VERIFIED_COMPOSE": "1",
    "PG_SYNTHESIS_ABSTRACT_CONCLUSION": "1",
    # I-wire-013 (#1327): the grounded DEPTH cross-source SYNTHESIS layer. Default-OFF in code so a
    # non-benchmark run is byte-identical; slate-pinned "1" (+ force-ON below) so the cert run actually
    # consolidates each high-corroboration basket into ONE cross-source finding (key_findings>0). The
    # synthesis is RE-GROUNDED through the UNCHANGED strict_verify (a synthesized sentence with no
    # grounding span is DROPPED — drop-not-fallback), so it is faithfulness-SAFE: zero new fabrication.
    "PG_SWEEP_DEPTH_LAYER": "1",
    # I-deepfix-001 (#1344) COVERAGE LEVERS (DRB-II) — ARM the 8 weight-and-consolidate breadth levers that
    # were BUILT + triple-gated but sat DARK (default-OFF, absent from the paid slate). §-1.3 DNA-ALIGNED:
    # each makes breadth EMERGE from honest weighted multi-attribution — NOT a hardcoded cap/target/thinner/
    # canary (BANNED). O1 facet outline: section count emerges from evidence clusters (non-clinical only;
    # clinical/unknown byte-identical). F1 route-all-baskets: consolidate-do-not-drop the ~600 stranded
    # verified baskets into section plans (nothing capped). F2/F5: the per-section evidence + word budgets
    # TRACK the full matched payload (remove the row/word CEILING — a cap removal, not a new floor). R1/R2:
    # expert facet planner + facet completeness widen retrieval breadth (the FS-Researcher path; compute-
    # safety bounds keyed to source YIELD, never a breadth number). D1/D4: within-basket verbatim qualifier
    # elaboration + facet-routed enrichment placement (both ADDITIVE keep-all, faithfulness-neutral). D1/D4
    # were previously armed ONLY by run_honest_sweep_r3.apply_winner_slate_on_paid_path (called in main_async,
    # which the Gate-B launcher never invokes) -> DARK on the Gate-B path; slate-pinning them here arms them
    # on the Gate-B launcher too. Each is DEFAULT-OFF in code (flag-OFF byte-identical); slate-pinned "1" so
    # apply_full_capability_benchmark_slate FORCE-sets it (each is in _BENCHMARK_FORCE_ON_FLAGS below) + each
    # is _BENCHMARK_PREFLIGHT_REQUIRED_FLAGS (fail-closed pre-spend) + _WINNER_FLAG_ALLOWLIST (SLATE-PURITY) +
    # asserted by assert_coverage_levers_armed() before spend. FAITHFULNESS-NEUTRAL: every surfaced/routed
    # source re-passes the UNCHANGED strict_verify / NLI / 4-role / provenance / span-grounding per claim.
    "PG_FACET_OUTLINE": "1",              # O1 facet outline (section count emerges from clusters)
    "PG_ROUTE_ALL_BASKETS": "1",          # F1 route-every-verified-basket (consolidate-don't-drop the stranded baskets)
    "PG_EV_BUDGET_TRACKS_PAYLOAD": "1",   # F2 per-section evidence budget tracks full matched payload (ceiling removed)
    "PG_WORD_BUDGET_TRACKS_PAYLOAD": "1", # F5 per-section word budget tracks full routed payload (clamp removed)
    "PG_EXPERT_FACET_PLANNER": "1",       # R1 expert facet planner (widen retrieval breadth; yield-keyed safety bounds)
    "PG_FACET_COMPLETENESS": "1",         # R2 facet completeness (retrieval-breadth completeness pass)
    "PG_QUALIFIER_ELABORATION": "1",      # D1 within-basket verbatim qualifier elaboration (keep-all, re-verified)
    "PG_ENRICHMENT_FACET_ROUTE": "1",     # D4 facet-routed enrichment placement (unbound-but-verified members)
    # I-deepfix-001 (#1344) Box C L2 — SUB-TOPIC DECOMPOSITION (the highest-value DRB-II Recall lever):
    # each per-basket producer emits ONE verified verbatim-span sentence PER DISTINCT atomic fact the
    # basket already grounds (deduped, keep-all consolidation) instead of a single headline — more Recall
    # from the corpus already fetched, ZERO new fetching. Faithfulness-neutral (each unit re-passes the
    # UNCHANGED strict_verify — it IS a verbatim span). DEFAULT-OFF in code (flag-OFF byte-identical);
    # slate-pinned "1" (force-ON + preflight-required + allowlisted + assert_coverage_levers_armed).
    "PG_SUBTOPIC_DECOMPOSITION": "1",     # L2 sub-topic decomposition (one verbatim-span sentence per distinct atomic fact)
    # I-deepfix-001 (#1344) Box C L5 — QUESTION/FACET-DERIVED REQUIRED-ENTITY COVERAGE lane: derives the
    # must-cover entity set from the question + R1 planner facets OFFLINE and fetches ONLY the still-missing
    # ones through the SAME live-retrieval chokepoint (seed-only). DEFAULT-ON in code (a byte-identical no-op
    # only if PG_COVERAGE_L5_REQUIRED_ENTITY is explicitly 0); slate-pinned "1" here as belt-and-suspenders so
    # a stray operator/.env =0 cannot leave the lane DARK on the paid run (the drb_72 dark-winner class).
    # DISTINCT force-ON slate flag (slate "1" + _BENCHMARK_FORCE_ON_FLAGS force-set + _WINNER_FLAG_ALLOWLIST),
    # NOT folded into the _COVERAGE_LEVER_FLAGS 8-dark assertion (force-ON already pins it to "1"). §-1.3
    # DNA-ALIGNED (breadth EMERGES from honest weighted multi-attribution — NO cap/target/thinner); every
    # fetched source re-passes the UNCHANGED strict_verify / NLI / 4-role / provenance / span-grounding.
    "PG_COVERAGE_L5_REQUIRED_ENTITY": "1", # L5 question/facet-derived required-entity coverage lane
    # I-beatboth-011 keystone-F1 (#1284, Codex gate P0): the multi-citation synthesis flag MUST ride the
    # slate (force-ON + preflight-required) or the keystone is WIRED-BUT-DEAD on the paid run — the exact
    # false-done the gate caught. ON => a >=2-DISTINCT-origin basket renders as ONE multi-cited sentence
    # surfacing all its corroborators; each clause re-passes the UNCHANGED strict_verify; flag-OFF byte-id.
    "PG_VERIFIED_COMPOSE_MULTICITED": "1",
    # I-beatboth-011 KEYSTONE (#1289): the bake-off-winning span-quality gate (F1 0.568, ~2x the best
    # heuristic) MUST ride the slate (force-ON + preflight-required) or the chrome/junk render fix is
    # WIRED-BUT-DEAD on the paid run — the exact false-done class this issue exists to kill. ON => the
    # rendered Key-Findings + Analytical-synthesis rollup finding units are screened by the GLM-5.2 LLM
    # judge and a unit it flags is_junk=True (scraped_heading/masthead/truncation/orphan_citation) is
    # WITHHELD from the rollup surface — §-1.3 FLAG-NOT-DROP: never deleted from the body / evidence /
    # bibliography, only excluded from the summary. Flag-OFF (default) => the gate makes ZERO LLM calls
    # and returns every unit is_junk=False, so report.md is byte-identical. The gate's GLM-5.2 caller
    # builds via the credibility control surface, whose check_family_segregation requires
    # PG_PERMIT_GENERATOR_EVALUATOR_SAME_FAMILY=1 (already set for the all-GLM-5.2 stack); without it the
    # gate fails SAFE (every unit pass-through) — confirmed below. FAITHFULNESS-NEUTRAL: an
    # extraction-integrity classifier, not a credibility/relevance filter; strict_verify/NLI/4-role/span
    # are UNTOUCHED.
    "PG_SPAN_QUALITY_GATE": "1",
    # Drift-protection: the module default is already z-ai/glm-5.2 (the §9.1.8 side-judge->mirror mapping +
    # the measured F1 topper); pin it so a stray operator value cannot silently swap the judge model.
    "PG_SPAN_QUALITY_GATE_PRIMARY_MODEL": "z-ai/glm-5.2",
    # I-beatboth-011 KEYSTONE (#1289): the I-extract-001 Layer-A fetch-side companions to the span gate.
    # PG_HTML_EXTRACTOR=trafilatura_precision favors precision on extraction (fewer page-furniture spans
    # enter the corpus in the first place — the upstream half of the chrome fix); PG_BLOCK_PAGE_DETECTOR=1
    # re-routes/re-fetches a block/stub page so a login-wall/CAPTCHA stub never becomes a "fetched" source.
    # Both are FAITHFULNESS-SAFE (they improve the INPUT corpus; touch no gate). PG_HTML_EXTRACTOR is a
    # STRING value -> it CANNOT ride the truthy required-flags loop; it is force-EXACT + value-equals-
    # asserted in preflight_full_capability (the PG_RELEVANCE_SCORER precedent). PG_BLOCK_PAGE_DETECTOR is
    # a boolean -> force-ON + preflight-required.
    "PG_HTML_EXTRACTOR": "trafilatura_precision",
    "PG_BLOCK_PAGE_DETECTOR": "1",
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
    # I-beatboth-008 (#1285) commit-2 build A: widen the distill MAP fan-out 8 -> 12 (more sources in
    # flight; the per-call wall above bounds each one). Read at call time in the sweep chain (imported
    # AFTER the slate) — env-set lands without a rebind. A worker/concurrency knob only: it changes how
    # many MAP calls run in parallel, never the per-call prompt envelope or which findings are produced.
    # (Codex commit-2 iter-2 P1-1: PG_DISTILL_MICROBATCH_SIZE was REMOVED from this slate — it batches
    # sources PER distill MAP call, changing the LLM prompt envelope + WHICH findings are produced, so it
    # is faithfulness-adjacent and out of scope for a parallelism-only commit.) Breadth-positive throughput
    # only; consolidate-keep-all DNA + faithfulness gates untouched.
    "PG_DISTILL_MAX_PARALLEL": "12",
    # I-arch-011 FIX-C (run #6 enrichment-verify "freeze" — the wiring gap): the I-arch-006 fix#19
    # bounded-PARALLEL findings verify (provenance_generator._parallel_verify_workers) exists but was
    # NEVER set in the slate, so the 737-source breadth-enrichment section verified its ~1839
    # sentence-units SERIALLY. At a healthy ~5.7s/call that is ~173min for ONE section — it blows the
    # run wall and looks frozen (the run-#6 "deadlock" was this serial grind, NOT a per-call deadlock;
    # the per-call total-deadline was proven sound by scripts/iarch011_entailment_deadline_repro.py).
    # Cap concurrency at 16 (matches PG_CREDIBILITY_PASS_MAX_INFLIGHT). The per-call total-deadline in
    # entailment_judge (PG_ENTAILMENT_TOTAL_S, now slate-pinned to 300 per idx53) is what makes it HANG-SAFE — parallelism alone is not
    # (list(map())+shutdown(wait=True) would block on a never-returning future). FAITHFULNESS-NEUTRAL:
    # the parallel path copies the parent contextvars context and ``map`` preserves input order, so
    # kept/dropped is byte-identical to the serial loop (concurrency changes timing, not verdicts); a
    # worker exception still propagates fail-loud. Behavioral proof on the banked drb_78 corpus + REAL
    # glm-5.1 judge (scripts/iarch011_parallel_verify_gate.py): the enrichment verify COMPLETES in
    # 17.4min (was ~173min serial) and keeps 1746 cited / 657 distinct sources on the enforce path.
    # I-beatboth-008 (#1285) commit-2 build A: raise the bounded findings-verify parallelism 16 -> 24.
    # The per-call total-deadline in entailment_judge (PG_ENTAILMENT_TOTAL_S) is what keeps it HANG-SAFE;
    # 24 only widens how many in flight. Read at call time (provenance_generator._parallel_verify_workers,
    # force-EXACT below). FAITHFULNESS-NEUTRAL: ``map`` preserves input order + copies the parent
    # contextvars context, so kept/dropped is byte-identical to serial — concurrency changes timing only.
    "PG_PARALLEL_VERIFY": "24",
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
    # ─────────────────────────────────────────────────────────────────────────────────────────────
    # I-beatboth-008 (#1285) commit-2 build A — PARALLELISM SLATE (worker counts / concurrency only;
    # NO verification logic touched). FAITHFULNESS-NEUTRAL throughout: every knob below changes only how
    # many units run concurrently, never which units pass/drop. The 5 EXISTING slate values raised above
    # (PG_PARALLEL_VERIFY 16->24, PG_CREDIBILITY_PASS_MAX_INFLIGHT 16->20, PG_DISTILL_MAX_PARALLEL 8->12,
    # PG_LIVE_RETRIEVER_MAX_WORKERS 16->24->48 [L1 dual-gated speed lever], PG_MAX_CONCURRENT_LLM 5->8)
    # live at their original sites; the NEW knobs that have no prior slate home are added here.
    #
    # PG_FOUR_ROLE_CLAIM_WORKERS: per-claim Mirror->Sentinel->Judge compute parallelism in the D8 seam.
    # CRITICAL import-timing (#1285 comment): sweep_integration.py:155 reads this AT IMPORT into the
    # module global `_CLAIM_WORKERS = max(1, int(os.getenv("PG_FOUR_ROLE_CLAIM_WORKERS","6")))`, and
    # run_gate_b.py:61 imports sweep_integration at THIS module's OWN top level — which executes BEFORE
    # apply_full_capability_benchmark_slate() ever runs. So setting the env in the slate alone is a SILENT
    # NO-OP: `_CLAIM_WORKERS` is already frozen at the default. apply_full_capability_benchmark_slate()
    # therefore REBINDS the live module attribute after the floor loop (see the rebind block in that
    # function) so the slate value ACTUALLY takes effect. The seam reads `_CLAIM_WORKERS` as a module
    # global at CALL time (sweep_integration.py:493/600/625), so the post-import reassignment is honored.
    "PG_FOUR_ROLE_CLAIM_WORKERS": "12",
    # I-wire-003 B1 (#1317): bound concurrent JUDGE POSTs UNDER the sustainable OpenRouter rate. With
    # PG_FOUR_ROLE_CLAIM_WORKERS=12 each firing mirror->sentinel->judge, the single rate-limited qwen
    # Judge saw up to ~12 simultaneous POSTs -> the 429 STORM (21 judge HTTP-429s, 153/1220 claims in
    # ~77 min). This caps concurrent Judge POSTs to a small STEADY value that stays under the throttle
    # (a steady-but-slower judge with full-jitter backoff finishes FASTER than a storm that 429s and
    # burns minutes in retry). Mirror/Sentinel parallelism is UNTOUCHED (only the judge role acquires
    # the throttle). FAITHFULNESS-NEUTRAL: concurrency only — never which claim passes/holds. The
    # transport reads this LAZILY on first judge call, so the slate value (set after import) is honored
    # without a rebind hook. Calibrate via the four_role_rate_limit_telemetry.json the run now writes.
    "PG_FOUR_ROLE_JUDGE_CONCURRENCY": "4",
    # I-beatboth-011 idx19 (#1289): pin the D8 4-role reasoning effort to MEDIUM in the FULL slate. It was
    # pinned ONLY in _SMOKE_SCALE_OVERRIDES, so a full benchmark ran the qwen Judge at the
    # apply-default xhigh (the setter below defaults to "xhigh") — the judge then spends its whole token
    # budget on reasoning before the 5-token enum verdict, minute-scale per claim (the D8 grind the
    # coverage map traced). medium returns content even on the slow providers (per the standing
    # fact_mirror_blank_xhigh_effort prescription). FAITHFULNESS-NEUTRAL: the verdict ladder already falls
    # back to "low"; effort governs latency, not the gate. Force-EXACT below so it reaches the live setter.
    "PG_FOUR_ROLE_REASONING_EFFORT": "medium",
    # I-beatboth-011 idx53 (#1289): the per-claim entailment total-deadline. It was set NOWHERE in the
    # slate, so verify ran at the 150s CODE default (not the 45s the stale comments above claimed) — a slow
    # GLM call holds a worker slot up to 150s. 300 matches the sibling per-call walls
    # PG_CREDIBILITY_JUDGE_TOTAL_S / PG_ROLE_TRANSPORT_TOTAL_S (=300). NOT 45: 45 is only ~5s above the 40s
    # healthy max and would force-close valid 41–60s calls → fail-closed sentinel → a §-1.3
    # lose-a-corroborator DROP. Read at call time in entailment_judge; force-EXACT below.
    "PG_ENTAILMENT_TOTAL_S": "300",
    # Section-parallelism (concurrency only; faithfulness-NEUTRAL — each section is still generated and
    # verified INDEPENDENTLY and IDENTICALLY, results merged back in the original `plans` order; the knob
    # is a Semaphore bound, never a section TARGET). Two collaborating envs, BOTH set to 6 so section
    # concurrency is genuinely 6 on every path:
    #   - PG_MAX_PARALLEL_SECTIONS IS consumed: run_honest_sweep_r3.py:8806 reads it as the
    #     `max_parallel_sections` kwarg default to generate_multi_section_report (default "3"). (The prior
    #     comment here claimed "no consumer in src/" — that was STALE/WRONG; corrected per Codex commit-2
    #     iter-2 P2.)
    #   - PG_PARALLEL_SECTIONS is the per-call OVERRIDE: multi_section_generator.py:7242 reads it at CALL
    #     time and, when >=1, REPLACES the caller-supplied max_parallel_sections kwarg.
    # Setting the kwarg-default (PG_MAX_PARALLEL_SECTIONS=6) AND the override (PG_PARALLEL_SECTIONS=6)
    # makes 6 the effective section concurrency regardless of which path constructs the generator.
    "PG_MAX_PARALLEL_SECTIONS": "6",
    "PG_PARALLEL_SECTIONS": "6",
    # PG_BYPASS_MAX_INFLIGHT: AccessBypass concurrent-fetch ceiling (access_bypass.py:319, read at CALL
    # time inside the fetch path; module pulled via the sweep chain AFTER the slate, so the env-set lands
    # without a rebind). 20 widens the paywall-bypass fan-out — fetch throughput only.
    "PG_BYPASS_MAX_INFLIGHT": "20",
    # PG_STORM_CONCURRENCY: parallel STORM interviews (storm_interviews.py:1410, read at CALL time;
    # imported via the sweep chain after the slate). 8 doubles the default-4 interview fan-out so the
    # outline-research phase finishes sooner. Discovery throughput only — faithfulness-neutral.
    "PG_STORM_CONCURRENCY": "8",
    # ─────────────────────────────────────────────────────────────────────────────────────────────
    # I-wire-013 (#1327): the render chrome-as-claim CANARY runs in ENFORCE on the cert run. The
    # function now DEFAULTS to enforce, but force-EXACT it here (a STRING value -> rides
    # _BENCHMARK_FORCE_EXACT_FLAGS below, NOT the numeric FLOOR path which would crash on
    # float("enforce")) so a stray operator PG_RENDER_CHROME_CANARY=warn|off cannot silently downgrade
    # the tripwire to telemetry-only on a paid run. FAITHFULNESS-NEUTRAL: the canary asserts NO content —
    # it only REFUSES to ship a chrome-saturated (untrustworthy) report.md.
    "PG_RENDER_CHROME_CANARY": "enforce",
    # ─────────────────────────────────────────────────────────────────────────────────────────────
    # I-wire-001 (#1296 section-winner board): force-set the LOCKED section winners so a Gate-B run
    # exercises the winning slate REGARDLESS of the operator's .env. Each flag is DEFAULT-OFF (or a
    # default model) in code so a non-benchmark run stays byte-identical; the slate ACTIVATES the winner
    # and the frozensets below FORCE it (a stray operator =0 / other-model cannot survive — the recurring
    # "built-but-left-off" / silent-downgrade trap). FAITHFULNESS-NEUTRAL throughout: every winner is a
    # retrieval / selection / consolidation / scope ROUTING or MODEL choice — none touches strict_verify /
    # the 4-role D8 seam / provenance / NLI entailment (the FROZEN faithfulness engine). 11 winner flags
    # are WIRED on the run path (each verified to have a live consumer that executes during run_one_query);
    # the 1 build-deferred winner (W9 dedup) is handled by a LOUD preflight WARNING in
    # preflight_full_capability — NOT preflight-required — so a paid run never FALSE-PASSES on a winner
    # whose consumer is not yet on the run path. SLATE-SET + PREFLIGHT-GATED IS NOT "FIRED": firing is
    # proven only by the e2e firing canary / §-1.1 audit, never by this env gate.
    #
    # BOOLEAN winners (force-ON below + truthy-preflight-required): each consumer reads the flag truthy.
    "PG_QGEN_FS_RESEARCHER": "1",        # W2 qgen=FS-Researcher (run_honest_sweep_r3:7118 _run_fs_researcher_retrieval)
    "PG_SEARCH_FUSION_WRRF": "1",        # W3 fusion=WRRF (domain_backends:69 / search_fusion_wrrf:55)
    "PG_CONTENT_RELEVANCE_JUDGE": "1",   # W5 relevance=Qwen3-Rerank-0.6B+GLM judge (content_relevance_judge:77 / live_retriever:459)
    "PG_CREDIBILITY_LLM_TIERING": "1",   # W8 cred=llm_tiering (tier_classifier:1233 / live_retriever:4178)
    "PG_CONSOLIDATION_NLI": "1",         # W10 consolidate=NLI (finding_dedup:585 / consolidation_nli:67)
    # I-deepfix-001 (#1344) WS-2 M6 (BEATBOTH_PLAN_CORRECTIONS): the CROSS-SOURCE ANALYTICAL layer.
    # DEFAULT-OFF (verified_compose.py:167-168) — the re-smoke had to set it by hand, so a paid Gate-B
    # run silently shipped NO analysis (M6 dark, "Comparative Assessment" gap-stub). Slate-pin "1" so
    # apply_full_capability_benchmark_slate FORCE-sets it (it is in _BENCHMARK_FORCE_ON_FLAGS below);
    # ALSO in _BENCHMARK_PREFLIGHT_REQUIRED_FLAGS (fail-closed pre-spend) + _WINNER_FLAG_ALLOWLIST
    # (SLATE-PURITY). FAITHFULNESS-NEUTRAL: each analytical sentence's two atoms re-pass the UNCHANGED
    # strict_verify per clause; the connective is engine-LICENSED (cross_source_synthesis.license_relation).
    # M2 (PG_DOCUMENT_TYPE_WEIGHT) stays OUT of the global slate (WS-8: journal-only template only).
    "PG_CROSS_SOURCE_SYNTHESIS": "1",    # M6 cross-source analytical layer (verified_compose:167 / cross_source_synthesis:214)
    "PG_ADEQUACY_CRAG": "1",             # W11 adequacy=CRAG (run_honest_sweep_r3:7446 CRAG loop)
    # W1 scope=intent_frame: the MODULE (src/polaris_graph/nodes/intent_frame.py) is built + flag-aware,
    # and run_intent_frame() is NOW called on the sweep scope-gate path (run_honest_sweep_r3.py:6426,
    # gated by intent_frame_enabled()/PG_SCOPE_INTENT_FRAME and FAIL-CLOSED when enabled — it raises
    # IntentFrameError that is deliberately NOT caught). I-wire-001 P1-1: it therefore GRADUATED out of
    # the build-deferred WARNING into _BENCHMARK_PREFLIGHT_REQUIRED_FLAGS below (a live run-path consumer
    # now reads it, so requiring it can no longer FALSE-PASS). The advisory intent decomposition runs IN
    # FRONT OF the binding run_scope_gate. FAITHFULNESS-NEUTRAL: advisory routing context only;
    # run_scope_gate stays the single binding gate.
    "PG_SCOPE_INTENT_FRAME": "1",
    # STRING (model-selector) winners (force-EXACT below + value-equals-asserted in preflight — they
    # CANNOT ride the truthy required-flags loop, which only accepts "1"/"true"/"True", the same reason
    # PG_RELEVANCE_SCORER is asserted separately). A model winner silently OFF = the default model runs.
    "PG_CLINICAL_PDF_EXTRACTOR": "mineru25",                       # W4 clinical-PDF (access_bypass:2968; else docling/PyMuPDF)
    "PG_EMBEDDER_MODEL": "qwen3",                                  # W6 embed=Qwen3-Embedding-8B (config/core:195, embedding_service:59; else MiniLM)
    "PG_RERANKER_MODEL": "qwen3",                                  # W7 rerank=Qwen3-Reranker-4B (config/core:218, evidence_selector:2306; else MiniLM/identity)
    "PG_CONTENT_RELEVANCE_RERANKER_MODEL": "Qwen/Qwen3-Reranker-0.6B",  # W5 relevance reranker model (content_relevance_judge:182)
    # I-deepfix-001 (#1344) WS-0: the W5 content-relevance reranker (Qwen3-Reranker-0.6B) scores the WHOLE
    # candidate pool in ONE forward pass by default (PG_CONTENT_RELEVANCE_SCORE_CHUNK unset => 0 => one pass,
    # content_relevance_judge.py:451). Co-resident on ONE card with the Qwen3-Embedding-8B, that one-pass
    # [pairs x seq x ~152k-vocab] logits tensor OOMs and the scorer FALLS BACK to full weight for every
    # passage (W5 silently dark — the drb_72 W5-dark keystone). Pin the score-chunk to 2 so each forward is
    # bounded. Chunked scores are BYTE-IDENTICAL to one-pass (global-longest padding, content_relevance_judge.
    # py:457-464) => faithfulness-neutral WEIGHT. Force-EXACT "2" (in _BENCHMARK_FORCE_EXACT_FLAGS) — NOT a
    # FLOOR: a stray HIGHER operator/.env value (a scratchpad launcher exports 8) would re-open the one-pass
    # OOM, so pin EXACTLY 2. Numeric => the SLATE-PURITY gate skips it (infra config, not a feature-enable).
    "PG_CONTENT_RELEVANCE_SCORE_CHUNK": "2",  # WS-0: bound the W5 reranker forward pass (avoid one-pass co-resident OOM)
    # ─────────────────────────────────────────────────────────────────────────────────────────────
    # I-deepfix-001 U11 (Codex P1) — CLINICAL RECALL LIFT. These three were DARK on the paid run: the
    # evidence-type expansion is default-OFF in code, the S2 hit cap defaulted to 20, and WRRF (W3, force-
    # ON above) ran with NO academic-engine weights — so the claimed high-tier (RCT / SR-MA / guideline)
    # recall lift never fired. Activate them in the slate. FAITHFULNESS-NEUTRAL / §-1.3 WEIGHT-not-FILTER:
    # each is purely ADDITIVE discovery (more queries, higher hit caps, an engine-ranking weight) — no
    # source is dropped/capped/thinned, and every added candidate flows through the UNCHANGED fetch ->
    # tier -> strict_verify / NLI / provenance chokepoint. The FROZEN faithfulness engine is untouched.
    #
    # PG_EVIDENCE_TYPE_QUERY_EXPANSION (evidence_type_query_expansion.py:51) — float-parseable "1", so it
    # takes the numeric-FLOOR path (max(existing,1) => forces ON even past a stray operator "0") and
    # SLATE-PURITY skips it (float-parseable => infra, not a winner-checked feature-enable). Read at CALL
    # time by the live retriever, so the env-set lands without an import-time freeze.
    "PG_EVIDENCE_TYPE_QUERY_EXPANSION": "1",  # U11: activate high-tier evidence-type query expansion
    # Raise the primary-literature hit caps so the RCT/SR-MA/guideline results SURFACE above generic web.
    # PG_LIVE_MAX_S2 => live_retriever.DEFAULT_MAX_S2 (was default 20); PG_DOMAIN_MAX_HITS => the
    # europe_pmc / openalex / arxiv / s2 backend per-engine cap (was default 10). Numeric FLOOR entries
    # (max(existing, slate)): an operator may raise them but never silently drop below the U11 floor.
    "PG_LIVE_MAX_S2": "50",       # U11: S2 hit cap 20 -> 50 (the "DEFAULT_MAX_S2 stays 20" Codex flagged)
    "PG_DOMAIN_MAX_HITS": "50",   # U11: academic-backend per-engine hit cap 10 -> 50
    # WRRF engine weights (search_fusion_wrrf.py:104). WRRF is force-ON (W3) but had no weights, so every
    # engine used the default weight and a NEJM/OpenAlex #1 could be outranked by a marketing-page serper
    # #1. Lift the academic / clinical registries (openalex / europe_pmc / semantic_scholar / pubmed)
    # ABOVE generic web (serper). A NON-NUMERIC STRING => it MUST be force-EXACT (the numeric-FLOOR path
    # crashes on float("serper:...")) and, being a non-numeric string pin, is allowlisted in
    # _WINNER_FLAG_ALLOWLIST as the config for the W3 WRRF winner. The live retriever namespaces backends
    # as domain:<name>/need:<name> and the weights lookup falls back to the part after the namespace, so
    # "europe_pmc:1.3" matches the "domain:europe_pmc" engine.
    "PG_SEARCH_FUSION_WRRF_WEIGHTS": (
        "serper:1.0,openalex:1.3,europe_pmc:1.3,semantic_scholar:1.2,s2:1.2,pubmed:1.3,arxiv:1.1"
    ),
    # ─────────────────────────────────────────────────────────────────────────────────────────────
    # WINNERS ALREADY COVERED by EXISTING slate entries (kept intact, NOT re-added):
    #   W12 compose=floor_abstractive  -> PG_ABSTRACTIVE_WRITER (force-ON + preflight-required above)
    #   W13 verify=keep-floor          -> PG_STRICT_VERIFY_ENTAILMENT=enforce + the FROZEN faithfulness engine
    #   W14 render=det                 -> deterministic render (default) + PG_RENDER_CHROME_CANARY=enforce
    # W9 dedup=ContentDeduplicator: GRADUATED from build-deferred to a wired winner (I-deepfix-001
    #   #1344). The consolidate-keep-all content-dedup stage this comment previously demanded as the
    #   precondition NOW EXISTS: src/polaris_graph/synthesis/content_dedup_consolidate.py groups
    #   different-title near-identical-BODY syndicated sources (the residual gap finding_dedup's DOI/
    #   folded-title keying misses) into keep-all corroboration baskets — ANNOTATE-only, never drop,
    #   never merge (§-1.3). It is wired on the generator's post-retraction pool
    #   (multi_section_generator.consolidate_body_syndication) with a firing canary
    #   ([content_dedup_consolidate] W9: ...) + the body_syndication manifest telemetry, so its firing
    #   is OBSERVABLE (no longer the build-deferred ABSENCE). The §-1.3-VIOLATING DROP variant
    #   (PG_W9_CONTENT_DEDUP -> ContentDeduplicator.unique_items, which sheds corroborators) STAYS
    #   forbidden by the W9 GATE at the end of preflight_full_capability. The keep-all winner is
    #   force-ON here + preflight-required + allowlisted (the conscious "winner" decision).
    "PG_CONTENT_DEDUP_CONSOLIDATE": "1",                          # W9 dedup=ContentDeduplicator consolidate-keep-all (content_dedup_consolidate.py)
    # SMOKE NOTE: _SMOKE_SCALE_OVERRIDES inherits the real EMBED/RERANK winners (Qwen3 embed/rerank) as
    # genuine model-loading plumbing coverage — a smoke on the default MiniLM would never exercise the
    # winner-model load path, so a load bug would surface only on the expensive full run. EXCEPTION
    # (I-deepfix-001 #1344): the smoke pins PG_CLINICAL_PDF_EXTRACTOR=docling (NOT the slate's mineru25)
    # because the mineru25 GPU-VLM crashed the whole run with a NATIVE SIGABRT (uncatchable abort() inside
    # transformers .generate(), rc=134) before the back half ran — so the smoke validates the back-half
    # plumbing on the safe docling->PyMuPDF PDF path. mineru25 firing + its crash-isolation (subprocess/
    # hard-kill) is the queued fix before the paid run. Gate-B model-loading runs land on the GPU VM per
    # the VM-only run policy.
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
    # query counts, NOT part of the ~1000-URL fetch sum. Floor == the slate value (15).
    # I-deepfix-001 (#1344) PURITY: PG_STORM_MAX_BENCHMARK_QUERIES floor removed — STORM is dead, no
    # query-count floor should linger (it is slate "0" + force-EXACT not applicable; the cap dies with
    # the engine). PG_MAX_SUBQUERIES (the legacy decompose count) keeps its floor.
    "PG_MAX_SUBQUERIES": 15,
    # I-wire-005 B-B (#1319): floor-guard the Phase-7 quantified-spec Writer budgets so a
    # conservative .env/operator value cannot silently starve the spec call below capability and
    # silently no-op the differentiator on the paid run (the B-B failure). Floors == the slate
    # values; force-EXACT below additionally pins them so a value ABOVE the floor also cannot drift.
    "PG_QUANTIFIED_SPEC_MAX_TOKENS": 32768,
    "PG_QUANTIFIED_SPEC_REASONING_MAX_TOKENS": 8192,
}
# Flags that MUST be truthy for a full benchmark run (feature dead / unobservable otherwise).
# R1_deepener_enable (operator-authorized reversal, AskUserQuestion 2026-07-04): the old I-cap-005 P1-1
# note required PG_SWEEP_EVIDENCE_DEEPENER-truthy so an operator =0 could NOT survive the setdefault slate.
# R1 DELIBERATELY REVERSES that: the deepener is the recall lever, setdefault-ON (below) but LAW VI
# operator-override-wins — an explicit operator PG_SWEEP_EVIDENCE_DEEPENER=0 MUST now survive (the deepener
# SPENDS; the operator may legitimately run it dark). It is therefore NOT in this required-truthy tuple, NOT
# in FORCE_EXACT, and NOT in REQUIRED_OFF. When the deepener is ON but SEMANTIC_SCHOLAR_API_KEY is absent
# the slate emits a LOUD warning (fail-loud, not silent) so a dark recall lever is never a silent no-op.
_BENCHMARK_PREFLIGHT_REQUIRED_FLAGS = (
    # I-deepfix-001 (#1344) PURITY: PG_STORM_ENABLED_IN_BENCHMARK removed — STORM is a LOSER, no longer
    # required-truthy (a required-truthy flag set to "0" in the slate would itself fail the preflight).
    # It is instead force-EXACT "0" + REQUIRED_OFF below so the run fails closed if STORM is re-armed.
    # I-beatboth-011 keystone-F1 (#1284): fail-CLOSED if the multi-citation synthesis flag is off before
    # spend — the keystone's central feature must FIRE on the paid run, never be silently wired-but-dead.
    "PG_VERIFIED_COMPOSE_MULTICITED",
    # I-beatboth-011 KEYSTONE (#1289): fail-CLOSED if the span-quality gate / block-page detector are off
    # before spend — the chrome/junk rollup fix must FIRE on the paid run, never be silently wired-but-dead
    # (the exact false-done this issue exists to kill). Booleans -> safe in this truthy-required tuple.
    # (PG_HTML_EXTRACTOR is a STRING value -> value-equals-asserted separately in preflight_full_capability,
    # NOT here — it would fail the "1"/"true" check.)
    "PG_SPAN_QUALITY_GATE",
    "PG_BLOCK_PAGE_DETECTOR",
    # I-deepfix-001 (#1344) PURITY: PG_SWEEP_EVIDENCE_DEEPENER (non-winner bolt-on) and
    # PG_AGENTIC_SEARCH_IN_BENCHMARK (STORM's twin live-discovery loser) removed from required-truthy —
    # both are LOSERS, force-EXACT "0" + REQUIRED_OFF below (fail closed if either is re-armed).
    "PG_DEPTH_ANNOTATION_IN_BENCHMARK",
    "PG_NLI_IN_BENCHMARK",
    "PG_ENABLE_TOOL_TRACKER",
    # I-ready-004 (#1078): finding-dedup must be ON for Gate-B — OFF wastes the budget on near-dups.
    # PG_CAPPED_FINDING_DEDUP is NO LONGER required-truthy: I-arch-007 #1264 sets it 0 (dormant-cap
    # cleanup, ZERO cap per §-1.3); a required-truthy flag set to 0 in the slate would fail the preflight.
    # The pool is consolidated keep-all (CONSOLIDATE-DON'T-DROP); the cap is GONE, not merely bypassed.
    "PG_USE_FINDING_DEDUP",
    # I-deepfix-001 (#1344): W9 dedup=ContentDeduplicator GRADUATED to wired — the consolidate-keep-all
    # body-syndication stage (content_dedup_consolidate.consolidate_body_syndication) now fires on the
    # generator's post-retraction pool with a canary + manifest telemetry, so OFF is a silent winner-dark.
    # Fail closed if off before spend. (The §-1.3-violating DROP variant PG_W9_CONTENT_DEDUP stays
    # forbidden by the W9 GATE — distinct flag.)
    "PG_CONTENT_DEDUP_CONSOLIDATE",
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
    # I-deepfix-001 (#1344) PURITY: PG_STORM_OUTLINE_SECTIONS removed (STORM consumer, killed) — it is
    # force-EXACT "0" + REQUIRED_OFF below. The other 3 stay required (they are the W12 compose winners).
    "PG_BASKET_CORROBORATION_RENDER",
    "PG_VERIFIED_COMPOSE",
    "PG_SYNTHESIS_ABSTRACT_CONCLUSION",
    # I-beatboth-011 §3.1 ROUTE C (#1289): the abstractive writer must be ON for the cert run — OFF
    # silently reverts to the deterministic short-writer RENDER PROBE (verbatim span-dump). Fail the run
    # closed if a stray operator =0 left it off (its fail-closed activation also needs entailment=enforce).
    "PG_ABSTRACTIVE_WRITER",
    # I-cred-006b (#1170): the weighted-corpus gate must be ON for the beat-both run — OFF restores the
    # §-1.1-banned tier-count / material-deviation corpus REFUSAL that aborted the drb_72 dry-run
    # (abort_corpus_approval_denied) on a tier-skewed-but-legitimate ECONOMICS corpus. Fail closed if it
    # is not active so a tier-mix refusal can never silently reach the paid run.
    "PG_SWEEP_WEIGHTED_CORPUS_GATE",
    # drb_72 / I-deepfix-001 (#1344): PG_WEIGHTED_GATE_PROCEED_ON_SKEW must be ON for the beat-both run —
    # OFF lets PG_BENCHMARK_STRICT_GATES=1 re-impose the #1235 tier-COUNT corpus REFUSAL that aborted the
    # drb_72 official-question smoke (abort_corpus_approval_denied) on an ADEQUATE-but-tier-skewed corpus.
    # Fail CLOSED if a stray operator =0 left it off so the §-1.3 filter-not-weight refusal can never reach
    # the paid run. Disclose-and-proceed keeps the adequacy gate + corpus-ZERO floor + faithfulness engine.
    "PG_WEIGHTED_GATE_PROCEED_ON_SKEW",
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
    # I-wire-001 (#1296): the 7 WIRED BOOLEAN section winners must be ON for a paid Gate-B run — OFF
    # silently reverts each to its legacy default (FS-Researcher->legacy qgen, WRRF->no fusion,
    # content-relevance judge OFF, credibility LLM-tiering->heuristic tiers, NLI consolidation->literal
    # dedup, CRAG adequacy->count-floor, intent_frame->legacy run_scope_gate alone). Each consumer reads
    # the flag truthy and is force-ON above, so a stray operator =0 fails the run CLOSED here before spend.
    # The STRING (model-selector) winners cannot ride this truthy loop ("qwen3"/"mineru25" are not "1") —
    # they are value-equals-asserted in preflight_full_capability. W1 intent_frame is NOW wired
    # (run_honest_sweep_r3.py:6426, fail-closed) so it is required here; only W9 dedup remains
    # build-deferred -> WARNING, never required (no run-path consumer would FALSE-PASS).
    "PG_QGEN_FS_RESEARCHER",
    "PG_SEARCH_FUSION_WRRF",
    "PG_CONTENT_RELEVANCE_JUDGE",
    "PG_CREDIBILITY_LLM_TIERING",
    "PG_CONSOLIDATION_NLI",
    # I-deepfix-001 (#1344) WS-2 M6: fail-CLOSED before spend if the cross-source analytical layer is
    # off — a paid run with PG_CROSS_SOURCE_SYNTHESIS=0 silently ships zero analysis (the drb_72
    # re-smoke defect). Force-ON above, so a stray operator =0 fails the run CLOSED here. This is the
    # third of the three winner flags the WS-2 paid-preflight must reject a slate-OFF launch on
    # (PG_CONSOLIDATION_NLI + PG_BREADTH_ENRICHMENT_ENABLED are the other two, already required above).
    "PG_CROSS_SOURCE_SYNTHESIS",
    "PG_ADEQUACY_CRAG",
    # I-wire-001 P1-1: W1 scope=intent_frame GRADUATED from build-deferred to preflight-required.
    # run_intent_frame() is now CALLED on the run path (run_honest_sweep_r3.py:6426, gated by
    # intent_frame_enabled()/PG_SCOPE_INTENT_FRAME, FAIL-CLOSED when enabled), so OFF silently reverts the
    # scope path to the legacy run_scope_gate alone (no advisory intent decomposition). Force-ON in the
    # slate above; fail the run CLOSED here if a stray operator =0 left it off. FAITHFULNESS-NEUTRAL
    # (advisory routing context only; run_scope_gate stays the single binding gate).
    "PG_SCOPE_INTENT_FRAME",
    # I-deepfix-001 (#1344) COVERAGE LEVERS (DRB-II): fail-CLOSED before spend if any of the 8 weight-and-
    # consolidate breadth levers is off — a paid run with a coverage lever OFF silently ships a NARROWER
    # report (fewer facet sections / stranded verified baskets dropped / budgets clamped / thinner retrieval
    # / no qualifier elaboration / no facet-routed enrichment). Force-ON above, so a stray operator =0 fails
    # the run CLOSED here. §-1.3 DNA-ALIGNED (arm the existing default; NO new forced number introduced);
    # FAITHFULNESS-NEUTRAL (each surfaced/routed source re-passes the UNCHANGED strict_verify per claim).
    "PG_FACET_OUTLINE",              # O1 facet outline
    "PG_ROUTE_ALL_BASKETS",          # F1 route-every-verified-basket
    "PG_EV_BUDGET_TRACKS_PAYLOAD",   # F2 evidence budget tracks payload
    "PG_WORD_BUDGET_TRACKS_PAYLOAD", # F5 word budget tracks payload
    "PG_EXPERT_FACET_PLANNER",       # R1 expert facet planner
    "PG_FACET_COMPLETENESS",         # R2 facet completeness
    "PG_QUALIFIER_ELABORATION",      # D1 within-basket qualifier elaboration
    "PG_ENRICHMENT_FACET_ROUTE",     # D4 facet-routed enrichment placement
    # I-deepfix-001 loss-risk FIX-1 (H1 scope gate DARK): fail-CLOSED before spend if any of the four
    # scope+timeline ENFORCEMENT flags is off — a paid run with the scope gate dark silently ships a
    # selection byte-identical to the pre-fix (no out-of-scope demote / no anchor pin / no tier-deviation
    # disclosure). Force-ON above (slate + FORCE_ON), so a stray operator =0 fails the run CLOSED here.
    "PG_SCOPE_CONSTRAINT_ENFORCE",
    "PG_EXTRACT_SCOPE_CONSTRAINTS",
    "PG_RELEVANCE_PRESERVE_ANCHORS",
    "PG_CORPUS_TIER_DISCLOSURE_MODE",
    # I-deepfix-001 loss-risk FIX-2 (C2 wrong-question render): fail-CLOSED before spend if the official-
    # question binding is off — OFF lets the run silently GENERATE against the raw SWEEP_QUERIES prompt
    # (for drb_72 that is the I-safety-002b FIR/"English-language journal articles only" prompt, NOT the
    # canonical DRB-II idx-56 GenAI-labor question) → the split-brain that zeroed info_recall (0/57).
    # Force-set on the live run_gate_b_query path (before the override) so a benchmark run cannot answer
    # the wrong question; this required-flag makes a stray =0 fail the run CLOSED before any token spends.
    "PG_BENCHMARK_OFFICIAL_QUESTION",
)

# Codex diff-gate I-cap-005 P1-2: the minimum EFFECTIVE per-run budget cap. PG_MAX_COST_PER_RUN is an
# import-time constant in openrouter_client (cached at $10 default before Gate-B's slate runs), so the
# slate ALSO programmatically syncs it via set_max_cost_per_run(); the preflight then validates the live
# value via get_max_cost_per_run() so a stale-$10 cap cannot silently abort a full-depth paid run.
_BENCHMARK_MIN_COST_CAP_USD = 20.0

# Codex diff-gate iter-2: feature flags FORCED ON by the slate (a benchmark feature silently off via a
# conservative .env value is a capability downgrade). Everything else in the slate is a numeric FLOOR.
_BENCHMARK_FORCE_ON_FLAGS = frozenset({
    # I-deepfix-001 (#1344) PURITY: PG_STORM_ENABLED_IN_BENCHMARK + PG_SWEEP_EVIDENCE_DEEPENER removed —
    # both are LOSERS. They are force-EXACT "0" (in _BENCHMARK_FORCE_EXACT_FLAGS) + REQUIRED_OFF below.
    # I-beatboth-011 keystone-F1 (#1284): force-ON the multi-citation synthesis so a stray operator =0
    # cannot leave the keystone wired-but-dead on the paid run (the Codex-gate false-done).
    "PG_VERIFIED_COMPOSE_MULTICITED",
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
    # I-deepfix-001 (#1344) PURITY: PG_STORM_OUTLINE_SECTIONS removed (STORM consumer, killed) — it is
    # force-EXACT "0" + REQUIRED_OFF below. The other 3 stay force-ON (W12 compose winners).
    "PG_BASKET_CORROBORATION_RENDER",
    "PG_VERIFIED_COMPOSE",
    "PG_SYNTHESIS_ABSTRACT_CONCLUSION",
    # I-wire-013 (#1327): force-on the grounded DEPTH cross-source SYNTHESIS layer so a stray operator
    # =0 cannot leave it wired-but-dead on the paid run (key_findings would stay 0). Additive +
    # fail-open (a synthesis pre-pass failure omits the digest, never aborts the report); faithfulness-
    # SAFE because every synthesized sentence re-passes the UNCHANGED strict_verify or is dropped.
    "PG_SWEEP_DEPTH_LAYER",
    # I-deepfix-001 (#1344) WS-2 M6: force-on the cross-source analytical layer so a stray operator =0
    # cannot leave M6 wired-but-dead on the paid run (the drb_72 re-smoke had it OFF -> zero analysis /
    # "Comparative Assessment" gap-stub). Its own PG_CROSS_SOURCE_SYNTHESIS is DEFAULT-OFF, so it MUST be
    # force-set or it never fires. FAITHFULNESS-NEUTRAL (each analytical atom re-passes the UNCHANGED
    # strict_verify per clause; the connective is engine-LICENSED). Allowlisted in _WINNER_FLAG_ALLOWLIST
    # (SLATE-PURITY) + preflight-required above (fail-closed pre-spend).
    "PG_CROSS_SOURCE_SYNTHESIS",
    # I-beatboth-011 KEYSTONE (#1289): force-on the span-quality gate + the block-page detector so a stray
    # operator =0 cannot survive the setdefault slate and silently leave the chrome/junk rollup screen
    # wired-but-dead (the exact false-done this issue exists to kill). FAITHFULNESS-NEUTRAL (an
    # extraction-integrity classifier + an input re-fetch; touch no faithfulness gate). PG_HTML_EXTRACTOR
    # is a STRING -> force-EXACT below, not here.
    "PG_SPAN_QUALITY_GATE",
    "PG_BLOCK_PAGE_DETECTOR",
    # I-beatboth-011 §3.1 ROUTE C (#1289): force-on the faithful abstractive writer (the per-basket prose
    # PRODUCER inside PG_VERIFIED_COMPOSE). OFF reverts the cert run to the verbatim short-writer render
    # probe. Fail-closed activation also needs PG_STRICT_VERIFY_ENTAILMENT=enforce (force-on above).
    "PG_ABSTRACTIVE_WRITER",
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
    # drb_72 / I-deepfix-001 (#1344): force-on the proceed-on-skew kill-switch so an explicit operator
    # PG_WEIGHTED_GATE_PROCEED_ON_SKEW=0 cannot survive the setdefault slate and silently restore the
    # benchmark strict-gate tier-COUNT corpus REFUSAL on the paid run (the drb_72 official-question
    # smoke abort). FAITHFULNESS-NEUTRAL (pre-generation CORPUS gate only; disclose-and-proceed via the
    # credibility-weighted path, NEVER a source drop). Allowlisted for SLATE-PURITY below.
    "PG_WEIGHTED_GATE_PROCEED_ON_SKEW",
    # I-beatboth-fix-000 (#1171): force-on the two breadth feature flags so an explicit operator =0
    # cannot survive the setdefault slate and silently restore the breadth-collapse behaviour.
    # BB-002: keep Serper offset-paging past short pages (else the de-facto 10/query ceiling returns).
    "PG_SERPER_STOP_ON_ZERO_NEW",
    # I-deepfix-001 (#1344) PURITY: BB-006 PG_STORM_INGEST_WEB_RESULTS removed (STORM seed-URL ingest
    # lane, a LOSER) — slate "0" above + REQUIRED_OFF below (fail closed if re-armed).
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
    # I-wire-001 (#1296): force-ON the BOOLEAN section winners so a stray operator =0 cannot survive the
    # setdefault slate and silently revert a winner to its legacy default. FAITHFULNESS-NEUTRAL (routing /
    # selection / consolidation winners; the FROZEN faithfulness engine is untouched). The 7 wired winners
    # are ALSO preflight-required (fail-closed before spend). PG_SCOPE_INTENT_FRAME (W1) is NOW wired — its
    # consumer run_intent_frame() is called on the run path (run_honest_sweep_r3.py:6426, fail-closed when
    # enabled), so it is force-ON here AND preflight-required (I-wire-001 P1-1), no longer build-deferred.
    "PG_QGEN_FS_RESEARCHER",
    "PG_SEARCH_FUSION_WRRF",
    "PG_CONTENT_RELEVANCE_JUDGE",
    "PG_CREDIBILITY_LLM_TIERING",
    "PG_CONSOLIDATION_NLI",
    "PG_ADEQUACY_CRAG",
    "PG_SCOPE_INTENT_FRAME",
    # I-deepfix-001 (#1344) COVERAGE LEVERS (DRB-II): force-ON the 8 weight-and-consolidate breadth levers
    # so a stray operator/.env =0 cannot survive the setdefault slate and silently leave a coverage lever
    # DARK on the paid run (the drb_72 dark-winner class). Each is DEFAULT-OFF in code (flag-OFF byte-
    # identical); force-ON here + preflight-required below + allowlisted (SLATE-PURITY). §-1.3 DNA-ALIGNED
    # (breadth EMERGES from honest weighted multi-attribution — NO forced cap/target/thinner/canary);
    # FAITHFULNESS-NEUTRAL (every surfaced/routed source re-passes the UNCHANGED strict_verify per claim).
    # D1/D4 are the two that were dark on the Gate-B path (armed only by run_honest_sweep_r3.main_async's
    # apply_winner_slate_on_paid_path, which the Gate-B launcher never calls) — slate-pinning arms them here.
    "PG_FACET_OUTLINE",              # O1 facet outline
    "PG_ROUTE_ALL_BASKETS",          # F1 route-every-verified-basket
    "PG_EV_BUDGET_TRACKS_PAYLOAD",   # F2 evidence budget tracks payload (ceiling removed)
    "PG_WORD_BUDGET_TRACKS_PAYLOAD", # F5 word budget tracks payload (clamp removed)
    "PG_EXPERT_FACET_PLANNER",       # R1 expert facet planner
    "PG_FACET_COMPLETENESS",         # R2 facet completeness
    "PG_QUALIFIER_ELABORATION",      # D1 within-basket qualifier elaboration (Gate-B-dark; now armed)
    "PG_ENRICHMENT_FACET_ROUTE",     # D4 facet-routed enrichment placement (Gate-B-dark; now armed)
    "PG_SUBTOPIC_DECOMPOSITION",     # L2 sub-topic decomposition (one verbatim-span sentence per distinct atomic fact)
    "PG_COVERAGE_L5_REQUIRED_ENTITY", # L5 question/facet-derived required-entity coverage lane (default-ON; belt force-ON)
    # I-deepfix-001 loss-risk FIX-1 (H1 scope gate DARK): force-ON the four scope+timeline ENFORCEMENT
    # flags so an explicit operator/.env =0 cannot survive the setdefault slate and silently leave the
    # scope gate producing ZERO effect on the paid run. Slate-dict members above; preflight-required below.
    "PG_SCOPE_CONSTRAINT_ENFORCE",
    "PG_EXTRACT_SCOPE_CONSTRAINTS",
    "PG_RELEVANCE_PRESERVE_ANCHORS",
    "PG_CORPUS_TIER_DISCLOSURE_MODE",
})

# Flags/modes that the benchmark slate force-sets to a specific value that is
# not "on". Kept separate from _BENCHMARK_FORCE_ON_FLAGS so tests and comments
# around capability-enabling flags keep their original meaning.
_BENCHMARK_FORCE_EXACT_FLAGS = frozenset({
    "PG_SWEEP_ANALYST_SYNTHESIS",
    # I-beatboth-011 KEYSTONE (#1289): force-EXACT the STRING-valued span-gate companions so a stray
    # operator/.env value cannot survive the slate. PG_HTML_EXTRACTOR=trafilatura_precision selects the
    # precision profile (the int-FLOOR path would crash on float('trafilatura_precision')) — also
    # value-equals-asserted in preflight_full_capability (the PG_RELEVANCE_SCORER precedent).
    # PG_SPAN_QUALITY_GATE_PRIMARY_MODEL pins the judge model to z-ai/glm-5.2 (drift-protection; the
    # module default already equals this).
    "PG_HTML_EXTRACTOR",
    "PG_SPAN_QUALITY_GATE_PRIMARY_MODEL",
    # I-beatboth-011 (a) (#1289): force-EXACT the writer tuning so a stray .env cannot restore the slow
    # 8192-reasoning / concurrency-8 / 120s defaults that timed out Route C on the resume run.
    "PG_ABSTRACTIVE_WRITER_REASONING_MAX_TOKENS",
    "PG_ABSTRACTIVE_WRITER_CONCURRENCY",
    "PG_ABSTRACTIVE_WRITER_CALL_DEADLINE_S",
    # I-wire-005 B-B (#1319): force-EXACT the Phase-7 quantified-spec Writer budgets so a stray
    # operator/.env value (or a partial deploy) can neither lower them (starving content ->
    # spec_produced=False) nor raise them off the chosen pair. Both are ALSO floor-guarded above
    # (defense in depth). Faithfulness-neutral (structured DATA, validated downstream).
    "PG_QUANTIFIED_SPEC_MAX_TOKENS",
    "PG_QUANTIFIED_SPEC_REASONING_MAX_TOKENS",
    # I-beatboth-011 #1290: force-EXACT the 4-role D8 seam bound so a stale operator .env (or unset, which
    # makes _resolve_four_role_seam_timeout return the max(7200,4*6500)=26000s ~7.2h default) cannot
    # restore the grind past the run-wall.
    "PG_FOUR_ROLE_SEAM_TIMEOUT_SECONDS",
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
    # I-beatboth-011 (#1289): the per-claim entailment total-deadline (idx53) is the THIRD sibling wall —
    # force-EXACT "300" for the same reason as the two above (transport-only, must not be raised/lowered
    # off the chosen value; the stale slate comments claimed 45 but it was set NOWHERE → ran the 150s code
    # default). And the D8 4-role reasoning effort (idx19) must be force-EXACT "medium" so it reaches the
    # live setter below (which otherwise defaults to xhigh) — the cause of the D8 grind. Both faithfulness-
    # neutral: deadline is transport-only (fail-closed sentinel = same verdict the caller handles); effort
    # governs latency, and the verdict ladder already falls back to "low".
    "PG_ENTAILMENT_TOTAL_S",
    "PG_FOUR_ROLE_REASONING_EFFORT",
    # I-arch-011 (verify-speed): the judge provider-rotation flag. Force-EXACT "1" so a stray operator =0
    # cannot silently restore the single-host z-ai blank-storm (which DROPS verified sentences in enforce
    # mode -> breadth collapse). Faithfulness-neutral-to-improving (same glm-5.1 model, next healthy host).
    "PG_JUDGE_PROVIDER_ROTATE",
    # I-arch-011 FIX-C (Codex P2): force the parallel-verify worker count EXACTLY to the slate value (16)
    # so a stray operator/.env PG_PARALLEL_VERIFY can neither exceed the intended 16-worker cap nor
    # silently revert to serial (=1, the bug that froze run #6). Concurrency knob only; verdicts unchanged.
    "PG_PARALLEL_VERIFY",
    # I-arch-007 #1264 DORMANT-CAP CLEANUP: pin the re-cap EXACTLY OFF ("0") so a stray operator/.env
    # value can never silently re-enable it (operator: ZERO cap; §-1.3 BANNED bolt-on).
    # PG_CAPPED_FINDING_DEDUP=0 removes the re-cap-to-max_ev (verified the ONLY consumer is the two
    # run_honest_sweep_r3 re-cap sites, both `and _capped_dedup`-gated). Faithfulness-neutral (a cap only
    # ever DROPPED). NOTE: the sibling PG_SPAN_PER_SOURCE_CITE_CAP pin was REMOVED here — I-deepfix-001
    # DELETED that bolt-on from fact_dedup.py entirely, so there is no env left to force-exact.
    "PG_CAPPED_FINDING_DEDUP",
    # I-wire-013 (#1327): the render chrome-as-claim CANARY mode is a STRING ("enforce") — force-EXACT
    # (the int FLOOR path would crash on float("enforce")) so a stray operator PG_RENDER_CHROME_CANARY=
    # warn|off cannot silently downgrade the cert-run tripwire to telemetry-only. Faithfulness-neutral
    # (the canary REFUSES an untrustworthy chrome-saturated report.md; it asserts no content).
    "PG_RENDER_CHROME_CANARY",
    # I-wire-001 (#1296): the 4 STRING (model-selector) section winners. Force-EXACT (the int-FLOOR path
    # would crash on float("qwen3")/float("mineru25")) so a stray operator/.env model selection cannot
    # silently revert a model winner to its default (MiniLM embed/rerank, docling clinical-PDF). Each is
    # ALSO value-equals-asserted in preflight_full_capability (the PG_RELEVANCE_SCORER precedent) so a
    # dropped force-exact pin FAILS the paid run CLOSED. FAITHFULNESS-NEUTRAL: a model choice in the
    # retrieval/extraction lane; the FROZEN faithfulness engine re-checks every claim regardless.
    "PG_CLINICAL_PDF_EXTRACTOR",
    "PG_EMBEDDER_MODEL",
    "PG_RERANKER_MODEL",
    "PG_CONTENT_RELEVANCE_RERANKER_MODEL",
    # I-deepfix-001 (#1344) WS-0: force-EXACT the W5 score-chunk to the slate "2" (numeric infra knob — NOT a
    # FLOOR: a stray HIGHER operator/.env value would re-open the one-pass co-resident OOM that leaves W5
    # dark). SLATE-PURITY skips it (float-parseable => infra, not a feature-enable). Faithfulness-neutral
    # (chunked reranker scores are byte-identical to one-pass).
    "PG_CONTENT_RELEVANCE_SCORE_CHUNK",
    # I-deepfix-001 U11 (Codex P1): the WRRF engine-weight map is a NON-NUMERIC STRING, so it MUST ride
    # force-EXACT — the numeric-FLOOR path in apply_full_capability_benchmark_slate would crash on
    # float("serper:1.0,..."). Force-EXACT pins the exact weight string so a stray operator/.env value
    # cannot silently drop the academic-engine lift. Allowlisted in _WINNER_FLAG_ALLOWLIST (W3 config).
    "PG_SEARCH_FUSION_WRRF_WEIGHTS",
    # I-deepfix-001 (#1344) PURITY — force-EXACT the LOSER kill-switches to "0" so a stray operator/.env
    # value can NEVER re-arm a killed loser past the slate. Each is also in _BENCHMARK_PREFLIGHT_REQUIRED_OFF_FLAGS
    # (the NO-LOSER gate fails CLOSED if any resolves truthy). STORM core + its ingest seed-lane are STORM's
    # twin live-discovery losers; agentic URL-discovery is STORM's code-confirmed analogue; legacy q1d
    # decompose / IterResearch / research-planner are superseded query-gen modules (FS-Researcher is the
    # sole adaptive qgen winner). Force-EXACT "0" is the de-arm; REQUIRED_OFF is the fail-closed assert.
    # R1_deepener_enable: PG_SWEEP_EVIDENCE_DEEPENER is REMOVED from this force-EXACT kill (it is the recall
    # lever, setdefault-ON in apply_full_capability_benchmark_slate — LAW VI operator-override-wins).
    "PG_STORM_ENABLED_IN_BENCHMARK",      # K1 STORM core (the loser the operator saw fire)
    "PG_STORM_ENABLED",                   # K1 storm_interviews module flag (dual-arm kill)
    "PG_STORM_INGEST_WEB_RESULTS",        # K3 STORM seed-URL ingest lane
    "PG_AGENTIC_SEARCH_IN_BENCHMARK",     # K7 agentic URL-discovery (STORM's twin)
    "PG_SWEEP_QUERY_DECOMPOSE",           # K9 legacy q1d query_decompose (default-ON; kill at source)
    "PG_QGEN_ITERRESEARCH",               # K10 IterResearch driver (superseded by FS-Researcher)
    "PG_USE_RESEARCH_PLANNER",            # K11 legacy facet query-gen (dark but unguarded)
    # I-deepfix-001 (#1344) PURITY (Codex P2-storm-query-cap): the STORM benchmark-query CAP is slate "0"
    # (STORM is dead — the cap dies with the engine) but was NOT force-EXACT, so its FLOOR-absence left it
    # vulnerable to a stale higher operator/.env PG_STORM_MAX_BENCHMARK_QUERIES surviving (it is correctly
    # NOT in _BENCHMARK_PREFLIGHT_FLOORS — NO-LOSER gate A.2 asserts that — and the slate dict only
    # setdefaults non-force-exact keys, so a stray .env value would WIN). Force-EXACT "0" pins it to the
    # killed value. SLATE-PURITY skips it (falsy value, not winner-checked); its purity is the "0" pin
    # here + the run path keying on the dead PG_STORM_ENABLED_IN_BENCHMARK. Faithfulness-neutral (a dead
    # STORM query knob; STORM never fires).
    "PG_STORM_MAX_BENCHMARK_QUERIES",     # K1-adjacent: STORM query cap (dead engine; pin the "0")
    # I-deepfix-001 (#1344) PURITY — force-EXACT the WINNER / mirror-model selectors that the live consumer
    # reads but the slate previously left unpinned. PG_EMBED_MODEL (NOT PG_EMBEDDER_MODEL) is the var the
    # live relevance/off-topic + selection embedder loader reads (prefetch_offtopic_filter._embed_model_name);
    # an operator .env PG_EMBED_MODEL=all-MiniLM-L6-v2 would silently route the live embedder to MiniLM while
    # the slate-pinned PG_EMBEDDER_MODEL preflight passes GREEN. PG_ENTAILMENT_MODEL / PG_EVALUATOR_MODEL pin
    # the live faithfulness judge + external evaluator to the §9.1.8 locked mirror (glm-5.2) so a stray gemma
    # slug can never drift in (the #1249/#1251/#1252 failure class). FAITHFULNESS-NEUTRAL: a model SELECTION
    # in the retrieval/extraction/judge lane; the FROZEN faithfulness engine re-checks every claim regardless.
    "PG_EMBED_MODEL",                     # K12 live relevance embedder id (= Qwen3-Embedding-8B)
    "PG_ENTAILMENT_MODEL",                # gemma-pin: live NLI / semantic-conflict judge (= glm-5.2)
    "PG_EVALUATOR_MODEL",                 # gemma-pin: external evaluator (= glm-5.2)
})

# I-ready-017 FX-03 (#1107) Codex iter-2 P1: hard CEILING on the cited-span window (defense-in-depth on
# top of the force-exact above). The preflight fails closed if the EFFECTIVE window exceeds this, so a
# whole-record-sized window can never reach a paid Gate-B run even if the slate value is ever changed.
_BENCHMARK_SPAN_WINDOW_MAX_BYTES = 2000

# I-deepfix-001 (#1344) PURITY — the WINNERS-ONLY NO-LOSER set: every boolean loser/legacy that the
# kill-list de-armed MUST resolve OFF before spend. The REQUIRED_OFF loop in preflight_full_capability
# fails CLOSED if ANY of these is truthy (a stray operator/.env value re-arming a killed loser). STORM
# core + ingest + agentic are the live-discovery losers; the three query-gen entries (legacy decompose /
# IterResearch / research-planner) are the superseded query-gen modules (FS-Researcher W2 is the sole
# adaptive qgen winner). PG_SWEEP_ANALYST_SYNTHESIS stays (the un-span-verified synthesis layer). Each is
# ALSO force-EXACT "0" (slate de-arm) — REQUIRED_OFF is the fail-closed assert.
# R1_deepener_enable: PG_SWEEP_EVIDENCE_DEEPENER is REMOVED from this REQUIRED_OFF set — the citation-
# snowball deepener is now the recall lever (setdefault-ON, widen-only), NOT a killed loser.
_BENCHMARK_PREFLIGHT_REQUIRED_OFF_FLAGS = (
    "PG_SWEEP_ANALYST_SYNTHESIS",
    "PG_STORM_ENABLED_IN_BENCHMARK",   # K1 STORM core (the loser the operator saw fire)
    "PG_STORM_ENABLED",                # K1 storm_interviews module flag (dual-arm kill)
    "PG_STORM_INGEST_WEB_RESULTS",     # K3 STORM seed-URL ingest lane
    "PG_AGENTIC_SEARCH_IN_BENCHMARK",  # K7 agentic URL-discovery (STORM's twin)
    "PG_SWEEP_QUERY_DECOMPOSE",        # K9 legacy q1d query_decompose (default-ON consumer)
    "PG_QGEN_ITERRESEARCH",            # K10 IterResearch driver (superseded by FS-Researcher)
    "PG_USE_RESEARCH_PLANNER",         # K11 legacy facet query-gen
)

# I-ready-002 (#1071) P0: env modes the preflight MUST see at "enforce" — the binding faithfulness gate
# is degraded (entailment not binding / judge_error fails open) at any other value. PG_VERIFICATION_MODE
# is NOT required here (rescue widening is out of scope; judge_error fail-closed keys on the entailment mode).
_BENCHMARK_PREFLIGHT_ENFORCE_MODES = ("PG_STRICT_VERIFY_ENTAILMENT",)

# I-wire-001 (#1296): the STRING (model-selector) section winners cannot ride the truthy
# _BENCHMARK_PREFLIGHT_REQUIRED_FLAGS loop (which only accepts "1"/"true"/"True"), so each is asserted
# value-equals in preflight_full_capability — the SAME precedent as PG_RELEVANCE_SCORER=='semantic_v2'.
# A paid run FAILS CLOSED if the slate force-exact pin was dropped and a stray/empty value left a model
# winner silently OFF (the default model would run). Values are the slate force-exact literals (the
# force-exact path sets os.environ to exactly these), so an exact compare is self-consistent.
_BENCHMARK_WINNER_EXACT_VALUE_ASSERTIONS: dict[str, str] = {
    "PG_CLINICAL_PDF_EXTRACTOR": "mineru25",                       # W4 clinical-PDF (else docling/PyMuPDF)
    "PG_EMBEDDER_MODEL": "qwen3",                                  # W6 embed=Qwen3-Embedding-8B (else MiniLM)
    "PG_RERANKER_MODEL": "qwen3",                                  # W7 rerank=Qwen3-Reranker-4B (else MiniLM/identity)
    "PG_CONTENT_RELEVANCE_RERANKER_MODEL": "Qwen/Qwen3-Reranker-0.6B",  # W5 relevance reranker (0.6B)
    # I-deepfix-001 (#1344) PURITY — the live-loader / mirror-model selectors the slate left unpinned. The
    # value-equals assertion (run after the slate) fails CLOSED if a dropped force-EXACT pin or a stray
    # .env left the live embedder on MiniLM (PG_EMBED_MODEL is the var the live loader actually reads — NOT
    # the slate-pinned PG_EMBEDDER_MODEL) or the judge/evaluator on a non-mirror (gemma) slug. The gemma
    # ABSENCE is additionally asserted via the live EntailmentJudge ._model in the NO-LOSER gate below.
    "PG_EMBED_MODEL": "Qwen/Qwen3-Embedding-8B",                   # K12 live relevance embedder id
    "PG_ENTAILMENT_MODEL": "z-ai/glm-5.2",                         # gemma-pin: live NLI / semantic-conflict judge
    "PG_EVALUATOR_MODEL": "z-ai/glm-5.2",                          # gemma-pin: external evaluator
}

# I-wire-001 (#1296): section winners whose MODULE is built + flag-aware but whose CONSUMER is NOT yet
# wired onto the run path (build-deferred). They are NOT in _BENCHMARK_PREFLIGHT_REQUIRED_FLAGS — a
# truthy-required flag with no run-path consumer would FALSE-PASS (env="1" while the feature never
# fires). preflight_full_capability emits a LOUD WARNING naming each (the operator reads by ear), so the
# gap is never silent. (name, reason) — surfaced verbatim in the warning.
# I-wire-001 P1-1: W1 intent_frame GRADUATED (run_intent_frame() called at run_honest_sweep_r3.py:6426).
# I-deepfix-001 #1344: W9 dedup GRADUATED too — its consolidate-keep-all body-syndication stage is now
# wired (content_dedup_consolidate.consolidate_body_syndication) + canary + manifest telemetry, so it is
# force-ON + preflight-required + allowlisted. The list is now EMPTY. (Historical note: the I-wire-001
# P1-2 dedup-agent reconcile correctly found the ContentDeduplicator DROP variant was neither a standalone
# wire nor CRAG-transitive — that DROP variant stays forbidden by the W9 GATE; what graduated is the new
# keep-all stage, not the DROP variant.) A FUTURE build-deferred winner (module built, consumer not yet
# wired) is re-added to the tuple below so preflight_full_capability emits its LOUD WARNING.
# I-deepfix-001 (#1344): EMPTY — W9 dedup=ContentDeduplicator was the last build-deferred winner and is
# now GRADUATED. The consolidate-keep-all body-syndication stage
# (src/polaris_graph/synthesis/content_dedup_consolidate.py, wired in
# multi_section_generator.consolidate_body_syndication) fires on the Gate-B run path with a canary +
# body_syndication manifest telemetry, so W9 is force-ON + preflight-required + allowlisted above, not
# warn-only. The §-1.3-violating ContentDeduplicator DROP variant (PG_W9_CONTENT_DEDUP) stays forbidden by
# the W9 GATE. A FUTURE build-deferred winner (module built, consumer not yet wired) is re-added here so
# preflight_full_capability emits its LOUD WARNING.
_BENCHMARK_BUILD_DEFERRED_WINNERS: tuple[tuple[str, str], ...] = ()

# ─────────────────────────────────────────────────────────────────────────────────────────────────────
# I-deepfix-001 (#1344) PURITY — the WINNER FIRE-CONTRACT + slate-purity data the 3 serious-preflight gates
# consume. Built from the purity-registry workflow (file:line-verified vs HEAD); see
# state/deepfix_purity_buildspec.md "SERIOUS PREFLIGHT — 3 gates".
# ─────────────────────────────────────────────────────────────────────────────────────────────────────

# WINNER-FIRES post-run firing-marker contract: {winner -> a SUCCESS-SPECIFIC predicate that MUST match the
# run-dir log when that winner GENUINELY fired}. The post-run §-1.1 audit applies each predicate against the
# run log via ``firing_marker_matched`` and FAILS the run if a WIRED non-conditional winner's GENUINE-fire
# predicate did not match (flag-on but dark).
#
# I-deepfix-001 (#1344) PURITY, Codex diff-gate iter-1 P1 (purity_6b_verdict.txt:P1-winner-firing-contract-
# false-positive): the prior contract values were BARE substrings that FALSE-PASSED on degraded/premature
# lines — W12 "[abstractive_writer] pre-pass complete" substring-matched the DEGRADED "pre-pass complete:
# 0/0 baskets drafted" (drafts=0 = winner did NOT fire); W13 "[multi_section]" matched ~8 unrelated lines
# (off-list-title-dropped / outline-JSON-decode-failed); W5 matched even when device=unavailable (silent
# full-weight fallback, no genuine reranker fire); W6/W7 matched a load-START line logged BEFORE the model
# load succeeded. A bare-substring contract is therefore NOT a reliable deferred WINNER-FIRES proof.
#
# FIX: each marker is now a ``_FiringMarker`` predicate — ``must_contain`` (the success-specific substring)
# PLUS ``forbid`` (degraded / failure / premature substrings that, if present in the SAME log line, prove the
# winner did NOT genuinely fire). A line counts as a GENUINE fire iff it contains ``must_contain`` AND NONE of
# ``forbid``. ``conditional=True`` marks data-dependent winners (W4 mineru25 fires only if a clinical PDF was
# fetched; W10 NLI merge only with >=2 cross-cluster keys) whose ABSENCE is allowed — the audit treats them as
# conditional-present, never a fail-on-absent. Each ``must_contain`` is file:line-verified against a REAL
# producer SUCCESS line (see the per-row producer ref) so the contract can never silently point at a phantom
# string. The matcher ``firing_marker_matched`` is the single source of truth the post-run audit AND the
# durable section-test both consume, so "tightened to success-specific" is enforced, not merely documented.
#
# W9 is DARK (no run-path consumer) and is intentionally ABSENT from this contract — it is handled by the
# LOUD W9 operator-ack gate, never grep-asserted on the run.
@dataclass(frozen=True)
class _FiringMarker:
    """A SUCCESS-SPECIFIC firing predicate for one winner. A run-log line is a GENUINE fire of the winner iff
    it contains ``must_contain`` AND contains NONE of ``forbid`` (the degraded / failure / premature twins).
    ``conditional`` winners fire only data-dependently — their ABSENCE from the log is allowed."""
    must_contain: str
    forbid: tuple[str, ...] = ()
    conditional: bool = False


_WINNER_FIRING_MARKER_CONTRACT: dict[str, _FiringMarker] = {
    # W1 — intent_frame.py:337 "[intent_frame] #scope IntentFrame fired: questions=%d ..." (questions>=1 fire)
    "W1_scope_intent_frame": _FiringMarker("[intent_frame] #scope IntentFrame fired"),
    # W2 — run_honest_sweep_r3.py:7989 "[fs_researcher] #1296 FS-Researcher ... issued N queries" (in the
    # _fs_researcher_enabled() branch; the loser "[iterresearch] #1292" is the else-branch and must be ABSENT).
    "W2_qgen_fs_researcher": _FiringMarker("[fs_researcher] #1296 FS-Researcher", forbid=("issued 0 queries",)),
    # W3 — live_retriever.py:4260 "[live_retriever] WRRF FUSED %d engines (...) -> %d unique candidates"
    "W3_fusion_wrrf": _FiringMarker("[live_retriever] WRRF FUSED"),
    # W4 — access_bypass.py:4611 "[ACCESS] W4: mineru25 (GPU VLM) extracted %d chars ..." (CONDITIONAL: only
    # when a clinical PDF was fetched; absence is allowed, never a fail-on-absent).
    "W4_clinical_pdf_mineru25": _FiringMarker("[ACCESS] W4: mineru25 (GPU VLM) extracted", conditional=True),
    # W5 — live_retriever.py:4699 "[live_retriever] W2 content-relevance: scored=%d ... device=%s". FORBID
    # device=unavailable: a load FAILURE stamps device='unavailable' = silent full-weight fallback (NO genuine
    # reranker fire), and that line still carries "scored=" — so the bare substring false-passed. (Codex P1)
    "W5_relevance_content_judge": _FiringMarker(
        "[live_retriever] W2 content-relevance: scored=", forbid=("device=unavailable",)
    ),
    # W6 — prefetch_offtopic_filter.py:114 "[prefetch_offtopic] loading relevance embedder model=Qwen/Qwen3-
    # Embedding-8B ...". The model id appears ONLY on this load line (the 8B-not-MiniLM proof). FORBID the
    # load-failure twin prefetch_offtopic_filter.py:121 "[prefetch_offtopic] Embedder not available" — if the
    # SentenceTransformer construct on the next line raised, that warning fires and the embedder is None
    # (silent lexical degrade). must_contain + absent-failure-twin = the success-specific 8B-loaded proof. (P1)
    "W6_embed_qwen3_8b": _FiringMarker(
        "[prefetch_offtopic] loading relevance embedder model=Qwen/Qwen3-Embedding-8B",
        forbid=("[prefetch_offtopic] Embedder not available",),
    ),
    # W7 — qwen_reranker_scorer.py:94 "[qwen-reranker] loading Qwen/Qwen3-Reranker-4B on %s (causal-LM ...)".
    # The 4B id appears only on this load line (the 4B-not-MiniLM proof); the load is wrapped so a raise
    # propagates (no silent-degrade twin on this tag). Gated by reranker-ON, so absence on a reranker-off
    # sub-path is benign; when the reranker IS invoked this is the genuine 4B-load fire. (Codex P1)
    "W7_rerank_qwen3_4b": _FiringMarker("[qwen-reranker] loading Qwen/Qwen3-Reranker-4B"),
    # W8 — credibility_llm_tiering.py:300 "[credibility_llm_tiering] tiered via GLM: ... llm_success=%d".
    # Already success-gated by the producer (llm_success>0); the DEGRADED twin logs "DEGRADED (rules-floor
    # only)" / "GLM tiering did NOT fire" under the SAME tag, so FORBID it belt-and-suspenders. (Codex did NOT
    # flag W8 — already correct; the forbid is defense-in-depth, never weakens it.)
    "W8_cred_llm_tiering": _FiringMarker(
        "[credibility_llm_tiering] tiered via GLM", forbid=("DEGRADED (rules-floor only)",)
    ),
    # W9 — content_dedup_consolidate.py "[content_dedup_consolidate] W9: ... basket(s) ... (KEEP-ALL ...)"
    # (I-deepfix-001 #1344 GRADUATED). The consolidate-keep-all body-syndication canary; fires on every
    # Gate-B run that reaches the generator's post-retraction pool (>=2 eligible rows) — even at 0 baskets
    # (a legitimate fire: it ran, found no near-identical-body syndication). KEEP-ALL is asserted in the
    # line; FORBID nothing (0 baskets is success). This is the behavioral proof W9 fired (was the DARK gap).
    "W9_dedup_content_consolidate": _FiringMarker("[content_dedup_consolidate] W9:"),
    # W10 — consolidation_nli.py:125 "[consolidation_nli] loading cross-encoder %s" (CONDITIONAL: only when
    # >=2 cross-cluster keys exist; absence is allowed).
    "W10_consolidate_nli": _FiringMarker("[consolidation_nli] loading cross-encoder", conditional=True),
    # W11 — run_honest_sweep_r3.py:8278 "[crag-adequacy] classifier verdict=%s sufficient=%s". FORBID
    # verdict=error (crag_adequacy_loop.py:360 returns verdict="error" on a raised classifier call — the
    # classifier did NOT genuinely grade) and verdict=unparseable (crag_adequacy_loop.py:310 conservative
    # not-sufficient on an unparseable grade). A genuine fire is verdict in {correct,ambiguous,incorrect}. (P1)
    "W11_adequacy_crag": _FiringMarker(
        "[crag-adequacy] classifier verdict=", forbid=("verdict=error", "verdict=unparseable")
    ),
    # W12 — abstractive_writer.py:642 "[abstractive_writer] pre-pass complete: %d/%d baskets drafted ...".
    # FORBID "pre-pass complete: 0/0" (abstractive_writer.py:603 — no baskets, the legacy degraded skip) AND
    # ": 0 baskets drafted" prefix-shapes: drafts=0 means the abstractive winner did NOT fire on any basket
    # and the legacy K-span fallback ran. (Codex P1: the bare substring matched the 0/0 degraded line.)
    "W12_compose_floor_abstractive": _FiringMarker(
        "[abstractive_writer] pre-pass complete:", forbid=("pre-pass complete: 0/",)
    ),
    # W13 — multi_section_generator.py:4029 "[multi_section] <section> verified-compose PRIMARY: %d baskets ->
    # draft_chars=%d" — the GENUINE per-section verified-compose keep-floor fire (the strict_verify-gated
    # compose path; faithfulness engine FROZEN). must_contain is the "verified-compose PRIMARY:" PHRASE (NOT
    # "[multi_section] verified-compose ..." — the producer interpolates the section TITLE between the tag and
    # the phrase, so the tag and phrase are NON-adjacent in the runtime line). The phrase is unique to line
    # 4029 (it appears in no drop/fail log), so it is the success-specific marker. Replaces the prior bare
    # "[multi_section]" which matched ~8 unrelated lines (off-list-title-dropped / outline-JSON-decode-failed
    # / advisory-prompt-load-failed). The sibling FIX-K verbatim-span render (multi_section_generator.py:3960)
    # is the K-span fallback, NOT the abstractive-compose keep-floor winner, so it is deliberately NOT
    # accepted here. (Codex P1)
    "W13_verify_keep_floor": _FiringMarker("verified-compose PRIMARY:"),
    # W14 — run_honest_sweep_r3.py:12753 "[citation-normalizer] key-findings: <canary>" — the deterministic
    # render-seam canary emitted at the assemble_report_md seam.
    "W14_render_det": _FiringMarker("[citation-normalizer] key-findings:"),
}


def firing_marker_matched(marker: _FiringMarker, log_text: str) -> bool:
    """True iff ``log_text`` contains at least one line that is a GENUINE fire of ``marker``: a line that
    contains ``marker.must_contain`` AND contains NONE of ``marker.forbid``. The per-line check (not a global
    ``and not any(forbid in log_text)``) is deliberate: a degraded line and a genuine line can BOTH appear in
    the same run (e.g. one section degrades, another genuinely composes) — the winner fired iff ANY line is a
    clean genuine fire. This is the single source of truth the post-run §-1.1 audit and the durable section-
    test both consume. Pure string logic — no spend, no network."""
    must = marker.must_contain
    forbid = marker.forbid
    for line in log_text.splitlines():
        if must in line and not any(bad in line for bad in forbid):
            return True
    return False


def firing_marker_contract_substrings() -> dict[str, str]:
    """The {winner -> must_contain} view of the contract — the success-specific substring the post-run audit
    greps for each winner. Back-compat surface for any consumer that only needs the positive substring; the
    forbid/conditional discrimination lives in ``firing_marker_matched``."""
    return {k: m.must_contain for k, m in _WINNER_FIRING_MARKER_CONTRACT.items()}


# I-deepfix-001 (#1344) WS-2 M6 — the cross-source analytical layer's POST-RUN fail-loud firing
# assertion. M6 is NOT one of the 14 section winners, so it is deliberately absent from
# _WINNER_FIRING_MARKER_CONTRACT (which the SLATE-PURITY test pins at exactly 14); it gets its own
# dedicated assertion here. The producer (cross_source_synthesis.compose_cross_source_analytical_units,
# :310-323) logs a GENUINE-fire line "[cross_source_synthesis] composed N cross-source analytical
# unit(s) ..." and a SILENT-NO-OP line "... anchored cross-source pair(s) but 0 analytical units
# survived ..." when eligible pairs existed but nothing survived per-clause re-verify. The stems below
# are the stable literals in those two producer lines.
_CROSS_SOURCE_FIRED_MARKER = "[cross_source_synthesis] composed"
_CROSS_SOURCE_SILENT_NOOP_MARKER = "anchored cross-source pair(s) but 0 analytical units survived"


def assert_cross_source_synthesis_fired(log_text: str) -> None:
    """WS-2 fail-loud M6 firing assertion (post-run, pure string logic — no spend, no network).

    When PG_CROSS_SOURCE_SYNTHESIS is ON (the slate force-pins it) AND the run's cross_source_synthesis
    producer reported that anchored cross-source pair(s) EXISTED (>=2 same-anchor, distinct-cluster
    baskets) yet 0 analytical units survived per-clause re-verify across the WHOLE run, the M6 analytical
    layer is a SILENT NO-OP (flag-on but dark) — raise RuntimeError. This is the exact firing failure the
    drb_72 re-smoke shipped: slate-on but ``cross_source_analytical_units == 0`` while eligible pairs
    existed.

    A run with NO anchored pairs (the conditional-absence case — no silent-no-op line was ever logged)
    NEVER raises: analytical yield EMERGES from real anchored pairs, it is never forced (§-1.3). A run
    that produced >=1 analytical unit anywhere (a "composed" line present) NEVER raises even if one
    section was individually barren — ``cross_source_analytical_units > 0`` at the run level. Slate-OFF is
    a no-op (the feature's own PG_CROSS_SOURCE_SYNTHESIS is the LAW-VI kill-switch that disarms BOTH the
    feature and this assertion). Consumed by the post-run §-1.1 audit alongside the winner firing-marker
    grep; the durable section-test exercises the same function."""
    if os.getenv("PG_CROSS_SOURCE_SYNTHESIS", "0").strip().lower() not in ("1", "true", "yes", "on"):
        return
    lines = log_text.splitlines()
    eligible_but_barren = any(_CROSS_SOURCE_SILENT_NOOP_MARKER in ln for ln in lines)
    genuinely_fired = any(_CROSS_SOURCE_FIRED_MARKER in ln for ln in lines)
    if eligible_but_barren and not genuinely_fired:
        raise RuntimeError(
            "benchmark post-run FAILED [WINNER-FIRES M6]: PG_CROSS_SOURCE_SYNTHESIS is ON and the run "
            "logged anchored cross-source pair(s) with 0 analytical units surviving per-clause re-verify "
            "for the WHOLE run — the M6 cross-source analytical layer is a SILENT NO-OP "
            "(cross_source_analytical_units == 0 while >=2 same-anchor baskets existed). Investigate "
            "cross_source_synthesis.license_relation / the per-clause re-verify; do NOT ship a run whose "
            "analytical layer produced nothing while eligible pairs existed."
        )


# ── FIX 1 (I-deepfix-001 Codex gate P0, WS-1 judge cache run-scope) ──────────────────────────────────
def _judge_verdict_idempotency_enabled() -> bool:
    """Mirror ``judge_adapter._verdict_idempotency_enabled`` — the PG_JUDGE_VERDICT_IDEMPOTENCY kill-switch
    (default ON). Read at CALL time (LAW VI) so a slate/operator override after import wins. When OFF the
    idempotency cache is never populated by ``run_judge``, so the per-document reset is skipped too (no
    behaviour change — byte-identical to pre-fix)."""
    return os.getenv("PG_JUDGE_VERDICT_IDEMPOTENCY", "1").strip().lower() not in (
        "0", "false", "no", "off",
    )


def _benchmark_official_question_enabled() -> bool:
    """PG_BENCHMARK_OFFICIAL_QUESTION kill-switch (default OFF, opt-in). Read at CALL time (LAW VI).

    The wrong-question fix for the benchmark path. ``run_gate_b`` calls ``run_one_query`` DIRECTLY,
    bypassing ``run_honest_sweep_r3.main_async`` — where the GATE0 canonical override
    (run_honest_sweep_r3.py:19099) rewrites each benchmark ``q["question"]`` to the CANONICAL gold-file
    question by idx. So a benchmark launched through ``run_gate_b`` runs on the ``SWEEP_QUERIES`` prompt
    verbatim, which for ``drb_72_ai_labor`` is the I-safety-002b program's FIR/safety prompt (a different
    program shares the slug) — NOT the official DRB-II idx-56 GenAI question. When this flag is truthy,
    ``run_gate_b_query`` replaces ``q["question"]`` with ``gate0_lineage.canonical_question_for_slug(slug)``
    BEFORE retrieval/generation, so protocol.json ``research_question``, retrieval, generation, and the
    report title all use the official idx question.

    Default OFF is byte-identical (the safety program keeps its locked FIR prompt; the locked file
    ``.codex/I-safety-002b/golden_questions_locked.md`` is never touched). FAITHFULNESS-NEUTRAL: this
    changes ONLY the input question text — no verify threshold, gate, span-grounding, or NLI rule."""
    return os.getenv("PG_BENCHMARK_OFFICIAL_QUESTION", "0").strip().lower() in (
        "1", "true", "yes", "on",
    )


# ── FIX 3 (I-deepfix-001 Codex gate P1, M6 firing-canary wiring) ─────────────────────────────────────
# The M6 producer (``cross_source_synthesis.compose_cross_source_analytical_units``) logs its fire /
# silent-no-op markers via its MODULE logger, which streams to STDOUT — NOT to ``run_dir/run_log.txt``
# (only the sweep's ``_log`` tee reaches that file; see run_honest_sweep_r3.py:7442-7444). So the post-run
# canary cannot read the markers from the run-dir log. We instead CAPTURE that one module logger's records
# in-process for the duration of the query, then feed the captured text to ``assert_cross_source_synthesis_
# fired`` in the post-run block. Observability-only; captures nothing but the M6 marker lines; never reads,
# alters, or decides a verdict (the frozen faithfulness engine is untouched).
_CROSS_SOURCE_SYNTHESIS_LOGGER = "src.polaris_graph.generator.cross_source_synthesis"


def _m6_firing_canary_enabled() -> bool:
    """PG_M6_FIRING_CANARY kill-switch (default ON). OFF => no capture handler is attached and the post-run
    M6 canary call is skipped entirely — byte-identical to pre-fix. Read at CALL time (LAW VI)."""
    return os.getenv("PG_M6_FIRING_CANARY", "1").strip().lower() not in (
        "0", "false", "no", "off",
    )


class _CrossSourceMarkerCaptureHandler(logging.Handler):
    """Append the ``cross_source_synthesis`` module logger's message lines into ``sink`` so the post-run M6
    canary can assert the analytical layer fired. A logging handler must NEVER raise into the caller, so
    ``emit`` swallows any formatting error. Sequential-sweep safe (§8.4 — one query at a time); attached +
    detached around a single ``asyncio.run(run_gate_b_query(...))`` so it never leaks across queries."""

    def __init__(self, sink: list[str]) -> None:
        super().__init__()
        self._sink = sink

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self._sink.append(record.getMessage())
        except Exception:  # noqa: BLE001 — a logging handler must never propagate an error to the caller
            pass


def _run_m6_firing_canary(
    log_lines: list[str],
    status: str,
    *,
    smoke_scale: bool,
    domain: str,
    slug: str,
) -> str:
    """POST-RUN M6 firing canary (FIX 3). Mirrors the breadth-canary pattern: on a RELEASED, non-smoke run,
    assert the M6 cross-source analytical layer fired (or was conditionally absent) from the captured
    ``cross_source_synthesis`` marker lines. A GENUINE silent-no-op (anchored cross-source pair(s) existed
    but 0 analytical units survived per-clause re-verify) raises RuntimeError -> "FAILED" (caller sets
    overall_rc=1). ``assert_cross_source_synthesis_fired`` ALSO self-skips on PG_CROSS_SOURCE_SYNTHESIS off
    (flag-off => early return, no raise). Reuses the breadth canary's released-status universe so the M6
    canary applies exactly where a full-contract report was rendered. Returns a one-line sweep-record status.
    Faithfulness-neutral: reads captured run telemetry, asserts nothing about any verdict."""
    if status not in _BREADTH_CANARY_RELEASED_STATUSES:
        return f"skip:status={status or '<none>'}"
    if smoke_scale:
        return "skip:smoke_scale"
    log_text = "\n".join(log_lines)
    try:
        assert_cross_source_synthesis_fired(log_text)
    except RuntimeError as _m6_exc:
        logging.getLogger("run_gate_b").error(
            "M6 cross-source firing canary FAILED for %s/%s: %s", domain, slug, _m6_exc,
        )
        print(f"<<< {domain} / {slug}: M6 cross-source firing canary FAILED: {_m6_exc}")
        return "FAILED"
    print(f"<<< {domain} / {slug}: M6 cross-source firing canary=ok")
    return "ok"


# W9 DARK-WINNER policy (spec OPERATOR DECISION #2). W9 (ContentDeduplicator) ships a DROP variant — wiring
# it as-is would shed corroborators and VIOLATE §-1.3 consolidate-keep-all + the FROZEN faithfulness
# contract. The FIRST-BUILD-STEP reconcile VERIFIED (not assumed) that the content near-dup function is
# SUBSUMED on Gate-B by the keep-all consolidation stack: finding_dedup #7 same-work consolidation
# (SameWorkGroup — keeps ALL member URLs as corroborating locators, never drops; finding_dedup.py:66-128)
# + consolidate=NLI W10 (literal-cluster union, corroboration_count UP, no row dropped). So W9's DARK state
# is CORRECT-BY-DESIGN, not a gap. The W9 gate therefore LOGS this loudly and PROCEEDS (SUBSUMED branch);
# it does NOT block runs. It does NOT silent-pass: if a future operator wires the DROP variant onto the run
# path (PG_W9_CONTENT_DEDUP truthy) it FAILS CLOSED (that would violate §-1.3) unless the operator signs the
# §-1.3 waiver PG_W9_DARK_ACK=1. The build-deferred WARNING is REPLACED by this gate.
_W9_SUBSUMED_BY = (
    "finding_dedup #7 same-work consolidation (SameWorkGroup keep-all, never drops a corroborator) + "
    "consolidate=NLI W10 (literal-cluster union, corroboration_count UP, no row dropped) — §-1.3 keep-all"
)

# SLATE-PURITY allowlist: every flag that is LEGITIMATELY force-on / force-EXACT-truthy maps to either one
# of the 14 winners OR the FROZEN faithfulness engine / transport / observability infra. The SLATE-PURITY
# gate asserts every force-on flag + every truthy force-EXACT key is in this set, and FAILS CLOSED on any
# unrecognized force-on ("slate impurity: <flag> maps to no winner") — the structural backstop that catches
# the NEXT STORM-like loser being force-on'd back into the slate. Enumerated from the SURVIVING force-on set
# (NOT losers): the killed losers (STORM/agentic/deepener/decompose/iterresearch/research-planner) are
# force-EXACT to "0" (FALSY) so they never enter the truthy-purity check. Reviewed/extended deliberately —
# a NEW force-on flag forces a conscious "winner or infra?" decision, which is exactly the gate the mandate
# wants. NOTE: force-EXACT flags pinned to a FALSY value ("0") or a non-on STRING are NOT purity-checked
# (only winner MODEL-selector strings + the on-valued ones are), so the killed-loser "0" pins do not need
# an allowlist entry; the model-selector winners (mineru25 / qwen3 / glm-5.2 / Qwen3-* ids) DO.
_WINNER_FLAG_ALLOWLIST: frozenset[str] = frozenset({
    # ── the 14 section winners (W1–W14) ──────────────────────────────────────────────────────────────
    "PG_SCOPE_INTENT_FRAME",                 # W1 scope=intent_frame
    "PG_QGEN_FS_RESEARCHER",                 # W2 qgen=FS-Researcher
    "PG_SEARCH_FUSION_WRRF",                 # W3 fusion=WRRF
    "PG_CLINICAL_PDF_EXTRACTOR",             # W4 clinical-PDF=mineru25 (string winner)
    "PG_CONTENT_RELEVANCE_JUDGE",            # W5 relevance judge (GLM leg)
    "PG_CONTENT_RELEVANCE_RERANKER_MODEL",   # W5 relevance reranker (0.6B string winner)
    "PG_EMBEDDER_MODEL",                     # W6 embed=Qwen3-Embedding-8B (string winner, selection path)
    "PG_EMBED_MODEL",                        # W6 embed (live-loader var, string winner)
    "PG_RELEVANCE_SCORER",                   # W6 main-path activation (semantic_v2 string)
    "PG_RERANKER_MODEL",                     # W7 rerank=Qwen3-Reranker-4B (string winner)
    "PG_CREDIBILITY_LLM_TIERING",            # W8 cred=llm_tiering
    "PG_CONTENT_DEDUP_CONSOLIDATE",          # W9 dedup=ContentDeduplicator (consolidate-keep-all body-syndication; I-deepfix-001 #1344 GRADUATED from build-deferred)
    "PG_CONSOLIDATION_NLI",                  # W10 consolidate=NLI
    "PG_ADEQUACY_CRAG",                      # W11 adequacy=CRAG
    "PG_VERIFIED_COMPOSE",                   # W12 compose=floor_abstractive
    "PG_ABSTRACTIVE_WRITER",                 # W12 abstractive writer (per-basket prose producer)
    "PG_BASKET_CORROBORATION_RENDER",        # W12/W14 keep-all basket render
    "PG_SYNTHESIS_ABSTRACT_CONCLUSION",      # W14 render=det (abstract/conclusion sandwich)
    # ── FROZEN faithfulness engine + the verified-compose / breadth surfaces (NOT losers) ───────────
    "PG_STRICT_VERIFY_ENTAILMENT",           # W13 binding entailment leg (frozen engine, enforce mode)
    "PG_MAX_JUDGE_ERROR_RATE",               # judge error-rate wall (faithfulness transport)
    "PG_NLI_IN_BENCHMARK",                   # additive NLI validator annotation
    "PG_SWEEP_NLI_CONFLICT",                 # NLI semantic-conflict detection layer
    "PG_SWEEP_TABLE_CELL_VERIFY",            # table-cell numeric verify layer
    "PG_USE_SAFETY_REFUSAL",                 # safety-refusal classifier layer
    "PG_SWEEP_SEMANTIC_CONTRAINDICATION",    # semantic contraindication credit + negation guard
    "PG_SWEEP_NUMERIC_SANITIZER",            # numeric-token sanitizer
    "PG_SPAN_RESOLVER",                      # span-grounding resolver
    "PG_SPAN_QUALITY_GATE",                  # chrome/junk span-quality gate
    "PG_BLOCK_PAGE_DETECTOR",                # block-page detector (re-fetch input)
    "PG_GATE_B_CITED_SPAN",                  # cited-span windowing on the 4-role seam
    "PG_GATE_B_SPAN_NORMALIZE",              # ligature-only cited-span normalization
    "PG_USE_FINDING_DEDUP",                  # #7 same-work consolidation (keep-all)
    "PG_RELEVANCE_FLOOR",                    # relevance floor (float in (0,1])
    "PG_RETRIEVAL_RELEVANCE_GATE",           # B4 relevance gate
    "PG_SWEEP_CREDIBILITY_REDESIGN",         # B6/B8/B12 credibility redesign (W8/W10 dependency)
    "PG_BREADTH_ENRICHMENT_ENABLED",         # I-arch-007 weighted unbound-SUPPORTS breadth surface
    "PG_REDACT_HELD_UNSUPPORTED",            # B16 redaction kill-switch
    "PG_ALWAYS_RELEASE",                     # always-release (labeler-not-blocker)
    "PG_SECTION_DISTILL",                    # map-reduce evidence distiller
    "PG_SWEEP_WEIGHTED_CORPUS_GATE",         # weighted-corpus gate (no tier-count refusal)
    "PG_WEIGHTED_GATE_PROCEED_ON_SKEW",      # drb_72 proceed-on-skew: relax strict tier-COUNT refusal -> disclose+proceed (gate-adjacent infra; weight-not-filter, faithfulness-neutral)
    "PG_VERIFIED_COMPOSE_MULTICITED",        # keystone multi-citation synthesis
    "PG_SWEEP_DEPTH_LAYER",                  # grounded DEPTH cross-source synthesis
    "PG_CROSS_SOURCE_SYNTHESIS",             # M6 cross-source analytical layer (I-deepfix-001 #1344 WS-2)
    "PG_RESUME_REFETCH_DEGRADED",            # A15 resume fetch-shell re-fetch
    # ── I-deepfix-001 loss-risk FIX-1: scope+timeline ENFORCEMENT infra (winner-or-infra DECISION: INFRA) ─
    # These are NOT losers. They ARM the scope gate (commit 64c10a49) whose enforcement half was dark on
    # Gate-B: out-of-scope DEMOTE (a §-1.3 WEIGHT, never a hard drop), marquee/user anchor PIN, and the
    # tier-deviation DISCLOSURE mode that REPLACES a §-1.3-banned corpus REFUSAL with a disclosed-weight
    # proceed. Weight-not-filter + faithfulness-neutral (every surfaced/demoted source re-passes the
    # UNCHANGED strict_verify per claim) -> allowlisted as selection/scope infra.
    "PG_SCOPE_CONSTRAINT_ENFORCE",           # out-of-scope demote / restrict-to mask / user-pin plan
    "PG_EXTRACT_SCOPE_CONSTRAINTS",          # intake scope+timeline intent extraction (feeds the enforcer)
    "PG_RELEVANCE_PRESERVE_ANCHORS",         # never cut a marquee / user-pinned anchor source
    "PG_CORPUS_TIER_DISCLOSURE_MODE",        # tier-deviation PROCEED-with-disclosed-profile (not a §-1.3 refusal)
    # ── transport / observability / honesty markers (NOT winners, NOT losers) ───────────────────────
    "PG_ENABLE_TOOL_TRACKER",                # tool-utilization tracker (firing observability)
    "PG_DEPTH_ANNOTATION_IN_BENCHMARK",      # depth annotation (non-gating)
    "PG_CUSTODY_LANE_MARKER",                # custody-lane honesty marker
    "PG_BEHAVIORAL_CANARY",                  # behavioral pre-spend canary
    "PG_SUPER_HEAVY_PREFLIGHT",              # super-heavy behavioral preflight
    "PG_RUN_HEALTH_GATE",                    # run-health backstop (still guards quantified)
    "PG_BENCH_EXTENDED_METRICS",             # extended beat-both scorer metrics (measurement-only)
    "PG_REQUIRED_ENTITY_LEDGER",             # RequiredEntityLedger coverage-gap disclosure
    "PG_SERPER_STOP_ON_ZERO_NEW",            # Serper offset-paging (fetch breadth, not a loser lane)
    "PG_JUDGE_PROVIDER_ROTATE",              # judge provider-rotation (faithfulness-neutral transport)
    "PG_PARALLEL_VERIFY",                    # parallel-verify worker count (concurrency knob)
    "PG_SELECT_SUBQUERY_FLOOR",              # selection sub-query coverage floor (selection infra)
    "PG_SELECT_CONSTRAINED_GREEDY",          # constrained-greedy selection (selection infra)
    "PG_SENTINEL_TRANSPORT_DEGRADE",         # sentinel transport degrade (faithfulness-neutral transport)
    "PG_TRAFILATURA_SUBPROCESS",             # trafilatura in-subprocess fetch (extraction transport)
    # ── string-valued mirror/judge pins (force-EXACT, truthy-but-not-"on" — allowlisted for purity) ──
    "PG_ENTAILMENT_MODEL",                   # gemma-pin: live judge mirror (glm-5.2)
    "PG_EVALUATOR_MODEL",                    # gemma-pin: external evaluator mirror (glm-5.2)
    "PG_HTML_EXTRACTOR",                     # trafilatura precision profile (fetch extraction winner-adjacent)
    "PG_SPAN_QUALITY_GATE_PRIMARY_MODEL",    # span-quality judge model pin (glm-5.2)
    "PG_RENDER_CHROME_CANARY",               # render chrome-as-claim canary (enforce)
    "PG_ENTAILMENT_PROMPT_VARIANT",          # widening-aware entailment prompt (widen_c)
    "PG_SCOPE_SIM_MEASURE",                  # scope similarity measure (containment)
    "PG_UNPAYWALL_EMAIL",                    # real OA resolver contact email
    # I-deepfix-001 U11 (Codex P1): the WRRF engine-weight map is a non-numeric string force-EXACT pin
    # (so SLATE-PURITY demands it be allowlisted). It is the CONFIG for the W3 WRRF fusion winner —
    # weighting academic/clinical registries above generic web — NOT a new feature-enable. Allowlisted
    # deliberately (the conscious 'winner or infra?' decision the gate exists to force): it is W3 config.
    "PG_SEARCH_FUSION_WRRF_WEIGHTS",         # W3 WRRF engine-weight map (academic-lift config)
    # I-deepfix-001 (#1344) PURITY (Codex P2-slate-purity-skips-string-force-exact): the ONE non-model
    # STRING force-exact infra pin. PG_FOUR_ROLE_REASONING_EFFORT='medium' (the D8 GLM-5.2 xhigh-blanks
    # fix) is non-falsy, non-numeric, and not an ON-token, so the SLATE-PURITY string-pin check below
    # demands it be a RECOGNIZED force-exact value. It is transport/latency config (the reasoning-effort
    # pin reaching set_four_role_reasoning_effort), NOT a winner-value selection — allowlisted explicitly
    # so the clean slate PASSES while a future BOGUS string force-exact (not here) still fails CLOSED.
    "PG_FOUR_ROLE_REASONING_EFFORT",         # D8 4-role reasoning-effort pin (medium; latency config)
    # ── I-deepfix-001 (#1344) DRB-II COVERAGE LEVERS — weight-and-consolidate breadth surfaces (NOT losers) ──
    # The 8 built-and-gated breadth levers armed on the paid slate. §-1.3 DNA-ALIGNED: breadth EMERGES from
    # honest weighted multi-attribution (facet outline = section count from clusters; route-all = consolidate-
    # don't-drop stranded baskets; budgets track payload = ceiling removed; facet planner/completeness = wider
    # retrieval; D1/D4 = additive keep-all placement) — NONE is a forced cap/target/thinner/canary. Each is a
    # conscious 'winner or infra?' decision: they are the DRB-II COVERAGE machinery, allowlisted deliberately.
    "PG_FACET_OUTLINE",                      # O1 facet outline (section count emerges from clusters)
    "PG_ROUTE_ALL_BASKETS",                  # F1 route-every-verified-basket (consolidate-don't-drop)
    "PG_EV_BUDGET_TRACKS_PAYLOAD",           # F2 evidence budget tracks payload (ceiling removed)
    "PG_WORD_BUDGET_TRACKS_PAYLOAD",         # F5 word budget tracks payload (clamp removed)
    "PG_EXPERT_FACET_PLANNER",               # R1 expert facet planner (retrieval breadth)
    "PG_FACET_COMPLETENESS",                 # R2 facet completeness (retrieval-breadth completeness)
    "PG_QUALIFIER_ELABORATION",              # D1 within-basket verbatim qualifier elaboration (keep-all)
    "PG_ENRICHMENT_FACET_ROUTE",             # D4 facet-routed enrichment placement (keep-all)
    "PG_SUBTOPIC_DECOMPOSITION",             # L2 sub-topic decomposition (verbatim-span sentence per distinct atomic fact; keep-all)
    "PG_COVERAGE_L5_REQUIRED_ENTITY",        # L5 question/facet-derived required-entity coverage lane (winners-only purity)
})

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
    # I-deepfix-001 U31 (Codex P1): raise the fail-closed floor from 50000 to 300000 so the
    # preflight actually ENFORCES the U31 cap on the paid run (a too-late slate that left the
    # live constant below 300000 is now caught pre-spend, not false-passed). The slate FLOOR
    # already forces PG_LIVE_CONTENT_MAX >= 300000, so a correctly-applied run always clears.
    ("src.polaris_graph.retrieval.live_retriever", "DEFAULT_CONTENT_MAX_CHARS", 300000),
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
    # per-call 6500 < section 9000 < run-wall 14400; the explicit ordering assertion in
    # preflight_full_capability fails closed if a future value inverts the hierarchy.
    # I-deepfix-001 (wallclock_guard): raised 10800 -> 14400 to match the slate (a real clinical
    # back-half measured 10992s > 10800). Floor stays strictly above section 9000.
    "PG_RUN_WALL_CLOCK_SEC": 14400,
}


# I-arch-007 SMOKE scale-down. Applied (FORCE-SET, bypassing the ~1000-URL FLOOR) AFTER the
# full-capability slate ONLY when --smoke-scale is passed, so a PLUMBING smoke runs ~25-35 min and a
# HANG self-kills in ~60 min instead of 6h (I-deepfix-001: retrieval wall 1200 + run-wall 3600). INPUT
# BREADTH (the 5 fetch lanes + query-breadth counts)
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
    # I-deepfix-001 (#1344) PURITY: STORM is a dead loser — neutralize its two smoke knobs to "0" so a
    # --smoke-scale run cannot re-introduce a non-zero STORM query cap / under-fire floor (the SLATE-PURITY
    # gate would otherwise see a truthy STORM knob). The full-slate values are also "0".
    "PG_STORM_MAX_BENCHMARK_QUERIES": "0",   # was 4 (STORM dead — query cap 0)
    "PG_STORM_MIN_EFFECTIVE_QUERIES": "0",   # was 2 (STORM dead — under-fire floor 0; never trips)
    "PG_MAX_SUBQUERIES": "4",                # was 15
    "PG_STORM_PERSPECTIVES_COUNT": "3",      # was 8
    "PG_STORM_ROUNDS_PER_PERSPECTIVE": "2",  # was 4
    # the SUPER-HEAVY pre-spend preflight requires discovery to return >= this many candidate URLs
    # (default 100); the smoke discovers ~20-40, so lower the floor or it aborts before the sweep.
    "PG_PREFLIGHT_MIN_BREADTH": "10",        # was 100
    # I-deepfix-001 (#1344) SMOKE-CRASH FIX: the W4 mineru25 GPU-VLM PDF parser (the full slate forces
    # PG_CLINICAL_PDF_EXTRACTOR=mineru25) crashed the WHOLE run with a native `Fatal Python error:
    # Aborted` (SIGABRT, rc=134) inside transformers `.generate()` during VLM layout-detect on a PDF —
    # a native abort() is uncatchable by the mineru circuit-breaker / per-call timeout / try-except, so
    # it killed the process mid-retrieval before the back half ever ran. The PLUMBING smoke only needs
    # PDF BODIES (which docling->PyMuPDF extracts faithfully — §-1.3: every source kept, faithfulness
    # untouched), NOT the VLM layout fidelity. Pin the smoke to the safe default extractor so the smoke
    # can validate the back half (generation->4role->strict_verify->render). PAID slate keeps mineru25
    # (W4 winner); its crash-isolation (subprocess/hard-kill) is the queued fix before the paid run.
    "PG_CLINICAL_PDF_EXTRACTOR": "docling",  # smoke: no GPU-VLM (avoids the mineru25 SIGABRT); paid keeps mineru25
    # I-cred-008b basket-coverage gate scales with breadth; keep the super-heavy preflight's own
    # gates ON (faithfulness/behavioral) — only the BREADTH-count floor is lowered for the smoke.
    # timeout hierarchy — coherent retrieval-wall < run-wall (with back-half headroom) AND
    # per-call < generator < section < seam < run-wall, scaled so a HANG is caught in ~60 min.
    # A tiny smoke section finishes in minutes, well under these, so none truncates a HEALTHY
    # section (the arch-005 trap).
    # I-deepfix-001 (#1344) SMOKE-HANDOFF FIX: the full slate pins PG_RETRIEVAL_QUESTION_WALL_SECONDS
    # =5400 via FLOOR semantics; on the smoke that EXCEEDS the smoke run-wall (was 2400), so the
    # per-question retrieval deadline could NEVER hand off the partial corpus -> retrieval ran
    # UNBOUNDED and the smoke never reached generation/render (the back-half plumbing stayed
    # unexercised). The benchmark preflight SKIPS the retrieval<run coherence check on smoke_scale
    # (run_gate_b.py:2616 `and not smoke_scale`), so nothing caught the incoherent hierarchy. Pin a
    # smoke retrieval wall STRICTLY BELOW the smoke run-wall with ample back-half room: 1200 retrieval
    # + up to 2400 back-half <= 3600 run-wall (seam backstop 1800 < 2400 -> a healthy back half is
    # never guillotined). Smoke-only; the PAID slate (5400 < 10800) is UNTOUCHED. Faithfulness-neutral:
    # a disclosed retrieval_wall_hit hands off the partial corpus and drops no source (§-1.3).
    "PG_RETRIEVAL_QUESTION_WALL_SECONDS": "1200", # per-question retrieval handoff (20 min) — < run-wall
    "PG_VERIFIER_LLM_TIMEOUT_SECONDS": "300",    # per verifier LLM call (5 min)
    "PG_GENERATOR_LLM_TIMEOUT_SECONDS": "600",   # per generator call (10 min) — synced to live module below
    "PG_SECTION_WALLCLOCK_SECONDS": "900",       # per section (15 min)
    "PG_FOUR_ROLE_SEAM_TIMEOUT_SECONDS": "1800", # 4-role D8 seam (30 min)
    # I-deepfix-001 (#1344) back-half headroom: the first authorized smoke must fit retrieval (1200) +
    # tiering + adequacy/CRAG + generation + strict_verify + the 4-role seam (1800) inside the run-wall.
    # 3600 risked guillotining mid-back-half (error_unexpected, no report); 5400 keeps seam 1800 <
    # run-wall and retrieval 1200 < run-wall (passes the coherence preflight). Also pin the credibility
    # pass wall coherent with the smoke (the full slate force-exacts 3000, incoherent vs a 5400 run-wall).
    "PG_RUN_WALL_CLOCK_SEC": "5400",             # OUTER backstop (90 min) — retrieval 1200 + back-half ~4200
    "PG_CREDIBILITY_PASS_WALL_S": "600",         # smoke credibility-pass wall (10 min) — < run-wall, coherent
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
    floor loop (bypassing max()), shrinking INPUT breadth + timeout backstops for a ~25-35 min plumbing
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
    # ─────────────────────────────────────────────────────────────────────────────────────────────
    # I-deepfix-001 Item-10 (#1344): WIRE the W4 mineru25 clinical-PDF winner to its vlm-http-client
    # backend as the DEFAULT for clinical Gate-B runs. The slate force-EXACTs PG_CLINICAL_PDF_EXTRACTOR=
    # mineru25 (above), but historically left the mineru BACKEND unset — so resolve_mineru_backend fell to
    # the YAML default `in-process`, _mineru25_extract raised "no server URL configured", every clinical
    # PDF degraded to the Docling/PyMuPDF LOSER, and the circuit breaker OPENED after 3 — mineru NEVER
    # genuinely ran (proven in the drb live log: repeated "mineru25 vlm-http-client: no server URL
    # configured" -> DISCLOSED fallback, "circuit breaker OPEN ... after N consecutive failures"). Point
    # the pipeline at the supervised dedicated-GPU mineru-vllm-server (127.0.0.1:30024, the host/port in
    # config/serving/mineru_vllm_server.yaml, /health 200 on the box). `setdefault` (NOT force): a box that
    # exports a different PG_MINERU25_BACKEND / PG_MINERU25_SERVER_URL WINS (LAW VI) — this is the
    # standard-local default, not a hard pin. The isolated-venv CLI path is genuinely box-specific
    # (/root/mineru_svc/bin/mineru), so it stays an operator env (PG_MINERU25_CLI_PATH) — the WINNER-FIRES
    # W4 preflight below FAILS LOUD before spend if the CLI can't be resolved or the server is unreachable,
    # so a mis-provisioned box can never silently ship the Docling loser. FAITHFULNESS-NEUTRAL: this only
    # chooses HOW the clinical-PDF text is extracted; the FROZEN faithfulness engine (strict_verify / NLI /
    # 4-role D8 / provenance / span-grounding) re-grounds every claim from the extracted text regardless.
    os.environ.setdefault("PG_MINERU25_BACKEND", "vlm-http-client")
    os.environ.setdefault("PG_MINERU25_SERVER_URL", "http://127.0.0.1:30024")
    # ─────────────────────────────────────────────────────────────────────────────────────────────
    # R1_deepener_enable: ENABLE the citation-snowball evidence deepener — the recall lever for the
    # blocked-reference / primary-starved corpus (task72: adequacy='proceed' + fully covered, but
    # T1+T2=14/182 — the 14 primary studies behind a BLOCKED systematic review were never fetched; the
    # deepener does backward+forward Semantic Scholar citation chase, the exact tool to pull a review's
    # primaries). `setdefault` (NOT force / NOT a slate-dict FLOOR): LAW VI — an operator/.env
    # PG_SWEEP_EVIDENCE_DEEPENER=0 still WINS (a slate-dict boolean is max()-floored, which would force a
    # "0" up to "1"; the explicit setdefault here is true operator-override-wins). WIDEN-ONLY (§-1.3):
    # every URL the deepener discovers is fed back through the UNCHANGED run_live_retrieval(seed_urls=…)
    # -> fetch -> classify_source_tier -> is_content_starved -> strict_verify chokepoint
    # (run_honest_sweep_r3.py), so a thin/abstract-only paper is DROPPED fail-closed and the FROZEN
    # faithfulness engine (strict_verify / NLI / 4-role D8 / provenance / span-grounding) re-grounds every
    # claim — no tier laundering, no auto-trust, faithfulness NEVER relaxed.
    os.environ.setdefault("PG_SWEEP_EVIDENCE_DEEPENER", "1")
    # SEMANTIC_SCHOLAR_API_KEY passthrough: the deepener reads the key via os.getenv and no-ops without it
    # (evidence_deepener.py:132-134). The key is a SECRET, so it is NEVER setdefaulted to a literal (LAW VI);
    # it passes through from the process env / .env (load_dotenv) automatically on the in-process
    # run_one_query path. The deepener-on + key-absent FAIL-LOUD (LAW II) is NOT asserted here: this slate is
    # invoked by many hermetic slate-config tests that do not stub SEMANTIC_SCHOLAR_API_KEY, and asserting
    # during mere configuration would RuntimeError them in clean CI. Instead the fail-loud lives at the ONE
    # chokepoint EVERY real paid entry flows through — should_trigger_deepener() in
    # src/polaris_graph/retrieval/deepener_sweep_adapter.py (wiring-gap iter-4, Codex REVISE): run_gate_b
    # main(), run_gate_b_query(), AND scripts/run_honest_sweep_r3.run_one_query() (the main_async/main path
    # that bypasses run_gate_b) all gate the deepener on that predicate, so it raises a RuntimeError naming
    # SEMANTIC_SCHOLAR_API_KEY when the deepener is enabled + the key is absent, and returns False (no raise)
    # for every other non-trigger reason. Config-only slate tests never call it, so they stay clean.
    # FAITHFULNESS-NEUTRAL: no faithfulness logic.
    # ─────────────────────────────────────────────────────────────────────────────────────────────
    # ARM R2 (wiring audit — Codex+Fable, 2026-07-04): PG_SUBENTITY_QUERY_EXPANSION defaults "0"
    # (sub_entity_query_expander.py:62) and was set NOWHERE in the effective run env, so the sub-entity +
    # STORM-perspective query expansion was DEAD on the drb_72 run. Arm it here so
    # sub_entity_expansion_enabled() -> True and widen_with_sub_entities fires
    # (fs_researcher_query_gen.py:398-405). `setdefault` (NOT force) so an explicit operator/.env override
    # still WINS (LAW VI). WIDEN-ONLY SUPERSET, FAITHFULNESS-NEUTRAL (§-1.3): it only ADDS scope-anchored
    # queries to the frontier (a strict superset of the flag-OFF issued set) — no cap / target / thinner /
    # drop; every added query routes through the UNCHANGED per_query_retrieve -> fetch ->
    # classify_source_tier -> strict_verify chokepoint, and the FROZEN faithfulness engine is untouched.
    os.environ.setdefault("PG_SUBENTITY_QUERY_EXPANSION", "1")
    # ─────────────────────────────────────────────────────────────────────────────────────────────
    # ARM L2 (wiring audit — Codex+Fable, 2026-07-04): PG_SUBTOPIC_ADDITIVE_FACTS defaults "0"
    # (verified_compose.py:560-567) and was set NOWHERE, so the additive distinct-fact pass (commit
    # 42692185 deferred-B) was DEAD. Arm it here so _subtopic_additive_facts_enabled() -> True and
    # compose_distinct_fact_units fires (verified_compose.py:2126). `setdefault` (NOT force) so an explicit
    # operator/.env override still WINS (LAW VI). ADDITIVE DISTINCT-FACT PASS, FAITHFULNESS-NEUTRAL (§-1.3):
    # each surfaced unit is a VERBATIM span slice that RE-PASSES the UNCHANGED strict_verify (verify_fn) and
    # is ADDITIVE to (never replaces) the headline — CONSOLIDATE-keep-all, drops nothing. No cap / target /
    # thinner; the FROZEN faithfulness engine is untouched.
    os.environ.setdefault("PG_SUBTOPIC_ADDITIVE_FACTS", "1")
    # ─────────────────────────────────────────────────────────────────────────────────────────────
    # Correction 7 (Codex+Fable gate) — SPEED LEVER L1 429/BREADTH STEP-DOWN, made REAL (was a comment).
    # PG_LIVE_RETRIEVER_MAX_WORKERS is a FLOOR entry (max(existing, 48)), so the forensic monitor CANNOT
    # lower it via the plain env — the floor raises it right back to 48. Honor a DEDICATED step-down
    # override HERE, AFTER the floor loop: the monitor sets PG_LIVE_RETRIEVER_MAX_WORKERS_STEPDOWN=36 (or
    # 24) WITHOUT a code edit when telemetry shows a 429-rate rise or a cited-source breadth regression vs
    # the 24-worker baseline. The effective value is min(<slate ceiling 48>, override) so the monitor can
    # only step DOWN from the ceiling (never silently RAISE fetch concurrency; the per-host politeness cap
    # PG_LIVE_RETRIEVER_PER_HOST_CONCURRENT stays the invariant). An absent/invalid/<=0 override leaves the
    # floored ceiling unchanged. Placed BEFORE the smoke-scale block so a --smoke-scale run's own override
    # still wins for smoke. FAITHFULNESS-NEUTRAL: fetch concurrency only; strict_verify / NLI / 4-role D8 /
    # provenance re-check every claim regardless of worker count. This is a monitor-set input, NOT a runtime
    # auto-step-down (the loop reads the override each run; a live auto-decrementer is out of scope).
    _workers_ceiling = int(_FULL_CAPABILITY_BENCHMARK_SLATE["PG_LIVE_RETRIEVER_MAX_WORKERS"])
    _stepdown_raw = os.environ.get("PG_LIVE_RETRIEVER_MAX_WORKERS_STEPDOWN", "").strip()
    if _stepdown_raw:
        try:
            _stepdown = int(float(_stepdown_raw))
        except (TypeError, ValueError):
            _stepdown = 0
        if _stepdown > 0:
            os.environ["PG_LIVE_RETRIEVER_MAX_WORKERS"] = str(min(_workers_ceiling, _stepdown))
    # I-arch-007 SMOKE: AFTER the full-capability floor, FORCE-SET the small-scale overrides (bypassing
    # the FLOOR's max()) so a --smoke-scale plumbing run is ~25-35 min. INPUT BREADTH + timeout BACKSTOPS
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
    # I-beatboth-008 (#1285) commit-2 build A — IMPORT-TIMING REBIND for PG_FOUR_ROLE_CLAIM_WORKERS.
    # sweep_integration.py:155 reads this env AT IMPORT into the module global
    # `_CLAIM_WORKERS = max(1, int(os.getenv("PG_FOUR_ROLE_CLAIM_WORKERS","6")))`, and run_gate_b.py:61
    # imports sweep_integration at THIS module's OWN top level — which runs BEFORE this slate ever does.
    # So the slate's os.environ set above is a SILENT NO-OP on `_CLAIM_WORKERS` (already frozen at the
    # default). REBIND the live module attribute here (same fix class as the four setters above) so the
    # slate value ACTUALLY takes effect. The D8 seam reads `_CLAIM_WORKERS` as a module global at CALL
    # time (sweep_integration.py:493/600/625), so this post-import reassignment is honored on the run.
    # FAITHFULNESS-NEUTRAL: worker count only — the per-claim verdicts + D8 reduction are unchanged.
    # The module is already in sys.modules (imported at run_gate_b:61), so this import is free.
    import src.polaris_graph.roles.sweep_integration as _sweep_integration
    _sweep_integration._CLAIM_WORKERS = max(
        1, int(os.environ.get("PG_FOUR_ROLE_CLAIM_WORKERS", "6"))
    )


def _winner_slate_prespend_assert_enabled() -> bool:
    """Default-ON kill-switch for the pre-spend winner-slate assertion (LAW VI — env-driven, no hardcode).
    Set ``PG_WINNER_SLATE_PRESPEND_ASSERT=0`` to disable (only for a deliberate operator experiment)."""
    return os.getenv("PG_WINNER_SLATE_PRESPEND_ASSERT", "1").strip().lower() in ("1", "true", "yes", "on")


def assert_full_capability_slate_applied(smoke_scale: bool = False) -> None:
    """FAIL CLOSED (pre-spend, BEFORE the sweep import) if the full-capability slate did NOT actually land
    for a force-on / force-exact flag — i.e. a WINNER (esp. W2 ``PG_QGEN_FS_RESEARCHER``) would run silently
    DARK because a stray operator/.env value survived, or ``apply_full_capability_benchmark_slate``'s force
    semantics regressed to ``setdefault``.

    This is the drb_72 dark-winner class: the paid run silently ran a NON-WINNER config because the running
    process did not carry the winner flag truthy, and the only marker check was POST-run (after full spend).
    This turns that into a pre-spend HARD STOP, naming the offending flag, BEFORE the heavy sweep import and
    long before ``preflight_full_capability`` at the token boundary — the earliest, cheapest tripwire.

    Called IMMEDIATELY after ``apply_full_capability_benchmark_slate`` in ``run_gate_b_query`` (so the env
    reflects exactly the slate's force values, before any downstream ``os.environ`` set). ``smoke_scale``
    honors ``_SMOKE_SCALE_OVERRIDES`` (a smoke deliberately deviates from the slate, e.g. docling clinical
    PDF) so the assertion is correct on both the paid and smoke benchmark paths.

    FAITHFULNESS-NEUTRAL: reads ``os.environ`` + the slate constants only; touches no gate, no evidence, no
    verdict. Env-driven kill-switch ``PG_WINNER_SLATE_PRESPEND_ASSERT`` (default ON; LAW VI).
    """
    if not _winner_slate_prespend_assert_enabled():
        return
    mismatches = []
    for _flag in sorted(_BENCHMARK_FORCE_ON_FLAGS | _BENCHMARK_FORCE_EXACT_FLAGS):
        # The EFFECTIVELY-applied expected value: a --smoke-scale run deliberately overrides some slate
        # values (e.g. PG_CLINICAL_PDF_EXTRACTOR=docling), so honor _SMOKE_SCALE_OVERRIDES first, then the
        # slate. A force flag that is NOT a slate/smoke key is not governed by apply_slate — skip it (its own
        # default/preflight governs it); never assert a value apply_slate never set.
        if smoke_scale and _flag in _SMOKE_SCALE_OVERRIDES:
            _expected = _SMOKE_SCALE_OVERRIDES[_flag]
        elif _flag in _FULL_CAPABILITY_BENCHMARK_SLATE:
            _expected = _FULL_CAPABILITY_BENCHMARK_SLATE[_flag]
        else:
            continue
        if os.environ.get(_flag) != _expected:
            mismatches.append((_flag, _expected, os.environ.get(_flag)))
    if mismatches:
        _detail = "; ".join(f"{_f} expected {_e!r} got {_a!r}" for _f, _e, _a in mismatches)
        raise RuntimeError(
            "benchmark preflight FAILED [WINNER-SLATE-DARK] (pre-spend, pre-import): the full-capability "
            f"slate did not take effect for {len(mismatches)} force-on/force-exact flag(s) — a WINNER would "
            "run silently DARK (the drb_72 FS-Researcher dark-winner class this gate exists to kill). "
            f"Offending: {_detail}. Esp. PG_QGEN_FS_RESEARCHER MUST be '1'. "
            "apply_full_capability_benchmark_slate() must run immediately before this assertion (its "
            "force-set semantics are the fix); set PG_WINNER_SLATE_PRESPEND_ASSERT=0 ONLY for a deliberate "
            "operator experiment."
        )


# I-deepfix-001 (#1344) DRB-II COVERAGE LEVERS — the 8 weight-and-consolidate breadth levers that the paid
# slate now ARMS (built + triple-gated, previously DARK). This is the single source of truth the pre-spend
# assert + the coverage-wiring test both read. Each is DEFAULT-OFF in code; the slate force-ON-pins + preflight-
# requires + allowlists each. §-1.3 DNA-ALIGNED (breadth EMERGES; NO forced cap/target/thinner/canary).
_COVERAGE_LEVER_FLAGS: tuple[tuple[str, str], ...] = (
    ("PG_FACET_OUTLINE", "O1 facet outline (section count emerges from evidence clusters)"),
    ("PG_ROUTE_ALL_BASKETS", "F1 route-every-verified-basket (consolidate-don't-drop the stranded baskets)"),
    ("PG_EV_BUDGET_TRACKS_PAYLOAD", "F2 per-section evidence budget tracks full matched payload (ceiling removed)"),
    ("PG_WORD_BUDGET_TRACKS_PAYLOAD", "F5 per-section word budget tracks full routed payload (clamp removed)"),
    ("PG_EXPERT_FACET_PLANNER", "R1 expert facet planner (widen retrieval breadth)"),
    ("PG_FACET_COMPLETENESS", "R2 facet completeness (retrieval-breadth completeness pass)"),
    ("PG_QUALIFIER_ELABORATION", "D1 within-basket verbatim qualifier elaboration (keep-all; Gate-B-dark)"),
    ("PG_ENRICHMENT_FACET_ROUTE", "D4 facet-routed enrichment placement (keep-all; Gate-B-dark)"),
    # The Box C L2 lever (PG_SUBTOPIC_DECOMPOSITION) is a DISTINCT force-ON slate flag (slate "1" +
    # _BENCHMARK_FORCE_ON_FLAGS force-set + _WINNER_FLAG_ALLOWLIST), NOT folded into THIS "8 previously-dark
    # levers" assertion tuple: force-ON already force-sets it to "1" on every Gate-B run (a stray .env =0
    # cannot survive), so the pre-spend assertion membership is redundant for it.
)


def assert_coverage_levers_armed() -> None:
    """FAIL CLOSED (pre-spend, BEFORE the sweep import) if any DRB-II COVERAGE LEVER is not truthy in the
    EFFECTIVE env — i.e. a breadth lever would run silently DARK because the slate did not land it (a stray
    operator/.env =0 survived, or a force-on pin was dropped). Mirrors the WINNER-SLATE-DARK / REQUIRED-OFF
    assert style: reads ``os.environ`` + the ``_COVERAGE_LEVER_FLAGS`` constants only; touches no gate, no
    evidence, no verdict (FAITHFULNESS-NEUTRAL). Called immediately after ``assert_full_capability_slate_applied``
    in ``run_gate_b_query`` so the env reflects exactly the slate's force values.

    §-1.3 DNA-ALIGNED: it asserts the existing breadth levers are ARMED — it introduces NO cap/target/thinner/
    canary and NO forced breadth number. Shares the default-ON ``PG_WINNER_SLATE_PRESPEND_ASSERT`` kill-switch
    (LAW VI) with the winner-slate assertion (a deliberate operator experiment disables both together)."""
    if not _winner_slate_prespend_assert_enabled():
        return
    dark = [
        (flag, why) for flag, why in _COVERAGE_LEVER_FLAGS
        if os.getenv(flag, "0").strip().lower() not in ("1", "true", "yes", "on")
    ]
    if dark:
        _detail = "; ".join(f"{_f} ({_w}) = {os.getenv(_f)!r}" for _f, _w in dark)
        raise RuntimeError(
            "benchmark preflight FAILED [COVERAGE-LEVER-DARK] (pre-spend, pre-import): "
            f"{len(dark)} DRB-II coverage lever(s) did not take effect — the paid run would ship a NARROWER "
            "report (fewer facet sections / stranded verified baskets dropped / budgets clamped / thinner "
            "retrieval / no qualifier elaboration / no facet-routed enrichment). "
            f"Dark: {_detail}. apply_full_capability_benchmark_slate() must run immediately before this "
            "assertion (it force-ON-pins each lever); set PG_WINNER_SLATE_PRESPEND_ASSERT=0 ONLY for a "
            "deliberate operator experiment."
        )


def _assert_mineru25_http_backend_ready() -> None:
    """I-deepfix-001 Item-10 (#1344): FAIL-LOUD pre-spend readiness probe for the W4 mineru25 clinical-PDF
    winner — so a mis-provisioned GPU box can NEVER silently ship the Docling loser.

    Called from the WINNER-FIRES W4 preflight branch (only when PG_CLINICAL_PDF_EXTRACTOR=mineru25 and
    NOT offline). GPU-present (checked by the caller) is necessary but NOT sufficient: mineru25 now runs
    via the supervised dedicated-GPU ``mineru-vllm-server`` reached through the isolated-venv ``mineru``
    CLI. If the server is unreachable OR the CLI cannot be resolved, ``_mineru25_extract`` raises and
    EVERY clinical PDF degrades to Docling/PyMuPDF (then the circuit breaker opens) — the exact
    dark-winner failure this probe surfaces BEFORE a paid token instead of silently mid-retrieval.

    Codex P1 (Item-10): probe the SAME checks ``_mineru25_extract`` runs at fetch time, REGARDLESS of the
    resolved backend LABEL. ``_mineru25_extract`` no longer has an in-process path — it ALWAYS reads
    ``cfg.server_url``, resolves the CLI, and shells out to the ``vlm-http-client`` CLI (the
    ``-b vlm-http-client`` transport is hard-wired in ``client_cli_argv``). So a stale
    ``PG_MINERU25_BACKEND=in-process`` export must NOT short-circuit this probe to a false-green: on such
    a host (no server URL) the extractor raises "no server URL configured" and degrades every clinical
    PDF to Docling. This probe therefore checks server-URL-present + CLI-resolvable + server-reachable for
    ANY backend label, so a probe PASS genuinely predicts a fetch-time PASS.

    Reuses ``resolve_mineru_backend`` (env > YAML) so the probe checks the SAME config
    ``_mineru25_extract`` will resolve at fetch time. Raises RuntimeError with an actionable message on
    any fault. FAITHFULNESS-NEUTRAL: extractor-provisioning only; the FROZEN faithfulness engine is
    untouched.
    """
    import shutil as _shutil  # noqa: PLC0415
    import urllib.request as _urlreq  # noqa: PLC0415

    from src.polaris_graph.scale.mineru_vllm_config import (  # noqa: PLC0415
        MineruBackendConfigError,
        resolve_mineru_backend,
    )

    try:
        _cfg = resolve_mineru_backend()
    except MineruBackendConfigError as _exc:
        raise RuntimeError(
            "benchmark preflight FAILED [WINNER-FIRES W4]: PG_CLINICAL_PDF_EXTRACTOR=mineru25 but the "
            f"mineru backend is misconfigured: {_exc}"
        )
    # (0) A non-empty server URL is the extractor's FIRST fail-loud (``_mineru25_extract`` raises "no
    # server URL configured" for an empty URL — the in-process path is RETIRED). Check it REGARDLESS of
    # the resolved backend label (Codex P1): a stale ``PG_MINERU25_BACKEND=in-process`` override with no
    # URL would otherwise pass this probe on the old `if not is_http_client: return` early-out, yet the
    # extractor (which ignores the label and hard-wires ``-b vlm-http-client``) degrades EVERY clinical
    # PDF to Docling at fetch time. Failing here makes a probe PASS genuinely predict a fetch-time PASS.
    _server_url = (_cfg.server_url or "").strip().rstrip("/")
    if not _server_url:
        raise RuntimeError(
            "benchmark preflight FAILED [WINNER-FIRES W4]: PG_CLINICAL_PDF_EXTRACTOR=mineru25 but no "
            f"mineru server URL is configured (resolved backend={_cfg.backend!r}). The in-process mineru "
            "path is RETIRED — _mineru25_extract ALWAYS shells out to the vlm-http-client CLI + server "
            "URL, so an empty URL (a stale PG_MINERU25_BACKEND=in-process export leaves it unset) degrades "
            "EVERY clinical PDF to the Docling loser. Set PG_MINERU25_SERVER_URL (or "
            "PG_MINERU25_BACKEND=vlm-http-client so the slate wires the standard-local URL), or set "
            "PG_CLINICAL_PDF_EXTRACTOR=docling to skip the W4 winner. Refusing to silently degrade."
        )

    # (1) The isolated-venv mineru CLI must be resolvable (same logic _mineru25_extract uses). The prod
    # venv does NOT ship mineru; the box must set PG_MINERU25_CLI_PATH (or have mineru on PATH).
    _cli = (_cfg.client_cli or "").strip() or "mineru"
    _cli_path = _cli if os.path.isabs(_cli) else (_shutil.which(_cli) or "")
    if not _cli_path or not os.path.exists(_cli_path):
        raise RuntimeError(
            "benchmark preflight FAILED [WINNER-FIRES W4]: mineru25 vlm-http-client CLI not found "
            f"(resolved {_cli!r} -> {_cli_path!r}). Set PG_MINERU25_CLI_PATH to the isolated-venv mineru "
            "binary (e.g. /root/mineru_svc/bin/mineru) on the GPU box, or set "
            "PG_CLINICAL_PDF_EXTRACTOR=docling to skip the W4 winner. Refusing to silently degrade every "
            "clinical PDF to the Docling loser."
        )

    # (2) The supervised mineru-vllm-server must be reachable at the resolved server URL (from step 0) —
    # probe /health (the vLLM server serves GET /health -> 200). A cheap one-shot GET with a short
    # timeout; any failure (connection refused, timeout, non-200) FAILS the run before spend.
    _health_url = f"{_server_url}/health"
    _probe_timeout = float(os.getenv("PG_MINERU25_HEALTH_PROBE_TIMEOUT_S", "5") or "5")
    try:
        with _urlreq.urlopen(_health_url, timeout=_probe_timeout) as _resp:  # noqa: S310 — fixed local URL
            _status = getattr(_resp, "status", None) or _resp.getcode()
            if _status != 200:
                raise RuntimeError(f"/health returned HTTP {_status}")
    except Exception as _exc:  # noqa: BLE001 — any unreachable-server signal is a fail-loud
        raise RuntimeError(
            "benchmark preflight FAILED [WINNER-FIRES W4]: mineru25 vlm-http-client server NOT reachable "
            f"at {_server_url} ({str(_exc)[:160]}). Launch the supervised dedicated-GPU mineru-vllm-server "
            "(config/serving/mineru_vllm_server.yaml: CUDA_VISIBLE_DEVICES=1, --gpu-memory-utilization 0.4, "
            "--max-num-seqs 20) on card 1 before the paid run, or set PG_CLINICAL_PDF_EXTRACTOR=docling to "
            "skip the W4 winner. Refusing to silently degrade every clinical PDF to the Docling loser."
        )


def preflight_full_capability(smoke_scale: bool = False, offline: bool = False) -> None:
    """FAIL CLOSED if the effective benchmark config is below full capability or unobservable — so a
    silent throttle (the ~40-URL bug) can NEVER reach a paid run undetected. Raises RuntimeError.

    I-arch-007 ``smoke_scale=True`` (the --smoke-scale plumbing run) skips ONLY the CAPACITY floors —
    the breadth-knob floors, the min cost cap, the generator-timeout floor, and the extra-env capacity
    floors — because a smoke is DELIBERATELY below full breadth/cost. EVERY faithfulness check stays
    unconditional: the faithfulness slate, the section-fraction coverage floor, the required/required-off
    feature flags, the semantic_v2 relevance scorer, the cited-span window bound, the enforce-mode
    verifier, the row-cap ban, and the timeout-hierarchy ORDERING (which the smoke still satisfies).
    Default OFF = a full cert run validates every floor exactly as before.

    I-deepfix-001 (#1344) ``offline=True`` (an injected fake transport — the offline/unit-test path,
    ``run_gate_b_query(transport=<fake>)``) skips ONLY the WINNER-FIRES GPU-HOST probes (W4 GPU-present,
    W5 GPU warning) — an offline/CI host legitimately has no GPU and never spends a token, so a GPU
    assertion there is a false-fail, not a winner-dark catch. The 3 PURITY gates' STRUCTURAL checks
    (NO-LOSER, the W6/W7/W5 model-identity probes, SLATE-PURITY, W9) ALL stay unconditional — they are
    config-only and meaningful offline. The GPU-host probe is the LIVE-run host-capability check (the
    no-GPU host silently runs the docling LOSER), so it binds only on the real paid run (offline=False)."""
    # I-wire-001 (#1296): LOUD WARNING for the build-deferred section winner (W9 dedup — no run-path
    # consumer and no wiring flag; the I-wire-001 P1-2 dedup-agent reconcile confirmed it is neither a
    # standalone wire nor CRAG-transitive). W1 intent_frame GRADUATED to preflight-required at I-wire-001
    # P1-1 (run_intent_frame() is now called at run_honest_sweep_r3.py:6426, fail-closed), so it is no
    # longer warned here. Emitted FIRST — before any raise below — so it ALWAYS surfaces (the operator
    # reads by ear; it must not be skippable behind a later abort).
    # I-deepfix-001 (#1344) PURITY: this early heads-up is RETAINED but the W9 dark-winner POLICY is now
    # ENFORCED by the dedicated W9 GATE at the END of this function (the loud SUBSUMED-by-#10 status + the
    # fail-closed PG_W9_CONTENT_DEDUP / PG_W9_DARK_ACK §-1.3 protection). This loop is the FIRST-line
    # naming so the gap is never silent; the W9 gate is the operator-ack enforcement. NOT a raise here: W9
    # is honestly not on the run path, so REQUIRING it would FALSE-PASS (env set while the feature never
    # fires). Naming it keeps the gap explicit, never silent.
    import logging as _wire_logging
    _wire_logger = _wire_logging.getLogger("run_gate_b")
    for _deferred_name, _deferred_why in _BENCHMARK_BUILD_DEFERRED_WINNERS:
        _deferred_msg = (
            f"[preflight WARNING] I-wire-001 build-deferred section winner NOT enforced: "
            f"{_deferred_name} — {_deferred_why}"
        )
        _wire_logger.warning(_deferred_msg)
        print(_deferred_msg)
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
    # I-beatboth-011 #1290: fail-CLOSED that the 4-role D8 seam timeout is BOUNDED BELOW the run-wall, so
    # the seam can never grind past the wall (the 7.2h default max(7200,4*6500) the path-audit caught). The
    # full slate force-pins PG_FOUR_ROLE_SEAM_TIMEOUT_SECONDS, but a refactor dropping that pin would
    # silently restore the grind with no signal — so assert the LIVE resolved values here. Value-agnostic
    # (no hardcoded bound), smoke-safe (smoke pins 1800 < run-wall). Timeout plumbing only — faithfulness
    # untouched. This is the seam<=run-wall ordering the preflight previously OMITTED (only checked
    # generator<section<run-wall).
    from scripts.run_honest_sweep_r3 import (
        _resolve_four_role_seam_timeout as _resolve_seam,
        run_wall_clock_seconds as _run_wall_secs,
    )
    _seam_to = float(_resolve_seam())
    _run_wall = float(_run_wall_secs())
    if not (_seam_to <= _run_wall):
        raise RuntimeError(
            f"benchmark preflight FAILED: 4-role D8 seam timeout {_seam_to:.0f}s EXCEEDS the run-wall "
            f"{_run_wall:.0f}s (PG_RUN_WALL_CLOCK_SEC) — the seam would grind past the wall (the ~7.2h "
            f"default class). Pin PG_FOUR_ROLE_SEAM_TIMEOUT_SECONDS below the run-wall in the slate."
        )
    # I-beatboth-011 idx59 (#1289): fail-CLOSED that the PG_FOUR_ROLE_CLAIM_WORKERS rebind actually took.
    # The slate value only reaches the D8 seam via a post-import REBIND of _sweep_integration._CLAIM_WORKERS
    # in apply_full_capability_benchmark_slate (the env set alone is a silent no-op — the module global was
    # frozen at the import default 6). A future refactor dropping the rebind would SILENTLY halve D8
    # concurrency with no signal. Read the LIVE module attribute and compare to the env INT — value-agnostic
    # (never a hardcoded 12), smoke-safe. FAITHFULNESS-NEUTRAL: worker count only.
    if not smoke_scale:
        import src.polaris_graph.roles.sweep_integration as _sweep_integration_check
        _live_cw = int(getattr(_sweep_integration_check, "_CLAIM_WORKERS", 0))
        _env_cw = int(os.environ.get("PG_FOUR_ROLE_CLAIM_WORKERS", "6"))
        if _live_cw != _env_cw:
            raise RuntimeError(
                f"benchmark preflight FAILED: _sweep_integration._CLAIM_WORKERS={_live_cw} != "
                f"PG_FOUR_ROLE_CLAIM_WORKERS={_env_cw} — the D8 claim-worker REBIND did not take (the env set "
                f"is a silent no-op without it), so D8 concurrency would silently halve to the import default. "
                f"Restore the _CLAIM_WORKERS rebind in apply_full_capability_benchmark_slate."
            )
    # I-beatboth-011 §3.1 ROUTE C (#1289, advisor 2026-06-21): EXERCISE the abstractive-writer ON path at
    # preflight. The slate force-sets PG_ABSTRACTIVE_WRITER=1; its activation is FAIL-CLOSED and requires
    # PG_STRICT_VERIFY_ENTAILMENT=enforce (a paraphrase's only semantic guarantee is the entailment leg).
    # Calling assert_activation_preconditions() HERE catches a mis-set entailment mode BEFORE spend, not at
    # the first section mid-run. Only assert when the writer is actually ON (an operator may legitimately
    # disable it for a verbatim-only run). Faithfulness gate — runs on smoke + full alike.
    if os.getenv("PG_ABSTRACTIVE_WRITER", "0").strip().lower() not in ("", "0", "false", "off", "no"):
        from src.polaris_graph.generator.abstractive_writer import (  # noqa: PLC0415
            assert_activation_preconditions as _assert_aw_preconditions,
        )
        try:
            _assert_aw_preconditions()
        except RuntimeError as _awe:
            raise RuntimeError(f"benchmark preflight FAILED: {_awe}") from _awe
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
    # I-beatboth-011 KEYSTONE (#1289): PG_HTML_EXTRACTOR selects the trafilatura profile by a STRING value,
    # not a boolean, so it cannot ride the truthy-required loop above (the PG_RELEVANCE_SCORER precedent).
    # Fail closed if it is not the precision profile for a paid run — OFF/'default' silently reverts the
    # fetch lane to the recall profile that lets more page-furniture into the corpus (the upstream half of
    # the chrome fix). The slate force-EXACTs it to 'trafilatura_precision'.
    _html_extractor = os.getenv("PG_HTML_EXTRACTOR", "default").strip().lower()
    if _html_extractor != "trafilatura_precision":
        raise RuntimeError(
            f"benchmark preflight FAILED: PG_HTML_EXTRACTOR={_html_extractor!r} is not "
            f"'trafilatura_precision' — the precision extraction profile is dead-by-config (the recall "
            f"profile runs instead, admitting more page-furniture spans). Set "
            f"PG_HTML_EXTRACTOR=trafilatura_precision before the run."
        )
    # I-wire-001 (#1296): value-equals assertions for the 4 STRING (model-selector) section winners —
    # they cannot ride the truthy required-flags loop above ("qwen3"/"mineru25"/"Qwen/Qwen3-Reranker-0.6B"
    # are not "1"), the SAME reason PG_RELEVANCE_SCORER is asserted separately. Fail CLOSED so a dropped
    # force-exact pin or a stray/empty value can never silently leave a model winner OFF (the default
    # model would run). The slate force-exacts these; the assertion passes on the paid run and a paid run
    # genuinely exercises the winner-model load path. FAITHFULNESS-NEUTRAL (model choice; engine frozen).
    # I-deepfix-001 (#1344) SMOKE EXCEPTION (one key): the smoke pins PG_CLINICAL_PDF_EXTRACTOR=docling
    # (the safe non-VLM docling->PyMuPDF PDF path) to dodge the mineru25 GPU-VLM native SIGABRT that was
    # killing the whole run before the back half — so on a smoke this ONE key is expected to be 'docling'
    # while the PAID run still requires the slate's 'mineru25'. All OTHER winners stay asserted on BOTH
    # paths (the smoke genuinely loads Qwen3 embed/rerank etc.). §-1.3: docling extracts the PDF body, no
    # source dropped; mineru25-on-paid + its crash-isolation is the queued fix before the paid run.
    for _winner_flag, _winner_expected in _BENCHMARK_WINNER_EXACT_VALUE_ASSERTIONS.items():
        if smoke_scale and _winner_flag == "PG_CLINICAL_PDF_EXTRACTOR":
            _winner_expected = "docling"   # smoke: safe non-VLM PDF path; paid keeps mineru25
        _winner_value = os.getenv(_winner_flag, "").strip()
        if _winner_value != _winner_expected:
            raise RuntimeError(
                f"benchmark preflight FAILED: {_winner_flag}={_winner_value!r} != I-wire-001 winner "
                f"value {_winner_expected!r} — the section winner is silently OFF (the default model "
                f"runs instead). The slate force-exacts it; restore the pin before the run."
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
                f"benchmark preflight FAILED: {flag} is enabled — it is a killed LOSER / un-span-verified "
                f"layer that must be OFF for the WINNERS-ONLY purity build (I-deepfix-001 #1344). A stray "
                f"operator/.env value re-armed it past the slate force-EXACT. Set {flag}=0 before the run."
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
    # I-deepfix-001 W02-retrieval-wall-activate (#1344): the per-question retrieval wall MUST be
    # STRICTLY BELOW the run-wall so the partial corpus HANDS OFF (disclosed retrieval_wall_hit)
    # BEFORE the run-level asyncio.wait_for guillotines the whole question to a TIMEOUT stub. This
    # is the only sum-free invariant that MUST hold to "reach a report"; it FAILS CLOSED here, before
    # any spend, if a stale .env value (FLOOR semantics can only RAISE the wall) pushed the retrieval
    # wall to/past the run-wall. NOTE: a forensic-style aggregate-fit assertion of the form
    # `retrieval_wall + bounded-parallel(n_sections x section_wall) + seam_timeout <= run_wall` was
    # REJECTED as category-confused: section_wall (9000) and seam (7200) are INDEPENDENT hang-CATCH
    # backstops each deliberately sized ABOVE expected time, while run_wall (10800) is sized to the
    # EXPECTED ~86-min run + margin (per the B20 slate comment), NOT to the sum of inner backstops.
    # That sum (5400+9000+7200=21600) is ~2x the locked run-wall and would fail-close on EVERY healthy
    # run; inventing "expected-time" constants to make it pass would be a banned magic-number knob
    # (LAW VI / §-1.3). Whether the BACK HALF actually fits in (run_wall - retrieval_wall) is a real-run
    # timing property, not a static-preflight one — it belongs to the smoke/real-run check, not here.
    _eff_retr_wall = int(os.getenv("PG_RETRIEVAL_QUESTION_WALL_SECONDS", "0") or "0")
    if _eff_retr_wall > 0 and not (_eff_retr_wall < _eff_run_wall) and not smoke_scale:
        raise RuntimeError(
            "benchmark preflight FAILED: PG_RETRIEVAL_QUESTION_WALL_SECONDS="
            f"{_eff_retr_wall} is not strictly below PG_RUN_WALL_CLOCK_SEC={_eff_run_wall} — the "
            "per-question retrieval wall would not hand off the partial corpus before the run-wall "
            "guillotines the whole question to a TIMEOUT stub. Lower the retrieval wall below the "
            "run-wall (the slate sets 5400 < 10800) before the run."
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

    # ═════════════════════════════════════════════════════════════════════════════════════════════════
    # I-deepfix-001 (#1344) PURITY BUILD — the THREE SERIOUS-PREFLIGHT GATES. Authored INTO
    # preflight_full_capability (runs AFTER apply_full_capability_benchmark_slate, fail-CLOSED before any
    # spend) per state/deepfix_purity_buildspec.md "SERIOUS PREFLIGHT — 3 gates". The FROZEN faithfulness
    # engine (strict_verify / NLI / 4-role / provenance / span-grounding) is NEVER touched — this is
    # retrieval-orchestration purity only. These gates run on smoke + full alike (the smoke slate also kills
    # the losers); they are NOT capacity floors, so no smoke_scale skip.
    # ═════════════════════════════════════════════════════════════════════════════════════════════════
    _ON_TOKENS = ("1", "true", "yes", "on")

    def _is_off(_v: str) -> bool:
        """A loser env value is provably OFF (the NO-LOSER fail-closed contract)."""
        return _v.strip().lower() in ("", "0", "false", "no", "off")

    # ── GATE (A): NO-LOSER — assert every killed loser is provably dead ──────────────────────────────
    # The boolean losers are already wired through the _BENCHMARK_PREFLIGHT_REQUIRED_OFF_FLAGS loop above
    # (STORM core/ingest/agentic/decompose/iterresearch/research-planner — each raises if truthy).
    # This gate adds the STRUCTURAL + STRING-valued + module-level loser assertions the truthy-off loop
    # cannot express, each fail-CLOSED with a clear message.
    # R1_deepener_enable: PG_SWEEP_EVIDENCE_DEEPENER is REMOVED from the loser list — it is the recall lever
    # (setdefault-ON, widen-only), NOT a killed loser; a value of "1" is now VALID, not a dropped-pin regression.
    #
    # A.1 — slate membership: a killed loser must NOT have crept back into FORCE_ON / REQUIRED-truthy (a
    # dropped-pin regression). The REQUIRED_OFF loop catches the env VALUE; this catches the slate STRUCTURE
    # (a loser force-on'd back into the slate dict would set the env truthy AND fail the REQUIRED_OFF loop,
    # but naming the structural cause here makes the regression unambiguous).
    for _loser in (
        "PG_STORM_ENABLED_IN_BENCHMARK", "PG_STORM_INGEST_WEB_RESULTS",
        "PG_STORM_OUTLINE_SECTIONS", "PG_AGENTIC_SEARCH_IN_BENCHMARK",
    ):
        if _loser in _BENCHMARK_FORCE_ON_FLAGS or _loser in _BENCHMARK_PREFLIGHT_REQUIRED_FLAGS:
            raise RuntimeError(
                f"benchmark preflight FAILED [NO-LOSER]: {_loser} is a KILLED loser but is force-ON / "
                f"preflight-required in the slate (I-deepfix-001 #1344 purity) — it must be removed from "
                f"_BENCHMARK_FORCE_ON_FLAGS / _BENCHMARK_PREFLIGHT_REQUIRED_FLAGS (it is force-EXACT '0' + "
                f"REQUIRED_OFF). A dropped-pin regression re-armed the loser."
            )
    # A.2 — STORM query-count floor must be gone (a 30-query floor would force a STORM knob back into the
    # slate via the floor loop). The STORM outline scaffold flag must resolve OFF (its producer is dead).
    if "PG_STORM_MAX_BENCHMARK_QUERIES" in _BENCHMARK_PREFLIGHT_FLOORS:
        raise RuntimeError(
            "benchmark preflight FAILED [NO-LOSER]: PG_STORM_MAX_BENCHMARK_QUERIES is still in "
            "_BENCHMARK_PREFLIGHT_FLOORS — STORM is dead; no query-count floor should linger (it would "
            "re-introduce a STORM query knob)."
        )
    if not _is_off(os.getenv("PG_STORM_OUTLINE_SECTIONS", "0")):
        raise RuntimeError(
            "benchmark preflight FAILED [NO-LOSER]: PG_STORM_OUTLINE_SECTIONS is enabled — it is a STORM "
            "consumer (the outline scaffold); STORM is a killed loser. Set it 0 (section structure reverts "
            "to research_plan/legacy, which keeps compose=floor_abstractive W12 intact)."
        )
    # A.3 — the STORM under-fire floor must be 0 so the INVERTED run-health abort_discovery_degraded can
    # never trip on a (correctly) absent STORM.
    try:
        _storm_min_eff = int(os.getenv("PG_STORM_MIN_EFFECTIVE_QUERIES", "0"))
    except ValueError:
        raise RuntimeError(
            "benchmark preflight FAILED [NO-LOSER]: PG_STORM_MIN_EFFECTIVE_QUERIES="
            f"{os.getenv('PG_STORM_MIN_EFFECTIVE_QUERIES')!r} is not an int."
        )
    if _storm_min_eff != 0:
        raise RuntimeError(
            f"benchmark preflight FAILED [NO-LOSER]: PG_STORM_MIN_EFFECTIVE_QUERIES={_storm_min_eff} != 0 — "
            f"a non-zero under-fire floor would let the run-health gate emit abort_discovery_degraded when "
            f"the (correctly dead) STORM does not fire (the INVERTED-mandate self-abort)."
        )
    # A.4 — the storm_interviews MODULE flag (PG_STORM_ENABLED, storm_interviews.py:42) must resolve OFF.
    # The slate force-EXACTs it "0" (dual-arm kill). Assert the EFFECTIVE ENV value — NOT the import-time
    # cached module attribute, which is a test-order artifact (the module may have imported under the
    # operator .env PG_STORM_ENABLED=1 BEFORE the slate ran; that is HARMLESS on Gate-B because the run path
    # keys on PG_STORM_ENABLED_IN_BENCHMARK, but the slate pins this second arm 0 too for purity). If the
    # module is importable, REFRESH its cached attribute from the slate-applied env so the module agrees.
    if not _is_off(os.getenv("PG_STORM_ENABLED", "0")):
        raise RuntimeError(
            "benchmark preflight FAILED [NO-LOSER]: PG_STORM_ENABLED is enabled — the storm_interviews "
            "engine module flag (the second STORM arm) is armed. STORM is a killed loser; the slate "
            "force-EXACTs PG_STORM_ENABLED=0. A stray operator/.env value re-armed it past the slate."
        )
    try:
        import src.polaris_graph.agents.storm_interviews as _storm_mod  # noqa: PLC0415
        # Re-sync the import-time-cached module flag to the slate-applied env (the run path re-reads the env
        # gate at call time; this keeps the module attribute honest for any direct module-flag reader).
        _storm_mod.PG_STORM_ENABLED = (os.getenv("PG_STORM_ENABLED", "0") == "1")
    except ImportError:
        pass  # module genuinely absent on this checkout → the engine cannot fire (also dead)
    # A.5 — the live relevance embedder hole: prefetch_offtopic_filter._embed_model_name() reads
    # PG_EMBED_MODEL (NOT the slate-pinned PG_EMBEDDER_MODEL). A stray .env PG_EMBED_MODEL=all-MiniLM would
    # route the live embedder to MiniLM while the env-string preflight passes GREEN. Assert the EFFECTIVE id.
    _embed_id = os.getenv("PG_EMBED_MODEL", "Qwen/Qwen3-Embedding-8B").strip()
    if "minilm" in _embed_id.lower() or "qwen3-embedding-8b" not in _embed_id.lower():
        raise RuntimeError(
            f"benchmark preflight FAILED [NO-LOSER]: PG_EMBED_MODEL={_embed_id!r} is not the Qwen3-Embedding-8B "
            f"winner — the LIVE relevance/off-topic + selection embedder (prefetch_offtopic_filter._load_embedder) "
            f"reads THIS var (not the slate-pinned PG_EMBEDDER_MODEL), so a stray value silently routes it to "
            f"MiniLM (a killed loser). Pin PG_EMBED_MODEL=Qwen/Qwen3-Embedding-8B."
        )
    # A.6 — gemma must be ABSENT from the live judge + evaluator, both pinned to the §9.1.8 mirror (glm-5.2),
    # and the two must be EQUAL (the pathB two-family invariant the slate comment relies on). Read the
    # EFFECTIVE model the way the live code resolves it (env override else mirror default), not just the env.
    from src.polaris_graph.llm.openrouter_client import PG_MIRROR_MODEL as _mirror_model  # noqa: PLC0415
    _entail_model = (os.getenv("PG_ENTAILMENT_MODEL") or _mirror_model).strip()
    _eval_model = (os.getenv("PG_EVALUATOR_MODEL") or _mirror_model).strip()
    for _judge_label, _judge_model in (("PG_ENTAILMENT_MODEL", _entail_model), ("PG_EVALUATOR_MODEL", _eval_model)):
        if "gemma" in _judge_model.lower():
            raise RuntimeError(
                f"benchmark preflight FAILED [NO-LOSER]: {_judge_label} resolves to {_judge_model!r} — "
                f"gemma is operator-locked OUT (§9.1.8; the #1249/#1251/#1252 drift). Pin it to the locked "
                f"mirror z-ai/glm-5.2."
            )
        if _judge_model != "z-ai/glm-5.2":
            raise RuntimeError(
                f"benchmark preflight FAILED [NO-LOSER]: {_judge_label} resolves to {_judge_model!r} != the "
                f"§9.1.8 locked mirror 'z-ai/glm-5.2'. force-EXACT it in the slate."
            )
    if _entail_model != _eval_model:
        raise RuntimeError(
            f"benchmark preflight FAILED [NO-LOSER]: PG_ENTAILMENT_MODEL={_entail_model!r} != "
            f"PG_EVALUATOR_MODEL={_eval_model!r} — the pathB two-family invariant (entailment==evaluator) "
            f"is violated."
        )
    # A.7 — WRRF (W3) must resolve ON: the SAME kill-switch proves the winner fires AND the legacy
    # serial/RRF-free fusion path is dead (documentary — the correct winner-displaces-legacy pattern).
    from src.polaris_graph.retrieval.search_fusion_wrrf import wrrf_enabled as _wrrf_enabled  # noqa: PLC0415
    if not _wrrf_enabled():
        raise RuntimeError(
            "benchmark preflight FAILED [NO-LOSER]: wrrf_enabled() is False — PG_SEARCH_FUSION_WRRF (W3) is "
            "off, so the legacy RRF-free fusion (a non-winner) would run. Force-on PG_SEARCH_FUSION_WRRF."
        )

    # ── GATE (B): WINNER-FIRES — behavioral PRE-SPEND probes for the tractable winners ───────────────
    # Behavioral, NOT flag-set. The TRACTABLE pre-spend probes that do NOT require a heavy model LOAD or a
    # live LLM call run HERE (load-identity / config-resolve / GPU-present). The deeper behavioral probes
    # (actually LOAD the 8B embedder + a 4096-dim cosine; drive score_passages to read reranker_device;
    # drive classify_sources_llm_tiering to assert llm_success>0; the W12/W13 fixture composes) are
    # DEFERRED to the VM behavioral run + the POST-RUN firing-marker grep — see _WINNER_FIRING_MARKER_CONTRACT
    # and the deferred-probe note below (NOT faked: a heavy GPU model load at preflight is forbidden off-VM,
    # and a real-corpus LLM probe is a spend; the run-log firing-marker post-check is the honest behavioral
    # proof). Probes are import-guarded so a missing optional dep degrades to the env/identity assertion
    # rather than a false preflight crash.
    #
    # W4 — clinical-PDF=mineru25 GPU-present gate. mineru25 fires ONLY when a GPU is visible; on a no-GPU host
    # access_bypass silently returns '' and falls through to the docling/PyMuPDF LOSER (the dark-winner
    # failure). Env value-equals is already asserted above; here assert a GPU is actually present so the
    # docling fall-through is provably unreachable on the cert host.
    if (not offline) and os.getenv("PG_CLINICAL_PDF_EXTRACTOR", "").strip().lower() == "mineru25":
        try:
            import torch as _torch  # noqa: PLC0415
            if not _torch.cuda.is_available():
                raise RuntimeError(
                    "benchmark preflight FAILED [WINNER-FIRES W4]: PG_CLINICAL_PDF_EXTRACTOR=mineru25 but "
                    "torch.cuda.is_available() is False — on a no-GPU host mineru25 silently returns '' and "
                    "falls through to the docling/PyMuPDF LOSER for every clinical PDF. Run on the GPU VM "
                    "(offline/unit-test runs pass transport=<fake> and skip this host-capability probe)."
                )
        except ImportError:
            raise RuntimeError(
                "benchmark preflight FAILED [WINNER-FIRES W4]: PG_CLINICAL_PDF_EXTRACTOR=mineru25 but torch "
                "is not importable — the GPU VLM extractor cannot load; it would fall through to the docling "
                "LOSER. Install torch / run on the GPU VM."
            )
        # I-deepfix-001 Item-10 (#1344): GPU-present is necessary but NOT sufficient — mineru25 now runs via
        # the vlm-http-client backend (a supervised dedicated-GPU mineru-vllm-server reached through the
        # isolated-venv mineru CLI). Probe the resolved server /health + the CLI path so a box that has a GPU
        # but no running server / no CLI fails LOUD before spend instead of silently degrading every clinical
        # PDF to the Docling loser (the exact failure in the drb live log). Runs REGARDLESS of the resolved
        # backend label — the extractor has no in-process path, so a stale in-process override cannot skip it.
        _assert_mineru25_http_backend_ready()
    # W6 — embed=Qwen3-Embedding-8B LOAD-IDENTITY (tractable: env-resolve, no model load). The live loader
    # prefetch_offtopic_filter._embed_model_name() must resolve to the 8B id (non-None, the winner). The
    # DEEPER probe (actually LOAD the 8B + assert a 4096-dim non-None cosine) is DEFERRED to the VM run (a
    # heavy GPU load is forbidden at preflight off-VM); the run-log "loading relevance embedder
    # model=Qwen/Qwen3-Embedding-8B" firing marker is the behavioral proof it loaded.
    try:
        from src.polaris_graph.retrieval.prefetch_offtopic_filter import (  # noqa: PLC0415
            _embed_model_name as _resolve_embed_id,
        )
        _resolved_embed = (_resolve_embed_id() or "").strip()
        if not _resolved_embed or "qwen3-embedding-8b" not in _resolved_embed.lower():
            raise RuntimeError(
                f"benchmark preflight FAILED [WINNER-FIRES W6]: prefetch_offtopic_filter._embed_model_name() "
                f"resolves to {_resolved_embed!r}, not the Qwen3-Embedding-8B winner — the live relevance "
                f"embedder would load a non-winner (MiniLM) or None (silent lexical degrade)."
            )
    except ImportError:
        pass  # retrieval module unavailable on this checkout → covered by the A.5 env-id assertion
    # W7 — rerank=Qwen3-Reranker-4B IDENTITY (tractable: config-resolve, no model load). CrossEncoderConfig
    # .from_env() must select the 4B causal-LM reranker. The DEEPER probe (load + a permutation reorder) is
    # DEFERRED to the VM run; the run-log "[qwen-reranker] loading Qwen/Qwen3-Reranker-4B" marker is the
    # behavioral proof. (#1312: loading this CausalLM via sentence_transformers.CrossEncoder mints a random
    # head — the live path uses the dedicated causal-LM scorer; this identity check reads the config only.)
    try:
        from src.config.core import CrossEncoderConfig as _CrossEncoderConfig  # noqa: PLC0415
        _rerank_cfg_model = (_CrossEncoderConfig.from_env().model or "").strip()
        if _rerank_cfg_model != "Qwen/Qwen3-Reranker-4B":
            raise RuntimeError(
                f"benchmark preflight FAILED [WINNER-FIRES W7]: CrossEncoderConfig.from_env().model="
                f"{_rerank_cfg_model!r} != 'Qwen/Qwen3-Reranker-4B' — PG_RERANKER_MODEL did not select the "
                f"4B reranker winner (the ms-marco-MiniLM default or a stray value would run)."
            )
    except ImportError:
        pass  # config module unavailable → covered by the PG_RERANKER_MODEL value-equals assertion above
    # W5 — relevance reranker IDENTITY + GPU-present (tractable). The 0.6B reranker id must resolve to the
    # winner, and a GPU must be present so the reranker runs on cuda (a CPU run is a DISCLOSED degrade, not
    # the production path; a load FAILURE sets reranker_device='unavailable' = silent full-weight fallback).
    # The DEEPER probe (drive score_passages on an on/off-topic pair, assert device in {cuda,cpu} !=
    # 'unavailable' + the off-topic passage demoted) is DEFERRED to the VM run; the run-log "W2
    # content-relevance: scored" marker (device-stamped) is the behavioral proof.
    try:
        from src.polaris_graph.retrieval.content_relevance_judge import (  # noqa: PLC0415
            _reranker_model_name as _resolve_cr_rerank_id,
        )
        _cr_rerank_id = (_resolve_cr_rerank_id() or "").strip()
        if _cr_rerank_id != "Qwen/Qwen3-Reranker-0.6B":
            raise RuntimeError(
                f"benchmark preflight FAILED [WINNER-FIRES W5]: content_relevance_judge._reranker_model_name() "
                f"resolves to {_cr_rerank_id!r} != 'Qwen/Qwen3-Reranker-0.6B' — the relevance reranker winner "
                f"is not selected."
            )
    except ImportError:
        pass  # covered by the PG_CONTENT_RELEVANCE_RERANKER_MODEL value-equals assertion above
    if (not offline) and os.getenv("PG_CONTENT_RELEVANCE_JUDGE", "0").strip().lower() in _ON_TOKENS:
        try:
            import torch as _torch_cr  # noqa: PLC0415
            if not _torch_cr.cuda.is_available():
                _wire_logger.warning(
                    "[preflight WARNING W5] PG_CONTENT_RELEVANCE_JUDGE on but no GPU visible — the "
                    "Qwen3-Reranker-0.6B leg will run on CPU (a DISCLOSED degrade, not the production GPU "
                    "path). Run on the GPU VM for the cert run."
                )
        except ImportError:
            pass
    # POST-RUN FIRING-MARKER CONTRACT — exposed for the §-1.1 post-run audit. The audit applies each
    # _WINNER_FIRING_MARKER_CONTRACT predicate against the run-dir log via firing_marker_matched() (success-
    # specific: must_contain present AND no forbid twin on the same line) and FAILS if a WIRED non-conditional
    # winner's GENUINE-fire predicate did not match (flag-on but dark) — the behavioral proof the pre-spend
    # identity probes cannot give. Codex diff-gate iter-1 P1: the predicate replaces the prior bare-substring
    # value that false-passed on degraded/premature lines (W12 0/0 drafts, W13 unrelated [multi_section] logs,
    # W5 device=unavailable, W6/W7 pre-load-success). conditional=True winners (W4/W10) are data-dependent —
    # their absence is allowed, never a fail-on-absent.
    # DEFERRED-PROBE NOTE (honest, NOT faked): W4 (load + extract), W5 (score_passages device), W6 (load +
    # 4096-dim cosine), W7 (load + reorder), W8 (classify_sources_llm_tiering llm_success>0), W10 (NLI
    # cross-encoder merge), W11 (CRAG live grade), W12 (abstractive_pre_pass drafts>0), W13 (strict_verify
    # keep/drop fixture) each need a heavy GPU model LOAD or a live LLM spend — both forbidden at off-VM
    # preflight — so their behavioral verification is the run-log firing-marker post-check, not a fake
    # pre-spend stub. The contract dict IS that verification's machine-readable source of truth.

    # ── GATE (C): SLATE-PURITY — every force-on flag must map to a winner / frozen-engine infra ──────
    # The structural backstop that catches the NEXT STORM-like loser being force-on'd back into the slate.
    # Every flag in _BENCHMARK_FORCE_ON_FLAGS (all feature-enables) + every force-EXACT flag whose value is
    # an ON-token (a feature toggled on by exact value) OR a non-empty NON-NUMERIC STRING (a model/profile
    # PIN, e.g. PG_EMBED_MODEL / PG_RELEVANCE_SCORER / PG_FOUR_ROLE_REASONING_EFFORT) must be in
    # _WINNER_FLAG_ALLOWLIST. force-EXACT flags pinned to a FALSY ("0"/"") value (the killed losers) or a
    # NUMERIC string (timeouts / floats / counts — infra config, not feature-enables) are NOT winner-checked:
    # their purity is enforced by the NO-LOSER gate (the "0" pins) and their dedicated value validators
    # (the numeric knobs).
    #
    # I-deepfix-001 (#1344) PURITY (Codex P2-slate-purity-skips-string-force-exact): the prior loop ONLY
    # added force-exact flags whose value is an _ON_TOKEN — so STRING model PINS (PG_EMBED_MODEL=
    # 'Qwen/Qwen3-Embedding-8B', PG_RELEVANCE_SCORER='semantic_v2', PG_ENTAILMENT_MODEL='z-ai/glm-5.2', ...)
    # SKIPPED the allowlist entirely. A future BOGUS string force-exact (a re-introduced loser pinned to a
    # string value, e.g. PG_SOME_LOSER='legacy') would then sail through SLATE-PURITY. Extend the check to
    # ALSO require any non-empty, non-falsy, NON-NUMERIC string force-exact value's flag to be allowlisted
    # (every legitimate string pin already is — verified offline against the clean slate; the ONE non-model
    # string infra pin PG_FOUR_ROLE_REASONING_EFFORT was added to the allowlist alongside this change).
    # _is_off (defined above) handles the falsy/"0" skip; float-parseable handles the numeric-infra skip.
    _force_on_to_check = set(_BENCHMARK_FORCE_ON_FLAGS)
    for _fe_flag in _BENCHMARK_FORCE_EXACT_FLAGS:
        _fe_val = str(_FULL_CAPABILITY_BENCHMARK_SLATE.get(_fe_flag, "")).strip()
        if _is_off(_fe_val):
            continue                                   # killed-loser "0"/"" pin — NO-LOSER gate governs it
        if _fe_val.lower() in _ON_TOKENS:
            _force_on_to_check.add(_fe_flag)           # feature toggled on by exact value
            continue
        try:
            float(_fe_val)
            continue                                   # numeric infra (timeout / float / count) — value-validated
        except ValueError:
            _force_on_to_check.add(_fe_flag)           # genuine NON-NUMERIC string PIN — must be allowlisted
    for _on_flag in sorted(_force_on_to_check):
        if _on_flag not in _WINNER_FLAG_ALLOWLIST:
            raise RuntimeError(
                f"benchmark preflight FAILED [SLATE-PURITY]: {_on_flag} is force-on / force-EXACT to a "
                f"recognized-feature value in the slate but maps to no winner / frozen-engine infra flag in "
                f"_WINNER_FLAG_ALLOWLIST (I-deepfix-001 #1344 winners-only purity). Either it is a "
                f"re-introduced LOSER (the next STORM) — remove the force-on/force-exact — OR it is a "
                f"legitimately-new winner/infra flag — add it to the allowlist deliberately (the conscious "
                f"'winner or infra?' decision the gate exists to force)."
            )

    # ── W9 GATE — keep-all winner WIRED; the §-1.3-violating DROP variant stays forbidden ────────────
    # I-deepfix-001 (#1344): W9 GRADUATED. The CONSOLIDATE-KEEP-ALL variant
    # (PG_CONTENT_DEDUP_CONSOLIDATE -> content_dedup_consolidate.consolidate_body_syndication) is now wired
    # on the run path (groups near-identical-BODY syndication into keep-all baskets — annotate, never drop)
    # and is force-ON + preflight-required above, so OFF already fails the required-flags loop. This gate's
    # REMAINING job is to forbid the SEPARATE §-1.3-VIOLATING DROP variant: ContentDeduplicator's
    # ``unique_items`` (PG_W9_CONTENT_DEDUP) sheds corroborators. If a future operator wires the DROP variant
    # it FAILS CLOSED — unless they sign the §-1.3 waiver PG_W9_DARK_ACK=1 (logged loudly). The keep-all
    # winner's BEHAVIORAL proof is the [content_dedup_consolidate] run-log canary + body_syndication manifest.
    _w9_keepall_on = os.getenv("PG_CONTENT_DEDUP_CONSOLIDATE", "1").strip().lower() in _ON_TOKENS
    _w9_drop_wired = os.getenv("PG_W9_CONTENT_DEDUP", "0").strip().lower() in _ON_TOKENS
    _w9_ack = os.getenv("PG_W9_DARK_ACK", "0").strip().lower() in _ON_TOKENS
    if _w9_drop_wired and not _w9_ack:
        raise RuntimeError(
            "benchmark preflight FAILED [W9]: PG_W9_CONTENT_DEDUP is wired (the ContentDeduplicator DROP "
            "variant) but the §-1.3 waiver PG_W9_DARK_ACK is not set — a hard-drop content-dedup stage sheds "
            f"corroborators and violates consolidate-keep-all. The keep-all winner "
            f"(PG_CONTENT_DEDUP_CONSOLIDATE) + {_W9_SUBSUMED_BY} already cover near-dup consolidation. "
            "Remove PG_W9_CONTENT_DEDUP, or sign PG_W9_DARK_ACK=1 to override."
        )
    _w9_status_msg = (
        "[preflight W9-GATE] W9 dedup=ContentDeduplicator WIRED via the consolidate-keep-all body-"
        f"syndication stage (PG_CONTENT_DEDUP_CONSOLIDATE={'on' if _w9_keepall_on else 'OFF'}); the §-1.3-"
        "violating DROP variant (PG_W9_CONTENT_DEDUP) stays forbidden. Behavioral proof = the "
        "[content_dedup_consolidate] run-log canary + body_syndication manifest telemetry."
    )
    if _w9_drop_wired and _w9_ack:
        _w9_status_msg = (
            "[preflight W9-GATE] PG_W9_CONTENT_DEDUP wired AND PG_W9_DARK_ACK=1 — the operator has signed the "
            "§-1.3 waiver to run the ContentDeduplicator DROP variant. Proceeding under explicit override "
            f"(the keep-all subsumption {_W9_SUBSUMED_BY} is bypassed)."
        )
    _wire_logger.warning(_w9_status_msg)
    print(_w9_status_msg)


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
    # Correction 8 (Codex+Fable gate): recognize ALL THREE enrichment heading forms — the flat title,
    # the per-facet prefix ("Corroborated Findings: <facet>"), and the residual ("Additional Corroborated
    # Findings"). Under the facet route the flat title never renders, so the prior flat-only check false-
    # alarmed. Import all three constants (read-only; faithfulness-neutral).
    from src.polaris_graph.generator.weighted_enrichment import (
        _ENRICHMENT_FACET_TITLE_PREFIX,
        _ENRICHMENT_RESIDUAL_TITLE,
        _ENRICHMENT_TITLE,
    )

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

    import re as _re

    # Correction 8: collect EVERY offset where an enrichment title (flat / facet-prefix / residual)
    # appears in the report body. The facet route renders one "Corroborated Findings: <facet>" heading
    # per facet plus a residual "Additional Corroborated Findings"; the legacy route renders the single
    # flat title. Recognizing all three stops the false alarm the flat-only check raised under the facet
    # route. (The facet prefix and the residual title are distinct substrings — neither is contained in
    # the other nor in the flat title — so no double-count matters for the presence/citation checks.)
    _enrichment_markers = (
        _ENRICHMENT_TITLE,
        _ENRICHMENT_RESIDUAL_TITLE,
        _ENRICHMENT_FACET_TITLE_PREFIX,
    )
    _marker_starts: list[int] = []
    for _marker in _enrichment_markers:
        _from = 0
        while True:
            _hit = body.find(_marker, _from)
            if _hit < 0:
                break
            _marker_starts.append(_hit)
            _from = _hit + len(_marker)

    if not _marker_starts:
        raise BreadthEnrichmentCanaryError(
            f"breadth-enrichment canary FAILED for run_dir={run_dir}: the released report.md does "
            f"NOT contain ANY weighted-enrichment section (none of '{_ENRICHMENT_TITLE}', "
            f"'{_ENRICHMENT_FACET_TITLE_PREFIX}<facet>', '{_ENRICHMENT_RESIDUAL_TITLE}'). The §-1.3 "
            "breadth funnel silently reasserted (the unbound-SUPPORTS basket was never surfaced). "
            "PG_BREADTH_ENRICHMENT_ENABLED is force-required for the benchmark; investigate the "
            f"[multi_section] I-arch-007 breadth log line for the empty-exit reason.{_degrade_hint}"
        )

    # For each enrichment heading occurrence, slice from the title to the NEXT markdown heading (or EOF)
    # so a downstream References/Bibliography `[N]` cannot satisfy the gate (Codex P1 choke-fix iter2);
    # UNION the section bodies and assert >=1 `[N]` citation marker across the union. FAIL CLOSED when
    # the enrichment renders heading-only (no in-section cite) — the silent breadth funnel.
    _union_bodies: list[str] = []
    for _start in _marker_starts:
        _rest = body[_start:]
        _next_heading = _re.search(r"(?m)^\s*#{1,6}\s", _rest)
        _union_bodies.append(_rest[: _next_heading.start()] if _next_heading else _rest)
    _section_body = "\n".join(_union_bodies)
    if not _re.search(r"\[\d+\]", _section_body):
        raise BreadthEnrichmentCanaryError(
            f"breadth-enrichment canary FAILED for run_dir={run_dir}: {len(_marker_starts)} weighted-"
            f"enrichment section(s) rendered (flat / facet / residual) but NO section body carries a "
            "citation marker (a heading-only enrichment; a trailing bibliography no longer counts) — no "
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
    # I-deepfix-001 (#1344) FIX 2 — PRE-SPEND WINNER-SLATE ASSERTION (pre-import, pre-spend). Fail CLOSED
    # HERE if the slate did not land a force-on / force-exact winner (esp. W2 PG_QGEN_FS_RESEARCHER) — the
    # drb_72 silent dark-winner class where the running process ran a NON-WINNER config and the only marker
    # check was POST-run (after full spend). This is the EARLIEST tripwire: it runs BEFORE the heavy sweep
    # import below and long before preflight_full_capability at the token boundary. Env kill-switch
    # (PG_WINNER_SLATE_PRESPEND_ASSERT) default-ON; faithfulness-neutral (reads env + slate constants only).
    assert_full_capability_slate_applied(smoke_scale=smoke_scale)
    # I-deepfix-001 (#1344) DRB-II COVERAGE LEVERS — PRE-SPEND assertion (pre-import, pre-spend). Fail CLOSED
    # HERE if any of the 8 weight-and-consolidate breadth levers (facet outline / route-all-baskets / evidence
    # + word budget tracks payload / expert facet planner / facet completeness / qualifier elaboration / facet-
    # routed enrichment) did not land truthy — a coverage lever running DARK silently ships a NARROWER report.
    # The slate force-ON-pins each; this is the earliest tripwire (before the heavy sweep import). Shares the
    # PG_WINNER_SLATE_PRESPEND_ASSERT kill-switch; faithfulness-neutral (reads env + slate constants only).
    assert_coverage_levers_armed()
    # I-deepfix-001 (#1344) wiring-gap iter-4 (Codex REVISE): the citation-snowball evidence deepener
    # FAIL-LOUD (LAW II) is NOT asserted here — it lives at the ONE chokepoint EVERY real paid entry flows
    # through, should_trigger_deepener() in deepener_sweep_adapter.py. This function reaches it via
    # run_one_query (run_honest_sweep_r3.py:10492), so a keyless deepener-on run — CLI main(), the direct
    # real-spend replay entry (iwire002_backhalf_replay_preflight.py), OR the run_honest_sweep_r3
    # main_async/main path that bypasses run_gate_b entirely — all fail loud at that single guard. A local
    # assertion here would NOT cover the bypass path and would only duplicate the chokepoint, so it is
    # removed (Codex: prefer the single chokepoint). Hermetic seam/flag tests inject a fake transport and
    # mock run_one_query, so they never reach the predicate and need no key.

    # OFFICIAL-QUESTION OVERRIDE (wrong-question fix). ``run_gate_b`` bypasses
    # ``run_honest_sweep_r3.main_async``, where the GATE0 canonical override
    # (run_honest_sweep_r3.py:19099) rewrites each benchmark ``q["question"]`` to the CANONICAL
    # gold-file question by idx. So a benchmark launched HERE runs on the raw ``SWEEP_QUERIES``
    # prompt — for ``drb_72_ai_labor`` that is the I-safety-002b FIR/safety prompt (a different
    # program shares the slug), NOT the official DRB-II idx-56 GenAI question. When
    # ``PG_BENCHMARK_OFFICIAL_QUESTION`` is truthy, replace ``q["question"]`` with the canonical
    # question (by gold-file idx, via gate0_lineage) BEFORE ``run_one_query`` runs, so protocol.json
    # ``research_question``, retrieval, generation, and the report title all use the official idx
    # question. Copies the dict so the shared ``SWEEP_QUERIES`` entry is never mutated (the loader
    # returns the live registry dict). Default OFF => byte-identical (the safety program keeps its
    # locked prompt). FAITHFULNESS-NEUTRAL: only the INPUT question text changes; no verify/gate/NLI
    # rule is touched. Import + gold-file read are lazy + gated so the module's NO-SPEND-at-import
    # invariant and off-path (no third_party gold file) both hold.
    # I-deepfix-001 loss-risk FIX-2 (C2 wrong-question render): FORCE the official-question binding ON for
    # the benchmark run. Default OFF => the run generates against the raw SWEEP_QUERIES prompt (for drb_72
    # the I-safety-002b FIR/"English-language journal articles only" prompt, NOT the canonical DRB-II
    # idx-56 GenAI-labor question) => the split-brain that zeroed info_recall (0/57). Set BEFORE the
    # override below (which reads it) AND before preflight_full_capability (which fail-closes on it via
    # _BENCHMARK_PREFLIGHT_REQUIRED_FLAGS). UNCONDITIONAL so the pre-spend required-flag check passes on
    # BOTH the live and the offline seam-test path; the gold-file READ below is gated on the LIVE path
    # (transport is None) so an offline test (fake transport, mocked run_one_query, no third_party gold
    # file) never reads it. FAITHFULNESS-NEUTRAL (input question text only). setdefault is WRONG here — a
    # stray operator/.env =0 must NOT survive (that is the exact wrong-question hole this fix closes).
    os.environ["PG_BENCHMARK_OFFICIAL_QUESTION"] = "1"
    if _benchmark_official_question_enabled() and transport is None:
        _official_slug = q.get("slug")
        from scripts.dr_benchmark.gate0_lineage import (
            DRB_SLUGS_WITHOUT_CANONICAL_GOLD as _GATE0_NO_GOLD,
            SLUG_TO_IDX as _GATE0_SLUG_TO_IDX,
            canonical_question_for_slug as _gate0_canonical_q,
            is_benchmark_slug as _gate0_is_benchmark_slug,
            sha256_text as _gate0_sha,
        )
        if _official_slug in _GATE0_SLUG_TO_IDX:
            _official_question = _gate0_canonical_q(_official_slug)
            if _gate0_sha(q.get("question", "")) != _gate0_sha(_official_question):
                print(
                    f"[OFFICIAL-QUESTION] slug {_official_slug}: launched question OVERRIDDEN with "
                    f"canonical DRB-II idx {_GATE0_SLUG_TO_IDX[_official_slug]} (was the locked program "
                    f"prompt); protocol.json + retrieval + generation now use the official question."
                )
            q = {**q, "question": _official_question}
        elif _official_slug in _GATE0_NO_GOLD or not _gate0_is_benchmark_slug(_official_slug):
            # DOCUMENTED no-op (never a silent gap): a no-gold benchmark slug (drb_90) or a non-benchmark
            # slug has NO canonical DRB-II question to bind to => keep the launched prompt. Now that the
            # official-question binding is DEFAULT-ON for every benchmark run (FIX-2 above), a no-gold slug
            # must skip gracefully, not the prior hard ValueError (which assumed explicit opt-in intent).
            print(
                f"[OFFICIAL-QUESTION] slug {_official_slug}: no canonical DRB-II gold binding "
                f"(no-gold / non-benchmark) => launched prompt kept (documented no-op)."
            )
        else:
            # FAIL LOUD (LAW II): an UNREGISTERED benchmark slug (a future drb_NN neither gold-bound in
            # SLUG_TO_IDX nor listed in DRB_SLUGS_WITHOUT_CANONICAL_GOLD) — never silently run an unbound
            # benchmark prompt (the drb_72 wrong-question failure class).
            raise ValueError(
                f"PG_BENCHMARK_OFFICIAL_QUESTION set but benchmark slug {_official_slug!r} is "
                f"UNREGISTERED in gate0_lineage (neither SLUG_TO_IDX nor DRB_SLUGS_WITHOUT_CANONICAL_"
                f"GOLD) — cannot resolve the official question (would silently run the wrong prompt). "
                f"Register the slug's gold idx or list it no-gold."
            )

    from scripts.run_honest_sweep_r3 import run_one_query

    enable_four_role_mode()
    # FIX 1 (I-deepfix-001 Codex gate P0, WS-1 judge cache run-scope): RESET the process-wide judge verdict
    # idempotency cache at the START of THIS document's 4-role evaluation. The cache
    # (judge_adapter._JUDGE_VERDICT_CACHE) keys a CLEAN parsed verdict on (normalized_claim, span-identity)
    # to byte-twin-dedup WITHIN ONE report's 4-role pass. It is process-wide and, pre-fix, never cleared —
    # so in the sequential multi-query sweep (main() runs each run_gate_b_query in the SAME process) a
    # document-1 verdict could leak into document-2 and short-circuit a fresh judge call for a same-text
    # claim/span, or be inherited on the degrade path. run_gate_b_query processes exactly ONE report, so its
    # top is the per-document boundary: reset here, ONCE, BEFORE run_one_query runs this report's claims, so
    # within-document twins still share the verdict but no verdict crosses a document boundary. Gated on the
    # SAME default-ON PG_JUDGE_VERDICT_IDEMPOTENCY kill-switch that arms the cache (OFF => cache never
    # populated => no-op, and not called => byte-identical). FAITHFULNESS-NEUTRAL: clears a transport-dedup
    # cache only; parse_judge_verdict + _compose_final_verdict (how a verdict is DECIDED) are UNTOUCHED.
    if _judge_verdict_idempotency_enabled():
        reset_judge_verdict_cache()
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
    # I-deepfix-001 (#1344) PURITY: agentic URL-DISCOVERY is STORM's twin LOSER (code-confirmed) — KILLED.
    # Programmatically force it OFF here (was "1") so a stray operator/.env =1 cannot re-arm the live
    # agentic-search consumer (which also seeds from the legacy decompose output, run_honest_sweep_r3.py
    # @8743). Removed from REQUIRED_FLAGS + added to REQUIRED_OFF so the preflight fails closed if re-armed.
    os.environ["PG_AGENTIC_SEARCH_IN_BENCHMARK"] = "0"     # force-OFF (I-deepfix-001 purity: loser killed)
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
    # I-deepfix-001 winners — force-on so every fix FIRES on the paid run (the recurring
    # "committed-but-switched-off" failure). Entry-scoped (per-query, before run_one_query), read at
    # CALL time by each module's *_enabled() helper, so this lands without an import-time freeze.
    # FAITHFULNESS-NEUTRAL: WEIGHT / CONSOLIDATE / DISCLOSE / one-legit-hard-DROP seams only; the
    # faithfulness engine (strict_verify / NLI / 4-role D8 / provenance) is untouched. §-1.3 honored:
    # the ONLY hard-drop here is B2 (explicit operator-prohibited references). The two default-OFF
    # winners (B10 EXTRACT_USER_CONSTRAINTS, B14 TITLE_BODY_CONSISTENCY) MUST be set or they never
    # fire; the rest are default-ON, pinned so a stray operator/.env =0 cannot silently disable them.
    os.environ["PG_EXTRACT_USER_CONSTRAINTS"] = "1"               # B10: NL date/lang/journal constraint extract (default-OFF — MUST set)
    os.environ["PG_TITLE_BODY_CONSISTENCY"] = "1"                 # B14: title<->body identity gate, never drops (default-OFF — MUST set)
    os.environ["PG_BLOCKED_REFERENCE_DENYLIST"] = "1"            # B2: the ONE legit hard-drop (operator-prohibited refs); .env=0 must not win
    os.environ["PG_QUERY_DIRECTIVE_SCREEN"] = "1"                # B3: strip injected directive clauses from sub-queries
    os.environ["PG_CORROBORATION_SANITIZE"] = "1"               # B6a: chrome-header screen (keep-all sources/count)
    os.environ["PG_CLAIM_SHAPE_GATE"] = "1"                      # B6b/B8: skip malformed basket HEADER line only (never a source)
    os.environ["PG_CREDIBILITY_TIER_AUTHORITY_JOIN"] = "1"       # B9a: tier->authority prior so weight_mass != 0 (redesign master on)
    os.environ["PG_MIRROR_CITE_COLLAPSE"] = "1"                  # B9c: fold same-origin mirror citations (keeps all sources)
    os.environ["PG_CONSOLIDATION_NLI_PROSE"] = "1"              # B15: NLI prose consolidation (keep-all corroboration)
    os.environ["PG_FACT_DEDUP_PROSE"] = "1"                     # B15: Jaccard prose dedup (consolidate, never drop a claim)
    os.environ["PG_EPISTEMIC_MARKER_GUARD"] = "1"               # B16: drop a sentence rendering an assumption as a finding (additive)
    os.environ["PG_TEMPORAL_SCOPE_GUARD"] = "1"                 # B16: drop a sentence widening the cited horizon (additive)
    os.environ["PG_REPAIR_MARKER_PRUNE_ENABLED"] = "1"          # B17: fail-CLOSED unsupported-marker prune in sentence repair
    os.environ["PG_RENDER_GFM_TABLE_NORMALIZE"] = "1"           # B18: structural GFM table fixer (never drops/reorders cells)
    os.environ["PG_CONTRADICTION_SUPPRESS_METRIC_MISMATCH"] = "1"  # B18b: route metric-mismatch out of headline count (all sources disclosed)
    os.environ["PG_CONTRADICTION_SCOPE_MISMATCH_GUARD"] = "1"      # 13a: same-drug different time-window/population -> possible_metric_mismatch, not a hard contradiction (default-OFF — MUST set; both sides disclosed)
    os.environ["PG_REPORT_D8_BANNER"] = "1"                     # B8: top-of-report unadjudicated banner when 4-role D8 did not bind
    os.environ["PG_REPORT_FULL_DROP_DISCLOSURE"] = "1"          # B8: count ALL drop categories in the evidence-support disclosure
    # B11C1 PG_OPENROUTER_PROVIDER_SLO force-on REMOVED (#1344): it injected invalid OpenRouter
    # provider.min_throughput / .max_latency keys → 400 on the sentinel (super_heavy_preflight caught it
    # before spend). The whole C1 SLO-body injection is deleted in provider_routing.py; healthy-host
    # steering is served by the pinned order/ignore chain + B11 C2 measured-tok/s rotation.
    os.environ["PG_PERMIT_GENERATOR_EVALUATOR_SAME_FAMILY"] = "1"  # I-deepfix-001 Phase4: REQUIRED for the all-GLM-5.2 same-family run (else the two-family invariant aborts); B4 makes PT03/badge HONESTLY disclose non-segregation
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
    # I-deepfix-001 (#1344): offline=(transport injected) skips ONLY the WINNER-FIRES GPU-host probes
    # (W4/W5) — an offline/unit-test run has no GPU and spends no token, so a GPU assertion there is a
    # false-fail. The NO-LOSER / model-identity / SLATE-PURITY / W9 purity gates all stay unconditional.
    preflight_full_capability(smoke_scale=smoke_scale, offline=(transport is not None))
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
        finalize_timeout_run_and_maybe_write_error_manifest,
        run_wall_clock_seconds,
    )
    # I-deepfix-001 (Codex e2e gate P1): the paid Gate-B path must ALSO install the
    # multi_section_generator run-wall deadline (mirror run_honest_sweep_r3.py B20). Without it
    # the per-section wall-clock guard + disclosed gap-stub path is INACTIVE here, so a wedged
    # section consumes the run wall -> error_unexpected timeout / NO rendered report instead of a
    # disclosed gap-stub report. Faithfulness untouched (a gap-stub asserts no findings).
    from src.polaris_graph.generator.multi_section_generator import (
        set_run_wall_deadline as _msg_set_run_wall_deadline,
        reset_run_wall_deadline as _msg_reset_run_wall_deadline,
    )
    _wall = run_wall_clock_seconds()
    _run_dir = out_root / q["domain"] / q["slug"]
    _run_dir.mkdir(parents=True, exist_ok=True)
    _t0 = _time.time()
    _run_wall_deadline = _time.monotonic() + _wall
    _deadline_token = _RUN_WALL_CLOCK_DEADLINE_CTX.set(_run_wall_deadline)
    _msg_deadline_token = _msg_set_run_wall_deadline(_run_wall_deadline)
    try:
        try:
            _summary = await asyncio.wait_for(
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
        finally:
            # Reset the generator run-wall deadline (paired with the set above) so it never leaks
            # into a subsequent query. Runs on BOTH the success return and the timeout path.
            try:
                _msg_reset_run_wall_deadline(_msg_deadline_token)
            except Exception:  # noqa: BLE001 — token reset is best-effort hygiene
                pass
        # I-deepfix-001 loss-risk FIX-2/FIX-3 — RENDER-TIME RUN-VALIDITY GATES. After the report is
        # rendered but BEFORE it is returned (and long before the downstream scoring judge spends), assert
        # the shipped report ANSWERS the bound question (no silent reformulation, FIX-2) and carries the
        # task's stated output CONTRACT (named sections + required summary table, FIX-3). A violation
        # RAISES RunValidityGateError (fail loud, do-not-ship) + writes a durable marker + flips the
        # manifest to abort_run_validity_gate, so a wrong-question / contract-broken report can never be
        # scored as a valid submission (the drb_72 info_recall-0 + presentation-1/5 loss class). Config-
        # driven per slug (config/benchmark/task_output_contracts.yaml); a slug with no contract, a non-
        # shipping status, or no rendered report.md is a documented NO-OP (offline seam tests that mock
        # run_one_query write no report => skip). FAITHFULNESS-NEUTRAL: reads the shipped report + the
        # bound question and decides ship / do-not-ship; touches no faithfulness gate. Kill-switch
        # PG_RUN_VALIDITY_GATE (default ON — fail-closed armed for benchmark runs).
        from scripts.dr_benchmark.run_validity_gate import enforce_render_validity
        enforce_render_validity(_summary, q, _run_dir)
        return _summary
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
        # WALLCLOCK-GUARD (I-deepfix-001 ordering fix): one shared seam captures the PRESERVE
        # decision BEFORE the finalizer writes its backstop report.md, then finalizes and (only
        # for a genuine no-report hang) stamps the labeled error manifest. See the helper docstring.
        finalize_timeout_run_and_maybe_write_error_manifest(
            _run_dir, _timeout_summary, q, wall_clock_seconds=_wall,
        )
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
            "I-arch-007 SMOKE: small-scale FAST run (~25-35 min) for PLUMBING validation. After the "
            "full-capability floor slate, FORCE-SET (bypassing the ~1000-URL floor) the retrieval "
            "BREADTH knobs small (~45 URLs total) + a coherent short timeout hierarchy so a HANG is "
            "known in ~40 min, not 6h. INPUT-breadth + backstops ONLY — the faithfulness engine, the "
            "A20 consolidate funnel, and the 4-role D8 seam are UNCHANGED. Default OFF = full run "
            "byte-identical. Use to catch report-build/release/funnel/token-starvation bugs fast "
            "BEFORE the full-scale beat-both run."
        ),
    )
    parser.add_argument(
        "--official-question", action="store_true", default=False,
        help=(
            "Wrong-question fix: run the OFFICIAL DeepResearch-Bench-II question for each benchmark "
            "slug (resolved by gold-file idx via gate0_lineage) instead of the SWEEP_QUERIES prompt. "
            "The benchmark path bypasses run_honest_sweep_r3.main_async's GATE0 canonical override, so "
            "drb_72_ai_labor otherwise generates on the I-safety-002b FIR prompt (a different program "
            "shares the slug). Sets PG_BENCHMARK_OFFICIAL_QUESTION=1. Default OFF = byte-identical "
            "(the safety program keeps its locked prompt). Faithfulness-neutral (input question only). "
            "Requires the third_party gold file present (fails loud otherwise)."
        ),
    )
    args = parser.parse_args(argv)

    # --official-question is operator sugar for the PG_BENCHMARK_OFFICIAL_QUESTION env override that
    # run_gate_b_query reads at call time (single override implementation). Set it BEFORE the per-query
    # loop so both --only and --all pick it up; a pre-existing env value already truthy also stands.
    if args.official_question:
        os.environ["PG_BENCHMARK_OFFICIAL_QUESTION"] = "1"

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
    # I-deepfix-001 (#1344) wiring-gap iter-4 (Codex REVISE): the citation-snowball evidence deepener
    # FAIL-LOUD (LAW II) is NOT asserted here. It lives at the ONE chokepoint EVERY real paid entry flows
    # through — should_trigger_deepener() in src/polaris_graph/retrieval/deepener_sweep_adapter.py — which
    # main() reaches via run_gate_b_query -> run_one_query. That single guard also covers the
    # run_honest_sweep_r3 main_async/main path that bypasses run_gate_b entirely (a main()-local assert here
    # would NOT), so the local assertions in main() + run_gate_b_query are removed (Codex: prefer the single
    # chokepoint, no duplication). A keyless deepener-on paid run still fails loud — at the predicate, before
    # the snowball spends. FAITHFULNESS-NEUTRAL: no faithfulness logic.
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
        #
        # FIX 3 (I-deepfix-001 Codex gate P1, M6 firing-canary wiring): attach the in-process capture
        # handler to the cross_source_synthesis module logger BEFORE the run, so THIS document's M6 fire /
        # silent-no-op markers are captured (they stream to stdout via the module logger, NOT to
        # run_dir/run_log.txt). Detached in the `finally` below so it never leaks into the next query.
        # Default-ON kill-switch PG_M6_FIRING_CANARY; OFF => no handler, no canary call (byte-identical).
        _m6_log_lines: list[str] = []
        _m6_handler = None
        _m6_logger = logging.getLogger(_CROSS_SOURCE_SYNTHESIS_LOGGER)
        if _m6_firing_canary_enabled():
            _m6_handler = _CrossSourceMarkerCaptureHandler(_m6_log_lines)
            _m6_logger.addHandler(_m6_handler)
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
            # FIX 3: POST-RUN M6 firing canary — mirror the breadth-canary pattern (unconditional call;
            # self-skips on non-released/smoke, and on PG_CROSS_SOURCE_SYNTHESIS off inside the assert;
            # sets overall_rc=1 on a GENUINE M6 silent-no-op). Reads the markers captured for THIS query.
            _m6_canary = None
            if _m6_handler is not None:
                _m6_canary = _run_m6_firing_canary(
                    _m6_log_lines, status,
                    smoke_scale=args.smoke_scale, domain=domain, slug=slug,
                )
                if _m6_canary == "FAILED":
                    overall_rc = 1
            _sweep_records.append({
                "query_index": query_index,
                "slug": slug,
                "domain": domain,
                "status": status,
                "ok": _status_ok and _breadth_canary != "FAILED" and _m6_canary != "FAILED",
                "breadth_enrichment_canary": _breadth_canary,
                "m6_cross_source_canary": _m6_canary,
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
        finally:
            # FIX 3: detach the M6 capture handler on EVERY exit path (success, crash, or _abort re-raise)
            # so it never leaks into the next query's capture (sequential sweep, §8.4).
            if _m6_handler is not None:
                _m6_logger.removeHandler(_m6_handler)
        _persist_sweep_summary()
    return overall_rc


if __name__ == "__main__":
    import sys

    # I-wire-011 iter-4 (Codex iter-3 P1) BELT-AND-SUSPENDERS: arm the PG_TEARDOWN_WALL watchdog on the
    # PAID Gate-B entrypoint too. The watchdog was previously armed ONLY by run_honest_sweep.main(); this
    # CLI reaches run_one_query via run_gate_b_query/asyncio.run and so never armed it, leaving the paid
    # path exposed to a NON-NLI lingering non-daemon pool (e.g. an orphaned 4-role seam claim executor)
    # wedging the interpreter at exit. Mirror run_honest_sweep.main() EXACTLY: arm in a finally so a
    # wedged pool can hang the interpreter on either the success or the exception path; default-safe
    # (PG_TEARDOWN_WALL=0 => true no-op). The NLI worker's own exit-safety is the daemon thread in
    # run_honest_sweep_r3._nli_annotation_with_wall; this is an independent backstop for other pools.
    from scripts.run_honest_sweep_r3 import _run_process_teardown

    _rc = 1
    try:
        _rc = main()
    finally:
        _run_process_teardown(_rc)
    sys.exit(_rc)
