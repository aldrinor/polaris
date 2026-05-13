"""I-arch-001a — augment_v6_manifest helper coverage."""

from __future__ import annotations

from polaris_graph.audit_ir.manifest_augment import augment_v6_manifest


def test_non_v6_mode_returns_input_unchanged() -> None:
    """When external_run_id is None, the helper is a passthrough (byte-identical)."""
    manifest = {"status": "success", "run_id": "SWEEP_x_y_123", "scope": {"decision": "in_scope"}}
    out = augment_v6_manifest(
        manifest,
        external_run_id=None,
        decision_id=None,
        query_slug=None,
    )
    assert out is manifest  # exact same object — zero behavioral change


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
