"""I-wire-001 W1 — scope=intent_frame (advisory intent decomposition).

This module implements the W1 winner ("intent_frame", section-winner board row 1):
a SINGLE GLM-5.2 call that decomposes a long / confusing / multi-part research
prompt into a typed ``IntentFrame`` — ``{questions[], domain, clarification_needed[]}``
— BEFORE the deterministic ``run_scope_gate`` runs.

It is ADVISORY. It runs IN FRONT OF the deterministic scope gate and does NOT
replace, relax, or serialize into the immutable, hash-stamped ``protocol.json``
(design: ``docs/scope_intake_landscape_2026.md`` §3 Job 1). The deterministic
scope gate remains the single binding gate; the frame is routing context only,
the same contract the existing advisory ``DomainIntent`` already follows
(``scope_gate.py`` ``classify_domain_intent``).

FAITHFULNESS: nothing here touches the frozen faithfulness engine
(strict_verify / NLI / 4-role D8 / provenance). It only shapes *which questions
get asked*; it produces no citable evidence and reads no spans.

WIRING DISCIPLINE (CLAUDE.md "fully-wired" gate): default OFF =>
byte-identical legacy (the frame is never built, the injected ``llm`` is never
called, zero spend). When ENABLED, the step is FAIL-CLOSED — if the decomposition
yields an empty / None frame (blank LLM reply, unparseable JSON, or zero
questions) it RAISES ``IntentFrameError`` so a silent no-op aborts the run rather
than shipping the legacy path under a "wired" claim. The firing canary is emitted
ONLY after a successful decomposition, reporting real runtime counts.

The ``llm`` is an INJECTED ``Callable[[str], str]`` (the GLM-5.2 policy, sovereign
mirror stack), mirroring ``fs_researcher_query_gen.plan_fs_researcher_queries``.
The integrator builds the sync GLM-5.2 callable (``PG_MIRROR_MODEL``, default
``z-ai/glm-5.2``) exactly like ``run_honest_sweep_r3._iter_llm``; this module
never imports the OpenRouter client, so it is unit-testable on a pure stub.
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from typing import Any, Callable

logger = logging.getLogger(__name__)

# (prompt) -> reply text. The GLM-5.2 policy, injected (async client wrapped to
# sync by the caller). Identical seam shape to fs_researcher_query_gen.LlmFn.
LlmFn = Callable[[str], str]

# ─── env knobs (LAW VI — no hard-coded behaviour) ───────────────────────────
_ENV_FLAG = "PG_SCOPE_INTENT_FRAME"
_FLAG_TRUE_VALUES = frozenset({"1", "true", "yes", "on"})

_ENV_MAX_QUESTIONS = "PG_SCOPE_INTENT_FRAME_MAX_QUESTIONS"
_DEFAULT_MAX_QUESTIONS = 10
_ENV_MAX_CLARIFICATIONS = "PG_SCOPE_INTENT_FRAME_MAX_CLARIFICATIONS"
_DEFAULT_MAX_CLARIFICATIONS = 6

# Free-text domain label fallback (NOT a closed enum — mirrors the scope gate's
# `general` safe default so an unrecognised label never aborts downstream).
_DEFAULT_DOMAIN = "general"

# Accepted JSON key aliases. The brief's public contract is questions /
# clarification_needed, but the gold fixture
# (tests/fixtures/upstream_golds/scope_intent_decomposition_gold.jsonl) and a
# free GLM reply may use sub_questions / ambiguities_to_clarify — accept both in
# the PARSER without widening the public dataclass.
_QUESTION_KEYS = ("questions", "sub_questions")
_CLARIFY_KEYS = ("clarification_needed", "ambiguities_to_clarify")
_DOMAIN_KEY = "domain"

# Single-call decomposition prompt. JSON-only reply requested.
_PROMPT_TEMPLATE = (
    "You are an intent-decomposition step that runs in front of a research "
    "pipeline. Read the user's raw research prompt and return ONE JSON object "
    "(no prose, no markdown code fences) with EXACTLY these keys:\n"
    '  "questions": a list of the distinct, self-contained research '
    "sub-questions the prompt is actually asking. Decompose a multi-part or "
    "confusing prompt into separate questions; return a single-item list when "
    "it is one question.\n"
    '  "domain": one short lowercase free-text domain label '
    '(e.g. "clinical", "economics", "policy", "technology", "general").\n'
    '  "clarification_needed": a list of short clarifying questions to ask the '
    "user ONLY when the prompt is genuinely under-specified; an empty list "
    "otherwise.\n"
    "Return only the JSON object.\n\n"
    "RAW PROMPT:\n{question}"
)


class IntentFrameError(RuntimeError):
    """Raised when the intent-frame step is ENABLED but fails to produce a
    non-empty frame (blank/None LLM reply, unparseable JSON, or zero questions).

    Fail-closed by design: the integrator MUST let this propagate (do NOT wrap
    it and fall back to the legacy path) — otherwise the silent-no-op the
    "fully-wired" gate forbids re-appears under a wired claim.
    """


@dataclass(frozen=True)
class IntentFrame:
    """Advisory intent decomposition (W1). NOT serialized into protocol.json —
    pure routing context handed to the scope gate / query-gen.

    Attributes:
        questions: distinct self-contained research sub-questions (>= 1 item;
            an empty list is impossible — it is the fail-closed trip).
        domain: short free-text domain label, ``general`` when unknown.
        clarification_needed: clarifying questions for an under-specified prompt;
            empty when the prompt is well-specified.
    """

    questions: list[str]
    domain: str
    clarification_needed: list[str]


def intent_frame_enabled() -> bool:
    """True iff the W1 intent-frame step is flag-enabled.

    Default OFF: the frame is never built, the injected ``llm`` is never called,
    and behaviour is byte-identical to the legacy scope path.
    """
    return os.getenv(_ENV_FLAG, "0").strip().lower() in _FLAG_TRUE_VALUES


def _max_questions() -> int:
    """Cap on decomposed questions kept (env-overridable; caps prompt blow-up)."""
    raw = os.getenv(_ENV_MAX_QUESTIONS, "").strip()
    if not raw:
        return _DEFAULT_MAX_QUESTIONS
    try:
        value = int(raw)
    except ValueError:
        logger.warning(
            "[intent_frame] %s=%r is not an int — using %d",
            _ENV_MAX_QUESTIONS, raw, _DEFAULT_MAX_QUESTIONS,
        )
        return _DEFAULT_MAX_QUESTIONS
    return value if value > 0 else _DEFAULT_MAX_QUESTIONS


def _max_clarifications() -> int:
    """Cap on clarification items kept (env-overridable)."""
    raw = os.getenv(_ENV_MAX_CLARIFICATIONS, "").strip()
    if not raw:
        return _DEFAULT_MAX_CLARIFICATIONS
    try:
        value = int(raw)
    except ValueError:
        logger.warning(
            "[intent_frame] %s=%r is not an int — using %d",
            _ENV_MAX_CLARIFICATIONS, raw, _DEFAULT_MAX_CLARIFICATIONS,
        )
        return _DEFAULT_MAX_CLARIFICATIONS
    return value if value > 0 else _DEFAULT_MAX_CLARIFICATIONS


def _build_prompt(question: str) -> str:
    """Render the single-call decomposition prompt for ``question``."""
    return _PROMPT_TEMPLATE.format(question=(question or "").strip())


def _extract_json_object(text: str) -> dict[str, Any]:
    """Parse the first JSON object out of an LLM reply.

    Tolerates a leading/trailing prose or ```json code fences by taking the
    span from the first ``{`` to the last ``}``. Raises ``IntentFrameError`` on
    any failure (fail-closed; never silently swallows a parse error).
    """
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise IntentFrameError(
            "intent-frame reply contained no JSON object"
        )
    blob = text[start:end + 1]
    try:
        parsed = json.loads(blob)
    except json.JSONDecodeError as exc:
        raise IntentFrameError(
            f"intent-frame reply was not valid JSON: {exc}"
        ) from exc
    if not isinstance(parsed, dict):
        raise IntentFrameError(
            "intent-frame JSON was not an object"
        )
    return parsed


def _coerce_str_list(value: Any, cap: int) -> list[str]:
    """Coerce a JSON value into a deduped list of non-empty stripped strings.

    Accepts a list (items stringified) or a single string (wrapped). Order is
    preserved; duplicates (case-insensitive) are dropped; the result is capped.
    """
    if value is None:
        return []
    items: list[Any]
    if isinstance(value, str):
        items = [value]
    elif isinstance(value, (list, tuple)):
        items = list(value)
    else:
        return []

    out: list[str] = []
    seen: set[str] = set()
    for item in items:
        text = str(item).strip()
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(text)
        if len(out) >= cap:
            break
    return out


def _first_present(obj: dict[str, Any], keys: tuple[str, ...]) -> Any:
    """Return the value of the first present alias key, else None."""
    for key in keys:
        if key in obj:
            return obj[key]
    return None


def _normalize_domain(value: Any) -> str:
    """Lowercase / collapse-whitespace a free-text domain label; ``general``
    when blank or absent (never a closed-enum gate)."""
    text = " ".join(str(value or "").split()).strip().lower()
    return text or _DEFAULT_DOMAIN


def decompose_intent_frame(question: str, llm: LlmFn) -> IntentFrame:
    """Run the single GLM-5.2 intent decomposition and return a typed frame.

    This is the pure decomposition — it does NOT consult the flag (the flag
    gate lives in ``run_intent_frame``). It is FAIL-CLOSED: a blank/None reply,
    unparseable JSON, or a frame with zero questions raises ``IntentFrameError``.
    Emits the firing canary ONLY after a successful, non-empty decomposition.

    Args:
        question: the raw research prompt.
        llm: injected ``Callable[[str], str]`` GLM-5.2 policy (one call total).

    Returns:
        IntentFrame with >= 1 question.

    Raises:
        IntentFrameError: enabled-but-empty (the silent-no-op trip).
    """
    raw = llm(_build_prompt(question))
    if not isinstance(raw, str) or not raw.strip():
        raise IntentFrameError(
            "intent-frame llm returned an empty / None response"
        )

    parsed = _extract_json_object(raw)
    questions = _coerce_str_list(
        _first_present(parsed, _QUESTION_KEYS), _max_questions()
    )
    clarification_needed = _coerce_str_list(
        _first_present(parsed, _CLARIFY_KEYS), _max_clarifications()
    )
    domain = _normalize_domain(parsed.get(_DOMAIN_KEY))

    if not questions:
        raise IntentFrameError(
            "intent-frame decomposition produced zero questions"
        )

    frame = IntentFrame(
        questions=questions,
        domain=domain,
        clarification_needed=clarification_needed,
    )
    # FIRING CANARY — emitted ONLY here, after a real successful decomposition,
    # reporting real runtime counts (not a flag/import/config echo). Propagates
    # to the run-log stdout handler (logging.basicConfig INFO in the integrator).
    logger.info(
        "[intent_frame] #scope IntentFrame fired: questions=%d domain=%s clarify=%d",
        len(frame.questions), frame.domain, len(frame.clarification_needed),
    )
    return frame


def run_intent_frame(question: str, llm: LlmFn) -> IntentFrame | None:
    """Integrator entry point: the advisory intent-frame step.

    Returns ``None`` iff the step is disabled (default) — the legacy scope path
    runs unchanged, the ``llm`` is never called, zero spend. When enabled it
    decomposes via :func:`decompose_intent_frame` and is FAIL-CLOSED
    (``IntentFrameError`` propagates — the integrator must NOT catch-and-fall-
    back to legacy, or the wired guarantee dies).

    Args:
        question: the raw research prompt.
        llm: injected GLM-5.2 ``Callable[[str], str]`` (built by the integrator).

    Returns:
        IntentFrame when enabled and decomposition succeeds; ``None`` when
        disabled.
    """
    if not intent_frame_enabled():
        return None
    return decompose_intent_frame(question, llm)
