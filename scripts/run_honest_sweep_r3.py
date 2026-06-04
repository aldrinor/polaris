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
# Pipeline modules use both `from src.polaris_graph.X import Y` and
# `from polaris_graph.X import Y` namespaces. Add C:/POLARIS/src so
# the bare-namespace imports resolve. (I-bug-100 documented the
# module-instance identity hazard; for runtime production scripts
# both prefixes must resolve to the same files.)
sys.path.insert(0, str(ROOT / "src"))

logging.basicConfig(
    level=os.environ.get("PG_LOG_LEVEL", "INFO"),
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
    stream=sys.stdout,
)
for noisy in ("httpx", "httpcore"):
    logging.getLogger(noisy).setLevel(logging.WARNING)

from src.polaris_graph.evaluator.external_evaluator import run_external_evaluation  # noqa: E402
from src.polaris_graph.evaluator.live_judge import judge_report  # noqa: E402
# I-safety-002b (#925) PR-2: Path-B benchmark gate (preflight + capture + assert_post_run).
from src.polaris_graph.benchmark import pathB_capture as _pathb  # noqa: E402
from src.polaris_graph.generator.multi_section_generator import (  # noqa: E402
    generate_multi_section_report,
)
from src.polaris_graph.generator.provenance_generator import (  # noqa: E402
    resolve_provenance_to_citations,
    strict_verify,
)
from src.polaris_graph.llm.openrouter_client import (  # noqa: E402
    PG_MAX_COST_PER_RUN,
    BudgetExceededError,
    current_run_cost,
    reset_run_cost,
    set_current_run_id,
)
# M-INT-0b: pin capture + replay
from src.polaris_graph.audit_ir.model_pin import (  # noqa: E402
    DEFAULT_REPLAY_ENV_VARS,
    ModelPin,
    capture_pin,
    pin_from_json,
    pin_to_json,
)
from src.polaris_graph.audit_ir.pin_replay import (  # noqa: E402
    apply_replay_plan,
    build_replay_plan,
)
# M-INT-2: cache + cache-warming
from src.polaris_graph.audit_ir.retrieval_cache import (  # noqa: E402
    RetrievalCacheStore,
)
from src.polaris_graph.audit_ir.cache_warming import (  # noqa: E402
    CacheFetcher,
    FetchResult as WarmFetchResult,
    warm_cache,
)
# M-INT-3: freshness detector + eviction
from src.polaris_graph.audit_ir.freshness_monitor import (  # noqa: E402
    FreshnessAlertStore,
    FreshnessCheckResult,
    FreshnessDetector,
    FreshnessStatus,
    check_freshness,
)
from src.polaris_graph.audit_ir.manifest_augment import augment_v6_manifest  # noqa: E402
from src.polaris_v6.queue.run_events import (  # noqa: E402
    emit_event,
    emit_terminal_event,
)
from src.polaris_graph.nodes.completeness_checker import (  # noqa: E402
    CompletenessReport,
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
# M-INT-4: OpenRouter ScopeAffinityLLM in production scope-gate path
from src.polaris_graph.audit_ir.scope_classifier_llm import (  # noqa: E402
    LLMScopeEligibilityClassifier,
    LLMScopeEligibilityClassifierConfig,
    LLMVerdict,
    OpenRouterScopeAffinityLLM,
)
# M-INT-5: Domain router into live retrieval flow
from src.polaris_graph.audit_ir.domain_router import (  # noqa: E402
    DomainAdapter,
    DomainTemplate,
    DomainTemplateRegistry,
    RoutingOutcome,
    RoutingResult,
    route_to_domain,
)
# M-INT-7: Billing quota gating
from src.polaris_graph.audit_ir.billing_quota_store import (  # noqa: E402
    BillingQuotaStore,
    PlanTier,
    QuotaEventKind,
    QuotaExceededError,
)
# M-INT-6: LLMAugmentedInductor in operator-review queue + M-D1 CI
from src.polaris_graph.auto_induction.keyword_inductor import (  # noqa: E402
    KeywordInductor,
)
from src.polaris_graph.auto_induction.llm_inductor import (  # noqa: E402
    LLMAugmentedInductor,
    LLMAugmentedInductorConfig,
    MockTemplateAffinityClassifier,
)
from src.polaris_graph.auto_induction.precision_metrics import (  # noqa: E402
    InductorVerdict,
)
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
    "partial_evaluator_advisory",    # BUG-M-205: judge flagged critical axes
    "partial_qwen_advisory",         # I-modref-004 (#530): legacy alias, historical manifests
    "partial_saturation",            # I-meta-005 Phase 4 (#988): pruned report, some sections under-covered
    # abort — pipeline refused to produce a report
    "abort_scope_rejected",
    "abort_no_sources",
    "abort_corpus_inadequate",
    "abort_corpus_approval_denied",
    "abort_no_verified_sections",
    "abort_evaluator_critical",      # BUG-M-205: PT08/PT11/PT12 integrity failure
    "abort_budget_exceeded",         # I-meta-008 (#1015): PG_MAX_COST_PER_RUN breached mid-run (generator OR 4-role verifier)
    # error — unhandled exception
    "error_unexpected",
})

# Map legacy summary["status"] labels → unified manifest.status values.
_SUMMARY_TO_UNIFIED: dict[str, str] = {
    "ok": "success",
    "ok_thin_corpus": "partial_thin_corpus",
    "ok_incomplete_corpus": "partial_incomplete_corpus",
    "ok_outline_fallback": "partial_outline_fallback",
    "ok_evaluator_advisory": "partial_evaluator_advisory",
    "ok_qwen_advisory": "partial_qwen_advisory",  # I-modref-004 (#530): legacy alias
    "warn_rule_checks": "partial_rule_check_warnings",
    "fail_no_sources": "abort_no_sources",
    "fail_no_verified_prose": "abort_no_verified_sections",
    "abort_scope_rejected": "abort_scope_rejected",
    "abort_corpus_inadequate": "abort_corpus_inadequate",
    "abort_corpus_approval_denied": "abort_corpus_approval_denied",
    "abort_no_verified_sections": "abort_no_verified_sections",
    "abort_evaluator_critical": "abort_evaluator_critical",
    # I-meta-005 Phase 4 (#988): pruned partial report (some sections under-covered).
    "partial_saturation": "partial_saturation",
    # I-meta-002 sub-PR-6: 4-role D8 release decision (single binding gate). Released =>
    # success; held => a release-blocking abort (D8 held: fabricated occurrence / coverage
    # shortfall / S0 must-cover missing / pending rewrite). Only set on the guarded 4-role path.
    "four_role_released": "success",
    "four_role_held": "abort_four_role_release_held",
    # I-meta-008 (#1015): PG_MAX_COST_PER_RUN breach mid-run (generator OR 4-role verifier) is a
    # clean budget abort, NOT error_unexpected.
    "abort_budget_exceeded": "abort_budget_exceeded",
    "error": "error_unexpected",
}


def to_unified_status(summary_status: str) -> str:
    """Map a legacy summary["status"] label to the unified
    manifest.status taxonomy. Unknown labels become error_unexpected
    (fail loudly for the reader; still a valid taxonomy value)."""
    return _SUMMARY_TO_UNIFIED.get(summary_status, "error_unexpected")


def _prune_plan_to_sufficient_sections(research_plan, sufficiency_report):
    """I-meta-005 Phase 4 (#988): build a PRUNED `ResearchPlan` whose outline
    contains ONLY the SUFFICIENT sections, so the generator (which fixes its
    output structure to `research_plan.outline`) structurally CANNOT render an
    under-covered section in a `partial_saturation` report.

    The plan is index-based (`SectionOutlineItem.sub_query_indices` point into
    `plan.sub_queries`), and the whole-plan facet-union invariant requires
    `union(retained sub_query_indices) == range(len(pruned.sub_queries))`. So the
    prune MUST:
      (1) drop the under-covered `SectionOutlineItem`s;
      (2) drop the now-ORPHANED `sub_queries` (mapped by no retained section);
      (3) REMAP the retained sections' `sub_query_indices` to the compacted
          `sub_queries` list, so all indices stay in-range and the union invariant
          holds on the pruned plan.

    Returns `(pruned_plan, dropped_section_titles)`. `pruned_plan` is None when
    ZERO sections are sufficient (caller aborts `abort_corpus_inadequate`).
    """
    from src.polaris_graph.planning.research_planner import (
        ResearchPlan,
        SectionOutlineItem,
    )

    sub_queries = list(getattr(research_plan, "sub_queries", []) or [])
    outline = list(getattr(research_plan, "outline", []) or [])
    suff_by_unit = {
        u.unit_id: bool(getattr(u, "sufficient", False))
        for u in getattr(sufficiency_report, "per_unit", []) or []
    }

    retained: list = []
    dropped_titles: list[str] = []
    for sec_idx, section in enumerate(outline):
        unit_id = f"section_{sec_idx}"
        if suff_by_unit.get(unit_id, False):
            retained.append(section)
        else:
            dropped_titles.append(getattr(section, "title", "") or unit_id)

    if not retained:
        return None, dropped_titles

    # (2) collect the sub_query indices any retained section maps; (3) build a
    # compaction map old_idx -> new_idx over the retained-and-in-range indices.
    used_old_indices = sorted({
        idx
        for section in retained
        for idx in (getattr(section, "sub_query_indices", []) or [])
        if 0 <= idx < len(sub_queries)
    })
    remap = {old: new for new, old in enumerate(used_old_indices)}
    pruned_sub_queries = [sub_queries[old] for old in used_old_indices]

    pruned_outline: list = []
    for section in retained:
        new_indices = [
            remap[idx]
            for idx in (getattr(section, "sub_query_indices", []) or [])
            if idx in remap
        ]
        pruned_outline.append(
            SectionOutlineItem(
                archetype=getattr(section, "archetype", "") or "Background",
                title=getattr(section, "title", "") or "",
                evidence_target=int(getattr(section, "evidence_target", 0) or 0),
                sub_query_indices=new_indices,
            )
        )

    pruned_plan = ResearchPlan(
        research_question=getattr(research_plan, "research_question", ""),
        frame=getattr(research_plan, "frame", None),
        sub_queries=pruned_sub_queries,
        outline=pruned_outline,
    )
    return pruned_plan, dropped_titles


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


def _retrieval_manifest_section(retrieval) -> dict:
    """#958 (S2): the SINGLE source of truth for a manifest's "retrieval"
    section. Used by BOTH `_base_manifest_envelope` (abort paths) AND the
    inline success-path manifest, so the corpus-truncation flag + counts can
    never be omitted on one path. All getattr with defaults (backward
    compatible with pre-#958 retrieval objects)."""
    return {
        "pre_filter": getattr(retrieval, "total_candidates_pre_filter", 0),
        "fetched": getattr(retrieval, "candidates_fetched", 0),
        "failed": getattr(retrieval, "candidates_failed_fetch", 0),
        "api_calls": getattr(retrieval, "api_calls", {}),
        # #958: fail-loud corpus-truncation signal (was log-only).
        "corpus_truncated": bool(getattr(retrieval, "corpus_truncated", False)),
        "candidates_total": getattr(retrieval, "candidates_total", 0),
        "candidates_processed": getattr(retrieval, "candidates_processed", 0),
    }


def _base_manifest_envelope(
    *,
    run_id: str,
    q: dict,
    retrieval=None,
    run_cost: float = 0.0,
) -> dict:
    """BUG-SCHEMA-R8d fix: every manifest (success AND abort) carries
    the same envelope so downstream consumers get consistent keys
    regardless of exit path.

    Caller adds status-specific fields on top (adequacy, generator,
    evaluator_gate, scope, error, etc.). Using this helper prevents
    the envelope from drifting between exit paths.
    """
    env: dict = {
        "run_id": run_id,
        "slug": q.get("slug", ""),
        "domain": q.get("domain", ""),
        "question": q.get("question", ""),
        "cost_usd": run_cost,
        "budget_cap_usd": PG_MAX_COST_PER_RUN,
    }
    if retrieval is not None:
        env["retrieval"] = _retrieval_manifest_section(retrieval)
    return env


def write_per_run_cost_ledger(run_dir: Path, run_id: str) -> int:
    """BUG-M-206 fix (deep-dive R8): filter the global cost ledger for
    entries tagged with this run_id and write a per-run copy to
    <run_dir>/cost_ledger.jsonl. Returns the count of entries written.

    The global ledger stays authoritative (monotonic append-only log),
    but per-run consumers don't have to grep it by run_id anymore.
    """
    global_path = Path(
        os.environ.get("PG_COST_LEDGER_PATH", "logs/pg_cost_ledger.jsonl")
    )
    if not global_path.exists():
        return 0
    out_path = run_dir / "cost_ledger.jsonl"
    n = 0
    try:
        with open(global_path, "r", encoding="utf-8") as src, \
                open(out_path, "w", encoding="utf-8") as dst:
            for line in src:
                line = line.rstrip("\n")
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if entry.get("session_id") == run_id:
                    dst.write(line + "\n")
                    n += 1
    except OSError as exc:
        logging.getLogger(__name__).warning(
            "per-run cost ledger write failed: %s", exc,
        )
    return n


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
        # Full-scale amplified query set. Each fans out to Serper + S2 +
        # domain backends; dedup pre-filter collapses duplicates. ~30
        # queries targets ~1000 unique URL candidates pre-filter.
        "amplified": [
            # SURPASS program trials
            "tirzepatide SURPASS-1 monotherapy T2DM HbA1c",
            "tirzepatide SURPASS-2 semaglutide comparison",
            "tirzepatide SURPASS-3 insulin degludec",
            "tirzepatide SURPASS-4 insulin glargine",
            "tirzepatide SURPASS-5 insulin glargine",
            "tirzepatide SURPASS-6 basal insulin",
            "tirzepatide SURPASS-J metformin Japan",
            "tirzepatide SURPASS-AP-Combo Asia-Pacific",
            # Efficacy endpoints
            "tirzepatide HbA1c reduction randomized controlled trial",
            "tirzepatide weight loss phase 3 trial",
            "tirzepatide fasting serum glucose reduction",
            "tirzepatide body weight percentage reduction",
            "tirzepatide 15 mg efficacy type 2 diabetes",
            "tirzepatide GIP GLP-1 receptor agonist mechanism",
            # Safety signals
            "tirzepatide gastrointestinal adverse events nausea",
            "tirzepatide treatment discontinuation adverse events",
            "tirzepatide hypoglycemia safety profile",
            "tirzepatide pancreatitis risk long-term",
            "tirzepatide thyroid C-cell safety signal",
            "tirzepatide cardiovascular safety SURPASS-CVOT",
            # Comparative / population
            "tirzepatide vs semaglutide meta-analysis obesity",
            "tirzepatide network meta-analysis GLP-1 agonists",
            "tirzepatide older adults elderly type 2 diabetes",
            "tirzepatide renal impairment dosing",
            "tirzepatide hepatic impairment pharmacokinetics",
            # Real-world + FDA
            "tirzepatide FDA approval Mounjaro Zepbound label",
            "tirzepatide real-world evidence effectiveness",
            "tirzepatide continuation discontinuation long-term outcomes",
            "tirzepatide prescribing information pharmacokinetics",
            "tirzepatide pediatric adolescent investigation",
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
    # I-beat-001 Carney goldset (per outputs/I-beat-001/carney_goldset_v1.md)
    {
        "slug": "carney_ai_sovereignty_canada_compute",
        "domain": "ai_sovereignty",
        "question": (
            "What is the cost-quality-jurisdiction trade-off between Canada "
            "operating its own sovereign frontier-LLM compute (SCALE-AI funded "
            "clusters, Quebec hydro) versus relying on US-headquartered "
            "hyperscalers (Azure, AWS, GCP) for federal-government AI "
            "workloads in 2026?"
        ),
        "amplified": [
            "Canada sovereign AI compute SCALE-AI cluster",
            "CLOUD Act FISA 702 Canadian data jurisdictional risk",
            "Quebec hydro AI compute energy grid",
            "AWS GovCloud Azure Government Canada federal procurement",
            "Canadian Centre for Cyber Security AI cloud guidelines",
            "Pan-Canadian AI Strategy compute infrastructure",
        ],
    },
    {
        "slug": "carney_canada_us_cusma_review_2026",
        "domain": "canada_us",
        "question": (
            "How are Canada's CUSMA review preparations (2026 Article 34.7 "
            "mandatory review) being shaped by the second Trump administration's "
            "tariff threats on Canadian steel, aluminum, and softwood lumber, "
            "and what are the realistic negotiating leverage points for the "
            "Carney government?"
        ),
        "amplified": [
            "CUSMA Article 34.7 review 2026 Canada",
            "Trump tariff Canadian steel aluminum 2026",
            "softwood lumber dispute Canada-US 2026",
            "Section 232 national security tariff Canada",
            "Canadian dairy supply management CUSMA negotiation",
            "Canada-US trade leverage 2026 critical minerals",
        ],
    },
    {
        "slug": "carney_workforce_genai_white_collar",
        "domain": "workforce",
        "question": (
            "What is the projected impact of generative-AI adoption on "
            "Canadian white-collar employment in finance, legal, and "
            "public-sector knowledge work over 2026-2030, and what active "
            "labour-market interventions have evidence of effectiveness in "
            "analogous past technology shocks?"
        ),
        "amplified": [
            "generative AI white collar employment Canada finance legal",
            "Canadian labour market AI displacement augmentation",
            "ESDC retraining technology shock effectiveness",
            "OECD employment outlook generative AI 2026",
            "Statistics Canada labour force AI adoption",
            "Canadian public sector knowledge work AI productivity",
        ],
    },
    {
        "slug": "carney_housing_supply_vs_demand_metros",
        "domain": "policy",
        "question": (
            "What is the evidence base for the effectiveness of supply-side "
            "housing interventions (zoning reform, infrastructure-tied federal "
            "transfers, modular construction subsidies, foreign-buyer bans) "
            "versus demand-side interventions (mortgage stress-test changes, "
            "first-time-buyer incentives, immigration-pacing) on housing "
            "affordability in major Canadian metros 2020-2026?"
        ),
        "amplified": [
            "Canadian housing supply zoning reform evidence",
            "Canada Housing Accelerator Fund effectiveness",
            "mortgage stress test B-20 housing affordability",
            "foreign buyer ban Canada housing prices impact",
            "Toronto Vancouver housing starts policy intervention",
            "CMHC housing supply gap analysis 2026",
        ],
    },
    {
        "slug": "carney_pharmacare_bill_c64_evidence",
        "domain": "policy",
        "question": (
            "What is the evidence base for the effectiveness of pharmacare "
            "programs at reducing population-level chronic-disease morbidity "
            "and out-of-pocket household drug spending, comparing Quebec RPAM, "
            "New Zealand PHARMAC, and UK NHS models, with implications for "
            "the federal Pharmacare Act (Bill C-64) rollout in Canada?"
        ),
        "amplified": [
            "Quebec RPAM pharmacare effectiveness evidence",
            "New Zealand PHARMAC drug pricing health outcomes",
            "UK NHS prescription drug coverage chronic disease",
            "Canada Pharmacare Act Bill C-64 implementation",
            "out-of-pocket drug spending Canada household",
            "CIHI Conference Board pharmacare cost-effectiveness",
        ],
    },
    # I-safety-002b (#925): DRB-EN #72 — AI labor-market lit review. Operator-authorized
    # smoke run for the Path-B gate (per scripts/dr_benchmark/smoke.md). Verbatim prompt
    # from .codex/I-safety-002b/golden_questions_locked.md. Domain "workforce" so the
    # native per_query_report_contract[drb_72_ai_labor] (workforce.yaml) is reachable at
    # runtime (I-meta-002 PR-11 #937): the 4-role Gate-B builder keys the frozen contract
    # by (domain template, slug); domain "custom" left it inert (contract lives in
    # workforce.yaml). Fires corpus_adequacy_gate + strict_verify + evaluator as before.
    {
        "slug": "drb_72_ai_labor",
        "domain": "workforce",
        "question": (
            "Please write a literature review on the restructuring impact of "
            "Artificial Intelligence (AI) on the labor market. Focus on how AI, "
            "as a key driver of the Fourth Industrial Revolution, is causing "
            "significant disruptions and affecting various industries. Ensure the "
            "review only cites high-quality, English-language journal articles."
        ),
        # Amplified retrieval set targeting the 8 Q72 rubric elements via JOURNAL-PUBLISHER
        # site: operators (I-bug-942 #928 fix). The rubric demands "high-quality, English-
        # language journal articles" exactly; targeting AEA/QJE/JPE/Science/Wiley directly
        # pulls T1 sources past the corpus_adequacy_gate.
        "amplified": [
            "site:aeaweb.org Autor why are there still so many jobs Journal of Economic Perspectives",
            "site:aeaweb.org Goos Manning Salomons explaining job polarization American Economic Review",
            "site:aeaweb.org Acemoglu Restrepo automation and new tasks Journal of Economic Perspectives",
            "site:journals.uchicago.edu Acemoglu Restrepo robots and jobs Journal of Political Economy",
            "site:academic.oup.com Brynjolfsson generative AI at work Quarterly Journal of Economics",
            "site:academic.oup.com Autor Levy Murnane skill content technological change Quarterly Journal of Economics",
            "site:science.org Eloundou GPTs are GPTs large language models labor",
            "site:science.org Noy Zhang generative artificial intelligence productivity",
            "site:sciencedirect.com Frey Osborne future of employment computerisation Technological Forecasting Social Change",
            "site:onlinelibrary.wiley.com Goldsmith Casey fourth industrial revolution Southern Economic Journal",
            "Frey Osborne 2017 Technological Forecasting Social Change 47 percent computerisation",
            "Acemoglu Restrepo race between man and machine 2018 American Economic Review",
            "Acemoglu Restrepo 2020 robots and jobs Journal of Political Economy 128",
            "Brynjolfsson Li Raymond 2025 generative AI at work productivity QJE",
            "Autor 2015 Journal of Economic Perspectives why so many jobs",
            "Goos Manning Salomons 2014 American Economic Review polarization routine-biased",
            "skill-biased technical change wage inequality peer reviewed economics",
            "AI labor market exposure occupations literature review journal",
            "automation employment effects commuting zones manufacturing peer reviewed",
            "generative AI productivity field experiment journal article",
        ],
    },
    # I-meta-002 PR-11 (#937): remaining 4 LOCKED golden DRB-EN benchmark questions
    # (#75/#76/#78/#90 — #72 above). Verbatim prompts from
    # .codex/I-safety-002b/golden_questions_locked.md. Each slug EXACTLY equals its frozen
    # native per_query_report_contract key so load_scope_template(domain) +
    # load_required_entities(template, slug) resolves the contract at runtime (a routing
    # typo fail-closes in the M3a builder). These are NO-NETWORK registration stubs: no
    # `amplified` / seed field, so import + registration trigger no live fetch/spend.
    {
        "slug": "drb_75_metal_ions_cvd",
        "domain": "clinical",
        "question": (
            "Could therapeutic interventions aimed at modulating plasma metal "
            "ion concentrations represent effective preventive or therapeutic "
            "strategies against cardiovascular diseases? What types of "
            "interventions—such as supplementation—have been proposed, and is "
            "there clinical evidence supporting their feasibility and efficacy?"
        ),
    },
    {
        "slug": "drb_76_gut_microbiota_crc",
        "domain": "clinical",
        "question": (
            "The significance of the gut microbiota in maintaining normal "
            "intestinal function has emerged as a prominent focus in "
            "contemporary research, revealing both beneficial and detrimental "
            "impacts on the equilibrium of gut health. Disruption of microbial "
            "homeostasis can precipitate intestinal inflammation and has been "
            "implicated in the pathogenesis of colorectal cancer. Conversely, "
            "probiotics have demonstrated the capacity to mitigate inflammation "
            "and retard the progression of colorectal cancer. Within this "
            "domain, key questions arise: What are the predominant types of gut "
            "probiotics? What precisely constitutes prebiotics and their "
            "mechanistic role? Which pathogenic bacteria warrant concern, and "
            "what toxic metabolites do they produce? How might these findings "
            "inform and optimize our daily dietary choices?"
        ),
    },
    {
        "slug": "drb_78_parkinsons_dbs",
        "domain": "clinical",
        "question": (
            "Parkinson's disease has a profound impact on patients. What are "
            "the potential health warning signs associated with different "
            "stages of the disease? As family members, which specific signs "
            "should alert us to intervene or seek medical advice regarding the "
            "patient's condition? Furthermore, for patients who have undergone "
            "Deep Brain Stimulation (DBS) surgery, what daily life adjustments "
            "and support strategies can be implemented to improve their comfort "
            "and overall well-being?"
        ),
    },
    {
        "slug": "drb_90_adas_liability",
        "domain": "policy",
        "question": (
            "Analyze the complex issue of liability allocation in accidents "
            "involving vehicles with advanced driver-assistance systems (ADAS) "
            "operating in a shared human-machine driving context. Your analysis "
            "should integrate technical principles of ADAS, existing legal "
            "frameworks, and relevant case law to systematically examine the "
            "boundaries of responsibility between the driver and the system. "
            "Conclude with proposed regulatory guidelines or recommendations."
        ),
    },
]


# ---------------------------------------------------------------------------
# M-INT-0b — Pin capture on every sweep run (Phase E0)
# ---------------------------------------------------------------------------
#
# Wires `model_pin.capture_pin(...)` into every sweep run, so each
# completed query writes a `model_pin.json` to its run_dir. Enables
# `--replay-from-pin <path>` to apply a captured pin's runtime
# configuration (env vars + model assignments) before re-running.
#
# Per FINAL_PLAN.md M-INT-0b acceptance:
#   - Substrate IS imported (capture_pin, replay primitives) — see imports
#   - Substrate IS invoked (this helper called from run_one_query)
#   - Run-log evidence: model_pin.json written to run_dir; manifest.json
#     references it
#   - PG_CAPTURE_PIN=0 disables (rollback)
#
# Reproducibility/nondeterminism risk (FINAL_PLAN.md §F risk #3) is
# mitigated by capturing the pin BEFORE Phase E1's parallel fetch /
# cache / freshness integrations land. Every subsequent run is then
# replayable.


