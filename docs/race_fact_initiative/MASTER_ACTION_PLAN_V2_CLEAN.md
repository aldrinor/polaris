# MASTER_ACTION_PLAN v2 — CLEAN (no-ghost) — LOSSLESS consolidation of Sol + Fable (Phase-4 re-run)

Provenance: both phase4b verdicts read line-by-line by Opus; both ingestion receipts VERIFIED vs ground truth
(all 10 artifacts, exact line counts + FIRST/MID/LAST). Both verdicts GHOST-AUDITED CLEAN (every banned-pattern
hit is a rejection). Attribution: **[S]** Sol, **[F]** Fable, **[S+F]** both. Supersedes the drifted Phase-4
(MASTER_ACTION_PLAN.md §12 rollback). Governed by `GHOST_BAN.md`. Design-only — no code until operator sign-off.

Inputs: `PIPELINE_GAP_AUDIT.md` (14 clean Phase-3 gaps), `phase4_v30_retarget_verdict.md` (V30 architecture map),
`phase4b_sol_verdict.md` (475), `phase4b_fable_verdict.md` (235).

---

## 0. WHAT BOTH MODELS AGREE ON (the clean spine)

1. **No shared runtime carrier / no apparatus.** [S+F] Both REJECT, by name and under renaming: `AnalyticalContract`
   carrier, `LicensedInference`, `OPERATOR_LICENSE`/entailment predicate, `PremiseRelation`/premise IDs, runtime
   before/after canaries, emitted==admitted binding audits, non-scoreable/suppression states, any NLI layer around
   `strict_verify`, post-gen citation-splitting/rewriting/residual-deletion/rerouting. Every lever is the SIMPLEST
   per-seam **pre-generation prompt / outline-focus / scope change** reaching the active writer.
2. **Existing engine untouched.** [S+F] `provenance_generator.py` + `clinical_generator/strict_verify.py` never
   imported/modified. Verifier-strip is lawful: better upstream evidence or DROP the lever — never rescue/relax.
3. **Deterministic checks are TESTS, not gates.** [S+F] Offline scripts on emitted reports/plans that decide
   whether a lever SHIPS; nothing in the generation call path reads their result.
4. **Measure-first.** [S+F] mf_baseline 0.5009 is INVALID (V30-off). Establish the V30-on/task-72/levers-off
   baseline via Stage-0 BEFORE any lever; re-anchor every Phase-3 "before-number" on it.
