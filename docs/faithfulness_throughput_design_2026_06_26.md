# Faithfulness 4-role D8 verify THROUGHPUT design — the single best solution for OUR situation

**GitHub:** I-wire-006 (#1320), umbrella I-wire-001. **Mode:** DESIGN ONLY (no pipeline run, no source edit in this pass).
**Date:** 2026-06-26. **Branch:** bot/I-wire-001-integration.
**Constraint:** make the 4-role D8 verify settle ALL ~1,220 claims FAST + COMPLETELY while the faithfulness DECISION logic stays FROZEN (I-faith-001 incumbent holds). A slow/missing role MUST stay fail-CLOSED (UNSUPPORTED, never a false GROUNDED/VERIFIED). This is the throughput/transport layer ONLY.

**Inputs synthesized:** the codebase review (`state/beatboth_campaign/D8_TRANSPORT_DESIGN.md` = the I-wire-004 reliability fixes; `openrouter_role_transport.py:478-535,1517-1588`; `sweep_integration.py:522-660`; `config/serving/verifier_roles.yaml:65-95`; `config/settings/openrouter_provider_routing.yaml:56-60`; `config/architecture/polaris_runtime_lock.yaml:83-138`; `outputs/audits/I-run11-004/claude_audit.md`) + the external research (`docs/verify_models_landscape_2026.md`).

---

## 0. The one-paragraph answer

The throughput collapse (2 of ~1,220 claims settled in 54 min) is NOT a deadline-tuning problem — it is a **model-fit** problem. The locked Sentinel **minimax/minimax-m2 is a ~229B-param MoE** (`verifier_roles.yaml:80-83`: bf16 ~458GB, needs an 8x80GB box). It does NOT fit the campaign VM's 2xRTX3090Ti (~48GB), so it is **permanently forced onto the OpenRouter provider chain `[google-vertex, novita, atlas-cloud, minimax]`** — every one of which is slow/NULL-uptime — and each claim burns the per-call deadline across the whole chain before degrading (~27 min/claim). No deadline value fixes this: a 30-45s wall (the issue's sub-lever) force-closes HEALTHY multi-minute decomposition calls into UNGROUNDED -> UNSUPPORTED = the drb_72-class collapse (`openrouter_role_transport.py:483-486`: "faithfulness-safe yet mission-useless"), and seam-preserve alone yields "2 settled + 1,218 fail-closed" = complete-and-safe but coverage ~= 0 = useless. **The durable fix is to swap the Sentinel to a model that FITS the VM and self-hosts (no slow external chain, no trickle-hang, no 429), chosen by a measured isolation bake-off + re-certification — NOT to keep tuning a model that can never run on our box.** Two levers ship in parallel: (P) the model swap (lock change, operator sign-off) and (A) an always-ship seam-preserve + 300s floor (no sign-off, lever-independent).

---

## 1. Root cause — verified, not assumed

| Fact | Evidence |
|---|---|
| Sentinel = minimax/minimax-m2, ~229B MoE, bf16 ~458GB, needs 8x80GB | `verifier_roles.yaml:80-87`; lock `:83-100` |
| Campaign VM = 2xRTX3090Ti ~48GB; GLM-5.2 already REMOTE via OpenRouter | MEMORY 14-winners pin 2026-06-24 |
| -> Sentinel CANNOT self-host on the box; forced onto OpenRouter chain | `verifier_roles.yaml:84` (`serving_route: vast_self_host` is aspirational/8xH100-PENDING); benchmark routes via OpenRouter |
| The chain `[google-vertex, novita, atlas-cloud, minimax]` is slow / NULL-uptime | `openrouter_provider_routing.yaml:56-60`; issue #1320 |
| Each claim burns the deadline across every provider then degrades -> ~27 min/claim -> collapse | issue #1320; I-wire-004 rotation made each force-close cheaper but did NOT raise throughput |
| Healthy minimax decomposition is "seconds-to-MINUTES"; NO latency samples were ever persisted | `openrouter_role_transport.py:482,489-491` |
| The 30-45s deadline sub-lever is a TRAP | `openrouter_role_transport.py:483-486` (a too-tight wall mass-over-drops HEALTHY calls = drb_72 collapse) |

**Throughput math (the discriminator, input UNMEASURED):** ~1,220 claims / `PG_FOUR_ROLE_CLAIM_WORKERS` (default 6) x (s/claim). At full health "minutes" -> 1220/6 x ~2.5 min ~= 8 h *even when nothing hangs* — so the MODEL latency, not the wall, is the ceiling. Because no s/claim sample exists (`:489-491`), **the lever must be picked by MEASUREMENT, not assertion** (the I-faith-001 lesson: "benchmarking beat assuming new=better").

---

## 2. The levers, weighed

