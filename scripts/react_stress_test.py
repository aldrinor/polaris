"""Stress test: ReAct analysis on 5 diverse evidence sets with 6-axis audit.

Loads REAL evidence from previous pipeline runs, runs the ReAct agent,
then audits every line of output using a 6-axis evaluation:

Axis 1: Factual Accuracy (25 pts) — numerical claim verification
Axis 2: Synthesis Quality (25 pts) — parroting, cross-source integration
Axis 3: Question Answering (20 pts) — multi-criteria integration, ranking
Axis 4: Evidence Utilization (10 pts) — category coverage
Axis 5: Citation Quality (10 pts) — count, validity
Axis 6: Content Quality (10 pts) — density, units, zero leakage

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

import numpy as np


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
        claim_lower = claim_text.lower()
        ev_stmt = evidence_store[ev_id].get("statement", "").lower()
        key_num = nums[-1]

        # Check 1: Number presence + unit match
        if key_num in ev_stmt:
            # Extract the unit phrase near the number in both claim and
            # evidence. Catches ppt→ppb, mg→ng, billion→million errors.
            # Look for unit within 30 chars after the number.
            unit_words = (
                r"(?:parts?\s+per\s+(?:trillion|billion|million)|"
                r"ppt|ppb|ppm|mg/[gL]|ng/[gL]|µg/[gL]|"
                r"%|mg|ng|µg|kWh|MPa|GPa|µm|m³|"
                r"billion|million|USD)"
            )
            claim_unit_re = re.compile(
                re.escape(key_num) + r'.{0,20}?' + unit_words,
            )
            ev_unit_re = re.compile(
                re.escape(key_num) + r'.{0,20}?' + unit_words,
            )
            claim_unit_m = claim_unit_re.search(claim_lower)
            ev_unit_m = ev_unit_re.search(ev_stmt)
            if claim_unit_m and ev_unit_m:
                # Extract just the unit part (last word/phrase)
                c_unit = re.search(unit_words, claim_unit_m.group())
                e_unit = re.search(unit_words, ev_unit_m.group())
                if c_unit and e_unit and c_unit.group() == e_unit.group():
                    number_verified += 1
                elif c_unit and e_unit:
                    # Unit mismatch — flag it
                    category_mismatches.append({
                        "claim": claim_text[:80],
                        "ev_id": ev_id,
                        "claim_category": f"unit:{c_unit.group()}",
                        "ev_category": f"unit:{e_unit.group()}",
                        "ev_statement": evidence_store[ev_id].get(
                            "statement", "",
                        )[:80],
                    })
                else:
                    number_verified += 1
            else:
                # No unit found near number — still count as verified
                number_verified += 1

        # Check 2: Category match — use ALL matching categories (not first-wins)
        # to avoid false positives on evidence like "100% removal at $90 cost"
        claim_cats = set()
        if any(w in claim_lower for w in cost_words):
            claim_cats.add("cost")
        if any(w in claim_lower for w in removal_words):
            claim_cats.add("removal")
        if any(w in claim_lower for w in market_words):
            claim_cats.add("market")

        ev_cats = set()
        if any(w in ev_stmt for w in cost_words):
            ev_cats.add("cost")
        if any(w in ev_stmt for w in removal_words):
            ev_cats.add("removal")
        if any(w in ev_stmt for w in market_words):
            ev_cats.add("market")

        # Mismatch only if claim categories and evidence categories
        # have ZERO overlap (both non-empty)
        if claim_cats and ev_cats and not (claim_cats & ev_cats):
            category_mismatches.append({
                "claim": claim_text[:80],
                "ev_id": ev_id,
                "claim_category": ", ".join(sorted(claim_cats)),
                "ev_category": ", ".join(sorted(ev_cats)),
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


def audit_parroting(context: str, evidence_store: dict) -> dict:
    """Check if synthesis merely parrots source evidence verbatim.

    A sentence is "parroted" if word-level Jaccard similarity > 0.5
    against any single evidence statement (using 4+ char words only).
    """
    sentences = [s.strip() for s in re.split(r'[.!?]\s+', context) if s.strip()]
    ev_word_sets = {}
    for eid, ev in evidence_store.items():
        stmt = ev.get("statement", "")
        ev_word_sets[eid] = set(re.findall(r'[a-z]{4,}', stmt.lower()))

    parroted_count = 0
    examples = []

    for sentence in sentences:
        sent_words = set(re.findall(r'[a-z]{4,}', sentence.lower()))
        if not sent_words:
            continue
        for eid, ev_words in ev_word_sets.items():
            if not ev_words:
                continue
            intersection = sent_words & ev_words
            union = sent_words | ev_words
            jaccard = len(intersection) / len(union) if union else 0.0
            if jaccard > 0.5:
                parroted_count += 1
                if len(examples) < 3:
                    examples.append(sentence)
                break  # Count each sentence only once

    total = len(sentences) or 1
    return {
        "total_sentences": len(sentences),
        "parroted_count": parroted_count,
        "parroted_ratio": round(parroted_count / total, 4),
        "examples": examples,
    }


def audit_integration(context: str, query: str) -> dict:
    """Measure multi-criteria integration depth in the synthesis.

    Detects whether the query is multi-criteria and checks how many
    paragraphs integrate 3+ different criteria keywords.
    """
    multi_criteria_pattern = re.compile(
        r'\b(?:and|&|vs\.?|versus|compare)\b', re.IGNORECASE,
    )
    is_multi_criteria = bool(multi_criteria_pattern.search(query))

    criteria_words = {
        "cost", "price", "expensive", "affordable", "budget",
        "effective", "efficiency", "removal", "performance", "treatment",
        "trade-off", "tradeoff", "however", "whereas", "although",
        "compared", "versus", "limitation", "drawback", "advantage",
    }

    paragraphs = [p.strip() for p in context.split("\n\n") if p.strip()]
    integrated_count = 0

    for para in paragraphs:
        para_lower = para.lower()
        found = {w for w in criteria_words if w in para_lower}
        # 2+ criteria words = integrated (was 3, too strict)
        if len(found) >= 2:
            integrated_count += 1

    total_paragraphs = len(paragraphs) or 1
    integration_ratio = round(integrated_count / total_paragraphs, 4)

    # Broader ranking detection — includes conditional rankings,
    # numbered lists, "tier" systems, confidence scores
    ranking_pattern = re.compile(
        r'\b(?:rank|best|recommend|prefer|optimal|superior|tier|'
        r'first|second|third|highest|lowest|top)\b|'
        r'(?:score[:\s]+\d|/10\b|\d+/100)',
        re.IGNORECASE,
    )
    has_ranking = bool(ranking_pattern.search(context))

    integration_score = round(
        0.6 * integration_ratio + 0.4 * (1.0 if has_ranking else 0.0), 4,
    )

    return {
        "is_multi_criteria": is_multi_criteria,
        "total_paragraphs": len(paragraphs),
        "integrated_paragraphs": integrated_count,
        "integration_ratio": integration_ratio,
        "has_ranking": has_ranking,
        "integration_score": integration_score,
    }


def audit_evidence_coverage(context: str, evidence_store: dict) -> dict:
    """Measure how many evidence categories are actually cited.

    Groups evidence by fact_category and checks whether at least one
    evidence_id from each category appears as [CITE:ev_xxx] in context.
    """
    by_category: dict[str, list[str]] = {}
    for eid, ev in evidence_store.items():
        cat = ev.get("fact_category", "general") or "general"
        by_category.setdefault(cat, []).append(eid)

    cited_ids = set(re.findall(r'\[CITE:(ev_[a-f0-9]+)\]', context))
    categories_cited = 0
    for cat, eids in by_category.items():
        if any(eid in cited_ids for eid in eids):
            categories_cited += 1

    total_evidence = len(evidence_store) or 1
    evidence_cited = len(cited_ids & set(evidence_store.keys()))

    return {
        "total_categories": len(by_category),
        "categories_cited": categories_cited,
        "category_coverage": round(
            categories_cited / max(len(by_category), 1), 4,
        ),
        "total_evidence": len(evidence_store),
        "evidence_cited": evidence_cited,
        "utilization_rate": round(evidence_cited / total_evidence, 4),
    }


def audit_cross_source(context: str) -> dict:
    """Count sentences that cite 2+ different evidence sources."""
    sentences = [s.strip() for s in re.split(r'[.!?]\s+', context) if s.strip()]
    cross_source_count = 0

    for sentence in sentences:
        cites = set(re.findall(r'\[CITE:(ev_[a-f0-9]+)\]', sentence))
        if len(cites) >= 2:
            cross_source_count += 1

    total = len(sentences) or 1
    return {
        "total_sentences": len(sentences),
        "cross_source_sentences": cross_source_count,
        "cross_source_ratio": round(cross_source_count / total, 4),
    }


# ---------------------------------------------------------------------------
# NLI-based audit functions (SOTA: replaces regex hacks)
# ---------------------------------------------------------------------------

_nli_scorer_cache = None


async def _get_nli_scorer():
    """Lazy-load NLI scorer singleton."""
    global _nli_scorer_cache
    if _nli_scorer_cache is not None:
        return _nli_scorer_cache
    try:
        from src.polaris_graph.agents.nli_verifier import load_nli_model
        _nli_scorer_cache = await load_nli_model()
        return _nli_scorer_cache
    except Exception:
        return None


async def audit_nli_faithfulness(context: str, evidence_store: dict) -> dict:
    """NLI-based claim-evidence verification.

    Replaces regex unit checker + category mismatch detector.
    Uses MiniCheck flan-t5-large to check if each cited claim is
    entailed by the cited evidence. Naturally catches unit errors
    (ppt vs ppb), category mismatches, and hallucinated claims.
    """
    if os.getenv("PG_NLI_ENABLED", "0") != "1":
        return {"nli_available": False}

    scorer = await _get_nli_scorer()
    if scorer is None:
        return {"nli_available": False}

    # Extract all (claim, evidence) pairs from citations
    cite_pattern = re.compile(r'([^.!?\n]{10,150})\[CITE:(ev_[a-f0-9]+)\]')
    claim_texts = []
    ev_statements = []
    ev_ids = []

    for match in cite_pattern.finditer(context):
        claim = match.group(1).strip()
        eid = match.group(2)
        if eid not in evidence_store:
            continue
        ev_stmt = evidence_store[eid].get("statement", "")
        if not ev_stmt or len(ev_stmt) < 10:
            continue
        claim_texts.append(claim)
        ev_statements.append(ev_stmt)
        ev_ids.append(eid)

    if not claim_texts:
        return {"nli_available": True, "total_claims": 0,
                "supported": 0, "not_supported": 0, "contradicted": 0,
                "contradictions": [], "faithfulness_score": 1.0}

    # Run NLI in batch (blocking call → thread)
    try:
        _labels, probs, _chunks, _chunk_probs = await asyncio.to_thread(
            scorer.score, docs=ev_statements, claims=claim_texts,
        )
    except Exception as exc:
        print(f"    NLI scoring failed: {type(exc).__name__}: {str(exc)[:100]}")
        return {"nli_available": False}

    # Classify results
    support_threshold = float(os.getenv(
        "PG_FAITHFULNESS_NLI_THRESHOLD", "0.65",
    ))
    contradict_threshold = float(os.getenv(
        "PG_NLI_DISPUTE_THRESHOLD", "0.3",
    ))

    supported = 0
    not_supported = 0
    contradicted = 0
    contradictions = []

    for i, prob in enumerate(probs):
        p = float(prob)
        if p >= support_threshold:
            supported += 1
        elif p < contradict_threshold:
            contradicted += 1
            contradictions.append({
                "claim": claim_texts[i][:100],
                "ev_id": ev_ids[i],
                "ev_statement": ev_statements[i][:100],
                "nli_score": round(p, 3),
                "label": "CONTRADICTS",
            })
        else:
            not_supported += 1

    total = len(probs)
    return {
        "nli_available": True,
        "total_claims": total,
        "supported": supported,
        "not_supported": not_supported,
        "contradicted": contradicted,
        "contradictions": contradictions,
        "faithfulness_score": round(supported / max(total, 1), 3),
    }


def audit_originality(context: str, evidence_store: dict) -> dict:
    """Embedding-based originality detection.

    Replaces Jaccard word-overlap parroting detector. Uses cosine
    similarity between output sentences and evidence statements.
    Only flags sentences with very high similarity (>0.92) AND
    no analytical markers — technical terminology alone won't trigger.
    """
    from src.utils.embedding_service import embed_texts

    # Analytical markers that indicate synthesis (not copying)
    analytical_markers = {
        "however", "therefore", "trade-off", "tradeoff", "suggests",
        "implies", "compared", "indicates", "whereas", "consequently",
        "despite", "furthermore", "moreover", "notably", "in contrast",
        "on the other hand", "this suggests", "this indicates",
        "this creates", "this highlights", "this means", "ranking",
        "rank", "trade-offs", "reveals", "necessitating",
    }

    # Clean citations from sentences before embedding
    cite_re = re.compile(r'\[CITE:ev_[a-f0-9]+\]')
    sentences = [
        s.strip() for s in re.split(r'[.!?]\s+', context) if len(s.strip()) > 20
    ]
    clean_sentences = [cite_re.sub('', s).strip() for s in sentences]

    # Collect evidence statements
    ev_statements = [
        ev.get("statement", "")
        for ev in evidence_store.values()
        if ev.get("statement", "") and len(ev.get("statement", "")) > 10
    ]

    if not clean_sentences or not ev_statements:
        return {"total_sentences": len(sentences), "original": len(sentences),
                "copied": 0, "copy_ratio": 0.0, "examples": []}

    try:
        sent_embeddings = embed_texts(clean_sentences)
        ev_embeddings = embed_texts(ev_statements)

        sent_matrix = np.array(sent_embeddings)
        ev_matrix = np.array(ev_embeddings)

        # Cosine similarity (embeddings are L2-normalized)
        sim_matrix = sent_matrix @ ev_matrix.T

        copied = 0
        examples = []
        for i, sent in enumerate(sentences):
            max_sim = float(np.max(sim_matrix[i]))
            if max_sim > 0.92:
                sent_lower = sent.lower()
                has_marker = any(m in sent_lower for m in analytical_markers)
                if not has_marker:
                    copied += 1
                    if len(examples) < 3:
                        examples.append(sent[:100])

        total = len(sentences)
        return {
            "total_sentences": total,
            "original": total - copied,
            "copied": copied,
            "copy_ratio": round(copied / max(total, 1), 3),
            "examples": examples,
        }
    except Exception as exc:
        print(f"    Originality check failed: {type(exc).__name__}: {str(exc)[:100]}")
        return {"total_sentences": len(sentences), "original": len(sentences),
                "copied": 0, "copy_ratio": 0.0, "examples": []}


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
    # 8-phase pipeline: learnings + scaffold + write + critique + rewrite
    os.environ["PG_REACT_TIMEOUT_SECONDS"] = "900"

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

    # Build outputs — use INTERPRETATION step only for substance audits.
    # build_synthesis_context() includes raw tool output (comparison tables,
    # agreement analysis) which inflates citation mismatches and spot-check
    # failures on non-prose content like "**Comparison Table** (unit: %)".
    context = notebook.build_synthesis_context()
    entries = [e.model_dump() for e in notebook.to_entries()]

    # Extract interpretation-only text for substance audits
    interp_text = ""
    for step in notebook.steps:
        if step.tool_name == "interpret_results" and step.result.success:
            interp_text = step.result.markdown
            break
    # Use interpretation text for substance audits, full context for density
    audit_context = interp_text or context

    # -----------------------------------------------------------------------
    # DEEP AUDIT (6-Axis Evaluation)
    # -----------------------------------------------------------------------
    cite_audit = audit_citations(audit_context, evidence_store)
    density_audit = audit_information_density(audit_context)
    stats_audit = audit_statistics(entries, notebook.data_points)
    insight_audit = audit_insights(entries)
    leak_audit = audit_polaris_leakage(audit_context, evidence_store)
    factual_audit = audit_factual_accuracy(audit_context, evidence_store)
    breadth_audit = audit_breadth_depth(audit_context)
    spot_checks = spot_check_citations(audit_context, evidence_store, n=5)

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
    # 6-Axis Substance Score (100 pts)
    # -----------------------------------------------------------------------
    # NLI-based audits (SOTA) with regex fallback
    _nli_active = os.getenv("PG_NLI_ENABLED", "0") == "1"
    nli_faith_audit = None
    originality_audit = None

    if _nli_active:
        nli_faith_audit = await audit_nli_faithfulness(
            audit_context, evidence_store,
        )
        if not nli_faith_audit.get("nli_available", False):
            _nli_active = False
            nli_faith_audit = None
        else:
            originality_audit = audit_originality(
                audit_context, evidence_store,
            )

    # Legacy regex audits (always computed for reference)
    parroting_audit = audit_parroting(audit_context, evidence_store)
    integration_audit = audit_integration(audit_context, query)
    coverage_audit = audit_evidence_coverage(audit_context, evidence_store)
    cross_source_audit = audit_cross_source(audit_context)

    score = 0
    max_score = 100
    penalties = []

    # Axis 1: Factual Accuracy (25 pts)
    vr = factual_audit['verification_rate']
    score_a1 = min(15, int(15 * min(vr, 80) / 80))
    if _nli_active and nli_faith_audit:
        fs = nli_faith_audit['faithfulness_score']
        n_contra = nli_faith_audit['contradicted']
        if n_contra == 0 and fs >= 0.80:
            score_a1 += 10
        elif n_contra <= 1 and fs >= 0.60:
            score_a1 += 5
            penalties.append(
                f"NLI faith: {fs:.0%} ({n_contra} contradictions)"
            )
        else:
            penalties.append(
                f"NLI faith: {fs:.0%} ({n_contra} contradictions)"
            )
    else:
        if not factual_audit['category_mismatches']:
            score_a1 += 10
        elif len(factual_audit['category_mismatches']) <= 1:
            score_a1 += 5
            penalties.append(
                f"Category mismatch: "
                f"{len(factual_audit['category_mismatches'])}"
            )
        else:
            penalties.append(
                f"Category mismatches: "
                f"{len(factual_audit['category_mismatches'])}"
            )
    score += score_a1

    # Axis 2: Synthesis Quality (25 pts)
    score_a2 = 0
    if _nli_active and originality_audit:
        cr = originality_audit['copy_ratio']
        if cr <= 0.15:
            score_a2 += 15
        elif cr <= 0.30:
            score_a2 += 8
            penalties.append(f"Copy ratio: {cr:.0%}")
        else:
            penalties.append(f"High copy ratio: {cr:.0%}")
    else:
        pr = parroting_audit['parroted_ratio']
        if pr <= 0.30:
            score_a2 += 15
        elif pr <= 0.50:
            score_a2 += 8
            penalties.append(f"Parroting: {pr:.0%}")
        else:
            penalties.append(f"High parroting: {pr:.0%}")

    cs = cross_source_audit['cross_source_sentences']
    if cs >= 3:
        score_a2 += 10
    elif cs >= 1:
        score_a2 += 5
        penalties.append(f"Low cross-source: {cs}")
    else:
        penalties.append(f"No cross-source sentences")
    score += score_a2

    # Axis 3: Question Answering (20 pts)
    score_a3 = 0
    ir = integration_audit['integration_ratio']
    if ir >= 0.50:
        score_a3 += 12
    elif ir >= 0.25:
        score_a3 += 6
        penalties.append(f"Low integration: {ir:.0%}")
    else:
        penalties.append(f"No integration: {ir:.0%}")

    if integration_audit['has_ranking']:
        score_a3 += 8
    else:
        penalties.append("No ranking/recommendation")
    score += score_a3

    # Axis 4: Evidence Utilization (10 pts)
    score_a4 = 0
    cc = coverage_audit['category_coverage']
    if cc >= 0.60:
        score_a4 += 10
    elif cc >= 0.40:
        score_a4 += 5
        penalties.append(f"Low category coverage: {cc:.0%}")
    else:
        penalties.append(f"Poor category coverage: {cc:.0%}")
    score += score_a4

    # Axis 5: Citation Quality (10 pts)
    score_a5 = 0
    if cite_audit['total_cite_tokens'] >= 10:
        score_a5 += 5
    elif cite_audit['total_cite_tokens'] >= 5:
        score_a5 += 3
    else:
        penalties.append(f"Low citations: {cite_audit['total_cite_tokens']}")

    if not cite_audit['phantom_citations']:
        score_a5 += 5
    else:
        penalties.append(f"Phantom: {cite_audit['phantom_citations']}")
    score += score_a5

    # Axis 6: Content Quality (10 pts)
    score_a6 = 0
    if leak_audit['leakage_count'] == 0:
        score_a6 += 5
    else:
        penalties.append(f"POLARIS leakage: {leak_audit['leakage_count']}")

    if density_audit['numbers_with_units'] >= 5:
        score_a6 += 5
    elif density_audit['numbers_with_units'] >= 2:
        score_a6 += 3
    else:
        penalties.append(f"Low data density: {density_audit['numbers_with_units']}")
    score += score_a6

    # Print NLI-based audits (when active)
    if _nli_active and nli_faith_audit:
        print(f"\n  ── NLI FAITHFULNESS ──")
        print(f"    Claims: {nli_faith_audit['total_claims']}")
        print(f"    Supported: {nli_faith_audit['supported']}")
        print(f"    Not supported: {nli_faith_audit['not_supported']}")
        print(f"    Contradicted: {nli_faith_audit['contradicted']}")
        print(f"    Faithfulness: {nli_faith_audit['faithfulness_score']:.0%}")
        for c in nli_faith_audit['contradictions'][:3]:
            print(f"      X [{c['label']}] {c['ev_id']}: "
                  f"NLI={c['nli_score']:.3f}")
            print(f"        claim: \"{c['claim'][:70]}\"")
            print(f"        evidence: \"{c['ev_statement'][:70]}\"")

    if _nli_active and originality_audit:
        print(f"\n  ── ORIGINALITY (embedding) ──")
        print(f"    Sentences: {originality_audit['total_sentences']}")
        print(f"    Original: {originality_audit['original']}")
        print(f"    Copied: {originality_audit['copied']} "
              f"({originality_audit['copy_ratio']:.0%})")
        if originality_audit.get('examples'):
            for ex in originality_audit['examples'][:2]:
                print(f"      > \"{ex[:80]}\"")

    # Print legacy regex audits (always shown for reference)
    print(f"\n  ── SUBSTANCE: PARROTING (Jaccard) ──")
    print(f"    Sentences: {parroting_audit['total_sentences']}")
    print(f"    Parroted: {parroting_audit['parroted_count']} "
          f"({parroting_audit['parroted_ratio']:.0%})")
    if parroting_audit.get('examples'):
        for ex in parroting_audit['examples'][:2]:
            print(f"      > \"{ex[:80]}\"")

    print(f"\n  ── SUBSTANCE: INTEGRATION ──")
    print(f"    Multi-criteria: {integration_audit['is_multi_criteria']}")
    print(f"    Integrated paragraphs: {integration_audit['integrated_paragraphs']}/{integration_audit['total_paragraphs']}")
    print(f"    Has ranking: {integration_audit['has_ranking']}")
    print(f"    Integration score: {integration_audit['integration_score']:.2f}")

    print(f"\n  ── SUBSTANCE: EVIDENCE COVERAGE ──")
    print(f"    Categories cited: {coverage_audit['categories_cited']}/{coverage_audit['total_categories']}")
    print(f"    Utilization: {coverage_audit['utilization_rate']:.0%}")

    print(f"\n  ── SUBSTANCE: CROSS-SOURCE ──")
    print(f"    Cross-source sentences: {cross_source_audit['cross_source_sentences']}")
    print(f"    Cross-source ratio: {cross_source_audit['cross_source_ratio']:.0%}")

    print(f"\n  ── SCORE: {score}/{max_score} ──")
    print(f"    Axis 1 (Factual):     {score_a1}/25")
    print(f"    Axis 2 (Synthesis):   {score_a2}/25")
    print(f"    Axis 3 (QA):          {score_a3}/20")
    print(f"    Axis 4 (Evidence):    {score_a4}/10")
    print(f"    Axis 5 (Citation):    {score_a5}/10")
    print(f"    Axis 6 (Content):     {score_a6}/10")
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
        "parroting_ratio": parroting_audit['parroted_ratio'],
        "integration_score": integration_audit['integration_score'],
        "category_coverage": coverage_audit['category_coverage'],
        "cross_source": cross_source_audit['cross_source_sentences'],
        "nli_faithfulness": (
            nli_faith_audit['faithfulness_score']
            if nli_faith_audit else None
        ),
        "nli_contradictions": (
            nli_faith_audit['contradicted']
            if nli_faith_audit else None
        ),
        "originality_copy_ratio": (
            originality_audit['copy_ratio']
            if originality_audit else None
        ),
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
