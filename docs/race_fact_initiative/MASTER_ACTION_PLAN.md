# MASTER_ACTION_PLAN — Phase 4 — LOSSLESS consolidation of Sol + Fable

Provenance: both Phase-4 verdicts read line-by-line by Opus. Both ingestion receipts VERIFIED against ground
truth (all 10 prior artifacts, exact line counts 245/462/472/424/1147/272/335/820/267/220, FIRST/MID/LAST
verbatim, spot-checked with `sed`). Attribution: **[S]** Sol, **[F]** Fable, **[S+F]** both independently.
Nothing compressed; where the two overlap, every distinct clause/test/risk/decision from each side is kept.
Design-only — no pipeline code is written until the operator approves this plan.

Inputs: `PIPELINE_GAP_AUDIT.md` (14 unified gaps U1–U14), `phase4_sol_verdict.md` (586), `phase4_fable_verdict.md`
(596). Champion throughout = **mf_baseline** (all levers OFF except `PG_RENDER_BLOCKS=1`, strict-verify bypassed)
at Overall mean **0.5009** (draws 0.5088/0.5017/0.4922); noise bar **±0.027**; the two 0.0800 Insight cells (#7
mechanisms, #8 cross-industry synthesis) are the largest on the scorecard.

---

## 0. WHAT BOTH INVESTIGATORS AGREE ON (the settled architecture)

**[S+F]** These are not in dispute — they are the spine of the plan:

1. **One object, not fourteen flags.** Every fix is a component of a single per-run **`AnalyticalContract` (AC)**,
   built from the question + admitted evidence, projected into outline/block/claim plans. **[S]** "not fourteen
   switches and not fourteen prompt fragments." The independent-flag path is what measured flat
   (`PIPELINE_GAP_AUDIT.md:24-28,668-679,810-820`).
2. **One consumption point.** The AC must be consumed by the **active producer
   `_compose_section_per_basket`** (verified-compose primary branch) — **not** only `_call_section` (the `else`
   fallback). A component reaching only `_call_section`, a sidecar prompt, telemetry, or an unused outline field
   is unwired and fails the gate. **[S]** locates it precisely: `verified_compose.py:_compose_section_per_basket`
   line 2841, selected by `multi_section_generator.py:_run_section` at `:6477-6713`; `_call_section` is `:6714-6728`.
3. **Semantic audit, never nonemptiness.** Fulfillment means the emitted proposition ENTAILS the obligation
   (dimension-role pair, channel term, boundary term, label, policy clause) — never "the bound section is
   non-empty" (the toothless `coverage_obligations.py:139-158`). **[S+F] "Semantic" = proposition-level
   deterministic tests/fixtures, NOT an NLI/entailment model** (R2 bans new entailment machinery).
4. **Champion = mf_baseline (0.5009), the ONLY comparator.** Measuring against mf_max / 7phase / faithoff_t72 /
   any weaker arm is void — the champion is the highest measured config. Ladder discipline: each shipped wave
   becomes the next wave's comparator.
5. **Two-tier measurement.** Deterministic structural assertion FIRST (free, noise-immune), then a paired
   same-judge **≥3v3** RACE probe decided on the paired MEAN per-dimension delta clearing ±0.027. Never a
   single-draw decision. Build-all-then-measure: deterministic tests gate each component; the probe measures the
   assembled wave.
6. **Faithfulness firewall.** `provenance_generator.py` + `clinical_generator/strict_verify.py` are untouchable;
   every sentence still carries `[ev_XXX]` markers; the ONE new sentence class (U1's paragraph-closing inference)
   is admitted only under a deterministic zero-new-factual-token canary; **NO post-generation content edit ever**,
   the sole labeled exception being layout-only render normalization proven by token-multiset/token-stream
   identity.
7. **Critical path agreement:** both put **U3 → U4/U6 → U7** at the center (Insight #8 0.0800 + Comp #3 0.0725 +
   Insight #10 0.0640), with U3 converting a measured-zero lever into the substrate for three later components.
8. **Wave-2-as-relation-layer agreement:** both group **U3 + U4 + U6** as one coherent "relation layer" wave
   (same data structure viewed three ways: pairwise relations → comparison groups → regime schema).

---

## 1. THE ONE REAL DISAGREEMENT — FIRST-SHIP WAVE & WAVE GROUPINGS (operator decision)

Both plans reach the same end state (all 14 gaps, one AC, identical charter) via **different build sequences**.
This is the decision the operator must make; I do not collapse it.

### 1.1 The two proposed wave decompositions (verbatim groupings)

| wave | **[S] Sol — governance-foundation-first** | **[F] Fable — proven-winner-first** |
|---|---|---|
| **W1 (first ship)** | **U5 + U11 + U13 + U12** — contract carrier + semantic coverage + source admission + marginal ownership + structure carrier | **U1 + U12-lite + U14b** — AC carrier + licensed paragraph-closing inference + layout normalizer + one-fact-one-sentence |
| **W2** | U2 + U3 + U1 (mechanism/relation/deduction vertical slice) | U3 + U4 + U6 (relation layer) |
| **W3** | U6 + U9 + U8 + U4 (context/measurement/concept/comparison) | U5 + U11 + U14a (coverage, admission & citation volume) |
| **W4** | U7 + U10 (epistemic synthesis + implications) | U2 + U8 + U10 (architecture spine) |
| **W5** | U14 (FACT atomic citation) | U7-full + U9 + U13 + U12-full (semantic governance) |

Note both build the **AC carrier in Wave 1** and both put **U12 in Wave 1** (Sol: full U12; Fable: U12-lite). Both
absorb the flat levers (contradiction_mining, relation_packs, coverage_obligations) into AC builders and retire
the sentence-span tables — those are not in dispute.

### 1.2 Sol's argument for governance-first (U1 deferred to W2)

**[S]** "The first production wave should **not** be U1 or U3 alone."
- **U1 alone is not the smallest safe win.** "Without first-class blocks and claim ownership, its 'paragraph
  closing' behavior is not reliably represented in `_compose_section_per_basket`, and a prompt-only implementation
  repeats the failure mode."
- **U3 alone is not a shippable report behavior.** "A nonempty relation ledger is a deterministic success, but it
  earns no score until admitted evidence, semantic ownership, and the active producer turn it into verified
  explanatory prose."
- **Wave 1 is the smallest high-confidence first shipment** because it replaces the four failed architectural
  assumptions — section-presence-as-coverage, ungoverned admission, route-all prose, advisory structure — with one
  auditable carrier, AND has substantial direct headroom: 2×0.0725 Comp (U5), 0.0625 Inst + literature-depth (U11),
  0.0500 focus (U13), the below-parity Read family (U12). "Wave 2 follows immediately and is the first direct
  Insight ceiling play. No discretionary polish belongs between Waves 1 and 2."

### 1.3 Fable's argument for proven-winner-first (U1 ships first)

**[F]** directly rebuts Sol's objection:
- **U1 is both investigators' independent #1** (proxy 0.04408 per 0.0800 cell, both cells at once); needs no
  upstream object; its deterministic test is zero-LLM; it targets "the single biggest winner-vs-midscorer
  difference on the board AND locally (fable5 0.5131 Insight vs champ 0.3411)."
- **"No foundational contract wave needs to precede U1 — provided Wave 1's definition-of-done includes creating the
  AC carrier and its consumption point in `_compose_section_per_basket` (R4.1–R4.2)."** The contract-first
  requirement is satisfied by making the carrier part of Wave 1 with U1 as its first payload. **"A carrier-only
  'Wave 0' would ship nothing measurable and burn a probe cycle."**
- **U1 and U3 are the right first PLAYS but not one wave** — different seams (writer contract vs relation layer);
  coupling them makes the paired probe unattributable. U3 leads Wave 2 immediately.
- **U12-lite rides along** because it is free (deterministic, layout-only), repairs our only below-parity
  dimension, its lints become the permanent render gate, and it **hedges U1's Read-density risk in the same probe.**
- Critical-path framing: "U1 is off-path (no dependents block on it) — which is exactly why it ships first:
  maximum expected value, zero blocking risk."

### 1.4 Opus's reading + recommendation (for operator to accept or override)

The disagreement narrows to one question: **does U1's paragraph-closing inference need the semantic-
ownership/coverage/admission machinery (U5/U11/U13) to be reliably represented at the producer, or is the AC
carrier + wiring assertion + layout-lite enough?**

- Fable **directly answers Sol's exact objection**: U1 is not "prompt-only" if it ships as the AC carrier's first
  payload with a deterministic wiring assertion that its directive is observable in `_compose_section_per_basket`
  inputs (R4.2). Sol's "prompt-only repeats the failure" premise is thus already mitigated in Fable's design.
- U1's proof is **self-contained**: `paragraph_deduction_rate` 0.16→>0.6 + the zero-new-token canary + a 3v3
  Insight probe need none of U5/U11/U13 to be measured. The empirical anchor (fable5 0.5131 Insight with
  per-paragraph deduction) pays off without the governance stack. **[S]'s counter** is that fable5 was a manual
  target, not the wired pipeline — a fair caveat, but one the Wave-1 probe directly tests.
- **Risk asymmetry favors Fable's order as the first ship:** it is cheaper, faster to a score signal, attacks the
  two biggest cells first, and is independently reversible. If it measures flat, that flat result is *itself the
  experiment that would validate Sol* (it would prove U1 needs the governance stack) — at a fraction of the build
  cost of standing up semantic-coverage + admission-enforcement first. Sol's Wave 1 has the most surface area and
  the riskiest components (semantic audit correctness, corpus-shrink from admission enforcement) before any score
  signal.

**Opus recommendation: adopt Fable's first-ship (Wave 1 = U1 + U12-lite + U14b, with the AC carrier as its
definition-of-done), and honor Sol's carrier-first insistence — which Fable's design already does.** Keep Sol's
governance components (U5/U11/U13) as the very next priority; if Wave 1's probe is flat despite green
deterministic gates, that is the signal to front-load Sol's governance wave exactly as he specifies. **This is a
judgment call, not a settled fact — it is the operator's to make.** (Both wave decompositions are preserved in
full in §4 so either path is buildable.)

---

## 2. MERGED EXECUTION_CHARTER (Sol A1–A5 ≡ Fable R1–R5; every distinct clause preserved)

The two charters are congruent; merged below rule-by-rule, `[S]`/`[F]`/`[S+F]` attributed.

### C1 — GENERALIZATION GATE (no task-72 overfit ships) — [S A1] + [F R1]

**Rule.** A fix is admissible only if ALL hold:
- **[S+F] Zero task/domain literals** in code/prompts/config it introduces. Banned: task-72 domain nouns
  (labor/industry/4IR/journal-name strings), benchmark-task identifiers, venue whitelists, sector lists, any
  domain-vocabulary lookup table. **[S+F] The ONLY fixed vocabularies permitted are role/type/status vocabularies**
  — analytical roles {mechanism, cross-context comparison, consensus/disagreement, implications}; query types
  {factual, causal, comparative, critical}; comparability boundaries {population, method, level, period, measure}
  (the fields `relation_evidence_packs._attributes` already aliases); the three-level epistemic-status vocabulary;
  **[S] contract states** {supported, retrieval_needed, unsupported_disclosed, not_applicable}. CONTENT always
  comes from the question + admitted evidence at runtime (`PIPELINE_GAP_AUDIT.md:302-316,376-389,413-416`).
- **[S+F] Zero magic counts** (no hardcoded section/industry/word/source/paragraph/citation targets). **[S]** the
  only permitted numerics are TEST-PROTOCOL values (≥2 held-out corpora, ≥3v3 draws, ±0.027 band) declared as
  named acceptance constants in fixtures — they must never enter runtime selection or prose generation.
- **[S+F] Zero adjective flag names** — no new `PG_*` with "max/full/rich/smart/deep/enhanced/better"; components
  are named by the seam/object they build. Behavior is a required projection of the one contract when its semantic
  preconditions are present.
- **[S+F] Held-out proof:** the fix's deterministic small test passes on task 72 AND ≥2 unrelated held-out
  benchmark tasks with materially different weight profiles, **frozen before implementation.** Named candidates:
  - **[S+F] task 91** (Saint Seiya inventory; .37 Comp / **.11 Insight** / .32 Inst / .20 Read) — anti-analytical
    extreme; conditional analytical triggers (U2 mechanism role, U5 analytical rows) must NOT fire / degrade
    gracefully;
  - **[S+F] task 100** (AI & interpersonal relationships; .29/.40/.16/.15) — high-Insight analytical extreme;
  - **[S+F] task 73** (novice EFL teachers; Read **.25**, highest in corpus) — audience/readability stressor;
  - **[F] task 51** (Japan elderly consumption; data-heavy, heading-sparse) — data-presentation stressor;
  - **[S+F] task 4** (zh, gold + mind-map deliverable; .20/.38/.26/.16) — language + format-instruction stressor.
  - **[F] Mandatory pair: 91 + 100** (opposite Insight extremes); recommended add 73 or 51. Operator picks final
    set (blocks build — OQ-1).
- **[S] Role-triggered fixes pass BOTH a positive and a negative activation test** (mechanism spine fires on a
  causal question, stays absent on a pure inventory unless evidence independently licenses it).
- **[S] Every contract field has evidence ownership or an explicit non-claim state**; empty strings / section
  presence / prompt-word matches cannot count as semantic fulfillment.

**Audit procedure [S+F].** (a) grep the runtime diff/prompts/config/schema-defaults for task IDs, benchmark names,
held-out-question literals, task-72 domain terms, fixed targets, new adjective flags, and digits in prompt/config
additions; test fixtures reviewed separately. (b) trace every fixed enum → confirm it is role/type/status, not
answer content. (c) run the exact small test on the prespecified held-out corpora — a fix that passes 72 but fails
either held-out is rejected as overfit; the **task-91 no-fire conditionality check is mandatory** for any
analytically-conditioned component. (d) **[S]** run the negative-control question and verify inapplicable roles stay
absent, not generic boilerplate. (e) **[S]** inspect a serialized contract — every content-bearing field must point
to question spans / constraint IDs / evidence IDs/spans / upstream contract IDs. (f) **[S]** compare emitted prose to
contract semantically: a nonempty section is never proof of fulfillment; the proposition must entail the
obligation-and-role pair. **[F]** confirm the component reads content from the constraint extractor
(`compose_agentic_report_s3gear329.py:398-410`) or admitted evidence rows, never its own literals.

**Stop [S+F].** Any literal / magic-count / adjective-name finding, or any held-out deterministic-test failure,
blocks the wave. No "temporary" literals. **[S] There is no RACE probe for a fix that fails this gate.**

> ⚠️ **VOID — see §12 ROLLBACK (2026-07-24).** The "Licensed-inference admission (the U1 canary)" clause below —
> a RUNTIME pre-producer admission gate with "premise claim IDs + permitted reasoning operator" — was a Sol
> escalation that CONTRADICTS Fable's own rule in this same section ("No new entailment/NLI machinery anywhere").
> It is the seed of a faithfulness-ghost / post-generation apparatus and is DISCARDED. U1 reverts to the clean
> Phase-3 form: a PRE-GENERATION prompt change + a deterministic zero-new-number TEST (not a runtime gate),
> relying on the EXISTING faithfulness engine. See `PIPELINE_GAP_AUDIT.md` U1 and §12 below.

### C2 — FAITHFULNESS FIREWALL — [S A2] + [F R2]

- **[S+F] Untouchable set:** `provenance_generator.py` (rewrite + citation resolution `:3714-3943`,`:4637-5252`)
  and `clinical_generator/strict_verify.py` (identifier/span/numeric/overlap/entailment `:387-574`). Claim-
  admission controls, not score planners; the fix belongs upstream. **No wave may weaken, bypass, special-case,
  lower a threshold in, or reinterpret either.** **[F] No new entailment/NLI machinery anywhere** (standing rule;
  champion runs strict-verify OFF and fixes must be valid under BOTH strict-verify configurations).
- **[S+F] Every new factual/analytical sentence still carries valid evidence markers** exactly as today
  (`multi_section_generator.py:3517-3519`).
- **[S+F] Licensed-inference admission (the U1 canary).** The one new sentence class — the paragraph-closing
  inference — is admitted only if a deterministic canary proves: **[S]** (1) its marker set is the union/subset of
  the premise sentences' markers; (2) after normalization every factual token (numerals, dates, units, named
  entities, identifiers, content-bearing terms) already occurs in cited premise sentences/spans — only a fixed
  connective/epistemic vocabulary may be new; (3) no new URL, citation identity, population, measure, direction,
  magnitude, entity, or boundary condition appears; (4) it is represented in the contract as synthesis-derived with
  premise claim IDs + permitted reasoning operator. **If the canary fails, the inference is never sent to the
  producer; it is not rewritten after generation.** **[F]** the same canary gates U7's labeled propositions (≥2
  cited premises; the label explicitly marks the report's own inference as inference — the faithful way to be
  novel) and U10's implication objects.
