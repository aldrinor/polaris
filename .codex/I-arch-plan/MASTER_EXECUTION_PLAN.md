# MASTER EXECUTION PLAN v2 (DEFINITIVE) — FS-Researcher-complete-and-beat + full user-adjustability

Author: FABLE 5 (architect brain). Date: 2026-07-10. Branch: `bot/I-deepfix-relaunch`.
Supersedes v1 of this file. Synthesizes: `00_frontier_reference_2602_01566.md` (FS-Researcher,
arXiv 2602.01566), `01_offtopic_subquery.md`, `02_holistic_review.md`, `03_deliverable_awareness.md`,
`04_baskets_per_section.md`, `05_orchestrator_revise.md`, `06_checkpoint_resume_arch.md`,
`07_querygen_breadth_scope.md`, anchored on `.codex/I-arch-audit/fable_orchestration_audit.md`.

**What v2 adds over v1 (the three folds):**
1. **The FS-Researcher completion framing (§0):** the campaign is now explicitly "finish the three
   parts of the paper POLARIS skipped, then beat the paper at its one weak point."
2. **Design 7 is a build item, not a reference doc:** query-gen breadth resolver + scope flowing
   into every search backend and into query wording (folded into S1, §3 R11).
3. **THE BIG ONE — full user-adjustability via ONE RunConfig (§1):** every knob in the pipeline is
   user-controllable two ways — written in the natural-language prompt, or set on an explicit
   control panel. This is a cross-cutting HARD BUILD REQUIREMENT binding every section.

**How Opus uses this document.** This plan is the ORDER OF BATTLE: it fixes the section boundaries,
the build sequence, the cross-design conflict rulings, and the locked config. Each numbered design
doc remains the BINDING detail spec for its component (file:line seams, dataclasses, flags, prompts).
Where this plan and a design doc disagree, THIS PLAN WINS (the rulings in §3 exist precisely to
resolve those disagreements). Opus follows this plan verbatim: work packages in §7 order, each under
§-1.2 issue-first workflow, each dual-gated (real Codex CLI + real Fable 5, both APPROVE), 200-LOC
PR cap with declared exemptions.

**Standing mandates (unchanged, binding on every work package):**
- §-1.3 weight-and-consolidate; the faithfulness engine (strict_verify / NLI / 4-role D8 /
  provenance / span-grounding) is UNTOUCHED by every package — zero diffs under those paths, checked
  at every gate.
- §-1.1 line-by-line forensic audits; no metadata/pattern/sample shortcuts.
- LAW VI: every knob is config, never a hardcoded value — now formalized as the RunConfig principle
  (§1); defaults are byte-identical-OFF; the Gate-B slate pins the ON state.
- §9.1.8 model/token lock: generator `deepseek/deepseek-v4-pro`, mirror `z-ai/glm-5.1`, sentinel
  `minimax/minimax-m2`, judge `qwen/qwen3.6-35b-a3b`; side judges map to the mirror; max_tokens
  generous (cap-not-target); no per-leg model knobs. Model choice is NOT a RunConfig knob.
- Fable investigates root cause, Opus builds, Codex+Fable gate. Offline tests are not a preflight:
  each section proves itself on banked replay, then ONE small real run, before any paid full run.

---

## 0. THE FRAMING — complete FS-Researcher, then beat it

arXiv 2602.01566 IS the paper POLARIS took its production query-gen from
(`retrieval/fs_researcher_query_gen.py`, `PG_QGEN_FS_RESEARCHER=1`). POLARIS adopted ONLY the
query-gen slice. The paper's actual headline machinery — the structured knowledge base feeding the
writer, the outline-as-todo with section checklists, and the report-level review that RE-OPENS
failing sections — was never adopted, and those three skipped parts map one-to-one onto the top
gaps in our own orchestration audit. The paper's ablation says this is the load-bearing piece:
removing the workspace/review loop drops RACE 52.76 → 48.69.

**So this campaign = COMPLETE the three skipped parts, then EXCEED the paper:**

| # | FS-Researcher mechanism we skipped | POLARIS gap (audit) | This plan's fix |
|---|---|---|---|
| C1 | Report-level review with section RE-OPEN ("if flaws are identified, the corresponding sections are marked [IN-PROGRESS] again") | Gap #1: no holistic review in production; sections composed in parallel and concatenated | Design 2 holistic review (S5) + Design 5 ORCH-3 revise with section re-open (S4→S5) |
| C2 | Writer plans the outline FROM distilled, citation-carrying NOTES (`knowledge_base/`), never from raw page titles | Gap #3: outline sees ≤150 rows tersed to ev_id+tier+TITLE only, one shot | Design 5 ORCH-1 basket-digest menu (S4): the outline planner reads consolidated-claim DIGESTS (claim text + corroboration + tier mix + member ev_ids), 100% of pool covered |
| C3 | Section-level checklist ("did this section address every item assigned to it?") + per-section KB subtree loaded on demand | Gap #6: baskets global, composer gets raw rows; no per-section outcome check | Design 4 section-basket map (S5): per-section baskets with primary/corroborating roles; Design 5 `SectionOutcome` digests = the section checklist (unused ev_ids, uncovered baskets, kept fraction, undersupplied) |
| X1 | **THE EXCEED MOVE.** The paper FREEZES its knowledge base when writing starts ("web browsing tools removed") — a section discovered thin at compose time is stuck | We don't freeze | Bounded THIN-SECTION RE-FETCH loop (§4 S-X): when a section's outcome digest comes back thin/undersupplied, the reviser emits targeted gap queries routed through the EXISTING full retrieval lane (tier/topic/junk/dedup all re-apply), one bounded round, then recompose. Doc 00 R8 + Design 5 ORCH-4, now IN this campaign (ruling R10) |

Adoption is MECHANISM-ONLY: the paper's backbones are closed models; POLARIS implements the
architecture on the operator-locked open-weight stack (§9.1.8) — adopt the loop, never the models.
Our grounding stays STRONGER than the paper's (their guarantee is citation-presence; ours is
span-entailment): checklists are STRUCTURAL checks, never claim-truth gates; every sentence any new
loop produces or revises re-runs strict_verify; digests carry ev_id + span offsets so composition
grounds on raw spans, never paraphrased note text. We also do NOT copy the paper's
one-section-per-session serialization (a context-window workaround) — sections stay concurrent.

---

## 1. THE RUNCONFIG PRINCIPLE — full user-adjustability (cross-cutting, HARD requirement)

**Operator requirement, verbatim intent:** EVERY single knob must be user-controllable, TWO ways —
(a) written in the natural-language prompt and parsed, AND (b) set explicitly on a CONTROL PANEL.
This section unifies Design 3 (deliverable), Design 7 (breadth + scope), the existing scope intake,
and Design 6's resume-adjustment vocabulary into ONE object and ONE precedence rule. It is a HARD
BUILD REQUIREMENT on every section of this plan: no section closes its lock-down bar without
RunConfig conformance (§1.6).

### 1.1 One object

New module `src/polaris_graph/run_config.py` (one class, one file, LAW V):