5. **U1 is the first lever, alone** (Fable pairs U12-lite as a Read-hedge rider). Same clean form both sides.
6. **Critical score-weighted path: U3 → U4 → U7** (Insight #8 0.0800 + Comp #3 0.0725-share + Insight #10 0.0640).
7. **Two-model + ghost-audit on every build diff** (never solo again).

---

## 1. EXECUTION_CHARTER (clean) — [S A1-A6] + [F C1-C5]
- **Generalization gate.** No task/domain literals, magic counts, entity lists, or adjective/version flag names;
  fixed role/type/status vocabularies OK; held-out **91/100/73** mandatory (task-91 must prove NO-FIRE for
  analytical-only behaviors). Test fixtures may hold exact expected data.
- **Faithfulness rule (the clean replacement for the VOID C2).** Pre-generation only; existing engine untouched;
  NO ghost apparatus (the enumerated ban above); **drop-lever if not clean**; verifier-strip is lawful.
- **Measurement gate.** Deterministic test at the emitted-report seam FIRST; then ≥3v3 paired vs the Stage-0
  V30-on/task-72 baseline, paired-mean per-dimension, target dim > +0.027, any dim ≤ −0.027 = no-go, FACT
  non-inferior, same pinned judge/frozen corpus, no single-draw decisions, flat-lever ships only as a proven
  dependency.
- **No-regression + stop.** Ship only when BOTH reviewers approve the clean architecture, the output test passes,
  the paired mean clears +0.027, no dim regresses, FACT non-inferior. Else revert + one clean prompt/scope
  correction or DROP. No apparatus to rescue a lever.
- **Reviewer ghost-audit (run on every diff)** [S+F, both wrote it independently]: grep the diff for
  `admission|canary|entail|nli|licens|binding|premise|operator[_ -]?licen|non[_ -]?scoreable|suppress|fail[_ -]?closed|admitted|emitted[_ =]|analyticalcontract`
  — any proposing hit in `src/`|`scripts/run_honest_sweep_r3.py`|`scripts/dr_benchmark/` = REJECT; plus 5 structural
  checks (no emitted-vs-stored compare; no content-dropping predicate between producer and render except the
  token-identity layout normalizer; no engine import; deterministic checks live under tests/; no dataclass with
  premise-IDs/admitted-tokens/marker-bindings/reasoning-operators). (Now `docs/race_fact_initiative/GHOST_BAN.md`.)

---

## 2. PER-GAP DISPOSITION (14 Phase-3 gaps on the V30 hybrid writer)

Legend: **KEEP** = clean pre-gen change survives; **DROP** = cannot be done cleanly pre-gen (or ghost-only/moot).

| gap | disposition | simplest clean pre-gen change (file:line) | deterministic TEST (ship decision) |
|---|---|---|---|
| **U1** mechanisms/synthesis (Insight #7+#8 .0800×2) | **KEEP — FIRST** [S+F] | permit ONE paragraph-closing synthesis sentence in BOTH streams: V30 narrative (`slot_fill.py:703-786` + `PG_NARRATIVE_PROSE_SYSTEM_MESSAGE` `multi_section_generator.py:796-807` + ceiling `:685-700`) and legacy twin (`:3517-3519` + retry `:4420-4432`). §4 below. | paragraph_deduction_rate 0.16→>0.6 (re-anchor); zero-new-number ⊆; verifier-survival <50%⇒DROP; 91/100/73; off-state byte identity |
| **U2 (+U8)** framework spine + designated-concept reuse (Insight #7 share/#9; Comp #1; Inst #14) | **KEEP** (wave 3) [S+F] | extend `_FACET_SKELETON_ADDENDUM` (`multi_section_generator.py:942-951`) w/ conditional 5th framework role + body-foci channel-reuse + (U8 folded) designated-concept define+reuse. Outline text only. [F] notes contract stream partly delivers this via `workforce.yaml` | outline-JSON: framework role ≤ pos 2 + ≥50% body foci carry a channel term; **task-91 NO-FIRE** |
| **U3** explain divergence (Insight #8 .0800; Comp #5) | **KEEP** (wave 2 lead) [S+F] | harvest ALL 3 contradiction-judge classes + boundary reason (`contradiction_mining.py:123-167`, today yield 0) into a pre-gen divergence ledger; render into synthesis-focus text + the existing relation-framing prompt (`:12382-12399`, plain text, NOT an admission seam). [S] DROP if it can't reach the prompt without a relation/license object | miner unit-run: ledger non-empty (today 0); emitted synthesis names ≥1 boundary term/pair |
| **U4 (+U6)** measure×context comparison + retire degrading tables (Insight #8 share; Comp #3 .0725; Read .056) | **KEEP** (wave 2) [S+F] | regroup relation-packs by shared-MEASURE×different-CONTEXT using existing attrs (`relation_evidence_packs.py:56-66→69-85`); writer directive + "table→interpretation paragraph" rule; retire any table whose only non-dup column is citations AT ITS PRODUCER (pre-write). U6 folded: synonyms=one context | simulated-clean lint: 0 malformed / 0 verbatim dupes; comparative-sentence counter |
| **U5 (a+b)** coverage breadth (Comp #2+#3 .0725×2; Inst #16) | **KEEP, split** (wave 4) [S+F] | U5a outline: quantified-class → multiple distinct instances where evidence supports (`:939-960`). U5b retrieval: point the EXISTING sweep gap-round/saturation at typed {factual/causal/comparative/critical} facet queries — **NEW corpus snapshot, own baseline arm**. [F] Phase-3 scope_contract/coverage_obligations seams are NOT on the Gate-B path | U5a outline-JSON ≥2 distinct instances; U5b retrieval telemetry (3→8+ instances) + FACT pair count |
| **U6** regime diversity | **KEEP — merged into U4/U5a** [F] / [S] standalone outline instruction | (see U4+U5a) | (see U4) |
| **U7** labeled cross-cutting propositions (Insight #10 .0640) | **KEEP** (wave 3) [S+F] | extend synthesis-role sentence (`:952-955`) w/ [F] directive: name cross-cutting proposition, ≥2 cited findings, fixed 3-level status label, state the discriminating test. **[S+F] Sol's inference planner REJECTED** | ≥1 labeled proposition w/ ≥2 markers (today 0); zero-new-number; 91 no forced novelty; verifier-survival⇒DROP |
| **U8** concept spine | **KEEP — merged into U2** [F] / [S] via outline focus | (see U2) | (see U2) |
| **U9** measurement ontology (Comp #4/#6; Inst #15) | **DROP** [F] / [S] keep-as-labels — **RESOLVED: DROP** | [F] only honest test is NLI-shaped + planner form is a runtime aggregation gate; largely moot vs live writer **rule 8** (`:3524-3525`) + rule 4 (`:3521`). Residual value carried by U3's boundary vocabulary. [S] wanted prompt-labels + "no aggregate over incompatible values" test — but that test needs semantic incompat detection → ghost-adjacent. **Ghost-ban ⇒ conservative call ⇒ DROP** (revisit as a specific prompt change only if Stage-0 indicts it) | — |
| **U10** implications from mechanisms + resolvable gaps (Insight #11 .0480; Comp #6) | **KEEP** (wave 3) [S+F] | strengthen closing-role sentence (`:955-956`): conclusion names its mechanism/evidence family; each gap states its resolving observation; benefit/harm for-whom/when. **[S+F] implication-object planner REJECTED** | every gap bullet has a resolvability clause (0/4→all) |
| **U11** source signaling (Inst #17+#18 .0625; Comp #5) | **KEEP scoped** [F] / [S] DROP-broad — **RESOLVED: KEEP the narrow prose form, DROP the exclusive-compliance claim** | [S] correctly: an "exclusive compliance" guarantee needs runtime source filtering = BANNED → DROP that. [F] narrow clean form KEPT: venue-at-first-mention directive (metadata already in `workforce.yaml`/`format_source_attribution_metadata:3902-3938`) + reader-register Limitations (no tier codes) + a policy sentence ONLY if telemetry truthfully entails it. No compliance gate | venue-attribution rate ~0→≳0.8; zero internal-vocab tokens; policy-clause ⊆ telemetry |
| **U12** layout + single-Limitations (Read .0840; below parity) | **KEEP lite** (wave-1 rider) [S+F] | (i) final-render ordered-token-proven layout normalizer before first `report.md` write (`run_honest_sweep_r3.py:17951-17965`) — the SOLE post-gen op, content-exact; (ii) single-Limitations ownership at plan merge (`multi_section_generator.py:11479-11484`). [F] Gate-B framing paragraph left alone (moot) | render lint (run-in headings/repeated-Limitations/verbatim-dupes → 0); ordered-token identity |
| **U13** no residual dump (Inst #13 .0500) | **KEEP lite** [F] / [S] DROP-routing — **RESOLVED: KEEP the outline clause, DROP the routing planner** | [S] correctly: a marginal-contribution routing planner / body exclusion / post-gen deletion = BANNED → DROP that. [F] clean form KEPT: one anti-residual sentence in the OUTLINE instructions (writer already has the composition rule `:3593-3595`; outline side is the missing half) + outline-JSON lint. **[S+F] routing planner REJECTED** | outline-JSON: zero residual-class sections; no section owning majority of routed IDs (telemetry) |
| **U14a** FACT volume via more admitted works | **KEEP** (rides U5b) [S+F] | no separate change — mathematically downstream of U5b (each new admitted work +≥1 pair). **[S+F] external-citation claim contract REJECTED**; only a retrieval-side canonical/DOI-URL preference note is clean | FACT extract+dedup pair count before/after U5b; full-FACT valid_rate ≥ baseline |
| **U14b** one-fact-one-sentence | **DROP** [F] / [S] keep-narrow — **RESOLVED: DROP route-wide; narrow per-producer only if Stage-0 indicts** | Already stated on BOTH streams (`slot_fill.py:767-769`; legacy rule 8 `:3524-3525`). [F] "extend to every authored producer + audit after each rewrite" = the 27-route drift trap → DROP. [S] narrow "add to legacy + regulatory prompts" is clean but [F]'s condition applies: **do it only if Stage-0 FACT telemetry shows a specific producer depresses pairs, then fix THAT producer's prompt as its own tested lever** | (conditional; per-producer output atomicity + FACT pairs) |

**Net: 12 KEEP (U1,U2+U8,U3,U4+U6,U5,U7,U10,U11-narrow,U12-lite,U13-lite,U14a) / 2 DROP (U9, U14b-route-wide).**

---

## 3. STAGE-0 (precondition — no lever precedes it) + BUILD WAVES

**Stage-0** [S+F]: (a) **lineage seam** — bypass Gate-B's forced idx-56 override (`run_gate_b.py:5659-5687`), carry
the registered legacy task-72 question (`run_honest_sweep_r3.py:7919-7934`, byte-identical to `query.jsonl` id=72
[F]-verified) end-to-end through generation + `score_report_race.py --task-id 72`, keeping the
`gate0_lineage.assert_no_split_brain` guard pointed at the legacy source. Experiment-identity plumbing, no content
lever. (b) **re-baseline** — ≥3 V30-on/task-72 draws, one pinned judge, frozen `corpus_snapshot.json`; freeze RACE-
by-dim/FACT/hashes; **re-anchor every deterministic before-number** on these artifacts. TEST: question-hash identity
at every stage + V30 dispatch confirmed + 3 `race_result.txt` exist.

**Waves** (Fable's seam-grouping; Sol's ordering noted where it differs):
- **Wave 1 — writer floor:** **U1** (both streams) + **U12-lite** rider (render lint hedges U1's Read-density risk in the same 3v3).
- **Wave 2 — relation layer:** **U3** (lead) → **U4 (+U6)**. U4 meaningless without U3's ledger.
- **Wave 3 — outline roles (one skeleton seam `:939-960`):** **U2 (+U8)** + **U7** + **U10**. Task-91 no-fire is the wave's signature held-out test. (U7 after wave 2 — reads U3's multi-source clusters.)
- **Wave 4 — breadth & compliance (corpus-changing):** **U5a → U5b** (new corpus, own baseline arm) + **U11-narrow** + **U13-lite** + **U14a** (test-only rider).
- Critical path **U3→U4→U7**. **First lever: U1.**
  *(Sol's alt ordering put U5/U8/U2/U10 in wave 2 and U9/U6/U3/U4 in wave 3; both agree on Stage-0-first, U1-first, and the U3→U4→U7 spine.)*

---

## 4. U1 — THE CLEAN FORM (ship candidate #1, specified to the line) [S+F]

**What it is:** a pre-generation prompt amendment permitting ONE optional paragraph-closing synthesis sentence
deriving what the paragraph's already-cited findings jointly imply — verified by the EXISTING per-sentence
verifier, shipped or dropped by deterministic TESTS on output. NO admission object / binding audit / entailment /
runtime canary / non-scoreable state / engine change.

**Contract stream (V30 narrative):** [F C.1]
- User prompt `slot_fill.py:703-786` (TASK `:764-769`): add — *"You MAY close the paragraph with ONE synthesis
  sentence stating what the fields you just restated jointly imply … that follows only from the sentences you
  wrote above. It must introduce NO new number, percentage, date, unit, named entity, study, metric, outcome, or
  population not already above it, and end with the same citation marker. If no non-trivial joint implication
  exists, do not write it."* + carve the single labeled exception in the VERBATIM-CONSTRAINT block (`:770-784`).
- System `PG_NARRATIVE_PROSE_SYSTEM_MESSAGE` `multi_section_generator.py:796-807`: one clause permitting the
  bounded closing synthesis sentence (default-string change, no flag).
- Ceiling `slot_fill.py:685-700`: guidance adds "…plus at most one closing synthesis sentence"; computed cap adds
  exactly the 1 licensed sentence (pre-gen prompt-builder parameter, no magic target). Off-state → byte-identical.
- Markers: single-entity/single-marker stream → "union" is trivially `[bound]`; the existing narrative verifier
  (`contract_section_runner.py:2117-2141`, `allow_rescue=False`) makes its unchanged decision; if it drops, it stays dropped.

**Legacy-enrichment twin:** [F C.2] writer contract `multi_section_generator.py:3517-3519` + retry `:4420-4432`:
add the Phase-3 clean rule (close a paragraph with one inference from its own cited findings; no new number/entity;
carry the union of that paragraph's markers). Bodhi bolded-label form stays writer-chosen.

**TESTS (ship decision; offline scripts):** [S+F] T1 paragraph_deduction_rate (re-anchor on Stage-0; >0.6);
T2 zero-new-number ⊆ (0 violations; entity-novelty is telemetry not a gate — NER too unreliable to gate);
T3 verifier-survival telemetry **(<50% ⇒ DROP U1)**; T4 held-out 91/100/73 (91: conditional MAY → no forced/
templated closer); T5 off-state byte identity. **Probe:** 3v3 vs Stage-0; ship iff Insight paired mean > +0.027
(or Insight ≥ 0 AND Read > +0.027 via U12-lite), no dim ≤ −0.027. **Flat ⇒ DROP U1.** Anchor for expecting an
effect: fable5_scoped's per-paragraph deduction carried the only local parity-beat (Insight .5131 vs .3411).

**U1 explicitly does NOT contain** [F C.4]: no LicensedInference, pre-admitted candidate, admission disposition,
premise-relation records, emitted==admitted comparison, carrier, per-route audits, non-scoreable state, or any
change to `_verify_one_stream`/`strict_verify`/`provenance_generator`. Entire lever = 2 prompt strings + 1
ceiling parameter + 5 test scripts + 1 probe.

---

## 5. ORDERED CLEAN BUILD LIST
0. **Stage-0** (lineage binding + 3-draw V30-on/task-72 baseline + re-anchor before-numbers). *Precondition.*
1. **U1** (both streams) + **U12-lite** rider — Wave 1.
2. **U3** → **U4(+U6)** — Wave 2.
3. **U2(+U8)** + **U7** + **U10** — Wave 3 (skeleton seam; task-91 no-fire).
4. **U5a → U5b** (new corpus) + **U11-narrow** + **U13-lite** + **U14a** — Wave 4.
**DROP:** U9 (NLI-shaped test / aggregation-gate + moot vs rule 8), U14b route-wide (drift trap; narrow per-producer
fix only if Stage-0 FACT telemetry indicts a specific producer). Machinery dropped inside kept levers: AC carrier,
inference planner (U7), implication objects (U10), context-clustering planner (U6), routing planner (U13),
external-citation claim contract (U14).

Each lever: build behind an off-state byte-identity check, deterministic test at the emitted-report seam, **both**
Fable+Sol diff-gate + ghost-audit, then the 3v3 paired probe vs the last approved state. No apparatus rescues a
failing lever — it drops.
