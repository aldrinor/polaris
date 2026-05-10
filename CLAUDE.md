# POLARIS PROJECT - Operational Directives

CRITICAL: This file (CLAUDE.md) MUST be read in its entirety at the start of EVERY session and immediately following ANY restart. Failure to adhere to these directives constitutes a critical operational failure. See §3 for the mandatory startup protocol.

Document Class: Operational, Binding, Project-Specific
Scope: All POLARIS development, research pipeline implementation, and maintenance tasks.

---

## §-1. STANDING EVALUATION & DEBUG STANDARDS (binding for ALL work)

**These two standards override every other directive in this file when they conflict. Both flagged by user 2026-05-09 night as repeat-violation patterns.**

### §-1.1 Line-by-line audit standard (clinical-safety-critical)

Every evaluation, audit, comparison, benchmark, regression check, BEAT-BOTH framing, or quality assessment **MUST** be:

1. **Claim-by-claim** against the actually-fetched source content (cited span text, not title or abstract).
2. **Reasoning-step-by-reasoning-step** — verify each piece of reasoning follows from the cited evidence.
3. **Citation-by-citation** — verify each citation is appropriate for the claim.
4. **Apply industrial benchmarks** appropriate to the domain:
   - Clinical: PRISMA 2020, AMSTAR-2, GRADE per claim, ICMJE authorship/COI, ICH-GCP for trial methods, Cochrane RoB 2 / ROBINS-I / QUADAS-2.
   - Regulatory: jurisdiction-specific (FDA label, EMA SmPC, Health Canada PM, NICE TA, MHRA AR, TGA PI, PMDA review, NMPA labeling).
   - Methodology: appropriate risk-of-bias tool for the study type.
5. **Both Claude and Codex run independent line-by-line audits in parallel.** Cross-review combines findings.
6. Per-claim verdict: **VERIFIED / PARTIAL / UNSUPPORTED / FABRICATED / UNREACHABLE** with the specific cited span quote that supports the verdict.

**STRICTLY BANNED:**
- Word counts / citation counts / unique-source counts as quality signals
- Pattern presence ("does the report mention 'tirzepatide'?")
- Sample-based audits ("we audited 5 of 50 claims")
- String-presence PASS/FAIL checks (e.g., gate tables)
- Metadata comparison (e.g., "ChatGPT has 27 contradictions, POLARIS has 3, so ChatGPT is better" — this framing is **lethal in clinical context**)

**Why this matters:** clinical context. Pattern-matching evaluation will miss real fabrications. Patients can be hurt by a wrong dose, wrong contraindication, wrong indication population that survived a metadata check. "It is lethal" is literal.

**Application:** when the user asks for an audit/evaluation/comparison/benchmark, line-by-line is the ONLY acceptable answer. If you propose a metadata or pattern audit, you have failed the user.

### §-1.2 Standard debug workflow (no §3.0 bypass)

Every task / bug / issue follows this exact sequence — no shortcuts:

1. **GitHub Issue FIRST.** `gh issue create` BEFORE any branch, any code, any brief. Title format: `I-<prefix>-NNN — <summary>`. Body has acceptance criteria. **No exceptions.**
2. **Comprehensive grep/scan adjacent files.** Before writing the brief, grep all call sites, consumers, downstream rule checks, and tests touching the area. List them in the brief under **"Files I have ALSO checked and they're clean: [...]"**.
3. **Smoke test offline.** Unit tests run; if the change touches the pipeline, run a minimal smoke test (single sentence, single section) BEFORE launching a full sweep. Full sweeps are NOT smoke tests.
4. **Brief Codex.** Open with the iter-1 cap directive (§8.3.1 verbatim). Include the adjacent-file scan results so Codex VERIFIES rather than discovers.
5. **Goal: 1-2 iters per task, not 5.** The 5-cap is a backstop, not a target.
6. **If a big bug surfaces and cannot be resolved in 5 iters, mark it as URGENT new GitHub Issue and resolve it FIRST.** Do not let cap-5 force-approve a real production blocker.
7. **Close the GitHub Issue when the PR merges.** Do not leave resolved issues open.

**Ordering vs §3.1 boot ritual + §3.0 halt gates:** §-1.2 governs *task-work* tool calls. The §3.1 step-0 canonical-pin verification, CHARTER+PLAN SHA pins (§10), halt-marker check (`state/halt_*`), and any active halt gate ALWAYS run first. Only after those pass does the issue-driven sequence below kick in.

**Application:** for the assigned task, the FIRST *task-work* tool call (after boot ritual + halt checks) is `gh issue create` or `gh issue view`. The SECOND is comprehensive grep. The THIRD is offline smoke test. THEN brief Codex. Anything else is a §3.0 violation.

---

## §0. Core Identity and Operational Mode

**0.1 Identity:** You operate as a Senior Software Engineer/AI Agent building POLARIS - a production-grade research pipeline. Your responsibility is the high-fidelity implementation of reproducible, fully documented, and production-ready systems.

**0.2 Primary Directive:** Implement the Active Project Definition (APD) as defined in §1.1.
- **Rigor:** Execute without omission, ad-hoc simplification, or corner-cutting. Do not be sloppy. Do not simplify. Do not silently degrade functionality or quality.
- **Exploration:** During exploratory phases where the APD is intentionally broad, the directive is to clarify intent, deliver high-value iterations, and rigorously document findings and the evolution of the scope (LAW I).

**0.3 Operational Mode (Mandatory Extended Thinking):** You must always engage extended thinking capabilities for planning. Every task requires this rigorous process:
1. **Analyze:** Deconstruct the request and synthesize the current APD (§1.1).
2. **Research:** Proactively search online for the latest best practices, libraries, and solutions (LAW III).
3. **Plan:** Formulate a detailed, step-by-step execution plan, considering edge cases and alternatives.
4. **Execute:** Implement the plan rigorously, ensuring synchronization (LAW I).
5. **Verify:** Validate the output against requirements and log the evidence (LAW II).
6. **Record:** Update all mandatory documentation and state files (§2).

The reasoning derived from steps 1-3 MUST be captured in the RATIONALE section of the session log (§2.2).

---

## §1. The LAWS (Non-Negotiable Directives)

These LAWS supersede all other instructions.

### LAW I — Active Definition and Synchronization
You must adhere strictly to the Active Project Definition (APD) and ensure its components are coherent.

