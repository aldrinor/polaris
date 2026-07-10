"""I-deepfix-006-compose C1 — the ADDITIVE entailment verify path for cross-source SYNTHESIS.

WHY: ``depth_synthesis.synthesize_cross_source_findings`` re-grounds every synthesized cross-source
sentence through the FROZEN ``strict_verify`` engine, whose faithfulness floor is (a) a resolvable
provenance token, (b) every number in the sentence present in the cited span, and (c) a >=2 VERBATIM
content-word overlap between the sentence and the span. Leg (c) is LEXICAL: a genuine PARAPHRASE that
consolidates several corroborating spans into one clean news-style sentence (the whole point of the
synthesis pass) shares fewer than two verbatim content words with any single span and is DROPPED —
even though it is a faithful, number-matched, ENTAILED restatement of the evidence. That is the ~11
eligible baskets going 3->0 in the depth forensic.

THE FIX (this module, default-ON ``PG_SYNTH_ENTAILMENT_VERIFY``): an ADDITIVE second verify leg that
keeps a synthesized sentence iff (a) it resolves >=1 provenance token to a cited span in the SAME
basket-scoped pool, (b) every number in it appears in that span (the SAME numeric leg strict_verify
uses — the module-level ``_decimals_in`` / ``_numbers_in`` helpers, reused UNCHANGED), and (c) the
cited span ENTAILS the sentence via the existing directional NLI judge
(``consolidation_nli.entails_directional``) — IN PLACE of the >=2-verbatim-content-word test.

FAITHFULNESS (the frozen engine is UNTOUCHED — nothing here relaxes it):
  * ``strict_verify`` itself is never edited. This is a SEPARATE verify_fn whose kept sentences are
    UNIONED with strict_verify's (see ``make_entailment_union_verify_fn``) — strict_verify passes are
    ALWAYS kept; the entailment leg only ADDS entailed paraphrases the lexical leg dropped. It can
    never REMOVE a strict_verify pass, so the union is a pure superset (ADDITIVE, never a regression).
  * A paraphrase that MOVES / mangles a number fails the numeric leg and is DROPPED — the numeric
    invariant #3 is byte-for-byte the same predicate the frozen engine applies.
  * A NON-entailed paraphrase (the judge returns False) is DROPPED. Only a directionally-ENTAILED
    span->sentence relation is kept — the ALCE / DeepTRACE citation direction (span entails claim).
  * On a judge DEGRADE (the cross-encoder is unavailable / faulted => ``None``) we KEEP the sentence
    with a disclosed ``judge-unavailable`` LABEL (fix 5, operator 2026-07-10). The sentence is already
    provenance-resolved AND number-matched; the OLD >=2 lexical content-word fallback resurrected the
    killed lexical ghost on every judge outage, so it is removed. A degrade never lexical-gates and
    never silently keeps unlabeled — the label IS the faithfulness signal.

The default entailment judge is the SAME resident cross-encoder the consolidation leg already loads
(``entails_directional``, lazy) — ZERO new model / OpenRouter spend. Tests inject a deterministic
``entails_fn`` so the whole path is proven OFFLINE with no GPU / network.
"""
from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from src.polaris_graph.generator.provenance_generator import (
    _INTEGER_PERCENT_RE,
    _PLACEBO_COMPARATOR_RE,
    _THRESHOLD_RE,
    ProvenanceToken,
    SentenceVerification,
    _decimals_in,
    _numbers_in,
    _strip_dose_patterns,
    _verifier_cleaned_text,
    parse_provenance_tokens,
    split_into_sentences,
)

logger = logging.getLogger(__name__)

# Default-ON master gate (LAW VI). OFF => the union wrapper is never applied and the synthesis pass
# re-grounds through the FROZEN strict_verify ALONE (byte-identical to pre-C1).
_ENV_ENTAILMENT_VERIFY = "PG_SYNTH_ENTAILMENT_VERIFY"

