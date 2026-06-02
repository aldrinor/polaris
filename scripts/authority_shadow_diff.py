"""Shadow harness — run ON vs OFF over the clinical S2 fixture (GH #983).

Emits a per-URL diff + a directional confusion matrix so a human reviewer can
see exactly where the field-agnostic authority view diverges from the legacy
clinical tier. Offline; no network. Read-only — does not gate anything.

Usage:
    python scripts/authority_shadow_diff.py
"""
from __future__ import annotations

import collections
import json
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

FIXTURE = REPO_ROOT / "tests" / "fixtures" / "authority" / "clinical_200_urls.jsonl"


def main() -> None:
    rows = [
        json.loads(ln)
        for ln in FIXTURE.read_text(encoding="utf-8").splitlines()
        if ln.strip()
    ]

    os.environ["PG_USE_AUTHORITY_MODEL"] = "1"
    from src.polaris_graph.authority import AuthoritySignals
    from src.polaris_graph.retrieval.tier_classifier import (
        ClassificationSignals,
        classify_source_tier,
    )

    matches = 0
    confusion: dict[str, int] = collections.Counter()
    diffs: list[dict] = []
    for e in rows:
        s = e["signals"]
        sig = ClassificationSignals(
            url=e["url"],
            title=e["title"],
            fetched_content_length=s["fetched_content_length"],
            openalex_publication_type=s["openalex_publication_type"],
            openalex_source_type=s["openalex_source_type"],
            openalex_is_peer_reviewed=s["openalex_is_peer_reviewed"],
        )
        sig.authority = AuthoritySignals(**e["authority_signals"])
        result = classify_source_tier(sig)
        view = result.tier.value
        head = e["head_tier"]
        confusion[f"{head}->{view}"] += 1
        if view == head:
            matches += 1
        else:
            diffs.append({
                "url": e["url"],
                "head_tier": head,
                "view_tier": view,
                "head_rule": e["head_rule"],
                "source_class": result.source_class,
                "authority_score": result.authority_score,
                "authority_confidence": result.authority_confidence,
            })

    print(f"shadow diff over {len(rows)} clinical URLs")
    print(f"agreement: {matches}/{len(rows)} = {matches / len(rows):.3f}")
    print("confusion (head->view : count):")
    for k, v in sorted(confusion.items()):
        print(f"  {k} : {v}")
    print(f"\n{len(diffs)} per-URL diffs:")
    for d in diffs:
        print(
            f"  {d['head_tier']}->{d['view_tier']} [{d['head_rule']}] "
            f"class={d['source_class']} conf={d['authority_confidence']} {d['url'][:60]}"
        )


if __name__ == "__main__":
    main()
