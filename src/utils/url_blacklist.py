#!/usr/bin/env python3
"""
POLARIS URL Blacklist Module
============================
Centralized URL filtering for commercial, spam, and low-quality sources.

This module consolidates all URL blacklist patterns used across phases
to ensure consistent filtering at INGESTION (P3) rather than after fetching (P4).

Usage:
    from src.utils.url_blacklist import is_url_blacklisted, filter_blacklisted_urls

    # Check single URL
    if is_url_blacklisted("https://grandviewresearch.com/market"):
        print("URL is blacklisted")

    # Filter list of URLs
    clean_urls = filter_blacklisted_urls(urls)
"""

from typing import List, Optional, Set, Tuple
from urllib.parse import urlparse


# =============================================================================
# DOMAIN BLACKLISTS
# =============================================================================

# Market research spam sites - HARD REJECT
MARKET_RESEARCH_SPAM = {
    "grandviewresearch",
    "mordorintelligence",
    "researchnester",
    "marketresearch",
    "polarismarketresearch",
    "expertmarketresearch",
    "arizton",
    "statista.com",
    "technavio",
    "reportlinker",
    "marketsandmarkets",
    "businesswire.com/news/home",  # Press releases about market research
    "prnewswire.com",
    "globenewswire.com",
    "ibisworld",
    "euromonitor",
    "frost.com",  # Frost & Sullivan
}

# E-commerce and retail sites - HARD REJECT
ECOMMERCE_DOMAINS = {
    "amazon.com",
    "amazon.",  # All Amazon domains (amazon.co.uk, etc.)
    "alibaba",
    "ebay.com",
    "ebay.",
    "walmart.com",
    "homedepot.com",
    "lowes.com",
    "target.com",
    "costco.com",
    "wayfair.com",
    "overstock.com",
    "bestbuy.com",
    "wish.com",
    "etsy.com",
    "shopify.com/products",
}

# Social media sites - HARD REJECT
SOCIAL_MEDIA_DOMAINS = {
    "linkedin.com",
    "facebook.com",
    "twitter.com",
    "x.com",
    "instagram.com",
    "tiktok.com",
    "reddit.com",
    "quora.com",
    "pinterest.com",
    "youtube.com",
    "tumblr.com",
    "snapchat.com",
    "discord.com",
    "twitch.tv",
}

# SEO spam and affiliate sites - HARD REJECT
SEO_SPAM_DOMAINS = {
    "medium.com/",  # Note: trailing slash to allow "mediumspray.com" etc.
    "blog.",  # Blog subdomains
    "/blog/",  # Blog paths
    "buzzfeed.com",
    "huffpost.com",
    "dailymail.co.uk",
    "thespruce.com",
    "bobvila.com",
    "familyhandyman.com",
    "wikihow.com",
}

# Commercial filter vendor sites - HARD REJECT
# Note: Patterns should be specific enough not to match legitimate research URLs
FILTER_VENDOR_DOMAINS = {
    # Specific vendor domains
    "aquasana.com",
    "multipure.com",
    "springwellwater.com",
    "berkeywater.com",
    "berkeyfilters.com",
    "brita.com",
    "culligan.com",
    "pur.com",
    "zerowater.com",
    "lifestraw.com",
    "sawyer.com",
    "aquagear.com",
    "clearlyfilteredwater.com",
    "expresswater.com",
    "apecwater.com",  # APEC Water Systems
    "ispringfilter.com",  # iSpring
    "home-water-purifiers.com",
    "waterfiltersfast.com",
    "discountfilterstore.com",
    "filterwater.com",
    "waterfilterdirect.com",
    "mrcoffee.com",
    # Generic vendor domain patterns (more specific)
    "waterfilters.com",
    "waterfilter.com",
    "filterforyou.com",
    "filtersfast.com",
    "purewater.com",
    "cleanwater.com",
    "purifierstore.com",
}

# News and media sites (not primary research sources) - SOFT REJECT
NEWS_MEDIA_DOMAINS = {
    "news-medical.net",
    "medicalnewstoday.com",
    "healthline.com",
    "webmd.com",
    "mayoclinic.org/healthy-lifestyle",  # Not the research section
    "cnn.com/health",
    "bbc.com/news",
    "reuters.com",
    "apnews.com",
    "theguardian.com",
    "nytimes.com",
    "washingtonpost.com",
    "forbes.com",
    "businessinsider.com",
    "cnbc.com",
    "foxnews.com",
    "usatoday.com",
    "newsweek.com",
    "time.com",
}


# =============================================================================
# URL PATTERN BLACKLISTS
# =============================================================================

