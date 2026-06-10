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
    if needs_rewrite:
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
# DEFAULT OFF: PG_ALWAYS_RELEASE unset/0/false/no/off -> compute_release_outcome reproduces the
# legacy `release_allowed` decision verbatim (byte-identical; no status/label change).

# Master flag (default OFF -> legacy withhold behaviour, byte-identical). ON only on an EXPLICIT
# truthy token (Codex slice-1 P2: a stray value like "garbage" must NOT silently enable it).
_ENV_ALWAYS_RELEASE = "PG_ALWAYS_RELEASE"
_ON_VALUES = frozenset({"1", "true", "yes", "on"})

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


def is_hard_block(
    *,
    fabricated_occurrence_latched: bool,
    zero_verified: bool,
    zero_usable_evidence: bool,
) -> bool:
    """The canonical no-fabrication hard line (blueprint R1): a report is HARD-blocked iff a
    FABRICATED occurrence latched OR there is true zero-grounding (no VERIFIED claim AND no usable
    evidence). Everything else releases (with labels) under always-release."""
    return bool(fabricated_occurrence_latched or (zero_verified and zero_usable_evidence))


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


def always_release_enabled() -> bool:
    """PG_ALWAYS_RELEASE (default OFF). ON only on explicit truthy ('1'/'true'/'yes'/'on')."""
    import os

    return os.environ.get(_ENV_ALWAYS_RELEASE, "").strip().lower() in _ON_VALUES


def compute_release_outcome(
    decision: ReleaseDecision,
    *,
    zero_verified: bool,
    zero_usable_evidence: bool,
    safety_floor_insufficient: bool,
    coverage_fraction: float,
    always_release: bool | None = None,
) -> ReleaseOutcome:
    """Map a D8 ``ReleaseDecision`` to a release outcome under the always-release reframe.

    When always-release is OFF (default), reproduce the LEGACY decision verbatim: ``released`` ==
    ``decision.release_allowed``, the held reasons stay blockers, and the status is the legacy
    held/success label — byte-identical behaviour. When ON, convert non-hard holds to disclosed
    gaps and release, keeping only the fabricated/zero-grounding hard line and the clinical
    safety-floor normal-render block (blueprint R1/R2).
    """
    enabled = always_release_enabled() if always_release is None else always_release
    hard_block = is_hard_block(
        fabricated_occurrence_latched=decision.fabricated_occurrence_latched,
        zero_verified=zero_verified,
        zero_usable_evidence=zero_usable_evidence,
    )
    hard_block_reasons: list[str] = []
    if decision.fabricated_occurrence_latched:
        hard_block_reasons.append(_REASON_FABRICATED_OCCURRENCE)
    if zero_verified and zero_usable_evidence:
        hard_block_reasons.append("zero_grounding")
    safety_floor = "insufficient" if safety_floor_insufficient else "ok"

    if not enabled:
        # Legacy withhold path — byte-identical to `decision.release_allowed`.
        status = STATUS_SUCCESS if decision.release_allowed else STATUS_ABORT_FOUR_ROLE_HELD
        return ReleaseOutcome(
            released=decision.release_allowed,
            hard_block=not decision.release_allowed and hard_block,
            normal_release_blocked=not decision.release_allowed,
            status=status,
            disclosed_gaps=[],
            hard_block_reasons=hard_block_reasons if not decision.release_allowed else [],
            release_quality_score=coverage_fraction,
            safety_floor=safety_floor,
        )

    # --- always-release ON ---
    if hard_block:
        status = (
            STATUS_ABORT_FABRICATED
            if decision.fabricated_occurrence_latched
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
        )

    # Every remaining held reason is a DISPLAYED disclosed-gap label, not a blocker.
    disclosed_gaps = list(decision.held_reasons)
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
    )
