#!/usr/bin/env python3
"""S3 CONSOLIDATE replay harness — build cp3_basket_snapshot.json from a cp2 corpus.

Standalone CLI (LAW VII): loads an S2 cp2_corpus_snapshot.json, runs the REAL production
consolidation (src/polaris_graph/synthesis/finding_dedup.dedup_by_finding) with the deployed
flag slate, and writes the cp3 basket snapshot in the same schema the sweep persists. Pure
CPU (NLI OFF) => deterministic, seconds. No LLM, no network.
"""
from __future__ import annotations
import argparse, hashlib, json, os, sys, time
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

# S2/S3 re-pass Fix 3(b): the deployed S3 slate now flips the SEMANTIC merge authority ON —
# ``PG_CONSOLIDATION_NLI`` (bidirectional-NLI over the literal clusters) and
# ``PG_FINDING_DEDUP_NLI`` — so same-meaning-different-words findings MERGE instead of
# fragmenting on the numeric-tuple key. The Fix-1/3c/4/5/6 kill-switches are pinned ON here
# for an explicit, self-documenting deployed slate (each defaults ON in code; pinning makes
# the run reproducible and the parity with the production sweep visible).
_SLATE = {
    'PG_BASKET_CONSUME_FINDING_DEDUP': '1',
    'PG_CONSOLIDATION_NLI': '1',            # Fix 3(b): semantic merge authority ON
    'PG_FINDING_DEDUP_NLI': '1',            # Fix 3(b): finding-dedup NLI leg ON
    'PG_FINDING_DEDUP_QUALITATIVE': '1',
    'PG_SWEEP_CREDIBILITY_REDESIGN': '1',
    'PG_SAMEWORK_CROSSMIRROR': '1',         # Fix 4: cross-mirror same-work identity
    'PG_CI_ANTIBOT_SHELL': '1',             # Fix 1(a)(b): general anti-bot / shell chrome
    'PG_FINDING_DEDUP_KEY_HYGIENE': '1',    # Fix 3(c): garbage subject/value key guard
    'PG_CORROBORATION_DISTINCT_WORKS': '1',  # Fix 5: corroboration = distinct works
    'PG_CORROBORATION_DERIVATIVE_PRESS': '1',  # Fix 6: derivative-press excluded from count
    'PG_CONSOLIDATION_NLI_QUALITATIVE': '1',  # Fix 3(a): NLI merges qualitative baskets too
    'PG_CONSOLIDATION_NLI_SUBBUCKET': '1',    # Fix 3: pre-bucket over-cap buckets so large
                                              # same-value clusters still NLI-merge (the two
                                              # 44k/51k-pair buckets were skipped otherwise)
}


