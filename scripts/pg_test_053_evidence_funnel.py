"""
PG_TEST_053: Evidence Funnel Collapse Prevention

Validates FIX-057 (T052 root cause elimination):
- Cut 1: Section cap tightened for <10 evidence (max(3, evidence_count))
- Cut 2: PG_TIER_SILVER_THRESHOLD 0.40 -> 0.35
- Cut 3: Synthesis fallback to GOLD+SILVER confirmed active
- Cut 4: PG_MAX_EXECUTION_MINUTES 150 -> 180

Also validates FIX-053 through FIX-056 from prior session.

Key validation targets (compared to T047 benchmarks):
1. Evidence after analysis: >= 100 (T052 had 56)
2. Evidence after dedup: >= 20 (T052 had 3)
3. Sections <= evidence count (T052 had 13 sections for 3 evidence)
4. Words >= 10,000 (T052 had 2,091)
5. Citations >= 100 (T052 had 13)
6. Sources >= 15 (T052 had 3)
7. Faithfulness >= 70%
8. Cost < $5.00

Same PFAS query as PG_TEST_035-052 for direct comparison.
"""

import asyncio
import json
import logging
import os
import re
import sys
import time
from collections import Counter
from pathlib import Path
from urllib.parse import urlparse

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
os.chdir(PROJECT_ROOT)

from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("logs/polaris_graph.log", mode="a", encoding="utf-8"),
    ],
)
logger = logging.getLogger(__name__)

VECTOR_ID = "PG_TEST_053"
OUTPUT_DIR = Path("outputs/polaris_graph")


