"""
POLARIS API Query Schemas - SOTA Multi-Source Retrieval
=========================================================
Pydantic schemas for academic API queries and responses.

These schemas standardize the interface between:
- P2 (Query Generation) -> P3 (Search Execution)
- API Clients (OpenAlex, S2, CrossRef, Unpaywall) -> P3
- Citation Chainer -> P3

References:
- GPT Blueprint: Phase 2-3 Multi-Source Ingestion
- Gemini Diagnostic: Section 2 Clean Metadata
"""

from datetime import UTC, datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, Field, field_validator


# =============================================================================
# ENUMS
# =============================================================================

class APISource(str, Enum):
    """Academic API source identifiers."""
    OPENALEX = "openalex"
    SEMANTIC_SCHOLAR = "semantic_scholar"
    CROSSREF = "crossref"
    UNPAYWALL = "unpaywall"
    PUBMED = "pubmed"
    SERPER = "serper"  # Web search fallback


class QueryType(str, Enum):
    """Type of query to execute."""
    KEYWORD = "keyword"          # Traditional keyword search
    SEMANTIC = "semantic"        # Semantic/embedding-based search
    DOI_LOOKUP = "doi_lookup"    # Direct DOI resolution
    CITATION = "citation"        # Citation chaining (forward/backward)
    AUTHOR = "author"            # Author-based search


class RegionCode(str, Enum):
    """Geographic region codes for filtering."""
    NORTH_AMERICA = "NORTH_AMERICA"
    EUROPE = "EUROPE"
    ASIA_PACIFIC = "ASIA_PACIFIC"
    GLOBAL = "GLOBAL"


class OAStatus(str, Enum):
    """Open Access status."""
    GOLD = "gold"      # Published in OA journal
    GREEN = "green"    # Repository version
    HYBRID = "hybrid"  # OA in subscription journal
    BRONZE = "bronze"  # Free but no license
    CLOSED = "closed"  # Paywalled


class PaperType(str, Enum):
    """Type of academic paper."""
    JOURNAL_ARTICLE = "journal-article"
    BOOK_CHAPTER = "book-chapter"
    CONFERENCE_PAPER = "conference-paper"
    PREPRINT = "preprint"
    REVIEW = "review"
    DATASET = "dataset"
    OTHER = "other"


# =============================================================================
# AUTHOR MODEL
# =============================================================================

class NormalizedAuthor(BaseModel):
    """
    Normalized author representation across all APIs.

    Validates author names to filter garbage values like:
    - "Username", "Contact X", "admin@site.com"
    - Domain names used as author names
    """
    given_name: Optional[str] = Field(None, description="First/given name")
    family_name: Optional[str] = Field(None, description="Last/family name")
    full_name: str = Field(..., description="Complete display name")
    orcid: Optional[str] = Field(None, description="ORCID identifier")
    affiliations: List[str] = Field(default_factory=list)
    source_api: Optional[APISource] = None

    @property
    def is_valid(self) -> bool:
        """Check if author appears to be a real person."""
        name = self.full_name.lower()

        # Reject domain patterns
        domain_patterns = [".com", ".org", ".net", ".edu", ".gov", ".io", ".ai"]
        if any(p in name for p in domain_patterns):
            return False

        # Reject contact patterns
        contact_patterns = ["contact", "username", "admin", "editor", "staff", "team"]
        if any(p in name for p in contact_patterns):
            return False

        # Reject email-like names
        if "@" in name:
            return False

        # Reject single lowercase words (likely usernames)
        if " " not in self.full_name and self.full_name.islower() and len(self.full_name) > 3:
            return False

        return True


# =============================================================================
# PAPER MODEL
# =============================================================================

