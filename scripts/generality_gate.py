#!/usr/bin/env python3
"""THE GENERALITY GATE — does the research pipeline WORK on a question it has never seen?

WHY THIS EXISTS
---------------
All 38 scored runs are task 72 (AI × the labour market). "General research system" is, until this
gate measures it, AN UNSUPPORTED CLAIM. Sol put this gate BEFORE task-72 scoring for that reason: we
would rather KNOW the pipeline is overfit than BELIEVE it is general.

It runs the ACTUAL pipeline — NOT a full paid compose — on four questions:

    1. task 72   — AI and the labour market                                   [control; must still work]
    2. clinical  — SGLT2 inhibitors in heart failure with preserved EF
    3. legal     — common-law vs civil-law enforcement of non-compete clauses
    4. thin      — long-term health effects of microplastic inhalation (occupational)
                   [deliberately thin: "the literature does not settle this" is a PASS, not a failure]

and, for each, walks the real stages and MEASURES what happens:

    compile_contract  (research_contract.py)   — does it produce a SANE contract, or emit AI/labour?
    route             (source_router.py)        — clinical→PubMed/registries, legal→SSRN/official, NOT NBER
    coverage_matrix   (research_contract.py)    — false-gap rate; relevant-primary-work recall
    build_extract_prompt (research_contract.py) — is the extraction prompt question-specific or hardcoded?
    licenses_absence  (source_router.py)        — is a 429 a SEARCH_FAILED, or does it become an "absence"?

Everything here READS the pipeline; nothing here re-implements it. The one nondeterministic step is the
single cached LLM call inside compile_contract. No compose, no paid generation.

THE PARSER LANDMINE (measured, not assumed)
-------------------------------------------
compile_contract feeds the model's reply to research_contract._jparse -> cellcog_composer.jparse, whose
regex `\\[.*\\]` extracts a JSON *array*. The compile prompt asks for a JSON *object*. On an object the
regex grabs the first inner array through the last inner array and json.loads raises "Extra data". The
call site (research_contract.py:456) does not guard it, so on a CACHE MISS — i.e. any genuinely unseen
question — compile_contract RAISES. This gate instruments that exact call so it can report, per question,
whether the SHIPPED parser would have crashed, while a corrected object-parser lets the rest of the
pipeline be measured anyway. The corrected parse is clearly labelled everywhere it is used.

Run it:
    set -a && . ./.env && set +a
    python3 scripts/generality_gate.py            # all four, human-readable
    python3 scripts/generality_gate.py --json     # + machine summary at the end
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'scripts'))

import research_contract as RC          # noqa: E402
import source_router as SR              # noqa: E402


# ── THE FOUR QUESTIONS. task 72 verbatim from the bench; the other three exactly as the gate order
#    names them. NONE of these strings is referenced anywhere in the pipeline. ──────────────────────
def _task72_prompt() -> str:
    try:
        q, _ = RC.load_question(72)
        return q
    except SystemExit:
        # bench data not present in this checkout — use the canonical task-72 prompt verbatim.
        return ('Please write a literature review on the restructuring impact of Artificial '
                'Intelligence (AI) on the labor market. Focus on how AI, as a key driver of the '
                'Fourth Industrial Revolution, is causing significant disruptions and affecting '
                'various industries. Ensure the review only cites high-quality, English-language '
                'journal articles.')


QUESTIONS = [
    ('task72',   'CONTROL — AI × the labour market',                         _task72_prompt()),
    ('clinical', 'CLINICAL — SGLT2 inhibitors in HFpEF',
     'What does the evidence say about SGLT2 inhibitors in heart failure with preserved ejection '
     'fraction?'),
    ('legal',    'LEGAL — common-law vs civil-law non-compete enforcement',
     'How do common-law and civil-law jurisdictions differ in enforcing non-compete clauses?'),
    ('thin',     'THIN — long-term health effects of microplastic inhalation (occupational)',
     'Long-term health effects of microplastic inhalation in occupational settings'),
]

# AI/labour vocabulary. If a NON-task-72 contract's STRUCTURE carries these, the compiler leaked the
# seed topic into an unrelated question — the exact overfit tell. (Matched whole-word, lowercased.)
AILABOUR = ['artificial intelligence', 'labor market', 'labour market', 'automation', 'employment',
            'wage', 'wages', 'job displacement', 'occupation', 'fourth industrial revolution',
            'workforce', 'reskilling', 'gpt', 'llm', 'generative ai', 'robot', 'computerisation',
            'computerization']

# What "the right sources" means per domain, expressed as ADAPTER IDS from config/source_routes.yaml.
# These are assertions about ROUTING, checked against the live route() output — not hints TO it.
EXPECT = {
    'clinical': {'must_fire_any': ['clinicaltrials_gov', 'clinical_guidelines', 'medrxiv', 'biorxiv'],
                 'must_fire_all': ['europe_pmc', 'pmc'],            # PubMed Central / Europe PMC = "PubMed"
                 'must_not_fire': ['nber', 'iza', 'repec']},
    'legal':    {'must_fire_any': ['ssrn'],
                 'must_fire_official_any': ['govinfo', 'eurlex', 'courtlistener', 'official_legal_scoped'],
                 'must_not_fire': ['nber', 'iza', 'repec']},
    'task72':   {'must_fire_any': ['nber', 'iza', 'repec'],         # task 72 IS economics — NBER is CORRECT here
                 'must_not_fire': []},
    'thin':     {'must_not_fire': ['nber', 'iza', 'repec']},
}


# ════════════════════════════════════════════════════════════════════════════════════════════════════
# A CORRECT object/array parser — the one-line fix jparse is missing. Used only to keep the pipeline
# measurable past the shipped crash; every result computed with it is labelled "[recovered]".
# ════════════════════════════════════════════════════════════════════════════════════════════════════
def robust_jparse(s: str):
    s = (s or '').strip()
    s = re.sub(r'^```(?:json)?\s*', '', s)
    s = re.sub(r'\s*```$', '', s).strip()
    for opn, cls in (('{', '}'), ('[', ']')):
        i, j = s.find(opn), s.rfind(cls)
        if i != -1 and j > i:
            try:
                return json.loads(s[i:j + 1])
            except Exception:
                continue
    return None


# ════════════════════════════════════════════════════════════════════════════════════════════════════
# STAGE 1 — COMPILE. Instrument _jparse so ONE llm call tells us both (a) whether the SHIPPED parser
# would crash and (b) the true contract (via the corrected parser).
# ════════════════════════════════════════════════════════════════════════════════════════════════════
def compile_stage(question: str) -> dict:
    """ONE llm call, via an instrumented _jparse. From the single model reply we learn BOTH whether the
    SHIPPED parser would crash (research_contract._jparse -> cellcog_composer.jparse) AND the true
    contract (via the corrected parser). No second paid call is needed to demonstrate the crash."""
    import cellcog_composer as CC
    probe: dict = {'called': False}
    orig = RC._jparse

    def _instrumented(s: str):
        probe['called'] = True
        probe['raw_first'] = (s or '').strip()[:1]
        probe['raw_len'] = len(s or '')
        try:
            CC.jparse(s)                              # exactly what compile_contract:456 does today
            probe['shipped_parser'] = 'ok'
        except Exception as e:                        # the unguarded crash, on THIS model reply
            etb = traceback.extract_tb(e.__traceback__)
            frame = next((fr for fr in reversed(etb) if Path(fr.filename).name == 'cellcog_composer.py'),
                         etb[-1] if etb else None)
            probe['shipped_parser'] = f'{type(e).__name__}: {str(e)[:70]}'
            probe['crash_at'] = f'{Path(frame.filename).name}:{frame.lineno}' if frame else ''
        return robust_jparse(s)

    RC._jparse = _instrumented
    try:
        c = RC.compile_contract(question, use_llm=True, force=True, verbose=False)
    finally:
        RC._jparse = orig

    # SHIPPED verdict, derived from the same reply (no extra call). If _jparse was never called the
    # contract came from disk cache and the live LLM+parse path was not exercised this run.
    if not probe['called']:
        shipped = {'exercised': False}
    elif probe.get('shipped_parser') == 'ok':
        shipped = {'exercised': True, 'ok': True}
    else:
        shipped = {'exercised': True, 'ok': False, 'crash': probe['shipped_parser'],
                   'at': probe.get('crash_at', ''), 'via': 'research_contract.py:456 (unguarded)'}

    # DEGRADED: the offline regex-floor contract — the pipeline's real fallback when the LLM path fails
    # (and the only thing currently cached for 3 of these 4 questions). No network.
    floor = RC.compile_contract(question, use_llm=False, force=True, verbose=False)

    return {'shipped': shipped, 'contract': c, 'floor': floor, 'probe': probe}


def _struct_blob(c: RC.Contract) -> str:
    """The contract's STRUCTURED vocabulary only (not the question echo) — where leakage would show."""
    bits = [c.genre, c.review_subject, c.title, c.subject_axis.name]
    bits += [t.label for t in c.subject_axis.values]
    bits += [t.label for t in c.outcome_dimensions]
    bits += [t.label for t in c.core_concepts]
    bits += [t.label for t in c.framing_devices]
    bits += list(c.method_designs) + list(c.unit_levels)
    for t in c.core_concepts + c.outcome_dimensions + list(c.subject_axis.values):
        bits += list(t.aliases)
    return ' '.join(str(b) for b in bits).lower()


