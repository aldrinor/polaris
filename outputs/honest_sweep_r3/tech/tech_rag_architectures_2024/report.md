# Research report: What are the current best practices for retrieval-augmented generation architectures as of 2024-2025?

### Efficacy

A proven strategy is implementing a hybrid retrieval approach, combining keyword and semantic search; a typical implementation might weight BM25 at 0.3 and dense embeddings at 0.7 for general queries, dynamically adjusting based on query characteristics.[1] For performance, embedding cached vectors for frequently accessed content can cut p95 response time from 2.1 seconds to 450 milliseconds.[1] Key performance metrics include Precision@K, with targets of ≥0.85 for regulated content and ≥0.65 for exploratory queries, and an Answer Rate target of ≥0.90.[1] The economic case is compelling, as embedding new documents costs roughly $0.001-$0.01 per document, allowing a typical 10,000-document knowledge base to be indexed for under $100, a fraction of the cost of fine-tuning.[1] This approach enables systems to adapt to specific domains and provide source-backed answers without extensive retraining.[2] Effective deployment also utilizes open-source tools, such as those with built-in evaluation and enterprise connectors, to build production-ready systems.[1]

### Comparative

The quality of the data ingestion pipeline, particularly document parsing and semantic chunking, is identified as the primary determinant of overall RAG system performance.[3] For retrieval, production systems now require a sophisticated, multi-stage funnel that mandates a hybrid search approach combining sparse keyword-based and dense semantic vectors to maximize recall.[3] When comparing embedding models, a clear trade-off exists between managed services and open-source options.[3] Managed services like OpenAI's API offer ease of use and reliability but incur costs, such as $0.00002 per 1,000 tokens for text-embedding-3-small, and introduce potential latency and data privacy concerns.[3] In contrast, open-source models such as bge-base-en-v1.5 or jina-embeddings-v2-base-en provide greater control and privacy by enabling local deployment.[3] The industry trajectory is moving away from simple prototypes toward complex, multimodal, and agentic systems that form the core of modern AI applications.[3]

### Mechanism

RAG systems consist of three core modules: a query encoder, a retriever, and a generator.[4] Architecturally, they can be categorized into retriever-centric, generator-centric, hybrid, and robustness-oriented designs.[4] Retriever-centric systems delegate primary responsibility to the retriever, treating the generator as a passive decoder.[4] Generator-centric systems concentrate innovation on the decoding process, shifting the burden of factual grounding and integration to the language model.[4] Hybrid systems tightly couple the retriever and generator, treating them as co-adaptive reasoning agents with iterative feedback.[4] The generation process formally models a conditional distribution where the output depends on the input and retrieved documents.[4] The architecture integrates dense retrieval mechanisms and transformer-based generation models to condition generation on retrieved information.[5] Enhancements include adaptive retrieval, which can reduce redundant retrievals by 14.9% in short-form tasks, and query refinement techniques like perplexity-driven decomposition.[4]

### Limitations

Limitations: The corpus has significant tier-distribution gaps, with only 25% of sources being T1 primary studies and a substantial 38% classified as T4 expert opinion. No direct contradictions between sources were detected by the pipeline. The evidence horizon is narrow, with all included sources published from 2018 to the present, which may exclude foundational research from earlier periods.

## Methods
Pre-registered protocol.json (SHA-256 5c5df4b82279af98...).
Corpus: Serper + Semantic Scholar + OpenAlex live retrieval.
Generator model: deepseek/deepseek-v3.2-exp (multi-section: outline + 3 parallel sections + strict_verify + regen-on-failure).
Evaluator model: qwen/qwen3-8b (different family).
Sources classified using T1-T7 tier taxonomy.
Inclusion / exclusion per tech template. Sponsor / conflict-of-interest review per source.
Prompt-injection sanitization enabled. Retrieved 2026-04-18.
Expected tier distribution: T1 20-50%, T4 10-35%, T2 5-25%, T6 5-25%, T3 0-15%, T5 0-10%, T7 0-15%. Actual distribution: T1=25%, T4=38%, T6=25%, T7=12%.


## Bibliography
[1] RAG in 2025: 7 Proven Strategies to Deploy Retrieval- ... — https://www.morphik.ai/blog/retrieval-augmented-generation-strategies (tier T4)
[2] Retrieval-Augmented Generation in 2025: Solving LLM's ... — https://dev.to/genezio/retrieval-augmented-generation-in-2025-solving-llms-biggest-challenges-4d4i (tier T6)
[3] RAG: An Architectural Review and Strategic Outlook for 2025 — https://www.linkedin.com/pulse/rag-architectural-review-strategic-outlook-2025-bal%C3%A1zs-feh%C3%A9r-bwzpf (tier T4)
[4] Retrieval-Augmented Generation: A Comprehensive ... — https://arxiv.org/html/2506.00054v1 (tier T4)
[5] What is Retrieval Augmented Generation(RAG) in 2025? — https://www.glean.com/blog/rag-retrieval-augmented-generation (tier T1)
