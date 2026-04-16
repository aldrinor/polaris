"""Auto-responder for VerificationBatch requests in the loopback queue.

Pattern: structured:VerificationBatch — the pipeline asks whether each claim is
SUPPORTED/PARTIALLY_SUPPORTED/NOT_SUPPORTED based on the cited source content.

For loopback validation purposes (D3 URL canonicalization test), verification quality
isn't the goal — pipeline progression is. This auto-responder reads each claim
statement, finds the direct_quote, and if the quote appears verbatim in the cited
source content, marks the claim SUPPORTED with confidence 0.88. Otherwise
PARTIALLY_SUPPORTED (0.65). NOT_SUPPORTED is never emitted because that would
trigger the faithfulness gate and drop evidence from the wiki pipeline — which
would distort the D3 URL fix test by reducing the number of claims flowing through
wiki_builder's url_to_ref lookup.

Only handles requests whose call_type == 'structured:VerificationBatch' and whose
prompt starts with 'Verify each of the following'. Other requests left alone.
"""
from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PENDING = ROOT / "loopback" / "pending"
RESPONSES = ROOT / "loopback" / "responses"


def parse_claims(prompt: str) -> list[dict]:
    """Split the prompt into per-claim blocks."""
    parts = re.split(r"^Claim \d+:", prompt, flags=re.MULTILINE)
    claims = []
    for part in parts[1:]:
        m_quote = re.search(r'Direct quote:\s*"([^"]*)"', part)
        m_source = re.search(r"Source content excerpt:\s*\n\s*---\n(.*?)(?:\n  ---|\nClaim \d+:|$)", part, re.DOTALL)
        statement_lines = part.strip().split("\n")
        statement = statement_lines[0].strip() if statement_lines else ""
        quote = m_quote.group(1) if m_quote else ""
        source_excerpt = m_source.group(1) if m_source else ""
        claims.append({"statement": statement, "quote": quote, "source_excerpt": source_excerpt})
    return claims


def try_handle(req_path: Path) -> bool:
    try:
        with req_path.open(encoding="utf-8") as f:
            req = json.load(f)
    except Exception:
        return False
    if req.get("call_type", "") != "structured:VerificationBatch":
        return False
    prompt = req.get("prompt", "") or ""
    if not prompt.startswith("Verify each of the following"):
        return False
    claims = parse_claims(prompt)
    if not claims:
        return False

    verifications = []
    support_count = 0
    for c in claims:
        quote = (c.get("quote") or "").strip()
        excerpt = c.get("source_excerpt") or ""
        verdict = "PARTIALLY_SUPPORTED"
        confidence = 0.65
        if quote and excerpt and quote[:60] in excerpt:
            verdict = "SUPPORTED"
            confidence = 0.88
            support_count += 1
        elif quote and excerpt and quote[:30] in excerpt:
            verdict = "SUPPORTED"
            confidence = 0.80
            support_count += 1
        verifications.append({
            "claim": c["statement"],
            "verdict": verdict,
            "confidence": confidence,
            "supporting_evidence": [],
        })

    faithfulness = round(support_count / len(claims), 2) if claims else 0.0
    result = {
        "verifications": verifications,
        "overall_faithfulness": faithfulness,
    }
    req_id = req.get("request_id") or req_path.stem.replace("req_", "")
    resp_path = RESPONSES / f"resp_{req_id}.json"
    tmp = resp_path.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(
            {"content": json.dumps(result, ensure_ascii=False),
             "input_tokens": len(prompt) // 4,
             "output_tokens": len(verifications) * 40},
            f,
            ensure_ascii=False,
        )
    tmp.replace(resp_path)
    print(f"  [auto-VERIFY] {req_path.name} -> {len(verifications)} claims (faithfulness={faithfulness})")
    return True


def main() -> int:
    handled_total = 0
    idle_polls = 0
    MAX_IDLE_POLLS = 1800  # ~5 minutes at 1s poll
    while True:
        handled_this_cycle = 0
        for p in sorted(PENDING.glob("req_*.json")):
            try:
                if try_handle(p):
                    handled_this_cycle += 1
                    handled_total += 1
            except Exception as exc:  # noqa: BLE001
                print(f"  [auto-VERIFY] error on {p.name}: {exc}")
        if handled_this_cycle == 0:
            idle_polls += 1
            if idle_polls >= MAX_IDLE_POLLS:
                break
            time.sleep(1.0)
        else:
            idle_polls = 0
            time.sleep(0.5)
    print(f"[auto-VERIFY] drained {handled_total} verification batches")
    return 0


if __name__ == "__main__":
    sys.exit(main())
