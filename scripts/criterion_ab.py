#!/usr/bin/env python3
"""CRITERION-LEVEL A/B — the instrument the whole wheel depends on, and it did not exist.

WHY (adversarial lens 3, verified against score_calculator.py + criteria.jsonl + the measured judge output):

    **20 of the 25 criteria cannot individually clear the +0.0094 kill rule EVEN AT A PERFECT 10/10.**

A criterion of weight 0.0435 (e.g. "Depth and Representativeness") would have to move **+4.8 points on the
0-10 scale** to shift the OVERALL score by the +0.0094 our kill rule demands. Half the scale. On one criterion.

Both foundation plans mandated ONE LEVER AT A TIME *and* a kill rule that cannot see one lever.
**They would have killed every good lever they built.** That is not a hypothetical: this repo's history is a
graveyard of levers that "moved a metric while the mechanism never fired" — and of levers that fired and were
thrown away because a scalar could not resolve them.

THE FIX COSTS NOTHING. The judge already writes a 0-10 score AND a written analysis for every criterion, for
BOTH articles, on every call. `deepresearch_bench_race.py` keeps four floats and discards the rest. We stopped
discarding it (scripts/judge_feedback.py). So:

    STOP measuring a lever against the SCALAR.
    START measuring it against THE CRITERION IT TARGETS.

Same judge calls. Same cost. Roughly 10x the statistical power — purely by not deleting the output.

USAGE
    # score two artifacts k times each and compare AT THE CRITERION LEVEL
    set -a && . ./.env && set +a
    python scripts/criterion_ab.py --a outputs/rank10_sections_compose/report.md \
                                   --b outputs/wave1_reflow/report.md \
                                   --task-id 72 --k 5 --targets "Exclusive Citation,Critical Synthesis"

A lever is KEPT iff the criteria it TARGETS move, with the whole-report criteria as a guard against regression.
"""
from __future__ import annotations

import argparse
import json
import os
import statistics as st
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def score_once(report: str, task: str, out: Path) -> dict | None:
    """One comparative judge call -> the FULL per-criterion ledger (both articles)."""
    r = subprocess.run(
        [sys.executable, str(ROOT / 'scripts' / 'judge_feedback.py'),
         '--report', report, '--task-id', task, '--out', str(out)],
        cwd=ROOT, capture_output=True, text=True, timeout=1800)
    if not out.exists():
        print(f'    ! judge failed: {r.stderr[-200:] if r.stderr else "no output"}')
        return None
    return json.loads(out.read_text())


def ledger(fb: dict) -> dict[tuple[str, str], tuple[float, float]]:
    """(dim, criterion) -> (our_score, reference_score)."""
    out = {}
    for dim, items in (fb['judge_output'] or {}).items():
        if not isinstance(items, list):
            continue
        for c in items:
            out[(dim, c['criterion'])] = (c['article_1_score'], c['article_2_score'])
    return out


