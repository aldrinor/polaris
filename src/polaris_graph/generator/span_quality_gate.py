"""I-extract-001 LAYER B — span-quality gate (render-seam extraction-integrity judge).

The bake-off winner (`outputs/audits/iextract001/layerB_leaderboard.md`): an LLM judge
that, per candidate finding unit, decides whether the unit is a cleanly-extracted,
self-contained declarative finding OR page-furniture / broken-extraction garbage
(scraped heading, journal masthead, mid-word truncation, orphan citation fragment).
On the real banked drb_72 report the LLM judge scored **F1 0.568** (P 0.401, R 0.973),
~2x the best cheap heuristic composite (0.278) and catches the glued-mid-prose chrome +
cut-word-before-`[N]` that the production §-1.1 regex detector is structurally BLIND to
(it returned PASS / 0 chrome on this junk-filled report — the iwire013 blind-predicate
saga this issue exists to fix).

CRITICAL §-1.3 CONTRACT — FLAG, NEVER DROP:
  This module ONLY classifies + returns verdicts. It NEVER deletes, mutates, reorders,
  or removes a unit. The returned list is aligned 1:1 with the input. A silent low-
  precision DROP of a real finding is a clinical-safety failure; the gate surfaces a
  per-unit ``is_junk`` flag + class for an out-of-band review/render decision made by
  the (deferred) caller. On ANY uncertainty (judge_error / timeout / malformed output)
  the unit is reported ``is_junk=False`` (pass-through) and counted under ``errors`` —
  flagging on uncertainty is the §-1.3 failure mode and is deliberately avoided.

PRECISION NARROWING (benchmark key-finding #2 — recover the recall-first FPs):
  The judge holds ~0.40 precision at full recall; ~85% of its false positives are
  ordinary well-formed clean findings. Per the leaderboard the fix is to NARROW the
  contamination rule to the labeling convention. Implemented TWO ways:
    (1) PROMPT — the judge is instructed with the narrowed rule (truncation = mid-word
        only; orphan = bare citation fragment only; a real finding carrying a leading
        section-word prefix or a trailing multi-citation cluster is a real finding).
    (2) DETERMINISTIC post-pass — ``_apply_precision_narrowing`` demotes the three
        deterministically-separable FP shapes the leaderboard names. The hard invariant:
        narrowing ONLY EVER flips junk -> clean (precision-improving); it can NEVER flip
        clean -> junk. The deterministic pass is a BACKSTOP — the clause-cut truncation
        FPs ("...has been used to") are NOT deterministically separable from clause-cut
        true positives ("...non-routine tasks") and are left to the prompt + judge.

MODELS (central runtime lock, `config/architecture/polaris_runtime_lock.yaml`):
  primary = z-ai/glm-5.2 (per task + §9.1.8: side-judges map to the MIRROR; GLM-5.2 is
  also the measured F1 topper). design.md's "Qwen-primary" framing is the input the task
  deliberately overrode — do NOT "fix" it back. escalation = qwen/qwen3.6-35b-a3b (the
  judge role), a different family (qwen != glm) -> family-segregation passes.

ESCALATION caller is INJECTABLE and defaults to None (disabled). The production GLM-5.2
primary caller reuses the proven `make_openrouter_credibility_caller` control surface
(family-segregation, mirror provider-pin, budget + wall-deadline). That factory pins to
the MIRROR (GLM) chain, which a Qwen escalation must NOT inherit (it would hard-400
under allow_fallbacks=False when a Path-B gate is active) — so the escalation caller is
left for the deferred render-seam wiring to inject correctly-pinned. The benchmark
escalated 0/471 units (Qwen confidence always >= 0.7), so injectable-by-default is honest.

BENCHMARK-FIDELITY CAVEAT: the production call is a flattened single-user-message prompt
with NO ``response_format: json_object`` (the mirror hosts 404 on it — I-arch-011 B14),
which DIVERGES from the multi-turn + json_object shape that measured F1 0.568. The 0.568
is therefore NOT guaranteed on this path; the deferred fresh-run §-1.4 audit is the real
validation (committed + green != wired).

BOUNDED PARALLELISM (runtime-parallelism mandate): per-unit judging runs bounded-parallel
via ``ThreadPoolExecutor(max_workers=PG_SPAN_QUALITY_GATE_WORKERS)`` (default 16),
order-PRESERVING (gather-then-sort by index) so concurrency never changes a per-unit
outcome.

Flag-gated: ``PG_SPAN_QUALITY_GATE`` (default OFF). When OFF, ``screen_finding_units``
makes ZERO LLM calls and returns disabled (is_junk=False) verdicts so the deferred caller
can call it unconditionally as a safe no-op.

The faithfulness engine (strict_verify / NLI / 4-role / provenance) is FROZEN and
untouched. This module is an EXTRACTION-INTEGRITY classifier, NOT a credibility/relevance
filter (CLAUDE.md §-1.3 weight-don't-drop).
"""
from __future__ import annotations

