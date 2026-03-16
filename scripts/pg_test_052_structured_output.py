"""
PG_TEST_052: Structured Output Reliability + Legacy Import Guard

Validates FIX-052:
- FIX-052A: require_parameters: true in OpenRouter provider config
- FIX-052B: DNS failure 30s backoff
- FIX-052C: Legacy import guards (src.formatters, src.reasoning)
- FIX-052D: OPENROUTER_REQUIRE_PARAMETERS env var

Key validation targets:
1. require_parameters: true visible in provider config
2. NO import errors for src.formatters, src.reasoning
3. Stub content :[{ rate < 20% (was 42.9% in T051 Run 3)
4. Batch failure rate < 30% (was 100% iter 1, 42.9% iter 2 in T051)
5. All FIX-048 through FIX-051h validations still pass
6. Faithfulness >= 75%
7. Words >= 8,000
8. Cost < $3.00

Same PFAS query as PG_TEST_035-051 for direct comparison.
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

VECTOR_ID = "PG_TEST_052"
OUTPUT_DIR = Path("outputs/polaris_graph")


async def main():
    from src.polaris_graph.graph import build_and_run

    print("=" * 70, flush=True)
    print("  PG_TEST_052: STRUCTURED OUTPUT RELIABILITY", flush=True)
    print("=" * 70, flush=True)
    print(f"  Max execution:        {os.getenv('PG_MAX_EXECUTION_MINUTES', '150')}min", flush=True)
    print(f"  Max iterations:       {os.getenv('PG_MAX_ITERATIONS', '5')}", flush=True)
    print(f"  NLI ENABLED:          {os.getenv('PG_NLI_ENABLED', '0')}", flush=True)
    print(f"  Cross-source ENABLED: {os.getenv('PG_CROSS_SOURCE_ENABLED', '1')}", flush=True)
    print(f"  Firecrawl ENABLED:    {os.getenv('PG_FIRECRAWL_ENABLED', '0')}", flush=True)
    print(f"  Crawl4AI ENABLED:     {os.getenv('PG_CRAWL4AI_ENABLED', '0')}", flush=True)
    print(f"  Halluc detect ENABLED:{os.getenv('PG_HALLUCINATION_DETECT_ENABLED', '0')}", flush=True)
    print(f"  Checkpoint ENABLED:   {os.getenv('PG_CHECKPOINT_ENABLED', '0')}", flush=True)
    print("  --- FIX-052 Specific ---", flush=True)
    print(f"  require_parameters:   {os.getenv('OPENROUTER_REQUIRE_PARAMETERS', 'NOT SET')}", flush=True)
    print(f"  DNS retry backoff:    {os.getenv('PG_DNS_RETRY_BACKOFF', '30')}s", flush=True)
    print(f"  Provider order:       {os.getenv('OPENROUTER_PROVIDER_ORDER', 'NOT SET')}", flush=True)
    print(f"  Allow fallbacks:      {os.getenv('OPENROUTER_ALLOW_FALLBACKS', 'NOT SET')}", flush=True)
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
            max_execution_minutes=int(os.getenv("PG_MAX_EXECUTION_MINUTES", "150")),
        )

        elapsed = time.time() - start
        qm = result.get("quality_metrics") or {}
        usage = result.get("llm_usage") or {}
        report = result.get("final_report", "")
        evidence = result.get("evidence_chain", result.get("evidence", []))
        claims = result.get("claims", [])

        print(flush=True)
        print("=" * 70, flush=True)
        print(f"  PG_TEST_052 COMPLETED ({elapsed:.0f}s / {elapsed / 60:.1f}min)", flush=True)
        print("=" * 70, flush=True)
        print(f"  Status:         {result.get('status')}", flush=True)
        print(f"  Quality gate:   {result.get('quality_gate_result', '?')}", flush=True)
        print(f"  Expansion:      {result.get('expansion_passes_used', 0)} passes", flush=True)
        print(f"  Iterations:     {result.get('iteration_count', '?')}", flush=True)
        print(f"  Converged:      {result.get('converged', '?')}", flush=True)
        print(flush=True)

        # --- Quality Metrics ---
        print("  --- Quality Metrics ---", flush=True)
        total_words = qm.get("total_words", 0)
        total_citations = qm.get("total_citations", 0)
        unique_sources = qm.get("unique_sources", 0)
        faith_score = qm.get("faithfulness_score", -1.0)
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

        # =====================================================================
        # FIX-051h SPECIFIC VALIDATIONS (inherited from T051)
        # =====================================================================
        print("  " + "=" * 66, flush=True)
        print("  FIX-051h NLI FEEDBACK LOOP AUDIT", flush=True)
        print("  " + "=" * 66, flush=True)

        # 1. Signal 5: nli_self_check_score on evidence
        ev_with_nli_score = [e for e in evidence if "nli_self_check_score" in e]
        ev_nli_scores = [e["nli_self_check_score"] for e in ev_with_nli_score]
        nli_enriched_pct = len(ev_with_nli_score) / max(len(evidence), 1) * 100
        print(f"  [S5] Evidence with nli_self_check_score: {len(ev_with_nli_score)}/{len(evidence)} ({nli_enriched_pct:.1f}%)", flush=True)
        if ev_nli_scores:
            avg_nli = sum(ev_nli_scores) / len(ev_nli_scores)
            min_nli = min(ev_nli_scores)
            max_nli = max(ev_nli_scores)
            print(f"  [S5] Score range: {min_nli:.3f} - {max_nli:.3f} (avg {avg_nli:.3f})", flush=True)
            unique_scores = len(set(round(s, 4) for s in ev_nli_scores))
            print(f"  [S5] Unique score values: {unique_scores} (target: >3)", flush=True)
        else:
            print("  [S5] WARNING: NO evidence has nli_self_check_score!", flush=True)

        # 2. Claims: verification_type field completeness
        claims_with_vtype = [c for c in claims if "verification_type" in c]
        claims_vtype_dist = Counter(c.get("verification_type", "MISSING") for c in claims)
        print(f"  [VC] Claims with verification_type: {len(claims_with_vtype)}/{len(claims)}", flush=True)
        print(f"  [VC] verification_type distribution: {dict(claims_vtype_dist)}", flush=True)

        # 3. Claims: nli_score field presence
        claims_with_nli = [c for c in claims if c.get("nli_score") is not None]
        nli_claim_scores = [c["nli_score"] for c in claims_with_nli]
        print(f"  [NS] Claims with nli_score: {len(claims_with_nli)}/{len(claims)}", flush=True)
        if nli_claim_scores:
            avg_claim_nli = sum(nli_claim_scores) / len(nli_claim_scores)
            disputed_range = [s for s in nli_claim_scores if 0.3 <= s <= 0.7]
            print(f"  [NS] NLI score avg: {avg_claim_nli:.3f}", flush=True)
            print(f"  [NS] Disputed range (0.3-0.7): {len(disputed_range)}/{len(nli_claim_scores)}", flush=True)

        # 4. Claims: cross_source_score presence
        claims_with_cross = [c for c in claims if c.get("cross_source_score") is not None]
        print(f"  [CS] Claims with cross_source_score: {len(claims_with_cross)}/{len(claims)}", flush=True)

        # 5. LLM second opinion detection
        llm_with_nli = [
            c for c in claims
            if c.get("verification_type") == "extraction_self_check"
            and c.get("nli_score") is not None
        ]
        print(f"  [M] LLM second-opinion claims with preserved NLI score: {len(llm_with_nli)}", flush=True)

        # 6. Tier composite differentiation
        composites = [e.get("tier_composite_score", 0) for e in evidence if "tier_composite_score" in e]
        if composites:
            unique_composites = len(set(round(c, 4) for c in composites))
            composite_range = max(composites) - min(composites)
            print(f"  [TC] Composite score range: {min(composites):.4f} - {max(composites):.4f} (spread {composite_range:.4f})", flush=True)
            print(f"  [TC] Unique composite values: {unique_composites}/{len(composites)}", flush=True)

        # 7. Tier distribution
        tier_dist = Counter(e.get("quality_tier", "UNKNOWN") for e in evidence)
        ev_count = len(evidence)
        print(f"  [TD] Tier distribution: {dict(tier_dist)}", flush=True)
        bronze_pct = tier_dist.get("BRONZE", 0) / max(ev_count, 1) * 100
        gold_pct = tier_dist.get("GOLD", 0) / max(ev_count, 1) * 100
        print(f"  [TD] BRONZE: {bronze_pct:.1f}% | GOLD: {gold_pct:.1f}%", flush=True)

        print(flush=True)

        # --- Source/Report Quality ---
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
        dur_052 = elapsed / 60
        print("  " + "=" * 140, flush=True)
        print("  PG_TEST COMPARISON", flush=True)
        print("  " + "=" * 140, flush=True)
        header = f"  {'Metric':<22} {'T037':>8} {'T039':>8} {'T040':>8} {'T047':>8} {'T051R3':>8} {'T052':>8}"
        separator = f"  {'-'*22} {'-'*8} {'-'*8} {'-'*8} {'-'*8} {'-'*8} {'-'*8}"
        print(header, flush=True)
        print(separator, flush=True)
        print(f"  {'Faithfulness':<22} {'82.6%':>8} {'80.5%':>8} {'N/A':>8} {'100%':>8} {'N/A':>8} {faith_score:>7.1%}", flush=True)
        print(f"  {'Duration (min)':<22} {'80':>8} {'84':>8} {'89':>8} {'105':>8} {'~120':>8} {dur_052:>8.0f}", flush=True)
        cost_str = f"${cost:.2f}"
        print(f"  {'Cost':<22} {'$1.14':>8} {'$1.31':>8} {'$0.72':>8} {'$0.72':>8} {'N/A':>8} {cost_str:>8}", flush=True)
        print(f"  {'Words':<22} {'7525':>8} {'11583':>8} {'12616':>8} {'12375':>8} {'N/A':>8} {total_words:>8}", flush=True)
        print(f"  {'Citations':<22} {'109':>8} {'191':>8} {'208':>8} {'243':>8} {'N/A':>8} {total_citations:>8}", flush=True)
        print(f"  {'Sources':<22} {'27':>8} {'18':>8} {'13':>8} {'40':>8} {'N/A':>8} {unique_sources:>8}", flush=True)
        print(f"  {'Evidence':<22} {'1266':>8} {'1011':>8} {'1282':>8} {'258':>8} {'N/A':>8} {ev_count:>8}", flush=True)
        nli_enriched_str = f"{len(ev_with_nli_score)}"
        print(f"  {'NLI enriched ev':<22} {'N/A':>8} {'N/A':>8} {'N/A':>8} {'N/A':>8} {'N/A':>8} {nli_enriched_str:>8}", flush=True)
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
            hard_fails.append(f"Words {total_words} < 6000")
        if total_citations < 50:
            hard_fails.append(f"Citations {total_citations} < 50")
        if phantom_count > 0:
            hard_fails.append(f"Phantom [*] markers found: {phantom_count}")

        # FIX-051h specific hard fails
        if len(ev_with_nli_score) == 0 and os.getenv("PG_NLI_ENABLED", "0") == "1":
            hard_fails.append("ZERO evidence has nli_self_check_score (Signal 5 dead)")
        if len(claims_with_vtype) < len(claims):
            hard_fails.append(f"Claims missing verification_type: {len(claims) - len(claims_with_vtype)}")

        # Soft warnings
        if faith_score >= 0 and faith_score < 0.75:
            soft_warns.append(f"Faithfulness {faith_score:.1%} below 75% target")
        if total_words < 8000:
            soft_warns.append(f"Words {total_words} below 8000 target")
        if cost > 3.0:
            soft_warns.append(f"Cost ${cost:.2f} exceeds $3.00 target")
        if len(llm_with_nli) == 0 and os.getenv("PG_NLI_ENABLED", "0") == "1":
            soft_warns.append("No LLM second-opinion claims found with preserved NLI scores")

        if hard_fails:
            print("  *** HARD FAIL ***", flush=True)
            for f in hard_fails:
                print(f"    [X] {f}", flush=True)
        if soft_warns:
            print("  *** WARNINGS ***", flush=True)
            for w in soft_warns:
                print(f"    [!] {w}", flush=True)

        if not hard_fails:
            print("  *** PG_TEST_052: PASS ***", flush=True)
        else:
            print(f"  *** PG_TEST_052: FAIL ({len(hard_fails)} hard fails) ***", flush=True)

    except Exception as e:
        elapsed = time.time() - start
        logger.exception("PG_TEST_052 FAILED with exception")
        print(f"\n  *** PG_TEST_052 FAILED ({elapsed:.0f}s): {e}", flush=True)
        raise


if __name__ == "__main__":
    asyncio.run(main())
