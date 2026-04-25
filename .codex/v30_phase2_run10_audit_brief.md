V30 Phase-2 run-10 deep content audit — xhigh reasoning.

**Skip git status.** Codex at gpt-5.4 + xhigh.

## Target

`outputs/full_scale_v30_phase2_run10/clinical/clinical_tirzepatide_t2dm/report.md`
(3,023 words — first run >3K, status=success, qwen=3 GOOD + 1
ACCEPTABLE + 1 NEEDS_REVISION, release_allowed=True, gate_reasons=[]).

Manifest: same dir / manifest.json.

## Run history scoreboard

| Run | status | release | qwen | tally |
|-----|--------|---------|------|-------|
| 7 | success | True | 2G+2A+1NR | 1BB+3BO+3LB |
| 9 | partial | False | 1G+1A+3NR | 1BB+4BO+2LB CHECKPOINT |
| 10 | **success** | **True** | **3G+1A+1NR** | TBD |

Run-10 carries M-69 Fix #1 (SURPASS-6 DOI corrected — was glioblastoma
JAMA paper) + Fix #4 (strict_verify rescue for contract sentences).

## What changed since run-9

1. **SURPASS-6 biblio binding correct now** — biblio[7] = "Tirzepatide
   vs Insulin Lispro Added to Basal Insulin in Type 2 Diabetes" (real
   Rosenstock paper, was glioblastoma in run-9).
2. **SURPASS-1 extractions back** — Population, Primary endpoint,
   Safety signal, Study design, Sponsor all extracted (run-9 had
   only fragments).
3. **All 6 regulatory subsections render** with multiple field
   attempts (FDA Mounjaro now lists 5 fields, FDA Zepbound 5 fields,
   EMA EPAR 4 fields, NICE TA924 5 fields, NICE TA1026 2 substantive
   fields, HC monograph 4 fields). Most still mark `not extractable`
   but headings + structure are present.
4. **Word count**: 3,023 (run-9: 2,812; run-7: 2,489).
5. **release_allowed=True** restored (was False in run-8/9 due to
   Qwen citation_tightness flagging gap-citation refs as "invalid
   sources").

## Residuals

- SURPASS-3/4/5/6 + SURMOUNT-2 still have many `not extractable`
  fields despite OA full-text retrieval.
- Trial Summary still 4 rows (SURPASS-5/6 + CVOT missing).
- Regulatory biblio statements still bare entity_id
  (`statement=fda_mounjaro_label`) — Fix #2 was placed at the wrong
  surface; correction queued for run-11.
- Hedging propagation into Comparative + Safety body still pending.

## Competitors

- `state/compare_chatgpt_dr.txt` (4,830 words)
- `state/compare_gemini_dr.txt` (6,835 words)

## Audit ask

Apply same 7-dim framework as run-7 + run-9. Report
**dimension-level deltas vs run-9** explicitly:

1. Citations — SURPASS-6 binding correct now; full ETD+CI+P on
   SURPASS-2 preserved.
2. Regulatory — 6/6 rendered, FDA Zepbound + NICE TA1026 have
   substantive content, others mostly stubs. Net BO?
3. Jurisdiction — US + EU + UK + Canada explicit (was BO in run-9).
4. Claim-frames — SURPASS-1 PICO restored; SURPASS-2/Thomas remain
   strong; SURPASS-3-6 mostly gaps.
5. Structure — 15/15 slots render, biblio binding corrected.
6. Contradictions — same disclosure as run-9.
7. Narrative depth — Comparative + Safety + Population Subgroups
   richer than run-9 (more numeric data integrated).

## Decision gate

- `BEAT_BOTH_SHIP` = ≥5/7 BB/BO AND zero LB
- `PHASE2_CHECKPOINT` = ≥4/7 ≥BO AND ≤1 LB (run-9 hit this)
- `ITERATE` = otherwise

## Output

Write to `outputs/codex_findings/v30_phase2_run10_audit/findings.md`:

```markdown
# Codex V30 Phase-2 run-10 audit

**7-dimension verdict**: BB=<n>/7 | BO=<n>/7 | LB=<n>/7 | TIE=<n>/7

## Ship classification

- Gate: BEAT_BOTH_SHIP | PHASE2_CHECKPOINT | ITERATE
- Net progress vs run-9: <BB+/-, BO+/-, LB+/->
- Regressions: <none | list>

## 7-dim analysis

<per-dim with line refs to report.md and competitor compares>

## Reconciliation with run-9 trajectory

<are we ahead vs run-9, what specifically improved, what still fails>

## Recommended action

<SHIP | CHECKPOINT-and-escalate-M-70 | ITERATE-narrow-fix-list>
```

Under 350 lines. Full xhigh budget.
