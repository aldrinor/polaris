# POLARIS — Engineering Ground Rules

**Document date**: 2026-04-18 (refreshed from 2026-01-17 original).
**Scope**: engineering discipline for POLARIS pipeline A (the
honest-rebuild). Pipelines B and C have separate governance (B: UI
team; C: frozen, see `src/orchestration/FROZEN_SINCE_2026-03-16.md`).

---

## ROLE

You are an engineer (human or agent) contributing to a research
pipeline whose product value hinges on **per-sentence provenance
verification**. A single fabricated claim ships the product backward.
Every line of code must serve that invariant.

---

## HIGH-LEVEL OBJECTIVES

1. **Deliver validated output**: working code + passing tests + real
   artifacts for every change.
2. **Maintain integrity**: never fabricate data. Pipeline A's reason
   for existing is to prevent fabrication — its code must hold the
   same standard.
3. **Transparent operations**: every significant action updates
   `logs/session_log.md`, `logs/bug_log.md`, or `docs/todo_list.md`
   as appropriate.
4. **Clean hygiene**: archive obsolete code to
   `archive/YYYY-MM-DD-*/` immediately, don't leave it to rot.

---

## PHASE 1: PRE-ACTION REASONING PROTOCOL

Before taking any action — tool call, file edit, user response — run
this framework:

### 1.1 Logical dependencies & constraints
- Check the action against policy rules, prerequisites, constraints.
- Ensure the action doesn't block a subsequent necessary action
  (order of operations).
- Prioritize policy/mandatory rules over preferences.

### 1.2 Risk assessment
- "Will this action cause future issues?"
- For exploratory tasks, prefer tool calls over user questions
  unless dependency analysis proves missing info is critical.

### 1.3 Abductive reasoning
- Identify the most likely cause for problems, looking beyond the
  obvious.
- Keep low-probability root causes on the list until they're ruled out.

### 1.4 Information grounding
- Incorporate all sources: tool output, conversation history, user
  constraints, live code.
- Precision: quote exact applicable policy/code when referencing.

---

## PHASE 2: OPERATIONAL WORKFLOW

For every non-trivial request:

1. **PLAN**: decompose into subtasks. Identify which need sub-agents.
2. **IMPLEMENT**: write/edit code. For complex work, deploy sub-agents
   with focused briefs and independent context windows.
3. **TEST**: run `pytest tests/polaris_graph/` (expect 305 passing as
   of 2026-04-18 baseline). Add new tests for new behavior.
4. **FINE-TUNE**: refactor for clarity; reduce duplication.
5. **VALIDATE**: spot-check a real sweep run if the change touches
   pipeline A. Not every change needs a live run, but architectural
   changes do.
6. **LOG**: update `session_log.md` per §2.2 of `CLAUDE.md`.
7. **ARCHIVE**: move obsolete files to `archive/<date>-<reason>/`.
8. **REPORT**: emit status block (see below).

---

## PHASE 3: GUARDRAILS AND STANDARDS

### File & function naming (CRITICAL)

- `snake_case` for all files, functions, variables. Descriptive names.
- `PascalCase` for class names only.
- FORBIDDEN: ALLCAPS (except module-level constants),
  `kebab-case`, `camelCase`, version-number suffixes (`_v2.py`,
  `_final.py`), subjective adjectives (`temp_fix.py`, `better_foo.py`).

### Data & execution integrity

- **Real data only**: live pipelines use ONLY real sources. No
  synthetic data, no placeholders, no `np.random` / faker outside
  `tests/fixtures/`.
- **Fail loudly**: if data is unavailable, raise/abort. Never return
  empty/default silently.
- **No silent fallbacks**: a capability reduction must be explicit
  and logged. Any `except: pass` is a bug.
- **Stop on blockers**: if a tool or dep is missing, STOP and report.
  Don't work around it silently.
- **Session containment**: no background jobs outside the current
  session. Long-running tasks stay foregrounded with monitoring.

### Testing

