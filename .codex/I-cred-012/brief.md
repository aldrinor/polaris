# I-cred-012 (#1162) — ACTIVATION integration ARCHITECTURE (wire the redesign chain into the live path) — BRIEF for Codex

HARD ITERATION CAP: 5 per document. This is iter 5 of 5 (the CAP). (Read ITER-1..ITER-4 RESOLUTIONS — ITER-4 covers the fact-dedup `_resolve` alias path, P10 append-only + plan_sufficiency re-cert, honest_pipeline scope-out, and the P3 certainty carrier.) Per §8.3.1: if this returns REQUEST_CHANGES, the architecture is force-APPROVE'd on remaining non-P0/P1 and any residual narrow edge case becomes a sub-issue follow-up — there is no iter 6.
- Front-load ALL real findings in iter 1. Reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, force-APPROVE'd on remaining-non-P0/P1; no iter 6.
- Surface any held-back P1 NOW. Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

This is a DESIGN brief for the INTEGRATION ARCHITECTURE — where each of the 11 committed pure modules plugs into the live pipeline, in what order, gated by which flag, producing what for downstream. NO code yet. Your job: validate the hook points + order + flags, catch any faithfulness/ordering risk, BEFORE I edit the binding generation/retrieval/adequacy paths. The actual per-hook diffs are the sub-issues (007b/008b/010b/006b), each its own diff-gate.

## 0. HARD CONSTRAINTS (operator-locked)

- The redesign chain is ADVISORY. `strict_verify` (provenance_generator) + the 4-role D8 release policy (roles/release_policy.py) stay the ONLY binding gates. No module's output can keep/drop a sentence or flip release.
- Every hook flag-gated; OFF ⇒ byte-identical. Activation = a deliberate Gate-B slate (force-on + fail-closed preflight), like the existing STORM/4-role slate — NOT default-on.
- Fail-LOUD on a wired module erroring (no silent swallow → false green — the drb_72 dead-route lesson). A wired-but-broken module must abort, not degrade silently.

## 1. The 11 modules + their I/O (committed, default-OFF)

- P2 `authority/credibility_skill.py` `score_source_credibility(question, rows, *, domain, judge) -> [CredibilityJudgment(evidence_id, reliability, relevance, credibility_weight, ...)]` — needs retrieved rows + the injected production judge.
- P3 `authority/supersession.py` `supersession_adjustment(row) -> SupersessionResult` — per source.
- P4 `synthesis/independence_collapse.py` `collapse_independent_origins(rows, ...) -> origin clusters + per-row canonical/origin_cluster_id`.
- P5 `synthesis/claim_graph.py` `build_claim_graph(rows, ...) -> AtomicClaim[] (claim_cluster_id) + ContradictionEdge[]`.
- P6 `synthesis/weight_mass.py` `aggregate_weight_mass(claims, rows, judgments) -> ClaimWeightMass[]` (rows must carry origin_cluster_id + is_canonical_origin from P4; judgments from P2).
- P7 `synthesis/both_sides.py` `compose_both_sides(edges, weight_mass, claims) -> blocks` + `render_both_sides(blocks) -> str`.
- P8 `synthesis/disclosure_population.py` `populate_disclosure(verifications, credibility_by_evidence, origin_by_evidence) -> verifications'` (operates on post-strict_verify SentenceVerifications).
- P10 `retrieval/dissent_recall_builder.py` `build_dissent_queries(edges, claims, weight_by_cluster) -> queries` (feeds retrieval).
- P11 `synthesis/calibration_metrics.py` — offline analysis, not in the live path.

## 2. Proposed integration (PLEASE VALIDATE the hook points + order)

```
run_live_retrieval (retrieval/live_retriever.py:2317)  -> evidence rows
  │
  ├─[CREDIBILITY-ANALYSIS PASS — NEW flag-gated step, after retrieval / before generation]
  │   1. P4 collapse_independent_origins(rows)  -> merge origin_cluster_id + is_canonical_origin ONTO rows
  │   2. P3 supersession_adjustment per row     -> additive temporal signal
  │   3. P2 score_source_credibility(question, rows, judge=production_judge) -> credibility_by_evidence
  │   4. P5 build_claim_graph(rows)             -> AtomicClaim[] + ContradictionEdge[]
  │   5. P6 aggregate_weight_mass(claims, rows, judgments) -> ClaimWeightMass[]
  │   (+ P10 dissent: if edges, build_dissent_queries -> feed a flagged saturation gap-round BEFORE generation)
  │
  ├─ generate_multi_section_report (generator/multi_section_generator.py:4381)  [UNCHANGED generation]
  │     └─ strict_verify (BINDING, unchanged) -> SentenceVerification[]
  │
  ├─[P8 populate_disclosure(verifications, credibility_by_evidence, origin_by_evidence)]  -> populated fields
  │
  ├─ 4-role D8 release policy (roles/release_policy.py)  [BINDING, unchanged]
  │
  └─[REPORT ASSEMBLY]
        ├─ P8 render: the 4 disclosure fields per claim (SUPPORTS not EXISTS) into resolve_provenance_to_citations
        └─ P7 render_both_sides(blocks): appended as a disclosure section AFTER verified prose (like limitations_text:289)
```

**Q1 — the credibility-analysis pass hook:** where exactly does this flag-gated pass live? Candidates: (a) inside the sweep orchestrator (`scripts/run_honest_sweep_r3.py` / the Gate-B runner) between retrieval and generation; (b) a new `src/polaris_graph/synthesis/credibility_pass.py` orchestrator the runner calls. I lean (b) — a pure orchestrator function `run_credibility_analysis(question, rows, *, domain, judge) -> CredibilityAnalysis(judgments, origin_by_evidence, claims, edges, weight_mass)` that the runner invokes when the slate flag is on, keeping the wiring testable + the runner change minimal. Confirm.

**Q2 — flag slate:** one master `PG_SWEEP_CREDIBILITY_REDESIGN` that turns the chain on (the per-module flags stay as sub-switches), set force-on in the Gate-B slate with a fail-closed preflight? Or keep per-module flags only? I lean a master slate flag + per-module sub-flags (matches the existing STORM/4-role slate pattern).

**Q3 — P10 dissent feedback into retrieval:** dissent queries need P5 edges + P6 weights, which need the rows — but feeding them back means a SECOND retrieval round (saturation). Is the right shape: round-0 retrieve → credibility pass → if edges, dissent gap-round → re-run credibility pass on the enlarged corpus → generate? Confirm the loop shape + that it stays inside the existing saturation budget.

**Q4 — P8 render touches provenance_generator (a faithfulness file).** It only renders the 4 inert disclosure fields (additive, flag-gated), never the verify logic. Confirm that the render edit is acceptable as additive-disclosure (Phase-1 designed the fields for exactly this) vs needing its own extra-careful sign-off.

**Q5 — fail-loud:** each wired module wrapped so an exception ABORTS (e.g. `abort_credibility_pass_error`) rather than silently skipping — the drb_72 silent-downgrade lesson. Confirm this is the right posture (vs degrade-to-OFF on error, which would hide a broken activation).

## 3. Acceptance for THIS architecture brief

Validate: (a) the hook points + order are correct + faithfulness-safe; (b) the binding gates (strict_verify, 4-role D8) are untouched; (c) OFF stays byte-identical; (d) the fail-loud posture; (e) the data-flow joins (evidence_id, origin_cluster_id, claim_cluster_id) are coherent across the chain. Flag any ordering bug (e.g. P6 before P4-merge, P8 before strict_verify).

## 4. Output schema

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```
