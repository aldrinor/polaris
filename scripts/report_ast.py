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
import html
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'scripts'))

import provenance as P  # noqa: E402
from synthesis_contract import (Premise, Synthesis, validate,  # noqa: E402
                                SPELLED_QTY, FORECAST, classify_claim, prove,
                                level_span_support)


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
#:
#: The set is SPLIT by what the connective ASSERTS. A NEUTRAL joiner asserts only conjunction or
#: simultaneity — "X finds a, while/and Y finds b" — a relation both spans already license by merely
#: co-existing. A CONTRASTIVE joiner asserts that the second finding OPPOSES the first ("whereas",
#: "by contrast", "but", "yet", "though"); THAT relation is a claim, and it is a claim NEITHER
#: span-check tests — the lie sits BETWEEN the clauses, outside both. Sol admitted two POSITIVE,
#: unrelated findings joined by "by contrast"; neither source entails the contrast. Until a
#: proof-carrying planner verdict supplies the relation (an Owned synthesis, rung 4), the WRITER may
#: not assert it, so a model-chosen contrastive connective is REFUSED. `while` is retained as a
#: neutral simultaneity joiner: it asserts no direction of opposition, and the honest cross-source
#: synthesis — the most valuable sentence in the review — is written with it.
NEUTRAL_CONNECTIVES = ('while', 'and')
CONTRASTIVE_CONNECTIVES = ('whereas', 'by contrast', 'but', 'yet', 'though')
CONNECTIVES = NEUTRAL_CONNECTIVES + CONTRASTIVE_CONNECTIVES


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


#: Well-known venue names that a model may TYPE even when they are nowhere in this corpus — Sol's
#: "Science reports that ..." is the canonical case: the corpus never contained Science, so indexing the
#: corpus alone could never catch it. Used ONLY NEGATIVELY, across domains (Sol's paired clinical/legal
#: fixtures), to refuse a clause that names one of them. Multi-word entries are matched as a phrase.
_KNOWN_VENUES = frozenset({
    'science', 'nature', 'cell', 'lancet', 'the lancet', 'jama', 'nejm', 'bmj', 'pnas', 'plos one',
    'econometrica', 'american economic review', 'quarterly journal of economics', 'the economist',
    'new england journal of medicine', 'journal of the american medical association',
    'harvard law review', 'yale law journal', 'stanford law review', 'columbia law review',
    'supreme court reporter', 'federal reporter', 'us reports',
})

#: A reporting-attribution construction the WRITER may never type: "<Proper subject> <reporting verb>
#: that ...". Attribution is rendered from the graph ("Bloom and Draca show that ..."), so a clause that
#: says who found the finding is either naming a source or nesting a second attribution — both unlawful.
#: It catches ANY invented venue, not only the ones on the denylist above.
_REPORTING_VERBS = (
    r'report|reports|reported|find|finds|found|show|shows|showed|state|states|stated|argue|argues|'
    r'argued|note|notes|noted|observe|observes|observed|conclude|concludes|concluded|demonstrate|'
    r'demonstrates|demonstrated|establish|establishes|established|claim|claims|claimed|suggest|'
    r'suggests|suggested|write|writes|wrote|prove|proves|proved|hold|holds|held|rule|rules|ruled')
_ATTRIB_PATTERN = re.compile(
    r'\b([A-Z][A-Za-z.&\'\-]+)(?:\s+(?:and|&)\s+[A-Z][A-Za-z.&\'\-]+|\s+et\s+al\.?)?\s+'
    r'(?:' + _REPORTING_VERBS + r')\s+that\b')
