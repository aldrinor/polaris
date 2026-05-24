# Claude architect audit — I-p2-051 (#849): Dashboard (Runs) S-audit + CJK-date fix

## Goal
First cred-gated page (build-order step 5). /dashboard fetches GET /api/v6/runs and
401-redirects to /sign-in on the live site without a real reviewer JWT — so it was audited by
rendering LOCALLY (seeded client session + Playwright route-mocked /runs fixture) to actually
SEE the populated layout + the empty/error states. The fixture is visual-audit-only — never
shipped; the page keeps fetching real data.

## What looking-at-it found (the value of rendering)
A real bug only a render catches: run dates showed as CJK ("2026年5月21日"). `formatWhen` used
`toLocaleDateString(undefined, …)`, which falls back to the host/system locale → Japanese dates
on a non-English server. On a Canadian gov demo dates must be deterministically English.

## What changed (2 files, +9/-4)
- `app/dashboard/page.tsx`: `formatWhen` `undefined` → `"en-CA"` (English dates); runs-list
  `<ul>` gained brand `shadow-card` + `overflow-hidden` (elevation); run-row title
  `line-clamp-1` → `line-clamp-2` (Codex visual P2, mobile scanability).
- `app/components/recent_runs_strip.tsx`: the SAME CJK-date bug (Home's recent-runs strip) →
  `"en-CA"`. Fixed in-scope as the date-locale-class fix (Home had the identical latent defect).

## Preserved
The real `listCompletedRuns` fetch, the verdict logic (success→Verified / abort_*→Declined /
error_*→Error tokens), and testids (dashboard-page, dashboard-start-run, runs-list, run-row-*).
The page was already a competent tokenized list — assessed first, only the above changed.

## Dual Codex gate
- Brief APPROVE. Visual `-i` APPROVE (iter 1: populated desktop A / mobile A- / empty A) on the
  mock-rendered states. Code diff APPROVE (iter 1, zero findings; "en-CA" valid BCP-47).

## Honest verification state
LIVE-populated verification on polarisresearch.ca is DEFERRED — the page 401-redirects there
without the real reviewer credential. I verified the layout + states against a route-mocked
fixture (visual audit only) + the natural empty/error states. NOT live-verified with real data;
that step needs the reviewer credential.

## Constraints honored
Brand `#c8102e`; tokens only; logic/testids preserved; no fabricated SHIPPED data; no test
relaxation.

canonical-diff-sha256: 159334464d2ad6beac3b280cdffa2dec6fc8e90be8612e44b45190253232c2df
