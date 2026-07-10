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

_SLATE = {
    'PG_BASKET_CONSUME_FINDING_DEDUP': '1',
    'PG_CONSOLIDATION_NLI': '0',
    'PG_FINDING_DEDUP_NLI': '0',
    'PG_FINDING_DEDUP_QUALITATIVE': '1',
    'PG_SWEEP_CREDIBILITY_REDESIGN': '1',
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
        return _row_field(rows[i], 'title', 'statement') if 0 <= i < len(rows) else ''

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
    }

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
