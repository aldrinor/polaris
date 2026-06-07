HARD ITERATION CAP: 5 per document. This is iter N of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

---

# Codex diff-gate — I-ready-018 cluster A (#1138): import-root alias (your C3 ruling)

This implements YOUR design ruling C3 (.codex/I-ready-018/clusterA_design_verdict.txt). Review the
IMPLEMENTATION for correctness + faithfulness + run-safety.

## Output schema (REQUIRED — last `verdict:` line authoritative)
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

## The diff (`.codex/I-ready-018/c3_codex_diff.patch`)
1. **`src/sitecustomize.py`** (NEW) — a `MetaPathFinder` that aliases bare `polaris_graph[.sub]` →
   canonical `src.polaris_graph[.sub]` so both spellings are the SAME module object.
   - **Location is `src/` NOT repo-root**: you specified repo-root sitecustomize, but empirically a
     repo-root `sitecustomize.py` does NOT auto-load here (CPython does not import sitecustomize from
     CWD reliably; `'' in sys.path` but `'sitecustomize' in sys.modules` was False). `src/` IS on
     `sys.path` whenever the dual-root condition exists (V6 server + pytest both run `PYTHONPATH=src`),
     so `src/sitecustomize.py` auto-loads in exactly those contexts. The beat-both RUN is `src.`-only
     single-root (no `PYTHONPATH=src`) → it never loads this and never needs it (no dual identity).
   - Idempotent (meta_path membership check via `_tag`); fail-fast on pre-loaded divergence; recursion
     guard via `_in_progress`.
   - **Deadlock fix (important)**: my first version held a non-reentrant `threading.Lock` across
     `importlib.import_module(canonical)`, which re-enters the finder for the canonical module's own
     bare submodule imports → deadlock (3 pytest procs hung). REMOVED the lock — CPython's import
     system already serializes per-module (`_bootstrap._ModuleLock`); the `_in_progress` set is the
     sufficient recursion guard. Please confirm there is no remaining deadlock/recursion path.
2. **`tests/polaris_graph/test_import_root_alias_iready018.py`** (NEW) — identity regression tests:
   bare and src `VerifiedSentence`/`Section`/`strict_verify`/`provenance`/`generator` are the SAME
   object under the both-roots pytest path; skip cleanly under single-root.
3. **`tests/polaris_graph/test_demo_smoke.py`** — ENV_ONLY: set `POLARIS_AUTH_DISABLED=1` +
   `POLARIS_STATIC_ACCOUNTS_PATH` (committed fixture) before importing `create_app` (was a collection
   error: `static_accounts.yaml not found`).

## Evidence
- **Cascade 115 passed / 0 failed** (`outputs/audits/I-ready-018/c3_cascade_verify.txt`):
  test_generator(15) + provenance_entailment(4) + strict_verify + golden slice_003(5) + all 4 V6 api
  routes + demo_smoke — the ~36-failure cluster A + demo_smoke all GREEN.
- **Run-safety re-verified**: root-only `python -c "import src.polaris_graph.clinical_generator.strict_verify"`
  works WITHOUT `PYTHONPATH=src` (the beat-both run import path is untouched); both-roots
  `bare VerifiedSentence is src VerifiedSentence` → True.
- **Full-sweep regression check** (the global-hook safety gate) result will be appended; baseline was
  5592 passed.

## Faithfulness (your ruling: faithfulness_risk none under the full-prefix early alias)
The alias collapses `strict_verify`/`provenance` to ONE module object → ONE `_JUDGE_SINGLETON` + one
telemetry-counter set (your stated faithfulness-POSITIVE outcome). No strict_verify/provenance import
PREFIX was changed (per your instruction). No production logic changed.

## Specific risks to adjudicate
1. **Deadlock/recursion**: with the lock removed, is the `_in_progress` set + CPython per-module lock
   sufficient under concurrent imports (the 4-role seam ThreadPoolExecutor)? Any residual re-entrancy
   that could deadlock or double-register a module?
2. **Fail-fast correctness**: the divergence check raises if both spellings are already loaded to
   different objects. Is that the right safety posture, and can it false-positive during normal
   partial-init (a module present in sys.modules but mid-execution)?
3. **`src/` location vs your repo-root spec**: does `src/sitecustomize.py` satisfy the intent for the
   V6 server (`PYTHONPATH=src` → loads before app import) AND pytest, while correctly NOT loading for
   the `src.`-only run? Confirm `-S` is not used by any entrypoint (verified: no `-S` in CI/Docker).
4. Any faithfulness-invariant risk (strict_verify / provenance / 4-role / two-family) you can see in
   making bare and src. the same object?

## Files I have ALSO checked
- No repo-root `conftest.py`/`sitecustomize.py` pre-existed. No `python -S` in `.github/workflows/*` or Dockerfile.
- `src/__init__.py` + `src/polaris_graph/__init__.py` both exist (the dual-tree precondition).
- The beat-both run launches `python -m scripts.dr_benchmark.run_gate_b` from repo-root (src.-only).