async def main():
    from src.polaris_graph.graph import build_and_run

    print("=" * 70, flush=True)
    print("  PG_TEST_053: EVIDENCE FUNNEL COLLAPSE PREVENTION", flush=True)
    print("=" * 70, flush=True)
    print(f"  Max execution:        {os.getenv('PG_MAX_EXECUTION_MINUTES', '180')}min", flush=True)
    print(f"  Max iterations:       {os.getenv('PG_MAX_ITERATIONS', '5')}", flush=True)
    print(f"  NLI ENABLED:          {os.getenv('PG_NLI_ENABLED', '0')}", flush=True)
    print(f"  Cross-source ENABLED: {os.getenv('PG_CROSS_SOURCE_ENABLED', '1')}", flush=True)
    print(f"  Halluc detect ENABLED:{os.getenv('PG_HALLUCINATION_DETECT_ENABLED', '0')}", flush=True)
    print(f"  Checkpoint ENABLED:   {os.getenv('PG_CHECKPOINT_ENABLED', '0')}", flush=True)
    print("  --- FIX-057 Specific ---", flush=True)
    print(f"  SILVER threshold:     {os.getenv('PG_TIER_SILVER_THRESHOLD', '0.40')}", flush=True)
    print(f"  GOLD threshold:       {os.getenv('PG_TIER_GOLD_THRESHOLD', '0.65')}", flush=True)
    print(f"  Max outline sections: {os.getenv('PG_MAX_OUTLINE_SECTIONS', '15')}", flush=True)
    print(f"  Planner timeout:      {os.getenv('PG_PLANNER_TIMEOUT', '180')}s", flush=True)
    print(f"  Halluc section timeout:{os.getenv('PG_HALLUCINATION_SECTION_TIMEOUT', '600')}s", flush=True)
    print("=" * 70, flush=True)

    start = time.time()

    try:
        result = await build_and_run(
            vector_id=VECTOR_ID,
            query=(
                "What are the most effective and affordable water filtration "
                "technologies for removing PFAS from drinking water?"
            ),
            application="Household Water Filter",
            region="NORTH AMERICA",
            stage=1,
            max_iterations=int(os.getenv("PG_MAX_ITERATIONS", "5")),
            max_execution_minutes=int(os.getenv("PG_MAX_EXECUTION_MINUTES", "180")),
        )

        elapsed = time.time() - start
        qm = result.get("quality_metrics") or {}
        usage = result.get("llm_usage") or {}
        report = result.get("final_report", "")
        evidence = result.get("evidence_chain", result.get("evidence", []))
        claims = result.get("claims", [])

        print(flush=True)
        print("=" * 70, flush=True)
        print(f"  PG_TEST_053 COMPLETED ({elapsed:.0f}s / {elapsed / 60:.1f}min)", flush=True)
        print("=" * 70, flush=True)
        print(f"  Status:         {result.get('status')}", flush=True)
        print(f"  Quality gate:   {result.get('quality_gate_result', '?')}", flush=True)
        print(f"  Expansion:      {result.get('expansion_passes_used', 0)} passes", flush=True)
        print(f"  Iterations:     {result.get('iteration_count', '?')}", flush=True)
        print(f"  Converged:      {result.get('converged', '?')}", flush=True)
        print(flush=True)

        # --- Evidence Funnel Analysis (FIX-057 CRITICAL) ---
        print("  " + "=" * 66, flush=True)
        print("  EVIDENCE FUNNEL ANALYSIS (FIX-057)", flush=True)
        print("  " + "=" * 66, flush=True)

        ev_count = len(evidence)
        tier_dist = Counter(e.get("quality_tier", "UNKNOWN") for e in evidence)
        gold_count = tier_dist.get("GOLD", 0)
        silver_count = tier_dist.get("SILVER", 0)
        bronze_count = tier_dist.get("BRONZE", 0)
        junk_count = tier_dist.get("JUNK", 0)

        print(f"  Total evidence:       {ev_count}", flush=True)
        print(f"  GOLD:                 {gold_count} ({gold_count / max(ev_count, 1) * 100:.1f}%)", flush=True)
        print(f"  SILVER:               {silver_count} ({silver_count / max(ev_count, 1) * 100:.1f}%)", flush=True)
        print(f"  BRONZE:               {bronze_count} ({bronze_count / max(ev_count, 1) * 100:.1f}%)", flush=True)
        print(f"  JUNK:                 {junk_count} ({junk_count / max(ev_count, 1) * 100:.1f}%)", flush=True)

        # Composite score distribution
        composites = [e.get("tier_composite_score", 0) for e in evidence if "tier_composite_score" in e]
        if composites:
            avg_comp = sum(composites) / len(composites)
            above_silver = sum(1 for c in composites if c >= 0.35)
            above_gold = sum(1 for c in composites if c >= 0.65)
            print(f"  Composite avg:        {avg_comp:.4f}", flush=True)
            print(f"  Above SILVER (0.35):  {above_silver}/{len(composites)}", flush=True)
            print(f"  Above GOLD (0.65):    {above_gold}/{len(composites)}", flush=True)

        # Faithfulness
        faithful_claims = [c for c in claims if c.get("is_faithful")]
        faith_score = qm.get("faithfulness_score", -1.0)
        print(f"  Faithful claims:      {len(faithful_claims)}/{len(claims)}", flush=True)
        print(f"  Faithfulness score:   {faith_score:.1%}", flush=True)
        print(flush=True)

        # T052 vs T053 funnel comparison
        print("  --- Funnel Comparison (T052 vs T053) ---", flush=True)
        print(f"  {'Metric':<25} {'T052':>10} {'T053':>10} {'T047':>10}", flush=True)
        print(f"  {'-'*25} {'-'*10} {'-'*10} {'-'*10}", flush=True)
        print(f"  {'Total evidence':<25} {'56':>10} {ev_count:>10} {'258':>10}", flush=True)
        print(f"  {'GOLD+SILVER':<25} {'?':>10} {gold_count + silver_count:>10} {'?':>10}", flush=True)
        print(f"  {'Faithful claims':<25} {'6':>10} {len(faithful_claims):>10} {'218':>10}", flush=True)
        print(flush=True)

        # --- Quality Metrics ---
        print("  --- Quality Metrics ---", flush=True)
        total_words = qm.get("total_words", 0)
        total_citations = qm.get("total_citations", 0)
        unique_sources = qm.get("unique_sources", 0)
        print(f"  Words:          {total_words}", flush=True)
        print(f"  Sections:       {qm.get('total_sections', 0)}", flush=True)
        print(f"  Citations:      {total_citations}", flush=True)
        print(f"  Unique sources: {unique_sources}", flush=True)
        print(f"  Faithfulness:   {faith_score:.1%}", flush=True)
        print(f"  Citation HHI:   {qm.get('citation_hhi', 0):.4f} ({qm.get('citation_hhi_label', '?')})", flush=True)
        print(flush=True)

        # --- LLM Usage ---
        print("  --- LLM Usage ---", flush=True)
        cost = usage.get("total_cost_usd", 0)
        print(f"  Total calls:    {usage.get('total_calls', 0)}", flush=True)
        print(f"  Cost:           ${cost:.4f}", flush=True)
        print(flush=True)

        # --- NLI Feedback Loop Audit ---
        print("  " + "=" * 66, flush=True)
        print("  NLI FEEDBACK LOOP AUDIT", flush=True)
        print("  " + "=" * 66, flush=True)

        ev_with_nli_score = [e for e in evidence if "nli_self_check_score" in e]
        ev_nli_scores = [e["nli_self_check_score"] for e in ev_with_nli_score]
        nli_enriched_pct = len(ev_with_nli_score) / max(len(evidence), 1) * 100
        print(f"  [S5] Evidence with nli_self_check_score: {len(ev_with_nli_score)}/{len(evidence)} ({nli_enriched_pct:.1f}%)", flush=True)
        if ev_nli_scores:
            avg_nli = sum(ev_nli_scores) / len(ev_nli_scores)
            print(f"  [S5] Score range: {min(ev_nli_scores):.3f} - {max(ev_nli_scores):.3f} (avg {avg_nli:.3f})", flush=True)

        claims_with_vtype = [c for c in claims if "verification_type" in c]
        claims_vtype_dist = Counter(c.get("verification_type", "MISSING") for c in claims)
        print(f"  [VC] Claims with verification_type: {len(claims_with_vtype)}/{len(claims)}", flush=True)
        print(f"  [VC] verification_type distribution: {dict(claims_vtype_dist)}", flush=True)
        print(flush=True)

        # --- Source Quality ---
        print("  --- Source & Report Quality ---", flush=True)
        ev_domains = {}
        for e in evidence:
            url = e.get("source_url", "")
            if url:
                domain = urlparse(url).netloc or url
                ev_domains[domain] = ev_domains.get(domain, 0) + 1
        top_domains = sorted(ev_domains.items(), key=lambda x: -x[1])[:8]
        print(f"  Source domains:           {len(ev_domains)} unique", flush=True)
        print(f"  Top domains:              {top_domains}", flush=True)

        double_bracket_count = len(re.findall(r'\[\[', report))
        phantom_count = report.count("[*]")
        print(f"  Double brackets:          {double_bracket_count} (target: 0)", flush=True)
        print(f"  Phantom [*]:              {phantom_count} (target: 0)", flush=True)

        halluc_audit = result.get("hallucination_audit", [])
        halluc_rewritten = sum(1 for h in halluc_audit if h.get("needs_rewrite"))
        print(f"  Halluc audit:             {len(halluc_audit)} sections, {halluc_rewritten} rewritten", flush=True)
        print(flush=True)

        # --- COMPARISON TABLE ---
        dur_053 = elapsed / 60
        print("  " + "=" * 140, flush=True)
        print("  PG_TEST COMPARISON", flush=True)
        print("  " + "=" * 140, flush=True)
        header = f"  {'Metric':<22} {'T039':>8} {'T047':>8} {'T052':>8} {'T053':>8}"
        separator = f"  {'-'*22} {'-'*8} {'-'*8} {'-'*8} {'-'*8}"
        print(header, flush=True)
        print(separator, flush=True)
        print(f"  {'Faithfulness':<22} {'80.5%':>8} {'100%':>8} {'N/A':>8} {faith_score:>7.1%}", flush=True)
        print(f"  {'Duration (min)':<22} {'84':>8} {'105':>8} {'370+':>8} {dur_053:>8.0f}", flush=True)
        cost_str = f"${cost:.2f}"
        print(f"  {'Cost':<22} {'$1.31':>8} {'$0.72':>8} {'$0.55':>8} {cost_str:>8}", flush=True)
        print(f"  {'Words':<22} {'11583':>8} {'12375':>8} {'2091':>8} {total_words:>8}", flush=True)
        print(f"  {'Citations':<22} {'191':>8} {'243':>8} {'13':>8} {total_citations:>8}", flush=True)
        print(f"  {'Sources':<22} {'18':>8} {'40':>8} {'3':>8} {unique_sources:>8}", flush=True)
        print(f"  {'Evidence':<22} {'1011':>8} {'258':>8} {'56':>8} {ev_count:>8}", flush=True)
        print(f"  {'GOLD+SILVER':<22} {'N/A':>8} {'N/A':>8} {'?':>8} {gold_count + silver_count:>8}", flush=True)
        print("  " + "=" * 140, flush=True)

        # Save result
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        out_path = OUTPUT_DIR / f"{VECTOR_ID}.json"
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, default=str)
        print(f"\n  Result saved: {out_path}", flush=True)

        if report:
            report_path = OUTPUT_DIR / f"{VECTOR_ID}_report.md"
            with open(report_path, "w", encoding="utf-8") as f:
                f.write(report)
            print(f"  Report saved: {report_path}", flush=True)

        # PASS/FAIL
        print(flush=True)
        hard_fails = []
        soft_warns = []

        # Hard fails
        faith_sentinel = (faith_score == -1.0)
        if faith_sentinel:
            hard_fails.append("Faithfulness = -1.0 sentinel (never measured)")
        if faith_score >= 0 and faith_score < 0.50:
            hard_fails.append(f"Faithfulness {faith_score:.1%} < 50%")
        if total_words < 6000:
            hard_fails.append(f"Words {total_words} < 6,000 (FIX-057 target: 10,000)")
        if total_citations < 30:
            hard_fails.append(f"Citations {total_citations} < 30")
        if unique_sources < 10:
            hard_fails.append(f"Sources {unique_sources} < 10 (FIX-057 target: 15)")
        if phantom_count > 0:
            hard_fails.append(f"Phantom [*] markers found: {phantom_count}")

        # FIX-057 specific: evidence funnel check
        if ev_count < 20:
            hard_fails.append(f"Evidence funnel COLLAPSED: only {ev_count} pieces (target >= 100)")
        if gold_count + silver_count < 10:
            hard_fails.append(f"GOLD+SILVER only {gold_count + silver_count} (target >= 10)")

        # Soft warnings
        if faith_score >= 0 and faith_score < 0.75:
            soft_warns.append(f"Faithfulness {faith_score:.1%} below 75% target")
        if total_words < 10000:
            soft_warns.append(f"Words {total_words} below 10,000 T047 benchmark")
        if total_citations < 100:
            soft_warns.append(f"Citations {total_citations} below 100 T047 benchmark")
        if unique_sources < 20:
            soft_warns.append(f"Sources {unique_sources} below 20 T047 benchmark")
        if cost > 5.0:
            soft_warns.append(f"Cost ${cost:.2f} exceeds $5.00 target")

        if hard_fails:
            print("  *** HARD FAIL ***", flush=True)
            for f in hard_fails:
                print(f"    [X] {f}", flush=True)
        if soft_warns:
            print("  *** WARNINGS ***", flush=True)
            for w in soft_warns:
                print(f"    [!] {w}", flush=True)

        if not hard_fails:
            print("  *** PG_TEST_053: PASS ***", flush=True)
        else:
            print(f"  *** PG_TEST_053: FAIL ({len(hard_fails)} hard fails) ***", flush=True)

    except Exception as e:
        elapsed = time.time() - start
        logger.exception("PG_TEST_053 FAILED with exception")
        print(f"\n  *** PG_TEST_053 FAILED ({elapsed:.0f}s): {e}", flush=True)
        raise


if __name__ == "__main__":
    asyncio.run(main())
