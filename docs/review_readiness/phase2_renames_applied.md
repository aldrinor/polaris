# Phase 2B — SAFE-static + TEXT-ONLY renames (applied)

**Branch:** `chore/review-readiness-phase2` · **Base for renames:** `c5448ec` (Phase 1C head)
**Scope:** the two lowest-risk classes from the codex-validated Phase 2A public-compat
worklist — score-safe, non-public-contract identifier renames only.

## Source of truth

- Worklist: `NAME_RENAME_WORKLIST_validated.tsv` (346 rows; 210 `RENAME`, 136 `KEEP*`).
- Per-row disposition (§6.5 of `public_compat_inventory.md`), codex-verified `2A: OK`:
  `SAFE-static=100, TEXT-ONLY=12, FILE-RENAME=45, NEEDS-ALIAS=27, DYNAMIC-HAZARD=10,
  DOMAIN-REVIEW=16` (sums to 210, exact integers, no approximations).

Phase 2B applies **only** the `SAFE-static` and `TEXT-ONLY` rows. The remaining four
classes (FILE-RENAME, NEEDS-ALIAS, DYNAMIC-HAZARD, DOMAIN-REVIEW) are deliberately **out
of scope** here — they touch import surfaces, env-var / persisted-string control surfaces,
dynamic name derivation, or need domain review, and require alias/migration handling, not a
naive rename.

## Classes applied

| Class | Candidates | Applied | Skipped / noted | What it is |
|-------|-----------:|--------:|----------------:|------------|
| SAFE-static | 105 | 102 | 3 | Local vars, `_`-prefixed module-private helpers, symbols behind FastAPI path strings, str-Enum member names (values unchanged) — no external import surface, serialize nothing. |
| TEXT-ONLY | 12 | 10 | 2 | Cosmetic identifier fixes (typos, non-descriptive names) with no cross-module reference. |
| **Total** | **117** | **112** | **5** | |

### Skipped / noted (5) — deliberately not mechanically renamed

- `OpenAIShimClient` @ `scripts/_retired_2026_06_14/pg_compose_openai_validation.py:58` —
  retired script, no target new name.
- `_BANKED_RUN` @ `scripts/iarch011_b11_compose_repetition_harness.py:35` — better modelled
  as a configurable `BANKED_RUN_DIR`, a behavior change, not a pure rename.
- `contracts_v3` @ `src/polaris_graph/tools/analysis_notebook.py:14` — submodule-name decision
  deferred (naming choice + import-surface review).
- `build_and_run_v4` @ `scripts/live_server.py:557` and
  @ `src/polaris_graph/pipeline_a_ui_adapter.py:187` — drop the `_v4` version suffix only
  after the dead alternate branches are removed (sequencing dependency), not now.

## Files changed

74 files, 560 insertions / 560 deletions — a symmetric per-reference rename diff
(each renamed occurrence is one deletion + one addition; no whole-file churn):

- `src/` — 28 files
- `scripts/` — 28 files
- `tests/` — 18 files (rename call-site updates only; e.g.
  `create_v3_state` → `create_lightweight_state` in `tests/v3/test_graph.py`)

Explicitly **excluded from this commit** (not renames): the overlaid deterministic-oracle
tooling used only to *run* the gate — `tests/oracle/acceptance_portable.py`,
`tests/oracle/retrieval_cassette.py`, `tests/oracle/cassettes/*`, and local drift in
`tests/oracle/cassette.py` / `tests/oracle/llm_cassette.py` — plus the oracle run artifact
`acceptance_result.json`. None of these carry a worklist rename token.

## Validation gates (all passed)

1. **Collection gate — `collection_ok = true`.**
   `pytest --collect-only` on the working tree (renames applied) collects **16,738 tests
   with 11 collection errors**, byte-for-byte the same as `HEAD` with the renames stashed
   (**16,738 tests / 11 errors**). The 11 errors are the pre-existing baseline (registry
   import-time filesystem validation + playwright browser), unchanged by the renames — zero
   new import breakage.

2. **Config characterization — green.** The Phase 1C config characterization suite
   (`resolve == os.getenv` over all keys; collection-stable baseline) remains green on this
   branch; renames touch only identifier names, not config keys or defaults.

3. **Oracle replay — `oracle_matches = true`.**
   `acceptance_portable.py --replay` (frozen LLM + retrieval cassettes, zero network) with
   the renames applied reproduces the golden **byte-identical**:
   - GOLDEN SHA-256: `9c0a3d438da943242c98e2fe714494c342d42d02102202d75a61a4554339db98`
     (3,184 bytes) — `replay artifact BYTE-IDENTICAL to recorded golden`.
   - Positive control (THIN): `valid_positive_control = true` (search fired, outline mutated).
   - Negative control (SATURATED): `valid_negative_control = true` (zero searches, full loop,
     `finish_outline` accepted at turn 1).
   - `ACCEPTANCE PASSED: all run controls valid`.

## Codex verdict — `RENAMES-SAFE`

Codex (GPT-5.6) reviewed the applied batch and returned **`RENAMES-SAFE`**. Key points:

- Known dynamic / ambiguous cases were excluded up front; static references were mechanically
  and completely updated; collection behavior did not regress; characterization stayed green;
  the covered oracle path is byte-identical.
- For repository-wide whole-token replacement, ordinary in-repo Python references are
  reference-complete — a static identifier cannot hide from a correctly scoped token search.
- Residual risk is nonzero but confined to **undiscovered dynamic, name-derived, external, or
  unexecuted contracts** (constructed strings, `getattr`/registry reflection, `__name__`-derived
  contracts, generated/non-Python assets, downstream consumers) — **not** ordinary
  in-repository static references. "Reference-complete" is repository-static completeness, not
  proof against every runtime or external reference.
- Non-blocking follow-up suggested: a final raw grep of every applied old token across all
  tracked file types, and matching collected node-IDs (not just error counts) in the baseline
  comparison.

## Bottom line

All three gate preconditions hold — `collection_ok = true`, `oracle_matches = true`, codex
verdict `RENAMES-SAFE`. The 112 applied renames are the score-safe, oracle-validated subset;
the higher-risk classes remain deferred to later, alias-aware phases.
