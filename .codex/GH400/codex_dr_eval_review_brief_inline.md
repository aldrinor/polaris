Independent review of Claude's DR-eval-state-of-art synthesis. Output YAML only.

# Task

Claude has produced a research synthesis on 2025-2026 DR-evaluation best practices (below). Your job is to **independently audit** this synthesis: missed sources, inaccuracies, weak claims, and counter-recommendations. Treat this as you would a peer review of a survey paper. Use web search liberally — don't rely on Claude's framing alone.

# Claude's synthesis (verbatim)

```
# DR Evaluation: State of the Art — 2025-2026 (Claude's synthesis, pre-Codex-review)

## Top-line

Best practice for evaluating Deep Research outputs in 2025-2026 has converged on **three layers**: (1) atomic-claim decomposition + per-claim verification against retrieved evidence, (2) citation-quality scoring (recall + precision + context-match), (3) expert-rubric multi-dimensional scoring with complexity-tagged tasks. The §-1.1 standard (clinical evidence-appraisal: PRISMA 2020 / AMSTAR-2 / GRADE / Cochrane RoB 2 / ROBINS-I / QUADAS-2 / ICMJE / jurisdictional) sits underneath as the **domain-specific quality floor** for clinical/regulatory claims, but the 2026 DR-frontier adds rubric breadth and atomic verification that §-1.1 alone does not specify.

## Layer 1 — Atomic-claim factuality (2025-2026 SOTA)

| Method | What it does | Key 2025-2026 finding |
|---|---|---|
| **FactScore** (2023, baseline) | GPT-4 decomposes long-form text into atomic claims, verifies each against retrieved knowledge | Sensitive to decomposer choice — sub-claim atomicity varies |
| **VeriScore** (2024) | Verifiable-claims focus: only verify claims that can be objectively checked; ignore opinions | Avoids penalizing legitimate opinion text |
| **VeriFastScore** (EMNLP 2025) | Fine-tuned Llama 3.1 8B does claims+verify in ONE pass | r=0.80 example-level / r=0.94 system-level correlation with VeriScore; **6.6× speedup** |
| **MiniCheck-FT5** (2024) | Trained fact-checker on grounding documents | **400× cheaper than GPT-4**, comparable accuracy |
| **RefChecker** (2024) | Knowledge-triplet decomposition (subject-predicate-object), 3-context settings | Outperforms prior across all contexts |
| **C2-Cite** (2026) | Contextual citation alignment with router function | **+5.8% citation quality / +17.4% correctness** over ALCE |

**Key 2025 finding (Decomposition Dilemmas, NAACL 2025):** Claim decomposition is NOT universally beneficial. With AlignScore verifier → positive impact. With MiniCheck verifier → LOWER performance than no-decomposition. **Verifier choice matters as much as decomposition method.**

## Layer 2 — Citation quality (ALCE-lineage)

ALCE (Princeton, EMNLP 2023) established the baseline:
- **Citation Recall**: does the cited span support the claim (NLI-based)
- **Citation Precision**: are non-supportive citations removed
- **Citation-F1**: harmonic mean
- Plus fluency + correctness on the answer itself

Extensions in 2025:
- **CiteLab** (ACL 2025 demo): citation development+diagnosis framework
- **PFCG** (NAACL 2025): positional fine-grained — does the citation point to the RIGHT span, not just the right URL
- **C2-Cite** (2026): contextual-aware citation generation, transforms markers into "active knowledge pointers"

## Layer 3 — Expert-rubric DR benchmarks (the new SOTA layer)

| Benchmark | Source | Dimensions | Scale |
|---|---|---|---|
| **DeepResearch Bench (DRB)** | Tencent + Tsinghua | RACE (4-dim adaptive criteria) + FACT (citation accuracy + groundedness) | 96K user queries → 100 hard prompts; v2 Feb 2026 |
| **BrowseComp** | OpenAI | Hard-to-find entangled info; persistence + creativity | 1,266 problems |
| **DRACO** | Perplexity | Factual accuracy + breadth/depth + presentation + citation | 100 tasks, 10 domains, 40 countries |
| **ResearchRubrics** | Scale AI (ICLR 2026) | 2,500+ expert criteria per-prompt; complexity tagged (breadth × nesting × exploration) | 101 prompts × 20-43 criteria each |
| **ResearcherBench** | SII-GAIR | Frontier research questions, systematic | research-focused |
| **DeepSearchQA** | DeepMind 2026 | Comprehensiveness gap measurement | new comprehensiveness metric |

**Common rubric structure across all 4:** factual accuracy / completeness / citation quality / clarity (presentation) / reasoning coherence. ResearchRubrics adds **complexity stratification** (3-axis) and **2,800 hours of expert labor** producing **fine-grained 2,500+ criteria** — gold-standard for clinical/policy DR.

## Layer 4 — Clinical/regulatory-specific (PRISMA-AI, 2024-2025)

- **PRISMA-trAIce** (JMIR AI 2025): NEW checklist extension to PRISMA 2020 for "Transparent Reporting of Artificial Intelligence in Comprehensive Evidence-synthesis" — requires disclosure when AI is a methodological tool in SR/MA.
- **PRISMA-AI** (in development at EQUATOR Network): broader AI-in-research reporting guideline.
- **LLM-as-quality-appraiser** finding (medRxiv 2024-04): individual LLM accuracy 63-70% on PRISMA appraisal; 53-74% on AMSTAR. **Human-AI collaboration → 89-96% on PRISMA, 91-95% on AMSTAR** (with 25-35% deferral rates). Implication: LLM-only quality appraisal is insufficient; need human-in-loop.

This means for POLARIS's audit: when applying PRISMA / AMSTAR / GRADE / RoB scores to claims, the audit MUST involve a deferral path (claims where evaluator is uncertain → escalate to human or stricter reviewer), not auto-decide.

## Layer 5 — Open-source eval harnesses (2025-2026 production)

| Repo | Specialty | Notable |
|---|---|---|
| **RAGAS** | Reference-free RAG eval | Faithfulness + answer-relevancy + context-relevance + context-recall metrics |
| **DeepEval** (Confident AI) | Pytest-style LLM unit tests | 14+ metrics; faithfulness metric is reference-free |
| **Opik** (Comet) | Tracing + eval + dataset | Self-hostable, full lifecycle |
| **Langfuse** | Production observability | LLM-as-judge + dataset synthesis |
| **HHEM 2.1 + FaithJudge** (Vectara) | Hallucination evaluation | Public leaderboard since 2023 |
| **REFCHECKER** | Fine-grained hallucination | Knowledge-triplet-based |
| **VeriFastScore** | Long-form factuality | 6.6× speedup |

## Gap analysis: §-1.1 vs 2026 DR-frontier

What §-1.1 already covers (clinical evidence-appraisal):
✓ PRISMA 2020 (SR reporting)
✓ AMSTAR-2 (SR quality)
✓ GRADE per claim (certainty)
✓ Cochrane RoB 2 / ROBINS-I / QUADAS-2 (bias scoring)
✓ ICMJE (authorship/COI)
✓ Jurisdictional regulatory (FDA/EMA/HC)
✓ 5-verdict claim rubric (VERIFIED/PARTIAL/UNSUPPORTED/FABRICATED/UNREACHABLE)

What §-1.1 does NOT explicitly include but 2026 DR-frontier requires:
✗ **Atomic-claim decomposition** before verdict (each claim → set of atoms, each atom verified)
✗ **Citation Recall + Precision + F1** as numeric scores
✗ **Citation-context-match at span level** (cited URL vs cited span text vs claim text)
✗ **Reasoning-step support** (does inference X→Y follow from cited evidence?)
✗ **Multi-source agreement** (claim supported by ≥2 independent sources)
✗ **Recency/staleness flag** per citation (source year vs claim's currency)
✗ **Complexity stratification of the question itself** (DRB 3-axis: breadth/nesting/exploration)
✗ **Deferral path** for uncertain claims (human-AI collaboration finding)
✗ **Sponsor/COI flag** as a structured field per cited source
✗ **PRISMA-trAIce disclosure** when AI is used in evidence-synthesis (POLARIS uses LLM for synthesis → must self-disclose)

## Recommended POLARIS audit-schema upgrade

For each claim emitted in a POLARIS report, the upgraded cross-review record should contain:

```yaml
claim_id: ...
claim_text: "verbatim from report"
section: Efficacy | Safety | Comparative | ...
atomic_units: [list of atomic sub-claims]
per_atom:
  - atom: "..."
    verdict: VERIFIED | PARTIAL | UNSUPPORTED | FABRICATED | UNREACHABLE
    grade_certainty: high | moderate | low | very_low
    cited_source: [url, span_text, span_offset]
    citation_recall: 0.0-1.0
    citation_precision: 0.0-1.0
    context_match: yes | partial | no
    rob_score: low | some_concerns | high  # if RCT
    robins_i_score: low | moderate | serious | critical  # if observational
    quadas_2_score: low | unclear | high  # if diagnostic
    prisma_2020_conform: yes | partial | no  # if SR/MA cited
    amstar_2_score: high | moderate | low | critically_low  # if SR/MA cited
    icmje_coi_flag: disclosed | undisclosed | sponsor_stated
    recency_flag: current | stale_lt_2y | stale_gt_2y
    multi_source_corroboration: 1 | 2 | 3+  # count of independent sources supporting
    jurisdiction_alignment: fda | ema | health_canada | nice | mhra | tga | pmda | nmpa | none_applicable
