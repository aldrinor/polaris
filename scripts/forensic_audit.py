"""
Post-run exhaustive forensic audit for POLARIS pipeline.

Reads ALL trace events, cost ledger, result state, and final report to
produce a comprehensive 11-section forensic analysis. Every reasoning
stream, evidence piece, citation, and LLM call is examined line-by-line.

11 Forensic Sections:
    1. Pipeline Timeline         Node durations, critical path, iteration rationale
    2. Planning Deep-Dive        Full reasoning text, query diversity analysis
    3. Search & Fetch Forensics  Every search/fetch, domain distribution, stub rate
    4. STORM Interview Review    Full Q&A transcripts, persona coverage
    5. Evidence Chain            Full funnel, every piece with quote text
    6. Verification Forensics    Every claim verdict, per-source faithfulness
    7. Report Text Forensics     Citation mapping, cross-section dedup, CoT scan
    8. Quality Gate Audit        Every gate with threshold vs actual
    9. LLM Call Audit            Every call with tokens/cost, cross-check ledger
   10. Anomaly Digest            Categorized counts from live anomaly log
   11. Benchmark Comparison      Run metrics vs competitor placeholders

CLI: python scripts/forensic_audit.py --vector-id PG_TEST_059
     [--trace ...] [--result ...] [--report ...]

Zero new dependencies. Standard library + json.
"""

import argparse
import json
import logging
import math
import os
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("forensic_audit")

# Pricing (from openrouter_client.py:53-54)
INPUT_COST_PER_M = float(os.getenv("OPENROUTER_INPUT_COST_PER_M", "0.45"))
OUTPUT_COST_PER_M = float(os.getenv("OPENROUTER_OUTPUT_COST_PER_M", "2.25"))

# CoT patterns (from automated_deep_audit.py:50-90)
_COT_PATTERNS = [
    r"\bLet me\b", r"\bI need to\b", r"\bFirst,", r"\bStep\s+\d+:",
    r"\bNow I will\b", r"\bthinking about\b", r"\bIn summary, I\b",
    r"\bAs an AI\b", r"\bmy analysis\b", r"\bI should note\b",
    r"\bI will now\b", r"\bLet's\b", r"\bI have identified\b",
    r"\bI'll\b", r"\bmy assessment\b", r"\bI believe\b", r"\bI think\b",
    r"\bI would\b", r"\bmy review\b", r"\bI must write\b",
    r"\bI only have \d+\b", r"\bGiven the strict instruction\b",
    r"\bThe content stays grounded\b", r"\bI should indicate\b",
    r"\bI should write\b", r"\bI cannot invent\b", r"\bI am instructed\b",
    r"\bI was told to\b", r"\bthe provided evidence\b",
    r"^\s*\d+[a-z]\.\s",
]
_COMPILED_COT = [re.compile(p, re.IGNORECASE | re.MULTILINE) for p in _COT_PATTERNS]


# ---------------------------------------------------------------------------
# File loading utilities
# ---------------------------------------------------------------------------
def _load_jsonl(path: Path) -> list[dict]:
    """Load all lines from a JSONL file."""
    items = []
    if not path.exists():
        logger.warning("File not found: %s", path)
        return items
    with open(path, "r", encoding="utf-8") as f:
        for i, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                items.append(json.loads(line))
            except json.JSONDecodeError:
                logger.debug("Malformed JSONL line %d in %s", i, path)
    return items


def _load_json(path: Path) -> Optional[dict]:
    """Load a JSON file."""
    if not path.exists():
        logger.warning("File not found: %s", path)
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _load_text(path: Path) -> Optional[str]:
    """Load a text file."""
    if not path.exists():
        logger.warning("File not found: %s", path)
        return None
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _group_events(events: list[dict]) -> dict[str, list[dict]]:
    """Group trace events by type."""
    grouped: dict[str, list[dict]] = defaultdict(list)
    for ev in events:
        grouped[ev.get("type", "unknown")].append(ev)
    return grouped


def _filter_cost_ledger(
    all_entries: list[dict], trace_events: list[dict],
) -> list[dict]:
    """Filter cost ledger to entries within the trace's time window.

    Uses the first and last trace event timestamps to bracket the run.
    Falls back to returning all entries if timestamps can't be parsed.
    """
    if not trace_events or not all_entries:
        return all_entries

    # Extract time window from trace
    timestamps = [e.get("ts", "") for e in trace_events if e.get("ts")]
    if not timestamps:
        return all_entries

    try:
        first_ts = datetime.fromisoformat(min(timestamps))
        last_ts = datetime.fromisoformat(max(timestamps))
    except (ValueError, TypeError):
        return all_entries

    # Add 1-minute buffer on each side
    from datetime import timedelta
    start = first_ts - timedelta(minutes=1)
    end = last_ts + timedelta(minutes=1)

    filtered = []
    for entry in all_entries:
        entry_ts_str = entry.get("timestamp", "")
        if not entry_ts_str:
            continue
        try:
            entry_ts = datetime.fromisoformat(entry_ts_str)
            if start <= entry_ts <= end:
                filtered.append(entry)
        except (ValueError, TypeError):
            continue

    return filtered


# ---------------------------------------------------------------------------
# Section builders
# ---------------------------------------------------------------------------
def _section_1_timeline(events: list[dict], grouped: dict) -> str:
    """Section 1: Pipeline Timeline."""
    lines = ["## 1. Pipeline Timeline\n"]

    # Node start/end pairs
    node_starts = {}
    node_entries = []
    for ev in events:
        node = ev.get("node", "")
        if ev.get("type") == "node_start":
            node_starts[node] = ev.get("ts", "")
        elif ev.get("type") == "node_end":
            start_ts = node_starts.get(node, "")
            duration_ms = ev.get("duration_ms", 0)
            node_entries.append({
                "node": node,
                "start": start_ts,
                "end": ev.get("ts", ""),
                "duration_ms": duration_ms,
            })

    if node_entries:
        lines.append("| Node | Start | End | Duration |")
        lines.append("|------|-------|-----|----------|")
        total_ms = 0
        for ne in node_entries:
            dur = ne["duration_ms"]
            total_ms += dur
            lines.append(
                f"| {ne['node']} | {_fmt_ts(ne['start'])} | "
                f"{_fmt_ts(ne['end'])} | {_fmt_dur(dur)} |"
            )
        lines.append(f"\n**Total pipeline time:** {_fmt_dur(total_ms)}\n")

        # Critical path (longest node)
        if node_entries:
            longest = max(node_entries, key=lambda x: x["duration_ms"])
            lines.append(
                f"**Critical path:** {longest['node']} "
                f"({_fmt_dur(longest['duration_ms'])})\n"
            )

    # Iteration decisions
    iter_decisions = grouped.get("iteration_decision", [])
    if iter_decisions:
        lines.append("### Iteration Decisions\n")
        for ev in iter_decisions:
            lines.append(f"**Iteration {ev.get('iteration', '?')}:** "
                         f"decision=`{ev.get('decision', '')}`\n")
            rationale = ev.get("rationale", {})
            if isinstance(rationale, dict):
                for k, v in rationale.items():
                    lines.append(f"- {k}: {v}")
            elif isinstance(rationale, str):
                lines.append(f"- {rationale}")
            lines.append("")

    # Evaluate node enrichment (new visibility)
    evaluate_ends = [e for e in events if e.get("type") == "node_end" and e.get("node") == "evaluate"]
    for ev in evaluate_ends:
        delta = ev.get("evidence_delta")
        faith = ev.get("faithfulness")
        if delta is not None or faith is not None:
            lines.append("### Evaluate Node Details\n")
            if delta is not None:
                lines.append(f"- Evidence delta: {delta:+d}")
            if faith is not None:
                lines.append(f"- Faithfulness: {faith*100:.1f}%")
            lines.append("")

    return "\n".join(lines)


