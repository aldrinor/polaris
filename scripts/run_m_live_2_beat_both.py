"""M-LIVE-2: BEAT-BOTH head-to-head vs ChatGPT DR + Gemini DR.

Loads three manifests:
  - POLARIS: from outputs/m_live_1_smoke/clinical/clinical_tirzepatide_t2dm/manifest.json
  - ChatGPT: extracted from state/compare_chatgpt_dr.txt
  - Gemini:  extracted from state/compare_gemini_dr.txt

Runs `score_run(...)` on each, then per-dimension verdict:
  - BEAT-BOTH:   POLARIS strictly above both competitors
  - BEAT-ONE:    POLARIS above one but not both
  - TIE:         POLARIS within tolerance of competitors
  - BEHIND:      POLARIS strictly below at least one competitor

Output:
  - outputs/m_live_2_beat_both/manifest.json (per-dimension
    verdict, raw scores, deltas)

Per `docs/full_online_plan_FINAL.md` M-LIVE-2:
  - 3 score_run + 2 diff_dimension_scores calls
  - Codex review: independently re-extracts competitor manifests;
    risk flagged: extraction normalization can invalidate verdict
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.polaris_graph.audit_ir.beat_both_scoring import (  # noqa: E402
    BEAT_BOTH_SCORERS,
    DimensionScore,
    diff_dimension_scores,
    score_run,
    tolerance_for,
)
from src.polaris_graph.audit_ir.competitor_manifest_extractor import (  # noqa: E402
    extract_competitor_manifest,
)


POLARIS_SMOKE_ROOT = REPO_ROOT / "outputs" / "m_live_1_smoke"


def _find_latest_polaris_manifest_path() -> Path:
    """Find the latest M-LIVE-1 smoke run's manifest.

    v3 R2 P1 fix: order by the timestamp embedded in the dir name
    (`run_YYYYMMDD_HHMMSS`), NOT by `st_mtime`. mtime is mutable —
    `git checkout`, `cp -r`, or `touch` change it without changing
    the run identity. The timestamp suffix IS the run identity per
    M-LIVE-1's `time.strftime("%Y%m%d_%H%M%S")` convention.

    Falls back to the canonical baseline at
    `tests/fixtures/m_live_4_baseline/` so M-LIVE-2 can be exercised
    offline / in CI without a fresh smoke run.
    """
    if POLARIS_SMOKE_ROOT.exists():
        # Sort by name (timestamp string is lexicographically equal
        # to chronological for the YYYYMMDD_HHMMSS format).
        run_dirs = sorted(
            (p for p in POLARIS_SMOKE_ROOT.glob("run_*") if p.is_dir()),
            key=lambda p: p.name,
            reverse=True,
        )
        for rd in run_dirs:
            manifests = list(rd.rglob("manifest.json"))
            if manifests:
                return manifests[0]
    fixture = REPO_ROOT / "tests" / "fixtures" / "m_live_4_baseline"
    if fixture.exists():
        manifests = list(fixture.rglob("manifest.json"))
        if manifests:
            return manifests[0]
    raise SystemExit(
        "no POLARIS manifest found. Run "
        "scripts/run_m_live_1_smoke.py first, or commit a baseline "
        "to tests/fixtures/m_live_4_baseline/"
    )


POLARIS_MANIFEST_PATH = _find_latest_polaris_manifest_path()
CHATGPT_DR_PATH = REPO_ROOT / "state" / "compare_chatgpt_dr.txt"
GEMINI_DR_PATH = REPO_ROOT / "state" / "compare_gemini_dr.txt"

OUT_DIR = REPO_ROOT / "outputs" / "m_live_2_beat_both"


def _load_polaris_manifest() -> dict[str, Any]:
    """Load + stitch POLARIS artifacts into a single manifest dict
    that `beat_both_scoring.score_run()` understands.

    POLARIS V30 emits:
      - manifest.json (top-level run summary)
      - live_corpus_dump.json (citations with URLs, list of dicts)
      - bibliography.json (statements with tier, list of dicts)
      - report.md (prose with [N] citation markers)

    M-D9 BEAT-BOTH expects a manifest with `citations` /
    `evidence` / `report.citations` keyed list of dicts with
    `url` field, plus `claims` / `sections` / `tables`.

    This stitcher unifies the V30 outputs into that shape.
    """
    if not POLARIS_MANIFEST_PATH.exists():
        raise SystemExit(
            f"POLARIS manifest not found at {POLARIS_MANIFEST_PATH}. "
            "Run M-LIVE-1 smoke first via "
            "scripts/run_m_live_1_smoke.py"
        )
    with POLARIS_MANIFEST_PATH.open(encoding="utf-8") as f:
        manifest = json.load(f)

    run_dir = POLARIS_MANIFEST_PATH.parent

    citations: list[dict[str, Any]] = []
    corpus_path = run_dir / "live_corpus_dump.json"
    if corpus_path.exists():
        with corpus_path.open(encoding="utf-8") as f:
            corpus = json.load(f)
        if isinstance(corpus, list):
            for entry in corpus:
                if isinstance(entry, dict) and entry.get("url"):
                    citations.append({
                        "url": entry["url"],
                        "tier": entry.get("tier"),
                        "title": entry.get("title"),
                    })
    manifest["citations"] = citations

    bib_path = run_dir / "bibliography.json"
    if bib_path.exists():
        with bib_path.open(encoding="utf-8") as f:
            bib = json.load(f)
        if isinstance(bib, list):
            manifest["claims"] = [
                {
                    "raw": entry.get("statement", ""),
                    "n": None,
                    "baseline": None,
                    "endpoint": None,
                    "ci": None,
                    "tier": entry.get("tier"),
                    "evidence_id": entry.get("evidence_id"),
                }
                for entry in bib if isinstance(entry, dict)
            ]

    # v4 R3 P1 fix: use `_extract_sections()` and `_extract_tables()`
    # DIRECTLY (the same functions competitor manifests pass through),
    # not just the underlying regex. v3 inlined `_SECTION_HEADER_RE`
    # but skipped `_extract_sections`'s 80-char + digit-only filters,
    # producing an off-by-1 vs the competitor surface (the report's
    # 132-char H1 was counted by v3 but dropped by competitor rules).
    # v4 calls the same helper functions on POLARIS report.md as
    # the competitor extractor calls on competitor prose →
    # identical extraction semantics on both sides.
    sections: list[dict[str, str]] = []
    tables: list[dict[str, Any]] = []
    report_md_path = run_dir / "report.md"
    body_text: str | None = None
    if report_md_path.exists():
        try:
            body_text = report_md_path.read_text(encoding="utf-8")
            from src.polaris_graph.audit_ir.competitor_manifest_extractor import (
                _extract_sections,
                _extract_tables,
            )
            sections = _extract_sections(body_text)
            tables = _extract_tables(body_text)
        except Exception:
            body_text = None
    manifest["sections"] = sections
    manifest["tables"] = tables

    # v2 R1 P1 #2 fix: M-D9 narrative_length / contradiction
    # scorers read `report.body` / `body`, NOT
    # `report.narrative_word_count`. v1 only populated word-count
    # so both scorers returned 0 across all 3 manifests.
    # v2 also populates `report.body` with the actual narrative.
    if body_text is not None:
        manifest.setdefault("report", {})
        manifest["report"]["narrative_word_count"] = (
            len(body_text.split())
        )
        manifest["report"]["body"] = body_text

    return manifest


def _load_competitor(path: Path, source: str) -> dict[str, Any]:
    if not path.exists():
        raise SystemExit(
            f"competitor file not found: {path} (source={source})"
        )
    text = path.read_text(encoding="utf-8", errors="replace")
    return extract_competitor_manifest(text, source=source)


def _scores_to_dict(
    scores: dict[str, DimensionScore],
) -> dict[str, dict[str, Any]]:
    return {
        dim: {
            "value": s.value,
            "higher_is_better": s.higher_is_better,
            "rationale": s.rationale,
        }
        for dim, s in scores.items()
    }


def _per_dimension_verdict(
    polaris: dict[str, DimensionScore],
    chatgpt: dict[str, DimensionScore],
    gemini: dict[str, DimensionScore],
) -> dict[str, dict[str, Any]]:
    """Per-dimension verdict logic.

    For each dimension, classify POLARIS vs each competitor as
    AHEAD / TIE / BEHIND (using `tolerance_for(dim)`); aggregate
    into BEAT-BOTH / BEAT-ONE / TIE / BEHIND.

    v2 R1 P1 #3 fix: when all 3 scores are 0.0 on a dimension,
    that dimension is structurally not measurable (e.g. claim_frames
    requires N+baseline+endpoint+CI fields none of the manifests
    populate yet). Report verdict=N/A rather than TIE — TIE would
    falsely imply the comparison is meaningful.
    """
    verdicts: dict[str, dict[str, Any]] = {}
    common = sorted(set(polaris) & set(chatgpt) & set(gemini))
    for dim in common:
        p = polaris[dim]
        c = chatgpt[dim]
        g = gemini[dim]
        tol = tolerance_for(dim)
        if p.value == 0.0 and c.value == 0.0 and g.value == 0.0:
            verdicts[dim] = {
                "verdict": "N/A",
                "polaris": p.value,
                "chatgpt": c.value,
                "gemini": g.value,
                "tolerance": tol,
                "delta_chatgpt": 0.0,
                "delta_gemini": 0.0,
                "vs_chatgpt": "n/a",
                "vs_gemini": "n/a",
                "higher_is_better": p.higher_is_better,
                "rationale": (
                    "All 3 manifests scored 0.0 — dimension not "
                    "measurable on current inputs (likely missing "
                    "extraction support)."
                ),
            }
            continue

        def cmp_one(competitor: DimensionScore) -> str:
            delta = p.value - competitor.value
            if p.higher_is_better:
                if delta > tol:
                    return "ahead"
                if delta < -tol:
                    return "behind"
                return "tie"
            else:
                if delta < -tol:
                    return "ahead"
                if delta > tol:
                    return "behind"
                return "tie"

        vs_chatgpt = cmp_one(c)
        vs_gemini = cmp_one(g)
        ahead_count = sum(
            1 for v in (vs_chatgpt, vs_gemini) if v == "ahead"
        )
        behind_count = sum(
            1 for v in (vs_chatgpt, vs_gemini) if v == "behind"
        )
        if ahead_count == 2:
            verdict = "BEAT-BOTH"
        elif ahead_count == 1 and behind_count == 0:
            verdict = "BEAT-ONE"
        elif behind_count == 2:
            verdict = "BEHIND-BOTH"
        elif behind_count >= 1:
            verdict = "BEHIND"
        else:
            verdict = "TIE"

        verdicts[dim] = {
            "verdict": verdict,
            "polaris": p.value,
            "chatgpt": c.value,
            "gemini": g.value,
            "tolerance": tol,
            "delta_chatgpt": p.value - c.value,
            "delta_gemini": p.value - g.value,
            "vs_chatgpt": vs_chatgpt,
            "vs_gemini": vs_gemini,
            "higher_is_better": p.higher_is_better,
        }
    return verdicts


def _summarize(verdicts: dict[str, dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {
        "BEAT-BOTH": 0, "BEAT-ONE": 0, "TIE": 0,
        "BEHIND": 0, "BEHIND-BOTH": 0, "N/A": 0,
    }
    for v in verdicts.values():
        counts[v["verdict"]] = counts.get(v["verdict"], 0) + 1
    return counts


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 72)
    print("M-LIVE-2 BEAT-BOTH head-to-head")
    print("=" * 72)

    polaris_m = _load_polaris_manifest()
    chatgpt_m = _load_competitor(CHATGPT_DR_PATH, source="chatgpt_dr")
    gemini_m = _load_competitor(GEMINI_DR_PATH, source="gemini_dr")

    print(f"  POLARIS:  {POLARIS_MANIFEST_PATH}")
    print(f"  ChatGPT:  {CHATGPT_DR_PATH}")
    print(f"  Gemini:   {GEMINI_DR_PATH}")
    print()

    polaris_scores = score_run(polaris_m)
    chatgpt_scores = score_run(chatgpt_m)
    gemini_scores = score_run(gemini_m)

    polaris_vs_chatgpt = diff_dimension_scores(
        chatgpt_scores, polaris_scores,
    )
    polaris_vs_gemini = diff_dimension_scores(
        gemini_scores, polaris_scores,
    )

    verdicts = _per_dimension_verdict(
        polaris_scores, chatgpt_scores, gemini_scores,
    )
    summary = _summarize(verdicts)

    manifest = {
        "milestone": "M-LIVE-2",
        "version": "v4",
        "polaris_manifest_path": str(POLARIS_MANIFEST_PATH),
        "chatgpt_source": str(CHATGPT_DR_PATH),
        "gemini_source": str(GEMINI_DR_PATH),
        "polaris_scores": _scores_to_dict(polaris_scores),
        "chatgpt_scores": _scores_to_dict(chatgpt_scores),
        "gemini_scores": _scores_to_dict(gemini_scores),
        "polaris_vs_chatgpt_verdict": str(
            polaris_vs_chatgpt.verdict.value
            if hasattr(polaris_vs_chatgpt.verdict, "value")
            else polaris_vs_chatgpt.verdict
        ),
        "polaris_vs_gemini_verdict": str(
            polaris_vs_gemini.verdict.value
            if hasattr(polaris_vs_gemini.verdict, "value")
            else polaris_vs_gemini.verdict
        ),
        "per_dimension_verdicts": verdicts,
        "summary": summary,
        "chatgpt_extraction_metadata":
            chatgpt_m.get("extraction_metadata"),
        "gemini_extraction_metadata":
            gemini_m.get("extraction_metadata"),
    }

    manifest_path = OUT_DIR / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    print("=" * 72)
    print("Per-dimension verdicts")
    print("=" * 72)
    for dim in sorted(verdicts):
        v = verdicts[dim]
        print(
            f"  {dim:30}  "
            f"{v['verdict']:14}  "
            f"P={v['polaris']:.1f}  "
            f"C={v['chatgpt']:.1f}  "
            f"G={v['gemini']:.1f}"
        )
    print()
    print("Summary:")
    for k in ("BEAT-BOTH", "BEAT-ONE", "TIE", "BEHIND", "BEHIND-BOTH", "N/A"):
        print(f"  {k:14}: {summary.get(k, 0)}")
    print()
    print(f"manifest: {manifest_path}")
    print("=" * 72)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
