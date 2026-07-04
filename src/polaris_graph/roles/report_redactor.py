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

import os
import re
from dataclasses import dataclass, field

# WS-5 FIX-b (I-deepfix-001): the effect-size conditional/threshold guard lives in the additive
# overstatement_guard leaf module (os/re only — no polaris imports, so no cycle). Imported lazily
# would also work; a module-level import is safe and keeps the annotate path self-describing.
from src.polaris_graph.generator.overstatement_guard import (
    effect_size_conditional_reason,
    figure_consistency_annotate_enabled,
)

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
# I-perm-005 (#1199): the annotator's appended confidence label. Stripped in the stem so an
# already-annotated sentence still matches its claim stem at the coverage floor (annotate is
# idempotent). The redactor never sees this marker (annotate XOR reconcile per PG_ALWAYS_RELEASE),
# so stripping it is a no-op on the redaction path.
_CONFIDENCE_MARKER_RE = re.compile(r"\s*\[confidence:[^\]]*\]")
_WHITESPACE_RE = re.compile(r"\s+")
# WS-5 FIX-a (I-deepfix-001): the provenance token carried by a claim's AUDIT sentence, used to
# re-key the confidence annotation on SPAN identity so a flagged claim's byte/figure-twin (bound
# to a DIFFERENT claim_id) inherits the caveat. Token form: [#ev:<evidence_id>:<start>-<end>].
_SPAN_IDENTITY_RE = re.compile(r"\[#ev:([^:\]]+):(\d+)-(\d+)\]")
# A numeric figure (integer or decimal) — links a flagged claim to a VERIFIED twin that re-lifts
# the SAME figure from the SAME cited span (surgical: same-span prose that repeats no flagged
# figure is NOT caveated).
_FIGURE_TOKEN_RE = re.compile(r"\d+(?:\.\d+)?")
# F10(b) (I-arch-004 A3): interior whitespace-before-punctuation, collapsed in
# _normalize so the redaction stem matches the SHIPPED form. The resolver runs
# `re.sub(r"\s+([.!?,;])", r"\1", ...)` on every sentence before it renders, so
# `word .` in the audit_map sentence ships as `word.`; the redactor must apply
# the same collapse or the stem misses the collapsed sentence. Same punctuation
# set as the resolver (provenance_generator).
_INTERIOR_SPACE_BEFORE_PUNCT_RE = re.compile(r"\s+([.!?,;])")

# A4 (I-deepfix-001) — the inline attribution-origin caveat marker appended to a
# mis-attributed sentence in the VISIBLE report (see ``annotate_report_attribution_origin``
# below). It is a bracketed disclosure with no terminal period (so a sentence splitter never
# treats it as a new sentence), form: ``[attribution unverified — the cited source does not
# appear to be <ACTOR>; ...]``. Stripped inside ``_normalize`` so a caveated sentence still
# matches its own claim stem at the coverage floor for the redactor / annotator, both of which
# run AFTER the render-seam caveat pass. Additive: a sentence WITHOUT the caveat is byte-unchanged.
_ATTRIBUTION_CAVEAT_RE = re.compile(r"\s*\[attribution unverified[^\]]*\]")


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
    # I-wire-015 #1337 R5: "claim" = removed at span/line granularity (TIER 1/2). "section" = the
    # claim was un-boundable to a span/line, so its whole markdown section was withheld (TIER 4)
    # rather than aborting the entire report. Either way the unsupported claim NEVER ships.
    redaction_scope: str = "claim"


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
                # I-wire-015 #1337 R5: machine-readable scope ("claim" = span/line redaction;
                # "section" = the whole section was withheld because the claim was un-boundable to a
                # smaller unit). Lets a consumer count/triage section-level withholds programmatically.
                "redaction_scope": rc.redaction_scope,
                "note": (
                    f"claim re-judged {rc.verdict} by the 4-role seam and removed from "
                    "report.md (refuse-in-place); curator-actionable gap"
                    + (
                        "; SECTION withheld (claim was un-boundable to a span/line — "
                        "the whole section was conservatively withheld, not the whole report)"
                        if rc.redaction_scope == "section" else ""
                    )
                ),
            }
            for rc in self.redacted
        ]


def _prose_stem(text: str) -> str:
    """Strip provenance tokens + numbered citation markers, leaving the bare claim prose.

    (The annotator's confidence marker is stripped LOCALLY in the annotator path only — never here —
    so the shared redaction normalization is byte-unchanged; Codex slice-2 P0-2.)"""
    text = _PROVENANCE_TOKEN_RE.sub("", text)
    text = _NUMBERED_MARKER_RE.sub("", text)
    return text


