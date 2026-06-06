# FX-14 (#1129) grounding — V29/M44 custody telemetry not_applicable marker (path B)

Status: GROUNDED + 2 real-artifact corrections applied. Author next wake (fresh context — this is the
only faithfulness-adjacent remaining item; even path B writes provenance-related markers that must be
exactly right). Decision: **path B** (telemetry-only marker), brief path A to Codex.

## The bug
`v29_primary_custody.json=[]` and `m44_primary_citation_telemetry.json={injection_log:[],
validator_violations:[]}` even when primary-trial seeds were present. The M-44/M-52/V29 custody+
INJECTION block is gated on `if primary_trial_anchors:` (`multi_section_generator.py:4610`); in planner
ON-mode `primary_trial_anchors` (`_primary_anchors`, from `get_primary_trial_anchors_for_slug` at
`run_honest_sweep_r3.py:3351`) is empty, so the block is skipped and the telemetry is written silently
empty at the write sites `run_honest_sweep_r3.py:4331-4342` (m44) and `:4376-4380` (v29).

## Decision: path B (faithfulness-safe), path A → Codex
- (A) re-derive anchors so the block fires = re-enables M-52 evidence_pool pulls + M-44 outline
  injection in a dormant lane → MUTATES the evidence reaching the generator → faithfulness-adjacent,
  REJECTED as default. Brief to Codex as the alternative.
- (B) when the log is empty BUT primary-trial seeds existed, write
  `{status:'not_applicable_planner_lane', reason, primary_trial_doi_seed_rows:N,
  primary_trial_anchors_configured:bool}` instead of silent []/{}. Telemetry-only, ZERO generator change.

## CORRECTION 1 — detection signal is evidence_pool, NOT retrieval_trace
`retrieval_trace.jsonl` rows are per-backend-call: keys = `['kind','backend','query','return_count',
'urls']` — they carry NO `query_origin`. My first plan (count primary-seed rows from retrieval_trace)
was WRONG. The correct signal: the in-memory `evidence` list (== `evidence_pool.json` when dumped) —
each row has a `query_origin` field. Count rows with `query_origin == 'primary_trial_doi_seed'`.
ACTION for authoring: confirm the exact `evidence` variable name in scope at `run_honest_sweep_r3.py`
~4331 (the list passed to multi_section_generate) and that its rows carry `query_origin`.

## CORRECTION 2 — the forensic's "16+ rows" is stale; honest held count is 2
Held drb_72 `evidence_pool.json` (21 rows) origin tally: `primary_trial_doi_seed` = **2** (not 16+).
The forensic's "16+" predates FX-15a, which was MISLABELING agentic seeds as primary_trial_doi. FX-15a
(verified) fixed that, so the HONEST primary-seed count on this run is 2. This is exactly why FX-14
depends on FX-15a, and why §-1.1 on the real artifact matters (the forensic number was wrong). On a
fresh post-FX-15a run the marker fires when there is >=1 real primary_trial_doi_seed row but custody
is empty.

## Fix shape (path B)
- `run_honest_sweep_r3.py` ~4331/4377: compute `n_primary = sum(1 for ev in <evidence> if
  ev.get('query_origin')=='primary_trial_doi_seed')`. When `n_primary>0` AND the m44 injection_log /
  v29 custody_log are empty, write the marker object into BOTH files instead of silent []/{}.
  Flag-gated `PG_CUSTODY_LANE_MARKER` (default OFF → byte-identical; force-ON + preflight floor-flag in
  the Gate-B slate `run_gate_b.py`).
- multi_section_generator.py UNCHANGED.

## Acceptance
- Offline smoke: synthetic evidence list w/ 2 primary_trial_doi_seed rows + empty custody → marker
  written with `primary_trial_doi_seed_rows:2`; 0 such rows → empty unchanged; flag OFF → byte-identical
  (no marker even with primary rows).
- §-1.1 on held drb_72: with the flag ON, the marker would fire with `primary_trial_doi_seed_rows:2`
  (the corrected honest count) — NEVER silent [] when seeds exist.
- Codex diff-gate APPROVE + confirm path B loses no real custody signal vs path A.

## Then: FX-12 (P3, last) — eval_gate judge_skipped_d8_binding reason (run_honest_sweep_r3.py callsite
:4961 + evaluator_gate.py). After FX-14, this closes the campaign ledger.
