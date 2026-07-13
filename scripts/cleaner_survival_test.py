#!/usr/bin/env python3
"""CLEANER-SURVIVAL TEST — which citation format survives RACE's LLM cleaner?

THE STAKES: RACE runs an LLM "ArticleCleaner" over every report BEFORE the judge sees it, instructed to
"remove all citation links, citation marks (such as [1], [2] ...), reference lists, footnotes".
VERIFIED on our own artifact: 345 [n] markers -> 0, and our entire 105-entry bibliography -> deleted.

So the judge currently sees POLARIS as a report with NO SOURCES AT ALL, on a task whose instruction is
"Ensure the review only cites high-quality, English-language journal articles."

The #1 system (cellcog) instead writes "Acemoglu and Restrepo (2019), in the Journal of Economic
Perspectives, show..." — ordinary prose. We BELIEVE the cleaner cannot remove that. But GPT-5.6 Sol
made the correct objection: **the cleaner is an LLM, not a regex.** Its prompt says "or other complex
citation formats". Whether author-year attribution survives is an EMPIRICAL question, and the entire
attribution lever rests on the answer.

This runs the PRODUCTION cleaner over the same 12 factual sentences rendered in 5 competing formats,
N times each, and reports what survives. No guessing.

Usage:
  set -a && . ./.env && set +a
  python scripts/cleaner_survival_test.py --runs 3
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
DRB = ROOT / 'third_party' / 'deep_research_bench'
sys.path.insert(0, str(DRB))

# 12 real facts from our own report, rendered 5 ways. Author/venue/year are REAL (Crossref-verified).
FACTS = [
    ('Automation generates a displacement effect that reduces labor\'s share of value added, countered by a reinstatement effect as new tasks reinstate labor',
     'Acemoglu and Restrepo', 2019, 'Journal of Economic Perspectives'),
    ('About 47 percent of total US employment is at risk of computerisation',
     'Frey and Osborne', 2017, 'Technological Forecasting and Social Change'),
    ('Generative AI raised the productivity of professional writing tasks by 40 percent and quality by 18 percent',
     'Noy and Zhang', 2023, 'Science'),
    ('Around 80 percent of the US workforce could have at least 10 percent of their tasks affected by large language models',
     'Eloundou et al.', 2024, 'Science'),
    ('The occupational AI exposure measure links AI advances to the abilities required by each occupation',
     'Felten et al.', 2021, 'Strategic Management Journal'),
    ('Employment polarization increased as routine task-intensive middle-wage jobs declined',
     'Autor et al.', 2013, 'American Economic Review'),
    ('Task content of occupations is the correct unit of analysis for technological displacement rather than skill level',
     'Autor', 2015, 'Journal of Economic Perspectives'),
    ('AI adoption in service firms reshapes the division of labor between employees and customers',
     'Buhalis et al.', 2019, 'Journal of Service Management'),
    ('Human resource management is being restructured by algorithmic decision systems',
     'Chowdhury et al.', 2023, 'Human Resource Management Review'),
    ('Entrepreneurial venture creation is being reshaped by artificial intelligence in the Fourth Industrial Revolution',
     'Chalmers et al.', 2021, 'Entrepreneurship Theory and Practice'),
    ('Wage growth for high-skilled workers diverged from that of routine workers over the period studied',
     'Baum-Snow and Pavan', 2013, 'The Review of Economics and Statistics'),
    ('The demand for social and analytical skills has risen relative to routine cognitive skills',
     'Autor et al.', 2006, 'American Economic Review'),
]


def render(fmt: str) -> str:
    """Render the 12 facts in one citation format, as a plausible report body."""
    out = ['## Empirical Evidence on AI and Labor Restructuring', '']
    for i, (fact, who, yr, venue) in enumerate(FACTS, 1):
        if fmt == 'A_numbered_marker':          # what POLARIS does today
            s = f'{fact}.[{i}]'
        elif fmt == 'B_parenthetical':          # (Author, Year)
            s = f'{fact} ({who}, {yr}).'
        elif fmt == 'C_narrative_author_year':  # cellcog's style: grammatical subject
            s = f'{who} ({yr}) show that {fact.lower()}.'
        elif fmt == 'D_narrative_with_journal':  # + the journal named in the sentence
            s = f'Writing in the {venue}, {who} ({yr}) show that {fact.lower()}.'
        elif fmt == 'E_journal_prefix':         # journal-first framing
            s = f'In their {yr} {venue} article, {who} show that {fact.lower()}.'
        else:
            raise ValueError(fmt)
        out.append(s)
        out.append('')
    if fmt == 'A_numbered_marker':
        out += ['## References', '']
        for i, (_, who, yr, venue) in enumerate(FACTS, 1):
            out.append(f'[{i}] {who} ({yr}). {venue}.')
    return '\n'.join(out)


def survives(cleaned: str, fmt: str) -> dict:
    """What survived, per fact?"""
    authors = sum(1 for (_, who, _, _) in FACTS if who.split()[0] in cleaned)
    years = sum(1 for (_, _, yr, _) in FACTS if str(yr) in cleaned)
    venues = sum(1 for (_, _, _, v) in FACTS if v.split()[0] in cleaned and v.split()[-1] in cleaned)
    facts = sum(1 for (f, _, _, _) in FACTS if f.split()[3] in cleaned)  # a content word from each fact
    markers = len(re.findall(r'\[\d+\]', cleaned))
    return {'authors': authors, 'years': years, 'venues': venues,
            'facts_intact': facts, 'markers_left': markers, 'words': len(cleaned.split())}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--runs', type=int, default=3)
    a = ap.parse_args()

    from utils.clean_article import ArticleCleaner  # noqa: E402
    from utils.api import AIClient                  # noqa: E402

    client = AIClient()
    cleaner = ArticleCleaner(client)

    formats = ['A_numbered_marker', 'B_parenthetical', 'C_narrative_author_year',
               'D_narrative_with_journal', 'E_journal_prefix']

    print(f"=== CLEANER-SURVIVAL TEST — {len(FACTS)} facts x {len(formats)} formats x {a.runs} runs ===")
    print("    (the cleaner is an LLM, so this is measured, not assumed)\n")
    print(f"{'format':<26} {'authors':>8} {'years':>6} {'venues':>7} {'facts':>6} {'[n]':>4}   (of 12)")
    print('-' * 74)

    results = {}
    for fmt in formats:
        raw = render(fmt)
        agg = []
        for r in range(a.runs):
            try:
                cleaned = cleaner.chunk_clean_article(raw, language='en')
            except Exception as e:
                print(f"  {fmt}: cleaner error {e}")
                continue
            agg.append(survives(cleaned, fmt))
            if r == 0:
                Path(f'outputs/cleaner_test_{fmt}.txt').write_text(cleaned)
        if not agg:
            continue
        m = {k: sum(d[k] for d in agg) / len(agg) for k in agg[0]}
        results[fmt] = m
        print(f"{fmt:<26} {m['authors']:>8.1f} {m['years']:>6.1f} {m['venues']:>7.1f} "
              f"{m['facts_intact']:>6.1f} {m['markers_left']:>4.0f}")

    print('\n=== VERDICT ===')
    best = max(results, key=lambda f: (results[f]['authors'] + results[f]['venues'])) if results else None
    for fmt, m in results.items():
        keeps_sourcing = m['authors'] >= 10 and m['facts_intact'] >= 10
        verdict = 'SURVIVES — sourcing visible to the judge' if keeps_sourcing else 'SOURCING DESTROYED'
        print(f"  {fmt:<26} {verdict}")
    if best:
        print(f"\n  ** USE: {best} **")
        print(f"     authors surviving: {results[best]['authors']:.1f}/12, "
              f"venues: {results[best]['venues']:.1f}/12")
    Path('outputs/cleaner_survival.json').write_text(json.dumps(results, indent=1))
    print('\nwrote outputs/cleaner_survival.json + outputs/cleaner_test_<fmt>.txt')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
