"""OpenRouter `RoleTransport` for the 3 verifier roles at the BENCHMARK stage (I-meta-007d).

WHY THIS EXISTS (operator directive 2026-06-01, I-meta-007d): at the CURRENT dev/benchmark
stage all 4 roles run on OpenRouter with MAX reasoning so the head-to-head can run WITHOUT
standing up the self-hosted vLLM GPU fleet (saves the Vast.ai GPU rental cost). The GENERATOR
already runs live on OpenRouter (`PG_GENERATOR_MODEL` via the async `openrouter_client.py`).
This transport routes the three VERIFIER roles (Mirror / Sentinel / Judge) THROUGH the SAME
OpenRouter gateway, each pinned to its BENCHMARK-STAGE OpenRouter slug (see
`BENCHMARK_VERIFIER_LINEUP` below — NOT the lock's self-host slugs), with reasoning enabled at
the MAX effort "xhigh".

BENCHMARK-STAGE LINEUP vs SOVEREIGN LOCK (P1-1, I-meta-007d diff-gate iter-1): the runtime lock
(config/architecture/polaris_runtime_lock.yaml) pins the SOVEREIGN self-host slugs for the
verifier roles — Mirror `cohere/command-a-plus`, Sentinel
`ibm-granite/granite-guardian-4.1-8b`. Those are NOT on OpenRouter (Cohere is not on OpenRouter
at all; only the GENERAL `ibm-granite/granite-4.1-8b` is, not the Guardian variant). At the
benchmark stage the operator re-picked the OpenRouter-available alternatives, Codex-gated in
`outputs/I-meta-002/role_selection_final.md` (2026-05-31): Mirror -> `z-ai/glm-5.1`
(family z-ai), Sentinel -> the general `ibm-granite/granite-4.1-8b` (family ibm-granite).
Writer (`deepseek/deepseek-v4-pro`) and Judge (`qwen/qwen3.6-35b-a3b`) are IDENTICAL in the lock
and the benchmark lineup. So at the benchmark stage this transport resolves each verifier role's
slug from `BENCHMARK_VERIFIER_LINEUP` (the env-overridable lineup below), NOT from the lock's
`_lock_model_slug`.

SENTINEL BENCHMARK-vs-SOVEREIGN TRADEOFF (honest, per the Codex gate on
role_selection_final.md): the general `ibm-granite/granite-4.1-8b` is NOT the purpose-built
faithfulness detector — the self-host Sentinel is the task-trained
`granite-GUARDIAN-4.1-8b`. The Guardian's edge over a general open model on the SAME
LLM-AggreFact RAGTruth benchmark is a SMALL single-digit margin (~1.5-2.3 BAcc pts;
Guardian-4.1-think 0.841 vs Qwen2.5-72B 81.9 / Llama-3.3-70B 82.6) — `sentinel_gap_honest =
FALSE`; the prior "+6.5-11 BAcc" figure was OVERSTATED / mixed-baseline. The Guardian gap is
larger on raw RAGTruth response-level F1, but the same-benchmark edge is single-digit. The
self-host Guardian is the SOVEREIGN-stage Sentinel for specialist/operational reasons (task-
trained 8B, simpler ops, and the ~82 general models either collide with the Judge's Qwen family
or are not on OpenRouter), NOT a proven double-digit win. This general-granite-vs-Guardian delta
is the documented benchmark-vs-sovereign tradeoff (the benchmark uses the OpenRouter-available
general model; the sovereign destination uses the self-host Guardian).

SOVEREIGNTY (binding, do NOT silently drop): OpenRouter is a US router. Routing the verifier
roles through it is acceptable for the DEV/BENCHMARK stage ONLY. It is NOT acceptable for the
sovereign demo (`feedback_sovereignty_threat_model`: no runtime US LLM-vendor calls, no data in
US jurisdiction). The FINAL sovereign destination remains self-hosting the LOCK's self-host
slugs (cohere Mirror, granite-GUARDIAN Sentinel) per the lock's
`serving_route: vast_self_host*` (config/architecture/polaris_runtime_lock.yaml), served by
`OpenAICompatibleRoleTransport`. This transport does NOT mutate the lock — the lock still pins
the self-host slugs + `vast_self_host*`; the routing choice AND the slug source are env-gated
(`PG_FOUR_ROLE_TRANSPORT`, see run_gate_b.py) and the lock's sovereign destination is unchanged.

SHAPE REUSE (no duplication): OpenRouter's `/chat/completions` is the SAME OpenAI-compatible
response shape as the self-host vLLM `/v1/chat/completions`, so this transport REUSES the
already-tested helpers from `openai_compatible_transport` for everything on the RESPONSE side —
message normalization (`_normalize_messages`: documents / Mirror pass-2 content_hash / pass-1
<co> instruction rendered model-visible), body assembly (`_build_body`: explicit passthrough
allowlist, no POLARIS-internal-key leak), reasoning-vs-verdict separation (`_separate_reasoning`:
the `reasoning_content` field OR a leading inline `<think>` block split off the bare verdict),
the Mirror `<co>` raw-text-as-is invariant, and Path-B capture sanitization
(`_sanitize_raw_for_capture`). The genuinely-new bits here are the OpenRouter-specific ones:
the base URL, the Bearer-`OPENROUTER_API_KEY` auth, the reasoning REQUEST param
(`{"enabled": True, "effort": "xhigh"}` — `xhigh` is OpenRouter's documented MAXIMUM effort),
the served-identity stash (`{provider, model, system_fingerprint}` — OpenRouter reports a
`provider`, unlike a self-host vLLM whose identity is its endpoint), the benchmark-lineup slug
resolution (P1-1), the `message.reasoning` extraction (P1-3, see below), and the
top-level-`documents` drop (P1-4, see `_build_openrouter_body`).

P1-3 (message.reasoning): OpenRouter returns the verifier's reasoning in
`response.choices[0].message.reasoning` (NOT `reasoning_content` and NOT an inline `<think>`
block) — see https://openrouter.ai/docs/guides/best-practices/reasoning-tokens. The reused
`_parse_response` reads only `reasoning_content` / `<think>`, so it would LOSE the OpenRouter
reasoning. This transport therefore uses its OWN `_parse_openrouter_response` which adds the
`message.reasoning` field to the reasoning-extraction precedence
(`reasoning_content` -> `message.reasoning` -> leading inline `<think>`). The reasoning is
surfaced to `RoleResponse.reasoning` (kept SEPARATE from `raw_text`) AND stripped OUT of the
Path-B capture channel (`_sanitize_raw_for_capture` now also pops `reasoning`), so verifier
reasoning is never lost from `four_role_role_calls.jsonl` and never leaks into capture.

Reasoning vs output MUST stay separate (I-meta-002-q1b): `RoleResponse.reasoning` carries the
verifier's chain-of-thought; `RoleResponse.raw_text` carries ONLY the bare verdict/body the
verdict parsers consume. This is enforced by `_parse_openrouter_response` (which reuses
`_separate_reasoning` + the post-split blank guard).

No-spend / no-network-in-tests boundary: the `httpx.Client` is DEPENDENCY-INJECTED via the
constructor (same pattern as `OpenAICompatibleRoleTransport`). Tests pass
`httpx.Client(transport=httpx.MockTransport(...))` so there is NO socket in any pytest path.

Fail loud (LAW II): a missing `OPENROUTER_API_KEY`, a non-resolving role slug, a non-200 HTTP
status, or a malformed body raises (never a silent empty `RoleResponse`).
"""

