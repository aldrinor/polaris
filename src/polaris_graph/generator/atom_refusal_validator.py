"""Atom citation validator + gap renderer (recommended_path #4).

Per Codex APPROVE_DESIGN 2026-05-26 (refusal_design_verdict):
    - Approach C hybrid: prompt-side instruction + post-hoc enforcement
    - STRICT layer: missing/invalid atom_id → REPLACE sentence with refusal
    - SOFT layer: value/endpoint/entity/timepoint mismatch → log only, do
      NOT replace (during demo period)
    - Sentence-level refusal granularity
    - gaps.json sidecar AND inline refusal markers in report.md
    - Multi-atom sentences: ALL cited atom_ids must exist (any missing → refuse)

Quantitative-claim detector per Codex (triggers A + B only, with exclusions
for design/admin numbers; qualitative comparative outcome language also
required to cite atoms even without numbers).

This module is pure functions — no I/O except gaps.json writing via
explicit helper. Consumer (multi_section_generator) calls
`validate_section()` once per V4 Pro section body, then
`write_gaps_sidecar()` at the end.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Optional

from src.polaris_graph.generator.claim_atom_extractor import (
    ClaimAtom,
    format_refusal_for_missing_atom,
)


class RefusalAction(str, Enum):
    REFUSED = "refused"            # sentence replaced with refusal template
    ALLOWED = "allowed"            # sentence kept as-is (atom valid)
    LOGGED_ONLY = "logged_only"    # sentence kept but soft mismatch logged


class RefusalReason(str, Enum):
    MISSING_ATOM_CITATION = "missing_atom_citation"   # no atom_NNN in sentence
    INVALID_ATOM_ID = "invalid_atom_id"               # atom_NNN cited but not in catalog
    EV_CITATION_FOR_CLAIM = "ev_citation_for_claim"   # [ev_XXX] used for factual claim
    SOFT_MISMATCH = "soft_mismatch"                   # cited atom value/endpoint differs
    PARTIAL_COVERAGE_SUSPECTED = "partial_coverage_suspected"
    NO_VIOLATION = "no_violation"                     # sentence is valid


# ---------------------------------------------------------------------------
# Quantitative-claim detector (per Codex APPROVE_DESIGN trigger schema)
# ---------------------------------------------------------------------------

# Trigger A: number + endpoint vocab term
# Trigger B: number alone (but not design/admin numbers — see exclusions)

# Numbers in sentence — require non-letter context to avoid matching
# embedded digits in endpoint names like "HbA1c" (the "1") or "T2DM"
# (the "2"). Same approach as atom_extractor._NUMBER_ATOM_RE.
_NUMBER_RE = re.compile(
    r"(?<![A-Za-z0-9_.])[-−]?\d+(?:\.\d+)?(?![A-Za-z0-9_])"
)

# Endpoint vocab — superset for claim-detection (any one of these triggers
# atom-citation requirement when combined with a number or with a
# qualitative comparative term)
_ENDPOINT_VOCAB_RE = re.compile(
    r"\b("
    r"hba1c|fasting\s+(?:plasma\s+)?glucose|fpg|fsg|"
    r"body\s+weight|weight\s+(?:loss|reduction)|bmi|waist\s+circumference|"
    r"ldl[-\s]?c|hdl[-\s]?c|triglycerides|cholesterol|"
    r"blood\s+pressure|systolic|diastolic|sbp|dbp|mmhg|"
    r"mace|myocardial\s+infarction|stroke|cv\s+death|cardiovascular\s+death|"
    r"all[-\s]?cause\s+mortality|heart\s+failure|hf\s+hospitali[zs]ation|"
    r"egfr|uacr|aki|creatinine|"
    r"adverse\s+events?|aes?|serious\s+adverse|sae|discontinuation|"
    # Iter-2 fix (Codex iter-1 P1): common safety endpoints by name
    r"nausea|vomiting|diarrh(?:o)?ea|constipation|abdominal\s+pain|"
    r"injection[-\s]?site\s+reaction|"
    r"hypoglycemia|hypoglycaemia|pancreatitis|gallbladder|retinopathy|mtc|"
    r"hazard\s+ratio|risk\s+ratio|odds\s+ratio|relative\s+risk|"
    r"responder\s+rate|response\s+rate|incidence|"
    r"non[-\s]?inferiority|superior(?:ity)?"
    r")\b",
    re.IGNORECASE,
)

# NOTE (iter-4 design decision): two prior iterations (iter-2, iter-3)
# attempted an eligibility-range override via these two regex constants.
# Codex iter-3 caught that pure-regex disambiguation between
# "eligibility framing + endpoint+number" and "outcome claim + baseline
# mention" is fundamentally fragile. Per CLAUDE.md §-1.1 clinical-safety
# principle, the safer default is: any quantitative claim requires
# atom citation. Constants retained for any future revisit but NO
# LONGER WIRED into requires_atom_citation().
_ELIGIBILITY_RANGE_RE = re.compile(
    r"\b(?:inclusion\s+criter\w*|exclusion\s+criter\w*|"
    r"eligibility\s+criter\w*|eligible\s+(?:if|when)\b|"
    r"required\s+(?:hba1c|weight|bmi)\s+(?:of|between)\b)",
    re.IGNORECASE,
)
_OUTCOME_VERB_WITH_NUMBER_RE = re.compile(
    r"\b(?:reduc(?:ed|tions?|ing)|"
    r"decreas(?:ed|es?|ing)|increas(?:ed|es?|ing)|"
    r"chang(?:ed|es?)|improv(?:ed|ements?|ing)|"
    r"lower(?:ed|ing)|rais(?:ed|ing)|"
    r"fell|rose|dropped)\s+"
    r"(?:by|of|from|to)?\s*[-−]?\d",
    re.IGNORECASE,
)

# Qualitative comparative/outcome language requiring atom citation
# (Codex iter-1 P1 expanded: catch "more common with X than Y", "higher
# with X than Y", "greater reduction than", etc.)
_QUAL_COMPARATIVE_RE = re.compile(
    r"\b("
    r"greater(?:\s+\w+){0,4}\s+than|"
    r"less(?:\s+\w+){0,4}\s+than|"
    r"lower(?:\s+\w+){0,4}\s+than|"
    r"higher(?:\s+\w+){0,4}\s+than|"
    r"more(?:\s+\w+){0,4}\s+than|"     # "more common with X than Y"
    r"fewer(?:\s+\w+){0,4}\s+than|"
    r"superior(?:ity)?\s+to|non[-\s]?inferior(?:ity)?\s+to|"
    r"statistically\s+significant|significantly\s+\w+|"
    r"reduced|increased|decreased|elevated|improved|worsened|"
    r"more\s+(?:effective|common|frequent)|less\s+(?:effective|common|frequent)|"
    r"compared\s+(?:to|with)|versus|vs\.?"
    r")\b",
    re.IGNORECASE,
)

# Comparator/arm language that — combined with a comparative phrase —
# signals a factual comparative claim. Iter-4 fix (Codex iter-3 novel-P1):
# build comparator-arm regex from claim_atom_extractor._DRUG_RE so any
# drug name known to the atom extractor is also recognized here.
# Avoids drift between extractor's vocab and validator's vocab.
def _build_comparative_arm_re() -> re.Pattern:
    from src.polaris_graph.generator.claim_atom_extractor import _DRUG_RE
    drug_alt = _DRUG_RE.pattern.removeprefix(r"\b(").removesuffix(r")\b")
    pattern = (
        r"\b(?:than|versus|vs\.?|compared\s+(?:to|with))\s+"
        r"(?:"
        r"placebo|control(?:s|\s+arm)?|standard\s+care|usual\s+care|"
        r"active\s+comparator|background\s+therapy|sham|"
        r"glp[-\s]?1|sglt2|dpp[-\s]?4|insulin|metformin|sulfonylurea|"
        + drug_alt
        + r")\b"
    )
    return re.compile(pattern, re.IGNORECASE)


_COMPARATIVE_ARM_RE = _build_comparative_arm_re()

# Numbers to EXCLUDE from Trigger B when they appear with admin/design context
_ADMIN_NUMBER_RE = re.compile(
    r"\b("
    r"phase\s+(?:I{1,3}V?|IV|\d+)|"
    r"week[s]?\s+\d+|\d+\s+week[s]?|"
    r"month[s]?\s+\d+|\d+\s+month[s]?|"
    r"year[s]?\s+\d+|\d+\s+year[s]?|"
    r"day[s]?\s+\d+|\d+\s+day[s]?|"
    r"n\s*=\s*\d+|sample\s+size\s+\d+|"
    r"arm\s+\d+|\d+\s+arm[s]?|"
    r"\d+(?:\.\d+)?\s*(?:mg|μg|mcg|kg|g|mL|L|U|IU)(?!\s*/[dl])"  # dose-only, lab unit still triggers
    r")\b",
    re.IGNORECASE,
)

# Allowed-without-atom categories — narrative/synthesis prose
_NARRATIVE_CATEGORY_RE = re.compile(
    r"\b("
    r"mechanism\s+of\s+action|receptor\s+agonis[mt]|incretin|"
    r"open[-\s]?label|double[-\s]?blind|randomi[zs]ed|placebo[-\s]?controlled|"
    r"phase\s+(?:I{1,3}V?|IV|\d+)\s+(?:trial|study)|"
    r"inclusion\s+criter|exclusion\s+criter|eligibility|eligible\s+patients|"
    r"prevalence|epidemiology|burden\s+of\s+disease|"
    r"limitation|limited\s+by|caveat|long[-\s]?term\s+\w+\s+(?:data|safety)|"
    r"these\s+(?:outcomes|results|findings)\s+(?:were|are)\s+(?:consistent|in\s+line)"
    r")\b",
    re.IGNORECASE,
)


# Atom-ID citation pattern: atom_NNN
_ATOM_ID_RE = re.compile(r"\batom_\d{3,}\b")
_EV_ID_RE = re.compile(r"\[?ev_\d{3,}(?::\d+-\d+)?\]?")
_PROVENANCE_TOKEN_RE = re.compile(r"\[#ev:ev_\d{3,}:\d+-\d+\]")

# I-gen-005 Step 3b commit 2 (Codex iter-1 P1.1): resolved verified_text
# contains numeric bibliography markers [1], [2], etc. (from
# resolve_provenance_to_citations) + atom_NNN (from V4 Pro per Step 3a)
# + bare [ev_XXX] (defensive). All three would be matched by _NUMBER_RE
# as bare numbers and trigger false Trigger B (number alone).
#
# These strip patterns produce a CLEANED COPY used for claim detection
# and value extraction. extract_atom_citations / extract_ev_citations
# still consume the ORIGINAL sentence for citation parsing.
_BIBLIO_MARKER_RE = re.compile(r"\[\d+\]")
_ATOM_TOKEN_FOR_STRIP_RE = re.compile(
    r"\(?atom_\d{3,}(?:,\s*atom_\d{3,})*\)?",
    re.IGNORECASE,
)
_EV_TOKEN_FOR_STRIP_RE = re.compile(
    r"\[?ev_\d+(?::\d+-\d+)?\]?",
    re.IGNORECASE,
)


def _strip_citation_tokens_for_detection(sentence: str) -> str:
    """Strip [N] bibliography markers + atom_NNN + [ev_XXX] tokens from
    the sentence COPY used by claim detection and number extraction.

    Per Codex Step 3b iter-1 P1.1: validating resolved verified_text
    without stripping these tokens caused false Trigger B activations
    on narrative sentences with citation markers.

    The original sentence is preserved for citation parsing —
    extract_atom_citations / extract_ev_citations should always be
    called on the ORIGINAL sentence, never on the cleaned copy.
    """
    s = _BIBLIO_MARKER_RE.sub(" ", sentence)
    s = _ATOM_TOKEN_FOR_STRIP_RE.sub(" ", s)
    s = _EV_TOKEN_FOR_STRIP_RE.sub(" ", s)
    return re.sub(r"\s+", " ", s).strip()


@dataclass
class GapRecord:
    """One per sentence in a section's validation pass."""
    section_id: str
    section_title: str
    sentence_index: int
    original_sentence: str
    rendered_text: str
    action: RefusalAction
    reason: RefusalReason
    cited_atoms: list[str] = field(default_factory=list)
    missing_atoms: list[str] = field(default_factory=list)
    detected_endpoint: Optional[str] = None
    detected_entity: Optional[str] = None
    detected_timepoint: Optional[str] = None
    detected_values: list[str] = field(default_factory=list)
    notes: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "claim_id": f"{self.section_id}.s{self.sentence_index:03d}",
            "sentence_index": self.sentence_index,
            "original_sentence": self.original_sentence,
            "rendered_text": self.rendered_text,
            "action": self.action.value,
            "reason": self.reason.value,
            "cited_atoms": self.cited_atoms,
            "missing_atoms": self.missing_atoms,
            "detected_endpoint": self.detected_endpoint,
            "detected_entity": self.detected_entity,
            "detected_timepoint": self.detected_timepoint,
            "detected_values": self.detected_values,
            "notes": self.notes,
        }