- **[S+F] NO post-generation content edit, EVER.** The NVIDIA-style rubric rewrite is the one competitor move
  structurally forbidden; its surfaces are absorbed pre-generation into U1/U2/U4/U7/U10. **Sole labeled exception —
  layout-only render normalization:** deterministic markdown layout ops on writer-emitted text with ZERO word
  changes / ZERO content drops (split run-in heading lines at the heading/body boundary; blank-line hygiene around
  headings), the same category as the shipping `_materialize_paragraph_breaks` (`:3686-3692`) and
  `markdown_table_normalizer`. **[S]** the normalizer must prove the ordered non-whitespace token stream is
  byte-for-byte identical before/after; may not add/remove/paraphrase/reorder/merge/split content. **[F]** ships
  with a diff-auditor asserting token-multiset equality (layout chars excluded). **[S+F]** the post-assembly
  summary-table path is forbidden (injects content after composition).

**Audit [F].** (a) `git diff --stat` shows zero lines changed in untouchable files; (b) canary runs as a
deterministic lint on every composed artifact; (c) normalizer token-equality check runs on every assembly; (d)
grep new prompts for instructions licensing out-of-evidence content beyond the one inference class.
**Stop [S+F].** Any untouchable-file diff, canary failure, or normalizer token change → no ship. **[S+F]** if
strict verification removes a planned sentence, the lawful response is stronger evidence ownership or regeneration
from the plan — never restore/edit the sentence or relax the verifier.

