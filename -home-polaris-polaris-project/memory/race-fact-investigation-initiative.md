---
name: race-fact-investigation-initiative
description: 4-phase grounded 3-model investigation to map proven fixes to every RACE+FACT sub-item; key findings + the codex-drives-kimi rig
metadata: 
  node_type: memory
  type: project
  originSessionId: 21e87760-8436-4090-870d-99ef2121882e
---

Initiative (2026-07-23): a **grounded, line-by-line, no-guessing** 4-phase investigation to map a
true/generalized/small-test-proven fix to **every scored sub-item of RACE and FACT**. Plan + docs live in
repo `docs/race_fact_initiative/` (branch `fix/race-batch1-evidence-substrate`). Tasks #36-#40.

**Operating model** — each phase = one cycle: Opus writes a deep brief → **3 models investigate
independently in GOAL mode** (max reasoning, web+code, every claim tied to a cited line) → each returns a
verdict+plan → **Opus consolidates** (re-reads all 3 line-by-line) → operator signs off → next phase.
Phases: P0 infra → P1 SCORING_SPEC (RACE+FACT line-by-line) → P2 COMPETITOR_TEARDOWN (top-10) →
P3 PIPELINE_GAP_AUDIT (our gaps+fix+test) → P4 EXECUTION_CHARTER + MASTER_ACTION_PLAN (sign-off gate). NO
pipeline code until MASTER_ACTION_PLAN approved.

**STATUS 2026-07-23: ALL 4 PHASES COMPLETE** (panel = Sol + Fable; K3 dropped, Moonshot 429-throttled).
Deliverables committed+pushed in docs/race_fact_initiative/ (commit 155e60c0): SCORING_SPEC.md,
COMPETITOR_TEARDOWN.md, PIPELINE_GAP_AUDIT.md (14 unified gaps U1-U14), **MASTER_ACTION_PLAN.md** + all
raw phase1-4 sol/fable verdicts. Every receipt was verified against ground truth each phase.

**The plan both models converged on:** ONE pre-generation `AnalyticalContract` (AC) — built from question +
admitted evidence, consumed by the ACTIVE producer `_compose_section_per_basket` (NOT `_call_section`, the else
branch — a prompt addendum routed only there misses the producer = the proven cause of the measured-flat levers),
audited SEMANTICALLY (proposition entails obligation, NOT section-nonempty; and NOT an NLI model — R2 bans new
entailment machinery per [[no-entailment-ever-rule]]). Champion = mf_baseline 0.5009 (all levers OFF but
PG_RENDER_BLOCKS), the ONLY valid comparator. Critical path U3→U4/U6→U7. 5-rule charter (generalization gate w/
held-out tasks 91+100+{73|51|4}; faithfulness firewall + U1 zero-new-factual-token canary + layout-only render
exception; deterministic-then-3v3-paired measurement gate; shared-contract rule; no-regression gate).

