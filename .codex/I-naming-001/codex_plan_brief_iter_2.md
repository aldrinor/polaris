HARD ITERATION CAP: 5 per document. This is iter 2 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

# I-naming-001 — Rename BPEI plan iter 2 (P1 + P2 fixes)

## Iter-1 P1 resolutions

### P1-1 — missed `tests/v6/test_ambiguity_detector.py` import

**Confirmed.** `tests/v6/test_ambiguity_detector.py:10` is `from polaris_v6.bpei.ambiguity_detector import (...)`. After `git mv src/polaris_v6/bpei → src/polaris_v6/ambiguity_detector`, this import breaks. Plan iter 2 explicitly adds this file to the import-update list.

### P1-2 — user-visible BPEI in web/app UI (the actual point of the rename)

**Confirmed via grep.** 7 user-facing surfaces:

```
web/app/dashboard/page.tsx:394   "Disambiguation needed (BPEI guard)"
web/app/generation/page.tsx:61   "POLARIS chains the full BPEI spine: scope discovery (slice 001), …"
web/app/generation/page.tsx:91   "Slice 003 (BPEI generator + strict-verify)"
web/app/intake/page.tsx:47       "the BPEI front half: refusal-bait detection, scope classification …"
web/app/intake/page.tsx:61       "Slice 001 (BPEI front half)"
web/app/retrieval/page.tsx:79    "Slice 002 (BPEI retrieval half)"
web/lib/api.ts:827               "/** Build + download a GPG-signed audit bundle for the given BPEI chain. */"
```

These are what Carney would literally see. Iter-2 plan extends scope to rename UI copy.

**Replacement convention** (proposed; Codex confirm or reject):
- `BPEI guard` → `ambiguity guard`
- `BPEI spine` → `research pipeline`
- `BPEI front half` → `scope + intake`
- `BPEI retrieval half` → `retrieval`
- `BPEI generator + strict-verify` → `generator + strict-verify` (drop the BPEI prefix entirely)
- `BPEI chain` → `research chain`

Rationale: "BPEI" in these contexts is being used to mean "the whole orchestration pipeline" (scope → intake → retrieval → generation → verify). "Research pipeline" / "research chain" is the standard term Carney's office would understand.

## Iter-1 P2 resolutions

### P2-1 — preserve literal BPEI test probes

**Acknowledged.** Test fixtures that use the literal string `"What is BPEI?"` or `"BPEI"` as INPUT data (simulating the original 2026-04-30 incident probe) MUST stay verbatim. Renaming them would lose the regression value.

Specifically preserve as-is:
- Any test fixture file under `tests/v6/fixtures/` containing `"BPEI"` as a query input
- Any e2e spec under `web/tests/e2e/` that types `"BPEI"` into a search box as an adversarial test
- Memory file `bpei_phantom_completion_lessons.md` (user-level, ~/.claude/, not in repo)

Distinguish: **rename "BPEI" as a NAME for a feature**, **preserve "BPEI" as TEST INPUT STRING**.

### P2-2 — memory file is user-level, not repo

**Acknowledged.** `memory/bpei_phantom_completion_lessons.md` lives at `~/.claude/projects/C--POLARIS/memory/bpei_phantom_completion_lessons.md`, not in this repo. Stage-4 step in iter-1 plan dropped (out of repo scope). Instead, I'll append a note to `state/polaris_restart/issue_breakdown.md` documenting the rename + cross-referencing the memory file for the incident origin.

### P2-3 — docs grep too narrow

**Confirmed.** 20 doc files have BPEI references:

```
docs/benchmark/scoring_rubric.md
docs/blocked/blocked_on_user_action_tracker.md
docs/blockers.md
docs/carney_delivery_plan_v5_1_redline.md       (HISTORICAL — pre-v6.2)
docs/carney_delivery_plan_v5_draft.md            (HISTORICAL)
docs/carney_delivery_plan_v6_2.md                (CURRENT — active mission plan)
docs/carney_delivery_plan_v6_draft.md            (HISTORICAL — superseded by v6_2)
docs/carney_handover/5min_video_script.md        (Carney-facing!)
docs/shippable_plan_v2_draft.md                  (HISTORICAL)
docs/shippable_plan_v3_draft.md                  (HISTORICAL)
docs/shippable_plan_v4_draft.md                  (HISTORICAL)
docs/substrate_audit_2026-05-01.md
docs/task_acceptance_matrix.yaml
docs/v6_substrate_audit_2026-05-01.md
docs/walkthroughs/1.8/briefing.md
docs/walkthroughs/1.8/recording_template.md
docs/walkthroughs/1.8/test_inputs.md              (TEST INPUTS — preserve literal probes)
docs/walkthroughs/2B.7/test_inputs.md             (TEST INPUTS — preserve)
docs/walkthroughs/2C.6/briefing.md
docs/walkthroughs/2C.6/test_inputs.md             (TEST INPUTS — preserve)
```

