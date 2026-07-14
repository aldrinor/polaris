#!/usr/bin/env python3
"""THE COMPOSER — it writes a DRAFT. IT CANNOT PUBLISH. That is now a property of the filesystem.

WHAT WAS WRONG WITH THIS FILE, AND WHY THE FIX IS NOT ANOTHER CHECK
-------------------------------------------------------------------
1. TWO DISCONNECTED CARD LANES. The miner wrote `evidence_cards_v2.json`; THIS FILE READ
   `evidence_cards.json` — a different file, whose cards carry no manifestation, no content hash and no
   span offsets, and four of whose cards were mined out of Frey & Osborne's ORA LANDING PAGE (548 words
   of cookie banner and metadata) and printed as findings of Technological Forecasting and Social
   Change. The composer could not have detected that: the lane it read had nothing in it to detect with.
   THE SEAM IS GONE. There is one bundle, it is passed EXPLICITLY, and it is pinned by hash.

2. IT INFERRED SOURCE IDENTITY FROM SURNAMES. `_cited_cards()` decided which paper a sentence was about
   by regex-matching author surnames in the model's prose, then gated the sentence against whatever card
   that hit. So "Bresnahan reports task displacement" — a real mechanism, a real paper, a FABRICATED
   BINDING — was gated against a card the model had effectively chosen for itself.
   THE MODEL NO LONGER NAMES SOURCES AT ALL. It emits a bare finding plus THE CARD ID, and
   `report_ast.render_attribution()` attaches the citation, from the expression the SOURCE POLICY chose.
   The model cannot write "Writing in the Journal of Political Economy" over working-paper bytes,
   because it never types a journal's name.

3. IT WROTE THE JUDGED ARTIFACT ITSELF (`(OUT_DIR / 'report.md').write_text(report)`, old line 775), and
   the hand-written abstract above it bypassed every gate in the file — 4 sentences of unsourced claims,
   assembled with an f-string, that no lane ever looked at.
   THERE IS NO WRITER IN THIS FILE. `outputs/release/` is mode 0555 and this process cannot create a
   file in it. The abstract is now AST nodes like everything else.

4. IT LISTED FINDINGS INSTEAD OF ADJUDICATING THEM. 28 subsections were generated INDEPENDENTLY in a
   thread pool; nobody ever decided what was compared with what, so "Critical Synthesis" (w=0.0800, the
   joint-heaviest criterion) scored 6.36 on 210 words of 8,012. `argument_planner.py` — built, tested,
   and until now imported by nobody — builds COMPARISON BUNDLES from the bound cards BEFORE any prose
   and hands each subsection a PLAN. This file now WIRES it: the writer FILLS the plan (it states the
   two sides of each comparison as attributed clauses), and the planner's DETERMINISTIC owned verdict
   ("the evidence establishes X at the firm level but not economy-wide") is appended and RE-GATED
   through the same `validate_report` as every model sentence. The composer trusts only the defensive
   SAME_OUTCOME_DIFFERENT_UNIT verdict, and only when both cards' outcome is an unambiguous quantity
   (see `_OUTCOME_DECOY`): a false conflict assembled from true particulars is the one lie no gate can
   catch, and it burns the artifact.

WHAT THE COMPOSER MAY DO: propose nodes. What it may not do: emit characters into the release.
"""
from __future__ import annotations

import argparse
import asyncio
import concurrent.futures as futures
import hashlib
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'scripts'))

import provenance as P                                                          # noqa: E402
import publisher                                                                # noqa: E402
from report_ast import (Attributed, Clause, Owned, Heading, ParagraphBreak,     # noqa: E402
                        EvidenceTable, CardBundle, CONNECTIVES, validate_report,
                        entailed_by_span, numbers_in, split_sentences)
from synthesis_contract import validate, Premise, Synthesis, OPERATIONS         # noqa: E402
import argument_planner as AP                                                   # noqa: E402
import cohesion_pass as CP                                                      # noqa: E402

DRAFTS = ROOT / 'outputs' / 'drafts'
MODEL = os.getenv('PG_GENERATOR_MODEL', 'z-ai/glm-5.2')

POLICIES = {p.name: p for p in (P.JOURNAL_ONLY, P.PEER_REVIEWED, P.OFFICIAL_TEXT, P.ANY_VERSION)}


# ----------------------------------------------------------------- LLM

def llm(prompt: str, max_tokens: int = 8192) -> str:
    def _call() -> str:
        from src.polaris_graph.llm.openrouter_client import OpenRouterClient

        async def _run() -> str:
            c = OpenRouterClient(model=MODEL)
            try:
                r = await c.generate(prompt=prompt, max_tokens=max_tokens, temperature=0.0)
                if isinstance(r, str):
                    return r
                content = getattr(r, 'content', None)
                if content is not None:
                    return content
                return r.get('content') if isinstance(r, dict) else str(r)
            finally:
                cl = getattr(c, 'close', None)
                if cl:
                    try:
                        await cl()
                    except Exception:
                        pass
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(_run())
        finally:
            loop.close()

    with futures.ThreadPoolExecutor(max_workers=1) as ex:
        return ex.submit(_call).result(timeout=420)


def jparse(s: str):
    s = re.sub(r'^```(?:json)?|```$', '', (s or '').strip(), flags=re.M).strip()
    m = re.search(r'\[.*\]', s, re.S)
    return json.loads(m.group(0)) if m else None


# ----------------------------------------------------------------- THE ONE BUNDLE

def sha256_file(p: Path) -> str:
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def load_bundle(cards_path: Path, graph_path: Path, ledger_path: Path,
                policy_name: str = 'journal_articles_only',
                expect_cards_sha: str = '', expect_graph_sha: str = '') -> CardBundle:
    """ONE explicit card-bundle path, plus ITS graph and ledger HASHES. No defaults that point at a file
    somebody else is writing.

    A hash mismatch is a REFUSAL, not a warning. The composer that ran before this one read a card file
    whose provenance it never established, and the number it produced (0.4603) is not a real number.
    """
    cards_sha, graph_sha = sha256_file(cards_path), sha256_file(graph_path)
    ledger_sha = sha256_file(ledger_path) if Path(ledger_path).exists() else ''
    if expect_cards_sha and expect_cards_sha != cards_sha:
        raise SystemExit(f'CARD BUNDLE IS NOT THE ONE PINNED: expected {expect_cards_sha[:16]}…, '
                         f'{cards_path} is {cards_sha[:16]}…')
    if expect_graph_sha and expect_graph_sha != graph_sha:
        raise SystemExit(f'GRAPH IS NOT THE ONE PINNED: expected {expect_graph_sha[:16]}…, '
                         f'{graph_path} is {graph_sha[:16]}…')
    graph = P.Graph.from_json(json.loads(Path(graph_path).read_text()))   # STRICT LOAD. May raise.
    cards = json.loads(Path(cards_path).read_text())
    return CardBundle(cards, graph, POLICIES[policy_name], cards_sha=cards_sha,
                      graph_sha=graph_sha, ledger_sha=ledger_sha)


