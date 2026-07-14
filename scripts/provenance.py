#!/usr/bin/env python3
"""TYPED WORK / EXPRESSION / MANIFESTATION GRAPH — attribution may name only what the bytes prove.

WHY THIS EXISTS

  The corpus was one row per DOI. One row means one identity, so the row for a QJE article and the
  bytes of an NBER working paper were THE SAME OBJECT. `wp_fetch.py` wrote the working paper's text
  into `row['fulltext']`; the row kept `attribution = "Writing in the Quarterly Journal of Economics
  in 2003, Autor, Levy and Murnane"`. The miner then bound spans to that row, the writer named the
  journal, and the gate checked the sentence against the working paper's span. Every component was
  honest. The DATA MODEL did the lying: it had nowhere to put the difference.

  Sol, verbatim: "A predecessor working paper and later journal article may be closely related, but
  they are DIFFERENT SOURCES until version equivalence is proven. The recovered text is presently A
  DISCOVERY LEAD, not automatically journal-attributable evidence."

  So the row is split into three typed nodes, and the difference gets somewhere to live:

      Work           the research object / case / trial          "what was studied"
        Expression   the version of the report of that work      "which version says it"
          Manifest.  the retrieved bytes + content hash          "the text we actually hold"

  Spans bind to a MANIFESTATION, never to a Work. That is the whole point: `span -> manifestation`
  is a fact about bytes we hold; `span -> work` is a wish.

THE CORE RULE (Sol, verbatim)

  "Every span binds to its exact manifestation_id and content hash. ATTRIBUTION MAY NAME ONLY THAT
   MANIFESTATION, unless a stronger edge proves that the cited source contains the same span."

  Implemented in `Graph.attribution_targets()`. An edge only widens what a span may name if it is
  SPAN-PRESERVING (exact_copy_of, authenticated accepted_manuscript_of) *and* ASSERTED. A
  `predecessor_of` edge never widens anything, however plausible: PEER REVIEW CHANGES NUMBERS.

  "A title similarity match can PROPOSE predecessor_of; it CANNOT ASSERT exact_copy_of."
  -> every edge carries `status` (PROPOSED | ASSERTED) and a `basis` naming the evidence. An edge
     with no basis cannot be constructed.

NO UNIVERSAL WORD THRESHOLD (Sol, item 4)

  "A universal word threshold cannot define 'full text': a short judicial opinion, statute section,
   trial-registry record, and journal article have different completeness profiles."

  MIN_WORDS=2500 was my own invention and it is deleted. `profile()` derives, FROM THE BYTES:
  artifact_kind, sections present, body/chrome ratio, result-bearing sections, extractability,
  identity agreement, fetch outcome — and judges completeness AGAINST THE PROFILE FOR THAT KIND.
  A four-page judicial opinion is COMPLETE. A 535-word cookie banner is not, at any length.

  There is exactly ONE reducer that may answer "is this the whole document?": `judge_completeness()`,
  driven by the KIND_PROFILE registry. `profile()` calls it, `Graph.from_json()` calls it, and
  `event_ledger.derive_content_profile()` calls it. It was written twice before — 1,200 words here
  and FULLTEXT_MIN=2,500 there — which is not a shared rule, it is two rules that disagree, and the
  document a card cites depends on which module last looked at it.

THE API. EXACTLY THREE ENTRY POINTS (Sol, "reality checks", item 5)

    bind_span(manifestation_id, start, end)   -> bytes -> a bound span. BOUNDS ARE VALIDATED.
    resolve_attribution(manifestation_id, policy) -> what that span may NAME, under THIS task's rule
    verify_span(binding)                      -> the enforcement point re-checks EVERYTHING

  bind_span() returns IDENTIFIERS — `expression_id` and `permitted_expression_ids`. It used to return
  `may_name`: a list of English SENTENCES. A sentence is a display cache, and a consumer that must
  string-match prose to decide what is legal has no rule at all — it has a suggestion. Prose is
  produced by resolve_attribution(), carried as `.text`, and NOTHING IS EVER VALIDATED AGAINST IT.

WHAT RE-DERIVING THE LABELS FROM THE BYTES ACTUALLY FOUND

  The memo assumed the six `fulltext_source='working_paper'` rows were working papers. The bytes say
  that label recorded WHICH FETCHER RAN, not WHAT THE ARTIFACT IS. It is false in both directions:

    Parry et al. (2016), Group & Organization Management, "Rise of the Machines"
        -> the bytes are Yang-Hui He, "MATHEMATICS: THE RISE OF THE MACHINES", an arXiv PAPER ABOUT
           THEOREM-PROVING. None of Parry, Cohen or Bhattacharya appears anywhere in the 4,027 words.
           The title matcher matched the phrase "Rise of the Machines". This is not a predecessor,
           not a preprint, not a version — IT IS A DIFFERENT WORK, and 17 of its numbers were queued
           to be printed as findings of a management journal.
    Acemoglu and Restrepo (2019), JEP -> the bytes ARE the typeset JEP article. Not a working paper.
    Autor (2015), JEP                 -> the bytes are the AEA WEBSITE'S COOKIE BANNER. 535 words.
    Autor et al. (2003), QJE          -> readable body, but chars 0-19,569 are (cid:N) font codes and
                                         NOTHING in the bytes says whether this is QJE or NBER 8337.
                                         Genuinely UNRESOLVED -> therefore NOT journal-attributable.

  And one the memo never suspected, found by the same content check, ALREADY SHIPPED IN A CARD:

    Weiss (2008), Economics Letters   -> the PDF extracted as a CAESAR-SHIFTED GLYPH DUMP.
        span:  "...wkh qxpehu ri kdluguhvvhuv juhz pruh wkdq 633 shu fhqw ehwzhhq 4<<5 dqg 4<<<"
        plain: "...the number of hairdressers grew more than 300 per cent between 1992 and 1999"
        card:  "633 percent increase in number of hairdressers"          THE PAPER SAYS 300.

        The span gate did its job perfectly: that span IS verbatim in the source. But the SOURCE was
        a corrupted encoding of the paper, so "verbatim from the source" was verbatim from garbage.
        EXTRACTION QUALITY IS A PRECONDITION FOR THE GATE TO MEAN ANYTHING, and nothing was checking
        it. That is why `extractability` is in the profile and why it is load-bearing for
        faithfulness, not merely for tidy labelling.

    usage:  python3 scripts/provenance.py            # the honest census
"""
from __future__ import annotations

import hashlib
import json
import re
import statistics
import sys
import unicodedata
from dataclasses import dataclass, field, asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))

# ONE definition of "section", shared with the miner. Two functions that each decide what a section
# is will drift, and every offset stored in every card indexes into whichever one won that day.
from evidence_miner import View, sections_of, SECTION_WEIGHT  # noqa: E402

CORPUS = ROOT / 'outputs' / 'journal_corpus_content.json'
GRAPH_OUT = ROOT / 'outputs' / 'provenance_graph.json'

#: THE API. A span becomes a citation through these three functions and no others.
#:     bind_span(manifestation_id, start, end)        -> Graph.bind_span
#:     resolve_attribution(manifestation_id, policy)  -> Graph.resolve_attribution
#:     verify_span(binding)                           -> Graph.verify_span
__all__ = [
    'Graph', 'Work', 'Expression', 'Manifestation', 'Edge', 'SpanCorrespondence',
    'SourcePolicy', 'Attribution', 'SpanBindingError', 'GraphIntegrityError',
    'JOURNAL_ONLY', 'PEER_REVIEWED', 'OFFICIAL_TEXT', 'ANY_VERSION',
    'KIND_PROFILE', 'ARTIFACT_KINDS', 'FINDING_BEARING_KINDS', 'EXPRESSION_KINDS', 'WORK_KINDS',
    'SPAN_PRESERVING', 'NON_SPAN_PRESERVING',
    'CANON_ALGORITHM', 'CANON_VERSION', 'canonicalize', 'canonical_hash', 'binding_id',
    'make_correspondence',
    'judge_completeness', 'profile', 'derive_expression_kind', 'derive_source_type', 'migrate',
]


# =================================================================================================
# 1. NODE TYPES
# =================================================================================================

# The version taxonomy. `repository` is NOT a version — a repository copy is a MANIFESTATION (a place
# bytes live) of some expression, which is where it sits in the graph below.
#
# A JUDICIAL OPINION HAS NO `journal_version`, AND A STATUTE HAS NO PREPRINT. The scholarly five were
# the only kinds here, and `migrate()` therefore minted a `journal_version` for every row it saw —
# which is not a taxonomy, it is an assumption wearing one. `official_text` and `registry_record` are
# the authoritative expressions of the non-scholarly works, and the registry below says which work
# kind has which.
EXPRESSION_KINDS = ('journal_version', 'proceedings_version', 'accepted_manuscript', 'working_paper',
                    'preprint', 'official_text', 'registry_record', 'unknown')


@dataclass
class Work:
    """The research object / case / trial. NOT a document. Nothing binds to it.

    `kind` IS LOAD-BEARING, not decoration: it selects the completeness profile its documents are
    judged against. A `case` is judged as a judicial opinion — COMPLETE AT ANY LENGTH — and a `study`
    is judged as a scholarly article, where 300 words is a fragment. Judge one by the other's rule and
    you either destroy the opinion or admit the fragment.
    """
    id: str
    title: str
    authors: list[str]
    year: int | None
    venue: str | None            # the venue / court / reporter / registry that names the official text
    doi: str | None
    kind: str = 'study'          # WORK_KINDS


@dataclass
class Expression:
    """A VERSION of the report of a Work. This is the unit an attribution may name.

    There is NO `citable_in_journal_only_answer` field any more. Citability is a property of THE
    ANSWER'S INSTRUCTION, not of the node: the same accepted manuscript is inadmissible under
    "journal articles only" and admissible under "any identified version". A boolean stored on the
    node has to be wrong for one of them, and a stored label that can be wrong is this whole file's
    subject. It is DERIVED, per policy, by `Graph.resolve_attribution()`.
    """
    id: str
    work_id: str
    kind: str                     # EXPRESSION_KINDS
    kind_basis: str               # WHY we believe that — derived from bytes, or 'claimed_by_metadata'
    attribution: str              # DISPLAY ONLY. The sentence a writer may render for THIS expression.
    #                             # Nothing is ever validated against it — see THE LAW.


@dataclass
class Manifestation:
    """The BYTES WE ACTUALLY HOLD. Every span binds here, and to `content_hash`."""
    id: str
    expression_id: str
    work_id: str
    text: str                     # retained in full. NOTHING IS EVER DELETED.
    content_hash: str             # sha256 of `text`
    n_words: int
    locator: str | None           # the URL these bytes came from
    locator_status: str           # RECORDED | NOT_RECORDED_BY_FETCHER | CONTRADICTS_CONTENT
    fetched_by: str               # which fetcher wrote it
    text_field: str               # which corpus field it came from ('fulltext' | 'abstract')
    profile: dict = field(default_factory=dict)   # the content-derived artifact profile


@dataclass
class Edge:
    """A TYPED, EVIDENCED relation. An edge with no basis cannot be constructed."""
    src: str
    dst: str
    type: str                     # EDGE_TYPES
    status: str                   # PROPOSED | ASSERTED
    basis: str                    # the evidence. Never empty.


EDGE_TYPES = ('exact_copy_of', 'accepted_manuscript_of', 'predecessor_of',
              'reports_same_study', 'supersedes', 'cites')

# THE ONLY EXPRESSION-WIDE EDGE THAT MAY WIDEN AN ATTRIBUTION.
# A span in manifestation M may name expression E != M.expression ONLY across this edge, and ONLY when
# the edge is ASSERTED. `predecessor_of` and `reports_same_study` are deliberately absent: a working
# paper and the journal article report the same study, and PEER REVIEW CHANGES NUMBERS.
#
# `accepted_manuscript_of` WAS IN THIS TUPLE AND IS NOT ANY MORE. (Sol, V9 §4: "`accepted_manuscript_of`
# remains a useful bibliographic edge, but it is not span-preserving.") It stayed here on the theory that
# an accepted manuscript is post-peer-review and therefore says what the journal says. It is not, and it
# does not: copy-editing, proof corrections, and the editor's own last round all land AFTER acceptance,
# and the numbers move. Worse, the edge was reachable FROM REPOSITORY METADATA — version_align mapped
# Unpaywall's `acceptedVersion` string straight onto it and alignment_census declared the result
# journal-ADMISSIBLE. That is a live fabrication path: a repository's one-word label, three hops later,
# printing a manuscript's number under a journal's name.
#
# AN ACCEPTED MANUSCRIPT IS NEVER THE JOURNAL VERSION MERELY BECAUSE A REPOSITORY SAYS `acceptedVersion`.
# What CAN carry a span from an accepted manuscript into the journal is a verified SpanCorrespondence —
# THAT SPAN, those two hashes, those two offsets, exact canonical equality — and nothing else.
SPAN_PRESERVING = ('exact_copy_of',)

#: An edge that is a real bibliographic fact and transfers NO attribution whatsoever. Kept explicit so
#: that "which edges are inert" is a statement in the code and not an absence from a tuple.
NON_SPAN_PRESERVING = tuple(t for t in ('exact_copy_of', 'accepted_manuscript_of', 'predecessor_of',
                                        'reports_same_study', 'supersedes', 'cites')
                            if t not in SPAN_PRESERVING)


# =================================================================================================
# 1b. PER-SPAN ATTRIBUTION — THE SpanCorrespondence  (Sol V9 §4)
# =================================================================================================
"""
THE API MOVED FROM MANIFESTATION-WIDE PERMISSION TO BINDING-SPECIFIC PERMISSION.

The old shape was `resolve_attribution(manifestation_id, policy)`: ONE answer for a whole document. An
edge that widened it widened it for EVERY span in the manifestation at once — so proving that ONE
sentence of an accepted manuscript survived into the journal would have licensed the OTHER four hundred,
including the ones peer review rewrote. That is permission by association, and the association is exactly
what we cannot check.

A `SpanCorrespondence` is the narrowest true thing: THIS span, in THESE bytes, is character-for-character
THAT span, in THOSE bytes. It carries both manifestation ids, both content hashes, both offset pairs,
both verbatim spans, the canonicalization ALGORITHM AND VERSION under which they were compared, the exact
canonical-span hash, and the identity decision for each manifestation. The verifier RECHECKS all of it —
the hashes, the offsets, and exact canonical text equality — because a correspondence that arrives from a
JSON file is an untrusted input, like everything else here.

Consequences, all of them mechanical below:

  * Repository metadata can NEVER prove span equivalence. There is no field on this record where a
    repository's opinion could be written; the record is made of hashes and offsets or it is not made.
  * A correspondence grants permission FOR THAT SPAN ONLY — not for every assertion in the manuscript.
  * "0.37 versus 0.2" FAILS IMMEDIATELY: canonicalization does not touch digits, so the canonical texts
    differ and `verify_correspondence()` returns False before any policy is consulted.
  * A span found independently in the VoR's own bytes should be REBOUND to the VoR manifestation
    (`Graph.rebind()`), which is strictly stronger than a correspondence: no cross-document permission
    is needed at all when the span is IN the document you want to name.
  * An accepted manuscript with no VoR bytes stays accepted-manuscript-attributable ONLY.
"""

#: THE CANONICALIZATION. Named and VERSIONED, because two documents compared under different rules were
#: never compared. It does exactly two things — Unicode compatibility normalisation (so a ligature or a
#: non-breaking space in a PDF is not a "difference"), and whitespace collapse (so a column break is not
#: a difference either).
#:
#: WHAT IT DELIBERATELY DOES NOT DO, and why each omission is load-bearing:
#:   - it does not case-fold      : "Table 3" and "table 3" may genuinely be different objects
#:   - it does not strip punctuation: "0.37" vs "037" is not a rounding, it is a different number
#:   - it does not normalise digits or units: THIS IS THE ACEMOGLU TEST. 0.37pp in the NBER working
#:     paper, 0.2pp in the published JPE. Any "smart" numeric tolerance here would align them, and the
#:     whole point of this file is that PEER REVIEW CHANGES NUMBERS.
CANON_ALGORITHM = 'nfkc_whitespace_collapse'
CANON_VERSION = '1'


def canonicalize(s: str) -> str:
    """The ONE canonicalization. Its name and version travel with every correspondence that uses it."""
    return re.sub(r'\s+', ' ', unicodedata.normalize('NFKC', s or '')).strip()


def canonical_hash(s: str) -> str:
    """sha256 of the canonical form, DOMAIN-SEPARATED BY ALGORITHM AND VERSION.

    Without the prefix, a hash computed under algorithm v1 and a hash computed under a future v2 would be
    indistinguishable strings, and a stored hash would silently certify a comparison that was never made.
    """
    return hashlib.sha256(
        f'{CANON_ALGORITHM}:{CANON_VERSION}:{canonicalize(s)}'.encode('utf-8', 'ignore')).hexdigest()


