# I-meta-001 — iter 2: deepen on Codex novel findings + reach convergence

UNCAPPED iteration. Convergence is reached when both Claude and Codex agree the root-cause inventory is complete AND the solution set is implementable.

## Output schema (please use)

```yaml
verdict: APPROVE_FOR_IMPLEMENTATION | REQUEST_DEEPER_INVESTIGATION
new_root_causes_found_this_iter: [...]
solutions_revised: [...]                # what changed since iter 1
final_implementation_order: [...]       # locked dependency-ordered list
operator_decisions_blocked_on: [...]    # items only the operator can decide
metrics_to_validate: [...]
convergence_call: continue | accept_remaining
```

## 1. CLAUDE VERIFIED YOUR ITER-1 NOVEL FINDINGS

All four checked. Evidence:

### V1. `docs/polaris_locked_scope.md` not in canonical_pin.txt — CONFIRMED
```
$ grep -E "polaris_locked_scope" docs/canonical_pin.txt
(empty)
```
The doc that self-describes as the anti-drift source is invisible to the pin-verification ritual.

### V2. Three conflicting locks — CONFIRMED
- `docs/polaris_per_role_sota_2026_05_27.md`: Mirror = **Kimi K2.6** (earlier)
- `docs/polaris_step_b_full_set_audit_2026_05_27.md`: Mirror = **Cohere Command A+ (Apache 2.0 verified 2026-05-27)** (later)
- Operator's image (most recent operator surface): **Cohere Command A+** ← matches Step-B doc

So Step-B doc supersedes per-role-sota doc (same day, but Step-B references Command A+ release of 2026-05-20 + Apache 2.0 confirmation). **Three "locks" exist, none formally retired.**

Important: Step-B doc explicitly says "Independent pass / cross-validation pending." So Step-B's pick is **operator-preferred but not Codex-cross-validated yet**.

### V3. MEMORY.md truncation order — Claude H9 WAS WRONG. CODEX WAS RIGHT.
Top 3 entries are dated 2026-05-28 (today) and 2026-05-27 (yesterday). Recent at TOP. Truncation (if it happens) drops OLDEST entries, not newest. Claude H9 withdrawn — apologies for the wrong direction.

The actual hazard from MEMORY.md being 37.4 KB > 24.4 KB limit: **older anchor memories** (CLAUDE.md global directives, foundational behavioral rules established months ago) are the truncation victims. The most-recent locks are safe, but the FOUNDATIONAL anchors that hold Claude's role identity might be dropping. (Different hazard than I claimed; still a hazard.)

### V4. Branch vs active issue mismatch — CONFIRMED
```
branch: bot/I-safety-001a-contract-v3-3-lock
active_issue_id: I-safety-002b
```
3 follow-up bug commits (I-bug-944, 945, 946) landed on a branch named for a different issue. The branch-active-issue invariant is violated.

### V5. Family registry lacks Cohere + IBM Granite — CONFIRMED
`src/polaris_graph/llm/openrouter_client.py:422 _FAMILY_PREFIXES` has 10 families: deepseek, qwen, glm, llama, gemma, mistral, kimi, openai, anthropic, google-closed.
Missing: **cohere**, **ibm-granite**.

Implication: even after the 9 untracked docs are committed + the 4-role architecture is wired into code, `family_from_model("cohere/command-a-plus")` returns `"unknown"` and `check_family_segregation()` would refuse to construct the client. This is a hard implementation blocker for the 4-role rollout.

Further: `check_family_segregation()` is currently **pairwise** (generator vs evaluator). A 4-role architecture needs **4-way segregation** (all four families distinct OR explicit rules for which pairs may collide).

## 2. ADDITIONAL DRIFT CLASSES CLAUDE FOUND WHILE VERIFYING

### V6. `.codex/` has 20+ untracked files including completed Codex review artifacts
`git ls-files --others --exclude-standard .codex/` returns audit records like `.codex/I-gen-005-step15-atom/codex_diff_review_brief_iter1..5.md` + their verdicts. These are CODEX REVIEW HISTORY for shipped work that is now invisible to git (and therefore to any auditor who later wants to read "what did Codex APPROVE on this PR?").

So drift class isn't just "decision documents in docs/". It's also "Codex-review-trail artifacts in .codex/". Both are untracked.

### V7. The 4-role lock may itself need a "Mirror exists in the codebase" gate
Even with all docs committed + family registry expanded, the bare assertion "POLARIS architecture = {Generator, Mirror, Sentinel, Judge}" needs a code-side verification that each layer is *implemented*. Not just configured. The pathB gate currently can pass with a 2-role pin because it captures whatever roles are pinned. It does NOT verify that the SET of pinned roles is the SET the architecture requires.

### V8. CLAUDE.md §3.0 lists 6 PR artifacts (brief, codex_brief_verdict, codex_diff.patch, codex_diff_audit, claude_audit, codex_visual_audit). None of them are "architecture conformance attestation." So even after structural fixes, a future PR can ship without proving it preserves the architecture invariant.

## 3. UPDATED HYPOTHESES (closing iter-1's, adding new)

