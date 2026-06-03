# I-faith-002 / #1039 — CORE replaces Sci-Hub: the two smoke-found bugs, fixed + live-proven

The CORE-replaces-Sci-Hub build passed unit tests but the LIVE smoke (real key,
real `api.core.ac.uk`, 3 real DOIs) surfaced TWO coupled P0 bugs. Both are now
fixed and re-proven against live CORE. This is the clinical-safety path: a
wrong-paper full text fed to the span-grounded verifier would let fabrications
cite a "matching-DOI" span.

## Bug 1 (dead path) — redirect not followed
CORE v3 now 301-redirects `GET /v3/search/works` → `/v3/search/works/`.
`httpx.Client(timeout=...)` defaults to NO redirect-following, so every call
landed on the `status_code != 200` branch and returned `("", "")` for EVERY DOI
— a silent dead path that ALSO hid Bug 2.
- Live proof (before): `follow=False → HTTP 301` for all DOIs; `follow=True → HTTP 200`.
- Fix: `httpx.Client(timeout=_CORE_TIMEOUT, follow_redirects=True)` (core_client.py).
- Regression test: `test_production_client_follows_redirects` asserts the
  production-built client is created with `follow_redirects=True`.

## Bug 2 (wrong-paper fabrication) — DOI-equality is NOT a sufficient identity check
CORE mis-tags DISTINCT papers under one exact DOI. Querying the Acemoglu DOI
`10.1257/jep.33.2.3` returns 3 results ALL tagged with that exact DOI:
- `[0]` "Impacto de las nuevas tecnologías en los salarios en Colombia" (Spanish,
  year 2022) — **65 287 chars of fullText**
- `[1]`/`[2]` "Automation and New Tasks…" (the CORRECT paper, year 2019) — **fullText empty**

The original client returned the FIRST exact-DOI match with fullText → it handed
back 25 000 chars of the WRONG paper. DOI-equality passed because CORE itself
mis-tags the Spanish paper with the Acemoglu DOI.
- Fix: a content-identity guard. `fetch_core_oa_fulltext` now takes
  `expected_title` / `expected_year` (the INDEPENDENT CrossRef-resolved values
  the caller already has at frame_fetcher Step 2b). A result's `fullText` is
  trusted only when its title shares enough significant tokens
  (overlap-coefficient ≥ `PG_CORE_TITLE_MATCH_MIN`=0.5) with the anchor AND its
  year is within `PG_CORE_YEAR_TOLERANCE`. With NO caller hint, a set of
  exact-DOI results carrying CONFLICTING titles is rejected outright (mis-tag).
  This mirrors the existing PubMed DOI-consistency guard already in
  frame_fetcher (lines ~1243).
- frame_fetcher passes `expected_title=title, expected_year=year` (CrossRef).

## Live proof AFTER the fix (real function, real key)
Production path (anchor = CrossRef title), the 3 required DOIs:
- `10.1371/journal.pmed.1003583` (PRISMA) → `("", "")`  [exact record, empty fullText — legit]
- `10.1257/jep.33.2.3` (Acemoglu) → `("", "")`  [was 25 000 chars of the Spanish paper; now REJECTED]
- `10.1126/science.adh2586` (Eloundou) → `("", "")`  [0 hits — legit]

Guard is load-bearing (Acemoglu DOI, vary the anchor):
- anchor = Spanish title → 25 000 chars (guard ALLOWS what the anchor matches)
- anchor = correct title → `("", "")` (correct paper has no fullText)
- ⇒ discriminates by content identity, not DOI.

True-positive happy path (proves Bug 1's redirect fix lets CORE serve content):
- a real OA DOI `10.17169/refubium-24667` with matching title →
  25 000 chars + `downloadUrl https://core.ac.uk/download/199423038.pdf`
- same DOI with a deliberately-wrong anchor → `("", "")` (rejected).

## Sci-Hub OFF (confirmed)
- `access_bypass.py:955` default `PG_SCIHUB_ENABLED` = `"0"`; the ONE `_try_scihub`
  call site (line 959) is inside the `== "1"` guard ⇒ no outbound sci-hub.* request.
- `frame_fetcher` independently rejects any `access_method` containing `scihub`.

## Tests
`pytest test_core_client.py test_m56_frame_fetcher.py test_fetch_access_bypass_wiring.py
test_m23_access_bypass_fixes.py test_access_bypass_backend_timeout.py
test_access_bypass_teardown_drain.py test_faith_rescue_guard.py` → **130 passed**.
New: 7 #1039 regression tests (1 redirect + 6 identity-guard) on top of the 14 base.

## Codex diff-gate iter 1 → iter 2 hardening (3 P1s, all addressed)
Codex iter 1 returned REQUEST_CHANGES with 3 P1s; all fixed:
- **P1.1 (title match too weak):** overlap-coefficient-over-min let a short/subset
  wrong title pass ("Automation" vs the 6-token title → 1/1=1.0). Switched to
  **Jaccard** (intersection/union) ≥ `PG_CORE_TITLE_MATCH_MIN`=0.5 **AND** a floor
  of `PG_CORE_TITLE_MIN_SHARED_TOKENS`=2 shared tokens. Now "Automation" (1/6≈0.17,
  1 shared) and "Automation and Labor" (2/6≈0.33) both REJECT; a genuinely
  truncated correct title (4/6≈0.67) still passes.
- **P1.2 (no-hint path trusted DOI alone):** an independent title anchor is now
  REQUIRED for ANY positive return. No `expected_title` (incl. CrossRef failure →
  None) ⇒ `("", "")`. CORE fullText is never trusted on DOI-equality alone.
- **P1.3 (runnable scripts still touched Sci-Hub):** flipped `PG_SCIHUB_ENABLED`
  default `"1"`→`"0"` in 11 launcher/smoke config dicts (run_full_scale_v10..v30,
  run_m_live_1_smoke, run_phase_g_full_scale); gated the 2 direct `_try_scihub`
  calls (pg_integration_smoke.py, pg_integration_smoke_v2.py) behind
  `PG_SCIHUB_ENABLED=="1"` so the smokes never issue a sci-hub.* request by default.

Live re-verify (hardened): Acemoglu DOI → 0 with CrossRef anchor, 0 with no anchor,
0 with a subset "Automation" anchor; true-positive OA DOI → 25 000 chars with its
title anchor, 0 with no anchor. 132 tests pass (4 new #1039 identity tests added).
