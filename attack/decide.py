import json, numpy as np
P=json.load(open('/home/polaris/polaris_project/attack/panel_rebuilt.json'))
SYS=sorted({r['sys'] for r in P}); TASKS=sorted({r['task'] for r in P}); n=len(P)
MDE=0.0094

def fe_beta(xraw, dim, rows=P, transform=None, sd_mode='pooled'):
    m=len(rows)
    x=np.array([r[xraw] for r in rows],float)
    if transform: x=transform(x)
    y=np.array([r[dim] for r in rows],float)
    tk=sorted({r['task'] for r in rows}); sy=sorted({r['sys'] for r in rows})
    tm={t:i for i,t in enumerate(tk)}; sm={s:i for i,s in enumerate(sy)}
    D=np.zeros((m,len(tk)+len(sy)-1))
    for i,r in enumerate(rows):
        D[i,tm[r['task']]]=1
        j=sm[r['sys']]
        if j>0: D[i,len(tk)+j-1]=1
    X=np.column_stack([D,x])
    XtX=X.T@X; Xinv=np.linalg.pinv(XtX); b=Xinv@X.T@y; e=y-X@b
    # cluster by task
    meat=np.zeros((X.shape[1],X.shape[1]))
    for t in tk:
        idx=[i for i,r in enumerate(rows) if r['task']==t]
        u=X[idx].T@e[idx]; meat+=np.outer(u,u)
    G=len(tk); c=G/(G-1)*(m-1)/(m-X.shape[1])
    V=c*Xinv@meat@Xinv
    sd = x.std(ddof=1)
    beta=b[-1]*sd; se=np.sqrt(max(V[-1,-1],0))*sd
    return beta, se, beta/se if se>0 else 0

print('='*104)
print('TWO-WAY FE (task x system), per +1 POOLED SD of the feature. n=898. SE clustered by task.')
print("k=5 MDE = +0.0094.  '*' = 95% CI excludes 0.   '!!' = 95% CI lies ENTIRELY ABOVE the MDE.")
print('='*104)
DIMS=['overall_score','readability','comprehensiveness','insight','instruction_following']
FEATS=[('words','log(words)',np.log),('sections','sections',None),('h3','H3 count',None),
       ('med_para','median para words',None),('med_para','log(med_para)',np.log),
       ('tables','tables',None),('n_paras','n paragraphs',None),
       ('bullets_per_1k','bullets/1k',None),('headings_per_1k','headings/1k',None),
       ('sent_per_para','sentences/para',None)]
print(f"{'feature':<20}" + ''.join(f'{d[:9]:>21}' for d in DIMS))
for f,lab,tf in FEATS:
    row=f'{lab:<20}'
    for d in DIMS:
        b,se,t=fe_beta(f,d,transform=tf)
        lo,hi=b-1.96*se,b+1.96*se
        star='!!' if lo>MDE else ('* ' if lo>0 or hi<0 else '  ')
        row+=f'{b:>+9.4f}({se:.4f}){star:>3}'
    print(row)
print()
print('='*104)
print('THE CHERRY-PICK CHECK: F2 says "top systems span 2,035 (dalpha) to 6,259 (lunon) median words,')
print('a 3x length range with a 0.004 score spread." -- here is the FULL system table (n=9).')
print('='*104)
print(f"{'system':<32}{'med words':>10}{'med sect':>10}{'med para':>10}{'overall':>9}{'read':>8}")
rows=[]
for s in sorted(SYS, key=lambda s:-np.mean([r['overall_score'] for r in P if r['sys']==s])):
    g=[r for r in P if r['sys']==s]
    mw=np.median([r['words'] for r in g]); ms=np.median([r['sections'] for r in g])
    mp=np.median([r['med_para'] for r in g])
    ov=np.mean([r['overall_score'] for r in g]); rd=np.mean([r['readability'] for r in g])
    rows.append((s,mw,ms,mp,ov,rd))
    print(f'{s:<32}{mw:>10.0f}{ms:>10.0f}{mp:>10.0f}{ov:>9.4f}{rd:>8.4f}')
mw=[r[1] for r in rows]; ov=[r[4] for r in rows]; mp=[r[3] for r in rows]; rd=[r[5] for r in rows]
def sp(a,b):
    ra=np.argsort(np.argsort(a)); rb=np.argsort(np.argsort(b)); return np.corrcoef(ra,rb)[0,1]
print(f'\n  BETWEEN-SYSTEM (n=9)  Spearman(median words, overall)   = {sp(mw,ov):+.3f}')
print(f'  BETWEEN-SYSTEM (n=9)  Pearson (log med words, overall)  = {np.corrcoef(np.log(mw),ov)[0,1]:+.3f}')
print(f'  BETWEEN-SYSTEM (n=9)  Spearman(median para, readability)= {sp(mp,rd):+.3f}')
print(f'  BETWEEN-SYSTEM (n=9)  Spearman(median para, overall)    = {sp(mp,ov):+.3f}')
