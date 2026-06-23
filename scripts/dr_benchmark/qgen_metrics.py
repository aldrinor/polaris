"""Fast, resume-from-cache query-gen metrics (I-qgen-001, GH #1291).

Replaces the 0-vs-0, hours-long EXACT-named-study judge (which read ~24 chunks per uncovered
point => ~1370 GLM calls per method per task) with two FAST metrics that read the BANKED
retrieval cache (resume from checkpoints — no re-fetch):

  1. breadth_recall  : distinct sources + distinct findings a method's queries surfaced, at
                       equal budget. PURE COUNTING — no GLM, instant. Directly answers
                       "which query-gen retrieves MORE" (the query-gen lever).
  2. finding_coverage: FINDING-LEVEL rubric coverage. Builds a COMPACT per-source digest
                       (whole corpus -> ~1 context window) and judges each rubric point against
                       it in ONE parallel GLM call — "does the corpus DISCUSS this finding"
                       (not "cite the exact named paper"). ~57 parallel calls, not ~1370 serial.

Both are deterministic given the cache + (for the judge) the injected llm. Faithfulness engine
untouched — these score query-gen COVERAGE only.
"""

from __future__ import annotations

import json
import os
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Callable

from scripts.dr_benchmark.run_qgen_coverage import _CACHE_DIR, _qkey, _row_text

RetrieveFn = Callable[[str], list[dict]]
LlmFn = Callable[[str], str]


# --------------------------------------------------------------------- resume: cache-only retrieve
def make_cache_only_retrieve(domain: str | None = None, allow_fetch: bool = False) -> RetrieveFn:
    """A retrieve() that RESUMES from the banked retrieval cache.

    Default (allow_fetch=False) is a TRUE resume: a cache miss returns [] and NEVER hits the
    network — fast + free, exact replay of what the killed run banked. allow_fetch=True falls
    back to a live fetch on a miss (to fill partially-cached tasks), still caching the result.
    """
    def retrieve(query: str) -> list[dict]:
        path = os.path.join(_CACHE_DIR, f"{_qkey(query, domain)}.json")
        if os.path.isfile(path):
            with open(path, encoding="utf-8") as handle:
                return json.load(handle)
        if not allow_fetch:
            return []
        # fill-in fetch for partially-cached tasks (drb_76/drb_78) — reuses the real retriever.
        from scripts.dr_benchmark.run_qgen_coverage import make_real_retrieve

        return make_real_retrieve(domain=domain)(query)

    return retrieve


# --------------------------------------------------------------------- metric 1: breadth recall
@dataclass
class BreadthResult:
    distinct_sources: int
    distinct_findings: int
    total_rows: int


def breadth_recall(corpus: list[dict]) -> BreadthResult:
    """Distinct sources + distinct findings a method's corpus carries. No GLM — pure counting.

    A "finding" is a coarse normalized key of a source's contributed text (its title+statement+
    grounding span); near-duplicate rows collapse, so this rewards a method that surfaces
    genuinely DIFFERENT evidence, not just more rows of the same thing.
    """
    urls: set[str] = set()
    findings: set[str] = set()
    for row in corpus:
        url = (row.get("url") or "").strip()
        if url:
            urls.add(url)
        text = " ".join((_row_text(row) or row.get("text") or "").split()).lower()
        if text:
            findings.add(text[:200])
    return BreadthResult(len(urls), len(findings), len(corpus))


# --------------------------------------------------------------------- metric 2: finding coverage
def build_digest(
    corpus: list[dict], per_source_chars: int | None = None, max_chars: int | None = None
) -> str:
    """A COMPACT corpus digest: one capped line per source, total bounded well under a context window.

    This is what makes the judge fast: instead of chunking 1.15M chars into ~24 windows and
    re-reading them per point, the whole corpus is compressed to a SMALL digest the judge reads
    once per BATCH of points. For a finding-level topic match, a source's title + a short head of
    its statement/span is enough — so the digest stays ~10K tokens, keeping each judge call fast
    (a 35K-token digest made calls 5-33s each; a small digest makes them ~2-4s).
    """
    per_source_chars = per_source_chars or int(os.getenv("PG_QGEN_DIGEST_PER_SOURCE_CHARS", "220"))
    max_chars = max_chars or int(os.getenv("PG_QGEN_DIGEST_MAX_CHARS", "45000"))
    lines: list[str] = []
    for row in corpus:
        text = " ".join((_row_text(row) or row.get("text") or "").split())[:per_source_chars]
        if text:
            lines.append(text)
    return "\n".join(lines)[:max_chars]


