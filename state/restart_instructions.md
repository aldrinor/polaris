# Restart Instructions — issue-driven workflow (post 2026-05-05 restart)

## Boot ritual (mandatory per CLAUDE.md §10)

1. Read `CLAUDE.md` completely (project directives, especially §-1, §3.0, §10).
2. Read `polaris-controls/CHARTER.md` and `PLAN.md` (admin-only sister repo nested at `C:\POLARIS\polaris-controls\`).
3. Verify BOTH SHAs against `state/polaris_restart/charter_sha_pin.txt`. Either-file mismatch = HARD STOP per §3.1 step 0.
4. Read `state/active_issue.json`.
5. Read `docs/stier_experience_directive_2026_05_24.md` — the operator's S-tier directive (Codex decides everything, no checkpoints, frontier-BEATING bar).
6. Re-load CHARTER `I-ux-001` umbrella issue **#872** for the current S-tier workstream.

## CURRENT WORKSTREAM (resume point as of 2026-05-24)

**I-ux-001 — S-tier experience initiative** (GH#872 umbrella) — execute all pages at frontier-BEATING bar.

### Status as of this handover

| Sub-issue | GH# | State | What landed |
|---|---|---|---|
| I-ux-001 plan | umbrella #872 | APPROVED (Codex uncapped iter 5 v4) | `docs/stier_experience_plan.md` |
| I-ux-001a — Prereq 0: signed-bundle moat | #873 | OPERATOR MERGE QUEUE (codex-required PASS) | `web/lib/gpg_verify_bundle.ts`, tri-state SignatureBadge, gpgv-isolated keyring verifier, CI guard `scripts/check_signed_bundles.py`, Dockerfile gnupg install |
| I-ux-001a — Real demo signed bundle | #875 | OPERATOR MERGE QUEUE | `scripts/build_canonical_demo_bundle.py` signs by default; ships `polaris_demo_pubkey.asc` + `state/polaris_gpg_keyid.txt` |
| I-ux-001b — Figma hero prototype | #877 | OPERATOR MERGE QUEUE | 5 Codex visual-audit rounds B → B+ → A → A/A → A/A-+GREENLIGHT; v6 applied A+ unlock spec (unified Sealed evidence block + "matched 6 of 6 numbers" stamp + sentence-case ladder); Figma file `Is7pehpxPdn3ZOOgCsyUjs`; screenshots `web/p2shots/I-ux-001b/hero_stage{2,4}_v{1..6}_*.png` |
| I-ux-001c — Hero implementation | #878 | **NEXT WORK** | Next.js + Tailwind v4 build of the prototyped hero |

### Operator standing directive (2026-05-24) — REMAINS BINDING

Anchored in `docs/stier_experience_directive_2026_05_24.md` + memory `feedback_codex_decides_all_stier_uncapped_2026_05_24.md` + `.claude/hooks/stier_session_start.py` + `.claude/hooks/stier_stop_hook.py`:

- **Codex decides EVERYTHING.** NEVER ask operator. NEVER use Opus advisor() tool.
- **NO ITERATION CAP** on the I-ux-001 plan review (per-Issue diff/brief gates keep §8.3.1 5-cap).
- **DON'T checkpoint / report status / pause / ask "should I continue."** Forbidden self-stops per §8.3.10.
- **§8.4 resource discipline:** ONE `codex exec` at a time; kill YOUR strays (codex/python/node); NEVER touch operator's other-project processes.
- **LAW II — Real Data Only, No Silent Fallbacks, Fail Loudly.**
- **`gh pr merge --admin` REVOKED.** Operator handles morning merge.
- **Brand red `#c8102e` LOCKED.**
- **Honest sovereignty wording only** (LLM via OpenRouter-US disclosed at /transparency).
- **Per-sentence provability + signed two-family bundle = core differentiator** — do not dilute.
- **Demo reviewer credential is a REAL SECRET** — use without echoing/committing.
- **When context nears full:** update `state/restart_instructions.md` (this file) → auto-compact → continue.

## NEXT CONCRETE ACTION

**Open `I-ux-001c — Hero implementation` (GH#878)** — Next.js + Tailwind v4 build of the Codex-greenlit proof-replay prototype.

### Step-by-step from cold boot

1. Boot ritual (§3.1 step 0 canonical pin + CHARTER+PLAN SHA).
2. `git checkout polaris && git pull` (ensure #873/#875/#877 merged by operator overnight; if not, work proceeds on a branch off `bot/I-ux-001b-foundation`).
3. `git checkout -b bot/I-ux-001c-hero-implementation`.
4. **GitHub Issue already exists: #878.** Read it.
5. **Comprehensive grep adjacent files** (§-1.2 step 2):
   - `web/components/inspector/inspector_proof_header.tsx` (current hero band — needs upgrade)
   - `web/components/inspector/bundle_header.tsx` (SignatureBadge tri-state — already correct)
   - `web/components/inspector/family_segregation_badge.tsx`
   - `web/lib/inspector_bundle_loader.ts` (now returns `signatureState`)
   - `web/app/inspector/[runId]/page.tsx` (current consumer)
   - `web/app/runs/[runId]/page.tsx` (target location for Proof Replay tab)
   - `web/components/proof_replay/*` (any existing proof-replay components from P2-seq-07 #746)
   - `web/components/citation_chip*` (P2-seq-04 #743), `verdict_chip*` (#744), `evidence_card*` (#745)
   - `docs/web/proof_replay_storyboard.md` — 6-beat reveal, mobile bottom-sheet, reduced-motion equivalent
   - `docs/web/components_catalogue.md` — ClaimSentence, ProofPanel, FaithfulnessChip (checklist grammar), CertaintyBadge (ordinal ladder), unified SourceCard+SourceSpanPreview Sealed evidence block, SignaturePill, WhatThisDoesNotProve, IntendedUseBanner
   - `docs/web/design_tokens_v2.md` — type, two-judgment color (faithfulness green/amber/magenta-red vs brand red; evidence-strength slate-blue ordinal), motion tokens
6. **Smoke test offline:** verify the existing real signed bundle at `web/public/canonical_bundles/v1_canonical_success/` loads with `signatureState=gpg_verified` (depends on #875).
7. **Write brief `.codex/I-ux-001c/brief.md`** — start with §8.3.1 cap directive verbatim. Reference v6 screenshots + storyboard + catalogue + tokens. Acceptance: built page matches prototype at the same A+ bar via Codex `codex exec -i live_render.png` visual audit; Time-to-first-proof <400ms; claim-to-claim switch <120ms perceived; six microstates + reduced-motion; WCAG 2.2 AA (axe 0); verified LIVE on polarisresearch.ca.
8. Codex brief gate → diff → Codex diff gate → live visual audit → operator merge queue.

### Reference artifacts

- **v6 desktop screenshot:** `web/p2shots/I-ux-001b/hero_stage2_v6_desktop.png` (164805 bytes)
- **v6 mobile screenshot:** `web/p2shots/I-ux-001b/hero_stage4_v6_mobile.png` (46649 bytes)
- **Codex iter-5 verdict (greenlight):** `.codex/I-ux-001b/visual_audit_v5.txt`
- **Figma file:** `Is7pehpxPdn3ZOOgCsyUjs` (desktop node 1:2, mobile node 14:2)
- **Real signed bundle:** `web/public/canonical_bundles/v1_canonical_success/` (signed by `FB221F...01CC`, GPG-verifiable offline via `scripts/check_signed_bundles.py`)

## Workflow rules (binding)

Per CLAUDE.md §3.0 + plan §7.A LOCKED A2 + §7.B LOCKED B1:

- **Claude:** writes code (briefs + diffs + claude_audit).
- **Codex:** reviews. Two APPROVE gates per Issue (brief + diff). 5-iter cap per §8.3.1 (NOT the umbrella plan — that's uncapped per I-ux-001 directive).
- **User:** spec owner + after-the-fact merge gate. Reads `git log` in morning (B1 pure auto-merge). CI required check `polaris/codex-required` enforces.

**Per-Issue 5-artifact triple** (CI rejects PR without these):
- `.codex/<issue_id>/brief.md`
- `.codex/<issue_id>/codex_brief_verdict.txt` (APPROVE)
- `.codex/<issue_id>/codex_diff.patch` (with `# canonical-diff-sha256: <hex>` trailer)
- `.codex/<issue_id>/codex_diff_audit.txt` (APPROVE)
- `outputs/audits/<issue_id>/claude_audit.md` (`git add -f` past .gitignore `outputs/*` rule)

## Deferred workstreams

- **#871 / I-bug-900 URGENT** — live clinical run aborts `corpus_inadequate`; tier-classifier mis-tiers FDA/NICE/PubMed; T1=0; demo blocker. Codex said sequence in parallel, not before hero ships.
- **P3 run-quality bugs** — #702 #703 #675 #676 #537.
- **Phase 0 hardware + sovereign migration chain** — deferred until after Carney demo lands. Posture (c) means Carney demo uses OpenRouter; sovereign vLLM on OVH H200 becomes Phase 2.
