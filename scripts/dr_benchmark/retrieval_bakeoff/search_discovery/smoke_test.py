"""search_discovery bake-off — OFFLINE stub smoke (no network, no keys, no GPU).

I-ret-002 (#1294), layer 1 of 7. Proves, fully offline with MOCKED providers and a SYNTHETIC
gold fixture:
  1. all four layer files import + py_compile clean;
  2. the GATE-0 scorer-math canaries pass (positive/negative/normalization/lineage + the two
     corrected-metric canaries: set-OR partial-hit, same-domain-different-page-negative);
  3. the per-candidate LIVENESS canary correctly FAILS LOUD on a simulated stub candidate
     (empty / constant / keyless-claims-live) and SKIPS a no_key candidate without failing;
  4. the recall scorer ranks a good provider above a junk provider on synthetic data;
  5. the fixture builder runs offline with a synthetic resolver and produces a sha-pinned gold.

Exit 0 iff ALL pass; non-zero + a printed reason otherwise. No model, no API, no network.
"""

from __future__ import annotations

import json
import os
import py_compile
import sys
import tempfile
from dataclasses import dataclass, field

_HERE = os.path.dirname(os.path.abspath(__file__))
# .../scripts/dr_benchmark/retrieval_bakeoff/search_discovery -> .../scripts/dr_benchmark
_WORKTREE_DR_BENCHMARK = os.path.abspath(os.path.join(_HERE, "..", ".."))


def _find_seam_root() -> str:
    """Return a checkout root that actually contains the reused seams (gate0_lineage.py).

    On a thin git worktree the seams live in the main checkout, not the worktree; on a full
    checkout the worktree root IS the seam root. No network, no install — just a file probe.
    """
    candidates = [
        os.path.abspath(os.path.join(_HERE, "..", "..", "..", "..")),  # this checkout's root
        os.environ.get("POLARIS_REPO_ROOT", ""),
        r"C:\POLARIS",  # the canonical main checkout (seam source on a thin worktree)
        "/c/POLARIS",
    ]
    for root in candidates:
        if root and os.path.isfile(
            os.path.join(root, "scripts", "dr_benchmark", "gate0_lineage.py")
        ):
            return root
    raise RuntimeError(
        "could not locate a checkout containing scripts/dr_benchmark/gate0_lineage.py "
        "(set POLARIS_REPO_ROOT)"
    )


def _bootstrap_imports() -> str:
    """Make BOTH the reused seams and this worktree's layer package importable; return seam_root.

    main's ``scripts/dr_benchmark/__init__.py`` makes ``scripts.dr_benchmark`` a REGULAR package
    pinned to the seam checkout, so a thin worktree's copy is invisible by sys.path alone. The
    standard namespace-extension mechanism: import the regular package from the seam root, then
    EXTEND its ``__path__`` with this worktree's ``dr_benchmark`` dir so the namespace children
    (``retrieval_bakeoff.search_discovery.*``) resolve from the worktree while the seams resolve
    from main. A no-op when run from a full checkout (the two dirs coincide).
    """
    seam_root = _find_seam_root()
    if seam_root not in sys.path:
        sys.path.insert(0, seam_root)
    import scripts.dr_benchmark as _drb  # regular pkg pinned to seam_root

    if _WORKTREE_DR_BENCHMARK not in list(_drb.__path__):
        _drb.__path__.append(_WORKTREE_DR_BENCHMARK)
    return seam_root


_SEAM_ROOT = _bootstrap_imports()
# Absolute path to the canonical DRB-II gold file (DEFAULT_TASKS_PATH is repo-relative; resolve
# it against the seam checkout so the lineage canary + fixture build work from any cwd).
ABS_TASKS = os.path.join(
    _SEAM_ROOT, "third_party", "DeepResearch-Bench-II", "tasks_and_rubrics.jsonl"
)

from scripts.dr_benchmark.retrieval_bakeoff.search_discovery import build_fixture as bf
from scripts.dr_benchmark.retrieval_bakeoff.search_discovery import gate0
from scripts.dr_benchmark.retrieval_bakeoff.search_discovery import run_bakeoff as rb


LAYER_FILES = ("build_fixture.py", "run_bakeoff.py", "gate0.py", "smoke_test.py")


# ---------------------------------------------------------------------------
# Synthetic (mocked) providers — NO network. Each implements SearchProvider.
# ---------------------------------------------------------------------------


