#!/usr/bin/env python3
"""THE TYPED REPORT AST — THE LAW, MECHANISED. There is no other way to say a sentence.

    Every sentence is ATTRIBUTED (names a source -> MUST be entailed by THAT source's VERBATIM SPAN)
    or OWNED (reviewer's voice -> names no source, carries no new particular, MAY be non-entailed).
    THE VERBATIM SPAN IS THE ONLY EVIDENCE. The model-written `claim` is a display cache; nothing is
    ever validated against it.

WHY THIS FILE EXISTS, AND WHY IT IS NOT ANOTHER PREFLIGHT
---------------------------------------------------------
Six adversary attacks succeeded while `test_gate_is_wired.py` was 16/16 GREEN and nothing had been
weakened. The reason was not a weak check. It was that **the checks certified a lane the fabrication no
longer used**: 6,463 lines of correct, self-tested modules were dead code, and the composer imported not
one of them. `provenance.py` passed its own 18/18 self-test while the P0 it was built to stop sat live on
disk.

So the gate is no longer a function the writer is asked to call. IT IS THE ONLY TYPE A SENTENCE CAN HAVE.
A sentence that has not been through here is not "ungated" — IT DOES NOT EXIST, because prose is never
concatenated anywhere in this pipeline. `render()` is the only thing that emits characters, it emits them
only from validated nodes, and `publisher.py` is the only thing that may write them into the release
directory.

WHAT CHANGED IN THE SHAPE OF A SENTENCE
---------------------------------------
The old composer inferred WHO A SENTENCE WAS ABOUT BY LOOKING FOR SURNAMES IN IT (`_cited_cards`). That
is how "Bresnahan reports task displacement" — a real mechanism, a real paper, a FABRICATED BINDING —
was gated against whichever card the regex happened to hit first. Sol: **DO NOT INFER VOICE OR SOURCE
IDENTITY FROM SURNAMES.**

Here, the model does not write attribution prose AT ALL, and it does not get to imply a source by naming
one. It emits a bare FINDING plus THE CARD ID it came from:

    Attributed(clauses=[Clause(card_id='...:76927-77299', text='the employment-to-population ratio
                               falls by 0.37 percentage points per robot per thousand workers')])

and THIS FILE renders the attribution — from the graph, from the expression the SOURCE POLICY selected.
The model cannot copy an attribution, cannot invent one, and cannot name a journal whose bytes we do not
hold, because it never types the journal's name.

A CROSS-SOURCE SENTENCE IS A CONJUNCTION OF ATTRIBUTED CLAUSES, EACH BOUND TO ITS OWN CARD. That keeps
the heaviest criterion on the board (critical synthesis, w=0.0800) reachable — the old gate deleted every
comparative sentence — while the fabricated binding still dies, because the clause that says "task
displacement" names Bresnahan's card_id and 'task displacement' is not in Bresnahan's span.

THE CHAIN, WHICH IS THE WHOLE POINT
-----------------------------------
    sentence -> card -> bound span -> manifestation_id + content_hash -> permitted expression -> attribution

`CardBundle.resolve()` IS that chain, as one function, and it is the only door. Nothing in this file, in
`cellcog_composer.py`, or in `publisher.py` reads a card's `attribution`, `venue`, `doi` or `authors` to
decide anything. Those are display caches. The graph decides.
"""
from __future__ import annotations

import hashlib
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'scripts'))

import provenance as P  # noqa: E402
from synthesis_contract import Premise, Synthesis, validate, OPERATIONS  # noqa: E402


# =================================================================================================
# 0. THE NODES. A report is a list of these and NOTHING ELSE.
# =================================================================================================

@dataclass(frozen=True)
class Clause:
    """ONE finding, from ONE card. The text is the FINDING ONLY — no attribution, no journal, no year.

    `card_id` is not a hint and it is not decoration: it is the sentence's ONLY connection to reality,
    and it is checked against the bytes. The model may not name a source in `text`; if it does, the
    clause is refused (SOURCE_NAMED_IN_CLAUSE_TEXT), because a named source in model prose is a source
    WE DID NOT RESOLVE.
    """
    card_id: str
    text: str


#: How clause i>0 joins the clause before it. A CLOSED SET — the model may not write connective prose,
#: because a connective is where an unsourced particular hides ("..., which explains why 40% of...").
CONNECTIVES = ('while', 'whereas', 'by contrast', 'and', 'though', 'but', 'yet')


