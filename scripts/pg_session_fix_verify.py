"""Zero-cost verification of session fixes.

Checks:
  1. FIX-ENTROPY math (Shannon entropy normalization)
  2. Hallucination detector discriminates good vs fabricated content
  3. Remediation wiring is structurally sound (imports + signature)

Usage: python scripts/pg_session_fix_verify.py
"""
import asyncio
import math
import os
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

from dotenv import load_dotenv
load_dotenv(override=False)


def verify_entropy() -> tuple[bool, str]:
    """Mirror the exact code block in graph.py:801-816. Verify math across 4 cases."""
    def _compute(evidence: list[dict]) -> float:
        persp_counts = Counter(
            e.get("perspective", "Scientific") for e in evidence if e.get("perspective")
        )
        total = sum(persp_counts.values())
        if total > 0 and len(persp_counts) > 1:
            probs = [c / total for c in persp_counts.values()]
            entropy = -sum(p * math.log2(p) for p in probs if p > 0)
            max_entropy = math.log2(len(persp_counts))
            return round(entropy / max_entropy, 3) if max_entropy > 0 else 0.0
        return 0.0

    cases = [
        ("1-perspective uniform", [{"perspective": "Scientific"}] * 10, 0.0, 0.0),
        ("2-perspective 50/50", [{"perspective": "Scientific"}] * 5 + [{"perspective": "Industry"}] * 5, 1.0, 1.0),
        ("3-perspective uneven", [{"perspective": "Scientific"}] * 6 + [{"perspective": "Industry"}] * 3 + [{"perspective": "Regulatory"}] * 1, 0.70, 0.85),
        ("empty", [], 0.0, 0.0),
    ]

    failures = []
    for name, ev, lo, hi in cases:
        val = _compute(ev)
        ok = lo <= val <= hi
        print(f"  [{'OK' if ok else 'FAIL'}] {name}: entropy={val:.3f} (expected {lo}-{hi})")
        if not ok:
            failures.append(f"{name} got {val}, expected {lo}-{hi}")
    return (len(failures) == 0, "; ".join(failures) or "all 4 cases passed")


def verify_remediation_wiring() -> tuple[bool, str]:
    """Static verification: imports resolve, signatures match expected shape."""
    try:
        from src.polaris_graph.wiki.wiki_composer import _compose_one_section, compose_from_wiki
        from src.polaris_graph.agents.hallucination_detector import (
            audit_sections_for_hallucination, _is_enabled,
        )
    except Exception as exc:
        return False, f"import failed: {exc}"

    import inspect
    sig = inspect.signature(_compose_one_section)
    if "unsupported_spans" not in sig.parameters:
        return False, "_compose_one_section missing unsupported_spans parameter"

    compose_src = inspect.getsource(compose_from_wiki)
    checks = [
        ("audit_sections_for_hallucination call", "audit_sections_for_hallucination(" in compose_src),
        ("FIX-HALLUC-WIKI-WIRE marker", "FIX-HALLUC-WIKI-WIRE" in compose_src),
        ("FIX-HALLUC-REMEDIATE marker", "FIX-HALLUC-REMEDIATE" in compose_src),
        ("unsupported_spans propagation", "unsupported_spans=unsupported_examples" in compose_src),
    ]
    fails = [name for name, ok in checks if not ok]
    if fails:
        return False, f"missing in compose_from_wiki: {fails}"
    return True, f"unsupported_spans param present, 4/4 wiring markers found, detector enabled={_is_enabled()}"


