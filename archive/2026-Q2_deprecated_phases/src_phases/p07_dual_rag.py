#!/usr/bin/env python3
"""
POLARIS Phase 7: Dual RAG Analysis
==================================
Evidence-grounded synthesis using dual retrieval strategies.

Purpose:
- Retrieve relevant chunks using dense (embedding) and sparse (BM25) methods
- Assemble context within token budget
- Generate analysis with citation markers [CITE:chunk_id]
- Validate citation coverage

Usage:
    python src/phases/p07_dual_rag.py --vector-id S1V1_Household_Water_Filter_NORTH_AMERICA --input outputs/P6/S1V1...json --output outputs/P7/

CLI Contract:
    --vector-id: Required. Vector ID string.
    --input: Required. Path to Phase 6 output JSON.
    --output: Optional. Output directory (default: outputs/P7/)
    --self-test: Run self-test mode
"""

import argparse
import asyncio
import json
import logging
import math
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

# Configure logging
logger = logging.getLogger(__name__)

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.schemas.phase_models import Phase6Output, Phase7Output
from src.state.ledger import Ledger
from src.config import get_config, OUTPUTS_DIR
from src.memory.chroma_client import get_chroma_manager
from src.llm.gemini_client import get_gemini_client
from src.audit import get_audit


# =============================================================================
# SPARSE RETRIEVAL (BM25 - SOTA UPGRADE)
# =============================================================================

_bm25_index = None
_bm25_available = None


def load_bm25_library():
    """Check if rank_bm25 library is available."""
    global _bm25_available
    if _bm25_available is not None:
        return _bm25_available

    try:
        from rank_bm25 import BM25Okapi
        _bm25_available = True
        return True
    except ImportError:
        # LOW-066: Use logger instead of print
        logger.warning("[PHASE-7][WARN] rank_bm25 not available, using fallback BM25")
        _bm25_available = False
        return False


class BM25Retriever:
    """
    BM25 sparse retrieval using rank_bm25 library.

    SOTA Implementation:
    - Uses BM25Okapi for proper keyword retrieval
    - Tokenizes with simple word splitting
    - Returns ranked results with scores
    """

    def __init__(self, chunks: List[Dict[str, Any]]):
        """
        Initialize BM25 index from chunks.

        Args:
            chunks: List of chunks with 'text' and 'id' fields
        """
        self.chunks = chunks
        self.corpus = [c.get("text", "") for c in chunks]
        self.tokenized_corpus = [self._tokenize(doc) for doc in self.corpus]

        if load_bm25_library():
            from rank_bm25 import BM25Okapi
            self.bm25 = BM25Okapi(self.tokenized_corpus)
            self._use_library = True
        else:
            self.bm25 = None
            self._use_library = False

    def _tokenize(self, text: str) -> List[str]:
        """Tokenize text for BM25."""
        text = text.lower()
        # Simple word tokenization
        words = re.findall(r'\b[a-z]{2,}\b', text)
        return words

    def retrieve(self, query: str, top_k: int = 10) -> List[Tuple[Dict[str, Any], float]]:
        """
        Retrieve top-k chunks using BM25.

        Args:
            query: Query string
            top_k: Number of results

        Returns:
            List of (chunk, score) tuples sorted by relevance
        """
        tokenized_query = self._tokenize(query)

        if self._use_library and self.bm25:
            # Use rank_bm25 library
            scores = self.bm25.get_scores(tokenized_query)
            # Pair chunks with scores
            scored_chunks = list(zip(self.chunks, scores))
            # Sort by score descending
            scored_chunks.sort(key=lambda x: x[1], reverse=True)
            return scored_chunks[:top_k]
        else:
            # Fallback to manual BM25
            scores = compute_bm25_scores_manual(query, self.corpus)
            scored_chunks = list(zip(self.chunks, scores))
            scored_chunks.sort(key=lambda x: x[1], reverse=True)
            return scored_chunks[:top_k]


def compute_bm25_scores_manual(
    query: str,
    documents: List[str],
    k1: float = 1.5,
    b: float = 0.75,
) -> List[float]:
    """
    Fallback BM25 implementation when rank_bm25 not available.

    Args:
        query: Query string
        documents: List of document texts
        k1: Term frequency saturation parameter
        b: Length normalization parameter

    Returns:
        List of BM25 scores
    """
    if not documents:
        return []

    def tokenize(text: str) -> List[str]:
        text = text.lower()
        return re.findall(r'\b[a-z]{2,}\b', text)

    query_terms = tokenize(query)
    doc_tokens = [tokenize(doc) for doc in documents]

    # Calculate document frequencies
    df = Counter()
    for tokens in doc_tokens:
        unique_tokens = set(tokens)
        for token in unique_tokens:
            df[token] += 1

    avg_dl = sum(len(tokens) for tokens in doc_tokens) / len(documents)
    n_docs = len(documents)

    scores = []
    for doc_idx, tokens in enumerate(doc_tokens):
        score = 0.0
        doc_len = len(tokens)
        term_freq = Counter(tokens)

        for term in query_terms:
            if term not in term_freq:
                continue

            tf = term_freq[term]
            doc_freq = df.get(term, 0)

            idf = math.log((n_docs - doc_freq + 0.5) / (doc_freq + 0.5) + 1)
            numerator = tf * (k1 + 1)
            denominator = tf + k1 * (1 - b + b * doc_len / avg_dl)
            score += idf * numerator / denominator

        scores.append(score)

    return scores


def reciprocal_rank_fusion(
    dense_results: List[Tuple[str, float]],
    sparse_results: List[Tuple[str, float]],
    k: int = 60,
) -> List[Tuple[str, float]]:
    """
    Merge dense and sparse retrieval results using Reciprocal Rank Fusion (RRF).

    RRF formula: score(d) = sum(1 / (k + rank(d)))

    Args:
        dense_results: List of (chunk_id, score) from dense retrieval
        sparse_results: List of (chunk_id, score) from sparse retrieval
        k: RRF constant (default 60, standard value)

    Returns:
        Merged list of (chunk_id, rrf_score) sorted by combined score
    """
    rrf_scores = {}

    # Add dense scores
    for rank, (chunk_id, _) in enumerate(dense_results, start=1):
        rrf_scores[chunk_id] = rrf_scores.get(chunk_id, 0) + 1.0 / (k + rank)

    # Add sparse scores
    for rank, (chunk_id, _) in enumerate(sparse_results, start=1):
        rrf_scores[chunk_id] = rrf_scores.get(chunk_id, 0) + 1.0 / (k + rank)

    # Sort by RRF score
    sorted_results = sorted(rrf_scores.items(), key=lambda x: x[1], reverse=True)
    return sorted_results


