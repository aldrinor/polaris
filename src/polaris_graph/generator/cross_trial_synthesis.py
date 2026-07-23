"""Evidence-derived cross-study synthesis context.

The slot layer already extracts source-bound fields.  This module preserves
the useful next step—finding patterns across several empirical units—without
assuming a subject area, intervention class, outcome name, or fixed study
program.  Field names and values come exclusively from the payloads.

The output is prompt context, not released prose.  It deliberately describes
which source-derived fields can be compared and leaves interpretation to the
writer and the unchanged verification path.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Iterable

from .slot_fill import SlotFillPayload

logger = logging.getLogger("polaris_graph.cross_study_synthesis")


@dataclass(frozen=True)
class _StudyFrame:
    """Extracted fields for one evidence-bound empirical unit."""

    anchor: str
    entity_id: str
    evidence_id: str
    fields: dict[str, str]


def _display_anchor(payload: SlotFillPayload) -> str:
    title = re.sub(r"\s+", " ", str(payload.subsection_title or "")).strip()
    if title:
        return title
    return re.sub(r"[_-]+", " ", str(payload.entity_id or "")).strip()


def _aggregate_study_frames(
    payloads: list[SlotFillPayload],
) -> list[_StudyFrame]:
    """Collect every payload that contains at least one extracted field."""

    frames: list[_StudyFrame] = []
    for payload in payloads:
        extracted = {
            field_fill.field_name: str(field_fill.value)
            for field_fill in payload.fields
            if field_fill.status == "extracted" and field_fill.value
        }
        if not extracted:
            continue
        frames.append(_StudyFrame(
            anchor=_display_anchor(payload),
            entity_id=payload.entity_id,
            evidence_id=payload.bound_ev_id,
            fields=extracted,
        ))
    return frames


@dataclass(frozen=True)
class _CrossStudyPattern:
    """One comparison licensed by fields shared across evidence units."""

    section: str
    pattern_type: str
    summary: str
    contributing_anchors: tuple[str, ...]
    contributing_evidence_ids: tuple[str, ...]


def _ordered_unique(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for raw in values:
        value = re.sub(r"\s+", " ", str(raw or "")).strip()
        key = value.casefold()
        if value and key not in seen:
            seen.add(key)
            out.append(value)
    return out


def _field_label(field_name: str) -> str:
    return re.sub(r"[_-]+", " ", field_name).strip()


def _shared_field_patterns(
    frames: list[_StudyFrame],
) -> list[_CrossStudyPattern]:
    """Describe fields reported by more than one evidence unit.

    No direction, trend, equivalence, or causal inference is asserted.  The
    values are copied verbatim from the slot payloads.
    """

    by_field: dict[str, list[tuple[_StudyFrame, str]]] = {}
    for frame in frames:
        for field_name, value in frame.fields.items():
            by_field.setdefault(field_name, []).append((frame, value))

    patterns: list[_CrossStudyPattern] = []
    for field_name, rows in by_field.items():
        if len({row.entity_id for row, _ in rows}) < 2:
            continue
        rendered = "; ".join(
            f"{frame.anchor}: {value}"
            for frame, value in rows
        )
        anchors = tuple(_ordered_unique(frame.anchor for frame, _ in rows))
        evidence_ids = tuple(
            _ordered_unique(frame.evidence_id for frame, _ in rows)
        )
        patterns.append(_CrossStudyPattern(
            section="cross-study synthesis",
            pattern_type="shared_field",
            summary=(
                f"Across the evidence units, {_field_label(field_name)} is "
                f"reported as follows: {rendered}."
            ),
            contributing_anchors=anchors,
            contributing_evidence_ids=evidence_ids,
        ))
    return patterns


def _condition_patterns(
    frames: list[_StudyFrame],
) -> list[_CrossStudyPattern]:
    """Surface different comparison conditions derived from field names.

    Schema authors commonly name such a field ``comparator`` or
    ``comparison_condition``.  Matching the linguistic stem keeps the rule
    schema-derived without enumerating possible domain values.
    """

    matching_fields = {
        field_name
        for frame in frames
        for field_name in frame.fields
        if re.search(r"compar|reference[_ -]?condition", field_name, re.I)
    }
    patterns: list[_CrossStudyPattern] = []
    for field_name in matching_fields:
        rows = [
            (frame, frame.fields[field_name])
            for frame in frames
            if frame.fields.get(field_name)
        ]
        distinct = _ordered_unique(value for _, value in rows)
        if len(distinct) < 2:
            continue
        rendered = "; ".join(
            f"{frame.anchor}: {value}"
            for frame, value in rows
        )
        patterns.append(_CrossStudyPattern(
            section="comparative synthesis",
            pattern_type="comparison_conditions",
            summary=f"Comparison conditions differ across sources: {rendered}.",
            contributing_anchors=tuple(
                _ordered_unique(frame.anchor for frame, _ in rows)
            ),
            contributing_evidence_ids=tuple(
                _ordered_unique(frame.evidence_id for frame, _ in rows)
            ),
        ))
    return patterns


@dataclass(frozen=True)
class CrossStudySynthesisBlock:
    """Prompt suggestions keyed by their evidence-derived analytical role."""

    section_to_patterns: dict[str, list[_CrossStudyPattern]] = field(
        default_factory=dict,
    )

    def get_for_section(self, section_title: str) -> list[_CrossStudyPattern]:
        """Return patterns whose field vocabulary overlaps the section.

        A dedicated synthesis/comparison section receives all patterns.  For a
        topical section, only patterns sharing a content token with its title
        are returned.
        """

        normalized = re.sub(r"\s+", " ", section_title.strip().lower())
        direct = list(self.section_to_patterns.get(normalized, []))
        title_tokens = set(re.findall(r"[a-z][a-z0-9-]{2,}", normalized))
        if re.search(r"\b(?:synth|compar|across)\w*", normalized):
            return [
                pattern
                for patterns in self.section_to_patterns.values()
                for pattern in patterns
            ]
        for key, patterns in self.section_to_patterns.items():
            key_tokens = set(re.findall(r"[a-z][a-z0-9-]{2,}", key))
            if title_tokens & key_tokens:
                direct.extend(patterns)
        # Stable de-duplication for a direct key plus token-overlap match.
        seen: set[tuple[str, str, tuple[str, ...]]] = set()
        out: list[_CrossStudyPattern] = []
        for pattern in direct:
            identity = (
                pattern.pattern_type,
                pattern.summary,
                pattern.contributing_evidence_ids,
            )
            if identity not in seen:
                seen.add(identity)
                out.append(pattern)
        return out


def build_cross_study_synthesis(
    payloads: list[SlotFillPayload],
) -> CrossStudySynthesisBlock:
    """Aggregate payloads and return evidence-derived cross-study patterns."""

    frames = _aggregate_study_frames(payloads)
    if len(frames) < 2:
        logger.info(
            "[m72] only %d evidence frames with extracted fields; "
            "cross-study synthesis skipped",
            len(frames),
        )
        return CrossStudySynthesisBlock()

    patterns = [
        *_condition_patterns(frames),
        *_shared_field_patterns(frames),
    ]
    section_to_patterns: dict[str, list[_CrossStudyPattern]] = {}
    for pattern in patterns:
        section_to_patterns.setdefault(pattern.section, []).append(pattern)
    logger.info(
        "[m72] cross-study synthesis found %d source-derived patterns",
        len(patterns),
    )
    return CrossStudySynthesisBlock(section_to_patterns=section_to_patterns)


def render_cross_study_synthesis_block(
    section_title: str,
    block: CrossStudySynthesisBlock,
) -> str:
    """Render source-derived cross-study context for one writer section."""

    patterns = block.get_for_section(section_title)
    if not patterns:
        return ""
    lines = [
        "",
        "=== M-72 CROSS-STUDY SYNTHESIS CONTEXT ===",
        (
            "The following comparisons are assembled only from extracted slot "
            "payloads. Integrate a relevant comparison when it fits this "
            "section, cite every contributing evidence marker, and do not add "
            "a trend, mechanism, or conclusion absent from the source values."
        ),
        "",
    ]
    for pattern in patterns:
        markers = "".join(
            f"[{evidence_id}]"
            for evidence_id in pattern.contributing_evidence_ids
            if evidence_id
        )
        lines.append(
            f"  - Pattern type: {pattern.pattern_type}\n"
            f"    Source-derived comparison: {pattern.summary}{markers}"
        )
    lines.append("")
    return "\n".join(lines)


# Compatibility aliases for existing call sites.  The behavior and prompt
# vocabulary are cross-study and domain-neutral.
CrossTrialSynthesisBlock = CrossStudySynthesisBlock


def build_cross_trial_synthesis(
    payloads: list[SlotFillPayload],
) -> CrossStudySynthesisBlock:
    return build_cross_study_synthesis(payloads)


def render_cross_trial_synthesis_block(
    section_title: str,
    block: CrossStudySynthesisBlock,
) -> str:
    return render_cross_study_synthesis_block(section_title, block)