### C3 — MEASUREMENT GATE — [S A3] + [F R3]

- **[S+F] Tier 1 deterministic proof first.** Every component ships its audit-named SMALL TEST as a zero/low-LLM
  assertion. **[S]** this proof must exercise the REAL seam named in the wave, including
  `_compose_section_per_basket` where prose is involved — a green test over an unused prompt or `_call_section`
  alone is insufficient. Deterministic assertions are per-U-item; one failed U-item blocks the whole wave (it may
  be removed/redesigned, never carried into the probe as an unproven passenger).
- **[S+F] Tier 2 assembled paired RACE probe.** Build the ASSEMBLED wave (not isolated flag combos); compare to the
  immutable champion; **[S]** same frozen corpus snapshot / question / model / judge / reference / cleaner policy /
  otherwise-identical config, paired in a prespecified interleaved order so provider drift is shared; ≥3 candidate
  + ≥3 champion draws; **[S] freeze and hash the cleaned candidate/champion articles used for scoring so cleaner
  randomness is not misattributed to the judge, and separately run one end-to-end cleaner robustness check.**
  Compute each pair's candidate−champion delta for Overall + all four dims; decide on the paired MEAN.
- **[S+F] Decision band.** A targeted dimension must improve > +0.027. **[S]** any dimension ≤ −0.027 is a material
  regression = immediate no-go; a negative mean inside the band is inconclusive, not a pass — run only the
  prespecified confirmatory pairs and do not promote unless the mean is nonnegative. **[S] Also compare the
  cumulative candidate with the last approved wave** (prevents a later wave preserving a win over the old champion
  while erasing a previously banked dimension gain).
- **[F] Flat-wave rule:** a wave flat on all paired means (none negative beyond −0.027) MAY ship only if its
  deterministic gates all pass AND it is a declared dependency of a later wave (foundation shipping), with the flat
  result RECORDED — never spun as a win.
- **[S+F] Build-all-then-measure:** deterministic tests attribute each lever; the probe evaluates the integrated
  wave; within-wave components are not RACE-probed one at a time.
- **[F] Audit:** probe manifests record judge model, corpus hash, config hash, draw IDs; reviewer recomputes paired
  means from `results/race/*/raw_results.jsonl`; any probe missing its paired champion arm is invalid/void.
- **[S+F] STOP RULE.** No ship when: any deterministic assertion fails; a targeted dimension fails +0.027 after the
  prespecified probe; any dimension regresses ≤ −0.027; the FACT precision/non-inferiority gate fails for a
  citation-affecting wave; or the generalization/firewall audit fails. **[S] There is no "ship because Overall
  rose" exception for a dimension regression; no build-all-and-guess.** **[F]** a wave regressing a dimension is
  decomposed via the AC's component switches, the offender identified by its deterministic telemetry, then repaired
  or retired.

### C4 — SHARED-CONTRACT RULE — [S A4] + [F R4]

- **[S+F] One object.** Every wave extends/consumes one versioned `AnalyticalContract`. **[S] Proposed top-level
  fields** (invariant = required content):
  `question` (spans, semantic operators, deliverable, named concepts/classes, constraints) · `admission` (each
  row's eligibility decision + evidence + reader-safe disclosure) · `obligations` (question-derived dimension/role
  obligations w/ supported|retrieval_needed|unsupported_disclosed|not_applicable) · `mechanisms` (chain links,
  moderators, net-direction condition, missing-link boundaries) · `relations` (convergence | qualified divergence |
  non-comparability edges; direct conflict = a qualified-divergence subtype with both poles) · `contexts`
  (evidence-derived regime attributes + shared comparison schemas) · `measurements`
  (construct/unit/basis/margin/population/period/affected-party + observation|model|forecast status) · `inferences`
  (premise claim IDs, reasoning operator, boundary conditions, epistemic status, falsifier/resolving observation) ·
  `implications` (upstream mechanism/relation IDs, affected context, direction, trade-off, evidence grade, resolving
  observable) · `sections` (role, owned obligations/relations, evidence IDs, ordered block IDs) · `blocks` (reader
  question, analytical move, transition relation, claim IDs, optional table ID) · `claims` (atomic proposition
  frame, exact span ownership, marker set, factual-token inventory, canonical URL/dedup identity where applicable) ·
  `audit` (semantic-fulfillment, generalization, canary, render-preservation results).