from __future__ import annotations

import json
import logging
import os

import httpx

from src.polaris_graph.benchmark import pathB_capture as _pathb_capture
from src.polaris_graph.roles.openai_compatible_transport import (
    BlankVerdictError,
    RoleTransportError,
    _build_body,
    _normalize_messages,
    _separate_reasoning,
    _sanitize_raw_for_capture,
)
from src.polaris_graph.roles.provider_routing import (
    apply_provider_routing,
    role_provider_routing,
    slug_for_provider,
)
from src.polaris_graph.roles.role_transport import RoleRequest, RoleResponse

logger = logging.getLogger(__name__)

# The OpenAI-compatible chat-completions path. OpenRouter's base URL already ends in `/api/v1`
# (OPENROUTER_BASE_URL default `https://openrouter.ai/api/v1`), so we append ONLY
# `/chat/completions` here — NOT the self-host `/v1/chat/completions` constant, which would
# double the `/v1` segment against the OpenRouter base.
_CHAT_COMPLETIONS_PATH = "/chat/completions"

# Roles this transport serves at the benchmark stage. The generator is excluded — it already
# runs on OpenRouter via the async openrouter_client, upstream of the per-claim verifier path.
_SERVED_ROLES = ("mirror", "sentinel", "judge")
_EXCLUDED_ROLE = "generator"

# === BENCHMARK-STAGE OpenRouter verifier lineup (P1-1, I-meta-007d diff-gate iter-1) =========
# The operator-chosen OpenRouter slugs from outputs/I-meta-002/role_selection_final.md
# (Codex-gated 2026-05-31), which DIFFER from the lock's SOVEREIGN self-host slugs for two of
# the three verifier roles:
#   - Mirror   `z-ai/glm-5.1`               (family z-ai)        — lock pins cohere/command-a-plus
#                                                                   (Cohere is NOT on OpenRouter);
#                                                                   GLM-5.1 is the operator re-pick.
#   - Sentinel `ibm-granite/granite-4.1-8b` (family ibm-granite) — lock pins the self-host
#                                                                   granite-GUARDIAN-4.1-8b (NOT on
#                                                                   OpenRouter); the GENERAL
#                                                                   granite-4.1-8b IS on OpenRouter
#                                                                   and is the benchmark alternative
#                                                                   (the Guardian is the SOVEREIGN
#                                                                   Sentinel — see module docstring's
#                                                                   benchmark-vs-sovereign tradeoff).
#   - Judge    `qwen/qwen3.6-35b-a3b`       (family qwen)        — IDENTICAL to the lock.
# Writer/generator (`deepseek/deepseek-v4-pro`, family deepseek) is also IDENTICAL to the lock;
# it runs upstream on OpenRouter via openrouter_client and is not served by THIS transport, but
# its family is needed by the 4-distinct-family check (resolved from the lock by run_gate_b.py).
# Families across the active benchmark lineup: deepseek / z-ai / ibm-granite / qwen = 4 distinct.
#
# LAW VI (zero hard-coding): each verifier role's benchmark slug is env-overridable via the
# lock's per-role env_vars (`PG_MIRROR_MODEL` / `PG_SENTINEL_MODEL` / `PG_JUDGE_MODEL`),
# DEFAULTING to the role_selection_final slug. Read lazily (per-call) so an override set after
# import is honored and import never depends on env presence.
_BENCHMARK_LINEUP_ENV = {
    "mirror": "PG_MIRROR_MODEL",
    "sentinel": "PG_SENTINEL_MODEL",
    "judge": "PG_JUDGE_MODEL",
}
_BENCHMARK_LINEUP_DEFAULT_SLUG = {
    "mirror": "z-ai/glm-5.1",
    # I-run11-004: benchmark Sentinel is the CERTIFIED MiniMax-M2 decomposition detector
    # (replaces the general ibm-granite/granite-4.1-8b, which mislabeled grounded claims). The
    # benchmark default mode for the Sentinel is "decomposition" (see sentinel_adapter).
    "sentinel": "minimax/minimax-m2",
    "judge": "qwen/qwen3.6-35b-a3b",
}
# Expected DEFAULT family lane per benchmark verifier role (the lane each role's
# role_selection_final slug belongs to). This is the EXPECTED value, not the asserted one —
# `benchmark_verifier_family` derives the ACTIVE family from the ACTIVE slug (so a
# `PG_<ROLE>_MODEL` override is reflected, not assumed) and FAILS LOUD when an override's family
# leaves this lane. Without that, an override like `PG_JUDGE_MODEL=z-ai/glm-5.1` would serve the
# Judge and Mirror as the SAME family while a static map still read "qwen" and the
# 4-distinct-family check passed — a clinical-lethal self-verify collision (CLAUDE.md §9.1)
# slipping past the gate. The family is the slug's provider prefix (`provider/model`): for all
# four lineup members `slug.split("/")[0]` IS the family (z-ai / ibm-granite / qwen / deepseek).
_BENCHMARK_VERIFIER_DEFAULT_FAMILY = {
    "mirror": "z-ai",
    # I-run11-004: MiniMax-M2 Sentinel — its `provider/` prefix `minimax` IS the family lane.
    "sentinel": "minimax",
    "judge": "qwen",
}


