#!/usr/bin/env python3
"""
POLARIS Content Ingestion - SOTA Edition
=========================================
URL fetching with Trafilatura for forensic text extraction.

Features:
- Trafilatura for clean HTML-to-text conversion (SOTA)
- pdfminer.six for PDF text extraction
- Zero HTML artifacts in NLI pipeline
- User-Agent rotation and rate limiting

Usage:
    from src.utils.ingest import fetch_url, ContentFetcher, extract_text_forensic

    content = await fetch_url("https://example.com/article")
    clean_text = extract_text_forensic(content.content, content.content_type)
"""

import asyncio
import hashlib
import io
import logging
import random
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import httpx
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)

# SOTA Text Extraction Libraries
try:
    import trafilatura
    TRAFILATURA_AVAILABLE = True
except ImportError:
    TRAFILATURA_AVAILABLE = False

try:
    from pdfminer.high_level import extract_text as pdfminer_extract_text
    from pdfminer.pdfparser import PDFSyntaxError
    PDFMINER_AVAILABLE = True
except ImportError:
    PDFMINER_AVAILABLE = False

from src.config import get_config
from src.utils.rate_limiter import get_rate_limiter

# Configure logging
logger = logging.getLogger(__name__)


# =============================================================================
# FORENSIC TEXT EXTRACTION (SOTA - Trafilatura + pdfminer)
# =============================================================================

# Boilerplate patterns to remove (IRON LOOP: Sterile Ingestion)
BOILERPLATE_PATTERNS = [
    r"click here to see",
    r"cookie policy",
    r"privacy policy",
    r"terms of service",
    r"all rights reserved",
    r"subscribe to our newsletter",
    r"sign up for",
    r"follow us on",
    r"share this article",
    r"related articles",
    r"you may also like",
    r"powered by",
    r"copyright \d{4}",
    r"©\s*\d{4}",
    # IRON LOOP: Additional fluff patterns
    r"add to cart",
    r"buy now",
    r"search menu",
    r"skip to content",
    r"skip to main",
    r"toggle navigation",
    r"close menu",
    r"open menu",
    r"accept cookies",
    r"we use cookies",
    r"manage preferences",
    r"manage consent",
    r"your privacy",
    r"data protection",
    r"gdpr",
    r"loading\.\.\.",
    r"please wait",
    r"affiliate link",
    r"sponsored content",
    r"advertisement",
    r"promoted",
    r"read more",
    r"continue reading",
    r"show more",
    r"see also",
    r"popular posts",
    r"trending now",
    r"most read",
    r"editors pick",
    r"editor's choice",
    r"contact us",
    r"about us",
    r"terms and conditions",
    r"sitemap",
    r"rss feed",
    r"print this",
    r"email this",
    r"log in",
    r"sign in",
    r"create account",
    r"register now",
    r"join free",
    r"free trial",
    r"get started",
]

BOILERPLATE_REGEX = re.compile(
    "|".join(BOILERPLATE_PATTERNS),
    re.IGNORECASE
)

# IRON LOOP: Fluff phrases that indicate garbage chunks
FLUFF_PHRASES = [
    "cookie policy",
    "rights reserved",
    "subscribe",
    "search menu",
    "add to cart",
    "buying guide",
    "best reviews",
    "top 10",
    "affiliate",
    "sponsored",
    "advertisement",
    "privacy policy",
    "terms of service",
    "contact us",
    "about us",
    "navigation menu",
    "skip to",
    "toggle menu",
    "close modal",
    "accept all",
    "reject all",
    "manage cookies",
]


# =============================================================================
# BUG-008 FIX: BIBLIOGRAPHIC METADATA VALIDATION
# Prevents garbage author values like "Username", "Contact X", mirror domains
# NO HARDCODING - patterns are generic validation rules, not topic-specific
# =============================================================================

# Garbage author patterns to reject - these are GENERIC patterns that indicate
# scraping errors, not topic-specific terms. They apply to ALL 400+ applications.
GARBAGE_AUTHOR_PATTERNS = [
    r'^username$',  # Forum/comment section scraped
    r'^user$',
    r'^author$',
    r'^admin$',
    r'^anonymous$',
    r'^unknown$',
    r'^contact\s+',  # Press contact scraped (e.g., "Contact Andrew Mann")
    r'^press\s+contact',
    r'^media\s+contact',
    r'^for\s+immediate\s+release',
    r'^news\s+release',
    r'^\d+$',  # Just numbers
    r'^\.com$',
    r'^\.org$',
    r'^\.gov$',
    r'^http',  # URLs
    r'^\s*$',  # Empty/whitespace
    r'^n/a$',
    r'^none$',
    r'^see\s+',
    r'^click\s+',
]


def _load_domain_normalization_map() -> Dict[str, Optional[str]]:
    """
    Load domain normalization map from config.

    Returns map of mirror/archive domains to canonical domains.
    If not configured, returns empty dict (no normalization).

    This allows domain mappings to be configured per-deployment
    without hardcoding in source code.
    """
    try:
        from src.config import get_config
        config = get_config()
        # Try to get from config, default to empty if not configured
        return getattr(config, 'domain_normalization_map', {}) or {}
    except Exception:
        # Config not available - return empty (no normalization)
        return {}


def validate_author_field(author: str) -> Optional[str]:
    """
    BUG-008 FIX: Validate and clean author field.

    Rejects garbage values like:
    - "Username" (forum scraped)
    - "Contact Andrew Mann" (press contact)
    - URLs/domains as author

    Args:
        author: Raw author string

    Returns:
        Cleaned author string or None if garbage
    """
    if not author:
        return None

    author_clean = author.strip()
    author_lower = author_clean.lower()

    # Check against garbage patterns
    for pattern in GARBAGE_AUTHOR_PATTERNS:
        if re.match(pattern, author_lower):
            return None

    # Check if author is actually a domain/URL
    if "." in author_clean and " " not in author_clean:
        # Looks like a domain (e.g., "restoredcdc.org")
        if any(tld in author_lower for tld in [".com", ".org", ".gov", ".edu", ".net"]):
            return None

    # Check if too short (likely garbage)
    if len(author_clean) < 3:
        return None

    # Check if mostly non-alphabetic (likely scraped junk)
    alpha_count = sum(1 for c in author_clean if c.isalpha())
    if len(author_clean) > 0 and alpha_count / len(author_clean) < 0.5:
        return None

    return author_clean


def normalize_url_domain(url: str) -> str:
    """
    BUG-008 FIX: Normalize URL to canonical domain.

    Converts mirror/archive URLs to original sources.
    Domain mappings loaded from config (not hardcoded).

    Args:
        url: Source URL

    Returns:
        Normalized URL
    """
    if not url:
        return url

    url_lower = url.lower()

    # Load domain normalization map from config (not hardcoded)
    domain_map = _load_domain_normalization_map()

    # Check for configured mirror domains
    for mirror, canonical in domain_map.items():
        if mirror in url_lower:
            if canonical:
                # Replace with canonical domain
                return url_lower.replace(mirror, canonical)
            else:
                # Archive URL - try to extract original
                # e.g., web.archive.org/web/123/https://cdc.gov/page
                archive_match = re.search(r'archive\.org/web/\d+/(https?://[^/]+)', url)
                if archive_match:
                    return archive_match.group(1)

    # Generic archive.org handling (infrastructure, not topic-specific)
    if "archive.org/web/" in url_lower:
        archive_match = re.search(r'archive\.org/web/\d+/(https?://[^/]+)', url)
        if archive_match:
            return archive_match.group(1)

    return url


def is_garbage_chunk(text: str) -> bool:
    """
    IRON LOOP: Check if a chunk is garbage/fluff that should be dropped.

    Args:
        text: Text to check

    Returns:
        True if the chunk is garbage and should be dropped
    """
    if not text or len(text.strip()) < 50:
        return True

    text_lower = text.lower()

    # Check for fluff phrases
    for phrase in FLUFF_PHRASES:
        if phrase in text_lower:
            return True

    # Check alpha ratio - reject if mostly non-alphabetic
    alpha_count = sum(1 for c in text if c.isalpha())
    if len(text) > 0 and alpha_count / len(text) < 0.5:
        return True

    return False


