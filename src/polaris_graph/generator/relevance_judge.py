"""SURE-RAG-style three-way per-citation relevance judge (I-beatboth-003, #1280).

WHY (helps both boards). ``strict_verify`` (provenance_generator) is relevance-BLIND:
invariant #3's ``>=2-content-word`` overlap (``PG_PROVENANCE_MIN_CONTENT_OVERLAP``) PASSES
a source that shares two incidental words without establishing the required RELATION —
the "off-topic-but-topical" case (right entity named, wrong relation). These off-topic
citations spike DeepTRACE citation-imprecision AND dilute DeepResearch-Bench-II relevance.

WHAT this module is. A thin, INJECTABLE, three-way per-citation judge that runs ALONGSIDE
strict_verify (never replacing it, never an input to ``is_verified`` or the six strict_verify
checks). It returns one of three LABELS per (sentence, cited-span) pair:

  * SUPPORTED   — the span establishes the required relation for the claim -> keep as a
                  support citation.
  * INSUFFICIENT — the span mentions the right entity WITHOUT establishing the required
                  relation -> DEMOTE the citation to "listed, not load-bearing"
                  (provenance_generator render layer drops it from the inline support set).
  * REFUTED     — the span CONTRADICTS the claim -> route to a contradiction flag (the
                  citation is removed from the support set; the sentence still ships).

CRITICAL faithfulness invariants (CLAUDE.md §-1.3 / §-1.4 + the #1280 brief):

  1. ALWAYS-RELEASE. This is a per-citation LABEL, NEVER a hold / abstain. SURE-RAG natively
     ABSTAINS below threshold; POLARIS does NOT import the abstain. The report ALWAYS ships.
  2. NEVER strand a statement uncited (minimum-retention). This module only LABELS; the
     provenance_generator render layer enforces the minimum-retention guard (demote only if
     >=1 support citation remains, else keep the citation + mark the statement weak).
  3. The faithfulness ENGINE (strict_verify / NLI / 4-role D8 / span-grounding) is the ONLY
     hard gate and is NEVER touched here. The relevance label is a NEW added dimension.
  4. Default-OFF + byte-identical when off. ``relevance_gate_enabled()`` defaults False; with
     the flag OFF the judge is NEVER instantiated and NO LLM call is made.
  5. Judge model + threshold env-configurable (LAW VI). Default GLM-5.2 via OpenRouter.
  6. Fail-loud means the HARNESS / acceptance fails on a silent no-op (the effect must FIRE
     in the real output) — it does NOT mean runtime report suppression. On a judge TRANSPORT
     / parse error at runtime the judge returns SUPPORTED (keep the cite the strict_verify gate
     already passed) + a reason, so always-release holds (a runtime error never demotes or
     holds; it only declines to add the relevance dimension for that one citation).

The judge is INJECTABLE via a callable ``relevance_judge_fn(claim, span) -> (label, reason)``
so the §-1.4 fail-loud replay harness can mock it deterministically with NO model spend.
"""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Callable, Optional

logger = logging.getLogger("polaris_graph.relevance_judge")

# ─────────────────────────────────────────────────────────────────────────────
# Public label taxonomy (NOT the NLI ENTAILED/NEUTRAL/CONTRADICTED taxonomy —
# this is the SURE-RAG relevance/answerability taxonomy, deliberately distinct).
# ─────────────────────────────────────────────────────────────────────────────
LABEL_SUPPORTED = "SUPPORTED"
LABEL_INSUFFICIENT = "INSUFFICIENT"
LABEL_REFUTED = "REFUTED"
_VALID_LABELS = frozenset({LABEL_SUPPORTED, LABEL_INSUFFICIENT, LABEL_REFUTED})

# The signature of an injectable judge: (claim_text, cited_span_text) -> (label, reason).
RelevanceJudgeFn = Callable[[str, str], "tuple[str, str]"]

