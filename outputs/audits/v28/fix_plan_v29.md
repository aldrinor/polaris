# V28 → V29 Fix Plan (Strategy β cycle 1 of 4)

**Scope context**: Cycle 1 of the Claude + Codex convergent Strategy β
roadmap (`outputs/audits/v28/strategic_cross_review.md`). Narrow
custody fix per Codex's lower-verdict-controls discipline:
selector + generator + telemetry ONLY. No cosmetic fixes. No
prompt rewrites. No two-stage rewrite (V30 scope).

**V28 baseline**: 3 BEAT_BOTH + 0 BEAT_ONE + 4 LOSE_BOTH
cross-reviewed. Net ≥BEAT_ONE count REGRESSED 5 → 3 vs V27.

**V29 target**: 4-5 BB + 2-3 BO + 0-1 LB. Lift Dims 1 (Citations),
4 (Claim frames), 5 (Structural depth) from LOSE_BOTH to
≥BEAT_ONE. Dim 7 (Narrative depth) may still lag pending V30/V31.

**Stop criterion (unchanged)**: BEAT-BOTH ChatGPT DR + Gemini
3.1 Pro DR on all 7 dimensions.

## Dimension-preservation statement (whole plan)

- **Dim 2 Regulatory BEAT_BOTH**: preserved. V29 does not touch
  `regulatory_expander`, clinical.yaml regulatory_anchors, M-42d
  HC quota, or M-48 population-scope labels. No risk of regression.
- **Dim 3 Jurisdictional BEAT_BOTH**: preserved. Same infrastructure
  as Dim 2. No touch.
- **Dim 6 Contradictions BEAT_BOTH**: preserved. V29 does not touch
  the contradiction detector, disclosure section, or tier-distribution
  reporting. No touch.
- **Per-sentence [ev_id] provenance**: preserved. strict_verify gate
  unchanged. V29 only changes WHICH evidence rows reach the
  generator; it does not relax verification of what the generator
  writes.

## Items (Codex-recommended implementation order)

### M-51 — Selector hard-reservation of anchor-matched primaries (V29-a)

**Causal stage**:
`src/polaris_graph/retrieval/evidence_selector.py` —
`select_evidence_for_generation` post-process pass.

**Prior mechanism gap**: V28 failure analysis (cross-review + Codex
audit) verified that SURPASS-4 Del Prato Lancet and SURPASS-CVOT
Nicholls records are present in V28's `live_corpus_dump.json` but
ABSENT from `bibliography.json`. The selector's tier-balanced
allocation dropped them in favor of higher-relevance-scored
meta-analyses and post-hocs. Existing M-42e primary floor reserves
a few T1 slots per anchor BUT only via `by_tier.get("T1", [])`
scan, which is bounded by T1 quota. When multiple high-scoring T1
non-primary rows outrank the primary, the primary is still dropped.

**Fix**:
1. After the existing tier-balanced + M-42e + M-42c + M-42d
   reservation passes complete, add a final **unconditional
   anchor-primary post-process**:
   ```python
   # V29-a pseudocode
   if primary_trial_anchors:
       selected_ids = {id(item) for item in selected}
       insertions = 0
       cap = len(primary_trial_anchors)
       for anchor in primary_trial_anchors:
           if insertions >= cap:
               break
           # Scan full scored pool (not just T1 quota slice)
           for item in scored:
               if id(item) in selected_ids:
                   continue
               if _m42e_detect_primary_for_anchor(item[3], anchor):
                   selected.insert(0, item)
                   selected_ids.add(id(item))
                   insertions += 1
                   break
       # Trim back to max_rows by removing lowest-ranked non-reserved
       # rows (NOT reserved primaries). Cap respected.
   ```
2. If the post-process would push `len(selected) > max_rows`, pop
   from the END of `selected` — but skip any popped row that is
   itself an M-42e primary (don't reject a reserved primary to make
   room for another reserved primary; cap at `len(anchors)` prevents
   this case anyway).
3. Emit telemetry note: `m51_anchor_primary_custody matched=N
   inserted=M cap=K`.

**Preservation risks**:
- Could push `len(selected) > max_rows` temporarily. Mitigation:
  cap insertions at `len(anchors)` and trim non-reserved rows after.
