import json, sys, re, collections
d=json.load(open(sys.argv[1]))
b=d["payload"]["baskets"]
sw=d["payload"].get("same_work_groups",[])
# Map url -> same_work_id
url2work={}
for g in sw:
    wid=g.get("same_work_id","")
    for u in g.get("member_urls",[]):
        url2work[u]=wid
def host(u):
    m=re.match(r"https?://([^/]+)",u or "")
    return (m.group(1) if m else "").replace("www.","")
# FRAGMENTATION: group baskets by the same_work_id of their representative url (fallback: host)
frag=collections.defaultdict(list)
for x in b:
    u=x["member_urls"][0] if x["member_urls"] else ""
    wid=url2work.get(u) or ("host:"+host(u))
    frag[wid].append(x)
multi=[(w,xs) for w,xs in frag.items() if len(xs)>1]
multi.sort(key=lambda t:-len(t[1]))
print("=== PAPERS SPLIT INTO MULTIPLE FINDING-BASKETS (fragmentation) ===")
print("distinct works/hosts among baskets:",len(frag),"| works split into >1 basket:",len(multi))
for w,xs in multi[:22]:
    print("WORK %s  -> %d baskets"%(w[:64],len(xs)))
    for x in xs:
        print("     c%d m%d | %s"%(x["corroboration_count"],x["member_count"],x["representative_statement"][:110]))
