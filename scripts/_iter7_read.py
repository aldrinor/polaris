import json,re,sys
cp3=sys.argv[1]
d=json.load(open(cp3))
p=d['payload']; bs=p['payload']['baskets'] if 'payload' in p else p['baskets']
cs=p['consolidation_summary']
print('BASKET_COUNT',len(bs))
for k in ['raw_row_count','distinct_finding_count','same_work_groups','basket_total','basket_multi_member','basket_multi_corroboration','nli_merge_count','collapsed_row_count','rep_invariant_merge_count']:
    print('  cs',k,'=',cs.get(k))
print('  numeric_confirm',json.dumps(cs.get('numeric_confirm_telemetry')))
print('  nli_stats',json.dumps({k:cs.get('nli_score_stats',{}).get(k) for k in ['n_texts','edges','scored_fraction','degraded']}))
# corroboration distinct-works evidence
multi=[(i,b['corroboration_count'],b['member_count']) for i,b in enumerate(bs) if b['member_count']>1]
print('MULTI_MEMBER_BASKETS',len(multi))
same_work_cc1=[x for x in multi if x[1]==1]
print('  of which cc==1 (refetch/same-work collapsed):',len(same_work_cc1))
print('  of which cc>1 (genuine multi-work corroboration):',len([x for x in multi if x[1]>1]))
# Eloundou
elo={'eloundou_gpts_are_gpts','ev_886','ev_883','ev_887','ev_890','ev_880','ev_879','ev_878','ev_047','ev_1112','ev_891','ev_488'}
elob=[i for i,b in enumerate(bs) if set(b['member_evidence_ids'])&elo]
print('ELOUNDOU_BASKETS',len(elob),elob)
for i in elob:
    print('  #%03d cc=%s mc=%s :: %s'%(i,bs[i]['corroboration_count'],bs[i]['member_count'],(bs[i]['representative_statement'] or '')[:110].replace(chr(10),' ')))
# byte-identical dup
def norm(s): return re.sub(r'\s+',' ',(s or '').strip().lower())[:200]
from collections import defaultdict
g=defaultdict(list)
for i,b in enumerate(bs): g[norm(b['representative_statement'])].append(i)
dups=[(k,v) for k,v in g.items() if len(v)>1]
print('BYTE_IDENTICAL_DUP_GROUPS',len(dups),'excess',sum(len(v)-1 for _,v in dups))
for k,v in dups: print('  ',v,'::',k[:90])
# dump read file
out=[]
for i,b in enumerate(bs):
    out.append('#%03d cc=%s mc=%s host=%s'%(i,b['corroboration_count'],b['member_count'],'|'.join(sorted(set(b['member_hosts']))[:3])))
    out.append('   EIDS '+' | '.join(b['member_evidence_ids'][:6]))
    out.append('   REP '+(b['representative_statement'] or '')[:300].replace(chr(10),' '))
open('/workspace/s2s3_wt/outputs/s2s3_repass/iter7/all_baskets_read.txt','w').write(chr(10).join(out))
print('WROTE all_baskets_read.txt')
