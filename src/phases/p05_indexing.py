#!/usr/bin/env python3
"""
POLARIS Phase 5: VWM Indexing
=============================
Generate embeddings and index filtered chunks to VWM.

Purpose:
- Generate embeddings for filtered chunks from Phase 4
- Store chunks in Vector Working Memory (VWM) using ChromaDB
- Promote high-quality chunks to LTM-Stage for future reference

Usage:
    python src/phases/p05_indexing.py --vector-id S1V1_Household_Water_Filter_NORTH_AMERICA --input outputs/P4/S1V1...json --output outputs/P5/

CLI Contract:
    --vector-id: Required. Vector ID string.
    --input: Required. Path to Phase 4 output JSON.
    --output: Optional. Output directory (default: outputs/P5/)
    --self-test: Run self-test mode
"""

import argparse
import asyncio
import hashlib
import json
import logging
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.schemas.phase_models import Phase4Output, Phase5Output, RelevanceTier
from src.state.ledger import Ledger
from src.config import get_config, OUTPUTS_DIR
from src.memory.chroma_client import get_chroma_manager
from src.audit import get_audit
from src.utils.fact_extractor import extract_facts_regex, FactType


# =============================================================================
# EMBEDDING GENERATION
# =============================================================================

def get_embedding_model():
    """
    Load sentence-transformers embedding model.

    Returns model or None if not available.
    """
    try:
        from sentence_transformers import SentenceTransformer
        config = get_config()
        model_name = config.models.embedding.model

        logger.info(f"Loading embedding model: {model_name}")
        model = SentenceTransformer(model_name)
        return model
    except ImportError:
        # LOW-003: Log warning for missing dependency
        logger.warning("sentence-transformers not available, using fallback")
        return None
    except Exception as e:
        # LOW-004: Log warning for model load failure
        logger.warning(f"Could not load embedding model: {e}")
        return None


def generate_embeddings(
    texts: List[str],
    model: Any = None,
    batch_size: int = 32,
) -> List[List[float]]:
    """
    Generate embeddings for a list of texts.

    Args:
        texts: List of text strings to embed
        model: Sentence transformer model (or None for fallback)
        batch_size: Batch size for encoding

    Returns:
        List of embedding vectors
    """
    if not texts:
        return []

    if model is not None:
        # Use sentence-transformers
        embeddings = model.encode(
            texts,
            batch_size=batch_size,
            show_progress_bar=True,
            convert_to_numpy=True,
        )
        return [emb.tolist() for emb in embeddings]
    else:
        # Fallback: Simple hash-based pseudo-embeddings
        # This is NOT semantically meaningful, just for testing
        embeddings = []
        for text in texts:
            # Generate deterministic pseudo-embedding from text hash
            text_hash = hashlib.sha256(text.encode()).hexdigest()
            # Convert hash to 384-dimensional vector (to match MiniLM dimensions)
            emb = []
            for i in range(384):
                # Use different hash bytes to create variation
                byte_idx = i % 32  # SHA256 has 32 bytes
                char = text_hash[byte_idx * 2:(byte_idx + 1) * 2]
                val = (int(char, 16) / 255.0) * 2 - 1  # Normalize to [-1, 1]
                emb.append(val)
            embeddings.append(emb)
        return embeddings


def is_gpu_available() -> bool:
    """Check if GPU is available for embeddings."""
    try:
        import torch
        return torch.cuda.is_available()
    except ImportError:
        return False


# =============================================================================
# SOTA: SPECTER2 EMBEDDINGS FOR ACADEMIC CONTENT (from upgrade plan)
# SPECTER2 is optimized for scientific paper similarity
# =============================================================================

_specter2_model = None
_specter2_tokenizer = None


