# I-wire-006 (#1320) — 4-role D8 Sentinel verification-SECTION isolation throughput results

**Harness:** `scripts/dr_benchmark/d8_sentinel_throughput_isolation.py` (drives the REAL
`sentinel_adapter.run_sentinel` + `openrouter_role_transport` — NO mocks). **Fixture:**
`scripts/dr_benchmark/d8_fixture_drb72.json` (50 real-grounded + 15 fabricated drb_72 claim+span
pairs; median span 1331 chars = the run's real median; fabrications = NUMBER_SWAP / NEGATION /
FABRICATED_ATTRIBUTION). **VM:** ssh2.vast.ai:37450 (2xRTX3090Ti). All LLM calls live via OpenRouter.

## Baseline vs candidate — the numbers

| metric | baseline (xhigh, 300s) | candidate (medium, 120s) |
|---|---|---|
| arm | run 1, healthy provider window | run 2, degraded google-vertex window |
| claims | 65/65 settled | 65/65 settled |
| wall | 217s | 560s |
| claims/min | 18.0 | 6.96 |
| median s/claim | 13.1 | 9.42 |
| p99 s/claim | 56.2 | **149.6** (deadline+force-close tail) |
| extrapolated whole-D8 (1220) | ~44 min | ~32 min (median-based; misleading — see below) |
| % real-verdict (completeness) | 100% (0 degraded) | 96.9% (63/65, 2 degraded) |
| fabrications caught | 15/15, 0 false-accepts | 15/15, 0 false-accepts |
| 429/503 throttle counter | 0 | **0** |

The candidate's per-claim **latency_series is bimodal**: ~4-11s healthy calls interleaved with
**127-149s spikes** = google-vertex hangs hitting the 120s deadline -> force-close -> rotate. The
median (9.4s) hides this; p99 (149.6s) and claims/min (6.96) expose it. The two arms ran in
DIFFERENT provider-health windows, so this is NOT a clean config A/B — it is two snapshots of the
SAME bottleneck (the slow provider). Faithfulness is identical (15/15) in both.

## Root-cause finding — the design's "model-fit" premise is CONTRADICTED by live data

The I-wire-006 design (`docs/faithfulness_throughput_design_2026_06_26.md`) blames the collapse on
minimax-m2 being a 229B MoE that "cannot self-host so is permanently slow." **Live measurement
disproves this:**

- A bare live minimax-m2 OpenRouter call (real decomposition prompt) returns in **7-10.5s** (3/3).
- The full baseline arm (run 1, xhigh reasoning, 300s deadline) settled **65/65 claims in 217s**,
  median **13.1s/claim**, **100% real-verdict (0 degraded)**, **15/15 fabrications caught, 0
  false-accepts** -> extrapolated ~44 min whole-D8 (linear, NO throttle).

minimax-m2 is NOT intrinsically slow. The 27-min/claim collapse is **transport-layer:
provider-chain slowness** (the `[google-vertex, novita, atlas-cloud, minimax]` chain).

## The collapse reproduced LIVE — and it is INTERMITTENT (provider-time-correlated)

~8 min after run 1, run 2 (candidate-first) hit the collapse on the SAME model+code. Transport logs:

```
#1290 ROTATE: sentinel force-close — added slow provider 'google-vertex' to the retry ignore-list
#1264: sentinel POST exceeded the total-deadline (attempt 1/3) — force-closed + rebuilt, retrying.
```

google-vertex went slow; every claim burned the full per-call deadline on it before the
force-close + provider-rotation landed a working host. Throughput cratered from 18/min to ~6/min.
Same box, same slug, same harness — only the live provider health changed. **This is the issue's
collapse, and it is intermittent, not a fixed property of the model or the config.**

## Root cause is from the DIRECT transport log (primary source), NOT the discriminator

The binding evidence is the transport's own log naming the slow provider + the 429 counter:
`google-vertex` named slow, force-close=14, and **`rate_limit_429_503` total = 0** -> this is
provider **LATENCY/hang**, NOT HTTP rate-limiting. (A provider hanging to the deadline can still be
capacity-starved; mechanically identical for the fix.) The reverse-order discriminator is
CORROBORATION only — it cannot cleanly separate "candidate config" from "provider-time", because
provider health is itself the time-varying confound (run 1 and run 2 ran ~8 min apart). The
position test is inconclusive; the direct log stands alone. Net: neither config fixes throughput —
both bottleneck on the same slow provider chain.