def extract_author_from_url(url: str) -> str:
    """
    IRON LOOP: Metadata Repair - Extract author/source from URL domain.

    If metadata author is "Unknown", use the domain name as author.
    FIX BUG 9: Map institutional domains to proper organization names.

    Args:
        url: Source URL

    Returns:
        Organization name or domain name as author
    """
    if not url:
        return "Unknown"

    # SOTA: Expanded institutional domain to author/organization mapping
    # Priority: Use actual author names when extracted from content
    # This serves as fallback when author extraction fails
    INSTITUTIONAL_AUTHOR_MAP = {
        # US Government agencies
        "epa.gov": "U.S. Environmental Protection Agency",
        "cdc.gov": "U.S. Centers for Disease Control and Prevention",
        "nih.gov": "National Institutes of Health",
        "fda.gov": "U.S. Food and Drug Administration",
        "usgs.gov": "U.S. Geological Survey",
        "noaa.gov": "National Oceanic and Atmospheric Administration",
        "hhs.gov": "U.S. Department of Health and Human Services",
        "usda.gov": "U.S. Department of Agriculture",
        "energy.gov": "U.S. Department of Energy",
        "state.gov": "U.S. Department of State",
        "census.gov": "U.S. Census Bureau",
        # International organizations
        "who.int": "World Health Organization",
        "europa.eu": "European Commission",
        "un.org": "United Nations",
        "worldbank.org": "World Bank",
        "unicef.org": "UNICEF",
        "oecd.org": "OECD",
        "wto.org": "World Trade Organization",
        # National governments
        "canada.ca": "Health Canada",
        "gov.uk": "UK Health Security Agency",
        "gov.au": "Australian Government",
        "efsa.europa.eu": "European Food Safety Authority",
        # Academic publishers (fallback if author not extracted)
        "nature.com": "Nature Publishing Group",
        "sciencedirect.com": "Elsevier",
        "springer.com": "Springer",
        "wiley.com": "Wiley",
        "tandfonline.com": "Taylor & Francis",
        "oup.com": "Oxford University Press",
        "cambridge.org": "Cambridge University Press",
        "plos.org": "PLOS",
        "mdpi.com": "MDPI",
        "frontiersin.org": "Frontiers",
        "bmj.com": "BMJ",
        "thelancet.com": "The Lancet",
        "nejm.org": "New England Journal of Medicine",
        "jamanetwork.com": "JAMA Network",
        # Research institutions
        "nationalacademies.org": "National Academies of Sciences",
        "nap.edu": "National Academies Press",
        "rand.org": "RAND Corporation",
        "brookings.edu": "Brookings Institution",
        # Water/Environment specific
        "oxfamwash.org": "Oxfam WASH",
        "washresources.cawst.org": "CAWST",
        "cawst.org": "CAWST",
        "wateraid.org": "WaterAid",
        "wqa.org": "Water Quality Association",
        "wqrf.org": "Water Quality Research Foundation",
        "waterrf.org": "Water Research Foundation",
        "awwa.org": "American Water Works Association",
        "nsf.org": "NSF International",
        "iwa-network.org": "International Water Association",
        # Academic databases (prefer individual author extraction)
        "pmc.ncbi.nlm.nih.gov": "PubMed Central",
        "pubmed.ncbi.nlm.nih.gov": "PubMed",
        "ncbi.nlm.nih.gov": "NCBI",
        "semanticscholar.org": "Semantic Scholar",
        "arxiv.org": "arXiv",
        "ssrn.com": "SSRN",
        "researchgate.net": "ResearchGate",
        "academia.edu": "Academia.edu",
    }

    try:
        parsed = urlparse(url)
        domain = parsed.netloc.lower()

        # Remove www. prefix
        if domain.startswith("www."):
            domain = domain[4:]

        # Check institutional mapping first
        for pattern, org_name in INSTITUTIONAL_AUTHOR_MAP.items():
            if pattern in domain:
                return org_name

        # Fallback to domain name
        if domain:
            return domain
    except (ValueError, AttributeError):
        # URL parsing failed - return fallback
        return "Unknown"

    return "Unknown"


def extract_text_forensic(content: str, content_type: str = "", url: str = "") -> Tuple[str, str]:
    """
    SOTA Forensic Text Extraction - Zero HTML in NLI pipeline.

    Uses Trafilatura for HTML extraction (industry-leading accuracy).
    Uses pdfminer.six for PDF extraction.

    Args:
        content: Raw content (HTML or PDF bytes)
        content_type: MIME type (e.g., "text/html", "application/pdf")
        url: Source URL (helps Trafilatura with site-specific rules)

    Returns:
        Tuple of (clean_text, extracted_title)
    """
    if not content:
        return "", ""

    # Detect content type
    is_pdf = (
        "pdf" in content_type.lower() or
        url.lower().endswith(".pdf") or
        content[:5] == b'%PDF-' if isinstance(content, bytes) else content[:5] == '%PDF-'
    )

    if is_pdf:
        return _extract_text_from_pdf(content)
    else:
        return _extract_text_from_html_trafilatura(content, url)


def _extract_text_from_html_trafilatura(raw_html: str, url: str = "") -> Tuple[str, str]:
    """
    Extract text from HTML using Trafilatura (SOTA accuracy).

    Trafilatura is the industry standard for web content extraction,
    outperforming newspaper3k, readability, and BeautifulSoup.

    Args:
        raw_html: Raw HTML content
        url: Source URL (optional, helps with site-specific extraction)

    Returns:
        Tuple of (clean_text, extracted_title)
    """
    if not raw_html:
        return "", ""

    title = ""

    # SOTA: Use Trafilatura
    if TRAFILATURA_AVAILABLE:
        try:
            # GH #1260: both libxml2 doors (extract + extract_metadata) go
            # through the ONE SIGSEGV-guarded entrypoint (size gate + optional
            # hard-killable subprocess). A bare call here would let a libxml2
            # C-crash on a pathological doc take down the whole process —
            # uncatchable by `except Exception`.
            from src.tools.access_bypass import (
                safe_trafilatura_extract,
                safe_trafilatura_extract_metadata,
            )
            # Trafilatura extraction with optimal settings
            extracted = safe_trafilatura_extract(
                raw_html,
                include_tables=True,       # Keep table data
                include_comments=False,    # No comments
                include_images=False,      # No image tags
                no_fallback=False,         # Use fallback if main extraction fails
                favor_precision=True,      # Prefer precision over recall
                deduplicate=True,          # Remove duplicate content
                url=url if url else None,  # Site-specific rules
            )

            if extracted:
                # Get title via metadata extraction
                metadata = safe_trafilatura_extract_metadata(raw_html)
                if metadata and metadata.title:
                    title = metadata.title

                # Final cleanup
                text = _clean_extracted_text(extracted)
                return text, title

        except Exception as e:
            logger.warning(f"Trafilatura extraction failed: {e}, falling back to BS4")

    # Fallback to BeautifulSoup if Trafilatura unavailable or failed
    return _clean_html_bs4(raw_html)


def _extract_text_from_pdf(content: bytes | str) -> Tuple[str, str]:
    """
    Extract text from PDF using pdfminer.six.

    Args:
        content: PDF content (bytes or string)

    Returns:
        Tuple of (clean_text, extracted_title)
    """
    if not PDFMINER_AVAILABLE:
        logger.warning("pdfminer.six not available, cannot extract PDF text")
        return "", ""

    try:
        # Convert string to bytes if needed
        if isinstance(content, str):
            content = content.encode('latin-1', errors='replace')

        # Extract text from PDF
        pdf_file = io.BytesIO(content)
        text = pdfminer_extract_text(pdf_file)

        # Clean the extracted text
        if text:
            text = _clean_extracted_text(text)

            # Try to extract title from first line or heading
            lines = text.split('\n')
            title = ""
            for line in lines[:5]:  # Check first 5 lines
                line = line.strip()
                if len(line) > 10 and len(line) < 200:
                    title = line
                    break

            return text, title

    except PDFSyntaxError as e:
        logger.warning(f"PDF syntax error: {e}")
    except Exception as e:
        logger.warning(f"PDF extraction error: {e}")

    return "", ""


