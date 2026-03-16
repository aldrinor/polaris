#!/usr/bin/env python3
"""
POLARIS Geographic Tagger Module
=================================
Tags content with geographic metadata at ingestion time.

This module extracts geographic signals from:
1. URL/TLD (e.g., .gov = USA, .uk = UK)
2. Content text (country names, region keywords)
3. Regulatory body mentions (FDA = USA, EMA = EU)

Usage:
    from src.utils.geographic_tagger import GeographicTagger, tag_content_geography

    tagger = GeographicTagger()
    geo_meta = tagger.tag(url="https://epa.gov/water", text="EPA regulations in USA...")
    # Returns: {"region": "NORTH_AMERICA", "countries": ["United States"], "confidence": 0.85}
"""

import logging
import re
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple
from urllib.parse import urlparse

import yaml

logger = logging.getLogger(__name__)


# =============================================================================
# CONFIGURATION LOADING
# =============================================================================

def _load_geographic_config() -> dict:
    """Load geographic regions configuration."""
    config_path = Path(__file__).parent.parent.parent / "config" / "settings" / "geographic_regions.yaml"

    if config_path.exists():
        with open(config_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    else:
        # Fallback minimal config
        return {
            "regions": {
                "NORTH_AMERICA": {
                    "name": "North America",
                    "countries": ["United States", "Canada"],
                    "tlds": [".gov", ".edu", ".us", ".ca"],
                    "keywords": ["USA", "United States", "American", "Canada"],
                    "regulatory_bodies": ["FDA", "EPA", "CDC"],
                },
                "EUROPE": {
                    "name": "Europe",
                    "countries": ["United Kingdom", "Germany", "France"],
                    "tlds": [".uk", ".eu", ".de", ".fr"],
                    "keywords": ["Europe", "European", "EU", "UK"],
                    "regulatory_bodies": ["EMA", "EFSA"],
                },
                "ASIA_PACIFIC": {
                    "name": "Asia Pacific",
                    "countries": ["China", "Japan", "India", "Australia"],
                    "tlds": [".cn", ".jp", ".in", ".au"],
                    "keywords": ["Asia", "APAC", "China", "Japan", "India"],
                    "regulatory_bodies": ["NMPA", "PMDA", "TGA"],
                },
                "GLOBAL": {
                    "name": "Global",
                    "countries": [],
                    "tlds": [],
                    "keywords": ["global", "worldwide", "international"],
                    "regulatory_bodies": ["WHO", "ISO"],
                },
            }
        }


# =============================================================================
# GEOGRAPHIC TAGGER CLASS
# =============================================================================

class GeographicTagger:
    """
    Tags content with geographic metadata.

    Analyzes URLs and text content to determine geographic relevance.
    """

    def __init__(self):
        """Initialize the tagger with configuration."""
        self.config = _load_geographic_config()
        self.regions = self.config.get("regions", {})

        # Build lookup tables for fast matching
        self._build_lookup_tables()

    def _build_lookup_tables(self) -> None:
        """Build reverse lookup tables for efficient matching."""
        # TLD to region mapping
        self.tld_to_region: Dict[str, str] = {}
        for region_id, region_data in self.regions.items():
            for tld in region_data.get("tlds", []):
                self.tld_to_region[tld.lower()] = region_id

        # Regulatory body to region mapping
        self.regbody_to_region: Dict[str, str] = {}
        for region_id, region_data in self.regions.items():
            for body in region_data.get("regulatory_bodies", []):
                self.regbody_to_region[body.upper()] = region_id

        # Country to region mapping
        self.country_to_region: Dict[str, str] = {}
        for region_id, region_data in self.regions.items():
            for country in region_data.get("countries", []):
                self.country_to_region[country.lower()] = region_id

        # Keyword patterns per region (compiled regex)
        self.keyword_patterns: Dict[str, re.Pattern] = {}
        for region_id, region_data in self.regions.items():
            keywords = region_data.get("keywords", [])
            if keywords:
                # Build pattern with word boundaries
                pattern_str = r'\b(' + '|'.join(re.escape(kw) for kw in keywords) + r')\b'
                self.keyword_patterns[region_id] = re.compile(pattern_str, re.IGNORECASE)

    def extract_from_url(self, url: str) -> Tuple[Optional[str], float]:
        """
        Extract geographic signal from URL/TLD.

        Priority order:
        1. Authority domains (pubmed, WHO, etc.) -> GLOBAL
        2. Government TLDs (.gov, .gov.uk, etc.) -> Regional
        3. Country TLDs (.de, .fr, etc.) -> Regional

        Args:
            url: Source URL

        Returns:
            Tuple of (region_id, confidence)
        """
        if not url:
            return None, 0.0

        try:
            parsed = urlparse(url)
            domain = parsed.netloc.lower()

            # PRIORITY 1: Check for known authority domains FIRST (global sources)
            # These are always considered global regardless of TLD
            authority_domains = self.config.get("cross_regional", {}).get("authority_domains", [])
            for auth_domain in authority_domains:
                if auth_domain in domain:
                    return "GLOBAL", 0.70

            # PRIORITY 2: Check for government/educational TLDs (strong regional signal)
            if domain.endswith(".gov.uk"):
                return "EUROPE", 0.95
            if domain.endswith(".gov.au"):
                return "ASIA_PACIFIC", 0.95
            if domain.endswith(".gov"):
                return "NORTH_AMERICA", 0.95

            # PRIORITY 3: Check country-specific TLDs
            for tld, region in self.tld_to_region.items():
                if domain.endswith(tld):
                    return region, 0.80

        except (ValueError, AttributeError) as e:
            # HIGH-013: Log URL parsing error instead of silent pass
            logger.debug(f"URL parsing failed for geographic extraction: {url} - {e}")

        return None, 0.0

    def extract_from_text(self, text: str, max_chars: int = 5000) -> Dict[str, int]:
        """
        Extract geographic signals from text content.

        Args:
            text: Content text
            max_chars: Maximum characters to analyze

        Returns:
            Dict of region_id -> match count
        """
        if not text:
            return {}

        # Truncate for performance
        text_sample = text[:max_chars]
        region_counts: Dict[str, int] = {}

        # Check keyword patterns for each region
        for region_id, pattern in self.keyword_patterns.items():
            matches = pattern.findall(text_sample)
            if matches:
                region_counts[region_id] = len(matches)

        # Check regulatory body mentions (strong signal)
        for body, region in self.regbody_to_region.items():
            # Use word boundary for regulatory bodies
            body_pattern = rf'\b{re.escape(body)}\b'
            if re.search(body_pattern, text_sample, re.IGNORECASE):
                region_counts[region] = region_counts.get(region, 0) + 3  # Strong weight

        # Check country mentions
        text_lower = text_sample.lower()
        for country, region in self.country_to_region.items():
            if country in text_lower:
                region_counts[region] = region_counts.get(region, 0) + 2

        return region_counts

    def tag(
        self,
        url: str = "",
        text: str = "",
        title: str = "",
    ) -> Dict[str, any]:
        """
        Tag content with geographic metadata.

        Combines signals from URL and text to determine geographic relevance.

        Args:
            url: Source URL
            text: Content text
            title: Content title (also analyzed)

        Returns:
            Dict with keys:
            - region: Primary region ID (e.g., "NORTH_AMERICA")
            - region_name: Human-readable region name
            - countries: List of detected countries
            - confidence: Confidence score (0.0 to 1.0)
            - signals: Dict of individual signal contributions
        """
        signals = {}

        # Extract URL signal
        url_region, url_confidence = self.extract_from_url(url)
        if url_region:
            signals["url"] = {"region": url_region, "confidence": url_confidence}

        # Extract text signals
        combined_text = f"{title} {text}"
        text_counts = self.extract_from_text(combined_text)
        if text_counts:
            # Find dominant region from text
            max_region = max(text_counts.items(), key=lambda x: x[1])
            text_confidence = min(0.90, 0.40 + (max_region[1] * 0.10))  # Scale by count
            signals["text"] = {
                "region": max_region[0],
                "confidence": text_confidence,
                "counts": text_counts,
            }

        # Combine signals to determine primary region
        if not signals:
            # No geographic signals found
            return {
                "region": "GLOBAL",
                "region_name": "Global",
                "countries": [],
                "confidence": 0.30,
                "signals": {},
            }

        # Priority: URL signal > Text signal (URL is more reliable)
        if "url" in signals:
            primary_region = signals["url"]["region"]
            base_confidence = signals["url"]["confidence"]

            # Boost if text confirms URL
            if "text" in signals and signals["text"]["region"] == primary_region:
                base_confidence = min(1.0, base_confidence + 0.10)
        else:
            primary_region = signals["text"]["region"]
            base_confidence = signals["text"]["confidence"]

        # Get region metadata
        region_data = self.regions.get(primary_region, {})
        region_name = region_data.get("name", primary_region)

        # Extract detected countries
        detected_countries = []
        if "text" in signals:
            combined_lower = combined_text.lower()
            for country in region_data.get("countries", []):
                if country.lower() in combined_lower:
                    detected_countries.append(country)

        return {
            "region": primary_region,
            "region_name": region_name,
            "countries": detected_countries[:5],  # Limit to top 5
            "confidence": round(base_confidence, 2),
            "signals": signals,
        }

    def is_region_match(
        self,
        content_region: str,
        target_region: str,
        allow_global: bool = True,
    ) -> bool:
        """
        Check if content region matches target region.

        Args:
            content_region: Region detected in content
            target_region: Target region for the research
            allow_global: If True, GLOBAL content matches any target

        Returns:
            True if regions match
        """
        if content_region == target_region:
            return True

        if allow_global:
            # GLOBAL content matches any target
            if content_region == "GLOBAL":
                return True
            # Any content matches GLOBAL target
            if target_region == "GLOBAL":
                return True

        return False


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

# Singleton tagger instance
_tagger_instance: Optional[GeographicTagger] = None


def get_tagger() -> GeographicTagger:
    """Get or create singleton tagger instance."""
    global _tagger_instance
    if _tagger_instance is None:
        _tagger_instance = GeographicTagger()
    return _tagger_instance


def tag_content_geography(
    url: str = "",
    text: str = "",
    title: str = "",
) -> Dict[str, any]:
    """
    Tag content with geographic metadata.

    Convenience function using singleton tagger.

    Args:
        url: Source URL
        text: Content text
        title: Content title

    Returns:
        Geographic metadata dict
    """
    return get_tagger().tag(url=url, text=text, title=title)


def extract_region_from_vector_id(vector_id: str) -> str:
    """
    Extract target region from vector ID.

    Vector ID format: S1V1_Application_Name_REGION
    Example: S1V1_Household_Water_Filter_NORTH_AMERICA -> NORTH_AMERICA

    Args:
        vector_id: Vector ID string

    Returns:
        Region ID (e.g., "NORTH_AMERICA", "EUROPE", "GLOBAL")
    """
    # Known multi-word regions
    known_regions = {
        "NORTH_AMERICA", "SOUTH_AMERICA", "CENTRAL_AMERICA", "LATIN_AMERICA",
        "WESTERN_EUROPE", "EASTERN_EUROPE", "NORTHERN_EUROPE", "SOUTHERN_EUROPE",
        "SOUTH_ASIA", "EAST_ASIA", "SOUTHEAST_ASIA", "CENTRAL_ASIA", "WEST_ASIA",
        "NORTH_AFRICA", "SOUTH_AFRICA", "WEST_AFRICA", "EAST_AFRICA", "CENTRAL_AFRICA",
        "MIDDLE_EAST", "ASIA_PACIFIC", "SUB_SAHARAN_AFRICA",
        "GLOBAL", "WORLDWIDE", "INTERNATIONAL",
        "USA", "UK", "EU", "CHINA", "INDIA", "JAPAN", "KOREA", "BRAZIL",
        "CANADA", "MEXICO", "AUSTRALIA", "GERMANY", "FRANCE", "SPAIN", "ITALY",
        "EUROPE",
    }

    parts = vector_id.split("_")

    # Check for two-word regions (e.g., NORTH_AMERICA)
    if len(parts) >= 2:
        two_word = f"{parts[-2]}_{parts[-1]}"
        if two_word.upper() in known_regions:
            return two_word.upper()

    # Check for single-word regions
    if parts:
        one_word = parts[-1].upper()
        if one_word in known_regions:
            return one_word

    return "GLOBAL"


# =============================================================================
# SELF-TEST
# =============================================================================

if __name__ == "__main__":
    print("=" * 60)
    print("GEOGRAPHIC TAGGER MODULE SELF-TEST")
    print("=" * 60)

    tagger = GeographicTagger()

    # Test cases
    test_cases = [
        # URL-based detection
        {
            "url": "https://www.epa.gov/ground-water-and-drinking-water",
            "text": "The EPA sets standards for drinking water quality.",
            "expected_region": "NORTH_AMERICA",
        },
        {
            "url": "https://www.gov.uk/government/water-quality",
            "text": "UK government regulations on water treatment.",
            "expected_region": "EUROPE",
        },
        {
            "url": "https://www.tga.gov.au/therapeutic-goods",
            "text": "Australian TGA guidelines for water filters.",
            "expected_region": "ASIA_PACIFIC",
        },
        # Text-based detection
        {
            "url": "https://example.com/article",
            "text": "FDA regulations in the United States require water filters to meet safety standards. The EPA monitors water quality across American households.",
            "expected_region": "NORTH_AMERICA",
        },
        {
            "url": "https://example.com/eu-study",
            "text": "European Union EFSA guidelines establish water quality standards across EU member states including Germany, France, and the UK.",
            "expected_region": "EUROPE",
        },
        # Global/authority sources
        {
            "url": "https://pubmed.ncbi.nlm.nih.gov/12345678",
            "text": "A global study on water contamination patterns.",
            "expected_region": "GLOBAL",
        },
    ]

    print("\n[TEST] Geographic Tagging:")
    passed = 0
    failed = 0

    for i, case in enumerate(test_cases, 1):
        result = tagger.tag(url=case["url"], text=case["text"])
        status = "PASS" if result["region"] == case["expected_region"] else "FAIL"

        if status == "PASS":
            passed += 1
        else:
            failed += 1

        url_short = case["url"][:40] + "..." if len(case["url"]) > 40 else case["url"]
        print(f"\n  [{status}] Test {i}: {url_short}")
        print(f"         Expected: {case['expected_region']}, Got: {result['region']}")
        print(f"         Confidence: {result['confidence']}")
        if result.get("countries"):
            print(f"         Countries: {result['countries']}")

    print(f"\n[RESULTS] Passed: {passed}/{passed + failed}")

    # Test vector ID parsing
    print("\n[TEST] Vector ID Region Extraction:")
    vector_tests = [
        ("S1V1_Household_Water_Filter_NORTH_AMERICA", "NORTH_AMERICA"),
        ("S2V3_Industrial_Pump_EUROPE", "EUROPE"),
        ("S1V5_Water_Treatment_ASIA_PACIFIC", "ASIA_PACIFIC"),
        ("S3V1_Generic_Product_GLOBAL", "GLOBAL"),
    ]

    for vector_id, expected in vector_tests:
        result = extract_region_from_vector_id(vector_id)
        status = "PASS" if result == expected else "FAIL"
        print(f"  [{status}] {vector_id} -> {result} (expected: {expected})")

    print("\n" + "=" * 60)
    print("SELF-TEST COMPLETE")
    print("=" * 60)