# A resolved provenance token, for the dedup key of the union wrapper.
_EV_TOKEN_RE = re.compile(r"\[#ev:[A-Za-z0-9_]+:\d+-\d+\]")

# The soft-warning that marks a sentence KEPT by the entailment leg (read by the C3 D8-promote routing).
SYNTH_ENTAILMENT_SOFT_WARNING = "synthesis_entailment_verified"
# fix 5 (operator 2026-07-10): the disclosed label a KEPT sentence carries when the entailment judge was
# unavailable/degraded (number-matched + provenance-resolved but the semantic judge could not run).
SYNTH_ENTAILMENT_JUDGE_UNAVAILABLE = "synthesis_entailment_judge_unavailable"

# entails_fn(premise, hypothesis) -> True (entails) | False (does not) | None (judge unavailable / degrade)
EntailsFn = Callable[[str, str], Optional[bool]]


def entailment_verify_enabled() -> bool:
    """Default-ON. OFF (``PG_SYNTH_ENTAILMENT_VERIFY=0``) => the entailment union is never wired and the
    synthesis pass re-grounds through the frozen ``strict_verify`` alone (byte-identical to pre-C1)."""
    return os.getenv(_ENV_ENTAILMENT_VERIFY, "1").strip().lower() not in ("", "0", "false", "off", "no")


def _default_entails_fn(premise: str, hypothesis: str) -> Optional[bool]:
    """The production entailment judge: the SAME resident cross-encoder the consolidation leg loads
    (``consolidation_nli.entails_directional`` — span=premise, claim=hypothesis). Lazy import so this
    module stays cheap. Any import/scoring fault surfaces as ``None`` (=> the DEGRADE fallback), never a
    crash and never a silent True."""
    try:
        from src.polaris_graph.synthesis.consolidation_nli import entails_directional
    except Exception as exc:  # pragma: no cover — consolidation_nli is stable in-tree
        logger.warning("[synthesis_entailment_verify] entails_directional unavailable (%s) => degrade", exc)
        return None
    try:
        return entails_directional(premise, hypothesis)
    except Exception as exc:  # noqa: BLE001 — an infra fault degrades, never crashes the verify
        logger.warning("[synthesis_entailment_verify] entails_directional raised (%s) => degrade", exc)
        return None


@dataclass
class _EntailmentVerificationReport:
    """A minimal report exposing the ONE attribute the depth synthesis ``_collect`` reads: a list of
    kept ``SentenceVerification`` (each carrying ``.sentence`` with its [#ev:...] tokens and ``.tokens``)."""

    kept_sentences: list[SentenceVerification] = field(default_factory=list)


def _resolve_spans(
    tokens: list[ProvenanceToken], evidence_pool: dict
) -> "tuple[list[ProvenanceToken], list[str]]":
    """Resolve each token to its cited span text in the BASKET-SCOPED pool (a token whose evidence_id is
    absent from the scoped pool — a cross-basket citation — is skipped, so it fails CLOSED). Span bounds
    are validated with the SAME predicate the frozen engine uses (in-bounds, start < end)."""
    valid: list[ProvenanceToken] = []
    spans: list[str] = []
    for tok in tokens:
        ev = (evidence_pool or {}).get(tok.evidence_id)
        if ev is None:
            continue
        direct_quote = ev.get("direct_quote") or ev.get("statement") or ""
        if tok.end > len(direct_quote) or tok.start < 0 or tok.start >= tok.end:
            continue
        span_text = direct_quote[tok.start:tok.end]
        if not span_text.strip():
            continue
        valid.append(tok)
        spans.append(span_text)
    return valid, spans


