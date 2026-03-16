"""
POLARIS Domain Diversity Tests

Validates W1.2 Task: Source Diversity Enforcement
- Domain extraction from URLs
- Diversity capping (max results per domain)
- Diversity statistics calculation
- Low diversity warnings
"""

import pytest
import logging
from typing import List, Dict

logger = logging.getLogger(__name__)


class TestDomainExtraction:
    """Test URL domain extraction."""

    def test_basic_domain_extraction(self):
        """Test basic domain extraction from URLs."""
        from src.agents.search_agent import extract_domain_from_url

        test_cases = [
            ("https://www.example.com/page", "example.com"),
            ("https://example.com/page", "example.com"),
            ("http://subdomain.example.com/", "subdomain.example.com"),
            ("https://cdc.gov/disease/info", "cdc.gov"),
            ("https://www.nature.com/articles/123", "nature.com"),
        ]

        for url, expected_domain in test_cases:
            result = extract_domain_from_url(url)
            assert result == expected_domain, f"URL {url} -> {result}, expected {expected_domain}"

    def test_www_prefix_removal(self):
        """Test that www. prefix is removed."""
        from src.agents.search_agent import extract_domain_from_url

        assert extract_domain_from_url("https://www.google.com") == "google.com"
        assert extract_domain_from_url("https://google.com") == "google.com"

    def test_invalid_urls(self):
        """Test handling of invalid URLs."""
        from src.agents.search_agent import extract_domain_from_url

        # Should return empty string for invalid URLs
        assert extract_domain_from_url("") == ""
        assert extract_domain_from_url("not-a-url") == ""
        # Graph URLs extract the scheme-specific part as netloc (acceptable)
        # These are handled separately in diversity enforcement
        result = extract_domain_from_url("graph://entity/123")
        assert result == "entity"  # This is expected behavior from urlparse


class TestDiversityEnforcement:
    """Test domain diversity enforcement."""

    def test_caps_single_domain(self):
        """Test that results from a single domain are capped."""
        from src.agents.search_agent import enforce_domain_diversity

        # Create 20 results from same domain (cap is 10)
        results = [
            {"url": f"https://example.com/page{i}", "title": f"Page {i}"}
            for i in range(20)
        ]

        filtered = enforce_domain_diversity(results)

        # Should cap at 10 (config default)
        assert len(filtered) == 10, f"Expected 10 results, got {len(filtered)}"

    def test_preserves_diverse_results(self):
        """Test that diverse results are preserved."""
        from src.agents.search_agent import enforce_domain_diversity

        # Create results from 5 different domains (2 each)
        results = []
        for domain in ["a.com", "b.com", "c.com", "d.com", "e.com"]:
            results.append({"url": f"https://{domain}/page1", "title": f"{domain} 1"})
            results.append({"url": f"https://{domain}/page2", "title": f"{domain} 2"})

        filtered = enforce_domain_diversity(results)

        # All 10 should be preserved (none over cap)
        assert len(filtered) == 10, f"Expected 10 results, got {len(filtered)}"

    def test_mixed_diversity(self):
        """Test mixed scenario with some domains over cap."""
        from src.agents.search_agent import enforce_domain_diversity

        # Create 15 from domain A (will be capped), 5 from domain B (under cap)
        results = [
            {"url": f"https://domaina.com/page{i}", "title": f"A {i}"}
            for i in range(15)
        ]
        results.extend([
            {"url": f"https://domainb.com/page{i}", "title": f"B {i}"}
            for i in range(5)
        ])

        filtered = enforce_domain_diversity(results)

        # Should have 10 from A (capped) + 5 from B = 15
        assert len(filtered) == 15, f"Expected 15 results, got {len(filtered)}"

        # Count per domain
        domain_a_count = sum(1 for r in filtered if "domaina.com" in r["url"])
        domain_b_count = sum(1 for r in filtered if "domainb.com" in r["url"])

        assert domain_a_count == 10, f"Domain A count: {domain_a_count}, expected 10"
        assert domain_b_count == 5, f"Domain B count: {domain_b_count}, expected 5"

    def test_preserves_graph_results(self):
        """Test that graph results (without URLs) are preserved."""
        from src.agents.search_agent import enforce_domain_diversity

        results = [
            {"url": "graph://entity/123", "title": "Graph Entity 1"},
            {"url": "graph://entity/456", "title": "Graph Entity 2"},
            {"url": "https://example.com/page", "title": "Web Page"},
        ]

        filtered = enforce_domain_diversity(results)

        # All should be preserved (graph URLs don't extract to valid domains)
        assert len(filtered) == 3