@dataclass(frozen=True)
class Attributed:
    """A sentence that names sources. EVERY clause is entailed by ITS OWN card's verbatim span."""
    clauses: tuple[Clause, ...]
    connective: str = 'while'

    def card_ids(self) -> tuple[str, ...]:
        return tuple(c.card_id for c in self.clauses)


@dataclass(frozen=True)
class Owned:
    """The reviewer's voice. MAY BE NON-ENTAILED — that is what insight IS.

    It must name NO source and carry NO new particular. Two regimes, one type:

      * `premise_ids` non-empty  -> a SYNTHESIS over admitted premises. It must additionally pass a
        typed operation in `synthesis_contract` (a mechanism may appear ONLY if a premise states it).
        This is the body lane.
      * `premise_ids` empty      -> a FRAME sentence (an abstract's "Objective.", a section's bridge).
        It is licensed by nothing and may therefore assert nothing particular: no number, no source, no
        proper noun the review has not already earned. This is the lane the hand-written abstract used
        to bypass the law through, and it is now a TYPE with a CHECK, not an f-string in write_report().
    """
    text: str
    premise_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class Heading:
    level: int
    text: str


@dataclass(frozen=True)
class ParagraphBreak:
    """A paragraph boundary, AS A NODE — so a paragraph cannot be made by concatenating a '\\n\\n'.

    If whitespace were prose, the writer would have a lane that emits characters without a type, and
    every hole in this file's header began as a lane that emitted characters without a type.
    """


@dataclass(frozen=True)
class EvidenceTable:
    """Every cell is a field of a card whose binding RE-VERIFIES at render time. No model prose."""
    card_ids: tuple[str, ...]
    caption: str = ('**Table 1. Quantitative findings across the reviewed literature.** Each row reports '
                    'a figure stated by the cited paper itself, verified against that paper\'s own bytes.')


Node = Attributed | Owned | Heading | ParagraphBreak | EvidenceTable


# =================================================================================================
# 1. THE CHAIN.  sentence -> card -> bound span -> manifestation + hash -> permitted expression
# =================================================================================================

@dataclass(frozen=True)
class Resolution:
    ok: bool
    card_id: str
    refusal: str = ''
    manifestation_id: str = ''
    content_hash: str = ''
    expression_id: str = ''            # the expression whose bytes the span ACTUALLY came from
    names_expression_id: str = ''      # the expression the sentence is PERMITTED to name
    span: str = ''                     # THE VERBATIM SPAN. THE ONLY EVIDENCE.
    span_start: int = -1
    span_end: int = -1
    work_id: str = ''
    attribution: str = ''              # RENDERED FROM THE GRAPH. Never copied off the card.
    card: dict = field(default_factory=dict)


def _binding_from_card(c: dict) -> dict:
    """The binding a card carries, in the shape `Graph.verify_span()` demands.

    A card that has not been through `graph.bind_span()` HAS NO BINDING, and this returns {} rather than
    a plausible-looking dict assembled from a DOI and two integers. That distinction is the P0: a DOI
    names a WORK, and a work has no bytes.
    """
    if not c.get('manifestation_id') or not c.get('content_hash'):
        return {}
    for k in ('span_start', 'span_end', 'span_raw'):
        if c.get(k) is None:
            return {}
    return dict(
        manifestation_id=c['manifestation_id'],
        content_hash=c['content_hash'],
        span_start=c['span_start'],
        span_end=c['span_end'],
        text=c['span_raw'],
        permitted_expression_ids=list(c.get('permitted_expression_ids') or []),
    )


