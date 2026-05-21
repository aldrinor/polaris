# I-ui-001 (#704) — UI visual identity overhaul (design record)

Rebranded from I-cd-ui-001 (codex-required branch-id schema). Full Codex
brief review (2 iters) + diff review (1 iter) trail is on the superseded
bot/I-cd-ui-001-visual-identity branch + PRs #718.

Direction: Perplexity-style frontier-research-tool home + single cyan accent.
- globals.css: zinc-50 surface + cyan accent oklch(0.50 0.20 200) light /
  0.65 dark. Codex-verified AA: primary/fg 4.53:1, accent/fg 6.96:1,
  ring 4.53:1. chart-* left monochrome.
- home: hero 'What can POLARIS verify for you today?' → progressive GET
  form (action=/intake, name=q) → /intake?q=; recent-runs strip (consumes
  GET /api/v6/runs #705 via bearer authHeader; null on 401/empty/any fail);
  cyan active template card + hover lift. Preserves home_g1_g8 structure.
- intake: ?q= prefill via useSearchParams under <Suspense> (sign-in precedent).

Codex caught 2 P1 at design time: primary contrast (L0.55→0.50 for AA) +
bearer authHeader strip (not authFetch — no public-home /sign-in redirect).
Diff P2: true zinc-50 (hue 286) vs gray-50 — fixed.

Verdict: brief APPROVE iter 2; diff APPROVE iter 1 + MERGE AUTHORIZED.
Smoke: typecheck clean, lint 0 errors, npm build succeeds.
