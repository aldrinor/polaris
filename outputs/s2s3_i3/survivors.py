import json,re
d=json.load(open('/workspace/s2s3_wt/outputs/s2s3_i3/s3/cp3_basket_snapshot.json'))
B=d['payload']['baskets']
cp2=json.load(open('/workspace/s2s3_wt/outputs/s2s3_i3/s2/cp2_corpus_snapshot.json'))
rows={str(r.get('evidence_id','')):r for r in cp2['evidence_for_gen'] if isinstance(r,dict)}
def body(e):
    r=rows.get(e,{}); return (r.get('direct_quote') or r.get('statement') or '')
def nonascii_ratio(s):
    s=s[:1000]
    if not s: return 0
    na=sum(1 for c in s if ord(c)>127 or (ord(c)<32 and c not in '\n\t\r'))
    return na/len(s)
# member-level survivor scan
allmembers=set()
for b in B:
    for e in b.get('member_evidence_ids',[]): allmembers.add(e)
print('distinct member eids across baskets:', len(allmembers))
binary=[]; navshell=[]; scholar=[]; captcha=[]
navpat=['navigated to','news-insights','/events','/about-','mobile-search-modal','skip to content','sign in','cookie']
for e in sorted(allmembers):
    bd=body(e)
    if nonascii_ratio(bd)>0.15 and len(bd)>200: binary.append(e)
    low=bd[:300].lower()
    if 'navigated to' in low or ('/events' in low and 'butlersnow' in low) or 'mobile-search-modal' in low: navshell.append(e)
    if 'scholar.google.com/citations' in bd[:400]: scholar.append(e)
    if 'just a moment' in low or 'confirm you are human' in low or 'verifying your browser' in low: captcha.append(e)
print('MEMBER binary-garbled:', len(binary), binary[:12])
print('MEMBER navshell:', len(navshell), navshell[:12])
print('MEMBER scholar-citations chrome:', len(scholar), scholar[:12])
print('MEMBER captcha:', len(captcha), captcha[:12])
# FRAGMENTS: single-member baskets total
sm=[b for b in B if b['member_count']==1]
print('single-member baskets:', len(sm), 'of', len(B))
