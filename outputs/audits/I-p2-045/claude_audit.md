# Claude architect audit — I-p2-045 (#837): Intake page S-rebuild

## Goal
Move /intake ("Ask") from a B- (a small Check-scope card floating in an empty page) to A++/S
— input-as-hero + an intentional, filled surface.

## What changed (3 files, +55/-4)
- `web/app/intake/page.tsx`: "CLINICAL SCOPE DISCOVERY" uppercase eyebrow above the H1; a
  factual 3-step "how it works" sibling band (Ask → Scope-checked first → Get a verified
  brief) filling the formerly-empty lower half.
- `web/app/intake/components/intake_form.tsx`: question Input enlarged (h-12 text-base) as the
  hero; sample chips tokenized hover. Logic + testids unchanged; form Card keeps shadow-card.
- `docs/web/s_tier_design_system.md`: Intake grade.

## Stale-test resolution (NOT a relaxation)
`intake.spec.ts:21` asserts visible `/Clinical scope discovery/i`, but the #613 rebuild had
changed the heading to "Ask a clinical research question" — so the assertion was failing
silently behind the non-functional e2e lane (#720). Verified the string existed NOWHERE in the
current code and the live prod page lacked it. Resolved per Codex's recommendation by RESTORING
it as a crafted uppercase eyebrow — honest (the scope-check IS clinical scope discovery) + a
premium pattern. The test now passes against the real page; the test was not edited/relaxed.

## Honest copy (LAW II)
The 3-step band describes only the real ask → scope-check → span-verified-brief flow. No
fabricated metrics; no banned dev-language; the scope-check backend behavior is unchanged.

## e2e
intake_g1_g8 4/4 pass (1 header/1 main, no banned dev-language, no console errors, nav parity);
intake.spec "renders title/form/suggestions" passes (eyebrow). Scope-SUBMIT specs require the
v6 backend (not up in dev) — environmental, unchanged behavior.

## Dual Codex gate
- Brief APPROVE (iter 2; iter-1 caught the stale eyebrow assertion).
- Visual `-i` APPROVE (iter 1: desktop A- / mobile A-).
- Code diff APPROVE (iter 1, zero findings) — `.codex/I-p2-045/codex_diff_audit.txt`.

## Constraints honored
Brand `#c8102e` untouched; tokens only; honest wording; logic/testids preserved; no test
relaxation; no fabricated proof.

canonical-diff-sha256: cdc6285009f8b3318060ac8c5cfc603243a6becbb6d2cf671ed4b7d8d3908718
