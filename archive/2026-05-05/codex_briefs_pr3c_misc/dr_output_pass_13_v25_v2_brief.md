You are Codex DR output audit pass 13, running as step 2b of the
autoloop V2 protocol. First V25 audit under V2 — Claude is writing
its own parallel audit to outputs/audits/v25/claude_audit.md.

## Stop criterion (unchanged)

BEAT-BOTH ChatGPT DR + Gemini 3.1 Pro DR on 7 dimensions.

## V25 headline metrics (already extracted)

Compared against prior Vs:

| Metric | V23 | V24 | V25 |
|---|---:|---:|---:|
| sections | 5 | 5 | **6** (Efficacy, Safety, Comparative, Mechanism, Dose Response, Regulatory) |
| prose body words | 1455 | 1327 | **1707** |
| verified sentences | 35 | 38 | **51** |
| bibliography size | 31 | 35 | **40** |
| corpus size | 360 | 409 | 414 |
| report total words | 2503 | 2666 | **2921** |
| M-41c sentences dropped | — | — | **9** (Safety 2, Mechanism 6, Regulatory 1) |
| Trial Summary table | MISSING | PRESENT (thin) | SUPPRESSED (M-41b dropped thin rows; nothing valid remained) |
| Mechanism section | — | PRESENT (5 mentions) | **PRESENT** (2 mentions — M-41c dropped 6 under-framed) |
| Regulatory section | PRESENT | **MISSING (regression)** | **RESTORED** (M-41a 6-section outline) |
| FDA / EMA / NICE / HC citations | 6/4/3/0 | 0/0/0/0 (regression) | **7/3/4/1** (recovered + gained HC) |
| evaluator rule checks | 12/13 | 13/13 | 12/13 (PT13 advisory only, same as V23) |
| release_allowed | true | true | true |
| status | success | success | success |

### V25 vs V23 prior pass-11 baseline

V25 is structurally STRONGER than V23 on dimensions V23 won:
- Regulatory: restored. V25 has 7 FDA entries (V23 had 6), 3 EMA
  (V23 had 4 — slight regression), 4 NICE (V23 had 3), 1 HC
  (V23 had 0 — gain).
- Mechanism: new section, 2 verified mentions in the actual
  report (V23 had 0).
- Claim frames: M-41c dropped 9 under-framed trial-name mentions,
  so the remaining trial mentions in V25 should be properly
  framed. SURPASS-2 (4), SURPASS-3 (2). Compare to V24's more
  numerous but under-framed trial mentions.

### V25 weaknesses to verify

- Trial summary table is EMPTY (M-41b decided no rows were
  meaningful enough to ship). This is a design trade: better
  than V24's 3-rows-2-empty table, but still not a table.
- Mechanism section only 2 mentions of "mechanism" in final prose
  (M-41c dropped 6 under-framed sentences). Question: is what
  remains sufficient to BEAT ChatGPT or Gemini on Mechanism?
- Limitations section word count not yet pulled — check if
  present + substantive.

## What to verify dimension-by-dimension

1. **Citations**: unique URL count (40) vs ChatGPT (21) vs Gemini
   (43). Primary-trial coverage: are NEJM/Lancet/JAMA SURPASS-2
   (Frias 2021), SURPASS-1 (Rosenstock 2021), SURPASS-3
   (Ludvik 2021), SURMOUNT-1 (Jastreboff 2022) cited as
   first-class sources?

2. **Regulatory**: V25 restored Regulatory section. How deep is
   it vs ChatGPT's FDA label/EMA SmPC coverage vs Gemini's FDA/
   Health Canada/counterfeit/monograph coverage?

3. **Jurisdictional**: V25 has 1 HC citation. Compare to Gemini's
   Health Canada specificity (KwikPen, counterfeit, product
   monograph details). Is 1 HC entry enough or still weak?

4. **Claim frames**: M-41c deterministically enforces. Spot-check
   3-5 named-trial sentences in V25 prose for full-frame
   compliance (N / baseline / comparator / dose / endpoint /
   timepoint / effect size). The surviving mentions SHOULD all
   carry 3+ frame elements.

5. **Structural depth**: V25 has 6 prose sections + Limitations +
   Methods + Contradictions + Bibliography. No trial table (M-41b
   suppressed). Compare to ChatGPT's trial architecture table +
   forest chart + prescribing + NNT + timeline; Gemini's trial-
   by-trial subsections + regulatory-risk synthesis.

6. **Contradiction handling**: V25 will have a contradictions
   section. V23 was BEAT_BOTH here; V24 preserved it. V25 should
   preserve too.

7. **Narrative depth**: V25 Mechanism has 2 mentions (post-M-41c
   drops). Gemini has full pharmacokinetics + receptor-binding
   + clamp data + central appetite. Is V25's Mechanism competitive?

## Context budget discipline

Read ONLY:
```
outputs/full_scale_v25/clinical/clinical_tirzepatide_t2dm/report.md
outputs/full_scale_v25/clinical/clinical_tirzepatide_t2dm/bibliography.json
outputs/full_scale_v25/clinical/clinical_tirzepatide_t2dm/manifest.json
state/compare_chatgpt_dr.txt
state/compare_gemini_dr.txt
```

Do NOT read contradictions.json (V25 manifest summarizes), do NOT
read live_corpus_dump.json, do NOT enumerate archive/ or outputs/
beyond the V25 directory.

## Deliverable

Write `outputs/audits/v25/codex_audit.md` with:
- 7-dimension table: BEAT_BOTH / BEAT_ONE / LOSE_BOTH per dim with
  concrete evidence (POLARIS-output line + competitor line)
- Overall verdict: BEAT_BOTH | PARTIAL | REGRESSED
- Specific gaps if not BEAT_BOTH
- Per-fix assessment: did M-35 / M-36 / M-37 / M-38 / M-40 /
  M-41a / M-41b / M-41c / M-41d move their intended dimensions?

Keep under 3000 words. Claude is writing a parallel audit; after
both land, cross-review per V2 runbook §3.
