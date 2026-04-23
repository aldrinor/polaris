# Restart Instructions — 2026-04-22 (V28 → V29 entry point)

## Autoloop V2 is in force (user directive 2026-04-21)

Full runbook: `state/autoloop_v2_runbook.md` (Codex-hardened).
Memory rule: `memory/autoloop_v2_audit_cross_review.md`.

## Current state (2026-04-22 23:14 UTC)

**V28 COMPLETE.** Cross-reviewed verdict: **3 BEAT_BOTH + 0 BEAT_ONE
+ 4 LOSE_BOTH** — NOT SHIPPABLE. Net ≥BEAT_ONE count REGRESSED 5 → 3
vs V27.

V28 artifacts:
- `outputs/full_scale_v28/clinical/clinical_tirzepatide_t2dm/` —
  report.md (3,837 words), bibliography.json (46 entries),
  contradictions.json (14), m44/m47/m50 telemetry JSONs
- `outputs/audits/v28/claude_deep_content_audit.md`
- `outputs/codex_findings/v28_deep_content_audit/findings.md`
- `outputs/audits/v28/cross_review.md`
- `outputs/audits/v28/gate_verdict.md`
- `outputs/audits/v28/strategic_cross_review.md` — V29-V32 roadmap

## Next action: V29 implementation

**Current handover**: `state/autoloop_handover_2026-04-22_v29_entry.md`

**User approved Strategy β** (2026-04-22) — convergent Claude+Codex
architectural roadmap:
- V29 foundation (narrow selector custody) — NOW
- V30 two-stage generator (Phase 1 primary skeleton + Phase 2 enrichment)
- V31 mechanism/narrative closure (primary clamp/PK extraction)
- V32 calibration (non-clinical slug validation)

### V29 scope (Codex-constrained)

1. **V29-a**: Selector hard-reservation in
   `src/polaris_graph/retrieval/evidence_selector.py`. Post-process
   selector output: for each anchor in `primary_trial_anchors`,
   scan live_corpus for `_m42e_detect_primary_for_anchor`-positive
   rows. If found in corpus but NOT in selected_rows, INSERT at
   position 0. Cap at 11 insertions.

2. **V29-b**: Generator-side named-trial injection in
   `src/polaris_graph/generator/multi_section_generator.py`. Extend
   `_m44_detect_primary_ev_ids` to accept live_corpus. When anchor's
   primary is in live_corpus but not evidence_pool, pull into
   evidence_pool + section ev_ids.

3. **V29-c**: Per-anchor custody telemetry. New field on
   MultiSectionResult: `v29_primary_custody_log`. Per anchor:
   found_in_live_corpus / found_ev_id / selected_into_pool /
   injected_into_section / direct_quote_chars /
   direct_quote_adequate / cited_in_verified_prose / citation_count.
   Orchestrator persists to `v29_primary_custody.json`.

   M-49 extension: `test_all_anchors_cited_in_verified_prose`
   asserts every configured anchor ends with
   `cited_in_verified_prose=true`.

**OUT OF V29 SCOPE**:
- Trial Summary table cell correction (V30/V31)
- M-47 validator relaxation (V30)
- Mechanism extraction architecture (V31)
- Prompt rewrites beyond primary-citation hints
- Two-stage generator rewrite (V30)

## Task graph (TaskList)

- #15 V29 fix plan → Codex plan review (ready to start) ← START HERE
- #12 V29-a selector custody (blocked on #15)
- #13 V29-b generator injection (blocked on #15)
- #14 V29-c custody telemetry (blocked on #15)
- #16 V29 sweep + audit cycle (blocked on #12+#13+#14)

## Quick resume (for wake-up)

1. Read `state/autoloop_handover_2026-04-22_v29_entry.md` first.
2. Task #15: write `outputs/audits/v28/fix_plan_v29.md` with V2 §5
   schema for V29-a/b/c.
3. Submit to Codex for plan pass-1 review.
4. On APPROVED: implement V29-a → tests → Codex audit → V29-b →
   tests → Codex audit → V29-c → tests → Codex audit.
5. Clone `scripts/run_full_scale_v28.py` → `run_full_scale_v29.py`.
6. Launch sweep. Monitor for manifest.
7. Post-manifest: M-49 preservation + V29 custody diagnostic +
   parallel Claude+Codex deep content audits → cross-review →
   gate verdict.
8. If SHIPPABLE (7/7 BEAT_BOTH): PushNotification, STOP.
9. If PARTIAL: V30 scope per strategic cross-review; await user.

## Autoloop rules in force

1. Every fix → Codex code audit before sweep launch
2. V29 fix plan → Codex plan review before implementation
3. V29 sweep launches autonomously when all code Codex-READY
4. On manifest: M-49 preservation + deep content audits
5. §7 halt triggers surface to user — do NOT silently continue

No cycle cap. Stop criterion: BEAT-BOTH, not threshold-only.

## Files the autoloop consults

- `docs/todo_list.md` — backlog, ACTIVE at top (V29-V32 roadmap)
- `state/autoloop_handover_2026-04-22_v29_entry.md` — this cycle
- `state/compare_chatgpt_dr.txt`, `state/compare_gemini_dr.txt` —
  competitor baselines
- `outputs/audits/v28/strategic_cross_review.md` — V29-V32 plan
- `logs/session_log.md`, `logs/bug_log.md` — durable state

## Budget check

Session wall-clock at V28 completion: ~36h since V25 start.
V29 projected +12h. Budget cap is $100 (V28 session total ~$20).
V29-V32 total projected: 11-12 days engineering + $17 + 4 cycles.

## §7 halt-trigger history (for audit)

2026-04-22 V28 fired triggers #7 (regression without compensating
same-axis BB) and #10 (net ≥BO count regressed 5 → 3). User surfaced,
reviewed strategic briefs, approved Strategy β. V29 is user-approved
continuation.

---

## Archived — 2026-04-21 V25 launch

V25 launch handover at
`state/autoloop_handover_2026-04-21_v25_v2_launch.md`.
V25 → V26 → V27 → V28 cycle arc in session_log.md + commit history
under branch PL-honest-rebuild-phase-1.
