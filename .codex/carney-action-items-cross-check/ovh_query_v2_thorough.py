"""Bulletproof OVH GPU-in-Canada check.

Goal: definitively answer "does OVH have ANY H100/H200/A100/L4/L40s hardware
deployable in a Canadian datacenter?"

Cross-checks:
1. Project-scoped flavor query per region (deployment endpoint).
2. Unfiltered project flavor catalogue (what this project can theoretically order).
3. OVH order catalogue with ovhSubsidiary=CA (what OVH SELLS to Canadian accounts).
4. Datacenter / region metadata to confirm physical location of each region.
"""
import os
import json
import ovh

env = {}
for line in open(r"C:\POLARIS\.env", encoding="utf-8"):
    line = line.strip()
    if not line or line.startswith("#") or "=" not in line:
        continue
    k, v = line.split("=", 1)
    env[k] = v

client = ovh.Client(
    endpoint=env["OVH_ENDPOINT"],
    application_key=env["OVH_APPLICATION_KEY"],
    application_secret=env["OVH_APPLICATION_SECRET"],
    consumer_key=env["OVH_CONSUMER_KEY"],
)
PROJ = "446fccde73604cfbb0758c6012dad6d1"
GPU_TOKENS = ("h100", "h200", "a100", "l4-", "l40", "-l4", "-l40", "gpu", "ai1-")


def is_gpu(name: str) -> bool:
    ll = name.lower()
    return any(g in ll for g in GPU_TOKENS)


print("=" * 70)
print("CHECK 1: Datacenter / region metadata — what regions exist, where physically?")
print("=" * 70)
regions = client.get("/cloud/project/" + PROJ + "/region")
for r in sorted(regions):
    try:
        info = client.get("/cloud/project/" + PROJ + "/region/" + r)
        dc = info.get("datacenter", "?")
        country = info.get("country", "?")
        continent_code = info.get("continentCode", "?")
        ip_countries = info.get("ipCountries", [])
        services = [s.get("name") for s in info.get("services", []) if s.get("status") == "UP"]
        has_instance = "instance" in services
        print(f"  {r:14}  dc={dc:6}  country={country:4}  continent={continent_code:3}  ipCountries={ip_countries}  instance={has_instance}")
    except Exception as e:
        print(f"  {r:14}  ERROR: {e}")

print()
print("=" * 70)
print("CHECK 2: Unfiltered project flavor catalogue (every flavor this project")
print("         can order, in any region) — looking for GPU SKUs")
print("=" * 70)
all_flavors = client.get("/cloud/project/" + PROJ + "/flavor")
gpu_flavors = [f for f in all_flavors if is_gpu(f.get("name", ""))]
print(f"Total flavors visible: {len(all_flavors)};  GPU flavors: {len(gpu_flavors)}")
print()
for f in gpu_flavors:
    print(f"  name={f.get('name',''):20}  region={f.get('region','?'):8}  type={f.get('type','?'):16}  ram={f.get('ram','?')}GB  vcpus={f.get('vcpus','?')}  available={f.get('available',None)}")

print()
print("=" * 70)
print("CHECK 3: ORDER CATALOGUE — what OVH SELLS to Canadian subsidiary (ovhSubsidiary=CA)")
print("=" * 70)
try:
    catalogue = client.get("/order/catalog/public/cloud", ovhSubsidiary="CA")
    plans = catalogue.get("plans", [])
    gpu_plans = []
    for p in plans:
        code = p.get("planCode", "")
        if is_gpu(code):
            gpu_plans.append(p)
    print(f"Total plans in CA subsidiary catalogue: {len(plans)};  GPU plans: {len(gpu_plans)}")
    print()
    for p in gpu_plans:
        code = p.get("planCode", "")
        # extract pricing
        pricings = p.get("pricings", [])
        hourly_prices = []
        for pr in pricings:
            mode = pr.get("mode", "")
            if "hourly" in mode.lower() or pr.get("intervalUnit") == "hour":
                hourly_prices.append(f"{pr.get('priceInUcents', '?')/1e8 if pr.get('priceInUcents') else '?'} {pr.get('tax',{}).get('currency','?') if isinstance(pr.get('tax'),dict) else 'CAD'}")
        # extract data sources / available regions from product blueprint
        configs = p.get("configurations", [])
        region_configs = []
        for c in configs:
            if c.get("name") in ("region", "datacenter"):
                vals = c.get("values", [])
                region_configs.extend(vals)
        print(f"  planCode={code:25}  hourly={hourly_prices}  regions_in_plan={region_configs[:5]}")
except Exception as e:
    print(f"  catalogue query failed: {e}")

print()
print("=" * 70)
print("CHECK 4: Try ovhSubsidiary=US, FR, CA — does H100 plan exist for each?")
print("=" * 70)
for subsid in ["CA", "US", "FR"]:
    try:
        cat = client.get("/order/catalog/public/cloud", ovhSubsidiary=subsid)
        plans = cat.get("plans", [])
        gpu_plan_codes = [p.get("planCode","") for p in plans if is_gpu(p.get("planCode",""))]
        print(f"  ovhSubsidiary={subsid}:  {len(gpu_plan_codes)} GPU plans:  {gpu_plan_codes}")
    except Exception as e:
        print(f"  ovhSubsidiary={subsid}: ERROR {e}")

print()
print("=" * 70)
print("CHECK 5: Per-region deployment — try to LIST what regions a sample H100 plan")
print("         can actually deploy to (the operative question)")
print("=" * 70)
# For each GPU flavor that the project sees, list its physical region
for f in gpu_flavors[:5]:
    name = f.get("name", "")
    region = f.get("region", "?")
    # Look up the region's country
    try:
        info = client.get("/cloud/project/" + PROJ + "/region/" + region)
        country = info.get("country", "?")
        dc = info.get("datacenter", "?")
        print(f"  flavor {name:16}  deploys to region={region:8}  country={country}  datacenter={dc}")
    except Exception as e:
        print(f"  flavor {name:16}  deploys to region={region:8}  (region info lookup failed: {e})")
