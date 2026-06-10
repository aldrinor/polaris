"""Post-gate report.md reconciliation against the 4-role D8 verdicts (I-beatboth-fix-000 #1171).

THE FAITHFULNESS LEAK this module closes
----------------------------------------
``scripts/run_honest_sweep_r3.py`` assembles ``report.md`` from strict_verify-KEPT
sentences (L5780) BEFORE the authoritative 4-role D8 seam runs (L6407+). The seam
re-judges every kept sentence with the stronger Mirror/Sentinel/Judge stack and can
flip a strict_verify-kept sentence to a non-VERIFIED verdict
(UNSUPPORTED / FABRICATED / UNREACHABLE / PARTIAL at ANY severity). Today the runner
consumes that verdict ONLY as a manifest flag (``release_allowed=False`` +
``needs_rewrite``); it NEVER reconciles the assembled ``report.md`` against the
verdicts. So a sentence the strongest verifier rejected still ships as asserted prose.

drb_90 proof: ``needs_rewrite`` carried 7 material UNSUPPORTED claim_ids and at least
six of those sentences (e.g. the "$27,874 per violation" penalty figure, the
"UN Regulation No. 157 — ALKS" instrument line) were physically present in the shipped
``report.md`` body and carried-up Key Findings.

WHAT THIS HELPER DOES (fail-closed)
-----------------------------------
For every claim whose 4-role ``final_verdict`` is non-VERIFIED, it locates the
claim's verbatim sentence in the rendered ``report.md`` and REPLACES it with the
existing visible gap language ("did not survive verification; curator-actionable gap").
Redaction is SEVERITY-INDEPENDENT (I-faith-003 #1174): a claim is redacted iff its verdict
is non-VERIFIED, at ANY severity. S3 "observe-only" governs the release LATCH only
(release_policy.py) — it never exempts an unverified claim from redaction.

It is REFUSE-IN-PLACE, not a generative rewrite: no new spend, no new claims. The
redaction IS the "one rewrite/refuse-in-place attempt" the D8 policy docstring designs
but the runner never wired.

The mapping is NOT 1:1 with strict_verify-kept (run_honest_sweep_r3.py:5660-5669 in-tree
caveat: downstream dedup/repair passes mutate the body). THREE TIERS of locating the prose
(I-redact-001 #1181 — high-recall detection, high-precision action):
  * TIER 1 (precise, single span): the claim's prose IS one discrete rendered sentence
    span (coverage >= ``_MIN_REDACTION_COVERAGE``) -> redact exactly that span, leaving
    every VERIFIED neighbor sentence and its [N] markers byte-for-byte (the leak fix).
  * TIER 2 (minimal containing unit): the claim's normalized prose is unambiguously
    PRESENT but it does not cover one span at the coverage floor — because a boundary
    under-split merged it with a VERIFIED neighbor, OR it straddles >=2 rendered spans.
    Redact the SMALLEST set of consecutive spans (or, only if no span set bounds it, the
    body line) whose concatenation contains the stem — over-redact SAFELY rather than
    abort (issue acceptance 1+2). The cross-line projection makes table/line-join
    rendering visible so this is never a silent ``already_absent``.
  * TIER 3 (genuinely absent): the claim's prose is genuinely ABSENT from the rendered
    report (downstream dedup/repair removed it) -> already not shipped; record
    ``already_absent`` and ship nothing extra (the SAFE state).
FAIL-CLOSED contract (I-redact-001 #1181): the helper RAISES ``ReportRedactionError`` ONLY
when a material non-VERIFIED claim's normalized prose is genuinely ABSENT from the normalized
report yet a real inconsistency demands a fail-closed abort — i.e. neither TIER-1 nor TIER-2
can bound the prose AND the prose is not cleanly absent. A merely hard-to-pin-to-one-sentence
claim is redacted via TIER 2, NOT aborted. The boundary hardening (``_SENTENCE_BOUNDARY_RE``,
I-redact-001) splits ``...risk[1] Cereal...`` / ``...adherence.[16] 87.3%...`` so the common
case resolves at TIER 1; TIER 2 is the defense-in-depth for any future under-split shape.

MULTI-OCCURRENCE (I-redact-001 #1181, Codex iter-1 P1-1): the same non-VERIFIED stem can appear
more than once (e.g. once cleanly + once in an under-split merge). The tiered redaction LOOPS
per claim until the stem is absent from the line-join-normalized whole body (no occurrence left)
or no tier makes further progress (fail-closed) — so a second occurrence can never leak. The
claim is recorded in ``redacted`` exactly ONCE regardless of how many physical spans were removed.

Pure function (string ops only; no network, no I/O). The CALLER reads/writes report.md.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# REDACTION IS SEVERITY-INDEPENDENT (I-faith-003 #1174). Any claim the 4-role seam did NOT
# mark VERIFIED — PARTIAL/UNSUPPORTED/FABRICATED/UNREACHABLE — must not ship as asserted prose,
# regardless of severity. Severity ("S0".."S3") governs the RELEASE LATCH in release_policy.py
# (a non-required-entity S3 claim does not BLOCK release), NEVER this redaction path: previously
# the S3 "observe-only" scope guard wrongly let 26 UNSUPPORTED claims (incl. clinical-safety
# guidance) ship across the 5 beat-both questions (BB5-F01). VERIFIED survives; every other
# verdict is a leak if it ships as prose.
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


def reconcile_report_against_verdicts(
    report_text: str,
    final_verdicts: dict[str, str],
    audit_map: dict[str, dict],
) -> RedactionResult:
    """Remove every non-VERIFIED claim's verbatim sentence from ``report_text``.

    Redaction is severity-independent (I-faith-003 #1174): a claim is redacted iff its
    4-role verdict is not VERIFIED, at ANY severity (S0..S3). Severity governs the release
    latch in release_policy.py, never this redaction path.

    Args:
      report_text: the assembled report.md content.
      final_verdicts: claim_id -> 4-role final verdict (UNSUPPORTED/VERIFIED/...).
      audit_map: claim_id -> {"sentence": <verbatim>, "severity": <S0..S3>, ...}
                 (the persisted four_role_claim_audit.json structure).

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
        if verdict == _VERDICT_VERIFIED:
            # VERIFIED survives at ANY severity. Every non-VERIFIED verdict is redacted
            # regardless of severity (I-faith-003 #1174): S3 "observe-only" governs the
            # release LATCH (release_policy.py), never this redaction path.
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

        # MULTI-OCCURRENCE LOOP (I-redact-001 #1181, Codex iter-1 P1-1): a non-VERIFIED stem can
        # appear MORE THAN ONCE in the body — e.g. once cleanly (TIER 1 catches it) and once in a
        # boundary-under-split span (only TIER 2 catches it). The prior single-pass logic marked
        # the claim handled after the FIRST successful removal and `continue`d, leaving the second
        # occurrence in result.report_text — a leak. We now loop the tiered redaction until the
        # stem is ABSENT from the line-join-normalized whole-body projection (no occurrence left)
        # OR no tier can make further progress (-> fail-closed). The loop terminates because each
        # successful removal replaces the matched prose with ``_GAP_REPLACEMENT`` (which cannot
        # re-match the stem), so occurrences are consumed monotonically.
        redacted_any_for_claim = False
        while _prose_present(working, stem_norm):
            # TIER 1 — precise single-span redaction (coverage floor protects VERIFIED neighbors).
            # One pass clears EVERY clean (pin-at-floor) occurrence across all lines at once.
            removed, working = _redact_sentence(working, stem_norm)
            if removed:
                redacted_any_for_claim = True
                continue

            # TIER 1 made no progress this pass, but the prose IS still present (line-join
            # projection): it did not pin to one span at the coverage floor (a boundary
            # under-split merged it with a VERIFIED neighbor, OR it straddles spans). TIER 2 —
            # redact the minimal CONTAINING unit, over-redacting SAFELY rather than aborting a
            # present-but-hard-to-pin claim (#1181). TIER 2 removes ONE under-split unit per pass;
            # the loop re-checks presence and keeps going for any further occurrence.
            removed, working = _redact_minimal_containing_unit(working, stem_norm)
            if removed:
                redacted_any_for_claim = True
                continue

            # FAIL-CLOSED: the prose registers as present in the line-join projection (e.g. it
            # spans a heading/bibliography line the redactor must not touch, or its alignment is
            # unbounded across non-adjacent units) but NEITHER tier could bound it to a redactable
            # unit without nuking a forbidden line. A real inconsistency — refuse to ship a partial
            # report (#1174). Raising here (not after the loop) means we never spin: no progress +
            # still present == abort.
            raise ReportRedactionError(
                f"claim {claim_id} ({verdict}/{severity}) prose is present in report.md "
                "but could not be bounded to any redactable unit (span set or body line); "
                "refusing to ship a partially-reconciled report (fail-closed). "
                f"prose_stem={stem_norm[:120]!r}"
            )

        # Record the claim ONCE after the loop (Codex iter-1 P1-1: appending per removal would
        # double-count a claim that occurred twice and inflate redacted_count). If the loop body
        # never ran, the prose was genuinely ABSENT from the start — the SAFE state (TIER 3).
        if redacted_any_for_claim:
            result.redacted.append(
                RedactedClaim(
                    claim_id=claim_id,
                    severity=severity,
                    verdict=verdict,
                    claim_text=sentence,
                )
            )
        else:
            result.already_absent.append(claim_id)  # TIER 3 — genuinely absent, ship nothing

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
# I-redact-001 #1181 — three ALTERNATION ARMS so a real boundary is not under-split (the
# under-split merged a non-VERIFIED sentence with a VERIFIED neighbor into one over-long span,
# dropping coverage below the floor and forcing a whole-report abort). Each arm still demands
# inter-sentence whitespace + a sentence-start, so decimals/abbreviations never become a split:
#   ARM 1 (terminator, sentence-start char): "...crashes.[8] The..." — the original behavior.
#   ARM 2 (terminator + >=1 marker, digit-start next): "...adherence.[16] 87.3% of..." — the
#          next sentence begins with a digit (defeating ARM 1's [A-Z"'(#] lookahead). REQUIRES
#          at least one [N] marker between the period and the digit, so a bare decimal
#          "0.90 (0.83 to 0.97) was found." (period, space, digit, NO marker) never matches.
#   ARM 3 (>=1 marker as terminator, NO preceding period): "...risk[1] Cereal...",
#          "...recovery[17][22] Legal..." — the renderer emitted the citation marker(s) with no
#          terminal period before them; the marker(s) ARE the boundary. The marker stays with
#          the LEFT (cited) sentence (it is m.start()-anchored, then rstrip-included in the span),
#          so a VERIFIED neighbor keeps its [N] byte-for-byte (the Codex iter-1 P1 invariant).
#          Codex iter-1 P2: ARM 3 is WORD-ANCHORED — the marker run must immediately follow a
#          word character ``(?<=\w)`` (NO whitespace between the sentence-final word and its
#          marker), so it fires only on a plausible sentence end where the renderer dropped the
#          terminal period ("risk[1]", "recovery[17][22]"). A MID-sentence inline citation —
#          "...as shown [5] In vivo..." or "the [5] Group reported..." — has WHITESPACE before
#          the bracket, so ``(?<=\w)`` rejects it and the inline-cited sentence stays intact (no
#          false split -> no over-redaction of a VERIFIED sentence). This only ever causes an
#          UNDER-split, which TIER 2 then bounds safely; it can never over-split a survivor.
# A decimal like "0.457" or "No. 157" or "U.S." is never a boundary: ARM 1/2 require whitespace
# before the next char and ARM 2 requires an intervening [N] marker; "U.S. products" splits only
# if "products" were uppercase (it is not), and "No. 157" has no marker so ARM 2 cannot fire.
_SENTENCE_BOUNDARY_RE = re.compile(
    r"(?:"
    r"[.!?](?:\s*\[\d+\])*\s+(?=[A-Z\"'(#])"   # ARM 1: terminator -> sentence-start char
    r"|[.!?](?:\s*\[\d+\])+\s+(?=\d)"           # ARM 2: terminator + marker -> digit-start
    r"|(?<=\w)(?:\[\d+\])+\s+(?=[A-Z\"'(#0-9])"  # ARM 3: WORD-ATTACHED marker-as-terminator, no period
    r")"
)

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


def _is_redactable_body_line(line: str) -> bool:
    """A body line the redactor is allowed to rewrite: NOT a heading (#…), a bibliography /
    already-gap row ([…), or blank. Mirrors the skip in ``_redact_sentence`` so TIER-2 honors
    the exact same no-touch set (a claim that exists ONLY inside a heading stays a fail-closed
    inconsistency, not a TIER-2 redaction — preserving the present-but-unlocatable contract).
    """
    stripped = line.lstrip()
    return bool(stripped) and not stripped.startswith("#") and not stripped.startswith("[")


def _prose_present(report_text: str, stem_norm: str) -> bool:
    """High-RECALL presence detector over a LINE-JOIN-NORMALIZED projection of the whole body
    (research practice: cross-line / table rendering is a blind spot — never silently treat a
    line-straddling claim as already-absent). Returns True iff the claim stem is normalized-
    present either within one body line OR across the join of consecutive redactable body lines.

    Recall here only guards against a FALSE ``already_absent`` (a leak); the high-PRECISION
    decision of WHICH unit to remove stays in ``_redact_minimal_containing_unit`` (exact
    normalized containment + the coverage floor), so this projection never itself redacts.
    """
    if stem_norm in _normalize(report_text):
        return True
    # Cross-line projection: join only the redactable body lines (skip headings / bib / blanks),
    # normalized, and look for the stem straddling a soft line break.
    body = " ".join(
        line for line in report_text.split("\n") if _is_redactable_body_line(line)
    )
    return stem_norm in _normalize(body)


def _redact_minimal_containing_unit(report_text: str, stem_norm: str) -> tuple[bool, str]:
    """TIER-2 fallback (#1181): the stem is present but did NOT pin to one span at the coverage
    floor. Remove the SMALLEST containing unit, over-redacting SAFELY rather than aborting:

      1. Within a single redactable body line, find the smallest set of CONSECUTIVE spans whose
         concatenation (normalized) contains the stem, and replace exactly that span set with one
         gap sentence — preserving every OTHER span (and its [N] markers) and all inter-span
         whitespace byte-for-byte. This handles both the boundary-under-split residue and a TRUE
         multi-span straddle (issue acceptance 1+2) with the same walk.
      2. If no within-line consecutive-span set bounds the stem (it straddles a soft line break),
         replace the smallest run of consecutive redactable body lines whose join contains the
         stem with one gap line — the coarsest safe unit.

    Returns (redacted_any, new_text). Returns (False, unchanged) iff the stem cannot be bounded
    by any redactable unit (the caller then fails closed). NEVER touches a heading/bib line.
    """
    lines = report_text.split("\n")

    # ---- 1) within-line minimal consecutive-span set -------------------------------------
    for idx, line in enumerate(lines):
        if not _is_redactable_body_line(line):
            continue
        if stem_norm not in _normalize(line):
            continue
        spans = _sentence_spans(line)
        span_set = _minimal_consecutive_span_set(line, spans, stem_norm)
        if span_set is not None:
            lo, hi = span_set  # inclusive span indices
            start = spans[lo][0]
            end = spans[hi][1]
            new_line = line[:start] + _GAP_REPLACEMENT + line[end:]
            lines[idx] = new_line
            return True, "\n".join(lines)

    # ---- 2) cross-line: smallest consecutive redactable-body-line run --------------------
    redactable_idx = [i for i, ln in enumerate(lines) if _is_redactable_body_line(lines[i])]
    for span_len in range(1, len(redactable_idx) + 1):
        for offset in range(0, len(redactable_idx) - span_len + 1):
            window = redactable_idx[offset : offset + span_len]
            # The window must be CONTIGUOUS in the body-line sequence to be one rendered unit.
            if window[-1] - window[0] != span_len - 1:
                continue
            joined = " ".join(lines[i] for i in window)
            if stem_norm in _normalize(joined):
                first = window[0]
                # Replace the first line of the run with the gap; blank the remaining lines so the
                # leak prose is fully removed while preserving the line count (no structural churn).
                lines[first] = _GAP_REPLACEMENT
                for i in window[1:]:
                    lines[i] = ""
                return True, "\n".join(lines)

    return False, report_text


def _minimal_consecutive_span_set(
    line: str, spans: list[tuple[int, int]], stem_norm: str
) -> tuple[int, int] | None:
    """Smallest (lo, hi) inclusive index window over ``spans`` whose concatenated source text is
    normalized-containing ``stem_norm``. Grows the window by length so the FIRST hit is minimal;
    prefers the smallest unit (precision: do not nuke a section when a span-pair suffices)."""
    n = len(spans)
    for window in range(1, n + 1):
        for lo in range(0, n - window + 1):
            hi = lo + window - 1
            seg = line[spans[lo][0] : spans[hi][1]]
            if stem_norm in _normalize(seg):
                return (lo, hi)
    return None
