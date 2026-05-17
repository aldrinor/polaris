"""
BUG-B-102 regression tests: pipeline-B UI path parity via graph_v4.

Pre-fix: the Docker default `serve` entry routed to v1/v2/v3 graphs
which had ZERO pipeline-A hardening (no strict_verify, no corpus
approval enforcement, no delimiter sanitization, no unified manifest
status taxonomy).

Post-fix (R2b-R2g): graph_v4.py shim wraps pipeline-A's run_one_query.
live_server defaults PG_GRAPH_VERSION to v4. UI users now get:
  - strict_verify (B-1..B-5 hardened)
  - corpus_approval_gate (B-2)
  - scope_gate rejection (B-100)
  - unified manifest.status taxonomy (B-101)
  - delimiter breakout defense (B-5)
  - evaluator gate (M-205)
  - tier-balanced evidence selection (M-201)
  - per-run cost ledger (M-206)
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest


# ─────────────────────────────────────────────────────────────────
# 1. graph_v4 imports + signature compatibility with v1/v2/v3
# ─────────────────────────────────────────────────────────────────

def test_b102_graph_v4_importable_and_signature_matches() -> None:
    """build_and_run_v4 signature must be v1/v2/v3-compatible so
    live_server dispatch drops in without argument changes."""
    import inspect
    from src.polaris_graph.pipeline_a_ui_adapter import build_and_run_v4
    sig = inspect.signature(build_and_run_v4)
    params = set(sig.parameters.keys())
    # Minimum required for live_server compatibility
    required = {
        "vector_id", "query", "application", "region",
        "max_iterations", "max_execution_minutes",
    }
    missing = required - params
    assert not missing, f"build_and_run_v4 missing params: {missing}"


# ─────────────────────────────────────────────────────────────────
# 2. Domain inference from application/query hints
# ─────────────────────────────────────────────────────────────────

def test_b102_graph_v4_domain_inference() -> None:
    """Application/query hints route to known scope templates. Otherwise
    default to 'custom' (R2b)."""
    from src.polaris_graph.pipeline_a_ui_adapter import _infer_domain
    assert _infer_domain("clinical", "") == "clinical"
    assert _infer_domain("pharma", "") == "clinical"
    assert _infer_domain("tech", "") == "tech"
    assert _infer_domain("policy", "") == "policy"
    assert _infer_domain("due_diligence", "") == "due_diligence"
    # Free-form → custom
    assert _infer_domain("", "What is the best espresso machine?") == "custom"
    assert _infer_domain("home_goods", "vacuum cleaner review") == "custom"
    # Keyword in query
    assert _infer_domain("", "AI safety regulation in EU") in ("policy", "tech")


# ─────────────────────────────────────────────────────────────────
# 3. UI JSON adapter produces the shape live_server expects
# ─────────────────────────────────────────────────────────────────

def test_b102_graph_v4_ui_json_adapter_shape(tmp_path: Path) -> None:
    """_adapt_pipeline_a_to_ui_json produces fields the UI reads."""
    from src.polaris_graph.pipeline_a_ui_adapter import _adapt_pipeline_a_to_ui_json

    # Build a fake run_dir with a manifest + report
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    manifest = {
        "status": "success",
        "release_allowed": True,
        "generator": {
            "words": 1200, "sentences_verified": 42, "sentences_dropped": 3,
            "sections_kept": 3,
        },
        "cost_usd": 0.87,
        "budget_cap_usd": 5.00,
        "evaluator_gate": {"gate_class": "pass"},
        "evidence_selection": {"selection_strategy": "tier_balanced_v1"},
    }
    (run_dir / "manifest.json").write_text(json.dumps(manifest))
    (run_dir / "report.md").write_text("# Report\n\nFindings.")
    (run_dir / "bibliography.json").write_text(json.dumps([
        {"num": 1, "evidence_id": "ev_001", "url": "https://x", "tier": "T1"},
    ]))
    (run_dir / "contradictions.json").write_text(json.dumps([]))

    summary = {"manifest": manifest, "question": "Q?", "run_dir": str(run_dir)}
    ui = _adapt_pipeline_a_to_ui_json(summary, "vec_001", run_dir)

    # UI contract fields
    required_keys = {
        "vector_id", "original_query", "status", "release_allowed",
        "final_report", "bibliography", "contradictions",
        "quality_metrics", "evaluator_gate", "evidence_selection",
        "cost_usd", "budget_cap_usd", "run_dir", "graph_version",
        "timestamps",
    }
    assert required_keys - set(ui.keys()) == set(), (
        f"UI JSON missing: {required_keys - set(ui.keys())}"
    )
    assert ui["status"] == "success"
    assert ui["release_allowed"] is True
    assert ui["graph_version"] == "v4"
    assert ui["quality_metrics"]["total_words"] == 1200
    assert len(ui["bibliography"]) == 1


# ─────────────────────────────────────────────────────────────────
# 4. UI JSON is written atomically (tmp + rename)
# ─────────────────────────────────────────────────────────────────

def test_b102_graph_v4_writes_ui_json_atomically(tmp_path: Path, monkeypatch) -> None:
    """_write_ui_json uses a tmp file + rename so readers never see
    a partial write."""
    from src.polaris_graph.pipeline_a_ui_adapter import _write_ui_json

    monkeypatch.chdir(tmp_path)
    data = {"vector_id": "test_vec", "status": "success"}
    _write_ui_json("test_vec", data)
    out = tmp_path / "outputs" / "polaris_graph" / "test_vec.json"
    assert out.exists()
    # .tmp shouldn't exist post-rename
    assert not (tmp_path / "outputs" / "polaris_graph" / "test_vec.json.tmp").exists()
    loaded = json.loads(out.read_text(encoding="utf-8"))
    assert loaded["vector_id"] == "test_vec"
    assert loaded["status"] == "success"


# ─────────────────────────────────────────────────────────────────
# 5. Error path: graph_v4 catches run_one_query exceptions gracefully
# ─────────────────────────────────────────────────────────────────

def test_b102_graph_v4_error_path_returns_valid_status(
    tmp_path: Path, monkeypatch,
) -> None:
    """When run_one_query raises, graph_v4 writes an error UI JSON
    and returns a status that's in the unified taxonomy."""
    from src.polaris_graph import pipeline_a_ui_adapter
    from scripts.run_honest_sweep_r3 import UNIFIED_STATUS_VALUES

    async def _boom(*a, **kw):
        raise RuntimeError("simulated infra failure")

    monkeypatch.chdir(tmp_path)
    # Patch at the deferred-import site
    monkeypatch.setattr(
        "scripts.run_honest_sweep_r3.run_one_query",
        _boom,
    )

    async def _runner():
        return await pipeline_a_ui_adapter.build_and_run_v4(
            vector_id="err_vec",
            query="anything",
            application="tech",
            region="",
        )
    result = asyncio.run(_runner())
    assert result["status"] in UNIFIED_STATUS_VALUES, (
        f"Error-path status must be in unified taxonomy: {result}"
    )
    assert result["status"] == "error_unexpected"
    # UI JSON also written
    out = tmp_path / "outputs" / "polaris_graph" / "err_vec.json"
    assert out.exists()
    ui = json.loads(out.read_text(encoding="utf-8"))
    assert ui["status"] == "error_unexpected"
    assert "error" in ui


