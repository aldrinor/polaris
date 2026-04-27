"""Run diff (M-16 — Phase C).

Per FINAL_PLAN.md Phase C deliverable #6: "run diff" — given two
run_ids of the same template+slug, emit a structured diff of the
material claims/evidence/contradictions changes.

Use cases:
  - Operator wants to know what changed between yesterday's audit
    and today's audit of the same drug+condition.
  - Regression alerts (M-18) can call into this to detect
    materially different runs and surface them for human review.
  - Customer support flow (M-24) shows users why a re-run produced
    different output.

What's a "material" change vs a noise change:

  MATERIAL (surfaced in the diff):
    - Added or removed claims (verified vs unverified status).
    - Added or removed evidence sources.
    - Resolved or new contradictions.
    - Source-tier mix shift > 10 percentage points on any tier.

  NOISE (suppressed):
    - Identical claims with token-level whitespace differences.
    - Re-ordering of evidence within the same source.
    - Cost / wall-clock differences (those are surfaced in
      manifest, not the diff).
    - Model version differences (surfaced in manifest, not diff).

Output is a structured `RunDiff` dataclass. The renderer (HTML
or JSON via the API) projects it.

Per LAW II:
  - Two unrelated runs (different template_id, different slug)
    raise ValueError. The diff makes no sense across templates.
  - Missing-side runs raise ValueError. The diff is symmetric;
    callers must provide both.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any

from src.polaris_graph.audit_ir.loader import AuditIR


# ---------------------------------------------------------------------------
# Records
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ClaimDelta:
    """One claim that's been added or removed.

    `direction` is "added" (in B not A) or "removed" (in A not B).
    `claim_id` is the stable claim identifier so the renderer can
    cross-reference into the AuditIR.
    """

    direction: str
    claim_id: str
    section: str
    text: str
    is_verified: bool


@dataclass(frozen=True)
class EvidenceDelta:
    """One evidence source added or removed."""

    direction: str
    evidence_id: str
    statement: str
    tier: str
    url: str


@dataclass(frozen=True)
class ContradictionDelta:
    """One contradiction added or removed across runs.

    `subject` and `predicate` are the stable cross-run handle
    (cluster_id is an int auto-assigned per-run and not stable).
    """

    direction: str
    subject: str
    predicate: str
    severity: str


@dataclass(frozen=True)
class TierMixShift:
    """One tier whose share moved more than the threshold."""

    tier: str  # "tier1", "tier2", "tier3", "tier4"
    a_pct: float
    b_pct: float
    delta_pp: float  # b_pct - a_pct in percentage points


@dataclass(frozen=True)
class RunDiff:
    """Top-level diff record returned by `diff_runs`.

    Codex M-16 design note: AuditIR.manifest doesn't carry a
    template_id field; the audit shape is identified by `slug`
    (e.g. "clinical_tirzepatide_t2dm"). Both runs must share the
    same slug to be diffable. If users later need cross-template
    comparisons (e.g. v30_clinical vs v34_clinical for the same
    drug), that's a separate feature.
    """

    a_run_id: str
    b_run_id: str
    slug: str  # both runs must share this
    claim_deltas: tuple[ClaimDelta, ...] = field(default_factory=tuple)
    evidence_deltas: tuple[EvidenceDelta, ...] = field(default_factory=tuple)
    contradiction_deltas: tuple[ContradictionDelta, ...] = field(default_factory=tuple)
    tier_shifts: tuple[TierMixShift, ...] = field(default_factory=tuple)


# ---------------------------------------------------------------------------
# Defaults (LAW VI — env-overridable)
# ---------------------------------------------------------------------------


import os


def _tier_shift_threshold_pp() -> float:
    """Return the percentage-point threshold above which a tier
    mix shift counts as material. Env: PG_RUN_DIFF_TIER_PP
    (default 10.0). LAW VI."""
    raw = os.environ.get("PG_RUN_DIFF_TIER_PP")
    if raw is None:
        return 10.0
    try:
        return max(0.0, float(raw))
    except ValueError:
        return 10.0


# ---------------------------------------------------------------------------
# Diff computation
# ---------------------------------------------------------------------------


def _normalize_claim_text(text: str) -> str:
    """Whitespace-normalize claim text so trivial reformatting
    doesn't surface as a material change."""
    return " ".join((text or "").split()).strip()


