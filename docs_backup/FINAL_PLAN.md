# THE FINAL PLAN — adjudicated after 6 adversarial lenses. This is the executable truth.

## THE CALL

**DELETE K1 AND PATCH THE LEDGER. TODAY. BEFORE ANYTHING ELSE.**

K1 is a kill rule that FIRES RIGHT NOW. It says: "if `reference_total` >= 7.5, the analytic ceiling is <= 0.571 and both plans' gates are unreachable — re-target." Measured against our own article, **R = 8.033**. K1 fires, declares a ceiling of **0.5545** — and **cellcog scored 0.5603 today, on the same judge, the same task, the same reference.** The ceiling that would have halted this project is already exceeded by a number sitting on our disk.

The reason nobody saw it: **the harness computes `target_total` and `reference_total` at `deepresearch_bench_race.py:158` and then throws both away.** Six lines of destruction hid the single fact that invalidates the project's most sobering kill rule.

So, in order, on day zero:
1. **Patch `final_result` to persist `criteria_scores[]`, `target_total`, `reference_total`.** 6 lines, $0.
2. **Strike K1.** Replace the ceiling with `10 / (10 + R_at_the_target's_operating_point)`. Measured, that is **0.5802 — and both gates are reachable.**
3. **Re-run `judge_feedback.py` at k=5 across POLARIS / bodhi / cellcog, logging R every call** (~$3). This confirms dR/dT, prices every lever ~20% higher than the R-fixed model, and turns the judge from a scoreboard into an instrument.

Then, the same day, ship the **attribution-channel fix** — because our 1.5/10 on the highest-headroom criterion on the board is not a corpus defect, it is a **channel defect**, and it costs a day: the RACE cleaner deletes our 345 `[n]` markers and our reference list before the judge reads a word, leaving 3 journal names and 11 consultancy names visible. **We are being graded on a corpus we did not submit.**



## THE PLAN

# THE FINAL PLAN
### Everything that survived adversarial re-derivation. Every number below is measured from the judge's own per-criterion output, recomputed through the harness's own weighting code.

---

## THE INSTRUMENT, RESTATED (this is what changed)

```
                T        R      overall     T/R
POLARIS      6.345    8.033     0.4413     0.790
BODHI        8.930    7.545     0.5420     1.184
CELLCOG      9.384    7.363     0.5603     1.275     <-- MEASURED, not estimated
```
**R is not a constant.** Same fixed reference, three calls: **8.033 / 7.545 / 7.363**. The judge marks the *reference* DOWN as the target gets better. dR/dT = **-0.21**.
- Proof needing no regression: R fixed at 8.033 makes cellcog's 0.5603 require **T = 10.24/10**. Impossible. cellcog scored it. Therefore R fell.
- **Ceiling = 0.5802**, not 0.5545. **K1 is dead. Both gates are reachable.**
- **Every lever is worth ~20% more than any plan on this table booked it at.**

---

## PHASE 0 — THE INSTRUMENT (Day 0, ~$4, blocks everything)

**0.1 E1 — THE LEDGER PATCH.** Persist `criteria_scores[]`, `target_total`, `reference_total`. 6 lines, $0. *This is the bug that hid the R-drag.*
**0.2 STRIKE K1.** Rewrite the ceiling as `10/(10+R_at_operating_point)` = **0.5802**.
**0.3 R AT k=5** across all three targets (~$3). Confirms the drag magnitude.
**0.4 E6 — PER-CRITERION SD** on the 5 banked `noise_r10_*` artifacts ($0.55). **No criterion is a deficit until its own SD is known.** If SD >= the deficits we intend to chase, we steer by the aggregate and by the judge's written analysis — not by the deficit map.

---

## PHASE 1 — THE FIVE THINGS THE JUDGE SAYS IT PAYS FOR
### (measured, in score units, R-drag applied)

| # | lever | criterion | w | us | cell | Δ |
|---|---|---|---|---|---|---|
| 1 | **reconciling conflicts** | Critical Synthesis & Nuanced Evaluation | .0800 | 5.8 | 9.6 | **+0.0116** |
| 2 | **declared evidence constraint** | Exclusive Citation of High-Quality Journal Articles | .0375 | **1.5** | 8.0 | **+0.0093** |
| 3 | **named tagged syntheses** | Emergent Themes / Theoretical Linkages | .0640 | 6.4 | 9.8 | **+0.0083** |
| 4 | **evidence-TYPE diversity** | Depth & Representativeness of Literature | .0435 | 5.0 | 9.5 | **+0.0075** |
| 5 | **the summary table** | *D1: Clarity of Data* — **a READABILITY criterion** | .0140 | 4.8 | 9.2 | +0.0024 |

> **Correction to the brief:** "+5.0" is RAW CRITERION POINTS, not score. In score units the declared constraint is **+0.0093** — real, cheap, clears the k=5 resolvable effect alone, but it is **#2, not #1**. And the "sectoral table" praise lands on **D1 (w=0.0140)**, so the table is part of the shape bundle, not a fifth content lever.