# ---------------------------------------------------------------------------
# M-INT-2 — Cache + cache-warming around sweep entry (Phase E1)
# ---------------------------------------------------------------------------
#
# Wires `cache_warming.warm_cache(...)` into the sweep so canonical
# sources for each query can be pre-warmed before the live retrieval
# runs. Idempotent: re-running the sweep on the same canonical URLs
# skips the fetch (cache_hit_count>0) on the second pass.
#
# Acceptance bar:
#   - Imported (warm_cache, CacheFetcher, RetrievalCacheStore)
#   - Invoked (warm_cache called from main_async pre-sweep)
#   - Run-log evidence: WarmingReport written to manifest path
#   - PG_USE_CACHE_WARMING=0 disables (rollback)


def _cache_db_path(out_root: Path) -> Path:
    raw = os.environ.get("PG_RETRIEVAL_CACHE_DB_PATH")
    if raw:
        return Path(raw)
    return out_root / "retrieval_cache.sqlite"


def _warm_canonical_corpus(
    workspace_id: str,
    canonical_urls: list[str],
    out_root: Path,
) -> dict | None:
    """Best-effort cache-warm. Returns the WarmingReport summary
    dict, or None when disabled / no URLs / failure.

    Failure logged but does NOT raise — telemetry/observability
    must not gate the sweep.
    """
    if os.environ.get("PG_USE_CACHE_WARMING", "1") == "0":
        return None
    if not canonical_urls:
        return None
    try:
        store = RetrievalCacheStore(_cache_db_path(out_root))

        class _StubHttpFetcher:
            """v1 noop fetcher: returns a minimal payload so the cache
            entry exists. Real HTTP wiring comes in Phase F /
            production. The substrate import + invocation is what
            M-INT-2 demonstrates."""

            def fetch(self, source_url: str) -> WarmFetchResult:
                # Returning empty payload still creates the cache
                # entry, demonstrating end-to-end wiring.
                return WarmFetchResult(
                    payload=b"",
                    content_type="text/plain",
                    fetch_status_code=200,
                )

        report = warm_cache(
            store,
            workspace_id,
            canonical_urls,
            _StubHttpFetcher(),
            skip_existing=True,
            on_fetcher_error="record",
        )
        return {
            "fetched_count": report.fetched_count,
            "skipped_count": report.skipped_count,
            "errored_count": report.errored_count,
            "started_at": report.started_at,
            "finished_at": report.finished_at,
        }
    except Exception as exc:
        print(f"[M-INT-2] WARN: cache warming failed: {exc}")
        return None


# ---------------------------------------------------------------------------
# M-INT-3 — Freshness detector + eviction (Phase E1)
# ---------------------------------------------------------------------------
#
# Wires `freshness_monitor.check_freshness(...)` +
# FreshnessAlertStore into the sweep. For each canonical URL,
# run a freshness check; if status is in evicting set
# (superseded/retracted/EoC), evict from the cache.
#
# v1 stub detector: returns UNCHANGED for everything. Real
# Crossref `update-policy` integration is Phase F.
# Substrate import + invocation + SQL writes are demonstrated.


def _freshness_db_path(out_root: Path) -> Path:
    raw = os.environ.get("PG_FRESHNESS_DB_PATH")
    if raw:
        return Path(raw)
    return out_root / "freshness_alerts.sqlite"


def _check_corpus_freshness(
    workspace_id: str,
    canonical_urls: list[str],
    out_root: Path,
) -> dict | None:
    """Best-effort freshness check + eviction. Returns a summary
    dict with per-status counts, or None when disabled."""
    if os.environ.get("PG_USE_FRESHNESS_DETECTOR", "1") == "0":
        return None
    if not canonical_urls:
        return None
    try:
        alert_store = FreshnessAlertStore(_freshness_db_path(out_root))
        cache_store = RetrievalCacheStore(_cache_db_path(out_root))

        class _StubFreshnessDetector:
            """v1 detector: returns UNCHANGED for every URL.
            Real Crossref update-policy probe is Phase F.
            Demonstrates substrate import + invocation +
            FreshnessCheckResult shape."""

            def detect(self, source_url: str) -> FreshnessCheckResult:
                return FreshnessCheckResult(
                    source_url=source_url,
                    status=FreshnessStatus.UNCHANGED,
                    details="stub detector v1 (real Crossref in Phase F)",
                    new_canonical_url=None,
                    fetched_status_code=200,
                )

        detector = _StubFreshnessDetector()
        per_status: dict[str, int] = {
            s.value: 0 for s in FreshnessStatus
        }
        evicted = 0
        for url in canonical_urls:
            try:
                alert = check_freshness(
                    workspace_id=workspace_id,
                    source_url=url,
                    detector=detector,
                    store=alert_store,
                    cache=cache_store,
                )
                per_status[alert.status] = per_status.get(alert.status, 0) + 1
                if alert.evicted_cache_key is not None:
                    evicted += 1
            except Exception as exc:
                print(f"[M-INT-3] WARN: freshness check failed for "
                      f"{url}: {exc}")
        return {
            "per_status": per_status,
            "evicted_count": evicted,
            "total_checked": len(canonical_urls),
        }
    except Exception as exc:
        print(f"[M-INT-3] WARN: freshness path failed: {exc}")
        return None


# ──────────────────────────────────────────────────────────────────────
# M-INT-4 — OpenRouter ScopeAffinityLLM in production (Phase E2)
# ──────────────────────────────────────────────────────────────────────


# Closed taxonomy of supported domains for the LLM scope classifier.
# Mirrors `scope_gate.SUPPORTED_DOMAINS` minus `custom` (LLM is asked
# to pick a real domain, not the catch-all UI bucket).
_SCOPE_LLM_SUPPORTED_DOMAINS: tuple[str, ...] = (
    "clinical", "policy", "tech", "due_diligence",
)


def _build_scope_llm():
    """Factory for the production scope LLM. Tests monkeypatch this
    to inject a Mock or broken classifier without instantiating the
    OpenRouter client (which requires OPENROUTER_API_KEY)."""
    return OpenRouterScopeAffinityLLM()


def _classify_scope_with_llm(
    question: str,
    domain: str,
) -> dict | None:
    """Best-effort LLM scope classification, run alongside the
    deterministic template-driven `run_scope_gate`. Returns a
    summary dict or None when disabled / empty input.

    Per LAW II — failure must NOT gate the sweep. Any exception
    in the LLM path is caught and logged; an UNCERTAIN verdict
    is recorded so operator-review can pick it up.
    """
    if os.environ.get("PG_USE_LLM_SCOPE", "0") == "0":
        return None
    if not question or not isinstance(question, str):
        return None
    try:
        llm = _build_scope_llm()
        config = LLMScopeEligibilityClassifierConfig(
            supported_domains=_SCOPE_LLM_SUPPORTED_DOMAINS,
        )
        classifier = LLMScopeEligibilityClassifier(llm, config)
        classification = classifier.classify(question)
        return {
            "verdict": classification.verdict.value,
            "confidence": classification.confidence,
            "domain": classification.domain,
            "rationale": classification.rationale,
            "template_domain_hint": domain,
        }
    except Exception as exc:
        print(f"[M-INT-4] WARN: scope LLM path failed: {exc}")
        return None


# ──────────────────────────────────────────────────────────────────────
# M-INT-5 — Domain router into live retrieval flow (Phase E2)
# ──────────────────────────────────────────────────────────────────────


class _StubCrossrefAdapter:
    """v1 stub DomainAdapter for clinical (Crossref).

    Real HTTP wiring is Phase F. v1 demonstrates substrate
    import + invocation + RoutingResult shape; the actual
    Crossref retrieval will plug into adapter_id="crossref"
    once concrete adapters land.
    """

    @property
    def adapter_id(self) -> str:
        return "crossref"


class _StubPubmedAdapter:
    """v1 stub DomainAdapter for clinical (PubMed)."""

    @property
    def adapter_id(self) -> str:
        return "pubmed"


def _build_domain_router_registry() -> DomainTemplateRegistry:
    """Default registry. Tests can monkeypatch this for custom
    template sets. Real config-driven registry comes in Phase F."""
    return DomainTemplateRegistry(
        templates=(
            DomainTemplate(
                domain_id="clinical",
                display_name="Clinical research",
                scope_template_path="config/scope_templates/clinical.yaml",
                expected_adapter_ids=("crossref", "pubmed"),
            ),
            DomainTemplate(
                domain_id="policy",
                display_name="Policy / regulatory",
                scope_template_path="config/scope_templates/policy.yaml",
                expected_adapter_ids=("crossref",),
            ),
        )
    )


def _build_domain_router_adapters() -> dict[str, DomainAdapter]:
    """Default adapter pool. Real HTTP-backed adapters in Phase F."""
    return {
        "crossref": _StubCrossrefAdapter(),
        "pubmed": _StubPubmedAdapter(),
    }


def _route_query_to_domain(
    classification,
    *,
    requested_domain: str | None = None,
) -> dict | None:
    """Best-effort domain routing for the LLM scope classification.
    Telemetry only — does NOT gate retrieval. PG_USE_DOMAIN_ROUTER=0
    disables. Per LAW II, internal failure returns None (does not raise).

    Codex round-1 MEDIUM fix (v2): when result.template is None
    (UNKNOWN_DOMAIN, REJECTED_*, MISSING_ADAPTERS), the routing
    summary's `domain` was None — the original LLM-asserted domain
    tag was lost. v2 surfaces the original `requested_domain`
    alongside `domain` so unknown-domain telemetry preserves
    "user asked for X, registry doesn't know it" signal.
    """
    if os.environ.get("PG_USE_DOMAIN_ROUTER", "0") == "0":
        return None
    # Default to classification.domain if caller didn't pass one.
    if requested_domain is None and hasattr(classification, "domain"):
        requested_domain = classification.domain
    try:
        registry = _build_domain_router_registry()
        adapters = _build_domain_router_adapters()
        result = route_to_domain(classification, registry, adapters)
        return {
            "outcome": result.outcome.value,
            "domain": (
                result.template.domain_id if result.template else None
            ),
            "requested_domain": requested_domain,
            "adapter_ids": [a.adapter_id for a in result.adapters],
            "rationale": result.rationale,
        }
    except Exception as exc:
        print(f"[M-INT-5] WARN: domain_router path failed: {exc}")
        return None


# ──────────────────────────────────────────────────────────────────────
# M-INT-7 — Billing quota gating (Phase E4)
# ──────────────────────────────────────────────────────────────────────


def _check_audit_run_quota() -> dict | None:
    """Best-effort billing quota check + consume for one audit run.
    Returns a summary dict or None when disabled / no org configured.

    Per LAW II — internal failure returns None (does not raise).
    QuotaExceededError is caught and returned as a structured
    summary with `consumed=False, exceeded=True` so the caller
    can decide whether to abort the run with a quota status.

    PG_USE_BILLING_QUOTA=0 disables (default 0 in v1).
    PG_BILLING_ORG_ID specifies which org to charge.
    """
    if os.environ.get("PG_USE_BILLING_QUOTA", "0") == "0":
        return None
    org_id = os.environ.get("PG_BILLING_ORG_ID", "").strip()
    if not org_id:
        # No org configured — best-effort, don't gate sweep without
        # an explicit assignment.
        return None
    try:
        db_path = Path(os.environ.get(
            "PG_BILLING_QUOTA_DB_PATH",
            str(Path("state") / "billing_quota.sqlite"),
        ))
        store = BillingQuotaStore(db_path)
        try:
            event = store.consume(
                org_id=org_id,
                kind=QuotaEventKind.AUDIT_RUN_ENQUEUED,
            )
            check = store.check_quota(
                org_id=org_id,
                kind=QuotaEventKind.AUDIT_RUN_ENQUEUED,
            )
            return {
                "consumed": True,
                "exceeded": False,
                "org_id": org_id,
                "event_id": event.event_id,
                "used": check.used,
                "cap": check.cap,
                "remaining": check.remaining,
            }
        except QuotaExceededError as exc:
            return {
                "consumed": False,
                "exceeded": True,
                "org_id": org_id,
                "reason": str(exc),
            }
    except Exception as exc:  # noqa: BLE001
        print(f"[M-INT-7] WARN: billing quota path failed: {exc}")
        return None


# ──────────────────────────────────────────────────────────────────────
# M-INT-6 — LLMAugmentedInductor + operator-review queue (Phase E3)
# ──────────────────────────────────────────────────────────────────────


def _build_inductor():
    """Factory for the production inductor. Tests monkeypatch this
    to inject a known-abstaining or known-accepting inductor without
    depending on the (mocked-or-real) LLM classifier path.

    v1: KeywordInductor base + MockTemplateAffinityClassifier in
    LLMAugmentedInductor. Real OpenRouter-backed classifier wiring
    is Phase F (M-LIVE-2). Substrate import + invocation +
    InductorVerdict shape demonstrated.
    """
    return LLMAugmentedInductor(
        base_inductor=KeywordInductor(),
        llm_classifier=MockTemplateAffinityClassifier(),
        config=LLMAugmentedInductorConfig(),
    )


def _record_operator_review_item(
    *,
    run_dir: Path,
    query: str,
    verdict: InductorVerdict,
) -> None:
    """Append an abstaining inductor verdict to the run's
    operator-review queue (one JSONL per sweep run). Called only
    when verdict.decision == 'abstain' — the operator-review
    queue is exactly the set of cases the inductor declined to
    auto-induce."""
    queue_path = run_dir / "operator_review_queue.jsonl"
    item = {
        "ts": _utc_now_iso(),
        "query": query,
        "decision": verdict.decision,
        "confidence": verdict.confidence,
        "abstain_reason": verdict.abstain_reason,
    }
    queue_path.parent.mkdir(parents=True, exist_ok=True)
    with queue_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(item, sort_keys=True) + "\n")


def _utc_now_iso() -> str:
    """ISO-8601 UTC timestamp for queue rows."""
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


def _induce_with_llm(
    query: str,
    run_dir: Path,
) -> dict | None:
    """Best-effort auto-induction. Telemetry only — does NOT
    gate retrieval. PG_USE_AUTO_INDUCTION=0 disables.
    Per LAW II, internal failure returns None (does not raise).

    Abstain verdicts are recorded to operator_review_queue.jsonl
    in run_dir, surfacing them for human review.
    """
    if os.environ.get("PG_USE_AUTO_INDUCTION", "0") == "0":
        return None
    if not query or not isinstance(query, str):
        return None
    try:
        inductor = _build_inductor()
        verdict = inductor.induce(query)
        summary = {
            "decision": verdict.decision,
            "confidence": verdict.confidence,
            "abstain_reason": verdict.abstain_reason,
            "induced_slug": (
                getattr(verdict.induced_contract, "slug", None)
                if verdict.induced_contract is not None else None
            ),
        }
        if verdict.decision == "abstain":
            try:
                _record_operator_review_item(
                    run_dir=run_dir, query=query, verdict=verdict,
                )
            except Exception as exc:  # noqa: BLE001
                print(
                    f"[M-INT-6] WARN: operator-review queue write "
                    f"failed: {exc}"
                )
        return summary
    except Exception as exc:  # noqa: BLE001
        print(f"[M-INT-6] WARN: inductor path failed: {exc}")
        return None


def _capture_run_pin(
    run_id: str,
    run_dir: Path,
    *,
    notes: str = "",
) -> Path | None:
    """Best-effort sweep-run pin capture. Returns the path to the
    written `model_pin.json`, or None when disabled / failed.

    Failure does NOT raise — telemetry/observability writes must
    not gate the actual sweep result.
    """
    if os.environ.get("PG_CAPTURE_PIN", "1") == "0":
        return None
    try:
        # Minimal generator-role pin from current OPENROUTER_DEFAULT_MODEL.
        # Future M-INT-0b v2 may extend with evaluator/judge/inductor roles.
        generator_model = os.environ.get(
            "OPENROUTER_DEFAULT_MODEL", "unknown"
        )
        pin = capture_pin(
            run_id=run_id,
            llm_models={"generator": generator_model},
            llm_providers={"generator": "openrouter"},
            capture_env_var_names=DEFAULT_REPLAY_ENV_VARS,
            notes=notes,
        )
        pin_path = run_dir / "model_pin.json"
        pin_path.write_text(pin_to_json(pin) + "\n", encoding="utf-8")
        return pin_path
    except Exception as exc:  # noqa: BLE001 — intentional broad
        # Per LAW II + FINAL_PLAN risk #3 mitigation: pin capture
        # failure must never gate the sweep. Log and continue.
        print(f"[M-INT-0b] WARN: pin capture failed for {run_id}: {exc}")
        return None


def _attach_tool_utilization(manifest: dict, run_dir: Path) -> dict:
    """I-meta-007b (#meta-007) P1: attach the per-run tool-utilization summary
    to ``manifest`` (and write ``run_dir/tool_summary.json``) immediately before
    EVERY ``manifest.json`` write — success AND all abort/error paths.

    Thin fail-safe wrapper around
    :func:`src.polaris_graph.telemetry.tool_tracer.attach_tool_utilization`.
    Pure no-op when PG_ENABLE_TOOL_TRACKER selects OFF (manifest unchanged, no
    file written), so OFF-mode manifest.json stays byte-identical. Any telemetry
    or import error is swallowed + logged so it can never abort the run.
    """
    try:
        from src.polaris_graph.telemetry.tool_tracer import (
            attach_tool_utilization as _attach,
        )
        return _attach(manifest, run_dir)
    except Exception as _tt_exc:  # noqa: BLE001 — telemetry must not abort the run
        print(f"[tool_tracker] utilization attach skipped: {_tt_exc}")
        return manifest


