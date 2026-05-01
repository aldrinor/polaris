"""Workspace memory substrate (Phase 2B Task 2B.6).

Per memory bpei_phantom_completion_lessons.md and v6 plan errata,
existing `workspace_memory.py` is keyword/Jaccard v1, NOT semantic.
Phase 2B migrates to a Chroma-backed semantic store. This module
holds the v6 schema + an in-memory implementation that can be
swapped for Chroma when the cluster is live.
"""