# ─────────────────────────────────────────────────────────────────────────────
# Env knobs (LAW VI — zero hard-coding). Read at call time so tests / the harness
# can toggle without re-import.
# ─────────────────────────────────────────────────────────────────────────────
_ENV_FLAG = "PG_RELEVANCE_GATE"  # master ON/OFF; default OFF -> byte-identical
_ENV_MODEL = "PG_RELEVANCE_MODEL"  # judge model; default GLM-5.2 via OpenRouter
_ENV_REASONING_EFFORT = "PG_RELEVANCE_REASONING_EFFORT"
_ENV_MAX_TOKENS = "PG_RELEVANCE_MAX_TOKENS"
_ENV_TIMEOUT_S = "PG_RELEVANCE_TIMEOUT_S"
# Campaign override: all-GLM-5.2 single family. The relevance judge is an evaluator-family
# call; under all-GLM the generator IS GLM too, so check_family_segregation WOULD raise. The
# campaign deliberately overrides §9.1.1 (MASTER_PLAN all-GLM-5.2 single-family lock). This
# flag rides the SAME documented override rather than a new silent bypass: when set, the
# relevance judge SKIPS the family-segregation guard. Default 0 -> guard stays ON.
_ENV_ALLOW_SAME_FAMILY = "PG_RELEVANCE_ALLOW_SAME_FAMILY"

# Conservative defaults. The model default is the campaign judge (GLM-5.2 via OpenRouter).
# Per CLAUDE.md §9.1.8 the EXACT OpenRouter slug must be reconciled against /api/v1/models
# before any LIVE run; the harness mocks the judge so the slug is not load-bearing here.
_DEFAULT_MODEL = "z-ai/glm-5.2"
_DEFAULT_REASONING_EFFORT = "high"
_DEFAULT_MAX_TOKENS = 256
_DEFAULT_TIMEOUT_S = 30.0


def relevance_gate_enabled() -> bool:
    """True iff the SURE-RAG relevance gate is ON (``PG_RELEVANCE_GATE`` truthy).

    Default OFF -> the per-citation labeling block is skipped entirely and the verify ->
    render path is byte-identical to HEAD. Read at call time (no import-time capture) so the
    harness can flip it per-case."""
    v = os.getenv(_ENV_FLAG, "0").strip().lower()
    return v in ("1", "true", "yes", "on", "enabled")


def _allow_same_family() -> bool:
    v = os.getenv(_ENV_ALLOW_SAME_FAMILY, "0").strip().lower()
    return v in ("1", "true", "yes", "on", "enabled")


def normalize_label(raw: object) -> Optional[str]:
    """Coerce a judge's raw verdict string to one of the three canonical labels, or None
    when it is unrecognizable (the caller then treats it as a judge error -> SUPPORTED keep).

    Accepts case-insensitive Supported/Insufficient/Refuted plus a few obvious synonyms
    seen from reasoning models (e.g. "support", "irrelevant", "contradicted")."""
    if raw is None:
        return None
    s = str(raw).strip().upper()
    if not s:
        return None
    if s in _VALID_LABELS:
        return s
    if s.startswith("SUPPORT"):
        return LABEL_SUPPORTED
    if s.startswith("INSUFFICIENT") or s.startswith("IRRELEVANT") or s.startswith("OFF"):
        return LABEL_INSUFFICIENT
    if s.startswith("REFUT") or s.startswith("CONTRADICT"):
        return LABEL_REFUTED
    return None


# ─────────────────────────────────────────────────────────────────────────────
# The relevance prompt — SURE-RAG taxonomy, distinct from the NLI entailment prompt.
# ─────────────────────────────────────────────────────────────────────────────
_RELEVANCE_PROMPT = (
    "You are a strict citation-relevance judge. You are given a CLAIM and a SPAN of source "
    "text that is cited to support that claim. Decide whether the SPAN establishes the "
    "specific RELATION the CLAIM asserts.\n\n"
    "Return EXACTLY one label:\n"
    "- SUPPORTED: the SPAN establishes the relation the CLAIM asserts (a conservative "
    "paraphrase counts).\n"
    "- INSUFFICIENT: the SPAN mentions the right entity or topic but does NOT establish the "
    "required relation (right entity, wrong relation — off-topic-but-topical).\n"
    "- REFUTED: the SPAN contradicts the CLAIM.\n\n"
    "CLAIM:\n{claim}\n\nSPAN:\n{span}\n\n"
    'Respond with ONLY a JSON object: {{"label": "SUPPORTED|INSUFFICIENT|REFUTED", '
    '"reason": "<one short sentence>"}}'
)


