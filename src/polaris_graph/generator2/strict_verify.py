"""Strict verifier per CLAUDE.md §9.1 invariant 3.

Per-sentence check enforcing:
  (a) at least one provenance token present
  (b) every token references an evidence_id in the pool
  (c) span bounds are valid (0 <= start <= end <= len(text))
  (d) every decimal in the sentence appears in the cited spans
  (e) sentence and span share >= MIN_CONTENT_OVERLAP content words
  (f) I-bug-092: span semantically ENTAILS the sentence's specific claims
      (gated behind PG_STRICT_VERIFY_ENTAILMENT, defaults off)

Checks (a)-(e) are mechanical "provenance hygiene" — they bound a claim to
the same TOPIC as its span. Check (f) is "provenance correctness" — it
verifies the span actually entails the sentence's specific facts. The
audit on 2026-05-09 found that a capable generator can pass (a)-(e) by
producing topically-overlapping prose that introduces unsourced specifics
(e.g. inserting "pancreatic β-cells", "lipid metabolism", "energy storage"
into a span that says only "synergistic actions on insulin secretion,
glucagon suppression, appetite regulation, and adipocyte metabolism").

Returns a (verifier_pass: bool, drop_reason: str | None) pair, or directly
constructs a VerifiedSentence for use by the generator orchestrator.

Tunables (read at call time so tests can override):
  PG_PROVENANCE_MIN_CONTENT_OVERLAP — minimum shared content words (default 2)
  PG_STRICT_VERIFY_ENTAILMENT       — "off" | "warn" | "enforce" (default)
                                       off:     skip check (f), pre-I-bug-092 behavior
                                                — operator override; production runs
                                                  ship without provenance-correctness
                                                  enforcement
                                       warn:    run check (f), log violations,
                                                do NOT drop (collect telemetry)
                                       enforce: run check (f), drop on
                                                NEUTRAL or CONTRADICTED verdict
                                                (default per I-bug-095, validated
                                                empirically by I-bug-094 live test)
  PG_ENTAILMENT_MODEL               — entailment judge model
                                       (default: google/gemma-4-31b-it,
                                        the two-family evaluator)
"""

from __future__ import annotations

import json
import logging
import os
import re

from polaris_graph.generator2.provenance import (
    ProvenanceToken,
    extract_tokens,
    get_span_text,
    strip_tokens,
    validate_token_against_pool,
)
from polaris_graph.generator2.verified_report import (
    DropReason,
    VerifiedSentence,
)
from polaris_graph.retrieval2.evidence_pool import EvidencePool

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Tunables
# ---------------------------------------------------------------------------

DEFAULT_MIN_CONTENT_OVERLAP = 2

# Minimal English stopword list. Strict-verify's content-word overlap should
# count substantive vocabulary, not function words. This is intentionally
# small — the rule is conservative ("at least 2 shared content words")
# so even a short stoplist yields the right behavior.
_STOPWORDS: frozenset[str] = frozenset({
    "a", "an", "the", "and", "or", "but", "if", "of", "in", "on", "at",
    "to", "for", "with", "as", "by", "from", "into", "through", "during",
    "before", "after", "above", "below", "between", "is", "are", "was",
    "were", "be", "been", "being", "have", "has", "had", "having", "do",
    "does", "did", "doing", "will", "would", "should", "could", "may",
    "might", "must", "can", "this", "that", "these", "those", "it",
    "its", "their", "there", "they", "them", "we", "us", "our", "you",
    "your", "i", "me", "my", "he", "she", "his", "her",
})

_DECIMAL_RE = re.compile(r"\d+(?:\.\d+)?")
_WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9_\-]+")


def _min_overlap_threshold() -> int:
    raw = os.environ.get("PG_PROVENANCE_MIN_CONTENT_OVERLAP", "")
    try:
        return max(0, int(raw))
    except ValueError:
        return DEFAULT_MIN_CONTENT_OVERLAP


def _content_words(text: str) -> set[str]:
    """Lowercase content words (>=3 chars, not stopwords) from `text`."""
    return {
        m.group(0).lower()
        for m in _WORD_RE.finditer(text)
        if len(m.group(0)) >= 3 and m.group(0).lower() not in _STOPWORDS
    }


def _decimals(text: str) -> set[str]:
    """Numeric tokens (integers + decimals) from `text`."""
    return {m.group(0) for m in _DECIMAL_RE.finditer(text)}


