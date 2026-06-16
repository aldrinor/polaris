#!/usr/bin/env python3
"""Build a per-claim §-1.1 audit ledger from a completed POLARIS run directory.

For the line-by-line audit standard (CLAUDE.md §-1.1) the auditor needs, for
every claim sentence in the report: the claim text, the evidence id it cites,
the EXACT cited span text (so the verdict is against the span, not the title or
abstract), and the source metadata. This script performs the deterministic join

    claim sentence  ->  [#ev:<evidence_id>:<start>-<end>] token(s)
                    ->  evidence_pool.json row by evidence_id
                    ->  direct_quote[start:end]  (the cited span)

and emits both a machine-readable ``claims_ledger.jsonl`` and a human/Codex
readable ``claims_ledger.md``. It NEVER renders a verdict — that is the job of
the parallel Claude + Codex auditors that consume this ledger. It is read-only:
it consumes run artifacts and writes only the two ledger files.

Usage:
    python -m scripts.dr_benchmark.build_claims_ledger <run_dir> [--out-dir DIR]

``run_dir`` must contain ``four_role_claim_audit.json`` and
``evidence_pool.json`` (the standard sweep artifacts). The span field is
``direct_quote`` (verified empirically: the [#ev:id:start-end] offsets index
into the evidence row's ``direct_quote``).
"""

# Standard Library
import argparse
import json
import re
import sys
from pathlib import Path

# The provenance token carried on every generated sentence (CLAUDE.md §9.1.2).
_TOKEN_RE = re.compile(r"\[#ev:([^:\]]+):(\d+)-(\d+)\]")
# The field the token offsets index into (confirmed against drb_72 run data).
_SPAN_FIELD = "direct_quote"


def _load_evidence_pool(run_dir: Path) -> dict:
    """evidence_id -> evidence row. The pool is a JSON list of rows."""
    rows = json.loads((run_dir / "evidence_pool.json").read_text(encoding="utf-8"))
    pool = {}
    for row in rows:
        eid = row.get("evidence_id")
        if eid:
            pool[eid] = row
    return pool


def _strip_tokens(sentence: str) -> str:
    """The human-readable claim with provenance tokens removed."""
    return _TOKEN_RE.sub("", sentence).strip()


def _citations_for(sentence: str, pool: dict) -> list[dict]:
    """Resolve every [#ev:id:start-end] token in a sentence to its cited span.

    UNREACHABLE markers are emitted explicitly (id absent from pool, or offsets
    out of range) so the auditor sees the gap rather than a silent drop — a
    silent drop would let a fabricated/unresolvable citation pass unaudited.
    """
    cites: list[dict] = []
    for eid, start_s, end_s in _TOKEN_RE.findall(sentence):
        start, end = int(start_s), int(end_s)
        row = pool.get(eid)
        if row is None:
            cites.append(
                {"evidence_id": eid, "start": start, "end": end,
                 "span_text": None, "resolve_status": "EVIDENCE_ID_NOT_IN_POOL"}
            )
            continue
        text = row.get(_SPAN_FIELD) or ""
        span = text[start:end]
        status = "ok"
        if not span:
            status = "EMPTY_SPAN"
        elif end > len(text):
            status = "OFFSET_PAST_END"
        cites.append(
            {
                "evidence_id": eid,
                "start": start,
                "end": end,
                "span_text": span,
                "span_field_len": len(text),
                "resolve_status": status,
                "source_title": row.get("title"),
                "doi": row.get("doi"),
                "source_url": row.get("source_url"),
                "tier": row.get("tier"),
                "year": row.get("year"),
                "authors": row.get("authors"),
                "journal": row.get("journal"),
            }
        )
    return cites


def build_ledger(run_dir: Path) -> list[dict]:
    audit = json.loads(
        (run_dir / "four_role_claim_audit.json").read_text(encoding="utf-8")
    )
    pool = _load_evidence_pool(run_dir)
    ledger: list[dict] = []
    for claim_id, rec in audit.items():
        sentence = rec.get("sentence", "")
        ledger.append(
            {
                "claim_id": claim_id,
                "section_index": rec.get("section_index"),
                "section_title": rec.get("section_title"),
                "severity": rec.get("severity"),
                "covered_element_ids": rec.get("covered_element_ids", []),
                "claim_text": _strip_tokens(sentence),
                "raw_sentence": sentence,
                "citations": _citations_for(sentence, pool),
            }
        )
    # Stable order: section then claim index (claim_id sorts that way already).
    ledger.sort(key=lambda r: r["claim_id"])
    return ledger


def _write_markdown(ledger: list[dict], path: Path) -> None:
    lines = [
        "# Claims ledger (§-1.1 audit input) — NO verdicts rendered here",
        "",
        f"Total claims: {len(ledger)}. Each claim's verdict is to be filled by "
        "the parallel Claude + Codex auditors against the cited span below.",
        "",
    ]
    cur_section = object()
    for r in ledger:
        if r["section_title"] != cur_section:
            cur_section = r["section_title"]
            lines.append(f"\n## Section {r['section_index']}: {cur_section}\n")
        lines.append(f"### {r['claim_id']}  (severity {r['severity']})")
        lines.append(f"**CLAIM:** {r['claim_text']}")
        if not r["citations"]:
            lines.append("**CITED SPAN:** _(no provenance token on this sentence)_")
        for c in r["citations"]:
            if c.get("span_text"):
                lines.append(
                    f"**CITED SPAN** [{c['evidence_id']} {c['start']}-{c['end']}] "
                    f"(_{c.get('source_title')}_, {c.get('doi') or c.get('source_url')}):"
                )
                lines.append(f"> {c['span_text']}")
            else:
                lines.append(
                    f"**CITED SPAN** [{c['evidence_id']} {c['start']}-{c['end']}]: "
                    f"**UNREACHABLE — {c['resolve_status']}**"
                )
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("run_dir", type=Path)
    ap.add_argument("--out-dir", type=Path, default=None)
    args = ap.parse_args(argv)

    run_dir = args.run_dir
    out_dir = args.out_dir or run_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    ledger = build_ledger(run_dir)

    jsonl = out_dir / "claims_ledger.jsonl"
    with jsonl.open("w", encoding="utf-8") as fh:
        for r in ledger:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    _write_markdown(ledger, out_dir / "claims_ledger.md")

    # Summary to stdout (no quality signal — just resolution health).
    n = len(ledger)
    no_token = sum(1 for r in ledger if not r["citations"])
    unreachable = sum(
        1
        for r in ledger
        for c in r["citations"]
        if not c.get("span_text")
    )
    sev = {}
    for r in ledger:
        sev[r["severity"]] = sev.get(r["severity"], 0) + 1
    print(f"claims={n} no_provenance_token={no_token} unreachable_citations={unreachable}")
    print(f"severity={sev}")
    print(f"wrote {jsonl} and {out_dir/'claims_ledger.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