def reverify(b: CardBundle) -> list[str]:
    """BEFORE ANY LLM CALL. Every PRIMARY and every CORROBORATING binding, re-resolved from the bytes.

    Not "on the way out". Not "in a preflight somebody may run". HERE, before a single token is spent,
    because a card that cannot prove its bytes must never reach a writer's context window — the writer
    will faithfully report it, and everything downstream will then be checking a fabrication against
    itself.
    """
    ok, bad = [], []
    # ITERATE A SNAPSHOT. The loop body ADDS corroborating cards to `b.cards`, and iterating a dict
    # while inserting into it is a RuntimeError. It does not fire today only because no card in this
    # bundle carries a corroborating source — i.e. the crash is waiting for the first one that does,
    # which is precisely the code path we least want to discover in production.
    for cid in list(b.cards):
        r = b.resolve(cid)
        (ok if r.ok else bad).append(cid if r.ok else f'{cid}: {r.refusal}')
        # A CORROBORATING SOURCE IS A CITATION. It gets the same chain, independently — it is exactly as
        # capable of naming a document its span never came from as the primary is.
        for j, cs in enumerate(b.cards[cid].get('corroborating_sources') or []):
            sub = dict(cs)
            sub.setdefault('id', f'{cid}#corr{j}')
            if sub['id'] not in b.cards:
                b.cards[sub['id']] = sub
            rc = b.resolve(sub['id'])
            if not rc.ok:
                bad.append(f'{cid} corroborating[{j}]: {rc.refusal}')
    return bad


# ----------------------------------------------------------------- selection & prompt

def _select(b: CardBundle, sub: str, k: int = 12) -> list[str]:
    """Pick the ADMITTED cards most relevant to this subsection. An unbound card is not a candidate."""
    want = {w for w in re.findall(r'[a-z]{4,}', sub.lower())}
    scored = []
    for cid in b.admitted_ids():
        c = b.cards[cid]
        blob = (f"{c.get('claim','')} {c.get('level','')} {c.get('method','')} "
                f"{' '.join(c.get('mechanisms') or [])} {' '.join(c.get('facet_tags') or [])} "
                f"{c.get('outcome','')} {c.get('technology','')} {c.get('industry','')}").lower()
        have = {w for w in re.findall(r'[a-z]{4,}', blob)}
        scored.append((len(want & have), cid))
    scored.sort(key=lambda x: -x[0])
    return [cid for s, cid in scored[:k] if s > 0] or [cid for _, cid in scored[:5]]


def _fmt_cards(b: CardBundle, card_ids: list[str]) -> str:
    """THE WRITER SEES THE SPAN AND THE CARD ID. IT NEVER SEES AN ATTRIBUTION.

    REFUSES an unbound card — it does not skip it, it raises. A composer that silently drops the cards it
    cannot justify still produces a document, and the document it produces is the one that gets
    published.
    """
    out = []
    for cid in card_ids:
        r = b.resolve(cid)
        if not r.ok:
            raise ValueError(f'_fmt_cards REFUSES an unbound card: {cid} — {r.refusal}')
        c = r.card
        span = re.sub(r'\s+', ' ', r.span).strip()
        mech = (f" | mechanism STATED BY THE PAPER: {', '.join(c['mechanisms'])}"
                if c.get('mechanisms') else '')
        out.append(
            f"card_id: {cid}\n"
            f"  THE SOURCE SAYS (verbatim — every number you write MUST appear here): \"{span}\"\n"
            f"  unit of analysis: {c.get('level') or c.get('unit_of_analysis') or '?'} | "
            f"horizon: {c.get('horizon') or '?'} | method: {c.get('method') or c.get('design') or '?'}"
            f"{mech}")
    return '\n'.join(out)


WRITE_PROMPT = """You are writing ONE subsection of an academic literature review on the restructuring impact of
Artificial Intelligence on the labor market, for a top-tier journal audience.

SECTION: {section}
SUBSECTION: {sub}
{plan}
THE EVIDENCE. These are the ONLY facts you may state. Each is a VERBATIM SPAN from a peer-reviewed
journal article, with the id of the card that holds it:

{cards}
{ledger}

** YOU DO NOT WRITE CITATIONS. ** Do not name an author. Do not name a journal. Do not write a year.
The citation is attached automatically, from a provenance graph, to whichever card_id you cite. If you
type an author's name or a journal's name, THE SENTENCE IS DELETED.

Return ONLY a JSON array of sentence objects. Two kinds, and no others:

  {{"voice": "ATTRIBUTED",
    "clauses": [{{"card_id": "<exact id from above>",
                 "text": "<the finding, in your words, WITH ITS NUMBER, and NOTHING that is not in
                          that card's span>"}}],
    "connective": "while"}}

  {{"voice": "OWNED",
    "premise_ids": ["<card_id>", "<card_id>"],
    "text": "<your own reasoning ACROSS those cards: what they jointly establish, where they conflict,
             what they do not settle. NO number. NO source name. NO new fact.>"}}

  {{"paragraph_break": true}}

RULES — every one is enforced mechanically, and a violating sentence is DELETED, never repaired:

1. AN ATTRIBUTED CLAUSE IS CHECKED AGAINST ITS OWN CARD'S SPAN. Every figure you write must appear,
   verbatim, in the span of the card_id you attached it to. A number from card A in a clause that cites
   card B is a fabrication and it is caught.
2. ** WHERE A CARD CARRIES A FIGURE, REPORT THE FIGURE. ** The effect size, the percentage, the
   elasticity. The #1 system on this benchmark reports 202 quantitative findings; our last report
   reported 2, and the judge wrote "citations are named but findings are missing". A cited source with
   no finding attached is our single most expensive defect.
3. A CROSS-SOURCE SENTENCE IS THE MOST VALUABLE SENTENCE IN A REVIEW. To compare two papers, emit ONE
   ATTRIBUTED object with TWO clauses, each naming its own card_id, joined by a connective from:
   {connectives}. This is how you write "X finds a, while Y finds b" — and each half is checked against
   its own source.
4. AN OWNED SENTENCE IS YOUR VOICE. It may draw a conclusion the sources do not state — that is what
   insight IS — but it may not carry a number, a name, or a new particular, and it must reason over at
   least TWO premise cards. Use verdict language: "establishes", "does not establish", "is limited to",
   "cannot distinguish", "remains unresolved".
   You may NOT invent a causal explanation. If no card states a mechanism, you may say the findings
   differ in level, horizon, or method — you may NOT say why the world behaves that way.
5. Open each paragraph with a claim, not a topic announcement. Never mention this pipeline or "the
   question above". Aim for 2-4 paragraphs of ~100 words, separated by {{"paragraph_break": true}}.
6. ** SAY EACH FACT ONCE. ** A finding stated in full in one place and REFERRED BACK TO in another is a
   review; a finding re-narrated in eight places is a list. Where a fact below is marked SPENT or is
   licensed only in a NEW ROLE, obey that: the sentence that restates it is deleted, and you will have
   spent your paragraph on nothing.

Return ONLY the JSON array."""


