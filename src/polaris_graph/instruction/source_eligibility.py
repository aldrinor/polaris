"""Source-eligibility gate — positive proof of what a source IS, per row.

Ported from the cellcog eligibility doctrine (READ-ONLY source in the flywheel
tree): *eligibility is a positive proof of what the source IS, never a tier
guess*. The cellcog originals this ports are

  * ``scripts/provenance.py:1783`` ``derive_source_type`` — refuses to mint a
    ``journal_version`` from a type label alone; upgrades to journal only on a
    DOI **and** a venue (the core "positive-proof" conjunction), and mints NO
    expression when there is no proof (absence of proof = ineligible).
  * ``scripts/weighting.py:362`` ``gate_eligibility`` — the peer-reviewed-only
    gate + the language axis; a HARD ``only`` policy multiplies ineligible rows
    by 0.0 (kept in the graph, excluded from the body).
  * flywheel commit ``8589849`` (``multi_section_generator.py:_tier_first_menu``)
    — the Rank12 doctrine that this signal belongs on the *writer's menu*,
    behind a default-OFF flag, applied BEFORE the top-N cap, never touching
    ``ev_ids`` / the evidence pool / the frozen faithfulness engine.

The champion corpus schema (``data/cp4_corpus_s3gear_329.json``, 997 rows) is
NOT the cellcog schema. In particular ``doi``/``journal`` are populated on only
5 rows, there is no ``language`` field, and the journal proof lives in the
``source_url`` host + ``document_type``. So the cellcog "DOI and venue" rule is
kept but *OR'd* with a host-based positive proof and the declared doc-type.

This module is a **pure function of one row** plus two static, module-level
host lists (auditable constants). No imports from cellcog, no graph, no LLM. It
is standalone: nothing here is wired into the driver/generator. Any integration
MUST sit behind the default-OFF ``PG_SOURCE_ELIGIBILITY`` flag and follow the
Rank12 rule (reorder/annotate the writer's menu only, before the top-N cap).
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Tuple
from urllib.parse import urlparse

# ---------------------------------------------------------------------------
# Static host lists — the corpus-specific ground truth. Exposed as module-level
# constants so they are auditable and testable. Match is on the *registrable
# domain*: host == d  OR  host endswith "." + d.
# ---------------------------------------------------------------------------

# HARD-INELIGIBLE hosts. A landing on one of these is positive proof the source
# is NOT a peer-reviewed journal article. Checked FIRST — overrides any
# document_type / DOI signal (a preprint mirror of a journal work is still a
# preprint host, not the journal version).
HARD_INELIGIBLE_HOSTS: Tuple[str, ...] = (
    # Encyclopedia / wiki
    "wikipedia.org",
    # IGO / policy reports (never peer-reviewed journals)
    "oecd.org",
    "ilo.org",
    "imf.org",
    "worldbank.org",
    "weforum.org",
    "europa.eu",
    # Working-paper / preprint servers & mirrors
    "nber.org",
    "iza.org",
    "ssrn.com",
    "arxiv.org",
    "preprints.org",
    "repec.org",
    "econstor.eu",
    "cepr.org",
    "researchgate.net",
    "semanticscholar.org",
    "academia.edu",
    "ora.ox.ac.uk",
    # Central banks / gov stats / notes
    "bls.gov",
    "federalreserve.gov",
    "stlouisfed.org",
    "frb.org",
    "bnpparibas.com",
    "congress.gov",
    "publishing.service.gov.uk",
    "gov",
    "gov.uk",
    # Think-tanks / consultancies / business schools / banks
    "brookings.edu",
    "rand.org",
    "deloitte.com",
    "mckinsey.com",
    "hbs.edu",
    "hbsp.harvard.edu",
    "chicagobooth.edu",
    "mitsloan.mit.edu",
    "economics.mit.edu",
    "jpmorgan.com",
    "morganstanley.com",
    "budgetlab.yale.edu",
    "equitablegrowth.org",
    "laweconcenter.org",
    "bipartisanpolicy.org",
    "aei.org",
    # News / blogs / Q&A / personal / hosting
    "medium.com",
    "quora.com",
    "indeed.com",
    "ssir.org",
    "substack.com",
    "squarespace.com",
    "nytimes.com",
)

# POSITIVE journal-publisher hosts. A landing here is positive proof of a
# peer-reviewed journal/proceedings article — load-bearing because many of
# these (mdpi, pmc, sciencedirect, oup, emerald, cambridge) carry
# document_type=UNKNOWN, so the host is the only surviving proof.
JOURNAL_PUBLISHER_HOSTS: Tuple[str, ...] = (
    "sciencedirect.com",
    "springer.com",  # covers link.springer.com
    "tandfonline.com",
    "sagepub.com",  # covers journals.sagepub.com
    "oup.com",  # covers academic.oup.com
    "nature.com",
    "pnas.org",
    "cambridge.org",
    "emerald.com",
    "wiley.com",  # covers onlinelibrary.wiley.com + *.onlinelibrary.wiley.com
    "plos.org",  # covers journals.plos.org
    "aeaweb.org",
    "mdpi.com",
    "ncbi.nlm.nih.gov",  # covers pmc./pubmed./www.ncbi.nlm.nih.gov
    "iop.org",  # covers iopscience.iop.org
    "ilpnetwork.org",  # covers journal.ilpnetwork.org
)

# English/international TLDs and known-English hosts that PRE-EMPT the
# non-English ccTLD rule. A ccTLD not on this list flags positively-foreign.
_ENGLISH_TLDS: Tuple[str, ...] = (
    "com",
    "org",
    "net",
    "edu",
    "gov",
    "uk",
    "eu",
    "int",
    "io",
    "co",
)

# ccTLDs that positively indicate a non-English publisher of record.
_FOREIGN_TLDS: Tuple[str, ...] = (
    "de",
    "fr",
    "es",
    "it",
    "nl",
    "pl",
    "cn",
    "jp",
    "ru",
    "br",
    "kr",
    "se",
    "cz",
    "at",
    "ch",
    "be",
    "pt",
    "gr",
    "fi",
    "dk",
    "no",
    "hu",
    "ro",
    "tr",
)

# Declared document_type values that are POSITIVE journal proof.
_JOURNAL_DOC_TYPES: Tuple[str, ...] = ("JOURNAL_ARTICLE", "REVIEW_ARTICLE")

# Declared document_type values that are POSITIVE proof of ineligibility.
_NON_JOURNAL_DOC_TYPES: Tuple[str, ...] = (
    "PREPRINT",
    "REPORT",
    "BLOG_COMMENTARY",
    "ENCYCLOPEDIA",
    "BOOK",
)


def _host_matches(host: str, domains: Tuple[str, ...]) -> str:
    """Return the matched registrable domain (host == d or endswith '.'+d), else ''."""
    for d in domains:
        if host == d or host.endswith("." + d):
            return d
    return ""


def _extract_host(row: Dict[str, Any]) -> str:
    return urlparse(row.get("source_url") or "").netloc.lower().removeprefix("www.")


def _tld_of(host: str) -> str:
    return host.rsplit(".", 1)[-1] if "." in host else ""


def _classify_journal(row: Dict[str, Any], host: str) -> Tuple[bool, str]:
    """Positive-proof journal classification. Returns (is_journal, basis)."""
    dt = str(row.get("document_type") or "").strip().upper()
    doi = (row.get("doi") or "").strip()
    jour = (row.get("journal") or "").strip()

    # 1) Journal-publisher host of record. Checked FIRST because it is a SPECIFIC
    #    positive host-of-record proof: e.g. pmc./pubmed.ncbi.nlm.nih.gov are
    #    journal hosts that also end in the broad ``.gov`` hard-ineligible
    #    wildcard, and the specific journal signal must win over the wildcard.
    #    No explicit hard-ineligible host overlaps this allowlist.
    good = _host_matches(host, JOURNAL_PUBLISHER_HOSTS)
    if good:
        return True, f"host {host} is a peer-reviewed journal publisher ({good})"

    # 2) HARD-INELIGIBLE hosts override any doc_type / DOI signal (a preprint
    #    mirror of a journal work is still a preprint host).
    bad = _host_matches(host, HARD_INELIGIBLE_HOSTS)
    if bad:
        return False, f"host {host} is a non-journal publisher of record ({bad})"

    # 3) POSITIVE journal proof (any one is sufficient).
    #  3a. Declared type is a journal/review article.
    if dt in _JOURNAL_DOC_TYPES:
        return True, "document_type declares a peer-reviewed article"
    #  3b. DOI + named journal (the cellcog conjunction).
    if doi and jour:
        return True, f"row carries DOI {doi} and journal {jour}"
    #  3c. DOI-resolver with an asserted article type.
    if host == "doi.org" and dt in _JOURNAL_DOC_TYPES:
        return True, "doi.org resolver with an asserted article document_type"

    # 4) Declared NON-journal type is positive proof of ineligibility.
    if dt in _NON_JOURNAL_DOC_TYPES:
        return False, f"document_type={dt} is not a peer-reviewed article"

    # 5) Default: absence of proof is ineligibility (mirrors derive_source_type
    #    minting NO expression when nothing is claimed). NOT a tier guess.
    return False, "no positive proof of a peer-reviewed journal article"


def _classify_english(row: Dict[str, Any], host: str) -> Tuple[bool, str]:
    """Positive-with-conservative-default English classification.

    There is no ``language`` field, so infer from the host ccTLD and default to
    English (the corpus is an English research corpus). A row is only marked
    non-English when the registrable domain carries a positively non-English
    ccTLD and is not an English/international TLD.
    """
    tld = _tld_of(host)
    if host and tld in _FOREIGN_TLDS and tld not in _ENGLISH_TLDS:
        return False, f"host {host} has a non-English ccTLD .{tld}"
    return True, "no positive non-English signal (default English)"


def classify_source(row: Dict[str, Any]) -> Dict[str, Any]:
    """Classify one corpus row as a source.

    Returns a dict with the four contract keys::

        {
          'eligible': bool,        # is_journal AND is_english
          'source_class': str,     # 'journal_article' | 'non_journal' | 'non_english'
          'language_ok': bool,     # is_english
          'reasons': [str, ...],   # audit basis, journal axis before language
        }

    It never gates on ``tier`` (tier is a credibility ranking, not a source-kind
    proof). Pure function; no side effects.
    """
    host = _extract_host(row)
    is_journal, journal_basis = _classify_journal(row, host)
    is_english, english_basis = _classify_english(row, host)

    eligible = is_journal and is_english
    reasons: List[str] = [journal_basis, english_basis]

    if not is_journal:
        source_class = "non_journal"
    elif not is_english:
        source_class = "non_english"
    else:
        source_class = "journal_article"

    return {
        "eligible": eligible,
        "source_class": source_class,
        "language_ok": is_english,
        "reasons": reasons,
    }


def filter_eligible(
    rows: List[Dict[str, Any]], policy: Any = None
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Split ``rows`` into (eligible_rows, rejected_rows).

    ``policy`` is accepted for parity with cellcog ``gate_eligibility(row,
    policy)`` and forward-compat with a question-derived policy object; the
    champion policy (DRB task-72) is fixed as "only cite high-quality,
    English-language journal articles", which is what ``classify_source``
    already encodes, so ``policy`` is currently informational only. Rows are
    returned in their original order; neither list is mutated in place.
    """
    eligible_rows: List[Dict[str, Any]] = []
    rejected_rows: List[Dict[str, Any]] = []
    for row in rows:
        if classify_source(row)["eligible"]:
            eligible_rows.append(row)
        else:
            rejected_rows.append(row)
    return eligible_rows, rejected_rows


def is_enabled() -> bool:
    """True iff the default-OFF ``PG_SOURCE_ELIGIBILITY`` flag is truthy.

    Read at call time so the harness can toggle without re-import. The OFF path
    (this returning False) must leave any caller's row list byte-identical —
    this module ships wired to nothing, so OFF is the current state.
    """
    return os.getenv("PG_SOURCE_ELIGIBILITY", "0").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )
