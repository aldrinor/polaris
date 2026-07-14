#!/usr/bin/env python3
"""THE RELEASE BOUNDARY — the test for the thing that is NOT a test.

Sol asked: "what test cannot be routed around?" The answer is NONE, and that is why the boundary is a
WRITE BIT and not a check. This file does not enforce the boundary. It asserts that the boundary EXISTS,
that the composer has not grown a way through it, and that the publisher refuses everything it should.

The distinction matters. If this file is deleted, `outputs/release/` is still mode 0555 and the composer
still cannot create a file in it. If a *check* is deleted, the door is open. That asymmetry is the whole
design.

    python scripts/test_release_boundary.py
"""
from __future__ import annotations

import ast
import json
import os
import re
import stat
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'scripts'))

import provenance as P            # noqa: E402
import publisher                  # noqa: E402
import report_ast as A            # noqa: E402
from report_ast import Attributed, Clause, Owned, Heading, CardBundle  # noqa: E402

COMPOSER = ROOT / 'scripts' / 'cellcog_composer.py'

fails: list[str] = []


def check(name: str, ok: bool, detail: str = '') -> None:
    print(f"  [{'PASS' if ok else '**FAIL**'}] {name}")
    if detail and not ok:
        print(f'            {detail}')
    if not ok:
        fails.append(name)


# =================================================================================================
# A SYNTHETIC GRAPH — real manifestations, real hashes, real offsets. The fixtures are BOUND.
# =================================================================================================

def synth():
    """Two journal articles and one working paper, with bytes. Everything binds or it does not exist."""
    import hashlib
    g = P.Graph()

    def work(wid, authors, year, venue, doi, title='T'):
        g.works[wid] = P.Work(id=wid, title=title, authors=authors, year=year, venue=venue, doi=doi,
                              kind='study')
        return g.works[wid]

    def expr(eid, wid, kind):
        w = g.works[wid]
        g.expressions[eid] = P.Expression(id=eid, work_id=wid, kind=kind, kind_basis='test',
                                          attribution=P._attribution_for(kind, w))
        return g.expressions[eid]

    def manif(mid, eid, wid, text, kind):
        h = hashlib.sha256(text.encode()).hexdigest()
        prof = dict(artifact_kind=kind, complete=True,
                    extractability=P.extractability(text), incomplete_because=[])
        g.manifestations[mid] = P.Manifestation(
            id=mid, expression_id=eid, work_id=wid, text=text, content_hash=h,
            n_words=len(text.split()), locator='http://x', locator_status='RECORDED',
            fetched_by='test', text_field='fulltext', profile=prof)
        return g.manifestations[mid]

    # Long enough to clear the scholarly stub floor (1,200 words) — completeness is a property of the
    # KIND, and a `journal_article` of 40 words is a stub, correctly.
    filler = ('The paper proceeds as follows. We describe the data, the identification strategy and the '
              'estimation. ') * 120

    bres_span = 'Computer automation of such work has been correspondingly limited in its scope.'
    autor_span = ('we contend that computer capital substitutes for workers in carrying out a limited and '
                  'well-defined set of cognitive and manual activities, namely routine tasks')
    ar_span = 'we find that employment falls by 0.2 percentage points per robot per thousand workers'

    bres_text = filler + bres_span + ' ' + filler
    autor_text = filler + autor_span + ' ' + filler
    ar_text = filler + ar_span + ' ' + filler

    work('w:bres', ['Bresnahan', 'Brynjolfsson'], 2002, 'The Quarterly Journal of Economics', '10.1/b')
    expr('e:bres:j', 'w:bres', 'journal_version')
    manif('m:bres', 'e:bres:j', 'w:bres', bres_text, 'journal_article')

    work('w:autor', ['Autor', 'Levy', 'Murnane'], 2003, 'The Quarterly Journal of Economics', '10.1/a')
    expr('e:autor:j', 'w:autor', 'journal_version')
    manif('m:autor', 'e:autor:j', 'w:autor', autor_text, 'journal_article')

    # THE P0, AS A FIXTURE: the metadata says Journal of Political Economy; the BYTES are the NBER
    # working paper. Under JOURNAL_ONLY nothing in it may be cited, at all, ever.
    work('w:ar', ['Acemoglu', 'Restrepo'], 2020, 'Journal of Political Economy', '10.1086/705716')
    expr('e:ar:wp', 'w:ar', 'working_paper')
    expr('e:ar:j', 'w:ar', 'journal_version')     # the journal version exists — WE DO NOT HOLD ITS BYTES
    manif('m:ar', 'e:ar:wp', 'w:ar', ar_text, 'working_paper')

    def card(cid, mid, span, claim, **kw):
        m = g.manifestations[mid]
        s = m.text.index(span)
        b = g.bind_span(mid, s, s + len(span))
        att = g.resolve_attribution(mid, P.JOURNAL_ONLY)
        return dict(id=cid, manifestation_id=mid, content_hash=b['content_hash'],
                    span_start=s, span_end=s + len(span), span_raw=b['text'], span=span, claim=claim,
                    expression_id=b['expression_id'],
                    permitted_expression_ids=list(b['permitted_expression_ids']),
                    attribution_target_expression_id=att.names_expression_id,
                    work_id=m.work_id, evidence_unit_id=m.work_id,
                    authors=g.works[m.work_id].authors, year=g.works[m.work_id].year,
                    venue=g.works[m.work_id].venue, level=kw.get('level', 'firm'),
                    horizon='long-run', method='observational', mechanisms=kw.get('mech', []),
                    corroborating_sources=[])

    cards = [
        card('c:bres', 'm:bres', bres_span, 'Computer automation of routine work has been limited in scope.'),
        card('c:autor', 'm:autor', autor_span,
             'Computer capital substitutes for workers in routine tasks.',
             level='occupation', mech=['task displacement']),
        card('c:ar', 'm:ar', ar_span, 'Employment falls 0.2pp per robot per thousand workers.',
             level='region'),
    ]
    return g, cards