@dataclass
class GoodSyntheticProvider:
    """A realistic backend: distinct, relevant, non-constant ranked lists per query."""

    name: str = "good_synthetic"
    runnable: str = "yes"
    # Map a known liveness probe to a relevant ranked list; gold URLs for the scoring slug.
    _table: dict = field(default_factory=lambda: {
        "World Health Organization official website": [
            {"url": "https://www.who.int/", "title": "WHO", "snippet": ""},
            {"url": "https://en.wikipedia.org/wiki/WHO", "title": "WHO wiki", "snippet": ""},
        ],
        "National Institutes of Health official website": [
            {"url": "https://www.nih.gov/", "title": "NIH", "snippet": ""},
            {"url": "https://pubmed.ncbi.nlm.nih.gov/", "title": "PubMed", "snippet": ""},
        ],
    })

    def search(self, query: str):
        if query in self._table:
            return list(self._table[query])
        # Scoring queries: return the gold DOI so recall is high.
        return [
            {"url": "https://doi.org/10.1234/smoke.2025.001", "title": "gold", "snippet": ""},
            {"url": "https://example.com/noise", "title": "noise", "snippet": ""},
        ]


@dataclass
class JunkSyntheticProvider:
    """A backend that returns only unrelated junk for the scoring queries (low recall)."""

    name: str = "junk_synthetic"
    runnable: str = "yes"

    def search(self, query: str):
        if "World Health" in query:
            return [{"url": "https://www.who.int/", "title": "WHO", "snippet": ""}]
        if "National Institutes" in query:
            return [{"url": "https://www.nih.gov/", "title": "NIH", "snippet": ""}]
        return [{"url": "https://spam-seo.net/clickbait", "title": "junk", "snippet": ""}]


@dataclass
class EmptyStubProvider:
    """Claims runnable but returns EMPTY (keyless/stub) — liveness MUST fail loud."""

    name: str = "empty_stub"
    runnable: str = "yes"

    def search(self, query: str):
        return []


@dataclass
class ConstantStubProvider:
    """Claims runnable, returns a FIXED believable list regardless of query — must fail loud."""

    name: str = "constant_stub"
    runnable: str = "yes"

    def search(self, query: str):
        return [
            {"url": "https://www.who.int/", "title": "WHO", "snippet": ""},
            {"url": "https://www.nih.gov/", "title": "NIH", "snippet": ""},
        ]


@dataclass
class NoKeyProvider:
    """A no_key candidate — must be SKIPPED, never failed, never faked."""

    name: str = "tavily_nokey"
    runnable: str = "no_key"

    def search(self, query: str):
        raise AssertionError("no_key provider.search must NOT be called")


# ---------------------------------------------------------------------------
# Checks.
# ---------------------------------------------------------------------------


def check_py_compile() -> None:
    for fn in LAYER_FILES:
        py_compile.compile(os.path.join(_HERE, fn), doraise=True)


def check_scorer_math_canaries() -> list[str]:
    # The lineage canary reads the canonical gold file; pass the absolute path (cwd-independent).
    return gate0.run_scorer_math_canaries(tasks_path=ABS_TASKS)


def check_liveness_fails_on_stub() -> None:
    """The CORE anti-drb_72 proof: stub candidates FAIL LOUD; no_key skips; good passes."""
    # 1. A good provider passes liveness on its own.
    good = gate0.liveness_check_one(GoodSyntheticProvider())
    assert good.status == "live", f"good provider should be live, got {good.status}: {good.detail}"

    # 2. no_key is skipped, not failed.
    nokey = gate0.liveness_check_one(NoKeyProvider())
    assert nokey.status == "skipped_no_key", f"no_key should skip, got {nokey.status}"

    # 3. Empty stub FAILS.
    empty = gate0.liveness_check_one(EmptyStubProvider())
    assert empty.status == "FAILED", f"empty stub MUST fail, got {empty.status}"

    # 4. Constant stub FAILS (non-constant check).
    const = gate0.liveness_check_one(ConstantStubProvider())
    assert const.status == "FAILED", f"constant stub MUST fail, got {const.status}"

    # 5. The aggregate raises GateZeroError when a declared-runnable stub is present.
    raised = False
    try:
        gate0.run_liveness_canaries([GoodSyntheticProvider(), EmptyStubProvider(), NoKeyProvider()])
    except gate0.GateZeroError:
        raised = True
    assert raised, "run_liveness_canaries MUST raise on a declared-runnable stub"

    # 6. And does NOT raise when only good + no_key are present.
    ok = gate0.run_liveness_canaries([GoodSyntheticProvider(), NoKeyProvider()])
    statuses = {r.name: r.status for r in ok}
    assert statuses.get("good_synthetic") == "live"
    assert statuses.get("tavily_nokey") == "skipped_no_key"


