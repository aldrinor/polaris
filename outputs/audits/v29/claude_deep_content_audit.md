# V29 Claude Deep Content Audit
## Line-by-line PRISMA 2020 / AMSTAR-2 / GRADE vs ChatGPT + Gemini

**Audit date**: 2026-04-23
**V29 manifest**: status=success, release_allowed=True, cost $0.018
**V29 runtime**: 2h35m (launched 07:25:53, manifest 10:01:18)
**V29 custody diagnostic**: 0/11 anchors with cited_in_verified_prose
(breakdown below)

---

## V29 custody diagnostic (M-53) — THE V29 headline

Per-anchor telemetry from `v29_primary_custody.json`:

| Anchor | Custody step that broke |
|---|---|
| SURPASS-1 | generator prose (M-51/M-44 injected but LLM didn't cite) |
| SURPASS-2 | retrieval (primary not in live_corpus) |
| SURPASS-3 | retrieval |
| SURPASS-4 | generator prose (M-51 inserted but LLM didn't cite) |
| SURPASS-5 | generator prose (M-44 injected but LLM didn't cite) |
| SURPASS-6 | retrieval |
| SURPASS-CVOT | retrieval |
| SURMOUNT-1 | retrieval |
| SURMOUNT-2 | retrieval |
| SURMOUNT-3 | retrieval |
| SURMOUNT-4 | retrieval |

**Two distinct V29 defects surfaced** (not one, as we assumed):

**Defect A: Retrieval non-determinism (7/11 anchors).** V28 had
SURPASS-4 Del Prato Lancet in live_corpus; V29's identical M-48
first-author variant query "Del Prato Lancet tirzepatide glargine
cardiovascular" did NOT surface it. V29 live_corpus contains
trial-name mentions for SURPASS-2/3/6/CVOT + SURMOUNT-1/2/3/4
(6-10 rows each) but NONE pass the strict
`_m42e_detect_primary_for_anchor` test (which requires primary
DOI/host + no post-hoc/review marker in title).

**Defect B: Generator prompt doesn't force M-44 injection to prose
(3/11 anchors).** M-51 inserted SURPASS-4 (ev_402) into
selected_rows. M-44 injected ev_402 into Efficacy, Safety,
Comparative, Population Subgroups sections. LLM DID NOT CITE
ev_402 in any section's prose. The injected ev_id never reached
the bibliography — the generator picked other evidence from its
subset instead. M-44 validator is empty because the LLM never
named the trial by short-name, so there's nothing for the
same-sentence check to enforce.

---

## Quantitative V27 → V28 → V29 snapshot

| Metric | V27 | V28 | **V29** | V29 Δ vs V28 |
|---|---:|---:|---:|---:|
| Report words | 3,441 | 3,837 | **3,397** | -11% |
| Content sections | 3 | 6 | **6** | = |
| **Mechanism section words** | 184 | 866 | **1,388** | **+60%** |
| Per-Trial Summaries | 0 | 3 | **0** | LOST |
| Trial Summary table rows | 0 | 2 | **0** | LOST |
| Trial Program Timeline | 0 | 2 | **0** | LOST |
| Biblio size | 47 | 46 | **47** | +1 |
| Contradictions | 13 | 14 | **15** | +1 |
| FDA entries | 5 | 4 | **8** | **+4** |
| EMA entries | 7 | 3 | **3** | = |
| NICE entries | 3 | 4 | **2** | **-2** |
| HC entries | 3 | 1 | **1** | = |
| SURPASS-CVOT mentioned | ✗ | ✗ | **✓** | NEW |
| SURMOUNT-2 mentioned | ✗ | ✗ | **✓** | NEW |

V29 is stronger on **Mechanism + FDA coverage + CVOT/SURMOUNT-2 mentions** but LOST all 3 structural artifacts from V28 (table, timeline, subsections).

---

## Topic A — SURPASS-2

### V29 says
> "The indirect comparison estimated significantly greater weight loss with tirzepatide 10 and 15 mg versus semaglutide 2 mg, with ETDs of -3.15 kg and -5.15 kg, respectively.[4]"

V29 mentions SURPASS-2 3 times in prose but cites the sema-2-mg aITC (T4), not the primary Frías NEJM ETDs (-0.15/-0.39/-0.45%). Same failure mode as V28.

### ChatGPT says
Full primary ETDs with CIs + P-values + open-label caveat.

### Gemini says
15 mg absolute HbA1c 2.46% from 8.28%; weight 12.4 kg vs 6.2 kg sema.

**Winner: ChatGPT > Gemini > V29**

---

## Topic B — SURPASS-CVOT

### V29 says
> "In the SURPASS-CVOT trial, which compared tirzepatide to dulaglutide in patients with type 2 diabetes and atherosclerotic cardiovascular disease, tirzepatide was noninferior to dulaglutide for a composite of cardiovascular death, myocardial infarction, or stroke.[43]"

**V29 MENTIONS SURPASS-CVOT** — first POLARIS cycle to do so. Uses correct noninferiority language. But missing HR (0.92), CI (0.83-1.01), P-values, and N (13,299). Cited via [43] which is NOT the Nicholls primary (M-53 says CVOT failed at retrieval).

### ChatGPT says
Full HR 0.92 / CI / P=0.003 NI + correct non-superiority framing.

### Gemini says
Full numeric frame + overstates with "definitively proven" language.

### Appraisal
V29 correctly frames NI but lacks the effect estimates with
uncertainty. Directionally correct; numerically thin.

**Winner: Gemini ≈ ChatGPT > V29** (V29 improved from complete absence in V28 to directionally correct mention — real progress, not yet competitive)

---

## Topic C — SURPASS-4

### V29 says
V29 does NOT mention SURPASS-4. Material omission — same as V28.
M-51 telemetry shows SURPASS-4 primary (ev_402) WAS inserted into
selected_rows and M-44 injected it into 4 sections' ev_ids, but
the LLM didn't cite it. Custody broke at generator prose.

### ChatGPT says
Dense: 52-wk ETDs + 104-wk durability + MACE-4 HR 0.74.

### Gemini says
15 mg primary efficacy + target attainment.

**Winner: ChatGPT >> Gemini > V29 (LOSE_BOTH)**

---

## Topic D — Mechanism

### V29 says (1,388-word section, 1.6x V28's 866)
> "Tirzepatide is primarily metabolized by proteolytic cleavage of the peptide backbone, beta-oxidation of its C20 fatty diacid moiety, and amide hydrolysis..."
> "bioavailability of approximately 80%... time to reach maximum plasma concentration (Tmax) ranges from 8 to 72 hours... mean terminal half-life of tirzepatide is approximately 5 days... 99% to plasma albumin..."
> "improvements in homeostatic model assessment indices (HOMA2-IR and HOMA2-B)..."
> MC4R knockout mouse data (NEW): tirzepatide 31.6% weight reduction vs semaglutide 19.7% vs retatrutide 24.1%.

**V29 Mechanism is now clearly COMPETITIVE with Gemini**:
- C20 fatty diacid (Gemini exclusive → now V29 too)
- Half-life 5 days (both)
- 99% albumin binding (V29 exclusive)
- Tmax 8-72h (V29 exclusive)
- HOMA2-IR / HOMA2-B (V29 exclusive — clinical biomarker)
- MC4R mouse data (V29 exclusive — mechanistic comparison)

Missing from V29: receptor-affinity asymmetry ("imbalanced dual
agonist"), Thomas clamp M-value 63%, biphasic insulin secretion.

### Gemini says
Full clamp data + receptor affinity framing.

### Appraisal
V29 now matches Gemini on PK depth + adds HOMA biomarker + MC4R
data. Still loses to Gemini on direct clamp-study extraction.

**Winner: V29 ≈ Gemini (tie); V29 beats ChatGPT (no dedicated mechanism)**

This is a **major upgrade from V28** (V28 was LOSE_BOTH on
Narrative depth; V29 is competitive).

---

## Topic E — Regulatory coverage

### V29 says
FDA (Mounjaro + Zepbound, boxed warning, full warnings, dosing);
EMA (pediatric ≥10, additional monitoring); HC (Mounjaro 2022
authorization, Product Monograph); NICE TA924 triple-therapy +
BMI ≥35 + ethnic-adjusted thresholds.

**V29 preserves the V28 4-jurisdiction win.** Same content
coverage as V28 in this section.

### ChatGPT says
FDA + EMA only.

### Gemini says
FDA + HC depth, no NICE/EMA breadth.

**Winner: V29 > Gemini > ChatGPT (BEAT_BOTH preserved)**

---

## Topic F — Contradictions and uncertainty

### V29 says
- 15 enumerated contradictions (+1 vs V28)
- Methods section: tier distribution T1=14%, T2=9%, T3=12%, T4=28%, T5=3%, T6=3%, T7=27%
- Limitations: "high-severity contradictions were detected on the effect of tirzepatide on body weight, with sources disagreeing on magnitude by over 5500% for the 5 mg dose"
- No explicit sponsorship / open-label disclosure

### ChatGPT says
Sponsor + open-label + comparator-evolution caveats.

**Winner: V29 > ChatGPT on enumeration; ChatGPT > V29 on clinical caveat. Tie.**

---

## 7-dimension head-to-head (claude view)

| Dim | V28 | **V29** | Delta |
|---|:-:|:-:|:-:|
| 1. Citations | LOSE_BOTH | **BEAT_ONE** | ↑ (47 entries incl. CVOT + SURMOUNT-2 mentions, but still no SURPASS-2/4 primaries; competitive with Gemini) |
| 2. Regulatory | BEAT_BOTH | BEAT_BOTH | preserved |
| 3. Jurisdictional | BEAT_BOTH | BEAT_BOTH | preserved |
| 4. Claim frames | LOSE_BOTH | LOSE_BOTH | = (still missing primary ETDs for SURPASS-2/4) |
| 5. Structural depth | LOSE_BOTH | **LOSE_BOTH** | = (V29 LOST M-42b + M-50 artifacts that V28 had — NET DOWNGRADE within a dim that was already LB) |
| 6. Contradictions | BEAT_BOTH | BEAT_BOTH | preserved (15 vs V28's 14) |
| 7. Narrative depth | LOSE_BOTH | **BEAT_ONE** | ↑ (Mechanism +60% words, C20/PK/HOMA/MC4R — now competitive with Gemini) |

**V29 aggregate**: 3 BEAT_BOTH + 2 BEAT_ONE + 2 LOSE_BOTH.

Compared to V28 (3 BB + 0 BO + 4 LB):
- **2 dims upgraded** LOSE_BOTH → BEAT_ONE (Dim 1 Citations, Dim 7 Narrative)
- **2 dims preserved** at LOSE_BOTH (Dim 4 Claim frames, Dim 5 Structural depth)
- **3 BEAT_BOTH preserved**

Net ≥BEAT_ONE count: 5 (V29) vs 3 (V28) = **+2 improvement**.

This is **dimensional IMPROVEMENT from V28** even though no dim
reached BEAT_BOTH that wasn't already there. V29 matches V27's
≥BEAT_ONE count (5) but has more BEAT_BOTH at the top (3 vs V27's 1).

---

## Honest V29 verdict

V29 is **progress, not arrival**. Not SHIPPABLE (needs 7/7), but
NOT a regression vs V28 on the net dimensional count.

### What V29 proved works

- **M-51 selector hard-reservation**: fires correctly (1 insertion
  for SURPASS-4 per telemetry)
- **M-44 generator injection**: fires correctly (12 injection-log
  entries across 4 sections for SURPASS-1/4/5)
- **M-53 custody telemetry**: precise diagnostic; pinpoints exactly
  which custody step broke per anchor
- **Strategy β direction**: narrative depth CAN lift (Mechanism
  +60% words, now competitive) when the architecture is right

### What V29 proved doesn't work (alone)

- **M-42b trial table + M-50 subsections**: both REGRESSED from
  V28 (empty in V29, ≥2 rows/3 subsections in V28). Prompt-level
  cause unclear — the machinery is the same. Likely driven by
  V29 evidence pool not having enough "primary_trial" rows that
  pass the strict `_m42e_detect_primary_for_anchor` filter
  (retrieval variance — V29 corpus is structurally different
  from V28's).
- **M-44 validator**: can't catch "injected ev_id but LLM didn't
  cite" failure mode because LLM doesn't name the trial by short-
  name in prose, so there's nothing for the same-sentence check
  to enforce. The validator requires the TRIAL NAME to be
  present; the LLM just avoids both.

### What V29 surfaces as the next bottleneck

Custody telemetry shows the REAL V30 scope splits in two:

1. **Retrieval determinism/coverage (defect A)**: M-48 variant
   queries hit different results cycle-to-cycle. 7/11 anchors
   failed at retrieval in V29; different subset of 7/11 failed in
   V28. Needs deterministic retrieval strategy or fallback when
   primary doesn't land (e.g. direct DOI lookup via CrossRef API).

2. **Forced-citation contract (defect B)**: Even when M-51 + M-44
   put the primary in the section's evidence subset, the LLM
   doesn't cite it. Needs prompt-level enforcement like "when
   evidence ev_402 is SURPASS-4's primary publication and
   configured as a pivotal trial, you MUST include a sentence
   naming SURPASS-4 and citing [ev_402]". Currently the prompt
   only hints at primary-trial citation; V30 needs hard contract.

Strategy β V30 was originally "two-stage generator" — this now
splits: V30a (retrieval determinism) + V30b (forced-citation
contract).

---

## Cross-review with Codex pending

Codex parallel audit at `outputs/codex_findings/v29_deep_content_audit/findings.md`. V2 step 3 cross-review next.