reasoning_chain_step_by_step:
  - step: "..."
    follows_from_evidence: yes | partial | no | overreach
codex_verdict_independent: { same fields, populated by Codex }
reconciled_verdict: VERIFIED | PARTIAL | UNSUPPORTED | FABRICATED | UNREACHABLE  # stricter rule
deferred_to_human: yes | no
```

Aggregate metrics per report:
- VERIFIED / PARTIAL / UNSUPPORTED / FABRICATED / UNREACHABLE distribution (5-verdict)
- GRADE distribution (high / moderate / low / very_low)
- Citation-F1 (system-level)
- Multi-source corroboration rate
- Deferral rate (% claims escalated to human)
- COI-undisclosed rate
- Stale-citation rate

## Sources cited

- DeepResearch Bench: https://deepresearch-bench.github.io/ + arXiv https://github.com/Ayanami0730/deep_research_bench
- BrowseComp: https://openai.com/index/browsecomp/
- DRACO: https://research.perplexity.ai/articles/evaluating-deep-research-performance-in-the-wild-with-the-draco-benchmark
- ResearchRubrics: https://arxiv.org/abs/2511.07685 + https://github.com/scaleapi/researchrubrics
- ResearcherBench: https://arxiv.org/pdf/2507.16280
- VeriFastScore: https://arxiv.org/abs/2505.16973
- MiniCheck: https://arxiv.org/abs/2404.10774
- RefChecker: https://arxiv.org/html/2405.14486v1
- Decomposition Dilemmas (NAACL 2025): https://arxiv.org/html/2411.02400
- ALCE (Princeton): https://github.com/princeton-nlp/ALCE
- CiteLab (ACL 2025): https://aclanthology.org/2025.acl-demo.47.pdf
- C2-Cite: https://arxiv.org/html/2602.00004
- PRISMA-trAIce: https://ai.jmir.org/2025/1/e80247
- LLM PRISMA/AMSTAR appraisal benchmark: https://www.medrxiv.org/content/medrxiv/early/2024/04/22/2024.04.21.24306137.full.pdf
- Vectara HHEM leaderboard + FaithJudge: https://arxiv.org/html/2505.04847v2
- RAGAS/DeepEval/Opik/Langfuse comparison: https://atlan.com/know/llm-evaluation-frameworks-compared/

## Status

Claude synthesis complete. **Pending Codex independent review** of this dossier for completeness, accuracy, missed sources, and counter-recommendations. Cross-reconciled output → feeds into POLARIS audit-schema v2 spec.

```

