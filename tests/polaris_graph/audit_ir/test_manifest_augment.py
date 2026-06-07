"""I-arch-001a — augment_v6_manifest helper coverage."""

from __future__ import annotations

from polaris_graph.audit_ir.manifest_augment import augment_v6_manifest


def test_non_v6_mode_adds_only_reasoning_trace_no_v6_fields() -> None:
    """I-ready-018 (#1088): in non-v6 mode (external_run_id is None) the helper now adds ONLY the
    I-gen-004 (#496) reasoning_trace reference (operator process-transparency directive, added on
    EVERY invocation per the function docstring + module docstring) and NO v6 run_store fields. The
    prior assertion `out is manifest` predates I-gen-004 — it is STALE, not a regression. Faithfulness
    note: reasoning_trace is process-transparency EVIDENCE explicitly NOT subject to strict_verify."""
    manifest = {"status": "success", "run_id": "SWEEP_x_y_123", "scope": {"decision": "in_scope"}}
    out = augment_v6_manifest(
        manifest,
        external_run_id=None,
        decision_id=None,
        query_slug=None,
    )
    # Input is NOT mutated (the helper returns a copy).
    assert "reasoning_trace" not in manifest
    # Non-v6 output = input + the reasoning_trace ref, and NOTHING else.
    assert out["status"] == "success"
    assert out["run_id"] == "SWEEP_x_y_123"
    assert out["scope"] == {"decision": "in_scope"}  # no decision_id injected in non-v6 mode
    assert out["reasoning_trace"]["file"] == "reasoning_trace.jsonl"
    # No v6 run_store / retrieval / adequacy / models fields in non-v6 mode.
    for v6_key in ("external_run_id", "query_slug", "retrieval", "adequacy", "models"):
        assert v6_key not in out, f"non-v6 mode must NOT add {v6_key!r}"
    assert set(out) == set(manifest) | {"reasoning_trace"}


def test_v6_mode_adds_external_run_id_and_query_slug() -> None:
    out = augment_v6_manifest(
        {"status": "success"},
        external_run_id="uuid-1234",
        decision_id="dec-5678",
        query_slug="clinical_glp1",
    )
    assert out["external_run_id"] == "uuid-1234"
    assert out["query_slug"] == "clinical_glp1"
    assert out["scope"]["decision_id"] == "dec-5678"


def test_v6_mode_preserves_existing_scope_block() -> None:
    """Existing scope.* keys survive; decision_id is merged in."""
    out = augment_v6_manifest(
        {"scope": {"decision": "in_scope", "rejected": False}},
        external_run_id="uuid-1",
        decision_id="dec-1",
        query_slug="q",
    )
    assert out["scope"]["decision"] == "in_scope"
    assert out["scope"]["rejected"] is False
    assert out["scope"]["decision_id"] == "dec-1"


def test_v6_mode_optional_blocks_appended() -> None:
    out = augment_v6_manifest(
        {"status": "success"},
        external_run_id="uuid-1",
        decision_id="dec-1",
        query_slug="q",
        retrieval_block={"latency_ms": 1234, "cost_usd": 0.42},
        adequacy_block={"decision": "adequate"},
        models_block={"generator": "gen-A", "evaluator": "eval-B"},
    )
    assert out["retrieval"]["latency_ms"] == 1234
    assert out["adequacy"]["decision"] == "adequate"
    assert out["models"]["generator"] == "gen-A"


def test_does_not_mutate_input() -> None:
    """Input dict is unmodified after augmentation."""
    manifest = {"status": "success", "scope": {"decision": "in_scope"}}
    snapshot = dict(manifest)
    augment_v6_manifest(manifest, external_run_id="x", decision_id="y", query_slug="z")
    assert manifest == snapshot
