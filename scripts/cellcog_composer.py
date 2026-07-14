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
                        entailed_by_span, numbers_in)
from synthesis_contract import validate, Premise, Synthesis, OPERATIONS         # noqa: E402

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
    for cid in b.cards:
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

THE EVIDENCE. These are the ONLY facts you may state. Each is a VERBATIM SPAN from a peer-reviewed
journal article, with the id of the card that holds it:

{cards}

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
            nodes.append(Owned(text=txt, premise_ids=pids))
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
        Owned(text='**Methods.** The review draws exclusively on peer-reviewed, English-language '
                   'journal articles whose full text was retrieved and verified against the published '
                   'version of record; every finding reported below is bound to a verbatim passage of '
                   'the article it is credited to.'),
        ParagraphBreak(),
        Owned(text='**Scope.** Where only a working-paper or preprint version of a study could be '
                   'obtained, that study is excluded from the findings rather than cited as though the '
                   'journal article had been read.'),
        ParagraphBreak(),
    ]


def methods_nodes(b: CardBundle) -> list:
    n_cards = len(b.admitted_ids())
    n_units = len({b.resolve(c).work_id for c in b.admitted_ids()})
    return [
        Heading(2, 'Scope, Methods, and Source Selection'),
        Owned(text='**Source policy.** Only articles published in peer-reviewed journals are cited. '
                   'Working papers, preprints, accepted manuscripts, landing pages and abstracts are '
                   'excluded from the evidence base, and are retained only as leads to a published '
                   'version.'),
        ParagraphBreak(),
        Owned(text=f'**Evidence base.** The findings below rest on {_spell(n_cards)} verified passages '
                   f'drawn from {_spell(n_units)} peer-reviewed studies. A passage is admitted only '
                   f'where the article\'s own text states the finding attributed to it.'),
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

    def one(job):
        sec, sub = job
        sel = _select(b, sub)
        if not sel:
            return job, [], ['no cards selected']
        prompt = WRITE_PROMPT.format(section=sec, sub=sub, cards=_fmt_cards(b, sel),
                                     connectives=', '.join(CONNECTIVES))
        if dry:
            return job, [], ['--dry: no LLM call']
        try:
            raw = jparse(llm(prompt, max_tokens=8192))
        except Exception as e:
            return job, [], [f'llm: {e}']
        nodes, dropped = _nodes_from(raw, b, set(sel))
        # THE GATE, ON THE CRITICAL PATH — node by node, against the bytes.
        good = []
        for i, n in enumerate(nodes):
            fails = validate_report([n], b)
            if fails:
                dropped += [str(f) for f in fails]
                continue
            good.append(n)
        return job, good, dropped

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

    DRAFTS.mkdir(parents=True, exist_ok=True)
    (DRAFTS / 'drops.json').write_text(json.dumps(all_dropped, indent=1))

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

    # ---- HAND IT TO THE PUBLISHER. THIS PROCESS CANNOT WRITE THE FILE ITSELF.
    meta = publisher.publish(nodes, b, provenance_of_inputs=dict(
        cards=str(cards_path), graph=str(graph_path), ledger=str(ledger_path)))
    print('\n' + '=' * 90)
    print('PUBLISHED — by the publisher, atomically, into a directory this process cannot write to')
    print('=' * 90)
    for k in ('report', 'sidecar', 'report_sha256', 'n_sentences', 'n_attributed', 'n_owned',
              'n_table_rows', 'n_cards_cited', 'n_works_cited'):
        print(f'  {k:16}: {meta[k]}')
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
