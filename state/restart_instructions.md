# Restart Instructions — ACTIVE: I-ux-001 S-tier experience initiative (2026-05-24)

## ⚡ CURRENT WORKSTREAM (resume point as of 2026-05-25)

**I-ux-001 — S-tier experience plan + execution (GitHub #872).** Operator directive 2026-05-24, operator ASLEEP, **FULL AUTHORIZATION**. Autonomous, multi-session.

**Read first on resume:**
1. `docs/stier_experience_directive_2026_05_24.md` — the full directive + operating model + research synthesis.
2. `.claude/hooks/stier_directive.txt` — the TL;DR (also auto-injected by the SessionStart hook after compaction).
3. Memory `feedback_codex_decides_all_stier_uncapped_2026_05_24.md`.
4. `docs/stier_experience_plan.md` v4 (Codex APPROVE'd) + `.codex/I-ux-001/PLAN_APPROVED.md`.

**Operating model (binding):** Codex decides ALL — never ask the operator. NO iteration cap on the plan review. Don't checkpoint/report/pause. On context-fill: update THIS file, auto-compact, continue. One codex at a time (§8.4). Route everything to Codex CLI (`env -u OPENAI_API_KEY codex exec`, visual via `-i`); NEVER the Opus advisor() tool.

**Anti-drift machinery (LIVE, verified 2026-05-24):**
- SessionStart hook `.claude/hooks/stier_session_start.py` → re-injects directive on startup/resume/compact.
- Stop hook `.claude/hooks/stier_stop_hook.py` → blocks premature stop while #872 OPEN; gates on objective GitHub state; escape valves = `state/stier_halt_*.md` / gh-failure / issue-closed / 60-block stuck-cap.
- Both wired in `.claude/settings.json` (single committed source).

## Boot ritual (mandatory per CLAUDE.md §10)

1. Read `CLAUDE.md` completely (project directives, especially §-1, §3.0, §10).
2. Read `polaris-controls/CHARTER.md` and `PLAN.md` (admin-only sister repo nested at `C:\POLARIS\polaris-controls\`).
3. Verify BOTH SHAs against `state/polaris_restart/charter_sha_pin.txt`. Either-file mismatch = HARD STOP per §3.1 step 0.
4. Read `state/active_issue.json`.
5. Read `docs/stier_experience_directive_2026_05_24.md` — the operator's S-tier directive.
6. Re-load CHARTER `I-ux-001` umbrella issue **#872** + sub-issues #873/#875/#877/#878/#879.

## Status as of this handover (2026-05-25)

| Sub-issue | GH# | State | What landed |
|---|---|---|---|
| I-ux-001 plan | umbrella #872 | APPROVED (Codex uncapped iter 4 v4, zero P0/P1) | `docs/stier_experience_plan.md` + `.codex/I-ux-001/PLAN_APPROVED.md` |
| I-ux-001a — Prereq 0: signed-bundle moat | #873 | OPERATOR MERGE QUEUE (codex-required PASS) | `web/lib/gpg_verify_bundle.ts`, tri-state SignatureBadge, gpgv-isolated keyring verifier, CI guard, Dockerfile gnupg install |
| I-ux-001a — Real demo signed bundle | #875 | OPERATOR MERGE QUEUE | `scripts/build_canonical_demo_bundle.py` signs by default; ships `polaris_demo_pubkey.asc` + `state/polaris_gpg_keyid.txt` |
| I-ux-001b — Figma hero prototype (Stage 2 + Stage 4) | #877 | OPERATOR MERGE QUEUE | 5 Codex visual-audit rounds B → B+ → A → A/A → A/A-+GREENLIGHT; v6 applied A+ unlock (unified Sealed evidence block + "matched 6 of 6 numbers" stamp + sentence-case ladder) |
| **I-ux-001d — Extend prototype: motion + all-pages BEFORE code** | **#879** | **IN PROGRESS — sequencing plan APPROVED Codex iter-3 (accept_remaining, 0 P0/P1); TRACK 1 hero-motion stills next** | 12 pages × 2 viewports = 24 frames; 8 motion scenes + per-scene reduced-motion variants; demo nav = 4 items (5 routes cut from primary nav, kept as deep-link); /transparency = dedicated HTML page (NEW route #12) + /.well-known/transparency.json for machines; per-frame v6 checklist (12 items incl. semantic-icon restraint + zero-jargon banlist) |
| I-ux-001c — Hero implementation | #878 | QUEUED AFTER #879 | Next.js + Tailwind v4 build of the prototyped hero |

## NEXT CONCRETE ACTION (resume from cold here)

**I-ux-001d TRACK 1 — hero motion stills.** Sequencing plan APPROVED Codex iter-3, `accept_remaining`. Begin Figma motion choreography on the existing v6 hero frames.

### Step-by-step from cold boot

1. Boot ritual (§3.1 step 0 canonical pin + CHARTER+PLAN SHA + halt-marker check).
2. `git checkout bot/I-ux-001d-extend-prototype-audit && git pull`.
3. **Files to ground in:**
   - `docs/web/i_ux_001d_motion_still_convention.md` — 8 scenes + per-scene reduced-motion; timestamp table
   - `docs/web/i_ux_001d_route_frame_map.md` — 12 pages × 2 viewports; per-frame v6 checklist; nav-cut + transparency split
   - `docs/web/proof_replay_storyboard.md` — 6-beat hero choreography spec
   - `web/p2shots/I-ux-001b/hero_stage{2,4}_v6_*.png` — the precedent stills (t=final_static; existing Figma frame `1:2` desktop + `14:2` mobile in file `Is7pehpxPdn3ZOOgCsyUjs`)
   - `.codex/I-ux-001d/sequencing_verdict_iter{1,2,3}.txt` — full direction history
4. **Figma execution** (use_figma):
   a. Open file `Is7pehpxPdn3ZOOgCsyUjs`, locate page "I-ux-001b hero v6" with frames `1:2` (desktop) and `14:2` (mobile).
   b. Duplicate to new page "I-ux-001d motion" — 8 scene-rows × {full-motion + reduced-motion variants} × {desktop + mobile}.
   c. For each scene, build the timestamp-keyed frames per `i_ux_001d_motion_still_convention.md` table. Use opacity + transform deltas only (Smart Animate is non-destructive on copy-on-write).
   d. Add 16px on-frame annotation overlay per the convention: `<scene> · t=<ms> · <state> · <viewport> · reduced-motion: <yes|no>`.
   e. Export each PNG to `web/p2shots/I-ux-001d/motion/<filename per convention>`.
5. **First sub-track (smoke test):** `hero_first_reveal` desktop full-motion only (6 frames: t=0, 120, 250, 400, 600, 700). Confirm the still sequence READS as motion to Codex before scaling to all 8 scenes.
6. **Codex hero-motion audit** via `codex exec -i <each motion still>` with brief `.codex/I-ux-001d/motion_audit_brief_iter1.md` (use the §0 cap directive verbatim). Audit asks: does the motion grammar match the 6-beat choreography spec? Does it honor reduced-motion (WCAG 2.2 2.3.3)? Does it ever obscure the two-judgment separation or source-span attribution?
7. On Codex APPROVE → TRACK 2 (family-template contact-sheet).
8. Track-by-track until all 5 tracks APPROVED, then sign-off.

### Operator standing directive (2026-05-24) — REMAINS BINDING

Anchored in `docs/stier_experience_directive_2026_05_24.md` + memory `feedback_codex_decides_all_stier_uncapped_2026_05_24.md` + the hook pair:

- **Codex decides EVERYTHING.** NEVER ask operator. NEVER use Opus advisor() tool.
- **NO ITERATION CAP** on the I-ux-001 plan review (per-Issue diff/brief gates keep §8.3.1 5-cap).
- **DON'T checkpoint / report status / pause / ask "should I continue."** Forbidden self-stops per §8.3.10.
- **§8.4 resource discipline:** ONE `codex exec` at a time; kill YOUR strays (codex/python/node); NEVER touch operator's other-project processes.
- **LAW II — Real Data Only, No Silent Fallbacks, Fail Loudly.**
- **`gh pr merge --admin` REVOKED.** Operator handles morning merge.
- **Brand red `#c8102e` LOCKED.**
- **Honest sovereignty wording only** (LLM via OpenRouter-US disclosed at /transparency footer integration).
- **Per-sentence provability + signed two-family bundle = core differentiator** — do not dilute.
- **Demo reviewer credential is a REAL SECRET** — use without echoing/committing.
- **When context nears full:** update `state/restart_instructions.md` (this file) → auto-compact → continue.

## Workflow rules (binding)

Per CLAUDE.md §3.0 + plan §7.A LOCKED A2 + §7.B LOCKED B1:

- **Claude:** writes code (briefs + diffs + claude_audit).
- **Codex:** reviews. Two APPROVE gates per Issue (brief + diff). 5-iter cap per §8.3.1 (NOT the umbrella plan — that's uncapped per I-ux-001 directive).
- **User:** spec owner + after-the-fact merge gate. Reads `git log` in morning. CI required check `polaris/codex-required` enforces.

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
