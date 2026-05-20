"""OVH GPU topology + capacity probe (I-cd-008, GH#640).

Read-only verification of OVH catalog + project-region capacity for the
locked Carney topology: 8xH200 (h200-1920) generator box + 4xH100
(h100-1520) evaluator box, in a non-US region (Canada BHS or France
GRA/SBG/RBX).

Per operator memory `feedback_verify_primary_sources_before_relying_2026_05_15`:
- Cross-check via 4+ independent signals (catalog @ CA + catalog @ FR +
  project flavor list + per-region quota state).
- Per-region availability, not billing-currency. Catalog presence at a
  subsidiary is NOT the same as project-region availability or quota.

Per Codex iter-2 brief P2:
- Use unfiltered `GET /cloud/project/{serviceName}/flavor` + client-side
  filter (region-filtered probes 404 on aggregate codes).
- Quota endpoint: `GET /cloud/project/{serviceName}/region/{regionName}/quota/allowed`
  (note the `/region/{regionName}/` prefix; NOT a project-wide path).
- `GET /cloud/project/{serviceName}/region` to derive real region names
  before per-region calls.
- `/cloud/order/rule/availability` as an additional catalog/order-rule
  signal (not cart/expressOrder dry-runs).

Reads `OVH_*` from .env. NEVER ECHOES SECRET VALUES. Writes a JSON
audit artifact to `outputs/audits/I-cd-008/probe_result.json`.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import ovh

REPO_ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = REPO_ROOT / ".env"
OUT_PATH = REPO_ROOT / "outputs" / "audits" / "I-cd-008" / "probe_result.json"

# Locked Carney topology — operator-locked, do not negotiate.
TARGET_SKUS = ("h200-1920", "h100-1520")
GPU_SUBSTRINGS = ("h100", "h200", "l40", "l4-", "a100", "a10-", "gpu")
NON_US_REGION_PREFIXES = ("BHS", "GRA", "SBG", "RBX", "WAW", "ERI", "UK", "DE")


def _read_env(path: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    if not path.exists():
        sys.exit(f"FATAL: .env not found at {path}")
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        s = line.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        k, v = s.split("=", 1)
        env[k.strip()] = v.strip()
    for k in ("OVH_ENDPOINT", "OVH_APPLICATION_KEY", "OVH_APPLICATION_SECRET", "OVH_CONSUMER_KEY"):
        if k not in env:
            sys.exit(f"FATAL: {k} missing from .env")
    return env


def _client(env: dict[str, str]) -> ovh.Client:
    return ovh.Client(
        endpoint=env["OVH_ENDPOINT"],
        application_key=env["OVH_APPLICATION_KEY"],
        application_secret=env["OVH_APPLICATION_SECRET"],
        consumer_key=env["OVH_CONSUMER_KEY"],
    )


def _catalog_skus(client: ovh.Client, subsidiary: str) -> list[dict] | dict:
    """Catalog presence at a billing subsidiary. Returns list of GPU plan rows,
    or a dict with `error` key if the endpoint rejects this subsidiary
    (e.g., querying `ovhSubsidiary=FR` against the `ovh-ca` endpoint)."""
    try:
        cat = client.get("/order/catalog/public/cloud", ovhSubsidiary=subsidiary)
    except ovh.exceptions.APIError as exc:
        return {"error": f"{type(exc).__name__}: {exc}", "subsidiary": subsidiary}
    rows: list[dict] = []
    for addon in cat.get("addons", []):
        pc = (addon.get("planCode") or "").lower()
        if not any(k in pc for k in GPU_SUBSTRINGS):
            continue
        rows.append(
            {
                "planCode": addon.get("planCode"),
                "invoiceName": addon.get("invoiceName"),
                "blobs_tags": (addon.get("blobs") or {}).get("tags", []),
                "pricings_count": len(addon.get("pricings") or []),
            }
        )
    return rows


def _project_regions(client: ovh.Client, project_id: str) -> list[str]:
    """Real region codes enabled for the project (e.g., BHS5, GRA9, GRA11)."""
    return client.get(f"/cloud/project/{project_id}/region")


def _project_flavors(client: ovh.Client, project_id: str) -> list[dict]:
    """UNFILTERED project-wide flavor list (per Codex iter-2 P2)."""
    return client.get(f"/cloud/project/{project_id}/flavor")


def _region_quota(client: ovh.Client, project_id: str, region: str) -> dict:
    """Per-region quota state."""
    return client.get(f"/cloud/project/{project_id}/region/{region}/quota")


def _region_quota_allowed(client: ovh.Client, project_id: str, region: str) -> dict:
    """Per-region allowed-quota (what increases the project can request)."""
    return client.get(f"/cloud/project/{project_id}/region/{region}/quota/allowed")


def _order_rule_availability(client: ovh.Client, sku: str) -> dict | None:
    """Catalog/order-rule availability signal (per Codex iter-2 P2)."""
    try:
        return client.get("/cloud/order/rule/availability", planCode=sku)
    except ovh.exceptions.APIError:
        return None


def probe(env: dict[str, str], project_id: str) -> dict:
    """Run the full 4+ signal probe; return structured result."""
    client = _client(env)
    result: dict = {
        "probe_utc": datetime.now(timezone.utc).isoformat(),
        "project_id": project_id,
        "endpoint": env["OVH_ENDPOINT"],
        "target_skus": list(TARGET_SKUS),
    }

    # Signal 1+2: catalog at CA and FR subsidiaries.
    result["signal_1_catalog_CA"] = _catalog_skus(client, "CA")
    result["signal_2_catalog_FR"] = _catalog_skus(client, "FR")

    # Signal 3: project flavors (unfiltered, then client-side filter).
    # Both wrapped in try/except so a single failure doesn't abort the whole
    # probe (per Codex diff iter-1 P2).
    try:
        regions = _project_regions(client, project_id)
        result["project_regions"] = regions
    except ovh.exceptions.APIError as exc:
        result["project_regions"] = []
        result["project_regions_error"] = str(exc)
        regions = []
    try:
        all_flavors = _project_flavors(client, project_id)
    except ovh.exceptions.APIError as exc:
        all_flavors = []
        result["project_flavors_error"] = str(exc)
    target_rows = [
        {
            "name": f.get("name"),
            "region": f.get("region"),
            "available": f.get("available"),
            "quota": f.get("quota"),
            "ram": f.get("ram"),
            "vcpus": f.get("vcpus"),
        }
        for f in all_flavors
        if (f.get("name") in TARGET_SKUS)
    ]
    result["signal_3_project_flavors_target"] = target_rows
    result["project_flavor_total_rows"] = len(all_flavors)

    # Signal 4: per-region quota + allowed-quota for candidate non-US regions.
    candidate_regions = [r for r in regions if any(r.startswith(p) for p in NON_US_REGION_PREFIXES)]
    result["candidate_non_us_regions"] = candidate_regions
    quota_state: dict = {}
    for region in candidate_regions:
        entry: dict = {}
        try:
            entry["quota"] = _region_quota(client, project_id, region)
        except ovh.exceptions.APIError as exc:
            entry["quota_error"] = str(exc)
        try:
            entry["allowed"] = _region_quota_allowed(client, project_id, region)
        except ovh.exceptions.APIError as exc:
            entry["allowed_error"] = str(exc)
        quota_state[region] = entry
    result["signal_4_region_quota"] = quota_state

    # Extra signal: order-rule availability per SKU.
    result["signal_5_order_rule_availability"] = {
        sku: _order_rule_availability(client, sku) for sku in TARGET_SKUS
    }

    # Topology verdict — derive from the actual target-SKU state, not hardcoded.
    # BOTH target SKUs must have at least one project-flavor row with
    # available=True AND quota>=1 for the topology to be obtainable.
    has_h200 = any(
        r.get("name") == "h200-1920" and r.get("available") and (r.get("quota") or 0) >= 1
        for r in target_rows
    )
    has_h100 = any(
        r.get("name") == "h100-1520" and r.get("available") and (r.get("quota") or 0) >= 1
        for r in target_rows
    )
    verdict: dict = {
        "target_skus_obtainable_now": bool(has_h200 and has_h100),
        "h200_1920_obtainable": has_h200,
        "h100_1520_obtainable": has_h100,
        "blockers": [],
    }
    if not has_h200:
        if not any(f.get("name") == "h200-1920" for f in all_flavors):
            verdict["blockers"].append(
                "h200-1920 absent from project flavor list entirely — operator must request "
                "OVH support add this SKU to the project allowlist for a non-US region "
                "(preferred: GRA9 or GRA11)."
            )
        else:
            verdict["blockers"].append(
                "h200-1920 present in project flavor list but no row has available=True AND "
                "quota>=1 — operator must request an OVH quota increase."
            )
    if not has_h100:
        if not any(f.get("name") == "h100-1520" for f in all_flavors):
            verdict["blockers"].append(
                "h100-1520 absent from project flavor list entirely — operator must request "
                "OVH support add this SKU to the project allowlist."
            )
        else:
            verdict["blockers"].append(
                "h100-1520 present in project flavor list but no row has available=True AND "
                "quota>=1 in any project region — operator must request an OVH quota "
                "increase (GRA9/GRA11 candidates)."
            )
    result["verdict"] = verdict
    return result


def main() -> int:
    env = _read_env(ENV_PATH)
    project_id = "446fccde73604cfbb0758c6012dad6d1"  # state/ovh_infra.md
    result = probe(env, project_id)
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    summary_lines = [
        f"probe_utc: {result['probe_utc']}",
        f"endpoint: {result['endpoint']}",
        f"project_regions: {', '.join(result['project_regions'])}",
        f"candidate_non_us_regions: {', '.join(result['candidate_non_us_regions'])}",
        f"signal_1 catalog@CA: {len(result['signal_1_catalog_CA']) if isinstance(result['signal_1_catalog_CA'], list) else result['signal_1_catalog_CA']}",
        f"signal_2 catalog@FR: {len(result['signal_2_catalog_FR']) if isinstance(result['signal_2_catalog_FR'], list) else result['signal_2_catalog_FR']}",
        f"signal_3 project flavors hitting target SKUs:",
    ]
    for row in result["signal_3_project_flavors_target"]:
        summary_lines.append(
            f"   {row['name']:>16} @ {row['region']:>8} available={row['available']} quota={row['quota']}"
        )
    summary_lines.append(f"verdict.target_skus_obtainable_now = {result['verdict']['target_skus_obtainable_now']}")
    for b in result["verdict"]["blockers"]:
        summary_lines.append(f"BLOCKER: {b}")
    print("\n".join(summary_lines))
    print(f"\nfull JSON: {OUT_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
