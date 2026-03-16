#!/usr/bin/env python3
"""
POLARIS Academic Paper Fetcher
==============================
Fetches actual academic paper content from various sources.

Supports:
- DOI resolution via CrossRef and Unpaywall
- PubMed Central full-text
- Semantic Scholar PDF links
- OpenAlex paper metadata + PDF
- PDF content extraction
- Archive.org fallback

Usage:
    from src.utils.academic_fetcher import AcademicFetcher

    fetcher = AcademicFetcher()
    content = await fetcher.fetch_paper(doi="10.1234/example")
"""

import asyncio
import hashlib
import os
import re
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote, urlparse

import aiohttp
import logging

# Configure logging
logger = logging.getLogger(__name__)

# Optional PDF extraction
try:
    import fitz  # PyMuPDF
    HAS_PYMUPDF = True
except ImportError:
    HAS_PYMUPDF = False


@dataclass
class PaperContent:
    """Extracted paper content."""
    doi: Optional[str] = None
    title: Optional[str] = None
    authors: List[str] = field(default_factory=list)
    abstract: Optional[str] = None
    full_text: Optional[str] = None
    source: str = "unknown"  # pubmed, semantic_scholar, openalex, crossref, unpaywall
    url: Optional[str] = None
    pdf_url: Optional[str] = None
    is_open_access: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)