class CardBundle:
    """ONE card lane. ONE graph. ONE policy. THE SEAM IS GONE.

    There were TWO DISCONNECTED CARD LANES: the miner wrote `evidence_cards_v2.json` and the composer
    read `evidence_cards.json` — a file whose cards carry no manifestation, no hash and no expression,
    and whose four Frey & Osborne cards were mined out of an ORA LANDING PAGE. The composer could not
    have detected that, because the lane it read had nothing in it to detect with.

    A bundle is constructed from an EXPLICIT path plus the graph, and it REFUSES to exist if the bytes
    on disk are not the bytes it was promised.
    """

    def __init__(self, cards: list[dict], graph: P.Graph,
                 policy: P.SourcePolicy = P.JOURNAL_ONLY,
                 cards_sha: str = '', graph_sha: str = '', ledger_sha: str = ''):
        self.graph = graph
        self.policy = policy
        self.cards_sha = cards_sha
        self.graph_sha = graph_sha
        self.ledger_sha = ledger_sha
        # A DUPLICATE CARD ID IS A REFUSAL, NOT AN OVERWRITE.
        #
        # This dict used to be filled with `self.cards[cid] = c`, and the miner's id is
        # `{doi}:{span_start}-{span_end}` — so TWO FINDINGS MINED FROM ONE SPAN COLLIDE. On the first
        # real bundle, 13 of 52 cards were silently overwritten: the composer printed "52 cards, 0
        # refused" and had 39. The evidence did not fail a check. IT LEFT WITHOUT ONE, which is the
        # quieter half of every defect in this file's header. And a sentence citing a colliding id
        # names an AMBIGUOUS card: same span, different claim, different act, different table row.
        self.cards: dict[str, dict] = {}
        dupes: dict[str, int] = {}
        for c in cards:
            cid = c.get('id')
            if not cid:
                raise ValueError('a card with no `id` cannot be cited by a sentence, and is REFUSED')
            if cid in self.cards:
                dupes[cid] = dupes.get(cid, 1) + 1
                continue
            self.cards[cid] = c
        if dupes:
            n = sum(dupes.values()) - len(dupes)
            raise ValueError(
                f'{len(dupes)} DUPLICATE CARD ID(S) ({n} cards would be silently dropped) — a bundle '
                f'whose ids are ambiguous is not a bundle, and a sentence citing one of them names no '
                f'determinate evidence. Offenders: {sorted(dupes)[:3]}')
        self._cache: dict[str, Resolution] = {}
        # Every surname and venue the bundle knows. Used ONLY NEGATIVELY — to refuse a source name in
        # a lane that is not allowed to have one. We never infer WHICH source from a surname again.
        self._source_words: set[str] = set()
        for c in self.cards.values():
            for a in (c.get('authors') or []):
                if len(a) >= 4:
                    self._source_words.add(a.lower())
        for w in graph.works.values():
            for a in (w.authors or []):
                if len(a) >= 4:
                    self._source_words.add(a.lower())

    # -- THE ONLY DOOR ----------------------------------------------------------------------------
    def resolve(self, card_id: str) -> Resolution:
        """sentence -> card -> bound span -> manifestation_id + content_hash -> permitted expression
        -> attribution.

        EVERY step is re-derived from the graph HERE, at use time. Nothing stored on the card is
        trusted: not the attribution, not the permitted set, not the expression, not the hash.

        `verify_span()` is called FIRST — before any field of the card is read for any purpose — because
        a card whose bytes do not verify is not a weak card, it is NOT A CARD, and reading its `venue`
        to make a decision is how a landing page became a peer-reviewed article.
        """
        if card_id in self._cache:
            return self._cache[card_id]
        r = self._resolve(card_id)
        self._cache[card_id] = r
        return r

    def _resolve(self, card_id: str) -> Resolution:
        c = self.cards.get(card_id)
        if c is None:
            return Resolution(False, card_id, refusal='NO_SUCH_CARD_IN_BUNDLE')

        binding = _binding_from_card(c)
        if not binding:
            return Resolution(False, card_id, refusal='CARD_IS_UNBOUND (no manifestation_id/content_hash '
                                                      '/span offsets — a DOI names a work, and a work has '
                                                      'no bytes)')
        # ---- 1. THE BYTES. Untrusted input; re-check offsets, hash, and the text itself.
        if not self.graph.verify_span(binding):
            return Resolution(False, card_id, refusal=f'SPAN_DOES_NOT_VERIFY against '
                                                      f'{binding["manifestation_id"]}')
        mid = binding['manifestation_id']
        m = self.graph.manifestations[mid]

        # ---- 2. THE POLICY. What, if anything, may a span in these bytes NAME?
        att = self.graph.resolve_attribution(mid, self.policy)
        if not att.admitted:
            return Resolution(False, card_id, refusal=f'SOURCE_POLICY_REFUSES: {att.refusal}')

        # ---- 3. THE CARD'S OWN STORED TARGET MUST BE THE ONE THE GRAPH RESOLVES *NOW*.
        #         A stored target is a cache, and a cache that is not checked is how a stale permission
        #         keeps naming a journal it was never allowed to name.
        stored = c.get('attribution_target_expression_id')
        if stored and stored != att.names_expression_id:
            return Resolution(False, card_id,
                              refusal=f'STALE_ATTRIBUTION_TARGET: card says {stored!r}, the graph '
                                      f'resolves {att.names_expression_id!r} under `{self.policy.name}`')

        # ---- 4. THE ATTRIBUTION IS RENDERED FROM THE GRAPH. The card's own string is never read.
        expr = self.graph.expressions[att.names_expression_id]
        work = self.graph.works[expr.work_id]
        prose = render_attribution(work, expr)
        if not prose:
            return Resolution(False, card_id,
                              refusal=f'EXPRESSION_KIND_IS_NOT_RENDERABLE_AS_A_CITATION: {expr.kind!r}')

        return Resolution(
            True, card_id, manifestation_id=mid, content_hash=binding['content_hash'],
            expression_id=binding.get('expression_id') or m.expression_id,
            names_expression_id=att.names_expression_id,
            span=binding['text'], span_start=binding['span_start'], span_end=binding['span_end'],
            work_id=m.work_id, attribution=prose, card=c)

    def admitted_ids(self) -> list[str]:
        return [cid for cid in self.cards if self.resolve(cid).ok]

    def names_a_source(self, text: str) -> str:
        """The surname/venue check, used ONLY to REFUSE. Returns the offending token, or ''.

        This is not `_cited_cards()` coming back in through a window. That function asked "WHICH source
        is this sentence about?" and answered with a guess, then gated the sentence against the guess.
        This one asks "does this text name ANY source at all?" and uses the answer only to say NO. There
        is no lane in which a surname selects a card.
        """
        low = text.lower()
        for w in self._source_words:
            if re.search(rf'\b{re.escape(w)}\b', low):
                return w
        return ''