def _section_2_planning(grouped: dict) -> str:
    """Section 2: Planning Deep-Dive."""
    lines = ["## 2. Planning Deep-Dive\n"]

    # Reasoning captures for planning
    reasoning = [e for e in grouped.get("reasoning_capture", [])
                 if e.get("node") == "plan"]
    if reasoning:
        lines.append(f"**Planning reasoning captures:** {len(reasoning)}\n")
        for i, ev in enumerate(reasoning, 1):
            text = ev.get("reasoning_text", "")
            call_type = ev.get("call_type", "")
            lines.append(f"### Planning Reasoning #{i} ({call_type})")
            lines.append(f"*{len(text)} chars*\n")
            lines.append("```")
            lines.append(text)
            lines.append("```\n")
    else:
        lines.append("*No planning reasoning captured.*\n")

    # Query generation
    queries = [e for e in grouped.get("query", []) if e.get("node") == "plan"]
    if queries:
        lines.append("### Query Generation\n")
        for ev in queries:
            lines.append(f"- {ev.get('action', '')}: {ev.get('count', 0)} queries")
        lines.append("")

    # Query Plan analysis (new visibility emissions)
    plan_events = [e for e in grouped.get("evidence", [])
                   if e.get("action") in ("query_plan", "seed_query_plan")]
    if plan_events:
        lines.append("### Research Plan\n")
        for pe in plan_events:
            strategy = pe.get("search_strategy", "")
            concepts = pe.get("key_concepts", [])
            plan_queries = pe.get("queries", [])
            persp_dist = pe.get("perspective_distribution", {})
            missing = pe.get("missing_perspectives", [])

            lines.append(f"**Search strategy:** {strategy}")
            if concepts:
                lines.append(f"**Key concepts:** {', '.join(concepts[:10])}")
            lines.append(f"**Queries generated:** {len(plan_queries)}\n")

            if persp_dist:
                lines.append("| Perspective | Queries |")
                lines.append("|-------------|---------|")
                for p, cnt in sorted(persp_dist.items(), key=lambda x: -x[1]):
                    flag = " **MISSING**" if p in missing else ""
                    lines.append(f"| {p}{flag} | {cnt} |")
                lines.append("")

            if missing:
                lines.append(f"**Missing perspectives:** {', '.join(missing)}\n")

            if plan_queries:
                lines.append("| # | Query | Perspective | Intent |")
                lines.append("|---|-------|-------------|--------|")
                for i, q in enumerate(plan_queries[:30], 1):
                    lines.append(f"| {i} | {q.get('query', '')[:80]} | {q.get('perspective', '')} | {q.get('intent', '')[:50]} |")
                lines.append("")

    return "\n".join(lines)


def _section_3_search_fetch(grouped: dict) -> str:
    """Section 3: Search & Fetch Forensics."""
    lines = ["## 3. Search & Fetch Forensics\n"]

    # Search results
    searches = grouped.get("search_result", [])
    if searches:
        lines.append(f"**Total search events:** {len(searches)}\n")

        # By engine
        by_engine = defaultdict(list)
        for ev in searches:
            by_engine[ev.get("engine", "unknown")].append(ev)

        lines.append("### Search Results by Engine\n")
        lines.append("| Engine | Queries | Total Results | Avg Results/Query |")
        lines.append("|--------|---------|---------------|-------------------|")
        for engine, evs in sorted(by_engine.items()):
            total_results = sum(e.get("result_count", 0) for e in evs)
            avg = total_results / max(len(evs), 1)
            lines.append(f"| {engine} | {len(evs)} | {total_results} | {avg:.1f} |")
        lines.append("")

        # Full query list
        lines.append("### All Search Queries\n")
        for ev in searches:
            lines.append(
                f"- [{ev.get('engine', '')}] \"{ev.get('query', '')}\" "
                f"-> {ev.get('result_count', 0)} results"
            )
        lines.append("")

        # Academic vs web ratio
        web_count = sum(len(evs) for eng, evs in by_engine.items()
                        if eng not in ("semantic_scholar", "openalex"))
        acad_count = sum(len(evs) for eng, evs in by_engine.items()
                         if eng in ("semantic_scholar", "openalex"))
        total = web_count + acad_count
        if total > 0:
            lines.append(
                f"**Web/Academic ratio:** {web_count}/{acad_count} "
                f"({web_count/total:.0%}/{acad_count/total:.0%})\n"
            )

    # Fetches
    fetches = grouped.get("fetch", [])
    if fetches:
        lines.append(f"### Fetch Results ({len(fetches)} total)\n")

        # Status distribution
        status_counts = Counter(e.get("status", "unknown") for e in fetches)
        lines.append("| Status | Count | % |")
        lines.append("|--------|-------|---|")
        for status, count in status_counts.most_common():
            pct = count / len(fetches) * 100
            lines.append(f"| {status} | {count} | {pct:.1f}% |")
        lines.append("")

        # Domain distribution
        domains = Counter()
        for ev in fetches:
            url = ev.get("url", "")
            domain = _extract_domain(url)
            if domain:
                domains[domain] += 1

        if domains:
            lines.append("### Domain Distribution (top 20)\n")
            lines.append("| Domain | Fetches | Avg Content (chars) |")
            lines.append("|--------|---------|---------------------|")
            domain_content = defaultdict(list)
            for ev in fetches:
                domain = _extract_domain(ev.get("url", ""))
                if domain:
                    domain_content[domain].append(ev.get("content_len", 0))
            for domain, count in domains.most_common(20):
                avg_len = sum(domain_content[domain]) / max(len(domain_content[domain]), 1)
                lines.append(f"| {domain} | {count} | {avg_len:.0f} |")
            lines.append("")

        # Stub/paywall rate
        stub_count = sum(1 for e in fetches
                         if e.get("status") == "ok" and 0 < e.get("content_len", 0) < 500)
        paywall_count = status_counts.get("paywall", 0) + status_counts.get("blocked", 0)
        if len(fetches) > 0:
            lines.append(
                f"**Stub rate:** {stub_count}/{len(fetches)} ({stub_count/len(fetches):.1%})  \n"
                f"**Paywall/blocked rate:** {paywall_count}/{len(fetches)} "
                f"({paywall_count/len(fetches):.1%})\n"
            )

        # Duplicate URL list
        url_counts = Counter(e.get("url", "") for e in fetches)
        dupes = {url: cnt for url, cnt in url_counts.items() if cnt > 1 and url}
        if dupes:
            lines.append(f"### Duplicate Fetch URLs ({len(dupes)})\n")
            for url, cnt in sorted(dupes.items(), key=lambda x: -x[1])[:20]:
                lines.append(f"- ({cnt}x) {url[:120]}")
            lines.append("")

        # Full fetch log
        lines.append("<details><summary>Full Fetch Log (click to expand)</summary>\n")
        for ev in fetches:
            status = ev.get("status", "?")
            url = ev.get("url", "")
            clen = ev.get("content_len", 0)
            dur = ev.get("duration_ms", 0)
            lines.append(f"- [{status}] {url} ({clen} chars, {_fmt_dur(dur)})")
        lines.append("\n</details>\n")

    # Agentic search rounds (new visibility emissions)
    agentic_rounds = [e for e in grouped.get("evidence", [])
                      if e.get("action") == "agentic_round_summary"]
    if agentic_rounds:
        lines.append("### Agentic Search Convergence\n")
        lines.append("| Round | Queries | Web | Academic | New URLs | Total URLs |")
        lines.append("|-------|---------|-----|----------|----------|------------|")
        for r in agentic_rounds:
            lines.append(f"| {r.get('count', '?')} | {r.get('queries', 0)} | "
                         f"{r.get('web_results', 0)} | {r.get('academic_results', 0)} | "
                         f"{r.get('new_urls', 0)} | {r.get('total_urls', 0)} |")
        lines.append("")

        # Convergence analysis
        if len(agentic_rounds) >= 2:
            first_new = agentic_rounds[0].get("new_urls", 0)
            last_new = agentic_rounds[-1].get("new_urls", 0)
            if first_new > 0:
                convergence = 1.0 - (last_new / first_new)
                lines.append(f"**Convergence:** {convergence:.0%} URL discovery reduction "
                             f"({first_new} -> {last_new} new URLs/round)\n")

    # Fetch pipeline summary
    fetch_summaries = [e for e in grouped.get("evidence", [])
                       if e.get("action") == "fetch_summary"]
    if fetch_summaries:
        fs = fetch_summaries[-1]  # Use most recent
        lines.append("### Fetch Pipeline Summary\n")
        total = fs.get("total_attempted", 0)
        success = fs.get("success", 0)
        snippet = fs.get("snippet_fallback", 0)
        failed = fs.get("failed", 0)
        lines.append(f"| Metric | Count | % |")
        lines.append(f"|--------|-------|---|")
        lines.append(f"| Attempted | {total} | 100% |")
        lines.append(f"| Success | {success} | {success/max(total,1)*100:.0f}% |")
        lines.append(f"| Snippet Fallback | {snippet} | {snippet/max(total,1)*100:.0f}% |")
        lines.append(f"| Failed | {failed} | {failed/max(total,1)*100:.0f}% |")
        lines.append("")

    return "\n".join(lines)


