```
HARD ITERATION CAP: 5 per document. This is iter 2 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

**REVIEW ONLY — do not modify any file. Judge this brief's acceptance criteria + the routed decision; return the YAML verdict block only.**

---

# Codex BRIEF review — I-ready-016b: ACTIVATE the readiness faithfulness flags in the Gate-B full-capability slate

## §0 What this brief asks you to judge

This is a **brief-gate**, iter-2. **Iter-1 returned REQUEST_CHANGES with 1 P1 + 1 P2; both are addressed:**
- **P1 (the `float('local')` crash):** `PG_DOC_INGEST_BACKEND` is now LEFT OUT of the benchmark slate entirely (§5) — the change touches only the 3 benchmark-critical flags.
- **P2 (verification path):** AC3 now verifies via an offline env-capture / fake-transport test, NOT `run_gate_b --list` (§6.3).

Judge:
1. Are the (corrected) acceptance criteria correct, complete, and verifiable?
2. Any P0/P1 execution risk in the PROPOSED CHANGE itself (a flag that would weaken a gate, an import-order trap, a preflight that bites a legitimate run).

Return the §8.3.9 YAML schema only.

## §1 Problem (grounded, not paraphrased)

Three readiness faithfulness features shipped flag-gated **default OFF** so that flag-OFF is byte-identical to prior behavior (the established `_BENCHMARK_FORCE_ON_FLAGS` pattern in this same file). They are:

- **`PG_USE_SAFETY_REFUSAL`** (#1072, I-ready-007) — input harm-refusal. Read at `scripts/run_honest_sweep_r3.py:1689` (`os.getenv("PG_USE_SAFETY_REFUSAL", "0").strip() in ("1","true","True")`) and `src/polaris_graph/api/intake.py:140`. Default OFF → the whole pre-retrieval refusal block is skipped. High-precision classifier (keys on explicit harm-INTENT clause, never clinical/policy subject) that **FAILS OPEN** (classifier error → harmful=False → proceed) per the I-ready-007 brief-gate decision (`scripts/run_honest_sweep_r3.py:1687-1688`).
- **`PG_SWEEP_NLI_CONFLICT`** (#1079) — semantic contradiction detector. Default OFF → no judge built, byte-identical (`src/polaris_graph/retrieval/semantic_conflict_detector.py:53,106`; `scripts/run_honest_sweep_r3.py:3123`). Enabled = surfaces MORE contradictions (additive observability).
- **`PG_SWEEP_TABLE_CELL_VERIFY`** (#1084, I-ready-015) — table-cell numeric faithfulness gate. `src/polaris_graph/generator/multi_section_generator.py:2323-2328`: `_table_cell_verify_enabled()` returns True iff the env value is NOT in `{"", "0", "false", "off", "no"}`. So `="1"` enables it; default `""` disables it. The docstring at :2324-2325 literally says *"Default OFF -> byte-identical; turned ON + preflighted in the full-capability benchmark slate after audit."* — i.e. THIS activation is the documented intent.

**The bug being closed:** `scripts/dr_benchmark/run_gate_b.py` is the Gate-B production entrypoint. `apply_full_capability_benchmark_slate()` (:565) + the `run_gate_b_query()` force-on block (:739-782) set every other full-capability flag, but a grep of `run_gate_b.py` for all three names (and for `PG_DOC_INGEST_BACKEND`) returns **No matches**. So a full Gate-B run today leaves all three OFF → they are **inert** on the paid run. That is the silent-downgrade class the operator's no-silent-downgrade directive forbids: a shipped, audited faithfulness layer that never fires on the actual benchmark.

## §2 Where the change goes (exact, line-grounded — `scripts/dr_benchmark/run_gate_b.py`)

**The existing force-on precedent** lives in `run_gate_b_query()`:
- `:768` `os.environ["PG_DEPTH_ANNOTATION_IN_BENCHMARK"] = "1"  # force-on (Codex iter-2 P1-1: .env=0 must not win)`
- `:774` `os.environ["PG_AGENTIC_SEARCH_IN_BENCHMARK"] = "1"  # force-on (...)`
- `:782` `os.environ["PG_NLI_IN_BENCHMARK"] = "1"  # force-on (...)`
- `:787` `preflight_full_capability()` — the fail-closed preflight, called AFTER every cap+flag is applied, BEFORE a single token is spent.