# =================================================================================================
# 2. ATTRIBUTION, RENDERED FROM THE GRAPH — NEVER WRITTEN OR COPIED BY A MODEL
# =================================================================================================

#: The year is PROSE, never parenthetical: every one of the 281 "(YYYY)" parentheses in the reference
#: system is deleted by RACE's ArticleCleaner. `Expression.attribution` is the parenthetical display
#: form (`Acemoglu and Restrepo (2020), Journal of Political Economy`); it does not survive the cleaner,
#: so we re-render the SAME FACTS, from the SAME NODES, in the form that does.
_LEAD_FORMS = (
    'Writing in {venue_the} in {year}, {who} show that ',
    '{who}, writing in {venue_the} in {year}, report that ',
    'A {year} {venue} study by {who} finds that ',
    '{who} establish, in {venue_the} in {year}, that ',
    'The evidence {who} present in {venue_the} in {year} is that ',
)
_TRAIL_FORMS = (
    '{who}, writing in {venue_the} in {year}, report that ',
    'in {venue_the} in {year}, {who} show that ',
    '{who} find, in their {year} {venue} paper, that ',
)

#: WHICH EXPRESSION KINDS MAY BE RENDERED AS A JOURNAL CITATION AT ALL.
#: A `working_paper` expression is NOT renderable here, ever, in any form. Under JOURNAL_ONLY it never
#: reaches this function (resolve_attribution refuses it first) — this is the SECOND lock on the same
#: door, and it exists because the first lock is the one that was found unlocked.
_JOURNAL_KINDS = ('journal_version', 'proceedings_version')


#: Venue names that take a definite article ("in the American Economic Review") as against those that do
#: not ("in PLOS ONE", "in Technovation", "in AI and Ethics"). Getting this wrong is not cosmetic: the
#: released artifact said "in the AI and Ethics in 2022", and a reviewer who writes that has not read
#: the journal. The rule is the head noun, not a hand-list of titles.
_TAKES_THE = re.compile(r'\b(journal|review|quarterly|proceedings|annals|bulletin|letters|transactions'
                        r'|magazine|gazette|record|reporter)\b', re.I)


def _venue_the(venue: str) -> str:
    """'the Journal of Political Economy', 'The Quarterly Journal of Economics', 'PLOS ONE'.

    Never 'the The' (the venue already carries its article) and never 'the AI and Ethics'.
    """
    v = (venue or '').strip()
    if not v:
        return ''
    if v.lower().startswith('the '):
        return v
    return f'the {v}' if _TAKES_THE.search(v) else v


def _who(work: P.Work) -> str:
    a = [x for x in (work.authors or []) if x]
    if not a:
        return ''
    if len(a) == 1:
        return a[0]
    if len(a) == 2:
        return f'{a[0]} and {a[1]}'
    return f'{a[0]} and colleagues'


