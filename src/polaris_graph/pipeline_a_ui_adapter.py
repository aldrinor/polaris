"""
pipeline_a_ui_adapter — BUG-B-102 R2c (pipeline-B UI parity via pipeline-A).

The Docker default `serve` path (scripts/live_server.py → FastAPI) has
three legacy graph variants (v1/v2/v3) that do NOT enforce any of the
5-round pipeline-A hardening (strict_verify, corpus_approval,
delimiter sanitization, abort statuses, two-family evaluator).
Codex full-audit pass 1 flagged this as a blocker (B-102).

v4 is a thin shim: it accepts the v1/v2/v3 UI signature, synthesizes a
pipeline-A query dict, calls `scripts.run_honest_sweep_r3.run_one_query`
(the battle-tested, 10+ rounds-hardened orchestrator), then adapts the
pipeline-A manifest + report into the UI's JSON contract at
`outputs/polaris_graph/{vector_id}.json`.

Trace events (`pipeline_start`, `report_assembled`, `pipeline_end`)
are emitted through the existing PipelineTracer so the live_server
SSE endpoint keeps working without frontend changes.

Design choices:
- No refactor of run_one_query. Call it as-is with a synthesized `q`.
- Domain inference: if the caller's `application` field matches a known
  domain key, use it; else default to "custom" (see R2b scope template).
- No forced amplification — UI queries come in raw; the retriever will
  do whatever query amplification it normally does.
- Pipeline-A artifacts go to a run directory; a pointer is added to
  the UI JSON so consumers can drill down.
"""
from __future__ import annotations

import asyncio
import datetime
import json
import logging
import os
import re
import time
from pathlib import Path
from typing import Any, Callable, Optional

_DOC_ID_RE = re.compile(r"[a-f0-9]{16}")


def _load_uploaded_documents(
    document_ids: list[str], ingester: Any = None, chunk_size: int = 1500,
) -> list[dict]:
    """Load chunks for given document_ids from DocumentIngester.

    Per I-f3-001. Validates each doc_id against 16-hex format (matches
    `hashlib.sha256(file_bytes).hexdigest()[:16]` per document_ingester.py:162)
    BEFORE filesystem lookup to prevent path traversal. Skips invalid /
    missing IDs with a logged warning. Raises RuntimeError if every
    requested ID failed (LAW II — fail loud).
    """
    if not document_ids:
        return []
    if ingester is None:
        from src.polaris_graph.document_ingester import DocumentIngester
        ingester = DocumentIngester()
    out: list[dict] = []
    for doc_id in document_ids:
        if not _DOC_ID_RE.fullmatch(doc_id):
            logger.warning("[v4 graph] invalid doc_id format: %r", doc_id)
            continue
        doc = ingester.get_document(doc_id)
        if doc is None:
            logger.warning("[v4 graph] doc_id %s not found", doc_id)
            continue
        content = doc.get("content", "")
        if not content:
            logger.warning("[v4 graph] doc_id %s has empty content", doc_id)
            continue
        meta = doc.get("metadata", {})
        name = meta.get("original_filename") or meta.get("filename") or doc_id
        chunks = [content[i : i + chunk_size] for i in range(0, len(content), chunk_size)]
        for idx, chunk_text in enumerate(chunks):
            out.append({
                "document_id": doc_id, "filename": name,
                "chunk_index": idx, "text": chunk_text,
            })
    if not out:
        raise RuntimeError(
            f"_load_uploaded_documents: every requested document_id "
            f"({len(document_ids)} ids) failed to resolve"
        )
    return out


logger = logging.getLogger(__name__)


_DOMAIN_HINTS = {
    "clinical": "clinical",
    "medical": "clinical",
    "pharma": "clinical",
    "health": "clinical",
    "tech": "tech",
    "technology": "tech",
    "software": "tech",
    "ai": "tech",
    "ml": "tech",
    "policy": "policy",
    "regulation": "policy",
    "regulatory": "policy",
    "due_diligence": "due_diligence",
    "dd": "due_diligence",
    "finance": "due_diligence",
    "investment": "due_diligence",
}


