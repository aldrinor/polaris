Excellent, comprehensive guidance — and it confirms my D6/D7 read plus surfaces the critical brief-gate-as-first-state point and the two money-gate split. Everything is grounded. Writing the proposal now as my final markdown text (no files written, per harness + advisor instruction).

---

# PROPOSAL — POLARIS Standing Task-Execution Practice (`polaris_task_cycle`)

**Status:** DRAFT for operator approval + Codex review. Not a lock. Not a CLAUDE.md commit yet.
**Scope:** The standing process for ALL future POLARIS task-work, built on the Claude Code Workflow tool. Extends — never contradicts — the binding rules in `CLAUDE.md` (§3.0, §8.3.x, §-1.1/§-1.2, §10).
**Grounding:** verified against `config/architecture/polaris_runtime_lock.yaml`, `scripts/dr_benchmark/{pathB_run_gate.py,smoke.md}`, `scripts/architecture/{verify_lock.py,weekly_drift_report.py}`, `.github/workflows/architecture-conformance.yml`, `state/active_issue.json`, `.codex/I-meta-002/feasibility_synthesis.md`.

**Single governing principle:** *The Workflow tool orchestrates Claude-side work (build → smoke → convey → iterate). It NEVER owns a gate decision.* Codex is the only review gate (§3.0); CI is the only merge gate; the operator is the spec/merge owner. The workflow drives sequencing and evidence assembly; authority stays where the cage put it.

---

## 1. THE STANDING LOOP AS A STATE MACHINE

The operator's verbatim loop (build → smoke → convey-all-incl-visual → codex-review → iterate → APPROVE-or-5cap → close → next) is the **diff cycle**. But §3.0 binds POLARIS to **two** Codex gates per Issue, each with its own 5-cap: a **brief gate** (acceptance-criteria correctness, BEFORE build) and a **diff gate** (code correctness, after smoke). A single-review state machine would contradict §3.0 — the exact "extends-not-contradicts" failure this task warns against. So the machine instantiates CONVEY → CODEX_REVIEW → ITERATE → GATE **twice**: once around the brief, once around the diff.

```
                          ┌────────────────────────────────────────────────┐
   (operator TaskCreate)  │  Issue N from issue_breakdown.md (locked order) │
            │             └────────────────────────────────────────────────┘
            ▼
   [BOOT]──►[BRIEF]──►[CONVEY_BRIEF]──►[CODEX_REVIEW_BRIEF]◄──┐
                                          │                   │ iter<5 & REQUEST_CHANGES
                                          │ APPROVE or iter=5  │
                                          ▼                   │
                                       [BUILD]                │ (ITERATE_BRIEF)
                                          │                   │
                                          ▼                   │
                                   [SMOKE]─(GATE A/B)─────────┘  (FAIL → back to BUILD or URGENT issue)
                                          │ smoke GREEN
                                          ▼
                                 [CONVEY_DIFF]──►[CODEX_REVIEW_DIFF]◄──┐
                                          │                            │ iter<5 & REQUEST_CHANGES
                                          │ APPROVE or iter=5           │ (ITERATE_DIFF)
                                          ▼                            │
                                       [GATE]──────────────────────────┘
                                          │ verdict:APPROVE (or iter-5 force-APPROVE)
                                          ▼
                                       [CLOSE]   (CI auto-merge → issue auto-closes; NOT a Claude action)
                                          │
                                          ▼
                                       [NEXT]    (git checkout -b bot/<next-issue> — locked sequence)
```

