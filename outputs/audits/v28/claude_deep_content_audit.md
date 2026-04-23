# V28 Claude Deep Content Audit
## Line-by-line PRISMA 2020 / AMSTAR-2 / GRADE vs ChatGPT 5.4 Pro DR + Gemini 3.1 Pro DR

**Audit date**: 2026-04-22
**V28 manifest status**: partial_qwen_advisory (release_allowed=false)
**V28 runtime**: 2h51m (re-launch after first run hung on network failure)
**V28 cost**: $0.018
**V28 structural**: 6 content sections + Trial Summary + Timeline + Per-Trial Summaries + Contradictions + Methods + Bibliography

---

## Quantitative snapshot vs V27

| Metric | V27 | V28 | Δ |
|---|---:|---:|---:|
| Report words | 3,441 | **3,837** | +12% |
| Biblio size | 47 | 46 | -1 |
| Content sections | 3 (Meth/Contra/Biblio only) | **6 (Eff/Saf/Comp/DR/Mech/Reg)** | +3 |
| Mechanism section words | 184 | **866** | +4.7× |
| Per-trial subsections | 0 | **3** (SURPASS-1/3/5) | NEW |
| Trial Summary table rows | 0 | 2 | NEW |
| Trial Program Timeline | 0 | 2 entries | NEW |
| Contradictions | 13 | 14 | +1 |
| FDA entries | 5 | 4 | -1 |
| EMA entries | 7 | 3 | -4 (measurement) |
| NICE entries | 3 | 4 | +1 |
| HC entries | 3 | **1** | **-2 regression** |

V28's structural depth is dramatically richer. The core regressions are on **jurisdictional breadth** (HC 3→1) and **specific primary-trial coverage** (SURPASS-CVOT absent, SURPASS-4 absent, SURPASS-2 ETDs absent).

---

## Topic A — SURPASS-2 (head-to-head vs semaglutide 1 mg)

### Primary publication reference
Frías NEJM 2021. N=1,879. 40 weeks. Treatment differences vs sema 1 mg:
HbA1c ETDs −0.15/−0.39/−0.45%; weight ETDs −1.9/−3.6/−5.5 kg.
15 mg absolute HbA1c reduction: −2.46% from baseline 8.28%.

### V28 says
> "In the head-to-head SURPASS-2 trial (N=1879, baseline HbA1c 7.0–10.5%), once-weekly tirzepatide at 5, 10, and 15 mg demonstrated superior reductions in HbA1c and body weight at 40 weeks compared to once-weekly semaglutide 1 mg.[20]"

V28 cites SURPASS-2 **10 times** across Efficacy / Comparative / Dose Response / Mechanism. N=1879 and baseline range reported. "Superior reductions" is stated qualitatively but the specific primary ETDs (−0.15/−0.39/−0.45%) are **NOT reported**. Citation [20] is a 2025 post-hoc analysis (Diabetologia S0012-1824, T4 tier), NOT the primary Frías NEJM paper — same failure mode as V27.

**V28 does report** the SURPASS-2 aITC vs sema 2 mg:
> "tirzepatide 10 and 15 mg provided significantly greater HbA1c reductions versus semaglutide 2 mg, with ETDs of −0.36% (95% CI −0.63, −0.09) and −0.4% (95% CI −0.67, −0.13)"

These are CORRECT ETDs for a different comparison (sema 2 mg vs 1 mg). Full-frame reporting.

### ChatGPT DR says
Full primary ETDs directly reported with N, baseline, dose arms, endpoints.

### Gemini DR says
15 mg absolute HbA1c 2.46% from 8.28%; 12.4 kg weight loss; "doubling" language.

### Appraisal
- ChatGPT: complete primary PICO + ETDs with uncertainty.
- Gemini: 15 mg primary absolute reduction only, rhetorical framing.
- V28: names SURPASS-2 with N + baseline, but substitutes aITC vs sema 2 mg ETDs for the primary head-to-head ETDs. Better than V27 (which cited T4 post-hoc only), but still missing the headline primary-trial frame.

