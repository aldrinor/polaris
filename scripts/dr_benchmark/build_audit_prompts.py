#!/usr/bin/env python3
"""Generate self-contained §-1.1 claim-by-claim audit prompts from a claims ledger.

Splits ``claims_ledger.jsonl`` into N chunks and writes one Codex/Claude audit
prompt per chunk. Each prompt is fully self-contained: the research question +
scope, the §-1.1 verdict rubric, the machine-parseable output schema, and the
chunk's claims paired with their EXACT cited span. The auditor (Codex via
`codex exec`, or a Claude workflow agent) verdicts every claim against its span —
VERIFIED / PARTIAL / UNSUPPORTED / FABRICATED / UNREACHABLE — with the span
substring that justifies the verdict. NO sampling: every claim in the ledger is
emitted into exactly one chunk.

Usage:
    python -m scripts.dr_benchmark.build_audit_prompts <run_dir> --question-file Q --chunks N --out-dir DIR
"""

# Standard Library
import argparse
import json
import sys
from pathlib import Path

_RUBRIC = """You are an independent clinical-grade faithfulness auditor applying the §-1.1
line-by-line standard. For EACH claim below, decide whether the CITED SPAN (the
exact source substring, given verbatim) supports the CLAIM. This is claim-vs-span
only — do NOT use outside knowledge to confirm a claim; judge solely whether the
span entails it.

Per-claim verdict (exactly one):
- VERIFIED    : the span directly supports the full claim (incl. every number/qualifier).
- PARTIAL     : the span supports part of the claim but not all of it (e.g. a number or
                qualifier in the claim is absent from / differs from the span).
- UNSUPPORTED : the span is on-topic but does NOT support the claim.
- FABRICATED  : the claim asserts something the span contradicts, or a number/entity that
                does not appear in the span at all.
- UNREACHABLE : the span is empty / missing / not resolvable.
Also flag OFF_TOPIC=true if the claim (regardless of span support) is not about the
research question's topic (the restructuring impact of AI on the labor market).

For every claim output one JSON object per line (JSONL), no prose:
{"claim_id": "...", "verdict": "VERIFIED|PARTIAL|UNSUPPORTED|FABRICATED|UNREACHABLE",
 "off_topic": true|false, "justify_span_substring": "<=160 chars of the span that
 decides it", "note": "<=160 chars only if PARTIAL/UNSUPPORTED/FABRICATED/OFF_TOPIC"}
Output ONLY the JSONL, one object per claim, all claims in this chunk."""


def _claim_block(rec: dict) -> str:
    lines = [f"CLAIM_ID {rec['claim_id']} (section: {rec.get('section_title')}, severity {rec.get('severity')})",
             f"CLAIM: {rec['claim_text']}"]
    if not rec["citations"]:
        lines.append("CITED SPAN: (none — sentence carried no provenance token)")
    for c in rec["citations"]:
        if c.get("span_text"):
            src = c.get("source_title") or c.get("doi") or c.get("source_url") or "?"
            lines.append(f"CITED SPAN [{c['evidence_id']}] (source: {src}):")
            lines.append(f'"""{c["span_text"]}"""')
        else:
            lines.append(f"CITED SPAN [{c['evidence_id']}]: UNREACHABLE ({c.get('resolve_status')})")
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("run_dir", type=Path)
    ap.add_argument("--question", type=str, required=True)
    ap.add_argument("--chunks", type=int, default=5)
    ap.add_argument("--out-dir", type=Path, required=True)
    args = ap.parse_args(argv)

    ledger = [json.loads(l) for l in (args.run_dir / "claims_ledger.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    args.out_dir.mkdir(parents=True, exist_ok=True)

    n = len(ledger)
    k = -(-n // args.chunks)  # ceil
    written = []
    for ci in range(args.chunks):
        chunk = ledger[ci * k:(ci + 1) * k]
        if not chunk:
            continue
        header = (
            f"RESEARCH QUESTION (scope): {args.question}\n\n"
            f"{_RUBRIC}\n\n"
            f"=== CLAIMS TO AUDIT (chunk {ci+1}; {len(chunk)} claims) ===\n\n"
        )
        body = "\n\n".join(_claim_block(r) for r in chunk)
        p = args.out_dir / f"audit_prompt_chunk{ci+1:02d}.txt"
        p.write_text(header + body, encoding="utf-8")
        written.append((p, len(chunk)))
    total = sum(c for _, c in written)
    print(f"chunks={len(written)} total_claims={total} (ledger={n})")
    for p, c in written:
        print(f"  {p}  ({c} claims)")
    assert total == n, f"chunk coverage mismatch: {total} != {n} (NO claim may be dropped)"
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
