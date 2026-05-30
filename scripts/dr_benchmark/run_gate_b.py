"""Gate-B production caller — wires the native 4-role evaluation into the honest sweep.

I-meta-002 PR-9/M3b. This is WIRING ONLY: it constructs the real
`OpenAICompatibleRoleTransport` for the three self-hosted verifier roles (Mirror / Sentinel /
Judge — the generator stays on OpenRouter, upstream of this transport), sets
`PG_FOUR_ROLE_MODE`, builds a no-argument CLOSURE over the native input builder
(`build_native_gate_b_inputs`) + the deterministic evidence normalization, and hands the
transport + builder into `run_one_query`.

CONTAMINATION-CRITICAL (§-1.1, operator-locked): every input is built ONLY from NATIVE
config — the scope template's `per_query_report_contract[<slug>].required_entities` and the
D8 release-policy config. This module NEVER reads anything under `outputs/dr_benchmark/`
(gold rubric / freeze pin / competitor answers).

NO SPEND / NO NETWORK at import. The transport's `httpx.Client` is created INSIDE
`build_gate_b_transport` (not at module level), so importing this module never opens a client
or touches a socket. The Gate-B LIVE run (real self-host endpoints + real spend) is the later
operator-authorized canary; this module is exercised offline by the seam test with a FAKE
transport injected in place of `build_gate_b_transport`'s output.
"""

from __future__ import annotations

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
from src.polaris_graph.roles.release_policy import load_d8_policy_config

# The three self-hosted verifier roles this caller serves (the generator is excluded — it runs
# live on OpenRouter, upstream of the per-claim verifier transport).
_VERIFIER_ROLES = ("mirror", "sentinel", "judge")

# Env flag the guarded sweep branch reads to activate the 4-role seam.
_FOUR_ROLE_MODE_ENV = "PG_FOUR_ROLE_MODE"

# httpx client timeout knob (LAW VI): same env var + fallback the transport uses.
_TIMEOUT_SECONDS = int(os.getenv("PG_LLM_TIMEOUT_SECONDS", "90"))


def build_gate_b_transport() -> OpenAICompatibleRoleTransport:
    """Construct the real self-host verifier transport (one shared sync `httpx.Client`).

    Built INSIDE this function (never at module level) so importing `run_gate_b` opens no
    client and touches no socket. The transport resolves each verifier role's per-role
    `PG_<ROLE>_BASE_URL` / `PG_<ROLE>_API_KEY` at `complete()` time (no OpenRouter-key leak;
    keyless self-host omits the Authorization header). Returns a transport that, when actually
    invoked, POSTs `/v1/chat/completions` to the configured self-host endpoints — that live
    invocation is the later operator-authorized Gate-B canary, never a test.
    """
    return OpenAICompatibleRoleTransport(httpx.Client(timeout=_TIMEOUT_SECONDS))


def verifier_model_slugs() -> dict[str, str]:
    """Return the pinned `{mirror,sentinel,judge: model_slug}` map from the runtime lock.

    The single machine-readable source of truth (LAW VI). The generator slug is intentionally
    excluded — it is not a per-claim verifier role.
    """
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


async def run_gate_b_query(
    q: dict,
    out_root: Path,
    *,
    transport: OpenAICompatibleRoleTransport | None = None,
    d8_config_path: str | Path | None = None,
) -> dict:
    """Run ONE query through the honest sweep with the native 4-role Gate-B seam ACTIVE.

    WIRING ONLY (LAW VII CLI isolation): activates `PG_FOUR_ROLE_MODE`, builds the real
    self-host verifier `transport` (unless one is injected — the offline seam test injects a
    FAKE), builds the argument-taking Gate-B builder closure, and hands transport + builder into
    `run_one_query`. The seam calls the builder AFTER generation with the run-local objects.

    This function is the Gate-B production entrypoint; its LIVE invocation (real self-host
    endpoints + real spend) is the later operator-authorized canary. It is NEVER invoked against
    a live endpoint by any test — the seam test exercises `run_four_role_seam` with a fake
    transport directly. Imported lazily so this module's import never pulls the big sweep file.
    """
    from scripts.run_honest_sweep_r3 import run_one_query

    enable_four_role_mode()
    active_transport = transport if transport is not None else build_gate_b_transport()
    builder = make_gate_b_input_builder(d8_config_path=d8_config_path)
    return await run_one_query(
        q,
        out_root,
        four_role_transport=active_transport,
        four_role_input_builder=builder,
    )
