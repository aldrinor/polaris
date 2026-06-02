"""I-meta-006 (#1006) — system-agnostic ATOMIC claim + citation extraction.

Turns ANY deep-research report (POLARIS, ChatGPT, Gemini) into a uniform list of
ATOMIC factual claims, each carrying the citation(s) it attaches to, so the SAME
§-1.1 faithfulness audit runs identically across systems (Codex design-gate
APPROVE iter3). It assigns NO verdicts and confers NO auto-pass — POLARIS
`[#ev:]` spans are used for extraction + to DEFINE the cited span, never to
auto-verify.

Cash-free + deterministic given the INJECTED ``atomizer`` (the real atomizer runs
in the operator-gated paid run; tests pass a deterministic fake). Compound
sentences split into separate factual atoms so the denominator is not
methodology-dependent (Codex iter-1 P1-2). An atom with NO citation is KEPT (it
scores as uncited downstream — Codex iter-1 P2-1).

Citation formats handled:
  - POLARIS: ``[#ev:<id>:<start>-<end>]`` (the exact span) + bare ``[N]`` →
    bibliography; reuses ``provenance_generator.parse_provenance_tokens``.
  - ChatGPT / Gemini: academic ``(Author, Year)`` keys + numbered superscripts,
    resolved against the report's reference list.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Callable

from src.polaris_graph.generator.provenance_generator import (
    parse_provenance_tokens,
    split_into_sentences,
)

# A system identifier.
SYSTEMS = ("polaris", "chatgpt", "gemini")

# academic "(Author, 2015)" / "(Acemoglu & Restrepo, 2018, 2019)" inline keys.
_AUTHOR_YEAR_RE = re.compile(r"\(([^()]*?\b(?:19|20)\d{2}[a-z]?[^()]*?)\)")
# bare numbered citation markers: [1], [12].
_NUMBERED_RE = re.compile(r"\[(\d{1,3})\]")
# unicode superscript citation markers (Gemini-style), e.g. "churn²⁷".
_SUPERSCRIPT_RE = re.compile(r"[⁰¹²³⁴-⁹]+")
_SUPERSCRIPT_MAP = {
    "⁰": "0", "¹": "1", "²": "2", "³": "3", "⁴": "4",
    "⁵": "5", "⁶": "6", "⁷": "7", "⁸": "8", "⁹": "9",
}
# strip POLARIS provenance + bare numbered markers from the rendered atom text.
_POLARIS_TOKEN_RE = re.compile(r"\[#ev:[A-Za-z0-9_]+:\d+-\d+\]")
_ATOM_HAS_ALPHA_RE = re.compile(r"[A-Za-z]")


def _superscript_to_number(run: str) -> str:
    return "".join(_SUPERSCRIPT_MAP.get(c, "") for c in run)


@dataclass(frozen=True)
class CitationRef:
    """One citation a claim attaches to. ``kind='uncited'`` = no citation."""
    system: str
    kind: str                 # "ev_span" | "author_year" | "numbered" | "uncited"
    raw_key: str              # the marker text as it appeared in the report
    resolved: str | None = None   # url / evidence_id / reference text (None = unresolved)
    ev_start: int | None = None   # POLARIS [#ev:] span (the MOST SPECIFIC cited anchor)
    ev_end: int | None = None


@dataclass
class ExtractedAtom:
    atom_id: str
    text: str                       # clean prose, citation markers stripped
    citation_refs: list[CitationRef] = field(default_factory=list)

    @property
    def is_cited(self) -> bool:
        return any(c.kind != "uncited" for c in self.citation_refs)


def _default_atomizer(sentence: str) -> list[str]:
    """Conservative deterministic fallback: split independent clauses on a
    semicolon. The real run injects a faithful atomizer; this keeps the harness
    deterministic + cash-free for the obvious compound case without inventing
    atoms."""
    parts = [p.strip() for p in sentence.split(";")]
    return [p for p in parts if p]


def _strip_markers(text: str, system: str) -> str:
    s = _POLARIS_TOKEN_RE.sub("", text)
    s = _NUMBERED_RE.sub("", s)
    if system != "polaris":
        s = _AUTHOR_YEAR_RE.sub("", s)
        s = _SUPERSCRIPT_RE.sub("", s)
    return re.sub(r"\s+", " ", s).strip()


def _extract_citations(
    sentence: str, system: str, references: dict[str, str],
) -> list[CitationRef]:
    refs: list[CitationRef] = []
    if system == "polaris":
        for tok in parse_provenance_tokens(sentence):
            refs.append(CitationRef(
                system=system, kind="ev_span", raw_key=tok.raw,
                resolved=tok.evidence_id, ev_start=tok.start, ev_end=tok.end,
            ))
        for m in _NUMBERED_RE.finditer(sentence):
            num = m.group(1)
            refs.append(CitationRef(
                system=system, kind="numbered", raw_key=m.group(0),
                resolved=references.get(num),
            ))
    else:
        for m in _AUTHOR_YEAR_RE.finditer(sentence):
            key = m.group(1).strip()
            refs.append(CitationRef(
                system=system, kind="author_year", raw_key=m.group(0),
                resolved=references.get(key) or references.get(_norm_key(key)),
            ))
        for m in _NUMBERED_RE.finditer(sentence):
            num = m.group(1)
            refs.append(CitationRef(
                system=system, kind="numbered", raw_key=m.group(0),
                resolved=references.get(num),
            ))
        for m in _SUPERSCRIPT_RE.finditer(sentence):
            num = _superscript_to_number(m.group(0))
            if num:
                refs.append(CitationRef(
                    system=system, kind="numbered", raw_key=m.group(0),
                    resolved=references.get(num),
                ))
    if not refs:
        refs.append(CitationRef(system=system, kind="uncited", raw_key=""))
    return refs


def _norm_key(key: str) -> str:
    return re.sub(r"\s+", " ", key.strip().lower())


def extract_atoms(
    report_text: str,
    system: str,
    references: dict[str, str] | None = None,
    *,
    atomizer: Callable[[str], list[str]] | None = None,
    question_id: str = "",
) -> list[ExtractedAtom]:
    """Extract atomic claims + their citations from a report. ``references`` maps
    a citation key (numbered string / author-year / normalized author-year) to a
    resolved source (url/title); ``atomizer`` is the INJECTED faithful atomizer
    (default = conservative semicolon split)."""
    if system not in SYSTEMS:
        raise ValueError(f"unknown system {system!r}; expected one of {SYSTEMS}")
    references = references or {}
    atomize = atomizer or _default_atomizer

    atoms: list[ExtractedAtom] = []
    for si, sentence in enumerate(split_into_sentences(report_text)):
        refs = _extract_citations(sentence, system, references)
        for ai, raw_atom in enumerate(atomize(sentence)):
            text = _strip_markers(raw_atom, system)
            if not text or not _ATOM_HAS_ALPHA_RE.search(text):
                continue
            prefix = f"{system}:{question_id}:" if question_id else f"{system}:"
            atoms.append(ExtractedAtom(
                atom_id=f"{prefix}{si}:{ai}", text=text, citation_refs=list(refs),
            ))
    return atoms
