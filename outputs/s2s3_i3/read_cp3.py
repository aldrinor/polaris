import json,re
d=json.load(open('/workspace/s2s3_wt/outputs/s2s3_i3/s3/cp3_basket_snapshot.json'))
B=d['payload']['baskets']
print('TOTAL BASKETS', len(B))

def hay(b):
    parts=[b.get('representative_statement','') or '']
    parts+= b.get('member_urls',[]) or []
    parts+= b.get('member_evidence_ids',[]) or []
    parts+= [str(x) for x in (b.get('finding_key',[]) or [])]
    return ' '.join(parts).lower()

# 1) ELOUNDOU
el=[i for i,b in enumerate(B) if 'eloundou' in hay(b) or 'gpts are gpts' in hay(b) or 'gpts_are_gpts' in hay(b)]
print('=== ELOUNDOU baskets:', len(el))
for i in el:
    b=B[i]
    print('  b#%d members=%d corrob=%d rep=%s'%(i,b['member_count'],b['corroboration_count'],b['representative_evidence_id']))
    print('     stmt:', (b.get('representative_statement','') or '')[:150])
    print('     eids:', b.get('member_evidence_ids',[])[:15])
    print('     urls:', [u[:60] for u in (b.get('member_urls',[]) or [])][:6])

# 2) CHROME/OFFTOPIC scan across all baskets (context-level markers)
chrome_pat=['just a moment','confirm you are human','verifying your browser','enable javascript','cloudflare','captcha','access denied','are you a robot','loading...','page not found','404 not found']
print('=== CHROME-suspect baskets ===')
ch=0
for i,b in enumerate(B):
    h=hay(b)
    st=(b.get('representative_statement','') or '')
    if any(p in h for p in chrome_pat) or st.strip().lower().startswith('%pdf'):
        ch+=1
        print('  b#%d rep=%s corrob=%d | %s'%(i,b['representative_evidence_id'],b['corroboration_count'], st[:90]))
print('CHROME-suspect count:', ch)