# ----------------------------------------------------------------- LLM output -> AST NODES

def _nodes_from(raw, b: CardBundle, allowed: set[str]) -> tuple[list, list[str]]:
    """Parse the model's structured output into TYPED NODES. Anything malformed is DROPPED, with a
    reason. Nothing is repaired, and nothing untyped ever becomes prose."""
    nodes, dropped = [], []
    if not isinstance(raw, list):
        return [], ['model did not return a JSON array']
    for item in raw:
        if not isinstance(item, dict):
            dropped.append(f'not an object: {str(item)[:50]}')
            continue
        if item.get('paragraph_break'):
            nodes.append(ParagraphBreak())
            continue
        voice = (item.get('voice') or '').upper()
        if voice == 'ATTRIBUTED':
            cls = []
            bad = False
            for cl in (item.get('clauses') or []):
                cid, txt = (cl or {}).get('card_id'), ((cl or {}).get('text') or '').strip()
                if cid not in allowed:
                    dropped.append(f'ATTRIBUTED cites a card not offered to it: {cid!r}')
                    bad = True
                    break
                if not txt:
                    bad = True
                    break
                cls.append(Clause(card_id=cid, text=txt))
            if bad or not cls:
                continue
            conn = (item.get('connective') or 'while').strip().lower()
            if conn not in CONNECTIVES:
                conn = 'while'
            nodes.append(Attributed(clauses=tuple(cls), connective=conn))
        elif voice == 'OWNED':
            txt = (item.get('text') or '').strip()
            pids = tuple(p for p in (item.get('premise_ids') or []) if p in allowed)
            if not txt:
                continue
            # ONE NODE, ONE SENTENCE. A model that packs three sentences into one OWNED object is not
            # granted one licence for three claims: each sentence becomes its own node, over the SAME
            # premises, and each must pass the owned lane ALONE. This is strictly stricter than gating
            # the blob — it is not a repair, it is the law applied at the granularity the law is
            # written at, and it is what makes a per-sentence receipt possible.
            for s in split_sentences(txt):
                nodes.append(Owned(text=s, premise_ids=pids))
        else:
            dropped.append(f'unknown voice {voice!r}')
    return nodes, dropped


OUTLINE = [
    ('Scope, Methods, and Source Selection', [
        'This review draws only on peer-reviewed journal articles',
        'What counts as labor-market restructuring',
    ]),
    ('AI as the Driver of the Fourth Industrial Revolution', [
        'How the Fourth Industrial Revolution differs from the previous three',
        'Why AI is a general-purpose technology rather than a single innovation',
        'The scale and speed of the disruption claimed in the literature',
    ]),
    ('Theoretical Frameworks for Technological Displacement', [
        'Skill-biased technical change and its limits',
        'The task-based framework: displacement, reinstatement, and the labor share',
        'Prediction machines: AI as a fall in the cost of prediction',
    ]),
    ('Measuring Exposure, Adoption, and Realized Outcomes', [
        'Exposure measures encode different theories of susceptibility',
        'Exposure is not adoption, and adoption is not impact',
    ]),
    ('Employment, Displacement, and Job Creation', [
        'Evidence for displacement at the occupational level',
        'Evidence for reinstatement and new task creation',
        'Why firm-level and aggregate estimates diverge',
    ]),
    ('Wages, Skills, and the Labor Share', [
        'Skill demand is being recomposed rather than simply raised',
        'The labor share and the distribution of gains',
    ]),
    ('Productivity and the Generative-AI Turn', [
        'Task-level productivity gains in controlled settings',
        'Why large task gains coexist with weak aggregate effects',
    ]),
    ('Sectoral Disruption Across Industries', [
        'Manufacturing and the robotics evidence',
        'Professional, financial, and knowledge services',
        'Healthcare, education, and the caring professions',
        'Creative work and the generative-AI frontier',
    ]),
    ('Critical Synthesis: What the Literature Establishes and What It Does Not', [
        'What the evidence establishes',
        'Where the literature genuinely disagrees',
        'What the evidence cannot yet resolve',
    ]),
    ('Implications and a Research Agenda', [
        'Implications that follow from the mechanisms',
        'Gaps the evidence itself exposes',
    ]),
]


# ----------------------------------------------------------------- THE ABSTRACT — THROUGH THE AST
#
# The old abstract was FOUR HAND-WRITTEN SENTENCES in an f-string at write_report():709, asserting
# "The evidence establishes displacement at the task and occupational level and productivity gains in
# controlled settings" over a corpus in which the composer had never checked a single binding. It went
# into the judged file WITHOUT PASSING THROUGH ANY GATE IN THIS FILE. It is now nodes, and it is
# validated by exactly the same code as every other sentence.

def abstract_nodes(b: CardBundle) -> list:
    """OWNED frame sentences: no source, no number, no new particular. That is all the law permits a
    sentence licensed by nothing."""
    return [
        Heading(2, 'Abstract'),
        Owned(text='**Objective.** This review examines how artificial intelligence, as a '
                   'general-purpose technology of the Fourth Industrial Revolution, is restructuring '
                   'work across industries.'),
        ParagraphBreak(),
        # The first draft of THIS sentence said "...whose full text was retrieved and verified", and the
        # gate deleted it as META_COMMENTARY. It was right to: "retrieved" is a fact about a pipeline,
        # and a literature review has no pipeline. Then the PUBLISHER refused the next draft, because
        # it packed two sentences into one node and the sidecar could not issue a receipt for either.
        # The law caught its own author twice, in the one lane that used to have no gate at all.
        Owned(text='**Methods.** The review draws exclusively on peer-reviewed, English-language '
                   'journal articles.'),
        Owned(text='Every finding below is taken from a verbatim passage of the article it is credited '
                   'to, and no finding is stated that its cited article does not itself state.'),
        ParagraphBreak(),
        Owned(text='**Scope.** Where only a working-paper or preprint version of a study could be '
                   'obtained, that study is excluded from the findings rather than cited as though the '
                   'journal article of record had been read.'),
        ParagraphBreak(),
    ]


def methods_nodes(b: CardBundle) -> list:
    n_cards = len(b.admitted_ids())
    n_units = len({b.resolve(c).work_id for c in b.admitted_ids()})
    return [
        Heading(2, 'Scope, Methods, and Source Selection'),
        Owned(text='**Source policy.** Only articles published in peer-reviewed journals are cited.'),
        Owned(text='Working papers, preprints, accepted manuscripts, landing pages and abstracts are '
                   'excluded from the evidence base, and are retained only as leads to a published '
                   'version of record.'),
        ParagraphBreak(),
        Owned(text=f'**Evidence base.** The findings below rest on {_spell(n_cards)} verified passages '
                   f'drawn from {_spell(n_units)} peer-reviewed studies.'),
        Owned(text='A passage is admitted only where the article\'s own text states the finding '
                   'attributed to it.'),
        ParagraphBreak(),
    ]


