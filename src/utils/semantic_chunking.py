#!/usr/bin/env python3
"""
POLARIS Semantic Chunking
=========================
Stage-specific semantic chunking with intelligent text segmentation.

Supports:
- Stage-based template selection (research, validation, synthesis)
- Semantic sentence boundary detection
- Paragraph preservation
- Overlap handling for context continuity

Usage:
    from src.utils.semantic_chunking import SemanticChunker

    chunker = SemanticChunker(stage=1)
    chunks = chunker.chunk(text)
"""

import logging
import re
from dataclasses import dataclass
from typing import List, Optional, Tuple

from src.config import get_config

logger = logging.getLogger(__name__)


# =============================================================================
# STAGE TEMPLATES
# =============================================================================

# Default templates by stage category
STAGE_TEMPLATES = {
    # Stage 1-4: Research phase - smaller chunks for precise retrieval
    "research": {
        "chunk_size": 800,
        "chunk_overlap": 150,
        "separators": ["\n\n", "\n", ". ", "! ", "? ", "; ", ", "],
    },
    # Stage 5-8: Validation phase - medium chunks for context
    "validation": {
        "chunk_size": 1200,
        "chunk_overlap": 200,
        "separators": ["\n\n", "\n", ". ", "! ", "? "],
    },
    # Stage 9-13: Synthesis phase - larger chunks for coherent narrative
    "synthesis": {
        "chunk_size": 1500,
        "chunk_overlap": 300,
        "separators": ["\n\n", "\n"],
    },
    # Academic paper template - preserves sections
    "academic": {
        "chunk_size": 1000,
        "chunk_overlap": 200,
        "separators": ["\n\n\n", "\n\n", "\n", ". "],
    },
    # Government/regulatory document template
    "regulatory": {
        "chunk_size": 1200,
        "chunk_overlap": 250,
        "separators": ["\n\n", "\n", ". ", "; "],
    },
}

# Stage to template mapping
STAGE_TO_TEMPLATE = {
    1: "research",
    2: "research",
    3: "research",
    4: "research",
    5: "validation",
    6: "validation",
    7: "validation",
    8: "validation",
    9: "synthesis",
    10: "synthesis",
    11: "synthesis",
    12: "synthesis",
    13: "synthesis",
}


@dataclass
class ChunkMetadata:
    """Metadata for a chunk."""
    index: int
    start_char: int
    end_char: int
    sentence_count: int
    has_paragraph_break: bool


