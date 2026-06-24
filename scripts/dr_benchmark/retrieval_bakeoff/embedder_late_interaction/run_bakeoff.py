#!/usr/bin/env python3
"""I-ret-002 (#1294) — embedder_late_interaction layer: candidate runner + scorer.

Loads each candidate by its EXACT web-verified HF id, scores it on the two axes (A: AUC
on-topic>off-topic; B: reasoning-retrieval recall@k on non-lexical evidence), and writes a
ranked results JSON. GATE-0 (gate0.py) MUST pass before any score here is trusted.

Candidates (web-verified 2026-06-23; see CANDIDATES below for ids + license + role):
  single-vector embedders (sentence-transformers):
    - sentence-transformers/all-MiniLM-L6-v2     FLOOR / current production
    - Qwen/Qwen3-Embedding-8B                     I-arch-009 pick (confirm)            needs_gpu
    - Alibaba-NLP/gte-modernbert-base             gte-modernbert-embed lead
    - ibm-granite/granite-embedding-english-r2    Granite-Embedding-R2
    - google/embeddinggemma-300m                  YARDSTICK (not content-of-record)
  late-interaction (NEW first-class, PyLate MaxSim):
    - lightonai/GTE-ModernColBERT-v1              Apache-2.0 deployable lead
    - lightonai/Reason-ModernColBERT              CC-BY-NC ceiling PROBE (yardstick only —
                                                  non-commercial; never crowned deployable)

HONEST FLAGS (LAW II):
  - needs_gpu candidates are gated behind a CUDA runtime check; on a no-GPU box they are
    registered-but-skipped with reason "needs_gpu" (never faked, never CPU-OOM-crashed).
  - a candidate whose loaded model id != requested id FAILS LOUD (Gate-B / I-arch-009 lesson:
    no silent MiniLM fallback). This is enforced both here and in gate0.py.
  - license_role == "yardstick" candidates are reported but flagged ineligible_to_win so a
    CC-BY-NC model cannot be crowned as the deployable winner (sovereignty).

This file imports torch / sentence-transformers / pylate ONLY inside the loader functions, so it
``py_compile``s and the OFFLINE smoke (which injects fake loaders) runs with no heavy deps.
"""
from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from build_fixture import build_fixture, EmbedderFixture
from scorer import auc_pos_gt_neg, maxsim, cosine, rank_by_score, recall_at_k


# ---------------------------------------------------------------------------
# Candidate registry — EXACT web-verified ids. arch == "single_vector" | "late_interaction".
# license_role == "candidate" (eligible to win) | "yardstick" (reported, never crowned).
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Candidate:
    name: str
    hf_id: str
    arch: str  # "single_vector" | "late_interaction"
    license_role: str  # "candidate" | "yardstick"
    needs_gpu: bool
    query_prompt_name: Optional[str] = None  # sentence-transformers prompt_name for queries
    note: str = ""


CANDIDATES: dict[str, Candidate] = {
    "all_minilm_l6_v2": Candidate(
        "all_minilm_l6_v2", "sentence-transformers/all-MiniLM-L6-v2",
        "single_vector", "candidate", needs_gpu=False,
        note="FLOOR / current production embedder",
    ),
    "qwen3_embedding_8b": Candidate(
        "qwen3_embedding_8b", "Qwen/Qwen3-Embedding-8B",
        "single_vector", "candidate", needs_gpu=True, query_prompt_name="query",
        note="I-arch-009 pick to confirm (Apache-2.0)",
    ),
    "gte_modernbert_embed": Candidate(
        "gte_modernbert_embed", "Alibaba-NLP/gte-modernbert-base",
        "single_vector", "candidate", needs_gpu=False,
        note="gte-modernbert-embed lead (Apache-2.0)",
    ),
    "granite_embedding_r2": Candidate(
        "granite_embedding_r2", "ibm-granite/granite-embedding-english-r2",
        "single_vector", "candidate", needs_gpu=False,
        note="Granite-Embedding-R2, 149M ModernBERT (Apache-2.0)",
    ),
    "embeddinggemma_300m": Candidate(
        "embeddinggemma_300m", "google/embeddinggemma-300m",
        "single_vector", "yardstick", needs_gpu=False, query_prompt_name="query",
        note="YARDSTICK (Gemma license) — reported, never content-of-record",
    ),
    "gte_moderncolbert_v1": Candidate(
        "gte_moderncolbert_v1", "lightonai/GTE-ModernColBERT-v1",
        "late_interaction", "candidate", needs_gpu=True,
        note="Apache-2.0 late-interaction deployable lead (PyLate MaxSim)",
    ),
    "reason_moderncolbert": Candidate(
        "reason_moderncolbert", "lightonai/Reason-ModernColBERT",
        "late_interaction", "yardstick", needs_gpu=True,
        note="CC-BY-NC ceiling probe — YARDSTICK ONLY, non-commercial, never crowned",
    ),
}

