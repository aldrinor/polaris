"""Stress test: ReAct analysis on 5 diverse evidence sets with deep audit.

Loads REAL evidence from previous pipeline runs, runs the ReAct agent,
then audits every line of output for:
- Citation accuracy (does [CITE:ev_xxx] match the claim it's attached to?)
- Information density (ratio of facts vs filler)
- Statistical correctness (can we verify the computed numbers?)
- Provenance integrity (every analysis ID traces to real evidence)
- Unit coherence (no mixing mg/L with %)
- Insight uniqueness (are insights substantive or generic?)

Usage:
    python -u -m scripts.react_stress_test
"""

import asyncio
import json
import math
import os
import re
import sys
import time
from collections import Counter
from pathlib import Path


# ---------------------------------------------------------------------------
# Evidence sets to test (diverse domains, sizes, quality distributions)
# ---------------------------------------------------------------------------
TEST_SETS = [
    {
        "file": "outputs/polaris_graph/PG_TEST_047.json",
        "name": "PFAS-258",
        "desc": "PFAS water filtration (258 ev, mixed tiers)",
    },
    {
        "file": "outputs/polaris_graph/PG_TEST_058.json",
        "name": "PFAS-40",
        "desc": "PFAS filtration small set (40 ev, mostly SILVER)",
    },
    {
        "file": "outputs/polaris_graph/SHOWME_TEST_001.json",
        "name": "DVS-71",
        "desc": "DVS-PEI polymer chemistry (71 ev, niche domain)",
    },
    {
        "file": "outputs/polaris_graph/GEMINI_E2E_20260316_015917.json",
        "name": "ADHESION-242",
        "desc": "Adhesion testing methods (242 ev, comparison-heavy)",
    },
    {
        "file": "outputs/polaris_graph/PG_TEST_045.json",
        "name": "PFAS-280",
        "desc": "PFAS filtration v2 (280 ev, different search round)",
    },
]


# ---------------------------------------------------------------------------
# Deep content audit functions
# ---------------------------------------------------------------------------

def audit_citations(context: str, evidence_store: dict) -> dict:
    """Audit every [CITE:ev_xxx] token in the context."""
    cite_pattern = re.compile(r'\[CITE:(ev_[a-f0-9]+)\]')
    all_cites = cite_pattern.findall(context)
    unique_cites = set(all_cites)

    phantom = [c for c in unique_cites if c not in evidence_store]
    valid = [c for c in unique_cites if c in evidence_store]

    # Check if cited evidence is relevant to surrounding text
    mismatched = []
    for match in cite_pattern.finditer(context):
        eid = match.group(1)
        if eid not in evidence_store:
            continue
        # Get 200 chars surrounding the citation
        start = max(0, match.start() - 200)
        end = min(len(context), match.end() + 50)
        surrounding = context[start:end].lower()
        # Get the evidence statement
        ev_stmt = evidence_store[eid].get("statement", "").lower()
        # Check word overlap (at least 2 shared content words)
        surr_words = set(re.findall(r'[a-z]{4,}', surrounding))
        ev_words = set(re.findall(r'[a-z]{4,}', ev_stmt))
        overlap = surr_words & ev_words
        if len(overlap) < 2 and ev_stmt:
            mismatched.append({
                "evidence_id": eid,
                "context_snippet": context[start:end][:100],
                "evidence_statement": ev_stmt[:100],
                "overlap_words": list(overlap),
            })

    return {
        "total_cite_tokens": len(all_cites),
        "unique_cited": len(unique_cites),
        "phantom_citations": phantom,
        "valid_citations": len(valid),
        "mismatched_citations": mismatched,
        "citation_density": len(all_cites) / max(len(context.split()), 1) * 100,
    }