| Lever | Speed | Faithfulness quality | Sovereignty | Sign-off | Effort |
|---|---|---|---|---|---|
| **L0: shorter per-call deadline (30-45s)** | fake-fast | **REGRESSES** (mass over-drop of healthy calls = drb_72 collapse) | n/a | none | trivial | **REJECT** — disproven by our own code `:483-486`. |
| **L1: keep minimax + fail-fast + route-to-fastest-host + seam-wall-preserve (no lock change)** | bounded by the SLOWEST that minimax serves on; cannot beat the model's own s/claim ceiling on a chain of slow hosts | unchanged (incumbent) | unchanged | none | low | Real but a CEILING — minimax stays off-box; "route to fastest host" still routes to a slow host. |
| **L2 (PRIMARY): swap Sentinel to a fast VM-self-hostable distinct-family sovereign model, bake-off + re-cert** | self-hosted on the box -> no external chain, no trickle-hang, no 429; s/claim measured + bounded | re-certified vs the 56-item fixture BEFORE adopt (0 false-accepts gate) | open-weight self-hostable on OUR box = STRONGER sovereignty than the current remote-only minimax | **YES** (lock slug mutation) | medium | Durable. |
| **A (ALWAYS-SHIP, lever-independent): seam-preserve partial verdicts + keep 300s floor** | turns a tail-hang from "discard thousands" into "keep all settled" | fail-closed for un-settled claims | n/a | **none** | low | Ships regardless of L1/L2. |

**Why L2 over L1:** L1 cannot beat physics — minimax-m2 is a 229B MoE that will never fit 2x3090Ti, so it is structurally remote-only and its throughput is hostage to whichever slow OpenRouter host answers. L1 makes each failure cheaper; it does not make the model fast. L2 removes the off-box dependency entirely: a model that self-hosts on the box has no provider chain to traverse, no trickle-hang class, no 429, and a measured local s/claim we control via `PG_FOUR_ROLE_CLAIM_WORKERS`.

---

## 3. RECOMMENDATION

### PRIMARY (durable, needs operator sign-off): swap the Sentinel to a fast, VM-self-hostable, distinct-family SOVEREIGN model — chosen by a measured isolation bake-off + re-certification.

