"""
Production-scale wiki compose validation against REAL evidence.

Loads PG_TEST_041 (1024 LLM-extracted evidence pieces from a real Qwen 3.5
Plus production run on PFAS water filtration), runs build_wiki on it, then
composes the full report via the OpenAI shim using gpt-4o.

This validates the wiki compose path at production scale (12 sections,
1024 evidence, 81 sources) using real prior-production evidence.

WHAT THIS PROVES:
- Wiki builder handles 1024 evidence + 12 sections without error
- compose_from_wiki() scales to 12 sections without timeout / OOM
- Quality gate evaluates correctly at production scale
- Citation integrity holds with 81 sources
- Bibliography assembles correctly
- Final report > 8K words with > 50 citations

WHAT THIS DOES NOT PROVE:
- G-Eval quality vs Qwen 3.5 Plus baseline (gpt-4o is comparable but different)
- Real LLM evidence extraction (this loads pre-extracted evidence)
- Full search → fetch → extract → wiki → compose end-to-end
"""
import asyncio
import json
import os
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
load_dotenv()

os.environ["PG_WIKI_ENABLED"] = "1"
os.environ["PG_WIKI_5LENS"] = "1"

import logging
logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

# Reuse the OpenAI shim from the smaller test
from scripts.pg_compose_openai_validation import OpenAIShimClient