def _clean_html_bs4(raw_html: str) -> Tuple[str, str]:
    """
    Fallback HTML cleaning using BeautifulSoup.

    Args:
        raw_html: Raw HTML content

    Returns:
        Tuple of (clean_text, extracted_title)
    """
    if not raw_html:
        return "", ""

    try:
        from bs4 import BeautifulSoup
    except ImportError:
        logger.warning("BeautifulSoup not available, using regex fallback")
        return _clean_html_regex(raw_html)

    # Parse HTML
    soup = BeautifulSoup(raw_html, "html.parser")

    # Extract title before removing tags
    title = ""
    title_tag = soup.find("title")
    if title_tag and title_tag.string:
        title = title_tag.string.strip()

    # Also check og:title and meta title
    if not title:
        og_title = soup.find("meta", property="og:title")
        if og_title and og_title.get("content"):
            title = og_title["content"].strip()

    if not title:
        meta_title = soup.find("meta", attrs={"name": "title"})
        if meta_title and meta_title.get("content"):
            title = meta_title["content"].strip()

    # Remove unwanted tags completely (including their content)
    for tag_name in ["script", "style", "nav", "header", "footer", "aside",
                     "noscript", "iframe", "form", "button", "input", "select",
                     "meta", "link", "head"]:
        for tag in soup.find_all(tag_name):
            tag.decompose()

    # Remove elements with common boilerplate classes/ids
    boilerplate_selectors = [
        "[class*='cookie']", "[id*='cookie']",
        "[class*='sidebar']", "[id*='sidebar']",
        "[class*='footer']", "[id*='footer']",
        "[class*='header']", "[id*='header']",
        "[class*='nav']", "[id*='nav']",
        "[class*='menu']", "[id*='menu']",
        "[class*='ad-']", "[id*='ad-']",
        "[class*='social']", "[id*='social']",
        "[class*='share']", "[id*='share']",
        "[class*='comment']", "[id*='comment']",
        "[class*='related']", "[id*='related']",
    ]

    for selector in boilerplate_selectors:
        try:
            for element in soup.select(selector):
                element.decompose()
        except (ValueError, SyntaxError) as e:
            # LOW-031: Log invalid CSS selector
            logger.debug(f"Invalid CSS selector '{selector}': {e}")

    # Get text content
    text = soup.get_text(separator=" ", strip=True)

    # Clean up the text
    text = _clean_extracted_text(text)

    return text, title


def _clean_html_regex(raw_html: str) -> Tuple[str, str]:
    """
    Fallback HTML cleaning using regex when BeautifulSoup is not available.

    Args:
        raw_html: Raw HTML content

    Returns:
        Tuple of (clean_text, extracted_title)
    """
    # Extract title
    title = ""
    title_match = re.search(r"<title[^>]*>([^<]+)</title>", raw_html, re.IGNORECASE)
    if title_match:
        title = title_match.group(1).strip()

    # Remove script and style blocks
    text = re.sub(r"<script[^>]*>.*?</script>", " ", raw_html, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<style[^>]*>.*?</style>", " ", text, flags=re.DOTALL | re.IGNORECASE)

    # Remove all HTML tags
    text = re.sub(r"<[^>]+>", " ", text)

    # Decode HTML entities
    text = re.sub(r"&nbsp;", " ", text)
    text = re.sub(r"&amp;", "&", text)
    text = re.sub(r"&lt;", "<", text)
    text = re.sub(r"&gt;", ">", text)
    text = re.sub(r"&quot;", '"', text)
    text = re.sub(r"&#\d+;", " ", text)
    text = re.sub(r"&[a-zA-Z]+;", " ", text)

    # Clean up
    text = _clean_extracted_text(text)

    return text, title


def _clean_extracted_text(text: str) -> str:
    """
    Clean extracted text by removing boilerplate and normalizing whitespace.

    Args:
        text: Extracted text content

    Returns:
        Cleaned text
    """
    if not text:
        return ""

    # Remove boilerplate lines
    lines = text.split("\n")
    clean_lines = []

    for line in lines:
        line = line.strip()
        if not line:
            continue

        # Skip very short lines (likely navigation items)
        if len(line) < 15:
            continue

        # Skip lines matching boilerplate patterns
        if BOILERPLATE_REGEX.search(line):
            continue

        # Skip lines that are mostly punctuation or numbers
        alpha_ratio = sum(1 for c in line if c.isalpha()) / max(len(line), 1)
        if alpha_ratio < 0.4:
            continue

        clean_lines.append(line)

    text = " ".join(clean_lines)

    # Normalize whitespace
    text = re.sub(r"\s+", " ", text)
    text = text.strip()

    # Remove any remaining HTML-like artifacts
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\{[^}]+\}", "", text)  # CSS-like artifacts

    return text


# Backwards compatibility alias
def clean_html(raw_html: str) -> Tuple[str, str]:
    """Backwards compatible alias for extract_text_forensic."""
    return extract_text_forensic(raw_html, "text/html")


def extract_title_from_url(url: str) -> str:
    """
    Extract a readable title from URL slug as fallback.

    Args:
        url: URL string

    Returns:
        Extracted title or empty string
    """
    try:
        parsed = urlparse(url)
        path = parsed.path.rstrip("/")

        if not path or path == "/":
            return parsed.netloc

        # Get last path component
        slug = path.split("/")[-1]

        # Remove file extension
        slug = re.sub(r"\.(html?|php|asp|aspx|jsp|pdf)$", "", slug, flags=re.IGNORECASE)

        # Convert slug to readable title
        title = slug.replace("-", " ").replace("_", " ")
        title = re.sub(r"[^\w\s]", " ", title)
        title = " ".join(word.capitalize() for word in title.split())

        return title if len(title) > 3 else parsed.netloc

    except (ValueError, AttributeError, TypeError):
        return ""


# =============================================================================
# ISSUE C FIX: ENHANCED METADATA EXTRACTION
# =============================================================================


