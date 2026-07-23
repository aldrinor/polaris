# PIPELINE_GAP_AUDIT — Phase 3 — LOSSLESS consolidation of Sol + Fable

Provenance: both Phase-3 verdicts read line-by-line by Opus. Both ingestion receipts VERIFIED against
ground truth (all 7 prior artifacts, exact line counts 245/462/472/424/1147/272/335, FIRST/MID/LAST verbatim).
Attribution tags: **[S]** = Sol only, **[F]** = Fable only, **[S+F]** = both independently found it.
Nothing compressed away; where the two overlap, every distinct file:line / weight / test from each side is kept.

Repos: pipeline `/home/polaris/wt/faithoff` (design-only — NO pipeline file modified in Phase 3).
Sub-item weights cite `SCORING_SPEC.md`; winner moves cite `COMPETITOR_TEARDOWN.md`.

---

## 0. THE SHARED VERDICT (both investigators, independently)

**[S]** "POLARIS is not losing task 72 primarily because it lacks evidence or a report skeleton. It loses
because the plan does not turn the question into testable analytical obligations, the relationship layer does
not build context-aware propositions, and the active composer often receives neither."

**[F]** "The all-levers-ON config (mf_max mean 0.4933) does NOT beat the all-levers-OFF baseline
(mf_baseline mean 0.5009) — the current lever set is measured FLAT-to-negative. We now sit AT reference
parity, while current-tab winners hold Insight 54.6–57.1 and legacy winners 58.5–61.5. The remaining climb is
exactly the Phase-2 winner behaviors, none of which our stages currently produce or demand."

**[S+F] The single structural thesis for Phase 4:** the fix is ONE pre-generation analytical contract, shared
by outline + retrieval-admission + relation-planning + the **active verified-compose producer** + semantic
acceptance. **[S]** "Adding more advisory prompt prose or more independent flags will repeat the measured-flat
failure unless the contract changes evidence ownership and is consumed by the producer that actually emits
verified sentences."

### 0.1 Measured state (task-72, RACE = target/(target+ref), parity = 0.5)

**[S]** Live RACE for record 72 (`results/race/faithoff_t72/raw_results.jsonl:1`):
Comp **0.4733**, Insight **0.4489**, Inst **0.4455**, Read **0.3981**, Overall **0.4486**.
Old `champ_ourcorpus`: 0.3924 / 0.3411 / 0.3717 / 0.3640, Overall 0.3671.
FACT (`results/fact/faithoff_t72_fact/fact_result.txt`): 11 citations, 11 valid, valid_rate 1.0 — high precision,
low supported-pair VOLUME vs 111 distinct in-prose markers + 147 bibliography entries
(`outputs/faithoff_t72/compose_summary.json:30-38`).

**[F]** Full scoreboard trajectory (word/heading/table counts from cleaned articles):

| run | overall | comp | insight | inst | read | words | headings | tables | notes |
|---|---|---|---|---|---|---|---|---|---|
| champ_ourcorpus | 0.3671 | .3924 | .3411 | .3717 | .3640 | 2,563 | 13 | 0 | old champion |
| faithoff_t72 | 0.4486 | .4733 | .4489 | .4455 | .3981 | 7,697 | 14 | 0 | wall-paragraph era |
| 7phase_full_draw_1/2 | 0.4945/0.4769 | .5023/.4863 | .4977/.4894 | .4981/.4634 | .4635/.4494 | 7,163 | 49 | 8 (malformed) | 7-lever |
| **mf_baseline_1/2/3** | **0.5088/0.5017/0.4922** | .505/.5048/.4884 | **.5212/.513/.5005** | .5003/.4963/.4845 | .502/.4785/.4936 | 5,898 | 9 | 0 | ALL levers OFF |
| mf_max_1/2/3 | 0.4875/0.4943/0.4982 | — | .5038/.50/.5089 | — | — | 6,972 | — | — | ALL levers ON |
| fable5_scoped (manual) | 0.5065 | .4992 | .5131 | .4941 | **.5262** | 3,071 | 11 | 14 | per-para deduction |

**[S]** same-harness replicated arms (`run_race_max_focus.sh`): baseline mean Overall 0.5009, full 0.4966,
max 0.4933. max−baseline = −0.0073 Insight / −0.0075 Read / −0.0076 Overall — all INSIDE the ±0.027 single-judge
noise and directionally NEGATIVE. **[F]** baseline draws span 0.4922–0.5088 (range 0.017 overall, up to 0.024/dim)
→ this IS the ±0.027 noise bar every small test must clear.

**Decisive shared fact [S+F]:** the current levers are measured flat-to-negative; the climb is the winner behaviors.

### 0.2 CRITICAL wiring facts Phase 4 must respect (both flagged — do not skip)

1. **[S]** The active prose producer is **`_compose_section_per_basket`** (verified-compose primary branch);
   **`_call_section` is only the `else` branch** (`multi_section_generator.py:6630-6728`). **A correct prompt
   addendum routed only to `_call_section` still misses the producer that emits the sentences.** Any Phase-4 fix
   must be consumed by the primary branch.
2. **[F]** In the measured CHAMPION config (`mf_baseline .../draw_3 compose_summary.json resolved_lever_states`):
   `PG_RENDER_BLOCKS=1`, EVERYTHING else OFF/empty (`PG_SECTION_STRUCTURE=0`, `PG_CONTRADICTION_MINING=''`,
   `PG_RELATION_EVIDENCE_PACKS=''`, `PG_SCOPE_DEEPENING=''`, `PG_COVERAGE_SPINE=''`,
   `PG_RQ_SOURCE_ELIGIBILITY_ENFORCE=''`, `PG_STRICT_VERIFY_OFF=1`, entailment off). So the binding constraint on
   prose today is the **WRITER PROMPT TEXT itself** — the strict-verify sentence-drop machinery is bypassed, but
   the writer is still TOLD the closed-world rules (see U1).
3. **[S+F] Faithfulness path is NOT the cause and stays untouched.** `provenance_generator.py:3714-3943` /
   `:4637-5252` (rewrite + citation resolution) and `clinical_generator/strict_verify.py:387-574` (identifier/
   span/numeric/overlap/entailment checks) are claim-admission controls, not score planners. Source eligibility,
   analytical coverage, paragraph ownership, comparison design must be solved UPSTREAM.
4. **[S]** RACE exposes only 4 dimension scores, not per-criterion scores. Prioritization below uses
   `effective weight × (1 − observed dimension score)` as a TRANSPARENT PROXY only — never a fabricated per-cell
   score. Proxy: 0.04408 per 0.080 Insight cell, 0.03819 per 0.0725 Comp cell, 0.03527 for the 0.064 cell.

---

## 1. UNIFIED GAP REGISTER (U1–U14) — weight × headroom order

Each row: **GAP** (quoted file:line, both sides) · **SUB-ITEM LOST** (weight) · **WINNER MOVE** (teardown) ·
**FIX** (generalized, pre-generation, faithfulness untouched) · **SMALL TEST**.

---

### U1 — The writer contract structurally FORBIDS the per-paragraph deduction that wins the two 0.0800 Insight cells
Maps: **[F GAP-1]** + **[S G1 winner-move]**.

**GAP.** **[F]** `multi_section_generator.py:3517-3519` (SECTION_SYSTEM_PROMPT_TEMPLATE, CRITICAL RULES): "1. Use
ONLY facts present in the <<<evidence:ev_XXX>>> blocks below. Do not introduce outside information." + "2. EVERY
sentence must end with at least one [ev_XXX] marker." Retry contract doubles down (`:4420-4432`): "If a sentence
cannot carry a real [ev_XXX] marker, do not write that sentence." A *derived implication* is by definition the
writer's inference, not a fact "present in" any single block → the prompt instructs the model NOT to write it.
Observed: `mf_baseline_draw_1` has only **6 implication-family tokens in 5,898 words**; champ_ourcorpus "almost no
paragraph ends with a derived implication" (TEARDOWN Part 6 [F]-1). The reference has a "this implies/suggests"
clause ending essentially every mechanism paragraph (ref:38,:98,:100,:147,:172,:184,:207,:257). **[S]** the
writer's causal rule at `:3532-3540` is CONDITIONAL ("When the current section concerns a mechanism") so it
cannot create a missing implication either.

**SUB-ITEM LOST.** **[S+F]** Insight #7 "Mechanisms of restructuring" **0.0800** + Insight #8 "Critical
cross-industry synthesis" **0.0800** — the two largest cells (`SCORING_SPEC I.7`). The 8–10 band is gated on
"deeply analyzes interplay and causal mechanisms, rather than a superficial listing" and "second-order effects."
Evidence: our Insight 0.50–0.52 vs cellcog 57.08 / Qianfan 61.48; fable5_scoped's only parity-beat (Insight
.5131) came with exactly this per-paragraph deduction cadence — **[F]** "the single biggest winner-vs-midscorer
difference" (TEARDOWN Part 5 Pattern 1).