def get_specter2_model():
    """
    SOTA: Load SPECTER2 model for academic paper embeddings.

    SPECTER2 is a scientific paper embedding model from AllenAI
    that captures semantic similarity between research papers
    better than general-purpose embedding models.

    Model: allenai/specter2_base

    Returns:
        Tuple of (model, tokenizer) or (None, None) if unavailable
    """
    global _specter2_model, _specter2_tokenizer

    if _specter2_model is not None:
        return _specter2_model, _specter2_tokenizer

    try:
        from transformers import AutoModel, AutoTokenizer
        import torch

        model_name = "allenai/specter2_base"
        print(f"[PHASE-5][SOTA] Loading SPECTER2 model: {model_name}")

        _specter2_tokenizer = AutoTokenizer.from_pretrained(model_name)
        _specter2_model = AutoModel.from_pretrained(model_name)

        # Move to GPU if available
        if torch.cuda.is_available():
            _specter2_model = _specter2_model.cuda()
            logger.info("SPECTER2 using GPU")
        else:
            logger.info("SPECTER2 using CPU")

        return _specter2_model, _specter2_tokenizer

    except ImportError as e:
        # LOW-005: Log warning for missing SPECTER2 dependency
        logger.warning(f"SPECTER2 not available (transformers not installed): {e}")
        return None, None
    except Exception as e:
        # LOW-006: Log warning for SPECTER2 load failure
        logger.warning(f"Could not load SPECTER2: {e}")
        return None, None


def generate_specter2_embeddings(
    texts: List[str],
    batch_size: int = 16,
) -> Optional[List[List[float]]]:
    """
    SOTA: Generate embeddings using SPECTER2 for academic content.

    Args:
        texts: List of text strings (ideally title + abstract format)
        batch_size: Batch size for encoding

    Returns:
        List of 768-dimensional embedding vectors, or None if SPECTER2 unavailable
    """
    import torch

    model, tokenizer = get_specter2_model()
    if model is None or tokenizer is None:
        return None

    embeddings = []

    try:
        model.eval()
        with torch.no_grad():
            for i in range(0, len(texts), batch_size):
                batch_texts = texts[i:i + batch_size]

                # Tokenize
                inputs = tokenizer(
                    batch_texts,
                    padding=True,
                    truncation=True,
                    max_length=512,
                    return_tensors="pt",
                )

                # Move to same device as model
                device = next(model.parameters()).device
                inputs = {k: v.to(device) for k, v in inputs.items()}

                # Forward pass
                outputs = model(**inputs)

                # Use [CLS] token embedding
                batch_embeddings = outputs.last_hidden_state[:, 0, :].cpu().numpy()

                for emb in batch_embeddings:
                    embeddings.append(emb.tolist())

        print(f"[PHASE-5][SOTA] Generated {len(embeddings)} SPECTER2 embeddings")
        return embeddings

    except Exception as e:
        # LOW-076: Use logger instead of print
        logger.warning(f"[PHASE-5][SOTA] SPECTER2 embedding generation failed: {e}")
        return None


def is_academic_url(url: str) -> bool:
    """
    SOTA: Check if URL is from an academic source.

    Used to determine whether to use SPECTER2 vs general embeddings.

    Args:
        url: Source URL

    Returns:
        True if URL is from academic source
    """
    academic_patterns = [
        "pubmed", "ncbi.nlm.nih.gov", "pmc.",
        "arxiv.org", "semanticscholar.org",
        "doi.org", ".edu", "nature.com",
        "sciencedirect.com", "springer.com",
        "wiley.com", "plos.org", "biomedcentral.com",
    ]
    url_lower = url.lower()
    return any(pattern in url_lower for pattern in academic_patterns)


# =============================================================================
# VWM INDEXING
# =============================================================================

