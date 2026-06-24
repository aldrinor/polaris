# Faithfulness Verification Models Landscape 2025/2026 — the swappable MODELS inside the FROZEN faithfulness engine

**Status:** research deliverable, operator-requested 2026-06-23/24. The "faithfulness verification
models" section of the standard pipeline-section review. Mirrors `docs/retrieval_landscape_2026.md`
and `docs/consolidation_landscape_2026.md`.

**Method:** deep research — primary-source verified (arXiv / HuggingFace / GitHub) for every 2025/2026
candidate, year + URL + license per model, then grounded against the actual POLARIS verify path in the
repo. FRONTIER-TECH MANDATE applied: a "recency re-check" pass below explicitly hunts for anything
newer and rejects pre-2024 unless it is the genuine incumbent floor.

**The single hard constraint that frames everything:** the faithfulness ENGINE is the crown jewel and
is **NEVER changed** — strict_verify's deterministic checks (a)-(e), the per-sentence provenance/span
binding, the 4-role D8 release policy, the single-token anti-laundering isolation. This document
benchmarks **only the swappable MODELS** that sit in the engine's judgment slots: the entailment / NLI /
claim-grounding model that answers "does this cited span ENTAIL this sentence's claims?" Nothing here
relaxes a gate. A better model makes the SAME gate more accurate; it never widens a span, never flips
`is_verified`, never makes a failing claim pass.

---

## 0. The one-paragraph answer