def _extract_pmid_from_url(url: str) -> Optional[str]:
    """Extract PMID from PubMed URL."""
    # Patterns: /pubmed/12345678, /12345678/, ?term=12345678
    import re
    patterns = [
        r'pubmed\.ncbi\.nlm\.nih\.gov/(\d{7,8})',
        r'pubmed/(\d{7,8})',
        r'/(\d{7,8})/?$',
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None


def _extract_pmcid_from_url(url: str) -> Optional[str]:
    """Extract PMCID from PMC URL."""
    import re
    # Pattern: /articles/PMC1234567/
    match = re.search(r'PMC(\d{6,8})', url, re.IGNORECASE)
    if match:
        return f"PMC{match.group(1)}"
    return None


def extract_doi_from_url(url: str) -> Optional[str]:
    """
    Extract DOI from URL - universal fallback for all URLs.

    Handles formats:
    - https://doi.org/10.1234/example
    - https://dx.doi.org/10.1234/example
    - URLs with DOI in query params: ?doi=10.1234/example
    - URLs with DOI in path: /article/10.1234/example

    DOI format: 10.XXXX/suffix where suffix can contain various characters
    but should stop at URL terminators (#, ?, or end).

    Args:
        url: Any URL that might contain a DOI

    Returns:
        DOI string (e.g., "10.1234/example") or None
    """
    import re
    from urllib.parse import unquote

    if not url:
        return None

    # Decode URL-encoded characters
    decoded_url = unquote(url)

    # Pattern 1: doi.org or dx.doi.org direct links
    # Stop at query params, fragments, or trailing slashes
    doi_org_match = re.search(
        r'(?:dx\.)?doi\.org/(10\.\d{4,}/[^?\s#]+)',
        decoded_url,
        re.IGNORECASE
    )
    if doi_org_match:
        doi = doi_org_match.group(1).rstrip('/')
        return doi

    # Pattern 2: DOI in query parameter
    doi_param_match = re.search(
        r'[?&]doi=(10\.\d{4,}/[^&\s#]+)',
        decoded_url,
        re.IGNORECASE
    )
    if doi_param_match:
        return doi_param_match.group(1)

    # Pattern 3: DOI embedded in path (common in some publishers)
    # e.g., /article/10.1016/j.watres.2023.12345
    doi_path_match = re.search(
        r'/(?:article|doi|pdf)/(10\.\d{4,}/[^?\s#/]+(?:/[^?\s#/]+)?)',
        decoded_url,
        re.IGNORECASE
    )
    if doi_path_match:
        return doi_path_match.group(1)

    return None


async def _fetch_pubmed_metadata_via_api(pmid: Optional[str] = None, pmcid: Optional[str] = None) -> Optional[Dict[str, str]]:
    """
    Fetch metadata from NCBI E-utilities API.

    This is the RELIABLE way to get PubMed/PMC metadata since the web pages
    render content with JavaScript which static HTML parsing can't capture.

    Args:
        pmid: PubMed ID (e.g., "12345678")
        pmcid: PMC ID (e.g., "PMC1234567")

    Returns:
        Dict with title, author, date, doi or None if failed
    """
    if not pmid and not pmcid:
        return None

    try:
        # Use efetch to get article metadata in XML format
        base_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"

        if pmid:
            params = {"db": "pubmed", "id": pmid, "retmode": "xml"}
        else:
            # Convert PMCID to PMID first if needed
            params = {"db": "pmc", "id": pmcid.replace("PMC", ""), "retmode": "xml"}

        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(base_url, params=params)
            if response.status_code != 200:
                return None

            xml_content = response.text

            # Parse XML to extract metadata
            import re

            result = {}

            # FIX BUG 10: Handle BOTH PubMed AND PMC XML formats
            # PubMed uses: <ArticleTitle>, <LastName>/<ForeName>, <ArticleId IdType="doi">
            # PMC uses: <article-title>, <surname>/<given-names>, <article-id pub-id-type="doi">

            # Extract title - try PubMed format first, then PMC format
            title_match = re.search(r'<ArticleTitle>([^<]+)</ArticleTitle>', xml_content)
            if not title_match:
                title_match = re.search(r'<article-title>([^<]+)</article-title>', xml_content)
            if title_match:
                result["title"] = title_match.group(1).strip()

            # Extract authors - try PubMed format first
            authors = []
            # PubMed format: <Author><LastName>X</LastName><ForeName>Y</ForeName></Author>
            author_pattern = r'<Author[^>]*>.*?<LastName>([^<]+)</LastName>.*?(?:<ForeName>([^<]+)</ForeName>)?.*?</Author>'
            for match in re.finditer(author_pattern, xml_content, re.DOTALL):
                last_name = match.group(1)
                first_name = match.group(2) if match.group(2) else ""
                if first_name:
                    authors.append(f"{first_name} {last_name}")
                else:
                    authors.append(last_name)
                if len(authors) >= 3:
                    break

            # If no PubMed authors found, try PMC format
            if not authors:
                # PMC format: <contrib><name><surname>X</surname><given-names>Y</given-names></name></contrib>
                pmc_pattern = r'<surname>([^<]+)</surname>.*?(?:<given-names[^>]*>([^<]+)</given-names>)?'
                for match in re.finditer(pmc_pattern, xml_content, re.DOTALL):
                    surname = match.group(1)
                    given = match.group(2) if match.group(2) else ""
                    if given:
                        authors.append(f"{given} {surname}")
                    else:
                        authors.append(surname)
                    if len(authors) >= 3:
                        break

            if authors:
                if len(authors) > 2:
                    result["author"] = f"{authors[0]} et al."
                else:
                    result["author"] = ", ".join(authors)

            # Extract publication date - try multiple formats
            year_match = re.search(r'<PubDate>.*?<Year>(\d{4})</Year>', xml_content, re.DOTALL)
            if not year_match:
                year_match = re.search(r'<ArticleDate[^>]*>.*?<Year>(\d{4})</Year>', xml_content, re.DOTALL)
            if not year_match:
                # PMC format: <pub-date><year>XXXX</year></pub-date>
                year_match = re.search(r'<pub-date[^>]*>.*?<year>(\d{4})</year>', xml_content, re.DOTALL)
            if year_match:
                result["date"] = year_match.group(1)

            # Extract DOI - try PubMed format first, then PMC format
            doi_match = re.search(r'<ArticleId IdType="doi">([^<]+)</ArticleId>', xml_content)
            if not doi_match:
                doi_match = re.search(r'<article-id pub-id-type="doi">([^<]+)</article-id>', xml_content)
            if doi_match:
                result["doi"] = doi_match.group(1).strip()

            return result if result else None

    except Exception as e:
        logger.debug(f"NCBI API fetch failed: {e}")
        return None


def _fetch_pubmed_metadata_via_api_sync(pmid: Optional[str] = None, pmcid: Optional[str] = None) -> Optional[Dict[str, str]]:
    """Synchronous wrapper for _fetch_pubmed_metadata_via_api."""
    try:
        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(_fetch_pubmed_metadata_via_api(pmid, pmcid))
        finally:
            loop.close()
    except Exception:
        return None


# =============================================================================
# SOTA: OAI-PMH METADATA EXTRACTION
# =============================================================================

def _fetch_pmc_metadata_via_oaipmh(pmc_id: str) -> Optional[Dict[str, str]]:
    """
    SOTA: Fetch PMC metadata using OAI-PMH protocol.

    This is more reliable than E-utilities for title extraction because:
    1. OAI-PMH uses a standardized protocol with consistent output
    2. The article-title is always in a predictable location
    3. No confusion between <Title> (journal) and <ArticleTitle> (paper)

    Args:
        pmc_id: PMC ID (with or without "PMC" prefix)

    Returns:
        Dict with title, author, date, doi or None if failed
    """
    try:
        from sickle import Sickle
        from lxml import etree
    except ImportError:
        logger.debug("sickle/lxml not available for OAI-PMH - falling back to E-utilities")
        return None

    try:
        # Clean PMC ID
        pmc_id_clean = pmc_id.replace("PMC", "").strip()

        # Initialize OAI-PMH client for PMC
        oai_endpoint = "https://pmc.ncbi.nlm.nih.gov/oai/oai.fcgi"
        sickle = Sickle(oai_endpoint)

        # Construct OAI identifier
        oai_id = f"oai:pubmedcentral.nih.gov:{pmc_id_clean}"

        # Fetch record using 'pmc' metadata prefix (full JATS XML)
        record = sickle.GetRecord(identifier=oai_id, metadataPrefix='pmc')

        # Parse XML
        root = etree.fromstring(record.raw.encode('utf-8'))

        result = {}

        # Define namespace map for XPath
        nsmap = {
            'oai': 'http://www.openarchives.org/OAI/2.0/',
            'pmc': 'https://jats.nlm.nih.gov/ns/archiving/1.3/',
        }

        # Extract article-title - this is the CORRECT title
        # Try multiple XPath patterns for different JATS versions
        title_xpaths = [
            './/article-title',
            './/{https://jats.nlm.nih.gov/ns/archiving/1.3/}article-title',
            './/{http://dtd.nlm.nih.gov/ns/archiving/2.3/}article-title',
            './/{http://www.ncbi.nlm.nih.gov/entrez/query/DTD/pubmed_080101.dtd}ArticleTitle',
        ]

        for xpath in title_xpaths:
            try:
                title_elems = root.xpath(xpath)
                if title_elems:
                    title_text = etree.tostring(title_elems[0], method='text', encoding='unicode').strip()
                    if title_text and len(title_text) > 10:
                        result["title"] = title_text
                        break
            except Exception as xpath_err:
                logger.debug(f"[OAI-PMH] XPath pattern failed: {xpath_err}")
                continue

        # Fallback: search with local-name() which ignores namespaces
        if "title" not in result:
            try:
                title_elems = root.xpath('//*[local-name()="article-title"]')
                if title_elems:
                    title_text = etree.tostring(title_elems[0], method='text', encoding='unicode').strip()
                    if title_text and len(title_text) > 10:
                        result["title"] = title_text
            except Exception as fallback_err:
                logger.debug(f"[OAI-PMH] Fallback title extraction failed: {fallback_err}")

        # Extract authors
        authors = []
        try:
            # Find surname/given-names pairs
            surname_elems = root.xpath('//*[local-name()="surname"]')
            given_elems = root.xpath('//*[local-name()="given-names"]')

            for i, surname in enumerate(surname_elems[:3]):  # Limit to first 3 authors
                surname_text = surname.text or ""
                given_text = given_elems[i].text if i < len(given_elems) and given_elems[i].text else ""
                if given_text:
                    authors.append(f"{given_text} {surname_text}")
                else:
                    authors.append(surname_text)
        except Exception as author_err:
            logger.debug(f"[OAI-PMH] Author extraction failed: {author_err}")

        if authors:
            if len(authors) > 2:
                result["author"] = f"{authors[0]} et al."
            else:
                result["author"] = ", ".join(authors)

        # Extract publication year
        try:
            year_elems = root.xpath('//*[local-name()="year"]')
            for year_elem in year_elems[:3]:  # Check first few
                year_text = year_elem.text
                if year_text and year_text.isdigit() and 1900 < int(year_text) < 2100:
                    result["date"] = year_text
                    break
        except Exception as year_err:
            logger.debug(f"[OAI-PMH] Year extraction failed: {year_err}")

        # Extract DOI
        try:
            doi_elems = root.xpath('//*[local-name()="article-id"][@pub-id-type="doi"]')
            if doi_elems:
                result["doi"] = doi_elems[0].text
        except Exception as doi_err:
            logger.debug(f"[OAI-PMH] DOI extraction failed: {doi_err}")

        if result.get("title"):
            logger.debug(f"[OAI-PMH] Successfully extracted title for PMC{pmc_id_clean}: {result['title'][:50]}...")
            return result

        return None

    except Exception as e:
        logger.debug(f"[OAI-PMH] Failed for PMC{pmc_id}: {e}")
        return None


def fetch_pmc_title_sota(pmc_id: str) -> Optional[str]:
    """
    SOTA: Get PMC article title using fallback chain.

    Priority order:
    1. OAI-PMH (most reliable for article-title)
    2. E-utilities efetch API
    3. E-utilities esummary API

    Args:
        pmc_id: PMC ID (with or without "PMC" prefix)

    Returns:
        Article title or None
    """
    pmc_id_clean = pmc_id.replace("PMC", "").strip()

    # Method 1: OAI-PMH (SOTA - most reliable)
    oai_result = _fetch_pmc_metadata_via_oaipmh(pmc_id_clean)
    if oai_result and oai_result.get("title"):
        return oai_result["title"]

    # Method 2: E-utilities (existing fallback)
    eutils_result = _fetch_pubmed_metadata_via_api_sync(pmcid=pmc_id_clean)
    if eutils_result and eutils_result.get("title"):
        return eutils_result["title"]

    logger.warning(f"[SOTA] Failed to extract title for PMC{pmc_id_clean} via all methods")
    return None


@dataclass
class ExtractedMetadata:
    """Metadata extracted from HTML content."""
    title: str = ""
    author: str = ""
    publication_date: str = ""
    description: str = ""
    source_type: str = "web"
    doi: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "title": self.title,
            "author": self.author,
            "publication_date": self.publication_date,
            "description": self.description,
            "source_type": self.source_type,
            "doi": self.doi,
        }


