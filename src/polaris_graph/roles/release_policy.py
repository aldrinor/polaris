"""D8 production release policy — occurrence / residual / S0-must-cover gate.

I-meta-002 sub-PR-3. This is the PRODUCTION release gate (a pure function over D8 claim
rows; no network, no I/O except the config loader). It is a SEPARATE layer from the
FROZEN, pre-registered benchmark scorer (`claim_audit_scorer.py`): this module REUSES the
canonical `Verdict` vocabulary (for the type hint only) but does NOT mutate the scorer, does
NOT import its private constants, and does NOT change its 0.70 frozen benchmark threshold.

The clinical occurrence/residual split (from the I-meta-002 iter-2 D8 design ruling):

  * FABRICATED is OCCURRENCE-gated with zero tolerance, via a true one-way LATCH. A
    fabricated *citation identity* arrives already stamped `verdict=="FABRICATED"` — the
    CALLER (sub-PR-5) runs `judge_contract.classify_unreachable` UPSTREAM with the evidence
    pool and writes the result into the row. D8 reads `verdict` only; it never re-classifies
    and never receives the evidence pool.
  * UNSUPPORTED is RESIDUAL-gated: one rewrite/refuse-in-place attempt, then gate only if the
    `CoverageLedger` fraction is below the configured `coverage_threshold`. The ledger
    denominator is the FIXED per-question required-element set, so dropping/refusing a claim
    LOWERS coverage rather than dodging the gate.
  * Genuine UNREACHABLE fetch-misses follow the SAME residual path as UNSUPPORTED (never
    silently passed). Only fabricated identities (already `FABRICATED`) occurrence-gate.
  * S0 must-cover categories abort release if any required category lacks a VERIFIED claim,
    regardless of the overall coverage fraction.
  * PARTIAL S0/S1 claims get one rewrite attempt, then ship as a visible advisory gap.

Refused-in-place / residual gaps are always emitted as visible `Gap`s — never silent drops.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

from src.polaris_graph.benchmark.claim_audit_scorer import Verdict

# --- canonical verdict tokens (Verdict is a Literal of plain strings, NOT an Enum) -------
# Mirror judge_contract's _CLASS_* string-constant pattern; never write `Verdict.X`.
_VERDICT_VERIFIED = "VERIFIED"
_VERDICT_PARTIAL = "PARTIAL"
_VERDICT_UNSUPPORTED = "UNSUPPORTED"
_VERDICT_FABRICATED = "FABRICATED"
_VERDICT_UNREACHABLE = "UNREACHABLE"

# --- local materiality (do NOT import the frozen scorer's private _MATERIAL_SEVERITIES) ---
# Material = decision-relevant. Kept in sync with config/architecture/d8_release_policy.yaml
# `material_severities`. S3 is observe-only and never gates / never latches.
_MATERIAL_SEVERITIES = ("S0", "S1", "S2")
# Severities at which a PARTIAL claim earns a rewrite-then-advisory pass.
_PARTIAL_REWRITE_SEVERITIES = ("S0", "S1")

# --- stable reason codes (held_reasons) ---------------------------------------------------
_REASON_FABRICATED_OCCURRENCE = "d8_fabricated_occurrence"
_REASON_S0_MUST_COVER_MISSING_PREFIX = "d8_s0_must_cover_missing:"
_REASON_UNSUPPORTED_RESIDUAL_BELOW_COVERAGE = "d8_unsupported_residual_below_coverage"
# A pass with claims still routed to a rewrite/refuse-in-place attempt is NOT releasable yet
# (the required attempt has not happened). Blocks release on the first pass (Codex diff P1-a).
_REASON_PENDING_REWRITE = "d8_pending_rewrite"

# --- stable gap kinds ---------------------------------------------------------------------
_GAP_UNCOVERED_S0 = "uncovered_s0"
_GAP_REFUSED_IN_PLACE = "refused_in_place"
_GAP_RESIDUAL_UNSUPPORTED = "residual_unsupported"
_GAP_PARTIAL_ADVISORY = "partial_advisory"
_GAP_COVERAGE_SHORTFALL = "coverage_shortfall"

# --- config loader -----------------------------------------------------------------------
_CONFIG_KEY_COVERAGE_THRESHOLD = "coverage_threshold"
_CONFIG_KEY_MATERIAL_SEVERITIES = "material_severities"
_CONFIG_KEY_S0_MUST_COVER = "s0_must_cover_categories"

# Default config path: <repo_root>/config/architecture/d8_release_policy.yaml.
# parents[3] of .../src/polaris_graph/roles/release_policy.py == the repo root.
_DEFAULT_CONFIG_PATH = (
    Path(__file__).resolve().parents[3]
    / "config"
    / "architecture"
    / "d8_release_policy.yaml"
)


@dataclass
class D8ClaimRow:
    """Production-side D8 claim row (wrapper; does NOT mutate the frozen `ClaimRow`).

    `verdict` is a `claim_audit_scorer.Verdict` value already stamped by the caller
    (sub-PR-5): fabricated citation identity -> "FABRICATED"; genuine fetch-miss ->
    "UNREACHABLE". D8 reads it; it never calls `classify_unreachable`.

    `citation_id` is carried for gap reporting only. `s0_categories` lists which S0
    must-cover categories THIS claim addresses (empty if none).
    """

    claim_id: str
    severity: str
    verdict: Verdict
    citation_id: str | None = None
    s0_categories: list[str] = field(default_factory=list)

    @property
    def is_material(self) -> bool:
        return self.severity in _MATERIAL_SEVERITIES


@dataclass
class CoverageLedger:
    """Element-level coverage ledger with a FIXED required-set denominator.

    `covered_element_ids` is populated by the CALLER (sub-PR-5) — only required elements
    satisfied by a citation-supported VERIFIED claim are added, and genuine UNREACHABLE
    elements are excluded by the caller. D8 only reads `.fraction()`. Because the denominator
    is the fixed required set, dropping/refusing a claim shrinks the numerator (lowers the
    fraction); it can never inflate coverage.
    """

    required_element_ids: list[str]
    covered_element_ids: set[str] = field(default_factory=set)

    def fraction(self) -> float:
        required = set(self.required_element_ids)
        if not required:
            return 1.0
        return len(required & self.covered_element_ids) / len(required)


@dataclass
class Gap:
    """One visible gap in `gaps.json`. Never a silent drop."""

    ref: str  # claim_id or category
    kind: str  # one of _GAP_* above
    severity: str
    note: str


@dataclass
class ReleaseDecision:
    """The D8 release decision over one pass of claim rows."""

    release_allowed: bool
    held_reasons: list[str]
    gaps: list[Gap]
    needs_rewrite: list[str]
    fabricated_occurrence_latched: bool


@dataclass
class D8PolicyConfig:
    """Loaded D8 policy config (production layer)."""

    coverage_threshold: float
    material_severities: list[str]
    s0_must_cover_categories: list[str]


def load_d8_policy_config(path: str | Path | None = None) -> D8PolicyConfig:
    """Load the D8 release-policy config from YAML (LAW VI, zero hard-coding).

    Fails loudly (FileNotFoundError / KeyError) on a missing file or missing key — never
    silently defaults. The per-question required S0 set is passed by the caller, not read
    here; `s0_must_cover_categories` is only the default clinical vocabulary.
    """
    config_path = Path(path) if path is not None else _DEFAULT_CONFIG_PATH
    if not config_path.is_file():
        raise FileNotFoundError(f"D8 policy config not found: {config_path}")
    with config_path.open(encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"D8 policy config is not a mapping: {config_path}")
    return D8PolicyConfig(
        coverage_threshold=float(data[_CONFIG_KEY_COVERAGE_THRESHOLD]),
        material_severities=list(data[_CONFIG_KEY_MATERIAL_SEVERITIES]),
        s0_must_cover_categories=list(data[_CONFIG_KEY_S0_MUST_COVER]),
    )


def apply_d8_release_policy(
    d8_rows: list[D8ClaimRow],
    *,
    required_s0_categories: list[str],
    coverage_ledger: CoverageLedger,
    coverage_threshold: float,
    rewrite_already_attempted: bool,
    prior_fabricated_latched: bool = False,
) -> ReleaseDecision:
    """Apply the D8 production release policy to one pass of claim rows.

    Every gate is evaluated (no short-circuit) so `gaps` / `held_reasons` are complete.
    `release_allowed` is True iff `held_reasons` is empty; `gaps` and `needs_rewrite` are
    separate reporting channels and do NOT by themselves block release.
    """
    held_reasons: list[str] = []
    gaps: list[Gap] = []
    needs_rewrite: list[str] = []

    material_rows = [row for row in d8_rows if row.is_material]

    # (a) FABRICATED occurrence LATCH — one-way; rewrite does NOT clear it.
    fabricated_this_pass = any(
        row.verdict == _VERDICT_FABRICATED for row in material_rows
    )
    fabricated_occurrence_latched = prior_fabricated_latched or fabricated_this_pass
    if fabricated_occurrence_latched:
        held_reasons.append(_REASON_FABRICATED_OCCURRENCE)

    # (b) UNSUPPORTED residual + (b2) genuine UNREACHABLE residual — SAME path.
    # First pass: route material UNSUPPORTED/UNREACHABLE rows to a rewrite/refuse-in-place
    # attempt. Post-attempt: emit a VISIBLE residual gap for any that remain (never a silent
    # drop). The coverage HOLD below is computed from the ledger alone — NOT from whether a
    # residual row is still present — so dropping/refusing the row cannot dodge the gate
    # (Codex diff P1-b).
    for row in material_rows:
        if row.verdict not in (_VERDICT_UNSUPPORTED, _VERDICT_UNREACHABLE):
            continue
        if not rewrite_already_attempted:
            needs_rewrite.append(row.claim_id)
        else:
            if row.verdict == _VERDICT_UNREACHABLE:
                note = (
                    "genuine fetch-miss (UNREACHABLE) remained after one rewrite attempt; "
                    "visible residual gap, not silently passed"
                )
            else:
                note = "unsupported claim remained after one rewrite/refuse-in-place attempt"
            gaps.append(
                Gap(
                    ref=row.claim_id,
                    kind=_GAP_RESIDUAL_UNSUPPORTED,
                    severity=row.severity,
                    note=note,
                )
            )
    # Coverage floor — UNCONDITIONAL on the fixed-denominator ledger. A run whose required-
    # element coverage is below threshold is never releasable, whether the shortfall is caused
    # by an UNSUPPORTED/UNREACHABLE row that is still present, one that was dropped/refused, or
    # a required element that never had a claim at all. This closes the "drop the row to dodge
    # the gate" hole (Codex diff P1-b): the denominator is the required set, so removing a claim
    # lowers the fraction. On the first pass a low fraction is additionally caught by the
    # pending-rewrite hold below; once the rewrite is exhausted, this is the binding gate.
    if coverage_ledger.fraction() < coverage_threshold:
        held_reasons.append(_REASON_UNSUPPORTED_RESIDUAL_BELOW_COVERAGE)
        gaps.append(
            Gap(
                ref="__coverage__",
                kind=_GAP_COVERAGE_SHORTFALL,
                severity="S0",
                note=(
                    f"required-element coverage {coverage_ledger.fraction():.3f} is below the "
                    f"{coverage_threshold:.3f} threshold (fixed required-set denominator)"
                ),
            )
        )

    # (c) S0 must-cover gate — category covered iff a VERIFIED claim carries it.
    verified_categories: set[str] = set()
    for row in d8_rows:
        if row.verdict == _VERDICT_VERIFIED:
            verified_categories.update(row.s0_categories)
    for category in required_s0_categories:
        if category not in verified_categories:
            held_reasons.append(f"{_REASON_S0_MUST_COVER_MISSING_PREFIX}{category}")
            gaps.append(
                Gap(
                    ref=category,
                    kind=_GAP_UNCOVERED_S0,
                    severity="S0",
                    note=(
                        "required S0 must-cover category has no VERIFIED claim "
                        "(PARTIAL/citation-only does not satisfy it)"
                    ),
                )
            )

    # (d) PARTIAL S0/S1 — one rewrite, then visible advisory gap.
    for row in d8_rows:
        if row.verdict != _VERDICT_PARTIAL:
            continue
        if row.severity not in _PARTIAL_REWRITE_SEVERITIES:
            continue
        if not rewrite_already_attempted:
            needs_rewrite.append(row.claim_id)
        else:
            gaps.append(
                Gap(
                    ref=row.claim_id,
                    kind=_GAP_PARTIAL_ADVISORY,
                    severity=row.severity,
                    note="PARTIAL claim ships as a visible advisory after one rewrite attempt",
                )
            )

    # A pass with pending rewrites is NOT releasable — the required rewrite/refuse-in-place
    # attempt has not happened yet (Codex diff P1-a: release_allowed previously ignored
    # needs_rewrite, letting a first-pass run release before the attempt).
    #
    # I-perm-006 (#1200): `d8_pending_rewrite` is a PHANTOM block — `rewrite_already_attempted` is
    # hardcoded False at every call site and NO outer loop ever re-runs the seam to set it True
    # (grep: `rewrite_already_attempted=True` exists ONLY in tests/). So it blocks release for an
    # attempt the architecture structurally never executes. Under the always-release reframe
    # (I-perm-001) an UNSUPPORTED claim ships LABELED via the annotator, not blocked, so the phantom
    # block is removed: when PG_ALWAYS_RELEASE is on, `needs_rewrite` stays a pure REPORTING channel
    # and does NOT add a held_reason. Flag OFF -> byte-identical (the block still fires).
    if needs_rewrite and not always_release_enabled():
        held_reasons.append(_REASON_PENDING_REWRITE)

    release_allowed = not held_reasons
    return ReleaseDecision(
        release_allowed=release_allowed,
        held_reasons=held_reasons,
        gaps=gaps,
        needs_rewrite=needs_rewrite,
        fabricated_occurrence_latched=fabricated_occurrence_latched,
    )


def to_gaps_json(decision: ReleaseDecision) -> list[dict]:
    """Serialize a decision's gaps into a JSON-ready list of dicts (gaps.json structure)."""
    return [
        {
            "ref": gap.ref,
            "kind": gap.kind,
            "severity": gap.severity,
            "note": gap.note,
        }
        for gap in decision.gaps
    ]