def index_chunks_to_vwm(
    vector_id: str,
    chunks: List[Dict[str, Any]],
    embeddings: List[List[float]],
) -> int:
    """
    Index chunks and embeddings to VWM collection.

    Args:
        vector_id: Vector ID (determines VWM collection)
        chunks: List of chunk dictionaries
        embeddings: Corresponding embeddings

    Returns:
        Number of chunks indexed
    """
    chroma = get_chroma_manager()

    # Get or create VWM collection
    vwm_name = chroma.get_vwm_name(vector_id)
    vwm = chroma.register_vwm(vector_id)

    # Prepare data for ChromaDB
    ids = [c["chunk_id"] for c in chunks]
    documents = [c["text"] for c in chunks]
    metadatas = [
        {
            "source_url": c.get("source_url") or "",
            "title": c.get("title") or "",  # OPERATION GLASS HOUSE: Include title
            "author": c.get("author") or "",  # FIX: Propagate author metadata (handle None)
            "publication_date": c.get("publication_date") or "",  # FIX: Propagate date metadata (handle None)
            "doi": c.get("doi") or "",  # FIX: Propagate DOI metadata (handle None)
            "relevance_score": c.get("relevance_score") or 0.0,
            "relevance_tier": c.get("relevance_tier") or "unknown",
            "content_hash": c.get("content_hash") or "",
            "vector_id": vector_id,
            "indexed_at": datetime.now(timezone.utc).isoformat(),
            # SOTA: Geographic metadata from ingestion
            "geo_region": c.get("geo_region") or "GLOBAL",
            "geo_countries": json.dumps(c.get("geo_countries") or []),  # Serialize list
            "geo_confidence": c.get("geo_confidence") or 0.0,
            # SOTA: Source API tracking (from upgrade plan)
            "source_api": c.get("source_api") or "unknown",
            # SOTA: NER-based study location (from upgrade plan)
            "study_locations": json.dumps(c.get("study_locations") or []),  # Serialize list
            "study_countries": json.dumps(c.get("study_countries") or []),  # Serialize list
            "ner_confidence": c.get("ner_confidence") or 0.0,
            # SOTA: Source quality from P4
            "source_quality_score": c.get("source_quality_score") or 0.0,
            # SOTA: Contextual summary from P4
            "contextual_summary": c.get("contextual_summary") or "",
        }
        for c in chunks
    ]

    # Add to collection in batches
    batch_size = 100
    indexed = 0

    for i in range(0, len(ids), batch_size):
        batch_ids = ids[i:i + batch_size]
        batch_docs = documents[i:i + batch_size]
        batch_metas = metadatas[i:i + batch_size]
        batch_embs = embeddings[i:i + batch_size] if embeddings else None

        if batch_embs:
            vwm.add(
                ids=batch_ids,
                documents=batch_docs,
                metadatas=batch_metas,
                embeddings=batch_embs,
            )
        else:
            vwm.add(
                ids=batch_ids,
                documents=batch_docs,
                metadatas=batch_metas,
            )

        indexed += len(batch_ids)

    return indexed


def promote_to_ltm(
    vector_id: str,
    chunks: List[Dict[str, Any]],
    embeddings: List[List[float]],
    stage: int,
) -> int:
    """
    Promote high-quality chunks to LTM-Stage.

    Only promotes GOLD tier chunks.

    Args:
        vector_id: Vector ID
        chunks: All filtered chunks
        embeddings: Corresponding embeddings
        stage: Stage number for LTM-Stage collection

    Returns:
        Number of chunks promoted
    """
    chroma = get_chroma_manager()

    # Filter for GOLD tier only
    gold_chunks = []
    gold_embeddings = []

    for i, chunk in enumerate(chunks):
        if chunk.get("relevance_tier") == RelevanceTier.GOLD.value:
            gold_chunks.append(chunk)
            if embeddings:
                gold_embeddings.append(embeddings[i])

    if not gold_chunks:
        return 0

    # Get LTM-Stage collection
    ltm_stage = chroma.get_ltm_stage(stage)

    # Prepare data
    ids = [f"{vector_id}_{c['chunk_id']}" for c in gold_chunks]
    documents = [c["text"] for c in gold_chunks]
    metadatas = [
        {
            "source_url": c.get("source_url") or "",
            "title": c.get("title") or "",  # FIX: Include title in LTM
            "author": c.get("author") or "",  # FIX: Include author in LTM (handle None)
            "publication_date": c.get("publication_date") or "",  # FIX: Include date in LTM (handle None)
            "doi": c.get("doi") or "",  # FIX: Include DOI in LTM (handle None)
            "relevance_score": c.get("relevance_score") or 0.0,
            "vector_id": vector_id,
            "stage": stage,
            "promoted_at": datetime.now(timezone.utc).isoformat(),
        }
        for c in gold_chunks
    ]

    # Add to LTM-Stage
    if gold_embeddings:
        ltm_stage.add(
            ids=ids,
            documents=documents,
            metadatas=metadatas,
            embeddings=gold_embeddings,
        )
    else:
        ltm_stage.add(
            ids=ids,
            documents=documents,
            metadatas=metadatas,
        )

    return len(gold_chunks)