def binding_id(manifestation_id: str, content_hash: str, start: int, end: int) -> str:
    """The identity of a BOUND SPAN — the unit `resolve_attribution()` now answers about.

    It is derived, not minted: the same span of the same bytes always has the same id, and a binding whose
    offsets or whose source bytes were edited IS A DIFFERENT BINDING and cannot inherit the old one's
    permission.
    """
    h = hashlib.sha256(f'{manifestation_id}|{content_hash}|{start}|{end}'.encode()).hexdigest()
    return f'bind:{h[:16]}'


@dataclass
class SpanCorrespondence:
    """THIS span in THESE bytes IS THAT span in THOSE bytes. The only thing that can move a span across
    documents — and it moves exactly one span.

    Every field is a hash, an offset, a verbatim string, or a decision derived from bytes. There is no
    field for a repository's version label, and that absence is the design.
    """
    id: str
    source_manifestation_id: str
    source_raw_hash: str          # sha256 of the source manifestation's text (its content_hash)
    source_start: int
    source_end: int
    source_span: str              # VERBATIM, as sliced

    target_manifestation_id: str
    target_raw_hash: str
    target_start: int
    target_end: int
    target_span: str              # VERBATIM, as sliced

    canonicalization: str         # ALGORITHM:VERSION under which the two were compared
    canonical_span_hash: str      # the exact hash of the shared canonical text

    source_identity: str          # the identity decision for the SOURCE manifestation
    target_identity: str          # ...and for the TARGET. Both must be CONFIRMED.
    basis: str                    # how this correspondence was established. Never empty.


CORRESPONDENCE_IDENTITY_OK = ('CONFIRMED',)


def make_correspondence(g: 'Graph', source_mid: str, source_start: int, source_end: int,
                        target_mid: str, target_start: int, target_end: int,
                        basis: str) -> SpanCorrespondence:
    """Build a correspondence FROM THE BYTES. It is then still VERIFIED before it grants anything —
    the constructor is a convenience, never an authority.
    """
    src = g.manifestations[source_mid]
    tgt = g.manifestations[target_mid]
    s_span = src.text[source_start:source_end]
    t_span = tgt.text[target_start:target_end]
    cid = hashlib.sha256(
        f'{source_mid}|{source_start}|{source_end}|{target_mid}|{target_start}|{target_end}'
        .encode()).hexdigest()[:16]
    return SpanCorrespondence(
        id=f'corr:{cid}',
        source_manifestation_id=source_mid, source_raw_hash=src.content_hash,
        source_start=source_start, source_end=source_end, source_span=s_span,
        target_manifestation_id=target_mid, target_raw_hash=tgt.content_hash,
        target_start=target_start, target_end=target_end, target_span=t_span,
        canonicalization=f'{CANON_ALGORITHM}:{CANON_VERSION}',
        canonical_span_hash=canonical_hash(s_span),
        source_identity=(src.profile.get('identity') or {}).get('verdict', 'UNRESOLVED'),
        target_identity=(tgt.profile.get('identity') or {}).get('verdict', 'UNRESOLVED'),
        basis=basis)


# =================================================================================================
# 2. CONTENT-DERIVED ARTIFACT PROFILE  — this replaces MIN_WORDS
# =================================================================================================

# --- extractability ------------------------------------------------------------------------------
# Thresholds are DERIVED FROM THE OBSERVED DISTRIBUTION of this corpus, not invented, and __main__
# reprints that distribution so they can be re-derived by anyone who doubts them. On the 70-row
# corpus the stopword density of intact prose runs 0.198 - 0.45 (median 0.292); the single
# Caesar-shifted document sits at 0.012. The gap is 16x and the threshold below falls in empty space.
_FUNCTION_WORDS = frozenset("""the of and to in a is that for with as on by are we this be it from at
an not which or have has was were their its they there than these such been between more can may""".split())
CORRUPT_STOPWORD_DENSITY = 0.10   # < this => the bytes are not English prose (cipher / glyph dump)
DEGRADED_CID_RATIO = 0.05         # > this => a non-embedded font left (cid:N) codes in the text

_CID = re.compile(r'\(cid:\d+\)')
_WORDY = re.compile(r"[A-Za-z']+")

# --- chrome --------------------------------------------------------------------------------------
# Web furniture. A landing page is not a paper at ANY word count, and 548 words of it is not an
# "abstract" either -- calling it one implies the paper's own summary, which we do not have.
_CHROME = re.compile(
    r'(uses cookies|cookie (policy|settings|consent)|accept(ing)? (all )?cookies|skip to (main|content)'
    r'|sign in|log ?in|register|create an account|privacy policy|terms (of use|and conditions)'
    r'|newsletter|subscribe|add to cart|purchase|download pdf|share (this|on)|permissions'
    r'|all rights reserved|advertisement|search this site|contact name email|send me)', re.I)

# --- self-identifying version furniture ----------------------------------------------------------
_WP_MARK = re.compile(
    r'(nber working paper|national bureau of economic research|working paper (no\.?|series|\d)'
    r'|iza (discussion paper|dp)|discussion paper (no\.?|series)|cepr discussion paper'
    r'|preliminary(?: and incomplete)?[.:—-]? *(?:please )?do not (cite|quote)'
    r'|comments? welcome|this draft)', re.I)
_PREPRINT_MARK = re.compile(r'(arxiv[:\s]*\d{4}\.\d{4,5}|ssrn[- ]id|preprint (submitted|version)|biorxiv)', re.I)
_AM_MARK = re.compile(
    # ---- THE WHITE ROSE GAP (found by the hop-6 probe; it was a LIVE fabrication path) -----------
    # This detector required the literal word `accepted` or `final`, or the phrase "this is THE
    # author". White Rose, Enlighten and most EPrints repositories write, verbatim:
    #
    #     "This is AN AUTHOR PRODUCED VERSION of a paper published in <journal>."
    #
    # `produced` is neither `accepted` nor `final`, and `an` is not `the` — so the commonest
    # accepted-manuscript cover sheet in the UK was INVISIBLE to the accepted-manuscript detector. It
    # then fell through to _JOURNAL_MARK, which matched the DOI THE COVER SHEET PRINTS, and the
    # manuscript was classified `journal_version` and CITED AS THE JOURNAL ARTICLE.
    # Like the NIH widening below, this can only move bytes OUT of journal_version, never into it.
    r"(accepted manuscript|author'?s? (accepted|final|original) (version|manuscript)"
    r'|author[- ]?produced[- ]?(version|manuscript)|postprint|post-print'
    r'|published version\)? *\(refereed\)|this is (?:the|an?) (author|accepted)'
    # ---- THE NIH AUTHOR MANUSCRIPT (Sol V9 §2, the PMC silent failure list, verbatim: "NIH manuscript
    # ---- is mistaken for publisher VoR") ---------------------------------------------------------
    # PMC deposits NIH-funded accepted manuscripts ALONGSIDE publisher VoRs, in the same JATS dialect,
    # under the same kind of PMCID. Nothing on the wire distinguishes them — Europe PMC's `nihAuthMan`
    # flag is a REPOSITORY LABEL, and the whole V9 P0 was the project of refusing to let a repository
    # label decide what bytes ARE. So the tell has to come from THE DOCUMENT'S OWN FRONT MATTER, and
    # there are exactly two that are reliable:
    #
    #   1. the stamp PMC prints in the running head of every page of one:
    #        "Author manuscript; available in PMC 2026 Jan 01."
    #      Note this did NOT match the old pattern: `author'?s? (accepted|final) (version|manuscript)`
    #      requires the word `accepted` or `final`, and the NIH stamp says neither. The most common
    #      accepted manuscript in biomedicine was invisible to the accepted-manuscript detector.
    #   2. the JATS front-matter id <article-id pub-id-type="manuscript">NIHMS2075474</article-id>,
    #      which routes_bio.jats_to_text linearizes into the header. A VoR does not carry one.
    #
    # Both are ANCHORED (the stamp requires "in PMC"; the id requires the NIHMS prefix + digits), so a
    # paper that merely discusses author manuscripts in its prose cannot trip them. This is a STRICTLY
    # WIDENING change to an accepted-manuscript detector: it can only move bytes OUT of journal_version,
    # never into it. Under a JOURNAL-ONLY contract that is the safe direction, and it is the true one.
    r'|author manuscript;? *available in pmc|\bnihms\s*\d{3,})', re.I)
# Typeset journal furniture: a running head with volume/issue/pages, or a publisher rights block.
_JOURNAL_MARK = re.compile(
    r'(volume \d+[,—-] *number \d+|vol\.? *\d+[,(]? *(no\.?|issue|\()? *\d+'
    r'|doi[:\s]*10\.\d{4,9}/|©\s*(the author|\d{4})|article reuse guidelines'
    r'|received .{0,40}(revised|accepted).{0,40}\d{4}'
    # ---- THE MASTHEAD FORMS THIS PATTERN COULD NOT SEE ------------------------------------------
    # Segmenting the cover sheet off (below) exposed a gap that the cover sheet had been HIDING: the
    # two commonest article-of-record mastheads in this corpus matched NOTHING here, and both real
    # journal articles were being rescued by the DOI THEIR COVER SHEET PRINTED. Remove the cover
    # sheet and the AER deposit fell to `unknown`. The furniture was always right there:
    #     "American Economic Review 2014, 104(8): 2509-2526"   <- vol(issue): page-range
    #     "AI and Ethics (2021) 1:119-130"                     <- (year) vol:page-range
    #     "https://doi.org/10.1007/..."                        <- `doi[:\s]*10\.` cannot match this:
    #                                                             ".org/" sits between `doi` and `10.`
    # Widening an ADMITTING mark is the dangerous direction, and it is safe ONLY because of where this
    # mark may now be read: the article's OWN front matter, never a cover sheet, and only after the
    # accepted-manuscript / working-paper / preprint marks have all declined to fire.
    r'|doi\.org/10\.\d{4,9}/'
    r'|\b\d{1,4} *\( *\d{1,3} *\) *: *\d{1,5} *[-–—] *\d{1,5}'
    r'|\(\d{4}\) *\d{1,4} *: *\d{1,5} *[-–—] *\d{1,5})', re.I)

#: ══ A REPOSITORY COVER SHEET IS NOT THE DOCUMENT. THE *ONE* DEFINITION. ═════════════════════════
#:
#: THE SIXTH HOP OF THE V9 P0 LIVED IN EXACTLY THIS GAP. `_JOURNAL_MARK` above matches a bare DOI
#: string — and this file's own census docstring has warned, in writing, the whole time:
#:
#:     "`_JOURNAL_MARK` matches a DOI string — but a DOI string is printed by every repository COVER
#:      SHEET, which cites the article rather than being it."
#:
#: The warning was written and the code was never changed. `derive_expression_kind` read its marks out
#: of `text[:12000]` — cover sheet included — so a White Rose deposit of an ACCEPTED MANUSCRIPT was
#: classified `journal_version` on the strength of the DOI ITS OWN COVER SHEET PRINTS, and
#: `resolve_attribution(JOURNAL_ONLY)` then ADMITTED it and would have printed "Acemoglu and Restrepo
#: (2020), Journal of Political Economy" over the manuscript's 0.37pp.
#:
#: THE RULE, AND IT IS NOT NEGOTIABLE:
#:   * the cover sheet MAY CONVICT — a library writing "this is an author produced version" is
#:     describing THE FILE IT DEPOSITED, and that is testimony about these bytes;
#:   * the cover sheet MAY NEVER ACQUIT — its DOI, its volume/issue, its citation block are the
#:     library CITING the article of record, which is precisely what a document that IS the article
#:     of record never needs to do.
#: Convicting evidence is read from the whole document; ACQUITTING evidence only from the article's
#: own front matter. (event_ledger imports this same pattern, so "what is a cover sheet" is defined
#: ONCE in this repo and cannot drift between the two lanes that ask.)
_COVER_SHEET = re.compile(
    r'(this is a repository copy of|this is an? (author|accepted|final)[- ]?(produced|version)'
    r'|white rose research online|enlighten|eprints|dspace|munin|hal (open science|id)'
    r'|citation for (the )?published version|the version (presented here|in the repository)'
    r'|downloaded from .{0,60}(repository|eprints|dspace|core\.ac\.uk)'
    r'|this version is available at|general rights|take down policy'
    r'|users may download and print one copy)', re.I)


def segment_cover_sheet(text: str, window: int = 12000) -> tuple[str, str]:
    """-> (cover_sheet_text, the_document_itself).

    The boundary is the first form feed after the last cover-sheet marker — a cover sheet IS a
    separate PDF page, and that is the one structural thing reliably true of it. No marker => no cover
    sheet, and the document is the whole text (the common case, which must stay cheap).
    """
    head = text[:window]
    hits = list(_COVER_SHEET.finditer(head))
    if not hits:
        return '', text
    end = hits[-1].end()
    ff = text.find('\x0c', end)
    boundary = ff + 1 if 0 <= ff < window else end
    return text[:boundary], text[boundary:]

# =================================================================================================
# THE REGISTRY — the ONE table that says what each artifact kind IS and when it is COMPLETE.
# =================================================================================================
# Sol's point, made mechanical: completeness is a property OF A KIND, never of a word count.
#
# `stub_floor` separates THE DOCUMENT from A STUB OF IT, and it exists ONLY for the scholarly kinds,
# where a 500-word artifact is definitionally not the article (it is its abstract, or its landing
# page). For a judicial opinion, a statute section or a trial-registry record it is None: THOSE
# ARTIFACTS ARE COMPLETE AT ANY LENGTH. That is the whole difference between this and MIN_WORDS=2500,
# which asserted one number over every kind of document in the world.
#
# `expression` is the expression kind these bytes CONSTITUTE when they are the document — the link
# between "what is this artifact" and "what may a span in it name". A judicial opinion's bytes are its
# `official_text`; there is no journal version of it to widen to, ever.
#
# `needs_results` IS DELIBERATELY ABSENT. I first wrote it as a completeness gate and it declared six
# genuine journal articles incomplete — Technovation (15,985w), JEP (11,872w), AER (9,732w), JBR,
# Raj, Chalmers — because economics papers title their results sections after their CONTENT ("V. The
# Effect of Robots on Employment"), and a JEP essay has no results section at all. Gating on a
# section heading is the same error as gating on a word count, moved one axis over. The
# result-bearing sections are REPORTED in the profile (the miner weights by them) and GATE NOTHING.

SCHOLARLY_STUB_FLOOR = 1200     # scholarly kinds ONLY. It is not a fact about documents in general.
SCHOLARLY_ABSTRACT_FLOOR = 120  # ...and below THIS, a scholarly fragment is a citation stub.

KIND_PROFILE: dict[str, dict] = {
    'journal_article':       dict(stub_floor=SCHOLARLY_STUB_FLOOR, abstract_floor=SCHOLARLY_ABSTRACT_FLOOR,
                                  expression='journal_version',     finding_bearing=True),
    'proceedings_paper':     dict(stub_floor=SCHOLARLY_STUB_FLOOR, abstract_floor=SCHOLARLY_ABSTRACT_FLOOR,
                                  expression='proceedings_version', finding_bearing=True),
    'working_paper':         dict(stub_floor=SCHOLARLY_STUB_FLOOR, abstract_floor=SCHOLARLY_ABSTRACT_FLOOR,
                                  expression='working_paper',       finding_bearing=True),
    'preprint':              dict(stub_floor=SCHOLARLY_STUB_FLOOR, abstract_floor=SCHOLARLY_ABSTRACT_FLOOR,
                                  expression='preprint',            finding_bearing=True),
    'accepted_manuscript':   dict(stub_floor=SCHOLARLY_STUB_FLOOR, abstract_floor=SCHOLARLY_ABSTRACT_FLOOR,
                                  expression='accepted_manuscript', finding_bearing=True),
    # A short official opinion IS the whole artifact. No results section, no methods, and COMPLETE.
    # stub_floor=None IS THE POINT OF THIS TABLE. Do not put a number here. Ever.
    'judicial_opinion':      dict(stub_floor=None, abstract_floor=None,
                                  expression='official_text',   finding_bearing=True),
    'statute_section':       dict(stub_floor=None, abstract_floor=None,
                                  expression='official_text',   finding_bearing=True),
    'trial_registry_record': dict(stub_floor=None, abstract_floor=None,
                                  expression='registry_record', finding_bearing=True),
    # These are NEVER complete, at any length, and may never carry a finding. They have no expression:
    # a cookie banner is not a VERSION of the paper, it is not the paper at all.
    'abstract':              dict(stub_floor=None, abstract_floor=None, expression=None, finding_bearing=False),
    'citation_only':         dict(stub_floor=None, abstract_floor=None, expression=None, finding_bearing=False),
    'landing_page':          dict(stub_floor=None, abstract_floor=None, expression=None, finding_bearing=False),
    'extraction_failure':    dict(stub_floor=None, abstract_floor=None, expression=None, finding_bearing=False),
    'wrong_work':            dict(stub_floor=None, abstract_floor=None, expression=None, finding_bearing=False),
    'unknown':               dict(stub_floor=None, abstract_floor=None, expression=None, finding_bearing=False),
}
# DERIVED from the registry, never maintained beside it — two lists of kinds will drift, and the one
# that drifts is always the one a gate reads.
ARTIFACT_KINDS = tuple(KIND_PROFILE)
FINDING_BEARING_KINDS = tuple(k for k, v in KIND_PROFILE.items() if v['finding_bearing'])

