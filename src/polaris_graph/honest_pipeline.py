"""
Honest-rebuild pipeline orchestrator — wires Phase 2/3/4/5 together.

End-to-end flow:
  T+0: Phase 2b scope_gate -> writes protocol.json
  T+1: (mock) retrieval + Phase 2a tier classification of sources
  T+2: Phase 2d prefetch off-topic filter (optional, applied during
       retrieval — for offline run we skip it and go straight to
       post-fetch)
  T+3: Phase 2g corpus-approval gate -> writes corpus_approval.json
  T+4: Phase 3 contradiction detection -> writes contradictions.json
  T+5: Phase 4 provenance-emitting generator (mock draft) -> verified
       report text with citations
  T+6: Phase 5 external evaluator -> writes evaluator_output.json

The orchestrator is designed to run in a "dry-validation" mode where
no network calls happen — evidence and draft are supplied by the
caller. This lets us validate the ARTIFACT SHAPES and CONTENT GATES
line-by-line without depending on API keys.

A separate online mode (not in this file) will plug in Serper /
OpenAlex / DeepSeek / Qwen. For Phase 6 validation, offline mode is
sufficient and explicitly what the audit plan calls for.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Optional

from src.polaris_graph.evaluator.external_evaluator import (
    EvaluatorOutput,
    run_external_evaluation,
)
from src.polaris_graph.generator.provenance_generator import (
    resolve_provenance_to_citations,
    strict_verify,
    wrap_evidence_for_prompt,
)
from src.polaris_graph.nodes.corpus_approval_gate import (
    CorpusApprovalDecision,
    CorpusSource,
    authorization_from_env,
    check_auto_approve_allowed,
    compute_tier_distribution,
    save_approval_decision,
)
from src.polaris_graph.nodes.scope_gate import (
    ScopeGateResult,
    run_scope_gate,
)
from src.polaris_graph.retrieval.contradiction_detector import (
    detect_contradictions,
    extract_numeric_claims,
    format_contradictions_for_user,
    serialize_contradiction_record,
)
from src.polaris_graph.retrieval.tier_classifier import (
    ClassificationSignals,
    classify_source_tier,
)

logger = logging.getLogger("polaris_graph.honest_pipeline")


# Canonical tier order for the "Actual distribution" disclosure. ALL seven
# tiers are ALWAYS shown (including 0% ones) so the disclosure has no gap.
_DISCLOSURE_TIER_ORDER = ("T1", "T2", "T3", "T4", "T5", "T6", "T7")


def _tier_distribution_percentages(
    tier_counts: dict[str, int],
    total_sources: int,
) -> list[tuple[str, int]]:
    """Integer tier percentages that sum to EXACTLY 100 (largest-remainder).

    Single source of truth = the raw ``tier_counts`` histogram over
    ``total_sources``. Every canonical tier T1..T7 is present in the result
    (0% when the corpus has none) plus any extra tier key found in
    ``tier_counts`` (e.g. ``UNKNOWN``) so no source is silently dropped from the
    denominator. Percentages are apportioned with the largest-remainder
    (Hamilton) method: floor each tier's exact share, then hand the leftover
    whole-percent points one-by-one to the tiers with the largest fractional
    remainders (deterministic tie-break: larger remainder first, then canonical
    order). This guarantees the printed percentages sum to 100 when
    ``total_sources > 0`` — replacing the per-tier independent ``round`` that
    could sum to 99 or 101 and silently omitted 0% tiers.

    RENDER/DISCLOSURE TEXT ONLY — faithfulness-neutral. Touches no gate.
    """
    extra = sorted(k for k in tier_counts if k not in _DISCLOSURE_TIER_ORDER)
    tiers = list(_DISCLOSURE_TIER_ORDER) + extra

    if total_sources <= 0:
        return [(t, 0) for t in tiers]

    exact = {t: tier_counts.get(t, 0) * 100.0 / total_sources for t in tiers}
    floors = {t: int(exact[t]) for t in tiers}
    remainder_points = 100 - sum(floors.values())
    # Deterministic ranking of tiers by fractional remainder (desc), then order.
    ranked = sorted(
        tiers,
        key=lambda t: (-(exact[t] - floors[t]), tiers.index(t)),
    )
    result = dict(floors)
    for i in range(max(0, remainder_points)):
        result[ranked[i % len(ranked)]] += 1
    return [(t, result[t]) for t in tiers]


@dataclass
class PipelineArtifacts:
    """Everything written to disk by a successful run."""

    run_dir: Path
    protocol_path: Path
    corpus_approval_path: Path
    contradictions_path: Path
    report_path: Path
    bibliography_path: Path
    evaluator_output_path: Path
    manifest_path: Path

    def as_manifest(self) -> dict[str, str]:
        return {
            "protocol": str(self.protocol_path),
            "corpus_approval": str(self.corpus_approval_path),
            "contradictions": str(self.contradictions_path),
            "report": str(self.report_path),
            "bibliography": str(self.bibliography_path),
            "evaluator_output": str(self.evaluator_output_path),
        }


@dataclass
class PipelineResult:
    """Return value of run_honest_pipeline()."""

    artifacts: PipelineArtifacts
    scope_result: ScopeGateResult
    corpus_decision: CorpusApprovalDecision
    contradictions_found: int
    final_report_text: str
    # FX-05 (I-ready-017): None on an abort_corpus_approval_denied run (no
    # synthesis/evaluator work was done). Check `status` before using.
    evaluator: Optional[EvaluatorOutput]
    sentences_verified: int
    sentences_dropped: int
    # FX-05: "success" | "abort_corpus_approval_denied". A denied corpus
    # short-circuits before strict-verify/report/evaluator (§9.1 #5).
    status: str = "success"


def _build_tier_signals(
    source: dict[str, Any],
) -> ClassificationSignals:
    return ClassificationSignals(
        url=source.get("url", ""),
        title=source.get("title", ""),
        publisher=source.get("publisher", ""),
        fetched_content_length=source.get("content_length", 0),
        openalex_publication_type=source.get("openalex_pub_type", ""),
        openalex_source_type=source.get("openalex_source_type", ""),
        openalex_is_peer_reviewed=source.get("is_peer_reviewed", False),
        source_type_hint=source.get("source_type_hint", ""),
    )


def run_honest_pipeline(
    *,
    research_question: str,
    domain: str,
    run_id: str,
    run_dir: Path | str,
    retrieved_sources: list[dict[str, Any]],
    evidence: list[dict[str, Any]],
    draft_text: str,
    approval_note: str = "",
    auto_approve_if_within_bounds: bool = True,
    quantified_models: dict[tuple[str, str], Any] | None = None,
) -> PipelineResult:
    """Run the honest-rebuild pipeline end-to-end in offline mode.

    Args:
        research_question: User query (verbatim).
        domain: clinical / policy / tech / due_diligence.
        run_id: Stable identifier.
        run_dir: Directory for artifacts.
        retrieved_sources: List of dicts with fields used by
            tier_classifier (url / title / publisher / content_length /
            openalex_pub_type / openalex_source_type / etc.) plus 'domain'.
        evidence: List of evidence rows. Each dict has:
            evidence_id, source_url, statement, direct_quote, tier.
            (tier is populated by the tier classifier step below.)
        draft_text: Prose draft with [#ev:id:start-end] provenance tokens.
        approval_note: Explanation if material deviation from protocol.
        auto_approve_if_within_bounds: If True and no material
            deviation, approve automatically.
    """
    run_dir_path = Path(run_dir)
    run_dir_path.mkdir(parents=True, exist_ok=True)

    # ── Phase 2b: scope gate ────────────────────────────────────────────
    scope_result = run_scope_gate(
        research_question=research_question,
        run_dir=run_dir_path,
        run_id=run_id,
        domain=domain,
    )
    protocol_dict = scope_result.protocol.to_json_dict()

    # ── Phase 2a: tier classification of retrieved sources ─────────────
    classified_sources: list[CorpusSource] = []
    for src in retrieved_sources:
        signals = _build_tier_signals(src)
        res = classify_source_tier(signals)
        classified_sources.append(CorpusSource(
            url=src.get("url", ""),
            title=src.get("title", ""),
            domain=src.get("domain", ""),
            tier=res.tier.value,
            tier_confidence=res.confidence,
            tier_rule=res.matched_rules[0] if res.matched_rules else "",
            tier_reasons=list(res.reasons),
        ))

    # Attach tier to each evidence row whose source_url matches
    url_to_tier = {c.url: c.tier for c in classified_sources}
    for ev in evidence:
        url = ev.get("source_url", "")
        if url in url_to_tier:
            ev["tier"] = url_to_tier[url]

    # ── Phase 2g: corpus approval gate ──────────────────────────────────
    report = compute_tier_distribution(classified_sources, protocol_dict)
    approved = False
    # FX-05 (I-ready-017): a material-deviation corpus auto-approves ONLY with a
    # structured authorization (PG_AUTHORIZED_SWEEP_APPROVAL), never a free-text
    # note. `approval_note` is descriptive/audit only.
    authorization = authorization_from_env()
    if auto_approve_if_within_bounds and not report.has_material_deviation:
        approved = True
    else:
        ok, _ = check_auto_approve_allowed(report, authorization)
        approved = ok

    decision = CorpusApprovalDecision(
        run_id=run_id,
        decision_at_unix=time.time(),
        decision_at_iso=time.strftime(
            "%Y-%m-%dT%H:%M:%SZ", time.gmtime()
        ),
        approved=approved,
        user_note=approval_note,
        authorization=authorization,
        approved_source_urls=[s.url for s in classified_sources] if approved else [],
        rejected_source_urls=[] if approved else [s.url for s in classified_sources],
        report=report,
        protocol_sha256=scope_result.protocol_sha256,
    )
    corpus_approval_path = save_approval_decision(decision, run_dir_path)

    # FX-05 (I-ready-017): §9.1 #5 — a denied corpus aborts BEFORE any
    # strict-verify / report / evaluator work. A material-deviation corpus with
    # no structured PG_AUTHORIZED_SWEEP_APPROVAL authorization is denied; emit a
    # pipeline-verdict report and return early (no normal report on a denied
    # corpus).
    if not approved:
        abort_report_path = run_dir_path / "report.md"
        abort_report_path.write_text(
            f"# Research report: {research_question}\n\n"
            "## Pipeline verdict\n\n"
            "Corpus approval was denied: the corpus has a material deviation "
            "from the pre-registered protocol and no structured operator "
            "authorization (PG_AUTHORIZED_SWEEP_APPROVAL=1) was supplied. "
            "No report was synthesized.\n\n"
            "Status: abort_corpus_approval_denied\n",
            encoding="utf-8",
        )
        abort_manifest_path = run_dir_path / "manifest.json"
        abort_manifest_path.write_text(
            json.dumps(
                {
                    "run_id": run_id,
                    "status": "abort_corpus_approval_denied",
                    "corpus_approved": False,
                },
                indent=2, sort_keys=True,
            ) + "\n",
            encoding="utf-8",
        )
        abort_artifacts = PipelineArtifacts(
            run_dir=run_dir_path,
            protocol_path=scope_result.protocol_path,
            corpus_approval_path=corpus_approval_path,
            contradictions_path=run_dir_path / "contradictions.json",
            report_path=abort_report_path,
            bibliography_path=run_dir_path / "bibliography.json",
            evaluator_output_path=run_dir_path / "evaluator_output.json",
            manifest_path=abort_manifest_path,
        )
        return PipelineResult(
            artifacts=abort_artifacts,
            scope_result=scope_result,
            corpus_decision=decision,
            contradictions_found=0,
            final_report_text="",
            evaluator=None,
            sentences_verified=0,
            sentences_dropped=0,
            status="abort_corpus_approval_denied",
        )

    # ── Phase 3: contradiction detection ───────────────────────────────
    # B9: route + label by the deterministic is_clinical signal so a non-clinical
    # run uses the domain-agnostic extractor and possible_metric_mismatch
    # labeling. Clinical (domain="clinical") is byte-identical.
    from src.polaris_graph.domain.domain_signal import is_clinical_domain
    _is_clinical_hp = is_clinical_domain(domain, evidence)
    num_claims = extract_numeric_claims(evidence, domain=domain)
    contradictions = detect_contradictions(num_claims, is_clinical=_is_clinical_hp)
    contradictions_path = run_dir_path / "contradictions.json"
    contradictions_path.write_text(
        json.dumps(
            [serialize_contradiction_record(c) for c in contradictions],
            indent=2, sort_keys=True, default=str,
        ) + "\n",
        encoding="utf-8",
    )

    # ── Phase 4: strict verification of draft + resolution ─────────────
    # MOAT SEAM (2026-07-11): thread the agentic outliner's verified quantified-model
    # registry so a computed number rendered as a ``[#calc:model:hash:field]`` token is
    # force-routed to ``verify_modeled_atom`` (the Regime-C calc router) instead of being
    # dropped ``no_provenance_token``. Default None => byte-identical legacy behaviour
    # (the router is skipped, exactly as before). A derived number can NEVER launder through
    # the ``[#ev:]`` span path (``number_not_in_any_cited_span`` still fires), so this only
    # OPENS the verified compute lane in production — it never widens the render surface.
    evidence_pool = {ev["evidence_id"]: ev for ev in evidence}
    strict = strict_verify(draft_text, evidence_pool, quantified_models=quantified_models)
    rendered_text, biblio = resolve_provenance_to_citations(
        strict.kept_sentences, evidence_pool,
    )

    report_path = run_dir_path / "report.md"
    biblio_path = run_dir_path / "bibliography.json"

    # Augment rendered text with a methods section that includes the
    # PRISMA-trAIce disclosures Phase 5 looks for.
    from src.polaris_graph.llm.openrouter_client import (
        PG_EVALUATOR_MODEL,
        PG_GENERATOR_MODEL,
    )
    retrieval_date = time.strftime("%Y-%m-%d")
    methods_section = (
        "\n\n## Methods\n"
        f"This research follows a pre-registered protocol.json artifact.\n"
        f"Retrieved on {retrieval_date} from PubMed, OpenAlex, and Semantic Scholar.\n"
        f"Generator model: {PG_GENERATOR_MODEL}.\n"
        f"Evaluator model: {PG_EVALUATOR_MODEL} (different family).\n"
        f"Sources were classified using the T1-T7 tier taxonomy "
        f"(T1 peer-reviewed primary, T2 SR/MA, T3 regulatory, T4 "
        f"narrative review, T5 industry, T6 commentary/news, T7 "
        f"conference abstract / stub).\n"
        f"Inclusion criteria: peer-reviewed journal articles, regulatory\n"
        f"documents, human studies. Exclusion criteria: user-upload\n"
        f"document hosts, student journals, press releases without a\n"
        f"peer-reviewed primary source. Sponsor / conflict-of-interest\n"
        f"funding was evaluated per source.\n"
        f"Prompt-injection sanitization was applied to all evidence "
        f"before prompt construction.\n"
        f"Expected tier distribution per the clinical template: T1 "
        f"30-60%, T2 15-40%, T3 5-25%. Actual distribution: "
    )
    # Append actual tier distribution. Percentages are computed from the raw
    # tier_counts (single source of truth) with largest-remainder rounding so
    # they sum to EXACTLY 100%, and ALL tiers T1..T7 are shown (including 0%
    # ones) so there is no gap. Any extra tier key (e.g. UNKNOWN) is appended so
    # no source is dropped from the denominator.
    actual_parts = [
        f"{tier}={pct}%"
        for tier, pct in _tier_distribution_percentages(
            report.tier_counts, report.total_sources,
        )
    ]
    methods_section += ", ".join(actual_parts) + ".\n"

    # Contradiction disclosure paragraph
    if contradictions:
        n = len(contradictions)
        pluralized = "contradiction" if n == 1 else "contradictions"
        verb = "was" if n == 1 else "were"
        methods_section += (
            "\n## Contradiction disclosures\n"
            f"{n} {pluralized} {verb} detected and {'is' if n == 1 else 'are'} "
            f"disclosed below alongside {'its' if n == 1 else 'their'} "
            f"source tiers.\n\n"
        )
        for c in contradictions:
            methods_section += (
                f"- {c.subject} / {c.predicate}: "
                f"values range {c.claims[0].value} to {c.claims[-1].value} "
                f"{c.claims[0].unit} "
                f"(relative difference {c.relative_difference*100:.1f}%). "
                f"Sources: "
                + ", ".join(
                    f"ev={cc.evidence_id} tier={cc.source_tier}"
                    for cc in c.claims
                )
                + ".\n"
            )

    # Bibliography section
    biblio_section = "\n\n## Bibliography\n"
    for b in biblio:
        biblio_section += (
            f"[{b['num']}] {b['statement']} — {b['url']} (tier {b['tier']})\n"
        )

    final_report_text = (
        f"# Research report: {research_question.strip()}\n\n"
        + rendered_text
        + methods_section
        + biblio_section
    )

    report_path.write_text(final_report_text, encoding="utf-8")
    biblio_path.write_text(
        json.dumps(biblio, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    # ── Phase 5: external evaluator ─────────────────────────────────────
    evaluator = run_external_evaluation(
        report_text=final_report_text,
        protocol=protocol_dict,
        tier_distribution_report=asdict(report),
        contradictions=[serialize_contradiction_record(c) for c in contradictions],
        evidence_pool=evidence_pool,
        enable_llm_judge=False,
    )
    evaluator_path = run_dir_path / "evaluator_output.json"
    evaluator_path.write_text(
        json.dumps(evaluator.to_json_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    # ── Manifest ────────────────────────────────────────────────────────
    manifest_path = run_dir_path / "manifest.json"
    manifest = {
        "run_id": run_id,
        "domain": domain,
        "research_question": research_question,
        "protocol_sha256": scope_result.protocol_sha256,
        "artifacts": {
            "protocol": "protocol.json",
            "corpus_approval": "corpus_approval.json",
            "contradictions": "contradictions.json",
            "report": "report.md",
            "bibliography": "bibliography.json",
            "evaluator_output": "evaluator_output.json",
        },
        "summary": {
            "total_sources": len(classified_sources),
            "total_evidence": len(evidence),
            "sentences_verified": strict.total_kept,
            "sentences_dropped": strict.total_dropped,
            "contradictions_found": len(contradictions),
            "rule_checks_pass": evaluator.rule_check_pass_count,
            "rule_checks_fail": evaluator.rule_check_fail_count,
            "corpus_approved": decision.approved,
        },
    }
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    artifacts = PipelineArtifacts(
        run_dir=run_dir_path,
        protocol_path=scope_result.protocol_path,
        corpus_approval_path=corpus_approval_path,
        contradictions_path=contradictions_path,
        report_path=report_path,
        bibliography_path=biblio_path,
        evaluator_output_path=evaluator_path,
        manifest_path=manifest_path,
    )
    return PipelineResult(
        artifacts=artifacts,
        scope_result=scope_result,
        corpus_decision=decision,
        contradictions_found=len(contradictions),
        final_report_text=final_report_text,
        evaluator=evaluator,
        sentences_verified=strict.total_kept,
        sentences_dropped=strict.total_dropped,
    )
