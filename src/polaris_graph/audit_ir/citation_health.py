"""Citation health checks (M-17 — Phase C).

Static integrity check over a loaded `AuditIR`. The audit bundle
exposed by M-16 only matters if its citation graph is internally
coherent: every `[#ev:<evidence_id>:<start>-<end>]` token in the
verified report must resolve to a bibliography entry, every
bibliography entry should be referenced by at least one verified
sentence, and the bookkeeping fields (tier, span bounds, num,
evidence_id uniqueness) must be self-consistent.

This module is the within-run companion to M-18 (regression
alerts, which is across-run). It does NOT fetch URLs or reach the
network — that surface is M-18 territory. Health checks here are
fast, deterministic, and run synchronously at audit-bundle export
time and on demand via the inspector endpoint.

LAW II compliance: a broken reference is a real problem and must
surface as ERROR. We do not soften severity for "yellow" runs; the
operator decides whether a yellow audit ships.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Mapping

from src.polaris_graph.audit_ir.loader import (
    AuditIR,
    BibliographyEntry,
    VerifiedReport,
)


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------


class IssueSeverity(Enum):
    """Severity tiers for citation health issues."""

    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


class CitationIssueCode(Enum):
    """Stable issue codes for citation health findings.

    Codes are stable strings (kebab-case via Enum value) so external
    consumers (regression-alerts dashboard, CSV export, automated
    triage) can filter without parsing message text.
    """

    BROKEN_REF = "broken_ref"
    BROKEN_REPORT_CITATION = "broken_report_citation"
    INVALID_SPAN = "invalid_span"
    INVALID_TIER = "invalid_tier"
    DUPLICATE_EVIDENCE_ID = "duplicate_evidence_id"
    DUPLICATE_BIB_NUM = "duplicate_bib_num"
    NON_POSITIVE_BIB_NUM = "non_positive_bib_num"
    ORPHAN_EVIDENCE = "orphan_evidence"
    EMPTY_STATEMENT = "empty_statement"
    EMPTY_URL = "empty_url"
    VERIFIED_NO_TOKENS = "verified_no_tokens"


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CitationHealthIssue:
    """One health-check finding, location-tagged for surfacing.

    Optional location fields are populated only when relevant to the
    issue type (e.g. broken_ref carries claim_id + section_title;
    duplicate_bib_num carries bib_num).
    """

    severity: IssueSeverity
    code: CitationIssueCode
    message: str
    evidence_id: str | None = None
    bib_num: int | None = None
    section_title: str | None = None
    claim_id: str | None = None


@dataclass(frozen=True)
class CitationHealthSummary:
    """Aggregate counts + an overall status traffic-light."""

    total_evidence: int
    total_sentences_verified: int
    total_sentences_dropped: int
    error_count: int
    warning_count: int
    info_count: int
    overall_status: str  # "green" | "yellow" | "red"


@dataclass(frozen=True)
class CitationHealthReport:
    """Container surfaced to inspector router + audit-bundle export."""

    issues: tuple[CitationHealthIssue, ...]
    summary: CitationHealthSummary


# ---------------------------------------------------------------------------
# Validation primitives
# ---------------------------------------------------------------------------


# Real V30 tier keys (matches run_diff convention). UNKNOWN is the
# explicit fallback used by the manifest for un-classified sources.
_VALID_TIERS: frozenset[str] = frozenset({
    "T1", "T2", "T3", "T4", "T5", "T6", "T7", "UNKNOWN",
})


def _check_bibliography(
    bibliography: tuple[BibliographyEntry, ...],
) -> tuple[list[CitationHealthIssue], dict[str, BibliographyEntry]]:
    """Scan bibliography for duplicates, invalid tiers, empty fields.

    Returns (issues, evidence_id_index). The index maps evidence_id
    to the FIRST occurrence so caller can resolve token refs without
    re-scanning. Duplicates are reported but do not poison the index.
    """
    issues: list[CitationHealthIssue] = []
    evidence_id_index: dict[str, BibliographyEntry] = {}
    seen_nums: dict[int, BibliographyEntry] = {}

    for entry in bibliography:
        if entry.evidence_id in evidence_id_index:
            issues.append(
                CitationHealthIssue(
                    severity=IssueSeverity.ERROR,
                    code=CitationIssueCode.DUPLICATE_EVIDENCE_ID,
                    message=(
                        f"evidence_id {entry.evidence_id!r} appears "
                        f"more than once in bibliography (first as "
                        f"[{evidence_id_index[entry.evidence_id].num}], "
                        f"again as [{entry.num}])"
                    ),
                    evidence_id=entry.evidence_id,
                    bib_num=entry.num,
                )
            )
        else:
            evidence_id_index[entry.evidence_id] = entry

        if entry.num in seen_nums:
            issues.append(
                CitationHealthIssue(
                    severity=IssueSeverity.ERROR,
                    code=CitationIssueCode.DUPLICATE_BIB_NUM,
                    message=(
                        f"bibliography number [{entry.num}] is used "
                        f"by multiple entries (evidence_ids "
                        f"{seen_nums[entry.num].evidence_id!r} and "
                        f"{entry.evidence_id!r})"
                    ),
                    bib_num=entry.num,
                    evidence_id=entry.evidence_id,
                )
            )
        else:
            seen_nums[entry.num] = entry

        if entry.num <= 0:
            issues.append(
                CitationHealthIssue(
                    severity=IssueSeverity.ERROR,
                    code=CitationIssueCode.NON_POSITIVE_BIB_NUM,
                    message=(
                        f"bibliography num must be a positive integer; "
                        f"got {entry.num} for evidence_id "
                        f"{entry.evidence_id!r}"
                    ),
                    bib_num=entry.num,
                    evidence_id=entry.evidence_id,
                )
            )

        if not entry.statement or not entry.statement.strip():
            issues.append(
                CitationHealthIssue(
                    severity=IssueSeverity.ERROR,
                    code=CitationIssueCode.EMPTY_STATEMENT,
                    message=(
                        f"bibliography entry [{entry.num}] "
                        f"({entry.evidence_id!r}) has no statement; "
                        f"renderers cannot caption a citation without one"
                    ),
                    bib_num=entry.num,
                    evidence_id=entry.evidence_id,
                )
            )

        if not entry.url or not entry.url.strip():
            issues.append(
                CitationHealthIssue(
                    severity=IssueSeverity.WARNING,
                    code=CitationIssueCode.EMPTY_URL,
                    message=(
                        f"bibliography entry [{entry.num}] "
                        f"({entry.evidence_id!r}) has no source URL; "
                        f"reviewers cannot follow the link to verify"
                    ),
                    bib_num=entry.num,
                    evidence_id=entry.evidence_id,
                )
            )

        if entry.tier not in _VALID_TIERS:
            issues.append(
                CitationHealthIssue(
                    severity=IssueSeverity.ERROR,
                    code=CitationIssueCode.INVALID_TIER,
                    message=(
                        f"bibliography entry [{entry.num}] "
                        f"({entry.evidence_id!r}) has tier "
                        f"{entry.tier!r} which is not a valid V30 tier "
                        f"(expected one of: "
                        f"{', '.join(sorted(_VALID_TIERS))})"
                    ),
                    bib_num=entry.num,
                    evidence_id=entry.evidence_id,
                )
            )

    return issues, evidence_id_index


def _check_verified_report(
    verified_report: VerifiedReport,
    evidence_id_index: Mapping[str, BibliographyEntry],
) -> tuple[list[CitationHealthIssue], set[str]]:
    """Scan verified-report sentences for broken refs + invalid spans.

    Returns (issues, referenced_evidence_ids). Referenced ids are
    used by the caller to detect orphan bibliography entries.
    """
    issues: list[CitationHealthIssue] = []
    referenced: set[str] = set()

    for section in verified_report.sections:
        for sentence in section.sentences:
            if not sentence.is_verified:
                # Dropped sentences may have any token shape; they
                # are not part of the rendered citation graph and
                # don't get health-checked.
                continue

            if not sentence.tokens:
                issues.append(
                    CitationHealthIssue(
                        severity=IssueSeverity.ERROR,
                        code=CitationIssueCode.VERIFIED_NO_TOKENS,
                        message=(
                            f"sentence {sentence.claim_id!r} is marked "
                            f"verified but carries no evidence tokens; "
                            f"strict_verify should have dropped it"
                        ),
                        section_title=section.title,
                        claim_id=sentence.claim_id,
                    )
                )
                continue

            for token in sentence.tokens:
                referenced.add(token.evidence_id)

                if token.evidence_id not in evidence_id_index:
                    issues.append(
                        CitationHealthIssue(
                            severity=IssueSeverity.ERROR,
                            code=CitationIssueCode.BROKEN_REF,
                            message=(
                                f"sentence {sentence.claim_id!r} cites "
                                f"evidence_id {token.evidence_id!r} but "
                                f"no bibliography entry has that id"
                            ),
                            evidence_id=token.evidence_id,
                            section_title=section.title,
                            claim_id=sentence.claim_id,
                        )
                    )

                if token.start < 0 or token.end <= token.start:
                    issues.append(
                        CitationHealthIssue(
                            severity=IssueSeverity.ERROR,
                            code=CitationIssueCode.INVALID_SPAN,
                            message=(
                                f"sentence {sentence.claim_id!r} cites "
                                f"evidence {token.evidence_id!r} with "
                                f"invalid span [{token.start}, "
                                f"{token.end}); start must be >= 0 and "
                                f"end must exceed start"
                            ),
                            evidence_id=token.evidence_id,
                            section_title=section.title,
                            claim_id=sentence.claim_id,
                        )
                    )

    return issues, referenced


# Codex M-17 v1 review fix: report.md `[N]` citations are a
# first-class renderer contract — the inspector / audit-bundle
# delivery surface displays them, and customers expect [N] in the
# rendered prose to resolve to a bibliography entry. Bibliography
# nums are positive integers, never zero, and we only flag bare
# `[N]` patterns (not `[#ev:...]` provenance tokens, which are
# handled by _check_verified_report).
#
# We strip `[#ev:...]` first to avoid accidentally matching the
# integer inside an evidence span like `[#ev:ev_001:5-10]`, and
# we strip fenced code blocks so a markdown list "[1] Item" inside
# a code block doesn't surface as a broken citation.
_REPORT_CITATION_RE = re.compile(r"\[(\d+)\]")
_PROVENANCE_TOKEN_RE = re.compile(r"\[#ev:[^\]]*\]")
_CODE_FENCE_RE = re.compile(r"```.*?```", re.DOTALL)
_INLINE_CODE_RE = re.compile(r"`[^`]*`")


def _check_report_citations(
    report_md: str,
    bibliography: tuple[BibliographyEntry, ...],
) -> list[CitationHealthIssue]:
    """Codex M-17 v1 review fix: report.md uses bare `[N]` markers
    to cite bibliography entries by number. Every `[N]` in the
    rendered prose must resolve to a bibliography entry with that
    num, or the renderer surfaces a dead link to the customer.

    Provenance tokens (`[#ev:...]`), fenced code blocks, and inline
    backtick code spans are stripped before scanning to avoid false
    positives on integer-looking content that isn't a citation.
    """
    issues: list[CitationHealthIssue] = []
    if not report_md:
        return issues

    cleaned = _CODE_FENCE_RE.sub("", report_md)
    cleaned = _INLINE_CODE_RE.sub("", cleaned)
    cleaned = _PROVENANCE_TOKEN_RE.sub("", cleaned)

    bib_nums = {entry.num for entry in bibliography}
    seen: set[int] = set()

    for match in _REPORT_CITATION_RE.finditer(cleaned):
        try:
            num = int(match.group(1))
        except ValueError:  # defensive — regex captures \d+ only
            continue
        if num in seen:
            continue
        seen.add(num)
        if num not in bib_nums:
            issues.append(
                CitationHealthIssue(
                    severity=IssueSeverity.ERROR,
                    code=CitationIssueCode.BROKEN_REPORT_CITATION,
                    message=(
                        f"report.md cites [{num}] but no bibliography "
                        f"entry has num={num}; the rendered prose "
                        f"shows a dead link to the customer"
                    ),
                    bib_num=num,
                )
            )
    return issues


def _check_orphans(
    bibliography: tuple[BibliographyEntry, ...],
    referenced_ids: set[str],
) -> list[CitationHealthIssue]:
    """Bibliography entries never cited by a verified sentence.

    Reported as WARNING (not ERROR): an orphan source is allowed —
    the corpus may have provided it during retrieval but no
    verified sentence ended up needing it. Surfacing the warning
    lets reviewers see expensive-to-acquire sources that contributed
    nothing to the rendered report.
    """
    issues: list[CitationHealthIssue] = []
    for entry in bibliography:
        if entry.evidence_id not in referenced_ids:
            issues.append(
                CitationHealthIssue(
                    severity=IssueSeverity.WARNING,
                    code=CitationIssueCode.ORPHAN_EVIDENCE,
                    message=(
                        f"bibliography entry [{entry.num}] "
                        f"({entry.evidence_id!r}) is not cited by any "
                        f"verified sentence — the source contributed "
                        f"to retrieval but not to the rendered report"
                    ),
                    bib_num=entry.num,
                    evidence_id=entry.evidence_id,
                )
            )
    return issues


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def check_citation_health(ir: AuditIR) -> CitationHealthReport:
    """Run all integrity checks over a loaded AuditIR.

    Pure function over the IR — does not mutate, does not fetch
    network, does not load source content. Safe to call from any
    request handler. Time complexity is O(B + S*T) where B is the
    bibliography size, S is the verified-sentence count, T is the
    average tokens-per-sentence (typically 1-3).
    """
    bib_issues, evidence_id_index = _check_bibliography(ir.bibliography)
    sent_issues, referenced_ids = _check_verified_report(
        ir.verified_report, evidence_id_index
    )
    orphan_issues = _check_orphans(ir.bibliography, referenced_ids)
    report_citation_issues = _check_report_citations(
        ir.report_md, ir.bibliography
    )

    all_issues = tuple(
        bib_issues + sent_issues + orphan_issues + report_citation_issues
    )

    err = sum(1 for i in all_issues if i.severity == IssueSeverity.ERROR)
    warn = sum(1 for i in all_issues if i.severity == IssueSeverity.WARNING)
    info = sum(1 for i in all_issues if i.severity == IssueSeverity.INFO)

    if err > 0:
        status = "red"
    elif warn > 0:
        status = "yellow"
    else:
        status = "green"

    summary = CitationHealthSummary(
        total_evidence=len(ir.bibliography),
        total_sentences_verified=ir.verified_report.sentences_verified,
        total_sentences_dropped=ir.verified_report.sentences_dropped,
        error_count=err,
        warning_count=warn,
        info_count=info,
        overall_status=status,
    )
    return CitationHealthReport(issues=all_issues, summary=summary)


def issue_to_dict(issue: CitationHealthIssue) -> dict:
    """Serialize an issue for JSON transport."""
    return {
        "severity": issue.severity.value,
        "code": issue.code.value,
        "message": issue.message,
        "evidence_id": issue.evidence_id,
        "bib_num": issue.bib_num,
        "section_title": issue.section_title,
        "claim_id": issue.claim_id,
    }


def report_to_dict(report: CitationHealthReport) -> dict:
    """Serialize a full health report for JSON transport."""
    return {
        "summary": {
            "total_evidence": report.summary.total_evidence,
            "total_sentences_verified": report.summary.total_sentences_verified,
            "total_sentences_dropped": report.summary.total_sentences_dropped,
            "error_count": report.summary.error_count,
            "warning_count": report.summary.warning_count,
            "info_count": report.summary.info_count,
            "overall_status": report.summary.overall_status,
        },
        "issues": [issue_to_dict(i) for i in report.issues],
    }
