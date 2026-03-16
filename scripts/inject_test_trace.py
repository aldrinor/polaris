"""
Synthetic trace injector for dashboard validation.

Writes a JSONL trace file containing ALL event types (old + new WAVE 1-5)
with realistic data so the dashboard can be visually verified.

Usage:
    python scripts/inject_test_trace.py
    python scripts/live_server.py --trace logs/pg_trace_DASHBOARD_TEST.jsonl --port 8765
"""

import json
import os
import time
from datetime import datetime, timezone, timedelta

OUTPUT = os.getenv(
    "PG_TEST_TRACE_OUTPUT",
    "logs/pg_trace_DASHBOARD_TEST.jsonl",
)

VECTOR_ID = "DASHBOARD_TEST"
BASE_TIME = datetime.now(timezone.utc)


def ts(offset_seconds: float = 0) -> str:
    return (BASE_TIME + timedelta(seconds=offset_seconds)).isoformat()


def emit(f, event_type: str, node: str, offset: float, **data):
    ev = {
        "ts": ts(offset),
        "vid": VECTOR_ID,
        "node": node,
        "type": event_type,
        **data,
    }
    f.write(json.dumps(ev, default=str) + "\n")


def main():
    os.makedirs(os.path.dirname(OUTPUT) or ".", exist_ok=True)

    with open(OUTPUT, "w", encoding="utf-8") as f:
        t = 0.0

        # ============================================================
        # WAVE 1: pipeline_start
        # ============================================================
        emit(f, "pipeline_start", "pipeline", t,
             vector_id=VECTOR_ID,
             query="What are the most effective and scalable methods for removing per- and polyfluoroalkyl substances (PFAS) from municipal drinking water systems, and what are the comparative costs, energy requirements, and regulatory considerations across different treatment technologies?",
             application="Water Treatment Technology Assessment",
             region="North America",
             max_iterations=4,
             max_execution_minutes=90,
             resume=False,
             budget_usd=5.0)
        t += 0.5

        # ============================================================
        # Plan node
        # ============================================================
        emit(f, "node_start", "plan", t, iteration=1)
        t += 0.5

        # Reasoning captures for plan phase
        emit(f, "reasoning_capture", "plan", t,
             call_type="plan:query_generation",
             reasoning_text="I need to analyze the research question about PFAS removal from municipal drinking water. This is a multi-faceted topic spanning chemistry, engineering, economics, and regulation. Let me break down the key dimensions:\n\n1. **Technology categories**: Granular activated carbon (GAC), powdered activated carbon (PAC), ion exchange (IX) resins, reverse osmosis (RO), nanofiltration (NF), and emerging destructive methods (electrochemical oxidation, UV/persulfate, sonolysis).\n\n2. **Performance metrics**: Removal efficiency (% PFAS removed), treatment capacity (gallons/day), breakthrough time, selectivity for short-chain vs long-chain PFAS, regeneration cycles.\n\n3. **Cost dimensions**: Capital expenditure (CAPEX), operating expenditure (OPEX), cost per 1000 gallons treated, lifecycle costs over 20-year horizon, economies of scale.\n\n4. **Regulatory landscape**: EPA's proposed MCL of 4 ppt for PFOA/PFOS (2024), state-level variations, compliance timelines, monitoring requirements.\n\nI should generate queries across at least 6 STORM perspectives to ensure comprehensive coverage. The key gap I want to avoid is focusing only on technical performance without addressing the practical implementation challenges that utilities face.",
             input_tokens=1250, output_tokens=0, reasoning_tokens=4500)
        t += 1.0

        emit(f, "reasoning_capture", "plan", t,
             call_type="plan:strategy_selection",
             reasoning_text="For query strategy, I'm choosing multi_perspective_storm because this topic requires diverse viewpoints:\n- Technical perspective needs academic sources (peer-reviewed studies)\n- Economic perspective needs both academic and industry reports\n- Regulatory perspective needs government sources and legal databases\n- Environmental perspective needs lifecycle assessment studies\n- Public health perspective needs epidemiological data\n\nI'll weight 3 queries toward technical (the core question), 2 each for economic/regulatory/environmental/public_health, and 1 for comparative reviews. This ensures we get both depth and breadth.",
             input_tokens=0, output_tokens=0, reasoning_tokens=2100)
        t += 0.5

        # Query plan (existing event, now with full queries)
        emit(f, "evidence", "plan", t,
             action="query_plan",
             count=12,
             search_strategy="multi_perspective_storm",
             key_concepts=["PFAS", "activated carbon", "ion exchange", "reverse osmosis", "nanofiltration", "cost analysis"],
             perspective_distribution={
                 "technical": 3, "economic": 2, "regulatory": 2,
                 "environmental": 2, "public_health": 2, "comparative": 1
             },
             missing_perspectives=["historical"],
             queries=[
                 {"query": "PFAS removal efficiency granular activated carbon GAC municipal water treatment systems peer-reviewed studies 2023-2025", "perspective": "technical", "intent": "Evaluate GAC adsorption capacity and breakthrough curves for short-chain and long-chain PFAS compounds", "source_preference": "academic"},
                 {"query": "ion exchange resin PFAS removal drinking water selectivity regeneration lifecycle cost", "perspective": "technical", "intent": "Compare IX resin types for PFAS selectivity and regeneration economics", "source_preference": "academic"},
                 {"query": "reverse osmosis nanofiltration PFAS rejection rates energy consumption municipal scale", "perspective": "technical", "intent": "Assess membrane technologies for PFAS rejection at municipal scale", "source_preference": "academic"},
                 {"query": "PFAS water treatment capital operating cost comparison per gallon treated 2024", "perspective": "economic", "intent": "Compare lifecycle costs across GAC, IX, RO, and emerging technologies", "source_preference": "web"},
                 {"query": "EPA PFAS maximum contaminant level MCL drinking water regulation 2024 2025 compliance timeline", "perspective": "regulatory", "intent": "Track current EPA MCL rulemaking and compliance deadlines for utilities", "source_preference": "web"},
                 {"query": "PFAS destruction technologies electrochemical oxidation sonochemical degradation pilot scale results", "perspective": "technical", "intent": "Evaluate emerging destructive technologies beyond conventional separation", "source_preference": "academic"},
                 {"query": "municipal water utility PFAS treatment implementation case studies cost effectiveness", "perspective": "economic", "intent": "Real-world case studies of PFAS treatment implementation and costs", "source_preference": "web"},
                 {"query": "environmental impact PFAS treatment waste disposal concentrated brine management", "perspective": "environmental", "intent": "Assess secondary environmental impacts of PFAS treatment waste streams", "source_preference": "academic"},
                 {"query": "PFAS health effects exposure drinking water epidemiological studies cancer risk", "perspective": "public_health", "intent": "Document health risks driving regulatory action on PFAS in drinking water", "source_preference": "academic"},
                 {"query": "state-level PFAS drinking water standards comparison stricter than EPA federal", "perspective": "regulatory", "intent": "Compare state-level PFAS regulations that exceed federal standards", "source_preference": "web"},
                 {"query": "PFAS contamination groundwater prevalence United States municipal water systems affected", "perspective": "environmental", "intent": "Quantify the scale of PFAS contamination in US water systems", "source_preference": "web"},
                 {"query": "comparative analysis PFAS removal technologies advantages disadvantages table review 2024", "perspective": "comparative", "intent": "Find existing comparative reviews and technology assessment frameworks", "source_preference": "academic"},
             ])
        t += 2.0

        # WAVE 1: llm_detail (query planning LLM call)
        emit(f, "llm_detail", "plan", t,
             call_type="plan:query_generation",
             model="moonshotai/kimi-k2-instruct",
             temperature=0.7,
             max_tokens=16384,
             reasoning_enabled=True,
             response_format="",
             prompt_messages=[
                 {"role": "system", "content": "You are a SOTA research query planner using the STORM multi-perspective methodology. Your job is to generate exactly 12 search queries covering 8 research perspectives. Each query must be specific, searchable, and designed to find high-quality evidence.\n\nPerspectives: technical, economic, regulatory, environmental, public_health, comparative, historical, societal\n\nFor each query provide:\n- query: The actual search string (be specific, include year ranges)\n- perspective: Which perspective this serves\n- intent: What you expect to find\n- source_preference: 'academic' or 'web'"},
                 {"role": "user", "content": "Research question: What are the most effective and scalable methods for removing per- and polyfluoroalkyl substances (PFAS) from municipal drinking water systems, and what are the comparative costs, energy requirements, and regulatory considerations across different treatment technologies?\n\nApplication: Water Treatment Technology Assessment\nRegion: North America\n\nGenerate 12 search queries covering at least 6 perspectives."}
             ],
             response_content='{"sub_queries": [{"query": "PFAS removal efficiency granular activated carbon GAC municipal water treatment systems peer-reviewed studies 2023-2025", "perspective": "technical", "intent": "Evaluate GAC adsorption capacity", "source_preference": "academic"}, ...], "search_strategy": "multi_perspective_storm", "key_concepts": ["PFAS", "activated carbon", "ion exchange"]}',
             response_reasoning="Let me analyze the research question systematically. PFAS removal involves multiple technology categories: adsorption (GAC, PAC), ion exchange, membrane filtration (RO, NF), and emerging destructive methods. I need queries that cover technical performance, costs, regulations, environmental impact, and health drivers...",
             input_tokens=1250,
             output_tokens=2800,
             reasoning_tokens=4500,
             duration_ms=8500,
             cost_usd=0.0234)
        t += 3.0

        emit(f, "llm_call", "plan", t,
             call_type="plan:query_generation",
             input_tokens=1250, output_tokens=2800,
             duration_ms=8500, reasoning_tokens=4500,
             cost_usd=0.0234, cumulative_cost_usd=0.0234,
             model="moonshotai/kimi-k2-instruct")
        t += 0.5

        emit(f, "node_end", "plan", t, duration_ms=12000, query_count=12)
        t += 1.0

        # ============================================================
        # Search node
        # ============================================================
        emit(f, "node_start", "search", t, iteration=1)
        t += 0.3

        emit(f, "reasoning_capture", "search", t,
             call_type="search:query_amplification",
             reasoning_text="Amplifying 12 planned queries into 36 search-ready variants. For each query, I'm generating 2-3 reformulations:\n- Original query preserved for precision\n- Broader variant for recall (removing year constraints)\n- Academic variant with specific journal/venue terms\n\nI'm also interleaving web and academic searches at a 60/40 ratio. Web searches go to Serper (primary) with DuckDuckGo fallback. Academic searches target Semantic Scholar's bulk API with field filters for environmental science, water research, and chemical engineering.",
             input_tokens=800, output_tokens=0, reasoning_tokens=1800)
        t += 0.5

        emit(f, "reasoning_capture", "search", t,
             call_type="search:execution",
             reasoning_text="Executing 36 queries across 3 search engines concurrently (web_concurrency=20, academic_concurrency=1 due to S2 rate limits). Expected yield: ~10 results/query for Serper, ~5 for S2 bulk. That's potentially 360 web + 60 academic = 420 raw results before deduplication.\n\nDomain blocklist active: filtering out medium.com, reddit.com, quora.com, and known paywall domains. Authority scoring will boost .gov, .edu, and peer-reviewed sources.",
             input_tokens=0, output_tokens=0, reasoning_tokens=1500)
        t += 0.2

        # Amplified queries (WAVE 2.4)
        emit(f, "query", "search", t,
             action="amplified", count=36,
             queries=[
                 "PFAS removal efficiency granular activated carbon GAC municipal water treatment systems peer-reviewed studies 2023-2025",
                 "PFAS GAC adsorption breakthrough curves short-chain long-chain compounds",
                 "granular activated carbon PFAS water treatment performance metrics",
                 "ion exchange resin PFAS removal drinking water selectivity regeneration lifecycle cost",
                 "IX resin PFAS selectivity comparison single-use vs regenerable",
                 "ion exchange PFAS treatment cost per 1000 gallons",
                 "reverse osmosis nanofiltration PFAS rejection rates energy consumption municipal scale",
                 "RO membrane PFAS removal 99 percent rejection pilot studies",
                 "nanofiltration PFAS treatment energy requirements comparison",
             ])
        t += 1.0

        # Per-query search results (WAVE 2.2 — Serper with URLs/titles/snippets)
        search_queries = [
            ("PFAS removal efficiency granular activated carbon GAC", "serper", 10),
            ("ion exchange resin PFAS removal drinking water", "serper", 8),
            ("reverse osmosis nanofiltration PFAS rejection rates", "serper", 7),
            ("PFAS water treatment capital operating cost comparison", "serper", 9),
            ("EPA PFAS maximum contaminant level MCL 2024 2025", "serper", 10),
            ("PFAS destruction technologies electrochemical oxidation", "serper", 6),
            ("municipal water utility PFAS treatment case studies", "serper", 8),
        ]
        for sq, engine, count in search_queries:
            emit(f, "search_result", "search", t,
                 engine=engine,
                 query=sq,
                 result_count=count,
                 urls=[
                     f"https://doi.org/10.1021/acs.est.{2024+i}example" if i % 3 == 0
                     else f"https://www.epa.gov/pfas/treatment-tech-{i}"  if i % 3 == 1
                     else f"https://www.waterworld.com/pfas-article-{i}"
                     for i in range(min(count, 10))
                 ],
                 titles=[
                     f"Granular Activated Carbon for PFAS Removal: A Systematic Review ({2023+i%3})" if i % 4 == 0
                     else f"EPA Technical Brief: PFAS Treatment Technologies for Drinking Water" if i % 4 == 1
                     else f"Cost-Effectiveness Analysis of PFAS Removal at Municipal Scale" if i % 4 == 2
                     else f"Ion Exchange vs GAC: Comparative Performance for Short-Chain PFAS"
                     for i in range(min(count, 10))
                 ],
                 snippets=[
                     "This study evaluated the performance of granular activated carbon (GAC) contactors for removing 24 PFAS compounds from municipal drinking water. Results showed >95% removal for long-chain PFAS (PFOA, PFOS) with GAC contact times of 10-15 minutes...",
                     "The EPA has established Maximum Contaminant Levels (MCLs) for six PFAS compounds at 4 parts per trillion (ppt) for PFOA and PFOS individually, with a combined MCL of 10 ppt for other PFAS...",
                     "A lifecycle cost analysis across 47 water utilities found that GAC treatment costs range from $0.50-$2.30 per 1,000 gallons depending on influent PFAS concentrations and empty bed contact time...",
                 ][:min(count, 3)])
            t += 0.3

        # OpenAlex academic results (WAVE 2.2)
        emit(f, "search_result", "search", t,
             engine="openalex",
             query="PFAS removal activated carbon municipal water",
             result_count=5,
             urls=["https://doi.org/10.1021/acs.est.3c09876", "https://doi.org/10.1016/j.watres.2024.01234"],
             titles=["Breakthrough Behavior of PFAS in GAC Contactors", "Comparative PFAS Removal by GAC and IX Resins"],
             years=[2024, 2024],
             citation_counts=[45, 23])
        t += 1.0

        # S2 fallback (WAVE 2.2)
        emit(f, "search_result", "search", t,
             engine="s2",
             query="PFAS nanofiltration rejection mechanisms",
             result_count=3,
             urls=["https://api.semanticscholar.org/paper1", "https://api.semanticscholar.org/paper2"],
             titles=["Nanofiltration Membrane Rejection of PFAS", "Membrane-Based PFAS Treatment"],
             years=[2023, 2024])
        t += 0.5

        # Exa per-query (WAVE 2.1)
        emit(f, "search_result", "search", t,
             engine="exa",
             query="PFAS water treatment cost effectiveness analysis 2024",
             result_count=4,
             urls=["https://www.awwa.org/pfas-cost-study", "https://www.sciencedirect.com/pfas-economics"],
             titles=["AWWA PFAS Treatment Cost Study 2024", "Economics of PFAS Remediation"],
             snippets=["Comprehensive cost analysis of GAC, IX, and RO for PFAS removal across 120 US utilities..."],
             scores=[0.92, 0.87, 0.81, 0.76],
             exa_cost=0.015)
        t += 0.5

        # Cache hit (WAVE 2.2)
        emit(f, "search_result", "search", t,
             engine="serper",
             query="EPA PFAS MCL final rule 2024",
             result_count=6,
             cached=True)
        t += 0.3

        # DDG fallback (WAVE 2.3)
        emit(f, "search_result", "search", t,
             engine="duckduckgo",
             query="PFAS foam fractionation pilot results",
             result_count=3,
             fallback=True,
             urls=["https://www.wef.org/pfas-foam", "https://pubs.acs.org/pfas-foam-study"],
             titles=["Foam Fractionation for PFAS Removal", "Pilot-Scale PFAS Foam Treatment"])
        t += 0.3

        # DDG fallback summary (WAVE 2.3)
        emit(f, "evidence", "search", t,
             action="ddg_fallback_summary",
             count=3,
             zero_result_queries=2,
             retried=2)
        t += 0.5

        # Exa summary
        emit(f, "evidence", "search", t,
             action="exa_summary",
             count=12,
             queries=4,
             session_cost=0.042,
             session_searches=4)
        t += 0.5

        # Fetch events
        fetch_urls = [
            ("https://doi.org/10.1021/acs.est.3c09876", "success", 15200),
            ("https://www.epa.gov/pfas/treatment-technologies", "success", 28400),
            ("https://www.waterworld.com/pfas-costs-2024", "success", 8900),
            ("https://www.sciencedirect.com/pfas-economics", "snippet_fallback", 1200),
            ("https://pubs.acs.org/restricted-pfas-paper", "paywall_skip", 0),
            ("https://blocked-domain.example.com/pfas", "blocked", 0),
            ("https://www.awwa.org/pfas-cost-study", "success", 22100),
            ("https://www.nature.com/pfas-health-review", "success", 31000),
        ]
        for url, status, content_len in fetch_urls:
            emit(f, "fetch", "analyze", t,
                 url=url, status=status, content_len=content_len,
                 duration_ms=1200 + content_len // 10)
            t += 0.2

        emit(f, "node_end", "search", t, duration_ms=45000)
        t += 1.0

        # ============================================================
        # STORM interviews
        # ============================================================
        emit(f, "node_start", "storm_interviews", t, iteration=1)
        t += 0.3

        emit(f, "reasoning_capture", "storm_interviews", t,
             call_type="storm:persona_selection",
             reasoning_text="Selecting STORM personas for multi-perspective interviews. The research question spans 5 key domains, so I need at least 5 expert personas:\n\n1. **Environmental Engineer** — for technical treatment process expertise\n2. **Utility Finance Director** — for real-world cost and implementation data\n3. **EPA Program Lead** — for regulatory context and compliance requirements\n4. **Environmental Toxicologist** — for PFAS fate, transport, and environmental impact\n5. **Public Health Epidemiologist** — for health outcome data driving regulatory urgency\n\nEach persona will conduct a focused interview exploring their domain expertise, generating targeted questions that probe beyond surface-level information. The cross-pollination between perspectives (e.g., cost implications of regulatory deadlines) is where the most valuable insights emerge.",
             input_tokens=500, output_tokens=0, reasoning_tokens=2200)
        t += 0.3

        personas = [
            ("Dr. Sarah Chen", "technical", "Environmental Engineering Professor"),
            ("Michael Torres", "economic", "Water Utility Finance Director"),
            ("Jennifer Walsh", "regulatory", "EPA PFAS Program Lead"),
            ("Prof. Raj Patel", "environmental", "Environmental Toxicologist"),
            ("Dr. Lisa Kim", "public_health", "Public Health Epidemiologist"),
        ]
        for name, perspective, expertise in personas:
            # Interview complete (WAVE 4.5)
            emit(f, "llm_call", "storm_interviews", t,
                 call_type="storm_interviews:interview_complete",
                 persona_name=name,
                 perspective=perspective,
                 rounds_completed=3,
                 search_results=8)

            # Storm transcript
            emit(f, "storm_transcript", "storm_interviews", t,
                 persona=name,
                 round=1,
                 question=f"From your {perspective} perspective, what is the most critical factor in selecting PFAS treatment technology for municipal water systems?",
                 answer=f"As a {expertise}, I would emphasize that the selection must consider not just removal efficiency but long-term operational sustainability. For example, GAC systems require frequent media replacement, which creates a secondary waste stream...",
                 sources=["https://doi.org/10.1021/acs.est.3c09876"],
                 key_findings=[f"GAC requires replacement every 6-12 months for PFAS",
                              f"IX resins offer higher selectivity but 3x capital cost"],
                 expertise=expertise,
                 question_focus=f"{perspective} analysis of PFAS treatment")
            t += 2.0

        # One failed interview (WAVE 4.5)
        emit(f, "llm_call", "storm_interviews", t,
             call_type="storm_interviews:interview_failed",
             persona_name="Dr. James Wright",
             perspective="historical",
             persona_index=5,
             failure="timeout",
             timeout_seconds=300)
        t += 0.5

        # Failed interview storm_transcript (so dashboard shows failed overlay)
        emit(f, "storm_transcript", "storm_interviews", t,
             persona="Dr. James Wright",
             round=1,
             question="From your historical perspective, how has PFAS regulation evolved over the past two decades?",
             answer="I cannot provide specific details on this topic at this time.",
             sources=[],
             key_findings=[],
             expertise="Environmental Historian",
             question_focus="historical analysis of PFAS regulation")
        t += 0.5

        emit(f, "llm_call", "storm_interviews", t,
             call_type="storm_interviews:interview_simulation",
             conversations=5, total_rounds=15,
             search_results=40,
             completed_perspectives=5,
             skipped_perspectives=1)
        t += 0.5

        emit(f, "node_end", "storm_interviews", t, duration_ms=65000)
        t += 1.0

        # ============================================================
        # Analyze node
        # ============================================================
        emit(f, "node_start", "analyze", t, iteration=1, sources_to_analyze=42)
        t += 0.3

        emit(f, "reasoning_capture", "analyze", t,
             call_type="analyze:evidence_extraction",
             reasoning_text="Processing 42 fetched sources for evidence extraction. Batching into 7 groups of 6 sources each for parallel LLM extraction.\n\nExtraction strategy:\n- For each source, extract factual claims with direct quotes\n- Apply 5-signal scoring: relevance (to PFAS removal), authority (source credibility), information density, freshness (publication year), grounding (quote availability)\n- Filter evidence below 0.20 relevance threshold (likely off-topic)\n- Tag each piece with STORM perspective alignment\n\nContent cap: 10,000 chars per source to stay within Kimi K2.5 context window. Sources exceeding this will use smart truncation (preserve abstract + conclusion + tables).",
             input_tokens=0, output_tokens=0, reasoning_tokens=3200)
        t += 0.3

        emit(f, "reasoning_capture", "analyze", t,
             call_type="analyze:quality_scoring",
             reasoning_text="Scoring evidence against 5 quality signals:\n\n**Relevance** (0-1): Semantic similarity to research question using embedding cosine distance. Threshold 0.40 for inclusion. 42% of raw extractions typically fall below this.\n\n**Authority** (0-1): Source domain scoring — .gov/.edu get 0.8+, peer-reviewed journals 0.7+, industry reports 0.5-0.7, news sites 0.3-0.5. Paywall domains flagged for content validation.\n\n**Information Density** (0-1): Ratio of specific facts (numbers, percentages, dates) to total claims. Dense sources score higher.\n\n**Freshness** (0-1): Decay function from publication year. 2024-2025 sources score 0.9+, 2020-2023 score 0.6-0.8, pre-2020 score 0.3-0.5.\n\n**Grounding** (0-1): Does the evidence include a direct, verifiable quote from the source? Quote-grounded evidence scores 0.8+, paraphrased scores 0.4.",
             input_tokens=0, output_tokens=0, reasoning_tokens=2800)
        t += 0.2

        # Extraction batch progress (WAVE 3.4)
        for batch_idx in range(1, 8):
            emit(f, "llm_call", "analyze", t,
                 call_type="analyze:extraction_batch",
                 batch_index=batch_idx,
                 total_batches=7,
                 evidence_extracted=15 + batch_idx * 3,
                 evidence_total=batch_idx * 18,
                 sources_in_batch=6,
                 source_urls=[
                     f"https://source-{batch_idx}-{j}.example.com" for j in range(6)
                 ])
            t += 3.0

        # Evidence extracted
        emit(f, "evidence", "analyze", t,
             action="extracted", count=126,
             sources_fetched=42, gold=18, silver=45, bronze=63)
        t += 0.5

        # Fetch summary
        emit(f, "evidence", "analyze", t,
             action="fetch_summary",
             total_attempted=42, success=35,
             snippet_fallback=4, failed=3)
        t += 0.5

        # ============================================================
        # WAVE 3: Tier scoring detail
        # ============================================================
        scoring_data = []
        for i in range(126):
            tier = "GOLD" if i < 18 else "SILVER" if i < 63 else "BRONZE"
            composite = 0.75 - (i * 0.003)
            veto = ""
            if i > 100:
                veto = "substance<0.2"
            elif i > 90 and i <= 100:
                veto = "snippet_cap"
            scoring_data.append({
                "id": f"ev_{i:04d}abcdef{i:04d}",
                "tier": tier,
                "composite": round(max(0.15, composite), 4),
                "sig_relevance": round(max(0.1, 0.85 - i * 0.004), 4),
                "sig_authority": round(max(0.1, 0.70 - i * 0.003), 4),
                "sig_density": round(max(0.05, 0.80 - i * 0.005), 4),
                "sig_freshness": round(max(0.2, 0.90 - i * 0.002), 4),
                "sig_grounding": round(max(0.1, 0.65 - i * 0.003), 4),
                "veto_reason": veto,
                "source_url": f"https://source-{i % 20}.example.com/paper-{i}",
                "statement": [
                    "Granular activated carbon (GAC) achieves >95% removal of PFOA and PFOS at empty bed contact times of 10-15 minutes",
                    "Ion exchange resins demonstrate higher selectivity for short-chain PFAS compared to GAC",
                    "Reverse osmosis membranes reject >99% of all PFAS compounds but at 3-5x the energy cost of GAC",
                    "The EPA final MCL rule sets PFOA and PFOS limits at 4 parts per trillion individually",
                    "Lifecycle cost analysis shows GAC treatment ranges from $0.50-$2.30 per 1,000 gallons",
                    "Electrochemical oxidation achieves complete mineralization of PFAS but remains at pilot scale",
                    "PFAS contamination affects an estimated 110 million Americans' drinking water supplies",
                    "Foam fractionation concentrates PFAS by 100-1000x before destructive treatment",
                ][i % 8],
            })

        emit(f, "evidence", "analyze", t,
             action="tier_scoring_detail",
             count=126,
             scores=scoring_data)
        t += 0.5

        # Signal distribution
        emit(f, "evidence", "analyze", t,
             action="tier_signal_distribution",
             count=126,
             signal_stats={
                 "semantic_relevance": {"min": 0.12, "median": 0.58, "max": 0.92, "count": 126},
                 "source_authority": {"min": 0.10, "median": 0.45, "max": 0.88, "count": 126},
                 "content_density": {"min": 0.05, "median": 0.52, "max": 0.95, "count": 126},
                 "freshness": {"min": 0.20, "median": 0.72, "max": 0.98, "count": 126},
                 "nli_grounding": {"min": 0.10, "median": 0.48, "max": 0.85, "count": 126},
             },
             tier_counts={"GOLD": 18, "SILVER": 45, "BRONZE": 63})
        t += 0.5

        # ============================================================
        # WAVE 3: Dedup detail
        # ============================================================
        dedup_pairs = [
            {"original_idx": 5, "duplicate_idx": 47, "similarity": 0.923, "type": "near_duplicate"},
            {"original_idx": 12, "duplicate_idx": 89, "similarity": 0.891, "type": "near_duplicate"},
            {"original_idx": 3, "duplicate_idx": 3, "similarity": 1.0, "type": "exact"},
            {"original_idx": 22, "duplicate_idx": 67, "similarity": 0.856, "type": "near_duplicate"},
            {"original_idx": 8, "duplicate_idx": 102, "similarity": 0.912, "type": "near_duplicate"},
            {"original_idx": 15, "duplicate_idx": 15, "similarity": 1.0, "type": "exact"},
            {"original_idx": 31, "duplicate_idx": 78, "similarity": 0.877, "type": "near_duplicate"},
            {"original_idx": 41, "duplicate_idx": 99, "similarity": 0.845, "type": "near_duplicate"},
        ]
        emit(f, "evidence", "analyze", t,
             action="dedup_detail",
             count=126,
             before_count=126,
             after_count=112,
             exact_removed=6,
             near_removed=8,
             minhash_pairs=dedup_pairs)
        t += 0.5

        # Dedup summary
        emit(f, "evidence", "analyze", t,
             action="dedup_summary",
             count=112,
             pre_dedup=126,
             post_dedup=112)
        t += 0.5

        # Accumulated
        emit(f, "evidence", "analyze", t,
             action="accumulated", count=112)
        t += 0.5

        # Cross-reference groups (corroborating evidence clusters)
        cross_ref_groups = []
        for g in range(8):
            group_ids = [f"ev_{g*5+j:04d}abcdef{g*5+j:04d}" for j in range(4)]
            cross_ref_groups.append({
                "group_id": g,
                "evidence_ids": group_ids,
                "similarity": round(0.72 + g * 0.03, 2),
                "agreement_score": round(0.68 + g * 0.04, 2),
                "claim_summary": f"PFAS treatment method {g+1} effectiveness data corroboration",
            })
        emit(f, "evidence", "analyze", t,
             action="cross_reference_groups",
             groups=cross_ref_groups,
             total_groups=len(cross_ref_groups))
        t += 0.5

        # Evidence conflicts (contradicting evidence pairs)
        evidence_conflicts = [
            {
                "evidence_id_a": "ev_0002abcdef0002",
                "evidence_id_b": "ev_0045abcdef0045",
                "score": 0.85,
                "similarity": 0.15,
                "conflict_type": "contradictory_findings",
                "description": "GAC lifetime estimates differ: 6 months vs 18 months",
            },
            {
                "evidence_id_a": "ev_0010abcdef0010",
                "evidence_id_b": "ev_0067abcdef0067",
                "score": 0.72,
                "similarity": 0.28,
                "conflict_type": "cost_disagreement",
                "description": "IX resin costs: $0.50/1000gal vs $1.20/1000gal",
            },
        ]
        emit(f, "evidence", "analyze", t,
             action="evidence_conflicts",
             conflicts=evidence_conflicts,
             total_conflicts=len(evidence_conflicts))
        t += 0.5

        emit(f, "node_end", "analyze", t, duration_ms=95000, evidence_count=112)
        t += 1.0

        # ============================================================
        # Verify node
        # ============================================================
        emit(f, "node_start", "verify", t, iteration=1, evidence_count=112)
        t += 0.3

        emit(f, "reasoning_capture", "verify", t,
             call_type="verify:nli_cascade",
             reasoning_text="Running NLI verification cascade on 112 evidence pieces. Strategy:\n\n1. **NLI fast-pass** (MiniCheck flan-t5-large): All 112 items verified against source content. Context window: extract ~2K chars around each quote for 512-token limit. Expected throughput: ~0.14s/item = ~16 seconds total.\n\n2. **LLM fallback** (for items NLI can't determine): Evidence without direct quotes or with content < 500 chars gets LLM-based verification via Kimi K2.5.\n\n3. **Cross-source NLI**: After individual verification, run pairwise contradiction detection on claims about the same topic. Looking for conflicting statistics (e.g., different removal efficiency percentages for the same technology).\n\nExpected outcome: ~82% SUPPORTED, ~9% PARTIALLY_SUPPORTED, ~9% NOT_SUPPORTED. Items failing verification can still be included if they have GOLD/SILVER tier scores, but will be flagged in the report.",
             input_tokens=0, output_tokens=0, reasoning_tokens=3500)
        t += 0.3

        # WAVE 4.1: Verification context
        verification_claims = []
        for i in range(112):
            is_faithful = i < 92  # ~82% faithfulness
            verdict = "SUPPORTED" if is_faithful else ("PARTIALLY_SUPPORTED" if i < 102 else "NOT_SUPPORTED")
            basis = "content" if i < 80 else ("quote_only" if i < 100 else "title_only")
            verification_claims.append({
                "evidence_id": f"ev_{i:04d}abcdef{i:04d}",
                "verdict": verdict,
                "confidence": round(0.95 - i * 0.003, 3),
                "is_faithful": is_faithful,
                "basis": basis,
                "nli_score": round(0.90 - i * 0.005, 3) if i < 100 else 0.0,
                "cross_source_score": round(0.80 - i * 0.004, 3) if i < 50 else 0.0,
                "source_url": f"https://source-{i % 20}.example.com/paper-{i}",
                "statement": scoring_data[i]["statement"] if i < len(scoring_data) else "",
                "direct_quote": f"Direct quote from source {i}: evidence supporting the claim..." if i < 80 else "",
            })

        emit(f, "evidence", "verify", t,
             action="verification_context",
             count=112,
             claims=verification_claims)
        t += 1.0

        # NLI verification detail
        emit(f, "evidence", "verify", t,
             action="nli_verification_detail",
             count=112,
             faithful_count=92,
             faithfulness_pct=82.1,
             disputed_count=20,
             api_error_count=3,
             basis_distribution={"content": 80, "quote_only": 20, "title_only": 12},
             claims_detail=[{
                 "id": f"ev_{i:04d}ab",
                 "nli_score": round(0.90 - i * 0.02, 3),
                 "cross_source_score": round(0.80 - i * 0.03, 3),
                 "is_faithful": i < 15,
                 "statement": scoring_data[i]["statement"] if i < len(scoring_data) else "",
             } for i in range(20)])
        t += 0.5

        emit(f, "evidence", "verify", t,
             action="accumulated", count=112)
        t += 0.5

        emit(f, "node_end", "verify", t, duration_ms=180000, evidence_count=112)
        t += 1.0

        # Verification batch (llm_call) — populates verificationVerdicts in dashboard
        batch_claims = []
        for i in range(112):
            is_faithful = i < 92
            verdict = "SUPPORTED" if is_faithful else ("PARTIALLY_SUPPORTED" if i < 102 else "NOT_SUPPORTED")
            batch_claims.append({
                "statement": f"Claim {i}: PFAS treatment evidence assertion {i}",
                "faithful": is_faithful,
                "verdict": verdict,
                "nli_score": round(0.95 - (i * 0.005), 3) if i < 92 else round(0.35 + (i - 92) * 0.02, 3),
                "source_url": f"https://source-{i % 20}.example.com",
                "direct_quote": f"Supporting quote for claim {i}" if is_faithful else "",
                "reasoning": f"Verification reasoning for claim {i}",
                "verification_basis": "content" if i < 80 else "quote_only",
            })
        emit(f, "llm_call", "verify", t,
             call_type="verification_batch",
             batch_size=112,
             claims=batch_claims,
             input_tokens=50000, output_tokens=15000,
             duration_ms=45000,
             cost_usd=0.12, cumulative_cost_usd=0.89,
             model="moonshotai/kimi-k2-instruct")
        t += 1.0

        # ============================================================
        # Evaluate node
        # ============================================================
        emit(f, "node_start", "evaluate", t, iteration=1)
        t += 0.3

        emit(f, "reasoning_capture", "evaluate", t,
             call_type="evaluate:quality_assessment",
             reasoning_text="Evaluating iteration 1 results against quality gates:\n\n- Evidence count: 112 (threshold: ≥10) ✓\n- Gold-tier evidence: 18 (16%) — strong factual anchors\n- Silver-tier evidence: 34 (30%) — good supporting data\n- Bronze-tier evidence: 60 (54%) — lower quality, supplementary\n- Faithfulness: 82.1% (threshold: ≥70%) ✓\n- Source diversity: 42 unique sources ✓\n- Perspective coverage: 6/8 perspectives (missing: historical, societal)\n\nDecision: CONTINUE to iteration 2. Rationale:\n- Missing 2 perspectives that could strengthen the analysis\n- Only 16% GOLD evidence — gap search could find higher-quality academic sources\n- Faithfulness above threshold but room for improvement through additional verification\n- Budget remaining: $4.77 of $5.00 — sufficient for one more iteration",
             input_tokens=0, output_tokens=0, reasoning_tokens=2500)
        t += 0.3

        emit(f, "iteration_decision", "evaluate", t,
             iteration=1,
             decision="continue",
             rationale={
                 "evidence_count": 112,
                 "gold_count": 18,
                 "faithfulness": 0.821,
                 "gaps": ["Foam fractionation cost data", "Emerging destructive technologies at scale"],
                 "reason": "Faithfulness adequate but evidence gaps in emerging technologies",
             })
        t += 0.5

        emit(f, "node_end", "evaluate", t, duration_ms=5000)
        t += 1.0

        # ============================================================
        # Synthesize node
        # ============================================================
        emit(f, "node_start", "synthesize", t, iteration=1)
        t += 0.3

        emit(f, "reasoning_capture", "synthesize", t,
             call_type="synthesize:clustering",
             reasoning_text="Clustering 112 evidence pieces into thematic groups using map-reduce approach (batch size 50, 3 batches). Strategy:\n\n1. Map phase: Each batch of ~37 items gets clustered into 4-6 themes independently\n2. Reduce phase: Merge themes across batches using Jaccard word similarity (threshold 0.30)\n3. Final: ~8 coherent themes covering the full research landscape\n\nUsing programmatic merge instead of LLM merge for 100% ID preservation (vs ~50% with LLM). The GraphRAG insight: let code track IDs while LLM provides semantic labels.",
             input_tokens=0, output_tokens=0, reasoning_tokens=2000)
        t += 0.3

        emit(f, "reasoning_capture", "synthesize", t,
             call_type="synthesize:outline_generation",
             reasoning_text="Generating report outline from 8 thematic clusters. Structure:\n\n1. Executive summary (grounded in GOLD evidence only)\n2. Technical section: GAC, IX, membrane technologies (clusters 1-3)\n3. Cost analysis: comparative economics (cluster 4)\n4. Regulatory landscape: EPA MCLs, state standards (cluster 5)\n5. Emerging technologies: destructive methods (cluster 6)\n6. Environmental considerations: waste management (cluster 7)\n7. Health context: epidemiological evidence (cluster 8)\n8. Conclusion and recommendations\n\nEach section will use cite-first synthesis: every factual claim must have a [CITE:ev_xxx] before it can appear in the draft. This eliminates hallucination by construction.",
             input_tokens=0, output_tokens=0, reasoning_tokens=2400)
        t += 0.2

        # Clustering
        emit(f, "evidence", "synthesize", t,
             action="clustering", count=8, evidence_count=112,
             themes=[
                 {"theme": "GAC Adsorption Performance and Limitations", "count": 22},
                 {"theme": "Ion Exchange Technology Selectivity", "count": 18},
                 {"theme": "Membrane Filtration (RO/NF) Capabilities", "count": 15},
                 {"theme": "Treatment Cost Economics", "count": 20},
                 {"theme": "Regulatory Framework and MCL Compliance", "count": 14},
                 {"theme": "Emerging Destructive Technologies", "count": 8},
                 {"theme": "Environmental Impact and Waste Management", "count": 10},
                 {"theme": "Public Health Risk Assessment", "count": 5},
             ])
        t += 2.0

        # Report outline
        emit(f, "evidence", "synthesize", t,
             action="report_outline",
             count=8,
             title="PFAS Removal Technologies for Municipal Drinking Water",
             sections=[
                 {"id": "s1", "title": "Introduction: The PFAS Challenge in Municipal Water", "order": 1, "description": "Scope and prevalence of PFAS contamination", "evidence_count": 8, "perspectives": ["public_health", "environmental"]},
                 {"id": "s2", "title": "Granular Activated Carbon (GAC) Treatment", "order": 2, "description": "Performance, capacity, and breakthrough behavior", "evidence_count": 22, "perspectives": ["technical"]},
                 {"id": "s3", "title": "Ion Exchange (IX) Resin Technology", "order": 3, "description": "Selectivity, regeneration, and lifecycle", "evidence_count": 18, "perspectives": ["technical", "economic"]},
                 {"id": "s4", "title": "Membrane Technologies: RO and Nanofiltration", "order": 4, "description": "Rejection rates, energy, and concentrate management", "evidence_count": 15, "perspectives": ["technical", "environmental"]},
                 {"id": "s5", "title": "Emerging Destructive Technologies", "order": 5, "description": "Electrochemical, sonochemical, and advanced oxidation", "evidence_count": 8, "perspectives": ["technical"]},
                 {"id": "s6", "title": "Comparative Cost Analysis", "order": 6, "description": "Capital, operating, and lifecycle cost comparison", "evidence_count": 20, "perspectives": ["economic"]},
                 {"id": "s7", "title": "Regulatory Landscape and Compliance", "order": 7, "description": "Federal and state MCLs, compliance timelines", "evidence_count": 14, "perspectives": ["regulatory"]},
                 {"id": "s8", "title": "Conclusions and Recommendations", "order": 8, "description": "Technology selection framework and future outlook", "evidence_count": 7, "perspectives": ["comparative"]},
             ])
        t += 1.0

        # Section writes
        sections_data = [
            ("s1", "Introduction: The PFAS Challenge in Municipal Water", 450, 8),
            ("s2", "Granular Activated Carbon (GAC) Treatment", 1200, 18),
            ("s3", "Ion Exchange (IX) Resin Technology", 980, 14),
            ("s4", "Membrane Technologies: RO and Nanofiltration", 850, 12),
            ("s5", "Emerging Destructive Technologies", 380, 5),
            ("s6", "Comparative Cost Analysis", 1100, 16),
            ("s7", "Regulatory Landscape and Compliance", 720, 10),
            ("s8", "Conclusions and Recommendations", 520, 6),
        ]
        for sid, title, words, ev_count in sections_data:
            emit(f, "llm_call", "synthesize", t,
                 call_type="section_write",
                 title=title,
                 input_tokens=3000 + ev_count * 200,
                 output_tokens=words * 2,
                 duration_ms=12000 + words * 5)
            t += 2.0

        # Quality gate — first check (fails on word count)
        emit(f, "quality_gate", "synthesize", t,
             gate="post_synthesis",
             passed=False,
             expansion_pass=1,
             total_words=6200,
             total_citations=89,
             unique_sources=28,
             faithfulness=0.821)
        t += 0.5

        # WAVE 4.4: Expansion detail
        emit(f, "evidence", "synthesize", t,
             action="expansion_detail",
             count=2,
             pass_number=1,
             dynamic_target=400,
             avg_deficit=280,
             min_acceptable=600,
             sections=[
                 {"section_id": "s1", "title": "Introduction: The PFAS Challenge in Municipal Water", "before_words": 450, "evidence_assigned": 8},
                 {"section_id": "s5", "title": "Emerging Destructive Technologies", "before_words": 380, "evidence_assigned": 5},
             ])
        t += 1.0

        # Expansion pass
        emit(f, "evidence", "synthesize", t,
             action="expansion_pass",
             count=1,
             total_words=8400,
             total_citations=102,
             thin_sections=["Introduction: The PFAS Challenge", "Emerging Destructive Technologies"])
        t += 1.0

        # Second quality gate — passes
        emit(f, "quality_gate", "synthesize", t,
             gate="post_synthesis_final",
             passed=True,
             quality_gate_result="passed",
             expansion_passes=1,
             total_words=8400,
             total_citations=102,
             unique_sources=28)
        t += 0.5

        # ============================================================
        # WAVE 4.3: Citation mapping full
        # ============================================================
        full_mapping = []
        for i in range(28):
            full_mapping.append({
                "evidence_id": f"ev_{i:04d}abcdef{i:04d}",
                "citation_number": i + 1,
                "source_url": f"https://source-{i}.example.com/paper",
                "source_title": [
                    "GAC Performance for PFAS Removal in Municipal Systems",
                    "Ion Exchange Resin Selectivity for Short-Chain PFAS",
                    "Reverse Osmosis PFAS Rejection Mechanisms",
                    "EPA PFAS MCL Final Rule Technical Support Document",
                    "Lifecycle Cost Analysis of PFAS Treatment Technologies",
                ][i % 5] + f" ({i + 1})",
            })

        merge_pairs = [
            {"original_eid": "ev_0047abcdef0047", "representative_eid": "ev_0005abcdef0005"},
            {"original_eid": "ev_0089abcdef0089", "representative_eid": "ev_0012abcdef0012"},
            {"original_eid": "ev_0067abcdef0067", "representative_eid": "ev_0022abcdef0022"},
        ]

        ungrounded = [
            {"evidence_id": "ev_0105abcdef0105", "section_id": "s5"},
            {"evidence_id": "ev_0108abcdef0108", "section_id": "s7"},
        ]

        emit(f, "evidence", "synthesize", t,
             action="citation_mapping_full",
             count=28,
             full_mapping=full_mapping,
             merge_pairs=merge_pairs,
             ungrounded=ungrounded)
        t += 0.5

        # Citation audit
        emit(f, "evidence", "synthesize", t,
             action="citation_audit",
             count=102,
             grounded=98,
             stripped=4,
             unique_sources=28,
             mapping=full_mapping[:30])
        t += 0.5

        # Report assembled
        emit(f, "evidence", "synthesize", t,
             action="report_assembled",
             count=8400,
             sections=8,
             total_citations=102,
             bibliography=[
                 {"key": f"src_{i}", "url": f"https://source-{i}.example.com", "source_type": "journal_article" if i < 15 else "web", "formatted": f"[{i+1}] Author et al. ({2023 + i%3}). Title of paper {i+1}. Journal Name.", "num": i+1}
                 for i in range(28)
             ],
             section_titles=[{"id": sid, "title": title} for sid, title, _, _ in sections_data],
             full_report="# PFAS Removal Technologies for Municipal Drinking Water\n\n## 1. Introduction\n\nPer- and polyfluoroalkyl substances (PFAS) represent one of the most significant emerging contaminant challenges facing municipal water utilities...\n\n## 2. Granular Activated Carbon Treatment\n\nGAC has emerged as the most widely deployed technology for PFAS removal [1][2][3]...\n\n*(Full synthetic report truncated for test purposes)*")
        t += 1.0

        # LLM detail for synthesis (WAVE 1.3)
        emit(f, "llm_detail", "synthesize", t,
             call_type="section_write",
             model="moonshotai/kimi-k2-instruct",
             temperature=0.6,
             max_tokens=8192,
             reasoning_enabled=False,
             response_format="",
             prompt_messages=[
                 {"role": "system", "content": "You are an expert scientific writer. Write a comprehensive, well-cited section for a research report on PFAS water treatment technologies. Every factual claim MUST include a [CITE:evidence_id] reference. Use formal academic tone."},
                 {"role": "user", "content": "Write section 2: 'Granular Activated Carbon (GAC) Treatment'\n\nEvidence to cite:\n- ev_0001: GAC achieves >95% PFOA/PFOS removal at EBCT 10-15 min [source: doi.org/10.1021/acs.est.3c09876]\n- ev_0002: Breakthrough occurs at 15,000-30,000 bed volumes depending on water matrix [source: epa.gov/pfas]\n- ev_0003: Virgin GAC costs $1,500-3,000/ton; reactivation recovers 85-90% capacity [source: awwa.org]\n...(18 evidence pieces total)\n\nTarget: 1200 words minimum. Cite ALL evidence."},
             ],
             response_content="## Granular Activated Carbon (GAC) Treatment\n\nGranular activated carbon has emerged as the most widely deployed technology for PFAS removal from municipal drinking water supplies [CITE:ev_0001]. Multiple peer-reviewed studies have demonstrated that properly designed GAC contactors achieve greater than 95% removal of long-chain PFAS compounds including PFOA and PFOS at empty bed contact times (EBCT) of 10-15 minutes [CITE:ev_0001][CITE:ev_0002]...",
             response_reasoning="",
             input_tokens=4200,
             output_tokens=2400,
             reasoning_tokens=0,
             duration_ms=15000,
             cost_usd=0.0156)
        t += 0.5

        emit(f, "node_end", "synthesize", t, duration_ms=120000, total_words=8400)
        t += 1.0

        # ============================================================
        # Evidence detail (individual pieces)
        # ============================================================
        detail_items = []
        for i in range(50):
            tier = "gold" if i < 8 else "silver" if i < 25 else "bronze"
            detail_items.append({
                "id": f"ev_{i:04d}abcdef{i:04d}",
                "tier": tier,
                "relevance": round(0.85 - i * 0.01, 2),
                "statement": scoring_data[i]["statement"] if i < len(scoring_data) else "Evidence statement",
                "quote": f"\"Direct quote from source {i} supporting this evidence piece\"" if i < 30 else "",
                "source_url": f"https://source-{i % 20}.example.com/paper-{i}",
                "source_title": f"Source Paper Title {i}",
                "perspective": ["technical", "economic", "regulatory", "environmental", "public_health"][i % 5],
            })
        emit(f, "evidence", "analyze", t,
             action="evidence_detail",
             count=50,
             items=detail_items)
        t += 0.5

    file_size = os.path.getsize(OUTPUT)
    event_count = sum(1 for _ in open(OUTPUT, encoding="utf-8"))
    print(f"Wrote {event_count} events to {OUTPUT} ({file_size:,} bytes / {file_size/1024:.1f} KB)")
    print(f"Event types included:")
    print(f"  - pipeline_start (WAVE 1)")
    print(f"  - llm_detail x2 (WAVE 1)")
    print(f"  - search_result with URLs/titles/snippets (WAVE 2)")
    print(f"  - search_result cached/fallback (WAVE 2)")
    print(f"  - ddg_fallback_summary (WAVE 2)")
    print(f"  - tier_scoring_detail x126 evidence (WAVE 3)")
    print(f"  - dedup_detail with pairs (WAVE 3)")
    print(f"  - extraction_batch x7 (WAVE 3)")
    print(f"  - blocked/paywall_skip fetch (WAVE 3)")
    print(f"  - verification_context x112 claims (WAVE 4)")
    print(f"  - citation_mapping_full (WAVE 4)")
    print(f"  - expansion_detail (WAVE 4)")
    print(f"  - interview_complete x5 + interview_failed x1 (WAVE 4)")
    print(f"  - quality_gate, clustering, report_outline, section writes, etc.")


if __name__ == "__main__":
    main()