# ── I-perm-001 (#1195) keystone slice 1: WITHHOLD → ALWAYS-RELEASE + LABEL ───────────────────
# The withhold-when-imperfect gate stack (coverage-below-threshold, S0-must-cover-missing,
# pending-rewrite) BLOCKS the whole report. Under always-release it converts every such hold
# from a release-BLOCKER into a DISPLAYED disclosed-gap label; the report ships with honest
# per-gap disclosure and the user judges. The ONLY hard line that still withholds a normal
# report is (a) a FABRICATED occurrence latch, or (b) true zero-grounding (no VERIFIED claim AND
# no usable evidence). A clinical safety floor (all required S0 SAFETY categories disclosed as
# gaps / zero VERIFIED safety content) does not HARD-block, but it blocks the NORMAL render and
# ships an honest "insufficient safety evidence" report instead (operator decision, blueprint R2).
#
# B5/B7 (2026-06-14): DEFAULT ON. ONLY an EXPLICIT off token ('0'/'false'/'no'/'off') reproduces
# the legacy `release_allowed` decision verbatim (byte-identical). Unset / empty / unrecognized ->
# ON. The legacy-regression callers pass the off state EXPLICITLY (compute_release_outcome's
# `always_release=False` arg, or env '0') — never an empty string.

# Master flag.
#
# B5/B7 (DUAL_AGREED_PLAN, operator-locked 2026-06-14) — "nothing shall hold the report":
# the production DEFAULT is now ON (always-release). Holds become DISPLAYED disclosed-gap labels;
# every run ships an honest artifact. The OFF switch is retained for the byte-identical legacy
# regression: an EXPLICIT off token (``0`` / ``false`` / ``off`` / ``no``) restores the legacy
# withhold decision verbatim. UNSET, EMPTY (``""``), and any UNRECOGNIZED value resolve to the
# default ON — a default-ON flag must never SILENTLY withhold a report on an unset/stray/empty
# value. The legacy-regression callers never pass ``""``; they pass ``"0"`` (env) or
# ``always_release=False`` (the explicit arg to ``compute_release_outcome``).
_ENV_ALWAYS_RELEASE = "PG_ALWAYS_RELEASE"
_ON_VALUES = frozenset({"1", "true", "yes", "on"})
# Explicit OFF tokens — the ONLY way to restore the legacy withhold path. Anything else (unset,
# unrecognized) resolves to the default-ON always-release behaviour.
_OFF_VALUES = frozenset({"0", "false", "no", "off"})