**WINNER MOVE.** **[S+F]** Pattern 1 "DEDUCTION APPENDED TO DESCRIPTION" + Bodhi N1 labeled-deduction template
("end every evidence unit with a bolded `Implication:` clause" — addendum F5, "cheapest implementation of
Pattern 1"); win-map #7 move 3 (`COMPETITOR_TEARDOWN.md:274-280`).

**FIX (writer prompt; PRE-gen).** **[F]** Add ONE licensed-inference class to the section writing contract:
*"After the cited findings of a paragraph, close it with one inference sentence stating what those already-cited
findings jointly imply — a mechanism, boundary condition, reconciliation, or consequence. It must follow only
from the cited sentences of that same paragraph, introduce no new number/entity/factual claim, and carry the
union of that paragraph's evidence markers."* Optionally shipped as a bolded label (Bodhi form), writer-chosen not
hardcoded. **WHY GENERAL:** a discourse-structure rule (evidence → derived implication); names no task/domain/
count/vocabulary; the benchmark's insight-criteria generator rewards it on every task (`criteria_prompt:256-282`
is task-independent). **FAITHFULNESS:** the inference carries the paragraph's own markers and introduces no new
factual token (deterministic, testable) → same class as today's cross-source synthesis sentences; the
comparative-recovery path `:4648-4735` already handles multi-span sentences. NOT a post-gen edit.

**SMALL TEST.** **[F]** (a) Zero-LLM structural assertion: `paragraph_deduction_rate` = fraction of ≥3-sentence
body paragraphs whose final sentence is connective/inferential with NO new numeric token vs preceding sentences.
Before (mf_baseline_draw_1) ≈ 0.16; target > 0.6; PLUS a zero-new-number canary (faithfulness). (b) 3v3 paired
same-judge RACE probe on Insight; the effect separated fable5 (.5131) from champ (.3411) locally and 57-vs-50 on
the board → expected +0.02–0.04 normalized clears ±0.027 on the paired mean (decide on paired mean, not single
draws).

---

### U2 — No mechanism/causal-chain spine that exists BEFORE evidence and is REUSED as report architecture
Maps: **[S G1 main fix]** + **[F GAP-2]**.

**GAP.** **[F]** `multi_section_generator.py:939-960` `_FACET_SKELETON_ADDENDUM` fixes exactly FOUR roles
(overview / thematic bodies / ONE synthesis / conclusions+gaps). There is **no explanatory-framework/mechanism
role**; a "Theoretical Frameworks" section exists only if the corpus happens to yield that facet. Nothing tells
downstream sections to REUSE the framework's channels. **[S]** the outliner bars itself from inventing mechanisms
(`outline_agent.py:1324-1331,1447-1458` — only a concrete aspect explicitly asked justifies expansion); the
skeleton "does not guarantee a causal spine" (`multi_section_generator.py:917-950`). Observed: champ_ourcorpus's
mechanism spine is only "substitution vs complementary effects" then an unrelated model-fit statistic; framework
channels never appear as organizing vocabulary in empirical/sectoral section foci (`multi_section_outline.json`).

**SUB-ITEM LOST.** **[S+F]** Insight #7 **0.0800** (make mechanism the *reusable architecture*, not isolated
prose) + Insight #9 4IR-integration 0.0480; **[S]** secondarily #11 implications 0.0480.

**WINNER MOVE.** **[S+F]** Pattern 2 "MECHANISM-FIRST ARCHITECTURE — early theory/mechanism section reused by the
rest" (ref §2→§3-8; AI-Q mechanism_explorer subagent + architect "Mechanism constraints"; Qianfan :193-218;
`COMPETITOR_TEARDOWN.md:221-224`). **[S]** "put the mechanism framework before evidence, specify forces and a net
condition, reuse it, end mechanism paragraphs with a derived implication."

**FIX (outliner; PRE-gen).** **[S]** Before outlining, compile analytical obligations from the question's semantic
operator. When it asks how/why/impact/change/causation, require evidence-backed **causal chains** with fields:
conditions, process, intermediate outcome, final outcome, moderators, and the condition governing net direction.
Attach each chain to the baskets supporting its individual links; assign it as a reusable lens to relevant
sections; if evidence supports only part, plan the BOUNDARY rather than complete it. **[F]** Extend the skeleton
with a 5th role + reuse contract: *"When the question is analytical (effects/impacts/causes/drivers/feasibility/
change), include ONE explanatory-framework section immediately after the opening, whose focus enumerates the
causal channels the assigned evidence supports; and write every thematic body section's focus to name which
channels its evidence tests, extends, or bounds."* Question-type trigger uses the existing per-run constraint
extractor (`compose_agentic_report_s3gear329.py:398-410`), not hardcoded keywords. **WHY GENERAL:** reacts to
question semantics + evidence relations, not this task/domain/fixed menu; channels still EMERGE from evidence.
**FAITHFULNESS:** outline/focus text only; every sentence still evidence-cited.

**SMALL TEST.** **[S]** feed planner a causal fixture, a descriptive fixture, and evidence with one deliberately
missing link; deterministically assert causal obligations + supported-link ownership appear ONLY for the causal
fixture and the missing link becomes a boundary; compose short sections from frozen baskets **through the active
producer** and assert the same mechanism identifiers govern theory/comparison/implication plans without leaking
into prose. **[F]** on `multi_section_outline.json`: (i) framework-role section at position ≤2 when constraints
mark the question analytical; (ii) ≥50% of body foci contain a framework channel term (string containment, ~1
outline call). Then paired Insight RACE probe (mean Δ > 0.027).

---

### U3 — Cross-study synthesis is a late writing request, not a precomputed relation plan; the contradiction miner throws away the exact divergences the rubric pays for (yield 0)
Maps: **[S G2]** + **[F GAP-3]**.

**GAP.** **[F]** `contradiction_mining.py:123-126` (judge): "Different populations, methods, periods, measures,
endpoints, or observed-versus-modelled results are not automatically conflicts … classify them as
non_comparable." and `:167` `find_contradictions` keeps ONLY `classification=="conflict" and confident==True` —
the `non_comparable`/`compatible` verdicts, WITH their boundary `reason` (`:132`), are DISCARDED. Measured yield
on real task-72: **`contradictions_detected: 0`** (`mf_max-…draw_1/compose_summary.json`). Only consumer is a
hedging block (`contradiction_hedging.py` via `_call_section:4345-4360`) — a hedge, not an explanation. **[S]**
the generic skeleton allocates exactly ONE combined synthesis+contradictions section (`:944-950`); in the real
outline it got 17 evidence IDs while "Additional Corroborated Findings" got 433 (`multi_section_outline.json`
sections 10 & 12); the valuable reconciliation in article line 43 is compressed into one wall paragraph.

**SUB-ITEM LOST.** **[S+F]** Insight #8 **0.0800** (8–10 band = "patterns, sector variation, consensus, debate,
uncertainty rather than a catalog") + Comp #5 literature depth 0.0435; **[S]** also #22 sourced synthesis 0.0210.
**[F]** THE definitive wrong-wiring finding: the lever ran, cost LLM calls, produced zero usable structure — its
output set is EMPTY BY CONSTRUCTION on literatures whose "disagreements" are level/method/period differences
(nearly all of them; ref:81 divergence by technology/period/geography/level/methodology/outcome).

**WINNER MOVE.** **[S+F]** Pattern 3 "EXPLAIN DISAGREEMENT not report it" (ref:73/:81/:291-294; Dalpha ":41 not
contradictory; they measure different levels of adjustment"; Lunon "design-induced artifact"; DRAGged: explicit
conflict reasoning "significantly improves" quality). **[S]** "state a reconciliation thesis, extract
cross-context patterns, explain disagreement through unit, margin, technology, horizon, method, institutional
setting."

