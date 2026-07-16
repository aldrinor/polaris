"""Acceptance tests for the source-eligibility gate.

Fully offline: loads the champion corpus, runs the pure classifier, and asserts
the positive/negative host fixtures from the port spec. Known-bad publisher-of-
record hosts (Wikipedia, Morgan Stanley, WEF, OECD, ILO, NBER, IZA) must be
INELIGIBLE; known peer-reviewed journal hosts (PMC, ScienceDirect, AEA,
PubMed) must be ELIGIBLE. Also prints an eligibility summary (counts).

The classifier is a pure function of one row, so hosts that do not appear in
the corpus (morganstanley.com, weforum.org) are exercised with synthetic rows.
"""

import json
import os
from collections import Counter
from urllib.parse import urlparse

import pytest

from src.polaris_graph.instruction.source_eligibility import (
    classify_source,
    filter_eligible,
    is_enabled,
)

CORPUS_PATH = os.path.join(
    os.path.dirname(__file__),
    "..",
    "..",
    "data",
    "cp4_corpus_s3gear_329.json",
)

# Hosts the port spec pins as INELIGIBLE (non-journal publishers of record).
KNOWN_BAD_HOSTS = [
    "en.wikipedia.org",
    "morganstanley.com",
    "weforum.org",
    "oecd.org",
    "ilo.org",
    "nber.org",
    "docs.iza.org",
]

# Hosts the port spec pins as ELIGIBLE (peer-reviewed journal publishers).
KNOWN_JOURNAL_HOSTS = [
    "pmc.ncbi.nlm.nih.gov",
    "sciencedirect.com",
    "aeaweb.org",
    "pubmed.ncbi.nlm.nih.gov",
]


def _host(row):
    return urlparse(row.get("source_url") or "").netloc.lower().removeprefix("www.")


@pytest.fixture(scope="module")
def evidence():
    with open(CORPUS_PATH, encoding="utf-8") as fh:
        return json.load(fh)["evidence"]


def test_flag_default_off():
    """The integration flag is default-OFF (OFF path is byte-identical today)."""
    assert is_enabled() is False


def test_known_bad_hosts_ineligible(evidence):
    by_host = {}
    for row in evidence:
        by_host.setdefault(_host(row), []).append(row)

    for host in KNOWN_BAD_HOSTS:
        rows = by_host.get(host)
        if rows is None:
            # Not present in the corpus — exercise the pure function directly.
            rows = [{"source_url": f"https://www.{host}/report", "document_type": "UNKNOWN"}]
        for row in rows:
            result = classify_source(row)
            assert result["eligible"] is False, (
                f"{host} must be INELIGIBLE, got {result}"
            )
            assert result["source_class"] == "non_journal", (
                f"{host} expected non_journal, got {result}"
            )


def test_known_journal_hosts_eligible(evidence):
    by_host = {}
    for row in evidence:
        by_host.setdefault(_host(row), []).append(row)

    for host in KNOWN_JOURNAL_HOSTS:
        rows = by_host.get(host)
        assert rows, f"expected corpus rows for known-journal host {host}"
        for row in rows:
            result = classify_source(row)
            assert result["eligible"] is True, (
                f"{host} must be ELIGIBLE, got {result}"
            )
            assert result["source_class"] == "journal_article"
            assert result["language_ok"] is True


def test_tier_is_never_the_gate(evidence):
    """A T1 researchgate.net preprint mirror is ineligible; a lower-tier journal
    host is eligible — proving tier never admits/excludes (Rank12 defect)."""
    rg = {
        "source_url": "https://www.researchgate.net/publication/123",
        "document_type": "PREPRINT",
        "tier": "T1",
    }
    jour = {
        "source_url": "https://doi.org/10.1257/jep.33.2.3",
        "document_type": "JOURNAL_ARTICLE",
        "tier": "T4",
    }
    assert classify_source(rg)["eligible"] is False
    assert classify_source(jour)["eligible"] is True


def test_filter_eligible_partitions_all(evidence):
    eligible, rejected = filter_eligible(evidence)
    assert len(eligible) + len(rejected) == len(evidence)
    # No row appears in both partitions.
    assert all(classify_source(r)["eligible"] for r in eligible)
    assert all(not classify_source(r)["eligible"] for r in rejected)


def test_eligibility_summary(evidence, capsys):
    """Print the eligibility summary (counts) — informational, always passes."""
    eligible, rejected = filter_eligible(evidence)
    by_class = Counter(classify_source(r)["source_class"] for r in evidence)

    lines = [
        "",
        "=== SOURCE-ELIGIBILITY SUMMARY (champion corpus, 997 rows) ===",
        f"  TOTAL rows        : {len(evidence)}",
        f"  ELIGIBLE          : {len(eligible)}",
        f"  REJECTED          : {len(rejected)}",
        f"  by source_class   : {dict(by_class)}",
    ]
    with capsys.disabled():
        print("\n".join(lines))

    assert len(eligible) + len(rejected) == len(evidence)
    assert by_class["journal_article"] == len(eligible)