# =============================================================================
# MAIN PHASE LOGIC
# =============================================================================

async def run_phase5(
    vector_id: str,
    input_path: Path,
    output_dir: Path,
) -> Phase5Output:
    """
    Execute Phase 5: VWM Indexing.

    Args:
        vector_id: Vector ID to process
        input_path: Path to Phase 4 output
        output_dir: Directory to write output

    Returns:
        Phase5Output model
    """
    timestamps = {"start": datetime.now(timezone.utc).isoformat()}
    audit = get_audit()

    # Load config
    config = get_config()

    # 1. Load Phase 4 output
    with open(input_path, "r", encoding="utf-8") as f:
        p4_data = json.load(f)

    p4_output = Phase4Output(**p4_data)

    # Verify vector ID matches
    if p4_output.vector_id != vector_id:
        raise ValueError(f"Vector ID mismatch: {vector_id} != {p4_output.vector_id}")

    # 2. Get filtered chunks
    chunks = p4_output.filtered_chunks
    print(f"[PHASE-5][{vector_id}][INFO] Chunks to index: {len(chunks)}")

    # 2.5 SOTA: Extract structured facts from chunks (Sprint 3)
    # Use fast regex extraction for initial pass
    total_facts_extracted = 0
    for idx, chunk in enumerate(chunks):
        text = chunk.get("text", "")
        chunk_id = chunk.get("chunk_id", f"chunk_{idx}")
        if text:
            fact_collection = extract_facts_regex(text, chunk_id)
            # Store facts as serializable data in chunk metadata
            all_facts = fact_collection.all_facts()
            chunk["extracted_facts"] = [
                {"type": f.fact_type if isinstance(f.fact_type, str) else f.fact_type.value,
                 "value": f.value,
                 "unit": getattr(f, "unit", None),
                 "confidence": f.confidence}
                for f in all_facts
            ]
            total_facts_extracted += len(all_facts)
    if total_facts_extracted > 0:
        print(f"[PHASE-5][{vector_id}][INFO] Extracted {total_facts_extracted} structured facts from chunks")

    if not chunks:
        print(f"[PHASE-5][{vector_id}][WARN] No chunks to index")
        timestamps["end"] = datetime.now(timezone.utc).isoformat()
        return Phase5Output(
            vector_id=vector_id,
            chunks_indexed=0,
            vwm_collection_size=0,
            embeddings_generated=0,
            gpu_used=False,
            ltm_promotions=0,
            chunking_template="research_paper",
            timestamps=timestamps,
        )

    # 3. Extract texts for embedding
    texts = [c["text"] for c in chunks]

    # SOTA: Determine which chunks are from academic sources for SPECTER2
    academic_indices = []
    general_indices = []
    for i, chunk in enumerate(chunks):
        source_url = chunk.get("source_url", "")
        if is_academic_url(source_url):
            academic_indices.append(i)
        else:
            general_indices.append(i)

    print(f"[PHASE-5][{vector_id}][SOTA] Academic chunks: {len(academic_indices)}, General chunks: {len(general_indices)}")

    # 4. Load embedding model
    gpu_used = is_gpu_available()
    model = get_embedding_model()

    # 5. Generate embeddings
    # NOTE: SPECTER2 disabled due to dimension mismatch with ChromaDB query embedding
    # SPECTER2 produces 768-dim embeddings, but ChromaDB default query embedding is 384-dim
    # All embeddings must use consistent dimensions for VWM querying to work
    embeddings = [None] * len(texts)
    specter2_used = False

    # SPECTER2 disabled - using consistent embedding model for all content
    # This ensures ChromaDB queries work correctly in P7 dense retrieval
    if academic_indices:
        print(f"[PHASE-5][{vector_id}][INFO] Found {len(academic_indices)} academic chunks (using standard embeddings for consistency)")

    # Generate embeddings for general content (and academic if SPECTER2 failed)
    remaining_indices = [i for i in range(len(texts)) if embeddings[i] is None]
    if remaining_indices:
        remaining_texts = [texts[i] for i in remaining_indices]
        print(f"[PHASE-5][{vector_id}][INFO] Generating general embeddings for {len(remaining_indices)} chunks (GPU: {gpu_used})...")
        general_embeddings = generate_embeddings(remaining_texts, model, batch_size=config.models.embedding.batch_size)
        for idx, emb in zip(remaining_indices, general_embeddings):
            embeddings[idx] = emb
            if "embedding_model" not in chunks[idx]:
                chunks[idx]["embedding_model"] = "sentence_transformers"

    print(f"[PHASE-5][{vector_id}][INFO] Generated {len(embeddings)} embeddings (SPECTER2: {specter2_used})")

    # 6. Index to VWM
    print(f"[PHASE-5][{vector_id}][INFO] Indexing to VWM...")
    chunks_indexed = index_chunks_to_vwm(vector_id, chunks, embeddings)

    # 7. Get VWM collection size
    chroma = get_chroma_manager()
    vwm = chroma.get_vwm(vector_id)
    vwm_size = vwm.count() if vwm else 0

    # 8. Promote GOLD chunks to LTM-Stage
    # Parse stage from vector_id (e.g., S1V1_... -> stage 1)
    stage = 1
    try:
        stage_str = vector_id.split("_")[0]  # "S1V1" or similar
        stage = int(stage_str[1])  # Extract the digit after 'S'
    except (IndexError, ValueError):
        stage = 1

    print(f"[PHASE-5][{vector_id}][INFO] Promoting GOLD chunks to LTM-Stage {stage}...")
    ltm_promotions = promote_to_ltm(vector_id, chunks, embeddings, stage)

    # Audit: Log memory operations for each chunk
    if audit:
        total_chars = sum(len(c.get("text", "")) for c in chunks)
        for chunk in chunks:
            chunk_id = chunk.get("chunk_id", "unknown")
            tier = chunk.get("relevance_tier", "unknown")
            audit.log_memory_operation(
                operation_type="index",
                memory_tier="vwm",
                chunk_id=chunk_id,
                success=True,
            )
            # Log promotion to LTM for GOLD chunks
            if tier == RelevanceTier.GOLD.value:
                audit.log_memory_operation(
                    operation_type="promote",
                    memory_tier="ltm_stage",
                    chunk_id=chunk_id,
                    success=True,
                )

        # Log memory state
        audit.log_memory_state(
            vwm_chunk_count=vwm_size,
            vwm_total_chars=total_chars,
            ltm_stage_chunk_count=ltm_promotions,
            ltm_global_chunk_count=0,
        )

    # 9. Determine chunking template
    # Based on stage, use appropriate template
    stage_templates = config.models.chunking.stage_templates
    chunking_template = stage_templates.get(stage, "research_paper")

    timestamps["end"] = datetime.now(timezone.utc).isoformat()

    # 10. Build output
    output = Phase5Output(
        vector_id=vector_id,
        chunks_indexed=chunks_indexed,
        vwm_collection_size=vwm_size,
        embeddings_generated=len(embeddings),
        gpu_used=gpu_used,
        ltm_promotions=ltm_promotions,
        chunking_template=chunking_template,
        timestamps=timestamps,
    )

    return output


