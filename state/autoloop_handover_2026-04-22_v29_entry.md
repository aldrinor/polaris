# POLARIS Autoloop V2 — V29 Entry Handover (2026-04-22 23:45 UTC)

Previous handovers:
- `state/autoloop_handover_2026-04-22_v28_launch.md` — V28 launch
- `state/autoloop_handover_2026-04-22_v26_launch.md` — V26 launch
- `state/autoloop_handover_2026-04-21_v25_v2_launch.md` — V25 launch

## Stop condition (unchanged)

BEAT-BOTH ChatGPT 5.4 Pro DR + Gemini 3.1 Pro DR on 7 dimensions,
cross-reviewed content audit (line-by-line PRISMA/AMSTAR-2/GRADE).

## V28 outcome (just closed)

**Cross-reviewed scoreboard**: 3 BEAT_BOTH + 0 BEAT_ONE + 4 LOSE_BOTH.
NOT SHIPPABLE. Net ≥BEAT_ONE count REGRESSED 5 → 3 vs V27.

V28 report artifacts:
`outputs/full_scale_v28/clinical/clinical_tirzepatide_t2dm/`
- report.md: 3,837 words, 6 content sections
- bibliography.json: 46 entries
- contradictions.json: 14 items
- m44/m47/m50/refetch telemetry JSONs all populated
- Manifest status: partial_qwen_advisory, release_allowed=false

V28 audit artifacts (`outputs/audits/v28/`):
- claude_deep_content_audit.md
- cross_review.md (lower-verdict-controls adjudication)
- gate_verdict.md (NOT SHIPPABLE + V29 candidates)
- claude_strategic_path.md
- strategic_cross_review.md (Claude + Codex converge on β)

Codex: `outputs/codex_findings/v28_deep_content_audit/findings.md` +
`outputs/codex_findings/v28_strategic_path/findings.md`

## §7 halt triggers fired on V28

1. **Trigger #7**: REGRESSION dimension V27 → V28 without compensating
   same-axis BEAT_BOTH. Dim 1 (Citations) and Dim 7 (Narrative depth)
   both regressed BEAT_ONE → LOSE_BOTH.
2. **Trigger #10**: Net dimensional health regressed 5 → 3 ≥BEAT_ONE
   count.

User surfaced per V2 protocol. User approved Strategy β architectural
roadmap after reviewing both auditors' strategic briefs.

## Strategy β (convergent Claude + Codex plan, user-approved)

| Cycle | Scope | Projected outcome | Cost |
|---|---|---|---|
| **V29** | Selector custody + generator injection + per-anchor telemetry (CURRENT) | 4-5 BB + 2-3 BO + 0-1 LB | ~12h / $5 |
| V30 | Two-stage generator: Phase 1 primary-only skeleton + Phase 2 enrichment | 5-6 BB + 1-2 BO + 0 LB | ~5d / $5 |
| V31 | Mechanism/Narrative closure: primary clamp/PK extraction | 7/7 BEAT_BOTH | ~3d / $5 |
| V32 | Calibration on non-clinical slug (Codex addition — prevent tirzepatide hardcoding masquerading as architecture) | validation | ~2d / $2 |

## V29 scope (Codex-constrained via lower-verdict-controls)

### V29-a: Selector hard-reservation

**File**: `src/polaris_graph/retrieval/evidence_selector.py`

**Change**: After `select_evidence_for_generation` tier-balancing
completes, post-process the selected list:

```python
# Pseudocode
for anchor in primary_trial_anchors:
    primary_row = find_in_live_corpus_matching_anchor(anchor, live_corpus)
    if primary_row and primary_row not in selected_rows:
        selected_rows.insert(0, primary_row)  # highest priority
    if insertions >= len(primary_trial_anchors):
        break  # cap
```

Uses existing `_m42e_detect_primary_for_anchor(row, anchor)` detector
(shared with M-50 candidate selection + M-44 injection).

**Caveat**: The selector currently receives `evidence_rows` not
`live_corpus`. V29-a may require threading `live_corpus` through as
a new parameter from the orchestrator.

### V29-b: Generator-side injection

**File**: `src/polaris_graph/generator/multi_section_generator.py`

**Change**: Extend `_m44_detect_primary_ev_ids` to accept an
optional `live_corpus` argument. When anchor's primary is in
live_corpus but not evidence_pool:
1. Add the row to evidence_pool with fresh ev_id.
2. Inject the ev_id into appropriate section's ev_ids per
   `_m44_section_matches_anchor` affinity.
3. Record in `m44_injection_log` with action=`injected_from_corpus`.

### V29-c: Per-anchor custody telemetry

**File**: `src/polaris_graph/generator/multi_section_generator.py`
+ `scripts/run_honest_sweep_r3.py`

**Change**:
1. New `MultiSectionResult.v29_primary_custody_log: list[dict]`.
2. Compute per anchor (after section generation completes):
   ```json
   {
     "anchor": "SURPASS-2",
     "found_in_live_corpus": true,
     "found_ev_id": "ev_0217",
     "selected_into_pool": false,
     "injected_into_section": "Efficacy",
     "direct_quote_chars": 1842,
     "direct_quote_adequate": true,
     "cited_in_verified_prose": false,
     "citation_count": 0
   }
   ```
3. Orchestrator writes to `v29_primary_custody.json` per sweep run.
4. M-49 extension (`test_m49_v28_preservation.py` → rename to
   `test_m49_v29_preservation.py`): new test
   `test_all_anchors_cited_in_verified_prose` asserts every
   anchor's `cited_in_verified_prose=true`.

