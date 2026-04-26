"""Load a V30 Phase-2 run artifact directory into a canonical AuditIR object.

The AuditIR is the single source of truth for the Evidence Inspector and
all derivative renderers. It joins:
- manifest.json (run metadata, frame_coverage_report, corpus tier fractions)
- report.md (the rendered markdown report with [N] inline citations)
- bibliography.json (the [N] -> evidence_id -> source mapping)
- contradictions.json (the 14 tier-labeled disagreement clusters)
- verification_details.json (per-section drop reasons)

into a single immutable object with lookup methods.

Per FINAL_PLAN.md (jointly Claude+Codex agreed):
- The audit graph IR is canonical (NOT the report)
- Evidence Inspector is the primary renderer
- All other outputs are derivative projections with back-links to claim IDs
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class BibliographyEntry:
    """A single source in the bibliography — the [N] -> source mapping."""

    num: int
    evidence_id: str
    statement: str
    tier: str
    url: str


@dataclass(frozen=True)
class ContradictionClaim:
    """One claim inside a contradiction cluster."""

    evidence_id: str
    subject: str
    predicate: str
    arm: str
    dose: str
    value: float
    unit: str
    source_tier: str
    source_url: str
    context_snippet: str
    endpoint_phrase: str


@dataclass(frozen=True)
class ContradictionCluster:
    """A tier-labeled disagreement cluster with N claims that disagree on a predicate."""

    cluster_id: int
    predicate: str
    absolute_difference: float
    claims: tuple[ContradictionClaim, ...]


@dataclass(frozen=True)
class FrameCoverageEntry:
    """One contract-slot entity in the frame coverage report."""

    entity_id: str
    entity_type: str
    status: str
    doi: str | None
    pmid: str | None
    failure_reason: str | None
    available_artifacts: tuple[str, ...]
    required_fields: tuple[str, ...]
    provenance_class: str
    human_completion_eligible: bool
    is_pipeline_fault: bool
    retrieval_attempt_log: tuple[dict[str, Any], ...]


@dataclass(frozen=True)
class FrameCoverageReport:
    """Frame coverage for the whole run — pass / partial / gap counts + per-entity rows."""

    pass_count: int
    partial_count: int
    frame_gap_count: int
    pipeline_fault_count: int
    total_entities: int
    total_slots: int
    research_question: str
    entries: tuple[FrameCoverageEntry, ...]
    schema_version: str


@dataclass(frozen=True)
class TierMix:
    """Tier distribution across the corpus and selected evidence."""

    fractions: dict[str, float]
    corpus_count: int
    approved: bool


@dataclass(frozen=True)
class RunManifest:
    """Top-level run metadata — the audit-bundle header."""

    run_id: str
    slug: str
    status: str
    question: str
    protocol_sha256: str
    cost_usd: float
    budget_cap_usd: float
    word_count: int
    sentences_verified: int
    sentences_dropped: int
    contradictions_found: int
    completeness_percent: float
    evaluator_gate: str
    release_allowed: bool
    v30_enabled: bool


@dataclass(frozen=True)
class AuditIR:
    """The canonical audit graph IR for one V30 Phase-2 run.

    All renderers (Evidence Inspector views 1-5, PDF, DOCX, CSV, charts,
    brief, deck) project from this object and retain back-links to its
    claim IDs.
    """

    run_id: str
    artifact_dir: Path
    report_md: str
    manifest: RunManifest
    bibliography: tuple[BibliographyEntry, ...]
    contradictions: tuple[ContradictionCluster, ...]
    frame_coverage: FrameCoverageReport
    tier_mix: TierMix

    def get_bibliography_by_num(self, num: int) -> BibliographyEntry | None:
        """Look up a bibliography entry by the [N] citation number."""
        for entry in self.bibliography:
            if entry.num == num:
                return entry
        return None

    def get_bibliography_by_evidence_id(
        self, evidence_id: str
    ) -> BibliographyEntry | None:
        """Look up a bibliography entry by evidence_id."""
        for entry in self.bibliography:
            if entry.evidence_id == evidence_id:
                return entry
        return None

    def get_contradictions_for_evidence(
        self, evidence_id: str
    ) -> tuple[ContradictionCluster, ...]:
        """Return all contradiction clusters that contain the given evidence_id."""
        out = []
        for cluster in self.contradictions:
            if any(c.evidence_id == evidence_id for c in cluster.claims):
                out.append(cluster)
        return tuple(out)

    def get_frame_coverage_for_entity(
        self, entity_id: str
    ) -> FrameCoverageEntry | None:
        """Look up a frame coverage entry by entity_id."""
        for entry in self.frame_coverage.entries:
            if entry.entity_id == entity_id:
                return entry
        return None

    def get_tier_counts(self) -> dict[str, int]:
        """Return absolute tier counts derived from fractions × corpus_count."""
        return {
            tier: int(round(frac * self.tier_mix.corpus_count))
            for tier, frac in self.tier_mix.fractions.items()
        }


def _read_json(path: Path) -> Any:
    """Read a JSON file. Fail loudly if missing or malformed."""
    if not path.exists():
        raise FileNotFoundError(f"Required artifact missing: {path}")
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _read_text(path: Path) -> str:
    """Read a text file. Fail loudly if missing."""
    if not path.exists():
        raise FileNotFoundError(f"Required artifact missing: {path}")
    return path.read_text(encoding="utf-8")


def _parse_bibliography(raw: list[dict[str, Any]]) -> tuple[BibliographyEntry, ...]:
    return tuple(
        BibliographyEntry(
            num=int(entry["num"]),
            evidence_id=str(entry["evidence_id"]),
            statement=str(entry.get("statement", "")),
            tier=str(entry.get("tier", "UNKNOWN")),
            url=str(entry.get("url", "")),
        )
        for entry in raw
    )


def _parse_contradictions(
    raw: list[dict[str, Any]],
) -> tuple[ContradictionCluster, ...]:
    clusters = []
    for idx, raw_cluster in enumerate(raw):
        claims = tuple(
            ContradictionClaim(
                evidence_id=str(c.get("evidence_id", "")),
                subject=str(c.get("subject", "")),
                predicate=str(c.get("predicate", "")),
                arm=str(c.get("arm", "")),
                dose=str(c.get("dose", "")),
                value=float(c.get("value", 0.0)),
                unit=str(c.get("unit", "")),
                source_tier=str(c.get("source_tier", "UNKNOWN")),
                source_url=str(c.get("source_url", "")),
                context_snippet=str(c.get("context_snippet", "")),
                endpoint_phrase=str(c.get("endpoint_phrase", "")),
            )
            for c in raw_cluster.get("claims", [])
        )
        clusters.append(
            ContradictionCluster(
                cluster_id=idx,
                predicate=str(raw_cluster.get("predicate", "")),
                absolute_difference=float(raw_cluster.get("absolute_difference", 0.0)),
                claims=claims,
            )
        )
    return tuple(clusters)


def _parse_frame_coverage(raw: dict[str, Any]) -> FrameCoverageReport:
    entries = tuple(
        FrameCoverageEntry(
            entity_id=str(e.get("entity_id", "")),
            entity_type=str(e.get("entity_type", "")),
            status=str(e.get("status", "")),
            doi=e.get("doi"),
            pmid=e.get("pmid"),
            failure_reason=e.get("failure_reason"),
            available_artifacts=tuple(e.get("available_artifacts", [])),
            required_fields=tuple(e.get("required_fields", [])),
            provenance_class=str(e.get("provenance_class", "")),
            human_completion_eligible=bool(e.get("human_completion_eligible", False)),
            is_pipeline_fault=bool(e.get("is_pipeline_fault", False)),
            retrieval_attempt_log=tuple(e.get("retrieval_attempt_log", [])),
        )
        for e in raw.get("entries", [])
    )
    by_status = raw.get("by_status", {})
    return FrameCoverageReport(
        pass_count=int(by_status.get("pass", raw.get("pass_count", 0))),
        partial_count=int(by_status.get("partial", raw.get("partial_count", 0))),
        frame_gap_count=int(raw.get("frame_gap_count", 0)),
        pipeline_fault_count=int(raw.get("pipeline_fault_count", 0)),
        total_entities=int(raw.get("total_entities", 0)),
        total_slots=int(raw.get("total_slots", 0)),
        research_question=str(raw.get("research_question", "")),
        entries=entries,
        schema_version=str(raw.get("schema_version", "1.0")),
    )


def _parse_tier_mix(corpus: dict[str, Any]) -> TierMix:
    return TierMix(
        fractions=dict(corpus.get("tier_fractions", {})),
        corpus_count=int(corpus.get("count", 0)),
        approved=bool(corpus.get("approved", False)),
    )


def _parse_manifest(raw: dict[str, Any]) -> RunManifest:
    generator = raw.get("generator", {})
    completeness = raw.get("completeness", {})
    evaluator = raw.get("evaluator_gate", {})
    if isinstance(evaluator, dict):
        gate_class = str(evaluator.get("gate_class", "unknown"))
        release_allowed = bool(evaluator.get("release_allowed", False))
    else:
        gate_class = str(evaluator)
        release_allowed = bool(raw.get("release_allowed", False))

    completeness_pct = 0.0
    if isinstance(completeness, dict):
        covered = completeness.get("covered_topics") or completeness.get("covered")
        total = completeness.get("total_topics") or completeness.get("total")
        if covered is not None and total:
            completeness_pct = (float(covered) / float(total)) * 100.0

    return RunManifest(
        run_id=str(raw.get("run_id", "")),
        slug=str(raw.get("slug", "")),
        status=str(raw.get("status", "")),
        question=str(raw.get("question", "")),
        protocol_sha256=str(raw.get("protocol_sha256", "")),
        cost_usd=float(raw.get("cost_usd", 0.0)),
        budget_cap_usd=float(raw.get("budget_cap_usd", 0.0)),
        word_count=int(generator.get("words", 0)),
        sentences_verified=int(generator.get("sentences_verified", 0)),
        sentences_dropped=int(generator.get("sentences_dropped", 0)),
        contradictions_found=int(raw.get("contradictions_found", 0)),
        completeness_percent=completeness_pct,
        evaluator_gate=gate_class,
        release_allowed=release_allowed,
        v30_enabled=bool(raw.get("v30_enabled", False)),
    )


def load_audit_ir(artifact_dir: Path | str) -> AuditIR:
    """Load a V30 Phase-2 run artifact directory into a canonical AuditIR.

    Required files in artifact_dir:
        manifest.json
        report.md
        bibliography.json
        contradictions.json

    Raises FileNotFoundError if any required file is missing.
    """
    artifact_dir = Path(artifact_dir)
    if not artifact_dir.is_dir():
        raise NotADirectoryError(f"artifact_dir is not a directory: {artifact_dir}")

    manifest_raw = _read_json(artifact_dir / "manifest.json")
    report_md = _read_text(artifact_dir / "report.md")
    bibliography_raw = _read_json(artifact_dir / "bibliography.json")
    contradictions_raw = _read_json(artifact_dir / "contradictions.json")

    manifest = _parse_manifest(manifest_raw)
    bibliography = _parse_bibliography(bibliography_raw)
    contradictions = _parse_contradictions(contradictions_raw)
    frame_coverage = _parse_frame_coverage(manifest_raw.get("frame_coverage_report", {}))
    tier_mix = _parse_tier_mix(manifest_raw.get("corpus", {}))

    return AuditIR(
        run_id=manifest.run_id,
        artifact_dir=artifact_dir,
        report_md=report_md,
        manifest=manifest,
        bibliography=bibliography,
        contradictions=contradictions,
        frame_coverage=frame_coverage,
        tier_mix=tier_mix,
    )