def _family_from_slug(slug: str) -> str:
    """The family lineage of an OpenRouter slug = its `provider/` prefix (fail loud if absent).

    Every OpenRouter slug is `provider/model`; the provider prefix IS the family lineage the
    4-distinct-family invariant is asserted over (z-ai / ibm-granite / qwen / deepseek). A slug
    with no `/` cannot have its family determined — raise rather than guess (LAW II fail-loud).
    """
    provider, sep, _ = slug.partition("/")
    if not sep or not provider:
        raise ValueError(
            f"benchmark verifier slug {slug!r} is not a `provider/model` OpenRouter slug; its "
            "family lineage cannot be determined (fail-closed — the 4-distinct-family invariant "
            "must assert on a real family)."
        )
    return provider


def benchmark_verifier_slug(role: str) -> str:
    """Resolve a verifier role's BENCHMARK-STAGE OpenRouter slug (P1-1, LAW VI).

    Sources `PG_<ROLE>_MODEL` (the lock's per-role `env_vars.primary`), DEFAULTING to the
    operator-chosen role_selection_final.md OpenRouter slug. This is the benchmark lineup —
    DISTINCT from the lock's self-host `_lock_model_slug` for Mirror + Sentinel (see module
    docstring). The generator/unknown role raises (it is not served by this transport).
    """
    if role == _EXCLUDED_ROLE:
        raise ValueError(
            f"role {role!r} is not served by this transport — the generator runs on OpenRouter "
            "via openrouter_client.py, upstream of the per-claim verifier path."
        )
    if role not in _SERVED_ROLES:
        raise ValueError(
            f"role {role!r} is not a benchmark-stage verifier role {_SERVED_ROLES}"
        )
    return os.getenv(_BENCHMARK_LINEUP_ENV[role], _BENCHMARK_LINEUP_DEFAULT_SLUG[role])


def benchmark_verifier_lineup() -> dict[str, str]:
    """Return the active `{mirror,sentinel,judge: benchmark_slug}` map (P1-1, LAW VI).

    The SINGLE source of truth for the benchmark-stage verifier slugs, consumed by BOTH the
    transport's `openrouter_role_endpoint` (the slug it POSTs as `body["model"]`) AND
    run_gate_b.py's `verifier_model_slugs` (the slug it pins into `RoleRequest.model_slug`), so
    served (the slug sent) == pinned (the slug in the request/gate) on the OpenRouter path.
    """
    return {role: benchmark_verifier_slug(role) for role in _SERVED_ROLES}


def benchmark_verifier_family(role: str) -> str:
    """Return the ACTIVE BENCHMARK-lineup family for a verifier `role` (the active-lineup family
    the 4-distinct-family check asserts on, NOT the lock's). The generator/unknown role raises.

    The family is derived from the ACTIVE slug (`benchmark_verifier_slug`, which honors the
    `PG_<ROLE>_MODEL` override) — NOT a static assumption. FAILS LOUD when an override's family
    leaves the role's expected default lane, so a cross-family re-pick (e.g.
    `PG_JUDGE_MODEL=z-ai/glm-5.1`, which would collide the Judge with the z-ai Mirror) is caught
    here rather than silently passing the 4-distinct-family gate on a stale static map
    (clinical-lethal self-verify, CLAUDE.md §9.1). An IN-LANE override (same provider prefix)
    passes.
    """
    if role == _EXCLUDED_ROLE:
        raise ValueError(
            f"role {role!r} is the generator — its family is sourced from the lock, not the "
            "benchmark verifier lineup."
        )
    if role not in _SERVED_ROLES:
        raise ValueError(
            f"role {role!r} is not a benchmark-stage verifier role {_SERVED_ROLES}"
        )
    active_family = _family_from_slug(benchmark_verifier_slug(role))
    expected_family = _BENCHMARK_VERIFIER_DEFAULT_FAMILY[role]
    if active_family != expected_family:
        raise ValueError(
            f"benchmark verifier role {role!r}: active slug family {active_family!r} (from "
            f"{_BENCHMARK_LINEUP_ENV[role]}={benchmark_verifier_slug(role)!r}) leaves the "
            f"expected lane {expected_family!r}. A cross-family re-pick risks a self-verify "
            f"collision with another role (CLAUDE.md §9.1, all_distinct); fix the override or "
            f"update the lineup default (fail-closed)."
        )
    return active_family


# === STAGE annotation (P2, I-meta-007d diff-gate iter-1) =====================================
# A machine-readable stage marker so a future gate/manifest reader can never mistake an
# OpenRouter BENCHMARK run for the sovereign self-host serving path (the lock's
# serving_route: vast_self_host*). Surfaced in the four-role manifest stage block by the caller.
FOUR_ROLE_STAGE = "benchmark_openrouter"

# Reasoning REQUEST param for MAX reasoning (operator directive: MAX reasoning at the benchmark
# stage). Mirrors openrouter_client._call_impl's `reasoning_enabled` branch
# (openrouter_client.py:1424): `{"effort": reasoning_effort, "enabled": True}`. OpenRouter's
# constraint is that `effort` and `max_tokens` are mutually exclusive; "xhigh" is OpenRouter's
# documented MAXIMUM reasoning effort (P1-2, I-meta-007d diff-gate iter-1 — "high" is a LOWER
# allocation, so the prior "high" default silently DOWNGRADED the operator's MAX-reasoning
# directive). Source: https://openrouter.ai/docs/guides/best-practices/reasoning-tokens .
# LAW VI: effort is overridable via PG_FOUR_ROLE_REASONING_EFFORT (default "xhigh" = MAX).
_REASONING_EFFORT = os.getenv("PG_FOUR_ROLE_REASONING_EFFORT", "xhigh")

