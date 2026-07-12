#!/usr/bin/env python3
"""Repair corpus metadata: populate DOI + journal/publisher + re-tier from signals we ALREADY have
(the direct_quote text, the source_url, the title). Deterministic, conservative, non-destructive.

The bug this fixes: 992/995 rows had empty doi/journal and 253 were tier=UNKNOWN, even though the
source is clearly a peer-reviewed journal (e.g. Acemoglu-Restrepo JEP, DOI in the text). Good sources
were being mislabeled, which (a) makes the corpus look low-quality and (b) tanks instruction-following
on benchmarks that demand journal sources. We recover the metadata instead of re-fetching.

Rule of law (CLAUDE.md §-1.3): weight-and-consolidate, never filter. This only RE-LABELS tier and
FILLS missing metadata from evidence already present; it deletes nothing.
"""
import json, re, sys, collections, copy

SRC = "/home/polaris/wt/outline_agent/data/cp4_corpus_s3gear_329.json"
OUT = "/home/polaris/wt/outline_agent/data/cp4_corpus_s3gear_329.repaired.json"

DOI_RE = re.compile(r'10\.\d{4,9}/[-._;()/:A-Za-z0-9]+')

# Defensible domain -> (tier, publisher/venue-kind). Tiers per the project's T1(top primary) .. T7 scale.
# T1-T2 = peer-reviewed journals / top working-paper series; T3-T4 = gov/central-bank/IGO/institutional;
# T5 = industry/consulting; T6-T7 = tertiary/blog/marketing. Only assign on a CLEAR domain signal.
DOMAIN_TIER = {
    # peer-reviewed journals & top academic (T1)
    'aeaweb.org':'T1','sciencedirect.com':'T1','link.springer.com':'T1','cambridge.org':'T1',
    'emerald.com':'T1','nber.org':'T1','onlinelibrary.wiley.com':'T1','tandfonline.com':'T1',
    'journals.sagepub.com':'T1','academic.oup.com':'T1','mdpi.com':'T2','arxiv.org':'T2',
    'papers.ssrn.com':'T2','ideas.repec.org':'T2','econstor.eu':'T2','cepr.org':'T2',
    'pmc.ncbi.nlm.nih.gov':'T1','pubmed.ncbi.nlm.nih.gov':'T1','revistes.ub.edu':'T1',
    'econbiz.de':'T2','siepr.stanford.edu':'T2','economics.mit.edu':'T2','nature.com':'T1',
    # gov / central bank / IGO / institutional (T3-T4)
    'bls.gov':'T3','congress.gov':'T3','oecd.org':'T3','imf.org':'T3','ilo.org':'T3',
    'openknowledge.worldbank.org':'T3','newyorkfed.org':'T3','federalreserve.gov':'T3',
    'brookings.edu':'T4','reports.weforum.org':'T4','weforum.org':'T4','whitehouse.gov':'T3',
    # industry / consulting (T5)
    'goldmansachs.com':'T5','mckinsey.com':'T5','hbsp.harvard.edu':'T5','shrm-res.cloudinary.com':'T5',
    # tertiary / blog / marketing (T6-T7)
    'en.wikipedia.org':'T7','static1.squarespace.com':'T6','ssir.org':'T5','medium.com':'T7',
}
# publisher/venue label by domain (for the journal field when the content doesn't name it)
DOMAIN_VENUE = {
    'aeaweb.org':'American Economic Association','nber.org':'NBER Working Paper',
    'papers.ssrn.com':'SSRN','arxiv.org':'arXiv','ideas.repec.org':'RePEc','econstor.eu':'EconStor',
    'cepr.org':'CEPR','congress.gov':'Congressional Research Service','oecd.org':'OECD',
    'imf.org':'IMF','ilo.org':'ILO','bls.gov':'U.S. Bureau of Labor Statistics',
    'openknowledge.worldbank.org':'World Bank','newyorkfed.org':'Federal Reserve Bank of New York',
    'reports.weforum.org':'World Economic Forum','weforum.org':'World Economic Forum',
    'pmc.ncbi.nlm.nih.gov':'PubMed Central','brookings.edu':'Brookings Institution',
}
# journal names commonly present in econ/AI-labor text -> use if found in the quote
JOURNAL_PAT = re.compile(r'(Journal of [A-Z][A-Za-z ]+|Review of [A-Z][A-Za-z ]+|Quarterly Journal of [A-Za-z ]+|'
                         r'American Economic Review|Econometrica|Research Policy|Labour Economics|'
                         r'Technological Forecasting and Social Change|Nature[A-Za-z ]*)')