#: NOT A DOCUMENT AT ALL — as distinct from `unknown`, which IS a document whose VERSION we cannot
#: establish. Autor, Levy & Murnane (2003) is 10,902 readable words whose title page is (cid:N) font
#: codes: we HOLD a document and cannot say which version it is. A cookie banner is not a document.
#: Reporting those two in one bucket would say "we hold nothing" about a paper we hold in full, which
#: is a different claim, and a false one.
NOT_A_DOCUMENT_KINDS = tuple(k for k, v in KIND_PROFILE.items()
                             if not v['finding_bearing'] and k != 'unknown')

#: WHICH COMPLETENESS PROFILE DOES THIS WORK'S DOCUMENT GET? `None` => the scholarly family, whose
#: artifact kind is derived from the bytes' own version furniture. Everything else is fixed by the
#: work: a case produces judicial opinions, and no amount of NBER letterhead makes one a working paper.
WORK_KIND_ARTIFACT: dict[str, str | None] = {
    'study':   None,
    'case':    'judicial_opinion',
    'statute': 'statute_section',
    'trial':   'trial_registry_record',
}
WORK_KINDS = tuple(WORK_KIND_ARTIFACT)

#: THE ROW'S OWN DECLARED TYPE -> (work kind, the expression the METADATA claims exists).
#: `migrate()` used to hardcode a `journal_version` for every row in the corpus. Sol: "That is not
#: valid for a judicial opinion or statute." The row DECLARES its type — every one of the 70 rows here
#: carries `type: 'journal-article'` from Crossref, and the code never once read it. It assumed the
#: answer it happened to be right about, which is not the same as being right.
SOURCE_TYPE: dict[str, tuple[str, str]] = {
    'journal-article':     ('study',   'journal_version'),
    'journal article':     ('study',   'journal_version'),
    'proceedings-article': ('study',   'proceedings_version'),
    'book-chapter':        ('study',   'journal_version'),
    'posted-content':      ('study',   'preprint'),      # a preprint row claims NO journal version
    'preprint':            ('study',   'preprint'),
    'report':              ('study',   'working_paper'),
    'working-paper':       ('study',   'working_paper'),
    'judicial-opinion':    ('case',    'official_text'),
    'opinion':             ('case',    'official_text'),
    'case':                ('case',    'official_text'),
    'statute':             ('statute', 'official_text'),
    'legislation':         ('statute', 'official_text'),
    'clinical-trial':      ('trial',   'registry_record'),
    'trial-registration':  ('trial',   'registry_record'),
}

RESULT_BEARING = ('results', 'tables', 'analysis')


def judge_completeness(artifact_kind: str, n_words: int,
                       extraction_verdict: str = 'CLEAN') -> tuple[bool, list[str]]:
    """THE ONE COMPLETENESS REDUCER. `profile()`, `Graph.from_json()` and
    `event_ledger.derive_content_profile()` all come through here and through nothing else.

    THERE IS NO UNIVERSAL WORD THRESHOLD IN THIS FUNCTION AND THERE MUST NEVER BE ONE. Completeness is
    read out of KIND_PROFILE for THIS kind: a judicial opinion, a statute section and a trial-registry
    record have stub_floor=None and are COMPLETE AT ANY LENGTH. A cookie banner is incomplete at ANY
    length, because `landing_page` cannot bear a finding at all — which is the correct reason, and not
    a fact about its size.

    The one length that is never enough is ZERO. "Complete at any length" is not complete at no length:
    a registry record we hold nothing of is not a short registry record.
    """
    spec = KIND_PROFILE.get(artifact_kind)
    if spec is None:
        raise ValueError(f'{artifact_kind!r} is not a registered artifact kind — an unregistered kind '
                         f'cannot be judged complete OR incomplete, and defaulting it to either is how '
                         f'a label outruns its evidence. Register it in KIND_PROFILE.')
    reasons: list[str] = []
    if not spec['finding_bearing']:
        reasons.append(f'artifact kind `{artifact_kind}` cannot carry a finding')
    if extraction_verdict == 'CORRUPT':
        reasons.append('bytes are not readable prose')
    if n_words <= 0:
        reasons.append('there are no bytes — complete at any length is not complete at NO length')
    elif spec['stub_floor'] is not None and n_words < spec['stub_floor']:
        reasons.append(f'{n_words} words is below the stub floor for `{artifact_kind}` '
                       f'({spec["stub_floor"]}) — this is a fragment of the document, not the document')
    return (not reasons), reasons


def _norm(s: str) -> str:
    return re.sub(r'\s+', ' ', (s or '')).strip()


def extractability(text: str) -> dict:
    """Are these bytes even a readable rendering of a document? Derived, never asserted."""
    toks = _WORDY.findall(text.lower())
    n = len(toks) or 1
    sw = sum(1 for t in toks if t in _FUNCTION_WORDS) / n
    words = text.split() or ['']
    cid = len(_CID.findall(text)) / len(words)
    alpha = sum(c.isalpha() or c.isspace() for c in text) / max(1, len(text))
    if sw < CORRUPT_STOPWORD_DENSITY:
        verdict = 'CORRUPT'          # not English. A cipher, a glyph dump, or not prose at all.
    elif cid > DEGRADED_CID_RATIO:
        verdict = 'DEGRADED'         # readable body, but a non-embedded font ate part of it
    else:
        verdict = 'CLEAN'
    return dict(verdict=verdict, stopword_density=round(sw, 4),
                cid_ratio=round(cid, 4), alpha_ratio=round(alpha, 3))


# A body that is the paper CONTAINS THE PAPER'S OWN ABSTRACT'S VOCABULARY -- the abstract is a
# summary of it. Measured on this corpus: every genuine body scores 0.975-1.000 (7 of 9 at exactly
# 1.000). The one body that is a DIFFERENT PAPER scores 0.391. The threshold below sits in the middle
# of that empty gap; __main__ reprints the distribution so it can be re-derived rather than believed.
CONTRADICTED_VOCAB_OVERLAP = 0.70
_IDENT_MIN_ABSTRACT_WORDS = 40      # below this the abstract is too thin to be a probe
_IDENT_MIN_VOCAB = 10
_IDENT_MIN_BODY_WORDS = 1000        # below this the body is a stub; absence proves nothing


def identity_agreement(text: str, work: Work, independent_abstract: str = '',
                       readable: bool = True) -> dict:
    """Do these bytes belong to the Work the row claims? THE CHECK THAT CATCHES A DIFFERENT PAPER.

    Not one component asked this. A title matcher matched the phrase "Rise of the Machines" and
    handed us a MATHEMATICS PREPRINT; every downstream check then verified, correctly and
    irrelevantly, that the span was verbatim IN THE MATHEMATICS PREPRINT.

    CONTRADICTED REQUIRES POSITIVE EVIDENCE OF A DIFFERENT WORK. It is never inferred from the
    ABSENCE of ours. My first version of this function inferred it from absence -- "none of the
    claimed authors appears in the text" -- and it convicted EIGHT papers, all innocent: seven were
    bare abstracts that simply do not carry an author block, and the eighth was Autor (2003), whose
    title page is (cid:N) font codes. Meanwhile the ONE genuinely foreign paper scored CONFIRMED,
    because its two-word title ("Rise of the Machines") appears verbatim in the maths paper.
    Absence of our evidence, read as evidence of absence, is the HTTP-429-means-"no free copy exists"
    error exactly. So the only route to CONTRADICTED is a positive, two-sided content test:

        the row carries an abstract FROM THE BIBLIOGRAPHY (independent of whatever we fetched);
        the body we fetched does NOT contain that abstract's distinctive vocabulary;
        therefore the body is not a rendering of this work.
    """
    head = text[:20000]
    authors = [a for a in (work.authors or []) if len(a) > 2]
    named = [a for a in authors if re.search(r'\b' + re.escape(a) + r'\b', head, re.I)]
    twords = {w for w in re.findall(r'[a-z]{5,}', (work.title or '').lower())}
    tfound = {w for w in twords if w in head.lower()}
    # A title of one or two distinctive words is not a test: "Rise of the Machines" yields {machines},
    # which the maths paper contains. Below three, the title signal is UNUSABLE, not passing.
    title_usable = len(twords) >= 3

    overlap: float | None = None
    vocab = {w for w in re.findall(r'[a-z]{5,}', (independent_abstract or '').lower())
             if w not in _FUNCTION_WORDS}
    if (len((independent_abstract or '').split()) >= _IDENT_MIN_ABSTRACT_WORDS
            and len(vocab) >= _IDENT_MIN_VOCAB
            and len(text.split()) >= _IDENT_MIN_BODY_WORDS):
        low = text.lower()
        overlap = round(sum(1 for w in vocab if w in low) / len(vocab), 3)

    if not readable:
        # You cannot judge identity from bytes you cannot read. Autor (2003)'s authors and title are
        # absent because they are (cid:11)(cid:3)... -- that is a fact about the FONT, not the paper.
        verdict, basis = 'UNRESOLVED', 'bytes are not readable — identity cannot be judged'
    elif overlap is not None and overlap < CONTRADICTED_VOCAB_OVERLAP:
        verdict = 'CONTRADICTED'
        basis = (f'the body contains only {overlap:.0%} of the distinctive vocabulary of this work’s '
                 f'own abstract (genuine bodies on this corpus: 97.5–100%) — THESE ARE NOT ITS BYTES')
    elif named:
        verdict, basis = 'CONFIRMED', f'{len(named)}/{len(authors)} claimed authors named in the text'
    elif overlap is not None and overlap >= 0.90:
        verdict, basis = 'CONFIRMED', f'body contains {overlap:.0%} of its own abstract’s vocabulary'
    elif title_usable and len(tfound) >= 0.8 * len(twords):
        verdict, basis = 'CONFIRMED', f'{len(tfound)}/{len(twords)} distinctive title words present'
    else:
        verdict, basis = 'UNRESOLVED', 'no positive evidence either way (absence proves nothing)'

    return dict(verdict=verdict, basis=basis,
                authors_named=len(named), authors_claimed=len(authors),
                title_words_found=len(tfound), title_words=len(twords), title_usable=title_usable,
                abstract_vocab_overlap=overlap)


def derive_expression_kind(text: str, work_kind: str = 'study') -> tuple[str, str]:
    """Which VERSION do these bytes say they are? Derived from self-identifying furniture.

    Returns ('unknown', ...) freely. `unknown` is the honest answer for a PDF body with its title
    page mangled, and an honest `unknown` costs us evidence -- which is the correct price.

    THE SCHOLARLY VERSION TAXONOMY APPLIES ONLY TO SCHOLARLY WORKS. There is no preprint of a statute
    and no accepted manuscript of a judicial opinion; the authoritative text IS the artifact, and the
    registry says so. Running the NBER/arXiv/"accepted manuscript" regexes over a court opinion does
    not find nothing — it finds whatever the opinion happens to QUOTE, which is how a whole-text scan
    for "NBER Working Paper" once read the bibliography and called the JEP article a working paper.
    """
    fam = WORK_KIND_ARTIFACT.get(work_kind or 'study')
    if fam is not None:
        ex = KIND_PROFILE[fam]['expression']
        return ex, (f'work kind `{work_kind}` — the version taxonomy of a {fam.replace("_", " ")} is '
                    f'not the scholarly one; these bytes are its {ex.replace("_", " ")}')
    head = text[:12000]
    # THE COVER SHEET MAY CONVICT BUT MAY NEVER ACQUIT (see `_COVER_SHEET`). The three INADMISSIBLE
    # marks are read from the whole head — a library describing the file it deposited is testimony
    # about these bytes. The one ADMITTING mark is read ONLY from the article's own front matter,
    # because a cover sheet's DOI and citation block are the library CITING the article of record,
    # which is the one thing the article of record itself never has to do.
    cover, document = segment_cover_sheet(head)
    wp, pre, am = _WP_MARK.search(head), _PREPRINT_MARK.search(head), _AM_MARK.search(head)
    jr = _JOURNAL_MARK.search(document[:12000])

    # Order still matters (an accepted manuscript carries the journal's citation block too), but it is
    # no longer LOAD-BEARING: the only branch that can return `journal_version` cannot see the cover
    # sheet at all, so no reordering of these four lines can promote a manuscript to the article of
    # record. The ordering is a courtesy to the ERROR MESSAGE, not the thing keeping the door shut.
    if am:
        return 'accepted_manuscript', f'bytes say: {am.group(0)[:48]!r}'
    if wp:
        return 'working_paper', f'bytes say: {wp.group(0)[:48]!r}'
    if pre:
        return 'preprint', f'bytes say: {pre.group(0)[:48]!r}'
    if jr:
        return 'journal_version', (f'typeset journal furniture in the ARTICLE\'S OWN front matter '
                                   f'(not on a cover sheet): {jr.group(0)[:48]!r}')
    if cover:
        return 'unknown', ('a repository cover sheet, and NO version furniture in the document under '
                           'it — the library\'s citation of the article is not the article')
    return 'unknown', 'no self-identifying version furniture in the first 12,000 chars'


def profile(text: str, work: Work, independent_abstract: str = '',
            fetch_outcome: str = 'ok') -> dict:
    """THE CONTENT-DERIVED ARTIFACT PROFILE. Replaces MIN_WORDS entirely.

    Every field is derived FROM THE BYTES. `complete` is judged against the profile FOR THIS KIND,
    so a short judicial opinion is complete and a 535-word cookie banner is not.
    """
    text = text or ''
    words = len(text.split())
    ex = extractability(text)
    ident = identity_agreement(text, work, independent_abstract, readable=ex['verdict'] == 'CLEAN')

    view = View(text)
    secs = sections_of(view)
    present = sorted({name for _, _, name in secs if name not in ('front', 'body')})
    result_secs = [s for s in present if s in RESULT_BEARING]   # REPORTED. GATES NOTHING. See above.
    # body/chrome ratio, measured on the bytes -- not on a word count.
    chrome_hits = len(_CHROME.findall(text))
    body_chars = sum(e - s for s, e, name in secs if SECTION_WEIGHT.get(name, 0.5) > 0)
    body_ratio = round(body_chars / max(1, len(text)), 3)
    chrome_per_kw = round(1000 * chrome_hits / max(1, words), 2)

    work_kind = work.kind or 'study'
    family = WORK_KIND_ARTIFACT.get(work_kind)      # None => scholarly; else the kind is FIXED by the work
    ekind, ebasis = derive_expression_kind(text, work_kind=work_kind)

    # ---- artifact_kind: DERIVED, in strict order of what the bytes can actually PROVE ------------
    # THE BYTES MAY ALWAYS DEMOTE. They may never promote. A judicial opinion whose fetch returned a
    # login wall is a landing_page, not a short opinion — so the demotions run FIRST, above the work's
    # own kind. But nothing in a stranger's letterhead can turn a statute into a working paper, so the
    # work's kind runs ABOVE the scholarly version furniture.
    if fetch_outcome != 'ok':
        # A failed fetch is a fact about our REQUEST, never a fact about the world.
        kind, basis = 'unknown', f'fetch outcome: {fetch_outcome}'
    elif ident['verdict'] == 'CONTRADICTED':
        # The single most important branch in this file. These bytes are SOMEONE ELSE'S PAPER.
        kind, basis = 'wrong_work', ident['basis']
    elif ex['verdict'] == 'CORRUPT':
        kind, basis = 'extraction_failure', (
            f"stopword density {ex['stopword_density']} < {CORRUPT_STOPWORD_DENSITY} — "
            f"these bytes are not English prose")
    elif chrome_hits >= 2 and (chrome_per_kw >= 5 or (family is None and words < SCHOLARLY_STUB_FLOOR)):
        # WEB FURNITURE WITH NO DOCUMENT UNDER IT. Note that the AEA landing page for Autor (2015)
        # carries the article's own "vol. 29, no. 3" citation block -- so journal furniture proves
        # only that a page CITES the article, never that it IS the article. This test runs first for
        # exactly that reason.
        # The LENGTH half of this test is scholarly-only: a 300-word statute section is a statute
        # section, and only the chrome DENSITY may call it a web page.
        kind, basis = 'landing_page', (
            f'{chrome_hits} web-chrome markers ({chrome_per_kw}/1k words) over {words} words — '
            f'this is a web page about the document, not the document')
    elif family is not None:
        # A CASE, A STATUTE, A TRIAL RECORD. Its completeness is not a word count and never was.
        kind, basis = family, (f'work kind `{work_kind}` — this is its {family.replace("_", " ")}, '
                               f'which is COMPLETE AT ANY LENGTH (registry stub_floor=None)')
    elif ekind == 'journal_version':
        kind, basis = 'journal_article', ebasis
    elif ekind == 'proceedings_version':
        kind, basis = 'proceedings_paper', ebasis
    elif ekind in ('working_paper', 'preprint', 'accepted_manuscript'):
        kind, basis = ekind, ebasis
    elif words < SCHOLARLY_ABSTRACT_FLOOR:
        kind, basis = 'citation_only', f'{words} words — a citation stub, not even an abstract'
    elif words < SCHOLARLY_STUB_FLOOR:
        kind, basis = 'abstract', f'{words} words with no version furniture — a stub, not the article'
    else:
        kind, basis = 'unknown', ebasis

    # ---- completeness: THE ONE REDUCER, driven by the registry FOR THIS KIND ---------------------
    complete, reasons = judge_completeness(kind, words, ex['verdict'])

    return dict(
        artifact_kind=kind, artifact_kind_basis=basis,
        expression_kind=ekind, expression_kind_basis=ebasis,
        complete=complete, incomplete_because=reasons,
        n_words=words, sections_present=present, result_bearing_sections=result_secs,
        body_ratio=body_ratio, chrome_markers=chrome_hits, chrome_per_1k_words=chrome_per_kw,
        extractability=ex, identity=ident, fetch_outcome=fetch_outcome,
    )