# ---------------------------------------------------------------------------
# Quantitative-claim detection
# ---------------------------------------------------------------------------

def requires_atom_citation(sentence: str) -> tuple[bool, Optional[str]]:
    """Codex APPROVE_DESIGN claim detector.

    Returns (requires_atom, reason). True if sentence makes a factual
    quantitative claim that needs atom_NNN citation; False for pure
    narrative/mechanism/trial-design prose.

    Triggers:
      A: number + endpoint vocab term → requires atom
      B: number alone (excluding admin/design numbers) → requires atom
      Plus: qualitative comparative outcome language even without numbers

    Excludes:
      - pure mechanism / trial identity / eligibility / background prose
    """
    s_raw = sentence.strip()
    if not s_raw:
        return False, None

    # Step 3b commit 2: strip citation tokens for detection-time analysis.
    # [N] markers + atom_NNN + [ev_XXX] would otherwise be parsed as
    # bare numbers and trigger false claim-required.
    s = _strip_citation_tokens_for_detection(s_raw)
    if not s:
        return False, None

    numbers = _NUMBER_RE.findall(s)
    has_endpoint = bool(_ENDPOINT_VOCAB_RE.search(s))
    has_qual_comparative = bool(_QUAL_COMPARATIVE_RE.search(s))
    has_comparator_arm = bool(_COMPARATIVE_ARM_RE.search(s))
    has_outcome_number = bool(numbers) and has_endpoint

    # Iter-4 decision (Codex iter-3 continuing-P1): the eligibility
    # override was removed. Two iterations of regex tightening (iter-2,
    # iter-3) still couldn't reliably distinguish:
    #   - "Patients meeting inclusion criteria had HbA1c of 6.8%"  (outcome — must require)
    #   - "Eligible adults had baseline HbA1c between 7.0 and 10.0" (eligibility — should allow)
    # Codex correctly observed that pure-regex disambiguation is
    # fundamentally fragile here.
    #
    # SAFE DEFAULT: any quantitative claim requires atom citation. If
    # V4 Pro cannot find a supporting atom (because the sentence is
    # actually just eligibility framing), V4 Pro emits a refusal block.
    # The refusal reads slightly awkwardly for benign eligibility
    # sentences ("Insufficient evidence about HbA1c..."), but this is
    # SAFER than masking real outcome claims that happen to share
    # eligibility-frame keywords.
    #
    # Trade-off accepted per clinical-safety principle (CLAUDE.md §-1.1):
    # false negative (over-refuse benign eligibility) is recoverable;
    # false positive (mask real outcome) is lethal.

    # Pure narrative categories — never require atom citation UNLESS
    # there's also an outcome-number combo or qualitative comparative.
    narrative_matches = _NARRATIVE_CATEGORY_RE.findall(s)
    if narrative_matches and not has_outcome_number and not has_qual_comparative:
        return False, None

    # Trigger A: number + endpoint
    if has_outcome_number:
        return True, "trigger_A_number_plus_endpoint"

    # Qualitative comparative outcome language with an endpoint OR
    # an explicit comparator arm (versus/than/compared to PLACEBO/DRUG).
    # Catches "Tirzepatide showed greater reduction than semaglutide"
    # (no endpoint vocab term but clearly a comparative claim).
    if has_qual_comparative and (has_endpoint or has_comparator_arm):
        return True, "trigger_qualitative_comparative"

    # Trigger B: number alone, but check for admin/design exclusions
    if numbers:
        admin_matches = _ADMIN_NUMBER_RE.findall(s)
        # If the sentence has more numbers than admin matches, at least
        # one number is "outcome-like" — require citation.
        if len(numbers) > len(admin_matches):
            return True, "trigger_B_number_alone"

    return False, None