# SEO spam URL patterns - HARD REJECT
SEO_URL_PATTERNS = {
    "best-",
    "-reviews",
    "top-10",
    "top10",
    "buying-guide",
    "-vs-",
    "/compare/",
    "/deals/",
    "/discount",
    "/coupon",
    "/promo",
    "/affiliate",
    "/sponsored",
    "/partner/",
    "-buying-guide",
    "-guide-",
    "/buyers-guide",
    "/reviews/",
    "-review.html",
    "comparison",
}

# Commercial/shop URL patterns - HARD REJECT
COMMERCIAL_URL_PATTERNS = {
    "store.",
    "shop.",
    "/buy",
    "/product",
    "/cart",
    "/checkout",
    "/add-to-cart",
    "/order/",
    "/pricing",
    "/plans/",
    "?utm_",  # Marketing tracking params
    "/shop/",
    "/store/",
    "/products/",
}


# =============================================================================
# CONTENT BLACKLIST PHRASES
# =============================================================================

# SEO spam content phrases (for post-fetch filtering)
SEO_CONTENT_BLACKLIST = [
    "buying guide",
    "best reviews",
    "top 10",
    "affiliate",
    "sponsored post",
    "as an amazon associate",
    "buy now",
    "limited time offer",
    "discount code",
    "promo code",
    "shop now",
    "free shipping",
    "order now",
    "add to cart",
    "compare prices",
    "cheapest",
    "best deal",
    "market size",
    "cagr",
    "market forecast",
    "request a free sample",
    "download report",
    "market growth",
    "market share",
    "market analysis report",
    "industry report",
    "market research report",
    "billion by",  # "X billion by 2030"
    "million by",  # "X million by 2025"
]


# =============================================================================
# MAIN FUNCTIONS
# =============================================================================

def is_url_blacklisted(url: str, include_news: bool = True) -> Tuple[bool, str]:
    """
    Check if a URL is blacklisted.

    Args:
        url: URL to check
        include_news: If True, also reject news/media sites (default: True)

    Returns:
        Tuple of (is_blacklisted, reason)
        - is_blacklisted: True if URL should be rejected
        - reason: Human-readable reason for rejection (empty if not blacklisted)
    """
    if not url:
        return True, "empty_url"

    url_lower = url.lower()

    # Check market research spam
    for pattern in MARKET_RESEARCH_SPAM:
        if pattern in url_lower:
            return True, f"market_research_spam:{pattern}"

    # Check e-commerce
    for pattern in ECOMMERCE_DOMAINS:
        if pattern in url_lower:
            return True, f"ecommerce:{pattern}"

    # Check social media
    for pattern in SOCIAL_MEDIA_DOMAINS:
        if pattern in url_lower:
            return True, f"social_media:{pattern}"

    # Check SEO spam domains
    for pattern in SEO_SPAM_DOMAINS:
        if pattern in url_lower:
            return True, f"seo_spam_domain:{pattern}"

    # Check filter vendor sites
    for pattern in FILTER_VENDOR_DOMAINS:
        if pattern in url_lower:
            return True, f"filter_vendor:{pattern}"

    # Check SEO URL patterns
    for pattern in SEO_URL_PATTERNS:
        if pattern in url_lower:
            return True, f"seo_url_pattern:{pattern}"

    # Check commercial URL patterns
    for pattern in COMMERCIAL_URL_PATTERNS:
        if pattern in url_lower:
            return True, f"commercial_pattern:{pattern}"

    # Check news/media (optional)
    if include_news:
        for pattern in NEWS_MEDIA_DOMAINS:
            if pattern in url_lower:
                return True, f"news_media:{pattern}"

    return False, ""


def filter_blacklisted_urls(
    urls: List[str],
    include_news: bool = True,
    log_rejected: bool = True,
) -> Tuple[List[str], List[Tuple[str, str]]]:
    """
    Filter a list of URLs, removing blacklisted ones.

    Args:
        urls: List of URLs to filter
        include_news: If True, also reject news/media sites
        log_rejected: If True, print rejected URLs

    Returns:
        Tuple of (clean_urls, rejected_list)
        - clean_urls: URLs that passed the filter
        - rejected_list: List of (url, reason) tuples for rejected URLs
    """
    clean_urls = []
    rejected = []

    for url in urls:
        is_blacklisted, reason = is_url_blacklisted(url, include_news)
        if is_blacklisted:
            rejected.append((url, reason))
            if log_rejected:
                # Truncate URL for logging
                url_short = url[:60] + "..." if len(url) > 60 else url
                print(f"    [BLACKLIST] Rejected: {url_short} ({reason})")
        else:
            clean_urls.append(url)

    return clean_urls, rejected