def _claims_by_id(ir: AuditIR) -> dict[str, Any]:
    """Map claim_id → ReportSentence across all sections.

    AuditIR's verified_report.sections is a tuple of ReportSection,
    each with a `sentences` tuple of ReportSentence. claim_id is
    stable per (artifact_dir, section, status, idx)."""
    out: dict[str, Any] = {}
    for section in ir.verified_report.sections:
        for sentence in section.sentences:
            out[sentence.claim_id] = sentence
    return out


def _evidence_by_id(ir: AuditIR) -> dict[str, Any]:
    """Map evidence_id → BibliographyEntry."""
    out: dict[str, Any] = {}
    for entry in ir.bibliography:
        out[entry.evidence_id] = entry
    return out


def _contradictions_by_subject(ir: AuditIR) -> dict[str, Any]:
    """Map (subject, predicate) → ContradictionCluster.

    Codex M-16 note: ContradictionCluster.cluster_id is an
    int auto-assigned by the loader (idx). It's NOT stable
    across runs — re-running the audit can re-order clusters
    and produce different cluster_ids for the same disagreement.
    The stable handle is (subject, predicate), which describes
    what the cluster is ABOUT.
    """
    out: dict[str, Any] = {}
    for cluster in ir.contradictions:
        subject = getattr(cluster, "subject", "") or ""
        predicate = getattr(cluster, "predicate", "") or ""
        key = f"{subject}|{predicate}"
        out[key] = cluster
    return out


def _diff_claims(ir_a: AuditIR, ir_b: AuditIR) -> tuple[ClaimDelta, ...]:
    a_map = _claims_by_id(ir_a)
    b_map = _claims_by_id(ir_b)
    deltas: list[ClaimDelta] = []
    # In A not B → removed.
    for cid, sa in a_map.items():
        if cid not in b_map:
            deltas.append(ClaimDelta(
                direction="removed",
                claim_id=cid,
                section=sa.section,
                text=_normalize_claim_text(sa.text),
                is_verified=sa.is_verified,
            ))
    # In B not A → added.
    for cid, sb in b_map.items():
        if cid not in a_map:
            deltas.append(ClaimDelta(
                direction="added",
                claim_id=cid,
                section=sb.section,
                text=_normalize_claim_text(sb.text),
                is_verified=sb.is_verified,
            ))
    # Stable order for deterministic output.
    deltas.sort(key=lambda d: (d.direction, d.section, d.claim_id))
    return tuple(deltas)


def _diff_evidence(ir_a: AuditIR, ir_b: AuditIR) -> tuple[EvidenceDelta, ...]:
    a_map = _evidence_by_id(ir_a)
    b_map = _evidence_by_id(ir_b)
    deltas: list[EvidenceDelta] = []
    for eid, ea in a_map.items():
        if eid not in b_map:
            deltas.append(EvidenceDelta(
                direction="removed",
                evidence_id=eid,
                statement=getattr(ea, "statement", "") or "",
                tier=getattr(ea, "tier", "") or "",
                url=getattr(ea, "url", "") or "",
            ))
    for eid, eb in b_map.items():
        if eid not in a_map:
            deltas.append(EvidenceDelta(
                direction="added",
                evidence_id=eid,
                statement=getattr(eb, "statement", "") or "",
                tier=getattr(eb, "tier", "") or "",
                url=getattr(eb, "url", "") or "",
            ))
    deltas.sort(key=lambda d: (d.direction, d.evidence_id))
    return tuple(deltas)


