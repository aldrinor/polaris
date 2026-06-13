# Codex DESIGN REVIEW — POLARIS consolidation (per-claim basket) design, I-arch-001 (#1245), iter 5 of ≤5

HARD ITERATION CAP: 5 per document. This is iter 5 of 5 (the cap).
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

## ITER-4 → ITER-5: what changed (FINAL gate — verify the two wiring fixes; confirm APPROVE)
Iter 4 was dual `REQUEST_CHANGES` but strongly CONVERGED: **both reviewers 0 P0, faithfulness SAFE, catalog complete** (Codex: "no other common clinical-lethal discriminator missing"; Claude convergence lens CLEAN over 9 candidate dimensions). The only opens were two COMPLEMENTARY wiring P1s + one path typo. Iter-5 closes them.
1. **`[FIX-5, Claude iter-4 P1]` `atom_uid` provisioned (§4.2/§7).** The fail-closed singleton key used `claim.atom_uid` but the field was never added (today per-atom uniqueness is a threaded `claim_index` argument the single-arg `build_merge_key` can't read). §7 now adds a per-atom-unique `atom_uid` to `AtomicClaim`, set from the threaded `claim_index`. **VERIFY** §8 test #23 (two unresolved atoms of the same `evidence_id` → distinct singleton ids; no same-source collision under numeric fan-out).
2. **`[FIX-5, Codex iter-4 P1]` real `domain` threaded (§7).** The main path called `run_credibility_analysis(..., domain=None)` (`multi_section_generator.py:5471-5473`) while `generate_multi_section_report` had the real `domain` (`:5224`, from `run_honest_sweep_r3.py:6146`); with fail-closed dispatch `domain=None` ⇒ consolidation INERT. §7 now threads the normalized query domain through `run_credibility_analysis`→`build_claim_graph`→`AtomicClaim.domain`. **VERIFY** §8 test #22 (activated main-path: two all-known equal clinical atoms MERGE while missing/unknown-domain stays singleton).
3. **`[FIX-5]` path typo** corrected to `generator/quantified_analysis.py` (§5/§8).
This is the FINAL (iter 5/5) gate. APPROVE iff the two wiring fixes are genuinely closed (so Principle 2 is now executable on the main path and singletons are unique) and there is no NEW P0/P1. A *rare* not-yet-catalogued within-domain dimension is an acceptable §9.1-bounded residual (fail-closed dispatch + §-1.1 audit), NOT a blocker.

## What this is
A DESIGN review (no diff yet) of the **consolidation step** — the keystone (Wave 3) of the POLARIS deep-research pipeline redesign. This is **clinical-grade and faithfulness-critical**: a wrong design here fabricates corroboration that can survive to a patient-facing report. The design has ALREADY been through one adversarial clinical stress test (verdict DESIGN_NEEDS_FIXES) and its 5 required fixes are integrated. Your job: find what still FAILS, grounded in file:line. If it is sound, SAY SO — manufacturing a defect to look thorough is itself the failure.

## The yardstick — operator's three principles
1. **Weight, don't filter** — every relevant source flows to composition with a credibility weight; never hard-drop to hit a number; social media stays low-weight.
2. **Consolidate, don't drop** — group same-claim sources into a basket; keep them ALL as corroboration; cover qualitative claims, not numeric-only.
3. **Basket faithfulness** — verify each claim against its WHOLE basket; the verdict carries corroboration (count + weights + agreement). STRENGTHENS faithfulness, never relaxes it.

## THE LOAD-BEARING FINDING the design now rests on (verify it)
`strict_verify` is **per-member** — it checks each generated sentence against ITS OWN cited span and NEVER cross-compares two basket members (claimed: `src/polaris_graph/generator/.../strict_verify` path; verify the exact file:line). Therefore a **false-MERGE** (two distinct claims fused into one basket) fabricates a corroboration COUNT, not a span — every wrongly-merged member still grounds its own span and passes. **So span-grounding is structurally incapable of catching an over-merge, and the MERGE KEY is the SOLE defense.** Consequence: any discriminating slot that can be empty (`''`) on both sides and is NOT sentinel-guarded is an UNBACKSTOPPED LETHAL HOLE. Confirm or refute this — it is the spine of the whole design.

## READ THESE (verify against the real code, do not hand-wave)
- `docs/consolidation_design_wave3.md` — THE design under review (§0 the merge-key-is-sole-defense argument; §1 atomic extraction; §2 equivalence; §3 PICO-TS blocking; §4 the false-merge guard set; §5 data model with two origin counts; §6 verification+render; §7 files; §8 the 6 proof tests; §9 open risks).
- `docs/pipeline_redesign_master_plan.md` — parent plan (the 3 principles, §6 faithfulness-safety, the wave order).
- Code: `src/polaris_graph/synthesis/claim_graph.py` (`_normalized_key_numeric` ~L191-213, `_normalized_key_qualitative` ~L216-239, `cluster_equivalent_claims` L362-380, per-claim sentinel L202-203/231/340, `extract_atomic_claims` L246-346); `src/polaris_graph/retrieval/contradiction_detector.py` (`ExtractedNumericClaim` L170-183, `_extract_endpoint_phrase` L353-369, `_subject_near_position` ~L520); `src/polaris_graph/retrieval/qualitative_conflict_detector.py` (`condition_scope`/`object_slot` default `''` ~L363-371); `src/polaris_graph/synthesis/finding_dedup.py` (member-drop L196-210, `round(value,3)` key L91); `src/polaris_graph/synthesis/weight_mass.py`; `src/polaris_graph/synthesis/both_sides.py`; `src/polaris_graph/synthesis/credibility_pass.py`; the strict_verify path.

## REVIEW QUESTIONS (answer EACH, grounded in file:line)
1. **False-merge guard COMPLETENESS (the P0 question).** The design claims to generalize the unknown-blocks-merge sentinel to: numeric population, comparator, endpoint_phrase/timeframe, direction/sign; qualitative condition_scope, object_slot. Verify against the ACTUAL key functions. **Is there ANY discriminating slot that can be `''` on both sides and would still wildcard-merge (`''=='' ` → same cluster)?** Name every one you find — each is an unbackstopped lethal hole.
2. **Is §0 correct** — that strict_verify is per-member and cannot catch cross-member fusion? Cite the exact file:line.
3. **FAITHFULNESS SAFETY (lethal if wrong).** Is there ANY path where a claim passes on weaker evidence than TODAY? Check: basket verdict can only downgrade/label never upgrade; the strengthening count is `verified_support_origin_count` (members that each pass strict_verify) NOT `total_clustered_origin_count`; the equivalence NLI fails CLOSED. Name any regression, any field-conflation, any OR-that-lowers-the-bar.
3b. **Does the design ADD any new accept path** (e.g., the optional `PG_SWEEP_CLAIM_EQUIV` NLI merge) that could merge two claims that should stay separate? Is fail-closed actually fail-closed?
4. **Delivers the 3 principles?** Weight (sources kept + weighted, not dropped)? Consolidate (keep ALL basket members, qualitative too)? Basket faithfulness (verify vs whole basket, strengthen not relax)?
5. **Over-engineering to CUT?** Anything bigger/fancier than needed. (Operator hates over-engineering. The design claims the ONLY genuine build is population/comparator/direction fields + the generalized sentinel — is that right, or is something else sneaking in a rebuild?)
6. **Any WRONG move that breaks a working part?** finding_dedup retirement must preserve its safe behaviors (qualitative pass-through, conservative-singleton, unknown-subject sentinel). claim_graph/weight_mass/both_sides reuse must not break them. The faithfulness engine must be untouched.
7. **Reuse-not-rebuild real?** Is the claim that this reuses claim_graph/weight_mass/both_sides/credibility_skill (no new framework, no second scorer) accurate against the code?
8. **Wave-3 scope correct?** Does it correctly NOT dissolve `PG_MAX_EV_PER_SECTION`/source caps (that is Wave 4, because baskets must exist first)? Is OFF = byte-identical (default-OFF flag) genuinely achievable?

## OUTPUT SCHEMA (end your review with EXACTLY this)
```yaml
verdict: APPROVE | REQUEST_CHANGES
sole_defense_claim_confirmed: yes|no — <strict_verify per-member, file:line>
unsentineled_slots_found: [<every discriminating slot that can still ''==''-merge, file:line; or "none">]
faithfulness_safety: SAFE | RISK — <any path to weaker-than-today acceptance; or none>
delivers_principle_1_weight: yes|partial|no
delivers_principle_2_consolidate: yes|partial|no
delivers_principle_3_basket_faithfulness: yes|partial|no
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
over_engineering_to_cut: [<or "none">]
breaks_working_part: [<or "none">]
convergence_call: continue | accept_remaining
top_changes_before_execution: [<minimal set to fix before coding; empty if APPROVE>]
```
APPROVE_PLAN iff the false-merge guard set is complete (no unsentineled discriminating slot), the faithfulness gate cannot regress, all three principles are delivered, and there is no real over-engineering or broken-working-part. Do not nitpick cosmetics into a block.
