# Codex BRIEF review — I-naming-002 / GH #436: rename v30_runner.py → honest_sweep_job_runner.py

HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

---

## 0.1 Review stage — PRE-IMPLEMENTATION brief review

This is the **brief** review (the plan). The working tree is intentionally
unmodified; the diff review later verifies the applied rename. Evaluate §2-§4
as a plan — especially the §3 scope-boundary call.

## 1. Issue

GH #436 (I-naming-002) — naming-audit follow-up from #434. `v30_runner.py` is
a version-only filename (§4.1 forbids version numbers in names); its docstring
calls it "the V30 Phase-2 sweep JobRunner". Rename to `honest_sweep_job_runner.py`.
P3, mechanical. Branch `bot/I-naming-002` (a normal `I-<prefix>-<NNN>` id — no
re-cut needed).

## 2. The rename (full footprint — grep-verified against HEAD f39bb6be)

### File renames (`git mv`, history-preserving)
- `src/polaris_graph/audit_ir/v30_runner.py` → `honest_sweep_job_runner.py`
- `tests/polaris_graph/test_v30_runner.py` → `test_honest_sweep_job_runner.py`

### Python identifier renames (version-named → descriptive)
- `V30JobRunner` → `HonestSweepJobRunner`  (class, `v30_runner.py:177`)
- `V30RunnerConfig` → `HonestSweepJobRunnerConfig`  (config dataclass, `:165`)
- `make_default_v30_runner` → `make_default_honest_sweep_job_runner`  (`:450`)

### Reference sites updated (3 importers + 2 doc-mentions + 1 comment)
- `src/polaris_graph/audit_ir/__init__.py:29-32,144,149` — import path +
  the 2 identifiers in the import list + `__all__`.
- `src/polaris_graph/audit_ir/inspector_router.py:406,417,418,425` — import
  path, `make_default_*()` call, the `V30JobRunner` docstring/log-msg mentions.
- `tests/polaris_graph/test_honest_sweep_job_runner.py` — import path +
  `V30JobRunner`/`V30RunnerConfig`/`make_default_*` refs + test-fn names.
- `src/polaris_graph/audit_ir/job_runner.py:11` — docstring mention.
- `src/polaris_graph/audit_ir/progress_surfaces.py:17` — docstring mention.
- `src/polaris_graph/llm/openrouter_client.py:61` — comment "matches the
  v30_runner.py default" → the new filename.

## 3. Scope boundary — DELIBERATELY NOT renamed (adjudicate this)

The following carry `v30` but are **protocol / registry data values**, not
filename-or-identifier hygiene — renaming them is a behaviour change, out of a
P3 naming-audit's scope:
- `template_id = "v30_clinical"` (`:187`) + its string refs in error messages
  (`:231/314/353/369`) — the registered job-template id. The inspector router
  registers the runner under `'v30_clinical'`; changing the string changes the
  registry key.
- `SURFACE_KIND`/phase map keys `"v30_phase1"` / `"v30_phase2"` and the log
  tags `"[v30]"` / `"[v30-p2]"` (`:80-131`) — these match the bracketed phase
  tags actually emitted by `scripts/run_honest_sweep_r3.py`; renaming them
  desyncs the phase classifier from the sweep script's real output.
- Docstring prose "V30 Phase-2 sweep" — an accurate description of the sweep
  generation the runner drives; kept as accurate history.

**Question for Codex:** is this scope right — file + Python identifiers
(`V30JobRunner`/`V30RunnerConfig`/`make_default_v30_runner`) renamed,
protocol/registry strings (`"v30_clinical"`, `"v30_phase*"`, `[v30]` tags)
left intact — or should #436 be narrowed to file + import-paths only (leaving
the identifiers)? The full-identifier rename keeps `honest_sweep_job_runner.py`
from exporting a `V30JobRunner` (the inconsistency a half-rename leaves);
the protocol strings are firmly out of scope either way.

## 4. Files I have ALSO checked and they're clean

- `grep -rn "v30_runner" --include=*.py` (excl. `.codex/`, `archive/`,
  `codex_tmp*`, `__pycache__`): the only real importers are
  `audit_ir/__init__.py`, `inspector_router.py`, `test_v30_runner.py`. No
  dynamic import / `importlib` / string-path reference to the module.
- `grep "V30JobRunner" / "make_default_v30_runner"`: all refs are in the 5
  files listed in §2 — no serialized/registry use of these identifiers as
  strings.
- `__pycache__` stale `.pyc` are not committed (gitignored).

## 5. Test / smoke

`git mv` preserves history. After the rename: `ast.parse` the renamed module +
the 3 updated importers; `PYTHONPATH='src;.' pytest tests/polaris_graph/test_honest_sweep_job_runner.py`
+ a `python -c "import src.polaris_graph.audit_ir"` import-closure smoke (the
`__init__.py` re-exports must resolve). No behaviour test applies — pure rename.

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
