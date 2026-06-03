# I-faith-002 / #1035 / #1039 — CORE legal-OA full text replaces Sci-Hub

## Goal (operator directive)
Replace the illegal Sci-Hub access path with the CORE (core.ac.uk) v3 API as the
LEGAL best-effort OA full-text source, wired into the production retrieval path,
smoke-tested to confirm it is "truly ready, wired and functional."

## Acceptance criteria
1. Sci-Hub is OFF by default on EVERY runnable path (production + scripts); no
   sci-hub.* request is issued without explicit operator opt-in.
2. CORE is wired CORE-first at `frame_fetcher` Step 2b as the legal OA full-text
   source, DOI-keyed.
3. CORE NEVER admits a wrong paper into the clinical span-grounded path
   (CORE mis-tags distinct papers under one DOI — proven live).
4. `core_client` is env-driven (LAW VI), never raises, falls back to `("","")`.
5. Tests green; behavior re-verified against LIVE CORE.

## Approach
- `access_bypass.py`: `PG_SCIHUB_ENABLED` default `"1"`→`"0"`; the single
  `_try_scihub` call site stays gated. 11 launcher/smoke scripts flipped to `"0"`;
  2 direct `_try_scihub` calls gated behind the opt-in flag.
- `src/tools/core_client.py` (NEW): `fetch_core_oa_fulltext(doi, *,
  expected_title, expected_year)` — DOI-keyed query with `follow_redirects=True`
  (CORE 301-redirects), and a CONTENT-IDENTITY guard: a result's `fullText` is
  trusted only when its title is a SUBSET of the CrossRef-authoritative
  `expected_title` (rejects drug substitution AND identity-adding superset =
  sibling trial) with a coverage floor and a min-shared-token floor; an
  independent title anchor is REQUIRED (no DOI-only trust).
- `frame_fetcher` Step 2b passes the CrossRef-resolved title/year as the anchor.

## Evidence
Full RCA + live proof: `.codex/I-faith-002/core_1039_fix_proof.md`.
Diff gate: `.codex/I-faith-002/codex_diff_audit.txt` (APPROVE, iter 4).