# ---------------------------------------------------------------------------
# Citation parsing
# ---------------------------------------------------------------------------

def extract_atom_citations(sentence: str) -> list[str]:
    """All atom_NNN citations in this sentence."""
    return _ATOM_ID_RE.findall(sentence)


def extract_ev_citations(sentence: str) -> list[str]:
    """All [ev_XXX] or ev_XXX citations in this sentence."""
    return _EV_ID_RE.findall(sentence)


def has_ev_citation_for_factual_claim(sentence: str) -> bool:
    """True if sentence cites [ev_XXX] for what should be a factual claim.

    Per Codex APPROVE_DESIGN: '[ev_XXX] is for non-claim transitions only.'
    """
    requires_atom, _ = requires_atom_citation(sentence)
    if not requires_atom:
        return False
    return bool(_EV_ID_RE.search(sentence)) and not _ATOM_ID_RE.search(sentence)


# ---------------------------------------------------------------------------
# Sentence splitter (decimal-aware, matches atom_extractor's logic)
# ---------------------------------------------------------------------------

# Decimal-aware sentence split. Two boundary patterns (alternation):
#   (a) [.;!?] followed by whitespace + [A-Z\[] or end-of-text
#       (standard prose boundary; lookbehind handles decimals via
#        sentinel-pre-pass in split_sentences below)
#   (b) [.;!?]\[N\] + whitespace + [A-Z\[]
#       (resolved-citation boundary — Step 3b commit 2 follow-up iter-3
#        per Codex PR #906 iter-3 P1). resolve_provenance_to_citations
#        emits "<sentence>.[1] <next_sentence>.[2]" with the citation
#        marker GLUED to the period. Pattern (a) alone misses this:
#        "[1] sentence_two" matches but skips before "[1]". Pattern (b)
#        explicitly consumes the [N] marker as part of the boundary so
#        the SECOND sentence is its own validator input.
_SENTENCE_SPLIT_RE = re.compile(
    r"(?<=[.;!?])(?:\[\d+\])?\s+(?=[A-Z\[]|$)"
)


