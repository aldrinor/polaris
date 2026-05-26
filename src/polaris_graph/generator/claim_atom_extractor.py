"""I-gen-005 atom-first architecture: extract STRUCTURED claim atoms
from evidence direct_quotes.

Per Codex strategy verdict 2026-05-26 (`codex_quality_strategy_verdict.txt`)
recommended_path #2 + design verdict APPROVE_DESIGN 2026-05-26.

Why this module exists:
    The current architecture lets V4 Pro write open prose, then catches
    fabrications post-hoc via strict_verify. Codex's read: that's
    backwards. The fix is to PRE-EXTRACT verifiable facts (atoms) from
    cited evidence spans BEFORE generation, then constrain V4 Pro to
    cite atom_ids that map to fixed spans. V4 Pro becomes the
    rhetorical/synthesis layer, not the fact source.

This is the long-run architecture in microcosm. The existing
`evidence_value_extractor.py` extracts flat number/trial/drug tokens
per evidence row; this module emits richer ClaimAtom records with
endpoint/comparator/timepoint metadata, exact span offsets, and
section relevance tags.

Per Codex APPROVE_DESIGN:
    - Pure-Python regex (Option D: regex now, LLM later)
    - 13 fields per atom (9 from Codex's recommended_path + 4 additions
      I proposed: value_signed, confidence, provenance_class,
      source_paper_title)
    - Numerical atom_id format ("atom_001", ...)
    - Section-relevance filter for prompt injection
    - Narrative sentences allowed WITH_LIMITS (non-claim transitions
      only; factual claims MUST cite an atom)

This module is INTENTIONALLY pure-Python regex — no LLM call. Fast,
deterministic, reproducible. Atoms come from actual evidence text;
nothing fabricated here.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Optional


# ---------------------------------------------------------------------------
# ClaimAtom — the structured record V4 Pro will cite from
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ClaimAtom:
    """A single verifiable claim extracted from an evidence span.

    Frozen because atom_id resolution depends on stable identity through
    the pipeline.
    """

    # Identity + provenance (from Codex's recommended_path #2):
    atom_id: str            # "atom_001"
    evidence_id: str        # "ev_017"
    span_start: int         # offset in direct_quote where the atom is grounded
    span_end: int           # offset in direct_quote (exclusive)
    literal_text: str       # verbatim text from the span supporting this claim

    # Semantic fields (Codex's recommended_path #2):
    entity: str             # "tirzepatide" / "SURPASS-2" / "apixaban"
    endpoint: str           # "HbA1c" / "body weight" / "stroke"
    comparator: str         # "placebo" / "semaglutide" / "" if none
    timepoint: str          # "week 40" / "72 weeks" / "" if none
    value: str              # "-2.30" / "82-86" / "1.93"
    unit: str               # "percentage points" / "kg" / "%" / ""

    # Routing (Codex's recommended_path #2):
    section_tags: tuple[str, ...]  # ("Efficacy", "Comparative")
    tier: str                       # "T1" / "T2" / ...

    # Codex APPROVE_DESIGN additions:
    value_signed: bool              # True if the value is negative
    confidence: str                 # "high" | "medium" | "low"
    provenance_class: str           # "abstract_only" | "open_access" | ...
    source_paper_title: str         # for refusal disclosure


# ---------------------------------------------------------------------------
# Clinical vocabulary maps
# ---------------------------------------------------------------------------

# Each endpoint maps to (a) its regex pattern (with optional aliases),
# (b) the canonical name to emit in the atom, (c) the section tags
# that endpoint belongs to. Section tags are LIST because some endpoints
# belong to multiple sections (HbA1c reduction is Efficacy AND
# Comparative when a comparator is present).
#
# Pattern uses non-capturing groups so finditer.group(0) returns the
# matched canonical text.
_ENDPOINT_VOCAB: list[tuple[re.Pattern, str, tuple[str, ...]]] = [
    # Glycemic
    (re.compile(r"\b(?:HbA1c|HbA1C|glycated\s+hemoglobin|A1C)\b", re.IGNORECASE),
     "HbA1c", ("Efficacy", "Comparative", "Dose Response")),
    (re.compile(r"\b(?:FPG|fasting\s+plasma\s+glucose|fasting\s+serum\s+glucose|FSG)\b", re.IGNORECASE),
     "fasting glucose", ("Efficacy", "Comparative")),
    (re.compile(r"\bnormoglycemi[ac]\b|\bHbA1c\s*<\s*5\.7", re.IGNORECASE),
     "normoglycemia (HbA1c<5.7%)", ("Efficacy", "Comparative")),

    # Weight
    (re.compile(r"\b(?:body\s+weight|weight\s+loss|weight\s+reduction|BMI|kg\s+loss)\b", re.IGNORECASE),
     "body weight", ("Efficacy", "Comparative", "Dose Response")),

    # Cardiovascular
    (re.compile(r"\bMACE\b|major\s+adverse\s+cardiovascular\s+events?", re.IGNORECASE),
     "MACE", ("Efficacy", "Safety", "Comparative")),
    (re.compile(r"\b(?:cardiovascular|CV)\s+death", re.IGNORECASE),
     "cardiovascular death", ("Efficacy", "Safety")),
    (re.compile(r"\bstroke\b|\bischemic\s+stroke\b", re.IGNORECASE),
     "stroke", ("Efficacy", "Safety", "Comparative")),
    (re.compile(r"\bmyocardial\s+infarction|\bMI\b", re.IGNORECASE),
     "myocardial infarction", ("Efficacy", "Safety")),

    # Blood pressure
    (re.compile(r"\bsystolic\s+blood\s+pressure|\bsystolic\s+BP\b|\bSBP\b", re.IGNORECASE),
     "systolic BP", ("Efficacy", "Comparative")),
    (re.compile(r"\bdiastolic\s+blood\s+pressure|\bdiastolic\s+BP\b|\bDBP\b", re.IGNORECASE),
     "diastolic BP", ("Efficacy", "Comparative")),
    (re.compile(r"\bblood\s+pressure\b(?!\s*(?:profile))", re.IGNORECASE),
     "blood pressure", ("Efficacy", "Comparative")),

    # Lipids
    (re.compile(r"\b(?:LDL[-\s]?C|low[-\s]density\s+lipoprotein)", re.IGNORECASE),
     "LDL-C", ("Efficacy", "Comparative")),
    (re.compile(r"\btriglycerides?\b", re.IGNORECASE),
     "triglycerides", ("Efficacy", "Comparative")),
    (re.compile(r"\b(?:HDL[-\s]?C|high[-\s]density\s+lipoprotein)", re.IGNORECASE),
     "HDL-C", ("Efficacy", "Comparative")),

    # Safety
    (re.compile(r"\b(?:adverse\s+events?|AE)\b", re.IGNORECASE),
     "adverse events", ("Safety",)),
    (re.compile(r"\bserious\s+adverse\s+events?|\bSAE\b", re.IGNORECASE),
     "serious adverse events", ("Safety",)),
    (re.compile(r"\b(?:discontinuation|discontinued)\b", re.IGNORECASE),
     "discontinuation", ("Safety", "Dose Response")),
    (re.compile(r"\bnausea\b", re.IGNORECASE), "nausea", ("Safety",)),
    (re.compile(r"\bvomiting\b", re.IGNORECASE), "vomiting", ("Safety",)),
    (re.compile(r"\bdiarr?h[oe]a\b", re.IGNORECASE), "diarrhea", ("Safety",)),
    (re.compile(r"\babdominal\s+pain\b", re.IGNORECASE), "abdominal pain", ("Safety",)),
    (re.compile(r"\b(?:gastrointestinal|GI)\s+(?:adverse|events?)", re.IGNORECASE),
     "GI events", ("Safety",)),
    (re.compile(r"\bhypoglycem(?:ia|ic)\b", re.IGNORECASE),
     "hypoglycemia", ("Safety", "Comparative")),
    (re.compile(r"\bpancreatitis\b", re.IGNORECASE),
     "pancreatitis", ("Safety",)),
    (re.compile(r"\b(?:intracranial\s+hemorrhage|ICH)\b", re.IGNORECASE),
     "intracranial hemorrhage", ("Safety", "Comparative")),
    (re.compile(r"\bGI\s+bleeding|gastrointestinal\s+bleeding", re.IGNORECASE),
     "GI bleeding", ("Safety", "Comparative")),
    (re.compile(r"\bmajor\s+bleeding\b", re.IGNORECASE),
     "major bleeding", ("Safety", "Comparative")),
    (re.compile(r"\bC[-\s]?cell\b|\bthyroid\s+(?:carcinoma|cancer)\b", re.IGNORECASE),
     "thyroid C-cell signal", ("Safety",)),

    # Treatment differences (Efficacy + Comparative)
    (re.compile(r"\bestimated\s+treatment\s+difference|\bETD\b", re.IGNORECASE),
     "estimated treatment difference", ("Efficacy", "Comparative")),
    (re.compile(r"\btreatment\s+difference\b", re.IGNORECASE),
     "treatment difference", ("Efficacy", "Comparative")),

    # Mechanism
    (re.compile(r"\bhalf[-\s]?life\b", re.IGNORECASE),
     "half-life", ("Mechanism",)),
    (re.compile(r"\bbioavailability\b", re.IGNORECASE),
     "bioavailability", ("Mechanism",)),
    (re.compile(r"\b(?:Tmax|tmax|T_max)\b"),
     "Tmax", ("Mechanism",)),
    (re.compile(r"\bM[-\s]?value\b", re.IGNORECASE),
     "M-value", ("Mechanism",)),
    (re.compile(r"\b(?:hyperinsulinemic[-\s]?euglycemic\s+clamp|HE\s+clamp)\b", re.IGNORECASE),
     "HE clamp", ("Mechanism",)),
    (re.compile(r"\b(?:receptor\s+(?:affinity|binding|selectivity))\b", re.IGNORECASE),
     "receptor binding", ("Mechanism",)),
    (re.compile(r"\b(?:GIP|GLP[-\s]?1)\s+receptor\b", re.IGNORECASE),
     "incretin receptor activity", ("Mechanism",)),

    # Trial design / population
    (re.compile(r"\b(?:sample\s+size|N\s*=\s*\d+|n\s*=\s*\d+|enrolled\s+\d+)\b", re.IGNORECASE),
     "sample size", ("Efficacy", "Safety", "Comparative", "Dose Response")),
    (re.compile(r"\bbaseline\b(?!\s+(?:value|of))", re.IGNORECASE),
     "baseline value", ("Efficacy", "Comparative")),
]

# Comparator vocabulary — extracted from "vs/versus/compared to X" patterns.
_COMPARATOR_LEAD_RE = re.compile(
    r"\b(?:vs\.?|versus|compared\s+(?:to|with)|relative\s+to|against)\s+"
    r"([A-Za-z][A-Za-z\s\-]{1,40}?)"
    r"(?=[,;.\s\(]|$|\d|in\s+|at\s+)",
    re.IGNORECASE,
)

# Timepoint patterns: "at week N", "after N weeks", "by N months", etc.
_TIMEPOINT_RE = re.compile(
    r"\b(?:at|after|by|over|in|through)\s+"
    r"(\d+(?:\.\d+)?)\s*"
    r"(weeks?|months?|years?|days?)\b",
    re.IGNORECASE,
)
# Alternate: "week 40", "month 6"
_TIMEPOINT_NAMED_RE = re.compile(
    r"\b(week|month|year|day)\s+(\d+)\b",
    re.IGNORECASE,
)

# Unit patterns (associated with a number)
_UNIT_TOKEN_RE = re.compile(
    r"(?P<unit>%|"
    r"percentage\s+points?|pp|"
    r"mg|kg|g|mL|L|μg|mcg|IU|U|"
    r"mmol/L|mg/dL|"
    r"weeks?|months?|years?|days?|hours?|min(?:utes?)?|"
    r"kg/m\^?2|kg\.m-2|"
    r"per\s+1000|per\s+100|"
    r"BPM|bpm|mmHg)\b",
    re.IGNORECASE,
)

# Number pattern (matches values that can serve as atom anchors).
# Allows decimals, ranges (`7.25-10.36`), and signed numbers. Avoids
# matching inside identifier-like sequences.
_NUMBER_ATOM_RE = re.compile(
    r"(?<![A-Za-z0-9_.])"
    r"(?P<value>"
    r"[-−]?\d+(?:[.,]\d+)?"
    r"(?:\s*[-–—]\s*[-−]?\d+(?:[.,]\d+)?)?"  # optional range form
    r")"
    r"(?![A-Za-z0-9_])"
)

# Entity vocabulary (drug names + trial names). Reuses
# evidence_value_extractor patterns but kept local so this module is
# self-contained.
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
    r"|ARISTOTLE|RE[-\s]?LY|ROCKET[-\s]?AF|ENGAGE[-\s]?AF|"
    r"|AVERROES|RELY-?ABLE"
    r"|TIDE|TARGET|SOUL"
    r"|VERTIS-?(?:CV)?"
    r")\b",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Extraction
# ---------------------------------------------------------------------------

# Context window (chars before+after the number) to scan for endpoint /
# comparator / timepoint / unit when building one atom around a number.
_CONTEXT_BEFORE = 120
_CONTEXT_AFTER = 80


def _extract_unit_near(text: str) -> str:
    """Return the FIRST unit token found in `text`, lowercased and
    normalized. Empty string if none."""
    m = _UNIT_TOKEN_RE.search(text)
    if not m:
        return ""
    raw = m.group("unit").lower().strip()
    # Normalize percentage-points variants
    if raw in ("pp", "percentage point", "percentage points"):
        return "percentage points"
    return raw


def _extract_endpoint_near(
    text: str,
) -> tuple[str, tuple[str, ...]]:
    """Return (canonical_endpoint_name, section_tags) for the FIRST
    endpoint pattern that matches in `text`, or ("", ()) if none."""
    for pat, canonical, tags in _ENDPOINT_VOCAB:
        if pat.search(text):
            return canonical, tags
    return "", ()


def _extract_comparator_near(text: str, entity: str = "") -> str:
    """Return the comparator drug found in `text`.

    Strategy (iter 2 fix per pytest failure):
        Clinical text often writes "versus -1.86 with semaglutide" where
        the comparator drug name follows the comparison value (not
        directly after "versus"). Regex-on-"versus" is brittle; the
        better approach is: find ALL drugs in the local context, and
        return the FIRST drug that is NOT the entity. The entity is the
        drug the claim is ABOUT; the comparator is the other drug.

    Fallback: if no drug-vs-drug pattern, use the legacy regex which
    catches "vs placebo", "vs standard care", etc.
    """
    entity_norm = entity.lower().strip()
    # Pass 1: any drug name not matching entity
    for m in _DRUG_RE.finditer(text):
        d = m.group(0).lower().strip()
        if entity_norm:
            # Skip if this drug is the entity (allow partial-match dedup
            # e.g., "tirzepatide" == "tirzepatide 15 mg")
            if d == entity_norm or entity_norm.startswith(d) or d.startswith(entity_norm):
                continue
        return d
    # Pass 2: legacy "vs X" / "compared to Y" regex
    m = _COMPARATOR_LEAD_RE.search(text)
    if not m:
        return ""
    raw = m.group(1).strip().lower()
    for trailing in (" group", " arm", " patients", " participants"):
        if raw.endswith(trailing):
            raw = raw[: -len(trailing)]
    return raw.strip()


def _extract_timepoint_near(text: str) -> str:
    """Return the first timepoint phrase found in `text`."""
    m = _TIMEPOINT_RE.search(text)
    if m:
        n, unit = m.group(1), m.group(2)
        return f"{n} {unit.lower()}"
    m2 = _TIMEPOINT_NAMED_RE.search(text)
    if m2:
        unit, n = m2.group(1).lower(), m2.group(2)
        return f"{unit} {n}"
    return ""


def _entity_for_evidence(evidence_row: dict[str, Any], context: str) -> str:
    """Determine the entity (drug / trial) this atom is about. Prefers
    the explicit drug found in the local context; falls back to drug
    found in the paper title; final fallback to first trial mention."""
    drug_in_ctx = _DRUG_RE.search(context)
    if drug_in_ctx:
        return drug_in_ctx.group(0).strip()
    title = evidence_row.get("statement") or evidence_row.get("title") or ""
    drug_in_title = _DRUG_RE.search(title)
    if drug_in_title:
        return drug_in_title.group(0).strip()
    trial_in_ctx = _TRIAL_RE.search(context)
    if trial_in_ctx:
        return trial_in_ctx.group(0).strip()
    trial_in_title = _TRIAL_RE.search(title)
    if trial_in_title:
        return trial_in_title.group(0).strip()
    return ""


def _score_confidence(
    has_endpoint: bool,
    has_comparator: bool,
    has_timepoint: bool,
    has_unit: bool,
    has_entity: bool,
) -> str:
    """Confidence = function of how many fields were extracted."""
    score = sum([has_endpoint, has_comparator, has_timepoint, has_unit, has_entity])
    if score >= 4:
        return "high"
    if score >= 2:
        return "medium"
    return "low"


def extract_atoms_from_evidence(
    evidence_row: dict[str, Any],
    atom_id_start: int = 0,
) -> list[ClaimAtom]:
    """Extract ClaimAtoms from one evidence row's `direct_quote`.

    Strategy:
        Walk every numeric anchor in direct_quote. For each, examine a
        context window (CONTEXT_BEFORE chars before + CONTEXT_AFTER
        after) to extract endpoint / comparator / timepoint / unit. If
        no endpoint is found, the number is dropped (it's not a
        verifiable clinical claim — could be sample size on its own,
        but we skip to avoid noise).

    Args:
        evidence_row: dict with keys evidence_id, direct_quote, tier,
            statement/title, provenance_class
        atom_id_start: starting index for atom_id generation (atoms are
            numbered globally per query, not per evidence)

    Returns:
        list of ClaimAtom in evidence-document order.
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
    atom_counter = atom_id_start
    n = len(direct_quote)

    for m in _NUMBER_ATOM_RE.finditer(direct_quote):
        raw_value = m.group("value").strip()
        # Skip pure-integer single-digit "0"/"1"/etc. as standalone
        # noise (no clinical meaning without context).
        if raw_value.lstrip("-−") in {"0", "1", "2", "3", "4", "5", "6", "7", "8", "9"}:
            # Allow only if context strongly suggests a real claim
            # (e.g., "1 mg" with unit). Detect via unit immediately after.
            tail = direct_quote[m.end():m.end() + 8]
            if not _UNIT_TOKEN_RE.match(tail.lstrip()):
                continue

        num_start, num_end = m.start(), m.end()
        ctx_start = max(0, num_start - _CONTEXT_BEFORE)
        ctx_end = min(n, num_end + _CONTEXT_AFTER)
        context = direct_quote[ctx_start:ctx_end]
        right_context = direct_quote[num_end:ctx_end]

        endpoint, section_tags = _extract_endpoint_near(context)
        if not endpoint:
            # No endpoint = no verifiable clinical claim.
            continue

        timepoint = _extract_timepoint_near(context)
        unit = _extract_unit_near(right_context) or _extract_unit_near(context)
        entity = _entity_for_evidence(evidence_row, context)
        comparator = _extract_comparator_near(context, entity=entity)

        # value_signed: number starts with - or unicode minus
        value_signed = raw_value.startswith("-") or raw_value.startswith("−")
        # Normalize unicode minus to ASCII for the stored value
        norm_value = raw_value.replace("−", "-")

        confidence = _score_confidence(
            has_endpoint=bool(endpoint),
            has_comparator=bool(comparator),
            has_timepoint=bool(timepoint),
            has_unit=bool(unit),
            has_entity=bool(entity),
        )

        # Literal text = expand to nearest sentence boundary in the
        # context window so the verifier can see the full clinical claim.
        lit_start = ctx_start
        lit_end = ctx_end
        # Find nearest preceding sentence boundary
        for i in range(num_start - 1, max(ctx_start - 1, -1), -1):
            if direct_quote[i] in ".;\n":
                lit_start = i + 1
                break
        # Find nearest following sentence boundary
        for i in range(num_end, min(ctx_end + 60, n)):
            if direct_quote[i] in ".;\n":
                lit_end = i + 1
                break
        literal_text = direct_quote[lit_start:lit_end].strip()

        atom_counter += 1
        atoms.append(ClaimAtom(
            atom_id=f"atom_{atom_counter:03d}",
            evidence_id=ev_id,
            span_start=lit_start,
            span_end=lit_end,
            literal_text=literal_text,
            entity=entity,
            endpoint=endpoint,
            comparator=comparator,
            timepoint=timepoint,
            value=norm_value,
            unit=unit,
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

    Atoms are numbered globally across the query (atom_001 in ev_001's
    quote, atom_002 next, etc.) so atom_id is stable across sections.

    Returns:
        dict[atom_id, ClaimAtom]
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
    """Filter to atoms whose section_tags include this section.

    Section title is matched case-insensitively against the
    section_tags tuple.
    """
    sec = section_title.strip()
    return {
        aid: a
        for aid, a in catalog.items()
        if any(s.lower() == sec.lower() for s in a.section_tags)
    }


def format_atom_catalog_for_prompt(
    section_atoms: dict[str, ClaimAtom],
    *,
    max_atoms: int = 60,
) -> str:
    """Render the section-filtered atom catalog as a structured block
    for V4 Pro's system prompt.

    Schema is compact JSON-ish per row; V4 Pro learns to read it
    line-by-line. The prompt-side rule is: cite atom_ids, not raw
    [ev_XXX]; if no atom supports your claim, refuse or weaken the
    sentence to non-factual.
    """
    if not section_atoms:
        return "ATOM CATALOG: (empty — no verified atoms for this section's focus)"

    lines = ["ATOM CATALOG (cite atom_ids in your prose; one per factual claim):"]
    for i, (aid, a) in enumerate(sorted(section_atoms.items())):
        if i >= max_atoms:
            lines.append(f"  ... ({len(section_atoms) - max_atoms} more atoms truncated)")
            break
        # Compact one-line atom render
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
        # Literal text on the next indented line
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
