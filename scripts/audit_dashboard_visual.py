"""
Visual audit of the POLARIS Live Dashboard.

Starts the live server, injects synthetic trace events covering ALL enriched
data types, takes full-page screenshots of every tab + interactive states,
and produces a JSON report with findings.

Run: python scripts/audit_dashboard_visual.py
Output: outputs/dashboard_audit/
"""

import json
import os
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
OUTPUT_DIR = Path("outputs/dashboard_audit")
SCREENSHOT_WIDTH = 1400
SCREENSHOT_HEIGHT = 900

# ---------------------------------------------------------------------------
# Synthetic events — comprehensive set covering ALL enriched data
# ---------------------------------------------------------------------------
SYNTHETIC_EVENTS = [
    {"type": "node_start", "node": "plan", "vid": "PG_AUDIT_001", "ts": "2026-02-26T10:00:00Z", "iteration": 1},
    {"type": "node_end", "node": "plan", "duration_ms": 5200, "vid": "PG_AUDIT_001", "ts": "2026-02-26T10:00:05Z", "query_count": 25},
    {"type": "node_start", "node": "search", "vid": "PG_AUDIT_001", "ts": "2026-02-26T10:00:06Z"},
    {"type": "search_result", "engine": "serper", "query": "PFAS treatment granular activated carbon efficiency drinking water", "result_count": 10, "vid": "PG_AUDIT_001", "ts": "2026-02-26T10:00:07Z"},
    {"type": "search_result", "engine": "serper", "query": "PFOS PFOA removal mechanisms adsorption ion exchange", "result_count": 8, "vid": "PG_AUDIT_001", "ts": "2026-02-26T10:00:08Z"},
    {"type": "search_result", "engine": "s2", "query": "granular activated carbon PFAS removal efficiency meta-analysis", "result_count": 5, "vid": "PG_AUDIT_001", "ts": "2026-02-26T10:00:09Z"},
    {"type": "search_result", "engine": "exa", "query": "PFAS water treatment technology comparison 2024 2025", "result_count": 7, "vid": "PG_AUDIT_001", "ts": "2026-02-26T10:00:10Z"},
    {"type": "search_result", "engine": "s2", "query": "ion exchange resin PFAS short chain removal", "result_count": 4, "vid": "PG_AUDIT_001", "ts": "2026-02-26T10:00:11Z"},
    {"type": "search_result", "engine": "tavily", "query": "EPA PFAS treatment guidelines municipal water", "result_count": 6, "vid": "PG_AUDIT_001", "ts": "2026-02-26T10:00:12Z"},
    {"type": "search_result", "engine": "ddg", "query": "PFAS remediation cost analysis lifecycle", "result_count": 3, "vid": "PG_AUDIT_001", "ts": "2026-02-26T10:00:13Z"},
    {"type": "fetch", "url": "https://nature.com/articles/s41545-024-00312-x", "status": "success", "content_len": 42000, "method": "jina", "vid": "PG_AUDIT_001", "ts": "2026-02-26T10:00:15Z"},
    {"type": "fetch", "url": "https://pubs.acs.org/doi/10.1021/acs.est.3c07890", "status": "success", "content_len": 38000, "method": "jina", "vid": "PG_AUDIT_001", "ts": "2026-02-26T10:00:16Z"},
    {"type": "fetch", "url": "https://epa.gov/water/pfas-treatment-technologies", "status": "success", "content_len": 25000, "method": "trafilatura", "vid": "PG_AUDIT_001", "ts": "2026-02-26T10:00:17Z"},
    {"type": "fetch", "url": "https://sciencedirect.com/science/article/pii/S0043135424001234", "status": "snippet_fallback", "content_len": 1200, "method": "trafilatura", "vid": "PG_AUDIT_001", "ts": "2026-02-26T10:00:18Z"},
    {"type": "fetch", "url": "https://mdpi.com/2073-4441/15/8/1456", "status": "success", "content_len": 31000, "method": "firecrawl", "vid": "PG_AUDIT_001", "ts": "2026-02-26T10:00:19Z"},
    {"type": "fetch", "url": "https://doi.org/10.1016/j.watres.2024.121890", "status": "fail", "content_len": 0, "method": "jina", "vid": "PG_AUDIT_001", "ts": "2026-02-26T10:00:20Z"},
    {"type": "fetch", "url": "https://awwa.org/resources/pfas-treatment-fact-sheet", "status": "success", "content_len": 18000, "method": "trafilatura", "vid": "PG_AUDIT_001", "ts": "2026-02-26T10:00:21Z"},
    {"type": "fetch", "url": "https://ncbi.nlm.nih.gov/pmc/articles/PMC10234567", "status": "snippet_fallback", "content_len": 950, "method": "trafilatura", "vid": "PG_AUDIT_001", "ts": "2026-02-26T10:00:22Z"},
    {"type": "node_end", "node": "search", "duration_ms": 16000, "vid": "PG_AUDIT_001", "ts": "2026-02-26T10:00:22Z"},
    {"type": "node_start", "node": "storm_interviews", "vid": "PG_AUDIT_001", "ts": "2026-02-26T10:00:23Z"},
    {"type": "llm_call", "call_type": "perspective_discovery", "perspectives": ["Environmental Chemist", "Water Treatment Engineer", "Public Health Epidemiologist", "Regulatory Policy Analyst", "Municipal Water Operator"], "vid": "PG_AUDIT_001", "ts": "2026-02-26T10:00:24Z"},
    {"type": "storm_transcript", "persona": "Environmental Chemist", "round": 1, "question": "What are the primary mechanisms by which granular activated carbon adsorbs PFAS compounds, and how do molecular properties affect removal efficiency?", "answer": "Granular activated carbon (GAC) removes PFAS primarily through hydrophobic interactions between the fluorinated carbon chains and the carbon surface. Longer-chain PFAS (C8+) like PFOS and PFOA show significantly higher adsorption due to stronger hydrophobic driving forces. Short-chain PFAS (C4-C6) are more hydrophilic and have lower adsorption capacity, typically achieving only 30-50% removal versus >90% for long-chain compounds.", "sources": ["nature.com", "pubs.acs.org"], "key_findings": ["GAC removes >90% of PFOS/PFOA via hydrophobic adsorption", "Short-chain PFAS (C4-C6) only 30-50% removal", "Bed life decreases 40-60% in presence of NOM"], "expertise": "PFAS remediation and environmental chemistry specialist with 15 years research experience", "question_focus": "Adsorption mechanisms, chain-length effects, and competitive adsorption with NOM", "vid": "PG_AUDIT_001", "ts": "2026-02-26T10:00:35Z"},
    {"type": "storm_transcript", "persona": "Water Treatment Engineer", "round": 1, "question": "How does GAC compare to ion exchange resins in terms of operational efficiency and cost for municipal-scale PFAS treatment?", "answer": "In our plant-scale comparisons, single-use IX resins achieve 95-99% removal of both long and short-chain PFAS, but at 2-3x the media cost of GAC. GAC is more cost-effective for long-chain dominated contamination profiles. The key trade-off is that GAC requires more frequent replacement (6-12 months vs 12-24 months for IX) but has lower disposal costs since spent GAC can be thermally reactivated.", "sources": ["epa.gov", "awwa.org"], "key_findings": ["IX resins: 95-99% removal all chain lengths, 2-3x media cost", "GAC: more cost-effective for long-chain dominant profiles", "GAC bed life: 6-12 months, IX: 12-24 months", "Thermal reactivation possible for spent GAC"], "expertise": "20 years designing and operating municipal water treatment plants", "question_focus": "Operational performance metrics, cost comparisons, and practical implementation challenges", "vid": "PG_AUDIT_001", "ts": "2026-02-26T10:00:50Z"},
    {"type": "storm_transcript", "persona": "Public Health Epidemiologist", "round": 1, "question": "What health risks are associated with PFAS exposure at current regulatory thresholds, and how effective are treatment technologies at meeting proposed limits?", "answer": "The EPA's 2024 MCLs of 4 ppt for PFOS and PFOA represent a dramatic tightening from previous advisory levels. Epidemiological evidence links PFAS exposure to thyroid disease, immunosuppression, and several cancers. At these ultra-low limits, only advanced treatment trains combining GAC with IX or nanofiltration consistently achieve compliance. Single-technology approaches often fall short for the full suite of regulated PFAS.", "sources": ["epa.gov", "ncbi.nlm.nih.gov"], "key_findings": ["EPA 2024 MCLs: 4 ppt PFOS/PFOA", "Health links: thyroid disease, immunosuppression, cancers", "Multi-barrier treatment needed for 4 ppt compliance"], "expertise": "Environmental epidemiology focusing on drinking water contaminants", "question_focus": "Health outcome data, regulatory threshold adequacy, and treatment effectiveness at new limits", "vid": "PG_AUDIT_001", "ts": "2026-02-26T10:01:05Z"},
    {"type": "node_end", "node": "storm_interviews", "duration_ms": 42000, "vid": "PG_AUDIT_001", "ts": "2026-02-26T10:01:05Z"},
    {"type": "node_start", "node": "analyze", "vid": "PG_AUDIT_001", "ts": "2026-02-26T10:01:06Z"},
    {"type": "evidence", "action": "extracted", "count": 156, "gold": 28, "silver": 85, "bronze": 43, "sources_fetched": 8, "vid": "PG_AUDIT_001", "ts": "2026-02-26T10:01:30Z"},
    {"type": "evidence", "action": "relevance_scored", "count": 156, "mean_relevance": 0.72, "vid": "PG_AUDIT_001", "ts": "2026-02-26T10:01:35Z"},
    {"type": "evidence", "action": "offtopic_filtered", "count": 138, "removed": 18, "threshold": 0.35, "vid": "PG_AUDIT_001", "ts": "2026-02-26T10:01:36Z"},
    {"type": "evidence", "action": "evidence_detail", "count": 8, "items": [
        {"id": "ev_pfas_001", "statement": "GAC removes >90% of PFOS and PFOA from drinking water at standard empty bed contact times of 10-20 minutes", "quote": "Our pilot-scale results demonstrate 93.2% removal of PFOS and 91.8% removal of PFOA using bituminous GAC at EBCT of 15 minutes", "source_url": "https://nature.com/articles/s41545-024-00312-x", "source_title": "Pilot-Scale GAC Treatment for PFAS Removal", "tier": "GOLD", "relevance": 0.95, "perspective": "Environmental Chemist"},
        {"id": "ev_pfas_002", "statement": "Short-chain PFAS compounds (C4-C6) show significantly reduced GAC adsorption compared to long-chain PFAS", "quote": "Short-chain PFBA and PFHxA showed only 32% and 47% removal respectively, compared to >90% for PFOS", "source_url": "https://pubs.acs.org/doi/10.1021/acs.est.3c07890", "source_title": "Chain-Length Effects on PFAS Adsorption", "tier": "GOLD", "relevance": 0.93, "perspective": "Environmental Chemist"},
        {"id": "ev_pfas_003", "statement": "Ion exchange resins achieve 95-99% removal of both long and short-chain PFAS but at 2-3x the media cost of GAC", "quote": "PFAS-selective IX resins demonstrated 97.3% total PFAS removal at 2.4x the annualized media cost compared to GAC treatment", "source_url": "https://epa.gov/water/pfas-treatment-technologies", "source_title": "EPA PFAS Treatment Technology Guide", "tier": "GOLD", "relevance": 0.91, "perspective": "Water Treatment Engineer"},
        {"id": "ev_pfas_004", "statement": "Thermal reactivation of spent GAC recovers 85-90% of adsorption capacity while reducing disposal costs by 60%", "quote": "Thermally reactivated GAC retained 87% of virgin carbon capacity after three regeneration cycles", "source_url": "https://mdpi.com/2073-4441/15/8/1456", "source_title": "GAC Regeneration Economics", "tier": "SILVER", "relevance": 0.84, "perspective": "Water Treatment Engineer"},
        {"id": "ev_pfas_005", "statement": "EPA's 2024 MCLs of 4 ppt for PFOS and PFOA require multi-barrier treatment approaches for consistent compliance", "quote": "Achieving the 4 ng/L PFOS MCL consistently required combined GAC + anion exchange treatment trains", "source_url": "https://epa.gov/water/pfas-treatment-technologies", "source_title": "EPA PFAS Treatment Technology Guide", "tier": "GOLD", "relevance": 0.89, "perspective": "Regulatory Policy Analyst"},
        {"id": "ev_pfas_006", "statement": "Natural organic matter (NOM) competition reduces GAC bed life for PFAS removal by 40-60%", "quote": "In high-NOM source waters (TOC > 4 mg/L), GAC bed life for PFAS decreased from 18 months to 7-11 months", "source_url": "https://nature.com/articles/s41545-024-00312-x", "source_title": "Pilot-Scale GAC Treatment for PFAS Removal", "tier": "SILVER", "relevance": 0.82, "perspective": "Environmental Chemist"},
        {"id": "ev_pfas_007", "statement": "Epidemiological evidence links PFAS exposure to thyroid disease, immunosuppression, and several cancers", "quote": "Meta-analysis of 23 cohort studies confirmed positive associations between serum PFOS levels and thyroid dysfunction (OR 1.32, 95% CI 1.15-1.52)", "source_url": "https://ncbi.nlm.nih.gov/pmc/articles/PMC10234567", "source_title": "PFAS Health Effects Meta-Analysis", "tier": "SILVER", "relevance": 0.78, "perspective": "Public Health Epidemiologist"},
        {"id": "ev_pfas_008", "statement": "Municipal treatment costs for PFAS compliance range from $0.50-$2.00 per 1000 gallons depending on technology and influent concentration", "quote": "", "source_url": "https://awwa.org/resources/pfas-treatment-fact-sheet", "source_title": "AWWA PFAS Treatment Cost Summary", "tier": "BRONZE", "relevance": 0.68, "perspective": "Municipal Water Operator"},
    ], "vid": "PG_AUDIT_001", "ts": "2026-02-26T10:01:40Z"},
    {"type": "node_end", "node": "analyze", "duration_ms": 55000, "evidence_count": 138, "vid": "PG_AUDIT_001", "ts": "2026-02-26T10:02:01Z"},
    {"type": "node_start", "node": "verify", "vid": "PG_AUDIT_001", "ts": "2026-02-26T10:02:02Z"},
    {"type": "llm_call", "call_type": "verification_batch", "batch_size": 5, "supported": 4, "partial": 1, "not_supported": 0, "claims": [
        {"id": "ev_pfas_001", "verdict": "SUPPORTED", "confidence": 0.96, "faithful": True, "statement": "GAC removes >90% of PFOS and PFOA from drinking water at standard EBCT"},
        {"id": "ev_pfas_002", "verdict": "SUPPORTED", "confidence": 0.94, "faithful": True, "statement": "Short-chain PFAS show significantly reduced GAC adsorption vs long-chain"},
        {"id": "ev_pfas_003", "verdict": "SUPPORTED", "confidence": 0.91, "faithful": True, "statement": "IX resins achieve 95-99% removal at 2-3x the media cost of GAC"},
        {"id": "ev_pfas_005", "verdict": "SUPPORTED", "confidence": 0.89, "faithful": True, "statement": "EPA 2024 MCLs require multi-barrier treatment for compliance"},
        {"id": "ev_pfas_008", "verdict": "PARTIAL", "confidence": 0.52, "faithful": False, "statement": "Municipal treatment costs range $0.50-$2.00 per 1000 gallons"},
    ], "vid": "PG_AUDIT_001", "ts": "2026-02-26T10:02:30Z"},
    {"type": "llm_call", "call_type": "verification_batch", "batch_size": 3, "supported": 2, "partial": 0, "not_supported": 1, "claims": [
        {"id": "ev_pfas_004", "verdict": "SUPPORTED", "confidence": 0.87, "faithful": True, "statement": "Thermal reactivation recovers 85-90% of GAC adsorption capacity"},
        {"id": "ev_pfas_006", "verdict": "SUPPORTED", "confidence": 0.83, "faithful": True, "statement": "NOM competition reduces GAC bed life by 40-60%"},
        {"id": "ev_pfas_007", "verdict": "NOT_SUPPORTED", "confidence": 0.35, "faithful": False, "statement": "PFAS linked to thyroid disease via meta-analysis OR 1.32"},
    ], "vid": "PG_AUDIT_001", "ts": "2026-02-26T10:02:45Z"},
    {"type": "node_end", "node": "verify", "duration_ms": 43000, "vid": "PG_AUDIT_001", "ts": "2026-02-26T10:02:45Z"},
    {"type": "node_start", "node": "evaluate", "vid": "PG_AUDIT_001", "ts": "2026-02-26T10:02:46Z"},
    {"type": "quality_gate", "gate": "faithfulness", "passed": True, "actual": 0.867, "threshold": 0.80, "vid": "PG_AUDIT_001", "ts": "2026-02-26T10:02:50Z"},
    {"type": "iteration_decision", "iteration": 1, "decision": "continue_to_synthesis", "vid": "PG_AUDIT_001", "ts": "2026-02-26T10:02:52Z"},
    {"type": "node_end", "node": "evaluate", "duration_ms": 6000, "vid": "PG_AUDIT_001", "ts": "2026-02-26T10:02:52Z"},
    {"type": "node_start", "node": "synthesize", "vid": "PG_AUDIT_001", "ts": "2026-02-26T10:02:53Z"},
    {"type": "evidence", "action": "clustering", "count": 5, "evidence_count": 138, "themes": [
        {"theme": "PFAS adsorption mechanisms and chain-length effects on GAC", "count": 32},
        {"theme": "Ion exchange resin technology and cost comparison", "count": 28},
        {"theme": "Regulatory standards and health risk assessment", "count": 24},
        {"theme": "GAC regeneration, lifecycle costs, and operational factors", "count": 18},
        {"theme": "Multi-barrier treatment train design for compliance", "count": 36},
    ], "vid": "PG_AUDIT_001", "ts": "2026-02-26T10:03:00Z"},
    {"type": "llm_call", "call_type": "section_write", "section_id": "s1", "word_count": 1250, "evidence_count": 12, "title": "PFAS Adsorption Mechanisms and Chain-Length Effects", "content": "## PFAS Adsorption Mechanisms and Chain-Length Effects\n\nGranular activated carbon (GAC) remains the most widely deployed technology for per- and polyfluoroalkyl substances (PFAS) removal from drinking water, primarily operating through hydrophobic interactions between fluorinated carbon chains and the activated carbon surface [1]. Pilot-scale studies demonstrate that GAC achieves **93.2% removal of PFOS** and **91.8% removal of PFOA** at standard empty bed contact times (EBCT) of 10-20 minutes [1].\n\n### Chain-Length Dependence\n\nThe effectiveness of GAC adsorption is strongly dependent on PFAS chain length. Long-chain compounds (C8+) such as PFOS and PFOA exhibit significantly higher adsorption due to stronger hydrophobic driving forces, routinely achieving >90% removal [2]. In contrast, short-chain PFAS compounds (C4-C6) show dramatically reduced removal efficiency:\n\n- **PFBA (C4):** 32% removal\n- **PFHxA (C6):** 47% removal  \n- **PFOS (C8):** >90% removal [2]\n\nThis chain-length dependence has critical implications for treatment plant design, as contamination profiles increasingly include short-chain PFAS from industrial substitution of legacy long-chain compounds.\n\n### Natural Organic Matter Competition\n\nA significant operational challenge is competitive adsorption by natural organic matter (NOM). In source waters with elevated total organic carbon (TOC > 4 mg/L), GAC bed life for PFAS removal decreases from approximately 18 months to 7-11 months, representing a **40-60% reduction** in effective service life [1]. This competition mechanism must be accounted for in treatment system sizing and media replacement scheduling.", "vid": "PG_AUDIT_001", "ts": "2026-02-26T10:03:30Z"},
    {"type": "llm_call", "call_type": "section_write", "section_id": "s2", "word_count": 980, "evidence_count": 9, "title": "Ion Exchange Resins: Performance and Cost Trade-offs", "content": "## Ion Exchange Resins: Performance and Cost Trade-offs\n\nPFAS-selective ion exchange (IX) resins represent the primary alternative to GAC for drinking water treatment, offering superior removal of both long and short-chain PFAS compounds. PFAS-selective IX resins demonstrate **97.3% total PFAS removal** across all chain lengths, compared to GAC's variable performance that degrades significantly for short-chain compounds [3].\n\n### Cost Comparison\n\nThe enhanced performance of IX resins comes at a premium, with annualized media costs approximately **2-3 times higher** than equivalent GAC treatment capacity [3]. However, IX resins offer longer bed life (12-24 months vs 6-12 months for GAC), partially offsetting the higher media cost through reduced replacement frequency.\n\n### Regeneration Economics\n\nUnlike single-use IX resins, spent GAC can be thermally reactivated, recovering **85-90% of virgin carbon adsorption capacity** while reducing disposal costs by approximately 60% [4]. After three regeneration cycles, thermally reactivated GAC retained 87% of its original capacity, making it economically viable for utilities with access to reactivation facilities.", "vid": "PG_AUDIT_001", "ts": "2026-02-26T10:03:50Z"},
    {"type": "llm_call", "call_type": "section_write", "section_id": "s3", "word_count": 870, "evidence_count": 7, "title": "Regulatory Framework and Health Implications", "content": "## Regulatory Framework and Health Implications\n\nThe regulatory landscape for PFAS in drinking water has undergone a dramatic shift with the EPA's 2024 establishment of Maximum Contaminant Levels (MCLs) at **4 parts per trillion (ppt) for PFOS and PFOA** [5]. These ultra-low limits represent a fundamental challenge for water treatment systems.\n\n### Health Evidence\n\nThe stringent regulatory action is supported by growing epidemiological evidence linking PFAS exposure to adverse health outcomes, including thyroid disease, immunosuppression, and several cancers [7].\n\n### Treatment Implications\n\nMeeting the 4 ppt MCLs consistently requires **multi-barrier treatment approaches**, as single-technology solutions often fail to achieve reliable compliance across varying water quality conditions [5]. Combined GAC and anion exchange treatment trains have emerged as the most reliable configuration for consistent compliance.", "vid": "PG_AUDIT_001", "ts": "2026-02-26T10:04:10Z"},
    {"type": "evidence", "action": "citation_audit", "count": 24, "grounded": 21, "stripped": 3, "unique_sources": 6, "mapping": [
        {"num": 1, "url": "https://nature.com/articles/s41545-024-00312-x", "title": "Pilot-Scale GAC Treatment for PFAS Removal"},
        {"num": 2, "url": "https://pubs.acs.org/doi/10.1021/acs.est.3c07890", "title": "Chain-Length Effects on PFAS Adsorption"},
        {"num": 3, "url": "https://epa.gov/water/pfas-treatment-technologies", "title": "EPA PFAS Treatment Technology Guide"},
        {"num": 4, "url": "https://mdpi.com/2073-4441/15/8/1456", "title": "GAC Regeneration Economics"},
        {"num": 5, "url": "https://epa.gov/water/pfas-treatment-technologies", "title": "EPA PFAS Treatment Technology Guide"},
        {"num": 6, "url": "https://awwa.org/resources/pfas-treatment-fact-sheet", "title": "AWWA PFAS Treatment Cost Summary"},
        {"num": 7, "url": "https://ncbi.nlm.nih.gov/pmc/articles/PMC10234567", "title": "PFAS Health Effects Meta-Analysis"},
    ], "vid": "PG_AUDIT_001", "ts": "2026-02-26T10:04:15Z"},
    {"type": "evidence", "action": "report_assembled", "count": 10200, "sections": 3, "total_citations": 24, "bibliography_entries": 7, "bibliography": [
        {"key": "chen_2024_gac", "url": "https://nature.com/articles/s41545-024-00312-x", "source_type": "academic", "formatted": "Chen et al. (2024) Pilot-Scale GAC Treatment for PFAS Removal from Drinking Water. Nature Water, 2(4), 312-325."},
        {"key": "zhang_2023_chain", "url": "https://pubs.acs.org/doi/10.1021/acs.est.3c07890", "source_type": "academic", "formatted": "Zhang & Liu (2023) Chain-Length Effects on PFAS Adsorption by Activated Carbon. Environ. Sci. Technol., 57(42), 15890-15901."},
        {"key": "epa_2024_pfas", "url": "https://epa.gov/water/pfas-treatment-technologies", "source_type": "government", "formatted": "US EPA (2024) PFAS Treatment Technologies for Drinking Water: Technical Guide."},
        {"key": "wang_2023_regen", "url": "https://mdpi.com/2073-4441/15/8/1456", "source_type": "academic", "formatted": "Wang et al. (2023) Economics of GAC Thermal Reactivation for PFAS Treatment. Water, 15(8), 1456."},
        {"key": "awwa_2024_cost", "url": "https://awwa.org/resources/pfas-treatment-fact-sheet", "source_type": "industry", "formatted": "AWWA (2024) PFAS Treatment Cost Summary for Water Utilities."},
        {"key": "johnson_2024_health", "url": "https://ncbi.nlm.nih.gov/pmc/articles/PMC10234567", "source_type": "academic", "formatted": "Johnson et al. (2024) PFAS Exposure and Health Outcomes: A Systematic Review and Meta-Analysis. Environ. Health Perspect., 132(3)."},
    ], "section_titles": [
        {"id": "s1", "title": "PFAS Adsorption Mechanisms and Chain-Length Effects", "words": 1250},
        {"id": "s2", "title": "Ion Exchange Resins: Performance and Cost Trade-offs", "words": 980},
        {"id": "s3", "title": "Regulatory Framework and Health Implications", "words": 870},
    ], "vid": "PG_AUDIT_001", "ts": "2026-02-26T10:04:20Z"},
    {"type": "quality_gate", "gate": "word_count", "passed": True, "actual": 10200, "threshold": 2000, "vid": "PG_AUDIT_001", "ts": "2026-02-26T10:04:22Z"},
    {"type": "quality_gate", "gate": "citation_count", "passed": True, "actual": 24, "threshold": 5, "vid": "PG_AUDIT_001", "ts": "2026-02-26T10:04:23Z"},
    {"type": "quality_gate", "gate": "unique_sources", "passed": True, "actual": 6, "threshold": 3, "vid": "PG_AUDIT_001", "ts": "2026-02-26T10:04:24Z"},
    {"type": "quality_gate", "gate": "post_synthesis_final", "passed": True, "total_words": 10200, "total_citations": 24, "unique_sources": 6, "expansion_pass": 1, "quality_gate_result": "PASS - all gates satisfied", "vid": "PG_AUDIT_001", "ts": "2026-02-26T10:04:25Z"},
    {"type": "node_end", "node": "synthesize", "duration_ms": 92000, "total_words": 10200, "faithfulness": 0.867, "vid": "PG_AUDIT_001", "ts": "2026-02-26T10:04:25Z"},
    # ---- 100% Visibility Events ----
    # Query Plan
    {"type": "evidence", "action": "query_plan", "count": 25,
     "search_strategy": "broad_then_deep",
     "key_concepts": ["PFAS removal", "activated carbon", "water treatment", "ion exchange"],
     "queries": [
         {"query": "PFAS removal activated carbon", "perspective": "Environmental Chemist", "intent": "mechanisms", "source_preference": "academic"},
         {"query": "ion exchange PFAS treatment", "perspective": "Water Engineer", "intent": "comparison", "source_preference": "web"},
     ],
     "perspective_distribution": {"Environmental Chemist": 8, "Water Engineer": 6, "Public Health": 5, "Regulatory": 4, "Industry": 2},
     "missing_perspectives": ["Community Advocate", "Toxicologist"],
     "vid": "PG_AUDIT_001", "ts": "2026-02-26T10:00:04Z"},
    # Tier Signal Distribution
    {"type": "evidence", "action": "tier_signal_distribution", "count": 156,
     "signal_stats": {
         "semantic_relevance": {"min": 0.15, "median": 0.68, "max": 0.97, "count": 156},
         "source_authority": {"min": 0.08, "median": 0.52, "max": 0.94, "count": 156},
         "content_density": {"min": 0.22, "median": 0.61, "max": 0.89, "count": 156},
         "freshness": {"min": 0.10, "median": 0.72, "max": 1.00, "count": 156},
         "nli_grounding": {"min": 0.00, "median": 0.55, "max": 0.91, "count": 140},
     }, "vid": "PG_AUDIT_001", "ts": "2026-02-26T10:01:32Z"},
    # Dedup Summary
    {"type": "evidence", "action": "dedup_summary", "count": 138,
     "pre_dedup": 156, "post_dedup": 138,
     "vid": "PG_AUDIT_001", "ts": "2026-02-26T10:01:33Z"},
    # Fetch Summary
    {"type": "evidence", "action": "fetch_summary", "count": 8,
     "total_attempted": 12, "success": 6, "snippet_fallback": 2, "failed": 4,
     "vid": "PG_AUDIT_001", "ts": "2026-02-26T10:01:34Z"},
    # NLI Verification Detail
    {"type": "evidence", "action": "nli_verification_detail", "count": 100,
     "faithful_count": 87, "faithfulness_pct": 87.0, "disputed_count": 13,
     "claims_detail": [
         {"statement": "GAC removes >90% of PFOS from drinking water", "is_faithful": True, "nli_score": 0.95},
         {"statement": "IX resins achieve 95-99% total PFAS removal", "is_faithful": True, "nli_score": 0.88},
         {"statement": "Unverified cost claim about treatment scaling", "is_faithful": False, "nli_score": 0.28},
     ], "vid": "PG_AUDIT_001", "ts": "2026-02-26T10:02:35Z"},
    # Cross-Reference Groups
    {"type": "evidence", "action": "cross_reference_groups", "count": 4,
     "groups": [
         {"similarity": 0.93, "evidence_ids": ["ev_pfas_001", "ev_pfas_006"]},
         {"similarity": 0.86, "evidence_ids": ["ev_pfas_003", "ev_pfas_005"]},
     ], "vid": "PG_AUDIT_001", "ts": "2026-02-26T10:02:40Z"},
    # Report Outline
    {"type": "evidence", "action": "report_outline", "count": 3,
     "title": "Comprehensive Analysis of PFAS Treatment Technologies",
     "sections": [
         {"title": "PFAS Adsorption Mechanisms", "evidence_count": 12, "target_words": 800, "description": "GAC adsorption pathways"},
         {"title": "Ion Exchange Technology Comparison", "evidence_count": 9, "target_words": 700, "description": "Comparing GAC and IX"},
         {"title": "Regulatory Framework and Health Effects", "evidence_count": 7, "target_words": 600, "description": "EPA regulations"},
     ], "vid": "PG_AUDIT_001", "ts": "2026-02-26T10:03:05Z"},
    # Section-Evidence Map
    {"type": "evidence", "action": "section_evidence_map", "count": 3,
     "mapping": [
         {"section_id": "section_0", "evidence_count": 12},
         {"section_id": "section_1", "evidence_count": 9},
         {"section_id": "section_2", "evidence_count": 7},
     ], "vid": "PG_AUDIT_001", "ts": "2026-02-26T10:04:16Z"},
    # Hallucination Audit
    {"type": "evidence", "action": "hallucination_audit", "count": 3,
     "sections": [
         {"section_id": "s1", "title": "PFAS Adsorption Mechanisms", "hallucination_ratio": 0.08, "needs_rewrite": False, "flagged_spans": 1},
         {"section_id": "s2", "title": "Ion Exchange Technology", "hallucination_ratio": 0.45, "needs_rewrite": True, "flagged_spans": 6},
         {"section_id": "s3", "title": "Regulatory Framework", "hallucination_ratio": 0.12, "needs_rewrite": False, "flagged_spans": 2},
     ], "vid": "PG_AUDIT_001", "ts": "2026-02-26T10:04:17Z"},
    # Evidence Conflicts
    {"type": "evidence", "action": "evidence_conflicts", "count": 1,
     "conflicts": [
         {"type": "contradiction", "score": 0.87, "statement_a": "GAC is more cost-effective for long-chain PFAS", "statement_b": "IX resins are more economical at municipal scale"},
     ], "vid": "PG_AUDIT_001", "ts": "2026-02-26T10:04:18Z"},
    # Expansion Pass
    {"type": "evidence", "action": "expansion_pass", "count": 1,
     "total_words": 3100, "total_citations": 24,
     "thin_sections": ["Regulatory Framework"],
     "vid": "PG_AUDIT_001", "ts": "2026-02-26T10:04:19Z"},
    # Gap Analysis Detail
    {"type": "evidence", "action": "gap_analysis_detail", "count": 138,
     "total_evidence": 138, "gold_count": 28, "faithfulness": 0.867,
     "needs_iteration": False,
     "gaps": ["Limited data on emerging PFAS treatment technologies", "Insufficient cost-benefit analysis for small utilities"],
     "gap_queries": ["emerging PFAS treatment technology review"],
     "perspective_coverage": {"Environmental Chemist": 32, "Water Engineer": 28, "Public Health": 18, "Regulatory": 12},
     "vid": "PG_AUDIT_001", "ts": "2026-02-26T10:02:51Z"},
    # Agentic Round Summary (2 rounds)
    {"type": "evidence", "action": "agentic_round_summary", "count": 1,
     "queries": 7, "web_results": 40, "academic_results": 9, "new_urls": 35, "total_urls": 35,
     "vid": "PG_AUDIT_001", "ts": "2026-02-26T10:00:14Z"},
    {"type": "evidence", "action": "agentic_round_summary", "count": 2,
     "queries": 5, "web_results": 20, "academic_results": 4, "new_urls": 12, "total_urls": 47,
     "vid": "PG_AUDIT_001", "ts": "2026-02-26T10:00:21Z"},
    # Agentic Search Complete
    {"type": "evidence", "action": "agentic_search_complete", "count": 2,
     "total_queries": 12, "total_urls": 47,
     "vid": "PG_AUDIT_001", "ts": "2026-02-26T10:00:22Z"},
    # Section Evidence Filtered
    {"type": "evidence", "action": "section_evidence_filtered", "count": 12,
     "section_id": "s1", "title": "PFAS Adsorption Mechanisms",
     "total_available": 138, "after_filter": 12,
     "vid": "PG_AUDIT_001", "ts": "2026-02-26T10:03:25Z"},
    # Report Assembled with full_report
    {"type": "evidence", "action": "report_assembled", "count": 10200, "sections": 3,
     "total_citations": 24, "bibliography_entries": 7,
     "full_report": "# Comprehensive Analysis of PFAS Treatment Technologies\n\n## 1. PFAS Adsorption Mechanisms\n\nGAC removes PFAS through hydrophobic interactions [1].\n\n## 2. Ion Exchange Technology\n\nIX resins offer superior short-chain PFAS removal [3].\n\n## 3. Regulatory Framework\n\nEPA 2024 MCLs require multi-barrier treatment [5].",
     "bibliography": [
         {"key": "chen_2024", "url": "https://nature.com/articles/s41545-024-00312-x", "source_type": "academic", "formatted": "Chen et al. (2024) PFAS Removal by GAC. Nature Water."},
         {"key": "epa_2024", "url": "https://epa.gov/water/pfas-treatment-technologies", "source_type": "government", "formatted": "US EPA (2024) PFAS Treatment Guide."},
     ],
     "section_titles": [
         {"id": "s1", "title": "PFAS Adsorption Mechanisms", "words": 1250},
         {"id": "s2", "title": "Ion Exchange Technology", "words": 980},
         {"id": "s3", "title": "Regulatory Framework", "words": 870},
     ], "vid": "PG_AUDIT_001", "ts": "2026-02-26T10:04:20Z"},
    # LLM Calls with model tracking
    {"type": "llm_call", "call_type": "plan", "model": "moonshotai/kimi-k2-instruct",
     "input_tokens": 2500, "output_tokens": 800, "cost_usd": 0.05,
     "vid": "PG_AUDIT_001", "ts": "2026-02-26T10:00:01Z"},
]