**The slate dict** `_FULL_CAPABILITY_BENCHMARK_SLATE` is at `:411-479` (applied by `apply_full_capability_benchmark_slate()` at :565, FLOOR semantics for numerics, force-exact for `_BENCHMARK_FORCE_ON_FLAGS` :513-530 / `_BENCHMARK_FORCE_EXACT_FLAGS` :535-537).

**The preflight** `preflight_full_capability()` is at `:600-674`. Its required-ON mechanism is `_BENCHMARK_PREFLIGHT_REQUIRED_FLAGS` (:492-503), checked in the loop at `:615-620` (`os.getenv(flag, "0").strip() not in ("1","true","True")` → raise RuntimeError, abort).

## §3 Proposed change (what the diff will do)

**(a) Force-ON in `run_gate_b_query()`** — add three lines mirroring `:782` EXACTLY (direct `os.environ[...] = "1"`, NOT setdefault, so a `.env=0` cannot silently downgrade — same rationale as the existing `# .env=0 must not win` lines), placed in the same force-on block before `preflight_full_capability()` at :787:
```
os.environ["PG_USE_SAFETY_REFUSAL"]      = "1"   # #1072 input harm-refusal (fail-OPEN; never over-refuses)
os.environ["PG_SWEEP_NLI_CONFLICT"]      = "1"   # #1079 semantic contradiction surfacing (additive)
os.environ["PG_SWEEP_TABLE_CELL_VERIFY"] = "1"   # #1084 table-cell numeric faithfulness gate
```

**(b) Extend the fail-closed preflight** — add the three flag names to `_BENCHMARK_PREFLIGHT_REQUIRED_FLAGS` (:492-503) so `preflight_full_capability()` ABORTS loudly (RuntimeError, zero spend) if any of the three is off at preflight time. This is the operator no-silent-downgrade guard: a misconfigured/off flag stops the run before any token is billed.

**Note for the reviewer on the table-cell flag's truthiness:** the required-ON loop at :616 checks `os.getenv(flag, "0").strip() not in ("1","true","True")`. With force-on `="1"`, `"1" in ("1","true","True")` is True → passes. `_table_cell_verify_enabled()` uses a DIFFERENT predicate (`not in {"","0","false","off","no"}`) but `"1"` is truthy under BOTH, so force-on `="1"` satisfies both the preflight check and the module's own gate. No mismatch. (Flagged here so you can confirm the two predicates agree on `"1"`.)

## §4 Faithfulness-safety argument (the core of why this is APPROVE-able)

All three only **ADD** a layer; none weakens or bypasses any existing gate. OFF = the exact prior behavior (byte-identical), which is why they shipped default-OFF:
- **Safety refusal** refuses harmful *inputs* before retrieval; it **fails OPEN** on classifier error (proceed), and is high-precision on explicit harm-INTENT (never over-refuses clinical/policy research). It cannot drop a legitimate verified claim — it operates on the *question*, upstream of generation. Worst case if mis-fired: a refusal of a genuinely-harmful query (the intended behavior).
- **NLI conflict** is additive contradiction *surfacing* (more observability of disagreement among sources); it does not gate or drop generated prose.
- **Table-cell verify** DROPS fabricated/unsupported numeric table rows — a STRENGTHENING of faithfulness, the same direction as strict_verify. It cannot pass a row that strict_verify would have dropped; it can only remove an additional fabrication.

None touches the binding 4-role D8 gate, strict_verify, the entailment verifier (`PG_STRICT_VERIFY_ENTAILMENT=enforce`, already in the slate at :461/:521), or the report.md verified-only surface. The faithfulness machinery is otherwise untouched.

## §5 `PG_DOC_INGEST_BACKEND=local` (#1077) — DECIDED: leave out of the benchmark slate (iter-1 P1 fix)

**Iter-1 verdict caught a real bug in my original lean** and I have corrected the design accordingly: `_FULL_CAPABILITY_BENCHMARK_SLATE` is applied by `apply_full_capability_benchmark_slate()`, whose value-handling path coerces slate values numerically (FLOOR semantics) — so a string entry `PG_DOC_INGEST_BACKEND: "local"` would hit `float("local")` and **abort the whole run before it starts**. Combined with the fact that the benchmark sweep never reads this flag (it attaches docs via `run_gate_b --upload-file` → `DocumentIngester` directly, NOT through `upload.py`), the correct and safe decision is: **DO NOT add `PG_DOC_INGEST_BACKEND` to the benchmark slate at all.**

