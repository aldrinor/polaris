# Claude architect audit — I-p2-044 (#835): Home page S-rebuild

## Goal
Move the front door (`/`) from a clean-but-generic B to A++/S — proof-led + differentiated —
and fix the sovereignty overclaim.

## What changed (4 files, +43/-21)
- `web/app/page.tsx`: hero pill "Sovereign Canadian deep research" → "Canadian-hosted deep
  research"; pillar "Sovereign" → "Canadian-hosted" (honest body); compacted hero vertical
  rhythm so ProofShowcase enters the first viewport; pillars plain columns → crafted elevation
  cards.
- `web/app/components/proof_showcase.tsx`: shadow-sm → brand shadow-card + hover (front-door
  centerpiece); mobile overflow fix (grid cells min-w-0; claim + blockquote break-words/
  hyphens; CTA row flex-wrap). Real-data path + `proof-showcase` testid unchanged.
- `web/app/layout.tsx`: global metadata.title "POLARIS Canada — Sovereign Deep Research" →
  "Canadian-hosted Deep Research" (Codex diff-review P1 — a residual present-tense overclaim
  I missed in the first pass; caught by the gate).
- `docs/web/s_tier_design_system.md`: Home per-screen grade + honest e2e triage.

## Honest-sovereignty (correctness, line-by-line)
Three present-tense overclaims removed: the hero pill, the "Sovereign" pillar, AND the global
`<title>` (verified in the rendered dev `<title>` = "POLARIS Canada — Canadian-hosted Deep
Research"). LLM inference is currently routed via OpenRouter-US (disclosed at /transparency).
No present-tense sovereignty claim remains on the home page.

## No fabricated proof (LAW II)
ProofShowcase + RecentRunsStrip render REAL data; their data logic is untouched — only card
elevation + mobile wrapping changed.

## e2e (home_g1_g8) — honest status, two distinct pre-existing failures
4/6 pass: G1 (single header), G3 (Verify focus-visible), G5 (3 viewports), form→/intake.
- **G2** (no-banned-dev-language) fails: uses `body.textContent()` (includes the RSC `<script>`
  payload), catching the unchanged hero Input's `placeholder:text-muted-foreground` class +
  `placeholder=` attr via `/\bplaceholder\b/i`. Proven to fail on the live BASELINE prod home
  (pre-this-change) too → pre-existing, not introduced here. Follow-up: switch G2 to
  `innerText` like the inspector spec.
- **G8** (zero-console) fails: a 500 from `/api/v6/runs?status=completed` (RecentRunsStrip)
  when no v6 backend runs in the test env — pre-existing, unrelated to this CSS+copy change.
Neither relaxed to hide a bug (standing rule); the CI e2e lane is non-functional regardless
(#720 backend boot).

## Dual Codex gate
- Brief APPROVE (iter 1, grounded on the live B-grade screenshot).
- Visual `-i` APPROVE (iter 2: desktop A / fold A- / mobile A-). iter-1→2 closed 2 P1s (mobile
  proof clipping; the Next dev-indicator "N" badge, dev-only/absent in prod).
- Code diff APPROVE (iter 2: caught + fixed the residual <title> overclaim P1) —
  `.codex/I-p2-044/codex_diff_audit.txt`.

## Constraints honored
Brand `#c8102e` untouched; tokens only; honest sovereignty wording (now incl. <title>); real
proof preserved; no test relaxation; no silent fallback.

canonical-diff-sha256: a3be626e4076aaa39e8d4ae3054838bc3e1aad96a618bf6fd7af6414c43b1bc4