- Could displace legitimately high-scored non-primary T1 rows.
  Mitigation: `max_rows` is configurable (PG_LIVE_MAX_EV_TO_GEN=300
  in V28 launcher); displacing up to 11 non-primary rows is
  acceptable trade-off to ensure pivotal coverage.

**Acceptance criteria**:
Given a live corpus with SURPASS-4 Del Prato Lancet primary row + 50
other T1 rows + `primary_trial_anchors=["SURPASS-4", ...]`:
- `selected_rows` contains the Del Prato row.
- Telemetry note includes `m51_anchor_primary_custody matched=1
  inserted=1`.
- Backward-compat: when `primary_trial_anchors=None` or empty,
  selector output is byte-identical to V28 (no regression).

**Test coverage**:
`tests/polaris_graph/test_m51_selector_custody.py`:
1. Fixture: pool has SURPASS-4 primary + 50 non-primary T1. Anchor
   includes SURPASS-4. Assert selected contains SURPASS-4 at
   position 0.
2. Fixture: pool has SURPASS-4 + SURPASS-CVOT primaries. Anchors
   include both. Assert both inserted.
3. Fixture: pool has no SURPASS-4 row. Anchors include SURPASS-4.
   Assert no insertion (no-op when primary not in corpus).
4. Fixture: SURPASS-4 already selected via M-42e. Assert no
   duplicate insertion.
5. Fixture: 11 anchors, 11 primaries in pool. Assert exactly 11
   insertions (cap enforced).
6. Fixture: no anchors configured. Assert V28-identical output.

**Classification**: `root_cause`. Addresses the exact V28 failure
point — primary in corpus but not selected.

### M-52 — Generator-side injection from live_corpus when pool lacks primary (V29-b)

**Causal stage**:
`src/polaris_graph/generator/multi_section_generator.py` —
`_m44_detect_primary_ev_ids` + injection loop in
`generate_multi_section_report`.

**Prior mechanism gap**: M-44 detects primaries in `evidence_pool`
only. If the selector's output (passed to the generator as the
`evidence` argument) is missing a primary, M-44's injection is a
no-op for that anchor. M-51 should prevent this, but belt-and-
suspenders: the generator should itself pull from the full
retrieved corpus when the section needs it.

**Fix**:
1. Extend `generate_multi_section_report` signature:
   ```python
   async def generate_multi_section_report(
       *,
       ...
       live_corpus: list[dict[str, Any]] | None = None,
       ...
   ) -> MultiSectionResult:
   ```
2. In orchestrator (`scripts/run_honest_sweep_r3.py`), pass
   `live_corpus=retrieval.evidence_rows` (the full retrieved pool,
   not just the selector output).
3. Extend `_m44_detect_primary_ev_ids` to scan both `evidence_pool`
   AND `live_corpus` when the latter is non-None. If a primary is
   in live_corpus but not evidence_pool:
   - Assign a fresh ev_id (prefix `ev_from_corpus_`)
   - Add the row to `evidence_pool`
   - Include it in returned `primary_ev_ids_by_anchor` dict
4. Existing injection loop in `generate_multi_section_report`
   (lines ~2200) picks up the new ev_ids and injects into section
   plans via `_m44_inject_primaries_into_outline`.
5. Log new action type `injected_from_corpus` in
   `m44_injection_log` entries.

**Preservation risks**:
- evidence_pool mutation. Risk: strict_verify uses evidence_pool as
  its source-of-truth. New rows added here MUST carry valid
  `direct_quote` + `source_url` + `tier` fields for strict_verify
  to work. Mitigation: live_corpus rows already have these fields;
  no schema transformation needed.
- ev_id collisions. Mitigation: prefix `ev_from_corpus_` distinguishes
  these from retrieval-assigned `ev_NNN` IDs.

**Acceptance criteria**:
Given `evidence_pool` WITHOUT SURPASS-CVOT Nicholls but
`live_corpus` WITH it, and `primary_trial_anchors=["SURPASS-CVOT"]`:
- After M-52 injection, `evidence_pool` contains the Nicholls row.
- `m44_injection_log` has an entry with `action="injected_from_corpus"`
  for the anchor.
- Section plans for Safety / Cardiovascular sections have the new
  ev_id in their `ev_ids` list.

**Test coverage**:
`tests/polaris_graph/test_m52_generator_corpus_injection.py`:
1. Fixture: evidence_pool lacks primary, live_corpus has it. Assert
   row pulled + injected.
