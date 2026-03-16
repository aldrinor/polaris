"""
Session-scoped RAG over locally uploaded documents using ChromaDB.

Each research session gets an isolated ChromaDB collection (``docs_{session_id}``)
that holds chunked and embedded document content.  All embedding is performed
locally via the POLARIS singleton EmbeddingService (sentence-transformers
all-MiniLM-L6-v2, 384 dims) -- no external API calls.

Persistence directory: PG_DOC_RAG_DIR env var (default: state/doc_rag).

Usage:
    rag = LocalDocumentRAG("session_abc123")
    chunk_count = await rag.ingest_document(doc_id, content, metadata)
    results = await rag.query("What contaminants are regulated?", k=10)
    await rag.cleanup()
"""

import asyncio
import hashlib
import logging
import os
import re
import time
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration (LAW VI: all from env vars)
# ---------------------------------------------------------------------------

DOC_RAG_DIR = Path(os.getenv("PG_DOC_RAG_DIR", "state/doc_rag"))
CHUNK_SIZE_TOKENS = int(os.getenv("PG_DOC_RAG_CHUNK_SIZE", "512"))
CHUNK_OVERLAP_TOKENS = int(os.getenv("PG_DOC_RAG_CHUNK_OVERLAP", "50"))
COLLECTION_PREFIX = "docs_"

# Approximate characters per token for whitespace-split tokenisation.
# sentence-transformers uses a WordPiece tokenizer; 1 token ~ 4 chars is a
# reasonable approximation for English prose.
CHARS_PER_TOKEN = int(os.getenv("PG_DOC_RAG_CHARS_PER_TOKEN", "4"))

# Maximum batch size for ChromaDB upsert to avoid memory pressure.
UPSERT_BATCH_SIZE = int(os.getenv("PG_DOC_RAG_UPSERT_BATCH", "256"))