**FIX (evidence packing + outliner; PRE-gen).** **[S]** Build an **evidence-relation graph** before prose: for
every potentially related basket represent proposition, direction, outcome measure, unit, observation-vs-
projection, method, period, population, evidence-derived context attributes; preserve **three edge types —
convergence, qualified divergence, non-comparability**; generate planned synthesis propositions only when cited
nodes license the relation (including the moderator/measurement difference that explains it); **route these
propositions + exact source sets into the active verified-compose producer, not merely an optional writer
prompt.** **[F]** Concretely: keep the same miner+judge but harvest ALL THREE verdict classes into a **divergence
ledger** {class, subject, predicate, measure, reason}; (a) the synthesis focus receives boundary reasons as
writing obligations ("for each retained pair, state both findings with citations and explain the difference using
the recorded boundary — population/method/level/period/measure"); (b) true `conflict` entries additionally
obligate a debate treatment (both poles + what evidence resolves it). **WHY GENERAL:** the three-class taxonomy +
boundary vocabulary are domain-free comparability dimensions — the same fields `relation_evidence_packs._attributes`
already aliases (`:69-85`). **FAITHFULNESS:** untouched; routes existing admitted evidence, prose still per-
sentence cited.

**SMALL TEST.** **[F]** (a) isolated miner unit-run on the frozen corpus: assert the harvested ledger is
non-empty and ≥N pairs carry a boundary `reason` where today's confirmed-conflict-only harvest = 0 (reuses
already-paid judge verdicts). (b) synthesis section names ≥1 recorded boundary term per covered pair. **[S]** use
frozen rows with a genuine same-measure conflict, compatible-at-different-margins, and unrelated; assert the
graph produces the correct 3 relation states; compose a miniature report through verified-compose and assert ≥1
cross-source proposition survives strict verification. (c) 3v3 paired Insight probe, no FACT precision regression.

---

### U4 — No shared-dimension comparison artifact; relation-pack key is a token-bag; the only "table" is a sentence-span inventory that DEGRADES under RACE cleaning
Maps: **[S G11]** (+ G2 relation-pack wiring) + **[F GAP-4]**.

