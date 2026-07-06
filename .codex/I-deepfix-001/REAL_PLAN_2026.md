# REAL PLAN 2026 — POLARIS composition + coverage fix (Codex + Claude + Fable, converged)

**Grounding:** the 2026 deep-research brief (`BESTPRACTICE_2026_BRIEF.md`), the confirmed root (`TRUE_ROOT_SOLUTION.md`), and a full two-round Codex+Fable iteration with every code-cite verified against the real repo (`iter_fable_propose.md`, `iter_codex_review.md` = verdict CONVERGE, `iter_fable_refine.md`). Research + plan phase. **NO code has changed. Awaiting operator GO before any build.**

---

## plain_verdict (plain English)

Here is the real fix, in plain words.

Right now the pipeline writes the report the wrong way round. It checks one sentence against one source first. Then it only lets the writer glue those already-checked sentences together. That one rule is the root of both problems you keep seeing. The prose comes out choppy and broken, like a list of unrelated islands. And there is no real cross-source thinking, because no step is even allowed to write a sentence that pulls two sources together.

The winners in 2026 do it the other way. They write the whole coherent report first. Then they check each sentence against its sources afterward, as a filter. If a sentence fails, they fix it or drop it — but they never chop the writing back into pieces. We confirmed this is what ChatGPT-style deep research, and the top research papers, all do.

So the fix is: let the writer write a real connected paragraph for each group of sources first. Then run our exact same safety check on each sentence, downstream. If a sentence does not hold up, re-word it a couple of times; if it still fails, throw that sentence away and show the raw source quote in a clearly labeled box instead — never glued into the prose.

We fix coverage at the same time, as an equal job, not an afterthought. Today most source groups end up with only one source, so there is nothing to cross-compare. We turn on the grouping that puts sources that say the same thing into one basket. We move the cross-source comparison out of a dead side-branch and into the main writing. We widen the search so we gather more angles. And we add a check that fails loudly if the report comes out shallow.

The safety check itself does not change at all. It stays exactly as strict. We are only changing which sentence gets written, never how a sentence is judged. That is the clinical-safety line, and it is not touched.

Both reviewers — the real Codex and the real Fable 5 — agree on this. They checked it against our actual code. They fixed two of our own mistakes in the process: one claim we made about a flag was wrong, and one research citation did not exist, so we dropped it. That is the honest state.

One more honest point. Most of this we can test fast by replaying source sets we already have on disk. But the wider-search part cannot be tested that way — it needs one small fresh paid run to prove it. And the biggest danger is a "fake success": the flags turn on, the logs look busy, but the report is still shallow. So the real proof is a reader that checks the actual finished paragraphs, not internal counters. We build that reader as part of the work.

That is the plan. Nothing is built yet. Say go and I start building, one piece at a time, each piece checked by both Codex and Fable before it counts.

---

## the_real_architecture

One pipeline, coherence produced once at compose time, verification applied downstream as a filter that never re-fragments prose:

`PLAN -> RETRIEVE -> CONSOLIDATE -> SYNTHESIZE (coherent prose FIRST) -> ATTRIBUTE (deterministic binding; writer tokens are hints) -> VERIFY (per-sentence, downstream, UNCHANGED) -> REPAIR (re-attribute -> bounded re-draft -> discard/label) -> RENDER`.

- **PLAN** — `_section_baskets_for_compose` (`multi_section_generator.py:4927`) upgraded to carry (facet, basket-ids, pro/con allocation), fed by the facet planner's `counter_evidence` lens (`expert_facet_planner.py:44`).
- **RETRIEVE** — STORM + tier classifier unchanged (weight-not-filter); frontier widened by the two wideners.
- **CONSOLIDATE** — finding_dedup multi-member clusters become the baskets (keep-all, merge-only).
- **SYNTHESIZE** — the writer drafts one coherent multi-sentence narrative per multi-source basket group, plus cross-basket analytical units and the section lead, in one pass, from supplied evidence only. **This is the only place global coherence is produced.**
- **ATTRIBUTE** — writer `[#ev]` tokens are hints; the authority is deterministic post-hoc binding (`verify_sentence_provenance` + bounded re-anchor `provenance_generator.py:1297-1352`, "no new acceptance path" + `PG_SPAN_RESOLVER` argmax), plus a NEW cross-member coarse step under the identical full-gate contract.
- **VERIFY** — strict_verify + NLI + the stricter writer wrapper + own-region gate + 4-role D8 + report_redactor, byte-untouched. A failing sentence routes to REPAIR, never to concatenation.
- **REPAIR** — re-attribute first, then bounded whole-paragraph re-draft via existing `revise_reasons`, capped by `PG_WRITER_REPAIR_MAX`; every attempt re-runs the unchanged gate; exhaustion discards the failed authored sentence.
- **RENDER** — [N] resolution, the CWF corroboration weight channel, presentation tables, one chrome screen.

