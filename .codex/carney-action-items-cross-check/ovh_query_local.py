"""Read-only OVH catalogue query.

Lists every GPU SKU (H100/H200/A100/L4/L40) per region available to the
POLARIS project. Used to verify whether OVH BHS5 actually exposes H200
to fresh Public Cloud projects, or only OVH France does.
"""
import os
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

print("=== 1. Regions visible to this project ===")
regions = client.get("/cloud/project/" + PROJ + "/region")
print(", ".join(sorted(regions)))

print()
print("=== 2. GPU flavors per region (H100/H200/A100/L4/L40) ===")
seen = {}
errors = []
GPU_TOKENS = ("h100", "h200", "a100", "l4-", "l40", "-l4", "-l40")
for r in sorted(regions):
    try:
        flavors = client.get("/cloud/project/" + PROJ + "/flavor", region=r)
    except Exception as e:
        errors.append((r, str(e)))
        continue
    for f in flavors:
        name = f.get("name", "")
        ll = name.lower()
        if any(g in ll for g in GPU_TOKENS):
            t = f.get("type", "?")
            ram = f.get("ram", "?")
            cpu = f.get("vcpus", "?")
            av = f.get("available", None)
            print(
                "  region=" + r.ljust(8)
                + " name=" + name.ljust(20)
                + " type=" + str(t).ljust(14)
                + " ram=" + str(ram) + "GB"
                + " vcpus=" + str(cpu)
                + " avail=" + str(av)
            )
            seen.setdefault(name, []).append(r)
if errors:
    print("--- region errors ---")
    for r, e in errors[:5]:
        print("  " + r + ": " + e)

print()
print("=== 3. Summary: which GPU SKU exists in which region(s) ===")
if not seen:
    print("  *** NO GPU flavors visible in ANY region for this project ***")
    print("  Cause: GPU not enabled on this fresh project.")
    print("  The OVH support ticket we have open IS the unblock path.")
else:
    for sku in sorted(seen):
        regs = sorted(seen[sku])
        canadian = [r for r in regs if "BHS" in r.upper() or r.upper().startswith("CA-")]
        marker = "  *** CANADIAN: " + str(canadian) + " ***" if canadian else ""
        print("  " + sku.ljust(20) + " -> " + str(regs) + marker)

print()
print("=== 4. BHS regions visible to this project ===")
bhs = sorted([r for r in regions if "BHS" in r.upper()])
print("  " + str(bhs))

print()
print("=== 5. Public flavor catalogue (no region filter) — what OVH sells AT ALL ===")
all_flavors = client.get("/cloud/project/" + PROJ + "/flavor")
gpu_all = [f for f in all_flavors if any(g in f.get("name", "").lower() for g in GPU_TOKENS)]
by_sku = {}
for f in gpu_all:
    name = f.get("name", "")
    reg = f.get("region", "?")
    by_sku.setdefault(name, []).append(reg)
if not gpu_all:
    print("  *** NO GPU flavors in unfiltered catalogue either — GPU genuinely not enabled ***")
else:
    for sku in sorted(by_sku):
        regs = sorted(set(by_sku[sku]))
        canadian = [r for r in regs if "BHS" in r.upper() or r.upper().startswith("CA-")]
        marker = "  *** CANADIAN: " + str(canadian) + " ***" if canadian else "  (no Canadian region)"
        print("  " + sku.ljust(20) + " -> " + str(regs) + marker)
