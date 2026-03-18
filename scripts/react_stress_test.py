"""Stress test: ReAct analysis on 5 diverse evidence sets with DRACO-inspired audit.

Loads REAL evidence from previous pipeline runs, runs the ReAct agent,
then audits every line of output using a 4-axis evaluation inspired by
Perplexity's DRACO benchmark:

Axis 1: Factual Accuracy (40 pts) — numerical claim verification
Axis 2: Breadth/Depth (20 pts) — cross-source insights, trade-offs
Axis 3: Citation Quality (25 pts) — count, validity, semantic match
Axis 4: Content Quality (15 pts) — density, units, zero leakage

Plus line-by-line verification: full interpretation output printed,
5 random citations spot-checked per run against source evidence.

Usage:
    python -u -m scripts.react_stress_test
"""

import asyncio
import json
import math
import os
import random
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
    """Audit every [CITE:ev_xxx] token in the context.

    Uses a LINE-level context window for list items (not 200-char window)
    to avoid cross-item bleed. A citation on a list item about "PFOS 34 ng/L"
    should be checked against THAT line, not the header 3 lines above.
    """
    cite_pattern = re.compile(r'\[CITE:(ev_[a-f0-9]+)\]')
    all_cites = cite_pattern.findall(context)
    unique_cites = set(all_cites)

    phantom = [c for c in unique_cites if c not in evidence_store]
    valid = [c for c in unique_cites if c in evidence_store]

    # Check if cited evidence is relevant to its immediate line
    mismatched = []
    lines = context.split("\n")
    for line_num, line in enumerate(lines):
        for match in cite_pattern.finditer(line):
            eid = match.group(1)
            if eid not in evidence_store:
                continue

            # Use the LINE containing the citation as context
            # Plus the line above for additional context
            ctx_lines = []
            if line_num > 0:
                ctx_lines.append(lines[line_num - 1])
            ctx_lines.append(line)
            surrounding = " ".join(ctx_lines).lower()

            # Get the evidence statement
            ev_stmt = evidence_store[eid].get("statement", "").lower()

            # Extract content words (4+ chars, skip common words)
            surr_words = set(re.findall(r'[a-z]{4,}', surrounding))
            ev_words = set(re.findall(r'[a-z]{4,}', ev_stmt))
            overlap = surr_words & ev_words

            # Also check number overlap (shared numeric values)
            surr_nums = set(re.findall(r'\d+\.?\d*', surrounding))
            ev_nums = set(re.findall(r'\d+\.?\d*', ev_stmt))
            num_overlap = surr_nums & ev_nums

            # Pass if: 2+ word overlap OR 1+ number overlap OR
            # citation is on a table/summary line (structural citation)
            is_structural = (
                line.strip().startswith("|")
                or line.strip().startswith("**Summary")
                or line.strip().startswith("**Overall")
                or "across" in line.lower()
            )

            if len(overlap) < 2 and len(num_overlap) == 0 and not is_structural:
                mismatched.append({
                    "evidence_id": eid,
                    "context_line": line.strip()[:100],
                    "evidence_statement": ev_stmt[:100],
                    "word_overlap": len(overlap),
                    "number_overlap": len(num_overlap),
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
    """Verify statistical claims against raw data using same unit grouping."""
    issues = []
    verified = 0

    for entry_dict in entries:
        stats = entry_dict.get("statistics", {})
        if not stats or not stats.get("mean"):
            continue

        claimed_mean = stats.get("mean")
        claimed_n = stats.get("n")

        if not data_points or not claimed_n:
            continue

        # Group by unit (same logic as _wrap_statistical_summary)
        by_unit: dict[str, list] = {}
        for dp in data_points:
            unit = dp.get("unit", "unknown") or "unknown"
            try:
                v = float(str(dp.get("value", "")).replace(",", ""))
                by_unit.setdefault(unit, []).append(v)
            except (ValueError, TypeError):
                pass

        if not by_unit:
            continue

        # Use the largest unit group (same as the tool does)
        primary_unit = max(by_unit, key=lambda u: len(by_unit[u]))
        primary_values = by_unit[primary_unit]

        if not primary_values:
            continue

        actual_mean = sum(primary_values) / len(primary_values)

        # Verify: claimed mean should match unit-filtered mean
        if claimed_mean != 0:
            pct_diff = abs(actual_mean - claimed_mean) / abs(claimed_mean)
            if pct_diff > 0.01:  # >1% difference
                issues.append({
                    "type": "mean_mismatch",
                    "claimed": round(claimed_mean, 4),
                    "computed_unit_filtered": round(actual_mean, 4),
                    "unit": primary_unit,
                    "n_claimed": claimed_n,
                    "n_actual": len(primary_values),
                    "pct_diff": round(pct_diff * 100, 1),
                })
            else:
                verified += 1
        else:
            verified += 1

    return {
        "entries_with_stats": sum(1 for e in entries if e.get("statistics", {}).get("mean")),
        "verified": verified,
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


def audit_factual_accuracy(context: str, evidence_store: dict) -> dict:
    """DRACO Axis 1: Verify each numerical claim against cited evidence.

    For each [CITE:ev_xxx], extract the number near it and check:
    1. Does the number appear in the cited evidence statement?
    2. Does the claim category match the evidence category?
    """
    cite_pattern = re.compile(r'([^.!?\n]{10,120})\[CITE:(ev_[a-f0-9]+)\]')

    total_checked = 0
    number_verified = 0
    category_mismatches = []

    cost_words = {"cost", "price", "expensive", "affordable", "budget",
                  "spending", "billion", "million", "usd", "$"}
    removal_words = {"removal", "removed", "efficiency", "reduction",
                     "achieved", "treatment", "filtration", "adsorption"}
    market_words = {"market", "share", "cagr", "growth", "valued",
                    "projected", "revenue"}

    for match in cite_pattern.finditer(context):
        claim_text = match.group(1).strip()
        ev_id = match.group(2)

        if ev_id not in evidence_store:
            continue

        nums = re.findall(r'(\d+\.?\d*)', claim_text)
        if not nums:
            continue

        total_checked += 1
        ev_stmt = evidence_store[ev_id].get("statement", "").lower()
        key_num = nums[-1]

        # Check 1: Number presence
        if key_num in ev_stmt:
            number_verified += 1

        # Check 2: Category match
        claim_lower = claim_text.lower()
        claim_cat = (
            "cost" if any(w in claim_lower for w in cost_words) else
            "removal" if any(w in claim_lower for w in removal_words) else
            "market" if any(w in claim_lower for w in market_words) else
            "other"
        )
        ev_cat = (
            "cost" if any(w in ev_stmt for w in cost_words) else
            "removal" if any(w in ev_stmt for w in removal_words) else
            "market" if any(w in ev_stmt for w in market_words) else
            "other"
        )

        if claim_cat != "other" and ev_cat != "other" and claim_cat != ev_cat:
            category_mismatches.append({
                "claim": claim_text[:80],
                "ev_id": ev_id,
                "claim_category": claim_cat,
                "ev_category": ev_cat,
                "ev_statement": evidence_store[ev_id].get("statement", "")[:80],
            })

    return {
        "total_checked": total_checked,
        "number_verified": number_verified,
        "verification_rate": round(
            number_verified / max(total_checked, 1) * 100, 1,
        ),
        "category_mismatches": category_mismatches,
    }


def audit_breadth_depth(context: str) -> dict:
    """DRACO Axis 2: Measure breadth and depth of analysis.

    Counts unique technologies/methods, cross-source insights,
    and trade-off identifications.
    """
    # Count unique technologies/methods (common domain-specific terms)
    tech_patterns = re.findall(
        r'(?:Reverse Osmosis|Granular Activated Carbon|Ion Exchange|'
        r'Biochar|Nanofiltration|Membrane|Adsorption|Coagulation|'
        r'Activated Alumina|Electrocoagulation|UV|Ozone|GAC|RO|NF|UF|MF|'
        r'PFAS|PFOS|PFOA|DVS|PEI|EDI|Polymer|Ceramic|Activated Carbon|'
        r'Sand Filtration|Flocculation|Precipitation|Distillation|'
        r'[A-Z][a-z]+ [A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)',
        context,
    )
    unique_techs = len(set(t.strip() for t in tech_patterns))

    # Count cross-source insights (sentences citing 2+ different sources)
    cross_source = 0
    for sentence in re.split(r'[.!?]\s+', context):
        cites = set(re.findall(r'\[CITE:(ev_[a-f0-9]+)\]', sentence))
        if len(cites) >= 2:
            cross_source += 1

    # Count trade-off identifications
    tradeoff_patterns = [
        r'(?:but|however|although|while|whereas|despite|on the other hand)',
        r'(?:trade-?off|downside|limitation|disadvantage|drawback)',
        r'(?:more expensive|less effective|higher cost|lower efficiency)',
        r'(?:better for|worse for|preferred when|suitable for)',
    ]
    tradeoffs = sum(
        len(re.findall(p, context, re.IGNORECASE))
        for p in tradeoff_patterns
    )

    return {
        "unique_technologies": unique_techs,
        "cross_source_insights": cross_source,
        "tradeoff_identifications": min(tradeoffs, 20),
    }


def spot_check_citations(
    context: str, evidence_store: dict, n: int = 5,
) -> list:
    """Randomly spot-check N citations against source evidence.

    Returns list of dicts with claim text, evidence text, and match assessment.
    """
    pattern = re.compile(r'([^.!?\n]{10,150})\[CITE:(ev_[a-f0-9]+)\]')
    matches = list(pattern.finditer(context))

    if not matches:
        return []

    sample = random.sample(matches, min(n, len(matches)))

    checks = []
    for match in sample:
        claim = match.group(1).strip()
        ev_id = match.group(2)
        ev = evidence_store.get(ev_id, {})
        ev_stmt = ev.get("statement", "N/A")

        claim_words = set(re.findall(r'[a-z]{4,}', claim.lower()))
        ev_words = set(re.findall(r'[a-z]{4,}', ev_stmt.lower()))
        overlap = claim_words & ev_words

        claim_nums = set(re.findall(r'\d+\.?\d*', claim))
        ev_nums = set(re.findall(r'\d+\.?\d*', ev_stmt))
        num_overlap = claim_nums & ev_nums

        checks.append({
            "claim": claim[:100],
            "ev_id": ev_id,
            "ev_statement": ev_stmt[:100],
            "word_overlap": len(overlap),
            "number_overlap": len(num_overlap),
            "likely_match": len(overlap) >= 2 or len(num_overlap) >= 1,
        })

    return checks


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
    # DEEP AUDIT (DRACO-Inspired 4-Axis Evaluation)
    # -----------------------------------------------------------------------
    cite_audit = audit_citations(context, evidence_store)
    density_audit = audit_information_density(context)
    stats_audit = audit_statistics(entries, notebook.data_points)
    insight_audit = audit_insights(entries)
    leak_audit = audit_polaris_leakage(context, evidence_store)
    factual_audit = audit_factual_accuracy(context, evidence_store)
    breadth_audit = audit_breadth_depth(context)
    spot_checks = spot_check_citations(context, evidence_store, n=5)

    # Print step trace
    for step in notebook.steps:
        status = "OK" if step.result.success else "FAIL"
        print(f"  Step {step.step_number}: {step.tool_name} [{status}] "
              f"({step.elapsed_seconds:.1f}s)")
        print(f"    -> {step.reasoning[:100]}")
        if step.result.success:
            print(f"    -> {len(step.result.source_evidence_ids)} evidence, "
                  f"{len(step.result.data_points_produced)} data points, "
                  f"{len(step.result.markdown)} chars")

    # Print full interpretation (Steps 13-15: non-optional)
    interp_steps = [
        s for s in notebook.steps
        if s.tool_name == "interpret_results" and s.result.success
    ]
    if interp_steps:
        print(f"\n  ── FULL INTERPRETATION OUTPUT ──")
        interp_text = interp_steps[0].result.markdown
        for line in interp_text.split("\n"):
            print(f"    | {line}")
        print(f"    [{len(interp_text)} chars]")

    # Print DRACO Axis 1: Factual Accuracy
    print(f"\n  ── AXIS 1: FACTUAL ACCURACY ──")
    print(f"    Claims checked: {factual_audit['total_checked']}")
    print(f"    Numbers verified: {factual_audit['number_verified']}")
    print(f"    Verification rate: {factual_audit['verification_rate']}%")
    print(f"    Category mismatches: {len(factual_audit['category_mismatches'])}")
    for mm in factual_audit['category_mismatches'][:3]:
        print(f"      X {mm['ev_id']}: claim={mm['claim_category']}, "
              f"ev={mm['ev_category']} — \"{mm['claim'][:50]}\"")

    # Print DRACO Axis 2: Breadth/Depth
    print(f"\n  ── AXIS 2: BREADTH & DEPTH ──")
    print(f"    Unique technologies: {breadth_audit['unique_technologies']}")
    print(f"    Cross-source insights: {breadth_audit['cross_source_insights']}")
    print(f"    Trade-off identifications: {breadth_audit['tradeoff_identifications']}")

    # Print DRACO Axis 3: Citation Quality
    print(f"\n  ── AXIS 3: CITATION QUALITY ──")
    print(f"    Total tokens: {cite_audit['total_cite_tokens']} "
          f"({cite_audit['unique_cited']} unique)")
    print(f"    Phantom: {len(cite_audit['phantom_citations'])}")
    print(f"    Mismatched: {len(cite_audit['mismatched_citations'])}")
    if cite_audit['mismatched_citations']:
        for mm in cite_audit['mismatched_citations'][:3]:
            print(f"      X {mm['evidence_id']}: "
                  f"line='{mm.get('context_line', mm.get('context_snippet', ''))[:60]}' "
                  f"vs ev='{mm['evidence_statement'][:60]}'")

    # Print DRACO Axis 4: Content Quality
    print(f"\n  ── AXIS 4: CONTENT QUALITY ──")
    print(f"    Content ratio: {density_audit['content_ratio']}%")
    print(f"    Numbers with units: {density_audit['numbers_with_units']}")
    print(f"    POLARIS leakage: {leak_audit['leakage_count']}")

    # Print spot-check results (5 random citations)
    print(f"\n  ── CITATION SPOT-CHECK ({len(spot_checks)} samples) ──")
    for i, sc in enumerate(spot_checks, 1):
        verdict = "PASS" if sc['likely_match'] else "FAIL"
        print(f"    {i}. [{verdict}] {sc['ev_id']}")
        print(f"       Claim: \"{sc['claim'][:80]}\"")
        print(f"       Evidence: \"{sc['ev_statement'][:80]}\"")
        print(f"       Overlap: {sc['word_overlap']} words, "
              f"{sc['number_overlap']} numbers")

    # Statistics audit (supplementary)
    if stats_audit['verification_issues']:
        print(f"\n  ── STATISTICS ISSUES ──")
        for issue in stats_audit['verification_issues']:
            print(f"      X {issue['type']}: claimed={issue['claimed']}, "
                  f"actual={issue['computed_unit_filtered']}")

    # -----------------------------------------------------------------------
    # DRACO-Inspired 4-Axis Score
    # -----------------------------------------------------------------------
    score = 0
    max_score = 100
    penalties = []

    # Axis 1: Factual Accuracy (40 pts)
    vr = factual_audit['verification_rate']
    if vr >= 80:
        score += 25
    elif vr >= 50:
        score += int(25 * vr / 80)
    else:
        penalties.append(f"Low verification: {vr}%")
        score += max(0, int(25 * vr / 80))

    if not factual_audit['category_mismatches']:
        score += 15
    elif len(factual_audit['category_mismatches']) <= 1:
        score += 8
        penalties.append(
            f"Category mismatch: {len(factual_audit['category_mismatches'])}"
        )
    else:
        penalties.append(
            f"Category mismatches: {len(factual_audit['category_mismatches'])}"
        )

    # Axis 2: Breadth/Depth (20 pts)
    if breadth_audit['unique_technologies'] >= 3:
        score += 10
    elif breadth_audit['unique_technologies'] >= 1:
        score += 5
    else:
        penalties.append("No technologies identified")

    depth_score = (
        breadth_audit['cross_source_insights']
        + breadth_audit['tradeoff_identifications']
    )
    if depth_score >= 3:
        score += 10
    elif depth_score >= 1:
        score += 5
    else:
        penalties.append(f"Low depth: {depth_score} insights+tradeoffs")

    # Axis 3: Citation Quality (25 pts)
    if cite_audit['total_cite_tokens'] >= 10:
        score += 10
    elif cite_audit['total_cite_tokens'] >= 5:
        score += 5
    else:
        penalties.append(f"Low citations: {cite_audit['total_cite_tokens']}")

    if not cite_audit['phantom_citations']:
        score += 10
    else:
        penalties.append(f"Phantom: {cite_audit['phantom_citations']}")

    if len(cite_audit['mismatched_citations']) <= 2:
        score += 5
    else:
        penalties.append(
            f"Mismatched: {len(cite_audit['mismatched_citations'])}"
        )

    # Axis 4: Content Quality (15 pts)
    if density_audit['content_ratio'] >= 30:
        score += 5
    else:
        penalties.append(f"Low content: {density_audit['content_ratio']}%")

    if density_audit['numbers_with_units'] >= 5:
        score += 5
    elif density_audit['numbers_with_units'] >= 2:
        score += 3
    else:
        penalties.append(
            f"Low data density: {density_audit['numbers_with_units']}"
        )

    if leak_audit['leakage_count'] == 0:
        score += 5
    else:
        penalties.append(f"POLARIS leakage: {leak_audit['leakage_count']}")

    print(f"\n  ── SCORE: {score}/{max_score} ──")
    print(f"    Axis 1 (Factual):  "
          f"{min(40, score)}/40")
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
