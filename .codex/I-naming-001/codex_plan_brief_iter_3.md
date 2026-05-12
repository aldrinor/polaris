HARD ITERATION CAP: 5 per document. This is iter 3 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

# I-naming-001 plan iter 3 — P1-3 + P2-4 + P2-5 fixes

## P1-3 resolved — actual exported API verified

Read `src/polaris_v6/bpei/ambiguity_detector.py`. Actual public API:
- `CandidateSnippet` (class)
- `AmbiguityCluster` (class)
- `AmbiguityResult` (class)
- `detect_ambiguity` (function)

The current `__init__.py` is just a docstring (no re-exports). Stage 1 will ADD re-exports per Option B:

```python
# src/polaris_v6/ambiguity_detector/__init__.py
"""Ambiguity detector — HDBSCAN-based detection of multi-meaning queries
before retrieval. Surfaces a disambiguation modal when ≥2 distinct
concept-clusters share the query's entity space.

Historical: this module was originally named `bpei/` after the
2026-04-30 'phantom completion' incident where a user typed the literal
string "BPEI" as an adversarial probe and the system fabricated an
answer. The directory carried the commemorative tag through 2026-05-12,
when it was renamed to its descriptive name. See
memory/bpei_phantom_completion_lessons.md (user-level memory) for the
incident write-up.
"""
from .ambiguity_detector import (
    AmbiguityCluster,
    AmbiguityResult,
    CandidateSnippet,
    detect_ambiguity,
)

__all__ = [
    "AmbiguityCluster",
    "AmbiguityResult",
    "CandidateSnippet",
    "detect_ambiguity",
]
```

Stage 6 sanity test updated:
```bash
python -c "from polaris_v6.ambiguity_detector import CandidateSnippet, AmbiguityCluster, AmbiguityResult, detect_ambiguity; print('ok')"
python -c "from polaris_v6.ambiguity_detector.ambiguity_detector import CandidateSnippet, detect_ambiguity; print('ok')"
pytest --collect-only tests/v6/test_ambiguity_detector.py tests/v6/test_api_ambiguity.py
grep -rln "from polaris_v6.bpei" src tests scripts   # must return 0
```

## P2-4 resolved — `scripts/autoloop/backfill_pre_bootstrap_verdicts.py`

Confirmed at lines 70, 77, 78. Will update:
- Line 70 comment: `# Phase 1 — BPEI spine substrate (cycle-11 lock)` → `# Phase 1 — research pipeline substrate (cycle-11 lock)`
- Line 77 title: `"F2 BPEI ambiguity detector substrate"` → `"F2 ambiguity detector substrate"`
- Line 78 evidence path: `"src/polaris_v6/bpei/ambiguity_detector.py"` → `"src/polaris_v6/ambiguity_detector/ambiguity_detector.py"`

If left unfixed, the script silently skips Task 1.2 evidence — the failure mode Codex caught.

## P2-5 resolved — additional walkthrough/script copy

Confirmed:
- `docs/walkthroughs/I-f10-008-tirzepatide-vs-semaglutide.md:176` — `"BPEI question → retrieval → spec generation → UI"` → `"ambiguity-checked question → retrieval → spec generation → UI"`
- `docs/walkthroughs/5.1/full_corpus_test_inputs.md:20` — query INPUT `"What is the BPEI methodology…"` — **PRESERVE LITERAL** (this is an adversarial probe per P2-1).
- `docs/walkthroughs/5.1/full_corpus_test_inputs.md:22` — comment `"Expected ambiguity: YES — BPEI ambiguity should fire (modal asks if user means biopsychosocial / business process / etc.)"` — update to `"Expected: ambiguity detector should fire (modal asks if user means biopsychosocial / business process / etc.)"`. Note: this comment EXPLAINS the probe; the probe itself (line 20) is preserved literal.
- `scripts/screenshot_walkthrough.js:2` — `"the BPEI chain"` → `"the research pipeline"`

All added to Stage 2/3/4 file list.

## P3 cosmetic resolved

- Extended final grep coverage: now greps for `polaris_v6.bpei`, `src/polaris_v6/bpei`, `BPEI spine`, `BPEI chain`, `BPEI guard`, `BPEI front half`, `BPEI retrieval half`, `BPEI generator` across `src/ tests/ scripts/ web/ docs/`. Each pattern must return 0 (after rename) EXCEPT for `BPEI` standalone in test-input fixtures (P2-1).

- `docs/carney_handover/5min_video_script.md` — re-checked: only reference is to the **memory filename** `bpei_phantom_completion_lessons.md`. Per Codex P3 guidance, the filename reference STAYS (memory file is commemoratively named); the surrounding prose is rewritten to neutral explanatory text:
  - Before: `... the BPEI ambiguity guard (see memory/bpei_phantom_completion_lessons.md) ...`
  - After: `... the ambiguity detector (incident write-up: memory/bpei_phantom_completion_lessons.md, commemoratively named after the 2026-04-30 probe) ...`