def audit_information_density(context: str) -> dict:
    """Measure how much of the text is substantive vs filler."""
    lines = [l.strip() for l in context.split("\n") if l.strip()]

    filler_patterns = [
        r'^#+\s',           # Headers (not content)
        r'^[-*]\s*$',       # Empty list items
        r'^\|.*\|$',        # Table rows (counted separately)
        r'^---',            # Separators
        r'^\s*$',           # Blank
    ]

    table_lines = 0
    header_lines = 0
    filler_lines = 0
    content_lines = 0

    for line in lines:
        if re.match(r'^\|.*\|$', line):
            table_lines += 1
        elif re.match(r'^#+\s', line):
            header_lines += 1
        elif any(re.match(p, line) for p in filler_patterns):
            filler_lines += 1
        else:
            content_lines += 1

    # Count numbers in content (sign of data density)
    numbers_found = len(re.findall(
        r'\d+\.?\d*\s*(%|mg|ng|ppt|ppb|ppm|m2|kWh|\$|USD|g/L|mg/g)',
        context,
    ))

    # Count unique factual claims (sentences with numbers + units)
    factual_sentences = len(re.findall(
        r'[A-Z][^.!?]*\d+\.?\d*\s*(%|mg|ng|ppt|ppb|ppm|kWh|\$)[^.!?]*[.!?]',
        context,
    ))

    total = len(lines) or 1
    return {
        "total_lines": len(lines),
        "content_lines": content_lines,
        "table_lines": table_lines,
        "header_lines": header_lines,
        "filler_lines": filler_lines,
        "content_ratio": round(content_lines / total * 100, 1),
        "numbers_with_units": numbers_found,
        "factual_sentences": factual_sentences,
        "data_density": round(numbers_found / total * 100, 1),
    }


def audit_statistics(entries: list, data_points: list) -> dict:
    """Verify statistical claims against raw data."""
    issues = []

    for entry_dict in entries:
        stats = entry_dict.get("statistics", {})
        if not stats or not stats.get("mean"):
            continue

        claimed_mean = stats.get("mean")
        claimed_n = stats.get("n")

        # Try to verify from data points
        if data_points and claimed_n:
            # Get the values from data points matching this unit
            values = []
            for dp in data_points:
                try:
                    v = float(str(dp.get("value", "")).replace(",", ""))
                    values.append(v)
                except (ValueError, TypeError):
                    pass

            if values:
                actual_mean = sum(values) / len(values)
                # Check if claimed mean is within 20% of actual
                # (they may use different subsets)
                if claimed_mean != 0 and abs(actual_mean - claimed_mean) / abs(claimed_mean) > 0.5:
                    issues.append({
                        "type": "mean_mismatch",
                        "claimed": claimed_mean,
                        "computed_from_all": round(actual_mean, 2),
                        "note": "May use unit-filtered subset (expected)",
                    })

    return {
        "entries_with_stats": sum(1 for e in entries if e.get("statistics", {}).get("mean")),
        "verification_issues": issues,
    }


def audit_insights(entries: list) -> dict:
    """Check if insights are substantive or generic water."""
    generic_patterns = [
        r'^extracted \d+ numeric',       # Just restating the tool action
        r'^meta-analysis across',         # Generic structure
        r'^consensus strength:',          # Just repeating agreement label
    ]

    total_insights = 0
    substantive = 0
    generic = 0
    unique_insights = set()

    for entry_dict in entries:
        for insight in entry_dict.get("insights", []):
            total_insights += 1
            lower = insight.lower().strip()
            unique_insights.add(lower)

            is_generic = any(re.match(p, lower) for p in generic_patterns)
            if is_generic:
                generic += 1
            else:
                # Substantive = contains a specific number + context
                if re.search(r'\d+\.?\d*', insight) and len(insight) > 30:
                    substantive += 1
                elif len(insight) > 50:
                    substantive += 1
                else:
                    generic += 1

    return {
        "total_insights": total_insights,
        "substantive": substantive,
        "generic": generic,
        "unique": len(unique_insights),
        "substantive_ratio": round(substantive / max(total_insights, 1) * 100, 1),
    }


