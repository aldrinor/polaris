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

# I-deepfix-001 (§9.1.8 anti-starvation, Codex diff-gate iter1 P0): this is the FOURTH live glm side
# judge (the W2 content-relevance escalation is DEFAULT-ON and run_gate_b force-enables it). GLM ignores
# reasoning.effort, so a provider that runs reasoning long can eat the whole max_tokens budget and blank
# the verdict. The shared leaf helper puts the PROVEN D8-Mirror NUMERIC reasoning cap
# (reasoning_cap << max_tokens) on a glm judge body; a non-glm model (e.g. a PG_RELEVANCE_MODEL=kimi
# override) keeps its byte-identical {effort} shape. Stdlib-light leaf import.
from src.polaris_graph.llm.judge_reasoning_block import build_judge_reasoning_block as _build_reasoning_block

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
# I-deepfix-001 (§9.1.8 anti-starvation, Codex diff-gate iter1 P0): the OLD default 256 STARVED the
# glm-5.2 reasoning judge — the reasoning burst ate the whole 256-token budget so message.content came
# back EMPTY (finish_reason=length). This judge fires by default via the W2 content-relevance escalation
# (PG_CONTENT_RELEVANCE_JUDGE default-ON, force-enabled at run_gate_b.py:1364), so the starvation hit
# every paid run. §9.1.8 "max_tokens ALWAYS go to the model REAL max": glm-5.2's mirror-chain MIN
# completion cap is 131072 — the SAME real cap the credibility / entailment / semantic-conflict side
# judges resolved from a LIVE OpenRouter read 2026-06-14 (_CREDIBILITY_MAX_TOKENS_CHAIN_MIN). max_tokens
# is a CAP billed by ACTUAL usage (~a few hundred tokens for a relevance verdict), so a generous cap is
# free insurance, never a pre-allocated spend. Env-overridable per LAW VI (PG_RELEVANCE_MAX_TOKENS). The
# numeric reasoning cap (build_judge_reasoning_block) then keeps the reasoning burst strictly below this
# so the JSON verdict always lands.
_DEFAULT_MAX_TOKENS = 131072
_DEFAULT_TIMEOUT_S = 30.0

# ─────────────────────────────────────────────────────────────────────────────
# I-deepfix-001 Item-12 (DNS resilience). The W2 content-relevance escalation is DEFAULT-ON and
# force-enabled by run_gate_b, so this per-citation judge fires on every paid run. A TRANSIENT DNS /
# name-resolution blip (getaddrinfo "Temporary failure in name resolution" -> httpx.ConnectError)
# previously fell straight through to the always-release SUPPORTED keep on the FIRST hit, silently
# dropping the relevance dimension for that citation (Item-12: ~5x/run, ~25s wasted each). Add a
# BOUNDED retry-with-backoff for DNS / transient-CONNECT faults ONLY. A parse / empty /
# unparseable-verdict / HTTP-status fault keeps the byte-identical single-attempt always-release path;
# a BudgetExceededError still propagates (never retried, never masked).
#
# FAITHFULNESS-NEUTRAL (§9.1 the faithfulness ENGINE is the only hard gate; §-1.3 weight-not-filter):
# the relevance label is NEVER the faithfulness gate — it runs ALONGSIDE strict_verify on cites that
# ALREADY cleared the hard gate, and its only downstream effect is to DEMOTE a citation's weight
# (never DROP the source). On retry exhaustion the SAME always-release SUPPORTED keep fires (existing
# behavior, unchanged). So the retry can only RECOVER a real verdict on a transient blip (which may
# DEMOTE = strengthen) or be a no-op; it never relaxes faithfulness and never drops a credible source.
# Env-driven per LAW VI (read at call time so the harness can toggle without re-import).
# ─────────────────────────────────────────────────────────────────────────────
_ENV_DNS_RETRY_ATTEMPTS = "PG_RELEVANCE_DNS_RETRY_ATTEMPTS"       # extra retries after the first attempt
_ENV_DNS_RETRY_BACKOFF_S = "PG_RELEVANCE_DNS_RETRY_BACKOFF_S"     # base backoff seconds (exponential)
_ENV_DNS_RETRY_BACKOFF_CAP_S = "PG_RELEVANCE_DNS_RETRY_BACKOFF_CAP_S"  # per-wait ceiling seconds
_DEFAULT_DNS_RETRY_ATTEMPTS = 2       # -> up to 3 total attempts (the task's "2-3x")
_DEFAULT_DNS_RETRY_BACKOFF_S = 1.0    # short backoff: 1s, 2s, ... (exponential, capped)
_DEFAULT_DNS_RETRY_BACKOFF_CAP_S = 10.0