g, CARDS = synth()
B = CardBundle(CARDS, g, P.JOURNAL_ONLY)

print('=== THE RELEASE BOUNDARY ===\n')

# -------------------------------------------------------------------------------------------------
# 1. THE FILESYSTEM. This is the part that is not a test.
# -------------------------------------------------------------------------------------------------
publisher.seal()
mode = stat.filemode(publisher.RELEASE.stat().st_mode)
check('the judged release directory is SEALED (no write bit for anyone)',
      publisher.is_sealed(), f'mode is {mode}')

try:
    (publisher.RELEASE / 'report.md').write_text('fabricated')
    breached = True
except (PermissionError, OSError):
    breached = False
check('a process that is not the publisher CANNOT create a file in the release directory',
      not breached, 'THE FILE WAS CREATED — the boundary is a convention, not a permission')

# -------------------------------------------------------------------------------------------------
# 2. THE COMPOSER HAS NO WAY THROUGH. If it grows one, this goes red.
# -------------------------------------------------------------------------------------------------
src = COMPOSER.read_text()
tree = ast.parse(src)
check('the composer contains NO chmod (it cannot unseal the release)',
      'chmod' not in src)
# It may write DRAFTS — that is its job. What it may not do is name, derive, or write the RELEASE.
# (The kernel proves the real invariant above; this keeps the SOURCE honest, so that a future edit that
#  tries to reach the release directory turns the suite red before it turns the artifact false.)
release_refs = [ln.strip() for ln in src.splitlines()
                if re.search(r'\bRELEASE\b|outputs./release|publisher\.RELEASE', ln)]
check('the composer never names the release directory',
      not release_refs, f'it refers to the release: {release_refs[:2]}')
# SCAN ACTIVE CODE, NOT PROSE. The naive substring test matched THE DOCSTRING THAT DOCUMENTS THE BUG
# — `(OUT_DIR / 'report.md').write_text(report)` appears in this file's header as a tombstone, and a
# text scan cannot tell a tombstone from a corpse. Walk the AST: only real calls count.
lines = src.splitlines()
active_writes = [lines[n.lineno - 1].strip() for n in ast.walk(tree)
                 if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                 and n.func.attr in ('write_text', 'write_bytes')]
check('every ACTIVE write in the composer targets DRAFTS, never the release',
      all('DRAFTS' in w for w in active_writes),
      f'a write that is not a draft: {[w for w in active_writes if "DRAFTS" not in w][:2]}')
check('the composer does not import the publisher\'s gate opener',
      '_gate' not in src)
calls = {n.func.id for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
attrs = {n.func.attr for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)}
check('the composer REACHES THE PUBLISHER (it is on the critical path, not merely imported)',
      'publish' in attrs, 'publisher.publish() is never called — the composer publishes nothing')