class AcademicFetcher:
    """
    Fetches academic paper content from multiple sources.

    Priority order:
    1. Unpaywall (open access PDFs)
    2. PubMed Central (free full text)
    3. Semantic Scholar (PDF links)
    4. OpenAlex (metadata + links)
    5. CrossRef (DOI resolution)
    6. Archive.org (fallback)
    """

    def __init__(
        self,
        email: Optional[str] = None,
        cache_dir: Optional[Path] = None,
    ):
        """
        Initialize fetcher.

        Args:
            email: Email for API polite pool (recommended)
            cache_dir: Directory for caching PDFs
        """
        self.email = email or os.environ.get("POLARIS_EMAIL", "polaris@example.com")
        self.cache_dir = cache_dir or Path(tempfile.gettempdir()) / "polaris_papers"
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        # API endpoints
        self.unpaywall_base = "https://api.unpaywall.org/v2"
        self.crossref_base = "https://api.crossref.org/works"
        self.pmc_base = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
        self.semantic_scholar_base = "https://api.semanticscholar.org/graph/v1"
        self.openalex_base = "https://api.openalex.org"

    async def fetch_paper(
        self,
        doi: Optional[str] = None,
        pmid: Optional[str] = None,
        url: Optional[str] = None,
        title: Optional[str] = None,
    ) -> Optional[PaperContent]:
        """
        Fetch paper content from the best available source.

        Args:
            doi: Digital Object Identifier
            pmid: PubMed ID
            url: Direct URL to paper
            title: Paper title for search

        Returns:
            PaperContent if found, None otherwise
        """
        content = None

        # Try DOI-based fetching first
        if doi:
            # Clean DOI
            doi = self._clean_doi(doi)

            # Try Unpaywall first (best for open access)
            content = await self._fetch_unpaywall(doi)
            if content and content.full_text:
                return content

            # Try CrossRef for metadata + links
            content = await self._fetch_crossref(doi)
            if content and content.full_text:
                return content

        # Try PubMed if we have PMID
        if pmid:
            content = await self._fetch_pubmed(pmid)
            if content and content.full_text:
                return content

        # Try URL directly
        if url:
            content = await self._fetch_from_url(url)
            if content and content.full_text:
                return content

        # Try title search as last resort
        if title and not content:
            content = await self._search_by_title(title)

        return content

    def _clean_doi(self, doi: str) -> str:
        """Clean and normalize DOI."""
        # Remove common prefixes
        doi = doi.strip()
        doi = re.sub(r'^https?://(dx\.)?doi\.org/', '', doi)
        doi = re.sub(r'^doi:', '', doi, flags=re.IGNORECASE)
        return doi

    async def _fetch_unpaywall(self, doi: str) -> Optional[PaperContent]:
        """Fetch from Unpaywall API."""
        url = f"{self.unpaywall_base}/{quote(doi, safe='')}?email={self.email}"

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=30) as resp:
                    if resp.status != 200:
                        return None

                    data = await resp.json()

                    content = PaperContent(
                        doi=doi,
                        title=data.get("title"),
                        source="unpaywall",
                        url=data.get("doi_url"),
                        is_open_access=data.get("is_oa", False),
                    )

                    # Get best OA location
                    best_oa = data.get("best_oa_location")
                    if best_oa:
                        pdf_url = best_oa.get("url_for_pdf") or best_oa.get("url")
                        content.pdf_url = pdf_url

                        # Try to fetch PDF content
                        if pdf_url:
                            text = await self._extract_pdf_from_url(pdf_url)
                            if text:
                                content.full_text = text
                                return content

                    return content

        except Exception as e:
            # LOW-007: Log error instead of print
            logger.debug(f"Unpaywall error for {doi}: {e}")
            return None

    async def _fetch_crossref(self, doi: str) -> Optional[PaperContent]:
        """Fetch from CrossRef API."""
        url = f"{self.crossref_base}/{quote(doi, safe='')}"
        headers = {"User-Agent": f"POLARIS/1.0 (mailto:{self.email})"}

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers, timeout=30) as resp:
                    if resp.status != 200:
                        return None

                    data = await resp.json()
                    message = data.get("message", {})

                    content = PaperContent(
                        doi=doi,
                        title=message.get("title", [None])[0],
                        source="crossref",
                        url=message.get("URL"),
                    )

                    # Extract authors
                    for author in message.get("author", []):
                        name = f"{author.get('given', '')} {author.get('family', '')}".strip()
                        if name:
                            content.authors.append(name)

                    # Check for full-text links
                    for link in message.get("link", []):
                        if link.get("content-type") == "application/pdf":
                            content.pdf_url = link.get("URL")
                            break

                    # Try to fetch PDF
                    if content.pdf_url:
                        text = await self._extract_pdf_from_url(content.pdf_url)
                        if text:
                            content.full_text = text

                    return content

        except Exception as e:
            # LOW-008: Log error instead of print
            logger.debug(f"CrossRef error for {doi}: {e}")
            return None

    async def _fetch_pubmed(self, pmid: str) -> Optional[PaperContent]:
        """Fetch from PubMed Central."""
        # First get article metadata
        search_url = f"{self.pmc_base}/esearch.fcgi?db=pmc&term={pmid}[pmid]&retmode=json"

        try:
            async with aiohttp.ClientSession() as session:
                # Search for PMC ID
                async with session.get(search_url, timeout=30) as resp:
                    if resp.status != 200:
                        return None

                    data = await resp.json()
                    id_list = data.get("esearchresult", {}).get("idlist", [])

                    if not id_list:
                        return None

                    pmc_id = id_list[0]

                # Fetch full text
                fetch_url = f"{self.pmc_base}/efetch.fcgi?db=pmc&id={pmc_id}&rettype=full&retmode=xml"

                async with session.get(fetch_url, timeout=60) as resp:
                    if resp.status != 200:
                        return None

                    xml_content = await resp.text()

                    # Extract text from XML (simplified)
                    text = self._extract_text_from_pmc_xml(xml_content)

                    if text:
                        return PaperContent(
                            doi=None,
                            source="pubmed",
                            full_text=text,
                            url=f"https://www.ncbi.nlm.nih.gov/pmc/articles/PMC{pmc_id}/",
                            is_open_access=True,
                            metadata={"pmid": pmid, "pmc_id": pmc_id},
                        )

        except Exception as e:
            # LOW-009: Log error instead of print
            logger.debug(f"PubMed error for {pmid}: {e}")
            return None

        return None

    def _extract_text_from_pmc_xml(self, xml: str) -> Optional[str]:
        """Extract readable text from PMC XML."""
        import re

        # Remove XML tags but keep content
        text = re.sub(r'<[^>]+>', ' ', xml)
        # Clean up whitespace
        text = re.sub(r'\s+', ' ', text).strip()

        # Only return if we got substantial content
        if len(text) > 1000:
            return text

        return None

    async def _fetch_from_url(self, url: str) -> Optional[PaperContent]:
        """Fetch content directly from URL."""
        try:
            parsed = urlparse(url)

            # Check if it's a PDF
            if url.lower().endswith('.pdf') or 'pdf' in parsed.path.lower():
                text = await self._extract_pdf_from_url(url)
                if text:
                    return PaperContent(
                        source="direct_pdf",
                        url=url,
                        full_text=text,
                    )

            # Try as HTML
            async with aiohttp.ClientSession() as session:
                headers = {
                    "User-Agent": "Mozilla/5.0 (compatible; POLARIS/1.0)"
                }
                async with session.get(url, headers=headers, timeout=30) as resp:
                    if resp.status != 200:
                        return None

                    content_type = resp.headers.get("Content-Type", "")

                    if "pdf" in content_type:
                        pdf_bytes = await resp.read()
                        text = self._extract_pdf_from_bytes(pdf_bytes)
                        if text:
                            return PaperContent(
                                source="direct_pdf",
                                url=url,
                                full_text=text,
                            )
                    else:
                        html = await resp.text()
                        text = self._extract_text_from_html(html)
                        if text and len(text) > 500:
                            return PaperContent(
                                source="direct_html",
                                url=url,
                                full_text=text,
                            )

        except Exception as e:
            # LOW-010: Log error instead of print
            logger.debug(f"URL fetch error for {url}: {e}")

        return None

    async def _extract_pdf_from_url(self, url: str) -> Optional[str]:
        """Download and extract text from PDF URL."""
        if not HAS_PYMUPDF:
            return None

        try:
            # Check cache first
            cache_key = hashlib.md5(url.encode()).hexdigest()
            cache_path = self.cache_dir / f"{cache_key}.txt"

            if cache_path.exists():
                return cache_path.read_text(encoding="utf-8")

            # Download PDF
            async with aiohttp.ClientSession() as session:
                headers = {"User-Agent": "Mozilla/5.0 (compatible; POLARIS/1.0)"}
                async with session.get(url, headers=headers, timeout=60) as resp:
                    if resp.status != 200:
                        return None

                    content_type = resp.headers.get("Content-Type", "")
                    if "pdf" not in content_type and not url.lower().endswith('.pdf'):
                        return None

                    pdf_bytes = await resp.read()

            # Extract text
            text = self._extract_pdf_from_bytes(pdf_bytes)

            # Cache result
            if text:
                cache_path.write_text(text, encoding="utf-8")

            return text

        except Exception as e:
            # LOW-011: Log error instead of print
            logger.debug(f"PDF extraction error for {url}: {e}")
            return None

    def _extract_pdf_from_bytes(self, pdf_bytes: bytes) -> Optional[str]:
        """Extract text from PDF bytes using PyMuPDF."""
        if not HAS_PYMUPDF:
            return None

        try:
            doc = fitz.open(stream=pdf_bytes, filetype="pdf")
            text_parts = []

            for page in doc:
                text = page.get_text()
                if text:
                    text_parts.append(text)

            doc.close()

            full_text = "\n\n".join(text_parts)

            # Only return if we got substantial content
            if len(full_text) > 500:
                return full_text

        except Exception as e:
            # LOW-012: Log error instead of print
            logger.debug(f"PyMuPDF error: {e}")

        return None

    def _extract_text_from_html(self, html: str) -> Optional[str]:
        """Extract readable text from HTML."""
        import re

        # Remove script and style elements
        html = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL | re.IGNORECASE)
        html = re.sub(r'<style[^>]*>.*?</style>', '', html, flags=re.DOTALL | re.IGNORECASE)

        # Remove HTML tags
        text = re.sub(r'<[^>]+>', ' ', html)

        # Decode HTML entities
        text = text.replace('&nbsp;', ' ')
        text = text.replace('&amp;', '&')
        text = text.replace('&lt;', '<')
        text = text.replace('&gt;', '>')
        text = text.replace('&quot;', '"')

        # Clean up whitespace
        text = re.sub(r'\s+', ' ', text).strip()

        return text if len(text) > 100 else None

    async def _search_by_title(self, title: str) -> Optional[PaperContent]:
        """Search for paper by title using OpenAlex."""
        encoded_title = quote(title)
        url = f"{self.openalex_base}/works?filter=title.search:{encoded_title}&per-page=1"

        try:
            async with aiohttp.ClientSession() as session:
                headers = {"User-Agent": f"POLARIS/1.0 (mailto:{self.email})"}
                async with session.get(url, headers=headers, timeout=30) as resp:
                    if resp.status != 200:
                        return None

                    data = await resp.json()
                    results = data.get("results", [])

                    if not results:
                        return None

                    work = results[0]
                    doi = work.get("doi", "").replace("https://doi.org/", "")

                    content = PaperContent(
                        doi=doi if doi else None,
                        title=work.get("title"),
                        source="openalex",
                        url=work.get("id"),
                        is_open_access=work.get("open_access", {}).get("is_oa", False),
                    )

                    # Get PDF URL if available
                    oa_url = work.get("open_access", {}).get("oa_url")
                    if oa_url:
                        content.pdf_url = oa_url
                        text = await self._extract_pdf_from_url(oa_url)
                        if text:
                            content.full_text = text

                    # If no PDF, try DOI-based fetching
                    if not content.full_text and doi:
                        unpaywall_content = await self._fetch_unpaywall(doi)
                        if unpaywall_content and unpaywall_content.full_text:
                            content.full_text = unpaywall_content.full_text

                    return content

        except Exception as e:
            # LOW-013: Log error instead of print
            logger.debug(f"OpenAlex search error: {e}")
            return None

    async def fetch_semantic_scholar(self, paper_id: str) -> Optional[PaperContent]:
        """Fetch from Semantic Scholar API."""
        url = f"{self.semantic_scholar_base}/paper/{paper_id}"
        params = "?fields=title,abstract,authors,openAccessPdf,externalIds"

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url + params, timeout=30) as resp:
                    if resp.status != 200:
                        return None

                    data = await resp.json()

                    content = PaperContent(
                        doi=data.get("externalIds", {}).get("DOI"),
                        title=data.get("title"),
                        abstract=data.get("abstract"),
                        source="semantic_scholar",
                    )

                    # Get authors
                    for author in data.get("authors", []):
                        if author.get("name"):
                            content.authors.append(author["name"])

                    # Get PDF URL
                    oa_pdf = data.get("openAccessPdf")
                    if oa_pdf:
                        content.pdf_url = oa_pdf.get("url")
                        content.is_open_access = True

                        # Try to fetch PDF
                        if content.pdf_url:
                            text = await self._extract_pdf_from_url(content.pdf_url)
                            if text:
                                content.full_text = text

                    return content

        except Exception as e:
            # LOW-014: Log error instead of print
            logger.debug(f"Semantic Scholar error: {e}")
            return None


