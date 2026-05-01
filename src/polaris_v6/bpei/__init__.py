"""BPEI fix substrate — Phase 1 Task 1.2 (F2 ambiguity detector).

The BPEI failure pattern (memory: bpei_phantom_completion_lessons.md): user
typed "What is BPEI" into the dashboard, scope gate accepted it, retrieval
mixed two unrelated meanings (banking terminology vs. blood-pressure
something else). This module provides the HDBSCAN-based ambiguity detector
that surfaces multi-meaning queries before any retrieval cost is incurred.

Pattern: embed candidate retrievals → HDBSCAN cluster → if ≥2 clusters
with min_cluster_size sources, the question is ambiguous and the UI
shows a disambiguation modal.
"""