def _normalize(text: str) -> str:
    """Citation-insensitive, whitespace-insensitive prose for matching across the
    provenance-token -> numbered-marker render shift. Trailing punctuation stripped.

    F10(b) (I-arch-004 A3): ALSO collapse interior whitespace-BEFORE-punctuation
    (``word .`` -> ``word.``), mirroring the resolver's own normalization
    (provenance_generator: ``re.sub(r"\\s+([.!?,;])", r"\\1", stripped)``). The
    audit_map sentence (the pre-resolve ``sv.sentence``) can carry ``word .``
    interior spacing that the resolver collapses before the sentence SHIPS as
    ``word.``; without this collapse the redaction stem would not match the
    shipped form and a present-but-collapsed non-VERIFIED claim was wrongly
    recorded ``already_absent`` (a silent leak — 07-001 / 06-006 interior-collapse
    case). This applies the SAME collapse to both stem and rendered side, so the
    match is consistent and idempotent; it never relaxes a match, only adds one.
    """
    text = _prose_stem(text)
    # A4 (I-deepfix-001): also strip the inline attribution-origin caveat so a sentence that
    # received the visible caveat still matches its claim stem at the coverage floor for the
    # redactor / annotator (both run AFTER the render-seam caveat pass). Additive — a sentence
    # without the caveat is byte-unchanged; nothing else in the pipeline emits this marker.
    text = _ATTRIBUTION_CAVEAT_RE.sub("", text)
    text = _WHITESPACE_RE.sub(" ", text)
    text = _INTERIOR_SPACE_BEFORE_PUNCT_RE.sub(r"\1", text)
    return text.strip().rstrip(".").strip()


# ─────────────────────────────────────────────────────────────────────────────
# WS-5 (I-deepfix-001) — figure-consistency re-key helpers (annotate path only)
# ─────────────────────────────────────────────────────────────────────────────
def _span_identities(sentence: str) -> set[tuple[str, int, int]]:
    """The (evidence_id, start, end) provenance tuples a claim's AUDIT sentence carries."""
    return {
        (m.group(1), int(m.group(2)), int(m.group(3)))
        for m in _SPAN_IDENTITY_RE.finditer(sentence or "")
    }