# ─────────────────────────────────────────────────────────────────
# 6. live_server now dispatches to v4 by default
# ─────────────────────────────────────────────────────────────────

def test_b102_live_server_dispatches_v4_by_default() -> None:
    """Source check: PG_GRAPH_VERSION default is 'v4' and the v4
    branch imports build_and_run_v4."""
    sweep_path = (
        Path(__file__).resolve().parents[2] / "scripts" / "live_server.py"
    )
    source = sweep_path.read_text(encoding="utf-8")
    assert 'os.getenv("PG_GRAPH_VERSION", "v4")' in source, (
        "live_server PG_GRAPH_VERSION default must be v4"
    )
    assert 'pipeline_a_ui_adapter import build_and_run_v4' in source, (
        "live_server must import build_and_run_v4 in the v4 branch"
    )


def test_b102_live_server_legacy_variants_still_selectable() -> None:
    """Legacy v1/v2/v3 still reachable via explicit env flags for
    compatibility during migration."""
    sweep_path = (
        Path(__file__).resolve().parents[2] / "scripts" / "live_server.py"
    )
    source = sweep_path.read_text(encoding="utf-8")
    assert 'graph_version == "v3"' in source
    assert 'graph_version == "v1"' in source
    # v2 requires the old opt-in flag
    assert "PG_V2_ENABLED" in source


