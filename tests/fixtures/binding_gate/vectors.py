"""Deterministic fixtures for the P6 real-chain 12-vector binding-gate acceptance battery.

Every builder here emits ONLY structural furniture (version stamps in the vocabulary of the world, a
front-matter DOI line, a byline) and per-domain identifiers. NO rule under test is allowed to key on a
DOI, title, author, venue, or subject literal, so the four DOMAINS below carry completely unrelated
identifiers across four unrelated fields (clinical / legal / economics / CS); the acceptance test
parameterises vectors 1-11 over all four and asserts the STRUCTURAL result is identical for each.

Nothing binary is committed: the salvage vectors (4, 10) reuse the identity_metadata raw-artifact
builders (PDF/HTML/JATS) generated at call time.
"""
from __future__ import annotations

# A long, complete scholarly body. 120 repetitions clears the scholarly stub floor so completeness is
# never the reason a vector rejects (except where a vector deliberately tests incompleteness).
FILLER = ('This paper studies the question at length across many pages of careful analysis, '
          'reporting the design, the data and the estimates in full. ') * 120

# ── STRUCTURAL VERSION FURNITURE — the vocabulary of the world, never a subject or an identifier ──
JOURNAL_MASTHEAD = 'Some Learned Review, Volume 12, Number 3, 2020, Pages 45-67.'
ACCEPTED_STAMP   = 'Accepted manuscript. This is the author-accepted version.'
ACCEPTED_CITE    = 'The version of record appeared in the journal; cite the published article.'
WORKING_STAMP    = 'NBER Working Paper No. 25682'
PREPRINT_STAMP   = 'arXiv:2401.01234'

# A shared, DIGIT-bearing span. Canonicalisation never touches digits, so an exactly-shared span is
# exactly equal in two documents and a changed one is not (the correspondence vector, 9).
SHARED_SPAN = ('The estimated elasticity was 0.42 with a robust standard error of 0.06 across every '
               'specification we ran, and the point estimate did not move when controls were added.')

# A header made only of PDF glyph codes: ZERO readable words, so the identity window is unreadable and
# the reducer cannot bind on it (vectors 3 and 4). It is NOT a stranger's paper — it is a font failure.
GLYPH_HEADER = '(cid:12)(cid:5)(cid:99)(cid:7)(cid:41)(cid:3)(cid:88)(cid:76)(cid:11)(cid:29) ' * 12


#: Four unrelated Work identities. Every identifier/subject term differs; the STRUCTURE is held constant
#: so the acceptance test can prove the outcome is determined by typed structure, not by any label.
DOMAINS = [
    dict(id='clinical', doi='10.1056/clin-A', foreign_doi='10.1056/clin-STRANGER',
         title='A Randomised Trial of the Widget Regimen in Adults', authors=('Adams', 'Brown'),
         byline='By Alice Adams and Bob Brown', venue='New England Journal of Medicine',
         foreign_title='An Unrelated Cohort Analysis of the Gadget Protocol',
         foreign_byline='By Carla Carter and Dan Dupont',
         generic_title='Adult Trial Report'),
    dict(id='legal', doi='10.2307/legal-A', foreign_doi='10.2307/legal-STRANGER',
         title='On the Interpretation of the Contract Formation Doctrine', authors=('Reyes', 'Silva'),
         byline='By Ana Reyes and Ivo Silva', venue='Harvard Law Review',
         foreign_title='Concerning the Distinct Rule of Promissory Estoppel',
         foreign_byline='By Omar Farouk and Lena Vogt',
         generic_title='Doctrine Case Note'),
    dict(id='economics', doi='10.1086/econ-A', foreign_doi='10.1086/econ-STRANGER',
         title='Automation and the Structure of New Labour Tasks', authors=('Okoro', 'Tan'),
         byline='By Ngozi Okoro and Wei Tan', venue='Journal of Political Economy',
         foreign_title='Migration and the Composition of Regional Wages',
         foreign_byline='By Priya Nair and Sven Holt',
         generic_title='Labour Market Note'),
    dict(id='cs', doi='10.5555/cs-A', foreign_doi='10.5555/cs-STRANGER',
         title='A Transformer Architecture for Program Synthesis Tasks', authors=('Park', 'Vasquez'),
         byline='By Jin Park and Luis Vasquez', venue='NeurIPS Proceedings',
         foreign_title='A Recurrent Model for Automated Theorem Proving',
         foreign_byline='By Mei Chen and Karl Ober',
         generic_title='Synthesis System Report'),
]

DOMAINS_BY_ID = {d['id']: d for d in DOMAINS}


def scholarly_body(d, *, furniture='', doi='__self__', title=None, byline=None, span=None,
                   masthead=JOURNAL_MASTHEAD):
    """A complete scholarly body. `doi='__self__'` prints the domain's OWN requested DOI in the front
    matter (identity proven); pass a foreign DOI to make the bytes a stranger's paper. `furniture` is any
    structural version stamp; when supplied it vetoes the published masthead exactly as a repository
    deposit that carries both does."""
    doi = d['doi'] if doi == '__self__' else doi
    title = d['title'] if title is None else title
    byline = d['byline'] if byline is None else byline
    doiline = f'doi: {doi}\n' if doi else ''
    results = span or 'We estimate the effect is 0.2 units (standard error 0.05) across 722 sites.'
    return (f'{title}\n{byline}\n{furniture}\n{masthead} {doiline}'
            f'1. Introduction\n{FILLER}\n4. Results\n{results}\n')


def row(d, *, fulltext, doi=None, title=None, authors=None):
    """A corpus row that REQUESTS domain `d`'s identity, wrapping the given bytes."""
    return {'doi': d['doi'] if doi is None else doi,
            'title': d['title'] if title is None else title,
            'authors': list(d['authors'] if authors is None else authors),
            'venue': d['venue'], 'year': 2020, 'type': 'journal-article',
            'fulltext': fulltext, 'abstract': ''}
