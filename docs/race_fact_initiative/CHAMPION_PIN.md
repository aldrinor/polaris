# V30-on / task-72 CHAMPION — state pin (re-baseline in progress)

- branch: fix/race-batch1-evidence-substrate
- HEAD commit: 028ea1f06b75a7880f0fd27420843f1d069cf34c
- WIP snapshot (git stash create, full worktree incl. junk-gate rename): 96572b20dd13146ebbad054ade22f6b0cda05870
- launcher: scripts/dr_benchmark/run_gate_b.py --only drb_72_ai_labor (V30 forced ON)
- lineage: PG_BENCHMARK_QUESTION_LINEAGE=legacy_race_task (answers legacy task-72; scored --task-id 72)
- RACE judge (pinned for the WHOLE ladder): openai/gpt-5.5 (via OpenRouter)
- retrieval env: Serper + Jina (no S2_API_KEY — consistent across all draws; frozen corpus from draw 1)
- forensic: worktree WIP audited SAFE (docs/race_fact_initiative/wip_forensic_{sol,fable}_verdict.md); old raw-A launchers quarantined
- protocol: draw 1 fresh (establishes corpus_snapshot); draws 2-3 --resume from a copy of draw-1 corpus; score each IN-RUN-DIR