#: ...but a common noun/pronoun subject ("Firms report that ...", "These studies show that ...") is NOT
#: a source name. Only a subject NOT on this list trips the attribution refusal.
_COMMON_SUBJECTS = frozenset({
    'the', 'this', 'these', 'those', 'they', 'we', 'it', 'a', 'an', 'one', 'some', 'many', 'most',
    'both', 'several', 'few', 'all', 'each', 'firms', 'workers', 'studies', 'study', 'researchers',
    'results', 'result', 'findings', 'finding', 'data', 'evidence', 'authors', 'author', 'scholars',
    'economists', 'papers', 'paper', 'estimates', 'models', 'analyses', 'experiments', 'trials',
    'surveys', 'reviews', 'here', 'there', 'such', 'our', 'their', 'its', 'his', 'her', 'who', 'which',
    'courts', 'court', 'patients', 'participants', 'respondents', 'clinicians', 'firms', 'markets'})


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
        # Every surname AND venue the bundle knows. Used ONLY NEGATIVELY — to refuse a source name in a
        # lane that is not allowed to have one. We never infer WHICH source from a surname again.
        #
        # THE OLD SET ADDED AUTHORS ONLY, AND ONLY AT len>=4. Sol walked through both holes: a journal
        # name ("Science reports that ...") was never in the set, so it shipped under an AER card; and a
        # sub-4-char surname ("Wu", "Ng") was invisible, as was a bare surname when the author was stored
        # as a full name ("Daron Acemoglu" is one token to `\bdaron acemoglu\b`, so "Acemoglu" alone slips
        # the exact match). We now index venues too, and index each NAME TOKEN, not only the whole string.
        self._source_words: set[str] = set()      # single tokens, matched at word boundaries
        self._source_phrases: set[str] = set()    # multi-word venue names, matched as a phrase
        for c in self.cards.values():
            for a in (c.get('authors') or []):
                self._index_person(a)
            self._index_venue(c.get('venue'))
        for w in graph.works.values():
            for a in (w.authors or []):
                self._index_person(a)
            self._index_venue(getattr(w, 'venue', None))

    def _index_person(self, name: str) -> None:
        """A person can be named by the whole string OR by a single token of it (the surname alone)."""
        n = re.sub(r'\s+', ' ', (name or '').strip().lower())
        if not n:
            return
        toks = re.findall(r"[a-z][a-z.'’\-]*[a-z]", n)  # drop bare initials ("j."), keep "wu", "ng"
        if len(n) >= 4:
            self._source_words.add(n)
        for t in toks:
            if len(t) >= 2:
                self._source_words.add(t)

    def _index_venue(self, venue: str) -> None:
        """A venue can be named whole ("the American Economic Review") or, when it is one distinctive
        word ("Science", "Nature", "Technovation"), by that word. We do NOT add single tokens of a
        multi-word venue — "economic" or "review" are common words and would refuse honest prose."""
        v = re.sub(r'\s+', ' ', (venue or '').strip().lower())
        if not v:
            return
        core = re.sub(r'^the\s+', '', v)
        toks = core.split(' ')
        if len(toks) == 1 and len(toks[0]) >= 4:
            self._source_words.add(toks[0])
        else:
            self._source_phrases.add(v)
            if core != v:
                self._source_phrases.add(core)

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

        # ---- 2. THE POLICY. What, if anything, may THIS SPAN name?
        #         Sol V9 §4: the question is asked about the BINDING, not about the manifestation. A
        #         manifestation-wide answer would hand THIS span whatever permission any OTHER span in
        #         the same document had earned — and the spans peer review rewrote sit in the very same
        #         document as the spans it left alone. Permission is per span or it is fiction.
        att = self.graph.resolve_attribution(binding, self.policy)
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

        It refuses on THREE grounds: (1) a corpus surname or single-word venue; (2) a venue name — a
        corpus multi-word venue, or a well-known journal/reporter the model typed from memory though the
        corpus never held it (Sol's "Science"); (3) a reporting-attribution construction ("<X> reports
        that ..."), which names a source for ANY invented venue, not only the ones we can enumerate.
        """
        raw = text or ''
        low = ' ' + re.sub(r'\s+', ' ', raw.lower()) + ' '
        for w in self._source_words:
            if re.search(rf'\b{re.escape(w)}\b', low):
                return w
        for p in self._source_phrases | _KNOWN_VENUES:
            if p and re.search(rf'\b{re.escape(p)}\b', low):
                return p
        m = _ATTRIB_PATTERN.search(raw)
        if m and m.group(1).lower() not in _COMMON_SUBJECTS:
            return m.group(1)
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
#
# SOL LADDER RUNG 2. The old check here was bag-of-words: a multi-digit-number-presence test plus 25%
# lexical overlap. It ADMITTED "the ratio FELL by 1.5 points" over a span that says the ratio ROSE by
# 1.5 points, because "rose"/"fell" is one token of overlap and the number 1.5 is present in both. That
# is not entailment. Word overlap is a NECESSARY support signal, never a SUFFICIENT one.
#
# The replacement is a real entailment check with three deterministic gates that can only fire on a
# genuine CONFLICT (so a true finding is never wrongly rejected), plus a fail-closed semantic judge for
# the residue deterministic rules cannot adjudicate:
#
#   (A) NUMBERS + UNITS. Every numeric quantity in the clause — INCLUDING single digits, INCLUDING a
#       number that happens to equal the publication year — must appear STANDING ALONE in the span with
#       the SAME UNIT. "1.5 points" != "1.5 percent". A fabricated "9 percent" that is absent dies here.
#   (B) DIRECTION / POLARITY. A clause that asserts the OPPOSITE direction of its span (rose vs fell,
#       increased vs decreased, more vs less) is REJECTED. This is burn #1, the worst one.
#   (C) CONTENT FLOOR. The clause's content words must actually be in the span (necessary support).
#   (D) SEMANTIC RESIDUE. Modality/hedging ("may reduce" vs "reduces"), negation ("did not reduce" vs
#       "reduces"), and comparator/scope claims that the deterministic layer flags but cannot resolve
#       route to a CONSTRAINED entailment judge. MATCH ships; NO_MATCH and UNCERTAIN FAIL CLOSED. A
#       doctrinal clause with no number is not auto-passed and not auto-failed: it is supported by the
#       content floor when it is a faithful restatement, and routed to the judge when it is not.

_STOP = {'writing', 'article', 'journal', 'review', 'that', 'show', 'shows', 'find', 'finds', 'found',
         'report', 'reports', 'reported', 'demonstrate', 'demonstrates', 'evidence', 'study', 'their',
         'this', 'these', 'those', 'with', 'from', 'have', 'been', 'were', 'which', 'while', 'also',
         'than', 'when', 'more', 'most', 'such', 'they', 'them', 'about', 'paper', 'papers', 'result',
         'results', 'finding', 'findings', 'authors', 'author'}

_NUM = re.compile(r'\d+(?:\.\d+)?')

#: A number followed (optionally) by its unit. Longest units first so "percentage points" is not read as
#: bare "points", and "%" / "$" attach. `(?<![\d.])` keeps "0.2" from being read out of "10.25".
_NUM_UNIT = re.compile(
    r'(?<![\d.])(\d+(?:\.\d+)?)\s*'
    r'(percentage\s+points?|percentage\s+point|basis\s+points?|percent|points?|bps|'
    r'pp|%|\$|fold|times|million|billion|trillion|thousand)?',
    re.I)

#: Spelled cardinals we resolve to digits so "five percent" is checked against "5 percent" (and vice
#: versa). Kept small and only counted when a unit follows, so "one of the" is never read as a quantity.
_SPELLED = {'zero': '0', 'one': '1', 'two': '2', 'three': '3', 'four': '4', 'five': '5', 'six': '6',
            'seven': '7', 'eight': '8', 'nine': '9', 'ten': '10', 'eleven': '11', 'twelve': '12',
            'twenty': '20', 'thirty': '30', 'forty': '40', 'fifty': '50', 'hundred': '100'}
_SPELLED_UNIT = re.compile(
    r'\b(' + '|'.join(_SPELLED) + r')\s+'
    r'(percentage\s+points?|basis\s+points?|percent|points?|bps|pp|fold|times|'
    r'million|billion|trillion|thousand)\b', re.I)

#: Direction / polarity lexicons. A conflict fires ONLY when the clause is exclusively one direction and
#: the span is exclusively the opposite — so a true finding, which shares its span's direction, is safe.
_UP = {'rose', 'rise', 'rises', 'rising', 'risen', 'increase', 'increased', 'increases', 'increasing',
       'grew', 'grow', 'grows', 'growing', 'grown', 'growth', 'gain', 'gained', 'gains', 'gaining',
       'higher', 'greater', 'up', 'upward', 'upwards', 'expand', 'expanded', 'expands', 'expanding',
       'expansion', 'climb', 'climbed', 'surge', 'surged', 'doubled', 'tripled', 'quadrupled',
       'raise', 'raised', 'raises', 'boost', 'boosted', 'positive'}
_DOWN = {'fell', 'fall', 'falls', 'falling', 'fallen', 'decline', 'declined', 'declines', 'declining',
         'decrease', 'decreased', 'decreases', 'decreasing', 'drop', 'dropped', 'drops', 'dropping',
         'lower', 'lowered', 'fewer', 'down', 'downward', 'downwards', 'shrink', 'shrank', 'shrunk',
         'shrinks', 'shrinking', 'contract', 'contracted', 'contracts', 'contraction', 'reduce',
         'reduced', 'reduces', 'reducing', 'reduction', 'diminish', 'diminished', 'negative', 'halve',
         'halved', 'loss', 'lost'}

_HEDGE = {'may', 'might', 'could', 'suggest', 'suggests', 'suggesting', 'appear', 'appears', 'appeared',
          'likely', 'possibly', 'potentially', 'seem', 'seems', 'seemed', 'tend', 'tends', 'perhaps',
          'presumably', 'arguably'}
_NEG = re.compile(r"\b(not|no|never|without|cannot|can't|didn't|doesn't|don't|isn't|aren't|wasn't|"
                  r"weren't|fails?|failed|neither|nor|un(?:able|likely))\b", re.I)
_COMPARATOR = re.compile(r'\b(more than|less than|greater than|fewer than|compared (?:to|with)|'
                         r'relative to|versus|as much as|twice as|half as|outperform\w*|'
                         r'exceed\w*|larger than|smaller than)\b', re.I)


def numbers_in(s: str) -> list[str]:
    return _NUM.findall(s or '')


def number_stands_alone(num: str, src: str) -> bool:
    """`"0.2" in "10.25"` IS TRUE. A substring test leaks a fabricated effect size through any source
    that happens to contain a longer number with the same digits in it — and we deliberately flood this
    prose with figures, which loads that hole with live rounds."""
    return bool(re.search(rf'(?<![\d.]){re.escape(num)}(?![\d])', src))


def _norm_unit(u: str) -> str:
    """Fold surface unit forms to a canonical tag. 'points' != 'percent'; 'percentage points' == 'pp'."""
    if not u:
        return ''
    u = re.sub(r'\s+', ' ', u.strip().lower())
    if u in ('%', 'percent', 'pct', 'percentage'):
        return 'percent'
    if u.startswith('percentage point'):
        return 'pp'
    if u == 'pp':
        return 'pp'
    if u.startswith('basis point') or u == 'bps':
        return 'bps'
    if u.startswith('point'):
        return 'points'
    if u in ('fold', 'times'):
        return 'times'
    if u == '$':
        return 'dollars'
    if u in ('million', 'billion', 'trillion', 'thousand'):
        return u
    return u


def quantities_in(s: str) -> list[tuple[str, str]]:
    """Every (number, canonical-unit) pair in the text. Digit forms and spelled forms both, so a clause
    that swaps the unit — or invents a figure the span never states — cannot slip through."""
    out: list[tuple[str, str]] = []
    for m in _NUM_UNIT.finditer(s or ''):
        out.append((m.group(1), _norm_unit(m.group(2) or '')))
    for m in _SPELLED_UNIT.finditer(s or ''):
        out.append((_SPELLED[m.group(1).lower()], _norm_unit(m.group(2))))
    return out


def _quantity_supported(num: str, unit: str, src: str, span_q: list[tuple[str, str]]) -> bool:
    """The clause's (num, unit) is supported iff the SAME number stands alone in the span AND, when the
    clause carries a unit, some standing-alone occurrence in the span carries the SAME unit."""
    if not number_stands_alone(num, src):
        return False
    if not unit:
        return True
    return any(n == num and u == unit for n, u in span_q)


# ---- THE CONSTRAINED SEMANTIC JUDGE — CONSULTED ON EVERY CLAUSE, FAIL CLOSED -----------------------
#
# SOL LADDER RUNG 2, THE HONEST FIX. The prior rung asked the judge ONLY when a hand-built residue
# detector (hedge/negation/comparator word lists) fired. A fresh adversary walked straight past it with
# SYNONYMS the lists never named — 'rose' rendered as 'plunged' (Sol's Burn #1), 'doubled' when the span
# says '1.5 points', 'worldwide' when the span says 'in the US', 'causes' when the span says 'associated
# with'. None of those trip a residue word, so the judge WAS NEVER CALLED and the lie shipped.
#
# THE LESSON, MECHANISED: a gate assembled from a list of words only catches the words its author
# imagined. So the judge is no longer conditional on anything. EVERY attributed clause and EVERY
# evidence-table row that survives the deterministic pre-filter is put to the judge, WHOLE CLAUSE vs
# WHOLE SPAN. Only ENTAILED admits. NOT_ENTAILED and UNCERTAIN both REJECT. If the model cannot be
# reached, that is UNCERTAIN and it REJECTS — a validator that admits when it cannot check is the whole
# problem.
#
# The deterministic layer (numbers+units, a strict direction opposition, a content floor) is REJECT-ONLY
# defence-in-depth: it may kill an obvious fabrication cheaply and offline, but it may NEVER conclude
# ADMIT. Passing it means "not yet rejected", never "entailed" — the only thing that says "entailed" is
# the judge.
#
# A judge is a callable(clause_text, span_text) -> (verdict, excerpt) where verdict is ENTAILED |
# NOT_ENTAILED | UNCERTAIN (MATCH/NO_MATCH accepted as aliases so an older stub still wires). Tests
# inject a deterministic stub via set_entailment_judge(); production uses the repo llm() model.

_ENTAILED = 'ENTAILED'
_NOT_ENTAILED = 'NOT_ENTAILED'
_UNCERTAIN = 'UNCERTAIN'

_ENTAILMENT_JUDGE = None  # type: ignore[var-annotated]
#: Judge verdicts memoised by (span_hash, normalised clause). A re-run is then stable and cheap, and the
#: deterministic pre-filter means the judge is only ever asked the semantic residue the cheap rules leave.
_JUDGE_CACHE: dict[tuple[str, str], tuple[str, str]] = {}


def set_entailment_judge(fn) -> None:
    """Wire a real LLM entailment judge. Tests inject a deterministic stub; production wires the model.
    Clearing the cache here keeps a swapped stub from reading a previous judge's verdict for the same
    (span, clause)."""
    global _ENTAILMENT_JUDGE
    _ENTAILMENT_JUDGE = fn
    _JUDGE_CACHE.clear()


def _canon_verdict(v) -> str:
    """Fold a judge's surface verdict to the canonical three. Anything unrecognised is UNCERTAIN, so an
    unparseable or novel reply FAILS CLOSED rather than being read as an admit."""
    s = str(v or '').strip().upper()
    if s in ('ENTAILED', 'MATCH', 'YES', 'TRUE', 'ENTAILS'):
        return _ENTAILED
    if s in ('NOT_ENTAILED', 'NOT ENTAILED', 'NO_MATCH', 'NO', 'FALSE', 'CONTRADICTED', 'CONTRADICTS'):
        return _NOT_ENTAILED
    return _UNCERTAIN


def _span_hash(span: str) -> str:
    return hashlib.sha256(re.sub(r'\s+', ' ', (span or '').strip()).encode('utf-8')).hexdigest()


def _llm_entailment_judge(clause: str, span: str) -> tuple[str, str]:
    """The production judge: a constrained call to the repo model via cellcog_composer.llm().

    It is ALWAYS attempted — there is no opt-in flag, because the judge is now the gate, not an optional
    second opinion. On ANY failure (import error, transport error, timeout, unparseable reply) it returns
    UNCERTAIN, and UNCERTAIN REJECTS. It NEVER returns ENTAILED without an affirmative model verdict."""
    prompt = (
        'You are a STRICT textual-entailment judge for a scientific literature review. You are given a '
        'verbatim SPAN from a source document and a CLAIM a reviewer wrote. Decide whether the SPAN, '
        'read literally and alone, ENTAILS the CLAIM — i.e. everything the CLAIM asserts is supported by '
        'the SPAN, with:\n'
        '  - the SAME DIRECTION/POLARITY (rose vs fell/plunged/slid/weakened are NOT the same);\n'
        '  - the SAME MAGNITUDE (a span that says "1.5 points" does NOT entail "doubled"/"tripled");\n'
        '  - the SAME NUMBERS WITH UNITS;\n'
        '  - the SAME MODALITY ("is associated with" does NOT entail "causes"; "may reduce" is not '
        '"reduces");\n'
        '  - the SAME SCOPE/POPULATION/COMPARATOR ("in the United States" does NOT entail "worldwide"/'
        '"across every advanced economy").\n'
        'If the CLAIM asserts ANYTHING the SPAN does not support, answer NOT_ENTAILED. If you genuinely '
        'cannot tell from the SPAN alone, answer UNCERTAIN. Do not be generous.\n'
        'Reply with ONLY a JSON object and nothing else: '
        '{"verdict":"ENTAILED"|"NOT_ENTAILED"|"UNCERTAIN","excerpt":"<the SPAN words that decided it>"}.\n\n'
        f'SPAN:\n{span}\n\nCLAIM:\n{clause}\n')
    try:
        import json as _json
        from cellcog_composer import llm  # lazy: composer owns the model client (avoids an import cycle)
        raw = llm(prompt, max_tokens=300)
        m = re.search(r'\{.*\}', raw or '', re.S)
        obj = _json.loads(m.group(0)) if m else {}
        return _canon_verdict(obj.get('verdict')), str(obj.get('excerpt', ''))[:160]
    except Exception as e:  # noqa: BLE001  — any failure FAILS CLOSED
        return _UNCERTAIN, f'judge unavailable (fail closed): {type(e).__name__}'


def _semantic_judge(clause: str, span: str) -> tuple[str, str]:
    """The judge, memoised and normalised. Returns (canonical verdict, deciding excerpt). A stub raising,
    or any non-verdict, is folded to UNCERTAIN — the fail-closed direction."""
    key = (_span_hash(span), re.sub(r'\s+', ' ', (clause or '').strip()))
    if key in _JUDGE_CACHE:
        return _JUDGE_CACHE[key]
    fn = _ENTAILMENT_JUDGE or _llm_entailment_judge
    try:
        v, why = fn(clause, span)
    except Exception as e:  # noqa: BLE001
        v, why = _UNCERTAIN, f'judge raised (fail closed): {type(e).__name__}'
    res = (_canon_verdict(v), str(why or '')[:160])
    _JUDGE_CACHE[key] = res
    return res


def _modality_residue(ctext: str, src: str) -> str:
    """LEGACY, kept only for backward import compatibility (an old probe imports it). It is NO LONGER a
    gate: the judge is now consulted UNCONDITIONALLY, precisely because this residue detector — a list of
    hedge/negation/comparator words — was blind to every synonym its author did not enumerate. Returns a
    human-readable note about the residue it happens to notice, and nothing depends on the value."""
    cw = set(re.findall(r"[a-z']+", ctext))
    sw = set(re.findall(r"[a-z']+", src))
    if (sw & _HEDGE) and not (cw & _HEDGE):
        return 'span hedges; clause asserts categorically'
    if bool(_NEG.search(ctext)) != bool(_NEG.search(src)):
        return 'negation polarity differs'
    if _COMPARATOR.search(ctext) and not _COMPARATOR.search(src):
        return 'clause asserts a comparison the span does not state'
    return ''


def entailed_by_span(text: str, span: str, work: P.Work | None = None,
                     min_overlap: float = 0.25) -> tuple[bool, str]:
    """Is THIS text ENTAILED by THIS verbatim span? The span is the only evidence there is.

    `claim` — the model's restatement — is not a parameter of this function and never will be. The old
    gate read `src = f'{span} {claim}'`, and since the writer was handed only the claim, the chain was:
    the model writes the claim -> the writer writes from the claim -> the gate checks the writing
    against the claim. THE GATE VALIDATED THE MODEL AGAINST ITSELF.

    Two layers, in order:

      1. A DETERMINISTIC PRE-FILTER that may only REJECT (numbers+units, a strict direction opposition, a
         content floor). It is cheap and certain and it kills the obvious fabrication offline. It NEVER
         admits — surviving it means "not yet rejected".
      2. THE JUDGE, consulted on the WHOLE clause vs the WHOLE span for EVERY clause that survives (1),
         not conditioned on any word list. ONLY 'ENTAILED' admits; 'NOT_ENTAILED' and 'UNCERTAIN' — and a
         judge that cannot be reached — REJECT. This is the line that catches the synonym sign-flip
         ('plunged'), the magnitude fabrication ('doubled'), the scope swap ('worldwide') and the
         modality flip ('causes'), none of which any lexicon here names.
    """
    src = (span or '').lower()
    if not src:
        return False, 'NO_SPAN'
    ctext = (text or '').lower()

    # ============ DETERMINISTIC PRE-FILTER — REJECT-ONLY. It may kill; it may never admit. ============
    # (A) NUMBERS + UNITS. Every quantity in the clause must stand alone in the span with the SAME unit.
    #     No single-digit exemption. No year exemption. "1.5 points" does not support "1.5 percent".
    span_q = quantities_in(src)
    for num, unit in quantities_in(ctext):
        if not _quantity_supported(num, unit, src, span_q):
            return False, f'NUMBER_OR_UNIT_NOT_IN_SPAN:{num}{(" " + unit) if unit else ""}'
    # A bare integer with no recognised unit (e.g. a fabricated "2021 regions") is still a quantity.
    for num in numbers_in(ctext):
        if not number_stands_alone(num, src):
            return False, f'NUMBER_NOT_IN_SPAN:{num}'

    # (B) DIRECTION / POLARITY. Reject only a strict opposition — clause one way, span the other way.
    #     This catches the IN-lexicon flip ("fell" vs "rose") without a model call; the OUT-of-lexicon
    #     flip ("plunged", "slid", "weakened") is left for the judge, which is the whole point of (2).
    cw = set(re.findall(r'[a-z]+', ctext))
    sw = set(re.findall(r'[a-z]+', src))
    c_up, c_down = bool(cw & _UP), bool(cw & _DOWN)
    s_up, s_down = bool(sw & _UP), bool(sw & _DOWN)
    if (c_down and not c_up and s_up and not s_down) or (c_up and not c_down and s_down and not s_up):
        return False, 'DIRECTION_CONTRADICTS_SPAN'

    # (C) CONTENT FLOOR. A clause whose content words are largely absent from the span is unsupported.
    words = {w for w in re.findall(r'[a-z]{4,}', ctext)} - _STOP
    if work:
        words -= {w for w in re.findall(r'[a-z]{4,}', (work.venue or '').lower())}
        words -= {w for w in re.findall(r'[a-z]{4,}', ' '.join(work.authors or []).lower())}
    src_words = {w for w in re.findall(r'[a-z]{4,}', src)}
    if words and len(words & src_words) / len(words) < min_overlap:
        return False, 'CONTENT_NOT_IN_SPAN'

    # ============ THE JUDGE — WHOLE CLAUSE vs WHOLE SPAN, EVERY TIME. ONLY 'ENTAILED' ADMITS. ==========
    verdict, why = _semantic_judge(text, span)
    if verdict != _ENTAILED:
        return False, f'JUDGE_{verdict}' + (f' :: {why}' if why else '')
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


def _claim_text(r: Resolution) -> str:
    """The ONE rendering of a table row's finding — used by BOTH the validator and the renderer, so the
    string that is checked is byte-for-byte the string that ships. Un-escaped, whitespace-collapsed, no
    trailing period; never truncated, because a truncation could drop the very figure that was verified."""
    return re.sub(r'\s+', ' ', html.unescape(r.card.get('claim') or '')).strip().rstrip('.')


# =================================================================================================
# 4a. THE OWNED-FRAME AND HEADING PARTICULAR GATES  (SOL_BURN_V10 §2 and §3)
#
# A premise-free OWNED node and a Heading were the two lanes that could assert ANYTHING: the owned
# frame was checked only for digits + source names, and a heading only for non-emptiness. Both are the
# reviewer's own voice, licensed by no span, so BOTH may carry no new PARTICULAR — no spelled quantity,
# no magnitude word, no forecast, no novel named entity. The released abstract used the owned-frame
# bypass; "## Acemoglu proves that 47 percent of jobs will disappear." used the heading bypass.
# =================================================================================================

#: A magnitude/severity absolute stands in for a number the reviewer cannot vouch for: "fatal" is a
#: 100%-mortality claim, exactly as "doubled" is a x2 claim. SPELLED_QTY (imported from the synthesis
#: contract) already catches doubl*/tripl*/halv*/percent*/majority/most-of; these are the unbounded
#: absolutes it does not. Kept tiny and word-boundaried so "fatally flawed argument" is the only kind of
#: false positive, and that phrase has no place in a section frame either.
_MAGNITUDE_ABS = re.compile(r'\b(fatal|fatally|lethal|lethally|deadly|mortal|mortally)\b', re.I)

#: A run-in bold label — "**Objective.** ...", "**Evidence base.** ..." — is a mini-heading, not prose.
#: Stripped before the entity scan so the label's capitals are not read as named entities.
_FRAME_LABEL = re.compile(r'^\s*\*\*[^*]+\*\*\s*')

#: Capitals that are orthography or discourse, never a named entity, even mid-sentence.
_DISCOURSE_CAPS = {'the', 'this', 'these', 'those', 'a', 'an', 'and', 'or', 'but', 'of', 'in', 'on',
                   'at', 'by', 'for', 'to', 'with', 'as', 'ai'}


def _novel_multiword_entity(text: str) -> str:
    """A premise-free frame is licensed by nothing, so it may name NO entity. A run of TWO OR MORE
    consecutive Title-Case tokens that are not sentence-initial and not pure discourse is a named entity
    the review has not earned — "Fourth Industrial Revolution", "Goldman Sachs". A lone proper adjective
    ("English-language") is NOT flagged: a single capital mid-sentence is too often orthography, and the
    synthesis lane (which HAS premises) is where single new entities are caught against premise spans."""
    body = _FRAME_LABEL.sub('', text or '')
    toks = re.findall(r'\S+', body)
    run: list[str] = []
    for idx, tok in enumerate(toks):
        core = re.sub(r"[^A-Za-z'\-]", '', tok)
        is_entity_cap = bool(re.match(r'[A-Z][a-z]', core)) and idx != 0 \
            and core.lower() not in _DISCOURSE_CAPS
        if is_entity_cap:
            run.append(core)
            continue
        if len(run) >= 2:
            return ' '.join(run)
        run = []
    return ' '.join(run) if len(run) >= 2 else ''


def _owned_frame_particular(text: str) -> str:
    """The premise-free OWNED lane. Digits and source names are already refused by the shared checks;
    THIS refuses the particulars they missed: a spelled quantity ("doubled", "a third", "the vast
    majority"), a magnitude word ("fatal"), or a novel named entity. Returns a refusal, or ''.

    This is the gate the released abstract bypassed: an Owned() with no premises used to assert any
    factual claim it liked as long as it typed no digit. Now it must be a genuine FRAME."""
    m = SPELLED_QTY.search(text or '')
    if m:
        return f'OWNED_CARRIES_A_SPELLED_QUANTITY:{m.group(0)!r}'
    m = _MAGNITUDE_ABS.search(text or '')
    if m:
        return f'OWNED_CARRIES_A_MAGNITUDE_WORD:{m.group(0)!r}'
    ent = _novel_multiword_entity(text or '')
    if ent:
        return f'OWNED_CARRIES_A_NOVEL_NAMED_ENTITY:{ent!r}'
    return ''


#: The research contract used to derive a premise's facets FROM ITS SPAN. Cached: building it lazily
#: imports the composer's outline, and we do not want that on every premise.
_FACET_CONTRACT = None


def _facet_contract():
    global _FACET_CONTRACT
    if _FACET_CONTRACT is None:
        import argument_planner as _AP          # lazy: avoids any import-time coupling to the planner
        _FACET_CONTRACT = _AP.default_contract()
    return _FACET_CONTRACT


def _premise_with_span_facets(pid: str, r: Resolution) -> Premise:
    """A premise carrying facets DERIVED FROM ITS OWN VERBATIM SPAN, not trusted off the card.

    The unit of analysis is the facet a reconciliation turns on, and the card's DECLARED `level` is a
    string an extractor wrote — a card can say `firm` over a span that only ever says `regions`. So the
    declared level is kept ONLY if the span supports it (`unit_span`); outcome and direction are read
    straight from the span through the planner's joint derivation. A proof may then turn on facets that
    are bound to bytes, which is the whole of RUNG 4 obligation 2.
    """
    import argument_planner as _AP              # lazy
    c = r.card
    span = r.span or ''
    level = (c.get('level', '') or c.get('unit_of_analysis', '')).strip()
    horizon = c.get('horizon', '')
    method = c.get('method', '') or c.get('design', '')
    card_for_facets = {
        'id': pid, 'doi': c.get('doi', ''), 'span': span, 'claim': '', 'level': level,
        'method': method, 'horizon': horizon, 'mechanisms': c.get('mechanisms') or [],
        'authors': c.get('authors') or [], 'year': c.get('year'), 'venue': c.get('venue', ''),
    }
    try:
        cf = _AP.derive_facets(card_for_facets, _facet_contract())
        outcome = cf.f('outcome')
        direction = cf.f('direction')
        outcome_v, outcome_span = outcome.value, outcome.evidence
        direction_v, direction_span = direction.value, direction.evidence
    except Exception:                            # fail closed: no span facets => an unprovable premise
        outcome_v = outcome_span = direction_v = direction_span = ''
    return Premise(
        id=pid, text=span, source=r.attribution,
        level=level, horizon=horizon, method=method, mechanisms=c.get('mechanisms') or [],
        outcome=outcome_v, direction=direction_v,
        unit_span=level_span_support(span, level),
        outcome_span=outcome_span, direction_span=direction_span,
        horizon_span=horizon)


def validate_heading(i: int, n: Heading, b: CardBundle) -> list[Failure]:
    """A heading LABELS a section; it is not a third voice that may assert a finding. It carries no
    factual assertion: no number (digit, spelled quantity, or magnitude word), no named source, and no
    forecast. "## Acemoglu proves that 47 percent of jobs will disappear." is refused on THREE counts
    (the digit, the source name, and the forecast); "Employment effects" and a Title-Case section title
    carry none of them and pass. The publisher still skips heading LINES in its prose-receipt sweep, but
    that is now safe: a heading that reaches the page has passed HERE, so it carries no assertion to
    fabricate. The "third voice that can say anything" is closed by refusing the assertion, not by
    receipting it."""
    t = (n.text or '').strip()
    if not t:
        return [Failure(i, 'Heading', 'EMPTY')]
    if re.search(r'\d', t):
        return [Failure(i, 'Heading', 'HEADING_CARRIES_A_NUMBER', t[:70])]
    m = SPELLED_QTY.search(t) or _MAGNITUDE_ABS.search(t)
    if m:
        return [Failure(i, 'Heading', 'HEADING_CARRIES_A_QUANTITY', m.group(0))]
    named = b.names_a_source(t)
    if named:
        return [Failure(i, 'Heading', 'HEADING_NAMES_A_SOURCE',
                        f'{named!r} — a heading that names a source asserts that source found something; '
                        f'that is an attribution, and an attribution must be entailed by a span.')]
    m = FORECAST.search(t)
    if m:
        return [Failure(i, 'Heading', 'HEADING_FORECASTS', m.group(0))]
    return []


def validate_node(i: int, n: Node, b: CardBundle) -> list[Failure]:
    if isinstance(n, ParagraphBreak):
        return []
    if isinstance(n, Heading):
        return validate_heading(i, n, b)

    # ---------------------------------------------------------------- ATTRIBUTED
    if isinstance(n, Attributed):
        f: list[Failure] = []
        if not n.clauses:
            return [Failure(i, 'Attributed', 'NO_CLAUSES')]
        if n.connective and n.connective not in CONNECTIVES:
            f.append(Failure(i, 'Attributed', 'CONNECTIVE_NOT_IN_CLOSED_SET', n.connective))
        # A CONTRASTIVE connective, on a MULTI-CLAUSE sentence, asserts that the findings OPPOSE — a
        # relation neither clause's span-check tests. The writer may not assert it. (A single-clause
        # node has no join, so its connective is inert; it is only refused when it actually joins.)
        if len(n.clauses) > 1 and n.connective in CONTRASTIVE_CONNECTIVES:
            f.append(Failure(i, 'Attributed', 'CONTRASTIVE_CONNECTIVE_ASSERTS_UNPROVEN_RELATION',
                             f'{n.connective!r} claims the findings oppose; no span-check proves that '
                             f'relation. Join with a neutral connective, or let a proof-carrying Owned '
                             f'synthesis assert the contrast.'))
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
        # 3. If it is licensed by premises, it must be a PROOF-CARRYING VERDICT over them (RUNG 4).
        #    The old gate tried EVERY operation and admitted if ANY passed — so it admitted BOTH "these
        #    point in opposite directions" AND "these are not contradictory" for the same premises, a
        #    false reconciliation assembled from true particulars. Now the sentence's OWN claim selects
        #    the operation, and only that operation's proof — checked against SPAN-BOUND facets — admits.
        if n.premise_ids:
            prem: dict[str, Premise] = {}
            for pid in n.premise_ids:
                r = b.resolve(pid)
                if not r.ok:
                    return [Failure(i, 'Owned', f'PREMISE_UNRESOLVED: {r.refusal}', pid)]
                prem[pid] = _premise_with_span_facets(pid, r)
            if len(prem) < 2:
                return [Failure(i, 'Owned', 'SYNTHESIS_NEEDS_2_PREMISES', str(n.premise_ids))]
            # (a) the sentence's claim names the operation that must license it; fail closed if unrecognised
            claim_class, op = classify_claim(n.text)
            if not op:
                return [Failure(i, 'Owned', 'OWNED_VERDICT_UNCLASSIFIABLE',
                                'the sentence makes no recognised verdict, so no proof can be checked '
                                f'against it — {n.text[:60]!r}')]
            # (b) generic safety: no new particular, anchored, no imported mechanism (unchanged bar)
            ok_safe, why_safe = validate(Synthesis(op, list(prem), n.text), prem)
            if not ok_safe:
                return [Failure(i, 'Owned', f'SYNTHESIS_REFUSED:{why_safe}', n.text[:70])]
            # (c) THE PROOF. The operation that licenses THIS claim must have its preconditions satisfied.
            proof, why = prove(op, list(prem.values()), n.text)
            if proof is None:
                return [Failure(i, 'Owned', f'OWNED_VERDICT_UNPROVEN:{claim_class}', why)]
            return []
        # 4. A FRAME sentence: licensed by nothing, so it may assert NO PARTICULAR. Digits and source
        #    names are refused above; a spelled quantity, a magnitude word ("fatal", "doubled"), or a
        #    novel named entity ("...the Fourth Industrial Revolution...") is refused HERE. This closes
        #    the premise-free OWNED bypass — the lane the released abstract used (SOL_BURN_V10 §2).
        why2 = _owned_frame_particular(n.text)
        if why2:
            return [Failure(i, 'Owned', why2, n.text[:70])]
        return []

    # ---------------------------------------------------------------- TABLE
    if isinstance(n, EvidenceTable):
        f = []
        for cid in n.card_ids:
            r = b.resolve(cid)
            if not r.ok:
                f.append(Failure(i, 'EvidenceTable', r.refusal, cid))
                continue
            # A TABLE CELL IS AN ATTRIBUTED CLAUSE IN A BOX. It is held to the SAME law: the claim the
            # judge reads must be ENTAILED by this row's own span (number, unit, polarity), and it may
            # not itself NAME A SOURCE. The exact string validated here is the exact string _table_cells
            # renders — `_claim_text(r)` — so there is no gap between what is checked and what ships.
            claim = _claim_text(r)
            work = b.graph.works.get(r.work_id)
            ok, why = entailed_by_span(claim, r.span, work, min_overlap=0.34)
            if not ok:
                f.append(Failure(i, 'EvidenceTable', f'ROW_{why}', f'{cid} :: {claim[:50]}'))
                continue
            named = b.names_a_source(claim)
            if named:
                f.append(Failure(i, 'EvidenceTable', 'ROW_NAMES_A_SOURCE',
                                 f'{cid} :: {named!r} — attribution is rendered from the graph, not '
                                 f'typed into the cell'))
            # `level` and `method` are NOT printed (see `_table_cells`): they are model/extractor facets
            # with NO span binding — Sol shipped level="children with cancer", method="randomized trial"
            # under an employment span. An unverifiable facet does not reach the page, so it cannot lie.
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


def _table_cells(n: EvidenceTable, b: CardBundle, limit: int = 14) -> list[dict]:
    """The rows the renderer AND the sidecar both draw from — computed ONCE, so the page and its receipts
    can never disagree. Study/journal/year are RENDERED FROM THE GRAPH (never off the card); the finding
    is `_claim_text(r)`, the exact span-entailed string the validator already cleared. There is no Level
    or Method cell: those facets have no span binding and so may not reach the page.
    """
    out = []
    for cid in n.card_ids[:limit]:
        r = b.resolve(cid)
        if not r.ok:
            continue
        expr = b.graph.expressions[r.names_expression_id]
        work = b.graph.works[expr.work_id]
        out.append(dict(cid=cid, res=r, who=_who(work), year=work.year,
                        venue=(work.venue or ''), claim=_claim_text(r)))
    return out


def _table_md(n: EvidenceTable, cells: list[dict]) -> str:
    if len(cells) < 3:
        return ''
    cell = lambda x: html.unescape(str(x if (x is not None and str(x) != '') else '--')).replace('|', '/')
    rows = [f"| {cell(c['who'])}, {c['year']} | {cell(c['venue'])[:34]} | {cell(c['claim'])} |"
            for c in cells]
    return '\n'.join(['', n.caption, '',
                      '| Study | Journal | Quantitative finding |',
                      '|---|---|---|'] + rows)


def _table(n: EvidenceTable, b: CardBundle, limit: int = 14) -> str:
    return _table_md(n, _table_cells(n, b, limit))


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
            cells = _table_cells(n, b)
            t = _table_md(n, cells)
            if t:
                md.append(t)
                md.append('')
                # THE RECEIPT IS THE CELL THE JUDGE READS — the finding string that is actually printed,
                # keyed by its own hash — NOT an opaque `TABLE_ROW::<id>` that resolves to nothing. The
                # publisher can now re-verify a table row against its span exactly as it does a sentence.
                for c in cells:
                    r = c['res']
                    claim = c['claim']
                    sidecar.append(dict(sentence_hash=sentence_hash(claim), sentence=claim, voice='TABLE',
                                        card_id=c['cid'], manifestation_id=r.manifestation_id,
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
