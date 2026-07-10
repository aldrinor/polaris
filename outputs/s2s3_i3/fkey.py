import json
d=json.load(open('/workspace/s2s3_wt/outputs/s2s3_i3/s3/cp3_basket_snapshot.json'))
B=d['payload']['baskets']
cp2=json.load(open('/workspace/s2s3_wt/outputs/s2s3_i3/s2/cp2_corpus_snapshot.json'))
rows={str(r.get('evidence_id','')):r for r in cp2['evidence_for_gen'] if isinstance(r,dict)}
def body(e):
    r=rows.get(e,{}); return (r.get('direct_quote') or r.get('statement') or '')
for tgt in ['ev_991','ev_150']:
    b=next(b for b in B if b['representative_evidence_id']==tgt)
    print('==== rep=%s corrob=%d members=%d'%(tgt,b['corroboration_count'],b['member_count']))
    print('  finding_key=', b.get('finding_key'))
    print('  rep_stmt=', (b.get('representative_statement','') or '')[:130])
    for e in b.get('member_evidence_ids',[]):
        print('  --%s:: %s'%(e, body(e)[:150].replace(chr(10),' ')))
