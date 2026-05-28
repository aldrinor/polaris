"""Dual-§-1.1-audit reconciler (I-safety-002b #925 PR-3).

Combines a Claude ledger + a Codex ledger for the same (system, question) into a single
reconciled ledger. **Conservative-MAX rule** (Codex PR-3 design answer C): on per-claim verdict
disagreement, take the WORSE-of-two as the gating verdict — clinical-lethal framing means a
problem either auditor finds counts. The disagreement is preserved in `audit_note` so the
trail is transparent. Same rule for Coverage rows (worse-of-two: covered AND citation_supported
both demoted on either-says-no).

Pure logic. No I/O beyond the schema dataclasses.
"""

from __future__ import annotations

from datetime import datetime, timezone

from scripts.dr_benchmark.ledger_schema import Claim, Coverage, Ledger

# Verdict severity order (low = good, high = bad). Conservative-MAX takes the HIGHEST.
_VERDICT_ORDER = {
    "VERIFIED": 0,
    "PARTIAL": 1,
    "UNREACHABLE": 2,
    "UNSUPPORTED": 3,
    "FABRICATED": 4,
}
_SEVERITY_ORDER = {"S3": 0, "S2": 1, "S1": 2, "S0": 3}


def _worse_verdict(a: str, b: str) -> str:
    return a if _VERDICT_ORDER[a] >= _VERDICT_ORDER[b] else b


def _worse_severity(a: str, b: str) -> str:
    """When auditors disagree on severity, escalate to the HIGHER severity (more critical)."""
    return a if _SEVERITY_ORDER[a] >= _SEVERITY_ORDER[b] else b


def _carry_evidence(a: Claim, b: Claim, worse_verdict: str) -> tuple[str | None, str | None, str | None]:
    """For the worse verdict, pick the evidence (span_quote / unreachable_subtype / audit_note)
    from whichever auditor produced THAT verdict. If both produced the worse verdict, prefer
    Claude's (deterministic tie-break) and append both notes."""
    # The "winning" row(s) on the worse_verdict.
    winners: list[Claim] = [c for c in (a, b) if c.verdict == worse_verdict]
    if not winners:
        winners = [a, b]  # both better than worse_verdict (impossible by construction)
    primary = winners[0]
    return primary.span_quote, primary.unreachable_subtype, primary.audit_note


def _reconcile_claim(a: Claim, b: Claim) -> Claim:
    """Conservative-MAX one claim; preserve disagreement in audit_note for traceability."""
    worse_v = _worse_verdict(a.verdict, b.verdict)
    worse_s = _worse_severity(a.severity, b.severity)
    span, subtype, note = _carry_evidence(a, b, worse_v)
    disagreement = a.verdict != b.verdict or a.severity != b.severity
    base_note = note or ""
    if disagreement:
        trail = (
            f"reconciled: claude={a.verdict}/{a.severity}, codex={b.verdict}/{b.severity}; "
            f"conservative-MAX -> {worse_v}/{worse_s}"
        )
        full_note = f"{base_note} | {trail}" if base_note else trail
    else:
        full_note = note
    # citation_id: prefer non-null; if both non-null but differ, prefer the worse_v auditor's.
    citation = a.citation_id if (a.verdict == worse_v and a.citation_id) else (
        b.citation_id if b.citation_id else a.citation_id
    )
    return Claim(
        claim_id=a.claim_id,
        severity=worse_s,
        verdict=worse_v,
        citation_id=citation,
        span_quote=span,
        unreachable_subtype=subtype if worse_v == "UNREACHABLE" else None,
        audit_note=full_note,
    )


def _reconcile_coverage(a: Coverage, b: Coverage) -> Coverage:
    """Conservative-MAX coverage: covered AND citation_supported each fall to the WORSE of two
    (either auditor says NO -> NO). Disagreement preserved in auditor_note."""
    covered = a.covered and b.covered
    cs = a.citation_supported and b.citation_supported
    if a.covered != b.covered or a.citation_supported != b.citation_supported:
        trail = (
            f"reconciled: claude=covered={a.covered}/cited={a.citation_supported}, "
            f"codex=covered={b.covered}/cited={b.citation_supported}; "
            f"conservative-MAX -> covered={covered}/cited={cs}"
        )
        base = a.auditor_note or b.auditor_note or ""
        note = f"{base} | {trail}" if base else trail
    else:
        note = a.auditor_note or b.auditor_note
    return Coverage(
        element_id=a.element_id,
        covered=covered,
        citation_supported=cs,
        auditor_note=note,
    )


