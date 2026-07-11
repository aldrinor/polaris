import json, sys, re
d=json.load(open(sys.argv[1]))
b=d["payload"]["baskets"]
def host(x):
    u=x["member_urls"][0] if x["member_urls"] else ""
    m=re.match(r"https?://([^/]+)",u or "")
    return (m.group(1) if m else "").replace("www.","")[:24]
for i,x in enumerate(b):
    print("%3d|c%d m%d|%-24s|%s"%(i,x["corroboration_count"],x["member_count"],host(x),x["representative_statement"][:130].replace(chr(10)," ")))