import json
import logging
import os
import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Callable

logger = logging.getLogger(__name__)

# ── env knobs (LAW VI — zero hard-coding) ────────────────────────────────────
_ENV_FLAG = "PG_SPAN_QUALITY_GATE"
# primary = GLM-5.2 (mirror) per the task + §9.1.8 side-judge->mirror mapping + measured
# F1 topper. design.md's "Qwen-primary" is the input the task overrode — do not flip back.
_ENV_PRIMARY_MODEL = "PG_SPAN_QUALITY_GATE_PRIMARY_MODEL"
_DEFAULT_PRIMARY_MODEL = "z-ai/glm-5.2"
# escalation = the qwen judge role (different family). Caller is injectable; default None.
_ENV_ESCALATION_MODEL = "PG_SPAN_QUALITY_GATE_ESCALATION_MODEL"
_DEFAULT_ESCALATION_MODEL = "qwen/qwen3.6-35b-a3b"
_ENV_WORKERS = "PG_SPAN_QUALITY_GATE_WORKERS"
_DEFAULT_WORKERS = 16
_ENV_ESCALATE_BELOW = "PG_SPAN_QUALITY_GATE_ESCALATE_BELOW"
_DEFAULT_ESCALATE_BELOW = 0.7

# ── verdict vocabulary (verdict_schema.json) ─────────────────────────────────
_CLASS_CLEAN = "clean"
_VALID_JUNK_CLASSES = frozenset(
    {"scraped_heading", "masthead", "truncation", "orphan_citation"}
)
_VALID_CLASSES = frozenset(_VALID_JUNK_CLASSES | {_CLASS_CLEAN})

# ── per-unit verdict provenance (REAL runtime states, surfaced by the canary) ──
_SOURCE_PRIMARY = "primary"          # primary judge produced the verdict
_SOURCE_ESCALATION = "escalation"    # low-confidence -> re-judged by the escalation tier
_SOURCE_NARROWED = "narrowed_clean"  # a junk verdict demoted to clean by the precision pass
_SOURCE_ERROR = "error"             # judge_error / malformed -> pass-through (is_junk=False)
_SOURCE_DISABLED = "disabled"       # flag OFF -> unit passed through unjudged

