#!/usr/bin/env python3
"""WS-0 (I-deepfix-001 #1344) — the run-launch GPU device-split config + a co-residence preflight.

WHY THIS EXISTS (the drb_72 GPU-OOM degrade cascade)
----------------------------------------------------
On the 2-card VM (2x RTX3090Ti, ~24GB each) the paid Gate-B run put the W5 content-relevance reranker,
the W6 Qwen3-Embedding-8B embedder, and the W10 consolidation NLI cross-encoder ALL on ``cuda:0`` (every
device env unset defaults the model to card 0). The 16GB embedder + the reranker's ~24.8GB one-pass
logits tensor then OOM'd, and the run SILENTLY DEGRADED: W2 semantic-relevance fell back to lexical,
consolidation fell to the CPU wall (under-merge), and GLM credibility-tiering fell to the rules-floor.
That single infra fault is the upstream root of the thin single-origin corpus (B2 Recall + Analysis).

THE FIX (proven 2026-06-30) — a 2-card device split + a bounded W5 score chunk
------------------------------------------------------------------------------
  * ``PG_EMBED_DEVICE=cuda:0``            — W6 Qwen3-Embedding-8B alone on card 0 (~16GB fp16)
  * ``PG_RERANKER_DEVICE=cuda:1``         — W7 Qwen3-Reranker-4B on card 1
  * ``PG_NLI_DEVICE=cuda:1``              — FaithLens NLI cross-encoder on card 1 (off the critical path)
  * ``PG_CONSOLIDATION_NLI_DEVICE=cuda:1``— W10 consolidation NLI cross-encoder on card 1
  * ``PG_CONTENT_RELEVANCE_SCORE_CHUNK=2``— W5 reranker scores in chunks so the per-forward logits tensor
    stays small enough to fit alongside the co-resident embedder (faithfulness-neutral — chunked scores
    are byte-identical to the one-pass path; content_relevance_judge.py:442-455).

The W5 content-relevance reranker (Qwen3-Reranker-0.6B) stays on ``cuda:0`` (its own
``PG_CONTENT_RELEVANCE_DEVICE`` default "cuda") but is BOUNDED by the score chunk, so the split leaves
card 0 = big embedder + bounded 0.6B reranker, card 1 = 4B reranker + two small NLI cross-encoders.

SINGLE-CARD HOSTS (e.g. an A100-80GB)
-------------------------------------
On a host with only one visible CUDA device, a split cannot help — everything co-resides, and on an
80GB card it fits with headroom. The card-split warning is therefore suppressed when ``device_count < 2``.
The W5 score-chunk bound STILL applies (it is cheap insurance against the 24.8GB one-pass tensor even on
a big card), so that warning is card-count-independent.

BUILD-ONLY / NO SPEND / NO MODEL LOAD
-------------------------------------
Pure config. ``detect_coresidence_warnings`` is a pure function over an env map + a device count (offline-
testable, no GPU needed). Only ``--check`` touches the GPU — a free ``torch.cuda.device_count()`` read
(no model load, no completion call). ``--export`` emits sourceable ``export K=V`` lines for the launcher.

LAW VI: the recommended values ARE this file's config surface (a documented launch template), not magic
numbers scattered through the run path. The run path READS these envs; this helper DECLARES them.

Usage
-----
    # print the documented launch template (human-readable)
    python scripts/dr_benchmark/gpu_device_split.py

    # emit sourceable export lines for a 2-card launch
    source <(python scripts/dr_benchmark/gpu_device_split.py --export)
    python scripts/dr_benchmark/run_gate_b.py --only <slug>

    # preflight the CURRENT env against the visible GPU topology (warns on co-residence)
    python scripts/dr_benchmark/gpu_device_split.py --check     # exit 0 clean, 3 == warnings emitted
"""

from __future__ import annotations

import argparse
import os
import sys
from typing import Mapping, Optional

# The recommended 2-card split + the W5 score-chunk bound (the proven 2026-06-30 fix). This is the
# documented launch template; the run path reads each key at model-load / call time.
RECOMMENDED_DEVICE_SPLIT: dict[str, str] = {
    "PG_EMBED_DEVICE": "cuda:0",              # W6 Qwen3-Embedding-8B (embedding_service:150 / prefetch_offtopic_filter:140)
    "PG_RERANKER_DEVICE": "cuda:1",           # W7 Qwen3-Reranker-4B (evidence_selector:2658 / qwen_reranker_scorer:83)
    "PG_NLI_DEVICE": "cuda:1",                # FaithLens NLI (nli_verifier:95, off the critical path)
    "PG_CONSOLIDATION_NLI_DEVICE": "cuda:1",  # W10 consolidation NLI cross-encoder (consolidation_nli:73)
    "PG_CONTENT_RELEVANCE_SCORE_CHUNK": "2",  # W5 reranker chunked scoring (content_relevance_judge:451)
}

# The four HEAVY-model device envs whose co-residence on one card is the OOM-degrade risk. (The W5
# content-relevance reranker uses PG_CONTENT_RELEVANCE_DEVICE and is bounded by the score chunk, so it
# is intentionally NOT in the card-balance set — the score-chunk warning covers it.)
_HEAVY_MODEL_DEVICE_ENVS: dict[str, str] = {
    "PG_EMBED_DEVICE": "W6 embedder (Qwen3-Embedding-8B, ~16GB fp16)",
    "PG_RERANKER_DEVICE": "W7 reranker (Qwen3-Reranker-4B, ~8GB)",
    "PG_NLI_DEVICE": "FaithLens NLI cross-encoder",
    "PG_CONSOLIDATION_NLI_DEVICE": "W10 consolidation NLI cross-encoder",
}