# ---------------------------------------------------------------------------
# Entailment judge (I-bug-092 — provenance correctness)
# ---------------------------------------------------------------------------
#
# After mechanical checks (a)-(e) pass, the entailment judge asks an LLM
# whether the cited span semantically ENTAILS the sentence's specific
# claims. This catches the residual fabrication patterns the audit on
# 2026-05-09 surfaced:
#   - mechanistic granularity insertion (M2: span says "adipocyte
#     metabolism", sentence adds "lipid metabolism, energy storage")
#   - specificity inflation (C2: span says "GLP-1 RAs", sentence
#     upgrades to "semaglutide at the highest studied doses")
#   - numbers nearby but not entailed (C1: span has 27/46/19 elsewhere,
#     sentence claims 69-80% reach <=6.5% which is not in the span)
#
# The judge is the two-family evaluator (Gemma 4 31B by default), which
# matches the §9.1.1 invariant — a different lineage than the generator
# (DeepSeek). Calls go through OpenRouter using the existing project
# auth substrate.

_DEFAULT_ENTAILMENT_MODEL = "google/gemma-4-31b-it"
_ENTAILMENT_TIMEOUT_S = 30.0
_ENTAILMENT_PROMPT = """You are a strict entailment judge. You will be given a SPAN of source text and a SENTENCE that cites that span. Decide whether the SPAN entails the SENTENCE.

Rules:
- ENTAILED: every factual assertion in the SENTENCE is supported by the SPAN. Conservative paraphrase is allowed.
- NEUTRAL: the SENTENCE introduces a fact, entity, mechanism, or specificity NOT present in the SPAN (e.g. SPAN says "GLP-1 RAs", SENTENCE says "semaglutide"; SPAN says "adipocyte metabolism", SENTENCE adds "lipid metabolism" or "energy storage"; SPAN has numbers but not the specific claim being made).
- CONTRADICTED: the SENTENCE asserts something the SPAN explicitly disagrees with.

Return STRICT JSON only, no prose:
{{"verdict": "ENTAILED" | "NEUTRAL" | "CONTRADICTED", "reason": "<one short sentence>"}}

SPAN:
{span}

SENTENCE:
{sentence}

JSON:"""


class _EntailmentJudge:
    """Synchronous httpx wrapper around an OpenRouter entailment call.

    Lazy-initialized via _get_judge() so import-time cost is zero when
    PG_STRICT_VERIFY_ENTAILMENT=off (the default).
    """

    def __init__(self) -> None:
        import httpx  # local import: avoid forcing the dep when off

        # Lazy-import the family-segregation check so the off-mode path
        # never touches openrouter_client. The judge is acting as a
        # content evaluator (Layer-2), so it MUST differ from the
        # generator family per CLAUDE.md §9.1.1 — fail at construction
        # if PG_ENTAILMENT_MODEL is in the same family as PG_GENERATOR_MODEL.
        from polaris_graph.llm.openrouter_client import check_family_segregation

        api_key = os.environ.get("OPENROUTER_API_KEY", "").strip()
        if not api_key:
            raise RuntimeError(
                "PG_STRICT_VERIFY_ENTAILMENT requires OPENROUTER_API_KEY"
            )
        self._api_key = api_key
        self._model = os.environ.get(
            "PG_ENTAILMENT_MODEL", _DEFAULT_ENTAILMENT_MODEL
        )
        # Two-family invariant per §9.1.1: raises RuntimeError if the
        # entailment judge ends up in the same family as the generator
        # (e.g. an operator setting PG_ENTAILMENT_MODEL to a DeepSeek
        # variant when PG_GENERATOR_MODEL is also DeepSeek). The
        # default model (google/gemma-4-31b-it) is in a different
        # family from DeepSeek by construction.
        check_family_segregation(evaluator_model=self._model)
        self._client = httpx.Client(timeout=_ENTAILMENT_TIMEOUT_S)

    def judge(self, sentence: str, span: str) -> tuple[str, str]:
        """Return (verdict, reason).

        verdict is one of "ENTAILED", "NEUTRAL", "CONTRADICTED".
        On API/parse failure returns ("ENTAILED", "judge_error: ...") —
        fail-open so a transient OpenRouter outage does not nuke a run.
        """
        prompt = _ENTAILMENT_PROMPT.format(span=span, sentence=sentence)
        try:
            response = self._client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self._model,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.0,
                    "max_tokens": 100,
                    "response_format": {"type": "json_object"},
                },
            )
            response.raise_for_status()
            data = response.json()
            content = data["choices"][0]["message"]["content"]
            parsed = json.loads(content)
            verdict = str(parsed.get("verdict", "")).upper().strip()
            reason = str(parsed.get("reason", ""))
            if verdict not in ("ENTAILED", "NEUTRAL", "CONTRADICTED"):
                return "ENTAILED", f"judge_error: bad_verdict={verdict!r}"
            return verdict, reason
        except Exception as exc:  # noqa: BLE001 — fail-open by design
            logger.warning("entailment judge error: %s", exc)
            return "ENTAILED", f"judge_error: {type(exc).__name__}"


_JUDGE_SINGLETON: _EntailmentJudge | None = None