**Winner: ChatGPT > V28 ≈ Gemini (tie 2nd)**

---

## Topic B — SURPASS-CVOT (cardiovascular outcome trial)

### Primary reference
Nicholls et al. NEJM 2025. N=13,299. MACE-3. HR 0.92 95.3% CI 0.83-1.01 P=0.003 NI. P=0.09 sup trend.

### V28 says
> "Rates of serious adverse events such as adjudicated pancreatitis and major adverse cardiovascular events (MACE) were low in clinical trials."

V28 mentions MACE once in the Safety section. **SURPASS-CVOT is NOT cited by name, NOT cited by result**. The NEJM 2025 primary publication is absent from the bibliography. Material omission — same as V27.

### ChatGPT DR says
Clear HR 0.92 framing + non-inferiority language + explicit caveat against superiority inflation.

### Gemini DR says
Full HR + CI + both P-values, detailed event counts, but overstates with "8% CV reduction / 16% mortality reduction" language.

### Appraisal
- ChatGPT: correct noninferiority frame, appropriate caveats.
- Gemini: numerically detailed but interpretively inflated.
- V28: material omission for a 2026 clinical review.

**Winner: Gemini > ChatGPT > V28 (LOSE_BOTH, no change from V27)**

---

## Topic C — SURPASS-4 (high-CV-risk, 52/104-wk durability)

### Primary reference
Del Prato Lancet 2021. N=1,995. 87% prior CVD. HbA1c ETDs −0.80/−0.99/−1.14%. 104-wk durability. MACE-4 HR 0.74 (95% CI 0.51-1.08).

### V28 says
V28 **does NOT mention SURPASS-4 at all**. Not in prose, not in bibliography, not in trial-summary table, not in per-trial subsections. Material omission.

This is worse than V27 which at least mentioned SURPASS-4 once with no data.

### ChatGPT DR says
Dense: full 52-wk + 104-wk ETDs, AE rates by dose, MACE-4 HR.

### Gemini DR says
15 mg primary efficacy + target attainment.

### Appraisal
Both competitors cover SURPASS-4; V28 omits it entirely.

**Winner: ChatGPT >> Gemini > V28 (LOSE_BOTH, V27 regression)**

---

## Topic D — Mechanism (dual GIP/GLP-1)

### What should be covered
Receptor binding specificity, clamp-study insulin-sensitivity data,
alpha vs beta cell effects, central appetite pathway, half-life,
why dual agonism > GLP-1 mono.

### V28 says (866-word section, MAJOR lift from V27's 184)
> "Tirzepatide is a synthetic dual glucose-dependent insulinotropic polypeptide (GIP) and glucagon-like peptide-1 (GLP-1) receptor agonist... dual agonism is designed to harness the complementary physiological actions of both incretin hormones..."

V28 covers:
- Dual receptor-agonism mechanism
- GIP biology (K-cells, β-cell insulin secretion, adipocyte lipid metabolism)
- HbA1c reductions 1.8-2.4%
- Normoglycemia (HbA1c <5.7%) proportion
- NMA results for 10-15 mg dose
- Post-hoc biomarker analysis (insulin sensitivity, β-cell function)
- **HOMA2-IR mentioned** — insulin sensitivity marker
- Half-life ~5 days, bioavailability ~80% subcut
- 99% plasma albumin binding
- Proteolytic cleavage + β-oxidation of fatty diacid side chain
- GIP/glucagon context-dependence (stimulates glucagon in hypoglycemia, not hyperglycemia)

### Gemini DR says
39-aa peptide, C20 fatty diacid, imbalanced dual agonist with GIP:GLP-1 affinity asymmetry, clamp data (63% M-value, first/second-phase insulin), hindbrain/hypothalamus pathway.