## composition_fix

Behind `PG_SYNTH_PRIMARY` (default OFF) + `PG_WRITER_REPAIR_MAX` (default 2).

1. **Flag-selected writer contract (NOT edited in place).** Keep `_WRITER_SYSTEM` byte-unchanged; add `_WRITER_SYSTEM_GROUP` ("one coherent multi-sentence narrative for this GROUP of verified spans; every sentence ends with its exact provenance token(s); every number verbatim; every hedge preserved; never a fact outside a provided span"). Select at call time on the flag read — so gate-B's force-ON `PG_ABSTRACTIVE_WRITER` (`run_gate_b.py:825`) stays byte-identical when `PG_SYNTH_PRIMARY` is unset. **(This corrects our own round-1 "byte-identical" error, found by code-check.)**
2. **Bounded repair + separate labeled fallback block.** In `_compose_one_basket` (`verified_compose.py:1268-1335`), behind the call-time flag: collect all failing sentences -> CoF re-attribution -> whole-paragraph re-draft with `revise_reasons` -> full re-verify (UNCHANGED wrapper), cap `PG_WRITER_REPAIR_MAX`. On exhaustion keep verified authored sentences as body; emit the uncovered fact's K-span as a LABELED bracketed evidence unit on its OWN line via the ARM-B pattern (`partition_composed_disclosures` :1156 + `render_degraded_disclosures` :1174) — NOT the current mid-line glue `" ".join(kept + [fallback])` (:1329). Failed authored sentences are discarded, never shipped.
3. **Primary-path wiring.** `PG_SYNTH_PRIMARY` makes the group-writer the primary body path (`multi_section_generator.py:4924-5030`; `assert_activation_preconditions` still hard-requires entailment=enforce); the FIX-K span-dump demotes to fallback-only. No new hot-path imports.
4. **One hygiene screen** (`is_render_chrome_or_unrenderable`, pre-writer + final render). Freeze the per-shape denylist stack; consolidation is a later PR.

## coverage_fix

Co-equal track, its own gate (never derived from the defect list, per the coverage-is-co-equal directive).

1. **Multi-origin baskets EXIST (keystone).** Flip `PG_BASKET_CONSUME_FINDING_DEDUP` ON (`credibility_pass.py:65-76`). Add `PG_FINDING_DEDUP_NLI` (default OFF, slate-ON) requiring **strict bidirectional entailment** (`consolidation_nli.py:334-343`) to merge; one-direction-only = an EXTENSION edge (not a merge); contradiction = durable `ContradictionEdge`; infra-`None` = fail-closed singleton.
2. **Cross-source analysis into the body plan.** Replace anchor-equality pairing (`cross_source_synthesis.py:85-94`) with plan-driven candidates (same facet; `ContradictionEdge` via `_edge_between`; `entails_directional` agreement/extension). Keep `LICENSED_CONNECTIVES` closed + `relational_quantifier_guard`. Move `compose_cross_source_analytical_units` + `depth_synthesis.synthesize_cross_source_findings` out of the fail-open tail into `_compose_section_per_basket` (edges already threaded at `:4976/:5011`).
3. **Numeric comparator, fail-closed.** Comparative connective only when measure/unit/entity/denominator/time-window/baseline ALL match (extend `_normalized_key_numeric`, `claim_graph.py:229-239`); any missing/ambiguous field => neutral connective. Pure arithmetic over already-verified numbers; each clause keeps its own token.
4. **Structured tables** — `presentation_tables.py` behind `PG_PRESENTATION_TABLES` (default OFF): deterministic tables of verbatim verified numbers + [N] cites.
5. **Flip + slate the wideners** — `PG_EXPERT_FACET_PLANNER` + `PG_SUBENTITY_QUERY_EXPANSION`; add coverage flags AND `PG_SYNTH_PRIMARY` to `_PAID_PATH_WINNER_FLAGS` (`run_honest_sweep_r3.py:20012-20023`) + gate-B full-capability slate.
6. **Fail-loud dark-path canaries** (`run_gate_b.py:2431` family): `assert_depth_synthesis_fired` (eligible baskets yet `kept_findings==0`) + `assert_multi_origin_baskets_exist` (multi-member clusters yet zero `verified_support_origin_count>=2` baskets). Detectors force investigation, never a number.