| State | Entry condition | Exit condition | CLAUDE.md rule it honors | Workflow primitive / shell step that implements it |
|---|---|---|---|---|
| **BOOT** | New turn / Issue assigned | §10 ritual passes (canonical pin + CHARTER/PLAN SHA + `active_issue.json` read) | §3.1 step 0, §10 boot ritual | Shell preamble (NOT inside workflow): `verify_lock` SHA check + `git show HEAD:` pin compare; halt-marker scan `state/halt_*` |
| **BRIEF** | BOOT clean | `.codex/<id>/brief.md` authored (acceptance criteria + adjacent-file scan + verbatim §8.3.1 cap directive) | §-1.2 step 1–2, §8.3.3, REVIEW_BRIEF_FORMAT §0–§8 | `agent()` (Claude-fork) writes brief; or done in main turn pre-workflow |
| **CONVEY_BRIEF** | brief authored | brief packaged for Codex (no builder rationale, spec-only) | feedback_codex_must_see_evidence_not_conclusion | script assembles bundle path list |
| **CODEX_REVIEW_BRIEF** | bundle ready | `codex_brief_verdict.txt` written with final `verdict:` line | §3.0 "Codex is the only gate", §-1.1 | **`codex exec` shell step inside one non-parallel `agent()`** (see §2 hook) |
| **ITERATE_BRIEF** | verdict=REQUEST_CHANGES & iter<5 | revised brief → loop to CONVEY_BRIEF | §8.3.1, §8.3.5 iteration_trajectory.md, §8.3.9 schema | plain JS `for` loop body; append `iteration_trajectory.md` |
| **GATE(brief)** | verdict=APPROVE OR iter=5 | proceed to BUILD; if iter=5 REQUEST_CHANGES → write `codex_brief_verdict_iter5_force_approve.txt` + final `verdict: APPROVE` | §8.3.1 force-APPROVE procedure | parse last `verdict:` line; branch |
| **BUILD** | brief APPROVE'd | diff committed as `.codex/<id>/codex_diff.patch` + working-tree changes | §3.0 "Claude writes code (briefs AND diffs)", LAW II/VI | `agent()` (Claude-fork) edits/writes/commits |
| **SMOKE** | build complete | Gate-A (offline + cheap real) GREEN; Gate-B only if GPU rented | §-1.2 step 3, §9.4, smoke.md, §8.4 | `parallel([pytest, verify_lock, preflight_offline, contract_tests])` + cheap real probes — **see §3** |
| **CONVEY_DIFF** | smoke GREEN | diff + smoke results + **visual artifacts** packaged for Codex | §8.3.3, REVIEW_BRIEF_FORMAT §9, feedback_codex_has_vision | script collects {diff, smoke JSON, screenshot paths}; visual via `codex exec -i` |
| **CODEX_REVIEW_DIFF** | bundle ready | `codex_diff_audit.txt` (+ `codex_visual_audit.txt` if `web/**` touched) | §3.0, red_team_checklist, §-1.1 line-by-line | `codex exec` (and `codex exec -i` for visual) shell step in `agent()` |
| **ITERATE_DIFF** | verdict=REQUEST_CHANGES & iter<5 | revised diff → loop to SMOKE→CONVEY_DIFF | §8.3.1, §8.3.5 | JS `for` loop; re-smoke each round |
| **GATE(diff)** | verdict=APPROVE OR iter=5 | all required artifacts present; iter-5 → `codex_diff_audit_iter5_force_approve.txt` + residual follow-up Issues | §8.3.1, §3.0 5-artifact triple | parse + branch + write force-approve artifact |
| **CLOSE** | diff APPROVE'd + artifacts complete | Codex `verdict: APPROVE` → CI `polaris/codex-required` passes → **GitHub auto-merge → issue auto-closes** | §3.0, §8.2, CHARTER §1, forbidden_admin_merge | **NO workflow step** — this is the gate chain, not Claude. ⚠ see dependency below |
| **NEXT** | Issue N merged | `git checkout polaris && git pull && git checkout -b bot/<next-issue>` — locked next per issue_breakdown.md | §8.3.10, §3.0 "cannot start N+1 until N completed" | shell step; zero prose between merge and branch (§8.2) |

**CLOSE is never a Claude action.** The chain is: Codex APPROVE (or iter-5 force-APPROVE) → verdict-file last `verdict:` line → CI required check `polaris/codex-required` → auto-merge → issue auto-closes. Claude has **no** `gh pr merge --admin` (CHARTER §1, forbidden_admin_merge, forbidden_autonomous_merge_is_cage_bypass). The operator's "close the GH issue" phrasing maps to §-1.2 step 7 *mechanical follow-through*, not a Claude merge.

> **⚠ OPERATOR-SIDE PREREQUISITE (D4, currently broken):** per `active_issue.json.branch_protection_finding_d4`, polaris `main` has `required_status_checks=[]` and `enforce_admins=false`. **`polaris/codex-required` is NOT actually enforced** today, so the auto-merge-on-APPROVE chain is not live. The CLOSE→auto-merge link depends on the operator fixing branch protection (add `codex-required` as a required check, set `enforce_admins=true`). Until then, merges remain a manual operator action at `git log` review time. *This is the single highest-severity gap — see §6.*