**GAP.** **[F]** (i) `relation_evidence_packs.py:56-66`: the "proposition" grouping key is a sorted token-bag of
the statement (`" ".join(sorted(_tokens(_row_proposition(row))))`) → near-random pseudo-propositions; injected as
a raw JSON dump into the system prompt (`:4188-4198`) with one sentence of guidance; measured flat. (ii)
`multi_section_generator.py:8437-8573` `_construct_synthesis_table` emits `| Finding | Value | Source |` rows
whose "Finding" cell is a literal SENTENCE SPAN of verified prose. The RACE cleaner strips the citation-bearing
Source column → malformed `| Finding | Value |` remnants duplicating body sentences verbatim, plus orphan
`Finding: …` prose lines (cleaned lines 59/61 duplicate line 42; degenerate row "| 54.11% freelancers … | 54.11%
|" cleaned line 157). This VIOLATES our own writer rule "Keep each cell to a short phrase, never a full prose
sentence" (`:3595-3600`) — the construction BYPASSES the writer. **[S]** both task-72 reports contain NO markdown
table (TEARDOWN Part 6); base writer permits a table only conditionally (`:3597-3602`); `PG_SUMMARY_TABLE_COMPOSE`
inserts a table AFTER assembly (`compose_agentic_report_s3gear329.py:746-761`) — **forbidden by the pre-generation
rule**; the max table (`report.md:41-44`) merely repeats two facts, not the shared matrix #8 needs.

**SUB-ITEM LOST.** **[S+F]** Insight #8 **0.0800** + Comp #3 industry scope **0.0725** + Read #22 anti-redundancy
0.0210 (verbatim duplication IS the redundancy case) + Read #23 table clarity 0.0140 + Read #24 layout/no-broken-
tables 0.0140. Evidence [F]: memory "cleaner KEEPS well-formed tables; ours were malformed"; 7phase Read
0.4494–0.4635 vs baseline-without-tables 0.4785–0.502 → **the table lever is net-NEGATIVE.**

**WINNER MOVE.** **[S+F]** win-map #8/#23: "sector × mechanism/outcome/evidence-strength/moderator matrix + 3-6
propositions … a table without the inference paragraph does not complete the cell"; "After each table write 2-3
sentences interpreting the key pattern" (aiq_orch.j2:67); WhaleCloud matrix + five moderators; NVIDIA matrix;
addendum F4: comparison/consensus tables ARE pre-generation-plannable.

**FIX (evidence packing + writer; PRE-gen).** **[F]** Retire the sentence-span inventory table from the judged
report (a deterministic property: any table whose only non-duplicated column is citations MUST degrade to
duplication under the citation-stripping cleaner, on every task). Replace the relation-pack key with the
comparability schema the module already extracts (`_attributes`: design/population/measure/basis/period): group
admitted rows sharing a **MEASURE across different CONTEXT** values; hand the writer per group a directive
("these cited rows report the same measure in different contexts; state the comparison and, where evidence
supplies it, the factor explaining the difference") letting the WRITER emit comparative prose OR a valid table
under the existing rule, followed by a general composition rule: "any table must be followed by one paragraph
stating the dominant pattern and exceptions." **[S]** when the relation planner finds multiple contexts sharing
dimensions, create a **table PLAN before writing**: row entities, shared columns, cell-level source ownership,
units, missingness, and the interpretive proposition it supports; if not comparable → plan prose; generate/verify
each cell as an ordinary evidence-bound unit; the post-assembly constructor is not reusable as-is. **WHY GENERAL:**
measure×context grouping + table-interpretation are domain-free discourse rules; no counts/domain words.
**FAITHFULNESS:** grouping only reorders admitted rows; prose still per-sentence cited; no post-gen injection.

**SMALL TEST.** **[F]** (a) simulated-clean lint (no LLM): strip `[N]`/citation-only columns, run
`cleaned_output_guard.find_malformed_tables` → assert 0 defects (today 8 malformed lines in 7phase) and 0 body
sentences duplicated verbatim ≥2× (today ≥2). (b) comparative-coverage counter: sentences citing ≥2 rows whose
context labels differ (today ≈ the one synthesis section; after: every section owning a multi-context group).
**[S]** comparable + non-comparable fixtures → table plan only for the former, exact column consistency, source
ownership per factual cell, preserved units, interpretation block after; through the ordinary verifier+renderer;
no post-gen insertion. (c) paired Insight+Read probe.

---

### U5 — Requested breadth is represented by concepts, not decomposed outcome dimensions; the coverage audit is toothless; gap-detection is BARRED from mechanisms/comparisons; deepening is inert
Maps: **[S G3]** + **[F GAP-5]** (+ coverage_obligations wiring both sides).

**GAP.** **[S]** the outliner stops when its gap ledger is empty and treats only NAMED missing aspects as
searchable (`outline_agent.py:1309-1332`); coverage obligations append a concept to the nearest section focus
(`coverage_obligations.py:107-136`) and the audit tests only whether the section contains ANY text (`:139-158`)
→ max audit "missing: []" is NOT semantic completion; "Effects … across various industries" is called fulfilled
solely because bound to "Economic Consequences" (`compose_summary.json:11292-11300`). **[F]** three coupled
defects: (i) `outline_agent.py:1449-1462` STRICT GROUNDING RULE: "Do NOT invent generic sub-topics, background,
history, **mechanisms, or comparisons** … if the question does not ask for it, it is not a deficiency" — but the
benchmark's criteria generator ALWAYS derives mechanism/synthesis/comparison sub-criteria from an analytical task
(`criteria_prompt:213-226`) → our gap detector is ANTI-ALIGNED with the scoring surface by explicit instruction;
(ii) `PG_SCOPE_DEEPENING` empty in every measured run — the acquisition loop never runs at this seam
(`compose_agentic_report_s3gear329.py:431` "requires_retrieval_pipeline"); (iii) `build_scope_deepening_queries`
(`scope_contract.py:415-491`) emits only topical facet queries — no typed factual/causal/comparative/critical mix
(cf. AI-Q architect "24-32 queries typed factual/causal/comparative/critical/trend"). Observed: mf_baseline_draw_1
has NO sectoral section and no 4IR section; 7phase covered 3 industries vs reference 8+.

**SUB-ITEM LOST.** **[S+F]** Comp #2 restructuring-dimension breadth **0.0725** + Comp #3 industry scope **0.0725**
+ Inst #16 various-industries 0.0375; **[F]** Comp #1/Insight #9 4IR 0.0290/0.0480, indirectly Insight #8.
Evidence [F]: Sourcery is proof-by-counterexample — a missing sector tour forfeits ~3 Comp points even with
competent insight (addendum System 4).

**WINNER MOVE.** **[S+F]** Pattern 4 "RUBRIC-SHAPED COVERAGE AUDIT before/while writing" (ZTE per-chapter audit
triggers re-research; AI-Q SATISFIED/PARTIALLY/UNSATISFIED per constraint) + Pattern 12 "let evidence change the
plan" (WebWeaver/AgentCPM/DualGraph); win-map #4 industries spanning "materially different task/institution
regimes."

**FIX (scope contract + outliner; PRE-gen).** **[S]** convert each broad requested outcome into evidence-derived
dimensions using task wording + retrieved controlled terms + reported endpoints + recurring distinctions; each
dimension carries a STATUS: supported (with evidence + a planned analytical move) / retrieval-needed /
unsupported-disclosed; **fulfillment must be SEMANTIC — the planned/emitted proposition must ENTAIL the
dimension-role pair, not merely occupy a bound section.** **[F]** (a) build a question-derived coverage ledger:
every explicitly named dimension + every named entity-CLASS quantifier (plural/"various"/"different") obligating
multiple materially distinct instances; for analytical questions add the four analytical roles (mechanism,
cross-context comparison, consensus/disagreement, implications) as ledger rows (rubric-ALGORITHM alignment, not
task literals); (b) relax the checklist grounding rule from "explicitly named" to "named OR implied by the
ledger" (ledger is question-derived, so anti-invention discipline is preserved by quoting the class noun); (c)
type deepening queries per row (factual/causal/comparative/critical — fixed TYPE vocab is general; CONTENT is
prompt-derived); (d) turn deepening ON at this seam (it exists+tested: `deepen_scope_contract:316-413`) with its
disclosed wall. **WHY GENERAL:** ledger content 100% prompt-derived; only role/type vocabularies are fixed and
they are properties of research questions, not domains. **FAITHFULNESS:** retrieval-side only; admission still
passes the same scope/type judges.

**SMALL TEST.** **[F]** (a) ledger-fulfillment telemetry (retrieval only, minutes, no full gen): every ledger row
ends with ≥1 admitted row or a disclosed unfillable; count distinct entity-class instances with class-specific
evidence (today 3 industries → reference 8+). (b) each fulfilled row owns a section/named focus clause. **[S]**
construct prompts whose broad outcomes decompose differently + a nonempty section omitting one required dimension;
assert the CURRENT audit passes the decoy but the NEW audit fails it, then passes only after a source-bound
proposition covering the dimension is planned+emitted. (c) paired Comp probe (headroom .49→.55+ dwarfs ±0.027).

---

### U6 — Industries are CATALOGED, not selected and compared as distinct regimes
Maps: **[S G4]** (Fable folds context-diversity into GAP-5; kept distinct because Sol's regime-schema is a separate mechanism).

**GAP.** **[S]** `faithoff_t72` article line 35 is one enormous sequence of occupation/sector examples — breadth
by NAME but no common fields for mechanism, adoption, outcome, institution, affected party, evidence strength.
The outline assigns 93 evidence IDs to one "Industry and Occupational Case Studies" section with a generic
case-study focus; the max audit binds "various industries" to an economic-consequences section and calls it
fulfilled (`compose_summary.json:11292-11300`).

**SUB-ITEM LOST.** **[S]** Comp #3 industry-specific scope **0.0725** + Inst #16 various industries 0.0375; also
the context BASIS of Insight #8 synthesis 0.0800.

**WINNER MOVE.** **[S]** span materially different task/institutional regimes, compare through a shared schema,
make sector variation an organizing AXIS not a list (`COMPETITOR_TEARDOWN.md:228-240`).

**FIX (evidence packing + outliner; PRE-gen).** **[S]** infer context attributes from admitted evidence; cluster
contexts by materially different mechanisms/institutions/adoption conditions/outcome margins; choose coverage for
analytical DIVERSITY not name count; build a common-schema comparison plan from dimensions genuinely SHARED by the
selected contexts; assign both context-specific findings and a cross-context proposition. **WHY GENERAL:**
"context" and the schema are discovered from evidence metadata/claims → generalizes to regions, populations,
jurisdictions, technologies.

**SMALL TEST.** **[S]** supply baskets from several named contexts incl. near-synonyms and genuinely different
regimes; assert synonym proliferation does NOT satisfy diversity, every selected context has source support, the
common-schema plan contains only shared dimensions, and the synthesis proposition uses evidence from multiple
distinct regimes; same-judge paired probe improving both Comp and Insight beyond noise.

---

### U7 — Emergent themes are never asked for; no epistemic status exists anywhere (the 0.0640 cell is unaddressed)
Maps: **[S G5]** + **[F GAP-6]**.

**GAP.** **[F]** grep-verified: NO prompt in `multi_section_generator.py`/`outline_agent.py` asks for higher-order
themes, novel perspectives, named syntheses, or epistemic labels. The synthesis skeleton role (`:952-955`) asks
only "where studies AGREE, where they CONTRADICT, and how strong the evidence is." The writer's synthesis rule
(`:3567-3570`) offers four moves (convergence/conflict/mechanism/boundary) — none is "derive a NEW relationship
and label its status." Observed: zero coined themes, zero epistemic tags in every task-72 report. **[S]** the
report makes deductions (article line 43) but their epistemic status and discriminating test are unlabeled
(`COMPETITOR_TEARDOWN.md:310-311` records the same defect); neither contradiction mining nor relation packing
induces a NEW falsifiable relationship from independent baskets.

**SUB-ITEM LOST.** **[S+F]** Insight #10 emergent themes/linkages/novel perspectives **0.0640** (3rd-largest
cell). **[F]** 'Originality' appears 38× in EN insight-criteria names → this cell exists on essentially every task.

**WINNER MOVE.** **[S+F]** win-map #10 "derive a NEW falsifiable relationship from multiple baskets + label
epistemic status + state the missing test" (cellcog four-tag protocol + ":282 No peer-reviewed study has yet
tested…"; Lunon coined themes + falsifiers N5; Xiaoyi consensus/controversy tables with Confidence columns N15;
addendum F4 "epistemic labeling has escalated from tags to ARTIFACTS — all pre-generation-plannable").

**FIX (writer prompt for the synthesis-role section; PRE-gen).** **[S]** add an **inference planner** over the
evidence-relation graph: a candidate inference must identify independent supporting baskets, the reasoning
operator connecting them, boundary conditions, an epistemic category (reported vs synthesis-derived), and an
observable that would weaken it; only source-supported premises enter strict verification; the inference is
calibrated to those premises and planned before writing (topic-independent formal reasoning over provenance
topology). **[F]** extend the synthesis-role directive (role already detected via
`relation_evidence_packs.is_synthesis_plan`/skeleton role 3): *"Beyond agreement and conflict, derive the
cross-cutting propositions the combined evidence supports but no single source states: name each, ground it in
≥2 cited findings, label its status using a fixed three-level vocabulary (directly evidenced across sources /
consistent-but-untested pattern / this review's own hypothesis), and for any non-established one state what
observation or design would test it."* **WHY GENERAL:** multi-basket inference + status label + missing test is
domain-free; the status vocabulary is epistemology, not domain content; no counts. **FAITHFULNESS:** labels
EXPLICITLY mark the report's own inference as inference — the FAITHFUL way to be novel (unlabeled novelty is the
fabrication risk); each proposition still cites its rows.

**SMALL TEST.** **[S]** two independent baskets that jointly license a conditional relationship, one basket
alone, a confounded counterexample; assert only the joint case creates a synthesis-derived proposition retaining
both premise citations + a falsifier, and the confounded case is labeled unresolved. **[F]** synthesis section
contains ≥1 labeled proposition per multi-member cluster in its pack (label lexicon + ≥2 distinct markers; today
0). Paired Insight probe (this cell was the sharpest cellcog-57.08-vs-Bodhi-54.60 difference — addendum System 1b).

---

### U8 — The central task concept (4IR) is introduced, not USED as an explanatory variable
Maps: **[S G6]** (Fable partially covers via U11 headings; Sol's concept-role-spine is a distinct mechanism).

**GAP.** **[S]** the report defines the Fourth Industrial Revolution in article line 7 then mostly uses it as
framing; coverage spine is default-off (`config_defaults.py:920`); the max obligation binds "AI as a key
driver…" to the CONCLUSION (`compose_summary.json:11278-11284`) rather than enforcing explanatory roles across the
report; the generic skeleton cannot distinguish a required central concept from ordinary background.

**SUB-ITEM LOST.** **[S]** Comp #1 4IR grounding 0.0290 + Insight #9 4IR integration 0.0480 + Inst #14 4IR-driver
theme 0.0375.

**WINNER MOVE.** **[S]** define + historically contrast the central concept, then use its supported properties to
explain pace, breadth, redesign, institutional pressure (`COMPETITOR_TEARDOWN.md:232-243`).

**FIX (outliner; PRE-gen).** **[S]** for every concept the prompt designates as a driver/lens/organizing theme,
create a **concept-role spine**: definition, contrast, mechanism role, context-variation role, implication role —
but instantiate only roles supported by evidence; an intro mention cannot fulfill downstream roles. **WHY
GENERAL:** roles come from the semantic relation between prompt concepts, not any named concept.

**SMALL TEST.** **[S]** a task with a designated driver + one with a merely-mentioned background term; assert only
the driver receives a role spine and an intro-only report fails the semantic audit; compose frozen evidence and
verify non-intro planned propositions use the concept as an explanatory variable; paired RACE probe.

---

### U9 — Exposure / adoption / productivity / realized outcomes are not governed by a shared measurement ontology; benefits & harms are scattered
Maps: **[S G7]** (no direct Fable equivalent — distinct).

**GAP.** **[S]** the writer does ask for scope disambiguation (`:3529-3530,3562-3568`) and article line 43
distinguishes some measures, but there is NO report-wide pre-generation ontology preventing an exposure score, an
experiment, a forecast, a firm association, and a labor-market outcome from being treated as one disruption
scale; benefits/harms are scattered rather than conditioned on stakeholder and horizon.

**SUB-ITEM LOST.** **[S]** Comp #4 disruptive character/scale 0.0435 + Comp #6 balanced impacts 0.0290 + Inst #15
significant disruption 0.0375.

**WINNER MOVE.** **[S]** treat exposure, observed task productivity, diffusion, and realized employment/wage
outcomes as DIFFERENT quantities; balance effects by affected party and time horizon
(`COMPETITOR_TEARDOWN.md:235-242`).

**FIX (evidence packing; PRE-gen).** **[S]** induce a measurement ontology from evidence fields + claim text:
construct, unit, observed/modelled/forecast status, margin, population, period, affected party; permit
aggregation/net-direction claims ONLY for compatible measurements; build an effect ledger preserving benefits,
harms, distribution, horizon, uncertainty **without forcing artificial balance where evidence is one-sided.**

**SMALL TEST.** **[S]** mix exposure percentages, experimental productivity effects, forecasts, observed
employment changes; assert the planner refuses a common aggregate, preserves labels/units, produces
stakeholder/horizon comparisons only where licensed; a one-sided fixture must DISCLOSE asymmetry, not invent a
counterclaim.

---

### U10 — Implications are recommendations appended to evidence, not consequences of diagnosed levers; balance & resolvable-gaps missing
Maps: **[S G8]** + **[F GAP-10]**.

**GAP.** **[S]** `faithoff_t72` article line 39 serially inventories institutions/programs; champ article line 35
offers generic investment/collaboration prescriptions; no plan object links an implication to a specific
mechanism, context, trade-off, evidence strength, and observable. **[F]** the skeleton closing role (`:955-956`)
asks for "CONCLUSIONS and open RESEARCH GAPS" but never (i) recommendations tied to diagnosed mechanisms with
change-conditions nor (ii) gap statements converted to testable designs/observables; 7phase lists four GENERIC
gap bullets (cleaned lines 207-213), none states the resolving observation; no balanced benefit/harm obligation
(Comp #6: mf_baseline has no focus clause owning "challenges AND opportunities").

**SUB-ITEM LOST.** **[S+F]** Insight #11 implications & future agendas **0.0480** + Comp #6 balanced impacts 0.0290.

**WINNER MOVE.** **[S+F]** win-map #11 "each rec states mechanism-changed/population/trade-off/evidence-strength/
testable-outcome" + Pattern 11 "FORWARD-LOOKING BUT FALSIFIABLE — state what evidence is missing + what
observation resolves it" (ref:300-307; NVIDIA:391-401; Lunon N5 falsifiers; Xiaoyi N14 per-section Critical-
Evidence-Gap blocks; fable5 ":98 Threshold that would change this").

**FIX (outliner closing role; PRE-gen).** **[S]** derive implication objects from already-planned mechanism +
synthesis propositions; each must point to the diagnosed lever, affected context/population, expected direction,
trade-off, evidence grade, and an observation that would test it; REJECT generic recommendations with no upstream
proposition. **[F]** strengthen the closing-role directive: *"For each conclusion, name the mechanism/evidence
family that supports it; for each open gap, state what data/comparison/observation would resolve it; where the
evidence shows both benefits and harms, state for whom and under what conditions each dominates."* **WHY
GENERAL:** mechanism-attribution, resolvability, distributional balance are properties of any evidence synthesis;
no domain nouns/counts. **FAITHFULNESS:** prose obligations over already-cited findings only.

**SMALL TEST.** **[F]** every gap bullet in the closing section contains a resolvability clause (references future
evidence with a concrete object drawn from the report's own vocabulary; today 0/4 in 7phase). **[S]** give the
planner evidence-backed vs generic recommendation candidates; assert only the former is admitted and every
implication has valid upstream proposition IDs + a predicted observable. Paired Insight probe.

---

### U11 — Source-constraint compliance is never performed in judged prose — and our Limitations section actively performs NON-compliance to the judge
Maps: **[S G9]** + **[F GAP-8]**.

**GAP.** **[F]** post-cleaning, Inst #17/#18's only carriers are in-prose signals; our reports carry NO
source-policy sentence (grep: none), sparse venue attribution (mf_baseline: ONE italic journal name; champ
"almost no author-year-journal"), and a closing Limitations that DISCLOSES corpus non-compliance in INTERNAL
vocabulary — 7phase cleaned line 220: "only 4% of sources are T1 primary studies and 1% are T2, while T4 20%, T6
21%, and a full 25% could not be tier-classified" — internal tier telemetry leaked to the judge (writer prompt
bans "tier" vocab `:3606-3608` but the deterministic Limitations renderer emitted it; `_deterministic_reader_
limitations:8843-8917` is cleaner but still leads with corpus-composition self-indictment); the retrieval-side
firewall `PG_RQ_SOURCE_ELIGIBILITY_ENFORCE` is EMPTY in the champion config — tier compliance ~73% at best
(memory rank12). **[S]** the driver writes source-selection telemetry to `methods.md`, explicitly "NOT part of the
judged report" (`compose_agentic_report_s3gear329.py:776-810`); base article line 55 self-discloses only 4% T1 /
1% T2 / 25% unknown while lines 7-51 cite working papers, org reports, websites, pasted pages; max report names an
NBER working paper, journalism, grey literature, IEEE conference paper on line 7. The scope contract correctly
excludes definitive-wrong-type + unresolved-type under an exclusive constraint (`scope_contract.py:152-177`) but
its admission function consumes source types + languages ONLY (`:223-262`) — extracted `quality_attributes` are
NOT checked there; in the base compose summary the prebuilt corpus was not scope-evaluated and compliance is null
(`compose_summary.json:41-42`).

**SUB-ITEM LOST.** **[S+F]** Inst #17 journal-only **0.0375** + Inst #18 English-only 0.0250 (= 0.0625) + Comp #5
literature depth 0.0435; **[S]** #12 literature-review form 0.0250. **[S]** #17 is DIRECTLY violated; #18 is an
unproven visibility/compliance risk (reports are English, no confirmed non-English article found) — a compliance/
visibility risk, not a claimed observed violation.

**WINNER MOVE.** **[S+F]** Pattern 7 "IN-PROSE SOURCE-QUALITY SIGNALING — author-year-journal + explicit
source-policy sentences + flagged exclusions"; Dalpha = existence proof (35/35 journal DOIs) + N9 evidence-
provenance typing; Bodhi N3 first-person evidence-boundary protocol. **[S]** "enforce source type at retrieval,
carry an auditable selection method, state source policy + named author/year/journal + exclusions in prose
because bibliography prestige is invisible to RACE."

**FIX (retrieval + writer; PRE-gen; honesty-preserving).** **[S]** compile every exclusive source/language/date/
quality constraint into an ADMISSION CONTRACT before outlining; a load-bearing row must have definitive eligible
type+language + evidence-based quality status (publication provenance, peer-review status, correction/retraction
state where available, venue identity, design transparency); unknown eligibility becomes a retrieval target or
disclosed gap, NEVER body evidence; generate a reader-facing selection statement from the ACTUAL admission ledger
and plan it into the intro/method section — no venue whitelist/domain literal required. **[F]** concretely: (a)
when extracted constraints carry an exclusive source-class/language term (`_EXCLUSIVE_RE` exists
`scope_contract.py:40-43`), make admission-time eligibility enforcement the DEFAULT at this seam (firewall exists,
unwired in champion config); (b) writer: require (i) the opening section to state the review's ACTUAL admission
policy AS ENFORCED, derived from constraint + enforcement telemetry (never beyond telemetry — if exceptions were
admitted, disclose their role, the Dalpha/Bodhi move), and (ii) each named study's first mention to carry venue/
year metadata the evidence row already supplies (`format_source_attribution_metadata` sidecar exists `:3902-3938`;
the directive to USE it in prose is the missing half); (c) Limitations: keep honesty but express composition in
READER vocabulary only (publication types, not tier codes) — pin the reader-register renderer and extend its
leak-screen to every Limitations path. **WHY GENERAL:** triggers from extracted constraints, metadata from
evidence rows; no venue lists/domain words. **FAITHFULNESS:** nothing claimed that telemetry doesn't support;
attribution uses only evidence-supplied fields (existing "Never invent a missing field" rule stands).

**SMALL TEST.** **[S]** mixed-metadata corpus (eligible, wrong-type, wrong-language, unknown, retracted,
unverified-quality); deterministically assert partition completeness, no inadmissible row in any section plan,
explicit exercise of the quality rule; compose a miniature review and assert the cleaned body truthfully names its
selection policy and contains no inadmissible load-bearing attribution; paired Inst probe. **[F]** three lints:
[i] zero internal-vocabulary tokens (tier codes/telemetry) in the rendered report (7phase today FAILS); [ii]
policy sentence present iff exclusive constraint extracted, every clause entailed by enforcement telemetry
(string check against disclosure JSON); [iii] venue-attribution rate on named-study first mentions when the row
supplies it (today ~0 → target ≳0.8); corpus-side eligibility-compliance fraction from the firewall's telemetry
(43%→73% already measured).

---

### U12 — Paragraph/heading structure is advisory text the active producer does not preserve; run-in headings, truncated preamble, repeated subheadings, duplicate sentences reach the judge
Maps: **[S G10]** + **[F GAP-9]**.

**GAP.** **[S]** `faithoff_t72` has 14 prose paragraphs, 608.5-word median, 838-word max (TEARDOWN Part 2
forensic); article lines 11/35/43 each pack multiple analytical moves in one wall; lines 27/47 begin mid-word;
line 51 begins with a pasted page header. Writer asks for 3–6 sentence paragraphs (`:3581-3585`) and the marker
path materializes writer breaks (`:3670-3707,6748-6750`), but verified-compose constructs units separately and
joins them; rich structure can put subheads inline; `PG_SECTION_STRUCTURE` wins over the block-preserving path
(`:3729-3740`) and the max report has `### Guiding Questions…` embedded on physical line 7 violating the own-line
rule (`:3581-3585`). **[F]** four observed defects: (i) RUN-IN HEADINGS raw 7phase lines 33/42 `### AI Skills …
**AI skills are consolidating…**` heading+body on ONE line (violates `:3556-3559`); no deterministic normalizer
exists (`find_malformed_tables` detects tables only, DISCLOSES); (ii) the driver hardcodes a preamble under the
title (`compose_agentic_report_s3gear329.py:680-694`) surviving TRUNCATED mid-sentence in the judged article
("…group the evidence by", cleaned line 2) describing organizing mechanics our own rule bans (`:3572-3573`); (iii)
"### Evidence Limitations" repeated as a subheading 4–6× (cleaned 55/103/125/214); (iv) duplicated sentences
cleaned lines 42 vs 59 (via GAP-4 table degradation).

**SUB-ITEM LOST.** **[S+F]** Read #19 language 0.0280, #20 structure 0.0280, #21 cohesion 0.0210, #22 synthesis
clarity 0.0210, #24 layout 0.0140, #25 audience 0.0140. **[F]** Read is our WEAKEST dim (7phase .4494–.4635;
faithoff .3981) and BELOW parity — unlike winners who accept a Read trade for density (addendum F2) — so Read is
real floor headroom.

**WINNER MOVE.** **[S+F]** win-map #24 "stable heading depth, repeated schemas, no orphan headings/broken tables/
boilerplate"; **[S]** "one inferential move per paragraph; transitions encode the actual relation; definition →
intuition/example → limitation; no raw retrieval fragments" (`COMPETITOR_TEARDOWN.md:242-251`).

**FIX (writer prompt + deterministic render assembly; PRE-gen / layout-only).** **[S]** make paragraph blocks
first-class PLAN objects: each block owns one reader question + one analytical movement (claim, evidence/
appraisal, relation/implication) with an explicit transition relation to neighbors; the active producer emits
verified sentences INTO those block containers; the renderer preserves container boundaries + heading nodes
exactly; add pre-composition input SANITATION preventing navigation text, cut fragments, page boilerplate from
becoming evidence spans. **[F]** (a) remove the driver's hardcoded preamble from the judged report (the Intro
section already frames scope); (b) add a deterministic LAYOUT normalizer at assembly (same class as
`_materialize_paragraph_breaks:3686-3692` and `markdown_table_normalizer` which already ship): split any heading
line that continues into prose, enforce blank lines around headings — markdown layout normalization of writer-
emitted text, ZERO word changes/content drops, NOT a post-gen content edit; (c) per-section limitation prose goes
into the section body (no repeated dedicated subheading); one report-level Limitations role owns the register.
**WHY GENERAL:** all format-level rules independent of task/domain. **FAITHFULNESS:** untouched (no sentence
added/removed/changed).