def crit_weights(task: str) -> dict[tuple[str, str], float]:
    """Effective global weight = within-dimension weight x dimension weight."""
    p = ROOT / 'third_party' / 'deep_research_bench' / 'data' / 'criteria_data' / 'criteria.jsonl'
    for line in p.open():
        d = json.loads(line)
        if str(d['id']) != str(task):
            continue
        W = {}
        for dim, items in d['criterions'].items():
            tot = sum(c['weight'] for c in items) or 1.0
            for c in items:
                W[(dim, c['criterion'])] = (c['weight'] / tot) * d['dimension_weight'][dim]
        return W
    return {}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--a', required=True, help='baseline report')
    ap.add_argument('--b', required=True, help='the arm')
    ap.add_argument('--task-id', default='72')
    ap.add_argument('--k', type=int, default=5)
    ap.add_argument('--targets', default='', help='comma-separated substrings of the criteria this lever TARGETS')
    a = ap.parse_args()

    W = crit_weights(a.task_id)
    tmp = ROOT / 'outputs' / '_ab'
    tmp.mkdir(parents=True, exist_ok=True)

    runs: dict[str, list[dict]] = {'A': [], 'B': []}
    for i in range(a.k):
        for arm, path in (('A', a.a), ('B', a.b)):
            print(f'  [{arm}] replicate {i+1}/{a.k} ...')
            fb = score_once(path, a.task_id, tmp / f'{arm}_{i}.json')
            if fb:
                runs[arm].append(ledger(fb))

    if not runs['A'] or not runs['B']:
        print('FATAL: no successful scorings')
        return 1

    crits = sorted(set(runs['A'][0]) & set(runs['B'][0]), key=lambda c: -W.get(c, 0))
    targets = [t.strip().lower() for t in a.targets.split(',') if t.strip()]

    print('\n' + '=' * 104)
    print(f'=== CRITERION-LEVEL A/B  (k={a.k} each; A={Path(a.a).parent.name}  B={Path(a.b).parent.name}) ===')
    print('    A lever is judged on THE CRITERIA IT TARGETS, not on the scalar it cannot move.\n')
    print(f'{"w":>6} {"criterion":<58} {"A":>6} {"B":>6} {"delta":>7} {"t":>6}  target?')
    print('-' * 104)

    tot_a = tot_b = 0.0
    hits, regressions = [], []
    for c in crits:
        av = [r[c][0] for r in runs['A'] if c in r]
        bv = [r[c][0] for r in runs['B'] if c in r]
        if not av or not bv:
            continue
        ma, mb = st.mean(av), st.mean(bv)
        w = W.get(c, 0)
        tot_a += ma * w
        tot_b += mb * w
        d = mb - ma
        sd = st.pstdev(av + bv) or 0.001
        t = d / (sd * (2 / max(1, len(av))) ** 0.5)
        is_t = any(x in c[1].lower() for x in targets)
        mark = ' <<< TARGET' if is_t else ''
        if is_t and d > 0:
            hits.append((c[1], d, t))
        if d <= -1.0:
            regressions.append((c[1], d))
        print(f'{w:6.4f} {c[1][:58]:<58} {ma:6.2f} {mb:6.2f} {d:+7.2f} {t:+6.1f}{mark}')

    # the scalar, for reference only -- it is NOT the decision instrument
    refs = st.mean([sum(r[c][1] * W.get(c, 0) for c in crits if c in r) for r in runs['A']])
    sa = tot_a / (tot_a + refs) if (tot_a + refs) else 0
    sb = tot_b / (tot_b + refs) if (tot_b + refs) else 0
    print('-' * 104)
    print(f'  OVERALL (context only, NOT the decision): A {sa:.4f}  B {sb:.4f}  delta {sb-sa:+.4f}')
    print(f'  (a single criterion of weight 0.0435 must move +4.8 pts to shift this by +0.0094 —'
          f' which is why we do NOT decide on it)')

    print('\n=== VERDICT ===')
    if targets:
        if hits:
            print('  TARGETED CRITERIA THAT MOVED:')
            for name, d, t in hits:
                verdict = 'RESOLVED' if abs(t) >= 2 else 'below 2 sigma'
                print(f'    {d:+.2f} pts (t={t:+.1f}, {verdict})  {name[:64]}')
        else:
            print('  ** THE LEVER DID NOT MOVE ITS OWN TARGET CRITERIA. The mechanism did not fire. **')
    if regressions:
        print('\n  ** REGRESSIONS (>= -1.0 pt) — a lever that wins its target and loses elsewhere is NOT a win: **')
        for name, d in regressions:
            print(f'    {d:+.2f}  {name[:70]}')
    elif targets and hits:
        print('\n  no criterion regressed by >= 1.0 pt.')

    Path(ROOT / 'outputs' / 'criterion_ab.json').write_text(json.dumps({
        'a': a.a, 'b': a.b, 'k': a.k,
        'criteria': [{'dim': c[0], 'criterion': c[1], 'weight': W.get(c, 0),
                      'a_mean': st.mean([r[c][0] for r in runs['A'] if c in r]),
                      'b_mean': st.mean([r[c][0] for r in runs['B'] if c in r])} for c in crits],
        'overall_a': sa, 'overall_b': sb,
    }, indent=1))
    print(f'\nwrote outputs/criterion_ab.json')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