def _write_synthetic_gold(path: str) -> None:
    """A tiny synthetic gold fixture for the recall-scoring smoke (idx 56)."""
    rows = [
        {
            "idx": 56, "finding_index": 0, "finding": "cite study 'Smoke Study'",
            "title": "Smoke Study", "confirmation_status": "title_verified",
            "gold_sources": [
                {"kind": "doi_pmid", "doi": "10.1234/smoke.2025.001",
                 "pmid": None, "canonical_url": "https://doi.org/10.1234/smoke.2025.001",
                 "domain": None, "path_slug": None, "title": "Smoke Study"},
            ],
        },
        {
            "idx": 56, "finding_index": 1, "finding": "untitled judge-mapped finding",
            "title": None, "confirmation_status": "judge_proposed_needs_confirm",
            "gold_sources": [],  # excluded from denominator (needs_confirm, no gold)
        },
    ]
    with open(path, "w", encoding="utf-8") as handle:
        handle.write("\n".join(json.dumps(r, sort_keys=True) for r in rows) + "\n")


def check_recall_scorer() -> None:
    """Good provider out-recalls junk on synthetic gold; needs_confirm row excluded."""
    with tempfile.TemporaryDirectory() as tmp:
        gold_path = os.path.join(tmp, "gold.jsonl")
        _write_synthetic_gold(gold_path)
        queries = {"drb_72_ai_labor": ["any held query"]}
        out = rb.run_bakeoff(
            gold_path, queries,
            providers=[GoodSyntheticProvider(), JunkSyntheticProvider()],
            rank_k=20,
        )
        board = {b["provider"]: b["mean_recall_at_k"] for b in out["ranked_board"]}
        assert board["good_synthetic"] == 1.0, f"good should recall 1.0, got {board}"
        assert board["junk_synthetic"] == 0.0, f"junk should recall 0.0, got {board}"
        # The needs_confirm row (no gold) is excluded from the denominator, not silently scored.
        per_slug = out["per_slug_results"][0]
        assert per_slug["total_scorable"] == 1, "only the 1 confirmed-gold row is scorable"
        assert per_slug["n_skipped_needs_confirm"] == 1


def _synthetic_resolver(title: str, context: str):
    """Offline resolver: deterministic, no network. Resolves any title to a fake DOI."""
    if not title:
        return None
    # Simulate an unambiguous resolution.
    return {
        "doi": "10.9999/synthetic." + str(abs(hash(title)) % 100000),
        "pmid": None,
        "canonical_url": "https://doi.org/10.9999/synthetic",
        "matched_title": title, "match_similarity": 1.0,
    }


def check_fixture_builder_offline() -> None:
    """build_fixture runs offline with the synthetic resolver and sha-pins a gold."""
    with tempfile.TemporaryDirectory() as tmp:
        out = os.path.join(tmp, "drb_gold_sources.jsonl")
        manifest = bf.build_fixture(
            out, _synthetic_resolver, slugs=("drb_72_ai_labor",), tasks_path=ABS_TASKS
        )
        assert manifest["fixture_sha256"], "fixture must be sha-pinned"
        assert manifest["n_rows_total"] > 0, "fixture must have rows"
        # The blocked source must NOT appear as a gold member.
        loaded = bf.load_fixture(out)
        assert 56 in loaded, "idx 56 rows must load"
        # Every row that has gold carries a confirmation_status that is not silently 'scored'.
        for row in loaded[56]:
            assert row["confirmation_status"] in (
                "title_verified", "judge_proposed_needs_confirm", "unresolved_needs_confirm",
            )


def main() -> int:
    checks = [
        ("py_compile", check_py_compile),
        ("scorer_math_canaries", check_scorer_math_canaries),
        ("liveness_fails_on_stub", check_liveness_fails_on_stub),
        ("recall_scorer", check_recall_scorer),
        ("fixture_builder_offline", check_fixture_builder_offline),
    ]
    for name, fn in checks:
        try:
            result = fn()
            extra = f" -> {result}" if result else ""
            print(f"[PASS] {name}{extra}")
        except Exception as exc:  # noqa: BLE001 — smoke must report the failing check loudly
            print(f"[FAIL] {name}: {type(exc).__name__}: {exc}", file=sys.stderr)
            return 1
    print("SMOKE GREEN: search_discovery layer (offline, mocked) — all 5 checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
