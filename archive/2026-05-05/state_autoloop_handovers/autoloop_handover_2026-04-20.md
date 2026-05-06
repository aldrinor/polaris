# POLARIS DR Auto-Loop — Handover State (2026-04-20)

## Current cycle state

**Iteration 4** of Codex-gated full-scale auto-loop.

### V10 sweep completed (2026-04-20 ~00:00)
- Commit: `ff68b86` (M-23 a-f + M-24 a-b + hotfix)
- Launcher: `scripts/run_full_scale_v10.py`
- Output: `outputs/full_scale_v10/clinical/clinical_tirzepatide_t2dm/`
- status=`abort_evaluator_critical`, release_allowed=False
- T1=20%, T2=14%, T4=38%, T7=22% (BEST corpus tier mix yet)
- Bibliography: 16 unique cited entries, T1+T2=75%, T7=6.25%
- 3 sections (Efficacy/Safety/Comparative), 834 words, 24 verified, 16 dropped
- Evaluator failed PT08 (contradiction) + PT11 (uncited numeric)
- Qwen: citation_tightness=needs_revision

### Codex DR audit pass 4 verdict (live-fetch, not metadata-based)
- Commit audited: `ff68b86`
- Findings: `outputs/codex_findings/dr_output_pass_4/findings.md` (15197 bytes)
- Audit SHA: `5502ddb` (PL commit)
- Verdict: **MATERIAL-GAPS-FIX-AND-RESWEEP**
- Live-fetch result: 18 FAITHFUL / 1 FABRICATED / 1 EMBELLISHED / 4 UNVERIFIABLE (24 total)

### Root-cause diagnosis (before M-25 work)

**1. Outline section count 3 (not 5):** NOT a fallback. LLM outline ran OK
and returned 3 sections (Efficacy, Safety, Comparative). Outline prompt
permits "3-5 sections" — LLM chose minimum. M-24 hotfix (outline_max_tokens
800→2500) prevented JSON truncation but did not force section-count
maximum. `manifest.generator.outline_sections=["Efficacy","Safety","Comparative"]`
confirms clean LLM parse. `outline_ok=True`, no `outline_fallback_used=True`
in manifest.

**2. FABRICATED #20 root cause = generator binding bug:**
- Bibliography [15] = ev_015
- ev_015 title is "Tirzepatide after intensive lifestyle intervention in
  adults with overweight or obesity: the SURMOUNT-3 phase 3 trial"
- URL: `https://www.nature.com/articles/s41591-023-02597-w` (SURMOUNT-3)
- Sentence written by generator: "SURMOUNT-1... tirzepatide 15 mg... 20.9%
  at 72 weeks versus 3.1% placebo" — cites ev_015
- strict_verify passed (numbers likely appear in SURMOUNT-3 paper body as
  subgroup/secondary values)
- No trial-name matching prevented the binding
- **Fix: M-25a — trial-name match in strict_verify**

**3. EMBELLISHED #12 root cause = scope leak:**
- Safety section cites Nature paper `s41467-026-71080-0` (PG-102 phase I,
  bispecific GLP-1/GLP-2 agonist — NOT tirzepatide)
- No population/drug-name gate prevented non-tirzepatide evidence in a
  tirzepatide safety section
- **Fix: M-25c — drug/population gate for safety section**

**4. 4 UNVERIFIABLE:** Codex could not live-fetch URNCST DOI, AHA DOI,
PMC11088184 (x2) source bodies. May be (a) stubs we missed, or (b) paywall
regression between sweep and audit. Needs inspection of cached content.
Defers to M-25 follow-up.

## M-25 plan (per advisor guidance)

**Do NOT batch all 6 Codex-named fixes.** Fixes 1/4/6 depend on outline
running at full width. Fixes 2/3/5 are independent. Ordered by leverage:

- **M-25a (HIGH)**: Trial-name match in strict_verify.
  If sentence names trial S (SURPASS-N, SURMOUNT-N, SELECT, LEADER,
  SUSTAIN, PIONEER, STEP, REWIND, AWARD, GRADE, etc.), cited evidence
  must have S in its title OR be explicitly linked as a secondary/
  post-hoc source for trial S. Prevents FABRICATED-#20 class defects.
  Add failing test first.

- **M-25b (HIGH)**: Outline "choose 5 when supported". Change prompt
  from "Choose 3-5 sections that are best supported" to "Choose EXACTLY
  5 sections when the corpus supports; fall back to 4 only if ≥2
  sections would have <8 ev_ids". This expands from 3→5 sections and
  lifts word count from 834 → ~1400+. Required for 50+ citation density.

- **M-25c (MEDIUM)**: Drug/population scope gate. Safety-section writer
  must reject evidence rows whose title lacks the target drug
  (tirzepatide) OR explicitly mentions only non-T2DM populations (T1D,
  obesity-without-diabetes, other drugs). Addresses EMBELLISHED #12.

- **M-25d (MEDIUM)**: Emit M-23 telemetry into run_log.txt. Unpaywall
  queries/hits, OA swaps, winner backend, quality score. Needed so
  Codex can verify M-23 impact without blind inference.

- **M-25e (LOW)**: Citation adjacency enforcement in limitations +
  contradictions prose. Addresses PT11 + PT08. Can be prompt-only.

- **M-25f (DEFER)**: Adjudicated contradiction table. Architectural.
  Post-M-25.

## Test suite health

654 tests passing at commit `ff68b86`. No regressions from V10.

## Next actions

1. Write failing test reproducing M-25a trial-name misbinding (ev_015 /
   SURMOUNT-1 case).
2. Implement M-25a trial-name gate.
3. M-25b outline prompt update.
4. Verify tests stay green.
5. Launch V11 ONLY after M-25a + M-25b + green suite.

## Key files

- `docs/todo_list.md` — prioritized backlog, ACTIVE section at top
- `.codex/dr_output_audit_pass_4_v10_brief.md` — DR audit brief (committed)
- `outputs/codex_findings/dr_output_pass_4/findings.md` — pass-4 verdict
- `outputs/full_scale_v10/` — v10 artifacts

## Cost so far (V10 sweep)

$0.0067 / $10.00 cap.

## Timeline

- 06:43 V10 launched (ff68b86)
- 23:42 V10 completed (abort_evaluator_critical)
- 23:50 Pass 4 brief staged
- 00:00 Pass 4 dispatched (codex exec --full-auto)
- 00:06 Pass 4 completed (MATERIAL-GAPS, live-fetch mandate satisfied)
- 00:08 Pass 4 findings committed (5502ddb)
- 00:10 Diagnosis: outline OK (3/5 min), #20 = generator binding bug
