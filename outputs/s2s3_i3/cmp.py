import json
def load(p): return json.load(open(p))['payload']['baskets']
A=load('/workspace/s2s3_wt/outputs/s2s3_i3/s3/cp3_basket_snapshot.json')   # before fix
Bb=load('/workspace/s2s3_wt/outputs/s2s3_i3/s3b/cp3_basket_snapshot.json') # after fix
def top(B,label):
    mc=sorted([b for b in B if b['corroboration_count']>1], key=lambda x:-x['corroboration_count'])
    print('=== %s: baskets=%d multi_corrob=%d  top corrob:'%(label,len(B),len(mc)))
    for b in mc[:8]:
        print('   corrob=%d members=%d rep=%s | %s'%(b['corroboration_count'],b['member_count'],b['representative_evidence_id'],(b.get('representative_statement','') or '')[:70]))
top(A,'BEFORE fix (s3)')
top(Bb,'AFTER fix (s3b)')
# did the garble seeds vanish from any basket?
def has(B,eid):
    return [ (b['representative_evidence_id'],b['corroboration_count'],b['member_count']) for b in B if eid in (b.get('member_evidence_ids',[]) or []) ]
for e in ['ev_1091','ev_169','ev_056','ev_1052','ev_1196','ev_304','ev_507','ev_989']:
    print('member %s : before=%s after=%s'%(e, has(A,e), has(Bb,e)))
