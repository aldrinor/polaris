# I-deepfix-001 RELAUNCH GATE — every issue fixed→gated→tested→preflighted before ANY paid relaunch

**OVERNIGHT (operator asleep, 2026-07-02):** authorized — after preflight full-green, provision 5 dual-GPU boxes (1 question each), launch, monitor forensically, deliver a §-1.1 beat-both report; iterate if deficient. Authoritative plan: **`OVERNIGHT_RUN_PLAN.md`** (wall pin, survives compaction).

**STATUS 2026-07-02:** 32/32 committed + Codex-gated. 0 conflict markers. Frozen engine untouched except U29. Preflight in progress (PREFLIGHT_MATRIX.md).

**BINDING (operator 2026-07-01):** NO paid relaunch until EVERY row below is `DONE` (fixed + Codex-gated + test + preflight) OR `LIVE-CANARY` (offline fix + a fail-loud canary that ABORTS the run if the effect does not fire). Nothing skipped. This overrides the earlier "8 now, 20 later" deferral.

Legend: **DONE** = fixed+gated+committed. **GATE** = applied to tree, Codex-gate + commit pending. **BUILD** = fix not yet written (offline-tractable). **RESEARCH** = needs GitHub/deep research first. **LIVE-CANARY** = only provable on the live run → offline fix + fail-loud abort canary. **ACCEPTED** = intentional, operator-confirmed (not a bug).

## P0 — crashes
| # | issue | state | fix / canary |
|---|---|---|---|
| U1 | mineru pdfium SIGSEGV | **DONE** | lock all backends; committed, Codex APPROVE |
| U2 | CUBLAS GPU-OOM | **DONE** | mineru→card1 + chunk-caps (env + committed) |

## P1 — SOTA blockers
| # | issue | state | fix / canary |
|---|---|---|---|
| U3 | generator emits no provenance tokens → empty safety sections | **GATE** | provenance_repair in LLM else-branch |
| U4 | consolidation keying → 0 corroboration | **GATE** | keystone qual-atom union + chrome guard |
| U5 | verbatim span-dump, synthesis disabled | **LIVE-CANARY** | unlocked by U4; canary: composition must be synthesized (multi-cited sentence >0), abort if span-dump |
| U6 | chrome glued + canary blind | **GATE** | chrome_canary_unblind containment rules |
| U7 | mineru not installed on hosts | **DONE** | mineru 2.5.4 + vLLM server up (proven drb_76) |
| U8 | mineru semaphore wrong event loop → degrade | **BUILD (ready — research-2 traced) + LIVE-CANARY** | reset cached HttpVlmClient._aio_client_sem to a fresh Semaphore(1) before each do_parse (http-client path, under the existing GPU lock) so it re-binds to this call's asyncio.run loop; offline-testable; KEEP the "GPU VLM extracted N chars" abort canary as belt |
| U9 | off-topic corpus contamination | **GATE(headline) + BUILD(corpus topical floor)** | headline relevance-weighted done; corpus-level topical relevance still to build |
| U10 | tier mis-rates both ways | **GATE(venue) + BUILD(scam/commercial demote)** | venue exemption done; retracted/commercial demote still to build |
| U11 | clinical T1/T2 starved (retrieval) | **RESEARCH** | upstream retrieval surfacing high-tier |
| U12 | W5 near-binary weight | **GATE** | w5 graded monotone + chunk max-pool |
| U13 | span-grounded but MISREPRESENTED headline (poultry 99.4% as clinical) | **BUILD** | subject/unit preservation on promoted claims |
| U14 | journal-article classifier 100% broken | **GATE** | journal_genre_stamp |
| U15 | wall-clock discards rendered report | **GATE** | wallclock_guard + raise wall |
| U16 | entailment-judge network instability (429/DNS) | **RESEARCH** | judge provider-count (kimi-k2.6 21 providers) + retry/backoff |

## P2
| # | issue | state | fix |
|---|---|---|---|
| U17 | duplicate sections (CWF ≈ Evidence base) | **BUILD** | #1335 repetition |
| U18 | CWF corroboration render unusable | **BUILD** | header prose (I-wire-014 FIX-A class) |
| U19 | docling fallback never runs docling | **BUILD** | fix bytes>0 gate |
| U20 | junk spans counted as evidence | **BUILD** | extend junk screen beyond YouTube |
| U21 | T1 sources fetch-fail retained at 0 weight | **BUILD** | fetch retry/repair |
| U22 | CRAG adequacy no-op | **BUILD** | wire corrective loop iters |
| U23 | completeness gate all-non-applicable | **BUILD** | intervention recognizer |
| U24 | numeric-citation hygiene (~72% decimals uncited) | **BUILD** | PT11 gate enforce not advisory |
| U25 | OpenAlex 0 candidates (masked) | **RESEARCH** | OpenAlex query/params |
| U26 | green scorecard masks deficiencies | **BUILD** | scorecard honesty |

## P3
| # | issue | state | fix |
|---|---|---|---|
| U27 | quantified trade-off silent no-op | **RESEARCH** | spec returned |
| U28 | contradiction detector noise | **BUILD** | rel-diff/stopword guards |
| U29 | verify span-imprecision leniency | **BUILD (faithfulness-adjacent, careful+gate)** | narrow-span contradiction must not pass on wider entail |
| U30 | two-family safeguard disabled | **ACCEPTED (operator override PG_PERMIT)** | operator to confirm keep/restore — NOT a silent fix |
| U31 | fetch fidelity (25000-char truncation) | **BUILD** | raise/repair truncation |
| U32 | monitoring miscounts mineru firing | **DONE** | monitor counts real "GPU VLM extracted N chars" |

## Preflight gate before relaunch (all must pass)
1. Full offline test suite green (no new regressions).
2. Every GATE/BUILD fix Codex-APPROVE'd + committed.
3. Offline smoke (single sentence/section) runs clean.
4. Fail-loud canaries armed for LIVE-CANARY rows (U5 synthesis-fires, U8 mineru-fires) — run ABORTS if they don't fire.
5. `git log` shows every fix; docs + GitHub #1344 updated.