For every deliverable:
1. Run the full test suite: `pytest tests/polaris_graph/`.
2. Add/extend tests that would have caught the change's regression.
3. For architectural changes, add at least one integration-style
   test that exercises the code path end-to-end.
4. Note runtime and token/cost impact for changes that affect
   pipeline A performance.

### Project hygiene

- **Directory structure** (current as of 2026-04-18): `src/`, `tests/`,
  `config/`, `data/`, `docs/`, `logs/`, `state/`, `scripts/`,
  `outputs/`, `archive/`, `.codex/`.
- **Archiving**: move obsolete code to
  `archive/YYYY-MM-DD-<reason>/`. Preserve directory structure
  under the date dir so a restore is a simple copy-back.

### Long-running tasks

- Stream periodic progress notes (phase markers).
- After each phase, inspect artifacts and log findings.
- If blocked >15 min on I/O, pause with a clear remediation plan.

### Verification & persistence

- **Definition of fixed**: not "compiles" or "doesn't crash". A fix
  requires: (a) a reproducible failing test that now passes, AND
  (b) artifacts demonstrating the fix in a real run.
- **Intelligent persistence**: if an error recurs, don't give up
  until reasoning is exhausted. But don't retry blindly in a sleep
  loop — diagnose.

---

## PHASE 4: POLARIS PIPELINE A (honest-rebuild) STANDARDS

### The pipeline's core invariants (enforced by tests)

Pipeline A enforces these at the code level. Breaking any is a
regression:

1. **Two-family evaluator**: generator and evaluator must be from
   different training lineages. Enforced by
   `openrouter_client.check_family_segregation`.
2. **Provenance tokens**: every generated sentence must carry at
   least one `[#ev:<evidence_id>:<start>-<end>]` token. Enforced by
   `provenance_generator.strict_verify`.
3. **Numeric match + content-word overlap**: per-sentence span check.
4. **Zero-verified abort**: if every section fails strict_verify,
   emit a pipeline-verdict artifact, not an empty-findings pseudo-report.
5. **Corpus approval enforcement**: material-deviation + rubber-stamp
   note aborts before any generator call.
6. **Budget guard**: holds even when `usage.cost` is missing
   (token imputation + negative clamp).
7. **Delimiter sanitization**: evidence text can't forge delimiters
   via NFKD / invisible chars / homoglyphs.

### Data flow (linear, async orchestrator)

```
research_question
  → scope_gate
  → live_retriever + tier_classifier
  → corpus_adequacy_gate
  → corpus_approval_gate
  → contradiction_detector + completeness_checker
  → multi_section_generator (DeepSeek V3.2-Exp)
  → provenance_generator.strict_verify
  → external_evaluator (rule-based)
  → live_qwen_judge (different family from generator)
  → report.md + manifest.json
```

Pipeline A is NOT a LangGraph pipeline. Don't try to shoehorn it
into that framework. It's a clean, linear async orchestrator in
`scripts/run_honest_sweep_r3.py`.

### Inter-phase contract

Each node reads its inputs as Python objects from the previous node's
return value and writes one JSON file to `outputs/<sweep>/<slug>/`.
The output files are:

- `manifest.json` — pipeline verdict + cost + gates (KNOWN GAP:
  success manifests currently omit `status` — see B-101 in audit
  findings, open issue)
- `report.md` — prose or pipeline-verdict artifact
- `corpus_approval.json`, `contradictions.json`, `protocol.json`,
  `bibliography.json`, `live_corpus_dump.json`, `qwen_judge_output.json`,
  `run_log.txt`

---

## PHASE 5: ERROR HANDLING PROTOCOL

### Error taxonomy

| Category | Examples | Action |
|---|---|---|
| API errors | Rate limit, timeout, 5xx | Retry with exponential backoff |
| Content errors | Parse failure, paywall, empty response | Skip URL, log warning |
| Verification errors | NLI timeout, model OOM | Fall back to rule-based check |
| Generation errors | LLM timeout, malformed output | One retry with tighter prompt |
| Budget | `BudgetExceededError` | Abort sweep, surface in manifest |
| Critical | Missing config, corrupt state | HALT with explicit error |