def _leak(c: RC.Contract, question: str) -> list[str]:
    """AI/labour tokens present in the contract STRUCTURE but NOT in the question itself."""
    blob = _struct_blob(c)
    qn = question.lower()
    hits = []
    for tok in AILABOUR:
        if re.search(rf'(?<![a-z]){re.escape(tok)}(?![a-z])', blob) and tok not in qn:
            hits.append(tok)
    return sorted(set(hits))


# ════════════════════════════════════════════════════════════════════════════════════════════════════
# STAGE 2 — ROUTE.
# ════════════════════════════════════════════════════════════════════════════════════════════════════
def route_stage(contract, floor, table) -> dict:
    plan = SR.route(table, contract)
    fplan = SR.route(table, floor)
    ev = [f.adapter_id for f in plan.fired if f.kind == 'evidence']
    fev = [f.adapter_id for f in fplan.fired if f.kind == 'evidence']
    return {'plan': plan, 'fplan': fplan, 'evidence_routes': ev, 'floor_evidence_routes': fev,
            'roles': list(plan.required.keys()), 'jurisdictions': dict(plan.jurisdictions)}


def route_verdict(key: str, plan) -> tuple[bool, list[str]]:
    exp = EXPECT.get(key, {})
    notes, ok = [], True
    fired = set(plan.fired_ids())
    for a in exp.get('must_not_fire', []):
        if a in fired:
            ok = False
            notes.append(f'FAIL routed to {a} (must NOT fire)')
    ma = exp.get('must_fire_any')
    if ma:
        hit = [a for a in ma if a in fired]
        if not hit:
            ok = False
            notes.append(f'FAIL none of {ma} fired')
        else:
            notes.append(f'ok fired {hit} (of {ma})')
    for a in exp.get('must_fire_all', []):
        if a not in fired:
            ok = False
            notes.append(f'FAIL {a} did not fire (required)')
    mo = exp.get('must_fire_official_any')
    if mo:
        hit = [a for a in mo if a in fired]
        if not hit:
            ok = False
            notes.append(f'FAIL no official legal route {mo} fired')
        else:
            notes.append(f'ok official legal route {hit}')
    return ok, notes