### 1.1 THE ATTRIBUTION CHANNEL — do this FIRST. It is the mechanism behind lever #2, and it is free.
**MEASURED.** RACE's `clean_prompt.py` deletes *reference lists, `[n]` markers and footnotes* from **every** submission before the judge reads it. Our report:
```
345  [n] markers          -> DELETED
  1  References section   -> DELETED
 10  in-prose year-parens -> survive
  3  journal names in prose   |  11 consultancy names in prose
     (Journal of x1, Nature x2)  (WEF x2, Goldman Sachs x4, PwC, Deloitte, Gartner, IBM, IDC)
```
The judge's verbatim complaint on the 1.5/10: *"It lacks a formal reference list and cites... the World Economic Forum, International Data Corporation, PwC, IBM, Deloitte, Gartner... Goldman Sachs."* **It named exactly the eleven sources we leave visible.** It is not hallucinating — it is reading precisely what survives the cleaner.

**Our 1.5/10 is a CHANNEL defect before it is a corpus defect. We are graded on a corpus we did not submit.**

**FIX:** every citable claim carries **author + year + journal INSIDE the sentence** (cellcog's measured narrative form). Delete the `[n]` markers. Keep the reference list — it costs nothing and is deleted anyway — but **never rely on it**.
**K5 COUNTER:** post-cleaner count of surviving (author, year, venue) triples. Today ~10. Target >=100.

### 1.2 MAKE THE CONSTRAINT TRUE, THEN DECLARE IT — in that order.
This is where the synthesis and the what-actually-wins lens collide, and **both are half right**:
- The lens is right: the declaration is **absent, free, and worth +0.0093-0.0110.** Grep the synthesis's 412 lines for "evidence constraint" — **zero hits.** Its only engagement is to **delete** it.
- The synthesis is right: the current hardcoded abstract ("draws exclusively on peer-reviewed journal articles") is a **fabricated compliance claim** and must die.
- **RESOLUTION — read the judge's actual words. It is not paying for the sentence; it is paying for the sentence BEING TRUE.** Bodhi gets 8.2 for *"explicitly states an evidence constraint **and mostly discusses recognizable peer-reviewed journal literature**... it generally **honors** the constraint."*

**So, in strict order:**
- **(a) TURN ON THE HARD GATE.** `PG_SCOPE_TOPIC_GATE_HARD_DROP=1`, plus the venue gate. **Scope is a WEIGHT on the research pool and a HARD GATE on the CITABLE pool.** Non-journal sources may inform; they may never be cited.
- **(b) RENDER `brief.scope` AS THE OPENING SCOPE/METHODS BLOCK**, with **every count read from the evidence ledger in code, never emitted by the LLM.** It is then honest **by construction** — the numbers cannot be fabricated because the model never writes them.
- **(c) FLIP THE FRAME ON THE TIER CENSUS.** Keep every count. Publish it as **CONSTRAINT HONORED**, not **DEFICIT CONFESSED**. Bodhi's exact move: *"Where the record contains only bibliographic indications without extractable results, I do not use it or explicitly limit claims."* Same information, same integrity, +6.7 raw points. Our current sentence — *"the corpus skews heavily toward secondary sources... 15% UNKNOWN tier"* — is the losing frame, and the synthesis's integrity regime **mandates it.** The honesty is not the problem. The rhetoric of honesty is.
- **(d) GATE (must re-verify):** measure what fraction of the coverage matrix is fillable **from journals alone**. If it is not fillable, **scope the declaration to what is true.** *A declaration we cannot honor is the fabrication we are trying to kill.*
- **(e)** Add it to the adversarial suite as a **MUST-ADMIT** case, so the integrity floor cannot delete it again.

### 1.3 EVIDENCE-TYPE DIVERSITY (+0.0075)
The plan's WEIGHT function (`relevance x venue x citations x recency x groundability`) has **no study-design term**, and the coverage matrix's cells are topical. The judge pays for the **mix of evidence KINDS**: *"seminal theory, causal empirical studies, meta-analyses, field experiments, administrative data, qualitative labor-process work."*
**FIX:** a second axis on the coverage matrix — `{seminal theory, causal/quasi-experimental, meta-analysis, field experiment, administrative data, qualitative}` — derived per domain. WEIGHT gains a design-diversity term. STOP requires the design mix filled, not just the topical cells. **A re-query, not a new subsystem.**

### 1.4 RECONCILING CONFLICTS (+0.0116 — the single heaviest)
Fable's **CONTRADICTION INDEX** survives and is the best-aimed component in either foundation plan. Plus the **CORPUS CENSUS**, computed in code: *"Across the 41 divergent pairs among the 137 works retrieved, 29 divide along the unit at which outcomes are measured."*
> **CAUTION:** the census is REJECTED by the contract's own rule 4 (`synthesis_carries_a_digit`), and the proposed `COVERAGE_GAP` exemption **does not reach it**. **Add a CENSUS operation with the count computed in code**, or the plan's own flagship thesis sentence stays banned by the plan's own gate.

### 1.5 NAMED TAGGED SYNTHESES (+0.0083)
cellcog scores **9.8/10** for *"its eight tagged syntheses... show genuine synthesis beyond summary."* Insight sold in **named, counted, first-person units** with a graded epistemic tag. Pure composition. The cheapest content lever on the board.

---

## PHASE 2 — SHAPE, RE-PRICED (parallel, ~1 day)

**DEAD (LENS 1, well-powered nulls):** sections (+0.0020/SD) — **"add 30+ subsections" is DEAD**, and the H3 r=+0.519 everyone read as a mandate is 100% system identity. Length is a **FLOOR (~5,000w)**, saturating ~8,000w — **we are at 9,194, past the knee.** Sol's 13,500-16,500w and Fable's 15,000-16,000w targets are **DELETED**.

**ALIVE — and the synthesis's "book it at ZERO" is refuted by the judge in writing:** the 7 readability criteria taken to cellcog's level = **+0.0270 with drag = 2.9x the k=5 resolvable effect, 23% of the gap.**
- S2 = **3.5, our worst criterion of 25**: *"extremely long paragraphs... a fragmented narrative"*
- L1 = 4.5: *"dense, repetitive, and awkward"* · F1 = 5.5: *"very long paragraphs, lack of tables, absence of a bibliography"*
- Our median paragraph is **677 words — the 99.7th percentile of 898 articles.** E0's null has **no support there.**
- E0 is computed on **RAW** submissions; the judge scores **CLEANED** text. The regression that licensed the zero is structurally blind to the only channel that reaches the grader.

**SO:** ~100w paragraphs, real transitions, tables, in-prose attribution. **Book it at +0.027**, ship the mechanism counter (post-cleaner median paragraph words), and let **E4 (k=10 paired, content held fixed) SIZE it — not decide whether it exists.**

---

## PHASE 3 — FAITHFULNESS: FABRICATION IMPOSSIBLE, SCHOLARLY INFERENCE POSSIBLE

**The synthesis's invariant is FALSE.** *"Fabrication... is never the assertion of a RELATION"* (line 163) — sign inversion is a relation-fabrication with no new particular, and line 163 contradicts the synthesis's own line 191. **And line 163 is the sentence that gets operationalised.**

### THE INVARIANT THAT REPLACES IT
> **EVERY SENTENCE IS EITHER ATTRIBUTED OR OWNED.**
> - **ATTRIBUTED** — names a source. Must be **ENTAILED by that source's own VERBATIM SPAN** (not its LLM-composed claim). Carries the numbers, years, N's. **Fabrication is banned absolutely here.**
> - **OWNED** — reviewer's voice, first person. **MAY NOT name a source.** MAY NOT carry a particular absent from the ledger. Must be **NON-CONTRADICTED** by its premises — and is **EXPLICITLY PERMITTED TO BE NON-ENTAILED, because that is what insight IS.**
>
> **Fabrication = an ATTRIBUTED sentence its source does not entail.**
> **Insight = an OWNED sentence its premises do not entail.**
> **Same logical shape. Distinguished by VOICE, not by entailment.**

**WHY.** Measured: the two classes occupy the SAME CELL under entailment. Reject on NEUTRAL and you delete **76/78 (97%)** of the exact prose the judge scored **9.8/10** — including cellcog's flagship *"We propose, as analytical synthesis, that informality functions as the Global South's institutional analogue..."*, which is non-entailed **by design**. cellcog is paid for *"connecting findings that no single paper contains."* **No entailment threshold separates insight from mechanism-transplant. Voice does.** cellcog already does exactly this and is paid 9.8/10 for it.

### ORDERED, EXECUTABLE
1. **FIX THE INPUT BEFORE THE GATE.** `mechanisms` is copied raw with no span check. **MEASURED: 42/81 (52%) absent from their own span; 35/81 (43%) in NEITHER span nor claim — pure invention.** *"Task displacement"* is bound to **Bresnahan et al. (2002)**, whose span never says it — a real mechanism from a real paper, bound to the wrong paper, **already shipping.** → **Every mechanism carries a char offset, or is DROPPED.**
2. **HAND THE WRITER THE SPAN, NOT THE CLAIM.** The composer shows the writer the LLM's paraphrase (explicitly *"in your words"*) + *"mechanism stated by the paper"* — and **never shows the span**. Any gate whose ground truth is the *claim* would **CERTIFY** fabrication, not catch it.
3. **MECHANISM TRANSPLANT IS FIXABLE IN CODE TODAY, NO LLM.** The contract unions mechanisms across ALL cited premises, so one card's mechanism licenses causal prose about a *different* card's finding. → typed edge: `mechanism_premise_id` **==** `effect_premise_id`. Deterministic set membership.
4. **REJECT ON CONTRADICTED, NOT ON NEUTRAL**, in the synthesis lane. NEUTRAL stays **unchanged in the evidence lane.**
5. **DELETE from the synthesis lane:** `VERDICT_VOCAB` (a 17-item hardcoded idiom list that alone deletes 92% of the 9.8/10 prose), `UNIVERSAL` (bans "none" -> makes COVERAGE_GAP unpassable), `FORECAST` (bans "will" -> makes the insight rubric's own foresight criterion, w=0.048, literally unwritable), `Rule 10` (punishes abstraction — the thing insight pays for).
6. **ADD A CENSUS OPERATION** with the count computed in code.
7. **THE POISONED-CARD CI TEST — FIRST, BEFORE ONE GATE IS RELAXED.** `validate()`'s **only call site in the entire repo is its own `self_test()`**, fed its own hardcoded fixture, printing green. That is *exactly* the failure the synthesis warns against — the warning is already true of the code it warns about. **The test must FAIL when the gate is bypassed.**
8. **REWRITE K6.** Replace "zero false admissions AND zero false rejections" (a contradiction) with a **measured two-sided error report**: false-admission rate on the adversarial suite (sign inversion, mechanism transplant, subsumption inversion = MUST-REJECT) AND **false-rejection rate on cellcog's entire 9.8/10 Section 5 — all 78 sentences — as a MUST-ADMIT fixture.**
9. **ACCEPT AND PRICE THE RESIDUE.** Subsumption/relational inversion is **not deterministically checkable.** Its containment is the OWNED-voice marking plus the corpus census — not another gate. Say so out loud.
10. **THE HARD ABORT STANDS.** One fabricated particular on a shipped page burns the artifact regardless of score. **A 0.60 obtained by fabricating is a 0.00.**

---

## PHASE 4 — GENERALITY: UNMEASURED, AND HOW WE MEASURE IT CHEAPLY

**SAY IT PLAINLY: generality is UNMEASURED, not disproven.**
- **"0.263" IS NOT A GENERALITY NUMBER.** All five `polaris_vm_*` runs are **ABORTS** (`four_role_held` / `report_redaction_failed` -> `_ARTIFACT_KIND_DEGRADED`; our own code calls it "a run-level / infra failure"), generated **five weeks stale**, merely scored on 07-11. **The pipeline REFUSED to ship them.** And the overfit argument collapses on its own data: `polaris_vm_t72` IS a task-72 run and scores **0.2530 — fourth of five, BELOW the mean of the four "unseen" tasks (0.2655). Task-72 advantage = -0.0125, NEGATIVE.**
- **VERIFIED: 38 scored runs since 07-12. ALL task 72. Zero elsewhere.**

**THE CHEAP MEASUREMENT, in cost order:**
- **4.1 (~$5) RUBRIC RECALL ON ALL 100 TASKS.** RACE ships the judge's real criteria for all 100 tasks. Run RACE's own generators (k=3, union) on all 100 prompts; score weighted rubric-mass recall + dimension-weight L1 against `criteria.jsonl`. **The only generality claim in this plan that is a MEASUREMENT rather than an argument, and it is executable before anything downstream is built.** *(K2 stands: <80% recall -> the derivation layer is sand; fall back to the static rubric and downgrade the claim in writing.)*
- **4.2 (~$3) RUN THE CURRENT PIPELINE END-TO-END, TO COMPLETION, ON 2 NON-72 TASKS.** We have never done this. Until we do, we do not have a generality number.
- **4.3 THE 3-TASK PANEL IS THE HEADLINE METRIC (K4, hard CI gate).** 72 (academic) / 78 (clinical — three of its top six criteria are literally *"Response to Query on..."*, readability weight 0.20) / 90 (proposal — insight weight 0.38). **A lever that lifts 72 and moves nothing on 78/90 is an overfit and is REVERTED, not tweaked.**

**THE OVERFIT IS IN THE OUTLINE, NOT THE TERM LISTS:**
- **4.4 CLOSE THE LIVE FOOTGUN (one line, today).** `_allowed_sections_for_domain("")` returns the **CLINICAL drug-trial set** (Efficacy / Safety / Regulatory / Dose Response), and `domain: str = ""` is the **default** at three call sites. **Any caller omitting `domain=` composes a drug-trial outline regardless of the question** — contradicting the two modules that already declare the rule (*"blank -> general, NEVER clinical"*). It does **not** fire on the benchmark. Fix it anyway; add the test.
- **4.5 WIRE THE PACK LOADER THAT ALREADY EXISTS.** `config/domain_packs/*.yaml` **already own a `sections:` list per domain**; **`load_domain_pack()` has ZERO production callers**; `multi_section_generator.py` never imports it. Replace the module constants with `load_domain_pack(domain)["sections"]`. **"Make it general" is a WIRING sprint against a tested abstraction — days, not a quarter, and not a day of deleting term lists either.**
- **4.6 MIGRATE THE 3 REAL VOCABULARIES** (`_DOMAIN_PHRASES` = **119**, `_RISK_PHRASES` = **73**, the endpoint taxonomy) into the packs. **Failure mode off-domain is EMPTY cells, not WRONG cells — a recall cost, not a correctness one. Not a P0.**
- **4.7 KILL THE PROPOSED CI GREP.** "Ban domain nouns" would **flag `domain_signal.py` (the anti-overfit spine) and the test mocks — and MISS `_ALLOWED_SECTIONS` entirely**, because "Efficacy / Safety / Dose Response" contains no domain noun. **It condemns the fix and approves the bug.** Replace with the assertion that binds: **no section-title list may be a module constant; every outline resolves through `load_domain_pack`** — plus a golden test that a non-clinical question never produces a clinical genre heading.

---

## PHASE 5 — THE WHEEL

FIX -> COMPOSE (3-task panel) -> INTEGRITY GATES -> SCORE k=5 (**capturing R**) -> **READ THE JUDGE'S OWN WRITTEN ANALYSIS** -> FIX.

- **STACK LEVERS. DO NOT RUN ONE AT A TIME.** This is the real correction, and it inverts the synthesis's reasoning while preserving its conclusion. The +0.0094 kill rule is a **LOW bar, not a blind one** — every dimension-scoped lever clears it by **3-6x**. **The problem is that the gap needs ~13 of them STACKED, and one-lever-at-a-time forbids stacking.** (And the lever-kill is **Fable's alone**; Sol's 0.0094 is a noise floor.)
- **K5 (mechanism counters)** — non-negotiable. A score run is **inadmissible** as evidence about a lever whose post-cleaner counter did not move.
- **K7 (run kill)** — two consecutive turns gaining < +0.0094 on the **panel mean** while below target -> **STOP and report MISSED.** No fallback success state. *A plan that ships with a fallback hits the fallback.*
- **K8 (honesty kill)** — **50 of the 100 tasks are Chinese** and nothing we have built composes in Chinese. Every corpus-wide claim is scoped to the **50 English tasks** or retracted on sight.
- **HARD BOUNDARY:** the composer never reads `reference.jsonl`. CI-enforced.

---

# DOES IT BEAT 0.5603? — **NO. NOT AS SPECIFIED. HERE IS EXACTLY WHAT IS MISSING.**

Measured from the judge's own per-criterion scores (n=1, R-drag applied):
```
BASELINE                                                  0.4413   (T=6.345, R=8.033)
+ the 4 judge-named CONTENT levers, at cellcog's scores   +0.0413  ->  0.4827   (35% of gap)
+ the entire SHAPE bundle (7 readability crit, incl table)+0.0244  ->  0.5071   (55% of gap)
                                                          -----------------------------------
   EVERYTHING THE JUDGE SAYS IT PAYS FOR, MAXED OUT   =   0.5071
BODHI                                                     0.5420   (needs T = 8.878)
CELLCOG                                                   0.5603   (needs T = 9.416)
CEILING (T=10, with drag)                                 0.5802
```

**Stacking every lever the judge has NAMED — all five, plus every readability criterion, each taken to cellcog's own measured score — reaches ~0.507. That does not beat bodhi (0.5420), let alone cellcog (0.5603).**

### WHAT IS MISSING, NAMED EXACTLY
To reach 0.5603 we need **T = 9.416** — which is **cellcog's own T (9.384)**. There is no subset. We must match cellcog on **essentially all 25 criteria**. After the five levers and shape, the residual (+0.0612 — *as large as everything the judge praised*) sits in **14 criteria the judge never named**, dominated by four:

| criterion | w | us | cell | Δ |
|---|---|---|---|---|
| Scope of Industry-Specific Analysis | .0725 | 6.8 | 9.3 | +0.0070 |
| Analytical Depth in Characterizing Mechanisms | .0800 | 7.5 | 9.7 | +0.0068 |
| Insightful Integration of AI within the 4IR | .0480 | 5.8 | 9.2 | +0.0063 |
| Value and Foresight (implications / future agendas) | .0480 | 6.5 | 9.1 | +0.0048 |

**These are not levers. They are the document having a thesis and covering its ground.** **F3 SURVIVES, and it is the honest core of the synthesis:** the weighted mean of all 25 criteria must move **6.35 -> 9.42** — a band jump — and **nobody on this table, including me, has a proven mechanism for producing one.** The hypothesis is *"answer the question that was actually asked, from evidence that is actually about it, and say something true and non-obvious."* **It is a hypothesis, not a priced lever, and it is the thing that will make us miss.**

**A hard lesson embedded in that table: the judge's written critique is a map of the CHEAPEST wins, not a map of the GAP.** Half the gap lives in criteria it never complained about.

### WHAT IS GENUINELY BETTER THAN BEFORE
1. **The ceiling is 0.580, not 0.5545.** K1 would have **halted the project** on a false ceiling that cellcog's measured score already exceeds. **Both gates are reachable.**
2. **Every lever is worth ~20% more than any plan booked it at** (dR/dT = -0.21 — the reference is marked down as we improve).
3. **The #2 lever is nearly free and we have never once touched it.** 1.5/10 on a criterion where **the reference itself scores 2.0**, and the mechanism is a channel defect fixable in a day.
4. **Shape is not zero.** It is +0.027 — 2.9x the resolvable effect — and the judge wrote down the mechanism itself.
5. **We steer by what the judge WRITES, not by what we guess.** `judge_feedback.py` costs $0.11 and answered, in one call, questions these plans budget days and dollars to argue about. **Run the $0.11 oracle before the $11 experiment suite.**

### HONEST PROBABILITIES
- **P(k=5 panel mean > bodhi 0.5420) ≈ 35-45%.** The named levers + shape + the channel fix are real and measured. The band jump is not.
- **P(k=5 > cellcog 0.5603) ≈ 15-20%.** It requires matching the #1 system criterion-for-criterion.
- **P(the SYSTEM, on an unseen task, beats 0.5420 in cycle one) — I will not put a number on five aborted, five-week-old runs. Phase 4.2 measures it for $3. Until it does, generality is UNMEASURED and we say so.**



## SURVIVES (build on these)

- **THE SCORING ALGEBRA (verified from source).** `deepresearch_bench_race.py:155-160`: overall = T/(T+R). `utils/score_calculator.py`: criterion weights renormalize within a dimension; dimension weights sum to 1.0; so T and R are weighted MEANS on 0-10 and all 25 global weights sum to 1.0. I reproduced every weight the synthesis quotes (0.0435, 0.0375, 0.080, 25 criteria). dS/dT = R/(T+R)^2 is the right formula.

- **F3 — THE OBJECTIVE IS NOT ADDITIVE. SURVIVES, and it is the honest core of the synthesis.** MEASURED from the judge's own per-criterion scores: the FIVE things the judge says it pays for, PLUS all seven readability criteria, each taken all the way to cellcog's own measured score, reach **0.5071 — 55% of the gap.** The other ~half lives in 14 criteria the judge never named in its praise. No subset closes it.

- **R IS NOT A CONSTANT — the new load-bearing fact, and I verified it myself.** Same fixed reference article, three separate judge calls: **R = 8.033 (vs us) / 7.545 (vs bodhi) / 7.363 (vs cellcog)**. Falls monotonically as the target improves. dR/dT = -0.21. Proven without regression: if R were fixed at 8.033, cellcog's measured 0.5603 would require T = 10.24/10 — above the cap. cellcog scored it. Therefore R fell. Consequences: levers are worth ~20% MORE than the R-fixed model says, and the ceiling RISES as you improve.

- **THE JOURNAL CRITERION IS THE BIGGEST w x HEADROOM LEVER ON THE BOARD AND IT IS NEARLY FREE.** 'Exclusive Citation of High-Quality Journal Articles', w=0.0375: **we score 1.5/10. The REFERENCE scores 2.0. Bodhi 8.2, cellcog 8.0.** Worth +0.0093 (R-fixed) / +0.0110 (with drag) — it clears the k=5 resolvable effect ALONE. The synthesis never once proposes stating an evidence constraint; grep for it across all 412 lines returns ZERO hits.

- **THE CHANNEL MECHANISM (mine — no lens stated it this sharply; it EXPLAINS the 1.5/10).** RACE's `clean_prompt.py` deletes reference lists, [n] markers and footnotes from EVERY submission before the judge reads it. Our report carries **345 [n] markers and a References section — all deleted** — leaving only **10 in-prose year-parens and 3 journal names**, against **11 surviving consultancy names** (WEF, PwC, Deloitte, Gartner, IBM, Goldman Sachs x4, IDC), because consultancies are narrative subjects. The judge's verbatim complaint names EXACTLY those consultancies. **We are scored on a corpus we did not submit.**

- **LENS 1's WELL-POWERED NULLS.** Sections +0.0020/SD — 'add 30+ subsections' is DEAD, and the H3 r=+0.519 everyone read as a mandate is 100% system identity. Length is a FLOOR (~5,000w), saturating ~8,000w; we are at 9,194 — past the knee. Sol's 13,500-16,500w and Fable's 15,000-16,000w targets are DELETED.

- **LENS 2 — GENERALITY IS UNMEASURED, NOT DISPROVEN.** All five polaris_vm_* runs are ABORTS, five weeks stale. The task-72 'overfit advantage' is NEGATIVE (-0.0125). VERIFIED BY ME: **38 scored runs since 07-12, ALL task 72, zero elsewhere.**

- **MECHANISM FABRICATION IS LIVE AND QUANTIFIED (I reproduced it exactly).** On the live 133-card corpus: 81 (card, mechanism) pairs. **42/81 (52%) of mechanisms are absent from their own span. 35/81 (43%) appear in NEITHER span nor claim — pure invention.** 'Task displacement' is bound to Bresnahan et al. (2002), whose span never says it. A fabrication assembled entirely from true particulars, already shipping.

- **FABRICATION AND INSIGHT OCCUPY THE SAME CELL.** Both are non-entailed, non-contradicted relations over true particulars. Measured: the contract's premise-independent rules reject **76/78 (97%)** of the exact prose the judge scored **9.8/10**. No entailment threshold admits insight and rejects mechanism-transplant. They are distinguished by VOICE, not by entailment.

- **THE OVERFIT IS IN THE OUTLINE, NOT THE TERM LISTS.** VERIFIED: `multi_section_generator.py:785 _ALLOWED_SECTIONS` = a drug-trial genre (Efficacy/Safety/Regulatory/Dose Response); `:811-817 _allowed_sections_for_domain('')` returns the CLINICAL set; `domain: str = ''` is the default at :2079/:2890/:9488. It contradicts `domain_signal.py:50-52` and `domain_pack.py:9-12` ('blank -> general, NEVER clinical'). It does NOT fire on the benchmark — a loaded footgun, not a fired one.

- **THE GENERALIZATION ARCHITECTURE IS ALREADY BUILT AND UNWIRED.** VERIFIED: `config/domain_packs/{clinical,economics,general,policy,science,technology}.yaml` each own a `sections:` list (general.yaml:31 -> Overview / Key Findings / Evidence and Analysis / Comparative / Limitations). **`load_domain_pack()` has ZERO production callers.** 'Make it general' is a WIRING job against a tested abstraction — days, not a quarter.

- **_DOMAIN_PHRASES = exactly 119, _RISK_PHRASES = 73** (counted). Real, checked in, load-bearing, filling live summary-table cells. Failure mode off-domain is EMPTY cells, not WRONG cells — a recall cost.

- **THE PLAN'S STRUCTURAL SPINE.** SELECT as a hard gate on the CITABLE pool (`PG_SCOPE_TOPIC_GATE_HARD_DROP` defaults to 0 today); citation-sort is topic-blind and is the deterministic generator of the ResNet/PRISMA junk; propose-then-resolve with a published FNR; date-filtered recency (retires Sol's Gate 0); the Stage-0 derivation layer; the contradiction index + corpus census; E1 the ledger patch; the poisoned-card CI test; the hard abort (one fabricated particular burns the artifact); K4 (panel mean), K5 (mechanism counters), K7 (run kill), K8 (50 of 100 tasks are Chinese).


## DIES (do not build on these)

- **K1 — THE CEILING GATE. DELETE IT TODAY.** It says 'if R >= 7.5 the ceiling is 0.571 and both gates are unreachable.' R measured against OUR article is **8.033 — K1 FIRES**, and declares a ceiling of **0.5545 that cellcog's measured 0.5603 ALREADY EXCEEDS.** A kill rule that would HALT THE PROJECT, falsified by data on disk. The true ceiling with the drag is **0.5802**, and **both plans' gates (0.5670 / 0.5672) ARE reachable.** K1 measured R against our own weakness and concluded the target was impossible.

- **THE SYNTHESIS'S HEADLINE: 'both plans mandate one-lever-at-a-time AND a kill rule no single lever can clear.'** FALSE on every clause. The +0.0094 lever-kill is **Fable's alone** (Sol's 0.0094 is a NOISE FLOOR; his KILL_RULE is run-level). Levers in both plans are DIMENSION-scoped and clear +0.0094 by **3-6x**. Even at criterion level, 2 of 25 clear it alone. And the synthesis's own worked example (+0.016 > +0.0094) refutes it. It compared +0.016 to the **0.117 GAP** and drew a conclusion about the **0.0094 KILL RULE** — two thresholds 13x apart, merged. **The real problem is STACKING, not RESOLUTION.**

- **'DOCUMENT SHAPE IS WORTH ~ZERO; BOOK IT AT ZERO.'** Refuted by the judge in writing. The 7 readability criteria taken to cellcog's level = **+0.0270 with drag — 2.9x the k=5 resolvable effect, 23% of the gap.** The judge names the mechanism itself: 'extremely long paragraphs... a fragmented narrative' (S2 = **3.5, our worst criterion**), 'dense, repetitive, and awkward' (L1 = 4.5). E0, the regression that licensed the zero, is computed on RAW submissions while the judge scores CLEANED text — it is structurally blind to the only channel that reaches the grader.

- **'FABRICATION IS NEVER THE ASSERTION OF A RELATION' (line 163).** FALSE, and it contradicts the synthesis's own line 191. Sign inversion is a fabrication that IS a relation. And line 163 is the sentence that gets operationalised.

- **PROPERTY 3 (synthesis entailment, reject on NEUTRAL) AS THE FAITHFULNESS REMEDY.** It deletes 97% of the 9.8/10 prose. A genuine synthesis is BY DEFINITION a relation the premises do not support — cellcog says so itself ('connecting findings that no single paper contains') and is paid 9.8/10 for it. **Reject on CONTRADICTED, not on NEUTRAL.**

- **K6's 'ZERO FALSE ADMISSIONS AND ZERO FALSE REJECTIONS'.** Unachievable by the proposed mechanism — it demands zero error on a problem where the two classes are IDENTICAL along the axis it measures. Do not ship a gate whose acceptance criterion is a contradiction.

- **'DOMAIN VOCABULARY IN 10+ LIVE SOURCE FILES'.** INFLATED. Of the 6 named: `decomposer.py` is DEAD CODE whose domain words are docstring-only (0 executable hits); `scope_classifier_llm.py`'s GLP-1 list is a UNIT-TEST MOCK with zero production callers; `template_classifier.py` is a 3-entry tokenizer alias; `evidence_value_extractor.py` degrades to inert; and **`domain_signal.py` is the ANTI-OVERFIT SPINE — the synthesis cited the FIX as the BUG.** ~3 real vocabularies, not 10+.

- **THE PROPOSED CI GREP ('ban domain nouns').** ACTIVELY HARMFUL. It would flag `domain_signal.py` (the fix) and the test mocks, and **MISS `_ALLOWED_SECTIONS` (the actual overfit) entirely** — because 'Efficacy / Safety / Dose Response' contains no domain noun. It condemns the fix and approves the bug.

- **'THE MOST DISHONEST LINE WE CURRENTLY SHIP'.** Not shipped. VERIFIED: `cellcog_composer.py` and `synthesis_contract.py` do not exist in the canonical repo (`/workspace/POLARIS`) — they are flywheel-worktree scripts. Same for VERDICT_VOCAB / SAFE_CAPS / CONTRASTS_LEVEL. (The hardcoded compliance abstract still dies — it is a fabricated claim — but it is not in the system that scores 0.263.)

- **'+5.0 IS THE SINGLE BIGGEST MEASURED WIN ON THE BOARD'** — a UNITS ERROR, and it was in my own brief. +5.0 is RAW CRITERION POINTS (bodhi 8.2 vs ref 3.2). In score units it is **+0.0093** — real, cheap, clears the resolvable effect, but it is **#2, not #1** (reconciling conflicts, w=0.080, is +0.0116). Same species of error LENS 1 caught. Do not book +5.0.

- **'ITS SECTORAL TABLE IS CLEAR AND USEFUL (+2.4)' IS NOT A CONTENT LEVER.** I traced it: it scores against **D1: Clarity of Data/Evidence, w=0.0140** (a READABILITY criterion), worth **+0.0024** — BELOW the resolvable effect standalone. The summary table is a component of the shape bundle, not a fifth content lever.

- **FABLE'S EXPECTED-TOTAL (0.5719).** Arithmetically impossible: it books comprehensiveness -> 0.58 and insight -> 0.58, which require **10.26/10 and 10.05/10** even against the most-dragged reference ever observed. Above the cap. Nobody caught this.

- **'cellcog may come back BELOW bodhi.'** REFUTED. cellcog = **0.5603** > bodhi **0.5420**. Measured. Also dead: 'T/R = 1.31, higher than any system on any dimension' — the frontier omitted cellcog, whose task-72 insight T/R is 1.309; the margin is 0.0004, ~20x below judge noise.


## MUST RE-VERIFY BEFORE TRUSTING

- **THE R-DRAG MAGNITUDE (dR/dT = -0.21) IS n=3 SINGLE CALLS.** The SIGN is proven without regression (R fixed at 8.033 makes cellcog's 0.5603 require T=10.24 > cap). The MAGNITUDE is not. It is now load-bearing for the ceiling, for every lever's value, and for both plans' arithmetic. **Re-run judge_feedback k=5 on all three targets, capturing R.** ~$3.

- **EVERY PER-CRITERION NUMBER IN MY LEVER TABLE IS n=1.** The judge scores all 25 criteria in ONE call, so they are halo-correlated. **E6 (per-criterion SD matrix, $0.55 on the 5 banked noise_r10_* artifacts) must run before any criterion is called a deficit.** The RANKING of the top levers is probably robust (1.5 vs 8.0 is not noise). The VALUES are not.

- **THE 0.263 SYSTEM NUMBER IS NOT A GENERALITY NUMBER.** Those five runs are ABORTS, five weeks stale. **Re-run the CURRENT pipeline end-to-end, to completion, on >=2 non-72 tasks (~$3).** Until then we have never measured generality — we have 38 consecutive task-72 runs.

- **THE SHAPE BUNDLE (+0.0270) ASSUMES WE CAN REACH CELLCOG'S READABILITY SCORES.** Our 677-word median paragraph is the 99.7th percentile of 898 articles — E0's null has NO SUPPORT there. **E4 (k=10 paired, content and word count held fixed, paragraphs split) SIZES it.** It is now a sizing experiment, not a go/no-go: the judge has already told us in writing that the effect exists.

- **IS A JOURNAL-ONLY CORPUS EVEN ACHIEVABLE?** The judge names WEF, IDC, PwC, IBM, Deloitte, Gartner, Goldman Sachs in our prose. **BEFORE declaring the constraint, MEASURE: what fraction of the coverage matrix is fillable from journals alone?** If it is not fillable, the declaration must be SCOPED to what is true. **A declaration we cannot honor is precisely the fabrication we are trying to kill.**

- **cellcog's 0.5603 AND bodhi's 0.5420 ARE BOTH n=1** (bodhi's board raw_results says 0.5441; my recompute says 0.5420 — that spread IS the noise). k=5 them ($0.55) before any gate is set from them.

- **K2 STANDS UNCHANGED AND UNRUN:** if the compiler's weighted rubric-mass recall against the 100-task ground truth is < 80%, the derivation layer is sand — fall back to the static rubric and downgrade the generality claim IN WRITING.
