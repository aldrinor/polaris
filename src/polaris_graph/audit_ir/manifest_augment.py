"""I-arch-001a — single helper for v6-mode manifest augmentation.

Pipeline-A writes manifest.json at 6 sites (line refs in run_honest_sweep_r3.py:
1331/1453/1667/1746/2303/2806). When v6_mode is active, each call routes
through augment_v6_manifest() to add the v6 fields the API + run_store +
F-snowball bridge require. When v6_mode is False, only the I-gen-004 (#496)
``reasoning_trace`` reference is added (see augment_v6_manifest); all other
v6 fields stay absent.
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

    The I-gen-004 (#496) ``reasoning_trace`` reference is added on EVERY
    invocation (operator transparency directive). Non-v6 invocations
    (external_run_id is None) otherwise get the input back unchanged — no
    v6 run_store / retrieval / adequacy / models fields.
    """
    augmented = dict(manifest)
    # I-gen-004 (#496): every run writes reasoning_trace.jsonl (the raw model
    # reasoning channel — process-transparency evidence, NOT verified claims;
    # strict_verify is never run against it). Referenced unconditionally so
    # an operator can locate it from any manifest — success / abort / error,
    # v6-mode or legacy CLI. Filename mirrors
    # generator.reasoning_trace.REASONING_TRACE_FILENAME.
    augmented["reasoning_trace"] = {
        "file": "reasoning_trace.jsonl",
        "description": (
            "raw model reasoning channel captured per generator LLM call; "
            "process-transparency evidence, NOT verified claims"
        ),
    }
    if external_run_id is None:
        return augmented

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