# ── precision-narrowing constants ────────────────────────────────────────────
# Sentence-terminal punctuation. A truncation flag on a unit that ENDS complete (terminal
# punct, no mid-word glue) is a complete-sentence false positive -> demote.
_TERMINAL_PUNCT = frozenset(".!?")
# Mid-word cut signature observed in the gold (e.g. "employ.; ment", "statis.; bstitution"):
# a letter, a period, a semicolon, then a lowercase letter — a word welded across an
# internal '.;' glue. Effectively never occurs in clean prose -> high-precision KEEP signal.
_MIDWORD_CUT = re.compile(r"[A-Za-z]\s*\.\s*;\s*[a-z]")
# A trailing citation cluster like "[15]" / "[9][10][8]" / "[9, 10]" stripped before the
# complete-sentence / bracket-only tests so a clean finding's trailing cites do not confuse them.
_TRAILING_CITES = re.compile(r"(?:\s*\[\d+[\d,;\s]*\])+\s*$")
_CITES_ANYWHERE = re.compile(r"\[\d+[\d,;\s]*\]")
# Closing quotes / parens / brackets that may trail terminal punctuation in real prose.
# Character class members written as ASCII-safe escapes so the literal can never be
# silently broken by a curly->straight quote transcode (the original failure mode): the
# straight double quote is escaped (\"), the curly closers use \u escapes that `re`
# resolves (’ = right single quote, ” = right double quote). Also: straight
# single quote ('), close paren ()), and escaped close bracket (\]). Anchored end-of-string.
_TRAILING_CLOSERS = re.compile(r"[\"'’”)\]]+$")
# Benign section-word prefix: a bold "**Foundational_Theory.**" label OR a short Title-case
# "Foundational Theory." label, followed by real prose. Demote scraped_heading only when a
# SUBSTANTIAL declarative finding follows (so a true heading like "Frequently Asked Questions.
# How does it work" — short trailing — is NOT demoted).
_BOLD_SECTION_PREFIX = re.compile(r"^\s*\*\*[^*]+\*\*\s*\S")
_PLAIN_SECTION_PREFIX = re.compile(
    r"^\s*[A-Z][A-Za-z]*(?:[_ ][A-Z][A-Za-z]*){0,3}\.\s+\S"
)
_SECTION_PREFIX_MIN_TRAILING_WORDS = 8


@dataclass(frozen=True)
class SpanQualityVerdict:
    """Per-candidate extraction-integrity verdict. STRUCTURE-only; never a drop.

    ``is_junk`` is the flag the (deferred) render-seam caller consults; ``junk_class`` is
    one of the schema classes ("clean" when not junk). ``unit_index`` aligns 1:1 with the
    input list. ``source`` records which path produced the verdict (REAL runtime state).
    """

    unit_index: int
    is_junk: bool
    junk_class: str
    confidence: float
    offending_span: str
    source: str


# ──────────────────────────────────────────────────────────────────────────────
# flag + config helpers
# ──────────────────────────────────────────────────────────────────────────────
def is_span_quality_gate_enabled() -> bool:
    """True iff PG_SPAN_QUALITY_GATE is set truthy (default OFF). LAW VI env-gated."""
    return os.environ.get(_ENV_FLAG, "").strip().lower() in ("1", "true", "yes", "on")


def _workers() -> int:
    """Bounded-parallel worker count from PG_SPAN_QUALITY_GATE_WORKERS. Clamped >=1."""
    try:
        n = int(os.environ.get(_ENV_WORKERS, str(_DEFAULT_WORKERS)))
    except (TypeError, ValueError):
        n = _DEFAULT_WORKERS
    return max(1, n)


def _escalate_below() -> float:
    """Confidence floor below which a primary verdict is re-judged by the escalation tier."""
    try:
        v = float(os.environ.get(_ENV_ESCALATE_BELOW, str(_DEFAULT_ESCALATE_BELOW)))
    except (TypeError, ValueError):
        v = _DEFAULT_ESCALATE_BELOW
    return min(1.0, max(0.0, v))


def primary_model() -> str:
    return os.environ.get(_ENV_PRIMARY_MODEL, "").strip() or _DEFAULT_PRIMARY_MODEL


def escalation_model() -> str:
    return os.environ.get(_ENV_ESCALATION_MODEL, "").strip() or _DEFAULT_ESCALATION_MODEL