**SMALL TEST.** **[S]** section plan with multiple analytical moves + unique block IDs; assert one-to-one survival
of block boundaries through compose → provenance rewrite → strict verify → render; headings on their own lines;
no input-fragment sentinel; compare deterministic block/heading metrics before/after. **[F]** deterministic lint
(seconds, no LLM): zero heading lines containing sentence text (today ≥2); zero repeated identical subheading
titles beyond skeleton roles (today 4–6× "Evidence Limitations"); zero mid-sentence-truncatable preamble; zero
verbatim duplicate sentences ≥15 words (today ≥2). Then 3v3 paired Read probe (sub-parity Read has documented
+0.045/dim-point at-parity leverage).

---

### U13 — Route-all creates a miscellaneous evidence dump and lets low-contribution text into the body
Maps: **[S G12]** (Fable touches via U12(iv) duplicates; Sol's marginal-contribution routing is distinct).

**GAP.** **[S]** the base outline's last section is literally "Additional Corroborated Findings" with **433
evidence IDs** and the same phrase as its focus (`compose_summary.json:18-20`; `multi_section_outline.json` sec
12) — this CONTRADICTS the current composition rule "Do not create an additional, miscellaneous, residual, or
corroborated-findings section" (`multi_section_generator.py:3593-3595`), showing prompt advice cannot repair
upstream ROUTING; article line 31 contains raw blog phrasing; lines 47/51 contain broken retrieval artifacts.
More evidence became more prose without a marginal-contribution test.

**SUB-ITEM LOST.** **[S]** Inst #13 on-topic focus **0.0500** + Read #19 language 0.0280 + Read #22 synthesis-not-
serial 0.0210 + Read #24 layout 0.0140.

**WINNER MOVE.** **[S]** every added section adds a NEW analytical layer; off-topic evidence removed at retrieval
+ composition; repeated/corroborating sources synthesized in the owning claim, not dumped
(`COMPETITOR_TEARDOWN.md:231-232,289-298`).

**FIX (evidence routing; PRE-gen).** **[S]** before body routing, require each basket to declare a MARGINAL
CONTRIBUTION to a supported coverage obligation, relation, method appraisal, limitation, or implication; merge
corroboration into its owning proposition; evidence without a body contribution stays ARCHIVED for bibliography/
audit and can trigger a gap but does NOT force prose; sanitize candidate spans for fragment boundaries + page-
navigation signatures before admission. **WHY GENERAL:** an ownership rule, not evidence deletion or a topic-
specific filter. **FAITHFULNESS:** archives, does not delete; admitted body claims still cited.

**SMALL TEST.** **[S]** duplicate, corroborating, off-topic, boilerplate, novel baskets; assert every emitted
block has one valid analytical owner, corroborators join the existing proposition, the novel basket adds a
planned move, the rest stays out of body while archived, and the report contains NO residual-section role.

---

### U14 (FACT) — E.Cit is a supported-pair VOLUME game we lose 5–15× while precision is fine
Maps: **[S G13]** + **[F GAP-11]**.

**GAP.** **[F]** measured (`results/fact/*/fact_result.txt`): b0fact E.Cit 16.0 @ 94.1%; b1fact 31.0 @ 68.9%;
faithoff_t72 11.0 @ 100%. The FACT champion (gemini DR, the reference generator) posts **E.Cit 165.34 @ C.Acc
78.3** — "at near-equal precision, E.Cit is a 4× VOLUME game" (TEARDOWN Part 4). Cause: the draw cites only 41
distinct references inline (183 markers, raw 7phase) and sentences pack multiple facts per single `[N]`. **[S]**
FACT finds only 11 supported pairs despite 111 distinct prose markers + 147 bibliography entries; the benchmark
extracts four inline forms, returns nothing for bibliography-only sources, dedups by URL, counts supported
statement–URL pairs (`SCORING_SPEC.md:168-181`); the pipeline optimizes strict INTERNAL provenance but does not
preflight the external extractor's complete-proposition / canonical-URL / inline-location / dedup identity as one
plan object; two AEA destinations were unavailable to scraping and excluded as unknown (URL volatility).

**SUB-ITEM LOST.** **[S+F]** FACT E.Cit (surface #46 unique SUPPORTED pairs are linear; #48/#49 multiplicities) —
an entire leaderboard column, ORTHOGONAL to RACE (`SCORING_SPEC II`). **[S]** FACT #40–#52: immediate atomic
citation, extractable form, complete fact frame, reachable URL, exact support, avoidance of unsupported+duplicate
pairs, supported-pair volume, multi-source/multi-fact behavior.

**WINNER MOVE.** **[S+F]** many unique inline statement-URL pairs at maintained precision; per-section evidence-
scoped writing (WebWeaver 25%→85.9%); AI-Q per-research-unit citation contract. **[S]** "attach a reachable real
URL immediately after the smallest complete proposition, keep each source-specific proposition atomic, widen
unique supported pairs without sacrificing precision."

**FIX (retrieval + writer; PRE-gen).** **[S]** extend the CLAIM PLAN (not strict verification) with an external-
citation contract: atomic proposition frame, exact supporting span, canonical reachable URL, inline marker
mapping, expected dedup key; a multi-source sentence is allowed only when each source supports the SAME complete
atomic proposition; distinct source-specific facts become distinct planned units; preflight reachability +
extractor compatibility before generation, retaining the stricter internal faithfulness gate. **[F]** two general
moves: (a) U5's ledger-typed deepening raises distinct admitted works per facet (each new admitted work yielding
≥1 supported claim adds ≥1 pair, linearly); (b) add the converse of the one-proposition-per-sentence rule: *"when
several admitted sources independently support distinct facts, write each fact as its own cited sentence rather
than folding them into one summary sentence."* **WHY GENERAL:** no counts/domains; scales E.Cit with real corpus
abundance only. **FAITHFULNESS:** more atomic citation, never looser support.

**SMALL TEST.** **[S+F]** extract+dedup ONLY (no scrape/validate — cheap): run the FACT extract+dedup stages on a
fixed report before/after; metric = unique statement-URL pairs (proxy upper bound of E.Cit); today ≈ tens of
pairs from 41–111 distinct sources → target growth proportional to admitted-work growth from U5's test; a
follow-up full FACT run on the final candidate validates valid_rate ≥ baseline (no precision regression). Strict
verification remains unchanged.

---

## 2. WHY EXISTING LEVERS MEASURED FLAT (wrong wiring vs wrong idea) — merged [F B.1] + [S §"existing levers"]

| lever | verdict | evidence (file:line) | fix |
|---|---|---|---|
| `contradiction_mining` | **wrong wiring, idea right** [S+F] | yields `contradictions_detected: 0` on the real corpus (`mf_max draw_1`) because the judge files level/method/period divergence — the very thing #8 pays for — as non_comparable/compatible (`contradiction_mining.py:123-126`) and `find_contradictions:167` discards those classes + their boundary reasons; consumer is a hedge not a reconciliation | U3 |
| `relation_evidence_packs` | **wrong wiring, idea right** [S+F] | grouping key = token-bag of the statement (`:56-66`) → pseudo-propositions; delivered as raw JSON dump in the system prompt with one guidance sentence (`:4188-4198`); global map reaches only a lexically-recognized synthesis section (`:190-205`) | U4 |
| `PG_SYNTHESIS_TABLE_CONSTRUCT` / `PG_SUMMARY_TABLE_COMPOSE` | **wrong idea for the cell** [S+F] | `Finding|Value|Source` sentence-span inventory duplicates prose + deterministically degraded by the citation-stripping cleaner (malformed 2-col remnants + `Finding:` orphan lines 7phase cleaned :129-157/:59-61); post-assembly insertion also violates the pre-gen rule (`compose_…py:746-761`) | U4 (retire/replace) |
| `PG_SECTION_STRUCTURE` | **idea right, unpoliced output** [S+F] | produced run-in `### heading **prose**` (raw 7phase :33/:42), wins over the block-preserving path (`:3729-3740`); no layout normalizer → Read losses ate gains | U12(b) |
| `PG_COVERAGE_OBLIGATIONS` | **idea right, toothless audit + wrong binding** [S+F] | audit counts fulfilled iff bound section non-empty (`coverage_obligations.py:149-158`); bound "4IR driver" to the CONCLUSION (mf_max audit); no heading/echo requirement, no retrieval trigger | U5 + U8/U11 |
| `PG_COVERAGE_SPINE` / `PG_SCOPE_DEEPENING` | **inert in every measured run** [F] | both empty in mf_baseline/mf_max/7phase champion configs; deepening logs "requires_retrieval_pipeline" (`compose_…py:431`) — a lever that never runs measures exactly 0 | U5(d) wire |
| `contradiction_hedging`, `PG_NARRATIVE_ATTRIBUTION` | **idea right, advisory-only** [F] | hedging asks to "acknowledge" (not explain); attribution metadata rides as a sidecar but no rule compels venue-in-prose at first mention | U3, U11(b)(ii) |

---

## 3. COMPLETE SCORED-SURFACE DISPOSITION [S] — every RACE/FACT cell → controlling gap (unified U#)

| scored surface | observed disposition | controlling gap |
|---|---|---|
| Comp #1 4IR grounding .0290 | definition present; explanatory reuse incomplete | U8 |
| Comp #2 restructuring breadth .0725 | many dimensions; no semantic ledger/completeness proof | U5 |
| Comp #3 industry scope .0725 | many names; no regime diversity/common schema | U6 |
| Comp #4 disruption scale .0435 | unlike measures discussed but not governed report-wide | U9 |
| Comp #5 literature depth .0435 | large corpus; methods/source quality not reader-visible/compliant | U3, U11 |
| Comp #6 balanced impacts .0290 | both signs present; no stakeholder/horizon effect ledger | U9 |
| Insight #7 mechanisms **.0800** | strong isolated base section; not a reusable plan spine | U1, U2 |
| Insight #8 cross-industry synthesis **.0800** | late/compressed paragraph; no context-aware relation graph | U3, U4, U6 |
| Insight #9 4IR integration .0480 | framing label more than explanatory variable | U8, U2 |
| Insight #10 emergent themes **.0640** | deductions not epistemically labeled/falsified | U7 |
| Insight #11 implications .0480 | recommendations not linked to diagnosed levers/tests | U10 |
| Inst #12 literature-review form .0250 | thematic shell present; selection method absent from judged body | U11 |
| Inst #13 focus .0500 | residual dump + retrieval artifacts violate focus | U13 |
| Inst #14 driver theme .0375 | named centrally but not role-audited | U8 |
| Inst #15 significant disruption .0375 | scale categories insufficiently separated | U9 |
| Inst #16 various industries .0375 | names present; analytical variation weak | U5, U6 |
| Inst #17 journal-only .0375 | DIRECTLY failed by non-journal load-bearing sources | U11 |
| Inst #18 English-only .0250 | no observed language breach; compliance statement invisible | U11 |
| Read #19 language .0280 | fragments, boilerplate, walls | U12, U13 |
| Read #20 structure .0280 | macro skeleton good; internal heading/block preservation broken | U12 |
| Read #21 cohesion .0210 | transitions hidden within long multi-move paragraphs | U12 |
| Read #22 sourced synthesis .0210 | relation plan + ownership insufficient | U3, U12, U13 |
| Read #23 data/table clarity .0140 | absent in base; max table not comparative | U4 |
| Read #24 layout .0140 | no base tables; inline headings in max | U12, U4 |
| Read #25 audience .0140 | scholarly tone present; definitions/intuition/limits not block-planned | U12 |
| FACT #40–#52 | 11/11 supported but low effective volume + URL/extractor fragility | U14 |

---

## 4. GAPS NOT FIXABLE PRE-GENERATION (and why) — merged [S §Limits] + [F B.2]

1. **[S+F] Cleaner nondeterminism/truncation** (`SCORING_SPEC I.10`): the judged text is an LLM rewrite we don't
   control (our preamble truncated mid-sentence, tables mangled in-flight). We can only make artifacts robust-to-
   cleaning (U4/U12 do); we cannot fix the cleaner. Residual risk stays.
2. **[S+F] Single-call judge variance** (±0.027; `SCORING_SPEC Part V #7`): irreducible in-pipeline; every test
   uses deterministic structural assertions first + paired multi-draw probes second.
3. **[S+F] Reference contamination + the relative frame** (`SCORING_SPEC I.11`): a target stylistically close to
   the Gemini reference benefits; not an actionable lever beyond adopting the winning surfaces themselves.
4. **[S] Strict verification may remove a planned sentence** whose support is inadequate — the lawful response is
   stronger evidence ownership or regeneration from the plan, never weakening faithfulness or editing the finished
   report.
5. **[S+F] NVIDIA-style post-gen rubric rewrite** is the one competitor move structurally FORBIDDEN for us; its 10
   editor instructions are instead absorbed into U1/U2/U4/U7/U10's writer- and outline-stage rules — exactly the
   brief's demand.
6. **[S+F] Two-column FACT reality**: E.Cit depends on TODAY's page reachability at scoring time (Jina drift,
   `SCORING_SPEC II.3`) — not controllable pre-generation beyond choosing stable canonical URLs at retrieval.