- **[S+F] One consumption point** = `_compose_section_per_basket`. **[S]** the producer must return block/claim IDs
  with its draft so semantic acceptance maps surviving verified sentences back to obligations; it does not bypass
  provenance/strict verification. **[F] Definition-of-done for every wave includes a wiring assertion** that the
  component's payload is observable in the active producer's inputs.
- **[S+F] Semantic audit** (proposition-level deterministic, NOT an NLI model).
- **[S+F] No independent-flag path.** New behavior enters as an AC component with a switch used ONLY for staged
  measurement/rollback, in the AC's namespace — not a new `PG_*` adjective flag. **[S] Existing ideas absorbed:**
  contradiction mining → relation-edge construction; relation packs → relation/context projections; coverage
  obligations → semantic obligations; scope deepening → required transition for `retrieval_needed`; section
  structure → block preservation; narrative attribution → claim/source projection. **[S+F]** the sentence-span
  synthesis-table constructors are RETIRED from the judged body (diagnostics may stay in a non-RACE sidecar).
- **[F] Advisory prose is not a fix** — a prompt-only wave must justify why it won't repeat the flat failure; U1
  qualifies because it changes the writer's licensed sentence CLASS and ships a deterministic behavioral gate.
- **[F] Audit:** (a) dump the active producer's assembled inputs on a fixture run, assert the payload is present;
  (b) grep for new top-level env flags outside the AC namespace; (c) each obligation's fulfillment test is
  proposition-level. **Stop:** a component not consumed by `_compose_section_per_basket`, or audited only by
  section-nonemptiness, does not ship.

### C5 — NO-REGRESSION / CHAMPION-PROTECTION GATE — [S A5] + [F R5]

- **[S+F] The comparator is mf_baseline (0.5009)** — the highest measured config; any other comparator is void.
  **[F]** pin the champion `resolved_lever_states` snapshot
  (`outputs/race_max_focus/mf_baseline-20260723T152731Z/draw_3/compose_summary.json`) in VCS as a named frozen
  config.
- **[S+F] Champion protection:** archive hashes of corpus snapshot, raw+cleaned reports, reference, judge/model
  settings, resolved config, and score outputs for all champion draws; keep the champion path reproducible (never
  overwrite/redefine); **[F] AC components default OFF until their wave ships, so the shipped pipeline with an empty
  AC must reproduce the champion byte-for-byte at the config level** (an empty-AC run is diffed against the pinned
  champion before any probe is accepted).
- **[S+F] Measure every cumulative wave directly against the champion even after a prior wave won; also compare
  against the prior approved wave** to prevent losing banked gains. **[F] Ladder discipline:** after each shipped
  wave the new assembled config becomes the next champion, with its own ≥3-draw reference set.
- **[S+F] Ship criterion:** paired mean Overall ≥ champion within noise (no Overall regression beyond −0.027); no
  dimension regresses beyond −0.027; any claimed win clears +0.027 on the targeted dimension(s).
- **[S+F] Corpus/judge pinning:** frozen corpus, recorded judge model; cross-judge comparisons forbidden
  (`SCORING_SPEC.md:219-234`). **[S]** production admission still requires the firewall even though the historical
  champion telemetry had strict-verify OFF — the champion is the RACE oracle, not authority to weaken faithfulness.
- **Stop [F]:** any probe without the champion arm, or any shipped wave that cannot reproduce the champion under
  empty-AC, is reverted.

---

## 3. RUNTIME CONTRACT FLOW [S B1] (the end-state pipeline both plans converge to)

```text
question + constraints
   -> source admission --------> disclosed ineligible/unknown archive
   -> coverage obligations <---- typed retrieval/deepening until supported or disclosed
   -> mechanism + relation + context + measurement planners
   -> section -> paragraph-block -> claim/table/implication plans
   -> _compose_section_per_basket (ACTIVE producer)
   -> UNCHANGED provenance rewrite + strict verification
   -> semantic contract audit
   -> layout-only render normalization
```
**[S]** Source eligibility + semantic coverage precede relation/prose planning; the same IDs flow through the
active producer and unchanged verifier. (Note: the flow is the agreed END STATE; the two plans differ only in the
ORDER waves build toward it — §4.)

---

## 4. BOTH BUILD-WAVE DECOMPOSITIONS (preserved in full — either is buildable)

### 4.A — Sol's waves (governance-foundation-first)

- **[S] W1 — Contract foundation + semantic coverage/admission + ownership + structure carrier (U5, U11, U13, U12).**
  Shared object: AC foundation with `question, admission, obligations, sections, blocks, claims, audit`. New
  `src/polaris_graph/generator/analytical_contract.py` (`build_question_contract, apply_admission_decisions,
  build_coverage_obligations, assign_marginal_owners, build_section_blocks, audit_semantic_fulfillment,
  validate_contract`); consumes `constraint_extractor.extract_constraints_async`
  (`multi_section_generator.py:11243-11249`); `scope_contract.apply_scope_contract:180 / deepen_scope_contract:316
  / build_scope_deepening_queries:415`; replaces/adapts `coverage_obligations.build_obligations, thread_obligations,
  audit_fulfillment` (reject the nonempty-text audit); `outline_agent.run_outline_agent_or_legacy,
  refine_outline_from_seed`; routes owned baskets in `multi_section_generator._assign_evidence_to_planned_outline:2555`
  (constraint/coverage seam `:11223-11265`, final audit `:13621-13626`); carries block/claim IDs through
  `_run_section:6242` → `verified_compose._compose_section_per_basket:2841`; layout-only normalizer replaces/extends
  `_materialize_paragraph_breaks:3686`; removes the hardcoded judged-body preamble
  `compose_agentic_report_s3gear329.py:680-694` and turns `:776-810` method telemetry into a planned method block.
  Internal order: schema/validator → admission → coverage/deepening → owner routing → section/block projection →
  semantic audit → layout normalization.
- **[S] W2 — Mechanism + relation reasoning + licensed deductions (U2, U3, U1).** Extend AC with `mechanisms,
  relations, inferences`. `analytical_contract` gains `build_mechanism_chains, build_relation_edges,
  plan_block_inference, validate_inference_tokens`; `_FACET_SKELETON_ADDENDUM:942` + `_select_outline_system_prompt:1650`
  project the framework role; `outline_agent` consumes mechanism obligations (drops the anti-mechanism gap rule);
  `contradiction_mining.cluster_candidate_pairs/_judge_prompt/find_contradictions` retain all verdict classes +
  boundary reasons; `relation_evidence_packs._attributes/build_relation_evidence_packs/relation_context_for_plan`
  become contract builders; producer consumes block inference plans; `SECTION_SYSTEM_PROMPT_TEMPLATE:3508-3615` may
  describe the licensed inference (prompt text is not wiring proof).
- **[S] W3 — Context/measurement/concept/comparison (U6, U9, U8, U4).** Extend AC with `contexts, measurements`,
  designated-concept roles, `table_plan` block subtype. `analytical_contract` gains `build_context_profiles,
  select_context_diversity, build_measurement_ontology, build_concept_role_spine, plan_comparison_block,
  plan_table_block`; retire `relation_evidence_packs._proposition_key:56` token-bag; retire
  `_construct_synthesis_table:8437` + `PG_SUMMARY_TABLE_COMPOSE:746-761` from judged output; tables emitted from
  block/claim plans through the producer with cell ownership + following interpretation; `find_malformed_tables`
  stays a render check.
