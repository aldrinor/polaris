HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

# I-naming-001 — Rename BPEI → ambiguity_detector + broader naming-audit plan

GH#434. Branch `bot/I-naming-001-bpei-rename-plus-audit` (off polaris). Plan-review iter 1.

## Why this matters (verbatim user)

> "BPEI ambiguity detector >>> Why you give a stupid name like it?"
> "ambiguity detector, why don't just name it in this way?"
> "Yes, and pls also work with codex, to make sure you don't miss anyone behind without naming"

The name `BPEI` is a commemorative tag from the 2026-04-30 'phantom completion' incident — user typed the literal string 'BPEI' as a probe and the system fabricated an answer. The directory got named after the incident. **Bad name for outside-perspective / Carney handover.**

## Part A — BPEI rename scope

### Production tree references (case-insensitive grep)

**Directories to rename:**
- `src/polaris_v6/bpei/` → `src/polaris_v6/ambiguity_detector/`

**Files inside renamed dir:**
- `src/polaris_v6/bpei/ambiguity_detector.py` — keep filename (already descriptive); only the parent dir changes
- `src/polaris_v6/bpei/__init__.py` — keep filename; only parent dir changes

**Files that import from the renamed module (`from polaris_v6.bpei...`):**
- `src/polaris_v6/api/ambiguity.py` line 16: `from polaris_v6.bpei.ambiguity_detector import (...)` → `from polaris_v6.ambiguity_detector.ambiguity_detector import (...)`
  - **Subtle issue**: this creates `ambiguity_detector.ambiguity_detector` which is awkward. Consider also flattening `ambiguity_detector.py` → exported directly from `__init__.py`. Or rename the dir to `ambiguity/` and keep filename — cleaner.
- All `__pycache__/` files will rebuild on first import; no manual cleanup needed.

**FastAPI route status:**
- `src/polaris_v6/api/ambiguity.py:21` already mounts at `/ambiguity`. NO route rename needed — only the internal import path.
- Frontend `web/lib/api.ts:161` already hits `${BACKEND_URL}/ambiguity` — NO change.
- Frontend `web/app/intake/components/intake_form.tsx:16` imports `AmbiguityModal` (component, not BPEI-named) — NO change.

**Other code/doc/test files mentioning the string "bpei" (8 files, mostly comments/docstrings):**
- `src/polaris_graph/api/audit_bundle_route.py` (1 occurrence — comment/docstring)
- `src/polaris_graph/api/intake.py` (1)
- `src/polaris_graph/api/intake_route.py` (1)
- `src/polaris_graph/api/__init__.py` (1)
- `src/polaris_graph/audit_bundle/bundle_schema.py` (1)
- `src/polaris_graph/audit_bundle/manifest_builder.py` (1)
- `src/polaris_graph/intake/cluster_labeler.py` (1)
- `src/polaris_graph/intake/disambiguation_clusterer.py` (1)
- `src/polaris_graph/scope/scope_decision.py` (1)
- `src/polaris_v6/api/ambiguity.py` (1 — docstring or status text)
- `src/polaris_v6/bpei/ambiguity_detector.py` (1 — docstring header)
- `src/polaris_v6/bpei/__init__.py` (3 — module docstring)
- `src/polaris_v6/memory/__init__.py` (1)
- `src/polaris_v6/pipeline.py` (cached) (1)
- `tests/e2e/frontend_replay_smoke.py` (1)
- `tests/polaris_graph/audit_bundle/test_bundle_builder.py` (1)
- `tests/polaris_graph/followup/test_agent.py` (1)
- `tests/polaris_graph/golden/test_slice_004_goldens.py` (1)
- `tests/v6/test_ambiguity_detector.py` (1)
- `tests/v6/test_api_ambiguity.py` (1)
- `tests/v6/test_run_benchmark_script.py` (1)
- + adapter pycache hits (auto-rebuilt)

Plan for these comment/docstring occurrences: replace `BPEI ambiguity detector` → `ambiguity detector` and `BPEI` standalone → `ambiguity detector (formerly BPEI)`. Preserve the commemorative tag in **one** place — `src/polaris_v6/ambiguity_detector/__init__.py` module docstring — with a "Historical: named after the BPEI phantom-completion incident, 2026-04-30" footnote. This keeps the audit trail to memory file `bpei_phantom_completion_lessons.md` without polluting every grep.

## Part B — Broader naming audit (per user directive)

### Other cryptic insider-named items in production tree

I scanned `src/polaris_graph/` and `src/polaris_v6/` for filename/dirname patterns matching version tags (`v30`, `v32`, etc.), milestone tags (`M-INT`, `M-D`, etc.), feature tags (`F1`..`F15`), and short uppercase acronyms.

**Production code with cryptic version-numbered names (no descriptive part):**