**Lead candidate: IBM Granite Guardian 3.3-8B** (Apache-2.0, family=granite, distinct from glm/qwen; `verify_models_landscape_2026.md` Lane-B lead; #3 on LLM-AggreFact, hybrid-thinking groundedness JUDGE that preserves the decompose+span-coverage Sentinel contract). **8B fits the 2x3090Ti box self-hosted** — the exact property minimax-m2 lacks.

**HONESTY — address head-on (advisor-flagged):** the lock comment says "broken Granite Guardian -> CERTIFIED MiniMax-M2" (I-run11-004). The bake-off (`outputs/audits/I-run11-004/claude_audit.md`) chose minimax on a **faithfulness/decomposition-contract** pass (0/28 false-accepts), and the operator directive then was "**strongest latest frontier LLMs, NO encoders**" — the LettuceDetect/FactCG **encoder** class was **explicitly abandoned per operator**. So: (a) the I-run11-004 brief must be read to confirm whether Granite 4.1 failed on *serving/loading* (fixable by self-serving 3.3-8B) vs *faithfulness contract* (a real disqualifier) BEFORE re-recommending it — do not blind-re-pick a rejected model; (b) the encoder Lane-A models in the research doc (FactCG-0.4B, LettuceDetect) are **operator-rejected for the Sentinel slot** and are NOT primary candidates here (they remain a possible local FIRST-PASS corroborator beside an LLM Sentinel, never the sole Sentinel, only if a bake-off shows they re-certify — almost certainly they do not on decomposition).

**Candidates to ISOLATION-TEST (LLM decomposition Sentinels; distinct family; fit 2x3090Ti or a small VM):**
1. **IBM Granite Guardian 3.3-8B** (Apache-2.0, granite) — lead; self-hosts on the box.
2. **Patronus Lynx-8B** (Llama-3 community license — VERIFY field-of-use for clinical/commercial before adopt; RAG-hallucination judge, clinical-adjacent training).
3. **mistral-large-2512** (already in the I-run11-004 certify cache as a distinct-family contender) — re-measure latency + re-cert; larger, may not fit the box (servability check).
4. **minimax/minimax-m2 (CONTROL arm)** — measure its real s/claim on the OpenRouter chain so the swap is decided on data, not assertion. If minimax wins on a faster host AND its s/claim is sane, the fallback (L1) holds.

The bake-off MEASURES median + p99 s/claim per candidate and re-runs the certification fixture; the winner must pass BOTH the throughput bound AND the 0-false-accept faithfulness gate. No model is crowned on a vendor headline.

### ALWAYS-SHIP (no sign-off, independent of which model wins): seam-preserve partial verdicts + keep the 300s floor.

On a seam-wall timeout / propagated fault, RETURN the partial `computed` verdicts already settled (the in-memory `computed` list at `sweep_integration.py:561` — NOT `four_role_compute_progress.json`, which is only `{done,total}`; correct the issue's imprecision), instead of `cancel_futures=True` + raise discarding everything (`:585-591`). Un-settled claims are scored fail-CLOSED (UNSUPPORTED / uncovered), NEVER VERIFIED. Keep the 300s Sentinel floor (`:493-494`) — do NOT drop to 30-45s. This caps the blast radius of any slow tail and is correct regardless of the model swap.

### FALLBACK (if no candidate re-certifies, OR minimax wins the bake-off): keep minimax.

Keep minimax-m2 + crank `PG_FOUR_ROLE_CLAIM_WORKERS` **only if self-hosted** (cranking workers against the slow OpenRouter chain just multiplies stuck calls + 429s — net-negative) + keep the 300s floor + the always-ship seam-preserve. Honestly slower-but-complete; acceptable only if the bake-off proves no faster sovereign model re-certifies.

---

## 4. Acceptance metrics (isolation-test the Sentinel SECTION only; fixed claim set; on the VM, NOT the full pipeline)

**Throughput:** median + p99 s/claim per candidate; whole-D8 wall-clock extrapolated for ~1,220 claims at `PG_FOUR_ROLE_CLAIM_WORKERS`. **Sane bound to BEAT: < 60 min total D8 wall** for ~1,220 claims (vs the 54-min/2-claim collapse) — i.e. median s/claim x 1220 / workers < 3600 s.

**Completeness:** settled count == claim count; coverage computed over ALL claims; ZERO claims lost to a seam teardown; the seam returns the partial `computed` list, NEVER `{}`. `final_verdicts > 0` and reflects real adjudication, not force-close churn.

**Faithfulness-catch (frozen, the hard gate):** re-run the I-run11-004 56-item fixture (28 grounded + 28 fabricated across NUMBER_SWAP / ENTITY_SWAP / NEGATION / FABRICATED_ATTRIBUTION / SCOPE_INFLATION). Require **0 false-accepts on all 28 fabrications** + over-flag <= ~0.107 (the minimax baseline). A missing/slow role stays fail-CLOSED (UNSUPPORTED). `_compose_final_verdict` byte-unchanged. Any candidate that regresses the fabrication-catch is auto-REJECT (clinical §-1.1: a fabrication surviving the detector is lethal).

**Wiring (the §-1.4 behavioral gate):** the chosen change must FIRE in a real run — claims settle fast in the rendered output, not green-tests-only.

---

## 5. What needs operator sign-off

1. **Lock mutation — Sentinel `model_slug`** (`polaris_runtime_lock.yaml:90`) per the lock's mutation policy (`:9-13`): a Codex APPROVE on a brief naming the superseding decision doc + the operator commits the change (Claude has no signing key). Re-pin `docs/canonical_pin.txt` to the new lock SHA. Attach the re-certification artifact (0/28 false-accepts on the new model).
2. **Sovereignty confirmation:** confirm the new slug satisfies `feedback_sovereignty_threat_model` — open-weight, self-hostable on OUR box, distinct family from glm (gen+mirror) and qwen (judge), no closed-source fallback. (Granite = Apache-2.0, IBM-US-origin open weights — confirm IBM-US-origin is acceptable under the sovereignty definition, as the prior lock already accepted it as the Sentinel pick.)
3. **License field-of-use** for any Llama-3-licensed candidate (Patronus Lynx) before adopt.
4. **VM-fit confirmation:** the chosen model serves on the 2xRTX3090Ti box (or the procured GPU) — the property minimax-m2 lacks.

**No sign-off needed** for the always-ship seam-preserve + 300s-floor (reliability/transport only, faithfulness-frozen, default-safe).

---

## 6. Out of scope (named so a reviewer sees they were checked)

- **Problem-3 (quantified `spec_produced=False`)** from issue #1320 is NOT throughput/completeness/faithfulness-frozen — its root cause is unknown (the reasoning_max_tokens=8192 + junk-filter fix did not resolve it on the VM). Treat as a SEPARATE root-cause pass; do not force a throughput design onto it.
- **The faithfulness ENGINE** (strict_verify / NLI / 4-role verdict logic / coverage / release_policy / `_compose_final_verdict`) — FROZEN, never touched. Every change here is model-slug, transport client lifecycle, seam-preserve, or token budget.
- **Lane-A encoder first-pass** (FactCG / LettuceDetect) for check (f) entailment — a separate `verify_models_landscape_2026.md` decision; operator-rejected for the Sentinel slot specifically.

---

## 7. Honest uncertainty

- **s/claim is UNMEASURED for every candidate** (including the minimax control) — the whole recommendation is gated on the isolation bake-off producing real numbers. The < 60-min bound is the target to beat, not a measured claim.
- **Granite Guardian was the prior lock's Sentinel and was replaced as "broken"** — the I-run11-004 brief must be read to confirm the failure mode (serving vs faithfulness) before crowning it. If it failed on the decomposition contract, the bake-off must prove 3.3-8B passes it now, or fall to Lynx/mistral.
- **"Strongest frontier LLMs, NO encoders"** is a standing operator directive — re-confirm it still holds before proposing any encoder corroborator.
- Granite/Lynx are 8B reasoning judges, NOT the cheap local NLI — they sit in the Sentinel/Lane-B slot and do not by themselves add a local first-pass; that is fine (the Sentinel IS a reasoning decomposition role).