def find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]


def main():
    from playwright.sync_api import sync_playwright

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Start server
    port = find_free_port()
    trace_dir = Path("logs")
    trace_dir.mkdir(exist_ok=True)
    dummy_trace = trace_dir / "pg_trace_DASHBOARD_AUDIT.jsonl"
    dummy_trace.write_text("", encoding="utf-8")

    project_root = Path(__file__).resolve().parents[1]
    proc = subprocess.Popen(
        [sys.executable, "scripts/live_server.py", "--port", str(port), "--no-tunnel", "--trace", str(dummy_trace)],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        cwd=str(project_root),
    )

    url = f"http://localhost:{port}"
    print(f"Starting server on {url}...")

    for _ in range(20):
        try:
            urllib.request.urlopen(url, timeout=1)
            break
        except Exception:
            time.sleep(0.5)
    else:
        proc.kill()
        out = proc.stdout.read().decode(errors="replace")
        print(f"FAIL: Server did not start. Output:\n{out[:2000]}")
        return

    print("Server ready. Launching Chromium...")

    findings = []
    screenshots = []

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": SCREENSHOT_WIDTH, "height": SCREENSHOT_HEIGHT})

        js_errors = []
        page.on("console", lambda msg: js_errors.append({"type": msg.type, "text": msg.text}) if msg.type == "error" else None)
        page.on("pageerror", lambda exc: js_errors.append({"type": "pageerror", "text": str(exc)}))

        # Load page
        page.goto(url, wait_until="domcontentloaded")
        page.wait_for_timeout(2000)

        # Screenshot 1: Empty state
        path = str(OUTPUT_DIR / "01_empty_state.png")
        page.screenshot(path=path, full_page=False)
        screenshots.append(path)
        print(f"  [1/24] Empty state screenshot")

        # Inject all events
        for ev in SYNTHETIC_EVENTS:
            page.evaluate(f"processEvent({json.dumps(ev)})")
        page.wait_for_timeout(500)

        # Screenshot 2: Overview after events
        page.evaluate("switchTab('overview')")
        page.wait_for_timeout(300)
        path = str(OUTPUT_DIR / "02_overview_populated.png")
        page.screenshot(path=path, full_page=False)
        screenshots.append(path)
        print(f"  [2/24] Overview tab screenshot")

        # Screenshot 3: Queries
        page.evaluate("switchTab('queries')")
        page.wait_for_timeout(300)
        path = str(OUTPUT_DIR / "03_queries_tab.png")
        page.screenshot(path=path, full_page=False)
        screenshots.append(path)
        print(f"  [3/24] Queries tab screenshot")

        # Screenshot 4: Sources
        page.evaluate("switchTab('sources')")
        page.wait_for_timeout(300)
        path = str(OUTPUT_DIR / "04_sources_tab.png")
        page.screenshot(path=path, full_page=False)
        screenshots.append(path)
        print(f"  [4/24] Sources tab screenshot")

        # Screenshot 5: STORM
        page.evaluate("switchTab('storm')")
        page.wait_for_timeout(300)
        path = str(OUTPUT_DIR / "05_storm_tab.png")
        page.screenshot(path=path, full_page=False)
        screenshots.append(path)
        print(f"  [5/24] STORM tab screenshot")

        # Screenshot 6: Evidence
        page.evaluate("switchTab('evidence')")
        page.wait_for_timeout(300)
        path = str(OUTPUT_DIR / "06_evidence_tab.png")
        page.screenshot(path=path, full_page=False)
        screenshots.append(path)
        print(f"  [6/24] Evidence tab screenshot")

        # Screenshot 7: Evidence GOLD filter
        page.click('[data-tier="gold"]')
        page.wait_for_timeout(300)
        path = str(OUTPUT_DIR / "07_evidence_gold_filter.png")
        page.screenshot(path=path, full_page=False)
        screenshots.append(path)
        page.click('[data-tier="all"]')
        print(f"  [7/24] Evidence GOLD filter screenshot")

        # Screenshot 8: Report tab
        page.evaluate("switchTab('report')")
        page.wait_for_timeout(300)
        path = str(OUTPUT_DIR / "08_report_tab.png")
        page.screenshot(path=path, full_page=False)
        screenshots.append(path)
        print(f"  [8/24] Report tab screenshot")

        # Screenshot 9: Report with section expanded
        section_rows = page.query_selector_all(".section-row")
        if section_rows:
            section_rows[0].click()
            page.wait_for_timeout(500)
        path = str(OUTPUT_DIR / "09_report_section_expanded.png")
        page.screenshot(path=path, full_page=False)
        screenshots.append(path)
        print(f"  [9/24] Report section expanded screenshot")

        # Screenshot 10: Report scrolled to bibliography
        page.evaluate("document.getElementById('report-bibliography').scrollIntoView()")
        page.wait_for_timeout(300)
        path = str(OUTPUT_DIR / "10_report_bibliography.png")
        page.screenshot(path=path, full_page=False)
        screenshots.append(path)
        print(f"  [10/24] Report bibliography screenshot")

        # Screenshot 11: Trace tab
        page.evaluate("switchTab('trace')")
        page.wait_for_timeout(300)
        path = str(OUTPUT_DIR / "11_trace_tab.png")
        page.screenshot(path=path, full_page=False)
        screenshots.append(path)
        print(f"  [11/24] Trace tab screenshot")

        # Screenshot 12: Trace filtered to STORM
        page.click('[data-ttype="storm_transcript"]')
        page.wait_for_timeout(300)
        path = str(OUTPUT_DIR / "12_trace_storm_filter.png")
        page.screenshot(path=path, full_page=False)
        screenshots.append(path)
        print(f"  [12/24] Trace STORM filter screenshot")

        # Reset trace filter
        page.click('[data-ttype="all"]')
        page.wait_for_timeout(200)

        # Screenshot 13: Full Report tab
        page.evaluate("switchTab('fullreport')")
        page.wait_for_timeout(500)
        path = str(OUTPUT_DIR / "13_fullreport_tab.png")
        page.screenshot(path=path, full_page=False)
        screenshots.append(path)
        print(f"  [13/24] Full Report tab screenshot")

        # Screenshot 14: Overview with gap analysis + LLM usage
        page.evaluate("switchTab('overview')")
        page.wait_for_timeout(300)
        page.evaluate("document.getElementById('ov-gap-analysis').scrollIntoView()")
        page.wait_for_timeout(200)
        path = str(OUTPUT_DIR / "14_overview_gap_analysis.png")
        page.screenshot(path=path, full_page=False)
        screenshots.append(path)
        print(f"  [14/24] Overview gap analysis screenshot")

        # Screenshot 15: Overview LLM usage
        page.evaluate("document.getElementById('ov-llm-usage').scrollIntoView()")
        page.wait_for_timeout(200)
        path = str(OUTPUT_DIR / "15_overview_llm_usage.png")
        page.screenshot(path=path, full_page=False)
        screenshots.append(path)
        print(f"  [15/24] Overview LLM usage screenshot")

        # Screenshot 16: Queries research plan
        page.evaluate("switchTab('queries')")
        page.wait_for_timeout(300)
        path = str(OUTPUT_DIR / "16_queries_research_plan.png")
        page.screenshot(path=path, full_page=False)
        screenshots.append(path)
        print(f"  [16/24] Queries research plan screenshot")

        # Screenshot 17: Sources fetch pipeline
        page.evaluate("switchTab('sources')")
        page.wait_for_timeout(300)
        path = str(OUTPUT_DIR / "17_sources_fetch_pipeline.png")
        page.screenshot(path=path, full_page=False)
        screenshots.append(path)
        print(f"  [17/24] Sources fetch pipeline screenshot")

        # Screenshot 18: Evidence signal distribution
        page.evaluate("switchTab('evidence')")
        page.wait_for_timeout(300)
        path = str(OUTPUT_DIR / "18_evidence_signals.png")
        page.screenshot(path=path, full_page=False)
        screenshots.append(path)
        print(f"  [18/24] Evidence signal distribution screenshot")

        # Screenshot 19: Evidence NLI verification (scroll down)
        page.evaluate("document.getElementById('ev-nli-verification').scrollIntoView()")
        page.wait_for_timeout(200)
        path = str(OUTPUT_DIR / "19_evidence_nli_verification.png")
        page.screenshot(path=path, full_page=False)
        screenshots.append(path)
        print(f"  [19/24] Evidence NLI verification screenshot")

        # Screenshot 20: Report outline
        page.evaluate("switchTab('report')")
        page.wait_for_timeout(300)
        page.evaluate("document.getElementById('rpt-outline').scrollIntoView()")
        page.wait_for_timeout(200)
        path = str(OUTPUT_DIR / "20_report_outline.png")
        page.screenshot(path=path, full_page=False)
        screenshots.append(path)
        print(f"  [20/24] Report outline screenshot")

        # Screenshot 21: Report hallucination audit
        page.evaluate("document.getElementById('rpt-hallucination-audit').scrollIntoView()")
        page.wait_for_timeout(200)
        path = str(OUTPUT_DIR / "21_report_hallucination_audit.png")
        page.screenshot(path=path, full_page=False)
        screenshots.append(path)
        print(f"  [21/24] Report hallucination audit screenshot")

        # Screenshot 22: Report evidence conflicts
        page.evaluate("document.getElementById('rpt-evidence-conflicts').scrollIntoView()")
        page.wait_for_timeout(200)
        path = str(OUTPUT_DIR / "22_report_evidence_conflicts.png")
        page.screenshot(path=path, full_page=False)
        screenshots.append(path)
        print(f"  [22/24] Report evidence conflicts screenshot")

        # Screenshot 23: Report expansion history
        page.evaluate("document.getElementById('rpt-expansion-history').scrollIntoView()")
        page.wait_for_timeout(200)
        path = str(OUTPUT_DIR / "23_report_expansion_history.png")
        page.screenshot(path=path, full_page=False)
        screenshots.append(path)
        print(f"  [23/24] Report expansion history screenshot")

        # Screenshot 24: Evidence dedup + cross-ref
        page.evaluate("switchTab('evidence')")
        page.wait_for_timeout(300)
        page.evaluate("document.getElementById('ev-dedup-pipeline').scrollIntoView()")
        page.wait_for_timeout(200)
        path = str(OUTPUT_DIR / "24_evidence_dedup_crossref.png")
        page.screenshot(path=path, full_page=False)
        screenshots.append(path)
        print(f"  [24/24] Evidence dedup + cross-ref screenshot")

        # Collect findings
        if js_errors:
            findings.append({"severity": "ERROR", "check": "JS errors", "detail": json.dumps(js_errors[:10])})
        else:
            findings.append({"severity": "PASS", "check": "JS errors", "detail": "0 errors during full event injection"})

        # Check all tabs are switchable
        for tab in ["overview", "queries", "sources", "storm", "evidence", "report", "trace", "fullreport"]:
            page.evaluate(f"switchTab('{tab}')")
            page.wait_for_timeout(100)
            visible = page.is_visible(f"#pane-{tab}")
            findings.append({
                "severity": "PASS" if visible else "FAIL",
                "check": f"Tab '{tab}' switchable",
                "detail": f"Visible: {visible}"
            })

        # Check key content rendered
        checks = [
            ("Overview status text", "#current-status-text", "Synthesizing"),
            ("Phase stepper done", "#step-plan", None),
            ("Vector ID", "#vector-id", "PG_AUDIT_001"),
            ("Evidence count", "#pm-evidence", None),
            ("Faithfulness", "#pm-faith", "86.7%"),
            ("Cost visible", "#pm-cost", "$"),
        ]
        for label, selector, expected_text in checks:
            el = page.query_selector(selector)
            if el:
                text = el.inner_text()
                if expected_text and expected_text not in text:
                    findings.append({"severity": "WARN", "check": label, "detail": f"Expected '{expected_text}' in '{text}'"})
                else:
                    findings.append({"severity": "PASS", "check": label, "detail": text[:80]})
            else:
                findings.append({"severity": "FAIL", "check": label, "detail": f"Selector {selector} not found"})

        # Check enriched data
        page.evaluate("switchTab('evidence')")
        page.wait_for_timeout(200)
        detail_cards = page.query_selector_all(".evidence-detail-card")
        findings.append({
            "severity": "PASS" if len(detail_cards) >= 3 else "FAIL",
            "check": "Evidence detail cards",
            "detail": f"{len(detail_cards)} cards rendered"
        })

        page.evaluate("switchTab('report')")
        page.wait_for_timeout(200)
        theme_chips = page.query_selector_all(".theme-chip")
        findings.append({
            "severity": "PASS" if len(theme_chips) >= 4 else "FAIL",
            "check": "Cluster themes",
            "detail": f"{len(theme_chips)} themes rendered"
        })

        verdict_cards = page.query_selector_all(".verdict-card")
        findings.append({
            "severity": "PASS" if len(verdict_cards) >= 5 else "FAIL",
            "check": "Verification verdicts",
            "detail": f"{len(verdict_cards)} verdicts rendered"
        })

        bib_entries = page.query_selector_all(".bib-entry")
        findings.append({
            "severity": "PASS" if len(bib_entries) >= 5 else "FAIL",
            "check": "Bibliography entries",
            "detail": f"{len(bib_entries)} entries rendered"
        })

        section_rows = page.query_selector_all(".section-row")
        findings.append({
            "severity": "PASS" if len(section_rows) >= 3 else "FAIL",
            "check": "Section writes with titles",
            "detail": f"{len(section_rows)} sections rendered"
        })

        preview = page.query_selector(".section-content-preview.open")
        findings.append({
            "severity": "PASS" if preview else "WARN",
            "check": "Expandable section content",
            "detail": "Section preview is expanded" if preview else "No section expanded (may need click)"
        })

        page.evaluate("switchTab('storm')")
        page.wait_for_timeout(200)
        storm_text = page.inner_text("#pane-storm")
        has_expertise = "remediation" in storm_text.lower() or "specialist" in storm_text.lower()
        findings.append({
            "severity": "PASS" if has_expertise else "FAIL",
            "check": "STORM persona expertise",
            "detail": "Expertise text visible" if has_expertise else "Expertise NOT found"
        })
        has_qa = "hydrophobic" in storm_text.lower()
        findings.append({
            "severity": "PASS" if has_qa else "FAIL",
            "check": "STORM Q&A content",
            "detail": "Answer content visible" if has_qa else "Answer NOT found"
        })

        # Check new visibility features
        # Full Report tab
        page.evaluate("switchTab('fullreport')")
        page.wait_for_timeout(300)
        fullreport_text = page.inner_text("#pane-fullreport")
        has_fullreport = "PFAS" in fullreport_text and "Adsorption" in fullreport_text
        findings.append({
            "severity": "PASS" if has_fullreport else "FAIL",
            "check": "Full Report content",
            "detail": f"Report text rendered ({len(fullreport_text)} chars)" if has_fullreport else "Full Report NOT rendered"
        })

        export_btn = page.query_selector("#btn-export-report")
        findings.append({
            "severity": "PASS" if export_btn else "FAIL",
            "check": "Export report button",
            "detail": "Export button present" if export_btn else "Export button NOT found"
        })

        # Gap Analysis card
        page.evaluate("switchTab('overview')")
        page.wait_for_timeout(200)
        gap_text = page.inner_text("#ov-gap-analysis")
        has_gap = "gap" in gap_text.lower() and "138" in gap_text
        findings.append({
            "severity": "PASS" if has_gap else "FAIL",
            "check": "Gap analysis card",
            "detail": "Gap analysis rendered" if has_gap else "Gap analysis NOT rendered"
        })

        # LLM Usage card
        llm_text = page.inner_text("#ov-llm-usage")
        has_llm = "llm" in llm_text.lower() or "calls" in llm_text.lower()
        findings.append({
            "severity": "PASS" if has_llm else "FAIL",
            "check": "LLM usage card",
            "detail": "LLM usage rendered" if has_llm else "LLM usage NOT rendered"
        })

        # Research Plan card
        page.evaluate("switchTab('queries')")
        page.wait_for_timeout(200)
        plan_text = page.inner_text("#q-research-plan")
        has_plan = "research plan" in plan_text.lower() or "broad_then_deep" in plan_text
        findings.append({
            "severity": "PASS" if has_plan else "FAIL",
            "check": "Research plan card",
            "detail": "Research plan rendered" if has_plan else "Research plan NOT rendered"
        })

        # Agentic rounds
        rounds_text = page.inner_text("#q-agentic-rounds")
        has_rounds = "round" in rounds_text.lower() or "agentic" in rounds_text.lower()
        findings.append({
            "severity": "PASS" if has_rounds else "FAIL",
            "check": "Agentic rounds card",
            "detail": "Agentic rounds rendered" if has_rounds else "Agentic rounds NOT rendered"
        })

        # Fetch Pipeline
        page.evaluate("switchTab('sources')")
        page.wait_for_timeout(200)
        fetch_text = page.inner_text("#src-fetch-pipeline")
        has_fetch = "fetch" in fetch_text.lower() or "pipeline" in fetch_text.lower()
        findings.append({
            "severity": "PASS" if has_fetch else "FAIL",
            "check": "Fetch pipeline card",
            "detail": "Fetch pipeline rendered" if has_fetch else "Fetch pipeline NOT rendered"
        })

        # Signal Distribution
        page.evaluate("switchTab('evidence')")
        page.wait_for_timeout(200)
        sig_text = page.inner_text("#ev-signal-dist")
        has_sig = "signal" in sig_text.lower() or "semantic" in sig_text.lower()
        findings.append({
            "severity": "PASS" if has_sig else "FAIL",
            "check": "Signal distribution card",
            "detail": "Signal distribution rendered" if has_sig else "Signal distribution NOT rendered"
        })

        # NLI Verification
        nli_text = page.inner_text("#ev-nli-verification")
        has_nli = "nli" in nli_text.lower() or "faithful" in nli_text.lower()
        findings.append({
            "severity": "PASS" if has_nli else "FAIL",
            "check": "NLI verification card",
            "detail": "NLI verification rendered" if has_nli else "NLI verification NOT rendered"
        })

        # Dedup Pipeline
        dedup_text = page.inner_text("#ev-dedup-pipeline")
        has_dedup = "dedup" in dedup_text.lower() or "156" in dedup_text
        findings.append({
            "severity": "PASS" if has_dedup else "FAIL",
            "check": "Dedup pipeline card",
            "detail": "Dedup pipeline rendered" if has_dedup else "Dedup pipeline NOT rendered"
        })

        # Cross-Reference
        xref_text = page.inner_text("#ev-cross-ref")
        has_xref = "cross" in xref_text.lower() or "corroboration" in xref_text.lower()
        findings.append({
            "severity": "PASS" if has_xref else "FAIL",
            "check": "Cross-reference card",
            "detail": "Cross-reference rendered" if has_xref else "Cross-reference NOT rendered"
        })

        # Report Outline
        page.evaluate("switchTab('report')")
        page.wait_for_timeout(200)
        outline_text = page.inner_text("#rpt-outline")
        has_outline = "outline" in outline_text.lower() or "Comprehensive" in outline_text
        findings.append({
            "severity": "PASS" if has_outline else "FAIL",
            "check": "Report outline card",
            "detail": "Report outline rendered" if has_outline else "Report outline NOT rendered"
        })

        # Hallucination Audit
        halluc_text = page.inner_text("#rpt-hallucination-audit")
        has_halluc = "hallucination" in halluc_text.lower() or "REWRITE" in halluc_text
        findings.append({
            "severity": "PASS" if has_halluc else "FAIL",
            "check": "Hallucination audit card",
            "detail": "Hallucination audit rendered" if has_halluc else "Hallucination audit NOT rendered"
        })

        # Evidence Conflicts
        conflict_text = page.inner_text("#rpt-evidence-conflicts")
        has_conflict = "conflict" in conflict_text.lower() or "contradiction" in conflict_text.lower()
        findings.append({
            "severity": "PASS" if has_conflict else "FAIL",
            "check": "Evidence conflicts card",
            "detail": "Evidence conflicts rendered" if has_conflict else "Evidence conflicts NOT rendered"
        })

        # Expansion History
        exp_text = page.inner_text("#rpt-expansion-history")
        has_exp = "expansion" in exp_text.lower() or "pass" in exp_text.lower()
        findings.append({
            "severity": "PASS" if has_exp else "FAIL",
            "check": "Expansion history card",
            "detail": "Expansion history rendered" if has_exp else "Expansion history NOT rendered"
        })

        # Section-Evidence Map
        sem_text = page.inner_text("#rpt-section-evidence-map")
        has_sem = "section" in sem_text.lower() and "evidence" in sem_text.lower()
        findings.append({
            "severity": "PASS" if has_sem else "FAIL",
            "check": "Section-evidence map card",
            "detail": "Section-evidence map rendered" if has_sem else "Section-evidence map NOT rendered"
        })

        # Color check
        bg = page.evaluate("getComputedStyle(document.body).backgroundColor")
        is_slate = "15" in bg and "23" in bg and "42" in bg
        findings.append({
            "severity": "PASS" if is_slate else "FAIL",
            "check": "Slate background color",
            "detail": f"Body bg: {bg}"
        })

        html_src = page.content()
        has_green = "#10A37F" in html_src or "#10a37f" in html_src
        findings.append({
            "severity": "FAIL" if has_green else "PASS",
            "check": "No green (#10A37F)",
            "detail": "GREEN FOUND" if has_green else "No green references"
        })

        browser.close()

    proc.kill()
    proc.wait(timeout=5)
    if dummy_trace.exists():
        dummy_trace.unlink()

    # Write report
    report = {
        "screenshots": screenshots,
        "findings": findings,
        "summary": {
            "total": len(findings),
            "pass": sum(1 for f in findings if f["severity"] == "PASS"),
            "warn": sum(1 for f in findings if f["severity"] == "WARN"),
            "fail": sum(1 for f in findings if f["severity"] == "FAIL"),
            "error": sum(1 for f in findings if f["severity"] == "ERROR"),
        }
    }
    report_path = OUTPUT_DIR / "audit_report.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    # Print summary
    print(f"\n{'='*60}")
    print(f"DASHBOARD VISUAL AUDIT REPORT")
    print(f"{'='*60}")
    print(f"Screenshots: {len(screenshots)} saved to {OUTPUT_DIR}/")
    print(f"Checks: {report['summary']['pass']} PASS, {report['summary']['warn']} WARN, {report['summary']['fail']} FAIL, {report['summary']['error']} ERROR")
    print(f"{'='*60}")

    for f in findings:
        icon = {"PASS": "OK", "WARN": "!!", "FAIL": "XX", "ERROR": "!!"}[f["severity"]]
        print(f"  [{icon}] {f['check']}: {f['detail'][:80]}")

    print(f"\nFull report: {report_path}")
    print(f"Screenshots: {OUTPUT_DIR}/")

    if report["summary"]["fail"] > 0 or report["summary"]["error"] > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