# Held reasons that are NON-hard: under always-release they become disclosed-gap labels, not
# release blockers. A FABRICATED occurrence is the one held reason that is NEVER a mere label.
_NON_HARD_HELD_REASONS = frozenset(
    {
        _REASON_UNSUPPORTED_RESIDUAL_BELOW_COVERAGE,
        _REASON_PENDING_REWRITE,
    }
)

# Status vocabulary (mirrors scripts/run_honest_sweep_r3.py UNIFIED_STATUS_VALUES; slice 1 adds
# the two released-with-disclosure terminals — both are RELEASED, not abort).
STATUS_SUCCESS = "success"
STATUS_RELEASED_WITH_DISCLOSED_GAPS = "released_with_disclosed_gaps"
STATUS_RELEASED_INSUFFICIENT_SAFETY = "released_insufficient_safety_evidence"
STATUS_ABORT_NO_VERIFIED = "abort_no_verified_sections"
STATUS_ABORT_FOUR_ROLE_HELD = "abort_four_role_release_held"
STATUS_ABORT_FABRICATED = "abort_evaluator_critical"

# B5/B7 (DUAL_AGREED_PLAN §B5/B7, operator-RATIFIED 2026-06-14): a FABRICATED citation is an
# INVENTED source not in the evidence pool — it can never be honestly LABELED (there is no real
# basket to disclose). The ratified disposition is: DROP that one claim with a LOUD disclosure and
# still SHIP the report, rather than HARD-blocking the whole report. The fabricated claim's prose
# is removed by the report_redactor (verdict set includes FABRICATED); this gap reason surfaces the
# drop as a DISPLAYED label so the drop is never silent. This is NOT a faithfulness relaxation: the
# fabricated claim is still detected and still excised from asserted prose — only the REPORT-LEVEL
# disposition changes from withhold-everything to ship-minus-the-bad-claim.
_GAP_FABRICATED_CITATION_DROPPED = "d8_fabricated_citation_dropped_and_disclosed"


