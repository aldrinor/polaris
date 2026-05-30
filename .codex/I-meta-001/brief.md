# I-meta-001 — Root-cause investigation: why did 6 safeguards fail to catch 4-role architecture drift

UNCAPPED ITERATION per operator standing directive on planning/audit tasks (`feedback_codex_decides_all_stier_uncapped_2026_05_24`). This is NOT a code-diff review — no 5-cap.

Operator request (verbatim, 2026-05-28 ~15:30 PDT): "So, we need a true investigation on the cause, and true solution to address all causes, could you please deeply investigate with Codex about it"

## Output schema (please use)

```yaml
verdict: APPROVE | REQUEST_DEEPER_INVESTIGATION
confirmed_root_causes: [...]            # Codex-validated, with evidence
novel_root_causes: [...]                # Codex found, Claude missed
disagreements_with_claude: [...]        # where Codex's analysis diverges
ranked_solutions: [...]                 # 3-7 systemic fixes, ordered by impact * (1/cost)
quick_wins_under_2_hours: [...]
medium_changes_under_2_days: [...]
structural_changes_over_1_week: [...]
implementation_order: [...]             # dependency-ordered sequence
metrics_to_validate_solutions_worked: [...]
convergence_call: continue | accept_remaining
```

---

## 1. THE SURFACE (factual)