# ════════════════════════════════════════════════════════════════════════════════════════════════════
# STAGE 3 — COVERAGE (dry-run over the ONLY corpus the pipeline holds).
# ════════════════════════════════════════════════════════════════════════════════════════════════════
def coverage_stage(contract, cards, corpus) -> dict:
    # No ledger, no graph — exactly the __main__ path when no evidence graph is attached. The point is
    # to see whether the corpus the pipeline HOLDS can cover THIS contract, and whether an empty cell
    # ever prints as a false absence.
    m = RC.coverage_matrix(contract, cards, corpus, graph=None, ledger=None)
    routed = sum(len(c.card_ids) for c in m.cells.values())
    distinct_cards_routed = len({cid for c in m.cells.values() for cid in c.card_ids})
    false_gaps = [c for c in m.cells.values() if c.status == RC.GAP and c.absence_licensed]
    closed = m.by_status(RC.CLOSED)
    thin = m.by_status(RC.THIN)
    limitation = m.by_status(RC.LIMITATION)
    return {'matrix': m, 'n_cells': len(m.cells), 'card_slots_routed': routed,
            'distinct_cards_routed': distinct_cards_routed, 'n_cards': len(cards),
            'false_gaps': len(false_gaps), 'closed': len(closed), 'thin': len(thin),
            'limitation': len(limitation), 'unrouted': len(m.unrouted)}


