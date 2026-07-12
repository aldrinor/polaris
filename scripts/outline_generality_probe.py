#!/usr/bin/env python3
"""STEP 2 generality probe: call ONLY the outline SEED (_call_outline, one LLM call) on THREE
different-domain evidence sets and print the resulting section plan. Proves the structure fix is
TOPIC-DRIVEN and GENERAL (a topic-appropriate skeleton on AI/labor, medical, and finance) WITHOUT
running the full/expensive section-writing pipeline and WITHOUT tuning to any benchmark task.

Run:
    set -a && . ./.env && set +a
    PG_FACET_OUTLINE=1 PG_FACET_OUTLINE_SKELETON=1 \
        python scripts/outline_generality_probe.py
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def _ev(eid, title, stmt, tier="T1"):
    return {"evidence_id": eid, "title": title, "statement": stmt, "tier": tier}


# --- Domain 2: MEDICAL (gut microbiota / intestinal function) — small synthetic pool ------------
MEDICAL = [
    _ev("gm_scfa_barrier", "Short-chain fatty acids and gut barrier integrity",
        "Butyrate produced by commensal bacteria strengthens the intestinal epithelial barrier and reduces permeability."),
    _ev("gm_dysbiosis_ibd", "Dysbiosis in inflammatory bowel disease",
        "Reduced microbial diversity and loss of Faecalibacterium prausnitzii are associated with Crohn's disease and ulcerative colitis."),
    _ev("gm_fmt_cdi", "Fecal microbiota transplantation for C. difficile",
        "Fecal microbiota transplantation restores microbial diversity and resolves recurrent Clostridioides difficile infection in most patients."),
    _ev("gm_gutbrain_vagus", "Gut-brain axis signaling via the vagus nerve",
        "Commensal microbes modulate host behavior and mood through vagal afferent signaling and microbial metabolites."),
    _ev("gm_probiotic_rct", "Probiotic supplementation randomized trial",
        "A randomized controlled trial reported modest improvement in gastrointestinal symptoms with multi-strain probiotic supplementation.", "T1"),
    _ev("gm_diet_fiber", "Dietary fiber shapes microbial composition",
        "High-fiber diets enrich butyrate-producing taxa whereas Western diets deplete them.", "T2"),
    _ev("gm_immune_treg", "Microbiota and regulatory T-cell development",
        "Colonization by specific Clostridia species promotes regulatory T-cell differentiation and mucosal immune tolerance."),
    _ev("gm_metaanalysis", "Systematic review of microbiome interventions",
        "A systematic review found heterogeneous outcomes across microbiome-targeted interventions, limiting firm clinical recommendations.", "T2"),
    _ev("gm_antibiotic", "Antibiotic-driven dysbiosis and recovery",
        "Broad-spectrum antibiotics cause durable reductions in microbial diversity that recover incompletely over months.", "T1"),
    _ev("gm_gaps", "Open questions in microbiome causality",
        "Whether microbial changes are cause or consequence of disease remains unresolved in most human studies.", "T4"),
]

# --- Domain 3: FINANCE (global insurers comparison) — small synthetic pool ----------------------
FINANCE = [
    _ev("fin_solvency_ratios", "Solvency II capital ratios of top insurers",
        "Leading European insurers reported Solvency II coverage ratios well above regulatory minimums, signaling strong capital buffers.", "T3"),
    _ev("fin_growth_5yr", "Five-year premium growth across major insurers",
        "Gross written premiums grew at differing rates across the ten largest global insurers over the past five years.", "T2"),
    _ev("fin_dividend", "Dividend payout and shareholder returns",
        "Several large insurers maintained stable dividend payout ratios and executed share-buyback programs.", "T2"),
    _ev("fin_china_potential", "Foreign insurer expansion in China",
        "Regulatory liberalization has expanded foreign insurers' access to the Chinese market, raising their growth potential.", "T3"),
    _ev("fin_credit_rating", "Credit ratings and financial strength",
        "Major insurers hold AA-range financial-strength ratings from leading agencies, reflecting low default risk.", "T3"),
    _ev("fin_underwriting", "Underwriting profitability and combined ratios",
        "Combined ratios below 100 percent indicate underwriting profitability among the strongest property-casualty insurers.", "T2"),
    _ev("fin_investment_income", "Investment portfolio and interest-rate sensitivity",
        "Insurers' investment income rose with higher interest rates, though asset-liability mismatches remain a risk.", "T2"),
    _ev("fin_esg", "ESG and long-term underwriting risk",
        "Climate and ESG exposures are reshaping catastrophe underwriting and long-term liability assumptions.", "T4"),
    _ev("fin_market_share", "Market share and geographic diversification",
        "Geographic diversification across Asia, Europe, and the Americas buffers insurers against regional shocks.", "T2"),
    _ev("fin_gaps", "Data limitations in cross-insurer comparison",
        "Differences in accounting standards complicate direct cross-border comparison of insurer financials.", "T4"),
]

MEDICAL_RQ = ("Research the significance of the gut microbiota in maintaining normal intestinal "
              "function, its role in disease, and therapeutic interventions that target it.")
FINANCE_RQ = ("Collect and compare the world's top ten insurance companies across financing, "
              "creditworthiness, five-year growth, dividends, and future potential in China, and "
              "assess which are most likely to rank highest by assets in the future.")


async def run_one(name, rq, evidence, domain, model):
    from src.polaris_graph.generator.multi_section_generator import _call_outline
    pr, retry, itok, otok = await _call_outline(
        rq, evidence, model, 0.2, 2500, domain=domain,
    )
    print(f"\n===== {name}  (domain={domain!r}, {len(evidence)} ev, retry={retry}) =====")
    print(f"ok={pr.ok}  n_sections={len(pr.plans)}  reason_codes={pr.reason_codes[:4]}")
    for i, p in enumerate(pr.plans):
        print(f"  {i+1}. {p.title}   [{len(p.ev_ids)} ev]")
        print(f"       focus: {str(p.focus)[:110]}")
    return [p.title for p in pr.plans]


async def main():
    if not os.getenv("OPENROUTER_API_KEY"):
        print("BLOCKED: OPENROUTER_API_KEY not set", file=sys.stderr)
        return 2
    from src.polaris_graph.outline.outline_agent import outliner_code_model
    model = outliner_code_model()
    print(f"facet={os.getenv('PG_FACET_OUTLINE')}  skeleton={os.getenv('PG_FACET_OUTLINE_SKELETON')}  model={model}")

    # AI/labor: sample from the real corrected corpus (keep it small for a cheap probe).
    corpus = json.loads((ROOT / "data/cp4_corpus_s3gear_329.corrected.json").read_text())
    ai_ev = corpus["evidence"][:70]
    ai_rq = corpus["research_question"]
    ai_domain = corpus.get("domain", "workforce")

    results = {}
    results["ai_labor"] = await run_one("AI / LABOR", ai_rq, ai_ev, ai_domain, model)
    results["medical"] = await run_one("MEDICAL", MEDICAL_RQ, MEDICAL, "medical", model)
    results["finance"] = await run_one("FINANCE", FINANCE_RQ, FINANCE, "finance", model)

    (ROOT / "outputs" / "outline_generality_probe.json").write_text(
        json.dumps(results, indent=2) + "\n", encoding="utf-8")
    print("\nWROTE outputs/outline_generality_probe.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