7. **[S] Bibliography stripping is fixed RACE behavior** → compliance must be truthfully stated in PROSE from the
   admission ledger; render-only bibliography changes cannot earn #17/#18.

---

## 5. CONSOLIDATED PRIORITIZED FIX LIST (effective weight × our headroom)

Priority is the merge of both investigators' ranked lists (they agree on the top tier). Proxy = eff-weight ×
(1 − dim score) [S]. Each line: unified gap · cells · one-line fix · headline test.

1. **U1 — Insight #7+#8, 0.0800+0.0800 (proxy 0.04408 each).** Add a licensed-inference writer rule: every
   ≥3-sentence evidence paragraph closes with ONE inference sentence deriving what its already-cited findings
   jointly imply, zero new facts/numbers, carrying the paragraph's markers. Test: `paragraph_deduction_rate`
   0.16→>0.6 + zero-new-number canary, then 3v3 paired Insight probe. *(Both rank #1.)*
2. **U3 — Insight #8, 0.0800 (+ Comp #5).** Harvest ALL contradiction-judge classes into a divergence ledger /
   context-aware relation graph (convergence / qualified divergence / non-comparability) and ROUTE it to the
   active verified-compose producer, obligating the synthesis to EXPLAIN each divergence by its recorded boundary.
   Test: miner unit-run — ledger non-empty where today's yield is a measured 0 — + "synthesis names ≥1 boundary
   term per pair" + strict-verified cross-source proposition + paired probe.
3. **U2 — Insight #7, 0.0800 (+ #9 0.0480).** Add a question-type-conditional mechanism/causal-chain spine placed
   before the evidence bodies, whose channels every body section's focus must reference; derive supported causal
   chains from question semantics. Test: outline-JSON assertion (framework ≤ position 2; ≥50% body foci name a
   channel) + active-producer structural assertion + paired probe.
4. **U5 — Comp #2+#3, 0.0725+0.0725 (+ Inst #16 0.0375).** Question-derived coverage ledger (named dimensions +
   entity-class quantifiers + the four analytical roles); ground gap-detection in it (relax the anti-invention
   rule to "named OR implied by ledger"); type deepening queries (factual/causal/comparative/critical); turn
   deepening ON; SEMANTIC fulfillment (proposition must entail the dimension-role pair). Test: retrieval-only
   ledger-fulfillment telemetry (3 industries → 8+) + decoy-section-fails-until-emitted + paired Comp probe.
