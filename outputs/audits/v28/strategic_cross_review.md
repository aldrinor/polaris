# Strategic Cross-Review: Claude + Codex paths to 7/7 BEAT_BOTH

## Agreement (both auditors)

**Strategy β is the right path.** Both Claude and Codex independently
arrive at:

1. **7/7 BEAT_BOTH is achievable autonomously** — not a human-
   curation ceiling. The ceiling is pipeline-ordering.
2. **Current gap is pipeline-ordering, not prompt-tweaking**. POLARIS
   retrieves broadly → scores → recovers named-trial structure from
   survivors. Competitors appear to start from a curated pivotal-
   trial frame, then enrich. POLARIS needs to invert the order.
3. **Root cause** of 4 LOSE_BOTH dimensions is a single defect:
   primary publications land in live_corpus but don't become the
   spine of the report. Fixing this lifts Dims 1, 4, 5, 7
   simultaneously.
4. **Strategy α alone (narrow engineering) is insufficient** for
   7/7. It's necessary scaffolding, not the destination.
5. **Strategy γ (relax strict_verify) is rejected.** Strict_verify
   is POLARIS's core differentiator; relaxing it trades away the
   transparency advantage for marginal narrative gain.
6. **Strategy ε (ship V28) is rejected.** V28 regressed net
   dimensional health vs V27 (5 → 3 ≥BEAT_ONE dims); shipping a
   regression is not quality focus.
7. **3-cycle roadmap: V29 foundation → V30 two-stage architecture
   → V31 mechanism/narrative closure.**

## Disagreements (narrow)

### V29 scope

| Auditor | V29 scope | Rationale |
|---|---|---|
| Claude | A + B + D | Add trial table cell correction to avoid shipping "SURPASS-5 baseline 7.0%" which is factually wrong |
| **Codex** | **A + B only** | "Do not spend V29 on table cosmetics, mechanism relaxation, or broad prompt rewrites. If SURPASS-4 and SURPASS-CVOT are already in live_corpus and still absent from the report after V29, the architecture is failing at the exact custody boundary that must be fixed before 7/7 is credible." |

**Lower-verdict-controls adjudication**: Codex's stricter V29 scope
stands. V29 should be **selector-custody-only**: a single clean
architectural slice that gives us per-anchor telemetry on whether the
primary was found / selected / injected / quote-adequate / cited in
prose. Trial table correction moves to V30 or V31 — it's cosmetic
unless the primary-publication custody works first.

### Per-anchor telemetry (Codex addition not in Claude's plan)

Codex adds a new gate/telemetry artifact: for each configured anchor,
record five booleans:
1. primary found in live_corpus?
2. primary selected into evidence pool?
3. primary injected into a section's ev_ids?
4. primary's direct_quote ≥100 chars?
5. primary cited in verified prose?

If anchor is "found=true, selected=false", the V29 fix failed at the
selector. If "selected=true, injected=false", M-44 failed. If "cited
=false" despite all 4 prior true, the prompt failed. This lets V29's
outcome be diagnosed precisely, not just scored.

**Adopt Codex's per-anchor telemetry proposal.** It's a strict
improvement.

### V32 calibration cycle (Codex addition)

Codex adds a V32 safety cycle: run the entire pipeline on a
non-clinical slug (materials chemistry, ML benchmarking, etc.) to
verify the V29-V31 changes are architectural, not tirzepatide-
specific hardcoding masquerading as architecture.

Claude's plan omitted this. **Codex is correct** — POLARIS has
specifically added tirzepatide-labeled SURPASS/SURMOUNT anchors and
population_scope labels. V32 should verify these patterns
generalize.

## Convergent plan (after cross-review)

### V29 — selector primary-custody (narrow scope per Codex)

Implementation in `src/polaris_graph/retrieval/evidence_selector.py`:

1. After the tier-balanced selection pass, run a post-process:
   - For each anchor in `primary_trial_anchors` parameter, scan
     live_corpus for `_m42e_detect_primary_for_anchor`-positive
     rows.
   - If found in live_corpus but NOT in `selected_rows`, INSERT
     it into `selected_rows` at position 0 (highest priority
     for generator).
   - Cap total insertions at `len(primary_trial_anchors)`.
2. In `multi_section_generator.py`, extend M-44 to check for
   anchor-matched primaries in live_corpus (not just
   evidence_pool) and pull them into section ev_ids when present.