[SYNTHESIS DOCUMENT IS AT C:\POLARIS\.codex\GH400\dr_eval_state_of_art_2026.md — read it before reviewing.]

# Critical review questions

1. **Coverage gaps:** What 2025-2026 papers / tools / rubrics did Claude MISS that should be in a complete survey?
2. **Mis-characterizations:** Where does Claude OVER- or UNDER-claim about a method's properties? (e.g., "VeriFastScore 6.6× speedup" — is the figure right; is the correlation strong enough for clinical use?)
3. **Schema critique:** Is the recommended POLARIS audit-schema v2 too heavy, too light, or wrong-axis? What would you add/remove?
4. **Clinical-safety lens:** §-1.1 standard's clinical-evidence frameworks are domain-specific. Does the 2026 DR-frontier ACTUALLY translate to clinical/regulatory context, or are DR benchmarks more general/lay?
5. **Operational feasibility:** For POLARIS's ~85 deep claims per report × 5 reports × 2 reviewers, is the proposed schema realistic in the 4-month Carney delivery window?
6. **Counter-recommendations:** What approach would you propose instead — same, partial, or substantially different?

# Output format

```yaml
verdict: ENDORSE | ENDORSE_WITH_AMENDMENTS | DISPUTE
overall_assessment: "2-3 sentences"
coverage_gaps:
  - paper_or_tool: ...
    why_missing_matters: ...
    citation: ...
mischaracterizations:
  - claude_claim: "..."
    codex_correction: "..."
    citation: ...
schema_critique:
  too_heavy: [...]
  too_light: [...]
  wrong_axis: [...]
  add_instead: [...]
clinical_translation:
  - dr_frontier_concept: ...
    translates_to_clinical: yes | partial | no
    reason: ...
operational_feasibility:
  realistic: yes | partial | no
  budget_constraint: ...
  recommended_compromise: ...
counter_recommendations:
  - rec: ...
    rationale: ...
final_recommendation_for_polaris_audit_schema_v2:
  must_have:
    - ...
  defer_to_v3:
    - ...
  reject:
    - ...
```

Output YAML only. No commentary outside.
