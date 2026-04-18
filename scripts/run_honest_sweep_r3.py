"""
R-3: 8-query cross-domain readiness sweep.

Runs the full live honest-rebuild pipeline on 8 queries spanning all
4 domain scope templates. Records success / failure-mode matrix +
per-query artifacts in outputs/honest_sweep_r3/<domain>/<slug>/.

This is the "never tested on a query other than semaglutide" gap from
the readiness-gate analysis. Expect some queries to surface novel
failure modes; that's the point.

Usage:
    python -X utf8 scripts/run_honest_sweep_r3.py
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import sys
import time
import traceback
from dataclasses import asdict
from pathlib import Path

from dotenv import load_dotenv
load_dotenv(override=False)

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

logging.basicConfig(
    level=os.environ.get("PG_LOG_LEVEL", "INFO"),
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
    stream=sys.stdout,
)
for noisy in ("httpx", "httpcore"):
    logging.getLogger(noisy).setLevel(logging.WARNING)

from src.polaris_graph.evaluator.external_evaluator import run_external_evaluation  # noqa: E402
from src.polaris_graph.evaluator.live_qwen_judge import judge_report  # noqa: E402
from src.polaris_graph.generator.multi_section_generator import (  # noqa: E402
    generate_multi_section_report,
)
from src.polaris_graph.generator.provenance_generator import (  # noqa: E402
    resolve_provenance_to_citations,
)
from src.polaris_graph.llm.openrouter_client import (  # noqa: E402
    PG_MAX_COST_PER_RUN,
    current_run_cost,
    reset_run_cost,
)
from src.polaris_graph.nodes.completeness_checker import (  # noqa: E402
    check_completeness,
)
from src.polaris_graph.nodes.corpus_adequacy_gate import (  # noqa: E402
    assess_corpus_adequacy,
)
from src.polaris_graph.nodes.corpus_approval_gate import (  # noqa: E402
    CorpusApprovalDecision,
    check_auto_approve_allowed,
    compute_tier_distribution,
    save_approval_decision,
)
from src.polaris_graph.nodes.scope_gate import run_scope_gate  # noqa: E402
from src.polaris_graph.retrieval.contradiction_detector import (  # noqa: E402
    detect_contradictions,
    extract_numeric_claims,
)
from src.polaris_graph.retrieval.live_retriever import (  # noqa: E402
    run_live_retrieval,
)


# ─────────────────────────────────────────────────────────────────
# BUG-B-101 fix: unified manifest.status taxonomy.
#
# Pre-fix, successful runs wrote manifest.json WITHOUT a "status" key
# while abort runs DID include it. Documentation claimed
# manifest.status was authoritative — it wasn't. See
# outputs/codex_findings/deep_dive_round_1/findings.md for the full
# scoping analysis.
#
# Post-fix, EVERY exit path writes a manifest.json with a "status"
# field from this unified taxonomy. `summary["status"]` is preserved
# as secondary sweep telemetry for backward compatibility with any
# downstream counter that relied on the legacy labels.
# ─────────────────────────────────────────────────────────────────

UNIFIED_STATUS_VALUES: frozenset[str] = frozenset({
    # success
    "success",
    # partial — report produced but degraded signal
    "partial_thin_corpus",
    "partial_incomplete_corpus",
    "partial_rule_check_warnings",
    "partial_outline_fallback",      # BUG-M-203: planner failed, fallback used
    "partial_qwen_advisory",         # BUG-M-205: Qwen judge flagged critical axes
    # abort — pipeline refused to produce a report
    "abort_scope_rejected",
    "abort_no_sources",
    "abort_corpus_inadequate",
    "abort_corpus_approval_denied",
    "abort_no_verified_sections",
    "abort_evaluator_critical",      # BUG-M-205: PT08/PT11/PT12 integrity failure
    # error — unhandled exception
    "error_unexpected",
})

# Map legacy summary["status"] labels → unified manifest.status values.
_SUMMARY_TO_UNIFIED: dict[str, str] = {
    "ok": "success",
    "ok_thin_corpus": "partial_thin_corpus",
    "ok_incomplete_corpus": "partial_incomplete_corpus",
    "ok_outline_fallback": "partial_outline_fallback",
    "ok_qwen_advisory": "partial_qwen_advisory",
    "warn_rule_checks": "partial_rule_check_warnings",
    "fail_no_sources": "abort_no_sources",
    "fail_no_verified_prose": "abort_no_verified_sections",
    "abort_scope_rejected": "abort_scope_rejected",
    "abort_corpus_inadequate": "abort_corpus_inadequate",
    "abort_corpus_approval_denied": "abort_corpus_approval_denied",
    "abort_no_verified_sections": "abort_no_verified_sections",
    "abort_evaluator_critical": "abort_evaluator_critical",
    "error": "error_unexpected",
}


def to_unified_status(summary_status: str) -> str:
    """Map a legacy summary["status"] label to the unified
    manifest.status taxonomy. Unknown labels become error_unexpected
    (fail loudly for the reader; still a valid taxonomy value)."""
    return _SUMMARY_TO_UNIFIED.get(summary_status, "error_unexpected")


def expected_str_for_abort(protocol: dict) -> str:
    """Render expected tier distribution for abort-artifact text."""
    parts = []
    for entry in protocol.get("expected_tier_distribution", []) or []:
        tier = entry.get("tier")
        mn = (entry.get("min_fraction", 0) or 0) * 100
        mx = (entry.get("max_fraction", 1) or 1) * 100
        if tier:
            parts.append(f"{tier} {mn:.0f}-{mx:.0f}%")
    return ", ".join(parts) or "per scope template"


def filter_verified_sections(sections) -> list:
    """Codex round 1 B-3: the single-source-of-truth predicate for
    "did this section survive Phase-4 strict_verify?". A section
    qualifies only if it was NOT dropped AND has non-empty verified_text.
    """
    return [
        sr for sr in sections
        if not getattr(sr, "dropped_due_to_failure", True)
        and getattr(sr, "verified_text", "")
    ]


def build_no_verified_sections_abort_body(
    research_question: str,
    sections,
) -> str:
    """Codex round 1 B-3: build the pipeline-verdict markdown body used
    when ZERO sections survived strict_verify. Pure function so a
    behavior test can call it without mocking run_one_query."""
    head = (
        f"# Research report: {research_question}\n\n"
        "## Pipeline verdict\n\n"
        f"DeepSeek V3.2-Exp generated {len(sections)} "
        "section(s), but EVERY section failed Phase-4 strict_verify: "
        "the cited evidence did not support the claims, or the "
        "generator did not emit provenance tokens.\n\n"
        "### Per-section verdict\n\n"
    )
    rows = "\n".join(
        f"- **{sr.title}** — verified={sr.sentences_verified}, "
        f"dropped={sr.sentences_dropped}, "
        f"regen_attempted={sr.regen_attempted}, "
        f"error={sr.error!r}"
        for sr in sections
    )
    tail = (
        "\n\n### Suggested next steps\n\n"
        "- Widen retrieval so the generator has anchor evidence "
        "to cite.\n"
        "- Tune the generator prompt for stricter citation "
        "discipline.\n"
        "- Abort and refine the research question.\n"
    )
    return head + rows + tail


# ─────────────────────────────────────────────────────────────────────────────
# 8-query manifest. Two per domain. Deliberately diverse within each
# domain so novel failure modes have a chance to appear.
# ─────────────────────────────────────────────────────────────────────────────
SWEEP_QUERIES: list[dict] = [
    # Clinical
    {
        "slug": "clinical_tirzepatide_t2dm",
        "domain": "clinical",
        "question": (
            "What is the efficacy and safety of tirzepatide for glycemic "
            "control and weight loss in adults with type 2 diabetes?"
        ),
        "amplified": [
            "tirzepatide SURPASS trial HbA1c reduction",
            "tirzepatide weight loss randomized controlled trial",
            "tirzepatide safety adverse events gastrointestinal",
        ],
    },
    {
        "slug": "clinical_afib_anticoagulation",
        "domain": "clinical",
        "question": (
            "What are current clinical guidelines for oral anticoagulation "
            "in adults with non-valvular atrial fibrillation?"
        ),
        "amplified": [
            "atrial fibrillation direct oral anticoagulant guideline",
            "CHA2DS2-VASc score anticoagulation threshold",
            "apixaban rivaroxaban warfarin non-valvular atrial fibrillation",
        ],
    },
    # Policy
    {
        "slug": "policy_fda_ai_devices",
        "domain": "policy",
        "question": (
            "How is the FDA regulating AI-enabled medical devices under "
            "the current Predetermined Change Control Plan framework?"
        ),
        "amplified": [
            "FDA AI medical device predetermined change control plan",
            "FDA 510(k) AI enabled software SaMD",
            "FDA AI ML guidance adaptive algorithm",
        ],
    },
    {
        "slug": "policy_medicare_drug_price",
        "domain": "policy",
        "question": (
            "What is the impact of Medicare drug-price negotiation under "
            "the Inflation Reduction Act on drug list prices and access?"
        ),
        "amplified": [
            "Medicare drug price negotiation Inflation Reduction Act",
            "IRA Part D negotiated drug prices impact",
            "Medicare negotiation semaglutide Ozempic price",
        ],
    },
    # Tech
    {
        "slug": "tech_rag_architectures_2024",
        "domain": "tech",
        "question": (
            "What are the current best practices for retrieval-augmented "
            "generation architectures as of 2024-2025?"
        ),
        "amplified": [
            "retrieval augmented generation RAG 2024",
            "dense retrieval embedding models benchmark",
            "graph RAG knowledge graph retrieval",
        ],
    },
    {
        "slug": "tech_long_context_transformer",
        "domain": "tech",
        "question": (
            "What techniques extend transformer context length beyond "
            "128K tokens while preserving recall quality?"
        ),
        "amplified": [
            "long context transformer attention optimization",
            "RULER benchmark long context needle in haystack",
            "sparse attention RoPE YaRN context extension",
        ],
    },
    # Due-diligence
    {
        "slug": "dd_novo_nordisk_obesity_position",
        "domain": "due_diligence",
        "question": (
            "What is Novo Nordisk's competitive position in the obesity "
            "pharmaceutical market relative to Eli Lilly and newer entrants?"
        ),
        "amplified": [
            "Novo Nordisk obesity market share Wegovy",
            "Eli Lilly Zepbound tirzepatide obesity competitive",
            "obesity drug pipeline 2025 new entrants",
        ],
    },
    {
        "slug": "dd_lilly_tirzepatide_manufacturing",
        "domain": "due_diligence",
        "question": (
            "What is the current state of Eli Lilly's tirzepatide "
            "manufacturing capacity and supply outlook?"
        ),
        "amplified": [
            "Eli Lilly tirzepatide manufacturing capacity expansion",
            "Zepbound Mounjaro supply shortage FDA",
            "Lilly Concord North Carolina Indiana manufacturing investment",
        ],
    },
]


async def run_one_query(
    q: dict,
    out_root: Path,
) -> dict:
    """Run the full honest pipeline on one query. Returns a summary dict."""
    reset_run_cost()

    run_dir = out_root / q["domain"] / q["slug"]
    run_dir.mkdir(parents=True, exist_ok=True)
    run_id = f"SWEEP_{q['domain']}_{q['slug']}_{int(time.time())}"

    log_path = run_dir / "run_log.txt"
    log_f = log_path.open("w", encoding="utf-8")

    def _log(msg: str) -> None:
        print(msg)
        log_f.write(msg + "\n")
        log_f.flush()

    summary: dict = {
        "slug": q["slug"],
        "domain": q["domain"],
        "question": q["question"],
        "run_id": run_id,
        "status": "started",
        "run_dir": str(run_dir),
        "error": "",
    }

    try:
        _log("=" * 72)
        _log(f"SWEEP domain={q['domain']} slug={q['slug']}")
        _log(f"Question: {q['question']}")
        _log(f"Budget cap: ${PG_MAX_COST_PER_RUN:.4f}")
        _log("=" * 72)

        # Phase 2b scope gate
        scope = run_scope_gate(
            research_question=q["question"],
            run_dir=run_dir,
            run_id=run_id,
            domain=q["domain"],
        )
        protocol = scope.protocol.to_json_dict()
        _log(f"[scope]       sha256={scope.protocol_sha256[:16]}... "
             f"decision={scope.protocol.scope_decision} "
             f"needs_review={scope.protocol.needs_user_review}")

        # BUG-B-100 fix (deep-dive R3): the scope gate is now a real
        # gate. If it rejects, abort BEFORE retrieval with a pipeline-
        # verdict artifact and manifest.status=abort_scope_rejected.
        if scope.protocol.scope_rejected:
            reasons_text = "; ".join(scope.protocol.scope_reasons) or "(no reasons)"
            _log(f"[ABORT]       Scope rejected: "
                 f"{scope.protocol.scope_rejection_code} — {reasons_text}")
            summary["status"] = "abort_scope_rejected"
            summary["error"] = (
                f"scope rejected: {scope.protocol.scope_rejection_code}"
            )
            (run_dir / "report.md").write_text(
                f"# Research report: {q['question']}\n\n"
                "## Pipeline verdict\n\n"
                "The scope gate refused to proceed with this research "
                "question. The pipeline is refusing to spend retrieval "
                "and generation budget on a query that would not produce "
                "a meaningful evidence corpus.\n\n"
                f"### Rejection code\n\n`{scope.protocol.scope_rejection_code}`\n\n"
                "### Reasons\n\n"
                + "\n".join(f"- {r}" for r in scope.protocol.scope_reasons)
                + "\n\n### Suggested next steps\n\n"
                "- Refine the research question with explicit scope hints "
                "(e.g., add population / intervention for clinical queries).\n"
                "- Choose a supported domain: clinical, policy, tech, or "
                "due_diligence.\n"
                "- Provide user_overrides via the caller's protocol to "
                "supply the missing scope anchors directly.\n",
                encoding="utf-8",
            )
            run_cost = current_run_cost()
            abort_manifest = {
                "run_id": run_id,
                "slug": q["slug"],
                "domain": q["domain"],
                "question": q["question"],
                "status": "abort_scope_rejected",
                "protocol_sha256": scope.protocol_sha256,
                "scope": {
                    "decision": scope.protocol.scope_decision,
                    "rejected": scope.protocol.scope_rejected,
                    "rejection_code": scope.protocol.scope_rejection_code,
                    "reasons": scope.protocol.scope_reasons,
                },
                "cost_usd": run_cost,
                "budget_cap_usd": PG_MAX_COST_PER_RUN,
            }
            (run_dir / "manifest.json").write_text(
                json.dumps(abort_manifest, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            summary["manifest"] = abort_manifest
            summary["cost_usd"] = run_cost
            log_f.close()
            return summary

        # Live retrieval
        t0 = time.time()
        retrieval = run_live_retrieval(
            research_question=q["question"],
            amplified_queries=q.get("amplified", []),
            protocol=protocol,
            max_serper=8,
            max_s2=8,
            fetch_cap=20,
            enable_openalex_enrich=True,
            enable_prefetch_filter=False,
            domain=q["domain"],   # R-6 Gap-2 domain backends
        )
        dt = time.time() - t0
        _log(f"[retrieval]   pre_filter={retrieval.total_candidates_pre_filter}, "
             f"fetched={retrieval.candidates_fetched}, "
             f"failed={retrieval.candidates_failed_fetch}, "
             f"elapsed={dt:.1f}s  api_calls={retrieval.api_calls}")

        if len(retrieval.classified_sources) == 0:
            # BUG-B-101 fix: previously returned without any manifest,
            # so downstream couldn't tell the run happened at all.
            summary["status"] = "fail_no_sources"
            summary["error"] = "zero sources retrieved"
            run_cost = current_run_cost()
            abort_manifest = {
                "run_id": run_id,
                "slug": q["slug"],
                "domain": q["domain"],
                "question": q["question"],
                "status": "abort_no_sources",
                "error": "zero sources retrieved",
                "retrieval": {
                    "pre_filter": retrieval.total_candidates_pre_filter,
                    "fetched": retrieval.candidates_fetched,
                    "failed": retrieval.candidates_failed_fetch,
                    "api_calls": retrieval.api_calls,
                },
                "cost_usd": run_cost,
                "budget_cap_usd": PG_MAX_COST_PER_RUN,
            }
            (run_dir / "manifest.json").write_text(
                json.dumps(abort_manifest, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            summary["manifest"] = abort_manifest
            summary["cost_usd"] = run_cost
            log_f.close()
            return summary

        # Dump corpus
        (run_dir / "live_corpus_dump.json").write_text(
            json.dumps(
                [asdict(s) for s in retrieval.classified_sources],
                indent=2, sort_keys=True, default=str,
            ) + "\n",
            encoding="utf-8",
        )

        # Corpus approval
        dist = compute_tier_distribution(
            retrieval.classified_sources, protocol,
        )
        tier_summary = ", ".join(
            f"{k}={v*100:.0f}%"
            for k, v in sorted(dist.tier_fractions.items())
        )
        _log(f"[corpus]      total={dist.total_sources}  {tier_summary}  "
             f"material_deviation={dist.has_material_deviation}")

        # R-6 Gap-1: corpus-adequacy gate.
        adequacy = assess_corpus_adequacy(
            tier_counts=dist.tier_counts,
            evidence_row_count=len(retrieval.evidence_rows),
            domain=q["domain"],
            protocol=protocol,
        )
        (run_dir / "corpus_adequacy.json").write_text(
            json.dumps(asdict(adequacy), indent=2, sort_keys=True, default=str)
            + "\n",
            encoding="utf-8",
        )
        _log(f"[adequacy]    decision={adequacy.decision}  "
             f"applicable_checks={len(adequacy.findings)}  "
             f"critical={sum(1 for f in adequacy.findings if f.severity=='critical')}  "
             f"warn={sum(1 for f in adequacy.findings if f.severity=='warn')}")
        for f in adequacy.findings:
            if not f.ok:
                _log(f"                {f.severity.upper():<8} {f.name}: "
                     f"{f.observed} vs threshold {f.threshold}")

        # R-6 Gap-3: completeness check (before synthesis so gaps can
        # trigger expansion).
        completeness = check_completeness(
            domain=q["domain"],
            research_question=q["question"],
            evidence_rows=retrieval.evidence_rows,
        )
        (run_dir / "completeness.json").write_text(
            json.dumps(
                {
                    "domain": completeness.domain,
                    "total_applicable": completeness.total_applicable,
                    "total_covered": completeness.total_covered,
                    "total_uncovered": completeness.total_uncovered,
                    "covered_fraction": completeness.covered_fraction,
                    "uncovered_topic_ids": completeness.uncovered_topic_ids(),
                    "expand_queries": completeness.expand_queries,
                    "notes": completeness.notes,
                    "per_topic": [
                        {
                            "id": tc.topic.id,
                            "label": tc.topic.label,
                            "applies": tc.applies,
                            "covered": tc.covered,
                            "hits": tc.hits,
                            "matched_keywords": tc.matched_keywords,
                        }
                        for tc in completeness.topics
                    ],
                },
                indent=2, sort_keys=True,
            ) + "\n",
            encoding="utf-8",
        )
        _log(f"[completeness] {completeness.total_covered}/"
             f"{completeness.total_applicable} topics covered  "
             f"uncovered={completeness.uncovered_topic_ids()}")

        # R-6 Gap-3: gap-triggered expansion. If uncovered topics and
        # we have enable_expansion, fire another retrieval pass with
        # the expansion queries, then re-classify + re-check.
        enable_expansion = os.getenv("PG_R6_ENABLE_EXPANSION", "1") == "1"
        if (enable_expansion and completeness.expand_queries
                and completeness.total_uncovered > 0):
            _log(f"[expansion]   triggering {len(completeness.expand_queries)} "
                 f"expansion queries")
            # Cap expansion queries to keep cost/runtime bounded
            expand_q_cap = int(os.getenv("PG_R6_EXPAND_QUERY_CAP", "4"))
            exp_queries = completeness.expand_queries[:expand_q_cap]
            try:
                exp_retrieval = run_live_retrieval(
                    research_question=q["question"],
                    amplified_queries=exp_queries,
                    protocol=protocol,
                    max_serper=5,
                    max_s2=5,
                    fetch_cap=15,
                    enable_openalex_enrich=True,
                    enable_prefetch_filter=False,
                    domain=q["domain"],
                )
                _log(f"[expansion]   fetched={exp_retrieval.candidates_fetched} "
                     f"new evidence rows")
                # Merge: add new evidence that isn't already present
                existing_urls = {
                    s.url for s in retrieval.classified_sources
                }
                for src in exp_retrieval.classified_sources:
                    if src.url not in existing_urls:
                        retrieval.classified_sources.append(src)
                existing_ev_ids = {
                    ev["evidence_id"] for ev in retrieval.evidence_rows
                }
                # Renumber new evidence rows to avoid collisions
                base = len(retrieval.evidence_rows)
                for i, ev in enumerate(exp_retrieval.evidence_rows):
                    new_id = f"ev_{base + i:03d}"
                    ev["evidence_id"] = new_id
                    retrieval.evidence_rows.append(ev)
                # Re-classify tier distribution with the merged corpus
                dist = compute_tier_distribution(
                    retrieval.classified_sources, protocol,
                )
                tier_summary = ", ".join(
                    f"{k}={v*100:.0f}%"
                    for k, v in sorted(dist.tier_fractions.items())
                )
                # Re-check completeness
                completeness = check_completeness(
                    domain=q["domain"],
                    research_question=q["question"],
                    evidence_rows=retrieval.evidence_rows,
                )
                _log(f"[expansion]   post: total={dist.total_sources} "
                     f"covered={completeness.total_covered}/"
                     f"{completeness.total_applicable}")
                # Also re-run adequacy
                adequacy = assess_corpus_adequacy(
                    tier_counts=dist.tier_counts,
                    evidence_row_count=len(retrieval.evidence_rows),
                    domain=q["domain"],
                    protocol=protocol,
                )
                (run_dir / "corpus_adequacy.json").write_text(
                    json.dumps(asdict(adequacy), indent=2, sort_keys=True, default=str)
                    + "\n",
                    encoding="utf-8",
                )
            except Exception as exc:
                _log(f"[expansion]   FAILED: {exc}")

        # R-6 Gap-1: if adequacy still says ABORT after optional
        # expansion, refuse to synthesize — emit a short "corpus
        # inadequate" manifest and return status=abort_corpus_inadequate.
        if adequacy.decision == "abort":
            _log(f"[ABORT]       Corpus inadequate for confident synthesis. "
                 f"Refusing to ship a misleading short report.")
            summary["status"] = "abort_corpus_inadequate"
            summary["error"] = adequacy.notes[0] if adequacy.notes else "corpus_inadequate"
            # Still save what we have
            (run_dir / "report.md").write_text(
                f"# Research report: {q['question']}\n\n"
                "## Pipeline verdict\n\n"
                "The corpus retrieved for this query did not meet the "
                f"adequacy thresholds for domain {q['domain']}. The "
                "pipeline is refusing to synthesize a report that would "
                "read as confident while being based on thin evidence.\n\n"
                "### Adequacy findings\n\n"
                + "\n".join(
                    f"- **{f.severity.upper()}** {f.name}: "
                    f"observed={f.observed}, threshold={f.threshold}"
                    for f in adequacy.findings if not f.ok
                )
                + "\n\n### Suggested next steps\n\n"
                "- Widen retrieval (more amplified queries, higher caps).\n"
                "- Relax adequacy thresholds if the domain has inherently "
                "sparse evidence.\n"
                "- Refine the research question to a narrower, better-"
                "supported sub-topic.\n",
                encoding="utf-8",
            )
            run_cost = current_run_cost()
            manifest = {
                "run_id": run_id, "slug": q["slug"], "domain": q["domain"],
                "question": q["question"],
                "status": "abort_corpus_inadequate",
                "adequacy": asdict(adequacy),
                "corpus": {
                    "count": dist.total_sources,
                    "tier_fractions": dist.tier_fractions,
                },
                "completeness": {
                    "total_applicable": completeness.total_applicable,
                    "total_covered": completeness.total_covered,
                    "total_uncovered": completeness.total_uncovered,
                    "uncovered_topic_ids": completeness.uncovered_topic_ids(),
                },
                "cost_usd": run_cost,
            }
            (run_dir / "manifest.json").write_text(
                json.dumps(manifest, indent=2, sort_keys=True, default=str) + "\n",
                encoding="utf-8",
            )
            summary["manifest"] = manifest
            summary["cost_usd"] = run_cost
            log_f.close()
            return summary

        note = f"R-3 sweep. Domain={q['domain']}. Auto-approve on sweep."
        if dist.has_material_deviation:
            ok, err = check_auto_approve_allowed(dist, note)
            approved = ok
            approval_error = err
        else:
            approved = True
            approval_error = ""
        decision = CorpusApprovalDecision(
            run_id=run_id,
            decision_at_unix=time.time(),
            decision_at_iso=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            approved=approved, user_note=note,
            approved_source_urls=[s.url for s in retrieval.classified_sources] if approved else [],
            rejected_source_urls=[] if approved else [s.url for s in retrieval.classified_sources],
            report=dist, protocol_sha256=scope.protocol_sha256,
        )
        save_approval_decision(decision, run_dir)

        # Codex round 1 B-2: ENFORCE the corpus-approval gate. Previously
        # the orchestrator wrote corpus_approval.json and then proceeded
        # regardless of `approved`. Now we short-circuit exactly like the
        # adequacy-abort path when approval was denied (material deviation
        # + rubber-stamp note). No LLM call, pipeline verdict artifact only.
        if not approved:
            _log(f"[ABORT]       Corpus approval denied "
                 f"(material deviation without substantive note). "
                 f"Refusing to synthesize.")
            summary["status"] = "abort_corpus_approval_denied"
            summary["error"] = approval_error or "approval_denied"
            (run_dir / "report.md").write_text(
                f"# Research report: {q['question']}\n\n"
                "## Pipeline verdict\n\n"
                "The corpus has a material deviation from the "
                f"pre-registered protocol for domain {q['domain']} and "
                "the approval step did not receive a substantive note "
                "explaining the deviation. The pipeline is refusing to "
                "synthesize a report over an unapproved corpus.\n\n"
                "### Approval failure\n\n"
                f"- {approval_error or 'no substantive note provided'}\n\n"
                "### Tier distribution\n\n"
                f"Expected: {expected_str_for_abort(protocol)}\n"
                f"Actual:   {tier_summary}\n\n"
                "### Suggested next steps\n\n"
                "- Provide a substantive approval note (>=30 chars) that "
                "explains why the deviation is acceptable for this "
                "research question.\n"
                "- Widen retrieval to align the actual tier distribution "
                "with the expected range.\n"
                "- Abort and refine the research question.\n",
                encoding="utf-8",
            )
            run_cost = current_run_cost()
            manifest = {
                "run_id": run_id, "slug": q["slug"], "domain": q["domain"],
                "question": q["question"],
                "status": "abort_corpus_approval_denied",
                "approval_error": approval_error,
                "adequacy": asdict(adequacy),
                "corpus": {
                    "count": dist.total_sources,
                    "tier_fractions": dist.tier_fractions,
                    "material_deviation": dist.has_material_deviation,
                    "approved": False,
                },
                "cost_usd": run_cost,
            }
            (run_dir / "manifest.json").write_text(
                json.dumps(manifest, indent=2, sort_keys=True, default=str) + "\n",
                encoding="utf-8",
            )
            summary["manifest"] = manifest
            summary["cost_usd"] = run_cost
            log_f.close()
            return summary

        # Contradiction detection (now on the possibly-expanded evidence set)
        numeric_claims = extract_numeric_claims(retrieval.evidence_rows)
        contradictions = detect_contradictions(numeric_claims)
        (run_dir / "contradictions.json").write_text(
            json.dumps(
                [asdict(c) for c in contradictions],
                indent=2, sort_keys=True, default=str,
            ) + "\n",
            encoding="utf-8",
        )
        _log(f"[contradict]  numeric_claims={len(numeric_claims)}  "
             f"contradictions={len(contradictions)}")

        # Multi-section generation with Limitations (R-1)
        max_ev = int(os.getenv("PG_LIVE_MAX_EV_TO_GEN", "20"))
        evidence_for_gen = retrieval.evidence_rows[:max_ev]
        _log(f"[generation]  multi-section DeepSeek V3.2-Exp, "
             f"evidence={len(evidence_for_gen)}...")
        t0 = time.time()
        # R-6 Gap-3: pass uncovered-topic labels so the Limitations
        # paragraph can name the gaps explicitly.
        uncovered_labels = [
            next(
                (tc.topic.label for tc in completeness.topics
                 if tc.topic.id == tid),
                tid,
            )
            for tid in completeness.uncovered_topic_ids()
        ]
        multi = await generate_multi_section_report(
            research_question=q["question"],
            evidence=evidence_for_gen,
            section_temperature=0.3,
            outline_max_tokens=800,
            section_max_tokens=1200,
            min_kept_fraction=0.4,
            max_parallel_sections=3,
            tier_fractions=dist.tier_fractions,
            contradictions=[asdict(c) for c in contradictions],
            date_range=(
                protocol.get("date_range")
                if isinstance(protocol.get("date_range"), dict)
                else None
            ),
            uncovered_topics=uncovered_labels,
        )
        dt = time.time() - t0
        _log(f"              elapsed={dt:.1f}s outline={len(multi.outline)} "
             f"sections, words={multi.total_words}, "
             f"verified={multi.total_sentences_verified}, "
             f"dropped={multi.total_sentences_dropped}, "
             f"limitations_words={len(multi.limitations_text.split())}")

        # Assemble final report
        section_bodies = []
        for sr in multi.sections:
            if sr.dropped_due_to_failure or not sr.verified_text:
                continue
            section_bodies.append(f"### {sr.title}\n\n{sr.verified_text}")
        sections_concat = "\n\n".join(section_bodies)
        if multi.limitations_text:
            sections_concat += f"\n\n### Limitations\n\n{multi.limitations_text}"

        # Codex round 1 B-3: if ZERO sections survived verification,
        # refuse to ship report.md. The old code would write a Methods
        # + Bibliography file with an empty findings body, and only then
        # mark status=fail_no_verified_prose as a post-hoc flag.
        verified_sections = filter_verified_sections(multi.sections)
        if not verified_sections:
            _log(f"[ABORT]       All {len(multi.sections)} sections "
                 f"failed verification. Refusing to write a report body.")
            summary["status"] = "abort_no_verified_sections"
            summary["error"] = (
                f"all {len(multi.sections)} sections dropped at strict_verify"
            )
            (run_dir / "report.md").write_text(
                build_no_verified_sections_abort_body(q["question"], multi.sections),
                encoding="utf-8",
            )
            run_cost = current_run_cost()
            manifest = {
                "run_id": run_id, "slug": q["slug"], "domain": q["domain"],
                "question": q["question"],
                "status": "abort_no_verified_sections",
                "adequacy": asdict(adequacy),
                "corpus": {
                    "count": dist.total_sources,
                    "tier_fractions": dist.tier_fractions,
                    "approved": approved,
                },
                "generator": {
                    "outline_sections": [p.title for p in multi.outline],
                    "sections_total": len(multi.sections),
                    "sections_dropped": len(multi.sections),
                    "sentences_verified": 0,
                },
                "cost_usd": run_cost,
            }
            (run_dir / "manifest.json").write_text(
                json.dumps(manifest, indent=2, sort_keys=True, default=str) + "\n",
                encoding="utf-8",
            )
            summary["manifest"] = manifest
            summary["cost_usd"] = run_cost
            log_f.close()
            return summary

        from src.polaris_graph.llm.openrouter_client import (
            PG_EVALUATOR_MODEL, PG_GENERATOR_MODEL,
        )
        # Build expected-distribution string from the scope template so
        # PT07 passes regardless of domain.
        expected_parts = []
        for entry in protocol.get("expected_tier_distribution", []) or []:
            tier = entry.get("tier")
            mn = entry.get("min_fraction", 0) * 100
            mx = entry.get("max_fraction", 1) * 100
            if tier:
                expected_parts.append(f"{tier} {mn:.0f}-{mx:.0f}%")
        expected_str = ", ".join(expected_parts) or "per scope template"

        # R-6: surface adequacy + completeness in the Methods section.
        adequacy_line = (
            f"Corpus adequacy: decision={adequacy.decision}, "
            f"{sum(1 for f in adequacy.findings if f.ok)}/"
            f"{len(adequacy.findings)} thresholds met."
        )
        completeness_line = (
            f"Completeness checklist: {completeness.total_covered}/"
            f"{completeness.total_applicable} topics covered"
        )
        if completeness.uncovered_topic_ids():
            uncovered_labels = [
                next(
                    (tc.topic.label for tc in completeness.topics
                     if tc.topic.id == tid),
                    tid,
                )
                for tid in completeness.uncovered_topic_ids()
            ]
            completeness_line += f"; uncovered: {uncovered_labels}"
        completeness_line += "."

        methods = (
            "\n\n## Methods\n"
            f"Pre-registered protocol.json (SHA-256 {scope.protocol_sha256[:16]}...).\n"
            f"Corpus: Serper + Semantic Scholar + OpenAlex live retrieval, "
            f"augmented by domain backends ({q['domain']}: "
            f"{retrieval.notes[-1] if retrieval.notes else 'none'}).\n"
            f"Generator model: {PG_GENERATOR_MODEL} (multi-section: outline + "
            f"{len([s for s in multi.sections if not s.dropped_due_to_failure])} "
            f"parallel sections + strict_verify + regen-on-failure).\n"
            f"Evaluator model: {PG_EVALUATOR_MODEL} (different family).\n"
            f"Sources classified using T1-T7 tier taxonomy.\n"
            f"Inclusion / exclusion per {q['domain']} template. "
            f"Sponsor / conflict-of-interest review per source.\n"
            f"Prompt-injection sanitization enabled. "
            f"Retrieved {time.strftime('%Y-%m-%d')}.\n"
            f"Expected tier distribution: {expected_str}. "
            f"Actual distribution: {tier_summary}.\n"
            f"{adequacy_line}\n"
            f"{completeness_line}\n"
        )
        if contradictions:
            methods += f"\n## Contradiction disclosures\n{len(contradictions)} contradictions detected:\n\n"
            for c in contradictions:
                vals = ", ".join(str(cc.value) for cc in c.claims)
                methods += (
                    f"- {c.subject} / {c.predicate}: values [{vals}] "
                    f"{c.claims[0].unit}, rel diff {c.relative_difference*100:.1f}%.\n"
                )

        biblio_section = "\n\n## Bibliography\n"
        for b in multi.bibliography:
            biblio_section += (
                f"[{b['num']}] {b['statement'][:200]} — {b['url']} "
                f"(tier {b['tier']})\n"
            )

        final_report = (
            f"# Research report: {q['question']}\n\n"
            + sections_concat + methods + biblio_section
        )
        (run_dir / "report.md").write_text(final_report, encoding="utf-8")
        (run_dir / "bibliography.json").write_text(
            json.dumps(multi.bibliography, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

        # Evaluator rule checks
        ev_pool = {ev["evidence_id"]: ev for ev in evidence_for_gen}
        ev_out = run_external_evaluation(
            report_text=final_report,
            protocol=protocol,
            tier_distribution_report=asdict(dist),
            contradictions=[asdict(c) for c in contradictions],
            evidence_pool=ev_pool,
            enable_llm_judge=False,
        )
        (run_dir / "evaluator_rule_checks.json").write_text(
            json.dumps(ev_out.to_json_dict(), indent=2, sort_keys=True, default=str) + "\n",
            encoding="utf-8",
        )
        _log(f"[evaluator]   rule_checks={ev_out.rule_check_pass_count}/"
             f"{ev_out.rule_check_pass_count + ev_out.rule_check_fail_count} pass")
        for r in ev_out.rule_checks:
            if not r.passed:
                _log(f"                FAIL {r.item_id}: {r.details[:100]}")

        # Qwen judge
        jr = None
        try:
            jr = await judge_report(
                report_text=final_report,
                research_question=q["question"],
                temperature=0.2,
                max_tokens=800,
            )
            if jr.parse_ok:
                vcounts = {
                    v: sum(1 for j in jr.verdicts.values()
                           if j["verdict"] == v)
                    for v in ("good", "acceptable", "needs_revision", "unknown")
                }
                _log(f"[judge]       {vcounts}")
                for axis, v in jr.verdicts.items():
                    _log(f"              [{v['verdict'].upper():>15}] "
                         f"{axis}: {v['note'][:80]}")
            else:
                _log(f"[judge]       PARSE ERROR: {jr.error}")
            (run_dir / "qwen_judge_output.json").write_text(
                json.dumps({
                    "model": jr.model, "parse_ok": jr.parse_ok,
                    "verdicts": jr.verdicts, "raw": jr.raw_response,
                    "input_tokens": jr.input_tokens,
                    "output_tokens": jr.output_tokens,
                }, indent=2, sort_keys=True, default=str) + "\n",
                encoding="utf-8",
            )
        except Exception as exc:
            _log(f"[judge]       FAILED: {exc}")

        # Manifest — compute unified status BEFORE the write
        # so manifest.status is authoritative (BUG-B-101 fix).
        run_cost = current_run_cost()

        # BUG-M-205: evaluator gate combines deterministic rule failures
        # (PT08 contradiction disclosure, PT11 uncited numerics, PT12
        # invalid citation marker) with Qwen judge verdicts to produce
        # a release-gating decision. Abort class blocks success; partial
        # class prevents clean success but still ships the report.
        from src.polaris_graph.evaluator.evaluator_gate import (  # noqa: E402
            compute_evaluator_gate,
        )
        eval_gate = compute_evaluator_gate(
            ev_out=ev_out,
            qwen_result=jr if (jr and jr.parse_ok) else None,
            adequacy=adequacy,
            completeness=completeness,
        )
        _log(f"[eval_gate]   class={eval_gate.gate_class} "
             f"release_allowed={eval_gate.release_allowed} "
             f"reasons={eval_gate.reasons}")

        if dist.total_sources == 0:
            summary_status = "fail_no_sources"
        elif multi.total_sentences_verified == 0:
            summary_status = "fail_no_verified_prose"
        elif eval_gate.gate_class == "abort":
            # BUG-M-205: evaluator found an integrity failure
            # (PT08 contradiction missing, PT11 uncited numerics,
            # PT12 invalid citation marker).
            summary_status = "abort_evaluator_critical"
        elif getattr(multi, "outline_fallback_used", False):
            # BUG-M-203: planner failed/retry-failed; fallback used.
            summary_status = "ok_outline_fallback"
        elif eval_gate.gate_class == "partial" and eval_gate.qwen_critical_axes:
            # BUG-M-205: Qwen flagged critical axes (citation_tightness,
            # or hedging+tone pair, or multi-axis).
            summary_status = "ok_qwen_advisory"
        elif ev_out.rule_check_fail_count >= 3:
            summary_status = "warn_rule_checks"
        elif adequacy.decision == "expand":
            summary_status = "ok_thin_corpus"
        elif completeness.total_applicable > 0 and \
                completeness.covered_fraction < 0.5:
            summary_status = "ok_incomplete_corpus"
        else:
            summary_status = "ok"
        unified_status = to_unified_status(summary_status)
        manifest = {
            "run_id": run_id,
            "slug": q["slug"],
            "domain": q["domain"],
            "question": q["question"],
            "status": unified_status,
            # BUG-M-205: evaluator gate decision surfaced to downstream
            "release_allowed": eval_gate.release_allowed,
            "evaluator_gate": eval_gate.to_dict(),
            "protocol_sha256": scope.protocol_sha256,
            "retrieval": {
                "pre_filter": retrieval.total_candidates_pre_filter,
                "fetched": retrieval.candidates_fetched,
                "failed": retrieval.candidates_failed_fetch,
                "api_calls": retrieval.api_calls,
            },
            "corpus": {
                "count": dist.total_sources,
                "tier_fractions": dist.tier_fractions,
                "material_deviation": dist.has_material_deviation,
                "approved": approved,
            },
            "adequacy": {
                "decision": adequacy.decision,
                "findings_ok": sum(1 for f in adequacy.findings if f.ok),
                "findings_total": len(adequacy.findings),
                "critical_count": sum(
                    1 for f in adequacy.findings
                    if f.severity == "critical"
                ),
            },
            "completeness": {
                "total_applicable": completeness.total_applicable,
                "total_covered": completeness.total_covered,
                "total_uncovered": completeness.total_uncovered,
                "covered_fraction": round(completeness.covered_fraction, 3),
                "uncovered_topic_ids": completeness.uncovered_topic_ids(),
            },
            "contradictions_found": len(contradictions),
            "generator": {
                "outline_sections": [p.title for p in multi.outline],
                "sections_kept": sum(1 for s in multi.sections
                                     if not s.dropped_due_to_failure),
                "words": multi.total_words,
                "sentences_verified": multi.total_sentences_verified,
                "sentences_dropped": multi.total_sentences_dropped,
                "limitations_words": len(multi.limitations_text.split()),
            },
            "evaluator_rule_pass": ev_out.rule_check_pass_count,
            "evaluator_rule_fail": ev_out.rule_check_fail_count,
            "qwen_verdicts": (
                {v: sum(1 for j in jr.verdicts.values()
                        if j["verdict"] == v)
                 for v in ("good", "acceptable", "needs_revision", "unknown")}
                if jr and jr.parse_ok else {"error": "failed"}
            ),
            "cost_usd": run_cost,
            "budget_cap_usd": PG_MAX_COST_PER_RUN,
        }
        (run_dir / "manifest.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

        _log(f"[cost]        ${run_cost:.4f} (cap ${PG_MAX_COST_PER_RUN:.4f})")

        # Status was computed above (line ~851) and written into the
        # manifest. Mirror to summary for backward compatibility with
        # sweep counters that read the legacy labels.
        summary["status"] = summary_status
        summary["manifest"] = manifest
        summary["cost_usd"] = run_cost
        _log(f"[status]      {summary_status} (manifest.status={unified_status})")
    except Exception as exc:
        tb = traceback.format_exc()
        _log(f"[FATAL]       {exc}")
        _log(tb)
        summary["status"] = "error"
        summary["error"] = str(exc)[:300]
        # BUG-B-101 fix: previously the exception path wrote no
        # manifest, so a crashed run was indistinguishable from a
        # run that never started. Best-effort write.
        try:
            if run_dir is not None:
                run_cost = current_run_cost()
                error_manifest = {
                    "run_id": run_id,
                    "slug": q.get("slug", ""),
                    "domain": q.get("domain", ""),
                    "question": q.get("question", ""),
                    "status": "error_unexpected",
                    "error": str(exc)[:500],
                    "cost_usd": run_cost,
                    "budget_cap_usd": PG_MAX_COST_PER_RUN,
                }
                (run_dir / "manifest.json").write_text(
                    json.dumps(error_manifest, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8",
                )
                summary["manifest"] = error_manifest
                summary["cost_usd"] = run_cost
        except Exception as manifest_exc:
            # Don't mask the original exception if the best-effort
            # manifest write itself fails.
            _log(f"[FATAL]       manifest-write-also-failed: {manifest_exc}")

    log_f.close()
    return summary


async def main_async() -> int:
    out_root = ROOT / "outputs" / "honest_sweep_r3"
    out_root.mkdir(parents=True, exist_ok=True)

    print("=" * 72)
    print("R-3 CROSS-DOMAIN SWEEP — 8 queries across 4 domains")
    print("=" * 72)
    print()

    all_summaries: list[dict] = []
    for q in SWEEP_QUERIES:
        print(f"\n>>> {q['domain']} / {q['slug']}")
        t0 = time.time()
        summary = await run_one_query(q, out_root)
        dt = time.time() - t0
        summary["wall_time_seconds"] = round(dt, 1)
        all_summaries.append(summary)
        print(f"<<< status={summary['status']} cost=${summary.get('cost_usd', 0):.4f} "
              f"wall={dt:.1f}s\n")

    # Write cross-run summary
    sweep_summary_path = out_root / "sweep_summary.json"
    sweep_summary_path.write_text(
        json.dumps(all_summaries, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )

    # Markdown matrix
    md_lines = [
        "# R-3 cross-domain sweep — summary matrix",
        "",
        "| Domain | Slug | Status | Sources | Verified | Words | Rule checks | Judge good/accept/revise | Cost USD | Wall s |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for s in all_summaries:
        m = s.get("manifest", {})
        j = m.get("qwen_verdicts", {})
        jtxt = (
            f"{j.get('good', 0)}/{j.get('acceptable', 0)}/{j.get('needs_revision', 0)}"
            if isinstance(j, dict) and "error" not in j else "—"
        )
        md_lines.append(
            f"| {s['domain']} | {s['slug']} | {s['status']} | "
            f"{m.get('corpus', {}).get('count', '?')} | "
            f"{m.get('generator', {}).get('sentences_verified', '?')} | "
            f"{m.get('generator', {}).get('words', '?')} | "
            f"{m.get('evaluator_rule_pass', '?')}/"
            f"{m.get('evaluator_rule_pass', 0) + m.get('evaluator_rule_fail', 0)} | "
            f"{jtxt} | "
            f"{s.get('cost_usd', 0):.4f} | "
            f"{s.get('wall_time_seconds', 0)} |"
        )
    md_lines.append("")
    total_cost = sum(s.get("cost_usd", 0) or 0 for s in all_summaries)
    md_lines.append(f"**Total sweep cost: ${total_cost:.4f}**")
    md_lines.append(
        f"**Per-query budget cap: ${PG_MAX_COST_PER_RUN:.4f}**"
    )
    md_lines.append("")
    md_lines.append("## Per-query notes")
    md_lines.append("")
    for s in all_summaries:
        md_lines.append(f"### {s['domain']} / {s['slug']}")
        md_lines.append(f"- Question: {s['question']}")
        md_lines.append(f"- Status: **{s['status']}**")
        if s.get("error"):
            md_lines.append(f"- Error: `{s['error']}`")
        md_lines.append(f"- Artifacts: `{s.get('run_dir', '')}`")
        md_lines.append("")

    (out_root / "sweep_summary.md").write_text(
        "\n".join(md_lines) + "\n", encoding="utf-8",
    )

    print("=" * 72)
    print(f"SWEEP COMPLETE. Total cost: ${total_cost:.4f}")
    print(f"  ok:                  {sum(1 for s in all_summaries if s['status'] == 'ok')}")
    print(f"  warn_rule_checks:    {sum(1 for s in all_summaries if s['status'] == 'warn_rule_checks')}")
    print(f"  fail_no_sources:     {sum(1 for s in all_summaries if s['status'] == 'fail_no_sources')}")
    print(f"  fail_no_verified:    {sum(1 for s in all_summaries if s['status'] == 'fail_no_verified_prose')}")
    print(f"  error:               {sum(1 for s in all_summaries if s['status'] == 'error')}")
    print(f"Summary: {sweep_summary_path}")
    print(f"Matrix:  {out_root / 'sweep_summary.md'}")
    return 0


def main() -> int:
    return asyncio.run(main_async())


if __name__ == "__main__":
    sys.exit(main())