5. **U4 — Insight #8 0.0800 shared + Read #22/#23/#24 0.0560.** Retire the sentence-span `Finding|Value|Source`
   table (deterministically degrades under cleaning); regroup relation packs by shared-measure × different-context
   using the pack's existing attributes; writer emits comparison (prose or valid table) + a mandatory
   interpretation paragraph; table PLAN with cell-level source ownership. Test: simulated-clean lint (8 malformed
   → 0; ≥2 dupes → 0) + multi-context comparative-sentence count + paired Insight+Read probe.
6. **U7 — Insight #10, 0.0640.** Synthesis-role directive / inference planner: derive NAMED cross-cutting
   propositions grounded in ≥2 cited findings, each labeled with a fixed three-level evidential-status vocabulary
   + (when not established) the test that would resolve it. Test: labeled-proposition count 0→≥1 per multi-member
   cluster + joint/single/confounded fixtures + paired Insight probe.
7. **U8 — Insight #9 0.0480 + Comp #1 0.0290 + Inst #14 0.0375.** Designated-concept role spine (definition /
   contrast / mechanism / variation / implication), instantiate only evidence-supported roles; an intro mention
   cannot fulfill downstream roles. Test: intro-only mention fails the semantic audit; non-intro explanatory
   propositions pass.
8. **U10 — Insight #11 0.0480 + Comp #6 0.0290.** Closing-role / implication-derivation directive: each conclusion
   names its supporting mechanism/evidence family; each gap states its resolving observation; benefit/harm balance
   states for whom and when; reject generic recommendations with no upstream proposition. Test: resolvability
   clause per gap bullet 0/4→4/4 + upstream-proposition-ID check + paired probe.
