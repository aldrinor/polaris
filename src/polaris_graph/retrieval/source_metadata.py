"""S2 source-metadata enrichment — populate DOI + journal/venue + re-tier from signals
ALREADY present in each evidence row (the direct_quote text, the source_url, the title).

This is the NATIVE, at-the-source version of the proven downstream repair
(``outline_agent/scripts/repair_corpus_metadata.py``): instead of a band-aid that runs after
the corpus is banked, S2 stamps correct metadata onto every kept evidence row as it screens
them, so every run produces a corpus whose provenance is CORRECT from the source.

Rule of law (CLAUDE.md §-1.3): weight-and-consolidate, NEVER filter/delete. This module only
POPULATES missing metadata and RE-TIERS on a CLEAR real signal (DOI present, known-journal
domain, gov/IGO domain). It NEVER downgrades a real tier, never deletes a row, never invents a
DOI/journal that is not literally present in the evidence. Deterministic, conservative, no LLM.

Downstream effect (by design): once ``doi`` is populated, ``finding_dedup._same_work_key`` keys
on it FIRST, so true duplicates (same paper fetched at different mirror URLs) MERGE naturally in
S3 consolidation as corroboration — no separate delete-as-filter path (§-1.3).
"""
from __future__ import annotations

import re
from typing import Any

# DOI: the canonical CrossRef pattern. Kept identical to the proven repair regex.
DOI_RE = re.compile(r'10\.\d{4,9}/[-._;()/:A-Za-z0-9]+')

# Defensible domain -> tier (project T1..T7 scale). Only assign on a CLEAR domain signal.
# T1-T2 = peer-reviewed journals / top working-paper series; T3-T4 = gov/central-bank/IGO/
# institutional; T5 = industry/consulting; T6-T7 = tertiary/blog/marketing.
DOMAIN_TIER: dict[str, str] = {
    # peer-reviewed journals & top academic (T1)
    'aeaweb.org': 'T1', 'sciencedirect.com': 'T1', 'link.springer.com': 'T1', 'cambridge.org': 'T1',
    'emerald.com': 'T1', 'nber.org': 'T1', 'onlinelibrary.wiley.com': 'T1', 'tandfonline.com': 'T1',
    'journals.sagepub.com': 'T1', 'academic.oup.com': 'T1', 'mdpi.com': 'T2', 'arxiv.org': 'T2',
    'papers.ssrn.com': 'T2', 'ideas.repec.org': 'T2', 'econstor.eu': 'T2', 'cepr.org': 'T2',
    'pmc.ncbi.nlm.nih.gov': 'T1', 'pubmed.ncbi.nlm.nih.gov': 'T1', 'revistes.ub.edu': 'T1',
    'econbiz.de': 'T2', 'siepr.stanford.edu': 'T2', 'economics.mit.edu': 'T2', 'nature.com': 'T1',
    # gov / central bank / IGO / institutional (T3-T4)
    'bls.gov': 'T3', 'congress.gov': 'T3', 'oecd.org': 'T3', 'imf.org': 'T3', 'ilo.org': 'T3',
    'openknowledge.worldbank.org': 'T3', 'newyorkfed.org': 'T3', 'federalreserve.gov': 'T3',
    'brookings.edu': 'T4', 'reports.weforum.org': 'T4', 'weforum.org': 'T4', 'whitehouse.gov': 'T3',
    # industry / consulting (T5)
    'goldmansachs.com': 'T5', 'mckinsey.com': 'T5', 'hbsp.harvard.edu': 'T5',
    'shrm-res.cloudinary.com': 'T5',
    # tertiary / blog / marketing (T6-T7)
    'en.wikipedia.org': 'T7', 'static1.squarespace.com': 'T6', 'ssir.org': 'T5', 'medium.com': 'T7',
}

# publisher/venue label by domain (for the journal field when the content doesn't name it).
DOMAIN_VENUE: dict[str, str] = {
    'aeaweb.org': 'American Economic Association', 'nber.org': 'NBER Working Paper',
    'papers.ssrn.com': 'SSRN', 'arxiv.org': 'arXiv', 'ideas.repec.org': 'RePEc',
    'econstor.eu': 'EconStor', 'cepr.org': 'CEPR',
    'congress.gov': 'Congressional Research Service', 'oecd.org': 'OECD', 'imf.org': 'IMF',
    'ilo.org': 'ILO', 'bls.gov': 'U.S. Bureau of Labor Statistics',
    'openknowledge.worldbank.org': 'World Bank', 'newyorkfed.org': 'Federal Reserve Bank of New York',
    'reports.weforum.org': 'World Economic Forum', 'weforum.org': 'World Economic Forum',
    'pmc.ncbi.nlm.nih.gov': 'PubMed Central', 'brookings.edu': 'Brookings Institution',
    'sciencedirect.com': 'Elsevier (ScienceDirect)', 'link.springer.com': 'Springer',
    'onlinelibrary.wiley.com': 'Wiley', 'tandfonline.com': 'Taylor & Francis',
    'journals.sagepub.com': 'SAGE', 'academic.oup.com': 'Oxford University Press',
    'cambridge.org': 'Cambridge University Press', 'nature.com': 'Nature',
    'mdpi.com': 'MDPI', 'federalreserve.gov': 'Federal Reserve',
}

