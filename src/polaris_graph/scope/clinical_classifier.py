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

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

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