# ─────────────────────────────────────────────────────────────────
# 7. custom scope template (R2b) loads correctly
# ─────────────────────────────────────────────────────────────────

def test_b102_custom_scope_template_loadable() -> None:
    """R2b: the custom scope template for free-form UI queries loads
    without error and has expected keys."""
    from src.polaris_graph.nodes.scope_gate import (
        SUPPORTED_DOMAINS, load_scope_template,
    )
    assert "custom" in SUPPORTED_DOMAINS
    template = load_scope_template("custom")
    assert template["domain"] == "custom"
    assert "expected_tier_distribution" in template
    # Custom template is permissive: no mandatory T1 floor
    t1 = next(
        (t for t in template["expected_tier_distribution"] if t["tier"] == "T1"),
        None,
    )
    assert t1 is not None
    assert t1["min_fraction"] == 0.00


# ─────────────────────────────────────────────────────────────────
# 8. Full end-to-end graph_v4 invocation: signature + adapter wiring
# ─────────────────────────────────────────────────────────────────

def test_b102_graph_v4_end_to_end_with_mocked_orchestrator(
    tmp_path: Path, monkeypatch,
) -> None:
    """Mock run_one_query to return a successful summary; verify
    graph_v4 adapts it to UI JSON + emits trace events."""
    from src.polaris_graph import pipeline_a_ui_adapter

    monkeypatch.chdir(tmp_path)

    async def _mock_run(q, out_root):
        # Write a minimal manifest + report on disk (what pipeline A
        # does, shape-compatible with _adapt_pipeline_a_to_ui_json).
        run_dir = Path(out_root) / q["domain"] / q["slug"]
        run_dir.mkdir(parents=True, exist_ok=True)
        manifest = {
            "status": "success",
            "release_allowed": True,
            "generator": {
                "words": 500, "sentences_verified": 12, "sentences_dropped": 0,
                "sections_kept": 3,
            },
            "cost_usd": 0.42,
            "budget_cap_usd": 5.00,
            "evaluator_gate": {"gate_class": "pass", "release_allowed": True},
            "evidence_selection": {"selection_strategy": "tier_balanced_v1"},
        }
        (run_dir / "manifest.json").write_text(json.dumps(manifest))
        (run_dir / "report.md").write_text("# Research report\n\nFindings.")
        (run_dir / "bibliography.json").write_text(json.dumps([]))
        (run_dir / "contradictions.json").write_text(json.dumps([]))
        return {
            "manifest": manifest,
            "question": q["question"],
            "run_dir": str(run_dir),
            "status": "success",
        }

    monkeypatch.setattr(
        "scripts.run_honest_sweep_r3.run_one_query",
        _mock_run,
    )

    async def _runner():
        return await pipeline_a_ui_adapter.build_and_run_v4(
            vector_id="e2e_vec",
            query="What are the efficacy signals for semaglutide?",
            application="clinical",
            region="US",
        )
    result = asyncio.run(_runner())
    # Status from pipeline-A flows through
    assert result["status"] == "success"
    assert result["release_allowed"] is True
    assert result["graph_version"] == "v4"
    # UI JSON written at expected path
    ui_path = tmp_path / "outputs" / "polaris_graph" / "e2e_vec.json"
    assert ui_path.exists()
    ui = json.loads(ui_path.read_text(encoding="utf-8"))
    assert ui["vector_id"] == "e2e_vec"
    assert ui["status"] == "success"
    assert ui["graph_version"] == "v4"
    assert ui["final_report"].startswith("# Research report")
    # Trace file was created
    trace_path = tmp_path / "logs" / "pg_trace_e2e_vec.jsonl"
    assert trace_path.exists()
    events = [json.loads(line) for line in trace_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    # Trace JSONL uses "type" key, not "event_type"
    event_types = {e.get("type") for e in events}
    # Should have at least pipeline_start + pipeline_end
    assert "pipeline_start" in event_types, f"Got types: {event_types}"
    assert "pipeline_end" in event_types
