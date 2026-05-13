"""I-arch-001a — single helper for v6-mode manifest augmentation.

Pipeline-A writes manifest.json at 6 sites (line refs in run_honest_sweep_r3.py:
1331/1453/1667/1746/2303/2806). When v6_mode is active, each call routes
through augment_v6_manifest() to add the v6 fields the API + run_store +
F-snowball bridge require. When v6_mode is False, manifest stays byte-
identical to today (no key added).
"""

from __future__ import annotations

from typing import Any


def augment_v6_manifest(
    manifest: dict[str, Any],
    *,
    external_run_id: str | None,
    decision_id: str | None,
    query_slug: str | None,
    retrieval_block: dict[str, Any] | None = None,
    adequacy_block: dict[str, Any] | None = None,
    models_block: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return augmented manifest dict. Does not mutate input.

    Non-v6 invocations (external_run_id is None) get the input back
    unchanged — pipeline-A's existing behavior is preserved byte-for-byte.
    """
    if external_run_id is None:
        return manifest

    augmented = dict(manifest)
    augmented["external_run_id"] = external_run_id
    augmented["query_slug"] = query_slug

    scope = dict(augmented.get("scope") or {})
    scope["decision_id"] = decision_id
    augmented["scope"] = scope

    if retrieval_block is not None:
        augmented["retrieval"] = retrieval_block
    if adequacy_block is not None:
        augmented["adequacy"] = adequacy_block
    if models_block is not None:
        augmented["models"] = models_block

    return augmented
