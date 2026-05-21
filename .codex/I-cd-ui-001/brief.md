# Codex BRIEF review — I-cd-ui-001 (#704) UI visual identity overhaul

HARD ITERATION CAP: 5 per document. This is iter N of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

This is a BRIEF (design-spec) review — confirm the design is sound + safe BEFORE I implement. The brief IS the work for a UI task.

## Operator context
Deployed home (https://polarisresearch.ca) was flagged "fucking ugly as fuck" — pure-monochrome (every token `oklch(... 0 0)`, zero chroma). #704 operator-selected direction: Perplexity-style frontier-research-tool home + single cyan accent. Carney-demo visible surface.

## Scope (this PR) — split confirmed
**IN:** design tokens (globals.css) + home (page.tsx) redesign + IntakeForm `?q=` prefill + recent-runs strip component + home_g1_g8 Playwright spec update.
**OUT (sibling #707):** /runs/[runId] staged-progress screen (consumes #706 SSE). Do NOT expand into it.

## Verified facts (grounded, not guessed)
1. `GET /api/v6/runs` is GLOBALLY auth-gated: `FastAPI(..., dependencies=[Depends(_require_auth)])` (src/polaris_v6/api/app.py:80). A logged-out home visitor's fetch returns **401**. ⇒ recent-runs strip MUST render `null` on 401/empty/error — NEVER show an error on the public home.
2. `web/tests/e2e/home_g1_g8.spec.ts` (active CI gate, web_ci) asserts: exactly 1 `<header>`, `nav[aria-label='Primary']` visible + its 8 nav links, exactly 1 `<main>`, `template-card-clinical-link` testid visible + focus-visible, no banned dev strings, zero console errors. Redesign MUST preserve all of these; spec updated in THIS PR for any new/changed text.
3. `useSearchParams` (Next 16, web/node_modules/.../use-search-params.md) = client hook, `searchParams.get('q')`; component must sit under a Suspense boundary for static routes. IntakeForm is already `"use client"`.
4. Frontend → backend: `fetch("/api/v6/runs?status=completed&limit=5")` (web/lib/api.ts BACKEND_URL="/api/v6"; Next rewrites to backend). Cookie auth.
5. Home renders its OWN header via HomeKeyboardShell (AppShell suppressed on `/` by AppShellGate). intake prefill target: IntakeForm `const [question,setQuestion]=useState("")` (intake_form.tsx:43).

## Design tokens (globals.css) — EXACT values, light + dark
Replace pure-monochrome with zinc-50 + single cyan accent. Foreground stays dark for text contrast.

`:root` (light):
- `--background: oklch(0.985 0.002 247.86)`  (zinc-50, faint cool tint)
- `--foreground: oklch(0.21 0.006 285.9)`     (zinc-900, unchanged-ish dark text)
- `--primary: oklch(0.50 0.20 200)`           (cyan accent — iter-1 P1: darkened L0.55→0.50 so white fg ≥4.5:1 after sRGB gamut clip)
- `--primary-foreground: oklch(0.985 0 0)`    (white on cyan — now ≥4.5:1 at L0.50)
- `--ring: oklch(0.50 0.20 200)`              (cyan focus ring — full strength; see focus-cue note below)
- `--accent: oklch(0.95 0.03 200)`            (very light cyan tint, hover/active surface)
- `--accent-foreground: oklch(0.40 0.13 200)` (deep cyan text on the light cyan tint — verify ≥4.5:1)
- `--card: oklch(1 0 0)` (white card on zinc-50 bg — gives subtle separation)
- LEAVE chart-1..5 ALONE (multi-series data palette is a separate decision; "single accent" interpreted minimally).

`.dark`:
- `--primary: oklch(0.65 0.17 200)` (slightly lighter cyan for dark bg contrast)
- `--primary-foreground: oklch(0.21 0.006 285.9)` (dark text on lighter cyan)
- `--ring: oklch(0.65 0.17 200)`
- `--accent: oklch(0.32 0.05 200)` (muted cyan surface), `--accent-foreground: oklch(0.92 0.04 200)`
- background/foreground/card stay near current dark monochrome (acceptable; demo is light-mode).

## Home (page.tsx) layout — Perplexity-style
Preserve: HomeKeyboardShell wrapper (1 header + Primary nav), 1 `<main>`, footer, template-card-clinical-link testid + focus-visible. Restructure `<main>`:
1. **Hero** (centered, vertical rhythm py-16/20): h1 "What can POLARIS verify for you today?" (text-3xl/4xl, tracking-tight); a search form (max-w-2xl) = Input (placeholder "Ask a research question…") + cyan primary submit Button; on submit → `router.push('/intake?q=' + encodeURIComponent(value))` (client component for the hero, or a small `<form action="/intake" method="get">` with `name="q"` — prefer the form-GET so it works without JS; data-testid="home-hero-search"). Sub-line: the existing one-liner about two-family verified provenance.
2. **Recent-runs strip** (new client component `recent_runs_strip.tsx`): on mount (useEffect, client-only — no SSR fetch), `fetch("/api/v6/runs?status=completed&limit=5", { headers: authHeader() })` where `authHeader` is imported from `@/lib/auth` (iter-1 P1: frontend uses BEARER-token sessionStorage, NOT cookie auth — a raw fetch 401s even for signed-in users; `authFetch` is wrong here because it redirects logged-out visitors to /sign-in, which must NEVER happen on the public home). Render `null` on ANY of: 401, non-ok status, JSON parse failure, network failure, OR empty list. ONLY render the strip when the parsed array is non-empty: (a) has-runs → horizontal row of compact run chips (template + question snippet + finished date) linking `/runs/{run_id}`.
3. **Template cards**: keep the grid + all testids; restyle — active (clinical) card gets cyan accent (border-primary/40, cyan "Open" primary button); inactive stay muted; subtle hover lift (hover:shadow-sm transition). Heading "Research templates" kept.

## IntakeForm `?q=` prefill
`const sp = useSearchParams(); const [question,setQuestion]=useState(sp.get('q') ?? "")`. iter-1 P2: use the `<Suspense>` boundary pattern (the existing `web/app/sign-in/page.tsx` is the precedent — it wraps the useSearchParams client content in `<Suspense fallback={...}>`), NOT `dynamic = 'force-dynamic'`. Wrap the IntakeForm usage in the intake page in `<Suspense>` (or split the q-reading into a small inner client component under Suspense).

## Focus-cue note (iter-1 P2)
The cyan `--ring` at full strength is sufficient on zinc-50, but the repo's common `ring-ring/50` translucent halo alone is only ~1.58:1. Anywhere the focus indicator would rely ONLY on the translucent halo (hero search input, template links), keep a FULL-STRENGTH `border-ring` / full-strength ring so the focus cue meets the 3:1 non-text contrast minimum. Preserve the existing `focus-visible` on the clinical template link (home_g1_g8 asserts it).

## Playwright spec update (home_g1_g8.spec.ts)
Keep all structural asserts (1 header, nav, 1 main, clinical-link, focus-visible, no console errors). ADD: hero search testid visible. UPDATE any text assert that changed (the h1 text). Do NOT weaken existing asserts.

## LOC exemption (documented)
Est ~305 LOC (tokens ~20 + home ~200 + strip ~50 + intake wire ~5 + spec ~30). Exceeds the 200-LOC cap. Requesting exemption: the visual identity is ONE cohesive unit — splitting tokens from the home that consumes them is artificial, and the recent-runs strip's auth behavior is already verified. Per CLAUDE.md §3.0 the cap is a halt-condition unless exempted; documenting the exemption here.

## Review focus
1. Token values: contrast pairs WCAG-AA (primary-fg on primary; accent-fg on accent; cyan ring visible on zinc-50). Flag any pair < 4.5:1 (text) / 3:1 (UI).
2. The 401/empty/error → null strip behavior — correct + safe for the public home?
3. Next-16 correctness: form-GET vs router.push for the hero; useSearchParams Suspense requirement for IntakeForm prefill.
4. Anything that would break the home_g1_g8 gate that I haven't accounted for.
5. LOC exemption reasonable, or should the strip split to a follow-up?
6. Any NOVEL P0/P1.

## Output schema
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

---
## iter-2 changelog (addressing iter-1 REQUEST_CHANGES)
- P1 contrast: `--primary` L0.55→**0.50** (white fg now ≥4.5:1).
- P1 auth: recent-runs strip uses `fetch(url, { headers: authHeader() })` (bearer, NOT cookie, NOT authFetch) → null on 401/non-ok/parse-fail/network-fail/empty; never redirects.
- P2 Suspense: IntakeForm prefill uses the sign-in `<Suspense>` precedent, not force-dynamic.
- P2 focus-cue: full-strength ring/border-ring where halo-only would be <3:1.