# ──────────────────────────────────────────────────────────────────────────────
# pure prompt build (verbatim design.md / judge_prompt.txt, flattened to one message)
# ──────────────────────────────────────────────────────────────────────────────
_SYSTEM = (
    "You are an EXTRACTION-INTEGRITY judge for a research pipeline. Given ONE candidate "
    "finding unit extracted from a scraped web page, decide whether it is a real, "
    "self-contained declarative finding sentence OR page-furniture / broken-extraction "
    "garbage. You judge STRUCTURE ONLY (was this cleanly extracted prose), NOT "
    "credibility, source quality, or topical value. A low-quality but well-formed claim "
    "is is_real_finding=true. If ANY chrome, masthead, heading, truncation, or "
    "orphan-citation fragment is glued into an otherwise real sentence, the unit is "
    "is_real_finding=false (contamination rule)."
)
# Precision-narrowed contamination rule (benchmark key-finding #2) — carried in the prompt
# so the judge applies it; the deterministic post-pass backstops the separable shapes.
_NARROWED_RULE = (
    "Apply this NARROWED contamination rule to avoid over-flagging clean prose: "
    "(a) truncation ONLY for a MID-WORD cut (a word split by internal punctuation such as "
    "'employ.; ment', or a unit that ends mid-word); a complete declarative sentence is "
    "is_real_finding=true even if it reads as one clause of a larger argument. "
    "(b) orphan_citation ONLY for a unit that is ESSENTIALLY a bare citation fragment "
    "(e.g. '.[4][5]'); a real finding that merely ends with a trailing citation cluster "
    "(e.g. '...member countries.[11][12]') is is_real_finding=true. "
    "(c) a real finding that merely carries a leading section-word prefix "
    "(e.g. '**Foundational Theory.** <real finding>') is is_real_finding=true."
)
_SCHEMA_LINE = (
    'Return STRICT JSON only, no prose, no code fence: '
    '{"is_real_finding": bool, "failure_class": '
    '"clean|scraped_heading|masthead|truncation|orphan_citation", '
    '"offending_span": "verbatim offending substring or empty", '
    '"confidence": 0.0-1.0}'
)
# Balanced few-shot: 4 failure classes + 1 clean (illustrative, NOT from any test report)
# so the judge does not collapse to "always reject" (fatal in a consolidate-don't-drop pipeline).
_FEWSHOT = (
    ("Frequently Asked Questions. How does machine learning work.[7][8]",
     '{"is_real_finding": false, "failure_class": "scraped_heading", '
     '"offending_span": "Frequently Asked Questions. How does machine learning work", '
     '"confidence": 0.95}'),
    ("Received 12 March 2021; accepted 4 August 2021; published online 19 September 2021. "
     "Corresponding author: j.smith@univ.edu.[3]",
     '{"is_real_finding": false, "failure_class": "masthead", '
     '"offending_span": "Received 12 March 2021; accepted 4 August 2021", '
     '"confidence": 0.93}'),
    ("the model predicts employ.; ment growth across all sectors.[5][6]",
     '{"is_real_finding": false, "failure_class": "truncation", '
     '"offending_span": "employ.; ment", "confidence": 0.92}'),
    (".[4][5]",
     '{"is_real_finding": false, "failure_class": "orphan_citation", '
     '"offending_span": ".[4][5]", "confidence": 0.97}'),
    ("A 2020 OECD study estimates that 14% of jobs are at high risk of automation across "
     "member countries.[11]",
     '{"is_real_finding": true, "failure_class": "clean", '
     '"offending_span": "", "confidence": 0.9}'),
)