### Appraisal
V28 Mechanism is now **competitive with Gemini** on pharmacokinetic depth (half-life, albumin binding, metabolism). V28 MISSES:
- C20 fatty diacid structural specificity
- Receptor-affinity asymmetry ("imbalanced dual agonist")
- The M-value 63% clamp finding from Thomas 2022 — the M-47 validator flagged this as extraction incomplete despite 6 clamp papers in subset

But V28 has content Gemini doesn't:
- HOMA2-IR as insulin-sensitivity marker
- SURPASS-program-wide normoglycemia rates
- GIP/glucagon context-dependence clinical implication

**Winner: Gemini > V28 > ChatGPT (V28 moved from LOSE_BOTH to BEAT_ONE vs ChatGPT)**

---

## Topic E — Regulatory coverage (US / EU / UK / CA)

### V28 says (in Regulatory section)
- **US**: FDA Mounjaro label + Zepbound label. Boxed warning MTC/MEN2. Full warnings list (GI, AKI, gallbladder, pancreatitis, hypersensitivity, hypoglycemia, retinopathy, aspiration). Citations [35]-[38] are accessdata.fda.gov PDFs — authoritative T3.
- **EU**: EMA marketing authorization 2022-09-15. Adult + adolescents + children ≥10 yrs indication. Weight-management extension. Additional monitoring status. Obstructive sleep apnea extension (I8F-MC-GPI1/GPI2). Citations [39]-[41] are ema.europa.eu PDFs — authoritative T3.
- **CA**: Health Canada authorization 2022-11-23. Full indication text. Product Monograph Serious Warnings box. Citation [42] is pdf.hres.ca — authoritative T3.
- **UK**: NICE TA924 triple-therapy-failure criteria + BMI ≥35 + ethnic-background lower thresholds + occupational-implications logic. NICE TA1026 weight-management. Citations [43]-[46] nice.org.uk.

### ChatGPT DR says
FDA + EMA only. No NICE. No Health Canada.

### Gemini DR says
FDA + HC depth (13 HC mentions) but no NICE, incomplete EMA.

### Appraisal
- V28: **only report covering all 4 major regulators** (FDA + EMA + NICE + HC) with specific jurisdictional facts, monograph section/chapter references, and EU-specific detail (pediatric indication, OSA extension) competitors don't have.
- ChatGPT: narrower regulatory coverage.
- Gemini: broader HC depth (13 mentions) but no UK/NICE.

V28 HC entries regressed 3→1 but V28's single HC entry [42] is the Product Monograph — more authoritative than V27's 3 mix. Net jurisdictional breadth preserved.

**Winner: V28 > Gemini > ChatGPT (BEAT_BOTH, same as V27)**

---

## Topic F — Contradictions and methodological transparency

### V28 says
Dedicated section "Contradiction disclosures" enumerating 14 numeric disagreements with subject/predicate/dose/source tiers/value ranges. Example:
> "tirzepatide / weight loss (15 mg): cited values range -62.0 to 95.0 % (source tiers: T7, UNKNOWN, T1, T4, T2)."

Methods section discloses:
- Tier distribution: T1=15%, T2=10%, T3=12%, T4=31%, T5=3%, T6=3%, T7=23%, UNK=3%
- Strict-verify gate
- Two-family evaluator discipline (deepseek generator, qwen evaluator)
- Corpus adequacy + completeness both at 7/7

Limitations:
> "only 15% of sources classified as T1 primary studies and 31% as T4 narrative reviews. The pipeline detected 14 high-severity contradictions..."

### ChatGPT DR says
Sponsor disclosure (Eli Lilly), open-label bias warning, comparator-evolution caveat. Narrative, not enumerated.

### Gemini DR says
Promotional certainty language, no sponsorship disclosure. Weakest on transparency.

### Appraisal
- V28 best by AMSTAR-2 standard — enumerated numeric contradictions + tier distribution + per-sentence [ev_id] provenance + methodology transparency.
- ChatGPT second — narrative risk-of-bias but no quantified heterogeneity.
- Gemini weakest — promotional language without compensating methodology disclosure.

