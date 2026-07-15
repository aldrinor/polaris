import json, numpy as np, statistics as st
P = json.load(open('/home/polaris/polaris_project/attack/panel_rebuilt.json'))
SYS=sorted({r['sys'] for r in P}); TASKS=sorted({r['task'] for r in P})
n=len(P)
def dm(vals, by):
    vals=np.asarray(vals,float); out=vals.copy()
    gm=vals.mean()
    if 'task' in by:
        m={t:vals[[i for i,r in enumerate(P) if r['task']==t]].mean() for t in TASKS}
        out=out-np.array([m[r['task']] for r in P])+gm
    if 'sys' in by:
        m={s:vals[[i for i,r in enumerate(P) if r['sys']==s]].mean() for s in SYS}
        out=out-np.array([m[r['sys']] for r in P])+gm
    return out

lw=np.log(np.array([r['words'] for r in P],float))
sec=np.array([r['sections'] for r in P],float)
y=np.array([r['overall_score'] for r in P],float)

print('JOINT MODEL  y ~ log(words) + sections   (both regressors, as F2 tabulates them side by side)')
print(f"{'spec':<14}{'':>4}{'per POOLED SD':>15}{'per DEMEANED SD':>18}{'F2 quotes':>12}")
for name, by, q in [('within-TASK',['task'],(0.0267,0.0211)), ('within-SYS',['sys'],(0.0039,-0.0003)),
                    ('TWO-WAY FE',['task','sys'],(0.0069,0.00000))]:
    X=np.column_stack([np.ones(n), dm(lw,by), dm(sec,by)])
    yy=dm(y,by)
    b=np.linalg.lstsq(X,yy,rcond=None)[0]
    e=yy-X@b
    for j,(nm,raw,qq) in enumerate([('log(words)',lw,q[0]),('sections',sec,q[1])]):
        sd_pool=raw.std(ddof=1); sd_dm=dm(raw,by).std(ddof=1)
        print(f'{name:<14}{nm:<14}{b[j+1]*sd_pool:>+11.5f}{b[j+1]*sd_dm:>+18.5f}{qq:>+12.5f}')
    # within R2
    r2=1-(e@e)/(((yy-yy.mean())**2).sum())
    print(f'{"":<14}{"within-R2":<14}{r2:>11.3f}')