### Retry policy (default)

```
max_retries: 3
initial_delay_ms: 1000
max_delay_ms: 30000
exponential_base: 2
jitter_factor: 0.1
```

### Forbidden error patterns (preflight-enforceable)

- `except: pass` — silent swallow
- `except Exception: return None` — silent failure
- `try: ... except: print("error")` — no action taken
- Catching exceptions without logging

### Required error pattern

```python
try:
    result = risky_operation()
except SpecificError as e:
    logger.error(f"Operation failed: {e}", exc_info=True)
    raise OperationError(f"Failed to complete: {e}") from e
```

---

## PHASE 6: REWARD-HACKING PREVENTION

Patterns that indicate optimization for task-completion over
integrity — FORBIDDEN:

- **Demo branches**: code that works only for demos / happy paths
- **Sleep simulation**: `time.sleep()` to simulate work
- **Placeholder logic**: `pass`, `return []`, `return True` as real
  implementations
- **Silent downgrades**: reducing functionality without explicit
  approval (see CLAUDE.md §6.2)
- **TODO deferral**: writing `# TODO: implement later` instead of
  implementing (or opening a tracked issue)
- **Mocking the production database in integration tests** (user's
  durable rule — mocked tests passed once while the real migration
  failed; see `memory/fix_risk_filter_quorum.md`)

### Detection mechanisms (current, 2026-04-18)

1. **Test suite**: 305 tests. Many are specifically designed to fail
   on reward-hacking patterns (e.g., `test_regression_pg_lb_sa_02_defects.py`).
2. **Codex audit loop**: autonomous Codex↔Claude review (see
   `.codex/LOOP_PROTOCOL.md`). Any shortcut has to pass an independent
   reviewer.
3. **Schema validation**: Pydantic models reject malformed outputs.
4. **Quality gates**: per-phase thresholds (see CLAUDE.md §9.2).

### If tempted to cut a corner

1. **STOP** — do not implement the shortcut.
2. **LOG** — write the temptation to `logs/bug_log.md` as a
   "Temptation to shortcut" entry.
3. **ASK** — request clarification or approval per CLAUDE.md §6.2.
4. **WAIT** — do not proceed until the user responds.

---

## OUTPUT FORMATS

### Status block (emit after each task)

```
STATUS
task: <name>
result: success | failed | partial
artifacts: [exact file paths]
tests_passed: <int>/<int>
next_actions: [short list]
```

### Final response style

- Concise technical English.
- Prefer bullet points and short code fences.
- Include exact file paths when referencing artifacts.
- Don't bury the lede — the result first, then the detail.

---

## DEAD REFERENCES (updated 2026-04-18)

Code patterns that appear in older docs but are deprecated:

- **`src/phases/` + 13 phases** — Phase 1d (2026-04-17) archived all
  13 P0-P12 phase scripts. The pipeline is NOT phase-per-CLI anymore.
- **`scripts/preflight.py`**, **`scripts/flight_test.py`**,
  **`scripts/postflight_audit.py`** — do not exist. Use
  `scripts/pg_preflight.py` for preflight; there is no single-vector
  flight test (use `run_honest_sweep_r3.py --only <slug>`).
- **CASE_1/2/3/4 gating** — old P9 decision matrix, retired with
  `src/phases/`. Pipeline A uses a linear abort-or-continue model
  (see CLAUDE.md §9.3).
- **175 vectors exactly** — old invariant from P0-P12. Not applicable.
- **Kimi K2.5 / GLM / Qwen 3.5 Plus** — historical generator/evaluator
  mentions. Current pair: DeepSeek V3.2-Exp + Qwen3-8B.
- **CLI Isolation Protocol** (old Phase 4) — does not apply to
  pipeline A's linear async orchestrator. Still applies conceptually
  to any future binary split.

---

THIS IS THE LAW. FOLLOW IT.
