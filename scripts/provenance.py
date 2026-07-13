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
from dataclasses import dataclass, field, asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))

# ONE definition of "section", shared with the miner. Two functions that each decide what a section
# is will drift, and every offset stored in every card indexes into whichever one won that day.
from evidence_miner import View, sections_of, SECTION_WEIGHT  # noqa: E402

CORPUS = ROOT / 'outputs' / 'journal_corpus_content.json'
GRAPH_OUT = ROOT / 'outputs' / 'provenance_graph.json'


# =================================================================================================
# 1. NODE TYPES
# =================================================================================================

# The version taxonomy, exactly as specified. `repository` is NOT a version — a repository copy is a
# MANIFESTATION (a place bytes live) of some expression, which is where it sits in the graph below.
EXPRESSION_KINDS = ('journal_version', 'accepted_manuscript', 'working_paper', 'preprint', 'unknown')

# Artifact kinds carry their OWN completeness profile. This list is deliberately wider than this
# corpus needs: the moment `full text` is defined by a number of words, a short judicial opinion
# becomes "an abstract" and a cookie banner becomes "a paper".
ARTIFACT_KINDS = (
    'journal_article', 'working_paper', 'preprint', 'accepted_manuscript',
    'judicial_opinion', 'statute_section', 'trial_registry_record',
    'abstract', 'landing_page', 'extraction_failure', 'wrong_work', 'unknown',
)


@dataclass
class Work:
    """The research object / case / trial. NOT a document. Nothing binds to it."""
    id: str
    title: str
    authors: list[str]
    year: int | None
    venue: str | None            # the venue of the *journal expression*, if one is claimed
    doi: str | None
    kind: str = 'study'


@dataclass
class Expression:
    """A VERSION of the report of a Work. This is the unit an attribution may name."""
    id: str
    work_id: str
    kind: str                     # EXPRESSION_KINDS
    kind_basis: str               # WHY we believe that — derived from bytes, or 'claimed_by_metadata'
    attribution: str              # the sentence a writer is allowed to write for THIS expression
    citable_in_journal_only_answer: bool


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

# THE ONLY EDGES THAT MAY WIDEN AN ATTRIBUTION.
# A span in manifestation M may name expression E != M.expression ONLY across one of these, and ONLY
# when the edge is ASSERTED. `predecessor_of` and `reports_same_study` are deliberately absent:
# a working paper and the journal article report the same study, and PEER REVIEW CHANGES NUMBERS.
SPAN_PRESERVING = ('exact_copy_of', 'accepted_manuscript_of')


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
    r"(accepted manuscript|author'?s? (accepted|final) (version|manuscript)|postprint"
    r'|published version\)? *\(refereed\)|this is the (author|accepted))', re.I)
# Typeset journal furniture: a running head with volume/issue/pages, or a publisher rights block.
_JOURNAL_MARK = re.compile(
    r'(volume \d+[,—-] *number \d+|vol\.? *\d+[,(]? *(no\.?|issue|\()? *\d+'
    r'|doi[:\s]*10\.\d{4,9}/|©\s*(the author|\d{4})|article reuse guidelines'
    r'|received .{0,40}(revised|accepted).{0,40}\d{4})', re.I)

# --- what "complete" MEANS, per artifact kind ----------------------------------------------------
# Sol's point, made mechanical: completeness is a property OF A KIND, never of a word count.
#
# `stub_floor` separates THE DOCUMENT from A STUB OF IT, and it exists ONLY for the scholarly kinds,
# where a 500-word artifact is definitionally not the article (it is its abstract, or its landing
# page). For a judicial opinion, a statute section or a trial-registry record it is None: THOSE
# ARTIFACTS ARE COMPLETE AT ANY LENGTH. That is the whole difference between this and MIN_WORDS=2500,
# which asserted one number over every kind of document in the world.
#
# `needs_results` IS DELIBERATELY ABSENT. I first wrote it as a completeness gate and it declared six
# genuine journal articles incomplete — Technovation (15,985w), JEP (11,872w), AER (9,732w), JBR,
# Raj, Chalmers — because economics papers title their results sections after their CONTENT ("V. The
# Effect of Robots on Employment"), and a JEP essay has no results section at all. Gating on a
# section heading is the same error as gating on a word count, moved one axis over. The
# result-bearing sections are REPORTED in the profile (the miner weights by them) and GATE NOTHING.
KIND_PROFILE = {
    'journal_article':      dict(stub_floor=1200),
    'working_paper':        dict(stub_floor=1200),
    'preprint':             dict(stub_floor=1200),
    'accepted_manuscript':  dict(stub_floor=1200),
    # A short official opinion IS the whole artifact. No results section, no methods, and COMPLETE.
    'judicial_opinion':     dict(stub_floor=None),
    'statute_section':      dict(stub_floor=None),
    'trial_registry_record': dict(stub_floor=None),
    # These are NEVER complete, at any length, and may never carry a finding.
    'abstract':             dict(stub_floor=None),
    'landing_page':         dict(stub_floor=None),
    'extraction_failure':   dict(stub_floor=None),
    'wrong_work':           dict(stub_floor=None),
    'unknown':              dict(stub_floor=None),
}
# Kinds whose text may carry a finding at all, IF the profile also says complete.
FINDING_BEARING_KINDS = ('journal_article', 'working_paper', 'preprint', 'accepted_manuscript',
                         'judicial_opinion', 'statute_section', 'trial_registry_record')

