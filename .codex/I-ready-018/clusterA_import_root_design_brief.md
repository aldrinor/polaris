# Codex DESIGN consult — POLARIS import-root dual-identity (I-ready-018 cluster A)

You are a senior Python architect. I need a DESIGN RULING (not a code review) on how to fix a
dual-module-identity bug, with a hard constraint that the fix must NOT break the production
beat-both run. Reply with the schema at the end.

## The bug (empirically confirmed)
`src/` is a package (`src/__init__.py` exists) AND `src/polaris_graph/__init__.py` exists. So when
both repo-root AND `src/` are on `sys.path`, Python builds TWO distinct module trees:
`polaris_graph.*` and `src.polaris_graph.*`. Proven: `import polaris_graph.clinical_generator.verified_report as A; import src.polaris_graph.clinical_generator.verified_report as B; A.VerifiedSentence is B.VerifiedSentence` → **False** (two distinct classes).

`src/polaris_graph/clinical_generator/` MIXES import prefixes:
- BARE (`from polaris_graph.clinical_generator...`): `generator.py`, `real_completion.py`, `verified_report.py`, `section_blueprint.py`
- SRC (`from src.polaris_graph.clinical_generator...`): `strict_verify.py` (lines 49,56,60,126), `provenance.py` (line 23)

Consumers of clinical_generator use BARE: `src/polaris_graph/api/generation_route.py:28,32`, `src/polaris_v6/api/app.py:134`, `disambiguation_route.py:14`.

When both roots are live, `generator.py` (bare) builds a `Section(verified_sentences=[...])` whose
field type is the BARE `VerifiedSentence`, but `strict_verify.verify_sentence_to_record()` (src.)
returns a SRC `VerifiedSentence` → pydantic v2 `model_type` ValidationError → caught as
`GenerationError(code='completion_backend_unavailable')` → every section aborts. This cascades to
~36 test failures: `test_generator.py` (15), V6 api route tests (~11), `golden/test_slice_003` (5),
`test_provenance_generator_entailment` (4), `test_strict_verify::test_to_record_passes` (1).

## Where both roots are live (the constraint that breaks naive fixes)
- **V6 UI server** (`web_ci.yml:89`): `PYTHONPATH=src nohup python -m uvicorn polaris_v6.api.app:app` → `src/` (PYTHONPATH) AND repo-root (`python -m` CWD) both on path → BOTH trees live → the bug is LIVE in the V6 server, not just tests.
- **pytest** (`PYTHONPATH=src`, pytest rootdir=repo-root) → both trees live → the 36 test failures.
- **beat-both RUN** (`python -m scripts.dr_benchmark.run_gate_b` from repo-root, NO `PYTHONPATH=src`): ONLY repo-root on path → ONLY `src.polaris_graph` resolves, bare `polaris_graph` does NOT → single tree → NO dual identity. The run path (`run_honest_sweep_r3` → `multi_section_generator.py:2409` → `provenance_generator.py:1464/1532/1694`) imports `clinical_generator.strict_verify` via **`src.`** and works.

## Why each naive direction is unsafe (this is the crux)
1. **Normalize `strict_verify.py`/`provenance.py` bare** (WF-A's suggestion, to match the subpackage + bare consumers): BREAKS THE BEAT-BOTH RUN. The run is `src.`-only; `provenance_generator.py` + `multi_section_generator.py` import `from src.polaris_graph.clinical_generator.strict_verify import ...`. If `strict_verify.py` internally imports `provenance`/`verified_report` via **bare**, then under the run's `src.`-only path those bare imports fail → `strict_verify` import error → run crashes. (strict_verify = faithfulness invariant 9.1#3; provenance_generator is the production verifier on the run path.)
2. **Normalize the clinical_generator subpackage `src.`** (match the 146-file repo majority): the V6 consumers (`generation_route.py`/`app.py`) import clinical_generator via **bare**; under the V6 server (both roots) the consumer's bare `VerifiedReport`/`VerifiedSentence` ≠ the generator's now-`src.` ones → boundary mismatch persists at the route.
3. So neither single-direction prefix change fixes BOTH the V6 server AND the run without a deeper unification.

## Candidate fixes (rule on these / propose better)
- **(C1) Remove `src/__init__.py`** so `src.polaris_graph` is NO LONGER a valid package import, then convert ALL `from src.polaris_graph...` (146 src/ files + provenance_generator + multi_section_generator + run_honest_sweep_r3 + the 3 dual-root tests) to bare `polaris_graph`, and ensure every entrypoint puts `src/` on path (the canonical "src layout"). Pro: one true tree forever; canonical. Con: 146-file change; every launcher/CI must set `PYTHONPATH=src` (the run currently relies on repo-root + `src.`).
- **(C2) Standardize on `src.`**: convert the clinical_generator bare files + the bare consumers + the 72 bare test files to `src.polaris_graph`. Pro: matches the 146-file majority + the run path. Con: 72+ test-file change; the `src.` prefix is the non-canonical pattern; brittle if anything is launched with only `src/` on path.
- **(C3) Runtime alias** (a `sitecustomize.py` / root `conftest.py` + a `src/__init__.py` shim) that makes `src.polaris_graph` and `polaris_graph` resolve to the SAME module objects (e.g. `sys.modules['src.polaris_graph'] = sys.modules['polaris_graph']` registration). Pro: ~1 file, no mass edits, fixes BOTH server + tests + run. Con: import-hook magic; must be bullet-proof + load before any clinical_generator import.
- **(C4) Scope-limited:** only unify the clinical_generator subpackage identity (the only place the mix actually causes a pydantic class mismatch) via a local shim, leaving the rest. Pro: smallest blast radius. Con: leaves the latent dual-tree elsewhere.

## Questions for your ruling
1. Which option (C1/C2/C3/C4/other) is the correct fix given the HARD constraint "must not break the beat-both run (`src.`-only path)" AND must fix the live V6 server bug?
2. If C3 (alias): exact mechanism + where it must be installed so it is guaranteed to run before the first clinical_generator import in (a) the V6 server, (b) pytest, (c) the run — and confirm it cannot create import-cycle or double-execution-of-module-side-effects hazards (faithfulness: strict_verify module-level state).
3. Is there a faithfulness risk in ANY option to the strict_verify / provenance / 4-role / two-family invariants? (strict_verify has module-level singletons: `_JUDGE_SINGLETON`, judge telemetry counters — a duplicate module tree means duplicate singletons; flag if the chosen fix changes that.)
4. Severity/scoping: is cluster A correctly a SEPARATE refactor issue (it does NOT block the beat-both run), or must it be in the I-ready-018 landmine sweep?

## Output schema (reply EXACTLY this YAML; last `verdict:` line authoritative)
```yaml
verdict: APPROVE   # APPROVE means "design ruling delivered", not code approval
chosen_option: C1 | C2 | C3 | C4 | other
rationale: <2-4 sentences>
exact_mechanism: <concrete steps / files to touch>
beat_both_run_safe: true | false   # does your option keep the src.-only run working?
faithfulness_risk: <none | describe>
separate_issue_ok: true | false   # is it OK to fix cluster A as its own issue, not blocking the run?
remaining_blockers_for_execution: [...]
```
