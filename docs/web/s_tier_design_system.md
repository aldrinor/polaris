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
- **Home** (#835, I-p2-044): **desktop A / fold A− / mobile A−** (Codex visual iter-2
  APPROVE). Fixed the "Sovereign Canadian deep research" present-tense overclaim → honest
  "Canadian-hosted deep research"; compacted the hero so the real ProofShowcase enters the
  first viewport as the front-door artifact (brand-tinted elevation); pillars are crafted
  cards; mobile proof overflow fixed (min-w-0 + break-words); also fixed the global
  `layout.tsx` `<title>` "Sovereign Deep Research" overclaim. Known pre-existing (not this
  PR), two distinct causes: **G2** (no-banned-dev-language) uses `body.textContent()`, catching
  the hero Input's `placeholder:` class in the RSC payload (`/placeholder/i`) — proven to fail
  on the baseline too; fix = switch to `innerText` like the inspector spec. **G8**
  (zero-console) fails on a 500 from `/api/v6/runs?status=completed` (RecentRunsStrip) when no
  v6 backend runs in the test env — unrelated to G2. Both follow-ups.
- **Intake** (#837, I-p2-045): **desktop A− / mobile A−** (Codex visual iter-1 APPROVE). Was
  a small Check-scope card floating in an empty page; now a "CLINICAL SCOPE DISCOVERY" eyebrow
  + enlarged hero input + a factual 3-step "how it works" band (ask → scope-checked → verified
  brief) filling the surface. Restored the eyebrow string the existing `intake.spec` asserts
  (stale since the #613 rebuild) — a design element, not a test relaxation.
- **Contracts** (#839, I-p2-046): **desktop A / mobile A−** (Codex visual iter-2 APPROVE). A
  crafted static "Save + download" action bar (ring + brand shadow + explainer; iter-1 sticky
  version overlaid fields → made static), entity-type select height matched to inputs, chips +
  selects on the shared motion primitive, mobile entity row stacks. All field logic/testids
  preserved.
- **Upload** (#841, I-p2-047): **desktop A / drag-active A+ / mobile A** (Codex visual iter-1
  APPROVE). Crafted drop zone (UploadCloud icon + real drag-active brand-tint state + hover +
  focus + motion; drag-depth counter to avoid child-flicker), tokenized error, and a factual
  3-step "what happens after upload" band + /intake link filling the empty surface. Logic +
  testids preserved.
- **Pin Replay** (#843, I-p2-048): **empty state desktop A / mobile A−** (Codex visual iter-1
  APPROVE). In the demo the registry is empty (since #627) so the empty state is the only
  visible state; added a ghost-timeline skeleton (data-free) + concept caption so the page
  makes the temporal-drift differentiator tangible. Known pre-existing (NOT this PR, proven on
  baseline): `pin_replay_g1_g8` G8 fails on a Next-16 RSC `Set`-serialization warning ("Set
  objects are not supported" server→client) — follow-up.
- **Sign-in** (#845, I-p2-049): **desktop A / mobile A** (Codex visual iter-1 APPROVE). Fixed
  THREE present-tense sovereignty overclaims — narrowed (Codex P1) so they can't be read as
  covering US-routed LLM inference: "Sovereign Canadian processing" → "Canadian-hosted evidence
  records, integrity-hashed"; strip → "Canadian-hosted research workspace"; mobile lockup →
  "Canadian-hosted Workspace". Institutional split-screen preserved.

**All 7 PUBLIC pages now at the A bar** (Inspector A/A-/A/A- · Home A/A-/A- · Intake A-/A- ·
Contracts A/A- · Upload A/A+/A · Pin Replay A/A- · Sign-in A/A), each dual-Codex-gated
(visual `-i` + code) → merged → deployed → verified live.

### Cred-gated pages (rendered locally via seeded session + route-mocked fixture; LIVE-populated verify deferred to reviewer creds)

- **Dashboard / Runs** (#849, I-p2-051): **desktop A / mobile A- / empty A** (Codex visual iter-1
  APPROVE). Fixed a real CJK-date locale bug (`toLocaleDateString(undefined)` → `"en-CA"`; same
  fix on Home's `recent_runs_strip`), elevated the runs list (`shadow-card`), mobile title
  `line-clamp-2`.
- **Benchmark** (#851, I-p2-052): **desktop A / mobile A- / empty A- / error A- / list A** (Codex
  visual iter-2 APPROVE). Replaced dev-language amber/rose state cards (leaked
  `POLARIS_BENCHMARK_RESULTS_DIR` / `scripts/run_benchmark.py`) with the state-kit + tokens;
  headline tally, brand POLARIS column, tabular-nums, `--verified` winners, dash + "POLARIS-only"
  for unreported peer dims, readable stacked mobile. Removed a hardcoded "scores 1.0" overclaim
  (LAW II) — capability claim, scores come from the published scoreboard. The empty state is the
  live-visible state.
- **Memory** (#853, I-p2-053): **desktop A / mobile A- / empty A** (Codex visual iter-2 APPROVE).
  Was the rawest cred-gated page (raw controls, raw enum labels, `bg-blue-500`/`bg-rose-500`, NO
  loading/error/empty states). Rebuilt to the design system: Card form (human kind labels, raw
  option values preserved for the e2e), state-kit states, meaning-tinted kind chips
  (preferred=verified / rejected=refusal / rest neutral, brand reserved for the Remember action),
  3-line rows + "SAVED MEMORY · N". Fixed a `react-hooks/set-state-in-effect` lint blocker (Codex
  diff P1) via the codebase IIFE-in-effect idiom.

- **Compare** (#855, I-p2-054): **result desktop A / result mobile A / picker A / empty A** (Codex
  visual iter-2 APPROVE). Added a LoadingState + designed EmptyState; fixed a confusing brand-red
  `✓` flag (now `--verified` green Check for pass, muted X for an informational mismatch);
  tokenized the run-picker selects; Card-elevated the picker + headline + evidence + frame-coverage
  + contradictions. Run identity made unambiguous (Codex iter-1 P1): option labels lead with the
  unique run id + date, and the result header shows the compared pair (`left ↔ right`).

- **Source Review** (#857, I-p2-055): **populated desktop S- / mobile A++ / error A+** (Codex
  visual iter-2 APPROVE). Already the strongest cred-gated page (state-kit states, tier-token dots,
  exemplary honest framing — shows the curated source-set DEFINITION + per-tier adequacy bar, not a
  fabricated corpus or readiness %). Assess-first: gave the question / tier / "how sources" cards
  brand-tinted `shadow-card` + `rounded-xl` (were flat) for parity with the set, and added a
  "Try again" retry to the error state (Codex iter-1 P2). The honest no-fabricated-corpus framing
  is preserved.

- **Plan review** (#859, I-p2-056): **ready desktop A / ready mobile A / blocked A / no-question
  A-** (Codex visual iter-1 APPROVE). The run-start surface (intake → plan → run); on mount it
  re-runs the full intake gate, and Start is enabled only for an in_scope, disambiguation-resolved
  question. Assess-first: gave the question card + the four "What POLARIS will do" step cards
  `shadow-card` + `rounded-xl`, and toned the four step icons from brand-red to muted (brand
  reserved for the single Start-run action). The scope/concurrent guards + honest framing
  preserved. Residual P2 (accept_remaining): no-question empty state vertical rhythm.

Remaining cred-gated UI: the Run-progress page (the last journey leg). LIVE-populated verification
of all cred-gated pages awaits the demo reviewer credential.
