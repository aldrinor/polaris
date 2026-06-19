"""
Contradiction detector — HONEST-REBUILD Phase 3.

Finds pairs of evidence statements that directly contradict each other
on the same (subject, predicate, numeric value) tuple. Surfaces these
to the user before synthesis so the generator cannot silently pick one
side.

ADDRESSES PG_LB_SA_02_CONTENT_AUDIT Section E-06: the pre-rebuild
pipeline found two conflicting efficacy numbers for semaglutide weight
loss (STEP 1: 14.9% vs STEP 5: 17.4%), and the final report cited only
one without disclosing the range. A reader could not tell whether the
disagreement was stratification, dosing, duration, or cherry-picking.

DESIGN:
This detector is deterministic and rule-based. It does NOT use an LLM
to decide whether two claims contradict because LLM-based contradiction
detection has known failure modes on numerical values (confuses 14 and
17 as "roughly similar" even when it's a 17% relative difference).

Approach:
  1. Extract structured claims: (subject, predicate, numeric_value, unit)
     from each evidence row using regex on the direct_quote.
  2. Group claims by normalized (subject, predicate) pair.
  3. Within each group, flag numeric discrepancies > 10% relative
     difference OR > 2.0 absolute unit difference (configurable).
  4. Return a list of ContradictionRecord objects.

The caller (Phase 4 synthesis) inserts a disclosure line for each
contradicted claim: "Sources report X (ref A) and Y (ref B). The
reasons for the difference are [analyst note]."
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import asdict, dataclass, field
from typing import Any, Optional

logger = logging.getLogger("polaris_graph.contradiction_detector")


# ─────────────────────────────────────────────────────────────────────────────
# Numeric + unit extraction
# ─────────────────────────────────────────────────────────────────────────────

# Percentage values. Captures the number + "%" or " percent".
# Note: \b after "%" fails because % and space are both non-word chars —
# use a non-capturing boundary or a literal end-of-token check instead.
_PCT_RE = re.compile(
    r"(?P<value>-?\d+(?:\.\d+)?)\s*(?P<unit>%|percent|pct)(?=\s|[,.;:)\]!?]|$)",
    re.IGNORECASE,
)

# Mass / dose values with unit.
_DOSE_RE = re.compile(
    r"(?P<value>-?\d+(?:\.\d+)?)\s*(?P<unit>mg|µg|ug|mcg|g|kg)(?=\s|[,.;:)\]!?]|$)",
    re.IGNORECASE,
)

# HbA1c points. "percentage points" uses an explicit trailing word
# boundary since "points" ends on a word char.
_HBA1C_RE = re.compile(
    r"(?P<value>-?\d+(?:\.\d+)?)\s*(?P<unit>%|percentage\s*points?)",
    re.IGNORECASE,
)

# Time durations
_DURATION_RE = re.compile(
    r"(?P<value>-?\d+(?:\.\d+)?)\s*(?P<unit>weeks?|months?|years?)\b",
    re.IGNORECASE,
)

# ─────────────────────────────────────────────────────────────────────────────
# B9 domain-generalization — DOMAIN-AGNOSTIC numeric extraction.
#
# The clinical extractor (`extract_numeric_claims` clinical path) keys a claim
# on a CLINICAL predicate lexicon (`_EFFICACY_PREDICATES` / `_SAFETY_PREDICATES`)
# and a CLINICAL subject (`_DRUG_NAME_RE`). For a non-clinical corpus
# (economics / AI-labor / policy / science / tech) both return nothing, so
# `extract_numeric_claims` emits ZERO claims → every non-clinical numeric row
# becomes a SINGLETON in `finding_dedup` / `claim_graph` (the documented
# residual that blocks B6/B8 non-clinical baskets). The generic path below
# extracts a claim-atom WITHOUT any clinical literal: a generic metric cue (the
# SAME field-agnostic cues as `scope_gate.extract_research_frame_heuristic`) is
# the predicate, a generic number+unit is the value, and a generic content-word
# entity is the subject. This yields a REAL claim-key for non-clinical numerics
# (so corroborating sources can consolidate into a basket) WITHOUT loosening the
# clinical merge rule — clinical runs are byte-identical (gated on is_clinical).
# Faithfulness is unchanged: span-grounding / strict_verify remain the hard gate.
# ─────────────────────────────────────────────────────────────────────────────

# Any number with an OPTIONAL trailing unit token. Generic — no clinical
# vocabulary. Captures percent / currency-magnitude / plain counts so an
# economics or labor numeric ("GDP grew 3.2%", "$13 trillion", "75.5 percent")
# is extractable. The unit is normalized so two sources stating the same
# quantity in the same unit can consolidate.
_GENERIC_VALUE_RE = re.compile(
    r"(?P<value>-?\d+(?:,\d{3})*(?:\.\d+)?)\s*"
    r"(?P<unit>%|percent|percentage\s*points?|pp|bps|basis\s*points?|"
    r"trillion|billion|million|thousand|"
    r"usd|eur|gbp|cad|jpy|"
    r"gw|mw|kw|kwh|mwh|twh|tonnes?|tons?|"
    r"jobs?|workers?|people|users?|points?|x|×)?"
    r"(?=\s|[,.;:)\]!?]|$)",
    re.IGNORECASE,
)


def _normalize_generic_unit(unit: str) -> str:
    """Canonicalize a generic unit token so equivalent spellings consolidate.

    '%'/'percent' -> 'percent'; magnitude words and currencies stay as the
    lowercased token. Empty/None -> '' (a unit-less count). Pure."""
    u = (unit or "").strip().lower()
    if not u:
        return ""
    u = re.sub(r"\s+", " ", u)
    if u in ("%", "percent"):
        return "percent"
    if u in ("pp", "percentage point", "percentage points"):
        return "percentage_points"
    if u in ("bps", "basis point", "basis points"):
        return "basis_points"
    return u


def _normalize_predicate_generic(text: str) -> Optional[str]:
    """Return a field-agnostic predicate (a generic metric cue) present in the
    text, or None. Reuses `scope_gate.extract_research_frame_heuristic`'s
    metric-cue vocabulary (rate/ratio/cost/share/level/score/growth/emissions/
    accuracy/...). NO clinical literal. Pure, no LLM."""
    from src.polaris_graph.nodes.scope_gate import _FRAME_METRIC_CUES_RE
    m = _FRAME_METRIC_CUES_RE.search(text or "")
    if m:
        return m.group(1).lower()
    return None


# Generic stopwords for content-word subject extraction (no domain literal).
# Includes statistical / temporal / measurement FILLER words that are NOT real
# entities — a generic claim whose only nearby content word is filler resolves
# to "unknown" (a SAFE SINGLETON, never a false merge — the conservative rule).
_GENERIC_SUBJECT_STOPWORDS = frozenset({
    "the", "a", "an", "and", "or", "but", "is", "are", "was", "were", "of",
    "in", "on", "at", "to", "for", "with", "by", "from", "as", "that", "this",
    "these", "those", "it", "its", "be", "been", "has", "have", "had", "will",
    "would", "could", "should", "may", "can", "about", "into", "than", "such",
    "between", "over", "under", "per", "more", "most", "some", "all", "each",
    # Statistical / measurement / temporal filler — not an entity subject.
    "mean", "median", "average", "total", "observed", "reported", "estimated",
    "measured", "approximately", "roughly", "about", "value", "values",
    "rate", "ratio", "level", "amount", "number", "result", "results",
    "week", "weeks", "month", "months", "year", "years", "day", "days",
    "baseline", "change", "reduction", "increase", "decrease", "growth",
    "compared", "versus", "relative", "respectively", "overall", "general",
})


def _subject_generic(
    text: str, anchor_pos: int, predicate: str = "", window: int = 120,
) -> str:
    """Extract a generic content-word subject for a non-clinical claim — the
    noun that names WHAT the metric measures, NOT a drug name and NOT the metric
    cue itself.

    Strategy (deterministic, no clinical regex):
      1. Anchor on the metric-cue (`predicate`) occurrence nearest the numeric
         value when available; the subject of "X rate" / "X growth" / "X share"
         is the content noun IMMEDIATELY PRECEDING the cue ("unemployment rate"
         -> "unemployment"). This makes two sources stating the SAME metric on
         the SAME entity agree on the subject (so they can consolidate).
      2. Fall back to the nearest non-stopword, non-cue content token to the
         numeric anchor.
    Returns the lowercased token, or "unknown" when no content word is found
    (keeps the claim a SAFE SINGLETON — the conservative default, never a false
    merge)."""
    if not text:
        return "unknown"
    pred = (predicate or "").strip().lower()
    # 1. Noun immediately preceding the metric cue nearest the value.
    if pred:
        cue_pos = None
        best_cue_dist = 10 ** 9
        for m in re.finditer(re.escape(pred), text, flags=re.IGNORECASE):
            dist = abs(m.start() - anchor_pos)
            if dist < best_cue_dist:
                best_cue_dist = dist
                cue_pos = m.start()
        if cue_pos is not None:
            preceding = text[max(0, cue_pos - 60):cue_pos]
            toks = re.findall(r"[A-Za-z][A-Za-z0-9\-]{2,}", preceding)
            for tok in reversed(toks):
                low = tok.lower()
                if low in _GENERIC_SUBJECT_STOPWORDS or low == pred:
                    continue
                return low
    # 2. Nearest content token to the numeric anchor (excluding the cue word).
    lo = max(0, anchor_pos - window)
    hi = min(len(text), anchor_pos + window)
    local = text[lo:hi]
    anchor_local = anchor_pos - lo
    best_tok: Optional[str] = None
    best_dist = 10 ** 9
    for m in re.finditer(r"[A-Za-z][A-Za-z0-9\-]{2,}", local):
        tok = m.group(0)
        low = tok.lower()
        if low in _GENERIC_SUBJECT_STOPWORDS or low == pred:
            continue
        center = (m.start() + m.end()) // 2
        dist = abs(center - anchor_local)
        if dist < best_dist or (dist == best_dist and tok[:1].isupper()):
            best_dist = dist
            best_tok = tok
    return best_tok.lower() if best_tok else "unknown"


# Generic year / count reject: a bare 4-digit year or a number that is the
# obvious sample-size / date is NOT the measured metric value. Used to avoid
# keying a generic claim on a date or N when a real metric value is present.
_GENERIC_YEAR_RE = re.compile(r"^(19|20)\d{2}$")


def _looks_like_year_or_count(value: float, unit: str, window: str, pos: int) -> bool:
    """Heuristic: True if this number is most likely a YEAR or a bare sample
    count rather than a measured metric value. A unit-bearing number (percent /
    currency / magnitude) is always a real value. A bare 4-digit year, or a
    number immediately preceded by 'N=' / 'n=' / 'in 20YY' / 'sample of', is
    rejected so it cannot become the claim value/key."""
    if unit:
        return False  # a unit-bearing number is a real metric value
    s = str(int(value)) if value == int(value) else str(value)
    if _GENERIC_YEAR_RE.match(s):
        return True
    near = window[max(0, pos - 12):pos].lower()
    if "n=" in near or "n =" in near or "sample of" in near or "in 20" in near:
        return True
    return False


def _find_value_generic(
    text: str, cue_pos: Optional[int] = None,
) -> Optional[tuple[float, str, str, int]]:
    """Find the generic numeric value tied to the metric cue. Returns
    (value, normalized_unit, context_window, anchor_position) or None.

    B9 (Codex P1.4): pick the number NEAREST the metric cue (``cue_pos``) rather
    than the first number in the row, so a leading date / sample-size does not
    become the claim value/dedup key. A unit-bearing number is always preferred;
    bare years / 'N=' counts are skipped. When ``cue_pos`` is None, fall back to
    the first non-year/non-count number. NO clinical reject contexts. Pure."""
    if not text:
        return None
    # B13: the confidence-interval BOUND region(s) ("... CI 2-9", "... CI 5 to 12").
    # Numbers inside are interval bounds, not a measured outcome value.
    ci_regions = _ci_bound_regions(text)
    candidates: list[tuple[float, str, str, int]] = []
    for m in _GENERIC_VALUE_RE.finditer(text):
        raw = (m.group("value") or "").replace(",", "")
        try:
            value = float(raw)
        except ValueError:
            continue
        unit = _normalize_generic_unit(m.group("unit") or "")
        start_win = max(0, m.start() - 60)
        end_win = min(len(text), m.end() + 60)
        window = text[start_win:end_win]
        if _looks_like_year_or_count(value, unit, window, m.start() - start_win):
            continue
        # B13: skip a confidence-interval LEVEL ("95% CI" / "95 % confidence
        # interval"). It is the statistical confidence level, not a measured
        # outcome — anchored on THIS number's position so a real value elsewhere
        # in the row (the point estimate) is unaffected.
        if _is_confidence_level_at(text, m.start()):
            continue
        # B13: skip a CI BOUND that sits INSIDE the interval region (so "(95% CI
        # 2-9)" emits neither the 95 level nor the 2/-9 bounds). A real point
        # estimate outside the parenthetical is unaffected.
        if _in_ci_bound_region(m.start(), ci_regions):
            continue
        candidates.append((value, unit, window, m.start()))
    if not candidates:
        return None
    if cue_pos is None:
        return candidates[0]
    # Nearest candidate to the metric cue; a unit-bearing number wins a near tie.
    def _key(c: tuple[float, str, str, int]) -> tuple[int, int]:
        dist = abs(c[3] - cue_pos)
        return (dist, 0 if c[1] else 1)
    return min(candidates, key=_key)


def _extract_numeric_claims_generic(
    evidence: list[dict[str, Any]],
) -> list["ExtractedNumericClaim"]:
    """DOMAIN-AGNOSTIC numeric claim extraction for NON-clinical corpora.

    One claim per row at most (the first generic metric value), keyed on a
    generic predicate + generic subject + value + unit. A row with no generic
    metric cue OR no extractable number yields NO claim (kept as a safe
    singleton upstream). The clinical discriminator fields (dose / arm / Wave-3)
    stay at their UNKNOWN defaults so they never anchor a non-clinical merge —
    a non-clinical merge is anchored ONLY by a confidently-extracted
    subject+predicate+value+unit (the conservative rule). NO clinical literal.
    """
    claims: list[ExtractedNumericClaim] = []
    for ev in evidence:
        quote = ev.get("direct_quote") or ev.get("statement") or ""
        if not quote:
            continue
        predicate = _normalize_predicate_generic(quote)
        if not predicate:
            continue
        # Anchor the value on the number nearest the metric cue (Codex P1.4) so
        # a leading date / sample-size cannot become the claim value/key.
        _cue_m = re.search(re.escape(predicate), quote, flags=re.IGNORECASE)
        _cue_pos = _cue_m.start() if _cue_m else None
        found = _find_value_generic(quote, cue_pos=_cue_pos)
        if found is None:
            continue
        value, unit, ctx_window, anchor_pos = found
        subject = _subject_generic(quote, anchor_pos, predicate=predicate)
        # Codex iter-3 P1: do NOT set endpoint_phrase=predicate. The metric cue
        # IS the predicate, not a time-window/endpoint. Stamping it as
        # endpoint_phrase would make _shared_metric_axes read two same-predicate
        # generic claims as POSITIVELY-confirmed shared scope -> a hard
        # contradiction, when in fact their comparator/population/time-window are
        # UNCONFIRMED. Leaving the discriminator axes empty means an unconfirmed
        # generic numeric gap is correctly labeled possible_metric_mismatch
        # (conservative non-clinical default); a true contradiction needs a
        # positively-extracted shared scope axis. The predicate itself still
        # groups the claims (grouping key includes predicate).
        claims.append(ExtractedNumericClaim(
            evidence_id=str(ev.get("evidence_id", "")),
            subject=subject,
            predicate=predicate,
            value=value,
            unit=unit,
            context_snippet=ctx_window[:200],
            source_url=ev.get("source_url", ""),
            source_tier=ev.get("tier", ""),
        ))
    return claims


# Predicate keywords — the ones we most want to catch contradictions on.
# BUG-M-202 fix (deep-dive R7): expanded coverage beyond the original
# obesity/cardiometabolic-only set. A proper domain-YAML-driven
# profile loader is tracked as a follow-up (see docs/todo_list.md);
# this expansion is the minimum-viable fix to close the AF
# anticoagulation silent-failure reproducer.
_EFFICACY_PREDICATES_METABOLIC = (
    # Original obesity / GLP-1 / lipid
    "weight loss", "body weight", "weight reduction",
    "hba1c reduction", "a1c reduction",
    "systolic blood pressure reduction", "diastolic blood pressure reduction",
    "ldl reduction", "cholesterol reduction",
    "cardiovascular risk reduction", "mace reduction",
    "mortality reduction",
)

_EFFICACY_PREDICATES_ANTICOAGULATION = (
    # AF anticoagulation + guideline endpoints (BUG-M-202 R7)
    "stroke rate", "stroke risk", "ischemic stroke",
    "systemic embolism", "stroke or systemic embolism",
    "major bleeding", "clinically relevant non-major bleeding",
    "intracranial hemorrhage", "gastrointestinal bleeding",
    "time in therapeutic range", "ttr", "inr",
    "cha2ds2-vasc", "has-bled",
    "hazard ratio", "relative risk", "odds ratio",
)

_EFFICACY_PREDICATES_TECH = (
    # Tech / ML benchmark endpoints
    "accuracy", "f1 score", "f1-score",
    "precision", "recall", "auc", "roc auc",
    "error rate", "latency", "throughput",
    "inference time", "model size",
    "perplexity", "exact match",
    "exact-match accuracy",
)

_EFFICACY_PREDICATES_POLICY = (
    # Policy / regulatory quantitative endpoints
    "compliance rate", "adoption rate", "enforcement rate",
    "penalty rate", "coverage rate", "participation rate",
    "emissions reduction", "cost savings",
)

_EFFICACY_PREDICATES_DD = (
    # Due diligence / financial endpoints
    "revenue growth", "ebitda margin", "gross margin",
    "operating margin", "market share",
    "customer acquisition cost", "churn rate",
    "debt-to-equity", "cash flow",
)

_EFFICACY_PREDICATES = (
    _EFFICACY_PREDICATES_METABOLIC
    + _EFFICACY_PREDICATES_ANTICOAGULATION
    + _EFFICACY_PREDICATES_TECH
    + _EFFICACY_PREDICATES_POLICY
    + _EFFICACY_PREDICATES_DD
)

_SAFETY_PREDICATES_METABOLIC = (
    "incidence of nausea", "incidence of vomiting",
    "discontinuation rate", "adverse event rate",
    "serious adverse event rate", "pancreatitis incidence",
    "hypoglycemia incidence", "thyroid c-cell",
)

_SAFETY_PREDICATES_ANTICOAGULATION = (
    "bleeding rate", "fatal bleeding", "mortality",
    "all-cause mortality", "cardiovascular mortality",
)

_SAFETY_PREDICATES = (
    _SAFETY_PREDICATES_METABOLIC
    + _SAFETY_PREDICATES_ANTICOAGULATION
)

# Per-domain predicate set for the `domain` kwarg. The union is still
# the default when no domain is passed (backward-compat).
_DOMAIN_PREDICATES: dict[str, tuple] = {
    "clinical": (
        _EFFICACY_PREDICATES_METABOLIC
        + _EFFICACY_PREDICATES_ANTICOAGULATION
        + _SAFETY_PREDICATES_METABOLIC
        + _SAFETY_PREDICATES_ANTICOAGULATION
    ),
    "tech": _EFFICACY_PREDICATES_TECH,
    "policy": _EFFICACY_PREDICATES_POLICY,
    "due_diligence": _EFFICACY_PREDICATES_DD,
}


@dataclass
class ExtractedNumericClaim:
    """A claim like 'X causes Y-value-unit change in Z' extracted from evidence."""

    evidence_id: str
    subject: str      # e.g., "semaglutide"
    predicate: str    # e.g., "weight loss"
    value: float
    unit: str         # "%", "mg", "weeks", etc.
    context_snippet: str  # original text for display
    source_url: str = ""
    source_tier: str = ""
    dose: str = ""             # "2.4 mg", "7.2 mg", or "" if not present
    # arm: legacy default "treatment"; "comparator_adjacent" only when a
    # placebo/comparator cue fired. Kept at the LEGACY default (NOT None) for
    # OFF byte-identity: the OFF-path legacy key _normalized_key_numeric reads
    # ``arm`` into position 7 of the SHA-1-hashed cluster key
    # (claim_graph.py:241) and honest_pipeline/run_honest_sweep_r3 asdict it
    # into contradictions.json — so changing this default to None drifts the OFF
    # cluster ids + serialized bytes (Codex Slice-B P1). Flag-ON consolidation
    # is unaffected: claim_graph._unknown_arm treats "treatment" (the default,
    # never-cued) AS UNKNOWN, so a defaulted arm still forces a singleton and
    # only a positively-extracted "comparator_adjacent" anchors a merge
    # (design §4.3, the arm lesson — fail-closed without the None change).
    arm: str = "treatment"     # "treatment" (default/no-cue), "comparator_adjacent" (cue)
    endpoint_phrase: str = ""  # e.g., "at week 68", "from baseline", "mean change"
    # ── Wave-3 positive-known discriminator fields (I-arch-002 [1]) ──────────
    # All default '' = UNKNOWN sentinel. Dormant carriers: no consumer reads
    # them until claim_graph.build_merge_key reads them under
    # PG_SWEEP_CREDIBILITY_REDESIGN. A value is set ONLY when a positive token
    # was extracted (never derived/defaulted) per design §4.3.
    dose_frequency: str = ""    # "qd"/"bid"/"weekly"/... cadence token; '' = UNKNOWN
    comparator: str = ""        # the "vs X" comparator phrase; '' = UNKNOWN
    route_formulation: str = "" # "iv"/"po"/"sc"/"er"/...; '' = UNKNOWN
    effect_measure: str = ""    # "relative"/"absolute"/"hr"/"or"/"raw"; '' = UNKNOWN
    direction: str = ""         # "increase"/"decrease" TOKEN-only; '' = UNKNOWN
    population: str = ""         # "patients with X" cohort phrase; '' = UNKNOWN


@dataclass
class ContradictionRecord:
    """Two claims that contradict on the same (subject, predicate)."""

    subject: str
    predicate: str
    claims: list[ExtractedNumericClaim]
    relative_difference: float      # 0.0-1.0+ (|a-b|/min(|a|,|b|))
    absolute_difference: float
    severity: str                   # "low" / "medium" / "high"
    recommended_action: str = (
        "Disclose both values with their source tiers in the final report. "
        "If one source is T1 (RCT) and another is T5 (industry), note the "
        "authority gap alongside the numeric gap."
    )
    # ── A17 commensurability guard (I-arch-006 #1262) ────────────────────────
    # not_comparable=True marks a group whose claims carry POSITIVELY-DIVERGENT
    # physical quantity kinds (e.g. a 0.5-degree yaw angle bucketed with a 100 m
    # radar distance because both flattened to unit="") — an INCOMMENSURABLE
    # pairing. The numeric gap across such a pairing is a category error (the run
    # surfaced absolute_difference 99.5 / 199% relative across degrees-vs-meters),
    # so when this fires the surfaced relative_difference/absolute_difference are
    # nulled to None (no misleading magnitude) and the record is kept OUT of the
    # headline contradiction count — but every claim/source is still DISCLOSED
    # (never dropped). This is a VALIDITY/WEIGHT check, NOT a faithfulness-gate
    # change: strict_verify / NLI / 4-role thresholds are untouched, and a real
    # same-quantity contradiction is unaffected (both default fields stay False/"").
    not_comparable: bool = False
    incommensurable_reason: str = ""


# The Wave-3 dormant discriminator fields added to ExtractedNumericClaim (I-arch-002 [2]).
# They are read ONLY by claim_graph.build_merge_key under PG_SWEEP_CREDIBILITY_REDESIGN and
# must NOT appear in ANY serialized artifact on the OFF path, or OFF byte-identity breaks
# (the legacy contradictions.json never had these keys). asdict() emits EVERY dataclass
# field, so every site that serializes a ContradictionRecord routes through
# serialize_contradiction_record() which strips them when the flag is OFF.
_WAVE3_DORMANT_NUMERIC_FIELDS = (
    "dose_frequency", "comparator", "route_formulation",
    "effect_measure", "direction", "population",
)


# A17 record-level commensurability fields (I-arch-006 #1262). asdict() emits
# every dataclass field, so to preserve byte-identity for the legacy / clinical /
# comparable records (whose JSON never had these keys) they are STRIPPED whenever
# they sit at their inert defaults (not_comparable=False AND empty reason). They
# are emitted ONLY on a record where the A17 guard positively fired — the new,
# correct behavior is allowed to add keys exactly on the records it changed.
_A17_RECORD_FIELDS = ("not_comparable", "incommensurable_reason")


def serialize_contradiction_record(record: "ContradictionRecord") -> dict:
    """asdict a numeric ContradictionRecord for contradictions.json / manifest / PT08.

    When PG_SWEEP_CREDIBILITY_REDESIGN is OFF the Wave-3 dormant discriminator fields are
    STRIPPED from each nested claim so the serialized bytes are byte-identical to the
    pre-Slice-B tree (Claude Slice-B iter-2 Fix C). When ON the full field set is emitted
    (the redesign is the new behavior; ON is allowed to differ). endpoint_phrase/arm are
    pre-existing and always retained.

    A17 (I-arch-006 #1262): the record-level commensurability fields
    (not_comparable / incommensurable_reason) are stripped whenever they carry their
    inert defaults, so a comparable / clinical record serializes byte-identically to
    the pre-A17 tree; they appear ONLY on a record the A17 guard actually marked.
    """
    d = asdict(record)
    if not _credibility_redesign_enabled():
        for claim in d.get("claims", []) or []:
            for fname in _WAVE3_DORMANT_NUMERIC_FIELDS:
                claim.pop(fname, None)
    # A17: keep inert (default) records byte-identical — strip the new keys unless
    # the guard positively fired on THIS record.
    if not d.get("not_comparable") and not (d.get("incommensurable_reason") or ""):
        for fname in _A17_RECORD_FIELDS:
            d.pop(fname, None)
    return d


# ─────────────────────────────────────────────────────────────────────────────
# Extraction
# ─────────────────────────────────────────────────────────────────────────────


def _normalize_predicate(
    text: str, domain: str | None = None,
) -> Optional[str]:
    """Return the predicate keyword if present in the text.

    BUG-M-202 fix (deep-dive R7): when a domain is supplied, prefer
    domain-specific predicates first (higher specificity), then fall
    back to the union set. Previously, only the metabolic-centric
    union was checked — so AF anticoagulation queries returned zero
    matches because stroke/bleeding vocabulary wasn't in the table.
    """
    t = (text or "").lower()
    # Domain-specific first (more specific endpoints win ties).
    if domain and domain in _DOMAIN_PREDICATES:
        for p in _DOMAIN_PREDICATES[domain]:
            if p in t:
                return p
    # Fall back to union.
    for p in _EFFICACY_PREDICATES + _SAFETY_PREDICATES:
        if p in t:
            return p
    return None


def _normalize_subject(
    text: str, fallback: str = "unknown", general_fallback: bool = False,
) -> str:
    """Extract the salient subject of the clause: the first drug name, or fallback.

    This is the legacy API used when no positional anchor is available.
    Prefer _subject_near_position() when you know where the numeric value
    is and want to attribute the number to the nearest drug, not the
    first drug to appear in the wider text.

    B13 (I-arch-011) DOMAIN-GENERAL SUBJECT: ``general_fallback`` is OPT-IN and
    defaults False so EVERY pre-existing caller (the clinical numeric path via
    ``_subject_near_position`` line 621, and any other consumer) is byte-identical
    — the drug-name-only behaviour and its ``fallback`` are unchanged. When the
    caller opts in (the qualitative present-vs-absent detector, which runs on
    device / procedure / population corpora where NO drug name appears), and the
    drug allowlist finds nothing, we fall back to the in-file DOMAIN-AGNOSTIC noun
    extractor (``_subject_general_noun``) instead of the empty/`fallback` string.
    Without this, a non-drug clinical corpus (e.g. Parkinson / deep-brain-
    stimulation safety) resolved EVERY qualitative assertion's subject to "" — so
    Pass A (which skips empty-subject assertions) never fired and Pass B collapsed
    every unrelated flag into one ``("", concept_type)`` bucket: real T1 safety
    signals ("DBS is contraindicated in X") were diluted into indistinguishable
    noise. Drug-name precedence is preserved (a named drug still wins), so the
    existing clinical golden behaviour is unchanged. The contradiction surface is
    ADVISORY (labels, never drops/holds): a real entity subject only makes a true
    safety contradiction VISIBLE; faithfulness gates are untouched.
    """
    from src.polaris_graph.nodes.scope_gate import _DRUG_NAME_RE
    m = _DRUG_NAME_RE.search(text or "")
    if m:
        return m.group(1).lower()
    if general_fallback:
        noun = _subject_general_noun(text)
        if noun:
            return noun
    return fallback


# B13 (I-arch-011): light, dependency-free clause-subject (noun-phrase head)
# extraction for ANY domain (device / procedure / population / drug). Consistent
# with the in-file ``_subject_generic`` machinery (reuses ``_GENERIC_SUBJECT_STOPWORDS``)
# and the field-agnostic 2025 noun-phrase-head approach (head noun + descriptors,
# no parser): the salient subject of an English clause is overwhelmingly the
# noun-phrase head before the main verb. We take the FIRST content token (skipping
# generic statistical / temporal / filler stopwords) — deterministic, so the SAME
# entity phrased the same way ("DBS …" on both sides) resolves to the SAME token
# and the two assertions group/conflict. Acronyms / proper nouns are preferred so
# "DBS" / "Levodopa" win over a leading lowercase filler. Returns "" when no
# content token is found (a SAFE empty — the caller keeps its own fallback).
_SUBJECT_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9\-]{1,}")


def _subject_general_noun(text: str) -> str:
    """First salient content-word subject token of the clause, or "" if none.

    Domain-agnostic, deterministic, no LLM, no parser, never raises. Skips the
    shared generic statistical/temporal/measurement filler stopwords so a real
    entity (device, procedure, population, condition) anchors the subject. An
    ALL-CAPS acronym or a Capitalized proper noun in the clause is preferred over
    a leading lowercase common word (e.g. "DBS" over "the"), because the named
    entity is the safety subject the reader cares about."""
    if not text:
        return ""
    tokens = _SUBJECT_TOKEN_RE.findall(text)
    first_content: str = ""
    for tok in tokens:
        low = tok.lower()
        if low in _GENERIC_SUBJECT_STOPWORDS:
            continue
        # Prefer a named entity (acronym / proper noun) if one appears in-clause.
        if tok.isupper() or tok[:1].isupper():
            return low
        if not first_content:
            first_content = low
    return first_content


def _subject_near_position(
    text: str,
    anchor_pos: int,
    fallback: str = "unknown",
    window: int = 150,
) -> str:
    """R-5 Fix B: return the drug name whose match is CLOSEST to
    anchor_pos in `text`, within ±window chars.

    Used for cross-drug comparisons like:
        "Eli Lilly's Zepbound achieving 25.5% compared to Novo Nordisk's
        CagriSema at 23%, with Lilly's retatrutide at 28.7% and ..."

    Legacy `_normalize_subject(quote)` would return the first drug in
    the full quote (often 'retatrutide' here, even though 25.5% belongs
    to Zepbound). This function searches all drug matches inside the
    ±window chars around anchor_pos and returns the match with the
    smallest absolute distance.

    Falls back to _normalize_subject(text) (first-in-text) only if
    ZERO matches are found inside the window. Returns `fallback` if
    still nothing.
    """
    from src.polaris_graph.nodes.scope_gate import _DRUG_NAME_RE

    if not text:
        return fallback
    lo = max(0, anchor_pos - window)
    hi = min(len(text), anchor_pos + window)
    local = text[lo:hi]
    matches = list(_DRUG_NAME_RE.finditer(local))
    if not matches:
        # Widen search to full text as last resort
        return _normalize_subject(text, fallback)
    # Pick the match whose center is closest to the (anchor_pos - lo)
    # position inside `local`.
    anchor_local = anchor_pos - lo
    best = min(
        matches,
        key=lambda m: abs(((m.start() + m.end()) // 2) - anchor_local),
    )
    return best.group(1).lower()


# Fix-1 reject patterns. Numbers that sit inside these contexts are
# filtered BEFORE we pull the value, because they're structurally not
# the claim-under-measurement:
#   - "placebo N%" / "vs placebo" / "versus placebo" → comparator arm
#   - "≥5%" / "at least 5%" / "5% or more" / "5% threshold" → achievement
#     threshold, not the value being measured
#   - "STEP N" / "SUSTAIN N" → trial-program integer, not a value
#   - "week N" / "month N" / "year N" → duration
_PLACEBO_CONTEXT_RE = re.compile(
    r"(?:vs\.?|versus|v\.)\s+placebo|"
    r"placebo\s+(?:recipients|group|arm|patients)|"
    r"in\s+(?:the\s+)?placebo",
    re.IGNORECASE,
)
_ACHIEVEMENT_THRESHOLD_RE = re.compile(
    r"(?:at\s+least|≥|>=|>)\s*-?\d+(?:\.\d+)?\s*%|"
    r"-?\d+(?:\.\d+)?\s*%\s*(?:or\s+more|or\s+greater|threshold|achievement)",
    re.IGNORECASE,
)
_TRIAL_ACRONYM_NUM_RE = re.compile(
    r"\b(?:STEP|SUSTAIN|SURPASS|SURMOUNT|REWIND|LEADER|PIONEER|SELECT)\s*-?\s*\d+",
    re.IGNORECASE,
)
_DURATION_NUM_RE = re.compile(
    r"(?:week|month|year|day)s?\s+-?\d+(?:\.\d+)?|"
    r"-?\d+(?:\.\d+)?\s*(?:week|month|year|day)s?",
    re.IGNORECASE,
)
# B13 (I-arch-011) confidence-interval reject. A "95% CI" / "95 % confidence
# interval" token is the STATISTICAL CONFIDENCE LEVEL, not a measured outcome
# value — the run misparsed the "95%" in "Mortality reduction (95% CI 2-9)" as a
# 95% mortality value, then flagged a fake 3-contradiction artifact against a real
# single-digit mortality figure. We reject a number that is the confidence LEVEL
# directly before a CI / confidence-interval cue. We DO NOT reject a number merely
# because the wider sentence contains a CI elsewhere (that would suppress the real
# point estimate "8%" in "reduced to 8% (95% CI 5-12)"), and we DO NOT reject a
# plain "95% of patients" value (no CI cue). Word-boundary "CI" only, so it never
# fires on an unrelated capitalised "Ci"-prefixed token mid-word.
_CONFIDENCE_INTERVAL_LEVEL_RE = re.compile(
    r"-?\d+(?:\.\d+)?\s*%?\s*"
    r"(?:\bci\b|confidence\s+interval|credible\s+interval)",
    re.IGNORECASE,
)


def _is_confidence_level_at(text: str, num_pos: int) -> bool:
    """True iff the number at ``num_pos`` in ``text`` is the confidence LEVEL of a
    confidence/credible interval ("95% CI", "95 % confidence interval").

    Anchored on the number's own position: a CI cue elsewhere in the row does NOT
    reject a real point-estimate value. Pure, never raises."""
    if not text:
        return False
    for m in _CONFIDENCE_INTERVAL_LEVEL_RE.finditer(text):
        if m.start() == num_pos:
            return True
    return False


# The CI cue token itself ("CI" / "confidence interval" / "credible interval"),
# used to mark the START of a CI BOUND region. The region runs from the cue to the
# closing parenthesis/bracket (or the next ';' / sentence end), so the interval
# BOUNDS inside it ("2-9", "5 to 12") are not emitted as metric values either.
_CI_CUE_RE = re.compile(
    r"\b(?:ci|confidence\s+interval|credible\s+interval)\b", re.IGNORECASE,
)


def _ci_bound_regions(text: str) -> list[tuple[int, int]]:
    """Char spans that hold confidence/credible-interval BOUNDS (not a value).

    Each region starts just after a CI cue and ends at the next closing ``)``/``]``
    (or ``;`` / sentence end) — the numbers inside are interval bounds, not a
    measured outcome. Pure, never raises."""
    regions: list[tuple[int, int]] = []
    for m in _CI_CUE_RE.finditer(text or ""):
        start = m.end()
        end = len(text)
        for ch_pos in range(start, len(text)):
            if text[ch_pos] in ")];":
                end = ch_pos
                break
        regions.append((start, end))
    return regions


def _in_ci_bound_region(num_pos: int, regions: list[tuple[int, int]]) -> bool:
    """True iff ``num_pos`` falls inside any CI-bound region. Pure."""
    return any(lo <= num_pos < hi for lo, hi in regions)


# A valid claim usually carries a value-phrase verb. "Achieved 14.9%",
# "reduced by 12%", "loss of 15%", "mean change -14.9%". This
# whitelist prevents us from pulling random decimals that happen to be
# in the quote.
_VALUE_PHRASE_VERBS = re.compile(
    r"(?:achiev\w+|reduc\w+|los[ts]?|loss|decreas\w+|"
    r"mean\s+(?:change|weight|reduction|loss|difference)|"
    r"experienc\w+\s+a?\s*\d+|"
    r"reported|produc\w+|demonstrat\w+|"
    r"at\s+(?:week|month|year)\s+\d+)",
    re.IGNORECASE,
)

# ── Wave-3 master flag (I-arch-002) ──────────────────────────────────────────
# Read at CALL time (never import-time) so tests can monkeypatch os.environ and
# the OFF path is honoured per-invocation. Mirrors
# credibility_pass._OFF_VALUES semantics; inlined here to avoid importing the
# synthesis layer into retrieval (no cross-layer / circular-import coupling).
_CRED_REDESIGN_FLAG = "PG_SWEEP_CREDIBILITY_REDESIGN"
_CRED_REDESIGN_OFF_VALUES = frozenset({"", "0", "false", "off", "no"})


def _credibility_redesign_enabled() -> bool:
    """True when PG_SWEEP_CREDIBILITY_REDESIGN is on. OFF => byte-identical."""
    return (
        os.environ.get(_CRED_REDESIGN_FLAG, "").strip().lower()
        not in _CRED_REDESIGN_OFF_VALUES
    )


# Dose pattern (captures the full "X.X mg" string for grouping).
_DOSE_CAPTURE_RE = re.compile(
    r"(\d+(?:\.\d+)?\s*m[gc]g?|\d+(?:\.\d+)?\s*[µu]g|\d+(?:\.\d+)?\s*g\b)",
    re.IGNORECASE,
)

# Wave-3 variant (I-arch-002 [2], DRIFT-MGKG): preserves a per-weight ('/kg') or
# per-time ('/day','/m2',...) denominator so '5 mg/kg' is DISTINCT from '5 mg'
# (design §4.1/§4.3 — prevents a false dose-response merge). This change feeds
# the LEGACY detect_contradictions grouping key (:596 includes dose) and is
# therefore NOT byte-inert when the master flag is OFF; per the non-negotiable
# byte-identity rule it is GATED behind PG_SWEEP_CREDIBILITY_REDESIGN. When the
# flag is OFF the original _DOSE_CAPTURE_RE path runs verbatim.
_DOSE_CAPTURE_MGKG_RE = re.compile(
    r"(\d+(?:\.\d+)?\s*m[gc]g?|\d+(?:\.\d+)?\s*[µu]g|\d+(?:\.\d+)?\s*g\b)"
    r"(\s*/\s*(?:kg|m2|m\^?2|day|d|hr?|h|dose|week|wk))?",
    re.IGNORECASE,
)


def _extract_dose(text: str) -> str:
    """Extract the most-salient dose token from the text (for grouping).

    DRIFT-MGKG (I-arch-002 [2]): under PG_SWEEP_CREDIBILITY_REDESIGN a trailing
    per-weight/per-time denominator ('/kg', '/m2', ...) is preserved so
    '5 mg/kg' != '5 mg'. Flag OFF => original behaviour byte-for-byte.
    """
    if _credibility_redesign_enabled():
        m = _DOSE_CAPTURE_MGKG_RE.search(text or "")
        if not m:
            return ""
        base = m.group(1)
        denom = m.group(2) or ""
        # Normalize internal whitespace out of the denominator ('  / kg' -> '/kg')
        denom = re.sub(r"\s+", "", denom)
        return (base + denom).replace(" ", " ").lower()
    m = _DOSE_CAPTURE_RE.search(text or "")
    if not m:
        return ""
    return m.group(1).replace(" ", " ").lower()


def _detect_placebo_arm(text: str) -> bool:
    if not text:
        return False
    return bool(_PLACEBO_CONTEXT_RE.search(text))


# Pre-existing endpoint patterns (legacy; OFF path uses ONLY these).
_ENDPOINT_PATTERNS_LEGACY = (
    r"at\s+week\s+\d+", r"at\s+\d+\s+weeks?",
    r"at\s+month\s+\d+", r"at\s+\d+\s+months?",
    r"from\s+baseline", r"mean\s+change",
    r"intent\s*-?\s*to\s*-?\s*treat",
    r"per\s+protocol",
    r"trial\s+product\s+estimand",
)
# Wave-3 (I-arch-002 [2]): day + year endpoint patterns. They are appended AFTER the
# legacy patterns so they only fire when no legacy pattern matched, BUT they still
# change the OFF output for inputs that previously returned "" (e.g. "at day 28" with
# no week/month phrase) — and endpoint_phrase feeds BOTH the legacy cluster key
# (_normalized_key_numeric position 7) AND contradictions.json (asdict). Per the
# non-negotiable byte-identity rule they are therefore GATED behind
# PG_SWEEP_CREDIBILITY_REDESIGN (Claude Slice-B iter-2 P1); OFF runs the legacy set
# verbatim.
_ENDPOINT_PATTERNS_WAVE3 = (
    r"at\s+day\s+\d+", r"at\s+\d+\s+days?",
    r"at\s+year\s+\d+", r"at\s+\d+\s+years?",
)


def _extract_endpoint_phrase(text: str) -> str:
    """Extract a short endpoint descriptor ('at week 68', 'from baseline').

    The day/year forms are GATED behind PG_SWEEP_CREDIBILITY_REDESIGN (they would
    otherwise resolve previously-"" inputs and drift the OFF cluster key + serialized
    bytes — Claude Slice-B iter-2 P1). Flag OFF => legacy patterns only, byte-for-byte.
    """
    if not text:
        return ""
    low = text.lower()
    patterns = _ENDPOINT_PATTERNS_LEGACY
    if _credibility_redesign_enabled():
        patterns = patterns + _ENDPOINT_PATTERNS_WAVE3
    for pat in patterns:
        m = re.search(pat, low)
        if m:
            return m.group(0)
    return ""


# ─────────────────────────────────────────────────────────────────────────────
# Wave-3 positive-known discriminator extractors (I-arch-002 [2])
#
# Each returns '' (the UNKNOWN sentinel) unless a POSITIVE token was extracted.
# A defaulted or PREDICATE-DERIVED value is NOT "known" (design §4.3): these
# extractors read the evidence text ONLY, never the predicate. Dormant carriers
# until claim_graph.build_merge_key reads them under PG_SWEEP_CREDIBILITY_REDESIGN.
# ─────────────────────────────────────────────────────────────────────────────

# Dosing cadence (per-time schedule). Orthogonal to the per-mass dose axis:
# "15 mg weekly" != "15 mg daily" (the ISMP methotrexate sentinel error).
_DOSE_FREQUENCY_RE = re.compile(
    r"\b(?P<tok>"
    r"q\.?d\.?|b\.?i\.?d\.?|t\.?i\.?d\.?|q\.?i\.?d\.?|"   # latin abbreviations
    r"q\s*\d+\s*h|q\s*\d+\s*hours?|"                       # q8h / q 12 hours
    r"once[-\s]?(?:daily|a\s+day|per\s+day|weekly|a\s+week)|"
    r"twice[-\s]?(?:daily|a\s+day|per\s+day|weekly|a\s+week)|"
    r"three\s+times[-\s]?(?:daily|a\s+day|per\s+day)|"
    r"daily|weekly|biweekly|fortnightly|monthly"
    r")\b",
    re.IGNORECASE,
)

# Normalize a matched cadence token to a canonical key.
_DOSE_FREQUENCY_NORMALIZE = (
    (re.compile(r"^q\.?d\.?$", re.IGNORECASE), "qd"),
    (re.compile(r"^b\.?i\.?d\.?$", re.IGNORECASE), "bid"),
    (re.compile(r"^t\.?i\.?d\.?$", re.IGNORECASE), "tid"),
    (re.compile(r"^q\.?i\.?d\.?$", re.IGNORECASE), "qid"),
    (re.compile(r"^q\s*(\d+)\s*h(?:ours?)?$", re.IGNORECASE), r"q\1h"),
    (re.compile(r"^once[-\s]?(?:daily|a\s+day|per\s+day)$", re.IGNORECASE), "qd"),
    (re.compile(r"^twice[-\s]?(?:daily|a\s+day|per\s+day)$", re.IGNORECASE), "bid"),
    (re.compile(r"^three\s+times[-\s]?(?:daily|a\s+day|per\s+day)$", re.IGNORECASE), "tid"),
    (re.compile(r"^once[-\s]?(?:weekly|a\s+week)$", re.IGNORECASE), "weekly"),
    (re.compile(r"^twice[-\s]?(?:weekly|a\s+week)$", re.IGNORECASE), "biweekly"),
)


def _extract_dose_frequency(text: str) -> str:
    """Cadence token (qd/bid/tid/q\\d+h/once-daily/weekly/...) or '' if none."""
    if not text:
        return ""
    m = _DOSE_FREQUENCY_RE.search(text)
    if not m:
        return ""
    raw = re.sub(r"\s+", " ", m.group("tok").strip()).lower()
    for pat, repl in _DOSE_FREQUENCY_NORMALIZE:
        if pat.match(raw):
            return pat.sub(repl, raw)
    return raw


# Comparator: "vs X" / "versus X" / "compared to X". Captures the comparator
# noun phrase (short, stops at clause punctuation).
_COMPARATOR_RE = re.compile(
    r"(?:vs\.?|versus|compared\s+(?:to|with)|relative\s+to)\s+"
    r"(?P<comp>[a-z0-9][a-z0-9\-\s]{0,40}?)"
    r"(?=[,.;:)\]]|\s+(?:at|in|with|for|over|by|and|was|were|achiev|reduc)\b|$)",
    re.IGNORECASE,
)


def _extract_comparator(text: str) -> str:
    """The 'vs/versus/compared-to X' comparator phrase, or '' if none."""
    if not text:
        return ""
    m = _COMPARATOR_RE.search(text)
    if not m:
        return ""
    return re.sub(r"\s+", " ", m.group("comp").strip()).lower()


# Route / formulation: IV / PO / SC / IM / ER / XR / SR, plus spelled-out forms.
_ROUTE_FORMULATION_RE = re.compile(
    r"\b(?P<tok>"
    r"i\.?v\.?|intravenous(?:ly)?|"
    r"p\.?o\.?|per\s+os|oral(?:ly)?|by\s+mouth|"
    r"s\.?c\.?|subcutaneous(?:ly)?|subq|"
    r"i\.?m\.?|intramuscular(?:ly)?|"
    r"e\.?r\.?|x\.?r\.?|s\.?r\.?|"
    r"extended[-\s]?release|sustained[-\s]?release|immediate[-\s]?release"
    r")\b",
    re.IGNORECASE,
)
_ROUTE_FORMULATION_NORMALIZE = (
    (re.compile(r"^(?:i\.?v\.?|intravenous(?:ly)?)$", re.IGNORECASE), "iv"),
    (re.compile(r"^(?:p\.?o\.?|per\s+os|oral(?:ly)?|by\s+mouth)$", re.IGNORECASE), "po"),
    (re.compile(r"^(?:s\.?c\.?|subcutaneous(?:ly)?|subq)$", re.IGNORECASE), "sc"),
    (re.compile(r"^(?:i\.?m\.?|intramuscular(?:ly)?)$", re.IGNORECASE), "im"),
    (re.compile(r"^(?:e\.?r\.?|extended[-\s]?release)$", re.IGNORECASE), "er"),
    (re.compile(r"^(?:x\.?r\.?)$", re.IGNORECASE), "xr"),
    (re.compile(r"^(?:s\.?r\.?|sustained[-\s]?release)$", re.IGNORECASE), "sr"),
    (re.compile(r"^immediate[-\s]?release$", re.IGNORECASE), "ir"),
)


def _extract_route_formulation(text: str) -> str:
    """Route/formulation token (iv/po/sc/im/er/...) or '' if none."""
    if not text:
        return ""
    m = _ROUTE_FORMULATION_RE.search(text)
    if not m:
        return ""
    raw = re.sub(r"\s+", " ", m.group("tok").strip()).lower()
    for pat, repl in _ROUTE_FORMULATION_NORMALIZE:
        if pat.match(raw):
            return repl
    return raw


# Effect measure: relative / absolute / HR / OR / RR / raw — ONLY on an EXPLICIT
# measure word. "30% relative risk reduction" != "30% absolute risk reduction".
_EFFECT_MEASURE_RE = (
    (re.compile(r"\brelative\s+risk\s+reduction\b|\brelative\s+reduction\b|"
                r"\brelative\s+risk\b|\brrr\b", re.IGNORECASE), "relative"),
    (re.compile(r"\babsolute\s+risk\s+reduction\b|\babsolute\s+reduction\b|"
                r"\babsolute\s+risk\b|\barr\b", re.IGNORECASE), "absolute"),
    (re.compile(r"\bhazard\s+ratio\b|\bhr\b", re.IGNORECASE), "hr"),
    (re.compile(r"\bodds\s+ratio\b|\bor\b", re.IGNORECASE), "or"),
    (re.compile(r"\brisk\s+ratio\b|\brate\s+ratio\b|\brr\b", re.IGNORECASE), "rr"),
)


def _extract_effect_measure(text: str) -> str:
    """Effect-measure type (relative/absolute/hr/or/rr) on explicit word, else ''."""
    if not text:
        return ""
    for pat, label in _EFFECT_MEASURE_RE:
        if pat.search(text):
            return label
    return ""


# Direction: EXPLICIT clinical increase/decrease token ONLY. NEVER inferred from
# the predicate (design §4.3 — the predicate-derived fallback made "rose 5%" and
# "fell 5%" merge and broke design test #5).
#
# Codex Slice-B P1 (over-merge narrowing): BARE QUANTITY COMPARATIVES + ambiguous
# nouns are EXCLUDED — "more"/"less"/"fewer" (a magnitude comparison, not a
# clinical direction) and "loss"/"lost" (the outcome NOUN, e.g. "weight loss" is
# the predicate, not a fall in a metric). Including them converted an otherwise-
# UNKNOWN direction into a positive discriminator, making two distinct claims
# merge-eligible instead of safe singletons. The retained tokens are explicit
# directional verbs/adjectives only (increased/decreased/rose/fell/reduced/
# reduction/elevated/declined/lowered/raised + clear motion synonyms). Unknown
# direction returns '' so the merge-key slot forces a singleton (safe under-merge).
_DIRECTION_INCREASE_RE = re.compile(
    r"\b(?:increas\w+|rose|rise|risen|rising|higher|elevat\w+|"
    r"rais\w+|up\s+by|grew|grow\w*)\b",
    re.IGNORECASE,
)
_DIRECTION_DECREASE_RE = re.compile(
    r"\b(?:decreas\w+|reduc\w+|reduction|fell|fall\w*|fallen|drop\w*|lower\w*|"
    r"declin\w+|down\s+by|shrank|shrunk)\b",
    re.IGNORECASE,
)


def _extract_direction(text: str) -> str:
    """'increase'/'decrease' from an EXPLICIT token only; '' if none/ambiguous.

    Token-only by design (§4.3): never derived from the predicate. When BOTH an
    increase and a decrease token appear the direction is ambiguous -> '' (keep
    separate / fail-closed at the merge key).
    """
    if not text:
        return ""
    up = bool(_DIRECTION_INCREASE_RE.search(text))
    down = bool(_DIRECTION_DECREASE_RE.search(text))
    if up and not down:
        return "increase"
    if down and not up:
        return "decrease"
    return ""


# Population / cohort: "in patients with X" / "in adults with X" / "among ...".
# The terminating lookahead stops the cohort phrase at a clause boundary or the
# onset of an outcome verb. Verb stems (achiev/reduc/...) intentionally carry NO
# trailing \b so they match the inflected forms ("achieved", "reduced").
_POPULATION_RE = re.compile(
    r"\b(?:in|among)\s+"
    r"(?P<pop>(?:patients?|adults?|children|subjects?|participants?|women|men|"
    r"individuals?|people)\b[a-z0-9\-\s]{0,50}?)"
    r"(?=[,.;:)\]]|\s+(?:achiev|reduc|experienc|demonstrat|report|produc|"
    r"had\b|who\s+receiv|with\s+a\b)|$)",
    re.IGNORECASE,
)


def _extract_population(text: str) -> str:
    """The 'in/among patients with X' cohort phrase, or '' if none."""
    if not text:
        return ""
    m = _POPULATION_RE.search(text)
    if not m:
        return ""
    return re.sub(r"\s+", " ", m.group("pop").strip()).lower()


def _find_value_in_context(
    text: str, predicate: str,
) -> Optional[tuple[float, str, str, int]]:
    """Find a numeric value that sits INSIDE a value-phrase context.

    Returns (value, unit, matched_context, anchor_position_in_text) or None.

    The algorithm:
      1. Find all percentage matches.
      2. For each, check a ±40-char window for:
         (a) A value-phrase verb  AND
         (b) NOT a reject pattern (placebo, threshold, trial acronym, duration)
      3. Return the first match that satisfies both.

    R-5 Fix B: also returns the anchor position so the caller can
    attribute subject (drug name) to the drug NEAREST the value,
    not the first drug appearing in the full quote.
    """
    if not text:
        return None

    # Predicate-specific unit handling
    if "hba1c" in predicate or "a1c" in predicate:
        for m in _HBA1C_RE.finditer(text):
            window = text[max(0, m.start() - 40): min(len(text), m.end() + 40)]
            if _is_reject_context(window, m.start() - max(0, m.start() - 40)):
                continue
            if not _VALUE_PHRASE_VERBS.search(window):
                continue
            try:
                return (
                    float(m.group("value")), "percentage_points",
                    window, m.start(),
                )
            except ValueError:
                continue
        return None

    for m in _PCT_RE.finditer(text):
        start_win = max(0, m.start() - 40)
        end_win = min(len(text), m.end() + 40)
        window = text[start_win:end_win]
        # Reject if window is a comparator/threshold/acronym/duration
        if _is_reject_context(window, m.start() - start_win):
            continue
        if not _VALUE_PHRASE_VERBS.search(window):
            continue
        try:
            return (float(m.group("value")), "%", window, m.start())
        except ValueError:
            continue
    return None


def _is_reject_context(window: str, num_pos_in_window: int) -> bool:
    """Return True if the number at `num_pos_in_window` is in a reject context.

    We check the immediate left/right 30 chars around the number only —
    this prevents a distant "placebo" elsewhere in the window from
    wrongly rejecting a treatment-arm claim.
    """
    near_start = max(0, num_pos_in_window - 30)
    near_end = min(len(window), num_pos_in_window + 30)
    near = window[near_start:near_end]
    if _PLACEBO_CONTEXT_RE.search(near):
        return True
    if _ACHIEVEMENT_THRESHOLD_RE.search(near):
        return True
    if _TRIAL_ACRONYM_NUM_RE.search(near):
        return True
    # Duration reject: only if the number itself is inside a week/month/year span
    m = _DURATION_NUM_RE.search(near)
    if m and m.start() <= num_pos_in_window - near_start <= m.end():
        return True
    # B13: confidence-interval LEVEL reject — only if the number under
    # measurement IS the confidence level directly before a CI cue (e.g. the
    # "95%" in "(95% CI 2-9)"). Anchored on the number's own position so a real
    # point estimate elsewhere in the window (the "8%" in "8% (95% CI 5-12)") is
    # not rejected.
    num_local = num_pos_in_window - near_start
    for ci in _CONFIDENCE_INTERVAL_LEVEL_RE.finditer(near):
        if ci.start() <= num_local <= ci.start() + 2:
            return True
    return False


def _extract_numeric_value(text: str, predicate: str) -> Optional[tuple[float, str]]:
    """Back-compat: returns (value, unit) without the context.

    The new pipeline uses _find_value_in_context() directly to also
    capture the endpoint phrase; this shim keeps older call-sites
    working during the Fix-1 rollout.
    """
    if not text:
        return None
    result = _find_value_in_context(text, predicate)
    if result:
        v, u, _ctx, _pos = result
        return (v, u)

    # Fallback: if no value-phrase match, fall back to the previous
    # loose extraction — but ONLY for the predicate-specific regex,
    # not the generic "any percentage in the quote" fallback which
    # was the source of Fix-1 false positives.
    if "hba1c" in predicate or "a1c" in predicate:
        m = _HBA1C_RE.search(text)
        if m:
            try:
                return float(m.group("value")), "percentage_points"
            except ValueError:
                return None
    if "duration" in predicate:
        m = _DURATION_RE.search(text)
        if m:
            try:
                return float(m.group("value")), m.group("unit").lower()
            except ValueError:
                return None
    return None


def extract_numeric_claims(
    evidence: list[dict[str, Any]],
    domain: str | None = None,
) -> list[ExtractedNumericClaim]:
    """Extract structured numeric claims from evidence rows.

    Each evidence dict should have 'evidence_id', 'direct_quote' (or
    'statement'), 'source_url', 'tier'. Missing fields are handled.

    BUG-M-202 fix (deep-dive R7): `domain` parameter routes to a
    broader predicate set for non-clinical queries. Default None
    preserves the union-fallback (original behavior).

    B9 domain-generalization: for a NON-clinical run (deterministic
    `is_clinical_domain` over `domain` + the evidence text) the clinical
    predicate union + `_DRUG_NAME_RE` subject extract NOTHING, so this
    historically returned zero claims and every non-clinical numeric became a
    singleton. We now route non-clinical corpora to the DOMAIN-AGNOSTIC
    extractor (generic metric cue + generic subject + value + unit), which
    yields a real claim-key so corroborating sources can consolidate. The
    CLINICAL path (is_clinical True — `domain="clinical"`, or a blank domain
    over a clinically-signalled corpus) is byte-identical to before.
    """
    from src.polaris_graph.domain.domain_signal import is_clinical_domain
    if not is_clinical_domain(domain, evidence):
        return _extract_numeric_claims_generic(evidence)
    claims: list[ExtractedNumericClaim] = []
    for ev in evidence:
        quote = ev.get("direct_quote") or ev.get("statement") or ""
        if not quote:
            continue
        predicate = _normalize_predicate(quote, domain=domain)
        if not predicate:
            continue

        # Fix-1 uses _find_value_in_context which returns the matched
        # window so we can store the endpoint phrase.
        in_context = _find_value_in_context(quote, predicate)
        if in_context is None:
            continue
        value, unit, ctx_window, anchor_pos = in_context

        # R-5 Fix B: subject must be the drug NEAREST the numeric value,
        # not the first drug in the quote. Cross-drug comparison quotes
        # like "Zepbound 25.5% compared to CagriSema 23%" were mis-
        # attributing to the first drug mentioned earlier in the full
        # direct_quote (often the paragraph's primary topic, e.g.
        # retatrutide). _subject_near_position searches ±150 chars
        # around the value's position and picks the closest drug match.
        subject = _subject_near_position(quote, anchor_pos, fallback="unknown")

        dose = _extract_dose(ctx_window) or _extract_dose(quote)
        # arm classification: if the value sits in a placebo context
        # it wouldn't have passed _find_value_in_context, but we also
        # tag "comparator_adjacent" when the ctx includes "vs placebo"
        # farther out (this is additional info for display, not a filter).
        # OFF byte-identity (Codex Slice-B P1): a no-cue arm stays the LEGACY
        # "treatment" string, NOT None — the OFF-path cluster key
        # (_normalized_key_numeric, claim_graph.py:241) and contradictions.json
        # asdict both read this field, so emitting None would drift OFF cluster
        # ids + bytes. Flag-ON consolidation is still fail-closed: a defaulted
        # "treatment" arm is treated as UNKNOWN by claim_graph._unknown_arm and
        # forces a singleton; only the positively-extracted "comparator_adjacent"
        # cue anchors a merge (design §4.3 — the arm lesson holds without None).
        if _detect_placebo_arm(ctx_window):
            arm = "comparator_adjacent"
        else:
            arm = "treatment"
        endpoint_phrase = _extract_endpoint_phrase(ctx_window) or _extract_endpoint_phrase(quote)

        # Wave-3 positive-known discriminators (I-arch-002 [2]). Each reads the
        # evidence text ONLY (ctx first, then full quote) and yields '' when no
        # positive token is present. Dormant until build_merge_key reads them.
        dose_frequency = _extract_dose_frequency(ctx_window) or _extract_dose_frequency(quote)
        comparator = _extract_comparator(ctx_window) or _extract_comparator(quote)
        route_formulation = _extract_route_formulation(ctx_window) or _extract_route_formulation(quote)
        effect_measure = _extract_effect_measure(ctx_window) or _extract_effect_measure(quote)
        direction = _extract_direction(ctx_window) or _extract_direction(quote)
        population = _extract_population(ctx_window) or _extract_population(quote)

        claims.append(ExtractedNumericClaim(
            evidence_id=str(ev.get("evidence_id", "")),
            subject=subject,
            predicate=predicate,
            value=value,
            unit=unit,
            context_snippet=ctx_window[:200],
            source_url=ev.get("source_url", ""),
            source_tier=ev.get("tier", ""),
            dose=dose,
            arm=arm,
            endpoint_phrase=endpoint_phrase,
            dose_frequency=dose_frequency,
            comparator=comparator,
            route_formulation=route_formulation,
            effect_measure=effect_measure,
            direction=direction,
            population=population,
        ))
    return claims


# ─────────────────────────────────────────────────────────────────────────────
# Contradiction detection
# ─────────────────────────────────────────────────────────────────────────────

# Relative-difference threshold (|a-b|/min(|a|,|b|)) above which we
# flag a contradiction. Default 0.10 = 10%.
PG_CONTRADICTION_REL_THRESHOLD = float(
    os.getenv("PG_CONTRADICTION_REL_THRESHOLD", "0.10")
)

# Absolute-difference threshold (in the claim's native unit). If the
# relative threshold is tripped, absolute threshold is an AND filter —
# both must exceed to flag (avoids flagging 0.01 vs 0.03 rel=66%).
PG_CONTRADICTION_ABS_THRESHOLD = float(
    os.getenv("PG_CONTRADICTION_ABS_THRESHOLD", "1.0")
)


def _severity(rel: float, abs_: float) -> str:
    if rel >= 0.25 or abs_ >= 5.0:
        return "high"
    if rel >= 0.15 or abs_ >= 2.5:
        return "medium"
    return "low"


def _shared_metric_axes(group: list["ExtractedNumericClaim"]) -> bool:
    """B9 (Codex P1.3): return True only when the group's scope is POSITIVELY
    confirmed shared — a TRUE non-clinical contradiction. The plan requires a
    generic numeric contradiction to share endpoint + unit + population +
    comparator + time-window; otherwise it is a `possible_metric_mismatch`.

    Rule:
      * If ANY scope axis (comparator / population / endpoint_phrase) carries
        more than one distinct non-empty value -> the claims measure different
        things -> NOT shared (mismatch).
      * If NO scope axis is positively confirmed (every axis uniformly empty /
        UNKNOWN) -> we CANNOT confirm a shared metric -> NOT shared (mismatch).
        This is the conservative non-clinical default: unconfirmed scope is a
        possible_metric_mismatch, never a hard contradiction.
      * Otherwise (no conflicting axis AND at least one axis positively
        confirmed shared) -> shared metric -> a true contradiction.
    Pure helper."""
    def _axis(field_name: str) -> set[str]:
        return {(getattr(c, field_name, "") or "").strip().lower() for c in group}
    confirmed_shared = False
    for axis in ("comparator", "population", "endpoint_phrase"):
        vals = _axis(axis)
        non_empty = {v for v in vals if v}
        if len(non_empty) > 1:
            return False  # conflicting scope -> different metrics
        if len(non_empty) == 1 and "" not in vals:
            # every claim positively carries the SAME value on this axis
            confirmed_shared = True
    return confirmed_shared


def _is_unknown_subject(subject: str) -> bool:
    """True when a group's subject is the UNKNOWN sentinel (``"unknown"`` / blank).

    BUG-17 (#1262): ``_subject_near_position`` / ``_subject_generic`` resolve to
    ``"unknown"`` when entity extraction fails. An unknown subject is NOT a real
    entity — so two numbers grouped under it (PCA variance vs CRC prevalence vs
    mouse weight) measure DIFFERENT things and must not be asserted as a hard
    contradiction. Handled downstream as a DISCLOSURE (possible mismatch), never
    a blanket pairing AND never a blanket skip (a blanket skip could DROP a real
    contradiction whose entity extraction merely failed — a faithfulness loss).
    """
    return (subject or "").strip().lower() in ("", "unknown")


def _group_has_real_drug_subject(group: list["ExtractedNumericClaim"]) -> bool:
    """True iff the group is keyed on a REAL drug/intervention subject — the
    positive signal that licenses the clinical drug-trial contradiction schema.

    BUG-17 (#1262) part 1: ``is_clinical`` is a ROUTING string (``domain ==
    "clinical"`` makes ``is_clinical_domain`` return True unconditionally), NOT a
    guarantee the claim is about a drug/intervention. A clinical-ROUTED but
    NON-drug question (an ADAS yaw-angle ``accuracy`` number that happened to be
    routed clinical) must NOT inherit the drug-trial grouping schema. We
    therefore SEPARATE the routing string from a TRUE drug subject: the clinical
    no-guard path fires only when the group's shared subject is a recognised
    drug/intervention name (``_DRUG_NAME_RE``). Otherwise the group falls through
    to the same-metric-axes guard (possible_metric_mismatch), regardless of the
    routing flag.

    Deterministic, no LLM, never raises (recogniser/config errors are swallowed
    fail-soft — never drug-by-error). Faithfulness is unchanged: a genuine
    clinical drug contradiction (subject is e.g. ``"semaglutide"``) still has a
    real drug subject -> keeps the full clinical schema byte-for-byte.
    """
    subj = (group[0].subject or "").strip().lower() if group else ""
    if not subj or _is_unknown_subject(subj):
        return False
    try:
        from src.polaris_graph.nodes.scope_gate import _DRUG_NAME_RE
        return bool(_DRUG_NAME_RE.search(subj))
    except Exception:
        return False


# ─────────────────────────────────────────────────────────────────────────────
# A17 commensurability guard (I-arch-006 #1262)
#
# The grouping key is (subject, predicate, unit, dose). When unit is "" (the
# extractor could not attach a unit token), ALL unit-less numbers in a
# subject/predicate bucket collapse together — so a 0.5-DEGREE yaw angle gets
# bucketed with a 100-METRE radar distance under subject="lane" / predicate=
# "change" / unit="". The detector then computes a meaningless cross-quantity
# magnitude (the run surfaced absolute_difference 99.5 / relative 199% across
# degrees-vs-meters), a category error that is user-visible junk.
#
# This guard reads each claim's own context text for a POSITIVELY-KNOWN physical
# quantity kind (angle / length / speed / time / mass / temperature / data-size /
# frequency / currency / count-people). A group whose claims carry MORE THAN ONE
# distinct known quantity kind is INCOMMENSURABLE: its numbers are not comparable,
# so the surfaced rel/abs diff is nulled and the record is kept out of the headline
# count — but every claim/source stays DISCLOSED (never dropped). Unknown kinds
# never force incommensurability (conservative: only POSITIVE divergence triggers,
# so a genuine same-quantity contradiction is never mis-flagged). NO faithfulness
# threshold is touched. Deterministic, no LLM, never raises.
# ─────────────────────────────────────────────────────────────────────────────

_A17_GUARD_FLAG = "PG_CONTRADICTION_COMMENSURABILITY_GUARD"
_A17_GUARD_OFF_VALUES = frozenset({"0", "false", "off", "no"})


def _a17_guard_enabled() -> bool:
    """True (default) unless PG_CONTRADICTION_COMMENSURABILITY_GUARD is set off.

    Read at CALL time so tests can monkeypatch os.environ. Defaults ON because
    surfacing a degrees-vs-meters magnitude is §-1.3-incorrect validity junk; the
    flag exists only as a LAW-VI escape hatch / byte-identity audit lever.
    """
    return (
        os.environ.get(_A17_GUARD_FLAG, "").strip().lower()
        not in _A17_GUARD_OFF_VALUES
    )


# Positively-known physical quantity kinds, keyed by a context-text cue. The cues
# are deterministic word-boundary patterns (no clinical literal). Order is
# irrelevant — a claim's kind is the SET of all cues that fire; a group is
# incommensurable iff the UNION of single-kind claims spans >1 distinct kind.
_QUANTITY_KIND_CUES: tuple[tuple[str, "re.Pattern[str]"], ...] = (
    ("angle", re.compile(r"\b(?:degrees?|deg|°|radians?|yaw|pitch|roll|angular)\b", re.IGNORECASE)),
    ("length", re.compile(r"\b(?:metres?|meters?|kilometres?|kilometers?|km|cm|mm|"
                          r"miles?|feet|foot|inch(?:es)?|nanometres?|nanometers?|nm|µm|micrometres?|"
                          r"distances?|radius|radii|diameter|wavelengths?)\b"
                          r"|\d\s*m\b", re.IGNORECASE)),
    ("speed", re.compile(r"\b(?:km/?h|kph|mph|m/?s|knots?|velocity|speed)\b", re.IGNORECASE)),
    ("time_duration", re.compile(r"\b(?:seconds?|secs?|milliseconds?|ms|minutes?|mins?|"
                                 r"hours?|hrs?|microseconds?|µs|nanoseconds?|ns|latency)\b", re.IGNORECASE)),
    ("mass", re.compile(r"\b(?:kilograms?|kg|grams?|milligrams?|mg|µg|micrograms?|"
                        r"tonnes?|tons?|pounds?|lbs?|ounces?|oz)\b", re.IGNORECASE)),
    ("temperature", re.compile(r"\b(?:°c|°f|celsius|fahrenheit|kelvin)\b|\bdegrees?\s+(?:c|f|celsius|fahrenheit)\b", re.IGNORECASE)),
    ("data_size", re.compile(r"\b(?:bytes?|kilobytes?|kb|megabytes?|mb|gigabytes?|gb|terabytes?|tb|bits?|fps|frames?\s+per\s+second)\b", re.IGNORECASE)),
    ("frequency_hz", re.compile(r"\b(?:hertz|hz|khz|mhz|ghz)\b", re.IGNORECASE)),
    ("currency", re.compile(r"[$€£¥]|\b(?:usd|eur|gbp|cad|jpy|dollars?|euros?|pounds?\s+sterling)\b", re.IGNORECASE)),
    ("power_energy", re.compile(r"\b(?:watts?|kw|mw|gw|kwh|mwh|twh|joules?|kj|mj|volts?|amps?|amperes?)\b", re.IGNORECASE)),
)


def _value_anchor_pos(text: str, value: float) -> Optional[int]:
    """Best char position of the claim's numeric VALUE inside its context text.

    Tries the int form ('100'), the trimmed-float form ('0.5'), then the raw
    repr. Returns None when the value cannot be located (caller then falls back
    to whole-text scan). Pure."""
    if not text:
        return None
    forms: list[str] = []
    if value == int(value):
        forms.append(str(int(value)))
    forms.append(("%g" % value))
    forms.append(str(value))
    for form in forms:
        idx = text.find(form)
        if idx != -1:
            return idx
    return None


def _quantity_kinds_for_claim(claim: "ExtractedNumericClaim") -> frozenset[str]:
    """Positively-known physical quantity kind(s) for a claim, ANCHORED on the
    number nearest the claim's own value.

    The context_snippet can mention several quantities (a yaw snippet says
    '0.5 degrees can cause a lateral error of almost one meter' — angle AND
    length). A whole-text scan would mark such a claim ambiguous (multi-kind) and
    the conservative single-kind rule would then SKIP it, missing the very case
    A17 targets. So we anchor: the unit token is authoritative when present;
    otherwise the kind is the one whose cue fires CLOSEST to the value's position
    in the snippet (degrees is adjacent to 0.5 -> angle; m/distances is adjacent
    to 100 -> length). Returns frozenset() when no cue fires (UNKNOWN — never
    forces incommensurability). Pure, never raises."""
    unit = str(getattr(claim, "unit", "") or "")
    snippet = str(getattr(claim, "context_snippet", "") or "")
    # 1. Authoritative unit token (when the extractor attached one).
    for kind, pat in _QUANTITY_KIND_CUES:
        try:
            if unit and pat.search(unit):
                return frozenset({kind})
        except Exception:
            continue
    if not snippet.strip():
        return frozenset()
    anchor = _value_anchor_pos(snippet, getattr(claim, "value", 0.0))
    # 2. Value-anchored: pick the kind whose nearest cue match is closest to the
    #    value. Falls back to whole-text presence when the value can't be located.
    best_kind: Optional[str] = None
    best_dist = 10 ** 9
    for kind, pat in _QUANTITY_KIND_CUES:
        try:
            matches = list(pat.finditer(snippet))
        except Exception:
            continue
        if not matches:
            continue
        if anchor is None:
            # No anchor: degrade to first-found wins (deterministic by cue order).
            if best_kind is None:
                best_kind = kind
            continue
        for m in matches:
            center = (m.start() + m.end()) // 2
            dist = abs(center - anchor)
            if dist < best_dist:
                best_dist = dist
                best_kind = kind
    if best_kind is not None:
        return frozenset({best_kind})
    return frozenset()


def _group_incommensurable_reason(group: list["ExtractedNumericClaim"]) -> str:
    """Return a short reason string iff the group mixes POSITIVELY-DIVERGENT
    quantity kinds (incommensurable), else "".

    A claim contributes its kind ONLY when it resolves to EXACTLY ONE known kind
    (an ambiguous multi-kind claim, e.g. text mentioning both "metres" and
    "seconds", is not a reliable single-axis signal and is skipped — conservative).
    The group is incommensurable iff the union of those single-kind claims spans
    more than one distinct kind. Unknown / ambiguous claims never trigger it, so a
    genuine same-quantity numeric contradiction is NEVER mis-flagged. Pure."""
    seen: set[str] = set()
    for c in group:
        kinds = _quantity_kinds_for_claim(c)
        if len(kinds) == 1:
            seen.add(next(iter(kinds)))
    if len(seen) > 1:
        ordered = sorted(seen)
        return (
            "incommensurable quantity kinds in one bucket: "
            + " vs ".join(ordered)
            + " — numbers measure different physical quantities (unit token was "
            "missing, so they collapsed under the same surface key); the numeric "
            "gap is not a real disagreement"
        )
    return ""


def detect_contradictions(
    claims: list[ExtractedNumericClaim],
    *,
    rel_threshold: Optional[float] = None,
    abs_threshold: Optional[float] = None,
    is_clinical: bool = True,
) -> list[ContradictionRecord]:
    """Group claims by (subject, predicate, unit, dose) and flag discrepancies.

    Fix-1: grouping key now includes DOSE. A 2.4 mg weight-loss result
    and a 7.2 mg weight-loss result are NOT a contradiction — they're
    expected dose-response differences. They will only be grouped
    together if both happen to have no dose tag (e.g., a narrative
    review that doesn't specify dose).

    B9 domain-generalization (`is_clinical`, default True = byte-identical):
    on a NON-clinical run a generic numeric discrepancy is only a TRUE
    contradiction when the two numbers measure the SAME thing — same
    comparator, population, and endpoint/time-window. When those discriminators
    differ (or cannot be confirmed shared), the pair is labeled
    `possible_metric_mismatch` (severity downgraded, never silently dropped)
    rather than asserted as a hard contradiction. Clinical runs keep the full
    clinical contradiction rule unchanged (this branch never fires on them).
    """
    if rel_threshold is None:
        rel_threshold = PG_CONTRADICTION_REL_THRESHOLD
    if abs_threshold is None:
        abs_threshold = PG_CONTRADICTION_ABS_THRESHOLD

    grouped: dict[tuple[str, str, str, str], list[ExtractedNumericClaim]] = {}
    for c in claims:
        key = (c.subject, c.predicate, c.unit, c.dose or "")
        grouped.setdefault(key, []).append(c)

    records: list[ContradictionRecord] = []
    for (subject, predicate, unit, dose), group in grouped.items():
        if len(group) < 2:
            continue
        values = [c.value for c in group]
        vmin, vmax = min(values), max(values)
        denom = max(abs(vmin), 1e-9)
        rel = abs(vmax - vmin) / denom
        abs_diff = abs(vmax - vmin)
        if rel >= rel_threshold and abs_diff >= abs_threshold:
            predicate_display = predicate
            if dose:
                predicate_display = f"{predicate} ({dose})"
            # A17 (I-arch-006 #1262): commensurability guard runs FIRST, on EVERY
            # path (incl. the clinical real-drug path), because mixing divergent
            # PHYSICAL quantity kinds in one bucket is a stronger validity failure
            # than a scope mismatch — a unit-less collapse can bucket a 0.5-degree
            # yaw angle with a 100-metre radar distance even under a real subject.
            # When the group's claims carry positively-divergent quantity kinds the
            # numeric gap is a category error, so we NULL the surfaced rel/abs diff
            # (no misleading magnitude), label the record not_comparable, and keep
            # it OUT of the headline count — but DISCLOSE every claim/source (never
            # drop). This is a VALIDITY/WEIGHT check; no faithfulness threshold is
            # touched and only POSITIVE divergence triggers it (a genuine same-
            # quantity contradiction, e.g. two "%" claims, is never mis-flagged).
            # A17 scan ONLY a unit-LESS group (unit == ""). Physical units
            # (degrees / metres) are never in the extractor's unit alternation so
            # they ALWAYS collapse to unit="" — exactly the bucket A17 targets. A
            # group with ANY non-empty shared unit (%, currency, magnitude) is
            # commensurable BY CONSTRUCTION (the grouping key forces the same unit),
            # so scanning its prose for incidental physical-quantity nouns ("30 fps"
            # near one claim, "5 ms latency" near another) could only INVENT a false
            # divergence and SUPPRESS a genuine same-unit contradiction — the
            # cardinal faithfulness sin. The gate makes A17 fire on the real collapse
            # and never on a real shared-unit disagreement.
            incommensurable_reason = ""
            if _a17_guard_enabled() and unit == "":
                incommensurable_reason = _group_incommensurable_reason(group)
            if incommensurable_reason:
                # De-numbered, not None: the surfaced magnitude is set to 0.0 so a
                # downstream consumer reads "no asserted disagreement" (0%) instead
                # of the junk cross-quantity 199%/545%. 0.0 is None-safe at every
                # in-memory + JSON consumer (honest_pipeline `*100`, audit_ir
                # `float(...)`, generator `or 0`); None would crash them. The real
                # signal lives in not_comparable / incommensurable_reason / the
                # [not_comparable] tag + headline-count exclusion.
                records.append(ContradictionRecord(
                    subject=subject,
                    predicate=f"{predicate_display} [not_comparable]",
                    claims=sorted(group, key=lambda c: c.value),
                    relative_difference=0.0,
                    absolute_difference=0.0,
                    severity="low",
                    recommended_action=(
                        "Not comparable (A17): the numbers in this bucket measure "
                        "different physical quantities and collapsed under one "
                        "surface key only because a unit token was missing. Disclose "
                        "each value with its own context; do NOT assert a numeric "
                        "contradiction across them."
                    ),
                    not_comparable=True,
                    incommensurable_reason=incommensurable_reason,
                ))
                continue
            # A17 SAME-SOURCE guard (iarch007 FETCH-P0): a CROSS-source contradiction requires the
            # disagreeing numbers to come from DIFFERENT sources. When every claim in this group
            # shares ONE source (same source_url, or same evidence_id when a URL is absent — and the
            # cannot-attribute blank case), the spread is a WITHIN-source numeric span (a range, two
            # figures in one document, or an extraction artifact), NOT a cross-source contradiction.
            # Label it not_comparable, keep it OUT of the headline contradiction count, and DISCLOSE
            # every claim (never drop — §-1.3). This is a cross-source VALIDITY/WEIGHT check: no
            # faithfulness threshold is touched, and a genuine 2+-source disagreement is never
            # suppressed (the guard fires ONLY when fewer than two distinct sources are present).
            distinct_sources = {(c.source_url or c.evidence_id or "") for c in group}
            distinct_sources.discard("")
            if len(distinct_sources) < 2:
                only_src = next(iter(distinct_sources), "unknown")
                records.append(ContradictionRecord(
                    subject=subject,
                    predicate=f"{predicate_display} [not_comparable]",
                    claims=sorted(group, key=lambda c: c.value),
                    relative_difference=0.0,
                    absolute_difference=0.0,
                    severity="low",
                    recommended_action=(
                        "Not comparable (same-source A17): every value in this bucket comes from a "
                        "single source (or no source could be attributed), so this is a within-source "
                        "numeric span, not a cross-source contradiction. Disclose each value with its "
                        "own context; do NOT assert a cross-source numeric contradiction from one "
                        "source."
                    ),
                    not_comparable=True,
                    incommensurable_reason=(
                        f"same_source: the {len(group)} claims resolve to {len(distinct_sources)} "
                        f"distinct source(s) ({only_src!r}) — a within-source numeric span, not a "
                        "cross-source contradiction"
                    ),
                ))
                continue
            # B9: on a non-clinical run, a numeric gap is a TRUE contradiction
            # only when the claims share comparator/population/time-window. If
            # those discriminators differ or cannot be confirmed, label it a
            # `possible_metric_mismatch` (downgraded, surfaced, never dropped).
            #
            # BUG-17 (#1262): the same-metric-axes guard must ALSO apply on the
            # CLINICAL-ROUTED path whenever the group is NOT keyed on a real
            # drug/intervention subject. Two failure modes the old
            # `not is_clinical` gate let through:
            #   (1) clinical ROUTING string != TRUE drug subject — a clinical-
            #       routed but non-drug question (ADAS yaw-angle `accuracy`)
            #       inherited the drug-trial no-guard schema and asserted a hard
            #       contradiction with no shared-metric check.
            #   (2) unknown/blank subject — UNRELATED numbers (PCA variance vs CRC
            #       prevalence vs mouse weight) collapsed under subject="unknown"
            #       and were flagged as one hard contradiction.
            # Fix: the no-guard clinical schema fires ONLY for a group with a real
            # drug subject; an unknown-subject group OR a clinical-routed non-drug
            # group falls through to the shared-metric-axes guard, which DISCLOSES
            # the pair as a possible_metric_mismatch (never drops it — a genuinely
            # conflicting unknown-subject pair whose axes ARE confirmed-shared still
            # surfaces as a real contradiction). Faithfulness is NEVER relaxed: a
            # genuine same-DRUG numeric contradiction keeps the full clinical
            # schema, and no verified claim is dropped — we only stop FABRICATING
            # contradictions between numbers that do not measure the same thing.
            apply_metric_guard = not is_clinical or not _group_has_real_drug_subject(group)
            metric_mismatch = (
                apply_metric_guard and not _shared_metric_axes(group)
            )
            if metric_mismatch:
                predicate_display = f"{predicate_display} [possible_metric_mismatch]"
                severity = "low"
                action = (
                    "Possible metric mismatch (B9): these numbers may not measure "
                    "the same quantity — comparator, population, or time-window "
                    "could differ. Disclose both with their scope; do NOT assert a "
                    "contradiction without a confirmed shared metric."
                )
                records.append(ContradictionRecord(
                    subject=subject,
                    predicate=predicate_display,
                    claims=sorted(group, key=lambda c: c.value),
                    relative_difference=round(rel, 4),
                    absolute_difference=round(abs_diff, 4),
                    severity=severity,
                    recommended_action=action,
                ))
            else:
                records.append(ContradictionRecord(
                    subject=subject,
                    predicate=predicate_display,
                    claims=sorted(group, key=lambda c: c.value),
                    relative_difference=round(rel, 4),
                    absolute_difference=round(abs_diff, 4),
                    severity=_severity(rel, abs_diff),
                ))

    # Sort by severity (high first), then predicate
    severity_rank = {"high": 0, "medium": 1, "low": 2}
    records.sort(key=lambda r: (severity_rank.get(r.severity, 3), r.predicate))
    return records


def format_contradictions_for_user(
    records: list[ContradictionRecord],
) -> str:
    """Human-readable plain-text summary.

    A17 (I-arch-006 #1262): an incommensurable / `not_comparable` record (a bucket
    that mixed divergent physical quantity kinds) is EXCLUDED from the headline
    contradiction count and rendered as "not comparable" instead of a misleading
    rel/abs magnitude. Its claims are still listed (disclosed, never dropped) under
    a separate notice so the reader sees why the numbers are not a real
    disagreement.
    """
    if not records:
        return "No contradictions detected in the evidence corpus."
    comparable = [r for r in records if not getattr(r, "not_comparable", False)]
    not_comparable = [r for r in records if getattr(r, "not_comparable", False)]
    lines = [
        f"Detected {len(comparable)} contradiction(s) in the evidence corpus.",
        "",
    ]
    for i, r in enumerate(comparable, 1):
        lines.append(
            f"[{i}] {r.subject} / {r.predicate} — "
            f"severity={r.severity}, rel_diff={r.relative_difference*100:.1f}%, "
            f"abs_diff={r.absolute_difference:.2f} {r.claims[0].unit}"
        )
        for c in r.claims:
            lines.append(
                f"    - {c.value} {c.unit}   "
                f"[ev={c.evidence_id}, tier={c.source_tier}]   "
                f"{c.context_snippet[:120]}"
            )
        lines.append(f"    Action: {r.recommended_action}")
        lines.append("")
    if not_comparable:
        lines.append(
            f"Also surfaced {len(not_comparable)} not-comparable bucket(s) "
            "(numbers measure different quantities — NOT a contradiction):"
        )
        lines.append("")
        for j, r in enumerate(not_comparable, 1):
            lines.append(
                f"[NC{j}] {r.subject} / {r.predicate} — not comparable: "
                f"{r.incommensurable_reason}"
            )
            for c in r.claims:
                lines.append(
                    f"    - {c.value} {c.unit}   "
                    f"[ev={c.evidence_id}, tier={c.source_tier}]   "
                    f"{c.context_snippet[:120]}"
                )
            lines.append(f"    Action: {r.recommended_action}")
            lines.append("")
    return "\n".join(lines)