## traceability

1. **Minimal independently-entailing inline set** (`citation_set_minimizer.py`, `PG_MIN_CITE_SET` default OFF): (i) prune inline members whose span does not entail THAT sentence (pure Citation-Accuracy win); (ii) demote MVC-redundant same-statement corroborators (Hopcroft-Karp) to the weight channel. Honest tradeoff: removing a true supporter lowers Citation-Thoroughness, so the demotion threshold is TUNED against the offline scorer, not set to strict singleton. Render-channel only; basket keeps ALL members.
2. **Corroboration weight channel** — demoted/claim-but-not-sentence-entailing members render in the CWF surface (`_basket_corroboration_block`) as count + tier weights; nothing deleted (§-1.3 weight-not-citation).
3. **CoF re-attribution before repair** — coarse = sibling basket member rows (new, identical contract); fine = existing bounded re-anchor + `PG_SPAN_RESOLVER`. Both re-anchor flags slate-ON (default-OFF today).
4. **Two-sided pro/con for debate queries** — plan-time detector + `counter_evidence` lens; >=1 verified pro AND >=1 verified con; no counter-evidence => disclose the asymmetry, never fabricate balance.

## faithfulness

The ONLY hard gate stays strict_verify + NLI + 4-role D8 + provenance + span-grounding — byte-untouched, never relaxed. It moves from compositor to downstream filter. No flag touches a threshold, judge, gate condition, or abort semantic.

- Writer wrapper unchanged (no local-window rescue, judge_error fail-closed, span->sentence numeric completeness). Repair changes only which draft is submitted; strict finite cap; exhaustion can never ship a failed authored sentence.
- K-span passes provenance + own-region checks and renders only as a separate labeled evidence block — never body prose, never synthesized guidance. Always-release holds via the labeled block + untouched `_no_verified_span_disclosure`.
- Cross-source units verify per CLAUSE against each clause's OWN pool + own-region gate — never one aggregate against a union pool. Connectives carry no token, licensed only by certified engines, fail closed to neutral.
- Basket faithfulness STRENGTHENED (§-1.3.3): real multi-origin baskets mean each verdict carries genuine corroboration.

## build_validate_plan

**Waves (all default-OFF flags; parallel tracks touch disjoint files; each wave dual-gated real-Codex + real-Fable):**
- Wave 1: (1a) group contract + bounded repair + labeled fallback; (1b) keystone regroup slate-ON + `PG_FINDING_DEDUP_NLI` bidirectional-only; (1c) offline DeepTRACE self-scorer `scripts/deeptrace_self_score.py` — **TRIAGE predictor only, never a pass gate** (banked snapshots hold spans not full text, 550/694 truncated -> span-approximate by construction); its formula-fidelity itself Codex+Fable gated; (1d) slate additions + canaries.
- Wave 2 (after 1a+1b): (2a) pairing-predicate replacement + analytical-units-into-body; (2b) citation minimizer + weight-channel render; (2c) presentation tables; (2d) two-sided debate pass; (2e) **rendered-report acceptance harness** — checks ACTUAL paragraphs (writer prose shipped per section, labeled-fallback-block rate, analytical-units-in-body, verified two-sided treatment, chrome rate, rubric-facet coverage presence). This is the real gate; counters are only telemetry.

