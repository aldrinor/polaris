"""
Phase 11: Knowledge Integration - LTM Promotion and Archival

This phase promotes verified findings to Long-Term Memory (LTM) and
archives the research outputs when gating case is CASE_1.

ARCHITECT DIRECTIVE: NO MOCKING OF LOGIC
- Real LTM updates to global knowledge base
- Actual claim persistence to archive
- Live cross-referencing

Conditions:
- Only executes full LTM update when P11 gating_case == CASE_1
- For other cases, generates archive only (no LTM promotion)
"""

import asyncio
import json
import logging
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

# Configure logging
logger = logging.getLogger(__name__)

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.schemas.phase_models import (
    Phase6Output, Phase7Output, Phase9Output, Phase10Output, Phase11Output,
    GatingCase
)
from src.state.ledger import Ledger
from src.config import get_config, OUTPUTS_DIR, STATE_DIR
from src.memory.chroma_client import get_chroma_manager
from src.audit import get_audit


# ============================================================================
# SOTA: STRUCTURED ENTITY STORAGE
# Store extracted entities (pathogens, chemicals, locations) for cross-vector queries
# ============================================================================

class StructuredEntityStore:
    """
    SOTA: Structured storage for extracted entities enabling cross-vector queries.

    Stores entities extracted from research with:
    - Entity type (pathogen, chemical, location, organization, etc.)
    - Source vector ID
    - Context (surrounding text)
    - Relationships to other entities
    """

    def __init__(self):
        self._entity_file = STATE_DIR / "entity_store.json"
        self._entities = self._load_entities()

    def _load_entities(self) -> Dict[str, List[Dict[str, Any]]]:
        """Load entities from persistent storage."""
        if self._entity_file.exists():
            try:
                with open(self._entity_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return {"entities": [], "by_type": {}, "by_vector": {}}
        return {"entities": [], "by_type": {}, "by_vector": {}}

    def _save_entities(self):
        """Persist entities to storage."""
        self._entity_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self._entity_file, "w", encoding="utf-8") as f:
            json.dump(self._entities, f, indent=2)

    def add_entity(
        self,
        entity_text: str,
        entity_type: str,
        vector_id: str,
        context: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Add an entity to the store.

        Args:
            entity_text: The entity text (e.g., "E. coli")
            entity_type: Type of entity (pathogen, chemical, location, etc.)
            vector_id: Source vector ID
            context: Surrounding context text
            metadata: Additional metadata

        Returns:
            Entity ID
        """
        entity_id = f"ent_{entity_type}_{len(self._entities['entities']):06d}"

        entity = {
            "entity_id": entity_id,
            "text": entity_text,
            "text_normalized": entity_text.lower().strip(),
            "type": entity_type,
            "vector_id": vector_id,
            "context": context[:500],
            "metadata": metadata or {},
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

        self._entities["entities"].append(entity)

        # Index by type
        if entity_type not in self._entities["by_type"]:
            self._entities["by_type"][entity_type] = []
        self._entities["by_type"][entity_type].append(entity_id)

        # Index by vector
        if vector_id not in self._entities["by_vector"]:
            self._entities["by_vector"][vector_id] = []
        self._entities["by_vector"][vector_id].append(entity_id)

        return entity_id

    def get_entities_by_type(self, entity_type: str) -> List[Dict[str, Any]]:
        """Get all entities of a specific type."""
        entity_ids = self._entities["by_type"].get(entity_type, [])
        return [e for e in self._entities["entities"] if e["entity_id"] in entity_ids]

    def get_entities_by_vector(self, vector_id: str) -> List[Dict[str, Any]]:
        """Get all entities from a specific vector."""
        entity_ids = self._entities["by_vector"].get(vector_id, [])
        return [e for e in self._entities["entities"] if e["entity_id"] in entity_ids]

    def search_entities(self, query: str, entity_type: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        SOTA: Search entities across all vectors.

        Args:
            query: Search query (matches entity text)
            entity_type: Optional filter by type

        Returns:
            Matching entities
        """
        query_lower = query.lower()
        results = []

        for entity in self._entities["entities"]:
            if entity_type and entity["type"] != entity_type:
                continue
            if query_lower in entity["text_normalized"]:
                results.append(entity)

        return results

    def commit(self):
        """Persist changes to disk."""
        self._save_entities()


def extract_entities_from_text(text: str, vector_id: str) -> List[Dict[str, Any]]:
    """
    SOTA: Extract structured entities from text using pattern matching.

    Args:
        text: Text to extract entities from
        vector_id: Source vector ID

    Returns:
        List of extracted entity dictionaries
    """
    import re

    entities = []

    # Pathogen patterns
    pathogen_patterns = [
        r'\b(E\.\s*coli|Escherichia coli)\b',
        r'\b(Salmonella|Shigella|Campylobacter|Legionella)\b',
        r'\b(Cryptosporidium|Giardia|Entamoeba)\b',
        r'\b(norovirus|rotavirus|hepatitis [A-E])\b',
        r'\b(coliform|enterococci|Pseudomonas)\b',
    ]

    for pattern in pathogen_patterns:
        matches = re.findall(pattern, text, re.IGNORECASE)
        for match in matches:
            entity_text = match if isinstance(match, str) else match[0]
            entities.append({
                "text": entity_text,
                "type": "pathogen",
                "vector_id": vector_id,
            })

    # Chemical patterns
    chemical_patterns = [
        r'\b(chlorine|chloramine|ozone|UV)\b',
        r'\b(arsenic|lead|mercury|cadmium)\b',
        r'\b(nitrate|nitrite|phosphate|fluoride)\b',
        r'\b(PFAS|PFOA|PFOS)\b',
    ]

    for pattern in chemical_patterns:
        matches = re.findall(pattern, text, re.IGNORECASE)
        for match in matches:
            entities.append({
                "text": match,
                "type": "chemical",
                "vector_id": vector_id,
            })

    # Measurement patterns
    measurement_pattern = r'(\d+(?:\.\d+)?)\s*(%|CFU/mL|mg/L|μg/L|ppm|ppb)'
    matches = re.findall(measurement_pattern, text)
    for value, unit in matches:
        entities.append({
            "text": f"{value} {unit}",
            "type": "measurement",
            "vector_id": vector_id,
            "metadata": {"value": float(value), "unit": unit}
        })

    return entities


# ============================================================================
# SOTA: CROSS-VECTOR QUERY CAPABILITIES
# Query knowledge across multiple vectors
# ============================================================================

async def cross_vector_query(
    query: str,
    entity_types: Optional[List[str]] = None,
    vector_ids: Optional[List[str]] = None,
    limit: int = 20,
) -> Dict[str, Any]:
    """
    SOTA: Query knowledge across multiple vectors.

    This enables finding related research across different vector IDs,
    useful for synthesis and cross-referencing.

    Args:
        query: Search query
        entity_types: Optional filter by entity types
        vector_ids: Optional filter by vector IDs (None = all vectors)
        limit: Maximum results

    Returns:
        Dict with matching entities and chunks
    """
    results = {
        "entities": [],
        "chunks": [],
        "vectors_searched": [],
        "query": query,
    }

    # Search entities
    entity_store = StructuredEntityStore()

    if entity_types:
        for etype in entity_types:
            matching = entity_store.search_entities(query, entity_type=etype)
            results["entities"].extend(matching[:limit])
    else:
        matching = entity_store.search_entities(query)
        results["entities"].extend(matching[:limit])

    # Filter by vector_ids if specified
    if vector_ids:
        results["entities"] = [e for e in results["entities"] if e["vector_id"] in vector_ids]

    # Search LTM chunks
    try:
        chroma = get_chroma_manager()
        ltm_collection_name = get_ltm_collection_name()

        try:
            ltm_collection = chroma.client.get_collection(name=ltm_collection_name)
            chunk_results = ltm_collection.query(
                query_texts=[query],
                n_results=limit,
                include=["documents", "metadatas", "distances"]
            )

            if chunk_results and chunk_results.get("ids"):
                for i, chunk_id in enumerate(chunk_results["ids"][0]):
                    chunk = {
                        "chunk_id": chunk_id,
                        "text": chunk_results["documents"][0][i] if chunk_results.get("documents") else "",
                        "metadata": chunk_results["metadatas"][0][i] if chunk_results.get("metadatas") else {},
                        "distance": chunk_results["distances"][0][i] if chunk_results.get("distances") else 0,
                    }

                    # Filter by vector_ids if specified
                    source_vector = chunk.get("metadata", {}).get("source_vector_id", "")
                    if vector_ids and source_vector not in vector_ids:
                        continue

                    results["chunks"].append(chunk)
                    if source_vector and source_vector not in results["vectors_searched"]:
                        results["vectors_searched"].append(source_vector)

        except Exception as e:
            # LOW-088: Use logger instead of print
            logger.warning(f"LTM query failed: {e}")

    except Exception as e:
        # LOW-089: Use logger instead of print
        logger.warning(f"Cross-vector query failed: {e}")

    return results


async def find_related_vectors(
    vector_id: str,
    limit: int = 10,
) -> List[Dict[str, Any]]:
    """
    SOTA: Find vectors with related content based on shared entities.

    Args:
        vector_id: Source vector ID
        limit: Maximum related vectors to return

    Returns:
        List of related vector IDs with overlap scores
    """
    entity_store = StructuredEntityStore()
    source_entities = entity_store.get_entities_by_vector(vector_id)

    if not source_entities:
        return []

    # Count entity overlap with other vectors
    vector_overlap = {}
    source_entity_texts = {e["text_normalized"] for e in source_entities}

    for entity in entity_store._entities["entities"]:
        other_vector = entity["vector_id"]
        if other_vector == vector_id:
            continue

        if entity["text_normalized"] in source_entity_texts:
            if other_vector not in vector_overlap:
                vector_overlap[other_vector] = {"count": 0, "entities": []}
            vector_overlap[other_vector]["count"] += 1
            vector_overlap[other_vector]["entities"].append(entity["text"])

    # Sort by overlap count
    related = sorted(
        [
            {"vector_id": vid, "overlap_count": data["count"], "shared_entities": list(set(data["entities"]))[:5]}
            for vid, data in vector_overlap.items()
        ],
        key=lambda x: x["overlap_count"],
        reverse=True
    )[:limit]

    return related


# ============================================================================
# LTM OPERATIONS
# ============================================================================

def get_ltm_collection_name() -> str:
    """Get the global LTM collection name."""
    return "ltm_global_knowledge"


async def promote_to_ltm(
    vector_id: str,
    verified_chunks: List[str],
    chunk_metadata: Dict[str, Dict[str, Any]]
) -> int:
    """
    Promote verified chunks to the global LTM collection.

    Args:
        vector_id: Source vector ID
        verified_chunks: List of verified chunk IDs
        chunk_metadata: Metadata for each chunk

    Returns:
        Number of chunks promoted
    """
    if not verified_chunks:
        return 0

    try:
        chroma = get_chroma_manager()
        source_collection_name = f"vwm_{vector_id}"
        ltm_collection_name = get_ltm_collection_name()

        # Get or create LTM collection
        try:
            ltm_collection = chroma.client.get_or_create_collection(
                name=ltm_collection_name,
                metadata={"description": "POLARIS Global Long-Term Memory"}
            )
        except Exception as e:
            # LOW-090: Use logger instead of print
            logger.warning(f"Could not create LTM collection: {e}")
            return 0

        # Get source collection
        try:
            source_collection = chroma.client.get_collection(name=source_collection_name)
        except Exception:
            # LOW-091: Use logger instead of print
            logger.warning(f"Source collection not found: {source_collection_name}")
            return 0

        # Retrieve verified chunks from source
        results = source_collection.get(
            ids=verified_chunks,
            include=["documents", "metadatas", "embeddings"]
        )

        if not results or not results.get("ids"):
            return 0

        # Add to LTM with source tracking
        promoted = 0
        for i, chunk_id in enumerate(results["ids"]):
            document = results["documents"][i] if results.get("documents") else ""
            metadata = results["metadatas"][i] if results.get("metadatas") else {}
            embedding = results["embeddings"][i] if results.get("embeddings") else None

            # Enhance metadata with source info
            ltm_metadata = {
                **metadata,
                "source_vector_id": vector_id,
                "promoted_at": datetime.now(timezone.utc).isoformat(),
                "ltm_id": f"ltm_{vector_id}_{chunk_id}",
            }

            # Generate unique LTM ID
            ltm_id = f"ltm_{vector_id}_{chunk_id}"

            try:
                if embedding:
                    ltm_collection.add(
                        ids=[ltm_id],
                        documents=[document],
                        metadatas=[ltm_metadata],
                        embeddings=[embedding]
                    )
                else:
                    ltm_collection.add(
                        ids=[ltm_id],
                        documents=[document],
                        metadatas=[ltm_metadata]
                    )
                promoted += 1
            except Exception as e:
                # May already exist - try upsert
                try:
                    ltm_collection.upsert(
                        ids=[ltm_id],
                        documents=[document],
                        metadatas=[ltm_metadata]
                    )
                    promoted += 1
                except Exception:
                    # LOW-092: Use logger instead of print
                    logger.warning(f"Failed to add chunk {chunk_id}: {e}")

        return promoted

    except Exception as e:
        # LOW-093: Use logger instead of print
        logger.warning(f"LTM promotion failed: {e}")
        return 0


# ============================================================================
# CLAIM EXTRACTION AND PERSISTENCE
# ============================================================================

def extract_claims_from_analysis(analysis_text: str) -> List[Dict[str, Any]]:
    """
    Extract individual claims from the analysis text.

    Args:
        analysis_text: P7 analysis text with citations

    Returns:
        List of claim dictionaries
    """
    import re

    claims = []
    # Split by sentences or claim markers
    sentences = re.split(r'(?<=[.!?])\s+', analysis_text)

    for i, sentence in enumerate(sentences):
        # Check if sentence has citations
        citations = re.findall(r'\[CITE:([^\]]+)\]', sentence)
        if citations:
            claim = {
                "claim_id": f"claim_{i+1:04d}",
                "text": sentence.strip(),
                "citations": citations,
                "citation_count": len(citations),
            }
            claims.append(claim)

    return claims


async def persist_claims_to_archive(
    vector_id: str,
    claims: List[Dict[str, Any]],
    archive_dir: Path
) -> str:
    """
    Persist verified claims to the archive.

    Args:
        vector_id: Vector ID
        claims: List of claims to persist
        archive_dir: Archive directory

    Returns:
        Path to the archive file
    """
    archive_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    archive_path = archive_dir / f"{vector_id}__claims__{timestamp}.json"

    archive_data = {
        "vector_id": vector_id,
        "archived_at": datetime.now(timezone.utc).isoformat(),
        "claim_count": len(claims),
        "claims": claims,
    }

    with open(archive_path, 'w', encoding='utf-8') as f:
        json.dump(archive_data, f, indent=2, ensure_ascii=False)

    return str(archive_path)


# ============================================================================
# CROSS-REFERENCE DETECTION
# ============================================================================

async def find_cross_references(
    vector_id: str,
    verified_chunks: List[str]
) -> List[str]:
    """
    Find cross-references to other vectors in LTM.

    Args:
        vector_id: Current vector ID
        verified_chunks: Verified chunks from current research

    Returns:
        List of related vector IDs
    """
    try:
        chroma = get_chroma_manager()
        ltm_collection_name = get_ltm_collection_name()

        try:
            ltm_collection = chroma.client.get_collection(name=ltm_collection_name)
        except Exception as e:
            # LOW-035: Log LTM collection fetch error
            logger.debug(f"LTM collection '{ltm_collection_name}' not found: {e}")
            return []

        # Get existing LTM entries
        existing = ltm_collection.get(include=["metadatas"])

        if not existing or not existing.get("metadatas"):
            return []

        # Find related vectors
        related_vectors = set()
        for metadata in existing["metadatas"]:
            if metadata:
                source_id = metadata.get("source_vector_id", "")
                if source_id and source_id != vector_id:
                    related_vectors.add(source_id)

        return list(related_vectors)

    except Exception as e:
        # LOW-036: Log related vectors fetch error
        logger.debug(f"Error fetching related vectors for {vector_id}: {e}")
        return []


# ============================================================================
# MAIN PHASE EXECUTION
# ============================================================================

async def run_phase_11(
    vector_id: str,
    p10_output: Optional[Phase10Output] = None,
    p7_output: Optional[Phase7Output] = None,
    p6_output: Optional[Phase6Output] = None,
) -> Phase11Output:
    """
    Execute Phase 11: Knowledge Integration

    Workflow:
    1. Check gating case from P9
    2. If CASE_1: Promote verified chunks to LTM
    3. Extract and persist claims to archive
    4. Find cross-references

    Args:
        vector_id: Vector ID for the research
        p10_output: Optional P9 output (will load from file if not provided)
        p7_output: Optional P7 output for claim extraction
        p6_output: Optional P6 output for verified IDs

    Returns:
        Phase11Output with integration results
    """
    config = get_config()
    start_time = datetime.now(timezone.utc)
    audit = get_audit()

    print(f"\n{'='*60}")
    print(f"PHASE 11: KNOWLEDGE INTEGRATION")
    print(f"Vector ID: {vector_id}")
    print(f"{'='*60}")

    # Load phase outputs if not provided
    if p10_output is None:
        p10_dir = OUTPUTS_DIR / "P10"
        p10_files = list(p10_dir.glob(f"{vector_id}__P10__*.json"))
        if not p10_files:
            raise FileNotFoundError(f"No P10 output found for {vector_id}")
        with open(sorted(p10_files)[-1], 'r', encoding='utf-8') as f:
            p10_output = Phase10Output(**json.load(f))
        print(f"  Loaded P10: {sorted(p10_files)[-1].name}")

    if p7_output is None:
        p7_dir = OUTPUTS_DIR / "P7"
        p7_files = list(p7_dir.glob(f"{vector_id}__P7__*.json"))
        if p7_files:
            with open(sorted(p7_files)[-1], 'r', encoding='utf-8') as f:
                p7_output = Phase7Output(**json.load(f))
            print(f"  Loaded P7: {sorted(p7_files)[-1].name}")

    if p6_output is None:
        p6_dir = OUTPUTS_DIR / "P6"
        p6_files = list(p6_dir.glob(f"{vector_id}__P6__*.json"))
        if p6_files:
            with open(sorted(p6_files)[-1], 'r', encoding='utf-8') as f:
                p6_output = Phase6Output(**json.load(f))
            print(f"  Loaded P6: {sorted(p6_files)[-1].name}")

    gating_case = p10_output.gating_case
    print(f"\n  Gating Case: {gating_case.value}")

    # Step 1: Determine if LTM update should proceed
    ltm_updated = False
    claims_persisted = 0
    cross_references = []

    if gating_case == GatingCase.CASE_1:
        print("\n  Step 1: CASE_1 detected - Proceeding with LTM promotion...")

        # Get verified chunks from P6
        verified_chunks = []
        if p6_output and hasattr(p6_output, 'verified_ids'):
            verified_chunks = p6_output.verified_ids
        elif p6_output:
            # Try to get from integrity check results
            verified_chunks = getattr(p6_output, 'verified_chunk_ids', [])

        print(f"    Verified chunks: {len(verified_chunks)}")

        if verified_chunks:
            # Promote to LTM
            promoted = await promote_to_ltm(
                vector_id=vector_id,
                verified_chunks=verified_chunks,
                chunk_metadata={}
            )
            ltm_updated = promoted > 0
            print(f"    Promoted to LTM: {promoted} chunks")
    else:
        print(f"\n  Step 1: {gating_case.value} - Skipping LTM promotion")
        print(f"    LTM updates only occur for CASE_1 (finalize)")

    # Step 2: Extract and persist claims
    print("\n  Step 2: Extracting and archiving claims...")
    claims = []
    if p7_output and p7_output.analysis_text:
        claims = extract_claims_from_analysis(p7_output.analysis_text)
        print(f"    Extracted {len(claims)} claims with citations")

    archive_dir = OUTPUTS_DIR / "archive" / vector_id
    archive_path = await persist_claims_to_archive(
        vector_id=vector_id,
        claims=claims,
        archive_dir=archive_dir
    )
    claims_persisted = len(claims)
    print(f"    Archived to: {archive_path}")

    # Step 3: Extract entities and find cross-references
    print("\n  Step 3: Entity extraction and cross-references...")

    # SOTA: Extract entities from the analysis text
    entities_extracted = []
    if p7_output and p7_output.analysis_text:
        entities_extracted = extract_entities_from_text(p7_output.analysis_text, vector_id)
        print(f"    Extracted {len(entities_extracted)} entities from analysis")

        # Store entities for future cross-vector queries
        if entities_extracted:
            entity_store = StructuredEntityStore()
            for entity in entities_extracted:
                entity_store.add_entity(
                    entity_text=entity.get("text", ""),
                    entity_type=entity.get("type", "unknown"),
                    vector_id=vector_id,
                    context=entity.get("context", "")[:200] if entity.get("context") else "",
                )
            print(f"    Stored {len(entities_extracted)} entities in entity store")

    # Find related vectors based on entity overlap
    related_by_entities = await find_related_vectors(vector_id, limit=5)
    print(f"    Related vectors (entity overlap): {len(related_by_entities)}")

    # Also check LTM for cross-references
    ltm_cross_refs = []
    if p6_output and hasattr(p6_output, 'verified_ids'):
        ltm_cross_refs = await find_cross_references(
            vector_id=vector_id,
            verified_chunks=p6_output.verified_ids if hasattr(p6_output, 'verified_ids') else []
        )
    print(f"    LTM cross-references: {len(ltm_cross_refs)}")

    # Combine cross-references
    cross_references = list(set(
        [r.get("vector_id", "") for r in related_by_entities if r.get("vector_id")] +
        ltm_cross_refs
    ))
    print(f"    Total cross-references: {len(cross_references)}")

    # Audit: Log gap analysis
    if audit:
        # Log LTM promotion as memory operation
        if ltm_promoted > 0:
            audit.log_memory_operation(
                operation_type="promote",
                memory_tier="ltm_global",
                chunk_id=f"batch_{ltm_promoted}",
                success=True,
            )

        # Log gap analysis complete
        coverage_score = 1.0 if gating_case == GatingCase.CASE_1 else 0.5
        audit.log_gap_analysis_complete(
            coverage_score=coverage_score,
            completeness_score=claims_persisted / max(len(claims), 1) if claims else 1.0,
        )

    end_time = datetime.now(timezone.utc)

    # Build output
    output = Phase11Output(
        vector_id=vector_id,
        ltm_global_updated=ltm_updated,
        claims_persisted=claims_persisted,
        cross_references=cross_references,
        archive_path=archive_path,
        gating_case=gating_case,
        timestamps={
            "start": start_time.isoformat(),
            "end": end_time.isoformat()
        }
    )

    # Save output
    output_dir = OUTPUTS_DIR / "P11"
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = output_dir / f"{vector_id}__P11__{timestamp}.json"

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output.model_dump(), f, indent=2, ensure_ascii=False)

    print(f"\n  Summary:")
    print(f"    Gating Case: {gating_case.value}")
    print(f"    LTM Updated: {ltm_updated}")
    print(f"    Claims Archived: {claims_persisted}")
    print(f"    Cross-References: {len(cross_references)}")
    print(f"\n  Output saved: {output_path.name}")

    # Update ledger
    ledger = Ledger()
    ledger.append(
        vector_id=vector_id,
        phase=11,
        status="completed",
        output_path=str(output_path),
        notes=f"case={gating_case.value}, ltm={ltm_updated}, claims={claims_persisted}"
    )

    return output