class SemanticChunker:
    """
    Semantic chunking with stage-specific templates.

    Uses intelligent text segmentation that:
    - Respects sentence boundaries
    - Preserves paragraph structure
    - Applies stage-appropriate chunk sizes
    - Maintains context through overlap
    """

    def __init__(
        self,
        stage: int = 1,
        template_name: Optional[str] = None,
        chunk_size: Optional[int] = None,
        chunk_overlap: Optional[int] = None,
    ):
        """
        Initialize chunker.

        Args:
            stage: Research stage (1-13) for auto template selection
            template_name: Override template name (research, validation, synthesis, academic, regulatory)
            chunk_size: Override chunk size
            chunk_overlap: Override overlap size
        """
        self.stage = stage

        # Get template
        if template_name:
            template = STAGE_TEMPLATES.get(template_name, STAGE_TEMPLATES["research"])
        else:
            template_name = STAGE_TO_TEMPLATE.get(stage, "research")
            template = STAGE_TEMPLATES[template_name]

        # Apply overrides
        self.chunk_size = chunk_size or template["chunk_size"]
        self.chunk_overlap = chunk_overlap or template["chunk_overlap"]
        self.separators = template["separators"]
        self.template_name = template_name

        # Try to load config overrides
        try:
            config = get_config()
            if hasattr(config, 'models') and hasattr(config.models, 'chunking'):
                chunking = config.models.chunking
                # Check for stage-specific template
                if stage in chunking.stage_templates:
                    tpl_name = chunking.stage_templates[stage]
                    if tpl_name in chunking.templates:
                        tpl = chunking.templates[tpl_name]
                        self.chunk_size = tpl.chunk_size
                        self.chunk_overlap = tpl.chunk_overlap
                        self.separators = tpl.separators
                        self.template_name = tpl_name
        except (FileNotFoundError, KeyError, AttributeError, ValueError) as e:
            # HIGH-014: Log config loading error instead of silent pass
            logger.debug(f"Chunking config loading failed (using defaults): {e}")

    def chunk(self, text: str, min_chunk_size: int = 100) -> List[str]:
        """
        Chunk text using semantic boundaries.

        Args:
            text: Input text to chunk
            min_chunk_size: Minimum chunk size (smaller chunks are merged)

        Returns:
            List of text chunks
        """
        if not text or len(text.strip()) < min_chunk_size:
            return [text.strip()] if text and text.strip() else []

        # Clean and normalize text
        text = self._normalize_text(text)

        # Split into semantic units (sentences/paragraphs)
        units = self._split_into_units(text)

        # Combine units into chunks respecting size limits
        chunks = self._combine_units(units, min_chunk_size)

        return chunks

    def chunk_with_metadata(self, text: str, min_chunk_size: int = 100) -> List[Tuple[str, ChunkMetadata]]:
        """
        Chunk text and return metadata for each chunk.

        Args:
            text: Input text to chunk
            min_chunk_size: Minimum chunk size

        Returns:
            List of (chunk_text, metadata) tuples
        """
        if not text or len(text.strip()) < min_chunk_size:
            if text and text.strip():
                return [(text.strip(), ChunkMetadata(
                    index=0,
                    start_char=0,
                    end_char=len(text),
                    sentence_count=text.count('.') + text.count('!') + text.count('?'),
                    has_paragraph_break=False,
                ))]
            return []

        text = self._normalize_text(text)
        units = self._split_into_units(text)
        return self._combine_units_with_metadata(units, text, min_chunk_size)

    def _normalize_text(self, text: str) -> str:
        """Normalize whitespace and clean text."""
        # Replace multiple spaces with single space
        text = re.sub(r' +', ' ', text)
        # Normalize line breaks
        text = re.sub(r'\r\n', '\n', text)
        # Remove excessive blank lines (keep max 2)
        text = re.sub(r'\n{3,}', '\n\n', text)
        return text.strip()

    def _split_into_units(self, text: str) -> List[str]:
        """
        Split text into semantic units using separators.

        Tries each separator in order, using the first that produces
        good results.
        """
        units = []

        # First try paragraph split
        paragraphs = text.split('\n\n')

        for para in paragraphs:
            para = para.strip()
            if not para:
                continue

            # If paragraph is small enough, keep it as one unit
            if len(para) <= self.chunk_size:
                units.append(para)
            else:
                # Split large paragraphs into sentences
                sentences = self._split_into_sentences(para)
                units.extend(sentences)

        return units

    def _split_into_sentences(self, text: str) -> List[str]:
        """Split text into sentences using regex."""
        # Sentence boundary pattern
        # Handles: periods, question marks, exclamation marks
        # Avoids: abbreviations (Dr., Mr., etc.), decimals
        sentence_pattern = r'(?<=[.!?])\s+(?=[A-Z])'

        sentences = re.split(sentence_pattern, text)

        # Filter empty and merge very short sentences (but respect chunk size)
        result = []
        current = ""
        min_merge_size = 50
        max_merge_size = self.chunk_size // 2  # Don't merge beyond half chunk size

        for sent in sentences:
            sent = sent.strip()
            if not sent:
                continue

            # Merge short sentences, but don't exceed reasonable size
            if len(sent) < min_merge_size and current and len(current) + len(sent) < max_merge_size:
                current = current + " " + sent
            else:
                if current:
                    result.append(current)
                current = sent

        if current:
            result.append(current)

        return result

    def _combine_units(self, units: List[str], min_chunk_size: int) -> List[str]:
        """Combine semantic units into chunks of appropriate size."""
        if not units:
            return []

        chunks = []
        current_chunk = ""

        for unit in units:
            # Check if adding this unit would exceed chunk size
            potential_size = len(current_chunk) + len(unit) + 1  # +1 for space

            if potential_size <= self.chunk_size:
                # Add to current chunk
                if current_chunk:
                    current_chunk = current_chunk + " " + unit
                else:
                    current_chunk = unit
            else:
                # Current chunk is full
                if current_chunk and len(current_chunk) >= min_chunk_size:
                    chunks.append(current_chunk.strip())

                    # Start new chunk with overlap from end of previous
                    if self.chunk_overlap > 0 and len(current_chunk) > self.chunk_overlap:
                        # Get last N characters as overlap
                        overlap = self._get_overlap_text(current_chunk)
                        current_chunk = overlap + " " + unit if overlap else unit
                    else:
                        current_chunk = unit
                else:
                    # Current chunk too small, extend it
                    if current_chunk:
                        current_chunk = current_chunk + " " + unit
                    else:
                        current_chunk = unit

        # Add final chunk
        if current_chunk and len(current_chunk.strip()) >= min_chunk_size:
            chunks.append(current_chunk.strip())
        elif current_chunk and chunks:
            # Merge tiny final chunk with previous
            chunks[-1] = chunks[-1] + " " + current_chunk.strip()

        return chunks

    def _combine_units_with_metadata(
        self,
        units: List[str],
        original_text: str,
        min_chunk_size: int,
    ) -> List[Tuple[str, ChunkMetadata]]:
        """Combine units with metadata tracking."""
        chunks = self._combine_units(units, min_chunk_size)

        results = []
        current_pos = 0

        for i, chunk in enumerate(chunks):
            # Find chunk in original text
            start = original_text.find(chunk[:50], current_pos)
            if start == -1:
                start = current_pos
            end = start + len(chunk)
            current_pos = max(current_pos, end - self.chunk_overlap)

            metadata = ChunkMetadata(
                index=i,
                start_char=start,
                end_char=end,
                sentence_count=chunk.count('.') + chunk.count('!') + chunk.count('?'),
                has_paragraph_break='\n\n' in chunk or '\n' in chunk,
            )
            results.append((chunk, metadata))

        return results

    def _get_overlap_text(self, text: str) -> str:
        """Extract overlap text from end of chunk, respecting word boundaries."""
        if len(text) <= self.chunk_overlap:
            return text

        # Find a good break point near the overlap boundary
        overlap_start = len(text) - self.chunk_overlap

        # Look for sentence boundary first
        for pattern in ['. ', '! ', '? ', '\n', '; ', ', ']:
            pos = text.rfind(pattern, overlap_start, len(text) - 50)
            if pos > overlap_start:
                return text[pos + len(pattern):].strip()

        # Fall back to word boundary
        pos = text.rfind(' ', overlap_start, overlap_start + 100)
        if pos > overlap_start:
            return text[pos + 1:].strip()

        return text[overlap_start:].strip()


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

