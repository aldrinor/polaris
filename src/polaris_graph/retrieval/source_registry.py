"""Global Source Registry (v2 Loophole L1).

Assigns monotonic SRC-NNN IDs to every unique URL ONCE, before
parallel Section Writers begin. Prevents citation collision when
multiple sections cite the same source concurrently.

Thread-safe: uses threading.Lock for atomic ID assignment.

Usage:
    registry = SourceRegistry()
    sid = registry.register(url="https://...", title="...", source_type="web")
    # sid == "SRC-001"
    entry = registry.get("SRC-001")
    bib = registry.to_bibliography()
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger("polaris_graph")


@dataclass(frozen=True)
class SourceEntry:
    """Immutable record for a registered source."""

    source_id: str          # SRC-001, SRC-002, ...
    url: str
    title: str
    source_type: str        # web, academic, pdf, government, standard
    authors: list[str] = field(default_factory=list)
    year: Optional[int] = None
    venue: str = ""
    doi: str = ""
    domain: str = ""        # extracted from url for dedup
    authority_score: float = 0.0  # from source_confidence pipeline


class SourceRegistry:
    """Thread-safe global source registry.

    Guarantees:
        - Each URL gets exactly one SRC-NNN ID (idempotent register)
        - IDs are monotonically increasing
        - Safe for concurrent access from parallel section writers
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._by_url: dict[str, SourceEntry] = {}
        self._by_id: dict[str, SourceEntry] = {}
        self._counter: int = 0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def register(
        self,
        url: str,
        title: str = "",
        source_type: str = "web",
        authors: Optional[list[str]] = None,
        year: Optional[int] = None,
        venue: str = "",
        doi: str = "",
        authority_score: float = 0.0,
    ) -> str:
        """Register a source URL. Returns SRC-NNN (idempotent)."""
        normalized = self._normalize_url(url)
        with self._lock:
            if normalized in self._by_url:
                return self._by_url[normalized].source_id
            self._counter += 1
            sid = f"SRC-{self._counter:03d}"
            entry = SourceEntry(
                source_id=sid,
                url=url,
                title=title,
                source_type=source_type,
                authors=authors or [],
                year=year,
                venue=venue,
                doi=doi,
                domain=self._extract_domain(url),
                authority_score=authority_score,
            )
            self._by_url[normalized] = entry
            self._by_id[sid] = entry
            return sid

    def get(self, source_id: str) -> Optional[SourceEntry]:
        """Lookup by SRC-NNN ID."""
        return self._by_id.get(source_id)

    def get_by_url(self, url: str) -> Optional[SourceEntry]:
        """Lookup by URL."""
        return self._by_url.get(self._normalize_url(url))

    def contains_url(self, url: str) -> bool:
        """Check if URL already registered."""
        return self._normalize_url(url) in self._by_url

    @property
    def size(self) -> int:
        """Number of registered sources."""
        return self._counter

    def all_entries(self) -> list[SourceEntry]:
        """All entries in registration order."""
        return [self._by_id[f"SRC-{i:03d}"] for i in range(1, self._counter + 1)]

    def to_bibliography(self) -> list[dict]:
        """Export as bibliography list (for final report)."""
        bib = []
        for entry in self.all_entries():
            bib.append({
                "source_id": entry.source_id,
                "url": entry.url,
                "title": entry.title,
                "source_type": entry.source_type,
                "authors": entry.authors,
                "year": entry.year,
                "venue": entry.venue,
                "doi": entry.doi,
            })
        return bib

    def to_citation_map(self) -> dict[str, int]:
        """Map SRC-NNN -> sequential citation number [1], [2], etc."""
        return {
            f"SRC-{i:03d}": i
            for i in range(1, self._counter + 1)
        }

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    @staticmethod
    def _normalize_url(url: str) -> str:
        """Strip trailing slash, fragment, and lowercase for dedup."""
        url = url.split("#")[0].rstrip("/").lower()
        # Remove common tracking params
        if "?" in url:
            base, params = url.split("?", 1)
            clean_params = "&".join(
                p for p in params.split("&")
                if not p.startswith(("utm_", "ref=", "source="))
            )
            url = f"{base}?{clean_params}" if clean_params else base
        return url

    @staticmethod
    def _extract_domain(url: str) -> str:
        """Extract domain from URL."""
        try:
            from urllib.parse import urlparse
            return urlparse(url).netloc.lower()
        except Exception:
            return ""
