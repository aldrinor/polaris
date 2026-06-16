#!/usr/bin/env python3
"""Cross-review aggregator for the §-1.1 dual (Claude + Codex) claim audit.

Reads the per-chunk JSONL verdict files from BOTH independent auditors, joins
them on claim_id against the claims ledger, and emits:
  - audit_combined.jsonl : per-claim {claim_id, claude, codex, agree, final}
  - audit_summary.md     : verdict distribution per auditor, agreement rate, and
                           the full list of every non-VERIFIED / off-topic / and
                           auditor-DISAGREEMENT claim (the §-1.1 findings — no
                           sampling, no counts-as-quality; counts are reported only
                           as audit coverage, never as a quality score).

The combined `final` verdict is the WORSE of the two auditors (clinical safety:
if either auditor flags a problem, surface it). VERIFIED only when BOTH agree.

Usage:
    python -m scripts.dr_benchmark.aggregate_audit <run_dir> \
        --claude-glob 'codex_audit/claude_verdict_chunk*.jsonl' \
        --codex-glob  'codex_audit/codex_verdict_chunk*.jsonl'
"""

# Standard Library
import argparse
import glob
import json
import re
import sys
from pathlib import Path

# Severity order: worse verdict wins the `final`.
_RANK = {"FABRICATED": 5, "UNSUPPORTED": 4, "UNREACHABLE": 3, "PARTIAL": 2, "VERIFIED": 1, None: 0}


def _load_verdicts(run_dir: Path, pattern: str) -> dict:
    out: dict[str, dict] = {}
    for fp in sorted(glob.glob(str(run_dir / pattern))):
        text = Path(fp).read_text(encoding="utf-8", errors="ignore")
        for line in text.splitlines():
            line = line.strip()
            if not line or not line.startswith("{"):
                # tolerate code fences / stray prose around the JSONL
                m = re.search(r"\{.*\}", line)
                if not m:
                    continue
                line = m.group(0)
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            cid = rec.get("claim_id")
            if cid:
                out[cid] = rec
    return out


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("run_dir", type=Path)
    ap.add_argument("--claude-glob", default="codex_audit/claude_verdict_chunk*.jsonl")
    ap.add_argument("--codex-glob", default="codex_audit/codex_verdict_chunk*.jsonl")
    args = ap.parse_args(argv)
    rd = args.run_dir

    ledger = {json.loads(l)["claim_id"]: json.loads(l)
              for l in (rd / "claims_ledger.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()}
    claude = _load_verdicts(rd, args.claude_glob)
    codex = _load_verdicts(rd, args.codex_glob)

    combined = []
    for cid, lrec in ledger.items():
        cl = claude.get(cid, {})
        cx = codex.get(cid, {})
        clv, cxv = cl.get("verdict"), cx.get("verdict")
        final = clv if _RANK.get(clv, 0) >= _RANK.get(cxv, 0) else cxv
        agree = (clv == cxv) and clv is not None
        off_topic = bool(cl.get("off_topic")) or bool(cx.get("off_topic"))
        combined.append({
            "claim_id": cid,
            "section": lrec.get("section_title"),
            "claim_text": lrec.get("claim_text", "")[:200],
            "claude": clv, "codex": cxv, "agree": agree, "final": final,
            "off_topic": off_topic,
            "claude_note": cl.get("note", ""), "codex_note": cx.get("note", ""),
            "missing_auditor": [n for n, v in (("claude", clv), ("codex", cxv)) if v is None],
        })
    combined.sort(key=lambda r: r["claim_id"])

    (rd / "codex_audit" / "audit_combined.jsonl").write_text(
        "\n".join(json.dumps(c, ensure_ascii=False) for c in combined), encoding="utf-8")

    def dist(key):
        d = {}
        for c in combined:
            d[c[key]] = d.get(c[key], 0) + 1
        return d

    n = len(combined)
    both = [c for c in combined if not c["missing_auditor"]]
    agreed = sum(1 for c in both if c["agree"])
    findings = [c for c in combined if c["final"] not in ("VERIFIED",) or c["off_topic"] or not c["agree"]]

    lines = [
        "# §-1.1 dual claim audit — combined findings",
        "",
        f"claims audited: {n} (audit COVERAGE, not a quality score)",
        f"both auditors present: {len(both)}; auditor agreement: {agreed}/{len(both)}"
        + (f" ({agreed/len(both):.1%})" if both else ""),
        "",
        f"Claude verdict distribution: {dist('claude')}",
        f"Codex verdict distribution:  {dist('codex')}",
        f"Combined-final distribution: {dist('final')}",
        f"off-topic flagged (either): {sum(1 for c in combined if c['off_topic'])}",
        "",
        "## Every non-VERIFIED / off-topic / auditor-disagreement claim (the findings)",
        "",
    ]
    for c in findings:
        lines.append(
            f"- **{c['claim_id']}** [{c['section']}] final={c['final']} "
            f"(claude={c['claude']}, codex={c['codex']}"
            + (", OFF_TOPIC" if c["off_topic"] else "")
            + (", DISAGREE" if not c["agree"] and not c["missing_auditor"] else "")
            + (f", MISSING={c['missing_auditor']}" if c["missing_auditor"] else "")
            + f")\n    claim: {c['claim_text']}"
            + (f"\n    claude_note: {c['claude_note']}" if c["claude_note"] else "")
            + (f"\n    codex_note: {c['codex_note']}" if c["codex_note"] else "")
        )
    (rd / "codex_audit" / "audit_summary.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"claims={n} agreement={agreed}/{len(both)} findings={len(findings)}")
    print(f"final_dist={dist('final')}")
    print(f"wrote {rd/'codex_audit'/'audit_summary.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
