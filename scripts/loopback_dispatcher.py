"""Phase 2: Tiered loopback dispatcher.

Replaces loopback_auto_universal.py with explicit classification:
- Tier A: auto-served with schema-valid templates (query gen, dedup, simple schemas)
- Tier B: surfaced to operator (source analysis, clustering, verification)
- Tier C: surfaced to operator (outline, compose, remediation)

Design principles:
- No silent skips. Every pending request is classified and logged.
- Schema-validated responses (Pydantic) before write. Invalid → keep pending.
- Atomic response write: .tmp → fsync → rename.
- One-line stdout banner per Tier B/C call.
- Shape-drift log: every Tier A template write records template_fingerprint
  for Phase 8 comparison against real GLM-5.1 output.

Usage: python scripts/loopback_dispatcher.py
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import random
import signal
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

from dotenv import load_dotenv
load_dotenv(override=False)

LOOPBACK_DIR = Path(os.getenv("PG_LOOPBACK_DIR", "loopback"))
PENDING_DIR = LOOPBACK_DIR / "pending"
RESPONSES_DIR = LOOPBACK_DIR / "responses"
DONE_DIR = LOOPBACK_DIR / "done"
SHAPE_DRIFT_LOG = LOOPBACK_DIR / "shape_drift.jsonl"
OPERATOR_QUEUE_LOG = LOOPBACK_DIR / "operator_queue.jsonl"

for d in (PENDING_DIR, RESPONSES_DIR, DONE_DIR):
    d.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# ───────────────────────────── Classification ─────────────────────────

# Tier A: schema name → template generator (name, generator)
# Tier B/C: schema name in these sets → surface to operator
TIER_B_SCHEMAS = {
    "SourceAnalysisBatch",
    "EvidenceCardBatch",
    "StructuredDataExtraction",
    "PageSummaryBatch",
    "AgenticRoundAnalysis",
    "VerificationBatch",
    "GlobalEvidenceAssignment",
    "ClusterAssessment",
    "BatchClusterResult",
    "ClusterPlan",
    "GapAnalysis",
    "ScopeOutput",
    "StormOutlinePlan",
    "QuestionDecomposition",
}

TIER_C_SCHEMAS = {
    "ReportOutline",
}

# Unstructured generate/reason — routed by call_type + prompt content
# "generate" with COMPOSE_SYSTEM → Tier C (section compose / remediation)
# "generate" with "abstract" system → Tier C (abstract)
# "reason" low effort → usually Tier B


# ───────────────────────────── Tier A templates ────────────────────────

def _seed_from_prompt(prompt: str, system: str) -> int:
    """Deterministic seed based on prompt hash — same request same response."""
    h = hashlib.sha256((prompt + system).encode("utf-8", errors="ignore")).hexdigest()
    return int(h[:8], 16)


def _tmpl_query_plan(prompt: str, system: str) -> dict:
    """QueryPlan — 20 queries distributed across 9 STORM perspectives."""
    random.seed(_seed_from_prompt(prompt, system))
    perspectives = [
        "Scientific", "Regulatory", "Industry", "Economic",
        "Public_Health", "Historical", "Regional",
        "Methodological", "Emerging_Trends",
    ]
    topic_bits = [w for w in prompt.split()[:30] if len(w) > 3 and w.isalpha()]
    topic = " ".join(topic_bits[:6]) or "research topic"
    queries = []
    for i in range(20):
        p = perspectives[i % len(perspectives)]
        modifier = {
            "Scientific": "systematic review meta-analysis",
            "Regulatory": "FDA EFSA regulatory guidance",
            "Industry": "commercial market report datasheet",
            "Economic": "cost-effectiveness QALY economic analysis",
            "Public_Health": "WHO CDC population-level outcomes",
            "Historical": "foundational study evolution of knowledge",
            "Regional": "country-specific geographic comparison",
            "Methodological": "study design risk of bias GRADE",
            "Emerging_Trends": "preprint 2024 novel technique",
        }[p]
        queries.append({
            "query": f"{topic} {modifier}".strip(),
            "intent": f"Find {p.lower()} evidence on the research question",
            "source_preference": "academic" if p in ("Scientific", "Methodological") else "both",
            "perspective": p,
        })
    return {
        "analysis": f"Decompose research question into multi-perspective queries for: {topic[:60]}",
        "search_strategy": "broad",
        "sub_queries": queries,
        "key_concepts": topic_bits[:10],
        "expected_source_types": ["journal_article", "regulatory", "industry_report", "meta_analysis"],
    }


def _tmpl_seed_query_plan(prompt: str, system: str) -> dict:
    """SeedQueryPlan — fallback planner: minimal query list."""
    plan = _tmpl_query_plan(prompt, system)
    # SeedQueryPlan typically wraps sub_queries in a simpler shape — provide both
    return {"queries": [q["query"] for q in plan["sub_queries"]], **plan}


def _tmpl_search_refinement(prompt: str, system: str) -> dict:
    """SearchRefinement — refine failing queries. Schema: refined queries + rationale."""
    random.seed(_seed_from_prompt(prompt, system))
    base = " ".join(prompt.split()[:6])
    return {
        "refined_queries": [
            f"{base} meta-analysis",
            f"{base} systematic review",
            f"{base} randomized controlled trial",
        ],
        "rationale": "Broaden to include review-level evidence; drop overly specific modifiers.",
    }


def _tmpl_storm_persona_batch(prompt: str, system: str) -> dict:
    """StormPersonaBatch — schema requires personas with perspective, name,
    expertise, question_focus (NOT role/description/key_questions).

    Validated schema from P5 live run:
      StormPersona { perspective, name, expertise, question_focus }
      StormPersonaBatch { personas: [StormPersona] }
    """
    personas = []
    for perspective, name, expertise, focus in [
        ("Scientific", "Dr. A. Researcher", "Randomized-trial evidence synthesis and clinical endpoint evaluation relevant to the research question.", "Effect sizes from RCTs and meta-analyses with confidence intervals."),
        ("Regulatory", "Dr. B. Agency", "Regulatory-science evidence evaluation under FDA/EFSA/Health Canada claim-substantiation frameworks.", "Evidence thresholds and adverse-event signals that trigger consumer advisories."),
        ("Industry", "Dr. C. Practitioner", "Translating dietary or intervention evidence into consumer products and behavioral-coaching programs.", "Real-world adherence, retention, and effect sizes vs peer-reviewed magnitudes."),
        ("Economic", "Dr. D. Economist", "Cost-effectiveness modeling and QALY analysis for preventive interventions.", "ICERs, QALYs, and opportunity cost vs other interventions."),
        ("Public_Health", "Dr. E. Clinician", "Population-level dietary guidance and primary-care counseling across diverse populations.", "Contraindications, adverse events, and equity of applicability."),
    ]:
        personas.append({
            "perspective": perspective,
            "name": name,
            "expertise": expertise,
            "question_focus": focus,
        })
    return {"personas": personas}


def _tmpl_storm_question(prompt: str, system: str) -> dict:
    """StormQuestion — schema requires question, search_queries, perspective
    (NOT persona_role, follow_up_indicator).

    Validated schema from P5 live run:
      StormQuestion { question, search_queries[], perspective }
    """
    # Pull the persona's perspective from the prompt if declared
    perspective = "Scientific"
    import re as _re
    m = _re.search(r"Your perspective:\s*(\w+)", prompt)
    if m:
        perspective = m.group(1)
    return {
        "question": "What does the existing evidence show about effectiveness, magnitude, and limitations of the studied intervention compared to standard approaches?",
        "search_queries": [
            "effectiveness randomized controlled trial systematic review",
            "meta-analysis effect size confidence interval",
            "adverse events safety contraindications",
            "real-world adherence retention long-term outcomes",
            "comparison with standard care continuous intervention",
        ],
        "perspective": perspective,
    }


def _tmpl_storm_answer(prompt: str, system: str) -> dict:
    """StormAnswer — schema requires answer, key_findings, sources_used
    (NOT evidence_ids, confidence).

    Validated schema from P5 live run:
      StormAnswer { answer, key_findings[], sources_used[] }
    """
    return {
        "answer": (
            "The retrieved sources were not parsed into specific quantitative findings by the auto-template responder. "
            "A full evidence-grounded answer requires the operator LLM to read the provided search results and extract "
            "numeric effect estimates, confidence intervals, and methodological caveats."
        ),
        "key_findings": [
            "Auto-template response: specific findings require operator serving.",
        ],
        "sources_used": [],
    }


def _tmpl_disambig(prompt: str, system: str) -> dict:
    """DisambigResponse — entity disambiguation."""
    return {"entity_id": "", "confidence": 0.5, "rationale": "Ambiguous reference; deferring to context."}


def _tmpl_sql_query(prompt: str, system: str) -> dict:
    """SQLQuery — generate a DB query."""
    return {"sql": "SELECT * FROM evidence WHERE 1=1 LIMIT 0", "rationale": "Default no-op query."}


TIER_A_TEMPLATES = {
    "QueryPlan": _tmpl_query_plan,
    "SeedQueryPlan": _tmpl_seed_query_plan,
    "SearchRefinement": _tmpl_search_refinement,
    "StormPersonaBatch": _tmpl_storm_persona_batch,
    "StormQuestion": _tmpl_storm_question,
    "StormAnswer": _tmpl_storm_answer,
    "DisambigResponse": _tmpl_disambig,
    "SQLQuery": _tmpl_sql_query,
}


# ───────────────────────────── Core dispatcher ─────────────────────────

def classify(req: dict) -> tuple[str, str]:
    """Return (tier, reason). tier ∈ {'A', 'B', 'C'}."""
    schema = req.get("schema_name") or ""
    call_type = req.get("call_type", "")
    system = req.get("system", "") or ""
    prompt = req.get("prompt", "") or ""

    if schema in TIER_A_TEMPLATES:
        return "A", f"tier-A template for schema={schema}"
    if schema in TIER_C_SCHEMAS:
        return "C", f"tier-C schema={schema}"
    if schema in TIER_B_SCHEMAS:
        return "B", f"tier-B schema={schema}"
    if schema:
        return "B", f"unknown schema={schema} defaulting to tier-B operator"

    # Unstructured generate — inspect call_type + system/prompt content
    if call_type == "generate":
        sl = (system or "").lower()
        pl = (prompt or "").lower()
        if "academic researcher" in sl or "200-word abstract" in pl:
            return "C", "abstract compose"
        if "systematic review" in pl and "write section" in pl.lower():
            return "C", "section compose"
        if "remediation" in pl.lower() or "unsupported" in pl.lower():
            return "C", "section remediation re-compose"
        return "B", "unstructured generate (default tier-B operator)"
    if call_type.startswith("reason"):
        return "B", "reason call (default tier-B operator)"

    return "B", "default tier-B operator"


def _atomic_write(path: Path, data: dict) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.flush()
        try:
            os.fsync(f.fileno())
        except OSError:
            pass  # Windows sometimes rejects fsync on normal files
    os.replace(tmp, path)


def _validate_template(schema_name: str, obj: dict) -> tuple[bool, str]:
    """Validate a template response against the real Pydantic schema.

    Scans pg_schemas, claim_extract, and storm_interviews modules for the
    named class (STORM schemas live in storm_interviews, not pg_schemas).
    """
    _candidate_modules = [
        "src.polaris_graph.schemas",
        "src.polaris_graph.wiki.mesh.claim_extract",
        "src.polaris_graph.agents.storm_interviews",
    ]
    cls = None
    last_err = ""
    for modname in _candidate_modules:
        try:
            import importlib
            mod = importlib.import_module(modname)
            cand = getattr(mod, schema_name, None)
            if cand is not None:
                cls = cand
                break
        except Exception as exc:
            last_err = str(exc)
    if cls is None:
        return False, f"schema class {schema_name} not found (last import error: {last_err})"

    try:
        cls.model_validate(obj)
        return True, "OK"
    except Exception as exc:
        return False, f"validation failed: {str(exc)[:200]}"


def _log_shape_drift(req_id: str, schema: str, fingerprint: str, obj: dict) -> None:
    """Append a shape-drift record for Phase 8 comparison."""
    entry = {
        "ts": time.time(),
        "req_id": req_id,
        "schema": schema,
        "template_fingerprint": fingerprint,
        "response_keys": list(obj.keys())[:20],
    }
    with open(SHAPE_DRIFT_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def _log_operator_queue(req_id: str, tier: str, schema: str, reason: str, prompt_head: str) -> None:
    entry = {
        "ts": time.time(),
        "req_id": req_id,
        "tier": tier,
        "schema": schema,
        "reason": reason,
        "prompt_head": prompt_head[:160],
    }
    with open(OPERATOR_QUEUE_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


async def serve_tier_a(req: dict, req_path: Path) -> bool:
    """Auto-serve a Tier A request. Returns True if served successfully."""
    schema = req.get("schema_name", "")
    req_id = req.get("request_id", req_path.stem.replace("req_", ""))

    generator = TIER_A_TEMPLATES[schema]
    obj = generator(req.get("prompt", ""), req.get("system", ""))

    ok, msg = _validate_template(schema, obj)
    if not ok:
        logger.warning("[TIER A] schema=%s template rejected: %s. Leaving pending.", schema, msg)
        return False

    fingerprint = hashlib.sha256(
        json.dumps(obj, sort_keys=True).encode("utf-8")
    ).hexdigest()[:12]
    _log_shape_drift(req_id, schema, fingerprint, obj)

    response = {
        "content": json.dumps(obj, ensure_ascii=False),
        "reasoning": "",
        "input_tokens": max(1, len(req.get("prompt", "")) // 4),
        "output_tokens": max(1, len(json.dumps(obj)) // 4),
        "_template_fingerprint": fingerprint,
    }
    resp_path = RESPONSES_DIR / f"resp_{req_id}.json"
    _atomic_write(resp_path, response)
    logger.info("[TIER A] served req_%s schema=%s fingerprint=%s", req_id, schema, fingerprint)
    return True


def announce_operator(req: dict, req_path: Path, tier: str, reason: str) -> None:
    """Print an operator-visible banner for Tier B/C calls."""
    req_id = req.get("request_id", req_path.stem.replace("req_", ""))
    schema = req.get("schema_name") or "(unstructured)"
    call_type = req.get("call_type", "")
    prompt = req.get("prompt", "")

    _log_operator_queue(req_id, tier, schema, reason, prompt)

    banner = (
        f"\n{'='*72}\n"
        f"  OPERATOR NEEDED — TIER {tier}\n"
        f"  req_id:    {req_id}\n"
        f"  call_type: {call_type}\n"
        f"  schema:    {schema}\n"
        f"  reason:    {reason}\n"
        f"  prompt_head: {prompt[:160]}...\n"
        f"  file:      {req_path}\n"
        f"  To serve: inspect {req_path}, write loopback/responses/resp_{req_id}.json\n"
        f"{'='*72}\n"
    )
    print(banner, flush=True)
    logger.info("[TIER %s] OPERATOR req_%s schema=%s reason=%s", tier, req_id, schema, reason)


async def process_pending_once(seen: set[str]) -> int:
    """Scan pending/ once. Serve Tier A, announce Tier B/C. Return count processed."""
    count = 0
    for req_path in sorted(PENDING_DIR.glob("req_*.json")):
        if req_path.stem in seen:
            continue
        try:
            with open(req_path, encoding="utf-8") as f:
                req = json.load(f)
        except (json.JSONDecodeError, PermissionError, OSError):
            continue  # still being written; try next loop

        tier, reason = classify(req)

        if tier == "A":
            served = await serve_tier_a(req, req_path)
            if served:
                seen.add(req_path.stem)
                count += 1
            # if not served, leave pending (validator rejected) — operator can handle
            else:
                announce_operator(req, req_path, tier="B",
                                  reason=f"Tier A validator rejected: {reason}")
                seen.add(req_path.stem)
        else:
            announce_operator(req, req_path, tier=tier, reason=reason)
            seen.add(req_path.stem)
            count += 1
    return count


_shutdown = asyncio.Event()


def _handle_signal(signum, frame):
    logger.info("Signal %d received — initiating graceful shutdown", signum)
    _shutdown.set()


async def main() -> int:
    signal.signal(signal.SIGINT, _handle_signal)
    try:
        signal.signal(signal.SIGTERM, _handle_signal)
    except (AttributeError, ValueError):
        pass  # Windows

    poll_interval = float(os.getenv("PG_LOOPBACK_POLL_SEC", "1.0"))
    logger.info(
        "Loopback dispatcher ready. pending=%s responses=%s done=%s poll=%.1fs",
        PENDING_DIR, RESPONSES_DIR, DONE_DIR, poll_interval,
    )
    logger.info(
        "Tier A schemas: %s",
        ", ".join(sorted(TIER_A_TEMPLATES.keys())),
    )

    seen: set[str] = set()
    idle_ticks = 0
    while not _shutdown.is_set():
        n = await process_pending_once(seen)
        if n > 0:
            idle_ticks = 0
        else:
            idle_ticks += 1
            if idle_ticks % 30 == 0:
                logger.info("idle (%ds) — %d requests served so far", int(idle_ticks * poll_interval), len(seen))
        try:
            await asyncio.wait_for(_shutdown.wait(), timeout=poll_interval)
            break
        except asyncio.TimeoutError:
            continue

    logger.info("Dispatcher shutdown. Total classified: %d", len(seen))
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(asyncio.run(main()))