def _extract_first_json_object(content: object) -> dict:
    """Pull the first ``{...}`` JSON object out of a model response that may prepend
    reasoning text. Mirrors entailment_judge._extract_first_json_object intent."""
    text = content if isinstance(content, str) else str(content or "")
    start = text.find("{")
    if start < 0:
        return {}
    depth = 0
    for i in range(start, len(text)):
        c = text[i]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                try:
                    obj = json.loads(text[start:i + 1])
                    return obj if isinstance(obj, dict) else {}
                except (ValueError, TypeError):
                    return {}
    return {}


class _RelevanceJudge:
    """Synchronous httpx wrapper around an OpenRouter relevance call.

    Lazy-initialized + only ever constructed when ``relevance_gate_enabled()`` is True AND
    no judge fn was injected, so import-time / OFF-path cost is zero. Single-attempt + simple
    by design (this is a per-citation LABEL, not the hard gate); a runtime transport/parse
    fault returns SUPPORTED (keep the strict_verify-passed cite) so always-release holds."""

    def __init__(self) -> None:
        api_key = os.environ.get("OPENROUTER_API_KEY", "").strip()
        if not api_key:
            raise RuntimeError(
                f"{_ENV_FLAG} requires OPENROUTER_API_KEY (the relevance judge calls OpenRouter)"
            )
        self._api_key = api_key
        base_url = os.environ.get(
            "OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"
        ).rstrip("/")
        self._endpoint = f"{base_url}/chat/completions"
        self._model = os.environ.get(_ENV_MODEL, _DEFAULT_MODEL)
        # Two-family invariant (§9.1.1): the relevance judge is an evaluator-family call. Under
        # the all-GLM-5.2 campaign override the generator IS GLM too, so the guard WOULD raise.
        # Ride the SAME documented override (PG_RELEVANCE_ALLOW_SAME_FAMILY) — never a silent
        # bypass. Default: the guard runs and fails loud on an un-overridden same-family config.
        if not _allow_same_family():
            from src.polaris_graph.llm.openrouter_client import (  # noqa: PLC0415
                check_family_segregation,
            )
            check_family_segregation(evaluator_model=self._model)
        else:
            logger.info(
                "[relevance] %s set: skipping check_family_segregation under the "
                "all-GLM single-family campaign override", _ENV_ALLOW_SAME_FAMILY,
            )
        try:
            self._timeout_s = float(os.environ.get(_ENV_TIMEOUT_S, _DEFAULT_TIMEOUT_S))
        except (TypeError, ValueError):
            self._timeout_s = _DEFAULT_TIMEOUT_S
        self._client = self._build_client()

    def _build_client(self):
        import httpx  # local import: avoid forcing the dep on the OFF path

        from src.utils.shared_ssl_context import get_shared_ssl_context
        return httpx.Client(
            verify=get_shared_ssl_context(),
            timeout=httpx.Timeout(self._timeout_s),
        )

    def judge(self, claim: str, span: str) -> "tuple[str, str]":
        """Return (label, reason). label is one of SUPPORTED/INSUFFICIENT/REFUTED.

        On any transport/parse/empty fault -> ("SUPPORTED", "judge_error: <reason>"): the
        citation already cleared the strict_verify hard gate, so declining to add the
        relevance dimension keeps the pre-existing verified state (always-release; never a
        runtime demotion or hold on a judge error)."""
        prompt = _RELEVANCE_PROMPT.format(claim=claim, span=span)
        effort = (os.environ.get(_ENV_REASONING_EFFORT, "").strip().lower()
                  or _DEFAULT_REASONING_EFFORT)
        if effort not in ("low", "medium", "high", "xhigh"):
            effort = _DEFAULT_REASONING_EFFORT
        try:
            max_tokens = max(64, int(os.environ.get(_ENV_MAX_TOKENS, _DEFAULT_MAX_TOKENS)
                                     or _DEFAULT_MAX_TOKENS))
        except (TypeError, ValueError):
            max_tokens = _DEFAULT_MAX_TOKENS
        json_body = {
            "model": self._model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.0,
            "max_tokens": max_tokens,
            "reasoning": {"effort": effort},
        }
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        started = time.monotonic()
        try:
            response = self._client.post(self._endpoint, headers=headers, json=json_body)
            response.raise_for_status()
            data = response.json()
            # Record judge spend against the per-run budget cap + cost ledger, mirroring the
            # entailment judge. BudgetExceededError propagates (a cap breach aborts cleanly).
            try:
                from src.polaris_graph.llm import openrouter_client as _orc  # noqa: PLC0415
                _usage = (data or {}).get("usage") or {}
                _cost = _usage.get("cost")
                if _cost is not None:
                    _orc._add_run_cost(float(_cost))
                    _orc.check_run_budget(0)
            except ImportError:
                pass
            choices = (data or {}).get("choices") or []
            content = ""
            if choices:
                content = ((choices[0] or {}).get("message") or {}).get("content") or ""
            obj = _extract_first_json_object(content)
            label = normalize_label(obj.get("label"))
            reason = str(obj.get("reason") or "")[:200]
            if label is None:
                return (LABEL_SUPPORTED, f"judge_error: unparseable_verdict:{content[:80]!r}")
            return (label, reason)
        except Exception as exc:  # noqa: BLE001 — fail to SUPPORTED (keep cite), never hold
            from src.polaris_graph.llm.openrouter_client import (  # noqa: PLC0415
                BudgetExceededError,
            )
            if isinstance(exc, BudgetExceededError):
                raise
            dur_ms = int((time.monotonic() - started) * 1000)
            logger.warning(
                "[relevance] judge transport/parse fault (%dms) -> SUPPORTED keep: %s",
                dur_ms, exc,
            )
            return (LABEL_SUPPORTED, f"judge_error: {type(exc).__name__}:{str(exc)[:120]}")