**Validation split (banked-replay-blind lesson):** replay-validatable on banked corpora — 1a, 1b, 1c, 2a, 2b, 2c, 2e — run V1 (composition-only), V2 (coverage-structural-only), V3 (both), STRICTLY isolated (no mixed-flag variants). NEEDS ONE FRESH FRONT-HALF PAID RUN (resume skips fetch/frontier) — the wideners, counter-evidence retrieval, and re-confirming the 1313-word/zero-unit artifact is gone; one small fresh scored run on the VM 2-GPU box + 5-minute forensic read-every-line. Acceptance order: self-scorer triage -> acceptance harness on rendered reports -> paid DeepTRACE + DRB-II judges on actual output -> §-1.1 line-by-line read. Word/citation/source counts stay banned.

## what_changes (exact files + flags)

**New flags (all default OFF):** `PG_SYNTH_PRIMARY`, `PG_WRITER_REPAIR_MAX`(=2), `PG_FINDING_DEDUP_NLI`, `PG_MIN_CITE_SET`, `PG_PRESENTATION_TABLES`. **Existing flags slate-ON:** `PG_BASKET_CONSUME_FINDING_DEDUP`, `PG_EXPERT_FACET_PLANNER`, `PG_SUBENTITY_QUERY_EXPANSION`, `PG_PROVENANCE_REANCHOR`, `PG_SPAN_RESOLVER`.

**Files touched:**
- `src/polaris_graph/generator/abstractive_writer.py` — add `_WRITER_SYSTEM_GROUP`; `_build_writer_prompt` group mode (keep `_WRITER_SYSTEM` byte-unchanged).
- `src/polaris_graph/generator/verified_compose.py` — `_compose_one_basket` bounded repair + ARM-B labeled fallback (flag-gated; other paths byte-identical).
- `src/polaris_graph/generator/multi_section_generator.py` — `PG_SYNTH_PRIMARY` primary-path wiring; move cross-source/depth synthesis into body plan; demote FIX-K.
- `src/polaris_graph/synthesis/credibility_pass.py` — keystone flip; NLI-merge wiring.
- `src/polaris_graph/generator/finding_dedup.py` — bidirectional-entailment qualitative grouping.
- `src/polaris_graph/generator/cross_source_synthesis.py` — plan-driven pairing predicate.
- `src/polaris_graph/generator/depth_synthesis.py` — into-body wiring.
- `src/polaris_graph/generator/claim_graph.py` — numeric match-key extension.
- NEW `src/polaris_graph/generator/citation_set_minimizer.py`, NEW `src/polaris_graph/generator/presentation_tables.py`.
- `scripts/run_honest_sweep_r3.py` (slate `:20012-20023`) + `scripts/dr_benchmark/run_gate_b.py` (slate + `:2431` canaries).
- NEW `scripts/deeptrace_self_score.py` + NEW rendered-report acceptance harness.

## converged

Codex verdict CONVERGE; Fable refine adopted all 7 Codex refinements and verified them against real code. Both agree on: compose-then-verify; deterministic post-hoc binding is authority (writer tokens are hints); K-span as a separate labeled block; minimal independently-entailing inline set + weight channel; strict bidirectional entailment for merges (contradiction/extension = edges); numeric analysis only on full unit-match; offline scorer = triage not gate; rendered-report acceptance harness vs the false-fired-pipeline risk; faithfulness never relaxed.

**Two self-corrections found during code-check (honest):** (1) our round-1 "byte-identical when OFF" claim was FALSE — gate-B force-sets `PG_ABSTRACTIVE_WRITER=1`, so the writer contract must be flag-selected at call time, not edited in place; fixed. (2) the research cite "arXiv 2604.01432" does not exist in our corpus — dropped, with the number attached to it.

**Residual nuance for the operator (small, near-converged, not a blocker):** inline-citation count is a TUNED setting measured against the offline scorer (strict singleton-minimality would cost Citation-Thoroughness), not a fixed policy. And agreement/extension pairing calls the NLI engine live rather than persisting an edge map (persisting is optional/additive).

**Biggest risk:** a "false-fired pipeline" (flags on, logs busy, report still shallow) — the mechanism most likely is repair non-convergence under the harsh wrapper. De-risk: the rendered-report acceptance harness is the real gate; replay the repair-convergence distribution on 3 banked corpora first; fail-loud canaries; V1/V2/V3 isolation; the labeled fallback keeps any failure visible and honest.
