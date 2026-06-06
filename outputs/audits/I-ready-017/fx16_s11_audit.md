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

## iter-2 — Codex iter-1 REQUEST_CHANGES addressed
**P1 (real semantic hole) — FIXED.** iter-1 SKIP'd on `PG_DISABLE_ACCESS_BYPASS in {1,true,True}`, but
production (`live_retriever.py:1764`) disables the cascade ONLY on exactly `== "1"` (no strip/truthy).
So `PG_DISABLE_ACCESS_BYPASS=true` + chromium absent would SKIP the LIVE preflight while production
STILL ran the dead Crawl4AI tier → the exact silent httpx-naive fallback this gate exists to prevent.
Now the probe matches production EXACTLY: `os.getenv("PG_DISABLE_ACCESS_BYPASS","0") == "1"`. Proven by
`test_probe_disable_semantics_match_production_exactly` (true/True/yes/on/0/""/"  1  " → do NOT skip →
FAIL in LIVE when absent; only exact "1" → SKIP).

**P2-1 (cache-root coverage) — FIXED.** `_find_chromium_binary` now searches, in order,
`PLAYWRIGHT_BROWSERS_PATH` (the official override, skipping the special "0"), then the per-OS defaults
(Linux `~/.cache/ms-playwright`, Windows `~/AppData/Local/ms-playwright`, macOS
`~/Library/Caches/ms-playwright`) — no false-FAIL on non-Linux/relocated installs. Proven by
`test_find_chromium_honors_playwright_browsers_path`.

**P2-2 (file check) — FIXED.** Only a real `is_file()` launcher counts; a partial cache dir with the
launcher path as a directory no longer passes. Proven by `test_find_chromium_ignores_non_file_match`.
(The static gate is still weaker than "browser actually launches" — that is FX-16b's post-install live
fetch check, operator-gated.)

### iter-2 smoke
`pytest tests/polaris_graph/test_fx16_chromium_preflight_iready017.py` → 11 passed (8 original + 3 new
covering the P1 exact-semantics, PLAYWRIGHT_BROWSERS_PATH, and is_file fixes).