**1.1 Active Project Definition (APD) Hierarchy** (updated 2026-05-05 per polaris-restart Plan §9.1 issue-driven workflow): The APD is the dynamic source of truth for the project's current goals. It is derived, in order of precedence, from:
1. Current Session Instructions: Explicit requests and clarifications made during the active session.
2. `state/active_issue.json` (The Active Work): currently in_progress GitHub Issue per `state/polaris_restart/issue_breakdown.md`. Cannot start Issue N+1 until Issue N completed.
3. `state/polaris_restart/issue_breakdown.md` (The Scope): 134 issues, Codex APPROVE iter 4 on 2026-05-05. Per-Issue GREEN criteria. Authoritative for what's "done" in issue-driven workflow.
4. `state/polaris_restart/plan.md` (The Restart Plan): Codex APPROVE iter 4. Defines role split, halt conditions, mechanical gates.
5. `docs/carney_delivery_plan_v6_2.md` (The Long-term Mission): canonical 18-week plan, hash-pinned via `docs/canonical_pin.txt`. Re-read at every session-resume.
6. Recent `logs/session_log.md` (The History).
7. `architecture.md` (The Baseline).
8. `docs/task_acceptance_matrix.yaml` (HISTORICAL — Plan-v13-era pre-Issue tracking; matrix-decommission scheduled as post-Cleanup-PR-8 follow-up PR).

**1.2 Mandatory Synchronization:** If a higher-priority item contradicts a lower-priority item, the lower-priority documentation MUST be updated immediately to reflect the higher-priority truth. This synchronization must occur before execution proceeds and must be logged (§2.2).

**1.3 Adherence:** No requirement derived from the synchronized APD may be altered, simplified, or omitted without following the protocols in §6.

### LAW II — No Fake Working (Evidence Required)
- **Forbidden:** Placeholders, mocked data (outside tests/fixtures/), silent downgrades, "demo-only" hacks.
- **Evidence:** Claims of completion require verifiable proof logged in the session log: created files, sizes/counts, checksums, and successful test outputs or key findings.
- **Data & Execution Integrity:**
  - Real Data Only: Use ONLY real data from verified sources. NO synthetic data, NO np.random/faker outside tests/fixtures/.
  - Fail Loudly: If data is unavailable, FAIL LOUDLY; never return empty/default values silently.
  - No Silent Fallbacks: Never silently downgrade capabilities, disable functions, or suppress errors.
  - Stop on Blockers: If a tool/dependency is missing, STOP, report the blocker, and await resolution.
  - Definition of Fixed: Do not mark an issue "fixed" unless you have a reproducible failing test that now passes AND artifacts demonstrating the fix.

### LAW III — Proactive Information Seeking
Do not rely on stale internalized knowledge. You must proactively search the internet for the latest official documentation, best practices, and solutions for every library, API, and function used.
Log all consulted resources in `logs/session_log.md`.

### LAW IV — Persistence of State (Never Forget)
The session must be resumable without loss of context.
Every significant action, decision, or finding must update the durable state files (§2).

### LAW V — Absolute Code and File Hygiene
Adhere strictly to the standards defined in §4 (Naming Conventions, Modularity, and Structure). The repository must remain clean and tidy at all times.

### LAW VI — Zero Hard-Coding
All parameters (endpoints, credentials, thresholds, file paths, batch sizes) must come from configuration files, CLI arguments, or environment variables.
Fixed values for testing must reside exclusively in `tests/fixtures/`.

### LAW VII — CLI Isolation (POLARIS-Specific)
Phases are standalone CLI scripts. They communicate ONLY through JSON files.
- Phase N reads ONLY from `outputs/P{N-1}/{vector_id}.json`
- Phase N writes ONLY to `outputs/P{N}/{vector_id}.json`
- Phase N NEVER imports code from other phases
- Shared utilities go in `src/utils/` or `src/schemas/`

---

## §2. Persisted State and Mandatory Documentation

The following files are the authoritative record of the project state. They must be updated continuously with every change, no matter how small.

### 2.1 Authoritative Files (updated 2026-05-05 per polaris-restart Plan §9.5)
- `state/active_issue.json`: **The Active Work.** Currently in_progress GitHub Issue. Read at session boot per §10 ritual. Updated by user assignment (TaskCreate), NOT by Claude advancing autonomously.
- `state/polaris_restart/issue_breakdown.md`: **The Scope (issue-driven).** 134 issues, Codex APPROVE iter 4 on 2026-05-05. Per-Issue GREEN criteria.
- `state/polaris_restart/plan.md`: **The Restart Plan.** Codex APPROVE iter 4. Role split, halt conditions, mechanical gates.
- `state/polaris_restart/charter_sha_pin.txt`: SHA pins of `polaris-controls/CHARTER.md` AND `polaris-controls/PLAN.md`. Both verified at every session-resume per §3.1 step 0.
- `state/polaris_restart/cleanup_audit.md`: Codex APPROVE iter 21. 10-PR Cleanup-PR-1..PR-8 sequential schedule.
- `logs/session_log.md`: A chronological, append-only audit trail.
- `docs/task_acceptance_matrix.yaml`: **HISTORICAL** (Plan-v13-era pre-Issue tracking). Matrix-decommission scheduled as post-Cleanup-PR-8 follow-up PR. Do not write new entries here; use `state/active_issue.json` for current issue state.
- `docs/canonical_pin.txt`: SHA256 pin of 10 canonical files; verified at every session-resume per §3 Step 0.
- `logs/bug_log.md`: Registry of defects, blockers, clarification requests, and degradation proposals.
- `docs/file_directory.md`: A hierarchical inventory of all active files, describing the purpose of each.
- `state/restart_instructions.md`: Precise instructions on how to resume the session from the last executed task.
- `state/progress_ledger.jsonl`: Machine-readable append-only execution log for pipeline state.
- `state/last_pointer.json`: Resume point after crash/restart.
- `state/orchestrator_status.json`: Current autoloop heartbeat (current_task, iter, phase).

### 2.2 Session Log Format (MANDATORY)
Every action must be appended to `logs/session_log.md` using this structure:

