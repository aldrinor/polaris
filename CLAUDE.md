# POLARIS PROJECT - Operational Directives

CRITICAL: This file (CLAUDE.md) MUST be read in its entirety at the start of EVERY session and immediately following ANY restart. Failure to adhere to these directives constitutes a critical operational failure. See §3 for the mandatory startup protocol.

Document Class: Operational, Binding, Project-Specific
Scope: All POLARIS development, research pipeline implementation, and maintenance tasks.

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

**1.1 Active Project Definition (APD) Hierarchy:** The APD is the dynamic source of truth for the project's current goals. It is derived, in order of precedence, from:
1. Current Session Instructions: Explicit requests and clarifications made during the active session.
2. `docs/todo_list.md` (The Scope): The prioritized list of current tasks.
3. Recent `logs/session_log.md` (The History): History of decisions, rationale, and implementations.
4. `architecture.md` (The Baseline): Formal specification for POLARIS system architecture.

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

### 2.1 Authoritative Files
- `logs/session_log.md`: A chronological, append-only audit trail. Critical component of the APD.
- `docs/todo_list.md`: The prioritized backlog of remaining tasks. Updated in place; highest priority items must be at the front/top.
- `logs/bug_log.md`: Registry of defects, blockers, clarification requests, and degradation proposals.
- `docs/file_directory.md`: A hierarchical inventory of all active files, describing the purpose of each.
- `state/restart_instructions.md`: Precise instructions on how to resume the session from the last executed task.
- `state/progress_ledger.jsonl`: Machine-readable append-only execution log for pipeline state.
- `state/last_pointer.json`: Resume point after crash/restart.

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

## §3. Mandatory Session Protocol (Startup/Restart)

This protocol MUST be executed automatically at the start of every session and after any restart or crash.

### 3.1 Startup Protocol (The 10 Steps)
1. **Read CLAUDE.md:** Read this file completely.
2. **Synthesize APD (CRITICAL):** Determine the Active Project Definition by reviewing the sources in order (§1.1).
3. **Verify Environment:** Check that necessary environment variables and configuration files exist. Run `python scripts/preflight.py`.
4. **Review Bug Log:** Read `logs/bug_log.md` to identify blockers or pending clarifications.
5. **Review File Directory:** Read `docs/file_directory.md` to understand the current architecture.
6. **Read Restart Instructions:** Read `state/restart_instructions.md`.
7. **Check Progress Ledger:** Read `state/progress_ledger.jsonl` and `state/last_pointer.json` for pipeline resume point.
8. **Execute Recovery:** If restart_instructions.md contains instructions, execute them to restore the exact previous state.
9. **Determine Next Action:** Identify the next action based on the synthesized APD.
10. **Log Session Initialization:** Append a SESSION_INIT entry to `logs/session_log.md`.

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
│   ├── pg_preflight_v2.py        # Environment check (Docker `preflight` subcommand)
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
  `scripts/postflight_audit.py` — replaced by `pg_preflight_v2.py`;
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

THIS IS THE LAW. FOLLOW IT.