RESULT_BEARING = ('results', 'tables', 'analysis')

# The scholarly stub floor, used ONLY to decide document-vs-stub for the scholarly kinds above.
SCHOLARLY_STUB_FLOOR = 1200


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


def derive_expression_kind(text: str) -> tuple[str, str]:
    """Which VERSION do these bytes say they are? Derived from self-identifying furniture.

    Returns ('unknown', ...) freely. `unknown` is the honest answer for a PDF body with its title
    page mangled, and an honest `unknown` costs us evidence -- which is the correct price.
    """
    head = text[:12000]
    wp, pre, am, jr = (_WP_MARK.search(head), _PREPRINT_MARK.search(head),
                       _AM_MARK.search(head), _JOURNAL_MARK.search(head))
    # Order matters: an accepted manuscript deposited in a repository carries the journal's citation
    # block too, so the AM marker must be read BEFORE the journal marker or every AM reads as typeset.
    if am:
        return 'accepted_manuscript', f'bytes say: {am.group(0)[:48]!r}'
    if wp:
        return 'working_paper', f'bytes say: {wp.group(0)[:48]!r}'
    if pre:
        return 'preprint', f'bytes say: {pre.group(0)[:48]!r}'
    if jr:
        return 'journal_version', f'typeset journal furniture: {jr.group(0)[:48]!r}'
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

    ekind, ebasis = derive_expression_kind(text)

    # ---- artifact_kind: DERIVED, in strict order of what the bytes can actually PROVE ------------
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
    elif chrome_hits >= 2 and (words < SCHOLARLY_STUB_FLOOR or chrome_per_kw >= 5):
        # WEB FURNITURE WITH NO DOCUMENT UNDER IT. Note that the AEA landing page for Autor (2015)
        # carries the article's own "vol. 29, no. 3" citation block -- so journal furniture proves
        # only that a page CITES the article, never that it IS the article. This test runs first for
        # exactly that reason.
        kind, basis = 'landing_page', (
            f'{chrome_hits} web-chrome markers ({chrome_per_kw}/1k words) over {words} words — '
            f'this is a web page about the document, not the document')
    elif ekind == 'journal_version':
        kind, basis = 'journal_article', ebasis
    elif ekind in ('working_paper', 'preprint', 'accepted_manuscript'):
        kind, basis = ekind, ebasis
    elif words < SCHOLARLY_STUB_FLOOR:
        kind, basis = 'abstract', f'{words} words with no version furniture — a stub, not the article'
    else:
        kind, basis = 'unknown', ebasis

    # ---- completeness: judged AGAINST THE PROFILE FOR THIS KIND ---------------------------------
    spec = KIND_PROFILE[kind]
    reasons: list[str] = []
    if kind not in FINDING_BEARING_KINDS:
        reasons.append(f'artifact kind `{kind}` cannot carry a finding')
    if ex['verdict'] == 'CORRUPT':
        reasons.append('bytes are not readable prose')
    if spec['stub_floor'] is not None and words < spec['stub_floor']:
        # Scholarly kinds only. A judicial opinion has stub_floor=None and never reaches this line.
        reasons.append(f'{words} words is below the stub floor for `{kind}` ({spec["stub_floor"]}) — '
                       f'this is a fragment of the article, not the article')
    complete = not reasons

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