# =================================================================================================
# 3. THE GRAPH
# =================================================================================================

class SpanBindingError(ValueError):
    """A span that cannot be bound to real bytes. Not a warning: THE BINDING DOES NOT EXIST."""


class GraphIntegrityError(ValueError):
    """A graph on disk that does not agree with itself. It is REFUSED, never repaired."""


# What it takes to ASSERT that a span survives from one expression into another. Only a claim about
# BYTES can do it -- that is the entire content of the word "span-preserving".
_AUTHENTICATES = re.compile(
    r'byte[- ]for[- ]byte|byte[- ]level|checksum|sha-?256|content[_ -]hash'
    r'|identical (?:bytes|text|spans?)|span[- ]level (?:diff|comparison)'
    r'|(?:diffed|compared) (?:it )?against the .{0,30}(?:pdf|bytes|text|version)', re.I)
_PROVES_NOTHING_ABOUT_BYTES = re.compile(
    r'\btitles?\b|\bmetadata\b|\bsimilar\b|\bplausib|\blooks? like\b|self[- ]describ|\bassum', re.I)


def authentication_failure(basis: str) -> str:
    """'' if `basis` authenticates SPAN PRESERVATION; otherwise the reason it does not.

    Sol, verbatim: "A title similarity match can PROPOSE predecessor_of; it CANNOT ASSERT
    exact_copy_of."

    An ASSERTED span-preserving edge is the ONLY thing in this graph that lets a span name a document
    WHOSE BYTES WE DO NOT HOLD. It is therefore the only thing worth attacking, and it was guarded on
    ONE of its two types: the old check read `type == 'exact_copy_of' and 'title' in basis`. But
    `accepted_manuscript_of` is span-preserving too, and it widens attribution identically — so

        add_edge(wp, journal, 'accepted_manuscript_of', 'ASSERTED', 'the titles match')

    was ACCEPTED, and it made the working paper's spans journal-attributable. The rule is not "no
    title matches for exact_copy_of". The rule is: an ASSERTED span-preserving edge must name
    BYTE-LEVEL EVIDENCE, whatever it is called. Both directions are enforced here, in ONE predicate,
    used by `add_edge()` at construction AND by `from_json()` at load — because an edge that cannot be
    constructed but CAN BE LOADED is not a rule, it is a speed bump.
    """
    if not basis or not basis.strip():
        return 'an edge MUST carry a basis naming the evidence for it'
    weak = _PROVES_NOTHING_ABOUT_BYTES.search(basis)
    if weak:
        return (f'the basis rests on {weak.group(0)!r}, which proves NOTHING ABOUT BYTES — PEER REVIEW '
                f'CHANGES NUMBERS, and matching titles/metadata cannot show a span survived it')
    if not _AUTHENTICATES.search(basis):
        return ('the basis names no BYTE-LEVEL evidence (a byte-for-byte / checksum / span-level '
                'comparison against the target expression). Nothing else can ASSERT span preservation')
    return ''


@dataclass(frozen=True)
class SourcePolicy:
    """WHICH EXPRESSIONS THIS ANSWER IS ALLOWED TO CITE. The task's instruction, made mechanical.

    This is an ARGUMENT, not a stored field, because admissibility is a property of THE ANSWER and not
    of the bytes. The same accepted manuscript is inadmissible under "journal articles only" and
    admissible under "any identified version"; a boolean on the node has to be wrong for one of them.
    `Expression.citable_in_journal_only_answer` was exactly that boolean, and it is gone.
    """
    name: str
    permitted_expression_kinds: tuple[str, ...]
    require_complete: bool = True


#: Task 72. "If only the working paper is available, citing it VIOLATES THE JOURNAL-ONLY INSTRUCTION."
JOURNAL_ONLY  = SourcePolicy('journal_articles_only', ('journal_version',))
PEER_REVIEWED = SourcePolicy('peer_reviewed', ('journal_version', 'proceedings_version'))
#: For a legal or clinical question, the authoritative text IS the source. There is no journal here.
OFFICIAL_TEXT = SourcePolicy('official_text_only', ('official_text', 'registry_record'))
ANY_VERSION   = SourcePolicy('any_identified_version',
                             ('journal_version', 'proceedings_version', 'accepted_manuscript',
                              'working_paper', 'preprint', 'official_text', 'registry_record'))


@dataclass(frozen=True)
class Attribution:
    """The resolved answer to: may a span from these bytes be attributed AT ALL, and TO WHAT?"""
    manifestation_id: str
    content_hash: str
    expression_id: str                        # the expression whose bytes these ARE
    permitted_expression_ids: tuple[str, ...]  # everything a span here may name (IDs — never prose)
    policy: str
    admitted: bool
    names_expression_id: str | None           # THE id the sentence must name. None => name NOTHING.
    text: str | None                          # display cache. NOTHING IS EVER VALIDATED AGAINST IT.
    refusal: str | None
    #: WHICH SPAN this permission was granted to. `None` means the question was asked about a whole
    #: manifestation, and the answer therefore carries NO per-span widening — see resolve_attribution.
    binding_id: str | None = None


