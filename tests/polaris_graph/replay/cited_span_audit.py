"""§-1.1 ZERO-FABRICATION invariant over a saved run's audit pack (I-perm-009).

For every claim shipped in the report, every NUMERIC EXPRESSION it asserts (dose, %, HR, RR,
CI bound, p-value, count) must appear — as a WHOLE token with its sign/operator/percent
context — in that claim's CITED span. A number present in the claim but ABSENT from its cited
span is a fabrication OR a mis-bound citation (I-perm-004): either way a real faithfulness
signal, never a banned keyword-presence check.

Matching is **exact-token-set membership**, mirroring the production faithfulness gate
``clinical_generator/strict_verify.py`` (`sentence_decimals.issubset(span_decimals)`), so a
claim's "5 mg" can NEVER pass against a span's "50 mg" (the substring false-negative Codex
flagged). It is STRICTER than the production decimal check on three axes Codex called out:
  * percent is bound: "5%" != "5".
  * a measurement sign is bound: "-5%" != "5%".
  * a comparator is bound: "p<0.001" != "p=0.001".
A range dash ("0.47-0.89") is NOT treated as a sign (lookbehind), so range endpoints match.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Any

# Provenance token [#ev:evidence_id:start-end] and rendered numbered marker [12] — citation
# plumbing, never asserted numerics; stripped before extraction.
_PROVENANCE_TOKEN_RE = re.compile(r"\[#ev:[^\]]+\]")
_NUMBERED_MARKER_RE = re.compile(r"\[\d+\]")

# A numeric EXPRESSION: optional comparator (with optional whitespace before the number, so a
# SPACED inequality "p < 0.001" still binds the "<" — Codex iter-2 A3 residual), optional
# measurement sign (NOT a range dash — the lookbehind blocks a "-" that directly follows a
# digit/dot), the number (decimals + grouped thousands), optional immediate percent.
_COMPARATOR = r"(?:<=|>=|≤|≥|<|>|=)?\s?"
_SIGNED_NUMBER = r"(?<![\d.])[+\-−]?\d[\d,]*(?:\.\d+)?"
_PERCENT = r"(?:\s?%)?"
_NUMERIC_EXPR_RE = re.compile(_COMPARATOR + _SIGNED_NUMBER + _PERCENT)


class AuditPackMissingClaimsError(ValueError):
    """The audit pack has no ``claims`` — the §-1.1 audit cannot pass vacuously (LAW II)."""


@dataclass
class SpanFinding:
    """One numeric expression asserted in a claim but absent from its cited span."""

    idx: Any
    section: str
    evidence_id: str
    numeric: str
    claim_text: str
    cited_span_text: str


def _normalize(text: str) -> str:
    """NFKC + lowercase + unify minus + strip thousands separators + collapse whitespace."""
    text = unicodedata.normalize("NFKC", text)
    text = text.replace("–", "-").replace("—", "-").replace("−", "-").replace("≤", "<=").replace("≥", ">=")
    text = re.sub(r"(?<=\d),(?=\d)", "", text)  # drop thousands separators inside numbers
    return re.sub(r"\s+", " ", text).strip().lower()


def _canonical_expr(raw: str) -> str:
    """Strip internal whitespace + unify minus + drop a bare '=' so claim and span tokenize alike.

    A bare ``=`` carries no faithfulness meaning ("P value of 0.32" == "P=0.32"), so it is
    dropped to avoid false positives. The MEANINGFUL inequalities ``<`` ``>`` ``<=`` ``>=`` are
    KEPT bound to the number, so "p<0.001" still never matches "p=0.001" (Codex A3).
    """
    expr = raw.replace(" ", "").replace("−", "-").replace("≤", "<=").replace("≥", ">=").replace(",", "")
    if expr.startswith("="):
        expr = expr[1:]
    return expr


def _numeric_exprs(text: str) -> set[str]:
    cleaned = _NUMBERED_MARKER_RE.sub(" ", _PROVENANCE_TOKEN_RE.sub(" ", text))
    cleaned = _normalize(cleaned)
    out: set[str] = set()
    for match in _NUMERIC_EXPR_RE.finditer(cleaned):
        token = _canonical_expr(match.group(0))
        # A lone comparator / sign with no digit is not a numeric; require a digit.
        if any(ch.isdigit() for ch in token):
            out.add(token)
    return out


def audit_cited_spans(audit_pack: dict[str, Any]) -> list[SpanFinding]:
    """Return every numeric expression asserted in a claim that is absent from its cited span.

    Raises ``AuditPackMissingClaimsError`` if the pack has no claims (fail loud — a missing or
    empty audit pack must NEVER read as a clean zero-fabrication pass). Empty list == every
    shipped numeric is grounded verbatim (with sign/operator/percent) in its cited span.
    """
    claims = audit_pack.get("claims")
    if not claims:
        raise AuditPackMissingClaimsError(
            "audit_pack has no non-empty 'claims'; the §-1.1 zero-fabrication invariant "
            "cannot be evaluated and must NOT pass vacuously"
        )
    findings: list[SpanFinding] = []
    for claim in claims:
        span_exprs = _numeric_exprs(str(claim.get("cited_span_text", "")))
        for numeric in _numeric_exprs(str(claim.get("claim_text", ""))):
            if numeric not in span_exprs:
                findings.append(
                    SpanFinding(
                        idx=claim.get("idx"),
                        section=str(claim.get("section", "")),
                        evidence_id=str(claim.get("evidence_id", "")),
                        numeric=numeric,
                        claim_text=str(claim.get("claim_text", "")),
                        cited_span_text=str(claim.get("cited_span_text", "")),
                    )
                )
    return findings