# I-run11-004: hard floor on the decomposition Sentinel's top-level max_tokens. The certified
# MiniMax-M2 call used reasoning + max_tokens>=3000; anything below that truncates the JSON
# {verdict, atoms} mid-emission (the run-12 truncator) and collapses every claim to a fail-closed
# UNGROUNDED. An env override (PG_SENTINEL_DECOMPOSITION_MAX_TOKENS) can RAISE but never lower past
# this floor.
_SENTINEL_DECOMPOSITION_MIN_MAX_TOKENS = 3000

# I-meta-008 / #1026: blank-verdict step-down ladder. When a reasoning-first verifier returns a
# BLANK bare verdict (reasoning budget exhausted without converging under the high effort), retry
# with the effort stepped DOWN this ladder so the model is forced to spend tokens on the VERDICT,
# not endless reasoning. The first entry is the configured MAX effort; `None` means reasoning
# DISABLED (final resort — guarantees content). Overridable via PG_FOUR_ROLE_EFFORT_LADDER
# (comma-separated; the literal "off"/"none" -> reasoning disabled). MAX-reasoning-first, then a
# guaranteed verdict, then fail-loud only if even reasoning-off blanks.
def _parse_effort_ladder() -> tuple[object, ...]:
    raw = os.getenv("PG_FOUR_ROLE_EFFORT_LADDER")
    if not raw:
        return (_REASONING_EFFORT, "low", None)
    out: list[object] = []
    for token in raw.split(","):
        t = token.strip()
        if not t:
            continue
        out.append(None if t.lower() in ("off", "none", "disabled") else t)
    return tuple(out) if out else (_REASONING_EFFORT, "low", None)


_VERIFIER_EFFORT_LADDER = _parse_effort_ladder()

# Per-role reasoning policy (Codex iter-2 P1 — reasoning is NOT a one-size-fits-all switch).
#
# WHY per-role: Mirror (`z-ai/glm-5.1`) and Judge (`qwen/qwen3.6-35b-a3b`) are DELIBERATIVE
# verifiers — they weigh evidence and argue a verdict, so they get MAX reasoning effort
# (`xhigh`) AND `provider.require_parameters=True` (only route to a provider that honors
# reasoning).
#
# Sentinel is MODE-AWARE (I-run11-004): the CERTIFIED MiniMax-M2 DECOMPOSITION Sentinel
# (`minimax/minimax-m2`, the benchmark + lock default) was certified WITH reasoning ON and
# max_tokens>=3000 — turning reasoning OFF (or starving max_tokens to the 256 classifier budget)
# truncates the JSON {verdict, atoms} mid-emission and collapses every claim to a fail-closed
# UNGROUNDED (the run-12 truncator). So when the active Sentinel groundedness mode is
# "decomposition", the Sentinel sends MAX reasoning + a GENEROUS max_tokens, exactly replicating
# the certified call. The SOVEREIGN `guardian`/`noninverted` granite Sentinel modes stay
# reasoning-OFF (a <score>/one-word classifier whose self-host slug does not advertise
# `reasoning`); their settings are NOT regressed. LAW VI: overridable via `PG_SENTINEL_REASONING`.
_ROLE_REASONING_DEFAULT = {"mirror": True, "sentinel": False, "judge": True}


def sentinel_decomposition_active(slug_override: str | None = None) -> bool:
    """True iff the ACTIVE Sentinel groundedness mode is "decomposition" (I-run11-004).

    Lazily resolves `sentinel_adapter.sentinel_groundedness_mode()` (env- + model-aware, LAW VI)
    so the transport can mode-gate the Sentinel's reasoning + max_tokens WITHOUT an import-time
    dependency on the adapter (the adapter does not import this transport — no cycle). Any
    resolution error is swallowed to the conservative non-decomposition answer (the certified
    MiniMax call is only requested when the mode UNAMBIGUOUSLY resolves to decomposition).

    `slug_override` (Codex diff-gate iter-4 P2) is the slug ACTUALLY being served on this call —
    threaded through from the request so the reasoning/max_tokens gate keys on the real served
    model, not a stale `PG_SENTINEL_MODEL` env, in any direct/future call path.
    """
    try:
        from src.polaris_graph.roles.sentinel_adapter import (
            _MODE_DECOMPOSITION,
            sentinel_groundedness_mode,
        )

        return sentinel_groundedness_mode(slug_override) == _MODE_DECOMPOSITION
    except Exception:  # noqa: BLE001 — conservative: unknown -> not decomposition.
        return False


def role_reasoning_enabled(role: str, slug_override: str | None = None) -> bool:
    """Whether the given verifier role should send the MAX-reasoning request params.

    Returns the per-role default from `_ROLE_REASONING_DEFAULT`, overridable per role via the
    env var `PG_<ROLE>_REASONING` (LAW VI): "1"/"true"/"yes" -> True, "0"/"false"/"no" -> False;
    absent (or any other value) falls back to the role default. Mirror/Judge default True
    (deliberative verifiers -> MAX reasoning). Sentinel is MODE-AWARE (I-run11-004): in
    "decomposition" mode (the certified MiniMax-M2 detector) it defaults True (reasoning ON, as
    certified); in the sovereign granite `guardian`/`noninverted` modes it defaults False (a
    classifier whose slug does not advertise `reasoning`, so reasoning would break routing).
    """
    if role == "sentinel" and os.getenv(f"PG_{role.upper()}_REASONING") is None:
        # No explicit override: the Sentinel default is mode-aware (decomposition -> reasoning ON),
        # keyed on the ACTUAL served slug when supplied (Codex diff-gate iter-4 P2).
        default = sentinel_decomposition_active(slug_override)
    else:
        default = _ROLE_REASONING_DEFAULT.get(role, False)
    override = os.getenv(f"PG_{role.upper()}_REASONING")
    if override is None:
        return default
    token = override.strip().lower()
    if token in ("1", "true", "yes"):
        return True
    if token in ("0", "false", "no"):
        return False
    return default