def _section_4_storm(grouped: dict) -> str:
    """Section 4: STORM Interview Review."""
    lines = ["## 4. STORM Interview Review\n"]

    transcripts = grouped.get("storm_transcript", [])
    if not transcripts:
        lines.append("*No STORM transcripts captured.*\n")
        return "\n".join(lines)

    lines.append(f"**Total STORM rounds:** {len(transcripts)}\n")

    # Persona distribution
    personas = Counter(e.get("persona", "unknown") for e in transcripts)
    lines.append("### Persona Distribution\n")
    lines.append("| Persona | Rounds |")
    lines.append("|---------|--------|")
    for persona, count in personas.most_common():
        lines.append(f"| {persona} | {count} |")
    lines.append("")

    # Full transcripts
    for i, ev in enumerate(transcripts, 1):
        persona = ev.get("persona", "Unknown")
        round_num = ev.get("round", "?")
        question = ev.get("question", "")
        answer = ev.get("answer", "")
        sources = ev.get("sources", [])
        findings = ev.get("key_findings", [])

        lines.append(f"### Interview #{i}: {persona} (Round {round_num})\n")
        lines.append(f"**Question:**\n> {question}\n")
        lines.append(f"**Answer:**\n{answer}\n")
        if sources:
            lines.append("**Sources:**")
            for s in sources:
                lines.append(f"- {s}")
            lines.append("")
        if findings:
            lines.append("**Key Findings:**")
            for f in findings:
                lines.append(f"- {f}")
            lines.append("")

    # Coverage assessment
    lines.append("### Coverage Assessment\n")
    lines.append(f"- Unique personas: {len(personas)}")
    lines.append(f"- Total rounds: {len(transcripts)}")
    all_sources = set()
    all_findings = set()
    for ev in transcripts:
        all_sources.update(ev.get("sources", []))
        all_findings.update(ev.get("key_findings", []))
    lines.append(f"- Unique sources referenced: {len(all_sources)}")
    lines.append(f"- Unique findings: {len(all_findings)}\n")

    return "\n".join(lines)