def dom_of(url):
    p = url.split('/')
    return p[2].replace('www.','') if len(p) > 2 and url.startswith('http') else ''

def repair_row(r, stats):
    url = str(r.get('source_url') or r.get('url') or '')
    quote = str(r.get('direct_quote','')); title = str(r.get('title',''))
    dom = dom_of(url)
    # 1) DOI
    if not str(r.get('doi','')).strip():
        m = DOI_RE.search(quote) or DOI_RE.search(url)
        if m: r['doi'] = m.group(0).rstrip('.'); stats['doi_filled'] += 1
    # 2) journal/venue
    if not str(r.get('journal','')).strip():
        jm = JOURNAL_PAT.search(quote) or JOURNAL_PAT.search(title)
        if jm: r['journal'] = jm.group(1).strip(); stats['journal_filled'] += 1
        elif dom in DOMAIN_VENUE: r['journal'] = DOMAIN_VENUE[dom]; stats['journal_filled'] += 1
    # 3) tier — only upgrade from UNKNOWN/empty on a CLEAR signal; never downgrade a real tier
    cur = str(r.get('tier') or '').strip()
    if cur in ('', 'UNKNOWN'):
        new = None
        if str(r.get('doi','')).strip(): new = DOMAIN_TIER.get(dom, 'T2')  # has DOI => at least a paper
        elif dom in DOMAIN_TIER: new = DOMAIN_TIER[dom]
        if new:
            r['tier'] = new; r['tier_repaired'] = True; stats['tier_reclassed'] += 1
            stats['tier_to'][new] += 1
    return r

def main():
    d = json.load(open(SRC))
    rows = []
    def walk(o):
        if isinstance(o, dict):
            if o.get('direct_quote') is not None and (o.get('source_url') or o.get('url')): rows.append(o)
            for v in o.values(): walk(v)
        elif isinstance(o, list):
            for x in o: walk(x)
    walk(d)

    before = collections.Counter(str(r.get('tier') or 'UNKNOWN') for r in rows)
    stats = {'doi_filled':0,'journal_filled':0,'tier_reclassed':0,'tier_to':collections.Counter()}
    for r in rows: repair_row(r, stats)
    after = collections.Counter(str(r.get('tier') or 'UNKNOWN') for r in rows)

    # dedup detection (report only — do NOT delete, per §-1.3)
    key = collections.Counter()
    for r in rows:
        k = (str(r.get('doi','')).strip() or str(r.get('source_url') or r.get('url') or '') or str(r.get('title',''))).lower()
        key[k] += 1
    dups = sum(c-1 for c in key.values() if c > 1)

    json.dump(d, open(OUT,'w'), indent=1)
    print("=== METADATA REPAIR ===")
    print(f"rows: {len(rows)}")
    print(f"DOI filled:        {stats['doi_filled']}")
    print(f"journal filled:    {stats['journal_filled']}")
    print(f"tier reclassified: {stats['tier_reclassed']}  -> {dict(stats['tier_to'])}")
    print(f"\nUNKNOWN before: {before.get('UNKNOWN',0)}   after: {after.get('UNKNOWN',0)}")
    print(f"tier dist AFTER: {dict(sorted(after.items()))}")
    print(f"\nduplicate rows detected (same doi/url/title): {dups} (reported, NOT deleted)")
    print(f"\nwrote repaired corpus -> {OUT}")

if __name__ == '__main__':
    main()