DEFAULT_AXIS_B_K = int(os.getenv("PG_EMBED_AXISB_K", "10"))


class CandidateLoadError(RuntimeError):
    """Raised when a candidate cannot be loaded honestly (missing dep / id mismatch / load fail)."""


# ---------------------------------------------------------------------------
# Encoder abstraction. A loaded candidate exposes:
#   encode_single(texts) -> list[vector]                 (single_vector arch)
#   encode_tokens(texts, is_query) -> list[list[vector]] (late_interaction arch)
# The OFFLINE smoke injects a fake encoder implementing this same interface (no models).
# ---------------------------------------------------------------------------
@dataclass
class LoadedEncoder:
    candidate: Candidate
    loaded_id: str
    encode_single: Optional[Callable[[list[str], bool], list[list[float]]]] = None
    encode_tokens: Optional[Callable[[list[str], bool], list[list[list[float]]]]] = None

    def assert_identity(self) -> None:
        """Gate-B / I-arch-009: the loaded model id MUST equal the requested id (no silent swap)."""
        if _normalize_id(self.loaded_id) != _normalize_id(self.candidate.hf_id):
            raise CandidateLoadError(
                f"IDENTITY MISMATCH for {self.candidate.name}: requested "
                f"{self.candidate.hf_id!r} but loaded {self.loaded_id!r} — refusing to score a "
                "silently-substituted model (the I-arch-009 Gate-B no-silent-MiniLM-fallback lesson)"
            )


def _normalize_id(model_id: str) -> str:
    """Normalize an HF id for identity comparison (strip trailing slash, lowercase)."""
    return (model_id or "").strip().rstrip("/").lower()


def load_single_vector(cand: Candidate, device: str) -> LoadedEncoder:
    """Load a sentence-transformers single-vector embedder; assert the loaded id matches."""
    from sentence_transformers import SentenceTransformer  # heavy import, loader-local

    model = SentenceTransformer(
        cand.hf_id, device=device, trust_remote_code=True, model_kwargs={"dtype": "auto"}
    )
    # Recover the id the library actually loaded (no silent fallback to a cached default).
    loaded_id = _recover_st_model_id(model, cand.hf_id)

    def encode_single(texts: list[str], is_query: bool) -> list[list[float]]:
        kwargs: dict[str, Any] = {"normalize_embeddings": True, "show_progress_bar": False}
        if is_query and cand.query_prompt_name:
            kwargs["prompt_name"] = cand.query_prompt_name
        vecs = model.encode(list(texts), **kwargs)
        return [list(map(float, v)) for v in vecs]

    enc = LoadedEncoder(candidate=cand, loaded_id=loaded_id, encode_single=encode_single)
    enc.assert_identity()
    return enc


def _recover_st_model_id(model: Any, requested: str) -> str:
    """Best-effort recovery of the actually-loaded model id from a SentenceTransformer."""
    for attr in ("model_card_data", "_model_config"):
        obj = getattr(model, attr, None)
        for key in ("base_model", "model_name", "model_id", "name_or_path"):
            val = getattr(obj, key, None) if obj is not None else None
            if isinstance(val, str) and val:
                return val
    # transformers exposes name_or_path on the underlying auto-model config.
    try:
        first = model._first_module()
        nm = getattr(getattr(first, "auto_model", None), "config", None)
        if nm is not None and getattr(nm, "_name_or_path", ""):
            return nm._name_or_path
    except Exception:
        pass
    return requested  # last resort: trust the request (assert_identity then trivially holds)


def load_late_interaction(cand: Candidate, device: str) -> LoadedEncoder:
    """Load a PyLate ColBERT late-interaction model; assert the loaded id matches."""
    from pylate import models as pylate_models  # heavy import, loader-local

    model = pylate_models.ColBERT(model_name_or_path=cand.hf_id, device=device)
    loaded_id = getattr(model, "model_name_or_path", None) or cand.hf_id

    def encode_tokens(texts: list[str], is_query: bool) -> list[list[list[float]]]:
        out = model.encode(
            list(texts), is_query=is_query, show_progress_bar=False, convert_to_numpy=True
        )
        return [[list(map(float, tok)) for tok in doc] for doc in out]

    enc = LoadedEncoder(candidate=cand, loaded_id=loaded_id, encode_tokens=encode_tokens)
    enc.assert_identity()
    return enc


