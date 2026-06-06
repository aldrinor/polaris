"""FX-13 (I-ready-017 #1125): _domain_of must use removeprefix, not lstrip.

`netloc.lower().lstrip("www.")` strips any leading char in the SET {w, .}, corrupting domains whose
name starts with w/. (www.who.int -> "ho.int", www.washington.edu -> "ashington.edu"). The fix uses
`removeprefix("www.")` (literal prefix). The domain feeds source-diversity dedup, so a corrupted
label mis-buckets sources. Offline, no network.
"""
from __future__ import annotations

from src.polaris_graph.retrieval.live_retriever import _domain_of


def test_www_prefix_stripped_literally_not_charset():
    # the exact cases the old lstrip bug corrupted:
    assert _domain_of("https://www.who.int/data") == "who.int"            # was "ho.int"
    assert _domain_of("https://www.washington.edu/x") == "washington.edu"  # was "ashington.edu"
    assert _domain_of("https://www.aeaweb.org/articles?id=1") == "aeaweb.org"
    assert _domain_of("https://www.nature.com/articles/x") == "nature.com"


def test_non_www_host_not_over_stripped():
    # a host whose name starts with 'w'/'www' but is NOT a literal www. prefix must be left intact.
    assert _domain_of("https://wwwhost.example.com/x") == "wwwhost.example.com"  # was "host.example.com"
    assert _domain_of("https://web.mit.edu/x") == "web.mit.edu"                  # 'w'+'e' — lstrip kept 'eb...'? prefix-safe now


def test_plain_host_and_subdomain_unchanged():
    assert _domain_of("https://pubs.aeaweb.org/doi/10.1257/x") == "pubs.aeaweb.org"
    assert _domain_of("https://arxiv.org/abs/2401.00001") == "arxiv.org"
    assert _domain_of("https://nber.org/papers/w12345") == "nber.org"


def test_bad_url_returns_empty():
    assert _domain_of("") == ""
    assert _domain_of("not a url") == ""  # no netloc
