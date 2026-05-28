"""Path-B dual-§-1.1-audit ledger schema (I-safety-002b #925 PR-3).

The per-(system × question) JSON each auditor (Claude / Codex) writes for the dual line-by-line
audit. Mirrors `src.polaris_graph.benchmark.claim_audit_scorer.ClaimRow` validation so a ledger
that fails-closed here cannot smuggle a malformed row into the scorer. Pure stdlib + dataclasses
(no pydantic dep added).

Public surface:
- ``Claim``       — one atomic claim audited against the FETCHED cited span.
- ``Coverage``    — one pre-registered gold-rubric element's coverage by THIS system's report.
- ``Ledger``      — the full (system, question) audit ledger written by ONE auditor.
- ``load_ledger`` — read+validate a ledger JSON from disk.
- ``dump_ledger`` — write a validated ledger JSON to disk.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Literal

# Mirrored from claim_audit_scorer.py (PR-1) — do NOT diverge.
Verdict = Literal["VERIFIED", "PARTIAL", "UNSUPPORTED", "FABRICATED", "UNREACHABLE"]
Severity = Literal["S0", "S1", "S2", "S3"]
UnreachableSubtype = Literal["paywall", "robots", "fetch_failure", "source_missing"]
Auditor = Literal["claude", "codex", "reconciled"]
SystemId = Literal["polaris", "chatgpt", "gemini"]

_VERDICTS = ("VERIFIED", "PARTIAL", "UNSUPPORTED", "FABRICATED", "UNREACHABLE")
_SEVERITIES = ("S0", "S1", "S2", "S3")
_UNREACHABLE_SUBTYPES = ("paywall", "robots", "fetch_failure", "source_missing")
# "reconciled" is the output of dual-auditor reconciliation (PR-3 reconcile.py), NOT a
# real auditor — the upstream auditors are recorded in audit_method.
_AUDITORS = ("claude", "codex", "reconciled")
_SYSTEMS = ("polaris", "chatgpt", "gemini")


@dataclass
class Claim:
    """One atomic claim's audit row. Validation MIRRORS ClaimRow.__post_init__:
    UNREACHABLE requires unreachable_subtype; FABRICATED/PARTIAL require span_quote;
    UNSUPPORTED+cited requires span_quote OR audit_note (traceability)."""

    claim_id: str
    severity: str            # "S0"|"S1"|"S2"|"S3"
    verdict: str             # one of _VERDICTS
    citation_id: str | None = None
    span_quote: str | None = None
    unreachable_subtype: str | None = None
    audit_note: str | None = None

    def __post_init__(self) -> None:
        if not self.claim_id:
            raise ValueError("Claim.claim_id is required")
        if self.severity not in _SEVERITIES:
            raise ValueError(f"{self.claim_id}: severity {self.severity!r} not in {_SEVERITIES}")
        if self.verdict not in _VERDICTS:
            raise ValueError(f"{self.claim_id}: verdict {self.verdict!r} not in {_VERDICTS}")
        if self.verdict == "UNREACHABLE" and self.unreachable_subtype is None:
            raise ValueError(f"{self.claim_id}: UNREACHABLE requires unreachable_subtype")
        if self.verdict != "UNREACHABLE" and self.unreachable_subtype is not None:
            raise ValueError(
                f"{self.claim_id}: unreachable_subtype only valid for UNREACHABLE"
            )
        if (
            self.unreachable_subtype is not None
            and self.unreachable_subtype not in _UNREACHABLE_SUBTYPES
        ):
            raise ValueError(
                f"{self.claim_id}: unreachable_subtype {self.unreachable_subtype!r} "
                f"not in {_UNREACHABLE_SUBTYPES}"
            )
        if self.verdict in ("FABRICATED", "PARTIAL") and not self.span_quote:
            raise ValueError(
                f"{self.claim_id}: {self.verdict} requires a span_quote (the refuting/partial span)"
            )
        if (
            self.verdict == "UNSUPPORTED"
            and self.citation_id
            and not (self.span_quote or self.audit_note)
        ):
            raise ValueError(
                f"{self.claim_id}: UNSUPPORTED+cited requires a span_quote or audit_note (traceability)"
            )


@dataclass
class Coverage:
    """One pre-registered gold-rubric element's coverage row, produced in the SAME
    pass as the per-claim audit (Codex PR-3 design answer B)."""

    element_id: str
    covered: bool
    citation_supported: bool
    auditor_note: str | None = None

    def __post_init__(self) -> None:
        if not self.element_id:
            raise ValueError("Coverage.element_id is required")


@dataclass
class Ledger:
    """The full (system, question) audit ledger written by ONE auditor (claude OR codex)."""

    system: str           # one of _SYSTEMS
    question_id: str      # "Q72"|"Q75"|"Q76"|"Q78"|"Q90"
    auditor: str          # one of _AUDITORS
    audit_method: str     # short description, e.g. "dual-§-1.1-line-by-line-2026-05-28"
    audit_timestamp_utc: str
    rubric_sha256: str    # the freeze_pin.txt SHA of the rubric being audited against
    claims: list[Claim] = field(default_factory=list)
    coverage: list[Coverage] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.system not in _SYSTEMS:
            raise ValueError(f"system {self.system!r} not in {_SYSTEMS}")
        if self.auditor not in _AUDITORS:
            raise ValueError(f"auditor {self.auditor!r} not in {_AUDITORS}")
        if not self.question_id:
            raise ValueError("Ledger.question_id is required")
        if not self.audit_method:
            raise ValueError("Ledger.audit_method is required (audit-protocol identity)")
        if not self.audit_timestamp_utc:
            raise ValueError("Ledger.audit_timestamp_utc is required (audit-time identity)")
        if not self.rubric_sha256:
            raise ValueError("Ledger.rubric_sha256 is required (pre-registration anchor)")
        # Duplicate detection: claim_id and element_id are unique within a ledger.
        seen_claims = set()
        for c in self.claims:
            if c.claim_id in seen_claims:
                raise ValueError(f"duplicate claim_id {c.claim_id!r}")
            seen_claims.add(c.claim_id)
        seen_elements = set()
        for cv in self.coverage:
            if cv.element_id in seen_elements:
                raise ValueError(f"duplicate element_id {cv.element_id!r}")
            seen_elements.add(cv.element_id)


def load_ledger(path: Path) -> Ledger:
    """Read a ledger JSON; validate per dataclass __post_init__; raise on any malformed row."""
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    claims = [Claim(**c) for c in raw.get("claims", [])]
    coverage = [Coverage(**c) for c in raw.get("coverage", [])]
    head = {k: v for k, v in raw.items() if k not in ("claims", "coverage")}
    return Ledger(claims=claims, coverage=coverage, **head)


def dump_ledger(ledger: Ledger, path: Path) -> None:
    """Write a ledger JSON (validated by construction; no extra validation needed)."""
    out = asdict(ledger)
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(
        json.dumps(out, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
