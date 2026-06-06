# FX-05 (#1109) diff-gate — ITER 1 of 5

```
HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## Output schema (REQUIRED — reply with EXACTLY this YAML, nothing else)

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

## What FX-05 fixes (BUG-06)

`check_auto_approve_allowed(report, user_note)` guarded a material-deviation
corpus with a free-text heuristic: note must be ≥30 chars and not in a small
trivial-string denylist. The R-3 sweep's OWN canned note —
`"R-3 sweep. Domain=workforce. Auto-approve on sweep."` (50 chars) — cleared
both checks, so a corpus with TWO material tier deviations (T3 −0.35, T4 +0.217)
auto-approved and billed ~$7.86 of generator spend. Verified against the REAL
held artifact `outputs/audits/I-ready-017/run_artifacts/corpus_approval.json`
(`approved:true`, that exact note, `has_material_deviation:true`).

## The fix (diff: `.codex/I-ready-017/fx05_codex_diff.patch`, isolated vs CANARY-01 tip `b5ea6db4`)

1. New typed `AuthorizedSweep{authorized_by, authorized_at, flag_source}` — the
   ONE sanctioned credential. A free-text field is not a rubber-stamp defense.
2. `check_auto_approve_allowed(report, authorization=None)` REPLACES the note
   heuristic and **DELETES the `len>=30` + trivial denylist entirely**:
   - no material deviation → `(True, "")`
   - material deviation + `None` → DENY
   - material deviation + ANY non-`AuthorizedSweep` (e.g. a legacy free-text
     note string) → DENY (fail-closed isinstance guard — this is what closes
     the loophole even for the 3 callers the plan did not name)
   - material deviation + COMPLETE `AuthorizedSweep` → `(True, "")`
   - material deviation + INCOMPLETE `AuthorizedSweep` → DENY
3. `authorization_from_env()` builds an `AuthorizedSweep` iff
   `PG_AUTHORIZED_SWEEP_APPROVAL` is truthy (LAW VI: from config only).
4. **All 4 real callers** updated to pass `authorization_from_env()` (so none
   keeps the free-text loophole and none crashes on the new signature):
   `run_honest_sweep_r3.py:2995`, `honest_pipeline.py:191`,
   `run_honest_on_prerebuild_corpus.py:233`, `run_live_honest_cycle.py:178`.
   The free-text `user_note` is retained as a DESCRIPTIVE/audit field only.
5. `corpus_approval.json` persists the structured `authorization` block
   (additive optional field, default `None`; no code reconstructs the dataclass
   from JSON — grep clean — so backward-compatible).

## Evidence
- **Offline smoke:** 33 tests pass across all 3 rewritten gate test files +
  `test_m207_invariant_coverage`. (`test_b2`'s loophole-encoding test
  `substantive_note_accepted` was INVERTED to `free_text_note_alone_never_auto_approves`;
  the crown-jewel `cj_005` substantive-note-accepted test likewise inverted; the
  `test_corpus_approval_gate` len/denylist tests rewritten to structured-auth.)
- **§-1.1 audit on REAL output** (`outputs/audits/I-ready-017/fx05_s11_audit.md`):
  the held drb_72 `corpus_approval.json` report replayed through the new gate →
  the exact canned note now DENIES, no-flag DENIES, `PG_AUTHORIZED_SWEEP_APPROVAL=1`
  APPROVES with a structured block. PASS.

## Faithfulness-invariant check
No change to provenance / strict_verify / 4-role. FX-05 gates corpus approval
(pre-generation spend), upstream of those invariants.

## Q1 — intent confirmation (quality-impact framing)
DEFAULT = `abort_corpus_approval_denied` on ANY material deviation; the ONLY
sanctioned auto-approve is the explicit `PG_AUTHORIZED_SWEEP_APPROVAL` flag. This
HOLDS sweeps that previously auto-approved (e.g. the held drb_72 run would now
abort with zero generator cost). Per the plan + §9.1 invariant #5 this is the
intended spend-gate TIGHTENING, not a downgrade. **Confirm this default-deny is
correct** (highest quality/safety impact), or flag if you see a reason the
default should differ.

## Question
Is the structured-authorization gate correct and complete — loophole closed for
ALL callers, fail-closed on any non-`AuthorizedSweep`, default-deny honoring
§9.1 #5, no faithfulness-invariant regression? Anything blocking?
