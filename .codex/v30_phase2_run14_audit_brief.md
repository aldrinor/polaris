V30 Phase-2 run-14 deep content audit — xhigh reasoning.

**Skip git status.** Codex at gpt-5.4 + xhigh.

## Target

`outputs/full_scale_v30_phase2_run14/clinical/clinical_tirzepatide_t2dm/report.md`
(2,599 words, status=success, release_allowed=True, qwen=1G+3A+1NR).

V33 (M-72) cross-trial synthesis layer was the 5th architectural
cycle aimed at the persistent Narrative depth + Citations LB
ceiling. M-72 telemetry confirms it fired:
  21:40:27 [multi_section] M-72 injected 1 cross-trial synthesis
    patterns into section 'Safety'
  21:40:28 [multi_section] M-72 injected 1 cross-trial synthesis
    patterns into section 'Comparative'
  + retry passes (M-44 path)

## Run history

| Run | release | qwen | tally | wc |
|-----|---------|------|-------|-----|
|  9 | False | 1G+1A+3NR | 1+4+2 CHECKPOINT | 2,812 |
| 10 | True | 3G+1A+1NR | 1+4+2 ITERATE | 3,023 |
| 11 | True | 2G+2A+1NR | 1+4+2 ITERATE | 3,112 |
| 12 | False | 1G+2A+2NR | 1+4+2 ITERATE | 3,338 |
| 14 | True | 1G+3A+1NR | TBD | 2,599 |

## Observation

Run-14 word count REGRESSED to 2,599 (vs 3,338 run-12, 3,112
run-11). Yet release_allowed=True and qwen has 1G+3A+1NR. What
the body actually shows:

  - Safety: 3 sentences (run-12 had 5)
  - Comparative: 3 sentences (run-12 had 8)
  - Population Subgroups: 6 sentences (run-12 had 7)
  - Body of Efficacy slots much the same as run-11/12

So the M-72 prompt block may have CONSTRAINED rather than
enriched the LLM by replacing free-form synthesis with the
prescribed cross-trial inferences. The LLM took the M-72
suggestions as an upper bound rather than a floor.

## Audit ask

Apply 7-dim framework. Score deltas vs run-12. Specifically:

1. **Citations** — does run-14 still beat Gemini on T1
   hierarchy and lose to ChatGPT on density?
2. **Regulatory** — same architecture as run-12 (no V33 change);
   should be flat at LB.
3. **Jurisdiction** — same.
4. **Claim-frames** — flat; M-72 doesn't add claim frames.
5. **Structure** — same 24-section scaffold.
6. **Contradictions** — flat at BB.
7. **Narrative depth** — DID M-72 lift LB → BO? My reading is
   no; the body got SHORTER, not deeper. Codex's call here is
   the verdict on the entire V33 cycle.

## Decision gate

- BEAT_BOTH_SHIP = ≥5/7 BB/BO AND zero LB
- PHASE2_CHECKPOINT = ≥4/7 ≥BO AND ≤1 LB
- ITERATE = otherwise

## Output

Write to `outputs/codex_findings/v30_phase2_run14_audit/findings.md`:

```markdown
# Codex V30 Phase-2 run-14 audit

**7-dimension verdict**: BB=<n>/7 | BO=<n>/7 | LB=<n>/7 | TIE=<n>/7

## Ship classification

- Gate: BEAT_BOTH_SHIP | PHASE2_CHECKPOINT | ITERATE
- Net progress vs run-12: <BB+/-, BO+/-, LB+/->
- Regressions: <none | list>

## V33 (M-72) effectiveness

<Did the cross-trial synthesis lift Narrative depth?
Or did the prompt block constrain the LLM?>

## 7-dim analysis

<per-dim with line refs to report.md>

## Recommended action

<SHIP | CHECKPOINT | ITERATE | ACCEPT_CEILING>

If ACCEPT_CEILING: which run is the canonical PHASE2_CHECKPOINT
to ship as `AUDIT_GRADE_PREVIEW`? Run-9, run-11, or run-14?
```

Under 350 lines. Full xhigh budget. After 5 architectural
cycles, this is the gate decision: ship something, or accept
the ceiling and stop.
