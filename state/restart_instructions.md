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
| **I-ux-001d — Extend prototype: motion + all-pages BEFORE code** | **#879** | **IN PROGRESS — TRACK 1 sub-track A APPROVED Codex iter-2 (accept_remaining, ready_to_scale_with_caveats); TRACK 1 scale-up to 7 remaining scenes next** | sequencing plan APPROVED iter-3; sub-track A `hero_first_reveal` desktop 6 frames APPROVED iter-2 — motion grammar LOCKED. 12 pages × 2 viewports = 24 frames target; 8 motion scenes + per-scene reduced-motion; demo nav = 4 items (5 routes cut); /transparency = dedicated HTML page (NEW route #12); per-frame v6 checklist (12 items) |
| I-ux-001c — Hero implementation | #878 | QUEUED AFTER #879 | Next.js + Tailwind v4 build of the prototyped hero |

## NEXT CONCRETE ACTION (resume from cold here)

**I-ux-001d TRACK 1 SCALE — 7 remaining motion scenes.** Sub-track A (`hero_first_reveal` desktop full-motion) APPROVED Codex iter-2 (`accept_remaining`, `ready_to_scale_with_caveats`). Motion grammar LOCKED. Scale the same opacity-reveal + annotation pattern across all 8 scenes × {full-motion + reduced-motion variants} × {desktop + mobile}.

### Sub-track A APPROVED iter-2 — caveats to address during scale-up (not blocking)

- **P2** challenged-sentence label needs tightening (contrast/size/position) — currently slate-on-cream 10px Inter Medium with 4% tracking; bump to 11px + higher-contrast slate or add a 2px green accent dot
- **P2** t=400 has visible empty source-card slot above Evidence strength — the spatial-temporal reorder is "partially successful"; need to either collapse layout when source hidden OR use absolute-positioned reveals
- **P2** t=700 Limits disclosure sits close to the 24px bottom annotation bar — add 16-24px clearance before mobile/full rollout
- **P3** Evidence ladder labels small/low-contrast (carried forward from iter-1 P3)
- **P3** t=0 claim text still slightly more active than surrounding muted copy — minor

### Step-by-step from cold boot

1. Boot ritual (§3.1 step 0 canonical pin + CHARTER+PLAN SHA + halt-marker check).
2. `git checkout bot/I-ux-001d-extend-prototype-audit && git pull`.
3. **Files to ground in:**
   - `docs/web/i_ux_001d_motion_still_convention.md` — 8 scenes table + reduced-motion contract
   - `.codex/I-ux-001d/motion_audit_verdict_iter2.txt` — sub-track A APPROVE + caveats list
   - `web/p2shots/I-ux-001d/motion/hero_first_reveal_*.png` — the APPROVED grammar precedent (6 desktop full-motion frames)
   - Figma file `Is7pehpxPdn3ZOOgCsyUjs` page "I-ux-001d motion" — existing 6 frames (node IDs 23:2 ... 23:492)
4. **TRACK 1 scale execution** (use_figma, apply the iter-2 caveat fixes during scaling):
   a. **Mobile full-motion** for `hero_first_reveal` (6 frames at t=0/120/250/400/600/700 × 390×844). Source = `14:2` mobile hero. Same opacity-reveal pattern, mobile bottom-sheet layout per Stage 4 of storyboard.
   b. **Reduced-motion variants** for `hero_first_reveal` (desktop + mobile) at t=0/120/200 only (opacity-only crossfade per convention table row 1).
   c. **Remaining 7 scenes** (`hero_claim_switch`, `hero_sentence_hover`, `hero_sentence_focus`, `hero_mobile_sheet_open`, `hero_mobile_sheet_close`, `hero_failure_no_verified`, `hero_failure_refuse`) at their convention-table timestamps × {full + reduced where applicable} × {desktop + mobile where applicable}.
   d. Apply the iter-2 caveat fixes inline: tighten challenged-sentence label, collapse layout to avoid t=400 hole pattern in any future "intermediate reveal" frames, add bottom-disclosure clearance.
5. **Codex hero-motion mega-audit** via `codex exec -i` on the FULL scene-grid (one audit covering all scenes, NOT per-scene — per iter-3 D3 cadence lock). Brief: `.codex/I-ux-001d/motion_audit_brief_track1_scale.md`. Verdict: APPROVE iff motion grammar holds across all scenes + reduced-motion variants are coherent.
6. On TRACK 1 APPROVE → TRACK 2 (family-template contact-sheet: read-mode / edit-mode / monitor-mode / spatial / marketing-auth × 1 desktop each = 5 frames; per Codex iter-3 D3).
7. Then TRACK 3 (24-frame mega-audit), TRACK 4 (e2e click-through), TRACK 5 (per-page critical-path if flagged).
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