**"Military order" / strict-sequence resolution.** §8.3.10 mandates auto-advance to the next branch; §10-step-4 + §8.2 say "do NOT pick a task autonomously." These reconcile because `issue_breakdown.md` is a **locked sequence** — "next" is never a discretionary pick, so mechanical advance honors both. The "no autonomous pick" rule survives, narrowed to *discretionary* choice when ordering is genuinely ambiguous; it does not license skipping the locked next-Issue. This is operator-resolving-a-pre-existing-ambiguity, not operator-overriding-the-cage.

---

## 2. REUSABLE WORKFLOW SCRIPT TEMPLATE — `polaris_task_cycle`

Plain JS, `meta` pure-literal, `issue_id` passed as a workflow arg (never baked into `meta`). No `Date.now`/`Math.random`/`setTimeout` in phase 1 (breaks resume). `codex exec` runs as a **single foreground Bash step inside ONE non-parallel `agent()`** (§8.4: one codex at a time). The 5-cap iterate is a plain `for` loop. `parallel()`/`pipeline()` are used **only** where work genuinely fans out (multi-suite smoke; multi-claim self-audit) — the inherently-sequential review loop stays sequential.

```javascript
const meta = {
  name: "polaris_task_cycle",
  description: "Standing per-Issue cycle: brief-gate -> build -> smoke-before-spend -> diff-gate (5-cap). Workflow drives Claude-side work; codex exec + CI gate keep authority.",
  phases: [
    "brief", "codex_review_brief",
    "build", "smoke_gate_a", "smoke_gate_b",
    "convey_diff", "codex_review_diff",
    "wrapup"
  ]
};

// args: { issue_id, github_no, touches_web, gpu_rented }
async function main(args) {
  const id = args.issue_id;                 // e.g. "I-meta-002"  -- NOT in meta
  const codexDir = `.codex/${id}`;
  const briefPath = `${codexDir}/brief.md`;
  const diffPath  = `${codexDir}/codex_diff.patch`;

  // ---------- PHASE: brief (author acceptance criteria + adjacent scan) ----------
  phase("brief");
  await agent({
    label: `author-brief-${id}`, phase: "brief", agentType: "fork",
    prompt: `Author ${briefPath} for Issue ${id}. MUST start with the VERBATIM CLAUDE.md
      §8.3.1 cap directive as the first content block. Include: acceptance criteria;
      "Files I have ALSO checked and they're clean: [...]" adjacent-file scan (§-1.2 step 2);
      output schema (§8.3.9). Spec + criteria ONLY -- no implementation reasoning.
      Commit the file. Do not build yet.`
  });

  // ---------- PHASE: codex_review_brief (5-cap loop; codex exec is EXTERNAL) ----
  const briefVerdict = await codexGateLoop({
    phase: "codex_review_brief", id,
    gateFile: `${codexDir}/codex_brief_verdict.txt`,
    forceFile: `${codexDir}/codex_brief_verdict_iter5_force_approve.txt`,
    bundle: [briefPath],                    // brief only -- context isolation
    kind: "brief"
  });
  log(`brief gate => ${briefVerdict}`);

  // ---------- PHASE: build (Claude writes the diff) ----------------------------
  phase("build");
  await agent({
    label: `build-${id}`, phase: "build", agentType: "fork",
    prompt: `Implement Issue ${id} against the APPROVED brief ${briefPath}.
      Commit the working-tree diff as ${diffPath}. No "while we're at it" scope creep.`
  });

  // ---------- PHASE: smoke_gate_a (offline + cheap real -- NO gpu/cohere money) -
  phase("smoke_gate_a");
  const gateA = await parallel([
    () => agent({ label: "smoke-unit", phase: "smoke_gate_a", agentType: "fork",
      prompt: `Run: python -m pytest tests/dr_benchmark tests/architecture -q.
        Then: python -m scripts.architecture.verify_lock  (expect exit 0).
        Then: invoke pathB_run_gate.preflight(offline=True).
        Emit a fenced block whose LAST line is "gate_a_unit: PASS" or "gate_a_unit: FAIL".` }),
    () => agent({ label: "smoke-contract", phase: "smoke_gate_a", agentType: "fork",
      prompt: `Run the per-role CONTRACT validators against tests/fixtures/ (NOT live):
        - Sentinel: assert yes=UNGROUNDED, no=grounded  (LETHAL polarity, §-1.1)
        - Judge: assert guided_choice parses the 5-enum {VERIFIED|PARTIAL|UNSUPPORTED|FABRICATED|UNREACHABLE}
        - Mirror: assert two-pass (RAG citation pass + non-RAG JSON verdict pass) parses
        Last line: "gate_a_contract: PASS" or "gate_a_contract: FAIL".` }),
    () => agent({ label: "smoke-cheap-real", phase: "smoke_gate_a", agentType: "fork",
      prompt: `Minimal REAL connectivity, 1 call each (the only live endpoints pre-rental):
        - 1 Serper POST ("metformin"); 1 Semantic Scholar GET (1 result);
        - 1 DeepSeek V4 Pro generation (Generator -- ONLY one of the 4 roles with a live endpoint).
        Last line: "gate_a_real: PASS" or "gate_a_real: FAIL".` })
  ]);
  const gateAPass = gateA.every(r => /:\s*PASS\s*$/m.test(r.text || ""));
  if (!gateAPass) throw new Error(`SMOKE GATE A FAILED -> back to build / URGENT issue. ${JSON.stringify(gateA.map(r=>r.text))}`);

  // ---------- PHASE: smoke_gate_b (only if a GPU is rented; else SKIP) ----------
  phase("smoke_gate_b");
  if (args.gpu_rented) {
    const gateB = await agent({ label: "smoke-gate-b", phase: "smoke_gate_b", agentType: "fork",
      prompt: `GPU is rented. One REAL per-role call to each Vast endpoint (Mirror/Sentinel/Judge)
        + confirm served_identity == pinned slug AND the role's output contract holds live.
        NOTE: Judge slug typo (lock line 77) fails until the lock-mutation Issue lands.
        Last line: "gate_b: PASS" or "gate_b: FAIL".` });
    if (!/gate_b:\s*PASS/.test(gateB.text || "")) throw new Error("SMOKE GATE B FAILED -- do not start the full sweep / sustained rental.");
  } else {
    log("Gate B skipped: no GPU rented. Full sweep / sustained spend NOT authorized.");
  }

  // ---------- PHASE: convey_diff (assemble diff + smoke + visual paths) ---------
  phase("convey_diff");
  const visualPaths = args.touches_web
    ? [`${codexDir}/visual/before.png`, `${codexDir}/visual/during.png`, `${codexDir}/visual/after.png`]
    : [];
  if (args.touches_web) {
    await agent({ label: "render-visual", phase: "convey_diff", agentType: "fork",
      prompt: `Render the changed web/ surface in a sandbox; capture 3 temporal screenshots
        (before/during/after a scripted interaction) to ${visualPaths.join(", ")}.` });
  }
  const diffBundle = [diffPath, briefPath, /* smoke summary file */ `${codexDir}/smoke_results.json`, ...visualPaths];

  // ---------- PHASE: codex_review_diff (5-cap; visual via codex exec -i) --------
  const diffVerdict = await codexGateLoop({
    phase: "codex_review_diff", id,
    gateFile: `${codexDir}/codex_diff_audit.txt`,
    forceFile: `${codexDir}/codex_diff_audit_iter5_force_approve.txt`,
    bundle: diffBundle,
    visual: args.touches_web ? { images: visualPaths, gateFile: `${codexDir}/codex_visual_audit.txt` } : null,
    kind: "diff"
  });
  log(`diff gate => ${diffVerdict}`);

  // ---------- PHASE: wrapup ------------------------------------------------------
  phase("wrapup");
  // CLOSE is NOT here: Codex APPROVE -> CI polaris/codex-required -> auto-merge -> issue auto-closes.
  // NEXT (git checkout -b bot/<next-issue>) is a shell step the operator/main turn runs AFTER merge,
  // with ZERO prose between merge and branch (§8.2). The workflow returns; it does not merge.
  return { issue: id, brief: briefVerdict, diff: diffVerdict,
           gate_a: "PASS", gate_b: args.gpu_rented ? "checked" : "skipped",
           note: "CLOSE+NEXT happen via CI gate chain + post-merge shell, not in this workflow." };
}

// ===== 5-cap Codex gate loop. codex exec is EXTERNAL: one foreground Bash step, =====
// ===== one-at-a-time (§8.4), env -u OPENAI_API_KEY (§8.3.7), 9-min timeout.      =====
// ===== Verdict = free-text greppable marker, parsed deterministically (NOT a     =====
// ===== StructuredOutput schema -- this session saw 23/24 schema agents not emit).=====
async function codexGateLoop({ phase: ph, id, gateFile, forceFile, bundle, visual, kind }) {
  phase(ph);
  for (let i = 1; i <= 5; i++) {
    // ONE agent, ONE codex exec shell call. The agent assembles the brief-for-codex
    // from `bundle`, runs codex exec foreground, captures stdout to `gateFile`,
    // appends to state/polaris_restart/iteration_trajectory.md (§8.3.5).
    const visualClause = visual
      ? ` Also run the VISUAL audit: env -u OPENAI_API_KEY codex exec -i ${visual.images.join(" -i ")} `
        + `--skip-git-repo-check - < ${id}_visual_brief.md > ${visual.gateFile}  (rubric: .codex/visual_audit_rubric.md).`
      : "";
    const r = await agent({
      label: `codex-${kind}-iter${i}-${id}`, phase: ph, agentType: "fork",
      prompt:
        `This is iter ${i} of 5 (§8.3.1 cap). Assemble the Codex review brief from: ${bundle.join(", ")}.
         The brief MUST front-load ALL findings, start with the verbatim §8.3.1 cap directive,
         hand Codex SPEC+DIFF+SMOKE only (no builder rationale -- context isolation), and demand the
         §8.3.9 output schema. Then run EXACTLY ONE foreground codex call (§8.4 one-at-a-time):
           env -u OPENAI_API_KEY codex exec --skip-git-repo-check - < ${id}_codex_brief.md > ${gateFile}
         (timeout 9m).${visualClause}
         Append iter ${i} finding-counts to state/polaris_restart/iteration_trajectory.md.
         Report the LAST "verdict:" line you parsed from ${gateFile}.`
    });
    const verdict = parseLastVerdict(r.text);  // greps /verdict:\s*(APPROVE|REQUEST_CHANGES)/, last match
    if (verdict === "APPROVE") return "APPROVE";
    if (i === 5) {
      // §8.3.1 force-APPROVE: write annotation file + ensure gateFile's LAST line is verdict: APPROVE,
      // capture residuals as follow-up Issues in issue_breakdown.md, log to iteration_trajectory.md.
      await agent({ label: `force-approve-${kind}-${id}`, phase: ph, agentType: "fork",
        prompt: `Iter-5 cap hit with REQUEST_CHANGES. Write ${forceFile} (cap timestamp, residual P0/P1,
          follow-up Issue IDs, link to user directive 2026-05-06). Append "# force-approved at iter 5 cap
          per CLAUDE.md §8.3.1" + a final "verdict: APPROVE" line to ${gateFile}. Append force-approval
          to state/polaris_restart/iteration_trajectory.md.` });
      return "FORCE_APPROVE";
    }
    // else: revise the brief/diff for iter i+1, then loop (ITERATE state).
    await agent({ label: `revise-${kind}-iter${i}-${id}`, phase: ph, agentType: "fork",
      prompt: `Codex iter ${i} returned REQUEST_CHANGES. Address every P0/P1 in ${gateFile}.
        ${kind === "diff" ? "Re-run SMOKE GATE A after edits." : "Revise the brief."} Prepare iter ${i+1}.` });
  }
}
```

