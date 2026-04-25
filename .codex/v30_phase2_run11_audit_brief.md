V30 Phase-2 run-11 deep content audit — xhigh reasoning.

**Skip git status.** Codex at gpt-5.4 + xhigh.

## Target

`outputs/full_scale_v30_phase2_run11/clinical/clinical_tirzepatide_t2dm/report.md`
(3,112 words — highest yet, status=success, qwen=2 GOOD + 2 ACCEPTABLE
+ 1 NEEDS_REVISION, release_allowed=True, gate_reasons=
['advisory_pt13_unhedged_superlatives']).

## Run history

| Run | status | release | qwen | tally | notes |
|-----|--------|---------|------|-------|-------|
| 7 | success | True | 2G+2A+1NR | 1BB+3BO+3LB | 4 silent drops |
| 9 | partial | False | 1G+1A+3NR | 1BB+4BO+2LB CHECKPOINT | 15/15 cited gaps |
| 10 | success | True | 3G+1A+1NR | 1BB+4BO+2LB ITERATE | SURMOUNT-2 + Thomas regressed |
| 11 | **success** | **True** | **2G+2A+1NR** | TBD | M-69 Fix #5 active |

## Run-11 deltas vs run-10

Material improvements:

1. **Bibliography labels human-readable**: regulatory entries now
   read "FDA Mounjaro Label", "EMA Mounjaro Label", "NICE TA924
   Label", "NICE TA1026 Label", "FDA Zepbound Label" instead of
   bare entity_id (run-10 had `statement=fda_mounjaro_label`).
2. **SURMOUNT-2 recovered** from all-gap (run-10) to 5 extracted
   fields including baseline weight 100.7 kg, baseline HbA1c
   8.0%, primary endpoint = "percent change in body weight from
   baseline to week 72", sponsor.
3. **SURPASS-5 substantive**: full ETD with CI+P now in body
   ("10 mg: difference, −1.53% [97.5% CI, −1.80% to −1.27%];
   P <.001; 15 mg: difference, −1.47% [97.5% CI, −1.75% to
   −1.20%]; P <.001"). Was gap in run-9, partial in run-10.
4. **Thomas clamp** keeps all 8 fields (glucagon_suppression
   restored).
5. Word count 3,112 (run-10: 3,023; run-9: 2,812).

Residuals:

- SURPASS-6 still all-`not extractable` (DOI corrected but
  M-58 extraction still struggles with Rosenstock JAMA 2023
  abstract structure).
- SURPASS-CVOT remains paywall-blocked (frame_gap_unrecoverable
  by retrieval, not extraction).
- FDA Mounjaro / FDA Zepbound / EMA EPAR / NICE TA924 / HC
  monograph still mostly `not extractable` in body fields
  (regulatory pages have stub-like LLM extraction even with
  full-text fetched).
- Trial Summary still 4 rows with same biblio misalignment as
  run-10.

## Competitors

- `state/compare_chatgpt_dr.txt` (4,830 words)
- `state/compare_gemini_dr.txt` (6,835 words)

## Audit ask

Apply 7-dim framework. Score deltas vs run-10 explicitly.

Decision gate options:
- **BEAT_BOTH_SHIP** = ≥5/7 BB/BO AND zero LB
- **PHASE2_CHECKPOINT** = ≥4/7 ≥BO AND ≤1 LB
- **ITERATE** = otherwise

## Specific reconciliation questions

1. Does Bibliography cleanup (regulatory entries with proper
   "FDA Mounjaro Label" labels) lift Citations BO→BB?
2. Does SURMOUNT-2 recovery + SURPASS-5 ETD restoration lift
   Claim-frames BO→BB?
3. Does Regulatory move from LB to BO given:
   - 6/6 regulatory subsections render
   - Bibliography labels are now usable
   - Substantive content still thin (only TA1026 has 2-3 fields,
     others mostly stubs)?
4. Net progress vs run-9 CHECKPOINT? Has BB count moved?
5. Is run-11 the first **BEAT_BOTH_SHIP** candidate?

## Output

Write to `outputs/codex_findings/v30_phase2_run11_audit/findings.md`:

```markdown
# Codex V30 Phase-2 run-11 audit

**7-dimension verdict**: BB=<n>/7 | BO=<n>/7 | LB=<n>/7 | TIE=<n>/7

## Ship classification

- Gate: BEAT_BOTH_SHIP | PHASE2_CHECKPOINT | ITERATE
- Net progress vs run-10: <BB+/-, BO+/-, LB+/->
- Regressions: <none | list>

## 7-dim analysis

<per-dim with line refs to report.md and competitor compares>

## Reconciliation

<are run-10 regressions repaired? are bibliography fixes enough
to lift Citations? does run-11 ship?>

## Recommended action

<SHIP | CHECKPOINT-and-escalate-M-70 | ITERATE-narrow-fix-list>
```

Under 350 lines. Full xhigh budget.