_WORDS = {0: 'no', 1: 'one', 2: 'two', 3: 'three', 4: 'four', 5: 'five', 6: 'six', 7: 'seven',
          8: 'eight', 9: 'nine', 10: 'ten', 11: 'eleven', 12: 'twelve'}


def _spell(n: int) -> str:
    """An OWNED sentence MAY NOT CARRY A NUMBER — including the count of its own sources. Spelling it
    is not a loophole: the constraint is that the reviewer's voice asserts no PARTICULAR that a SOURCE
    must vouch for, and a digit in that lane is sourced to nothing. This count is a fact about THIS
    DOCUMENT, not about the world, so it is stated in words and it is true by construction."""
    return _num_words(max(0, int(n)))


def _num_words(n: int) -> str:
    tens = {2: 'twenty', 3: 'thirty', 4: 'forty', 5: 'fifty', 6: 'sixty', 7: 'seventy', 8: 'eighty',
            9: 'ninety'}
    if n < 13:
        return _WORDS[n]
    if n < 20:
        return {13: 'thirteen', 14: 'fourteen', 15: 'fifteen', 16: 'sixteen', 17: 'seventeen',
                18: 'eighteen', 19: 'nineteen'}[n]
    if n < 100:
        t, u = divmod(n, 10)
        return tens[t] + (f'-{_WORDS[u]}' if u else '')
    h, r = divmod(n, 100)
    return f'{_WORDS[h]} hundred' + (f' and {_num_words(r)}' if r else '')


def table_card_ids(b: CardBundle, limit: int = 14) -> list[str]:
    """The quantitative rows. Every one RE-VERIFIES its binding inside EvidenceTable's validator, and
    every figure must stand as its own number in that row's own span."""
    best: dict[str, tuple[int, str]] = {}
    for cid in b.admitted_ids():
        r = b.resolve(cid)
        c = r.card
        claim = c.get('claim') or ''
        nums = [n for n in numbers_in(claim) if len(n) >= 2 and n != str(b.graph.works[r.work_id].year)]
        if not nums:
            continue
        ok, _ = entailed_by_span(claim, r.span, b.graph.works.get(r.work_id), min_overlap=0.34)
        if not ok:
            continue
        prev = best.get(r.work_id)
        if prev is None or len(nums) > prev[0]:
            best[r.work_id] = (len(nums), cid)
    return [cid for _, cid in sorted(best.values(), key=lambda x: -x[0])][:limit]


# ----------------------------------------------------------------- THE ARGUMENT (argument_planner)
#
# The composer used to fan 28 subsections out to threads and generate every one INDEPENDENTLY: nobody
# anywhere decided what was COMPARED WITH WHAT, so the report LISTED findings and the "Critical Synthesis"
# criterion (w=0.0800, the joint-heaviest on the board) scored 6.36. `argument_planner.py` builds
# COMPARISON BUNDLES from the bound cards BEFORE a word of prose exists, keyed on (outcome x unit x ...),
# and hands each subsection a PLAN. This wires it in.
#
# THE OWNED VERDICT IS DETERMINISTIC, AND IT IS RE-GATED HERE. The planner writes each verdict from
# span-lifted surface forms + declared fields and pre-validates it through synthesis_contract at plan
# time; the composer nonetheless runs EVERY verdict node back through `validate_report` before it can
# become prose, so a verdict that does not survive the SHIPPING gate is DROPPED, never repaired. The
# builder does not certify itself: the same gate that judges the model's sentences judges the planner's.

# THE OUTCOME-DECOY GUARD — THE COMPOSER IS A CAREFUL CONSUMER, NOT A RUBBER STAMP.
# The planner keys `employment` on `\bjobs?\b` with a negative-lookahead that excludes
# satisfaction|security|quality|... but NOT `engagement`. On the real corpus that mis-tags five
# Braganza (2021) cards — "job engagement", "employee engagement", psychological-contract HR findings —
# as outcome=employment, and manufactures a same-unit OPPOSITE-DIRECTION "genuine conflict" against
# Schwabe's real displacement finding. Every particular in that sentence is true and the RELATION is
# invented: it is the exact FALSE RECONCILIATION THE LAW burns the artifact for, and NO downstream gate
# catches it, because there is no fabricated particular to catch. So a comparison is trusted only when
# BOTH cards' outcome is an unambiguous QUANTITY, not a compound noun. (The durable fix is one clause in
# argument_planner.default_contract()'s employment lookahead; it is reported upstream, not patched here.)
_OUTCOME_DECOY = re.compile(
    r'\b(?:job|jobs|employee|employees|worker|workers)\s+'
    r'(?:engagement|satisfaction|performance|insecurity|crafting|autonomy|motivation|experience|'
    r'well[-\s]?being|stress|burnout|morale|commitment|security|quality)\b', re.I)

# A deterministic verdict occasionally fills its CONTEXT slot with a polarity word ("... not
# contradictory in studies of negative: ..."): the claim is sound, the clause is broken prose. Strip
# THAT clause only; never touch the verdict itself.
_BAD_CTX = re.compile(r' in studies of (?:positive|negative|growth|decline|increas\w+|decreas\w+|'
                      r'reduc\w+|rais\w+|rising|falling|fell|rose|loss|losses|gains?|complement\w*|'
                      r'substitut\w*)\b', re.I)

# Only this bundle kind is emitted as an OWNED verdict. It carries the DEFENSIVE adjudication — "the
# evidence establishes X at the firm level but not economy-wide" / "these bear on different units and do
# not speak to the same quantity" — which is cellcog's own winning synthesis move and is sound on this
# corpus. SAME_UNIT_OPPOSITE_DIRECTION ("the evidence genuinely conflicts") is deliberately NOT emitted:
# asserting a conflict is the highest-risk owned claim, and every instance this corpus supports is a
# mis-tag artifact (see _OUTCOME_DECOY). A boundary/does-not-establish sentence never lies; a false
# conflict burns the artifact.
_VERDICT_KIND = 'SAME_OUTCOME_DIFFERENT_UNIT'


def _outcome_clean(bundle, cards_by_id: dict) -> bool:
    """Both cards' outcome must be an unambiguous quantity, not a compound noun (see _OUTCOME_DECOY)."""
    return all(not _OUTCOME_DECOY.search(cards_by_id[c].get('span') or '') for c in bundle.card_ids)


def _owned_from_planner(text: str, premise_ids, b: CardBundle):
    """Wrap a planner-authored OWNED string as a node and RE-GATE it. -> Owned or None.

    report_ast refuses any owned synthesis with fewer than two premises (SYNTHESIS_NEEDS_2_PREMISES),
    so a one-card bundle (UNCOUNTERED) can never license one here; and anything that does not clear the
    shipping gate is discarded rather than fixed."""
    if len(premise_ids) < 2:
        return None
    text = _BAD_CTX.sub('', text or '').strip()
    if not text:
        return None
    node = Owned(text=text, premise_ids=tuple(premise_ids))
    return node if not validate_report([node], b) else None