def build_judge_prompt(unit_text: str) -> str:
    """Pure: render the single-message span-quality prompt for ONE candidate unit.

    Flattened to one user message (system instructions + narrowed rule + balanced few-shot
    + task turn) because the injected ``call_llm(prompt) -> text`` surface (the proven
    credibility-caller control surface) sends a single user message and no ``response_format``.
    """
    parts = [_SYSTEM, "", _NARROWED_RULE, "", _SCHEMA_LINE, "",
             "EXAMPLES (illustrative, not from the report under review):"]
    for inp, out in _FEWSHOT:
        parts.append(f"CANDIDATE UNIT:\n{inp}")
        parts.append(out)
    parts.append(f"CANDIDATE UNIT:\n{unit_text}")
    parts.append("JSON:")
    return "\n".join(parts)


# ──────────────────────────────────────────────────────────────────────────────
# pure verdict parse (brace-walk; reasoning models emit JSON + trailing reasoning prose)
# ──────────────────────────────────────────────────────────────────────────────
def parse_verdict(text: str) -> dict | None:
    """Pure: extract the verdict object from a possibly-prose-wrapped reasoning response.

    Returns a normalised dict ``{is_real_finding, failure_class, offending_span, confidence}``
    or ``None`` on ANY malformed / out-of-scheme output (the caller then treats the unit as
    a pass-through error — fail-honest, never fabricate a junk flag). Mirrors
    ``entailment_judge._extract_first_json_object``'s technique: ``json.JSONDecoder().raw_decode``
    walks each top-level '{' and selects the FIRST complete object carrying the required
    ``"is_real_finding"`` key, so a valid verdict followed by trailing reasoning text (the
    GLM-5.2 reasoning-model norm) is recovered while a greedy regex would mis-grab.
    """
    if not isinstance(text, str) or not text.strip():
        return None
    decoder = json.JSONDecoder()
    search_from = 0
    while True:
        start = text.find("{", search_from)
        if start == -1:
            return None
        try:
            value, end = decoder.raw_decode(text, start)
        except json.JSONDecodeError:
            # not a complete object at this '{' — advance one char and keep scanning.
            search_from = start + 1
            continue
        if isinstance(value, dict) and "is_real_finding" in value:
            return _normalise_verdict(value)
        search_from = end


def _normalise_verdict(obj: dict) -> dict | None:
    """Coerce a raw verdict dict to the schema, or None if it is out-of-scheme."""
    is_real = obj.get("is_real_finding")
    if not isinstance(is_real, bool):
        return None
    failure_class = str(obj.get("failure_class", "")).strip()
    if failure_class not in _VALID_CLASSES:
        # §-1.3 FAIL-HONEST: an out-of-scheme / unknown failure_class is malformed judge
        # output. NEVER coerce it into a junk class — flagging a real unit as junk on
        # malformed/uncertain output is the wrong direction (a clinical-safety drop signal).
        # Return None so the caller routes the unit through the pass-through error path
        # (is_junk=False, junk_class=None, source="error").
        return None
    offending_span = str(obj.get("offending_span", "") or "")
    try:
        confidence = float(obj.get("confidence", 0.0))
    except (TypeError, ValueError):
        confidence = 0.0
    confidence = min(1.0, max(0.0, confidence))
    return {
        "is_real_finding": is_real,
        "failure_class": failure_class if not is_real else _CLASS_CLEAN,
        "offending_span": offending_span,
        "confidence": confidence,
    }


# ──────────────────────────────────────────────────────────────────────────────
# deterministic precision narrowing (ONLY ever flips junk -> clean; never clean -> junk)
# ──────────────────────────────────────────────────────────────────────────────
def _ends_complete_sentence(text: str) -> bool:
    """True iff ``text`` ends like a complete sentence (terminal punct), ignoring trailing
    citation clusters and closing quotes/parens."""
    s = _TRAILING_CITES.sub("", text.rstrip()).rstrip()
    s = _TRAILING_CLOSERS.sub("", s).rstrip()
    s = _TRAILING_CITES.sub("", s).rstrip()  # cites may sit inside closers, e.g. .[11])
    return bool(s) and s[-1] in _TERMINAL_PUNCT


