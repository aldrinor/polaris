#!/usr/bin/env python3
"""SOL'S RELEASE-BOUNDARY ATTACK (b) — END TO END, THROUGH THE REAL SUBMISSION COMMAND.

    "The test must attack THE PRODUCTION RELEASE BOUNDARY, not import a gate or inspect an AST."
    "THE ATTACK MUST RUN THE SAME SUBMISSION COMMAND USED FOR SCORING — not a helper, not an import,
     not a reimplementation."

Everything else in this repo tests the boundary by importing `publisher` and calling `publish()` in
process (`test_release_boundary.py`) or by walking the composer's AST (`test_gate_is_wired.py`). Tonight
proved that a green in-process check can sit on top of a live fabrication, because the check certifies a
LANE and the fabrication moves lanes. So this test does the one thing those cannot: it launches

    python scripts/cellcog_composer.py --write --cards <POISON> --graph <POISON> --policy journal_articles_only

as a SUBPROCESS, in a SEALED TEMPORARY RUN DIRECTORY, against a poisoned fixture, and then asserts ONLY on
the bytes that land in <run>/outputs/release/report.md — the file the grader would read.

TWO — AND ONLY TWO — HONEST DEVIATIONS FROM A BARE PRODUCTION INVOCATION, STATED UP FRONT:
  1. THE RUN DIRECTORY IS A TEMP COPY of scripts/ (+ a stub model, see #2). It has to be: the boundary is
     `<ROOT>/outputs/release` and ROOT is derived from `publisher.py.__file__`, so the only way to get a
     sealed temp release dir — and the only way NOT to clobber the real candidate release — is to run the
     byte-identical command from a temp ROOT. The composer, publisher, provenance loader and AST validator
     are copied VERBATIM from this repo; the CLI is identical.
  2. THE EXTERNAL MODEL IS REPLACED BY AN ADVERSARIAL STUB. The real generator is a network service that
     cannot be made deterministic offline, and — more to the point — the boundary must hold against a
     HOSTILE model, not a cooperative one. The stub reads the exact prompt the real model gets and answers
     with every attack it can: the working-paper span smuggled under a journal card, a fabricated figure,
     a clause naming a source, a citation of the refused P0 card, an OWNED sentence carrying a number, an
     OWNED sentence naming a source, and a research-gap claim that no premise derives. If any of that
     reaches report.md, the boundary has failed. Nothing else about the submission is stubbed.

WHAT IS NOT STUBBED: the graph is loaded by the real strict `provenance.Graph.from_json`; every card is
resolved by the real `CardBundle.resolve`; every node is validated by the real `report_ast.validate_report`;
the file is written by the real `publisher.publish` through the real 0555 write-bit boundary; and the
released file is re-audited by the real `publisher.py --verify` in a separate process.

    python scripts/test_release_e2e_attack.py                # the full attack
    python scripts/test_release_e2e_attack.py --check-fixture # just build+load the fixture and report
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

REAL_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REAL_ROOT / 'scripts'))

import provenance as P  # noqa: E402  (the REAL module — used ONLY to BUILD the fixture, never to gate)

# ================================================================================================
# DISTINCTIVE STRINGS. The attack asserts on the PRESENCE of #1 and the ABSENCE of the rest, IN THE
# RELEASED FILE. Every one is chosen so a substring test cannot false-positive on ordinary prose.
# ================================================================================================
POS_SPAN = ('the local employment-to-population ratio rose by 1.5 points in regions that adopted the '
            'technology')
# SPAN-ONLY: this phrase is in the verbatim SPAN but NOT in the card's `claim`, so its presence proves
# the SPAN reached a BODY attributed sentence — not merely the claim reaching the evidence table.
POS_PROBE = 'regions that adopted the technology'                        # MUST appear (positive control)

WP_SPAN = 'employment falls by 0.2 percentage points per robot per thousand workers'  # MUST NOT appear
WP_PROBE = '0.2 percentage points per robot'
FABRICATED = '47 percent of all jobs are at imminent risk'              # MUST NOT appear
GAP_PROBE = 'welding automation in the Bavarian'                        # MUST NOT appear (underived gap)
OWNED_NUM_PROBE = 'true displacement effect at roughly 25 percent'      # MUST NOT appear
NAMED_SOURCE = 'Acemoglu'                                               # MUST NOT appear anywhere

_FILLER = ('The paper proceeds as follows. We describe the data, the identification strategy and the '
           'estimation. ') * 120     # clears the 1,200-word scholarly stub floor -> a COMPLETE document


# ================================================================================================
# THE FIXTURE. Built with the REAL provenance API so its bytes truly bind and its graph survives the
# strict `from_json` loader the production command runs. Returns (Graph, {name: card_dict}).
# ================================================================================================

def build() -> tuple[P.Graph, dict[str, dict]]:
    g = P.Graph()

    def work(wid, authors, year, venue, doi, title='A study', kind='study'):
        g.works[wid] = P.Work(id=wid, title=title, authors=authors, year=year, venue=venue, doi=doi,
                              kind=kind)

    def expr(eid, wid, kind):
        g.expressions[eid] = P.Expression(id=eid, work_id=wid, kind=kind, kind_basis='fixture',
                                          attribution=P._attribution_for(kind, g.works[wid]))

    def manif(mid, eid, wid, text, artifact_kind, complete):
        g.manifestations[mid] = P.Manifestation(
            id=mid, expression_id=eid, work_id=wid, text=text,
            content_hash=hashlib.sha256(text.encode()).hexdigest(), n_words=len(text.split()),
            locator='http://example/x', locator_status='RECORDED', fetched_by='fixture',
            text_field='fulltext',
            profile=dict(artifact_kind=artifact_kind, complete=complete,
                         extractability=P.extractability(text),
                         incomplete_because=([] if complete else [f'`{artifact_kind}` cannot bear a finding'])))

    def scholarly(mid, eid, wid, span, kind='journal_article'):
        manif(mid, eid, wid, _FILLER + span + ' ' + _FILLER, kind, complete=True)

    # ---- FOUR CLEAN JOURNAL ARTICLES (positive controls; admitted under journal-only) --------------
    work('w:card', ['Bloom', 'Draca'], 2021, 'American Economic Review', '10.1/card')
    expr('e:card:j', 'w:card', 'journal_version')
    scholarly('m:card', 'e:card:j', 'w:card', POS_SPAN)

    work('w:noy', ['Noy', 'Zhang'], 2023, 'Science', '10.1/noy')
    expr('e:noy:j', 'w:noy', 'journal_version')
    scholarly('m:noy', 'e:noy:j', 'w:noy',
              'generative writing assistance raised task output by 40 percent among treated participants')

    work('w:autor', ['Autor', 'Levy', 'Murnane'], 2003, 'The Quarterly Journal of Economics', '10.1/a')
    expr('e:autor:j', 'w:autor', 'journal_version')
    scholarly('m:autor', 'e:autor:j', 'w:autor',
              'computer capital substitutes for workers in carrying out a well-defined set of routine tasks')

    work('w:web', ['Webb', 'Kraft'], 2020, 'ILR Review', '10.1/web')
    expr('e:web:j', 'w:web', 'journal_version')
    scholarly('m:web', 'e:web:j', 'w:web',
              'occupational exposure to language modeling reached 32 percent at the upper end of the range')

    # ---- THE P0: working-paper bytes wearing a journal's name --------------------------------------
    # metadata venue = Journal of Political Economy; the bytes are the NBER working paper.
    work('w:ar', ['Acemoglu', 'Restrepo'], 2020, 'Journal of Political Economy', '10.1086/705716')
    expr('e:ar:wp', 'w:ar', 'working_paper')
    expr('e:ar:j', 'w:ar', 'journal_version')          # the journal version EXISTS; we hold NO byte of it
    scholarly('m:ar', 'e:ar:wp', 'w:ar', WP_SPAN, kind='working_paper')

    # ---- THE LANDING PAGE carrying a genuine article phrase (Frey & Osborne ORA web page) -----------
    fo_text = ('About 47 percent of total US employment is at risk of computerisation according to the '
               'estimates reported here. Download the full text as a PDF. Accept all cookies to continue. '
               'Oxford University Research Archive record.')
    work('w:fo', ['Frey', 'Osborne'], 2013, 'Technological Forecasting and Social Change', '10.1/fo')
    expr('e:fo:x', 'w:fo', 'unknown')
    manif('m:fo', 'e:fo:x', 'w:fo', fo_text, 'landing_page', complete=False)

    # ---- CARDS -------------------------------------------------------------------------------------
    def card(cid, mid, span, claim, **over):
        m = g.manifestations[mid]
        s = m.text.index(span)
        b = g.bind_span(mid, s, s + len(span))
        att = g.resolve_attribution(mid, P.JOURNAL_ONLY)
        w = g.works[m.work_id]
        d = dict(id=cid, manifestation_id=mid, content_hash=b['content_hash'],
                 span_start=s, span_end=s + len(span), span_raw=b['text'], span=span, claim=claim,
                 expression_id=b['expression_id'],
                 permitted_expression_ids=list(b['permitted_expression_ids']),
                 attribution_target_expression_id=att.names_expression_id,
                 work_id=m.work_id, evidence_unit_id=m.work_id, authors=w.authors, year=w.year,
                 venue=w.venue, level=over.get('level', 'firm'), horizon='long-run',
                 method='observational', mechanisms=over.get('mechanisms', []), corroborating_sources=[],
                 source_version=m.content_hash[:12], text_field='fulltext')
        for k, v in over.items():
            if k in ('level', 'mechanisms'):
                continue
            d[k] = v
        return d

    cards: dict[str, dict] = {}
    # positive controls
    cards['c:pos'] = card('c:pos', 'm:card', POS_SPAN,
                          'The local employment-to-population ratio rose by 1.5 points in adopting regions.',
                          level='region', industry='manufacturing')
    cards['c:noy'] = card('c:noy', 'm:noy',
                          'generative writing assistance raised task output by 40 percent among treated participants',
                          'Generative writing assistance raised task output by 40 percent.',
                          level='task', technology='generative')
    cards['c:autor'] = card('c:autor', 'm:autor',
                            'computer capital substitutes for workers in carrying out a well-defined set of routine tasks',
                            'Computer capital substitutes for workers in routine tasks.',
                            level='occupation', industry='services')
    cards['c:web'] = card('c:web', 'm:web',
                          'occupational exposure to language modeling reached 32 percent at the upper end of the range',
                          'Occupational exposure to language modeling reached 32 percent.',
                          level='occupation', technology='language')

    # THE P0 — valid hash, complete bytes, IMPERMISSIBLE journal attribution (it is a working paper)
    cards['c:p0'] = card('c:p0', 'm:ar', WP_SPAN,
                         'Employment falls 0.2 percentage points per robot per thousand workers.',
                         level='region')

    # THE LANDING PAGE cited as an article
    cards['c:landing'] = card('c:landing', 'm:fo',
                              'About 47 percent of total US employment is at risk of computerisation',
                              'About 47 percent of US employment is at risk of computerisation.')

    # CARD-LEVEL POISONS (the graph is valid; the CARD lies) ------------------------------------------
    # no manifestation_id -> a DOI names a work, and a work has no bytes
    noid = card('c:noid', 'm:card', POS_SPAN, 'A finding with no bytes behind it.')
    noid['manifestation_id'] = ''
    noid['content_hash'] = ''
    cards['c:noid'] = noid
    # wrong hash -> the span binds to nothing
    wrong = card('c:wrhash', 'm:card', POS_SPAN, 'A finding whose hash does not match its bytes.')
    wrong['content_hash'] = 'deadbeef' * 8
    cards['c:wrhash'] = wrong
    # invalid / stale attribution target -> card claims to name an expression the graph does not resolve
    stale = card('c:staletarget', 'm:card', POS_SPAN, 'A finding pointing at the wrong expression.')
    stale['attribution_target_expression_id'] = 'e:noy:j'
    cards['c:staletarget'] = stale

    return g, cards


EXPECTED_REFUSAL = {
    'c:p0': 'SOURCE_POLICY', 'c:landing': 'SOURCE_POLICY', 'c:noid': 'CARD_IS_UNBOUND',
    'c:wrhash': 'SPAN_DOES_NOT_VERIFY', 'c:staletarget': 'STALE_ATTRIBUTION_TARGET',
}
ADMITTED = ['c:pos', 'c:noy', 'c:autor', 'c:web']


# ================================================================================================
# SERIALISATION + THE SEALED TEMP RUN DIRECTORY
# ================================================================================================

def write_fixture(g: P.Graph, cards: list[dict], out_dir: Path, tag: str) -> tuple[Path, Path]:
    gp = out_dir / f'{tag}.graph.json'
    cp = out_dir / f'{tag}.cards.json'
    gp.write_text(json.dumps(g.to_json(), indent=1))
    cp.write_text(json.dumps(cards, indent=1))
    return cp, gp


FAKE_MODEL = r'''
"""ADVERSARIAL MODEL STUB — it answers the composer's real prompt with every attack it can mount."""
import json, re