def reconcile(claude: Ledger, codex: Ledger) -> Ledger:
    """Reconcile two single-auditor ledgers for the same (system, question) into one.

    Raises ValueError if the ledgers disagree on identity (system/question/rubric_sha256) —
    that is a §-1.1 pre-registration violation, not a reconciliation case."""
    if claude.system != codex.system:
        raise ValueError(f"system mismatch: claude={claude.system}, codex={codex.system}")
    if claude.question_id != codex.question_id:
        raise ValueError(
            f"question_id mismatch: claude={claude.question_id}, codex={codex.question_id}"
        )
    if claude.rubric_sha256 != codex.rubric_sha256:
        raise ValueError(
            "rubric_sha256 mismatch — auditors audited against DIFFERENT pinned rubrics: "
            f"claude={claude.rubric_sha256}, codex={codex.rubric_sha256}"
        )
    if claude.auditor != "claude" or codex.auditor != "codex":
        raise ValueError("reconcile(claude, codex) requires correctly-tagged auditors")

    # Join claims by claim_id (require both auditors to cover each claim).
    claude_claims = {c.claim_id: c for c in claude.claims}
    codex_claims = {c.claim_id: c for c in codex.claims}
    all_claim_ids = sorted(set(claude_claims) | set(codex_claims))
    reconciled_claims: list[Claim] = []
    for cid in all_claim_ids:
        a = claude_claims.get(cid)
        b = codex_claims.get(cid)
        if a is None or b is None:
            # Either auditor missed this claim: the missing auditor's silence is treated as
            # WORSE-than-VERIFIED (UNSUPPORTED+audit_note) — conservative discipline. The other
            # auditor's row carries forward, escalated.
            present = a or b
            reconciled_claims.append(Claim(
                claim_id=cid,
                severity=present.severity,
                verdict=_worse_verdict(present.verdict, "UNSUPPORTED"),
                citation_id=present.citation_id,
                span_quote=present.span_quote,
                unreachable_subtype=present.unreachable_subtype if present.verdict == "UNREACHABLE" else None,
                audit_note=(
                    f"reconciled: only {present.audit_note or 'one'} auditor produced a row "
                    f"({'claude' if a else 'codex'}); other auditor silent -> escalated"
                ),
            ))
        else:
            reconciled_claims.append(_reconcile_claim(a, b))

    # Join coverage by element_id (same discipline).
    claude_cov = {c.element_id: c for c in claude.coverage}
    codex_cov = {c.element_id: c for c in codex.coverage}
    all_element_ids = sorted(set(claude_cov) | set(codex_cov))
    reconciled_coverage: list[Coverage] = []
    for eid in all_element_ids:
        a = claude_cov.get(eid)
        b = codex_cov.get(eid)
        if a is None or b is None:
            present = a or b
            reconciled_coverage.append(Coverage(
                element_id=eid,
                covered=False,  # missing-auditor escalates to NOT covered (conservative)
                citation_supported=False,
                auditor_note=(
                    f"reconciled: only one auditor ({'claude' if a else 'codex'}) covered this element"
                ),
            ))
        else:
            reconciled_coverage.append(_reconcile_coverage(a, b))

    return Ledger(
        system=claude.system,
        question_id=claude.question_id,
        auditor="reconciled",
        audit_method=f"reconciled-from:claude+codex (conservative-MAX); "
                     f"upstream: {claude.audit_method} / {codex.audit_method}",
        audit_timestamp_utc=datetime.now(timezone.utc).isoformat(),
        rubric_sha256=claude.rubric_sha256,
        claims=reconciled_claims,
        coverage=reconciled_coverage,
    )
