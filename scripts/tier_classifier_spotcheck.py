"""
Spot-check the Phase 2a tier classifier against PG_LB_SA_02 bibliography
entries using my reviewer labels from Section E-01 of the content audit.

Plan validation gate: ≤2 disagreements on 10-entry spot-check.

Usage:
    python scripts/tier_classifier_spotcheck.py

Output: loopback/audit/_tier_classifier_spotcheck.md
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

# Repo root on sys.path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.polaris_graph.retrieval.tier_classifier import (
    ClassificationSignals,
    TierLevel,
    classify_source_tier,
)


# Reviewer labels from loopback/audit/PG_LB_SA_02_CONTENT_AUDIT.md Section E-01.
# Mapping the original GOLD/SILVER/BRONZE/UNKNOWN verdicts to the T1-T7
# taxonomy of the new classifier.
#
# The "notes" field captures the reasoning I used in the audit so any
# disagreement with the classifier can be explained.
REVIEWER_LABELS: dict[int, dict[str, str]] = {
    1: {"expected": "T5", "notes": "ICER industry-funded white paper"},
    2: {"expected": "T3", "notes": "FDA 2021 Wegovy label"},
    3: {"expected": "T3", "notes": "CDA-AMC Combined Review"},
    4: {"expected": "T4", "notes": "Commentary in J Obes Metab Syndr"},
    5: {"expected": "T2", "notes": "Systematic Review and Meta-Analysis, AJC 2024"},
    6: {"expected": "T7", "notes": "Conference abstract (diabetesjournals supplement 1745-P)"},
    7: {"expected": "T2", "notes": "Published SR/MA, PMC"},
    8: {"expected": "T2", "notes": "Network meta-analysis review"},
    9: {"expected": "T6", "notes": "WashU news release"},
    10: {"expected": "T3", "notes": "Health Canada product monograph (Wegovy)"},
    11: {"expected": "T6", "notes": "Buchanan Ingersoll law-firm commentary article"},
    12: {"expected": "T1", "notes": "Case series + FAERS analysis, Clinical Kidney J"},
    13: {"expected": "T6", "notes": "nhsjs.com — National High School Journal of Science, student journal"},
    14: {"expected": "T1", "notes": "JAMA — STEP 3 Wadden 2021 primary trial paper"},
    15: {"expected": "T1", "notes": "Real-world retrospective cohort, Postgraduate Medicine"},
    16: {"expected": "T5", "notes": "touchendocrinology.com branded physician portal"},
    17: {"expected": "T2", "notes": "Cureus systematic review"},
    18: {"expected": "T5", "notes": "novomedlink.com Novo industry HCP page"},
    19: {"expected": "T6", "notes": "Scribd copy of FDA label — provenance unclear; counting as T6"},
    20: {"expected": "T5", "notes": "novomedlink.com Novo safety-profile page"},
    21: {"expected": "T5", "notes": "novomedlink.com Novo HCP-information page"},
    22: {"expected": "T7", "notes": "Semantic Scholar abstract-only (500 chars)"},
    23: {"expected": "T7", "notes": "Wiley abstract-only (500 chars retrieved)"},
    24: {"expected": "T6", "notes": "Access to Medicine Foundation commentary"},
    25: {"expected": "T3", "notes": "FDA direct statement on compounders"},
    26: {"expected": "T3", "notes": "FDA label via nctr-crs.fda.gov setid URL"},
    27: {"expected": "T6", "notes": "healthpolicy-watch.news commentary"},
    28: {"expected": "T7", "notes": "Nature abstract-only (500 chars)"},
    29: {"expected": "T2", "notes": "Published SR/MA, PubMed"},
    30: {"expected": "T4", "notes": "Postgraduate Medicine narrative review"},
    31: {"expected": "T4", "notes": "Narrative review in PMC"},
    32: {"expected": "T2", "notes": "SR/MA in Frontiers in Pharmacology"},
    33: {"expected": "T2", "notes": "SR/MA with PROSPERO registration, Frontiers in Endocrinology"},
}


def _infer_source_type_hint(bib: dict) -> str:
    """Pass-through of the source_type field with normalization."""
    raw = (bib.get("source_type") or "").strip().lower()
    return raw


def main() -> int:
    ref_to_content_path = ROOT / "loopback/audit/_ref_to_content.json"
    if not ref_to_content_path.exists():
        print(f"ERROR: {ref_to_content_path} not found. Run the audit first.")
        return 2

    data = json.loads(ref_to_content_path.read_text(encoding="utf-8"))

    rows: list[dict] = []
    agree_count = 0
    disagree_count = 0
    unknown_count = 0

    # Sort by int(ref_num) for readable output
    for ref_num_str in sorted(data.keys(), key=int):
        ref_num = int(ref_num_str)
        entry = data[ref_num_str]
        label_info = REVIEWER_LABELS.get(ref_num, {"expected": "?", "notes": "no reviewer label"})
        expected_tier = label_info["expected"]

        signals = ClassificationSignals(
            url=entry.get("biblio_url") or entry.get("fc_url") or "",
            fetched_content_length=entry.get("content_len", 0),
            openalex_publication_type=entry.get("publication_type", ""),
            openalex_source_type=entry.get("source_type_normalized", ""),
            source_type_hint=_infer_source_type_hint(entry),
            title=entry.get("biblio_title", ""),
            publisher="",  # not available in current ref_to_content
        )
        result = classify_source_tier(signals)

        actual = result.tier.value
        status = "AGREE" if actual == expected_tier else "DISAGREE"
        if result.tier == TierLevel.UNKNOWN:
            unknown_count += 1
        if status == "AGREE":
            agree_count += 1
        else:
            disagree_count += 1

        rows.append({
            "ref_num": ref_num,
            "url": signals.url,
            "content_len": signals.fetched_content_length,
            "source_type_hint": signals.source_type_hint,
            "expected": expected_tier,
            "actual": actual,
            "confidence": f"{result.confidence:.2f}",
            "status": status,
            "rule": (result.matched_rules[0] if result.matched_rules else ""),
            "reviewer_notes": label_info["notes"],
            "classifier_reasons": " | ".join(result.reasons),
        })

    # Write markdown report
    out = ROOT / "loopback/audit/_tier_classifier_spotcheck.md"
    lines = [
        "# Tier Classifier Spot-Check — PG_LB_SA_02 bibliography",
        "",
        f"**Total entries**: {len(rows)}",
        f"**Agreements**: {agree_count}",
        f"**Disagreements**: {disagree_count}",
        f"**UNKNOWN from classifier**: {unknown_count}",
        f"**Phase 2 gate**: ≤2 disagreements on a 10-entry sample (we tested all {len(rows)}).",
        "",
        "## Per-entry",
        "",
        "| Ref | Expected | Actual | Status | Rule | Content | URL / Reviewer notes |",
        "|---|---|---|---|---|---|---|",
    ]
    for row in rows:
        status_marker = "✓" if row["status"] == "AGREE" else "✗"
        short_url = row["url"][:60] + "…" if len(row["url"]) > 60 else row["url"]
        notes = row["reviewer_notes"]
        lines.append(
            f"| [{row['ref_num']}] | {row['expected']} | {row['actual']} "
            f"| {status_marker} {row['status']} | `{row['rule']}` "
            f"| {row['content_len']}c | `{short_url}` — {notes} |"
        )

    lines.append("")
    lines.append("## Disagreement details")
    lines.append("")
    for row in rows:
        if row["status"] == "DISAGREE":
            lines.append(f"### [{row['ref_num']}] expected {row['expected']}, got {row['actual']}")
            lines.append("")
            lines.append(f"- **URL**: `{row['url']}`")
            lines.append(f"- **Content length**: {row['content_len']} chars")
            lines.append(f"- **Reviewer reasoning**: {row['reviewer_notes']}")
            lines.append(f"- **Classifier rule**: `{row['rule']}`")
            lines.append(f"- **Classifier reasons**: {row['classifier_reasons']}")
            lines.append("")

    out.write_text("\n".join(lines) + "\n", encoding="utf-8")

    # Console summary
    print(f"Spot-check complete: {agree_count} agree / {disagree_count} disagree "
          f"/ {unknown_count} UNKNOWN out of {len(rows)}")
    print(f"Report written to {out}")
    for row in rows:
        if row["status"] == "DISAGREE":
            print(
                f"  DISAGREE [{row['ref_num']}]: expected {row['expected']}, "
                f"got {row['actual']} (rule: {row['rule']})"
            )
    # Use <= (ASCII) instead of U+2264 so cp1252 Windows consoles don't crash.
    print(f"\nPhase 2 gate (<=2 disagreements): "
          f"{'PASS' if disagree_count <= 2 else 'FAIL'}")
    return 0 if disagree_count <= 2 else 1


if __name__ == "__main__":
    sys.exit(main())
