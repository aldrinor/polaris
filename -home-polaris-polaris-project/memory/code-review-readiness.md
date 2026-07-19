---
name: code-review-readiness
description: "Telus code-review readiness initiative — plan v4 (codex-approved), Phase 0 done, box-3 GPU fix, deterministic oracle"
metadata: 
  node_type: memory
  type: project
  originSessionId: 21e87760-8436-4090-870d-99ef2121882e
---

Initiative (started 2026-07-18): make the deep-research pipeline pass an independent **Telus** code
review WITHOUT changing the RACE score or faithfulness. Plan **v4** is codex-approved after 4 review
rounds — at `polaris_project/CODE_REVIEW_READINESS_PLAN_v4.md`. Product rebranded **Deep Cove Research**
(GitHub repo renamed `aldrinor/polaris` → `aldrinor/deep-cove-research`); "Polaris" is now the internal
codename. Work lands on branch **`chore/review-readiness-phase0`** (~18 commits), never on protected `main`.

**Done (all codex-gated, on GitHub):** Phase 0-B (pyproject + report-only CI + SHA-pinned actions +
THIRD_PARTY_NOTICES + README); Phase 0-A baseline (secret-safe manifest, 694-var/352-PG config
inventory, test characterization — 16,501 tests, collection errors driven 23→11); real bug fixes
(`registry.py` import-time raise → thread-safe lazy; a `C:/POLARIS` hardcoded test path); and the
**deterministic regression oracle Layer 1** = `tests/oracle/cassette.py` (record/replay, codex-APPROVED,
12 tests) — the byte-identical arbiter every runtime change must pass.

**Box-3 GPU FIX (critical migration gap):** box 3's Blackwell GPU is `sm_120`; the migrated
`/opt/conda` torch 2.5.1+cu124 can't run it. Fix = a **clone** `/home/polaris/conda_cu128` with
`torch 2.9.1+cu128` (reranker+embeddings verified on GPU), cut over via symlink
**`/home/polaris/pipeline-env` → conda_cu128** (run the pipeline as `/home/polaris/pipeline-env/bin/python`;
rollback = retarget the symlink to `/opt/conda`). `/opt/conda` is root-owned/untouched. Box-3's newer
torch is NOT byte-identical to the A100 champion → treat champion as a *replication/re-baseline*, and
do refactor-equivalence *within* the cu128 env.

**Search "0 searches" alarm: RESOLVED** — codex-confirmed it was the degraded (GPU-broken) environment,
not a bug; the gap-detector + search path work (the `outline_agent.py:310` hypothesis was withdrawn).

**Remaining (multi-session, each runtime change needs the oracle + owner gate):** oracle Step 2 (wire
RecordProvider/ReplayProvider to the async LLM+retrieval boundaries + a small **paid** record run →
byte-identical replay); Phase 1 (923-key config → `settings.py`, characterization tests); Phase 2 (the
210 codex-validated renames in `polaris_project/NAME_RENAME_WORKLIST_validated.tsv` + wire the
checkpoint); Phase 3 (docs → required CI → the graph_v1/v2/v3 fork, riskiest, last). See also
[[research-planning-gate]].