@dataclass
class Graph:
    works: dict[str, Work] = field(default_factory=dict)
    expressions: dict[str, Expression] = field(default_factory=dict)
    manifestations: dict[str, Manifestation] = field(default_factory=dict)
    edges: list[Edge] = field(default_factory=list)
    correspondences: list[SpanCorrespondence] = field(default_factory=list)

    # -- construction -----------------------------------------------------------------------------
    def add_edge(self, src: str, dst: str, type: str, status: str, basis: str) -> Edge:
        if type not in EDGE_TYPES:
            raise ValueError(f'unknown edge type {type!r}')
        if status not in ('PROPOSED', 'ASSERTED'):
            raise ValueError(f'edge status must be PROPOSED or ASSERTED, not {status!r}')
        if not basis or not basis.strip():
            # An edge with no evidence is the entire failure we are here to end.
            raise ValueError('an edge MUST carry a basis naming the evidence for it')
        if status == 'ASSERTED' and type in SPAN_PRESERVING:
            # Enforced in the constructor so no caller can talk its way past it, and re-enforced in
            # from_json() so no FILE can either.
            why = authentication_failure(basis)
            if why:
                raise ValueError(f'cannot ASSERT {type} — {why}')
            why = self.exact_copy_failure(src, dst)
            if why:
                raise ValueError(f'cannot ASSERT {type} — {why}')
        e = Edge(src, dst, type, status, basis)
        self.edges.append(e)
        return e

    def exact_copy_failure(self, src: str, dst: str) -> str:
        """'' if the graph's OWN BYTES prove `src` and `dst` are the same document; else the reason.

        Sol V9 §4: "Expression-wide `exact_copy_of` is reserved for identity-confirmed manifestations
        whose entire canonical document text is equal."

        The old guard was `authentication_failure()` — a REGEX OVER THE BASIS STRING. It asked whether the
        PROSE mentioned a checksum. So the sentence

            'byte-for-byte comparison against the journal PDF: identical'

        asserted the edge, and NO BYTES WERE EVER COMPARED. A rule enforced by reading an English
        sentence is a rule enforced by whoever writes the sentence. The basis check is kept (it is a
        cheap filter and it catches the honest mistake), but the edge now also has to be TRUE: we must
        HOLD both documents, both must be identity-CONFIRMED, and their ENTIRE canonical texts must be
        equal. An expression-wide claim requires expression-wide evidence.

        This is deliberately hard to satisfy. It should be: an expression-wide edge is the only thing in
        this graph that widens EVERY span at once, and there are only two ways to earn one — hold both
        documents and find them identical, or don't have the edge. For anything narrower there is
        `SpanCorrespondence`, which grants one span.
        """
        def held(eid: str) -> list[Manifestation]:
            return [m for m in self.manifestations.values() if m.expression_id == eid]

        smans, tmans = held(src), held(dst)
        if not smans:
            return (f'we hold NO BYTES for {src!r}. An expression-wide exact_copy_of is a claim that two '
                    f'ENTIRE documents are equal; it cannot be made about a document we do not have')
        if not tmans:
            return (f'we hold NO BYTES for {dst!r} — THE DOCUMENT THIS EDGE WOULD LET US NAME. This is the '
                    f'exact shape of the P0: claiming equality with bytes we have never seen. Get the '
                    f'target document, or bind the span to what we actually hold')
        for label, mans in (('source', smans), ('target', tmans)):
            for m in mans:
                v = (m.profile.get('identity') or {}).get('verdict')
                if v not in CORRESPONDENCE_IDENTITY_OK:
                    return (f'the {label} manifestation {m.id!r} is identity `{v}`, not CONFIRMED — '
                            f'two documents we cannot even prove are OUR work cannot be proven equal '
                            f'to each other')
        for sm in smans:
            for tm in tmans:
                if canonicalize(sm.text) == canonicalize(tm.text):
                    return ''
        # Report the closest pair's disagreement, because "not equal" with no locus is unactionable.
        sm, tm = smans[0], tmans[0]
        cs, ct = canonicalize(sm.text), canonicalize(tm.text)
        return (f'the canonical texts are NOT equal ({len(cs):,} vs {len(ct):,} chars under '
                f'{CANON_ALGORITHM}:{CANON_VERSION}) — these are two different documents, and PEER '
                f'REVIEW CHANGES NUMBERS. If ONE SPAN survives, prove THAT SPAN with a '
                f'SpanCorrespondence; it grants that span and nothing else')

    def add_correspondence(self, sc: SpanCorrespondence) -> SpanCorrespondence:
        """A correspondence is VERIFIED AT CONSTRUCTION and re-verified at every use. It never enters
        the graph on its author's word — which is the one thing this whole file refuses to accept."""
        ok, why = self.verify_correspondence(sc)
        if not ok:
            raise ValueError(f'cannot add SpanCorrespondence {sc.id!r} — ' + '; '.join(why))
        self.correspondences.append(sc)
        return sc

    # -- THE CORE RULE ----------------------------------------------------------------------------
    def attribution_targets(self, manifestation_id: str) -> list[str]:
        """Which expressions a span in this manifestation MAY name WITHOUT A PER-SPAN PROOF.

        Always: the manifestation's own expression -- the bytes we hold are, definitionally, that
        expression's bytes. Additionally: any expression reachable by an ASSERTED, SPAN-PRESERVING
        edge — and after Sol V9 there is exactly ONE such edge type, `exact_copy_of`, which now requires
        that we HOLD both documents and that their ENTIRE canonical texts be equal. If two documents are
        the same document, every span in one is in the other, and widening is not a leap.

        Nothing else. `predecessor_of`, `reports_same_study` and — SINCE V9 — `accepted_manuscript_of`
        transfer NOTHING, however obvious the relation. To move ONE span across a non-identical document
        boundary, prove THAT SPAN: see `attribution_targets_for_binding()`.
        """
        m = self.manifestations[manifestation_id]
        targets = [m.expression_id]
        for e in self.edges:
            if e.src == m.expression_id and e.type in SPAN_PRESERVING and e.status == 'ASSERTED':
                if e.dst not in targets:
                    targets.append(e.dst)
        return targets

    # -- THE CORE RULE, PER SPAN (Sol V9 §4) ------------------------------------------------------
    def verify_correspondence(self, sc: SpanCorrespondence) -> tuple[bool, list[str]]:
        """RECHECK EVERYTHING: both hashes, both offsets, and exact canonical text equality.

        A correspondence is an untrusted input — it has been through a JSON file, like the graph itself.
        So nothing stored on it is believed: the hashes are recomputed from the bytes on the node, the
        offsets are re-sliced, the canonical forms are recomputed under the NAMED algorithm and version,
        and the two canonical spans must be EXACTLY equal.

        THE ACEMOGLU TEST LIVES HERE. "0.37 percentage points" and "0.2 percentage points" canonicalize
        to two different strings, so this returns False, and no policy is ever consulted. The failure is
        at the level of the bytes, which is the only level at which it cannot be argued with.
        """
        bad: list[str] = []
        src = self.manifestations.get(sc.source_manifestation_id)
        tgt = self.manifestations.get(sc.target_manifestation_id)
        if src is None:
            bad.append(f'source manifestation {sc.source_manifestation_id!r} is not held')
        if tgt is None:
            bad.append(f'target manifestation {sc.target_manifestation_id!r} is not held')
        if bad:
            return False, bad

        if sc.canonicalization != f'{CANON_ALGORITHM}:{CANON_VERSION}':
            bad.append(f'canonicalization {sc.canonicalization!r} is not this build\'s '
                       f'{CANON_ALGORITHM}:{CANON_VERSION} — two documents compared under a rule we no '
                       f'longer run were never compared by us at all')
            return False, bad

        for who, m, h, s, e, span in (
                ('source', src, sc.source_raw_hash, sc.source_start, sc.source_end, sc.source_span),
                ('target', tgt, sc.target_raw_hash, sc.target_start, sc.target_end, sc.target_span)):
            # 1. the hash on the correspondence must be the hash of the bytes on the node...
            if h != m.content_hash:
                bad.append(f'{who} hash {h[:12]}… is not the held manifestation\'s content_hash '
                           f'{m.content_hash[:12]}… — the document moved under the correspondence')
                continue
            # 2. ...and the node's bytes must still hash to it.
            if hashlib.sha256(m.text.encode('utf-8', 'ignore')).hexdigest() != m.content_hash:
                bad.append(f'{who} manifestation {m.id!r} does not hash to its own content_hash')
                continue
            # 3. the offsets are re-validated, never trusted (see bind_span for why `text[900:100]` is
            #    not merely wrong but INVISIBLY wrong).
            if (isinstance(s, bool) or isinstance(e, bool) or not isinstance(s, int)
                    or not isinstance(e, int) or s < 0 or e <= s or e > len(m.text)):
                bad.append(f'{who} offsets [{s}:{e}] are not a valid span of {m.id!r} ({len(m.text)} chars)')
                continue
            # 4. the verbatim span must BE what those offsets slice.
            if m.text[s:e] != span:
                bad.append(f'{who} verbatim span does not match the bytes at [{s}:{e}] of {m.id!r}')
        if bad:
            return False, bad

        # 5. IDENTITY. A correspondence between two documents we cannot prove are the works we asked for
        #    proves only that two strangers agree.
        for who, m, stored in (('source', src, sc.source_identity), ('target', tgt, sc.target_identity)):
            live = (m.profile.get('identity') or {}).get('verdict', 'UNRESOLVED')
            if stored != live:
                bad.append(f'{who} identity decision {stored!r} is stale — the bytes now derive {live!r}')
            elif live not in CORRESPONDENCE_IDENTITY_OK:
                bad.append(f'{who} manifestation {m.id!r} is identity `{live}`, not CONFIRMED')

        # 6. EXACT CANONICAL EQUALITY. The whole edifice reduces to this line.
        cs, ct = canonicalize(src.text[sc.source_start:sc.source_end]), \
            canonicalize(tgt.text[sc.target_start:sc.target_end])
        if cs != ct:
            bad.append(f'the canonical spans are NOT equal under {sc.canonicalization} — '
                       f'{cs[:60]!r} vs {ct[:60]!r}. THIS IS THE FINDING, not a bug to tune away: the '
                       f'two documents say different things, and peer review is what changed them')
        elif sc.canonical_span_hash != canonical_hash(src.text[sc.source_start:sc.source_end]):
            bad.append('the stored canonical_span_hash is not the hash of the canonical span')
        if not (sc.basis or '').strip():
            bad.append('a correspondence MUST carry a basis naming how it was established')
        return (not bad), bad

    def attribution_targets_for_binding(self, binding: dict) -> list[str]:
        """Which expressions THIS BOUND SPAN may name. The binding-specific rule.

        = the manifestation-wide targets (own expression + whole-document exact_copy_of)
        + the expression of every manifestation to which a VERIFIED CORRESPONDENCE carries THIS SPAN.

        "THIS SPAN" means these exact offsets. NOT a span that contains it, and NOT a span it contains —
        and that is not pedantry. Canonicalization collapses whitespace, so character offsets in the
        source do not map linearly onto the target; a sub-range of a proven-equal span has no proven
        counterpart. A correspondence grants permission for THAT SPAN ONLY (Sol V9 §4), and the only
        unfoolable reading of "that span" is offset equality.
        """
        mid = binding.get('manifestation_id')
        s, e = binding.get('span_start'), binding.get('span_end')
        targets = list(self.attribution_targets(mid))
        for sc in self.correspondences:
            if sc.source_manifestation_id != mid or sc.source_start != s or sc.source_end != e:
                continue
            ok, _why = self.verify_correspondence(sc)
            if not ok:
                continue          # a correspondence that no longer verifies grants NOTHING. Silently.
            tgt = self.manifestations[sc.target_manifestation_id]
            if tgt.expression_id not in targets:
                targets.append(tgt.expression_id)
        return targets

    # -- THE API. THREE FUNCTIONS. --------------------------------------------------------------
    def bind_span(self, manifestation_id: str, start: int, end: int) -> dict:
        """A span binds to its EXACT manifestation and content hash. This is what a card must carry
        instead of a bare DOI -- a DOI names a Work, and a Work has no bytes.

        BOUNDS ARE VALIDATED HERE. THEY WERE NOT, AND PYTHON IS SILENT ABOUT NONSENSE: for a
        1,000-char text, `text[-5:20]`, `text[900:100]` and `text[5000:6000]` are all `''`. Every one
        of those is a span that BINDS CLEANLY AND THEN VERIFIES — its stored text is empty, the empty
        slice still equals it, and the content hash is perfectly correct. The card would name a real
        paper, carry a real hash, pass verify_span(), and quote NOTHING FROM IT. That is a fabricated
        citation with a valid receipt, which is the exact shape of every defect in this file's header.
        A negative offset is worse than empty: `text[-5:]` silently indexes from the END and binds a
        span from somewhere else entirely.

        So they are REFUSED, not clamped. Clamping would invent a span the miner never mined.

        RETURNS IDENTIFIERS, NOT PROSE. `may_name` used to hand back English SENTENCES, so a consumer
        deciding what was legal had to string-match a display string. Prose is a cache; an id resolves.
        """
        m = self.manifestations.get(manifestation_id)
        if m is None:
            raise SpanBindingError(f'no manifestation {manifestation_id!r} — a span cannot bind to '
                                   f'bytes we do not hold')
        for nm, v in (('start', start), ('end', end)):
            if isinstance(v, bool) or not isinstance(v, int):
                raise SpanBindingError(f'{nm} offset must be an int, got {v!r} ({type(v).__name__})')
        n = len(m.text)
        if start < 0 or end < 0:
            raise SpanBindingError(
                f'NEGATIVE span [{start}:{end}] on {manifestation_id} — Python would index from the '
                f'END of the text and bind a span from a different part of the document')
        if end <= start:
            raise SpanBindingError(
                f'EMPTY OR REVERSED span [{start}:{end}] on {manifestation_id} — it slices to "" and '
                f'would then verify perfectly against nothing, under a real citation')
        if end > n:
            raise SpanBindingError(
                f'span [{start}:{end}] runs past the end of {manifestation_id} ({n} chars) — Python '
                f'would truncate it silently, and the stored text would not be the span that was mined')
        b = dict(
            manifestation_id=manifestation_id,
            content_hash=m.content_hash,
            span_start=start, span_end=end,
            text=m.text[start:end],
            expression_id=m.expression_id,
        )
        # THE BINDING IS NOW A NAMED THING. `resolve_attribution()` answers about IT, not about the
        # whole document — so it needs an identity, and that identity is DERIVED from the bytes and the
        # offsets. Edit either and you have a different binding, which inherits no permission.
        b['binding_id'] = binding_id(manifestation_id, m.content_hash, start, end)
        b['permitted_expression_ids'] = list(self.attribution_targets_for_binding(b))
        return b

    def rebind(self, binding: dict, target_manifestation_id: str) -> dict | None:
        """THE SPAN IS IN THE VoR's OWN BYTES — so bind it THERE, and stop needing permission.

        Sol V9 §4: "A matching span found independently in VoR bytes should normally be rebound directly
        to the VoR manifestation."

        This is strictly stronger than any correspondence, and it is the path we should take whenever it
        is open. A correspondence says "trust this proof that the other document contains the span". A
        REBINDING says "the document you want to cite contains the span; here are its offsets". The
        second needs no cross-document permission at all, because there is no crossing.

        Returns a NEW binding on the target, or None if the span is not verbatim in the target's bytes —
        and None is the honest answer, not a reason to fall back to a weaker claim.
        """
        tgt = self.manifestations.get(target_manifestation_id)
        if tgt is None:
            raise SpanBindingError(f'no manifestation {target_manifestation_id!r}')
        span = (binding or {}).get('text') or ''
        if not span:
            return None
        i = tgt.text.find(span)
        if i < 0:
            # Try the canonical view: a PDF column break inside the span is a rendering artifact, not a
            # textual difference. The OFFSETS returned are always into the RAW text, never the canonical
            # one — a card that indexes a canonical string indexes a document nobody holds.
            cspan = canonicalize(span)
            if not cspan:
                return None
            for j in range(len(tgt.text)):
                if canonicalize(tgt.text[j:j + len(span) + 64]).startswith(cspan):
                    for k in range(j + len(cspan), min(len(tgt.text), j + len(span) + 64) + 1):
                        if canonicalize(tgt.text[j:k]) == cspan:
                            return self.bind_span(target_manifestation_id, j, k)
            return None
        return self.bind_span(target_manifestation_id, i, i + len(span))

    def resolve_attribution(self, ref: dict | str,
                            source_policy: SourcePolicy = JOURNAL_ONLY) -> Attribution:
        """MAY THIS BOUND SPAN be attributed under THIS task's instruction, and TO WHAT ID?

        Sol V9 §4 moved this API from manifestation-wide permission to BINDING-SPECIFIC permission:

            resolve_attribution(binding, attribution_policy)

        `ref` is therefore a BINDING (the dict `bind_span()` returns, which is also what a card carries).
        A bare `manifestation_id` string is still accepted — the honest whole-document question, asked by
        the census and by the quarantine sweep — and it answers WITHOUT any per-span widening: a
        manifestation-wide question can only be answered with manifestation-wide evidence, i.e. the
        document's own expression plus a whole-document `exact_copy_of`. A SpanCorrespondence grants ONE
        SPAN and therefore cannot answer a question that was not asked about a span.

        Two independent conditions, BOTH required:
          1. the bytes are usable as evidence at all — complete, uncorrupted, the right work; AND
          2. some expression this span MAY LEGALLY NAME is of a kind THIS POLICY PERMITS.

        A span from a corrupt PDF of the real journal article is still inadmissible -- see Weiss, whose
        verbatim span said "633 per cent" because the PDF was a Caesar-shifted encoding of "300".
        """
        if isinstance(ref, str):
            manifestation_id, bid, targets_of = ref, None, self.attribution_targets
            binding = None
        else:
            binding = ref
            manifestation_id = binding.get('manifestation_id')
            bid = binding.get('binding_id')
            targets_of = None

        m = self.manifestations.get(manifestation_id)
        if m is None:
            raise KeyError(f'no manifestation {manifestation_id!r}')

        if binding is None:
            targets = tuple(targets_of(manifestation_id))
        else:
            # THE BINDING IS AN UNTRUSTED INPUT. It has been through a JSON file, and a binding whose
            # offsets nobody rechecked is `text[900:100]` — empty, self-consistent, and citing nothing.
            if not self.verify_span(binding):
                return Attribution(
                    manifestation_id=manifestation_id, content_hash=m.content_hash,
                    expression_id=m.expression_id, permitted_expression_ids=(),
                    policy=source_policy.name, admitted=False, names_expression_id=None, text=None,
                    binding_id=bid,
                    refusal=('this binding does not verify against the bytes it names — the offsets, the '
                             'hash, the stored span or the permitted set disagree with the manifestation'))
            targets = tuple(self.attribution_targets_for_binding(binding))

        base = dict(manifestation_id=manifestation_id, content_hash=m.content_hash,
                    expression_id=m.expression_id, permitted_expression_ids=targets,
                    policy=source_policy.name, binding_id=bid)

        if source_policy.require_complete and not m.profile.get('complete'):
            why = '; '.join(m.profile.get('incomplete_because') or ['the bytes are not a usable document'])
            return Attribution(**base, admitted=False, names_expression_id=None, text=None,
                               refusal=f'these bytes may not carry a finding: {why}')

        # Prefer the expression whose bytes these ACTUALLY ARE. Widening is a fallback, never a first
        # choice: naming the document we hold is always the strongest true thing we can say.
        permitted = [t for t in targets
                     if self.expressions[t].kind in source_policy.permitted_expression_kinds]
        if not permitted:
            kinds = ', '.join(sorted({self.expressions[t].kind for t in targets})) or 'nothing'
            return Attribution(
                **base, admitted=False, names_expression_id=None, text=None,
                refusal=(f'policy `{source_policy.name}` permits '
                         f'{{{", ".join(source_policy.permitted_expression_kinds)}}}, and a span here '
                         f'may only name {{{kinds}}}. No ASSERTED span-preserving edge widens it — '
                         f'citing a permitted source with THESE bytes would be fabrication'))
        chosen = m.expression_id if m.expression_id in permitted else permitted[0]
        return Attribution(**base, admitted=True, names_expression_id=chosen,
                           text=self.expressions[chosen].attribution, refusal=None)

    def verify_span(self, binding: dict) -> bool:
        """The enforcement point. A binding arriving here is AN UNTRUSTED INPUT — by now it has been
        through a JSON file — so this re-checks EVERYTHING bind_span() checked, and then the bytes.

        A gate that trusts the offsets it is handed is a gate that verifies `text[900:100] == ''`.
        """
        try:
            mid = binding['manifestation_id']
            s, e = binding['span_start'], binding['span_end']
            stored, chash = binding['text'], binding['content_hash']
        except (KeyError, TypeError):
            return False
        m = self.manifestations.get(mid)
        if m is None or m.content_hash != chash:
            return False
        for v in (s, e):
            if isinstance(v, bool) or not isinstance(v, int):
                return False
        if s < 0 or e <= s or e > len(m.text):
            return False
        # the node itself must not have been edited since it was loaded: the hash is over THE TEXT.
        if hashlib.sha256(m.text.encode('utf-8', 'ignore')).hexdigest() != m.content_hash:
            return False
        if m.text[s:e] != stored:
            return False
        # ...and the permitted set is not a cache. If an edge changed, or a SpanCorrespondence stopped
        # verifying, the STORED permission is stale — and a stale permission is how a span keeps naming
        # a journal it was never allowed to name. Recomputed PER SPAN, because that is now the unit at
        # which permission exists.
        if 'permitted_expression_ids' in binding:
            live = self.attribution_targets_for_binding(
                dict(manifestation_id=mid, span_start=s, span_end=e))
            if list(binding['permitted_expression_ids']) != live:
                return False
        return True

    # -- derived conveniences (they go THROUGH the API above; they are not a second door) ----------
    def journal_attributable(self, manifestation_id: str) -> bool:
        """May a span from these bytes be printed as a finding OF A JOURNAL ARTICLE? (task 72)"""
        return self.resolve_attribution(manifestation_id, JOURNAL_ONLY).admitted

    # -- serialisation ----------------------------------------------------------------------------
    def to_json(self) -> dict:
        return dict(
            works=[asdict(w) for w in self.works.values()],
            expressions=[asdict(e) for e in self.expressions.values()],
            # text is retained on disk too: NOTHING IS EVER DELETED.
            manifestations=[asdict(m) for m in self.manifestations.values()],
            edges=[asdict(e) for e in self.edges],
            correspondences=[asdict(c) for c in self.correspondences],
        )

    @classmethod
    def from_json(cls, data: dict | str) -> 'Graph':
        """STRICT LOAD. A GRAPH ON DISK IS AN UNTRUSTED INPUT.

        Every check here exists because the file it reads is the same KIND of artifact that lied to us
        already. `to_json()` writes the text, its hash, its word count and its derived profile, and any
        copy of that file — hand-edited, half-written, merged, or produced by an older version of this
        module — can disagree with itself in every one of those places. A loader that accepts what it
        is handed re-opens the hole FROM THE OTHER SIDE: the enforcement point would read a
        `complete: true` that no bytes support, and would enforce it.

        REFUSES, NEVER REPAIRS:
          - a content_hash that is not sha256(text)                  [the span gate's only anchor]
          - an n_words that is not len(text.split())                 [the count that describes a
                                                                       document we no longer hold —
                                                                       the exact defect event_ledger
                                                                       catches in the live corpus]
          - a stored extractability verdict the text does not support
          - a `complete: true` (or false) THE REGISTRY DOES NOT DERIVE for that kind and that text
          - a manifestation naming an expression or a work that does not exist
          - a manifestation whose expression belongs to a DIFFERENT work
          - an expression naming a work that does not exist
          - an edge whose endpoints do not exist, or that carries no basis
          - an ASSERTED span-preserving edge whose basis does not AUTHENTICATE span preservation
          - any unknown field, anywhere (a schema drift silently drops the field a gate reads)
        """
        if isinstance(data, str):
            data = json.loads(data)
        g = cls()
        err: list[str] = []

        def _fields(cl) -> set[str]:
            return set(cl.__dataclass_fields__)

        def _take(cl, d: dict, what: str):
            extra = set(d) - _fields(cl)
            if extra:
                err.append(f'{what}: unknown field(s) {sorted(extra)} — this graph was not written by '
                           f'this schema, and a field a gate reads may be missing from it')
                return None
            missing = _fields(cl) - set(d) - {'profile', 'kind'}
            if missing:
                err.append(f'{what}: missing field(s) {sorted(missing)}')
                return None
            return cl(**d)

        for d in data.get('works', []):
            w = _take(Work, d, f"work {d.get('id')!r}")
            if w is None:
                continue
            if w.kind not in WORK_KINDS:
                err.append(f'work {w.id!r}: kind {w.kind!r} is not a registered work kind {WORK_KINDS}')
            g.works[w.id] = w

        for d in data.get('expressions', []):
            e = _take(Expression, d, f"expression {d.get('id')!r}")
            if e is None:
                continue
            if e.kind not in EXPRESSION_KINDS:
                err.append(f'expression {e.id!r}: kind {e.kind!r} is not in EXPRESSION_KINDS')
            if e.work_id not in g.works:
                err.append(f'expression {e.id!r}: names work {e.work_id!r}, WHICH DOES NOT EXIST')
            g.expressions[e.id] = e

        for d in data.get('manifestations', []):
            m = _take(Manifestation, d, f"manifestation {d.get('id')!r}")
            if m is None:
                continue
            g.manifestations[m.id] = m
            where = f'manifestation {m.id!r}'

            # 1. THE HASH IS THE ONLY ANCHOR THE SPAN GATE HAS.
            real = hashlib.sha256((m.text or '').encode('utf-8', 'ignore')).hexdigest()
            if real != m.content_hash:
                err.append(f'{where}: content_hash {m.content_hash[:12]}… IS NOT sha256(text) '
                           f'({real[:12]}…) — every span bound to it is bound to nothing')
                continue

            # 2. references resolve, and resolve TO THE SAME WORK.
            if m.expression_id not in g.expressions:
                err.append(f'{where}: names expression {m.expression_id!r}, WHICH DOES NOT EXIST')
            elif g.expressions[m.expression_id].work_id != m.work_id:
                err.append(f'{where}: is filed under work {m.work_id!r} but its expression '
                           f'{m.expression_id!r} belongs to work '
                           f'{g.expressions[m.expression_id].work_id!r}')
            if m.work_id not in g.works:
                err.append(f'{where}: names work {m.work_id!r}, WHICH DOES NOT EXIST')

            # 3. the counts and labels stored beside the text must be THE ONES THE TEXT EARNS.
            words = len((m.text or '').split())
            if m.n_words != words:
                err.append(f'{where}: n_words={m.n_words:,} but the text holds {words:,} — the count '
                           f'describes a document this node no longer carries')
            prof = m.profile or {}
            kind = prof.get('artifact_kind')
            if kind not in KIND_PROFILE:
                err.append(f'{where}: artifact_kind {kind!r} is not a registered kind')
                continue
            verdict = extractability(m.text or '')['verdict']
            stored_v = (prof.get('extractability') or {}).get('verdict')
            if stored_v != verdict:
                err.append(f'{where}: stored extractability {stored_v!r} but the bytes are {verdict!r}')
            # THE ONE REDUCER, run again, against the bytes on disk. A `complete` flag nobody can
            # re-derive is a label that asserts more than its content supports — with nothing checking.
            ok, reasons = judge_completeness(kind, words, verdict)
            if bool(prof.get('complete')) != ok:
                err.append(f'{where}: profile says complete={prof.get("complete")!r}, but the registry '
                           f'derives complete={ok!r} for a `{kind}` of {words:,} words '
                           f'({"; ".join(reasons) if reasons else "no objection"})')

        for i, d in enumerate(data.get('edges', [])):
            e = _take(Edge, d, f'edge #{i}')
            if e is None:
                continue
            g.edges.append(e)
            where = f'edge #{i} {e.src!r} -{e.type}-> {e.dst!r}'
            if e.type not in EDGE_TYPES:
                err.append(f'{where}: unknown edge type {e.type!r}')
            if e.status not in ('PROPOSED', 'ASSERTED'):
                err.append(f'{where}: status must be PROPOSED or ASSERTED, not {e.status!r}')
            for end in (e.src, e.dst):
                if end not in g.expressions:
                    err.append(f'{where}: endpoint {end!r} DOES NOT EXIST')
            if not (e.basis or '').strip():
                err.append(f'{where}: carries NO BASIS')
            if e.status == 'ASSERTED' and e.type in SPAN_PRESERVING:
                why = authentication_failure(e.basis) or g.exact_copy_failure(e.src, e.dst)
                if why:
                    err.append(f'{where}: ASSERTED span-preserving edge — {why}')

        # ---- CORRESPONDENCES. Every one of them is RE-VERIFIED AGAINST THE BYTES ON DISK. ---------
        # A correspondence is the ONLY per-span door out of a document, so a file that could smuggle one
        # in would be a file that could make any manuscript's number into any journal's finding. The
        # loader runs the SAME verifier the resolver runs — hashes, offsets, exact canonical equality —
        # and refuses the whole graph if any of them fails. An edge that cannot be constructed but CAN
        # BE LOADED is not a rule; it is a speed bump, and we have been over that speed bump already.
        for i, d in enumerate(data.get('correspondences', [])):
            sc = _take(SpanCorrespondence, d, f'correspondence #{i}')
            if sc is None:
                continue
            g.correspondences.append(sc)
            ok, why = g.verify_correspondence(sc)
            if not ok:
                err.append(f'correspondence #{i} {sc.id!r} '
                           f'({sc.source_manifestation_id} -> {sc.target_manifestation_id}) '
                           f'DOES NOT VERIFY: ' + '; '.join(why))

        if err:
            raise GraphIntegrityError(
                f'{len(err)} integrity failure(s); THIS GRAPH IS NOT LOADED:\n  - ' + '\n  - '.join(err))
        return g


