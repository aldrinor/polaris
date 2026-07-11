import json, sys, re
cp3=sys.argv[1]
d=json.load(open(cp3))
b=d['payload']['baskets']
cs=d['payload']['consolidation_summary']
print('=== SUMMARY ===')
print(json.dumps(cs,indent=1))
print('total_baskets',len(b))
mm=[x for x in b if x['member_count']>1]
mc=[x for x in b if x['corroboration_count']>1]
print('multi_member',len(mm),'multi_corrob',len(mc))
def hay(x):
    return (x['representative_statement']+' '+' '.join(x['member_urls'])+' '+' '.join(x['member_hosts'])).lower()

# Eloundou
print('\n=== ELOUNDOU / GPTs-are-GPTs baskets (READ) ===')
el=[x for x in b if 'eloundou' in hay(x) or '2303.10130' in hay(x) or 'gpts are gpts' in hay(x)]
print('count',len(el))
for x in el:
    print('--- corrob',x['corroboration_count'],'mem',x['member_count'],'key',x['finding_key'])
    print('  REP:',repr(x['representative_statement'][:220]))
    print('  urls:',x['member_urls'][:5])
    print('  hosts:',x['member_hosts'][:6])

# short/chrome-looking rep candidates (LOCATE only; verdict by reading)
print('\n=== SHORT / POSSIBLE-CHROME REP CANDIDATES (READ & JUDGE) ===')
chrome_pat=re.compile(r'cookie|subscribe|sign in|log in|newsletter|404|not found|captcha|enable javascript|access denied|skip to|menu|all rights reserved|privacy policy|terms of use|search text|add_circle',re.I)
cand=[x for x in b if len(x['representative_statement'].split())<6 or chrome_pat.search(x['representative_statement'])]
print('candidates',len(cand))
for x in cand[:60]:
    print('  c%d m%d | %r | %s'%(x['corroboration_count'],x['member_count'],x['representative_statement'][:120],(x['member_urls'][0][:70] if x['member_urls'] else '')))
