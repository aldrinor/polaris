V30 Phase-2 run-7 deep content audit — xhigh reasoning.

**Skip git status.** Codex at gpt-5.4 + xhigh.

## Target

`outputs/full_scale_v30_phase2_run7/clinical/clinical_tirzepatide_t2dm/report.md`
(2,489 words, status=success, qwen=2 GOOD + 2 ACCEPTABLE + 1
NEEDS_REVISION, release_allowed=True — FIRST run to pass all
gates post-M-66).

Manifest: `outputs/full_scale_v30_phase2_run7/clinical/clinical_tirzepatide_t2dm/manifest.json`.

## Context

Post-M-66 run-7 delta vs run-2 baseline:
- status: partial_qwen_advisory → success
- release_allowed: False → True
- frame coverage pass: 8/15 → 14/15
- regulatory metadata_only: 6 → 0 (all fetched OPEN_ACCESS)
- Thomas clamp: 0 extracted → 7 of 10 fields
- NICE TA1026: 0 → 2 extracted
- M-63 parse failures: 6 (run-5) → 3 (run-7) after M-66a-R

But residual defects:
- SURPASS-6 still dropped from report body (M-59 pass, but not
  rendered). SURPASS-2's dose+weight ETDs absent.
- 4 of 6 regulatory subsections dropped from body (FDA Mounjaro,
  EMA EPAR, HC Mounjaro + partial SURPASS-6). `frame_coverage=pass`
  but body missing heading entirely.
- Trial Summary still 2 rows (below M-66 acceptance ≥6).
- Word count 2,489 vs ChatGPT 4,830 / Gemini 6,835.

## Competitors

- `state/compare_chatgpt_dr.txt` (4,830 words)
- `state/compare_gemini_dr.txt` (6,835 words)

## 7 BEAT-BOTH dimensions

(Same framework as run-2 audit at
`outputs/codex_findings/v30_phase2_run2_audit/findings.md`.)

1. Citations — primary-trial publications, ETD+CI+P, correct
   bindings
2. Regulatory — FDA + EMA + NICE + HC named and substantively cited
3. Jurisdiction — US + EU + UK + Canada coverage
4. Claim-frames — PICO, dose stratification, uncertainty language
5. Structure — section order, subsection granularity, table/timeline
6. Contradictions — tier-labeled explicit disclosure
7. Narrative depth — synthesis + comparative framing beyond extraction

For each: Verdict **V30 BEAT_BOTH | V30 BEAT_ONE | V30 LOSE_BOTH | TIE**
with line refs to report.md, compare_chatgpt_dr.txt,
compare_gemini_dr.txt.

## Claude's provisional verdict (for reconciliation)

`outputs/codex_findings/v30_phase2_run7_audit/claude_findings.md`
tallies **1 BB + 2 BO + 4 LB** (net ≥BEAT_ONE: 3). Classifies
as `PHASE2_CHECKPOINT`, NOT `BEAT_BOTH_SHIP` (strict gate = zero LB).

Expected disagreement points:
1. Does SURPASS-6 drop count as Structure LB or a regression?
2. Does NICE TA1026 2-field extraction count toward Regulatory
   recovery (LB→BO lift)?
3. Does M-66c Thomas clamp fix lift Claim-frames to BB?
4. Is FDA Zepbound's heading-with-zero-content rendering a
   Structure defect worse than missing-heading?

## Your job

Apply PRISMA 2020 / AMSTAR-2 / GRADE lens to each dimension.
Give per-dimension verdict with evidence (file:line refs).
Reconcile with Claude's verdict explicitly. Decide:
- SHIP (BEAT-BOTH ≥5/7 AND zero LB): proceed to announce V30
  Phase-2 ship.
- CHECKPOINT (≥4/7 ≥BO AND ≤1 LB AND zero regressions): commit
  as PHASE2_CHECKPOINT, escalate to M-67.
- ITERATE (worse than checkpoint): narrow fix plan for run-8.

## Output

Write to `outputs/codex_findings/v30_phase2_run7_audit/findings.md`.

```markdown
# Codex V30 Phase-2 run-7 audit vs ChatGPT DR + Gemini DR

**7-dimension verdict**: BB=<n>/7 | BO=<n>/7 | LB=<n>/7 | TIE=<n>/7

## Ship classification

- Gate: BEAT_BOTH_SHIP | PHASE2_CHECKPOINT | ITERATE
- Regressions vs run-2: <none | list>

## Primary-trial + regulatory spot-check

<per-entity status — render? extractions? >

## 7-dimension analysis

### 1. Citations
V30 says: ... [report.md:N]
ChatGPT says: ... [compare_chatgpt_dr.txt:N]
Gemini says: ... [compare_gemini_dr.txt:N]
Critical appraisal: ...
Winner: **V30 | ChatGPT | Gemini | TIE** → BB|BO|LB|TIE

### 2-7: <same format>

## Reconciliation with Claude's verdict

<point-by-point — agreements + disagreements + tie-breaker evidence>

## Summary + Next

- Tally: BB=<n> BO=<n> LB=<n>
- Recommended action: SHIP | CHECKPOINT | ITERATE
- Fix plan if ITERATE: <narrow list>
```

Under 400 lines. Full xhigh budget. This is the ship/checkpoint
decision gate.