**Where `codex exec` hooks in (the external part):** it is **not** a Workflow primitive. Inside `codexGateLoop`, a single `agent()` shells out to `env -u OPENAI_API_KEY codex exec ... > verdict.txt` (and `codex exec -i <png>` for visual). The Workflow tool only *spawns the agent* and *sequences the loop*; the review reasoning happens in the external Codex process. This is the honest seam — see §6(a).

---

## 3. THE SMOKE-BEFORE-SPEND GATE (I-meta-002 4-role pipeline)

**Two money gates, not one** — because the 3 new roles have **no endpoint until a GPU is rented** (Vast balance `$0`; Cohere Command A+ and Granite Guardian 4.1 are not on OpenRouter; Generator/DeepSeek V4 Pro is the *only* one of four with a live endpoint today). You literally cannot connectivity-probe Mirror/Sentinel/Judge before rental. So:

### Gate A — before ANY GPU / Cohere money (always runs, zero spend)

Mocks for the 3 new models live in **`tests/fixtures/`** (LAW II / §9.4): canned per-role response → assert *parsing/polarity/enum*. They validate the **output contract**, never inject fakes into a real run.

| Check | Command / mechanism | Pass assertion | Money? |
|---|---|---|---|
| Unit + fixture suites | `python -m pytest tests/dr_benchmark tests/architecture -q` | all green | none |
| Lock consistency | `python -m scripts.architecture.verify_lock` | exit 0 (slug/family/env triples match code) | none |
| Wiring shape | `pathB_run_gate.preflight(offline=True)` | OK (skips network + arch-coverage enforcement) | none |
| **Sentinel polarity** (LETHAL) | fixture: canned `<score>yes</score>` & `<score>no</score>` | `yes → UNGROUNDED/FABRICATED candidate`; `no → grounded` | none |
| **Judge enum** | fixture: vLLM `guided_choice` canned output | parses exactly one of `{VERIFIED\|PARTIAL\|UNSUPPORTED\|FABRICATED\|UNREACHABLE}` | none |
| **Mirror two-pass** | fixture: RAG-pass `<co>` span + non-RAG JSON verdict | both passes parse; `response_format` NOT sent in RAG mode | none |
| Serper reachability | 1 real POST, query `"metformin"` | HTTP 200 + non-empty results | ~1 cheap call |
| Semantic Scholar | 1 real GET, `limit=1` | HTTP 200 + 1 result | ~1 cheap call |
| Generator liveness | 1 real DeepSeek V4 Pro generation (tiny prompt) | non-empty completion; served==pinned | ~1 cheap call |

