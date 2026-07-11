"""The verified-compute RENDER lane for the agentic outliner (W3-render, 2026-07-11).

This module closes the render half of the compute-reachability P1: it is the ONLY path by
which a number the agent DERIVED (a delta / ratio / sum) may reach rendered outline text. It
does so without ever widening the faithfulness surface, because it renders that number ONLY as
a ``[#calc:model_id:spec_hash:field]`` token — which ``strict_verify`` force-routes to
``verify_modeled_atom`` (provenance_generator.py:1885), NOT to the ``[#ev:...]`` / ``[CITE:...]``
evidence-span path. A derived number can never satisfy the evidence-span path (its digits appear
in no single source span → ``number_not_in_any_cited_span``), so it is structurally impossible to
launder an unverified computed value through a citation. Proven end-to-end in
tests/polaris_graph/outline/test_verified_compute_render.py.

The moat vs. frontier products: the number is not asserted, it is COMPUTED and PROVED. The tool
supplies {question, sourced inputs (ev_id + raw_literal via a datapoint match), formula intent};
``build_quantified_spec`` (tradeoff_modeler.py:782) validates fail-closed —
``literal_span_is_faithful``, the pure-arithmetic AST whitelist, exact-one datapoint match, and
the material-dependency perturbation gate — then ``execute_quantified_model``
(quantified_analysis.py:650) RE-DERIVES the number by executing the rendered (non-LLM) script in
the sandbox and pins its canonical ``display_value``. Regime-C verification later re-checks the
rendered digits against that re-execution.

SPEND-FREE: no network, no codegen LLM. The spec is supplied by the caller and validated
deterministically; a bad spec returns ``None`` (the whole compute is skipped, fail-closed).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Optional

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ComputedClaim:
    """A verified, render-eligible computed number.

    ``calc_token`` is the ONLY thing that may be emitted into outline text next to
    ``display_value``; ``strict_verify`` (given the workspace's ``quantified_models`` registry)
    keeps the sentence iff the number immediately before the token canonicalizes to exactly
    ``display_value`` and every sourced input resolves. Anything else about this claim is
    telemetry.
    """

    model_id: str
    spec_hash: str
    field_id: str
    display_value: str
    calc_token: str
    question: str
    formula: str

    def render_sentence(self, lead: str) -> str:
        """A minimal, verifier-passing sentence: ``<lead> <display_value> <calc_token>.``

        ``lead`` is caller prose (e.g. "Adobe's operating income rose by"); the display value
        is placed IMMEDIATELY before the calc token (token adjacency, brief §1.4) so
        ``verify_modeled_atom`` binds the token to exactly this rendered number.
        """
        lead = lead.rstrip()
        return f"{lead} {self.display_value} {self.calc_token}."


async def run_verified_compute(
    workspace: Any,
    *,
    question: str,
    datapoints: list[dict[str, Any]],
    raw_spec: dict[str, Any],
    render_field: Optional[str] = None,
    timeout: int | None = None,
    on_reject: Optional[Any] = None,
) -> Optional[ComputedClaim]:
    """Build → validate → execute → REGISTER a verified quantified model; return a
    ``ComputedClaim`` for ONE output field (``render_field``, default: the first output).

    Fail-closed: returns ``None`` (and discloses the reject reason on the workspace) on ANY
    validation or execution failure. On success, the ``QuantifiedResult`` is registered in
    ``workspace.quantified_models`` keyed by ``(model_id, spec_hash)`` — exactly the shape
    ``strict_verify(..., quantified_models=<registry>)`` consumes — so the returned claim's
    ``calc_token`` will verify when it is later rendered into outline text.

    Parameters mirror the ``build_quantified_spec`` contract:
      * ``datapoints`` — the candidate sourced numbers (cp-format: evidence_id/label/context/
        value/unit); each referenced input matches EXACTLY one of these.
      * ``raw_spec`` — {model_id, title, inputs:[{name, datapoint_ref|modeled...}], outputs:
        [{name, formula, unit, display_kind}]}. The agent supplies the FORMULA INTENT here; the
        span derivation and re-execution are the tool's, not the agent's.
    """
    # Lazy imports: this module is loaded at agent import time; keep the heavy synthesis /
    # generator graph off the import path until a compute is actually requested.
    from src.polaris_graph.generator.quantified_analysis import execute_quantified_model  # noqa: PLC0415
    from src.polaris_graph.synthesis.tradeoff_modeler import build_quantified_spec  # noqa: PLC0415

    ev_store = getattr(workspace, "ev_store", {}) or {}

    reject_reasons: list[str] = []

    def _reject_sink(reason: str) -> None:
        reject_reasons.append(reason)
        if on_reject is not None:
            try:
                on_reject(reason)
            except Exception:  # noqa: BLE001 — a telemetry sink must never break the compute
                pass

    def _spec_llm(_q: str, _s: list[dict[str, Any]]) -> dict[str, Any]:
        # Deterministic: the caller already produced the validated-intent spec. build_quantified_spec
        # still runs EVERY fail-closed gate over it (no LLM, no codegen, spend-free).
        return raw_spec

    try:
        spec = build_quantified_spec(
            question, datapoints, ev_store,
            spec_llm=_spec_llm, on_reject=_reject_sink,
        )
    except Exception as exc:  # noqa: BLE001 — fail-closed: a builder defect skips the compute
        _disclose(workspace, f"verified_compute: spec build raised ({str(exc)[:120]}) — no number rendered")
        return None

    if spec is None:
        _disclose(
            workspace,
            f"verified_compute: spec REJECTED (fail-closed, no number rendered) "
            f"reasons={reject_reasons or ['unknown']}",
        )
        return None

    try:
        result = await execute_quantified_model(spec, ev_store, timeout=timeout)
    except Exception as exc:  # noqa: BLE001 — sandbox/exec failure is a clean skip
        _disclose(workspace, f"verified_compute: execution raised ({str(exc)[:120]}) — no number rendered")
        return None

    if result is None:
        _disclose(workspace, "verified_compute: model did not execute cleanly — no number rendered (fail-closed)")
        return None

    # Choose the field to render. Default: the first declared output name (its field_id == name).
    field_id = render_field or (spec.outputs[0].name if spec.outputs else "")
    disp = result.display_value(field_id)
    if not field_id or disp is None:
        _disclose(
            workspace,
            f"verified_compute: field {field_id!r} produced no display_value — no number rendered",
        )
        return None

    # REGISTER: this is what makes the calc token verifiable downstream. Keyed identically to
    # strict_verify's consumption ((model_id, spec_hash)).
    registry = _ensure_registry(workspace)
    registry[result.key()] = result

    token = result.calc_token(field_id)
    formula = ""
    out = spec.output_by_name(field_id.split("@", 1)[0])
    if out is not None:
        formula = out.formula

    _disclose(
        workspace,
        f"verified_compute: RENDER-ELIGIBLE {disp} via {token} "
        f"(formula={formula!r}, inputs={[s.name for s in spec.sourced_inputs]}) — "
        "renders ONLY through the verified [#calc:] lane, never [#ev:]/[CITE:]",
    )

    return ComputedClaim(
        model_id=result.model_id,
        spec_hash=result.spec_hash,
        field_id=field_id,
        display_value=disp,
        calc_token=token,
        question=question,
        formula=formula,
    )


def _ensure_registry(workspace: Any) -> dict:
    reg = getattr(workspace, "quantified_models", None)
    if not isinstance(reg, dict):
        reg = {}
        try:
            workspace.quantified_models = reg
        except Exception:  # noqa: BLE001 — a frozen/odd workspace still gets a usable local registry
            pass
    return reg


def _disclose(workspace: Any, text: str) -> None:
    fn = getattr(workspace, "disclose", None)
    if callable(fn):
        fn(text)
    else:
        logger.info("[verified_compute] %s", text)
