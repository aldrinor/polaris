HARD ITERATION CAP: 5 per document. This is iter N of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

# I-meta-005 Phase 6 (#990) — Domain-general section prompts + verified synthesis — BRIEF

You are reviewing the ACCEPTANCE CRITERIA (this brief), not code. Confirm the plan
is correct/complete/safe AND rule on the ONE open design question in §4.

## 1. Goal (plan row 83)
Two coupled changes to the report generator so a NON-clinical question is not given
clinical writing guidance, and integrative prose is verified:
- **A. Clinical advisory profile loads ONLY for a clinical frame.** Phase 1 built
  `config/section_prompts/{_registry.yaml,clinical.yaml}` + the field-agnostic
  selector `select_advisory_prompt_text(claim_type)`, but deliberately left the
  registry UNMAPPED (`by_claim_type: {}`, `default: null`) because "claim_type alone
  cannot identify a clinical question — `empirical` is shared by physics/battery/
  epidemiology; a correct clinical trigger needs an ENTITY-category signal (a later
  phase)." Phase 6 IS that later phase: provide the entity-category signal so the
  clinical advisory text is appended ONLY when the frame reads clinical, and NOT for
  a non-clinical empirical question.
- **B. Integrative prose lands in the VERIFIED core, not the unverified block.**
  Today `MultiSectionReport.analyst_synthesis_text` is interpretive commentary
  tracked SEPARATELY from `verified_words` (Phase-4 manifest split:
  `verified_words = total_words - analyst_synthesis_words`). The plan wants
  integrative/synthesis prose to be VERIFIED (carry `[ev_XXX]` provenance + pass
  `strict_verify`) rather than appended as an unverified analyst block.

## 2. HARD CONSTRAINTS
1. **Gated behind `PG_USE_RESEARCH_PLANNER`** (the on-path planner mode). OFF
   byte-identical: the legacy clinical `SECTION_SYSTEM_PROMPT_TEMPLATE` + the
   existing analyst-synthesis behaviour are unchanged when the flag is off.
2. **NO `if domain == "clinical"` / clinical-title literal as an on-path control
   value.** The clinical trigger must be a DATA signal read from the frame
   (entity categories / evidence_needs), config-driven — adding a new field family
   stays a config edit (LAW VI), mirroring Phase 1's registry.
3. **Field-agnostic.** A non-clinical empirical question (battery cycle-life, GDP,
   policy) gets NO clinical advisory text and a field-appropriate prompt.
4. **Verification integrity (LAW II + §9 invariants).** Any prose moved into the
   verified core MUST go through the SAME `strict_verify` (provenance token +
   numeric-match + content-overlap) as section prose — no laundering of unverified
   interpretation into the verified count. If a synthesis sentence cannot be
   grounded with `[ev_XXX]`, it MUST be dropped or kept clearly OUTSIDE the verified
   core, never counted as verified.
5. Money: prompt/config changes are spend-free to build + smoke (the generator LLM
   call is live-only; smoke uses injected/fake section outputs). snake_case; no
   `unittest.mock` in `src/`.

## 3. FILE-BY-FILE (proposed)
1. **`config/section_prompts/_registry.yaml` + (new) entity-signal mapping**: add the
   clinical trigger. Options (B-question relates): a `by_entity_category` map (frame
   entity categories → advisory family) alongside `by_claim_type`, so a frame whose
   entities are interventions/populations/endpoints/trials selects `clinical.yaml`.
   Non-clinical frames map to nothing (or a future neutral family).
2. **`src/polaris_graph/generator/multi_section_generator.py`**:
   - extend `select_advisory_prompt_text` to take the frame's entity-category signal
     (not just `claim_type`) and resolve via the registry. Pure config lookup; no
     clinical literal.
   - Part B: route the integrative/synthesis prose through `strict_verify` so it
     lands in `verified_text` (see §4 open question for the exact mechanism).
3. **`scripts/run_honest_sweep_r3.py`**: pass the frame entity-category signal into
   the generator on-mode (it already has `_research_plan.frame`). Manifest already
   splits verified vs analyst words (Phase 4) — adjust if Part B changes the split.

## 4. OPEN DESIGN QUESTION (rule on this — quality + safety impact)
Part B "integrative prose in the verified core" can be implemented two ways:
- **B1 (verify the existing analyst synthesis):** run the current
  `analyst_synthesis_text` through `strict_verify`; sentences that ground with
  `[ev_XXX]` move into `verified_text` (counted verified), ungrounded interpretive
  sentences are dropped or kept in a clearly-labelled non-verified appendix. Risk:
  much of "interpretive expert commentary" is BY DESIGN not a single-evidence claim
  (it synthesizes across sections), so strict per-sentence provenance may drop most
  of it — losing the integrative value the analyst block was added for.
- **B2 (a verified integrative SECTION):** add an integrative/synthesis SECTION to
  the planned outline (an archetype) that is generated WITH evidence + verified like
  any other section, and RETIRE or shrink the separate unverified analyst block. The
  integrative prose is then grounded-by-construction. Risk: larger change; must not
  regress OFF-mode or the Phase-4 partial-mode appender-disable.

**Which does Phase 6 implement?** My lean is **B2** (grounded-by-construction
integrative section is the honest "verified synthesis" the plan asks for; B1 risks
either dropping the synthesis or laundering ungrounded prose). But B2 is the larger
build. Rule: B1, B2, or a bounded hybrid — and if B2, confirm it rides the existing
archetype/partial-mode machinery so OFF + partial_saturation stay intact.

## 5. GREEN (exit, #990 + plan row 83)
- clinical advisory text appends ONLY for a clinical frame; a non-clinical empirical
  question gets none (data-signal trigger, no literal).
- integrative prose is VERIFIED (per the §4 ruling), not counted as verified unless
  it passed `strict_verify`.
- OFF byte-identical; field-agnostic; no clinical literal on the on-path.

## 6. SMOKE (proposed)
- P6-1 OFF byte-identity (legacy template + analyst block unchanged).
- P6-2 clinical frame → clinical advisory text appended.
- P6-3 non-clinical empirical frame → NO clinical advisory text.
- P6-4 the §4 mechanism: integrative prose only counts as verified after
  strict_verify (an ungrounded synthesis sentence is NOT in verified_text).
- P6-5 no clinical title/domain literal as an on-path control value (grep-style
  assertion + behavioural).

## 7. Output schema (REQUIRED)
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
design_ruling_part_b: B1 | B2 | hybrid (+ one-line why)
```