def split_sentences(text: str) -> list[str]:
    """Decimal-aware sentence split — matches atom_extractor's boundary
    rule (period followed by digit is NOT a boundary)."""
    if not text:
        return []
    # Pre-process: protect decimals by temporarily replacing "X.Y" with
    # "XY" before split, then restore.
    PROTECT = ""
    protected = re.sub(r"(\d)\.(\d)", rf"\1{PROTECT}\2", text)
    parts = _SENTENCE_SPLIT_RE.split(protected)
    return [p.replace(PROTECT, ".").strip() for p in parts if p.strip()]


# ---------------------------------------------------------------------------
# Validation core
# ---------------------------------------------------------------------------

def validate_sentence(
    sentence: str,
    sentence_index: int,
    section_id: str,
    section_title: str,
    catalog: dict[str, ClaimAtom],
) -> GapRecord:
    """Validate one sentence against the atom catalog.

    Returns a GapRecord with action + reason.

    STRICT layer (replaces sentence with refusal):
      - Sentence requires atom citation BUT no atom_NNN cited
      - Cited atom_NNN doesn't exist in catalog
      - [ev_XXX] cited for a factual claim (no atom_NNN)
      - Multi-atom: ANY cited atom_NNN missing → replace

    SOFT layer (logged_only; sentence kept as-is):
      - Cited atom value differs from sentence value (paraphrase)
      - Cited atom endpoint differs from sentence endpoint
    """
    cited_atoms = extract_atom_citations(sentence)
    requires_atom, claim_trigger = requires_atom_citation(sentence)

    # Non-claim sentence with no atoms cited → allowed (narrative)
    if not requires_atom and not cited_atoms:
        return GapRecord(
            section_id=section_id,
            section_title=section_title,
            sentence_index=sentence_index,
            original_sentence=sentence,
            rendered_text=sentence,
            action=RefusalAction.ALLOWED,
            reason=RefusalReason.NO_VIOLATION,
            notes="narrative/non-claim sentence; no atom citation required",
        )

    # Requires atom but no atom cited
    if requires_atom and not cited_atoms:
        # Check for [ev_XXX] misuse
        if extract_ev_citations(sentence):
            return _build_refusal_record(
                sentence, sentence_index, section_id, section_title,
                reason=RefusalReason.EV_CITATION_FOR_CLAIM,
                claim_trigger=claim_trigger,
            )
        return _build_refusal_record(
            sentence, sentence_index, section_id, section_title,
            reason=RefusalReason.MISSING_ATOM_CITATION,
            claim_trigger=claim_trigger,
        )

    # Cited atoms exist — validate each exists in catalog
    missing = [aid for aid in cited_atoms if aid not in catalog]
    if missing:
        return _build_refusal_record(
            sentence, sentence_index, section_id, section_title,
            reason=RefusalReason.INVALID_ATOM_ID,
            missing_atoms=missing,
            cited_atoms=cited_atoms,
            claim_trigger=claim_trigger,
        )

    # All cited atoms valid — SOFT mismatch checks (logged_only)
    # Step 3b commit 2: extract numbers from the citation-stripped copy
    # so atom_NNN/biblio markers do not pollute detected_values.
    soft_notes = []
    sentence_for_values = _strip_citation_tokens_for_detection(sentence)
    detected_values = _NUMBER_RE.findall(sentence_for_values)
    detected_value_set = set(detected_values)
    for aid in cited_atoms:
        atom = catalog[aid]
        # Iter-2 fix (Codex iter-1 P2): tighten value matching to
        # numeric-token boundaries. Old substring check matched
        # "2.30" inside "12.30" (false negative on mismatch). New
        # check uses the same _NUMBER_RE that extracted detected_values
        # — equality on token strings (sign-normalized).
        atom_val_normalized = atom.value.replace("−", "-")
        atom_val_unsigned = atom_val_normalized.lstrip("-")
        # Sentence contains atom's value iff atom_val (signed or unsigned)
        # appears as an EXTRACTED number token in the sentence.
        sentence_unsigned = {v.lstrip("-") for v in detected_value_set}
        if atom_val_unsigned and atom_val_unsigned not in sentence_unsigned:
            soft_notes.append(
                f"atom={aid} value={atom.value!r} not in sentence numeric tokens"
            )

    if soft_notes:
        return GapRecord(
            section_id=section_id,
            section_title=section_title,
            sentence_index=sentence_index,
            original_sentence=sentence,
            rendered_text=sentence,  # KEEP (soft layer)
            action=RefusalAction.LOGGED_ONLY,
            reason=RefusalReason.SOFT_MISMATCH,
            cited_atoms=cited_atoms,
            detected_values=detected_values,
            notes="; ".join(soft_notes),
        )

    # Clean — allowed
    return GapRecord(
        section_id=section_id,
        section_title=section_title,
        sentence_index=sentence_index,
        original_sentence=sentence,
        rendered_text=sentence,
        action=RefusalAction.ALLOWED,
        reason=RefusalReason.NO_VIOLATION,
        cited_atoms=cited_atoms,
        detected_values=detected_values,
    )


