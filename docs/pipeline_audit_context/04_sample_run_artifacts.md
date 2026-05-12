# Sample run artifacts (real, from outputs/)

Where to find representative pipeline A runs across each exit status.

## `status=abort_corpus_inadequate` (the positive-refusal case)

**Path**: `outputs/honest_sweep_r6_validation/tech/tech_rag_architectures_2024/`

- `manifest.json` — `status=abort_corpus_inadequate`, `cost_usd=0`
- `adequacy` block shows 3 critical threshold fails
  (`t1_count=0 < 1`, `t1_plus_t2=0 < 2`, `t1_plus_t2_plus_t3=0 < 2`)
- No LLM call was made — generator + evaluator never invoked

This is the "well-built" behavior Codex confirmed in round 1.

## `status=abort_no_verified_sections` (not yet observed in live sweeps)

No live example in `outputs/honest_sweep_r6_validation/`. The test suite
(`tests/polaris_graph/test_b3_no_verified_sections.py`) pins the
expected artifact shape.

## `status=success` (full run with verified prose)

**Path**: `outputs/honest_sweep_r6_validation/clinical/clinical_afib_anticoagulation/`

- `manifest.json` — `status=success`
- `report.md` — actual findings + bibliography
- `bibliography.json` — deduped cross-section
- Multiple sections generated + verified

## Cross-comparison

| Slug | Status | Cost | Sections | Verified | Notes |
|---|---|---|---|---|---|
| clinical_afib_anticoagulation | success | ~$1 | 3 | yes | typical success |
| tech_rag_architectures_2024 | abort_corpus_inadequate | $0 | 0 | n/a | abort before generation |
| policy_fda_ai_devices | success? | ? | ? | ? | check manifest |
| dd_novo_nordisk_obesity_position | success? | ? | ? | ? | check manifest |

## What to look for when reviewing run artifacts

- **Cost accounting**: does `manifest.cost_usd` match the sum of
  per-call costs in `logs/pg_cost_ledger.jsonl` for this run?
- **Sentence budget**: verified / (verified + dropped) ratio. If <40%
  per section, regeneration should have kicked in.
- **Bibliography coverage**: does every numbered citation in
  `report.md` appear in `bibliography.json`? Any dangling `[42]` that
  points to nothing?
- **Timestamp consistency**: does `protocol.json.timestamp` predate
  `manifest.json.timestamp`? Any out-of-order entries?
- **Deterministic output**: if the same corpus + same seed + same
  model are re-run, does the generated report match byte-for-byte?
  (Suspected no — LLM sampling is typically non-deterministic.)

## Rounds 1-5 audit record

**Path**: `outputs/codex_findings/round_{1,2,3,4,5}/`

Each round has:
- `findings.md` — Codex's verdict + blockers + mediums + recommendations
- `claude_response.md` — Claude's response + fix descriptions + new tests

Key round summaries:
- Round 1: 5 blockers (B-1..B-5) found
- Round 2: re-raised B-1 default + B-5 isolate controls + B-5 homoglyph overstate
- Round 3: architectural rewrite of sanitizer (view + index projection)
- Round 4: NFKD + combining-mark strip for diacritic homoglyphs
- Round 5: READY verdict — all prior invariants verified, no new blockers

Full loop state: `archive/2026-05-11-root-hygiene/codex_historical/loop_state.json` (decommissioned 2026-05-11 by I-hygiene-001 GH#432; preserved in archive).
