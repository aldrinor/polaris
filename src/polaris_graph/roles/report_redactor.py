"""Post-gate report.md reconciliation against the 4-role D8 verdicts (I-beatboth-fix-000 #1171).

THE FAITHFULNESS LEAK this module closes
----------------------------------------
``scripts/run_honest_sweep_r3.py`` assembles ``report.md`` from strict_verify-KEPT
sentences (L5780) BEFORE the authoritative 4-role D8 seam runs (L6407+). The seam
re-judges every kept sentence with the stronger Mirror/Sentinel/Judge stack and can
flip a strict_verify-kept sentence to a material non-VERIFIED verdict
(UNSUPPORTED / FABRICATED / UNREACHABLE / PARTIAL at S0/S1/S2). Today the runner
consumes that verdict ONLY as a manifest flag (``release_allowed=False`` +
``needs_rewrite``); it NEVER reconciles the assembled ``report.md`` against the
verdicts. So a sentence the strongest verifier rejected still ships as asserted prose.

drb_90 proof: ``needs_rewrite`` carried 7 material UNSUPPORTED claim_ids and at least
six of those sentences (e.g. the "$27,874 per violation" penalty figure, the
"UN Regulation No. 157 — ALKS" instrument line) were physically present in the shipped
``report.md`` body and carried-up Key Findings.

WHAT THIS HELPER DOES (fail-closed)
-----------------------------------
For every claim whose 4-role ``final_verdict`` is material-non-VERIFIED, it locates the
claim's verbatim sentence in the rendered ``report.md`` and REPLACES it with the
existing visible gap language ("did not survive verification; curator-actionable gap").
S3 (observe-only) claims are NEVER redacted (scope guard — they ship as disclosure-only).

It is REFUSE-IN-PLACE, not a generative rewrite: no new spend, no new claims. The
redaction IS the "one rewrite/refuse-in-place attempt" the D8 policy docstring designs
but the runner never wired.

The mapping is NOT 1:1 with strict_verify-kept (run_honest_sweep_r3.py:5660-5669 in-tree
caveat: downstream dedup/repair passes mutate the body). Two cases:
  * The claim's prose IS in the rendered report -> redact it (the leak).
  * The claim's prose is genuinely ABSENT from the rendered report -> already not
    shipped; record ``already_absent`` and ship nothing extra (the SAFE state).
FAIL-CLOSED contract: if a material non-VERIFIED claim's normalized prose IS present in
the normalized full report but the helper cannot pin a discrete rendered sentence to
replace, it RAISES ``ReportRedactionError`` so the caller can take the terminal
``abort_report_redaction_failed`` status rather than ship an unredacted leak.

Pure function (string ops only; no network, no I/O). The CALLER reads/writes report.md.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# Material = decision-relevant. Kept in lockstep with release_policy._MATERIAL_SEVERITIES
# and config/architecture/d8_release_policy.yaml `material_severities`. S3 is observe-only
# and is NEVER redacted (it ships disclosure-only per the BUG-11 scope guard).
DEFAULT_MATERIAL_SEVERITIES = ("S0", "S1", "S2")

# A final_verdict in this set, at a material severity, is a leak if it ships as prose.
# VERIFIED survives; PARTIAL/UNSUPPORTED/FABRICATED/UNREACHABLE are non-VERIFIED.
_NON_VERIFIED_VERDICTS = frozenset(
    {"UNSUPPORTED", "FABRICATED", "UNREACHABLE", "PARTIAL"}
)
_VERDICT_VERIFIED = "VERIFIED"

# The visible gap sentence a redacted claim is replaced with. Mirrors the existing gap
# language already used by contract_section_runner ("did not survive strict
# verification; curator-actionable gap.") so a redacted body reads consistently.
_GAP_REPLACEMENT = (
    "A claim previously stated here did not survive 4-role verification and was "
    "redacted; this is a curator-actionable gap."
)

# gaps.json kind for a post-gate redaction (mirrors release_policy._GAP_RESIDUAL_UNSUPPORTED
# vocabulary but is distinct so the audit trail shows the redaction happened in report.md).
GAP_KIND_REDACTED_UNSUPPORTED = "redacted_unsupported"

# POLARIS provenance token: [#ev:evidence_id:start-end].
_PROVENANCE_TOKEN_RE = re.compile(r"\[#ev:[^\]]+\]")
# Rendered numbered citation marker: [1], [12]. The final report converts each provenance
# token into one of these, so the stem matcher must ignore them on BOTH sides.
_NUMBERED_MARKER_RE = re.compile(r"\[\d+\]")
_WHITESPACE_RE = re.compile(r"\s+")


class ReportRedactionError(RuntimeError):
    """Raised when a material non-VERIFIED claim is present-but-unlocatable for a discrete
    rendered-sentence replacement. The caller MUST fail closed (do NOT ship the report).
    """


@dataclass
class RedactedClaim:
    """One claim whose verbatim sentence was removed from report.md (-> gaps.json)."""

    claim_id: str
    severity: str
    verdict: str
    claim_text: str  # the verbatim sentence (with its original provenance token)


@dataclass
class RedactionResult:
    """Outcome of reconciling report.md against the 4-role verdicts."""

    report_text: str
    redacted: list[RedactedClaim] = field(default_factory=list)
    # Material non-VERIFIED claims whose prose was already absent from the rendered report
    # (downstream dedup/repair had removed them) — recorded for the audit trail, not a leak.
    already_absent: list[str] = field(default_factory=list)

    @property
    def redacted_count(self) -> int:
        return len(self.redacted)

    def gaps_json(self) -> list[dict]:
        """Serialize the redactions as gaps.json entries (one per removed claim)."""
        return [
            {
                "ref": rc.claim_id,
                "kind": GAP_KIND_REDACTED_UNSUPPORTED,
                "severity": rc.severity,
                "note": (
                    f"claim re-judged {rc.verdict} by the 4-role seam and removed from "
                    "report.md (refuse-in-place); curator-actionable gap"
                ),
            }
            for rc in self.redacted
        ]


def _prose_stem(text: str) -> str:
    """Strip provenance tokens + numbered citation markers, leaving the bare claim prose."""
    text = _PROVENANCE_TOKEN_RE.sub("", text)
    text = _NUMBERED_MARKER_RE.sub("", text)
    return text


def _normalize(text: str) -> str:
    """Citation-insensitive, whitespace-insensitive prose for matching across the
    provenance-token -> numbered-marker render shift. Trailing punctuation stripped.
    """
    text = _prose_stem(text)
    text = _WHITESPACE_RE.sub(" ", text)
    return text.strip().rstrip(".").strip()


def _is_material_non_verified(verdict: str, severity: str, material: tuple[str, ...]) -> bool:
    # VERIFIED is not in _NON_VERIFIED_VERDICTS, so the first clause already excludes it.
    return verdict in _NON_VERIFIED_VERDICTS and severity in material


def reconcile_report_against_verdicts(
    report_text: str,
    final_verdicts: dict[str, str],
    audit_map: dict[str, dict],
    *,
    material_severities: tuple[str, ...] = DEFAULT_MATERIAL_SEVERITIES,
) -> RedactionResult:
    """Remove every material non-VERIFIED claim's verbatim sentence from ``report_text``.

    Args:
      report_text: the assembled report.md content.
      final_verdicts: claim_id -> 4-role final verdict (UNSUPPORTED/VERIFIED/...).
      audit_map: claim_id -> {"sentence": <verbatim>, "severity": <S0..S3>, ...}
                 (the persisted four_role_claim_audit.json structure).
      material_severities: which severities gate (default S0/S1/S2; S3 is never redacted).

    Returns a RedactionResult with the redacted text + per-claim records.

    Raises:
      ReportRedactionError — fail closed when a material non-VERIFIED claim's prose is
      present in the report but cannot be pinned to a discrete sentence to replace.
    """
    result = RedactionResult(report_text=report_text)
    working = report_text

    for claim_id, verdict in sorted(final_verdicts.items()):
        meta = audit_map.get(claim_id)
        if meta is None:
            # A verdict with no audit row is itself a fail-closed condition: we cannot
            # know the claim_text to redact, and a material non-VERIFIED claim might be
            # shipping. Only raise for non-VERIFIED verdicts (VERIFIED never redacts).
            if verdict != _VERDICT_VERIFIED:
                raise ReportRedactionError(
                    f"claim {claim_id} has verdict {verdict} but no audit_map row; "
                    "cannot locate its sentence to reconcile (fail-closed)."
                )
            continue

        severity = str(meta.get("severity", ""))
        if not _is_material_non_verified(verdict, severity, material_severities):
            # VERIFIED survives; S3 observe-only ships disclosure-only (scope guard).
            continue

        sentence = str(meta.get("sentence", ""))
        stem_norm = _normalize(sentence)
        if not stem_norm:
            # Defensive: an empty/whitespace-only claim sentence cannot be matched. A
            # material non-VERIFIED claim with no usable text is a fail-closed condition.
            raise ReportRedactionError(
                f"claim {claim_id} ({verdict}/{severity}) has empty claim_text; "
                "cannot reconcile (fail-closed)."
            )

        removed, working = _redact_sentence(working, stem_norm)
        if removed:
            result.redacted.append(
                RedactedClaim(
                    claim_id=claim_id,
                    severity=severity,
                    verdict=verdict,
                    claim_text=sentence,
                )
            )
            continue

        # Not redacted: either genuinely absent (SAFE) or present-but-unlocatable (FAIL).
        if stem_norm in _normalize(working):
            raise ReportRedactionError(
                f"claim {claim_id} ({verdict}/{severity}) prose is present in report.md "
                "but could not be pinned to a discrete rendered sentence for redaction; "
                "refusing to ship a partially-reconciled report (fail-closed). "
                f"prose_stem={stem_norm[:120]!r}"
            )
        result.already_absent.append(claim_id)

    result.report_text = working
    return result


def _redact_sentence(report_text: str, stem_norm: str) -> tuple[bool, str]:
    """Replace each rendered sentence whose normalized prose contains ``stem_norm`` with the
    visible gap language. Returns (redacted_any, new_text).

    Matching is done at the rendered-sentence granularity: each body line is split into
    sentence spans (each span KEEPS its own trailing citation markers), normalized (citation +
    whitespace insensitive), and a span is redacted iff its normalized prose CONTAINS the claim
    stem with sufficient coverage. Every NON-matching sentence — and its [N] markers — is
    preserved byte-for-byte, so redacting one sentence never strips citations off its VERIFIED
    neighbors (Codex iter-1 P1). Robust to the provenance-token -> [N] render shift; never
    matches across unrelated sentences.
    """
    redacted_any = False
    out_lines: list[str] = []
    for line in report_text.split("\n"):
        # Never touch headings, bibliography rows, or already-gap lines.
        stripped = line.lstrip()
        if stripped.startswith("#") or stripped.startswith("[") or not stripped:
            out_lines.append(line)
            continue
        new_line, hit = _redact_line(line, stem_norm)
        redacted_any = redacted_any or hit
        out_lines.append(new_line)
    return redacted_any, "\n".join(out_lines)


# A rendered-sentence boundary: a terminator [.!?], then any run of the sentence's OWN
# trailing citation markers ([N], optionally space-separated), then the inter-sentence
# whitespace, then the start of the next sentence. The trailing markers stay attached to the
# sentence they cite (the LEFT side) — they are NOT consumed as a separator.
#
# Codex iter-1 P1 fix: the prior `re.split(r"(?<=[.!?])(?:\[\d+\])?\s+...")` discarded the
# boundary marker (it was part of the matched, dropped separator), so redacting one sentence
# stripped the [8]/[4] citation markers off its VERIFIED neighbors on the same line and turned
# cited claims into uncited prose. The real drb_90 case: the VERIFIED 05-000 sentence renders
# "...crashes.[8]" immediately before the UNSUPPORTED 05-001 sentence — the [8] belongs to
# 05-000 and must survive redaction of 05-001.
#
# A decimal like "0.457" or "No. 157" is never a boundary: the lookahead demands whitespace +
# a sentence-start char (uppercase/quote/open-paren/hash), never a digit.
_SENTENCE_BOUNDARY_RE = re.compile(r"[.!?](?:\s*\[\d+\])*\s+(?=[A-Z\"'(#])")

# The claim stem must cover at least this fraction of a rendered sentence to redact it. Guards
# against a short non-VERIFIED claim whose normalized prose is a substring of a LONGER VERIFIED
# sentence wrongly redacting that survivor (over-redaction). Internal matching-precision floor,
# named per §9.4 (no magic numbers) — not an operator-tunable parameter.
_MIN_REDACTION_COVERAGE = 0.6


def _sentence_spans(line: str) -> list[tuple[int, int]]:
    """(start, end) spans over ``line``, one per rendered sentence, each span INCLUDING the
    sentence's trailing citation markers. The gaps between spans are pure inter-sentence
    whitespace, which the caller preserves verbatim — so a redaction never disturbs a
    neighbor's text or markers.
    """
    spans: list[tuple[int, int]] = []
    start = 0
    for m in _SENTENCE_BOUNDARY_RE.finditer(line):
        # m.group() == terminator + markers + trailing whitespace; the sentence (with its
        # markers) ends where that trailing whitespace begins.
        sentence_end = m.start() + len(m.group().rstrip())
        spans.append((start, sentence_end))
        start = m.end()  # next sentence begins after the inter-sentence whitespace
    spans.append((start, len(line)))
    return spans


def _sentence_matches_stem(sentence: str, stem_norm: str) -> bool:
    """A rendered sentence IS the rejected claim iff its normalized prose contains the claim
    stem AND the stem covers >= _MIN_REDACTION_COVERAGE of it (no short-substring false hit)."""
    sent_norm = _normalize(sentence)
    if not sent_norm or stem_norm not in sent_norm:
        return False
    return len(stem_norm) >= _MIN_REDACTION_COVERAGE * len(sent_norm)


def _redact_line(line: str, stem_norm: str) -> tuple[str, bool]:
    """Redact matching rendered sentences within a single body line, byte-preserving EVERY
    non-matching sentence (its exact text + citation markers) and all inter-sentence
    whitespace. Only the matching sentence span (including its own trailing markers) is
    replaced with the gap language.
    """
    # Fast reject: if the normalized line does not contain the stem, nothing to do.
    if stem_norm not in _normalize(line):
        return line, False

    out: list[str] = []
    cursor = 0
    hit = False
    for (start, end) in _sentence_spans(line):
        out.append(line[cursor:start])  # inter-sentence whitespace, verbatim
        sentence = line[start:end]
        if _sentence_matches_stem(sentence, stem_norm):
            out.append(_GAP_REPLACEMENT)
            hit = True
        else:
            out.append(sentence)  # byte-identical — markers intact
        cursor = end
    out.append(line[cursor:])
    return "".join(out), hit