def _section_5_evidence(result: Optional[dict], grouped: dict) -> str:
    """Section 5: Evidence Chain."""
    lines = ["## 5. Evidence Chain\n"]

    # Evidence flow from trace
    evidence_events = grouped.get("evidence", [])
    if evidence_events:
        lines.append("### Evidence Funnel (from trace)\n")
        lines.append("| Action | Count |")
        lines.append("|--------|-------|")
        for ev in evidence_events:
            lines.append(f"| {ev.get('action', '')} | {ev.get('count', 0)} |")
        lines.append("")

    # Full evidence from result state
    if result and "evidence" in result:
        evidence = result["evidence"]
        lines.append(f"### Full Evidence ({len(evidence)} pieces)\n")

        # Tier histogram
        tiers = Counter(e.get("quality_tier", "UNKNOWN") for e in evidence)
        lines.append("**Tier Distribution:**\n")
        lines.append("| Tier | Count | % |")
        lines.append("|------|-------|---|")
        for tier, count in tiers.most_common():
            pct = count / max(len(evidence), 1) * 100
            lines.append(f"| {tier} | {count} | {pct:.1f}% |")
        lines.append("")

        # Source concentration
        source_counts = Counter(e.get("source_url", "") for e in evidence)
        lines.append("**Source Concentration (top 15):**\n")
        lines.append("| Source URL | Evidence Count |")
        lines.append("|-----------|----------------|")
        for url, count in source_counts.most_common(15):
            lines.append(f"| {url[:80]} | {count} |")
        lines.append("")

        # Relevance distribution
        relevances = [e.get("relevance_score", 0) for e in evidence
                      if e.get("relevance_score") is not None]
        if relevances:
            avg_rel = sum(relevances) / len(relevances)
            lines.append(
                f"**Relevance:** min={min(relevances):.2f}, "
                f"max={max(relevances):.2f}, avg={avg_rel:.2f}\n"
            )

        # Full evidence listing (in expandable block)
        lines.append("<details><summary>Full Evidence Listing (click to expand)</summary>\n")
        for i, ev in enumerate(evidence, 1):
            eid = ev.get("evidence_id", f"ev_{i}")
            tier = ev.get("quality_tier", "?")
            rel = ev.get("relevance_score", 0)
            url = ev.get("source_url", "")
            quote = ev.get("direct_quote", "")
            lines.append(f"**{eid}** [{tier}, rel={rel:.2f}]")
            lines.append(f"- Source: {url[:120]}")
            lines.append(f"- Quote: {quote}")
            lines.append("")
        lines.append("</details>\n")

    # Signal Distribution (new visibility)
    signal_events = [e for e in grouped.get("evidence", [])
                     if e.get("action") == "tier_signal_distribution"]
    if signal_events:
        stats = signal_events[-1].get("signal_stats", {})
        lines.append("### 5-Signal Quality Distribution\n")
        lines.append("| Signal | Min | Median | Max | Count |")
        lines.append("|--------|-----|--------|-----|-------|")
        # FIX-P6: Map both old (semantic_*) and new (sig_*) key names for display
        names = {"sig_relevance": "Semantic Relevance", "sig_authority": "Source Authority",
                 "sig_density": "Content Density", "sig_freshness": "Freshness",
                 "sig_grounding": "NLI Grounding",
                 "semantic_relevance": "Semantic Relevance", "source_authority": "Source Authority",
                 "content_density": "Content Density", "freshness": "Freshness",
                 "nli_grounding": "NLI Grounding"}
        for sn, vals in stats.items():
            label = names.get(sn, sn)
            lines.append(f"| {label} | {vals.get('min',0):.3f} | {vals.get('median',0):.3f} | "
                         f"{vals.get('max',0):.3f} | {vals.get('count',0)} |")
        lines.append("")

    # Dedup effectiveness
    dedup_events = [e for e in grouped.get("evidence", [])
                    if e.get("action") == "dedup_summary"]
    if dedup_events:
        ds = dedup_events[-1]
        pre = ds.get("pre_dedup", 0)
        post = ds.get("post_dedup", ds.get("count", 0))
        removed = pre - post
        lines.append(f"### Dedup Pipeline\n")
        lines.append(f"- Pre-dedup: {pre}")
        lines.append(f"- Removed: {removed} ({removed/max(pre,1)*100:.0f}%)")
        lines.append(f"- Post-dedup: {post}\n")

    # Cross-reference groups
    xref_events = [e for e in grouped.get("evidence", [])
                   if e.get("action") == "cross_reference_groups"]
    if xref_events:
        groups = xref_events[-1].get("groups", [])
        lines.append(f"### Cross-Reference Corroboration ({len(groups)} groups)\n")
        for i, g in enumerate(groups[:10], 1):
            ids = g.get("evidence_ids", [])
            sim = g.get("similarity", 0)
            lines.append(f"- Group {i}: sim={sim:.2f}, evidence: {', '.join(ids[:5])}")
        lines.append("")

    return "\n".join(lines)


def _section_6_verification(result: Optional[dict], grouped: dict) -> str:
    """Section 6: Verification Forensics."""
    lines = ["## 6. Verification Forensics\n"]

    if result and "claims" in result:
        claims = result["claims"]
        lines.append(f"**Total claims:** {len(claims)}\n")

        # Verdict distribution
        verdicts = Counter(
            "FAITHFUL" if c.get("is_faithful") else "UNFAITHFUL"
            for c in claims
        )
        lines.append("**Verdict Distribution:**\n")
        lines.append("| Verdict | Count | % |")
        lines.append("|---------|-------|---|")
        for v, count in verdicts.most_common():
            pct = count / max(len(claims), 1) * 100
            lines.append(f"| {v} | {count} | {pct:.1f}% |")
        lines.append("")

        # Verification method distribution
        methods = Counter(c.get("verification_method", "unknown") for c in claims)
        lines.append("**Verification Method:**\n")
        for method, count in methods.most_common():
            lines.append(f"- {method}: {count}")
        lines.append("")

        # NLI score distribution
        nli_scores = [c.get("nli_score", 0) for c in claims
                      if c.get("nli_score") is not None]
        if nli_scores:
            avg_nli = sum(nli_scores) / len(nli_scores)
            lines.append(
                f"**NLI scores:** min={min(nli_scores):.2f}, "
                f"max={max(nli_scores):.2f}, avg={avg_nli:.2f}\n"
            )

        # Rubber-stamp check
        if claims:
            all_same = len(set(c.get("is_faithful") for c in claims)) <= 1
            if all_same and len(claims) > 5:
                lines.append(
                    "**WARNING: All claims have identical verdict "
                    f"({'FAITHFUL' if claims[0].get('is_faithful') else 'UNFAITHFUL'}) "
                    "-- possible rubber-stamping.**\n"
                )

        # Per-source faithfulness
        if result and "evidence" in result:
            evidence_map = {
                e.get("evidence_id"): e for e in result["evidence"]
            }
            source_faith: dict[str, list[bool]] = defaultdict(list)
            for c in claims:
                for eid in c.get("evidence_ids", []):
                    ev = evidence_map.get(eid)
                    if ev:
                        url = ev.get("source_url", "unknown")
                        source_faith[url].append(bool(c.get("is_faithful")))

            if source_faith:
                lines.append("### Per-Source Faithfulness\n")
                lines.append("| Source | Claims | Faithful | Rate |")
                lines.append("|--------|--------|----------|------|")
                for url, verdicts_list in sorted(
                    source_faith.items(),
                    key=lambda x: sum(x[1]) / max(len(x[1]), 1),
                ):
                    total = len(verdicts_list)
                    faithful = sum(verdicts_list)
                    rate = faithful / max(total, 1)
                    lines.append(
                        f"| {url[:60]} | {total} | {faithful} | {rate:.0%} |"
                    )
                lines.append("")

        # Full claim listing
        lines.append("<details><summary>Full Claim Listing (click to expand)</summary>\n")
        for c in claims:
            cid = c.get("claim_id", "?")
            faithful = c.get("is_faithful")
            method = c.get("verification_method", "?")
            nli = c.get("nli_score", "N/A")
            stmt = c.get("statement", "")
            lines.append(
                f"**{cid}** [{'FAITH' if faithful else 'UNFAITH'}] "
                f"method={method} nli={nli}"
            )
            lines.append(f"- Statement: {stmt}")
            reasoning = c.get("reasoning", "")
            if reasoning:
                lines.append(f"- Reasoning: {reasoning[:300]}")
            lines.append("")
        lines.append("</details>\n")

    # Verification-related trace events
    verify_gates = [e for e in grouped.get("quality_gate", [])
                    if e.get("gate") == "faithfulness"]
    if verify_gates:
        lines.append("### Faithfulness Gate History\n")
        for ev in verify_gates:
            lines.append(
                f"- {'PASS' if ev.get('passed') else 'FAIL'}: "
                f"actual={ev.get('actual')}, threshold={ev.get('threshold')}"
            )
        lines.append("")

    # NLI Verification Detail (new visibility)
    nli_events = [e for e in grouped.get("evidence", [])
                  if e.get("action") == "nli_verification_detail"]
    if nli_events:
        nli = nli_events[-1]
        lines.append("### NLI Verification Summary\n")
        lines.append(f"- Faithful: {nli.get('faithful_count', 0)}")
        lines.append(f"- Faithfulness: {nli.get('faithfulness_pct', 0):.1f}%")
        lines.append(f"- Disputed: {nli.get('disputed_count', 0)}\n")

        claims_detail = nli.get("claims_detail", [])
        if claims_detail:
            lines.append("### NLI Per-Claim Detail (top 20)\n")
            lines.append("| # | NLI Score | Faithful | Statement |")
            lines.append("|---|-----------|----------|-----------|")
            for i, c in enumerate(claims_detail[:20], 1):
                faith = "YES" if c.get("is_faithful") else "NO"
                score = c.get("nli_score", 0)
                stmt = c.get("statement", "")[:100]
                lines.append(f"| {i} | {score:.3f} | {faith} | {stmt} |")
            lines.append("")

    return "\n".join(lines)