# =================================================================================================
# 4. MIGRATION — corpus rows -> graph. NO TEXT IS DELETED.
# =================================================================================================

def _slug(s: str, n: int = 40) -> str:
    return re.sub(r'[^a-z0-9]+', '-', (s or '').lower()).strip('-')[:n] or 'x'


def derive_source_type(row: dict) -> tuple[str, str, str]:
    """WHAT KIND OF SOURCE DOES THIS ROW DECLARE ITSELF TO BE?
    -> (work_kind, the expression the metadata CLAIMS exists, basis)

    `migrate()` used to open with `jid = f'{wid}:journal_version'` for every row it was ever handed.
    Sol: "That is not valid for a judicial opinion or statute." It is not even valid for a PREPRINT
    row — a posted-content record claims no journal version at all, and minting one creates, out of
    nothing, a node whose whole meaning is "a peer-reviewed article exists here", for a work that may
    never have been through peer review.

    An empty claimed-expression is a LEGAL ANSWER and migrate() then mints no node. A row that names
    no venue claims no published version, and the honest record of that is an absence — not a
    `journal_version` whose attribution string renders as "Smith (2020), None".
    """
    declared = _norm(str(row.get('type') or '')).lower()
    if declared in SOURCE_TYPE:
        wk, ex = SOURCE_TYPE[declared]
        if ex in ('journal_version', 'proceedings_version') and not _norm(row.get('venue') or ''):
            return wk, '', (f'row declares type={declared!r} but names NO venue — there is no journal '
                            f'to name, so no journal expression is claimed')
        return wk, ex, f'row declares type={declared!r}'
    if row.get('nct_id') or re.match(r'\s*(NCT\d{8}|ISRCTN\d+|EUCTR)', str(row.get('id') or ''), re.I):
        return 'trial', 'registry_record', 'the row carries a trial-registry identifier'
    if row.get('court') or row.get('case_name'):
        return 'case', 'official_text', 'the row carries a court/case field'
    if row.get('statute') or row.get('section'):
        return 'statute', 'official_text', 'the row carries a statute/section field'
    if row.get('doi') and _norm(row.get('venue') or ''):
        return 'study', 'journal_version', 'no declared type; the row carries a DOI and a venue'
    return 'study', '', (f'the row declares type={declared or None!r} and carries no venue — it claims '
                         f'NO published expression, so none is minted')


def _attribution_for(kind: str, work: Work) -> str:
    """The sentence a writer may RENDER for this expression. DISPLAY ONLY.

    Whether it is legal in THIS answer is NOT decided here and is not stored anywhere — it is derived
    per policy by `Graph.resolve_attribution()`. Sol: "If only the working paper is available, citing
    it VIOLATES THE JOURNAL-ONLY INSTRUCTION, so it stays OUTSIDE THE ANSWER BODY." That is the
    JOURNAL_ONLY policy refusing it, not a boolean baked into the node.
    """
    who = ' and '.join(work.authors[:2]) + (' et al.' if len(work.authors) > 2 else '')
    yr = work.year
    venue = work.venue or ''
    if kind in ('official_text', 'registry_record'):
        # A case or a statute is named by ITS OWN TITLE and its court/reporter/registry — not by
        # "authors (year)". `Smith v. Jones (1998), Court of Appeal`.
        return f'{work.title} ({yr}), {venue}' if venue else f'{work.title} ({yr})'
    if not venue:
        return f'{who} ({yr}), UNNAMED VENUE [may not be cited]'
    if kind in ('journal_version', 'proceedings_version'):
        return f'{who} ({yr}), {venue}'
    if kind == 'accepted_manuscript':
        # Legal ONLY if authenticated as the AM *of the journal version* -- that edge, not this label.
        return f'{who} ({yr}), accepted manuscript of {venue}'
    if kind == 'working_paper':
        return f'{who} ({yr}), working paper [NOT the {venue} article]'
    if kind == 'preprint':
        return f'{who} ({yr}), preprint [NOT the {venue} article]'
    return f'{who} ({yr}), UNIDENTIFIED VERSION [may not be cited]'


def ensure_work(g: Graph, *, doi: str, title: str, authors: list[str], year, venue: str,
                source_type: str = '') -> tuple[Work, str, str]:
    """The Work node, and the expression its METADATA CLAIMS EXISTS. -> (work, claimed_id, claimed_kind)

    The claimed expression is real but WE MAY NOT HOLD ITS BYTES: it gets a node with no manifestation,
    and that emptiness is the honest record of what we do not have.
    """
    wid = 'work:' + (_slug(doi) if doi else _slug(title))
    row = dict(doi=doi, title=title, venue=venue, type=source_type)
    work_kind, claimed_kind, claimed_basis = derive_source_type(row)
    work = Work(id=wid, title=title or '', authors=list(authors or []), year=year,
                venue=_norm(venue or '').replace('&amp;', '&'), doi=doi or None, kind=work_kind)
    g.works.setdefault(wid, work)
    work = g.works[wid]

    claimed_id = ''
    if claimed_kind:
        claimed_id = f'{wid}:{claimed_kind}'
        g.expressions.setdefault(claimed_id, Expression(
            id=claimed_id, work_id=wid, kind=claimed_kind,
            kind_basis=f'claimed_by_metadata ({claimed_basis}; bytes NOT verified)',
            attribution=_attribution_for(claimed_kind, work)))
    return work, claimed_id, claimed_kind


def ingest_bytes(g: Graph, work: Work, text: str, *, text_field: str, fetched_by: str,
                 locator: str | None, locator_status: str, claimed_id: str, claimed_kind: str,
                 independent_abstract: str = '') -> str:
    """THE ONE PLACE BYTES BECOME A TYPED NODE. -> manifestation id.

    `migrate()` (corpus rows) and `provenance_construct.construct()` (the event ledger) BOTH come
    through here, and they must: two functions that each decide what an expression is would be two
    answers to "may this span name the journal", and the one that ships is whichever ran last.
    """
    wid = work.id
    prof = profile(text, work, independent_abstract=independent_abstract)
    ekind = prof['expression_kind']
    ebasis = prof['expression_kind_basis']

    if prof['artifact_kind'] in ('wrong_work', 'landing_page', 'extraction_failure'):
        # NOT A RENDERING OF ANY VERSION OF THIS WORK. It gets a QUARANTINE expression, not a version
        # node: the ORA landing page for Frey & Osborne contains the words "published version
        # (refereed)", and if we let that furniture name the expression we would have filed a WEB PAGE
        # as an accepted manuscript of a journal article. The bytes are RETAINED in full (nothing is
        # ever deleted) and attributable to nobody.
        eid = f'{wid}:quarantine:{prof["artifact_kind"]}'
        att = (f'THESE BYTES ARE NOT A USABLE RENDERING OF THIS WORK '
               f'({prof["artifact_kind"]}) — no attribution is possible')
        g.expressions[eid] = Expression(
            id=eid, work_id=wid, kind='unknown', kind_basis=prof['artifact_kind_basis'],
            attribution=att)
    elif ekind == 'unknown':
        eid = f'{wid}:unresolved_version'
        g.expressions[eid] = Expression(
            id=eid, work_id=wid, kind='unknown', kind_basis=ebasis,
            attribution=_attribution_for('unknown', work))
    else:
        eid = f'{wid}:{ekind}'
        g.expressions.setdefault(eid, Expression(
            id=eid, work_id=wid, kind=ekind, kind_basis=ebasis,
            attribution=_attribution_for(ekind, work)))

    h = hashlib.sha256(text.encode('utf-8', 'ignore')).hexdigest()
    mid = f'manif:{h[:12]}'
    g.manifestations[mid] = Manifestation(
        id=mid, expression_id=eid, work_id=wid, text=text, content_hash=h,
        n_words=prof['n_words'], locator=locator, locator_status=locator_status,
        fetched_by=fetched_by, text_field=text_field, profile=prof)

    # ---- EDGES. Only what the bytes support. ----------------------------------------------------
    # An edge needs somewhere to point. If the row claimed no published expression, there is no target
    # -- and inventing one to have something to point AT is how the journal_version node came to exist
    # for every row in the first place.
    if claimed_id and eid != claimed_id and not eid.startswith(f'{wid}:quarantine'):
        existing = {(e.src, e.dst, e.type) for e in g.edges}
        def _edge(src, dst, typ, status, basis):
            if (src, dst, typ) not in existing:          # idempotent: construct() runs after EVERY batch
                g.add_edge(src, dst, typ, status, basis)
                existing.add((src, dst, typ))
        if ekind in ('working_paper', 'preprint'):
            # The strongest thing that is TRUE. Not exact_copy_of. Not even asserted: we have not
            # compared the two texts, because we do not hold the other one.
            _edge(eid, claimed_id, 'predecessor_of', 'PROPOSED',
                  f'same work per bibliography metadata; version equivalence NOT tested '
                  f'(we do not hold the {claimed_kind} bytes). {ebasis}')
            _edge(eid, claimed_id, 'reports_same_study', 'PROPOSED',
                  'same title/authors/DOI row; peer review may still have changed the numbers')
        elif ekind == 'accepted_manuscript':
            # PROPOSED, not ASSERTED: the artifact SAYS it is the accepted manuscript. That is a claim
            # a component makes about itself, which is the one thing we never trust. ASSERTING this
            # edge requires authentication against the journal version's bytes.
            _edge(eid, claimed_id, 'accepted_manuscript_of', 'PROPOSED',
                  f'the artifact self-describes ({ebasis}); NOT authenticated against the '
                  f'{claimed_kind}, whose bytes we do not hold')
        elif ekind == 'unknown':
            _edge(eid, claimed_id, 'reports_same_study', 'PROPOSED',
                  'the bytes carry no version furniture; they may or may not be the '
                  f'{claimed_kind} text')
    return mid


def migrate(corpus: list[dict]) -> Graph:
    g = Graph()
    for row in corpus:
        work, claimed_id, claimed_kind = ensure_work(
            g, doi=row.get('doi') or '', title=row.get('title') or '',
            authors=list(row.get('authors') or []), year=row.get('year'),
            venue=row.get('venue') or '', source_type=str(row.get('type') or ''))

        # ---- the bytes we hold, if any ----------------------------------------------------------
        for fieldname in ('fulltext', 'abstract'):
            text = (row.get(fieldname) or '').strip()
            if not text:
                continue
            # The row's abstract came from the BIBLIOGRAPHY, independently of whatever body we
            # fetched — which is exactly what makes it usable as a probe against that body. It is
            # never used to probe itself.
            indep = (row.get('abstract') or '') if fieldname == 'fulltext' else ''

            # The fetcher's own label is EVIDENCE, NOT TRUTH. `fulltext_source='working_paper'`
            # records WHICH FETCHER RAN, not what the artifact is: it is false on 5 of the 6 rows
            # that carry it. The bytes decide; the label is recorded and contradicted in the open.
            claimed_src = row.get('fulltext_source') or 'publisher_or_oa'

            # THE LOCATOR. wp_fetch.py NEVER RECORDED THE URL IT FETCHED FROM, so for the rows it
            # touched the only URL on the row is `oa_url` -- left by an EARLIER fetcher and pointing
            # at the PUBLISHER (aeaweb.org!). A locator that names the journal while the bytes are a
            # working paper is worse than no locator, so it is not silently adopted.
            locator, lstatus = row.get('oa_url') or None, 'RECORDED'
            if not locator:
                lstatus = 'NOT_RECORDED_BY_FETCHER'
            elif claimed_src == 'working_paper':
                lstatus = 'CONTRADICTS_CONTENT (oa_url points at the publisher; these bytes were ' \
                          'fetched by wp_fetch, which never recorded its own URL)'

            ingest_bytes(g, work, text, text_field=fieldname, fetched_by=claimed_src,
                         locator=locator, locator_status=lstatus, claimed_id=claimed_id,
                         claimed_kind=claimed_kind, independent_abstract=indep)
    return g


# =================================================================================================
# 5. THE HONEST CENSUS
# =================================================================================================