**Gate-A GREEN checklist (must all be true before spending a cent on GPU/Cohere):**
- [ ] `pytest tests/dr_benchmark tests/architecture` all pass
- [ ] `verify_lock` exit 0
- [ ] `preflight(offline=True)` OK
- [ ] Sentinel polarity fixture asserts `yes=UNGROUNDED`
- [ ] Judge 5-enum `guided_choice` fixture parses
- [ ] Mirror two-pass (RAG citation + non-RAG JSON) fixture parses
- [ ] Serper 200 / S2 200 / DeepSeek generation non-empty (3 cheap real calls)

### Gate B — GPU rented, before the full sweep / sustained rental

Once (and only once) a GPU is rented, **1 real per-role call** to each Vast endpoint confirms `served_identity == pinned_slug` AND the live output contract holds (Sentinel polarity live, Judge enum live, Mirror two-pass live). Only after Gate B passes does the expensive path fire (`run_honest_sweep_r3` full power — `PG_SWEEP_FETCH_CAP=500`, `PG_LIVE_MAX_EV_TO_GEN=300`, 5×$0–$40/run per `smoke.md` — plus *sustained* Vast rental).

> **Frozen-by-design caveat:** while `polaris_runtime_lock.yaml status == codex_approved_pending_operator_signature`, `pathB_run_gate._assert_architecture_coverage()` **raises and refuses all non-offline smokes**. So the **live 4-role smoke (Gate B) is unavailable today**; only Gate A runs until `verify_lock` propagation promotes the lock to `status: locked`. Additionally, the **Judge slug typo** (lock line 77 `qwen/qwen-3.6-35b-a3b`) would fail its Gate-B served==pinned check until the operator-signed lock-mutation Issue (D5, already APPROVED) lands the corrected `qwen/qwen3.6-35b-a3b`.