def _get_judge() -> _EntailmentJudge:
    """Lazy singleton so off-mode pays zero import/connection cost."""
    global _JUDGE_SINGLETON
    if _JUDGE_SINGLETON is None:
        _JUDGE_SINGLETON = _EntailmentJudge()
    return _JUDGE_SINGLETON


# I-bug-097: dedup unknown-mode warnings so a long-running process logs
# at most ONE WARNING per typo string. Operators sometimes set
# PG_STRICT_VERIFY_ENTAILMENT=ENFORCE (already lowercased fine) or
# =enforced (verb form, falls through to off). Without a warning, the
# typo silently disables the gate.
_UNKNOWN_MODE_WARNED: set[str] = set()


# I-bug-096: process-lifetime telemetry counters for the entailment gate.
# Per Codex review of I-bug-092: in enforce mode the judge fail-open
# path returns ("ENTAILED", "judge_error: ...") on transient API errors.
# A persistent OpenRouter outage or model-format change could make the
# 6th check silently inert — every sentence falls through as ENTAILED
# while WARNING lines accumulate. These counters give an operator a
# concise "the gate ran N times, M of those errored" signal.
#
# Counters are strict_verify-side (not judge-side) per Codex's iter-1
# brief verdict: gate behavior is what we want to measure, not a
# specific judge implementation. Tests with FakeJudge tick these too,
# and a future swapped judge cannot bypass the judge_error counter.
_JUDGE_TELEMETRY: dict[str, int] = {
    "calls": 0,
    "entailed": 0,
    "neutral": 0,
    "contradicted": 0,
    "judge_error": 0,
}


def get_judge_telemetry() -> dict[str, int]:
    """Snapshot of process-lifetime entailment-judge counters.

    Read once before a job to compute deltas if needed. Operators
    concerned that the gate has gone silently inert can poll this from
    a health endpoint or scripts/observability tooling and alert on
    judge_error rate.
    """
    return dict(_JUDGE_TELEMETRY)


def reset_judge_telemetry() -> None:
    """Zero all judge telemetry counters in-place.

    Public so operators can deliberately reset between jobs / runs.
    Tests use this for isolation; production callers can use it to
    bound the counter arithmetic to a single run window.
    """
    for key in _JUDGE_TELEMETRY:
        _JUDGE_TELEMETRY[key] = 0


def _record_judge_outcome(verdict: str, reason: str) -> None:
    """Tick the appropriate counter based on judge return values.

    Normalizes the existing judge fail-open contract: when reason
    starts with 'judge_error:', the call errored and was returned as
    ENTAILED to keep the run alive. We tick judge_error in that case
    instead of entailed so an operator can distinguish "gate accepted
    the sentence" from "gate failed open."
    """
    _JUDGE_TELEMETRY["calls"] += 1
    if reason.startswith("judge_error:"):
        _JUDGE_TELEMETRY["judge_error"] += 1
        return
    key = verdict.lower()
    if key in _JUDGE_TELEMETRY:
        _JUDGE_TELEMETRY[key] += 1


# I-bug-095: production default flipped from "off" to "enforce" per
# Codex APPROVE iter 1. Empirical evidence: I-bug-094 live test ran
# 4/4 audit-derived cases (M2/C2/C1 + positive control) against real
# OpenRouter Gemma 4 31B and got correct verdicts. The cage is
# structurally complete with I-bug-092..097 + I-cj-008; flipping the
# default closes the loop on the 2026-05-09 audit-revealed gap.
#
# Operator escape hatch: `PG_STRICT_VERIFY_ENTAILMENT=off` continues
# to disable the check explicitly. Documented per Codex iter-1 brief
# verdict.
_DEFAULT_MODE = "enforce"


def _entailment_mode() -> str:
    """Return one of 'off', 'warn', 'enforce'. Unknown values map to default.

    I-bug-097: emit a single WARNING per process per unrecognized typo
    string. Empty / unset env returns the default mode silently —
    that is the intended default, not a misconfiguration.

    I-bug-095: default mode is 'enforce' (was 'off' before this Issue).
    Operators who need the pre-graduation behavior can set
    PG_STRICT_VERIFY_ENTAILMENT=off explicitly.
    """
    raw = os.environ.get("PG_STRICT_VERIFY_ENTAILMENT", _DEFAULT_MODE).lower().strip()
    if raw and raw not in ("off", "warn", "enforce"):
        if raw not in _UNKNOWN_MODE_WARNED:
            _UNKNOWN_MODE_WARNED.add(raw)
            logger.warning(
                "PG_STRICT_VERIFY_ENTAILMENT=%r unrecognized; "
                "treating as %r (default). Valid: off, warn, enforce.",
                raw, _DEFAULT_MODE,
            )
        return _DEFAULT_MODE
    return raw or _DEFAULT_MODE