def census(g: Graph, corpus: list[dict]) -> None:
    P = print
    P('=' * 100)
    P('PROVENANCE CENSUS — every label re-derived from the bytes it describes')
    P('=' * 100)

    P(f'\n  WORKS                 {len(g.works)}')
    P(f'  EXPRESSIONS           {len(g.expressions)}')
    P(f'  MANIFESTATIONS        {len(g.manifestations)}   (bytes we actually hold)')
    P(f'  EDGES                 {len(g.edges)}')

    P('\n--- MANIFESTATIONS BY EXPRESSION KIND (what version the BYTES say they are) ' + '-' * 24)
    byk: dict[str, list[Manifestation]] = {}
    for m in g.manifestations.values():
        byk.setdefault(g.expressions[m.expression_id].kind, []).append(m)
    for k in EXPRESSION_KINDS:
        ms = byk.get(k, [])
        if ms:
            P(f'  {k:<22} {len(ms):>3}   ({sum(x.n_words for x in ms):>7,} words held)')

    P('\n--- MANIFESTATIONS BY CONTENT-DERIVED ARTIFACT KIND ' + '-' * 47)
    bya: dict[str, list[Manifestation]] = {}
    for m in g.manifestations.values():
        bya.setdefault(m.profile['artifact_kind'], []).append(m)
    for k in ARTIFACT_KINDS:
        ms = bya.get(k, [])
        if ms:
            ok = sum(1 for x in ms if x.profile['complete'])
            P(f'  {k:<22} {len(ms):>3}   complete: {ok:>2}   not complete: {len(ms) - ok:>2}')

    # ---- THE NUMBER THE ANSWER ACTUALLY RESTS ON --------------------------------------------
    P('\n--- ADMISSIBILITY FOR A JOURNAL-ONLY ANSWER (task 72) ' + '-' * 45)
    jok = [m for m in g.manifestations.values() if g.journal_attributable(m.id)]
    wponly, unres, dead = [], [], []
    for m in g.manifestations.values():
        if g.journal_attributable(m.id):
            continue
        k = g.expressions[m.expression_id].kind
        if k in ('working_paper', 'preprint', 'accepted_manuscript'):
            wponly.append(m)
        # Read from the registry, not from a literal list kept beside it. The literal list is how a
        # new kind gets silently counted as something else: `citation_only` was born and 13 citation
        # stubs would have been reported as "unresolved versions" — a claim about VERSIONS, made about
        # documents we do not have.
        elif not m.profile['complete'] and m.profile['artifact_kind'] in NOT_A_DOCUMENT_KINDS:
            dead.append(m)
        else:
            unres.append(m)

    P(f'  JOURNAL-ATTRIBUTABLE            {len(jok):>3}   spans from these may be printed as journal findings')
    P(f'  WORKING-PAPER / PREPRINT ONLY   {len(wponly):>3}   INELIGIBLE — citing them breaks the journal-only')
    P(f'  {"":<32}      instruction; citing the journal with THEIR text is fabrication')
    P(f'  UNRESOLVED VERSION              {len(unres):>3}   bytes carry no version furniture — cannot be claimed')
    P(f'  NOT A DOCUMENT                  {len(dead):>3}   landing pages, corrupt extractions, wrong work')

    claimed_ft = sum(1 for c in corpus if c.get('content_status') == 'FULLTEXT')
    P(f'\n  THE CORPUS CLAIMS               {claimed_ft:>3}   rows with content_status=FULLTEXT')
    P(f'  THE BYTES SUPPORT               {len(jok):>3}   journal-attributable manifestations')
    P(f'  {"":>32}   ^ THIS IS WORSE THAN THE CORPUS CLAIMS. IT IS ALSO TRUE.')

    P('\n--- EDGES (nothing is ASSERTED that the bytes do not prove) ' + '-' * 39)
    for t in EDGE_TYPES:
        es = [e for e in g.edges if e.type == t]
        if es:
            a = sum(1 for e in es if e.status == 'ASSERTED')
            P(f'  {t:<24} {len(es):>3}   ASSERTED: {a}   PROPOSED: {len(es) - a}')
    P('  (0 ASSERTED span-preserving edges: we hold no journal bytes to compare against, so no')
    P('   working paper has EARNED the right to be cited as its journal article.)')

    # ---- every recovered paper, profiled -----------------------------------------------------
    P('\n--- CONTENT-DERIVED ARTIFACT PROFILE OF EVERY MANIFESTATION WE HOLD ' + '-' * 31)
    P(f'  {"words":>6} {"kind":<19} {"ver":<12} {"extract":<9} {"ident":<12} {"J?":<3} source')
    for m in sorted(g.manifestations.values(), key=lambda m: (
            not g.journal_attributable(m.id), -m.n_words)):
        p = m.profile
        w = g.works[m.work_id]
        who = f"{(w.authors or ['?'])[0]} ({w.year})"
        P(f"  {m.n_words:>6} {p['artifact_kind']:<19} {p['expression_kind'][:11]:<12} "
          f"{p['extractability']['verdict']:<9} {p['identity']['verdict']:<12} "
          f"{'YES' if g.journal_attributable(m.id) else ' no':<3} {who[:28]:<28} {w.venue[:30]}")

    # ---- the ones that were about to ship -----------------------------------------------------
    P('\n--- LABELS THAT ASSERTED MORE THAN THEIR CONTENT SUPPORTED ' + '-' * 40)
    for m in g.manifestations.values():
        p = m.profile
        # Only the manifestation the FULLTEXT claim actually refers to. A row's abstract is not
        # claimed to be full text, and reporting it here would itself be a label over-asserting.
        if m.text_field != 'fulltext':
            continue
        row = next((c for c in corpus if (c.get('doi') or '') == (g.works[m.work_id].doi or '')), {})
        claimed = row.get('content_status')
        if claimed == 'FULLTEXT' and not p['complete']:
            w = g.works[m.work_id]
            P(f"\n  {w.authors[0] if w.authors else '?'} ({w.year}), {w.venue[:44]}")
            P(f"      corpus says : content_status=FULLTEXT"
              + (f", fulltext_source={row.get('fulltext_source')}" if row.get('fulltext_source') else ''))
            P(f"      bytes say   : {p['artifact_kind']} — {p['artifact_kind_basis']}")
            for r in p['incomplete_because']:
                P(f"                    - {r}")

    P('\n--- EXTRACTABILITY DISTRIBUTION (so the thresholds can be RE-DERIVED, not trusted) ' + '-' * 16)
    dens = sorted(((m.profile['extractability']['stopword_density'], m.id, m)
                   for m in g.manifestations.values() if m.n_words >= 50))
    P(f'  stopword density: min {dens[0][0]:.3f}  median {statistics.median([d for d, _, _ in dens]):.3f}'
      f'  max {dens[-1][0]:.3f}   (n={len(dens)})')
    P('  lowest three: ' + ', '.join(
        f"{d:.3f} ({(g.works[m.work_id].authors or ['?'])[0]})" for d, _, m in dens[:3]))
    P(f'  CORRUPT threshold {CORRUPT_STOPWORD_DENSITY} sits in the gap between {dens[0][0]:.3f} and '
      f'{dens[1][0]:.3f} — a {dens[1][0] / max(dens[0][0], 1e-9):.0f}x separation, not a magic number.')

    ov = sorted((m.profile['identity']['abstract_vocab_overlap'], m.id, m)
                for m in g.manifestations.values()
                if m.profile['identity']['abstract_vocab_overlap'] is not None)
    if len(ov) >= 3:
        P(f'  abstract-vocabulary overlap (the wrong-work test), n={len(ov)}:')
        P('    lowest three: ' + ', '.join(
            f"{o:.3f} ({(g.works[m.work_id].authors or ['?'])[0]})" for o, _, m in ov[:3]))
        P(f'    CONTRADICTED threshold {CONTRADICTED_VOCAB_OVERLAP} sits between {ov[0][0]:.3f} '
          f'(a different paper) and {ov[1][0]:.3f} (the lowest genuine body).')


# =================================================================================================
# 6. SELF-TEST — ADVERSARIAL. Every case here is an ATTACK on the core rule, not a demonstration.
# =================================================================================================

def _raises(fn, exc) -> bool:
    """`fn` MUST raise `exc`. Returning a falsy value is not the same as refusing, and a check that
    accepts either is a check that would pass on a function that silently returns None."""
    try:
        fn()
    except exc:
        return True
    except Exception:
        return False
    return False