# journal names commonly present in econ / AI-labor text -> use if literally found in the quote.
JOURNAL_PAT = re.compile(
    r'(Journal of [A-Z][A-Za-z ]+|Review of [A-Z][A-Za-z ]+|Quarterly Journal of [A-Za-z ]+|'
    r'American Economic Review|Econometrica|Research Policy|Labour Economics|'
    r'Technological Forecasting and Social Change|Nature[A-Za-z ]*)')

# Order tiers so a "known-journal domain" upgrade never overwrites an already-better/equal tier.
_TIER_RANK = {'T1': 1, 'T2': 2, 'T3': 3, 'T4': 4, 'T5': 5, 'T6': 6, 'T7': 7}


def domain_of(url: str) -> str:
    """The registrable-ish host (``www.`` stripped) from a full http(s) URL, else ''."""
    p = str(url or '').split('/')
    return p[2].replace('www.', '') if len(p) > 2 and str(url).startswith('http') else ''


def _clean_doi(doi: str) -> str:
    """Strip trailing sentence punctuation and an UNBALANCED trailing ')' the greedy DOI char
    class can over-capture from an inline '(doi:10.x/y)'. A DOI that legitimately contains a
    balanced '(...)' is preserved. Conservative: only trims the tail, never the id body."""
    d = str(doi or '').rstrip('.,;:')
    # drop a trailing ')' only when there is no matching '(' inside the captured id.
    while d.endswith(')') and d.count('(') < d.count(')'):
        d = d[:-1].rstrip('.,;:')
    return d


def extract_doi(quote: str, url: str) -> str:
    """The first DOI literally present in the quote text or the URL (tail punctuation cleaned)."""
    m = DOI_RE.search(str(quote or '')) or DOI_RE.search(str(url or ''))
    return _clean_doi(m.group(0)) if m else ''


def enrich_row_metadata(row: dict[str, Any], stats: dict[str, Any] | None = None) -> dict[str, Any]:
    """POPULATE ``doi`` / ``journal`` / ``tier`` on ``row`` IN PLACE from signals already present.

    Conservative & non-destructive:
      * ``doi``     — filled only if empty, from a DOI literally in ``direct_quote`` or the URL.
      * ``journal`` — filled only if empty, from a journal name literally in the text, else a
                      defensible domain->venue label.
      * ``tier``    — UPGRADED only from '' / 'UNKNOWN' on a CLEAR signal (has-DOI => >= T2, or a
                      known domain tier). NEVER downgrades a real tier; never touches T1..T7.

    Returns the same ``row`` object (mutated). ``stats`` (optional) accumulates counters.
    """
    if stats is None:
        stats = {}
    url = str(row.get('source_url') or row.get('url') or '')
    quote = str(row.get('direct_quote', '') or '')
    title = str(row.get('title', '') or '')
    dom = domain_of(url)

    # 1) DOI — only fill when empty; never overwrite an existing DOI.
    if not str(row.get('doi', '') or '').strip():
        doi = extract_doi(quote, url)
        if doi:
            row['doi'] = doi
            stats['doi_filled'] = stats.get('doi_filled', 0) + 1

    # 2) journal / venue — literal journal name first, then a defensible domain label.
    if not str(row.get('journal', '') or '').strip():
        jm = JOURNAL_PAT.search(quote) or JOURNAL_PAT.search(title)
        if jm:
            row['journal'] = jm.group(1).strip()
            stats['journal_filled'] = stats.get('journal_filled', 0) + 1
        elif dom in DOMAIN_VENUE:
            row['journal'] = DOMAIN_VENUE[dom]
            stats['journal_filled'] = stats.get('journal_filled', 0) + 1

    # 3) tier — only UPGRADE from '' / 'UNKNOWN' on a CLEAR signal; never downgrade a real tier.
    cur = str(row.get('tier') or '').strip()
    if cur in ('', 'UNKNOWN'):
        new = None
        if str(row.get('doi', '') or '').strip():
            # a DOI means a real registrable scholarly work: at least a paper (T2), or the
            # domain's own (possibly stronger) tier if we know it.
            new = DOMAIN_TIER.get(dom, 'T2')
        elif dom in DOMAIN_TIER:
            new = DOMAIN_TIER[dom]
        if new:
            row['tier'] = new
            row['tier_repaired'] = True
            stats['tier_reclassed'] = stats.get('tier_reclassed', 0) + 1
            tt = stats.setdefault('tier_to', {})
            tt[new] = tt.get(new, 0) + 1
    return row


def enrich_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Enrich a list of evidence rows in place; return the accumulated stats dict."""
    stats: dict[str, Any] = {'doi_filled': 0, 'journal_filled': 0, 'tier_reclassed': 0, 'tier_to': {}}
    for r in rows:
        if isinstance(r, dict):
            enrich_row_metadata(r, stats)
    return stats