def _numbers_match(sentence_core: str, span_texts: list[str]) -> bool:
    """Leg (b): the SAME numeric leg strict_verify applies (invariant #3), reused UNCHANGED via the
    module-level helpers. Every decimal in the sentence must appear in the union of the cited-span
    decimals; when the sentence carries no decimals, every standalone integer must appear in the union of
    the cited-span numbers. Placebo-comparator + achievement-threshold numbers are stripped exactly as
    the frozen engine strips them, and a %-expressed integer beside a decimal is also required in-span."""
    stripped = _strip_dose_patterns(sentence_core)
    stripped = _PLACEBO_COMPARATOR_RE.sub(" ", stripped)
    stripped = _THRESHOLD_RE.sub(" ", stripped)

    agg_decimals: set[str] = set()
    agg_numbers: set[str] = set()
    for span in span_texts:
        span_stripped = _strip_dose_patterns(span)
        agg_decimals |= _decimals_in(span_stripped)
        agg_numbers |= _numbers_in(span_stripped)

    sentence_decimals = _decimals_in(stripped)
    if sentence_decimals:
        if sentence_decimals - agg_decimals:
            return False
        claimed_pct_ints = {
            m.group(1) for m in _INTEGER_PERCENT_RE.finditer(stripped)
        } - sentence_decimals
        if claimed_pct_ints:
            agg_int_only = agg_numbers - agg_decimals
            if claimed_pct_ints - agg_int_only:
                return False
        return True

    sentence_numbers = _numbers_in(stripped)
    if sentence_numbers and (sentence_numbers - agg_numbers):
        return False
    return True


def _entails_or_degrade(premise: str, hypothesis: str, entails_fn: EntailsFn) -> "tuple[bool, str | None]":
    """Leg (c): the span (premise) must ENTAIL the sentence (hypothesis). Returns ``(keep, label)``.

    fix 5 (operator 2026-07-10): a judge DEGRADE (``None`` — the cross-encoder is unavailable / faulted)
    NO LONGER falls back to the >=2 lexical content-word overlap. That fallback RESURRECTED the killed
    lexical ghost on every judge outage. The sentence at this point is ALREADY provenance-resolved AND
    number-matched (the caller checked both), so a judge outage is a pure infra fault, not a faithfulness
    signal: KEEP the sentence with a disclosed ``judge-unavailable`` LABEL — never lexical-gate, never
    silently keep unlabeled.

      * True  => (True, None)     keep, verified.
      * False => (False, None)    drop, the span does not entail the sentence.
      * None  => (True, LABEL)    keep with the disclosed judge-unavailable label.
    """
    verdict = entails_fn(premise, hypothesis)
    if verdict is True:
        return True, None
    if verdict is False:
        return False, None
    return True, SYNTH_ENTAILMENT_JUDGE_UNAVAILABLE


def entailment_verify(
    draft_text: str, evidence_pool: dict, *, entails_fn: Optional[EntailsFn] = None
) -> _EntailmentVerificationReport:
    """Verify a synthesis draft through the ADDITIVE entailment leg. Keeps a sentence iff (a) it resolves
    >=1 provenance token to a cited span, (b) its numbers match the span (frozen numeric leg), and (c)
    the span ENTAILS the sentence. Returns a report whose ``kept_sentences`` mirror strict_verify's
    (each carries ``.sentence`` with its [#ev:...] tokens and ``.tokens``)."""
    entails_fn = _default_entails_fn if entails_fn is None else entails_fn
    kept: list[SentenceVerification] = []
    for raw_sentence in split_into_sentences(draft_text or ""):
        sentence = raw_sentence.strip()
        if not sentence:
            continue
        tokens = parse_provenance_tokens(sentence)
        if not tokens:
            continue
        valid_tokens, span_texts = _resolve_spans(tokens, evidence_pool)
        if not valid_tokens or not span_texts:
            continue
        core = _verifier_cleaned_text(sentence)  # strip [#ev:] / atom artifacts for the numeric + NLI input
        if not core.strip():
            continue
        if not _numbers_match(core, span_texts):
            continue
        premise = " ".join(span_texts)
        keep, degrade_label = _entails_or_degrade(premise, core, entails_fn)
        if not keep:
            continue
        warnings = [SYNTH_ENTAILMENT_SOFT_WARNING]
        if degrade_label:
            warnings.append(degrade_label)
        kept.append(
            SentenceVerification(
                sentence=sentence,
                tokens=valid_tokens,
                is_verified=True,
                soft_warnings=warnings,
            )
        )
    return _EntailmentVerificationReport(kept_sentences=kept)