@dataclass
class FindingCoverageResult:
    covered: int
    total: int
    coverage: float
    per_point: list[dict] = field(default_factory=list)


def _parse_batch_answers(text: str, n: int) -> list[bool]:
    """Parse a batched judge reply into n booleans. Accepts lines like '1: YES' / '2. no' / 'YES'.

    Robust to extra prose: scans for the first n YES/NO tokens in order. Missing answers -> False
    (under-claim coverage on a malformed reply, never over-claim)."""
    out: list[bool] = []
    for raw in (text or "").splitlines():
        u = raw.strip().upper()
        if not u:
            continue
        # strip a leading "<n>:" / "<n>." index if present
        for sep in (":", ".", ")"):
            if sep in u[:4]:
                u = u.split(sep, 1)[1].strip()
                break
        if u.startswith("YES"):
            out.append(True)
        elif u.startswith("NO"):
            out.append(False)
        if len(out) >= n:
            break
    while len(out) < n:
        out.append(False)
    return out[:n]


def finding_coverage(
    points: list[str], digest: str, llm: LlmFn, workers: int | None = None,
    batch_size: int | None = None,
) -> FindingCoverageResult:
    """FINDING-LEVEL rubric coverage: does the corpus DISCUSS each required finding?

    SPEED: points are judged in BATCHES (default 8/call) — one digest read covers many points —
    and batches run in PARALLEL (bounded by `workers`). 57 points -> ~7 calls instead of 57. The
    judge is reasoning-light (the injected llm should minimize reasoning; this is a YES/NO topic
    match). Finding-level — the corpus need not cite the exact named study, only discuss the same
    phenomenon/area — so it DISCRIMINATES between query-gen methods (the exact-paper match was 0
    for both). Missing/ambiguous answers default to NO (under-claim, never over-claim).
    """
    workers = workers or int(os.getenv("PG_QGEN_JUDGE_WORKERS", "8"))
    batch_size = batch_size or int(os.getenv("PG_QGEN_JUDGE_BATCH_SIZE", "8"))
    batches = [points[i : i + batch_size] for i in range(0, len(points), batch_size)]

    def judge_batch(batch: list[str]) -> list[bool]:
        numbered = "\n".join(f"{i+1}. {p}" for i, p in enumerate(batch))
        prompt = (
            "You are scoring RETRIEVAL COVERAGE at the FINDING level. Below is a digest of a "
            "RETRIEVED corpus, then a numbered list of REQUIRED points a complete report must "
            "cover. For EACH point answer strictly YES or NO: does the corpus DISCUSS the topic / "
            "finding / claim that point describes (the SAME phenomenon or research area)? It need "
            "NOT cite the exact named study — a finding-level topical match counts; answer NO only "
            "if the corpus does not address that finding at all.\n\n"
            f"RETRIEVED CORPUS DIGEST:\n{digest}\n\n"
            f"REQUIRED POINTS:\n{numbered}\n\n"
            "Reply with exactly one line per point in the form '<number>: YES' or '<number>: NO'."
        )
        return _parse_batch_answers(llm(prompt) or "", len(batch))

    with ThreadPoolExecutor(max_workers=workers) as ex:
        batch_results = list(ex.map(judge_batch, batches))

    flags: list[bool] = []
    for r in batch_results:
        flags.extend(r)
    flags = flags[: len(points)]

    per_point = [
        {"point": p, "point_preview": p[:160], "covered": bool(c)} for p, c in zip(points, flags)
    ]
    covered = sum(1 for c in flags if c)
    total = len(points)
    return FindingCoverageResult(
        covered=covered, total=total, coverage=(covered / total) if total else 0.0,
        per_point=per_point,
    )