def _is_pmc_garbage_title(title: str) -> bool:
    """
    Check if a title from PMC/PubMed is garbage.

    BUG-007 FIX: PMC pages sometimes return garbage titles like:
    - PMC article IDs (PMC1234567)
    - Section headers (References, Authors' contributions, Acknowledgements)
    - Generic text (Article from pmc.ncbi.nlm.nih.gov)

    Args:
        title: Title candidate to check

    Returns:
        True if title is garbage, False if valid
    """
    if not title:
        return True

    title_lower = title.lower().strip()

    # Check for PMC/PMID patterns
    if re.match(r'^pmc\d+$', title_lower):
        return True
    if re.match(r'^\d{7,8}$', title_lower):  # PMID
        return True

    # Check for common section headers (garbage)
    garbage_patterns = [
        r'^references?$',
        r'^acknowledgements?$',
        r'^authors?\s*contributions?$',
        r'^author\s*information$',
        r'^funding$',
        r'^conflict\s*of\s*interest',
        r'^supplementary',
        r'^abstract$',
        r'^introduction$',
        r'^methods?$',
        r'^results?$',
        r'^discussion$',
        r'^conclusion$',
        r'^article\s+from\s+',
        r'^untitled$',
        r'^unknown$',
    ]
    for pattern in garbage_patterns:
        if re.match(pattern, title_lower):
            return True

    # Too short to be a real title
    if len(title) < 10:
        return True

    return False


def _extract_pubmed_metadata(raw_html: str, url: str = "") -> ExtractedMetadata:
    """
    Extract metadata specifically from PubMed/PMC pages.

    PubMed pages have consistent structure with citation metadata.
    PRIORITY: citation_title meta tag is MOST RELIABLE for academic sources.

    Args:
        raw_html: HTML content from PubMed/PMC
        url: Source URL

    Returns:
        ExtractedMetadata populated from PubMed structure
    """
    metadata = ExtractedMetadata(source_type="academic")

    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(raw_html, "html.parser")

        # BUG-007 FIX: Prioritize citation_title meta tag FIRST
        # PMC pages have this reliably populated with the actual article title
        # HTML selectors like .article-title can contain garbage (section headers, etc.)

        # PRIORITY 1: citation_title meta tag (most reliable for PubMed/PMC)
        citation_title = soup.find("meta", attrs={"name": "citation_title"})
        if citation_title and citation_title.get("content"):
            candidate = citation_title["content"].strip()
            # Validate it's not garbage (PMC ID, section name, etc.)
            if candidate and not _is_pmc_garbage_title(candidate):
                metadata.title = candidate

        # PRIORITY 2: og:title (usually same as citation_title)
        if not metadata.title:
            og_title = soup.find("meta", attrs={"property": "og:title"})
            if og_title and og_title.get("content"):
                candidate = og_title["content"].strip()
                # Clean PMC suffix from og:title
                candidate = re.sub(r'\s*-\s*PMC\s*$', '', candidate)
                candidate = re.sub(r'\s*-\s*PubMed\s*$', '', candidate)
                if candidate and not _is_pmc_garbage_title(candidate):
                    metadata.title = candidate

        # PRIORITY 3: HTML title tag (clean it up)
        if not metadata.title:
            title_tag = soup.find("title")
            if title_tag:
                candidate = title_tag.get_text(strip=True)
                # Clean PMC/PubMed suffix
                candidate = re.sub(r'\s*-\s*PMC\s*$', '', candidate)
                candidate = re.sub(r'\s*-\s*PubMed\s*$', '', candidate)
                candidate = re.sub(r'\s*-\s*NCBI\s*$', '', candidate)
                if candidate and not _is_pmc_garbage_title(candidate):
                    metadata.title = candidate

        # PRIORITY 4: HTML selectors (fallback only)
        if not metadata.title:
            html_selectors = [
                "h1.heading-title",
                ".content-title h1",
                "article h1",
                ".article-title",
            ]
            for selector in html_selectors:
                elem = soup.select_one(selector)
                if elem:
                    candidate = elem.get_text(strip=True)
                    if candidate and not _is_pmc_garbage_title(candidate):
                        metadata.title = candidate
                        break

        # PubMed author patterns - citation_author (singular) is most reliable
        # FIX BUG 6: Was looking for "citation_authors" (plural) which doesn't exist
        # The actual meta tag is "citation_author" (singular) with multiple tags
        author_metas = soup.find_all("meta", attrs={"name": "citation_author"})
        if author_metas:
            author_list = [m.get("content", "").strip() for m in author_metas if m.get("content")]
            if len(author_list) > 2:
                metadata.author = f"{author_list[0]} et al."
            elif author_list:
                metadata.author = ", ".join(author_list[:2])
        else:
            # Fallback to author list in HTML
            author_selectors = [
                ".authors-list .author-name",
                ".contrib-group .contrib",
                "a.full-name",
                ".author-name",
                "[data-ga-action='author_link']",
            ]
            authors = []
            for selector in author_selectors:
                elems = soup.select(selector)
                if elems:
                    for elem in elems[:3]:  # Max 3 authors
                        name = elem.get_text(strip=True)
                        if name and len(name) < 50:  # Sanity check
                            authors.append(name)
                    break
            if authors:
                if len(authors) > 2:
                    metadata.author = f"{authors[0]} et al."
                else:
                    metadata.author = ", ".join(authors)

        # PubMed date patterns
        date_meta = soup.find("meta", attrs={"name": "citation_publication_date"})
        if date_meta and date_meta.get("content"):
            metadata.publication_date = date_meta["content"].strip()
        else:
            date_meta = soup.find("meta", attrs={"name": "citation_date"})
            if date_meta and date_meta.get("content"):
                metadata.publication_date = date_meta["content"].strip()
            else:
                # Look for date in page
                date_selectors = [".cit time", ".pubdate", ".epub-date"]
                for selector in date_selectors:
                    elem = soup.select_one(selector)
                    if elem:
                        metadata.publication_date = elem.get_text(strip=True)
                        break

        # DOI extraction
        doi_meta = soup.find("meta", attrs={"name": "citation_doi"})
        if doi_meta and doi_meta.get("content"):
            metadata.doi = doi_meta["content"].strip()

        # Description from abstract
        abstract_selectors = [
            "meta[name='description']",
            "meta[property='og:description']",
            ".abstract-content",
            "#abstract",
        ]
        for selector in abstract_selectors:
            if selector.startswith("meta"):
                elem = soup.select_one(selector)
                if elem and elem.get("content"):
                    metadata.description = elem["content"].strip()[:500]
                    break
            else:
                elem = soup.select_one(selector)
                if elem:
                    metadata.description = elem.get_text(strip=True)[:500]
                    break

    except ImportError:
        logger.debug("BeautifulSoup not available for PubMed extraction")
    except Exception as e:
        logger.debug(f"PubMed metadata extraction error: {e}")

    # SOTA: Use OAI-PMH for PMC and E-utilities for PubMed
    # OAI-PMH is more reliable for article-title extraction (no <Title>/<ArticleTitle> confusion)
    if not metadata.author or metadata.author == "Unknown" or metadata.author == extract_author_from_url(url):
        pmid = _extract_pmid_from_url(url)
        pmcid = _extract_pmcid_from_url(url)

        api_metadata = None

        # SOTA: Try OAI-PMH first for PMC IDs (most reliable for titles)
        if pmcid:
            try:
                api_metadata = _fetch_pmc_metadata_via_oaipmh(pmcid)
                if api_metadata:
                    logger.debug(f"[SOTA] Got metadata via OAI-PMH for PMC{pmcid}: {api_metadata.get('title', 'N/A')[:50]}...")
            except Exception as e:
                logger.debug(f"[SOTA] OAI-PMH failed for PMC{pmcid}: {e}")

        # Fallback to E-utilities if OAI-PMH didn't work
        if not api_metadata and (pmid or pmcid):
            try:
                api_metadata = _fetch_pubmed_metadata_via_api_sync(pmid, pmcid)
                if api_metadata:
                    logger.debug(f"Got metadata from E-utilities for {pmid or pmcid}")
            except Exception as e:
                logger.debug(f"E-utilities fallback failed: {e}")

        if api_metadata:
            # FIX: Replace title even if it's a fallback like "Article from..."
            if api_metadata.get("title"):
                if not metadata.title or metadata.title.startswith("Article from") or _is_pmc_garbage_title(metadata.title):
                    metadata.title = api_metadata["title"]
            if api_metadata.get("author"):
                metadata.author = api_metadata["author"]
            if api_metadata.get("date") and not metadata.publication_date:
                metadata.publication_date = api_metadata["date"]
            # FIX: Always use API DOI if available (most reliable)
            if api_metadata.get("doi"):
                metadata.doi = api_metadata["doi"]

    # Final fallback author to domain if still unknown (should rarely happen now)
    if not metadata.author or metadata.author == "Unknown":
        metadata.author = extract_author_from_url(url)

    return metadata


