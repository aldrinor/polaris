# Claude architect audit — I-faith-002 / #1039 (CORE replaces Sci-Hub)

## Verdict: the fix meets every acceptance criterion; verified line-by-line + live.

### AC1 — Sci-Hub OFF on every runnable path
- `access_bypass.py:955` default `PG_SCIHUB_ENABLED="0"`; the ONLY `_try_scihub`
  call site (line 959) is inside the `== "1"` guard (grep-confirmed: one src call
  site). `frame_fetcher` independently rejects any `access_method` containing
  `scihub`.
- 11 launcher/smoke scripts flipped `"1"`→`"0"`; the 2 direct `_try_scihub` calls
  (pg_integration_smoke{,_v2}.py) gated behind the opt-in flag; stale "kept on"
  comments corrected. Codex diff-gate P1.3 + P2 — addressed.
- VERDICT: PASS.

### AC2 — CORE wired CORE-first
- `frame_fetcher` Step 2b tries `fetch_core_oa_fulltext(doi, expected_title=title,
  expected_year=year)` first, then the Sci-Hub-free AccessBypass on `("","")`.
  Telemetry parity preserved (every attempt logged). VERDICT: PASS.

### AC3 — never admits a wrong paper (the clinical-safety core)
The guard evolved through 3 Codex rounds; final rule: a CORE result's `fullText`
is trusted only if (a) DOI exact-match, (b) an independent title anchor exists,
(c) the candidate title is a SUBSET of the CrossRef-authoritative expected title
(adds no token), and (d) coverage ≥ 0.5 with ≥ 2 shared tokens.
- LIVE: Acemoglu DOI `10.1257/jep.33.2.3` → `("","")` (was 25 000 chars of a
  mis-tagged Spanish paper). No-anchor → `("","")`. Subset-wrong-title → reject.
- Drug substitution (semaglutide vs tirzepatide) → reject. Population superset
  (… in People with Type 2 Diabetes) → reject. Happy path (CORE title ⊆ anchor)
  → 25 000 chars. VERDICT: PASS.

### AC4 — env-driven, never raises
- All tunables `PG_CORE_*` from env (LAW VI). No key → `("","")` w/o request.
  Network/non-200/malformed/redirect/mismatch all → `("","")`. VERDICT: PASS.

### AC5 — tests + live
- 92 (core_client + frame) + access_bypass/faith suites → 107–134 pass across runs.
  conftest forces `PG_CORE_ENABLED=0` unconditionally (hermeticity). Live
  re-verified after every change. VERDICT: PASS.

## Residual (non-blocking, Codex accept_remaining)
- The subset-only title rule is conservative: it rejects a CORE record whose title
  legitimately adds a subtitle CrossRef lacks → abstract fallback. Correct for a
  clinical-safety system (CORE is best-effort; faithfulness is paramount).
- Two P2 cosmetics (stale comments / smoke wording) — fixed.
