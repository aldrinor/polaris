# Codex sequencing consultation — I-ux-001d campaign plan

## §0 cap directive (verbatim from CLAUDE.md §8.3.1)

```
HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## Context

Operator (asleep, full auth) reviewed my "Plan ready?" answer and called out that the Codex review covered the PLAN (uncapped iter 4 APPROVE) + the HERO STATIC PROTOTYPE (5 visual rounds, A/A- + GREENLIGHT) but NOT motion ("lively") and NOT all pages ("e2e"). Directive verbatim:

> "extend the prototype audit to motion (Figma Smart Animate / interactive prototype) + all-pages hero frames before code"

Issue #879 opened with full scope. THIS document is iter 1 = sequencing consultation, NOT a build call.

## State of the world

**Approved + locked:**
- `docs/stier_experience_plan.md` v4 — Codex iter-4 APPROVE, zero P0/P1, `convergence_call: accept_remaining`. Plan §14 sequencing: Prereq 0 → foundation+hero prototype → component system → hero build → clinical layer → journey views → supporting surfaces → #871 parallel → PM script.
- Foundation: `docs/web/design_tokens_v2.md`, `docs/web/components_catalogue.md`, `docs/web/proof_replay_storyboard.md`, signed-bundle moat (PR #875), tri-valued SignatureBadge (PR #873).
- Hero static prototype: Figma file `Is7pehpxPdn3ZOOgCsyUjs` desktop frame `1:2` (1440×900 Stage 2 Proof Replay open) + mobile frame `14:2` (390×844 Stage 4 bottom-sheet), v6 with unified Sealed evidence block + matched-numbers stamp. Codex iter-5 GREENLIGHT.

**Live incumbents** (P2-seq-13..23 deployed to polarisresearch.ca, but graded B/C+/B+/C/D+/D/B- per memory `feedback_codex_has_vision_use_image_flag_2026_05_23`):
- All 11 listed pages exist as Next.js routes today and render at polarisresearch.ca (HTTP 200)
- They predate the I-ux-001 plan; the I-ux-001c (#878) implementation will rebuild them per the new system
- The prototype-audit work in #879 is GREENFIELD — operator's "before code" framing means we design the new versions in Figma before writing the new code

**What's NOT done:**
- Motion choreography in Figma (6-beat reveal, claim-switch, hover/focus/active, mobile sheet, reduced-motion)
- 11 page hero frames × 2 viewports = 22 new frames
- E2E click-through prototype
- Codex's per-page audit at the same A+ bar the hero hit

## The decisions Codex owns

### D1 — Sequencing order

Option A (motion-first): finish the hero by adding motion to the Stage 2 + Stage 4 frames, lock the motion language, THEN apply it to all 11 pages.
Pro: motion conventions established once, applied consistently. Con: pages-without-motion can't be audited until late.

Option B (all-pages-first): build 22 static page frames first to lock visual system across the surface, THEN add motion to a representative subset.
Pro: parallelizable; per-page audit can fire in parallel. Con: motion language emerges late; some pages may need redesign once motion is added.

Option C (interleaved-by-family): build a family template (read-mode / edit-mode / monitor-mode / spatial / marketing), specialize, and add motion within each family.
Pro: thorough per-family. Con: 5 families × 5-iter-cap = 25 worst-case audits.

Option D (hero-extend-only-first): finish hero motion to A+, then build all-pages as STATIC only, defer motion on supporting pages to I-ux-001c implementation phase (`codex exec -i` on live render).
Pro: keeps #879 finite; respects plan §14 model where per-page motion gate happens at code time.
Con: doesn't fully satisfy operator's "lively + e2e before code" framing if they meant motion-everywhere.

### D2 — Per-family shared template strategy

Proposed families:
- **Read-mode** (Inspector/Report DONE, Compare, Audit, Source Review) — share evidence block + provenance + signed-bundle pill pattern
- **Edit-mode** (Intake, Plan review) — share form + decision-tree + just-ask input pattern
- **Monitor-mode** (Dashboard, Run progress, Transparency) — share status + system-state + progress pattern
- **Spatial** (Knowledge graph) — unique
- **Marketing** (Home, Sign-in) — unique

Should we build per-family templates and then specialize? Or design every page individually?

### D3 — Codex audit cadence

- Per-page: 12 audits × ≤5 iter each = up to 60 codex exec calls
- Per-family: 4 audits × ≤5 iter each = up to 20 calls
- Single mega-audit on a contact-sheet of all 22 frames: 1 audit × ≤5 iter = 5 calls

Cost vs rigor tradeoff. Per the line-by-line standard (§-1.1), per-page is the rigorous answer. Per-family + sample-spotcheck is the pragmatic answer. Codex's call.

### D4 — Motion conveyance to Codex

Codex `-i` accepts static images. Three options for motion:
- **Interactive prototype URL** — Codex can't play it back; need a separate vehicle
- **Smart Animate exported MP4/GIF** — Codex `-i` likely sees first frame only; not viable for time-axis review
- **Annotated still sequence** — capture key frames at t=0/120/200/320ms with labels; Codex reads timing from annotations and gestures rather than seeing motion. Pragmatic and rigorous if frames are well-chosen.

Recommendation: annotated still sequence. Codex confirms or proposes alternative.

### D5 — Acceptance bar

- Option α: A+ on every page (strictest; matches operator's "frontier-BEATING S-tier" framing)
- Option β: A+ on the demo critical-path (Home → Intake → Plan review → Run progress → Report → Compare → Knowledge graph); A on supporting pages (Audit, Sign-in, Dashboard, Source Review, Transparency)
- Option γ: Codex decides per page during the audit

### D6 — Live incumbent treatment

The P2-seq-13..23 pages exist + rendered. Two options:
- **Greenfield**: ignore the existing code; design from the plan principles only
- **Incumbent-informed**: Codex reviews the live render via `codex exec -i` first, lists what's salvageable vs what to rebuild, then prototype only the rebuilt parts

Plan §14 implies greenfield (the implementation step rebuilds everything per the new spec). But if the live pages have any A+ elements, salvaging beats rebuilding from zero.

## What I'm asking Codex for, in this iter 1

For each of D1-D6, return a recommendation grounded in:
- Latest best practice (cross-check with frontier products: Linear, Stripe, Vercel, Perplexity Spaces/Comet, Elicit, Consensus, Scite, OpenEvidence, FutureHouse, ChatGPT DR, Gemini DR)
- The clinical-safety / signed-bundle moat from the plan
- The 18-week Carney delivery budget (demo target 2026-06-05 to 2026-06-09 per state/active_issue.json — i.e., ~12 days from today)
- The §-1.1 line-by-line rigor standard
- The hero v6 prototype precedent (5-round visual iteration, A+ bar)

## Output schema (per CLAUDE.md §8.3.9)

```yaml
verdict: APPROVE | REQUEST_CHANGES   # APPROVE = sequencing plan accepted as-is; REQUEST_CHANGES = revise
d1_sequencing_order: A | B | C | D | other-with-rationale
d2_family_strategy: per_family | per_page | hybrid-spec
d3_audit_cadence: per_page | per_family | mega | hybrid-spec
d4_motion_conveyance: annotated_still_sequence | interactive_prototype_url | mp4_gif | hybrid-spec
d5_acceptance_bar: alpha_all_aplus | beta_aplus_critical_a_supporting | gamma_codex_per_page
d6_incumbent_treatment: greenfield | incumbent_informed
rationale_summary: [one paragraph per D1-D6 explaining the call grounded in best practice + clinical-safety + budget]
risks: [...]
remaining_blockers_for_execution: [...]
convergence_call: continue | accept_remaining
```

## Files Codex should consult before answering

- `docs/stier_experience_plan.md` (v4, APPROVE'd)
- `docs/web/design_tokens_v2.md`
- `docs/web/components_catalogue.md`
- `docs/web/proof_replay_storyboard.md`
- `web/p2shots/I-ux-001b/hero_stage2_v6_desktop.png` + `hero_stage4_v6_mobile.png` (the precedent)
- `.codex/I-ux-001b/visual_audit_v5.txt` (the precedent verdict)
- `web/app/**/page.tsx` (live incumbents)
- `state/active_issue.json` (budget context)

## Files I have ALSO checked and they're clean

- `state/restart_instructions.md` (current handover)
- `state/fallback_drill_etc/static_accounts.yaml` (no plaintext cred for prod; local-only)
- The plan §14 sequence and acceptance criteria
