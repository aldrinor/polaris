# ALL SIX ADVERSARIAL VERDICTS — the complete, attacked record


## LENS: kill-rule-math — **PARTIALLY_REFUTED**

## WHAT I DID
Rebuilt the score model from source, then recomputed every number from the raw per-criterion judge scores.

**The model (verified in code, not assumed).** `deepresearch_bench_race.py:155-160`: `overall = target_total/(target_total+reference_total)`. `utils/score_calculator.py`: within a dimension the criterion weights are renormalized (`dim_avg = Σ(w_c·s_c)/Σ(w_c)`) and then multiplied by the dimension weight. In `criteria.jsonl` task 72, criterion weights sum to **1.0 within each dimension**, and dimension weights sum to 1.0 — so the global effective weight is `W_d × w_c`, all 25 sum to exactly 1.0, and **T and R are weighted MEANS on 0–10**. That reproduces every weight the synthesis quotes: Depth&Repr = 0.29×0.15 = **0.0435** ✓; Journal-only = 0.25×0.15 = **0.0375** ✓; heaviest = 0.32×0.25 = **0.080** ✓; 25 criteria ✓. So `dS/dT = R/(T+R)²` is the right formula. **The synthesis's algebra is sound.**

**The data.** I did not have to estimate T and R — `outputs/judge_feedback{,_bodhi,_cellcog}.json` carry the judge's raw `article_1_score`/`article_2_score` for all 25 criteria. Recomputed exactly as the harness does:

| target | T | R | S | check |
|---|---|---|---|---|
| POLARIS | 6.345 | **8.033** | 0.4413 | (plans say 0.4382) |
| bodhi | 8.930 | **7.545** | 0.5420 | board raw_results: 0.5441 ✓ |
| cellcog | 9.384 | **7.363** | 0.5603 | |

## THE FINDING THAT BREAKS THE WHOLE ARGUMENT: **R IS NOT A CONSTANT**
Same reference article, three separate calls: R = 8.033 → 7.545 → 7.363. The judge marks the *reference* DOWN as the target gets better (insight swings a full 1.03 points; falls monotonically in 3/4 dims). **This is provable without any regression:** if R were fixed at 8.033, scoring cellcog's 0.5603 would require T = 1.2743 × 8.033 = **10.24/10**. Impossible. cellcog scored it. Therefore R fell. QED.

## CLAIM-BY-CLAIM

**1. "dS/dT ≈ 0.045" — the NUMBER is right; the DERIVATION is wrong.** At the measured operating point, `R/(T+R)² = 8.033/14.378² = **0.0389**`, not 0.045. The synthesis got 0.045 by *assuming* R≈7 (it says so at line 48: *"if the reference scores R≈7/10"*). But with the reference-drag included, `dS/dT = [R − T·(dR/dT)]/(T+R)²` with dR/dT = −0.21 gives **0.0453**. **Two errors cancel to within 1%.** It is accidentally correct.

**2. "+4.8 points for a w=0.0435 criterion" — SURVIVES.** Exact: R-fixed → +5.56 pts; R-responds → **+4.77 pts**. The synthesis's number is right.

**3. "BOTH plans" have the +0.0094 lever-kill — FALSE.** Only **Fable** does: `FABLE_PLAN_V4.md:19` *"Keep the lever only if paired delta >= +0.0094"* and `:28` *"a lever is kept iff its paired delta >= +0.0094"*. **Sol mentions 0.0094 exactly once**, at `SOL_PLAN_V4.md:79`, as a *noise floor* (*"Never n=1 (judge SD 0.0074; smallest resolvable paired effect +0.0094)"*). Sol's actual `KILL_RULE` (`:118-130`) is a **run-level** kill (best-of-3 below 0.5578 → declare X1/X2/X3) plus integrity aborts. Sol has **no lever-level kill rule at all.**

**4. "A kill rule that cannot see one lever" — FALSE, and the unit is wrong.** Both plans' levers are **DIMENSION-scoped**: Fable:19 *"exactly one **dimension-targeted** change"* (order: readability → attribution → insight → 4IR → corpus); Sol:89 *"spend the next turn's entire budget on the single largest deficit"* (per-dimension). **Neither plan ever proposes a single-criterion lever.** The synthesis tested a unit neither plan uses. Measured points needed on a dimension to clear +0.0094 (R-fixed, the *conservative* model):

| dimension | W | we score | needs | bodhi | cellcog |
|---|---|---|---|---|---|
| readability | 0.14 | **4.71** | **+1.76** | 8.65 | 9.11 |
| insight | 0.32 | 6.45 | **+0.77** | 8.89 | 9.53 |
| comprehensiveness | 0.29 | 7.23 | **+0.85** | 9.06 | 9.48 |
| instruction_following | 0.25 | 6.11 | **+0.98** | 9.24 | 9.24 |

Every lever both plans name clears the kill rule by **3–6×** on the plans' own booked numbers. The rule is a LOW bar, not a blind one.

**5. Even at the criterion level it's false: 2 of 25 clear +0.0094 alone.** "Critical Synthesis" (w=0.080, we score 5.8 → max **+0.0128**) and **"Exclusive Citation of High-Quality Journal Articles" (w=0.0375, we score 1.5/10 → max +0.0121)** — the very criterion the judge names as the biggest win on the board.

**6. The synthesis refutes itself in its own sentence.** Line 350: *"the SINGLE HEAVIEST criterion (w=0.080), taken from 5.5 to a perfect 10, buys **+0.016**"* — and +0.016 > +0.0094. The kill rule **sees** that lever. It compared +0.016 to the **0.117 GAP**, then drew a conclusion about the **0.0094 KILL RULE**. Two thresholds **13.4× apart**, merged. Non sequitur.

**7. "T/R = 1.31, higher than ANY system on ANY dimension" — technically alive by 0.0004, evidentially dead.** Gate arithmetic ✓ (0.5670→1.3095, 0.5672→1.3105), and lunon's insight = 1.2698 ✓ from `raw_results.jsonl`. **But that frontier was computed from a dataset that structurally omits cellcog** — the one system with no per-task file (both plans flag this). Measured today: **cellcog's task-72 insight T/R = 1.3091.** The claim survives Sol's gate by 0.0004 — ~20× below judge noise — and its cited evidence (1.270) is superseded. Practical force gone: the gate is **2.7%** above cellcog's measured overall T/R.

**8. BONUS — the synthesis's own K1 ceiling gate would abort the project on a false positive.** K1/E2 (lines 237/310/320, *"the most sobering possibility in the project"*): *"If R ≥ 7.5 the ceiling is 0.571 and both gates are unreachable."* R = **8.033 against our article → K1 FIRES**. But R against cellcog = 7.363 → ceiling 0.5759; with the measured drag at T=10, ceiling = **0.5789**. **Both gates sit BELOW the ceiling. They are reachable.** K1 measures R against our own weakness and concludes the target is impossible. (Note the mirror: under the synthesis's *own* R-fixed model, a **perfect 10/10 article scores only 0.5546** and cannot pass either gate. The drag it never modelled is the only thing that saves them.)

