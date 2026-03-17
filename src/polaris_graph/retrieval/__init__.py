"""CRAG Retrieval Pipeline (v2 Layer 1).

Replaces v1's 126-call LLM analyzer with $0 local embeddings.
Pipeline: Fetch -> Chunk -> Enrich -> Dedup -> Score -> Gate -> Register

Modules:
    crag_retriever       Main orchestrator (replaces analyze node)
    source_registry      Global Source Registry (SRC-NNN, Loophole L1)
    section_blueprint    Cross-section evidence assignment (Loophole L5)
    citation_normalizer  Compound citation splitting + SRC->number resolution
    pooled_embedder      Mean-pooling sub-chunking for 256-token model limit (Fix R4-#1)
    fetch_limiter        Semaphore + retry for rate-limited URL fetching (Fix R4-#4)
    verify_context       Citation-priority evidence selection for verifier (Fix R4-#5)
    llm_throttle         LLM concurrency limiter for TPM burst prevention (Fix R5-#3)
    verify_schemas       CoT verification schema to prevent sycophancy (Fix R5-#4)
    synthesis_prompts    Section writer prompt with phantom figure ban (Fix R5-#5)
"""

from src.polaris_graph.retrieval.source_registry import SourceRegistry
from src.polaris_graph.retrieval.crag_retriever import CRAGRetriever
from src.polaris_graph.retrieval.section_blueprint import SectionBlueprint
from src.polaris_graph.retrieval.citation_normalizer import (
    CITATION_RULES,
    normalize_citations,
    resolve_to_numbers,
)
from src.polaris_graph.retrieval.pooled_embedder import embed_with_pooling
from src.polaris_graph.retrieval.fetch_limiter import (
    rate_limited_fetch,
    rate_limited_fetch_batch,
)
from src.polaris_graph.retrieval.verify_context import build_verify_context
from src.polaris_graph.retrieval.llm_throttle import throttled_llm_call
from src.polaris_graph.retrieval.verify_schemas import (
    ClaimVerification,
    VERIFY_SYSTEM_PROMPT,
    VERIFY_USER_TEMPLATE,
)
from src.polaris_graph.retrieval.synthesis_prompts import (
    PHANTOM_FIGURE_BAN,
    EVIDENCE_FIRST_RULES,
    ANALYTICAL_WRITING_RULES,
    build_section_writer_prompt,
)

__all__ = [
    "ANALYTICAL_WRITING_RULES",
    "CRAGRetriever",
    "CITATION_RULES",
    "ClaimVerification",
    "EVIDENCE_FIRST_RULES",
    "PHANTOM_FIGURE_BAN",
    "SectionBlueprint",
    "SourceRegistry",
    "VERIFY_SYSTEM_PROMPT",
    "VERIFY_USER_TEMPLATE",
    "build_section_writer_prompt",
    "build_verify_context",
    "embed_with_pooling",
    "normalize_citations",
    "rate_limited_fetch",
    "rate_limited_fetch_batch",
    "resolve_to_numbers",
    "throttled_llm_call",
]
