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
from scripts.dr_benchmark.pathB_run_gate import (
    GateError,
    LLMCall,
    RolePin,
    assert_post_run,
    preflight,
)

logger = logging.getLogger(__name__)

_DEFAULT_GEN_SLUG = "deepseek/deepseek-v4-pro"
_DEFAULT_EVAL_SLUG = "google/gemma-4-31b-it"


def _role_pins() -> list[RolePin]:
    """Build the per-role pins from the live env.

    Codex PR-2 diff iter-1 P1 #1: read PG_GENERATOR_MODEL first (the documented honest_sweep
    override used by generate_multi_section_report); fall back to OPENROUTER_DEFAULT_MODEL,
    then the static default. Pinning the wrong env var made every correct call fail the gate.

    Codex PR-2 diff iter-1 P1 #2: surrogate_fields MUST be only those PROVEN present in the
    served response. assert_post_run treats a missing surrogate field as fatal, so requiring
    system_fingerprint would fail any provider that omits it (entailment_judge often does).
    Pin only the always-present surrogate (provider_name + model); build_response_metadata
    still records system_fingerprint when present, but it is NOT a required surrogate."""
    gen = (
        os.getenv("PG_GENERATOR_MODEL")
        or os.getenv("OPENROUTER_DEFAULT_MODEL")
        or _DEFAULT_GEN_SLUG
    ).strip()
    ev = (os.getenv("PG_EVALUATOR_MODEL") or _DEFAULT_EVAL_SLUG).strip()
    # I-bug-946 (#932): provider_name is no longer seeded from env's first entry. The
    # OPENROUTER_PROVIDER_ORDER env is now a CANDIDATE LIST, and preflight() resolves the
    # ACTUAL served provider per role via /api/v1/models/<id>/endpoints. Pre-seeding to
    # the env first-entry was the Codex iter-1 diff P1 bypass: my preflight only resolved
    # when provider_name was empty, so the bypass silently re-pointed both roles to the
    # first env entry. Now: empty string here forces preflight to resolve per role.
    surrogate_fields = ("provider_name", "model")
    return [
        RolePin("generator", gen, "", surrogate_fields),
        RolePin("evaluator", ev, "", surrogate_fields),
    ]


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