class NormalizedPaper(BaseModel):
    """
    Normalized paper representation across all academic APIs.

    This is the canonical format that P3 produces and P4 consumes.
    """
    # Identifiers
    doi: Optional[str] = Field(None, description="Digital Object Identifier")
    openalex_id: Optional[str] = Field(None, description="OpenAlex work ID")
    s2_id: Optional[str] = Field(None, description="Semantic Scholar paper ID")
    pubmed_id: Optional[str] = Field(None, description="PubMed ID (PMID)")
    arxiv_id: Optional[str] = Field(None, description="arXiv ID")

    # Core metadata
    title: str = Field(..., min_length=1, description="Paper title")
    abstract: Optional[str] = Field(None, description="Abstract text")
    tldr: Optional[str] = Field(None, description="AI-generated summary (from S2)")

    # Authors
    authors: List[NormalizedAuthor] = Field(default_factory=list)

    # Publication info
    publication_date: Optional[str] = Field(None, description="YYYY-MM-DD format")
    year: Optional[int] = Field(None, ge=1900, le=2030)
    venue: Optional[str] = Field(None, description="Journal or conference name")
    publisher: Optional[str] = None
    paper_type: Optional[PaperType] = None

    # Citations
    citation_count: int = Field(default=0, ge=0)
    influential_citation_count: int = Field(default=0, ge=0, description="From S2")
    reference_count: int = Field(default=0, ge=0)
    referenced_dois: List[str] = Field(default_factory=list, description="DOIs this paper cites")
    citing_dois: List[str] = Field(default_factory=list, description="DOIs citing this paper")

    # Open Access
    is_open_access: bool = False
    oa_status: Optional[OAStatus] = None
    pdf_url: Optional[str] = None
    license: Optional[str] = None

    # Geographic metadata (for filtering)
    author_countries: List[str] = Field(
        default_factory=list,
        description="ISO 3166-1 alpha-2 country codes from author affiliations"
    )
    study_regions: List[str] = Field(
        default_factory=list,
        description="Regions mentioned in abstract/title"
    )

    # Source tracking
    source_api: APISource = Field(..., description="API that provided this paper")
    retrieval_timestamp: str = Field(
        default_factory=lambda: datetime.now(UTC).isoformat()
    )

    # Relevance scoring (computed by P4)
    relevance_score: float = Field(default=0.0, ge=0.0, le=1.0)
    geographic_relevance: float = Field(default=1.0, ge=0.0, le=1.0)

    @property
    def primary_id(self) -> str:
        """Return the best available identifier."""
        return self.doi or self.openalex_id or self.s2_id or self.title[:50]

    @property
    def author_string(self) -> str:
        """Return formatted author string for citation."""
        valid_authors = [a for a in self.authors if a.is_valid]
        if not valid_authors:
            return "Unknown"
        if len(valid_authors) == 1:
            return valid_authors[0].full_name
        elif len(valid_authors) == 2:
            return f"{valid_authors[0].full_name} & {valid_authors[1].full_name}"
        else:
            return f"{valid_authors[0].full_name} et al."

    @property
    def has_valid_metadata(self) -> bool:
        """Check if paper has minimum required metadata."""
        return bool(self.title) and bool(self.doi or self.openalex_id or self.s2_id)

    @field_validator('doi')
    @classmethod
    def normalize_doi(cls, v):
        """Normalize DOI format."""
        if v is None:
            return None
        # Remove common prefixes
        for prefix in ["https://doi.org/", "http://doi.org/", "doi.org/", "doi:"]:
            if v.startswith(prefix):
                v = v[len(prefix):]
        return v


# =============================================================================
# QUERY MODELS
# =============================================================================

class APIQuery(BaseModel):
    """
    Query to execute against academic APIs.

    Generated by P2, consumed by P3.
    """
    query_id: str = Field(..., description="Unique query identifier")
    query_text: str = Field(..., min_length=1, description="Search query string")
    query_type: QueryType = Field(default=QueryType.KEYWORD)

    # Target APIs (ordered by preference)
    target_apis: List[APISource] = Field(
        default_factory=lambda: [APISource.OPENALEX, APISource.SEMANTIC_SCHOLAR],
        description="APIs to query, in order of preference"
    )

    # Filters
    year_min: Optional[int] = Field(None, ge=1900, le=2030)
    year_max: Optional[int] = Field(None, ge=1900, le=2030)
    region_filter: Optional[RegionCode] = None
    open_access_only: bool = False
    fields_of_study: List[str] = Field(default_factory=list)

    # Pagination
    max_results: int = Field(default=50, ge=1, le=1000)
    offset: int = Field(default=0, ge=0)

    # Citation chaining params
    seed_dois: List[str] = Field(
        default_factory=list,
        description="DOIs to use as seeds for citation chaining"
    )
    chain_forward: bool = Field(default=True, description="Find papers citing seeds")
    chain_backward: bool = Field(default=True, description="Find papers cited by seeds")

    # Metadata
    bucket: str = Field(default="academic", description="Query bucket: academic, government, etc.")
    priority: int = Field(default=5, ge=1, le=10, description="1=highest, 10=lowest")


class DOIQuery(BaseModel):
    """Query for direct DOI resolution."""
    dois: List[str] = Field(..., min_length=1, description="DOIs to resolve")
    include_references: bool = Field(default=False, description="Also fetch references")
    include_citations: bool = Field(default=False, description="Also fetch citations")
    target_apis: List[APISource] = Field(
        default_factory=lambda: [
            APISource.CROSSREF,
            APISource.OPENALEX,
            APISource.UNPAYWALL
        ]
    )


