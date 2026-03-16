"""
POLARIS v3 PDF Parser Tool

PDF document parsing and extraction:
- Text extraction from PDFs
- Table extraction
- Image extraction and analysis
- Metadata extraction
- Structured content parsing

Uses PyMuPDF (fitz) for parsing, Gemini for intelligent extraction.
"""

import logging
import io
import base64
import os
from typing import List, Dict, Any, Optional, Tuple
from pathlib import Path
from dataclasses import dataclass, field

from pydantic import BaseModel, Field
from langchain_core.tools import tool


logger = logging.getLogger(__name__)


# =============================================================================
# Output Schemas
# =============================================================================

class PDFMetadata(BaseModel):
    """PDF document metadata."""
    title: Optional[str] = Field(default=None)
    author: Optional[str] = Field(default=None)
    subject: Optional[str] = Field(default=None)
    creator: Optional[str] = Field(default=None)
    producer: Optional[str] = Field(default=None)
    creation_date: Optional[str] = Field(default=None)
    modification_date: Optional[str] = Field(default=None)
    page_count: int = Field(default=0)
    file_size_bytes: int = Field(default=0)


class PDFTable(BaseModel):
    """Extracted table from PDF."""
    page_number: int = Field(description="Page where table was found")
    table_index: int = Field(description="Index of table on page")
    headers: List[str] = Field(default_factory=list)
    rows: List[List[str]] = Field(default_factory=list)
    bbox: Optional[Tuple[float, float, float, float]] = Field(
        default=None, description="Bounding box (x0, y0, x1, y1)"
    )


class PDFImage(BaseModel):
    """Extracted image from PDF."""
    page_number: int = Field(description="Page where image was found")
    image_index: int = Field(description="Index of image on page")
    width: int = Field(description="Image width in pixels")
    height: int = Field(description="Image height in pixels")
    format: str = Field(description="Image format (png, jpeg, etc.)")
    base64_data: Optional[str] = Field(default=None, description="Base64 encoded image")
    analysis: Optional[Dict[str, Any]] = Field(default=None, description="Vision analysis")


class PDFPage(BaseModel):
    """Extracted content from a PDF page."""
    page_number: int = Field(description="Page number (1-indexed)")
    text: str = Field(description="Extracted text")
    tables: List[PDFTable] = Field(default_factory=list)
    images: List[PDFImage] = Field(default_factory=list)
    links: List[str] = Field(default_factory=list)


class PDFDocument(BaseModel):
    """Complete extracted PDF document."""
    file_path: str = Field(description="Source file path")
    metadata: PDFMetadata = Field(default_factory=PDFMetadata)
    pages: List[PDFPage] = Field(default_factory=list)
    full_text: str = Field(default="", description="Full document text")
    table_count: int = Field(default=0)
    image_count: int = Field(default=0)


# =============================================================================
# PDF Parser
# =============================================================================

