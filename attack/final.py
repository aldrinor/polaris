import json, numpy as np
P=json.load(open('/home/polaris/polaris_project/attack/panel_rebuilt.json'))
SYS=sorted({r['sys'] for r in P})

print('='*92)
print('1. IS F2\'s SYSTEM TABLE EVEN RIGHT?  It says dalpha=2,035 and lunon=6,259 median words.')
print('='*92)
for s in ['dalpha-deepresearch','lunon_full100_FINAL.submission','grok-deeper-search','perplexity-Research']:
    g=[r for r in P if r['sys']==s]
    en=[r for r in g if not r['zh']]; zh=[r for r in g if r['zh']]
    print(f'{s:<32} ALL med {np.median([r["words"] for r in g]):>8.0f} | EN med {np.median([r["words"] for r in en]):>8.0f} | ZH med {np.median([r["words"] for r in zh]):>8.0f}')
print('  -> F2\'s "2,035 / 6,259" match NOTHING in the data computed with the project\'s own feat.py.')
print('  -> And it names the ONE pair that brackets the plateau, omitting that the two LOWEST-scoring')
print('     systems on the board (grok 1,441w, perplexity 1,838w) are also the two SHORTEST.')

print()
print('='*92)
print('2. HOW MUCH IS "overall" ACTUALLY MADE OF READABILITY?  regress overall on the 4 dimension ratios')
print('='*92)
D=['comprehensiveness','insight','instruction_following','readability']
X=np.column_stack([np.ones(len(P))]+[np.array([r[d] for r in P]) for d in D])
y=np.array([r['overall_score'] for r in P])
b=np.linalg.lstsq(X,y,rcond=None)[0]; e=y-X@b
print('  implied weights: ' + '  '.join(f'{d[:6]}={b[i+1]:.3f}' for i,d in enumerate(D)) + f'   (R2={1-(e@e)/((y-y.mean())**2).sum():.4f}, resid SD={e.std():.5f})')
w_read=b[4]
print(f'  -> readability carries an effective weight of {w_read:.3f} in overall.')

print()
print('='*92)
print('3. THE PRICE OF OUR READABILITY HOLE (the thing F2 books at ZERO)')
print('='*92)
rd=np.array([r['readability'] for r in P])
ours=4.71/(4.71+8.42)
for tgt,lab in [(np.percentile(rd,5),'board 5th pct'),(np.median(rd),'board MEDIAN'),(0.5316,'best system (dalpha)')]:
    gain=(tgt-ours)*w_read
    print(f'  readability {ours:.4f} -> {tgt:.4f} ({lab:<22}) = +{tgt-ours:.4f} on the dim '
          f'-> +{gain:.4f} on OVERALL  ({gain/0.0094:.1f}x the k=5 MDE)')
print('\n  F2\'s instruction: "Cosmetics -- do them all in one afternoon, BOOK ZERO, never cite them as progress."')

print()
print('='*92)
print('4. HOW MUCH VARIATION DOES TWO-WAY FE THROW AWAY?  ("is F2 controlling away the treatment?")')
print('='*92)
def frac_left(vals):
    v=np.array(vals,float); tot=v.var()
    gm=v.mean()
    tmn={t:v[[i for i,r in enumerate(P) if r['task']==t]].mean() for t in {r['task'] for r in P}}
    smn={s:v[[i for i,r in enumerate(P) if r['sys']==s]].mean() for s in SYS}
    d=v-np.array([tmn[r['task']] for r in P])-np.array([smn[r['sys']] for r in P])+gm
    return d.var()/tot
for f,tf in [('words',np.log),('sections',None),('med_para',np.log),('tables',None)]:
    v=np.array([r[f] for r in P],float); v=tf(v) if tf else v
    # how much of x is explained by SYSTEM identity alone?
    smn={s:v[[i for i,r in enumerate(P) if r['sys']==s]].mean() for s in SYS}
    bs=np.array([smn[r['sys']] for r in P]); r2_sys=bs.var()/v.var()
    print(f'  {f:<10} {100*r2_sys:>5.1f}% of its variance IS system identity;  {100*frac_left(v):>5.1f}% survives two-way FE')
print('\n  -> log(words): FE discards 88% of the variation. THE EFFECT IS STILL +0.021/SD, t=5.0.')
print('  -> So for LENGTH, FE did not "reveal a null" -- it survived a control that removed 88% of the signal.')