def _extract_doi_metadata(raw_html: str, url: str = "") -> ExtractedMetadata:
    """
    Extract metadata from DOI resolvers and academic publisher pages.

    Args:
        raw_html: HTML content
        url: Source URL

    Returns:
        ExtractedMetadata from publisher page
    """
    metadata = ExtractedMetadata(source_type="academic")

    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(raw_html, "html.parser")

        # Citation meta tags (standard for academic publishers)
        title_meta = soup.find("meta", attrs={"name": "citation_title"})
        if title_meta and title_meta.get("content"):
            metadata.title = title_meta["content"].strip()
        else:
            # Try DC.title (Dublin Core)
            dc_title = soup.find("meta", attrs={"name": "DC.title"})
            if dc_title and dc_title.get("content"):
                metadata.title = dc_title["content"].strip()

        # Authors from citation_author (can be multiple)
        author_metas = soup.find_all("meta", attrs={"name": "citation_author"})
        if author_metas:
            authors = [m.get("content", "").strip() for m in author_metas if m.get("content")]
            if len(authors) > 2:
                metadata.author = f"{authors[0]} et al."
            elif authors:
                metadata.author = ", ".join(authors)
        else:
            # Try DC.creator
            dc_creators = soup.find_all("meta", attrs={"name": "DC.creator"})
            if dc_creators:
                authors = [m.get("content", "").strip() for m in dc_creators if m.get("content")]
                if len(authors) > 2:
                    metadata.author = f"{authors[0]} et al."
                elif authors:
                    metadata.author = ", ".join(authors)

        # Date
        date_meta = soup.find("meta", attrs={"name": "citation_publication_date"})
        if date_meta and date_meta.get("content"):
            metadata.publication_date = date_meta["content"].strip()
        else:
            date_meta = soup.find("meta", attrs={"name": "DC.date"})
            if date_meta and date_meta.get("content"):
                metadata.publication_date = date_meta["content"].strip()

        # DOI - try meta tag first, then extract from URL
        doi_meta = soup.find("meta", attrs={"name": "citation_doi"})
        if doi_meta and doi_meta.get("content"):
            metadata.doi = doi_meta["content"].strip()
        else:
            # FIX: Use universal DOI extraction from URL
            url_doi = extract_doi_from_url(url)
            if url_doi:
                metadata.doi = url_doi

        # Description
        desc_meta = soup.find("meta", attrs={"name": "description"})
        if desc_meta and desc_meta.get("content"):
            metadata.description = desc_meta["content"].strip()[:500]

    except ImportError:
        logger.debug("BeautifulSoup not available for DOI extraction")
    except Exception as e:
        logger.debug(f"DOI metadata extraction error: {e}")

    # Fallback author to domain
    if not metadata.author or metadata.author == "Unknown":
        metadata.author = extract_author_from_url(url)

    return metadata