class PDFParser:
    """
    PDF document parser using PyMuPDF.
    """

    def __init__(self, use_vision: bool = True):
        """
        Initialize PDF parser.

        Args:
            use_vision: Whether to use Gemini vision for image analysis
        """
        self.use_vision = use_vision
        self._vision_client = None

    def _get_vision_client(self):
        """Lazy load vision client."""
        if self._vision_client is None and self.use_vision:
            try:
                from .vision_tool import GeminiVisionClient
                self._vision_client = GeminiVisionClient()
            except Exception as e:
                logger.warning(f"Vision client not available: {e}")
                self.use_vision = False
        return self._vision_client

    def parse(
        self,
        file_path: str,
        extract_images: bool = True,
        extract_tables: bool = True,
        analyze_images: bool = False,
        max_pages: Optional[int] = None
    ) -> PDFDocument:
        """
        Parse a PDF document.

        Args:
            file_path: Path to PDF file
            extract_images: Whether to extract images
            extract_tables: Whether to extract tables
            analyze_images: Whether to analyze images with vision
            max_pages: Maximum pages to process (None for all)

        Returns:
            PDFDocument with extracted content
        """
        try:
            import fitz  # PyMuPDF
        except ImportError:
            logger.error("PyMuPDF not installed. Install with: pip install pymupdf")
            return PDFDocument(file_path=file_path)

        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"PDF not found: {file_path}")

        doc = fitz.open(file_path)

        # Extract metadata
        metadata = self._extract_metadata(doc, path)

        # Process pages
        pages = []
        full_text_parts = []
        total_tables = 0
        total_images = 0

        page_limit = min(doc.page_count, max_pages) if max_pages else doc.page_count

        for page_num in range(page_limit):
            page = doc[page_num]

            # Extract text
            text = page.get_text("text")
            full_text_parts.append(text)

            # Extract tables
            tables = []
            if extract_tables:
                tables = self._extract_tables(page, page_num + 1)
                total_tables += len(tables)

            # Extract images
            images = []
            if extract_images:
                images = self._extract_images(page, page_num + 1, analyze_images)
                total_images += len(images)

            # Extract links
            links = self._extract_links(page)

            pages.append(PDFPage(
                page_number=page_num + 1,
                text=text,
                tables=tables,
                images=images,
                links=links
            ))

        doc.close()

        return PDFDocument(
            file_path=file_path,
            metadata=metadata,
            pages=pages,
            full_text="\n\n".join(full_text_parts),
            table_count=total_tables,
            image_count=total_images
        )

    def _extract_metadata(self, doc, path: Path) -> PDFMetadata:
        """Extract PDF metadata."""
        meta = doc.metadata or {}

        return PDFMetadata(
            title=meta.get("title"),
            author=meta.get("author"),
            subject=meta.get("subject"),
            creator=meta.get("creator"),
            producer=meta.get("producer"),
            creation_date=meta.get("creationDate"),
            modification_date=meta.get("modDate"),
            page_count=doc.page_count,
            file_size_bytes=path.stat().st_size
        )

    def _extract_tables(self, page, page_num: int) -> List[PDFTable]:
        """Extract tables from a page."""
        tables = []

        try:
            # Use PyMuPDF's table extraction
            found_tables = page.find_tables()

            for idx, table in enumerate(found_tables):
                # Extract table data
                data = table.extract()

                if not data or len(data) < 2:
                    continue

                # First row as headers
                headers = [str(cell) if cell else "" for cell in data[0]]

                # Remaining rows as data
                rows = [
                    [str(cell) if cell else "" for cell in row]
                    for row in data[1:]
                ]

                tables.append(PDFTable(
                    page_number=page_num,
                    table_index=idx,
                    headers=headers,
                    rows=rows,
                    bbox=table.bbox if hasattr(table, 'bbox') else None
                ))

        except Exception as e:
            logger.warning(f"Table extraction failed on page {page_num}: {e}")

        return tables

    def _extract_images(
        self,
        page,
        page_num: int,
        analyze: bool = False
    ) -> List[PDFImage]:
        """Extract images from a page."""
        images = []

        try:
            image_list = page.get_images(full=True)

            for idx, img_info in enumerate(image_list):
                xref = img_info[0]

                try:
                    # Get image data
                    base_image = page.parent.extract_image(xref)

                    if not base_image:
                        continue

                    image_bytes = base_image["image"]
                    image_ext = base_image["ext"]
                    width = base_image.get("width", 0)
                    height = base_image.get("height", 0)

                    # Convert to base64
                    base64_data = base64.standard_b64encode(image_bytes).decode("utf-8")

                    # Analyze with vision if requested
                    analysis = None
                    if analyze and self.use_vision:
                        client = self._get_vision_client()
                        if client:
                            try:
                                data_uri = f"data:image/{image_ext};base64,{base64_data}"
                                result = client.analyze_image(data_uri)
                                analysis = result.model_dump()
                            except Exception as e:
                                logger.warning(f"Image analysis failed: {e}")

                    images.append(PDFImage(
                        page_number=page_num,
                        image_index=idx,
                        width=width,
                        height=height,
                        format=image_ext,
                        base64_data=base64_data if len(base64_data) < 100000 else None,  # Limit size
                        analysis=analysis
                    ))

                except Exception as e:
                    logger.warning(f"Failed to extract image {idx} on page {page_num}: {e}")

        except Exception as e:
            logger.warning(f"Image extraction failed on page {page_num}: {e}")

        return images

    def _extract_links(self, page) -> List[str]:
        """Extract links from a page."""
        links = []

        try:
            for link in page.get_links():
                uri = link.get("uri")
                if uri:
                    links.append(uri)
        except Exception as e:
            logger.warning(f"Link extraction failed: {e}")

        return links

    def extract_text_only(self, file_path: str) -> str:
        """
        Extract only text from PDF (fast mode).

        Args:
            file_path: Path to PDF

        Returns:
            Extracted text
        """
        try:
            import fitz
        except ImportError:
            logger.error("PyMuPDF not installed")
            return ""

        try:
            doc = fitz.open(file_path)
            text_parts = []

            for page in doc:
                text_parts.append(page.get_text("text"))

            doc.close()
            return "\n\n".join(text_parts)

        except Exception as e:
            logger.error(f"PDF text extraction failed: {e}")
            return ""

    def extract_tables_only(self, file_path: str) -> List[PDFTable]:
        """
        Extract only tables from PDF.

        Args:
            file_path: Path to PDF

        Returns:
            List of extracted tables
        """
        try:
            import fitz
        except ImportError:
            logger.error("PyMuPDF not installed")
            return []

        try:
            doc = fitz.open(file_path)
            all_tables = []

            for page_num, page in enumerate(doc):
                tables = self._extract_tables(page, page_num + 1)
                all_tables.extend(tables)

            doc.close()
            return all_tables

        except Exception as e:
            logger.error(f"PDF table extraction failed: {e}")
            return []