class TestDiversityStatistics:
    """Test diversity statistics calculation."""

    def test_basic_statistics(self):
        """Test basic diversity statistics."""
        from src.agents.search_agent import get_domain_statistics

        results = [
            {"url": "https://a.com/1"},
            {"url": "https://a.com/2"},
            {"url": "https://b.com/1"},
            {"url": "https://c.com/1"},
        ]

        stats = get_domain_statistics(results)

        assert stats["total_results"] == 4
        assert stats["unique_domains"] == 3
        assert stats["max_single_domain_count"] == 2
        assert stats["max_single_domain"] == "a.com"
        assert stats["max_single_domain_pct"] == 0.5

    def test_empty_results(self):
        """Test statistics with empty results."""
        from src.agents.search_agent import get_domain_statistics

        stats = get_domain_statistics([])

        assert stats["total_results"] == 0
        assert stats["unique_domains"] == 0
        assert stats["diversity_score"] == 0

    def test_perfect_diversity(self):
        """Test statistics with perfect diversity (all unique domains)."""
        from src.agents.search_agent import get_domain_statistics

        results = [
            {"url": "https://a.com/"},
            {"url": "https://b.com/"},
            {"url": "https://c.com/"},
            {"url": "https://d.com/"},
        ]

        stats = get_domain_statistics(results)

        assert stats["unique_domains"] == 4
        assert stats["max_single_domain_count"] == 1
        assert stats["max_single_domain_pct"] == 0.25
        # Diversity score = unique/total = 4/4 = 1.0
        assert stats["diversity_score"] == 1.0


class TestDiversityConfiguration:
    """Test diversity configuration loading."""

    def test_config_loaded(self):
        """Test that diversity config is loaded."""
        from src.agents.search_agent import _DIVERSITY_CONFIG

        assert _DIVERSITY_CONFIG is not None
        assert "max_results_per_domain" in _DIVERSITY_CONFIG
        assert "enabled" in _DIVERSITY_CONFIG

    def test_config_values_reasonable(self):
        """Test that config values are reasonable."""
        from src.agents.search_agent import _DIVERSITY_CONFIG

        max_per_domain = _DIVERSITY_CONFIG.get("max_results_per_domain", 10)
        min_domains = _DIVERSITY_CONFIG.get("min_unique_domains", 15)

        assert 5 <= max_per_domain <= 50, f"max_results_per_domain {max_per_domain} out of range"
        assert 5 <= min_domains <= 100, f"min_unique_domains {min_domains} out of range"


class TestSOTACompliance:
    """Test SOTA compliance requirements for diversity."""

    def test_prevents_single_domain_dominance(self):
        """Test that single domain cannot exceed 25% threshold."""
        from src.agents.search_agent import enforce_domain_diversity, get_domain_statistics

        # Create scenario where one domain would dominate (50% without enforcement)
        results = [
            {"url": f"https://dominant.com/page{i}"} for i in range(50)
        ]
        results.extend([
            {"url": f"https://other{i}.com/page"} for i in range(50)
        ])

        filtered = enforce_domain_diversity(results)
        stats = get_domain_statistics(filtered)

        # After enforcement, dominant domain should be capped
        # With cap of 10 and 50 other domains, max_pct should be low
        assert stats["max_single_domain_pct"] <= 0.25, \
            f"Single domain dominance {stats['max_single_domain_pct']:.1%} exceeds 25%"

    def test_maintains_minimum_domains(self):
        """Test that results maintain reasonable domain diversity."""
        from src.agents.search_agent import enforce_domain_diversity, get_domain_statistics

        # Create diverse result set
        results = []
        for i in range(20):
            for j in range(3):
                results.append({"url": f"https://domain{i}.com/page{j}"})

        filtered = enforce_domain_diversity(results)
        stats = get_domain_statistics(filtered)

        # Should maintain good diversity
        assert stats["unique_domains"] >= 15, \
            f"Unique domains {stats['unique_domains']} below minimum 15"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