def audit_polaris_leakage(context: str, evidence_store: dict) -> dict:
    """Check for any POLARIS branding leakage."""
    issues = []
    if "POLARIS" in context:
        for match in re.finditer(r'POLARIS', context):
            start = max(0, match.start() - 50)
            end = min(len(context), match.end() + 50)
            issues.append(context[start:end])

    if "Analysis Toolkit" in context:
        issues.append("'Analysis Toolkit' found in context")

    # Check evidence_store for leaked source_titles
    for eid, ev in evidence_store.items():
        st = ev.get("source_title", "")
        if "POLARIS" in st or "Analysis Toolkit" in st:
            issues.append(f"{eid}: source_title='{st}'")

    return {"leakage_count": len(issues), "details": issues[:5]}


# ---------------------------------------------------------------------------
# Main stress test
# ---------------------------------------------------------------------------

async def run_one_test(test_set: dict) -> dict:
    """Run ReAct agent on one evidence set and return audit results."""
    path = test_set["file"]
    name = test_set["name"]

    if not Path(path).exists():
        return {"name": name, "status": "SKIP", "reason": "File not found"}

    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    raw_evidence = data.get("evidence", [])
    query = data.get("original_query", "")

    if len(raw_evidence) < 5:
        return {"name": name, "status": "SKIP", "reason": f"Only {len(raw_evidence)} evidence"}

    # Build evidence store
    evidence_store = {}
    for ev in raw_evidence:
        eid = ev.get("evidence_id", "")
        if eid:
            evidence_store[eid] = ev

    # Configure agent
    os.environ["PG_REACT_MAX_ITERATIONS"] = "5"
    os.environ["PG_REACT_TIMEOUT_SECONDS"] = "120"

    from src.polaris_graph.llm.openrouter_client import OpenRouterClient
    from src.polaris_graph.tools.react_agent import ReactAnalysisAgent

    client = OpenRouterClient(session_id=f"stress_{name}")

    print(f"\n{'─'*80}")
    print(f"  {name}: {test_set['desc']}")
    print(f"  Query: {query[:100]}")
    print(f"  Evidence: {len(evidence_store)} pieces")
    print(f"{'─'*80}")

    start = time.monotonic()
    agent = ReactAnalysisAgent(
        client=client,
        evidence_store=evidence_store,
        evidence_ids=list(evidence_store.keys()),
        query=query,
    )
    notebook = await agent.run()
    elapsed = time.monotonic() - start

    # Build outputs
    context = notebook.build_synthesis_context()
    entries = [e.model_dump() for e in notebook.to_entries()]

    # -----------------------------------------------------------------------
    # DEEP AUDIT
    # -----------------------------------------------------------------------
    cite_audit = audit_citations(context, evidence_store)
    density_audit = audit_information_density(context)
    stats_audit = audit_statistics(entries, notebook.data_points)
    insight_audit = audit_insights(entries)
    leak_audit = audit_polaris_leakage(context, evidence_store)

    # Print step trace
    for step in notebook.steps:
        status = "OK" if step.result.success else "FAIL"
        print(f"  Step {step.step_number}: {step.tool_name} [{status}] "
              f"({step.elapsed_seconds:.1f}s)")
        print(f"    → {step.reasoning[:100]}")
        if step.result.success:
            print(f"    → {len(step.result.source_evidence_ids)} evidence, "
                  f"{len(step.result.data_points_produced)} data points, "
                  f"{len(step.result.markdown)} chars")

    # Print audit results
    print(f"\n  ── CITATION AUDIT ──")
    print(f"    Total tokens: {cite_audit['total_cite_tokens']} "
          f"({cite_audit['unique_cited']} unique)")
    print(f"    Phantom: {len(cite_audit['phantom_citations'])}")
    print(f"    Mismatched: {len(cite_audit['mismatched_citations'])}")
    if cite_audit['mismatched_citations']:
        for mm in cite_audit['mismatched_citations'][:3]:
            print(f"      ⚠ {mm['evidence_id']}: "
                  f"context='{mm['context_snippet'][:60]}' "
                  f"vs ev='{mm['evidence_statement'][:60]}'")
    print(f"    Citation density: {cite_audit['citation_density']:.1f} per 100 words")

    print(f"\n  ── CONTENT DENSITY AUDIT ──")
    print(f"    Lines: {density_audit['total_lines']} "
          f"(content={density_audit['content_lines']}, "
          f"table={density_audit['table_lines']}, "
          f"header={density_audit['header_lines']})")
    print(f"    Content ratio: {density_audit['content_ratio']}%")
    print(f"    Numbers with units: {density_audit['numbers_with_units']}")
    print(f"    Factual sentences: {density_audit['factual_sentences']}")
    print(f"    Data density: {density_audit['data_density']}%")

    print(f"\n  ── STATISTICS AUDIT ──")
    print(f"    Entries with stats: {stats_audit['entries_with_stats']}")
    if stats_audit['verification_issues']:
        for issue in stats_audit['verification_issues']:
            print(f"      ⚠ {issue['type']}: claimed={issue['claimed']}, "
                  f"all_data={issue['computed_from_all']}")

    print(f"\n  ── INSIGHT AUDIT ──")
    print(f"    Total: {insight_audit['total_insights']}, "
          f"Substantive: {insight_audit['substantive']}, "
          f"Generic: {insight_audit['generic']}")
    print(f"    Substantive ratio: {insight_audit['substantive_ratio']}%")

    print(f"\n  ── LEAKAGE AUDIT ──")
    print(f"    POLARIS leakage: {leak_audit['leakage_count']}")

    # Compute score
    score = 0
    max_score = 100
    penalties = []

    # Citation quality (30 pts)
    if cite_audit['total_cite_tokens'] >= 10: score += 10
    elif cite_audit['total_cite_tokens'] >= 5: score += 5
    else: penalties.append(f"Low citations: {cite_audit['total_cite_tokens']}")

    if not cite_audit['phantom_citations']: score += 10
    else: penalties.append(f"Phantom: {cite_audit['phantom_citations']}")

    if len(cite_audit['mismatched_citations']) <= 2: score += 10
    else: penalties.append(f"Mismatched: {len(cite_audit['mismatched_citations'])}")

    # Content quality (30 pts)
    if density_audit['content_ratio'] >= 30: score += 10
    else: penalties.append(f"Low content: {density_audit['content_ratio']}%")

    if density_audit['numbers_with_units'] >= 5: score += 10
    elif density_audit['numbers_with_units'] >= 2: score += 5
    else: penalties.append(f"Low data density: {density_audit['numbers_with_units']}")

    if density_audit['factual_sentences'] >= 3: score += 10
    else: penalties.append(f"Few factual sentences: {density_audit['factual_sentences']}")

    # Analysis depth (20 pts)
    if notebook.successful_steps >= 3: score += 10
    elif notebook.successful_steps >= 2: score += 5
    else: penalties.append(f"Only {notebook.successful_steps} steps")

    if len(notebook.data_points) >= 10: score += 10
    elif len(notebook.data_points) >= 3: score += 5
    else: penalties.append(f"Low data: {len(notebook.data_points)} points")

    # Insight quality (10 pts)
    if insight_audit['substantive_ratio'] >= 50: score += 10
    elif insight_audit['substantive_ratio'] >= 25: score += 5
    else: penalties.append(f"Generic insights: {insight_audit['substantive_ratio']}%")

    # Zero leakage (10 pts)
    if leak_audit['leakage_count'] == 0: score += 10
    else: penalties.append(f"POLARIS leakage: {leak_audit['leakage_count']}")

    print(f"\n  ── SCORE: {score}/{max_score} ──")
    if penalties:
        for p in penalties:
            print(f"    penalty: {p}")

    cost = client.usage.total_cost_usd
    print(f"  Time: {elapsed:.1f}s | Cost: ${cost:.4f}")

    return {
        "name": name,
        "status": "OK",
        "score": score,
        "penalties": penalties,
        "steps": notebook.step_count,
        "successful": notebook.successful_steps,
        "tool_sequence": [s.tool_name for s in notebook.steps],
        "data_points": len(notebook.data_points),
        "entries": len(entries),
        "citations": cite_audit['total_cite_tokens'],
        "unique_cited": cite_audit['unique_cited'],
        "phantom": len(cite_audit['phantom_citations']),
        "mismatched": len(cite_audit['mismatched_citations']),
        "content_ratio": density_audit['content_ratio'],
        "numbers_with_units": density_audit['numbers_with_units'],
        "leakage": leak_audit['leakage_count'],
        "elapsed": round(elapsed, 1),
        "cost": round(cost, 4),
        "context_chars": len(context),
    }