**9. BONUS — Fable's expected-total is arithmetically impossible.** `FABLE_PLAN_V4.md:22` books comprehensiveness→0.58 and insight→0.58. Normalized 0.58 ⇒ t = 1.381·r. Even with the reference dragged to its **lowest ever observed** value, that needs us to score **10.26/10** and **10.05/10**. Above the cap. Fable's headline 0.5719 rests on two unreachable targets. Neither the synthesis nor either prior lens caught this.

### SURVIVES
**SURVIVES (confirmed):** (a) the algebra — S = T/(T+R), weights sum to 1.0, T/R is a weighted mean on 0–10, dS/dT = R/(T+R)²; (b) **"+4.8 points"** is the right answer (true value +4.77) for a w=0.0435 criterion; (c) the weights 0.0435 / 0.0375 / 0.080 / 25 criteria are all exactly right; (d) the gate→T/R arithmetic (0.5670→1.3095, 0.5672→1.3105); (e) **the band-jump problem is REAL and worse than stated** — the weighted mean of all 25 criteria must go **6.35 → 9.63/10**, i.e. *above cellcog's 9.38*, and the gap needs **~13 kill-rule-clearing levers stacked**.

**REFUTED:** the headline. "Both plans mandate one-lever-at-a-time AND a kill rule that cannot see one lever; they would have killed every good lever they built" fails on every clause. *Both* → only Fable has a lever-kill (SOL_PLAN_V4.md:79 is a noise floor; Sol's KILL_RULE is run-level). *Cannot see one lever* → the plans' levers are dimension-scoped and clear +0.0094 by 3–6×; even at the criterion level 2/25 clear it alone; and the synthesis's own worked example (+0.016 > +0.0094) refutes it. Its "0.045" is right only by two cancelling errors, and its "no system has ever posted 1.31" is a 0.0004 margin against a frontier that omitted cellcog (whose insight T/R is 1.3091).

**THE NEW LOAD-BEARING FACT NOBODY HAS MODELLED: the reference's raw score is not a constant.** R = 8.033 vs us, 7.545 vs bodhi, 7.363 vs cellcog — same article, three calls. Proven, not estimated: R fixed at 8.033 makes cellcog's 0.5603 require 10.24/10. This means levers are worth **~17% more** than the R-fixed model says, the ceiling **rises** as you improve, and dimension-normalized targets (the unit BOTH plans book their arithmetic in) are **not a stable measurement scale**.

**THE PARENT'S CONCLUSION IS RIGHT, FOR THE WRONG REASON.** Measure at the criterion level — not because the kill rule is blind, but because (1) the dimension score *hides* the biggest lever on the board: instruction_following reads a bland 6.11/10 while concealing a **1.5/10** criterion (journal-only, w=0.0375, 8.5 points of headroom — bodhi 8.2, cellcog 8.0); and (2) raw criterion scores are the only unit immune to the reference-drag.


### FIX
**1. Delete the claim, keep the arithmetic.** In `/home/polaris/polaris_project/sota_review/foundation/OPUS_SYNTHESIS_V1.md:349-350`, "a kill rule that no single lever can clear — they would have killed every good lever they built" is false and should be struck. Replace with the true finding: *the kill rule is easily cleared (every dimension lever clears it 3–6×); the problem is that the GAP needs ~13 of them stacked, and both plans forbid stacking.* That is the real tension between one-lever-at-a-time and the target — and it is a **stacking** problem, not a **resolution** problem.

**2. Correct the attribution.** The +0.0094 lever-kill is **Fable's alone** (`FABLE_PLAN_V4.md:19,:28`). Sol has no lever-level kill rule (`SOL_PLAN_V4.md:79` is a noise floor; `:118-130` is a run-level kill). Fix "BOTH foundation plans" at :349 and :389.

**3. Disarm K1 before it fires falsely.** `OPUS_SYNTHESIS_V1.md:320` would abort the plan on R ≥ 7.5. R measured against our article is **8.033** — K1 fires today, on an artifact of our own weakness. Rewrite the ceiling as `10/(10 + R_at_the_target_operating_point)`; measured, that is **0.5789**, and **both gates are reachable.**

**4. Re-run judge_feedback k=5, capturing R.** The reference-drag (dR/dT ≈ −0.21) is proven in sign but estimated from n=3 single calls. It is now load-bearing for the ceiling, for lever value, and for both plans' expected-totals. Patch `scripts/judge_feedback.py` to log `target_total` and `reference_total` on every run — the harness throws them away at `deepresearch_bench_race.py:158`, which is why nobody saw this.

**5. Point the next lever at the 1.5/10.** "Exclusive Citation of High-Quality Journal Articles" (w=0.0375): we score **1.5**, bodhi **8.2**, cellcog **8.0**. It is the largest w×headroom in the rubric after the heaviest insight criterion, it clears the kill rule alone (+0.0094 to +0.0121), and it is the one lever on the board that is nearly free — it is a stated evidence constraint in prose, not


## LENS: overfit-in-code — **PARTIALLY_REFUTED**

# VERDICT: PARTIALLY REFUTED. The headline is inflated; the real overfit is somewhere the synthesis never looked — and the fix is already built and switched off.

I opened every file. AST-audited them to separate executable code from docstrings/comments. Traced every call site. Parsed the sweep manifest.

## 1. WHAT SURVIVES (CONFIRMED, exactly)

`src/polaris_graph/generator/summary_table.py:270` `_DOMAIN_PHRASES` — I counted the literals: **exactly 119.** The synthesis's number is dead right. `:307` `_RISK_PHRASES` = **73**. They fill live cells at `:1135-1136`. This one is real and checked in.

## 2. THE FILE LIST IS INFLATED — 2 of 6 named files are FALSE POSITIVES, 1 is trivial, and 1 is the ANTI-overfit mechanism cited as the bug

AST audit (`prose` = docstring/comment, `CODE` = executable):

| file | prose hits | **CODE hits** | truth |
|---|---|---|---|
| `decomposer.py` | 6 | **0** | **DEAD + docstring-only** |
| `scope_classifier_llm.py` | 0 | 4 | **unit-test mock** |
| `template_classifier.py` | 19 | 1 | 3-entry tokenizer alias |
| `domain_signal.py` | 0 | 4 | **the anti-overfit spine** |
| `evidence_value_extractor.py` | 0 | 1 | anti-fabrication allow-list |
| `claim_atom_extractor.py` | 20 | 11 | **genuinely real** |

- **`decomposer.py` — DOUBLE false positive.** Its only domain words (tirzepatide/semaglutide/T2DM) are **in the module docstring**; the executable code is six English connectives (`considering`, `including`, `across`…). **0 code hits.** And it's **dead**: the only importer in the whole repo is `tests/polaris_graph/test_decomposer.py`. The live one is `retrieval/query_decomposer.py`.
- **`scope_classifier_llm.py:143-163` — false positive.** The GLP-1 list lives in `_DEFAULT_MOCK_PROFILES` for `MockScopeAffinityLLM`: *"Deterministic, rule-based LLM mock for offline unit tests."* **Zero production callers.**
- **`template_classifier.py:237`** is `_COMPACT_DRUG_CLASS_SPLIT = {"glp1": ["glp","1"], "sglt2":…, "dpp4":…}` — a *tokenizer normalizer* so "GLP1" and "GLP-1" tokenize alike. Inert on non-clinical text.
- **`domain_signal.py` — the synthesis cites the FIX as the BUG.** It calls it "a GLP-1-flavoured clinical term list." Its actual docstring (L1-13): *"POLARIS is GENERAL by default; clinical rigor is a DETECTED specialization… The historical failure (the 2,738 junk clinical-contradiction flags on a labor-displacement report) was… that the clinical predicate/lexicon logic fired UNCONDITIONALLY on every domain. The fix is a single, deterministic, NO-LLM `is_clinical` signal threaded into every consumer."* The clinical terms are the **detector that turns the clinical path OFF**. It gates **10 live modules**; `contradiction_detector.py:1557-58` literally reads `if not is_clinical_domain(domain, evidence): return`.
- **`evidence_value_extractor.py:58-67`** `_DRUG_RE` is a closed-world **anti-fabrication allow-list**. `build_allow_lists` (`:127-140`): *"Rows with NO extractable value are omitted (so the caller's `if _allow_lists:` truthy check is False when the whole subset is qualitative)."* On non-clinical corpora it contributes nothing; the prompt is unchanged. **Degrades to inert.**
- **`claim_atom_extractor.py`** (HbA1c `:184`, myocardial infarction `:220`, GLP-1 alternation `:328`) is real and live via `build_atom_catalog` → `evidence_distiller.py:62`.

So "10+ live source files riddled" → **~3 live load-bearing vocabularies**, one inert-on-miss, one is_clinical-gated.

## 3. THE SYNTHESIS'S OTHER "SHIPPED" HARDCODINGS ARE NOT IN THE SHIPPED SYSTEM

`grep -rn "VERDICT_VOCAB|SAFE_CAPS|CONTRASTS_LEVEL" src/` → **nothing.** `synthesis_contract.py` and `cellcog_composer.py` **do not exist in the canonical repo** — they're in `/home/polaris/wt/flywheel/scripts/`, and live `src/` never imports them. So the "17-item hardcoded idiom list," `SAFE_CAPS` containing `'AI'`, and *"the hardcoded abstract at cellcog_composer.py:400-414 — the most dishonest line we currently ship"* are **flywheel experiment scripts, not the system that scores 0.263.**

## 4. THE REAL OVERFIT — WHICH THE SYNTHESIS MISSED ENTIRELY

**The genre is hardcoded in the OUTLINE, not the term lists.** `multi_section_generator.py`:

- **`:785 _ALLOWED_SECTIONS = ["Efficacy","Safety","Regulatory","Comparative","Mechanism","Dose Response","Population Subgroups","Long-term Outcomes"]`** — a **drug-trial genre**. Comment `:779`: *"The outline call is constrained to pick from this list."*
- `:801 _ALLOWED_SECTIONS_GENERIC` — 6 fixed buckets.
- **`:811-818 _allowed_sections_for_domain()` returns the CLINICAL set when domain is `""` OR `"clinical"`.**
- **`:9488  domain: str = ""`** — the parameter default is **blank**.

**⇒ any caller omitting `domain=` composes a drug-trial outline regardless of the question.** `scripts/run_honest_on_prerebuild_corpus.py:301` is exactly such a caller (verified: no `domain=` in its call). This contradicts the operator-locked rule in `domain_signal.py:50-52` and `domain_pack.py:9-12` — *"blank/unknown → general, **NEVER clinical**."* **Two modules say ''→general; the composer says ''→clinical.**

**But it does NOT fire on the benchmark.** I parsed `SWEEP_QUERIES` (`run_honest_sweep_r3.py:7465`): **18 queries, 0 blank domains**; `drb_72_ai_labor` carries `domain='workforce'` → generic set. Confirmed against the real artifact `/workspace/outline_agent_wt/tests/fixtures/drb72/report.md`: headings are Background / Key Findings / Evidence and Analysis / Implications / Limitations. **A loaded footgun, not a fired one.** (This is also why I do not let the synthesis claim its headline.)

## 5. THE SCOPING ANSWER: NEITHER A DAY NOR A QUARTER. IT'S A WIRING JOB.

**The generalization architecture is already built, tested — and unwired.**
- `config/domain_packs/{clinical,economics,general,policy,science,technology}.yaml` exist. Each owns **`sections:`** (general.yaml → Overview / Key Findings / Evidence and Analysis / Comparative / Limitations), plus `contradiction_predicates`, lexicon pointers, credibility priors. `domain_pack.py:14`: *"LAW VI: no hard-coded pack content — everything is read from YAML."*
- **`load_domain_pack()` has ZERO production callers.** Repo-wide: only its own module and `tests/polaris_graph/test_b9_domain_generalization.py`. The packs' `sections:` key is read **nowhere**.
- **`multi_section_generator.py` never imports `domain_pack` at all.** It uses its own module constants instead of the YAML that was written to replace them.
- The emergent-outline fix also exists, also off: `PG_FACET_OUTLINE` (default `"0"`, `:851`) makes titles+count emerge from evidence facets; `PG_USE_RESEARCH_PLANNER` default off. `:821-831` calls truncate-to-6 *"a CAP being REMOVED."* And `:861` disables the facet outline for blank/clinical **regardless of the flag**.

## 6. THE KILLER: THE SYNTHESIS'S OWN REMEDY WOULD GREENLIGHT THE ACTUAL OVERFIT

It proposes *"a CI grep bans domain nouns from every file outside brief.json."* Run that grep on this codebase and it: **flags `domain_signal.py` (the anti-overfit spine), the test mocks, and the docstrings — while missing `_ALLOWED_SECTIONS` entirely**, because "Efficacy / Safety / Regulatory / Dose Response" contains **no domain noun at all**. They're clinical *genre* labels. The proposed gate would condemn the fix and approve the bug.

### SURVIVES
SURVIVES (verified): `summary_table.py:270` `_DOMAIN_PHRASES` = **exactly 119** phrases (count confirmed), `:307` `_RISK_PHRASES` = 73, both filling live table cells at `:1135-36`; plus `claim_atom_extractor.py`'s clinical endpoint taxonomy (live via `build_atom_catalog`). Real, checked-in, load-bearing. On an off-vocabulary domain the cells go **empty, not wrong** — a recall cost, not a correctness one.

DIES: "domain vocabulary in 10+ live source files." Of the 6 named, `decomposer.py` is **dead code whose domain words are docstring-only (0 executable hits)**; `scope_classifier_llm.py`'s GLP-1 list is a **unit-test mock with zero production callers**; `template_classifier.py` is a 3-entry tokenizer alias; `evidence_value_extractor.py` is an anti-fabrication allow-list that degrades to inert; and **`domain_signal.py` is the anti-overfit spine, not the overfit** — it gates 10 modules so clinical logic does NOT fire on labour corpora. The synthesis cited the fix as the bug. Separately, `VERDICT_VOCAB`/`SAFE_CAPS`/`CONTRASTS_LEVEL`/`cellcog_composer.py` are **absent from live `src/`** — they're flywheel-worktree scripts, so "the most dishonest line we currently ship" is not shipped.

THE REAL FINDING (missed by the synthesis): the genre is hardcoded in the **OUTLINE**. `multi_section_generator.py:785 _ALLOWED_SECTIONS` is a drug-trial section list (Efficacy/Safety/Regulatory/Dose Response/…), and `:811-818` routes **blank domain → CLINICAL** while `:9488` makes `domain: str = ""` the **default** — directly contradicting `domain_signal.py:50-52` and `domain_pack.py:9-12` ("blank → general, NEVER clinical"). It does **not** fire on the benchmark (all 18 `SWEEP_QUERIES` carry a domain; `drb_72_ai_labor`='workforce', and the real drb72 artifact shows generic headings) — a loaded footgun, not a fired one.

SCOPING ANSWER (the question the lens exists to settle): **days, not a quarter — and not a day of grepping term lists either.** The generalization architecture is **already built, tested, and unwired**: `config/domain_packs/*.yaml` already own per-domain `sections:`, but **`load_domain_pack()` has ZERO production callers** and `multi_section_generator.py` never imports it. The emergent-facet outline (`PG_FACET_OUTLINE`) and planner outline (`PG_USE_RESEARCH_PLANNER`) both exist and are **default-OFF**. "Make it general" = wire the loader that already exists, not write one.

WARNING: the synthesis's proposed remedy — "a CI grep bans domain nouns" — would **flag 


### FIX
Do NOT budget a quarter, and do NOT budget "a day of deleting term lists." Budget a WIRING sprint against an abstraction that already exists and is already tested.

1. **Close the live footgun (one line, do it first).** `multi_section_generator.py:811-818` — `_allowed_sections_for_domain("")` must return the GENERIC/general set, not `_ALLOWED_SECTIONS`. Blank domain currently yields a drug-trial outline. Make it agree with the two modules that already declare the rule (`domain_signal.py:50-52`, `domain_pack.py:9-12`: blank → general, NEVER clinical). Also fix the caller `scripts/run_honest_on_prerebuild_corpus.py:301`, which passes no `domain=`. Add a test asserting `_allowed_sections_for_domain("")` contains no clinical genre label.

2. **Wire the pack loader that already exists.** Replace the module constants `_ALLOWED_SECTIONS` / `_ALLOWED_SECTIONS_GENERIC` with `load_domain_pack(domain)["sections"]`. The YAML (`config/domain_packs/{clinical,economics,general,policy,science,technology}.yaml`) already carries a `sections:` list per domain; the loader already defaults unknown→general and is covered by `tests/polaris_graph/test_b9_domain_generalization.py`. It currently has **zero production callers** — that is the whole bug. This deletes the genre hardcode outright.

3. **Migrate the 3 real vocabularies into the packs.** `summary_table.py:270/307` (119 + 73 phrases) and `claim_atom_extractor.py`'s endpoint taxonomy move into pack YAML — the packs already have `contradiction_predicates` and lexicon-pointer slots designed for exactly this. Note the failure mode is *empty cells*, not wrong cells, so this is a recall fix, not a correctness fix — schedule it accordingly, not as a P0.

4. **Turn on what's already built.** `PG_FACET_OUTLINE=1` (default `"0"` at `:851`) makes section titles and count emerge from real evidence facets; `PG_USE_RESEARCH_PLANNER` swaps in the planner archetype outline. Also fix `:861`, which disables the facet outline for blank/clinical *regar


## LENS: fabrication — **PARTIALLY_REFUTED**

## 1. THE TWO CODE CLAIMS: BOTH CONFIRMED, ONE WORSE THAN STATED

**`validate()` imported at `/home/polaris/wt/flywheel/scripts/cellcog_composer.py:49`, never called — CONFIRMED, AND WORSE.**
- `grep -n "validate" scripts/cellcog_composer.py` returns exactly ONE line: `49:from synthesis_contract import Premise, Synthesis, validate, OPERATIONS`.
- `synthesis_contract` is imported by exactly TWO files repo-wide: itself and `cellcog_composer.py`.
- The ONLY call site of `validate()` in the entire repo is **`synthesis_contract.py:311`, inside `self_test()`**, against its own hardcoded fixture dict `P`. The gate is a closed loop: invoked only by its own self-test, fed its own hand-written examples, prints green. `Premise`, `Synthesis`, `OPERATIONS` are ALSO imported at `:49` and ALSO unused — the entire module is dead code in the composer.
- This is exactly the failure the synthesis warns against at its line 201 ("a test that FAILS if the gate is bypassed, not one that passes because the gate returned True in isolation"). The existing self-test IS the latter. The warning is already true of the code it warns about.
- The only thing between LLM prose and the page is `_clean()` (`:342-364`): drops `[n]` markers, drops meta-commentary words, strips parenthetical years. Zero faithfulness checking. CONFIRMED.

**`mechanisms` at `:167` copied unchecked — CONFIRMED, and quantified for the first time.**
`'mechanisms': f.get('mechanisms') or []` — raw from LLM output, while `span`/`claim` beside it get the gate. Measured on the live 133-card corpus (`outputs/evidence_cards.json`):
- 52/133 cards declare >=1 mechanism; 81 (card, mechanism) pairs.
- **42/81 (52%) of mechanisms do not appear in their own span.**
- **35/81 (43%) appear in NEITHER the span NOR the claim — pure LLM invention.**
- `synthesis_contract.py:123` documents `Premise.mechanisms` as "mechanisms **STATED IN THE SPAN**." Its only producer violates that for over half its instances.
- Live: `'task displacement'` and `'limited substitution of routine tasks'` are attached to **Bresnahan et al. (2002)**, whose span reads only "Computer automation of such work has been correspondingly limited in its scope." Neither phrase is in the paper. "Task displacement" is Autor-Levy-Murnane's term — a REAL mechanism from a REAL paper, bound to the WRONG paper. **A fabrication assembled entirely from existing particulars, already shipping.**

## 2. THE CONCRETE PATH TO THE PAGE (traced in code, not reasoned)
1. `extract_cards()` — LLM #1 emits `claim` ("one sentence stating the finding, **in your words**", `:118`), `span`, `mechanisms`.
2. `:161` — the ONLY gate: `if norm(span)[:60] not in norm(text): continue`. It checks the **SPAN, not the CLAIM**. The claim is never checked against the span anywhere.
3. `:167` — `mechanisms` copied raw.
4. `_fmt_cards()` (`:330-338`) hands the writer: `FINDING: {c['claim']}` (the LLM's paraphrase) + `ATTRIBUTION (use this exact wording): {c['attribution']}` (the real author/journal/year) + `mechanism stated by the paper: {mechanisms}` (the unchecked invention, **labelled "stated by the paper"**). **THE SPAN IS NEVER SHOWN TO THE WRITER** — the verified quote is an admission ticket, then discarded.
5. `_clean()` — punctuation only. 6. Page.

So: a mechanism the paper never stated, stamped "stated by the paper," handed to a writer that never sees the source, printed under a real author's name, past a cleaner that checks punctuation. Meanwhile `:185` prints `span-verified against the source text: 100%`.

## 3. IS "NO NEW PARTICULAR" SUFFICIENT? NO — CONFIRMED BY EXECUTION
Three attacks, built ONLY from true particulars in admitted premises, all **ADMITTED** by the real `validate()`:
- **A1 SUBSUMPTION INVERSION**: "...the regional estimate is limited to a displacement margin that the firm-level result subsumes." (`subsumes`, `is limited to` are both in VERDICT_VOCAB.) No digit, no new capitalised token, no causal verb. ADMITTED.
- **A2 MECHANISM TRANSPLANT**: "The firm-level expansion is driven by task displacement..." — the mechanism belongs to p1 (Acemoglu-Restrepo); the sentence attaches it to p2's finding (Babina). Rule 6 (`:200`) computes `stated` as the **UNION over ALL cited premises**, so one card's mechanism licenses causal prose about a different card's finding. ADMITTED.
- **A3 SIGN INVERSION**: "...both establish that robot adoption **supports** the employment-to-population ratio..." — p1 says it REDUCES it. ADMITTED.

But **the synthesis already says this** (lines 190-191, 194, 408). My lens's hypothesis is CONFIRMED as a fact about the code, but it does not refute the document's diagnosis.

## 4. WHERE THE SYNTHESIS IS ACTUALLY WRONG — THE OPPOSITE FAILURE, AND IT IS FATAL

**(a) Its headline sentence is false and contradicts its own section.** Line 163: *"Fabrication is always the introduction of a PARTICULAR... **It is never the assertion of a RELATION.** Everything fraud consists of lives in particulars."* Line 191: referential closure *"admits mechanism transplant, misattribution, and sign inversion — all **false relations over true particulars**."* Both cannot be true. A3 is a fabrication that IS the assertion of a relation. Line 191 is right; **line 163 is wrong — and line 163 is the sentence that gets operationalised.**

**(b) The proposed fix cannot work.** Property 3 (line 191): entailment call with SPAN = the premises' claim texts, "NEUTRAL if it asserts a relation... those premises do not support." `entailment_judge.py:588` verbatim: *"NEUTRAL: the SENTENCE introduces a fact, entity, mechanism, or specificity NOT present in the SPAN."*
Now the measured judge reality: cellcog scores **9.8/10** (reference 7.0) on *"Identification and Articulation of Emergent Themes, Theoretical Linkages, or Novel Perspectives"* — *"Its eight tagged syntheses... show genuine synthesis beyond summary."* cellcog's own text: they *"extend the field's understanding by **connecting findings that no single paper contains**"*, and *"**Neither** the Global South development literature **nor** the mainstream labor economics literature **has explicitly framed informality in these terms**."*
**A genuine synthesis is BY DEFINITION a relation the premises do not support. That is what "beyond summary" means.** Property 3 returns NEUTRAL on it and deletes it.
MEASURED — the contract's premise-independent rules (4, 7, 8; they fire identically whatever premises you supply, so this is an airtight lower bound) over cellcog Section 5, the exact 2,004 words scored 9.8/10:
- **76/78 sentences (97%) REJECTED.**
- Rule 8 (VERDICT_VOCAB) alone: 72/78 (92%). Whole document: 572/610 (94%). **The synthesis's "93%" claim is CONFIRMED — independently reproduced.**
- Rule 4 (any digit): 33/78 (42%) — including *"Dell'Acqua... document in-frontier compression across **758** consultants"*, the empirical anchor of "augmentation as skill compression," one of the named eight. Rule 4 also kills every sentence carrying a year — i.e. the synthesis's own mandated citation form `Author(s) (YYYY), in the *Journal*...` (lines 104, 218).
- The flagship: *"We propose, as analytical synthesis, that informality functions as the Global South's institutional analogue to European coordinated-bargaining... systems"* — dies to `no_verdict_vocabulary`, and dies AGAIN under Property 3 as NEUTRAL, **because no premise supports it — which is precisely why it is worth 9.8/10.**

**THE FUNDAMENTAL RESULT: fabrication and insight occupy the SAME CELL.** Sort by the entailment judge's own verdicts: A3 (sign flip) -> CONTRADICTED, catchable. **A1 (subsumption inversion) and A2 (mechanism transplant) -> NEUTRAL. The informality buffer, the exposure inversion, skill compression (the 9.8/10) -> NEUTRAL.** A1/A2 and the 9.8/10 insights are in the *same bucket*: non-entailed, non-contradicted, no new particular.
- Reject on NEUTRAL -> delete the insights (97% of Section 5), score zero on INSIGHT (heaviest dimension, mean weight 0.352).
- Reject only on CONTRADICTED -> admit the insights AND admit subsumption-inversion and mechanism-transplant.
- **No entailment threshold admits one and rejects the other.**
Therefore the release gate — *"Zero false admissions AND zero false rejections, green on every commit"* (line 201; K6 line 332) — **is not achievable by the mechanism proposed.** It demands zero error on a problem where the two classes are identical along the axis it measures. The synthesis half-sees this at line 408 but has the sign backwards: it fears the gate is too WEAK to catch bad relations. The measurement shows it is simultaneously too STRONG to admit good ones — and those are the same fact.

**(c) The synthesis's own centrepiece is banned by its own contract.** The CORPUS CENSUS — "THE THESIS, and it is true by construction" (line 97), "fires unchanged" (line 138), item 3 of the composer (line 214). Executed: *"Across the 41 divergent pairs among the 137 works retrieved for this review, 29 divide along the uni

### SURVIVES
SURVIVES (confirmed): (1) Both code claims. `validate()` is imported at cellcog_composer.py:49 and never called — and worse, its ONLY call site repo-wide is synthesis_contract.py:311 inside its own self_test(), so the gate has never touched a real sentence; Premise/Synthesis/OPERATIONS are likewise imported-and-unused. The only thing between LLM prose and the page is the regex _clean(). (2) mechanisms at :167 is copied unchecked — now QUANTIFIED: 52% of declared mechanisms are absent from their own span, 43% are in neither span nor claim, and 'task displacement' is bound to Bresnahan et al. (2002), which never says it. The two-hop launder is live. (3) The synthesis's own "93% deleted" figure — independently reproduced (94% doc-wide from VERDICT_VOCAB alone). (4) "No new particular" is NOT a sufficient invariant: three fabrications assembled entirely from existing particulars (subsumption inversion, mechanism transplant, sign inversion) are ADMITTED by the real gate. (5) The synthesis's DIAGNOSIS — it names this hole itself at lines 190-191 and 408, honestly.

DIES: (1) Its headline invariant, line 163 — "fabrication... is never the assertion of a RELATION" — is FALSE, and contradicts its own line 191. (2) Its REMEDY. Property 3 (synthesis entailment) cannot separate insight from fabrication, because both are non-entailed, non-contradicted relations over true particulars — they occupy the same cell. Measured: the contract's premise-independent rules reject 76/78 (97%) of the exact prose the judge scored 9.8/10, including the flagship "informality buffer" synthesis, which is non-entailed BY DESIGN — cellcog itself says its syntheses "connect findings no single paper contains." (3) Its RELEASE GATE. K6's "zero false admissions AND zero false rejections" is unachievable by the proposed mechanism — it demands zero error where the classes are identical along the measured axis. (4) Its OWN CENTREPIECE. The corpus census — "THE THESIS, true by construction" — is rejected by its own rule 4 (synthesis_carries_a_digit), and the proposed COVERAGE_GAP exemption does not cover it; no operation for it exists in OPERATIONS at all.

REFUTED (my own hypotheses, stated plainly): number-injection into claims is 0/133 — does not fire. The 60-char span-prefix gate is a real design flaw (99% of cards have unverified span tails) but has ZERO live exploits — all 7 divergences are benign PDF de-hyphenation. Latent, not active.


### FIX
THE INVARIANT THE SYNTHESIS IS GROPING FOR AND NEVER STATES. Replace "no new particular" with:

  EVERY SENTENCE IS EITHER ATTRIBUTED OR OWNED.
  - ATTRIBUTED: names a source. Must be ENTAILED by that source's own VERBATIM SPAN (not its claim). Carries the numbers, the years, the N's. Fabrication is banned absolutely here.
  - OWNED: reviewer's voice, first person. MAY NOT name a source. MAY NOT carry a particular absent from the ledger. Must be NON-CONTRADICTED by its premises — but is EXPLICITLY PERMITTED to be non-entailed, because that is what insight IS.

Fabrication = an ATTRIBUTED sentence its source does not entail. Insight = an OWNED sentence its premises do not entail. They are the SAME LOGICAL SHAPE and are distinguished by WHOSE VOICE THEY ARE IN — not by entailment. cellcog already does exactly this and is paid 9.8/10 for it: "WE PROPOSE, AS ANALYTICAL SYNTHESIS, that informality functions as..." The gate is not "is this entailed" but "is this MARKED as non-entailed."

CONCRETELY, IN ORDER:
1. FIX THE INPUT BEFORE THE GATE. cellcog_composer.py:167 — `mechanisms` must carry a char offset into the source or be DROPPED (43% are inventions today). And :335 — hand the writer the SPAN, not the LLM-composed `claim`; or require claim-entailed-by-span. Property 3's ground truth is currently an unverified paraphrase, so it would CERTIFY fabrication rather than catch it.
2. SYNTHESIS LANE: REJECT ON *CONTRADICTED*, NOT ON NEUTRAL. NEUTRAL is the class containing BOTH insight and the residual fabrications — rejecting on it is a category error and costs 97% of the 9.8/10 prose. CONTRADICTED-rejection kills sign inversion (A3), the class that is actually checkable.
3. MECHANISM TRANSPLANT (A2) IS FULLY FIXABLE IN CODE TODAY — no LLM. synthesis_contract.py:200 unions mechanisms across ALL cited premises. Make it a typed edge: Synthesis.mechanism_premise_id AND Synthesis.effect_premise_id, and require they be THE SAME PREMISE. Deterministic set membership. (The synthes


## LENS: what-actually-wins — **CONFIRMED**

## 0. FIRST: MY OWN BRIEF CONTAINS A UNITS ERROR, AND I AM NOT GOING TO REPEAT IT

My lens was handed the claim that the declared-evidence-constraint lever is "worth +5.0 — the SINGLE BIGGEST measured win on the board." I verified it, and **that is a units error of exactly the species LENS 1 caught in the synthesis.**

`+5.0` is in **raw criterion points**. I read the real weighting code (`third_party/deep_research_bench/utils/score_calculator.py:136-152`): criterion weights sum to **1.0 within each dimension** (4.0 total across 4 dims), so a criterion's *global* weight is `dim_weight x crit_weight`. "Exclusive Citation of 'High-Quality Journal Articles'" = `0.25 x 0.15 = 0.0375`.

Rebuilding T and R from the three judge calls made today (`outputs/judge_feedback{,_bodhi,_cellcog}.json`) through the harness's own `calculate_weighted_scores`:
```
OURS      T=6.3454  R=8.0326  overall=0.4413   (insight 6.45 | compreh 7.22 | instr 6.11 | READ 4.71)
BODHI     T=8.9300  R=7.5451  overall=0.5420
CELLCOG   T=9.3842  R=7.3632  overall=0.5603
```
Every number in my context is confirmed exactly. But then:

**Journal criterion, us 1.5 -> cellcog's 8.0: dT=+0.244 -> overall +0.0093.**
Not "+5.0". **+0.0093** — sitting exactly ON the k=5 resolvable effect (+0.0094) the synthesis itself cites. The lever is real, and it is *cheap*, but it is not a gap-closer. Anyone booking "+5.0" is making the same mistake as "log-words = +0.0069/SD."

**And F3 SURVIVES.** I took all five judge-verified levers to *cellcog's own measured per-criterion scores* — the ceiling of what these levers can buy: **+0.0444.** Add the whole shape bundle: **+0.0585** — 49% of the 0.119 gap. To actually *reach* 0.5603 at R=8.03 you need **T = 10.24 — above the judge's 0-10 cap.** "No subset of criteria closes the gap; the objective is not additive" is CONFIRMED by the judge's own per-criterion data. The synthesis's most important structural insight is right.

**So the plan is not refuted by these levers. It is refuted by what it does with them.**

---
## 1. THE SCORECARD: 3 OF 5 HAVE A HOME. TWO DON'T EXIST IN THE PLAN AT ALL.

| lever | gw | us | cell | worth | home in the plan? |
|---|---|---|---|---|---|
| **L1 declared evidence constraint** | .0375 | **1.5** | 8.0 | +0.0093 | **ABSENT — AND ACTIVELY DELETED** |
| **L2 evidence-TYPE diversity** | .0435 | 5.0 | 9.5 | +0.0075 | **ABSENT** |
| L3 named tagged syntheses | .0640 | 6.4 | 9.8 | +0.0083 | PRESENT (corpus census, :99/:214) |
| L4 reconciling conflicts | .0800 | 5.8 | 9.6 | +0.0116 | PRESENT (contradiction index, :96) |
| L5 summary table | .0350 | 4.4 | 9.3 | +0.0068 | present, **BOOKED AT ZERO** |
| **+ the "cosmetics" bundle** (L1/S1/S2/F1/A1) | .105 | 4.83 | 9.04 | **+0.0167** | **BOOKED AT ZERO** |

**L1 — grep for `evidence constraint` / `scope statement` / `methodolog` / `declares` across all 412 lines of the synthesis: ZERO HITS.** The plan never once proposes that the document *state* its evidence constraint. Its only engagement with the concept is at **:218 and :386, where it DELETES it**: *"delete the hardcoded abstract at `cellcog_composer.py:400-414` ... a fabricated compliance claim aimed squarely at the instruction-following grader, and the most dishonest line we currently ship. It dies first."*

Here is what the judge actually rewards. **Bodhi's first four lines** (`outputs/bodhi_72.md:1-4`):
> `## Scope, assumptions, and how "AI-driven restructuring" is treated in this review`
> `- **Scope**: peer-reviewed, English-language **journal articles** on ...`
> `- **Evidence constraint**: I only cite journal articles. Where the research record contains only bibliographic indications of a paper's existence (without extractable results), I either do not use it or explicitly limit claims to what is visible on the journal landing page.`

Judge: *"Article 1 **explicitly states an evidence constraint to cite only journal articles**"* -> **8.2 vs the reference's 3.2.**

And cellcog's structured abstract does **L1 and L2 in one paragraph**:
> `**Methods.** The review draws on approximately 96 English-language peer-reviewed journal articles from economics, management and operations, sociology and technology studies, and applied health and education venues, spanning the early 1990s through April 2026.`

Judge: *"explicitly states a peer-reviewed journal-article restriction"* -> 8.0. And *"compares seminal theory, causal empirical studies, meta-analyses, field experiments, administrative data, and qualitative labor-process work"* -> 9.5 on Depth. **The structured abstract — which the synthesis lists in the cosmetics bundle and books at ZERO — is the delivery vehicle for the two levers it misses.**

**L2 — the plan's WEIGHT function (:153) is `relevance x venue standing x citations x recency-fit x groundability`. There is no study-design term.** Its coverage-matrix cells are *facets of criteria* — topics — and its STOP rule is "when the matrix is full." A topically-complete, design-monotonous corpus passes every gate the plan has. The judge pays +2.6/+3.1 for the *mix of evidence kinds*, and nothing in the plan aims at it.

---
## 2. WHAT WE ACTUALLY SHIP INSTEAD — AND WHY THE PLAN WOULD SHIP IT AGAIN

Judge, on us: *"explicitly **admits** that the corpus includes secondary, unknown-tier, and non-primary materials"* -> **1.5/10.** That is `outputs/rank10_sections_compose/report.md:47`:
> `Limitations: The corpus skews heavily toward secondary and synthesized sources, with only 6% of materials classified as T1 primary studies ... a further 15% of sources remain of UNKNOWN tier ...`

Bodhi and we are **making the same honest disclosure about thin evidence.** Bodhi frames it as **a constraint honored** (8.2). We frame it as **a deficit confessed** (1.5). Same integrity. Opposite rhetoric. **A 6.7-point spread on framing alone.**

And the synthesis's integrity regime *mandates the losing frame*: *"Three tiers, all three counts always published"* (:92), *"the exclusion rate is published"* (:93), *"Missing texture is narrated as missing"* (:88). Executed as written, **the plan reproduces the 1.5/10.** Its honesty is not the problem. Its *rhetoric of honesty* is.

The bitter irony: the plan's own Stage 1 (hard SELECT gate on the **citable** pool) + Stage 0 (`scope.venue_class` derived from the prompt's own words) **would make the deleted sentence TRUE.** The plan builds the machinery that licenses the declaration, then deletes the declaration, and never re-issues it.

---
## 3. THE BIGGER MISS: "SHAPE = 0" IS REFUTED BY THE JUDGE'S OWN WRITTEN CRITIQUE

Our worst dimension is READABILITY: **4.705 vs the reference's 8.420.** The judge's reasons, verbatim:
- **S2 (3.5, our worst criterion, -4.7):** *"Many paragraphs are **extremely long** ... The result is a **fragmented narrative** despite the use of headings."*
- **F1 (5.5):** *"the layout is visually heavy because of **very long paragraphs, lack of tables, and absence of a bibliography**."*
- **L1 (4.5):** *"the prose is frequently **dense, repetitive, and awkward**."* **A1 (5.5):** *"Its **density** and abrupt transitions."*

**Every one of those is a shape defect. The pure-shape bundle (L1/S1/S2/F1/A1) taken to cellcog's levels = dT +0.442 = +0.0167 overall — 1.8x the k=5 MDE, 14% of the entire gap.** The synthesis does it "in one afternoon" and **books ZERO** (:9, :104, :218, :344).

And E0, the regression that licensed booking zero, **cannot see the channel that matters**:
- The board `.jsonl` files hold the **RAW submissions** (bodhi's has 140 `[n]` markers). The judge scores the **CLEANED** article. `prompt/clean_prompt.py:28`: *"remove all citation links, citation marks ... **reference lists**, footnotes"*. **Every bibliography on the board is deleted before scoring.** So E0's `[n] markers r=+0.226` is a regression on a feature the judge literally never reads — and our journal identity, which lives *entirely* in the `[n]` markers and the stripped reference list, reaches the judge as **nothing**. That is *why* the judge says we have "no formal citations."
- The synthesis's own honest-unknowns admit the paragraph null "has no support at our operating point."

**The plan's single best idea is "the grader is a queryable oracle and we have been throwing away its answers" (Stage 5 / E1). Its central claim — F2, shape ~ 0 — was decided without asking the oracle. When you ask it, for $0.11, its #1 complaint about us is shape.**

---
## 4. BONUS, SAME ROOT CAUSE: KILL RULE K1 IS ARITHMETICALLY UNSOUND

E2/K1 treat R as a constant to be read once: *"Max achievable = 10/(10+R)"*; *"If R >= 7.5 ... cellcog sits at ~97% of the theoretical maximum ... both plans' gates are unreachable by construction."*

Execute it exactly as written. E2 reads `reference_total` from our own scored run: **R = 8.0326.** K1 fires (8.03 >= 7.5). Ceiling = 10/(10+8.0326) = **0.5545**.
**cellcog scored 0.5603 today — same judge, same task, same reference. The "analytic ceiling" is already exceeded by a

### SURVIVES
**THE SYNTHESIS'S SPINE SURVIVES — F3 IN PARTICULAR, AND IT SURVIVES ON MY OWN NUMBERS.** All five judge-verified levers, taken to cellcog's own measured per-criterion scores, buy **+0.044**; add the entire shape bundle and it is **+0.059** — half the 0.119 gap, not all of it. Reaching cellcog's 0.5603 at R=8.03 requires **T = 10.24, above the judge's 0-10 cap**. "No subset of criteria closes the gap; the objective is not additive" is CONFIRMED by the judge's own per-criterion table. So is the 0.263-system finding, the ResNet/citation-sort mechanism, the never-fired `validate()`, and the contradiction index (which is aimed at the judge's single heaviest paying criterion, w=0.080, and is the plan's best-aimed component).

**WHAT DIES IS THE ACCOUNTING, NOT THE THESIS.** The plan has exactly two boxes — CONTENT (booked) and COSMETICS (zeroed) — and the judge pays for two things that fit in neither:
1. **DECLARED COMPLIANCE.** Telling the judge in prose which constraints you honored. Costs four bullets. Worth **+0.0093** — on the nose of the plan's own +0.0094 kill threshold, at ~1% of the cost of the "afternoon" it prices at "0.00-0.02". The plan doesn't under-book it; **it deletes it, and never re-issues it — even though its own hard SELECT gate would make it TRUE.**
2. **EVIDENCE-TYPE COMPOSITION.** Not what the evidence is *about* but what *kind* it is. The plan's WEIGHT function and coverage matrix have no axis for it.

**AND THE ONE THE LENS DIDN'T ASK ABOUT IS BIGGER THAN BOTH: "book shape at ZERO" is refuted by the judge in writing.** The pure-shape bundle is worth **+0.0167 — 1.8x the resolvable effect** — and the judge names the cause twice in its own critique ("extremely long paragraphs", "a fragmented narrative"). E0, the regression that licensed the zero, is computed on RAW submissions while the judge scores CLEANED text with every reference list and citation marker stripped (`clean_prompt.py:28`) — so it is structurally blind to the only channel by which journal identity reaches the grader.

**Our 1.5/10 and bodhi's 8.2/10 contain the SAME honest disclosure.** Bodhi: *"I only cite journal articles; where the record is thin I limit my claims"* — a constraint honored. Us: *"the corpus skews heavily toward secondary sources... 15% UNKNOWN tier"* — a deficit confessed. **The plan's integrity regime ("all three counts always published", "the exclusion rate is published") systematically mandates the losing frame.** The honesty is not the problem. The 


### FIX
**1. RESTORE THE DECLARATION — AND MAKE IT TRUE. The plan already owns both halves; it just never joins them.**
Stage 0 already derives `scope.{venue_class, recency, language, topic_statement}`. Stage 1 already enforces it (hard SELECT gate on the *citable* pool). Stage 5 already computes counts in code (`COVERAGE_GAP`: *"the count computed in code from `len(corpus)`, never emitted by the LLM"`). **Add one step: RENDER `brief.scope` as the document's opening Scope/Methods block, with every count read from the evidence ledger.** It is then honest *by construction* — the numbers cannot be fabricated because the LLM never emits them. This converts the plan's "most dishonest line" into a true one and reclaims **+0.0093 for four bullets.** Make it a `MUST-ADMIT` case in the adversarial suite so the integrity floor cannot delete it again.

**2. FLIP THE FRAME ON THE TIER CENSUS.** Keep every count. Publish it as **CONSTRAINT HONORED**, not **DEFICIT CONFESSED** — bodhi's exact move: *"Where the record contains only bibliographic indications without extractable results, I either do not use it or explicitly limit claims."* Same information, same integrity, +6.7 raw points. The QUOTABLE/ABSTRACT-CITABLE/NAMED tiers become the *statement of method*, not the *admission of failure*.

**3. ADD AN EVIDENCE-TYPE AXIS.** The coverage matrix gets a second axis — `{seminal theory, causal/quasi-experimental, meta-analysis, field experiment, administrative data, qualitative/labor-process}` — derived per domain like everything else. The WEIGHT function (`relevance x venue x citations x recency x groundability`) gains a **design-diversity** term, and STOP requires the design mix to be filled, not just the topical cells. Cheap: it is a re-query, not a new subsystem.

**4. UN-ZERO SHAPE. Book it, counter it, and do it FIRST — not "one afternoon", unowned and undated.** It is +0.0167, 1.8x the MDE, and the judge has already written down the mechanism. Give it K5 mechanism counters (median p



# THE ADJUDICATION

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
|---|---|---|-


## SURVIVES
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


## DIES
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


## MUST RE-VERIFY
- **THE R-DRAG MAGNITUDE (dR/dT = -0.21) IS n=3 SINGLE CALLS.** The SIGN is proven without regression (R fixed at 8.033 makes cellcog's 0.5603 require T=10.24 > cap). The MAGNITUDE is not. It is now load-bearing for the ceiling, for every lever's value, and for both plans' arithmetic. **Re-run judge_feedback k=5 on all three targets, capturing R.** ~$3.
- **EVERY PER-CRITERION NUMBER IN MY LEVER TABLE IS n=1.** The judge scores all 25 criteria in ONE call, so they are halo-correlated. **E6 (per-criterion SD matrix, $0.55 on the 5 banked noise_r10_* artifacts) must run before any criterion is called a deficit.** The RANKING of the top levers is probably robust (1.5 vs 8.0 is not noise). The VALUES are not.
- **THE 0.263 SYSTEM NUMBER IS NOT A GENERALITY NUMBER.** Those five runs are ABORTS, five weeks stale. **Re-run the CURRENT pipeline end-to-end, to completion, on >=2 non-72 tasks (~$3).** Until then we have never measured generality — we have 38 consecutive task-72 runs.
- **THE SHAPE BUNDLE (+0.0270) ASSUMES WE CAN REACH CELLCOG'S READABILITY SCORES.** Our 677-word median paragraph is the 99.7th percentile of 898 articles — E0's null has NO SUPPORT there. **E4 (k=10 paired, content and word count held fixed, paragraphs split) SIZES it.** It is now a sizing experiment, not a go/no-go: the judge has already told us in writing that the effect exists.
- **IS A JOURNAL-ONLY CORPUS EVEN ACHIEVABLE?** The judge names WEF, IDC, PwC, IBM, Deloitte, Gartner, Goldman Sachs in our prose. **BEFORE declaring the constraint, MEASURE: what fraction of the coverage matrix is fillable from journals alone?** If it is not fillable, the declaration must be SCOPED to what is true. **A declaration we cannot honor is precisely the fabrication we are trying to kill.**
- **cellcog's 0.5603 AND bodhi's 0.5420 ARE BOTH n=1** (bodhi's board raw_results says 0.5441; my recompute says 0.5420 — that spread IS the noise). k=5 them ($0.55) before any gate is set from them.
- **K2 STANDS UNCHANGED AND UNRUN:** if the compiler's weighted rubric-mass recall against the 100-task ground truth is < 80%, the derivation layer is sand — fall back to the static rubric and downgrade the generality claim IN WRITING.