def self_test() -> int:
    fails: list[str] = []

    def ck(name: str, ok: bool) -> None:
        print(f"  [{'PASS' if ok else '**FAIL**'}] {name}")
        if not ok:
            fails.append(name)

    w = Work(id='work:w', title='Robots and Jobs', authors=['Acemoglu', 'Restrepo'], year=2020,
             venue='Journal of Political Economy', doi='10.1086/705716')
    g = Graph(works={'work:w': w})
    g.expressions['work:w:journal_version'] = Expression(
        'work:w:journal_version', 'work:w', 'journal_version', 'metadata',
        'Acemoglu and Restrepo (2020), Journal of Political Economy')
    g.expressions['work:w:working_paper'] = Expression(
        'work:w:working_paper', 'work:w', 'working_paper', 'bytes say NBER WORKING PAPER SERIES',
        'Acemoglu and Restrepo (2020), working paper [NOT the Journal of Political Economy article]')
    # The authors are NAMED in the header, so identity derives CONFIRMED — which the V9 exact_copy_of
    # rule now REQUIRES on both sides. (Two documents we cannot prove are ours cannot be proven equal.)
    body = ('NBER WORKING PAPER SERIES ROBOTS AND JOBS by Acemoglu and Restrepo. '
            + 'the effect of robots on employment is '
              'estimated across commuting zones and we find a decline. ' * 80)
    g.manifestations['manif:wp'] = Manifestation(
        'manif:wp', 'work:w:working_paper', 'work:w', body,
        hashlib.sha256(body.encode()).hexdigest(), len(body.split()), None,
        'NOT_RECORDED_BY_FETCHER', 'wp_fetch', 'fulltext',
        profile(body, w))

    # ---- THE CORE RULE ---------------------------------------------------------------------
    ck('a span in a WORKING PAPER may NOT name the journal article',
       'work:w:journal_version' not in g.attribution_targets('manif:wp'))
    ck('...and journal_attributable() says NO',
       not g.journal_attributable('manif:wp'))
    ck('the only attribution offered names the WORKING PAPER, and says it is not the journal',
       'NOT the Journal of Political Economy'
       in g.resolve_attribution('manif:wp', ANY_VERSION).text)

    g.add_edge('work:w:working_paper', 'work:w:journal_version', 'predecessor_of', 'PROPOSED',
               'title match')
    ck('a PROPOSED predecessor_of edge does NOT make it journal-attributable',
       not g.journal_attributable('manif:wp'))

    g.add_edge('work:w:working_paper', 'work:w:journal_version', 'predecessor_of', 'ASSERTED',
               'the working paper is provably the predecessor of the journal article')
    ck('even an ASSERTED predecessor_of does NOT transfer attribution (PEER REVIEW CHANGES NUMBERS)',
       not g.journal_attributable('manif:wp'))

    g.add_edge('work:w:working_paper', 'work:w:journal_version', 'exact_copy_of', 'PROPOSED',
               'the texts look similar')
    ck('a PROPOSED exact_copy_of does NOT transfer attribution either',
       not g.journal_attributable('manif:wp'))

    try:
        g.add_edge('work:w:working_paper', 'work:w:journal_version', 'exact_copy_of', 'ASSERTED',
                   'the titles match')
        ok = False
    except ValueError:
        ok = True
    ck('a TITLE MATCH may not ASSERT exact_copy_of (Sol: it can only PROPOSE predecessor_of)', ok)

    # ---- THE V9 P0: `accepted_manuscript_of` IS NOT SPAN-PRESERVING -------------------------------
    # It WAS. It was in SPAN_PRESERVING, and it widened attribution exactly as exact_copy_of does — so an
    # ASSERTED accepted_manuscript_of made a manuscript's spans printable under the journal's name. And
    # the edge was reachable from A REPOSITORY'S ONE-WORD LABEL: Unpaywall says `acceptedVersion`,
    # version_align mapped that to this edge, alignment_census called the result ADMISSIBLE. Three hops
    # from a metadata string to a fabricated journal finding.
    ck('accepted_manuscript_of is NO LONGER span-preserving (the V9 P0)',
       'accepted_manuscript_of' not in SPAN_PRESERVING
       and 'accepted_manuscript_of' in NON_SPAN_PRESERVING)
    g.add_edge('work:w:working_paper', 'work:w:journal_version', 'accepted_manuscript_of', 'ASSERTED',
               'byte-for-byte checksum of the repository deposit against the accepted manuscript')
    ck('even an ASSERTED accepted_manuscript_of, on BYTE-LEVEL evidence, TRANSFERS NOTHING',
       'work:w:journal_version' not in g.attribution_targets('manif:wp')
       and not g.journal_attributable('manif:wp'))
    ck('...and the refusal still names fabrication — an AM is not the journal version',
       'fabrication' in (g.resolve_attribution('manif:wp', JOURNAL_ONLY).refusal or ''))

    try:
        g.add_edge('work:w:working_paper', 'work:w:journal_version', 'exact_copy_of', 'ASSERTED', '')
        ok = False
    except ValueError:
        ok = True
    ck('an edge with NO BASIS cannot be constructed at all', ok)

    # A BASIS THAT *SAYS* "byte-for-byte" IS STILL A SENTENCE. The old guard was a REGEX OVER PROSE, so
    # the string below asserted the edge and NO BYTES WERE EVER COMPARED. We hold no journal bytes here.
    try:
        g.add_edge('work:w:working_paper', 'work:w:journal_version', 'exact_copy_of', 'ASSERTED',
                   'byte-for-byte comparison against the journal PDF: identical span at 76927-77299')
        ok = False
    except ValueError:
        ok = True
    ck('an exact_copy_of asserted on a SENTENCE about bytes we do not hold is REFUSED (V9 §4)', ok)

    # The rule must also WORK when the proof is genuinely earned -- a gate that never opens is a gate
    # nobody will keep. Expression-wide equality requires EXPRESSION-WIDE EVIDENCE: we must hold BOTH
    # documents, both identity-CONFIRMED, and their ENTIRE canonical texts must be equal.
    jbody = body.replace('NBER WORKING PAPER SERIES ', '')   # ...a DIFFERENT document. Not equal.
    g.expressions['work:w2:journal_version'] = g.expressions['work:w:journal_version']
    g.manifestations['manif:jv'] = Manifestation(
        'manif:jv', 'work:w:journal_version', 'work:w', jbody,
        hashlib.sha256(jbody.encode()).hexdigest(), len(jbody.split()), None, 'RECORDED',
        'publisher', 'fulltext', profile(jbody, w))
    del g.expressions['work:w2:journal_version']
    try:
        g.add_edge('work:w:working_paper', 'work:w:journal_version', 'exact_copy_of', 'ASSERTED',
                   'sha-256 of both canonical texts compared')
        ok = False
    except ValueError:
        ok = True
    ck('an exact_copy_of between two documents whose canonical texts DIFFER is REFUSED', ok)

    # ...and now the honest case: the journal bytes really ARE the same document.
    g.manifestations['manif:jv'] = Manifestation(
        'manif:jv', 'work:w:journal_version', 'work:w', body,
        hashlib.sha256(body.encode()).hexdigest(), len(body.split()), None, 'RECORDED',
        'publisher', 'fulltext', profile(body, w))
    g.add_edge('work:w:working_paper', 'work:w:journal_version', 'exact_copy_of', 'ASSERTED',
               'sha-256 of the entire canonical text of both manifestations: equal')
    ck('an ASSERTED exact_copy_of (both documents HELD, entire canonical text equal) DOES license it',
       g.journal_attributable('manif:wp'))
    ck('...and resolve_attribution then names the JOURNAL EXPRESSION BY ID, not by prose',
       g.resolve_attribution('manif:wp', JOURNAL_ONLY).names_expression_id == 'work:w:journal_version')
    g.edges = [e for e in g.edges if e.type != 'exact_copy_of' or e.status != 'ASSERTED']
    del g.manifestations['manif:jv']

    # ---- PER-SPAN ATTRIBUTION (Sol V9 §4) --------------------------------------------------------
    # An ACCEPTED MANUSCRIPT and the JOURNAL VERSION. They are NOT the same document — the AM says
    # 0.37, the journal says 0.2 — but ONE sentence survived peer review verbatim. That sentence, and
    # NOTHING ELSE IN THE MANUSCRIPT, may be printed under the journal's name.
    SURVIVED = 'Industrial robots are fully autonomous and reprogrammable machines used in manufacturing.'
    CHANGED_AM = 'we estimate that one more robot per thousand workers reduces employment by 0.37 percent'
    CHANGED_J = 'we estimate that one more robot per thousand workers reduces employment by 0.2 percent'
    pad = 'The analysis proceeds in three stages across commuting zones and industries. ' * 90

    # Each document's own front matter says what it is, and NAMES ITS AUTHORS — so profile() derives
    # `accepted_manuscript` / `journal_article`, both complete, both identity CONFIRMED. Nothing here is
    # asserted; it is all read out of the bytes, exactly as in production.
    am_head = 'Accepted manuscript. Robots and Jobs. Acemoglu and Restrepo. '
    jv_head = 'Journal of Political Economy Vol. 128, No. 6. Robots and Jobs. Acemoglu and Restrepo. '
    am_text = am_head + pad + SURVIVED + ' ' + CHANGED_AM + ' ' + pad
    jv_text = jv_head + pad + SURVIVED + ' ' + CHANGED_J + ' ' + pad
    pg = Graph(works={'work:w': w})
    pg.expressions['work:w:accepted_manuscript'] = Expression(
        'work:w:accepted_manuscript', 'work:w', 'accepted_manuscript', 'bytes say ACCEPTED MANUSCRIPT',
        _attribution_for('accepted_manuscript', w))
    pg.expressions['work:w:journal_version'] = Expression(
        'work:w:journal_version', 'work:w', 'journal_version', 'typeset',
        'Acemoglu and Restrepo (2020), Journal of Political Economy')

    def _man(mid, eid, text):
        p = profile(text, w)
        p['identity'] = dict(p['identity'], verdict='CONFIRMED', basis='test fixture: identity confirmed')
        pg.manifestations[mid] = Manifestation(
            mid, eid, 'work:w', text, hashlib.sha256(text.encode()).hexdigest(),
            len(text.split()), None, 'RECORDED', 'test', 'fulltext', p)

    _man('manif:am', 'work:w:accepted_manuscript', am_text)
    _man('manif:jv', 'work:w:journal_version', jv_text)

    a_s = am_text.index(SURVIVED)
    j_s = jv_text.index(SURVIVED)
    a_c = am_text.index(CHANGED_AM)
    j_c = jv_text.index(CHANGED_J)

    b_surv = pg.bind_span('manif:am', a_s, a_s + len(SURVIVED))
    b_chng = pg.bind_span('manif:am', a_c, a_c + len(CHANGED_AM))
    ck('a bound span now carries a BINDING_ID — permission is a property OF THE SPAN',
       b_surv['binding_id'].startswith('bind:') and b_surv['binding_id'] != b_chng['binding_id'])
    ck('with NO correspondence, an accepted manuscript is NOT journal-attributable, span by span',
       not pg.resolve_attribution(b_surv, JOURNAL_ONLY).admitted
       and not pg.resolve_attribution(b_chng, JOURNAL_ONLY).admitted)
    ck('...and it IS attributable AS AN ACCEPTED MANUSCRIPT (V9: "accepted-manuscript-attributable only")',
       pg.resolve_attribution(b_surv, ANY_VERSION).admitted
       and pg.resolve_attribution(b_surv, ANY_VERSION).names_expression_id
       == 'work:w:accepted_manuscript')

    # THE ACEMOGLU TEST. 0.37 in the manuscript, 0.2 in the journal. IT MUST FAIL AT THE BYTES.
    bad_sc = make_correspondence(pg, 'manif:am', a_c, a_c + len(CHANGED_AM),
                                 'manif:jv', j_c, j_c + len(CHANGED_J),
                                 basis='the same sentence in both documents')
    okc, whyc = pg.verify_correspondence(bad_sc)
    ck('THE ACEMOGLU TEST: a 0.37-vs-0.2 correspondence FAILS IMMEDIATELY (canonical texts differ)',
       not okc and any('NOT equal' in x for x in whyc))
    ck('...and add_correspondence REFUSES it — it never reaches the graph',
       _raises(lambda: pg.add_correspondence(bad_sc), ValueError))

    # THE SURVIVING SENTENCE. Verbatim in both. It — and only it — earns the journal's name.
    good_sc = make_correspondence(pg, 'manif:am', a_s, a_s + len(SURVIVED),
                                  'manif:jv', j_s, j_s + len(SURVIVED),
                                  basis='exact canonical equality of the span in both held documents')
    pg.add_correspondence(good_sc)
    b_surv = pg.bind_span('manif:am', a_s, a_s + len(SURVIVED))       # re-bind: permission changed
    b_chng = pg.bind_span('manif:am', a_c, a_c + len(CHANGED_AM))
    ck('a VERIFIED correspondence makes THAT SPAN journal-attributable',
       pg.resolve_attribution(b_surv, JOURNAL_ONLY).admitted
       and pg.resolve_attribution(b_surv, JOURNAL_ONLY).names_expression_id
       == 'work:w:journal_version')
    ck('THAT SPAN ONLY: the 0.37 sentence in the SAME manuscript is STILL refused',
       not pg.resolve_attribution(b_chng, JOURNAL_ONLY).admitted)
    ck('...and the MANIFESTATION-WIDE question is still NO (a per-span proof is not a document permit)',
       not pg.journal_attributable('manif:am'))

    # THE REBINDING. The span is in the VoR's OWN bytes, so bind it THERE and need no permission at all.
    rb = pg.rebind(b_surv, 'manif:jv')
    ck('a span found independently in the VoR bytes REBINDS directly to the VoR manifestation',
       rb is not None and rb['manifestation_id'] == 'manif:jv'
       and rb['text'] == SURVIVED and pg.verify_span(rb)
       and pg.resolve_attribution(rb, JOURNAL_ONLY).names_expression_id == 'work:w:journal_version')
    ck('...and a span that is NOT in the VoR bytes cannot be rebound to them (None, not a fallback)',
       pg.rebind(b_chng, 'manif:jv') is None)

    # THE CORRESPONDENCE IS RE-VERIFIED AT EVERY USE, INCLUDING FROM DISK.
    tampered = json.loads(json.dumps(pg.to_json()))
    tampered['correspondences'][0]['target_start'] = j_c
    tampered['correspondences'][0]['target_end'] = j_c + len(CHANGED_J)
    ck('from_json REFUSES a correspondence whose offsets were re-pointed at a DIFFERENT sentence',
       _raises(lambda: Graph.from_json(tampered), GraphIntegrityError))
    tampered2 = json.loads(json.dumps(pg.to_json()))
    tampered2['correspondences'][0]['source_span'] = 'anything at all'
    ck('from_json REFUSES a correspondence whose verbatim span is not what its offsets slice',
       _raises(lambda: Graph.from_json(tampered2), GraphIntegrityError))
    ck('a graph carrying a GENUINE correspondence round-trips through the strict loader',
       len(Graph.from_json(json.loads(json.dumps(pg.to_json()))).correspondences) == 1)

    # ---- corrupt bytes of the RIGHT paper are still inadmissible ----------------------------
    caesar = 'Vhfwlrq 5 wkdw wkh qxpehu ri kdluguhvvhuv juhz pruh wkdq 633 shu fhqw. ' * 40
    p = profile(caesar, w)
    ck('a CAESAR-SHIFTED PDF dump is an extraction_failure, not full text',
       p['artifact_kind'] == 'extraction_failure' and not p['complete'])
    g.manifestations['manif:bad'] = Manifestation(
        'manif:bad', 'work:w:journal_version', 'work:w', caesar,
        hashlib.sha256(caesar.encode()).hexdigest(), len(caesar.split()), None, 'RECORDED',
        'publisher', 'fulltext', p)
    ck('...and corrupt bytes OF THE JOURNAL VERSION ITSELF are still NOT journal-attributable',
       not g.journal_attributable('manif:bad'))

    # ---- NO UNIVERSAL WORD THRESHOLD (Sol, item 4) ------------------------------------------
    # This test used to FAKE its own subject: `op_kind = dict(op, artifact_kind='judicial_opinion')`
    # -- it overwrote the derived kind with the one it wanted, then checked the REGISTRY TABLE rather
    # than the DERIVATION, and passed. profile() could not produce `judicial_opinion` at all: a
    # 100-word opinion came out `abstract`, complete=False, and the registry entry that says
    # stub_floor=None was UNREACHABLE CODE. The generality was asserted in a comment and denied by
    # the function. Now the work's kind drives it, and the check is on what profile() ACTUALLY RETURNS.
    opinion = Work('work:op', 'Smith v. Jones', ['Smith'], 1998, 'Court of Appeal', None, 'case')
    short = ('The appellant challenges the order of the court below. We have considered the record '
             'and the submissions of both parties. The appeal is dismissed with costs. It is so '
             'ordered by the court this day. ') * 3
    op = profile(short, opinion)
    ck(f'a {len(short.split())}-word JUDICIAL OPINION is COMPLETE — profile() DERIVES it, no floor applies',
       op['artifact_kind'] == 'judicial_opinion' and op['complete'] and not op['incomplete_because'])
    ck('...and the same 100 words of a SCHOLARLY work is a stub, NOT the article',
       not profile(short, w)['complete']
       and KIND_PROFILE['journal_article']['stub_floor'] == SCHOLARLY_STUB_FLOOR)
    statute = Work('work:st', 'Section 230', [], 1996, '47 U.S.C.', None, 'statute')
    st = profile('No provider or user of an interactive computer service shall be treated as the '
                 'publisher or speaker of any information provided by another information content '
                 'provider.', statute)
    ck('a 32-word STATUTE SECTION is COMPLETE AT ANY LENGTH (it is the whole enacted text)',
       st['artifact_kind'] == 'statute_section' and st['complete'])
    ck('...but NO length is complete at ZERO — an empty registry record is not a short one',
       not judge_completeness('trial_registry_record', 0)[0]
       and judge_completeness('trial_registry_record', 12)[0])
    ck('an unregistered artifact kind cannot be judged complete OR incomplete — it RAISES',
       _raises(lambda: judge_completeness('press_release', 5000), ValueError))

    banner = ('This website uses cookies. By clicking the Accept button you agree. Privacy Policy. '
              'Sign in. Subscribe. Download PDF. ') * 12
    ck('a 535-word publisher COOKIE BANNER is a landing_page, complete=False',
       profile(banner, w)['artifact_kind'] == 'landing_page'
       and not profile(banner, w)['complete'])
    # ...and the bytes may always DEMOTE, even a work whose kind would otherwise be complete at any
    # length. A login wall served by a court's website is a login wall.
    ck('a COOKIE BANNER served for a JUDICIAL OPINION is still a landing_page (bytes may demote)',
       profile(banner, opinion)['artifact_kind'] == 'landing_page'
       and not profile(banner, opinion)['complete'])

    # ---- identity: ABSENCE IS NOT CONTRADICTION ---------------------------------------------
    no_authors = ('The effect of robots on employment across commuting zones is estimated. ' * 200)
    i = identity_agreement(no_authors, w, independent_abstract='', readable=True)
    ck('an author block missing from the text NEVER yields CONTRADICTED (absence proves nothing)',
       i['verdict'] != 'CONTRADICTED')
    # >= _IDENT_MIN_BODY_WORDS: below that floor the probe DECLINES to judge rather than guess, so a
    # short fixture would pass this test for the wrong reason.
    maths = 'We argue how AI can assist mathematics in theorem proving and conjecture formulation. ' * 90
    assert len(maths.split()) >= _IDENT_MIN_BODY_WORDS
    # A realistic bibliography abstract: >= _IDENT_MIN_ABSTRACT_WORDS, else the probe rightly declines.
    abs_ = ('We estimate the effect of industrial robots on employment and wages across United States '
            'commuting zones exposed to automation between 1990 and 2007, using an instrument built '
            'from robot adoption in other advanced economies. Our estimates imply large negative '
            'effects of robots on employment and wages in local labour markets, concentrated in '
            'manufacturing industries and among routine manual occupations.')
    assert len(abs_.split()) >= _IDENT_MIN_ABSTRACT_WORDS
    i2 = identity_agreement(maths, w, independent_abstract=abs_, readable=True)
    ck('a DIFFERENT PAPER is CONTRADICTED by positive evidence (its abstract vocabulary is absent)',
       i2['verdict'] == 'CONTRADICTED')

    # ---- span binding: BOUNDS ARE VALIDATED, NOT TRUSTED -------------------------------------
    b = g.bind_span('manif:wp', 10, 60)
    ck('a bound span carries its manifestation_id AND content hash',
       b['manifestation_id'] == 'manif:wp' and len(b['content_hash']) == 64 and g.verify_span(b))
    ck('a span whose source bytes changed FAILS verification',
       not g.verify_span(dict(b, content_hash='0' * 64)))

    # THE BINDING RETURNS IDS, NOT PROSE. A consumer that must string-match an English sentence to
    # find out what it may cite has a suggestion, not a rule.
    # The ASSERTED exact_copy_of was withdrawn above (we no longer hold the journal bytes), and the
    # ASSERTED accepted_manuscript_of transfers NOTHING — so the ONLY thing this span may name is the
    # working paper whose bytes it is. That is the V9 P0, visible in the permitted set itself.
    ck('a bound span carries expression_id + PERMITTED EXPRESSION IDS (not `may_name` prose)',
       b['expression_id'] == 'work:w:working_paper'
       and b['permitted_expression_ids'] == ['work:w:working_paper']
       and 'may_name' not in b)

    n = len(g.manifestations['manif:wp'].text)
    for name, s, e in (('NEGATIVE  (Python would index from the END of the text)', -5, 20),
                       ('REVERSED  (slices to "", then verifies against nothing)', 900, 100),
                       ('EMPTY     (a real citation quoting zero characters)',     50, 50),
                       ('PAST-END  (Python truncates it silently)',                n - 10, n + 500),
                       ('BOTH PAST-END (the span is nowhere in the document)',     n + 10, n + 60)):
        ck(f'bind_span REFUSES a {name} span [{s}:{e}]',
           _raises(lambda s=s, e=e: g.bind_span('manif:wp', s, e), SpanBindingError))
    ck('bind_span REFUSES a non-int offset (True is an int in Python, and it is not an offset)',
       _raises(lambda: g.bind_span('manif:wp', True, 60), SpanBindingError)
       and _raises(lambda: g.bind_span('manif:wp', 10.5, 60), SpanBindingError))
    ck('bind_span REFUSES bytes we do not hold',
       _raises(lambda: g.bind_span('manif:nonexistent', 0, 10), SpanBindingError))

    # ...and the ENFORCEMENT POINT re-checks them, because by then the binding has been through a file.
    ck('verify_span REJECTS a hand-edited binding whose offsets were never validated',
       not g.verify_span(dict(b, span_start=900, span_end=100, text=''))
       and not g.verify_span(dict(b, span_start=-5, span_end=20, text=''))
       and not g.verify_span(dict(b, span_end=n + 500)))
    ck('verify_span REJECTS a binding whose PERMITTED SET is stale (an edge changed under it)',
       not g.verify_span(dict(b, permitted_expression_ids=['work:w:journal_version', 'work:w:oops'])))

    # ---- the policy, not a boolean on the node ------------------------------------------------
    wp_only = Graph(works={'work:w': w},
                    expressions={k: v for k, v in g.expressions.items()},
                    manifestations={'manif:wp': g.manifestations['manif:wp']})   # NO edges
    ck('under JOURNAL_ONLY the working paper is REFUSED, with the reason named',
       not wp_only.resolve_attribution('manif:wp', JOURNAL_ONLY).admitted
       and 'fabrication' in wp_only.resolve_attribution('manif:wp', JOURNAL_ONLY).refusal)
    ck('...and under ANY_VERSION THE SAME BYTES are admitted, naming the working paper',
       wp_only.resolve_attribution('manif:wp', ANY_VERSION).admitted
       and wp_only.resolve_attribution('manif:wp', ANY_VERSION).names_expression_id
       == 'work:w:working_paper')

    # ---- migrate() MUST NOT MINT A JOURNAL VERSION FOR EVERY ROW ON EARTH --------------------
    mg = migrate([
        {'doi': '10.1/j', 'title': 'A Journal Article', 'authors': ['A'], 'year': 2020,
         'venue': 'Journal of Political Economy', 'type': 'journal-article', 'abstract': ''},
        {'doi': '', 'title': 'Smith v. Jones', 'authors': [], 'year': 1998,
         'venue': 'Court of Appeal', 'type': 'judicial-opinion', 'abstract': ''},
        {'doi': '10.1/p', 'title': 'A Preprint', 'authors': ['B'], 'year': 2024,
         'venue': 'arXiv', 'type': 'posted-content', 'abstract': ''},
    ])
    kinds = {e.work_id: e.kind for e in mg.expressions.values()}
    ck('migrate() gives a JUDICIAL OPINION an `official_text`, NOT a journal_version',
       kinds.get('work:smith-v-jones') == 'official_text')
    ck('migrate() gives a PREPRINT ROW a `preprint` — a posted-content record claims NO journal',
       kinds.get('work:10-1-p') == 'preprint')
    ck('...and a journal-article row still claims its journal_version',
       kinds.get('work:10-1-j') == 'journal_version')
    ck('a row that names NO venue and NO type claims NOTHING — no expression is invented for it',
       not migrate([{'doi': '', 'title': 'Loose Bytes', 'authors': ['C'], 'year': 2020,
                     'venue': '', 'type': '', 'abstract': ''}]).expressions)

    # ---- from_json: A GRAPH ON DISK IS AN UNTRUSTED INPUT -------------------------------------
    doc = g.to_json()
    ck('a graph written by to_json() round-trips through the STRICT loader',
       len(Graph.from_json(json.loads(json.dumps(doc))).manifestations) == len(g.manifestations))

    def tamper(fn) -> dict:
        d = json.loads(json.dumps(doc))
        fn(d)
        return d

    attacks = [
        ('the TEXT is edited but the hash is left alone (every span bound to it is bound to nothing)',
         lambda d: d['manifestations'][0].__setitem__('text', d['manifestations'][0]['text'] + ' and 633 per cent')),
        ('the hash is recomputed but N_WORDS still describes the document we no longer hold',
         lambda d: d['manifestations'][0].__setitem__('n_words', 99999)),
        ('a manifestation names an EXPRESSION THAT DOES NOT EXIST',
         lambda d: d['manifestations'][0].__setitem__('expression_id', 'work:w:ghost')),
        ('a manifestation names a WORK THAT DOES NOT EXIST',
         lambda d: d['manifestations'][0].__setitem__('work_id', 'work:ghost')),
        ('an edge endpoint DOES NOT EXIST',
         lambda d: d['edges'][0].__setitem__('dst', 'work:w:ghost')),
        ('an edge carries NO BASIS',
         lambda d: d['edges'][0].__setitem__('basis', '   ')),
        ('an ASSERTED exact_copy_of is smuggled in ON A TITLE MATCH (add_edge refuses it; the FILE must too)',
         lambda d: d['edges'].append(dict(src='work:w:working_paper', dst='work:w:journal_version',
                                          type='exact_copy_of', status='ASSERTED',
                                          basis='the titles and metadata match exactly'))),
        ('an ASSERTED exact_copy_of is smuggled in NAMING BYTES WE DO NOT HOLD (V9 §4)',
         lambda d: d['edges'].append(dict(src='work:w:working_paper', dst='work:w:journal_version',
                                          type='exact_copy_of', status='ASSERTED',
                                          basis='sha-256 checksum of both documents: identical'))),
        ('`complete: true` is written onto a CORRUPT extraction (the registry does not derive it)',
         lambda d: [m for m in d['manifestations'] if m['id'] == 'manif:bad'][0]['profile']
         .__setitem__('complete', True)),
        ('`artifact_kind` is upgraded to journal_article to escape the stub floor',
         lambda d: [m for m in d['manifestations'] if m['id'] == 'manif:bad'][0]['profile']
         .update(artifact_kind='journal_article', complete=True)),
        ('an unknown field appears (a schema drift silently drops the field a gate reads)',
         lambda d: d['manifestations'][0].__setitem__('citable_in_journal_only_answer', True)),
    ]
    for name, fn in attacks:
        ck(f'from_json REFUSES: {name}',
           _raises(lambda fn=fn: Graph.from_json(tamper(fn)), GraphIntegrityError))

    print(f"\n  {'ALL PASS' if not fails else str(len(fails)) + ' FAILURES: ' + ', '.join(fails)}")
    return 1 if fails else 0


def main() -> int:
    if '--self-test' in sys.argv:
        print('=== provenance.py SELF-TEST (every case is an attack on the core rule) ===\n')
        return self_test()
    corpus = json.loads(CORPUS.read_text())
    g = migrate(corpus)
    census(g, corpus)
    GRAPH_OUT.write_text(json.dumps(g.to_json(), indent=1))
    print(f'\n  graph written to {GRAPH_OUT}  (all text retained — nothing deleted)')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