1. **`src/polaris_graph/audit_ir/v30_runner.py`** — file. "v30" = pipeline version 30. Better name: `honest_rebuild_runner.py` or `pipeline_v30_runner.py` (version-bearing but at least explicit about what it's a runner for). Cross-ref: per architecture.md, "V30" was the honest-rebuild sweep variant.

2. **`src/polaris_graph/v30_sweep_integration.py`** — file. Same issue. Better: `honest_sweep_integration.py`.

3. **`src/polaris_graph/generator2/`** and **`src/polaris_graph/retrieval2/`** — sibling-numbered dirs. The "2" suggests there's a v1 elsewhere; in fact `src/polaris_graph/generator/` IS the v1. Better convention: name by *what is different*, e.g. `generator_with_provenance_tokens/` or just keep `generator/` and retire the v1 instead of versioning.

**Other patterns surfaced (lower priority):**

- `src/polaris_graph/graph.py`, `graph_v2.py`, `graph_v3.py` — LangGraph variants. Documented in architecture.md. The version suffix here is intentional (UI pipeline B variants) and not cryptic — `graph_v2.py = CRAG`, `graph_v3.py = ReAct`. The names appear in docstrings. **Not a rename target.**

- `src/polaris_v6/memory/__init__.py` mentions BPEI (1 ref).

### What's NOT cryptic (intentionally surfaced so you can confirm)

- All `src/polaris_graph/{intake,scope,audit_bundle,evidence_contract,evaluator,generator,llm,memory,nodes,retrieval,wiki,benchmark,export,followup,anti_sycophancy,audit_ir,auto_induction,document_ingester}` — descriptive.
- All `src/polaris_v6/{api,bpei↑,charts,memory,observability,queue,scope,sycophancy,...}` — all descriptive except `bpei`.

## Rename execution plan

### Stage 1 — Stage rename (no code change)

```bash
git mv src/polaris_v6/bpei src/polaris_v6/ambiguity_detector
```

### Stage 2 — Update internal imports + comments

Python files touched (estimated 10-15):
- `src/polaris_v6/api/ambiguity.py` — update import path
- `src/polaris_v6/ambiguity_detector/__init__.py` — update module docstring (keep one commemorative footnote)
- `src/polaris_v6/ambiguity_detector/ambiguity_detector.py` — strip BPEI from docstring header
- `src/polaris_v6/memory/__init__.py` — comment update
- `src/polaris_v6/pipeline.py` — if reachable (cached only)
- `tests/v6/test_ambiguity_detector.py` — comment update
- `tests/v6/test_api_ambiguity.py` — comment update
- `tests/v6/test_run_benchmark_script.py` — comment update
- `src/polaris_graph/api/{audit_bundle_route,intake,intake_route,__init__}.py` — comment updates
- `src/polaris_graph/audit_bundle/{bundle_schema,manifest_builder}.py` — comment updates
- `src/polaris_graph/intake/{cluster_labeler,disambiguation_clusterer}.py` — comment updates
- `src/polaris_graph/scope/scope_decision.py` — comment update
- `tests/e2e/frontend_replay_smoke.py` — comment update
- `tests/polaris_graph/audit_bundle/test_bundle_builder.py` — comment update
- `tests/polaris_graph/followup/test_agent.py` — comment update
- `tests/polaris_graph/golden/test_slice_004_goldens.py` — comment update

### Stage 3 — Update docs

- `architecture.md` — search/replace BPEI references
- `docs/file_directory.md` — `src/polaris_v6/bpei/` → `src/polaris_v6/ambiguity_detector/`
- `README.md` — search/replace BPEI references (if any)
- `docs/handover.md` — append note: 2026-05-12 I-naming-001 rename

### Stage 4 — Memory references (preserve)

- `memory/bpei_phantom_completion_lessons.md` — file name PRESERVED (commemorative).
- Inside the file, append a "Resolution 2026-05-12 (GH#434)" note documenting the rename.

### Stage 5 — Sanity test

- `pytest --collect-only tests/v6/test_ambiguity_detector.py tests/v6/test_api_ambiguity.py` — must collect cleanly (no import errors).
- `python -c "from polaris_v6.ambiguity_detector.ambiguity_detector import AmbiguityDetector; print('ok')"` — must work.
- Optional: hit `/ambiguity` endpoint live to confirm routing unbroken.

## Choice point: directory layout

Two options for the new dir/file structure. Asking Codex to pick:

**Option A** — keep file structure flat:
```
src/polaris_v6/ambiguity_detector/
├── __init__.py
└── ambiguity_detector.py        # ← awkward: dir.file_dot_module is same name
```

Import: `from polaris_v6.ambiguity_detector.ambiguity_detector import AmbiguityDetector`

**Option B (recommended)** — re-export from `__init__.py`:
```
src/polaris_v6/ambiguity_detector/
├── __init__.py                  # ← `from .ambiguity_detector import AmbiguityDetector`
└── ambiguity_detector.py
```

Import: `from polaris_v6.ambiguity_detector import AmbiguityDetector`

**Option C** — rename inner file too:
```
src/polaris_v6/ambiguity_detector/
├── __init__.py                  # ← `from .core import AmbiguityDetector`
└── core.py
```

Import: `from polaris_v6.ambiguity_detector import AmbiguityDetector`

Claude recommends **Option B** (zero file-content moves needed beyond imports; re-export gives clean public API).

## Questions for Codex

1. Approve directory naming (Option A/B/C)?
2. Approve commemorative-footnote-in-one-place strategy (vs scrub all BPEI mentions vs keep all)?
3. Approve broader naming-audit findings — are `v30_runner.py`, `v30_sweep_integration.py`, `generator2/`, `retrieval2/` worth follow-up issues, or accept-as-is?
4. Anything I missed in the BPEI grep?
5. Any other production-tree filename/dirname I should add to the naming-audit list?

## Output schema

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
p3_cosmetic: [...]
directory_layout_choice: A | B | C
commemorative_footnote_strategy: one_place | scrub_all | keep_all
broader_naming_audit_findings:
  - file_or_dir: "<path>"
    issue: "<why cryptic>"
    severity: P1 | P2 | P3
    suggested_rename: "<new name>"
    recommended_action: do_in_this_pr | followup_pr | accept_as_is
bpei_grep_missed_items: [...]  # paths Codex thinks Claude missed
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```