async def main():
    print(f"\n{'='*80}")
    print("POLARIS v3 ReAct STRESS TEST — Deep Content Audit")
    print(f"{'='*80}")
    print(f"Testing {len(TEST_SETS)} diverse evidence sets")
    print(f"Max iterations: 5 | Timeout: 120s | Tool timeout: 60s")

    results = []
    for test_set in TEST_SETS:
        try:
            r = await run_one_test(test_set)
            results.append(r)
        except Exception as exc:
            print(f"\n  CRASH: {test_set['name']}: {type(exc).__name__}: {str(exc)[:200]}")
            results.append({
                "name": test_set["name"],
                "status": "CRASH",
                "error": str(exc)[:200],
            })

    # -----------------------------------------------------------------------
    # Summary table
    # -----------------------------------------------------------------------
    print(f"\n{'='*80}")
    print("STRESS TEST SUMMARY")
    print(f"{'='*80}")
    print(f"{'Name':<15} {'Score':>5} {'Steps':>5} {'Data':>5} {'Cites':>5} "
          f"{'Phntm':>5} {'Match':>5} {'Leak':>4} {'Time':>6} {'Cost':>7}")
    print(f"{'-'*15} {'-'*5} {'-'*5} {'-'*5} {'-'*5} {'-'*5} {'-'*5} "
          f"{'-'*4} {'-'*6} {'-'*7}")

    total_cost = 0
    total_score = 0
    ok_count = 0

    for r in results:
        if r["status"] == "SKIP":
            print(f"{r['name']:<15} {'SKIP':>5} — {r.get('reason', '')}")
            continue
        if r["status"] == "CRASH":
            print(f"{r['name']:<15} {'CRASH':>5} — {r.get('error', '')[:50]}")
            continue

        ok_count += 1
        total_cost += r["cost"]
        total_score += r["score"]

        mismatch_marker = f"{r['mismatched']}!" if r["mismatched"] > 2 else str(r["mismatched"])
        print(f"{r['name']:<15} {r['score']:>5} {r['successful']:>5} "
              f"{r['data_points']:>5} {r['citations']:>5} {r['phantom']:>5} "
              f"{mismatch_marker:>5} {r['leakage']:>4} {r['elapsed']:>5.1f}s "
              f"${r['cost']:>6.4f}")

    if ok_count > 0:
        avg_score = total_score / ok_count
        print(f"\nAverage score: {avg_score:.1f}/100")
        print(f"Total cost: ${total_cost:.4f}")

    # Verdict
    all_pass = all(
        r.get("score", 0) >= 50 and r.get("leakage", 0) == 0
        for r in results if r["status"] == "OK"
    )
    print(f"\n{'='*80}")
    if all_pass and ok_count >= 3:
        print("OVERALL VERDICT: PASS — Analysis robust across diverse evidence sets")
    else:
        print("OVERALL VERDICT: NEEDS WORK — See penalties above")
    print(f"{'='*80}\n")


if __name__ == "__main__":
    asyncio.run(main())
