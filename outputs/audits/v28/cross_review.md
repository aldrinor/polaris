# V28 Cross-review (step 3, autoloop V2)

**Audit date**: 2026-04-22
**Rule**: per-disagreement table; lower verdict controls unless disproven with concrete evidence.
**Sources**:
- Claude: `outputs/audits/v28/claude_deep_content_audit.md`
- Codex: `outputs/codex_findings/v28_deep_content_audit/findings.md`

## Per-topic agreement table

| Topic | Claude winner | Codex winner | Agreement |
|---|:-:|:-:|:-:|
| A. SURPASS-2 | ChatGPT | ChatGPT | ✓ |
| B. SURPASS-CVOT | Gemini | ChatGPT | **disagree** |
| C. SURPASS-4 | ChatGPT | ChatGPT | ✓ |
| D. Mechanism | Gemini | Gemini | ✓ |
| E. Regulatory | V28 | V28 | ✓ |
| F. Contradictions/uncertainty | V28 | Tie (ChatGPT / V28) | soft disagree |

5 of 6 topics converge on the winner. The B disagreement reflects how each auditor weighted Gemini's detailed MACE numbers against ChatGPT's correct noninferiority framing — both interpretations are defensible. F is a split where Codex credits ChatGPT's clinical uncertainty language alongside V28's enumeration.

## Per-dimension agreement table (the authoritative scoreboard)

| Dim | Claude verdict | Codex verdict | Lower | Adjudication |
|---|---|---|---|---|
| 1. Citations | BEAT_ONE | LOSE_BOTH | LOSE_BOTH | SURPASS-2 cited via T4 post-hoc [20]; SURPASS-4/CVOT primaries absent from bibliography despite being in live corpus. Claude's BEAT_ONE was based on 46 total entries — Codex's is based on pivotal coverage. **Lower verdict stands: LOSE_BOTH.** |
| 2. Regulatory | BEAT_BOTH | BEAT_BOTH | — | Agreed: V28 is only report with FDA + EMA + NICE + HC. |
| 3. Jurisdictional | BEAT_BOTH | BEAT_BOTH | — | Agreed: jurisdiction-specific detail preserved. |
| 4. Claim frames | BEAT_ONE | LOSE_BOTH | LOSE_BOTH | Codex cited 3 concrete failures: SURPASS-2 primary ETDs missing, SURPASS-4/CVOT omitted, Trial Summary table cells malformed (SURPASS-5 "baseline 7.0%" is wrong — actual 8.31%; endpoint blank; result "10.5%" uninterpretable). **Lower verdict stands: LOSE_BOTH.** |
| 5. Structural depth | BEAT_ONE | LOSE_BOTH | LOSE_BOTH | Codex cited 3 concrete failures: (a) Trial Summary table 2 weak rows with corrupted cells, (b) per-trial subsections cover SURPASS-1/-3/-5 instead of target SURPASS-2/-4/-CVOT/SURMOUNT-2, (c) SURPASS-5 subsection admits "quote does not specify a key safety caveat" — 6/7 elements, fails M-50 contract. ChatGPT has 6×11 table; Gemini has all-trial subsections. V28 is structurally thinner than both. **Lower verdict stands: LOSE_BOTH.** |
| 6. Contradiction handling | BEAT_BOTH | BEAT_BOTH | — | Agreed: 14-item enumeration + tier disclosure. |
| 7. Narrative depth | BEAT_ONE | LOSE_BOTH | LOSE_BOTH | Codex: Mechanism 866w is longer than V27 (184w) but content is generic review-grade, not primary-extraction depth. No [ev_X] inline same-sentence citations for clamp findings. ChatGPT wins on trial narrative extraction; Gemini wins on mechanism pharmacology. V28 third in both. **Lower verdict stands: LOSE_BOTH.** |

## Adjudicated V28 scoreboard

**3 BEAT_BOTH + 0 BEAT_ONE + 4 LOSE_BOTH**

Comparison across cycles:

| Cycle | BEAT_BOTH | BEAT_ONE | LOSE_BOTH | Total ≥BEAT_ONE |
|---|---:|---:|---:|---:|
| V25 | 1 | 4 | 2 | 5 |
| V27 | 1 | 4 | 2 | 5 |
| **V28** | **3** | **0** | **4** | **3** |