def render_attribution(work: P.Work, expr: P.Expression, lead: bool = True, form: int = 0) -> str:
    """The attribution clause for THIS expression. Returns '' if this expression may not be cited.

    THE MODEL NEVER SEES THIS STRING BEFORE IT WRITES, AND NEVER TYPES IT. It writes a bare finding and
    a card id; the prose below is attached afterwards, from the work and the expression the policy
    chose. That is why "Writing in the Journal of Political Economy..." can no longer appear over bytes
    that came from NBER Working Paper 23285: the sentence's journal name is not something the model can
    produce.
    """
    if expr.kind not in _JOURNAL_KINDS:
        return ''
    who, venue = _who(work), (work.venue or '').strip()
    if not who or not venue or not work.year:
        return ''
    forms = _LEAD_FORMS if lead else _TRAIL_FORMS
    f = forms[form % len(forms)]
    return f.format(who=who, venue=venue, venue_the=_venue_the(venue), year=work.year)


# =================================================================================================
# 3. ENTAILMENT — AGAINST THE VERBATIM SPAN, AND NOTHING ELSE
# =================================================================================================

_STOP = {'writing', 'article', 'journal', 'review', 'that', 'show', 'shows', 'find', 'finds', 'found',
         'report', 'reports', 'reported', 'demonstrate', 'demonstrates', 'evidence', 'study', 'their',
         'this', 'these', 'those', 'with', 'from', 'have', 'been', 'were', 'which', 'while', 'also',
         'than', 'when', 'more', 'most', 'such', 'they', 'them', 'about', 'paper', 'papers', 'result',
         'results', 'finding', 'findings', 'authors', 'author'}

_NUM = re.compile(r'\d+(?:\.\d+)?')


def numbers_in(s: str) -> list[str]:
    return _NUM.findall(s or '')


def number_stands_alone(num: str, src: str) -> bool:
    """`"0.2" in "10.25"` IS TRUE. A substring test leaks a fabricated effect size through any source
    that happens to contain a longer number with the same digits in it — and we deliberately flood this
    prose with figures, which loads that hole with live rounds."""
    return bool(re.search(rf'(?<![\d.]){re.escape(num)}(?![\d])', src))


def entailed_by_span(text: str, span: str, work: P.Work | None = None,
                     min_overlap: float = 0.25) -> tuple[bool, str]:
    """Is THIS text supported by THIS verbatim span? The span is the only evidence there is.

    `claim` — the model's restatement — is not a parameter of this function and never will be. The old
    gate read `src = f'{span} {claim}'`, and since the writer was handed only the claim, the chain was:
    the model writes the claim -> the writer writes from the claim -> the gate checks the writing
    against the claim. THE GATE VALIDATED THE MODEL AGAINST ITSELF.
    """
    src = (span or '').lower()
    if not src:
        return False, 'NO_SPAN'
    year = str(work.year) if work and work.year else ''

    for num in numbers_in(text):
        if len(num) < 2 or num == year:
            continue
        if not number_stands_alone(num, src):
            return False, f'NUMBER_NOT_IN_SPAN:{num}'

    words = {w for w in re.findall(r'[a-z]{4,}', (text or '').lower())} - _STOP
    if work:
        words -= {w for w in re.findall(r'[a-z]{4,}', (work.venue or '').lower())}
        words -= {w for w in re.findall(r'[a-z]{4,}', ' '.join(work.authors or []).lower())}
    if not words:
        return True, ''
    src_words = {w for w in re.findall(r'[a-z]{4,}', src)}
    if len(words & src_words) / len(words) < min_overlap:
        return False, 'CONTENT_NOT_IN_SPAN'
    return True, ''


# =================================================================================================
# 4. VALIDATION — EVERY NODE, EVERY TIME, AT RENDER AND AGAIN AT PUBLISH
# =================================================================================================

MARKER = re.compile(r'\[\d+\]')
PAREN_YEAR = re.compile(r'\((?:19|20)\d\d[a-z]?\)')
BANNED_META = re.compile(
    r'\b(this report|this review synthesi[sz]es|the pipeline|retrieved|the question above|'
    r'span-grounded|telemetry|our system|we retrieved|the corpus|evidence card)\b', re.I)


@dataclass
class Failure:
    node_index: int
    kind: str
    reason: str
    detail: str = ''

    def __str__(self) -> str:
        d = f' :: {self.detail[:80]}' if self.detail else ''
        return f'[{self.node_index}] {self.kind}: {self.reason}{d}'