async def main():
    if not os.getenv("OPENAI_API_KEY"):
        print("ERROR: OPENAI_API_KEY not set")
        return 1

    model_name = os.getenv("OPENAI_TEST_MODEL", "gpt-4o")
    input_arg = sys.argv[1] if len(sys.argv) > 1 else "outputs/polaris_graph/PG_TEST_041.json"
    output_id = os.getenv("OUTPUT_ID", "PRODUCTION_SCALE_VALIDATION")

    print("=" * 70)
    print(f"PRODUCTION-SCALE WIKI COMPOSE — {model_name}")
    print(f"Source: {input_arg}")
    print("=" * 70)

    # ── Stage 1: Load real evidence + outline ────────────────────────
    test_path = Path(input_arg)
    if not test_path.exists():
        print(f"ERROR: {test_path} not found")
        return 1

    print(f"\n[1/4] Loading {test_path.name}")
    with open(test_path, encoding="utf-8") as f:
        d = json.load(f)

    evidence = d["evidence"]
    section_outline = d.get("section_outline", [])
    query = d.get("original_query", "")

    # Convert section_outline to wiki builder format
    outline = [
        {
            "section_id": s.get("section_id", ""),
            "title": s.get("title", ""),
            "description": s.get("description", s.get("title", "")),
        }
        for s in section_outline
    ]

    from collections import Counter
    tier_counts = Counter(e.get("quality_tier", "?") for e in evidence)
    print(f"  Query:    {query[:80]}")
    print(f"  Evidence: {len(evidence)} pieces ({dict(tier_counts)})")
    print(f"  Sources:  {len({e.get('source_url','') for e in evidence})} unique")
    print(f"  Sections: {len(outline)}")

    # ── Stage 2: Build wiki from real evidence ───────────────────────
    print(f"\n[2/4] Building wiki via build_wiki()")
    from src.polaris_graph.wiki.wiki_builder import build_wiki

    start = time.monotonic()
    wiki = build_wiki(
        evidence=evidence, outline=outline,
        query=query, vector_id=output_id,
    )
    build_elapsed = time.monotonic() - start

    # The builder may have augmented the outline with synthesis sections.
    # Use that augmented outline for compose so the new sections are written.
    compose_outline = wiki.outline if wiki.outline else outline

    total_claims = sum(len(c) for c in wiki.section_claims.values())
    print(f"  Built in {build_elapsed:.1f}s: {total_claims} claims, "
          f"{len(wiki.bibliography)} bib entries (outline: {len(compose_outline)} sections)")
    for sid, claims in wiki.section_claims.items():
        sec_title = next((s["title"] for s in compose_outline if s["section_id"] == sid), sid)
        srcs = len({c.get("source_url") for c in claims})
        print(f"    {sid}: {len(claims):3d} claims, {srcs:2d} sources | {sec_title[:42]}")

    # ── Stage 3: Compose via OpenAI shim ────────────────────────────
    print(f"\n[3/4] Composing {len(compose_outline)} sections via {model_name}")
    from src.polaris_graph.wiki.wiki_composer import compose_from_wiki

    client = OpenAIShimClient(model=model_name)
    start = time.monotonic()
    try:
        result = await compose_from_wiki(
            client=client,  # type: ignore[arg-type]
            wiki_result=wiki,
            query=query,
            outline=compose_outline,
        )
    except Exception as exc:
        print(f"\nFAIL: compose_from_wiki crashed: {type(exc).__name__}: {exc}")
        await client.close()
        return 1

    compose_elapsed = time.monotonic() - start
    await client.close()

    # ── Stage 4: Inspect and validate ────────────────────────────────
    sections = result["sections"]
    qm = result["quality_metrics"]
    print(f"\n[4/4] Compose done in {compose_elapsed:.0f}s ({client.calls} LLM calls)")
    print(f"  Status:        {result['status']}")
    print(f"  Quality gate:  {result['quality_gate_result']}")
    print(f"  Sections:      {len(sections)}/{len(compose_outline)}")
    print(f"  Total words:   {qm['total_words']}")
    print(f"  Citations:     {qm['total_citations']}")
    print(f"  Sources used:  {qm['unique_sources']}")
    print(f"  Zero-cite sec: {qm['zero_cite_sections']}")
    print(f"  Avg cite/sec:  {qm['avg_citations_per_section']:.1f}")
    print()
    for s in sections:
        print(f"    {s['section_id']}: {s['word_count']:5d} words, "
              f"{len(s['citation_ids']):3d} cites — {s['title'][:40]}")

    # ── Validation checks (production scale) ─────────────────────────
    print(f"\nValidation checks:")
    checks = []

    v1 = len(sections) == len(compose_outline)
    checks.append(("V1 all sections composed", v1, f"{len(sections)}/{len(compose_outline)}"))

    cot_phrases = ["let me", "i need to", "first, i'll", "thinking about",
                   "let's start", "i should", "i will write", "okay,",
                   "as an ai", "i'll write", "here's a"]
    cot_hits = sum(1 for s in sections for ph in cot_phrases
                   if ph in s["content"].lower())
    v2 = cot_hits == 0
    checks.append(("V2 no CoT leakage", v2, f"{cot_hits} hits"))

    leftover_pattern = re.compile(r"\[(?:REF|CITE|Ref|Cite|ref|cite):\d+\]")
    leftover = sum(1 for s in sections if leftover_pattern.search(s["content"]))
    if leftover_pattern.search(result.get("final_report", "")):
        leftover += 1
    v3 = leftover == 0
    checks.append(("V3 citation prefixes resolved", v3, f"{leftover} leaks"))

    placeholder_hits = sum(1 for s in sections if re.search(r"\[N\]", s["content"]))
    if re.search(r"\[N\]", result.get("final_report", "")):
        placeholder_hits += 1
    v3b = placeholder_hits == 0
    checks.append(("V3b no [N] placeholder", v3b, f"{placeholder_hits} leaks"))

    avg_density = (qm["total_citations"] / qm["total_words"] * 100) if qm["total_words"] else 0
    ceiling = (qm["unique_sources"] / qm["total_words"] * 100) if qm["total_words"] else 0
    target = ceiling * 0.5  # at production scale, 50% of ceiling is fine
    v4 = avg_density >= target
    checks.append(("V4 citation density vs pool",
                   v4, f"{avg_density:.2f}/100w (target {target:.2f}, ceiling {ceiling:.2f})"))

    bib_refs = set(b["ref_num"] for b in wiki.bibliography)
    orphans = sum(1 for s in sections
                  for n in re.findall(r"\[(\d+)\]", s["content"])
                  if int(n) not in bib_refs)
    v5 = orphans == 0
    checks.append(("V5 no orphan citations", v5, f"{orphans} orphans"))

    final = result["final_report"]
    v6 = "## References" in final and "[1]" in final and len(final) > 5000
    checks.append(("V6 final report assembled", v6, f"{len(final)} chars"))

    # Production quality gate: 8K+ words for a multi-section systematic review
    v7 = qm["total_words"] >= 8000
    checks.append(("V7 word count >= 8K (prod gate)", v7, f"{qm['total_words']} words"))

    # Production: 50+ citations across all sections
    v8 = qm["total_citations"] >= 50
    checks.append(("V8 total citations >= 50", v8, f"{qm['total_citations']} cites"))

    # Production: every section has citations
    v9 = qm["zero_cite_sections"] == 0
    checks.append(("V9 zero zero-cite sections", v9,
                   f"{qm['zero_cite_sections']} sections w/o cites"))

    print()
    all_pass = True
    for name, ok, detail in checks:
        marker = "PASS" if ok else "FAIL"
        if not ok:
            all_pass = False
        print(f"  [{marker}] {name:35s} {detail}")

    # ── Save the final report ───────────────────────────────────────
    out_dir = Path("outputs/polaris_graph")
    out_file = out_dir / f"{output_id}.md"
    out_file.write_text(final, encoding="utf-8")
    print(f"\nReport saved: {out_file} ({len(final)} chars)")

    # Also save the full result as JSON for downstream evaluation (G-Eval, etc.)
    json_file = out_dir / f"{output_id}.json"
    json_blob = {
        "vector_id": output_id,
        "original_query": query,
        "final_report": final,
        "sections": sections,
        "bibliography": wiki.bibliography,
        "quality_metrics": qm,
        "section_outline": result["section_outline"],
        "evidence_chain": result["evidence_chain"],
        "model": model_name,
        "compose_seconds": round(compose_elapsed, 1),
    }
    json_file.write_text(json.dumps(json_blob, indent=2, default=str), encoding="utf-8")
    print(f"JSON saved:   {json_file}")

    # ── Cost ────────────────────────────────────────────────────────
    pricing = {
        "gpt-5":         (1.25, 10.00),
        "gpt-4o":        (2.50, 10.00),
        "gpt-4o-mini":   (0.15,  0.60),
        "gpt-4-turbo":   (10.00, 30.00),
    }
    in_p, out_p = pricing.get(model_name, (2.50, 10.00))
    cost = (client.total_input / 1_000_000 * in_p) + (client.total_output / 1_000_000 * out_p)
    print(f"\n  LLM calls:        {client.calls}")
    print(f"  Input tokens:     {client.total_input:,}")
    print(f"  Output tokens:    {client.total_output:,}")
    print(f"  Cost:             ${cost:.4f}")

    print("\n" + "=" * 70)
    print("RESULT: " + ("ALL PASS" if all_pass else "SOME FAILED"))
    print(f"  Build: {build_elapsed:.1f}s | Compose: {compose_elapsed:.0f}s")
    print(f"  {len(sections)} sections, {qm['total_words']} words, "
          f"{qm['total_citations']} citations, {qm['unique_sources']} sources")
    print("=" * 70)

    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
