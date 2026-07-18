#!/usr/bin/env python3
"""THE PUBLISHER — THE ONLY PROCESS THAT MAY CREATE A FILE IN THE JUDGED RELEASE DIRECTORY.

Sol: "COMPOSERS MAY WRITE ONLY DRAFTS. ONLY THE PUBLISHER PROCESS HAS FILESYSTEM PERMISSION TO CREATE
FILES IN THE JUDGED RELEASE DIRECTORY."

THE QUESTION THIS FILE ANSWERS: "WHAT TEST CANNOT BE ROUTED AROUND?"
--------------------------------------------------------------------
None. That is the finding of the night. Six adversary attacks succeeded while the canary was 16/16 GREEN
and nothing had been weakened, because a test certifies A LANE, and the fabrication had moved to a
different lane. We then reproduced the exact bug the canary exists to catch — `validate()` imported and
never called — INSIDE THE FIX FOR IT.

So the boundary is not a test. It is the WRITE BIT.

    outputs/release/  is mode 0555 — r-xr-xr-x. NO WRITE PERMISSION FOR ANYONE, INCLUDING THE OWNER.

`cellcog_composer.py` contains no `chmod`, imports no gate-opener, and therefore CANNOT create
`report.md`. If a future agent adds `(RELEASE / 'report.md').write_text(md)` to the composer — which is
EXACTLY what the composer used to do, at line 775 — the kernel raises PermissionError. Not a warning, not
a failed assertion someone can comment out: EACCES, from the VFS, before a byte is written. Nobody has to
remember anything.

WHAT THIS BUYS, STATED HONESTLY — AND WHAT IT DOES NOT
------------------------------------------------------
This box has NO ROOT and NO USABLE UID SEPARATION (`unshare -U` is refused; there is no `newuidmap`).
With a second uid, the release directory would be owned by `publisher:publisher` and the composer's uid
could not open the gate AT ALL — that is the unbypassable version, and it is not available here.

What IS enforced, by the kernel, today:
  * NO process — publisher included — can create a file in the release directory while it is sealed.
  * The publisher opens the gate ONLY inside `_gate()`, ONLY after the ENTIRE AST has validated, and
    re-seals in a `finally` that runs on every exception path.
  * A stray `write_text` anywhere else in the repo raises PermissionError.

What is NOT enforced: a process running as uid 1000 that DELIBERATELY calls `os.chmod` first. I am not
going to claim otherwise. The lesson of tonight is that a self-certified boundary is worth nothing, and
the honest statement of this one is: it converts "a check a future agent can FORGET" into "a kernel
refusal a future agent must DELIBERATELY DEFEAT". `test_release_boundary.py` asserts the composer
contains no chmod and no writer, so defeating it deliberately also turns the suite red.

THE CHAIN, RE-DERIVED HERE, AT THE BOUNDARY, FROM THE BYTES
-----------------------------------------------------------
    sentence -> card -> bound span -> manifestation_id + content_hash -> permitted expression -> attribution

`render()` already validated. The publisher validates AGAIN, against a graph it loads ITSELF, because
"the composer already checked" is precisely the sentence that shipped the P0.
"""
from __future__ import annotations

import contextlib
import hashlib
import json
import os
import stat
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'scripts'))

import provenance as P                                        # noqa: E402
import report_ast as A                                        # noqa: E402

#: THE JUDGED RELEASE DIRECTORY. The only artifact the grader ever reads lives here.
RELEASE = ROOT / 'outputs' / 'release'

#: Sealed: r-xr-xr-x. No write bit anywhere. Creating a file inside it is EACCES for every process.
SEALED = 0o555
#: Open: rwxr-xr-x. Held for the duration of one atomic rename, inside `_gate()`, and never longer.
OPEN = 0o755


# =================================================================================================
# THE GATE
# =================================================================================================

def is_sealed() -> bool:
    if not RELEASE.exists():
        return False
    return (RELEASE.stat().st_mode & 0o222) == 0        # no write bit for user, group, or other


def seal() -> None:
    """Put the release directory back into its refusing state. Idempotent."""
    RELEASE.mkdir(parents=True, exist_ok=True)
    os.chmod(RELEASE, SEALED)


@contextlib.contextmanager
def _gate():
    """THE ONLY PLACE IN THIS REPOSITORY THAT MAY MAKE THE RELEASE DIRECTORY WRITABLE.

    It is private, it is not exported, and `cellcog_composer.py` does not import this module's writer at
    all. The `finally` re-seals on EVERY path — including an exception mid-rename — so a crashed publish
    cannot leave the door open for the next process that happens to call `write_text`.
    """
    RELEASE.mkdir(parents=True, exist_ok=True)
    os.chmod(RELEASE, OPEN)
    try:
        yield RELEASE
    finally:
        os.chmod(RELEASE, SEALED)