# Reuse the same timeout knob the self-host transport + openrouter_client use (LAW VI).
# I-meta-008 FULL-POWER: the reasoning verifiers (Mirror/Judge at effort=xhigh against a 16384-token
# budget) take MINUTES per claim — give them their OWN generous timeout (default 900s/15min), not the
# cheap 90s shared default (which also governs retrieval/embeddings). Env-overridable (LAW VI).
_TIMEOUT_SECONDS = int(os.getenv("PG_VERIFIER_LLM_TIMEOUT_SECONDS", "900"))

# LAW VI: base URL + key come from the SAME env vars openrouter_client reads (single source of
# truth). Read lazily (function-level) so import never depends on env presence.
_BASE_URL_ENV = "OPENROUTER_BASE_URL"
_BASE_URL_DEFAULT = "https://openrouter.ai/api/v1"
_API_KEY_ENV = "OPENROUTER_API_KEY"


def openrouter_base_url() -> str:
    """The OpenRouter API base URL (LAW VI: OPENROUTER_BASE_URL env, openrouter_client default).

    Trailing slash trimmed so `{base}{_CHAT_COMPLETIONS_PATH}` is well-formed. The default
    already ends in `/api/v1`.
    """
    return os.getenv(_BASE_URL_ENV, _BASE_URL_DEFAULT).rstrip("/")


def openrouter_api_key() -> str:
    """The OpenRouter API key (LAW VI: OPENROUTER_API_KEY env).

    Fails loud (LAW II) when unset: the benchmark-stage verifier path REQUIRES the OpenRouter
    key (this is the US-router dev/benchmark path — the self-host no-leak rule does NOT apply
    here; this IS the OpenRouter path).
    """
    key = os.getenv(_API_KEY_ENV, "")
    if not key:
        raise RoleTransportError(
            f"{_API_KEY_ENV} is not set; the benchmark-stage OpenRouter verifier transport "
            "requires it (LAW VI). Set it in .env, or select the self-host transport via "
            "PG_FOUR_ROLE_TRANSPORT=self_host."
        )
    return key


def openrouter_role_endpoint(role: str) -> tuple[str, str, str]:
    """Resolve `(base_url, api_key, model_slug)` for an OpenRouter-served verifier role.

    Sources the base URL + key from the OpenRouter env (LAW VI) and the `model_slug` from the
    BENCHMARK-STAGE lineup (`benchmark_verifier_slug`, P1-1) — the operator-chosen OpenRouter
    slugs in role_selection_final.md, NOT the lock's self-host `_lock_model_slug` (Cohere's
    Mirror + the granite-GUARDIAN Sentinel are not on OpenRouter; see module docstring). The
    SAME lineup feeds run_gate_b.py's `verifier_model_slugs`, so served (this slug, POSTed as
    `body["model"]`) == pinned (the slug in `RoleRequest.model_slug` / the Path-B gate pin) on
    the OpenRouter path. The generator is HARD-EXCLUDED (it runs on OpenRouter upstream of this
    transport); an unknown role raises.

    Fails loud (LAW II / LAW VI) on the excluded/unknown role or a missing OPENROUTER_API_KEY.
    """
    # `benchmark_verifier_slug` enforces the served-role guard (generator/unknown -> ValueError).
    return openrouter_base_url(), openrouter_api_key(), benchmark_verifier_slug(role)


# Top-level body key the self-host `_build_body` allowlist forwards but OpenRouter's
# chat-completions request schema does NOT define (P1-4). With provider.require_parameters=True
# OpenRouter only routes to a provider honoring ALL request params, so a top-level `documents`
# key would FAIL routing. The evidence is already rendered into the messages by
# `_normalize_messages` (both the prompt path and the Sentinel messages path), so dropping the
# top-level key is model-visibility-safe. Source: OpenRouter Chat Completions request schema +
# provider-selection docs (https://openrouter.ai/docs/api/reference/overview ,
# https://openrouter.ai/docs/guides/routing/provider-selection ).
_OPENROUTER_UNSUPPORTED_TOP_LEVEL_KEYS = ("documents",)