2. Fixture: both have primary. Assert no duplicate (existing
   `already_present` path).
3. Fixture: live_corpus=None. Assert V28-identical behavior (backward-compat).
4. Fixture: primary has thin direct_quote (<100 chars). Assert
   still pulled (strict contract is generator-level, not injection-level;
   the subsequent M-44 validator / M-50 selector will handle thin-quote).

**Classification**: `root_cause` (redundant with M-51 as a safety
net; both fire if V29 custody works correctly).

### M-53 — Per-anchor custody telemetry (V29-c, Codex-required)

**Causal stage**:
`src/polaris_graph/generator/multi_section_generator.py` +
`scripts/run_honest_sweep_r3.py`. Computed at end of
`generate_multi_section_report`.

**Prior mechanism gap**: V28 telemetry (M-44 injection_log, M-50
subsections, refetch diagnostics) tells us what code paths FIRED,
but not which anchors made it all the way through. When V29 runs,
we need to know for each configured anchor:
- Did retrieval find the primary?
- Did the selector preserve it?
- Did the generator inject it (if needed)?
- Was the direct_quote adequate?
- Did the verified prose cite it?

Codex: "Add a gate that reports, per anchor, whether the primary
was found, selected, injected, quote-adequate, and cited in prose.
... If SURPASS-4 and SURPASS-CVOT are already in live_corpus and
still absent from the report after V29, the architecture is
failing at the exact custody boundary that must be fixed before
7/7 is credible."

**Fix**:
1. New MultiSectionResult field:
   ```python
   v29_primary_custody_log: list[dict[str, Any]] = field(default_factory=list)
   ```
2. Computed AFTER section generation + strict_verify completes.
   For each anchor in `primary_trial_anchors`:
   ```python
   found_in_live_corpus = any(
       _m42e_detect_primary_for_anchor(row, anchor)
       for row in (live_corpus or [])
   )
   found_row = ... # first matching row
   selected_into_pool = found_row and found_row["evidence_id"] in evidence_pool
   injected_into_section = ...  # check m44_injection_log
   direct_quote_chars = len(found_row.get("direct_quote", "")) if found_row else 0
   direct_quote_adequate = direct_quote_chars >= 100
   cited_in_verified_prose = any(
       f"[{bibliography_num_for(ev_id)}]" in sr.verified_text
       for sr in section_results
       for ev_id in sr.biblio_slice
       if section_ev_id_matches_anchor(ev_id, anchor)
   )
   citation_count = sum(...)
   ```
3. Orchestrator persists
   `outputs/.../v29_primary_custody.json` per sweep:
   ```json
   [
     {
       "anchor": "SURPASS-2",
       "found_in_live_corpus": true,
       "found_ev_id": "ev_0217",
       "selected_into_pool": false,
       "injected_into_section": "Efficacy",
       "direct_quote_chars": 1842,
       "direct_quote_adequate": true,
       "cited_in_verified_prose": true,
       "citation_count": 3
     },
     ...
   ]
   ```

**Preservation risks**: None. Pure telemetry; does not change
generation behavior.

**Acceptance criteria**:
Given V29 sweep with 11 configured anchors, the diagnostic file:
- Contains exactly 11 entries.
- Every entry has all 8 required fields populated.
- For anchors where `cited_in_verified_prose=false`, investigation
  in the test suite can identify which custody step failed by
  scanning the earlier boolean fields.

**Test coverage**:
`tests/polaris_graph/test_m53_custody_telemetry.py`:
1. Fixture: 3 anchors, all paths succeed. Assert 3 entries all
   `cited_in_verified_prose=true`.
2. Fixture: 1 anchor, primary absent from live_corpus. Assert
   `found_in_live_corpus=false` + all downstream fields false.
3. Fixture: 1 anchor, primary selected but thin quote. Assert
   `direct_quote_adequate=false`.
4. Fixture: 1 anchor, injected but not cited. Assert
   `injected_into_section` populated + `cited_in_verified_prose=false`.

Plus M-49 extension:
`tests/polaris_graph/test_m49_v29_preservation.py`
new test `test_all_anchors_cited_in_verified_prose`:
Asserts that `v29_primary_custody.json` has every entry with
`cited_in_verified_prose=true`. Fails the V29 sweep if any anchor
didn't make it through.