def extract_metadata_from_html(raw_html: str, url: str = "") -> ExtractedMetadata:
    """
    ISSUE C FIX: Extract comprehensive metadata from HTML.

    Extraction priority:
    1. Site-specific extraction (PubMed, PMC, DOI) - MOST RELIABLE for academic
    2. JSON-LD structured data
    3. Open Graph meta tags (og:title, og:author)
    4. Standard meta tags (author, description)
    5. HTML title tag
    6. URL slug as fallback

    Args:
        raw_html: Raw HTML content
        url: Source URL for fallback extraction

    Returns:
        ExtractedMetadata with title, author, date, etc.
    """
    metadata = ExtractedMetadata()

    if not raw_html:
        if url:
            metadata.title = extract_title_from_url(url)
            metadata.author = extract_author_from_url(url)
        return metadata

    # PRIORITY 0: Site-specific extraction for academic sources
    url_lower = url.lower() if url else ""

    if "pubmed.ncbi.nlm.nih.gov" in url_lower or "pmc.ncbi.nlm.nih.gov" in url_lower:
        # PubMed/PMC specific extraction
        pubmed_meta = _extract_pubmed_metadata(raw_html, url)
        if pubmed_meta.author and pubmed_meta.author != "Unknown":
            return pubmed_meta
        # Keep what we got and continue to fill gaps
        metadata = pubmed_meta
    elif "doi.org" in url_lower or "nature.com" in url_lower or "sciencedirect.com" in url_lower:
        # DOI/academic publisher extraction
        doi_meta = _extract_doi_metadata(raw_html, url)
        if doi_meta.author and doi_meta.author != "Unknown":
            return doi_meta
        metadata = doi_meta

    # Try Trafilatura first (best for metadata)
    if TRAFILATURA_AVAILABLE:
        try:
            # GH #1260: extract_metadata enters libxml2 → route through the ONE
            # SIGSEGV-guarded door (size gate + optional subprocess containment).
            from src.tools.access_bypass import safe_trafilatura_extract_metadata
            traf_meta = safe_trafilatura_extract_metadata(raw_html)
            if traf_meta:
                if not metadata.title:
                    metadata.title = traf_meta.title or ""
                if not metadata.author or metadata.author == "Unknown":
                    metadata.author = traf_meta.author or ""
                if traf_meta.date and not metadata.publication_date:
                    metadata.publication_date = str(traf_meta.date)
                if not metadata.description:
                    metadata.description = traf_meta.description or ""

                # If we got good results, return early
                if metadata.title and metadata.author and metadata.author != "Unknown":
                    return metadata
        except Exception as e:
            logger.debug(f"Trafilatura metadata extraction failed: {e}")

    # Parse with BeautifulSoup for detailed extraction
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(raw_html, "html.parser")

        # 1. JSON-LD extraction (highest priority)
        json_ld_scripts = soup.find_all("script", type="application/ld+json")
        for script in json_ld_scripts:
            try:
                import json
                ld_data = json.loads(script.string or "")

                # Handle both single object and array of objects
                if isinstance(ld_data, list):
                    ld_data = ld_data[0] if ld_data else {}

                # Extract title
                if not metadata.title:
                    metadata.title = (
                        ld_data.get("headline") or
                        ld_data.get("name") or
                        ld_data.get("title") or
                        ""
                    )

                # Extract author (can be string or object)
                if not metadata.author or metadata.author == "Unknown":
                    author_data = ld_data.get("author")
                    if isinstance(author_data, dict):
                        metadata.author = author_data.get("name", "")
                    elif isinstance(author_data, list) and author_data:
                        first_author = author_data[0]
                        if isinstance(first_author, dict):
                            metadata.author = first_author.get("name", "")
                        else:
                            metadata.author = str(first_author)
                    elif isinstance(author_data, str):
                        metadata.author = author_data

                # Extract date
                if not metadata.publication_date:
                    metadata.publication_date = (
                        ld_data.get("datePublished") or
                        ld_data.get("dateCreated") or
                        ld_data.get("dateModified") or
                        ""
                    )

                # Extract description
                if not metadata.description:
                    metadata.description = ld_data.get("description", "")

            except (json.JSONDecodeError, TypeError, KeyError) as e:
                # LOW-032: Log JSON-LD parsing error
                logger.debug(f"JSON-LD metadata parsing error: {e}")
                continue

        # 2. Open Graph meta tags
        if not metadata.title:
            og_title = soup.find("meta", property="og:title")
            if og_title and og_title.get("content"):
                metadata.title = og_title["content"].strip()

        if not metadata.author or metadata.author == "Unknown":
            # Try article:author first
            og_author = soup.find("meta", property="article:author")
            if og_author and og_author.get("content"):
                metadata.author = og_author["content"].strip()
            else:
                # Try og:author
                og_author = soup.find("meta", property="og:author")
                if og_author and og_author.get("content"):
                    metadata.author = og_author["content"].strip()

        if not metadata.publication_date:
            og_date = soup.find("meta", property="article:published_time")
            if og_date and og_date.get("content"):
                metadata.publication_date = og_date["content"].strip()

        if not metadata.description:
            og_desc = soup.find("meta", property="og:description")
            if og_desc and og_desc.get("content"):
                metadata.description = og_desc["content"].strip()

        # 3. Standard meta tags
        if not metadata.title:
            meta_title = soup.find("meta", attrs={"name": "title"})
            if meta_title and meta_title.get("content"):
                metadata.title = meta_title["content"].strip()

        if not metadata.author or metadata.author == "Unknown":
            meta_author = soup.find("meta", attrs={"name": "author"})
            if meta_author and meta_author.get("content"):
                metadata.author = meta_author["content"].strip()

        if not metadata.publication_date:
            meta_date = soup.find("meta", attrs={"name": "date"})
            if meta_date and meta_date.get("content"):
                metadata.publication_date = meta_date["content"].strip()

        if not metadata.description:
            meta_desc = soup.find("meta", attrs={"name": "description"})
            if meta_desc and meta_desc.get("content"):
                metadata.description = meta_desc["content"].strip()

        # 4. HTML title tag
        if not metadata.title:
            title_tag = soup.find("title")
            if title_tag and title_tag.string:
                metadata.title = title_tag.string.strip()
                # Clean up common suffixes like " | Site Name"
                if " | " in metadata.title:
                    metadata.title = metadata.title.split(" | ")[0].strip()
                if " - " in metadata.title:
                    metadata.title = metadata.title.split(" - ")[0].strip()

        # 5. Look for byline/author in common HTML patterns
        if not metadata.author or metadata.author == "Unknown":
            # Common byline patterns
            byline_selectors = [
                "[class*='byline']",
                "[class*='author']",
                "[rel='author']",
                "[itemprop='author']",
                ".author-name",
                ".post-author",
                ".article-author",
            ]
            for selector in byline_selectors:
                try:
                    byline = soup.select_one(selector)
                    if byline:
                        text = byline.get_text(strip=True)
                        # Clean up "By " prefix
                        text = re.sub(r"^by\s+", "", text, flags=re.IGNORECASE)
                        if text and len(text) < 100:  # Sanity check
                            metadata.author = text
                            break
                except (ValueError, SyntaxError):
                    continue

    except ImportError:
        logger.debug("BeautifulSoup not available for metadata extraction")
    except Exception as e:
        logger.warning(f"Metadata extraction error: {e}")

    # 6. URL fallbacks
    if not metadata.title:
        metadata.title = extract_title_from_url(url)

    if not metadata.author or metadata.author == "Unknown":
        metadata.author = extract_author_from_url(url)

    # Detect source type
    if url:
        url_lower = url.lower()
        if any(domain in url_lower for domain in [".gov", ".edu", "pubmed", "ncbi.nlm"]):
            metadata.source_type = "academic"
        elif url_lower.endswith(".pdf"):
            metadata.source_type = "pdf"
        else:
            metadata.source_type = "web"

    # FIX: Universal DOI extraction fallback - always try to extract DOI from URL
    if not metadata.doi and url:
        url_doi = extract_doi_from_url(url)
        if url_doi:
            metadata.doi = url_doi

    # BUG-008 FIX: Validate author field to reject garbage values
    # Catches "Username", "Contact X", domain names as author, etc.
    if metadata.author:
        validated_author = validate_author_field(metadata.author)
        if validated_author is None:
            # Author was garbage - fall back to domain-based author
            logger.debug(f"[BUG-008] Rejected garbage author: '{metadata.author}' for URL: {url[:50]}...")
            metadata.author = extract_author_from_url(url)
        else:
            metadata.author = validated_author

    # BUG-008 FIX: Normalize URL to canonical domain (restoredcdc.org -> cdc.gov)
    # This ensures citations point to authoritative sources
    # NOTE: We keep the original URL for fetching but use normalized for author extraction
    if url and metadata.author:
        normalized_url = normalize_url_domain(url)
        if normalized_url != url:
            # If URL was normalized, author might also need update
            normalized_author = extract_author_from_url(normalized_url)
            # Only replace if we get a better (institutional) author
            if normalized_author != "Unknown" and normalized_author != metadata.author:
                logger.debug(f"[BUG-008] Normalized author from '{metadata.author}' to '{normalized_author}'")
                metadata.author = normalized_author

    return metadata


def is_garbage_content(text: str) -> bool:
    """
    Detect if text content is likely garbage (binary, metadata, etc.).

    Args:
        text: Text to check

    Returns:
        True if content appears to be garbage
    """
    if not text or len(text) < 50:
        return True

    # Check for binary garbage patterns
    garbage_patterns = [
        r"[^\x00-\x7F]{10,}",  # Long sequences of non-ASCII
        r"[\x00-\x08\x0B\x0C\x0E-\x1F]{3,}",  # Control characters
        r"(?:stream|endstream|endobj|xref)",  # PDF internals
        r"JFIF|Exif|Adobe|ICC_PROFILE",  # Image metadata markers
        r"<rdf:RDF|xmlns:rdf",  # RDF/XML metadata
        r"(?:[A-Za-z0-9+/]{50,}={0,2})",  # Long base64 sequences
    ]

    for pattern in garbage_patterns:
        if re.search(pattern, text):
            return True

    # Check character distribution
    printable = sum(1 for c in text if c.isprintable() or c.isspace())
    if printable / len(text) < 0.8:
        return True

    return False


# =============================================================================
# USER AGENTS
# =============================================================================

USER_AGENTS = [
    # Chrome on Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    # Chrome on Mac
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    # Firefox on Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    # Safari on Mac
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
    # Edge on Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0",
    # Research bot (for academic sources)
    "Mozilla/5.0 (compatible; POLARIS/1.0; Research Bot; +https://github.com/polaris-research)",
]


def get_random_user_agent() -> str:
    """Get a random User-Agent string."""
    return random.choice(USER_AGENTS)


# =============================================================================
# FETCH RESULT
# =============================================================================

@dataclass
class FetchResult:
    """Result of a URL fetch operation."""
    url: str
    success: bool
    status_code: Optional[int] = None
    content: Optional[str] = None
    content_type: Optional[str] = None
    content_length: Optional[int] = None
    content_hash: Optional[str] = None
    error: Optional[str] = None
    elapsed_ms: Optional[float] = None
    final_url: Optional[str] = None  # After redirects

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "url": self.url,
            "success": self.success,
            "status_code": self.status_code,
            "content_type": self.content_type,
            "content_length": self.content_length,
            "content_hash": self.content_hash,
            "error": self.error,
            "elapsed_ms": self.elapsed_ms,
            "final_url": self.final_url,
        }


# =============================================================================
# CONTENT FETCHER
# =============================================================================