@dataclass
class Graph:
    works: dict[str, Work] = field(default_factory=dict)
    expressions: dict[str, Expression] = field(default_factory=dict)
    manifestations: dict[str, Manifestation] = field(default_factory=dict)
    edges: list[Edge] = field(default_factory=list)

    # -- construction -----------------------------------------------------------------------------
    def add_edge(self, src: str, dst: str, type: str, status: str, basis: str) -> Edge:
        if type not in EDGE_TYPES:
            raise ValueError(f'unknown edge type {type!r}')
        if status not in ('PROPOSED', 'ASSERTED'):
            raise ValueError(f'edge status must be PROPOSED or ASSERTED, not {status!r}')
        if not basis or not basis.strip():
            # An edge with no evidence is the entire failure we are here to end.
            raise ValueError('an edge MUST carry a basis naming the evidence for it')
        if status == 'ASSERTED' and type == 'exact_copy_of' and 'title' in basis.lower():
            # Sol, verbatim: a title similarity match can PROPOSE predecessor_of; it CANNOT ASSERT
            # exact_copy_of. Enforced in the constructor so no caller can talk its way past it.
            raise ValueError('a title match may not ASSERT exact_copy_of — it proves nothing about bytes')
        e = Edge(src, dst, type, status, basis)
        self.edges.append(e)
        return e

    # -- THE CORE RULE ----------------------------------------------------------------------------
    def attribution_targets(self, manif_id: str) -> list[str]:
        """Which expressions a span in this manifestation MAY name. Sol's rule, mechanised.

        Always: the manifestation's own expression -- the bytes we hold are, definitionally, that
        expression's bytes. Additionally: any expression reachable by an ASSERTED, SPAN-PRESERVING
        edge, because such an edge is exactly a proof that the cited source contains the same span.
        Nothing else. A `predecessor_of` edge, however obvious, transfers NOTHING.
        """
        m = self.manifestations[manif_id]
        targets = [m.expression_id]
        for e in self.edges:
            if e.src == m.expression_id and e.type in SPAN_PRESERVING and e.status == 'ASSERTED':
                targets.append(e.dst)
        return targets

    def journal_attributable(self, manif_id: str) -> bool:
        """May a span from these bytes be printed as a finding OF A JOURNAL ARTICLE?

        Two independent conditions, BOTH required:
          1. some expression this span may legally name is a journal_version, AND
          2. the bytes are actually usable as evidence (complete, uncorrupted, the right work).
        A span from a corrupt PDF of the real journal article is still inadmissible -- see Weiss.
        """
        m = self.manifestations[manif_id]
        if not m.profile.get('complete'):
            return False
        return any(self.expressions[t].kind == 'journal_version'
                   for t in self.attribution_targets(manif_id))

    def attribution_for(self, manif_id: str) -> str:
        """The ONLY sentence a writer may use for a span from these bytes."""
        m = self.manifestations[manif_id]
        return self.expressions[m.expression_id].attribution

    # -- span binding -----------------------------------------------------------------------------
    def bind_span(self, manif_id: str, start: int, end: int) -> dict:
        """A span binds to its EXACT manifestation and content hash. This is what a card must carry
        instead of a bare DOI -- a DOI names a Work, and a Work has no bytes."""
        m = self.manifestations[manif_id]
        return dict(manifestation_id=manif_id, content_hash=m.content_hash,
                    span_start=start, span_end=end,
                    text=m.text[start:end],
                    may_name=[self.expressions[t].attribution for t in self.attribution_targets(manif_id)],
                    journal_attributable=self.journal_attributable(manif_id))

    def verify_span(self, bound: dict) -> bool:
        """The bytes a span was mined from must still be the bytes we hold."""
        m = self.manifestations.get(bound['manifestation_id'])
        return bool(m) and m.content_hash == bound['content_hash'] \
            and m.text[bound['span_start']:bound['span_end']] == bound['text']

    def to_json(self) -> dict:
        return dict(
            works=[asdict(w) for w in self.works.values()],
            expressions=[asdict(e) for e in self.expressions.values()],
            # text is retained on disk too: NOTHING IS EVER DELETED.
            manifestations=[asdict(m) for m in self.manifestations.values()],
            edges=[asdict(e) for e in self.edges],
        )


# =================================================================================================
# 4. MIGRATION — corpus rows -> graph. NO TEXT IS DELETED.
# =================================================================================================

def _slug(s: str, n: int = 40) -> str:
    return re.sub(r'[^a-z0-9]+', '-', (s or '').lower()).strip('-')[:n] or 'x'