```python
@dataclass
class RunConfig:
    breadth: BreadthBlock         # query_budget (any value incl. 35-or-above), serper_k, s2_k,
                                  # serper_total, fetch_cap, rounds, breadth_class
    scope: ScopeBlock             # date window, source types, geography, jurisdiction, language,
                                  # authors/named sources, peer_reviewed_only — wraps the EXISTING
                                  # UserConstraints + ScopeConstraints (intake_constraint_extractor)
    deliverable: DeliverableBlock # tone, audience, reading level, structure/sections, section order,
                                  # reference style, length target+strictness, depth posture,
                                  # summary_first / recommendations_last / tables, output format
                                  # — wraps Design 3's DeliverableSpec (ruling R1)
    stages: StagesBlock           # every other per-stage knob: topic-gate parallelism, outline
                                  # digest budget, revise rounds/recompose cap, holistic review
                                  # on/off + concurrency + word guards, section concurrency,
                                  # gap-refetch budget, tail-retry knobs, ...
    provenance: dict[str, KnobProvenance]  # per knob: {value, source: panel|parsed|env|default,
                                           #            span: verbatim prompt trigger or None}
```

Every field is optional/None-able; an empty RunConfig = today's behavior byte-identical.

### 1.2 The knob registry — the single source of knob truth

`config/settings/run_config_knobs.yaml` — the canonical registry. One entry per knob:
`{id, block, type, code_default, env_var (legacy alias), earliest_resume_checkpoint,
prompt_parseable: yes/no, panel_widget hint, dna_class}`. `dna_class` is one of
`breadth_budget | scope_constraint | presentation | stage_tuning` and is reviewed at registry time:
**a knob whose purpose would be "make a quality number hit X" is REJECTED at the registry** — the
§-1.3 day-waster ban is enforced structurally, at the schema, not by vigilance. Every existing
`PG_*` env knob that shapes a run's behavior gets a registry row (migration is mechanical, §1.5).
Model/token locks (§9.1.8) and the faithfulness engine's thresholds are NOT registered — they are
operator-locked, not user knobs.

### 1.3 Population — two user surfaces, one merge

```
code defaults  <  env vars (incl. the Gate-B slate)  <  PROMPT-PARSED  <  CONTROL PANEL / CLI
                                                        (S0 extractors)   (explicit overrides)
```

- **Prompt-parsed (surface a):** the S0 intake layer — Design 3's `deliverable_spec_extractor`
  (regex primary + one mirror-model semantic pass, anti-invention: every field carries a verbatim
  trigger span or is rejected), the EXISTING `intake_constraint_extractor` (scope), and Design 7
  D1's breadth directive lexicon ("exhaustive/comprehensive/all available evidence" → WIDE;
  "brief/quick overview" → NARROW; explicit numbers — "run at least 60 queries", "no more than 20
  sources" as a scope ask — honored verbatim). Parsed values land in RunConfig with
  `source: parsed` + the span.
- **Control panel (surface b):** an explicit RunConfig-overrides document — `run_config_overrides
  .json` (or the web POST body). The panel is a pipeline-B/web concern: the UI renders the knob
  registry grouped by block (breadth / scope / deliverable / stages), the user sets values, the
  panel writes overrides. **The backend contract is RunConfig JSON, nothing else** — the sweep and
  `run_gate_b.py` accept `--run-config <file>`; pipeline B's server writes the same file shape. The
  backend never knows a UI existed.
- **Precedence rule (binding, ruling R9):** panel/CLI explicit > prompt-parsed > env default > code
  default. Conflicts are resolved silently by precedence but DISCLOSED: the Methods block lists
  every non-default knob with its value and source layer ("query_budget=80 (control panel; prompt
  asked 'comprehensive' → WIDE=80 agreed)").
- **Safety ceilings stay env-side:** an absolute compute-safety ceiling per breadth knob
  (`PG_*_ABS_MAX` family) bounds even panel values — a ceiling protects the box and the wallet; it
  is never a quality target and it is generous (§-1.3). A user ask above the ceiling clamps LOUDLY
  (disclosed in Methods + run log), never silently.

### 1.4 One vocabulary for fresh runs AND resume adjustments

Design 6's `--adjust` spec IS a RunConfig delta. The validity matrix (which adjustment is legal
from which checkpoint) keys on each knob's `earliest_resume_checkpoint` registry field:
deliverable knobs valid from cp3+, scope knobs from cp1, breadth knobs only at cp0 (they shape
retrieval). "Resume drb_72 from the outline step, tone executive-brief, cap 3000 words" parses
through the SAME S0 extractors into the same object. cp0 IS the pinned RunConfig
(`cp0_run_config.json`, envelope §5): question + question_sha + fully-resolved RunConfig with
per-knob provenance. Resume refuses on RunConfig drift for stages already run (flag-slate assert
generalized), and an adjustment can never mutate a loaded checkpoint's payload.

### 1.5 Every stage reads through the resolver — zero raw env reads for registered knobs

Shared resolver `run_config.get(knob_id)` applies the §1.3 precedence using the pinned RunConfig +
env + registry default. Migration is SURGICAL, not a rewrite: each stage's existing env-read helper
(`_max_queries()`, `_max_serper`, `PG_OUTLINE_REVISE_ROUNDS` reads, holistic knobs, ...) swaps its
`os.getenv` for the resolver — same call sites, same defaults when nothing is set, byte-identical
behavior with an empty RunConfig. The registry + resolver land in WAVE 0 (§7) because every other
section builds against them.

### 1.6 RunConfig conformance — added to EVERY section's lock-down bar

Every section in §4 must additionally prove, before it locks:
1. Every knob the section reads resolves through `run_config.get` — grep proves zero raw
   `os.getenv` for registered knobs in the section's touched files.
2. One harness case where the knob is set BY PROMPT (parsed, span recorded) and one where it is set
   BY PANEL override — both behaviorally fire in the section's output (wiring standard: fires in
   rendered/emitted artifacts, not "flag set").
3. Panel-beats-parsed proven for at least one knob of the section (precedence test).
4. Methods/manifest discloses the section's non-default knobs with source layers.

### 1.7 What RunConfig may NEVER do

No RunConfig knob may: weaken or bypass the faithfulness engine; introduce a hard drop/cap/thin on
credible on-topic sources (§-1.3 — breadth knobs are spend budgets, scope knobs are the user's own
explicit constraints handled weight/mask/disclose, presentation knobs touch wording/order/render
only); select models (§9.1.8 lock); or exist to force a quality number. The registry's `dna_class`
review enforces this at schema time; the dual gate enforces it at diff time.

---

## 2. SECTION DECOMPOSITION — LOCKED-first list

Design 6 §2's skeleton adopted as the master spine: 8 sections, each with a frozen input contract
(the upstream checkpoint) and a frozen output contract (its own checkpoint). All boundaries are
EXISTING seams in `run_one_query` — surgical re-wire, no pipeline rewrite.

**LOCKED / DONE first:**

| # | Section | Status |
|---|---|---|
| **S1.a FETCH** | **LOCKED — DONE, on origin. Do not redesign, do not reopen.** Concurrency 48→14 (band 14-16): commit `67e57837`. Paid-tail retry (Zyte breaker-bypass + Archive.org) on fetch_failed: commit `91045104`. Lock-down record: commit `3c911533`. The as-built commits supersede Design 6 §5's paper spec wherever they differ; the lock-down record in `3c911533` is the binding record. Fetch-yield gate evaluates post-tail; fetch yield (N of M) stays the FIRST forensic number every monitoring tick. | LOCKED |

**Then the rest, in pipeline order:**