def _has_midword_glue(text: str) -> bool:
    """True iff ``text`` contains the '.;' internal mid-word glue (e.g. 'employ.; ment')."""
    return bool(_MIDWORD_CUT.search(text))


def _is_bracket_only(text: str) -> bool:
    """True iff the unit is essentially a bare citation fragment: no alphabetic content
    remains once citation clusters are removed (e.g. '.[19][20]', '[9][10][8]')."""
    return not re.search(r"[A-Za-z]", _CITES_ANYWHERE.sub("", text))


def _is_section_prefixed_finding(text: str) -> bool:
    """True iff the unit is a benign section-word prefix followed by a SUBSTANTIAL real
    finding (a bold '**Section.**' label, or a short Title-case 'Section.' label, then
    >= _SECTION_PREFIX_MIN_TRAILING_WORDS words of prose)."""
    if _BOLD_SECTION_PREFIX.match(text):
        trailing = re.sub(r"^\s*\*\*[^*]+\*\*\s*", "", text)
    elif _PLAIN_SECTION_PREFIX.match(text):
        trailing = re.sub(r"^\s*[A-Z][A-Za-z]*(?:[_ ][A-Z][A-Za-z]*){0,3}\.\s+", "", text)
    else:
        return False
    return len(trailing.split()) >= _SECTION_PREFIX_MIN_TRAILING_WORDS


def _apply_precision_narrowing(
    unit_text: str, failure_class: str, offending_span: str
) -> bool:
    """Return True iff a JUNK verdict SURVIVES the deterministic narrowing (stays junk).

    Demotes only the three deterministically-separable FP shapes the leaderboard names
    (orphan trailing-cite, complete-sentence truncation, section-word-prefix). The clause-cut
    truncation FPs are NOT separable from clause-cut TPs and are left to the prompt + judge.
    INVARIANT: only ever returns False (demote junk -> clean); it is only ever called on an
    already-junk verdict, so it can never flip clean -> junk.
    """
    if failure_class == "orphan_citation":
        # Keep only a genuine bare-citation fragment; demote a real finding carrying a
        # trailing multi-citation cluster.
        return _is_bracket_only(unit_text)
    if failure_class == "truncation":
        # Keep only mid-word evidence: the '.;' glue (in the span or unit) OR a unit that
        # ends mid-word (no terminal punctuation). Demote a complete declarative sentence.
        return (
            _has_midword_glue(offending_span)
            or _has_midword_glue(unit_text)
            or not _ends_complete_sentence(unit_text)
        )
    if failure_class == "scraped_heading":
        # Demote a benign section-word prefix that carries a substantial real finding.
        return not _is_section_prefixed_finding(unit_text)
    # masthead (and any other class): no deterministic narrowing — trust the judge.
    return True


# ──────────────────────────────────────────────────────────────────────────────
# single-unit judging
# ──────────────────────────────────────────────────────────────────────────────
def judge_unit(
    unit_text: str,
    unit_index: int,
    primary_call_llm: Callable[[str], str],
    *,
    escalation_call_llm: Callable[[str], str] | None = None,
    escalate_below: float | None = None,
) -> SpanQualityVerdict:
    """Judge ONE candidate unit. Never raises into the caller (LAW II fail-honest): any
    error from the injected caller / parse degrades to a pass-through (is_junk=False,
    source="error") so the §-1.3 contract holds (a real finding is never flagged on
    uncertainty)."""
    floor = _escalate_below() if escalate_below is None else escalate_below
    verdict = _judge_once(unit_text, primary_call_llm)
    source = _SOURCE_PRIMARY
    if verdict is None:
        return SpanQualityVerdict(
            unit_index=unit_index, is_junk=False, junk_class=_CLASS_CLEAN,
            confidence=0.0, offending_span="", source=_SOURCE_ERROR,
        )
    # Confidence-escalation: re-judge a low-confidence primary verdict on the escalation tier.
    if escalation_call_llm is not None and verdict["confidence"] < floor:
        esc = _judge_once(unit_text, escalation_call_llm)
        if esc is not None:
            verdict = esc
            source = _SOURCE_ESCALATION
    is_junk = not verdict["is_real_finding"]
    junk_class = verdict["failure_class"]
    if is_junk:
        # Deterministic precision narrowing — only ever demotes junk -> clean.
        survives = _apply_precision_narrowing(
            unit_text, junk_class, verdict["offending_span"]
        )
        if not survives:
            return SpanQualityVerdict(
                unit_index=unit_index, is_junk=False, junk_class=_CLASS_CLEAN,
                confidence=verdict["confidence"], offending_span="",
                source=_SOURCE_NARROWED,
            )
    return SpanQualityVerdict(
        unit_index=unit_index, is_junk=is_junk,
        junk_class=junk_class if is_junk else _CLASS_CLEAN,
        confidence=verdict["confidence"],
        offending_span=verdict["offending_span"] if is_junk else "",
        source=source,
    )


