"""I-deepfix-001 (item 13c) journal-registrant genre — offline RED→GREEN tests.

THE SCORE-DRAGGER: on the drb_72 "high-quality English-language journal articles only" run,
OpenAlex resolution returned little (autopsy U25: 0 OpenAlex candidates; discovery carried by
SemanticScholar/Serper), so the ONLY affirmative bibliographic signal on ~130 genuine
peer-reviewed journal articles was a resolved DOI. The prior narrow allowlist
(``_JOURNAL_DOI_REGISTRANT_PREFIXES`` = AEA / UChicago only) missed the mainstream registrants,
so Ecological Economics (Elsevier 10.1016), Social Forces (OUP 10.1093), Environment and
Planning A (SAGE 10.1068) and Work and Occupations (SAGE 10.1177) all fell to ``UNKNOWN``
(``is_journal_article`` TRUE for 0/791), dragging the disclosed credibility mean 0.56→0.28 and
falsely reporting zero journal articles on a journal-only question (autopsy U14).

THE FIX (``document_type_classifier.py`` only — the credibility_llm_tiering executor, the
faithfulness engine, and the fetch/breaker region are all untouched): recognize a canonical DOI
whose registrant is a KNOWN peer-reviewed JOURNAL publisher as affirmative journal evidence,
GUARDED by ``_is_book_doi`` so the mixed registrants' book/monograph/chapter DOIs are never
over-labeled; plus the OpenAlex ``is_peer_reviewed`` gold clause that mirrors the tier
classifier's already-approved U10 venue-authority exemption. §-1.3 WEIGHT-and-LABEL: this only
relabels a genuine journal and softens no source's display weight — nothing is dropped, and the
per-sentence faithfulness engine (strict_verify / NLI / 4-role / provenance / span-grounding) is
frozen. Offline: no GPU, no network, no paid LLM.

RED (pre-fix, verified against HEAD 8a81779c): every real-journal case below returned
``DocumentType.UNKNOWN`` (basis ``unresolved``). GREEN: they return ``JOURNAL_ARTICLE``.
"""
from __future__ import annotations

from src.polaris_graph.retrieval.document_type_classifier import (
    DocumentType,
    _is_book_doi,
    _is_non_journal_doi,
    classify_document_type,
    is_peer_reviewed_journal_article,
)

# Real drb_72 T1/T2 journal articles (from the banked live_corpus_dump), reproduced under the
# live U25 condition where the OpenAlex genre signal is ABSENT and only the DOI / doi.org or
# publisher /doi/ URL is present.
_REAL_JOURNALS = [
    # (url, doi, venue label)
    ("https://doi.org/10.1016/J.ECOLECON.2017.04.025", "10.1016/j.ecolecon.2017.04.025", "Ecological Economics / Elsevier"),
    ("https://doi.org/10.1093/SF/78.4.1509", "10.1093/sf/78.4.1509", "Social Forces / OUP"),
    ("https://doi.org/10.1068/a4412", "10.1068/a4412", "Environment and Planning A / SAGE"),
    ("https://journals.sagepub.com/doi/10.1177/0730888417720714", "", "Work and Occupations / SAGE (no doi field, /doi/ URL)"),
    ("https://doi.org/10.1177/0002716298559001007", "10.1177/0002716298559001007", "Annals AAPSS / SAGE"),
    ("https://www.tandfonline.com/doi/full/10.1080/17579961.2025.2593783", "", "Law, Innovation & Technology / T&F"),
    ("https://www.emerald.com/gkmc/article/doi/10.1108/GKMC-12-2024-0824/1296776/x", "10.1108/gkmc-12-2024-0824", "GKMC / Emerald"),
]

# Book / monograph / chapter DOIs on the SAME journal-dominant registrants — must NOT be journal.
_BOOK_DOIS = [
    ("https://doi.org/10.1016/B978-0-12-816088-6.00006-7", "10.1016/b978-0-12-816088-6.00006-7", "Elsevier book chapter"),
    ("https://link.springer.com/chapter/10.1007/978-3-031-37776-1_2", "10.1007/978-3-031-37776-1_2", "Springer book chapter"),
    ("https://doi.org/10.1093/oso/9780190931445.001.0001", "10.1093/oso/9780190931445.001.0001", "OUP monograph (oso)"),
    ("https://onlinelibrary.wiley.com/doi/10.1002/9781119081845", "10.1002/9781119081845", "Wiley book (ISBN DOI)"),
    ("https://doi.org/10.1017/CBO9781139226585", "10.1017/cbo9781139226585", "Cambridge book (CBO)"),
    ("https://link.springer.com/rwe/10.1007/978-1-4614-7883-6_810-1", "10.1007/978-1-4614-7883-6_810-1", "Springer reference work entry"),
]