def _section_7_report_text(
    report_text: Optional[str], result: Optional[dict],
    grouped: dict,
) -> str:
    """Section 7: Report Text Forensics."""
    lines = ["## 7. Report Text Forensics\n"]

    if not report_text:
        lines.append("*No report text available.*\n")
        return "\n".join(lines)

    word_count = len(report_text.split())
    lines.append(f"**Total words:** {word_count:,}\n")

    # Citation mapping: find all [N] references
    cite_pattern = re.compile(r"\[(\d+)\]")
    citations = cite_pattern.findall(report_text)
    cite_counts = Counter(citations)

    if cite_counts:
        lines.append(f"**Total inline citations:** {len(citations)}")
        lines.append(f"**Unique citation numbers:** {len(cite_counts)}\n")

        lines.append("### Citation Frequency\n")
        lines.append("| Ref # | Occurrences |")
        lines.append("|-------|-------------|")
        for ref, count in cite_counts.most_common():
            lines.append(f"| [{ref}] | {count} |")
        lines.append("")

    # Map to bibliography if available
    if result and "bibliography" in result:
        bib = result["bibliography"]
        if isinstance(bib, list):
            lines.append("### Bibliography Mapping\n")
            lines.append("| Ref # | URL | Title |")
            lines.append("|-------|-----|-------|")
            for entry in bib:
                if isinstance(entry, dict):
                    ref = entry.get("reference_number", entry.get("ref", "?"))
                    url = entry.get("url", entry.get("source_url", ""))
                    title = entry.get("title", entry.get("source_title", ""))
                    lines.append(f"| [{ref}] | {url[:80]} | {title[:60]} |")
            lines.append("")

    # Section-level analysis
    report_sections = report_text.split("\n## ")
    if len(report_sections) > 1:
        lines.append("### Citation Density per Section\n")
        lines.append("| Section | Words | Citations | Density |")
        lines.append("|---------|-------|-----------|---------|")
        for sec_text in report_sections:
            title_line = sec_text.split("\n")[0].strip("# ")
            sec_words = len(sec_text.split())
            sec_cites = len(cite_pattern.findall(sec_text))
            density = sec_cites / max(sec_words, 1) * 100
            lines.append(
                f"| {title_line[:40]} | {sec_words} | {sec_cites} | "
                f"{density:.1f}/100w |"
            )
        lines.append("")

    # Cross-section Jaccard duplication
    if result and "sections" in result:
        sections = result["sections"]
        if len(sections) >= 2:
            lines.append("### Cross-Section Jaccard Similarity\n")
            high_dupes = []
            for i in range(len(sections)):
                for j in range(i + 1, len(sections)):
                    content_i = sections[i].get("content", "")
                    content_j = sections[j].get("content", "")
                    jacc = _jaccard_words(content_i, content_j)
                    if jacc > 0.30:
                        ti = sections[i].get("title", f"Section {i}")
                        tj = sections[j].get("title", f"Section {j}")
                        high_dupes.append((ti, tj, jacc))

            if high_dupes:
                lines.append("| Section A | Section B | Jaccard |")
                lines.append("|-----------|-----------|---------|")
                for a, b, j in sorted(high_dupes, key=lambda x: -x[2]):
                    lines.append(f"| {a[:30]} | {b[:30]} | {j:.2f} |")
                lines.append("")
            else:
                lines.append("No cross-section pairs with Jaccard > 0.30.\n")

    # CoT leakage scan
    lines.append("### CoT Leakage Scan\n")
    cot_matches = []
    for pattern in _COMPILED_COT:
        found = pattern.findall(report_text)
        cot_matches.extend(found)

    if cot_matches:
        lines.append(f"**WARNING: {len(cot_matches)} CoT pattern matches found!**\n")
        for match in cot_matches[:20]:
            lines.append(f"- `{match}`")
        lines.append("")
    else:
        lines.append("No CoT leakage detected.\n")

    # Report Outline (new visibility)
    outline_events = [e for e in grouped.get("evidence", [])
                      if e.get("action") == "report_outline"]
    if outline_events:
        o = outline_events[-1]
        lines.append(f'### Report Outline: "{o.get("title", "")[:80]}"\n')
        outline_sections = o.get("sections", [])
        lines.append("| # | Title | Evidence | Target Words | Description |")
        lines.append("|---|-------|----------|--------------|-------------|")
        for i, s in enumerate(outline_sections, 1):
            lines.append(f"| {i} | {s.get('title','')[:60]} | {s.get('evidence_count',0)} | "
                         f"{s.get('target_words',0)} | {s.get('description','')[:80]} |")
        lines.append("")

    # Section-Evidence Map
    sem_events = [e for e in grouped.get("evidence", [])
                  if e.get("action") == "section_evidence_map"]
    if sem_events:
        mapping = sem_events[-1].get("mapping", [])
        lines.append("### Section-Evidence Mapping\n")
        for m in mapping:
            lines.append(f"- {m.get('section_id','')}: {m.get('evidence_count',0)} evidence pieces")
        lines.append("")

    # Hallucination Audit
    halluc_events = [e for e in grouped.get("evidence", [])
                     if e.get("action") == "hallucination_audit"]
    if halluc_events:
        halluc_sections = halluc_events[-1].get("sections", [])
        lines.append("### Hallucination Audit\n")
        lines.append("| Section | Ratio | Needs Rewrite | Flagged Spans |")
        lines.append("|---------|-------|---------------|---------------|")
        for s in halluc_sections:
            ratio = s.get("hallucination_ratio", 0)
            flag = "YES" if s.get("needs_rewrite") else "no"
            lines.append(f"| {s.get('title', s.get('section_id',''))[:50]} | "
                         f"{ratio:.0%} | {flag} | {s.get('flagged_spans',0)} |")
        avg = sum(s.get("hallucination_ratio", 0) for s in halluc_sections) / max(len(halluc_sections), 1)
        rewrite = sum(1 for s in halluc_sections if s.get("needs_rewrite"))
        lines.append(f"\n**Average hallucination ratio:** {avg:.0%}")
        lines.append(f"**Sections flagged for rewrite:** {rewrite}/{len(halluc_sections)}\n")

    # Evidence Conflicts
    conflict_events = [e for e in grouped.get("evidence", [])
                       if e.get("action") == "evidence_conflicts"]
    if conflict_events:
        conflicts = conflict_events[-1].get("conflicts", [])
        lines.append(f"### Evidence Conflicts ({len(conflicts)} found)\n")
        for i, c in enumerate(conflicts[:10], 1):
            lines.append(f"**Conflict {i}** (score: {c.get('score',0):.2f}, type: {c.get('type','')})")
            lines.append(f"- A: {c.get('statement_a','')[:120]}")
            lines.append(f"- B: {c.get('statement_b','')[:120]}\n")

    # Expansion History
    exp_events = [e for e in grouped.get("evidence", [])
                  if e.get("action") == "expansion_pass"]
    if exp_events:
        lines.append("### Expansion History\n")
        lines.append("| Pass | Words | Citations | Thin Sections |")
        lines.append("|------|-------|-----------|---------------|")
        for ep in exp_events:
            thin = ep.get("thin_sections", [])
            lines.append(f"| {ep.get('count','?')} | {ep.get('total_words',0):,} | "
                         f"{ep.get('total_citations',0)} | {', '.join(thin[:5]) if thin else 'none'} |")
        lines.append("")

    # Full Report Text (check existence and length)
    assembled = [e for e in grouped.get("evidence", [])
                 if e.get("action") == "report_assembled" and e.get("full_report")]
    if assembled:
        assembled_report_text = assembled[-1].get("full_report", "")
        lines.append(f"### Full Report Captured\n")
        lines.append(f"- Length: {len(assembled_report_text):,} characters")
        lines.append(f"- Sections: {assembled_report_text.count('## ')}")
        assembled_word_count = len(assembled_report_text.split())
        lines.append(f"- Word count (approx): {assembled_word_count:,}\n")
    else:
        lines.append("### Full Report\n")
        lines.append("*No full_report captured in report_assembled event.*\n")

    return "\n".join(lines)