# An UNSET device env lands the model on the module default card (cuda:0). That default IS the OOM trap
# the split fixes, so an unset env resolves to card 0 for the co-residence check (never "unknown").
_DEFAULT_GPU_CARD = 0

_SCORE_CHUNK_ENV = "PG_CONTENT_RELEVANCE_SCORE_CHUNK"


def resolve_gpu_card(value: Optional[str]) -> Optional[int]:
    """The GPU card index a device string targets. ``cuda:N`` -> N; ``cuda`` / bare ``N`` -> that index;
    UNSET/empty -> the module default card 0 (the co-residence trap); ``cpu`` or an unparseable value ->
    None (not a GPU card, excluded from the balance check)."""
    v = (value or "").strip().lower()
    if not v:
        return _DEFAULT_GPU_CARD
    if v == "cpu":
        return None
    if v == "cuda":
        return 0
    if v.startswith("cuda:"):
        tail = v.split(":", 1)[1]
        return int(tail) if tail.isdigit() else None
    if v.isdigit():
        return int(v)
    return None


def detect_coresidence_warnings(
    env: Mapping[str, str], device_count: Optional[int]
) -> list[str]:
    """Pure preflight. Return the list of WARNING strings for the given env + visible GPU count.

    (1) CARD CO-RESIDENCE — only when ``device_count >= 2``: if every heavy-model device env resolves to
        a SINGLE GPU card, the models will co-reside and risk the GPU-OOM degrade cascade; recommend the
        split. Suppressed on a 1-GPU host (a split cannot help there).
    (2) W5 SCORE-CHUNK — card-count-independent: if ``PG_CONTENT_RELEVANCE_SCORE_CHUNK`` is unset/0/negative
        (one-pass), the ~24.8GB one-pass logits tensor can OOM the co-resident embedder; recommend =2.
    """
    warns: list[str] = []

    if device_count is not None and device_count >= 2:
        gpu_cards: set[int] = set()
        for name in _HEAVY_MODEL_DEVICE_ENVS:
            card = resolve_gpu_card(env.get(name))
            if card is not None:
                gpu_cards.add(card)
        if len(gpu_cards) <= 1:
            only = next(iter(gpu_cards), _DEFAULT_GPU_CARD)
            split = ", ".join(
                f"{k}={RECOMMENDED_DEVICE_SPLIT[k]}"
                for k in _HEAVY_MODEL_DEVICE_ENVS
                if k in RECOMMENDED_DEVICE_SPLIT
            )
            warns.append(
                f"[gpu-device-split WARNING] {device_count} CUDA devices visible but every heavy model "
                f"resolves to a SINGLE card cuda:{only} "
                f"({', '.join(_HEAVY_MODEL_DEVICE_ENVS)}) — they will co-reside and risk a GPU-OOM degrade "
                f"(W5 reranker + W6 embedder + W10 NLI on one card was the drb_72 root). Apply the 2-card "
                f"split: {split}."
            )

    try:
        chunk = int((env.get(_SCORE_CHUNK_ENV) or "0").strip())
    except (TypeError, ValueError):
        chunk = 0
    if chunk <= 0:
        warns.append(
            f"[gpu-device-split WARNING] {_SCORE_CHUNK_ENV} is unset/0 (one-pass) — the W5 Qwen3-Reranker "
            f"scores ALL pairs in one forward pass (~24.8GB logits tensor) and can OOM the co-resident "
            f"embedder on cuda:0. Set {_SCORE_CHUNK_ENV}=2 (faithfulness-neutral: chunked scores are "
            f"byte-identical to one-pass)."
        )
    return warns


def _visible_cuda_device_count() -> Optional[int]:
    """A FREE ``torch.cuda.device_count()`` read (no model load, no spend). None if torch is unavailable."""
    try:
        import torch  # noqa: PLC0415
    except ImportError:
        return None
    try:
        return int(torch.cuda.device_count())
    except Exception:  # noqa: BLE001 — a driver hiccup must never crash a preflight
        return None


def render_launch_template(as_export: bool = False) -> str:
    """The documented launch config. ``as_export=True`` -> sourceable ``export K=V`` lines; else a
    human-readable ``K=V  # why`` template."""
    lines: list[str] = []
    for key, value in RECOMMENDED_DEVICE_SPLIT.items():
        if as_export:
            lines.append(f"export {key}={value}")
        else:
            why = _HEAVY_MODEL_DEVICE_ENVS.get(key, "W5 reranker chunked scoring (one-pass OOM guard)")
            lines.append(f"{key}={value}  # {why}")
    return "\n".join(lines)


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="WS-0 GPU device-split launch config + co-residence preflight.")
    ap.add_argument("--export", action="store_true", help="emit sourceable `export K=V` lines")
    ap.add_argument("--check", action="store_true",
                    help="preflight the CURRENT env vs the visible GPU topology (exit 3 if warnings)")
    args = ap.parse_args(argv)

    if args.export:
        print(render_launch_template(as_export=True))
        return 0

    if args.check:
        device_count = _visible_cuda_device_count()
        dc_note = "torch unavailable (card-split check skipped)" if device_count is None else f"{device_count} CUDA device(s)"
        print(f"[gpu-device-split] visible: {dc_note}")
        warns = detect_coresidence_warnings(os.environ, device_count)
        for w in warns:
            print(w)
        if not warns:
            print("[gpu-device-split] OK — no co-residence / one-pass OOM risk in the current env.")
        return 3 if warns else 0

    # default: print the documented template.
    print("# WS-0 recommended 2-card GPU device split (source via --export):")
    print(render_launch_template(as_export=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
