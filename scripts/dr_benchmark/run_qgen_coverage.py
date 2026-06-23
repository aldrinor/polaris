"""Runner for the query-gen COVERAGE-ISOLATION bake-off (I-qgen-001, GH #1291).

Wires the pure harness (qgen_coverage_harness + qgen_methods) to REAL POLARIS retrieval
and a REAL GLM-5.2 coverage judge, then ranks the query-gen methods by required-point
coverage on a canonical DRB-II task. NO report generation / rendering / DeepTRACE judge —
this scores ONLY query generation, on the COVERAGE axis it drives.

Two modes:
  --dry-run  : a deterministic STUB world (no API spend). Proves the wiring end-to-end and
               that the harness ranks correctly. Default.
  --real     : real Serper/S2 retrieval + real GLM-5.2 judge. Requires the env gate
               PG_QGEN_AUTHORIZED_SPEND=1 (the one wall Claude does NOT self-authorize) and
               the usual run keys (.env). Every retrieved query is cached to disk keyed by
               sha256(query) so every method sees IDENTICAL retrieval (isolation) and re-runs
               are free.

The floor method's queries are POLARIS's CURRENT query-gen output (anchor + decomposed
sub-queries via query_decomposer) — the real baseline every candidate must beat.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import sys

from scripts.dr_benchmark.gate0_lineage import SLUG_TO_IDX
from scripts.dr_benchmark.qgen_coverage_harness import (
    CoverageBudget,
    load_required_points,
    run_coverage_test,
)
from scripts.dr_benchmark.qgen_methods import ClosedLoopMethod, FloorMethod

_CACHE_DIR = os.path.join("outputs", "qgen_coverage", "retrieval_cache")
# Bump when the cached row schema or retrieval semantics change, so a stale cache cannot
# silently feed a new run. Part of the cache key alongside the query + domain.
_CACHE_SCHEMA_VERSION = "v1"


def _qkey(query: str, domain: str | None) -> str:
    """Cache key = sha256(schema_version | domain | normalized query). Including domain +
    version stops cross-domain or post-change cache reuse from contaminating a real run."""
    payload = f"{_CACHE_SCHEMA_VERSION}|{domain or ''}|{query.strip().lower()}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]


# --------------------------------------------------------------------------- floor queries
def _sweep_query_spec(slug: str) -> dict:
    """The SWEEP_QUERIES spec dict for a slug (from run_honest_sweep_r3) — fail loud if absent."""
    from scripts.run_honest_sweep_r3 import SWEEP_QUERIES

    for spec in SWEEP_QUERIES:
        if isinstance(spec, dict) and spec.get("slug") == slug:
            return spec
    raise SystemExit(
        f"[qgen] floor: slug {slug!r} not found in SWEEP_QUERIES — cannot build the real "
        f"POLARIS floor query set. Add the slug, or this task is not a sweep query."
    )


def floor_queries(slug: str, question: str) -> list[str]:
    """POLARIS's CURRENT query-gen FACETS for a benchmark slug (the floor under test).

    The live sweep builds the effective list as anchor + build_amplified_query_list(
    hand_authored=q["amplified"], decomposed=decompose_question(question), regulatory, trial)
    (run_honest_sweep_r3.py ~L6156). The hand-authored "amplified" set is the BULK of the real
    floor, so we pull it from SWEEP_QUERIES by slug — benchmarking the ACTUAL current POLARIS
    query-gen, not a crippled decompose-only floor (Codex iter-2 P1).

    Scope: regulatory/trial expansions are DOMAIN-BACKEND augmentations (a retrieval-section
    concern), deliberately excluded so this isolation test measures query GENERATION, not the
    domain backends (a separate section's bake-off). The anchor question is added by FloorMethod,
    so it is NOT in the returned facet list.
    """
    from src.polaris_graph.retrieval.query_decomposer import (
        build_amplified_query_list,
        decompose_question,
    )

    spec = _sweep_query_spec(slug)
    return build_amplified_query_list(
        hand_authored=list(spec.get("amplified", [])),
        decomposed=decompose_question(question),
        regulatory=[],
        trial=[],
    )


# --------------------------------------------------------------------------- real retrieve
def _row_text(row: dict) -> str:
    """Assemble per-source corpus text from a POLARIS evidence row.

    METRIC LABEL (Codex P2): this measures POLARIS GENERATOR-VISIBLE evidence coverage —
    title + statement + the grounding span (direct_quote) that the row actually carries forward,
    NOT the full fetched body. It answers "can the report ground this point on what retrieval
    surfaced", which is the right query-gen coverage signal. If a future test needs raw
    source-retrieval coverage (evidence anywhere in the fetched body, even un-quoted), persist a
    richer ``coverage_text`` field on the row and read it here instead.
    """
    parts = [row.get("title") or "", row.get("statement") or "", row.get("direct_quote") or ""]
    return " ".join(p for p in parts if p).strip()


def make_real_retrieve(domain: str | None = None):
    """A per-query retrieve() backed by run_live_retrieval, cached to disk by query hash."""
    from src.polaris_graph.retrieval.live_retriever import run_live_retrieval

    os.makedirs(_CACHE_DIR, exist_ok=True)

    def retrieve(query: str) -> list[dict[str, str]]:
        cache_path = os.path.join(_CACHE_DIR, f"{_qkey(query, domain)}.json")
        if os.path.isfile(cache_path):
            with open(cache_path, encoding="utf-8") as handle:
                return json.load(handle)
        result = run_live_retrieval(
            research_question=query, amplified_queries=[], domain=domain, anchor_seed=True
        )
        rows = [
            {"url": r.get("source_url") or "", "text": _row_text(r)}
            for r in (result.evidence_rows or [])
        ]
        with open(cache_path, "w", encoding="utf-8") as handle:
            json.dump(rows, handle, ensure_ascii=False)
        return rows

    return retrieve


# --------------------------------------------------------------------------- real GLM judge
def make_glm_llm():
    """An LLM callable (prompt -> text) backed by the locked GLM-5.2 mirror backbone.

    The model is INSTANCE-scoped on OpenRouterClient — generate(prompt, system="", max_tokens=...)
    has NO model/messages kwargs — so we construct the client pinned to z-ai/glm-5.2 (the lock's
    mirror/backbone) and call generate(prompt=...). max_tokens is set GENEROUSLY (a cap, not a
    target — billed by actual usage) per the repo LLM-governance rule: never starve reasoning.
    """
    from src.polaris_graph.llm.openrouter_client import OpenRouterClient

    model = os.getenv("PG_QGEN_BACKBONE_MODEL", "z-ai/glm-5.2")
    client = OpenRouterClient(model=model)
    max_tokens = int(os.getenv("PG_QGEN_LLM_MAX_TOKENS", "8192"))

    def llm(prompt: str) -> str:
        resp = asyncio.run(client.generate(prompt=prompt, max_tokens=max_tokens))
        return getattr(resp, "content", "") or ""

    return llm


def make_glm_coverage_judge():
    """A coverage judge (required_point, corpus_text) -> bool, backed by GLM-5.2.

    Asks: does the corpus contain evidence that lets a report cover this required point? Strict
    YES/NO; defaults to NO on ambiguity (under-claim coverage, never over-claim). The corpus is
    CHUNKED into windows so EVERY source is judged — never truncated to the first N chars, which
    let row order / truncation decide the score (Codex iter-2 P1). Returns True as soon as any
    chunk supports the point (short-circuit). A chunk-count cap is logged HONESTLY if hit.
    """
    llm = make_glm_llm()
    window = int(os.getenv("PG_QGEN_JUDGE_WINDOW_CHARS", "48000"))
    # A SANITY bound only — NOT a truncation point. Every chunk is judged; if a corpus is so
    # large it would exceed this, we FAIL LOUD rather than silently score a prefix (Codex P1-7).
    hard_max_chunks = int(os.getenv("PG_QGEN_JUDGE_HARD_MAX_CHUNKS", "500"))

    def judge(point: str, corpus_text: str) -> bool:
        text = corpus_text or ""
        chunks = [text[i : i + window] for i in range(0, max(len(text), 1), window)] or [""]
        if len(chunks) > hard_max_chunks:
            raise RuntimeError(
                f"[qgen-judge] corpus {len(text)} chars -> {len(chunks)} chunks exceeds the "
                f"sanity bound {hard_max_chunks}. Refusing to silently score a truncated prefix "
                f"(row order must NOT decide coverage). Raise PG_QGEN_JUDGE_HARD_MAX_CHUNKS "
                f"(cost is fine) or investigate the corpus size."
            )
        for chunk in chunks:  # judge EVERY chunk so every source is seen; short-circuit on YES
            prompt = (
                "You are scoring RETRIEVAL COVERAGE. Given a REQUIRED point a complete report "
                "must cover and a CHUNK of the retrieved corpus, answer strictly YES or NO: does "
                "this chunk contain evidence that would let a report COVER the required point? "
                "Answer NO if absent, only tangential, or ambiguous.\n\n"
                f"REQUIRED POINT:\n{point}\n\nCORPUS CHUNK:\n{chunk}\n\n"
                "Answer with one word: YES or NO."
            )
            if (llm(prompt) or "").strip().upper().startswith("YES"):
                return True
        return False

    return judge


# --------------------------------------------------------------------------- stub world
def _stub_retrieve_and_judge():
    """A deterministic stub world for --dry-run (no spend): the floor reaches a couple of
    points; the closed loop's gap re-query reaches more. Proves wiring + ranking only."""
    world = {
        "ai": [{"url": "u/ai", "text": "generative ai labor market evidence positive views"}],
        "negative": [{"url": "u/neg", "text": "negative views job displacement evidence"}],
        "challenge": [{"url": "u/ch", "text": "specific challenges reskilling evidence"}],
        "opportunit": [{"url": "u/op", "text": "future opportunities new occupations evidence"}],
    }

    def retrieve(query: str) -> list[dict[str, str]]:
        q = query.lower()
        out: list[dict[str, str]] = []
        for key, rows in world.items():
            if key in q:
                out += rows
        return out

    def judge(point: str, corpus_text: str) -> bool:
        p = point.lower()
        ct = corpus_text.lower()
        for token in ("positive", "negative", "challenge", "opportunit"):
            if token in p and token in ct:
                return True
        return False

    def stub_llm(prompt: str) -> str:
        if "Decompose" in prompt:
            return "ai labor market\nnegative views\nspecific challenges\nfuture opportunities"
        if "THIN or MISSING" in prompt:
            return "negative views\nspecific challenges\nfuture opportunities"
        return ""

    return retrieve, judge, stub_llm


# --------------------------------------------------------------------------- main
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Query-gen coverage-isolation bake-off")
    parser.add_argument("--slug", default="drb_72_ai_labor", help="benchmark slug (gate0)")
    parser.add_argument("--idx", type=int, default=None, help="override canonical idx")
    parser.add_argument("--real", action="store_true", help="real retrieval + GLM judge (spend)")
    parser.add_argument("--out", default="outputs/qgen_coverage/result.json")
    parser.add_argument("--domain", default=None)
    args = parser.parse_args(argv)

    from scripts.dr_benchmark.gate0_lineage import (
        DRB_SLUGS_WITHOUT_CANONICAL_GOLD,
        assert_drb_slug_registered,
        is_benchmark_slug,
    )

    # Fail loud on an unregistered drb_* benchmark slug (the silent-gap class).
    assert_drb_slug_registered(args.slug)
    if args.slug in DRB_SLUGS_WITHOUT_CANONICAL_GOLD:
        print(
            f"[qgen] slug {args.slug!r} has NO DRB-II gold task (no info_recall rubric) — it "
            f"cannot be coverage-scored. Aborting.",
            file=sys.stderr,
        )
        return 2
    mapped = SLUG_TO_IDX.get(args.slug)
    if is_benchmark_slug(args.slug):
        # A benchmark slug is CANONICALLY bound; --idx may only CONFIRM, never override — the
        # id<->idx mismatch is the exact drb_72 disaster class.
        if args.idx is not None and args.idx != mapped:
            print(
                f"[qgen] REFUSED: --idx {args.idx} != canonical idx {mapped} for benchmark slug "
                f"{args.slug!r}. The id/idx mismatch is the drb_72 disaster class — drop --idx.",
                file=sys.stderr,
            )
            return 2
        idx = mapped  # not None: registration passed AND slug is not in the no-gold set
    else:
        # A non-benchmark slug has no canonical mapping; --idx is REQUIRED to pick the rubric set.
        if args.idx is None:
            print(
                f"[qgen] non-benchmark slug {args.slug!r} needs an explicit --idx (no canonical "
                f"mapping).",
                file=sys.stderr,
            )
            return 2
        idx = args.idx

    required = load_required_points(idx)
    print(f"[qgen] idx={idx} slug={args.slug} required_points={len(required)} mode={'REAL' if args.real else 'DRY-RUN'}")

    if args.real:
        if os.getenv("PG_QGEN_AUTHORIZED_SPEND") != "1":
            print(
                "[qgen] REAL mode needs PG_QGEN_AUTHORIZED_SPEND=1 (operator spend gate). "
                "Claude does NOT self-authorize spend. Aborting.",
                file=sys.stderr,
            )
            return 3
        retrieve = make_real_retrieve(domain=args.domain)
        judge = make_glm_coverage_judge()
        llm = make_glm_llm()
    else:
        retrieve, judge, llm = _stub_retrieve_and_judge()

    # The floor's queries: real POLARIS query-gen in REAL mode; a stub set in dry-run.
    from scripts.dr_benchmark.qgen_coverage_harness import load_canonical_question

    if args.real:
        question = load_canonical_question(idx)
        facets = floor_queries(args.slug, question)
    else:
        facets = ["ai labor market", "negative", "challenge", "opportunit"]

    # Load the DRB-II BLOCKED reference (forbidden source) so it is excluded from EVERY method's
    # corpus before scoring — no method can win coverage via the prohibited source (Codex P1).
    from scripts.dr_benchmark.qgen_coverage_harness import load_blocked_references

    blocked_refs = load_blocked_references(idx)
    if blocked_refs:
        print(
            f"[qgen] BLOCKED reference for idx {idx}: "
            f"{(blocked_refs.get('title') or '')[:70]!r} "
            f"({len(blocked_refs.get('urls', []))} urls) — excluded from every method's corpus"
        )

    methods = [FloorMethod(facets=facets), ClosedLoopMethod(llm=llm)]
    results = run_coverage_test(
        idx, methods, retrieve, judge, budget=CoverageBudget(), blocked_refs=blocked_refs
    )

    print("\n=== COVERAGE RANKING (query-gen isolation) ===")
    for rank, r in enumerate(results, 1):
        print(
            f"  #{rank} {r.method:<26} coverage={r.coverage:.3f} ({r.covered}/{r.total}) "
            f"sources={r.n_sources} queries={r.n_queries_issued} blocked_dropped={r.blocked_dropped}"
        )

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as handle:
        json.dump(
            {
                "idx": idx,
                "slug": args.slug,
                "mode": "real" if args.real else "dry_run",
                "results": [r.__dict__ for r in results],
            },
            handle,
            ensure_ascii=False,
            indent=2,
        )
    print(f"\n[qgen] wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