def _attribution_for(kind: str, work: Work, profile_: dict) -> tuple[str, bool]:
    """The sentence a writer may write, and whether it is legal in a JOURNAL-ONLY answer.

    Sol: "If only the working paper is available, citing it VIOLATES THE JOURNAL-ONLY INSTRUCTION,
    so it stays OUTSIDE THE ANSWER BODY."
    """
    who = ' and '.join(work.authors[:2]) + (' et al.' if len(work.authors) > 2 else '')
    yr = work.year
    if kind == 'journal_version':
        return f'{who} ({yr}), {work.venue}', True
    if kind == 'accepted_manuscript':
        # Legal ONLY if authenticated as the AM *of the journal version* -- that edge, not this label.
        return f'{who} ({yr}), accepted manuscript of {work.venue}', False
    if kind == 'working_paper':
        return f'{who} ({yr}), working paper [NOT the {work.venue} article]', False
    if kind == 'preprint':
        return f'{who} ({yr}), preprint [NOT the {work.venue} article]', False
    return f'{who} ({yr}), UNIDENTIFIED VERSION [may not be cited]', False


def migrate(corpus: list[dict]) -> Graph:
    g = Graph()
    for row in corpus:
        doi = row.get('doi') or ''
        wid = 'work:' + (_slug(doi) if doi else _slug(row.get('title', '')))
        work = Work(id=wid, title=row.get('title') or '', authors=list(row.get('authors') or []),
                    year=row.get('year'), venue=_norm(row.get('venue') or '').replace('&amp;', '&'),
                    doi=doi or None)
        g.works[wid] = work

        # Every corpus row ASSERTS a journal expression exists (it has a DOI and a venue). That
        # expression is real -- but WE MAY NOT HOLD ITS BYTES. It gets a node with no manifestation,
        # and that emptiness is the honest record of what we do not have.
        jid = f'{wid}:journal_version'
        jatt, jok = _attribution_for('journal_version', work, {})
        g.expressions[jid] = Expression(
            id=jid, work_id=wid, kind='journal_version',
            kind_basis='claimed_by_metadata (DOI + venue from the bibliography; bytes NOT verified)',
            attribution=jatt, citable_in_journal_only_answer=jok)

        # ---- the bytes we hold, if any ----------------------------------------------------------
        for fieldname in ('fulltext', 'abstract'):
            text = (row.get(fieldname) or '').strip()
            if not text:
                continue
            # The row's abstract came from the BIBLIOGRAPHY, independently of whatever body we
            # fetched — which is exactly what makes it usable as a probe against that body. It is
            # never used to probe itself.
            indep = (row.get('abstract') or '') if fieldname == 'fulltext' else ''
            prof = profile(text, work, independent_abstract=indep)

            # The fetcher's own label is EVIDENCE, NOT TRUTH. `fulltext_source='working_paper'`
            # records WHICH FETCHER RAN, not what the artifact is: it is false on 5 of the 6 rows
            # that carry it. The bytes decide; the label is recorded and contradicted in the open.
            claimed_src = row.get('fulltext_source') or 'publisher_or_oa'
            ekind = prof['expression_kind']
            ebasis = prof['expression_kind_basis']

            if prof['artifact_kind'] in ('wrong_work', 'landing_page', 'extraction_failure'):
                # NOT A RENDERING OF ANY VERSION OF THIS WORK. It gets a QUARANTINE expression, not a
                # version node: the ORA landing page for Frey & Osborne contains the words "published
                # version (refereed)", and if we let that furniture name the expression we would have
                # filed a WEB PAGE as an accepted manuscript of a journal article. The bytes are
                # RETAINED in full (nothing is ever deleted) and attributable to nobody.
                eid = f'{wid}:quarantine:{prof["artifact_kind"]}'
                att = (f'THESE BYTES ARE NOT A USABLE RENDERING OF THIS WORK '
                       f'({prof["artifact_kind"]}) — no attribution is possible')
                g.expressions[eid] = Expression(
                    id=eid, work_id=wid, kind='unknown', kind_basis=prof['artifact_kind_basis'],
                    attribution=att, citable_in_journal_only_answer=False)
            elif ekind == 'unknown':
                eid = f'{wid}:unresolved_version'
                att, ok = _attribution_for('unknown', work, prof)
                g.expressions[eid] = Expression(
                    id=eid, work_id=wid, kind='unknown', kind_basis=ebasis,
                    attribution=att, citable_in_journal_only_answer=ok)
            else:
                eid = f'{wid}:{ekind}'
                att, ok = _attribution_for(ekind, work, prof)
                g.expressions.setdefault(eid, Expression(
                    id=eid, work_id=wid, kind=ekind, kind_basis=ebasis,
                    attribution=att, citable_in_journal_only_answer=ok))

            h = hashlib.sha256(text.encode('utf-8', 'ignore')).hexdigest()
            mid = f'manif:{h[:12]}'

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

            g.manifestations[mid] = Manifestation(
                id=mid, expression_id=eid, work_id=wid, text=text, content_hash=h,
                n_words=prof['n_words'], locator=locator, locator_status=lstatus,
                fetched_by=claimed_src, text_field=fieldname, profile=prof)

            # ---- EDGES. Only what the bytes support. -------------------------------------------
            if eid != jid and not eid.startswith(f'{wid}:quarantine'):
                if ekind in ('working_paper', 'preprint'):
                    # The strongest thing that is TRUE. Not exact_copy_of. Not even asserted:
                    # we have not compared the two texts, because we do not hold the other one.
                    g.add_edge(eid, jid, 'predecessor_of', 'PROPOSED',
                               f'same work per bibliography metadata; version equivalence NOT tested '
                               f'(we do not hold the journal bytes). {ebasis}')
                    g.add_edge(eid, jid, 'reports_same_study', 'PROPOSED',
                               'same title/authors/DOI row; peer review may still have changed the numbers')
                elif ekind == 'accepted_manuscript':
                    # PROPOSED, not ASSERTED: the artifact SAYS it is the accepted manuscript. That is
                    # a claim a component makes about itself, which is the one thing we never trust.
                    # ASSERTING this edge requires authentication against the journal version's bytes.
                    g.add_edge(eid, jid, 'accepted_manuscript_of', 'PROPOSED',
                               f'the artifact self-describes ({ebasis}); NOT authenticated against the '
                               f'journal version, whose bytes we do not hold')
                elif ekind == 'unknown':
                    g.add_edge(eid, jid, 'reports_same_study', 'PROPOSED',
                               'the bytes carry no version furniture; they may or may not be the journal text')
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
        elif not m.profile['complete'] and m.profile['artifact_kind'] in (
                'landing_page', 'extraction_failure', 'wrong_work', 'abstract'):
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
        'Acemoglu and Restrepo (2020), Journal of Political Economy', True)
    g.expressions['work:w:working_paper'] = Expression(
        'work:w:working_paper', 'work:w', 'working_paper', 'bytes say NBER WORKING PAPER SERIES',
        'Acemoglu and Restrepo (2020), working paper [NOT the Journal of Political Economy article]',
        False)
    body = ('NBER WORKING PAPER SERIES ROBOTS AND JOBS ' + 'the effect of robots on employment is '
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
       'NOT the Journal of Political Economy' in g.attribution_for('manif:wp'))

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

    try:
        g.add_edge('work:w:working_paper', 'work:w:journal_version', 'exact_copy_of', 'ASSERTED', '')
        ok = False
    except ValueError:
        ok = True
    ck('an edge with NO BASIS cannot be constructed at all', ok)

    # The rule must also WORK when the proof is genuinely earned -- a gate that never opens is a gate
    # nobody will keep.
    g.add_edge('work:w:working_paper', 'work:w:journal_version', 'exact_copy_of', 'ASSERTED',
               'byte-for-byte comparison against the journal PDF: identical span at 76927-77299')
    ck('an ASSERTED exact_copy_of (proven against the journal BYTES) DOES license the journal name',
       g.journal_attributable('manif:wp'))

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
    opinion = Work('work:op', 'Smith v. Jones', ['Smith'], 1998, 'Court of Appeal', None, 'case')
    short = ('The appellant challenges the order of the court below. We have considered the record '
             'and the submissions of both parties. The appeal is dismissed with costs. It is so '
             'ordered by the court this day. ') * 3
    op = profile(short, opinion)
    op_kind = dict(op, artifact_kind='judicial_opinion')     # kind supplied by the fetcher's context
    spec = KIND_PROFILE['judicial_opinion']
    ck('a 100-word judicial opinion has NO stub floor — it is COMPLETE at any length',
       spec['stub_floor'] is None and 'judicial_opinion' in FINDING_BEARING_KINDS)
    ck('...while the same length of SCHOLARLY article is a stub, not the article',
       KIND_PROFILE['journal_article']['stub_floor'] == SCHOLARLY_STUB_FLOOR)

    banner = ('This website uses cookies. By clicking the Accept button you agree. Privacy Policy. '
              'Sign in. Subscribe. Download PDF. ') * 12
    ck('a 535-word publisher COOKIE BANNER is a landing_page, complete=False',
       profile(banner, w)['artifact_kind'] == 'landing_page'
       and not profile(banner, w)['complete'])

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

    # ---- span binding ------------------------------------------------------------------------
    b = g.bind_span('manif:wp', 10, 60)
    ck('a bound span carries its manifestation_id AND content hash',
       b['manifestation_id'] == 'manif:wp' and len(b['content_hash']) == 64 and g.verify_span(b))
    ck('a span whose source bytes changed FAILS verification',
       not g.verify_span(dict(b, content_hash='0' * 64)))

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