---

## 4. HOW IT PREVENTS DIFF / DRIFT

The 12-step anti-drift order (I-meta-001 #933) is a **conditional applies-when preamble**, not a 12-action ritual per task. It fires only when the PR touches the `architecture-conformance.yml` `paths:` filter (`src/polaris_graph/**`, `scripts/dr_benchmark/**`, `scripts/architecture/**`, `config/architecture/**`, `docs/canonical_pin.txt`, `.env.example`, `docs/agent_architecture.md`, `docs/architecture.md`). Non-arch PRs skip it cleanly — the CI gate already does.

| Step(s) | What it asserts | Automation that enforces it |
|---|---|---|
| 1 branch == active_issue_id | branch hygiene | `weekly_drift_report.check_branch_active_issue_conformance` |
| 2 no untracked decision docs | `_lock`/`_sota`/`_pick`/`_audit` tracked | `weekly_drift_report.find_untracked_decision_docs` |
| 3 stale model refs carry `status: superseded` | frontmatter discipline | `weekly_drift_report.find_stale_model_refs` |
| 4–7 lock = source of truth; propagation manifest; canonical pin tracks lock SHA; N-way `all_distinct` family check | runtime conformance | **`scripts/architecture/verify_lock.py`** (`verify_lock_against_code`, `check_propagation_manifest`) |
| 8 distinct per-role env vars | `PG_GENERATOR/MIRROR/SENTINEL/JUDGE_MODEL`; `PG_EVALUATOR_MODEL` legacy maps to `mirror`, deprecated 2026-09-06 | `verify_lock` + lock `env_vars` block |
| 9 pathB gate architecture-coverage | refuses smokes while `status != locked` | `pathB_run_gate._assert_architecture_coverage` (lines ~311–317) |
| 10 update stale surfaces | `.env.example`, `agent_architecture.md`, `architecture.md` | `weekly_drift_report.py` |
| 11 PR attestation artifact | `.codex/<id>/architecture_conformance_attestation.md` with 7 required-true assertions + `lock_sha256` + Codex trail paths | **CI gate `architecture-conformance-required`** (parses the YAML footer) |
| 12 weekly drift report | scheduled drift scan | `scripts/architecture/weekly_drift_report.py` (schedulable via CronCreate) |

**Re-grounding (the literature's core anti-drift fix).** The §3.1 intra-task drift ritual (every 10 tool calls / 15 min) must **re-read the runtime *lock*** (`polaris_runtime_lock.yaml`), not just the issue row. As context fills, the spec is the first thing to fall out of the window; re-injecting the machine-readable lock is exactly the "configurancy / specification-locking + periodic re-verification" pattern. The mechanical question the agent asks is *"which lock checkpoints are unsatisfied?"* (a `verify_lock` query), not *"do I remember the architecture?"*. This is what turns the 4-role drift (the failure that produced I-meta-001) into a structurally-prevented class.

**Why this maps to 2026 best practice:** spec-as-executable-contract + conformance suite (`verify_lock` + CI gate) = the documented fix for "tests pass but coherence collapses." A green test suite is *not* evidence of spec conformance; the lock + attestation gate is. The two-family (now N-way `all_distinct`) generator/evaluator invariant is the literature-confirmed mitigation for same-family judge bias ("popularity trap") — do not relax it for convenience.

---

## 5. WHAT TO CODIFY WHERE

| Artifact | Location | Why there | New convention? |
|---|---|---|---|
| **Standing-loop section** (the §1 state machine + governing principle) | **CLAUDE.md amendment** — new section, e.g. `§3.0.1 Standing task-execution loop` | It is a binding process rule. **Delegates by §-number** to existing rules (build→§3.0; smoke→§-1.2 step 3; convey→§8.3.3 + REVIEW_BRIEF_FORMAT; review→§3.0 + red_team_checklist + §-1.1; iterate→§8.3; cap→§8.3.1; advance→§8.3.10 + issue_breakdown.md). Restates nothing. | No (extends CLAUDE.md) |
| **`polaris_task_cycle.js`** (the §2 template) | **`.claude/workflows/polaris_task_cycle.js`** (version-controlled, appears in `/` autocomplete) | Per-team shared, committed; invokable per Issue. Dir does not exist yet → this sets the convention. | **Yes** — `.claude/workflows/` |
| **Smoke-before-spend two-gate checklist** (the §3 tables) | **Extend `scripts/dr_benchmark/smoke.md`** — add a "4-role Gate A / Gate B" section | smoke.md is already the smoke runbook; fork = drift. Add, don't duplicate. | No (extends existing doc) |
| **12-step applies-when preamble** (the §4 table) | Short **doc** `docs/anti_drift_preamble.md` referenced from the CLAUDE.md amendment | Keeps CLAUDE.md lean; the preamble is a checklist keyed to the CI `paths:` filter. | No |
| **Verdict/attestation artifacts** | **REUSE existing**: `codex_brief_verdict.txt`, `codex_diff_audit.txt`, `architecture_conformance_attestation.md` (template `.codex/architecture_conformance_attestation_template.md`), `codex_visual_audit.txt` (rubric `.codex/visual_audit_rubric.md`), CI gates `polaris/codex-required` + `architecture-conformance-required` + `codex-visual-required` | Inventing parallel artifacts is the contradiction risk. The workflow *fills* these existing files. | No (reuse) |

---

## 6. HONEST GAPS (where Workflow does NOT cleanly fit the loop)

1. **`codex exec` is external to the Workflow spawn model.** The Workflow tool spawns *Claude/fork agents*; it cannot "review with Codex." Codex review only happens because an agent shells out to `codex exec`. **Workaround:** the `codexGateLoop` wraps each round in one `agent()` whose sole job is one foreground `codex exec` call (§8.4 one-at-a-time, §8.3.7 `env -u OPENAI_API_KEY`, 9-min timeout) → captured to the existing verdict file. The Workflow drives sequencing; it does not "decide."

2. **No mid-run user input + resume-only-within-session.** A 5-round Codex iteration cannot be one uninterrupted Workflow run if a round needs human steering, and exiting Claude Code mid-run restarts fresh next session. **Workaround:** treat each Issue's cycle as resumable-within-session; write `smoke_results.json` + verdict files + `iteration_trajectory.md` to disk after every phase so a fresh session can re-read state and resume from the last completed phase manually. Long/cross-session work splits into per-Issue runs.

3. **Schema-agent flakiness (this session: 23/24 schema-bound verifiers did NOT emit).** **Workaround (already in §2):** do NOT bind the verdict to a `StructuredOutput` tool call as the primary channel. Use a **free-text greppable marker** — the existing `verdict:` last-line parse of `codex_brief_verdict.txt` / `codex_diff_audit.txt` (the Ralph "Completion Promise" pattern) — + a deterministic parse step. If a schema is wanted, keep it minimal (verdict + findings array) and add a parse-retry that re-prompts only when the marker is absent.

4. **D4 branch protection (highest-severity).** The CLOSE→auto-merge→auto-close chain is **not live**: polaris `main` has `required_status_checks=[]` and `enforce_admins=false`, so `polaris/codex-required` is not enforced. **Operator-side fix required** (add the required check + `enforce_admins=true`). Until then, CLOSE is a manual operator merge at `git log` review; the workflow still stops at `wrapup` and never merges.

5. **Live 4-role smoke (Gate B) is frozen by design.** `pathB_run_gate._assert_architecture_coverage()` raises while `lock status == codex_approved_pending_operator_signature`. Only Gate A runs until `verify_lock` propagation promotes the lock to `status: locked`. Plus the Judge slug typo (lock line 77) must be fixed via the D5-APPROVED lock-mutation Issue before its Gate-B served==pinned probe can pass.

6. **Visual review needs `codex exec -i` on a rendered screenshot.** The Workflow can *stage* the artifact (render the web surface, capture 3 temporal screenshots), but the visual judgment is the external `codex exec -i <png>` call against `.codex/visual_audit_rubric.md`, written to `codex_visual_audit.txt` and gated by `codex-visual-required`. Non-visual Issues skip cleanly (the CI gate already does). **Workaround:** §2's `convey_diff` phase renders + attaches; `codexGateLoop`'s `visualClause` runs the `-i` call when `touches_web`.

7. **Cost is real and post-hoc.** Many spawned agents → meaningfully higher token usage than turn-by-turn, with no real-time per-run cap. **Workaround:** profile the first `polaris_task_cycle` run via `/usage`; keep `parallel()` only on the genuinely-fanned smoke + self-audit phases; route non-critical aggregation to a smaller model per-stage if needed.

---

**One open operator decision carried forward (does not block this proposal):** `active_issue.json` D6/D7 bind **both** Mirror and Sentinel to **Vast.ai self-host** (the binding APD source). `feasibility_synthesis.md` *recommends* Cohere-direct (Toronto, Canada-OK, full-precision) for the Mirror as a hardware-burden/calibration win. This proposal honors the binding D6/D7 (Vast self-host) and flags Cohere-direct as a **pending operator choice**, not the design — to be resolved on the D5 lock-mutation Issue alongside the Judge-slug fix.

This is a proposal for operator approval + Codex review, not a final lock. The state machine extends §3.0/§8.3.x/§-1.1/§-1.2/§10 by delegation; nothing here grants Claude a gate or merge authority.