def _infer_domain(application: str, query: str) -> str:
    """Return a scope-template domain. Default to 'custom' for
    free-form UI queries that don't hint at clinical/tech/policy/dd."""
    a = (application or "").lower()
    if a in _DOMAIN_HINTS:
        return _DOMAIN_HINTS[a]
    q = (query or "").lower()
    for key, dom in _DOMAIN_HINTS.items():
        if key in q:
            return dom
    return "custom"


def _safe_load_json(path: Path) -> dict[str, Any]:
    """Best-effort JSON load; empty dict if missing / malformed."""
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _adapt_pipeline_a_to_ui_json(
    summary: dict[str, Any],
    vector_id: str,
    run_dir: Path,
) -> dict[str, Any]:
    """Convert pipeline-A's summary + on-disk artifacts into the JSON
    shape live_server.py reads at
    `outputs/polaris_graph/{vector_id}.json`."""
    manifest = summary.get("manifest", {}) or _safe_load_json(
        run_dir / "manifest.json"
    )
    report_md_path = run_dir / "report.md"
    report_md = (
        report_md_path.read_text(encoding="utf-8")
        if report_md_path.exists() else ""
    )
    biblio = _safe_load_json(run_dir / "bibliography.json")
    contradictions = _safe_load_json(run_dir / "contradictions.json")

    # Pipeline-A manifest.status is the single authoritative verdict.
    status = manifest.get("status", summary.get("status", "unknown"))

    # UI expects certain fields — populate defensively. Downstream
    # consumers that use `manifest.status` are routed through
    # pipeline-A's unified taxonomy (see UNIFIED_STATUS_VALUES).
    return {
        "vector_id": vector_id,
        "original_query": summary.get("question", ""),
        "status": status,
        # BUG-M-205: release-gating flag surfaced for UI
        "release_allowed": manifest.get("release_allowed", status == "success"),
        "final_report": report_md,
        "bibliography": biblio if isinstance(biblio, list) else [],
        "contradictions": contradictions if isinstance(contradictions, list) else [],
        "quality_metrics": {
            "total_words": manifest.get("generator", {}).get("words", 0),
            "sentences_verified": manifest.get("generator", {}).get("sentences_verified", 0),
            "sentences_dropped": manifest.get("generator", {}).get("sentences_dropped", 0),
            "sections_kept": manifest.get("generator", {}).get("sections_kept", 0),
        },
        "evaluator_gate": manifest.get("evaluator_gate", {}),
        "evidence_selection": manifest.get("evidence_selection", {}),
        "cost_usd": manifest.get("cost_usd", 0.0),
        "budget_cap_usd": manifest.get("budget_cap_usd", 5.0),
        "run_dir": str(run_dir),
        "graph_version": "v4",
        "timestamps": {
            "completed": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        },
    }