def is_content_seo_spam(text: str) -> bool:
    """
    Check if content contains SEO spam phrases.

    Use this for post-fetch filtering when URL alone isn't sufficient.

    Args:
        text: Text content to check

    Returns:
        True if content appears to be SEO spam
    """
    if not text:
        return False

    text_lower = text.lower()
    for phrase in SEO_CONTENT_BLACKLIST:
        if phrase in text_lower:
            return True

    return False


def get_domain(url: str) -> str:
    """
    Extract domain from URL.

    Args:
        url: URL string

    Returns:
        Domain (e.g., "example.com")
    """
    try:
        parsed = urlparse(url)
        return parsed.netloc.lower()
    except (ValueError, AttributeError):
        return ""


def get_all_blacklist_patterns() -> Set[str]:
    """
    Get all blacklist patterns for inspection/testing.

    Returns:
        Set of all patterns across all blacklist categories
    """
    all_patterns = set()
    all_patterns.update(MARKET_RESEARCH_SPAM)
    all_patterns.update(ECOMMERCE_DOMAINS)
    all_patterns.update(SOCIAL_MEDIA_DOMAINS)
    all_patterns.update(SEO_SPAM_DOMAINS)
    all_patterns.update(FILTER_VENDOR_DOMAINS)
    all_patterns.update(NEWS_MEDIA_DOMAINS)
    all_patterns.update(SEO_URL_PATTERNS)
    all_patterns.update(COMMERCIAL_URL_PATTERNS)
    return all_patterns


# =============================================================================
# SELF-TEST
# =============================================================================

if __name__ == "__main__":
    print("=" * 60)
    print("URL BLACKLIST MODULE SELF-TEST")
    print("=" * 60)

    # Test URLs
    test_urls = [
        # Should be REJECTED
        ("https://www.grandviewresearch.com/industry-analysis/water-filter", True, "market_research"),
        ("https://www.amazon.com/water-filter-pitcher", True, "ecommerce"),
        ("https://www.linkedin.com/posts/water-quality", True, "social_media"),
        ("https://www.best-water-filter-reviews.com/top-10", True, "seo_pattern"),
        ("https://shop.brita.com/filters", True, "filter_vendor"),
        ("https://www.example.com/product/water-filter", True, "commercial_pattern"),
        ("https://news-medical.net/health/water-quality.aspx", True, "news_media"),
        ("https://www.aquasana.com/whole-house-filters", True, "filter_vendor"),
        # Should be ALLOWED
        ("https://www.epa.gov/ground-water-and-drinking-water", False, "government"),
        ("https://pubmed.ncbi.nlm.nih.gov/12345678", False, "academic"),
        ("https://www.cdc.gov/healthywater/drinking/home-water-treatment", False, "government"),
        ("https://awwa.org/resources/water-filter-research", False, "industry_org"),
        ("https://www.nature.com/articles/water-contamination-study", False, "academic_journal"),
        ("https://www.sciencedirect.com/science/article/filter-efficiency", False, "academic_journal"),
    ]

    print("\n[TEST] URL Blacklist Checks:")
    passed = 0
    failed = 0

    for url, expected_blacklisted, category in test_urls:
        is_blacklisted, reason = is_url_blacklisted(url)
        status = "PASS" if is_blacklisted == expected_blacklisted else "FAIL"

        if status == "PASS":
            passed += 1
        else:
            failed += 1

        expected_str = "REJECT" if expected_blacklisted else "ALLOW"
        actual_str = "REJECT" if is_blacklisted else "ALLOW"

        url_short = url[:50] + "..." if len(url) > 50 else url
        print(f"  [{status}] {url_short}")
        print(f"         Expected: {expected_str}, Got: {actual_str}")
        if reason:
            print(f"         Reason: {reason}")

    print(f"\n[RESULTS] Passed: {passed}/{passed+failed}")

    # Test content blacklist
    print("\n[TEST] Content SEO Spam Detection:")
    test_content = [
        ("This is a legitimate research paper about water quality.", False),
        ("BUYING GUIDE: Top 10 Best Water Filters of 2024", True),
        ("Market size is projected to reach $5 billion by 2030 with a CAGR of 8%", True),
        ("E. coli contamination rates in household filters were measured at 99.9%", False),
    ]

    for text, expected_spam in test_content:
        is_spam = is_content_seo_spam(text)
        status = "PASS" if is_spam == expected_spam else "FAIL"
        expected_str = "SPAM" if expected_spam else "CLEAN"
        actual_str = "SPAM" if is_spam else "CLEAN"
        text_short = text[:50] + "..." if len(text) > 50 else text
        print(f"  [{status}] \"{text_short}\" - Expected: {expected_str}, Got: {actual_str}")

    print("\n" + "=" * 60)
    print("SELF-TEST COMPLETE")
    print("=" * 60)