### Out of V29 scope (per Codex discipline)

- Trial Summary table cell correction (deferred — cosmetic)
- M-47 validator relaxation
- Mechanism extraction architecture
- Two-stage generator rewrite
- Any prompt rewrites beyond primary-citation hints

## V29 task graph (TaskList state)

- **#15** V29 fix plan → Codex plan review (ready, no blockers)
- **#12** V29-a selector custody (blocked on #15)
- **#13** V29-b generator injection (blocked on #15)
- **#14** V29-c custody telemetry (blocked on #15)
- **#16** V29 sweep + audit cycle (blocked on #12+#13+#14)

## V29 execution plan

1. Task #15: write `outputs/audits/v28/fix_plan_v29.md` with V2 §5
   schema per item (causal_stage / prior_mechanism_gap /
   preservation_risks / acceptance_criteria / test_coverage /
   classification). Submit to Codex for plan pass-1 review at
   `.codex/v29_fix_plan_review_pass1_brief.md`.

2. On APPROVED (or CONDITIONAL-no-blockers): begin V29-a.
   - Read evidence_selector.py + understand live_corpus flow
   - Implement V29-a post-process
   - Unit tests for: (a) anchor found in corpus, inserted;
     (b) anchor found in corpus AND selected_rows, no duplicate
     insert; (c) anchor not in corpus, no-op; (d) cap enforcement
   - Codex code audit for V29-a
   - On READY: V29-b

3. V29-b implementation:
   - Extend `_m44_detect_primary_ev_ids` signature
   - Add live_corpus arg passthrough from orchestrator
   - Unit tests for: (a) primary in corpus not in pool, pulled;
     (b) primary in both pool and corpus, no duplicate; (c) injection
     logged with `injected_from_corpus` action
   - Codex code audit
   - On READY: V29-c

4. V29-c implementation:
   - Write custody-log assembler function
   - MultiSectionResult field + orchestrator persistence
   - M-49 extension
   - Unit tests for custody-log schema + extended M-49 test
   - Codex code audit

5. Clone `scripts/run_full_scale_v28.py` → `run_full_scale_v29.py`.
   No env changes expected (V28 env is V27 env + PG_LIVE_MAX_EV_TO_GEN=300
   already applied).

6. Launch V29 sweep in background. Arm Monitor with 3 exit conditions
   (manifest / PID death / 10-min log-idle stuck detector).

7. Post-manifest pipeline:
   - Run M-49 preservation suite (extended with V29-c custody test).
     If any anchor's `cited_in_verified_prose=false`, halt and
     diagnose which custody step failed (the 5-boolean telemetry
     will tell us precisely).
   - If preservation passes: launch parallel Claude + Codex deep
     content audits per V2 step 2a/2b.
   - Cross-review + gate verdict.

8. Outcome gating:
   - SHIPPABLE (7/7 BEAT_BOTH): PushNotification. STOP.
   - PARTIAL with improvement: write V30 scope per strategic
     cross-review. Surface to user.
   - PARTIAL without improvement: investigate V29 custody telemetry
     for which step failed. Candidates: retrieval (anchor didn't
     land in live_corpus after all), selector (V29-a didn't
     insert), generator (V29-b didn't inject), strict_verify
     (primary cited but prose didn't survive verify).

## Halt triggers for V29

Standard V2 §7 triggers apply. Plus V29-specific:
- If V29 custody telemetry shows ≥7 of 11 anchors with
  `cited_in_verified_prose=true` but cross-reviewed scoreboard
  shows regression vs V27 → Codex was right that this is
  pipeline-ordering; V30 two-stage rewrite is mandatory.
- If V29 telemetry shows <7 of 11 `cited_in_verified_prose=true`
  → V29 fix itself failed; investigate which custody step.

## Budget

- V25→V28 cumulative: ~20h session + ~$20 aggregate spend
- V29 projected: +12h + $5
- V29-V32 total: 11-12 days engineering + $17 + 4 sweep cycles
- V2 §7 caps: 24h per cycle (V28 was 2h51m — well within); $100
  aggregate (currently ~$20 used)

## Autoloop continues autonomously

User said "follow tightly on the next run". Claude-side policy:
- V29 fix plan completion → submit to Codex WITHOUT user check-in
- On Codex READY → implement V29-a/b/c WITHOUT user check-in
- On all READY → launch V29 sweep WITHOUT user check-in
- On manifest → audits → cross-review → gate verdict WITHOUT user
  check-in
- ONLY surface to user on: §7 halt triggers OR SHIPPABLE outcome

Monitor tool = primary wake signal. ScheduleWakeup = fallback
heartbeat (1200-1800s).

## Files the autoloop consults on wake

1. `CLAUDE.md` (project) + user's global CLAUDE.md
2. `docs/todo_list.md` — ACTIVE V29-V32 section at top
3. `state/restart_instructions.md` — Quick resume steps
4. `state/autoloop_handover_2026-04-22_v29_entry.md` — this file
5. `state/compare_chatgpt_dr.txt`, `state/compare_gemini_dr.txt` —
   competitor baselines
6. `outputs/audits/v28/strategic_cross_review.md` — V29-V32 plan
7. `logs/session_log.md` — 2026-04-22 V28 close entry appended
8. `logs/bug_log.md` — BUG-V28-PRIMARY-CUSTODY entry added at top

All durable state is in repo. Next session continues from here
without loss of context.