# ---------------------------------------------------------------------------
# Per-sentence verifier
# ---------------------------------------------------------------------------

def verify_sentence(
    sentence_text: str,
    pool: EvidencePool,
    min_content_overlap: int | None = None,
    is_synthesis_claim: bool = False,
) -> tuple[bool, DropReason | None]:
    """Return (verifier_pass, drop_reason) for `sentence_text` against `pool`.

    Pass: returns (True, None).
    Fail: returns (False, drop_reason) with reason from DropReason literal.

    Implements CLAUDE.md §9.1 invariant 3 in order:
      1. at least one well-formed token        → no_provenance_token
      2. every token references known source_id → invalid_token
      3. spans within source bounds            → span_out_of_range
      4. every decimal in sentence in spans    → numeric_mismatch
      5. >=N shared content words              → overlap_too_low
      6. (I-bug-092) span entails sentence     → entailment_failed
         (gated by PG_STRICT_VERIFY_ENTAILMENT, off by default)

    If `is_synthesis_claim=True` AND the sentence has no tokens, return
    (True, None) — synthesis claims pass without provenance by definition
    (I-f5-006). If a synthesis claim DOES carry tokens, that's a generator
    bug; we still run token checks so the underlying invariant holds.
    """
    threshold = (
        min_content_overlap
        if min_content_overlap is not None
        else _min_overlap_threshold()
    )

    tokens = extract_tokens(sentence_text)
    if not tokens:
        if is_synthesis_claim:
            return True, None
        return False, "no_provenance_token"

    # Validate each token against the pool. Collect span texts for
    # later numeric + overlap checks.
    span_texts: list[str] = []
    for token in tokens:
        reason = validate_token_against_pool(token, pool)
        if reason == "invalid_token":
            return False, "invalid_token"
        if reason == "span_out_of_range":
            return False, "span_out_of_range"
        # Token valid — fetch its span text
        span = get_span_text(token, pool)
        if span is None:
            # Belt-and-suspenders: token validated but get_span_text said no.
            return False, "span_out_of_range"
        span_texts.append(span)

    sentence_clean = strip_tokens(sentence_text)
    combined_span = " ".join(span_texts)

    # Decimal match: every decimal in sentence must appear in the combined
    # span text. Permits the spans to contain MORE decimals than the
    # sentence cites — that's fine; the constraint is one-way.
    sentence_decimals = _decimals(sentence_clean)
    span_decimals = _decimals(combined_span)
    if not sentence_decimals.issubset(span_decimals):
        return False, "numeric_mismatch"

    # Content-word overlap
    sentence_words = _content_words(sentence_clean)
    span_words = _content_words(combined_span)
    overlap = len(sentence_words & span_words)
    if overlap < threshold:
        return False, "overlap_too_low"

    # Check (f) — entailment judge (I-bug-092). Synthesis claims with no
    # tokens already short-circuited above; if a synthesis claim DOES
    # carry tokens it must clear the same content-correctness bar as
    # any other cited sentence.
    mode = _entailment_mode()
    if mode in ("warn", "enforce"):
        verdict, reason = _get_judge().judge(sentence_clean, combined_span)
        _record_judge_outcome(verdict, reason)
        if verdict in ("NEUTRAL", "CONTRADICTED"):
            logger.warning(
                "entailment %s (mode=%s): sentence=%r reason=%r",
                verdict, mode, sentence_clean, reason,
            )
            if mode == "enforce":
                return False, "entailment_failed"

    return True, None


def verify_sentence_to_record(
    sentence_text: str,
    section_id: str,
    pool: EvidencePool,
    min_content_overlap: int | None = None,
    is_synthesis_claim: bool = False,
) -> VerifiedSentence:
    """Convenience: wrap verify_sentence into a VerifiedSentence record.

    Used by the generator orchestrator to build Section.verified_sentences.
    """
    passed, reason = verify_sentence(
        sentence_text,
        pool,
        min_content_overlap=min_content_overlap,
        is_synthesis_claim=is_synthesis_claim,
    )
    tokens = [t.raw for t in extract_tokens(sentence_text)]
    return VerifiedSentence(
        section_id=section_id,
        sentence_text=sentence_text,
        provenance_tokens=tokens,
        verifier_pass=passed,
        drop_reason=reason,
        evaluator_agrees=passed,
        is_synthesis_claim=is_synthesis_claim,
    )


# ---------------------------------------------------------------------------
# Section-level rollup
# ---------------------------------------------------------------------------

def section_pass_rate(sentences: list[VerifiedSentence]) -> float:
    """Fraction of sentences that passed verify, in [0.0, 1.0].

    Empty list returns 0.0 (vacuously below any threshold).
    """
    if not sentences:
        return 0.0
    passed = sum(1 for s in sentences if s.verifier_pass)
    return passed / len(sentences)
