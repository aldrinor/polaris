# Codex DIFF review — I-naming-010 / GH #444: rename src/polaris_graph/graph_v4.py → pipeline_a_ui_adapter.py

HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

---

## 1. What you are reviewing

The commit-1 diff for #444 — `git diff origin/polaris...HEAD` excluding
`.codex/I-naming-010/` and `outputs/audits/I-naming-010/` (the canonical diff
in `.codex/I-naming-010/codex_diff.patch`, sha256 trailer). It implements the
Codex-APPROVE'd brief `.codex/I-naming-010/brief.md` (brief APPROVE iter 1).
Pure rename — 4 files, +15/-15, 1 history-preserving `git mv`. Last of the
#437-444 naming-audit series.

## 2. The diff

- `git mv` `graph_v4.py` → `pipeline_a_ui_adapter.py` (99%).
- 4 targeted substring patterns + 1 coupled assertion (see brief §2):
  pattern 1 `polaris_graph.graph_v4 import` (7×), pattern 2 `polaris_graph
  import graph_v4` (3×), pattern 3 `graph_v4.build_and_run_v4(` (3×),
  pattern 4 the module's title docstring (1×); coupled
  `test_b102_graph_v4.py:197` assertion string (1×).

## 3. Verify against the brief — focus on the two landmines

1. **LANDMINE — output path UNCHANGED**: `pipeline_a_ui_adapter.py:246`
   `"outputs/polaris_graph_v4_runs"` must be UNCHANGED — it is a runtime
   output-dir default that *contains* the `graph_v4` substring; renaming it
   relocates artifacts. Confirm `grep -rc "polaris_graph_v4_runs"` → still 1.
2. **COUPLED assertion**: `test_b102_graph_v4.py:197` must now assert
   `'pipeline_a_ui_adapter import build_and_run_v4'`, and `live_server.py:557`
   must actually contain that string — they must match (the test reads
   live_server.py source). Pytest confirms.
3. Zero `polaris_graph.graph_v4 import` / `polaris_graph import graph_v4` /
   `graph_v4.build_and_run_v4` residue in `src/`+`tests/`+`scripts/`.
4. The public `build_and_run_v4` API name is UNCHANGED (`v4` ≠ `graph_v4`,
   not in scope).
5. The 3 sibling LangGraph entrypoints (`graph.py`/`graph_v2.py`/`graph_v3.py`)
   are UNCHANGED — `live_server.py`'s `PG_GRAPH_VERSION` v3/v2/v1 branches
   untouched.
6. `git mv` preserved history (diff shows `rename … (99%)`).
7. No behaviour change — pure rename.

## 4. Files I have ALSO checked and they're clean

- `grep -rn "graph_v4"` whole repo: every `.py` hit is accounted for —
  importers updated; the renamed module's internal comment (`:210`) +
  output-path (`:246`) deliberately untouched; the 2 test files' filenames +
  test function names left (file + import-path scope, brief §3b);
  conceptual prose in `decomposer.py` / `followup/__init__.py` /
  `nodes/scope_gate.py` / `polaris_v6/adapters/evidence_pool_merger.py` /
  `polaris_v6/schemas/run_request.py` / `tests/v6/test_evidence_pool_merger.py`
  / `scripts/autoloop/backfill_pre_bootstrap_verdicts.py` left as descriptive
  prose (brief §3d).
- `config/scope_templates/custom.yaml:3` — Codex's iter-1 brief P2 — a YAML
  prose mention, left intact (consistent with all other conceptual prose).
- `docs/**` mentions (substrate_audit, agent_architecture, carney plans,
  pipeline_audit_context, task_acceptance_matrix) — point-in-time
  audit/plan records, left per the #436-443 precedent.
- No `importlib` / dynamic-import / string-path reference to `graph_v4`.

## 5. Test state

`ast.parse` 4/4 clean. Import smoke resolves `build_and_run_v4` + 4 helpers.
`PYTHONPATH='src;.' pytest tests/polaris_graph/test_b102_graph_v4.py
tests/polaris_graph/test_graph_v4_documents.py` → 16 passed (incl. the
coupled live-server source-assertion test).

## 6. Required output schema (§8.3.9)

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

Loose verdict prose is rejected — emit the schema.
