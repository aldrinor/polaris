"""Validate sub-agent responses against production Pydantic schemas + audit checks.

Tests:
  V1. verifier_response.json parses as VerificationBatch (with model_validator coercion)
  V2. all 4 expected claims have a verdict
  V3. supporting_evidence ids actually exist in the input
  V4. verdicts are in the canonical vocabulary

  S1. section_writer_response.txt has [CITE:ev_xxx] markers
  S2. all citation IDs reference real evidence_ids from the input
  S3. >= 2 unique sources cited
  S4. no source cited > 3 times
  S5. no CoT leakage markers (I think, Let me, <thinking>, etc.)
  S6. ends with terminal punctuation (no truncation)
  S7. has Key Findings subsection
  S8. word count is sensible (>= 500, <= 2000)
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
import os
os.chdir(PROJECT_ROOT)

OUT = PROJECT_ROOT / "tests" / "fixtures" / "subagent_prompts"


def section(name):
    print(f"\n{'='*70}\n  {name}\n{'='*70}")


def check(name, cond, detail=""):
    status = "PASS" if cond else "FAIL"
    print(f"  [{status}] {name}{' -- ' + detail if detail else ''}")
    return cond


def validate_verifier():
    section("VERIFIER PROMPT TEST")
    from src.polaris_graph.schemas import VerificationBatch

    inputs = json.loads((OUT / "verifier_inputs.json").read_text(encoding="utf-8"))
    raw = (OUT / "verifier_response.json").read_text(encoding="utf-8")

    all_pass = True

    # V1: parse
    try:
        vb = VerificationBatch.model_validate_json(raw)
        all_pass &= check("V1. parses as VerificationBatch", True,
                          f"{len(vb.verifications)} verifications, faith={vb.overall_faithfulness}")
    except Exception as e:
        print(f"  parse error: {e}")
        all_pass &= check("V1. parses as VerificationBatch", False, str(e)[:120])
        return all_pass  # can't continue

    # V2: count match
    all_pass &= check(
        "V2. one verification per input claim",
        len(vb.verifications) == len(inputs),
        f"got {len(vb.verifications)}, expected {len(inputs)}",
    )

    # V3: supporting_evidence ids exist
    valid_ids = {e["evidence_id"] for e in inputs}
    bad_refs = []
    for v in vb.verifications:
        for ref in v.supporting_evidence:
            if ref not in valid_ids:
                bad_refs.append(ref)
    all_pass &= check(
        "V3. supporting_evidence references real evidence_ids",
        not bad_refs,
        f"unknown refs: {bad_refs[:3]}" if bad_refs else "all known",
    )

    # V4: verdict vocabulary
    canonical = {"SUPPORTED", "PARTIALLY_SUPPORTED", "NOT_SUPPORTED"}
    bad_verdicts = [v.verdict for v in vb.verifications if v.verdict not in canonical]
    all_pass &= check(
        "V4. verdicts use canonical vocabulary",
        not bad_verdicts,
        f"bad: {bad_verdicts}" if bad_verdicts else "",
    )

    # V5: confidence in [0, 1]
    bad_conf = [v.confidence for v in vb.verifications if not (0.0 <= v.confidence <= 1.0)]
    all_pass &= check(
        "V5. confidence in [0,1]",
        not bad_conf,
        f"bad: {bad_conf}" if bad_conf else "",
    )

    # Print verdict summary
    print(f"\n  Verdict summary:")
    for i, v in enumerate(vb.verifications):
        stored = inputs[i].get("stored_verdict", "?")
        print(f"    {i+1}. {v.verdict} (conf={v.confidence:.2f}) -- stored as {stored}")

    return all_pass


def validate_section_writer():
    section("SECTION WRITER PROMPT TEST")
    inputs = json.loads((OUT / "section_writer_inputs.json").read_text(encoding="utf-8"))
    text = (OUT / "section_writer_response.txt").read_text(encoding="utf-8")

    all_pass = True
    valid_ids = {e["evidence_id"] for e in inputs}
    source_for_id = {e["evidence_id"]: e["source_title"] for e in inputs}

    # S1: citations present
    cite_pattern = re.compile(r"\[CITE:(ev_[a-f0-9]+)\]")
    citations = cite_pattern.findall(text)
    all_pass &= check(
        "S1. has [CITE:ev_xxx] markers",
        len(citations) > 0,
        f"{len(citations)} citations",
    )

    # S2: all cited ids exist
    bad_cites = [c for c in citations if c not in valid_ids]
    all_pass &= check(
        "S2. citations reference real evidence_ids",
        not bad_cites,
        f"unknown: {bad_cites[:3]}" if bad_cites else "all known",
    )

    # S3: >= 2 unique sources
    cited_sources = {source_for_id[c] for c in citations if c in source_for_id}
    all_pass &= check(
        "S3. >= 2 unique sources cited",
        len(cited_sources) >= 2,
        f"{len(cited_sources)} unique sources",
    )

    # S4: no source > 3 times
    from collections import Counter
    src_counts = Counter(source_for_id[c] for c in citations if c in source_for_id)
    over = {s: n for s, n in src_counts.items() if n > 3}
    all_pass &= check(
        "S4. no source cited > 3 times",
        not over,
        f"over: {dict(list(over.items())[:2])}" if over else "",
    )

    # S5: no CoT markers
    cot_patterns = [
        r"\bI (?:think|will|need to|should)\b",
        r"\bLet me\b",
        r"<think(?:ing)?>",
        r"\bMy approach\b",
        r"\bFirst,? I\b",
        r"\bHere'?s? (?:my|the) (?:plan|outline|response)\b",
        r"\bAs an (?:AI|LLM|assistant)\b",
        r"```",  # code fences
    ]
    cot_hits = []
    for p in cot_patterns:
        m = re.search(p, text, re.IGNORECASE)
        if m:
            cot_hits.append(f"{p!r}: {m.group(0)!r}")
    all_pass &= check(
        "S5. no CoT/scaffolding markers",
        not cot_hits,
        f"{len(cot_hits)} hits: {cot_hits[0]}" if cot_hits else "",
    )

    # S6: ends with terminal punctuation
    last_chars = text.rstrip()[-3:]
    all_pass &= check(
        "S6. ends with terminal punctuation",
        text.rstrip().endswith((".", "?", "!", ")", '"')),
        f"last chars: {last_chars!r}",
    )

    # S7: Key Findings subsection
    has_kf = bool(re.search(r"\*\*Key Findings\*\*|^#+\s*Key Findings", text, re.MULTILINE))
    all_pass &= check(
        "S7. has Key Findings subsection",
        has_kf,
    )

    # S8: word count sensible
    wc = len(text.split())
    all_pass &= check(
        "S8. word count in [500, 2000]",
        500 <= wc <= 2000,
        f"{wc} words",
    )

    # Bonus: detect repeated section title
    sec_title = "Mechanisms and Metabolic Effects of Intermittent Fasting"
    title_repeated = text.count(sec_title) >= 1
    if title_repeated:
        print(f"  [WARN] section title appears {text.count(sec_title)}x in body (rule: should NOT repeat)")

    return all_pass


def main():
    if not (OUT / "verifier_response.json").exists():
        print(f"MISSING: {OUT / 'verifier_response.json'}")
        return 2
    if not (OUT / "section_writer_response.txt").exists():
        print(f"MISSING: {OUT / 'section_writer_response.txt'}")
        return 2

    v_pass = validate_verifier()
    s_pass = validate_section_writer()

    section("SUMMARY")
    print(f"  Verifier prompt: {'PASS' if v_pass else 'FAIL'}")
    print(f"  Section writer prompt: {'PASS' if s_pass else 'FAIL'}")
    return 0 if (v_pass and s_pass) else 1


if __name__ == "__main__":
    sys.exit(main())