# ============================================================================
# SELF-TEST
# ============================================================================

def self_test():
    """Run self-tests for Phase 11 components."""
    print("\nRunning Phase 11 self-tests...")

    # Test 1: Claim extraction
    test_text = """
    Water filters can reduce contaminants [CITE:chunk_001].
    However, they require maintenance [CITE:chunk_002].
    Studies show effectiveness varies [CITE:chunk_003] [CITE:chunk_004].
    This sentence has no citation.
    """

    claims = extract_claims_from_analysis(test_text)
    assert len(claims) == 3, f"Expected 3 claims with citations, got {len(claims)}"
    assert claims[0]["citation_count"] >= 1
    print("  [PASS] Claim extraction")

    # Test 2: Citation counting in claims
    total_citations = sum(c["citation_count"] for c in claims)
    assert total_citations == 4, f"Expected 4 total citations, got {total_citations}"
    print("  [PASS] Citation counting")

    # Test 3: LTM collection naming
    ltm_name = get_ltm_collection_name()
    assert ltm_name == "ltm_global_knowledge"
    print("  [PASS] LTM collection naming")

    print("\nAll Phase 11 self-tests PASSED!")
    return True


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Phase 11: Knowledge Integration")
    parser.add_argument("--vector-id", required=False, help="Vector ID to process")
    parser.add_argument("--input", required=False, help="Path to P9 output JSON (optional)")
    parser.add_argument("--output", required=False, help="Output directory (optional)")
    parser.add_argument("--self-test", action="store_true", help="Run self-tests")

    args = parser.parse_args()

    if args.self_test:
        self_test()
    elif args.vector_id:
        # Load P9 output if input specified
        p10_output = None
        if args.input:
            with open(args.input, 'r', encoding='utf-8') as f:
                p10_output = Phase10Output(**json.load(f))

        result = asyncio.run(run_phase_11(vector_id=args.vector_id, p10_output=p10_output))

        # Optionally save to custom output dir
        if args.output:
            out_dir = Path(args.output)
            out_dir.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            out_path = out_dir / f"{args.vector_id}__P11__{timestamp}.json"
            with open(out_path, 'w', encoding='utf-8') as f:
                json.dump(result.model_dump(), f, indent=2, ensure_ascii=False)
            print(f"  Output saved to: {out_path}")

        print(f"\nPhase 11 complete. LTM Updated: {result.ltm_global_updated}")
    else:
        print("Usage: python p10_knowledge_integration.py --vector-id <ID> [--input P9.json] or --self-test")