def _section_8_quality_gates(grouped: dict) -> str:
    """Section 8: Quality Gate Audit."""
    lines = ["## 8. Quality Gate Audit\n"]

    gates = grouped.get("quality_gate", [])
    if not gates:
        lines.append("*No quality gate events captured.*\n")
        return "\n".join(lines)

    lines.append(f"**Total gate checks:** {len(gates)}\n")

    lines.append("| Gate | Passed | Actual | Threshold | Node |")
    lines.append("|------|--------|--------|-----------|------|")
    for ev in gates:
        passed = "PASS" if ev.get("passed") else "FAIL"
        gate = ev.get("gate", "?")
        actual = ev.get("actual", "N/A")
        threshold = ev.get("threshold", "N/A")
        node = ev.get("node", "")
        lines.append(f"| {gate} | {passed} | {actual} | {threshold} | {node} |")
    lines.append("")

    # Trajectory across iterations
    faith_by_iter = defaultdict(list)
    for ev in gates:
        if ev.get("gate") == "faithfulness":
            # Extract iteration from nearby context
            faith_by_iter["faithfulness"].append(ev.get("actual"))
    if faith_by_iter.get("faithfulness"):
        vals = faith_by_iter["faithfulness"]
        lines.append("### Faithfulness Trajectory\n")
        for i, val in enumerate(vals, 1):
            lines.append(f"- Check {i}: {val}")
        lines.append("")

    # Gating case determination
    iter_decisions = grouped.get("iteration_decision", [])
    for ev in iter_decisions:
        decision = ev.get("decision", "")
        if "CASE" in decision:
            lines.append(f"**Gating Case:** `{decision}` at iteration {ev.get('iteration', '?')}\n")

    # Gap Analysis (new visibility)
    gap_events = [e for e in grouped.get("evidence", [])
                  if e.get("action") == "gap_analysis_detail"]
    if gap_events:
        ga = gap_events[-1]
        lines.append("### Gap Analysis\n")
        lines.append(f"- Total evidence: {ga.get('total_evidence', 0)}")
        lines.append(f"- GOLD evidence: {ga.get('gold_count', 0)}")
        lines.append(f"- Faithfulness: {ga.get('faithfulness', 0)*100:.1f}%")
        lines.append(f"- Needs iteration: {'YES' if ga.get('needs_iteration') else 'NO'}\n")

        gaps = ga.get("gaps", [])
        if gaps:
            lines.append(f"**Gaps ({len(gaps)}):**")
            for g in gaps[:10]:
                lines.append(f"- {g if isinstance(g, str) else json.dumps(g)[:120]}")
            lines.append("")

        pc = ga.get("perspective_coverage", {})
        if pc:
            lines.append("**Perspective Coverage:**\n")
            lines.append("| Perspective | Evidence Count |")
            lines.append("|-------------|----------------|")
            for p, cnt in sorted(pc.items(), key=lambda x: -x[1]):
                lines.append(f"| {p} | {cnt} |")
            lines.append("")

    return "\n".join(lines)


def _section_9_llm_calls(grouped: dict, cost_ledger: list[dict]) -> str:
    """Section 9: LLM Call Audit."""
    lines = ["## 9. LLM Call Audit\n"]

    llm_calls = grouped.get("llm_call", [])
    if not llm_calls:
        lines.append("*No LLM calls captured in trace.*\n")
        return "\n".join(lines)

    lines.append(f"**Total LLM calls:** {len(llm_calls)}\n")

    # Aggregate stats
    total_in = sum(e.get("input_tokens", 0) for e in llm_calls)
    total_out = sum(e.get("output_tokens", 0) for e in llm_calls)
    total_dur = sum(e.get("duration_ms", 0) for e in llm_calls)
    total_cost = (total_in * INPUT_COST_PER_M / 1e6) + (total_out * OUTPUT_COST_PER_M / 1e6)

    lines.append(f"- **Total input tokens:** {total_in:,}")
    lines.append(f"- **Total output tokens:** {total_out:,}")
    lines.append(f"- **Total LLM duration:** {_fmt_dur(total_dur)}")
    lines.append(f"- **Estimated cost (from trace):** ${total_cost:.2f}\n")

    # Cross-check with cost ledger
    if cost_ledger:
        ledger_cost = sum(e.get("cost_usd", 0) for e in cost_ledger)
        lines.append(f"- **Cost ledger total:** ${ledger_cost:.2f}")
        diff = abs(total_cost - ledger_cost)
        lines.append(f"- **Discrepancy:** ${diff:.2f}\n")

    # Cost by node
    by_node: dict[str, dict] = defaultdict(lambda: {
        "calls": 0, "in_tokens": 0, "out_tokens": 0, "cost": 0.0, "dur_ms": 0,
    })
    for ev in llm_calls:
        node = ev.get("node", "unknown")
        in_tok = ev.get("input_tokens", 0)
        out_tok = ev.get("output_tokens", 0)
        cost = (in_tok * INPUT_COST_PER_M / 1e6) + (out_tok * OUTPUT_COST_PER_M / 1e6)
        by_node[node]["calls"] += 1
        by_node[node]["in_tokens"] += in_tok
        by_node[node]["out_tokens"] += out_tok
        by_node[node]["cost"] += cost
        by_node[node]["dur_ms"] += ev.get("duration_ms", 0)

    lines.append("### Cost by Node\n")
    lines.append("| Node | Calls | Input Tok | Output Tok | Cost | Duration |")
    lines.append("|------|-------|-----------|------------|------|----------|")
    for node, stats in sorted(by_node.items(), key=lambda x: -x[1]["cost"]):
        lines.append(
            f"| {node} | {stats['calls']} | {stats['in_tokens']:,} | "
            f"{stats['out_tokens']:,} | ${stats['cost']:.2f} | "
            f"{_fmt_dur(stats['dur_ms'])} |"
        )
    lines.append("")

    # By call type
    by_type = Counter(e.get("call_type", "unknown") for e in llm_calls)
    lines.append("### Calls by Type\n")
    lines.append("| Call Type | Count |")
    lines.append("|-----------|-------|")
    for call_type, count in by_type.most_common():
        lines.append(f"| {call_type} | {count} |")
    lines.append("")

    # Token efficiency
    if total_in > 0:
        efficiency = total_out / total_in
        lines.append(f"**Token efficiency (out/in):** {efficiency:.2f}\n")

    # Model distribution (new visibility - model name in llm_call)
    model_counts = Counter()
    for ev in llm_calls:
        model = ev.get("model", "unknown")
        model_counts[model] += 1

    if model_counts and len(model_counts) > 1:  # Only show if meaningful
        lines.append("### Model Distribution\n")
        lines.append("| Model | Calls |")
        lines.append("|-------|-------|")
        for model, cnt in model_counts.most_common():
            lines.append(f"| {model[:50]} | {cnt} |")
        lines.append("")

    # Full call log
    lines.append("<details><summary>Full LLM Call Log (click to expand)</summary>\n")
    for ev in llm_calls:
        lines.append(
            f"- [{ev.get('node', '')}] {ev.get('call_type', '')} "
            f"in={ev.get('input_tokens', 0):,} out={ev.get('output_tokens', 0):,} "
            f"{_fmt_dur(ev.get('duration_ms', 0))}"
        )
    lines.append("\n</details>\n")

    return "\n".join(lines)