# DNS / name-resolution / transient-connection markers (host-agnostic, lowercase substrings). Mirrors
# the connectivity subset of entailment_judge._RATE_LIMIT_CONNECTIVITY_MARKERS. A getaddrinfo failure
# surfaces as httpx.ConnectError wrapping socket.gaierror; the string markers catch the same fault when
# it arrives inside a differently-typed exception (e.g. a wrapped/re-raised transport error).
_DNS_CONNECT_MARKERS: tuple[str, ...] = (
    "getaddrinfo",
    "temporary failure in name resolution",
    "name or service not known",
    "nodename nor servname",
    "name resolution",
    "failed to resolve",
)


def _is_dns_or_transient_connect_error(exc: BaseException) -> bool:
    """True iff ``exc`` is a DNS / name-resolution / transient-CONNECT transport fault a bounded retry
    can heal — ``httpx.ConnectError`` / ``httpx.ConnectTimeout`` (a getaddrinfo failure surfaces here), a
    raw ``socket.gaierror``, or any exception whose type/string carries a DNS marker. A parse / empty /
    HTTP-status / read-timeout / bad-verdict fault returns False, so the caller keeps its single-attempt
    always-release path for those. Never raises (a predicate must never break the judge)."""
    try:
        import httpx  # local import: keep the OFF-path import cost zero
        if isinstance(exc, (httpx.ConnectError, httpx.ConnectTimeout)):
            return True
    except Exception:  # noqa: BLE001 — httpx import/type checks must never break the predicate
        pass
    try:
        import socket
        if isinstance(exc, socket.gaierror):
            return True
    except Exception:  # noqa: BLE001
        pass
    try:
        haystack = f"{type(exc).__name__}: {exc}".lower()
        return any(marker in haystack for marker in _DNS_CONNECT_MARKERS)
    except Exception:  # noqa: BLE001
        return False


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

# I-wire-001 W2 (#1311): the CONTENT-RELEVANCE (question<->passage) prompt. This
# is a DIFFERENT task from the citation-claim prompt above: at the post-fetch /
# pre-tier seam there are NO generated claims yet, only the research QUESTION, so
# the judge must decide whether a fetched passage is RELEVANT EVIDENCE for the
# question — NOT whether a span supports a claim. It MUST mirror the Qwen3-
# Reranker's question-passage semantics (the reranker asks "does the Document
# meet the Query") so the two stages judge the SAME thing and escalation is
# coherent. Reuses the SAME SUPPORTED/INSUFFICIENT/REFUTED label vocabulary so
# the W2 caller's mapping is unchanged (SUPPORTED=keep, INSUFFICIENT/REFUTED=
# demote). The {claim} key carries the research QUESTION; {span} carries the
# fetched passage (the format keys are reused for transport compatibility).
_CONTENT_RELEVANCE_PROMPT = (
    "You are a strict content-relevance judge for a research pipeline. You are "
    "given a research QUESTION and a PASSAGE of fetched source text. Decide "
    "whether the PASSAGE contains information that is RELEVANT EVIDENCE for "
    "answering the QUESTION.\n\n"
    "Return EXACTLY one label:\n"
    "- SUPPORTED: the PASSAGE contains substantive information that helps answer "
    "the QUESTION (facts, findings, data, or authoritative statements on the "
    "question's topic — a partial but on-point answer counts).\n"
    "- INSUFFICIENT: the PASSAGE is on the general topic but does NOT contain "
    "information that answers the QUESTION (topical-but-useless: navigation/"
    "boilerplate/marketing, a generic background sentence, or the right subject "
    "with no answering content).\n"
    "- REFUTED: the PASSAGE is off-topic / unrelated to the QUESTION, or is "
    "non-content chrome (cookie notice, login wall, ads).\n\n"
    "QUESTION:\n{claim}\n\nPASSAGE:\n{span}\n\n"
    'Respond with ONLY a JSON object: {{"label": "SUPPORTED|INSUFFICIENT|REFUTED", '
    '"reason": "<one short sentence>"}}'
)