async def verify_hallucination_discrimination() -> tuple[bool, str]:
    """Exercise the detector with a known-good and known-fabricated section."""
    if os.getenv("PG_HALLUCINATION_DETECT_ENABLED", "0") != "1":
        return False, "PG_HALLUCINATION_DETECT_ENABLED=0"

    from src.polaris_graph.agents.hallucination_detector import (
        audit_sections_for_hallucination, _is_enabled,
    )
    if not _is_enabled():
        return False, "_is_enabled() returned False"

    # Pre-warm NLI model in THIS loop so the detector's thread-pool asyncio.run()
    # hits the _scorer singleton cache instead of a 30s fresh load.
    from src.polaris_graph.agents.nli_verifier import load_nli_model
    prewarmed = await load_nli_model()
    if prewarmed is None:
        return False, "NLI model pre-warm returned None"

    sections = [
        {
            "section_id": "sec_supported",
            "title": "Supported",
            "content": (
                "Activated carbon filtration removes chlorine and volatile organic "
                "compounds from drinking water. Reverse osmosis systems can remove "
                "up to 99% of dissolved contaminants."
            ),
            "evidence_ids": ["ev_1"],
        },
        {
            "section_id": "sec_fabricated",
            "title": "Fabricated",
            "content": (
                "The revolutionary quantum resonance filtration method developed by "
                "Dr. Hans Muller at the Zurich Institute of Advanced Hydrology in 2024 "
                "achieved 100% PFAS removal using crystalline nanotube matrices. "
                "This breakthrough was confirmed by NASA's Mars Water Reclamation Program "
                "and is now deployed in 47 countries worldwide."
            ),
            "evidence_ids": ["ev_1"],
        },
    ]
    evidence = [{
        "evidence_id": "ev_1",
        "statement": "Activated carbon removes chlorine and VOCs from water.",
        "direct_quote": "activated carbon removes chlorine",
        "source_content": (
            "Activated carbon filtration is a common water treatment method. "
            "It effectively removes chlorine, volatile organic compounds, and some "
            "pesticides. Reverse osmosis can remove up to 99% of dissolved salts."
        ),
    }]

    results = audit_sections_for_hallucination(
        sections=sections, evidence=evidence,
        research_query="What are effective water filtration methods for PFAS?",
    ) or []
    if not results:
        return False, "audit returned empty (detector load failed)"

    good = next((r for r in results if r["section_id"] == "sec_supported"), None)
    bad = next((r for r in results if r["section_id"] == "sec_fabricated"), None)
    if not (good and bad):
        return False, f"missing results: good={good is not None}, bad={bad is not None}"

    g = good["hallucination_ratio"]
    b = bad["hallucination_ratio"]
    bad_flagged = bad.get("needs_rewrite", False)
    msg = f"good={g:.1%}, fabricated={b:.1%}, fabricated_flagged={bad_flagged}"
    return (b > g and bad_flagged), msg


async def main() -> int:
    print("=" * 70)
    print("  POLARIS session-fix verification (zero cost)")
    print("=" * 70)

    results = {}

    print("\n[1/3] FIX-ENTROPY math")
    ok1, msg1 = verify_entropy()
    results["FIX-ENTROPY"] = (ok1, msg1)
    print(f"      {'PASS' if ok1 else 'FAIL'}: {msg1}")

    print("\n[2/3] Remediation wiring (static)")
    ok2, msg2 = verify_remediation_wiring()
    results["wiring"] = (ok2, msg2)
    print(f"      {'PASS' if ok2 else 'FAIL'}: {msg2}")

    print("\n[3/3] Hallucination detector discrimination")
    try:
        ok3, msg3 = await verify_hallucination_discrimination()
    except Exception as e:
        ok3, msg3 = False, f"exception: {e}"
    results["detector"] = (ok3, msg3)
    print(f"      {'PASS' if ok3 else 'FAIL'}: {msg3}")

    print("\n" + "=" * 70)
    passed = sum(1 for ok, _ in results.values() if ok)
    print(f"  SUMMARY: {passed}/{len(results)} passed")
    for name, (ok, msg) in results.items():
        print(f"    {'OK  ' if ok else 'FAIL'} {name}: {msg}")
    print("=" * 70)
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(asyncio.run(main()))