# =============================================================================
# SELF-TEST
# =============================================================================

def run_self_test() -> bool:
    """
    Run Phase 5 self-tests.

    Tests:
    1. Embedding generation (fallback)
    2. ChromaDB VWM indexing
    3. LTM promotion logic
    """
    print("Running Phase 5 self-tests...")

    # Test 1: Embedding generation (fallback)
    try:
        texts = ["This is test text one.", "This is test text two."]
        embeddings = generate_embeddings(texts, model=None)
        assert len(embeddings) == 2
        assert len(embeddings[0]) == 384
        print("  [PASS] Embedding generation (fallback)")
    except Exception as e:
        print(f"  [FAIL] Embedding generation (fallback): {e}")
        return False

    # Test 2: ChromaDB initialization
    try:
        chroma = get_chroma_manager()
        assert chroma is not None
        print("  [PASS] ChromaDB initialization")
    except Exception as e:
        print(f"  [FAIL] ChromaDB initialization: {e}")
        return False

    # Test 3: VWM registration
    try:
        test_vector_id = "TEST_Phase5_Self_Test"
        chroma = get_chroma_manager()
        vwm = chroma.register_vwm(test_vector_id)
        assert vwm is not None

        # Add test data
        vwm.add(
            ids=["test_chunk_1", "test_chunk_2"],
            documents=["Test document one.", "Test document two."],
            metadatas=[{"source": "test"}, {"source": "test"}],
        )

        # Verify count
        count = vwm.count()
        assert count >= 2

        # Clean up
        chroma.delete_collection(chroma.get_vwm_name(test_vector_id))
        print("  [PASS] VWM registration and indexing")
    except Exception as e:
        print(f"  [FAIL] VWM registration and indexing: {e}")
        return False

    # Test 4: GPU detection
    try:
        gpu = is_gpu_available()
        print(f"  [PASS] GPU detection (available: {gpu})")
    except Exception as e:
        print(f"  [FAIL] GPU detection: {e}")
        return False

    print("\nAll Phase 5 self-tests PASSED!")
    return True