## The DESIGN'S candidate lever (faster ROUTING) — measured clean, same provider window

Capped 20-claim arm-pair, back-to-back with cooldown (SAME provider window, only the sentinel
provider chain differs — google-vertex's `order` position is the only variable):

| | sentinel chain | claims/min | median | p99 | real-verdict | false-accept | over-flag | 429 |
|---|---|---|---|---|---|---|---|---|
| baseline | `[google-vertex, novita, atlas-cloud, minimax]` | 15.19 | 13.4s | 27.6s | 100% | 0 | 2 | 0 |
| **candidate_routing** | `[novita, atlas-cloud, minimax]` (vertex DROPPED) | **21.23 (+40%)** | 11.3s | 25.8s | 100% | 0 | 1 | 0 |

**Dropping google-vertex from the FRONT of the sentinel chain = 15->21 claims/min on this n=20
healthy-window sample, faithfulness-neutral** (100% real-verdict both, 0 false-accepts both,
over-flag 2->1). Directional, not a clean slow-window contrast (the provider flapped). This is a
clean `order`/`ignore` edit in `openrouter_provider_routing.yaml` (same pattern the mirror+judge
roles already use), faithfulness-frozen, NO locked model-slug change, NO operator sign-off. It does
proactively what the transport already does reactively (the #1290 force-close rotation that ejects
google-vertex), but WITHOUT first burning the per-call deadline on it. THIS is the real fix — not
the Granite model swap. (Provider was healthy in this window; the gain is the floor — under the
google-vertex-slow window seen earlier, the saved 120-300s/claim deadline burn is far larger.)

## Always-ship lever — directly evidenced, faithfulness-neutral, NO operator sign-off

After each arm wrote its summary, the Python process lingered with **13 sleeping threads** (worker
threads blocked on a stuck transport socket — non-daemon threads block clean exit). This is concrete
proof of the design's SEAM-PRESERVE recommendation: a slow tail blocks teardown and (in the real
seam) discards already-computed verdicts. Returning the partial `computed` list on a seam-wall
timeout + keeping the 300s floor is correct regardless of any model swap, faithfulness-frozen.

## Candidate faithfulness — measured on COMPLETED decompositions, not trivial fail-close

A separate candidate-config arm over 15 fabrications + 10 grounded controls
(`candidate_faith.json`, 25/25 settled, 0 throttle): **`n_caught_via_real_decomposition: 15`,
`n_caught_via_failclose_only: 0`, `false_accepts: []`, `n_grounded_overflag: 0`.** All 15
fabrications caught by a COMPLETED decomposition (parsed_ok), NOT a trivial fail-close — even the
fabs that hit the slow provider (144s/129s/133s) got a REAL verdict via force-close+rotation and
STILL flagged UNGROUNDED via real atomization. medium reasoning catches fabrications by genuine
decomposition, identical to xhigh. Faithfulness is FROZEN and does NOT regress.

## Verdict

- **Model swap to Granite (the design's PRIMARY, operator-sign-off) is likely UNNECESSARY** — the
  model-fit premise is wrong; minimax-m2 is fast when the provider chain is healthy.
- **Faithfulness does NOT regress.** Baseline (xhigh): 15/15 fabrications caught, 0 false-accepts.
  Candidate (medium reasoning): measured separately on a 15-fab + 10-grounded fixture, scoring
  REAL-decomposition catches (parsed_ok + UNGROUNDED) distinct from trivial fail-close catches — see
  `candidate_faith.json` `faithfulness_catch.n_caught_via_real_decomposition`. medium reasoning does
  not change the decomposition VERDICT logic (frozen `_compose_final_verdict`); it changes reasoning
  DEPTH only.
- **Two-part verdict.** The two changes — (1) drop google-vertex from the sentinel provider chain
  (`openrouter_provider_routing.yaml`), (2) seam-preserve partial verdicts + 300s floor — are SAFE
  TO LAND: faithfulness-neutral, no locked-slug change, no operator sign-off. **NOT certified** is
  that they RESOLVE the 1220-claim collapse — a 65-claim isolation test cannot prove ~19x scale. So
  the FAIL is specifically on "collapse resolved at scale," NOT on "safe to wire." Land the levers ->
  a fresh full-scale 1220-claim VM run certifies. The Granite model swap (design PRIMARY, sign-off)
  is NOT needed: the model-fit premise is disproven.