def is_hard_block(
    *,
    fabricated_occurrence_latched: bool,
    zero_verified: bool,
    zero_usable_evidence: bool,
    redaction_active: bool = True,
) -> bool:
    """The canonical no-fabrication hard line — narrowed per B5/B7 (operator-ratified 2026-06-14).

    A report is HARD-blocked iff there is true zero-grounding (no VERIFIED claim AND no usable
    evidence), OR a FABRICATED occurrence latched WHILE per-claim redaction is NOT active.

    ``redaction_active`` (default True — production leaves ``PG_REDACT_HELD_UNSUPPORTED`` ON, the
    kill-switch is test/offline-only) is the SAFETY COUPLING the narrowing depends on: a fabricated
    claim is allowed to ship-minus-itself ONLY because the redactor guarantees the fabricated claim's
    prose is excised. If redaction is disabled, the fabricated claim could ship as asserted prose, so
    FABRICATED REMAINS a hard block — the narrowing is gated on the excision being guaranteed.
    Zero-grounding is ALWAYS a hard block regardless of redaction.
    """
    if zero_verified and zero_usable_evidence:
        return True
    if fabricated_occurrence_latched and not redaction_active:
        return True
    return False


@dataclass
class ReleaseOutcome:
    """The always-release-aware release outcome over a D8 ``ReleaseDecision`` (I-perm-001).

    ``released`` — a report ships (normal OR honest-insufficient-safety variant).
    ``hard_block`` — the no-fabrication hard line fired; NO report ships as clean.
    ``normal_release_blocked`` — the polished normal report is withheld (hard_block OR the clinical
        safety floor is insufficient), but an honest report may still ship.
    ``status`` — the terminal pipeline status.
    ``disclosed_gaps`` — the held reasons surfaced as DISPLAYED labels (not blockers).
    ``release_quality_score`` — the displayed coverage fraction (NOT a trap-door threshold).
    """

    released: bool
    hard_block: bool
    normal_release_blocked: bool
    status: str
    disclosed_gaps: list[str]
    hard_block_reasons: list[str]
    release_quality_score: float
    safety_floor: str  # "ok" | "insufficient"
    # A18/A2-SEAM STRUCTURAL PROOF FIELDS (iarch007 SWEEP-P0 + RELEASE-P0). These three fields
    # let `assert_release_invariant` decide STRUCTURALLY (not by sniffing a gap-label string)
    # whether un-judged prose may ship. ALL THREE default to the SAFE (un-proven / fail-closed)
    # value so an outcome built without proof can never pass the invariant by omission:
    #   * adjudicated — the four-role D8 judge TRULY ran (backed by real final_verdicts). Defaults
    #     FALSE: a release that does not explicitly prove adjudication is treated as un-judged.
    #   * body_withheld — the findings body was suppressed (the seam fabrication-screen could not
    #     run / found a fabricated identity). Defaults FALSE (body ships) — explicit.
    #   * compensating_screen_passed — on a seam (no D8) the standalone fabrication screen ran
    #     CLEAN, so a body that ships is screen-safe. Defaults FALSE (no compensating proof).
    adjudicated: bool = False
    body_withheld: bool = False
    compensating_screen_passed: bool = False

    def display_quality_score(self) -> str:
        """B11 C3 (#1362 deepfix): the HONEST display string for the release quality score.

        ``release_quality_score`` is the coverage fraction. On a four-role D8 SEAM error (judge
        transport / HTTP-400) the judge NEVER adjudicated, so ``adjudicated`` is False and the raw
        float is 0.0 (or a coverage fraction that was never judged). Rendering that bare ``0.0`` as
        a quality score is a LIE — it reads as "this report scored zero quality" when the truth is
        "D8 could not score it at all". This helper renders ``N/A (D8 unadjudicated)`` whenever the
        judge did not adjudicate, and the numeric score otherwise. The raw float field is left
        unchanged for backward-compatible numeric consumers; the render/UI seam should consult THIS
        display string. Faithfulness-neutral: pure presentation of the already-computed state.
        """
        if not self.adjudicated:
            return "N/A (D8 unadjudicated)"
        return f"{self.release_quality_score:.3f}"


