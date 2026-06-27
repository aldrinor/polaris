"""I-wire-014 CWF header diagnostic (offline, fast).

Runs the REAL per-basket corroboration-header selection chain from
``run_honest_sweep_r3.py`` against a run's ``bibliography.json`` and reports,
for every basket, which screen leg rejected ``claim_text`` and what header was
finally chosen. Lets us iterate FIX-A (render the prose, don't dump hashes)
without a full replay.

Usage:  python scripts/iwire014_cwf_header_diagnostic.py <bibliography.json>
"""
import json
import re
import sys

from src.tools.access_bypass import clean_fetch_body, is_boilerplate_or_nonassertional

# Import the exact header helpers used by the real render (post-FIX-A #1334).
from scripts.run_honest_sweep_r3 import (  # type: ignore
    _normalize_claim_summary,
    _title_has_named_chrome,
    _claim_header_is_unrenderable,
    _best_corroboration_header,
    cwf_header_prose_enabled,
)

_HASH_RE = re.compile(r"^clm_[0-9a-f]+$")


def _final_header(basket: dict, statement: str) -> tuple[str, str]:
    """Replicate the REAL header selection (run_honest_sweep_r3 :2195-2225, post-FIX-A).
    Returns (final_header_text, classification)."""
    ccid = str(basket.get("claim_cluster_id") or "")
    raw = str(basket.get("claim_text") or "")
    dechromed = clean_fetch_body(raw).cleaned_text if raw else ""
    claim = _normalize_claim_summary(dechromed, quote_trim=160)
    if (
        not claim
        or is_boilerplate_or_nonassertional(claim)
        or _title_has_named_chrome(claim)
        or _claim_header_is_unrenderable(raw)
    ):
        prose = _best_corroboration_header(basket, statement) if cwf_header_prose_enabled() else ""
        if prose:
            return prose, "FIXA_prose_or_title"
        subj = str(basket.get("subject") or "").strip()
        pred = str(basket.get("predicate") or "").strip()
        claim = (f"{subj} {pred}".strip()) or ccid
        if claim == ccid or _HASH_RE.match(claim):
            return claim, "HASH(clm_)"
        return claim, "2WORD_STUB(subject+predicate)"
    return claim, "claim_text_direct"


def main() -> None:
    path = sys.argv[1] if len(sys.argv) > 1 else "bibliography.json"
    bib = json.load(open(path, encoding="utf-8"))
    entries = bib if isinstance(bib, list) else bib.get("bibliography", [])
    seen: set[str] = set()
    classes: dict[str, int] = {}
    samples: dict[str, list] = {}
    for b in entries:
        statement = str(b.get("statement") or "")
        for basket in (b.get("baskets") or []):
            ccid = str(basket.get("claim_cluster_id") or "")
            if not ccid or ccid in seen:
                continue
            seen.add(ccid)
            header, cls = _final_header(basket, statement)
            classes[cls] = classes.get(cls, 0) + 1
            samples.setdefault(cls, [])
            if len(samples[cls]) < 6:
                samples[cls].append((ccid[:18], repr(header[:140])))
    total = len(seen)
    bad = classes.get("HASH(clm_)", 0) + classes.get("2WORD_STUB(subject+predicate)", 0)
    print(f"unique baskets (deduped by ccid): {total}")
    print(f"REAL HEADER (sentence / title / claim_text): {total - bad}")
    print(f"JUNK HEADER (hash / 2-word stub): {bad}   <-- FIX-A target: 0\n")
    print("--- classification breakdown ---")
    for cls, n in sorted(classes.items(), key=lambda kv: -kv[1]):
        print(f"  {n:4d}  {cls}")
    print("\n--- samples per class (final header) ---")
    for cls, ss in samples.items():
        print(f"\n[{cls}]")
        for ccid, txt in ss:
            print(f"   {ccid}  {txt}")


if __name__ == "__main__":
    main()
