import json, numpy as np, statistics as st
P = json.load(open('/home/polaris/polaris_project/attack/panel_rebuilt.json'))
SYS = sorted({r['sys'] for r in P}); TASKS = sorted({r['task'] for r in P})

def two_way_demean_additive(vals, rows):
    """EXACTLY panel.py:79-85 -- the additive shortcut"""
    gm = st.mean(vals)
    sm = {s: st.mean([v for v,r in zip(vals,rows) if r['sys']==s]) for s in SYS}
    tm = {t: st.mean([v for v,r in zip(vals,rows) if r['task']==t]) for t in TASKS}
    return np.array([v - sm[r['sys']] - tm[r['task']] + gm for v,r in zip(vals,rows)])

for feat, tf, quoted in [('words', np.log, 0.0069), ('sections', None, 0.00000)]:
    xr = np.array([r[feat] for r in P], float)
    x  = tf(xr) if tf else xr
    y  = np.array([r['overall_score'] for r in P], float)
    xd = two_way_demean_additive(list(x), P)
    yd = two_way_demean_additive(list(y), P)
    beta_raw = (xd@yd)/(xd@xd)                      # slope on demeaned data == two-way FE slope
    sd_pooled = x.std(ddof=1)
    sd_demean = xd.std(ddof=1)
    r_fe = np.corrcoef(xd, yd)[0,1]
    print(f'=== {feat} ===')
    print(f'  two-way FE slope (per RAW unit)      : {beta_raw:+.6f}')
    print(f'  SD of x, POOLED (real corpus spread) : {sd_pooled:.4f}')
    print(f'  SD of x, AFTER two-way demeaning     : {sd_demean:.4f}   ({100*sd_demean/sd_pooled:.1f}% of pooled)')
    print(f'  demeaned correlation r_FE            : {r_fe:+.4f}   <-- this is what panel.py:86 prints')
    print(f'  beta x POOLED SD   (policy scaling)  : {beta_raw*sd_pooled:+.5f}')
    print(f'  beta x DEMEANED SD (residual scaling): {beta_raw*sd_demean:+.5f}   <<< F2 QUOTES {quoted:+.5f}')
    print(f'  r_FE x SD(y_demeaned)                : {r_fe*yd.std(ddof=1):+.5f}')
    print()

# what does 1 SD actually MEAN in each scaling?
xr = np.array([r['words'] for r in P],float); lx=np.log(xr)
print('INTERPRETATION of "+1 SD of log(words)":')
print(f'  pooled  SD = {lx.std(ddof=1):.3f} log-units  => a {np.exp(lx.std(ddof=1)):.2f}x change in length')
xd = two_way_demean_additive(list(lx), P)
print(f'  demeaned SD = {xd.std(ddof=1):.3f} log-units  => a {np.exp(xd.std(ddof=1)):.2f}x change in length')
print()
print('overall_score: mean %.4f  SD %.4f' % (np.mean([r['overall_score'] for r in P]), np.std([r['overall_score'] for r in P],ddof=1)))