- **2026-05-25 → 2026-05-27**: 9 high-impact decision documents authored, including the 4-role architecture lock (Generator V4 Pro + Mirror Cohere Command A+ + Sentinel IBM Granite Guardian 4.1 8B + Judge Qwen 3.6-35B-A3B + Python validators + Codex §-1.1 audit).
- **2026-05-27 → 2026-05-28**: 16 smoke iterations on I-safety-002b #925 (the DR head-to-head benchmark POLARIS vs ChatGPT 5.5 Pro / Gemini 3.1 Pro).
- Every smoke ran a **2-LLM subset** (Generator V4 Pro + ad-hoc evaluator Gemma 4 31B-it). Mirror, Sentinel, Judge do NOT EXIST as code in `src/`.
- 3 follow-up bug Issues filed during smokes: I-bug-944 (#930), I-bug-945 (#931), I-bug-946 (#932). Every one got Codex APPROVE on brief + diff. Every one was a gate fix on the 2-LLM stub. All three are still "improvements" to the wrong system.
- Pipeline self-reports `manifest.status=success`, `release_allowed=True`, `evaluator_rule_pass=12/fail=1` despite missing 50% of the locked architecture.
- ~$1.70 of billed OpenRouter calls + ~10 hours of Claude/Codex session-time spent inside the drift envelope before discovery.
- Discovery: 2026-05-28 ~15:25 PDT when operator showed the locked-architecture image.

## 2. THE SMOKING GUN (new evidence — found at brief-authoring time)

`git ls-files --others --exclude-standard docs/` returns **9 UNTRACKED decision documents**, all from 2026-05-25 → 2026-05-27:

```
docs/clinical_rag_sota_deepest_research_2026_05_27.md
docs/clinical_rag_validation_sota_2026_05_26.md
docs/polaris_model_selection_multi_param_2026_05_27.md
docs/polaris_per_role_sota_2026_05_27.md           ← THE 4-ROLE LOCK
docs/polaris_step_b_full_set_audit_2026_05_27.md
docs/v4_pro_academic_literature_2026_05_25.md
docs/v4_pro_constrained_value_research_2026_05_25.md
docs/v4_pro_root_cause_2026_05_25.md
docs/v4_pro_users_production_research_2026_05_25.md
```

Sizes range from ~5KB to ~58KB. None have ever been `git add`ed. None appear in `git log -- docs/`. They exist ONLY on the operator's machine.

**This single fact reframes the whole investigation.** The "drift" isn't drift in the usual sense — it's that a critical class of decision documents was authored, saved to disk, and never entered version control. Every downstream safeguard (Codex review, memory, canonical pin, CLAUDE.md boot ritual, GitHub Issues) depends on the decision being in git to do its job. When the decision skips git, all six safeguards become silent — not because they failed, but because they have nothing to check against.

## 3. THE SIX SAFEGUARDS — failure mode of each, with the smoking gun applied

| # | Safeguard | Its scope | Why it didn't catch this |
|---|-----------|-----------|--------------------------|
| 1 | GitHub Issues | tracks tasks (acceptance criteria) | An issue exists for `I-safety-002b` (#925). Its acceptance criteria are "run the DR benchmark" — not "system under test equals locked architecture". The architecture-completeness invariant is not anyone's per-issue check. |
| 2 | Codex review | gates code changes via brief+diff | Codex reviews what the brief asks. Brief I-bug-944/945/946 asked "does the gate enforce the pin correctly?" — Codex APPROVE'd, correctly, inside that scope. Codex CANNOT see untracked files; CANNOT see system-vs-architecture invariants the brief didn't introduce. The brief framing is the scope ceiling. |
| 3 | Doc updates | doc encodes the lock | Doc was written but **never committed**. The doc IS the safeguard, but only IF it's in version control. An untracked doc is invisible to everything downstream. |
| 4 | Memory | recalls prior conversation decisions | Memory entry `feedback_top_tier_model_only_2026_05_25` codified "V4 Pro generator + Gemma 4 31B evaluator" — correct on 2026-05-25 (before 4-role doc). The memory entry isn't auto-invalidated when a newer lock document lands. Memory is stale-but-confident — the worst failure mode of any recall system. |
| 5 | CLAUDE.md (boot ritual + APD) | tells Claude what to read at session start | §3.1 Step 0 reads the canonical pin (10 files) + Step 2 reads listed plan/issue/spec files. Untracked docs in `docs/` are never on the list. The boot ritual cannot read what it doesn't know to look for. |
| 6 | Canonical pin (docs/canonical_pin.txt) | SHA-pins 10 critical files; HARD STOP on mismatch | Pin protects the 10 named files from tampering. It does NOTHING about files outside the list, and it cannot include untracked files (no SHA without git-add). |

**Pattern:** each safeguard is a vertical that gates ITS OWN work-product. None of them is horizontal across "are all current decision documents IN git, propagated to memory + canonical pin + boot ritual + code-binding?"

## 4. CLAUDE'S WORKING HYPOTHESES (please challenge, expand, or refute)

H1. **No git-add gate at decision-document creation.** Whoever creates `docs/<topic>_<date>.md` files saves to disk and proceeds. No tool/hook/protocol fires "this looks like a load-bearing decision document — commit it now, update canonical pin, update memory."

H2. **No "architecture completeness" assertion in src/.** The locked 4-role architecture has zero machine-checkable representation. There is no `ARCHITECTURE.json` or `polaris_architecture_invariant.py` that says "exactly these 4 LLM roles exist, with these models, pinned to these slugs, served on these providers". The lock is prose.

H3. **Memory invalidation is by-content, not by-recency.** A memory entry from 2026-05-25 named "top tier model only" continues to be loaded as ground truth on 2026-05-28 with no signal that a later doc supersedes it. No memory entry carries an expiration anchor (e.g. "valid until next architecture-lock doc lands").

H4. **APD synthesis order is anchored backwards.** Per CLAUDE.md §1.1, APD synthesis goes: session instructions → active_issue.json → issue_breakdown.md → plan.md → carney_delivery_plan_v6_2.md → session_log.md → architecture.md → matrix (historical). NONE of these point to "scan recent docs/ for un-pinned decision documents that may have superseded older locks." The synthesis chain assumes the canonical files are complete; doesn't reach for what's outside them.

H5. **Codex's brief framing IS the scope ceiling.** Every Codex brief Claude wrote during smokes #13-#16 was correctly scoped to the specific bug. Codex's APPROVE means "the brief's claim is correct" — it CANNOT mean "the system the brief operates on is the right system." Codex doesn't broaden the question; it answers the question. (Same Codex blind spot Claude has, when both are reading the same brief.)

H6. **Smoke runs self-report success at the wrong granularity.** `manifest.status=success` means "the pipeline that exists ran to completion." It cannot mean "the pipeline that exists IS the pipeline POLARIS-as-locked specifies." The smoke harness has no notion of "architecture conformance" — only "did this code path complete."

H7. **GitHub Issues are by-task, not by-invariant.** No issue label / no issue template exists for "system invariants that should always hold across all Issues." There's no `architecture-conformance` label that says "if you change/add code, prove the architecture invariant still holds."

H8. **The work-product → record-in-git mapping is implicit.** CLAUDE.md §2.1 lists state files that "must be updated continuously." It does NOT explicitly require commits + push when a NEW decision document is created. The hygiene rule covers updates to existing files, not creation of new locked documents.

H9. **Memory inverse-truncation hides recent entries.** MEMORY.md is 37.4 KB (over the 24.4 KB load limit per the warning). Entries beyond ~24 KB are silently truncated at load time. The most RECENT memory entries (which would include any updates about the 4-role architecture) are statistically more likely to be truncated than older "behavioral rules" entries that anchor the top of the index.

## 5. CLAUDE'S PRELIMINARY SOLUTION SET (please weigh independently, add, drop)

S1. **`git add` discipline as binding hygiene.** CLAUDE.md §2 amendment: "Any new file in docs/, state/, polaris-controls/, or .codex/ that encodes a decision (architecture lock, model pick, SOTA selection, contract, plan) MUST be `git add`ed and committed in the same session it is authored. Untracked decision documents are forbidden after session end." Add a session-end hook that `git status --porcelain docs/ state/` and BLOCKS turn-yield if untracked files exist with "lock", "pick", "sota", "contract", "plan", or a `_YYYY_MM_DD` date suffix in their names.

S2. **Architecture invariant in code.** New file `src/polaris_graph/architecture/invariants.py` with `POLARIS_ARCHITECTURE = {"generator": {...}, "mirror": {...}, "sentinel": {...}, "judge": {...}, "plus": [...]}` as a frozen dataclass + `assert_architecture_complete()` that fails the build if any required layer's model_slug or import path is missing. Wire into preflight as the FIRST check before anything else. Pin the architecture spec file in canonical_pin.txt.

S3. **Memory auto-invalidation by superseding-document watch.** Memory entry frontmatter gets a new `supersedes_after_filename_pattern` field. When a file matching the pattern lands in docs/, the entry is auto-archived. E.g. `feedback_top_tier_model_only_2026_05_25.md` declares `supersedes_after_filename_pattern: "docs/polaris_per_role_sota_*.md"`. On session boot, scan `docs/` against active memory entries; flag entries whose superseding pattern matches.

S4. **APD synthesis prefix: recent-git scan.** CLAUDE.md §3.1 Step 0' (new step BEFORE the existing Step 0): `git log --since="72h ago" --name-only -- docs/ state/ polaris-controls/ | head -80` AND `git status --porcelain docs/ state/`. If any untracked files match the decision-doc pattern, HALT and demand commit before proceeding.

S5. **GH Issue template invariant.** All new Issue templates get a mandatory section: "System-under-test architecture conformance" with the architecture invariant doc hash + Codex-verified statement that the changed scope respects the invariant. CI gate `polaris/architecture-conformance` (new check) parses this and BLOCKS merge if absent or stale.

S6. **Smoke harness self-reports architecture coverage.** `pathB_run_gate.py:preflight()` adds a new assertion: `assert_architecture_complete(pin_role_pins)` — compares the captured role_pins set against the architecture invariant from S2. If a role from the architecture invariant is missing in role_pins, gate-FAIL with diagnostic. Manifests gain a `architecture_coverage` field that lists `{layer: present|missing}` per locked role.

S7. **"Decision document → propagation tracker" GH Issue.** Every locked decision doc gets a GH Issue with mandatory propagation checklist: `[ ] file committed`, `[ ] canonical_pin.txt updated`, `[ ] memory entries amended/superseded`, `[ ] code defaults updated`, `[ ] tests updated`, `[ ] CLAUDE.md / AGENTS.md cross-references updated`. The Issue cannot close until all checks done. Codex reviews the propagation diff, not just the doc.

S8. **Memory file size hard limit + load-order fix.** Memory load order should be REVERSED (most-recent-first), with hard truncation at 24 KB. This way recent entries always load; the oldest entries are the ones that get dropped. Plus a hard limit alert: if memory > 22 KB, force a "consolidation" pass that compresses older entries.

S9. **Codex brief template invariant.** All Codex review briefs MUST include a "System-under-test" section at the top that declares the architecture invariant the system claims to satisfy + the most-recent decision doc hash. Codex can then refuse the review if the declared system doesn't match the codebase state.

## 6. EVIDENCE FILES FOR CODEX TO READ (lazy import — read only if needed)

- `docs/polaris_per_role_sota_2026_05_27.md` (UNTRACKED, 58.7 KB — the 4-role lock)
- `docs/canonical_pin.txt` (the 10 pinned files; new docs don't auto-add)
- `src/polaris_graph/benchmark/pathB_runner.py` (lines 36-65 — defaults are 2-LLM)
- `src/polaris_graph/llm/entailment_judge.py` (line 79 — entailment defaults match Gemma evaluator, not Mirror/Sentinel/Judge)
- `scripts/dr_benchmark/pathB_run_gate.py` (RolePin has no notion of layer-completeness)
- `state/polaris_restart/plan.md` (the executive plan — was it superseded?)
- `~/.claude/projects/C--POLARIS/memory/MEMORY.md` (37.4 KB; over 24.4 KB load limit per system warning)
- `~/.claude/projects/C--POLARIS/memory/feedback_top_tier_model_only_2026_05_25.md` (the stale-but-confident entry)
- `CLAUDE.md` §-1, §0-§10 (the boot ritual + APD hierarchy)

## 7. CONSTRAINTS ON THE SOLUTION

- Carney deadline 2026-09-06 (~14 weeks). Solutions must be implementable in the remaining time without paralyzing forward progress on other Issues.
- Operator works alone except for Claude + Codex. No human-bureaucracy answers (e.g. "weekly design review meeting" is not implementable).
- Solutions must compose with existing rigor (5-iter Codex cap, autonomous merge flow, branch protection, canonical pin), not replace it.
- Solutions must address the smoking gun (untracked decision docs) AND the broader pattern (vertical-not-horizontal safeguards).
- Solutions must be verifiable after the fact (some automation/check that can prove the fix is working).

## 8. WHAT WE NEED FROM CODEX (this brief)

A. Confirm or refute each of H1–H9. Add hypotheses Codex sees that Claude missed.
B. Independent rank of S1–S9 by impact * (1/implementation_cost). Add solutions Codex thinks are missing. Drop solutions Codex thinks are theater.
C. A dependency-ordered implementation plan (which solution blocks which, what can run in parallel).
D. A short list of "metrics that prove the fix worked" — what should we observe in 1 week / 1 month / by Carney that tells us the drift class is truly closed.
E. A reality check: is there a class of drift we haven't even surfaced yet (e.g. state/ untracked files, polaris-controls drift, branch-protection asymmetries)? Codex's job here is to BROADEN the inquiry, not narrow it.

Iterate as many rounds as needed. Claude will read every iteration and push back where evidence supports a different view (`feedback_be_skeptical_of_codex_2026_05_13`). We converge when Codex says `convergence_call: accept_remaining` AND Claude agrees the analysis is complete enough to implement.