**Classification**: `preservation_guard`. Not root_cause (M-51 +
M-52 are the root-cause fixes); not band_aid (this diagnostic is
required by Codex for V30 de-risking).

## Per-item summary table

| Item | Stage | Addresses | Classification | V29 scope |
|---|---|---|---|---|
| M-51 | Selector post-process | Primary-in-corpus-not-selected | root_cause | in |
| M-52 | Generator injection | Belt-and-suspenders + ev_id continuity | root_cause | in |
| M-53 | Custody telemetry | Codex-required diagnostic for V30 planning | preservation_guard | in |

**Not in V29 scope** (Codex discipline, deferred to V30/V31):
- Trial Summary table cell correction (cosmetic until custody works)
- M-47 validator relaxation (wait for V29 custody baseline)
- Mechanism extraction architecture (V31)
- Two-stage generator rewrite (V30)
- Any prompt rewrites beyond M-44's existing hint

## Implementation order (Codex-recommended)

1. **M-51** (selector is the bottom of the pipeline; start here)
   - Impl + tests + Codex code audit
2. **M-52** (depends on M-51 telemetry for verification)
   - Impl + tests + Codex code audit
3. **M-53** (telemetry synthesizes M-51 + M-52 signals)
   - Impl + tests + Codex code audit
4. Clone `run_full_scale_v28.py` → `run_full_scale_v29.py` (no env changes)
5. Launch V29 sweep
6. Post-manifest: M-49 preservation (with new
   `test_all_anchors_cited_in_verified_prose`) + parallel deep
   content audits

## Expected V29 outcome

| Dim | V28 | V29 projection | Why |
|---|:-:|:-:|---|
| 1. Citations | LOSE_BOTH | **BEAT_ONE** | M-51/52 ensure primary-trial papers reach bibliography |
| 2. Regulatory | BEAT_BOTH | BEAT_BOTH | Preserved (no touch) |
| 3. Jurisdictional | BEAT_BOTH | BEAT_BOTH | Preserved (no touch) |
| 4. Claim frames | LOSE_BOTH | **BEAT_ONE** | Primary ETDs now citable in prose |
| 5. Structural depth | LOSE_BOTH | **BEAT_ONE** | M-50 subsections now candidates for SURPASS-2/4/CVOT/SURMOUNT-2 (the target set) |
| 6. Contradictions | BEAT_BOTH | BEAT_BOTH | Preserved |
| 7. Narrative depth | LOSE_BOTH | LOSE_BOTH or BEAT_ONE | Depends on whether Mechanism section's generator can extract Thomas clamp findings without the V30 two-stage architecture. Likely still LOSE_BOTH; V31 is the dedicated closure cycle. |

**Projected aggregate**: 3 BB + 3-4 BO + 0-1 LB. Upgrade from V28.
If Dim 7 lifts, 3 BB + 4 BO + 0 LB matches V27 baseline without any
regression. V30 + V31 target the residual gap.

## Plan review ping-pong budget

V2 §7 trigger #11 allows up to 3 pass-N plan reviews per item.
V29 = first pass. Budget intact.

## Questions for Codex plan review

1. **M-51 cap mechanics**: does capping at `len(anchors)=11` make
   sense, or should it be a configurable env knob (e.g. default 11,
   allow operator override)?
2. **M-52 ev_id prefix `ev_from_corpus_`**: collision-free with
   existing `ev_NNN`? Preferable to use the existing evidence_id
   from live_corpus if present (avoids invalidating any cached
   metadata)?
3. **M-53 quote adequacy threshold**: `≥100 chars` matches M-42b
   refetch threshold. Should V29 use the same threshold or a
   different one specific to custody (e.g. ≥500 chars for full-
   frame ETD extraction)?
4. **M-51 backward-compat test**: should I add explicit fixture
   verifying V28 selector behavior is byte-identical when anchors
   are empty? (I planned test #6 but want to confirm the shape.)
5. **Out-of-scope confirmation**: please confirm that V29 explicitly
   defers trial-table cell correction, M-47 relaxation, two-stage
   rewrite, and mechanism extraction — these are all V30/V31 scope
   per strategic cross-review, right?

## Next step per V2 runbook

Submit this plan to Codex for step 6 pass-1 plan review at
`.codex/v29_fix_plan_review_pass1_brief.md`.

On APPROVED or CONDITIONAL-no-blockers: begin M-51 implementation.