def _build_openrouter_body(request: RoleRequest, model_slug: str, normalized_messages: list[dict]) -> dict:
    """Assemble the OpenRouter request body: the SAME OpenAI-compatible body the self-host
    transport builds, MINUS the top-level `documents` key (P1-4), PLUS the MAX-reasoning param.

    Reuses `_build_body` for `model` + `messages` + the explicit passthrough allowlist
    (structured_outputs / response_format / documents / max_tokens — POLARIS-internal keys like
    pass2_input / citations / system never reach the body). Then (P1-4) DROPS the top-level
    `documents` key, which OpenRouter's chat-completions schema does not define and which would
    fail routing under `provider.require_parameters=True` — the evidence is already rendered into
    `messages` by `_normalize_messages`, so model-visibility is preserved. Then sets
    `reasoning = {"enabled": True, "effort": <_REASONING_EFFORT>}` — the openrouter_client
    `reasoning_enabled` shape (openrouter_client.py:1424). Per OpenRouter docs the mutually
    exclusive pair is `reasoning.effort` vs `reasoning.max_tokens`; the TOP-LEVEL `max_tokens` is
    NOT exclusive with effort and MUST exceed the reasoning budget. Under `effort=xhigh` the
    provider spends ~95% of top-level `max_tokens` on reasoning, so a popped/absent `max_tokens`
    starves the verdict. I-meta-008 FULL-POWER therefore SETS a generous top-level `max_tokens`
    (PG_VERIFIER_REASONING_MAX_TOKENS, default 16384) for the reasoning verifiers and an explicit
    small classifier budget (PG_SENTINEL_MAX_TOKENS, default 256) for the non-reasoning Sentinel.
    Source: https://openrouter.ai/docs/guides/best-practices/reasoning-tokens
    """
    body = _build_body(request, model_slug, normalized_messages)
    # P1-4: strip OpenRouter-unsupported top-level keys (currently `documents`). The evidence is
    # already model-visible in `messages` (rendered by `_normalize_messages`), so the model still
    # sees it; this only removes the schema-invalid body key that breaks require_parameters routing.
    for key in _OPENROUTER_UNSUPPORTED_TOP_LEVEL_KEYS:
        body.pop(key, None)
    # Codex iter-2 P1: reasoning is PER-ROLE. Only the deliberative verifiers (Mirror/Judge) get
    # MAX reasoning + `provider.require_parameters=True`. The Sentinel classifier gets NEITHER —
    # its OpenRouter slug does not advertise `reasoning`, so `require_parameters=True` would refuse
    # to route and fail the first call. See `role_reasoning_enabled` for the full rationale.
    if role_reasoning_enabled(request.role, request.model_slug):
        body["reasoning"] = {"enabled": True, "effort": _REASONING_EFFORT}
        # require_parameters=True makes OpenRouter ONLY route to a provider that actually HONORS the
        # `reasoning` param (OpenRouter's default when absent is False — it could otherwise route a
        # verifier to a provider that silently IGNORES reasoning, defeating the operator's
        # MAX-reasoning purpose). Mirrors openrouter_client._call_impl's provider block
        # (openrouter_client.py:1484-1487, OPENROUTER_REQUIRE_PARAMETERS default "true"). The
        # I-bug-946 singleton-routing half (resolved per-role provider) is M4/PENDING and
        # intentionally NOT here.
        # I-run11-007 (#1051): pin to the ranked HEALTHY provider chain (order + ignore +
        # allow_fallbacks:False) so a verifier call never lands on a slow/flaky provider.
        body["provider"] = apply_provider_routing({"require_parameters": True}, request.role)
        # I-meta-008 FULL-POWER (CORRECTS #1017): a reasoning verifier MUST carry a GENEROUS top-level
        # `max_tokens`, NOT have it popped. OpenRouter `effort=xhigh` allocates ~95% of `max_tokens`
        # to the reasoning budget, and `max_tokens` MUST be strictly higher than that budget so the
        # bare verdict has room (docs: best-practices/reasoning-tokens). It is `reasoning.effort` vs
        # `reasoning.max_tokens` that are mutually exclusive — NOT top-level `max_tokens`. The prior
        # #1017 fix popped it, so xhigh ate ~95% of an unknown provider default and STARVED the verdict
        # to empty for a reasoning-first Mirror (GLM-5.1) / Judge (Qwen) -> fail-loud crash on the run.
        # 16384 -> reasoning ~15564 + verdict room ~820 (generous for Mirror JSON + Judge enum).
        #
        # I-run11-004: the DECOMPOSITION Sentinel (MiniMax-M2, reasoning ON) emits a JSON
        # {verdict, unsupported_atoms, atoms} body — a multi-atom list needs MORE output room than a
        # bare verdict, AND the certification used reasoning + max_tokens>=3000. So the decomposition
        # Sentinel gets its OWN generous budget (default 16384, hard-floored at 3000 so an env
        # override can never re-introduce the run-12 truncation that collapses every claim to a
        # fail-closed UNGROUNDED). Other reasoning verifiers keep PG_VERIFIER_REASONING_MAX_TOKENS.
        if request.role == "sentinel":
            decomp_budget = int(os.getenv("PG_SENTINEL_DECOMPOSITION_MAX_TOKENS", "16384"))
            body["max_tokens"] = max(decomp_budget, _SENTINEL_DECOMPOSITION_MIN_MAX_TOKENS)
        else:
            body["max_tokens"] = int(os.getenv("PG_VERIFIER_REASONING_MAX_TOKENS", "16384"))
    else:
        # Sentinel (reasoning-disabled classifier): give it explicit output room rather than relying
        # on an unknown provider default (no pop-and-hope). Small budget is plenty for a label verdict.
        body["max_tokens"] = int(os.getenv("PG_SENTINEL_MAX_TOKENS", "256"))
        # I-run11-007 (#1051): pin the non-reasoning role to its ranked HEALTHY provider chain too
        # (NO require_parameters — its slug does not advertise reasoning, so require_parameters would
        # refuse to route). Only set the block when routing is configured for the role.
        routed = apply_provider_routing({}, request.role)
        if routed:
            body["provider"] = routed
    return body


def _openrouter_served_block(raw: dict) -> dict:
    """Stash the genuinely-OpenRouter-served identity under `_pathb_served` for the M4
    served==pinned gate.

    OpenRouter reports the served `provider` / `model` / `system_fingerprint` at the top level
    of the response body (unlike a self-host vLLM, whose served identity is its `endpoint`). We
    surface exactly those three, dropping any that are absent — `build_response_metadata`
    consumes `provider`/`model`/`system_fingerprint` from `_pathb_served` and never substitutes
    a request-derived value, so a response that fails to report its served identity fails the
    gate loud rather than passing on request-derived data.
    """
    served: dict = {}
    for key in ("provider", "model", "system_fingerprint"):
        value = raw.get(key)
        if value:
            served[key] = value
    return served


