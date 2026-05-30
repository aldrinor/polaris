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
from scripts.architecture.verify_lock import load_lock
from scripts.dr_benchmark.pathB_run_gate import (
    GateError,
    LLMCall,
    RolePin,
    assert_post_run,
    preflight,
)

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
    # N-way family segregation on the effective 4-role map (raises RuntimeError on collision).
    validate_role_families(slug_by_role)
    surrogate_fields = ("provider_name", "model")
    return [
        RolePin(role, slug_by_role[role], "", surrogate_fields)
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
    return (os.getenv("PG_PATHB_GATE_SALT") or "pathB-default-unsalted").encode("utf-8")


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