- H1–H8 confirmed by both Claude verification and Codex iter-1.
- H9 WITHDRAWN.
- NEW H10: **`.codex/` history is also untracked** → no audit trail for past Codex decisions.
- NEW H11: **Two-family segregation is pairwise; 4-role architecture needs N-way segregation logic that does not exist.**
- NEW H12: **No "architecture conformance attestation" in the PR artifact set.**
- NEW H13: **The "lock" word is overloaded.** Step-B says "Independent pass / cross-validation pending" — so what looks like a lock to the operator is still a recommendation pending Codex cross-validation. The DRAFT/RECOMMEND/LOCK lifecycle distinction is real (Codex iter-1 novel finding #2) and unresolved.

## 4. OPEN QUESTIONS FOR YOU (iter 2)

Q1. **Which of the 3 candidate locks is the FINAL POLARIS-architecture lock?**
   - Step-B doc + operator image agree on (Cohere Command A+ / Granite 4.1 / Qwen 3.6-35B-A3B). Per-role-sota doc has (Kimi K2.6 / Granite 3.3 / Qwen 3.6-35B-A3B).
   - Claude's read: Step-B is operator-preferred but says "cross-validation pending" — so it's an operator DRAFT, not a Codex-validated FINAL.
   - You are the cross-validator. Do you accept the Step-B picks as the final POLARIS architecture? Or do you have a different read (e.g. "I need to audit Cohere Command A+ on AA-Omniscience before locking" or "Granite 3.3 vs 4.1 needs a separate decision")?
   - We need YOUR call before any code-binding YAML can be written. Without it, S2 (architecture lock YAML) is blocked on the operator.

Q2. **DRAFT / RECOMMEND / LOCK lifecycle — specify the machine-distinguishable form.**
   - Codex iter-1 surfaced this gap. Proposed convention: each decision doc gains a frontmatter field `status: draft | recommendation | locked | superseded` and a `supersedes: <filename>` field. Locked status REQUIRES (a) Codex APPROVE artifact reference, (b) propagation-manifest checkmark, (c) committed.
   - Are there additional states you'd add? (e.g. `operator-locked-pending-codex` for the current Step-B doc situation)

Q3. **Architecture lock YAML schema — sketch.**
   Proposed: `config/architecture/polaris_runtime_lock.yaml`:
   ```yaml
   version: v1
   source_doc: docs/polaris_step_b_full_set_audit_2026_05_27.md
   source_doc_sha: <after commit>
   locked_at: 2026-05-27
   locked_by: operator
   cross_validated_by: ""           # populated when Codex APPROVE
   status: operator-draft
   roles:
     generator:
       model: deepseek/deepseek-v4-pro
       family: deepseek
     mirror:
       model: cohere/command-a-plus
       family: cohere               # requires registry expansion (V5)
     sentinel:
       model: ibm-granite/granite-guardian-4.1-8b
       family: ibm-granite          # requires registry expansion
     judge:
       model: qwen/qwen-3.6-35b-a3b
       family: qwen
   deterministic_layers:
     - python_validators
     - codex_section_1_1_audit
   ```
   Codex review: missing fields, wrong types, schema risks?

Q4. **N-way family segregation spec.** Pairwise check today is `generator_family != evaluator_family`. 4-way: do we require all 4 distinct, or specify allowed-collision rules?
   Claude proposal: all 4 distinct, hard fail otherwise. (Same lineage-diversity principle the pairwise check was built on.)

Q5. **Propagation manifest format.**
   Proposed: each locked decision doc carries `<filename>.propagation.json`:
   ```json
   {
     "doc_sha": "<sha>",
     "checkpoints": {
       "committed": true,
       "canonical_pinned": true,
       "memory_reconciled": ["entry_a_superseded", "entry_b_amended"],
       "code_defaults_updated": ["src/polaris_graph/.../X.py"],
       "tests_updated": ["tests/.../test_Y.py"],
       "claude_md_cross_references": ["§1.1"],
       "codex_cross_validated": "verdict_path"
     }
   }
   ```
   The "lock" is not granted until all checkpoints are true. Issue closes only when manifest is complete.

Q6. **Is `docs/polaris_locked_scope.md` retained or retired?** It self-describes as the anti-drift source but is itself outside the pin. Should we:
   (a) add it to canonical_pin.txt
   (b) merge its content into the new architecture lock YAML and retire it
   (c) split into "scope lock" (project goals) + "architecture lock" (layers + models) and pin both

   Claude's lean: (b) — single source of truth is better than two scope docs.

Q7. **What metric proves the drift class is closed in 1 week?**
   Codex iter-1 said "smoke cannot PASS with missing required roles." That's necessary but maybe not sufficient. Additional metrics?
   Proposal: also report at session-end "X% of recent decision docs in git" — should be 100%.

Q8. **Are there MORE drift classes we still haven't surfaced?** Codex went deep but please apply Cunningham's law one more time. Where else could "doc-says-X-but-code-says-Y" be lurking?
   Suspicion targets:
   - `src/polaris_graph/audit_ir/model_pin.py:26` references `judge` and `inductor` roles — are those vestiges of an older architecture? If so, do they conflict with the 4-role lock?
   - `state/polaris_restart/plan.md` — does that plan still describe the system as Codex/CLAUDE.md sees it?
   - `polaris-controls/CHARTER.md` — should it carry the architecture invariant?
   - Branch protection — is `bot/I-safety-001a-contract-v3-3-lock` protected the same as `polaris`? (smoke commits landed there; if it's unprotected, that's a Codex-bypass class).

## 5. CONTEXT THAT MAY HELP CODEX'S ITER 2

- The 9 untracked decision docs total ~XXX KB; they're all in `docs/` directory.
- The active branch `bot/I-safety-001a-contract-v3-3-lock` has 37 unpushed commits.
- `state/active_issue.json` = `I-safety-002b`; branch name says `I-safety-001a`.
- The Carney deadline is 2026-09-06 (~14 weeks).
- Operator has invited unbounded iteration on this brief because it's a planning audit, not a code diff.

Iterate as many rounds as needed. Surface anything we haven't yet thought of.
