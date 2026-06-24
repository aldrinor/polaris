"""Offline $0 smoke test: ContentDeduplicator is the ACTIVE default dedup (I-recency-001 #1296).

DEDUP is the recency-completion pick that is ALREADY wired as the active default — no change is
made to it; this test CONFIRMS that:

  1. ``ContentDeduplicator`` imports + instantiates (pure-Python MinHash, no model/network).
  2. ``analyzer._deduplicate_evidence`` is the production consumer and constructs exactly that
     class — proving the wiring is live, not a dead alternative.
  3. The kill-switch ``PG_EVIDENCE_DEDUP_ENABLED`` defaults to ON ("1"), so the active path runs
     by default.

Cost: $0 (MinHash is local; no LLM / network / GPU).
"""
from __future__ import annotations

import inspect


def test_content_deduplicator_imports_and_instantiates():
    """ContentDeduplicator is importable and constructs with no args ($0, pure-Python MinHash)."""
    from src.utils.content_deduplicator import ContentDeduplicator

    dedup = ContentDeduplicator()
    assert dedup is not None
    assert hasattr(dedup, "deduplicate"), "ContentDeduplicator must expose deduplicate()"


def test_content_deduplicator_deduplicates_exact_duplicate():
    """A real dedup pass collapses an exact-duplicate statement — proving the class WORKS, $0."""
    from src.utils.content_deduplicator import ContentDeduplicator

    dedup = ContentDeduplicator()
    items = [
        {"content": "Tirzepatide reduced HbA1c by 2.1 percent in SURPASS-2."},
        {"content": "Tirzepatide reduced HbA1c by 2.1 percent in SURPASS-2."},  # exact dup
        {"content": "Semaglutide lowered body weight in STEP-1."},
    ]
    result = dedup.deduplicate(items, content_key="content")
    assert result.unique_count <= 2, (
        f"exact duplicate should collapse to <=2 unique, got {result.unique_count}"
    )
    assert result.unique_count >= 1


def test_analyzer_deduplicate_evidence_uses_content_deduplicator():
    """analyzer._deduplicate_evidence is the production consumer and constructs ContentDeduplicator.

    We assert by source inspection (no run, no model, no network) that the active dedup function
    references ContentDeduplicator — confirming it is the wired-in default, not a dead alternative.
    """
    from src.polaris_graph.agents import analyzer

    src = inspect.getsource(analyzer._deduplicate_evidence)
    assert "ContentDeduplicator" in src, (
        "_deduplicate_evidence must construct ContentDeduplicator (the active dedup default)"
    )
    assert "dedup.deduplicate(" in src, (
        "_deduplicate_evidence must call ContentDeduplicator.deduplicate()"
    )


def test_evidence_dedup_enabled_defaults_on():
    """The kill-switch defaults to ON so the ContentDeduplicator path is the ACTIVE default."""
    import importlib
    import os

    prev = os.environ.get("PG_EVIDENCE_DEDUP_ENABLED")
    try:
        os.environ.pop("PG_EVIDENCE_DEDUP_ENABLED", None)
        import src.polaris_graph.state as state
        importlib.reload(state)
        assert state.PG_EVIDENCE_DEDUP_ENABLED is True, (
            "PG_EVIDENCE_DEDUP_ENABLED must default ON (dedup is the active default)"
        )
    finally:
        if prev is None:
            os.environ.pop("PG_EVIDENCE_DEDUP_ENABLED", None)
        else:
            os.environ["PG_EVIDENCE_DEDUP_ENABLED"] = prev
        import src.polaris_graph.state as state
        importlib.reload(state)


if __name__ == "__main__":
    test_content_deduplicator_imports_and_instantiates()
    test_content_deduplicator_deduplicates_exact_duplicate()
    test_analyzer_deduplicate_evidence_uses_content_deduplicator()
    test_evidence_dedup_enabled_defaults_on()
    print("PASS — ContentDeduplicator active-default dedup smoke ($0, no model/network)")
