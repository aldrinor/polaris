"""S7 deliverable-aware RENDER hamster harness (master plan WP-3d; Design 3 Level-1/2, render leg).

Renders reference-style entries + report shape + Methods disclosure blocks from a DeliverableSpec
fixture (and an optional RunConfig provenance fixture + an optional real bibliography), printing one
line per rendered artifact so Fable / Codex can read EVERY reference line against the row's REAL
captured metadata (§-1.1 forensic read: an author or year that is NOT in the row must NOT appear in
the rendered line — that is a FABRICATION and a fail).

OFFLINE by default (built-in 3-row fixture, zero spend, no live corpus, no LLM). On the VM the
``--bibliography`` flag points at a banked run's bibliography.json for the real-corpus read.

Usage:
  python scripts/deliverable_render_harness.py                       # built-in fixture, all styles
  python scripts/deliverable_render_harness.py --spec spec.json      # a specific deliverable ask
  python scripts/deliverable_render_harness.py --bibliography bib.json --run-config rc.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.polaris_graph.generator import deliverable_render as dr  # noqa: E402

# A tiny fixture with the two metadata shapes that matter: a row WITH authors+year, and a row with
# NEITHER (the common POLARIS case — the renderer must degrade to title/locator, never fabricate).
_FIXTURE_BIB = [
    {"num": 1, "statement": "Tirzepatide once weekly for type 2 diabetes (SURPASS-2)",
     "url": "https://doi.org/10.1056/x", "tier": "T1", "authors": ["Frías", "Davies"],
     "year": 2021},
    {"num": 2, "statement": "Semaglutide and cardiovascular outcomes", "url": "https://example.org/b",
     "tier": "T2", "year": 2016},
    {"num": 3, "statement": "Weight-loss maintenance: a narrative overview", "url": "",
     "tier": "T5"},
]
_STYLES = ["numeric", "author_year", "apa", "harvard", "vancouver"]


def _load(path: str | None) -> "dict | list | None":
    if not path:
        return None
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _year(row: dict) -> "int | None":
    for k in ("year", "publication_year", "pub_year"):
        v = row.get(k)
        try:
            y = int(str(v).strip()[:4])
            if 1500 <= y <= 2100:
                return y
        except (TypeError, ValueError):
            continue
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description="S7 deliverable render harness (offline)")
    ap.add_argument("--spec", help="DeliverableSpec JSON file")
    ap.add_argument("--run-config", dest="run_config", help="RunConfig provenance JSON file")
    ap.add_argument("--bibliography", help="bibliography rows JSON (list of dicts)")
    args = ap.parse_args()

    spec = _load(args.spec)
    run_config = _load(args.run_config)
    bib = _load(args.bibliography) or _FIXTURE_BIB

    print("=" * 78)
    print(f"spec_active={dr.is_spec_active(spec)}  spec={json.dumps(spec) if spec else '(none)'}")

    if spec:
        style, fallback = dr.resolve_reference_style(spec)
        styles_to_show = [style]
        print(f"resolved reference_style={style}  fallback={fallback}")
        ordering = dr.build_report_ordering(spec)
        print(f"resolved ordering={ordering}")
    else:
        styles_to_show = _STYLES  # no spec => show every style so the reader can compare shapes

    for style in styles_to_show:
        print("-" * 78)
        print(f"## Bibliography  (reference_style={style})")
        for row in bib:
            has_loc = bool(str(row.get("url") or "").strip() or str(row.get("doi") or "").strip())
            loc = (str(row.get("url") or "").strip()
                   or "no resolvable URL/DOI locator (disclosed evidence gap)")
            if style == "numeric":
                # the byte-identical HEAD render (title — locator (tier)).
                line = f"[{row['num']}] {row.get('statement', '')} — {loc} (tier {row.get('tier', '')})"
            else:
                line = dr.format_reference_body(
                    num=row["num"], title=str(row.get("statement", "")), locator=loc,
                    tier=row.get("tier", ""), genre_tag="", row=row, year=_year(row),
                    style=style, has_locator=has_loc,
                )
            print(f"  {line}")

    if spec:
        _, fb = dr.resolve_reference_style(spec)
        print("-" * 78)
        print("## Methods (adherence)")
        print(dr.render_deliverable_adherence_block(spec, reference_fallback=fb) or "  (empty)")
    if run_config:
        print("-" * 78)
        print("## Methods (run configuration)")
        print(dr.render_run_config_disclosure_block(run_config) or "  (empty)")
    print("=" * 78)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