POLARIS's live faithfulness check (f) — the entailment judgment that runs after the mechanical
(a)-(e) checks — is an **LLM-as-judge** (GLM-5.2 via `PG_ENTAILMENT_MODEL`, `entailment_judge.py:82`).
That is a deliberate sovereignty-and-reasoning choice, but it carries the cost and the socket-hang
class that the `entailment_judge.py` comments obsess over (HANG-J1/J2/J3, 14-22 minute trickle hangs,
~150s total-deadline patches). Critically, the **local fast-NLI slot the config already anticipates is
empty on the live path**: `NLIModelConfig` declares `microsoft/deberta-v3-large-mnli` and
`MiniCheckConfig` declares `MiniCheck-Flan-T5-Large`, but `deberta_client.py` does not exist on this
branch (it was the frozen pipeline-C NLI substrate) and MiniCheck appears only in the offline
auditor/audit lane, not in `strict_verify`. So the headline finding is: **POLARIS has a declared-but-
empty fast-local-checker slot, and the 2025/2026 frontier has exactly the model class to fill it.** The
frontier pick is a small (0.15-8B) open-weight grounded-factuality model added as an **always-on local
first-pass / corroborator beside the GLM-5.2 judge** — faithfulness-neutral, and it directly kills the
judge-hang and per-claim cost. The co-lead OSS candidates to beat are **FactCG-DeBERTa-L** (0.4B, MIT,
NAACL 2025) for the pure-NLI lane and **LettuceDetect** (ModernBERT, MIT, Feb 2025) for the token-level
span-flagging lane (it maps directly onto POLARIS's span-grounding), plus **IBM Granite Guardian 3.3-8B**
(Apache-2.0, Aug 2025, #3 on LLM-AggreFact) for the reasoning-judge lane. The canonical bake-off discriminator is **LLM-AggreFact
balanced accuracy** plus a **clinical slice** (MedHal / MedHallu, both 2025). The current top-of-board
**Bespoke-MiniCheck-7B (77.4%)** is yardstick-only — its commercial license is "contact us," not OSS.

---

## 1. What POLARIS has today (verified in the repo, not assumed)

| Slot | Current POLARIS implementation | Verified location |
|---|---|---|
| strict_verify checks (a)-(e) | Deterministic: evidence-id in pool, span bounds valid, every decimal in span, ≥2 content-word overlap, numeric match | `provenance_generator.py:942-1148`; `PG_PROVENANCE_MIN_CONTENT_OVERLAP=2` |
| strict_verify check (f) — entailment | **LLM-as-judge**, GLM-5.2 default, swappable via `PG_ENTAILMENT_MODEL`. Asks if the cited SPAN entails the SENTENCE. Fail-CLOSED `judge_error:` sentinel (drop → faithfulness-safe) | `llm/entailment_judge.py:82`; `_DEFAULT_ENTAILMENT_MODEL = "z-ai/glm-5.2"` |
| Local fast-NLI model | **DECLARED-BUT-EMPTY on the live path.** `NLIModelConfig` = `microsoft/deberta-v3-large-mnli`; `entailment_only=True`. But `src/llm/deberta_client.py` does NOT exist on this branch (frozen pipeline-C). `DeBERTaNLI` import is dead | `config/core.py:224-231`; `src/llm/__init__.py:14` (broken import) |
| MiniCheck claim-check | **DECLARED-BUT-OFFLINE.** `MiniCheckConfig` = `lytang/MiniCheck-Flan-T5-Large`. Used only by `auditor_agent.py` / `automated_deep_audit.py` ("external placeholder"), NOT in the live `strict_verify` path | `config/core.py:234-240`; `audit/automated_deep_audit.py:10,488` |
| 4-role D8 sentinel | Release policy over per-claim verdicts; reads `verdict` only, never re-classifies. Side judges (entailment / semantic_conflict / credibility) map to the **mirror** (GLM-5.2) per the runtime lock | `roles/release_policy.py`; `retrieval/semantic_conflict_detector.py:69` |
| Side-judge empty-content guard | Shared retry + fail-to-LABEL-never-HOLD guard for non-binding judge calls (the GLM empty-content collapse) | `llm/side_judge_guard.py` |

**Three honesty corrections to any naive "POLARIS uses DeBERTa-MNLI for NLI" reading:**

1. **The config DECLARES deberta-v3-large-mnli and MiniCheck-Flan-T5-Large, but neither is wired into
   the live faithfulness path.** The live entailment check is the GLM-5.2 LLM-as-judge. The
   `NLIThresholds.entailment_only=True` / `integrity_pass=0.85` knobs are pipeline-C / legacy-integrity
   config, not the Pipeline-A `strict_verify` (f) path.
2. **`src/llm/deberta_client.py` is missing** — `src/llm/__init__.py:14` imports `DeBERTaNLI`,
   `predict_nli`, etc. from a file that is not present on this branch. That is a dead import inherited
   from the frozen legacy CLI; the live path never calls it. So the "local NLI" slot is not a working
   incumbent — it is an empty slot the config anticipates.
3. **This is GOOD news for the bake-off.** An empty, config-anticipated slot is the cleanest possible
   place to add a fast local grounded-factuality model: faithfulness-neutral (advisory beside the
   GLM-5.2 judge), and it directly attacks the judge-hang/cost the `entailment_judge.py` comments
   document at length.

---

## 2. The two model lanes (this is the crux)

The verify slot is not one model class — it is two, and the bake-off must keep them separate.

- **Lane A — fast local NLI / claim-check (the empty slot).** A small encoder or distilled checker
  (0.4-1B) that runs on CPU/GPU in <1s per claim, always-on, zero API spend, no socket-hang class.
  Outputs a supported/unsupported score per (claim, span). This is the MiniCheck / HHEM / FactCG /
  ModernCE family. **Role in POLARIS: an always-on local first-pass and corroborator beside the GLM-5.2
  judge** — it pre-screens the easy cases deterministically and locally, and the LLM-judge is reserved
  for the genuinely hard residual. Faithfulness-neutral: it is advisory unless it agrees with the
  mechanical checks.
- **Lane B — reasoning LLM-judge (the current incumbent).** A larger instruction model (8B+) that
  reasons over span↔claim and emits a verdict, optionally with a reasoning trace for the audit replay.
  This is GLM-5.2 today; the 2025 OSS frontier here is Granite Guardian 3.3-8B and Patronus Lynx. **Role
  in POLARIS: the hard-residual judge.** Sovereignty + reasoning quality are the constraints.

The frontier recommendation is **not "replace the LLM-judge"** — it is **"fill the empty Lane-A slot
with a fast local checker, and bench a sovereign Lane-B judge against GLM-5.2."** Both are
faithfulness-neutral.

---

## 3. The isolation axis (how to bake this off WITHOUT an e2e run)

The engine wiring stays fixed, so the model is benchmarked in isolation against a labeled
claim-grounding gold set. The canonical bake-off for exactly this model class is **LLM-AggreFact** (the
MiniCheck benchmark; the public leaderboard ranks MiniCheck / Bespoke-MiniCheck / AlignScore / HHEM /
Granite Guardian / FactCG head-to-head by **balanced accuracy**). It aggregates 11 grounded-factuality
datasets (RAGTruth, Reveal, AggreFact-CNN/XSum, ExpertQA, ClaimVerify, FactCheck-GPT, etc.).

**Offline harness (no pipeline run):**
1. Feed each `(claim, evidence-span, gold-label)` triple to each candidate model.
2. Score **balanced accuracy** + AUC vs gold, plus **latency** (s/claim) and **VRAM** (servability).
3. **Clinical slice (mandatory for this sovereign clinical pipeline):** add **MedHal** (827K samples,
   Apache-2.0, April 2025) and **MedHallu** (10K PubMedQA-derived, EMNLP 2025), plus **MedNLI** as the
   classic short-premise clinical NLI control. Score the same balanced-accuracy + a **clinical
   high-precision** cut (in clinical context a false "supported" verdict is the lethal error — §-1.1).
4. **The constraint that picks the winner:** balanced accuracy on LLM-AggreFact **AND** the clinical
   slice, under an **OSS-deployable license** (Apache/MIT), **servable small** beside the GLM-5.2 judge
   on GLM-5.2-class infra. A higher vendor headline number does not win if it is NC-licensed or
   needs a separate large GPU.

This is the same behavioral-acceptance posture as the sibling docs: the leaderboard number is the
discriminator for the offline bake-off, but the FINAL adoption gate is that the model's verdicts
**agree with the frozen mechanical checks on a banked `corpus_snapshot.json`** and never relax a gate
(§-1.4). No model is crowned on a vendor self-report alone.

---

## 4. The candidate list (primary-source verified: year + URL + license)

Open-source-first (sovereignty). Split into Lane A (fast local) and Lane B (reasoning judge), plus the
yardstick-only NC/closed models and the genuine 2026 frontier methods.

### Lane A — fast local NLI / claim-check (fills the empty slot)

| Model | Year | Size | License | LLM-AggreFact BAcc | Primary source | Why |
|---|---|---|---|---|---|---|
| **FactCG-DeBERTa-L** | NAACL 2025 (Jan 2025) | 0.4B | **MIT** (weights `yaxili96/FactCG-DeBERTa-v3-Large`) | 75.6 (beats GPT-4o) | arXiv 2501.17144; github.com/derenlei/FactCG | **Lead OSS pure-NLI pick.** Graph-multi-hop synthetic training (CG2C); SOTA-class at 0.4B, fully MIT, CPU-servable. Directly fills the deberta-mnli slot the config already declares. |
| **LettuceDetect** (KRLabs/TU Wien) | Feb 2025 | ModernBERT base/large (~0.15-0.4B) | **MIT** (code + weights + pip) | (token-level; beats all prior encoder models on RAGTruth) | arXiv 2502.17125; github.com/KRLabsOrg/LettuceDetect | **Co-lead OSS pick (token-level).** ModernBERT encoder, 4-8k context, ~30x smaller than the best prompt-based models, **token-level** unsupported-span flagging — maps directly onto POLARIS's span-grounding. MIT, pip-installable, sovereign. |
| **MiniCheck-Flan-T5-L** | EMNLP 2024 | 0.8B | **Apache-2.0** (lib + weights) | 75.0 | arXiv 2404.10774; github.com/Liyan06/MiniCheck | The model POLARIS already CONFIGURES (`MiniCheckConfig`) but never wired live. Incumbent-floor for Lane A; cheap, proven, Apache. |
| **HHEM-2.1-Open** (Vectara) | 2024 (updated 2025) | T5-based, <600MB | **Apache-2.0** | (RAG-tuned; not a top AggreFact row but RAG-native) | huggingface.co/vectara/hallucination_evaluation_model | RAG-specific factual-consistency classifier, 0.6s/judgment on RTX 3090, CPU ~1.5s. Strong corroborator candidate; 4M+ downloads. |
| **ModernCE-large-nli** | 2025 | ModernBERT-large (~0.4B) | **MIT** | (general NLI cross-encoder; bench needed) | huggingface.co/dleemiller/ModernCE-large-nli | Already named in `consolidation_landscape_2026.md` (facet-4). 8192 context, always-on local. Keep consistent across docs: same model, different slot (here = per-claim entailment, there = basket conflict). |
| **MoritzLaurer/tasksource deberta-v3 zeroshot-v2.0-c** | 2024 | 0.4B | **MIT (c-variant data-clean)** | (zero-shot NLI baseline) | huggingface.co/MoritzLaurer | Sovereign zero-shot stance/NLI fallback; the **c-variant** is the commercially-clean one (non-c is research-only). Baseline contender. |
| **FENICE** (Babelscape) | ACL Findings 2024 | NLI + claim-extraction pipeline | **OSS (repo)** | 74.0 (set SOTA on AggreFact at release) | arXiv 2403.02270; github.com/Babelscape/FENICE | Interpretable NLI+claim-extraction metric with **span-level alignment** — matches POLARIS's span-grounding ethos (shows WHICH input span entails each claim). Method-aligned; bench as the interpretable option. |
| **AlignScore** | ACL 2023 | RoBERTa-L (0.4B) | **OSS** | 70.8 | arXiv 2305.16739 | **Baseline-only (pre-2024).** Retained solely as the classic NLI-alignment floor every newer model is measured against. Not a recommendation. |

### Lane B — reasoning LLM-judge (competes with GLM-5.2)

| Model | Year | Size | License | LLM-AggreFact | Primary source | Why |
|---|---|---|---|---|---|---|
| **IBM Granite Guardian 3.3-8B** | Aug 2025 | 8B | **Apache-2.0** | **#3 on board; 0.765 avg (thinking mode)**; RAGTruth 0.821, Reveal 0.896 | huggingface.co/ibm-granite/granite-guardian-3.3-8b; arXiv 2412.07724 | **Lead sovereign Lane-B pick.** Hybrid-thinking groundedness judge, 8B beats GPT-4o + Mistral-Large-2, Apache-2.0, #1 on REVEAL. Genuine 2025 OSS judge to bench head-to-head vs GLM-5.2. |
| **Patronus Lynx-8B / 70B** | Jul 2024 | 8B / 70B | **OSS (Llama-3 community)** | (SOTA on HaluBench at release; beats GPT-4o on RAG halluc.) | arXiv 2407.08488; huggingface.co/PatronusAI/Llama-3-Patronus-Lynx-8B-Instruct | RAG-hallucination judge trained on CovidQA/PubmedQA/DROP/RAGTruth (clinical-adjacent training data). Llama-3 license = check field-of-use; bench the 8B as a sovereign judge contender. |
| **GLM-5.2** (incumbent) | 2025 | mirror role | sovereign open-weight | — | runtime lock | The current Lane-B judge. The control arm. Bench every Lane-B contender against it; do not replace without a behavioral win. |

### Yardstick-only (NC / closed / restricted — do NOT deploy; measure against)

| Model | Year | License | Note |
|---|---|---|---|
| **Bespoke-MiniCheck-7B** | Aug 2024 | **Restricted** ("commercially useable — contact company@bespokelabs.ai"; not a clean OSS grant) | **#1 on LLM-AggreFact at 77.4%.** The number to beat, NOT a deployable. Treat the 77.4 as the ceiling yardstick. |
| GPT-4o / Claude-3.5-Sonnet | 2024 | Closed | Non-sovereign. Leaderboard reference points only (75.9 / 77.2). |
| Bespoke / HerO 7B NC variants | 2024 | CC-BY-NC | Design reference only (consistent with `consolidation_landscape_2026.md`). |

### Genuine 2026 frontier METHODS (verify-before-adopt; mostly papers, not yet vendorable weights)

| Method | Date | Primary source | What it adds | Adoptability |
|---|---|---|---|---|
| **GSAR — typed grounding** | Apr 25 2026 | arXiv 2604.23366 | Distinguishes **signal-derived** vs **model-inferred** claims — a typed grounding verdict, not one scalar. Directly relevant to the "untraceable citation = faithfulness defect?" question POLARIS already flagged. | Method/pattern; check for weights. |
| **RT4CHART — retromorphic context-faithfulness** | 2026 | arXiv 2603.27752 | Decomposes the answer into independently verifiable claims, **strict context-only evidence** requirement, fine-grained per-claim diagnosis. Mirrors POLARIS's per-sentence isolation. | Method; pattern-inspiration. |
| **RAGLens / SAE white-box detectors** | Dec 2025 / 2026 | arXiv 2512.08892; 2604.05358 | Sparse-autoencoder feature-based faithfulness flag from the generator's OWN activations — real-time, white-box. Only works if you control the generator weights (sovereign deploy can). | Forward-looking; not a drop-in checker. |
| **FaithJudge** (Vectara) | 2025/2026 | vectara (HHEM successor) | LLM-as-judge over a pool of human-annotated hallucination examples — improves judge consistency. Pattern for the Lane-B prompt. | Method; consistent-with the GLM-5.2 judge upgrade. |
| **HalluGuard** | Oct 2 2025 | arXiv 2510.00880 | Small **reasoning** model, evidence-grounded, competes with MiniCheck. | **CC-BY-4.0 (paper)**; verify weight license. Bench as a Lane-A/B hybrid. |
| **InFi-Check** | Jan 2026 | arXiv 2601.06666 | Interpretable + **fine-grained** fact-checking of LLMs — per-claim diagnosis with explanations, the 2026 successor direction to FENICE/FactCG. | Method; verify weight release. Track as the interpretable-fine-grained 2026 entry. |

### Clinical gold sets (the isolation-axis clinical slice)

| Dataset | Date | License | Use |
|---|---|---|---|
| **MedHal** | Apr 2025 | **Apache-2.0** | 827K samples (MedMCQA/MedNLI/Augmented-Clinical-Notes/MedQA/PubMedSum); binary factual/non-factual w/ explanations. The large clinical claim-grounding slice. |
| **MedHallu** | EMNLP 2025 | open | 10K PubMedQA-derived QA pairs w/ controlled hallucinations; clinical high-precision cut. |
| **MedNLI** | 2018 | restricted (PhysioNet credential) | Classic short-premise clinical NLI control; incumbent-floor clinical baseline. |
| **RAGTruth** (clinical subset) | 2024 | open | RAG-native hallucination annotations; already inside LLM-AggreFact. |

---

## 5. KEEP vs ADD vs FIX (against the current verify path)

The faithfulness ENGINE is frozen. Everything below is a MODEL swap or a wiring fix, never an
engine change.

### KEEP (verified present and correct)
- **The deterministic (a)-(e) mechanical checks.** These ARE the crown jewel's first line and must
  never be replaced by a learned model — they are exact, auditable, and fail-closed. A learned NLI
  model is only ever an ADD beside them.
- **The fail-CLOSED `judge_error:` sentinel** in `entailment_judge.py`. A model swap inherits this
  contract: unreachable judge → drop → faithfulness-safe.
- **The single-token anti-laundering isolation** (`credibility_pass.py`). No set/basket verifier may
  concatenate spans. Any Lane-A model verifies one (claim, span) pair in isolation.
- **GLM-5.2 as the Lane-B control.** Sovereign, reasoning-capable. Keep as the control arm; bench
  contenders against it.

### ADD (the real gaps, faithfulness-neutral)
1. **Fill the empty Lane-A slot with a fast local grounded-factuality model.** This is the single
   biggest genuine gap and the cleanest win: an always-on local checker (FactCG-DeBERTa-L lead,
   MiniCheck-Flan-T5-L incumbent-floor, HHEM-2.1-Open RAG-corroborator) that pre-screens locally,
   reserves the GLM-5.2 judge for the hard residual, and **eliminates the per-claim socket-hang and
   cost** the `entailment_judge.py` comments document. Advisory beside the mechanical checks.
2. **Bench a sovereign Lane-B judge (Granite Guardian 3.3-8B) against GLM-5.2.** Apache-2.0, 8B,
   #3-on-board groundedness reasoning judge. Only adopt on a behavioral win.
3. **A clinical-slice acceptance gate.** No model is adopted without passing the MedHal/MedHallu
   clinical high-precision cut — a general-domain BAcc win that regresses clinical precision is a
   §-1.1 fail.

### FIX (verified, repo-grounded, do first)
1. **The dead `deberta_client.py` import.** `src/llm/__init__.py:14` imports `DeBERTaNLI` from a file
   that does not exist on this branch (directory listing shows only `__init__.py`, `gemini_client.py`,
   `kimi_client.py`). The unconditional import means `import src.llm` is an **inferred** latent
   ImportError (inferred from the absent file, not run). Either restore it (if the local-NLI slot is to
   be filled) or remove the dead import. This is the literal "declared-but-empty slot." Resolving it IS
   adopting Lane A.
2. **Reconcile the config declarations with reality.** `NLIModelConfig` (deberta-v3-large-mnli) and
   `MiniCheckConfig` (Flan-T5-Large) are declared but unused on the live path. Either wire the chosen
   Lane-A model into `strict_verify` or annotate the config as legacy/pipeline-C so a future reader
   does not assume the live path runs DeBERTa-MNLI.
3. **Fix the stale docstring** in `entailment_judge.py:28-30` ("Gemma 4 31B by default") — the code
   default migrated to GLM-5.2. One-line hygiene (same class as the `semantic_conflict_detector.py:30`
   stale-docstring nit flagged in the consolidation doc).

### DO NOT add
- **Bespoke-MiniCheck-7B in production** — license is "contact us," not OSS. Yardstick-only.
- **Any closed/NC judge** (GPT-4o, Claude, NV-Embed-class) on the live path — sovereignty.
- **A learned NLI model as a REPLACEMENT for the mechanical (a)-(e) checks** — they stay; the model is
  always additive.
- **A set/basket joint-entailment verifier inline** — re-opens evidence laundering (the
  `consolidation_landscape_2026.md` facet-6 boundary). THIS doc is the per-claim MODEL; that doc is the
  set layer.

---

## 6. The bake-off candidate list (the next step)

Open-source-first. **Acceptance is behavioral, not a vendor score:** offline LLM-AggreFact + clinical
slice picks the discriminator, then the winner must agree with the frozen mechanical checks on a banked
`corpus_snapshot.json` and never relax a gate (§-1.4).

**Lane A (fast local — the empty slot):**
- FactCG-DeBERTa-L (0.4B, MIT) — **co-lead candidate to bench (pure NLI)**
- LettuceDetect (ModernBERT, MIT) — **co-lead candidate to bench (token-level span flagging)**
- MiniCheck-Flan-T5-L (0.8B, Apache-2.0) — incumbent-floor / already-configured
- HHEM-2.1-Open (T5, Apache-2.0) — RAG-native corroborator
- ModernCE-large-nli (ModernBERT, MIT) — long-context, cross-doc consistent with consolidation doc
- FENICE (NLI+claim-extraction, OSS) — interpretable span-aligned option
- MoritzLaurer deberta-v3 zeroshot-v2.0-**c** (MIT) — zero-shot sovereign fallback
- *(AlignScore — pre-2024 baseline floor only)*

**Lane B (reasoning judge — competes with GLM-5.2):**
- Granite Guardian 3.3-8B (Apache-2.0) — **lead candidate to bench**
- Patronus Lynx-8B (verify Llama-3 field-of-use) — RAG-halluc judge, clinical-adjacent training
- GLM-5.2 — control arm

**Yardsticks-to-beat (NOT deployed):**
- Bespoke-MiniCheck-7B (77.4 ceiling), GPT-4o (75.9), Claude-3.5-Sonnet (77.2)

**Clinical slice (mandatory):**
- MedHal (Apache-2.0), MedHallu, MedNLI control, RAGTruth-clinical

**2026 methods to track (not yet drop-in):**
- GSAR typed grounding, RT4CHART retromorphic, RAGLens/SAE white-box, FaithJudge, HalluGuard, InFi-Check (interpretable fine-grained, Jan 2026)

---

## 7. Honest uncertainty

- **LLM-AggreFact numbers are model-author-reported on a public leaderboard, not an independent
  head-to-head on POLARIS's own clinical claims.** Hence the behavioral-acceptance + clinical-slice
  requirement before any swap.
- **Bespoke-MiniCheck license is genuinely ambiguous** — the docs say "commercially useable, contact
  us." That is NOT a clean OSS grant, so it is yardstick-only here. If Bespoke issues a clear OSS/
  commercial license, re-classify.
- **Granite Guardian 3.3 / Lynx are LLM-judges (8B), not the cheap local NLI** — they belong in Lane B
  and do not by themselves solve the cost/hang problem the empty Lane-A slot does. Don't conflate the
  lanes.
- **Patronus Lynx is on the Llama-3 community license** — verify the field-of-use clause before
  sovereign deploy (clinical use may be fine, but confirm).
- **The 2026 methods (GSAR, RT4CHART, RAGLens) are papers/patterns**, several without confirmed
  open-weight releases. They inform the design (especially GSAR's typed grounding for the "untraceable
  citation" question), but are not bake-off-deployable code today.
- **The biggest single recommendation by confidence:** fill the empty Lane-A slot. It is the cleanest
  win (config already anticipates it, it kills the judge-hang/cost, it is faithfulness-neutral), and
  FactCG-DeBERTa-L (MIT, 0.4B, beats GPT-4o on AggreFact) is the lead.

---

## 8. Relevant files (for the bake-off brief)
- `src/polaris_graph/llm/entailment_judge.py:82` — the live LLM-as-judge (f) check; `_DEFAULT_ENTAILMENT_MODEL`, `PG_ENTAILMENT_MODEL`, the HANG-J total-deadline patches; stale docstring :28-30
- `src/polaris_graph/generator/provenance_generator.py:942-1148` — the deterministic (a)-(e) mechanical checks (KEEP, never model-replaced)
- `src/config/core.py:224-240` — `NLIModelConfig` (deberta-v3-large-mnli) + `MiniCheckConfig` (Flan-T5-L), both DECLARED-but-unused on live path
- `src/llm/__init__.py:14` — the DEAD `DeBERTaNLI` import (deberta_client.py missing → fix or restore)
- `src/agents/auditor_agent.py:180-218` — MiniCheck wired in the OFFLINE auditor lane only
- `src/polaris_graph/llm/side_judge_guard.py` — side-judge empty-content guard (fail-to-LABEL-never-HOLD)
- `src/polaris_graph/roles/release_policy.py` — 4-role D8 release policy (reads verdict only)
- `src/polaris_graph/retrieval/semantic_conflict_detector.py:69` — side judge (GLM-5.2), `PG_ENTAILMENT_MODEL`

## 9. Primary sources (2025/2026)
- LLM-AggreFact leaderboard — https://llm-aggrefact.github.io/ ; dataset https://huggingface.co/datasets/lytang/LLM-AggreFact
- MiniCheck (EMNLP 2024) — arXiv 2404.10774 ; github.com/Liyan06/MiniCheck (Apache-2.0)
- Bespoke-MiniCheck-7B (Aug 2024) — bespokelabs.ai/bespoke-minicheck (license: contact-us → yardstick-only)
- FactCG (NAACL 2025, Jan 2025) — arXiv 2501.17144 ; github.com/derenlei/FactCG (MIT, 0.4B)
- LettuceDetect (KRLabs/TU Wien, Feb 2025) — arXiv 2502.17125 ; github.com/KRLabsOrg/LettuceDetect (MIT, ModernBERT token-level)
- IBM Granite Guardian 3.3-8B (Aug 2025) — huggingface.co/ibm-granite/granite-guardian-3.3-8b (Apache-2.0). NOTE: the 3.3 BAcc figures (0.765 avg) are from the HF model card; arXiv 2412.07724 is the ORIGINAL Granite Guardian paper, not the 3.3 result.
- InFi-Check interpretable fine-grained fact-checking (Jan 2026) — arXiv 2601.06666
- Patronus Lynx (Jul 2024) — arXiv 2407.08488 ; huggingface.co/PatronusAI/Llama-3-Patronus-Lynx-8B-Instruct
- HHEM-2.1-Open (Vectara, 2024/2025) — huggingface.co/vectara/hallucination_evaluation_model (Apache-2.0)
- ModernCE-large-nli (2025) — huggingface.co/dleemiller/ModernCE-large-nli (MIT)
- FENICE (ACL Findings 2024) — arXiv 2403.02270 ; github.com/Babelscape/FENICE
- HalluGuard (Oct 2025) — arXiv 2510.00880 (CC-BY-4.0)
- GSAR typed grounding (Apr 2026) — arXiv 2604.23366
- RT4CHART retromorphic (2026) — arXiv 2603.27752
- RAGLens / SAE faithfulness (Dec 2025) — arXiv 2512.08892 ; 2604.05358
- MedHal (Apr 2025) — arXiv 2504.08596 (Apache-2.0, 827K)
- MedHallu (EMNLP 2025) — aclanthology.org/2025.emnlp-main.143 ; medhallu.github.io
- "Benchmarking LLM Faithfulness in RAG with Evolving Leaderboards" (May 2025) — arXiv 2505.04847
- AlignScore (ACL 2023, baseline floor only) — arXiv 2305.16739

---

## 10. Recency audit (2026-06-24) — is this the 2025/2026 frontier, or did old methods sneak in?

Operator challenge (FRONTIER-TECH MANDATE): "research ONLY the 2025/2026 frontier; reject pre-2024
unless it is the genuine incumbent floor."

**This model class is genuinely 2024-heavy** — and that is the honest reality, not a research miss.
MiniCheck (2024), HHEM (2024), Lynx (2024), AlignScore (2023), FENICE (2024) are all pre-2025. The
class's 2025/2026 frontier is thinner and more incremental than retrieval/embedding. So the recency
discipline is: **explicitly justify each retained pre-2025 model as the incumbent floor, and surface
the genuine 2025/2026 entries separately.**

| Model | Year | Verdict | Justification |
|---|---|---|---|
| **FactCG-DeBERTa-L** | Jan 2025 | **genuine 2025 frontier** | NAACL 2025, beats GPT-4o at 0.4B, MIT. Co-lead Lane-A pick (pure NLI). |
| **LettuceDetect** | Feb 2025 | **genuine 2025 frontier** | ModernBERT token-level span detector, MIT, ~30x smaller than best prompt models. Co-lead Lane-A pick (token-level). Found via the recency re-check. |
| **InFi-Check** | Jan 2026 | **genuine 2026 frontier** | Interpretable fine-grained fact-checking. Track as the 2026 interpretable entry. Found via the recency re-check. |
| **Granite Guardian 3.3-8B** | Aug 2025 | **genuine 2025 frontier** | #3 on LLM-AggreFact, Apache-2.0, hybrid-thinking. Lead Lane-B pick. |
| **HalluGuard / MedHal / MedHallu / GSAR / RT4CHART / RAGLens / FaithJudge** | 2025-2026 | **genuine 2025/2026** | The newest entries; GSAR (Apr 2026) and RT4CHART (2026) are the genuine 2026 methods. Clinical sets are 2025. |
| **ModernCE-large-nli** | 2025 | **genuine 2025** | ModernBERT-based NLI cross-encoder, MIT. Consistent with consolidation doc. |
| **MiniCheck-Flan-T5-L** | 2024 | **incumbent floor (retained, justified)** | The model POLARIS already CONFIGURES; Apache, proven, still a top-10 AggreFact row in 2026. Retained as the Lane-A floor, NOT crowned as frontier. |
| **HHEM-2.1-Open** | 2024 (2025 update) | **incumbent floor (retained, justified)** | 4M+ downloads, RAG-native, Apache, sub-second. Still the standard cheap RAG-consistency check in 2026. Corroborator role. |
| **Patronus Lynx** | Jul 2024 | **incumbent floor (retained, justified)** | The open RAG-hallucination judge; clinical-adjacent training. Retained as a Lane-B contender, dated honestly. |
| **AlignScore** | 2023 | **dated — baseline ONLY** | Explicitly the pre-2024 NLI-alignment floor every newer model is measured against. NOT a recommendation. |
| **deberta-v3-large-mnli (POLARIS config)** | 2021 | **dated — this is the declared-but-empty slot, i.e. the defect** | The config's declared local-NLI model is a 2021 DeBERTa. It is NOT wired live, and it is exactly what the Lane-A bake-off replaces. Named as the gap, not a recommendation. |

**Recency re-check honesty note:** the leaderboard WebFetch rendered only 11 of 39 models and
self-contradicted (listed Granite-3.3/FactCG while claiming "no 2025/2026 models"), so the first pass
had the 2024-era rendered top, not a confirmed current top. A targeted re-search closed that gap: it
surfaced **LettuceDetect (Feb 2025, ModernBERT token-level, MIT)** — a genuine 2025 Lane-A frontier
model the first pass missed, now a co-lead — and **InFi-Check (Jan 2026)**, the 2026 interpretable
fine-grained entry. The re-search also confirmed **no newer model has displaced Bespoke-MiniCheck-7B at
the 77.4 top of LLM-AggreFact** (HHEM-2.1 sits at 71.8; the leading deployables remain FactCG/Granite/
LettuceDetect), so the 77.4 ceiling yardstick holds.

**Net:** the recommendations ARE 2025/2026-current at the top of each lane (FactCG Jan-2025 +
LettuceDetect Feb-2025 co-leading Lane A, Granite Guardian Aug-2025 leading Lane B), the retained 2024
models are each justified as the genuine incumbent floor for a class that did not churn as fast as
retrieval, and the only "old old method" present — deberta-v3-large-mnli — is the POLARIS config's own
dormant declaration, named as the defect the bake-off fixes, not crowned. The genuine 2026 methods
(GSAR typed grounding, RT4CHART, RAGLens/SAE, InFi-Check) are surfaced as forward-track patterns, with
GSAR's signal-derived-vs-model-inferred typed grounding the most directly relevant to POLARIS's open
"untraceable citation = faithfulness defect?" question.