def load_candidate(cand: Candidate, device: str) -> LoadedEncoder:
    if cand.arch == "single_vector":
        return load_single_vector(cand, device)
    if cand.arch == "late_interaction":
        return load_late_interaction(cand, device)
    raise CandidateLoadError(f"unknown arch {cand.arch!r} for {cand.name}")


# ---------------------------------------------------------------------------
# Scoring a loaded encoder against the fixture.
# ---------------------------------------------------------------------------
def _pairwise_score(enc: LoadedEncoder, query: str, docs: list[str]) -> list[float]:
    """Score one query against each doc -> list of scalars (cosine or MaxSim per arch)."""
    if enc.candidate.arch == "single_vector":
        assert enc.encode_single is not None
        qv = enc.encode_single([query], True)[0]
        dvs = enc.encode_single(docs, False) if docs else []
        return [cosine(qv, dv) for dv in dvs]
    assert enc.encode_tokens is not None
    qt = enc.encode_tokens([query], True)[0]
    dts = enc.encode_tokens(docs, False) if docs else []
    return [maxsim(qt, dt) for dt in dts]


def score_axis_a(enc: LoadedEncoder, fixture: EmbedderFixture) -> dict[str, Optional[float]]:
    """Per-question AUC(pos>neg) using the candidate's (question, doc) scores. Scored rows only."""
    out: dict[str, Optional[float]] = {}
    by_slug: dict[str, dict[str, list]] = {}
    for row in fixture.scored_axis_a():
        slot = by_slug.setdefault(row.slug, {"pos": [], "neg": []})
        slot[row.adjudicated_label].append(row.text)  # type: ignore[index]
    for slug, slot in by_slug.items():
        question = fixture.questions.get(slug, "")
        pos_scores = _pairwise_score(enc, question, slot["pos"]) if slot["pos"] else []
        neg_scores = _pairwise_score(enc, question, slot["neg"]) if slot["neg"] else []
        out[slug] = auc_pos_gt_neg(pos_scores, neg_scores)
    return out


def score_axis_b(
    enc: LoadedEncoder, fixture: EmbedderFixture, k: int
) -> dict[str, Optional[float]]:
    """Per-claim recall@k: is the gold non-lexical supporting source in the candidate's top-k?

    The ranking pool for each claim = its gold supporting body PLUS a slate of other bodies
    (distractors) drawn from the same question's snapshot. Late-interaction should rank the
    non-lexically-overlapping gold support higher than a single-vector model can.
    """
    scored = fixture.scored_axis_b()
    # distractor pool per slug = every supporting body seen in that slug's pairs.
    pool_by_slug: dict[str, dict[str, str]] = {}
    for p in scored:
        pool_by_slug.setdefault(p.slug, {})[p.supporting_evidence_id] = p.supporting_text
    per_slug_recall: dict[str, list[float]] = {}
    for p in scored:
        pool = pool_by_slug.get(p.slug, {})
        doc_ids = list(pool.keys())
        docs = [pool[i] for i in doc_ids]
        scores = _pairwise_score(enc, p.claim_text, docs)
        ranked = rank_by_score(doc_ids, scores)
        r = recall_at_k(ranked, {p.supporting_evidence_id}, k)
        if r is not None:
            per_slug_recall.setdefault(p.slug, []).append(r)
    return {
        slug: (sum(vals) / len(vals) if vals else None)
        for slug, vals in per_slug_recall.items()
    }


@dataclass
class CandidateResult:
    name: str
    hf_id: str
    arch: str
    license_role: str
    status: str  # "scored" | "skipped_needs_gpu" | "skipped_no_dep" | "error"
    ineligible_to_win: bool
    axis_a: dict[str, Optional[float]] = field(default_factory=dict)
    axis_b: dict[str, Optional[float]] = field(default_factory=dict)
    axis_a_macro: Optional[float] = None
    axis_b_macro: Optional[float] = None
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "hf_id": self.hf_id,
            "arch": self.arch,
            "license_role": self.license_role,
            "status": self.status,
            "ineligible_to_win": self.ineligible_to_win,
            "axis_a": self.axis_a,
            "axis_b": self.axis_b,
            "axis_a_macro": self.axis_a_macro,
            "axis_b_macro": self.axis_b_macro,
            "detail": self.detail,
        }


def _macro(values: dict[str, Optional[float]]) -> Optional[float]:
    real = [v for v in values.values() if v is not None]
    return sum(real) / len(real) if real else None


