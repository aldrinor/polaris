# FX-16 §-1.1 audit — fail-closed chromium preflight probe (code half) (#1131)

**Standard:** §-1.1 over the held drb_72 `tool_summary.json` fetch outcome + the probe's
fail-closed behavior. NOTE: FX-16 has TWO halves — (a) the CODE probe (this audit, autonomous) and
(b) the VM deployment `python -m playwright install chromium --with-deps` (operator Q5) + the
post-install live fetch check (operator-gated). The full live §-1.1 (a JS page fetched non-empty via
Crawl4AI) runs after the operator installs chromium on the VM.

## The bug, on the real artifact
Held drb_72 fetch outcome (FX-20 §-1.1, same `tool_trace.jsonl`): `fetch_content` attempted **145**,
succeeded **74** → **success_rate 0.51**. Root cause (forensic): the AccessBypass cascade's
Playwright/Crawl4AI browser-fetch tier was DEAD on the VM (chromium binary absent), so the cascade
SILENTLY fell back to httpx-naive — a silent downgrade on a (paid) run (LAW II). No preflight caught
it before spend.

## The fix (code half — FX-16a)
`scripts/pg_preflight.py`:
- `_find_chromium_binary(cache_root=None)` — pure, cross-platform glob of the ms-playwright cache
  (Linux `chrome-linux*/chrome`, Windows `chrome-win*/chrome.exe`, macOS Chromium.app); never crashes.
- `test_chromium_browser_available()` (Tier-1): chromium present → PASS; absent + cascade-on →
  FAIL CLOSED in LIVE/paid mode (`PG_PREFLIGHT_LIVE=1`) with remediation; absent in DRY mode → SKIP
  with the same remediation (so dev/CI dry runs do NOT break); `PG_DISABLE_ACCESS_BYPASS=1` → SKIP
  (cascade intentionally off). Registered in `TIER_1_TESTS` (a Tier-1 FAIL → preflight exit 1).

## §-1.1 — the probe gates the exact symptom
- Held symptom: fetch success 0.51 due to a silent browser-tier fallback. With FX-16, a LIVE/paid
  preflight on a host WITHOUT chromium FAILS CLOSED before spend (proven:
  `test_probe_fails_closed_in_live_mode_when_absent`) — the run cannot reach the throttled-fetch state
  undetected. The remediation string names the exact fix (`python -m playwright install chromium
  --with-deps`) and the escape hatch (`PG_DISABLE_ACCESS_BYPASS=1`).
- Detection correctness on real layouts: `_find_chromium_binary` finds the Linux VM layout
  (`chromium-1187/chrome-linux/chrome`) and the Windows layout, and returns None on an absent/empty
  cache (proven by the layout tests) — no false PASS.

## Offline smoke (proves the code half)
`pytest tests/polaris_graph/test_fx16_chromium_preflight_iready017.py` → 8 passed: cache absent/empty →
None; Linux + Windows layouts detected; cascade-off → SKIP; present → PASS; LIVE + absent → FAIL;
DRY + absent → SKIP-with-remediation (dev/CI safe).

## Operator-gated remainder (FX-16b — NOT in this diff)
1. **Q5:** on the OVH VM run `python -m playwright install chromium --with-deps`.
2. Post-install live §-1.1: `pg_preflight` (LIVE) asserts the chromium tier OK; fetch ONE JS-heavy
   publisher URL → non-empty body via Crawl4AI (`tool_trace.jsonl` `backend_used='crawl4ai',
   status='ok'`); `tool_summary.json` `success_rate >= 0.40`.

## Faithfulness
Additive fail-closed preflight gate — observability/safety only. No grounding / strict_verify / 4-role
change. It can only ABORT a paid run that would silently degrade; it never weakens a check. DRY mode is
non-breaking (SKIP). No-silent-downgrade-aligned (LAW II): a dead fetch tier now fails loud pre-spend.