# =============================================================================
# URL CLASSIFIER
# =============================================================================

def classify_url(url: str) -> str:
    """
    Classify URL type for routing to appropriate fetcher.

    Returns:
        One of: "academic", "pdf", "standard"
    """
    parsed = urlparse(url)
    domain = parsed.netloc.lower()
    path = parsed.path.lower()

    # Academic domains
    academic_domains = [
        "pubmed.ncbi.nlm.nih.gov",
        "ncbi.nlm.nih.gov",
        "pmc.ncbi.nlm.nih.gov",
        "semanticscholar.org",
        "openalex.org",
        "doi.org",
        "dx.doi.org",
        "arxiv.org",
        "biorxiv.org",
        "medrxiv.org",
        "scholar.google.com",
        "researchgate.net",
        "academia.edu",
    ]

    # Check for academic domain
    for academic in academic_domains:
        if academic in domain:
            return "academic"

    # Check for DOI pattern
    if re.search(r'10\.\d{4,}/', url):
        return "academic"

    # Check for PDF
    if path.endswith('.pdf') or 'pdf' in path:
        return "pdf"

    return "standard"


def extract_doi_from_url(url: str) -> Optional[str]:
    """Extract DOI from URL if present."""
    # Pattern for DOI
    match = re.search(r'(10\.\d{4,}/[^\s\]"\'<>]+)', url)
    if match:
        return match.group(1)
    return None