def always_release_enabled() -> bool:
    """PG_ALWAYS_RELEASE — production DEFAULT ON (B5/B7: "nothing shall hold the report").

    OFF only on an EXPLICIT off token ('0'/'false'/'no'/'off'). Unset, EMPTY (''), OR any
    unrecognized value resolves to the default (ON) — a default-ON flag must never SILENTLY
    withhold a report on an unset/empty/typo value. The OFF switch is the byte-identical
    legacy-regression escape hatch; legacy callers pass it explicitly ('0' via env, or
    always_release=False to compute_release_outcome) and never as an empty string.
    """
    import os

    return os.environ.get(_ENV_ALWAYS_RELEASE, "").strip().lower() not in _OFF_VALUES


def compute_release_outcome(
    decision: ReleaseDecision,
    *,
    zero_verified: bool,
    zero_usable_evidence: bool,
    safety_floor_insufficient: bool,
    coverage_fraction: float,
    always_release: bool | None = None,
    redaction_active: bool = True,
    seam_unadjudicated: bool = False,
    fabrication_screen_ran: bool | None = None,
    fabrication_screen_found_fabrication: bool = False,
) -> ReleaseOutcome:
    """Map a D8 ``ReleaseDecision`` to a release outcome under the always-release reframe.

    When always-release is OFF, reproduce the LEGACY decision verbatim: ``released`` ==
    ``decision.release_allowed``, the held reasons stay blockers, and the status is the legacy
    held/success label — byte-identical behaviour. When ON, convert non-hard holds to disclosed
    gaps and release, keeping only the zero-grounding hard line and the clinical safety-floor
    normal-render block.

    ``redaction_active`` (default True — production default; the kill-switch is test/offline-only):
    B5/B7 (operator-ratified 2026-06-14) NARROWS the FABRICATED block. With redaction active, a
    latched FABRICATED occurrence ships the report MINUS the fabricated claim (excised by the
    report_redactor) with a LOUD disclosed-gap label, rather than hard-blocking the whole report.
    Only TRUE zero-grounding remains a whole-report hard block. If redaction is disabled, FABRICATED
    stays a hard block (the fabricated prose could otherwise ship) — see ``is_hard_block``.

    A2-SEAM (iarch007 RELEASE-P0) — the un-judged-release leak this CLOSES. When the four-role D8
    judge could not be reached (a transport error / HTTP-400), D8 NEVER adjudicated, so the outcome
    MUST carry the un-judged state honestly (``adjudicated=False``) and a non-empty seam disclosure,
    and a body may ship ONLY if a STANDALONE fabrication screen proves it safe:
      * ``seam_unadjudicated`` — this is the judge-seam path (no D8). Adjudicated is FALSE; the
        specific ``four_role_seam_unadjudicated`` gap is injected so the outcome can only resolve to
        released_with_disclosed_gaps, never success.
      * ``fabrication_screen_ran`` — TRI-STATE, FAIL-CLOSED on unknown. ``None`` (default / the
        screen result is UNKNOWN) and ``False`` (the screen could NOT run) BOTH WITHHOLD the body —
        an un-screened body never ships on a seam (P0 #3). Only an EXPLICIT ``True`` ships the body.
      * ``fabrication_screen_found_fabrication`` — even when the screen ran (``True``), if it FOUND
        a cited identity not in the evidence pool the body is WITHHELD (conservative). The body ships
        only when the screen ran AND found no fabrication, recorded as ``compensating_screen_passed``.
    On the non-seam (genuine-D8) paths ``adjudicated=True`` — the judge produced this decision.
    """
    if seam_unadjudicated:
        return _compute_seam_outcome(
            decision,
            zero_verified=zero_verified,
            zero_usable_evidence=zero_usable_evidence,
            safety_floor_insufficient=safety_floor_insufficient,
            coverage_fraction=coverage_fraction,
            always_release=always_release,
            redaction_active=redaction_active,
            fabrication_screen_ran=fabrication_screen_ran,
            fabrication_screen_found_fabrication=fabrication_screen_found_fabrication,
        )
    enabled = always_release_enabled() if always_release is None else always_release
    hard_block = is_hard_block(
        fabricated_occurrence_latched=decision.fabricated_occurrence_latched,
        zero_verified=zero_verified,
        zero_usable_evidence=zero_usable_evidence,
        redaction_active=redaction_active,
    )
    hard_block_reasons: list[str] = []
    if zero_verified and zero_usable_evidence:
        hard_block_reasons.append("zero_grounding")
    # The fabricated reason is a HARD-block reason ONLY while it actually hard-blocks (redaction
    # off). When the narrowing applies (always-release ON + redaction active) it is surfaced as a
    # disclosed-gap label below, never as a hard_block_reason.
    if decision.fabricated_occurrence_latched and not redaction_active:
        hard_block_reasons.append(_REASON_FABRICATED_OCCURRENCE)
    safety_floor = "insufficient" if safety_floor_insufficient else "ok"

    if not enabled:
        # Legacy withhold path — byte-identical to `decision.release_allowed`.
        # Legacy hard_block surfacing is independent of the B5/B7 narrowing (redaction param),
        # so recompute it here on the pre-narrowing fabricated/zero-grounding line to preserve the
        # exact OFF-path fields (Codex slice-1 P2).
        legacy_hard_block = bool(
            decision.fabricated_occurrence_latched
            or (zero_verified and zero_usable_evidence)
        )
        legacy_hard_reasons: list[str] = []
        if decision.fabricated_occurrence_latched:
            legacy_hard_reasons.append(_REASON_FABRICATED_OCCURRENCE)
        if zero_verified and zero_usable_evidence:
            legacy_hard_reasons.append("zero_grounding")
        status = STATUS_SUCCESS if decision.release_allowed else STATUS_ABORT_FOUR_ROLE_HELD
        return ReleaseOutcome(
            released=decision.release_allowed,
            hard_block=not decision.release_allowed and legacy_hard_block,
            normal_release_blocked=not decision.release_allowed,
            status=status,
            disclosed_gaps=[],
            hard_block_reasons=legacy_hard_reasons if not decision.release_allowed else [],
            release_quality_score=coverage_fraction,
            safety_floor=safety_floor,
            # Non-seam: this decision was produced by a four-role D8 run that ACTUALLY adjudicated.
            adjudicated=True,
        )

    # --- always-release ON ---
    if hard_block:
        # Under the B5/B7 narrowing, the ONLY thing that reaches here is true zero-grounding (a
        # fabricated occurrence with redaction active is NOT a hard block). Zero-grounding is
        # statuses-abort_no_verified; a fabricated-with-redaction-OFF hard block keeps the legacy
        # abort_evaluator_critical label.
        status = (
            STATUS_ABORT_FABRICATED
            if (decision.fabricated_occurrence_latched and not redaction_active)
            else STATUS_ABORT_NO_VERIFIED
        )
        return ReleaseOutcome(
            released=False,
            hard_block=True,
            normal_release_blocked=True,
            status=status,
            # A hard-block reason (fabricated) is NEVER a disclosed GAP (Codex slice-1 P2): it
            # lives in hard_block_reasons. Surface only the non-hard holds as disclosed gaps.
            disclosed_gaps=[
                r for r in decision.held_reasons if r != _REASON_FABRICATED_OCCURRENCE
            ],
            hard_block_reasons=hard_block_reasons,
            release_quality_score=coverage_fraction,
            safety_floor=safety_floor,
            adjudicated=True,
        )

    # Every remaining held reason is a DISPLAYED disclosed-gap label, not a blocker.
    # The fabricated occurrence (now narrowed to ship-minus-the-claim) is NOT in
    # decision.held_reasons as a label — it lives there as the hard `_REASON_FABRICATED_OCCURRENCE`
    # blocker token. Replace it with the explicit "dropped and disclosed" gap so the disclosure is
    # LOUD and never mistaken for the hard-block token.
    disclosed_gaps = [
        r for r in decision.held_reasons if r != _REASON_FABRICATED_OCCURRENCE
    ]
    if decision.fabricated_occurrence_latched:
        disclosed_gaps.append(_GAP_FABRICATED_CITATION_DROPPED)
    if safety_floor_insufficient:
        # Clinical safety floor: ship the honest insufficient-safety report, block normal render.
        return ReleaseOutcome(
            released=True,
            hard_block=False,
            normal_release_blocked=True,
            status=STATUS_RELEASED_INSUFFICIENT_SAFETY,
            disclosed_gaps=disclosed_gaps,
            hard_block_reasons=[],
            release_quality_score=coverage_fraction,
            safety_floor="insufficient",
            adjudicated=True,
        )
    status = STATUS_SUCCESS if not disclosed_gaps else STATUS_RELEASED_WITH_DISCLOSED_GAPS
    return ReleaseOutcome(
        released=True,
        hard_block=False,
        normal_release_blocked=False,
        status=status,
        disclosed_gaps=disclosed_gaps,
        hard_block_reasons=[],
        release_quality_score=coverage_fraction,
        safety_floor="ok",
        adjudicated=True,
    )


