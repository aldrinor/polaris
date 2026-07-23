"""Evidence-derived structured claim-frame extraction.

The extractor copies numeric findings and their surrounding frame from each
evidence row.  It has no topic ontology: measures, entities, identifiers, and
section labels come from row metadata or from generic linguistic relations in
the quoted text.  Numeric/unit, comparison, time, sample, and uncertainty
patterns are intentionally domain-neutral.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Any


# ---------------------------------------------------------------------------
# Literal value/unit spans
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ValueUnitSpan:
    literal_text: str
    value: str
    unit: str
    span_start: int
    span_end: int


_GENERAL_NUMBER = (
    r"(?:[<>\u2264\u2265\u00b1~\u2248]\s*)?"
    r"[-+\u2212]?\d[\d,]*(?:\.\d+)?"
    r"(?:\s*(?:[-\u2013\u2014]|to)\s*[-+\u2212]?\d[\d,]*(?:\.\d+)?)?"
)
_GENERAL_SUFFIX_UNIT = (
    r"(?:%|\u2030|\u00d7|[A-Za-z\u00b5\u03bc][A-Za-z0-9\u00b5\u03bc/\^\-]*"
    r"(?:\s+(?:per\s+)?[A-Za-z\u00b5\u03bc][A-Za-z0-9\u00b5\u03bc/\^\-]*)?)"
)
_GENERAL_VALUE_UNIT_RE = re.compile(
    rf"(?<![A-Za-z0-9_.-])(?P<prefix>[$\u00a3\u20ac\u00a5]\s*)?"
    rf"(?P<value>{_GENERAL_NUMBER})\s*(?P<unit>{_GENERAL_SUFFIX_UNIT})?",
    re.IGNORECASE,
)
_NON_UNIT_WORDS = frozenset({
    "a", "an", "and", "are", "as", "at", "be", "been", "being", "but", "by",
    "did", "do", "does", "for", "from", "had", "has", "have", "if", "in", "into",
    "is", "it", "of", "on", "or", "than", "that", "the", "then", "this", "to",
    "under", "versus", "was", "were", "when", "which", "while", "with", "would",
})
_UNIT_TRAILING_RELATION_RE = re.compile(
    r"\s+(?:compared|versus|with|under|for|among|between|than|at|after|before|"
    r"over|within|during|through|by|from|to|of|in|was|were|is|are|reported|"
    r"estimated|reached|hit|yielded|produced|achieved|attained|showed|"
    r"demonstrated|found|hourly|daily|weekly|monthly|yearly)$",
    re.IGNORECASE,
)


def _clean_unit(unit: str) -> str:
    cleaned = re.sub(r"\s+", " ", str(unit or "").strip())
    cleaned = _UNIT_TRAILING_RELATION_RE.sub("", cleaned).strip()
    return "" if cleaned.casefold() in _NON_UNIT_WORDS else cleaned


def normalize_value_unit(unit: str) -> str:
    """Return an orthographic comparison key without unit conversion."""

    key = re.sub(r"\s+", " ", str(unit or "").strip().casefold())
    if key in {"percent", "percentage"}:
        return "%"
    if key in {"percentage point", "percentage points"}:
        return "percentage point"
    return key


def extract_verbatim_value_unit_spans(text: str) -> list[ValueUnitSpan]:
    """Extract exact source slices that contain both a value and a unit."""

    source = str(text or "")
    spans: list[ValueUnitSpan] = []
    for match in _GENERAL_VALUE_UNIT_RE.finditer(source):
        prefix = (match.group("prefix") or "").strip()
        raw_suffix = match.group("unit") or ""
        suffix = _clean_unit(raw_suffix)
        unit = " ".join(part for part in (prefix, suffix) if part)
        if not unit:
            continue
        start, end = match.span()
        trailing_relation = _UNIT_TRAILING_RELATION_RE.search(raw_suffix)
        if trailing_relation and match.start("unit") >= 0:
            end = match.start("unit") + len(
                raw_suffix[:trailing_relation.start()].rstrip()
            )
        literal = source[start:end]
        assert literal == source[start:end]
        spans.append(ValueUnitSpan(
            literal_text=literal,
            value=match.group("value") or "",
            unit=unit,
            span_start=start,
            span_end=end,
        ))
    return spans


# ---------------------------------------------------------------------------
# Structured atom record
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ClaimAtom:
    atom_id: str
    evidence_id: str
    span_start: int
    span_end: int
    literal_text: str
    entity: str
    endpoint: str
    comparator: str
    timepoint: str
    value: str
    unit: str
    primary_section: str
    section_tags: tuple[str, ...]
    tier: str
    value_signed: bool
    confidence: str
    provenance_class: str
    source_paper_title: str


class NumberRole(Enum):
    OUTCOME = "outcome"
    CONDITION = "condition"
    TIMEPOINT = "timepoint"
    SAMPLE_SIZE = "sample_size"
    INTERVAL_BOUND = "interval_bound"
    INTERVAL_LEVEL = "interval_level"
    SIGNIFICANCE = "significance"
    UNKNOWN = "unknown"


_NUMBER_ATOM_RE = re.compile(
    rf"(?<![A-Za-z0-9_.-])(?P<value>{_GENERAL_NUMBER})(?![A-Za-z0-9_-])",
    re.IGNORECASE,
)
_SENTENCE_BOUNDARY_RE = re.compile(
    r"(?:\.(?=\s|$|\n|[A-Z])|[!?;](?=\s|$)|\n+)"
)
_TIME_UNIT_RE = re.compile(
    r"\b(?:milliseconds?|seconds?|minutes?|hours?|days?|weeks?|months?|years?)\b",
    re.IGNORECASE,
)
_TIMEPOINT_RE = re.compile(
    r"\b(?:at|after|before|over|within|during|through|by)?\s*"
    r"(?P<value>\d+(?:\.\d+)?)\s*"
    r"(?P<unit>milliseconds?|seconds?|minutes?|hours?|days?|weeks?|months?|years?)\b",
    re.IGNORECASE,
)
_PREFIX_TIMEPOINT_RE = re.compile(
    r"\b(?P<unit>milliseconds?|seconds?|minutes?|hours?|days?|weeks?|"
    r"months?|years?)\s+(?P<value>\d+(?:\.\d+)?)\b",
    re.IGNORECASE,
)
_SAMPLE_CONTEXT_RE = re.compile(
    r"(?:\b[nN]\s*=\s*$|\b(?:sample|dataset|cohort)\s+(?:of|size\s*[:=]?)?\s*$|"
    r"\b(?:included|enrolled|recruited|surveyed|observed|analy[sz]ed)\s*$)",
    re.IGNORECASE,
)
_INTERVAL_CONTEXT_RE = re.compile(
    r"\b(?:confidence|credible|prediction)\s+interval\b|\bCI\b",
    re.IGNORECASE,
)
_SIGNIFICANCE_RE = re.compile(
    r"\b[pq]\s*(?:=|<|>|≤|≥)\s*$",
    re.IGNORECASE,
)
_RESULT_RELATION_RE = re.compile(
    r"\b(?:was|were|is|are|averaged|measured|reported|estimated|reached|hit|"
    r"stood\s+at|totaled|amounted\s+to|changed|increased|decreased|declined|"
    r"reduced|improved|worsened|rose|fell|grew|dropped|yielded|produced|"
    r"achieved|attained|showed|demonstrated|found|occurred|"
    r"accounted\s+for|corresponded\s+to|resulted\s+in)\b",
    re.IGNORECASE,
)
_COMPARISON_RE = re.compile(
    r"\b(?:versus|vs\.?|compared\s+(?:to|with)|relative\s+to|than)\b",
    re.IGNORECASE,
)
_WORD_RE = re.compile(r"[^\W\d_][\w'’\-]*", re.UNICODE)
_IDENTIFIER_RE = re.compile(
    r"\b[A-Z][A-Z0-9]*(?:[-_/][A-Z0-9]+)+\b"
)

_METADATA_MEASURE_KEYS = (
    "endpoint", "primary_endpoint", "outcome", "measure", "metric",
    "variable", "indicator", "field_name",
)
_METADATA_ENTITY_KEYS = (
    "entity", "entity_name", "intervention", "exposure", "condition",
    "arm", "group", "system", "model_name", "study_name", "source_name",
)
_METADATA_SECTION_KEYS = (
    "primary_section", "section", "section_title", "rendering_slot",
    "topic", "facet",
)


def _row_text(row: dict[str, Any], keys: tuple[str, ...]) -> str:
    for key in keys:
        value = row.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _sentence_span(text: str, position: int) -> tuple[int, int, str]:
    start = 0
    for boundary in _SENTENCE_BOUNDARY_RE.finditer(text):
        if boundary.end() <= position:
            start = boundary.end()
            continue
        end = boundary.start()
        return start, end, text[start:end].strip()
    return start, len(text), text[start:].strip()


def _trim_frame_phrase(value: str) -> str:
    phrase = re.sub(r"\s+", " ", str(value or "")).strip(" ,:;.-")
    if not phrase:
        return ""
    phrase = re.sub(
        r"^(?:(?:the|a|an)\s+)?"
        r"(?:adjusted\s+|estimated\s+|observed\s+)?",
        "",
        phrase,
        flags=re.IGNORECASE,
    )
    change_match = re.search(
        r"\b(?:change|difference|reduction|increase|decrease)\s+"
        r"(?:from\s+\w+\s+)?(?:in|of)\s+(.+)$",
        phrase,
        re.IGNORECASE,
    )
    if change_match:
        phrase = change_match.group(1)
    # A source often writes ``entity + result verb + measure`` before the
    # value.  Retain the source-written measure while dropping the grammatical
    # subject and relation; no entity or measure vocabulary is assumed.
    relation_match = re.match(
        r"^.*\b(?:averaged|measured|reported|estimated|reached|hit|"
        r"totaled|changed|increased|decreased|declined|reduced|improved|"
        r"worsened|yielded|produced|achieved|attained|showed|demonstrated|"
        r"found)\s+(?P<measure>.+)$",
        phrase,
        re.IGNORECASE,
    )
    if relation_match:
        phrase = relation_match.group("measure")
        phrase = re.sub(
            r"^(?:the|a|an)\s+",
            "",
            phrase,
            flags=re.IGNORECASE,
        )
    phrase = re.sub(
        r"\s+\b(?:at|after|before|over|within|during|through|by)\s+"
        r"\d+(?:\.\d+)?\s*(?:milliseconds?|seconds?|minutes?|hours?|days?|weeks?|months?|years?)\b.*$",
        "",
        phrase,
        flags=re.IGNORECASE,
    )
    phrase = re.sub(
        r"\s+\b(?:change|difference|reduction|increase|decrease|value|level)\s*$",
        "",
        phrase,
        flags=re.IGNORECASE,
    )
    words = phrase.split()
    if len(words) > 10:
        phrase = " ".join(words[-10:])
    return phrase.strip(" ,:;.-")


def _metadata_measure(row: dict[str, Any]) -> str:
    return re.sub(
        r"\s+", " ", _row_text(row, _METADATA_MEASURE_KEYS),
    ).strip(" ,:;.-")


def _find_measure(
    sentence: str,
    number_offset: int,
    row: dict[str, Any],
) -> str:
    """Find the nearest measure phrase using generic grammatical relations."""

    metadata_measure = _metadata_measure(row)
    if metadata_measure:
        return metadata_measure
    left = sentence[:number_offset].rstrip()
    patterns = (
        r"(?:reported|estimated|measured|found|showed|demonstrated)\s+"
        r"(?:an?\s+|the\s+)?(?P<measure>[^,;:]{1,80}?)\s+"
        r"(?:of|at|as|=|:)\s*$",
        r"(?P<measure>[^,;:]{1,120}?)\s+"
        r"(?:was|were|is|are|averaged|measured|reported|estimated|reached|hit|"
        r"stood\s+at|totaled|amounted\s+to|occurred(?:\s+in)?|"
        r"accounted\s+for|corresponded\s+to)\s*(?:by|at|to|of|in|as)?\s*$",
        r"(?P<measure>[^,;:]{1,120}?)\s+"
        r"(?:changed|increased|decreased|declined|reduced|improved|worsened|"
        r"rose|fell|grew|dropped)\s*(?:by|to|from|at|of|in)?\s*$",
        r"(?:changed|increased|decreased|declined|reduced|improved|worsened|"
        r"raised|lowered|affected)\s+(?P<measure>[^,;:]{1,80}?)\s+"
        r"(?:by|to|from|at|of)\s*$",
        r"(?:primary|secondary|main)?\s*(?:endpoint|outcome|measure|metric|"
        r"indicator|variable)\s+(?:was|is|of|:)\s*"
        r"(?P<measure>[^,;:]{1,80}?)\s*$",
        r"(?:baseline|initial|starting)\s+(?P<measure>[^,;:]{1,60}?)\s*$",
        r"(?P<measure>[^,;:]{1,60}?)\s+(?:of|=|:)\s*$",
    )
    for pattern in patterns:
        match = re.search(pattern, left, re.IGNORECASE)
        if not match:
            continue
        measure = _trim_frame_phrase(match.group("measure"))
        if measure and _WORD_RE.search(measure):
            return measure
    # Some source constructions put the copied measure after the value:
    # ``entity achieved 12.4 unit measure at 30 days``.  Read that phrase up to
    # a generic comparison, scope, or time relation.
    number_match = _NUMBER_ATOM_RE.match(sentence[number_offset:])
    if number_match:
        raw_value = number_match.group("value").strip()
        unit = _unit_for_number(sentence, number_offset, raw_value)
        suffix = _suffix_after_written_unit(
            sentence[number_offset + len(raw_value):],
            unit,
        )
        suffix_match = re.match(
            r"\s*(?:of\s+)?(?P<measure>.+?)"
            r"(?=\s+(?:compared\s+(?:to|with)|relative\s+to|versus|vs\.?)\b|"
            r"\s+(?:while|whereas)\b|"
            r"\s+(?:at|after|before|over|within|during|through|by)\s+"
            r"(?:\d+(?:\.\d+)?\s*(?:milliseconds?|seconds?|minutes?|hours?|"
            r"days?|weeks?|months?|years?)|(?:milliseconds?|seconds?|minutes?|"
            r"hours?|days?|weeks?|months?|years?)\s+\d+(?:\.\d+)?)\b|"
            r"[,;:.]|$)",
            suffix,
            re.IGNORECASE,
        )
        if suffix_match:
            measure = _trim_frame_phrase(suffix_match.group("measure"))
            if (
                measure
                and _WORD_RE.search(measure)
                and not re.match(
                    r"^(?:with|under|for|among|in|from)\b",
                    measure,
                    re.IGNORECASE,
                )
            ):
                return measure
    # Coordinate lists often state the measure once, followed by several
    # condition-specific values.  Reuse only that source-written measure.
    for other_number in reversed(list(_NUMBER_ATOM_RE.finditer(sentence))):
        if other_number.start() >= number_offset:
            continue
        other_raw = other_number.group("value").strip()
        other_unit = _unit_for_number(sentence, other_number.start(), other_raw)
        if _classify_number(
            sentence, other_number.start(), other_raw, other_unit,
        ) is not NumberRole.OUTCOME:
            continue
        other_left = sentence[:other_number.start()].rstrip()
        for pattern in patterns:
            match = re.search(pattern, other_left, re.IGNORECASE)
            if not match:
                continue
            measure = _trim_frame_phrase(match.group("measure"))
            if measure and _WORD_RE.search(measure):
                return measure
    return ""


def _unit_for_number(sentence: str, number_offset: int, raw_value: str) -> str:
    """Read an adjacent unit, or inherit the nearest explicit unit in a list."""

    absolute_end = number_offset + len(raw_value)
    right = sentence[absolute_end:]
    match = re.match(r"\s*(%|‰|×|[A-Za-zµμ][A-Za-z0-9µμ/^\-]*(?:\s+[A-Za-zµμ][A-Za-z0-9µμ/^\-]*)?)", right)
    if match:
        unit = _clean_unit(match.group(1))
        if unit:
            return unit
    if re.match(
        r"\s*[\(\[]\s*\d+(?:\.\d+)?\s*%?\s*"
        r"(?:(?:confidence|credible|prediction)\s+)?(?:CI|interval)\b",
        right,
        re.IGNORECASE,
    ):
        return ""
    candidates = extract_verbatim_value_unit_spans(sentence)
    if not candidates:
        return ""
    outcome_candidates = []
    for span in candidates:
        left = sentence[max(0, span.span_start - 60):span.span_start]
        right = sentence[span.span_end:span.span_end + 30]
        if re.search(
            r"(?:\b(?:was|were|is|are|averaged|measured|reported|estimated|"
            r"reached|changed|increased|decreased|declined|reduced|improved|"
            r"worsened|rose|fell|grew|dropped|yielded|produced|occurred)\b"
            r"(?:\s+\w+){0,5}\s*(?:by|to|of|in|at)?|(?:by|to|of|in|at))\s*$",
            left,
            re.IGNORECASE,
        ) or re.match(
            r"\s*(?:with|under|for|compared|versus|vs\.?|relative\s+to)\b",
            right,
            re.IGNORECASE,
        ):
            outcome_candidates.append(span)
    pool = outcome_candidates or candidates
    return _clean_unit(min(
        pool,
        key=lambda span: min(
            abs(span.span_start - number_offset),
            abs(span.span_end - number_offset),
        ),
    ).unit)


def _suffix_after_written_unit(suffix: str, unit: str) -> str:
    """Remove the unit only when it is literally adjacent to this value."""

    if not unit:
        return suffix
    match = re.match(
        rf"\s*{re.escape(unit)}(?![A-Za-z0-9])",
        suffix,
        re.IGNORECASE,
    )
    return suffix[match.end():] if match else suffix


def _classify_number(
    sentence: str,
    number_offset: int,
    raw_value: str,
    unit: str,
) -> NumberRole:
    left = sentence[max(0, number_offset - 60):number_offset]
    right = sentence[number_offset + len(raw_value):number_offset + len(raw_value) + 40]
    if _SIGNIFICANCE_RE.search(left):
        return NumberRole.SIGNIFICANCE
    if _SAMPLE_CONTEXT_RE.search(left):
        return NumberRole.SAMPLE_SIZE
    if re.search(r"\bphase\s*$", left, re.IGNORECASE):
        return NumberRole.CONDITION
    if (
        _TIME_UNIT_RE.match(right.lstrip())
        or re.search(
            r"\b(?:milliseconds?|seconds?|minutes?|hours?|days?|weeks?|"
            r"months?|years?)\s*$",
            left,
            re.IGNORECASE,
        )
    ):
        return NumberRole.TIMEPOINT
    if _INTERVAL_CONTEXT_RE.search(sentence):
        open_paren = sentence.rfind("(", 0, number_offset)
        close_paren = sentence.find(")", number_offset)
        if open_paren >= 0 and close_paren >= 0:
            return NumberRole.INTERVAL_BOUND
        if re.match(
            r"\s*%\s*(?:(?:confidence|credible|prediction)\s+)?"
            r"(?:CI|interval)\b",
            sentence[number_offset + len(raw_value):],
            re.IGNORECASE,
        ):
            return NumberRole.INTERVAL_LEVEL
        if _INTERVAL_CONTEXT_RE.search(left):
            return NumberRole.INTERVAL_BOUND
    value_end = number_offset + len(raw_value)
    suffix = _suffix_after_written_unit(sentence[value_end:], unit)
    if re.search(
        r"\b(?:at\s+least|at\s+most|no\s+(?:less|more)\s+than)\s*$",
        left,
        re.IGNORECASE,
    ):
        return NumberRole.CONDITION
    if (
        re.search(
            r"\b(?:with|under|using|via)\b[^,;]*$",
            left,
            re.IGNORECASE,
        )
        and re.match(
            r"\s*(?:compared|versus|vs\.?|relative\s+to)\b",
            suffix,
            re.IGNORECASE,
        )
        and _NUMBER_ATOM_RE.search(left)
    ):
        return NumberRole.CONDITION
    if re.match(
        r"\s*of\s+[^,;:.]{1,100}\b"
        r"(?:achieved|attained|reached|reported|showed|demonstrated)\b",
        suffix,
        re.IGNORECASE,
    ):
        return NumberRole.OUTCOME
    if re.match(
        r"\s*(?:with|under|for|compared|versus|vs\.?|relative\s+to)\b",
        suffix,
        re.IGNORECASE,
    ):
        return NumberRole.OUTCOME
    if re.search(
        r"(?:\b(?:was|were|is|are|averaged|measured|reported|estimated|reached|hit|"
        r"stood\s+at|totaled|amounted\s+to|changed|increased|decreased|declined|"
        r"reduced|improved|worsened|rose|fell|grew|dropped|yielded|produced|"
        r"achieved|attained|occurred|accounted\s+for|corresponded\s+to|"
        r"resulted\s+in)\b"
        r"(?:\s+\w+){0,5}\s*(?:by|to|of|in|at|as)?|"
        r"(?:by|to|of|in|at))\s*$",
        left,
        re.IGNORECASE,
    ):
        return NumberRole.OUTCOME
    if re.search(r"\b(?:baseline|initial|starting)\b", left, re.IGNORECASE):
        return NumberRole.OUTCOME
    return NumberRole.UNKNOWN


def _find_entity(
    sentence: str,
    number_offset: int,
    row: dict[str, Any],
    endpoint: str = "",
) -> str:
    metadata = _row_text(row, _METADATA_ENTITY_KEYS)
    if metadata:
        return metadata
    left = sentence[:number_offset]
    result_relations = list(_RESULT_RELATION_RE.finditer(left))
    for index in range(len(result_relations) - 1, -1, -1):
        relation = result_relations[index]
        previous_end = result_relations[index - 1].end() if index else 0
        punctuation_end = max(
            left.rfind(",", previous_end, relation.start()),
            left.rfind(";", previous_end, relation.start()),
            left.rfind(":", previous_end, relation.start()),
        )
        start = punctuation_end + 1 if punctuation_end >= 0 else previous_end
        entity = left[start:relation.start()].strip()
        entity = re.sub(
            r"^.*\b(?:receiving|using|with|under|via)\s+",
            "",
            entity,
            flags=re.IGNORECASE,
        )
        entity = re.sub(
            r"^.*\b(?:while|whereas|and)\s+",
            "",
            entity,
            flags=re.IGNORECASE,
        )
        for value_span in extract_verbatim_value_unit_spans(entity):
            entity = entity.replace(value_span.literal_text, " ", 1)
        entity = re.sub(
            r"^(?:in|for|among)\s+",
            "",
            entity,
            flags=re.IGNORECASE,
        ).strip(" ,;:-")
        normalized_entity = re.sub(
            r"^(?:the|a|an|mean|median|average)\s+",
            "",
            entity,
            flags=re.IGNORECASE,
        ).casefold()
        normalized_endpoint = re.sub(
            r"^(?:the|a|an|mean|median|average)\s+",
            "",
            endpoint,
            flags=re.IGNORECASE,
        ).casefold()
        if (
            _WORD_RE.search(entity)
            and normalized_entity
            and normalized_entity != normalized_endpoint
        ):
            return entity

    right = sentence[number_offset:]
    value_match = _NUMBER_ATOM_RE.match(right)
    suffix = right[value_match.end():] if value_match else right
    adjacent_unit = _unit_for_number(
        sentence,
        number_offset,
        value_match.group("value").strip() if value_match else "",
    )
    comparison_after_value = bool(re.match(
        r"\s*(?:compared|versus|vs\.?|relative\s+to)\b",
        _suffix_after_written_unit(suffix, adjacent_unit),
        re.IGNORECASE,
    ))
    suffix = _suffix_after_written_unit(suffix, adjacent_unit)
    proportion_scope = re.match(
        r"\s*of\s+(?P<entity>[^,;:.]{1,80}?)\s+"
        r"(?:achieved|attained|reached|reported|showed|demonstrated)\b",
        suffix,
        re.IGNORECASE,
    )
    if proportion_scope:
        entity = proportion_scope.group("entity").strip()
        if _WORD_RE.search(entity):
            return entity
    after = None if comparison_after_value else re.match(
        r"\s*with\s+"
        r"(?P<entity>[^,;:.]{1,80}?)"
        r"(?=\s+(?:[<>\u2264\u2265\u00b1~\u2248]?\s*[-+\u2212]?\d|"
        r"versus|vs\.?|compared)|[,;.]|$)",
        suffix,
        re.IGNORECASE,
    )
    if after:
        entity = after.group("entity").strip()
        if _WORD_RE.search(entity):
            return entity
    identifier = _IDENTIFIER_RE.search(sentence)
    return identifier.group(0) if identifier else ""


def _find_comparator(sentence: str, entity: str) -> str:
    relation = _COMPARISON_RE.search(sentence)
    if not relation:
        return ""
    tail = sentence[relation.end():]
    candidate = re.split(
        r"[,;.]|\b(?:at|after|before|over|within|during|through)\s+\d",
        tail,
        maxsplit=1,
        flags=re.IGNORECASE,
    )[0].strip()
    if not _WORD_RE.search(candidate) or _NUMBER_ATOM_RE.match(candidate):
        with_entity = re.search(
            r"\b(?:with|under|for)\s+(?P<entity>[^,;:.]{1,80})",
            tail,
            re.IGNORECASE,
        )
        candidate = with_entity.group("entity").strip() if with_entity else ""
    candidate = re.sub(r"^(?:the|a|an)\s+", "", candidate, flags=re.IGNORECASE)
    if not candidate or candidate.casefold() == entity.casefold():
        return ""
    return candidate


def _find_timepoint(sentence: str, number_offset: int) -> str:
    candidates = [
        (
            match.start(),
            f"{match.group('value')} {match.group('unit')}",
        )
        for match in _TIMEPOINT_RE.finditer(sentence)
    ]
    candidates.extend(
        (
            match.start(),
            f"{match.group('unit')} {match.group('value')}",
        )
        for match in _PREFIX_TIMEPOINT_RE.finditer(sentence)
    )
    if not candidates:
        return ""
    _position, rendered = min(
        candidates,
        key=lambda item: abs(item[0] - number_offset),
    )
    return rendered


def _row_section(row: dict[str, Any]) -> str:
    return _row_text(row, _METADATA_SECTION_KEYS) or "Evidence"


def _confidence(endpoint: str, entity: str, unit: str, comparator: str, timepoint: str) -> str:
    present = sum(bool(value) for value in (endpoint, entity, unit, comparator, timepoint))
    if endpoint and unit and present >= 3:
        return "high"
    if endpoint and present >= 2:
        return "medium"
    return "low"


def _iter_table_atoms(
    row: dict[str, Any],
    direct_quote: str,
    counter: int,
) -> tuple[list[ClaimAtom], int, list[tuple[int, int]]]:
    """Extract generic markdown-table cells using source-written headers."""

    lines = list(re.finditer(r"(?m)^.*\|.*$", direct_quote))
    atoms: list[ClaimAtom] = []
    ranges: list[tuple[int, int]] = []
    header_cells: list[str] = []
    separator_seen = False
    section = _row_section(row)
    for line_match in lines:
        line = line_match.group(0)
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) < 2:
            continue
        if all(re.fullmatch(r":?-{3,}:?", cell) for cell in cells):
            separator_seen = True
            continue
        if not separator_seen:
            header_cells = cells
            continue
        ranges.append(line_match.span())
        measure = re.sub(r"\s+", " ", cells[0]).strip(" ,:;.-")
        if not measure or not _WORD_RE.search(measure):
            continue
        for index, cell in enumerate(cells[1:], start=1):
            cell_offset = line.find(cell)
            for number in _NUMBER_ATOM_RE.finditer(cell):
                raw = number.group("value").strip()
                unit = _unit_for_number(cell, number.start(), raw)
                if not unit:
                    continue
                counter += 1
                entity = header_cells[index] if index < len(header_cells) else ""
                atoms.append(ClaimAtom(
                    atom_id=f"atom_{counter:03d}",
                    evidence_id=str(row.get("evidence_id") or ""),
                    span_start=line_match.start() + cell_offset + number.start(),
                    span_end=line_match.start() + cell_offset + number.end(),
                    literal_text=line,
                    entity=entity,
                    endpoint=measure,
                    comparator="",
                    timepoint="",
                    value=raw.replace("\u2212", "-"),
                    unit=unit,
                    primary_section=section,
                    section_tags=(section,),
                    tier=str(row.get("tier") or ""),
                    value_signed=raw.startswith(("-", "\u2212")),
                    confidence="medium" if entity else "low",
                    provenance_class=str(row.get("provenance_class") or ""),
                    source_paper_title=str(
                        row.get("title") or row.get("source_title") or row.get("statement") or ""
                    ),
                ))
    return atoms, counter, ranges


def extract_atoms_from_evidence(
    evidence_row: dict[str, Any],
    atom_id_start: int = 0,
) -> list[ClaimAtom]:
    """Extract numeric claim frames from one evidence row."""

    direct_quote = str(evidence_row.get("direct_quote") or "")
    if not direct_quote:
        return []
    atoms, counter, table_ranges = _iter_table_atoms(
        evidence_row, direct_quote, atom_id_start,
    )

    def in_table(position: int) -> bool:
        return any(start <= position < end for start, end in table_ranges)

    section = _row_section(evidence_row)
    for match in _NUMBER_ATOM_RE.finditer(direct_quote):
        if in_table(match.start()):
            continue
        raw_value = match.group("value").strip()
        span_start, span_end, sentence = _sentence_span(direct_quote, match.start())
        if not sentence or raw_value not in sentence:
            continue
        leading_trim = len(direct_quote[span_start:span_end]) - len(
            direct_quote[span_start:span_end].lstrip()
        )
        span_start += leading_trim
        number_offset = match.start() - span_start
        unit = _unit_for_number(sentence, number_offset, raw_value)
        role = _classify_number(sentence, number_offset, raw_value, unit)
        if role is not NumberRole.OUTCOME:
            continue
        endpoint = _find_measure(sentence, number_offset, evidence_row)
        if not endpoint:
            continue
        entity = _find_entity(sentence, number_offset, evidence_row, endpoint)
        comparator = _find_comparator(sentence, entity)
        timepoint = _find_timepoint(sentence, number_offset)
        counter += 1
        normalized_value = raw_value.replace("\u2212", "-")
        atoms.append(ClaimAtom(
            atom_id=f"atom_{counter:03d}",
            evidence_id=str(evidence_row.get("evidence_id") or ""),
            span_start=span_start,
            span_end=span_end,
            literal_text=sentence,
            entity=entity,
            endpoint=endpoint,
            comparator=comparator,
            timepoint=timepoint,
            value=normalized_value,
            unit=unit,
            primary_section=section,
            section_tags=(section,),
            tier=str(evidence_row.get("tier") or ""),
            value_signed=normalized_value.startswith("-"),
            confidence=_confidence(endpoint, entity, unit, comparator, timepoint),
            provenance_class=str(evidence_row.get("provenance_class") or ""),
            source_paper_title=str(
                evidence_row.get("title")
                or evidence_row.get("source_title")
                or evidence_row.get("statement")
                or ""
            ),
        ))
    return atoms


def build_atom_catalog(
    evidence_subset: list[dict[str, Any]],
) -> dict[str, ClaimAtom]:
    """Build a stable catalog across an evidence subset."""

    catalog: dict[str, ClaimAtom] = {}
    counter = 0
    for row in evidence_subset:
        atoms = extract_atoms_from_evidence(row, atom_id_start=counter)
        for atom in atoms:
            catalog[atom.atom_id] = atom
        counter += len(atoms)
    return catalog


def _label_tokens(label: str) -> frozenset[str]:
    return frozenset(token.casefold() for token in _WORD_RE.findall(label))


def filter_atoms_for_section(
    catalog: dict[str, ClaimAtom],
    section_title: str,
) -> dict[str, ClaimAtom]:
    """Route explicit row labels by overlap; unlabeled rows remain available.

    The catalog is built from the section-local evidence subset, so the fallback
    label ``Evidence`` is intentionally section-neutral.
    """

    section_tokens = _label_tokens(section_title)
    return {
        atom_id: atom
        for atom_id, atom in catalog.items()
        if atom.primary_section == "Evidence"
        or bool(section_tokens & _label_tokens(atom.primary_section))
    }


def format_atom_catalog_for_prompt(
    section_atoms: dict[str, ClaimAtom],
    *,
    max_atoms: int = 60,
) -> str:
    if not section_atoms:
        return "ATOM CATALOG: (empty — no extracted atoms for this section)"
    lines = ["ATOM CATALOG (cite one atom_id per factual numeric claim):"]
    for index, (atom_id, atom) in enumerate(sorted(section_atoms.items())):
        if index >= max_atoms:
            lines.append(f"  ... ({len(section_atoms) - max_atoms} more atoms truncated)")
            break
        parts = [
            f"  {atom_id}: ev={atom.evidence_id} tier={atom.tier} conf={atom.confidence}",
            f"value={atom.value}{(' ' + atom.unit) if atom.unit else ''}",
            f"measure={atom.endpoint}",
        ]
        if atom.entity:
            parts.append(f"entity={atom.entity}")
        if atom.comparator:
            parts.append(f"compared_with={atom.comparator}")
        if atom.timepoint:
            parts.append(f"timepoint={atom.timepoint}")
        lines.append(" | ".join(parts))
        lines.append(f"    > {atom.literal_text[:200].replace(chr(10), ' ')}")
    return "\n".join(lines)


def format_refusal_for_missing_atom(
    *,
    endpoint: str,
    entity: str = "",
    timepoint: str = "",
) -> str:
    timepoint_clause = f"at {timepoint}" if timepoint else ""
    entity_clause = entity if entity else "the cited evidence"
    return (
        "Insufficient verified atom-level evidence from the cited corpus "
        f"to support a claim about {endpoint} {timepoint_clause} "
        f"for {entity_clause}."
    ).replace("  ", " ").strip()