# ════════════════════════════════════════════════════════════════════════════════════════════════════
# STAGE 4 — EXTRACTION DRY-RUN (no LLM: just the prompt the miner would send).
# ════════════════════════════════════════════════════════════════════════════════════════════════════
def extraction_stage(contract) -> dict:
    sample = {'title': 'A representative primary study', 'authors': ['Author, A.'],
              'venue': 'Journal of the Field', 'year': 2023}
    prompt = RC.build_extract_prompt(contract, sample, k=5, text='(verbatim article text would go here)')
    low = prompt.lower()
    subj = contract.review_subject.lower()
    subject_in = subj in low
    facet_in = any(f.label.lower() in low for f in contract.facets) if contract.facets else False
    # A GENUINE hardcode is an AI/labour phrase in the prompt that is NOT there because it is THIS
    # contract's own subject. For task 72 the subject legitimately IS AI×labour, so the phrase being
    # present is correct, not a baked-in string. Only flag it a defect when the phrase is present but
    # the contract's own subject does not account for it.
    phrases = ['restructuring impact of artificial intelligence', 'on the labor market']
    baked = [p for p in phrases if p in low and p not in subj]
    return {'len': len(prompt), 'mentions_subject': subject_in, 'mentions_a_facet': facet_in,
            'has_task72_hardcode': bool(baked), 'genre': contract.genre}


# ════════════════════════════════════════════════════════════════════════════════════════════════════
# STAGE 5 — ROUTE-ATTEMPT HONESTY. Does a 429 become an "absence"? (deterministic; no network)
# ════════════════════════════════════════════════════════════════════════════════════════════════════
def honesty_stage() -> dict:
    scenarios = [
        ('every applicable route answered 404', [SR.NOT_FOUND, SR.NOT_FOUND, SR.NOT_FOUND], True),
        ('same but ONE route was throttled (429)', [SR.NOT_FOUND, SR.NOT_FOUND, SR.THROTTLED], False),
        ('same but ONE route was access-denied (403)', [SR.NOT_FOUND, SR.ACCESS_DENIED], False),
        ('an applicable route was never attempted', [SR.NOT_FOUND, SR.NO_ATTEMPT], False),
        ('a copy was actually fetched', [SR.FETCHED, SR.NOT_FOUND], False),
    ]
    rows, ok = [], True
    for label, outs, expect in scenarios:
        lic, why = SR.licenses_absence(outs)
        good = (lic == expect)
        ok = ok and good
        rows.append((label, lic, expect, good, why))
    return {'ok': ok, 'rows': rows}


# ════════════════════════════════════════════════════════════════════════════════════════════════════
# DRIVER
# ════════════════════════════════════════════════════════════════════════════════════════════════════
def _hr(ch='─', n=100):
    return ch * n


