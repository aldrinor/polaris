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

Per `docs/full_online_plan.md` M-LIVE-2:
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


POLARIS_SMOKE_ROOT = REPO_ROOT / "outputs" / "phase_g_full_scale"


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

    # v1.1 A.3 (2026-04-30): claim_frames extraction from rendered
    # report.md. Each per-trial subsection has both:
    #   - Deterministic "Field: value [N]." prose with sample_size,
    #     baseline_*, etd_with_uncertainty, primary_endpoint
    #   - Markdown comparison table | trial | N | baseline | comparator | endpoint | effect | [N] |
    # v1.0 set all fields to None → claim_frames N/A across all 3
    # manifests. v1.1 parses the table rows AND the per-trial
    # deterministic prose to populate n / baseline / endpoint / ci.
    bib_path = run_dir / "bibliography.json"
    bib_entries: list[dict[str, Any]] = []
    if bib_path.exists():
        with bib_path.open(encoding="utf-8") as f:
            bib = json.load(f)
        if isinstance(bib, list):
            bib_entries = [b for b in bib if isinstance(b, dict)]

    claims: list[dict[str, Any]] = []
    if (run_dir / "report.md").exists():
        try:
            import re as _re
            text = (run_dir / "report.md").read_text(encoding="utf-8")

            # v1.1 A.5 (post-advisor fix): hoist `_real_value` so BOTH
            # the table branch and the per-subsection branch reject
            # "not stated" / "not extractable" placeholder strings.
            # Without this filter, M-58 placeholder fields (e.g. table
            # cells like "HbA1c not stated") get counted as populated
            # by the M-D9 claim_frames scorer's non-empty check —
            # inflating the count and violating LAW II (no fake
            # working). Per-subsection branch had this filter; table
            # branch did not. This corrects the asymmetry.
            def _real_value(text: str | None) -> str | None:
                if not text:
                    return None
                s = text.strip().rstrip(".,;").strip()
                if not s:
                    return None
                lower = s.lower()
                if "not extractable" in lower:
                    return None
                if "not stated" in lower:
                    return None
                if "not reported" in lower:
                    return None
                return s

            # Extract claims from comparison table rows.
            # Format: | trial | N | baseline | comparator | endpoint | effect_estimate | [N] |
            for m in _re.finditer(
                r"^\|\s*([A-Z][A-Za-z0-9 \-]*?)\s*\|\s*(\d{2,5})\s*\|"
                r"\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|"
                r"\s*([^|]+?)\s*\|\s*\[\d+\]\s*\|\s*$",
                text, flags=_re.MULTILINE,
            ):
                trial_name = m.group(1).strip()
                n_val = int(m.group(2))
                baseline = _real_value(m.group(3))
                comparator = _real_value(m.group(4))
                endpoint = _real_value(m.group(5))
                effect = _real_value(m.group(6))
                ci_val: str | None = None
                if effect:
                    ci_match = _re.search(
                        r"(\([^)]*(?:CI|p<|p=|–|-)[^)]*\)|"
                        r"95%\s*CI[^,;.]*|"
                        r"p\s*[<=]\s*0?\.\d+)",
                        effect,
                    )
                    if ci_match:
                        ci_val = ci_match.group(0).strip()
                    else:
                        ci_val = effect
                # All-fields gate: same as per-subsection branch.
                # A claim_frame requires N + baseline + endpoint + CI
                # all real (not placeholders). If any field is a
                # placeholder, the row contributes 0 to claim_frames.
                if (
                    n_val is not None
                    and baseline
                    and endpoint
                    and ci_val
                ):
                    claims.append({
                        "raw": (
                            f"{trial_name} N={n_val} "
                            f"baseline={baseline} "
                            f"comparator={comparator} "
                            f"endpoint={endpoint} "
                            f"effect={effect}"
                        ),
                        "trial": trial_name,
                        "n": n_val,
                        "baseline": baseline,
                        "endpoint": endpoint,
                        "ci": ci_val,
                        "comparator": comparator,
                    })

            # Also extract from the per-subsection deterministic
            # prose ("### TRIAL-NAME" + "Sample size: 1879 [N]." +
            # "Baseline hba1c: 8.07% [N]." + "Etd with uncertainty:
            # ... [N]." + "Primary endpoint: ... [N].").
            # This catches the 20+ per-trial blocks the comparison
            # table doesn't cover. Trials already in `claims` from
            # the table extractor are deduped by trial name.
            seen_trials = {c["trial"].lower() for c in claims}
            sub_blocks = _re.split(
                r"^###\s+", text, flags=_re.MULTILINE,
            )
            for block in sub_blocks[1:]:
                title_line, _, body = block.partition("\n")
                title = title_line.strip()
                # Trial-style title heuristics: contains a known
                # trial-name token like "SURPASS-N", "SURMOUNT-N",
                # "SELECT", "STEP-N" — clinical-domain shorthand.
                trial_match = _re.search(
                    r"\b([A-Z][A-Z0-9-]{2,})\b", title,
                )
                if not trial_match:
                    continue
                trial_short = trial_match.group(1)
                if trial_short.lower() in seen_trials:
                    continue
                # N: prefer "Sample size: N" labeled value, else
                # narrative phrase "enrolled N participants" / "N=N"
                # / "randomized N participants" / "study randomized
                # a total of N participants".
                n_val: int | None = None
                ss_m = _re.search(
                    r"Sample size:\s*([^\[]+?)\.\[\d+\]",
                    body, flags=_re.IGNORECASE,
                )
                if ss_m:
                    num_match = _re.search(
                        r"\b(\d{2,5})\b",
                        ss_m.group(1),
                    )
                    if num_match:
                        try:
                            n_val = int(num_match.group(1))
                        except ValueError:
                            pass
                if n_val is None:
                    # v1.1 A.4: allow up to 5 noun-phrase words between
                    # verb and digit, but require "participants?" /
                    # "patients?" after the digit so we don't mistake
                    # a year or other 2-5 digit number for the cohort.
                    # Catches: "enrolled a population of 1879 patients"
                    # (SURPASS-2), "randomly assigned a total of 117
                    # participants" (Thomas), "enrolled 478 adult
                    # participants" (SURPASS-1 narrative).
                    narr_n = _re.search(
                        r"(?:enrolled|randomized|randomised|"
                        r"randomly assigned)(?:\s+\w+){0,5}"
                        r"\s+(\d{2,5})\s+"
                        r"(?:adult\s+)?(?:participants?|patients?)",
                        body, flags=_re.IGNORECASE,
                    )
                    if narr_n:
                        try:
                            n_val = int(narr_n.group(1))
                        except ValueError:
                            pass

                # Baseline: anchor on labeled "Baseline X: Y.[N]"
                # only — not "at baseline" prose elsewhere.
                baseline_m = _re.search(
                    r"^Baseline[a-z0-9_ ]*?:\s*([^\[]+?)\.\[\d+\]",
                    body, flags=_re.IGNORECASE | _re.MULTILINE,
                )
                endpoint_m = _re.search(
                    r"Primary endpoint:\s*([^\[]+?)\.\[\d+\]",
                    body, flags=_re.IGNORECASE,
                )
                # Etd value may itself contain `[` brackets (e.g.
                # "[97.5% CI, ...]"). Anchor terminator on the
                # FIRST `.[\d+]` after the label.
                etd_m = _re.search(
                    r"Etd with uncertainty:\s*(.+?)\.\[\d+\]",
                    body, flags=_re.IGNORECASE | _re.DOTALL,
                )
                baseline_val = _real_value(
                    baseline_m.group(1) if baseline_m else None,
                )
                endpoint_val = _real_value(
                    endpoint_m.group(1) if endpoint_m else None,
                )
                ci_val = _real_value(
                    etd_m.group(1) if etd_m else None,
                )

                # Narrative-style fallbacks from the paragraph body.
                if not endpoint_val:
                    narr_ep = _re.search(
                        r"primary endpoint (?:was|assessed|"
                        r"objective was) (?:the )?([^\.]{15,200}?)\.\[\d+\]",
                        body, flags=_re.IGNORECASE,
                    )
                    if narr_ep:
                        endpoint_val = _real_value(narr_ep.group(1))
                if not baseline_val:
                    # Multiple narrative shapes:
                    # 1. "baseline HbA1c 8.31%"
                    # 2. "HbA1c of 8.31% at baseline"
                    # 3. "mean baseline HbA1c was 8.0%"
                    # 4. "BMI 36·1 kg/m2"
                    candidates = [
                        r"baseline\s+(?:HbA1c|glycated hemoglobin"
                        r"|glycated haemoglobin|body weight|BMI)"
                        r"[^\.\[]+",
                        r"(?:HbA1c|BMI|body weight)\s+(?:of|=|at)\s*"
                        r"\d+(?:[.,·]\d+)?%?[^\.\[]{0,40}",
                        r"(?:mean )?baseline\s+(?:was|of|=)\s*"
                        r"\d+(?:[.,·]\d+)?[^\.\[]{0,40}",
                    ]
                    for pat in candidates:
                        narr_bl = _re.search(
                            pat, body, flags=_re.IGNORECASE,
                        )
                        if narr_bl:
                            baseline_val = _real_value(narr_bl.group(0))
                            if baseline_val:
                                break
                if not ci_val:
                    narr_ci = _re.search(
                        r"(?:p\s*[<=]\s*0?\.\d+|"
                        r"\[?9[57](?:\.\d+)?%\s*CI[^\]\.]+|"
                        r"difference (?:vs|versus) placebo[^\.\[]+|"
                        r"-?\d+\.\d+%?\s*\([^)]*(?:CI|p\s*[<=])[^)]*\))",
                        body, flags=_re.IGNORECASE,
                    )
                    if narr_ci:
                        ci_val = _real_value(narr_ci.group(0))

                if (
                    n_val is not None
                    and baseline_val
                    and endpoint_val
                    and ci_val
                ):
                    claims.append({
                        "raw": title,
                        "trial": trial_short,
                        "n": n_val,
                        "baseline": baseline_val,
                        "endpoint": endpoint_val,
                        "ci": ci_val,
                    })
                    seen_trials.add(trial_short.lower())
        except Exception:
            pass

    if not claims and bib_entries:
        # Fallback to v1.0 behavior (no frame fields populated).
        claims = [
            {
                "raw": e.get("statement", ""),
                "n": None,
                "baseline": None,
                "endpoint": None,
                "ci": None,
                "tier": e.get("tier"),
                "evidence_id": e.get("evidence_id"),
            }
            for e in bib_entries
        ]
    manifest["claims"] = claims

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
