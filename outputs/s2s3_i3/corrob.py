import json
d=json.load(open('/workspace/s2s3_wt/outputs/s2s3_i3/s3/cp3_basket_snapshot.json'))
B=d['payload']['baskets']
# corroboration distinctness: for multi-corrob baskets, print members' urls+eids to judge distinct works vs refetch triplets
mc=sorted([b for b in B if b['corroboration_count']>1], key=lambda x:-x['corroboration_count'])
print('MULTI-CORROBORATION baskets:', len(mc))
for b in mc[:18]:
    print('--- corrob=%d members=%d rep=%s'%(b['corroboration_count'],b['member_count'],b['representative_evidence_id']))
    print('    stmt:', (b.get('representative_statement','') or '')[:110])
    urls=b.get('member_urls',[]) or []
    hosts=b.get('member_hosts',[]) or []
    for u,h in zip(urls, hosts):
        print('      host=%-28s %s'%(str(h)[:28], str(u)[:80]))
