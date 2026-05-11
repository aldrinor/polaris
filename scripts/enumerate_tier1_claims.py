"""Enumerate audit-grade claims from a verified report for Tier-1 v2 review.

Reads:
  - <report_dir>/report.md
  - <report_dir>/bibliography.json
  - <report_dir>/evidence_pool.json

Writes:
  - <output_yaml> claims enumeration in the Tier-1 v2 schema used by
    `.codex/I-eval-002/q5_claims_enumeration.yaml`.

Only sentences from the verified-findings sections (everything before
'## Analyst Synthesis' / similar synthesis markers) with at least one [N]
citation are enumerated. Synthesis sections are hedged per the report
header and not audit-grade.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


CITATION_RE = re.compile(r"\[(\d+)\]")
SECTION_HEADER_RE = re.compile(r"^###\s+(.+?)\s*$", re.MULTILINE)
SYNTHESIS_MARKERS = (
    "## Analyst Synthesis",
    "## Synthesis",
    "*This section is analyst synthesis",
)


def split_into_sentences(text: str) -> list[str]:
    """Split paragraph text into sentences. Naive split on '. ' followed by
    capital/[. Preserves the trailing period.
    """
    # Normalize whitespace
    text = re.sub(r"\s+", " ", text.strip())
    if not text:
        return []
    # Sentence boundary: period/!/? followed by zero or more inline [N]
    # citation tokens, then whitespace, then a capital letter. Use a
    # capture group on the [N] tokens so they re-attach to the preceding
    # sentence rather than disappearing into the delimiter.
    parts = re.split(r"(?<=[.!?])((?:\[\d+\])*)\s+(?=[A-Z])", text)
    # parts alternates: [sentence, citations, sentence, citations, ..., sentence]
    out: list[str] = []
    i = 0
    while i < len(parts):
        sentence = parts[i]
        suffix = parts[i + 1] if i + 1 < len(parts) else ""
        out.append((sentence + suffix).strip())
        i += 2
    return [s for s in out if s]


def extract_verified_findings(report_md: str) -> dict[str, list[str]]:
    """Return {section_title: [sentences]} for verified-findings sections,
    stopping at the first synthesis marker.
    """
    # Truncate at first synthesis marker
    cut_at = len(report_md)
    for marker in SYNTHESIS_MARKERS:
        idx = report_md.find(marker)
        if idx != -1 and idx < cut_at:
            cut_at = idx
    verified_part = report_md[:cut_at]

    # Walk by ### section headers
    sections: dict[str, list[str]] = {}
    headers = list(SECTION_HEADER_RE.finditer(verified_part))
    if not headers:
        return sections
    for i, m in enumerate(headers):
        title = m.group(1).strip()
        start = m.end()
        end = headers[i + 1].start() if i + 1 < len(headers) else len(verified_part)
        body = verified_part[start:end].strip()
        sentences = split_into_sentences(body)
        # Only keep sentences that contain at least one [N] citation
        cited = [s for s in sentences if CITATION_RE.search(s)]
        if cited:
            sections[title] = cited
    return sections


def build_enumeration(report_dir: Path, prefix: str) -> dict:
    report_md = (report_dir / "report.md").read_text(encoding="utf-8")
    bibliography = json.loads((report_dir / "bibliography.json").read_text(encoding="utf-8"))
    pool = json.loads((report_dir / "evidence_pool.json").read_text(encoding="utf-8"))

    # num -> bibliography entry; evidence_id -> pool entry
    num_to_biblio = {b["num"]: b for b in bibliography}
    ev_to_pool = {e["evidence_id"]: e for e in pool}

    sections = extract_verified_findings(report_md)

    claims: list[dict] = []
    claim_idx = 0
    for section_title, sentences in sections.items():
        for sentence in sentences:
            claim_idx += 1
            claim_id = f"{prefix}-T1-{claim_idx:03d}"
            cited_nums = sorted({int(n) for n in CITATION_RE.findall(sentence)})
            cited_evidence: list[dict] = []
            for n in cited_nums:
                if n not in num_to_biblio:
                    continue
                biblio = num_to_biblio[n]
                ev_id = biblio["evidence_id"]
                pool_entry = ev_to_pool.get(ev_id, {})
                span_text = (pool_entry.get("direct_quote") or "").strip()
                # Cap span_text at ~600 chars for audit readability
                if len(span_text) > 600:
                    span_text = span_text[:600]
                cited_evidence.append({
                    "evidence_id": ev_id,
                    "bibliography_num": n,
                    "url": biblio.get("url", ""),
                    "tier": biblio.get("tier", "UNKNOWN"),
                    "span": "0-500",
                    "title": biblio.get("statement", "")[:160],
                    "span_text": span_text,
                })
            claims.append({
                "claim_id": claim_id,
                "section": section_title,
                "sentence": sentence,
                "cited_evidence": cited_evidence,
            })

    return {
        "schema_version": "tier1_v2",
        "report": str(report_dir / "report.md").replace("\\", "/"),
        "claim_count": len(claims),
        "claims": claims,
    }


def emit_yaml(doc: dict, out_path: Path) -> None:
    """Hand-rolled YAML emitter — avoids PyYAML dependency and produces the
    block-scalar form used by the iter-2 schema.
    """
    lines: list[str] = []
    lines.append(f"# Tier-1 v2 claim enumeration — {doc['report']}")
    lines.append(f"# Total claims: {doc['claim_count']}")
    lines.append("")
    lines.append(f"schema_version: {doc['schema_version']}")
    lines.append(f"report: {doc['report']}")
    lines.append("claims:")
    for c in doc["claims"]:
        lines.append(f"  - claim_id: {c['claim_id']}")
        lines.append(f"    section: {json.dumps(c['section'])}")
        lines.append(f"    sentence: {json.dumps(c['sentence'])}")
        lines.append("    cited_evidence:")
        for ev in c["cited_evidence"]:
            lines.append(f"      - evidence_id: {ev['evidence_id']}")
            lines.append(f"        bibliography_num: {ev['bibliography_num']}")
            lines.append(f"        url: {json.dumps(ev['url'])}")
            lines.append(f"        tier: {ev['tier']}")
            lines.append(f"        span: '{ev['span']}'")
            lines.append(f"        title: {json.dumps(ev['title'])}")
            lines.append("        span_text: |")
            for body_line in (ev["span_text"] or "").splitlines() or [""]:
                lines.append(f"          {body_line}")
        lines.append("    # tier1_to_fill: claim_type, materiality, citation_context_match, verdict, rationale, reviewer_confidence")
        lines.append("")
    out_path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--report-dir", required=True)
    p.add_argument("--prefix", required=True, help="Claim ID prefix, e.g. Q1")
    p.add_argument("--out", required=True)
    args = p.parse_args()

    report_dir = Path(args.report_dir)
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    doc = build_enumeration(report_dir, args.prefix)
    emit_yaml(doc, out_path)
    print(f"Wrote {out_path} ({doc['claim_count']} claims)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