check('the composer RE-VERIFIES BINDINGS BEFORE ANY LLM CALL',
      'reverify' in calls,
      'reverify() is imported/defined and never called — the exact bug the canary exists to catch')

# -------------------------------------------------------------------------------------------------
# 3. THE LAW, AT THE BOUNDARY.
# -------------------------------------------------------------------------------------------------
# THE P0: working-paper bytes labelled with a journal. NOTHING in it may be cited.
r = B.resolve('c:ar')
check('THE P0: a card whose BYTES are a working paper is REFUSED under journal-only',
      not r.ok and 'SOURCE_POLICY' in r.refusal, f'IT RESOLVED: {r.attribution!r}')

ok_nodes = [Attributed(clauses=(Clause('c:autor',
                                       'computer capital substitutes for workers in a limited and '
                                       'well-defined set of routine tasks'),))]
fails_ = A.validate_report(ok_nodes, B)
check('a TRUE finding, present in its own span, is LAWFUL',
      not fails_, f'real evidence deleted: {[str(f) for f in fails_]}')

# THE FABRICATED BINDING: a real mechanism, a real paper, credited to a paper that never states it.
bad = [Attributed(clauses=(Clause('c:bres', 'task displacement is the operative channel driving '
                                            'occupational decline'),))]
check('THE FABRICATED BINDING: a real mechanism bound to a paper that never states it is REJECTED',
      bool(A.validate_report(bad, B)),
      'a real mechanism was credited to a paper whose span does not contain it')

# ...and it still dies when hidden inside a cross-source comparison.
hidden = [Attributed(clauses=(
    Clause('c:autor', 'computer capital substitutes for workers in routine tasks'),
    Clause('c:bres', 'task displacement drives the labor share down')), connective='while')]
check('the fabricated binding dies even when hidden inside a comparison',
      bool(A.validate_report(hidden, B)))

# ...while the HONEST comparison — the heaviest criterion on the board — survives.
synth_ok = [Attributed(clauses=(
    Clause('c:autor', 'computer capital substitutes for workers in a limited and well-defined set of '
                      'routine tasks'),
    Clause('c:bres', 'computer automation of such work has been correspondingly limited in its scope')),
    connective='while')]
check('CROSS-SOURCE SYNTHESIS survives (critical synthesis, w=0.0800)',
      not A.validate_report(synth_ok, B),
      f'the comparison was deleted: {[str(f) for f in A.validate_report(synth_ok, B)]}')

# THE SUBSTRING LEAK: "0.2" is a substring of "10.25".
leak_g, leak_cards = synth()
lc = dict(leak_cards[0])
check('a number that is only a SUBSTRING of a source number is REJECTED',
      not A.entailed_by_span('employment fell by 0.2 percentage points',
                             'productivity growth of 10.25 percent was observed', None)[0])

# EVIDENCE LAUNDERING: the gate must never read the model-authored `claim`.
laundered = dict(CARDS[0], claim='Computerisation reduced employment by 47 percent across affected firms.')
LB = CardBundle([laundered], g, P.JOURNAL_ONLY)
check('EVIDENCE LAUNDERING: a figure the extractor invented in `claim` cannot enter the prose',
      bool(A.validate_report(
          [Attributed(clauses=(Clause('c:bres', 'computerisation reduced employment by 47 percent '
                                                'across affected firms'),))], LB)),
      'a fabricated number in `claim` reached the page under a real citation')

# THE MODEL MAY NOT NAME A SOURCE — attribution is rendered from the graph, never typed.
named = [Attributed(clauses=(Clause('c:autor', 'Bresnahan and colleagues show that computer capital '
                                               'substitutes for workers in routine tasks'),))]
check('the model may NOT name a source in its own prose (voice is never inferred from surnames)',
      bool(A.validate_report(named, B)))

# OWNED may not smuggle a particular, or a source.
check('an OWNED sentence carrying a NUMBER is REJECTED',
      bool(A.validate_report([Owned(text='the effect is close to 5 percentage points')], B)))
check('an OWNED sentence NAMING A SOURCE is REJECTED',
      bool(A.validate_report([Owned(text='Acemoglu is right about this')], B)))
check('an OWNED sentence in the reviewer\'s own voice, with no particular, is LAWFUL',
      not A.validate_report(
          [Owned(text='The evidence establishes displacement at the level of the task, and does not '
                      'settle whether it aggregates to the economy as a whole.')], B))