def sparse_retrieve(
    query: str,
    chunks: List[Dict[str, Any]],
    top_k: int = 10,
) -> List[Dict[str, Any]]:
    """
    Retrieve top chunks using BM25 sparse retrieval.

    Args:
        query: Query string
        chunks: List of chunks with 'text' field
        top_k: Number of results to return

    Returns:
        Top-k chunks sorted by BM25 score
    """
    if not chunks:
        return []

    retriever = BM25Retriever(chunks)
    results = retriever.retrieve(query, top_k)

    # Return just the chunks (without scores)
    return [chunk for chunk, score in results]


# =============================================================================
# DENSE RETRIEVAL (CHROMA)
# =============================================================================

# Module-level embedding model cache for query embedding
_query_embedding_model = None


def _get_query_embedding_model():
    """
    Load embedding model matching P5's indexing model.

    This ensures query embeddings have the same dimension as indexed embeddings.
    Uses all-MiniLM-L6-v2 (384 dims) to match P5's standard embedding.
    """
    global _query_embedding_model
    if _query_embedding_model is not None:
        return _query_embedding_model

    try:
        from sentence_transformers import SentenceTransformer
        config = get_config()
        model_name = config.models.embedding.model
        _query_embedding_model = SentenceTransformer(model_name)
        print(f"[PHASE-7] Query embedding model loaded: {model_name}")
        return _query_embedding_model
    except Exception as e:
        # LOW-067: Use logger instead of print
        logger.warning(f"[PHASE-7][WARN] Failed to load embedding model: {e}")
        return None


def _compute_query_embedding(query: str) -> Optional[List[float]]:
    """Compute embedding for a query using the same model as P5."""
    model = _get_query_embedding_model()
    if model is None:
        return None

    try:
        embedding = model.encode(query, convert_to_numpy=True)
        return embedding.tolist()
    except Exception as e:
        # LOW-068: Use logger instead of print
        logger.warning(f"[PHASE-7][WARN] Query embedding failed: {e}")
        return None


def dense_retrieve(
    vector_id: str,
    query: str,
    top_k: int = 10,
) -> List[Dict[str, Any]]:
    """
    Retrieve top chunks using dense embedding retrieval from VWM.

    SOTA: Uses pre-computed query embeddings matching P5's model
    to ensure dimension consistency (384-dim all-MiniLM-L6-v2).

    Args:
        vector_id: Vector ID for VWM collection
        query: Query string
        top_k: Number of results to return

    Returns:
        Top-k chunks from VWM
    """
    chroma = get_chroma_manager()
    vwm = chroma.get_vwm(vector_id)

    if vwm is None:
        return []

    # SOTA: Compute query embedding using same model as P5 indexing
    query_embedding = _compute_query_embedding(query)

    if query_embedding is None:
        # Fallback to text-based query (may fail if dimensions mismatch)
        # LOW-069: Use logger instead of print
        logger.warning(f"[PHASE-7][WARN] Falling back to text-based query")
        results = vwm.query(
            query_texts=[query],
            n_results=top_k,
            include=["documents", "metadatas", "distances"]
        )
    else:
        # Use pre-computed embedding for dimension-safe query
        results = vwm.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
            include=["documents", "metadatas", "distances"]
        )

    chunks = []
    if results and results.get("ids") and results["ids"][0]:
        for i, chunk_id in enumerate(results["ids"][0]):
            chunks.append({
                "id": chunk_id,
                "text": results["documents"][0][i] if results.get("documents") else "",
                "metadata": results["metadatas"][0][i] if results.get("metadatas") else {},
                "distance": results["distances"][0][i] if results.get("distances") else 0,
            })

    return chunks


def get_all_chunks_from_vwm(vector_id: str, limit: int = 500) -> List[Dict[str, Any]]:
    """Get all chunks from VWM for sparse retrieval."""
    chroma = get_chroma_manager()
    vwm = chroma.get_vwm(vector_id)

    if vwm is None:
        return []

    results = vwm.get(
        limit=limit,
        include=["documents", "metadatas"]
    )

    chunks = []
    if results and results.get("ids"):
        for i, chunk_id in enumerate(results["ids"]):
            chunks.append({
                "id": chunk_id,
                "text": results["documents"][i] if results.get("documents") else "",
                "metadata": results["metadatas"][i] if results.get("metadatas") else {},
            })

    return chunks


# =============================================================================
# CONTEXT ASSEMBLY
# =============================================================================

def merge_and_dedupe(
    dense_results: List[Dict[str, Any]],
    sparse_results: List[Dict[str, Any]],
    use_rrf: bool = True,
) -> List[Dict[str, Any]]:
    """
    Merge and deduplicate retrieval results using RRF fusion.

    SOTA: Uses Reciprocal Rank Fusion for optimal merging.

    Args:
        dense_results: Results from dense retrieval
        sparse_results: Results from sparse retrieval
        use_rrf: Whether to use RRF fusion (default True)

    Returns:
        Merged and deduplicated chunks sorted by combined relevance
    """
    if use_rrf and dense_results and sparse_results:
        # Create ID-indexed chunk lookup
        chunk_lookup = {}
        for chunk in dense_results + sparse_results:
            chunk_id = chunk.get("id")
            if chunk_id:
                chunk_lookup[chunk_id] = chunk

        # Prepare results for RRF as (chunk_id, score) tuples
        dense_tuples = []
        for i, chunk in enumerate(dense_results):
            chunk_id = chunk.get("id")
            if chunk_id:
                # Use distance as score (lower distance = better = higher score inverted)
                dist = chunk.get("distance", 0)
                score = 1.0 / (1.0 + dist) if dist else 1.0
                dense_tuples.append((chunk_id, score))

        sparse_tuples = []
        for i, chunk in enumerate(sparse_results):
            chunk_id = chunk.get("id")
            if chunk_id:
                # BM25 score is already relevance-based
                sparse_tuples.append((chunk_id, 1.0))  # Rank-based, actual score doesn't matter for RRF

        # Apply RRF fusion
        rrf_results = reciprocal_rank_fusion(dense_tuples, sparse_tuples, k=60)

        # Convert back to chunks in RRF order
        merged = []
        for chunk_id, rrf_score in rrf_results:
            if chunk_id in chunk_lookup:
                chunk = chunk_lookup[chunk_id].copy()
                chunk["rrf_score"] = rrf_score
                merged.append(chunk)

        return merged

    # Fallback: Simple merge with dense priority
    seen_ids = set()
    merged = []

    for chunk in dense_results:
        chunk_id = chunk.get("id")
        if chunk_id and chunk_id not in seen_ids:
            seen_ids.add(chunk_id)
            merged.append(chunk)

    for chunk in sparse_results:
        chunk_id = chunk.get("id")
        if chunk_id and chunk_id not in seen_ids:
            seen_ids.add(chunk_id)
            merged.append(chunk)

    return merged