def _verdict_node(bundle, cf_by_id: dict, b: CardBundle):
    return _owned_from_planner(AP._verdict_text(bundle, cf_by_id), bundle.card_ids, b)


def _boundary_node(bundle, cf_by_id: dict, b: CardBundle):
    return _owned_from_planner(AP._boundary_text(bundle, cf_by_id), bundle.card_ids, b)


def _plan_brief(comps) -> str:
    """The writer's brief for an adjudicative subsection: open with a claim, and for each comparison
    write ONE two-clause attributed sentence. The VERDICT is added deterministically after the writer's
    findings, so the writer is told NOT to adjudicate in its own voice — it states the two sides."""
    if not comps:
        return ''
    lines = ['THIS SUBSECTION ADJUDICATES — open with a CLAIM, not a topic announcement. For EACH '
             'comparison below, write ONE ATTRIBUTED sentence with TWO clauses (one per card_id, joined '
             'by a connective), each stating that source\'s finding WITH ITS FIGURE:']
    for i, (bd, _v, _bnd) in enumerate(comps, 1):
        a, c = bd.card_ids
        units = ' vs '.join(sorted(bd.varies.values()))
        lines.append(f'  COMPARISON {i}: card {a}  AND  card {c}  '
                     f'— same outcome ({bd.shared.get("outcome", "?")}), different unit of analysis '
                     f'({units}).')
    lines.append('An analytical verdict is appended automatically after your sentences; do NOT write '
                 '"these are not contradictory" or a synthesis in your own voice — state the findings.')
    return '\n' + '\n'.join(lines) + '\n'


def _assign_comparisons(jobs, plans, all_bundles, cf_by_id, cards_by_id, b, contract,
                        k_adjudicative: int = 3) -> dict:
    """Hand each subsection the SOUND, DISTINCT comparison bundles it will adjudicate. Deterministic,
    run once BEFORE the writer threads, so no two subsections are dealt the same bundle and no thread
    races another for one.

    ADJUDICATIVE subsections — matched on the vocabulary of ARGUMENT ('disagree', 'establish',
    'resolve', 'gap'), which is general to any question — get FIRST PICK and SEVERAL bundles each. That
    concentration is what the Critical Synthesis section needs and never had (210 words of 8,012). A
    'disagreement' heading is served the apparent-conflict verdicts (which acknowledge the tension and
    dissolve it by unit of analysis); the others take the plain does-not-establish verdicts. Topical
    subsections take AT MOST ONE, and only the bundle the planner already found relevant to them."""
    def roles_for(sub: str):
        for pat, kinds in contract.adjudicative_roles.items():
            if re.search(pat, sub, re.I):
                return kinds
        return []

    # sound, gate-surviving verdict bundles, richest evidence first
    sound = []
    for bd in sorted(all_bundles, key=lambda z: -z.score):
        if bd.kind != _VERDICT_KIND or len(bd.card_ids) != 2 or not _outcome_clean(bd, cards_by_id):
            continue
        v = _verdict_node(bd, cf_by_id, b)
        if v is not None:
            sound.append((bd, v, _boundary_node(bd, cf_by_id, b)))

    out: dict = {job: [] for job in jobs}
    used_keys: set = set()
    used_sig: set = set()                       # (outcome, units) — one narration per contrast

    def take(job, limit, prefer_apparent=None):
        for bd, v, bnd in sound:
            if len(out[job]) >= limit:
                break
            sig = (bd.shared.get('outcome'), tuple(sorted(bd.varies.values())))
            if bd.key() in used_keys or sig in used_sig:
                continue
            if prefer_apparent is not None and bd.apparent_conflict != prefer_apparent:
                continue
            out[job].append((bd, v, bnd))
            used_keys.add(bd.key())
            used_sig.add(sig)

    # PASS 1 — adjudicative subsections, first pick, several each. A 'disagreement' heading claims the
    # apparent-conflict verdicts (which name a tension and dissolve it by unit of analysis) BEFORE an
    # 'establishes' heading can take them; then every adjudicative subsection fills up from what remains.
    adj = [job for job in jobs if roles_for(job[1])]
    for job in adj:
        if re.search(r'disagree|conflict|tension|contested|contradict', job[1], re.I):
            take(job, k_adjudicative, prefer_apparent=True)
    for job in adj:
        take(job, k_adjudicative)

    # PASS 2 — topical subsections, at most one, and only what the planner found relevant here.
    plan_by_job = {(p.section, p.subsection): p for p in plans}
    for job in jobs:
        if out[job] or roles_for(job[1]):
            continue
        p = plan_by_job.get(job)
        cmp = p.comparison if p else None
        if not (cmp and cmp.kind == _VERDICT_KIND and _outcome_clean(cmp, cards_by_id)):
            continue
        sig = (cmp.shared.get('outcome'), tuple(sorted(cmp.varies.values())))
        if cmp.key() in used_keys or sig in used_sig:
            continue
        v = _verdict_node(cmp, cf_by_id, b)
        if v is None:
            continue
        out[job].append((cmp, v, _boundary_node(cmp, cf_by_id, b)))
        used_keys.add(cmp.key())
        used_sig.add(sig)
    return out


# ----------------------------------------------------------------- THE FACT-USE LEDGER
#
# MEASURED ON THE SHIPPED REPORT: 222 card slots drawn from 82 cards. ONE finding narrated EIGHT TIMES.
# 41 exact repetitions. ~1,500-2,000 words of pure restatement — in a document whose lowest criterion is
# paragraph cohesion and whose judge wrote "fragmented narrative".
#
# THE CAUSE IS IN THIS FILE, AND IT IS `_select()`. Every subsection independently scores every admitted
# card by lexical fit and takes the top 12. A canonical finding — the one with the big number and the
# familiar vocabulary — scores in the top 12 of EIGHT subsections, so it is DEALT to eight writers, and
# eight writers each faithfully narrate it. No writer misbehaved. Nobody ever told them it was spent.
#
# `fact_use_ledger.plan_bundles()` deals every subsection a DELIBERATELY DIFFERENT bundle: narration is
# a PARTITION over findings (R1 — narrated in full exactly once), reuse is granted only in a NEW
# ANALYTICAL ROLE that must ADD something (R2/R3 — mechanism / contrast / boundary / method / implication),
# and everything else degrades to an OWNED BACKWARD REFERENCE that POINTS at the fact without SAYING it
# again (R4).
#
# IDENTITY IS KEYED ON sha1(THE VERBATIM SPAN), NEVER ON THE MODEL'S `claim`: "identity keyed on model
# prose is identity the model can forge by rewording" — a writer could otherwise launder a spent fact
# into a fresh one just by paraphrasing it.
#
# WHAT THE LEDGER DOES NOT DO: it does not touch the BASKET. Corroborating sources stay retained, cited
# and counted (`Cluster.corroborators`); the ledger governs RHETORICAL REUSE ONLY. And it is NOT a
# "one card, one section" partition of the EVIDENCE — Sol rejected that explicitly, because it starves
# the theory and synthesis sections of the canonical findings they exist to reason over. Those sections
# still get the big findings; they get them in a role that does a NEW JOB.