class CitationQuery(BaseModel):
    """Query for citation chaining."""
    seed_papers: List[str] = Field(
        ...,
        min_length=1,
        description="DOIs or OpenAlex IDs of seed papers"
    )
    direction: str = Field(
        default="both",
        description="forward | backward | both"
    )
    max_depth: int = Field(default=1, ge=1, le=3)
    max_per_seed: int = Field(default=50, ge=1, le=500)
    year_min: Optional[int] = None
    year_max: Optional[int] = None
    region_filter: Optional[RegionCode] = None


# =============================================================================
# RESPONSE MODELS
# =============================================================================

class APIQueryResult(BaseModel):
    """
    Result from executing an APIQuery.

    Returned by P3 after multi-source retrieval.
    """
    query_id: str
    query_text: str
    papers: List[NormalizedPaper] = Field(default_factory=list)

    # Statistics
    total_results: int = Field(default=0, ge=0)
    results_by_api: Dict[str, int] = Field(default_factory=dict)

    # Execution details
    apis_queried: List[APISource] = Field(default_factory=list)
    apis_succeeded: List[APISource] = Field(default_factory=list)
    apis_failed: List[APISource] = Field(default_factory=list)
    execution_time_ms: int = Field(default=0, ge=0)

    # Errors
    errors: List[str] = Field(default_factory=list)


class MultiSourceResult(BaseModel):
    """
    Combined result from all P3 retrieval activities.

    This is the output of Phase 3 after executing all queries.
    """
    vector_id: str
    queries_executed: int = Field(default=0, ge=0)
    queries_successful: int = Field(default=0, ge=0)
    queries_failed: int = Field(default=0, ge=0)

    # Papers retrieved
    papers: List[NormalizedPaper] = Field(default_factory=list)
    unique_papers: int = Field(default=0, ge=0)
    papers_with_doi: int = Field(default=0, ge=0)
    papers_with_pdf: int = Field(default=0, ge=0)

    # By source
    papers_by_source: Dict[str, int] = Field(default_factory=dict)
    papers_from_citation_chaining: int = Field(default=0, ge=0)

    # Quality metrics
    avg_citation_count: float = Field(default=0.0, ge=0.0)
    papers_with_abstract: int = Field(default=0, ge=0)
    valid_author_rate: float = Field(default=0.0, ge=0.0, le=1.0)

    # Timestamps
    timestamp_start: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    timestamp_end: Optional[str] = None
    total_execution_time_ms: int = Field(default=0, ge=0)

    def compute_stats(self):
        """Compute aggregate statistics from papers list."""
        if not self.papers:
            return

        self.unique_papers = len(self.papers)
        self.papers_with_doi = sum(1 for p in self.papers if p.doi)
        self.papers_with_pdf = sum(1 for p in self.papers if p.pdf_url)
        self.papers_with_abstract = sum(1 for p in self.papers if p.abstract)

        # Papers by source
        for paper in self.papers:
            source = paper.source_api.value
            self.papers_by_source[source] = self.papers_by_source.get(source, 0) + 1

        # Average citation count
        citations = [p.citation_count for p in self.papers if p.citation_count > 0]
        if citations:
            self.avg_citation_count = sum(citations) / len(citations)

        # Valid author rate
        total_authors = 0
        valid_authors = 0
        for paper in self.papers:
            for author in paper.authors:
                total_authors += 1
                if author.is_valid:
                    valid_authors += 1
        if total_authors > 0:
            self.valid_author_rate = valid_authors / total_authors


# =============================================================================
# REGION MAPPING
# =============================================================================

REGION_ISO_CODES: Dict[RegionCode, List[str]] = {
    RegionCode.NORTH_AMERICA: ["US", "CA", "MX"],
    RegionCode.EUROPE: [
        "GB", "DE", "FR", "IT", "ES", "NL", "BE", "SE", "NO", "DK",
        "FI", "AT", "CH", "IE", "PT", "PL", "CZ", "GR", "HU", "RO"
    ],
    RegionCode.ASIA_PACIFIC: [
        "CN", "JP", "KR", "IN", "AU", "NZ", "SG", "MY", "TH", "ID",
        "PH", "VN", "TW", "HK"
    ],
    RegionCode.GLOBAL: [],  # No filter
}


def get_country_codes(region: RegionCode) -> List[str]:
    """Get ISO country codes for a region."""
    return REGION_ISO_CODES.get(region, [])


# =============================================================================
# EXPORTS
# =============================================================================

__all__ = [
    # Enums
    "APISource",
    "QueryType",
    "RegionCode",
    "OAStatus",
    "PaperType",

    # Models
    "NormalizedAuthor",
    "NormalizedPaper",
    "APIQuery",
    "DOIQuery",
    "CitationQuery",
    "APIQueryResult",
    "MultiSourceResult",

    # Helpers
    "REGION_ISO_CODES",
    "get_country_codes",
]