# ── A2-SEAM + A18 HARD RELEASE-INVARIANT (iarch007 RELEASE-P0/SWEEP-P0) ──────────────────────
# The un-judged-release leak this whole block CLOSES: a four-role D8 seam error (the judge could
# not be reached) means D8 NEVER adjudicated. The OLD ReleaseOutcome had no way to RECORD that —
# the runtime seam builder defaulted to `adjudicated=True`, and the invariant accepted ANY
# non-empty disclosed_gaps as "seam proof". Either gap let an un-judged, un-screened body ship.
# These three structural fields + the prefix-aware detector + the fail-closed invariant make a
# seam release provable ONLY when (a) the body is withheld OR (b) a standalone fabrication screen
# ran clean AND the SPECIFIC seam gap is disclosed. Faithfulness: RECORDS the un-judged state and
# REFUSES an unsafe release — it relaxes nothing and marks nothing verified.

# The SPECIFIC disclosed-gap label the A2 seam rescue injects (matches scripts/run_honest_sweep_r3
# SEAM_GAP_UNADJUDICATED + iarch007_release_invariant_check._SEAM_GAP_TOKEN — one vocabulary).
_GAP_FOUR_ROLE_SEAM_UNADJUDICATED = "four_role_seam_unadjudicated"
# The disclosed label surfaced when the standalone seam fabrication screen could NOT run (so the
# body is withheld fail-closed — the withhold is never silent).
_GAP_SEAM_FABRICATION_SCREEN_UNAVAILABLE = "four_role_seam_fabrication_screen_unavailable"


