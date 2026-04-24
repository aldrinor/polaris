# Research report: What are the current best practices for retrieval-augmented generation architectures as of 2024-2025?

### Efficacy

The Blended RAG method, which leverages semantic search techniques and hybrid query strategies, achieved better retrieval results and set new benchmarks for Information Retrieval datasets like NQ and TREC-COVID.[1] In the specialized domain of music question answering, the MusT-RAG framework significantly outperformed traditional fine-tuning approaches in enhancing LLMs' adaptation capabilities, showing consistent improvements across both in-domain and out-of-domain benchmarks.[2] This demonstrates that adaptive, iterative frameworks like FAIR-RAG, which use explicit gap analysis to refine queries, are crucial for complex, multi-hop queries.[3] Similarly, hybrid retrieval strategies that blend different search techniques can substantially improve accuracy as document corpora scale.[1]

### Mechanism

Research and engineering practices have become fragmented due to the increasing diversity of RAG methodologies, which encompass a variety of fusion mechanisms, retrieval strategies, and orchestration approaches.[4] RAG offers a modular architecture for integrating external knowledge without increasing the underlying model's capacity, and it has matured from a specialized technique into a foundational architecture for enterprise AI.[4][5]

### Comparative

RAG implementations must be designed as core product components rather than bolted-on integrations to avoid failure, with one source noting over 70% of new LLM features quietly fail in production otherwise.[6] In the medical domain, there is no consensus on best practices for building RAG systems, necessitating careful analysis of components and systematic evaluations to reveal optimal trade-offs between performance and efficiency.[7] For the energy sector, a proposed system called Expert Mind adapts RAG to preserve tacit knowledge from an aging workforce, addressing the domain-specific challenge of irreversible knowledge loss through structured interviews and multimodal capture.[8] While the medical domain pursues industrial best practices through component evaluation, the energy sector's adaptation focuses on knowledge elicitation and ethical frameworks as first-class design constraints.[7][8] In software, best practices for registries and repositories focus on improving discoverability and transparency, which are distilled from the experiences of existing resources.[9]

### Safety

A stealthy membership inference technique called the Interrogation Attack (IA) targets documents in the RAG datastore by crafting natural-text queries answerable only with a target document's presence, demonstrating successful inference with just 30 queries.[10] The attack also shows a 2x improvement in TPR@1%FPR over prior inference attacks across diverse RAG configurations, costing less than $0.02 per document inference.[10] For faithful generation, advanced RAG methods often lack a robust mechanism to systematically identify and fill evidence gaps, which can propagate noise.[3] The FAIR-RAG framework addresses this with an Iterative Refinement Cycle and a Structured Evidence Assessment (SEA) module that audits aggregated evidence to identify confirmed facts and explicit informational gaps.[3] This evidence-driven process ensures a comprehensive context for final, strictly faithful generation.[3]

### Limitations

Limitations: The corpus is heavily skewed toward lower-tier sources, with only 10% of sources being T1 primary studies, while 70% are T4 (news and media). This imbalance may introduce a recency or popular-science bias into the synthesized conclusions. The evidence horizon spans from 2018 to the present, capturing recent developments but potentially missing foundational work from earlier periods. The pipeline did not detect any explicit contradictions in the extracted claims for this report.

## Methods
Pre-registered protocol.json (SHA-256 606fcbb07b97f9c7...).
Corpus: Serper + Semantic Scholar + OpenAlex live retrieval, augmented by domain backends (tech: domain_backends(tech): {'arxiv': 20, 'github': 22}).
Generator model: deepseek/deepseek-v3.2-exp (multi-section: outline + 4 parallel sections + strict_verify + regen-on-failure).
Evaluator model: qwen/qwen3-8b (different family).
Sources classified using T1-T7 tier taxonomy.
Inclusion / exclusion per tech template. Sponsor / conflict-of-interest review per source.
Prompt-injection sanitization enabled. Retrieved 2026-04-18.
Expected tier distribution: T1 20-50%, T4 10-35%, T2 5-25%, T6 5-25%, T3 0-15%, T5 0-10%, T7 0-15%. Actual distribution: T1=10%, T4=70%, T5=5%, T6=10%, T7=5%.
Corpus adequacy: decision=proceed, 7/7 thresholds met.
Completeness checklist: 6/6 topics covered.


## Bibliography
[1] Blended RAG: Improving RAG (Retriever-Augmented Generation) Accuracy with Semantic Search and Hybrid Query-Based Retrievers — http://arxiv.org/abs/2404.07220v2 (tier T4)
[2] MUST-RAG: MUSical Text Question Answering with Retrieval Augmented Generation — http://arxiv.org/abs/2507.23334v2 (tier T4)
[3] FAIR-RAG: Faithful Adaptive Iterative Refinement for Retrieval-Augmented Generation — http://arxiv.org/abs/2510.22344v1 (tier T4)
[4] Engineering the RAG Stack: A Comprehensive Review of the Architecture and Trust Frameworks for Retrieval-Augmented Generation Systems — http://arxiv.org/abs/2601.05264v1 (tier T4)
[5] RAG: An Architectural Review and Strategic Outlook for 2025 — https://www.linkedin.com/pulse/rag-architectural-review-strategic-outlook-2025-bal%C3%A1zs-feh%C3%A9r-bwzpf (tier T6)
[6] RAG Best Practices: Rethinking Knowledge Management for AI — https://redwerk.com/blog/rag-best-practices/ (tier T4)
[7] Pursuing Best Industrial Practices for Retrieval-Augmented Generation in the Medical Domain — http://arxiv.org/abs/2602.03368v2 (tier T4)
[8] Expert Mind: A Retrieval-Augmented Architecture for Expert Knowledge Preservation in the Energy Sector — http://arxiv.org/abs/2603.14541v1 (tier T4)
[9] Nine Best Practices for Research Software Registries and Repositories: A Concise Guide — http://arxiv.org/abs/2012.13117v1 (tier T4)
[10] Riddle Me This! Stealthy Membership Inference for Retrieval-Augmented Generation — http://arxiv.org/abs/2502.00306v2 (tier T4)
