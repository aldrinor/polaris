# Verifier self-host serving runbook — I-meta-002 PR-8 / M2

> **⚠ PAID STEP — the one-question canary. NOT executed by this PR.**
> Every command below rents real Vast.ai GPU boxes and bills per second. Nothing
> in PR-8/M2 runs these steps. They are the exact operator procedure for the
> later, operator-triggered, single-question canary deploy. Until the operator
> explicitly launches the canary, the three boxes do NOT exist and `PG_*_BASE_URL`
> are unset.

## What this runbook does

Brings up the **three self-hosted verifier roles** on Vast.ai, each serving the
EXACT model pinned in `config/architecture/polaris_runtime_lock.yaml`, then runs
the offline-tested identity probe (`scripts/dr_benchmark/verify_serving_identity.py`)
against the live boxes to confirm `served == pinned` before any benchmark question
is asked.

The **generator (DeepSeek V4 Pro) is NOT here** — it stays on OpenRouter
(`serving_route: openrouter`) across every benchmark scenario. Only Mirror,
Sentinel, and Judge are self-hosted.

Per-role serving spec is declared in `config/serving/verifier_roles.yaml`. This
runbook is the human procedure that realizes that config on rented hardware.

## Roles, boxes, and launch args (from `config/serving/verifier_roles.yaml`)

- **Mirror** — `cohere/command-a-plus`, bf16 full precision, **8×H100** box
  (~438 GB weights). Plain chat serving (no structured-output constraint) so the
  model emits inline `<co>covered text</co:doc_id>` citation spans.
- **Sentinel** — `ibm-granite/granite-guardian-4.1-8b`, **1×A100 80GB** box
  (dense ~16 GB). Plain chat (emits a `<score>` element, not JSON).
- **Judge** — `qwen/qwen3.6-35b-a3b`, fp8, **1×H100** box (~35 GB). Structured /
  guided decoding ENABLED so the verdict is hard-enum constrained at decode time.