- **[S] W4 — Epistemically labeled synthesis + implications (U7, U10).** Extend AC with bounded `inferences,
  implications` referring to upstream IDs. `plan_cross_basket_inferences, assign_epistemic_status, plan_implications,
  validate_upstream_reasoning`; `_FACET_SKELETON_ADDENDUM:942-960` closing/synthesis roles project only approved
  objects; producer emits labeled inference/implication through ordinary markers + unchanged verifier; W1 semantic
  audit checks every implication resolves valid upstream IDs and every non-established inference has a resolving
  observation.
- **[S] W5 — External FACT claim/citation planning (U14).** Extend each `claim` with atomic frame, exact span,
  canonical reachable URL, inline mapping, dedup key, extractor eligibility (`plan_external_citation,
  validate_extractor_eligibility, validate_canonical_url, expected_dedup_key`); `deepen_scope_contract` supplies
  more admitted works only for unfilled obligations; producer emits distinct source-specific facts as distinct
  cited units while retaining same-proposition corroboration; provenance/strict-verify unchanged; tests run
  extract/dedup first, full scrape/validate/stat only after structural success.

### 4.B — Fable's waves (proven-winner-first)

- **[F] W1 (first ship) — "Writer contract + render floor" (U1 + U12-lite + U14b).** AC carrier itself
  (empty-safe, champion-preserving) + its consumption point in `_compose_section_per_basket`, with the
  licensed-inference class + render/layout plan as its first two payloads. Files: `multi_section_generator.py:3517-3519`
  (add inference class), `:4420-4432` (retry contract), `:6630-6728` (producer consumption), `:3686-3692`
  (normalizer joins this class), `:3581-3585` (own-line heading rule); `compose_agentic_report_s3gear329.py:680-694`
  (delete preamble); `:8843-8917` `_deterministic_reader_limitations` (pin reader-register, one Limitations role);
  `cleaned_output_guard.py` (extend lints). Coherent: one seam, zero upstream deps, both investigators' #1 fix +
  floor-repair for our only below-parity dim; Bodhi labeled-deduction form writer-chosen.
- **[F] W2 — "Relation layer" (U3 + U4 + U6).** Extend AC with the evidence-relation graph/divergence ledger {class,
  subject, predicate, measure, reason} × 3 edge types + comparison groups + table plans with cell ownership. Files:
  `contradiction_mining.py:123-126,132,167` (harvest all classes, today yield 0); `relation_evidence_packs.py:56-66`
  (replace token-bag key w/ `_attributes:69-85`), `:190-205` (global-map delivery); `multi_section_generator.py:4188-4198`
  (per-group directives to the active producer), `:8437-8573` (retire sentence-span table);
  `compose_agentic_report_s3gear329.py:746-761` (retire post-assembly insertion). Coherent: same structure viewed
  three ways; U4/U6 meaningless without U3's ledger.
- **[F] W3 — "Coverage, admission & citation volume" (U5 + U11 + U14a).** Extend AC with coverage ledger (named
  dimensions + entity-class quantifiers + 4 analytical roles; STATUS supported|retrieval-needed|unsupported-
  disclosed) + source-admission ledger (type/language/evidence-based quality; unknown → retrieval target/disclosed
  gap) + claim/citation plan. Files: `scope_contract.py:40-43` (`_EXCLUSIVE_RE`), `:152-177`/`:223-262` (admission +
  quality attrs), `:316-413` (wire deepening ON), `:415-491` (typed queries); `outline_agent.py:1309-1332,1449-1462`
  (relax STRICT GROUNDING to "named OR implied by ledger"); `coverage_obligations.py:107-136,139-158` (semantic
  fulfillment); `compose_agentic_report_s3gear329.py:431` (deepening), `:776-810` (methods telemetry → policy
  sentence); `multi_section_generator.py:3902-3938` (`format_source_attribution_metadata` USE-in-prose directive).
  Coherent: one seam (what may enter + what must be covered); U14a is mathematically downstream of U5 (linear pair
  growth); only wave that changes corpus breadth, so it follows Wave-1's routing-independent gates.
- **[F] W4 — "Architecture spine" (U2 + U8 + U10).** Extend AC with mechanism spine (channels, net-condition,
  boundaries, reusable lens IDs) + concept-role spine + implication objects. Files: `multi_section_generator.py:939-960`
  (fifth framework role + reuse contract), `:955-956` (closing role), `:3532-3540` (conditional causal rule finally
  fed); `outline_agent.py:1324-1331,1447-1458`; `compose_agentic_report_s3gear329.py:398-410` (constraint extractor
  as trigger); `config_defaults.py:920` (coverage-spine default noted, superseded by AC roles); heading-echo
  ownership via `_conform_plans_to_required:1940` (GAP-7 folded into U5/U8 tests). Coherent: all OUTLINE-time role
  objects; U10 consumes U2 mechanism IDs + W2 synthesis; t91 no-fire is this wave's signature generalization test.
  **[F] Sequencing note:** W4 after W3 so U2/U8 induce channels over the COMPLETE (deepened) corpus, not twice;
  U10-lite (closing-role resolvability alone) MAY pull forward into W1 (OQ-6).
- **[F] W5 — "Semantic governance" (U7-full + U9 + U13 + U12-full).** Extend AC with inference plans (independent
  premises, operator, boundary, status, falsifier) + measurement ontology + routing ownership (every basket
  declares marginal contribution or stays archived) + block plan (one reader-question + one movement per block,
  transition relations). Files: relation-graph consumer from W2 (U7 planner); `relation_evidence_packs.py:69-85`
  (ontology fields); routing path that produced "Additional Corroborated Findings" 433 IDs vs the anti-residual
  rule `multi_section_generator.py:3593-3595`; blocks `:3670-3707,:6748-6750,:3729-3740`. Coherent: governs content
  earlier waves created; last because most upstream deps, not least valuable.
- **[F] Explicitly retired (no wave rebuilds):** `PG_SYNTHESIS_TABLE_CONSTRUCT` / `PG_SUMMARY_TABLE_COMPOSE`
  (wrong-idea + post-gen violation), the raw-JSON relation-pack dump, the hardcoded driver preamble — pending OQ-2.

---

## 5. DEPENDENCY GRAPH + CRITICAL PATH (both agree on the DAG; presented merged)

**[S] Dependency statements:** U11 governs what later counts as support (else polished claims from ineligible
material); U5 supplies the semantic ledger + retrieval-needed states used by U6/U8/U13/U14; U2 supplies mechanism
IDs for U1 and U10; U3 supplies the relation graph for U4/U6/U7/U9/U10/U14; U6 and U9 must precede U4 (a shared
table schema is lawful only for materially different contexts with compatible measures); U7 depends on multi-basket
relations; U10 depends on mechanisms/inferences/measurement; U12 is a cross-cutting carrier (without preserved
block IDs, U1's deduction, U4's table, U7/U10's labeled blocks can't be audited at the producer); U14 depends on
U5's admitted-work growth + U11/U13 ownership.

**[F] Notes:** U1 does NOT require U2 — the before-number (deduction rate 0.16) and fable5's 0.5131 Insight at
3,071 words prove per-paragraph deduction pays standalone; U2 later upgrades those deductions from paragraph-local
to spine-reusing. U6 sits across the relation and coverage waves (its schema is relation-layer, its instance supply
is coverage-layer).

