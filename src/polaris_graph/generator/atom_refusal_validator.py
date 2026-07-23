"""Atom-citation validation and explicit gap rendering.

Numeric and comparative claims are detected from generic grammar and the
evidence-derived claim-frame extractor.  This module contains no measure,
entity, topic, venue, or source-name vocabulary.
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
    extract_atoms_from_evidence,
    format_refusal_for_missing_atom,
)


class RefusalAction(str, Enum):
    REFUSED = "refused"
    ALLOWED = "allowed"
    LOGGED_ONLY = "logged_only"


class RefusalReason(str, Enum):
    MISSING_ATOM_CITATION = "missing_atom_citation"
    INVALID_ATOM_ID = "invalid_atom_id"
    EV_CITATION_FOR_CLAIM = "ev_citation_for_claim"
    SOFT_MISMATCH = "soft_mismatch"
    PARTIAL_COVERAGE_SUSPECTED = "partial_coverage_suspected"
    NO_VIOLATION = "no_violation"


_NUMBER_RE = re.compile(
    r"(?<![A-Za-z0-9_.-])[-\u2212\u2013\u2014]?\d[\d,]*(?:\.\d+)?"
    r"(?![A-Za-z0-9_-])"
)
_ATOM_ID_RE = re.compile(r"\batom_\d{3,}\b", re.IGNORECASE)
_EV_ID_RE = re.compile(r"\bev_\d+\b", re.IGNORECASE)
_BIBLIO_MARKER_RE = re.compile(r"\[\d+\]")
_ATOM_TOKEN_FOR_STRIP_RE = re.compile(
    r"\(?atom_\d{3,}(?:,\s*atom_\d{3,})*\)?",
    re.IGNORECASE,
)
_EV_TOKEN_FOR_STRIP_RE = re.compile(
    r"\[?ev_\d+(?::\d+-\d+)?\]?",
    re.IGNORECASE,
)
_RESULT_RELATION_RE = re.compile(
    r"\b(?:was|were|is|are|averaged|measured|reported|estimated|reached|"
    r"stood\s+at|totaled|amounted\s+to|changed|increased|decreased|declined|"
    r"reduced|improved|worsened|rose|fell|grew|dropped|yielded|produced|"
    r"occurred|accounted\s+for|corresponded\s+to|resulted\s+in|"
    r"associated\s+with)\b",
    re.IGNORECASE,
)
_SUBSTANTIVE_RESULT_RE = re.compile(
    r"\b(?:averaged|measured|reported|estimated|reached|stood\s+at|totaled|"
    r"amounted\s+to|changed|increased|decreased|declined|reduced|improved|"
    r"worsened|rose|fell|grew|dropped|yielded|produced|occurred|"
    r"accounted\s+for|corresponded\s+to|resulted\s+in|associated\s+with)\b",
    re.IGNORECASE,
)
_QUALITATIVE_COMPARISON_RE = re.compile(
    r"\b[^\W\d_]{3,}er\b.{0,40}\bthan\b|"
    r"\b(?:greater|less|lower|higher|more|fewer|better|worse|improved|"
    r"worsened|increased|decreased|reduced|elevated|superior|inferior|"
    r"significant(?:ly)?)\b"
    r".{0,80}\b(?:than|versus|vs\.?|compared\s+(?:to|with)|relative\s+to)\b|"
    r"\b(?:than|versus|vs\.?|compared\s+(?:to|with)|relative\s+to)\b"
    r".{0,80}\b(?:greater|less|lower|higher|more|fewer|better|worse|"
    r"improved|worsened|increased|decreased|reduced|superior|inferior)\b",
    re.IGNORECASE,
)
_TIME_NUMBER_RE = re.compile(
    r"\b\d+(?:\.\d+)?\s*(?:milliseconds?|seconds?|minutes?|hours?|days?|"
    r"weeks?|months?|years?)\b",
    re.IGNORECASE,
)
_SAMPLE_NUMBER_RE = re.compile(
    r"(?:\b[nN]\s*=\s*|\b(?:sample|dataset|cohort)\s+(?:of|size\s*[:=]?)?\s*|"
    r"\b(?:included|enrolled|recruited|surveyed|observed|analy[sz]ed)\s+)"
    r"\d[\d,]*",
    re.IGNORECASE,
)
_STRUCTURAL_NUMBER_RE = re.compile(
    r"\b(?:phase|stage|version|section|chapter|figure|table|step|round|wave)\s+"
    r"\d+(?:\.\d+)?\b",
    re.IGNORECASE,
)
_YEAR_NUMBER_RE = re.compile(
    r"\b(?:published|issued|released|dated|updated|from|in)\s+"
    r"(?:18|19|20|21)\d{2}\b",
    re.IGNORECASE,
)
_CONDITION_FRAME_RE = re.compile(
    r"\b(?:assigned|configured|set|scheduled|received|used|applied|ran|"
    r"eligible|required|criterion|threshold|range)\b",
    re.IGNORECASE,
)
_INTERVAL_RE = re.compile(
    r"\b(?:confidence|credible|prediction)\s+interval\b|\bCI\b",
    re.IGNORECASE,
)


def _strip_citation_tokens_for_detection(sentence: str) -> str:
    """Remove machine citations from the copy used for claim detection."""

    cleaned = _BIBLIO_MARKER_RE.sub(" ", sentence)
    cleaned = _ATOM_TOKEN_FOR_STRIP_RE.sub(" ", cleaned)
    cleaned = _EV_TOKEN_FOR_STRIP_RE.sub(" ", cleaned)
    return re.sub(r"\s+", " ", cleaned).strip()


def _frame_atoms(sentence: str) -> list[ClaimAtom]:
    return extract_atoms_from_evidence({
        "evidence_id": "ev_000",
        "direct_quote": sentence,
    })


def _numeric_spans(pattern: re.Pattern[str], text: str) -> list[tuple[int, int]]:
    return [match.span() for match in pattern.finditer(text)]


def _covered(position: int, spans: list[tuple[int, int]]) -> bool:
    return any(start <= position < end for start, end in spans)


def _has_nonstructural_number(sentence: str) -> bool:
    """Return whether at least one number is not purely design metadata."""

    structural_spans: list[tuple[int, int]] = []
    for pattern in (
        _TIME_NUMBER_RE,
        _SAMPLE_NUMBER_RE,
        _STRUCTURAL_NUMBER_RE,
        _YEAR_NUMBER_RE,
    ):
        structural_spans.extend(_numeric_spans(pattern, sentence))
    numbers = list(_NUMBER_RE.finditer(sentence))
    if not numbers:
        return False
    uncovered = [match for match in numbers if not _covered(match.start(), structural_spans)]
    if not uncovered:
        return False
    if (
        _CONDITION_FRAME_RE.search(sentence)
        and not _SUBSTANTIVE_RESULT_RE.search(sentence)
        and not _INTERVAL_RE.search(sentence)
    ):
        return False
    return True


@dataclass
class GapRecord:
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


def requires_atom_citation(sentence: str) -> tuple[bool, Optional[str]]:
    """Detect factual numeric or qualitative comparative claims."""

    cleaned = _strip_citation_tokens_for_detection(str(sentence or ""))
    if not cleaned:
        return False, None
    if _frame_atoms(cleaned):
        return True, "trigger_A_number_plus_endpoint"
    if _QUALITATIVE_COMPARISON_RE.search(cleaned):
        return True, "trigger_qualitative_comparative"
    if _has_nonstructural_number(cleaned):
        return True, "trigger_B_number_alone"
    return False, None


def extract_atom_citations(sentence: str) -> list[str]:
    return _ATOM_ID_RE.findall(sentence)


def extract_ev_citations(sentence: str) -> list[str]:
    return _EV_ID_RE.findall(sentence)


def has_ev_citation_for_factual_claim(sentence: str) -> bool:
    requires_atom, _ = requires_atom_citation(sentence)
    return (
        requires_atom
        and bool(_EV_ID_RE.search(sentence))
        and not bool(_ATOM_ID_RE.search(sentence))
    )


_SENTENCE_BOUNDARY_RE = re.compile(
    r"[.;!?](?:\[\d+\])?(?=\s+(?:[A-Z\[]|$))"
)


def split_sentences(text: str) -> list[str]:
    """Split prose without cutting decimals or balanced parentheticals."""

    if not text:
        return []
    sentinel = "\x00DEC\x00"
    protected = re.sub(
        r"(\d)\.(\d)",
        lambda match: f"{match.group(1)}{sentinel}{match.group(2)}",
        text,
    )
    pieces: list[str] = []
    last_end = 0
    length = len(protected)

    def inside_group(position: int) -> bool:
        stack: list[str] = []
        pairs = {")": "(", "]": "[", "}": "{"}
        for char in protected[:position]:
            if char in "([{":
                stack.append(char)
            elif char in pairs and stack and stack[-1] == pairs[char]:
                stack.pop()
        return bool(stack)

    for match in _SENTENCE_BOUNDARY_RE.finditer(protected):
        if inside_group(match.start()):
            continue
        end = match.end()
        pieces.append(protected[last_end:end])
        while end < length and protected[end].isspace():
            end += 1
        last_end = end
    if last_end < length:
        pieces.append(protected[last_end:])
    return [
        piece.replace(sentinel, ".").strip()
        for piece in pieces
        if piece.strip()
    ]


def _normalize_number(value: str) -> str:
    return (
        value.replace("\u2212", "-")
        .replace("\u2013", "-")
        .replace("\u2014", "-")
        .replace(",", "")
        .lstrip("-")
    )


def validate_sentence(
    sentence: str,
    sentence_index: int,
    section_id: str,
    section_title: str,
    catalog: dict[str, ClaimAtom],
) -> GapRecord:
    """Validate one sentence against its section-local atom catalog."""

    cited_atoms = extract_atom_citations(sentence)
    requires_atom, claim_trigger = requires_atom_citation(sentence)
    if not requires_atom and not cited_atoms:
        return GapRecord(
            section_id=section_id,
            section_title=section_title,
            sentence_index=sentence_index,
            original_sentence=sentence,
            rendered_text=sentence,
            action=RefusalAction.ALLOWED,
            reason=RefusalReason.NO_VIOLATION,
            notes="non-claim sentence; no atom citation required",
        )
    if requires_atom and not cited_atoms:
        reason = (
            RefusalReason.EV_CITATION_FOR_CLAIM
            if extract_ev_citations(sentence)
            else RefusalReason.MISSING_ATOM_CITATION
        )
        return _build_refusal_record(
            sentence,
            sentence_index,
            section_id,
            section_title,
            reason=reason,
            claim_trigger=claim_trigger,
        )
    missing = [atom_id for atom_id in cited_atoms if atom_id not in catalog]
    if missing:
        return _build_refusal_record(
            sentence,
            sentence_index,
            section_id,
            section_title,
            reason=RefusalReason.INVALID_ATOM_ID,
            missing_atoms=missing,
            cited_atoms=cited_atoms,
            claim_trigger=claim_trigger,
        )

    cleaned = _strip_citation_tokens_for_detection(sentence)
    detected_values = _NUMBER_RE.findall(cleaned)
    normalized_values = {_normalize_number(value) for value in detected_values}
    notes: list[str] = []
    for atom_id in cited_atoms:
        atom_value = _normalize_number(catalog[atom_id].value)
        if atom_value and atom_value not in normalized_values:
            notes.append(
                f"atom={atom_id} value={catalog[atom_id].value!r} "
                "not in sentence numeric tokens"
            )
    if notes:
        return GapRecord(
            section_id=section_id,
            section_title=section_title,
            sentence_index=sentence_index,
            original_sentence=sentence,
            rendered_text=sentence,
            action=RefusalAction.LOGGED_ONLY,
            reason=RefusalReason.SOFT_MISMATCH,
            cited_atoms=cited_atoms,
            detected_values=detected_values,
            notes="; ".join(notes),
        )
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


def _detected_frame(sentence: str) -> tuple[str, str, str]:
    atoms = _frame_atoms(_strip_citation_tokens_for_detection(sentence))
    if not atoms:
        return "this measured outcome", "", ""
    atom = atoms[0]
    return atom.endpoint, atom.entity, atom.timepoint


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
    endpoint, entity, timepoint = _detected_frame(sentence)
    rendered = format_refusal_for_missing_atom(
        endpoint=endpoint,
        entity=entity,
        timepoint=timepoint,
    )
    detected_values = _NUMBER_RE.findall(
        _strip_citation_tokens_for_detection(sentence)
    )
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
    endpoint, _, _ = _detected_frame(sentence)
    return endpoint


def _detect_entity_in_sentence(sentence: str) -> Optional[str]:
    _, entity, _ = _detected_frame(sentence)
    return entity or None


def _detect_timepoint_in_sentence(sentence: str) -> Optional[str]:
    _, _, timepoint = _detected_frame(sentence)
    return timepoint or None


@dataclass
class SectionValidationResult:
    section_id: str
    section_title: str
    original_text: str
    rendered_text: str
    gap_records: list[GapRecord] = field(default_factory=list)

    @property
    def refusal_count(self) -> int:
        return sum(
            record.action == RefusalAction.REFUSED
            for record in self.gap_records
        )

    @property
    def soft_mismatch_count(self) -> int:
        return sum(
            record.action == RefusalAction.LOGGED_ONLY
            for record in self.gap_records
        )

    @property
    def allowed_count(self) -> int:
        return sum(
            record.action == RefusalAction.ALLOWED
            for record in self.gap_records
        )


def validate_section(
    section_text: str,
    section_id: str,
    section_title: str,
    catalog: dict[str, ClaimAtom],
) -> SectionValidationResult:
    """Validate every sentence while preserving paragraph boundaries."""

    if not section_text or not section_text.strip():
        return SectionValidationResult(
            section_id,
            section_title,
            section_text,
            section_text,
            [],
        )
    rendered_paragraphs: list[str] = []
    records: list[GapRecord] = []
    sentence_index = 0
    for paragraph in re.split(r"\n{2,}", section_text):
        if not paragraph.strip():
            rendered_paragraphs.append(paragraph)
            continue
        rendered_sentences: list[str] = []
        for sentence in split_sentences(paragraph.strip()):
            record = validate_sentence(
                sentence,
                sentence_index,
                section_id,
                section_title,
                catalog,
            )
            records.append(record)
            rendered_sentences.append(record.rendered_text)
            sentence_index += 1
        rendered_paragraphs.append(" ".join(rendered_sentences))
    return SectionValidationResult(
        section_id=section_id,
        section_title=section_title,
        original_text=section_text,
        rendered_text="\n\n".join(rendered_paragraphs),
        gap_records=records,
    )


def build_gaps_document(
    document_id: str,
    section_results: list[SectionValidationResult],
) -> dict:
    return {
        "document_id": document_id,
        "generated_at": datetime.now(tz=timezone.utc).isoformat(),
        "sections": [
            {
                "section_id": section.section_id,
                "section_title": section.section_title,
                "claims": [record.to_dict() for record in section.gap_records],
                "summary": {
                    "total_sentences": len(section.gap_records),
                    "refused": section.refusal_count,
                    "soft_mismatch": section.soft_mismatch_count,
                    "allowed": section.allowed_count,
                },
            }
            for section in section_results
        ],
        "totals": {
            "total_sentences": sum(len(section.gap_records) for section in section_results),
            "refused": sum(section.refusal_count for section in section_results),
            "soft_mismatch": sum(
                section.soft_mismatch_count for section in section_results
            ),
            "allowed": sum(section.allowed_count for section in section_results),
        },
    }


def write_gaps_sidecar(
    output_dir: Path,
    document_id: str,
    section_results: list[SectionValidationResult],
    *,
    filename: str = "gaps.json",
) -> Path:
    path = output_dir / filename
    path.write_text(
        json.dumps(
            build_gaps_document(document_id, section_results),
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return path