| # | Section | Owns | Output checkpoint | Fix applied (design) |
|---|---|---|---|---|
| S0 | INTAKE | question + FULL RunConfig assembly: scope extraction (exists) + deliverable-spec extraction (Design 3) + breadth directive (Design 7 D1 parse side) + panel-override merge + provenance | `cp0_run_config.json` (NEW — is the pinned RunConfig) | Design 3 + Design 7 + §1 |
| S1.b | RETRIEVE (query-gen + search) | breadth resolver sizing query_budget/serper_k/s2_k/fetch_cap from RunConfig; scope → query WORDING (structured SCOPE DIRECTIVES block in TOC/facet/per-todo prompts, author lanes); scope → EVERY backend's filters as ADDITIVE scoped lanes (Serper `tbs/gl/hl`, S2 `year/publicationTypes`, OpenAlex `language/author` beyond the existing date lane); fetch cascade AS LOCKED (S1.a) | `cp1_fetch_snapshot.json` (exists) + intra-section `qgen_checkpoint.json` (Design 7 §3) | Design 7 D1-D3 |
| S2 | SELECT+WEIGH | rerank, scope-weight demote, topic gate (sub-query-aware), junk-deletion gate, LINE-LEVEL three-way select/drop reader (off_topic \| out_of_scope \| junk — operator sharpening 2026-07-10), selection | `cp2_corpus_snapshot.json` (exists) + intra-section `line_screen_verdicts.jsonl` | Design 1 + Design 1 §6 (SELECT+WEIGH v2) |
| S3 | CONSOLIDATE | finding/claim baskets, contradiction detectors | `cp3_basket_snapshot.json` (NEW) | Design 6 (checkpoint only; dedup loop already landed) |
| S4 | OUTLINE | outline planner + basket-digest menu + RunConfig requirement block + revise loop with section RE-OPEN | `cp4_outline_snapshot.json` (NEW) | Design 5 (ORCH-1/2/3) + Design 4 D3 (merged, ruling R2) — FS-completion C2 + C1(structural half) |
| S5 | COMPOSE | multi-section generation, section-basket map (roles), depth/analyst synthesis, fact_dedup, HOLISTIC REVIEW (tail), repetition guard, style block, **FS-Researcher per-sentence SOURCE-TIE** (provenance token `[#ev:<id>:<start>-<end>]` preserved through compose AND survives the holistic-review re-open; each small section traces to its sources — operator 2026-07-10) | `cp5_generation_snapshot.json` (exists; land ITEM 5a re-entry) | Design 4 + Design 2 + Design 3 consumer 2 — FS-completion C1(prose half) + C3 |
| S6 | VERIFY | strict_verify + NLI — **UNFROZEN (operator 2026-07-10):** rewire silent-**DROP** → **LABEL + REPAIR** — keep the unverified sentence in the report with a confidence label + NLI repair, do NOT delete; preserve the grounding/provenance SIGNAL. Kills the thin-report backfire, keeps the clinical-safety signal (operator's `feedback_always_release_verifier_labels_never_holds` rule) | `cp6_postverify_checkpoint.json` (exists; wire re-entry) | **TOUCHABLE** — DROP→LABEL+REPAIR; delete the piece that still backfires. Faithfulness engine no longer the untouchable only-hard-gate (§-1.3 relaxed). See OPERATOR_SECTION_DIRECTIVES §S6 |
| S7 | ADJUDICATE+RENDER | 4-role D8, redaction, reference-style/shape render, assembly, manifest, Methods adherence + knob disclosure | terminal artifacts | Design 3 consumers 3/4 + §1.3 disclosure |
| S-X | EXCEED: thin-section re-fetch | bounded gap re-retrieval loop between wave-1 compose and recompose (Design 5 ORCH-4 machinery; doc 00 R8) | folds into cp4/cp5 chain (gap rows re-enter at S1.b lane → S2 → S3 delta) | ruling R10 — the beat-the-paper move |

S7 is never resumable-past: D8 verdicts are never checkpoint-replayed (§-1.3 ABSOLUTE). The one
narrow exception is a render-only re-run (pure-code `report_assembler`) when prose is byte-identical.

---

## 3. CROSS-DESIGN CONFLICT RULINGS (binding — these amend the design docs)

**R1 — ONE DeliverableSpec.** Build Design 3's `retrieval/deliverable_spec_extractor.py` (the richer
dataclass with `structure_slots`, `reference_style`, `length_*`, `raw_directives`, O2 slot wiring).
Design 5 ORCH-2 does NOT build its own dataclass; it CONSUMES Design 3's spec (`required_sections`
:= `structure_slots` titles; `length_target` := Design 3's length fields). One flag:
`PG_DELIVERABLE_SPEC`. Design 5's `PG_EXTRACT_DELIVERABLE_SPEC` is dropped. **v2 amendment:** the
spec is the `deliverable` block OF RunConfig (§1.1) — same dataclass, one level down; the extractor
is S0's populator for that block.

**R2 — ONE outline basket-digest menu.** Build Design 5's `generator/outline_digest.py` (basket
lines + singleton lines + graceful terse + headroom guard + 100%-of-pool honesty assert). Flag:
`PG_OUTLINE_BASKET_DIGEST`. Design 4's `PG_OUTLINE_BASKET_DIGESTS` flag and its D3 subsection are
superseded; Design 4 keeps everything else (map, roles, refine-NLI, absorb).

**R3 — Holistic review wiring point is Design 2's seam, inside S5.** Inside
`generate_multi_section_report`, immediately BEFORE `_apply_cross_section_repetition_guard` at
`multi_section_generator.py:10633` — sentences still live at SV level with `[#ev:]` tokens, so
strict_verify re-runs directly. D8 stays in S7 and adjudicates the POST-review prose.

**R4 — ORCH-3 revise and the section-basket map compose cleanly.** Order inside S4→S5: wave-1
outline → build `SectionBasketMap` → compose wave-1 → ORCH-3 revise ops (→ S-X gap re-fetch when
active, ruling R10) → REBUILD the map for the new plan set (pure code, <5 s — never patch it
incrementally) → recompose only changed sections → holistic review → repetition guard. Per-section
composed checkpoints key on the PLAN HASH so a revised section invalidates only itself.

**R5 — SUPERSEDED by R10.** (v1 shipped ORCH-4 OFF and out of the campaign. See R10.)