def _judge_once(unit_text: str, call_llm: Callable[[str], str]) -> dict | None:
    """One judge call + parse. Returns the normalised verdict dict or None on any fault."""
    prompt = build_judge_prompt(unit_text)
    try:
        text = call_llm(prompt)
    except Exception as exc:  # noqa: BLE001 — fail-honest: degrade to pass-through
        logger.warning("[span_gate] judge_error for unit (len=%d): %s",
                       len(unit_text or ""), exc)
        return None
    verdict = parse_verdict(text)
    if verdict is None:
        logger.warning("[span_gate] malformed/out-of-scheme verdict for unit (len=%d)",
                       len(unit_text or ""))
    return verdict


# ──────────────────────────────────────────────────────────────────────────────
# production default caller (lazy — keeps the OFF path free of httpx + authority pkg)
# ──────────────────────────────────────────────────────────────────────────────
def _default_primary_caller() -> Callable[[str], str]:
    """Bind the production GLM-5.2 primary caller via the proven credibility control surface
    (family-segregation, mirror provider-pin, budget + wall-deadline). Lazy import keeps the
    OFF path / offline tests free of httpx + the authority package."""
    from src.polaris_graph.authority.credibility_judge_caller import (
        make_openrouter_credibility_caller,
    )

    return make_openrouter_credibility_caller(model=primary_model())


