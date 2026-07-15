import json, numpy as np
P=json.load(open('/home/polaris/polaris_project/attack/panel_rebuilt.json'))
SYS=sorted({r['sys'] for r in P}); TASKS=sorted({r['task'] for r in P}); n=len(P)

def twoway_X(rows):
    m=len(rows); tk=sorted({r['task'] for r in rows}); sy=sorted({r['sys'] for r in rows})
    tm={t:i for i,t in enumerate(tk)}; sm={s:i for i,s in enumerate(sy)}
    D=np.zeros((m,len(tk)+len(sy)-1))
    for i,r in enumerate(rows):
        D[i,tm[r['task']]]=1
        j=sm[r['sys']]
        if j>0: D[i,len(tk)+j-1]=1
    return D, tk

def fit(rows, extra, dim='overall_score'):
    D,tk=twoway_X(rows); X=np.column_stack([D,extra]); y=np.array([r[dim] for r in rows],float)
    Xinv=np.linalg.pinv(X.T@X); b=Xinv@X.T@y; e=y-X@b
    meat=np.zeros((X.shape[1],X.shape[1]))
    for t in tk:
        idx=[i for i,r in enumerate(rows) if r['task']==t]
        u=X[idx].T@e[idx]; meat+=np.outer(u,u)
    G=len(tk); c=G/(G-1)*(len(rows)-1)/(len(rows)-X.shape[1])
    V=c*Xinv@meat@Xinv
    k=extra.shape[1] if extra.ndim>1 else 1
    return b[-k:], np.sqrt(np.maximum(np.diag(V)[-k:],0))

print('='*96)
print('DOES LENGTH SATURATE?  Two-way FE, WORD BINS (ref = 2000-3500w).  Coef = score vs the ref bin.')
print('This is the test that could still rescue F2\'s conclusion about word targets.')
print('='*96)
BINS=[(0,2000),(2000,3500),(3500,5000),(5000,8000),(8000,12000),(12000,20000),(20000,10**9)]
REF=1
cols=[]; labs=[]
for i,(lo,hi) in enumerate(BINS):
    if i==REF: continue
    cols.append(np.array([1.0 if lo<=r['words']<hi else 0.0 for r in P]))
    labs.append(f'{lo}-{hi if hi<10**9 else "inf"}')
E=np.column_stack(cols)
b,se=fit(P,E)
print(f"{'bin':<14}{'n':>5}{'coef vs 2000-3500':>20}{'SE':>9}{'95% CI':>22}")
for i,(lo,hi) in enumerate(BINS):
    cnt=sum(1 for r in P if lo<=r['words']<hi)
    if i==REF:
        print(f'{str(lo)+"-"+str(hi):<14}{cnt:>5}{"0 (reference)":>20}')
        continue
    j=labs.index(f'{lo}-{hi if hi<10**9 else "inf"}')
    lo_,hi_=b[j]-1.96*se[j], b[j]+1.96*se[j]
    print(f'{labs[j]:<14}{cnt:>5}{b[j]:>+20.4f}{se[j]:>9.4f}{"["+format(lo_,"+.4f")+", "+format(hi_,"+.4f")+"]":>22}')

print()
print('='*96)
print('OUR POSITION vs THE ESTIMATION SUPPORT')
print('='*96)
mp=np.array([r['med_para'] for r in P],float); lmp=np.log(mp)
print(f'log(med_para): corpus mean {lmp.mean():.3f}  SD {lmp.std(ddof=1):.3f}   (median para = {np.exp(lmp.mean()):.0f}w)')
z=(np.log(677)-lmp.mean())/lmp.std(ddof=1)
print(f'POLARIS med_para = 677w -> log = {np.log(677):.3f} -> z = {z:+.2f} SD above the corpus mean')
b_read,se_read = -0.0027, 0.0010   # from previous run, log(med_para) -> readability
print(f'\nIf the FE slope on readability (-0.0027/SD, SE 0.0010) held linearly out to our point:')
print(f'   predicted readability penalty at 677w vs corpus mean = {z*b_read:+.4f}  (95% CI {z*(b_read+1.96*se_read):+.4f} .. {z*(b_read-1.96*se_read):+.4f})')
print(f'   ... but ONLY 3/898 articles are anywhere near 677w, so this is EXTRAPOLATION, not measurement.')

rd=np.array([r['readability'] for r in P],float)
print(f'\nREADABILITY RATIO on the board: min {rd.min():.4f} p5 {np.percentile(rd,5):.4f} med {np.median(rd):.4f} p95 {np.percentile(rd,95):.4f} max {rd.max():.4f}')
ours = 4.71/(4.71+8.42)
print(f'POLARIS readability ratio (from the judge\'s raw 4.71 vs 8.42) = {ours:.4f}')
print(f'  -> that is {100*(rd<ours).mean():.1f}th percentile of 898 articles; {(rd<ours).sum()} of 898 score below us.')
print(f'  -> the WORST system on the board (grok) averages {rd.min():.4f} at the article level, system-mean 0.4572.')
print(f'  -> we are {0.4572-ours:+.4f} BELOW the worst system on the board.')
print(f'  -> the ENTIRE between-system readability spread on the board is {0.5316-0.4572:.4f}. Our deficit to the floor is {0.4572-ours:.4f}.')
