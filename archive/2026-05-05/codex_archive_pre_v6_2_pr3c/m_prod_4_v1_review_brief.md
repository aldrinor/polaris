# Codex round 1 — M-PROD-4 v1 (release notes + supported-scope page)

## Pre-flight
- Branch: `polaris`
- Commit: `42b7fcb`
- Brief format: lean autoloop V3

## Scope
Phase H final milestone per FINAL_PLAN. Pure docs work:
- `docs/release_notes_v1.0.md` (~110 lines)
- `docs/supported_scope.md` (~140 lines)

## Tool hints
- Read: `docs/release_notes_v1.0.md` full file
- Read: `docs/supported_scope.md` full file
- Cross-reference: `docs/full_online_plan_FINAL.md` (canonical
  source for milestone status); `docs/pricing_and_positioning.md`
- Verify each "LOCKED" claim in release notes against actual
  commits on the polaris branch

## Acceptance bar
1. **Factual correctness.** Every "LOCKED via Codex R-N" claim
   in release notes maps to a real commit + Codex APPROVE
   verdict in `.codex/m_*_v*_verdict_brief.md`.
2. **Substrate count = 13** (M-INT-0a + 0b + 1..11), not 12.
3. **Out-of-scope list completeness.** Each refusal class
   in `supported_scope.md` is enforced by an actual substrate
   (M-INT-4 LLM scope or M-INT-5 domain router).
4. **Migration guide correctness.** Each command in the
   "Migration guide" section runs cleanly in the current repo.
5. **Compliance posture accuracy.** SOC2/HIPAA/EU AI Act/GDPR
   claims map to real artifacts.

## Severity rubric
- **P0** — false claim that misrepresents shippable state (e.g.,
  claims a milestone is LOCKED when it isn't)
- **P1** — phase-rework: factual error in scope/migration
- **P2** — governance precision (non-blocking)
- **P3** — polish: prose, formatting

**APPROVE iff zero P0 + zero P1.**

## Reviewer instructions
- Spot-check 3-5 "LOCKED" claims by reading the corresponding
  `.codex/*_verdict_brief.md` files.
- Run the migration guide commands; flag any that error.
- Verify substrate count: `M-INT-0a` + `M-INT-0b` + `M-INT-1`
  through `M-INT-11` = 13 substrates.

## Skepticism gate
List which milestones you spot-checked + which migration
commands you ran.

## Anti-nits (do NOT flag)
- Prose grammar / formatting
- Stylistic preferences on tone
- Suggestions for additional docs

## Verdict format
```
## Files scanned
## Acceptance bar verification
## Findings
### P0 (blocking)
### P1 (blocking)
### deferred_polish (P2/P3, non-blocking)
## Verdict APPROVE | REQUEST_CHANGES
```

## Round metadata
Round 1 of 5 hard cap.
