"""Clinical-question scope classifier — regex layer.

Per slice 001 architecture proposal §"Two-layer classifier (regex first,
LLM fallback)". This module ships PR 3 (regex layer); PR 4 adds LLM
fallback that runs only when regex returns 'uncertain'.

Layers (in order):
    1. Refusal-bait detection — short-circuits to ScopeClass(value=NULL)
       and a refused signal. Caller routes to status='refused'.
    2. PICO pattern matching — first-match-wins across efficacy/safety/
       diagnosis/prognosis patterns.
    3. Out-of-scope marker matching — explicit non-clinical topics.
    4. Fallback: ScopeClass(value='uncertain', confidence=0.0,
       provenance='regex'). Caller invokes LLM fallback in PR 4.

Pattern data lives in patterns/*.yaml so the regex set is version-
controlled separately from code. Patterns are compiled lazily at first
use and cached.

No I/O, no network, deterministic given the YAML data.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Callable, Protocol

import yaml

from polaris_graph.scope.scope_decision import ScopeClass

PATTERNS_DIR = Path(__file__).parent / "patterns"


@dataclass(frozen=True)
class _CompiledPattern:
    name: str
    klass: str | None  # ScopeClassValue for PICO; None for refusal/oos
    regex: re.Pattern[str]


@dataclass(frozen=True)
class RegexClassifyResult:
    """Result of regex-layer classification.

    Three mutually exclusive outcomes:
      - refused=True  → caller routes to ScopeStatus='refused'
      - scope_class.value == 'out_of_scope' → status='out_of_scope'
      - scope_class.value == 'uncertain' → caller invokes LLM fallback
      - scope_class.value in clinical_*  → caller proceeds to ambiguity detection
    """

    scope_class: ScopeClass
    refused: bool
    refusal_pattern: str | None  # name of matched refusal-bait pattern, or None


def _load_yaml(filename: str) -> dict:
    path = PATTERNS_DIR / filename
    if not path.is_file():
        raise FileNotFoundError(f"pattern file missing: {path}")
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


@lru_cache(maxsize=1)
def _pico_patterns() -> list[_CompiledPattern]:
    data = _load_yaml("pico_patterns.yaml")
    out: list[_CompiledPattern] = []
    for entry in data.get("patterns", []):
        out.append(_CompiledPattern(
            name=entry["name"],
            klass=entry["class"],
            regex=re.compile(entry["pattern"], re.IGNORECASE),
        ))
    return out


@lru_cache(maxsize=1)
def _refusal_patterns() -> list[_CompiledPattern]:
    data = _load_yaml("out_of_scope_patterns.yaml")
    out: list[_CompiledPattern] = []
    for entry in data.get("refusal_bait", []):
        out.append(_CompiledPattern(
            name=entry["name"],
            klass=None,
            regex=re.compile(entry["pattern"], re.IGNORECASE),
        ))
    return out


@lru_cache(maxsize=1)
def _out_of_scope_patterns() -> list[_CompiledPattern]:
    data = _load_yaml("out_of_scope_patterns.yaml")
    out: list[_CompiledPattern] = []
    for entry in data.get("out_of_scope", []):
        out.append(_CompiledPattern(
            name=entry["name"],
            klass="out_of_scope",
            regex=re.compile(entry["pattern"], re.IGNORECASE),
        ))
    return out


def regex_classify(normalized_text: str) -> RegexClassifyResult:
    """Classify a normalized question via regex layer only.

    Args:
        normalized_text: question text post-normalization (NFC, whitespace-
                         collapsed, control-stripped). Pass NormalizedQuestion.normalized.

    Returns:
        RegexClassifyResult with refused / clinical / out_of_scope / uncertain.

    Order:
      1. Check refusal-bait → if hit, return refused=True.
      2. Check PICO clinical patterns → if hit, return clinical_*.
      3. Check out-of-scope markers → if hit, return out_of_scope.
      4. Otherwise → return uncertain (caller hands off to LLM fallback).
    """
    if not isinstance(normalized_text, str):
        raise TypeError(
            f"regex_classify expected str, got {type(normalized_text).__name__}"
        )

    # 1. Refusal-bait first (security: don't engage with adversarial framing)
    for p in _refusal_patterns():
        if p.regex.search(normalized_text):
            return RegexClassifyResult(
                scope_class=ScopeClass(
                    value="out_of_scope",  # placeholder; refused=True is the real signal
                    confidence=1.0,
                    provenance="regex",
                    matched_pattern=p.name,
                ),
                refused=True,
                refusal_pattern=p.name,
            )

    # 2. PICO clinical patterns
    for p in _pico_patterns():
        if p.regex.search(normalized_text):
            return RegexClassifyResult(
                scope_class=ScopeClass(
                    value=p.klass,  # type: ignore[arg-type]
                    confidence=1.0,
                    provenance="regex",
                    matched_pattern=p.name,
                ),
                refused=False,
                refusal_pattern=None,
            )

    # 3. Out-of-scope markers
    for p in _out_of_scope_patterns():
        if p.regex.search(normalized_text):
            return RegexClassifyResult(
                scope_class=ScopeClass(
                    value="out_of_scope",
                    confidence=1.0,
                    provenance="regex",
                    matched_pattern=p.name,
                ),
                refused=False,
                refusal_pattern=None,
            )

    # 4. Uncertain — caller invokes LLM fallback (PR 4)
    return RegexClassifyResult(
        scope_class=ScopeClass(
            value="uncertain",
            confidence=0.0,
            provenance="regex",
            matched_pattern=None,
        ),
        refused=False,
        refusal_pattern=None,
    )


# ===========================================================================
# PR 4: LLM fallback layer
# ===========================================================================

LLM_PROMPT_TEMPLATE = """You are a clinical-research-question classifier. The user has typed:

{question}

Classify this question into EXACTLY ONE of:
  - clinical_efficacy   (asking whether a treatment helps/works)
  - clinical_safety     (asking about adverse effects/risks)
  - clinical_diagnosis  (asking about diagnostic accuracy/screening)
  - clinical_prognosis  (asking about survival/outcomes over time)
  - out_of_scope        (not a clinical research question)

Respond with ONLY a JSON object, no prose, no markdown fences:
{{"value": "<class>", "confidence": <float 0..1>, "reasoning": "<one sentence>"}}
"""


class LLMCompletionFn(Protocol):
    """Minimal interface for the LLM call. Tests inject mocks; production
    uses a thin wrapper around polaris_graph.llm.openrouter_client.
    """

    def __call__(self, prompt: str) -> str:
        ...


def _default_llm_completion(prompt: str) -> str:
    """Production LLM call — lazy import + low-temp small model.

    OpenRouterClient.generate is async; this sync helper runs it via
    asyncio.run. If we are already inside a running event loop (e.g. an
    async test or async FastAPI handler) we raise RuntimeError so the
    caller surfaces the misuse instead of silently returning "uncertain"
    via the outer try/except in llm_fallback_classify (LAW II — no
    silent fallback).
    """
    import asyncio

    from polaris_graph.llm.openrouter_client import OpenRouterClient

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        pass  # No running loop — safe to use asyncio.run
    else:
        raise RuntimeError(
            "_default_llm_completion called from an async context; "
            "callers in async code must invoke OpenRouterClient.generate "
            "directly with await, not through this sync wrapper."
        )

    client = OpenRouterClient()
    result = asyncio.run(
        client.generate(prompt=prompt, temperature=0.0, max_tokens=200)
    )
    return result.content if hasattr(result, "content") else str(result)


_VALID_LLM_CLASSES = {
    "clinical_efficacy",
    "clinical_safety",
    "clinical_diagnosis",
    "clinical_prognosis",
    "out_of_scope",
}


def _parse_llm_response(raw: str) -> tuple[str, float]:
    """Extract value + confidence from LLM JSON response.

    Robust to: leading/trailing whitespace, markdown code fences, prose
    wrappers. Returns ('uncertain', 0.0) if parsing fails entirely.
    """
    if not raw:
        return ("uncertain", 0.0)
    # Strip common markdown wrappers
    text = raw.strip()
    if text.startswith("```"):
        # Find the first { and last }
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1:
            text = text[start:end + 1]
    try:
        parsed = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        # Last-ditch: try to find any {...} substring
        match = re.search(r"\{[^{}]*\}", text, re.DOTALL)
        if not match:
            return ("uncertain", 0.0)
        try:
            parsed = json.loads(match.group(0))
        except (json.JSONDecodeError, ValueError):
            return ("uncertain", 0.0)
    if not isinstance(parsed, dict):
        return ("uncertain", 0.0)
    value = str(parsed.get("value", "")).strip()
    if value not in _VALID_LLM_CLASSES:
        return ("uncertain", 0.0)
    try:
        confidence = float(parsed.get("confidence", 0.5))
    except (TypeError, ValueError):
        confidence = 0.5
    confidence = max(0.0, min(1.0, confidence))
    return (value, confidence)


def llm_fallback_classify(
    normalized_text: str,
    *,
    completion_fn: Callable[[str], str] | None = None,
) -> ScopeClass:
    """Second-layer LLM classification for questions where regex returned uncertain.

    Args:
        normalized_text: question text post-normalization
        completion_fn: dependency-injectable LLM caller. Defaults to
                       _default_llm_completion (real OpenRouter call).
                       Tests pass mocks.

    Returns:
        ScopeClass with provenance="llm_fallback" and the LLM-derived value.
        Falls back to ScopeClass(value="uncertain", confidence=0.0) on ANY
        failure (no API key, network error, malformed response, etc.) so
        the pipeline degrades gracefully.
    """
    if not isinstance(normalized_text, str):
        raise TypeError(
            f"llm_fallback_classify expected str, got {type(normalized_text).__name__}"
        )

    fn = completion_fn or _default_llm_completion
    prompt = LLM_PROMPT_TEMPLATE.format(question=normalized_text)

    try:
        raw_response = fn(prompt)
    except Exception:
        # Graceful degradation — LLM unavailable, missing key, network error, etc.
        return ScopeClass(
            value="uncertain",
            confidence=0.0,
            provenance="llm_fallback",
            matched_pattern=None,
        )

    value, confidence = _parse_llm_response(raw_response)
    return ScopeClass(
        value=value,  # type: ignore[arg-type]
        confidence=confidence,
        provenance="llm_fallback",
        matched_pattern=None,
    )


def classify(
    normalized_text: str,
    *,
    completion_fn: Callable[[str], str] | None = None,
) -> RegexClassifyResult:
    """Full classifier pipeline: regex layer → LLM fallback if uncertain.

    The orchestrator helper for end-to-end use. Most callers should use
    this rather than regex_classify or llm_fallback_classify directly.

    Returns:
        RegexClassifyResult — same shape regardless of which layer answered.
        scope_class.provenance distinguishes ('regex' vs 'llm_fallback').
    """
    regex_result = regex_classify(normalized_text)
    if regex_result.refused:
        return regex_result
    if regex_result.scope_class.value != "uncertain":
        return regex_result

    # Hand off to LLM fallback
    llm_class = llm_fallback_classify(normalized_text, completion_fn=completion_fn)
    return RegexClassifyResult(
        scope_class=llm_class,
        refused=False,
        refusal_pattern=None,
    )