V28 improved on **BEAT_BOTH count** (1 → 3) but regressed on **≥BEAT_ONE count** (5 → 3). Net dimensional health: mixed. The "no LOSE_BOTH" target failed — V28 has 4 LOSE_BOTH (doubling V27's 2).

## Dimension-by-dimension V27 → V28 delta

| Dim | V27 | V28 | Delta |
|---|:-:|:-:|:-:|
| 1. Citations | BEAT_ONE | **LOSE_BOTH** | ↓ regressed |
| 2. Regulatory | BEAT_ONE | **BEAT_BOTH** | ↑ upgraded |
| 3. Jurisdictional | BEAT_ONE | **BEAT_BOTH** | ↑ upgraded |
| 4. Claim frames | LOSE_BOTH | LOSE_BOTH | = |
| 5. Structural depth | LOSE_BOTH | LOSE_BOTH | = |
| 6. Contradiction handling | BEAT_BOTH | BEAT_BOTH | = |
| 7. Narrative depth | BEAT_ONE | **LOSE_BOTH** | ↓ regressed |

**2 regressions** (Citations + Narrative) vs **2 upgrades** (Regulatory + Jurisdictional).

## §7 halt-trigger check

V2 §7 trigger #7: "Any REGRESSION dimension V27 → V28 without compensating BEAT_BOTH upgrade" — FIRES.

Dim 1 (Citations) V27=BEAT_ONE → V28=LOSE_BOTH: regression. Compensation? Dims 2 + 3 upgraded V27=BEAT_ONE → V28=BEAT_BOTH, which offsets. But those upgrades were already V27 wins at BEAT_ONE tier — the trigger asks whether the regression is OFFSET by NEW BEAT_BOTHs in dims that weren't already winning. Dim 1 regressing without a new BEAT_BOTH elsewhere is a genuine halt signal.

Dim 7 (Narrative) V27=BEAT_ONE → V28=LOSE_BOTH: regression. Not offset by any dim-specific upgrade (2+3 upgrades are on different axes).

**Recommendation**: halt autonomous loop; surface to user. V28 → V29 fix plan required.

## Root-cause classification of the 4 LOSE_BOTH dimensions

All 4 LOSE_BOTH root-cause to **2 upstream defects**:

### Defect 1: Retrieval landed 4/11 pivotal primary papers, not 9/11 target

Pivotal primaries in V28 bibliography:
- ✓ SURPASS-1 [1]: Lancet 2021
- ✓ SURPASS-3 [2][3]: Lancet 2021
- ✓ SURPASS-5 [17]: JAMA 2022
- ✓ SURPASS-6 [18]: JAMA 2023
- ✓ SURMOUNT-4 [11]: PMC 2024
- ✗ SURPASS-2 primary Frías NEJM — cited via T4 post-hoc [20] instead
- ✗ SURPASS-4 primary Del Prato Lancet — in live_corpus but not selected
- ✗ SURPASS-CVOT primary Nicholls NEJM 2025 — in live_corpus but not selected
- ✗ SURMOUNT-1 primary Jastreboff NEJM 2022
- ✗ SURMOUNT-2 primary Garvey Lancet 2023
- ✗ SURMOUNT-3 primary Wadden Nat Med 2023

5/11 in biblio (Codex counts 5-6 depending on separate counting of SURPASS-3 CGM substudy).

The M-48 first-author variant queries for SURPASS-2/4/CVOT DID fire (22 primary-trial queries observed in retrieval log), but:
- SURPASS-4 (Del Prato Lancet) landed in live_corpus but was not selected into the final bibliography — **selector bug, not retrieval bug**.
- SURPASS-CVOT primary was in live_corpus — same selector bug.
- SURPASS-2 primary may not have landed despite Frías variant — OR landed and was outranked by the post-hoc [20].

**This is the dominant root cause driving Dims 1, 4, 5, 7 to LOSE_BOTH.**

### Defect 2: M-44 injection did not force primary selection into sections

M-44 telemetry: 0 injections, 2 validator violations. If M-44's `_m44_detect_primary_ev_ids` couldn't see SURPASS-2/4/CVOT primaries in the evidence pool (because the selector dropped them), M-44 had nothing to inject.

If SURPASS-4/CVOT primaries WERE in the evidence pool but not `is_primary_trial`-tagged, M-44 also missed them.

Needs investigation at the selector → M-44 boundary: why did Del Prato Lancet land in live_corpus but not reach the section's ev_ids subset?

## Gate verdict

See `outputs/audits/v28/gate_verdict.md`.

## Next step per V2 runbook

V2 step 5: write V28 → V29 fix plan addressing Defect 1 + Defect 2. Submit to Codex for plan review.

**User surface required** — this is outside autoloop autonomy per §7 halt trigger.