9. **U11 — Inst #17+#18 0.0625 + Comp #5 0.0435 (+ #12 0.0250).** Full source-eligibility admission contract
   (type + language + evidence-based quality) default-on when an exclusive constraint is extracted; telemetry-
   derived in-prose admission-policy sentence; venue-at-first-mention from existing evidence metadata; reader-
   vocabulary-only Limitations (no tier codes). Test: three lints (zero internal-vocab tokens — today FAILS;
   policy ⊆ telemetry; venue-attribution rate ~0→≳0.8) + paired Inst probe + corpus eligibility-compliance
   counter (43%→73%).
10. **U9 — Comp #4 0.0435 + #6 0.0290 + Inst #15 0.0375.** Measurement/effect ontology: separate construct /
    margin / observation-status / stakeholder / horizon before any comparison or net claim; preserve one-sided
    evidence as one-sided. Test: incompatible metrics cannot aggregate; one-sided fixture discloses asymmetry.
11. **U13 — Inst #13 0.0500 (+ Read).** Marginal-contribution routing + input sanitation: body-route only baskets
    that add a supported analytical move; archive the rest; exclude fragments/boilerplate pre-compose; no residual
    section. Test: ownership completeness, no residual-section role, no fragment sentinel.
12. **U12 — Read #19/#20/#21/#22/#24/#25 0.0840 combined (we are BELOW parity).** First-class paragraph/heading
    blocks preserved through the active producer + verification + render; deterministic layout normalizer (split
    run-in headings, blank-line hygiene); drop the hardcoded driver preamble; one report-level Limitations role.
    Test: four-assert render lint (run-in headings ≥2→0; repeated subheads 4-6→0; preamble gone; verbatim dupes
    ≥2→0) + one-to-one block survival + paired Read probe.
13. **U6 — Comp #3 0.0725 shared + Insight #8.** Analytical context-diversity selection + common-schema comparison
    plan (materially different regimes, not name count). Test: synonyms don't satisfy diversity; multi-regime
    proposition; paired Comp/Insight gains clear noise.
14. **U14 — FACT E.Cit (separate track).** External-citation claim contract (atomic proposition, exact span,
    reachable canonical URL, inline mapping, dedup identity) + one-fact-one-cited-sentence rule + U5's ledger-typed
    deepening for more admitted works. Test: FACT extract+dedup-only pair count before/after (11 today vs champion
    165); full FACT run on the final candidate confirms valid_rate holds; strict verification unchanged.

**Measurement discipline for ALL of the above [S+F]** (`SCORING_SPEC Part V #7` + measured baseline spread
0.4922–0.5088): each fix ships its DETERMINISTIC assertion FIRST (free, noise-immune); score attribution uses
paired same-judge multi-draw probes (≥3v3, same corpus, otherwise-identical config), judged on the paired MEAN
per-dimension delta — never a single-draw comparison. **Build-all-then-measure** applies: deterministic tests
gate each lever individually; the RACE probe measures the assembled set.

---

## 6. PHASE-4 ARCHITECTURAL THESIS [S+F]

Both investigators converge: the Phase-4 center is **ONE pre-generation analytical contract** shared by outline,
retrieval admission, relation planning, active composition, and semantic acceptance — turning the question into
**testable analytical obligations** (mechanism chains, coverage-dimension ledger, context-aware relation graph
with three edge types, epistemically-labeled inferences, source-admission ledger, first-class paragraph blocks),
each **consumed by the producer that actually emits verified sentences** (`_compose_section_per_basket`, not only
`_call_section`), and each **audited SEMANTICALLY** (the proposition must entail the obligation, not merely occupy
a bound section). Adding more advisory prompt prose or independent flags will repeat the measured-flat failure.
Faithfulness engine untouched throughout; all fixes pre-generation; no post-gen content edit; no task/domain
literals, magic counts, or adjective flag names.