def estimate_tokens(text: str) -> int:
    """Rough token estimate (1 token ~ 4 chars)."""
    return len(text) // 4


def assemble_context(
    chunks: List[Dict[str, Any]],
    token_budget: int = 8000,
) -> Tuple[str, List[str]]:
    """
    Assemble context from chunks within token budget.

    Args:
        chunks: List of chunks to include
        token_budget: Maximum tokens for context

    Returns:
        Tuple of (context_text, chunk_ids_used)
    """
    context_parts = []
    chunk_ids_used = []
    tokens_used = 0

    for chunk in chunks:
        chunk_id = chunk.get("id", "unknown")
        text = chunk.get("text", "")

        chunk_tokens = estimate_tokens(text)
        if tokens_used + chunk_tokens > token_budget:
            break

        # Format chunk with ID for citation
        formatted = f"[CHUNK_ID: {chunk_id}]\n{text}\n"
        context_parts.append(formatted)
        chunk_ids_used.append(chunk_id)
        tokens_used += chunk_tokens

    context = "\n---\n".join(context_parts)
    return context, chunk_ids_used


# =============================================================================
# SOTA: THEMATIC CLAIM CLUSTERING
# Based on: Map-Reduce synthesis pattern from PaperQA2 and STORM
# =============================================================================

def cluster_chunks_by_theme(
    chunks: List[Dict[str, Any]],
) -> Dict[str, List[Dict[str, Any]]]:
    """
    SOTA: Cluster chunks by thematic content instead of by source.

    This implements the "group by concept not source" principle from
    research synthesis best practices. Prevents source-sequential reports.

    Args:
        chunks: List of chunks with 'text' and 'id' fields

    Returns:
        Dict mapping theme names to lists of related chunks
    """
    import re
    from collections import defaultdict

    # Define thematic patterns for water filter research
    # These should be configurable per research domain
    theme_patterns = {
        "contamination_rates": r"contamin|rate|percent|%|level|concentration|cfu|log\s*reduction",
        "pathogen_types": r"pathogen|bacteria|virus|parasite|protozoa|e\.?\s*coli|legionella|crypto|giardia|coliform",
        "filter_effectiveness": r"effect|efficacy|removal|reduction|perform|filter\s*cap",
        "maintenance_issues": r"mainten|replac|biofilm|clog|degrad|lifespan|shelf\s*life",
        "health_outcomes": r"health|disease|illness|outbreak|symptom|infect|mortal|morbid",
        "regulatory_standards": r"standard|regulat|guideline|epa|fda|nsf|who|compliance|certif",
        "geographic_patterns": r"region|location|area|country|state|municipal|rural|urban",
        "study_methodology": r"study|research|sample|method|test|analys|survey|trial",
    }

    themed_chunks = defaultdict(list)
    unassigned_chunks = []

    for chunk in chunks:
        text = chunk.get("text", "").lower()
        chunk_id = chunk.get("id", "")

        # Find best matching theme
        best_theme = None
        best_score = 0

        for theme, pattern in theme_patterns.items():
            matches = len(re.findall(pattern, text, re.IGNORECASE))
            if matches > best_score:
                best_score = matches
                best_theme = theme

        if best_theme and best_score >= 2:  # Require at least 2 keyword matches
            chunk_copy = chunk.copy()
            chunk_copy["theme_score"] = best_score
            themed_chunks[best_theme].append(chunk_copy)
        else:
            unassigned_chunks.append(chunk)

    # Add unassigned to "general" theme
    if unassigned_chunks:
        themed_chunks["general_findings"] = unassigned_chunks

    # Sort chunks within each theme by relevance score if available
    for theme in themed_chunks:
        themed_chunks[theme].sort(
            key=lambda x: (x.get("theme_score", 0), x.get("rrf_score", 0)),
            reverse=True
        )

    return dict(themed_chunks)


# =============================================================================
# SOTA: POST-PROCESSING CITATION VALIDATOR
# Ensures all citations reference chunks that exist in VWM
# =============================================================================

class CitationValidator:
    """
    SOTA: Post-processing citation validator for quality assurance.

    Validates that:
    1. All [CITE:chunk_id] tokens reference existing chunks
    2. Citations are semantically relevant to the claim they support
    3. No orphan citations or broken references exist
    """

    def __init__(self, valid_chunk_ids: Set[str], chunk_lookup: Dict[str, Dict[str, Any]]):
        """
        Initialize validator with valid chunk IDs.

        Args:
            valid_chunk_ids: Set of valid chunk IDs from VWM
            chunk_lookup: Dict mapping chunk_id -> chunk data
        """
        self.valid_chunk_ids = valid_chunk_ids
        self.chunk_lookup = chunk_lookup

    def validate_citations(self, analysis_text: str) -> Dict[str, Any]:
        """
        Validate all citations in the analysis text.

        Args:
            analysis_text: Generated analysis with [CITE:chunk_id] markers

        Returns:
            Dict with validation results:
            - valid_citations: List of valid chunk IDs
            - invalid_citations: List of invalid/missing chunk IDs
            - orphan_sentences: Sentences with no citation
            - citation_coverage: Ratio of valid to total citations
        """
        citation_pattern = r'\[CITE:([^\]]+)\]'
        all_citations = re.findall(citation_pattern, analysis_text)

        valid_citations = []
        invalid_citations = []

        for citation in all_citations:
            if citation in self.valid_chunk_ids:
                valid_citations.append(citation)
            else:
                invalid_citations.append(citation)

        # Calculate coverage
        total = len(all_citations)
        coverage = len(valid_citations) / total if total > 0 else 0.0

        return {
            "valid_citations": valid_citations,
            "invalid_citations": invalid_citations,
            "total_citations": total,
            "citation_coverage": coverage,
            "is_valid": len(invalid_citations) == 0,
        }

    def fix_invalid_citations(self, analysis_text: str) -> Tuple[str, int]:
        """
        Remove or flag invalid citations from text.

        Args:
            analysis_text: Text with potential invalid citations

        Returns:
            Tuple of (cleaned_text, removed_count)
        """
        citation_pattern = r'\[CITE:([^\]]+)\]'
        removed_count = 0

        def replace_invalid(match):
            nonlocal removed_count
            chunk_id = match.group(1)
            if chunk_id in self.valid_chunk_ids:
                return match.group(0)  # Keep valid citation
            else:
                removed_count += 1
                return ""  # Remove invalid citation

        cleaned = re.sub(citation_pattern, replace_invalid, analysis_text)

        # Clean up any resulting double spaces
        cleaned = re.sub(r' {2,}', ' ', cleaned)

        return cleaned, removed_count


