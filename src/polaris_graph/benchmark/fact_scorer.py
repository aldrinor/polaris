"""I-meta-006 (#1006) — FACT faithfulness scoring (evidence-locked judge harness).

Turns extracted atoms into reconciled per-claim ``ClaimRow``s for
``claim_audit_scorer``, by running an EVIDENCE-LOCKED judge against the MOST
SPECIFIC cited span each system supplied (Codex design-gate APPROVE iter3).

§-1.1 guarantees enforced HERE (not trusted from the judge):
  - The judge reads the FETCHED cited span, never title/abstract/metadata.
  - For VERIFIED / PARTIAL / FABRICATED, the judge's ``span_quote`` MUST be a
    literal substring of the fetched span; if not, the harness FAILS CLOSED to
    UNSUPPORTED (a judge that cannot produce a real supporting/refuting quote does
    NOT get to verify) — the quote cannot be fabricated (iter-1 P1-1).
  - Severity (S0-S3) is audit-assigned by the judge for EVERY atom, including
    uncited / unreachable ones (iter-2 P2-2); the harness never invents it.
  - MOST-SPECIFIC span per system, NO broader-source fallback; POLARIS ``[#ev:]``
    defines its span but confers NO auto-verification (iter-1 P1-4 / ruling q3).
  - Unresolved citation → UNREACHABLE(source_missing), kept in the denominator
    (iter-1 P2-2). Metadata/abstract-only → UNREACHABLE(metadata_only) (iter-2 P2-1).

The ``span_fetcher`` and ``judge`` are INJECTED (the real fetcher + the
Claude+Codex reconciled-audit adapter run in the operator-gated paid run; tests
pass deterministic fakes — cash-free).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from src.polaris_graph.benchmark.claim_audit_scorer import ClaimRow
from src.polaris_graph.benchmark.report_claim_extractor import (
    CitationRef,
    ExtractedAtom,
)

_VALID_SEVERITIES = ("S0", "S1", "S2", "S3")
_QUOTE_REQUIRED_VERDICTS = ("VERIFIED", "PARTIAL", "FABRICATED")


@dataclass
class SpanResult:
    """What ``span_fetcher`` returns: the fetched cited span TEXT, or an
    unreachable subtype when the actual cited source text could not be fetched."""
    text: str | None
    unreachable_subtype: str | None = None   # set iff text is None


@dataclass
class JudgeVerdict:
    """What the injected evidence-locked judge returns for one atom."""
    verdict: str               # VERIFIED|PARTIAL|UNSUPPORTED|FABRICATED|UNREACHABLE
    severity: str              # S0|S1|S2|S3 (audit-assigned)
    span_quote: str | None = None     # exact supporting/refuting quote from the span
    audit_note: str | None = None
    unreachable_subtype: str | None = None


SpanFetcher = Callable[[CitationRef], SpanResult]
Judge = Callable[[str, "str | None", "CitationRef | None"], JudgeVerdict]


def _severity(jv: JudgeVerdict) -> str:
    return jv.severity if jv.severity in _VALID_SEVERITIES else "S2"


def _most_specific_ref(atom: ExtractedAtom) -> CitationRef | None:
    """The most specific cited anchor: a POLARIS [#ev:] span first, then a
    resolved author-year/numbered citation, then any cited ref. None = uncited."""
    cited = [c for c in atom.citation_refs if c.kind != "uncited"]
    if not cited:
        return None
    for c in cited:
        if c.kind == "ev_span":
            return c
    for c in cited:
        if c.resolved:
            return c
    return cited[0]


def _uncited_row(atom: ExtractedAtom, jv: JudgeVerdict) -> ClaimRow:
    # Uncited material claim cannot be verified — UNSUPPORTED, citation_id=null.
    return ClaimRow(
        claim_id=atom.atom_id, severity=_severity(jv), verdict="UNSUPPORTED",
        citation_id=None, span_quote=None,
        audit_note=jv.audit_note or "uncited material claim; no citation supplied",
    )


def _unreachable_row(
    atom: ExtractedAtom, ref: CitationRef, subtype: str, severity: str,
) -> ClaimRow:
    return ClaimRow(
        claim_id=atom.atom_id, severity=severity, verdict="UNREACHABLE",
        citation_id=(ref.resolved or ref.raw_key or None),
        span_quote=None, unreachable_subtype=subtype,
        audit_note=f"cited source not fetchable ({subtype}); verdict withheld",
    )


def _cited_row(
    atom: ExtractedAtom, ref: CitationRef, jv: JudgeVerdict, span_text: str,
) -> ClaimRow:
    verdict = jv.verdict
    span_quote = jv.span_quote
    audit_note = jv.audit_note
    citation_id = ref.resolved or ref.raw_key or None

    # §-1.1 substring validation: a VERIFIED/PARTIAL/FABRICATED verdict MUST quote
    # a real span from the fetched text. If it does not, FAIL CLOSED to UNSUPPORTED
    # (the judge does not get to verify without a real quote).
    if verdict in _QUOTE_REQUIRED_VERDICTS:
        if not span_quote or span_quote not in span_text:
            return ClaimRow(
                claim_id=atom.atom_id, severity=_severity(jv), verdict="UNSUPPORTED",
                citation_id=citation_id, span_quote=None,
                audit_note="judge span_quote not found in fetched source; "
                           "verification withheld (fail-closed)",
            )

    # A judge that returns UNREACHABLE when the span WAS fetched is contradictory
    # → treat as UNSUPPORTED (the source was available; absence of support is
    # unsupported, not unreachable).
    if verdict == "UNREACHABLE":
        return ClaimRow(
            claim_id=atom.atom_id, severity=_severity(jv), verdict="UNSUPPORTED",
            citation_id=citation_id, span_quote=None,
            audit_note="judge returned UNREACHABLE but cited span was fetched; "
                       "coerced to UNSUPPORTED",
        )

    if verdict == "UNSUPPORTED":
        return ClaimRow(
            claim_id=atom.atom_id, severity=_severity(jv), verdict="UNSUPPORTED",
            citation_id=citation_id, span_quote=None,
            audit_note=audit_note or "no supporting span found in cited source",
        )

    # VERIFIED / PARTIAL / FABRICATED with a validated real span_quote.
    return ClaimRow(
        claim_id=atom.atom_id, severity=_severity(jv), verdict=verdict,
        citation_id=citation_id, span_quote=span_quote, audit_note=audit_note,
    )


def score_atoms(
    atoms: list[ExtractedAtom],
    *,
    span_fetcher: SpanFetcher,
    judge: Judge,
) -> list[ClaimRow]:
    """Score every atom into a ClaimRow via the injected fetcher + evidence-locked
    judge. Every atom yields exactly one row (none silently excluded)."""
    rows: list[ClaimRow] = []
    for atom in atoms:
        ref = _most_specific_ref(atom)
        if ref is None:                                   # uncited
            jv = judge(atom.text, None, None)
            rows.append(_uncited_row(atom, jv))
            continue
        # an author-year/numbered citation that resolves to NO source
        if ref.kind != "ev_span" and not ref.resolved:
            jv = judge(atom.text, None, ref)
            rows.append(_unreachable_row(atom, ref, "source_missing", _severity(jv)))
            continue
        span = span_fetcher(ref)
        if span.text is None:                             # fetched but unreachable
            jv = judge(atom.text, None, ref)
            rows.append(_unreachable_row(
                atom, ref, span.unreachable_subtype or "fetch_failure", _severity(jv),
            ))
            continue
        jv = judge(atom.text, span.text, ref)
        rows.append(_cited_row(atom, ref, jv, span.text))
    return rows