# =============================================================================
# SELF-TEST
# =============================================================================

if __name__ == "__main__":
    import asyncio

    async def test():
        print("=" * 60)
        print("ACADEMIC FETCHER SELF-TEST")
        print("=" * 60)

        fetcher = AcademicFetcher()

        # Test DOI fetch
        test_doi = "10.1016/j.watres.2019.115111"  # Water research paper
        print(f"\n[TEST 1] Fetching DOI: {test_doi}")

        content = await fetcher.fetch_paper(doi=test_doi)
        if content:
            print(f"  Title: {content.title}")
            print(f"  Source: {content.source}")
            print(f"  Open Access: {content.is_open_access}")
            print(f"  PDF URL: {content.pdf_url}")
            print(f"  Has full text: {bool(content.full_text)}")
            if content.full_text:
                print(f"  Text length: {len(content.full_text)} chars")
        else:
            print("  No content found")

        # Test URL classification
        print("\n[TEST 2] URL Classification")
        test_urls = [
            "https://pubmed.ncbi.nlm.nih.gov/12345678/",
            "https://doi.org/10.1234/example",
            "https://example.com/paper.pdf",
            "https://example.com/article",
        ]
        for url in test_urls:
            print(f"  {classify_url(url):10} <- {url}")

        print("\n" + "=" * 60)
        print("TEST COMPLETE")
        print("=" * 60)

    asyncio.run(test())