> The cost arithmetic lives in `docs/vast_ai_budget_i_meta_002.md`. For PR-8/M2
> and the one-question canary, the FULL-SELF-HOST path is the ONLY valid path: all
> three verifier roles (Mirror, Sentinel, Judge) MUST be served from rented Vast
> boxes. Do NOT point ANY verifier role's `PG_<ROLE>_BASE_URL` at a managed-vendor
> endpoint (Cohere's hosted API or any other). A managed-vendor Mirror endpoint
> breaks BOTH the architecture lock (Mirror `serving_route: vast_self_host_bf16`)
> AND the sovereignty threat model (NO runtime US-vendor LLM calls; Cohere's
> managed API is a US vendor). The identity probe only checks the SERVED slug, so a
> managed endpoint advertising the right name would PASS the probe while running the
> wrong, non-sovereign architecture — the probe cannot catch this, so the operator
> must NOT introduce a managed endpoint in the first place.

## Step 0 — preconditions (operator)

1. Vast.ai account funded (see `docs/vast_ai_budget_i_meta_002.md` for the credit
   to load per scenario).
2. `vastai` CLI installed and logged in (`vastai set api-key <KEY>`).
3. An SSH key registered with Vast for box access.
4. **Sovereignty note:** Vast H100/H200 inventory is US-only — acceptable ONLY
   because the DRB-EN benchmark uses PUBLIC data, no clinical data. Do NOT serve
   clinical/patient data from a Vast box (production clinical = direct-EU
   procurement, separate decision — `docs/vast_ai_budget_i_meta_002.md` §4).

## Step 1 — rent the three boxes (PAID)

Search for offers, then `vastai create instance` per role. Example shape (replace
`<offer_id>` with a matching offer from `vastai search offers`):

```bash
# Mirror — 8xH100 bf16
vastai search offers 'num_gpus=8 gpu_name=H100 inet_down>1000' --order 'dph'
vastai create instance <mirror_offer_id> \
  --image vllm/vllm-openai:latest \
  --disk 600 \
  --env '-p 8000:8000'

# Sentinel — 1xA100 80GB
vastai search offers 'num_gpus=1 gpu_name=A100_SXM4 gpu_ram>=80'
vastai create instance <sentinel_offer_id> \
  --image vllm/vllm-openai:latest \
  --disk 60 \
  --env '-p 8000:8000'

# Judge — 1xH100 fp8
vastai search offers 'num_gpus=1 gpu_name=H100'
vastai create instance <judge_offer_id> \
  --image vllm/vllm-openai:latest \
  --disk 80 \
  --env '-p 8000:8000'
```

> **Storage bills even when STOPPED — only DESTROY halts it.** Per §8.4
> resource discipline + `docs/vast_ai_budget_i_meta_002.md` §0.3, the dominant
> cost is hold-hours. Destroy each box the moment its session ends.

## Step 2 — launch vLLM per role (PAID, on each box)

SSH into each box and start the OpenAI-compatible vLLM server. The
`--served-model-name` MUST equal the locked slug — it is the identity the probe
and the M4 `served==pinned` gate trust. The `model` argument is the weights
SOURCE (HF repo or local path) and is intentionally DISTINCT from the served name
(Codex P2): vLLM advertises `--served-model-name` at `/v1/models`, not the source.

```bash
# Mirror — 8xH100 bf16, PLAIN chat (no guided decoding) for <co> citations
python -m vllm.entrypoints.openai.api_server \
  --model CohereLabs/command-a-plus-05-2026-bf16 \
  --served-model-name cohere/command-a-plus \
  --tensor-parallel-size 8 \
  --dtype bfloat16 \
  --max-model-len 32768 \
  --host 0.0.0.0 --port 8000

# Sentinel — 1xA100, PLAIN chat (Granite emits <score>, not JSON)
python -m vllm.entrypoints.openai.api_server \
  --model ibm-granite/granite-guardian-4.1-8b \
  --served-model-name ibm-granite/granite-guardian-4.1-8b \
  --tensor-parallel-size 1 \
  --dtype bfloat16 \
  --max-model-len 16384 \
  --host 0.0.0.0 --port 8000

# Judge — 1xH100 fp8, STRUCTURED/guided decoding ENABLED for hard-enum verdicts
python -m vllm.entrypoints.openai.api_server \
  --model Qwen/Qwen3.6-35B-A3B \
  --served-model-name qwen/qwen3.6-35b-a3b \
  --quantization fp8 \
  --tensor-parallel-size 1 \
  --max-model-len 32768 \
  --guided-decoding-backend xgrammar \
  --host 0.0.0.0 --port 8000
```

> `--model` (the weights source) above is the per-role `model_source` declared in
> `config/serving/verifier_roles.yaml` — confirm the exact HF repo id / revision
> against the lock's `codex_cross_validation_sources` before launching. Only
> `--served-model-name` (the config `served_model_name`) is bound to the lock slug;
> `model_source` is the weights location and is intentionally NOT lock-equality
> checked.

## Step 3 — set the per-role env vars (operator shell)

The probe and the runtime transport read `PG_<ROLE>_BASE_URL` / `PG_<ROLE>_API_KEY`
(LAW VI — never hard-coded). Use each box's public address + mapped port:

```bash
export PG_MIRROR_BASE_URL="http://<mirror_box_ip>:<port>"
export PG_SENTINEL_BASE_URL="http://<sentinel_box_ip>:<port>"
export PG_JUDGE_BASE_URL="http://<judge_box_ip>:<port>"

# Optional per-role API key if the box was launched with --api-key. If
# PG_<ROLE>_API_KEY is unset, the probe sends NO Authorization header (a
# self-hosted vLLM without --api-key needs none). The probe NEVER falls back to
# the OpenRouter key — it must never leak a foreign key to a self-host box.
export PG_MIRROR_API_KEY="<key-if-any>"
export PG_SENTINEL_API_KEY="<key-if-any>"
export PG_JUDGE_API_KEY="<key-if-any>"
```

## Step 4 — run the identity probe (cheap; confirms served == pinned)

```bash
python -m scripts.dr_benchmark.verify_serving_identity
```

Expected output on success (exit 0):

```
serving-identity probe — per role:
  mirror: reachable=True served_model='cohere/command-a-plus' expected='cohere/command-a-plus' matches_lock=True
  sentinel: reachable=True served_model='ibm-granite/granite-guardian-4.1-8b' expected='ibm-granite/granite-guardian-4.1-8b' matches_lock=True
  judge: reachable=True served_model='qwen/qwen3.6-35b-a3b' expected='qwen/qwen3.6-35b-a3b' matches_lock=True
OK — all 3 verifier roles serve their locked slugs.
```

The probe **fails loud** (exit 1, printed error) if any role: has an unset
`PG_<ROLE>_BASE_URL`, is unreachable, returns a malformed `/v1/models` body, or
serves a model id that is not its locked slug. Do NOT proceed to the benchmark
until the probe is green for all three roles.

## Step 5 — the canary question, then DESTROY (PAID)

Once the probe is green, run the single-question canary per the benchmark runbook,
then **immediately destroy every box** (storage bills until destroy):

```bash
vastai destroy instance <mirror_instance_id>
vastai destroy instance <sentinel_instance_id>
vastai destroy instance <judge_instance_id>
```

Unset the env vars when done so a later session does not accidentally probe a
torn-down box:

```bash
unset PG_MIRROR_BASE_URL PG_SENTINEL_BASE_URL PG_JUDGE_BASE_URL
unset PG_MIRROR_API_KEY PG_SENTINEL_API_KEY PG_JUDGE_API_KEY
```

## Teardown checklist (§8.4 resource discipline)

- [ ] All three Vast instances **destroyed** (not just stopped — storage bills on stop).
- [ ] `PG_*_BASE_URL` / `PG_*_API_KEY` env vars unset.
- [ ] Spend recorded against the `docs/vast_ai_budget_i_meta_002.md` scenario estimate.