3. New diagnostic file: `v29_primary_custody.json` with per-anchor
   entries:
   ```json
   {
     "SURPASS-2": {
       "found_in_live_corpus": true,
       "found_ev_id": "ev_0217",
       "selected_into_pool": true,
       "injected_into_section": "Efficacy",
       "direct_quote_chars": 1842,
       "direct_quote_adequate": true,
       "cited_in_verified_prose": true,
       "citation_count": 3
     },
     "SURPASS-CVOT": {
       "found_in_live_corpus": true,
       "found_ev_id": "ev_0441",
       "selected_into_pool": false,  // fail here
       ...
     }
   }
   ```
4. M-49 preservation test extended to assert every configured
   anchor ends with `cited_in_verified_prose=true`.

Expected V29 outcome: 4-5 BEAT_BOTH + 2-3 BEAT_ONE + 0-1 LOSE_BOTH.
Lifts Dims 1, 4, 5 to at least BEAT_ONE. Dim 7 may still lag.

Cycle cost: ~6h engineering + 1 sweep (~3h) + Codex audits + audit
cycle. ~12h total.

### V30 — two-stage generator architecture

Implementation in `src/polaris_graph/generator/multi_section_generator.py`
becomes two-phase:

**Phase 1 (pivotal-primary skeleton)**:
- New outline stage that generates a pivotal-primary-only outline:
  every section cites ONLY anchor-matched primary publications.
- Per-section contract: ≥3 ETDs + uncertainty values from the
  cited primary's `direct_quote`, with inline [ev_X] citations.
- If a primary's quote is thin or missing, refetch with full
  AccessBypass cascade + failover to archive.org / Unpaywall.
- If refetch still fails, section ships with honest disclaimer:
  "Primary publication [X] was cited in the bibliography but its
  direct-quote text was insufficient for full-frame extraction."
- **No substitution of meta-analysis / post-hoc for the primary.**

**Phase 2 (enrichment)**:
- Existing M-42 bundle runs ON TOP of Phase 1 skeleton.
- Meta-analyses and reviews enrich Phase 1 claims rather than
  replacing them.
- Contradiction detection + tier disclosure + Methods block
  unchanged.

Expected V30 outcome: 5-6 BEAT_BOTH + 1-2 BEAT_ONE + 0 LOSE_BOTH.

Cycle cost: 2-3 days engineering + 1 sweep + Codex audit cycle.
~4-5 days total.

### V31 — mechanism/narrative closure

Implementation: apply V30's Phase 1 + Phase 2 pattern to the
Mechanism section specifically.

- Phase 1 mechanism outline: require ≥3 direct_quote-sourced
  quantitative fields from clamp/PK primary papers (Thomas clamp,
  Coskun receptor affinity, Frias PK review).
- Phase 2 enrichment: tie-in mechanism reviews (statpearls,
  thieme-connect) for context.
- Retain strict_verify on ALL numeric claims; synthesis-only
  sentences must have same-paragraph evidence support but not
  necessarily same-sentence.

Expected V31 outcome: **7/7 BEAT_BOTH** if primary clamp paper is
quote-adequate. Otherwise 6/1 with Narrative at BEAT_ONE.

Cycle cost: 1-2 days engineering + 1 sweep + audit. ~3 days.

### V32 — calibration (Codex addition)

Run V31's pipeline on a non-clinical research question
(materials chemistry, ML benchmarking, macroeconomics — whatever
the clinical template generalizes to). Validate that the selector
custody + two-stage architecture work without tirzepatide-specific
hardcoding.

Cycle cost: 1 day + 1 sweep. ~2 days.

## Budget

- V29: ~12h / ~$5
- V30: ~5 days / ~$5
- V31: ~3 days / ~$5
- V32: ~2 days / ~$2
- **Total: ~11-12 days engineering + ~$17 budget.**

Session budget tracker: V25→V28 consumed ~18h / ~$20 over 4
cycles. V29-V32 projected 11-12 days + $17. Well within reasonable
runway for an "achieve 7/7 BEAT_BOTH" objective.

## Open question for the user

**Scope confirmation.** Ship the 4-cycle plan V29 → V32, or narrower?
My recommendation: approve V29 now (narrow, low-risk), defer
V30-V32 approval until V29 lands. V29 gives us the per-anchor
telemetry that tells us exactly where the architectural work needs
to land, which de-risks V30.

## Artifacts

- Claude strategic brief: `outputs/audits/v28/claude_strategic_path.md`
- Codex strategic brief: `outputs/codex_findings/v28_strategic_path/findings.md`
- This cross-review: `outputs/audits/v28/strategic_cross_review.md`