def _figure_tokens(sentence: str) -> set[str]:
    """Numeric figures in a claim's prose, EXCLUDING the digits inside its provenance token /
    numbered citation markers (a span offset like ``0-800`` is not a claimed figure)."""
    prose = _SPAN_IDENTITY_RE.sub("", sentence or "")
    prose = _NUMBERED_MARKER_RE.sub("", prose)
    return set(_FIGURE_TOKEN_RE.findall(prose))


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
        section_withheld_for_claim = False  # I-wire-015 #1337 R5: a TIER-4 section withhold fired
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

            # TIER 4 (I-wire-015 #1337 R5) — SECTION-level bounded withhold. The stem is present
            # (line-join projection) but neither a span (TIER 1) nor a body-line / line-run (TIER 2)
            # could bound it without touching a forbidden heading/bib line. Rather than abort the
            # WHOLE report (the legacy fail-closed below — one un-boundable chrome fragment then
            # collapses an otherwise-good report, the #1337 reconfirm3 failure), withhold ONLY the
            # markdown SECTION whose body contains the stem. The unsupported claim is FULLY removed
            # (faithfulness preserved — it NEVER ships); only that one section's coverage is lost
            # (disclosed in gaps.json as redaction_scope="section"); every other section survives.
            # This is the next-coarser bounded unit ABOVE TIER-2's line-run, so it only fires when
            # TIER-2 already could not bound the stem. Default-ON; env-reversible to the legacy abort.
            if _section_level_fallback_enabled():
                removed, working = _redact_containing_section(working, stem_norm)
                if removed:
                    redacted_any_for_claim = True
                    section_withheld_for_claim = True
                    continue

            # FAIL-CLOSED (true last resort): the prose registers as present in the line-join
            # projection but could not be bounded to a span, a body line/line-run, OR a section
            # (e.g. it exists ONLY inside a heading/bibliography line, or straddles a section
            # boundary). A real inconsistency — refuse to ship a partial report (#1174); never
            # present an unsupported claim as fact. Raising here (not after the loop) means we never
            # spin: no progress + still present == abort.
            raise ReportRedactionError(
                f"claim {claim_id} ({verdict}/{severity}) prose is present in report.md "
                "but could not be bounded to any redactable unit (span set, body line, or section); "
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
                    redaction_scope=("section" if section_withheld_for_claim else "claim"),
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
# A4 (I-deepfix-001) boundary-safety (Codex P1): the inline attribution-origin caveat
# (``annotate_report_attribution_origin`` below) is appended AFTER a sentence's terminator +
# citation markers and carries NO terminator of its own. Without help the splitter could not find
# the boundary AFTER the caveat, so the caveated sentence and the NEXT grounded sentence would fuse
# into one span and a later D8 redaction could over-remove the grounded neighbor. Each arm therefore
# consumes an OPTIONAL trailing attribution caveat as attached material of the PRECEDING sentence, so
# the split lands AFTER the caveat and the next sentence stays a clean, separate span. Purely
# additive: the optional group matches empty for caveat-free text, so a report that carries no
# attribution caveat segments byte-identically to before.
_ATTRIBUTION_CAVEAT_TRAILER = r"(?:\s*\[attribution unverified[^\]]*\])?"
_SENTENCE_BOUNDARY_RE = re.compile(
    r"(?:"
    r"[.!?](?:\s*\[\d+\])*" + _ATTRIBUTION_CAVEAT_TRAILER + r"\s+(?=[A-Z\"'(#])"   # ARM 1: terminator -> sentence-start char
    r"|[.!?](?:\s*\[\d+\])+" + _ATTRIBUTION_CAVEAT_TRAILER + r"\s+(?=\d)"           # ARM 2: terminator + marker -> digit-start
    r"|(?<=\w)(?:\[\d+\])+" + _ATTRIBUTION_CAVEAT_TRAILER + r"\s+(?=[A-Z\"'(#0-9])"  # ARM 3: WORD-ATTACHED marker-as-terminator, no period
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
    if not stripped or stripped.startswith("#"):
        return False
    # I-wire-015 #1337: a genuine bibliography reference row starts with a SINGLE citation marker
    # then the reference ("[12] Autor, D. (2015). ...") and must NOT be redacted. But a BODY line can
    # begin with the WRAPPED trailing citations of the previous sentence ("[71][5][7][6] Further
    # research is needed..." — 2+ consecutive leading markers) — that is CONTENT, not a reference, and
    # MUST stay redactable, else an unsupported claim rendered on it cannot be bounded by ANY tier and
    # collapses the whole report (the #1337 reconfirm3 failure: the un-VERIFIED claim 05-041 rendered
    # on a "[71][5][7][6] ..." line). So only a SINGLE leading marker (a real reference row) is
    # protected; 2+ consecutive leading markers mark a redactable wrapped-body line.
    if stripped.startswith("["):
        return bool(re.match(r"(?:\[\d+\]){2,}", stripped))
    return True


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


def _section_level_fallback_enabled() -> bool:
    """I-wire-015 #1337 R5: gate for the TIER-4 SECTION-level withhold (DEFAULT-ON). ON => an
    unsupported claim that neither TIER-1 (span) nor TIER-2 (line/line-run) can bound withholds only
    its markdown section instead of aborting the whole report. OFF => reverts to the legacy
    whole-report fail-closed abort. Faithfulness is IDENTICAL either way — the unsupported claim
    NEVER ships; the flag only chooses the blast radius (one section vs the entire report)."""
    return os.getenv("PG_REDACT_SECTION_LEVEL_FALLBACK", "1").strip().lower() not in (
        "", "0", "false", "off", "no",
    )


def _redact_containing_section(report_text: str, stem_norm: str) -> tuple[bool, str]:
    """TIER-4 (#1337 R5): the smallest BOUNDED unit above a body-line run — the markdown SECTION.
    Used ONLY after TIER-1 (span) and TIER-2 (line / line-run) both fail to bound a PRESENT
    unsupported claim (e.g. it straddles a heading the redactor must not touch, or non-adjacent
    units). Find the section — the run of lines from one ``#``-heading up to the next heading or
    EOF — whose redactable BODY lines' join contains the stem, and blank that section's body (its
    first redactable body line -> the gap sentence, the rest -> "" to preserve the line count),
    keeping the heading. The unsupported claim is FULLY removed (faithfulness preserved — it NEVER
    ships); only that one section's coverage is lost (disclosed). Returns (False, unchanged) iff no
    section BODY contains the stem (it lives only in a heading/bib line, or straddles a section
    boundary) — the caller then fails closed (the true last resort). NEVER touches a heading/bib
    line's text; NEVER ships the claim.
    """
    lines = report_text.split("\n")
    heading_positions = [i for i, ln in enumerate(lines) if ln.lstrip().startswith("#")]
    if not heading_positions:
        return False, report_text
    for k, h in enumerate(heading_positions):
        body_start = h + 1
        body_end = heading_positions[k + 1] if k + 1 < len(heading_positions) else len(lines)
        redactable_positions = [
            p for p in range(body_start, body_end) if _is_redactable_body_line(lines[p])
        ]
        if not redactable_positions:
            continue
        joined = " ".join(lines[p] for p in redactable_positions)
        if stem_norm in _normalize(joined):
            # Blank the whole section body: first redactable line -> the visible gap sentence; the
            # remaining redactable lines -> "" (preserve line count, no structural churn). Headings,
            # bibliography rows, and blank lines in the section are untouched.
            lines[redactable_positions[0]] = _GAP_REPLACEMENT
            for p in redactable_positions[1:]:
                lines[p] = ""
            return True, "\n".join(lines)
    return False, report_text


# ─────────────────────────────────────────────────────────────────────────────
# I-perm-005 (#1199) — ANNOTATE (keep + label), the always-release sibling of REDACT
# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class AnnotatedClaim:
    """One non-VERIFIED claim KEPT in report.md with an appended confidence marker."""

    claim_id: str
    severity: str
    verdict: str
    marker: str


@dataclass
class AnnotationResult:
    """Outcome of annotating report.md against the 4-role verdicts (keep + label)."""

    report_text: str
    annotated: list["AnnotatedClaim"] = field(default_factory=list)
    already_absent: list[str] = field(default_factory=list)

    @property
    def annotated_count(self) -> int:
        return len(self.annotated)


def _claim_fully_pinnable(working: str, stem_norm: str) -> bool:
    """True iff EVERY occurrence of ``stem_norm`` is a clean TIER-1 single-sentence span the annotator
    can label — checked on the MARKER-STRIPPED text using the REDACTOR's own TIER-1 locate.

    Completeness guard for the annotator (Codex slice-2 P0-1/P0-2 + iter-2): the appended confidence
    marker (no terminator) can ALTER ``_sentence_spans`` segmentation, so any post-marker scan is
    unreliable. Instead this strips ALL confidence markers FIRST (clean segmentation, immune to the
    marker even across claims; LOCAL strip — shared `_prose_stem` untouched), then runs the exact
    same TIER-1 removal the redactor uses (``_redact_sentence``): if removing every TIER-1-pinnable
    occurrence leaves the stem STILL present in the line-join projection, a non-TIER-1 occurrence
    (a boundary-straddle / under-split) remains that the per-line annotator CANNOT cleanly label ->
    fail closed. This is the SAME notion of "pinnable" the annotate pass acts on.
    """
    stripped = _CONFIDENCE_MARKER_RE.sub("", working)
    _removed, after = _redact_sentence(stripped, stem_norm)
    return not _prose_present(after, stem_norm)


def annotate_report_against_verdicts(
    report_text: str,
    final_verdicts: dict[str, str],
    audit_map: dict[str, dict],
    marker_by_claim: dict[str, str],
    *,
    span_text_by_claim: dict[str, str] | None = None,
) -> AnnotationResult:
    """KEEP every non-VERIFIED claim's sentence in ``report_text`` and APPEND its confidence marker.

    The always-release (I-perm-001) counterpart of ``reconcile_report_against_verdicts``: under the
    reframe a non-VERIFIED claim is shown LABELED (user judges) instead of DELETED. Severity-
    independent, like the redactor. ``marker_by_claim[claim_id]`` is the inline marker the caller
    computed from ``claim_labeler`` (a non-VERIFIED claim is always low / no-source-found — never
    high). A non-VERIFIED claim with no marker falls back to a generic low marker (never silently
    unlabeled).

    Single-pass per claim (appending a marker does not remove the stem, so there is no
    multi-occurrence loop): every matching sentence span across the body is labeled exactly once.

    Fail-closed (same safety contract as the redactor): a material non-VERIFIED claim whose prose is
    PRESENT but cannot be pinned to a discrete rendered sentence raises ``ReportRedactionError`` — we
    never ship a non-VERIFIED claim as bare unlabeled prose.

    WS-5 FIGURE-CONSISTENCY re-key (I-deepfix-001, default ON via ``PG_FIGURE_CONSISTENCY_ANNOTATE``):
    the low-confidence label used to key on ``claim_id`` alone, so a flagged claim's byte/figure-twin
    bound to a DIFFERENT (VERIFIED) claim_id — e.g. the Eloundou "46%" re-lifted verbatim into the
    Conclusion — shipped CLEAN with the caveat stripped. Two ADVISORY re-keys now make every twin
    inherit the caveat:
      * FIX-a: a VERIFIED claim that shares BOTH a span-identity tuple (evidence_id,start,end) AND a
        numeric figure with a flagged claim inherits that flagged sibling's marker.
      * FIX-b: when ``span_text_by_claim`` is supplied, a claim that re-lifts a span number while
        dropping the span's governing conditional/threshold antecedent (``effect_size_conditional_reason``)
        inherits a generic low marker.
    Advisory claims are BEST-EFFORT and NEVER fail-closed: labelling a twin only ADDS a caveat (§-1.3),
    so an absent / unpinnable twin is simply not labelled (its absence is not a leak — the twin is
    VERIFIED and already ships). ``PG_FIGURE_CONSISTENCY_ANNOTATE=0`` (or ``span_text_by_claim=None``
    for FIX-b) restores byte-identical claim_id-only behaviour. This never changes a verdict, never
    widens a span, never removes a caveat.
    """
    # IDEMPOTENCE (Codex slice-2 iter-4 P1): strip any PRE-EXISTING confidence markers up front so a
    # re-run over already-annotated output segments cleanly (the no-terminator marker would otherwise
    # collapse two same-line sentences into one span). Markers are deterministic, so stripping then
    # re-labeling reproduces them exactly; a fresh report has none, so this is a byte no-op there.
    report_text = _CONFIDENCE_MARKER_RE.sub("", report_text)

    # Collect every non-VERIFIED claim (validate + pinnability), THEN label in a SINGLE pass over the
    # ORIGINAL report (Codex slice-2 iter-3 P0): sequentially mutating `working` per claim let claim
    # A's appended marker (no terminator) perturb claim B's same-line segmentation, leaking B
    # unlabeled. Computing all sentence spans ONCE off the unmutated text removes that coupling.
    claims: list[tuple[str, str, str, str, str]] = []  # (claim_id, verdict, severity, stem, marker)
    already_absent: list[str] = []
    for claim_id, verdict in sorted(final_verdicts.items()):
        if verdict == _VERDICT_VERIFIED:
            continue
        meta = audit_map.get(claim_id)
        if meta is None:
            raise ReportRedactionError(
                f"claim {claim_id} has verdict {verdict} but no audit_map row; "
                "cannot locate its sentence to annotate (fail-closed)."
            )
        severity = str(meta.get("severity", ""))
        stem_norm = _normalize(str(meta.get("sentence", "")))
        if not stem_norm:
            raise ReportRedactionError(
                f"claim {claim_id} ({verdict}/{severity}) has empty claim_text; "
                "cannot annotate (fail-closed)."
            )
        if not _prose_present(report_text, stem_norm):
            already_absent.append(claim_id)  # downstream dedup removed it; nothing to label
            continue
        # COMPLETENESS: every occurrence must be a clean TIER-1 single sentence (checked on the
        # marker-stripped text via the redactor's TIER-1 — immune to the marker). A straddle /
        # under-split occurrence the per-line pass cannot pin -> fail closed (never ship unlabeled).
        if not _claim_fully_pinnable(report_text, stem_norm):
            raise ReportRedactionError(
                f"claim {claim_id} ({verdict}/{severity}) prose is present in report.md but at least "
                "one occurrence could not be pinned to a discrete sentence to annotate (fail-closed)."
            )
        marker = marker_by_claim.get(claim_id) or _DEFAULT_LOW_MARKER
        claims.append((claim_id, verdict, severity, stem_norm, marker))

    # WS-5 (I-deepfix-001): collect figure-consistency ADVISORY claims (default ON). These are
    # BEST-EFFORT twins of a flagged claim that inherit its caveat; unlike the mandatory
    # non-VERIFIED claims above they NEVER fail-closed (labelling a twin only ADDS a caveat, so an
    # absent / unpinnable twin is simply not labelled). Ordered AFTER the mandatory claims so a
    # sentence that IS a genuine non-VERIFIED claim keeps its own marker (first-match wins).
    advisory = _collect_figure_consistency_claims(
        report_text,
        final_verdicts,
        audit_map,
        marker_by_claim,
        span_text_by_claim,
        already_collected={c[0] for c in claims},
    )

    # SINGLE labeling pass: spans come from the ORIGINAL line (never a marker-mutated one), so two
    # same-line claims each get their own marker. Each sentence is matched marker-stripped (idempotent)
    # and labeled once with the FIRST claim it matches. Mandatory claims precede advisory twins.
    label_targets = claims + advisory
    labeled: set[str] = set()
    new_lines: list[str] = []
    for line in report_text.split("\n"):
        if not _is_redactable_body_line(line):
            new_lines.append(line)
            continue
        out: list[str] = []
        cursor = 0
        for (start, end) in _sentence_spans(line):
            out.append(line[cursor:start])  # inter-sentence whitespace, verbatim
            sentence = line[start:end]
            stripped_sentence = _CONFIDENCE_MARKER_RE.sub("", sentence)
            chosen: tuple[str, str] | None = None
            for claim_id, _v, _s, stem_norm, marker in label_targets:
                if _sentence_matches_stem(stripped_sentence, stem_norm):
                    chosen = (claim_id, marker)
                    break
            if chosen is None:
                out.append(sentence)  # byte-identical — VERIFIED / unrelated sentence
            else:
                claim_id, marker = chosen
                labeled.add(claim_id)
                out.append(sentence if marker in sentence else f"{sentence} {marker}")
            cursor = end
        out.append(line[cursor:])
        new_lines.append("".join(out))
    working = "\n".join(new_lines)

    # Defensive: a collected (present + pinnable) MANDATORY claim MUST have been labeled in the pass.
    annotated: list[AnnotatedClaim] = []
    for claim_id, verdict, severity, _stem, marker in claims:
        if claim_id not in labeled:
            raise ReportRedactionError(
                f"claim {claim_id} ({verdict}/{severity}) was pinnable but no sentence matched it in "
                "the labeling pass (fail-closed)."
            )
        annotated.append(
            AnnotatedClaim(claim_id=claim_id, severity=severity, verdict=verdict, marker=marker)
        )
    # Advisory twins are best-effort: record only the ones that actually got labelled; NEVER raise.
    for claim_id, verdict, severity, _stem, marker in advisory:
        if claim_id in labeled:
            annotated.append(
                AnnotatedClaim(claim_id=claim_id, severity=severity, verdict=verdict, marker=marker)
            )

    return AnnotationResult(report_text=working, annotated=annotated, already_absent=already_absent)


def _collect_figure_consistency_claims(
    report_text: str,
    final_verdicts: dict[str, str],
    audit_map: dict[str, dict],
    marker_by_claim: dict[str, str],
    span_text_by_claim: dict[str, str] | None,
    already_collected: set[str],
) -> list[tuple[str, str, str, str, str]]:
    """WS-5 (I-deepfix-001): build the ADVISORY figure-consistency labelling claims.

    Returns ``(claim_id, verdict, severity, stem_norm, marker)`` tuples for every claim NOT already
    collected as mandatory whose caveat must be inherited because it is a twin of a flagged claim:
      * FIX-a: it shares BOTH a span-identity tuple AND a numeric figure with a non-VERIFIED claim
        -> inherits that flagged sibling's marker.
      * FIX-b: ``span_text_by_claim`` names its cited span AND ``effect_size_conditional_reason``
        fires (the claim re-lifts a span number while dropping the governing conditional/threshold)
        -> inherits a generic low marker.
    Gated by ``PG_FIGURE_CONSISTENCY_ANNOTATE`` (default ON, via ``figure_consistency_annotate_enabled``);
    disabled -> returns ``[]`` (byte-identical claim_id-only behaviour). Never raises: a twin the
    per-line pass cannot pin is simply omitted (adding a caveat is a bonus, its absence is not a leak).
    """
    if not figure_consistency_annotate_enabled():
        return []

    # FIX-a index: (span-identities, figures, marker) for each flagged (non-VERIFIED) claim that
    # names BOTH a span and a figure. A twin must intersect BOTH to inherit (surgical — same-span
    # prose that repeats no flagged figure is NOT caveated).
    flagged_index: list[tuple[set[tuple[str, int, int]], set[str], str]] = []
    for claim_id, verdict in final_verdicts.items():
        if verdict == _VERDICT_VERIFIED:
            continue
        sentence = str((audit_map.get(claim_id) or {}).get("sentence", ""))
        spans = _span_identities(sentence)
        figs = _figure_tokens(sentence)
        if spans and figs:
            marker = marker_by_claim.get(claim_id) or _DEFAULT_LOW_MARKER
            flagged_index.append((spans, figs, marker))

    advisory: list[tuple[str, str, str, str, str]] = []
    seen = set(already_collected)
    for claim_id, verdict in sorted(final_verdicts.items()):
        if claim_id in seen:
            continue
        meta = audit_map.get(claim_id)
        if meta is None:
            continue
        sentence = str(meta.get("sentence", ""))
        stem_norm = _normalize(sentence)
        if not stem_norm or not _prose_present(report_text, stem_norm):
            continue  # nothing rendered to label

        marker: str | None = None
        # FIX-a — flagged span-identity + shared figure.
        twin_spans = _span_identities(sentence)
        twin_figs = _figure_tokens(sentence)
        if twin_spans and twin_figs:
            for f_spans, f_figs, f_marker in flagged_index:
                if (twin_spans & f_spans) and (twin_figs & f_figs):
                    marker = f_marker
                    break
        # FIX-b — effect-size conditional/threshold stripped (needs the cited span text).
        if marker is None and span_text_by_claim:
            span_text = span_text_by_claim.get(claim_id, "")
            if span_text and effect_size_conditional_reason(sentence, span_text):
                marker = _DEFAULT_LOW_MARKER

        if marker is None:
            continue
        advisory.append((claim_id, verdict, str(meta.get("severity", "")), stem_norm, marker))
        seen.add(claim_id)
    return advisory


# A generic low-confidence marker for a non-VERIFIED claim whose caller-supplied marker is missing
# (never leave an unverified claim unlabeled). Mirrors claim_labeler's low wording.
_DEFAULT_LOW_MARKER = "[confidence: low — NOT confirmed by the cited source; treat as unverified]"


# ─────────────────────────────────────────────────────────────────────────────
# A4 (I-deepfix-001) — ATTRIBUTION-ORIGIN visible-text caveat (render layer)
# ─────────────────────────────────────────────────────────────────────────────
# The attribution-origin guard (``attribution_origin_guard.attribution_origin_reason``) flags a
# claim that NAMES an organizational finder ("<ORG> found that Y") whose identity is NOT the
# publisher of ANY cited source — a re-reporting SECONDARY citation ("correctness is not
# faithfulness": the cited span supports the number, but the citation is not the faithful ORIGIN of
# the assertion). During verification that fires as DISCLOSURE-ONLY telemetry; the VISIBLE sentence
# still names the unsupported actor. This render pass APPENDS an inline caveat to that sentence so
# the mis-attribution is corrected in the text the reader sees.
#
# Codex P1 fixes (this rewrites VERIFIED visible prose — highest risk, conservative by construction):
#   * P1 #1 (boundary): the caveat marker is consumed as trailing material by
#     ``_SENTENCE_BOUNDARY_RE`` (see ``_ATTRIBUTION_CAVEAT_TRAILER``), so it can NEVER fuse the
#     caveated sentence with the next grounded sentence and cause a later D8 over-redaction. And
#     ``_normalize`` strips the caveat, so a caveated sentence still matches its own stem at the
#     redactor / annotator coverage floor.
#   * P1 #2 (citation-SPECIFIC, not citation-insensitive): the decision is RE-DERIVED per rendered
#     occurrence from that sentence's OWN resolved ``[N]`` citation domains via the guard — so a
#     legitimately primary-cited occurrence of the same claim is NEVER caveated, and a deduped-away
#     secondary occurrence cannot cause a sibling to be wrongly caveated.
#   * P1 #3 (ALL rendered claim units): the pass scans the ASSEMBLED report.md body directly, so it
#     covers EVERY rendered unit (CWF, quantified-analysis, every section) — not just
#     ``multi.sections``.
#
# §-1.3 WITHHOLD-DISCLOSE (never a hard drop): it NEVER drops the sentence, NEVER removes the
# grounded number, NEVER removes the ``[N]`` citation — it ONLY ADDS a caveat. HIGH-PRECISION +
# FAIL-OPEN: a sentence with no citations, or whose ``[N]`` citations cannot be FULLY resolved to
# URLs, is skipped (never caveated on incomplete evidence). The faithfulness engine (strict_verify /
# NLI / 4-role D8 / provenance) is untouched — this pass runs entirely at the render layer on
# already-verified prose.
_ATTRIBUTION_SOFT_WARNING_PREFIX = "attribution_origin_unverified:"
_ATTRIBUTION_ACTORS_RE = re.compile(r"actors=(.*?):cited_domains=")
# A bare numbered citation marker ``[12]`` — used to read a rendered sentence's OWN visible
# citations so the guard can be re-run against THAT occurrence's actual cited domains (P1 #2).
_NUMBERED_CITATION_RE = re.compile(r"\[(\d+)\]")
# A4 (I-deepfix-001) Codex P1: a rendered body line can BEGIN with wrapped trailing citations that
# belong to the PREVIOUS sentence ("[71][5][7][6] Further analysis found …"). A LEADING run of bare
# ``[N]`` markers (before any word character) is NOT this sentence's own citation — reading it would
# resolve a neighbor's source domains and could caveat this sentence on evidence it does not carry.
# Stripped before the sentence's OWN markers are read, so only citations attached to this sentence's
# words / trailing its own terminator survive.
_LEADING_WRAPPED_CITATIONS_RE = re.compile(r"^\s*(?:\[\d+\]\s*)+")


def attribution_actor_from_soft_warning(soft_warning: str) -> str | None:
    """Extract a human-readable actor label from an attribution-origin soft_warning.

    Soft-warning form (``attribution_origin_guard.attribution_origin_reason``):
      ``attribution_origin_unverified:actors=<run>|<run2>:cited_domains=<d1>,<d2>``
    Returns the ``actors=`` payload with the internal ``|`` separator rendered as ``/`` (e.g.
    "The International Labour Organization / Poland's National Research Institute"), or None when
    the string is not an attribution-origin warning / carries no actors (defensive — never raises).
    """
    if not soft_warning or not soft_warning.startswith(_ATTRIBUTION_SOFT_WARNING_PREFIX):
        return None
    m = _ATTRIBUTION_ACTORS_RE.search(soft_warning)
    if not m:
        return None
    actors = m.group(1).strip()
    if not actors:
        return None
    return actors.replace("|", " / ")


def _attribution_caveat_marker(actor: str) -> str:
    """The inline caveat appended to a mis-attributed sentence (plain declarative English)."""
    # Codex P1 (A4): NO semicolon — ``report_claim_extractor._default_atomizer`` splits atoms on
    # ``;``, so a semicolon here would spawn a spurious "…supported by the cited source]" claim atom.
    # An em-dash carries the same reading without creating a new atom.
    return (
        f"[attribution unverified — the cited source does not appear to be {actor} — "
        "the finding itself is supported by the cited source]"
    )


@dataclass
class AttributionCaveat:
    """One sentence that received an inline attribution-origin caveat in the visible report."""

    actor: str
    sentence: str  # the matched rendered sentence (pre-caveat)


@dataclass
class AttributionCorrectionResult:
    """Outcome of appending attribution-origin caveats to the rendered report."""

    report_text: str
    caveated: list[AttributionCaveat] = field(default_factory=list)
    # Sentences the guard would flag but whose visible ``[N]`` citations could not be fully resolved
    # to URLs (so we conservatively did NOT caveat) — recorded for the audit trail, never a leak.
    skipped_unresolved: list[str] = field(default_factory=list)

    @property
    def caveated_count(self) -> int:
        return len(self.caveated)


def _rendered_sentence_attribution_actor(
    sentence: str,
    citation_urls: "dict[str, str]",
    attribution_origin_reason,
) -> "tuple[str | None, bool]":
    """Decide whether ONE rendered sentence is a mis-attribution, citation-SPECIFICally (P1 #2).

    Returns ``(actor_label, resolved_ok)``:
      * ``actor_label`` is the finder to name in the caveat, or None when the sentence is not a
        mis-attribution (or cannot be judged).
      * ``resolved_ok`` is False when the sentence NAMES cited markers we could not fully resolve to
        URLs — the caller records that (audit trail) and conservatively skips it.

    The decision RE-RUNS the attribution-origin guard against THIS occurrence's OWN visible ``[N]``
    citations resolved to source URLs, so a legitimately primary-cited occurrence of the same claim
    never fires. FAIL-OPEN: a sentence with no citations, or any unresolved citation, is not
    caveated. Never raises.
    """
    # Idempotence: a sentence already carrying an attribution caveat is left alone (``_normalize``
    # strips the caveat, so the redactor / annotator still match its stem).
    if _ATTRIBUTION_CAVEAT_RE.search(sentence):
        return None, True
    # Codex P1 (A4): read only the citations this sentence OWNS. Strip a leading run of wrapped
    # markers that belong to the previous sentence (report_redactor documents this shape) so we never
    # resolve a neighbor's domains onto this sentence. If nothing remains after the strip, the
    # sentence carries no citation of its own -> cannot judge origin -> skip (fail-open).
    own = _LEADING_WRAPPED_CITATIONS_RE.sub("", sentence)
    nums = _NUMBERED_CITATION_RE.findall(own)
    if not nums:
        return None, True  # no citation the sentence OWNS -> cannot judge origin -> skip (fail-open)
    urls: list[str] = []
    for n in nums:
        url = citation_urls.get(str(n))
        if not url:
            # A cited marker we cannot resolve -> we cannot rule out a matching primary source ->
            # do NOT caveat (never caveat on incomplete evidence).
            return None, False
        urls.append(url)
    # Strip provenance tokens + numbered markers, keeping case + punctuation for the guard's
    # proper-noun + attribution-verb matcher.
    prose = _prose_stem(sentence).strip()
    if not prose:
        return None, True
    reason = attribution_origin_reason(prose, urls)
    if not reason:
        return None, True  # guard inert -> attribution is fine (or ambiguous) -> no caveat
    return attribution_actor_from_soft_warning(reason), True


def annotate_report_attribution_origin(
    report_text: str,
    citation_urls: "dict[str, str]",
) -> AttributionCorrectionResult:
    """APPEND an inline attribution caveat to every mis-attributed body sentence in ``report_text``.

    Args:
      report_text: the assembled report.md content.
      citation_urls: ``{citation_number(str): source_url}`` built from the rendered bibliography
        (each row's ``num`` -> ``url``). Used to resolve a sentence's OWN visible ``[N]`` markers to
        the domains the guard checks — this is what makes the caveat citation-SPECIFIC (P1 #2).

    For each body sentence, the attribution-origin guard is RE-RUN against that occurrence's own
    resolved citation domains (``_rendered_sentence_attribution_actor``); only a sentence that STILL
    fires gets the caveat appended once. Covers EVERY rendered claim unit because it walks report.md
    directly (P1 #3). IDEMPOTENT: a sentence already carrying an attribution caveat is byte-identical.
    NEVER raises — a sentence with unresolved citations is recorded in ``skipped_unresolved`` and
    left unchanged (FAIL-OPEN). Only body sentences are touched; headings and bibliography rows
    (``_is_redactable_body_line``) are byte-preserved.
    """
    from src.polaris_graph.generator.attribution_origin_guard import (  # noqa: PLC0415
        attribution_origin_reason,
    )

    caveated: list[AttributionCaveat] = []
    skipped_unresolved: list[str] = []
    new_lines: list[str] = []
    for line in report_text.split("\n"):
        if not _is_redactable_body_line(line):
            new_lines.append(line)  # heading / bibliography / blank — byte-identical
            continue
        out: list[str] = []
        cursor = 0
        for (start, end) in _sentence_spans(line):
            out.append(line[cursor:start])  # inter-sentence whitespace, verbatim
            sentence = line[start:end]
            actor, resolved_ok = _rendered_sentence_attribution_actor(
                sentence, citation_urls, attribution_origin_reason
            )
            if not resolved_ok:
                skipped_unresolved.append(sentence)
            if actor is None:
                out.append(sentence)  # byte-identical — not a mis-attribution / already caveated
            else:
                out.append(f"{sentence} {_attribution_caveat_marker(actor)}")
                caveated.append(AttributionCaveat(actor=actor, sentence=sentence))
            cursor = end
        out.append(line[cursor:])
        new_lines.append("".join(out))

    return AttributionCorrectionResult(
        report_text="\n".join(new_lines),
        caveated=caveated,
        skipped_unresolved=skipped_unresolved,
    )