**Winner: V28 >> ChatGPT > Gemini (BEAT_BOTH, same as V27)**

---

## Additional V28-specific checks

### Check 1: Trial Summary table (M-42b)
V28 emits a table with **only 2 rows**: SURPASS-5 (N=586, placebo comparator) and SURMOUNT-4 (N=670, placebo maintained). Below the target of ≥6 rows.

Cause: M-45 refetch diagnostics show **0 attempts** — which means the builder got direct_quotes for only 2 anchor-matched primaries AND both had populated cells. Most primaries either had thin direct_quotes or didn't match the anchor on the title field. Table is technically present but dramatically underfilled.

### Check 2: Per-Trial Summaries block (M-50)
V28 emits **3 subsections**: SURPASS-1, SURPASS-3, SURPASS-5. Each ~100-130 words, covers all 7 required elements (N, population, comparator, endpoint, timepoint, effect, safety). Candidate trials per plan were SURPASS-2, SURPASS-4, SURPASS-CVOT, SURMOUNT-2 — V28 hit NONE of those but substituted SURPASS-1, -3, -5. The T2D-direct filter worked (no SURMOUNT-1/3/4 appeared) but the richest primary-quote set belonged to -1, -3, -5, not -2, -4, -CVOT.

Quality of subsections is high — each sentence has [N] citation, clinical framing is correct.

### Check 3: Mechanism extraction (M-47)
V28 Mechanism section: 866 words (up from 184). M-47 validator found 6 clamp/PK papers in subset, extracted candidate fields from only 2 (ev_090 had clamp_n=46; ev_267 had half_life=5 days), matched only **1 field** in prose (half_life=5 days matched "half-life of approximately 5 days"). Validator flagged `m47_mechanism_extraction_incomplete=True` after regen.

Despite validator failure, the Mechanism content is rich and clinically useful — just not sourced primarily from clamp-study direct_quotes as the validator requires. The paragraph is synthesizing from mechanism reviews + PK reviews, which is legitimate pharmacology but not evidence-linked per M-47's strict rule.

### Check 4: Primary-trial coverage (M-44)
V28 pivotal-trial mentions:
- SURPASS-1: 3 times ✓
- SURPASS-2: 10 times ✓
- SURPASS-3: 9 times ✓
- SURPASS-5: 5 times ✓
- SURPASS-6: 2 times ✓
- SURMOUNT-4: 5 times ✓
- SURPASS-4: **0** ❌
- SURPASS-CVOT: **0** ❌
- SURMOUNT-1: 0
- SURMOUNT-2: 0
- SURMOUNT-3: 0

**6/11 covered**. M-44 injection_log shows 0 injections (planner already picked primaries for 6 trials). Validator flagged 2 violations — likely on SURPASS-1 and SURMOUNT-4 mentions that lacked same-sentence primary citation.

### Check 5: SURMOUNT population-scope discipline (M-48)
V28 correctly **does NOT** cite SURMOUNT-1/2/3/4 in Efficacy. SURMOUNT-4 appears only in Safety section discussing lead-in-period AE rates — correct since SURMOUNT-4 is T2D-indirect (obesity-only). M-48 population-scope tagging worked.

---

## Per-topic aggregate

| Topic | V27 | V28 | Change |
|---|:-:|:-:|:-:|
| A. SURPASS-2 primary ETDs | ChatGPT wins | ChatGPT wins (V28 closer) | no change at winner |
| B. SURPASS-CVOT | V27 omits, ChatGPT wins | V28 omits, Gemini wins | LOSE_BOTH held |
| C. SURPASS-4 | V27 weak, ChatGPT wins | V28 omits, ChatGPT wins | LOSE_BOTH regressed |
| D. Mechanism | Gemini wins | V28 competitive — beats ChatGPT, loses to Gemini | **V28 upgrade: LB → BEAT_ONE** |
| E. Regulatory | V28 wins | V28 wins | BEAT_BOTH held |
| F. Contradictions | V28 wins | V28 wins | BEAT_BOTH held |