def _diff_contradictions(
    ir_a: AuditIR, ir_b: AuditIR,
) -> tuple[ContradictionDelta, ...]:
    a_map = _contradictions_by_subject(ir_a)
    b_map = _contradictions_by_subject(ir_b)
    deltas: list[ContradictionDelta] = []
    for key, ca in a_map.items():
        if key not in b_map:
            deltas.append(ContradictionDelta(
                direction="removed",
                subject=getattr(ca, "subject", "") or "",
                predicate=getattr(ca, "predicate", "") or "",
                severity=getattr(ca, "severity", "") or "",
            ))
    for key, cb in b_map.items():
        if key not in a_map:
            deltas.append(ContradictionDelta(
                direction="added",
                subject=getattr(cb, "subject", "") or "",
                predicate=getattr(cb, "predicate", "") or "",
                severity=getattr(cb, "severity", "") or "",
            ))
    deltas.sort(key=lambda d: (d.direction, d.subject, d.predicate))
    return tuple(deltas)


def _tier_pcts(ir: AuditIR) -> dict[str, float]:
    """Compute tier percentages from the AuditIR tier_mix.

    AuditIR.tier_mix.fractions is a Mapping[tier_label, fraction]
    where fractions sum to 1.0. Convert to percentages."""
    tm = ir.tier_mix
    fractions = dict(tm.fractions or {})
    return {
        tier: 100.0 * float(fractions.get(tier, 0.0))
        for tier in ("tier1", "tier2", "tier3", "tier4")
    }


def _diff_tier_mix(
    ir_a: AuditIR, ir_b: AuditIR, threshold_pp: float,
) -> tuple[TierMixShift, ...]:
    a_pcts = _tier_pcts(ir_a)
    b_pcts = _tier_pcts(ir_b)
    shifts: list[TierMixShift] = []
    for tier in ("tier1", "tier2", "tier3", "tier4"):
        delta = b_pcts[tier] - a_pcts[tier]
        if abs(delta) >= threshold_pp:
            shifts.append(TierMixShift(
                tier=tier, a_pct=a_pcts[tier], b_pct=b_pcts[tier],
                delta_pp=delta,
            ))
    shifts.sort(key=lambda s: s.tier)
    return tuple(shifts)


def diff_runs(ir_a: AuditIR, ir_b: AuditIR) -> RunDiff:
    """Compute a structured diff between two AuditIR runs.

    Both runs MUST share `slug`. The diff doesn't make sense
    across different audit shapes.

    Per LAW II — fails LOUD on slug mismatch.
    """
    slug_a = ir_a.manifest.slug or ""
    slug_b = ir_b.manifest.slug or ""
    if slug_a != slug_b:
        raise ValueError(
            f"diff_runs: slug mismatch a={slug_a!r} b={slug_b!r}"
        )

    threshold_pp = _tier_shift_threshold_pp()
    return RunDiff(
        a_run_id=ir_a.manifest.run_id,
        b_run_id=ir_b.manifest.run_id,
        slug=slug_a,
        claim_deltas=_diff_claims(ir_a, ir_b),
        evidence_deltas=_diff_evidence(ir_a, ir_b),
        contradiction_deltas=_diff_contradictions(ir_a, ir_b),
        tier_shifts=_diff_tier_mix(ir_a, ir_b, threshold_pp),
    )


def diff_to_dict(d: RunDiff) -> dict[str, Any]:
    """JSON-serializable projection."""
    return {
        "a_run_id": d.a_run_id,
        "b_run_id": d.b_run_id,
        "slug": d.slug,
        "claim_deltas": [asdict(c) for c in d.claim_deltas],
        "evidence_deltas": [asdict(e) for e in d.evidence_deltas],
        "contradiction_deltas": [asdict(c) for c in d.contradiction_deltas],
        "tier_shifts": [asdict(t) for t in d.tier_shifts],
    }


def is_material(d: RunDiff) -> bool:
    """Return True if the diff contains ANY material change.
    Used by M-18 regression-alerts to decide whether to fire."""
    return bool(
        d.claim_deltas or d.evidence_deltas
        or d.contradiction_deltas or d.tier_shifts
    )
