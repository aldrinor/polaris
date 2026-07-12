#!/usr/bin/env python3
"""FLYWHEEL A/B: diff two routed outlines (CONTROL vs judge-ARMED) row-by-row.

Grounding tool, not a scorer. It answers exactly three questions an honest gate needs:
  1. WHAT was deleted (every dropped row, with tier + title) — so a human can eyeball a false drop.
  2. WHERE the survivors sit (per-section counts + the residual catch-all's share).
  3. WHETHER any high-tier / on-topic row died (the failure mode §-1.3.1(b) forbids).
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

RESIDUAL_HINTS = ("additional", "corroborat", "further", "supplementary")


def load(p: str) -> list[dict]:
    d = json.loads(Path(p).read_text(encoding="utf-8"))
    return d if isinstance(d, list) else d.get("sections", [])


def rows(secs: list[dict]) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for s in secs:
        for e in s.get("evidence", []) or []:
            eid = str(e.get("ev_id", ""))
            if eid:
                out.setdefault(eid, {**e, "_section": s.get("title", "?")})
    return out


def is_residual(title: str) -> bool:
    t = (title or "").lower()
    return any(h in t for h in RESIDUAL_HINTS)


def main() -> int:
    a_path, b_path = sys.argv[1], sys.argv[2]
    A, B = load(a_path), load(b_path)
    ra, rb = rows(A), rows(B)

    print(f"CONTROL  {a_path}\n  sections={len(A)} unique_rows={len(ra)}")
    print(f"ARMED    {b_path}\n  sections={len(B)} unique_rows={len(rb)}")

    deleted = set(ra) - set(rb)
    added = set(rb) - set(ra)
    print(f"\n=== DELETED by the judge: {len(deleted)}  (added: {len(added)}) ===")
    tiers = Counter(str(ra[e].get("tier", "?")) for e in deleted)
    print("  deleted by tier:", dict(sorted(tiers.items())))
    hi = [e for e in deleted if str(ra[e].get("tier", "")).upper() in ("T1", "T2")]
    print(f"  *** HIGH-TIER (T1/T2) DELETED: {len(hi)} *** {'<-- INSPECT EVERY ONE' if hi else '(none)'}")
    for e in sorted(hi):
        print(f"      [{ra[e].get('tier')}] {str(ra[e].get('title',''))[:95]}")

    print("\n  --- every deleted row (tier | section it sat in | title) ---")
    for e in sorted(deleted, key=lambda x: (str(ra[x].get("tier", "")), x)):
        r = ra[e]
        print(f"   {str(r.get('tier','?')):>7} | {str(r.get('_section',''))[:26]:<26} | {str(r.get('title',''))[:78]}")

    print("\n=== SECTION SHAPE (control -> armed) ===")
    ca = Counter(r["_section"] for r in ra.values())
    cb = Counter(r["_section"] for r in rb.values())
    for t in sorted(set(ca) | set(cb), key=lambda x: -ca.get(x, 0)):
        tag = "  <== RESIDUAL CATCH-ALL" if is_residual(t) else ""
        print(f"  {ca.get(t,0):>4} -> {cb.get(t,0):>4}   {t[:60]}{tag}")
    resid_a = sum(v for k, v in ca.items() if is_residual(k))
    resid_b = sum(v for k, v in cb.items() if is_residual(k))
    na, nb = max(1, len(ra)), max(1, len(rb))
    print(f"\n  RESIDUAL SHARE: {resid_a}/{na} ({resid_a/na:.0%})  ->  {resid_b}/{nb} ({resid_b/nb:.0%})")
    print(f"  THEMATIC (non-residual) rows: {na-resid_a}  ->  {nb-resid_b}"
          "   <-- the number that must NOT collapse; this is the depth budget")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
