HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
(This is a SCOPE-DECISION consult, NOT a brief review. One-shot answer expected.)

# Codex scope consult — I-cd-016 / GH#626

## Context

Brief iter 1 returned REQUEST_CHANGES with 4 P1 (auth + GPG + success-only + close-#626 framing).

The acceptance criterion is "real question → verified report end-to-end on OpenRouter." Codex iter-1 explicitly framed: "harness-only OR ship the artifact (real verified_report.json + bundle + run log)."

Backend infrastructure already exists (Dramatiq actors + Redis Streams SSE + pipeline-A wiring + bundle export per I-arch-001a..f). The hermetic capstone e2e PASSES on HEAD. What's missing is the live-OpenRouter run + auth/GPG plumbing for the smoke harness.

Session-quality signals: this is ~PR-8 of the session; 7 PRs already shipped; some quality slips noted (CI prettier blip on I-cd-013a; iter-count creeping on I-cd-014).

## The 3 paths (route this to Codex per operator directive 2026-05-20)

**Path A — Split: ship I-cd-016a (harness only) tonight + defer I-cd-016b (real OpenRouter run) to a new GitHub Issue.**
- Tonight's PR: ~400 LOC harness (smoke script + auth + GPG preflight + docs + lock assertions).
- New I-cd-016b issue: operator-supervised real run; produces actual verified_report.json + bundle + run log; closes #626.
- Matches I-cd-013a/b split pattern.
- Honest framing: PR description says "does not close #626; harness only; close-#626 is I-cd-016b."

**Path B — Push through: full harness + real OpenRouter run + close-#626 tonight.**
- Implement all 4 P1: auth flow + GPG preflight + success-only smoke + real OpenRouter invocation against live OVH deploy.
- Estimated $5-20 OpenRouter spend + 2-4 more hours.
- Risk: OVH deploy may need redeploy at HEAD (last redeploy at I-cd-002, several issues ago); session-quality at ~7-PR mark; real-money side-effect on first-attempt.
- Closes #626 with real artifacts attached.

**Path C — Pause: save brief substrate; resume next session with fresh head.**
- Branch + brief preserved.
- Next session re-enters at iter 2 brief with the 4 P1 folded.
- ~3 hours of substrate work preserved; ~3 hours of remaining work deferred.
- Operator gets a clean morning git log.

## Quality-impact rubric

Per `feedback_route_decisions_to_codex_quality_impact_2026_05_20.md`, rank by:
1. Correctness/security risk per path (auth/GPG getting wrong is real risk).
2. PR-cap discipline (200-LOC halt-condition + iter-5 convergence).
3. Downstream-issue dependency chain (I-cd-016 → I-cd-017..021 depend on it).
4. Operator-supervised-action gating (real OpenRouter money + GPG key handling).
5. Session-quality signals (~7 PRs in).

## Decision request

Which path (A, B, or C) has the **highest quality impact** for the Carney delivery? Return:

```yaml
recommendation: A | B | C
rationale: <2-3 sentences, ranking by the quality-impact rubric>
caveats: [<list of caveats Claude must honor>]
```