It is a **deployment-env / UI-demo-path** setting only. It is documented in the runbook (`docs/carney_demo_runbook.md`) as `PG_DOC_INGEST_BACKEND=local` for the UI upload path, NOT in the Gate-B slate. So this change touches ONLY the three benchmark-critical flags (§3); `PG_DOC_INGEST_BACKEND` is out of scope for `run_gate_b.py`.

## §6 Acceptance criteria

1. After the `run_gate_b_query()` force-on block runs, all three flags (`PG_USE_SAFETY_REFUSAL`, `PG_SWEEP_NLI_CONFLICT`, `PG_SWEEP_TABLE_CELL_VERIFY`) are `"1"` in `os.environ` **even if `.env` set them to `0`** (force-on, not setdefault — `.env=0 must not win`, mirroring :782).
2. `preflight_full_capability()` ABORTS loudly (RuntimeError, zero spend) if ANY of the three is off at preflight time (added to `_BENCHMARK_PREFLIGHT_REQUIRED_FLAGS`).
3. The three ON-state is verified via an OFFLINE env-capture path, NOT `run_gate_b --list` (iter-1 P2 fix: `--list` deliberately snapshots/restores `os.environ` and never calls `run_gate_b_query`/`preflight_full_capability`, so it cannot observe the activation). Use the same technique as `tests/dr_benchmark/test_run_gate_b_cli.py::test_per_question_path_threads_fake_transport_into_run_one_query` — call `run_gate_b_query` with an injected FAKE transport + a monkeypatched `run_one_query`, then assert `os.environ["PG_USE_SAFETY_REFUSAL"/"PG_SWEEP_NLI_CONFLICT"/"PG_SWEEP_TABLE_CELL_VERIFY"] == "1"` (no network, no spend). The preflight-bites assertion (AC5-ii) is a direct `preflight_full_capability()` call with one flag forced off → `RuntimeError`.
4. The faithfulness machinery is otherwise untouched: no change to strict_verify, the 4-role D8 gate, the entailment verifier, the report.md verified-only surface, or any numeric cap. Only these three flags + the preflight required-set are added.
5. A **behavioral** test proves: (i) force-on overrides `.env`/`os.environ`-preset `=0` (set all three to `"0"`, call the force-on path, assert `"1"`); AND (ii) the preflight BITES — with one of the three forced off after the slate, `preflight_full_capability()` raises RuntimeError naming that flag (the fail-closed guard actually triggers).

## §7 Files I have ALSO checked and they're clean

- `src/polaris_graph/nodes/safety_classifier.py` — present on this consolidated branch; classifier reads nothing new; gating is at the caller (run_honest_sweep_r3.py:1689 / intake.py:140), default-OFF byte-identical. Fails OPEN on error.
- `src/polaris_graph/retrieval/semantic_conflict_detector.py` — present; `_FLAG="PG_SWEEP_NLI_CONFLICT"` (:53), default-OFF returns byte-identical (:106), no judge constructed when off (:424). Additive-only.
- `src/polaris_graph/generator/multi_section_generator.py` — `_table_cell_verify_enabled()` (:2323-2328) default-OFF byte-identical; ON drops only fabricated cells; docstring states this slate is the intended activation.
- `src/polaris_v6/api/upload.py:65` — the ONLY consumer of `PG_DOC_INGEST_BACKEND`; confirms the benchmark sweep does not route through it (HTTP upload path only).
- `scripts/dr_benchmark/run_gate_b.py` — grep for all four env names returns No matches → none currently set → a full run leaves them OFF (the inert-feature bug this closes). The force-on precedent (:768/:774/:782) and `_BENCHMARK_PREFLIGHT_REQUIRED_FLAGS` (:492-503) are the exact mechanisms reused.

## §8 Output schema (§8.3.9 — return ONLY this)

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
routed_decision_PG_DOC_INGEST_BACKEND: include_setdefault_not_preflight | leave_out_of_slate | <your corrected instruction>
```