class Licence:
    """What THIS subsection may do with each card. The unit of authority is (card, subsection)."""

    __slots__ = ('narrate', 'new_role', 'backref')

    def __init__(self, narrate=(), new_role=(), backref=()):
        self.narrate = list(narrate)                 # card_ids: state in full, WITH the figure
        self.new_role = list(new_role)               # (card_id, role, must_add)
        self.backref = list(backref)                 # card_ids: point at it, NEVER restate it

    @property
    def attributable(self) -> list[str]:
        """The ONLY cards this subsection may put in an ATTRIBUTED clause."""
        return list(dict.fromkeys(self.narrate + [cid for cid, _r, _a in self.new_role]))


def _fact_use_plan(b: CardBundle, admitted: list[str], jobs: list) -> tuple[dict, dict]:
    """Run the ledger's planner over the ADMITTED cards and translate findings -> card_ids.

    The ledger speaks in FINDING ids (work + span hash). The composer speaks in CARD ids. This is the
    only place the two vocabularies meet, and the mapping is deterministic: `admitted` is ordered, so
    where two cards carry the same finding (same work, same bytes — 13 of them do in this bundle) the
    first one always wins and the duplicate is not separately narratable. That is not a loss: a second
    card over the SAME SPAN OF THE SAME PAPER is the same fact twice, which is the disease.
    """
    import fact_use_ledger as FUL          # deferred: FUL imports OUTLINE from this module (a cycle)

    plan_cards = [b.cards[cid] for cid in admitted]
    cid_of_fid: dict[str, str] = {}
    for cid in admitted:
        cid_of_fid.setdefault(FUL.finding_id(b.cards[cid]), cid)

    bundles, records = FUL.plan_bundles(plan_cards, OUTLINE)
    by_job = {(bd.section, bd.subsection): bd for bd in bundles}

    lic: dict = {}
    for job in jobs:
        bd = by_job.get(job)
        if bd is None:
            lic[job] = Licence()
            continue
        lic[job] = Licence(
            narrate=[cid_of_fid[f] for f in bd.narrate if f in cid_of_fid],
            new_role=[(cid_of_fid[f], r, add) for f, r, add in bd.new_role if f in cid_of_fid],
            backref=[cid_of_fid[f] for f in bd.backref if f in cid_of_fid])
    return lic, records


def _rank(b: CardBundle, cids: list[str], sub: str, k: int) -> list[str]:
    """Order a LICENSED set by how well it fits this subsection — scored on the PAPER'S SPAN and its
    declared fields (`fact_use_ledger.relevance`), never on the model-written `claim` that `_select`
    scores on. Licence decides WHETHER a card may be spoken here; relevance only decides the order."""
    import fact_use_ledger as FUL

    return sorted(dict.fromkeys(cids), key=lambda c: -FUL.relevance(b.cards[c], sub))[:k]


_NUM = re.compile(r'\d')


def _backref_topic(b: CardBundle, cid: str) -> str:
    """A NUMBER-FREE handle for a spent fact, built from the card's DECLARED FIELDS.

    The writer is asked to point back at this finding in its OWN voice. So it must not be shown the
    span (it would restate it) and must not be shown the `claim` (it carries the figure). It is shown
    the outcome, the unit and the sector — enough to refer, not enough to re-narrate. Any field that
    contains a digit is dropped: a backward reference that carries a number is a restatement.
    """
    c = b.cards[cid]
    bits = [str(c.get(k) or '').strip() for k in ('outcome', 'level', 'technology', 'industry')]
    bits = [x for x in bits if x and not _NUM.search(x) and len(x) < 42]
    return ' / '.join(dict.fromkeys(bits)) or 'a finding stated earlier in this review'


def _ledger_brief(b: CardBundle, lic: Licence) -> str:
    """The writer's standing orders on RHETORICAL REUSE. Mechanically enforced below — a violating
    sentence is DELETED, never repaired."""
    out: list[str] = []
    if lic.new_role:
        out.append('THESE FACTS HAVE ALREADY BEEN STATED IN FULL ELSEWHERE IN THIS REVIEW. You may use '
                   'each ONE more time, but ONLY TO DO A NEW JOB — not to tell it again:')
        for cid, role, add in lic.new_role:
            out.append(f'  card {cid} — permitted role here: {role.value} '
                       f'(the sentence must perform a {add}: set it AGAINST another finding, BOUND it, '
                       f'impugn its METHOD, or draw an IMPLICATION from it). Do not re-narrate it.')
    if lic.backref:
        out.append('THESE FACTS ARE SPENT. They are stated in full elsewhere and you may NOT state them '
                   'again — not their figure, not their finding. Where one bears on your argument, refer '
                   'BACKWARD to it in an OWNED sentence that names no source and carries NO NUMBER '
                   '(e.g. "the occupational-level displacement evidence considered above bears directly '
                   'on this question"). An ATTRIBUTED clause citing one of these is DELETED:')
        for cid in lic.backref:
            out.append(f'  (spent) {_backref_topic(b, cid)}')
    return ('\n' + '\n'.join(out) + '\n') if out else ''


def _ledger_gate(nodes: list, lic: Licence, comp_ids: set[str], sub: str) -> tuple[list, list[str]]:
    """THE ENFORCEMENT. An ATTRIBUTED clause may cite ONLY a card this subsection is licensed to speak.

    This is the check that makes the ledger REAL rather than advisory. The prompt above merely ASKS;
    a model that ignores it and narrates a spent fact anyway — which is exactly what a model under
    instruction-pressure does — has the sentence DELETED here, against the plan, before it can reach
    the page. Removing this function puts the eighth narration back.

    The comparison cards from `argument_planner` are licensed BY THE COMPARISON: adjudicating two
    findings against each other IS a new analytical role (CONTRAST), and the verdict that follows is
    unreadable if the two sides are not on the page.
    """
    allowed = set(lic.attributable) | set(comp_ids)
    good, dropped = [], []
    for n in nodes:
        if isinstance(n, Attributed):
            spent = [cl.card_id for cl in n.clauses if cl.card_id not in allowed]
            if spent:
                dropped.append(f'FACT_LEDGER: card {spent[0]} is SPENT here — it is narrated in full '
                               f'elsewhere; this subsection is licensed only to refer BACK to it')
                continue
        good.append(n)
    return good, dropped


# ----------------------------------------------------------------- compose

