HARD ITERATION CAP: 5 per document. This is iter 2 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

---

# Codex diff-gate iter-2 — I-ready-018 cluster A (#1138): import-root alias

You REQUEST_CHANGES'd iter-1 with 2 P1 + 3 P2. All addressed. Cumulative diff:
`.codex/I-ready-018/c3_codex_diff_iter2.patch` (iter-2 delta) over commit 85a24ec7 (iter-1).
Current files: `src/_polaris_import_alias.py`, `src/sitecustomize.py`, `scripts/dr_benchmark/run_gate_b.py`,
`tests/polaris_graph/test_import_root_alias_iready018.py`, `tests/polaris_graph/test_demo_smoke.py`.

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

## How each iter-1 finding was addressed
- **P1-1 (run-safety, Gate-B bare imports root-only)**: The finder was refactored into a STANDALONE
  module `src/_polaris_import_alias.py` (imports nothing from the aliased packages → no chicken-and-egg)
  that aliases BOTH `polaris_graph`→`src.polaris_graph` AND `polaris_v6`→`src.polaris_v6`. It is now
  installed in BOTH contexts: `src/sitecustomize.py` (server/pytest auto-load) AND explicitly at the
  TOP of `scripts/dr_benchmark/run_gate_b.py` (before any repo import) so the root-only run is safe for
  accidental/`--upload-file` bare imports. `run_gate_b.py:1099` upload imports also normalized to `src.`.
  VERIFIED: root-only (no `PYTHONPATH=src`) `_resolve_benchmark_upload('x.pdf','public')` now raises
  FileNotFoundError (imports resolved), NOT ModuleNotFoundError. The deeper cause was `polaris_v6`'s
  pre-existing bare-import debt (37 files) reached via the upload path — the run-entry alias covers it
  without a 37-file migration.
- **P1-2 (test_demo_smoke not hermetic)**: now force-sets `POLARIS_GPG_KEY_ID`, `SERPER_API_KEY`,
  `OPENROUTER_API_KEY`, `OPENAI_API_KEY`, `S2_API_KEY` to `""` (override, not setdefault) before importing
  `demo_smoke`/`create_app`, so ambient `.env` (loaded by `src/__init__`'s `load_dotenv`) cannot drive a
  live backend / `build_gpg_signer` at collection.
- **P2-1 (bad skip predicate)**: `test_import_root_alias` now skips on the definitive signal — the alias
  finder's `_tag` present on `sys.meta_path` — not a `sys.path` heuristic. Clean skip under single-root / `-S`.
- **P2-2 (bare-only absolute-PYTHONPATH launch breakage)**: `find_spec` returns None when the canonical
  `src.<root>` tree is NOT importable (cached per root), so a legitimate bare-only launch defers to the
  default machinery.
- **P2-3 (package __spec__/__path__ None until reload)**: `exec_module` now restores the canonical
  `__path__` (from `submodule_search_locations`) on FIRST import, so `importlib.resources`/pkgutil work
  on aliased packages immediately.

## Evidence
- Targeted: 43 passed (identity tests + demo_smoke + real_completion) under `PYTHONPATH=src`.
- Identity collapse VERIFIED for BOTH roots: `polaris_graph.*.VerifiedSentence is src.polaris_graph...` →
  True; `polaris_v6.queue.run_store is src.polaris_v6.queue.run_store` → True.
- Run-safety: root-only `import src.polaris_graph.clinical_generator.strict_verify` works; root-only
  `_resolve_benchmark_upload` imports resolve.
- Full sweep (tests/polaris_graph + roles + dr_benchmark + v6) running; the iter-1 committed C3 already
  took the offline sweep to 2 failed / 6569 passed / 0 collection errors (the 2 = key-gated GPG
  signed-bundle conformance fixtures, which need the test signing key — separate, run-irrelevant). I will
  append the iter-2 sweep result.

## Specific risks to adjudicate
1. Aliasing `polaris_v6` (new in iter-2) widens the hook's blast radius to a 37-file subsystem. Any
   dual-tree behavior in v6 tests that this could break? (full v6 sweep included.)
2. Installing the alias from `run_gate_b` top-of-module: safe ordering (before the first repo import)?
   Any import-cycle or double-install hazard? (install is idempotent via the meta_path `_tag`.)
3. The standalone installer is imported as bare `_polaris_import_alias` (sitecustomize) AND
   `src._polaris_import_alias` (run_gate_b) — two module objects of the INSTALLER itself, but install is
   idempotent so only one finder is added. Acceptable?
4. Faithfulness: still collapses strict_verify/provenance to one module + one `_JUDGE_SINGLETON`; no
   prefix changed in strict_verify/provenance; no production logic changed.