# =============================================================================
# LangChain Tools
# =============================================================================

@tool
def parse_pdf(
    file_path: str,
    extract_images: bool = False,
    extract_tables: bool = True
) -> Dict[str, Any]:
    """
    Parse a PDF document and extract text, tables, and optionally images.

    Args:
        file_path: Path to PDF file
        extract_images: Whether to extract images
        extract_tables: Whether to extract tables

    Returns:
        Extracted PDF content including text, tables, and metadata
    """
    try:
        parser = PDFParser(use_vision=extract_images)
        result = parser.parse(
            file_path=file_path,
            extract_images=extract_images,
            extract_tables=extract_tables,
            analyze_images=False  # Don't auto-analyze to save API calls
        )

        # Convert to dict, but limit content size
        output = {
            "file_path": result.file_path,
            "metadata": result.metadata.model_dump(),
            "page_count": len(result.pages),
            "table_count": result.table_count,
            "image_count": result.image_count,
            "full_text": result.full_text[:50000],  # Limit text size
            "tables": [t.model_dump() for t in result.pages[0].tables] if result.pages else [],
        }

        return output

    except Exception as e:
        logger.error(f"PDF parsing failed: {e}")
        return {"error": str(e)}


@tool
def extract_pdf_text(file_path: str) -> str:
    """
    Extract text content from a PDF file.

    Args:
        file_path: Path to PDF file

    Returns:
        Extracted text content
    """
    try:
        parser = PDFParser(use_vision=False)
        return parser.extract_text_only(file_path)
    except Exception as e:
        logger.error(f"PDF text extraction failed: {e}")
        return f"Extraction failed: {str(e)}"


@tool
def extract_pdf_tables(file_path: str) -> List[Dict[str, Any]]:
    """
    Extract tables from a PDF file.

    Args:
        file_path: Path to PDF file

    Returns:
        List of extracted tables with headers and rows
    """
    try:
        parser = PDFParser(use_vision=False)
        tables = parser.extract_tables_only(file_path)
        return [t.model_dump() for t in tables]
    except Exception as e:
        logger.error(f"PDF table extraction failed: {e}")
        return [{"error": str(e)}]


@tool
def analyze_pdf_with_vision(
    file_path: str,
    pages: Optional[List[int]] = None
) -> Dict[str, Any]:
    """
    Parse PDF and analyze images/charts using Gemini vision.

    Args:
        file_path: Path to PDF file
        pages: Specific pages to analyze (1-indexed), or None for all

    Returns:
        PDF content with image analysis
    """
    try:
        parser = PDFParser(use_vision=True)
        result = parser.parse(
            file_path=file_path,
            extract_images=True,
            extract_tables=True,
            analyze_images=True,
            max_pages=max(pages) if pages else 10  # Limit pages for analysis
        )

        # Filter to requested pages
        if pages:
            filtered_pages = [p for p in result.pages if p.page_number in pages]
        else:
            filtered_pages = result.pages

        output = {
            "file_path": result.file_path,
            "metadata": result.metadata.model_dump(),
            "analyzed_pages": len(filtered_pages),
            "pages": []
        }

        for page in filtered_pages:
            page_data = {
                "page_number": page.page_number,
                "text_preview": page.text[:1000],
                "table_count": len(page.tables),
                "image_count": len(page.images),
                "images_with_analysis": [
                    {
                        "index": img.image_index,
                        "size": f"{img.width}x{img.height}",
                        "analysis": img.analysis
                    }
                    for img in page.images if img.analysis
                ]
            }
            output["pages"].append(page_data)

        return output

    except Exception as e:
        logger.error(f"PDF analysis failed: {e}")
        return {"error": str(e)}


# =============================================================================
# Convenience Functions
# =============================================================================

def get_pdf_parser(**kwargs) -> PDFParser:
    """Get a configured PDF parser."""
    return PDFParser(**kwargs)


def quick_pdf_extract(file_path: str) -> Dict[str, Any]:
    """
    Quick extraction of key content from PDF.

    Args:
        file_path: Path to PDF

    Returns:
        Dict with text, tables, and metadata
    """
    parser = PDFParser(use_vision=False)

    try:
        result = parser.parse(
            file_path=file_path,
            extract_images=False,
            extract_tables=True,
            max_pages=20
        )

        return {
            "metadata": result.metadata.model_dump(),
            "text": result.full_text,
            "tables": [t.model_dump() for t in sum([p.tables for p in result.pages], [])],
            "page_count": result.metadata.page_count,
        }

    except Exception as e:
        logger.error(f"Quick PDF extract failed: {e}")
        return {"error": str(e)}
