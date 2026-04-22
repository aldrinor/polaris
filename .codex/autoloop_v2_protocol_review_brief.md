You are being asked for your OPINION on the proposed POLARIS
Autoloop V2 protocol. This is a META review — not a code audit.
The user has directed this new autoloop and wants your independent
assessment before we run under it autonomously (potentially 24h+
without user oversight).

## Your role in V2

You (Codex) have three distinct responsibilities under V2:

1. **Step 2b — Output audit**: read V{N}'s report.md, bibliography,
   manifest, verification_details line-by-line vs the two
   competitor PDFs (`state/compare_chatgpt_dr.txt`,
   `state/compare_gemini_dr.txt`) + industrial standards. Produce
   7-dimension BEAT_BOTH / BEAT_ONE / LOSE_BOTH verdict. (Same as
   your prior DR output audits.)

2. **Step 3b — Cross-review of Claude's audit**: read Claude's
   parallel audit (`claude_audit.md`), adjudicate agreements,
   surface disagreements with concrete citations.

3. **Step 6 — Fix-plan review (NEW)**: Claude writes a fix plan
   describing the root cause + fix approach for each failed
   dimension. YOU evaluate whether each item is a root-cause fix
   or a band-aid. If any item is a band-aid, plan is red-lighted
   and Claude revises. This is the autoloop's key guardrail — it
   prevents wasted sweep cycles on superficial fixes.

## The full protocol

Read: `state/autoloop_v2_runbook.md` for the complete runbook.

In short:

```
V{N} sweep
  → parallel Claude output audit + Codex output audit
  → cross-review (mutual adjudication)
  → gate: both green = ship / either red = continue
  → Claude writes fix plan (root cause for each gap)
  → Codex reviews plan: band-aid vs root-cause
  → green → Claude implements + Codex code audit
  → V{N+1} launched → loop
```

Fully autonomous — Claude self-paces via ScheduleWakeup, no user
intervention between sweeps.

## Files to read

```
state/autoloop_v2_runbook.md
memory/autoloop_v2_audit_cross_review.md      (via user's global memory)
C:\Users\msn\.claude\projects\C--POLARIS\memory\autoloop_v2_audit_cross_review.md
outputs/codex_findings/dr_output_pass_11/findings.md   (V1 output audit example — V23)
outputs/codex_findings/dr_output_pass_12/findings.md   (V1 output audit example — V24, REGRESSED)
outputs/codex_findings/m41_code_audit/findings.md      (V1 code audit example — pass-1 BLOCKED)
```

## Questions I'm asking you

1. **Is the V2 protocol sound?** Does it close the V1 gap where
   V24's regulatory regression was caught only by your DR pass 12
   (not earlier) — because only Codex was auditing output, not
   Claude?

2. **Is parallel Claude+Codex auditing additive or redundant?**
   Concerns about compute cost / Claude's self-audit blind spots
   vs Codex's? Any specific dimensions where one or the other is
   systematically weaker?

3. **Cross-review mechanics**: the runbook has Claude reading
   codex_audit.md and vice versa. Is this mutual-adjudication
   useful, or is it theater? What would make it real — specific
   disagreement-handling rules?

4. **Band-aid vs root-cause judgement** (step 6, your new
   responsibility): do you have concerns about being the sole
   arbiter of "this is a band-aid"? What criteria should you
   apply? Examples from V1 history:
   - M-40 (Mechanism section) — closed Narrative depth but CAUSED
     the Regulatory regression. Was it a root-cause fix for
     Narrative (yes), but should the plan have anticipated the
     displacement? (Arguably yes — M-40 pass-1 was under V1, no
     plan-gate existed.)
   - M-41b (drop trial table rows with >2 dashes) — is this
     band-aid or root-cause? My read: it's a surface fix for a
     symptom; the real root cause is that M-36's table
     generation prompt doesn't require LLM to omit rows when data
     is thin. Under V2, a stricter prompt gate on M-36 (or a
     generation-time row-quality check) would be root-cause;
     post-hoc drop is band-aid. Do you agree?

5. **Autonomous operation safety**: Claude will run this loop
   24h+ without user oversight. What halt conditions should be
   hardcoded? Currently the runbook has:
   - Plan-review ping-pong >3 cycles → halt + PushNotification
   - Quality regression vs prior V{N-1} → halt
   - Codex and Claude can't reconcile a cross-review disagreement
     → halt
   Are these sufficient? Any missing?

6. **Budget / compute boundaries**: each V sweep is ~90-200 min
   + 2 LLM audits + code audits. A non-converging loop could
   burn a lot of OpenRouter credits and Codex time. Should the
   runbook cap total cost or cycle count?

7. **Your own blind spots**: under V1 you caught M-40's under-
   firing only in pass-2 after a smoke test found a KeyError. Are
   there categories of bug Claude-audit would catch that Codex-
   audit would miss? Should step 3 (cross-review) specifically
   look for those?

## Deliverable

Write `outputs/codex_findings/autoloop_v2_protocol_review/opinion.md`
with:
- Overall verdict: APPROVED / APPROVED WITH CAVEATS / REJECT
- Answers to the 7 questions above
- Specific proposed changes to the runbook (if any)
- Your commitment on the 3 V2 responsibilities (can you deliver
  them at the quality the loop requires?)

Keep it under 2500 words.