def make_content_relevance_judge() -> "_RelevanceJudge":
    """Build a `_RelevanceJudge` wired with the content-relevance (question<->
    passage) prompt for I-wire-001 W2. Reuses the tested transport / budget
    ledger / family override / fail-to-KEEP path; only the prompt differs. NOT
    gated by PG_RELEVANCE_GATE (W2 is gated solely by PG_CONTENT_RELEVANCE_JUDGE)."""
    return _RelevanceJudge(prompt_template=_CONTENT_RELEVANCE_PROMPT)


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

    def __init__(self, prompt_template: str | None = None) -> None:
        # I-wire-001 W2 (#1311): an OPTIONAL prompt template lets a DIFFERENT
        # relevance task reuse this judge's tested transport (httpx client, budget
        # ledger, family-segregation override, fail-to-KEEP-on-error). Default =
        # the #1280 citation-claim prompt, so the existing path is BYTE-IDENTICAL.
        # The template must accept {claim} and {span} format keys.
        self._prompt_template = prompt_template or _RELEVANCE_PROMPT
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

    def _dns_retry_attempts(self) -> int:
        """I-deepfix-001 Item-12: extra retries after the first attempt on a DNS / transient-connect
        fault (env-driven per LAW VI; read at call time). A bad value falls back to the default."""
        try:
            return max(0, int(os.environ.get(_ENV_DNS_RETRY_ATTEMPTS, _DEFAULT_DNS_RETRY_ATTEMPTS)))
        except (TypeError, ValueError):
            return _DEFAULT_DNS_RETRY_ATTEMPTS

    def _dns_retry_wait_s(self, attempt: int) -> float:
        """I-deepfix-001 Item-12: exponential short backoff (base * 2**attempt) capped at the ceiling
        (env-driven per LAW VI). Returns >= 0.0; a bad env value falls back to the defaults."""
        try:
            base = float(os.environ.get(_ENV_DNS_RETRY_BACKOFF_S, _DEFAULT_DNS_RETRY_BACKOFF_S))
        except (TypeError, ValueError):
            base = _DEFAULT_DNS_RETRY_BACKOFF_S
        try:
            cap = float(os.environ.get(_ENV_DNS_RETRY_BACKOFF_CAP_S, _DEFAULT_DNS_RETRY_BACKOFF_CAP_S))
        except (TypeError, ValueError):
            cap = _DEFAULT_DNS_RETRY_BACKOFF_CAP_S
        return max(0.0, min(base * (2 ** attempt), cap))

    def judge(self, claim: str, span: str) -> "tuple[str, str]":
        """Return (label, reason). label is one of SUPPORTED/INSUFFICIENT/REFUTED.

        On any transport/parse/empty fault -> ("SUPPORTED", "judge_error: <reason>"): the
        citation already cleared the strict_verify hard gate, so declining to add the
        relevance dimension keeps the pre-existing verified state (always-release; never a
        runtime demotion or hold on a judge error)."""
        prompt = self._prompt_template.format(claim=claim, span=span)
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
            # I-deepfix-001 (§9.1.8): a glm judge gets a NUMERIC reasoning cap (reasoning_cap << max_tokens)
            # so a provider that runs reasoning long cannot blank the verdict; a non-glm model (e.g. a
            # PG_RELEVANCE_MODEL=kimi override) keeps the {effort} shape. Reasoning stays ON either way.
            "reasoning": _build_reasoning_block(self._model, effort, max_tokens),
        }
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        started = time.monotonic()
        # I-deepfix-001 Item-12 (DNS resilience): a bounded SAME-endpoint retry-with-backoff around the
        # POST+parse. ONLY a DNS / transient-connect fault is retried (a getaddrinfo blip that would
        # otherwise waste ~25s and silently drop the relevance dimension); every OTHER fault keeps the
        # byte-identical single-attempt always-release path, and BudgetExceededError propagates. On retry
        # exhaustion the SAME always-release SUPPORTED keep fires — faithfulness-neutral (this label is
        # never the hard gate; it only DEMOTES weight on an already-verified cite, never drops a source).
        attempts = self._dns_retry_attempts()
        last_exc: Optional[BaseException] = None
        for attempt in range(attempts + 1):
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
                last_exc = exc
                # Retry ONLY a DNS / transient-connect blip; a parse / empty / HTTP-status / bad-verdict
                # fault keeps the single-attempt always-release path (byte-identical to pre-fix).
                if attempt < attempts and _is_dns_or_transient_connect_error(exc):
                    wait = self._dns_retry_wait_s(attempt)
                    logger.warning(
                        "[relevance] DNS/transient-connect fault -> retry %d/%d in %.1fs: %s",
                        attempt + 1, attempts, wait, str(exc)[:120],
                    )
                    if wait > 0:
                        time.sleep(wait)
                    continue
                dur_ms = int((time.monotonic() - started) * 1000)
                logger.warning(
                    "[relevance] judge transport/parse fault (%dms) -> SUPPORTED keep: %s",
                    dur_ms, exc,
                )
                return (LABEL_SUPPORTED, f"judge_error: {type(exc).__name__}:{str(exc)[:120]}")
        # Unreachable in the current flow (every loop iteration returns or continues, and the final
        # attempt's except returns), but keep a fail-open-KEEP backstop so a future refactor can never
        # strand the caller on a runtime fault. §-1.3 always-release preserved.
        dur_ms = int((time.monotonic() - started) * 1000)
        logger.warning(
            "[relevance] judge retry loop exhausted (%dms) -> SUPPORTED keep: %s",
            dur_ms, last_exc,
        )
        return (
            LABEL_SUPPORTED,
            f"judge_error: {type(last_exc).__name__ if last_exc else 'unknown'}:{str(last_exc)[:120]}",
        )


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
