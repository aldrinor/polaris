import json, sys, re, collections
cp3=sys.argv[1]
d=json.load(open(cp3))
b=d["payload"]["baskets"]
cs=d["payload"]["consolidation_summary"]
sw=d["payload"].get("same_work_groups",[])
print("=== CONSOLIDATION SUMMARY ===")
print(json.dumps(cs,indent=1))
print("total_baskets",len(b))
mm=[x for x in b if x["member_count"]>1]
mc=[x for x in b if x["corroboration_count"]>1]
print("multi_member",len(mm),"multi_corrob",len(mc))
cd=collections.Counter(x["corroboration_count"] for x in b)
print("corroboration_count distribution:",dict(sorted(cd.items())))
def hay(x):
    return (x["representative_statement"]+" "+" ".join(x["member_urls"])+" "+" ".join(x["member_hosts"])).lower()
# ELOUNDOU
print("\n=== ELOUNDOU / GPTs-are-GPTs baskets ===")
el=[x for x in b if "eloundou" in hay(x) or "2303.10130" in hay(x) or "gpts are gpts" in hay(x) or "gpts-are-gpts" in hay(x)]
print("count",len(el))
for x in el:
    print("--- corrob",x["corroboration_count"],"mem",x["member_count"],"key",x["finding_key"])
    print("  REP:",repr(x["representative_statement"][:240]))
    print("  urls:",x["member_urls"][:6])
    print("  hosts:",x["member_hosts"][:6])
# SHORT/CHROME candidates (LOCATE ONLY; verdict by reading)
print("\n=== SHORT / POSSIBLE-CHROME REP CANDIDATES (locate; judge by reading) ===")
chrome_pat=re.compile(r"cookie|subscribe|sign ?in|log ?in|newsletter|404|not found|captcha|enable javascript|access denied|skip to|\bmenu\b|all rights reserved|privacy policy|terms of use|search text|add_circle|just a moment|verify you are human|performing security|are you a robot|loading",re.I)
cand=[x for x in b if len(x["representative_statement"].split())<6 or chrome_pat.search(x["representative_statement"])]
print("candidates",len(cand))
for x in cand:
    print("  c%d m%d | %r | %s"%(x["corroboration_count"],x["member_count"],x["representative_statement"][:150],(x["member_urls"][0][:70] if x["member_urls"] else "")))
# FRAGMENTATION: group baskets by folded title stem of first url/host to see one-paper-many-baskets
print("\n=== SAME_WORK GROUPS (multi-member; distinct-works collapse evidence) ===")
print("same_work multi-member group count:",len(sw))
for g in sw[:12]:
    print("  swid",g.get("same_work_id","")[:60],"nmembers",len(g.get("member_urls",[])))
    for u in g.get("member_urls",[])[:5]:
        print("      ",u[:90])