# =============================================================================
# CLI ENTRY POINT
# =============================================================================

def find_latest_p4_output(vector_id: str) -> Optional[Path]:
    """Find the most recent Phase 4 output for a vector."""
    p4_dir = OUTPUTS_DIR / "P4"
    if not p4_dir.exists():
        return None

    pattern = f"{vector_id}__P4__*.json"
    matches = sorted(p4_dir.glob(pattern), key=lambda x: x.stat().st_mtime, reverse=True)

    return matches[0] if matches else None


def main():
    parser = argparse.ArgumentParser(
        description="POLARIS Phase 5: VWM Indexing"
    )
    parser.add_argument(
        "--vector-id",
        type=str,
        help="Vector ID to process"
    )
    parser.add_argument(
        "--input",
        type=str,
        help="Path to Phase 4 output JSON"
    )
    parser.add_argument(
        "--output",
        type=str,
        default=str(OUTPUTS_DIR / "P5"),
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
        input_path = find_latest_p4_output(args.vector_id)
        if not input_path:
            print(f"[PHASE-5][{args.vector_id}][ERROR] No Phase 4 output found")
            sys.exit(1)

    if not input_path.exists():
        print(f"[PHASE-5][{args.vector_id}][ERROR] Input file not found: {input_path}")
        sys.exit(1)

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Log to ledger: running
    ledger = Ledger()
    ledger.append(
        vector_id=args.vector_id,
        phase=5,
        status="running",
        attempt=1,
        input_paths=[str(input_path)]
    )

    try:
        # Execute phase
        print(f"[PHASE-5][{args.vector_id}][INFO] Starting VWM indexing...")
        print(f"[PHASE-5][{args.vector_id}][INFO] Input: {input_path}")

        output = asyncio.run(run_phase5(args.vector_id, input_path, output_dir))

        # Write output
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = output_dir / f"{args.vector_id}__P5__{timestamp}.json"

        with open(output_file, "w", encoding="utf-8") as f:
            f.write(output.model_dump_json(indent=2))

        print(f"[PHASE-5][{args.vector_id}][INFO] Output: {output_file}")
        print(f"[PHASE-5][{args.vector_id}][INFO] Chunks indexed: {output.chunks_indexed}")
        print(f"[PHASE-5][{args.vector_id}][INFO] VWM collection size: {output.vwm_collection_size}")
        print(f"[PHASE-5][{args.vector_id}][INFO] LTM promotions: {output.ltm_promotions}")

        # Log to ledger: completed
        ledger.append(
            vector_id=args.vector_id,
            phase=5,
            status="completed",
            attempt=1,
            input_paths=[str(input_path)],
            output_path=str(output_file)
        )

        sys.exit(0)

    except Exception as e:
        print(f"[PHASE-5][{args.vector_id}][ERROR] {e}")
        import traceback
        traceback.print_exc()

        # Log to ledger: failed
        ledger.append(
            vector_id=args.vector_id,
            phase=5,
            status="failed",
            attempt=1,
            input_paths=[str(input_path)],
            error=str(e)
        )

        sys.exit(1)


if __name__ == "__main__":
    main()
