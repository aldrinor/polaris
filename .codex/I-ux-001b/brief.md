# Codex review brief — I-ux-001b foundation: design tokens v2 + components catalogue + proof-replay storyboard

## 0. ITERATION DIRECTIVE (CLAUDE.md §8.3.1)
HARD ITERATION CAP: 5 per document. Front-load all findings. "Don't pick bone from egg" — P0/P1 reserved for real risks. Same quality bar regardless of iter. Verdict APPROVE iff zero NOVEL P0 + zero continuing P0 + zero P1.

## 1. Pre-flight
- **Context:** GH#876 (sub-task of #872 / I-ux-001). Branch `bot/I-ux-001b-foundation` off `bot/I-ux-001a-prereq-0-signed-bundle`. Step §14.1 of the Codex-APPROVED `docs/stier_experience_plan.md` (`.codex/I-ux-001/PLAN_APPROVED.md`). Spec-only (no code in this PR); subsequent per-page Issues consume these.
- **Done-when:** the spec is concrete enough that any subsequent UI Issue can implement against it without re-deciding craft/motion/color/state details, AND the two-judgment separation (faithfulness vs evidence-strength) is visually-orthogonal-at-every-beat.

## 2. Reviewer Independence Protocol
> Verify by reading the actual docs (not the commit-message claims). A claim in the doc that's wrong/vague is a finding.

## 3. What to review (read all three files in full)
1. `docs/web/design_tokens_v2.md` — type / two-judgment color / motion / six microstates / brand red / maple-leaf / trust copy.
2. `docs/web/components_catalogue.md` — 9 components × six microstates × concrete CSS contract. Shared interactive baseline (§0) covers all selectors.
3. `docs/web/proof_replay_storyboard.md` — Stage 0 resting → Stage 7 Home teaser → Stage 8 acceptance tests. Frame-level motion for the 6-beat hero reveal.

## 4. Hard constraints (operator-LOCKED — not consultable)
- Brand red `#c8102e` LOCKED.
- Honest sovereignty (LLM via OpenRouter-US disclosed; "Canadian-hosted" = hosting/data).
- Per-sentence faithfulness + signed two-family bundle is the CORE differentiator.
- Two judgments (faithfulness vs evidence-strength) MUST stay visually orthogonal — conflating them is the lethal clinical confusion (plan §0).
- Next.js 16 / Tailwind v4 / Geist.
- Spec only here; no code review.

## 5. Acceptance criteria (forced enumeration — one line each in verdict)

1. **Tokens v2 type scale:** sufficient for the Linear/Stripe craft bar?
2. **Two-judgment color separation:** faithfulness palette (green/amber/red) vs evidence-strength palette (slate-blue ordinal) — actually orthogonal? Brand red `#c8102e` not colliding with `--unsupported`? WCAG-AA contrast per surface as claimed?
3. **Motion tokens** (3 durations, 1 easing): sufficient + Vercel-aligned (motion = state communication, never decoration)? `prefers-reduced-motion` covered everywhere?
4. **Six microstates** covered for every interactive element with concrete CSS contracts in `components_catalogue.md` §0?
5. **Maple-leaf production spec:** crisp SVG (replaces "low-fidelity dot-cloud"), placement rules clear?
6. **Trust copy table:** de-jargon complete (no "two-family invariant", "POOL ID", "Signature missing")? Single source of truth (`web/lib/trust_copy.ts`) the right shape?
7. **Storyboard Stage 0 resting:** the two affordances (faithfulness underline + leading-margin certainty dot) genuinely orthogonal and never adjacent?
8. **Storyboard Stage 2 6-beat reveal:** sequencing + timing realistic? Each beat justified ("what changed, why does this animation make it clearer")? Time-to-first-proof < 400ms?
9. **Storyboard Stage 4 mobile (bottom-sheet):** real, not hover-dependent?
10. **Storyboard Stage 5 reduced-motion:** equivalent preserves the sequencing INTENT as visual hierarchy?
11. **Storyboard Stage 6 failure-state choreography:** missing/present_unverified signature, UNSUPPORTED claim, inadequacy refusal — all *honest* per LAW II?
12. **Stage 7 Home teaser:** the inline 6-beat playing on a real claim from the real signed bundle is the right "first 30 seconds" hook?
13. **What's MISSING** to enable per-page implementation Issues.

> **Forced enumeration:** before declaring a verdict, write `Criterion N [name]: <findings or NONE>` for each.

## 6. Skepticism / completeness check
> List the files you actually READ this round. If you cannot confirm full scan of every criterion, emit `incomplete_review`.

## 7. Output schema
```
## Per-criterion forced enumeration
- Criterion 1 [type scale]: <findings or NONE>.
- ... (1-13)
## Findings { P0 / P1 / P2 / P3 }
## Verdict
verdict: APPROVE | REQUEST_CHANGES | incomplete_review
Convergence: APPROVE iff zero P0 + zero P1.
```