class OpenRouterClient:
    def __init__(self, *a, **k):
        pass

    async def close(self):
        pass

    async def generate(self, prompt="", **k):
        ids = re.findall(r"(?m)^card_id:\s*(\S+)", prompt)
        spans = re.findall(r'THE SOURCE SAYS[^"]*"([^"]*)"', prompt)
        span_of = dict(zip(ids, spans))
        arr = []
        # (1) CLEAN, SURVIVING sentences: echo each offered card's own verbatim span (guaranteed entailed).
        for cid in ids:
            sp = span_of.get(cid, "")
            if sp:
                arr.append({"voice": "ATTRIBUTED", "clauses": [{"card_id": cid, "text": sp}],
                            "connective": "while"})
        first = ids[0] if ids else None
        if first:
            # (2) the WORKING-PAPER span, smuggled under a JOURNAL card id
            arr.append({"voice": "ATTRIBUTED", "clauses": [{"card_id": first,
                        "text": "employment falls by 0.2 percentage points per robot per thousand workers"}]})
            # (3) a FABRICATED figure under a journal card
            arr.append({"voice": "ATTRIBUTED", "clauses": [{"card_id": first,
                        "text": "about 47 percent of all jobs are at imminent risk of automation"}]})
            # (4) a clause that NAMES A SOURCE (attribution must come from the graph, never the model)
            arr.append({"voice": "ATTRIBUTED", "clauses": [{"card_id": first,
                        "text": "Acemoglu and Restrepo show that robots sharply reduce local employment"}]})
        # (5) cite the REFUSED P0 card directly
        arr.append({"voice": "ATTRIBUTED", "clauses": [{"card_id": "c:p0",
                    "text": "employment falls by 0.2 percentage points per robot per thousand workers"}]})
        # (6) an OWNED sentence carrying a NEW PARTICULAR (a number)
        arr.append({"voice": "OWNED", "premise_ids": ids[:2],
                    "text": "The reviewer puts the true displacement effect at roughly 25 percent."})
        # (7) an OWNED sentence NAMING A SOURCE
        arr.append({"voice": "OWNED", "premise_ids": ids[:2],
                    "text": "Acemoglu is plainly correct that automation dominates reinstatement."})
        # (8) a research-GAP claim no premise derives (a fabricated new entity)
        arr.append({"voice": "OWNED", "premise_ids": ids[:2],
                    "text": "No study has yet examined welding automation in the Bavarian Mittelstand."})
        return json.dumps(arr)
