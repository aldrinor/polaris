"""I-gen-005 Pattern A / I-run11-010 (#1056, D1): per-evidence anti-fabrication allow-list.

For reasoning-first generators (V4 Pro), the generator is prone to fabricating plausible-sounding
NUMBERS, TRIAL NAMES, and DRUG NAMES that do not appear in the cited evidence span
(`number_not_in_any_cited_span` failure mode, ~12 instances/smoke per
docs/v4_pro_constrained_value_research_2026_05_25.md). This module extracts the CLOSED-WORLD set of
such values that actually appear in each evidence row, so `format_allow_list_for_prompt` can inject
"for evidence ev_X you may cite ONLY these values" into the system prompt. It is a PROMPT-TIME
constraint that complements the post-hoc `strict_verify` numeric/decimal check (§9.1): strict_verify
still drops a fabricated number at verification time, but the allow-list reduces fabrication up front
(and is the only prompt-time guard against fabricated non-numeric trial/drug NAMES).

History: this module existed locally (an orphan `.pyc` survived) but was NEVER committed, so the
import at multi_section_generator.py silently `ModuleNotFoundError`-d on every clean checkout and the
allow-list was a no-op. Restored under #1056 D1; the call site now imports it OUTSIDE its try so a
future deletion fails loud instead of silently degrading.

Pure-stdlib, no network, no model calls. Extraction preserves the ORIGINAL surface form of each value
(e.g. the Unicode minus "−2.04" and the spacing "12.9 kg") because the generated output is matched
EXACTLY against the allow-list — lossy normalization would cause false negatives.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# A single evidence span longer than this is not scanned (defensive: avoid a pathological regex pass
# on a malformed/huge body; the cited spans are kept well under this in practice). LAW VI: overridable.
import os as _os

_MAX_SCAN_CHARS = max(1000, int(_os.getenv("PG_ALLOW_LIST_MAX_SCAN_CHARS", "100000")))

# Numbers WITH optional unit/percent suffix. Linear (no nested quantifiers -> no catastrophic
# backtracking). Captures the verbatim surface form including a leading ASCII or Unicode minus.
_NUMBER_RE = re.compile(
    r"(?<![A-Za-z0-9_])"
    r"[-−]?\d+(?:[.,]\d+)?"
    r"(?:\s?%|\s?(?:mg|kg|g|mL|L|μg|mcg|IU|U)\b)?"
    r"(?![A-Za-z0-9_])"
)

# Named clinical trials (the I-gen-005 fabrication target). Alternation of literals + bounded
# numeric/arm suffixes — safe (no nested quantifiers). Case-sensitive (trial acronyms are uppercase).
_TRIAL_RE = re.compile(
    r"\b("
    r"SURPASS(?:[-\s]?(?:CVOT|AP|J|\d+))?"
    r"|SUSTAIN(?:[-\s]?\d+)?"
    r"|PIONEER(?:[-\s]?\d+)?"
    r"|STEP(?:[-\s]?\d+)?"
    r"|SELECT|REWIND|LEADER|SUSTAIN|HARMONY|EXSCEL|ELIXA|PIONEER"
    r"|EMPA[-\s]?REG(?:\s?OUTCOME)?|CANVAS|DECLARE(?:[-\s]?TIMI)?|CREDENCE|DAPA[-\s]?(?:HF|CKD)"
    r"|VERTIS(?:[-\s]?CV)?|AMPLITUDE(?:[-\s]?O)?|SOUL|FLOW|SURMOUNT(?:[-\s]?\d+)?"
    r")\b"
)

# Named drugs / brand names (the second fabrication target). Case-insensitive; returned lowercased.
_DRUG_RE = re.compile(
    r"\b("
    r"tirzepatide|semaglutide|dulaglutide|liraglutide|exenatide|lixisenatide|albiglutide"
    r"|efpeglenatide|retatrutide|orforglipron|survodutide|cagrilintide"
    r"|empagliflozin|dapagliflozin|canagliflozin|ertugliflozin|sotagliflozin"
    r"|metformin|insulin\sglargine|insulin\sdegludec"
    r"|Mounjaro|Zepbound|Ozempic|Wegovy|Rybelsus|Trulicity|Victoza|Saxenda|Jardiance|Farxiga|Invokana"
    r")\b",
    re.IGNORECASE,
)


@dataclass
class EvidenceAllowList:
    """The closed-world set of citable values extracted from ONE evidence row."""

    evidence_id: str
    numbers: list[str] = field(default_factory=list)
    trials: list[str] = field(default_factory=list)
    drugs: list[str] = field(default_factory=list)

    def is_empty(self) -> bool:
        return not (self.numbers or self.trials or self.drugs)


def _ordered_unique(values: list[str]) -> list[str]:
    """Preserve first-seen order while de-duplicating (stable, deterministic)."""
    seen: set[str] = set()
    out: list[str] = []
    for v in values:
        if v not in seen:
            seen.add(v)
            out.append(v)
    return out


def _extract_numbers(text: str) -> list[str]:
    return _ordered_unique(m.group().strip() for m in _NUMBER_RE.finditer(text))


def _extract_trials(text: str) -> list[str]:
    # Normalize internal whitespace so "EMPA REG" and "EMPA-REG" do not double-list.
    return _ordered_unique(
        re.sub(r"\s+", " ", m.group(1)).upper() for m in _TRIAL_RE.finditer(text)
    )


def _extract_drugs(text: str) -> list[str]:
    return _ordered_unique(
        re.sub(r"\s+", " ", m.group(1)).lower() for m in _DRUG_RE.finditer(text)
    )


def build_allow_list_for_evidence(
    evidence_id: str, direct_quote: str, statement: str
) -> EvidenceAllowList:
    """Extract the allow-list from one evidence row's cited text (`direct_quote` is authoritative;
    `statement` is appended so a value present only in the summary is still allowed)."""
    text = f"{direct_quote or ''} {statement or ''}".strip()
    if len(text) > _MAX_SCAN_CHARS:
        text = text[:_MAX_SCAN_CHARS]
    return EvidenceAllowList(
        evidence_id=evidence_id,
        numbers=_extract_numbers(text),
        trials=_extract_trials(text),
        drugs=_extract_drugs(text),
    )


def build_allow_lists(evidence_subset: list[dict]) -> dict[str, EvidenceAllowList]:
    """Build the per-evidence allow-list map. Rows with NO extractable value are omitted (so the
    caller's `if _allow_lists:` truthy check is False when the whole subset is qualitative)."""
    out: dict[str, EvidenceAllowList] = {}
    for ev in evidence_subset or []:
        ev_id = str(ev.get("evidence_id") or ev.get("id") or "")
        if not ev_id:
            continue
        allow = build_allow_list_for_evidence(
            ev_id, ev.get("direct_quote", "") or "", ev.get("statement", "") or ""
        )
        if not allow.is_empty():
            out[ev_id] = allow
    return out


def _format_capped(values: list[str], cap: int) -> str:
    if not values:
        return "(none)"
    shown = values[:cap]
    extra = len(values) - len(shown)
    rendered = ", ".join(shown)
    if extra > 0:
        rendered += f" (+{extra} more)"
    return rendered


def format_allow_list_for_prompt(
    allow_lists: dict[str, EvidenceAllowList],
    max_numbers_per_ev: int = 15,
    max_trials_per_ev: int = 5,
    max_drugs_per_ev: int = 10,
) -> str:
    """Render the allow-list map as a system-prompt constraint block."""
    if not allow_lists:
        return ""
    lines = [
        "EVIDENCE VALUE ALLOW-LIST (anti-fabrication constraint).",
        "For each evidence ID below, you may cite ONLY the NUMBERS, TRIAL NAMES, and DRUG NAMES "
        "listed for it. Do NOT introduce any number, trial, or drug name that is not in this list "
        "for the evidence you are citing — if a value you want to state is not listed, it is NOT "
        "supported by that evidence and must be omitted or attributed to a different cited source.",
    ]
    for ev_id in sorted(allow_lists):
        al = allow_lists[ev_id]
        parts = [
            f"numbers={{{_format_capped(al.numbers, max_numbers_per_ev)}}}",
            f"trials={{{_format_capped(al.trials, max_trials_per_ev)}}}",
            f"drugs={{{_format_capped(al.drugs, max_drugs_per_ev)}}}",
        ]
        lines.append(f"- {ev_id}: " + " | ".join(parts))
    lines.append(
        "Evidence rows not listed here have no extractable numeric/trial/drug content — you may "
        "cite them for qualitative claims only, with no numbers."
    )
    return "\n".join(lines)
