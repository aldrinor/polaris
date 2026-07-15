import json, numpy as np
np.set_printoptions(suppress=True)
P = json.load(open('/home/polaris/polaris_project/attack/panel_rebuilt.json'))
SYS = sorted({r['sys'] for r in P}); TASK = sorted({r['task'] for r in P})
si = {s:i for i,s in enumerate(SYS)}; ti = {t:i for i,t in enumerate(TASK)}
n = len(P)

def dummies(rows):
    D = np.zeros((n, len(TASK)+len(SYS)))
    for i,r in enumerate(rows):
        D[i, ti[r['task']]] = 1
        D[i, len(TASK)+si[r['sys']]] = 1
    # drop one system column for identification (task dummies span intercept)
    return np.hstack([D[:, :len(TASK)], D[:, len(TASK)+1:]])

def ols(y, X):
    XtX = X.T@X
    b = np.linalg.pinv(XtX)@X.T@y
    e = y - X@b
    return b, e, np.linalg.pinv(XtX)

def cluster_vcov(X, e, Xinv, groups):
    """cluster-robust sandwich"""
    meat = np.zeros((X.shape[1], X.shape[1]))
    for g in set(groups):
        idx = [i for i,gg in enumerate(groups) if gg==g]
        Xg = X[idx]; eg = e[idx]
        u = Xg.T@eg
        meat += np.outer(u,u)
    G = len(set(groups))
    c = G/(G-1) * (len(e)-1)/(len(e)-X.shape[1])
    return c * Xinv@meat@Xinv

def run(feat, dim, transform=None, label=None, rows=None, verbose=True):
    rows = rows if rows is not None else P
    m = len(rows)
    x_raw = np.array([r[feat] for r in rows], float)
    x = transform(x_raw) if transform else x_raw
    y = np.array([r[dim] for r in rows], float)
    sd_x = x.std(ddof=1)                     # POOLED SD -> "per +1SD" scaling
    tk = sorted({r['task'] for r in rows}); sy = sorted({r['sys'] for r in rows})
    tmap={t:i for i,t in enumerate(tk)}; smap={s:i for i,s in enumerate(sy)}
    D = np.zeros((m, len(tk)+len(sy)-1))
    for i,r in enumerate(rows):
        D[i, tmap[r['task']]] = 1
        j = smap[r['sys']]
        if j>0: D[i, len(tk)+j-1] = 1
    specs = {}
    # pooled
    Xp = np.column_stack([np.ones(m), x])
    # within-task
    Dt = np.zeros((m,len(tk)))
    for i,r in enumerate(rows): Dt[i,tmap[r['task']]]=1
    Xt = np.column_stack([Dt, x])
    # within-system
    Ds = np.zeros((m,len(sy)))
    for i,r in enumerate(rows): Ds[i,smap[r['sys']]]=1
    Xs = np.column_stack([Ds, x])
    # two-way
    X2 = np.column_stack([D, x])
    for name, X, cl in [('pooled',Xp,None), ('within-TASK',Xt,'task'),
                        ('within-SYS',Xs,'sys'), ('TWO-WAY FE',X2,'task')]:
        b,e,Xinv = ols(y,X)
        beta = b[-1]
        # cluster by TASK (the natural cluster: reference article is fixed per task)
        gT = [r['task'] for r in rows]; gS = [r['sys'] for r in rows]
        V_t = cluster_vcov(X,e,Xinv,gT); se_t = np.sqrt(max(V_t[-1,-1],0))
        V_s = cluster_vcov(X,e,Xinv,gS); se_s = np.sqrt(max(V_s[-1,-1],0))
        se_h = np.sqrt(max((e@e/(m-X.shape[1])) * Xinv[-1,-1], 0))
        r2 = 1 - (e@e)/(((y-y.mean())**2).sum())
        # residual variation in x surviving the FE (the "is there anything left to identify on")
        bx, ex, _ = ols(x, X[:, :-1]) if X.shape[1]>1 else (None, x-x.mean(), None)
        frac_x_left = ex.var(ddof=0)/x.var(ddof=0)
        specs[name] = dict(beta_sd=beta*sd_x, se_task=se_t*sd_x, se_sys=se_s*sd_x,
                           se_homo=se_h*sd_x, r2=r2, frac_x=frac_x_left)
    if verbose:
        lab = label or f'{feat} -> {dim}'
        print(f'\n### {lab}   (n={m}, pooled SD of x = {sd_x:.4g})')
        print(f"{'spec':<14}{'beta/+1SD':>11}{'SE(clu task)':>14}{'95% CI':>22}{'R2':>7}{'%var(x) left':>14}")
        for k,v in specs.items():
            lo,hi = v['beta_sd']-1.96*v['se_task'], v['beta_sd']+1.96*v['se_task']
            print(f"{k:<14}{v['beta_sd']:>+11.5f}{v['se_task']:>14.5f}"
                  f"{'['+format(lo,'+.4f')+', '+format(hi,'+.4f')+']':>22}{v['r2']:>7.3f}{100*v['frac_x']:>13.1f}%")
    return specs

print('='*100)
print('REPLICATION OF F2  (outcome = overall_score, 0-1 units; same units as the quoted +0.0069)')
print('='*100)
run('words','overall_score', transform=np.log, label='log(words) -> overall_score  [F2 quotes: within-task +0.0267 | within-sys +0.0039 | 2wayFE +0.0069]')
run('sections','overall_score', label='sections -> overall_score   [F2 quotes: within-task +0.0211 | within-sys -0.0003 | 2wayFE +0.00000]')