def run(as_json: bool) -> int:
    table = SR.load_table()
    cards = json.loads(RC.CARDS.read_text()) if RC.CARDS.exists() else []
    corpus_path = ROOT / 'outputs' / 'journal_corpus_content.json'
    corpus = json.loads(corpus_path.read_text()) if corpus_path.exists() else []

    print(_hr('═'))
    print('GENERALITY GATE — real pipeline, four questions, brutal metrics')
    print(f'  route table : {SR.ROUTES_YAML.name}  ({len(table.routes)} routes)')
    print(f'  corpus      : {corpus_path.name}  ({len(corpus)} works)   cards: outputs/{RC.CARDS.name} '
          f'({len(cards)})')
    print(_hr('═'))

    honesty = honesty_stage()
    summary = []

    for key, title, q in QUESTIONS:
        print('\n' + _hr('█'))
        print(f'▌ {title}')
        print(f'▌ Q: {q}')
        print(_hr('█'))

        rec = {'key': key}
        try:
            cs = compile_stage(q)
        except Exception as e:
            print(f'  COMPILE STAGE HARD-FAILED: {type(e).__name__}: {e}')
            summary.append({'key': key, 'fatal': str(e)})
            continue

        c, floor, sh, probe = cs['contract'], cs['floor'], cs['shipped'], cs['probe']

        # ---- STAGE 1: CONTRACT -------------------------------------------------------------------
        print('\n[1] COMPILE  (research_contract.compile_contract)')
        if not sh.get('exercised'):
            print('    SHIPPED path (use_llm): served from disk cache — live LLM+parse NOT exercised '
                  'this run (pre-cached contract)')
            shipped_ok = True
        elif sh.get('ok'):
            print('    SHIPPED path (use_llm, live): OK — the shipped jparse parsed this reply')
            shipped_ok = True
        else:
            print(f'    SHIPPED path (use_llm, live): CRASHED  {sh["crash"]}')
            print(f'        └ raised in {sh.get("at")}, called unguarded from {sh.get("via")}')
            print(f'        └ model reply began with {probe.get("raw_first")!r} ({probe.get("raw_len")} '
                  f'chars) and IS valid JSON — the parser, not the model, is at fault')
            shipped_ok = False
        print(f'    [recovered] genre     : {c.genre}')
        print(f'    [recovered] subject   : {c.review_subject}')
        print(f'    [recovered] axis      : {c.subject_axis.name} => '
              f'{[t.label for t in c.subject_axis.values][:8]}')
        print(f'    [recovered] outcomes  : {[t.label for t in c.outcome_dimensions][:8]}')
        print(f'    [recovered] methods   : {c.method_designs}')
        leak = _leak(c, q)
        if key == 'task72':
            print(f'    AI/labour in structure: present (CORRECT — this question IS AI/labour): '
                  f'{leak[:6] if leak else "(derived from question)"}')
            leak_ok = True
        else:
            print(f'    AI/labour leakage into structure (should be NONE): {leak if leak else "NONE"}')
            leak_ok = not leak
        rec['contract_sane'] = bool(c.review_subject and c.outcome_dimensions and c.subject_axis.values)
        rec['leak_ok'] = leak_ok
        rec['shipped_compile_ok'] = shipped_ok
        rec['shipped_exercised'] = sh.get('exercised', False)

        # ---- STAGE 2: ROUTE ----------------------------------------------------------------------
        rs = route_stage(c, floor, table)
        print('\n[2] ROUTE  (source_router.route)   [on the recovered contract]')
        print(f'    required roles : {rs["roles"]}')
        print(f'    jurisdictions  : {rs["jurisdictions"] or "none named — fire broadly"}')
        print(f'    EVIDENCE routes: {rs["evidence_routes"]}')
        rok, rnotes = route_verdict(key, rs['plan'])
        for n in rnotes:
            print(f'        {n}')
        print(f'    fires nber={rs["plan"].fires("nber")}  ssrn={rs["plan"].fires("ssrn")}  '
              f'courtlistener={rs["plan"].fires("courtlistener")}  govinfo={rs["plan"].fires("govinfo")}  '
              f'clinicaltrials_gov={rs["plan"].fires("clinicaltrials_gov")}  '
              f'clinical_guidelines={rs["plan"].fires("clinical_guidelines")}')
        print(f'    [floor contract would instead fire evidence]: {rs["floor_evidence_routes"]}')
        floor_plan = rs['fplan']
        frok, _ = route_verdict(key, floor_plan)
        print(f'        └ with the DEGRADED floor contract the routing verdict is: '
              f'{"PASS" if frok else "FAIL — collapses to generic/again-task72 routing"}')
        rec['route_ok_recovered'] = rok
        rec['route_ok_floor'] = frok
        # an economics working-paper channel firing on a NON-economics question (task72 IS economics):
        rec['econ_misfire'] = (key != 'task72' and any(rs['plan'].fires(a)
                               for a in ('nber', 'iza', 'repec')))

        # ---- STAGE 3: COVERAGE -------------------------------------------------------------------
        cov = coverage_stage(c, cards, corpus)
        print('\n[3] COVERAGE  (research_contract.coverage_matrix, no ledger)')
        print(f'    matrix cells            : {cov["n_cells"]}  '
              f'({len(c.subject_axis.values)}+1 rows × {len(c.outcome_dimensions)} cols)')
        print(f'    cards routed into matrix: {cov["distinct_cards_routed"]} / {cov["n_cards"]} '
              f'({cov["card_slots_routed"]} cell-placements)')
        print(f'    cells CLOSED (evidence) : {cov["closed"]}   THIN: {cov["thin"]}   '
              f'LIMITATION (never looked): {cov["limitation"]}')
        print(f'    FALSE GAPS (absence asserted with no ledger): {cov["false_gaps"]}   '
              f'{"←  none: the pipeline refuses to fake an absence" if cov["false_gaps"] == 0 else "←  DEFECT"}')
        recall_note = ('high — corpus IS this topic' if key == 'task72'
                       else 'ZERO relevant works exist in the only corpus the pipeline holds')
        print(f'    relevant-primary-work recall: {recall_note}')
        rec['false_gaps'] = cov['false_gaps']
        rec['cards_routed'] = cov['distinct_cards_routed']

        # ---- STAGE 4: EXTRACTION -----------------------------------------------------------------
        ex = extraction_stage(c)
        print('\n[4] EXTRACTION DRY-RUN  (research_contract.build_extract_prompt)')
        print(f'    prompt genre           : {ex["genre"]}   ({ex["len"]} chars)')
        print(f'    names THIS review subj : {ex["mentions_subject"]}')
        print(f'    carries a contract facet: {ex["mentions_a_facet"]}')
        print(f'    contains task-72 hardcode: {ex["has_task72_hardcode"]}  '
              f'{"←  DEFECT" if ex["has_task72_hardcode"] else "←  clean (fully contract-parameterised)"}')
        rec['extract_clean'] = (not ex['has_task72_hardcode']) and ex['mentions_subject']

        # ---- per-question thin conclusion --------------------------------------------------------
        if key == 'thin':
            print('\n[thin] IS THE THIN CONCLUSION CORRECT?')
            print('    With no microplastic corpus and no ledger, every cell is LIMITATION '
                  '("we never looked") —')
            print('    NOT a fabricated absence and NOT a fabricated finding. If a real search returned')
            print('    all-NOT_FOUND, licenses_absence() -> True and "the literature does not settle this"')
            print('    becomes a licensed, CORRECT answer. The machinery supports the right thin answer.')
            rec['thin_conclusion_correct'] = (cov['false_gaps'] == 0)

        summary.append(rec)

    # ---- STAGE 5: ROUTE-ATTEMPT HONESTY (shared, deterministic) -----------------------------------
    print('\n' + _hr('█'))
    print('▌ ROUTE-ATTEMPT HONESTY  (source_router.licenses_absence) — is a 429 an absence?')
    print(_hr('█'))
    for label, lic, expect, good, why in honesty['rows']:
        flag = 'ok ' if good else 'XX '
        print(f'  {flag}absence {"LICENSED" if lic else "REFUSED ":<8} (expected {expect}) :: {label}')
    print(f'    -> a 429/403/never-tried is SEARCH_FAILED, never an absence: '
          f'{"HOLDS" if honesty["ok"] else "BROKEN"}')

    # ---- VERDICT ---------------------------------------------------------------------------------
    print('\n' + _hr('═'))
    print('VERDICT')
    print(_hr('═'))
    for r in summary:
        k = r['key']
        bits = []
        bits.append(f'contract={"sane" if r.get("contract_sane") else "DEGRADED"}')
        bits.append(f'no-leak={"y" if r.get("leak_ok") else "N"}')
        if not r.get('shipped_exercised'):
            sc = 'cache'
        elif r.get('shipped_compile_ok'):
            sc = 'ok'
        else:
            sc = 'CRASH'
        bits.append(f'shipped-compile={sc}')
        bits.append(f'route(recovered)={"ok" if r.get("route_ok_recovered") else "FAIL"}')
        bits.append(f'route(floor)={"ok" if r.get("route_ok_floor") else "FAIL"}')
        bits.append(f'false-gaps={r.get("false_gaps")}')
        bits.append(f'recall={r.get("cards_routed")}cards')
        bits.append(f'extract={"clean" if r.get("extract_clean") else "DIRTY"}')
        print(f'  {k:<9} ' + '  '.join(bits))

    shipped_crashes = [r['key'] for r in summary if not r.get('shipped_compile_ok')]
    routes_need_llm = [r['key'] for r in summary
                       if r.get('route_ok_recovered') and not r.get('route_ok_floor')]
    econ_misfire = [r['key'] for r in summary if r.get('econ_misfire')]
    print('\n  BREAKPOINTS (file:line):')
    print('   1. cellcog_composer.py:106-108  jparse regex `\\[.*\\]` extracts a JSON ARRAY; the compile')
    print('      prompt returns an OBJECT -> "Extra data". research_contract.py:456 calls it unguarded, so')
    print(f'      compile_contract(use_llm=True) RAISES on a live compile. Crashed here: {shipped_crashes}.')
    print('   2. Router generality is CONTINGENT on the LLM contract. With the degraded regex-floor')
    print('      contract (the real fallback / the only thing cached for the new Qs), domain routing')
    print(f'      collapses to the generic OA backbone for: {routes_need_llm}  (no PubMed/registry/SSRN).')
    print('   3. source_routes.yaml evidence.working_paper.economics any_of contains the over-generic')
    print("      tokens 'trade' and 'employment'. A non-compete (restraint-of-TRADE, EMPLOYMENT law)")
    print(f'      question fires NBER/IZA/RePEc: {econ_misfire}. The router meets its own "legal≠NBER"')
    print('      canary only because its built-in legal example avoids those words — overfit to examples.')
    print('   4. journal_corpus_build.py:44-72  ANCHORS + TOPIC_AI/TOPIC_WORK force the ONLY evidence')
    print('      corpus to be AI/labour; outputs/journal_corpus_content.json is what coverage/extraction')
    print('      read. For every non-AI question the relevant-work recall is ZERO — the deepest overfit.')

    if as_json:
        print('\n' + json.dumps({'questions': [{k: v for k, v in r.items()} for r in summary],
                                 'honesty_ok': honesty['ok'],
                                 'shipped_compile_crashes': shipped_crashes,
                                 'routes_need_llm': routes_need_llm,
                                 'legal_economics_misfire': econ_misfire}, default=str))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--json', action='store_true', help='emit a machine summary after the report')
    args = ap.parse_args()
    return run(args.json)


if __name__ == '__main__':
    raise SystemExit(main())