Patch policy:
- **CURRENT docs** (carney_delivery_plan_v6_2.md, carney_handover/5min_video_script.md, blockers.md, blocked/blocked_on_user_action_tracker.md, substrate_audit_2026-05-01.md, v6_substrate_audit_2026-05-01.md, task_acceptance_matrix.yaml, benchmark/scoring_rubric.md, walkthroughs/{1.8,2B.7,2C.6}/{briefing,recording_template}.md): rename BPEI references using the convention above.
- **HISTORICAL docs** (carney_delivery_plan_v5_*, carney_delivery_plan_v6_draft, shippable_plan_v2_3_4_draft): leave as-is (historical record, superseded by v6_2).
- **TEST INPUT files** (walkthroughs/*/test_inputs.md): preserve verbatim `BPEI` strings (these are adversarial probe inputs).

### P3-1 — `src/polaris_v6/pipeline.py` doesn't exist

**Acknowledged.** The pycache hit was misleading; original `pipeline.py` was renamed/removed. Drop from list.

### P3-2 — `docs/file_directory.md` has no current BPEI hit

**Acknowledged.** Drop from list (no edit needed in this PR).

## Iter-1 broader naming-audit follow-ups (recorded)

Codex flagged additional cryptic names. Per acceptance criteria these are OUT-OF-SCOPE for this PR; they get follow-up issues:

| File / dir | Issue | Severity | Suggested rename | Follow-up issue |
|---|---|---|---|---|
| `src/polaris_graph/audit_ir/v30_runner.py` | Version-only | P3 | `honest_sweep_job_runner.py` | I-naming-002 |
| `src/polaris_graph/v30_sweep_integration.py` | Version-only | P3 | `honest_sweep_integration.py` | I-naming-003 |
| `src/polaris_graph/generator2/` | Sibling-numbered | **P2** | `clinical_generator/` | I-naming-004 |
| `src/polaris_graph/retrieval2/` | Sibling-numbered | **P2** | `clinical_retrieval/` | I-naming-005 |
| `src/polaris_graph/synthesis/peptide_flow.py` | Chemistry metaphor | **P2** | `narrative_flow_analyzer.py` | I-naming-006 |
| `src/polaris_graph/synthesis/disulfide_bridge.py` | Chemistry metaphor | **P2** | `cross_section_source_consistency.py` | I-naming-007 |
| `src/polaris_graph/synthesis/covalent_binder.py` | Chemistry metaphor | **P2** | `claim_evidence_binding.py` | I-naming-008 |
| `src/polaris_graph/synthesis/ionic_rebalancer.py` | Chemistry metaphor | **P2** | `evidence_section_affinity.py` | I-naming-009 |
| `src/polaris_graph/graph_v4.py` | Version-only | P3 | `pipeline_a_ui_adapter.py` | I-naming-010 |

Plan: I'll create the 9 follow-up issues on GH after BPEI ship, per Codex's `followup_pr` adjudication.

## Final scope of this PR

### Stage 1 — Dir rename
```
git mv src/polaris_v6/bpei src/polaris_v6/ambiguity_detector
```

### Stage 2 — Python import + comment updates (~20 files)

**Imports (will break if not updated):**
- `src/polaris_v6/api/ambiguity.py` line 16
- `tests/v6/test_ambiguity_detector.py` line 10 ★ ADDED IN ITER 2

**Comment/docstring updates (`BPEI ambiguity detector` → `ambiguity detector`):**
- `src/polaris_v6/ambiguity_detector/__init__.py` (3 occurrences; preserve ONE commemorative footnote)
- `src/polaris_v6/ambiguity_detector/ambiguity_detector.py` (1)
- `src/polaris_v6/memory/__init__.py` (1)
- `src/polaris_v6/api/ambiguity.py` docstring (1)
- `src/polaris_graph/api/audit_bundle_route.py` (1)
- `src/polaris_graph/api/intake.py` (1)
- `src/polaris_graph/api/intake_route.py` (1)
- `src/polaris_graph/api/__init__.py` (1)
- `src/polaris_graph/audit_bundle/bundle_schema.py` (1)
- `src/polaris_graph/audit_bundle/manifest_builder.py` (1)
- `src/polaris_graph/intake/cluster_labeler.py` (1)
- `src/polaris_graph/intake/disambiguation_clusterer.py` (1)
- `src/polaris_graph/intake/__init__.py` (1) ★ ADDED IN ITER 2
- `src/polaris_graph/scope/scope_decision.py` (1)
- `tests/e2e/frontend_replay_smoke.py` (1)
- `tests/polaris_graph/audit_bundle/test_bundle_builder.py` (1)
- `tests/polaris_graph/followup/test_agent.py` (1)
- `tests/polaris_graph/golden/test_slice_004_goldens.py` (1)
- `tests/v6/test_ambiguity_detector.py` (1 — comment, separate from import)
- `tests/v6/test_api_ambiguity.py` (1)
- `tests/v6/test_run_benchmark_script.py` (1)

### Stage 3 — Frontend (web/) ★ ADDED IN ITER 2

**User-facing UI copy (per replacement convention above):**
- `web/app/dashboard/page.tsx:394`
- `web/app/generation/page.tsx:61, 91`
- `web/app/intake/page.tsx:47, 61`
- `web/app/retrieval/page.tsx:79`

**Frontend code:**
- `web/lib/api.ts:827` (JSDoc comment)

**Frontend tests** (e2e specs that reference BPEI as a feature name, NOT as a test-input probe):
- `web/tests/e2e/command_palette_adversarial.spec.ts` — check context, rename name-refs only
- `web/tests/e2e/command_palette_suggest.spec.ts` — same
- `web/tests/e2e/f2_walkthrough.spec.ts` — same
- `web/tests/e2e/intake_disambiguation.spec.ts` — same

(If any of these use the literal string `"BPEI"` as a typed-in-search-box adversarial probe, those literals are preserved per P2-1.)

### Stage 4 — Docs ★ EXTENDED IN ITER 2

**Current docs (patch):**
- `docs/carney_delivery_plan_v6_2.md`
- `docs/carney_handover/5min_video_script.md` ★ CARNEY-FACING, MUST PATCH
- `docs/blockers.md`
- `docs/blocked/blocked_on_user_action_tracker.md`
- `docs/substrate_audit_2026-05-01.md`
- `docs/v6_substrate_audit_2026-05-01.md`
- `docs/task_acceptance_matrix.yaml`
- `docs/benchmark/scoring_rubric.md`
- `docs/walkthroughs/{1.8,2B.7,2C.6}/{briefing,recording_template}.md` (preserve test_inputs.md literals)
- `architecture.md` (per iter-1, even if no current hit — re-verify after rename to catch any newly-stale paths)
- `docs/file_directory.md` — append note about the rename and the historical commemorative tag

**Historical docs (leave as-is):**
- `docs/carney_delivery_plan_v5*.md`
- `docs/carney_delivery_plan_v6_draft.md`
- `docs/shippable_plan_v{2,3,4}_draft.md`

### Stage 5 — State + handover

- `state/polaris_restart/issue_breakdown.md` — append I-naming-001 entry + cross-ref to commemorative memory file
- `docs/handover.md` — append 2026-05-12 note
- `logs/session_log.md` — append §2.2 entry per CLAUDE.md

### Stage 6 — Sanity tests (after rename, before commit)

- `python -c "from polaris_v6.ambiguity_detector import AmbiguityDetector"` (Option B re-export pattern) — must succeed
- `python -c "from polaris_v6.ambiguity_detector.ambiguity_detector import AmbiguityDetector"` — must succeed (direct path)
- `pytest --collect-only tests/v6/test_ambiguity_detector.py tests/v6/test_api_ambiguity.py` — must collect 0 errors
- `grep -rln "from polaris_v6.bpei" src tests` — must return 0 hits (zero remaining direct imports)

## Adopted from iter-1 verdict

- **Directory layout: Option B** (re-export from `__init__.py`).
- **Commemorative footnote: one_place** (`src/polaris_v6/ambiguity_detector/__init__.py` module docstring).
- **Broader naming-audit items: followup_pr** for each (9 follow-up issues to be created post-merge).

## Questions for Codex iter 2

1. Does the iter-2 scope close iter-1 P1-1 (test import) and P1-2 (user-visible web copy)?
2. Is the UI-copy replacement convention (BPEI guard → ambiguity guard, BPEI spine → research pipeline, etc.) acceptable?
3. Is the historical-doc-leave-as-is policy correct, or should historical docs also be patched?
4. Any other P0/P1/P2 missed in iter-1?

## Output schema

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
p3_cosmetic: [...]
ui_copy_convention_review: approve | reject_with_alternative
historical_docs_policy_review: approve | reject
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```
