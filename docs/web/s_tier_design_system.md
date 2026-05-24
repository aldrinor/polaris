# POLARIS S-tier design system (canonical)

**Status:** authoritative. Source: Codex vision-authored direction
(`.codex/ui_visual_audit/s_tier_direction_verdict.txt`, 2026-05-23), grounded in
2026 best practice + Stripe/Linear/Vercel premium-UI invariants. Bar = **A++/S**,
visually competitive with AND differentiated from Perplexity / ChatGPT Deep
Research / Gemini. Tracking issue: #829 (umbrella), foundation #831 (I-p2-042).

## The signature move (the differentiator)

**Proof Replay is the product's visual operating system, not a component.**
Every screen reuses the same grammar: `claim sentence → provenance token → cited
source span → evaluator verdict → audit hash`. "Perplexity owns sources-near-answers;
POLARIS owns _every sentence is cross-examinable_." Proof tokens, the proof rail,
span highlights, and verdict badges appear consistently across the product.

## Tokens

- **Type:** Geist only. Scale: display 40/44·700, h1 32/38·700, h2 24/30·700,
  h3 18/26·600, body 16/24·400, body-sm 14/21·400, caption 12/16·500 (uppercase
  labels +0.08em), mono 13/18·500. Tabular nums for clinical values; mono for
  IDs/hashes/dates/model names.
- **Spacing grid:** 4 / 8 / 12 / 16 / 24 / 32 / 48 / 64 / 96. Page top pad 64
  (desktop) / 32 (mobile); section gap 48; card pad 24; inspector pad 16; form
  field gap 16. Max content 1120px / workbench 1200px. Spacing must be _invisible
  because systematic_ — never mix 16 and 24 arbitrarily.
- **Color (restraint):** near-neutral + ONE accent — **Canada red `#c8102e`
  (operator-locked 2026-05-21; do NOT change)** used once/screen, meaning-only
  (primary action or active proof mark, never decoration). Verified = green
  (`--verified`), warning = amber (`--contradiction`), danger = `--destructive`,
  refusal = neutral-strong. Evidence-role tokens: tier-1/2/3, proof-token,
  verified-bundle.
- **Radius:** cards `rounded-xl` (~12px), controls ~8px, pills full.
- **Border / shadow:** hairline `ring-foreground/10` (1px low-alpha) plus
  brand-tinted elevation `--shadow-card` / `--shadow-card-hover` (a neutral
  hairline lift and a faint Canada-red wash — never pure gray).
- **Motion:** ONE primitive — `--ease-standard: cubic-bezier(0.2,0.8,0.2,1)`,
  ~150–160ms. Reuse on hover/focus/tab/inspector-selection/span-reveal/skeleton.
  No ornamental animation.
- **Microstates (non-negotiable, every interactive element):** default / hover
  (brand-soft or neutral tint) / focus (custom 2px ring `ring-ring/…` + 2px
  offset, visible) / active (slight inset, buttons translateY(1px)) / disabled
  (opacity ~.45, no pointer) / loading (skeleton matching layout, never a bare
  spinner).
- **Empty/loading/error:** evidence-native + designed (ghost timeseries, claim-row
  skeletons, contract preview shell). Errors explain _which_ gate failed
  (scope / coverage / evaluator disagreement / infrastructure).

## Verification protocol (every UI PR)

1. GitHub issue first; close on merge.
2. Build the page/primitive to the spec; preserve logic + `data-testid`s.
3. **Dual visual gate:** Claude views the screenshots AND Codex audits them via
   `codex exec -i` at the A++/S bar — every state (empty/loading/error/populated)
   × desktop/tablet/mobile. Plus Codex CODE review (brief + diff).
4. e2e (Playwright) green; visual-regression baselines refreshed on intentional
   pixel changes.
5. Update this doc + `docs/file_directory.md`; deploy + live-verify.

## Build order

1. **Foundation tokens** (#831 / I-p2-042) — motion + brand-tinted shadow applied
   to Card; type/spacing/color already tokenized. ← _in progress_
2. **Primitives** — Button/Input/Select/Chip/Tab/Card/Badge/Skeleton/EmptyState,
   plus the proof primitives (ProofToken/ProofRail/SourceSpan/VerdictBadge).
3. **Proof system** — ClaimStack / ProofReplayPanel / EvaluatorVerdict /
   AuditHashChain.
4. **Pages** (S-bar, worst-gap weighted): Inspector ✓ (#833, dual visual gate iter-3
   APPROVE) → Home → Intake → Contracts → Upload → Pin Replay → Sign-in.
5. **Cred-gated** (need `POLARIS_DEMO_USER`/`POLARIS_DEMO_PASS`): dashboard,
   benchmark, memory, source-review, and the Plan → Run → Compare journey.

## Per-screen S-bar baseline (Codex visual gate, `-i`)

- **Inspector** (#833, I-p2-043): **desktop A / mobile A− / manifest A / abort A−**
  (Codex visual iter-3 APPROVE). The audit metadata no longer leads — a bespoke
  proof-header band (research question → verify-rate headline → grouped trust chips →
  zero-loss manifest disclosure) makes Proof Replay the centerpiece. Residual P2 (deferred):
  mobile evidence-card density lives in the Proof Replay split-view internals (separate
  component issue); the lower-left "N" badge in dev captures is the Next.js dev indicator
  (absent in production builds).
- Pre-redo baseline (Codex, 2026-05-23): Home B, Intake B−, Contracts B− (post first
  rebuild), Sign-in B−, Upload C+, Pin Replay C. Target every screen at A++/S with the
  signature move systematized.
