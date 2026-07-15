import json, sys, os
sys.path.insert(0, '/home/polaris/polaris_project/drb_corpus')
from feat import feats, is_zh   # reuse THEIR feature extractor verbatim, so I attack their numbers, not mine

B = '/home/polaris/polaris_project/drb_corpus/gpt55_board'
SYS = ['WhaleCloud-DocChain_0612','bodhi','dalpha-deepresearch','gemini-2.5-pro-deepresearch',
       'grok-deeper-search','lunon_full100_FINAL.submission','openai-deepresearch',
       'perplexity-Research','sourcery']
DIMS = ['overall_score','comprehensiveness','insight','instruction_following','readability']

panel=[]
for s in SYS:
    sc={}
    for line in open(f'{B}/scores/{s}/raw_results.jsonl'):
        d=json.loads(line); sc[d['id']]=d
    for line in open(f'{B}/{s}.jsonl'):
        d=json.loads(line)
        if d['id'] not in sc: continue
        z=is_zh(d['prompt'])
        f=feats(d['article'], z)
        f['sys']=s; f['task']=d['id']; f['zh']=int(z)
        for k in DIMS: f[k]=sc[d['id']][k]        # KEEP 0-1 UNITS (synthesis quotes +0.0069 in these units)
        panel.append(f)
json.dump(panel, open('/home/polaris/polaris_project/attack/panel_rebuilt.json','w'))
print('N =', len(panel))
print('systems:', len({r['sys'] for r in panel}), ' tasks:', len({r['task'] for r in panel}))
print('zh rows:', sum(r['zh'] for r in panel), ' en rows:', sum(1-r['zh'] for r in panel))
print('zh tasks:', len({r['task'] for r in panel if r['zh']}), ' en tasks:', len({r['task'] for r in panel if not r['zh']}))