**[S+F] Critical path (score-weighted): `U3 → U4/U6 → U7`** — carries Insight #8 (0.0800), Comp #3 (0.0725),
Insight #10 (0.0640); U3's head converts a measured-zero lever into the substrate for three components. **[S]
Full chain:** contract carrier/U12 → U11 admission → U5 semantic ledger+deepening → U3 relation graph → U6+U9
context/measurement → U4 comparison → U7 labeled inference → U10 implications → U14 atomic external citation.
**[F] Secondary path:** U5 → U6/U13/U14a (Comp breadth + FACT volume). **[F] U1 is off-path (no dependents block
on it) — the reason it can ship first at max expected value, zero blocking risk.** **[S] U2 can build in parallel
with U11/U5 once the schema exists, but U1 cannot ship until U2, U3, and the U12 block carrier meet at the
producer** — the crux of the §1 disagreement.

---

## 6. PER-WAVE GO/NO-GO — merged by the underlying gap tests (seam-agnostic; apply to whichever wave lands the gap)

The deterministic gates are gap-level and identical across both plans; grouped here by gap so either decomposition
can consume them. Each gate is the cheapest-first, then the paired probe.

- **U1** [F]: `paragraph_deduction_rate` 0.16→**>0.6** + zero-new-factual-token canary **0 violations** + render
  lint (run-in headings ≥2→0, repeated subheads 4–6→0, preamble absent, verbatim dupes ≥2→0) + normalizer
  token-multiset equality + wiring assertion (directive present in `_compose_section_per_basket` inputs). Cheapest
  proof: compose 2–3 sections from frozen baskets through the producer (minutes). Expected: Insight ↑ (two 0.0800
  cells), Read ↑ (0.0840 band). Probe: 3v3; ship if Insight paired mean > +0.027 OR (Insight ≥ 0 AND Read >
  +0.027), no dim < −0.027 (the Read guard is the U1-density risk check).
- **U3** [S+F]: isolated miner unit-run on the frozen corpus → divergence ledger **non-empty** with boundary
  reasons where today's harvest = **0** (reuses paid verdicts, ~0 new LLM cost); **[S]** three-relation fixture
  (conflict / compatible-at-different-margins / unrelated) → exactly the three edge states; miniature cross-source
  proposition cites both sides, names the boundary, survives unchanged strict-verify.
- **U4** [S+F]: simulated-clean lint (strip citation cols → `find_malformed_tables` **0** defects; today 8) + **0**
  verbatim body-duplications (today ≥2); comparative-coverage counter (sentences citing ≥2 differing-context rows);
  table plan only for shared compatible fields, every factual cell owns evidence+units, interpretation block
  follows; old `Finding|Value|Source` + post-assembly paths absent from judged report.
- **U5** [F]: retrieval-only ledger-fulfillment telemetry (every row → ≥1 admitted row or disclosed unfillable;
  distinct entity-class instances **3 → ≥8**); **[S]** decoy test (nonempty section omitting a required dimension
  FAILS until the covering proposition is planned+emitted).
- **U6** [S+F]: synonym contexts do NOT satisfy diversity; common-schema plan contains only shared dimensions;
  multi-regime proposition uses evidence from distinct regimes.
- **U7** [S+F]: synthesis section ≥1 labeled proposition per multi-member cluster (today **0**), label lexicon +
  ≥2 markers; joint/single/confounded fixtures (only joint yields a synthesis-derived proposition with falsifier;
  confounded → unresolved).
- **U8** [S+F]: designated driver gets a role spine, background term does not; intro-only mention FAILS the
  semantic audit. **[F]** heading-echo lint (every question-named topic matches a heading; today ≥2 unmatched).
- **U9** [S+F]: incompatible metrics refuse a common aggregate; one-sided evidence discloses asymmetry, never
  invents a counterclaim.
- **U10** [S+F]: resolvability clause per gap bullet **0/4→4/4**; every implication carries valid upstream
  proposition IDs; generic recommendations rejected; benefit/harm states affected party + conditions.
- **U11** [F]: zero internal-vocabulary (tier) tokens in the rendered report (today FAILS); policy sentence present
  iff exclusive constraint extracted AND every clause entailed by telemetry; venue-attribution rate ~0 → **≥0.8**;
  corpus eligibility-compliance counter (43%→73%) re-run at the compose seam; **[S]** mixed-metadata partition
  fixture (eligible/wrong-type/wrong-language/unknown/retracted/unverified) partitions completely, no inadmissible
  row in any plan.
- **U12** [S+F]: block IDs survive outline → producer → unchanged verification → render one-to-one; headings on
  own lines; normalizer changes no ordered non-whitespace token; zero run-in headings / repeated template
  subheadings / truncated preamble / assembly-caused duplicate sentence.
- **U13** [S]: every emitted block has one valid analytical owner; corroborators merge into the owning proposition;
  archive-only evidence stays available; **no residual-section role**; no fragment sentinel.
- **U14** [S+F]: extract+dedup-only pair count (no scrape/validate) grows proportionally to admitted-work growth vs
  today's 11; **[S]** every eligible claim → one complete extractable statement–URL identity; distinct facts =
  distinct cited units; unique-pair growth proportional to new admitted work, not marker repetition; full FACT run
  on the final candidate → valid_rate ≥ baseline (no precision regression).

**[S+F] Assembled-ladder probe** closes the initiative: the full final config vs the original mf_baseline, ≥3v3 —
build-all-then-measure's terminal read.

---

## 7. MERGED RISK REGISTER

### 7.A Not-fixable-pre-generation (live-with) — [S+F]
1. **Cleaner nondeterminism/truncation** — judged text is an LLM rewrite we don't control; make artifacts
   robust-to-cleaning (U4 lint, U12 hygiene), hash frozen cleaned articles for scoring, one end-to-end robustness
   run; never claim a cleaning-dependent win from one draw. 2. **Single-call judge variance ±0.027** — irreducible;
   all decisions on ≥3v3 paired means. 3. **Reference frame + contamination** — RACE is relative to the frozen
   Gemini reference; adopt winning surfaces, never compare across judge regimes. 4. **FACT URL reachability / Jina
   drift** — canonical stable URLs + reachability preflight; accept residual. 5. **Strict-verify sentence removal**
   — stronger evidence ownership or plan-regeneration, never firewall weakening. 6. **Post-gen rewrite forbidden**
   — NVIDIA move stays absorbed pre-gen; no exception creep beyond the labeled layout normalizer. **[S]** 7.
   Champion's historical verify-off config must not be confused with production safety — it is only the RACE oracle;
   every production candidate still passes markers, canary, and the unchanged verifier.

### 7.B Fixes that RISK a different cell (cost cells + mitigations) — [F] primary, [S] parallels folded in
- **RC-1 (U1 → Read density).** Per-paragraph deductions raise density; #1/#3/#4 systems all bottom out on Read
  (cellcog 51.94, Bodhi 51.87, Lunon 50.48) and we start BELOW parity. Mitigation: exactly ONE closing inference
  per paragraph (structural cap, not a count knob); U12-lite in the same wave; Read as co-primary probe guard.
- **RC-2 (U11 → Comp/FACT via corpus shrink).** Tier ceiling ~73%; Sourcery proves a thin sector base forfeits
  ~3 Comp points. Mitigation: U5 typed deepening refills BEFORE enforcement verdicts finalize; unknown-eligibility
  → retrieval target not silent drop; couple ledger fulfillment WITH compliance so neither ships alone; residual
  shortfall disclosed Dalpha/Bodhi-style; **[S]** acceptable shrink is an operator decision.