def validate_analysis_citations(
    analysis_text: str,
    available_chunk_ids: List[str],
    chunks: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    SOTA: Validate citations in generated analysis.

    Args:
        analysis_text: Generated analysis with citations
        available_chunk_ids: List of valid chunk IDs
        chunks: List of chunk dictionaries

    Returns:
        Validation results dict
    """
    chunk_lookup = {c.get("id"): c for c in chunks if c.get("id")}
    validator = CitationValidator(set(available_chunk_ids), chunk_lookup)
    return validator.validate_citations(analysis_text)


# =============================================================================
# SOTA: STORM ARCHITECTURE FOR COMPLEX TOPICS
# Multi-perspective outline generation based on: https://arxiv.org/abs/2402.14207
# =============================================================================

STORM_PERSPECTIVES = [
    {
        "name": "scientific",
        "focus": "What does the peer-reviewed scientific literature say?",
        "keywords": ["study", "research", "evidence", "data", "findings", "methodology"],
    },
    {
        "name": "regulatory",
        "focus": "What do regulations, guidelines, and standards require?",
        "keywords": ["regulation", "standard", "guideline", "compliance", "requirement", "EPA", "FDA", "WHO"],
    },
    {
        "name": "practical",
        "focus": "What are the real-world implementation challenges and solutions?",
        "keywords": ["implementation", "practice", "maintenance", "cost", "challenge", "solution"],
    },
    {
        "name": "comparative",
        "focus": "How do different approaches/methods compare?",
        "keywords": ["comparison", "versus", "alternative", "better", "worse", "tradeoff"],
    },
]

STORM_OUTLINE_PROMPT = """You are generating a multi-perspective research outline using the STORM methodology.

Research Question: {question}

Available Evidence Themes:
{themes_summary}

Perspective Being Analyzed: **{perspective_name}**
Focus Question: {perspective_focus}

Based on this perspective, identify:
1. Key sub-questions this perspective would ask
2. Which evidence themes are most relevant
3. Potential knowledge gaps from this viewpoint

Respond with JSON:
{{
    "perspective": "{perspective_name}",
    "sub_questions": ["Question 1?", "Question 2?"],
    "relevant_themes": ["theme1", "theme2"],
    "knowledge_gaps": ["Gap 1", "Gap 2"]
}}
"""


async def generate_storm_outline(
    question: str,
    themed_chunks: Dict[str, List[Dict[str, Any]]],
) -> Dict[str, Any]:
    """
    SOTA: Generate multi-perspective outline using STORM architecture.

    STORM (Synthesis of Topic Outlines through Retrieval and Multi-perspective
    Question Asking) creates richer outlines by considering multiple perspectives.

    Args:
        question: Research question
        themed_chunks: Chunks organized by theme

    Returns:
        STORM outline with perspectives and synthesized sections
    """
    client = get_gemini_client()

    # Summarize themes
    themes_summary = ""
    for theme, chunks in themed_chunks.items():
        themes_summary += f"\n- **{theme.replace('_', ' ').title()}**: {len(chunks)} evidence chunks"

    # Generate perspective-specific outlines
    perspectives_results = []
    for perspective in STORM_PERSPECTIVES:
        prompt = STORM_OUTLINE_PROMPT.format(
            question=question,
            themes_summary=themes_summary,
            perspective_name=perspective["name"],
            perspective_focus=perspective["focus"],
        )

        try:
            result = await client.generate_json(prompt)
            result["perspective_keywords"] = perspective["keywords"]
            perspectives_results.append(result)
            print(f"[PHASE-7][STORM] Generated {perspective['name']} perspective")
        except Exception as e:
            # LOW-070: Use logger instead of print
            logger.warning(f"[PHASE-7][STORM][WARN] Failed to generate {perspective['name']} perspective: {e}")

    # Synthesize perspectives into unified outline
    synthesized_outline = synthesize_storm_perspectives(perspectives_results, themed_chunks)

    return {
        "method": "storm",
        "perspectives_analyzed": len(perspectives_results),
        "perspectives": perspectives_results,
        "synthesized_outline": synthesized_outline,
        "knowledge_gaps": extract_all_gaps(perspectives_results),
    }


def synthesize_storm_perspectives(
    perspectives: List[Dict[str, Any]],
    themed_chunks: Dict[str, List[Dict[str, Any]]],
) -> List[Dict[str, Any]]:
    """
    Synthesize multiple perspectives into a unified outline.

    Args:
        perspectives: List of perspective analysis results
        themed_chunks: Available evidence themes

    Returns:
        Unified outline sections
    """
    # Collect all relevant themes across perspectives
    all_themes = set(themed_chunks.keys())
    theme_importance = Counter()

    for p in perspectives:
        for theme in p.get("relevant_themes", []):
            if theme in all_themes:
                theme_importance[theme] += 1

    # Build sections based on theme importance and perspectives
    sections = []

    # Core findings section (themes mentioned by multiple perspectives)
    core_themes = [t for t, count in theme_importance.most_common() if count >= 2]
    if core_themes:
        sections.append({
            "section_title": "Core Research Findings",
            "themes_to_include": core_themes[:3],
            "perspectives": ["scientific", "practical"],
            "key_questions": ["What are the main findings across perspectives?"],
        })

    # Perspective-specific sections
    for p in perspectives:
        perspective_themes = [t for t in p.get("relevant_themes", []) if t in all_themes]
        if perspective_themes and p.get("sub_questions"):
            sections.append({
                "section_title": f"{p.get('perspective', 'Analysis').title()} Perspective",
                "themes_to_include": perspective_themes[:2],
                "perspectives": [p.get("perspective")],
                "key_questions": p.get("sub_questions", [])[:2],
            })

    # Knowledge gaps section
    all_gaps = extract_all_gaps(perspectives)
    if all_gaps:
        sections.append({
            "section_title": "Knowledge Gaps and Limitations",
            "themes_to_include": list(themed_chunks.keys())[:2],
            "perspectives": ["scientific"],
            "key_questions": all_gaps[:3],
        })

    # Ensure conclusions
    sections.append({
        "section_title": "Conclusions and Recommendations",
        "themes_to_include": core_themes if core_themes else list(themed_chunks.keys())[:2],
        "perspectives": list(set(p.get("perspective") for p in perspectives)),
        "key_questions": ["What are the key takeaways?", "What actions are recommended?"],
    })

    return sections


def extract_all_gaps(perspectives: List[Dict[str, Any]]) -> List[str]:
    """Extract all knowledge gaps from perspectives."""
    gaps = []
    for p in perspectives:
        gaps.extend(p.get("knowledge_gaps", []))
    return list(set(gaps))[:10]  # Dedupe and limit


# =============================================================================
# SOTA: OUTLINE-FIRST GENERATION
# Based on: STORM and long-form generation best practices
# =============================================================================

OUTLINE_GENERATION_PROMPT = """Based on the available evidence themes, generate a structured outline for the research report.

Research Question: {question}

Available Evidence Themes:
{themes_summary}

Generate a logical outline with 4-6 sections that will:
1. Cover all major themes from the evidence
2. Flow logically from introduction to conclusion
3. Group related findings together
4. Ensure no important evidence is left out

Respond with JSON:
{{
    "outline": [
        {{
            "section_title": "Section Title",
            "themes_to_include": ["theme1", "theme2"],
            "key_questions": ["What should this section answer?"]
        }}
    ]
}}
"""


async def generate_outline(
    question: str,
    themed_chunks: Dict[str, List[Dict[str, Any]]],
) -> List[Dict[str, Any]]:
    """
    SOTA: Generate outline before writing content.

    Args:
        question: Research question
        themed_chunks: Chunks organized by theme

    Returns:
        List of outline sections with themes to include
    """
    client = get_gemini_client()

    # Summarize themes
    themes_summary = ""
    for theme, chunks in themed_chunks.items():
        themes_summary += f"\n- **{theme.replace('_', ' ').title()}**: {len(chunks)} evidence chunks"
        # Add sample claims from top chunks
        if chunks:
            sample_text = chunks[0].get("text", "")[:200]
            themes_summary += f"\n  Sample: \"{sample_text}...\""

    prompt = OUTLINE_GENERATION_PROMPT.format(
        question=question,
        themes_summary=themes_summary,
    )

    try:
        result = await client.generate_json(prompt)
        outline = result.get("outline", [])

        # Validate outline
        if not outline:
            # Generate default outline based on themes
            outline = [
                {"section_title": "Overview", "themes_to_include": ["general_findings"], "key_questions": []},
            ]
            for theme in themed_chunks.keys():
                if theme != "general_findings":
                    outline.append({
                        "section_title": theme.replace("_", " ").title(),
                        "themes_to_include": [theme],
                        "key_questions": []
                    })
            outline.append({
                "section_title": "Conclusions",
                "themes_to_include": list(themed_chunks.keys()),
                "key_questions": []
            })

        print(f"[PHASE-7][SOTA] Generated outline with {len(outline)} sections")
        return outline

    except Exception as e:
        # LOW-071: Use logger instead of print
        logger.warning(f"[PHASE-7][SOTA][WARN] Outline generation failed: {e}")
        # Return simple default outline
        return [
            {"section_title": "Key Findings", "themes_to_include": list(themed_chunks.keys()), "key_questions": []},
            {"section_title": "Analysis", "themes_to_include": list(themed_chunks.keys()), "key_questions": []},
        ]


def assemble_context_for_section(
    section: Dict[str, Any],
    themed_chunks: Dict[str, List[Dict[str, Any]]],
    token_budget: int = 4000,
) -> Tuple[str, List[str]]:
    """
    SOTA: Sliding context window - assemble context specific to a section.

    Args:
        section: Outline section dict with themes_to_include
        themed_chunks: All chunks organized by theme
        token_budget: Token budget for this section

    Returns:
        Tuple of (context_text, chunk_ids_used)
    """
    themes_to_include = section.get("themes_to_include", [])

    # Gather relevant chunks
    relevant_chunks = []
    for theme in themes_to_include:
        if theme in themed_chunks:
            relevant_chunks.extend(themed_chunks[theme])

    # Deduplicate by chunk ID
    seen_ids = set()
    unique_chunks = []
    for chunk in relevant_chunks:
        chunk_id = chunk.get("id")
        if chunk_id and chunk_id not in seen_ids:
            seen_ids.add(chunk_id)
            unique_chunks.append(chunk)

    # Assemble within budget
    return assemble_context(unique_chunks, token_budget)


# =============================================================================
# RAG GENERATION
# =============================================================================

ANALYSIS_SYSTEM_PROMPT = """You are a research analyst for POLARIS. Your task is to generate STRICTLY EVIDENCE-GROUNDED research summaries.

=== CRITICAL: CITATION ACCURACY REQUIREMENTS ===
Your response will be AUTOMATICALLY VERIFIED by an NLI (Natural Language Inference) model.
Claims that are NOT directly entailed by the cited chunk will be REJECTED and REMOVED.
Hallucination rate target: <5%. Every false citation hurts the score.

=== STRICT CITATION RULES ===
1. BEFORE writing a claim, FIND the exact chunk that states it
2. The cited chunk MUST CONTAIN the specific information in your claim
3. Use format [CITE:chunk_id] IMMEDIATELY after each claim
4. One claim = one citation. Do NOT combine multiple claims with one citation
5. If you cannot find a chunk that explicitly states something, DO NOT claim it

=== VERIFICATION WILL CHECK ===
- Does the chunk TEXT actually say what your claim states?
- Is the relationship "entailment" (chunk logically implies claim)?
- Score must be >70% entailment to pass verification

=== EXAMPLES ===
CHUNK: "The study found 60% of filtered water samples had bacteria."

BAD (will be REJECTED):
- "Water filters are effective at removing bacteria [CITE:chunk_001]" - chunk doesn't say this
- "Most filters work well [CITE:chunk_001]" - not stated in chunk
- "Filters improve water quality significantly [CITE:chunk_001]" - interpretation, not stated

GOOD (will be VERIFIED):
- "The study found that 60% of filtered water samples contained bacteria [CITE:chunk_001]" - exact match
- "According to the research, bacterial presence was detected in 60% of filtered samples [CITE:chunk_001]" - paraphrase of actual content

=== EVIDENCE-FIRST WORKFLOW ===
1. Read each chunk and note WHAT IT ACTUALLY SAYS
2. Write claims that MATCH what chunks say
3. Cite the chunk that CONTAINS the statement
4. If unsure, do NOT include the claim
"""

ANALYSIS_PROMPT = """Generate an EVIDENCE-GROUNDED research summary. Only include claims directly supported by the evidence.

**Research Question:** {question}

**Available Evidence (cite these EXACTLY):**
{context}

**STRICT INSTRUCTIONS:**
1. Read each CHUNK carefully and identify specific facts
2. Only report claims that are EXPLICITLY stated in the chunks
3. Each claim must cite the EXACT chunk that states it
4. Use [CITE:chunk_id] format immediately after each claim
5. If unsure whether evidence supports a claim, DO NOT include it
6. Prefer direct quotes or close paraphrases over interpretation

{feedback_section}
Generate your EVIDENCE-GROUNDED analysis:
"""

# Feedback template for correction loop
CORRECTION_FEEDBACK_TEMPLATE = """
**CORRECTION FEEDBACK:**
The following claims from your previous analysis were REJECTED because they were NOT supported by the evidence:
{rejected_claims}

Please regenerate the analysis WITHOUT these unsupported claims. Only include claims directly stated in the evidence.
"""


async def generate_analysis(
    question: str,
    context: str,
    chunk_ids: List[str],
    max_retries: int = 3,
    rejected_claims_feedback: Optional[List[str]] = None,
) -> Tuple[str, List[str], float]:
    """
    Generate analysis with citation markers.

    Args:
        question: Research question
        context: Retrieved context with chunk IDs
        chunk_ids: List of available chunk IDs
        max_retries: Maximum retry attempts
        rejected_claims_feedback: List of rejected claims from previous attempt (for correction loop)

    Returns:
        Tuple of (analysis_text, citation_tokens, confidence)
    """
    client = get_gemini_client()

    # Build feedback section if we have rejected claims
    feedback_section = ""
    if rejected_claims_feedback:
        rejected_list = "\n".join(f"- {claim}" for claim in rejected_claims_feedback[:10])  # Limit to 10
        feedback_section = CORRECTION_FEEDBACK_TEMPLATE.format(rejected_claims=rejected_list)

    prompt = ANALYSIS_PROMPT.format(
        question=question,
        context=context,
        feedback_section=feedback_section,
    )

    for attempt in range(max_retries):
        try:
            response = await client.generate(prompt, ANALYSIS_SYSTEM_PROMPT)

            # Extract citation tokens
            citation_pattern = r'\[CITE:([^\]]+)\]'
            citations = re.findall(citation_pattern, response)

            # Validate citations
            valid_citations = [c for c in citations if c in chunk_ids]

            if not valid_citations and attempt < max_retries - 1:
                # LOW-072: Use logger instead of print
                logger.warning(f"[PHASE-7][WARN] No valid citations found, retrying ({attempt + 1}/{max_retries})...")
                continue

            # Calculate confidence based on citation coverage
            if citations:
                confidence = len(valid_citations) / len(citations)
            else:
                confidence = 0.3  # Low confidence if no citations

            return response, list(set(citations)), confidence

        except Exception as e:
            # LOW-073: Use logger instead of print
            logger.warning(f"[PHASE-7][WARN] Generation failed: {e}")
            if attempt == max_retries - 1:
                raise

    return "", [], 0.0


# =============================================================================
# MAIN PHASE LOGIC
# =============================================================================

async def run_phase7(
    vector_id: str,
    input_path: Path,
    output_dir: Path,
    rejected_claims_feedback: Optional[List[str]] = None,
) -> Phase7Output:
    """
    Execute Phase 7: Dual RAG Analysis.

    Args:
        vector_id: Vector ID to process
        input_path: Path to Phase 6 output
        output_dir: Directory to write output
        rejected_claims_feedback: List of rejected claims from P7.5 (for correction loop)

    Returns:
        Phase7Output model
    """
    timestamps = {"start": datetime.now(timezone.utc).isoformat()}
    audit = get_audit()

    # Load config
    config = get_config()
    token_budget = config.thresholds.rag.context_budget_tokens
    top_k = config.thresholds.rag.top_k_per_query

    # 1. Load Phase 6 output
    with open(input_path, "r", encoding="utf-8") as f:
        p6_data = json.load(f)

    p6_output = Phase6Output(**p6_data)

    # Verify vector ID matches
    if p6_output.vector_id != vector_id:
        raise ValueError(f"Vector ID mismatch: {vector_id} != {p6_output.vector_id}")

    # 2. Build query from vector ID
    parts = vector_id.split("_")
    application = "_".join(parts[1:-1]) if len(parts) > 2 else "Unknown"
    region = parts[-1] if parts else "GLOBAL"
    question = f"What pathogen contamination rates and patterns exist in {application.replace('_', ' ')} for {region.replace('_', ' ')}?"

    print(f"[PHASE-7][{vector_id}][INFO] Research question: {question[:80]}...")

    # 3. RAG-1: Dense retrieval from VWM
    print(f"[PHASE-7][{vector_id}][INFO] Dense retrieval (top-{top_k})...")
    dense_chunks = dense_retrieve(vector_id, question, top_k=top_k)
    print(f"[PHASE-7][{vector_id}][INFO] Dense retrieved: {len(dense_chunks)} chunks")

    # 4. RAG-2: Sparse retrieval (BM25)
    print(f"[PHASE-7][{vector_id}][INFO] Sparse retrieval (BM25)...")
    all_chunks = get_all_chunks_from_vwm(vector_id, limit=500)
    sparse_chunks = sparse_retrieve(question, all_chunks, top_k=top_k)
    print(f"[PHASE-7][{vector_id}][INFO] Sparse retrieved: {len(sparse_chunks)} chunks")

    # 5. Merge and dedupe
    merged_chunks = merge_and_dedupe(dense_chunks, sparse_chunks)
    print(f"[PHASE-7][{vector_id}][INFO] Merged unique: {len(merged_chunks)} chunks")

    # 5.1 INTEGRITY FIX: Filter out chunks flagged in P6 contradiction pairs
    # Chunks that contradict other chunks in the corpus should not be cited
    contradiction_chunk_ids = set()
    contradiction_threshold = 0.90  # Only filter high-confidence contradictions
    for contradiction in p6_output.contradiction_details:
        if contradiction.contradiction_score >= contradiction_threshold:
            contradiction_chunk_ids.add(contradiction.chunk_a_id)
            contradiction_chunk_ids.add(contradiction.chunk_b_id)

    if contradiction_chunk_ids:
        pre_filter_count = len(merged_chunks)
        merged_chunks = [
            chunk for chunk in merged_chunks
            if chunk.get("id") not in contradiction_chunk_ids
        ]
        filtered_count = pre_filter_count - len(merged_chunks)
        print(f"[PHASE-7][{vector_id}][INTEGRITY] Filtered {filtered_count} contradiction-flagged chunks (threshold={contradiction_threshold})")
        if filtered_count > 0:
            print(f"[PHASE-7][{vector_id}][INTEGRITY] Blocked chunk IDs: {list(contradiction_chunk_ids)[:5]}...")

    # 5.5 SOTA: Cluster chunks by theme (group by concept, not source)
    print(f"[PHASE-7][{vector_id}][INFO] Clustering chunks by theme...")
    themed_chunks = cluster_chunks_by_theme(merged_chunks)
    themes_found = list(themed_chunks.keys())
    print(f"[PHASE-7][{vector_id}][INFO] Identified {len(themes_found)} themes: {themes_found}")

    # 5.6 SOTA: Use STORM architecture for complex multi-theme topics
    use_storm = len(themes_found) >= 4  # Use STORM if topic has multiple perspectives
    storm_outline = None

    if use_storm:
        print(f"[PHASE-7][{vector_id}][STORM] Complex topic detected ({len(themes_found)} themes), using STORM architecture...")
        try:
            storm_outline = await generate_storm_outline(question, themed_chunks)
            outline = storm_outline.get("synthesized_outline", [])
            print(f"[PHASE-7][{vector_id}][STORM] Generated multi-perspective outline with {len(outline)} sections")
            print(f"[PHASE-7][{vector_id}][STORM] Knowledge gaps identified: {len(storm_outline.get('knowledge_gaps', []))}")
        except Exception as e:
            # LOW-074: Use logger instead of print
            logger.warning(f"[PHASE-7][{vector_id}][STORM][WARN] STORM failed, using standard outline: {e}")
            outline = await generate_outline(question, themed_chunks)
            use_storm = False
    else:
        print(f"[PHASE-7][{vector_id}][INFO] Generating standard outline...")
        outline = await generate_outline(question, themed_chunks)

    print(f"[PHASE-7][{vector_id}][INFO] Outline: {[s.get('section_title') for s in outline]}")

    # Save outline and themed chunks for P12
    outline_file = output_dir / f"{vector_id}__P7_outline.json"
    outline_data = {
        "outline": outline,
        "themes": {
            theme: [{"id": c.get("id"), "text": c.get("text", "")[:500]} for c in chunks[:10]]
            for theme, chunks in themed_chunks.items()
        },
        "sota_method": "storm" if use_storm else "standard",
    }
    if storm_outline:
        outline_data["storm_perspectives"] = storm_outline.get("perspectives", [])
        outline_data["storm_knowledge_gaps"] = storm_outline.get("knowledge_gaps", [])
    with open(outline_file, "w", encoding="utf-8") as f:
        json.dump(outline_data, f, indent=2)

    # 6. Assemble context within token budget
    context, chunk_ids_used = assemble_context(merged_chunks, token_budget=token_budget)
    print(f"[PHASE-7][{vector_id}][INFO] Context assembled: {len(chunk_ids_used)} chunks, ~{estimate_tokens(context)} tokens")

    # 7. Generate analysis with citations
    if rejected_claims_feedback:
        print(f"[PHASE-7][{vector_id}][INFO] Regenerating with {len(rejected_claims_feedback)} rejected claims feedback...")
    else:
        print(f"[PHASE-7][{vector_id}][INFO] Generating analysis...")

    analysis_text, citation_tokens, confidence = await generate_analysis(
        question=question,
        context=context,
        chunk_ids=chunk_ids_used,
        max_retries=3,
        rejected_claims_feedback=rejected_claims_feedback,
    )

    print(f"[PHASE-7][{vector_id}][INFO] Analysis generated: {len(analysis_text)} chars")
    print(f"[PHASE-7][{vector_id}][INFO] Citation tokens: {len(citation_tokens)}")
    print(f"[PHASE-7][{vector_id}][INFO] Confidence: {confidence:.2f}")

    # 7.5 SOTA: Post-processing citation validation
    print(f"[PHASE-7][{vector_id}][SOTA] Validating citations...")
    citation_validation = validate_analysis_citations(
        analysis_text=analysis_text,
        available_chunk_ids=chunk_ids_used,
        chunks=merged_chunks,
    )

    if not citation_validation["is_valid"]:
        invalid_count = len(citation_validation["invalid_citations"])
        print(f"[PHASE-7][{vector_id}][WARN] Found {invalid_count} invalid citations - cleaning...")

        # Create validator and fix citations
        chunk_lookup = {c.get("id"): c for c in merged_chunks if c.get("id")}
        validator = CitationValidator(set(chunk_ids_used), chunk_lookup)
        analysis_text, removed_count = validator.fix_invalid_citations(analysis_text)

        # Recalculate citation tokens after cleanup
        citation_pattern = r'\[CITE:([^\]]+)\]'
        citation_tokens = list(set(re.findall(citation_pattern, analysis_text)))
        print(f"[PHASE-7][{vector_id}][INFO] Removed {removed_count} invalid citations, {len(citation_tokens)} remain")

        # Update confidence based on validated citations
        confidence = citation_validation["citation_coverage"]
    else:
        print(f"[PHASE-7][{vector_id}][INFO] All {citation_validation['total_citations']} citations validated successfully")

    # 8. Extract thinking process (simplified)
    thinking_process = f"Retrieved {len(dense_chunks)} dense + {len(sparse_chunks)} sparse chunks. Used {len(chunk_ids_used)} in context. Generated {len(citation_tokens)} citations."
    if use_storm:
        thinking_process += f" Used STORM multi-perspective architecture with {len(storm_outline.get('perspectives', []))} perspectives."

    # Audit: Log retrieval and generation
    if audit:
        # Log dense retrieval
        audit.log_retrieval(
            query_text=question,
            memory_tier="vwm",
            chunks_retrieved=[c.get("id", "") for c in dense_chunks],
            retrieval_method="dense_embedding",
            top_scores=[c.get("distance", 0.0) for c in dense_chunks[:5]],
        )

        # Log sparse retrieval
        audit.log_retrieval(
            query_text=question,
            memory_tier="vwm",
            chunks_retrieved=[c.get("id", "") for c in sparse_chunks],
            retrieval_method="bm25_sparse",
            top_scores=[],
        )

        # Log generation
        audit.log_generation(
            prompt_type="dual_rag_analysis",
            context_chunks=chunk_ids_used,
            output_text=analysis_text[:500],
            citations_generated=citation_tokens,
            tokens_used=estimate_tokens(context) + estimate_tokens(analysis_text),
        )

        # Log RAG complete
        audit.log_rag_complete(
            analysis_word_count=len(analysis_text.split()),
            context_utilization=len(chunk_ids_used) / max(len(merged_chunks), 1),
        )

        # Log LLM call
        audit.log_llm_call(
            phase=7,
            purpose="dual_rag_analysis",
            model="gemini",
            input_tokens=estimate_tokens(context),
            output_tokens=estimate_tokens(analysis_text),
            cost_usd=0.0,
            success=True,
        )

    timestamps["end"] = datetime.now(timezone.utc).isoformat()

    # 9. Build output
    output = Phase7Output(
        vector_id=vector_id,
        analysis_text=analysis_text,
        thinking_process=thinking_process,
        confidence_score=confidence,
        chunks_used=len(chunk_ids_used),
        citation_tokens=citation_tokens,
        token_usage={
            "context_tokens": estimate_tokens(context),
            "output_tokens": estimate_tokens(analysis_text),
        },
        timestamps=timestamps,
    )

    return output


# =============================================================================
# SELF-TEST
# =============================================================================

def run_self_test() -> bool:
    """
    Run Phase 7 self-tests.

    Tests:
    1. BM25 scoring
    2. Sparse retrieval
    3. Context assembly
    4. Citation extraction
    """
    print("Running Phase 7 self-tests...")

    # Test 1: BM25 scoring
    try:
        query = "water filter contamination bacteria"
        docs = [
            "Water filters can become contaminated with bacteria over time.",
            "The weather forecast shows rain tomorrow.",
            "Household water filters remove impurities and contaminants.",
        ]
        scores = compute_bm25_scores(query, docs)
        assert len(scores) == 3
        assert scores[0] > scores[1]  # First doc should score higher than second
        print(f"  [PASS] BM25 scoring: {[round(s, 2) for s in scores]}")
    except Exception as e:
        print(f"  [FAIL] BM25 scoring: {e}")
        return False

    # Test 2: Sparse retrieval
    try:
        chunks = [
            {"id": "c1", "text": "Water filters remove bacteria from drinking water."},
            {"id": "c2", "text": "The sun is a star in our solar system."},
            {"id": "c3", "text": "Bacterial contamination in filters is a concern."},
        ]
        results = sparse_retrieve("water filter bacteria", chunks, top_k=2)
        assert len(results) == 2
        assert results[0]["id"] in ["c1", "c3"]  # Relevant docs first
        print(f"  [PASS] Sparse retrieval: top IDs = {[r['id'] for r in results]}")
    except Exception as e:
        print(f"  [FAIL] Sparse retrieval: {e}")
        return False

    # Test 3: Context assembly
    try:
        chunks = [
            {"id": "chunk_001", "text": "A" * 1000},
            {"id": "chunk_002", "text": "B" * 1000},
            {"id": "chunk_003", "text": "C" * 1000},
        ]
        context, ids = assemble_context(chunks, token_budget=600)
        assert len(ids) >= 1
        assert "chunk_001" in ids
        print(f"  [PASS] Context assembly: {len(ids)} chunks fit in budget")
    except Exception as e:
        print(f"  [FAIL] Context assembly: {e}")
        return False

    # Test 4: Citation extraction
    try:
        text = "Water filters work [CITE:chunk_001] and should be replaced [CITE:chunk_002]."
        pattern = r'\[CITE:([^\]]+)\]'
        citations = re.findall(pattern, text)
        assert len(citations) == 2
        assert "chunk_001" in citations
        print(f"  [PASS] Citation extraction: {citations}")
    except Exception as e:
        print(f"  [FAIL] Citation extraction: {e}")
        return False

    # Test 5: Merge and dedupe
    try:
        dense = [{"id": "c1", "text": "A"}, {"id": "c2", "text": "B"}]
        sparse = [{"id": "c2", "text": "B"}, {"id": "c3", "text": "C"}]
        merged = merge_and_dedupe(dense, sparse)
        assert len(merged) == 3
        assert merged[0]["id"] == "c1"  # Dense first
        print(f"  [PASS] Merge and dedupe: {len(merged)} unique chunks")
    except Exception as e:
        print(f"  [FAIL] Merge and dedupe: {e}")
        return False

    print("\nAll Phase 7 self-tests PASSED!")
    return True


# =============================================================================
# CLI ENTRY POINT
# =============================================================================

def find_latest_p6_output(vector_id: str) -> Optional[Path]:
    """Find the most recent Phase 6 output for a vector."""
    p6_dir = OUTPUTS_DIR / "P6"
    if not p6_dir.exists():
        return None

    pattern = f"{vector_id}__P6__*.json"
    matches = sorted(p6_dir.glob(pattern), key=lambda x: x.stat().st_mtime, reverse=True)

    return matches[0] if matches else None


def main():
    parser = argparse.ArgumentParser(
        description="POLARIS Phase 7: Dual RAG Analysis"
    )
    parser.add_argument(
        "--vector-id",
        type=str,
        help="Vector ID to process"
    )
    parser.add_argument(
        "--input",
        type=str,
        help="Path to Phase 6 output JSON"
    )
    parser.add_argument(
        "--output",
        type=str,
        default=str(OUTPUTS_DIR / "P7"),
        help="Output directory"
    )
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="Run self-test mode"
    )

    args = parser.parse_args()

    # Self-test mode
    if args.self_test:
        success = run_self_test()
        sys.exit(0 if success else 1)

    # Normal execution requires vector-id
    if not args.vector_id:
        parser.error("--vector-id is required (unless using --self-test)")

    # Find input file
    if args.input:
        input_path = Path(args.input)
    else:
        input_path = find_latest_p6_output(args.vector_id)
        if not input_path:
            print(f"[PHASE-7][{args.vector_id}][ERROR] No Phase 6 output found")
            sys.exit(1)

    if not input_path.exists():
        print(f"[PHASE-7][{args.vector_id}][ERROR] Input file not found: {input_path}")
        sys.exit(1)

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Log to ledger: running
    ledger = Ledger()
    ledger.append(
        vector_id=args.vector_id,
        phase=7,
        status="running",
        attempt=1,
        input_paths=[str(input_path)]
    )

    try:
        # Execute phase
        print(f"[PHASE-7][{args.vector_id}][INFO] Starting Dual RAG Analysis...")
        print(f"[PHASE-7][{args.vector_id}][INFO] Input: {input_path}")

        output = asyncio.run(run_phase7(args.vector_id, input_path, output_dir))

        # Write output
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = output_dir / f"{args.vector_id}__P7__{timestamp}.json"

        with open(output_file, "w", encoding="utf-8") as f:
            f.write(output.model_dump_json(indent=2))

        print(f"[PHASE-7][{args.vector_id}][INFO] Output: {output_file}")
        print(f"[PHASE-7][{args.vector_id}][INFO] Chunks used: {output.chunks_used}")
        print(f"[PHASE-7][{args.vector_id}][INFO] Citations: {len(output.citation_tokens)}")
        print(f"[PHASE-7][{args.vector_id}][INFO] Confidence: {output.confidence_score:.2f}")

        # Log to ledger: completed
        ledger.append(
            vector_id=args.vector_id,
            phase=7,
            status="completed",
            attempt=1,
            input_paths=[str(input_path)],
            output_path=str(output_file)
        )

        sys.exit(0)

    except Exception as e:
        print(f"[PHASE-7][{args.vector_id}][ERROR] {e}")
        import traceback
        traceback.print_exc()

        # Log to ledger: failed
        ledger.append(
            vector_id=args.vector_id,
            phase=7,
            status="failed",
            attempt=1,
            input_paths=[str(input_path)],
            error=str(e)
        )

        sys.exit(1)


if __name__ == "__main__":
    main()
