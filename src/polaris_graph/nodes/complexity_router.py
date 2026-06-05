"""I-ready-006 (#1082): deterministic query-complexity router (no model, offline, §8.4-safe).

Classifies a research question as ``simple`` (a right-sizeable factual lookup), ``complex`` (the full
heavyweight deep-research path), or ``moderate``. Pure stdlib + ``re`` — no LLM call (burning an LLM
call just to decide a query is simple would defeat the cost-saving point) and no model load.

FAIL-OPEN by design (clinical-safety): anything NOT confidently ``simple`` is classified ``complex``,
so a hard clinical / policy / comparison / mechanism question is NEVER under-served. The caller wires
this behind ``PG_COMPLEXITY_ROUTING`` (default OFF) and only right-sizes when
``complexity == "simple"`` AND ``confidence >= PG_COMPLEXITY_MIN_CONFIDENCE``.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class ComplexityDecision:
    """The routing decision. ``reasons`` is auditable telemetry for the manifest."""

    complexity: str                       # "simple" | "moderate" | "complex"
    confidence: float                     # 0.0 - 1.0
    reasons: list[str] = field(default_factory=list)


# Intent markers that force the FULL heavyweight path — comparison / causal / mechanism / synthesis /
# clinical-evaluative. Presence of ANY ⇒ NOT simple (fail-open to complex). A clinical dosing / safety
# / efficacy / mechanism question is deliberately routed complex: better to OVER-serve it than under-
# serve it. NOTE: a bare conjunction ("Telus AND Bell ...") is a parallel FACTUAL lookup, not a
# comparison — only explicit compare/versus/difference verbs count here.
_COMPLEX_INTENT = re.compile(
    r"\b(compare|comparison|versus|vs\.?|difference between|trade[- ]?off|"
    r"why|how does|how do|mechanism|pathophysiolog|causal|cause[sd]?|effect of|impact of|"
    r"efficacy|safety|adverse|contraindicat|dose|dosing|titrat|regimen|"
    r"meta[- ]?analysis|systematic review|guideline|recommend|"
    r"relationship between|associat|correlat|predict|forecast|project|"
    r"should|optimal|best (?:approach|strategy|treatment|option)|evaluate|assess(?:ment)?|"
    r"pros and cons|advantages|risk[- ]?benefit|"
    # I-ready-006 (#1082) Codex diff-gate iter-3 P1-2: analytical / due-diligence intent — these are
    # NOT one-line factual lookups (e.g. "Apple revenue drivers and competitive risks", "Microsoft
    # revenue exposure to OpenAI", "Apple profit risk from China tariffs"). Any of these ⇒ full path.
    r"driver|risk|exposure|competiti|outlook|threat|headwind|tailwind|moat|"
    r"opportunit|strateg|tariff|sanction|next \d+ years|over the next|going forward|"
    r"implication|scenario|sensitivity|downside|upside|catalyst|"
    # iter-4 P1-2: investment-JUDGMENT markers — "Is Tesla stock overvalued/a buy?" is an analysis,
    # not a factual lookup. Structural (no ticker enumeration).
    r"overvalued|undervalued|fair[- ]?value|fairly valued|\bbuy\b|\bsell\b|\bhold\b|"
    r"worth buying|good investment|invest in|bullish|bearish|price target|"
    r"should i (?:buy|sell|invest)|is it a (?:buy|sell))\b",
    re.IGNORECASE,
)

# I-ready-006 (#1082) Codex diff-gate iter-4 P1-1: COHORT-PREVALENCE / drug-utilization pattern —
# "population/number/prevalence/proportion of <cohort> WITH/TAKING/USING/ON/DIAGNOSED <X>" is an
# epidemiology query, NOT a civic "population of <place>" fact. STRUCTURAL (catches the whole class
# without enumerating disease names, per Codex's blocker). Any hit ⇒ full path.
_COHORT_PREVALENCE = re.compile(
    r"\b(?:population|number|prevalence|proportion|percentage|share|count|fraction)\s+of\b"
    r".{0,60}?\b(?:with|who\s+(?:have|has|are|use|take)|taking|using|on\s+|diagnosed|"
    r"suffering|affected|living with|prescribed|treated)\b",
    re.IGNORECASE,
)

# Clinical / medical / health / epidemiology content. ANY hit ⇒ NOT simple (fail-open to complex),
# regardless of a factual cue — a clinical safety/outcome question ("mortality rate of Semaglutide",
# "incidence of Guillain-Barré after Shingrix") must NEVER be right-sized to a 1-source answer (Codex
# diff-gate iter-1 P1-1; lethal-class under-serving per CLAUDE.md §-1.1). Erring toward complex here
# is the SAFE direction (over-serving a stock query that trips a drug-suffix is harmless; under-
# serving a clinical query is not).
# Word/STEM group — matched as PREFIXES via the trailing \w* (Codex diff-gate iter-3 P1-1: the prior
# \b-bounded stems did NOT match "obesity"/"diabetes"/"statins"). \b(?:stem)\w* matches the stem plus
# any continuation. Includes common disease/condition names + abbreviations the allowlist flip alone
# might not veto.
_CLINICAL_CONTENT = re.compile(
    r"\b(?:patient|disease|syndrome|disorder|infect|cancer|tumou?r|diabet|obes|hypertens|"
    r"cardiovascular|cardiac|renal|hepatic|pulmonary|respiratory|neuro|psychiatr|oncolog|"
    r"mortality|morbidity|incidence|prevalence|survival|prognos|remission|relaps|recurren|"
    r"complication|hospitali|readmission|cure rate|case fatality|fatality|fatal|death|deaths|"
    r"epidemi|pandemic|outbreak|covid|coronavirus|influenza|ebola|measles|sepsis|stroke|"
    r"guillain|gbs|long covid|"
    r"drug|medication|therap|treatment|vaccin|immuni|dose|dosing|dosage|clinical|diagnos|symptom|"
    r"adverse|side[- ]?effect|toxicit|contraindicat|comorbid|"
    r"semaglutide|tirzepatide|ozempic|wegovy|mounjaro|metformin|warfarin|statin)\w*"
    r"|\b\w+(?:mab|nib|tinib|gliptin|glutide|afil|statin|sartan|cycline|cillin|mycin|"
    r"parin|setron|grel|zepine)\b",
    re.IGNORECASE,
)

# ALLOWLIST of clearly NON-medical factual domains that qualify a query as right-sizeable "simple".
# This is OPT-IN (a query is simple ONLY if it matches a known-safe factual cue) rather than OPT-OUT of
# a clinical DENYLIST — a denylist can never be complete (Codex diff-gate iter-2: the clinical guard
# missed "death" / "fatality" / "GBS" / "COVID" / "Shingrix"). With the allowlist, "death rate from
# COVID-19" / "rate of GBS after Shingrix" have NO safe factual cue ⇒ fail open to complex regardless
# of whether the denylist names that disease. Financial / economic / corporate / geographic / civic
# facts only — NOT generic "rate of" / "how many", which can be a clinical outcome rate.
_SAFE_FACTUAL_CUE = re.compile(
    r"\b(stock price|share price|stock|shares|market cap|market capitali[sz]ation|"
    r"revenue|profit|earnings|dividend|valuation|net worth|ipo|"
    r"gdp|inflation rate|unemployment rate|exchange rate|interest rate|"
    # I-ready-006 (#1082) Codex diff-gate iter-3 P1-1: "population OF <place>" is a civic fact, but bare
    # "population" allowed epidemiology ("population WITH obesity", "population TAKING statins") to route
    # simple. Require "population of"; drug-utilization / disease-prevalence phrasings lose the safe cue
    # (and the clinical guard above is the second line of defense).
    r"population of|capital of|area of|time ?zone|headquarter|founded|founder|"
    r"\bceo\b|number of employees|ticker|stock exchange)\b",
    re.IGNORECASE,
)

_TEMPORAL_RANGE = re.compile(
    r"\b(over (?:the )?(?:past|last)\s+\d+\s+years?|in \d{4}|since \d{4}|\d+[- ]year)\b",
    re.IGNORECASE,
)


def classify_complexity(question: str) -> ComplexityDecision:
    """Classify ``question``. Deterministic, fail-open. Never raises — a malformed input returns a
    low-confidence ``complex`` decision so the caller takes the full path."""
    try:
        q = (question or "").strip()
        if not q:
            return ComplexityDecision("complex", 0.0, ["empty_question_fail_open"])

        reasons: list[str] = []
        # Clinical/medical content + the cohort-prevalence pattern force the FULL path FIRST (highest
        # priority) — a clinical safety/outcome/epidemiology question is never right-sized (Codex
        # diff-gate iter-1/4 P1-1).
        if _CLINICAL_CONTENT.search(q):
            return ComplexityDecision("complex", 0.9, ["clinical_medical_content"])
        if _COHORT_PREVALENCE.search(q):
            return ComplexityDecision("complex", 0.9, ["cohort_prevalence_pattern"])

        # Any explicit compare/causal/mechanism/synthesis/investment-judgment intent ⇒ full path.
        if _COMPLEX_INTENT.search(q):
            return ComplexityDecision("complex", 0.9, ["complex_intent_marker"])

        has_safe_factual = bool(_SAFE_FACTUAL_CUE.search(q))
        has_temporal = bool(_TEMPORAL_RANGE.search(q))

        # Named-entity proxy: a capitalized token NOT at sentence start (so the leading "What"/"How"
        # is excluded), OR an all-caps ticker (2-5 letters). Strip trailing punctuation so "France?" /
        # "Canada?" still count as entities (Codex diff-gate iter-4 P2 — else they only reach 0.70 and
        # miss the 0.80 right-sizing gate; this over-serves, but it's the safe direction).
        words = q.split()
        caps = [
            w.rstrip("?.!,;:") for w in words[1:]
            if re.match(r"^[A-Z][A-Za-z.&-]+[?.!,;:]?$", w)
        ]
        has_entity = len(caps) >= 1 or bool(re.search(r"\b[A-Z]{2,5}\b", q))
        word_count = len(words)

        # SIMPLE is OPT-IN: it REQUIRES a SAFE non-medical factual cue (financial/economic/civic). A
        # query with no safe cue — incl. any clinical outcome/safety rate the denylist might miss —
        # FAILS OPEN to complex. Multi-entity is fine (e.g. "Telus and Bell stock price over 20 years").
        if has_safe_factual and has_entity and word_count <= 25:
            reasons.append("safe_factual_cue+named_entity")
            if has_temporal:
                reasons.append("temporal_range")
            return ComplexityDecision("simple", 0.85, reasons)

        # A short safe-factual question without a clear named entity is a weaker simple signal.
        if has_safe_factual and word_count <= 15:
            reasons.append("safe_factual_cue_short")
            return ComplexityDecision("simple", 0.70, reasons)

        # No SAFE factual cue ⇒ FAIL OPEN to the full heavyweight path.
        reasons.append("no_safe_factual_signal_fail_open")
        return ComplexityDecision("complex", 0.50, reasons)
    except Exception as exc:  # noqa: BLE001 — never let the router abort a run; fail open to complex.
        return ComplexityDecision("complex", 0.0, [f"router_error_fail_open:{type(exc).__name__}"])
