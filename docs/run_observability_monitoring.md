# Live-run observability monitoring (I-obs-001 #1141)

How to monitor a Gate-B benchmark run in real time and catch the three silent failure modes the drb_72 campaign (#1100) taught us, using the observability landed in I-obs-001. This is reusable for every live run, not just Q1.

## Artifacts the run emits

| Artifact | Flag | Contents |
|---|---|---|
| `state/run_status.json` (cross-query mirror) + `<run_dir>/run_status.json` | `PG_RUN_STATUS_HEARTBEAT` (default ON) | one JSON object refreshed at every stage transition: `query_index/total`, `stage`, `elapsed_s`, `running_cost_usd`, `budget_cap_usd`, `sources_kept`, `sections_done/total`, `claims_verified/total`, `last_update_utc` |
| `<run_dir>/retrieval_trace.jsonl` | always (Gate-B) | JSONL appended live during retrieval: `{kind:query, backend, query, return_count, urls}`, `{kind:kept, url, backend}`, `{kind:drop, url, reason}` |
| `<run_dir>/llm_io/<call_id>.json` | `PG_CAPTURE_RAW_LLM_IO` (default OFF) | one file per LLM call across all 4 egress paths (generator + Mirror/Sentinel/Judge + entailment/NLI judges): exact final request body + raw response |

Stage progression: `started → scope_gate_passed → retrieval_done → generation_done → four_role_started → four_role_done → manifest_written → <terminal status>`.

## Health one-liners (run every ~15 min)

Heartbeat summary:
```bash
python -c "import json; d=json.load(open('state/run_status.json')); print(f\"q{d['query_index']}/{d['query_total']} stage={d['stage']} kept={d['sources_kept']} claims={d['claims_verified']}/{d['claims_total']} cost=\${d['running_cost_usd']}/{d['budget_cap_usd']} elapsed={d['elapsed_s']}s\")"
```

Retrieval health:
```bash
python -c "import json,collections,glob; f=sorted(glob.glob('outputs/**/retrieval_trace.jsonl',recursive=True))[-1]; recs=[json.loads(l) for l in open(f)]; q=[r for r in recs if r['kind']=='query']; print('fetched_urls', sum(r['return_count'] for r in q), '| kept', sum(1 for r in recs if r['kind']=='kept'), '| drops', dict(collections.Counter(r['reason'] for r in recs if r['kind']=='drop')))"
```

## Failure-mode watch (abort early instead of burning the full budget)

| Failure mode | Signal | Healthy | RED FLAG → action |
|---|---|---|---|
| **Silent URL throttle** | trace `fetched_urls` + heartbeat `sources_kept` (`null` until `retrieval_done`, then the real count; `0` on the no-source abort) | fetched approaches `PG_SWEEP_FETCH_CAP` (1000); kept in tens-to-hundreds | fetched « ~200 at `retrieval_done`, or `sources_kept` ≤ ~40 → **ABORT**; a `PG_SWEEP_*` knob isn't taking effect (the #1098 0.286 baseline / the cap the operator is furious about) |
| **Dead-route 404 collapse** (drb_72 root cause) | `PG_BEHAVIORAL_CANARY` (pre-sweep, fail-closed) + trace `drops` by `reason` + heartbeat `claims_total` | canary passes; drops dominated by the HEALTHY reasons `offtopic` / `rerank_not_selected`; `claims_total` > 0 at `generation_done` | canary fail-closed = GOOD (no spend wasted); else a storm of `drop` with `reason=fetch_failed` (dead route / 404 / connection error) or `reason=content_starved` (empty 200 body), or `kept ≈ 0` / `claims_total ≈ 0` → **ABORT**. NOTE: the four real `drop.reason` strings are `offtopic`, `rerank_not_selected` (both normal filtering), `fetch_failed`, `content_starved` — there is no literal `"404"` reason, so watch `fetch_failed`/`content_starved` ratios, not the string "404" |
| **Verifier degradation** (#1071) | terminal `stage` + `claims_verified/total` | `stage=success`, `claims_verified` > 0 | terminal `stage=abort_verifier_degraded` → judge-error-rate gate FIRED (correct fail-closed; NOT a faithfulness leak). Inspect judge errors via `PG_CAPTURE_RAW_LLM_IO=1`; do NOT relax the gate |
| **Budget** | `running_cost_usd` vs `budget_cap_usd` | climbs steadily, < 1.0 | approaching cap → `BudgetExceededError` imminent (expected) |

Operator is BLIND: report each check as ONE spoken line, e.g. "query 1, retrieval_done, 740 fetched, 180 kept, $4 of $25, healthy" or "RED FLAG: only 38 kept — recommend abort."

## Hard caveat

A green run shape (`status: success`, claims_verified > 0) is necessary but NOT sufficient. The faithfulness gates can pass content that is still wrong (the campaign lesson: gates green ≠ faithful). The real acceptance is the §-1.1 line-by-line audit of `report.md` claim-by-claim against the cited span text, run by both Claude and Codex, then compared to the in-repo Q72 ChatGPT/Gemini outputs.