# ──────────────────────────────────────────────────────────────────────────────
# batch entry — the (deferred) render-seam caller's public surface
# ──────────────────────────────────────────────────────────────────────────────
def screen_finding_units(
    units: list[str],
    *,
    primary_call_llm: Callable[[str], str] | None = None,
    escalation_call_llm: Callable[[str], str] | None = None,
    max_workers: int | None = None,
) -> list[SpanQualityVerdict]:
    """Bounded-parallel span-quality screen over candidate finding units.

    THE PUBLIC SURFACE the (deferred) render-seam caller uses. Returns a list of
    ``SpanQualityVerdict`` aligned 1:1 with ``units`` (FLAG-not-drop: no unit is ever
    removed — the caller decides what to do with the flags out-of-band).

    Flag-gated: when PG_SPAN_QUALITY_GATE is OFF this makes ZERO LLM calls and returns
    disabled verdicts (is_junk=False, source="disabled") so the caller can invoke it
    unconditionally. When ON, the primary judge runs bounded-parallel; a low-confidence
    verdict is re-judged by ``escalation_call_llm`` if one is provided (default None ->
    no escalation, matching the 0/471-escalations benchmark). On any judge_error / malformed
    output a unit degrades to a pass-through (is_junk=False, source="error").

    ``primary_call_llm`` defaults to the production GLM-5.2 credibility caller; inject a stub
    for offline tests. ``escalation_call_llm`` is injectable — the production Qwen escalation
    must be pinned to the JUDGE chain by the caller (the default credibility factory pins to
    the MIRROR/GLM chain, which a Qwen model must not inherit), so it is intentionally not
    defaulted here.
    """
    n = len(units)
    if n == 0:
        return []
    if not is_span_quality_gate_enabled():
        logger.info(
            "[span_gate] DISABLED (PG_SPAN_QUALITY_GATE off): %d units passed through "
            "unjudged (zero LLM calls)", n,
        )
        return [
            SpanQualityVerdict(
                unit_index=i, is_junk=False, junk_class=_CLASS_CLEAN,
                confidence=0.0, offending_span="", source=_SOURCE_DISABLED,
            )
            for i in range(n)
        ]
    if primary_call_llm is not None:
        primary = primary_call_llm
    else:
        # §-1.3 FAIL-SAFE: the default GLM-5.2 caller is built via the credibility control
        # surface, whose `check_family_segregation` RAISES at construction when the span-gate
        # side-judge (GLM mirror per §9.1.8) shares the generator family unless the process
        # has PG_PERMIT_GENERATOR_EVALUATOR_SAME_FAMILY set (and also when OPENROUTER_API_KEY
        # is absent). We do NOT globally mutate that permit (a side-judge must not flip a
        # crown-jewel two-family invariant for the whole process). Instead, if the default
        # judge cannot be constructed, the gate fails SAFE: every unit passes through
        # unflagged (is_junk=False, source="error"). Flagging-on-unavailability would be the
        # §-1.3 wrong direction (a real finding dropped because the side-judge could not run).
        try:
            primary = _default_primary_caller()
        except RuntimeError as exc:
            logger.warning(
                "[span_gate] default judge unavailable (%s) -> %d units passed through "
                "unflagged (fail-safe, no flag on uncertainty)", exc, n,
            )
            return [
                SpanQualityVerdict(
                    unit_index=i, is_junk=False, junk_class=_CLASS_CLEAN,
                    confidence=0.0, offending_span="", source=_SOURCE_ERROR,
                )
                for i in range(n)
            ]
    workers = max_workers if max_workers is not None else _workers()
    floor = _escalate_below()

    def _one(idx: int) -> SpanQualityVerdict:
        try:
            return judge_unit(
                units[idx], idx, primary,
                escalation_call_llm=escalation_call_llm, escalate_below=floor,
            )
        except Exception as exc:  # noqa: BLE001 — defensive: judge_unit is contracted not to raise
            logger.warning("[span_gate] unexpected error judging idx=%d: %s", idx, exc)
            return SpanQualityVerdict(
                unit_index=idx, is_junk=False, junk_class=_CLASS_CLEAN,
                confidence=0.0, offending_span="", source=_SOURCE_ERROR,
            )

    by_idx: dict[int, SpanQualityVerdict] = {}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for verdict in pool.map(_one, range(n)):
            by_idx[verdict.unit_index] = verdict
    out = [by_idx[i] for i in range(n)]  # gather-then-sort: order-preserving

    # ── behavioral canary — REAL runtime counts, fired only after the fan-out ran ──
    flagged = [v for v in out if v.is_junk]
    class_counts = {c: 0 for c in sorted(_VALID_JUNK_CLASSES)}
    for v in flagged:
        if v.junk_class in class_counts:
            class_counts[v.junk_class] += 1
    escalated = sum(1 for v in out if v.source == _SOURCE_ESCALATION)
    narrowed = sum(1 for v in out if v.source == _SOURCE_NARROWED)
    errors = sum(1 for v in out if v.source == _SOURCE_ERROR)
    logger.info(
        "[span_gate] judged=%d flagged=%d (scraped_heading=%d masthead=%d "
        "truncation=%d orphan_citation=%d) escalated=%d narrowed=%d errors=%d",
        n, len(flagged), class_counts["scraped_heading"], class_counts["masthead"],
        class_counts["truncation"], class_counts["orphan_citation"],
        escalated, narrowed, errors,
    )
    return out