def write_report(cards_path: Path, graph_path: Path, ledger_path: Path, policy: str,
                 expect_cards_sha: str = '', expect_graph_sha: str = '', dry: bool = False) -> int:
    b = load_bundle(cards_path, graph_path, ledger_path, policy, expect_cards_sha, expect_graph_sha)

    # ============ BEFORE ANY LLM CALL ============
    bad = reverify(b)
    admitted = b.admitted_ids()
    print('=' * 90)
    print('THE COMPOSER — one card lane, one graph, one policy. It cannot publish.')
    print('=' * 90)
    print(f'  cards        : {cards_path}  ({b.cards_sha[:16]}…)')
    print(f'  graph        : {graph_path}  ({b.graph_sha[:16]}…)')
    print(f'  ledger       : {ledger_path}  ({b.ledger_sha[:16]}…)')
    print(f'  policy       : {b.policy.name}')
    print(f'  bindings RE-VERIFIED BEFORE ANY LLM CALL: {len(admitted)} admitted, {len(bad)} refused')
    for x in bad[:5]:
        print(f'     - REFUSED {x[:100]}')
    if not admitted:
        print('\n** NO ADMITTED CARDS. There is nothing this policy permits us to say. NOTHING SHIPS. **')
        return 1
    units = {b.resolve(c).work_id for c in admitted}
    print(f'  evidence units (studies) available     : {len(units)}')

    jobs = [(sec, sub) for sec, subs in OUTLINE for sub in subs]

    # ============ BUILD THE ARGUMENT BEFORE ANY PROSE — comparison bundles over the ADMITTED cards.
    # Only admitted cards are handed to the planner, so every card in every bundle is guaranteed to
    # resolve. If the planner fails for any reason, the composer degrades to REPORTING (no adjudication)
    # rather than not shipping — a review that lists is worse than one that argues, but better than none.
    plan_cards = [b.cards[cid] for cid in admitted]
    cards_by_id = {c['id']: c for c in plan_cards}
    comps_for: dict = {job: [] for job in jobs}
    n_bundles = 0
    try:
        contract = AP.default_contract()
        cfs = [AP.derive_facets(c, contract) for c in plan_cards]
        cf_by_id = {c.card_id: c for c in cfs}
        all_bundles = AP.find_bundles(cfs, contract, cards_by_id)
        n_bundles = sum(1 for x in all_bundles if x.kind != 'NOT_A_COMPARISON')
        plans = AP.plan_subsections(plan_cards, cfs, all_bundles, contract)
        comps_for = _assign_comparisons(jobs, plans, all_bundles, cf_by_id, cards_by_id, b, contract)
    except Exception as e:                       # planner is deterministic + tested; belt and braces
        print(f'  ** argument planner unavailable ({e!r}); subsections will REPORT, not ADJUDICATE **')
    n_verdicts = sum(len(v) for v in comps_for.values())
    print(f'  comparison bundles found                : {n_bundles}')
    print(f'  sound cross-source verdicts placed       : {n_verdicts} '
          f'(across {sum(1 for v in comps_for.values() if v)} subsections)')

    # ============ WHO MAY SAY WHAT, AND WHERE — the fact-use ledger, BEFORE any prose exists.
    # Narration is a PARTITION over findings; reuse must do a NEW JOB; everything else is a backward
    # reference. If the ledger fails, the composer does NOT silently fall back to the old lexical
    # free-for-all — that is the defect. It refuses, because a report that restates one finding eight
    # times is the exact artifact we are here to stop shipping.
    licences, fact_records = _fact_use_plan(b, admitted, jobs)
    unspoken = set(admitted) - {cid for lc in licences.values()
                                for cid in (lc.narrate + [c for c, _r, _a in lc.new_role])}
    n_narr = sum(len(lc.narrate) for lc in licences.values())
    n_reuse = sum(len(lc.new_role) for lc in licences.values())
    n_back = sum(len(lc.backref) for lc in licences.values())
    print(f'  FACT-USE LEDGER: {len(fact_records)} distinct findings (span-keyed) over {len(admitted)} cards')
    print(f'     narrated ONCE each                   : {n_narr} slots  (was: 222 slots from 82 cards)')
    print(f'     reused only in a NEW ANALYTICAL ROLE : {n_reuse}')
    print(f'     degraded to an OWNED BACKWARD REF    : {n_back}')
    print(f'     unspoken (free to any starved section): {len(unspoken)}')

    def one(job):
        sec, sub = job
        comps = comps_for.get(job) or []
        lic = licences.get(job) or Licence()
        # THE WRITER'S CARD SET: the comparison pairs FIRST (they must be on the page for the verdict to
        # read), then WHATEVER THIS SUBSECTION IS LICENSED TO SPEAK. The plan is FILLED, not freelanced.
        #
        # This line is the whole of TASK A's behavioural change. It used to be `_select(b, sub)` — an
        # INDEPENDENT top-12-by-lexical-fit, run 26 times over the same 232 cards, which is precisely how
        # one card came to be dealt to eight subsections and narrated eight times. The candidate pool is
        # now the LICENCE: the cards this subsection may narrate, plus the cards it may reuse IN A NEW
        # ROLE. A card spent elsewhere is not in the writer's context window at all, so the cheapest way
        # to not restate a fact is used first — never show it to the writer — and `_ledger_gate` below
        # catches the case where the model cites one anyway.
        comp_ids = [cid for (bd, _v, _bnd) in comps for cid in bd.card_ids]
        sel = [cid for cid in dict.fromkeys(comp_ids) if b.resolve(cid).ok]
        licensed = [cid for cid in lic.attributable if b.resolve(cid).ok]
        sel = list(dict.fromkeys(sel + _rank(b, licensed, sub, k=12)))[:12]
        if len(sel) < 3:
            # THE LEDGER STARVED THIS SUBSECTION, and an empty subsection is worse than an imperfect one.
            # But the fallback may NOT be the old lexical `_select`: that re-opens the exact lane R1
            # closes, and every card it returned would then be DELETED by `_ledger_gate` anyway — a paid
            # LLM call spent to produce nothing. It falls back only onto UNSPOKEN cards: admitted cards
            # that no subsection anywhere narrates or reuses. Speaking one of those breaks no rule,
            # because nobody else was ever going to say it.
            extra = [cid for cid in _select(b, sub) if cid in unspoken and b.resolve(cid).ok]
            sel = list(dict.fromkeys(sel + extra))[:12]
            lic.narrate += [cid for cid in extra if cid not in lic.narrate]   # the gate must let them by

        # THE DETERMINISTIC ADJUDICATION — planner-authored, already re-gated in _assign_comparisons.
        # Each comparison contributes its VERDICT (the varied payload — a different outcome/unit each);
        # boundaries are structurally alike ("...does not settle the magnitude..."), so only ONE is kept
        # per subsection, as a closing note rather than a refrain.
        verdicts = [v for (_bd, v, _bnd) in comps if v is not None]
        boundary = next((bnd for (_bd, _v, bnd) in comps if bnd is not None), None)
        owned = verdicts + ([boundary] if boundary is not None else [])

        if dry:
            return job, list(owned), ['--dry: no LLM call']
        if not sel:
            return job, list(owned), (['no cards selected'] if not owned else [])
        prompt = WRITE_PROMPT.format(section=sec, sub=sub, plan=_plan_brief(comps),
                                     cards=_fmt_cards(b, sel), ledger=_ledger_brief(b, lic),
                                     connectives=', '.join(CONNECTIVES))
        try:
            raw = jparse(llm(prompt, max_tokens=8192))
        except Exception as e:
            return job, list(owned), [f'llm: {e}']
        nodes, dropped = _nodes_from(raw, b, set(sel))
        # THE FACT-USE LEDGER, ON THE CRITICAL PATH — a spent fact may not be narrated again.
        nodes, spent_drops = _ledger_gate(nodes, lic, set(comp_ids), sub)
        dropped += spent_drops
        # THE GATE, ON THE CRITICAL PATH — node by node, against the bytes.
        good = []
        for i, n in enumerate(nodes):
            fails = validate_report([n], b)
            if fails:
                dropped += [str(f) for f in fails]
                continue
            good.append(n)
        # FINDINGS FIRST, THEN THE VERDICT THAT ADJUDICATES THEM. The owned verdict names the two cards
        # as premises; the writer has just stated them above it.
        return job, good + list(owned), dropped

    results: dict = {}
    all_dropped: list[str] = []
    with futures.ThreadPoolExecutor(max_workers=6) as ex:
        for job, nodes, dropped in ex.map(one, jobs):
            results[job] = nodes
            all_dropped += [f'{job[1][:34]} :: {d}' for d in dropped]
            n_a = sum(1 for n in nodes if isinstance(n, Attributed))
            n_o = sum(1 for n in nodes if isinstance(n, Owned))
            print(f'  [{n_a:>2} attributed | {n_o:>2} owned]  {job[1][:56]}')

    # ---- ASSEMBLE THE AST. Every node — abstract, methods, table, body — is the same type.
    nodes: list = [Heading(1, 'The Restructuring Impact of Artificial Intelligence on the Labor Market')]
    nodes += abstract_nodes(b)
    nodes += methods_nodes(b)
    tbl = table_card_ids(b)
    for i, (sec, subs) in enumerate(OUTLINE):
        if sec == 'Scope, Methods, and Source Selection':
            continue                      # already emitted, as nodes, above
        body: list = []
        for sub in subs:
            ns = results.get((sec, sub)) or []
            if not ns:
                continue
            body += [Heading(3, sub)] + ns + [ParagraphBreak()]
        if body:
            nodes += [Heading(2, sec)] + body
        if i == 1 and len(tbl) >= 3:
            nodes += [EvidenceTable(card_ids=tuple(tbl))]

    # ---- THE COHESION PASS. It runs on TYPED NODES, never on prose, and it may not touch a fact.
    # S2 Paragraph Cohesion = 4.90 is our LOWEST criterion and the judge named the cause: "fragmented
    # narrative... without adequate transitions". The cause is that 26 subsections were written by 26
    # independent calls, none of which could see the paragraph above it. This pass adds the OWNED
    # connective tissue those writers had no way to write — and it CANNOT do anything else: every
    # attributed node it returns is the same OBJECT it was handed (`_assert_frozen`, by identity), and
    # every sentence it writes goes back through `validate_report` before it may stand.
    nodes, coh = CP.apply(nodes, b)
    print(f'\n  COHESION PASS: +{coh.get("transitions_added", 0)} owned transitions, '
          f'+{coh.get("topics_added", 0)} topic sentences, '
          f'-{coh.get("owned_duplicates_deleted", 0)} duplicate owned sentences, '
          f'{coh.get("reordered_subsections", 0)} subsections reordered, '
          f'{coh.get("owned_refused_by_gate", 0)} of its own sentences REFUSED by the gate')

    DRAFTS.mkdir(parents=True, exist_ok=True)
    (DRAFTS / 'drops.json').write_text(json.dumps(all_dropped, indent=1))
    # THE LEDGER'S RECEIPT — a draft, never a release artifact. Who said what, where, in which role.
    (DRAFTS / 'fact_use_ledger.json').write_text(json.dumps(
        {f: {'work': r.work_id, 'narrations': len(r.narrations),
             'uses': [{'sub': u.subsection, 'role': u.role.value, 'mode': u.mode} for u in r.uses],
             'violations': r.violations()}
         for f, r in fact_records.items()}, indent=1))

    fails = validate_report(nodes, b)
    print(f'\n  AST: {len(nodes)} nodes | {len(fails)} unlawful | '
          f'{len(all_dropped)} sentences dropped by the contract')
    for d in all_dropped[:6]:
        print(f'     - {d[:110]}')
    if fails:
        print('\n** THE AST DOES NOT VALIDATE. NOTHING IS PUBLISHED. **')
        for f in fails[:10]:
            print(f'    - {f}')
        return 1

    if dry:
        # --dry proves the bindings and the WHOLE AST (now including the planner's deterministic
        # verdicts) without spending a token — and WITHOUT touching the sealed release.
        print(f'\n  --dry: {len(nodes)} nodes validated against the bytes; release left untouched.')
        return 0

    # ---- HAND IT TO THE PUBLISHER. THIS PROCESS CANNOT WRITE THE FILE ITSELF.
    meta = publisher.publish(nodes, b, provenance_of_inputs=dict(
        cards=str(cards_path), graph=str(graph_path), ledger=str(ledger_path)))
    print('\n' + '=' * 90)
    print('PUBLISHED — by the publisher, atomically, into a directory this process cannot write to')
    print('=' * 90)
    for k in ('report', 'sidecar', 'report_sha256', 'n_sentences', 'n_attributed_sentences',
              'n_clause_bindings', 'n_owned', 'n_table_rows', 'n_cards_cited', 'n_works_cited'):
        print(f'  {k:24}: {meta[k]}')
    return 0


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--cards', type=Path, default=ROOT / 'outputs' / 'evidence_cards_bound.json')
    ap.add_argument('--graph', type=Path, default=ROOT / 'outputs' / 'provenance_graph.json')
    ap.add_argument('--ledger', type=Path, default=ROOT / 'outputs' / 'event_ledger.jsonl')
    ap.add_argument('--policy', default='journal_articles_only', choices=sorted(POLICIES))
    ap.add_argument('--expect-cards-sha', default='')
    ap.add_argument('--expect-graph-sha', default='')
    ap.add_argument('--write', action='store_true')
    ap.add_argument('--dry', action='store_true', help='no LLM: prove the bindings and the AST only')
    a = ap.parse_args()
    if a.write or a.dry:
        raise SystemExit(write_report(a.cards, a.graph, a.ledger, a.policy,
                                      a.expect_cards_sha, a.expect_graph_sha, a.dry))
    print('use --write (or --dry)')