**R6 — checkpoint names.** Design 1's `topic_gate_verdicts.jsonl`, Design 2's
`holistic_review_input/output.json`, Design 4's `baskets_global/outline_plans/section_basket_map
.json`, Design 5's `outline_input/plan/final.json`, Design 7's `qgen_checkpoint.json` are all
INTRA-section checkpoints: listed in `checkpoint_index.json` with `stage` sub-ids, shared envelope
where JSON-shaped (JSONL streams record their file sha256 at section close). The 8 `cpN` files are
the SECTION boundaries; intra-section files make crashes cheap within a section. Design 5's
`outline_final.json` IS `cp4` (one file; names retired in favor of `cp4_outline_snapshot.json`).
Design 6's `cp0_intake_spec.json` is renamed `cp0_run_config.json` (§1.4).

**R7 — Design 2's deliverable-spec dependency is soft.** Holistic review takes the RunConfig
deliverable block when present; `None` → "internally consistent with the report's own dominant
register". The holistic module builds WITHOUT waiting for S0; the spec threads in when S0 merges.

**R8 — ONE RunConfig (new).** Design 3's DeliverableSpec, Design 7's BreadthPlan, the existing
`UserConstraints`+`ScopeConstraints`, and Design 6 §4's adjustment spec are BLOCKS of the single
`RunConfig` object (§1.1). No design builds a second top-level requirement container. `BreadthPlan`
remains Design 7's internal resolver OUTPUT; its resolved numbers are written back into
`RunConfig.breadth.provenance`-tracked values and the manifest.

**R9 — Precedence (new; amends Design 7 D1 input-precedence).** Panel/CLI explicit > prompt-parsed
> env default > code default. Design 7 D1's "explicit env overrides win absolutely" is amended: env
beats CODE default only; a parsed user directive beats a merely-default env; an explicit panel/CLI
override beats everything. The Gate-B slate lives at the env layer; where the benchmark needs fixed
values regardless of prompt phrasing, the slate ALSO writes explicit overrides (panel layer) — the
force-exact frozenset pattern generalizes to the override file.

**R10 — the thin-section re-fetch loop is IN this campaign (new; supersedes R5).** ORCH-4 / doc-00
R8 is the EXCEED move (§0 X1) and gets built, not deferred: gap queries emitted by the ORCH-3
reviser for thin/undersupplied sections route through the EXISTING per-query retrieval lane (same
`per_query_retrieve` the FS sub-queries use — tier classify, topic judge, junk gate, dedup all
re-apply to the new rows), ONE bounded round between wave-1 and the recompose wave, budget from
`RunConfig.stages.gap_refetch_budget` (registry knob; default from `PG_OUTLINE_GAP_QUERIES`).
Build in WAVE 3; it still ships default-OFF and is ACTIVATED in WAVE 5 only after the core loop
holds its bar on a real run (proven-activation discipline; a bounded spend budget, never a quality
target).

**R11 — Design 7 is folded into S0 + S1.b (new).** D1's parse side (breadth directive) is an S0
extractor; D1's sizing side (`breadth_resolver.py` + `config/settings/breadth_classes.yaml`) runs
at the S1.b seam reading RunConfig; D2 (scope → qgen prompts, author lanes) and D3 (scope → Serper
`tbs/gl/hl`, S2 `year/publicationTypes`, OpenAlex `language/author` — each an ADDITIVE scoped lane
beside the untouched base lane, each with its own kill-switch, each fail-open) are S1.b work
packages. §-1.3 discipline as written in doc 07 D3 is binding: scoped lanes only ADD discovery;
post-retrieval enforcement stays weight/mask/disclose; the no-drop superset proof is in the bar.
The FETCH sub-part of S1 is excluded — locked per §2.

**R12 — the control panel (new).** The panel is pipeline-B/web work: it renders the §1.2 knob
registry, writes RunConfig overrides, and calls the same backend contract (`--run-config` /
override file). It is ONE work package in WAVE 4, after the registry is stable. Its PRs touch
`web/**` and therefore carry the 6th artifact (`codex_visual_audit.txt`) per §3.0. The backend
never special-cases the panel: if the panel work slips, prompt-parsing + env + CLI already satisfy
user adjustability end-to-end; the panel is the second surface, not a dependency.

---

## 4. PER-SECTION: fix + hamster loop + lock-down bar + checkpoint boundary

Each subsection names the fix, the fast concurrent loop (test → read-every-line → Fable-investigate
→ Opus-build → retest), the bar, and the boundary. The named design doc's full acceptance list is
BINDING; the bar here is the summary contract Opus must not ship under. **Every bar below silently
includes the §1.6 RunConfig conformance items.**

### S0 — INTAKE → RunConfig (Design 3 + Design 7 parse + §1)
- **Fix:** (i) `run_config.py` + knob registry + resolver (§1, WAVE-0 foundation). (ii) Design 3's
  `deliverable_spec_extractor.py` — regex primary for mechanical fields, ONE mirror-model (GLM-5.1)
  call for semantic fields, O2 `extract_instruction_slots` finally wired; anti-invention: every
  field carries a verbatim trigger span or is rejected. (iii) Design 7 D1's breadth-directive
  parse (lexicon + GLM confirm; explicit numbers honored verbatim). (iv) Panel/CLI override merge +
  per-knob provenance. Threaded: scope_gate seam (after `scope_gate.py:1059`) →
  `protocol["run_config"]` → `cp0_run_config.json` → every downstream consumer.
- **Hamster loop:** Level 0 offline battery (~40 real DRB-II prompt phrasings + breadth/scope
  phrasings, seconds); Level 1 `scripts/deliverable_spec_harness.py` live extraction at
  32-concurrent (~1 min/iter), Fable reads every JSON line field-by-field vs the prompt's actual
  words (parsed-but-not-asked = INVENTED = fail); Level 2 banked-corpus compose replay. Plus the
  precedence matrix test: same knob set at all four layers → resolver picks correctly.
- **Bar (Design 3 §6.b all six, plus):** OFF byte-identical (prompt-string SHA equals HEAD); 100%
  mechanical extraction with spans, zero invented fields; behavioral honoring on 3 corpora × 3
  specs (dual-gate directive-by-directive); faithfulness-neutral (±2% noise, zero diff under
  untouchable paths); fail-open proof; Methods adherence disclosure present; precedence matrix
  green; every knob in cp0 carries provenance.
- **Checkpoint boundary:** clean question in → `cp0_run_config.json` out (atomic, SHA in manifest,
  loaded-never-re-extracted on resume).

### S1.a — FETCH — LOCKED, DONE
Commits `67e57837` + `91045104` + `3c911533` on origin. Concurrency 14 (band 14-16), paid-tail
retry on fetch_failed, lock-down record. NO further work in this campaign. The only touch allowed:
S1.a's already-locked knobs (`PG_BYPASS_MAX_INFLIGHT`, tail-retry flags) get registry rows so the
panel can SEE them — values stay operator-locked defaults; registry marks them `stage_tuning`,
panel-adjustable within the locked band only.

### S1.b — RETRIEVE: breadth + scope (Design 7 D1-D3, ruling R11)
- **Fix:** `retrieval/breadth_resolver.py` — `resolve_breadth(question, protocol, facets, run_config)
  -> BreadthPlan` sizing query_budget/serper_k/s2_k/serper_total/fetch_cap from the ask (explicit
  user number > breadth class WIDE/STANDARD/NARROW > structural width: facet count, multilingual
  profile, scope width), lookup table `config/settings/breadth_classes.yaml`, bounded by env abs
  ceilings; wired at `run_honest_sweep_r3.py:9734-9736` + `max_queries` kwarg into
  `_run_fs_researcher_retrieval` at `:10436` (kwarg exists end-to-end, never used). Scope → qgen:
  structured SCOPE DIRECTIVES block in the TOC/facet/per-todo prompts; landmark-lane pattern
  generalized; author/named-source lane (S2 `/author` + OpenAlex author filter). Scope → backends:
  ADDITIVE scoped lanes — Serper `tbs/cdr + gl + hl`; S2 `year` + `publicationTypes` (scoped lane
  only; journal-only stays dormant globally per operator veto); OpenAlex `language`/`author` beside
  the existing date lane. Flags `PG_BREADTH_RESOLVER`, `PG_SCOPE_TO_QGEN`, `PG_SERPER_SCOPE_FILTER`,
  `PG_S2_SCOPE_FILTER`, `PG_OPENALEX_SCOPE_FILTER` (alias keeps `PG_OPENALEX_DATE_FILTER`); all
  default OFF, all fail-open, base lanes never removed.
- **Hamster loop (Design 7 §3):** search-only mode (real Serper/S2/OpenAlex discovery, no content
  fetch, no generation) over a fixed 6-question probe slate — 2 NARROW / 2 STANDARD / 2 WIDE, incl.
  one dated, one geo-scoped, one non-English; each iteration reads the emitted queries and request
  logs LINE BY LINE. Minutes per iteration.
- **Bar (Design 7 §3 all six):** budget resolution per class + panel/parsed/env precedence + flag-OFF
  byte-identical (35/12/12/200); every issued query on scoped probes carries subject anchor AND
  scope terms, zero contradicting queries; request logs show the scoped params fired AND base lanes
  still fired (union proof); candidate-set superset-or-equal proof (no drop); kill mid-frontier →
  resume issues exactly the pending remainder; every lane emits its `[activation]` marker.
- **Checkpoint boundary:** cp0 in → `qgen_checkpoint.json` (BreadthPlan + full stamped sub-query set
  + per-query result counts; resume re-issues only pending) → `cp1_fetch_snapshot.json` out (via the
  LOCKED fetch).

### S2 — SELECT+WEIGH (Design 1)
- **Fix:** sub-query-aware topic judge. Stamp `retrieval_subquery` on every FS row (3 sites); gate
  derives anchors (`retrieval_subquery` > `query_origin` > none; label/junk anchors degrade to
  main-only); group rows by anchor; dual-anchor prompt per group; verdict set `ON_MAIN /
  ON_SUBQUERY / OFF_ASPECT / OFF_SUBJECT`; ON if on-topic to EITHER anchor; delete stays reserved
  for OFF_SUBJECT-against-BOTH (junk gate needs ZERO changes — the deletable class narrows
  mechanically). `ON_SUBQUERY` stamps a telemetry sidecar. Parallel batch dispatch
  `PG_SCOPE_TOPIC_PARALLEL` (slate 32). Incremental JSONL checkpoint `topic_gate_verdicts.jsonl`
  with header-pinned identity; resume replays judged rows without LLM calls. Flag
  `PG_TOPIC_GATE_SUBQUERY_AWARE` default ON.
- **Hamster loop:** `scripts/dr_benchmark/topic_gate_subquery_harness.py` on the banked drb_72
  `corpus_snapshot` (`--only 50` in <60 s; full 900 rows in single-digit minutes at parallel 32).
  One printed line per row; Fable reads the verdict lines against actual titles; `--refresh-group`
  re-judges only the group under investigation.
- **Bar (Design 1 §4d all seven):** OFF byte-identical, suite green untouched; unit battery
  (label-anchor rejection, precedence, legacy tokens, fail-open, deterministic grouping); drb_72
  behavioral replay — zero sub-query-relevant deletions AND confirmed true junk still deletes with
  disclosure, read line-by-line; determinism at parallel 32; crash-resume identity; zero
  faithfulness diffs; dual gate.
- **Checkpoint boundary:** cp1 in → `topic_gate_verdicts.jsonl` intra → cp2 out.
- **v2 AMENDMENT (operator sharpening 2026-07-10 — Design 1 §6, SELECT+WEIGH v2):** add the
  LINE-LEVEL three-way select/drop reader. §-1.3 reconciliation: credibility is the WEIGHT axis
  (a credible on-topic in-scope source is NEVER dropped — low tier = low weight; `credibility_pass`
  untouched); the ONLY drop triggers are (1) OFF_TOPIC against BOTH anchors (dual-anchor rule),
  (2) OUT_OF_USER_SCOPE — the user's EXPLICIT RunConfig scope (date window / recency / source type /
  peer-reviewed-only / geography / language / author; the user's own hard filter, activation-gated
  on a verbatim trigger span or panel override, never pipeline-initiated), (3) JUNK
  (chrome/nav/cookie/boilerplate). Decided PER LINE: new leaf `retrieval/line_screen.py` reads every
  line of each kept source's widest body and verdicts `KEEP | OFF_TOPIC | OUT_OF_SCOPE | JUNK`; a
  80%-relevant source keeps its 80%; whole-drop stays two-key (line screen + concurring whole-source
  verdict) with the marquee exemption + positive-relevance veto intact. Fail-open on every doubt
  (line KEPT); every drop disclosed VERBATIM (`line_screen_disclosure.json` + Methods counts).
  Reuses the topic gate scaffold, `junk_deletion_gate` partition/disclosure,
  `intake_constraint_extractor`/`scope_facet_classifier`/`constraint_enforcement` for scope, the
  `shell_detector` chrome vocab as line hints. Parallel `PG_LINE_SCREEN_PARALLEL` (slate 32);
  intra-checkpoint `line_screen_verdicts.jsonl`; cp2 unchanged. Bar: Design 1 §6.4 (a)-(e) on the
  real drb_72 corpus, read line-by-line. Faithfulness engine untouched.

### S3 — CONSOLIDATE (Design 6 checkpoint only)
- **Fix:** none to consolidation logic (finding_dedup/credibility_pass/detectors stand as deployed).
  NEW `cp3_basket_snapshot.json` writer at the post-consolidation seam: baskets (members,
  corroboration_count, weights), contradiction pairs — DATA only.
- **Hamster loop:** shared with the checkpoint layer (§5): write → kill → resume-at-cp3 → assert
  basket identity vs the banked run.
- **Bar:** cp3 round-trips byte-identically on the drb_72 bank; verdict-smuggling RED test refuses a
  poisoned cp3; resume at cp3 skips the NLI cross-encoder time and re-runs S4-S7 gates fresh.

### S4 — OUTLINE (Design 5; digest per R2, spec per R1/R8) — FS-completion C2 + C1-structural
- **Fix:** ORCH-1 `outline_digest.py`: basket lines (claim text + corroboration + tier mix + member
  ev_ids) + singleton lines, 100% pool coverage, graceful terse, flag `PG_OUTLINE_BASKET_DIGEST` —
  the planner now reads the semantic equivalent of the paper's `knowledge_base/`, not titles.
  ORCH-2 requirement-aware outline: REQUIREMENTS block from `RunConfig.deliverable` — required
  sections REQUIRED-IF-GROUNDED (undersupplied → disclosed-gap section, never silent drop, never
  fabrication), audience/tone as planning context, scope constraints stated; clinical 8-title path
  byte-identical unless the user explicitly supplies structure. ORCH-3 revise (the paper's section
  RE-OPEN): wave barrier after compose → deterministic per-section `SectionOutcome` digests (the
  section CHECKLIST: verified count, kept fraction, dropped, unused ev_ids, uncovered baskets,
  undersupplied) → ONE reviser call → ops `keep/merge/split/retitle/reassign/add` under
  deterministic apply rules (`keep` = byte-identical reuse; recompose runs the FULL section
  pipeline; invalid ops rejected with reason codes; wholesale-invalid → keep wave-1). Bounds from
  RunConfig: revise_rounds default 1 (hard max 2), max_recompose default 8.
- **Hamster loop:** `scripts/orchestrator_lab/outline_lab.py` on banked run dirs, three modes —
  `plan` (1 LLM call, <1 min), `revise` (1 call, no recompose cost), `apply-dry` (recorded output,
  zero LLM, milliseconds — where apply bugs are hunted). Multiple banked domains concurrent.
- **Bar (Design 5 §9 all nine):** structural validity 3 corpora × 3 runs; menu honesty (100% of rows
  accounted); coverage (every corroboration≥3 cluster assigned or disclosed-orphaned); requirement
  firing IN THE RENDERED report (headings match user structure, order included); revision firing on
  a banked thin-section run with byte-identical `keep` hashes; zero faithfulness diffs; apply-dry
  determinism; §-1.1 line-by-line audit of one full revised report; clinical byte-identity flags-OFF.
- **Checkpoint boundary:** cp3 in → `outline_input/plan` intra → `cp4_outline_snapshot.json` out.

### S5 — COMPOSE (Design 4 + Design 2 + Design 3 consumer 2) — FS-completion C1-prose + C3
- **Fix A (Design 4 — baskets-per-section = the paper's per-section KB subtree):**
  `synthesis/section_basket_map.py` — deterministic basket→section map: candidates from three
  signals (provenance floor = today's intersection rule, sub-query lineage, topical overlap), ONE
  primary home per basket (weighted argmax, keep-first ties), corroborating memberships carry only
  the section-matched facet ev_ids, no-candidate baskets go to ONE residual section —
  `stranded_count == 0` structurally (vs ~600/657 stranded today). Compose: primary view → full
  per-basket treatment exactly once run-wide; corroborating view → facet-scoped multicited
  sentence. Verify pools stay FULL basket-scoped in both roles. D4 per-section merge-refinement NLI
  (pairs ≤~1800, under the 20000 global cap — the drb_72 under-merge recall returns); merges relabel
  GLOBALLY. F1 orphan-router and the recomputed intersection become flag-OFF legacy. Flag
  `PG_SECTION_BASKET_MAP` (+ role policy, refine-NLI, weight knobs — all registry rows).
- **Fix B (Design 2 — holistic review, at R3's seam = the paper's report-level review):**
  `generator/holistic_review.py` — H1 ONE whole-report critique call → bound JSON edit plan with
  verbatim-quote anchoring (unmatched quotes discarded); H2 deterministic structural edits (section
  permutation under back-reference topology; exact-signature consolidation); H3 concurrent
  per-section revise (semaphore 32) on SV sentences with MANDATORY strict_verify re-run per changed
  sentence — fail → original kept. Edit contract: permute / re-verified replace / exact-signature
  consolidate / hedge-clause attach — nothing else. Hard gates R1-R6 (re-verify; zero report-wide
  evidence-id loss; contradictions never adjudicated — hedge + disclose, both sides ship; 80-130%
  word guard + 0.90 keep-floor; fail-conservative snapshot restore; kill-switch
  `PG_HOLISTIC_REVIEW`, slate ON). Consumes `RunConfig.deliverable` when present (R7) — tone judged
  against the SPEC, never a hardcoded register.
- **Fix C (Design 3 consumer 2):** `render_section_style_block(spec, n_sections)` appended by the
  section-prompt selector — audience/tone wording + derived sentence budget when a length ask
  exists (`hard` strictness routes to the existing CONCISE variant); CRITICAL RULES always win;
  brevity compresses sentences, never drops sources.
- **Hamster loops (three, concurrent — no shared state):** `scripts/replay_section_basket_map.py`
  (banked drb_72 baskets+plans, pure code, SECONDS per iteration, full assignment table read
  line-by-line; 30-basket fixture for branch coverage); `scripts/section_harness/
  holistic_review_harness.py` (`--fake-llm` <2 min zero spend / `--live` ≤10 min; per-edit
  ACCEPT/REJECT with reason + before/after diff read line-by-line); the Design 3 Level-2 compose
  replay for the style block.
- **Bar:** Design 4 §7b all eight (stranded==0; one primary home per basket; full treatment exactly
  once + repetition-guard fires ~0; byte-identical map across 3 builds/any worker count/any input
  permutation; faithfulness frozen incl. §-1.1 before/after audit; OFF byte-identity; ≥1 refine
  merge where the global pass skipped; map <5 s, refine <60 s/section) AND Design 2 §3.2 all eleven
  (A1 OFF-hash through A11 behavioral fire in real output) AND the style block's
  faithfulness-neutral proof (Design 3 bar #4).
- **Checkpoint boundary:** cp4 in → `section_basket_map.json` + `section_<idx>_composed.json`
  (plan-hash-keyed) + `holistic_review_input/output.json` intra → cp5 out.

### S6 — VERIFY (wiring only)
- **Fix:** none to the engine. Land ITEM 5a (generator-side cached-draft re-entry consuming
  `reused_outline` + raw drafts — validation/reconstruction exists at
  `run_honest_sweep_r3.py:8740-8790`) so cp5 becomes a real skip point; wire the existing
  `postverify_checkpoint` loader as the cp6 re-entry.
- **Hamster loop / bar:** covered by the checkpoint-layer matrix (§5): resume-at-cp5 skips the
  ~30-40-min generation with zero generator billing for stages ≤5 AND the run_log shows every
  verify/D8 `[activation]` marker recomputed downstream; resume-at-cp6 re-runs only D8+render.

### S7 — ADJUDICATE+RENDER (Design 3 consumers 3+4 + §1 disclosure)
- **Fix:** `_render_bibliography_lines` gains `reference_style` (numeric default byte-identical;
  author-year/APA/Harvard/Vancouver render from REAL captured metadata only — no-author rows fall
  back to title-year WITH a Methods disclosure; never fabricate an author or year; in-text `[N]`
  stays in v1). `assemble_report_md` gains ordering (summary-first / memo shapes /
  recommendations-last) — re-ordering and re-labeling of verbatim-extractive blocks only, zero new
  claim text. Methods gains the "Deliverable requirements" adherence block (every parsed directive
  verbatim + HONORED / PARTIAL(reason) / NOT-GROUNDED) AND the RunConfig disclosure block (every
  non-default knob + value + source layer, §1.3). D8 + redaction untouched.
- **Hamster loop:** Design 3 Level-2 harness renders references+shape from banked corpora per spec
  fixture; every reference line read against real captured metadata.
- **Bar:** Design 3 bars #1, #3, #6 as they apply to render; zero fabricated metadata (spot-read
  line-by-line); render-only re-run path proven (byte-identical prose in → only assembly
  re-executes); RunConfig disclosure present and correct on a run with panel + parsed + env knobs
  all in play.

### S-X — EXCEED: bounded thin-section re-fetch (ruling R10)
- **Fix:** ORCH-3's reviser emits `gap_queries` for thin/undersupplied sections; they route through
  the EXISTING per-query retrieval lane (`per_query_retrieve` — same tier/topic/junk/dedup path as
  every FS sub-query, so new rows are first-class citizens), ONE round between wave-1 and the
  recompose wave, budget `RunConfig.stages.gap_refetch_budget` (spend budget, never a quality
  target). New rows fold into the basket layer as an S3 delta; the section-basket map rebuilds
  (R4); only affected sections recompose. Ships default-OFF; activated WAVE 5.
- **Hamster loop:** `outline_lab.py` gains a `gap` mode — banked thin-section run + recorded gap
  queries → real retrieval of the gap set only → print the new rows + their gate verdicts,
  line-by-line. Minutes.
- **Bar:** on a banked run with a known undersupplied required section: gap queries fire only for
  flagged sections; new rows pass the FULL gate path (proof: topic/junk/dedup markers in the log);
  the recomposed section's new sentences all carry valid provenance; budget bound respected; OFF
  byte-identical; one small real run shows the loop closing a real gap with disclosure in Methods.
- **Checkpoint boundary:** operates inside the cp4→cp5 span; gap rows recorded in an intra-section
  `gap_refetch.json` (queries, rows, verdicts) chained in `checkpoint_index.json`.

---

## 5. CHECKPOINT / RESUME / TRACEABILITY ARCHITECTURE (Design 6, the connective tissue)

**Envelope.** One shared `src/polaris_graph/generator/checkpoint_envelope.py` for all 8 `cpN` files:
`schema_version` pin, `stage`, question SHA (GATE0 identity), `upstream {name, sha256}` hash-chain,
`flag_slate` + `run_config_sha` (resume refuses on drift), `adjustments_applied`, DATA-only payload
with the RECURSIVE forbidden-verdict-key guard extended to every checkpoint. Atomic writes (temp +
`os.replace`), sorted-keys deterministic bytes. Best-effort write (never abort a paid run),
fail-loud read (corrupt/mismatched never silently loads). cp1/cp2/cp5/cp6 migrate ADDITIVELY (old
snapshots still load via a legacy branch).

**Traceability ledger.** `checkpoint_index.json` per run_dir: append-ordered
`{stage, file, sha256, created_utc, upstream_sha}` covering section checkpoints AND intra-section
files (R6). Hash-chain validation = walk the list; the forensic monitor and the resume resolver
read ONLY this file to know where a run died and what is trustworthy.

**Resume contract — load N, adjust DOWNSTREAM only, re-run N+1..7.**
`run_gate_b.py --resume [--resume-from cpN] [--adjust adjustments.yaml] [--run-config file]`.
Default = nearest checkpoint (the existing later-wins rule generalized over the 8-chain). The
adjustment spec is a RunConfig DELTA in the SAME vocabulary S0 produces on a fresh run (§1.4) — the
operator can say "resume drb_72 from the outline step, tone executive-brief, cap 3000 words" and
the S0 extractor parses it; the panel can write the same delta. Validity matrix enforced fail-loud
via each knob's `earliest_resume_checkpoint` registry field: deliverable adjustments valid from
cp3+; scope adjustments from cp1; breadth adjustments only at cp0; question change = new run (GATE0
blocks). An adjustment can NEVER mutate a loaded checkpoint's payload — it only reconfigures the
stages that re-run. Supersede-never-delete: later checkpoints + old terminals move to
`run_dir/superseded/<utc>/`, recorded in the index. Resume event stamped into manifest + Methods
(entry checkpoint, adjustment digest, lineage pointer) — disclosed, never silent. Every resumed
stage re-runs EVERY faithfulness gate from data; a crash mid-resume is just another crash (next
`--resume` lands on the new nearest point).

**Isolation dividend.** Each section can be swapped, re-baked, or bake-off'd alone by feeding it a
banked upstream checkpoint and diffing its output checkpoint — this is what makes every hamster
loop in §4 cheap, and it is why the envelope + RunConfig build FIRST (§7 wave 0).

**Layer's own loop + bar (Design 6 §7):** `scripts/checkpoint_resume_harness.py` — concurrent
kill/resume matrix over every cpN × adjustment class on the banked drb_72 run_dir (truncate-copy,
resolve, assert selection + chain validation + tamper refusal + validity rejection; cheap stages
actually re-run and byte-diff). Bar: all eight of Design 6 §7b — matrix green; upstream-skip proven
in the cost ledger; gate re-run markers present; verdict-smuggling RED; adjustment-scoping proof
(cp4 tone change leaves cp1-cp3 sha256s untouched); determinism; §-1.1 audit of one resumed report;
fresh-vs-cp2-resumed parity of verified-claim sets.

---

## 6. LOCKED CONFIG (operator-locked; slate + registry are the source of truth)

| Setting | Value | Where |
|---|---|---|
| Fetch workers | `PG_BYPASS_MAX_INFLIGHT=14` (band 14-16, operator-locked; history 48→16→20→14) — **AS BUILT, commit `67e57837`** | LOCKED S1.a |
| Paid-tail retry | as built in commit `91045104` (Zyte breaker-bypass + Archive.org on fetch_failed); lock record `3c911533` | LOCKED S1.a |
| Breadth classes | `config/settings/breadth_classes.yaml` — NARROW `{15,20,120}` / STANDARD `{35,60,300}` / WIDE `{80,100,740}` starting rows, all registry knobs, user-overridable per §1.3; abs env ceilings generous | S1.b |
| Scope lanes | `PG_SCOPE_TO_QGEN`, `PG_SERPER_SCOPE_FILTER`, `PG_S2_SCOPE_FILTER`, `PG_OPENALEX_SCOPE_FILTER` — additive, fail-open, slate ON after S1.b bar | S1.b |
| Topic gate | `PG_TOPIC_GATE_SUBQUERY_AWARE=1` (default ON), `PG_SCOPE_TOPIC_PARALLEL=32`, `PG_TOPIC_SUBQ_MIN_TOKENS=3` | S2 |
| Line screen (v2) | `PG_LINE_SCREEN=1` after §6.4 bar (kill-switch OFF = byte-identical), `PG_LINE_SCREEN_PARALLEL=32`, `PG_LINE_SCREEN_MAX_LINES_PER_CALL=120`, `PG_LINE_SCREEN_SCOPE` auto-inert without explicit RunConfig scope | S2 |
| Deliverable spec | `PG_DELIVERABLE_SPEC=1` (slate; default OFF), `PG_DELIVERABLE_SPEC_LLM=1`, `PG_DELIVERABLE_RENDER=1` | S0/S7 |
| Outline | `PG_OUTLINE_BASKET_DIGEST=1`, `PG_OUTLINE_DIGEST_MAX_CHARS=60000`, `PG_OUTLINE_REVISE=1`, revise_rounds=1 (hard max 2), max_recompose=8 | S4 |
| Gap re-fetch | `gap_refetch_budget` default 0 (OFF) until WAVE-5 activation; then slate 4 | S-X |
| Section-basket map | `PG_SECTION_BASKET_MAP=1`, `PG_SECTION_BASKET_MAP_REFINE_NLI=1`, role policy `facet`, weights w_p=3/w_q=2/w_t=1 | S5 |
| Holistic review | `PG_HOLISTIC_REVIEW=1` (slate; default OFF), revise concurrency 32, word guard 80-130%, keep-floor 0.90, critique/revise max_tokens 16384/8192 | S5 |
| Section compose concurrency | `PG_MAX_PARALLEL_SECTIONS` / `PG_PARALLEL_SECTIONS` raised 6→32 (registry knob; provider-rate permitting) | S5 |
| Models | §9.1.8 lock verbatim — NOT RunConfig knobs; no per-leg model knobs; max_tokens = real provider caps | all |
| Slate discipline | force-exact frozenset pattern (`run_gate_b.py:1509-1527`) extended to the RunConfig override file (R9) so a stray env or panel value cannot silently downgrade a paid benchmark run | all |

Max-parallelism posture: queries parallelize as independent run_dirs/processes with independent
checkpoint chains on the 128-core box; intra-section LLM stages run at their 32-band knobs; fetch
is the ONE deliberately low number (14, locked) — the paid tail is the recovery lane, not a
throttle.

---

## 7. SEQUENCING — waves, dependencies, concurrency

Dependency spine: envelope + RunConfig registry/resolver → everything; S0 extractors → S1.b sizing
/ S4 ORCH-2 / S5 style block / S7 render / --adjust vocabulary (soft for Design 2 per R7); S4
digest → S4 revise → S-X; map rebuild rule R4 ties S4↔S5; panel needs the stable registry.
Everything else is independent. Each work package = its own GitHub Issue (§-1.2: issue FIRST, grep
adjacent files, offline smoke, then Codex brief), its own PR(s), dual-gated. A wave-1 package never
blocks on another wave-1 package; within a package, its own hamster loop runs to its bar BEFORE the
dual gate; NO package merges without its design doc's full acceptance list green; force-APPROVE
only per §8.3.1 at iter-5 with residuals filed as Issues.

**WAVE 0 — foundation (both packages concurrent).**
- WP-0a: `checkpoint_envelope.py` + `checkpoint_index.json` + additive cp1/cp2 migration (Design 6
  build 1).
- WP-0b: RunConfig core — `run_config.py` + `config/settings/run_config_knobs.yaml` registry +
  resolver + `--run-config` CLI intake + cp0 writer skeleton (§1). Empty-RunConfig byte-identity is
  this package's bar.
- (v1's WP-0b LOCKED fetch is DONE — commits `67e57837`/`91045104`/`3c911533`. Removed from the
  build queue.)

**WAVE 1 — independent section fixes (all five concurrent; no shared files).**
- WP-1a: S2 sub-query-aware topic judge, PR-1 core + PR-2 parallel/checkpoint/harness (Design 1),
  then PR-3 line-screen core + PR-4 scope leg/throughput/harness (Design 1 §6 SELECT+WEIGH v2 —
  operator sharpening 2026-07-10; PR-3/PR-4 depend on PR-1's anchor accessors, same package).
- WP-1b: S0 deliverable-spec extractor + breadth-directive parse + scope-gate seam + cp0 population
  + provenance (Design 3 PRs 1-2 + Design 7 D1 parse side) — unblocks four downstream consumers.
- WP-1c: S5 `holistic_review.py` module + fake-LLM unit battery + harness (Design 2 PRs 1+3 module
  part; wiring deferred to wave 3). Uses R7 — no wait on WP-1b.
- WP-1d: S5 `section_basket_map.py` module + fixture + replay harness (Design 4 WP1).
- WP-1e: S1.b `breadth_resolver.py` + `breadth_classes.yaml` + spine wiring + search-only probe
  harness (Design 7 D1 sizing side; reads RunConfig from WP-0b).

**WAVE 2 — outline + compose + scope-lane consumption (starts as wave-1 inputs land).**
- WP-2a: S4 `outline_digest.py` + `finding_clusters` threading (Design 5 build 1; R2).
- WP-2b: S4 ORCH-2 requirement block (needs WP-1b) + cp3/cp4 checkpoints (Design 6 build 3,
  Design 5 build 3).
- WP-2c: S5 compose wiring of the basket map — fast path, role policy, F1 absorb, per-section
  composed checkpoints (Design 4 WP2+WP5).
- WP-2d: S5 style block + section-prompt selector threading (Design 3 PR-3; needs WP-1b).
- WP-2e: S5 D4 per-section merge refinement (Design 4 WP4).
- WP-2f: S1.b scope → qgen prompts + author lane (Design 7 D2; needs WP-1b) and scope → backend
  filters, three additive lanes (Design 7 D3; independent of D2, can split into its own PR).

**WAVE 3 — the loops that span sections (sequential-ish; each depends on wave 2).**
- WP-3a: S4 ORCH-3 revise (outcome digests = section checklists, reviser call, deterministic apply,
  recompose wave, map rebuild per R4) + `outline_lab.py` (Design 5 builds 4-5).
- WP-3b: S5 holistic-review wiring at the `:10633` seam + sweep threading + slate pin + A7/A11 live
  evidence (Design 2 PRs 2-3 remainder).
- WP-3c: S6/S5 re-entry — ITEM 5a generator hook + cp6 loader wiring (Design 6 build 4).
- WP-3d: S7 render — reference style + assembler ordering + Methods adherence block + RunConfig
  disclosure block + Level-1/2 harness (Design 3 PR-4 + §1.3).
- WP-3e: S-X thin-section re-fetch loop — build, default-OFF, `gap` lab mode (R10; needs WP-3a).

**WAVE 4 — the connective layer + the panel + full assembly.**
- WP-4a: `--resume-from` + `--adjust` (RunConfig-delta vocabulary) + validity matrix from registry
  + supersession + manifest disclosure (Design 6 build 5) + `checkpoint_resume_harness.py`
  (build 6).
- WP-4b: CONTROL PANEL (pipeline B/web, R12): registry-driven knob UI (breadth / scope /
  deliverable / stages groups) → writes RunConfig overrides → same backend contract. PRs under
  `web/**` carry the 6th artifact (`codex_visual_audit.txt`). The backend is already
  user-adjustable without it (prompt + CLI + env) — the panel is the second surface.
- WP-4c: FULL-PIPELINE ASSEMBLY — all slate pins ON together (S-X still OFF); the kill/resume
  matrix across the 8-chain; then ONE small real run read forensically line-by-line (fetch yield
  first number every tick); then the paid full run; then the §-1.1 before/after report audit vs the
  pre-campaign baseline.

**WAVE 5 — EXCEED activation + proof.**
- WP-5a: activate S-X (`gap_refetch_budget` slate 4) after WAVE-4's bar holds; one small real run
  with a deliberately thin-section question; §-1.1 read of the gap-fetched rows and the recomposed
  section; then the loop rides the full benchmark runs.

---

## 8. DEFINITION OF DONE (the campaign, not a package)

1. Every §4 section bar green — INCLUDING the §1.6 RunConfig conformance items — every package
   dual-gate APPROVED, all slate pins landed. S1.a stays untouched (git log proof: no commits under
   the locked fetch paths after `3c911533` except registry rows).
2. The FS-completion proof: C1 (holistic review + revise re-open), C2 (digest-fed outline), C3
   (section baskets + outcome checklists) all behaviorally firing in ONE real run's artifacts, and
   X1 (thin-section re-fetch) closing a real gap on the WAVE-5 run — the paper's loop, complete,
   plus the move it cannot make.
3. Full-adjustability proof: one real run where breadth ("run 60 queries"), scope ("EU sources
   2019-2024 only, peer-reviewed"), and deliverable ("executive memo, Harvard references, summary
   first, ~2000 words") are ALL set in the PROMPT and honored end-to-end (§-1.1
   directive-by-directive read); the SAME asks set via the PANEL/override file produce the same
   honoring; panel-beats-parsed demonstrated on one knob. Methods disclosing every knob + source.
4. The wave-4 kill/resume matrix green across all 8 checkpoints including one adjusted resume
   (cp4 + tone adjustment) with upstream sha256s untouched.
5. One small real run, then one paid full run, forensically monitored (fetch yield N-of-M first,
   every line read), with: zero sub-query-relevant deletions; stranded baskets 0; repetition-guard
   fires ~0; holistic review liveness marker honest; requested-structure headings honored in
   `report.md`; scoped search lanes fired with union proof; Methods carries adherence + deletion +
   resume + RunConfig disclosures.
6. §-1.1 line-by-line before/after audit of the full report vs the pre-campaign baseline: zero new
   UNSUPPORTED/FABRICATED, faithfulness engine byte-untouched (`git diff` proof on the frozen
   paths).
7. Residual risks stay OPEN as Issues (corroborating-role under-render A/B; author-metadata capture
   for full in-text author-year v2; panel UX depth beyond the registry-driven v1) — filed, not
   silently absorbed.
