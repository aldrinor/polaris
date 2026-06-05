# Codex DIFF review — I-ready-016b (#1097): activate the 3 readiness faithfulness flags in the Gate-B slate

```
HARD ITERATION CAP: 5 per document. This is iter 1 of 5 (diff).
- Front-load ALL real findings in iter 1. No drip-feeding. Same quality bar regardless of iteration.
- Don't pick bone from egg: reserve P0/P1 for real execution risks.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

**REVIEW ONLY — do not modify any file. Return the YAML verdict block ONLY. Claude authored the diff (commit 78770645 on bot/I-ready-consolidated).**

---

## 0. Context

Brief-gate APPROVE'd (iter-2; the iter-1 P1 `float('local')` crash → PG_DOC_INGEST_BACKEND left OUT of the slate; iter-1 P2 → verification via fake-transport env-capture). This diff activates the 3 benchmark-critical readiness faithfulness flags in `scripts/dr_benchmark/run_gate_b.py` (they shipped flag-gated default-OFF; the slate previously set NONE of them, so a full run was inert — the silent-downgrade class).

## 1. The change

(a) In `run_gate_b_query()`, immediately after the existing `os.environ["PG_NLI_IN_BENCHMARK"] = "1"` force-on line: three new force-on lines (`PG_USE_SAFETY_REFUSAL`, `PG_SWEEP_NLI_CONFLICT`, `PG_SWEEP_TABLE_CELL_VERIFY` = "1"), mirroring the exact `.env=0 must not win` pattern.
(b) The same three added to `_BENCHMARK_PREFLIGHT_REQUIRED_FLAGS` so `preflight_full_capability()` fails closed (RuntimeError, zero spend) if any is off.
NO `PG_DOC_INGEST_BACKEND` (Codex-ruled leave-out; it gates the v6 UI upload path, not the benchmark, and would crash `apply_full_capability_benchmark_slate` via `float('local')`).

## 2. Adversarially check (my claims to refute)

- **Faithfulness-safe / additive only:** each flag only ADDS a layer — safety-refusal classifier on the input question (fail-OPEN, never over-refuses clinical/policy research), NLI semantic-conflict surfacing (additive observability, gates nothing), table-cell numeric verify (DROPS only fabricated cells, same direction as strict_verify). None weakens or bypasses the 4-role D8 gate, strict_verify, the entailment verifier, or report.md. Confirm no path weakens a gate.
- **Force-on truthiness vs preflight predicate:** force-on `="1"`; the preflight loop checks `os.getenv(flag,"0").strip() in ("1","true","True")` → "1" passes; the table-cell module's own gate uses `not in {"","0","false","off","no"}` → "1" truthy under both. Confirm the two predicates agree on "1".
- **No silent downgrade:** a `.env`/`os.environ` preset of `0` is overridden by the force-on (test asserts this); a misconfigured-off at preflight time aborts before spend (test asserts the preflight bites). Confirm.
- **Scope:** ONLY these 3 flags + the preflight required-set; no cap/model/role/verifier change; PG_DOC_INGEST_BACKEND correctly absent. Confirm.

## 3. Verification done (offline, no spend)

`tests/dr_benchmark/test_slate_readiness_flags_iready016b.py` (4 tests) + `tests/dr_benchmark/test_run_gate_b_cli.py` (17) = 21 passed: force-on overrides preset-0 (via fake-transport env-capture); preflight raises when one is forced off; CLI suite unaffected. `verify_lock --consistency` OK.

## 4. Output schema (return EXACTLY this)

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

---

## 5. The full committed diff (`git diff HEAD~1..HEAD`)

```diff
diff --git a/scripts/dr_benchmark/run_gate_b.py b/scripts/dr_benchmark/run_gate_b.py
index d54d3bd0..7a1e2c4e 100644
--- a/scripts/dr_benchmark/run_gate_b.py
+++ b/scripts/dr_benchmark/run_gate_b.py
@@ -500,6 +500,12 @@ _BENCHMARK_PREFLIGHT_REQUIRED_FLAGS = (
     # capped-dedup OFF would let the no-cap relevance-floor pool re-flood the generator (regress #1070).
     "PG_USE_FINDING_DEDUP",
     "PG_CAPPED_FINDING_DEDUP",
+    # I-ready-016b (#1097): the 3 readiness faithfulness layers MUST be on for Gate-B — each only ADDS a
+    # check (safety-refusal classifier / NLI semantic-conflict detection / table-cell numeric verify), so
+    # OFF is a silent faithfulness downgrade. Force-on in run_gate_b_query; fail closed here if any is off.
+    "PG_USE_SAFETY_REFUSAL",
+    "PG_SWEEP_NLI_CONFLICT",
+    "PG_SWEEP_TABLE_CELL_VERIFY",
 )
 
 # Codex diff-gate I-cap-005 P1-2: the minimum EFFECTIVE per-run budget cap. PG_MAX_COST_PER_RUN is an
