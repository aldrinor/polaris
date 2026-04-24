You are auditing M-35 (primary-trial retrieval anchors) as a code
review BEFORE the next full-scale sweep runs. Narrow scope.

## Scope discipline (user mandate)

Audit ONLY the M-35 diff (commit `040af5d`). This is a new retrieval-
side expander that parallels the M-28 regulatory_expander precedent
you approved READY in three passes (commits `ca2f4ff`, `80c7a8f`,
`8c54cd5`). The same abstraction shape — YAML-driven, no baked-in
host / trial / drug names, env-capped emission — was reapplied.

Do NOT invent adversarial probes. If you find a real defect, cite
the exact file + line and a failing scenario that maps to real
generator / retrieval output, not constructed text.

## Context

### V23 problem (Codex DR pass 11 gap #1)

V23 report = 1455 words / 31 citations / release_allowed=true
post-M-34. DR pass 11 verdict: PARTIAL. First named gap:

> Replace the citation mix with primary SURPASS-1, SURPASS-2,
> SURPASS-3, SURPASS-4, SURPASS-5, SURPASS-6, SURPASS-CVOT, and
> SURMOUNT-2/4 trial papers as first-class sources, while retaining
> regulator labels and high-quality meta-analyses as secondary.

V23 corpus (360 sources) had 62 rows mentioning SURPASS/SURMOUNT,
but the primary NEJM/Lancet publications for SURPASS-1/2/3 and
SURMOUNT-1 were NOT present — only conference abstracts and
post-hoc pooled analyses. See
`outputs/full_scale_v23/clinical/clinical_tirzepatide_t2dm/live_corpus_dump.json`.

### The fix

New module: `src/polaris_graph/retrieval/primary_trial_expander.py`
Mirrors `src/polaris_graph/retrieval/regulatory_expander.py` but:
- Query form: `"{anchor}" {question}` (quoted trial name) instead of
  `{question} site:{anchor}`.
- Keyed by sweep SLUG rather than per-domain (trial programs are
  question-specific).
- Env cap: `PG_SWEEP_MAX_PRIMARY_TRIAL_ANCHORS` (default 15, vs
  M-28's 10).
- Rejects entries containing whitespace OR double-quote (would
  break outer `"..."` quoting).

YAML: `config/scope_templates/clinical.yaml` gets a new
`per_query_primary_trial_anchors:` map keyed by slug. Currently
populated only for `clinical_tirzepatide_t2dm` with 11 pivotal
trial names.

Sweep script: one new call adjacent to the M-28 expander call.

### Smoke test I already ran (live Serper)

All four missing-from-V23 primaries surface in Serper top 5:
- `"SURPASS-1" {question}` → Lancet PIIS0140-6736(21)01324-6 at #2
- `"SURPASS-2" {question}` → NEJMoa2107519 at #2
- `"SURPASS-3" {question}` → Lancet Diabetes&Endo landia primary at #4
- `"SURMOUNT-1" {question}` → NEJMoa2206038 at #2

So the fix produces the expected retrieval effect.

## Files to read

```
src/polaris_graph/retrieval/primary_trial_expander.py    (NEW, ~130 LOC)
src/polaris_graph/retrieval/regulatory_expander.py       (M-28 precedent)
tests/polaris_graph/test_m35_primary_trial_expander.py   (NEW, 28 tests)
config/scope_templates/clinical.yaml                      (lines ~115-155, new YAML block)
scripts/run_honest_sweep_r3.py                            (lines ~540-575, expander wiring)
```

DO NOT read:
- `outputs/` (archive enumeration wasted the prior V23-diagnosis pass)
- `state/compare_*.txt` (competitor PDFs, not relevant to code audit)
- `archive/` (historical)
- `loopback/` (unrelated)

## What to verify

1. **Module discipline** — does `primary_trial_expander.py` contain
   any hard-coded trial / drug / domain terms in EXECUTABLE code?
   (The docstring legitimately mentions the Codex gap it addresses;
   the guard test `test_executable_code_contains_no_trial_names`
   enforces the discipline on the AST-parsed string constants and
   names — same principle as M-28's
   `test_module_contains_no_agency_or_host_strings` but adapted for
   trial-name semantics.)

2. **Graceful degradation** — template missing, key missing, slug
   missing, slug value not-a-list, list-with-bad-entries all return
   `[]`. No exceptions propagate. Call site in sweep script wraps
   the template load in try/except and still calls the expander
   with `None` on failure.

3. **Quoting hygiene** — the `"{anchor}"` wrap is safe iff anchor
   contains no `"` and no whitespace. The expander rejects both.
   Is there another escape that could produce a malformed query?
   (e.g. trailing backslash, newline in YAML string, unicode
   quote variants?)

4. **Cap enforcement** — default 15, env override, 0 = disabled,
   negative = clamped, malformed = default. Tests cover all branches.

5. **YAML schema compatibility** — `per_query_primary_trial_anchors`
   coexists with `regulatory_anchors` in the same template. Template
   load (via `scope_gate.load_scope_template`) still succeeds for
   `clinical` (has both), `policy` (regulatory only), `tech` (neither).

6. **Sweep wiring** — the expander is called with `q["slug"]` from
   SWEEP_QUERIES; `q["slug"]` is always a string (it's the dict key
   literal for each entry). Result merged to `_amplified_effective`
   after regulatory queries, before retrieval. No other code path
   reads from `primary_trial_anchors` (so a typo in YAML can only
   manifest as "no extra queries", not as a pipeline crash).

7. **Budget impact** — 11 anchors × existing per-query fan-out
   (Serper up to 50 + S2 up to 50 per template-expanded query) =
   +11 amplified queries. With V22 env (max_serper=50/max_s2=50)
   that's up to 550 extra Serper hits + 550 S2. Is that within
   sane retrieval-budget bounds? Current V22 sweep ran ~362 pre-
   filter candidates → ~344 fetched in ~114 min. Marginal cost
   acceptable, but flag if you see an edge case.

## What counts as a blocker vs medium

- **BLOCKER**: any path that crashes the pipeline, produces a
  malformed query string, leaks a trial/drug name into executable
  Python code (breaks the template-only discipline that M-28 set),
  or silently promotes invalid entries to queries.
- **MEDIUM**: suggest guard tests to add, schema tightening, budget-
  cap tuning, docstring phrasing. Not blocking.
- **LOW**: style / comment clarity.

## Deliverable

Write `outputs/codex_findings/m35_code_audit/findings.md` with:
- Final verdict (READY | BLOCKED | CONDITIONAL)
- Blocker list (zero items if READY)
- Medium follow-ups (non-gating)
- Explicit note on generalization discipline vs M-28 precedent