#: A sentence boundary: a terminator, whitespace, then a capital. Abbreviations ("et al.", "e.g.") and
#: initials are not boundaries — the old splitter amputated every attributed sentence at "et al." and
#: filled the report with stumps.
_ABBREV = re.compile(r'\b(et al|e\.g|i\.e|cf|vs|Dr|Prof|Mr|Mrs|Ms|St|Fig|No|pp|vol|ed|eds|approx|ca)\.$',
                     re.I)
_INITIAL = re.compile(r'\b[A-Z]\.$')


def split_sentences(text: str) -> list[str]:
    out, buf = [], ''
    for chunk in re.split(r'(?<=[.!?])(\s+)', text or ''):
        buf += chunk
        if not chunk.strip():
            continue
        head = buf.strip()
        if _ABBREV.search(head) or _INITIAL.search(head):
            continue
        if re.search(r'[.!?]$', head):
            out.append(head)
            buf = ''
    if buf.strip():
        out.append(buf.strip())
    return [x for x in out if x]


def _common(text: str) -> str:
    """Refusals that apply in EVERY lane, in EVERY node, including the abstract."""
    if not (text or '').strip():
        return 'EMPTY'
    if MARKER.search(text):
        return 'CITATION_MARKER'          # deleted by the cleaner anyway; never write one
    if PAREN_YEAR.search(text):
        return 'PARENTHETICAL_YEAR'       # deleted by the cleaner; the year must be prose
    if BANNED_META.search(text):
        return 'META_COMMENTARY'
    # ---- ONE NODE, ONE SENTENCE. THE LAW IS PER-SENTENCE, SO THE TYPE MUST BE PER-SENTENCE.
    #
    # The publisher caught this on the first real release, and refused it. A node holding TWO sentences
    # gets ONE sentence_hash — the hash of the blob — so the sidecar has no receipt for either sentence
    # as it appears in the file, and `verify_release()` finds prose in the judged artifact that resolves
    # to NOTHING. The receipt has to be per-sentence because THE JUDGE READS SENTENCES.
    #
    # (The offender was my own hand-written Methods paragraph. The law caught its author again.)
    if len(split_sentences(text)) > 1:
        return 'NODE_HOLDS_MORE_THAN_ONE_SENTENCE'
    return ''


