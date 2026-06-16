#!/usr/bin/env python3
"""A/B density comparison of two POLARIS run reports (padded vs concise).

The PG_ANTI_VERBOSITY A/B asks: does the concise config produce a DENSER report
(fewer restatement sentences per source) WITHOUT losing coverage or faithfulness?
This tool reports, for each run, per-section sentence counts, total sentences,
total words, coverage_fraction (from manifest), and the §-1.1 PARTIAL count (the
padding-over-statement artifacts, if an audit_combined.jsonl exists). It does NOT
declare a winner — it surfaces the numbers for the §-1.1 line-by-line judgement.

Density is reported as sentences-per-section and the padded-section flag
(a section with > THRESH sentences citing a single evidence id is a padding
suspect), NOT as a raw word count quality score.

Usage:
    python -m scripts.dr_benchmark.compare_density --a RUN_A_DIR --b RUN_B_DIR \
        [--label-a padded --label-b concise]
"""

# Standard Library
import argparse
import json
import re
from pathlib import Path

_SECT_RE = re.compile(r"^#{1,6}\s+(.*)$")
_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+")
_TOKEN_RE = re.compile(r"\[#ev:([^:\]]+):\d+-\d+\]|\[(\d+)\]")


def _analyze(run_dir: Path) -> dict:
    report = (run_dir / "report.md").read_text(encoding="utf-8", errors="ignore")
    sections: list[dict] = []
    cur = {"title": "(preamble)", "text": ""}
    for line in report.splitlines():
        m = _SECT_RE.match(line)
        if m:
            sections.append(cur)
            cur = {"title": m.group(1).strip(), "text": ""}
        else:
            cur["text"] += line + "\n"
    sections.append(cur)

    out_sections = []
    total_sents = 0
    for s in sections:
        body = re.sub(r"\[#ev:[^\]]+\]", "", s["text"])
        sents = [x for x in _SENT_SPLIT.split(body.strip()) if len(x.split()) > 3]
        # single-citation padding suspicion: count distinct [N]/[#ev] ids cited in the section
        ids = set()
        for mm in _TOKEN_RE.finditer(s["text"]):
            ids.add(mm.group(1) or mm.group(2))
        n = len(sents)
        total_sents += n
        out_sections.append({
            "title": s["title"], "sentences": n, "distinct_citations": len(ids),
            "padding_suspect": n >= 8 and len(ids) <= 2,
        })

    words = len(re.sub(r"\[#ev:[^\]]+\]", "", report).split())
    cov = None
    mf = run_dir / "manifest.json"
    if mf.exists():
        try:
            m = json.loads(mf.read_text(encoding="utf-8"))
            rec = m.get("required_entity_coverage") or {}
            cov = rec.get("coverage_fraction", m.get("coverage_fraction"))
        except Exception:
            pass
    partial = unsupported = off_topic = None
    ac = run_dir / "codex_audit" / "audit_combined.jsonl"
    if ac.exists():
        rows = [json.loads(l) for l in ac.read_text(encoding="utf-8").splitlines() if l.strip()]
        partial = sum(1 for r in rows if r["final"] == "PARTIAL")
        unsupported = sum(1 for r in rows if r["final"] in ("UNSUPPORTED", "FABRICATED"))
        off_topic = sum(1 for r in rows if r.get("off_topic"))
    return {
        "total_sentences": total_sents, "total_words": words,
        "coverage_fraction": cov, "sections": out_sections,
        "audit_partial": partial, "audit_unsupported_or_fab": unsupported,
        "audit_off_topic": off_topic,
        "padding_suspect_sections": [s["title"] for s in out_sections if s["padding_suspect"]],
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--a", type=Path, required=True)
    ap.add_argument("--b", type=Path, required=True)
    ap.add_argument("--label-a", default="A")
    ap.add_argument("--label-b", default="B")
    args = ap.parse_args()
    a = _analyze(args.a)
    b = _analyze(args.b)
    print(f"=== DENSITY A/B: {args.label_a} vs {args.label_b} ===")
    for lab, r in ((args.label_a, a), (args.label_b, b)):
        print(f"\n[{lab}]")
        print(f"  coverage_fraction = {r['coverage_fraction']}")
        print(f"  total_sentences   = {r['total_sentences']}  total_words = {r['total_words']}")
        print(f"  audit: PARTIAL={r['audit_partial']} UNSUP/FAB={r['audit_unsupported_or_fab']} OFF_TOPIC={r['audit_off_topic']}")
        print(f"  padding-suspect sections ({len(r['padding_suspect_sections'])}): {r['padding_suspect_sections']}")
    # headline deltas
    print("\n=== DELTAS (b - a) ===")
    def d(k):
        return (b[k] if b[k] is not None else 0) - (a[k] if a[k] is not None else 0)
    print(f"  coverage_fraction: {a['coverage_fraction']} -> {b['coverage_fraction']}")
    print(f"  total_sentences:   {a['total_sentences']} -> {b['total_sentences']} (delta {d('total_sentences')})")
    print(f"  padding-suspect sections: {len(a['padding_suspect_sections'])} -> {len(b['padding_suspect_sections'])}")
    print("\nWIN for concise IFF: padding-suspect sections DOWN, audit PARTIAL DOWN, "
          "coverage_fraction NOT below the padded run, faithfulness (UNSUP/FAB) not up.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
