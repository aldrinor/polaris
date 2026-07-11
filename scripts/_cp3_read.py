import json, sys, re
cp3 = sys.argv[1]
mode = sys.argv[2] if len(sys.argv) > 2 else "all"
d = json.load(open(cp3, encoding="utf-8"))
p = d["payload"]
b = p["baskets"]
cs = p["consolidation_summary"]
if mode == "summary":
    print("=== CONSOLIDATION SUMMARY ===")
    print(json.dumps(cs, indent=1))
    print("n_baskets", len(b))
    collapse = [x for x in b if x["corroboration_count"] < x["member_count"]]
    print("baskets where corrob < member_count (distinct-works collapse active):", len(collapse))
    multi = [x for x in b if x["member_count"] > 1]
    print("multi-member baskets:", len(multi))
    singles = [x for x in b if x["member_count"] == 1]
    print("singleton baskets:", len(singles))
    sys.exit(0)

def host_list(x):
    hosts = x.get("member_hosts") or []
    if hosts:
        return hosts
    urls = x.get("member_urls") or []
    out = []
    for u in urls:
        u2 = re.sub(r"^https?://(www\.)?", "", u or "")
        out.append(u2.split("/")[0])
    return sorted(set(h for h in out if h))

def dump(x, i):
    rep = (x["representative_statement"] or "").replace("\n", " ")
    m = x["member_count"]
    c = x["corroboration_count"]
    hs = host_list(x)
    print("[%d] m=%d corr=%d hosts=%s" % (i, m, c, hs))
    print("    REP: " + rep[:250])

if mode == "multi":
    multi = [x for x in b if x["member_count"] > 1]
    for i, x in enumerate(sorted(multi, key=lambda z: -z["member_count"])):
        dump(x, i)
elif mode == "eloundou":
    el = [x for x in b if re.search(r"eloundou|gpts are gpts|15% of all worker|46% of jobs|task exposure|exposure to (llms|large language)", json.dumps(x), re.I)]
    print("eloundou-related baskets:", len(el))
    for i, x in enumerate(el):
        dump(x, i)
else:
    for i, x in enumerate(b):
        dump(x, i)
