"""I-gen-005 atom-first architecture: extract STRUCTURED claim atoms
from evidence direct_quotes.

Per Codex strategy verdict 2026-05-26
(`codex_quality_strategy_verdict.txt`) recommended_path #2 + design
verdict APPROVE_DESIGN + diff iter-1 REQUEST_CHANGES (4 P1s closed
this iteration).

Why this module exists:
    The current architecture lets V4 Pro write open prose, then catches
    fabrications post-hoc via strict_verify. Codex's read: that's
    backwards. The fix is to PRE-EXTRACT verifiable facts (atoms) from
    cited evidence spans BEFORE generation, then constrain V4 Pro to
    cite atom_ids that map to fixed spans. V4 Pro becomes the
    rhetorical/synthesis layer, not the fact source.

Iter 2 (Codex iter-1 REQUEST_CHANGES) closes 4 P1 bugs:
    P1.1 unit_extraction_corrupts_units (line 209)
        Fix: special-case `%` without word boundary; word units need
        leading boundary; restrict fallback unit-scan to immediate
        post-value or comma-coordinate context only.

    P1.2 numeric_anchor_filter_emits_non_claim_values (line 438)
        Fix: NumberRole classifier (OUTCOME / DOSE / TIMEPOINT /
        SAMPLE_SIZE / CI_BOUND / CI_LEVEL) runs BEFORE atom creation.
        Only OUTCOME numbers become atoms. Doses, timepoints, sample
        sizes are stored as metadata fields on the OUTCOME atom they
        modify, not as separate atoms.

    P1.3 entity_comparator_binding_flips_arms (line 362)
        Fix: arm-local entity binding. For each value, find the
        nearest arm phrase ("with X", "X mg", "X group") within
        ~50 chars to the right (where clinical text typically places
        the arm label). Comparator from explicit "versus X" /
        "compared to Y" syntax separately.

    P1.4 literal_span_expansion_splits_decimals (line 483)
        Fix: decimal-aware sentence boundary regex. A period followed
        by a digit is part of a decimal (8.21), not a sentence end.
        Use ``\\.(?=\\s|$|\\n|[A-Z])`` boundary.

Also addresses Codex iter-1 P2s:
    - primary_section field added; section_tags computed dynamically
      from extracted comparator + dose + safety presence
    - Endpoint vocabulary extended with renal, CV/HF, obesity,
      metabolic, safety subgroup, and statistical-metadata terms

Module remains INTENTIONALLY pure-Python regex — no LLM call. Fast,
deterministic, reproducible. Atoms come from actual evidence text;
nothing fabricated here.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


# ---------------------------------------------------------------------------
# ClaimAtom — the structured record V4 Pro will cite from
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ClaimAtom:
    """A single verifiable claim extracted from an evidence span.

    Frozen because atom_id resolution depends on stable identity through
    the pipeline. 14 fields (13 from Codex APPROVE_DESIGN + primary_section
    added per Codex iter-1 diff review P2).
    """

    # Identity + provenance:
    atom_id: str            # "atom_001"
    evidence_id: str        # "ev_017"
    span_start: int         # offset in direct_quote where the atom is grounded
    span_end: int           # offset in direct_quote (exclusive)
    literal_text: str       # verbatim text from the span supporting this claim

    # Semantic fields:
    entity: str             # "tirzepatide 15 mg" / "SURPASS-2" / "apixaban"
    endpoint: str           # "HbA1c" / "body weight" / "stroke"
    comparator: str         # "semaglutide" / "placebo" / "" if none
    timepoint: str          # "40 weeks" / "1.8 years" / "" if none
    value: str              # "-2.30" / "0.69" / "82-86"
    unit: str               # "percentage points" / "kg" / "%" / "RR" / ""

    # Routing:
    primary_section: str            # Single best-fit section
    section_tags: tuple[str, ...]   # All sections this atom can serve
    tier: str                       # "T1" / "T2" / ...

    # Codex APPROVE_DESIGN additions:
    value_signed: bool              # True if the value is negative
    confidence: str                 # "high" | "medium" | "low"
    provenance_class: str           # "abstract_only" | "open_access" | ...
    source_paper_title: str         # for refusal disclosure


# ---------------------------------------------------------------------------
# NumberRole — what role does a numeric anchor play in clinical text?
# Codex iter-1 P1 #2 fix: classify each number BEFORE atom creation so
# timepoints / doses / sample-sizes / CI bounds don't pollute the catalog.
# ---------------------------------------------------------------------------

class NumberRole(Enum):
    OUTCOME = "outcome"          # Primary or secondary clinical endpoint value
    DOSE = "dose"                # Drug dose (5 mg, 0.5 μg)
    TIMEPOINT = "timepoint"      # Follow-up duration (40 weeks, 1.8 years)
    SAMPLE_SIZE = "sample_size"  # Number of participants (N=1879)
    CI_BOUND = "ci_bound"        # Confidence interval limits (0.58 to 0.95)
    CI_LEVEL = "ci_level"        # CI confidence level (95% CI)
    P_VALUE = "p_value"          # P-value (P<0.001)
    UNKNOWN = "unknown"          # Couldn't classify


# Classifiers — small per-role regex patterns evaluated against the
# IMMEDIATE neighborhood of the number (±20 chars). Order matters: first
# match wins. OUTCOME is the implicit default if no classifier hits.

# Dose: number immediately followed by mg/μg/U/etc with a drug name nearby
_DOSE_UNIT_RE = re.compile(
    r"^\s?(mg|μg|mcg|g|IU|U)\b",
    re.IGNORECASE,
)

# Timepoint: surrounded by "at/after/by/over" + "weeks/months/years/..."
_TIMEPOINT_BEFORE_RE = re.compile(
    r"\b(?:at|after|by|over|in|through|for|of)\s+\d+(?:\.\d+)?\s*"
    r"(?:weeks?|months?|years?|days?|hours?|min(?:utes?)?)\b$",
    re.IGNORECASE,
)
_TIMEPOINT_TRAILING_RE = re.compile(
    r"^\s?(?:weeks?|months?|years?|days?|hours?|min(?:utes?)?)\b",
    re.IGNORECASE,
)

# Sample size: number preceded by N=, n=, "enrolled", "randomized",
# "patients with", "participants with", "trial of", etc.
_SAMPLE_SIZE_LEFT_RE = re.compile(
    r"(?:\b(?:[Nn]\s*=\s*|enrolled|randomi[sz]ed|"
    r"included|recruited|trial\s+of|patients\s+with|"
    r"participants\s+with|adults\s+with|subjects\s+with|"
    r"a\s+total\s+of|cohort\s+of|study\s+of|population\s+of)\s*)$",
    re.IGNORECASE,
)
# Sample size: number followed by "patients", "participants", "adults",
# "subjects" (e.g., "1879 adults", "18,201 patients").
_SAMPLE_SIZE_RIGHT_RE = re.compile(
    r"^\s*"
    r"(?:patients?|participants?|adults?|subjects?|"
    r"individuals|persons|men|women)\b",
    re.IGNORECASE,
)

# CI bound: number is inside parens with "CI" pattern nearby. Iter-3
# replaced the iter-2 brittle left/right regex chain with the
# _is_inside_ci_parens() structural walk; iter-4 added
# _is_ci_bound_unparen() for non-parenthesized "HR 0.74, 95% CI 0.58,
# 0.95" forms. Only _CI_PAREN_LEFT_RE remains as a defense-in-depth
# catch for paren-only ranges without the "CI" word literal.
_CI_PAREN_LEFT_RE = re.compile(r"[\(\[][-−]?\d+(?:\.\d+)?\s*(?:to|[-–—])\s*$")

# CI level: number directly followed by "% CI" or "% confidence interval"
_CI_LEVEL_RIGHT_RE = re.compile(
    r"^\s?%?\s*(?:CI|confidence\s+interval)\b",
    re.IGNORECASE,
)

# P-value: "P<", "P=", "P>", "p value", "P-value"
_P_VALUE_LEFT_RE = re.compile(
    r"\b[Pp]\s*[<>=]\s*$|\b[Pp][-\s]?(?:value)?\s*=?\s*$",
)


# ---------------------------------------------------------------------------
# Endpoint vocabulary (expanded per Codex iter-1 P1 review)
# Each tuple = (regex_pattern, canonical_name, primary_section, secondary_tags)
# ---------------------------------------------------------------------------

_ENDPOINT_VOCAB: list[tuple[re.Pattern, str, str, tuple[str, ...]]] = [
    # ── Glycemic ──
    (re.compile(r"\b(?:HbA1c|HbA1C|glycated\s+hemoglobin|A1C)\b", re.IGNORECASE),
     "HbA1c", "Efficacy", ("Efficacy",)),
    (re.compile(r"\b(?:FPG|fasting\s+plasma\s+glucose|fasting\s+serum\s+glucose|FSG)\b", re.IGNORECASE),
     "fasting glucose", "Efficacy", ("Efficacy",)),
    (re.compile(r"\bnormoglycemi[ac]\b|\bHbA1c\s*<\s*5\.7", re.IGNORECASE),
     "normoglycemia (HbA1c<5.7%)", "Efficacy", ("Efficacy",)),

    # ── Weight / obesity / metabolic (Codex iter-1 vocab additions) ──
    (re.compile(r"\b(?:body\s+weight|weight\s+loss|weight\s+reduction|kg\s+loss)\b", re.IGNORECASE),
     "body weight", "Efficacy", ("Efficacy",)),
    (re.compile(r"\bBMI\b", re.IGNORECASE),
     "BMI", "Efficacy", ("Efficacy",)),
    (re.compile(r"\bwaist\s+circumference\b", re.IGNORECASE),
     "waist circumference", "Efficacy", ("Efficacy",)),
    (re.compile(r"\b(?:percent|%)\s+(?:body[-\s])?weight\s+(?:change|reduction|loss)", re.IGNORECASE),
     "% body weight change", "Efficacy", ("Efficacy",)),
    (re.compile(r"(?:≥|>=|\bat\s+least\s+)\s?(?:5|10|15|20)\s?%\s*(?:weight\s+loss|body[-\s]?weight)", re.IGNORECASE),
     "weight-loss threshold (≥5/10/15/20%)", "Efficacy", ("Efficacy",)),
    (re.compile(r"\b(?:insulin\s+sensitivity|HOMA[-\s]?IR)\b", re.IGNORECASE),
     "insulin sensitivity", "Mechanism", ("Mechanism", "Efficacy")),
    (re.compile(r"\bC[-\s]?peptide\b", re.IGNORECASE),
     "C-peptide", "Mechanism", ("Mechanism",)),
    (re.compile(r"\bbeta[-\s]?cell\s+function\b", re.IGNORECASE),
     "beta-cell function", "Mechanism", ("Mechanism",)),

    # ── Cardiovascular / heart failure (Codex iter-1 vocab additions) ──
    (re.compile(r"\bMACE\b|major\s+adverse\s+cardiovascular\s+events?", re.IGNORECASE),
     "MACE", "Efficacy", ("Efficacy", "Safety")),
    (re.compile(r"\b(?:cardiovascular|CV)\s+(?:death|mortality)", re.IGNORECASE),
     "cardiovascular mortality", "Efficacy", ("Efficacy", "Safety")),
    (re.compile(r"\ball[-\s]?cause\s+(?:death|mortality)", re.IGNORECASE),
     "all-cause mortality", "Efficacy", ("Efficacy", "Safety")),
    (re.compile(r"\b(?:hospitalization\s+for\s+heart\s+failure|HF\s+hospitalization|HHF)\b", re.IGNORECASE),
     "heart failure hospitalization", "Efficacy", ("Efficacy", "Safety")),
    (re.compile(r"\b(?:ischemic\s+)?stroke\b(?!\s+prevention)", re.IGNORECASE),
     "stroke", "Efficacy", ("Efficacy", "Safety")),
    (re.compile(r"\bmyocardial\s+infarction|\bMI\b(?!\s+\d)", re.IGNORECASE),
     "myocardial infarction", "Efficacy", ("Efficacy", "Safety")),
    (re.compile(r"\brevascularization\b", re.IGNORECASE),
     "revascularization", "Efficacy", ("Efficacy",)),

    # ── Blood pressure ──
    (re.compile(r"\bsystolic\s+blood\s+pressure|\bsystolic\s+BP\b|\bSBP\b", re.IGNORECASE),
     "systolic BP", "Efficacy", ("Efficacy",)),
    (re.compile(r"\bdiastolic\s+blood\s+pressure|\bdiastolic\s+BP\b|\bDBP\b", re.IGNORECASE),
     "diastolic BP", "Efficacy", ("Efficacy",)),

    # ── Lipids ──
    (re.compile(r"\b(?:LDL[-\s]?C|low[-\s]density\s+lipoprotein)", re.IGNORECASE),
     "LDL-C", "Efficacy", ("Efficacy",)),
    (re.compile(r"\btriglycerides?\b", re.IGNORECASE),
     "triglycerides", "Efficacy", ("Efficacy",)),
    (re.compile(r"\b(?:HDL[-\s]?C|high[-\s]density\s+lipoprotein)", re.IGNORECASE),
     "HDL-C", "Efficacy", ("Efficacy",)),

    # ── Renal (Codex iter-1 vocab additions) ──
    (re.compile(r"\beGFR\b|\bestimated\s+GFR\b|\bglomerular\s+filtration\s+rate\b", re.IGNORECASE),
     "eGFR", "Efficacy", ("Efficacy", "Safety")),
    (re.compile(r"\b(?:UACR|urine\s+albumin[-\s]?creatinine|albuminuria)\b", re.IGNORECASE),
     "UACR/albuminuria", "Efficacy", ("Efficacy",)),
    (re.compile(r"\bserum\s+creatinine\b|\bcreatinine\b", re.IGNORECASE),
     "serum creatinine", "Safety", ("Safety",)),
    (re.compile(r"\bkidney\s+composite\b|\brenal\s+composite\b", re.IGNORECASE),
     "kidney composite", "Efficacy", ("Efficacy", "Safety")),
    (re.compile(r"\bCKD\s+progression\b|\bchronic\s+kidney\s+disease\b", re.IGNORECASE),
     "CKD progression", "Efficacy", ("Efficacy", "Safety")),
    (re.compile(r"\b(?:AKI|acute\s+kidney\s+injury)\b", re.IGNORECASE),
     "acute kidney injury", "Safety", ("Safety",)),

    # ── Safety: AEs ──
    (re.compile(r"\bserious\s+adverse\s+events?|\bSAE\b", re.IGNORECASE),
     "serious adverse events", "Safety", ("Safety",)),
    (re.compile(r"\b(?:treatment[-\s]emergent\s+)?adverse\s+events?\b|\bTEAE\b", re.IGNORECASE),
     "adverse events", "Safety", ("Safety",)),
    (re.compile(r"\b(?:discontinuation|discontinued|treatment\s+withdrawal)\b", re.IGNORECASE),
     "discontinuation", "Safety", ("Safety",)),
    (re.compile(r"\bnausea\b", re.IGNORECASE), "nausea", "Safety", ("Safety",)),
    (re.compile(r"\bvomiting\b", re.IGNORECASE), "vomiting", "Safety", ("Safety",)),
    (re.compile(r"\bdiarr?h[oe]a\b", re.IGNORECASE), "diarrhea", "Safety", ("Safety",)),
    (re.compile(r"\babdominal\s+pain\b", re.IGNORECASE), "abdominal pain", "Safety", ("Safety",)),
    (re.compile(r"\b(?:gastrointestinal|GI)\s+(?:adverse|events?)\b", re.IGNORECASE),
     "GI events", "Safety", ("Safety",)),
    (re.compile(r"\bhypoglycem(?:ia|ic)\b", re.IGNORECASE),
     "hypoglycemia", "Safety", ("Safety",)),
    (re.compile(r"\bpancreatitis\b", re.IGNORECASE),
     "pancreatitis", "Safety", ("Safety",)),
    (re.compile(r"\b(?:intracranial\s+hemorrhage|ICH)\b", re.IGNORECASE),
     "intracranial hemorrhage", "Safety", ("Safety",)),
    (re.compile(r"\bGI\s+bleeding\b|\bgastrointestinal\s+bleeding\b", re.IGNORECASE),
     "GI bleeding", "Safety", ("Safety",)),
    (re.compile(r"\bmajor\s+bleeding\b", re.IGNORECASE),
     "major bleeding", "Safety", ("Safety",)),
    (re.compile(r"\b(?:C[-\s]?cell\s+(?:hyperplasia|cancer)|thyroid\s+(?:carcinoma|cancer)|MTC)\b", re.IGNORECASE),
     "thyroid C-cell signal", "Safety", ("Safety",)),
    (re.compile(r"\bretinopathy\b", re.IGNORECASE),
     "retinopathy", "Safety", ("Safety",)),
    (re.compile(r"\b(?:gallbladder\s+disease|cholelithiasis|cholecystitis)\b", re.IGNORECASE),
     "gallbladder disease", "Safety", ("Safety",)),

    # ── Treatment differences (efficacy + comparative) ──
    (re.compile(r"\bestimated\s+treatment\s+difference|\bETD\b", re.IGNORECASE),
     "estimated treatment difference", "Comparative", ("Efficacy", "Comparative")),
    (re.compile(r"\btreatment\s+difference\b", re.IGNORECASE),
     "treatment difference", "Comparative", ("Efficacy", "Comparative")),

    # ── Mechanism ──
    (re.compile(r"\bhalf[-\s]?life\b", re.IGNORECASE),
     "half-life", "Mechanism", ("Mechanism",)),
    (re.compile(r"\bbioavailability\b", re.IGNORECASE),
     "bioavailability", "Mechanism", ("Mechanism",)),
    (re.compile(r"\b(?:Tmax|tmax|T_max)\b"),
     "Tmax", "Mechanism", ("Mechanism",)),
    (re.compile(r"\bM[-\s]?value\b", re.IGNORECASE),
     "M-value", "Mechanism", ("Mechanism",)),
    (re.compile(r"\b(?:hyperinsulinemic[-\s]?euglycemic\s+clamp|HE\s+clamp)\b", re.IGNORECASE),
     "HE clamp", "Mechanism", ("Mechanism",)),
    (re.compile(r"\b(?:receptor\s+(?:affinity|binding|selectivity))\b", re.IGNORECASE),
     "receptor binding", "Mechanism", ("Mechanism",)),
]


# ---------------------------------------------------------------------------
# Statistical metadata vocab (Codex iter-1 addition).
# These mark the NUMBER as a metric type, not as a primary endpoint
# value. When an HR/OR/RR is detected, it modifies the OUTCOME atom's
# unit field rather than creating its own atom.
# ---------------------------------------------------------------------------

_STAT_METADATA: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\b(?:hazard\s+ratio|HR)\b", re.IGNORECASE), "HR"),
    (re.compile(r"\b(?:relative\s+risk|RR)\b", re.IGNORECASE), "RR"),
    (re.compile(r"\b(?:risk\s+ratio)\b", re.IGNORECASE), "RR"),
    (re.compile(r"\b(?:odds\s+ratio|OR)\b", re.IGNORECASE), "OR"),
    (re.compile(r"\b(?:absolute\s+risk\s+reduction|ARR)\b", re.IGNORECASE), "ARR"),
    (re.compile(r"\b(?:number\s+needed\s+to\s+treat|NNT)\b", re.IGNORECASE), "NNT"),
]


# ---------------------------------------------------------------------------
# Drug + trial vocabularies (kept local for self-containment)
# ---------------------------------------------------------------------------

_DRUG_RE = re.compile(
    r"\b("
    r"tirzepatide|semaglutide|liraglutide|dulaglutide|exenatide|lixisenatide"
    r"|empagliflozin|dapagliflozin|canagliflozin|ertugliflozin|sotagliflozin"
    r"|sitagliptin|saxagliptin|linagliptin|alogliptin|vildagliptin"
    r"|metformin|insulin\s+(?:glargine|degludec|aspart|lispro|detemir|isophane|NPH)?"
    r"|pioglitazone|rosiglitazone"
    r"|glipizide|glyburide|glimepiride|tolbutamide"
    r"|repaglinide|nateglinide"
    r"|acarbose|miglitol"
    r"|warfarin|coumarin|VKA|vitamin\s+K\s+antagonist"
    r"|dabigatran|rivaroxaban|apixaban|edoxaban|DOAC|NOAC|direct\s+oral\s+anticoagulant"
    r"|aspirin|clopidogrel|prasugrel|ticagrelor"
    r"|Mounjaro|Zepbound|Ozempic|Wegovy|Rybelsus|Victoza|Trulicity|Byetta|Bydureon"
    r"|Jardiance|Farxiga|Invokana|Steglatro"
    r"|Januvia|Onglyza|Tradjenta|Nesina"
    r"|Eliquis|Xarelto|Pradaxa|Lixiana|Savaysa"
    r")\b",
    re.IGNORECASE,
)

_TRIAL_RE = re.compile(
    r"\b("
    r"SURPASS(?:[- ]?(?:CVOT|J|AP|\d))?"
    r"|SURMOUNT(?:[- ]?\d+)?"
    r"|SUSTAIN(?:[- ]?\d+)?"
    r"|REWIND|LEADER|DECLARE(?:-?TIMI(?:[- ]?\d+)?)?"
    r"|EMPA(?:-?REG)?"
    r"|CANVAS|CREDENCE|DAPA-?HF|DAPA-?CKD"
    r"|STEP(?:[- ]?\d+)?"
    r"|PIONEER(?:[- ]?\d+)?"
    r"|AWARD(?:[- ]?\d+)?"
    r"|EXSCEL|ELIXA|HARMONY"
    r"|ACCORD|ADVANCE|VADT|UKPDS|DCCT|EDIC"
    r"|EMPEROR-?(?:Preserved|Reduced|Pooled)?"
    r"|ARISTOTLE|RE[-\s]?LY|ROCKET[-\s]?AF|ENGAGE[-\s]?AF"
    r"|AVERROES|RELY-?ABLE"
    r"|TIDE|TARGET|SOUL"
    r"|VERTIS-?(?:CV)?"
    r")\b",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# I-gen-005 Step 3k (Codex APPROVE_DESIGN iter-1): markdown safety-table
# row detection + per-cell atom extraction. Target: safety tables with
# format like:
#   | Nausea | 82 (17.4) | 111 | 90 (19.2) | 124 | 104 (22.1) | ... |
# Each cell with a percentage in parens or trailing % becomes a per-cell
# atom with endpoint = row header. Column-to-arm mapping is DEFERRED
# (Codex P2: trial-name entity fallback acceptable for now).
# ---------------------------------------------------------------------------

# Safety endpoint vocab for table-row headers. Mirrors the safety subset
# of _ENDPOINT_VOCAB so any row labeled with a known safety endpoint
# becomes a per-cell extraction candidate.
_SAFETY_TABLE_HEADER_RE = re.compile(
    r"(?:"
    r"^|^\W+|"  # row prefix tolerant (markdown bullets, leading symbols)
    r"\b"
    r")"
    r"(?P<endpoint>"
    r"nausea|vomiting|diarrh(?:o)?ea|constipation|abdominal\s+pain|"
    r"dyspepsia|decreased\s+appetite|"
    r"hypoglycem(?:ia|ic)|"
    r"pancreatitis|gallbladder(?:\s+disease)?|cholelithiasis|cholecystitis|"
    r"retinopathy|"
    r"injection[-\s]?site\s+reactions?|"
    r"(?:all\s+)?(?:treatment[-\s]?related\s+|treatment[-\s]?emergent\s+)?"
    r"adverse\s+events?(?:\s+leading\s+to\s+(?:treatment\s+)?discontinuation"
    r"(?:\s+of\s+\w+(?:\s+(?:or|and)\s+\w+)?)?)?|"
    r"TEAE|"
    r"serious\s+adverse\s+events?|SAEs?|"
    r"discontinuation|treatment\s+withdrawal|"
    r"patients\s+with\s+(?:≥|>=|≧)\s*1\s+(?:serious\s+)?adverse\s+events?|"
    r"patients\s+with\s+at\s+least\s+1\s+(?:serious\s+)?adverse\s+events?|"
    r"(?:all\s+)?gastrointestinal\s+(?:adverse\s+)?events?|"
    r"(?:all\s+)?GI\s+(?:adverse\s+)?events?|"
    r"thyroid\s+(?:carcinoma|cancer|c[-\s]?cell)|MTC|"
    r"C[-\s]?cell\s+(?:hyperplasia|cancer)|"
    r"GI\s+bleeding|gastrointestinal\s+bleeding|major\s+bleeding|"
    r"intracranial\s+hemorrhage|ICH|"
    # Codex Step 3k diff iter-1 P2 #2: expanded vocab for fresh tables
    r"death|all[-\s]?cause\s+mortality|"
    r"fatigue|asthenia|headache|dizziness|"
    r"hypersensitivity|allergic\s+reactions?|anaphylaxis|"
    r"acute\s+kidney\s+injury|AKI|renal\s+(?:impairment|failure)|"
    r"neoplasm|cancer|malignancy|"
    r"calcitonin|"
    r"hyperglycem(?:ia|ic)|"
    r"infection|"
    r"urinary\s+tract\s+infection|UTI|"
    r"upper\s+respiratory\s+tract\s+infection|URTI|"
    r"nasopharyngitis"
    r")",
    re.IGNORECASE,
)

# Cell percentage extraction:
#   - Number followed by % → that number
#   - Number inside (...) → that number (canonical "n (pct)" form)
# Bare numbers are SKIPPED per Codex Step 3k P2 (column-header parsing
# required to know if bare numbers are percentages vs counts).
_CELL_PCT_TRAILING_RE = re.compile(r"(?P<val>\d+(?:\.\d+)?)\s*%")
_CELL_PCT_PAREN_RE = re.compile(r"\(\s*(?P<val>\d+(?:\.\d+)?)\s*\)")


def _canonicalize_safety_endpoint(raw: str) -> str:
    """Map a raw safety table header to the canonical endpoint name
    used elsewhere in the catalog (matching _ENDPOINT_VOCAB entries).
    """
    r = raw.strip().lower()
    if "serious adverse" in r or re.match(r"^saes?$", r) or "≥1 serious adverse" in r:
        return "serious adverse events"
    if "leading to" in r and ("discontinuation" in r or "treatment withdrawal" in r):
        return "discontinuation"
    if "≥1 adverse event" in r or r in ("teae", "adverse event", "adverse events"):
        return "adverse events"
    if "gastrointestinal" in r or r in ("gi events", "gi adverse events"):
        return "GI events"
    if "injection" in r and "site" in r:
        return "injection-site reaction"
    if "thyroid" in r or r == "mtc" or "c-cell" in r or "c cell" in r:
        return "thyroid C-cell signal"
    if "gallbladder" in r or "cholelithiasis" in r or "cholecystitis" in r:
        return "gallbladder disease"
    # Common single-word endpoints — passthrough lowercase
    if r in (
        "nausea", "vomiting", "diarrhea", "diarrhoea", "constipation",
        "abdominal pain", "hypoglycemia", "hypoglycemic",
        "pancreatitis", "retinopathy", "discontinuation",
        "dyspepsia", "decreased appetite",
    ):
        if r == "diarrhoea":
            return "diarrhea"
        if r == "hypoglycemic":
            return "hypoglycemia"
        return r
    return r


# Codex Step 3k diff iter-3: raise from 14 to 30. The original 14
# was hit BEFORE the `||` row terminator in 5-arm tables (each arm
# has 2 columns: "n (pct)" + "No. of events"), producing rows that
# spilled across multiple actual rows.
_MAX_PIPES_PER_ROW = 30
# Empty-cell row separator pattern (markdown tables concatenated in
# a single line use "| |" as the row boundary).
_ROW_BOUNDARY_RE = re.compile(r"\|\s*\|")


def _detect_all_table_regions(direct_quote: str) -> list[tuple[int, int]]:
    """Codex Step 3k diff iter-2 P1 continuing: suppress legacy walk
    inside ANY pipe-rich region, not just safety-header rows. Catches
    descriptive sub-headers like 'Adverse events occurring in ≥5% of
    patients' which are still inside the table block.

    Returns list of (start, end) byte ranges in direct_quote where the
    pipe-density is high enough to be a table block. Heuristic: any
    window of 500 chars containing ≥6 `|` is part of a table; expand
    to the surrounding pipe-rich neighborhood.
    """
    if "|" not in direct_quote:
        return []
    pipe_positions = [i for i, c in enumerate(direct_quote) if c == "|"]
    if len(pipe_positions) < 6:
        return []
    regions: list[tuple[int, int]] = []
    # Group consecutive pipes where adjacent pipes are within 200 chars.
    # iter-3: raised from 80 to 200 to span descriptor cells like
    # "Adverse events occurring in ≥0.2% of the overall population
    # (i.e., 3 patients) and leading to discontinuation of tirzepatide
    # or semaglutide" between pipe-clusters of two data sections.
    cluster: list[int] = [pipe_positions[0]]
    for p in pipe_positions[1:]:
        if p - cluster[-1] <= 200:
            cluster.append(p)
        else:
            if len(cluster) >= 6:
                regions.append((cluster[0], cluster[-1] + 1))
            cluster = [p]
    if len(cluster) >= 6:
        regions.append((cluster[0], cluster[-1] + 1))
    return regions


def _iter_safety_table_rows(direct_quote: str) -> list[tuple[str, str, str]]:
    """Detect markdown safety-table rows in `direct_quote`.

    A row is a candidate if:
      1. First cell (preceded by `|` or line start) matches
         _SAFETY_TABLE_HEADER_RE
      2. Row has >= 3 pipe-separated data cells AFTER the header
      3. Row terminates at: newline, empty-cell row separator (`| |`),
         OR _MAX_PIPES_PER_ROW pipes (whichever comes first)

    Returns list of (endpoint_canonical, row_text, raw_endpoint_text).

    Header occurrences NOT inside a `|...|` row structure (i.e. in
    prose) are skipped. Each header occurrence is matched at most once.
    """
    rows: list[tuple[str, str, str, int]] = []
    text = direct_quote
    seen_starts: set[int] = set()
    for hdr in _SAFETY_TABLE_HEADER_RE.finditer(text):
        endpoint_text = hdr.group("endpoint")
        # Codex Step 3k diff iter-3 P1: use hdr.start("endpoint") not
        # hdr.start(). The `^\W+` prefix consumes leading symbols, so
        # hdr.start() is at position 0 (before `|`), forcing left_idx
        # to -1. Use the named group's start so left-scan finds the
        # actual `|` before the endpoint name.
        endpoint_start = hdr.start("endpoint")
        # Header must be inside a pipe-delimited structure. Codex Step 3k
        # diff iter-2 P2: walk LEFT until we find `|`, allowing arbitrary
        # cell content (e.g., "| Elevated blood calcitonin level |"
        # where the endpoint vocab "calcitonin" is not at cell start).
        # iter-3: bounded to 80 chars (typical cell width). Larger
        # scans land in unrelated cells.
        left_idx = endpoint_start - 1
        scan_steps = 0
        while left_idx >= 0 and scan_steps < 80:
            if text[left_idx] == "|":
                break
            if text[left_idx] == "\n":
                left_idx = -1
                break
            left_idx -= 1
            scan_steps += 1
        if left_idx < 0 or scan_steps >= 80 or text[left_idx] != "|":
            continue
        # Codex Step 3k diff iter-1 P1 #1: relax the right side — the
        # cell can contain additional text after the matched endpoint
        # phrase. The right boundary is the next `|`, not immediately
        # after the match end.
        right_idx = text.find("|", hdr.end())
        if right_idx < 0:
            continue
        # Avoid pathological gap (header matches but next `|` is too far,
        # e.g., in prose): reject if first-cell length > 200 chars.
        if right_idx - left_idx > 200:
            continue
        # Dedup: avoid matching the same header position twice via
        # overlapping regex matches.
        if left_idx in seen_starts:
            continue
        seen_starts.add(left_idx)
        # Walk forward from right_idx (the `|` right of header) counting
        # data cells. Stop at: newline, empty-cell boundary `| |`, OR
        # _MAX_PIPES_PER_ROW pipes total.
        pipe_count = 1  # the `|` between header and first data cell
        i = right_idx
        row_end = right_idx
        while i < len(text) and pipe_count <= _MAX_PIPES_PER_ROW:
            ch = text[i]
            if ch == "\n":
                break
            if ch == "|":
                # Empty-cell row boundary check: is the next non-space
                # also `|`? If so, this is the row terminator.
                j = i + 1
                while j < len(text) and text[j] in " \t":
                    j += 1
                if j < len(text) and text[j] == "|":
                    # Empty cell ahead — row ends at THIS pipe.
                    row_end = i
                    break
                pipe_count += 1
                row_end = i
            i += 1
        # Require >= 3 data cells in the row (3 pipes after the
        # header-right pipe).
        if pipe_count < 4:
            continue
        row_text = text[left_idx:row_end + 1]
        rows.append((endpoint_text.strip().lower(), row_text, endpoint_text, left_idx))
    return rows


def _extract_cell_percentages(row_text: str, header_end_idx: int) -> list[tuple[float, int, int, str]]:
    """For a table row, extract per-cell percentages.

    Returns list of (numeric_value, abs_start, abs_end, raw_text).
    abs_start/end are offsets WITHIN the row_text. Caller adjusts to
    direct_quote offsets.

    Skip:
      - Numbers before header_end_idx (the row header itself)
      - Bare numbers without % or ( ... ) context (Codex P2)
    """
    cells: list[tuple[float, int, int, str]] = []
    # Trailing-% form
    for m in _CELL_PCT_TRAILING_RE.finditer(row_text):
        if m.start() < header_end_idx:
            continue
        cells.append((float(m.group("val")), m.start("val"), m.end("val"), m.group(0)))
    # Parenthetical form
    for m in _CELL_PCT_PAREN_RE.finditer(row_text):
        if m.start() < header_end_idx:
            continue
        # Don't double-count if this paren cell already matched %
        already = any(
            c[1] == m.start("val") and c[2] == m.end("val")
            for c in cells
        )
        if not already:
            cells.append((float(m.group("val")), m.start("val"), m.end("val"), m.group(0)))
    return cells


# ---------------------------------------------------------------------------
# Number anchor + unit regexes (iter 2 fixes for P1 #1)
# ---------------------------------------------------------------------------

# Number anchor — same as iter 1
_NUMBER_ATOM_RE = re.compile(
    r"(?<![A-Za-z0-9_.])"
    r"(?P<value>"
    r"[-−]?\d+(?:[.,]\d+)?"
    r"(?:\s*[-–—]\s*[-−]?\d+(?:[.,]\d+)?)?"
    r")"
    r"(?![A-Za-z0-9_])"
)

# P1.1 fix: unit regex split into TWO patterns:
#   _UNIT_IMMEDIATE_RE — for unit attached directly after the number
#     (must match at position 0 of the text passed in)
#   _UNIT_PERCENT_RE — special-case for "%" without word boundary
# Word units (kg, mg, ...) require leading whitespace or hyphen so we
# don't match "kg" inside "kg/m2" mid-word or unrelated words.
_UNIT_PERCENT_RE = re.compile(r"^\s*(%|pp\b|percentage\s+points?)")
_UNIT_WORD_RE = re.compile(
    r"^\s+(?P<unit>"
    r"kg/m\^?2|mmol/L|mg/dL|mg/kg|μg/kg|"
    r"kg|g|mL|L|μg|mcg|IU|U|"
    r"BPM|bpm|mmHg|"
    r"per\s+1000|per\s+100|per\s+1000\s+person[-\s]?years?"
    r")\b",
    re.IGNORECASE,
)
# Dose unit — only for classification (does NOT become an OUTCOME atom).
# Iter-3 fix (Codex iter-2 P2): require NON-slash terminator to avoid
# matching mg in "mg/dL" (an LDL-C lab unit, not a dose). Negative
# lookahead `(?!/)` lets _UNIT_WORD_RE (mg/dL, mg/kg) win for compound
# lab units.
_UNIT_DOSE_RE = re.compile(r"^\s?(mg|μg|mcg|g|IU|U)(?!\w)(?!/)\b", re.IGNORECASE)


# ---------------------------------------------------------------------------
# Arm-local entity binding (P1 #3 fix)
# ---------------------------------------------------------------------------

# "with X dose" or "with X" — typically "...was -2.30 with tirzepatide 15 mg"
_ARM_PHRASE_RIGHT_RE = re.compile(
    r"^\s*(?:with|in|for|on)\s+"
    r"(?P<arm>"
    r"(?:"
    + r"|".join(_DRUG_RE.pattern.lstrip("\\b(").rstrip(")\\b").split("|"))
    + r")"  # any drug
    r"(?:\s+\d+(?:\.\d+)?\s*(?:mg|μg|mcg|U|IU))?"  # optional dose
    r")",
    re.IGNORECASE,
)

# Comparator phrase: "versus X" / "compared to Y" / "vs Z"
_COMPARATOR_PHRASE_RE = re.compile(
    r"\b(?:vs\.?|versus|compared\s+(?:to|with)|against|relative\s+to)\b",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Decimal-aware sentence boundary (P1 #4 fix)
# ---------------------------------------------------------------------------

# A sentence boundary is: . ; ! ? \n followed by whitespace/EOL/uppercase.
# A "." between digits (decimals like 8.21) is NOT a boundary.
# Used by literal_text expansion to avoid splitting "8.21" mid-decimal.
_SENTENCE_BOUNDARY_RE = re.compile(r"[.;!?](?=\s|$|\n)(?!\d)|\n+")


# ---------------------------------------------------------------------------
# Extraction helpers
# ---------------------------------------------------------------------------

_CONTEXT_BEFORE = 150
_CONTEXT_AFTER = 100
_ARM_LOOKAHEAD = 50  # P1 #3: arm phrase typically within 50 chars to the right


def _is_inside_ci_parens(direct_quote: str, num_start: int) -> bool:
    """Iter-3 helper (Codex iter-2 continuing-P1.2): True if `num_start`
    is inside a parenthetical group whose content contains "CI" before
    the number. Catches comma form, dash-range form, "to" form uniformly.

    Walks backward from num_start tracking paren depth. When we find the
    enclosing `(` or `[`, scan from that paren forward to num_start; if
    `\\bCI\\b` appears in that prefix, the number is a CI bound.
    """
    i = num_start - 1
    paren_depth = 0
    while i >= 0:
        c = direct_quote[i]
        if c == ')' or c == ']':
            paren_depth += 1
        elif c == '(' or c == '[':
            if paren_depth == 0:
                inside = direct_quote[i + 1:num_start]
                return bool(re.search(r'\bCI\b', inside, re.IGNORECASE))
            paren_depth -= 1
        i -= 1
    return False


def _is_ci_bound_unparen(direct_quote: str, num_start: int) -> bool:
    """Iter-4 helper (Codex iter-3 continuing-P1): catch non-parenthesized
    CI forms: "HR 0.74, 95% CI 0.58, 0.95" or "HR 0.74, 95% CI 0.58-0.95".

    The most recent "CI" mention within 60 chars LEFT of the number,
    with no sentence terminator between, where this number is the 1st
    or 2nd number after CI (first bound or second bound). Confidence-
    interval spelled-out form is also supported.
    """
    left_60 = direct_quote[max(0, num_start - 60):num_start]
    # Find most recent CI mention (last finditer match)
    ci_pos = -1
    for m in re.finditer(
        r'\b(?:CI|confidence\s+interval)\b',
        left_60,
        re.IGNORECASE,
    ):
        ci_pos = m.end()
    if ci_pos == -1:
        return False
    between = left_60[ci_pos:]
    # Sentence boundary between CI and number → not a CI bound
    if re.search(r'[.;!?](?=\s|$)(?!\d)', between):
        return False
    # Newline between CI and number → different context
    if "\n" in between:
        return False
    # Count digits between — at most 1 prior number (this is bound 1 or 2)
    nums_before = len(re.findall(r'[-−]?\d+(?:\.\d+)?', between))
    return nums_before <= 1


def _classify_number(
    direct_quote: str,
    match: re.Match,
    sentence_start: int = 0,
) -> tuple[NumberRole, str]:
    """Classify a numeric anchor as OUTCOME / DOSE / TIMEPOINT / etc.

    Returns (role, normalized_unit). Per Codex iter-1 P1 #2: skip
    non-OUTCOME numbers from atom creation.

    sentence_start parameter (iter-2 refinement): the offset of the
    sentence the value is in. Used for unit-inheritance lookback: in
    "-2.01 percentage points ... -2.24 with 10 mg" the second value
    inherits "percentage points" from the comma-coordinate antecedent
    within the SAME sentence.
    """
    num_start, num_end = match.start(), match.end()
    n = len(direct_quote)
    right = direct_quote[num_end:min(num_end + 30, n)]
    left = direct_quote[max(0, num_start - 60):num_start]

    # --- CI bound / CI level ---
    if _CI_LEVEL_RIGHT_RE.match(right):
        return NumberRole.CI_LEVEL, "%"
    # Iter-3 fix (Codex iter-2 continuing-P1.2): catch ALL CI-parens forms
    # (to / comma / dash-range / nested) by detecting that the number lives
    # inside parens whose content contains "CI". Covers:
    #   (95% CI, 0.58 to 0.95)   — original "to" form
    #   (95% CI 0.58, 0.95)      — comma form
    #   (95% CI 0.58-0.95)       — compact dash range (matched as ONE token)
    #   (CI 0.58 to 0.95)        — bare "CI"
    if _is_inside_ci_parens(direct_quote, num_start):
        return NumberRole.CI_BOUND, ""
    # Iter-4 fix (Codex iter-3 continuing-P1): non-parenthesized CI.
    # "HR 0.74, 95% CI 0.58, 0.95" or "HR 0.74, 95% CI 0.58-0.95" still
    # passed iter-3 because no enclosing paren. The helper checks recent
    # CI mention within 60 chars + ≤1 prior number + no sentence boundary.
    if _is_ci_bound_unparen(direct_quote, num_start):
        return NumberRole.CI_BOUND, ""
    # Paren-only range without "CI" word: "(0.58 to 0.95)" — second bound
    # via left context ending with "(<digit> to ". CI-bearing-parens already
    # caught above; this catches bare paren ranges (clinically rare but
    # safer to skip than emit).
    if _CI_PAREN_LEFT_RE.search(left):
        return NumberRole.CI_BOUND, ""

    # --- P-value ---
    if _P_VALUE_LEFT_RE.search(left):
        return NumberRole.P_VALUE, ""

    # --- Dose ---
    dose_m = _UNIT_DOSE_RE.match(right)
    if dose_m:
        return NumberRole.DOSE, dose_m.group(1).lower()

    # --- Timepoint ---
    if _TIMEPOINT_TRAILING_RE.match(right):
        return NumberRole.TIMEPOINT, _TIMEPOINT_TRAILING_RE.match(right).group(0).strip().lower()
    if _TIMEPOINT_BEFORE_RE.search(left):
        return NumberRole.TIMEPOINT, ""

    # --- Sample size ---
    if _SAMPLE_SIZE_LEFT_RE.search(left) or _SAMPLE_SIZE_RIGHT_RE.match(right):
        return NumberRole.SAMPLE_SIZE, ""

    # --- OUTCOME: unit via direct attachment ---
    pct = _UNIT_PERCENT_RE.match(right)
    if pct:
        unit_raw = pct.group(1)
        if unit_raw.lower().startswith("pp") or "percentage" in unit_raw.lower():
            return NumberRole.OUTCOME, "percentage points"
        return NumberRole.OUTCOME, "%"

    word_m = _UNIT_WORD_RE.match(right)
    if word_m:
        return NumberRole.OUTCOME, word_m.group("unit").lower()

    # Stat metadata (HR, RR, OR) — unitless ratios
    left_30 = direct_quote[max(0, num_start - 30):num_start]
    for pat, label in _STAT_METADATA:
        if pat.search(left_30):
            return NumberRole.OUTCOME, label

    # --- Unit inheritance from comma-coordinate antecedent (P1 #1 fix) ---
    # Codex proposed_fix: "only inherit a prior unit within an explicit
    # coordinate/list pattern."
    #
    # Iter-2 refinement: in clinical text "value unit with X, value with Y,
    # and value with Z" — the unit attaches to value 1 only, but
    # SEMANTICALLY all values share the unit. Trigger inheritance when:
    #   (a) sentence_left contains a `value unit` pair, AND
    #   (b) sentence_left contains a coordinate connector (comma OR
    #       "and ") somewhere after the value-unit pair (indicates a
    #       list/coordinate construction).
    sentence_left = direct_quote[sentence_start:num_start]
    if len(sentence_left) > 300:
        sentence_left = sentence_left[-300:]
    coord_unit_pat = re.compile(
        r"[-−]?\d+(?:\.\d+)?\s+"
        r"(?P<unit>"
        r"percentage\s+points?|pp|%|"
        r"kg/m\^?2|mmol/L|mg/dL|"
        r"kg|g|mL|L|μg|mcg|IU|U|"
        r"BPM|bpm|mmHg)"
        r"\b",
        re.IGNORECASE,
    )
    last_unit: Optional[str] = None
    last_unit_end = -1
    for cm in coord_unit_pat.finditer(sentence_left):
        last_unit = cm.group("unit").lower()
        last_unit_end = cm.end()
    if last_unit is not None:
        # Confirm coordinate structure: after the value-unit pair, look
        # for a comma or "and " or "or " separator within the same sentence.
        after_unit = sentence_left[last_unit_end:]
        if re.search(r"(?:,|\band\b|\bor\b|;)", after_unit):
            if last_unit in ("pp", "percentage point", "percentage points"):
                return NumberRole.OUTCOME, "percentage points"
            return NumberRole.OUTCOME, last_unit

    return NumberRole.UNKNOWN, ""


def _find_endpoint(
    text: str,
    num_offset: Optional[int] = None,
) -> tuple[str, str, tuple[str, ...]]:
    """Find endpoint in `text`. Returns (canonical, primary_section, tags).

    Iter-3 fix (Codex iter-2 novel-P1 multi_endpoint_first_binding): when
    `num_offset` is provided, search for the CLOSEST endpoint phrase to
    the value (walking backward first, then forward). Without this, a
    sentence like "...HbA1c by -2.30 percentage points and body weight by
    -11.2 kg" binds -11.2 kg to HbA1c (first endpoint), producing a
    FALSE atom.

    Legacy call (no num_offset) keeps the original first-match behavior
    for tests that don't pass a position.
    """
    if num_offset is None:
        for pat, canonical, primary, tags in _ENDPOINT_VOCAB:
            if pat.search(text):
                return canonical, primary, tags
        return "", "", ()

    # Collect ALL endpoint matches with their positions
    candidates: list[tuple[int, str, str, tuple[str, ...]]] = []
    for pat, canonical, primary, tags in _ENDPOINT_VOCAB:
        for m in pat.finditer(text):
            candidates.append((m.end(), canonical, primary, tags))

    if not candidates:
        return "", "", ()

    # Iter-5 fix (Codex iter-4 continuing-P1): coordinated endpoint
    # ambiguity — use CLAUSE STRUCTURE, not character distance.
    #
    # Algorithm:
    #   1. Find closest endpoint LEFT of value.
    #   2. For each OTHER endpoint with a different canonical also on
    #      the left, check the region between them and the closest:
    #      - If sentence/clause break (`.` or `;`) → different clause,
    #        not ambiguous, skip this candidate.
    #      - If a digit appears between → already separated by a value,
    #        skip.
    #      - If a coordinate connector (`and`/`or`/`,`) → ambiguous in
    #        same clause → REFUSE atom.
    #
    # Catches all coordinated forms including long endpoint phrases
    # ("all-cause mortality and hospitalization for heart failure ...")
    # without false refusals on multi-clause sentences.
    left_cands = sorted(
        [c for c in candidates if c[0] <= num_offset],
        key=lambda c: c[0],
    )
    if left_cands:
        closest = left_cands[-1]
        # Iter-5+ fix (Codex iter-5 continuing-P1): the previous
        # `between = text[c[0]:closest[0]]` included the CLOSEST
        # endpoint token itself in the slice. Endpoint names with
        # digits (HbA1c, T2DM) satisfied the digit-separator guard
        # and bypassed the refusal. Find the closest-endpoint START
        # position via its pattern match, then slice up to that
        # start position (excluding the endpoint token).
        closest_start = closest[0]
        for pat, canonical, _, _ in _ENDPOINT_VOCAB:
            if canonical != closest[1]:
                continue
            for em in pat.finditer(text):
                if em.end() == closest[0]:
                    closest_start = em.start()
                    break
            if closest_start != closest[0]:
                break
        for c in left_cands[:-1]:
            if c[1] == closest[1]:
                continue  # same canonical = not ambiguous
            between = text[c[0]:closest_start]
            # Different clause? Skip.
            if re.search(r"[.;](?=\s|$)", between):
                continue
            # Already separated by a value? Skip.
            if re.search(r"[-−]?\d", between):
                continue
            # Coordinate connector in same clause + no separator
            # → ambiguous → refuse atom.
            if re.search(r"\band\b|\bor\b|,", between):
                return "", "", ()
        return closest[1], closest[2], closest[3]
    # Fall through to closest on right
    right_cands = sorted(candidates, key=lambda c: c[0])
    _, canonical, primary, tags = right_cands[0]
    return canonical, primary, tags


def _find_arm_local_entity(
    direct_quote: str,
    num_match: re.Match,
) -> str:
    """P1 #3 fix (iter 2): bind entity to the arm phrase nearest the value.

    Strategy: find the FIRST arm phrase (closest to value) in the
    right-side window, whether short-form ("with 15 mg") or full-form
    ("with tirzepatide 15 mg"). For short-form, resolve drug from the
    most-recent drug mention in the left context.

    Critical: must find the CLOSEST arm, not the first full-form arm.
    Earlier iter-2 attempt skipped past "with 15 mg" to find "with
    semaglutide", flipping the arm for the tirzepatide 15 mg dose.
    """
    num_end = num_match.end()
    right_window = direct_quote[num_end:num_end + 80]

    # Combined regex: arm is either FULL_FORM (DRUG optionally + DOSE)
    # or SHORT_FORM (DOSE alone). Take the FIRST match — closest wins.
    # Iter-4 fix: also match "of <DRUG> patients/subjects" — clinical
    # safety pattern "in 45% of tirzepatide patients ... 38% of
    # semaglutide patients" where each value is followed by its arm.
    drug_alt = _DRUG_RE.pattern.removeprefix(r"\b(").removesuffix(r")\b")
    arm_re = re.compile(
        r"\b(?:with|in|for|on|of)\s+"
        r"(?P<arm>"
        # FULL form: drug name with optional dose
        + r"(?:" + drug_alt + r")"
        + r"(?:\s+\d+(?:\.\d+)?\s*(?:mg|μg|mcg|U|IU))?"
        + r"|"
        # SHORT form: dose alone (drug inherited from left context)
        + r"\d+(?:\.\d+)?\s*(?:mg|μg|mcg|U|IU)"
        + r")",
        re.IGNORECASE,
    )
    m = arm_re.search(right_window)
    if not m:
        return ""

    arm_text = m.group("arm").strip()

    # Short-form? First char is a digit. Resolve drug from left context.
    if arm_text and arm_text[0].isdigit():
        left_window = direct_quote[max(0, num_match.start() - 200):num_match.start()]
        prior_drugs = list(_DRUG_RE.finditer(left_window))
        if prior_drugs:
            drug = prior_drugs[-1].group(0).strip()
            return f"{drug} {arm_text.lower()}"
        return arm_text

    return arm_text


def _find_comparator(literal_text: str, entity: str) -> str:
    """Comparator extraction (iter-2 fix per Codex iter-1 P1 #3 review).

    CONSTRAINED to literal_text only — comparator must be in the SAME
    sentence as the value. This prevents "43% adverse events"
    (AE-only sentence) from inheriting "semaglutide" comparator from
    a previous sentence's HbA1c comparison.

    Strategy (3 passes inside literal_text):
        1. Explicit comparator phrase (versus/compared to X) + nearest
           drug after it — strongest signal.
        2. Any non-entity drug in literal_text (multi-arm comparison).
        3. Placebo / standard care literal — if "placebo" / "control"
           appears in literal_text.
    """
    entity_lower = entity.lower().strip()
    entity_drug = re.split(r"\s+\d", entity_lower, maxsplit=1)[0].strip()

    # Iter-3 fix (Codex iter-2 novel-P1): if `entity` appears AFTER a
    # "versus"/"vs"/"compared to" connector, entity IS the comparator arm.
    # Emitting `comparator=<index-drug>` would be a REVERSE COMPARATIVE
    # claim (semaglutide vs tirzepatide, when the sentence is making the
    # opposite claim). Suppress comparator entirely for comparator-arm
    # values.
    for vm in _COMPARATOR_PHRASE_RE.finditer(literal_text):
        after_versus = literal_text[vm.end():vm.end() + 100].lower()
        if entity_drug and entity_drug in after_versus:
            return ""

    # Pass 1: explicit comparator phrase + drug after it
    comp_phrase = _COMPARATOR_PHRASE_RE.search(literal_text)
    if comp_phrase:
        post_comp = literal_text[comp_phrase.end():comp_phrase.end() + 80]
        drug_m = _DRUG_RE.search(post_comp)
        if drug_m:
            d = drug_m.group(0).strip().lower()
            if not (entity_drug and (
                d == entity_drug or d.startswith(entity_drug) or entity_drug.startswith(d)
            )):
                return d
        # Fallback: literal noun after "versus"
        noun_m = re.match(
            r"\s*([A-Za-z][A-Za-z\s\-]{2,30}?)(?=[,;.\s\(]|$|\d)",
            post_comp,
        )
        if noun_m:
            cand = noun_m.group(1).strip().lower()
            if cand and cand not in (entity_drug, entity_lower):
                return cand

    # Pass 2: any non-entity drug in literal_text
    for m in _DRUG_RE.finditer(literal_text):
        d = m.group(0).strip().lower()
        if entity_drug and (
            d == entity_drug or d.startswith(entity_drug) or entity_drug.startswith(d)
        ):
            continue
        return d

    # Pass 3: placebo / standard care
    m = re.search(
        r"\b(placebo|standard\s+care|usual\s+care|control)\b",
        literal_text, re.IGNORECASE,
    )
    if m:
        return m.group(1).lower()
    return ""


def _find_timepoint(direct_quote: str, num_match: re.Match) -> str:
    """Find a timepoint phrase in the sentence containing the value."""
    num_start = num_match.start()
    ctx_start = max(0, num_start - 200)
    ctx_end = min(len(direct_quote), num_match.end() + 100)
    context = direct_quote[ctx_start:ctx_end]
    m = re.search(
        r"\b(?:at|after|by|over|in|through|for)\s+(\d+(?:\.\d+)?)\s*"
        r"(weeks?|months?|years?|days?)\b",
        context, re.IGNORECASE,
    )
    if m:
        return f"{m.group(1)} {m.group(2).lower()}"
    m2 = re.search(r"\b(week|month|year)\s+(\d+)\b", context, re.IGNORECASE)
    if m2:
        return f"{m2.group(1).lower()} {m2.group(2)}"
    return ""


def _expand_literal_text(
    direct_quote: str,
    num_match: re.Match,
) -> tuple[int, int, str]:
    """P1 #4 fix: expand to nearest sentence boundary using DECIMAL-AWARE
    boundary detection. Returns (span_start, span_end, literal_text).

    The boundary is `[.;!?](?=\\s|$|\\n)` — a period followed by
    whitespace or end-of-line. A period followed by a digit (decimal
    like 8.21) is NOT a boundary.
    """
    num_start, num_end = num_match.start(), num_match.end()
    n = len(direct_quote)

    # Walk LEFT looking for a sentence-ending boundary
    left_text = direct_quote[:num_start]
    boundary_left = 0
    for m in _SENTENCE_BOUNDARY_RE.finditer(left_text):
        boundary_left = m.end()  # Last boundary BEFORE the number wins

    # Walk RIGHT looking for the next sentence-ending boundary
    right_text = direct_quote[num_end:]
    m_right = _SENTENCE_BOUNDARY_RE.search(right_text)
    if m_right:
        boundary_right = num_end + m_right.end()
    else:
        boundary_right = n

    lit = direct_quote[boundary_left:boundary_right].strip()
    return boundary_left, boundary_right, lit


def _score_confidence(
    *,
    has_endpoint: bool,
    has_entity: bool,
    has_unit: bool,
    has_comparator: bool,
    has_timepoint: bool,
) -> str:
    """Recalibrated per Codex iter-1 P2:
    HIGH = endpoint + entity + unit + (comparator OR timepoint)
    MEDIUM = endpoint + entity + unit
    LOW = endpoint + value (everything else)
    """
    if has_endpoint and has_entity and has_unit and (has_comparator or has_timepoint):
        return "high"
    if has_endpoint and has_entity and has_unit:
        return "medium"
    return "low"


def _compute_section_tags(
    primary: str,
    secondary: tuple[str, ...],
    *,
    has_comparator: bool,
    has_dose_arm: bool,
) -> tuple[str, ...]:
    """Codex iter-1 P2 fix: section_tags are dynamic — add Comparative
    when a comparator is present, add Dose Response when a dose-arm
    is bound to the entity."""
    tags = set(secondary)
    tags.add(primary)
    if has_comparator:
        tags.add("Comparative")
    if has_dose_arm:
        tags.add("Dose Response")
    # Order: primary first, then alphabetical
    ordered = [primary] + sorted(t for t in tags if t != primary)
    return tuple(ordered)


def _compute_primary_section(
    vocab_primary: str,
    *,
    has_comparator: bool,
    has_dose_arm: bool,
) -> str:
    """Iter-4 fix (Codex iter-3 P2 ranking):

    Hierarchy (iter-4):
      1. has_dose_arm → "Dose Response" (always, regardless of comparator)
      2. has_comparator AND vocab_primary in {"Efficacy",
         "Comparative Effectiveness"} → "Comparative Effectiveness"
      3. otherwise → vocab_primary

    Per Codex iter-3: dose-arm WITHOUT comparator should still primary
    to Dose Response (dose-arm IS the dose-response signal). Comparator
    should NOT automatically move Safety/Mechanism atoms out of their
    vocab primary section — only Efficacy/Comparative atoms get
    re-routed.
    """
    if has_dose_arm:
        return "Dose Response"
    if has_comparator and vocab_primary in ("Efficacy", "Comparative Effectiveness"):
        return "Comparative Effectiveness"
    return vocab_primary


# ---------------------------------------------------------------------------
# Main extraction
# ---------------------------------------------------------------------------

def extract_atoms_from_evidence(
    evidence_row: dict[str, Any],
    atom_id_start: int = 0,
) -> list[ClaimAtom]:
    """Extract ClaimAtoms from one evidence row's `direct_quote`.

    Strategy (Codex iter-1-aware):
        1. Walk every numeric anchor.
        2. Classify each as OUTCOME / DOSE / TIMEPOINT / SAMPLE_SIZE /
           CI_BOUND / CI_LEVEL / P_VALUE / UNKNOWN.
        3. ONLY OUTCOME numbers become atoms.
        4. For each OUTCOME, look in the SAME SENTENCE for endpoint.
           If no endpoint → skip.
        5. Bind entity from the closest arm phrase ("with X" or "X mg").
        6. Bind comparator from explicit "versus" syntax.
        7. Expand literal_text with decimal-aware sentence boundaries.
        8. Validate literal_text contains the raw value text.
    """
    direct_quote = evidence_row.get("direct_quote") or ""
    if not direct_quote:
        return []

    ev_id = evidence_row.get("evidence_id", "")
    tier = str(evidence_row.get("tier", ""))
    provenance_class = str(evidence_row.get("provenance_class", ""))
    paper_title = (
        evidence_row.get("title")
        or evidence_row.get("statement", "")[:120]
        or ""
    )

    atoms: list[ClaimAtom] = []
    counter = atom_id_start

    # I-gen-005 Step 3k (Codex APPROVE_DESIGN iter-1): per-cell atoms
    # from markdown safety-table rows. Fires BEFORE the per-number walk
    # so per-cell atoms get earlier IDs. The per-number walk is
    # SUPPRESSED for numbers within detected table rows (Codex Step 3k
    # diff iter-1 P1 #2: legacy walk emits misleading atoms with wrong
    # entity/unit binding for table cells).
    safety_table_rows = _iter_safety_table_rows(direct_quote)
    # Codex Step 3k diff iter-4 P1: drop the broad _detect_all_table_regions
    # suppression — it was breaking legacy walk on non-safety tables
    # (efficacy, mechanism, etc.). Suppress ONLY within rows matched by
    # the safety vocab (whether or not they pass the emit-worthy cell
    # threshold). Descriptor rows ("≥0.2% of patients...") that match
    # safety vocab are still in safety_table_rows for suppression,
    # but don't emit atoms because cell count < 2.
    table_row_ranges: list[tuple[int, int]] = []
    for endpoint_canonical, row_text, raw_endpoint_text, row_start in safety_table_rows:
        row_end = row_start + len(row_text)
        table_row_ranges.append((row_start, row_end))
        # Locate the endpoint header within the row to know where
        # row-data begins (skip header value if any).
        hdr_m = re.search(
            re.escape(raw_endpoint_text), row_text, re.IGNORECASE
        )
        header_end = hdr_m.end() if hdr_m else 0
        cells = _extract_cell_percentages(row_text, header_end)
        # Codex Step 3k diff iter-3 P2: lowered from 3 to 2. Two-arm
        # placebo-controlled trial tables have legitimate rows with only
        # 2 percentage cells. Descriptor rows with embedded threshold
        # values (e.g., "≥0.2% to ≥5%") would have 2 percentages but
        # those rows are filtered upstream by the all-table-regions
        # legacy-walk suppression + the `||||||||` empty-cells boundary.
        if len(cells) < 2:
            continue
        # Trial-name fallback for entity (column-to-arm mapping DEFER
        # per Codex P2 #4).
        trial_m = _TRIAL_RE.search(direct_quote)
        entity = trial_m.group(0).strip() if trial_m else (
            evidence_row.get("statement", "")[:60] or "table"
        )
        # Canonicalize endpoint via vocab.
        endpoint_canon = _canonicalize_safety_endpoint(endpoint_canonical)
        for value_float, start, end, raw_text in cells:
            value_str = f"{value_float:g}"
            # Per-cell span offsets in direct_quote, per Codex Step 3k
            # diff iter-1 P2 #3: ClaimAtom contract requires real
            # direct_quote offsets, not row-relative.
            cell_span_start = row_start + start
            cell_span_end = row_start + end
            counter += 1
            atoms.append(ClaimAtom(
                atom_id=f"atom_{counter:03d}",
                evidence_id=ev_id,
                span_start=cell_span_start,
                span_end=cell_span_end,
                literal_text=row_text,
                entity=entity,
                endpoint=endpoint_canon,
                comparator="",
                timepoint="",
                value=value_str,
                unit="%",
                primary_section="Safety",
                section_tags=("Safety",),
                tier=tier,
                value_signed=False,
                # Codex Step 3k diff iter-1 P2 #4: ClaimAtom contract is
                # "high"|"medium"|"low" — was incorrectly set to 0.7.
                confidence="medium",
                provenance_class=provenance_class,
                source_paper_title=paper_title,
            ))

    def _in_table_row(pos: int) -> bool:
        """Codex Step 3k diff iter-1 P1 #2 suppression: skip per-number
        walk for numbers inside detected table rows. The legacy walk
        produces wrong entity/unit bindings for table cells; the
        table-row path emits the correct per-cell atoms above."""
        for s, e in table_row_ranges:
            if s <= pos < e:
                return True
        return False

    for m in _NUMBER_ATOM_RE.finditer(direct_quote):
        raw_value = m.group("value").strip()

        # Codex Step 3k diff iter-1 P1 #2: skip numbers inside detected
        # safety-table rows. The legacy walk produces wrong bindings.
        if _in_table_row(m.start()):
            continue

        # P1 #4 fix: decimal-aware literal_text expansion (FIRST so the
        # sentence boundaries are known before classification).
        span_start, span_end, literal_text = _expand_literal_text(direct_quote, m)

        # SAFETY FLOOR: literal_text MUST contain the raw value verbatim.
        if raw_value not in literal_text:
            continue

        # Codex Step 3k diff iter-4 P1 hardening: if the literal_text
        # is dominated by pipe-delimited table content (>=3 pipes), the
        # number is in a table context — let the table-row path handle
        # it (or skip silently if it's a descriptor row not covered by
        # the table-row detector). Avoids "≥0.2%" / "≥5%" descriptor
        # leaks while preserving prose-table mixed evidence.
        if literal_text.count("|") >= 3:
            continue

        # P1 #2 fix: classify before atom creation. Pass sentence_start
        # so unit-inheritance can search within the SAME sentence only.
        role, unit = _classify_number(direct_quote, m, sentence_start=span_start)
        if role != NumberRole.OUTCOME:
            continue

        # Find endpoint within the literal sentence.
        # Iter-3 fix: pass num offset (relative to literal_text) so the
        # CLOSEST endpoint to the value wins, not the first endpoint in
        # the sentence. Prevents multi-endpoint binding errors.
        num_offset_in_literal = m.start() - span_start
        endpoint, primary_section, secondary_tags = _find_endpoint(
            literal_text, num_offset=num_offset_in_literal
        )
        if not endpoint:
            continue

        # P1 #3 fix: arm-local entity binding.
        entity = _find_arm_local_entity(direct_quote, m)
        if not entity:
            # Iter-4 fix (Codex iter-3 continuing-P1): pick CLOSEST drug
            # to the value (preferring left side), not first drug in
            # literal_text. Handles "semaglutide, which reduced HbA1c
            # by -1.86" where the comparator-arm drug is left of value.
            #
            # Also iter-4 dose-arm fix: capture "<DRUG> N mg" as a single
            # entity so has_dose_arm=True. Critical for single-arm dose
            # studies where the dose is on the LEFT not right of value.
            num_offset_in_literal = m.start() - span_start
            drug_with_dose_re = re.compile(
                rf"({_DRUG_RE.pattern.removeprefix(chr(92) + 'b(').removesuffix(')' + chr(92) + 'b')})"
                r"(?:\s+\d+(?:\.\d+)?\s*(?:mg|μg|mcg|U|IU))?",
                re.IGNORECASE,
            )
            drug_candidates = list(drug_with_dose_re.finditer(literal_text))
            left_drugs = [d for d in drug_candidates if d.end() <= num_offset_in_literal]
            if left_drugs:
                # Closest on left = max end-position
                closest = max(left_drugs, key=lambda d: d.end())
                entity = closest.group(0).strip()
            elif drug_candidates:
                # No drug on left → take closest on right
                closest = min(drug_candidates, key=lambda d: d.start())
                entity = closest.group(0).strip()
            else:
                trial_m = _TRIAL_RE.search(literal_text)
                if trial_m:
                    entity = trial_m.group(0).strip()

        # Comparator constrained to literal_text (iter-2 fix).
        comparator = _find_comparator(literal_text, entity)
        timepoint = _find_timepoint(direct_quote, m)

        # Dose-arm detection: entity contains a dose unit
        has_dose_arm = bool(re.search(r"\d+\s*(?:mg|μg|mcg|U|IU)", entity))

        value_signed = raw_value.startswith("-") or raw_value.startswith("−")
        norm_value = raw_value.replace("−", "-")

        confidence = _score_confidence(
            has_endpoint=bool(endpoint),
            has_entity=bool(entity),
            has_unit=bool(unit),
            has_comparator=bool(comparator),
            has_timepoint=bool(timepoint),
        )

        # Iter-3 fix (Codex iter-2 P2): primary_section is dynamic, not
        # static vocab default. Dose-arm + comparator HbA1c atom goes to
        # "Dose Response", not "Efficacy". Prevents 3-section reuse.
        # Iter-4 fix (Codex iter-3 P3): compute primary_section BEFORE
        # section_tags so the tuple order reflects the rewritten primary.
        primary_section = _compute_primary_section(
            primary_section,
            has_comparator=bool(comparator),
            has_dose_arm=has_dose_arm,
        )
        section_tags = _compute_section_tags(
            primary_section, secondary_tags,
            has_comparator=bool(comparator),
            has_dose_arm=has_dose_arm,
        )

        counter += 1
        atoms.append(ClaimAtom(
            atom_id=f"atom_{counter:03d}",
            evidence_id=ev_id,
            span_start=span_start,
            span_end=span_end,
            literal_text=literal_text,
            entity=entity,
            endpoint=endpoint,
            comparator=comparator,
            timepoint=timepoint,
            value=norm_value,
            unit=unit,
            primary_section=primary_section,
            section_tags=section_tags,
            tier=tier,
            value_signed=value_signed,
            confidence=confidence,
            provenance_class=provenance_class,
            source_paper_title=paper_title,
        ))
    return atoms


def build_atom_catalog(
    evidence_subset: list[dict[str, Any]],
) -> dict[str, ClaimAtom]:
    """Build the complete atom catalog from a section's evidence subset.

    Atoms numbered globally across the query.
    """
    catalog: dict[str, ClaimAtom] = {}
    counter = 0
    for ev in evidence_subset:
        atoms = extract_atoms_from_evidence(ev, atom_id_start=counter)
        for a in atoms:
            catalog[a.atom_id] = a
        counter += len(atoms)
    return catalog


def filter_atoms_for_section(
    catalog: dict[str, ClaimAtom],
    section_title: str,
) -> dict[str, ClaimAtom]:
    """Filter atoms for a section.

    Iter-3 fix (Codex iter-2 P2): single-best-placement enforcement.
    Returns atoms whose `primary_section` matches the section title.
    Atoms with this section in `section_tags` but NOT as primary are
    excluded — they are cited in their primary section and should not be
    re-cited here. This prevents the same atom from landing in 3
    different sections of the report.

    Case-insensitive match. Section-name variants are normalized:
    "Comparative" ≡ "Comparative Effectiveness".
    """
    sec = section_title.strip().lower()
    # Section-name normalization for matching
    sec_aliases = {
        "comparative": "comparative effectiveness",
        "comparative effectiveness": "comparative effectiveness",
    }
    sec_normalized = sec_aliases.get(sec, sec)

    def matches(primary: str) -> bool:
        p = primary.strip().lower()
        p_normalized = sec_aliases.get(p, p)
        return p_normalized == sec_normalized

    return {
        aid: a
        for aid, a in catalog.items()
        if matches(a.primary_section)
    }


def format_atom_catalog_for_prompt(
    section_atoms: dict[str, ClaimAtom],
    *,
    max_atoms: int = 60,
) -> str:
    """Render the section-filtered atom catalog as a compact block for
    V4 Pro's system prompt."""
    if not section_atoms:
        return "ATOM CATALOG: (empty — no verified atoms for this section's focus)"

    lines = ["ATOM CATALOG (cite atom_ids in your prose; one per factual claim):"]
    for i, (aid, a) in enumerate(sorted(section_atoms.items())):
        if i >= max_atoms:
            lines.append(f"  ... ({len(section_atoms) - max_atoms} more atoms truncated)")
            break
        parts = [f"  {aid}: ev={a.evidence_id} tier={a.tier} conf={a.confidence}"]
        parts.append(f"value={a.value}{(' ' + a.unit) if a.unit else ''}")
        if a.entity:
            parts.append(f"entity={a.entity}")
        parts.append(f"endpoint={a.endpoint}")
        if a.comparator:
            parts.append(f"vs={a.comparator}")
        if a.timepoint:
            parts.append(f"timepoint={a.timepoint}")
        lines.append(" | ".join(parts))
        lit = a.literal_text[:200].replace("\n", " ")
        lines.append(f"    > {lit}")
    return "\n".join(lines)


def format_refusal_for_missing_atom(
    *,
    endpoint: str,
    entity: str = "",
    timepoint: str = "",
) -> str:
    """Codex APPROVE_DESIGN refusal template:

        Insufficient verified atom-level evidence from the cited corpus
        to support a claim about {endpoint} {timepoint_clause} for
        {entity_clause}.
    """
    timepoint_clause = f"at {timepoint}" if timepoint else ""
    entity_clause = entity if entity else "the cited population"
    return (
        f"Insufficient verified atom-level evidence from the cited corpus "
        f"to support a claim about {endpoint} {timepoint_clause} "
        f"for {entity_clause}."
    ).replace("  ", " ").strip()