# Registrants deliberately EXCLUDED (conference-heavy / preprint / dataset / working-paper /
# book publisher) — a genuine non-journal genre must never be over-labeled JOURNAL_ARTICLE.
_EXCLUDED = [
    ("https://doi.org/10.1109/ICSE.2019.00030", "10.1109/icse.2019.00030", "IEEE conference"),
    ("https://doi.org/10.1145/3292500.3330919", "10.1145/3292500.3330919", "ACM"),
    ("https://doi.org/10.3386/w27612", "10.3386/w27612", "NBER working paper"),
    ("https://doi.org/10.5281/zenodo.1234", "10.5281/zenodo.1234", "Zenodo dataset"),
    ("https://doi.org/10.4324/9781315066295", "10.4324/9781315066295", "Routledge book publisher"),
]


def test_real_journals_recovered_to_journal_article():
    """GREEN: the real drb_72 journals (OpenAlex genre absent) now classify as JOURNAL_ARTICLE via
    the book-guarded peer-reviewed registrant clause / the /doi/ URL DOI extraction."""
    fails = []
    for url, doi, label in _REAL_JOURNALS:
        dt, basis = classify_document_type(url=url, title="", doi=doi)
        if dt is not DocumentType.JOURNAL_ARTICLE:
            fails.append(f"{label}: {dt.value} (basis={basis}) — expected JOURNAL_ARTICLE")
        if is_peer_reviewed_journal_article(dt) is not True:
            fails.append(f"{label}: is_journal_article not True")
    assert not fails, "journal-recovery failures:\n  - " + "\n  - ".join(fails)


def test_book_dois_on_journal_registrants_never_journal():
    """Book-safety: the journal-dominant registrants also mint book/chapter DOIs; the
    ``_is_book_doi`` guard must keep every one of them OUT of the journal-positive class."""
    fails = []
    for url, doi, label in _BOOK_DOIS:
        dt, basis = classify_document_type(url=url, title="", doi=doi)
        if is_peer_reviewed_journal_article(dt):
            fails.append(f"{label}: mislabeled {dt.value} (basis={basis}) — a book must NOT be a journal article")
    assert not fails, "book-safety failures:\n  - " + "\n  - ".join(fails)


def test_is_book_doi_recognizes_book_patterns():
    """Direct book-DOI-suffix recognizer coverage (ISBN-embedded + publisher book slugs), and a
    journal DOI on the SAME registrant is NOT flagged as a book."""
    assert _is_book_doi("10.1016/b978-0-12-816088-6.00006-7")   # Elsevier B978 chapter
    assert _is_book_doi("10.1007/978-3-031-37776-1_2")          # Springer 978 chapter
    assert _is_book_doi("10.1002/9781119081845")               # Wiley ISBN DOI
    assert _is_book_doi("10.1017/cbo9781139226585")            # Cambridge CBO
    assert _is_book_doi("10.1093/oso/9780190931445.001.0001")  # OUP oso monograph
    # journal DOIs on the same registrants must NOT be flagged as books
    assert not _is_book_doi("10.1016/j.ecolecon.2017.04.025")
    assert not _is_book_doi("10.1093/sf/78.4.1509")
    assert not _is_book_doi("10.1002/soc4.70018")


def test_excluded_registrants_and_signalless_pages_not_journal():
    """Precision: conference/preprint/dataset/working-paper/book-publisher registrants and a
    signal-less scholarly-TITLED page stay non-journal (never 'not known-bad' promotion)."""
    fails = []
    for url, doi, label in _EXCLUDED:
        dt, basis = classify_document_type(url=url, title="A Study of X", doi=doi)
        if is_peer_reviewed_journal_article(dt):
            fails.append(f"{label}: over-labeled {dt.value} (basis={basis})")
    # signal-less scam page: scholarly title but no DOI, no OpenAlex signal
    dt, basis = classify_document_type(url="https://scholarly-sounding.example/x", title="A Randomized Study of X")
    if dt is not DocumentType.UNKNOWN:
        fails.append(f"signal-less page: {dt.value} (basis={basis}) — expected UNKNOWN")
    assert not fails, "precision failures:\n  - " + "\n  - ".join(fails)