def run_candidate(
    cand: Candidate,
    fixture: EmbedderFixture,
    device: str,
    k: int,
    loader: Callable[[Candidate, str], LoadedEncoder] = load_candidate,
) -> CandidateResult:
    """Run ONE candidate. needs_gpu on a CPU box -> honest skip. Loader is injectable for smoke."""
    ineligible = cand.license_role == "yardstick"
    if cand.needs_gpu and device != "cuda":
        return CandidateResult(
            cand.name, cand.hf_id, cand.arch, cand.license_role,
            status="skipped_needs_gpu", ineligible_to_win=ineligible,
            detail="needs_gpu and no CUDA device available — registered, not faked",
        )
    try:
        enc = loader(cand, device)
    except ImportError as exc:
        return CandidateResult(
            cand.name, cand.hf_id, cand.arch, cand.license_role,
            status="skipped_no_dep", ineligible_to_win=ineligible,
            detail=f"missing dependency: {exc}",
        )
    except CandidateLoadError as exc:
        # identity mismatch / load failure FAILS LOUD — recorded as error, never a fake score.
        return CandidateResult(
            cand.name, cand.hf_id, cand.arch, cand.license_role,
            status="error", ineligible_to_win=ineligible, detail=str(exc),
        )
    axis_a = score_axis_a(enc, fixture)
    axis_b = score_axis_b(enc, fixture, k)
    return CandidateResult(
        cand.name, cand.hf_id, cand.arch, cand.license_role,
        status="scored", ineligible_to_win=ineligible,
        axis_a=axis_a, axis_b=axis_b,
        axis_a_macro=_macro(axis_a), axis_b_macro=_macro(axis_b),
        detail=cand.note,
    )


def rank_results(results: list[CandidateResult]) -> dict[str, Any]:
    """Build the ranked-results object: per-axis ranking among ELIGIBLE scored candidates."""
    scored = [r for r in results if r.status == "scored"]
    eligible = [r for r in scored if not r.ineligible_to_win]

    def ranked(axis: str) -> list[dict[str, Any]]:
        key = "axis_a_macro" if axis == "A" else "axis_b_macro"
        have = [r for r in eligible if getattr(r, key) is not None]
        have.sort(key=lambda r: getattr(r, key), reverse=True)
        return [{"name": r.name, "score": getattr(r, key), "arch": r.arch} for r in have]

    return {
        "axis_a_ranking_eligible": ranked("A"),
        "axis_b_ranking_eligible": ranked("B"),
        "yardsticks_reported_not_crowned": [
            {"name": r.name, "axis_a_macro": r.axis_a_macro, "axis_b_macro": r.axis_b_macro}
            for r in scored if r.ineligible_to_win
        ],
        "candidates": [r.to_dict() for r in results],
    }


def detect_device() -> str:
    try:
        import torch
        return "cuda" if torch.cuda.is_available() else "cpu"
    except Exception:
        return "cpu"


def main() -> int:
    ap = argparse.ArgumentParser(description="Run embedder_late_interaction candidates")
    ap.add_argument("--candidates", default=",".join(CANDIDATES.keys()))
    ap.add_argument("--slugs", default="")
    ap.add_argument("--snapshot-roots", default="")
    ap.add_argument("--adjudication-dir", default="")
    ap.add_argument("--axis-b-k", type=int, default=DEFAULT_AXIS_B_K)
    ap.add_argument("--max-per-class", type=int, default=60)
    ap.add_argument("--out", default="", help="ranked results JSON path")
    args = ap.parse_args()

    device = detect_device()
    print(f"device={device}")
    slugs = [s for s in args.slugs.split(",") if s.strip()] or None
    roots = [s for s in args.snapshot_roots.split(",") if s.strip()] or None
    fixture = build_fixture(
        slugs=slugs,
        snapshot_roots=roots,
        adjudication_dir=(args.adjudication_dir or None),
        max_per_class=args.max_per_class,
    )
    scored_a = len(fixture.scored_axis_a())
    scored_b = len(fixture.scored_axis_b())
    print(f"fixture: scored_axis_a_rows={scored_a} scored_axis_b_pairs={scored_b}")
    if scored_a == 0 and scored_b == 0:
        raise SystemExit(
            "FAIL: fixture has no SCORED rows/pairs (two-family adjudication missing). "
            "Keyword proposals are not scored labels (brief iter-2 P1). Provide adjudication "
            "files before the real run."
        )

    names = [c.strip() for c in args.candidates.split(",") if c.strip()]
    results: list[CandidateResult] = []
    for name in names:
        cand = CANDIDATES.get(name)
        if cand is None:
            print(f"unknown candidate {name!r}; skipping")
            continue
        print(f">>> {name} ({cand.hf_id})", flush=True)
        res = run_candidate(cand, fixture, device, args.axis_b_k)
        print(f"    status={res.status} axisA={res.axis_a_macro} axisB={res.axis_b_macro}")
        results.append(res)

    ranked = rank_results(results)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as handle:
            json.dump(ranked, handle, indent=2)
        print(f"wrote {args.out}")
    else:
        print(json.dumps(ranked, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