def _build_refusal_record(
    sentence: str,
    sentence_index: int,
    section_id: str,
    section_title: str,
    *,
    reason: RefusalReason,
    missing_atoms: Optional[list[str]] = None,
    cited_atoms: Optional[list[str]] = None,
    claim_trigger: Optional[str] = None,
) -> GapRecord:
    """Build a refusal GapRecord. Renders the refusal template using
    detected endpoint/entity/timepoint from sentence text."""
    endpoint = _detect_endpoint_in_sentence(sentence) or "this outcome"
    entity = _detect_entity_in_sentence(sentence) or ""
    timepoint = _detect_timepoint_in_sentence(sentence) or ""

    rendered = format_refusal_for_missing_atom(
        endpoint=endpoint,
        entity=entity,
        timepoint=timepoint,
    )

    # Iter-2 fix (Codex iter-1 P2): preserve detected_values on refusal
    # records for downstream audit.
    detected_values = _NUMBER_RE.findall(sentence)

    return GapRecord(
        section_id=section_id,
        section_title=section_title,
        sentence_index=sentence_index,
        original_sentence=sentence,
        rendered_text=rendered,
        action=RefusalAction.REFUSED,
        reason=reason,
        cited_atoms=cited_atoms or [],
        missing_atoms=missing_atoms or [],
        detected_endpoint=endpoint,
        detected_entity=entity,
        detected_timepoint=timepoint,
        detected_values=detected_values,
        notes=f"claim_trigger={claim_trigger}" if claim_trigger else None,
    )