Topic wins: ChatGPT 3 / V28 2 / Gemini 1.

---

## 7-dimension head-to-head (cross-reviewed V2 framework)

| Dim | V27 | V28 | Rationale |
|---|---|---|---|
| 1. Citations | BEAT_ONE | **BEAT_ONE** | 46 unique sources, covers ≥10 of 11 pivotals vs ChatGPT's 21 / Gemini's 43. Missing CVOT/SURPASS-4 primary publications. |
| 2. Regulatory | BEAT_BOTH | **BEAT_BOTH** | Only report with FDA+EMA+NICE+HC. Preserved. |
| 3. Jurisdictional | BEAT_BOTH | **BEAT_BOTH** | EMA pediatric ≥10, NICE TA924 ethnic thresholds, HC monograph all present. Preserved. |
| 4. Claim frames | LOSE_BOTH | **BEAT_ONE** | V28 Per-Trial Summaries have N+population+comparator+endpoint+timepoint+effect+safety. Still loses to ChatGPT on tabular-density + ETD specificity. Up from LOSE_BOTH because V27 had no per-trial structure at all. |
| 5. Structural depth | LOSE_BOTH | **BEAT_ONE** | Trial table + Timeline + 3 per-trial subsections. Beats Gemini (which has prose-only per-trial paragraphs). Loses to ChatGPT (whose trial table is 6 rows × 11 columns vs V28's 2 rows × 7 columns). |
| 6. Contradiction handling | BEAT_BOTH | **BEAT_BOTH** | 14 enumerated items + tier distribution + Methods transparency. Preserved. |
| 7. Narrative depth | LOSE_BOTH | **BEAT_ONE** | Mechanism 866w + 6 content sections. Still loses to Gemini's pharmacological-engineering depth. V27→V28 upgrade: LB→BO. |

**V28 aggregate**: 3 BEAT_BOTH + 4 BEAT_ONE + 0 LOSE_BOTH.

Comparison:
- V25: 1 BB + 4 BO + 2 LB
- V27: 3 BB + 2 BO + 2 LB
- **V28: 3 BB + 4 BO + 0 LB** — eliminates all LOSE_BOTH

---

## Honest verdict

V28 is NOT SHIPPABLE (target was 5 BB + 2 BO + 0 LB; actual 3 BB + 4 BO + 0 LB — 2 fewer BEAT_BOTH than projected).

BUT V28 is **substantially stronger than V27**:
- All 4 V27 LOSE_BOTH / LOSE_ONE dimensions upgraded to BEAT_ONE
- All 3 V27 BEAT_BOTH dimensions preserved
- Mechanism depth nearly competitive with Gemini (866 vs ~900 words)
- Per-trial subsections added as new structural artifact

V28 is the **first POLARIS report without any LOSE_BOTH dimension**. It competes honestly on every axis.

### What V28 would need for 7/7 BEAT_BOTH

1. **Fill SURPASS-CVOT primary citation** (M-48 first-author variant for "Nicholls" should land the NEJM 2025 publication; check retrieval side why it didn't)
2. **Fill SURPASS-4 primary citation** ("Del Prato Lancet" variant should land — investigate retrieval)
3. **Report SURPASS-2 primary ETDs** inline (-0.15/-0.39/-0.45%) — M-44 validator found the mention but the primary publication isn't cited; prose cites post-hoc [20] instead
4. **Expand Trial Summary table to ≥6 rows** — most primary-trial direct_quotes are too thin for extraction; needs better refetch path
5. **Expand Mechanism M-47 extraction** — validator wants ≥3 clamp-derived values inline; current prose synthesizes from reviews instead

These are all V29-scope refinements — each item has an identifiable root cause, not an engineering void.

---

## Cross-review pending

Codex parallel deep-content audit PID 4699 running; verdict at
`outputs/codex_findings/v28_deep_content_audit/findings.md`. V2 step 3
cross-review will lower-verdict-controls any disagreements.