def test_codex_precision_holes_closed():
    """Codex diff-gate iter-1 findings, regression-locked:
      P1-a OUP reference/book slugs (acref/oso/acprof/oxfordhb/obo/actrade) never journal;
      P1-b a predatory-OA venue with EMPTY pub-type (U25 condition) + a journal-registrant DOI is
           PREDATORY_OA_JOURNAL, never laundered to JOURNAL_ARTICLE;
      P2-a a bare/malformed registrant DOI with no article suffix never promotes."""
    fails = []
    # P1-a: OUP reference / book platform DOIs on the (now broadly promoted) 10.1093 registrant
    oup_books = [
        "10.1093/acref/9780192806871.001.0001",   # Oxford Reference
        "10.1093/acrefore/9780190228637.013.1",   # Oxford Research Encyclopedias
        "10.1093/oso/9780190931445.001.0001",      # Oxford Scholarship Online
        "10.1093/oxfordhb/9780199234523.001.0001", # Oxford Handbooks
        "10.1093/obo/9780199756384-0001",          # Oxford Bibliographies
    ]
    for d in oup_books:
        if not _is_book_doi(d):
            fails.append(f"_is_book_doi missed OUP book/reference DOI {d}")
        dt, basis = classify_document_type(url=f"https://doi.org/{d}", doi=d, title="")
        if is_peer_reviewed_journal_article(dt):
            fails.append(f"OUP book/reference {d} mislabeled {dt.value} (basis={basis})")
    # P1-b: predatory OA, empty pub-type, journal-registrant DOI => PREDATORY, not JOURNAL
    dt, basis = classify_document_type(
        predatory_oa=True, openalex_publication_type="",
        url="https://www.ewadirect.com/proceedings/x", doi="10.1016/j.fake.2024.01.001",
    )
    if dt is not DocumentType.PREDATORY_OA_JOURNAL:
        fails.append(f"predatory+empty-pt+journal-DOI -> {dt.value} (basis={basis}); expected PREDATORY_OA_JOURNAL")
    # predatory OA also wins over the peer_reviewed gold clause
    dt, _ = classify_document_type(predatory_oa=True, openalex_is_peer_reviewed=True,
                                   openalex_publication_type="", url="https://x.example/p")
    if dt is not DocumentType.PREDATORY_OA_JOURNAL:
        fails.append("predatory+peer_reviewed -> not PREDATORY_OA_JOURNAL")
    # P2-a: bare registrant DOI (no article suffix) must NOT promote to journal
    for bare in ("10.1016", "10.1093", "10.1177"):
        dt, basis = classify_document_type(url=f"https://doi.org/{bare}", doi=bare, title="")
        if is_peer_reviewed_journal_article(dt):
            fails.append(f"bare registrant {bare} over-promoted to {dt.value} (basis={basis})")
    assert not fails, "precision-hole regressions:\n  - " + "\n  - ".join(fails)


def test_isbn10_books_and_procedia_not_journal():
    """Codex diff-gate iter-2 P1: non-978 book/proceedings families on the newly-trusted mixed
    registrants stay OUT of the journal-positive class, while a real article DOI on the SAME
    registrant is still recovered."""
    fails = []
    non_journal = [
        ("10.1007/0-387-95452-8_5", "Springer ISBN-10 book chapter (0-)"),
        ("10.1007/3-540-44581-1_5", "Springer ISBN-10 book chapter (3-)"),
        ("10.1002/0470011815.b2a10001", "Wiley ISBN-10 book (047…)"),
        ("10.1002/9781119081845.ch2", "Wiley ISBN-13 book"),
        ("10.1017/9781139226585.004", "Cambridge ISBN-13 book"),
        ("10.1057/9780230295704_3", "Palgrave ISBN book chapter"),
        ("10.1016/j.procs.2015.06.104", "Elsevier Procedia Computer Science (conference)"),
        ("10.1016/j.sbspro.2014.01.1234", "Elsevier Procedia Social & Behavioral (conference)"),
        ("10.1016/j.matpr.2020.05.678", "Materials Today: Proceedings (conference)"),
        ("10.1016/j.procir.2019.03.045", "Elsevier Procedia CIRP (conference)"),
        ("10.1016/j.egypro.2017.03.123", "Energy Procedia (conference)"),
        ("10.1016/j.ifacol.2019.12.493", "IFAC-PapersOnLine (conference)"),
        ("10.1108/S1479-361X20200000025004", "Emerald book series (S-ISSN)"),
        ("10.1093/0195101138.001.0001", "OUP raw ISBN-10 book DOI"),
    ]
    for d, label in non_journal:
        if not _is_non_journal_doi(d):
            fails.append(f"_is_non_journal_doi missed {label}: {d}")
        dt, basis = classify_document_type(url=f"https://doi.org/{d}", doi=d, title="")
        if is_peer_reviewed_journal_article(dt):
            fails.append(f"{label} mislabeled {dt.value} (basis={basis})")
    # real article DOIs on the SAME registrants are still recovered (journal DOIs begin with a letter)
    still_journal = [
        ("10.1007/s10551-018-3862-x", "Springer journal (Journal of Business Ethics)"),
        ("10.1002/hbe2.195", "Wiley journal (Human Behavior & Emerging Technologies)"),
        ("10.1016/j.ecolecon.2017.04.025", "Elsevier journal (Ecological Economics)"),
        ("10.1016/j.reprotox.2019.02.001", "Elsevier journal (Reproductive Toxicology — code contains 'pro')"),
        ("10.1108/GKMC-12-2024-0824", "Emerald journal (alpha code, not S-ISSN)"),
        ("10.1002/14651858.CD013574.pub2", "Cochrane systematic review (Wiley, digit-initial ISSN — carve-out)"),
    ]
    for d, label in still_journal:
        if _is_non_journal_doi(d):
            fails.append(f"_is_non_journal_doi FALSE-excluded real journal {label}: {d}")
        dt, _ = classify_document_type(url=f"https://doi.org/{d}", doi=d, title="")
        if dt is not DocumentType.JOURNAL_ARTICLE:
            fails.append(f"{label} not recovered: {dt.value}")
    assert not fails, "isbn10/procedia guard failures:\n  - " + "\n  - ".join(fails)