def _detect_endpoint_in_sentence(sentence: str) -> Optional[str]:
    m = _ENDPOINT_VOCAB_RE.search(sentence)
    return m.group(1).lower() if m else None


def _detect_entity_in_sentence(sentence: str) -> Optional[str]:
    # Reuse drug regex from atom_extractor — local import to avoid cycle
    from src.polaris_graph.generator.claim_atom_extractor import _DRUG_RE
    m = _DRUG_RE.search(sentence)
    return m.group(0).strip() if m else None


def _detect_timepoint_in_sentence(sentence: str) -> Optional[str]:
    m = re.search(
        r"\b(?:at|after|by|over)\s+(\d+\s*(?:weeks?|months?|years?|days?))\b",
        sentence, re.IGNORECASE,
    )
    return m.group(1).lower() if m else None


# ---------------------------------------------------------------------------
# Section-level validation
# ---------------------------------------------------------------------------

@dataclass
class SectionValidationResult:
    section_id: str
    section_title: str
    original_text: str
    rendered_text: str
    gap_records: list[GapRecord] = field(default_factory=list)

    @property
    def refusal_count(self) -> int:
        return sum(1 for g in self.gap_records if g.action == RefusalAction.REFUSED)

    @property
    def soft_mismatch_count(self) -> int:
        return sum(1 for g in self.gap_records if g.action == RefusalAction.LOGGED_ONLY)

    @property
    def allowed_count(self) -> int:
        return sum(1 for g in self.gap_records if g.action == RefusalAction.ALLOWED)