def _has_seam_unadjudicated_gap(disclosed_gaps: list[str]) -> bool:
    """True iff ``disclosed_gaps`` carries the SPECIFIC four_role_seam_unadjudicated label.

    PREFIX-AWARE (not a blanket substring): the seam disclosure is either the bare constant OR the
    descriptive runtime form ``"four_role_seam_unadjudicated: <reason>"`` that
    build_seam_release_outcome emits. A gap that merely CONTAINS the token mid-string (e.g.
    ``"note: four_role_seam_unadjudicated happened"``) is NOT the seam label — accepting it would
    re-open the iarch007 SWEEP-P0 bypass where an arbitrary gap passed as seam proof. So the match
    is: equality with the constant, OR a prefix of ``"<constant>:"``.
    """
    for gap in disclosed_gaps or []:
        g = str(gap)
        if g == _GAP_FOUR_ROLE_SEAM_UNADJUDICATED:
            return True
        if g.startswith(f"{_GAP_FOUR_ROLE_SEAM_UNADJUDICATED}:"):
            return True
    return False


def _compute_seam_outcome(
    decision: ReleaseDecision,
    *,
    zero_verified: bool,
    zero_usable_evidence: bool,
    safety_floor_insufficient: bool,
    coverage_fraction: float,
    always_release: bool | None,
    redaction_active: bool,
    fabrication_screen_ran: bool | None,
    fabrication_screen_found_fabrication: bool,
) -> ReleaseOutcome:
    """The judge-SEAM release outcome (D8 never adjudicated). FAIL-CLOSED.

    ``adjudicated`` is ALWAYS False on a seam (the judge did not run). A non-empty seam disclosure
    is ALWAYS injected so the outcome can only resolve to released_with_disclosed_gaps, never
    success. The body ships ONLY when a standalone fabrication screen PROVES it safe:
      * ``fabrication_screen_ran`` is None (UNKNOWN) or False (could not run) -> body WITHHELD, the
        unavailable-screen gap disclosed (P0 #3: an un-screened seam body never ships);
      * ``fabrication_screen_ran`` True AND found a fabricated identity -> body WITHHELD;
      * ``fabrication_screen_ran`` True AND found nothing -> body ships, compensating_screen_passed.

    A true zero-grounding (no VERIFIED claim AND no usable evidence) or a fabricated occurrence with
    redaction OFF is STILL a whole-report hard block on a seam (the same no-fabrication hard line as
    the non-seam path); it is checked first so an un-grounded seam never ships.
    """
    enabled = always_release_enabled() if always_release is None else always_release
    safety_floor = "insufficient" if safety_floor_insufficient else "ok"

    # The seam disclosure (bare constant; the runtime descriptive form is added by the caller in
    # scripts/run_honest_sweep_r3.build_seam_release_outcome — the prefix-aware detector matches both).
    disclosed_gaps: list[str] = [_GAP_FOUR_ROLE_SEAM_UNADJUDICATED]

    # The no-fabrication hard line still applies on a seam — a zero-grounding or
    # fabricated-with-redaction-off body must not ship even un-judged.
    hard_block = is_hard_block(
        fabricated_occurrence_latched=decision.fabricated_occurrence_latched,
        zero_verified=zero_verified,
        zero_usable_evidence=zero_usable_evidence,
        redaction_active=redaction_active,
    )
    if (not enabled) or hard_block:
        hard_block_reasons: list[str] = []
        if zero_verified and zero_usable_evidence:
            hard_block_reasons.append("zero_grounding")
        if decision.fabricated_occurrence_latched and not redaction_active:
            hard_block_reasons.append(_REASON_FABRICATED_OCCURRENCE)
        status = (
            STATUS_ABORT_FABRICATED
            if (decision.fabricated_occurrence_latched and not redaction_active)
            else STATUS_ABORT_FOUR_ROLE_HELD
            if not enabled
            else STATUS_ABORT_NO_VERIFIED
        )
        # Fail-closed seam hold: body withheld, never adjudicated.
        return ReleaseOutcome(
            released=False,
            hard_block=hard_block,
            normal_release_blocked=True,
            status=status,
            disclosed_gaps=disclosed_gaps,
            hard_block_reasons=hard_block_reasons,
            release_quality_score=coverage_fraction,
            safety_floor=safety_floor,
            adjudicated=False,
            body_withheld=True,
            compensating_screen_passed=False,
        )

    # always-release ON, not hard-blocked: decide the body disposition from the screen result.
    # ALWAYS-RELEASE PRINCIPLE (operator-locked: the verifier is a LABEL, never a HOLD): the D8 safety
    # floor being unconfirmed does NOT withhold the body — the report ALWAYS ships and the unadjudicated
    # state is DISCLOSED so the user judges (status=released_insufficient_safety_evidence + the seam
    # disclosure below). safety_floor_insufficient is a LABEL, not a gate. (An earlier change wrongly
    # forced a withhold here; reverted per operator 2026-06-20 — see feedback_always_release.)
    screen_clean = fabrication_screen_ran is True and not fabrication_screen_found_fabrication
    body_withheld = not screen_clean
    compensating_screen_passed = screen_clean
    if not screen_clean:
        # The body is withheld — surface WHY so the withhold is never silent (P0 #3).
        disclosed_gaps.append(_GAP_SEAM_FABRICATION_SCREEN_UNAVAILABLE)

    status = (
        STATUS_RELEASED_INSUFFICIENT_SAFETY
        if safety_floor_insufficient
        else STATUS_RELEASED_WITH_DISCLOSED_GAPS
    )
    return ReleaseOutcome(
        released=True,
        # The body is suppressed when withheld OR when the clinical safety floor blocks the normal
        # render; either way the polished normal report is not shipped as clean.
        hard_block=False,
        normal_release_blocked=body_withheld or safety_floor_insufficient,
        status=status,
        disclosed_gaps=disclosed_gaps,
        hard_block_reasons=[],
        release_quality_score=coverage_fraction,
        safety_floor=safety_floor,
        adjudicated=False,
        body_withheld=body_withheld,
        compensating_screen_passed=compensating_screen_passed,
    )


