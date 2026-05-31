"""Freeze the OFF-path ClassificationResult baseline for smoke S1 (GH #983).

One-time generator. Enumerates the unique classified URLs across the
``outputs/**/live_corpus_dump.json`` corpus, reconstructs the
``ClassificationSignals`` each carries (url + title + domain), runs the OFF
(legacy-rule) path of ``classify_source_tier`` with PG_USE_AUTHORITY_MODEL
explicitly UNSET, and writes the deterministic baseline to
``tests/fixtures/authority/clinical_tier_baseline_off.json``.

S1 then re-runs the same reconstruction and asserts byte-identity to this
baseline — proving the kill-switch OFF path did not drift when the dispatcher
+ additive fields landed. The baseline + the per-URL reconstructed signals are
committed so the offline replay is deterministic (no network).

Usage:
    python scripts/freeze_clinical_tier_baseline.py
"""
from __future__ import annotations

import glob
import json
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
DUMP_GLOB = str(REPO_ROOT / "outputs" / "**" / "live_corpus_dump.json")
OUT_PATH = (
    REPO_ROOT / "tests" / "fixtures" / "authority" / "clinical_tier_baseline_off.json"
)


def collect_unique_sources() -> list[dict[str, str]]:
    """Return the deduped {url, title, domain} list from every dump file."""
    by_url: dict[str, dict[str, str]] = {}
    for path in sorted(glob.glob(DUMP_GLOB, recursive=True)):
        try:
            rows = json.loads(Path(path).read_text(encoding="utf-8"))
        except (ValueError, OSError):
            continue
        if not isinstance(rows, list):
            continue
        for row in rows:
            if not isinstance(row, dict):
                continue
            url = row.get("url") or ""
            if not url or url in by_url:
                continue
            by_url[url] = {
                "url": url,
                "title": row.get("title", "") or "",
                "domain": row.get("domain", "") or "",
            }
    return [by_url[u] for u in sorted(by_url)]


def main() -> None:
    # The OFF path MUST be exercised — unset the flag explicitly.
    os.environ.pop("PG_USE_AUTHORITY_MODEL", None)
    from src.polaris_graph.retrieval.tier_classifier import (
        ClassificationSignals,
        classify_source_tier,
    )

    sources = collect_unique_sources()
    baseline: list[dict] = []
    for src in sources:
        signals = ClassificationSignals(url=src["url"], title=src["title"])
        result = classify_source_tier(signals)
        baseline.append(
            {
                "url": src["url"],
                "title": src["title"],
                "tier": result.tier.value,
                "confidence": result.confidence,
                "matched_rules": list(result.matched_rules),
                "reasons": list(result.reasons),
            }
        )

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(
        json.dumps(baseline, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"froze {len(baseline)} OFF-path results -> {OUT_PATH}")
    # Sanity echo so the freeze run is auditable.
    tiers: dict[str, int] = {}
    for row in baseline:
        tiers[row["tier"]] = tiers.get(row["tier"], 0) + 1
    print("tier distribution (OFF, url+title-only signals):", tiers)


if __name__ == "__main__":
    main()
