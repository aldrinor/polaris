"""
Live judge — HONEST-REBUILD Phase 5 live wiring.

Calls the REAL evaluator model via OpenRouter (model read from
PG_EVALUATOR_MODEL at runtime). Under the LOCKED 4-role architecture
(config/architecture/polaris_runtime_lock.yaml, I-meta-001 #933) the legacy
PG_EVALUATOR_MODEL knob resolves to the Mirror role via the lock's
legacy_compat map (PG_EVALUATOR_MODEL -> PG_MIRROR_MODEL) when unset.
Historical defaults: Gemma 4 31B as of 2026-05-08 per I-bug-087, previously
Qwen3-8B per HONEST-REBUILD Phase 1c. Produces per-axis structured verdicts
on a completed report.

This is the NON-SAME-FAMILY judge: the judge model must be from a
different training family than the generator. `check_family_segregation()`
must succeed before this is called.

DESIGN
------
We do NOT ask the judge for a single "faithfulness %". Per Phase 5
plan, that single number is the exact pattern that cooked Run #17.
Instead the judge produces per-axis verdicts:
  - citation_tightness: does each claim have an evidence citation?
  - hedging_appropriateness: does the prose hedge when evidence disagrees?
  - tone_consistency: is the tone evidence-grounded vs promotional?
  - flow: are the sentences logically ordered?
  - completeness: are major evidence rows touched on?

For each axis, the judge returns verdict ∈ {good, acceptable, needs_revision}
and a 1-2 sentence note. No aggregate "score".
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Any, Optional

logger = logging.getLogger("polaris_graph.live_judge")


SYSTEM_PROMPT = """You are a quality auditor for research summaries. You grade along distinct axes, you do NOT produce a single score.

Return your verdict as a JSON object with exactly these keys:
{
  "citation_tightness": {"verdict": "good|acceptable|needs_revision", "note": "..."},
  "hedging_appropriateness": {"verdict": "good|acceptable|needs_revision", "note": "..."},
  "tone_consistency": {"verdict": "good|acceptable|needs_revision", "note": "..."},
  "flow": {"verdict": "good|acceptable|needs_revision", "note": "..."},
  "completeness": {"verdict": "good|acceptable|needs_revision", "note": "..."}
}

Rules for each axis:
- citation_tightness: Does every factual claim have an adjacent citation marker [1] or [#ev:...]? Missing citations = needs_revision.
- hedging_appropriateness: Does the prose flag disagreement where the evidence shows disagreement? Overconfident = needs_revision.
- tone_consistency: Is tone evidence-grounded (not promotional)? Marketing language = needs_revision.
- flow: Do sentences follow a logical order (context -> mechanism -> evidence -> limitations)?
- completeness: Are the MAJOR evidence rows touched on (primary trials, regulatory status, key safety)? Missing core evidence = needs_revision.

Do NOT return anything other than the JSON object. No preamble, no sign-off, no markdown code fence."""


@dataclass
class LiveJudgeResult:
    verdicts: dict[str, dict[str, str]]   # axis -> {verdict, note}
    model: str
    raw_response: str
    parse_ok: bool
    input_tokens: int
    output_tokens: int
    error: str = ""


def _parse_judge_json(text: str) -> tuple[Optional[dict], str]:
    """Extract JSON from judge response. Returns (parsed, error_msg)."""
    if not text or not text.strip():
        return None, "empty response"
    # Strip common markdown fences
    stripped = text.strip()
    if stripped.startswith("```"):
        # Remove leading fence
        stripped = re.sub(r"^```(?:json)?\s*", "", stripped)
        # Remove trailing fence
        stripped = re.sub(r"\s*```\s*$", "", stripped)
    # Find first { and last } — fault-tolerant to any leading prose
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start == -1 or end == -1 or end < start:
        return None, "no JSON object found"
    try:
        parsed = json.loads(stripped[start:end + 1])
        return parsed, ""
    except json.JSONDecodeError as exc:
        return None, f"JSON decode error: {exc}"


def _validate_verdicts(parsed: dict) -> tuple[dict[str, dict[str, str]], list[str]]:
    """Ensure each axis has the expected shape. Returns (verdicts, warnings)."""
    required_axes = {
        "citation_tightness", "hedging_appropriateness",
        "tone_consistency", "flow", "completeness",
    }
    allowed_verdicts = {"good", "acceptable", "needs_revision"}
    verdicts: dict[str, dict[str, str]] = {}
    warnings: list[str] = []
    for axis in required_axes:
        val = parsed.get(axis)
        if not isinstance(val, dict):
            warnings.append(f"axis {axis!r}: missing or not a dict")
            verdicts[axis] = {"verdict": "unknown", "note": "missing from response"}
            continue
        verdict = str(val.get("verdict", "unknown")).strip().lower()
        if verdict not in allowed_verdicts:
            warnings.append(f"axis {axis!r}: verdict {verdict!r} not in allowed set")
            verdict = "unknown"
        note = str(val.get("note", "")).strip()[:500]
        verdicts[axis] = {"verdict": verdict, "note": note}
    return verdicts, warnings


async def judge_report(
    *,
    report_text: str,
    research_question: str,
    model: Optional[str] = None,
    max_tokens: int = 800,
    temperature: float = 0.2,
) -> LiveJudgeResult:
    """Call the evaluator model via OpenRouter for a structured per-axis verdict.

    check_family_segregation() is run BEFORE the call. If the configured
    generator/evaluator pair is same-family, this raises RuntimeError.
    """
    from src.polaris_graph.llm.openrouter_client import (  # noqa: E402
        OpenRouterClient,
        PG_EVALUATOR_MODEL,
        check_family_segregation,
    )

    check_family_segregation()   # raises if same family

    eval_model = model or PG_EVALUATOR_MODEL
    client = OpenRouterClient(model=eval_model)

    prompt = (
        f"Research question: {research_question}\n\n"
        f"Report to audit:\n\n{report_text}\n\n"
        f"Return the JSON object as specified in the system prompt."
    )

    logger.info("[live_judge] calling %s, report_chars=%d",
                eval_model, len(report_text))

    try:
        response = await client.generate(
            prompt=prompt,
            system=SYSTEM_PROMPT,
            max_tokens=max_tokens,
            temperature=temperature,
        )
    finally:
        if hasattr(client, "close"):
            try:
                await client.close()
            except Exception:
                pass
    raw = (response.content or "").strip()
    parsed, parse_err = _parse_judge_json(raw)

    if parsed is None:
        return LiveJudgeResult(
            verdicts={},
            model=eval_model,
            raw_response=raw,
            parse_ok=False,
            input_tokens=response.input_tokens,
            output_tokens=response.output_tokens,
            error=parse_err,
        )

    verdicts, warnings = _validate_verdicts(parsed)
    return LiveJudgeResult(
        verdicts=verdicts,
        model=eval_model,
        raw_response=raw,
        parse_ok=True,
        input_tokens=response.input_tokens,
        output_tokens=response.output_tokens,
        error="; ".join(warnings),
    )