def validate_section(
    section_text: str,
    section_id: str,
    section_title: str,
    catalog: dict[str, ClaimAtom],
) -> SectionValidationResult:
    """Validate all sentences in a section, preserving paragraph
    structure. Sentence-level refusal: refused sentences are replaced
    in `rendered_text`, others kept as-is.

    Step 3b commit 2 (Codex iter-2 P2.4): split on paragraph boundaries
    FIRST, validate per paragraph, join with \\n\\n. Sentence_index is
    MONOTONIC across paragraphs so gaps.json claim_id values stay
    unique. Previously a single " ".join collapsed all paragraphs into
    a single line — broke report.md formatting.
    """
    if not section_text or not section_text.strip():
        return SectionValidationResult(
            section_id=section_id,
            section_title=section_title,
            original_text=section_text,
            rendered_text=section_text,
            gap_records=[],
        )

    paragraphs = re.split(r"\n{2,}", section_text)
    rendered_paragraphs: list[str] = []
    gap_records: list[GapRecord] = []
    sentence_index = 0  # monotonic across paragraphs

    for para in paragraphs:
        para_stripped = para.strip()
        if not para_stripped:
            rendered_paragraphs.append(para)  # preserve whitespace-only paragraph
            continue
        sentences = split_sentences(para_stripped)
        rendered_sentences: list[str] = []
        for sent in sentences:
            record = validate_sentence(
                sent, sentence_index, section_id, section_title, catalog,
            )
            gap_records.append(record)
            rendered_sentences.append(record.rendered_text)
            sentence_index += 1
        rendered_paragraphs.append(" ".join(rendered_sentences))

    rendered_text = "\n\n".join(rendered_paragraphs)
    return SectionValidationResult(
        section_id=section_id,
        section_title=section_title,
        original_text=section_text,
        rendered_text=rendered_text,
        gap_records=gap_records,
    )


# ---------------------------------------------------------------------------
# gaps.json sidecar writer
# ---------------------------------------------------------------------------

def build_gaps_document(
    document_id: str,
    section_results: list[SectionValidationResult],
) -> dict:
    """Per Codex APPROVE_DESIGN gaps.json schema."""
    return {
        "document_id": document_id,
        "generated_at": datetime.now(tz=timezone.utc).isoformat(),
        "sections": [
            {
                "section_id": s.section_id,
                "section_title": s.section_title,
                "claims": [g.to_dict() for g in s.gap_records],
                "summary": {
                    "total_sentences": len(s.gap_records),
                    "refused": s.refusal_count,
                    "soft_mismatch": s.soft_mismatch_count,
                    "allowed": s.allowed_count,
                },
            }
            for s in section_results
        ],
        "totals": {
            "total_sentences": sum(len(s.gap_records) for s in section_results),
            "refused": sum(s.refusal_count for s in section_results),
            "soft_mismatch": sum(s.soft_mismatch_count for s in section_results),
            "allowed": sum(s.allowed_count for s in section_results),
        },
    }


def write_gaps_sidecar(
    output_dir: Path,
    document_id: str,
    section_results: list[SectionValidationResult],
    *,
    filename: str = "gaps.json",
) -> Path:
    """Write the gaps.json sidecar next to report.md.

    Returns the written path. Caller is responsible for ensuring
    `output_dir` exists.
    """
    doc = build_gaps_document(document_id, section_results)
    path = output_dir / filename
    path.write_text(
        json.dumps(doc, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return path