def _parse_openrouter_response(raw: dict) -> tuple[object, str | None, dict | None, str | None]:
    """OpenRouter-aware `(raw_text, served_model, usage, reasoning)` extraction (P1-3).

    Identical fail-loud contract to the self-host `_parse_response` (a missing `choices`, a
    non-dict choice / message, or a blank bare verdict after reasoning separation raises
    `RoleTransportError` — an empty/blank/reasoning-only completion is never a valid verifier
    answer). The ONLY difference is the reasoning-extraction precedence: OpenRouter returns the
    verifier's chain-of-thought in `message.reasoning` (NOT `reasoning_content`, NOT an inline
    `<think>` block) per https://openrouter.ai/docs/guides/best-practices/reasoning-tokens . So
    the precedence here is: `reasoning_content` (vLLM reasoning-parser shape, kept for
    cross-provider safety) -> `message.reasoning` (OpenRouter shape) -> a leading inline
    `<think>` block split off `content`.

    Reasoning stays SEPARATE from `raw_text` (I-meta-002-q1b): `raw_text` is ONLY the bare
    verdict/body the verdict parsers consume; the reasoning rides on `RoleResponse.reasoning`.
    """
    choices = raw.get("choices")
    if not choices:
        raise RoleTransportError(
            f"OpenRouter response carried no choices (model={raw.get('model')!r})"
        )
    first_choice = choices[0]
    if not isinstance(first_choice, dict):
        raise RoleTransportError(
            f"OpenRouter response choice was not an object (model={raw.get('model')!r})"
        )
    message = first_choice.get("message")
    if not isinstance(message, dict):
        raise RoleTransportError(
            f"OpenRouter response choice carried no message object (model={raw.get('model')!r})"
        )
    content = message.get("content")
    model_repr = f"{raw.get('model')!r}"

    # Reasoning precedence: explicit separate fields first (content is already the bare verdict),
    # then a leading inline <think> block. `reasoning_content` is the vLLM reasoning-parser field;
    # `reasoning` is OpenRouter's documented field (P1-3). Either separate field means `content`
    # is the bare verdict and is NOT searched for a <think> block.
    reasoning_content = message.get("reasoning_content")
    openrouter_reasoning = message.get("reasoning")
    if isinstance(reasoning_content, str) and reasoning_content.strip():
        bare: object = content
        reasoning: str | None = reasoning_content
    elif isinstance(openrouter_reasoning, str) and openrouter_reasoning.strip():
        bare = content
        reasoning = openrouter_reasoning
    else:
        bare, reasoning = _separate_reasoning(content, model_repr)

    # Post-split blank guard (same as _parse_response): a verifier role MUST return a non-blank
    # bare verdict/body. A reasoning-only / think-only / empty-content response is a transport
    # failure, never a deliberately-empty answer — fail loud.
    if bare is None or (isinstance(bare, str) and not bare.strip()):
        # I-meta-008 / #1026: a RECOVERABLE blank — a reasoning-first verifier under effort=xhigh
        # can exhaust its reasoning budget without converging and emit zero content. Raise the
        # distinct BlankVerdictError so `complete()` retries with the reasoning effort stepped DOWN
        # (forcing the bare verdict) instead of hard-crashing the whole 4-role run. Still fail-loud
        # if every step-down also blanks.
        raise BlankVerdictError(
            f"OpenRouter response choice carried no/blank message content after reasoning "
            f"separation (model={model_repr})"
        )
    served_model = raw.get("model")
    usage = raw.get("usage")
    return bare, served_model, usage, reasoning


