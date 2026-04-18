# Research report: What are the current best practices for retrieval-augmented generation architectures as of 2024-2025?

### Efficacy

Retrieval-Augmented Generation has evolved into a foundational architecture for enterprise AI, forming the core of modern knowledge-intensive applications.[1] The quality of the data ingestion pipeline, including multimodal document parsing and semantic chunking, is the primary determinant of a RAG system's performance.[1] Production-grade retrieval is a sophisticated, multi-stage process that mandates a hybrid search approach, combining sparse and dense vectors to maximize recall.[1] A typical hybrid implementation might weight a keyword-based method like BM25 at 0.3 and dense embeddings at 0.7 for general queries.[2] Key performance metrics include Precision@K, with targets varying from ≥0.85 for regulated content to ≥0.65 for exploratory research.[2] Optimization techniques like embedding caches can significantly reduce latency, cutting p95 response time from 2.1 seconds to 450 milliseconds.[2] For cost efficiency, embedding fresh documents is economical, costing roughly $0.001-$0.01 per document, allowing a typical enterprise knowledge base of 10,000 documents to be indexed for under $100.[2]

### Mechanism

Retrieval-Augmented Generation (RAG) enhances large language models by conditioning generation on external evidence retrieved at inference time.[3] The architecture of RAG operates by first querying a dataset of documents to find relevant content and then conditioning the generation process of the language model on the retrieved documents.[4] Formally, the generation process can be expressed as modeling a conditional distribution of the output given the input and a retrieved document.[3] A comprehensive taxonomy categorizes RAG architectures into retriever-centric, generator-centric, hybrid, and robustness-oriented designs.[3] Retriever-centric systems delegate architectural responsibility primarily to the retriever, treating the generator as a passive decoder.[3] Generator-based systems concentrate architectural innovation on the decoding process, shifting the burden of factual grounding and integration to the language model.[3] Hybrid systems tightly couple the retriever and generator, treating retrieval and generation as co-adaptive reasoning agents with iterative feedback.[3] Robustness-oriented systems are designed to preserve output quality in the face of noisy, irrelevant, or adversarially manipulated retrieval contexts.[3]

### Limitations

Limitations: The corpus is heavily weighted toward tertiary and lower-tier sources, with only 25% of sources being T1 primary studies, while T5 and T6 sources each constitute another 25%. No internal contradictions were detected by the pipeline. The evidence horizon is recent, spanning from January 2018 to the present, which may exclude foundational studies published prior to this period.

## Methods
Pre-registered protocol.json (SHA-256 d06fb9f2fc01882b...).
Corpus: Serper + Semantic Scholar + OpenAlex live retrieval.
Generator model: deepseek/deepseek-v3.2-exp (multi-section: outline + 2 parallel sections + strict_verify + regen-on-failure).
Evaluator model: qwen/qwen3-8b (different family).
Sources classified using T1-T7 tier taxonomy.
Inclusion / exclusion per tech template. Sponsor / conflict-of-interest review per source.
Prompt-injection sanitization enabled. Retrieved 2026-04-18.
Expected tier distribution: T1 20-50%, T4 10-35%, T2 5-25%, T6 5-25%, T3 0-15%, T5 0-10%, T7 0-15%. Actual distribution: T1=25%, T4=12%, T5=25%, T6=25%, T7=12%.


## Bibliography
[1] RAG: An Architectural Review and Strategic Outlook for 2025 — https://www.linkedin.com/pulse/rag-architectural-review-strategic-outlook-2025-bal%C3%A1zs-feh%C3%A9r-bwzpf (tier T6)
[2] RAG in 2025: 7 Proven Strategies to Deploy Retrieval- ... — https://www.morphik.ai/blog/retrieval-augmented-generation-strategies (tier T5)
[3] Retrieval-Augmented Generation: A Comprehensive ... — https://arxiv.org/html/2506.00054v1 (tier T4)
[4] What is Retrieval Augmented Generation(RAG) in 2025? — https://www.glean.com/blog/rag-retrieval-augmented-generation (tier T5)
