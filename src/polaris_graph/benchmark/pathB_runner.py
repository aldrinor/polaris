"""Path-B gate lifecycle helper for the honest_sweep runner (I-safety-002b #925).

Wraps each benchmark question with the gate: preflight + register capture sink + run +
assert_post_run before any scoring. Persists the pin record to the run dir. Self-contained
so the runner diff is minimal (1 import + 1 ``with`` per question).

Gate-off by default: the helper is a no-op context manager when ``--pathB-gate`` is not set,
so the existing honest_sweep pipeline is untouched outside the benchmark.

Per the Codex-APPROVED brief v2 (call_impl_capture + entailment_judge_capture +
served_metadata_provenance) and the Codex-APPROVED PR-2 role-tag fork (Option B: capture
only explicitly-tagged report-generator + report-evaluator calls; auxiliary scope/inductor
LLMs are not gated).
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
from pathlib import Path
from typing import Iterator

from src.polaris_graph.benchmark import pathB_capture as _capture
from src.polaris_graph.llm.openrouter_client import validate_role_families
from src.polaris_graph.roles.openrouter_role_transport import benchmark_verifier_slug
from scripts.architecture.verify_lock import load_lock
from scripts.dr_benchmark.pathB_run_gate import (
    GateError,
    LLMCall,
    RolePin,
    assert_post_run,
    preflight,
)
from src.polaris_graph.settings import resolve

logger = logging.getLogger(__name__)

# The four locked architecture roles (config/architecture/polaris_runtime_lock.yaml).
# Order is generator -> mirror -> sentinel -> judge (the canonical pipeline order).
_LOCKED_ROLES = ("generator", "mirror", "sentinel", "judge")

# Per-role env-var OVERRIDE knobs, applied ON TOP of the lock-sourced default slug. Mirrors
# config/architecture/polaris_runtime_lock.yaml:env_vars. The generator additionally honors
# the legacy OPENROUTER_DEFAULT_MODEL fallback (documented honest_sweep override chain).
_ROLE_ENV_OVERRIDE = {
    "generator": "PG_GENERATOR_MODEL",
    "mirror": "PG_MIRROR_MODEL",
    "sentinel": "PG_SENTINEL_MODEL",
    "judge": "PG_JUDGE_MODEL",
}


def _benchmark_openrouter_route() -> bool:
    """True iff the four-role transport is the benchmark OpenRouter route (PG_FOUR_ROLE_TRANSPORT
    unset or 'openrouter' — the DEFAULT). On that route the per-claim verifiers are served by the
    benchmark lineup over OpenRouter (the moonshotai/kimi-k2.6 Judge etc.), NOT the lock's sovereign
    self-host boxes. 'self_host' => the lock route (qwen Judge on the vast box), so the benchmark
    override below does NOT apply. Mirrors run_gate_b.four_role_transport_mode's default test WITHOUT
    importing the heavy benchmark CLI (LAW VII: a benchmark-side helper, not a lock change)."""
    return (resolve("PG_FOUR_ROLE_TRANSPORT") or "openrouter").strip().lower() == "openrouter"


def _lock_default_slug(role: str) -> str:
    """The role's default model_slug, SOURCED FROM the architecture lock so pins + lock cannot
    drift (Codex P2, accepted). Reads lock['required_roles'][role]['model_slug']."""
    lock = load_lock()
    return str(lock["required_roles"][role]["model_slug"]).strip()


def _resolve_role_slug(role: str) -> str:
    """Resolve a role's effective slug: lock default, with the per-role PG_*_MODEL env override
    applied on top. The generator preserves its documented PG_GENERATOR_MODEL >
    OPENROUTER_DEFAULT_MODEL > lock-default precedence (regression: a sweep that exports only
    OPENROUTER_DEFAULT_MODEL must still pin the right generator)."""
    default = _lock_default_slug(role)
    if role == "generator":
        return (
            os.getenv("PG_GENERATOR_MODEL")
            or os.getenv("OPENROUTER_DEFAULT_MODEL")
            or default
        ).strip()
    env_name = _ROLE_ENV_OVERRIDE[role]
    return (os.getenv(env_name) or default).strip()


def _role_pins() -> list[RolePin]:
    """Build the FOUR per-role pins (generator/mirror/sentinel/judge) from the lock + env.

    I-meta-002 sub-PR-5: the 2-role (generator+evaluator) pin set is replaced by the locked
    4-role set. The post-run gate enforces completeness in BOTH directions — every pinned role
    must be observed AND every observed call must be pinned (pathB_run_gate.assert_post_run
    lines 471/479) — so the pin set must EXACTLY match the captured roles. The 4-role pipeline
    emits generator/mirror/sentinel/judge calls; a leftover legacy 'evaluator' pin would
    therefore gate-FAIL at runtime (no evaluator call is captured). No production caller pins
    'evaluator' directly (only this function feeds preflight via gate_around_question), so the
    role is dropped here cleanly.

    Default slugs are LOCK-SOURCED via load_lock() (Codex P2, accepted) so the pins and the
    architecture lock cannot drift; per-role PG_*_MODEL env vars override on top. The generator
    keeps its PG_GENERATOR_MODEL > OPENROUTER_DEFAULT_MODEL > lock-default precedence.

    validate_role_families() runs on the effective 4-role map so the N-way family invariant
    (all 4 lineages distinct) holds at pin-build time — a same-family misconfiguration fails
    LOUD here rather than silently at runtime.

    Codex PR-2 diff iter-1 P1 #2: surrogate_fields are ONLY those PROVEN present in the served
    response (provider_name + model). assert_post_run treats a missing surrogate field as
    fatal; system_fingerprint is recorded when present but is NOT a required surrogate.

    I-bug-946 (#932): provider_name is left empty here; preflight() resolves the ACTUAL served
    provider per role via /api/v1/models/<id>/endpoints (the env is a candidate list)."""
    slug_by_role = {role: _resolve_role_slug(role) for role in _LOCKED_ROLES}
    # I-judge-kimi (2026-06-29): BENCHMARK-AWARE Judge pin. On the benchmark OpenRouter route the
    # Judge is NOT served by the lock's sovereign self-host qwen — qwen's ~2 OpenRouter providers
    # 429-tore the per-claim D8 seam, so the benchmark Judge was swapped to moonshotai/kimi-k2.6
    # (21 OpenRouter endpoints; see openrouter_role_transport._BENCHMARK_LINEUP_DEFAULT_SLUG). The
    # served identity the post-run gate must match is therefore the BENCHMARK lineup slug
    # (benchmark_verifier_slug('judge') = kimi) served OVER OpenRouter — NOT qwen @ vast_self_host_fp8.
    # So on this route the Judge pin's slug comes from the benchmark lineup AND its serving_route is
    # forced to 'openrouter' (set on the RolePin below; preflight preserves a pre-set route). The
    # Mirror/Sentinel/Generator pins are UNCHANGED. The SOVEREIGN lock path is untouched: in
    # self_host mode this override is OFF (the Judge stays the lock's qwen @ vast_self_host_fp8), and
    # PG_JUDGE_MODEL / the openrouter_client default stay the canonical-pinned qwen. This is a
    # benchmark-side serving override, NOT a lock change.
    judge_on_benchmark_route = _benchmark_openrouter_route()
    if judge_on_benchmark_route:
        slug_by_role["judge"] = benchmark_verifier_slug("judge")
    # N-way family segregation on the effective 4-role map (raises RuntimeError on collision).
    # I-beatboth-008 (#1285): honor the lock's family_policy.allowed_collisions (the single
    # source of truth) so the operator-approved all-GLM-5.2 generator+mirror collision PASSES
    # while a NON-listed same-family collision still RAISES. validate_role_families already
    # honors allowed_collisions under all_distinct (openrouter_client.py:774-787).
    _fp = load_lock().get("family_policy", {})
    _allowed_collisions = [tuple(str(x) for x in pair) for pair in _fp.get("allowed_collisions", [])]
    validate_role_families(slug_by_role, allowed_collisions=_allowed_collisions)
    surrogate_fields = ("provider_name", "model")
    return [
        RolePin(
            role,
            slug_by_role[role],
            "",
            surrogate_fields,
            # I-judge-kimi: the benchmark Judge is served over OpenRouter (kimi), so pin its route
            # to 'openrouter' to OVERRIDE the lock's vast_self_host_fp8 (preflight preserves a
            # pre-set serving_route). Every other role passes None -> preflight sources its route
            # from the lock as before (byte-identical: generator/mirror=openrouter, sentinel=
            # vast_self_host, judge=vast_self_host_fp8 in the sovereign self_host path).
            serving_route=("openrouter" if role == "judge" and judge_on_benchmark_route else None),
            # I-judge-kimi: the benchmark Judge is DELIBERATELY UNPINNED on OpenRouter (the
            # judge `order`/allow_fallbacks pin was removed from openrouter_provider_routing.yaml so
            # OpenRouter LOAD-BALANCES the ~178 per-claim D8 calls across kimi's 21 endpoints -> no
            # 429), and the blank-verdict recovery rotates providers. So a legitimate, fully-verified
            # kimi run serves MANY providers; allow_provider_drift tells assert_post_run to enforce
            # served==pinned MODEL (kimi) over the OpenRouter route but ALLOW the provider to vary.
            # ONLY the benchmark kimi Judge gets this; Mirror/Sentinel/Generator + every self-host
            # role keep allow_provider_drift=False (strict single-provider gate, byte-for-byte).
            allow_provider_drift=(role == "judge" and judge_on_benchmark_route),
        )
        for role in _LOCKED_ROLES
    ]


def role_tag(role: str):
    """Path-B capture role-tag context manager for a role-pipeline LLM call.

    Thin re-export of pathB_capture.llm_role so the 4-role call sites (Mirror/Sentinel/Judge)
    can scope their served-identity capture with the correct role string WITHOUT each importing
    pathB_capture directly. pathB_capture already accepts arbitrary role strings via its _ROLE
    contextvar, so "mirror" / "sentinel" / "judge" are supported with no capture-side change.
    Use as `with role_tag("sentinel"): ...`. The deep sweep call-site wiring is sub-PR-6."""
    return _capture.llm_role(role)


def _salt() -> bytes:
    return (resolve("PG_PATHB_GATE_SALT") or "pathB-default-unsalted").encode("utf-8")


@contextlib.contextmanager
def gate_around_question(
    *, enabled: bool, run_dir: Path, control_vars: list[str] | None = None,
) -> Iterator[None]:
    """Wrap one benchmark question's run with preflight + post-run assertion.

    Usage in the runner:
        with gate_around_question(enabled=args.pathB_gate, run_dir=run_dir):
            ... process_query body, including the role-tagged LLM calls ...
            # On normal exit, assert_post_run runs (raises GateError if not full-power).

    Behavior:
    - enabled=False: no-op (yields immediately, no capture, no preflight).
    - enabled=True: preflight (raises GateError if not full-power); register_pathB_capture;
      yield; on normal exit, assert_post_run; persist pin + result to ``run_dir``. On
      exception inside the body, capture is cleared but the exception propagates.
    """
    if not enabled:
        yield
        return

    pin_path = run_dir / "pathB_gate_pin.json"
    result_path = run_dir / "pathB_gate_result.json"
    invalid_sentinel = run_dir / "pathB_gate_INVALID"
    run_dir.mkdir(parents=True, exist_ok=True)

    # Codex PR-2 diff iter-1 P3: write a FAIL result file even when preflight raises,
    # so a missing-credential / unreachable-backend failure has an explicit per-run record
    # (otherwise the only artifact is a stderr exception, no traceable artifact).
    try:
        pin = preflight(
            control_vars=list(control_vars or []),
            role_pins=_role_pins(),
            salt=_salt(),
            roots=[Path("src/polaris_graph"), Path("scripts")],
            offline=False,  # real run = real reachability ping (gate enforce-by-default).
        )
    except GateError as exc:
        result_path.write_text(
            json.dumps(
                {"verdict": "FAIL", "stage": "preflight", "reason": str(exc)},
                indent=2, sort_keys=True,
            ),
            encoding="utf-8",
        )
        invalid_sentinel.write_text(
            f"preflight FAIL: {exc}\n", encoding="utf-8",
        )
        logger.error("[pathB] preflight FAIL: %s", exc)
        raise
    pin_path.write_text(json.dumps(pin, indent=2, sort_keys=True, default=str),
                        encoding="utf-8")
    _capture.register_pathB_capture()
    # I-bug-946 (#932): publish the resolved per-role provider mapping via ContextVar so
    # openrouter_client and entailment_judge force singleton routing in their request bodies.
    # Without this, OpenRouter's silent fallback re-routes mid-run and the post_run gate fails
    # (smoke #15: evaluator served by Novita while pin expected Fireworks).
    role_provider_map = {
        rp["role"]: rp["provider_name"]
        for rp in pin.get("role_pins", [])
        if rp.get("provider_name")
    }
    rp_token = _capture.set_role_providers(role_provider_map) if role_provider_map else None
    try:
        yield
    except Exception:
        # Propagate; do not run assert_post_run on a failed run (it would mask the cause).
        if rp_token is not None:
            _capture.reset_role_providers(rp_token)
        _capture.clear_pathB_capture()
        raise

    try:
        # #958 (S2): a truncated corpus (post-fetch loop budget broke mid-corpus)
        # is a fail-loud non-clean signal — block PASS BEFORE the assert/PASS write.
        # Reuses the existing GateError handler below (→ FAIL result + INVALID sentinel).
        try:
            _manifest = json.loads(
                (run_dir / "manifest.json").read_text(encoding="utf-8")
            )
        except Exception:
            _manifest = {}
        if _capture.corpus_truncated_from_manifest(_manifest):
            _rt = _manifest.get("retrieval", {})
            raise GateError(
                "corpus truncated — post-fetch loop budget broke mid-corpus "
                f"({_rt.get('candidates_processed')}/{_rt.get('candidates_total')} "
                "candidates processed); run is partial, not full-power"
            )
        calls = [LLMCall(**c) for c in _capture.collected_calls()]
        backends = _capture.attempted_backends()
        result = assert_post_run(
            pin=pin,
            control_vars=list(control_vars or []),
            salt=_salt(),
            calls=calls,
            retrieval_backends_attempted=backends,
        )
        result_path.write_text(
            json.dumps({"verdict": "PASS", **result}, indent=2, sort_keys=True, default=str),
            encoding="utf-8",
        )
        logger.info("[pathB] gate PASS for run_dir=%s", run_dir)
    except GateError as exc:
        result_path.write_text(
            json.dumps(
                {"verdict": "FAIL", "stage": "post_run_assert", "reason": str(exc)},
                indent=2, sort_keys=True,
            ),
            encoding="utf-8",
        )
        # Codex PR-2 diff iter-1 P2 #2: write an INVALID sentinel so downstream scoring
        # (PR-3 claim_audit_scorer) can skip the run_dir's per-run artifacts even though
        # they were written during the run (manifest/judge/etc.). The gate is the source
        # of truth for run validity; the sentinel makes that machine-readable.
        invalid_sentinel.write_text(
            f"post-run gate FAIL: {exc}\n", encoding="utf-8",
        )
        logger.error("[pathB] gate FAIL for run_dir=%s: %s", run_dir, exc)
        raise
    finally:
        _capture.clear_pathB_capture()
