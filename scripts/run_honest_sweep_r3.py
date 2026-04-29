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
    strict_verify,
)
from src.polaris_graph.llm.openrouter_client import (  # noqa: E402
    PG_MAX_COST_PER_RUN,
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
        env["retrieval"] = {
            "pre_filter": getattr(retrieval, "total_candidates_pre_filter", 0),
            "fetched": getattr(retrieval, "candidates_fetched", 0),
            "failed": getattr(retrieval, "candidates_failed_fetch", 0),
            "api_calls": getattr(retrieval, "api_calls", {}),
        }
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


async def run_one_query(
    q: dict,
    out_root: Path,
) -> dict:
    """Run the full honest pipeline on one query. Returns a summary dict."""
    reset_run_cost()

    run_dir = out_root / q["domain"] / q["slug"]
    run_dir.mkdir(parents=True, exist_ok=True)
    run_id = f"SWEEP_{q['domain']}_{q['slug']}_{int(time.time())}"
    # BUG-N-301 fix: set ambient run_id so every downstream
    # OpenRouterClient tags its cost-ledger entries with this run.
    set_current_run_id(run_id)

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
            (run_dir / "manifest.json").write_text(
                json.dumps(abort_manifest, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            summary["manifest"] = abort_manifest
            summary["cost_usd"] = run_cost
            try: write_per_run_cost_ledger(run_dir, run_id)
            except Exception: pass
            set_current_run_id(None)
            log_f.close()
            return summary

        # Live retrieval
        # Env-controllable retrieval width for full-scale runs:
        #   PG_SWEEP_MAX_SERPER  (default 8)   — number of amplified
        #     queries fanned to Serper
        #   PG_SWEEP_MAX_S2      (default 8)   — same to Semantic Scholar
        #   PG_SWEEP_FETCH_CAP   (default 20)  — max URLs to classify
        #     & fetch per query (after pre-filter)
        # Example full-scale: max_serper=20, max_s2=20, fetch_cap=200
        # → ~400 pre-filter candidates, 200 classified sources per query.
        _max_serper = int(os.getenv("PG_SWEEP_MAX_SERPER", "8"))
        _max_s2 = int(os.getenv("PG_SWEEP_MAX_S2", "8"))
        _fetch_cap = int(os.getenv("PG_SWEEP_FETCH_CAP", "20"))

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
        _amplified_effective = (
            list(q.get("amplified", [])) + _reg_queries + _trial_queries
        )

        t0 = time.time()
        retrieval = run_live_retrieval(
            research_question=q["question"],
            amplified_queries=_amplified_effective,
            protocol=protocol,
            max_serper=_max_serper,
            max_s2=_max_s2,
            fetch_cap=_fetch_cap,
            enable_openalex_enrich=True,
            enable_prefetch_filter=False,
            domain=q["domain"],   # R-6 Gap-2 domain backends
        )
        dt = time.time() - t0
        _log(f"[retrieval]   pre_filter={retrieval.total_candidates_pre_filter}, "
             f"fetched={retrieval.candidates_fetched}, "
             f"failed={retrieval.candidates_failed_fetch}, "
             f"elapsed={dt:.1f}s  api_calls={retrieval.api_calls}")

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
            (run_dir / "manifest.json").write_text(
                json.dumps(abort_manifest, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            summary["manifest"] = abort_manifest
            summary["cost_usd"] = run_cost
            try: write_per_run_cost_ledger(run_dir, run_id)
            except Exception: pass
            set_current_run_id(None)
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
            (run_dir / "manifest.json").write_text(
                json.dumps(manifest, indent=2, sort_keys=True, default=str) + "\n",
                encoding="utf-8",
            )
            summary["manifest"] = manifest
            summary["cost_usd"] = run_cost
            try: write_per_run_cost_ledger(run_dir, run_id)
            except Exception: pass
            set_current_run_id(None)
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
            (run_dir / "manifest.json").write_text(
                json.dumps(manifest, indent=2, sort_keys=True, default=str) + "\n",
                encoding="utf-8",
            )
            summary["manifest"] = manifest
            summary["cost_usd"] = run_cost
            try: write_per_run_cost_ledger(run_dir, run_id)
            except Exception: pass
            set_current_run_id(None)
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
        # BUG-M-201 fix (deep-dive R6): tier-balanced + relevance-ranked
        # selection instead of raw-order truncation. Previously the
        # generator saw evidence_rows[:20] in retrieval order, diverging
        # from what the gates certified.
        from src.polaris_graph.retrieval.evidence_selector import (
            select_evidence_for_generation,
        )
        max_ev = int(os.getenv("PG_LIVE_MAX_EV_TO_GEN", "20"))
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
        )
        evidence_for_gen = evidence_selection.selected_rows
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

        multi = await generate_multi_section_report(
            research_question=q["question"],
            evidence=evidence_for_gen,
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
            section_max_tokens=2400,
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
            (run_dir / "manifest.json").write_text(
                json.dumps(manifest, indent=2, sort_keys=True, default=str) + "\n",
                encoding="utf-8",
            )
            summary["manifest"] = manifest
            summary["cost_usd"] = run_cost
            try: write_per_run_cost_ledger(run_dir, run_id)
            except Exception: pass
            set_current_run_id(None)
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

        # BUG-M-2 diagnostic: re-run strict_verify on the preserved
        # rewritten_draft per section to capture the dropped-sentence
        # detail (sentence, failure_reasons, soft_warnings). The raw
        # StrictVerificationReport's `dropped_sentences` list isn't on
        # SectionResult, but strict_verify is pure computation so we
        # can reconstruct it here without an LLM call.
        ev_pool = {ev["evidence_id"]: ev for ev in evidence_for_gen}
        verif_details = {
            "sections": [],
            "totals": {
                "sentences_verified": multi.total_sentences_verified,
                "sentences_dropped": multi.total_sentences_dropped,
            },
        }
        for sr in multi.sections:
            if not sr.rewritten_draft:
                continue
            rpt = strict_verify(sr.rewritten_draft, ev_pool)
            verif_details["sections"].append({
                "title": sr.title,
                "dropped_due_to_failure": sr.dropped_due_to_failure,
                "total_in": rpt.total_in,
                "total_kept": rpt.total_kept,
                "total_dropped": rpt.total_dropped,
                "kept": [
                    {
                        "sentence": sv.sentence,
                        "tokens": [
                            {"evidence_id": t.evidence_id,
                             "start": t.start, "end": t.end}
                            for t in sv.tokens
                        ],
                        "soft_warnings": sv.soft_warnings,
                    }
                    for sv in rpt.kept_sentences
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
                    for sv in rpt.dropped_sentences
                ],
            })
        # Per-reason tally across all sections.
        reason_counts: dict[str, int] = {}
        for s in verif_details["sections"]:
            for d in s["dropped"]:
                for r in d["failure_reasons"]:
                    key = r.split(":", 1)[0]  # collapse parameterized detail
                    reason_counts[key] = reason_counts.get(key, 0) + 1
        verif_details["drop_reason_counts"] = reason_counts
        (run_dir / "verification_details.json").write_text(
            json.dumps(verif_details, indent=2, sort_keys=True, default=str) + "\n",
            encoding="utf-8",
        )

        # Evaluator rule checks
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
            # BUG-M-201: generator-visible evidence provenance.
            "evidence_selection": evidence_selection.to_dict(),
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
                from src.polaris_graph.v30_sweep_integration import (
                    append_disclosure_to_report,
                    merge_v30_into_manifest,
                    run_v30_post_generation,
                )
                # Phase 1 ships RETRIEVAL-coverage semantics only.
                # Legacy report / bibliography cross-check was
                # deprecated after three Codex audit rounds of
                # heuristic false-passes (see pass-4 scope narrow
                # in v30_sweep_integration module docstring).
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
                # in tests/polaris_graph/test_v30_sweep_integration.py).
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

    # BUG-M-206 + BUG-N-301 teardown: per-run ledger copy + run_id reset.
    try:
        n_ledger = write_per_run_cost_ledger(run_dir, run_id)
        summary["cost_ledger_entries"] = n_ledger
    except Exception as ledger_exc:
        logging.getLogger(__name__).warning(
            "per-run ledger copy failed: %s", ledger_exc
        )
    set_current_run_id(None)

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

    all_summaries: list[dict] = []
    replay_ctx_mgr.__enter__()
    sweep_exc_info: tuple | None = None
    try:
        for q in queries_to_run:
            print(f"\n>>> {q['domain']} / {q['slug']}")
            t0 = time.time()
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