def test_preprint_and_nonjournal_hosts_win_over_broad_registrant_doi():
    """Codex diff-gate iter-5 P1: the broad peer-reviewed-registrant DOI promotion runs AFTER the
    non-journal HOST negatives, so a preprint / book / news / blog host serving a PUBLISHED journal
    DOI (an author-uploaded reprint) keeps its host genre instead of being over-labeled a journal."""
    fails = []
    host_cases = [
        # (url, doi, expected DocumentType)
        ("https://papers.ssrn.com/sol3/papers.cfm?abstract_id=1", "10.1016/j.jfineco.2019.01.001",
         DocumentType.PREPRINT),
        ("https://www.researchgate.net/publication/365886802_x", "10.1177/0730888417720714",
         DocumentType.PREPRINT),
        ("https://osf.io/preprints/abcd", "10.1093/sf/78.4.1509", DocumentType.PREPRINT),
        ("https://www.amazon.com/dp/x", "10.1016/j.ecolecon.2017.04.025", DocumentType.BOOK),
    ]
    for url, doi, exp in host_cases:
        dt, basis = classify_document_type(url=url, doi=doi, title="")
        if dt is not exp:
            fails.append(f"{url[:44]} (doi {doi}) -> {dt.value} (basis={basis}); expected {exp.value}")
    # a genuine journal fetched from a NON-negative host is still recovered on the broad registrant DOI
    dt, _ = classify_document_type(url="https://journals.sagepub.com/doi/10.1177/0730888417720714", title="")
    if dt is not DocumentType.JOURNAL_ARTICLE:
        fails.append(f"journal on publisher host not recovered: {dt.value}")
    # OUP <slug>/ISBN book form (embedded ISBN-13 after a slug) is a book, not a journal
    if not _is_non_journal_doi("10.1093/actrade/9780198718123.003.0001"):
        fails.append("OUP <slug>/978… book DOI not recognized as non-journal")
    assert not fails, "host-ordering failures:\n  - " + "\n  - ".join(fails)


def test_openalex_peer_reviewed_gold_clause():
    """The OpenAlex gold ``is_peer_reviewed`` flag (present but with no explicit non-journal genre)
    resolves to a journal/review article — the SAME signal the tier classifier's U10 exemption
    trusts — while an explicit non-journal genre still wins (checked before the gold clause)."""
    # peer-reviewed, no explicit type/source => JOURNAL_ARTICLE
    dt, _ = classify_document_type(openalex_is_peer_reviewed=True, url="https://x.example/paper.pdf")
    assert dt is DocumentType.JOURNAL_ARTICLE
    # peer-reviewed review => REVIEW_ARTICLE
    dt, _ = classify_document_type(openalex_is_peer_reviewed=True, openalex_publication_type="review",
                                   url="https://x.example/p")
    assert dt is DocumentType.REVIEW_ARTICLE
    # peer-reviewed BUT explicit book-chapter genre => BOOK (negative genre wins)
    dt, _ = classify_document_type(openalex_is_peer_reviewed=True, openalex_publication_type="book-chapter",
                                   url="https://x.example/p")
    assert dt is DocumentType.BOOK
    # peer-reviewed BUT predatory venue => not laundered to a clean journal label
    dt, _ = classify_document_type(openalex_is_peer_reviewed=True, predatory_oa=True,
                                   openalex_publication_type="article", url="https://x.example/p")
    assert dt is DocumentType.PREDATORY_OA_JOURNAL
    # is_peer_reviewed FALSE + pt=article on an unknown host stays UNKNOWN (no over-mark)
    dt, _ = classify_document_type(openalex_publication_type="article", url="https://some-unknown-host.example/x")
    assert dt is DocumentType.UNKNOWN