def _abort_if_cancelled(
    q: dict,
    run_dir: Path,
    run_id: str,
    summary: dict,
    log_fn,
) -> bool:
    """I-rdy-011 (#507): cooperative cancel checkpoint for a v6 run.

    If a cancellation was requested for this v6 run, write a terminal
    `cancelled` manifest, emit the SSE terminal event, mark the summary, and
    return True so run_one_query aborts early at this stage boundary. Returns
    False for non-v6 runs or when no cancel is pending.

    Best-effort: a run_store lookup failure returns False — a healthy run is
    never aborted on a transient backend hiccup.
    """
    ext = q.get("external_run_id")
    if not (q.get("v6_mode") and ext):
        return False
    try:
        from polaris_v6.queue import run_store

        if not run_store.is_cancel_requested(ext):
            return False
    except Exception:  # noqa: BLE001 — cancel-check failure must not abort a healthy run
        return False
    log_fn("[cancel]      cancellation requested — aborting run cooperatively")
    manifest = {
        "run_id": run_id,
        "slug": q.get("slug", ""),
        "domain": q.get("domain", ""),
        "question": q.get("question", ""),
        "status": "cancelled",
    }
    manifest = _attach_tool_utilization(manifest, run_dir)
    (run_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    emit_event(ext, "run.completed", {"status": "cancelled"})
    summary["status"] = "cancelled"
    return True


def _normalize_quantified_telemetry(telemetry: dict) -> dict:
    """Add a normalized ``fired`` boolean to the Phase-7 quantified telemetry (I-meta-008 P1-3,
    #1018) so a post-run assertion can detect a SILENT no-op.

    The quantified block intentionally NEVER aborts the run (broad ``except`` in run_one_query), so
    an error or ``spec_produced=False`` would otherwise leave the manifest carrying the raw
    telemetry but no single clear "did the differentiator actually run" signal. ``fired`` is True
    iff the section produced at least one verified quantified sentence. Idempotent (``setdefault``).
    """
    telemetry.setdefault("fired", int(telemetry.get("verified_sentences", 0) or 0) > 0)
    return telemetry


async def run_one_query(
    q: dict,
    out_root: Path,
    *,
    four_role_transport=None,
    four_role_inputs=None,
    four_role_input_builder=None,
) -> dict:
    """Run the full honest pipeline on one query. Returns a summary dict.

    I-meta-002 sub-PR-6 (4-role wiring, GUARDED + default OFF): the 4-role evaluation path
    activates ONLY when BOTH ``four_role_transport`` is supplied (an explicit, INJECTED
    ``RoleTransport`` — there is NO default real transport; live transport is Gate-B after lock
    promotion) AND ``PG_FOUR_ROLE_MODE`` is enabled (env "1"/"true"/"True"). When OFF (the
    default), the legacy evaluator-gate path below is byte-unchanged. ``four_role_inputs`` is the
    caller-supplied ``FourRoleEvaluationInputs`` (claims with EXISTING ids, the canonical
    required-element coverage ledger, and the required-S0 set) — the sweep NEVER synthesizes
    them from the report (that extraction is Gate-B). When the branch fires it delegates entirely
    to ``sweep_integration.run_four_role_seam`` (D8 is the single binding gate) and
    overrides BOTH ``manifest['release_allowed']`` AND ``manifest['status']`` from the D8
    decision, demoting the legacy evaluator_gate to ADVISORY metadata only.

    I-meta-002 PR-9/M3b (Gate-B wiring): ``four_role_input_builder`` is an OPTIONAL no-argument
    closure (wired by ``scripts/dr_benchmark/run_gate_b.py`` over the native
    ``build_native_gate_b_inputs`` + evidence normalization). When supplied it WINS over a
    static ``four_role_inputs``: it is called AFTER generation to PRODUCE the inputs+audit
    bundle, and the seam writes the per-claim audit map to ``four_role_claim_audit.json`` next
    to the run. The default (both None while the branch is OFF) leaves the legacy path
    byte-unchanged.
    """
    reset_run_cost()
    # I-bug-111: reset synthesis-scrub alert + telemetry at run
    # boundary so per-run manifest reflects ONLY this run's
    # synthesis behavior. Without this reset, the sticky alert from
    # query N leaks into query N+1's manifest. Defensive lazy
    # import: tolerate environments where the module isn't loaded.
    try:
        from src.polaris_graph.generator.analyst_synthesis import (
            reset_synthesis_scrub_alert,
            reset_synthesis_telemetry,
        )
        reset_synthesis_scrub_alert()
        reset_synthesis_telemetry()
    except Exception:  # noqa: BLE001 — defensive: alert reset failure must not abort run
        pass

    # I-arch-001a: v6 actor passes out_root_override (UUID-scoped artifact_dir)
    # to prevent same-slug concurrent overwrites. Legacy CLI sweep keeps the
    # domain/slug nesting unchanged.
    _v6_override = q.get("out_root_override") if q.get("v6_mode") else None
    run_dir = Path(_v6_override) if _v6_override else (out_root / q["domain"] / q["slug"])
    run_dir.mkdir(parents=True, exist_ok=True)
    run_id = f"SWEEP_{q['domain']}_{q['slug']}_{int(time.time())}"
    # BUG-N-301 fix: set ambient run_id so every downstream
    # OpenRouterClient tags its cost-ledger entries with this run.
    set_current_run_id(run_id)

    # I-gen-004 (#496): run-scoped reasoning-trace collector. Write-through
    # mode — the jsonl is rewritten on every record/update so it is current
    # on disk regardless of which abort / error / success path the run exits
    # through. Sink lifecycle mirrors set_current_run_id (set here, released
    # in the run tail).
    from src.polaris_graph.generator.reasoning_trace import (
        ReasoningTraceCollector,
    )
    from src.polaris_graph.llm.openrouter_client import set_reasoning_sink
    _reasoning_collector = ReasoningTraceCollector(out_dir=run_dir)
    # I-gen-561 (#561) P2-2: materialize the (possibly empty)
    # reasoning_trace.jsonl now, so a run that aborts before any generator
    # LLM call still produces the file augment_v6_manifest() references.
    _reasoning_collector.flush(run_dir)
    set_reasoning_sink(_reasoning_collector)

    # I-meta-002-q1d (#945): per-call retrieval_trace.jsonl (mirror of reasoning_trace.jsonl for the
    # search/fetch half — the operator's §-1.1 line-by-line audit requirement). Start a FRESH per-query
    # trace and materialize the (possibly empty) file now so an early abort still produces it. The
    # recorders are best-effort no-ops; the §9.1 retrieval/verify chokepoint is never altered.
    from src.polaris_graph.benchmark.pathB_capture import (
        retrieval_trace_records as _retrieval_trace_records,
        start_retrieval_trace as _start_retrieval_trace,
    )
    _start_retrieval_trace()

    def _flush_retrieval_trace() -> None:
        try:
            with (run_dir / "retrieval_trace.jsonl").open("w", encoding="utf-8") as _rt:
                for _rec in _retrieval_trace_records():
                    _rt.write(json.dumps(_rec, ensure_ascii=False) + "\n")
        except Exception as _exc:  # noqa: BLE001 — best-effort observability, never abort the run
            print(f"[retrieval_trace] flush error (skipped): {_exc}")

    _flush_retrieval_trace()

    # I-meta-007b (#meta-007): per-tool utilization tracer. ON-mode additive,
    # record-only, spend-free. Reset the process-global singleton FIRST so a
    # multi-query sweep binds each query's tracer to its OWN run_dir (and never
    # accumulates calls across queries), then bind to this run_dir. Guarded by
    # PG_ENABLE_TOOL_TRACKER (default "1"): when OFF we reset to a fresh
    # in-memory tracer with NO run_dir, so no tool_trace.jsonl is written and
    # the manifest stays byte-identical (the tool_utilization key is gated on
    # _tool_tracker_on below). Best-effort — a telemetry import error must not
    # abort the run.
    _tool_tracker_on = os.environ.get("PG_ENABLE_TOOL_TRACKER", "1").strip() in (
        "1", "true", "True",
    )
    try:
        from src.polaris_graph.telemetry.tool_tracer import (
            get_tool_tracer as _get_tool_tracer,
            reset_tool_tracer as _reset_tool_tracer,
        )
        _reset_tool_tracer()
        _get_tool_tracer(run_dir if _tool_tracker_on else None)
    except Exception as _tt_exc:  # noqa: BLE001 — telemetry must not abort the run
        print(f"[tool_tracker] init skipped: {_tt_exc}")

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

        # I-arch-001e: stage event for SSE consumers (v6_mode only; no-op otherwise).
        if q.get("v6_mode") and q.get("external_run_id"):
            emit_event(
                q.get("external_run_id"),
                "scope_gate.completed",
                {
                    "decision": scope.protocol.scope_decision,
                    "reason": "; ".join(scope.protocol.scope_reasons) if scope.protocol.scope_rejected else "in_scope",
                },
            )

        # I-rdy-011 (#507): cooperative cancel checkpoint — before the
        # retrieval stage (the first long-running stage).
        if _abort_if_cancelled(q, run_dir, run_id, summary, _log):
            return summary

        # M-INT-4: best-effort LLM scope classification alongside
        # the deterministic template-driven gate. Telemetry only —
        # does NOT gate retrieval. PG_USE_LLM_SCOPE=0 disables.
        # Codex round-2 HIGH fix (v3): wrap the helper call itself
        # in try/except. v2 only protected against malformed dict
        # shapes; if the helper RAISES (e.g. unexpected internal
        # path, monkeypatched test stub, future bug introduced),
        # the exception escaped to the outer fatal handler with
        # status=error. Defense-in-depth: helper has its own
        # try/except internally; sweep adds a second layer per
        # LAW II "best-effort telemetry must not gate sweep".
        try:
            scope_llm_summary = _classify_scope_with_llm(
                question=q["question"],
                domain=q["domain"],
            )
        except Exception as exc:  # noqa: BLE001
            print(f"[M-INT-4] WARN: scope_llm helper raised: {exc}")
            scope_llm_summary = None
        if scope_llm_summary is not None:
            # Codex round-1 HIGH fix (v2): use .get() to defend
            # against a malformed M-INT-4 dict (e.g. missing
            # "confidence" key). v1 used `dict["key"]` here which
            # raised KeyError BEFORE the M-INT-5 try block — that
            # aborted run_one_query via the outer fatal handler
            # with status=error, violating LAW II's best-effort-
            # telemetry semantic.
            try:
                _v4_verdict = scope_llm_summary.get("verdict")
                _v4_conf = scope_llm_summary.get("confidence", 0.0)
                _v4_domain = scope_llm_summary.get("domain")
                _v4_hint = scope_llm_summary.get("template_domain_hint")
                _log(
                    f"[M-INT-4]     scope_llm: verdict={_v4_verdict} "
                    f"confidence={float(_v4_conf):.2f} "
                    f"domain={_v4_domain} "
                    f"template_hint={_v4_hint}"
                )
            except Exception as exc:  # noqa: BLE001
                print(f"[M-INT-4] WARN: scope_llm log line failed: {exc}")

            # M-INT-5: route the LLM scope verdict to a domain.
            # Best-effort, telemetry-only. PG_USE_DOMAIN_ROUTER=0 disables.
            from src.polaris_graph.audit_ir.scope_classifier import (
                ScopeClassification, ScopeVerdict,
            )
            verdict_enum_map = {
                "in_scope": ScopeVerdict.IN_SCOPE,
                "out_of_scope": ScopeVerdict.OUT_OF_SCOPE,
                "uncertain": ScopeVerdict.UNCERTAIN,
            }
            try:
                # Codex round-1 HIGH fix (v2): defensive against
                # malformed M-INT-4 dict here too — KeyError on
                # ["verdict"] was the actual abort path Codex
                # found. .get() returns None on missing key, then
                # the verdict_enum_map lookup falls back to UNCERTAIN.
                _v_verdict_str = scope_llm_summary.get("verdict")
                _v_verdict_enum = verdict_enum_map.get(
                    _v_verdict_str, ScopeVerdict.UNCERTAIN,
                )
                _v_conf_raw = scope_llm_summary.get("confidence", 0.0)
                try:
                    _v_conf = float(_v_conf_raw)
                except (TypeError, ValueError):
                    _v_conf = 0.0
                _v_domain = scope_llm_summary.get("domain")
                _v_rationale = scope_llm_summary.get("rationale", "")
                if not isinstance(_v_rationale, str):
                    _v_rationale = str(_v_rationale)
                _classification = ScopeClassification(
                    verdict=_v_verdict_enum,
                    confidence=_v_conf,
                    domain=_v_domain,
                    rationale=_v_rationale,
                )
                domain_route_summary = _route_query_to_domain(
                    _classification,
                    requested_domain=_v_domain,
                )
            except Exception as exc:  # noqa: BLE001
                # Best-effort — telemetry write must not gate the sweep.
                print(f"[M-INT-5] WARN: domain route synthesis failed: {exc}")
                domain_route_summary = None
            if domain_route_summary is not None:
                _log(
                    f"[M-INT-5]     domain_router: "
                    f"outcome={domain_route_summary['outcome']} "
                    f"domain={domain_route_summary['domain']} "
                    f"requested_domain={domain_route_summary.get('requested_domain')} "
                    f"adapters={domain_route_summary['adapter_ids']}"
                )

        # M-INT-6: best-effort auto-induction. Telemetry only —
        # abstain verdicts surface in operator_review_queue.jsonl.
        # PG_USE_AUTO_INDUCTION=0 disables (default 0).
        # Per LAW II — wrap in try/except for defense-in-depth.
        try:
            inductor_summary = _induce_with_llm(
                query=q["question"],
                run_dir=run_dir,
            )
        except Exception as exc:  # noqa: BLE001
            print(f"[M-INT-6] WARN: inductor helper raised: {exc}")
            inductor_summary = None
        if inductor_summary is not None:
            _log(
                f"[M-INT-6]     inductor: "
                f"decision={inductor_summary['decision']} "
                f"confidence={inductor_summary['confidence']:.2f} "
                f"slug={inductor_summary['induced_slug']} "
                f"abstain_reason={inductor_summary['abstain_reason']!r}"
            )

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
            # BUG-SCHEMA-R8d: shared envelope for schema consistency.
            abort_manifest = _base_manifest_envelope(
                run_id=run_id, q=q, retrieval=None, run_cost=run_cost,
            )
            abort_manifest.update({
                "status": "abort_scope_rejected",
                "protocol_sha256": scope.protocol_sha256,
                "scope": {
                    "decision": scope.protocol.scope_decision,
                    "rejected": scope.protocol.scope_rejected,
                    "rejection_code": scope.protocol.scope_rejection_code,
                    "reasons": scope.protocol.scope_reasons,
                },
            })
            abort_manifest = augment_v6_manifest(
                abort_manifest,
                external_run_id=q.get("external_run_id"),
                decision_id=q.get("decision_id"),
                query_slug=q.get("slug"),
            )
            abort_manifest = _attach_tool_utilization(abort_manifest, run_dir)
            (run_dir / "manifest.json").write_text(
                json.dumps(abort_manifest, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            summary["manifest"] = abort_manifest
            summary["cost_usd"] = run_cost
            try: write_per_run_cost_ledger(run_dir, run_id)
            except Exception: pass
            if q.get("v6_mode") and q.get("external_run_id"):
                emit_terminal_event(
                    q.get("external_run_id"),
                    "abort_scope_rejected",
                    error_msg=summary.get("error"),
                )
            set_current_run_id(None)
            set_reasoning_sink(None)
            log_f.close()
            return summary

        # Live retrieval
        # Env-controllable retrieval width for full-scale runs:
        #   PG_SWEEP_MAX_SERPER  (default 12)  — results per query from Serper
        #   PG_SWEEP_MAX_S2      (default 12)  — same from Semantic Scholar
        #   PG_SWEEP_FETCH_CAP   (default 40)  — max URLs to classify & fetch
        #     in TOTAL after dedup (NOT per query — I-meta-002-q1d #943 doc
        #     fix). Bounded by PG_MAX_COST_PER_RUN.
        # I-meta-002-q1d (#943): raised 8/8/20 → 12/12/40 to close the
        # evidence-depth gap vs frontier DR; the fetch-time relevance rerank
        # (#951) keeps the most relevant candidates within the total cap.
        _max_serper = int(os.getenv("PG_SWEEP_MAX_SERPER", "12"))
        _max_s2 = int(os.getenv("PG_SWEEP_MAX_S2", "12"))
        _fetch_cap = int(os.getenv("PG_SWEEP_FETCH_CAP", "40"))

        # I-meta-005 Phase 1 (#985): field-agnostic research planner (shadow
        # build, default OFF). When PG_USE_RESEARCH_PLANNER is on, the planner
        # produces the frame + faceted sub-queries + archetype outline; the
        # plan is SHA-pinned BEFORE retrieval (gap #19 extension) and its
        # sub-queries are the ONLY non-anchor query source — the legacy
        # domain-keyed expanders (M-28/M-35/trial-DOI/hand-authored) are NOT
        # invoked, the domain_backends router is bypassed (domain=None), and
        # R-6 {domain}.yaml completeness expansion is disabled. OFF: every
        # legacy path runs byte-identically.
        _use_research_planner = (
            os.getenv("PG_USE_RESEARCH_PLANNER", "0").strip()
            in ("1", "true", "True")
        )
        _research_plan = None
        _planner_protocol = None
        # I-meta-005 Phase 4 (#988): the generator-bound plan + partial flag.
        # Initialized here (OFF + ON) so the generator call is NameError-safe on
        # every path; the saturation loop reassigns them on-mode when it prunes.
        _gen_plan = None
        _partial_mode = False
        _finding_dedup_telemetry = None   # Phase 5 (#989); set just before generator
        if _use_research_planner:
            from src.polaris_graph.planning.research_planner import (
                plan_research,
                plan_sha256,
                serialize_plan_canonical,
            )
            from src.polaris_graph.llm.openrouter_client import (
                OpenRouterClient,
                PG_GENERATOR_MODEL,
            )

            def _planner_llm(prompt: str) -> str:
                # Production Writer call. Build + smoke NEVER reach this path
                # (the planner callable is injected/faked there). One Writer
                # call (plus at most one bounded retry inside plan_research).
                #
                # `run_one_query` is async — the sweep event loop is already
                # running here — so the coroutine is driven on a SEPARATE
                # thread with its own loop (thread-safe; never touches the
                # running loop, which `run_until_complete` would crash on).
                #
                # I-meta-005 Phase 1 FIX 3 (Codex diff-gate iter-1 P1 #3): the
                # prior bare `ThreadPoolExecutor(...).submit(asyncio.run, ...)`
                # ran with the worker's OWN empty ContextVar state, so the
                # planner Writer call's billed cost accumulated in
                # `_RUN_COST_CTX` only inside the worker snapshot and was LOST
                # to the parent run (`current_run_cost()` / `manifest.cost_usd`
                # under-reported live planner spend — a budget-cap integrity
                # LAW violation). Fix mirrors `auto_induction.llm_inductor`
                # rounds 3-4 (and `scope_classifier_llm._run_async_in_isolated_
                # thread`): capture the parent context with
                # `contextvars.copy_context()` and run the worker inside that
                # snapshot via `parent_ctx.run()` (READ visibility), THEN apply
                # the worker's cost delta back to the parent context via a
                # closure-shared holder (write-back, fires whether or not the
                # call raised — the OpenRouter client bills partial cost before
                # raising on empty-content/retry).
                import asyncio as _asyncio
                import concurrent.futures as _futures
                import contextvars as _contextvars
                from src.polaris_graph.llm.openrouter_client import (
                    _RUN_COST_CTX,
                )

                _parent_cost_before = _RUN_COST_CTX.get()
                _worker_cost_after_holder: list[float] = [_parent_cost_before]

                async def _run() -> str:
                    _client = OpenRouterClient(model=PG_GENERATOR_MODEL)
                    try:
                        _resp = await _client.generate(
                            prompt=prompt, max_tokens=2000, temperature=0.2,
                        )
                        return (_resp.content or "").strip()
                    finally:
                        # Capture the worker snapshot's accumulated cost even
                        # on raise (OpenRouter bills partial cost before
                        # raising on empty-content/retry paths).
                        _worker_cost_after_holder[0] = _RUN_COST_CTX.get()
                        if hasattr(_client, "close"):
                            try:
                                await _client.close()
                            except Exception:
                                pass

                _parent_ctx = _contextvars.copy_context()

                def _worker() -> str:
                    def _run_under_ctx() -> str:
                        return _asyncio.run(_run())
                    return _parent_ctx.run(_run_under_ctx)

                try:
                    with _futures.ThreadPoolExecutor(max_workers=1) as _pool:
                        return _pool.submit(_worker).result()
                finally:
                    # Apply the worker's cost delta to the parent context so
                    # the planner Writer spend merges into the parent run cost
                    # (whether or not the worker raised).
                    _cost_delta = (
                        _worker_cost_after_holder[0] - _parent_cost_before
                    )
                    if _cost_delta > 0:
                        _RUN_COST_CTX.set(_parent_cost_before + _cost_delta)

            _research_plan = plan_research(
                q["question"], planner_llm=_planner_llm,
            )
            # Pre-register + SHA-pin the plan BEFORE retrieval (gap #19).
            _plan_canonical = serialize_plan_canonical(_research_plan)
            _plan_path = run_dir / "research_plan.json"
            _plan_path.write_text(_plan_canonical + "\n", encoding="utf-8")
            _plan_sha = plan_sha256(_research_plan)
            _log(f"[planner]     research_plan pinned sha256={_plan_sha[:12]} "
                 f"sub_queries={len(_research_plan.sub_queries)} "
                 f"outline={len(_research_plan.outline)}")
            # Frame-derived anchor protocol so planner sub-queries validate
            # against the frame's OWN tokens (brief §2.4 validator adapter).
            _planner_protocol = _research_plan.frame.to_anchor_protocol(
                q["question"]
            )

        # I-meta-005 Phase 1 FIX 1 (Codex diff-gate iter-1 P1 #1): ON-mode
        # bypasses ALL domain/template effects — not just query expansion.
        # The whole M-28/M-35 template-load + regulatory/trial expander block
        # is gated on `if not _use_research_planner:`. ON-mode the planner's
        # field-agnostic facets (Phase 2) + saturation (Phase 4) replace the
        # domain-keyed scope template, so `load_scope_template` is NEVER
        # called, no expander is computed, and `_template` stays None. Every
        # downstream `_template` consumer is already None-tolerant — the
        # legacy `except: _template = None` fallback below proves it. OFF: the
        # block runs byte-identically (re-indented verbatim, zero refactor).
        if not _use_research_planner:
            # M-28 Fix #1 (2026-04-20): regulatory-anchor expansion. Loads
            # the scope template for this domain and — if the template has
            # a `regulatory_anchors` list — emits one extra amplified query
            # per anchor of the form `{question} site:{anchor}`. No hard-
            # coded agency list in Python; template-driven so each domain
            # controls its own anchors. Empty/missing list = no-op.
            from src.polaris_graph.nodes.scope_gate import load_scope_template
            from src.polaris_graph.retrieval.regulatory_expander import (
                expand_regulatory_queries,
            )
            from src.polaris_graph.retrieval.primary_trial_expander import (
                expand_primary_trial_queries,
            )
            try:
                _template = load_scope_template(q["domain"])
            except Exception as _ex:
                _log(
                    f"[M-28/M-35 warn] could not load template for domain="
                    f"{q['domain']!r}: {_ex} — continuing without regulatory "
                    f"(M-28) OR primary-trial (M-35) expansion"
                )
                _template = None
            # I-arch-001b: v6 actor synthesizes a per_query_report_contract from
            # the v6 template's frame_manifest and passes it through q. Merge it
            # into the scope template so M-55 compile_frame and
            # load_report_contract_for_slug see the synthesized contract for this
            # query's slug. Non-v6 sweep calls don't set v30_contract_patch -> noop.
            _v30_patch = q.get("v30_contract_patch") if q.get("v6_mode") else None
            if _v30_patch and isinstance(_template, dict):
                _template.setdefault("per_query_report_contract", {}).update(_v30_patch)
            _reg_queries = expand_regulatory_queries(q["question"], _template)
            if _reg_queries:
                _log(f"[M-28]        regulatory_anchors: +{len(_reg_queries)} "
                     f"queries (domain={q['domain']})")
            # M-35 (2026-04-21): primary-trial anchor expansion. Keyed by
            # sweep slug (trial names are query-specific). Missing slug or
            # missing `per_query_primary_trial_anchors` key = no-op.
            _trial_queries = expand_primary_trial_queries(
                q["question"], _template, q["slug"]
            )
            if _trial_queries:
                _log(f"[M-35]        primary_trial_anchors: +{len(_trial_queries)} "
                     f"queries (slug={q['slug']})")
        else:
            # ON-mode: NO load_scope_template, NO expander compute, NO row
            # labeling from template (the planner facets replace them).
            _template = None
            _reg_queries = []
            _trial_queries = []
            _log("[planner]     domain template + M-28/M-35 expanders "
                 "bypassed (field-agnostic planner facets replace them)")
        # I-meta-002-q1d (#951 q1d-a): decompose the multi-clause question into focused
        # sub-queries (pure, no-network) so a 40-70-word golden question is not fired as
        # ~one keyword query. Flag-gated (default ON); falls back to [] for short questions.
        _decomposed: list[str] = []
        if os.getenv("PG_SWEEP_QUERY_DECOMPOSE", "1").strip() in ("1", "true", "True"):
            from src.polaris_graph.retrieval.query_decomposer import (
                decompose_question,
            )
            _decomposed = decompose_question(q["question"])
            if _decomposed:
                _log(f"[q1d]         query_decompose: +{len(_decomposed)} sub-queries "
                     f"(slug={q['slug']})")
        from src.polaris_graph.retrieval.query_decomposer import (
            build_amplified_query_list,
        )
        if _use_research_planner and _research_plan is not None:
            # ON-mode: the planner's faceted sub-queries are the ONLY
            # non-anchor query source. The legacy domain-keyed expanders are
            # NOT invoked (regulatory/trial/hand_authored all empty); the
            # planner's facets ARE the field-agnostic regulatory/primary-
            # evidence expansion (brief §2.4).
            _amplified_effective = build_amplified_query_list(
                hand_authored=[],
                decomposed=list(_research_plan.sub_queries),
                regulatory=[],
                trial=[],
            )
        else:
            _amplified_effective = build_amplified_query_list(
                hand_authored=list(q.get("amplified", [])),
                decomposed=_decomposed,
                regulatory=_reg_queries,
                trial=_trial_queries,
            )

        # I-cap-002 feature 1/4 (#1060): STORM multi-perspective query expansion (default OFF,
        # fallback-safe). When PG_STORM_ENABLED_IN_BENCHMARK=1, call STORM to generate diverse
        # perspective QUESTIONS and append them as additional SEARCH QUERIES. STORM only widens the
        # query fan-out — evidence is still fetched verbatim by live_retriever and verified by
        # strict_verify + the 4-role seam, so NO faithfulness path is touched (STORM never produces
        # direct_quote/evidence rows here). A STORM failure NEVER aborts the run (logged loud, fall
        # through to the non-STORM query list). The module-level PG_STORM_ENABLED is import-cached,
        # so we toggle the MODULE attribute (not the env var) for THIS call only, restored in finally.
        if os.getenv("PG_STORM_ENABLED_IN_BENCHMARK", "0").strip() in ("1", "true", "True"):
            import asyncio as _storm_asyncio
            import contextvars as _storm_cv
            import src.polaris_graph.agents.storm_interviews as _storm_mod
            from src.polaris_graph.llm.openrouter_client import (
                OpenRouterClient as _StormClient,
                PG_GENERATOR_MODEL as _STORM_MODEL,
                _RUN_COST_CTX,
                check_run_budget as _storm_check_budget,
            )
            from src.polaris_graph.retrieval.storm_query_extractor import (
                extract_storm_questions,
            )

            _storm_state = {
                "original_query": q["question"],
                "region": q.get("region", "global"),
                "web_results": [],
                "academic_results": [],
            }
            _storm_out: dict = {}
            # Codex diff-gate iter-2 P1-a: STORM runs its interviews under asyncio.gather, whose child
            # tasks each get their OWN copied context. ContextVars do NOT propagate cost UP from
            # concurrent children, so STORM's _RUN_COST_CTX spend can be captured NEITHER by a parent
            # copy_context read NOR by a post-hoc check_run_budget — it would silently bypass
            # PG_MAX_COST_PER_RUN. Robust fix: book a CONSERVATIVE cost ENVELOPE (scaled by the STORM
            # perspective/round config) into the parent run cost and ENFORCE the cap BEFORE STORM runs.
            # STORM then runs in an ISOLATED context (its real spend is discarded from the parent total —
            # the envelope IS the parent's accounting for STORM). The envelope-inclusive isolated context
            # also makes STORM's OWN internal budget checks stop early if actual spend nears the cap.
            # Conservative by design: over-books, never under-enforces (LAW VI). The per-round estimate
            # is env-tunable.
            _storm_perspectives = int(os.getenv("PG_STORM_PERSPECTIVES_COUNT", "8"))
            _storm_rounds = int(os.getenv("PG_STORM_ROUNDS_PER_PERSPECTIVE", "4"))
            _storm_per_round_usd = float(os.getenv("PG_STORM_PER_ROUND_COST_USD", "0.10"))
            _storm_cost_envelope = max(
                0.0, _storm_perspectives * _storm_rounds * _storm_per_round_usd
            )
            if _storm_cost_envelope > 0:
                _RUN_COST_CTX.set(current_run_cost() + _storm_cost_envelope)
            # Raises BudgetExceededError (-> the sweep's abort_budget_exceeded handler) if the STORM
            # envelope would breach the cap; STORM does NOT run in that case (the raise precedes the try).
            _storm_check_budget(0)
            # Codex diff-gate iter-3 P2: create the client AFTER the budget precheck so a clean
            # envelope-breach abort does not leave an unclosed OpenRouterClient.
            _storm_client = _StormClient(model=_STORM_MODEL)
            _storm_ctx = _storm_cv.copy_context()
            _storm_prev = _storm_mod.PG_STORM_ENABLED
            _storm_mod.PG_STORM_ENABLED = True
            try:
                _storm_out = await _storm_asyncio.create_task(
                    _storm_mod.run_storm_interviews(_storm_client, _storm_state),
                    context=_storm_ctx,
                )
            except Exception as _storm_exc:  # noqa: BLE001 — STORM faults (incl. its own internal
                # BudgetExceededError from the isolated context) never abort the run: the parent budget
                # was already booked + enforced via the envelope above.
                _log(
                    f"[storm]       STORM query expansion failed: {_storm_exc} — "
                    f"proceeding without STORM queries"
                )
            finally:
                _storm_mod.PG_STORM_ENABLED = _storm_prev
                try:
                    await _storm_client.close()
                except Exception:  # noqa: BLE001
                    pass
            _storm_questions = extract_storm_questions(
                _storm_out.get("storm_conversations", []),
                cap=int(os.getenv("PG_STORM_MAX_BENCHMARK_QUERIES", "30")),
            )
            if _storm_questions:
                _seen_lower = {x.lower() for x in _amplified_effective}
                _storm_added = [x for x in _storm_questions if x.lower() not in _seen_lower]
                _amplified_effective = _amplified_effective + _storm_added
                _log(
                    f"[storm]       +{len(_storm_added)} perspective queries from "
                    f"{len(_storm_out.get('storm_conversations', []))} interviews (slug={q['slug']})"
                )

        # I-meta-005 Phase 1 FIX 1 (Codex diff-gate iter-1 P1 #1): ON-mode
        # computes NO template-keyed expander. The #817-L4 DOI-seed expander
        # reads the domain scope template (None on-mode); it is gated on
        # `if not _use_research_planner:` so no expander is computed on-mode
        # (the on-path already passes `_retrieval_seed_urls = []`). OFF: runs
        # byte-identically.
        if not _use_research_planner:
            # I-bug-776 (#817) layer-4 (Codex decision b): direct primary-trial DOI
            # seed candidates. Search-expansion (M-35 above) does not surface the
            # pivotal OA primaries for guideline-dominated questions, so inject the
            # anchored trials' known DOIs as DIRECT candidates. Slug-scoped no-op
            # when `per_query_primary_trial_dois` is absent for the slug.
            from src.polaris_graph.retrieval.primary_trial_expander import (
                expand_primary_trial_dois,
            )
            _trial_doi_seeds = expand_primary_trial_dois(_template, q["slug"])
            if _trial_doi_seeds:
                _log(f"[#817-L4]     primary_trial_doi_seeds: +{len(_trial_doi_seeds)} "
                     f"direct candidates (slug={q['slug']})")
        else:
            _trial_doi_seeds = []

        t0 = time.time()
        # I-meta-005 Phase 1 (#985) + Phase 2 (#986): ON-mode bypasses the
        # legacy domain router (brief §2.4) — `domain=None` skips the
        # domain_backends per-domain `if domain ==` candidate router. Phase 2
        # threads the planner FRAME so the field-agnostic NEED-TYPE registry
        # (keyed on the frame's declared evidence_needs + jurisdictions, NO
        # domain literal) REPLACES the domain backends at the live seam. The
        # frame-derived protocol replaces the clinical PICO protocol so planner
        # sub-queries validate against the frame's own tokens. No trial-DOI
        # seeds on-mode. OFF: the legacy domain + PICO protocol + DOI seeds run
        # byte-identically (research_frame=None -> the legacy `if domain ==`
        # seam is taken).
        _retrieval_domain = None if _use_research_planner else q["domain"]
        _retrieval_protocol = (
            _planner_protocol
            if (_use_research_planner and _planner_protocol is not None)
            else protocol
        )
        _retrieval_seed_urls = [] if _use_research_planner else _trial_doi_seeds
        _retrieval_frame = (
            _research_plan.frame
            if (_use_research_planner and _research_plan is not None)
            else None
        )
        retrieval = run_live_retrieval(
            research_question=q["question"],
            amplified_queries=_amplified_effective,
            protocol=_retrieval_protocol,
            max_serper=_max_serper,
            max_s2=_max_s2,
            fetch_cap=_fetch_cap,
            enable_openalex_enrich=True,
            enable_prefetch_filter=False,
            domain=_retrieval_domain,   # R-6 Gap-2 domain backends (None on-mode)
            seed_urls=_retrieval_seed_urls,   # #817 layer-4 DOI candidates (off-mode only)
            research_frame=_retrieval_frame,  # Phase 2 need-type registry (None off-mode)
        )
        dt = time.time() - t0
        _log(f"[retrieval]   pre_filter={retrieval.total_candidates_pre_filter}, "
             f"fetched={retrieval.candidates_fetched}, "
             f"failed={retrieval.candidates_failed_fetch}, "
             f"elapsed={dt:.1f}s  api_calls={retrieval.api_calls}")

        # I-meta-005 Phase 1 FIX 1 (Codex diff-gate iter-1 P1 #1): ON-mode
        # does NO template-driven row labeling. The M-48 population-scope
        # labeler reads the domain scope template (None on-mode), so it is
        # gated on `if not _use_research_planner:` to be literal about "no
        # row labeling from template." OFF: runs byte-identically.
        if not _use_research_planner:
            # M-48 (2026-04-22): tag evidence rows with per-anchor
            # population-scope labels from the scope template. For a T2D
            # research question, SURMOUNT-2 is direct (T2D+obesity) while
            # SURMOUNT-1/3/4 are indirect_for_t2d (obesity-only). The
            # generator reads these tags to avoid merging obesity-only
            # weight-loss estimates into direct T2D efficacy claims.
            # No-op when the template defines no labels for this slug.
            from src.polaris_graph.retrieval.primary_trial_expander import (
                label_rows_with_population_scope,
            )
            _m48_labeled_count = sum(
                1 for r in retrieval.evidence_rows
                if r.get("population_scope")
            )
            label_rows_with_population_scope(
                retrieval.evidence_rows, _template, q["slug"],
            )
            _m48_labeled_count_after = sum(
                1 for r in retrieval.evidence_rows
                if r.get("population_scope")
            )
            if _m48_labeled_count_after > _m48_labeled_count:
                _log(
                    f"[m48]         population_scope labeled "
                    f"{_m48_labeled_count_after - _m48_labeled_count} row(s)"
                )

        if len(retrieval.classified_sources) == 0:
            # BUG-B-101 fix: previously returned without any manifest,
            # so downstream couldn't tell the run happened at all.
            summary["status"] = "fail_no_sources"
            summary["error"] = "zero sources retrieved"
            run_cost = current_run_cost()
            abort_manifest = _base_manifest_envelope(
                run_id=run_id, q=q, retrieval=retrieval, run_cost=run_cost,
            )
            abort_manifest.update({
                "status": "abort_no_sources",
                "error": "zero sources retrieved",
            })
            abort_manifest = augment_v6_manifest(
                abort_manifest,
                external_run_id=q.get("external_run_id"),
                decision_id=q.get("decision_id"),
                query_slug=q.get("slug"),
            )
            abort_manifest = _attach_tool_utilization(abort_manifest, run_dir)
            (run_dir / "manifest.json").write_text(
                json.dumps(abort_manifest, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            summary["manifest"] = abort_manifest
            summary["cost_usd"] = run_cost
            try: write_per_run_cost_ledger(run_dir, run_id)
            except Exception: pass
            if q.get("v6_mode") and q.get("external_run_id"):
                emit_terminal_event(
                    q.get("external_run_id"),
                    "abort_no_sources",
                    error_msg=summary.get("error"),
                )
            set_current_run_id(None)
            set_reasoning_sink(None)
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

        # I-cd-706: SSE stage event (v6_mode only; emit_event is non-raising
        # so a Redis outage cannot affect pipeline control flow).
        if q.get("v6_mode") and q.get("external_run_id"):
            emit_event(
                q.get("external_run_id"),
                "corpus_adequacy.completed",
                {
                    "pool_size": len(retrieval.evidence_rows),
                    "tier_counts": dict(dist.tier_counts),
                },
            )

        # R-6 Gap-3: completeness check (before synthesis so gaps can
        # trigger expansion).
        # I-meta-005 Phase 1 FIX 1 (Codex diff-gate iter-1 P1 #1): ON-mode
        # NEVER calls `check_completeness` — it loads a `{domain}.yaml`
        # checklist, and feeding its uncovered checklist labels into the
        # generator (the uncovered-label -> generation hand-off below) shapes
        # written artifacts (the Limitations paragraph) with domain-keyed
        # framing. The field-agnostic planner facets (Phase 2) + saturation
        # (Phase 4) replace the domain checklist. ON-mode substitutes a
        # NEUTRAL `CompletenessReport` (total_applicable=0 -> covered_fraction
        # 1.0, uncovered_topic_ids() == [], so the downstream label hand-off
        # yields []). The telemetry write + log below run on the neutral
        # object (honest 0/0). OFF: `check_completeness` runs byte-identically.
        if not _use_research_planner:
            completeness = check_completeness(
                domain=q["domain"],
                research_question=q["question"],
                evidence_rows=retrieval.evidence_rows,
            )
        else:
            completeness = CompletenessReport(domain=q["domain"])
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
        # I-meta-005 Phase 1 (#985): ON-mode disables R-6 {domain}.yaml
        # completeness expansion (brief §2.4) — it is a `{domain}.yaml` router
        # forbidden on the field-agnostic on-path. The completeness CHECK still
        # runs for telemetry, but no domain-keyed expand_queries are fired into
        # retrieval. OFF: R-6 expansion runs byte-identically.
        enable_expansion = (
            os.getenv("PG_R6_ENABLE_EXPANSION", "1") == "1"
            and not _use_research_planner
        )
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

        # I-meta-002-q1d (#942-deepener): Stop-RAG-gated citation-snowball deepening. Default OFF (it
        # SPENDS). Fires only on a BORDERLINE corpus (Codex brief-gate predicate). Every discovered
        # paper URL is fed back through the SAME run_live_retrieval(seed_urls=...) fetch/tier/strict_
        # verify chokepoint — a deepened paper earns its tier only from fetched content; a thin/
        # abstract-only paper is DROPPED fail-closed (no laundering). Fail-open: any error leaves the
        # post-R6 corpus untouched.
        from src.polaris_graph.retrieval.deepener_sweep_adapter import (
            build_deepener_state,
            discovered_urls,
            run_deepener_sync,
            should_trigger_deepener,
        )
        if should_trigger_deepener(
            flag_on=os.getenv("PG_SWEEP_EVIDENCE_DEEPENER", "0").strip() in ("1", "true", "True"),
            has_s2_key=bool(os.getenv("SEMANTIC_SCHOLAR_API_KEY", "").strip()),
            has_seed_evidence=len(retrieval.evidence_rows) > 0,
            adequacy_decision=adequacy.decision,
            total_uncovered=completeness.total_uncovered,
        ):
            try:
                _deep_state = build_deepener_state(retrieval.evidence_rows, q["question"])
                _deep_out = run_deepener_sync(_deep_state)
                _url_cap = max(0, int(os.getenv("PG_SWEEP_DEEPENER_URL_CAP", "20")))
                _deep_urls = discovered_urls(_deep_out, cap=_url_cap)
                _log(f"[deepener]    discovered "
                     f"{len((_deep_out or {}).get('deepened_papers', []))} papers; seeding "
                     f"{len(_deep_urls)} urls (cap={_url_cap}); "
                     f"stats={(_deep_out or {}).get('deepener_stats', {})}")
                if _deep_urls:
                    deep_retrieval = run_live_retrieval(
                        research_question=q["question"],
                        amplified_queries=[],
                        protocol=protocol,
                        fetch_cap=min(len(_deep_urls), _url_cap),
                        enable_openalex_enrich=True,
                        enable_prefetch_filter=False,
                        seed_urls=_deep_urls,
                        seed_only=True,     # ONLY the deepener URLs — no Serper/S2/domain fan-out
                    )
                    # ATOMIC merge (Codex diff-gate iter-1 P1): stage everything in LOCAL copies,
                    # recompute dist/completeness/adequacy over the staged corpus, and COMMIT all
                    # assignments only after every recompute succeeds — so a recompute error leaves the
                    # post-R6 corpus untouched (the outer except is fail-open). Dedup by URL with the
                    # seen-set updated as sources are accepted; only deep evidence rows whose source URL
                    # was an ACCEPTED non-duplicate source are appended (no evidence_row_count inflation).
                    _staged_sources = list(retrieval.classified_sources)
                    _seen_urls = {s.url for s in _staged_sources}
                    _accepted_src_urls: set[str] = set()
                    for src in deep_retrieval.classified_sources:
                        if src.url and src.url not in _seen_urls:
                            _seen_urls.add(src.url)
                            _staged_sources.append(src)
                            _accepted_src_urls.add(src.url)
                    _staged_rows = list(retrieval.evidence_rows)
                    _base = len(_staged_rows)
                    _accepted = 0
                    for ev in deep_retrieval.evidence_rows:
                        _ev_url = (ev.get("source_url") or ev.get("url") or "").strip()
                        if not _ev_url or _ev_url not in _accepted_src_urls:
                            continue  # duplicate / not an accepted source — skip (no inflation)
                        ev["evidence_id"] = f"ev_{_base + _accepted:03d}"
                        _staged_rows.append(ev)
                        _accepted += 1
                    _staged_dist = compute_tier_distribution(_staged_sources, protocol)
                    # I-meta-005 Phase 1 FIX 1 (Codex diff-gate iter-1 P1 #1):
                    # the deepener staged re-check ALSO loads the domain
                    # `{domain}.yaml` checklist via `check_completeness`, then
                    # reassigns `completeness = _staged_completeness` below.
                    # On-mode that would OVERWRITE the neutral report with a
                    # domain-keyed one and re-introduce the banned checklist
                    # label -> generation leak (the deepener can fire on-mode on
                    # a BORDERLINE adequacy decision even with
                    # total_uncovered==0, since adequacy is not gated on-mode).
                    # Gate the re-check: on-mode keep the neutral report (the
                    # merge stays atomic). OFF: re-check runs byte-identically.
                    if not _use_research_planner:
                        _staged_completeness = check_completeness(
                            domain=q["domain"],
                            research_question=q["question"],
                            evidence_rows=_staged_rows,
                        )
                    else:
                        _staged_completeness = completeness
                    _staged_adequacy = assess_corpus_adequacy(
                        tier_counts=_staged_dist.tier_counts,
                        evidence_row_count=len(_staged_rows),
                        domain=q["domain"],
                        protocol=protocol,
                    )
                    # Commit atomically (all recomputes succeeded).
                    retrieval.classified_sources = _staged_sources
                    retrieval.evidence_rows = _staged_rows
                    dist = _staged_dist
                    completeness = _staged_completeness
                    adequacy = _staged_adequacy
                    _log(f"[deepener]    merged +{_accepted} evidence rows (post-chokepoint); "
                         f"adequacy={adequacy.decision} uncovered={completeness.total_uncovered}")
            except Exception as exc:
                _log(f"[deepener]    FAILED (fail-open): {exc}")

        # I-cap-002 feature 3/4 (#1060): agentic search as URL-DISCOVERY. Default OFF (it SPENDS +
        # makes network calls). The agentic loop DISCOVERS additional high-quality URLs; those URLs are
        # fetched VERBATIM through the SAME run_live_retrieval(seed_urls=…, seed_only=True) chokepoint
        # the deepener uses, so each discovered source earns its tier only from fetched content and is
        # strict_verify'd + 4-role-checked identically. The agentic notebook/summaries are NEVER read
        # (faithfulness: no model paraphrase can become a direct_quote). Budget: content reading is
        # forced OFF (the only un-enveloped LLM term) and a CONSERVATIVE envelope (rounds × per-round)
        # is booked + the cap ENFORCED BEFORE the loop (STORM pattern); the loop runs in an ISOLATED
        # context so its real spend is discarded (the envelope IS the parent's accounting). Fail-open:
        # any agentic/fetch/merge error leaves the post-deepener corpus untouched.
        if os.environ.get("PG_AGENTIC_SEARCH_IN_BENCHMARK", "0").strip() in (
            "1", "true", "True",
        ):
            import asyncio as _ag_asyncio
            import contextvars as _ag_cv
            import src.polaris_graph.agents.searcher as _ag_mod
            from src.polaris_graph.llm.openrouter_client import (
                OpenRouterClient as _AgClient,
                PG_GENERATOR_MODEL as _AG_MODEL,
                _RUN_COST_CTX,
                check_run_budget as _ag_check_budget,
            )
            from src.polaris_graph.retrieval.agentic_url_harvester import (
                harvest_agentic_urls,
                merge_seed_url_evidence,
            )

            # Conservative cost envelope: with content reading OFF the only LLM work is the per-round
            # analysis (<= PG_AGENTIC_MAX_ROUNDS calls). Book it + enforce the cap BEFORE the loop.
            _ag_max_rounds = int(os.getenv("PG_AGENTIC_MAX_ROUNDS", "12"))
            _ag_per_round_usd = float(os.getenv("PG_AGENTIC_PER_ROUND_COST_USD", "0.10"))
            _ag_cost_envelope = max(0.0, _ag_max_rounds * _ag_per_round_usd)
            if _ag_cost_envelope > 0:
                _RUN_COST_CTX.set(current_run_cost() + _ag_cost_envelope)
            # Raises BudgetExceededError (-> the sweep's abort_budget_exceeded handler) if the agentic
            # envelope would breach the cap. This precedes the try, so it PROPAGATES (matches STORM) —
            # the fail-open except below must NEVER swallow a budget abort.
            _ag_check_budget(0)
            _ag_url_cap = max(0, int(os.getenv("PG_AGENTIC_BENCHMARK_URL_CAP", "100")))
            _ag_urls: list[str] = []
            # Create the client AFTER the budget precheck so a clean envelope-breach abort does not
            # leave an unclosed client.
            _ag_client = _AgClient(model=_AG_MODEL)
            _ag_ctx = _ag_cv.copy_context()
            _ag_prev_reading = _ag_mod.PG_AGENTIC_CONTENT_READING_ENABLED
            _ag_prev_enabled = _ag_mod.PG_AGENTIC_SEARCH_ENABLED
            # Force content reading OFF (we discard the notebook anyway; this removes the only
            # un-enveloped LLM term so the budget envelope is airtight). Toggle the import-cached module
            # constants for the call; restore BOTH in finally.
            _ag_mod.PG_AGENTIC_CONTENT_READING_ENABLED = False
            _ag_mod.PG_AGENTIC_SEARCH_ENABLED = True
            try:
                _ag_state = {
                    "original_query": q["question"],
                    "region": q.get("region", "global"),
                    "sub_queries": list(_amplified_effective),
                    "web_results": [],
                    "academic_results": [],
                }
                _ag_result = await _ag_asyncio.create_task(
                    _ag_mod.execute_agentic_search(_ag_state, _ag_client),
                    context=_ag_ctx,
                )
                # Harvest URLs ONLY, then DISCARD the full result immediately so no notebook/summary
                # field is in scope near the merge below (faithfulness defense-in-depth).
                _ag_urls = harvest_agentic_urls(_ag_result, cap=_ag_url_cap)
                del _ag_result
                _log(f"[agentic]     discovered {len(_ag_urls)} urls (cap={_ag_url_cap})")
            except Exception as _ag_exc:  # noqa: BLE001 — agentic discovery faults never abort the run
                _log(
                    f"[agentic]     agentic discovery failed: {_ag_exc} — "
                    f"proceeding without agentic URLs"
                )
                _ag_urls = []
            finally:
                _ag_mod.PG_AGENTIC_CONTENT_READING_ENABLED = _ag_prev_reading
                _ag_mod.PG_AGENTIC_SEARCH_ENABLED = _ag_prev_enabled
                try:
                    await _ag_client.close()
                except Exception:  # noqa: BLE001
                    pass

            if _ag_urls:
                try:
                    agentic_retrieval = run_live_retrieval(
                        research_question=q["question"],
                        amplified_queries=[],
                        protocol=protocol,
                        fetch_cap=min(len(_ag_urls), _ag_url_cap),
                        enable_openalex_enrich=True,
                        enable_prefetch_filter=False,
                        seed_urls=_ag_urls,
                        seed_only=True,   # ONLY the agentic URLs — no Serper/S2/domain fan-out
                    )
                    # ATOMIC merge via the pure helper (dedup by URL + global ev_### renumber), then
                    # recompute dist/completeness/adequacy over the staged corpus and COMMIT only after
                    # every recompute succeeds — mirrors the deepener so a recompute error leaves the
                    # post-deepener corpus untouched (the outer except is fail-open).
                    _ag_sources, _ag_rows, _ag_acc_src, _ag_acc_rows = merge_seed_url_evidence(
                        retrieval.classified_sources,
                        retrieval.evidence_rows,
                        agentic_retrieval.classified_sources,
                        agentic_retrieval.evidence_rows,
                    )
                    _ag_dist = compute_tier_distribution(_ag_sources, protocol)
                    if not _use_research_planner:
                        _ag_completeness = check_completeness(
                            domain=q["domain"],
                            research_question=q["question"],
                            evidence_rows=_ag_rows,
                        )
                    else:
                        _ag_completeness = completeness
                    _ag_adequacy = assess_corpus_adequacy(
                        tier_counts=_ag_dist.tier_counts,
                        evidence_row_count=len(_ag_rows),
                        domain=q["domain"],
                        protocol=protocol,
                    )
                    retrieval.classified_sources = _ag_sources
                    retrieval.evidence_rows = _ag_rows
                    dist = _ag_dist
                    completeness = _ag_completeness
                    adequacy = _ag_adequacy
                    _log(f"[agentic]     merged +{_ag_acc_rows} evidence rows from "
                         f"+{_ag_acc_src} sources (post-chokepoint); adequacy={adequacy.decision} "
                         f"uncovered={completeness.total_uncovered}")
                except Exception as _ag_merge_exc:  # noqa: BLE001 — fail-open
                    _log(f"[agentic]     merge FAILED (fail-open): {_ag_merge_exc}")

        # I-meta-002-q1d (#945): all retrieval (base + R-6 + deepener) is complete here — flush the
        # retrieval_trace.jsonl now so EVERY exit path below (abort_corpus_inadequate, approval-denied,
        # and the success path) ships the full per-call search/fetch trace for line-by-line audit.
        _flush_retrieval_trace()
        # R-6 Gap-1: if adequacy still says ABORT after optional
        # expansion, refuse to synthesize — emit a short "corpus
        # inadequate" manifest and return status=abort_corpus_inadequate.
        # I-meta-005 Phase 3 (#987): ON-mode this legacy domain-keyed adequacy
        # is TELEMETRY-ONLY — it must NOT abort here, or an on-mode thin corpus
        # would exit via the aggregate-count gate BEFORE the binding plan-
        # sufficiency gate (the single final gate on `evidence_for_gen`) ever
        # runs. OFF-mode this aborts byte-identically (the off-mode gate as today).
        if not _use_research_planner and adequacy.decision == "abort":
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
            # BUG-SCHEMA-R8d: use shared envelope so every exit path
            # has the same field shape.
            manifest = _base_manifest_envelope(
                run_id=run_id, q=q, retrieval=retrieval, run_cost=run_cost,
            )
            manifest.update({
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
            })
            manifest = augment_v6_manifest(
                manifest,
                external_run_id=q.get("external_run_id"),
                decision_id=q.get("decision_id"),
                query_slug=q.get("slug"),
            )
            manifest = _attach_tool_utilization(manifest, run_dir)
            (run_dir / "manifest.json").write_text(
                json.dumps(manifest, indent=2, sort_keys=True, default=str) + "\n",
                encoding="utf-8",
            )
            summary["manifest"] = manifest
            summary["cost_usd"] = run_cost
            try: write_per_run_cost_ledger(run_dir, run_id)
            except Exception: pass
            if q.get("v6_mode") and q.get("external_run_id"):
                emit_terminal_event(
                    q.get("external_run_id"),
                    "abort_corpus_inadequate",
                    error_msg=summary.get("error"),
                )
            set_current_run_id(None)
            set_reasoning_sink(None)
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
            manifest = _base_manifest_envelope(
                run_id=run_id, q=q, retrieval=retrieval, run_cost=run_cost,
            )
            manifest.update({
                "status": "abort_corpus_approval_denied",
                "approval_error": approval_error,
                "adequacy": asdict(adequacy),
                "corpus": {
                    "count": dist.total_sources,
                    "tier_fractions": dist.tier_fractions,
                    "material_deviation": dist.has_material_deviation,
                    "approved": False,
                },
            })
            manifest = augment_v6_manifest(
                manifest,
                external_run_id=q.get("external_run_id"),
                decision_id=q.get("decision_id"),
                query_slug=q.get("slug"),
            )
            manifest = _attach_tool_utilization(manifest, run_dir)
            (run_dir / "manifest.json").write_text(
                json.dumps(manifest, indent=2, sort_keys=True, default=str) + "\n",
                encoding="utf-8",
            )
            summary["manifest"] = manifest
            summary["cost_usd"] = run_cost
            try: write_per_run_cost_ledger(run_dir, run_id)
            except Exception: pass
            if q.get("v6_mode") and q.get("external_run_id"):
                emit_terminal_event(
                    q.get("external_run_id"),
                    "abort_corpus_approval_denied",
                    error_msg=summary.get("error"),
                )
            set_current_run_id(None)
            set_reasoning_sink(None)
            log_f.close()
            return summary

        # Contradiction detection (now on the possibly-expanded evidence set)
        # BUG-M-202 fix: pass domain so per-domain predicates are checked
        # first (AF anticoagulation, tech benchmarks, policy rates, DD
        # financial metrics). Default union-fallback preserves original
        # obesity/GLP-1 coverage.
        numeric_claims = extract_numeric_claims(
            retrieval.evidence_rows, domain=q["domain"],
        )
        contradictions = detect_contradictions(numeric_claims)
        # Qualitative present-vs-absent clinical-safety conflict detection (I-meta-002-q1d #944).
        # Default ON (no-spend, additive, rule-cue only); kill-switch PG_SWEEP_QUALITATIVE_CONFLICT.
        # Merged into the SAME contradictions.json list (a `type:"qualitative"` discriminator +
        # `severity:"review"` distinguish them; downstream renderers branch on those). Fail-open: a
        # detector error never aborts the sweep.
        qualitative_records = []
        try:
            # ALL detector imports inside the fail-open try (Codex diff-gate iter-1 P2.1): a module
            # import failure must log + skip, never abort the sweep.
            from src.polaris_graph.retrieval.qualitative_conflict_detector import (
                detect_qualitative_conflicts,
                extract_qualitative_assertions,
                qualitative_conflict_enabled,
            )
            if qualitative_conflict_enabled():
                qualitative_records = detect_qualitative_conflicts(
                    extract_qualitative_assertions(
                        retrieval.evidence_rows, domain=q["domain"],
                    )
                )
        except Exception as exc:  # noqa: BLE001 — fail-open, log loudly, never abort the sweep
            _log(f"[qual-conflict] detector error (skipped, fail-open): {exc}")
            qualitative_records = []
        (run_dir / "contradictions.json").write_text(
            json.dumps(
                [asdict(c) for c in contradictions]
                + [asdict(qr) for qr in qualitative_records],
                indent=2, sort_keys=True, default=str,
            ) + "\n",
            encoding="utf-8",
        )
        _qual_hard = sum(1 for qr in qualitative_records if qr.severity in ("high", "medium"))
        _qual_review = sum(1 for qr in qualitative_records if qr.severity == "review")
        _log(f"[contradict]  numeric_claims={len(numeric_claims)}  "
             f"numeric_contradictions={len(contradictions)}  "
             f"qualitative_conflicts={_qual_hard}  qualitative_review_flags={_qual_review}")

        # Multi-section generation with Limitations (R-1)
        # BUG-M-201 fix (deep-dive R6): tier-balanced + relevance-ranked
        # selection instead of raw-order truncation. Previously the
        # generator saw evidence_rows[:20] in retrieval order, diverging
        # from what the gates certified.
        from src.polaris_graph.retrieval.evidence_selector import (
            select_evidence_for_generation,
        )
        max_ev = int(os.getenv("PG_LIVE_MAX_EV_TO_GEN", "20"))
        # I-meta-005 Phase 5 (#989): finding-dedup + relevance-floor corpus
        # (PG_USE_FINDING_DEDUP, default OFF). ON-mode replaces the max_ev cap with
        # a relevance floor (keep every row >= floor, no cap) and dedups by finding
        # before the generator. PG_RELEVANCE_FLOOR default 0.30, range (0.0, 1.0];
        # invalid/out-of-range fails LOUD (never silently send an unbounded pool).
        _use_finding_dedup = (
            os.getenv("PG_USE_FINDING_DEDUP", "0").strip()
            in ("1", "true", "True")
        )
        _relevance_floor: float | None = None
        if _use_finding_dedup:
            from src.polaris_graph.retrieval.evidence_selector import (
                parse_relevance_floor,
            )
            _relevance_floor = parse_relevance_floor(
                os.getenv("PG_RELEVANCE_FLOOR")
            )
        # M-42e (2026-04-22): pass primary_trial_anchors to the
        # selector so it can reserve T1 slots for named-trial
        # primary papers. Anchors come from the loaded scope
        # template's `per_query_primary_trial_anchors` map keyed by
        # sweep slug. Empty list when no anchors (no change vs V25).
        from src.polaris_graph.retrieval.primary_trial_expander import (
            get_primary_trial_anchors_for_slug,
            get_trial_population_scope_for_slug,
        )
        _primary_anchors = get_primary_trial_anchors_for_slug(
            _template, q["slug"]
        )

        # M-50 (2026-04-22): derive the T2D-direct anchor set from the
        # template's population_scope labels. Anchors labeled "direct"
        # qualify for per-trial subsections. SURMOUNT-1/3/4 (indirect
        # for T2D) excluded so weight-loss-only trials don't generate
        # T2D-misleading subsections.
        def _m50_direct_anchors_for_sweep(tmpl, slug):
            scope = get_trial_population_scope_for_slug(tmpl, slug)
            direct = [a for a, lab in scope.items() if lab == "direct"]
            if not direct and _primary_anchors:
                # When template has no scope labels, fall back to all
                # configured anchors (backwards-compatible with slugs
                # that haven't defined population_scope yet).
                direct = list(_primary_anchors)
            return direct

        def _compute_m50_skip_anchors(
            contract_plans: list[Any],
            primary_anchors: list[str],
        ) -> set[str]:
            """Codex M-63 REJECT Medium 2: map contract entity ids
            to M-50 trial anchor names via a normalized substring
            match so the sweep can tell M-50 which anchors are
            already owned by a contract slot.

            Normalization: strip `_`/`-`, lowercase. Match anchor
            against each entity_id; a normalized-anchor substring
            hit inside a normalized-entity-id is strong evidence
            the contract slot renders that trial (e.g.
            `surpass_2_primary` contains `surpass2` → SURPASS-2).

            Conservative: returns empty set if no contract plans
            present, or if no match found. False negatives cost
            one duplicate subsection (reader confusion, not
            pipeline failure); false positives would SUPPRESS a
            legitimate per-trial section, which is worse.
            """
            if not contract_plans or not primary_anchors:
                return set()
            skip: set[str] = set()
            for plan in contract_plans:
                slots = getattr(plan, "slots", ())
                for slot in slots:
                    for eid in getattr(slot, "entity_ids", ()):
                        norm_eid = (
                            eid.lower().replace("_", "").replace("-", "")
                        )
                        for anchor in primary_anchors:
                            norm_anchor = (
                                anchor.lower()
                                .replace("_", "").replace("-", "")
                            )
                            if norm_anchor and norm_anchor in norm_eid:
                                skip.add(anchor)
                                break
            return skip
        evidence_selection = select_evidence_for_generation(
            research_question=q["question"],
            protocol=protocol,
            classified_sources=retrieval.classified_sources,
            evidence_rows=retrieval.evidence_rows,
            max_rows=max_ev,
            primary_trial_anchors=_primary_anchors,
            relevance_floor=_relevance_floor,   # Phase 5: None OFF -> 20-cap path
        )
        evidence_for_gen = evidence_selection.selected_rows
        # I-meta-005 Phase 4 (#988): snapshot the PRE-INJECTION selection baseline.
        # Every non-selection injection below (V30 contract rows :2811, upload rows
        # :2841) is a PREPEND, so this snapshot stays the contiguous SUFFIX of
        # evidence_for_gen and `everything ahead of it` == the exact injected
        # prepend a gap round must re-apply (Codex diff-gate P1).
        _selection_base_rows = list(evidence_for_gen)
        _log(f"[select]      strategy={evidence_selection.selection_strategy} "
             f"selected={len(evidence_for_gen)} of {len(retrieval.evidence_rows)} "
             f"dropped={evidence_selection.dropped_count}")
        _log(f"              full_tiers={evidence_selection.full_counts} "
             f"selected_tiers={evidence_selection.selected_counts}")
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

        # V30 Phase-2 M-63: when PG_V30_PHASE2_ENABLED=1, compile
        # the contract + fetch frame rows BEFORE the generator so
        # `generate_multi_section_report` can dispatch contract
        # sections through the M-58 slot-bound runner. Phase-1
        # coverage logic already ran post-generation; Phase-2
        # layers the contract INTO the generator call.
        _phase2_contract_plans: list[Any] = []
        _phase2_contract_payloads: list[Any] = []  # threaded OUT later
        if os.environ.get("PG_V30_PHASE2_ENABLED", "0").strip() in (
            "1", "true", "True",
        ):
            try:
                from src.polaris_graph.nodes.frame_compiler import (
                    compile_frame,
                )
                from src.polaris_graph.retrieval.frame_fetcher import (
                    fetch_compiled_frame,
                )
                from src.polaris_graph.nodes.contract_outline import (
                    compose_outline_from_contract,
                )
                from src.polaris_graph.generator.contract_section_runner import (
                    ContractSectionPlanExt,
                    register_frame_rows_into_evidence_pool,
                )
                _cf = compile_frame(q["question"], _template, q["slug"])
                if _cf is not None:
                    _log(
                        f"[V30-P2]      compiled contract: "
                        f"entities={len(_cf.evidence_bindings)}"
                    )
                    _frame_rows = fetch_compiled_frame(_cf.evidence_bindings)
                    _log(
                        f"[V30-P2]      fetched {len(_frame_rows)} "
                        f"frame rows"
                    )
                    _outline_v30 = compose_outline_from_contract(
                        _cf, _frame_rows,
                    )
                    # Register FrameRows into the legacy evidence
                    # pool keyed by entity_id so the citation-rewrite
                    # regex (M-63 Fix #3) can resolve
                    # `[surpass_2_primary]` markers in M-58 prose.
                    _entity_metadata = _cf.contract.entities_by_id()
                    _frame_rows_by_eid = {
                        r.entity_id: r for r in _frame_rows
                    }
                    # Build evidence_pool-compatible rows: the
                    # sweep passes `evidence_rows` into the
                    # generator as a LIST and the generator
                    # constructs the dict internally. We inject
                    # the contract rows into that list so the
                    # generator's evidence_pool construction
                    # picks them up.
                    # M-69 Fix #2 (Codex run-9 audit): when r.title
                    # is empty (regulatory entities without CrossRef
                    # title), prefer the contract entity's
                    # label_name + jurisdiction over the bare
                    # entity_id. Pre-fix bibliography rendered
                    # ugly entries like
                    #   [10] fda_mounjaro_label — https://...
                    # Now reads as
                    #   [10] FDA Mounjaro Label — https://...
                    _contract_evidence_rows: list[dict[str, Any]] = []
                    for r in _frame_rows:
                        _ce = _entity_metadata.get(r.entity_id)
                        _label_name = (
                            getattr(_ce, "label_name", None)
                            if _ce is not None else None
                        )
                        _jurisdiction = (
                            getattr(_ce, "jurisdiction", None)
                            if _ce is not None else None
                        )
                        if r.title:
                            _statement = r.title
                        elif _label_name and _jurisdiction:
                            _statement = (
                                f"{_jurisdiction} {_label_name} Label"
                                if "label" not in _label_name.lower()
                                else f"{_jurisdiction} {_label_name}"
                            )
                        elif _label_name:
                            _statement = _label_name
                        else:
                            _statement = r.entity_id
                        _contract_evidence_rows.append({
                            "evidence_id": r.entity_id,
                            "statement": _statement,
                            "direct_quote": r.direct_quote or "",
                            "source_url": r.oa_pdf_url or r.url or "",
                            "title": r.title or "",
                            "authors": list(r.authors),
                            "journal": r.journal or "",
                            "year": r.year,
                            "doi": r.doi or "",
                            "pmid": r.pmid or "",
                            "tier": "T1",  # contract primaries are
                                          # tier-1 by assumption
                            "v30_frame_row": True,
                            "v30_entity_id": r.entity_id,
                            # I-run11-010 (#1056, S2): propagate the provenance class so downstream
                            # consumers can tell a METADATA_ONLY frame row (empty/near-empty
                            # direct_quote, citable only as a gap) from a real ABSTRACT_ONLY/OA row,
                            # instead of relying on strict_verify alone to drop an empty T1 span.
                            "provenance_class": (
                                r.provenance_class.value
                                if getattr(r, "provenance_class", None) is not None
                                else None
                            ),
                        })
                    # Build one ContractSectionPlanExt per section.
                    # Codex M-63 Medium 1 fix: ev_ids is the UNION of
                    # every slot's entity_ids (first-appearance order),
                    # not just the first slot's. Downstream M-50 skip
                    # logic + any pre-dispatch `plan.ev_ids` consumer
                    # needs the full set to avoid referencing missing
                    # primaries.
                    for _section in _outline_v30.sections:
                        _section_ev_ids: list[str] = []
                        _seen: set[str] = set()
                        for _sl in _section.slots:
                            for _eid in _sl.entity_ids:
                                if _eid not in _seen:
                                    _seen.add(_eid)
                                    _section_ev_ids.append(_eid)
                        _phase2_contract_plans.append(
                            ContractSectionPlanExt(
                                title=_section.section,
                                focus=_section.focus,
                                ev_ids=_section_ev_ids,
                                slots=_section.slots,
                                frame_rows_by_entity=_frame_rows_by_eid,
                                contract_entities_by_id=_entity_metadata,
                                research_question=q["question"],
                            )
                        )
                    # Prepend the contract rows onto the existing
                    # evidence list so the generator's evidence_pool
                    # includes them keyed by entity_id.
                    evidence_for_gen = (
                        _contract_evidence_rows + list(evidence_for_gen)
                    )
                    _log(
                        f"[V30-P2]      prepared {len(_phase2_contract_plans)} "
                        f"contract sections + {len(_contract_evidence_rows)} "
                        f"contract evidence rows"
                    )
                else:
                    _log(
                        f"[V30-P2]      no contract for slug="
                        f"{q['slug']!r}; running legacy generator only"
                    )
            except Exception as _p2_exc:
                _log(
                    f"[V30-P2]      ERROR: {type(_p2_exc).__name__}: "
                    f"{_p2_exc} — falling back to legacy generator"
                )

        # I-rdy-010 (#506): inject sovereignty-cleared uploaded-document
        # evidence. Prepended onto evidence_for_gen (mirroring the V30-P2
        # contract-row prepend above) so it flows into the generator AND
        # ev_pool -> evidence_pool.json -> the report bibliography.
        _upload_docs = q.get("uploaded_documents") or []
        if _upload_docs:
            from polaris_v6.adapters.upload_evidence import (
                build_upload_evidence_rows,
            )
            _upload_rows = build_upload_evidence_rows(_upload_docs)
            if _upload_rows:
                evidence_for_gen = _upload_rows + list(evidence_for_gen)
            _log(
                f"[upload]      injected {len(_upload_rows)} evidence row(s) "
                f"from {len(_upload_docs)} uploaded document(s)"
            )
        summary["uploaded_documents_used"] = len(_upload_docs)
        summary["uploaded_documents_blocked"] = int(
            q.get("uploaded_documents_blocked_count", 0) or 0
        )

        # I-meta-005 Phase 4 (#988) — Codex diff-gate P1: the EXACT non-selection
        # injected prepend (upload rows OUTERMOST, then V30 contract rows), in the
        # SAME order applied to round 0 above, is everything ahead of the captured
        # selection baseline. Gap rounds re-inject THIS identical block before
        # re-gating AND the generator, so an expansion round never drops the V30
        # contract evidence and the gate/generator stay in lockstep with round 0
        # on the billed set. Derived by suffix-diff (robust to which of the V30 /
        # upload branches actually ran) rather than re-referencing branch-local
        # vars that may be undefined.
        _gate_injected_prepend_rows = list(
            evidence_for_gen[: len(evidence_for_gen) - len(_selection_base_rows)]
        )

        # I-meta-005 Phase 3 (#987): THE SINGLE BINDING MONEY GATE (on-mode).
        # `evidence_for_gen` is now FULLY constructed — selection (:2568) +
        # the V30 contract-row prepend (:2719) + the upload-row prepend (:2754)
        # have all run and NOTHING further mutates it before the generator bills
        # at `generate_multi_section_report` below. The plan-sufficiency gate
        # certifies EXACTLY the rows that will be billed: does the corpus cover
        # EVERY planned sub-question to its per-section evidence_target at the
        # numeric authority floor? PROCEED -> generator; EXPAND/ABORT collapse to
        # `abort_corpus_inadequate` with ZERO generator tokens (Phase 4 owns the
        # actual saturation EXPANSION loop). Pure / no-network / spend-free. OFF-
        # mode this whole block is skipped (the legacy domain-keyed gate aborted
        # earlier, byte-identically).
        if _use_research_planner and _research_plan is not None:
            from src.polaris_graph.adequacy.plan_sufficiency_gate import (
                assess_plan_sufficiency,
            )
            _suff_floor_env = os.getenv(
                "PG_PLAN_SUFFICIENCY_AUTHORITY_FLOOR", ""
            ).strip()
            _suff_floor = float(_suff_floor_env) if _suff_floor_env else None
            # I-meta-005 Phase 4 (#988): PG_SATURATION_MAX_ROUNDS aliases the
            # Phase-3 gate's `max_rounds` (default 3) so round 0 returns EXPAND
            # (not ABORT) when sections are under-covered, letting the saturation
            # loop fire gap-targeted rounds. PG_PLAN_SUFFICIENCY_MAX_ROUNDS is
            # honored as a legacy override (still 0 if explicitly set).
            _sat_max_rounds = int(
                os.getenv(
                    "PG_PLAN_SUFFICIENCY_MAX_ROUNDS",
                    os.getenv("PG_SATURATION_MAX_ROUNDS", "3"),
                )
            )
            _suff_round = int(os.getenv("PG_PLAN_SUFFICIENCY_ROUND_INDEX", "0"))
            _suff_max_rounds = _sat_max_rounds
            _suff = assess_plan_sufficiency(
                plan=_research_plan,
                corpus_rows=evidence_for_gen,
                authority_floor=_suff_floor,
                round_index=_suff_round,
                max_rounds=_suff_max_rounds,
            )
            (run_dir / "plan_sufficiency.json").write_text(
                json.dumps(asdict(_suff), indent=2, sort_keys=True, default=str)
                + "\n",
                encoding="utf-8",
            )
            _log(
                f"[sufficiency] verdict={_suff.verdict} "
                f"floor={_suff.authority_floor} "
                f"sections={len(_suff.per_unit)} "
                f"under_covered={len(_suff.under_covered_units)}"
            )
            # I-meta-005 Phase 4 (#988): the SATURATION LOOP. Default-OFF body
            # (this whole on-mode block only runs when PG_USE_RESEARCH_PLANNER is
            # set). The loop DECISION logic is the PURE `run_saturation_loop` over
            # an injected gap-retrieval closure; it constructs NO HTTP client and
            # bills NO generator token. Round 0 already ran above; rounds >=1 fire
            # GAP-ONLY retrieval (anchor-suppressed), merge with global evidence_id
            # renumber, re-select, re-inject upload rows, and re-gate.
            _gen_plan = _research_plan          # full plan on PROCEED.
            _partial_mode = False
            _dropped_sections: list[str] = []
            if _suff.verdict != "proceed":
                from src.polaris_graph.retrieval.saturation import (
                    RoundOutcome,
                    canonical_source_url,
                    per_query_discovery_cost,
                    run_saturation_loop,
                    STOP_SUFFICIENT,
                )
                from src.polaris_graph.discovery.need_type_router import (
                    route_needs_to_adapters,
                )
                _sat_eps = float(os.getenv("PG_SATURATION_NOVELTY_EPS", "0.10"))
                _sat_max_calls = int(
                    os.getenv("PG_SATURATION_MAX_RETRIEVAL_CALLS", "120")
                )
                # Worst-case per-gap-query DISCOVERY cost: core Serper + core S2
                # (2) PLUS one call per routed need-type adapter (the dispatcher
                # loops PER query). adapter_count from the routed registry.
                try:
                    _adapter_count = len(
                        route_needs_to_adapters(_research_plan.frame)
                    )
                except Exception:
                    _adapter_count = 0
                _cost_per_query = per_query_discovery_cost(_adapter_count)

                def _run_gap_round(gap_queries: list[str]) -> RoundOutcome:
                    """On-mode gap-retrieval closure. Fires ONLY the gap
                    sub-queries (anchor-suppressed BOTH seams), merges with
                    global evidence_id renumber, re-selects, re-injects upload
                    rows, and re-gates on the billed set. Closes over the
                    enclosing `retrieval` / `evidence_for_gen` / `_suff` so the
                    final round's state flows to the generator."""
                    nonlocal retrieval, evidence_for_gen, _suff
                    _gap_ret = run_live_retrieval(
                        research_question=q["question"],
                        amplified_queries=list(gap_queries),
                        protocol=_retrieval_protocol,
                        max_serper=_max_serper,
                        max_s2=_max_s2,
                        fetch_cap=_fetch_cap,
                        enable_openalex_enrich=True,
                        enable_prefetch_filter=False,
                        domain=None,
                        seed_urls=[],
                        research_frame=_retrieval_frame,
                        anchor_seed=False,   # GAP round: no broad anchor re-run
                    )
                    # Merge new sources + GLOBAL evidence_id renumber (reuse the
                    # legacy-expansion pattern) so ids never collide/overwrite.
                    # Dedup on the SAME canonical-URL identity the novelty metric
                    # uses, so the billed pool never double-counts a source that
                    # `marginal_novelty` already collapsed (e.g. a ?utm_ variant
                    # of an existing source).
                    _existing_urls = {
                        s.url for s in retrieval.classified_sources
                    }
                    for _src in _gap_ret.classified_sources:
                        if _src.url not in _existing_urls:
                            retrieval.classified_sources.append(_src)
                            _existing_urls.add(_src.url)
                    # Snapshot the corpus BEFORE the merge: this is the novelty
                    # BASELINE the round's raw retrieved rows are scored against.
                    _prev_corpus = list(retrieval.evidence_rows)
                    _existing_canon = {
                        canonical_source_url(
                            _r.get("source_url") or _r.get("url") or ""
                        )
                        for _r in retrieval.evidence_rows
                    }
                    _new_rows: list = []
                    for _ev in _gap_ret.evidence_rows:
                        _canon = canonical_source_url(
                            _ev.get("source_url") or _ev.get("url") or ""
                        )
                        if _canon and _canon in _existing_canon:
                            continue   # canonical-URL duplicate of an existing row
                        _existing_canon.add(_canon)
                        _ev["evidence_id"] = (
                            f"ev_{len(retrieval.evidence_rows):03d}"
                        )
                        retrieval.evidence_rows.append(_ev)
                        _new_rows.append(_ev)
                    # Re-select over the merged corpus, then re-inject the SAME
                    # static non-selection prepend (upload + V30 contract rows) the
                    # round-0 gate used, so the re-gate certifies EXACTLY the
                    # augmented billed set the generator will see (P4-16). Codex
                    # diff-gate P1: previously only upload rows were re-injected,
                    # silently dropping the V30 contract evidence on expansion
                    # rounds -> gate/generator disagreed with round 0 and V30 runs
                    # could falsely read under-covered post-expand.
                    _resel = select_evidence_for_generation(
                        research_question=q["question"],
                        protocol=protocol,
                        classified_sources=retrieval.classified_sources,
                        evidence_rows=retrieval.evidence_rows,
                        max_rows=max_ev,
                        primary_trial_anchors=_primary_anchors,
                        relevance_floor=_relevance_floor,   # Phase 5 (#989)
                    )
                    _billed = (
                        list(_gate_injected_prepend_rows)
                        + list(_resel.selected_rows)
                    )
                    evidence_for_gen = _billed
                    _suff = assess_plan_sufficiency(
                        plan=_research_plan,
                        corpus_rows=evidence_for_gen,
                        authority_floor=_suff_floor,
                        round_index=_suff.round_index + 1,
                        max_rounds=_suff_max_rounds,
                    )
                    return RoundOutcome(
                        cumulative_retrieved_rows=list(retrieval.evidence_rows),
                        evidence_for_gen=evidence_for_gen,
                        sufficiency_report=_suff,
                        # Novelty DENOMINATOR = the RAW rows this round RETRIEVED
                        # (`_gap_ret.evidence_rows`), INCLUDING canonical-URL
                        # duplicates already in the corpus -- so a gap round that
                        # mostly re-fetches seen sources reads a LOW novelty
                        # fraction and the `< eps` flatten stop can fire. Only the
                        # deduped `_new_rows` were appended to the cumulative
                        # corpus above; the denominator must NOT be that deduped
                        # set or novelty degenerates to 1.0-or-0.0.
                        new_round_rows=list(_gap_ret.evidence_rows),
                        prev_corpus_rows=_prev_corpus,
                    )

                _round0 = RoundOutcome(
                    cumulative_retrieved_rows=list(retrieval.evidence_rows),
                    evidence_for_gen=evidence_for_gen,
                    sufficiency_report=_suff,
                    # Round 0 has no prior corpus: every retrieved row is novel,
                    # so the raw denominator == the whole round-0 corpus and the
                    # baseline is empty. `saturation_decision`'s round>=1 guard
                    # ignores round-0 novelty anyway.
                    new_round_rows=list(retrieval.evidence_rows),
                    prev_corpus_rows=[],
                )
                _sat = run_saturation_loop(
                    round0=_round0,
                    run_round_fn=_run_gap_round,
                    max_rounds=_suff_max_rounds,
                    novelty_eps=_sat_eps,
                    max_discovery_calls=_sat_max_calls,
                    cost_per_query=_cost_per_query,
                    plan=_research_plan,
                    log=_log,
                )
                _log(
                    f"[saturation]  TERMINAL decision={_sat.decision} "
                    f"rounds_fired={_sat.rounds_fired} "
                    f"discovery_calls={_sat.cumulative_discovery_calls}/"
                    f"{_sat_max_calls} "
                    f"novelty_trajectory={[round(x, 3) for x in _sat.novelty_trajectory]}"
                )
                # I-meta-005 Phase 4 (#988) — Codex diff-gate P2: persist the
                # saturation trajectory into the manifest (summary -> manifest) so
                # a partial/success run is observable WITHOUT re-reading run_log:
                # decision, rounds fired, discovery spend, per-round novelty.
                summary["saturation"] = {
                    "decision": _sat.decision,
                    "rounds_fired": _sat.rounds_fired,
                    "discovery_calls": _sat.cumulative_discovery_calls,
                    "max_discovery_calls": _sat_max_calls,
                    "novelty_trajectory": [
                        round(x, 4) for x in _sat.novelty_trajectory
                    ],
                    "truncated_any_round": _sat.truncated_any_round,
                }
                # `_suff` / `evidence_for_gen` / `retrieval` now hold the FINAL
                # round's state (the closure mutated them via nonlocal).
                if _sat.decision == STOP_SUFFICIENT:
                    # Gap closed during the loop -> PROCEED on the full plan.
                    _gen_plan = _research_plan
                    _partial_mode = False
                else:
                    # STOP_NOVELTY / STOP_BUDGET with sections still under-covered
                    # -> a PARTIAL report on a PRUNED plan (sufficient sections
                    # ONLY). Zero sufficient sections -> abort_corpus_inadequate.
                    _pruned_plan, _dropped_sections = (
                        _prune_plan_to_sufficient_sections(_research_plan, _suff)
                    )
                    if _pruned_plan is not None:
                        _gen_plan = _pruned_plan
                        _partial_mode = True
                        summary["status"] = "partial_saturation"
                        # Codex diff-gate P2: name the DROPPED (under-covered)
                        # sections + their shortfall in the manifest so the partial
                        # artifact discloses exactly which planned sub-questions the
                        # corpus could not cover, and by how much.
                        def _uncovered_sub_query_text(_unit):
                            # The TEXT of the uncovered sub-questions: the empty
                            # facets if any, else (total-shortfall) all the unit's
                            # mapped sub-queries. Resolved against the pinned plan.
                            _idx = (
                                list(_unit.empty_facets)
                                or list(_unit.sub_query_indices)
                            )
                            _sq = _research_plan.sub_queries
                            return [
                                _sq[_i] for _i in _idx
                                if 0 <= _i < len(_sq)
                            ]
                        _dropped_detail = [
                            {
                                "unit_id": _u.unit_id,
                                "title": _u.title,
                                "covered_count": _u.covered_count,
                                "evidence_target": _u.evidence_target,
                                "empty_facets": list(_u.empty_facets),
                                "below_floor_count": _u.below_floor_count,
                                # Codex diff-gate iter-2 P2a: the actual TEXT of the
                                # planned sub-questions the corpus could not cover.
                                "uncovered_sub_queries": _uncovered_sub_query_text(
                                    _u
                                ),
                            }
                            for _u in _suff.per_unit
                            if not _u.sufficient
                        ]
                        summary["saturation"]["sections_kept"] = len(
                            _pruned_plan.outline
                        )
                        summary["saturation"]["sections_dropped"] = list(
                            _dropped_sections
                        )
                        summary["saturation"]["dropped_sections_detail"] = (
                            _dropped_detail
                        )
                        summary["saturation"]["authority_floor"] = (
                            _suff.authority_floor
                        )
                        _log(
                            f"[saturation]  PARTIAL report: "
                            f"{len(_pruned_plan.outline)} sufficient section(s) "
                            f"kept; dropped {len(_dropped_sections)} under-"
                            f"covered: {_dropped_sections}"
                        )

            if _suff.verdict != "proceed" and _partial_mode is False:
                # EXPAND or ABORT -> hold BEFORE the generator bills (Phase 3
                # guarantee: a shallow corpus NEVER spends a generator token).
                # Reached only when the saturation loop found ZERO sufficient
                # sections (pruned plan empty) -> abort_corpus_inadequate.
                _log(
                    f"[ABORT]       Plan-sufficiency {_suff.verdict.upper()}: "
                    f"{len(_suff.under_covered_units)} planned section(s) under-"
                    f"covered. Refusing to bill the generator on a corpus that "
                    f"does not cover every planned sub-question."
                )
                summary["status"] = "abort_corpus_inadequate"
                summary["error"] = (
                    f"plan_sufficiency_{_suff.verdict}: "
                    f"{','.join(_suff.under_covered_units)}"
                )
                _shortfall_lines = []
                for _u in _suff.per_unit:
                    if _u.sufficient:
                        continue
                    _shortfall_lines.append(
                        f"- **{_u.unit_id}** {_u.title!r}: "
                        f"covered={_u.covered_count}/target={_u.evidence_target} "
                        f"above floor; empty facets="
                        f"{_u.empty_facets}; below-floor relevant="
                        f"{_u.below_floor_count}"
                    )
                (run_dir / "report.md").write_text(
                    f"# Research report: {q['question']}\n\n"
                    "## Pipeline verdict\n\n"
                    "The corpus retrieved for this query did not cover every "
                    "planned sub-question to its per-section evidence target at "
                    "the authority floor. The pipeline is holding BEFORE billing "
                    "the report generator (zero generator tokens spent) rather "
                    "than synthesizing a report with uncovered planned facets.\n\n"
                    f"Verdict: **{_suff.verdict.upper()}** "
                    f"(authority floor {_suff.authority_floor}).\n\n"
                    "### Under-covered planned sections\n\n"
                    + "\n".join(_shortfall_lines)
                    + "\n\n### Suggested next steps\n\n"
                    "- Saturate retrieval on the under-covered sub-questions "
                    "(Phase 4 expansion loop).\n"
                    "- Verify the planned evidence targets match what the "
                    "literature can support for each facet.\n",
                    encoding="utf-8",
                )
                # NOTE: the retrieval trace was already flushed unconditionally
                # at the post-deepener checkpoint (mirrors the legacy abort at
                # :2273, which does not re-flush) — do NOT re-flush here.
                run_cost = current_run_cost()
                manifest = _base_manifest_envelope(
                    run_id=run_id, q=q, retrieval=retrieval, run_cost=run_cost,
                )
                manifest.update({
                    "status": "abort_corpus_inadequate",
                    "plan_sufficiency": asdict(_suff),
                    "corpus": {
                        "count": dist.total_sources,
                        "tier_fractions": dist.tier_fractions,
                    },
                })
                manifest = augment_v6_manifest(
                    manifest,
                    external_run_id=q.get("external_run_id"),
                    decision_id=q.get("decision_id"),
                    query_slug=q.get("slug"),
                )
                manifest = _attach_tool_utilization(manifest, run_dir)
                (run_dir / "manifest.json").write_text(
                    json.dumps(manifest, indent=2, sort_keys=True, default=str)
                    + "\n",
                    encoding="utf-8",
                )
                summary["manifest"] = manifest
                summary["cost_usd"] = run_cost
                try:
                    write_per_run_cost_ledger(run_dir, run_id)
                except Exception:
                    pass
                if q.get("v6_mode") and q.get("external_run_id"):
                    emit_terminal_event(
                        q.get("external_run_id"),
                        "abort_corpus_inadequate",
                        error_msg=summary.get("error"),
                    )
                set_current_run_id(None)
                set_reasoning_sink(None)
                log_f.close()
                return summary

        # I-cd-706: SSE evidence-id events over the FINAL evidence_for_gen set
        # (NOT inside retrieval loops — bounded to the selected rows, tens to
        # low-hundreds). Rows are dicts; guard for any object rows defensively.
        if q.get("v6_mode") and q.get("external_run_id"):
            _ext = q.get("external_run_id")
            _seen_evidence_ids: set[str] = set()
            for _row in evidence_for_gen:
                if isinstance(_row, dict):
                    _eid = _row.get("evidence_id", "") or ""
                    _eurl = _row.get("source_url") or _row.get("url") or ""
                else:
                    _eid = getattr(_row, "evidence_id", "") or ""
                    _eurl = getattr(_row, "source_url", "") or getattr(_row, "url", "") or ""
                # Codex iter-1 P2: dedup by evidence_id so the UI gets one
                # event per unique source, not one per row.
                if _eid and _eid not in _seen_evidence_ids:
                    _seen_evidence_ids.add(_eid)
                    emit_event(_ext, "evidence.id_assigned", {"id": _eid, "url": _eurl})

        # I-rdy-011 (#507): cooperative cancel checkpoint — before the
        # generator stage (the most expensive stage).
        if _abort_if_cancelled(q, run_dir, run_id, summary, _log):
            return summary

        # I-safety-002b (#925) PR-2: tag this entire call as the report-generator role
        # so the Path-B gate captures every nested LLM completion (multi-section + analyst
        # + retries + reason) under role="generator". No-op when the gate is inactive.
        # I-meta-002-q1d (#948): campaign KG reuse (default-OFF PG_SWEEP_KG_REUSE). Gather prior-VERIFIED
        # claims that the MECHANICAL match-gate confirms are independently supported by THIS question's
        # evidence pool, and feed them ONLY as advisory context to the UNVERIFIED analyst layer
        # (fail-closed: claim text + CURRENT evidence id only; no prior ids; no provenance). Fail-open.
        _prior_verified_context: list[dict] = []
        try:
            from src.polaris_graph.memory.kg_reuse_gate import gather_reuse_context
            _prior_verified_context = gather_reuse_context(
                str(out_root / "verified_claim_graph_campaign.db"),
                q["question"], evidence_for_gen,
            )
            if _prior_verified_context:
                _log(f"[kg-reuse] {len(_prior_verified_context)} prior-verified claim(s) re-grounded "
                     f"in current corpus → analyst advisory")
        except Exception as _exc:  # noqa: BLE001 — reuse is advisory; never abort a run
            _log(f"[kg-reuse] gather skipped (fail-open): {_exc}")

        # I-meta-005 Phase 5 (#989): dedup-by-finding on the FINAL generator-visible
        # pool. Runs AFTER the Phase-3 plan-sufficiency gate (which certified the
        # full PRE-dedup billed set) and AFTER the terminal proceed/partial decision,
        # so the gate is never fed a shrunken corpus. Collapses rehashes of the same
        # finding to one representative + corroboration_count (independent
        # registrable-domains); applies to the full-plan AND the partial pruned pool.
        # OFF (_use_finding_dedup False) -> evidence_for_gen unchanged.
        if _use_finding_dedup:
            from src.polaris_graph.authority.data_loader import (
                load_authority_data,
            )
            from src.polaris_graph.synthesis.finding_dedup import (
                dedup_by_finding,
            )
            _gov_suffixes = load_authority_data()["psl_gov_suffixes"]
            _dedup = dedup_by_finding(
                evidence_for_gen, gov_suffixes=_gov_suffixes
            )
            evidence_for_gen = _dedup.deduped_rows
            _finding_dedup_telemetry = {
                "raw_row_count": _dedup.raw_row_count,
                "distinct_finding_count": _dedup.distinct_finding_count,
                "collapsed_row_count": _dedup.collapsed_row_count,
                "clusters": [
                    {
                        "finding_key": list(c.finding_key),
                        "corroboration_count": c.corroboration_count,
                        "member_hosts": c.member_hosts,
                    }
                    for c in _dedup.clusters
                ],
            }
            _log(
                f"[finding-dedup] raw={_dedup.raw_row_count} "
                f"distinct={_dedup.distinct_finding_count} "
                f"collapsed={_dedup.collapsed_row_count} "
                f"-> {len(evidence_for_gen)} generator rows"
            )

        _pathb_gen_tok = _pathb.set_role("generator")
        try:
            multi = await generate_multi_section_report(
                research_question=q["question"],
                evidence=evidence_for_gen,
                prior_verified_context=_prior_verified_context,
                section_temperature=0.3,
            # M-31 (2026-04-21): raise outline_max_tokens 800→2500 to
            # match the upstream default. V19 had 3 / V20 had 2
            # "Expecting ',' delimiter" JSON decode failures — all
            # caused by mid-JSON truncation at 800 tokens when the
            # outline contains 5 sections × 12-20 ev_ids each.
            # Fallback to 3-section deterministic outline costs
            # ~60% of word count and drops all regulatory sources.
            outline_max_tokens=2500,
            # M-33 (2026-04-21): raise section_max_tokens 1200→2400 to
            # match the upstream default. V22 diagnostic: one of six
            # sections hit exactly 1200 tokens (capped mid-generation),
            # limiting per-trial framing and narrative depth (1964 words
            # vs ChatGPT DR 4830 / Gemini DR 6054). Same regression
            # class as M-31 (script override clobbers module default).
            #
            # v1.1 backlog A.1 (2026-04-30): expose env override for
            # narrative_length tuning. v1.0 BEAT-BOTH on 4 of 7 dims;
            # narrative_length is BEHIND-BOTH at 2346 vs 4830/6835.
            # PG_SECTION_MAX_TOKENS lets Phase G capacity tuning
            # adjust without code change. Default unchanged (2400).
            section_max_tokens=int(os.environ.get(
                "PG_SECTION_MAX_TOKENS", "2400",
            )),
            min_kept_fraction=float(os.environ.get(
                "PG_MIN_KEPT_FRACTION", "0.4",
            )),
            max_parallel_sections=int(os.environ.get("PG_MAX_PARALLEL_SECTIONS", "3")),
            tier_fractions=dist.tier_fractions,
            contradictions=[asdict(c) for c in contradictions],
            date_range=(
                protocol.get("date_range")
                if isinstance(protocol.get("date_range"), dict)
                else None
            ),
            uncovered_topics=uncovered_labels,
            # M-42b (2026-04-22): pass primary_trial_anchors so the
            # deterministic trial-table+timeline builder can consume
            # primary-trial evidence rows directly. Uses the same
            # anchors as M-35 retrieval + M-42e selector floor.
            primary_trial_anchors=_primary_anchors,
            # M-50 (2026-04-22): pass T2D-direct anchors for per-trial
            # subsections. Derived from the template's
            # per_query_trial_population_scope dict — anchors labeled
            # "direct" are eligible for subsections. SURMOUNT-1/3/4
            # (indirect) excluded.
            direct_trial_anchors=_m50_direct_anchors_for_sweep(
                _template, q["slug"]
            ),
            # M-52 (2026-04-23): V29-b. Pass the full retrieved
            # live_corpus so the generator can pull anchor-matched
            # primaries into evidence_pool when the selector's M-51
            # hard-reservation failed (e.g. selector called without
            # anchors, or selector bug). Belt-and-suspenders with
            # M-51. No-op when primary_trial_anchors is empty.
            live_corpus=retrieval.evidence_rows,
            # V30 Phase-2 M-63: when non-empty, replaces the LLM
            # outline for contract sections. Built above when
            # PG_V30_PHASE2_ENABLED=1 AND the slug has a contract.
            v30_contract_plans=_phase2_contract_plans,
            # Codex M-63 Medium 2 fix: when contract plans are
            # active, suppress M-50 for anchors already rendered
            # by a contract slot. Map contract entity_ids ->
            # anchor names via normalized substring match
            # (e.g. `surpass_2_primary` → `SURPASS-2`). No-op when
            # contract plans are empty.
            m50_skip_anchors=_compute_m50_skip_anchors(
                _phase2_contract_plans, _primary_anchors,
            ) if _phase2_contract_plans else None,
            # I-meta-005 Phase 1 (#985): pre-registered ResearchPlan. None in
            # OFF mode (legacy `_call_outline` / `_ALLOWED_SECTIONS` path runs
            # byte-identically). When set, the generator FIXES the section
            # structure to `research_plan.outline`, assigns retrieved evidence
            # to those sections post-retrieval, and routes M-44/M-47 on the
            # archetype tag (not a clinical title).
            # I-meta-005 Phase 4 (#988): `_gen_plan` is the FULL plan on PROCEED
            # and the PRUNED plan (sufficient sections only) in partial_saturation
            # mode; `_partial_mode` then disables ALL FIVE out-of-plan appenders so
            # the rendered headings == exactly the pruned sufficient sections.
            research_plan=_gen_plan,
            partial_mode=_partial_mode,
            )
        finally:
            _pathb.reset_role(_pathb_gen_tok)
        dt = time.time() - t0
        _log(f"              elapsed={dt:.1f}s outline={len(multi.outline)} "
             f"sections, words={multi.total_words}, "
             f"verified={multi.total_sentences_verified}, "
             f"dropped={multi.total_sentences_dropped}, "
             f"limitations_words={len(multi.limitations_text.split())}")

        # I-cd-706: per-section SSE events (ALL sections incl. dropped, so the
        # staged-progress UI shows what was proposed + dropped). Emit the
        # verifier verdict then the generator section-complete for each.
        if q.get("v6_mode") and q.get("external_run_id"):
            _ext = q.get("external_run_id")
            for sr in multi.sections:
                emit_event(_ext, "strict_verify.section_completed", {
                    "section": sr.title,
                    "local": sr.sentences_verified > 0,
                    "global": (not sr.dropped_due_to_failure and bool(sr.verified_text)),
                })
                emit_event(_ext, "generator.section_completed", {
                    "section": sr.title,
                    "verified": sr.sentences_verified,
                    "dropped": sr.sentences_dropped,
                })

        # Assemble final report
        section_bodies = []
        for sr in multi.sections:
            if sr.dropped_due_to_failure or not sr.verified_text:
                continue
            section_bodies.append(f"### {sr.title}\n\n{sr.verified_text}")
        sections_concat = "\n\n".join(section_bodies)
        # M-36 (2026-04-21): insert the Trial Summary table between the
        # main sections and Limitations. Empty string when the prose
        # names no clinical trials or when the LLM call failed — do
        # not emit an empty section heading in that case.
        if getattr(multi, "trial_summary_table_text", ""):
            sections_concat += (
                f"\n\n### Trial Summary\n\n{multi.trial_summary_table_text}"
            )
        # M-42b (2026-04-22): Trial Program Timeline emitted after
        # the Trial Summary table when the deterministic builder has
        # chronological data. Empty when only the LLM-fallback table
        # path ran (M-36 doesn't produce timelines).
        if getattr(multi, "trial_timeline_text", ""):
            sections_concat += (
                f"\n\n### Trial Program Timeline\n\n{multi.trial_timeline_text}"
            )

        # M-50 (2026-04-22): per-trial subsections for T2D-direct
        # primary trials. Empty string when fewer than 2 qualifying
        # primaries (strict gating — no empty subsections).
        if getattr(multi, "m50_per_trial_subsections_text", ""):
            sections_concat += (
                f"\n\n## Per-Trial Summaries\n\n"
                f"{multi.m50_per_trial_subsections_text}"
            )

        # M-45 (2026-04-22): persist per-URL refetch diagnostics for
        # primary-trial refetches. Codex V28 plan pass-2 acceptance:
        # refetch_diagnostics.json records backend + char count +
        # eligibility for every skipped primary row. Written even when
        # empty (list of zero entries) so downstream audits know the
        # builder ran vs. was disabled.
        m45_diag = getattr(multi, "refetch_diagnostics", None) or []
        (run_dir / "refetch_diagnostics.json").write_text(
            json.dumps(m45_diag, indent=2, sort_keys=True, default=str) + "\n",
            encoding="utf-8",
        )
        if m45_diag:
            eligible = sum(1 for d in m45_diag if d.get("eligible"))
            _log(
                f"[m45]         refetch diagnostics: {len(m45_diag)} urls "
                f"attempted, {eligible} eligible"
            )

        # M-44 (2026-04-22): persist primary-trial injection +
        # validator telemetry.
        m44_injection = getattr(multi, "m44_injection_log", None) or []
        m44_violations = getattr(multi, "m44_validator_violations", None) or []
        (run_dir / "m44_primary_citation_telemetry.json").write_text(
            json.dumps(
                {
                    "injection_log": m44_injection,
                    "validator_violations": m44_violations,
                },
                indent=2, sort_keys=True, default=str,
            ) + "\n",
            encoding="utf-8",
        )
        if m44_injection or m44_violations:
            injected = sum(
                1 for e in m44_injection if e.get("action") == "injected"
            )
            _log(
                f"[m44]         injected={injected} validator_violations="
                f"{len(m44_violations)}"
            )

        # M-47 (2026-04-22): persist evidence-linked Mechanism clamp/PK
        # validator diagnostic. Empty dict when Mechanism subset had no
        # clamp paper (no-op); populated dict when clamp papers were
        # present.
        m47_diag_obj = getattr(multi, "m47_mechanism_clamp_diagnostic", {}) or {}
        (run_dir / "m47_mechanism_clamp_diagnostic.json").write_text(
            json.dumps(m47_diag_obj, indent=2, sort_keys=True, default=str) + "\n",
            encoding="utf-8",
        )
        if m47_diag_obj.get("clamp_papers_in_subset"):
            passed = m47_diag_obj.get("any_passes_threshold", False)
            _log(
                f"[m47]         mechanism_clamp papers="
                f"{len(m47_diag_obj['clamp_papers_in_subset'])} "
                f"passes_threshold={passed}"
            )

        # M-53 (2026-04-23): V29-c per-anchor custody telemetry.
        # Codex-required diagnostic for V30 planning — each configured
        # anchor gets a 9-field JSON entry tracking the full custody
        # chain: found_in_live_corpus → selected_into_pool →
        # injected_into_section → direct_quote_adequate →
        # cited_in_verified_prose. When V29 fails to lift a dim, this
        # file identifies exactly which custody step broke.
        custody_log = getattr(multi, "v29_primary_custody_log", []) or []
        (run_dir / "v29_primary_custody.json").write_text(
            json.dumps(custody_log, indent=2, sort_keys=True, default=str) + "\n",
            encoding="utf-8",
        )
        if custody_log:
            cited = sum(1 for e in custody_log if e.get("cited_in_verified_prose"))
            total = len(custody_log)
            _log(
                f"[m53]         v29 primary custody: {cited}/{total} "
                f"anchors cited_in_verified_prose"
            )

        # M-50 (2026-04-22): persist per-trial subsection telemetry.
        m50_entries = getattr(
            multi, "m50_per_trial_subsections_entries", [],
        ) or []
        (run_dir / "m50_per_trial_subsections.json").write_text(
            json.dumps(
                {
                    "entries": m50_entries,
                    "total_subsections": len(m50_entries),
                    "total_chars": len(
                        getattr(multi, "m50_per_trial_subsections_text", "")
                    ),
                    "input_tokens": getattr(
                        multi,
                        "m50_per_trial_subsections_input_tokens",
                        0,
                    ),
                    "output_tokens": getattr(
                        multi,
                        "m50_per_trial_subsections_output_tokens",
                        0,
                    ),
                },
                indent=2, sort_keys=True, default=str,
            ) + "\n",
            encoding="utf-8",
        )
        if m50_entries:
            trials = ", ".join(e.get("trial", "") for e in m50_entries)
            _log(f"[m50]         per-trial subsections: {len(m50_entries)} [{trials}]")
        # I-bug-105: two-layer report. Insert Analyst Synthesis between
        # the Verified Findings (above) and the Limitations (below).
        # Disclosure preamble per Codex iter-1 brief verdict.
        if getattr(multi, "analyst_synthesis_text", ""):
            from src.polaris_graph.generator.analyst_synthesis import (
                ANALYST_SYNTHESIS_DISCLOSURE,
            )
            sections_concat += (
                f"\n\n## Analyst Synthesis\n\n"
                f"*{ANALYST_SYNTHESIS_DISCLOSURE}*\n\n"
                f"{multi.analyst_synthesis_text}"
            )
        # I-meta-005 Phase 7 (#991): quantified trade-off (gap 9, PAL rewire).
        # Gate PG_ENABLE_QUANTIFIED_ANALYSIS (default OFF -> whole block skipped,
        # report + manifest byte-identical). ON-mode runs Extract -> Model ->
        # Execute(deterministic, no codegen LLM) -> Bind -> Verify(Regime C) and
        # appends a VERIFIED "Quantified Trade-off" section BEFORE Limitations
        # (D3). The Model spec-gen Writer call is the ONLY billed step
        # (operator-gated). Defensive: any failure logs + skips, never aborts.
        _quantified_telemetry = None
        if os.environ.get("PG_ENABLE_QUANTIFIED_ANALYSIS", "0").strip() in (
            "1", "true", "TRUE", "yes",
        ):
            try:
                import json as _q_json
                import re as _q_re

                from src.polaris_graph.generator.quantified_analysis import (
                    run_quantified_section,
                )
                # I-meta-008 (#1030 PR-C): import PG_GENERATOR_MODEL HERE (mirrors the planner
                # block ~L1802) so the _q_spec_provider closure below can bind it. Python makes
                # PG_GENERATOR_MODEL a LOCAL of run_one_query (it is import-assigned in the planner
                # block), so when the planner path did NOT run, the closure hit an UnboundLocalError
                # ("cannot access free variable PG_GENERATOR_MODEL") and the Phase-7 quantified
                # differentiator silently no-op'd (run 5: spec_produced=False). Binding it in this
                # always-executed (PG_ENABLE_QUANTIFIED_ANALYSIS=1) block fixes that.
                from src.polaris_graph.llm.openrouter_client import (
                    OpenRouterClient,
                    PG_GENERATOR_MODEL,
                )

                _q_ev_pool = {
                    ev["evidence_id"]: ev for ev in evidence_for_gen
                    if isinstance(ev, dict) and ev.get("evidence_id")
                }

                async def _q_spec_provider(_question, _sourced):
                    # The ONLY billed step: ask the Writer for a JSON ModelSpec
                    # over the EXISTING extracted sourced numbers; parse defensively.
                    _shortlist = [
                        {"evidence_id": d.get("evidence_id"), "label": d.get("label"),
                         "context": d.get("context"), "value": d.get("value"),
                         "unit": d.get("unit")}
                        for d in _sourced[:40]
                    ]
                    _prompt = (
                        "You are modeling a quantified trade-off for a research "
                        "report. Using ONLY the sourced numbers below, emit a "
                        "SINGLE JSON object (no prose) with keys model_id, title, "
                        "inputs, outputs, sensitivity, solve_for per the POLARIS "
                        "ModelSpec schema. Each SOURCED input MUST carry "
                        "datapoint_ref:{ev_id,label,context,value,unit} copied "
                        "EXACTLY from one listed number; mark every ASSUMPTION "
                        "input modeled:true with base+unit+sweep. Every output "
                        "formula must be pure arithmetic over the declared input "
                        "names. If the numbers do not support a defensible model, "
                        'return {"model_id":"none"} and nothing else.\n\n'
                        f"QUESTION: {_question}\n\n"
                        f"SOURCED NUMBERS (JSON): {_q_json.dumps(_shortlist)[:8000]}"
                    )
                    _client = OpenRouterClient(model=PG_GENERATOR_MODEL)
                    try:
                        _resp = await _client.generate(
                            _prompt, max_tokens=1500, temperature=0.0,
                        )
                    finally:
                        await _client.close()
                    _txt = getattr(_resp, "content", "") or ""
                    _m = _q_re.search(r"\{.*\}", _txt, _q_re.DOTALL)
                    if not _m:
                        return None
                    try:
                        _obj = _q_json.loads(_m.group(0))
                    except _q_json.JSONDecodeError:
                        return None
                    if (not isinstance(_obj, dict)
                            or _obj.get("model_id") in (None, "", "none")):
                        return None
                    return _obj

                _q_section_md, _quantified_telemetry = await run_quantified_section(
                    q["question"], _q_ev_pool,
                    spec_provider=_q_spec_provider, run_dir=str(run_dir),
                )
                if _q_section_md:
                    sections_concat += "\n\n" + _q_section_md
                    _log(
                        "[phase7]      quantified trade-off: "
                        f"{_quantified_telemetry.get('verified_sentences', 0)} "
                        "verified sentence(s)"
                    )
                else:
                    _log(
                        "[phase7]      no quantified section "
                        f"(spec_produced={_quantified_telemetry.get('spec_produced')})"
                    )
            except Exception as _q_exc:  # never abort the run on quantified failure
                _log(f"[phase7]      quantified analysis skipped: {str(_q_exc)[:160]}")
                _quantified_telemetry = {"enabled": True, "error": str(_q_exc)[:200]}

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
            manifest = _base_manifest_envelope(
                run_id=run_id, q=q, retrieval=retrieval, run_cost=run_cost,
            )
            manifest.update({
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
            })
            manifest = augment_v6_manifest(
                manifest,
                external_run_id=q.get("external_run_id"),
                decision_id=q.get("decision_id"),
                query_slug=q.get("slug"),
            )
            manifest = _attach_tool_utilization(manifest, run_dir)
            (run_dir / "manifest.json").write_text(
                json.dumps(manifest, indent=2, sort_keys=True, default=str) + "\n",
                encoding="utf-8",
            )
            summary["manifest"] = manifest
            summary["cost_usd"] = run_cost
            try: write_per_run_cost_ledger(run_dir, run_id)
            except Exception: pass
            if q.get("v6_mode") and q.get("external_run_id"):
                emit_terminal_event(
                    q.get("external_run_id"),
                    "abort_no_verified_sections",
                    error_msg=summary.get("error"),
                )
            set_current_run_id(None)
            set_reasoning_sink(None)
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
        # M-22 + M-25e (DR audit passes 1-5): contradiction disclosure.
        # M-22 (earlier) surfaced a bounded narrative paragraph to avoid a
        # raw dump. But the evaluator's PT08 check requires that every
        # contradiction's subject AND predicate appear verbatim in report
        # text — the narrative alone leaves PT08 failing on every V10-V12
        # sweep. M-25e restores per-contradiction enumeration (subject +
        # predicate + claim-value range + source tiers) so PT08 passes
        # while the framing paragraph preserves Codex's "not adjudicated,
        # mostly extraction artifacts" context.
        if contradictions:
            methods += (
                f"\n## Contradiction disclosures\n"
                f"The contradiction detector flagged {len(contradictions)} "
                f"numeric disagreements across the evidence pool. Most are "
                f"extraction artifacts produced by grouping different "
                f"endpoints (e.g. HbA1c % vs body-weight %), different "
                f"doses, different populations (T2D vs obesity-without-"
                f"diabetes), or different comparators under the same "
                f"subject/predicate label. The detector does NOT adjudicate "
                f"by endpoint, population, dose, timepoint, or source tier; "
                f"raw detector output is available in `contradictions.json`. "
                f"Per-flag enumeration (PT08 disclosure):\n\n"
            )
            for c in contradictions:
                subj = getattr(c, "subject", None) or (
                    c.get("subject", "") if isinstance(c, dict) else ""
                )
                pred = getattr(c, "predicate", None) or (
                    c.get("predicate", "") if isinstance(c, dict) else ""
                )
                claims = getattr(c, "claims", None) or (
                    c.get("claims", []) if isinstance(c, dict) else []
                )
                if claims:
                    first = claims[0]
                    last = claims[-1]
                    v_first = getattr(first, "value", None) or (
                        first.get("value", "") if isinstance(first, dict) else ""
                    )
                    v_last = getattr(last, "value", None) or (
                        last.get("value", "") if isinstance(last, dict) else ""
                    )
                    unit = getattr(first, "unit", None) or (
                        first.get("unit", "") if isinstance(first, dict) else ""
                    )
                    tiers = []
                    for cc in claims:
                        t = getattr(cc, "source_tier", None) or (
                            cc.get("source_tier", "") if isinstance(cc, dict) else ""
                        )
                        if t and t not in tiers:
                            tiers.append(t)
                    tier_str = ", ".join(tiers) if tiers else "unknown"
                    methods += (
                        f"- {subj} / {pred}: cited values range "
                        f"{v_first} to {v_last} {unit} "
                        f"(source tiers: {tier_str}).\n"
                    )
                else:
                    methods += f"- {subj} / {pred}: (no claim values).\n"
            methods += (
                f"\nClaims made in the body of this report are individually "
                f"bound to their cited evidence IDs via the strict-verify "
                f"gate, so the reader can trace any specific numeric "
                f"discrepancy to its source regardless of detector "
                f"granularity.\n"
            )

        # Qualitative present-vs-absent safety-conflict disclosure (#944). Renders by ASSERTION
        # STATUS (present/absent/indeterminate/statistical_null) — NOT the loader-required numeric
        # value — and separates hard conflicts from review flags (Codex brief-gate iter-1 P1.5).
        if qualitative_records:
            _hard = [r for r in qualitative_records if r.severity in ("high", "medium")]
            _review = [r for r in qualitative_records if r.severity == "review"]
            methods += (
                f"\n## Qualitative safety-conflict disclosures\n"
                f"The qualitative detector flagged {len(_hard)} present-vs-absent clinical-safety "
                f"conflict(s) (contraindication / drug-interaction / eligibility / warning / "
                f"adverse-event causation) and {len(_review)} review-flagged item(s) requiring human "
                f"adjudication. Status is shown as asserted PRESENT/ABSENT/INDETERMINATE, not a "
                f"numeric value; review flags are NOT adjudicated conflicts.\n\n"
            )
            for r in _hard + _review:
                _label = "CONFLICT" if r.severity in ("high", "medium") else "REVIEW"
                _statuses = " vs ".join(
                    f"{cl.get('assertion_status', '?')} "
                    f"[ev={cl.get('evidence_id', '')}, tier={cl.get('source_tier', '')}]"
                    for cl in r.claims
                )
                methods += f"- [{_label}] {r.subject} / {r.predicate}: {_statuses} — {r.conflict_reason}\n"

        biblio_section = "\n\n## Bibliography\n"
        for b in multi.bibliography:
            biblio_section += (
                f"[{b['num']}] {b['statement'][:200]} — {b['url']} "
                f"(tier {b['tier']})\n"
            )

        # I-meta-002-q1d (#949b): verified-only extractive Key Findings block (frontier DR leads with
        # findings-up-front; POLARIS opened cold into Efficacy). Pure extraction over already-verified
        # section prose — zero new claims, no spend. Fail-open + default-ON kill-switch PG_SWEEP_KEY_FINDINGS.
        _key_findings = ""
        try:
            from src.polaris_graph.generator.key_findings import build_key_findings
            _key_findings = build_key_findings(getattr(multi, "sections", []))
        except Exception as _exc:  # noqa: BLE001 — additive summary; never abort the report
            _log(f"[key-findings] skipped (fail-open): {_exc}")
        final_report = (
            f"# Research report: {q['question']}\n\n"
            + _key_findings + sections_concat + methods + biblio_section
        )
        (run_dir / "report.md").write_text(final_report, encoding="utf-8")
        (run_dir / "bibliography.json").write_text(
            json.dumps(multi.bibliography, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

        # I-gen-005 Step 3c (PR #906 Codex iter-5 P2 follow-up):
        # gaps.json sidecar writer. When PG_ATOM_REFUSAL_MODE was
        # log_only or strict, each non-dropped SectionResult carries an
        # atom_validation_result populated by the orchestrator hook
        # (multi_section_generator line ~4358). Persist these as
        # gaps.json next to report.md per the Codex APPROVE_DESIGN
        # gaps.json schema (per-section claims + per-section summary +
        # document totals).
        try:
            from src.polaris_graph.generator.atom_refusal_validator import (
                write_gaps_sidecar,
                SectionValidationResult,
            )
            _section_val_results = []
            for sr in multi.sections:
                val = getattr(sr, "atom_validation_result", None)
                if val is not None and isinstance(val, SectionValidationResult):
                    _section_val_results.append(val)
            if _section_val_results:
                _gaps_path = write_gaps_sidecar(
                    run_dir,
                    document_id=q.get("slug", q.get("question", "")[:60]),
                    section_results=_section_val_results,
                )
                _log(
                    f"[gaps]        wrote {_gaps_path.name} "
                    f"({len(_section_val_results)} sections, mode="
                    f"{multi.sections[0].atom_validation_mode if multi.sections else 'off'})"
                )
        except Exception as _gaps_exc:
            # Fail-soft per atom-first design — gaps.json missing must
            # not crash the sweep. Log loud + continue.
            _log(f"[gaps]        WARN write_gaps_sidecar failed: {_gaps_exc}")

        # I-gen-005 Step 1.5 (Codex smoke-review P1 finding): serialize
        # the FINAL per-sentence accounting from SectionResult, not a
        # bare re-run of strict_verify on sr.rewritten_draft. The prior
        # re-run produced a STALE diagnostic log: sentences listed as
        # "dropped" here were still appearing in report.md because
        # downstream dedup/repair passes had accepted them, but the
        # diagnostic re-run never saw the dedup state. Per Codex
        # smoke-review verdict 2026-05-26 — "do not reconstruct final
        # verification details by re-running bare strict_verify on
        # rewritten drafts."
        #
        # NOTE: ev_pool dict is still constructed here because downstream
        # code (line ~2815 evidence_pool.json writeback) consumes it.
        # The strict_verify re-run was the only thing that needed to go.
        ev_pool = {ev["evidence_id"]: ev for ev in evidence_for_gen}
        verif_details = {
            "sections": [],
            "totals": {
                "sentences_verified": multi.total_sentences_verified,
                "sentences_dropped": multi.total_sentences_dropped,
            },
        }
        for sr in multi.sections:
            if not sr.rewritten_draft and not sr.kept_sentences_pre_resolve:
                continue
            kept_svs = sr.kept_sentences_pre_resolve or []
            dropped_svs = sr.dropped_sentences_final or []
            dedup_redundants = sr.dropped_sentences_dedup_redundant or []
            m41c_underframed_svs = getattr(
                sr, "dropped_sentences_m41c_underframed", []
            ) or []
            total_dropped_section = (
                len(dropped_svs) + len(dedup_redundants)
                + len(m41c_underframed_svs)
            )
            verif_details["sections"].append({
                "title": sr.title,
                "dropped_due_to_failure": sr.dropped_due_to_failure,
                "total_in": len(kept_svs) + total_dropped_section,
                "total_kept": len(kept_svs),
                "total_dropped": total_dropped_section,
                "kept": [
                    {
                        "sentence": sv.sentence,
                        "tokens": [
                            {"evidence_id": t.evidence_id,
                             "start": t.start, "end": t.end}
                            for t in sv.tokens
                        ],
                        "soft_warnings": getattr(sv, "soft_warnings", []),
                    }
                    for sv in kept_svs
                ],
                "dropped": [
                    {
                        "sentence": sv.sentence,
                        "failure_reasons": sv.failure_reasons,
                        "tokens": [
                            {"evidence_id": t.evidence_id,
                             "start": t.start, "end": t.end}
                            for t in sv.tokens
                        ],
                    }
                    for sv in dropped_svs
                ],
                # I-gen-005 Step 1.5: dedup redundants are a SEPARATE
                # category — LLM-consolidated near-duplicates, NOT
                # strict_verify failures.
                "dropped_by_dedup_redundant": list(dedup_redundants),
                # I-gen-005 Step 1.5 iter-2 (Codex P1 #2): M-41c
                # under-framed trial-name policy drops. Sentences here
                # PASSED strict_verify but were removed by the M-41c
                # claim-frame filter.
                "dropped_by_m41c_underframed": [
                    {
                        "sentence": sv.sentence,
                        "tokens": [
                            {"evidence_id": t.evidence_id,
                             "start": t.start, "end": t.end}
                            for t in sv.tokens
                        ],
                    }
                    for sv in m41c_underframed_svs
                ],
            })
        # Per-reason tally across all sections (strict_verify failures only).
        reason_counts: dict[str, int] = {}
        for s in verif_details["sections"]:
            for d in s["dropped"]:
                for r in d["failure_reasons"]:
                    key = r.split(":", 1)[0]  # collapse parameterized detail
                    reason_counts[key] = reason_counts.get(key, 0) + 1
        verif_details["drop_reason_counts"] = reason_counts
        # I-gen-005 Step 1.5: tally each post-strict-verify category
        # separately so the operator can distinguish the three drop
        # paths (strict_verify failures, dedup consolidations, M-41c
        # policy drops).
        verif_details["dedup_redundant_count"] = sum(
            len(s.get("dropped_by_dedup_redundant", []))
            for s in verif_details["sections"]
        )
        verif_details["m41c_underframed_count"] = sum(
            len(s.get("dropped_by_m41c_underframed", []))
            for s in verif_details["sections"]
        )
        (run_dir / "verification_details.json").write_text(
            json.dumps(verif_details, indent=2, sort_keys=True, default=str) + "\n",
            encoding="utf-8",
        )

        # I-beat-001: persist evidence_pool.json so the line-by-line
        # audit harness (scripts/run_line_by_line_audit.py
        # --resolved-report) can run on delivered output. Without
        # this, the audit harness has no source spans to check claims
        # against, and BEAT-BOTH proof cannot run on production reports.
        (run_dir / "evidence_pool.json").write_text(
            json.dumps(
                [{**v, "evidence_id": k} for k, v in ev_pool.items()],
                indent=2, sort_keys=True, default=str,
            ) + "\n",
            encoding="utf-8",
        )

        # Evaluator rule checks
        # I-rdy-011 (#507): cooperative cancel checkpoint — after generation,
        # before the evaluator. A cancel requested during the (long) generator
        # stage is observed here rather than silently completing the run.
        if _abort_if_cancelled(q, run_dir, run_id, summary, _log):
            return summary

        # I-safety-002b (#925) PR-2: tag external_evaluator under role="evaluator". Per
        # Codex iter-1 P3: this is no-op in honest_sweep today (enable_llm_judge=False
        # routes only rule checks; future-proofs if an LLM judge is enabled).
        _pathb_ev_tok = _pathb.set_role("evaluator")
        try:
            ev_out = run_external_evaluation(
                report_text=final_report,
                protocol=protocol,
                tier_distribution_report=asdict(dist),
                contradictions=[asdict(c) for c in contradictions],
                evidence_pool=ev_pool,
                enable_llm_judge=False,
            )
        finally:
            _pathb.reset_role(_pathb_ev_tok)
        (run_dir / "evaluator_rule_checks.json").write_text(
            json.dumps(ev_out.to_json_dict(), indent=2, sort_keys=True, default=str) + "\n",
            encoding="utf-8",
        )
        _log(f"[evaluator]   rule_checks={ev_out.rule_check_pass_count}/"
             f"{ev_out.rule_check_pass_count + ev_out.rule_check_fail_count} pass")
        for r in ev_out.rule_checks:
            if not r.passed:
                _log(f"                FAIL {r.item_id}: {r.details[:100]}")

        # Judge — LEGACY single-judge path. I-meta-007: SKIP entirely when the 4-role
        # seam will run (PG_FOUR_ROLE_MODE on AND a transport injected). Running both
        # would DOUBLE-JUDGE with DIFFERENT models (legacy Mirror/Gemma here vs the
        # 4-role Qwen Judge in the seam) and produce conflicting verdicts; the seam's
        # D8 decision is the SINGLE binding gate. When the seam is OFF (default), the
        # legacy judge runs exactly as before (byte-identical).
        _seam_will_run = (
            os.environ.get("PG_FOUR_ROLE_MODE", "0").strip() in ("1", "true", "True")
            and four_role_transport is not None
        )
        jr = None
        if _seam_will_run:
            _log("[judge]       skipped — 4-role seam (D8) is the binding gate")
        else:
            try:
                # I-safety-002b (#925) PR-2: tag the live judge under role="evaluator".
                _pathb_jr_tok = _pathb.set_role("evaluator")
                try:
                    jr = await judge_report(
                        report_text=final_report,
                        research_question=q["question"],
                        temperature=0.2,
                        max_tokens=800,
                    )
                finally:
                    _pathb.reset_role(_pathb_jr_tok)
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
                (run_dir / "judge_output.json").write_text(
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
        # invalid citation marker) with judge verdicts to produce
        # a release-gating decision. Abort class blocks success; partial
        # class prevents clean success but still ships the report.
        from src.polaris_graph.evaluator.evaluator_gate import (  # noqa: E402
            compute_evaluator_gate,
        )
        eval_gate = compute_evaluator_gate(
            ev_out=ev_out,
            judge_result=jr if (jr and jr.parse_ok) else None,
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
        elif not eval_gate.release_allowed:
            # I-run11-009 (#1055): defense in depth — ANY gate result that WITHHOLDS release must
            # map to a hold status, never the benign "ok_*" branches or the "ok" fall-through below
            # (LAW II no-silent-downgrade). This catches the judge-unavailable fail-closed
            # (gate_class="advisory_unavailable" + release_allowed=False) and any future
            # release-withholding gate_class, so the manifest status and release_allowed flag can
            # never contradict (a False release_allowed reading as a shippable "ok").
            summary_status = "abort_evaluator_critical"
        elif getattr(multi, "outline_fallback_used", False):
            # BUG-M-203: planner failed/retry-failed; fallback used.
            summary_status = "ok_outline_fallback"
        elif eval_gate.gate_class == "partial" and eval_gate.judge_critical_axes:
            # BUG-M-205: judge flagged critical axes (citation_tightness,
            # or hedging+tone pair, or multi-axis).
            summary_status = "ok_evaluator_advisory"
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
        # I-meta-005 Phase 4 (#988): a pruned partial-saturation report SURFACES
        # as `partial_saturation` (tier-1 partial) — it OVERRIDES the success-
        # path heuristics (ok/ok_thin_corpus/...), but NOT a genuine integrity
        # failure on the pruned sections (abort_*/fail_* still win, since those
        # mean the kept sections themselves did not verify/release).
        if _partial_mode and unified_status in (
            "success",
            "partial_thin_corpus",
            "partial_incomplete_corpus",
            "partial_rule_check_warnings",
            "partial_outline_fallback",
            "partial_evaluator_advisory",
            "partial_qwen_advisory",
        ):
            summary_status = "partial_saturation"
            unified_status = "partial_saturation"
        manifest = {
            "run_id": run_id,
            "slug": q["slug"],
            "domain": q["domain"],
            "question": q["question"],
            "status": unified_status,
            # I-rdy-010 (#506): uploaded-document grounding + sovereignty proof.
            "uploaded_documents_used": summary.get("uploaded_documents_used", 0),
            "uploaded_documents_blocked": summary.get(
                "uploaded_documents_blocked", 0
            ),
            # BUG-M-205: evaluator gate decision surfaced to downstream
            "release_allowed": eval_gate.release_allowed,
            "evaluator_gate": eval_gate.to_dict(),
            # BUG-M-201: generator-visible evidence provenance.
            "evidence_selection": evidence_selection.to_dict(),
            "protocol_sha256": scope.protocol_sha256,
            # #958 (S2): use the shared retrieval-section writer so the
            # corpus-truncation flag + counts land on the SUCCESS path too
            # (this inline block previously bypassed _base_manifest_envelope).
            "retrieval": _retrieval_manifest_section(retrieval),
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
                # I-bug-105 two-layer reporting: distinguish verified
                # word count from analyst-synthesis word count so
                # downstream consumers cannot mistake total length for
                # audited length (per Codex iter-1 brief P0).
                "verified_words": (
                    multi.total_words
                    - getattr(multi, "analyst_synthesis_words", 0)
                ),
                "analyst_synthesis_words": getattr(
                    multi, "analyst_synthesis_words", 0
                ),
                "analyst_synthesis_input_tokens": getattr(
                    multi, "analyst_synthesis_input_tokens", 0
                ),
                "analyst_synthesis_output_tokens": getattr(
                    multi, "analyst_synthesis_output_tokens", 0
                ),
                "sentences_verified": multi.total_sentences_verified,
                "sentences_dropped": multi.total_sentences_dropped,
                "limitations_words": len(multi.limitations_text.split()),
            },
            "evaluator_rule_pass": ev_out.rule_check_pass_count,
            "evaluator_rule_fail": ev_out.rule_check_fail_count,
            "judge_verdicts": (
                {v: sum(1 for j in jr.verdicts.values()
                        if j["verdict"] == v)
                 for v in ("good", "acceptable", "needs_revision", "unknown")}
                if jr and jr.parse_ok
                # I-meta-007: when the 4-role seam ran, the legacy judge was
                # deliberately skipped (D8 is the binding gate) — say so, don't
                # mislabel it "failed".
                else ({"superseded_by_four_role_seam": True} if _seam_will_run
                      else {"error": "failed"})
            ),
            "cost_usd": run_cost,
            "budget_cap_usd": PG_MAX_COST_PER_RUN,
            # GH#423 I-gen-002: cross-section fact-dedup telemetry.
            # Persists fact_dedup pass results (groups, redundants,
            # rewrites_applied, drops) so observability + auditability
            # of the dedup behavior survives into manifest.json.
            "fact_dedup": getattr(multi, "fact_dedup_telemetry", {}),
        }

        # I-meta-005 Phase 1 (#985, P1-8): record the SHA-pinned ResearchPlan
        # in the manifest (gap #19 extension). ON-mode only — the key is absent
        # in OFF, preserving the legacy manifest shape byte-for-byte.
        if _use_research_planner and _research_plan is not None:
            manifest["research_plan"] = {
                "plan_path": str((run_dir / "research_plan.json").name),
                "plan_sha256": _plan_sha,
                "sub_query_count": len(_research_plan.sub_queries),
                "outline_archetypes": [
                    item.archetype for item in _research_plan.outline
                ],
            }

        # I-meta-005 Phase 4 (#988) — Codex diff-gate iter-2 P2a: surface the
        # saturation trajectory + per-section shortfall (incl. uncovered sub-query
        # text) in the per-run manifest too. It already lands in sweep_summary.json
        # via `summary`; this makes the PER-RUN audit artifact self-contained for a
        # partial_saturation result. ON-mode only (key absent in OFF -> legacy
        # manifest shape preserved).
        if summary.get("saturation"):
            manifest["saturation"] = summary["saturation"]

        # I-meta-005 Phase 5 (#989): finding-dedup telemetry + per-cluster
        # corroboration (independent hosts) in the per-run manifest. ON-mode only
        # (key absent in OFF -> legacy manifest shape preserved).
        if _finding_dedup_telemetry is not None:
            manifest["finding_dedup"] = _finding_dedup_telemetry

        # I-meta-005 Phase 7 (#991): quantified-analysis telemetry (spec produced,
        # execution success, sourced/modeled input counts, verified/dropped
        # sentence counts, sourced-input conflicts). ON-mode only (key absent in
        # OFF -> legacy manifest shape preserved byte-for-byte).
        if _quantified_telemetry is not None:
            # I-meta-008 P1-3 (#1018): normalize a `fired` boolean so a post-run assertion can
            # detect a SILENT no-op, and surface it LOUDLY in the log. The block never aborts the
            # run, so without this an error / spec_produced=False completes silently without the
            # Phase-7 differentiator and the manifest gives no single clear signal.
            _quantified_telemetry = _normalize_quantified_telemetry(_quantified_telemetry)
            manifest["quantified_analysis"] = _quantified_telemetry
            if not _quantified_telemetry["fired"]:
                _log(
                    "[phase7]      WARNING: quantified analysis ran but produced NO verified "
                    "quantified output (silent no-op) — manifest.quantified_analysis.fired=False"
                )

        # I-meta-002 sub-PR-6: GUARDED 4-role evaluation seam (default OFF, NO spend).
        # Activates ONLY when an explicit RoleTransport is INJECTED (four_role_transport)
        # AND PG_FOUR_ROLE_MODE is enabled. There is NO default real transport: the live
        # 4-role sweep is Gate-B (after lock promotion + operator spend authorization). When
        # this branch is OFF (the default), every line below is the unchanged legacy path —
        # eval_gate already drove manifest['release_allowed'] + status above.
        #
        # When ON: D8 (apply_d8_release_policy, via sweep_integration) is the SINGLE binding
        # gate. We OVERRIDE both manifest['release_allowed'] AND manifest['status'] from the
        # D8 decision (so status and release_allowed cannot contradict — the double-gate the
        # Codex P2 forbids) and DEMOTE the legacy evaluator_gate to advisory metadata only.
        # claims/ledger/required-set are caller-supplied (four_role_inputs); the sweep never
        # synthesizes claim_ids or a coverage denominator (fail-closed: sweep_integration
        # raises on a blank id or an empty canonical required set).
        _four_role_on = os.environ.get("PG_FOUR_ROLE_MODE", "0").strip() in (
            "1", "true", "True",
        )
        # I-meta-008 (#1014) loud guard: PG_FOUR_ROLE_MODE is on but NO transport was injected,
        # so the 4-role seam stays INERT and this run would silently use the legacy single-evaluator
        # gate. That is the exact "benchmark started via a legacy entrypoint" trap (#1014): the
        # 4-role benchmark ONLY runs via scripts/dr_benchmark/run_gate_b.py (its main()/the
        # run_gate_b_query entrypoint INJECTS a transport).
        # I-run11-009 (#1055): the loud log alone was NOT enough — the run still fell onto the legacy
        # gate, whose own judge-unavailable fail-open could ship an unjudged report. A caller that
        # explicitly asked for 4-role mode (PG_FOUR_ROLE_MODE=1) but supplied no transport is
        # MISCONFIGURED; it must FAIL CLOSED, never silently downgrade to the legacy gate (LAW II;
        # §-1.1). Legacy callers that never set PG_FOUR_ROLE_MODE are unaffected (the guard does not
        # fire for them). Override the manifest built above to a hold.
        if _four_role_on and four_role_transport is None:
            print(
                "[I-meta-008][GUARD] PG_FOUR_ROLE_MODE is ON but no four_role_transport was "
                "injected -- the 4-role benchmark seam is INERT. FAILING CLOSED (release HELD): "
                "this run will NOT silently fall back to the legacy single-evaluator gate. The "
                "native 4-role benchmark runs ONLY via scripts/dr_benchmark/run_gate_b.py "
                "(CLI: python -m scripts.dr_benchmark.run_gate_b)."
            )
            # Codex diff-gate iter-1 P1: set the LOCAL summary_status/unified_status too, not just the
            # manifest fields. The tail writes `summary["status"] = summary_status` (~L4813) and
            # sweep_summary.{json,md} read that top-level status — without this a held misconfiguration
            # could still surface as "ok"/"warn" in the summary while the manifest says held.
            summary_status = "four_role_held"
            unified_status = to_unified_status(summary_status)
            manifest["release_allowed"] = False
            manifest["status"] = unified_status
            manifest["four_role_seam_inert"] = True
        if _four_role_on and four_role_transport is not None:
            # M3b: the seam resolves inputs (builder WINS over static four_role_inputs; both
            # None -> fail-closed), runs the SINGLE binding D8 gate, and persists the per-claim
            # audit map next to the run. The builder closure is called HERE — AFTER generation —
            # so it sees the finished `multi` report; the sweep still synthesizes nothing itself.
            from src.polaris_graph.roles.sweep_integration import (  # noqa: E402
                FourRoleEvaluationResult,
                build_evaluator_agrees_map,
                run_four_role_seam,
            )
            # I-meta-008 (#1028-followup / hang): the seam runs SYNCHRONOUS httpx verifier calls.
            # Calling it directly in this async coroutine BLOCKS the event loop, and a wedged
            # verifier call (per-call 900s x up to 3 attempts) could hang the whole run ~45 min with
            # NO terminal artifact (run 5: 18-min poll() hang, no manifest.json). Run it on a worker
            # thread bounded by an overall wall-clock timeout and FAIL CLOSED on timeout/error
            # (release HELD — never release un-evaluated output, LAW II / §9.1). The timeout/error
            # path returns a real HELD FourRoleEvaluationResult so the existing post-seam manifest
            # block is byte-unchanged. Budget integrity: mirror the planner-LLM cost-reconciliation
            # (this file ~L1840) — copy_context for READ visibility + write the worker's accumulated
            # _RUN_COST_CTX delta back to the parent so PG_MAX_COST_PER_RUN stays intact even though
            # the seam ran in a copied ThreadPoolExecutor context.
            import concurrent.futures as _seam_futures
            import contextvars as _seam_cv
            from src.polaris_graph.llm.openrouter_client import (
                BudgetExceededError as _SeamBudgetExceededError,
                _RUN_COST_CTX as _seam_cost_ctx,
            )
            # I-run11-004: default raised 2400 -> 7200s. 2400 was the run-12 truncator — the
            # 4-role seam (now incl. the reasoning-ON MiniMax-M2 decomposition Sentinel + the xhigh
            # Mirror/Judge) takes minutes per claim, and a 2400s cap fired mid-run and held a
            # truncated manifest. PG_VERIFIER_LLM_TIMEOUT_SECONDS (the per-call budget) stays 900.
            # LAW VI: env-overridable.
            _seam_timeout = float(
                os.environ.get("PG_FOUR_ROLE_SEAM_TIMEOUT_SECONDS", "7200")
            )
            _seam_kg_path = out_root / "verified_claim_graph_campaign.db"
            _seam_parent_cost = _seam_cost_ctx.get()
            _seam_cost_holder = [_seam_parent_cost]
            _seam_parent_ctx = _seam_cv.copy_context()

            def _seam_worker() -> FourRoleEvaluationResult:
                def _run_under_ctx() -> FourRoleEvaluationResult:
                    try:
                        return run_four_role_seam(
                            four_role_transport,
                            run_dir=run_dir,
                            timestamp=_utc_now_iso(),
                            four_role_input_builder=four_role_input_builder,
                            four_role_inputs=four_role_inputs,
                            multi=multi,
                            template=_template,
                            slug=q["slug"],
                            domain=q["domain"],
                            ev_pool=ev_pool,
                            # I-meta-002-q1d (#948): persist the snowball KG to the CAMPAIGN-scoped
                            # db so later questions in this sweep can reuse THIS question's VERIFIED
                            # claims (fail-closed read).
                            campaign_kg_db=str(_seam_kg_path),
                        )
                    finally:
                        # Capture accumulated verifier spend even on raise/timeout so the parent
                        # write-back below cannot under-report (budget-cap integrity, LAW II).
                        _seam_cost_holder[0] = _seam_cost_ctx.get()
                return _seam_parent_ctx.run(_run_under_ctx)

            _seam_held_reason = None
            # Manage the executor MANUALLY (NOT `with`): a `with ThreadPoolExecutor` __exit__ calls
            # shutdown(wait=True), which BLOCKS until the wedged worker finishes — defeating the
            # timeout entirely (Codex diff-gate P1). shutdown(wait=False, cancel_futures=True) returns
            # promptly so the held manifest is written AT PG_FOUR_ROLE_SEAM_TIMEOUT_SECONDS; the
            # orphaned worker thread exits on its own per-call timeout. Mirrors audit_ir/parallel_fetch.py.
            _seam_pool = _seam_futures.ThreadPoolExecutor(max_workers=1)
            try:
                four_role_result = _seam_pool.submit(_seam_worker).result(
                    timeout=_seam_timeout
                )
            except _seam_futures.TimeoutError:
                _seam_held_reason = "seam_timeout"
            except _SeamBudgetExceededError:
                # A verifier cap breach (PG_MAX_COST_PER_RUN) MUST propagate to the existing outer
                # abort_budget_exceeded handler (the clean budget-abort contract) — NOT be swallowed
                # into a held seam_error (Codex diff-gate iter-2 P1). The worker's `finally` already
                # updated the cost holder, so the `finally` below reconciles the full spend before
                # this re-raises.
                raise
            except Exception as _seam_exc:  # noqa: BLE001 - any OTHER seam failure must fail CLOSED
                _seam_held_reason = f"seam_error:{type(_seam_exc).__name__}:{str(_seam_exc)[:120]}"
            finally:
                # NON-BLOCKING shutdown so a wedged worker cannot delay the held manifest (P1).
                _seam_pool.shutdown(wait=False, cancel_futures=True)
                # Budget reconciliation: on the SUCCESS path the worker's `finally` already updated
                # `_seam_cost_holder`, so this write-back is EXACT. On the TIMEOUT path the worker is
                # still running (holder == parent cost -> delta 0), so the in-flight verifier spend is
                # NOT added to the parent cap — an acceptable tradeoff (Codex P2): the run is ABORTING
                # (release HELD), the operator authorized spend, the orphaned worker's cost is bounded
                # by its own per-call timeout, and prompt fail-closed termination outranks exact
                # budget accounting on an already-aborted run.
                _seam_delta = _seam_cost_holder[0] - _seam_parent_cost
                if _seam_delta > 0:
                    _seam_cost_ctx.set(_seam_parent_cost + _seam_delta)
            if _seam_held_reason is not None:
                _log(
                    f"[four_role]   SEAM {_seam_held_reason} after <= {_seam_timeout}s "
                    "-> release HELD (fail-closed; terminal manifest written)"
                )
                four_role_result = FourRoleEvaluationResult(
                    release_allowed=False,
                    held_reasons=[_seam_held_reason],
                    gaps=[],
                    final_verdicts={},
                    records=[],
                    coverage_fraction=0.0,
                    fabricated_occurrence_latched=False,
                    needs_rewrite=[],
                    kg_path=_seam_kg_path,
                )
            # Demote the legacy gate to ADVISORY metadata; D8 owns the headline decision.
            manifest["evaluator_gate_advisory"] = manifest.pop("evaluator_gate")
            manifest["release_allowed"] = four_role_result.release_allowed
            # Single binding status: released => success; held => release-blocking abort.
            summary_status = (
                "four_role_released"
                if four_role_result.release_allowed
                else "four_role_held"
            )
            # Reassign BOTH the summary label AND the unified local so manifest.json,
            # sweep_summary.json (summary["status"] at the function tail), and the status log
            # line are all D8-driven and cannot disagree (no double-gate, Codex P2).
            unified_status = to_unified_status(summary_status)
            manifest["status"] = unified_status
            # final_verdicts (keyed by EXISTING claim_id) drive evaluator_agrees at the real
            # assembly point (clinical_generator, Gate-B); they are surfaced here so the D8
            # decision is fully auditable from the manifest. evaluator_agrees_from_verdict maps
            # VERIFIED->True / else->False (the helper lives in sweep_integration). The sweep's
            # SectionResult path holds SentenceVerification, NOT VerifiedSentence, so there is no
            # VerifiedSentence object to write here — populating one would be fake wiring.
            manifest["four_role_evaluation"] = {
                "release_allowed": four_role_result.release_allowed,
                "held_reasons": four_role_result.held_reasons,
                "coverage_fraction": round(four_role_result.coverage_fraction, 3),
                "fabricated_occurrence_latched": (
                    four_role_result.fabricated_occurrence_latched
                ),
                "needs_rewrite": four_role_result.needs_rewrite,
                "final_verdicts": four_role_result.final_verdicts,
                "gaps": [
                    {
                        "ref": gap.ref,
                        "kind": gap.kind,
                        "severity": gap.severity,
                        "note": gap.note,
                    }
                    for gap in four_role_result.gaps
                ],
                "kg_path": str(four_role_result.kg_path),
            }
            # I-meta-002 PR-9/M5: ADDITIVE per-claim evaluator_agrees MAP for audit/inspector
            # fidelity (NOT a release gate — D8 above stays the single binding gate). Joinable to
            # four_role_claim_audit.json by claim_id. kept_claim_ids is None here: on the sweep
            # path the FourRoleClaim set is built from KEPT (is_verified) sentences only, so every
            # claim_id in final_verdicts is already a kept claim (invariant documented in the
            # helper). The §-1.1 fail-safe rule (VERIFIED+kept -> True; every other verdict ->
            # False) lives in build_evaluator_agrees_map -> evaluator_agrees_from_verdict.
            manifest["four_role_evaluation"]["evaluator_agrees"] = (
                build_evaluator_agrees_map(four_role_result.final_verdicts)
            )
            _log(
                f"[four_role]   release_allowed={four_role_result.release_allowed} "
                f"coverage={four_role_result.coverage_fraction:.3f} "
                f"held_reasons={four_role_result.held_reasons}"
            )

        # V30 Report Contract Architecture integration (Phase 1 of
        # two). Opt-in via PG_V30_ENABLED=1. When disabled this is a
        # complete no-op — the runner doesn't even import the V30
        # module (Codex sweep-integration audit Medium: fully
        # hermetic gating). When enabled, runs M-54→M-55→M-56→M-57→
        # M-60→M-61 post-generation: compiles the per-query
        # contract, fetches deterministic DOI/PMID/Unpaywall content
        # for each contracted entity, composes the outline, emits
        # the structured frame_coverage_report +
        # human_gap_tasks.json.
        #
        # Phase 2 (separate cycle) will wire M-58 slot-bound prompts
        # + M-59 validator into the generator. At Phase 1 we only
        # attach the coverage block to manifest and append the
        # Methods disclosure to report.md — existing generator
        # output is untouched.
        if os.environ.get("PG_V30_ENABLED", "0").strip() in (
            "1", "true", "True",
        ):
            try:
                from src.polaris_graph.honest_sweep_integration import (
                    append_disclosure_to_report,
                    merge_v30_into_manifest,
                    run_v30_post_generation,
                )
                # Phase 1 ships RETRIEVAL-coverage semantics only.
                # Legacy report / bibliography cross-check was
                # deprecated after three Codex audit rounds of
                # heuristic false-passes (see pass-4 scope narrow
                # in honest_sweep_integration module docstring).
                # Phase 2 (M-58 + M-59 generator integration)
                # will claim true report-coverage.
                _report_path = run_dir / "report.md"
                v30_result = run_v30_post_generation(
                    research_question=q["question"],
                    scope_template=_template,
                    slug=q["slug"],
                    run_dir=run_dir,
                    log=_log,
                )
                # Manifest merge via factored helper (unit-tested
                # in tests/polaris_graph/test_honest_sweep_integration.py).
                merge_v30_into_manifest(manifest, v30_result)
                # Append Methods disclosure to report.md only if
                # the report actually exists — helper never
                # creates a disclosure-only file.
                if v30_result.enabled and v30_result.methods_disclosure_text:
                    try:
                        appended = append_disclosure_to_report(
                            _report_path,
                            v30_result.methods_disclosure_text,
                        )
                        if appended:
                            _log(
                                "[V30]         appended frame-"
                                "coverage disclosure to report.md"
                            )
                        else:
                            _log(
                                "[V30]         skipped disclosure "
                                "append: report.md missing"
                            )
                    except Exception as _report_exc:
                        _log(
                            f"[V30]         WARN report.md "
                            f"append failed: {_report_exc}"
                        )
            except Exception as _v30_exc:
                _log(
                    f"[V30]         ERROR integration exception: "
                    f"{type(_v30_exc).__name__}: {_v30_exc}"
                )
                manifest["v30_error"] = (
                    f"{type(_v30_exc).__name__}: {_v30_exc}"
                )

        # I-bug-111: surface synthesis [N] scrub alert in manifest.
        # `synthesis_n_scrub_alert: bool` is True iff any single
        # synthesis call in this run scrubbed more than
        # SYNTHESIS_SCRUB_ALERT_THRESHOLD (=5) [N] markers, indicating
        # the synthesis prompt or bibliography may be degenerating.
        # Defensive lazy import: tolerate environments where the
        # module isn't available.
        try:
            from src.polaris_graph.generator.analyst_synthesis import (
                synthesis_scrub_alert_state,
            )
            manifest["synthesis_n_scrub_alert"] = synthesis_scrub_alert_state()
        except Exception:  # noqa: BLE001 — defensive: surfacing failure must not abort manifest write
            pass

        # I-meta-007b (#meta-007): write run_dir/tool_summary.json and add the
        # additive manifest['tool_utilization'] summary via the shared helper
        # (same helper now called on every abort/error path — single source of
        # truth, identical shape). ON-mode only (gated on PG_ENABLE_TOOL_TRACKER
        # inside the helper): when OFF, neither the file nor the key is produced,
        # so manifest.json is byte-identical to the pre-I-meta-007b output.
        manifest = _attach_tool_utilization(manifest, run_dir)

        manifest = augment_v6_manifest(
            manifest,
            external_run_id=q.get("external_run_id"),
            decision_id=q.get("decision_id"),
            query_slug=q.get("slug"),
        )
        # I-meta-008 (#1015): `run_cost` was snapshotted (line ~4250) BEFORE the 4-role seam,
        # which now threads verifier spend into the run-budget accumulator. Recompute from the
        # accumulator so a successful Gate-B manifest reports generator + verifier cost, not
        # generator-only (a LAW-II under-reporting smell otherwise). No-op on non-4-role runs.
        run_cost = current_run_cost()
        manifest["cost_usd"] = run_cost

        # I-cap-002 feature 2/4 (#1060): ADVISORY analytical-depth annotation. NEVER gates.
        # Placed here — AFTER the 4-role seam status/release overwrite (L~4740-4751), the V30
        # block (which appends the Methods disclosure to report.md, L~4810+), and the cost
        # recompute above — so status / release_allowed / report.md are all FINAL. It only ADDS
        # manifest['analytical_depth_advisory'] + an analytical_depth.json sidecar; it reads the
        # delivered report but never mutates status/release/abort. Default OFF in run_one_query
        # (legacy honest-sweep manifest byte-unchanged); the Gate-B entry turns it ON via
        # PG_DEPTH_ANNOTATION_IN_BENCHMARK so the paid benchmark emits it. Fail-open: any error
        # logs + skips. Surface = the FULL on-disk report.md (front Key Findings, body, tables,
        # Limitations, V30 disclosure), split on ATX headers — see analytical_depth module. The
        # 'passed'/'deficient_sections' here are a benchmark-split ADVISORY read, NOT the RC-8 gate.
        if os.environ.get("PG_DEPTH_ANNOTATION_IN_BENCHMARK", "0").strip() in (
            "1", "true", "True",
        ):
            try:
                from src.polaris_graph.generator.analytical_depth import (
                    evaluate_analytical_depth,
                    split_report_into_sections,
                )
                try:
                    _report_text = (run_dir / "report.md").read_text(encoding="utf-8")
                except Exception:  # noqa: BLE001 — fall back to the in-memory assembly
                    _report_text = final_report
                _depth = evaluate_analytical_depth(
                    split_report_into_sections(_report_text)
                )
                _depth["advisory"] = True       # the benchmark NEVER gates on this signal
                _depth["surface"] = "benchmark_atx_split"
                # P2.3 (Codex iter-1): write the sidecar FIRST, then stamp the manifest key, so the
                # manifest can never carry the key while the sidecar is absent.
                (run_dir / "analytical_depth.json").write_text(
                    json.dumps(_depth, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8",
                )
                manifest["analytical_depth_advisory"] = _depth
                _log(
                    f"[depth]       advisory comparisons={_depth['comparison_markers']} "
                    f"tables={_depth['tables']} key_findings={_depth['key_findings']} "
                    f"challenges={_depth['challenge_markers']} "
                    f"deficient={len(_depth['deficient_sections'])} (non-gating)"
                )
            except Exception as _depth_exc:  # noqa: BLE001 — advisory; never abort the run
                _log(
                    f"[depth]       WARN advisory annotation skipped (fail-open): {_depth_exc}"
                )

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
    except BudgetExceededError as budget_exc:
        # I-meta-008 (#1015): PG_MAX_COST_PER_RUN was breached mid-run — generator OR (now) a
        # 4-role verifier call via the RecordingTransport cost hook. This is a CLEAN budget
        # abort, NOT error_unexpected: catch-and-set (do NOT re-raise) so the teardown below
        # (per-run ledger copy, emit_terminal_event, run_id/sink reset at ~4710) still runs —
        # those are OUTSIDE this try with no `finally`, so a bare `raise` would leak a stale
        # run_id/sink into the next question. Status maps to abort_budget_exceeded via
        # to_unified_status; the generator and the verifier now abort identically.
        run_cost = current_run_cost()
        _log(
            f"[BUDGET]      PG_MAX_COST_PER_RUN breached: {budget_exc} "
            f"(run_cost=${run_cost:.4f}, cap=${PG_MAX_COST_PER_RUN:.4f})"
        )
        summary["status"] = "abort_budget_exceeded"
        summary["error"] = str(budget_exc)[:300]
        try:
            if run_dir is not None:
                budget_manifest = {
                    "run_id": run_id,
                    "slug": q.get("slug", ""),
                    "domain": q.get("domain", ""),
                    "question": q.get("question", ""),
                    "status": "abort_budget_exceeded",
                    "error": str(budget_exc)[:500],
                    "cost_usd": run_cost,
                    "budget_cap_usd": PG_MAX_COST_PER_RUN,
                }
                budget_manifest = augment_v6_manifest(
                    budget_manifest,
                    external_run_id=q.get("external_run_id"),
                    decision_id=q.get("decision_id"),
                    query_slug=q.get("slug"),
                )
                budget_manifest = _attach_tool_utilization(budget_manifest, run_dir)
                (run_dir / "manifest.json").write_text(
                    json.dumps(budget_manifest, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8",
                )
                summary["manifest"] = budget_manifest
                summary["cost_usd"] = run_cost
        except Exception as manifest_exc:  # noqa: BLE001 — best-effort; never mask the budget abort
            _log(f"[BUDGET]      budget-abort manifest-write-also-failed: {manifest_exc}")
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
                error_manifest = augment_v6_manifest(
                    error_manifest,
                    external_run_id=q.get("external_run_id"),
                    decision_id=q.get("decision_id"),
                    query_slug=q.get("slug"),
                )
                error_manifest = _attach_tool_utilization(error_manifest, run_dir)
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

    # BUG-M-206 + BUG-N-301 teardown: per-run ledger copy + run_id reset.
    try:
        n_ledger = write_per_run_cost_ledger(run_dir, run_id)
        summary["cost_ledger_entries"] = n_ledger
    except Exception as ledger_exc:
        logging.getLogger(__name__).warning(
            "per-run ledger copy failed: %s", ledger_exc
        )

    # I-arch-001e: success + error_unexpected terminal events. The 5 abort
    # paths emit inline before their early returns; this catches the
    # success path (status set at line ~2865) plus the error path (status
    # set to "error" at line ~2873, mapped to error_unexpected here).
    if q.get("v6_mode") and q.get("external_run_id"):
        _final_status = summary.get("status") or "error_unexpected"
        if _final_status == "error":
            _final_status = "error_unexpected"
        # Use the manifest's unified status if available — it is the
        # canonical taxonomy (success / partial_* / abort_* / error_unexpected).
        _manifest = summary.get("manifest") or {}
        _manifest_status = _manifest.get("status")
        if _manifest_status:
            _final_status = _manifest_status
        emit_terminal_event(
            q.get("external_run_id"),
            _final_status,
            error_msg=summary.get("error"),
        )

    set_current_run_id(None)
    set_reasoning_sink(None)  # I-gen-004 (#496): release the run-scoped sink

    log_f.close()
    return summary


async def main_async() -> int:
    """CLI entry. Supports --only <slug> to run a single query and
    --out-root <path> to override the output directory. Documented in
    docs/runbook.md."""
    import argparse
    parser = argparse.ArgumentParser(
        description="POLARIS pipeline A — 8-query honest-rebuild sweep.",
    )
    parser.add_argument(
        "--only", type=str, default=None,
        help="Run only the query with this slug. Default: all 8.",
    )
    parser.add_argument(
        "--out-root", type=str, default=None,
        help="Output directory root. Default: outputs/honest_sweep_r3",
    )
    parser.add_argument(
        "--pathB-gate", action="store_true",
        help=(
            "I-safety-002b (#925): enable the Path-B DR head-to-head benchmark gate. "
            "Per question: preflight (full-power env + reachability + no fallbacks), "
            "capture every generator+evaluator LLM completion, then assert_post_run "
            "(served-model match + retrieval-backends actually attempted) BEFORE any "
            "scoring. Persists pathB_gate_pin.json + pathB_gate_result.json to run_dir."
        ),
    )
    parser.add_argument(
        "--replay-from-pin", type=str, default=None,
        help=(
            "M-INT-0b: load a captured ModelPin from <path> and apply "
            "its env-mutation plan before running the sweep. The "
            "pin's env_snapshot is restored under a context manager "
            "so the host environment is unaffected after the sweep "
            "exits. Use to reproduce a prior sweep run."
        ),
    )
    args = parser.parse_args()

    # M-INT-0b: --replay-from-pin handler. Build the replay plan
    # from the captured pin and apply it via the
    # `apply_replay_plan` context manager so the env mutation is
    # scoped + reversible.
    replay_pin_obj: ModelPin | None = None
    if args.replay_from_pin:
        replay_path = Path(args.replay_from_pin)
        if not replay_path.exists():
            print(f"ERROR: --replay-from-pin path not found: {replay_path}")
            return 2
        try:
            replay_pin_obj = pin_from_json(replay_path.read_text(encoding="utf-8"))
        except Exception as exc:
            print(f"ERROR: --replay-from-pin: malformed pin at {replay_path}: {exc}")
            return 2
        print(f"[M-INT-0b] Loaded replay pin from {replay_path}")
        print(f"[M-INT-0b] pin run_id={replay_pin_obj.run_id} "
              f"models={replay_pin_obj.llm_models}")

    if args.out_root:
        out_root = Path(args.out_root)
    else:
        out_root = ROOT / "outputs" / "honest_sweep_r3"
    out_root.mkdir(parents=True, exist_ok=True)

    queries_to_run = SWEEP_QUERIES
    if args.only:
        queries_to_run = [q for q in SWEEP_QUERIES if q["slug"] == args.only]
        if not queries_to_run:
            available = [q["slug"] for q in SWEEP_QUERIES]
            print(f"ERROR: --only {args.only!r} not found. Available slugs:")
            for s in available:
                print(f"  {s}")
            return 2

    print("=" * 72)
    if args.only:
        print(f"R-3 SINGLE-QUERY RUN — slug={args.only}")
    else:
        print("R-3 CROSS-DOMAIN SWEEP — 8 queries across 4 domains")
    print(f"Output root: {out_root}")
    if replay_pin_obj is not None:
        print(f"REPLAY MODE — applying pin {replay_pin_obj.run_id}")
    print("=" * 72)
    print()

    # M-INT-0b: enter replay context if a pin was loaded.
    # apply_replay_plan returns a context manager that restores
    # the prior env snapshot on exit, so this whole sweep is
    # scoped + reversible. Use manual __enter__/__exit__ so we
    # don't have to re-indent the existing sweep loop body.
    from contextlib import nullcontext
    if replay_pin_obj is not None:
        replay_plan = build_replay_plan(replay_pin_obj)
        replay_ctx_mgr = apply_replay_plan(replay_plan)
    else:
        replay_ctx_mgr = nullcontext()

    # M-INT-2: pre-sweep cache warming. Pulls a canonical-URL
    # list from each query (when defined) and warms the cache so
    # subsequent live-retrieval calls skip duplicate fetches.
    # Best-effort — failure logged, sweep proceeds.
    sweep_warm_summary: dict | None = None
    canonical_urls: list[str] = []
    for q in queries_to_run:
        for u in (q.get("canonical_urls") or []):
            if isinstance(u, str) and u not in canonical_urls:
                canonical_urls.append(u)
    if canonical_urls:
        sweep_warm_summary = _warm_canonical_corpus(
            workspace_id="sweep",
            canonical_urls=canonical_urls,
            out_root=out_root,
        )
        if sweep_warm_summary is not None:
            print(
                f"[M-INT-2] cache_warming: fetched="
                f"{sweep_warm_summary['fetched_count']} "
                f"skipped={sweep_warm_summary['skipped_count']} "
                f"errored={sweep_warm_summary['errored_count']}"
            )

        # M-INT-3: post-warm freshness check.
        sweep_freshness_summary = _check_corpus_freshness(
            workspace_id="sweep",
            canonical_urls=canonical_urls,
            out_root=out_root,
        )
        if sweep_freshness_summary is not None:
            per_status_counts = ", ".join(
                f"{status}={count}"
                for status, count in sweep_freshness_summary["per_status"].items()
            )
            print(
                f"[M-INT-3] sweep_freshness_summary: total_checked="
                f"{sweep_freshness_summary['total_checked']} "
                f"per_status={{{per_status_counts}}} "
                f"evicted_count={sweep_freshness_summary['evicted_count']}"
            )

    # M-INT-7: sweep-level billing quota check + consume.
    # Charges one AUDIT_RUN_ENQUEUED unit per sweep invocation
    # (not per query — the sweep is the unit of work).
    # Per LAW II — wrap in try/except for defense-in-depth.
    #
    # Codex round-2 MEDIUM fix (v3): only consume quota when
    # there's actual work to bill for. v1+v2 consumed
    # unconditionally; an empty sweep (e.g. --only matched no
    # slugs, or SWEEP_QUERIES=[]) burned one unit per invocation.
    # Codex repro: cap=1 + SWEEP_QUERIES=[] → first empty sweep
    # returned rc=0 but used the unit; second empty sweep was
    # then refused. Fix: skip the helper entirely when
    # queries_to_run is empty.
    if not queries_to_run:
        print(
            "[M-INT-7] billing_quota: skipped (no queries to run; "
            "no charge incurred)"
        )
        billing_summary = None
    else:
        try:
            billing_summary = _check_audit_run_quota()
        except Exception as exc:  # noqa: BLE001
            print(f"[M-INT-7] WARN: billing quota helper raised: {exc}")
            billing_summary = None
    if billing_summary is not None:
        if billing_summary.get("exceeded"):
            # Codex round-1 HIGH fix (v2): EXCEEDED must GATE
            # the sweep, not just log. Per FINAL_PLAN M-INT-7:
            # "M-NEW billing/quota gates production". v1 only
            # printed the EXCEEDED line and continued to run
            # queries — Codex repro: exhausted quota + stubbed
            # run_one_query showed the loop still executed.
            # v2 returns rc=2 before the query loop, writing a
            # quota-refusal sweep summary so callers can detect
            # the refusal.
            print(
                f"[M-INT-7] billing_quota: EXCEEDED "
                f"org={billing_summary['org_id']} "
                f"reason={billing_summary.get('reason', '<n/a>')!r}"
            )
            print(
                "[M-INT-7] sweep refused: org over quota; "
                "no queries executed"
            )
            try:
                refusal_summary = {
                    "status": "abort_quota_exceeded",
                    "billing_quota": billing_summary,
                    "queries_attempted": 0,
                    "out_root": str(out_root),
                }
                refusal_path = out_root / "sweep_quota_refusal.json"
                refusal_path.parent.mkdir(parents=True, exist_ok=True)
                refusal_path.write_text(
                    json.dumps(refusal_summary, indent=2, sort_keys=True)
                    + "\n",
                    encoding="utf-8",
                )
            except Exception as exc:  # noqa: BLE001
                # Best-effort artifact write — don't gate on FS errors.
                print(
                    f"[M-INT-7] WARN: refusal summary write failed: {exc}"
                )
            return 2
        print(
            f"[M-INT-7] billing_quota: "
            f"org={billing_summary['org_id']} "
            f"used={billing_summary['used']} "
            f"cap={billing_summary['cap']} "
            f"remaining={billing_summary['remaining']}"
        )

    all_summaries: list[dict] = []
    replay_ctx_mgr.__enter__()
    sweep_exc_info: tuple | None = None
    try:
        for q in queries_to_run:
            print(f"\n>>> {q['domain']} / {q['slug']}")
            t0 = time.time()
            # I-safety-002b (#925) PR-2: wrap each question's run with the Path-B gate
            # (preflight + capture + assert_post_run). No-op when --pathB-gate is off.
            _pathb_run_dir = out_root / q["domain"] / q["slug"]
            _pathb_run_dir.mkdir(parents=True, exist_ok=True)
            from src.polaris_graph.benchmark.pathB_runner import gate_around_question
            with gate_around_question(
                enabled=args.pathB_gate, run_dir=_pathb_run_dir,
            ):
                summary = await run_one_query(q, out_root)
            dt = time.time() - t0
            summary["wall_time_seconds"] = round(dt, 1)
            # M-INT-0b: capture a ModelPin for every run so later
            # replays can reproduce the exact runtime configuration.
            # Best-effort — failure does NOT gate the sweep summary.
            run_dir = Path(summary.get("run_dir", out_root))
            run_id = summary.get("run_id", "unknown")
            pin_path = _capture_run_pin(
                run_id, run_dir,
                notes=f"sweep {q['domain']}/{q['slug']} status={summary['status']}",
            )
            if pin_path is not None:
                summary["model_pin_path"] = str(pin_path)
            all_summaries.append(summary)
            print(f"<<< status={summary['status']} cost=${summary.get('cost_usd', 0):.4f} "
                  f"wall={dt:.1f}s\n")
    finally:
        replay_ctx_mgr.__exit__(None, None, None)

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
        j = m["judge_verdicts"] if "judge_verdicts" in m else m.get("qwen_verdicts", {})
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