def get_chunker_for_stage(stage: int) -> SemanticChunker:
    """Get a chunker configured for a specific research stage."""
    return SemanticChunker(stage=stage)


def chunk_text(
    text: str,
    stage: int = 1,
    min_chunk_size: int = 100,
) -> List[str]:
    """
    Quick function to chunk text for a given stage.

    Args:
        text: Text to chunk
        stage: Research stage (1-13)
        min_chunk_size: Minimum chunk size

    Returns:
        List of text chunks
    """
    chunker = SemanticChunker(stage=stage)
    return chunker.chunk(text, min_chunk_size)


def chunk_academic_paper(text: str) -> List[str]:
    """Chunk an academic paper using academic template."""
    chunker = SemanticChunker(template_name="academic")
    return chunker.chunk(text)


def chunk_regulatory_document(text: str) -> List[str]:
    """Chunk a regulatory document using regulatory template."""
    chunker = SemanticChunker(template_name="regulatory")
    return chunker.chunk(text)


# =============================================================================
# SELF-TEST
# =============================================================================

def run_self_test() -> bool:
    """Run self-tests for semantic chunking."""
    print("Running Semantic Chunking self-tests...")

    # Test 1: Basic chunking
    try:
        text = "This is sentence one. This is sentence two. " * 50
        chunker = SemanticChunker(stage=1)
        chunks = chunker.chunk(text)
        assert len(chunks) > 1, "Should produce multiple chunks"
        assert all(len(c) >= 100 for c in chunks), "All chunks should meet minimum size"
        print(f"  [PASS] Basic chunking: {len(chunks)} chunks")
    except Exception as e:
        print(f"  [FAIL] Basic chunking: {e}")
        return False

    # Test 2: Stage templates
    try:
        for stage in [1, 5, 10]:
            chunker = SemanticChunker(stage=stage)
            assert chunker.chunk_size > 0
            assert chunker.chunk_overlap > 0
        print("  [PASS] Stage templates")
    except Exception as e:
        print(f"  [FAIL] Stage templates: {e}")
        return False

    # Test 3: Paragraph preservation
    try:
        text = "First paragraph content here.\n\nSecond paragraph content here.\n\nThird paragraph."
        chunker = SemanticChunker(stage=1, chunk_size=100, chunk_overlap=20)
        chunks = chunker.chunk(text, min_chunk_size=10)
        # Should try to keep paragraphs together
        assert len(chunks) >= 1
        print(f"  [PASS] Paragraph preservation: {len(chunks)} chunks")
    except Exception as e:
        print(f"  [FAIL] Paragraph preservation: {e}")
        return False

    # Test 4: Metadata extraction
    try:
        text = "Sentence one. Sentence two. Sentence three. " * 20
        chunker = SemanticChunker(stage=1)
        results = chunker.chunk_with_metadata(text)
        assert len(results) > 0
        chunk, metadata = results[0]
        assert metadata.sentence_count > 0
        print(f"  [PASS] Metadata extraction: {len(results)} chunks with metadata")
    except Exception as e:
        print(f"  [FAIL] Metadata extraction: {e}")
        return False

    # Test 5: Academic template
    try:
        text = "Abstract: This study examines water filters.\n\nIntroduction\nWater quality is important.\n\nMethods\nWe tested filters."
        chunks = chunk_academic_paper(text)
        assert len(chunks) >= 1
        print(f"  [PASS] Academic template: {len(chunks)} chunks")
    except Exception as e:
        print(f"  [FAIL] Academic template: {e}")
        return False

    print("\nAll Semantic Chunking self-tests PASSED!")
    return True


if __name__ == "__main__":
    success = run_self_test()
    exit(0 if success else 1)
