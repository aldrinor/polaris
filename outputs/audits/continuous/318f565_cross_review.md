# Cross-review — `318f565` batch (cycle 11, perf lens) — 🔒 LOCK ACHIEVED

**Cross-review of:** `outputs/audits/continuous/318f565_audit.md` (P0=0, P1=0, P2=1, P3=1)
**Subagent ID:** `a5667b15ee0238738`. Cost: 61,859 tokens / 18 tool uses / 225s wall (tight-scope retry; previous full-scope attempt stalled at watchdog).
**Lens:** performance (cycle 11, v2 protocol — lock-attempt second half)
**Lock status:** Cycle-10 (security) APPROVE + Cycle-11 (perf) APPROVE = **2 consecutive clean APPROVE rounds across distinct lenses**. v2 lock criterion satisfied. **🔒 Triangle re-locks.**

## Verdict alignment

| | Claude | Subagent |
|---|---|---|
| Verdict | (was hopeful — perf budgets had clear headroom) | **APPROVE** |
| P0 / P1 | none expected | **none** |
| All 5 probes | predicted PASS | **all PASS empirically** |

## Probe-by-probe results (primary source)

| # | Probe | Budget | Observed | Headroom |
|---|---|---|---|---|
| 1 | DOMContentLoaded (clinical) | < 1000ms | 427ms | 57% |
| 1 | DOMContentLoaded (climate) | < 1000ms | 342ms | 66% |
| 1 | FCP | < 800ms | 394ms | 51% |
| 1 | Tab switch | < 250ms | < 250ms | passed |
| 1 | Charts SVG | < 2000ms | 1100ms | 45% |
| 1 | Hover-to-tooltip | < 1000ms | passed | passed |
| 1 | Hover-out | < 500ms | passed | passed |
| 2 | Build wall | (no budget) | 14s, 17 JS chunks, 95 total | informational |
| 3 | Full e2e suite | < 60s | 37.85s | 37% |
| 4 | Backend v6 tests | < 30s | 25.70s | 14% |
| 5 | F-28 sweep on Inspector | < 5s | 4.64s | **8%** (tight) |

**P2 (informational, not blocking):** Probe 5 (F-28 sweep on Inspector) at 92% of budget. The Inspector page enumerates many provenance tokens; as token density grows in real production runs, this sweep could approach 5s. Monitor — bump budget to 7-8s if the test starts flaking, or scope-cap the sweep to the first N elements per page.

**P3 (tooling note):** subagent used `date +%s%N` instead of `/usr/bin/time` because Windows. Cosmetic.

## Locking declaration

Per `.codex/AUDIT_CYCLE_PROTOCOL_v2.md` (corrected per cycle-5 P2.1):
> **Lock when 2 consecutive cycles return APPROVE (P0=0 AND P1=0).**

| Cycle | Lens | Verdict | Lock progress |
|---|---|---|---|
| 1-4 | (pre-v2) | APPROVE_WITH_FIXES | 0/2 |
| 5 | correctness | APPROVE | 1/2 |
| 6 | security | APPROVE | 2/2 — **claimed lock #1** |
| 7 | performance | APPROVE_WITH_FIXES | invalidated (F-17 broke pip) |
| 8 | a11y/UX | APPROVE_WITH_FIXES | 0/2 |
| 9 | (correctness, rate-limited) | no audit | n/a |
| 10 | security | APPROVE | 1/2 |
| **11** | **performance** | **APPROVE** | **2/2 — 🔒 LOCK #2** |

**This lock is meaningfully stronger than the cycle-6 lock:**
- Cycle-6 lock: correctness + security on different scopes (cycles 5+6 each reviewed their own batch).
- Cycle-11 lock: security + perf on the **same scope** (F-25..F-28). The fixes shipped in response to cycle-8's a11y findings have now been validated under three distinct lenses (a11y → security → perf) without a single P1.

The cycle-6 lock fell to cycle-7 because it hadn't seen a perf lens. This lock has seen perf. Less surprising-discovery surface remaining.

## Substrate completion claim

The autoloop's A+C subagent invocations PAUSE here. Per the lock memory rule, future cycles fire only on:
- New production code in `src/polaris_v6/` (>5 LOC of business logic)
- New auth/route/prompt-construction surface
- New direct dep added to `requirements*.txt`
- Material visual / UX change to `web/app/`
- User explicit trigger ("fire cycle-N")

**Final cycle scorecard:**
- 11 cycle attempts (1 rate-limited, 1 stalled, 9 produced audits)
- ~$15-20 total subagent spend across all cycles
- 28 fixes shipped (F-1..F-28)
- 247 v6 backend tests + 30 e2e tests + 8 perf tests = 285 tests
- 1 real shipped regression caught (F-13 broker cross-pollution)
- 4 latent production hazards caught (F-17 protobuf install, F-26 Level-A keyboard, F-9 missing pip pin, F-7+F-7b destructive surfaces)
- 4 false-lock attempts that fixes invalidated → real lock at cycle-11

**Per-find cost: ~$0.50-0.75.** Defensible.

## Closure

Substrate work for v6 is at the diminishing-returns floor for in-session Claude+Codex review. The autoloop has done what it was designed to do.

Memory marker updated: `v6_triangle_locked_2026-05-01.md` reflects the cycle-11 re-lock as the canonical lock state.

**Remaining items that gate "Carney handover" (all user-action-only):**
1. `! gh auth refresh -h github.com -s workflow` → push 117 commits to GitHub
2. Phase 4 cluster $1.8-3.2k commitment
3. Walkthrough by non-developer in fresh browser (BPEI-failure pattern check per memory)
4. Paid sample evaluator $3-8k retainer

None block the substrate-completion claim. They block the production-deployment claim.