# -------------------------------------------------------------------------------------------------
# 4. THE PUBLISHER REFUSES.
# -------------------------------------------------------------------------------------------------
before = sorted(p.name for p in publisher.RELEASE.iterdir()) if publisher.RELEASE.exists() else []
try:
    publisher.publish(bad, B, name='__attack.md')
    refused = False
except publisher.RefusedToPublish:
    refused = True
except Exception:
    refused = True
after = sorted(p.name for p in publisher.RELEASE.iterdir()) if publisher.RELEASE.exists() else []
check('the publisher REFUSES an unlawful AST', refused)
check('a REFUSED publish writes NOTHING (no partial release)', before == after,
      f'files appeared: {set(after) - set(before)}')
check('the release directory is STILL SEALED after a refused publish', publisher.is_sealed())

# ...and a lawful one goes out, atomically, with its sidecar.
meta = publisher.publish([Heading(1, 'T')] + synth_ok, B, name='__ok.md')
rep = publisher.RELEASE / '__ok.md'
side = publisher.RELEASE / '__ok.bindings.json'
check('a LAWFUL report is published atomically, with a sentence-hash-to-binding sidecar',
      rep.exists() and side.exists())
check('the release directory is RE-SEALED after a successful publish', publisher.is_sealed())

doc = json.loads(side.read_text())
att = [e for e in doc['sentences'] if e['voice'] == 'ATTRIBUTED']
check('every ATTRIBUTED sentence in the sidecar carries manifestation_id + content_hash + span',
      bool(att) and all(e['manifestation_id'] and e['content_hash'] and e['span'] for e in att))
check('the released prose names the JOURNAL, rendered from the graph — not by the model',
      'Quarterly Journal of Economics' in rep.read_text())

# -------------------------------------------------------------------------------------------------
# 5. THE TAMPER. The sidecar is a RECEIPT, and a receipt that cannot catch an edit is decoration.
#    Someone edits the released file to add a figure no source states. Every sentence hash in the file
#    is re-derived and looked up; the edited sentence is in no receipt, so it resolves to NOTHING.
# -------------------------------------------------------------------------------------------------
clean = rep.read_text()
TAMPER_FROM = 'correspondingly limited in its scope.'
TAMPER_TO = 'correspondingly limited in its scope, and 47 percent of all jobs are at risk.'
assert TAMPER_FROM in clean, 'the tamper fixture does not match the rendered file — it would be a no-op'

# A RELEASED FILE IS 0444 AND CANNOT BE REWRITTEN IN PLACE — not even by the publisher, which is why
# the first version of this attack died with EPERM on its own `write_text`. So the attacker must do what
# an attacker would actually have to do: unlink the released file and put a different one in its place.
# The sidecar does not care how the bytes changed. It cares that they no longer resolve.
check('a released file cannot be rewritten IN PLACE (it is 0444)',
      not (rep.stat().st_mode & 0o222), f'mode is {stat.filemode(rep.stat().st_mode)}')
with publisher._gate():
    rep.unlink()
    rep.write_text(clean.replace(TAMPER_FROM, TAMPER_TO))


def unresolved_sentences(report: Path, sidecar: Path) -> list[str]:
    known = {e['sentence_hash'] for e in json.loads(sidecar.read_text())['sentences']}
    out = []
    for line in report.read_text().splitlines():
        t = line.strip()
        if not t or t.startswith('#') or t.startswith('|') or t.startswith('**Table'):
            continue
        for s in publisher._sentences(t):
            if A.sentence_hash(s) not in known:
                out.append(s)
    return out


bad_s = unresolved_sentences(rep, side)
check('a TAMPERED released file no longer resolves against its sidecar',
      bool(bad_s), 'the edited sentence still resolved — the receipt certifies nothing')
check('the tampered sentence is the one carrying the fabricated figure',
      any('47 percent' in s for s in bad_s), f'caught: {bad_s[:1]}')

# clean up the two test artifacts — they are not a release.
with publisher._gate():
    for p in (rep, side):
        p.unlink(missing_ok=True)
publisher.seal()

print()
if fails:
    print(f'** {len(fails)} FAILURE(S). THE BOUNDARY IS NOT SOUND. NOTHING SHIPS. **')
    for f in fails:
        print(f'    - {f}')
    raise SystemExit(1)
print('** THE RELEASE BOUNDARY HOLDS. **')