def _section_10_anomaly_digest(anomalies: list[dict]) -> str:
    """Section 10: Anomaly Digest."""
    lines = ["## 10. Anomaly Digest\n"]

    if not anomalies:
        lines.append("*No live anomaly log available.*\n")
        return "\n".join(lines)

    lines.append(f"**Total anomalies:** {len(anomalies)}\n")

    # By severity
    by_severity = Counter(a.get("severity", "UNKNOWN") for a in anomalies)
    lines.append("### By Severity\n")
    lines.append("| Severity | Count |")
    lines.append("|----------|-------|")
    for sev, count in by_severity.most_common():
        lines.append(f"| {sev} | {count} |")
    lines.append("")

    # By category
    by_category = Counter(a.get("category", "unknown") for a in anomalies)
    lines.append("### By Category\n")
    lines.append("| Category | Count |")
    lines.append("|----------|-------|")
    for cat, count in by_category.most_common():
        lines.append(f"| {cat} | {count} |")
    lines.append("")

    # List all CRITICAL
    criticals = [a for a in anomalies if a.get("severity") == "CRITICAL"]
    if criticals:
        lines.append("### CRITICAL Anomalies\n")
        for a in criticals:
            lines.append(
                f"- **[{a.get('category', '')}]** {a.get('message', '')} "
                f"({a.get('ts', '')})"
            )
        lines.append("")

    return "\n".join(lines)


def _section_11_benchmark(
    result: Optional[dict],
    total_cost: float,
    total_time_min: float,
) -> str:
    """Section 11: Benchmark Comparison."""
    lines = ["## 11. Benchmark Comparison\n"]

    words = 0
    citations = 0
    sources = 0
    faith = 0.0
    evidence = 0

    if result:
        qm = result.get("quality_metrics", {})
        words = qm.get("total_words", 0)
        citations = qm.get("total_citations", 0)
        sources = qm.get("unique_sources", 0)
        faith = qm.get("faithfulness_score", 0.0)
        evidence = qm.get("total_evidence", 0)

    lines.append("| Metric | POLARIS | ChatGPT 5.2 Pro DR | Gemini 3 Pro DR |")
    lines.append("|--------|---------|--------------------|--------------------|")
    lines.append(f"| Words | {words:,} | -- | -- |")
    lines.append(f"| Citations | {citations} | -- | -- |")
    lines.append(f"| Unique Sources | {sources} | -- | -- |")
    lines.append(f"| Evidence Pieces | {evidence} | -- | -- |")
    lines.append(f"| Faithfulness | {faith:.1%} | -- | -- |")
    lines.append(f"| Cost | ${total_cost:.2f} | -- | -- |")
    lines.append(f"| Time (min) | {total_time_min:.1f} | -- | -- |")
    lines.append("")

    lines.append("### Scoring Rubric\n")
    lines.append("| Dimension | Weight | Score |")
    lines.append("|-----------|--------|-------|")
    lines.append(f"| D1: CoT Leakage (15%) | 15% | -- |")
    lines.append(f"| D2: Faithfulness (15%) | 15% | {faith:.1%} |")
    lines.append(f"| D3: Semantic Duplication (10%) | 10% | -- |")
    lines.append(f"| D4: Section Balance (5%) | 5% | -- |")
    lines.append(f"| D5: Citation Quality (10%) | 10% | -- |")
    lines.append(f"| D6: Bibliography (10%) | 10% | -- |")
    lines.append(f"| D7: Perspective Coverage (10%) | 10% | -- |")
    lines.append(f"| D8: Topical Relevance (10%) | 10% | -- |")
    lines.append(f"| D9: Coherence (10%) | 10% | -- |")
    lines.append(f"| D10: Pipeline Integrity (5%) | 5% | -- |")
    lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _fmt_ts(ts: str) -> str:
    """Format ISO timestamp to HH:MM:SS."""
    if not ts:
        return "--"
    try:
        dt = datetime.fromisoformat(ts)
        return dt.strftime("%H:%M:%S")
    except (ValueError, TypeError):
        return ts[:19]


def _fmt_dur(ms) -> str:
    """Format milliseconds as human-readable."""
    if ms is None or ms == 0:
        return "--"
    ms = float(ms)
    if ms < 1000:
        return f"{ms:.0f}ms"
    if ms < 60000:
        return f"{ms / 1000:.1f}s"
    return f"{ms / 60000:.1f}min"


def _extract_domain(url: str) -> str:
    """Extract domain from URL."""
    try:
        from urllib.parse import urlparse
        parsed = urlparse(url)
        return parsed.netloc or ""
    except Exception:
        return ""


def _jaccard_words(text_a: str, text_b: str) -> float:
    """Compute Jaccard similarity on word sets."""
    if not text_a or not text_b:
        return 0.0
    words_a = set(text_a.lower().split())
    words_b = set(text_b.lower().split())
    if not words_a or not words_b:
        return 0.0
    intersection = words_a & words_b
    union = words_a | words_b
    return len(intersection) / len(union) if union else 0.0