**WAVE-1 GATE CLEARED — operator decisions RESOLVED 2026-07-23 → BUILDING (task #41):**
- OQ-0 first-ship = **Fable proven-winner-first**. Order W1(U1+U12-lite+U14b, AC carrier=definition-of-done) →
  W2(U3+U4+U6) → W3(U5+U11+U14a) → W4(U2+U8+U10) → W5(U7-full+U9+U13+U12-full). Sol's governance-first order is
  the FALLBACK if W1 measures flat despite green deterministic gates.
- OQ-4 licensed-inference doctrine = **APPROVED** (paragraph-closing inference: zero new factual token/number/
  entity, union-of-paragraph-markers, enforced by the C2 canary; the single doctrine change).
- OQ-1 held-out set = **91 + 100 + 73** (91 inventory .11 Insight = mandatory NO-FIRE conditionality test;
  100 analytical .40; 73 Read .25 stressor). Every fix's deterministic test must pass on 72 + these 3.
- OQ-5 budget = **Wave 1 only for now** (~6 gens = 3v3 paired vs mf_baseline); rest decided after W1 result.
- Deferred: OQ-2 (before W2), OQ-3/7 (before W3), OQ-6/8/9/10/11/12 (in flight).
Discipline: design gated by Sol max-reasoning before code ([[codex-sol-max-reasoning]]); faithfulness engine
untouched ([[no-post-generation-fix-rule]], [[no-entailment-ever-rule]]); build-all-then-measure
([[build-all-then-measure-rule]]); consult on judgment calls ([[investigate-then-consult]],
[[two-way-iteration-rule]]).

**ARCHITECTURE CORRECTION (Sol Wave-1 design-gate, verified in code 2026-07-23) — matters for EVERY wave:**
The ACTIVE section writer is **`abstractive_writer._call_writer`** (system prompt `_WRITER_SYSTEM_GROUP`
abstractive_writer.py:431/:540), invoked via **`abstractive_pre_pass`** (:773), obtained in
`multi_section_generator._run_section` at :6545-6547 and passed as `writer_fn` INTO
`verified_compose._compose_section_per_basket` (which assembles/verifies DOWNSTREAM, per basket). So the audit's
"consume at _compose_section_per_basket" is necessary-but-NOT-sufficient: writer INSTRUCTIONS (U1 inference, U14b)
must reach `abstractive_pre_pass`/`_call_writer`, else they only hit the FALLBACK writer
(`SECTION_SYSTEM_PROMPT_TEMPLATE` in multi_section_generator, selected at ~:4168). CRITICAL for champion
preservation: `_SECTION_COMPOSITION_RULES` is UNCONDITIONALLY concatenated into that template at :3612-3615, so
appending Wave-1 text there changes the writer prompt EVEN WHEN THE SWITCH IS OFF. => Every Wave-1 behavior must
sit behind ONE call-time predicate `wave_active = (switch_enabled AND ac is not None AND not ac.is_empty)`, as a
gated prompt SUFFIX at the writer call site, never a module-template append. Sol Wave-1 gate = NO-GO (14 required
spec changes): pre-producer typed LicensedInference admission (premise claim IDs + marker UNION + reasoning-
operator enum) BEFORE the writer, canary = lexical/surface closure only (NOT semantic entailment) + new pure
fail-closed inventory helper composing evidence_value_extractor/claim_atom_extractor/verified_compose helpers
(engine untouched); U1 count-free (closing move, no "3+ sentences" magic count); ORDERED non-whitespace token
equality for layout (not multiset), Markdown-context-aware ATX-only normalizer at FINAL-render seam
(compose_agentic_report_s3gear329.py:724-746), gated; preamble OMISSION gated not deleted; repeated-Limitations =
pre-gen writer rule + NO-GO lint not post-gen delete; semantic naming PG_ANALYTICAL_CONTRACT/build_analytical_
contract (no version/adjective names, CLAUDE.md:290-295). Sol staging: (1) carrier/off-path purity FIRST no prose
change → (2) premise-owned inference planning → (3) active consumption via abstractive_pre_pass/_call_writer → (4)
post-compose fail-closed audit → (5) U12-lite separately gated at final render → (6) U14b last/separate arm.
Verdict at scratchpad/investigators/wave1_solgate_verdict.md (457 lines). Revising spec → re-gate before code.

**GATE ROUNDS + DECISIVE DISCOVERY (2026-07-23, 3 NO-GOs, then paused for operator):** Sol v1 NO-GO (active writer
= abstractive_writer not compose seam); v2 NO-GO (8/14 pass); v3 NO-GO (subset-check permits a DIFFERENT proposition
from same premise words → must bind emitted==admitted candidate exactly, ordered tokens/markers; operator license
matrix "launders" relations; dark authored routes: sentence_repair :6821-6858, fact_dedup :12533-12720, REDUCE
branch of _call_section :4057-4154, AND a SEPARATE report architecture — contract-section narrative via
_m63_narrative_llm_call / contract_section_runner.py / slot_fill.py). **THE FORK (operator decision pending):** there
are TWO writer architectures + TWO harnesses. (1) LEGACY abstractive path (_run_section→abstractive_pre_pass→
_call_writer→_compose_section_per_basket): used when PG_V30_PHASE2_ENABLED=0 (DEFAULT). The CHAMPION mf_baseline
0.5009 was generated on THIS path (run_race_max_focus.sh→run_k3.sh→run_raw_a.sh→compose_agentic_report; none set
V30). (2) V30 CONTRACT-SECTION/SLOT path (contract_section_runner.py build_slot_narrative_prompt / slot_fill.py):
scripts/dr_benchmark/run_gate_b.py:5746 FORCE-sets PG_V30_PHASE2_ENABLED=1, and its code self-describes as "THE
PRIMARY LIVE BENCHMARK PATH". So all Phase-3 audit + 4 gate rounds targeted the LEGACY path; if the canonical
scoreboard is Gate-B (V30 on), the real active writer is the slot/contract path and Wave-1 transport must retarget
there + re-baseline. MUST consult operator: which harness is the scoreboard we optimize — V30-off compose (mf_baseline
as-generated) or V30-on Gate-B? This gates the whole build. Loop PAUSED (no v4 gate) pending answer.

**OPERATOR DECISION 2026-07-23: canonical scoreboard = GATE-B / V30-ON (slot path).** => (1) mf_baseline 0.5009 is
INVALID as champion (V30-off); MUST RE-BASELINE under V30-on (Gate-B) before any Wave-1 measurement — real champion
number currently unknown; possible seed outputs/full_scale_v30_phase2_run14. (2) Active writer = the V30 NARRATIVE
stream: slot_fill.build_slot_narrative_prompt (:703, _SYSTEM_PROMPT :207) driven by
contract_section_runner.run_contract_section (:1627), per-sentence verified (rescue-ineligible), concatenated to
verified_text; NOT abstractive_writer/_compose_section_per_basket (that's the legacy V30-off path). (3) The 4 Sol gate
rounds' CHARTER (C1-C5), pre-producer canary doctrine, exact emitted==admitted-candidate binding, ordered-token
layout, complete-route coverage, OFF-path identity, semantic naming, 6-stage staging ALL CARRY OVER — only the
transport TARGET moves to the slot writer. (4) Phase-3 PIPELINE_GAP_AUDIT needs a V30 re-map (its "_compose_section_
per_basket" seam is legacy). NEXT: Sol line-by-line investigation of the V30 slot writer → retargeted Wave-1 seam map
→ spec v4 → re-gate → build Stage 1. Re-baseline run is a prerequisite (needs generation budget; OQ-5 "Wave-1 only ~6
gens" was for the legacy path — may need re-confirm).

**V30-RETARGET INVESTIGATION LANDED + LINEAGE DECISION (2026-07-24, wave1_v30_retarget_verdict.md 711 ln):**
Findings: (1) V30 report is HYBRID — contract-slot sections PLUS retained legacy-enrichment sections
(multi_section_generator.py:11467-11489); Wave 1 must cover BOTH. (2) There are ~27 authored/rewrite routes that can
reach the judged report (Sol §1.5) — narrative gen, regulatory synth (2-4 sent), deterministic slot prose, A1
fallback, fragment-snap, sibling re-anchor, consolidations, inline regroup, legacy enrichment, M-44/M-47 regen,
fact-dedup rewrite, repetition guard, global remap, atom replacement, framing/Abstract/Conclusion, suppressors,
summary-table, post-write redaction/disclosure/final-repetition. (3) The real judged string is the FINAL ON-DISK
report.md assembled in run_honest_sweep_r3.py (NOT compose_agentic_report_s3gear329.py — that's the legacy compose
script, not the Gate-B driver). (4) U1 still real (V30 narrative also forbids inference); U12 preamble MOOT on
Gate-B path (V30 owns headings+one Limitations; remaining=final-render layout+single-Limitations); U14b mostly moot
on normal narrative (directive exists) — gap=route completion+audit. (5) BLOCKER SURFACED: question/scorer lineage
mismatch — Gate-B force-answers DRB-II idx-56 (GenAI) but score_report_race.py packs legacy task-72 (4IR); can't
mix; DRB-II gold file MISSING from checkout. **OPERATOR DECISION 2026-07-24: canonical = TASK-72 (4IR) question +
V30 writer** => run V30 sweep on task-72 WITHOUT Gate-B's idx-56 override; score score_report_race --task-id 72;
re-baseline = V30-on + task-72 + AC-off (all Phase 1-4 analysis stays valid; no gold file needed). NEXT: determine
exact V30+task-72 (no idx-56 override) generation recipe; write spec v4 (V30 hybrid writer, Sol stage map §Retargeted
Wave-1 stage map, all carried-over charter/canary/exact-binding/complete-route rules); Sol re-gate v4; then
re-baseline (needs budget go) + build Stage 1. Phase-3 audit's "_compose_section_per_basket = sole producer"
premise REPLACED by the V30 hybrid dispatch.

**ROLLBACK + PHASE-4 RE-RUN (operator-directed 2026-07-24) — THE KEY COURSE CORRECTION:** The operator caught that
the Wave-1 build (Sol-SOLO gates v1-v4) had drifted into the HARD-BANNED faith-ghost apparatus: runtime
LicensedInference ADMISSION CANARY + OPERATOR_LICENSE ENTAILMENT predicate + exact emitted==admitted binding across
~27 routes + non-scoreable-on-mismatch suppression = [[no-entailment-ever-rule]] + [[no-post-generation-fix-rule]]
violation. ROOT CAUSE: (a) seed entered Phase-4 C2 (Sol's "admission canary + permitted reasoning operator" language
that I consolidated ALONGSIDE and CONTRADICTING Fable's own "no entailment/NLI machinery" rule — my consolidation
error); (b) I ran the Wave-1 BUILD gate SOLO-SOL, dropping Fable, so nobody invoked the charter's own no-ghost rule
for 5 rounds. LESSON: Phase 1-3 + Fable's charter half were CLEAN (generalized, no overfit, pre-gen prompt + a TEST);
never run a single-model build gate; hold the ghost bans over Sol's correctness-maximizing. ACTION: roll back to clean
Phase 3; committed rollback (bdeceb75) — MASTER_ACTION_PLAN §12 + C2 VOID flag; discard Wave-1 specs v1-v4/Stage-1 +
all AnalyticalContract/canary/binding apparatus; KEEP the valid V30/task-72 facts (phase4_v30_retarget_verdict.md).
RE-RAN PHASE 4 CLEAN with BOTH Fable+Sol (phase4_rerun_brief.md, HARD NO-GHOST mandate: pre-gen prompt/scope only,
existing engine untouched, deterministic checks are TESTS not runtime gates, drop-lever-if-not-clean, measure-first vs
V30-on/task-72 baseline). Outputs -> phase4b_sol_verdict.md + phase4b_fable_verdict.md (Fable agent a39804860cba87a5a).
U1 clean form = pre-gen narrative-prompt change permitting one paragraph-closing synthesis sentence, verified by the
EXISTING per-sentence verifier, TEST=paragraph_deduction_rate+zero-new-number; if stripped/flat -> DROP. NEXT: verify
both receipts -> lossless consolidate the CLEAN Phase-4 -> operator sign-off -> Stage-0 lineage seam + re-baseline ->
build smallest lever, both-gated.

**The 3-model panel (no Kimi account needed):** Sol = Codex CLI (gpt-5.6-sol, max). K3 = **Codex CLI driving
OpenRouter `moonshotai/kimi-k3`** — PROVEN working: `codex exec -c model_providers.openrouter.base_url=
"https://openrouter.ai/api/v1" -c model_providers.openrouter.env_key=OPENROUTER_API_KEY -c
model_provider=openrouter -c model=moonshotai/kimi-k3`. Fable = Claude Agent(model:fable). Opus consolidates.
Codex goals feature is live (~/.codex/goals_1.sqlite). "Fix Kimi Retry" = harden that codex-drives-k3 path.

**Grounded findings so far (to re-verify in the phases):**
- RACE ≈ Insight .32 / Comprehensiveness .29 / IF .25 / Readability .14 (task-72; weights are DYNAMIC per task).
- RACE **strips citations before judging** (clean_prompt.py) → FACT ≠ RACE; ~90% faithfulness buys 0 RACE points. See [[no-post-generation-fix-rule]].
- Compose-side levers measured FLAT: 3 arms indistinguishable (max 0.4933 / full 0.4966 / baseline 0.5009, all within ±0.014 noise, tonight's judge). The gap to leaders (~0.58) is **Insight**, which lives in the writer's reasoning + pre-gen structuring — NOT post-hoc passes (proven to regress 16-27%).
- **Judge drift**: tonight's gpt-5.5 judge scored a stored champion report 0.4718 (vs ~0.508 historical) → only WITHIN-judge comparisons valid; leaderboard/historical numbers NOT comparable; "beat everyone" not defensible tonight.
- Readability decomposes into 7 sub-criteria (task-72 criteria.jsonl): L1 prose .2, S1 structure/roadmap .2, S2 paragraph cohesion .15, P1 synthesis clarity .15, D1 data-as-tables .1, F1 formatting .1, A1 term-defs .1. Tables/formatting = only D1+F1 = 20%; our reports have 615-word wall-of-text paragraphs (worst loss) + no tables + weak roadmap.
- RACE noise floor: ±0.027 draw-to-draw on Readability; baseline_triple says gain is real only if replicated mean clears ~+0.014. Fix the measurement harness to always run a same-judge baseline + enough draws.

**INGESTION PROTOCOL (mandatory, every phase, both Sol+Fable):** before each phase, each investigator must
read EVERY line of EVERY prior-phase artifact (each phase's consolidated plan + Sol verdict + Fable verdict,
in docs/race_fact_initiative/) and emit an INGESTION RECEIPT at the top of its verdict — per file: line count +
verbatim FIRST/MID/LAST line. Opus VERIFIES each receipt against the real files; mismatch/missing => reject +
re-run. No skimming. Also: Opus's own consolidation must be LOSSLESS (read every line of both verdicts, preserve
every point, [S]/[F] attributed) — the operator caught Opus compressing/skipping Fable twice; that is the failure
mode to avoid. Snippet at scratchpad/investigators/INGESTION_PROTOCOL.md, prepended to every phase brief.
