"""Enumerate every verified sentence in Q5 Pharmacare for Tier-1 audit pilot.

Outputs YAML enumeration to .codex/I-eval-002/q5_claims_enumeration.yaml
suitable for both Claude (manual fill) and Codex (inline brief).
"""
from __future__ import annotations

import json
import re
from pathlib import Path

Q5_DIR = Path("outputs/I-beat-001_round_q5_retry/policy/carney_pharmacare_bill_c64_evidence")


def main() -> None:
    verification = json.loads((Q5_DIR / "verification_details.json").read_text(encoding="utf-8"))
    bibliography = json.loads((Q5_DIR / "bibliography.json").read_text(encoding="utf-8"))
    pool = json.loads((Q5_DIR / "evidence_pool.json").read_text(encoding="utf-8"))

    bib_by_evid = {entry["evidence_id"]: entry for entry in bibliography}
    pool_by_evid = {entry["evidence_id"]: entry for entry in pool if isinstance(entry, dict)}

    out_lines = [
        "# Q5 Pharmacare claim enumeration — Tier-1 pilot (GH#420 I-eval-002)",
        f"# Total verified-finding claims: pending count",
        "",
        "schema_version: tier1_v1",
        "report: outputs/I-beat-001_round_q5_retry/policy/carney_pharmacare_bill_c64_evidence/report.md",
        "claims:",
    ]
    claim_idx = 0
    for section in verification["sections"]:
        section_title = section["title"]
        for kept in section["kept"]:
            claim_idx += 1
            sentence = kept["sentence"]
            tokens = kept.get("tokens", [])
            # Clean sentence: strip provenance tokens for display
            clean = re.sub(r"\[#ev:[^\]]+\]", "", sentence).strip()
            # Map provenance tokens to bibliography entries
            cited = []
            for tok in tokens:
                evid = tok["evidence_id"]
                bib_entry = bib_by_evid.get(evid, {})
                pool_entry = pool_by_evid.get(evid, {})
                # The pool entry has the full source content
                cited.append({
                    "evidence_id": evid,
                    "bibliography_num": bib_entry.get("num"),
                    "url": bib_entry.get("url", "<unknown>"),
                    "tier": bib_entry.get("tier", "<unknown>"),
                    "title": bib_entry.get("statement", "<unknown>"),
                    "span_start": tok["start"],
                    "span_end": tok["end"],
                    "span_text_preview": (pool_entry.get("direct_quote", "") or pool_entry.get("content", "") or "")[tok["start"]:tok["end"]],
                })
            out_lines.append(f"  - claim_id: Q5-T1-{claim_idx:03d}")
            out_lines.append(f"    section: {section_title!r}")
            out_lines.append(f"    sentence: {clean!r}")
            out_lines.append(f"    cited_evidence:")
            for c in cited:
                out_lines.append(f"      - evidence_id: {c['evidence_id']}")
                out_lines.append(f"        bibliography_num: {c['bibliography_num']}")
                out_lines.append(f"        url: {c['url']!r}")
                out_lines.append(f"        tier: {c['tier']}")
                out_lines.append(f"        span: '{c['span_start']}-{c['span_end']}'")
                out_lines.append(f"        title: {c['title']!r}")
                out_lines.append(f"        span_text: |")
                for line in c['span_text_preview'].replace('\r', '').split('\n'):
                    out_lines.append(f"          {line}")
            out_lines.append(f"    # tier1_to_fill: claim_type, materiality, citation_context_match, verdict, rationale, reviewer_confidence")
            out_lines.append("")

    # Fix the placeholder count
    out_lines[1] = f"# Total verified-finding claims: {claim_idx}"
    out = "\n".join(out_lines)
    out_path = Path(".codex/I-eval-002/q5_claims_enumeration.yaml")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(out, encoding="utf-8")
    print(f"Wrote {out_path} ({claim_idx} claims, {len(out)} bytes)")


if __name__ == "__main__":
    main()