def _atomic_write(name: str, data: str) -> Path:
    """Write to a temp file OUTSIDE the release dir, fsync it, then rename it IN under the open gate.

    A partially-written report.md is a published report.md. `rename(2)` within a filesystem is atomic:
    the grader sees the old file or the new one, never half of one.
    """
    dst = RELEASE / name
    fd, tmp = tempfile.mkstemp(dir=str(ROOT / 'outputs'), prefix=f'.{name}.', suffix='.staging')
    try:
        with os.fdopen(fd, 'w') as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        # `mkstemp` creates 0600. A JUDGED ARTIFACT THAT THE JUDGE CANNOT READ IS NOT A RELEASE — and a
        # released file that its own author can still rewrite in place is not a release either. 0444.
        os.chmod(tmp, 0o444)
        os.replace(tmp, dst)
    except BaseException:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(tmp)
        raise
    return dst


def sha256_file(p: Path) -> str:
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


# =================================================================================================
# THE PUBLISH BOUNDARY
# =================================================================================================

class RefusedToPublish(Exception):
    """The report is not publishable. NOTHING WAS WRITTEN. It is not repaired, and it is not partially
    released."""


def publish(nodes: list[A.Node], bundle: A.CardBundle, *, name: str = 'report.md',
            provenance_of_inputs: dict | None = None) -> dict:
    """VALIDATE THE ENTIRE AST -> RENDER -> RE-RESOLVE EVERY SENTENCE -> ATOMICALLY RELEASE.

    Every one of these steps happens BEFORE the gate is opened. There is no path on which a byte is
    written and then checked, because "written and then checked" describes the artifact that is on disk
    right now, citing a web page as a peer-reviewed article.
    """
    # ---- 1. THE WHOLE AST, OR NOTHING. `render()` raises if any node is unlawful.
    fails = A.validate_report(nodes, bundle)
    if fails:
        raise RefusedToPublish(
            f'{len(fails)} unlawful node(s) — NOTHING IS PUBLISHED:\n  - ' +
            '\n  - '.join(str(f) for f in fails[:30]))
    md, sidecar = A.render(nodes, bundle)

    # ---- 2. RE-RESOLVE EVERY ATTRIBUTED SENTENCE, FROM THE SIDECAR, AGAINST THE GRAPH.
    #         The renderer produced both. Trusting it here would make the sidecar a record OF THE
    #         RENDERER rather than of the bytes — and a receipt that is not checked is the shape of
    #         every defect in this file's header.
    g = bundle.graph
    for e in sidecar:
        if e['voice'] == 'OWNED':
            continue
        b = dict(manifestation_id=e['manifestation_id'], content_hash=e['content_hash'],
                 span_start=e['span_start'], span_end=e['span_end'], text=e['span'])
        if not g.verify_span(b):
            raise RefusedToPublish(f'sentence does not resolve to its bytes at the boundary: '
                                   f'{e["sentence"][:70]!r} -> {e["manifestation_id"]}')
        att = g.resolve_attribution(e['manifestation_id'], bundle.policy)
        if not att.admitted or att.names_expression_id != e['names_expression_id']:
            raise RefusedToPublish(
                f'attribution target does not hold at the boundary: {e["sentence"][:70]!r} '
                f'names {e["names_expression_id"]!r}, policy `{bundle.policy.name}` resolves '
                f'{att.names_expression_id!r} ({att.refusal or "ok"})')

    # ---- 3. EVERY SENTENCE IN THE RENDERED FILE MUST BE IN THE SIDECAR.
    #         This is the check that catches a renderer which emits prose no node produced. Without it,
    #         the sidecar would certify the sentences it knows about and say nothing about the rest —
    #         which is exactly how 16/16 GREEN coexisted with six live attacks.
    known = {e['sentence_hash'] for e in sidecar}
    for line in md.splitlines():
        t = line.strip()
        if not t or t.startswith('#') or t.startswith('|') or t.startswith('**Table'):
            continue
        for s in A.split_sentences(t):
            if A.sentence_hash(s) not in known:
                raise RefusedToPublish(
                    f'THE RELEASED FILE WOULD CONTAIN A SENTENCE NO NODE PRODUCED: {s[:90]!r}')

    # ---- 4. the release is PINNED to the exact inputs that produced it.
    #
    # COUNT SENTENCES AS SENTENCES. The first version of this block reported
    # `n_attributed = len([e for e in sidecar if voice == 'ATTRIBUTED'])` = 153, and the file held 94
    # attributed sentences: the sidecar carries ONE ENTRY PER CLAUSE, and a cross-source sentence has
    # two. So the release announced 153 sentences it did not contain. That is a small number and it was
    # inflated by 63%, in the metrics of the very artifact whose subject is inflated numbers. The counts
    # below are now named for what they COUNT.
    att = [e for e in sidecar if e['voice'] == 'ATTRIBUTED']
    meta = dict(
        policy=bundle.policy.name,
        cards_sha256=bundle.cards_sha,
        graph_sha256=bundle.graph_sha,
        ledger_sha256=bundle.ledger_sha,
        n_sentences=len({e['sentence_hash'] for e in sidecar}),
        n_attributed_sentences=len({e['sentence_hash'] for e in att}),
        n_clause_bindings=len(att),          # a cross-source sentence binds more than once
        n_owned=sum(1 for e in sidecar if e['voice'] == 'OWNED'),
        n_table_rows=sum(1 for e in sidecar if e['voice'] == 'TABLE'),
        n_cards_cited=len({e['card_id'] for e in sidecar if e.get('card_id')}),
        n_works_cited=len({e['work_id'] for e in sidecar if e.get('work_id')}),
        inputs=provenance_of_inputs or {},
    )
    payload = json.dumps(dict(meta=meta, sentences=sidecar), indent=1)

    # ---- 5. ...and only NOW does the door open, for exactly two renames.
    with _gate():
        rp = _atomic_write(name, md)
        sp = _atomic_write(name.replace('.md', '') + '.bindings.json', payload)
    meta['report'] = str(rp)
    meta['sidecar'] = str(sp)
    meta['report_sha256'] = sha256_file(rp)
    return meta