def validate_node(i: int, n: Node, b: CardBundle) -> list[Failure]:
    if isinstance(n, ParagraphBreak):
        return []
    if isinstance(n, Heading):
        return [] if (n.text or '').strip() else [Failure(i, 'Heading', 'EMPTY')]

    # ---------------------------------------------------------------- ATTRIBUTED
    if isinstance(n, Attributed):
        f: list[Failure] = []
        if not n.clauses:
            return [Failure(i, 'Attributed', 'NO_CLAUSES')]
        if n.connective and n.connective not in CONNECTIVES:
            f.append(Failure(i, 'Attributed', 'CONNECTIVE_NOT_IN_CLOSED_SET', n.connective))
        for cl in n.clauses:
            why = _common(cl.text)
            if why:
                f.append(Failure(i, 'Attributed', why, cl.text[:70]))
                continue
            # THE CHAIN. If it does not resolve, the sentence does not exist.
            r = b.resolve(cl.card_id)
            if not r.ok:
                f.append(Failure(i, 'Attributed', r.refusal, cl.card_id))
                continue
            # THE MODEL MAY NOT NAME A SOURCE. It names a card_id; WE name the source.
            named = b.names_a_source(cl.text)
            if named:
                f.append(Failure(i, 'Attributed', 'SOURCE_NAMED_IN_CLAUSE_TEXT',
                                 f'{named!r} — attribution is rendered from the graph, not typed by '
                                 f'the model'))
                continue
            # ENTAILMENT, AGAINST THIS CLAUSE'S OWN CARD'S SPAN. This is the line that kills the
            # fabricated binding: the clause that says "task displacement" names Bresnahan's card,
            # and Bresnahan's span does not say it.
            work = b.graph.works.get(r.work_id)
            ok, why2 = entailed_by_span(cl.text, r.span, work)
            if not ok:
                f.append(Failure(i, 'Attributed', why2, f'{cl.card_id} :: {cl.text[:60]}'))
        return f

    # ---------------------------------------------------------------- OWNED
    if isinstance(n, Owned):
        why = _common(n.text)
        if why:
            return [Failure(i, 'Owned', why, n.text[:70])]
        # 1. NAMES NO SOURCE.
        named = b.names_a_source(n.text)
        if named:
            return [Failure(i, 'Owned', 'OWNED_NAMES_A_SOURCE',
                            f'{named!r} — a sentence that names a source is ATTRIBUTED, and must be '
                            f'entailed by that source. It may not enter through the owned lane.')]
        # 2. CARRIES NO NEW PARTICULAR. A figure in the reviewer's own voice is sourced to nothing.
        if re.search(r'\d', n.text):
            return [Failure(i, 'Owned', 'OWNED_CARRIES_A_NUMBER', n.text[:70])]
        # 3. If it is licensed by premises, it must be a TYPED SYNTHESIS over them.
        if n.premise_ids:
            prem: dict[str, Premise] = {}
            for pid in n.premise_ids:
                r = b.resolve(pid)
                if not r.ok:
                    return [Failure(i, 'Owned', f'PREMISE_UNRESOLVED: {r.refusal}', pid)]
                c = r.card
                prem[pid] = Premise(
                    id=pid, text=r.span, source=r.attribution,
                    level=c.get('level', '') or c.get('unit_of_analysis', ''),
                    horizon=c.get('horizon', ''), method=c.get('method', '') or c.get('design', ''),
                    mechanisms=c.get('mechanisms') or [])
            if len(prem) < 2:
                return [Failure(i, 'Owned', 'SYNTHESIS_NEEDS_2_PREMISES', str(n.premise_ids))]
            for op in OPERATIONS:
                ok, _ = validate(Synthesis(op, list(prem), n.text), prem)
                if ok:
                    return []
            _, why2 = validate(Synthesis('CONTRASTS_LEVEL', list(prem), n.text), prem)
            return [Failure(i, 'Owned', f'SYNTHESIS_REFUSED:{why2}', n.text[:70])]
        # 4. A FRAME sentence: licensed by nothing, so it asserts nothing particular. Already checked
        #    for numbers and source names above. That is the whole of what the law permits it.
        return []

    # ---------------------------------------------------------------- TABLE
    if isinstance(n, EvidenceTable):
        f = []
        for cid in n.card_ids:
            r = b.resolve(cid)
            if not r.ok:
                f.append(Failure(i, 'EvidenceTable', r.refusal, cid))
                continue
            # EVERY FIGURE IN THE ROW MUST STAND AS ITS OWN NUMBER IN THAT ROW'S OWN SPAN.
            claim = (r.card.get('claim') or '')
            work = b.graph.works.get(r.work_id)
            ok, why = entailed_by_span(claim, r.span, work, min_overlap=0.34)
            if not ok:
                f.append(Failure(i, 'EvidenceTable', f'ROW_{why}', f'{cid} :: {claim[:50]}'))
        return f

    return [Failure(i, type(n).__name__, 'UNKNOWN_NODE_TYPE')]


def validate_report(nodes: list[Node], b: CardBundle) -> list[Failure]:
    out: list[Failure] = []
    for i, n in enumerate(nodes):
        out += validate_node(i, n, b)
    return out


# =================================================================================================
# 5. RENDER — THE ONLY PLACE PROSE IS EVER PRODUCED
# =================================================================================================

def _fmt_sentence(n: Attributed, b: CardBundle, form_seed: int) -> str:
    parts = []
    for j, cl in enumerate(n.clauses):
        r = b.resolve(cl.card_id)
        expr = b.graph.expressions[r.names_expression_id]
        work = b.graph.works[expr.work_id]
        att = render_attribution(work, expr, lead=(j == 0), form=form_seed + j)
        body = cl.text.strip().rstrip('.')
        # lower-case the first letter of the finding: it follows "...show that".
        if body and body[0].isupper() and not body.startswith(tuple(w for w in ['AI', 'US', 'UK', 'EU'])):
            body = body[0].lower() + body[1:]
        parts.append((att + body) if j == 0 else f'{n.connective} {att}{body}')
    s = ', '.join(parts) if len(parts) > 1 else parts[0]
    return re.sub(r'\s+', ' ', s).strip() + '.'