def _row_field(row, *names):
    for n in names:
        v = row.get(n)
        if v:
            return str(v)
    return ''


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--cp2', required=True)
    ap.add_argument('--out', required=True)
    args = ap.parse_args()

    for k, v in _SLATE.items():
        os.environ[k] = v

    from src.polaris_graph.authority.data_loader import load_authority_data
    from src.polaris_graph.synthesis.finding_dedup import dedup_by_finding

    cp2_path = Path(args.cp2)
    data = json.load(cp2_path.open(encoding='utf-8'))
    rows = [r for r in data.get('evidence_for_gen', []) if isinstance(r, dict)]
    question = str(data.get('question', '') or '')
    domain = str(data.get('domain', '') or 'workforce')
    slug = str(data.get('slug', '') or '')

    gov = load_authority_data()['psl_gov_suffixes']
    res = dedup_by_finding(rows, gov_suffixes=gov, domain=domain)

    def _eid(i):
        return str(rows[i].get('evidence_id', '')) if 0 <= i < len(rows) else ''

    def _url(i):
        return _row_field(rows[i], 'source_url', 'url') if 0 <= i < len(rows) else ''

    def _tier(i):
        return (str(rows[i].get('tier', '') or 'UNKNOWN')) if 0 <= i < len(rows) else 'UNKNOWN'

    def _stmt(i):
        # Fix 7/9 (Fable): the representative_statement must be a READABLE, COMPLETE claim
        # sentence — not the page title, not a mid-word value-window ('us change the task...'),
        # not letter-spaced extraction garbage. General/question-agnostic: collapse letter
        # spacing, split into complete sentences (>=5 words), and prefer the COMPLETE sentence
        # carrying the numeric finding; fall back to the first complete sentence, then the
        # snippet, then the title.
        import re as _re
        from src.polaris_graph.synthesis.finding_dedup import _collapse_letter_spacing
        if not (0 <= i < len(rows)):
            return ''
        row = rows[i]
        body = _collapse_letter_spacing(_row_field(row, 'direct_quote', 'statement'))
        # Fix 4b/9: skip a nav/chrome/menu sentence when a clean content sentence exists, so the
        # representative_statement never reads as boilerplate (login / search-UI / share / cookie).
        _chrome = _re.compile(
            r'log ?in|sign ?in|subscribe|cookie|search text|search type|logical operator|'
            r'add_circle|remove_circle|skip to|newsletter|\bmenu\b|share this|©|›|»',
            _re.IGNORECASE)
        sentences = [
            s.strip() for s in _re.split(r'(?<=[.!?])\s+', body.strip())
            if len(s.split()) >= 5 and (s.strip()[:1].isupper() or s.strip()[:1].isdigit())
            and not _chrome.search(s)
        ]
        value_tok = None
        try:
            from src.polaris_graph.retrieval.contradiction_detector import extract_numeric_claims
            claims = extract_numeric_claims([row])
            if claims:
                v = float(getattr(claims[0], 'value', 0.0) or 0.0)
                value_tok = (str(int(v)) if v == int(v) else str(v))
                snip = _collapse_letter_spacing((getattr(claims[0], 'context_snippet', '') or '').strip())
        except Exception:
            claims = []
            snip = ''
        # Fix 9: a COMPLETE sentence containing the finding value is the best representative.
        if value_tok:
            for s in sentences:
                if value_tok in s:
                    return s[:300]
        if sentences:
            return sentences[0][:300]
        if claims and snip:
            return snip[:300]
        if body.strip():
            return body.strip()[:300]
        return _row_field(row, 'title', 'statement')

    baskets = []
    for c in res.clusters:
        mi = list(c.member_indices)
        baskets.append({
            'corroboration_count': c.corroboration_count,
            'finding_key': list(c.finding_key),
            'member_count': len(mi),
            'member_evidence_ids': [_eid(i) for i in mi],
            'member_hosts': list(c.member_hosts),
            'member_tiers_weight': [_tier(i) for i in mi],
            'member_urls': [_url(i) for i in mi],
            'representative_evidence_id': _eid(c.representative_index),
            'representative_statement': _stmt(c.representative_index),
        })

    sw = res.same_work
    sw_groups_payload = []
    sw_total = 0
    sw_multi = 0
    if sw is not None:
        sw_total = len(sw.groups)
        for g in sw.groups:
            if len(g.member_indices) > 1:
                sw_multi += 1
                sw_groups_payload.append({
                    'same_work_id': g.same_work_id,
                    'canonical_index': g.canonical_index,
                    'member_evidence_ids': list(g.member_evidence_ids),
                    'member_urls': list(g.member_urls),
                })

    multi_member = sum(1 for b in baskets if b['member_count'] > 1)
    multi_corrob = sum(1 for b in baskets if b['corroboration_count'] > 1)

    consolidation_summary = {
        'basket_total': len(baskets),
        'basket_multi_member': multi_member,
        'basket_multi_corroboration': multi_corrob,
        'raw_row_count': res.raw_row_count,
        'distinct_finding_count': res.distinct_finding_count,
        'collapsed_row_count': res.collapsed_row_count,
        'nli_merge_count': res.nli_merge_count,
        'qualitative_basket_count': res.qualitative_basket_count,
        'same_work_groups': sw_total,
        'same_work_multi_member': sw_multi,
        'same_work_dropped_captcha': len(sw.dropped_captcha_indices) if sw else 0,
        'same_work_dropped_prefix': len(sw.dropped_prefix_indices) if sw else 0,
        # Fix 1(e): recover-before-delete disclosure counts (§-1.3.1 fail-loud).
        'same_work_dropped_captcha_recovered': len(sw.dropped_captcha_recovered) if sw else 0,
        'same_work_dropped_captcha_gap': len(sw.dropped_captcha_gap) if sw else 0,
    }

    # Fix 1(e): DISCLOSE every chrome deletion (row count + reason) — §-1.3.1(a) fail-loud,
    # never silent. A RECOVERED drop's work survives via a clean same-work sibling; a GAP
    # drop is a coverage loss disclosed here, never fabricated.
    chrome_deletion_disclosure = []
    if sw is not None:
        for i in sorted(sw.dropped_captcha_indices):
            chrome_deletion_disclosure.append({
                'evidence_id': _eid(i),
                'url': _url(i),
                'title': (_row_field(rows[i], 'title', 'statement')[:120] if 0 <= i < len(rows) else ''),
                'reason': 'chrome_non_source',
                'recovery': ('recovered_via_same_work_sibling'
                             if i in sw.dropped_captcha_recovered else 'coverage_gap'),
            })

    # Fix 11 (Fable): ONE merged, machine-readable deletion disclosure that composition can cite
    # in Methods (§-1.3.1 fail-loud). It unifies the S2 whole-source / line drops (from the
    # sibling s2/summary.json produced by the line screen) with the S3 same-work chrome deletions
    # above — instead of the two living in separate artifacts (s2/disclosure.txt vs this snapshot).
    unified_deletion_disclosure = {
        's3_chrome_deletions': {
            'count': len(chrome_deletion_disclosure),
            'by_reason': {'chrome_non_source': len(chrome_deletion_disclosure)},
            'recovered': consolidation_summary['same_work_dropped_captcha_recovered'],
            'coverage_gap': consolidation_summary['same_work_dropped_captcha_gap'],
            'rows': chrome_deletion_disclosure,
        },
        's2_line_screen': {},
    }
    try:
        s2_summary_path = cp2_path.parent / 'summary.json'
        if s2_summary_path.exists():
            s2s = json.load(s2_summary_path.open(encoding='utf-8'))
            unified_deletion_disclosure['s2_line_screen'] = {
                'totals': s2s.get('totals', {}),
                'by_class': {
                    'cond_a_lines_dropped_quoted': len(s2s.get('cond_a_lines_dropped_quoted', []) or []),
                    'cond_b_no_credible_whole_drop': len(s2s.get('cond_b_no_credible_whole_drop', []) or []),
                    'cond_c_mixed_partial_keep': len(s2s.get('cond_c_mixed_partial_keep', []) or []),
                    'cond_d_scope': len(s2s.get('cond_d_scope', []) or []),
                    'cond_e_fail_open': len(s2s.get('cond_e_fail_open', []) or []),
                },
                'source': 's2/summary.json',
            }
    except Exception as _exc:  # fail-loud but never crash the harness
        unified_deletion_disclosure['s2_line_screen'] = {'error': str(_exc)}

    upstream_sha = hashlib.sha256(cp2_path.read_bytes()).hexdigest()
    envelope = {
        'schema_version': data.get('schema_version', 1),
        'stage': 's3_consolidate',
        'run_id': str(data.get('run_id', '') or ('SWEEP_' + slug)),
        'created_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        'question': question,
        'question_sha': hashlib.sha256(question.encode('utf-8')).hexdigest(),
        'domain': domain,
        'slug': slug,
        'flag_slate': dict(_SLATE),
        'faithfulness_invariant': 'DATA ONLY; no verdict stored; a resume re-runs every gate.',
        'upstream': {'name': cp2_path.name, 'sha256': upstream_sha},
        'adjustments_applied': [],
        'payload': {
            'baskets': baskets,
            'consolidation_summary': consolidation_summary,
            'contradiction_edges': [],
            'same_work_groups': sw_groups_payload,
            'chrome_deletion_disclosure': chrome_deletion_disclosure,
            'deletion_disclosure': unified_deletion_disclosure,  # Fix 11: merged S2+S3
        },
    }
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / 'cp3_basket_snapshot.json'
    out_path.write_text(json.dumps(envelope, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    print('wrote', out_path, 'baskets', len(baskets))
    print('consolidation_summary', json.dumps(consolidation_summary))
    print('upstream_sha', upstream_sha[:16])
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