# =================================================================================================
# VERIFY A RELEASE THAT IS ALREADY ON DISK — the auditor's entry point
# =================================================================================================

def verify_release(graph_path: Path, name: str = 'report.md') -> int:
    """Re-resolve the RELEASED FILE, from its sidecar, against the graph. Nothing is taken on trust.

    THE ONLY QUESTION THAT CANNOT BE FOOLED IS: WHAT IS IN THE FILE THE JUDGE WILL READ?
    """
    rep, side = RELEASE / name, RELEASE / (name.replace('.md', '') + '.bindings.json')
    if not rep.exists():
        print(f'no release at {rep}')
        return 1
    if not side.exists():
        print(f'** RELEASED FILE WITH NO SIDECAR: {rep} — it certifies nothing **')
        return 1
    g = P.Graph.from_json(json.loads(Path(graph_path).read_text()))
    doc = json.loads(side.read_text())
    sc = {e['sentence_hash']: e for e in doc['sentences']}
    md = rep.read_text()
    policy = {p.name: p for p in (P.JOURNAL_ONLY, P.PEER_REVIEWED, P.OFFICIAL_TEXT,
                                  P.ANY_VERSION)}[doc['meta']['policy']]

    bad, n_att, n_own = [], 0, 0
    for line in md.splitlines():
        t = line.strip()
        if not t or t.startswith('#') or t.startswith('|') or t.startswith('**Table'):
            continue
        for s in A.split_sentences(t):
            e = sc.get(A.sentence_hash(s))
            if e is None:
                bad.append(f'UNBOUND SENTENCE IN THE RELEASED FILE: {s[:80]!r}')
                continue
            if e['voice'] == 'OWNED':
                n_own += 1
                continue
            n_att += 1
            b = dict(manifestation_id=e['manifestation_id'], content_hash=e['content_hash'],
                     span_start=e['span_start'], span_end=e['span_end'], text=e['span'])
            if not g.verify_span(b):
                bad.append(f'SPAN DOES NOT VERIFY: {s[:70]!r}')
                continue
            att = g.resolve_attribution(e['manifestation_id'], policy)
            if not att.admitted:
                bad.append(f'POLICY REFUSES ITS SOURCE: {s[:70]!r} — {att.refusal}')
            elif att.names_expression_id != e['names_expression_id']:
                bad.append(f'ATTRIBUTION TARGET MOVED: {s[:70]!r}')

    print(f'  release      : {rep}')
    print(f'  report sha256: {sha256_file(rep)}')
    print(f'  sealed       : {is_sealed()}  (mode {stat.filemode(RELEASE.stat().st_mode)})')
    print(f'  policy       : {doc["meta"]["policy"]}')
    print(f'  ATTRIBUTED   : {n_att} sentences, every one re-resolved to bytes')
    print(f'  OWNED        : {n_own} sentences (reviewer voice, no source, no particular)')
    print(f'  works cited  : {doc["meta"].get("n_works_cited")}')
    if bad:
        print(f'\n** {len(bad)} SENTENCE(S) DO NOT RESOLVE. THE RELEASE IS CONTAMINATED. **')
        for x in bad[:20]:
            print(f'    - {x}')
        return 1
    print('\n** EVERY ATTRIBUTED SENTENCE IN THE RELEASED FILE RESOLVES: '
          'sentence -> card -> span -> manifestation+hash -> permitted expression -> attribution **')
    return 0


if __name__ == '__main__':
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument('--seal', action='store_true', help='(re)seal the release directory')
    ap.add_argument('--status', action='store_true')
    ap.add_argument('--verify', action='store_true')
    ap.add_argument('--graph', default=str(ROOT / 'outputs' / 'provenance_graph.json'))
    ap.add_argument('--name', default='report.md')
    a = ap.parse_args()
    if a.seal:
        seal()
        print(f'sealed {RELEASE} -> {stat.filemode(RELEASE.stat().st_mode)}')
    if a.status:
        RELEASE.mkdir(parents=True, exist_ok=True)
        print(f'{RELEASE}: mode {stat.filemode(RELEASE.stat().st_mode)}  sealed={is_sealed()}')
    if a.verify:
        raise SystemExit(verify_release(Path(a.graph), a.name))