def _table(n: EvidenceTable, b: CardBundle, limit: int = 14) -> str:
    import html
    rows = []
    for cid in n.card_ids[:limit]:
        r = b.resolve(cid)
        c = r.card
        expr = b.graph.expressions[r.names_expression_id]
        work = b.graph.works[expr.work_id]
        who = _who(work)
        claim = re.sub(r'\s+', ' ', html.unescape(c.get('claim') or '')).rstrip('.')
        if len(claim) > 155:
            claim = claim[:152].rsplit(' ', 1)[0] + '...'
        cell = lambda x: html.unescape(str(x or '--')).replace('|', '/')
        rows.append(f"| {cell(who)}, {work.year} | {cell(work.venue)[:34]} | "
                    f"{cell(c.get('level') or c.get('unit_of_analysis'))} | "
                    f"{cell(c.get('method') or c.get('design'))} | {claim} |")
    if len(rows) < 3:
        return ''
    return '\n'.join(['', n.caption, '',
                      '| Study | Journal | Level | Method | Quantitative finding |',
                      '|---|---|---|---|---|'] + rows)


def sentence_hash(s: str) -> str:
    """The sidecar's key. Normalised, so a whitespace edit to the released file is still resolvable —
    and a WORD edit is not."""
    return hashlib.sha256(re.sub(r'\s+', ' ', s.strip()).encode('utf-8')).hexdigest()


def render(nodes: list[Node], b: CardBundle) -> tuple[str, list[dict]]:
    """-> (markdown, sidecar). REFUSES to render an invalid report; it does not skip bad nodes.

    Skipping is what a composer does. A composer that drops the sentences it cannot justify still
    produces a document, and the document it produces is the one that gets published. THIS returns
    nothing at all unless EVERY node is lawful — which is why `publisher.py` can trust what it is
    handed, and why it re-validates anyway.
    """
    fails = validate_report(nodes, b)
    if fails:
        raise ValueError(f'{len(fails)} unlawful node(s); NOTHING IS RENDERED:\n  - ' +
                         '\n  - '.join(str(f) for f in fails[:25]))
    md: list[str] = []
    sidecar: list[dict] = []
    para: list[str] = []
    form_seed = 0

    def flush():
        if para:
            md.append(' '.join(para))
            md.append('')
            para.clear()

    for n in nodes:
        if isinstance(n, ParagraphBreak):
            flush()
        elif isinstance(n, Heading):
            flush()
            md.append(f"{'#' * n.level} {n.text}")
            md.append('')
        elif isinstance(n, Attributed):
            s = _fmt_sentence(n, b, form_seed)
            form_seed += 1
            para.append(s)
            for cl in n.clauses:
                r = b.resolve(cl.card_id)
                sidecar.append(dict(
                    sentence_hash=sentence_hash(s), sentence=s, voice='ATTRIBUTED',
                    card_id=cl.card_id, manifestation_id=r.manifestation_id,
                    content_hash=r.content_hash, span_start=r.span_start, span_end=r.span_end,
                    span=r.span, work_id=r.work_id, expression_id=r.expression_id,
                    names_expression_id=r.names_expression_id, policy=b.policy.name,
                    attribution=r.attribution))
        elif isinstance(n, Owned):
            s = re.sub(r'\s+', ' ', n.text.strip())
            para.append(s)
            sidecar.append(dict(sentence_hash=sentence_hash(s), sentence=s, voice='OWNED',
                                premise_ids=list(n.premise_ids), card_id=None, manifestation_id=None,
                                content_hash=None, policy=b.policy.name))
        elif isinstance(n, EvidenceTable):
            flush()
            t = _table(n, b)
            if t:
                md.append(t)
                md.append('')
                for cid in n.card_ids:
                    r = b.resolve(cid)
                    row = f'TABLE_ROW::{cid}'
                    sidecar.append(dict(sentence_hash=sentence_hash(row), sentence=row, voice='TABLE',
                                        card_id=cid, manifestation_id=r.manifestation_id,
                                        content_hash=r.content_hash, span_start=r.span_start,
                                        span_end=r.span_end, span=r.span, work_id=r.work_id,
                                        expression_id=r.expression_id,
                                        names_expression_id=r.names_expression_id,
                                        policy=b.policy.name, attribution=r.attribution))
    flush()
    out = re.sub(r'\n{3,}', '\n\n', '\n'.join(md)).strip() + '\n'
    # "Writing in the {venue}" + venue "The Quarterly Journal of Economics" -> "in the The Quarterly".
    # `_venue_the()` already prevents it at the source; this is belt-and-braces ON THE RENDERED BYTES,
    # because the last time this correction existed it ran AFTER write_text() on a dead variable and the
    # disk kept the broken string while the metrics described the fixed one.
    out = re.sub(r'\bthe The\b', 'The', out)
    return out, sidecar