class OpenRouterRoleTransport:
    """Sync `RoleTransport` routing the Mirror / Sentinel / Judge verifier roles via OpenRouter
    with MAX reasoning (benchmark stage, I-meta-007d).

    Implements the SAME `RoleTransport` Protocol as `OpenAICompatibleRoleTransport`. The
    `httpx.Client` is INJECTED so tests pass an in-process stub (no network, no spend). Each
    `complete()` resolves the OpenRouter endpoint + BENCHMARK-lineup slug (P1-1), normalizes the
    payload (reusing the self-host message-rendering, then dropping the top-level `documents` key
    per P1-4), POSTs `/chat/completions` with MAX (`xhigh`) reasoning enabled, separates reasoning
    from the bare verdict (via `_parse_openrouter_response`, which reads `message.reasoning` per
    P1-3), captures the call under the Path-B gate (reasoning sanitized OUT of the capture
    channel), and returns a `RoleResponse` with reasoning kept SEPARATE from `raw_text`.

    SOVEREIGNTY: OpenRouter is a US router — dev/benchmark ONLY. Self-host (the lock's
    `serving_route`) is the final sovereign destination. See the module docstring.
    """

    def __init__(self, http_client: httpx.Client) -> None:
        self._http_client = http_client

    def complete(self, request: RoleRequest) -> RoleResponse:
        """Perform one OpenRouter completion for `request`. SYNC. Fails loud on error.

        Generator requests raise via `openrouter_role_endpoint`. The normalized messages are the
        SAME list POSTed to the body AND passed to `capture_llm_call`. The captured raw is
        augmented with `_pathb_served={provider, model, system_fingerprint}` so M4's
        served==pinned check consumes the genuinely-served OpenRouter identity (not the
        request-derived `model`). Reasoning is separated from the bare verdict (I-meta-002-q1b)
        and sanitized OUT of the Path-B capture channel.
        """
        base_url, api_key, model_slug = openrouter_role_endpoint(request.role)
        normalized_messages = _normalize_messages(request)
        body = _build_openrouter_body(request, model_slug, normalized_messages)
        url = f"{base_url}{_CHAT_COMPLETIONS_PATH}"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://polaris-research.ai",
            "X-Title": "polaris graph",
        }

        # I-meta-008 / #1026: reasoning verifiers get the blank-verdict step-down ladder so a
        # non-converging xhigh response cannot crash the whole 4-role run. The non-reasoning
        # Sentinel makes a SINGLE attempt (its body has no `reasoning` block to step down) — its
        # behavior is unchanged.
        reasoning_role = role_reasoning_enabled(request.role, request.model_slug)
        # I-run11-007 (#1051): a NON-reasoning role made a SINGLE attempt, so a blank from a flaky
        # provider had no recovery (OpenRouter does not auto-advance on an empty 200). When the role
        # is PINNED to a ranked provider chain, give it (1 + PG_PROVIDER_BLANK_RETRIES) attempts at
        # the same effort; each blank excludes the served provider so the retry advances to the next
        # HEALTHY provider. WITHOUT routing there is no chain to fail over to, so it keeps the original
        # single attempt (the reasoning-roles-only step-down ladder is unchanged when routing is off).
        provider_blank_retries = max(0, int(os.getenv("PG_PROVIDER_BLANK_RETRIES", "3")))
        role_is_routed = role_provider_routing(request.role) is not None
        non_reasoning_attempts = (1 + provider_blank_retries) if role_is_routed else 1
        effort_ladder: tuple[object, ...] = (
            _VERIFIER_EFFORT_LADDER
            if reasoning_role
            else (_REASONING_EFFORT,) * non_reasoning_attempts
        )
        last_blank: BlankVerdictError | None = None

        with _pathb_capture.llm_role(request.role):
            for attempt, effort in enumerate(effort_ladder):
                # Step the reasoning effort DOWN per attempt (only meaningful for a reasoning role,
                # whose body carries a `reasoning` block). `effort is None` => reasoning DISABLED
                # (final resort, guarantees content): drop the `reasoning` param. Keep
                # `provider.require_parameters` if the body STILL carries an output-constraining
                # param (`response_format` / `structured_outputs`) — that pin then guarantees a
                # provider that HONORS those constraints (Codex diff-gate P2). Only when reasoning
                # was the sole constrained param do we drop require_parameters (it would otherwise
                # have nothing to enforce).
                if reasoning_role and "reasoning" in body:
                    if effort is None:
                        body.pop("reasoning", None)
                        provider = body.get("provider")
                        if isinstance(provider, dict) and not (
                            "response_format" in body or "structured_outputs" in body
                        ):
                            provider.pop("require_parameters", None)
                            if not provider:
                                body.pop("provider", None)
                    else:
                        body["reasoning"] = {"enabled": True, "effort": effort}

                try:
                    http_response = self._http_client.post(
                        url, json=body, headers=headers, timeout=_TIMEOUT_SECONDS
                    )
                except httpx.HTTPError as exc:
                    raise RoleTransportError(
                        f"OpenRouter {request.role!r} transport error at {url}: {exc}"
                    ) from exc

                if http_response.status_code != httpx.codes.OK:
                    raise RoleTransportError(
                        f"OpenRouter {request.role!r} returned HTTP {http_response.status_code} "
                        f"at {url}"
                    )
                try:
                    raw = http_response.json()
                except (json.JSONDecodeError, ValueError) as exc:
                    raise RoleTransportError(
                        f"OpenRouter {request.role!r} returned a non-JSON body at {url}: {exc}"
                    ) from exc

                # I-meta-002-q1b + P1-3: reasoning separated from the bare verdict HERE via the
                # OpenRouter-aware parser (reads `message.reasoning`, not just `reasoning_content` /
                # `<think>`), so the verdict parsers only ever see the bare answer (no "soap") and
                # the OpenRouter reasoning is not lost. A BLANK bare verdict is RECOVERABLE (#1026):
                # step the effort down and retry; fail loud only if the ladder is exhausted.
                try:
                    raw_text, served_model, usage, reasoning = _parse_openrouter_response(raw)
                except BlankVerdictError as exc:
                    last_blank = exc
                    # Codex diff-gate P1 (budget-cap bypass): a blank attempt is DISCARDED, so its
                    # `usage` never reaches RecordingTransport (which bills only the final returned
                    # response). Account THIS blank attempt's tokens into the SAME shared
                    # PG_MAX_COST_PER_RUN accumulator the generator + the successful verifier calls
                    # feed, then enforce the cap BEFORE the next paid retry. Lazy import keeps the
                    # raw transport free of an import-time dependency on the orchestration layer
                    # (`compute_role_call_cost` lives in role_pipeline; `_orc` is openrouter_client,
                    # which does NOT import the roles package — both are cycle-safe).
                    import src.polaris_graph.llm.openrouter_client as _orc
                    from src.polaris_graph.roles.role_pipeline import compute_role_call_cost

                    _orc._add_run_cost(
                        compute_role_call_cost(request.model_slug, raw.get("usage"))
                    )
                    _orc.check_run_budget(0)  # raises BudgetExceededError if the cap is now crossed.
                    # I-run11-007 (#1051): exclude the provider that just returned blank so the NEXT
                    # attempt advances to the next HEALTHY provider in the ranked order (OpenRouter
                    # will NOT auto-advance on an empty 200). The served `provider` is the DISPLAY
                    # name; map it back to the routing SLUG so `ignore` uses the SAME identity as
                    # `order` (Codex diff-gate iter-1 P1). Persists across the reasoning step-down too.
                    blanked_provider = slug_for_provider(raw.get("provider"))
                    if blanked_provider and isinstance(body.get("provider"), dict):
                        ignore_list = body["provider"].setdefault("ignore", [])
                        if blanked_provider not in ignore_list:
                            ignore_list.append(blanked_provider)
                    if attempt + 1 < len(effort_ladder):
                        logger.warning(
                            "[polaris graph] #1026: %s blank verdict at reasoning effort=%s "
                            "(attempt %d/%d) — stepping effort down to %s and retrying.",
                            request.role, effort, attempt + 1, len(effort_ladder),
                            effort_ladder[attempt + 1],
                        )
                        continue
                    raise  # ladder exhausted: even reasoning-off blanked -> genuine fail-loud.

                # Stash the genuinely-OpenRouter-served identity for M4 BEFORE capture, then
                # sanitize reasoning OUT of the captured response (no-leak): reasoning lives ONLY
                # on the returned RoleResponse + four_role_role_calls.jsonl, never in the capture
                # channel.
                raw["_pathb_served"] = _openrouter_served_block(raw)
                _pathb_capture.capture_llm_call(
                    role=request.role,
                    messages=normalized_messages,
                    raw_response=_sanitize_raw_for_capture(raw, bare_text=raw_text),
                )
                # Mirror <co> citation invariant: return raw_text AS-IS (tags intact),
                # citations=None — mirror_adapter owns the parse/strip/offset alignment. reasoning
                # rides alongside (never concatenated into raw_text) for separate persistence.
                return RoleResponse(
                    raw_text=raw_text,
                    served_model=served_model,
                    usage=usage,
                    citations=None,
                    reasoning=reasoning,
                )

        # Unreachable: the loop returns on success or raises on ladder exhaustion. Kept so the
        # function has no implicit `None` return path.
        raise last_blank or RoleTransportError(
            f"OpenRouter {request.role!r} produced no response"
        )
