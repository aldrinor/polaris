"""run_bakeoff.py -- score each extractor candidate, write ranked results.

Loads each candidate by its EXACT pip/HF id, runs it on every labeled page in
the fixture (BYTE-IDENTICAL HTML per candidate -- isolation), scores with the
metric, and writes a ranked results JSON.

Honest flags (LAW II):
  * needs_gpu candidates (MinerU-HTML, ReaderLM-v2) are gated behind --allow-gpu;
    without it they are registered-but-SKIPPED (status="skipped_needs_gpu"),
    NEVER given a faked score.
  * a candidate that load-fails records status="dead" with the error, NEVER a
    believable-low score (the drb_72 anti-pattern).

Decision rule (brief §3): among candidates that do NOT regress recall below the
Trafilatura incumbent floor (minus tolerance, §-1.3 weight-not-filter), winner =
highest F1, ties broken toward the DETERMINISTIC/extractive extractor. The
generative yardstick (ReaderLM-v2) is STRUCTURALLY excluded from winner
selection by role -- a higher F1 can never crown it.

GATE-0 must be GREEN before any score here is trusted: run_bakeoff refuses to
emit a winner if gate0 is red (anti-drb_72).

Faithfulness engine is never touched -- this scores extractor OUTPUT vs gold.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict, dataclass, field

from _candidates import (
    Candidate,
    ExtractorLoadError,
    build_candidate_registry,
    is_eligible_to_win,
)
from _scoring import (
    OfficialScorerStatus,
    average,
    build_official_runner,
    check_faithfulness,
    locate_official_scorer,
    rouge_n,
    score_official_or_fallback,
)
from gate0 import run_gate0

# §-1.3 weight-not-filter: a candidate may not regress recall below the
# incumbent floor minus this tolerance. Env-overridable, pre-registered.
RECALL_REGRESSION_TOLERANCE = float(os.getenv("PG_CE_BAKEOFF_RECALL_TOL", "0.02"))

# A candidate is win-eligible unless it has a SYSTEMATIC faithfulness failure
# (advisor blocker 2): a single per-page substring miss must NOT hard-drop the
# lead candidate. Below this fraction of faithful pages => systematic failure
# (a genuinely non-extractive path), which legitimately disqualifies it.
FAITHFULNESS_SYSTEMATIC_FLOOR = float(
    os.getenv("PG_CE_BAKEOFF_FAITH_SYSTEMATIC_FLOOR", "0.80")
)


@dataclass
class PageScore:
    page_id: str
    f1: float  # PRIMARY official ROUGE-N F1 (or flagged re-derivation)
    scorer_used: str  # "official" | "fallback_rederived"
    recall: float  # decomposed completeness (re-derivation half; NaN under official)
    precision: float
    junk_fraction: float
    faithful: bool
    verbatim_fraction: float


@dataclass
class CandidateResult:
    name: str
    key: str
    impl_id: str
    license: str
    role: str
    eligible_to_win: bool
    status: str  # scored | skipped_needs_gpu | dead | needs_fixture
    detail: str = ""
    mean_f1: float = 0.0
    mean_recall: float = 0.0
    mean_precision: float = 0.0
    mean_junk_fraction: float = 0.0
    faithful_fraction: float = 0.0
    scorer_used: str = ""  # official | fallback_rederived (honest provenance)
    page_count: int = 0
    pages: list = field(default_factory=list)


def _load_clinical_fixture(fixture_path: str) -> list[dict]:
    """Load labeled clinical pages (label_status == 'labeled' only are scored)."""
    pages: list[dict] = []
    if not os.path.isfile(fixture_path):
        return pages
    with open(fixture_path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            if rec.get("label_status") == "labeled" and rec.get("gold_main_body_md"):
                pages.append(rec)
    return pages


def score_candidate_on_pages(
    candidate: Candidate,
    pages: list[dict],
    status: OfficialScorerStatus,
    official_runner=None,
) -> CandidateResult:
    """Score one candidate across all labeled pages; never fakes a dead score.

    PRIMARY metric = the OFFICIAL WebMainBench ROUGE-N (N=5, jieba) via
    score_official_or_fallback when the cloned scorer is present; otherwise the
    FLAGGED re-derivation at N=5 (scorer_used recorded per page+result). The
    decomposed recall/precision halves come from the pure-Python pass and are
    used only for the §-1.3 recall non-regression floor + junk reporting.
    """
    base = CandidateResult(
        name=candidate.name,
        key=candidate.key,
        impl_id=candidate.impl_id,
        license=candidate.license,
        role=candidate.role,
        eligible_to_win=is_eligible_to_win(candidate),
        status="scored",
    )
    page_scores: list[PageScore] = []
    scorer_kinds: set[str] = set()
    for page in pages:
        html = page.get("raw_html", "")
        gold = page.get("gold_main_body_md", "")
        try:
            output = candidate.extract(html)
        except ExtractorLoadError as exc:
            base.status = "dead"
            base.detail = f"load/import failure: {exc}"
            return base  # FAIL LOUD -- no believable-low score
        except Exception as exc:  # noqa: BLE001
            base.status = "dead"
            base.detail = f"crashed: {exc!r}"
            return base
        primary = score_official_or_fallback(output, gold, status, official_runner=official_runner)
        scorer_kinds.add(primary.scorer_used)
        halves = rouge_n(output, gold)  # decomposed recall/precision/junk
        faith = check_faithfulness(output, html)
        page_scores.append(
            PageScore(
                page_id=page.get("page_id", ""),
                f1=primary.f1,
                scorer_used=primary.scorer_used,
                recall=halves.recall,
                precision=halves.precision,
                junk_fraction=halves.junk_fraction,
                faithful=faith.is_faithful,
                verbatim_fraction=faith.verbatim_fraction,
            )
        )
    base.page_count = len(page_scores)
    base.mean_f1 = average(p.f1 for p in page_scores)
    base.mean_recall = average(p.recall for p in page_scores)
    base.mean_precision = average(p.precision for p in page_scores)
    base.mean_junk_fraction = average(p.junk_fraction for p in page_scores)
    base.faithful_fraction = average(1.0 if p.faithful else 0.0 for p in page_scores)
    # If ANY page fell back, the candidate's headline F1 is honestly a mix; record
    # the strictest honest label (fallback if any page used it).
    base.scorer_used = "fallback_rederived" if "fallback_rederived" in scorer_kinds else "official"
    base.pages = [asdict(p) for p in page_scores]
    return base


def select_winner(
    results: list[CandidateResult], incumbent_key: str = "trafilatura"
) -> dict:
    """Apply the decision rule: recall non-regression floor + highest F1, ties
    to the deterministic extractor; generative yardstick excluded by role."""
    incumbent = next((r for r in results if r.key == incumbent_key and r.status == "scored"), None)
    recall_floor = (incumbent.mean_recall - RECALL_REGRESSION_TOLERANCE) if incumbent else 0.0

    # Eligibility: extractive non-yardstick role (structural never-crown) AND no
    # SYSTEMATIC faithfulness failure. A single per-page substring miss must NOT
    # hard-drop the lead (advisor blocker 2 / §-1.3 no-new-hard-filter); only a
    # candidate that is non-extractive across many pages is disqualified.
    eligible = [
        r
        for r in results
        if r.eligible_to_win
        and r.status == "scored"
        and r.faithful_fraction >= FAITHFULNESS_SYSTEMATIC_FLOOR
    ]
    # §-1.3: drop anyone who regresses recall below the incumbent floor.
    passing = [r for r in eligible if r.mean_recall >= recall_floor]
    if not passing:
        return {
            "winner": None,
            "reason": "no eligible scored candidate cleared the recall non-regression floor",
            "recall_floor": recall_floor,
            "faithfulness_systematic_floor": FAITHFULNESS_SYSTEMATIC_FLOOR,
        }
    # Highest F1; tie-break already favors extractive (all eligible are extractive).
    winner = max(passing, key=lambda r: (r.mean_f1, r.mean_recall))
    return {
        "winner": winner.key,
        "winner_f1": winner.mean_f1,
        "winner_scorer_used": winner.scorer_used,
        "recall_floor": recall_floor,
        "faithfulness_systematic_floor": FAITHFULNESS_SYSTEMATIC_FLOOR,
        "incumbent": incumbent_key,
        "note": (
            "generative yardstick excluded by role (structural never-crown); "
            "no SYSTEMATIC faithfulness failure required (single-page miss never hard-drops); "
            "recall non-regression enforced (§-1.3); PRIMARY F1 = official scorer when present."
        ),
    }


def run(*, fixture_path: str, out_path: str, allow_gpu: bool, require_gate0: bool) -> dict:
    candidates = build_candidate_registry()

    # GATE-0 must be green before any score is trusted (anti-drb_72).
    gate0_report = run_gate0(allow_gpu=allow_gpu, candidates=candidates)
    if require_gate0 and not gate0_report["all_passed"]:
        failed = [r["name"] for r in gate0_report["results"] if not r["passed"]]
        raise SystemExit(
            f"GATE-0 RED ({failed}) -- refusing to score (anti-drb_72). "
            "Fix the harness/candidates before trusting any number."
        )

    pages = _load_clinical_fixture(fixture_path)

    # PRIMARY scorer = official WebMainBench (N=5 jieba) when the cloned repo is
    # present; built once and injected. Absent -> FLAGGED re-derivation per result.
    status = locate_official_scorer(os.getenv("PG_WEBMAINBENCH_REPO") or None)
    official_runner = build_official_runner(status)

    results: list[CandidateResult] = []
    for cand in candidates:
        if cand.needs_gpu and not allow_gpu:
            results.append(
                CandidateResult(
                    name=cand.name,
                    key=cand.key,
                    impl_id=cand.impl_id,
                    license=cand.license,
                    role=cand.role,
                    eligible_to_win=is_eligible_to_win(cand),
                    status="skipped_needs_gpu",
                    detail="registered but skipped (no GPU host); never faked.",
                )
            )
            continue
        if not pages:
            # No labeled gold yet -> honest needs_fixture, not a fake score.
            results.append(
                CandidateResult(
                    name=cand.name,
                    key=cand.key,
                    impl_id=cand.impl_id,
                    license=cand.license,
                    role=cand.role,
                    eligible_to_win=is_eligible_to_win(cand),
                    status="needs_fixture",
                    detail="no labeled clinical pages; clinical-axis score not trusted.",
                )
            )
            continue
        results.append(score_candidate_on_pages(cand, pages, status, official_runner))

    scored = [r for r in results if r.status == "scored"]
    ranked = sorted(scored, key=lambda r: r.mean_f1, reverse=True)
    winner = select_winner(results) if scored else {"winner": None, "reason": "no scored candidates"}

    report = {
        "layer": "content_extraction",
        "gate0_passed": gate0_report["all_passed"],
        "fixture_path": fixture_path,
        "labeled_page_count": len(pages),
        "primary_scorer": "official" if official_runner is not None else "fallback_rederived (FLAGGED)",
        "primary_scorer_reason": status.reason,
        "metric_components": {
            "general_primary": "WebMainBench OFFICIAL ROUGE-N F1 (N=5, jieba)",
            "general_fallback": "pure-Python ROUGE-N (N=5), FLAGGED when official absent",
            "clinical_secondary_teds": (
                "TEDS table-fidelity (clinical subset) -- needs_dep (apted/easyted) + "
                "needs_fixture (gold table trees); registered, honestly flagged not-yet-wired."
            ),
            "faithfulness": "verbatim-substring vs source visible text (harness-internal)",
        },
        "winner_selection": winner,
        "ranked_keys": [r.key for r in ranked],
        "results": [asdict(r) for r in results],
        "lineage_sha256": gate0_report["lineage"]["lineage_sha256"],
    }
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run content_extraction bake-off")
    parser.add_argument(
        "--fixture",
        default=os.getenv(
            "PG_CE_BAKEOFF_FIXTURE",
            "outputs/ret_bakeoff/content_extraction/clinical_gold_fixture.jsonl",
        ),
    )
    parser.add_argument(
        "--out",
        default=os.getenv(
            "PG_CE_BAKEOFF_RESULTS",
            "outputs/ret_bakeoff/content_extraction/results.json",
        ),
    )
    parser.add_argument(
        "--allow-gpu",
        action="store_true",
        default=os.getenv("PG_CE_BAKEOFF_ALLOW_GPU", "0") == "1",
    )
    parser.add_argument(
        "--no-require-gate0",
        action="store_true",
        help="(diagnostic only) do not abort on a red GATE-0; never use for a trusted run",
    )
    args = parser.parse_args(argv)

    report = run(
        fixture_path=args.fixture,
        out_path=args.out,
        allow_gpu=args.allow_gpu,
        require_gate0=not args.no_require_gate0,
    )
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