def entailment_grounds_sentence(
    sentence: str, cited_rows: list, *, entails_fn: Optional[EntailsFn] = None
) -> bool:
    """The C3 promote confirmation (the ENTAILMENT analog of the D3 ``_frozen_engine_verifies_sentence``
    hook): reconstruct the cited spans from ``cited_rows`` (each row's full ``direct_quote`` / ``statement``)
    and confirm the synthesis sentence is number-grounded in the union AND ENTAILED by it. True => the
    sentence may be PROMOTED into the D8 4-role input set; a non-entailed / number-mismatched sentence =>
    False (not promoted). FAIL-CLOSED on no spans / empty prose."""
    entails_fn = _default_entails_fn if entails_fn is None else entails_fn
    core = _verifier_cleaned_text(str(sentence or ""))
    if not core.strip():
        return False
    span_texts: list[str] = []
    for row in (cited_rows or []):
        if not hasattr(row, "get"):  # accept any Mapping (dict / evidence record), skip non-mappings
            continue
        span = str(row.get("direct_quote") or row.get("statement") or "")
        if span.strip():
            span_texts.append(span)
    if not span_texts:
        return False
    if not _numbers_match(core, span_texts):
        return False
    premise = " ".join(span_texts)
    keep, _label = _entails_or_degrade(premise, core, entails_fn)
    return keep


def _norm_key(sentence: str) -> str:
    """Dedup key for the union: strip [#ev:...] tokens, collapse whitespace, lowercase."""
    bare = _EV_TOKEN_RE.sub(" ", sentence or "")
    return re.sub(r"\s+", " ", bare).strip().lower()


def make_entailment_union_verify_fn(
    base_verify_fn: Callable[..., Any], *, entails_fn: Optional[EntailsFn] = None
) -> Callable[..., Any]:
    """Wrap ``base_verify_fn`` (= the FROZEN ``strict_verify``) so its kept sentences are UNIONED with the
    entailment leg's kept sentences (dedup by normalized sentence). ADDITIVE: every strict_verify pass is
    kept unchanged; the entailment leg only ADDS entailed paraphrases the lexical >=2-content-word leg
    dropped. Each entailment-only addition carries the ``synthesis_entailment_verified`` soft-warning so
    the C3 D8-promote routing can recognize it. The returned callable has the SAME ``(draft, pool)``
    call shape ``synthesize_cross_source_findings`` invokes."""
    entails_fn = _default_entails_fn if entails_fn is None else entails_fn

    def _wrapped(draft: Any, pool: dict, *args: Any, **kwargs: Any) -> Any:
        base_report = base_verify_fn(draft, pool, *args, **kwargs)
        base_kept = list(getattr(base_report, "kept_sentences", None) or [])
        seen = {_norm_key(str(getattr(sv, "sentence", "") or "")) for sv in base_kept}
        seen.discard("")
        try:
            ent_report = entailment_verify(draft, pool, entails_fn=entails_fn)
        except Exception:  # noqa: BLE001 — the entailment leg is ADDITIVE; a fault keeps strict_verify only
            logger.warning("[synthesis_entailment_verify] entailment leg raised => strict_verify only", exc_info=True)
            return base_report
        merged = list(base_kept)
        for sv in ent_report.kept_sentences:
            key = _norm_key(str(getattr(sv, "sentence", "") or ""))
            if not key or key in seen:
                continue
            seen.add(key)
            if SYNTH_ENTAILMENT_SOFT_WARNING not in sv.soft_warnings:
                sv.soft_warnings.append(SYNTH_ENTAILMENT_SOFT_WARNING)
            merged.append(sv)
        try:
            base_report.kept_sentences = merged  # preserve every other field on the frozen report
            return base_report
        except Exception:  # pragma: no cover — StrictVerificationReport is a mutable dataclass
            return _EntailmentVerificationReport(kept_sentences=merged)

    return _wrapped