'''


def make_run_dir(with_model: bool) -> Path:
    tmp = Path(tempfile.mkdtemp(prefix='rb_run_'))
    shutil.copytree(REAL_ROOT / 'scripts', tmp / 'scripts',
                    ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    # `provenance.py` imports `evidence_miner`, which reads config/evidence_acts.json at load; the real
    # submission command reads config/ too. A faithful run dir mirrors it, verbatim, from the repo.
    shutil.copytree(REAL_ROOT / 'config', tmp / 'config',
                    ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    (tmp / 'outputs').mkdir()
    if with_model:
        llm = tmp / 'src' / 'polaris_graph' / 'llm'
        llm.mkdir(parents=True)
        for pkg in (tmp / 'src', tmp / 'src' / 'polaris_graph', llm):
            (pkg / '__init__.py').write_text('')
        (llm / 'openrouter_client.py').write_text(FAKE_MODEL)
    return tmp


def run_composer(run_dir: Path, cards: Path, graph: Path, policy='journal_articles_only', timeout=300):
    env = dict(os.environ, OPENROUTER_API_KEY='', PYTHONDONTWRITEBYTECODE='1')
    return subprocess.run(
        [sys.executable, str(run_dir / 'scripts' / 'cellcog_composer.py'), '--write',
         '--cards', str(cards), '--graph', str(graph), '--ledger', str(run_dir / 'outputs' / 'nope.jsonl'),
         '--policy', policy],
        cwd=str(run_dir), env=env, capture_output=True, text=True, timeout=timeout)


# ================================================================================================
# THE LEDGER
# ================================================================================================
FAILS: list[str] = []
NOTES: list[str] = []


def check(name: str, ok: bool, detail: str = ''):
    print(f"  [{'PASS' if ok else '**FAIL**'}] {name}")
    if detail and not ok:
        print(f'            {detail}')
    if not ok:
        FAILS.append(name)


def released(run_dir: Path) -> Path:
    return run_dir / 'outputs' / 'release' / 'report.md'


# ================================================================================================
def check_fixture_only():
    """Build the fixture, round-trip it through the STRICT loader, and print what resolves."""
    g, cards = build()
    d = Path(tempfile.mkdtemp(prefix='rb_fix_'))
    cp, gp = write_fixture(g, list(cards.values()), d, 'mixed')
    print(f'fixture written: {cp}\n                 {gp}')
    g2 = P.Graph.from_json(json.loads(gp.read_text()))       # the strict loader the composer runs
    print(f'graph reloaded through strict from_json: {len(g2.works)} works, '
          f'{len(g2.manifestations)} manifestations')
    from report_ast import CardBundle
    b = CardBundle(list(cards.values()), g2, P.JOURNAL_ONLY)
    print('\ncard resolution under journal_articles_only:')
    for cid in cards:
        r = b.resolve(cid)
        print(f'  {cid:16} {"ADMIT " if r.ok else "REFUSE"}  {(r.refusal or "")[:80]}')
    return g2, b


def main():
    if '--check-fixture' in sys.argv:
        check_fixture_only()
        return 0

    print('=' * 96)
    print('RELEASE-BOUNDARY ATTACK — through `cellcog_composer.py --write`, in a sealed temp run dir')
    print('=' * 96)

    g, cards = build()

    # =============================================================================================
    # PART A — FAIL CLOSED. Each poison, ALONE, must produce NONZERO EXIT and NO released report.md.
    #          (fresh temp dir each time, so "no report.md" is unambiguous.)
    # =============================================================================================
    print('\n-- PART A: a poisoned card, alone, cannot produce a release ---------------------------')
    single = {
        'NO manifestation_id': 'c:noid',
        'WRONG content hash': 'c:wrhash',
        'invalid/stale attribution target': 'c:staletarget',
        'working-paper bytes under a journal name (P0)': 'c:p0',
        'landing page cited as an article': 'c:landing',
    }
    for label, cid in single.items():
        rd = make_run_dir(with_model=False)
        try:
            cp, gp = write_fixture(g, [cards[cid]], rd, 'solo')
            r = run_composer(rd, cp, gp)
            no_release = not released(rd).exists()
            check(f'[{cid}] {label}: NONZERO EXIT and NO released report.md',
                  r.returncode != 0 and no_release,
                  f'rc={r.returncode} release_exists={not no_release}\n            '
                  f'{(r.stdout + r.stderr).strip()[-300:]}')
        finally:
            shutil.rmtree(rd, ignore_errors=True)

    # A contaminated manifestation IN THE GRAPH (bytes edited after hashing) must fail to LOAD.
    rd = make_run_dir(with_model=False)
    try:
        cp, gp = write_fixture(g, [cards['c:pos']], rd, 'corrupt')
        gj = json.loads(gp.read_text())
        for m in gj['manifestations']:
            if m['id'] == 'm:card':
                m['text'] = m['text'] + ' TAMPERED'          # hash no longer matches the bytes
        gp.write_text(json.dumps(gj))
        r = run_composer(rd, cp, gp)
        check('contaminated manifestation (bytes != hash): the STRICT loader refuses, NONZERO EXIT, no release',
              r.returncode != 0 and not released(rd).exists(),
              f'rc={r.returncode}\n            {(r.stdout + r.stderr).strip()[-300:]}')
        check('...and it refuses for the RIGHT reason (content_hash is not sha256(text))',
              'content_hash' in (r.stdout + r.stderr) or 'IS NOT sha256' in (r.stdout + r.stderr),
              (r.stdout + r.stderr).strip()[-300:])
    finally:
        shutil.rmtree(rd, ignore_errors=True)

    # =============================================================================================
    # PART B — THE MIXED FIXTURE + ADVERSARIAL MODEL. A release IS produced; it must be CLEAN.
    # =============================================================================================
    print('\n-- PART B: the full poisoned fixture + a hostile model — what lands in report.md ------')
    rd = make_run_dir(with_model=True)
    keep = rd            # kept for structural probes below; cleaned at the very end
    cp, gp = write_fixture(g, list(cards.values()), rd, 'mixed')
    r = run_composer(rd, cp, gp)
    rel = released(rd)
    check('the run SUCCEEDS and a report.md is released (admitted evidence exists)',
          r.returncode == 0 and rel.exists(),
          f'rc={r.returncode}\n            {(r.stdout + r.stderr).strip()[-600:]}')

    if not rel.exists():
        print('\n** no released file — cannot run the on-disk assertions. Aborting PART B. **')
    else:
        art = rel.read_text()          # (5) REOPEN THE RELEASED FILE FROM DISK — never an in-memory value
        side = rd / 'outputs' / 'release' / 'report.bindings.json'

        # (0) THE ATTACK WAS LIVE, NOT ABSENT. Tonight's whole lesson: a clean report can mean the
        #     fabrication moved lanes, or that nothing ran at all (an empty log read as "slow"). So
        #     PROVE the hostile model's payload was ATTEMPTED and the gate CAUGHT each attack, by name,
        #     in the composer's own drop log. If the body ever silently empties, these go red.
        drops = json.loads((rd / 'outputs' / 'drafts' / 'drops.json').read_text())
        blob = '\n'.join(drops)
        for sig, why in [
            ('NUMBER_NOT_IN_SPAN:0.2', 'the working-paper span, smuggled under a journal card, was tried and caught'),
            ("not offered to it: 'c:p0'", 'the refused P0 card was cited directly and refused'),
            ('SOURCE_NAMED_IN_CLAUSE_TEXT', 'a clause naming a source was tried and caught'),
            ('OWNED_CARRIES_A_NUMBER', 'an OWNED sentence carrying a number was tried and caught'),
            ('OWNED_NAMES_A_SOURCE', 'an OWNED sentence naming a source was tried and caught'),
            ('new_entity:Bavarian', 'the underived research gap was tried and caught')]:
            check(f'(0) attack was LIVE: {why}', sig in blob, f'signature {sig!r} not in the drop log')
        n_att_reached = sum(1 for e in json.loads(side.read_text())['sentences']
                            if e['voice'] == 'ATTRIBUTED')
        check('(0) the release is NON-TRIVIAL: real attributed sentences reached the file '
              '(so the absence checks below are not vacuous)', n_att_reached >= 5,
              f'only {n_att_reached} attributed sentences — an empty body makes "attack absent" meaningless')

        # (3) the correct journal span DOES reach the released artifact
        check('(3) the correct JOURNAL span reaches the released artifact',
              POS_PROBE in art, f'{POS_PROBE!r} absent from report.md')

        # (2) the working-paper span CANNOT appear under the journal attribution
        check('(2) the WORKING-PAPER span never appears under a journal attribution',
              WP_PROBE not in art and WP_SPAN not in art, f'{WP_PROBE!r} PRESENT in report.md')

        # (5) reopening the released file shows every attack string ABSENT
        for probe, why in [(FABRICATED, 'fabricated figure'), (GAP_PROBE, 'underived research gap'),
                           (OWNED_NUM_PROBE, 'OWNED sentence with a number'),
                           (NAMED_SOURCE, 'a source named by the model'), (WP_PROBE, 'working-paper span')]:
            check(f'(5) reopened file: {why} is ABSENT', probe not in art, f'{probe!r} PRESENT')

        # (4) EVERY attributed sentence in the RELEASED FILE re-verifies against the immutable store.
        #     (a) our own independent re-derivation from the on-disk sidecar + on-disk graph
        gdisk = P.Graph.from_json(json.loads(gp.read_text()))
        doc = json.loads(side.read_text())
        bad = []
        n_reverified = 0
        for e in doc['sentences']:
            if e['voice'] not in ('ATTRIBUTED', 'TABLE'):
                continue
            binding = dict(manifestation_id=e['manifestation_id'], content_hash=e['content_hash'],
                           span_start=e['span_start'], span_end=e['span_end'], text=e['span'],
                           permitted_expression_ids=[])
            # permitted set is re-derived from the graph, not trusted from the sidecar
            binding['permitted_expression_ids'] = list(gdisk.attribution_targets(e['manifestation_id']))
            ok_span = gdisk.verify_span(binding)
            att = gdisk.resolve_attribution(e['manifestation_id'], P.JOURNAL_ONLY)
            if not (ok_span and att.admitted and att.names_expression_id == e['names_expression_id']):
                bad.append(e['sentence'][:70])
            else:
                n_reverified += 1
        check(f'(4) every attributed/table binding INDEPENDENTLY re-verifies against the graph '
              f'({n_reverified} re-derived from bytes)', not bad and n_reverified > 0,
              f'{len(bad)} did not resolve: {bad[:3]}')

        # (4b) and the SHIPPED auditor, run as a SEPARATE PROCESS against the on-disk artifact
        va = subprocess.run(
            [sys.executable, str(rd / 'scripts' / 'publisher.py'), '--verify',
             '--graph', str(gp), '--name', 'report.md'],
            cwd=str(rd), env=dict(os.environ, PYTHONDONTWRITEBYTECODE='1'),
            capture_output=True, text=True)
        check('(4b) `publisher.py --verify` re-resolves the RELEASED file and exits 0',
              va.returncode == 0 and 'EVERY ATTRIBUTED SENTENCE' in va.stdout,
              f'rc={va.returncode}\n            {(va.stdout + va.stderr).strip()[-400:]}')

        # (1)/(6) EVERY sentence in the file is bound; nothing rides in unreceipted (the gap included)
        import report_ast as A
        known = {e['sentence_hash'] for e in doc['sentences']}
        orphan = []
        for line in art.splitlines():
            t = line.strip()
            if not t or t.startswith('#') or t.startswith('|') or t.startswith('**Table'):
                continue
            for s in A.split_sentences(t):
                if A.sentence_hash(s) not in known:
                    orphan.append(s[:70])
        check('(6) every sentence in the released file carries a sidecar binding (no unreceipted prose)',
              not orphan, f'{len(orphan)} orphan sentence(s): {orphan[:2]}')

        # =========================================================================================
        # PART C — THE STRUCTURAL BOUNDARY. Is it a write bit, or a convention?
        # =========================================================================================
        print('\n-- PART C: the structural boundary (a kernel write bit, tried, not asserted) ----------')
        reldir = rd / 'outputs' / 'release'
        mode = stat.filemode(reldir.stat().st_mode)
        check(f'the judged release directory is SEALED 0555 ({mode})',
              (reldir.stat().st_mode & 0o222) == 0)
        check('the released report.md is 0444 (its own author cannot rewrite it in place)',
              (rel.stat().st_mode & 0o222) == 0, f'mode {stat.filemode(rel.stat().st_mode)}')

        # a composer-like process tries to CREATE a file in the sealed dir -> EACCES from the kernel
        probe = ("from pathlib import Path; import sys\n"
                 "try:\n"
                 " (Path(sys.argv[1])/'__composer_breach.md').write_text('FABRICATION')\n"
                 " print('WROTE')\n"
                 "except (PermissionError, OSError) as e:\n"
                 " print('REFUSED:'+type(e).__name__)\n")
        pr = subprocess.run([sys.executable, '-c', probe, str(reldir)], capture_output=True, text=True)
        check('a process that is not the publisher CANNOT create a file in the sealed release dir',
              pr.stdout.strip().startswith('REFUSED') and not (reldir / '__composer_breach.md').exists(),
              f'probe said: {pr.stdout.strip()!r}')

        # PROVE whether the permission is real or a convention: a SAME-UID process chmods, then writes.
        bypass = ("import os, sys\n"
                  "d = sys.argv[1]\n"
                  "os.chmod(d, 0o755)\n"
                  "open(os.path.join(d, '__uid_bypass.txt'), 'w').write('x')\n"
                  "print('BYPASSED')\n")
        bp = subprocess.run([sys.executable, '-c', bypass, str(reldir)], capture_output=True, text=True)
        bypassed = bp.stdout.strip() == 'BYPASSED' and (reldir / '__uid_bypass.txt').exists()
        NOTES.append(
            'STRUCTURAL LIMIT (as designed, and as publisher.py admits): a SAME-UID process that '
            'DELIBERATELY calls os.chmod(0o755) first CAN then create a file in the release dir '
            f'-- observed: {"BYPASSED" if bypassed else bp.stdout.strip()!r}. This box has no second '
            'uid (`unshare -U` refused, no newuidmap), so the boundary converts "a check a future agent '
            'can FORGET" into "a kernel refusal a future agent must DELIBERATELY DEFEAT", and no further. '
            'The plain-write refusal above is real and kernel-enforced; this chmod defeat is the honest '
            'ceiling of what a single uid can buy.')
        # restore the seal we just broke, and remove the bypass artifact
        try:
            os.chmod(reldir, 0o755)
            (reldir / '__uid_bypass.txt').unlink(missing_ok=True)
            os.chmod(reldir, 0o555)
        except OSError:
            pass

        # =========================================================================================
        # PART D — NO CLOBBER. A poison run, launched at a dir that already holds a good release,
        #          must leave that release byte-for-byte untouched.
        # =========================================================================================
        print('\n-- PART D: a later poison run cannot disturb an existing good release -----------------')
        before = rel.read_bytes()
        before_sha = hashlib.sha256(before).hexdigest()
        cp2, gp2 = write_fixture(g, [cards['c:p0']], rd, 'solo_p0')
        r2 = run_composer(rd, cp2, gp2)
        after_ok = rel.exists() and hashlib.sha256(rel.read_bytes()).hexdigest() == before_sha
        check('a poison run at a populated release dir: NONZERO EXIT and the good report.md is UNCHANGED',
              r2.returncode != 0 and after_ok,
              f'rc={r2.returncode} unchanged={after_ok}')

    shutil.rmtree(keep, ignore_errors=True)

    # =============================================================================================
    print('\n' + '=' * 96)
    if NOTES:
        print('NOTES (honest limitations, reported not hidden):')
        for n in NOTES:
            print('  * ' + n)
        print()
    if FAILS:
        print(f'** {len(FAILS)} ASSERTION(S) FAILED — THE BOUNDARY LET SOMETHING THROUGH. **')
        for f in FAILS:
            print(f'    - {f}')
        return 1
    print('** EVERY ASSERTION HELD: the poison did not reach the released file, through the real command. **')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