@@ -780,6 +786,13 @@ async def run_gate_b_query(
     # pathB preflight requires PG_ENTAILMENT_MODEL == PG_EVALUATOR_MODEL and the default already
     # satisfies it. setdefault keeps the operator override (LAW VI).
     os.environ["PG_NLI_IN_BENCHMARK"] = "1"                # force-on (Codex iter-2 P1-1: .env=0 must not win)
+    # I-ready-016b (#1097): activate the 3 readiness faithfulness layers for the benchmark. Each only ADDS
+    # a layer (safety-refusal classifier / NLI semantic-conflict detection / table-cell numeric verify) — a
+    # gate is only ever STRENGTHENED, never weakened. Force-on so a conservative .env=0 cannot silently
+    # downgrade the run (operator no-downgrade directive); validated fail-closed by preflight below.
+    os.environ["PG_USE_SAFETY_REFUSAL"] = "1"              # force-on (Codex iter-2 P1-1: .env=0 must not win)
+    os.environ["PG_SWEEP_NLI_CONFLICT"] = "1"              # force-on (Codex iter-2 P1-1: .env=0 must not win)
+    os.environ["PG_SWEEP_TABLE_CELL_VERIFY"] = "1"         # force-on (Codex iter-2 P1-1: .env=0 must not win)
     # I-cap-005 (#1068) KEYSTONE: FAIL CLOSED here — AFTER every cap+flag is applied, BEFORE a single
     # token is spent. If any effective retrieval cap is below the full-capability floor, or any required
     # feature flag / the tool tracker is off, this raises RuntimeError and the run aborts. A silent throttle
diff --git a/tests/dr_benchmark/test_slate_readiness_flags_iready016b.py b/tests/dr_benchmark/test_slate_readiness_flags_iready016b.py
new file mode 100644
index 00000000..8b5dfd38
--- /dev/null
+++ b/tests/dr_benchmark/test_slate_readiness_flags_iready016b.py
@@ -0,0 +1,110 @@
+"""Offline tests for the I-ready-016b (#1097) readiness faithfulness flags in the Gate-B slate.
+
+NO network, NO spend anywhere. Covers:
+  * run_gate_b_query FORCE-ONs the three readiness faithfulness flags
+    (PG_USE_SAFETY_REFUSAL / PG_SWEEP_NLI_CONFLICT / PG_SWEEP_TABLE_CELL_VERIFY) even when the
+    process env presets them to "0" — a conservative .env=0 must NOT win (operator no-downgrade);
+  * the fail-closed preflight raises RuntimeError (aborting BEFORE any spend) naming a flag if any of
+    the three is off AFTER the slate is applied.
+
+These flags only ADD a faithfulness layer (safety-refusal classifier / NLI semantic-conflict /
+table-cell numeric verify) — a gate is only ever STRENGTHENED here, never weakened.
+
+Hermetic: env is snapshotted/restored (the _isolate_env autouse fixture) so a forced flag does not
+leak into sibling tests. Mirrors tests/dr_benchmark/test_run_gate_b_cli.py conventions.
+"""
+
+from __future__ import annotations
+
+import asyncio
+import os
+from pathlib import Path
+
+import pytest
+
+from scripts.dr_benchmark import run_gate_b
+from scripts.dr_benchmark.run_gate_b import (
+    _BENCHMARK_PREFLIGHT_REQUIRED_FLAGS,
+    apply_full_capability_benchmark_slate,
+    load_locked_questions,
+    main,  # imported for parity with the sibling CLI test module conventions
+    preflight_full_capability,
+    run_gate_b_query,
+)
+
+# The three readiness faithfulness flags activated by I-ready-016b (#1097).
+_READINESS_FLAGS = (
+    "PG_USE_SAFETY_REFUSAL",
+    "PG_SWEEP_NLI_CONFLICT",
+    "PG_SWEEP_TABLE_CELL_VERIFY",
+)
+
+
+@pytest.fixture(autouse=True)
+def _isolate_env():
+    """Snapshot os.environ before each test and restore it after, so a forced readiness flag (or the
+    full-capability slate) does not leak into sibling tests."""
+    snap = dict(os.environ)
+    try:
+        yield
+    finally:
+        os.environ.clear()
+        os.environ.update(snap)
+
+
+# --------------------------------------------------------------------------- force-on
+
+def test_run_gate_b_query_force_ons_readiness_flags_over_preset_zero(monkeypatch):
+    """run_gate_b_query must FORCE the three readiness faithfulness flags ON even when the process env
+    presets them to "0" (a conservative .env value must NOT win — operator no-downgrade directive).
+    run_one_query is monkeypatched to a recording async fake so the real retrieval/generation pipeline
+    (network + spend) never executes; an injected fake transport means no real transport is built."""
+    # Preset all three OFF in the process env — the slate/force-on must beat this.
+    for flag in _READINESS_FLAGS:
+        os.environ[flag] = "0"
+
+    captured = {}
+
+    async def _fake_run_one_query(q, out_root, **kwargs):
+        captured["q"] = q
+        captured["kwargs"] = kwargs
+        return {"status": "success", "slug": q["slug"]}
+
+    monkeypatch.setattr("scripts.run_honest_sweep_r3.run_one_query", _fake_run_one_query)
+
+    q = load_locked_questions(("drb_72_ai_labor",))[0]
+    fake_transport = object()  # never invoked — run_one_query is faked
+    summary = asyncio.run(
+        run_gate_b_query(q, Path("outputs/__test_unused__"), transport=fake_transport)
+    )
+
+    assert summary["status"] == "success"
+    # The recording fake actually ran (proves run_gate_b_query reached the force-on lines + preflight).
+    assert captured["q"]["slug"] == "drb_72_ai_labor"
+    # Force-on beat the preset "0" for all three readiness faithfulness flags.
+    for flag in _READINESS_FLAGS:
+        assert os.environ.get(flag) == "1", f"{flag} not force-on over preset 0"
+
+
+# --------------------------------------------------------------------------- fail-closed preflight
+
+@pytest.mark.parametrize("off_flag", _READINESS_FLAGS)
+def test_preflight_fails_closed_when_a_readiness_flag_is_off(off_flag):
+    """With the full-capability slate applied but ONE readiness flag forced back off, the fail-closed
+    preflight must raise RuntimeError naming that flag — so a silently-downgraded faithfulness layer can
+    never reach a paid run. Apply the slate first (matches the run order), then turn the one flag off."""
+    apply_full_capability_benchmark_slate()
+    # run_gate_b_query (not the slate) sets the feature flags the preflight requires, so satisfy EVERY
+    # required flag here to isolate the failure to off_flag — otherwise the preflight trips on the first
+    # unset required flag (e.g. PG_DEPTH_ANNOTATION_IN_BENCHMARK) instead of the readiness flag under test.
+    for flag in _BENCHMARK_PREFLIGHT_REQUIRED_FLAGS:
+        os.environ[flag] = "1"
+    # The binding-verifier enforce mode is also required by the preflight (set by the slate to "enforce",
+    # but make it explicit so this test stays independent of slate ordering).
+    os.environ["PG_STRICT_VERIFY_ENTAILMENT"] = "enforce"
+    # Now turn OFF only the readiness flag under test — the preflight must name exactly it.
+    os.environ[off_flag] = "0"
+
+    with pytest.raises(RuntimeError) as exc:
+        preflight_full_capability()
+    assert off_flag in str(exc.value)

```