- **RC-3 (U5 deepening → focus/Read walls).** More evidence historically became more prose (433-ID dump).
  Mitigation: ledger-SCOPED admission; U13 routing lands later, so include "no residual-section role" as a free
  regression lint until then.
- **RC-4 (U4 tables → Read under cleaner).** Mitigation: tables only from table PLANS with short-phrase cells +
  mandatory interpretation; simulated-clean lint permanent; where comparability fails, plan prose (fable5 won Read
  0.5262 WITH 14 table rows — malformed tables are the enemy, not tables).
- **RC-5 (U7 labels → fabrication-adjacent).** Mitigation: labels require ≥2 cited premises + the canary; confounded
  fixture must yield "unresolved"; unlabeled novelty stays banned.
- **RC-6 (U2 on non-analytical tasks).** Mitigation: question-type conditionality via constraint extractor + the
  mandatory t91 no-fire held-out test.
- **RC-7 (U14 atomic sentences → serial-summary Read).** Mitigation: rule applies only to independently supported
  DISTINCT facts; paragraphs stay claim-led (U1's closing inference gives synthesis); Read guard in every probe.
- **RC-8 (probe budget/schedule).** 5 waves × ≥3v3 ≈ 30+ generations + judge calls; under-budgeting invites
  single-draw shortcuts R3 forbids. Mitigation: fix the budget up front (OQ-5); deterministic gates kill weak
  components before any RACE spend.
- **[S] additional cost-cell rows:** semantic deepening broadens retrieval cost (cheapest telemetry first; stop
  when supported/disclosed, not at a breadth number); context-diversity must not become a hidden source cap (select
  for ownership without deleting sources; no max context count); measurement ontology must not suppress useful
  heterogeneity (block only aggregation, keep incompatible findings as labeled evidence); marginal-contribution
  routing must not be mistaken for deletion (archive + bibliography retain everything; only confirmed junk follows
  the existing carve-out); layout normalization must not cross into content editing (token identity or no-go).

---

## 8. OPERATOR DECISIONS BLOCKING THE BUILD (merged [S] 8 + [F] OQ-1..8)

1. **[S+F] OQ-1 Held-out generalization set.** Confirm the frozen tasks. Recommended core: **91 + 100** (mandatory,
   opposite Insight extremes) + one of {73, 51, 4}. Also decide: held-out runs outline/compose-level (cheap) or
   full-report (costly, more faithful). **Blocks Wave 1.**
2. **[S+F] OQ-2 Legacy lever retirements.** Confirm permanent retirement of `PG_SYNTHESIS_TABLE_CONSTRUCT` /
   `PG_SUMMARY_TABLE_COMPOSE` (wrong-idea + post-gen violation) + the raw relation-pack JSON dump, vs keep-behind-
   AC-switch for forensics; and rewire contradiction-mining/relation-packs/coverage-obligations into the AC.
   **[F] Blocks Wave 2.**
3. **[S+F] OQ-3 Eligibility posture + acceptable corpus shrink.** Hard-enforce (drop ineligible from body) vs
   enforce-and-disclose (admit flagged exceptions with role disclosure, Dalpha/Bodhi-style); how much shrink before
   Wave 3 must stop (RC-2). **[F] Blocks Wave 3.**
4. **[F] OQ-4 Licensed-inference doctrine sign-off.** Explicit sign-off that the paragraph-closing inference
   sentence (zero-new-factual-token, union-of-markers) is an approved amendment to the closed-world writer contract
   — the single doctrine change in the plan, adjacent to two standing hard rules (no post-gen fixes, no entailment
   machinery); R2/C2 is the enforcement mechanism. **Blocks Wave 1.**
5. **[S+F] OQ-5 Measurement budget.** Approve ≥3v3 paired draws per wave (5 waves + 1 assembled-ladder ≈ 33–40 full
   generations + judge runs) + the wall-clock envelope per generation. **[F] Blocks Wave 1.**
6. **[F] OQ-6 U10-lite pull-forward.** Whether to move the closing-role resolvability directive (deterministic gate
   0/4→4/4, near-zero cost) into Wave 1's writer-contract payload.
7. **[S+F] OQ-7 Deepening in the champion/production path.** U5 turns the retrieval loop ON at the compose seam
   (`requires_retrieval_pipeline`); confirm the runtime budget permits it in production, or whether deepening runs
   only in a pre-compose corpus-build stage. **[F] Blocks Wave 3.**
8. **[S+F] OQ-8 FACT track: baseline + coupling.** (a) Select the production FACT non-inferiority baseline (faithoff
   11@100% / b0fact 16@94.1% / b1fact 31@68.9%); (b) confirm U14 stays coupled to the coverage/admission wave
   (nearly free there) vs a separate deferred track.
9. **[S] OQ-9 Visible discourse labels.** Whether planned deduction/epistemic blocks visibly render labels
   (`Implication`, `Evidence status`, `What would resolve this`) or natural prose over the same typed contract —
   the safer audit surface is visible labels; the readability trade-off must be measured.
10. **[S] OQ-10 Inconclusive-paired-result policy.** Approve the prespecified maximum confirmatory pair count when a
    delta/small-negative stays inside ±0.027 — a fixed cap set before looking, no redraw-until-win.
11. **[S] OQ-11 FACT canonical-URL policy.** Preference order among DOI resolver / journal landing / stable
    repository when several URLs represent the same work, + the max allowed age of the reachability preflight.
12. **[S] OQ-12 Promotion strictness across non-target dimensions.** Confirm the conservative rule (no material
    regression ≤ −0.027, no promotion on an unresolved negative mean) rather than permitting an Overall-for-dimension
    trade.
13. **⭐ OQ-0 (Opus-added, the §1 decision) — FIRST-SHIP WAVE.** Choose the build sequence: **Fable's
    proven-winner-first** (W1 = U1 + U12-lite + U14b; Opus-recommended) vs **Sol's governance-foundation-first**
    (W1 = U5 + U11 + U13 + U12). Both reach the same end state; they differ on what ships first and how waves group
    (§4). This gates everything.

---

## 9. FINAL BUILD ORDER, FIRST SHIP, BLOCKERS

**[F] Recommended order (Opus concurs):** **W1 (U1 + U12-lite + U14b) → W2 (U3 + U4 + U6) → W3 (U5 + U11 + U14a) →
W4 (U2 + U8 + U10) → W5 (U7-full + U9 + U13 + U12-full)**, ladder-measured (each shipped wave becomes the next
comparator), critical path U3 → U4/U6 → U7-full, closed by the assembled-ladder probe.
**[S] Alternative order (governance-first):** W1 (U5+U11+U13+U12) → W2 (U2+U3+U1) → W3 (U6+U9+U8+U4) → W4 (U7+U10)
→ W5 (U14).

**First-ship wave (recommended): WAVE 1 = the AC carrier + licensed paragraph-closing inference (U1) + layout
normalizer/preamble-removal/single-Limitations (U12-lite) + one-fact-one-cited-sentence (U14b).** GO requires ALL
deterministic gates — `paragraph_deduction_rate` 0.16→>0.6; zero-new-factual-token canary 0 violations; render
lint (run-in headings ≥2→0, repeated subheads 4–6→0, preamble absent, verbatim dupes ≥2→0); normalizer
token-multiset equality; AC payload visible in `_compose_section_per_basket` inputs; held-out deterministic pass on
the OQ-1 tasks — THEN a 3v3 paired probe vs the pinned mf_baseline champion (0.5009): ship iff Insight paired mean
> +0.027 (or Insight ≥ 0 with Read > +0.027) and no dimension regresses beyond −0.027. Cheapest pre-60-min proof:
2–3 sections composed from frozen baskets through the active producer + the free render lint on existing artifacts.

**Decisions blocking Wave 1:** OQ-0 (first-ship sequence), OQ-1 (held-out set), OQ-4 (licensed-inference doctrine),
OQ-5 (probe budget). OQ-2 blocks Wave 2; OQ-3 and OQ-7 block Wave 3; the rest decidable in flight.

**No pipeline code is written until the operator approves this plan and answers the Wave-1 blockers.**

---

## 10. OPERATOR DECISIONS — RESOLVED 2026-07-23 (Wave-1 gate CLEARED)

- **OQ-0 (first-ship sequence): FABLE PROVEN-WINNER-FIRST.** Build order W1 (U1 + U12-lite + U14b, AC carrier as
  definition-of-done) → W2 (U3 + U4 + U6) → W3 (U5 + U11 + U14a) → W4 (U2 + U8 + U10) → W5 (U7-full + U9 + U13 +
  U12-full). Sol's governance-first order is the fallback if Wave 1 measures flat despite green deterministic gates.
- **OQ-4 (licensed-inference doctrine): APPROVED.** The paragraph-closing inference sentence (derives what a
  paragraph's already-cited findings jointly imply; zero new factual token/number/entity; carries the union of the
  paragraph's markers) is an approved amendment to the closed-world writer contract, enforced by the C2 canary.
- **OQ-1 (held-out set): 91 + 100 + 73.** Every fix's deterministic test must pass on task 72 AND on task 91
  (inventory, .11 Insight — mandatory no-fire conditionality), task 100 (analytical, .40 Insight), task 73
  (Read .25, readability stressor).
- **OQ-5 (probe budget): WAVE 1 ONLY for now** (~6 generations = 3v3 paired vs mf_baseline). Remaining waves'
  budget decided after the Wave-1 result.
- OQ-2/3/6/7/8/9/10/11/12: not yet needed (OQ-2 before Wave 2; OQ-3/7 before Wave 3; rest in flight).

## 11. CRITICAL RETARGET — canonical scoreboard = Gate-B / V30-ON (operator decision 2026-07-23)

Four Sol design-gate rounds on the Wave-1 spec surfaced that POLARIS has TWO writer architectures gated by
`PG_V30_PHASE2_ENABLED`: the LEGACY abstractive path (`_run_section`→`abstractive_pre_pass`→`_call_writer`→
`_compose_section_per_basket`, active when V30=0, the DEFAULT — how mf_baseline 0.5009 was generated), and the V30
CONTRACT-SECTION/SLOT path (`contract_section_runner.run_contract_section`→`slot_fill.build_slot_narrative_prompt`,
active when V30=1). `scripts/dr_benchmark/run_gate_b.py:5746` FORCE-sets V30=1 and self-describes as "THE PRIMARY
LIVE BENCHMARK PATH". **Operator decision: the canonical scoreboard is Gate-B / V30-ON.** Consequences:
1. **mf_baseline 0.5009 is INVALID as champion** (generated V30-off). MUST RE-BASELINE under V30-on before any
   Wave-1 measurement.
2. **Wave-1 transport retargets** from the abstractive writer to the V30 narrative stream
   (`build_slot_narrative_prompt` / `_SYSTEM_PROMPT` slot_fill.py:207,703; `run_contract_section` :1627).
3. **The CHARTER (C1-C5), pre-producer canary doctrine, exact emitted==admitted-candidate binding, ordered-token
   layout, complete-route coverage, OFF-path identity, semantic naming, and 6-stage staging ALL CARRY OVER** — only
   the transport target moves. The 4 gate verdicts remain the faithfulness/correctness rulebook.
4. **Phase-3 PIPELINE_GAP_AUDIT needs a V30 re-map** (its "active producer" seam is legacy-path).
NEXT: Sol line-by-line investigation of the V30 slot writer → retargeted Wave-1 seam map → spec v4 → re-gate →
build Stage 1. Re-baseline generation run is a prerequisite.

---

## 12. ROLLBACK — Phase 4 re-run under a NO-GHOST charter (operator decision 2026-07-24)

**Why.** The Wave-1 build (specs v1–v4 + Stage-1, gated by Sol SOLO) drifted into exactly the banned pattern: a
runtime `LicensedInference` **admission canary**, an `OPERATOR_LICENSE` **entailment predicate** "proving" an
inference is premise-licensed, `PremiseRelation` records, **exact emitted==admitted binding audits across ~27
rewrite routes**, and **non-scoreable-on-mismatch** report suppression. That is the faithfulness-ghost /
post-generation-fix / content-drop family the operator has HARD-BANNED (it cost months and damages RACE). The seed
entered in Phase-4 C2 (Sol's "admission canary… permitted reasoning operator" language, which I consolidated
alongside — and in contradiction to — Fable's "No new entailment/NLI machinery anywhere"); Sol-solo build gates
then inflated it.

**Rollback (operator-directed).**
- **KEEP (clean, both-gated, generalized, no overfit):** Phase 1 (SCORING_SPEC), Phase 2 (COMPETITOR_TEARDOWN),
  Phase 3 (PIPELINE_GAP_AUDIT — pre-generation fixes + deterministic TESTS). PLUS the VALID architecture facts:
  the active writer is the V30/Gate-B slot narrative path; canonical question = legacy task-72 (4IR); the champion
  must be re-baselined V30-on/task-72 (mf_baseline 0.5009 was V30-off). See §11 and `phase4_v30_retarget_verdict.md`.
- **DISCARD:** C2's runtime admission-canary clause (VOID, flagged above); Wave-1 specs v1–v4 + Stage-1 spec; the
  entire AnalyticalContract / canary / exact-binding / 27-route-audit apparatus.
- **REDO — re-run Phase 4** to turn the clean Phase-3 gaps into a V30-targeted MASTER plan under a HARD NO-GHOST
  charter, gated by **BOTH Fable and Sol** (two-model discipline restored — Fable authored "no entailment
  machinery" and is the counterweight Sol-solo lacked). Hard constraints every design must satisfy:
  1. NO entailment/NLI/faith-ghost machinery of any kind.
  2. NO post-generation content edit or content-drop/suppression gate (layout-only whitespace/heading
     normalization, provably content-preserving, is the sole exception).
  3. NO runtime admission gate / licensed-inference admission / premise-relation license / operator-license
     predicate / exact-emitted==admitted binding audit / non-scoreable-on-mismatch.
  4. Fixes are PRE-GENERATION prompt / scope-contract changes ONLY, reaching the ACTIVE V30 writer, relying on the
     EXISTING faithfulness engine untouched.
  5. Deterministic checks are TESTS that gate a lever's SHIP decision — never runtime content gates.
  6. If a gap cannot be fixed cleanly pre-generation → DROP THE LEVER. No machinery.
  7. No overfit / task-domain literals / magic counts / adjective-version flag names.
  8. Retargeted to the V30 slot writer + task-72; measure-first (establish the real V30-on/task-72 baseline before
     any lever).
- **THEN build** per the corrected plan, each small pre-gen change gated by both models, measured against the real
  V30-on/task-72 baseline.

The five Sol Wave-1 gate rounds are retained in scratchpad as a cautionary record; their VALID output (the V30
architecture map, the champion-invalidity finding, the question-lineage discovery) is preserved above and in
`phase4_v30_retarget_verdict.md`.
