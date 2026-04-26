V30 Phase-2 run-14 SUBSTANCE-DENSITY re-audit — xhigh reasoning.

**Skip git status.** Codex at gpt-5.4 + xhigh.

## Critical reframing — read carefully

The user pushed back on the prior `Narrative depth LB` verdict
(runs 9-14). My methodology was wrong: I measured "depth" by
competitor word count. The user asked: *"are they all golden, or
are they all water?"*

I (Claude) measured. The data:

| Metric | ChatGPT DR | Gemini DR | V30 run-14 |
|---|---|---|---|
| Word count | 4,830 | **6,835** | 2,599 |
| Numeric facts (%) | 257 | 129 | 91 |
| 95% CIs | 12 | **0** | 3 |
| P-values | 11 | 3 | 3 |
| HR/RR/OR | 5 | **0** | 1 |
| Inline [N] citations | 0 | 0 | **112** |
| Promotional adjectives | 1 | **58** | 1 |
| Numeric facts / 1K words | 59.0 | **19.3** | 37.6 |

**Gemini's word advantage is filler.** Zero 95% CIs across
6,835 words. Zero HR/RR/OR. 58 promotional adjectives ("remarkable
63%", "massive reduction", "profoundly", "effectively reverses
the lipotoxic environment"). This is press-release prose dressed
as a clinical brief.

**ChatGPT is real density.** 59 numeric facts / 1K words.
Genuinely audit-grade in numeric content, but ZERO inline
citations.

**V30 run-14 sits between**: 37.6 facts / 1K words (≈63% of
ChatGPT, ≈195% of Gemini). Plus the only artifact with inline
[N] citations.

## Audit ask

Under the original framing (word-count proxy for depth) the
verdict was 1 BB + 4 BO + 2 LB across runs 9-14. Re-audit run-14
under SUBSTANCE-DENSITY gates instead. Specifically:

### Re-score Narrative depth (was LB)

Two opposing facts:
  - V30 run-14 is shorter than Gemini AND ChatGPT
  - V30 run-14 has higher numeric-fact density per 1K words
    than Gemini AND comparable inline citation traceability
    that NEITHER competitor provides

PRISMA + GRADE prefer effect-estimate density + uncertainty
discipline + traceability over verbosity. Under PRISMA, does
V30 run-14 actually meet or exceed Gemini on Narrative depth?
Or is the strict ship gate's word-count proxy correct after all?

### Re-score Citations (was BO)

V30 run-14: 112 inline `[N]` citations, every claim traceable to
biblio.json, T1-anchored bibliography. ChatGPT: dense facts but
zero adjacent citations. Gemini: zero adjacent citations + mixed
T4/T7 sources (Pharmacy Times, Lilly PR, CBC).

PRISMA 2020 explicitly requires traceable inline citation. Is
this a BB lift for V30 — beating BOTH competitors on
PRISMA-compliant citation discipline?

### Re-score Hedging (cross-cutting consideration)

Gemini phrasing: "decisively established", "definitive
cardiovascular protection", "remarkable 63%", "robustly drives".
V30 run-14 + run-12 explicitly disclose 14 contradiction clusters
with tier labels.

Under GRADE / AMSTAR-2, Gemini's confidence language is a
quality DEFECT, not a depth strength. Should hedging discipline
be its own dimension lift?

## 7-dim re-evaluation

For each dimension, score:
1. Citations
2. Regulatory
3. Jurisdiction
4. Claim-frames
5. Structure
6. Contradictions
7. Narrative depth (under substance-density framing)

Verdict per dim: V30 BEAT_BOTH | BEAT_ONE | LOSE_BOTH | TIE.

Use the substance-density data above; pull additional substance
checks from `state/compare_chatgpt_dr.txt` and
`state/compare_gemini_dr.txt` as needed.

## Decision gate

- BEAT_BOTH_SHIP = ≥5/7 BB/BO AND zero LB
- PHASE2_CHECKPOINT = ≥4/7 ≥BO AND ≤1 LB

Under the substance-density re-frame, does run-14 reach
BEAT_BOTH_SHIP? Or PHASE2_CHECKPOINT?

## Key question

Was the prior Codex verdict (`ACCEPT_CEILING`) using a flawed
proxy (word count) for Narrative depth? Or does the strict
ship gate stay strict regardless of competitor quality?

## Output

Write to `outputs/codex_findings/v30_phase2_run14_substance_audit/findings.md`:

```markdown
# Codex V30 Phase-2 run-14 substance-density re-audit

**7-dimension verdict (substance-density framing)**: BB=<n>/7 | BO=<n>/7 | LB=<n>/7

## Methodology change

<acknowledgment that prior word-count proxy was wrong / right
for Narrative depth>

## Per-dimension re-scores

### 1. Citations (prior: BO; re-scored: ___)
<reasoning with evidence>

### 2-7: <same>

## Ship classification

- Gate: BEAT_BOTH_SHIP | PHASE2_CHECKPOINT | ITERATE
- Difference vs prior word-count framing: <quantified>

## Verdict on prior ACCEPT_CEILING

<was ceiling diagnosis correct? or was it a methodology error?>

## Recommended action

<SHIP run-14 as BEAT_BOTH_SHIP | ship as PHASE2_CHECKPOINT | iterate>
```

Under 300 lines. Full xhigh budget. This is a fundamental
methodology question, not a polish question. Be direct about
disagreements with my re-framing if you have them.