# ---------------------------------------------------------------------------
# Main forensic audit
# ---------------------------------------------------------------------------
def run_forensic_audit(
    vector_id: str,
    trace_path: Optional[Path] = None,
    result_path: Optional[Path] = None,
    report_path: Optional[Path] = None,
) -> tuple[str, dict]:
    """Run the full 11-section forensic audit.

    Returns (markdown_report, json_summary).
    """
    # Auto-discover files
    if trace_path is None:
        trace_path = Path(f"logs/pg_trace_{vector_id}.jsonl")
    if result_path is None:
        result_path = Path(f"outputs/polaris_graph/{vector_id}.json")
    if report_path is None:
        report_path = Path(f"outputs/polaris_graph/{vector_id}_report.md")

    cost_ledger_path = Path(os.getenv("PG_COST_LEDGER_PATH", "logs/pg_cost_ledger.jsonl"))
    anomaly_path = Path(os.getenv("PG_LIVE_ANOMALY_LOG", "logs/live_anomaly_log.jsonl"))

    logger.info("=" * 60)
    logger.info("POLARIS Forensic Audit: %s", vector_id)
    logger.info("Trace:   %s (%s)", trace_path, "exists" if trace_path.exists() else "MISSING")
    logger.info("Result:  %s (%s)", result_path, "exists" if result_path.exists() else "MISSING")
    logger.info("Report:  %s (%s)", report_path, "exists" if report_path.exists() else "MISSING")
    logger.info("Ledger:  %s (%s)", cost_ledger_path, "exists" if cost_ledger_path.exists() else "MISSING")
    logger.info("Anomaly: %s (%s)", anomaly_path, "exists" if anomaly_path.exists() else "MISSING")
    logger.info("=" * 60)

    # Load data
    trace_events = _load_jsonl(trace_path)
    grouped = _group_events(trace_events)
    result = _load_json(result_path)
    report_text = _load_text(report_path)
    all_cost_entries = _load_jsonl(cost_ledger_path)
    anomalies = _load_jsonl(anomaly_path)

    # Filter cost ledger to this run's time window (BUG-3 fix)
    cost_ledger = _filter_cost_ledger(all_cost_entries, trace_events)

    logger.info("Loaded: %d trace events, %d/%d cost entries (filtered), %d anomalies",
                len(trace_events), len(cost_ledger), len(all_cost_entries), len(anomalies))

    # Compute aggregate metrics for summary
    total_cost_trace = 0.0
    total_time_ms = 0.0
    for ev in trace_events:
        if ev.get("type") == "llm_call":
            in_tok = ev.get("input_tokens", 0)
            out_tok = ev.get("output_tokens", 0)
            total_cost_trace += (in_tok * INPUT_COST_PER_M / 1e6) + (out_tok * OUTPUT_COST_PER_M / 1e6)
        if ev.get("type") == "node_end" and ev.get("duration_ms"):
            total_time_ms += ev["duration_ms"]

    # Use cost ledger as primary source (more accurate than trace token math)
    total_cost_ledger = sum(e.get("cost_usd", 0) for e in cost_ledger)
    total_cost = max(total_cost_trace, total_cost_ledger)

    total_time_min = total_time_ms / 60000

    # Build sections
    sections_md = []
    sections_md.append(f"# POLARIS Forensic Audit: {vector_id}\n")
    sections_md.append(f"*Generated: {datetime.now(timezone.utc).isoformat()}*\n")
    sections_md.append(f"*Trace events: {len(trace_events)} | "
                       f"Cost: ${total_cost:.2f} | "
                       f"Time: {total_time_min:.1f}min*\n")
    sections_md.append("---\n")

    sections_md.append(_section_1_timeline(trace_events, grouped))
    sections_md.append(_section_2_planning(grouped))
    sections_md.append(_section_3_search_fetch(grouped))
    sections_md.append(_section_4_storm(grouped))
    sections_md.append(_section_5_evidence(result, grouped))
    sections_md.append(_section_6_verification(result, grouped))
    sections_md.append(_section_7_report_text(report_text, result, grouped))
    sections_md.append(_section_8_quality_gates(grouped))
    sections_md.append(_section_9_llm_calls(grouped, cost_ledger))
    sections_md.append(_section_10_anomaly_digest(anomalies))
    sections_md.append(_section_11_benchmark(result, total_cost, total_time_min))

    full_report = "\n".join(sections_md)

    # Build JSON summary
    json_summary = {
        "vector_id": vector_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "trace_file": str(trace_path),
        "result_file": str(result_path),
        "report_file": str(report_path),
        "total_trace_events": len(trace_events),
        "event_type_counts": {k: len(v) for k, v in grouped.items()},
        "total_cost_usd": round(total_cost, 4),
        "total_time_min": round(total_time_min, 1),
        "total_anomalies": len(anomalies),
        "anomaly_by_severity": dict(Counter(a.get("severity", "?") for a in anomalies)),
        "anomaly_by_category": dict(Counter(a.get("category", "?") for a in anomalies)),
    }

    if result:
        qm = result.get("quality_metrics", {})
        json_summary["quality_metrics"] = {
            "total_words": qm.get("total_words", 0),
            "total_citations": qm.get("total_citations", 0),
            "unique_sources": qm.get("unique_sources", 0),
            "total_evidence": qm.get("total_evidence", 0),
            "faithfulness_score": qm.get("faithfulness_score", 0.0),
        }

    return full_report, json_summary


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(
        description="POLARIS Post-Run Forensic Audit"
    )
    parser.add_argument(
        "--vector-id",
        type=str,
        required=True,
        help="Vector ID (e.g., PG_TEST_059)",
    )
    parser.add_argument(
        "--trace",
        type=str,
        default=None,
        help="Override path to trace JSONL",
    )
    parser.add_argument(
        "--result",
        type=str,
        default=None,
        help="Override path to result JSON",
    )
    parser.add_argument(
        "--report",
        type=str,
        default=None,
        help="Override path to report markdown",
    )
    args = parser.parse_args()

    trace_p = Path(args.trace) if args.trace else None
    result_p = Path(args.result) if args.result else None
    report_p = Path(args.report) if args.report else None

    full_report, json_summary = run_forensic_audit(
        args.vector_id, trace_p, result_p, report_p,
    )

    # Write outputs
    out_md = Path(f"outputs/forensic_report_{args.vector_id}.md")
    out_json = Path(f"outputs/forensic_report_{args.vector_id}.json")
    out_md.parent.mkdir(parents=True, exist_ok=True)

    with open(out_md, "w", encoding="utf-8") as f:
        f.write(full_report)

    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(json_summary, f, indent=2, default=str)

    word_count = len(full_report.split())
    logger.info("=" * 60)
    logger.info("Forensic audit complete: %s", args.vector_id)
    logger.info("Report: %s (%d words)", out_md, word_count)
    logger.info("JSON:   %s", out_json)
    logger.info("=" * 60)

    print(f"\nForensic report written:")
    print(f"  Markdown: {out_md} ({word_count:,} words)")
    print(f"  JSON:     {out_json}")
    print(f"  Cost:     ${json_summary['total_cost_usd']:.2f}")
    print(f"  Time:     {json_summary['total_time_min']:.1f}min")
    print(f"  Events:   {json_summary['total_trace_events']}")
    print(f"  Anomalies: {json_summary['total_anomalies']}")


if __name__ == "__main__":
    main()