async def build_and_run_v4(
    vector_id: str,
    query: str,
    application: str = "",
    region: str = "",
    stage: int = 1,
    max_iterations: int = 3,
    max_execution_minutes: int = 60,
    resume: bool = False,
    enable_dashboard: bool = True,
    document_ids: Optional[list[str]] = None,
    steer_callback: Optional[Callable] = None,
    research_brief: str = "",
) -> dict[str, Any]:
    """Pipeline-B UI entry via pipeline-A. Signature matches v1/v2/v3
    for live_server compatibility.

    Returns a dict with at least `status` so the caller's existing
    status-routing code keeps working. The full UI JSON is written
    to `outputs/polaris_graph/{vector_id}.json` as a side effect
    (matches the v1/v2/v3 convention).
    """
    # Deferred import: scripts.run_honest_sweep_r3 imports heavy pipeline-A
    # modules; deferring keeps graph_v4 import cheap.
    from scripts.run_honest_sweep_r3 import run_one_query

    started_at = datetime.datetime.now(datetime.timezone.utc)
    domain = _infer_domain(application, query)

    # Initialize tracer (same pattern as v3). The live_server SSE
    # tailer watches logs/pg_trace_{vector_id}.jsonl.
    tracer = None
    try:
        from src.polaris_graph.tracing import PipelineTracer
        tracer = PipelineTracer(vector_id)
        tracer.log_event("pipeline_start", data={
            "query": query,
            "application": application,
            "region": region,
            "vector_id": vector_id,
            "graph_version": "v4",
            "domain": domain,
            "pipeline_a_backed": True,
        })
    except Exception as exc:
        logger.warning("[v4 graph] Tracer init failed: %s", str(exc)[:100])

    # Synthesize pipeline-A `q` dict.
    q = {
        "slug": vector_id,
        "domain": domain,
        "question": query,
        "amplified": [],  # pipeline A's retriever amplifies on its own
    }
    if document_ids:  # truthy: handles None and []
        q["uploaded_documents"] = _load_uploaded_documents(document_ids)

    # Run directory for pipeline-A artifacts.
    out_root = Path(os.getenv(
        "PG_V4_OUT_ROOT", "outputs/polaris_graph_v4_runs",
    ))
    out_root.mkdir(parents=True, exist_ok=True)
    expected_run_dir = out_root / domain / vector_id

    # Delegate to pipeline A.
    try:
        summary = await run_one_query(q, out_root)
    except Exception as exc:
        logger.error(
            "[v4 graph] run_one_query raised: %s", exc, exc_info=True,
        )
        # Emit a synthetic error result matching UI contract.
        ui_json = {
            "vector_id": vector_id,
            "original_query": query,
            "status": "error_unexpected",
            "release_allowed": False,
            "final_report": "",
            "bibliography": [],
            "contradictions": [],
            "quality_metrics": {},
            "evaluator_gate": {},
            "evidence_selection": {},
            "cost_usd": 0.0,
            "budget_cap_usd": 5.0,
            "run_dir": str(expected_run_dir),
            "graph_version": "v4",
            "error": str(exc)[:500],
            "timestamps": {
                "started": started_at.isoformat(),
                "completed": datetime.datetime.now(
                    datetime.timezone.utc,
                ).isoformat(),
            },
        }
        _write_ui_json(vector_id, ui_json)
        if tracer:
            tracer.log_event("pipeline_end", data={
                "status": "error_unexpected", "error": str(exc)[:200],
            })
        return {"status": "error_unexpected", "error": str(exc)[:500]}

    # Summary is from pipeline-A; the actual run_dir is inside it.
    run_dir = Path(summary.get("run_dir", str(expected_run_dir)))

    # Emit report_assembled event if we produced a report.
    if tracer:
        manifest_status = summary.get("manifest", {}).get(
            "status", summary.get("status", ""),
        )
        is_content_report = (
            manifest_status == "success"
            or manifest_status.startswith("partial_")
        )
        tracer.log_event("report_assembled", data={
            "status": manifest_status,
            "is_content_report": is_content_report,
            "has_pipeline_verdict_artifact": manifest_status.startswith("abort_")
            or manifest_status.startswith("error_"),
        })

    # Adapt pipeline-A output into UI JSON.
    ui_json = _adapt_pipeline_a_to_ui_json(summary, vector_id, run_dir)
    _write_ui_json(vector_id, ui_json)

    if tracer:
        tracer.log_event("pipeline_end", data={
            "status": ui_json["status"],
            "release_allowed": ui_json["release_allowed"],
            "cost_usd": ui_json["cost_usd"],
        })

    return {
        "status": ui_json["status"],
        "release_allowed": ui_json["release_allowed"],
        "run_dir": str(run_dir),
        "graph_version": "v4",
    }


def _write_ui_json(vector_id: str, data: dict[str, Any]) -> None:
    """Write the UI-shape JSON to the path live_server.py reads.
    Uses a tmp + rename pattern so a reader never sees a half-written file."""
    out_dir = Path("outputs/polaris_graph")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{vector_id}.json"
    tmp_path = out_dir / f"{vector_id}.json.tmp"
    tmp_path.write_text(
        json.dumps(data, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    os.replace(tmp_path, out_path)
