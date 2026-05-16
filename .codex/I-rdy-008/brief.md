# Codex BRIEF review — I-rdy-008 (#504): wire live runs into the rich UI

**Type:** BRIEF review (acceptance-criteria correctness). Phase 3.5 of the Carney
demo execution plan. **iter 2 of 5.**

## §0. Iteration cap directive (CLAUDE.md §8.3.1, verbatim, binding)

```
HARD ITERATION CAP: 5 per document. This is iter N of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## §0.5. Changes since iter 1 (REQUEST_CHANGES — 1 P1 + 3 P2)

- **P1 (tier normalization missing)** — addressed: new **dec-5** in §3.2.
  `SourceSpan.source_tier` is `Literal["T1","T2","T3"]`; live artifacts carry
  T4-T7/UNKNOWN. The adapter now maps T1/T2/T3 through and collapses everything else
  → `T3`, matching `artifact_to_slice_chain._normalize_tier`. Tested.
- **P2-1 (`_write_synthetic_artifact_dir` writes no `evidence_pool.json`)** —
  addressed: §5 test plan now explicitly writes `evidence_pool.json` into the
  artifact_dir after calling the helper for happy-path tests.
- **P2-2 ("record the clamp" has no schema field)** — addressed: dec-6 now clamps
  the emitted offsets/`span_text` consistently and **logs** it; no schema expansion.
- **P2-3 (`docs/live_run_artifact_contract.md` not in this checkout)** —
  acknowledged: the contract is on PR #531 (not yet merged to `polaris`); #504
  branches off `polaris`. Codex confirmed the local code shape is consistent with
  the carve. The contract content is reproduced where needed below.
- Codex iter-1 **rulings incorporated** (all 4 questions answered) — see §6.

## §1. Issue + acceptance + scope authority

GH #504 (I-rdy-008, Phase 3.5): make the rich UI endpoints accept a real completed
run ID, not only golden fixtures. Implements the I-rdy-007 contract
`docs/live_run_artifact_contract.md` (PR #531, Codex brief+diff APPROVE).

**Scope = Pattern A only** (Codex iter-1: `pattern-a-only-correct`). The #504 issue
body lists "F13 pin replay, F14 memory"; the I-rdy-007 contract places both in
Pattern C: memory's durability gap is **#508 / I-rdy-012**; pin-replay has no v6
route → carved to a NEW follow-up issue (filed at PR-open; verified #505/#506 do not
cover it). #504 delivers the resolver + adapter + the 4 fixture-bound
`EvidenceContract` endpoints.

Acceptance: a live completed run is inspectable through bundle-JSON / charts /
follow-up / compare; the I-rdy-007 error matrix holds; existing golden-fixture tests
stay green; Codex APPROVE on brief + diff.

## §2. Current state (all files read this session)

The 4 fixture-bound endpoints resolve a run via the hard-coded `_GOLDEN_RUN_INDEX`
dict (`src/polaris_v6/api/bundle.py:45-53`; `charts.py`, `followup.py`, `compare.py`
import it) → load a golden `EvidenceContract` JSON from `tests/v6/fixtures/
evidence_contract_v1/` → a real `run_id` always 404s. The resolver substrate exists:
`run_store.get_run(run_id) → RunStatusResponse{lifecycle_status, pipeline_status,
artifact_dir, …}`; `load_audit_ir(artifact_dir) → AuditIR`. The `bundle.tar.gz`
endpoint is already live-wired (I-arch-001d) — the reference impl.

## §3. The plan

### 3.1 New file `src/polaris_v6/api/live_run_adapter.py`

Holds (a) the **resolver** `resolve_run(run_id) → artifact_dir` applying the
I-rdy-007 §6 error-state matrix (raises typed `HTTPException` 404/422), and (b) the
**adapter** `artifact_dir_to_evidence_contract(artifact_dir, run_status) →
EvidenceContract`. The adapter reuses `load_audit_ir()` + a direct
`evidence_pool.json` read. It is unit-testable in isolation; the 4 endpoints become
thin shells. NOT added to `artifact_to_slice_chain.py` (that file owns the
slice-chain triple).

### 3.2 The 6 adapter decisions — RESOLVED (the spec named some open; this
implementation brief decides them all):

- **dec-1 model identity:** `AuditIR.model_provenance` → if `None`, raw
  `manifest.json` `models` block (`generator` / `evaluator`) → if neither, **422**
  `run not contract-conformant: no model identity`. `family_segregation_passed` =
  `generator_family != evaluator_family` when families known, else compared on the
  model strings' org prefixes; never silently `True`.
- **dec-2 verifier split:** both `verifier_local_pass` and `verifier_global_pass` ←
  `AuditIR.ReportSentence.is_verified` (single bool). A finer split = follow-up.
- **dec-3 frame-coverage rollup:** group `AuditIR.frame_coverage.entries` by
  `(section, slot_id)`; `frame_name ← subsection_title`; `sources_assigned ← entry
  count`; `coverage_percent = (count where status == "pass") / total * 100`.
  `FrameCoverageEntry.status` is a free `str` — only exact `"pass"` counts as pass.
- **dec-4 contradiction projection:** per contract §4 — `contradiction_id ←
  f"contradiction_{cluster_id}"`; `claim_a/_b ← claims[0/1]` (`context_snippet` else
  composed); `evidence_a/_b ← [claims[0/1].evidence_id]`; `section_id` ← first
  `verified_report` section citing `claims[0].evidence_id`, else `"unsectioned"`;
  `resolution` default `"unresolved"`. For **>2 claims/cluster**, fold
  `claims[2:].evidence_id` into `evidence_b` — one `ContradictionRecord` per cluster.
- **dec-5 tier normalization (NEW — Codex iter-1 P1):** `SourceSpan.source_tier` is
  `Literal["T1","T2","T3"]`; pipeline-A artifacts carry T4/T5/T6/T7/UNKNOWN and
  arbitrary strings. The adapter maps `T1`/`T2`/`T3` through verbatim and collapses
  **every other value** (T4+, `UNKNOWN`, blank, unrecognized) → `T3`, matching
  `artifact_to_slice_chain._normalize_tier`. Without this, a live run with a non-T1/2/3
  bibliography entry fails `EvidenceContract` Pydantic validation and 500s every
  Pattern-A endpoint. Tested with a non-T1/2/3 bibliography entry.
- **dec-6 evidence_pool span clamp (Codex iter-1 ruling):** the adapter slices
  `SourceSpan.span_text` from the source body in `evidence_pool.json` (read
  tolerantly: `full_text` ?? `direct_quote` ?? `snippet`, per
  `artifact_to_slice_chain._full_text_for_evidence_id`). When the cited span
  `[span_start:span_end]` exceeds the available body length, the adapter **clamps**
  `span_start`/`span_end` to the body and emits `span_text` = the clamped slice, so
  the emitted offsets and text are mutually consistent; the clamp is **logged**
  (no schema field — `EvidenceContract` v1 is not expanded). If the body is empty
  OR the clamp yields no non-empty overlap, the run is not contract-conformant →
  **422**.

### 3.3 `_GOLDEN_RUN_INDEX` — fallback, not replacement (Codex iter-1: `fallback-ok`)

Each endpoint: resolve `run_store.get_run(run_id)` first; if it returns a row → live
path (resolver + adapter). If `None` → fall back to `_GOLDEN_RUN_INDEX` (golden test
IDs like `golden_clinical_001` are never real `run_id`s, so the resolver returns
`None` for them and the fallback serves them deterministically). Keeps all existing
endpoint tests green with no env-var conditional and no test refactor; matches
contract §5 ("golden fixtures remain valid as test inputs only").

### 3.4 The 4 endpoint rewirings

`bundle.py` `/bundle` JSON, `charts.py`, `followup.py`, `compare.py` — each: try
live resolver+adapter, fall back to golden dict. `bundle.tar.gz` (Pattern B) and the
golden-only `_FIXTURE_DIR` constant are untouched.

## §4. Deliverable files + LOC + cap-exemption (Codex iter-1: `single-pr-exemption-ok`)

- NEW `src/polaris_v6/api/live_run_adapter.py` — resolver + adapter (~120-160 LOC,
  +dec-5/dec-6).
- `bundle.py`, `charts.py`, `followup.py`, `compare.py` — rewiring (~40-80 LOC).
- NEW `tests/v6/test_live_run_adapter.py` — adapter unit tests + one live-path test
  per endpoint (~100-160 LOC).

**Honest estimate ~260-380 LOC — single PR, cap exemption** (Codex iter-1 ruled
`single-pr-exemption-ok`; precedent I-rdy-005 ~800-LOC). The adapter and the
rewiring are one inseparable reviewable unit — splitting yields dead code or
uncompilable endpoints.

## §5. Tests

- Adapter unit tests: build an `artifact_dir` via `_write_synthetic_artifact_dir`
  (from `tests/polaris_v6/api/test_artifact_to_slice_chain.py`). **The helper does
  NOT write `evidence_pool.json`** (Codex iter-1 P2-1) — happy-path tests write a
  small `evidence_pool.json` into the dir after calling the helper. Assert the
  produced `EvidenceContract`: each of dec-1..dec-6; the error matrix (not-found /
  not-completed / abort_* / release-blocked / missing `evidence_pool.json` / no
  model identity / non-T1-2-3 tier collapses not 500s / span-clamp).
- One live-path test per rewired endpoint (real `run_store` row + synthetic
  `artifact_dir` → 200 with adapted data).
- Existing golden-fixture endpoint tests must stay green (the fallback).
- Run: `$env:PYTHONPATH="C:\POLARIS;C:\POLARIS\src"; pytest tests/v6/ -q`.

## §6. Codex iter-1 rulings (incorporated) + residual question

1. **Scope carve** → `pattern-a-only-correct` — applied (§1).
2. **`_GOLDEN_RUN_INDEX`** → `fallback-ok` — applied (§3.3).
3. **Cap exemption** → `single-pr-exemption-ok` — applied (§4).
4. **`evidence_pool.json` span** → `clamp` (clamp to body, 422 if no non-empty
   overlap / no body) — applied as dec-6 (§3.2).

No residual questions. Confirm the iter-1 P1 (dec-5) + the 3 P2s are closed.

## §7. Adjacent-file scan — files I have ALSO checked (clean / context only)

`src/polaris_v6/api/bundle.py`, `charts.py`, `followup.py`, `compare.py`,
`artifact_to_slice_chain.py`; `src/polaris_v6/queue/run_store.py`;
`src/polaris_v6/schemas/evidence_contract.py`, `run_status.py`;
`src/polaris_graph/audit_ir/loader.py`; `tests/v6/test_end_to_end_arch_001f.py` +
`tests/polaris_v6/api/test_artifact_to_slice_chain.py` (the
`_write_synthetic_artifact_dir` helper). `bundle.tar.gz` path + `memory.py` are out
of scope and untouched.

## §8. GREEN criteria

1. `live_run_adapter.py` exists; the 4 endpoints resolve a live completed `run_id`.
2. The I-rdy-007 §6 error matrix holds on each endpoint.
3. All 6 adapter decisions are implemented as §3.2 — incl. dec-5 (no non-T1/2/3
   tier ever 500s an endpoint) and dec-6 (span clamp).
4. Existing golden-fixture endpoint tests green; new adapter + live-path tests green.
5. `pytest tests/v6/ -q` green; import smoke clean.
6. Codex APPROVE on brief + diff.

## §9. Output schema (CLAUDE.md §8.3.9 — bind to this)

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
verdict_reasoning: <text>
```
Loose prose without the schema → resubmit.
