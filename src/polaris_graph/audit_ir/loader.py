"""Load a V30 Phase-2 run artifact directory into a canonical AuditIR object.

The AuditIR is the single source of truth for the Evidence Inspector and
all derivative renderers. It joins:
- manifest.json (run metadata, frame_coverage_report, corpus tier fractions,
  evaluator gate, v30 warnings, retrieval stats)
- report.md (the rendered markdown report with [N] inline citations)
- bibliography.json (the [N] -> evidence_id -> source mapping)
- contradictions.json (the 14 tier-labeled disagreement clusters with severity)
- verification_details.json (per-section sentences + evidence-span tokens —
  this is the foundation for Evidence Inspector View 1 click-to-inspect)

into a single immutable object with lookup methods.

Per FINAL_PLAN.md (jointly Claude+Codex agreed):
- The audit graph IR is canonical (NOT the report)
- Evidence Inspector is the primary renderer
- All other outputs are derivative projections with back-links to claim IDs

Fail-loud semantics: missing or malformed required schema blocks raise
loudly. There is no silent zero-fill on canonical structures. This is the
audit-grade discipline applied to the IR itself.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping

# Bumped on schema-breaking changes. Renderers should check this and refuse
# to render IR they don't know how to project.
IR_SCHEMA_VERSION = "1.0.0"


# ---------------------------------------------------------------------------
# Bibliography
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class BibliographyEntry:
    """A single source in the bibliography — the [N] -> source mapping."""

    num: int
    evidence_id: str
    statement: str
    tier: str
    url: str


# ---------------------------------------------------------------------------
# Verified report (verification_details.json)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EvidenceSpanToken:
    """A `[#ev:<evidence_id>:<start>-<end>]` token bound to a sentence."""

    evidence_id: str
    start: int
    end: int


@dataclass(frozen=True)
class ReportSentence:
    """One sentence in the verified report — kept or dropped.

    `claim_id` is stable for the same artifact_dir: `<section>:<status>:<idx>`.
    Renderers (Evidence Inspector view 1) overlay these IDs onto the rendered
    `report.md` prose and use them as the click-to-inspect handle.
    """

    claim_id: str
    section: str
    text: str
    tokens: tuple[EvidenceSpanToken, ...]
    is_verified: bool
    failure_reasons: tuple[str, ...]


@dataclass(frozen=True)
class ReportSection:
    """One section in the verified report — title plus all its sentences."""

    title: str
    kept_count: int
    dropped_count: int
    total_in: int
    dropped_due_to_failure: int
    sentences: tuple[ReportSentence, ...]


@dataclass(frozen=True)
class VerifiedReport:
    """The full per-sentence verified report.

    `drop_reason_counts` is a read-only mapping from reason -> count.
    """

    sections: tuple[ReportSection, ...]
    sentences_verified: int
    sentences_dropped: int
    drop_reason_counts: Mapping[str, int]


# ---------------------------------------------------------------------------
# Contradictions
# ---------------------------------------------------------------------------


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
    """A tier-labeled disagreement cluster — extended with severity + action."""

    cluster_id: int
    subject: str
    predicate: str
    severity: str
    absolute_difference: float
    relative_difference: float
    recommended_action: str
    claims: tuple[ContradictionClaim, ...]


# ---------------------------------------------------------------------------
# Frame coverage
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RetrievalAttempt:
    """One retrieval attempt against an external source — frozen leaf."""

    attempt_index: int
    source: str
    url: str
    outcome: str
    http_status: int | None


@dataclass(frozen=True)
class FrameCoverageEntry:
    """One contract-slot entity in the frame coverage report.

    Includes section / slot_id / subsection_title (back-link into report
    structure) and min_fields_for_completion / human_curated_provenance
    (operator-completion workflow inputs).
    """

    entity_id: str
    entity_type: str
    section: str
    slot_id: str
    subsection_title: str
    status: str
    doi: str | None
    pmid: str | None
    failure_reason: str | None
    available_artifacts: tuple[str, ...]
    required_fields: tuple[str, ...]
    min_fields_for_completion: int
    provenance_class: str
    human_completion_eligible: bool
    human_curated_provenance: str | None
    is_pipeline_fault: bool
    retrieval_attempt_log: tuple[RetrievalAttempt, ...]


@dataclass(frozen=True)
class FrameCoverageReport:
    """Frame coverage for the whole run.

    `semantics_warning` preserves the V30 disclaimer that current
    `frame_coverage_report` reflects retrieval success, NOT verified-report
    coverage. Inspector view 3 must surface this.
    """

    pass_count: int
    partial_count: int
    frame_gap_count: int
    pipeline_fault_count: int
    total_entities: int
    total_slots: int
    research_question: str
    schema_version: str
    semantics_warning: str | None
    entries: tuple[FrameCoverageEntry, ...]


# ---------------------------------------------------------------------------
# Tier mix
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TierMix:
    """Tier distribution across the corpus.

    `fractions` is a read-only Mapping[str, float]; mutation is rejected.
    """

    fractions: Mapping[str, float]
    corpus_count: int
    approved: bool
    material_deviation: bool


# ---------------------------------------------------------------------------
# Evaluator gate
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EvaluatorGate:
    """The evaluator gate verdict — extended with reasons + rule blockers."""

    gate_class: str
    release_allowed: bool
    reasons: tuple[str, ...]
    rule_blockers: tuple[str, ...]
    qwen_critical_axes: tuple[str, ...]
    qwen_parse_ok: bool


# ---------------------------------------------------------------------------
# Retrieval stats
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RetrievalStats:
    """Top-level retrieval counts for the run."""

    pre_filter: int
    fetched: int
    failed: int
    by_provider: Mapping[str, int]


# ---------------------------------------------------------------------------
# Run manifest
# ---------------------------------------------------------------------------


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
    evaluator_gate: EvaluatorGate
    release_allowed: bool
    v30_enabled: bool
    v30_warnings: tuple[str, ...]
    retrieval_stats: RetrievalStats | None


# ---------------------------------------------------------------------------
# Top-level AuditIR
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AuditIR:
    """The canonical audit graph IR for one V30 Phase-2 run.

    All renderers (Evidence Inspector views 1-5, PDF, DOCX, CSV, charts,
    brief, deck) project from this object and retain back-links to its
    claim IDs.

    `ir_schema_version` lets future runs (V31, V32, V34) declare schema
    changes; renderers should check it and refuse unknown major versions.
    """

    ir_schema_version: str
    run_id: str
    artifact_dir: Path
    report_md: str
    manifest: RunManifest
    bibliography: tuple[BibliographyEntry, ...]
    contradictions: tuple[ContradictionCluster, ...]
    frame_coverage: FrameCoverageReport
    tier_mix: TierMix
    verified_report: VerifiedReport

    def get_bibliography_by_num(self, num: int) -> BibliographyEntry | None:
        for entry in self.bibliography:
            if entry.num == num:
                return entry
        return None

    def get_bibliography_by_evidence_id(
        self, evidence_id: str
    ) -> BibliographyEntry | None:
        for entry in self.bibliography:
            if entry.evidence_id == evidence_id:
                return entry
        return None

    def get_contradictions_for_evidence(
        self, evidence_id: str
    ) -> tuple[ContradictionCluster, ...]:
        out = []
        for cluster in self.contradictions:
            if any(c.evidence_id == evidence_id for c in cluster.claims):
                out.append(cluster)
        return tuple(out)

    def get_frame_coverage_for_entity(
        self, entity_id: str
    ) -> FrameCoverageEntry | None:
        for entry in self.frame_coverage.entries:
            if entry.entity_id == entity_id:
                return entry
        return None

    def get_tier_counts(self) -> dict[str, int]:
        return {
            tier: int(round(frac * self.tier_mix.corpus_count))
            for tier, frac in self.tier_mix.fractions.items()
        }

    def get_sentence_by_claim_id(self, claim_id: str) -> ReportSentence | None:
        """Foundation lookup for Evidence Inspector view 1 (Report click-to-inspect)."""
        for section in self.verified_report.sections:
            for sentence in section.sentences:
                if sentence.claim_id == claim_id:
                    return sentence
        return None

    def get_evidence_spans_for_claim(
        self, claim_id: str
    ) -> tuple[EvidenceSpanToken, ...]:
        sentence = self.get_sentence_by_claim_id(claim_id)
        return sentence.tokens if sentence is not None else ()


# ---------------------------------------------------------------------------
# Loader internals
# ---------------------------------------------------------------------------


class AuditIRSchemaError(ValueError):
    """Raised when an artifact directory violates the canonical schema."""


def _read_json(path: Path) -> Any:
    if not path.exists():
        raise FileNotFoundError(f"Required artifact missing: {path}")
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _read_text(path: Path) -> str:
    if not path.exists():
        raise FileNotFoundError(f"Required artifact missing: {path}")
    return path.read_text(encoding="utf-8")


def _require_keys(d: Mapping[str, Any], keys: tuple[str, ...], where: str) -> None:
    missing = [k for k in keys if k not in d]
    if missing:
        raise AuditIRSchemaError(
            f"{where}: required keys missing: {missing}"
        )


def _parse_bibliography(raw: list[dict[str, Any]]) -> tuple[BibliographyEntry, ...]:
    if not isinstance(raw, list):
        raise AuditIRSchemaError("bibliography.json: expected a list")
    out = []
    for i, entry in enumerate(raw):
        _require_keys(entry, ("num", "evidence_id"), f"bibliography[{i}]")
        out.append(
            BibliographyEntry(
                num=int(entry["num"]),
                evidence_id=str(entry["evidence_id"]),
                statement=str(entry.get("statement", "")),
                tier=str(entry.get("tier", "UNKNOWN")),
                url=str(entry.get("url", "")),
            )
        )
    return tuple(out)


def _parse_contradiction_claim(
    raw: Mapping[str, Any], where: str
) -> ContradictionClaim:
    _require_keys(raw, ("evidence_id", "predicate", "value"), where)
    return ContradictionClaim(
        evidence_id=str(raw["evidence_id"]),
        subject=str(raw.get("subject", "")),
        predicate=str(raw["predicate"]),
        arm=str(raw.get("arm", "")),
        dose=str(raw.get("dose", "")),
        value=float(raw["value"]),
        unit=str(raw.get("unit", "")),
        source_tier=str(raw.get("source_tier", "UNKNOWN")),
        source_url=str(raw.get("source_url", "")),
        context_snippet=str(raw.get("context_snippet", "")),
        endpoint_phrase=str(raw.get("endpoint_phrase", "")),
    )


def _parse_contradictions(
    raw: list[dict[str, Any]],
) -> tuple[ContradictionCluster, ...]:
    if not isinstance(raw, list):
        raise AuditIRSchemaError("contradictions.json: expected a list")
    clusters = []
    for idx, raw_cluster in enumerate(raw):
        where = f"contradictions[{idx}]"
        _require_keys(raw_cluster, ("predicate", "claims"), where)
        claims_raw = raw_cluster["claims"]
        if not isinstance(claims_raw, list) or len(claims_raw) < 2:
            raise AuditIRSchemaError(
                f"{where}: 'claims' must be a list of >=2 entries"
            )
        claims = tuple(
            _parse_contradiction_claim(c, f"{where}.claims[{j}]")
            for j, c in enumerate(claims_raw)
        )
        clusters.append(
            ContradictionCluster(
                cluster_id=idx,
                subject=str(raw_cluster.get("subject", "")),
                predicate=str(raw_cluster["predicate"]),
                severity=str(raw_cluster.get("severity", "unknown")),
                absolute_difference=float(raw_cluster.get("absolute_difference", 0.0)),
                relative_difference=float(raw_cluster.get("relative_difference", 0.0)),
                recommended_action=str(raw_cluster.get("recommended_action", "")),
                claims=claims,
            )
        )
    return tuple(clusters)


def _parse_retrieval_attempt(raw: Mapping[str, Any]) -> RetrievalAttempt:
    return RetrievalAttempt(
        attempt_index=int(raw.get("attempt_index", 0)),
        source=str(raw.get("source", "")),
        url=str(raw.get("url", "")),
        outcome=str(raw.get("outcome", "")),
        http_status=(int(raw["http_status"]) if raw.get("http_status") is not None else None),
    )


def _parse_frame_coverage_entry(
    raw: Mapping[str, Any], where: str
) -> FrameCoverageEntry:
    _require_keys(raw, ("entity_id", "status"), where)
    return FrameCoverageEntry(
        entity_id=str(raw["entity_id"]),
        entity_type=str(raw.get("entity_type", "")),
        section=str(raw.get("section", "")),
        slot_id=str(raw.get("slot_id", "")),
        subsection_title=str(raw.get("subsection_title", "")),
        status=str(raw["status"]),
        doi=raw.get("doi"),
        pmid=raw.get("pmid"),
        failure_reason=raw.get("failure_reason"),
        available_artifacts=tuple(raw.get("available_artifacts", [])),
        required_fields=tuple(raw.get("required_fields", [])),
        min_fields_for_completion=int(raw.get("min_fields_for_completion", 0)),
        provenance_class=str(raw.get("provenance_class", "")),
        human_completion_eligible=bool(raw.get("human_completion_eligible", False)),
        human_curated_provenance=raw.get("human_curated_provenance"),
        is_pipeline_fault=bool(raw.get("is_pipeline_fault", False)),
        retrieval_attempt_log=tuple(
            _parse_retrieval_attempt(r)
            for r in raw.get("retrieval_attempt_log", [])
        ),
    )


def _parse_frame_coverage(
    raw: Mapping[str, Any] | None, v30_warnings: tuple[str, ...]
) -> FrameCoverageReport:
    if not isinstance(raw, Mapping):
        raise AuditIRSchemaError(
            "manifest.frame_coverage_report: required block missing or not a dict"
        )
    _require_keys(raw, ("entries", "by_status"), "manifest.frame_coverage_report")
    entries = tuple(
        _parse_frame_coverage_entry(e, f"frame_coverage_report.entries[{i}]")
        for i, e in enumerate(raw["entries"])
    )
    by_status = raw["by_status"]
    semantics_warning = None
    for warning in v30_warnings:
        if "frame_coverage_report" in warning or "phase1_retrieval_coverage_only" in warning:
            semantics_warning = warning
            break
    return FrameCoverageReport(
        pass_count=int(by_status.get("pass", 0)),
        partial_count=int(by_status.get("partial", 0)),
        frame_gap_count=int(raw.get("frame_gap_count", 0)),
        pipeline_fault_count=int(raw.get("pipeline_fault_count", 0)),
        total_entities=int(raw.get("total_entities", 0)),
        total_slots=int(raw.get("total_slots", 0)),
        research_question=str(raw.get("research_question", "")),
        schema_version=str(raw.get("schema_version", "1.0")),
        semantics_warning=semantics_warning,
        entries=entries,
    )


def _parse_tier_mix(corpus: Mapping[str, Any] | None) -> TierMix:
    if not isinstance(corpus, Mapping):
        raise AuditIRSchemaError("manifest.corpus: required block missing or not a dict")
    _require_keys(corpus, ("tier_fractions", "count"), "manifest.corpus")
    fractions = {str(k): float(v) for k, v in corpus["tier_fractions"].items()}
    return TierMix(
        fractions=MappingProxyType(fractions),
        corpus_count=int(corpus["count"]),
        approved=bool(corpus.get("approved", False)),
        material_deviation=bool(corpus.get("material_deviation", False)),
    )


def _parse_evaluator_gate(raw: Any) -> EvaluatorGate:
    if not isinstance(raw, Mapping):
        # Some legacy artifacts stored evaluator_gate as a string class.
        return EvaluatorGate(
            gate_class=str(raw) if raw else "unknown",
            release_allowed=False,
            reasons=(),
            rule_blockers=(),
            qwen_critical_axes=(),
            qwen_parse_ok=False,
        )
    return EvaluatorGate(
        gate_class=str(raw.get("gate_class", "unknown")),
        release_allowed=bool(raw.get("release_allowed", False)),
        reasons=tuple(str(r) for r in raw.get("reasons", [])),
        rule_blockers=tuple(str(r) for r in raw.get("rule_blockers", [])),
        qwen_critical_axes=tuple(str(a) for a in raw.get("qwen_critical_axes", [])),
        qwen_parse_ok=bool(raw.get("qwen_parse_ok", False)),
    )


def _parse_retrieval_stats(raw: Any) -> RetrievalStats | None:
    if not isinstance(raw, Mapping):
        return None
    api_calls = raw.get("api_calls", {})
    if not isinstance(api_calls, Mapping):
        api_calls = {}
    by_provider: dict[str, int] = {}
    for k, v in api_calls.items():
        try:
            by_provider[str(k)] = int(v)
        except (TypeError, ValueError):
            continue
    return RetrievalStats(
        pre_filter=int(raw.get("pre_filter", 0)),
        fetched=int(raw.get("fetched", 0)),
        failed=int(raw.get("failed", 0)),
        by_provider=MappingProxyType(by_provider),
    )


def _parse_completeness_percent(raw: Any) -> float:
    """Compute completeness as a percentage, 0.0–100.0.

    V30 manifests use either:
      - {covered_fraction: 0.0–1.0}
      - {total_covered: int, total_applicable: int}
      - older keys: {covered_topics, total_topics} or {covered, total}

    Codex M-1 review caught that the old code looked for keys that don't
    exist in the V30 schema, returning 0.0 for a 7/7 manifest.
    """
    if not isinstance(raw, Mapping):
        return 0.0
    if "covered_fraction" in raw:
        try:
            return float(raw["covered_fraction"]) * 100.0
        except (TypeError, ValueError):
            pass
    for cov_key, tot_key in (
        ("total_covered", "total_applicable"),
        ("covered_topics", "total_topics"),
        ("covered", "total"),
    ):
        if cov_key in raw and tot_key in raw:
            try:
                cov = float(raw[cov_key])
                tot = float(raw[tot_key])
                if tot > 0:
                    return (cov / tot) * 100.0
            except (TypeError, ValueError):
                continue
    return 0.0


def _parse_manifest(raw: Mapping[str, Any]) -> RunManifest:
    _require_keys(
        raw,
        (
            "run_id",
            "slug",
            "status",
            "question",
            "protocol_sha256",
            "evaluator_gate",
            "completeness",
        ),
        "manifest.json",
    )
    generator = raw.get("generator", {})
    if not isinstance(generator, Mapping):
        generator = {}
    return RunManifest(
        run_id=str(raw["run_id"]),
        slug=str(raw["slug"]),
        status=str(raw["status"]),
        question=str(raw["question"]),
        protocol_sha256=str(raw["protocol_sha256"]),
        cost_usd=float(raw.get("cost_usd", 0.0)),
        budget_cap_usd=float(raw.get("budget_cap_usd", 0.0)),
        word_count=int(generator.get("words", 0)),
        sentences_verified=int(generator.get("sentences_verified", 0)),
        sentences_dropped=int(generator.get("sentences_dropped", 0)),
        contradictions_found=int(raw.get("contradictions_found", 0)),
        completeness_percent=_parse_completeness_percent(raw["completeness"]),
        evaluator_gate=_parse_evaluator_gate(raw["evaluator_gate"]),
        release_allowed=bool(raw.get("release_allowed", False)),
        v30_enabled=bool(raw.get("v30_enabled", False)),
        v30_warnings=tuple(str(w) for w in raw.get("v30_warnings", [])),
        retrieval_stats=_parse_retrieval_stats(raw.get("retrieval")),
    )


def _parse_verification_token(raw: Mapping[str, Any]) -> EvidenceSpanToken:
    return EvidenceSpanToken(
        evidence_id=str(raw.get("evidence_id", "")),
        start=int(raw.get("start", 0)),
        end=int(raw.get("end", 0)),
    )


def _parse_verification_sentence(
    raw: Mapping[str, Any], section_title: str, status: str, idx: int
) -> ReportSentence:
    return ReportSentence(
        claim_id=f"{section_title}:{status}:{idx}",
        section=section_title,
        text=str(raw.get("sentence", "")),
        tokens=tuple(
            _parse_verification_token(t) for t in raw.get("tokens", [])
        ),
        is_verified=(status == "kept"),
        failure_reasons=tuple(str(r) for r in raw.get("failure_reasons", [])),
    )


def _parse_verified_report(raw: Mapping[str, Any]) -> VerifiedReport:
    _require_keys(raw, ("sections", "totals"), "verification_details.json")
    if not isinstance(raw["sections"], list):
        raise AuditIRSchemaError("verification_details.json: 'sections' must be a list")
    sections: list[ReportSection] = []
    for sec in raw["sections"]:
        title = str(sec.get("title", ""))
        kept_raw = sec.get("kept", []) or []
        dropped_raw = sec.get("dropped", []) or []
        sentences = list(
            _parse_verification_sentence(s, title, "kept", i)
            for i, s in enumerate(kept_raw)
        )
        sentences.extend(
            _parse_verification_sentence(s, title, "dropped", i)
            for i, s in enumerate(dropped_raw)
        )
        sections.append(
            ReportSection(
                title=title,
                kept_count=int(sec.get("total_kept", len(kept_raw))),
                dropped_count=int(sec.get("total_dropped", len(dropped_raw))),
                total_in=int(sec.get("total_in", 0)),
                dropped_due_to_failure=int(sec.get("dropped_due_to_failure", 0)),
                sentences=tuple(sentences),
            )
        )
    totals = raw.get("totals", {}) or {}
    drop_counts = raw.get("drop_reason_counts", {}) or {}
    return VerifiedReport(
        sections=tuple(sections),
        sentences_verified=int(totals.get("sentences_verified", 0)),
        sentences_dropped=int(totals.get("sentences_dropped", 0)),
        drop_reason_counts=MappingProxyType(
            {str(k): int(v) for k, v in drop_counts.items()}
        ),
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def load_audit_ir(artifact_dir: Path | str) -> AuditIR:
    """Load a V30 Phase-2 run artifact directory into a canonical AuditIR.

    Required files in artifact_dir:
        manifest.json
        report.md
        bibliography.json
        contradictions.json
        verification_details.json

    Raises
    ------
    NotADirectoryError
        If `artifact_dir` is not an existing directory.
    FileNotFoundError
        If any required file is missing.
    AuditIRSchemaError
        If any required schema block is missing or malformed. The IR fails
        loud at load-time per audit-grade discipline; renderers should not
        have to defensively fill in missing data.
    """
    artifact_dir = Path(artifact_dir)
    if not artifact_dir.is_dir():
        raise NotADirectoryError(f"artifact_dir is not a directory: {artifact_dir}")

    manifest_raw = _read_json(artifact_dir / "manifest.json")
    if not isinstance(manifest_raw, Mapping):
        raise AuditIRSchemaError("manifest.json: top-level must be a JSON object")
    report_md = _read_text(artifact_dir / "report.md")
    bibliography_raw = _read_json(artifact_dir / "bibliography.json")
    contradictions_raw = _read_json(artifact_dir / "contradictions.json")
    verification_raw = _read_json(artifact_dir / "verification_details.json")

    manifest = _parse_manifest(manifest_raw)
    bibliography = _parse_bibliography(bibliography_raw)
    contradictions = _parse_contradictions(contradictions_raw)
    frame_coverage = _parse_frame_coverage(
        manifest_raw.get("frame_coverage_report"),
        manifest.v30_warnings,
    )
    tier_mix = _parse_tier_mix(manifest_raw.get("corpus"))
    verified_report = _parse_verified_report(verification_raw)

    return AuditIR(
        ir_schema_version=IR_SCHEMA_VERSION,
        run_id=manifest.run_id,
        artifact_dir=artifact_dir,
        report_md=report_md,
        manifest=manifest,
        bibliography=bibliography,
        contradictions=contradictions,
        frame_coverage=frame_coverage,
        tier_mix=tier_mix,
        verified_report=verified_report,
    )