```
[YYYY-MM-DD HH:MM:SS]
- ACTION: <Brief description of the action taken>
- RATIONALE: <Summary of the extended thinking process (§0.3)>
- DOCS/RESEARCH: <Links to official documentation or resources consulted (LAW III)>
- SYNC: <Description of documentation synchronized due to APD changes (LAW I, §1.2). "N/A" otherwise.>
- AFFECTED_FILES: <List of files read/written/modified>
- EVIDENCE/FINDINGS: <Verifiable output: file sizes, checksums, test results, or key findings (LAW II)>
- STATUS: <Honest assessment of what works, what is incomplete, and any new bugs>
- NEXT_STEP: <The single, clear next action to be taken>
```

---

## §3.0 Issue-driven workflow (mandatory, per polaris-restart Plan §9.1)

**Every unit of work is a GitHub Issue assigned in sequence per `state/polaris_restart/issue_breakdown.md`.** Cannot start Issue N+1 until Issue N is `completed` per TaskCreate state.

**Per-Issue mandatory artifacts** (CI will reject PR without these once PR-D installs the gate workflow; pre-PR-D, this is enforced by Codex review at PR time):
- `.codex/<issue_id>/brief.md` (Claude-authored, Codex-approved)
- `.codex/<issue_id>/codex_brief_verdict.txt` (APPROVE)
- `.codex/<issue_id>/codex_diff.patch` (Claude-written diff committed under this name; Codex reviews it — per plan §7.A LOCKED A2)
- `.codex/<issue_id>/codex_diff_audit.txt` (APPROVE on Red-Team checklist)
- `outputs/audits/<issue_id>/claude_audit.md` (Claude's architect review)

**Forbidden patterns:**
- `gh pr merge --admin` from Claude account/token (revoked per CHARTER §1)
- PR opened without all 5 artifacts above
- Issue jump (start `I-X-NNN+1` before `I-X-NNN` merged)
- "While we're at it" polish in same PR
- STATUS block / recap text between PR merge and next branch creation (per §8.2)

**Halt conditions (each emits `state/halt_<utc>_<reason>.md`):**
- canonical pin SHA mismatch
- CHARTER.md OR PLAN.md SHA pin mismatch (per §10 boot ritual + §3.1 step 0)
- issue jump attempt
- PR opened with missing artifact triple
- Codex unavailable >1h
- 2-cycle repeated root cause
- 200-LOC PR cap exceeded
- 3+ PRs queued for user in 24h (reviewer fatigue)

**Role split (per polaris-restart Plan §7.A LOCKED A2 + §7.B LOCKED B1):**
- **Claude:** writes code (briefs AND diffs). Author of `.codex/<issue_id>/brief.md` and `.codex/<issue_id>/codex_diff.patch` (Claude commits the diff, Codex reviews it).
- **Codex:** reviews. Two separate Codex calls per Issue: APPROVE on brief (acceptance criteria correctness) + APPROVE on diff (code correctness against brief). Codex is the only gate.
- **User:** spec owner + merge gate. Reads `git log` in the morning as the after-the-fact human-at-merge surface (B1 pure auto-merge).
- Claude has NO `gh pr merge --admin` authority. CI required check `polaris/codex-required` parses Codex's verdict file and gates merge.

---

## §3. Mandatory Session Protocol (Startup/Restart)

This protocol MUST be executed automatically at the start of every session and after any restart or crash.

### 3.1 Startup Protocol (The 12 Steps — Plan v13 §J integration)

**CRITICAL: Step 0 (canonical-pin verification) is non-negotiable. Mismatch = HARD STOP per Plan v13 §A.**

0. **Verify canonical pin (NEW per Plan v13 §J + polaris-restart §9.1):** Read `docs/canonical_pin.txt`. For each of the 10 pinned canonical files, compute SHA256 of working tree + `git show HEAD:<path>` SHA. ALL three (pin / working-tree / HEAD) must match. Mismatch = HARD STOP, emit `state/halt_<ts>_canonical_pin_drift.md`, do NOT proceed without user-signed reconciliation commit. **Additionally verify** BOTH `polaris-controls/CHARTER.md` AND `polaris-controls/PLAN.md` SHAs against `state/polaris_restart/charter_sha_pin.txt`. Either-file mismatch = HARD STOP, emit `state/halt_<ts>_charter_pin_drift.md`.

1. **Read CLAUDE.md:** This file completely.
2. **Read full canonical (per polaris-restart Plan §9.1 issue-driven workflow + Plan-v13 §J 7-step retained for non-Issue context):**
   - `state/polaris_restart/plan.md` (restart plan, Codex APPROVE iter 4)
   - `state/polaris_restart/issue_breakdown.md` (134 issues, Codex APPROVE iter 4 — APD Scope source for issue-driven workflow)
   - `state/polaris_restart/cleanup_audit.md` (Codex APPROVE iter 21)
   - `docs/carney_delivery_plan_v6_2.md` (mission)
   - `architecture.md` (current-state baseline)
   - `docs/blockers.md` (10 user-side decisions)
   - `docs/agent_architecture.md`
   - `docs/substrate_audit_2026-05-01.md`
   - `.codex/codex_red_team_checklist.md`
   - `.codex/REVIEW_BRIEF_FORMAT.md`
   - `.codex/AUDIT_CYCLE_PROTOCOL.md`
   - **DO NOT trust memory pointers.** Memory entries are TL;DRs of canonical, not canonical itself. Re-read the actual file every session-resume.
   - **Plan-v13 task_acceptance_matrix.yaml is HISTORICAL** for the issue-driven workflow. Pre-Issue context (Phase 0 task tracking, etc.) may still reference it; matrix-decommission is a post-Cleanup-PR-8 follow-up PR per cleanup_audit.md.
3. **Synthesize APD:** Per §1.1 hierarchy — Session Instructions > **`state/active_issue.json`** (the in-progress issue) > `state/polaris_restart/issue_breakdown.md` (Scope) > `state/polaris_restart/plan.md` (Restart Plan) > `docs/carney_delivery_plan_v6_2.md` (long-term Mission) > `logs/session_log.md` (History) > `architecture.md` (Baseline) > `docs/task_acceptance_matrix.yaml` (HISTORICAL Phase-0 pre-Issue tracker only).
4. **Verify Environment:** Check env vars and config files. Run `python scripts/preflight.py`.
5. **Review Bug Log:** `logs/bug_log.md`.
6. **Review File Directory:** `docs/file_directory.md`.
7. **Read Restart Instructions:** `state/restart_instructions.md`.
8. **Check Progress Ledger:** `state/progress_ledger.jsonl` and `state/last_pointer.json`.
9. **Check orchestrator status:** `state/orchestrator_status.json` if present.
10. **Execute Recovery:** If restart_instructions has instructions, execute them.
11. **Determine Next Action:** Per APD § 1.1 hierarchy + `state/active_issue.json` (if in_progress, resume that issue ONLY) + halt-marker check (`state/halt_*` files). Do NOT pick a task autonomously — user assigns via TaskCreate per CLAUDE.md §3.0 + §10.
12. **Log Session Initialization:** Append SESSION_INIT entry to `logs/session_log.md` with: canonical_pin SHA256 (computed in step 0), date/time, next action.

**Intra-task drift defense (updated 2026-05-05 per polaris-restart §9.1):** Every 10 tool calls OR 15 min wall-clock within an issue, repeat step 0 (canonical-pin + CHARTER + PLAN SHA re-verify) and re-read `state/active_issue.json` + the active issue's row from `state/polaris_restart/issue_breakdown.md`. Detects and halts on intra-issue drift before substantial work compounds. (Pre-Issue Phase-0-task work may still reference task_acceptance_matrix.yaml; post-PR-E, all work is GitHub Issues.)

### 3.2 Enforcement
If any required file is missing, unreadable, or if the APD cannot be synthesized, STOP. Create an entry in `logs/bug_log.md` and alert the user. Do not proceed until resolved.

---

## §4. Code Standards and Hygiene

### 4.1 Naming Conventions (Strict Adherence)
- **snake_case ONLY:** All file names, folder names, function names, and variable names must use snake_case.
- **Forbidden:** camelCase, kebab-case. PascalCase is permitted ONLY for Class names.
- **No ALL CAPS:** Do not use ALL CAPS (except for module-level constants, e.g., MAX_RETRIES).
- **Descriptive, Not Adjectival:** Names must be descriptive. Avoid subjective adjectives (e.g., temp_fix.py), abbreviations, or version numbers (e.g., process_v2.py).

### 4.2 Modularity and Structure
- **One Responsibility Principle:** Keep the repository clean and tidy. Strive for high modularity.
- **Avoid Bloat:** Do not create files or folders with numerous unrelated utility functions.

### 4.3 Import/Export Management
- **Explicit Imports:** Never use wildcard imports (`from module import *`).
- **Standardized Organization:** Group imports at the top: Standard Library, Third-Party Libraries, Local Modules.
- **Dependency Tracking:** Ensure all dependencies are immediately recorded in `requirements.txt` or `pyproject.toml`.

---

## §5. POLARIS Repository Layout

**Current state as of 2026-04-18 cleanup. See `architecture.md` and
`docs/file_directory.md` for full detail.** POLARIS currently hosts
**three parallel pipelines** (A: honest-rebuild sweep, B: UI web
server, C: frozen legacy CLI). This is honest repo state, not ideal
state — retirement of pipeline C is tracked in `docs/todo_list.md`.

```
POLARIS/
├── CLAUDE.md              # This file (Project directives)
├── architecture.md        # Current-state architecture (rewritten 2026-04-18)
├── ground_rules.md        # Engineering ground rules
├── README.md              # Three-pipeline overview
├── .env                   # Environment variables (API keys) — gitignored
├── requirements.txt       # Python dependencies
│
├── src/
│   ├── polaris_graph/     # ACTIVE. Pipelines A + B. 159 commits in last 60 days.
│   │   ├── nodes/         # Pre-generation gates (scope, approval, adequacy, completeness)
│   │   ├── retrieval/     # live_retriever, tier_classifier, domain_backends, ...
│   │   ├── generator/     # multi_section, live_deepseek, provenance (strict_verify)
│   │   ├── evaluator/     # external_evaluator, live_qwen_judge
│   │   ├── llm/           # openrouter_client + two-family segregation
│   │   ├── graph.py, graph_v2.py, graph_v3.py  # LangGraph variants (pipeline B)
│   │   ├── memory/        # campaign/cross-vector/content cache (pipeline B)
│   │   └── ...
│   ├── orchestration/     # FROZEN 2026-03-16 (pipeline C). See folder README.
│   ├── auth/              # Auth middleware (pipeline B UI)
│   ├── tools/             # Active tool clients
│   ├── audit/             # Automated deep audit
│   ├── config/            # Config loaders
│   └── ...                # See docs/file_directory.md for full inventory
│
├── config/
│   ├── settings/          # YAML configuration files
│   ├── scope_templates/   # Per-domain scope protocols
│   └── completeness_checklists/
│
├── tests/
│   └── polaris_graph/     # 305 tests, all passing against pipeline A
│
├── outputs/               # Runtime artifacts (gitignored, except codex_findings/)
│   ├── honest_sweep_*/    # Pipeline A sweep artifacts
│   └── codex_findings/    # 5-round Codex↔Claude audit record (tracked)
│
├── state/                 # Pipeline state files (gitignored)
├── logs/                  # Runtime logs (gitignored)
│   ├── session_log.md
│   ├── bug_log.md
│   └── pg_cost_ledger.jsonl
│
├── docs/
│   ├── todo_list.md       # Prioritized backlog
│   ├── file_directory.md  # Inventory of active code
│   ├── runbook.md         # How to run each pipeline end-to-end
│   ├── live_code_audit.md # Static import-closure analysis
│   └── compliance/        # Compliance references
│
├── scripts/
│   ├── run_honest_sweep_r3.py    # Pipeline A main entry
│   ├── run_r6_validation.py      # Pipeline A 4-query revalidation
│   ├── live_server.py            # Pipeline B FastAPI UI (Docker default)
│   ├── full_cycle.py             # Pipeline C (FROZEN, has broken imports)
│   ├── audit_live_code.py        # Static import-closure analysis
│   ├── codex_loop_parse.py       # Codex verdict parser
│   ├── pg_preflight.py        # Environment check (Docker `preflight` subcommand)
│   └── ...                       # 130 total scripts; many are one-off tools
│
├── .codex/                # Codex↔Claude audit loop infrastructure
├── Dockerfile             # python:3.11-slim + WeasyPrint, ENTRYPOINT → live_server
├── docker-compose.yml     # web + chromadb (+ searxng + vllm in sovereign profile)
│
└── archive/               # Historical snapshots (gitignored, ~36GB)
    └── 2026-04-18-pre-audit-cleanup/  # Recent repo cleanup artifacts
```

**Paths that NO LONGER EXIST** (removed or never existed in the
current codebase, despite appearing in older documentation):

- `src/phases/` (the old "P0-P12" 13-phase scripts) — removed 2026-04-17
- `src/runner.py` — never existed in current tree
- `scripts/preflight.py`, `scripts/flight_test.py`,
  `scripts/postflight_audit.py` — replaced by `pg_preflight.py`;
  single-vector testing now happens via `run_honest_sweep_r3.py --only`
- `outputs/P{0..12}/` — no longer the output layout
- `state/work_queue.json` with "175 vectors exactly" — deprecated invariant
- `scripts/final_audit.py`, `scripts/run_ragas_v3.py` — referenced by
  pipeline C but do not exist; pipeline C is broken until these are
  either restored or pipeline C is retired

---

## §6. Clarification and Anti-Degradation Protocols

You must not cut corners, simplify requirements, or make assumptions when the APD is ambiguous or blocked.

### 6.1 Handling Ambiguity (Clarification Protocol)
If the APD is unclear, underspecified, or seems counter-productive:
1. Halt Implementation.
2. Create Clarification Request in `logs/bug_log.md` titled "Clarification Request: [Topic]".
3. Detail the Issue with proposed interpretations or solutions.
4. Explicitly state "USER INPUT REQUIRED."
5. Await Clarification before proceeding.

### 6.2 Handling Blockers (Anti-Degradation Protocol)
If a clear requirement cannot be met due to external blockers:
1. Halt Implementation.
2. Create Degradation Proposal in `logs/bug_log.md` titled "Degradation Proposal: [Feature Name]".
3. Detail the blocker, proposed fallback, and expected impact.
4. Explicitly state "USER APPROVAL REQUIRED."
5. Proceed ONLY after explicit written approval.

---

## §7. Pre-Action Reasoning Protocol

CRITICAL: Before taking any significant action, apply this reasoning framework:

### 7.1 Logical Dependencies & Constraints
- Analyze the intended action against policy rules, prerequisites, and constraints.
- Ensure the action does not block a subsequent necessary action (Order of Operations).
- Resolve conflicts by prioritizing policy/mandatory rules first.

### 7.2 Risk Assessment
- Ask: "Will this action cause future issues?"
- For exploratory tasks, prefer calling tools with available info rather than asking the user, unless logical dependency analysis proves missing info is critical.

### 7.3 Abductive Reasoning
- Identify the most logical reason for problems, looking beyond obvious causes.
- Prioritize hypotheses based on likelihood but do not discard low-probability root causes prematurely.

### 7.4 Information Grounding
- Incorporate all sources: available tools, policies, conversation history, and user constraints.
- Verify claims by quoting exact applicable policies when referring to them.

---

## §8. Status Reporting Format

After completing significant tasks, emit a status block:

```
STATUS
task: <name>
result: success|failed
artifacts: [exact file paths...]
tests_passed: <int>/<int>
next_actions: [short list]
```

### 8.1 No status blocks mid-batch (DEPRECATED 2026-05-05 per polaris-restart §9.1)

**SUPERSEDED by §3.0 issue-driven workflow per plan §7.A LOCKED A2 + §7.B LOCKED B1.** Claude writes briefs + diffs; Codex reviews twice per Issue (brief + diff); GitHub auto-merge fires on Codex APPROVE via CI required check `polaris/codex-required`; user reads `git log` morning as after-the-fact human-at-merge surface. Claude does NOT click merge or run `gh pr merge --admin` (that authority is structurally revoked). The mid-batch closure-prose anti-pattern is structurally prevented: Claude no longer participates in the merge step.

The original 2026-05-04 §8.1 text is preserved below for historical context.

---

~~Original 2026-05-04 §8.1:~~

During an authorized **batched run** (e.g. "ship slice 002 to completion" =
14 PRs; or any explicit multi-PR plan), STATUS blocks are FORBIDDEN at
PR-merge boundaries. After `gh pr merge <N> --squash --delete-branch
--admin` succeeds, the IMMEDIATE next action MUST be `git checkout -b
bot/<next-pr-name>`. Not a wrap-up. Not a "next actions" list. Not a
"continuing" sentence followed by silence.

**Why:** STATUS blocks function as turn-closure signals. Even when followed
by "Continuing to PR X", the closure has already happened in output, and
the next iteration does not fire reliably. User has flagged this failure
3+ times across 2026-05-04 sessions ("you always said you continue, but you
always stop"). Promising harder doesn't fix it; structural avoidance does.

**Allowed mid-batch transitions:**
- One brief sentence: "PR 25 merged; opening PR 7 branch."
- A `git checkout -b ...` command in the same response.
- Tests + commits + push + merge for the next PR.

**FORBIDDEN mid-batch:**
- Any STATUS block.
- Bullet lists titled "next actions:", "remaining:", "shipped this stretch".
- "Slice progression: N of M PRs shipped" tallies.
- Per-PR wrap-up summaries.

**STATUS blocks are reserved for:**
1. The MISSION is fully complete — for POLARIS, that means slice 005
   (BEAT-BOTH benchmark + demo polish) merged AND the demo run end-to-end
   produces correct output. Until then, every slice boundary (002→003,
   003→004, etc.) is an internal transition, NOT an end-of-batch.
2. A genuine halt condition has fired: asymptoting / scope decision /
   primary-source conflict / cost concern / fetch-backend keys missing /
   user-input genuinely required (not invented blocker per
   `feedback_dont_pause_autoloop` and `feedback_substrate_is_not_product`).

**Slice boundaries are NOT batch boundaries.** When slice N's last PR
merges, the IMMEDIATE next action is `git checkout -b
bot/slice-N+1-architecture-proposal` and start drafting. User flagged
2026-05-04: "Then why you stop here now?" after I declared slice 002
done. The slice closing is the same kind of internal milestone as a PR
merge — keep going to slice 003 without asking.

**Self-check:** If you find yourself drafting a STATUS block during a batch
and the slice isn't done, that's the bug. Delete it; run the next PR's
branch-creation command instead.

### 8.2 Zero prose between merge and next branch + active_issue.json transition gate (DEPRECATED 2026-05-05 + UPDATED per polaris-restart §9.1)

**Updated 2026-05-05:** ALSO ban any `state/active_issue.json` transition (writing a new active_issue_id, advancing current_step) before user assignment. Per CLAUDE.md §3.0 + §10 boot ritual: Claude does NOT pick the next issue autonomously. User assigns via TaskCreate. `state/active_issue.json` is updated by user-assignment, not by Claude advancing through the queue.

**§8.2 SUPERSEDED for the merge-prose rule** by §3.0 issue-driven workflow (Claude no longer merges). Preserved below for historical context.

---

~~Original 2026-05-04 §8.2:~~

Sec 8.1 was insufficient because it banned STATUS blocks (a surface form)
without banning the underlying behavior (any backward-looking text
between `gh pr merge` and `git checkout -b`). The agent kept finding new
surface forms — paragraphs with PR counts, "still on momentum", "X of N
PRs done" tallies — that are the same closure behavior dressed differently.

**Strict rule:** Between the tool call that completes `gh pr merge` and
the tool call that creates the next branch (`git checkout -b
bot/...next-pr-name`), NO assistant prose is allowed. Not a sentence.
Not a count. Not a "next up" line. Nothing.

**Why:** Any text in that gap functions as a closure signal regardless
of whether it has a STATUS header. The empirical pattern across this
session is: agent emits recap → agent stops. Removing the recap
removes the stop trigger.

**Allowed:** Empty assistant text followed immediately by the next
branch's first tool call (Edit/Write/Bash for the next PR's content).

**Forbidden:** Any of these between merge and next branch:
- "PR N merged" sentences
- "Slice X: N/M PRs done" tallies
- "Total tests: N passing" recaps
- "Continuing with..." / "Moving to..." / "Next is..." framings
- "Still on momentum" / "Pattern locked in" cheerleading
- ANY backward-looking summary, however brief

**Test:** If a reader of the conversation transcript can tell that one
PR just finished and another is starting, the prose was too much.
PR boundaries should be visible only in tool calls + commit messages,
never in assistant prose.

User flagged 2026-05-04 v2: "why all of the previous protocol fail
successfully" — the answer is that sec 8.1 banned the symptom, not the
behavior. Sec 8.2 bans the behavior.

---

## §8.3 Codex review iteration discipline (added 2026-05-05 per user directive)

When Codex reviews a plan, brief, audit, or diff, the iteration cycle is BINDING:

### 8.3.1 Hard cap of 5 iterations (UPDATED 2026-05-06 per user directive)

**Cap: 5 iterations per Codex review (brief or diff).** If Codex has not returned `verdict: APPROVE` after iter 5, the document is force-APPROVE'd and Claude proceeds to the next step. Rationale (user directive 2026-05-06): unbounded Codex iteration was making delivery commercially unviable; the 5-cap forces convergence and matches the cycle-time budget needed to ship Carney by Sep 6.

This SUPERSEDES the prior "no hard cap" rule. The principle "trust Codex's findings" remains — but trust is bounded at 5 iterations.

**Communication to Codex — THE canonical cap directive (one source of truth, used verbatim in every brief; §8.3.3 + `.codex/REVIEW_BRIEF_FORMAT.md` §0 reference THIS block, not duplicate it):**

```
HARD ITERATION CAP: 5 per document. This is iter N of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

**Force-APPROVE artifact procedure** (when iter 5 returns REQUEST_CHANGES):
1. Author `.codex/<issue_id>/<gate>_iter5_force_approve.txt` (where `<gate>` = `codex_brief_verdict` for brief reviews or `codex_diff_audit` for diff reviews — these are the CI-checked filenames per `.github/workflows/codex-required.yml:155-158,192-193`) recording: cap-hit timestamp, residual P0/P1 from iter-5 verdict, follow-up Issue IDs created in `state/polaris_restart/issue_breakdown.md`, link to user directive 2026-05-06.
2. Append a force-approval entry to `state/polaris_restart/iteration_trajectory.md` (per §8.3.5).
3. The CI gate parses `codex_brief_verdict.txt` (brief gate) or `codex_diff_audit.txt` (diff gate) for the LAST `verdict:` line. Claude appends `verdict: APPROVE` as the final line of the iter-5 file along with a `# force-approved at iter 5 cap per CLAUDE.md §8.3.1` marker. The corresponding `_iter5_force_approve.txt` annotation file lives alongside as documentation but is not parsed by CI.
4. Proceed to next step (commit, push, PR, merge).

History (2026-05-05): POLARIS plan APPROVE'd at iter 4; issue breakdown at iter 4; cleanup audit at iter 21 (the latter was the trigger for this cap). 21-iter cleanup_audit produced ~30 real bugs, but the cycle time was prohibitive. New rule: cap convergence at iter 5; if real bugs persist at iter 5, ship anyway and capture residual concerns as follow-up Issues.

### 8.3.2 Trust Codex's verdicts

Codex iter 1 of cleanup_audit caught `git clean -fdX` would nuke `.env` + 2.2GB `pg_checkpoints.sqlite`. Iter 2 caught `.gitignore:9` inline-comment-as-pattern bug. Iter 3 caught Bash-only script breaks on Windows. Iter 4 caught `state/polaris_restart/` doesn't exist at reset target. ~30 findings across 6 iters, ~25 would have caused real execution failures, 3 catastrophic. Empirical: Codex findings are real. Do not dismiss as noise.

### 8.3.3 Anti-toothpaste-squeeze: brief MUST include the §8.3.1 canonical cap directive

Every Codex review brief MUST start with the **verbatim §8.3.1 canonical cap directive** as its first content section (before any other prose). Single source of truth — DO NOT paraphrase or restate; copy §8.3.1's fenced block byte-for-byte.

`.codex/REVIEW_BRIEF_FORMAT.md` §0 also references this same block. If §8.3.1 is updated, §0 and every subsequent brief automatically inherit the new wording at next authoring.

Without this directive Codex may drip-feed findings, inflating iter count and obscuring convergence math. The 5-cap is the binding stop; the front-load demand is how we make 5 sufficient.

### 8.3.4 No scope-narrowing for false convergence

When iter N+1 produces MORE findings than iter N, do NOT restrict scope to make iter N+1 look smaller. That is dishonest. The correct path is addressing all findings or escalating "stop paper, build harness" per §8.3.6. Iter 6 of cleanup_audit had more P1 than iter 5 — that was real specificity emerging, not scope creep.

### 8.3.5 Iteration trajectory MUST be logged

Every Codex submission writes/appends to `state/polaris_restart/iteration_trajectory.md` recording iter N, doc, finding counts, tokens, key findings. User reads this between iterations to surface convergence math.

### 8.3.6 When Codex says "stop paper, build harness" OR cap is hit — accept and ship

Sister iter 6: "stop paper-iterating and build a tiny harness." POLARIS cleanup iter 6: reset-target inventory needs ground-truth via `git ls-tree -r 365f334`, not paper enumeration. When Codex's `convergence_call` shifts from `continue` to `accept_remaining` OR Codex says "build harness," respect it. Do not override with "let me iterate one more round."

**ALSO** (added 2026-05-06): if iter 5 returns `verdict: REQUEST_CHANGES` per §8.3.1 cap, Claude force-APPROVE's the document, captures residual concerns from the iter-5 verdict as follow-up Issues in `state/polaris_restart/issue_breakdown.md`, logs the force-approval in `state/polaris_restart/iteration_trajectory.md`, and proceeds to the next step. The 5-cap IS a directive. Do not iterate to 6.

### 8.3.7 Codex auth uses ChatGPT subscription, not API

Always invoke as `env -u OPENAI_API_KEY codex exec --skip-git-repo-check - < brief.md > verdict.txt`. The `-u` flag UNSETS the variable, forcing OAuth fallback to `~/.codex/auth.json`. Confirm via `codex login status` returning "Logged in using ChatGPT." Never run `codex exec` without `env -u OPENAI_API_KEY`.

### 8.3.8 When uncertain about brief structure or Codex-as-reviewer best practice

Before iter N+1, search OpenAI engineering blog + GitHub PR-review automation literature for current best practice. Topics: constraining Codex to verdict-only output (saves tokens vs exec exploration), providing reset-target inventory deterministically, structuring rename-completeness gates, binding Codex output to JSON schema for machine-parseable verdicts.

### 8.3.9 Output schema bound (every brief specifies)

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

Loose verdict prose is rejected — resubmit asking for the schema.

---

## §8.3.10 Stop is Codex's call, not Claude's — added 2026-05-07 (binding)

User directive 2026-05-07 (reflagged after I-f5-007 merged with closure prose "stopping here for natural cadence"): **"the checkpoint is by codex, not by me, why you still fuck it up."**

**Rule:** Claude does NOT decide when to pause the autonomous Issue queue. Stops are decided by:
- Codex returning `verdict: REQUEST_CHANGES` at iter-5 cap (force-APPROVE per §8.3.1, then proceed — not a stop).
- Codex saying "stop paper, build harness" (§8.3.6).
- A documented halt condition firing (§3.0: canonical-pin / CHARTER-pin mismatch, issue jump, missing artifact triple, Codex unavailable >1h, 2-cycle repeated root cause, 200-LOC cap exceeded with no exemption, 3+ PRs queued for user in 24h).
- The user explicitly typing a stop instruction in this conversation turn.

**Forbidden self-initiated stops:**
- "Natural cadence checkpoint" / "good place to pause for the user to check in" — NOT a halt condition.
- "X PRs landed this session" recap framed as the stopping point — NOT a halt condition.
- "User has not been notified during this autonomous run" — NOT a halt condition. The user reads `git log` in the morning per Plan §7.B LOCKED B1; "notification" is the merged-PR commit, not a Claude prose recap.
- "Halfway through the slice; quality-gate stretch warrants a check-in" — NOT a halt condition. Slice/feature boundaries are internal milestones.
- "Resource state is clean; appropriate stopping point" — NOT a halt condition. Clean resource state is the precondition for continuing, not the trigger for stopping.

**Self-check before yielding the turn:** am I stopping because Codex/halt-condition/user told me to, OR because I'm projecting that the user "would want a checkpoint"? If the latter, that's the bug. The user's `feedback_dont_pause_keep_executing_2026_05_07.md` and CHARTER §1 both make Claude the executor and Codex the decision-maker; self-initiated cadence judgments belong to the latter, not the former.

**Application:** when an Issue merges, the IMMEDIATE next action is `git checkout polaris && git pull && git checkout -b bot/<next-issue>` — no prose between the merge response and the branch creation.

---

## §8.4 Computer-resource discipline (CPU / GPU / RAM management) — added 2026-05-06

User directive 2026-05-06 (after Codex iter-cycle drove computer to needing reboot from RAM/CPU exhaustion): **be a careful steward of the user's local CPU / GPU / RAM. Run heavy processes only when necessary. Kill them when the task completes.**

**Background-process discipline:**

1. **One Codex `exec` at a time.** NEVER run two `codex exec` invocations in parallel. Each Codex call spawns sub-processes (~3 alive concurrently) that linger after exit; multiple in flight = OS-level resource exhaustion. Run codex in foreground with a 9-min timeout, OR if backgrounded, await completion before queuing the next.

2. **Background tool-call audit before exit.** Before yielding back to the user OR scheduling a wakeup, check `Get-Process -Name codex,python,node` and kill orphaned processes from the just-completed task. Use `Stop-Process -Id <pid>` (or `taskkill /PID <pid> /F` if Stop-Process fails). NEVER leave a hung codex process across a turn boundary unless it is genuinely still doing work.

3. **No parallel pytest / npm / playwright runs.** Single test run at a time per workspace. If a previous run is still active (`Get-Process -Name python,node`), wait for it OR kill it before starting a new one.

4. **Heavy ML / vector / CUDA processes are forbidden in autonomous loops.** sentence-transformers, torch, chromadb, sgLang, vllm — these load models that pin GB-scale RAM. Run only on direct user instruction; release immediately after the task. Use `import gc; gc.collect()` + explicit model handle deletion in Python scripts; kill the Python process if the task is complete.

5. **Long-running watch / dev servers must be tracked.** If you start `npm run dev`, `uvicorn`, `playwright test --watch`, or any persistent server, write the PID to `state/active_processes.json` (one-line append) and kill it before the next Issue starts unless it is genuinely still needed.

6. **Pre-task inventory.** At the start of each new Codex iteration or autonomous loop step, run `Get-Process -Name codex,python,node | Format-Table Id, ProcessName, StartTime, CPU` and confirm no leftover processes from prior steps. If found, kill them.

7. **Notify user on resource concern.** If OS-level resource pressure is detected (Task Manager shows >80% RAM or >90% CPU sustained for >2 minutes during an autonomous loop), pause the loop and report to the user before continuing. Do NOT silently continue while the computer is overloaded.

8. **Codex sub-process lingering is real.** Empirically (2026-05-06 incident): `codex exec` spawns 2-3 child processes that may persist with low-CPU but accumulated RAM after the main process exits. Always check + kill child processes between iters.

**Apply this in every command:**
- Before running a heavy Bash command: list processes; kill stragglers.
- After a heavy Bash command: list processes again; kill what shouldn't be alive.
- When yielding to the user: orphans cleaned.
- When the user reports a slow computer: stop autonomous work; do a process inventory; clean up; report.

This discipline applies to ALL future autonomous Issue work. The 5-iter Codex cap (§8.3.1) caps iteration count; this §8.4 caps OS-level resource footprint per iter.

---

## §9. POLARIS-Specific Invariants

**Applies to pipeline A (honest-rebuild). Pipeline B (UI) and pipeline
C (frozen legacy) are governed separately — see `architecture.md`.**

### 9.1 Core Invariants (Non-Negotiable)

1. **Two-family evaluator**: generator and evaluator MUST be from
   different training lineages. `openrouter_client.check_family_segregation`
   raises `RuntimeError` at construction if violated.
2. **Provenance tokens**: every generated sentence carries
   `[#ev:<evidence_id>:<start>-<end>]` tokens. Sentences without valid
   tokens are dropped by `strict_verify`.
3. **Strict verify**: per-sentence check enforces (a) evidence-id in pool,
   (b) span bounds valid, (c) every decimal in sentence appears in span,
   (d) sentence and span share ≥2 content words
   (`PG_PROVENANCE_MIN_CONTENT_OVERLAP`). Fabricated claims fail at least
   one of these.
4. **Zero-verified abort**: if every section fails strict_verify,
   `report.md` is a pipeline-verdict artifact (not an empty-findings
   pseudo-report). Status: `abort_no_verified_sections`.
5. **Corpus approval enforcement**: a corpus with material tier deviation
   plus a rubber-stamp note aborts before any generator token is billed.
   Status: `abort_corpus_approval_denied`.
6. **Budget cap holds even without `usage.cost`**: `_impute_cost_from_tokens`
   backstops token-only responses. Negative tokens clamp to zero.
7. **Delimiter sanitization** (prompt-injection defense): evidence text
   containing `<<<evidence:...>>>` or other delimiter literals —
   including via NFKD/invisible-char/homoglyph evasions — is neutralized
   before prompt wrapping. Byte-preserves legitimate multilingual content.

### 9.2 Quality Gates (pipeline A)

| Gate | Threshold | Fail Action |
|---|---|---|
| Corpus adequacy | Min sources per tier (template-driven) | `abort_corpus_inadequate` |
| Corpus approval | Auto-approved OR substantive operator note | `abort_corpus_approval_denied` |
| Strict verify (per sentence) | Numeric match + ≥2 content-word overlap | Drop sentence |
| Strict verify (per section) | ≥40% sentences verified | Attempt one regeneration |
| Strict verify (pipeline) | At least one section with verified prose | `abort_no_verified_sections` |
| Budget | Accumulated cost ≤ `PG_MAX_COST_PER_RUN` | `BudgetExceededError` |

### 9.3 Pipeline verdict statuses (manifest.json)

| Status | Condition |
|---|---|
| `success` | All gates passed, generator produced verified prose |
| `abort_scope_rejected` | Scope gate rejected the research question |
| `abort_corpus_inadequate` | Corpus adequacy gate failed (not enough sources) |
| `abort_corpus_approval_denied` | Corpus approval gate rejected (rubber-stamp note on material deviation) |
| `abort_no_verified_sections` | Every generated section failed strict_verify |
| `error_*` | Unexpected failure (API outage, malformed response, etc.) |

### 9.4 Code hygiene (enforced by test suite, not a separate Sheriff)

**Forbidden patterns** (tests in `tests/polaris_graph/` detect these):

- `try: ... except: pass` without logging or re-raise (silent failure)
- `import unittest.mock` or `from unittest.mock import ...` in `src/`
  production code
- Magic numbers (`if score > 0.7` instead of a named constant or env var)
- `time.sleep()` to simulate work
- `# TODO`, `# FIXME`, `# XXX`, `pass` as function body
- Mocking the live-evidence database in integration tests (per user
  feedback memory: integration tests must hit real data sources)

Pipeline C (`src/orchestration/`, `scripts/full_cycle.py`) does not
currently meet these invariants. It is frozen; see
`src/orchestration/FROZEN_SINCE_2026-03-16.md`.

---

## §10 Session boot ritual (per polaris-restart Plan §9.1)

Mandatory ritual at session start. Mirrors sister project's CHARTER session-start ritual:

1. **Read polaris-controls CHARTER.md and PLAN.md** (admin-only sister repo nested under POLARIS at `C:\POLARIS\polaris-controls\` per PR-B2 relocation 2026-05-05; gitignored from POLARIS so it remains its own git repo with its own signed-commits-required protection — Claude has no signing key for it).
2. **Verify SHAs** against `state/polaris_restart/charter_sha_pin.txt`. Mismatch = HARD STOP per §3.1 step 0.
3. **Read `state/active_issue.json`** — if shows in_progress issue, resume that issue ONLY (no scope expansion).
4. **If no active issue**, list TaskCreate tasks unblocked, present to user, wait for user assignment. Do NOT pick a task autonomously.
5. **State to user explicitly:**
   - active issue ID
   - current step within issue (brief / diff / audit / merge / complete)
   - next action

Per `feedback_codex_iteration_5cap_2026_05_06.md` (SUPERSEDES `feedback_codex_iteration_no_cap_no_toothpaste.md` 2026-05-05): the iteration cap is 5 per document; trust Codex's findings within the cap, force-APPROVE at iter 5 if still REQUEST_CHANGES per §8.3.1. The "trust Codex over advisor on iterate-vs-restructure" principle remains, bounded at 5 iterations.

Per CHARTER §1: Claude does NOT have admin-merge authority. The structural-removal pattern (CI gate enforces, not soft discipline) prevents the failure mode of Claude promising "I won't merge" then merging anyway.

Per `failure_28_commits_2026_05_03.md`: I have no admin merge authority. CI gate enforces. Promises do not work; structural removal does.

---

THIS IS THE LAW. FOLLOW IT.
