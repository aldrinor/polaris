# POLARIS Mission Status

**As of:** 2026-05-04
**Authority:** `polaris-controls/PLAN.md` (admin-only, signed)
**Deliverable:** Sep 6, 2026 — tracer demo to Carney's office

This document is an honest accounting of where the mission stands, what
agents have shipped, and what genuinely remains user-blocked. It is updated
when the agent finishes a slice or hits a halt condition. It is NOT
authoritative — `polaris-controls/PLAN.md` is. This is a status surface for
the user to read.

---

## 1. Slice progression vs PLAN.md

PLAN.md slice 0–5 with target windows:

| Slice | PLAN window | Substrate state | Demo state |
|---|---|---|---|
| 0 | Week 0 (May 4-10) | DONE — cage, archive cutover, golden tests pinned | n/a |
| 1 — Scope discovery + ambiguity | May 11-31 | DONE — `polaris_graph/scope/`, `/api/intake`, `/intake` page, 5 user-authored goldens in `polaris-controls/golden/slice_001/` | demoable: type clinical question → ScopeDecision card |
| 2 — Tiered retrieval | Jun 1-28 | DONE — `polaris_graph/retrieval2/`, `/api/retrieval`, `/retrieval` page, real Serper + Semantic Scholar fetcher | demoable with `SERPER_API_KEY` set |
| 3 — Generator + strict-verify | Jun 29 - Jul 26 | DONE — `polaris_graph/generator2/`, `/api/generation`, `/generation` page, deepseek-v4-pro adapter with 1-shot anti-leak | demoable with `OPENROUTER_API_KEY` set |
| 4 — Audit bundle GPG-signed | Jul 27 - Aug 16 | DONE — `polaris_graph/audit_bundle/`, `/api/audit-bundle`, GPG signer with detached ASCII-armored sig, download integrated into `/generation` | demoable with `POLARIS_GPG_KEY_ID` set |
| 5 — BEAT-BOTH benchmark + demo polish | Aug 17 - Sep 5 | DONE — `polaris_graph/benchmark/`, `/api/benchmark`, `/benchmark` page, `scripts/run_benchmark.py` CLI, home walkthrough nav, `docs/demo_runbook.md`, `scripts/seed_demo_benchmark.py`, `scripts/demo_smoke.py` | demoable with `POLARIS_BENCHMARK_RESULTS_DIR` pointing at seeded artifact |
| Demo | Sep 6 | n/a | scheduled |

**Calendar reality:** the slice substrate has all been shipped ahead of
calendar. PLAN.md windows are upper bounds for when each slice MUST be
demoable; shipping early is fine.

---

## 2. Sep 6 demo deliverable checklist

From PLAN.md §1 (Mission Statement):

- [x] Single domain (clinical research, baseline) — clinical_efficacy + clinical_safety scope classes only
- [x] End-to-end pipeline scope → ambiguity → retrieval → generator → audit → benchmark — all 5 slices wired through `polaris_v6.api.app`
- [x] Demo-able by a non-developer in a fresh browser — `web/app/page.tsx` four-step walkthrough; `docs/demo_runbook.md` walks the operator through env setup → boot → click-through
- [x] Audit bundle GPG-signed, verifiable — slice 004 emits `.tar.gz.asc`; verified externally via `gpg --verify`
- [x] BEAT-BOTH benchmark run vs ChatGPT-DR / Gemini-DR on at least 1 query — slice 005 CLI + `--skip-polaris` flag for re-scoring; one-query real demo via `scripts/run_benchmark.py` with all 3 envs set

---

## 3. Pre-demo smoke checks (no external cost)

```bash
# Stack health (no LLM/search cost)
PYTHONPATH=src python scripts/demo_smoke.py -v

# Engine tests (305 tests + slice runners)
PYTHONPATH=src python -m pytest tests/polaris_graph/ -q

# Frontend Playwright (requires `npx next start` on :3000)
cd web && npx playwright test
```

A green smoke does NOT certify content correctness — only structural health.
For content correctness during the demo, the operator must follow
`docs/demo_runbook.md` with keys set.

---

## 4. User-blocked / out-of-scope for agent

These items remain pending per task tracker and require user action; the
agent cannot resolve them without authorization:

| Task | Blocker | Owner |
|---|---|---|
| Vast.ai US dev cluster operational (0.3) | account + billing | user |
| DeepSeek V4 hardware Path A/B/C decision (0.6) | strategic call | user |
| SGLang vs vLLM bakeoff (0.7) | gated on 0.6 | user |
| OVH Canada BHS H200 verification (0.9 — HARD GATE) | invoice + hardware | user |
| Promote `.codex/slices/slice_00{2,3,4,5}/golden_drafts/*.json` → `polaris-controls/golden/slice_00{2,3,4,5}/` | admin write to controls repo | user |
| Carney reframe conversation (Sep 6 = tracer demo, not v1.0) | external coordination | user |

The agent does NOT block on these for shipping substrate; per
`feedback_dont_stop_on_picker_empty.md` and
`feedback_dont_stop_on_user_budget_block.md`, agent continues with
substrate that does not need cash, hardware, or admin-repo writes.

---

## 5. Repo state

- **Branch:** `polaris`
- **Cage:** `verify_cage.py` 33/33 last verified
- **Engine tests:** 305+ passing in `tests/polaris_graph/`
- **Slice goldens:** slice 001 (5 in controls), slices 002-005 (drafts in `.codex/slices/<id>/golden_drafts/` awaiting promotion)
- **PRs shipped this batch:** 74 (PRs #1-#74 across slices 001-005 + demo polish + smoke)

---

## 6. Update protocol

This file gets updated when:

- A slice closes (last PR merged)
- A halt condition fires (cost concern, primary-source conflict, scope decision)
- The user asks for a status snapshot
- The agent picks the next slice or PR sequence

The agent does NOT edit `PLAN.md`, `CHARTER.md`, or any file under
`polaris-controls/` — that authority is user-only per PLAN.md §11.
