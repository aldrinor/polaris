import json,re
d=json.load(open('/workspace/s2s3_wt/outputs/s2s3_i3/s3c/cp3_basket_snapshot.json'))
B=d['payload']['baskets']
cp2=json.load(open('/workspace/s2s3_wt/outputs/s2s3_i3/s2/cp2_corpus_snapshot.json'))
rows={str(r.get('evidence_id','')):r for r in cp2['evidence_for_gen'] if isinstance(r,dict)}
def bd(e): r=rows.get(e,{}); return (r.get('direct_quote') or r.get('statement') or '')
def na_ratio(s):
    s=s[:800]
    if not s: return 0
    return sum(1 for c in s if ord(c)>127 or (ord(c)<32 and c not in '\n\t\r'))/len(s)
# member-level chrome/binary survivors
allm=set()
for b in B:
    for e in b.get('member_evidence_ids',[]): allm.add(e)
binary=[]; navshell=[]
for e in allm:
    b=bd(e); low=b[:300].lower()
    toks=b[:800].split()
    if len(toks)>=20:
        wl=sum(1 for t in toks if re.fullmatch(r'[A-Za-z]{2,}[.,;:]?',t))
        if wl/len(toks)<0.10: binary.append(e)
    if 'navigated to' in low: navshell.append(e)
print('members total',len(allm),'| binary-survivors',len(binary),binary[:8],'| navshell',len(navshell),navshell[:8])
# eloundou
el=[b for b in B if 'eloundou' in (b.get('representative_statement','') or '').lower() or 'gpts_are_gpts' in ' '.join(b.get('member_evidence_ids',[])).lower() or 'gpts are gpts' in (b.get('representative_statement','') or '').lower() or any('2303.10130' in u for u in (b.get('member_urls',[]) or []))]
print('ELOUNDOU-related baskets:',len(el))
for b in el:
    print('  m=%d corrob=%d rep=%s | %s'%(b['member_count'],b['corroboration_count'],b['representative_evidence_id'],(b.get('representative_statement','') or '')[:70]))
    print('    eids',b.get('member_evidence_ids',[])[:8])
# top corrob distinctness
print('--- corrob=4 ev_941 (Noy-Zhang?) member urls ---')
b=next(b for b in B if b['representative_evidence_id']=='ev_941')
for u,h in zip(b.get('member_urls',[]),b.get('member_hosts',[])): print('   ',h,u[:80])