class ContentFetcher:
    """
    Robust content fetcher with retries and rate limiting.

    Features:
    - Automatic retries with exponential backoff
    - Per-domain rate limiting
    - User-Agent rotation
    - Configurable timeouts
    - Content hashing
    """

    def __init__(
        self,
        connect_timeout: float = 10.0,
        read_timeout: float = 30.0,
        max_retries: int = 3,
        max_content_size: int = 10 * 1024 * 1024,  # 10MB
        use_rate_limiter: bool = True,
    ):
        """
        Initialize content fetcher.

        Args:
            connect_timeout: Connection timeout in seconds
            read_timeout: Read timeout in seconds
            max_retries: Maximum retry attempts
            max_content_size: Maximum content size in bytes
            use_rate_limiter: Whether to use rate limiting
        """
        self.connect_timeout = connect_timeout
        self.read_timeout = read_timeout
        self.max_retries = max_retries
        self.max_content_size = max_content_size
        self.use_rate_limiter = use_rate_limiter

        # Load config overrides if available
        try:
            config = get_config()
            self.connect_timeout = config.search.fetching.connect_timeout
            self.read_timeout = config.search.fetching.read_timeout
            self.max_retries = config.search.fetching.max_retries
            self.max_content_size = config.search.fetching.max_content_size_mb * 1024 * 1024
        except (AttributeError, ImportError, FileNotFoundError):
            # Config not available, use constructor defaults
            logger.debug("Config not available, using default fetch settings")

        self._rate_limiter = get_rate_limiter() if use_rate_limiter else None

    def _get_domain(self, url: str) -> str:
        """Extract domain from URL."""
        parsed = urlparse(url)
        return parsed.netloc

    def _compute_hash(self, content: str) -> str:
        """Compute SHA256 hash of content."""
        return hashlib.sha256(content.encode("utf-8", errors="ignore")).hexdigest()

    async def _wait_for_rate_limit(self, domain: str) -> None:
        """Wait for rate limit if enabled."""
        if self._rate_limiter:
            await self._rate_limiter.acquire_async(domain, timeout=30.0)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type((httpx.TimeoutException, httpx.NetworkError)),
    )
    async def _fetch_with_retry(
        self,
        client: httpx.AsyncClient,
        url: str,
        headers: Dict[str, str],
    ) -> httpx.Response:
        """Fetch URL with retry logic."""
        response = await client.get(
            url,
            headers=headers,
            follow_redirects=True,
            timeout=httpx.Timeout(
                connect=self.connect_timeout,
                read=self.read_timeout,
                write=10.0,
                pool=5.0,
            ),
        )
        return response

    async def fetch(self, url: str, headers: Optional[Dict[str, str]] = None) -> FetchResult:
        """
        Fetch content from a URL.

        Args:
            url: URL to fetch
            headers: Optional custom headers

        Returns:
            FetchResult with content or error
        """
        domain = self._get_domain(url)
        start_time = asyncio.get_event_loop().time()

        # Rate limiting
        await self._wait_for_rate_limit(domain)

        # Prepare headers
        request_headers = {
            "User-Agent": get_random_user_agent(),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate",
            "Connection": "keep-alive",
        }
        if headers:
            request_headers.update(headers)

        try:
            async with httpx.AsyncClient() as client:
                response = await self._fetch_with_retry(client, url, request_headers)

                elapsed = (asyncio.get_event_loop().time() - start_time) * 1000

                # Check content size
                content_length = response.headers.get("content-length")
                if content_length and int(content_length) > self.max_content_size:
                    return FetchResult(
                        url=url,
                        success=False,
                        status_code=response.status_code,
                        error=f"Content too large: {content_length} bytes",
                        elapsed_ms=elapsed,
                        final_url=str(response.url),
                    )

                # Get content
                content = response.text

                # Truncate if needed
                if len(content) > self.max_content_size:
                    content = content[:self.max_content_size]
                    logger.warning(f"Truncated content from {url}")

                content_hash = self._compute_hash(content)
                content_type = response.headers.get("content-type", "unknown")

                logger.debug(f"Fetched {url}: {len(content)} bytes in {elapsed:.0f}ms")

                return FetchResult(
                    url=url,
                    success=response.status_code < 400,
                    status_code=response.status_code,
                    content=content,
                    content_type=content_type,
                    content_length=len(content),
                    content_hash=content_hash,
                    elapsed_ms=elapsed,
                    final_url=str(response.url),
                )

        except httpx.TimeoutException as e:
            elapsed = (asyncio.get_event_loop().time() - start_time) * 1000
            logger.warning(f"Timeout fetching {url}: {e}")
            return FetchResult(
                url=url,
                success=False,
                error=f"Timeout: {str(e)}",
                elapsed_ms=elapsed,
            )

        except httpx.NetworkError as e:
            elapsed = (asyncio.get_event_loop().time() - start_time) * 1000
            logger.warning(f"Network error fetching {url}: {e}")
            return FetchResult(
                url=url,
                success=False,
                error=f"Network error: {str(e)}",
                elapsed_ms=elapsed,
            )

        except Exception as e:
            elapsed = (asyncio.get_event_loop().time() - start_time) * 1000
            logger.error(f"Error fetching {url}: {e}")
            return FetchResult(
                url=url,
                success=False,
                error=f"Fetch error: {str(e)}",
                elapsed_ms=elapsed,
            )

    async def fetch_many(
        self,
        urls: List[str],
        max_concurrent: int = 10,
    ) -> List[FetchResult]:
        """
        Fetch multiple URLs concurrently.

        Args:
            urls: List of URLs to fetch
            max_concurrent: Maximum concurrent fetches

        Returns:
            List of FetchResults
        """
        semaphore = asyncio.Semaphore(max_concurrent)

        async def fetch_with_semaphore(url: str) -> FetchResult:
            async with semaphore:
                return await self.fetch(url)

        tasks = [fetch_with_semaphore(url) for url in urls]
        return await asyncio.gather(*tasks)


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

_fetcher: Optional[ContentFetcher] = None


def get_fetcher() -> ContentFetcher:
    """Get the singleton content fetcher."""
    global _fetcher
    if _fetcher is None:
        _fetcher = ContentFetcher()
    return _fetcher


async def fetch_url(url: str, headers: Optional[Dict[str, str]] = None) -> FetchResult:
    """
    Convenience function to fetch a URL.

    Args:
        url: URL to fetch
        headers: Optional custom headers

    Returns:
        FetchResult
    """
    fetcher = get_fetcher()
    return await fetcher.fetch(url, headers)


async def fetch_urls(urls: List[str], max_concurrent: int = 10) -> List[FetchResult]:
    """
    Convenience function to fetch multiple URLs.

    Args:
        urls: URLs to fetch
        max_concurrent: Maximum concurrent fetches

    Returns:
        List of FetchResults
    """
    fetcher = get_fetcher()
    return await fetcher.fetch_many(urls, max_concurrent)


# =============================================================================
# SELF-TEST
# =============================================================================

if __name__ == "__main__":
    import asyncio

    print("=" * 60)
    print("CONTENT INGESTION SELF-TEST")
    print("=" * 60)

    async def run_tests():
        # Test 1: Simple fetch
        print("\n[TEST 1] Simple fetch...")
        result = await fetch_url("https://httpbin.org/get")
        assert result.success is True
        assert result.status_code == 200
        assert result.content is not None
        assert result.content_hash is not None
        print(f"  [PASS] Fetched {result.content_length} bytes, hash: {result.content_hash[:16]}...")

        # Test 2: User-Agent rotation
        print("\n[TEST 2] User-Agent rotation...")
        ua1 = get_random_user_agent()
        ua2 = get_random_user_agent()
        ua3 = get_random_user_agent()
        # At least some should be different (probabilistic)
        agents = {ua1, ua2, ua3}
        print(f"  [PASS] Generated {len(agents)} unique User-Agents from 3 calls")

        # Test 3: Error handling (invalid URL)
        print("\n[TEST 3] Error handling...")
        result = await fetch_url("https://this-domain-definitely-does-not-exist-12345.com/")
        assert result.success is False
        assert result.error is not None
        print(f"  [PASS] Error caught: {result.error[:50]}...")

        # Test 4: Multiple URLs
        print("\n[TEST 4] Batch fetch...")
        urls = [
            "https://httpbin.org/get",
            "https://httpbin.org/headers",
            "https://httpbin.org/ip",
        ]
        results = await fetch_urls(urls, max_concurrent=3)
        success_count = sum(1 for r in results if r.success)
        print(f"  [PASS] Fetched {success_count}/{len(urls)} URLs successfully")

        # Test 5: Rate limiter integration
        print("\n[TEST 5] Rate limiter integration...")
        fetcher = ContentFetcher(use_rate_limiter=True)
        # Fetch same domain multiple times quickly
        for i in range(3):
            result = await fetcher.fetch("https://httpbin.org/delay/0")
            assert result.success is True
        print("  [PASS] Rate limiter allowed requests")

        # Test 6: FetchResult serialization
        print("\n[TEST 6] Result serialization...")
        result = await fetch_url("https://httpbin.org/get")
        result_dict = result.to_dict()
        assert "url" in result_dict
        assert "success" in result_dict
        assert "content_hash" in result_dict
        print(f"  [PASS] Serialized to dict with {len(result_dict)} keys")

        print("\n" + "=" * 60)
        print("ALL TESTS PASSED")
        print("=" * 60)

    asyncio.run(run_tests())
