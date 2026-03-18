"""Full-scale ReAct analysis test on REAL evidence from PG_TEST_047.

Loads 258 evidence pieces about PFAS water filtration, runs the ReAct
agent with PG_REACT_MAX_ITERATIONS=5, and prints detailed diagnostics
showing every tool choice, reasoning, output quality, and citation chain.

Usage:
    python -u scripts/react_full_scale_test.py
"""

import asyncio
import json
import os
import re
import sys
import time


async def main():
    # -----------------------------------------------------------------------
    # 1. Load real evidence from PG_TEST_047
    # -----------------------------------------------------------------------
    result_path = "outputs/polaris_graph/PG_TEST_047.json"
    print(f"\n{'='*80}")
    print("POLARIS v3 ReAct Full-Scale Test")
    print(f"{'='*80}")
    print(f"Loading evidence from: {result_path}")

    with open(result_path, encoding="utf-8") as f:
        result_data = json.load(f)

    raw_evidence = result_data.get("evidence", [])
    query = result_data.get("original_query", "")
    print(f"Query: {query}")
    print(f"Evidence pieces loaded: {len(raw_evidence)}")

    # Build evidence_store dict (keyed by evidence_id)
    evidence_store = {}
    for ev in raw_evidence:
        eid = ev.get("evidence_id", "")
        if not eid:
            continue
        evidence_store[eid] = ev

    evidence_ids = list(evidence_store.keys())

    # Quick stats
    tiers = {}
    numeric_count = 0
    for ev in evidence_store.values():
        t = ev.get("quality_tier", "UNKNOWN")
        tiers[t] = tiers.get(t, 0) + 1
        stmt = ev.get("statement", "")
        if re.search(r'\d+\.?\d*\s*(%|mg|ppt|ppb|ppm|ng|mgd|\$)', stmt):
            numeric_count += 1

    print(f"Tier distribution: {tiers}")
    print(f"Evidence with numeric data: {numeric_count}/{len(evidence_store)}")

    # -----------------------------------------------------------------------
    # 2. Configure ReAct agent for full run
    # -----------------------------------------------------------------------
    os.environ["PG_REACT_MAX_ITERATIONS"] = "5"
    os.environ["PG_REACT_TIMEOUT_SECONDS"] = "180"
    os.environ["PG_REACT_TOOL_TIMEOUT"] = "60"

    from src.polaris_graph.llm.openrouter_client import OpenRouterClient
    from src.polaris_graph.tools.react_agent import ReactAnalysisAgent

    client = OpenRouterClient(session_id="react_full_scale")
    print(f"\nLLM: {client.model}")
    print(f"Max iterations: 5, Timeout: 180s, Tool timeout: 60s")

    # -----------------------------------------------------------------------
    # 3. Run the ReAct agent
    # -----------------------------------------------------------------------
    print(f"\n{'='*80}")
    print("RUNNING REACT AGENT...")
    print(f"{'='*80}\n")

    start_time = time.monotonic()

    agent = ReactAnalysisAgent(
        client=client,
        evidence_store=evidence_store,
        evidence_ids=evidence_ids,
        query=query,
    )
    notebook = await agent.run()

    total_elapsed = time.monotonic() - start_time

    # -----------------------------------------------------------------------
    # 4. Print detailed diagnostics for every step
    # -----------------------------------------------------------------------
    print(f"\n{'='*80}")
    print("STEP-BY-STEP TRACE")
    print(f"{'='*80}")

    for step in notebook.steps:
        status = "OK" if step.result.success else "FAIL"
        print(f"\n--- Step {step.step_number}: {step.tool_name} [{status}] "
              f"({step.elapsed_seconds:.2f}s) ---")
        print(f"  REASONING: {step.reasoning}")

        if step.result.success:
            ev_ids = step.result.source_evidence_ids
            print(f"  Evidence IDs: {len(ev_ids)} unique "
                  f"(first 5: {ev_ids[:5]})")
            print(f"  Data points produced: {len(step.result.data_points_produced)}")
            print(f"  Charts: {len(step.result.charts)}")
            print(f"  Insights ({len(step.result.insights)}):")
            for insight in step.result.insights[:3]:
                print(f"    - {insight[:120]}")
            if step.result.statistics:
                print(f"  Statistics: {json.dumps(step.result.statistics, default=str)[:200]}")

            # Show markdown preview
            md = step.result.markdown
            print(f"  Markdown ({len(md)} chars):")
            # Show first 500 chars
            for line in md[:500].split("\n"):
                print(f"    {line}")
            if len(md) > 500:
                print(f"    ... ({len(md) - 500} more chars)")
        else:
            print(f"  ERROR: {step.result.error}")

    # -----------------------------------------------------------------------
    # 5. Citation provenance analysis
    # -----------------------------------------------------------------------
    print(f"\n{'='*80}")
    print("CITATION PROVENANCE ANALYSIS")
    print(f"{'='*80}")

    context = notebook.build_synthesis_context()
    cite_tokens = re.findall(r"\[CITE:(ev_[a-f0-9]+)\]", context)
    unique_cited = set(cite_tokens)

    print(f"Total [CITE:ev_xxx] tokens in context: {len(cite_tokens)}")
    print(f"Unique evidence IDs cited: {len(unique_cited)}")
    print(f"All source evidence IDs collected: "
          f"{len(notebook.get_all_source_evidence_ids())}")

    # Verify all cited IDs exist in evidence_store
    phantom_cites = [c for c in unique_cited if c not in evidence_store]
    print(f"Phantom citations (ID not in evidence): {len(phantom_cites)}")
    if phantom_cites:
        print(f"  PHANTOM IDs: {phantom_cites[:10]}")

    # Check for "POLARIS" leakage
    polaris_count = context.count("POLARIS")
    toolkit_count = context.count("Analysis Toolkit")
    print(f"'POLARIS' in context: {polaris_count}")
    print(f"'Analysis Toolkit' in context: {toolkit_count}")

    # -----------------------------------------------------------------------
    # 6. AnalysisEntry output quality
    # -----------------------------------------------------------------------
    entries = notebook.to_entries()

    print(f"\n{'='*80}")
    print(f"ANALYSIS ENTRIES ({len(entries)} total)")
    print(f"{'='*80}")

    for entry in entries:
        cite_count = len(re.findall(r"\[CITE:", entry.markdown))
        print(f"\n  [{entry.analysis_type}] {entry.title[:80]}")
        print(f"    entry_id: {entry.entry_id}")
        print(f"    source_evidence_ids: {len(entry.source_evidence_ids)}")
        print(f"    CITE tokens in markdown: {cite_count}")
        print(f"    statistics: {json.dumps(entry.statistics, default=str)[:150]}")
        print(f"    insights: {entry.insights[:2]}")
        print(f"    markdown length: {len(entry.markdown)} chars")
        if entry.image_base64:
            print(f"    HAS CHART: {len(entry.image_base64)} base64 chars")

    # -----------------------------------------------------------------------
    # 7. Synthesis context preview (what the section writer would see)
    # -----------------------------------------------------------------------
    print(f"\n{'='*80}")
    print("SYNTHESIS CONTEXT PREVIEW (first 2000 chars)")
    print(f"{'='*80}")
    for line in context[:2000].split("\n"):
        print(f"  {line}")
    if len(context) > 2000:
        print(f"\n  ... ({len(context) - 2000} more chars)")

    # -----------------------------------------------------------------------
    # 8. Summary
    # -----------------------------------------------------------------------
    print(f"\n{'='*80}")
    print("SUMMARY")
    print(f"{'='*80}")
    print(f"  Total time: {total_elapsed:.1f}s")
    print(f"  Steps taken: {notebook.step_count}")
    print(f"  Steps succeeded: {notebook.successful_steps}")
    print(f"  Tool sequence: {' -> '.join(s.tool_name for s in notebook.steps)}")
    print(f"  Data points extracted: {len(notebook.data_points)}")
    print(f"  Analysis entries: {len(entries)}")
    print(f"  Unique evidence cited: {len(unique_cited)}")
    print(f"  Phantom citations: {len(phantom_cites)}")
    print(f"  POLARIS leakage: {polaris_count}")
    print(f"  API cost: ${client.usage.total_cost_usd:.4f}")

    # Pass/fail verdict
    print(f"\n{'='*80}")
    failures = []
    if notebook.successful_steps < 2:
        failures.append(f"Only {notebook.successful_steps} successful steps (need >= 2)")
    if phantom_cites:
        failures.append(f"{len(phantom_cites)} phantom citations")
    if polaris_count > 0:
        failures.append(f"'POLARIS' found {polaris_count} times in output")
    if toolkit_count > 0:
        failures.append(f"'Analysis Toolkit' found {toolkit_count} times in output")
    if len(cite_tokens) == 0:
        failures.append("Zero [CITE:ev_xxx] tokens in synthesis context")
    if len(entries) == 0:
        failures.append("Zero AnalysisEntry objects produced")

    if failures:
        print("VERDICT: FAIL")
        for f in failures:
            print(f"  - {f}")
    else:
        print("VERDICT: PASS")
        print(f"  {notebook.successful_steps} tools executed autonomously")
        print(f"  {len(cite_tokens)} citations traced to original sources")
        print(f"  {len(entries)} analysis entries ready for synthesis")
        print(f"  Zero POLARIS leakage, zero phantom citations")
    print(f"{'='*80}\n")


if __name__ == "__main__":
    asyncio.run(main())