class LocalDocumentRAG:
    """Session-scoped retrieval-augmented generation over uploaded documents.

    Creates an isolated ChromaDB collection per session so that document
    embeddings do not leak across sessions.
    """

    def __init__(self, session_id: str) -> None:
        if not session_id or not session_id.strip():
            raise ValueError("session_id must be a non-empty string.")

        self._session_id = session_id
        self._collection_name = f"{COLLECTION_PREFIX}{session_id}"
        self._client = None
        self._collection = None
        self._embedding_fn = None

        logger.info(
            "[local_document_rag] Initialised for session=%s (collection=%s)",
            session_id,
            self._collection_name,
        )

    # ------------------------------------------------------------------
    # Lazy initialisation (avoid import-time side effects)
    # ------------------------------------------------------------------

    def _ensure_client(self) -> None:
        """Create the PersistentClient and collection on first access."""
        if self._client is not None:
            return

        try:
            import chromadb
            from chromadb.config import Settings
        except ImportError as exc:
            raise RuntimeError(
                "chromadb is required for LocalDocumentRAG. "
                "Install with: pip install chromadb"
            ) from exc

        persist_path = DOC_RAG_DIR.resolve()
        persist_path.mkdir(parents=True, exist_ok=True)

        self._client = chromadb.PersistentClient(
            path=str(persist_path),
            settings=Settings(
                anonymized_telemetry=False,
                allow_reset=False,
            ),
        )

        # Use the POLARIS singleton embedding function so that embeddings
        # are consistent with the rest of the pipeline (all-MiniLM-L6-v2).
        try:
            from src.utils.embedding_service import get_chromadb_embedding_function
            self._embedding_fn = get_chromadb_embedding_function()
        except Exception as exc:
            logger.warning(
                "[local_document_rag] Failed to load POLARIS embedding function, "
                "falling back to ChromaDB default: %s",
                str(exc)[:200],
            )
            self._embedding_fn = None

        kwargs = {"name": self._collection_name}
        if self._embedding_fn is not None:
            kwargs["embedding_function"] = self._embedding_fn

        self._collection = self._client.get_or_create_collection(**kwargs)

        logger.info(
            "[local_document_rag] ChromaDB client ready at %s "
            "(collection=%s, count=%d)",
            persist_path,
            self._collection_name,
            self._collection.count(),
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def ingest_document(
        self,
        doc_id: str,
        content: str,
        metadata: Optional[dict] = None,
    ) -> int:
        """Chunk *content*, embed, and upsert into the session collection.

        Args:
            doc_id:   Unique identifier for the document.
            content:  Full extracted plain-text of the document.
            metadata: Optional document-level metadata to attach to every
                      chunk (e.g. filename, author, pages).

        Returns:
            Number of chunks upserted.

        Raises:
            ValueError: If doc_id or content is empty.
        """
        if not doc_id or not doc_id.strip():
            raise ValueError("doc_id must be a non-empty string.")
        if not content or not content.strip():
            raise ValueError(
                f"content is empty for doc_id={doc_id}. "
                "Cannot ingest an empty document."
            )

        self._ensure_client()
        start_ts = time.monotonic()

        chunks = _chunk_text(
            content,
            chunk_size_tokens=CHUNK_SIZE_TOKENS,
            overlap_tokens=CHUNK_OVERLAP_TOKENS,
        )

        if not chunks:
            logger.warning(
                "[local_document_rag] Chunking produced 0 chunks for "
                "doc_id=%s (%d chars).",
                doc_id, len(content),
            )
            return 0

        # Build ids, documents, metadatas for ChromaDB upsert
        ids: list[str] = []
        documents: list[str] = []
        metadatas: list[dict] = []
        base_meta = metadata or {}

        for idx, chunk in enumerate(chunks):
            chunk_id = _make_chunk_id(doc_id, idx)
            chunk_meta = {
                "doc_id": doc_id,
                "chunk_index": idx,
                "chunk_count": len(chunks),
                "char_start": chunk["char_start"],
                "char_end": chunk["char_end"],
            }
            # Merge document-level metadata (only scalar values for ChromaDB)
            for key, val in base_meta.items():
                if isinstance(val, (str, int, float, bool)):
                    chunk_meta[key] = val

            ids.append(chunk_id)
            documents.append(chunk["text"])
            metadatas.append(chunk_meta)

        # Upsert in batches to avoid memory pressure
        total_upserted = 0
        for batch_start in range(0, len(ids), UPSERT_BATCH_SIZE):
            batch_end = batch_start + UPSERT_BATCH_SIZE
            self._collection.upsert(
                ids=ids[batch_start:batch_end],
                documents=documents[batch_start:batch_end],
                metadatas=metadatas[batch_start:batch_end],
            )
            total_upserted += len(ids[batch_start:batch_end])

            # Yield to the event loop between batches
            if batch_end < len(ids):
                await asyncio.sleep(0)

        elapsed = time.monotonic() - start_ts
        logger.info(
            "[local_document_rag] Ingested doc_id=%s -> %d chunks in %.2fs "
            "(collection=%s, total=%d)",
            doc_id,
            total_upserted,
            elapsed,
            self._collection_name,
            self._collection.count(),
        )
        return total_upserted

    async def query(
        self,
        query: str,
        k: int = 10,
        where_filter: Optional[dict] = None,
    ) -> list[dict]:
        """Retrieve the top-*k* most relevant chunks for *query*.

        Args:
            query:        Natural language query string.
            k:            Number of results to return (default 10).
            where_filter: Optional ChromaDB where clause to filter by
                          metadata (e.g. ``{"doc_id": "abc123"}``).

        Returns:
            List of dicts, each containing:
                chunk_id  (str):   The unique chunk identifier.
                text      (str):   The chunk content.
                metadata  (dict):  Attached metadata.
                distance  (float): Embedding distance (lower = more similar).
        """
        if not query or not query.strip():
            logger.warning("[local_document_rag] Empty query, returning [].")
            return []

        self._ensure_client()

        collection_count = self._collection.count()
        if collection_count == 0:
            logger.info(
                "[local_document_rag] Collection %s is empty, returning [].",
                self._collection_name,
            )
            return []

        effective_k = min(k, collection_count)

        query_kwargs = {
            "query_texts": [query],
            "n_results": effective_k,
        }
        if where_filter:
            query_kwargs["where"] = where_filter

        try:
            results = self._collection.query(**query_kwargs)
        except Exception as exc:
            logger.error(
                "[local_document_rag] Query failed on collection=%s: %s",
                self._collection_name,
                str(exc)[:300],
            )
            raise

        # Unpack ChromaDB results into a flat list
        output: list[dict] = []
        if not results or not results.get("ids"):
            return output

        result_ids = results["ids"][0]
        result_docs = results["documents"][0] if results.get("documents") else []
        result_metas = results["metadatas"][0] if results.get("metadatas") else []
        result_dists = results["distances"][0] if results.get("distances") else []

        for i, chunk_id in enumerate(result_ids):
            output.append({
                "chunk_id": chunk_id,
                "text": result_docs[i] if i < len(result_docs) else "",
                "metadata": result_metas[i] if i < len(result_metas) else {},
                "distance": result_dists[i] if i < len(result_dists) else 0.0,
            })

        logger.debug(
            "[local_document_rag] Query returned %d results from %s "
            "(k=%d, collection_count=%d).",
            len(output),
            self._collection_name,
            effective_k,
            collection_count,
        )
        return output

    async def cleanup(self) -> None:
        """Delete the session-specific collection and release resources."""
        if self._client is None:
            logger.debug(
                "[local_document_rag] cleanup() called but client was "
                "never initialised for session=%s.",
                self._session_id,
            )
            return

        try:
            self._client.delete_collection(name=self._collection_name)
            logger.info(
                "[local_document_rag] Deleted collection %s for session=%s.",
                self._collection_name,
                self._session_id,
            )
        except Exception as exc:
            logger.warning(
                "[local_document_rag] Failed to delete collection %s: %s",
                self._collection_name,
                str(exc)[:200],
            )

        self._collection = None
        self._client = None

    # ------------------------------------------------------------------
    # Convenience properties
    # ------------------------------------------------------------------

    @property
    def session_id(self) -> str:
        """Return the session identifier."""
        return self._session_id

    @property
    def collection_name(self) -> str:
        """Return the underlying ChromaDB collection name."""
        return self._collection_name

    @property
    def chunk_count(self) -> int:
        """Return the total number of chunks in the collection."""
        if self._collection is None:
            return 0
        return self._collection.count()

    def get_document_ids(self) -> list[str]:
        """Return distinct doc_ids stored in this session collection."""
        if self._collection is None:
            return []

        try:
            all_meta = self._collection.get(include=["metadatas"])
            metadatas = all_meta.get("metadatas") or []
            doc_ids = sorted({
                m.get("doc_id", "")
                for m in metadatas
                if m.get("doc_id")
            })
            return doc_ids
        except Exception as exc:
            logger.warning(
                "[local_document_rag] Failed to list doc_ids: %s",
                str(exc)[:200],
            )
            return []


# ---------------------------------------------------------------------------
# Chunking utilities
# ---------------------------------------------------------------------------

def _chunk_text(
    text: str,
    chunk_size_tokens: int = CHUNK_SIZE_TOKENS,
    overlap_tokens: int = CHUNK_OVERLAP_TOKENS,
) -> list[dict]:
    """Split *text* into overlapping chunks of approximately *chunk_size_tokens*.

    Each chunk dict contains:
        text       (str): The chunk content.
        char_start (int): Start character offset in the original text.
        char_end   (int): End character offset in the original text.

    The chunker splits on paragraph boundaries first, then on sentence
    boundaries, to preserve semantic coherence.  Token counts are
    approximated using ``CHARS_PER_TOKEN``.
    """
    if not text or not text.strip():
        return []

    chunk_size_chars = chunk_size_tokens * CHARS_PER_TOKEN
    overlap_chars = overlap_tokens * CHARS_PER_TOKEN

    # Split into paragraphs (double newline or more)
    paragraphs = re.split(r"\n{2,}", text)

    chunks: list[dict] = []
    current_text = ""
    current_start = 0
    cursor = 0  # tracks character position in original text

    for para in paragraphs:
        para = para.strip()
        if not para:
            # Account for the split characters
            cursor += 2  # approximate for \n\n
            continue

        # Find actual position of this paragraph in original text
        para_start = text.find(para, cursor)
        if para_start == -1:
            para_start = cursor
        para_end = para_start + len(para)

        # Would adding this paragraph exceed the chunk size?
        tentative = (current_text + "\n\n" + para).strip() if current_text else para
        if len(tentative) > chunk_size_chars and current_text:
            # Flush current chunk
            chunks.append({
                "text": current_text,
                "char_start": current_start,
                "char_end": current_start + len(current_text),
            })

            # Start new chunk with overlap
            if overlap_chars > 0 and len(current_text) > overlap_chars:
                overlap_text = current_text[-overlap_chars:]
                # Start from a sentence boundary within the overlap if possible
                sent_break = _find_sentence_break(overlap_text)
                if sent_break > 0:
                    overlap_text = overlap_text[sent_break:].strip()
                current_text = overlap_text + "\n\n" + para
                current_start = para_start - len(overlap_text)
            else:
                current_text = para
                current_start = para_start
        else:
            if not current_text:
                current_start = para_start
            current_text = tentative

        cursor = para_end

    # Flush remaining
    if current_text.strip():
        chunks.append({
            "text": current_text.strip(),
            "char_start": current_start,
            "char_end": current_start + len(current_text.strip()),
        })

    # Handle oversized chunks by splitting on sentence boundaries
    final_chunks: list[dict] = []
    for chunk in chunks:
        if len(chunk["text"]) <= chunk_size_chars * 1.5:
            final_chunks.append(chunk)
        else:
            sub_chunks = _split_oversized_chunk(
                chunk["text"],
                chunk["char_start"],
                chunk_size_chars,
                overlap_chars,
            )
            final_chunks.extend(sub_chunks)

    return final_chunks


def _split_oversized_chunk(
    text: str,
    base_offset: int,
    chunk_size_chars: int,
    overlap_chars: int,
) -> list[dict]:
    """Split an oversized chunk on sentence boundaries."""
    sentences = _split_sentences(text)
    chunks: list[dict] = []
    current_text = ""
    current_start = base_offset
    cursor = 0

    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue

        tentative = (current_text + " " + sentence).strip() if current_text else sentence
        if len(tentative) > chunk_size_chars and current_text:
            chunks.append({
                "text": current_text,
                "char_start": current_start,
                "char_end": current_start + len(current_text),
            })

            if overlap_chars > 0 and len(current_text) > overlap_chars:
                overlap_text = current_text[-overlap_chars:]
                current_text = overlap_text + " " + sentence
            else:
                current_text = sentence
            current_start = base_offset + cursor
        else:
            if not current_text:
                current_start = base_offset + cursor
            current_text = tentative

        cursor += len(sentence) + 1  # +1 for space/newline

    if current_text.strip():
        chunks.append({
            "text": current_text.strip(),
            "char_start": current_start,
            "char_end": current_start + len(current_text.strip()),
        })

    return chunks


def _split_sentences(text: str) -> list[str]:
    """Split text into sentences using pysbd or regex fallback."""
    try:
        import pysbd
        segmenter = pysbd.Segmenter(language="en", clean=False)
        return segmenter.segment(text)
    except ImportError:
        pass

    # Regex fallback: split after sentence-ending punctuation followed by
    # a space and an uppercase letter.
    return re.split(r"(?<=[.!?])\s+(?=[A-Z])", text)


def _find_sentence_break(text: str) -> int:
    """Find the first sentence break position in *text*.

    Returns the index right after the sentence-ending punctuation,
    or 0 if no break is found.
    """
    match = re.search(r"[.!?]\s+", text)
    if match:
        return match.end()
    return 0


def _make_chunk_id(doc_id: str, chunk_index: int) -> str:
    """Deterministic chunk identifier: ``{doc_id}_c{chunk_index:04d}``."""
    return f"{doc_id}_c{chunk_index:04d}"
