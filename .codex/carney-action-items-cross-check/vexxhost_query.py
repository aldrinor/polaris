"""Vexxhost Montréal — sovereign Canadian cloud catalogue query.

Goal: definitively answer "does Vexxhost have H100/H200/A100/L4/L40s
deployable in Canada, and at what self-serve price?"

Steps:
1. Unscoped auth at the public auth URL (just username/password) to get a
   token + list projects this user has access to.
2. For each project, scoped auth → list compute flavors → filter for GPU.
3. If quota info is exposed, capture it (how many GPU instances can we spawn).
"""
import os
import sys
import json
from pathlib import Path

# Load .env
env = {}
for line in Path(r"C:\POLARIS\.env").read_text(encoding="utf-8").splitlines():
    line = line.strip()
    if not line or line.startswith("#") or "=" not in line:
        continue
    k, v = line.split("=", 1)
    env[k] = v

AUTH_URL = env["VEXXHOST_AUTH_URL"]
USERNAME = env["VEXXHOST_USERNAME"]
PASSWORD = env["VEXXHOST_PASSWORD"]

import requests

print("=" * 70)
print("STEP 1: Unscoped Keystone auth — get token + project list")
print("=" * 70)
print(f"  auth_url = {AUTH_URL}")
print(f"  username = {USERNAME[:6]}…")

# Try default user-domain first; Vexxhost typically uses 'Default'.
for user_domain in ["Default", "default"]:
    body = {
        "auth": {
            "identity": {
                "methods": ["password"],
                "password": {
                    "user": {
                        "name": USERNAME,
                        "domain": {"name": user_domain},
                        "password": PASSWORD,
                    }
                },
            },
            "scope": "unscoped",
        }
    }
    r = requests.post(f"{AUTH_URL}/auth/tokens", json=body, timeout=30)
    if r.status_code == 201:
        token = r.headers.get("X-Subject-Token")
        print(f"  user_domain={user_domain} → AUTH OK (status 201), token len={len(token) if token else 0}")
        break
    else:
        print(f"  user_domain={user_domain} → FAIL status={r.status_code}: {r.text[:200]}")
else:
    print("  *** unscoped auth failed across both Default/default. Stopping.")
    sys.exit(1)

print()
print("=" * 70)
print("STEP 2: List projects this user has access to")
print("=" * 70)
headers = {"X-Auth-Token": token}
r = requests.get(f"{AUTH_URL}/auth/projects", headers=headers, timeout=30)
print(f"  status={r.status_code}")
projects = []
if r.status_code == 200:
    projects = r.json().get("projects", [])
    for p in projects:
        print(f"  id={p['id']}  name={p['name']:30}  domain_id={p.get('domain_id','?')}  enabled={p.get('enabled',True)}")
else:
    print(f"  body: {r.text[:300]}")

if not projects:
    print("\n  *** No projects visible. May need a different user domain or the account isn't provisioned yet.")
    sys.exit(2)

print()
print("=" * 70)
print("STEP 3: For each project, scoped auth → catalogue + compute flavors")
print("=" * 70)

GPU_TOKENS = ("h100", "h200", "a100", "l4", "l40", "gpu", "v100", "a40", "a10")


def is_gpu_flavor(name: str, extras: dict) -> bool:
    ll = name.lower()
    if any(g in ll for g in GPU_TOKENS):
        return True
    # OpenStack convention: extra_specs may include pci_passthrough:alias or similar
    for k, v in (extras or {}).items():
        sk = str(k).lower() + " " + str(v).lower()
        if any(g in sk for g in ("gpu", "pci_passthrough", "nvidia")):
            return True
    return False


for proj in projects:
    pid, pname = proj["id"], proj["name"]
    print(f"\n--- project: {pname} (id={pid}) ---")

    # Scoped auth
    body = {
        "auth": {
            "identity": {
                "methods": ["password"],
                "password": {
                    "user": {
                        "name": USERNAME,
                        "domain": {"name": "Default"},
                        "password": PASSWORD,
                    }
                },
            },
            "scope": {"project": {"id": pid}},
        }
    }
    r = requests.post(f"{AUTH_URL}/auth/tokens", json=body, timeout=30)
    if r.status_code != 201:
        print(f"  scoped auth FAIL: {r.status_code} {r.text[:200]}")
        continue
    scoped_token = r.headers["X-Subject-Token"]
    catalog = r.json()["token"]["catalog"]

    # Find compute endpoint
    compute_endpoint = None
    for svc in catalog:
        if svc["type"] == "compute":
            for ep in svc["endpoints"]:
                if ep["interface"] == "public":
                    compute_endpoint = ep["url"]
                    print(f"  compute endpoint: {compute_endpoint} (region={ep.get('region','?')})")
                    break
            if compute_endpoint:
                break
    if not compute_endpoint:
        print("  *** no compute service in this project's catalog")
        continue

    # List flavors with detail
    h = {"X-Auth-Token": scoped_token}
    r = requests.get(f"{compute_endpoint}/flavors/detail", headers=h, timeout=30)
    if r.status_code != 200:
        print(f"  flavors/detail FAIL: {r.status_code} {r.text[:200]}")
        continue
    flavors = r.json().get("flavors", [])
    print(f"  total flavors in project: {len(flavors)}")

    gpu_flavors = []
    for f in flavors:
        name = f.get("name", "")
        extras = f.get("extra_specs", {})
        if is_gpu_flavor(name, extras):
            gpu_flavors.append(f)

    if not gpu_flavors:
        print("  *** no GPU flavors visible in this project")
        # Try the full extras anyway by fetching one example
        if flavors:
            print(f"     (sample non-GPU flavor for reference: {flavors[0].get('name')})")
        continue

    print(f"  GPU flavors found: {len(gpu_flavors)}")
    for f in gpu_flavors:
        print(f"    name={f.get('name',''):24}  ram={f.get('ram','?')}MB  vcpus={f.get('vcpus','?')}  disk={f.get('disk','?')}GB  is_public={f.get('os-flavor-access:is_public', True)}")
        # Show extra_specs (where GPU info usually lives)
        for k, v in (f.get("extra_specs") or {}).items():
            print(f"      extra: {k} = {v}")

    # Quota
    rq = requests.get(f"{compute_endpoint}/os-quota-sets/{pid}", headers=h, timeout=30)
    if rq.status_code == 200:
        q = rq.json().get("quota_set", {})
        print(f"  quota: instances={q.get('instances','?')}  cores={q.get('cores','?')}  ram_MB={q.get('ram','?')}")
    else:
        print(f"  quota query: {rq.status_code} {rq.text[:80]}")

print()
print("=" * 70)
print("DONE")
print("=" * 70)
