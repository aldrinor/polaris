#!/usr/bin/env python3
"""Measure the clean-pool A/B: armed (topic judge deletes) vs ctrl (dirty pool).

The question is NOT "which report is longer" — the ceiling argument predicts both land at
~4k words because the section writer's sentence target is fixed and evidence-independent.
The question is whether the CLEAN pool converts a higher fraction of what it writes into
VERIFIED prose (kept_fraction), which is the number the ceiling argument's own evidence
(kept_fraction=0.35, measured on the ~50%-alien corpus) is confounded by.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ARMS = {
    "armed (clean pool)": Path("/home/polaris/wt/flywheel/outputs/rank6_armed_compose"),
    "ctrl  (dirty pool)": Path("/home/polaris/wt/fw_ctrl/outputs/rank6_ctrl_compose"),
}


def _find(d: Path, *pats: str) -> Path | None:
    for p in pats:
        hits = sorted(d.glob(p))
        if hits:
            return hits[-1]
    return None


def measure(d: Path) -> dict:
    m: dict = {"dir": str(d), "exists": d.exists()}
    if not d.exists():
        return m

    report = _find(d, "*report*.md", "*.md")
    if report:
        text = report.read_text(errors="replace")
        m["report"] = report.name
        m["words"] = len(text.split())
        m["citations"] = len(re.findall(r"\[\d+\]|\[\^?[A-Za-z0-9_-]+\]", text))
        secs = []
        for mt in re.finditer(r"^#{2,3} (.+)$", text, re.M):
            start = mt.end()
            nxt = re.search(r"^#{2,3} ", text[start:], re.M)
            body = text[start : start + (nxt.start() if nxt else len(text) - start)]
            secs.append((mt.group(1)[:48], len(body.split())))
        m["sections"] = secs

    # verification stats — the load-bearing numbers
    for stat in d.glob("*.json"):
        try:
            j = json.loads(stat.read_text())
        except Exception:  # noqa: BLE001
            continue
        if not isinstance(j, dict):
            continue
        for k in (
            "kept_fraction",
            "verified_sentences",
            "dropped_sentences",
            "n_off_subject_deletable",
            "n_in",
            "faithfulness",
        ):
            if k in j and k not in m:
                m[k] = j[k]
    return m


def main() -> int:
    out = {}
    for name, d in ARMS.items():
        out[name] = measure(d)

    print("=" * 78)
    print("CLEAN-POOL A/B  —  does removing the ~51% alien menu raise VERIFIED depth?")
    print("=" * 78)
    for name, m in out.items():
        print(f"\n### {name}")
        if not m.get("exists"):
            print("   (no output dir yet — run still in flight)")
            continue
        if "words" not in m:
            print("   (dir exists, no report written yet)")
            continue
        print(f"   report            : {m.get('report')}")
        print(f"   TOTAL WORDS       : {m.get('words')}")
        print(f"   citations         : {m.get('citations')}")
        for k in ("kept_fraction", "verified_sentences", "dropped_sentences", "faithfulness"):
            if k in m:
                print(f"   {k:<18}: {m[k]}")
        if m.get("sections"):
            print("   per-section words :")
            for t, w in m["sections"]:
                print(f"        {w:>5}w  {t}")

    a, c = out.get("armed (clean pool)", {}), out.get("ctrl  (dirty pool)", {})
    if "words" in a and "words" in c:
        print("\n" + "=" * 78)
        print("VERDICT INPUTS")
        print(f"  words       armed={a['words']}  ctrl={c['words']}  delta={a['words'] - c['words']:+d}")
        if "kept_fraction" in a and "kept_fraction" in c:
            print(f"  kept_frac   armed={a['kept_fraction']}  ctrl={c['kept_fraction']}")
        print("\n  Reading guide:")
        print("   * kept_fraction UP, words ~flat  => Lock A (quality) real, Lock B (fixed")
        print("     10-18-sentence target) is the binding length ceiling. Raise the target NEXT,")
        print("     on the clean pool — that is the only path to a 10-22k frontier report.")
        print("   * kept_fraction FLAT             => the alien menu was NOT what strict_verify")
        print("     was killing; the ceiling argument survives and compose needs a deeper fix.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
