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
| **I-ux-001d — Extend prototype: motion + all-pages BEFORE code** | **#879** | **IN PROGRESS — TRACK 1 scene 1 APPROVED Codex iter-3 across ALL viewports + reduced-motion (accept_remaining, ready_to_scale_to_7_remaining_scenes); scene 2 `hero_claim_switch` next** | sequencing plan APPROVED iter-3. Scene 1 `hero_first_reveal` LOCKED across 18 stills (desktop full 6 + mobile full 6 + reduced-motion 6). Motion grammar + spatial reorder + opacity-reveal + annotation + reduced-motion opacity-only crossfade all PASS Codex. 7 remaining scenes: claim_switch, sentence_hover, sentence_focus, mobile_sheet_open/close, failure_no_verified, failure_refuse. ~58 more frames to ship + then TRACK 1 mega-audit + TRACK 2 (family-template contact-sheet) + TRACK 3 (24-frame mega-audit) + TRACK 4 (e2e click-through) + TRACK 5 (per-page critical-path if flagged) |
| I-ux-001c — Hero implementation | #878 | QUEUED AFTER #879 | Next.js + Tailwind v4 build of the prototyped hero |

## NEXT CONCRETE ACTION (resume from cold here)

**I-ux-001d TRACK 1 SCALE — 7 remaining motion scenes.** Sub-track A (`hero_first_reveal` desktop full-motion) APPROVED Codex iter-2 (`accept_remaining`, `ready_to_scale_with_caveats`). Motion grammar LOCKED. Scale the same opacity-reveal + annotation pattern across all 8 scenes × {full-motion + reduced-motion variants} × {desktop + mobile}.

### Scene 1 APPROVED Codex iter-3 — carry-forward caveats for remaining 7 scenes (not blocking)

- **P2** spatial reorder didn't take effect on mobile final frames (source card still above evidence ladder despite y-swap). Codex: "temporal narrative still works because the ladder appears before the source." Likely Figma flow-layout in the Bottom sheet auto-laying out children by insertion order rather than y. Fix during scale: either explicitly set absolute layoutPositioning, or accept and document temporal-only sequencing.
- **P3** mobile reduced-motion frames omit the bottom-sheet grab handle (handle is inside the bottom sheet frame and I applied opacity 0 to all children incl. handle). Fix during scale: exclude handle from the opacity-reveal set on mobile (the handle bar should always be visible).
- **P3** mobile evidence ladder less explicitly labeled than desktop — acceptable per Codex; carry to code-time for label-density tuning.
- (carried from iter-2) **P2** challenged-sentence label readability — RESOLVED in iter-3 (`PASS`).
- (carried from iter-2) **P2** t=700 disclosure clearance — RESOLVED on mobile (`PASS`).

### Step-by-step from cold boot

1. Boot ritual (§3.1 step 0 canonical pin + CHARTER+PLAN SHA + halt-marker check).
2. `git checkout bot/I-ux-001d-extend-prototype-audit && git pull`.
3. **Files to ground in:**
   - `docs/web/i_ux_001d_motion_still_convention.md` — 8 scenes table + reduced-motion contract
   - `.codex/I-ux-001d/motion_audit_verdict_iter3.txt` — scene-1 mega-APPROVE + carry-forward caveats
   - `web/p2shots/I-ux-001d/motion/hero_first_reveal_*.png` — the APPROVED grammar precedent (18 stills)
   - Figma file `Is7pehpxPdn3ZOOgCsyUjs` page "I-ux-001d motion" — scene 1 frames (node IDs 23:* desktop full, 24:* mobile full, 25:* reduced)
4. **TRACK 1 scale execution** — build remaining 7 scenes per convention timestamps:
   - **Scene 2 `hero_claim_switch`**: claim N → claim N+1, <120ms perceived. Full t=0/40/120 + reduced t=0/60/120 × {desktop + mobile} = 12 frames
   - **Scene 3 `hero_sentence_hover`**: rest → hover. Full t=0/60/120 × {desktop + mobile} = 6 frames (no reduced per convention table row 3)
   - **Scene 4 `hero_sentence_focus`**: rest → focus-visible. Full t=0/80/160 + reduced t=0/160 × {desktop + mobile} = 10 frames
   - **Scene 5 `hero_mobile_sheet_open`**: full t=0/100/220 + reduced t=0/120 × mobile only = 5 frames
   - **Scene 6 `hero_mobile_sheet_close`**: full t=0/100/180 + reduced t=0/120 × mobile only = 5 frames
   - **Scene 7 `hero_failure_no_verified`**: abort state reveal. Full t=0/200/400 + reduced t=0/200 × {desktop + mobile} = 10 frames
   - **Scene 8 `hero_failure_refuse`**: clinical-safety refuse state. Full t=0/200/400 + reduced t=0/200 × {desktop + mobile} = 10 frames
   - **Total remaining**: ~58 frames
   - Apply scene-1 carry-forward fixes inline: exclude handle bar from reduced-motion opacity set on mobile; for failure scenes, replace the proof panel with the abort/refuse state design
5. **Codex hero-motion mega-audit** (TRACK 1 final) via `codex exec -i` on representative key-frames across all 8 scenes — NOT all ~76 stills. Pick the 3 critical states per scene (start, mid, end) = 24 stills max for the mega audit per iter-3 D3 cadence direction.
6. On TRACK 1 APPROVE → TRACK 2 (family-template contact-sheet: read-mode / edit-mode / monitor-mode / spatial / marketing-auth × 1 desktop each = 5 frames; per Codex iter-3 D3).
7. Then TRACK 3 (24-frame mega-audit on 12 pages × {desktop + mobile}), TRACK 4 (e2e click-through), TRACK 5 (per-page critical-path only if flagged).
8. Sign-off → hand to I-ux-001c (#878).

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