_JUDGE_SINGLETON: Optional[_RelevanceJudge] = None


def _get_judge() -> _RelevanceJudge:
    """Process-lifetime singleton, built lazily on first use (only when the gate is ON and no
    judge fn was injected). Never constructed on the OFF path."""
    global _JUDGE_SINGLETON
    if _JUDGE_SINGLETON is None:
        _JUDGE_SINGLETON = _RelevanceJudge()
    return _JUDGE_SINGLETON


def reset_judge_singleton() -> None:
    """Test/harness hook: drop the cached judge so a re-config takes effect."""
    global _JUDGE_SINGLETON
    _JUDGE_SINGLETON = None


def judge_citation_relevance(
    claim: str,
    span: str,
    *,
    relevance_judge_fn: Optional[RelevanceJudgeFn] = None,
) -> "tuple[str, str]":
    """Label one (claim, cited-span) pair SUPPORTED / INSUFFICIENT / REFUTED.

    ``relevance_judge_fn`` (injectable, default None) lets the §-1.4 fail-loud harness mock
    the judge deterministically (NO model spend). When None, the live OpenRouter GLM-5.2 judge
    is used. The returned label is ALWAYS one of the three canonical labels (an unrecognizable
    verdict from an injected fn is coerced to SUPPORTED + a judge_error reason — keep the cite,
    never strand) so the caller never has to handle an out-of-taxonomy value."""
    if relevance_judge_fn is not None:
        try:
            raw_label, reason = relevance_judge_fn(claim, span)
        except Exception as exc:  # noqa: BLE001 — an injected fn fault keeps the cite
            return (LABEL_SUPPORTED, f"judge_error: injected_fn:{type(exc).__name__}")
        label = normalize_label(raw_label)
        if label is None:
            return (LABEL_SUPPORTED, f"judge_error: injected_unparseable:{raw_label!r}")
        return (label, str(reason or "")[:200])
    return _get_judge().judge(claim, span)