class ReleaseInvariantError(RuntimeError):
    """Raised by ``assert_release_invariant`` when a release-asserting outcome cannot PROVE the
    four-role D8 judge adjudicated, OR (on a seam) that the un-judged body is provably safe.

    This is the in-process, structural twin of scripts/iarch007_release_invariant_check (the
    artifact-layer CI gate). It is the LAST fail-closed line before the success-path manifest
    write: a path that mis-builds the A2 seam rescue (auto-releasing un-judged content as a
    release-asserting status) raises here rather than shipping an un-judged report.
    """


# Release-asserting statuses: a report ships as clean/judge-final OR honest-disclosed. Each demands
# proof of adjudication OR a provably-safe seam disposition. abort_*/error_*/partial_* are NOT
# release-asserting (the invariant is a no-op on them — no false trip).
_RELEASE_ASSERTING_STATUSES = frozenset(
    {
        STATUS_SUCCESS,
        STATUS_RELEASED_WITH_DISCLOSED_GAPS,
        STATUS_RELEASED_INSUFFICIENT_SAFETY,
    }
)


def assert_release_invariant(outcome: ReleaseOutcome) -> ReleaseOutcome:
    """Fail-closed: refuse any release-asserting outcome that cannot PROVE it is judge-safe.

    Returns ``outcome`` unchanged on PASS; raises ``ReleaseInvariantError`` on a violation. The
    proof is read STRUCTURALLY from the outcome fields (status + adjudicated + body_withheld +
    compensating_screen_passed + the prefix-aware seam-gap detector), NEVER by sniffing an
    arbitrary gap-label string. The accepted shapes (and ONLY these):

      (a) the four-role D8 judge TRULY adjudicated — ``adjudicated=True`` — AND this is NOT a seam
          (a seam disclosure with adjudicated=True is a CONTRADICTION: the default-True-on-seam leak
          this closes), OR
      (b) the SPECIFIC ``four_role_seam_unadjudicated`` gap is disclosed AND a compensating
          standalone fabrication screen ran clean (``compensating_screen_passed`` — leg-3 is COUPLED
          to the specific seam gap; a bare screen flag without the disclosure is NOT proof), OR
      (c) the findings body is WITHHELD (``body_withheld`` — nothing un-judged ships).

    It does NOT accept ``adjudicated=True`` by itself when a seam gap is present (that is the
    contradiction), and does NOT accept an arbitrary non-empty disclosed_gaps list as seam proof.
    Non-release-asserting statuses (abort_*/error_*/partial_*) pass untouched. A ``released``
    that contradicts an abort status is also a violation.
    """
    status = str(outcome.status or "")
    seam_gap = _has_seam_unadjudicated_gap(outcome.disclosed_gaps)

    # Contradiction guard (fires for ANY status, before the per-status legs): a seam disclosure
    # means the judge did NOT adjudicate, so adjudicated=True alongside the seam gap is the
    # default-True-on-seam leak — fail closed.
    if seam_gap and outcome.adjudicated:
        raise ReleaseInvariantError(
            "release outcome carries the four_role_seam_unadjudicated gap AND adjudicated=True — a "
            "contradiction (a judge seam-error means D8 never adjudicated). This is the "
            "default-True-on-seam leak; the seam outcome MUST carry adjudicated=False."
        )

    if status not in _RELEASE_ASSERTING_STATUSES:
        # Not release-asserting. The only remaining check is a released/abort contradiction:
        # a `released`-True outcome whose status is an abort is a self-contradiction.
        if outcome.released and status.startswith("abort"):
            raise ReleaseInvariantError(
                f"released=True but status={status!r} (an abort) — the binding release decision "
                "contradicts the terminal status."
            )
        return outcome

    # The seam-rescue proof (the ONLY way a release-asserting status may ship un-judged): the
    # SPECIFIC seam gap is disclosed AND the body is provably safe — withheld OR a compensating
    # fabrication screen ran clean. An arbitrary disclosed gap is NOT proof (SWEEP-P0).
    seam_rescue_proven = seam_gap and (
        outcome.body_withheld or outcome.compensating_screen_passed
    )

    if outcome.adjudicated or seam_rescue_proven:
        return outcome

    # No real D8 adjudication and no proven-safe seam disposition. A body withheld (even without
    # the seam gap) is still a terminal SAFE disposition — nothing un-judged ships — so accept it.
    if outcome.body_withheld:
        return outcome

    raise ReleaseInvariantError(
        f"status={status!r} asserts a release, but there is NO D8 adjudication "
        "(adjudicated=False) and NO PROVEN seam rescue (the specific four_role_seam_unadjudicated "
        "label PLUS a withheld body OR a passed compensating fabrication screen) and the body is NOT "
        "withheld. A released report with no real judging and no proven-safe disposition is a silent "
        "un-judged release — refused fail-closed."
    )