## Final scope (iter 3)

### Stage 1 — Dir rename + re-exports
```
git mv src/polaris_v6/bpei src/polaris_v6/ambiguity_detector
```
Then rewrite `src/polaris_v6/ambiguity_detector/__init__.py` with re-exports above.

### Stage 2 — Python imports + comments (22 files)

**Import updates (would break if not done):**
- `src/polaris_v6/api/ambiguity.py:16`
- `tests/v6/test_ambiguity_detector.py:10`

**Comment/docstring updates:**
- `src/polaris_v6/ambiguity_detector/ambiguity_detector.py` (1, header)
- `src/polaris_v6/memory/__init__.py` (1)
- `src/polaris_v6/api/ambiguity.py` (1, docstring)
- `src/polaris_graph/api/{audit_bundle_route,intake,intake_route,__init__}.py` (4 × 1)
- `src/polaris_graph/audit_bundle/{bundle_schema,manifest_builder}.py` (2 × 1)
- `src/polaris_graph/intake/{cluster_labeler,disambiguation_clusterer,__init__}.py` (3 × 1)
- `src/polaris_graph/scope/scope_decision.py` (1)
- `tests/e2e/frontend_replay_smoke.py` (1)
- `tests/polaris_graph/audit_bundle/test_bundle_builder.py` (1)
- `tests/polaris_graph/followup/test_agent.py` (1)
- `tests/polaris_graph/golden/test_slice_004_goldens.py` (1)
- `tests/v6/test_ambiguity_detector.py` (1, comment)
- `tests/v6/test_api_ambiguity.py` (1)
- `tests/v6/test_run_benchmark_script.py` (1)

**Scripts:**
- `scripts/autoloop/backfill_pre_bootstrap_verdicts.py` (3, lines 70/77/78) ★ ITER-3
- `scripts/screenshot_walkthrough.js` (1, line 2) ★ ITER-3

### Stage 3 — Frontend (web/)

**User-facing UI copy:**
- `web/app/dashboard/page.tsx:394`
- `web/app/generation/page.tsx:61, 91`
- `web/app/intake/page.tsx:47, 61`
- `web/app/retrieval/page.tsx:79`

**Frontend code/test:**
- `web/lib/api.ts:827`
- `web/tests/e2e/command_palette_adversarial.spec.ts`
- `web/tests/e2e/command_palette_suggest.spec.ts`
- `web/tests/e2e/f2_walkthrough.spec.ts`
- `web/tests/e2e/intake_disambiguation.spec.ts`

(For each e2e spec: rename FEATURE-NAME references only; preserve any literal `"BPEI"` strings typed as adversarial probes per P2-1.)

### Stage 4 — Docs

**Current docs (patch):**
- `docs/carney_delivery_plan_v6_2.md`
- `docs/carney_handover/5min_video_script.md` (neutralize prose; preserve memory filename ref per P3)
- `docs/blockers.md`
- `docs/blocked/blocked_on_user_action_tracker.md`
- `docs/substrate_audit_2026-05-01.md`
- `docs/v6_substrate_audit_2026-05-01.md`
- `docs/task_acceptance_matrix.yaml`
- `docs/benchmark/scoring_rubric.md`
- `docs/walkthroughs/{1.8,2B.7,2C.6}/{briefing,recording_template}.md` (preserve test_inputs.md literals)
- `docs/walkthroughs/I-f10-008-tirzepatide-vs-semaglutide.md:176` ★ ITER-3
- `docs/walkthroughs/5.1/full_corpus_test_inputs.md:22` ★ ITER-3 (line 22 comment only; line 20 literal probe preserved)

**Historical docs (leave as-is):**
- `docs/carney_delivery_plan_v5*.md`
- `docs/carney_delivery_plan_v6_draft.md`
- `docs/shippable_plan_v{2,3,4}_draft.md`

### Stage 5 — State + handover

- `state/polaris_restart/issue_breakdown.md` — append I-naming-001 entry
- `docs/handover.md` — append 2026-05-12 note
- `logs/session_log.md` — §2.2 entry

### Stage 6 — Sanity tests

(See P1-3 resolution above for the corrected import paths.)

## Questions for Codex iter 3

1. Does this close P1-3 + P2-4 + P2-5?
2. Any other production-tree reference I still missed? (Codex's broader grep covered scripts/ + docs/walkthroughs in iter 2; please re-spot-check.)
3. Approve the carney_handover/5min_video_script.md rewrite framing?
4. Approve the test-input vs name-ref distinction policy for the 4 e2e specs?

## Output schema

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
p3_cosmetic: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```
