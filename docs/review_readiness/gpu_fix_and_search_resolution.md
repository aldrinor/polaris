# Box-3 GPU fix + search-diagnosis RESOLUTION

## Box-3 GPU incompatibility (fixed)
- **Problem:** the migrated `/opt/conda` shipped `torch 2.5.1+cu124` (supports `sm_50..sm_90`), but box-3's
  GPU is a Blackwell RTX PRO 6000 = **`sm_120`** → all GPU compute failed ("no kernel image available").
  The migration verify only checked `import torch` (works) — not GPU *execution* (fails).
- **Fix (codex-guided, isolated → clone → cutover):**
  1. Disposable venv proved `torch 2.9.1+cu128` runs `sm_120` matmul + the real Qwen3-Reranker
     (`AutoModelForCausalLM`) + sentence-transformers embeddings on GPU.
  2. Cloned `/opt/conda` → **`/home/polaris/conda_cu128`** (root-owned original untouched = rollback),
     upgraded the torch trio there (`torch 2.9.1 / torchvision 0.24.1 / torchaudio 2.9.1 + cu128`,
     triton 3.5.1, nvidia-cu12 12.8). `pip check` warnings are identical to `/opt/conda` (pre-existing).
  3. Cutover via a **stable symlink `/home/polaris/pipeline-env -> conda_cu128`**; launchers call
     `/home/polaris/pipeline-env/bin/python`. **Rollback = retarget the symlink to `/opt/conda`**
     (verified both directions). Only 5 `.sh` launchers hardcode `/opt/conda/bin/python`; `onstart.sh`
     is git-backup-only and needs no change.
- **Champion caveat:** box-3's newer kernels are **not byte-identical** to the A100 champion env.
  Treat: (a) *refactor equivalence* = compare within the same cu128 env; (b) *champion reproduction*
  = a **replication/re-baseline with tolerances**, not byte-repro.

## Search "0 calls" — RESOLVED (it was an environment artifact, not a bug)
The acceptance "positive control" fired 0 searches on the **degraded** (GPU-broken, browserless) run,
which triggered a diagnosis. Re-running on the **fixed GPU env** reversed the finding:

| | Degraded run | Clean run (cu128, browser) |
|---|---|---|
| THIN checklist | "NONE (no deficiencies)" | **named 3 gaps** (CV safety, MACE, SURMOUNT-MMO) |
| THIN searches | 0 | **1** (search path fires) |
| SATURATED | 0 (possibly vacuous) | 0 — **valid** negative control (THIN proved search fires) |
| harness exit | crash (hardcoded path) | **EXIT=0** (portability fix) |

**Conclusion:** the gap-detector and the `search_more_evidence` path **work correctly**. The earlier
"0 searches" was caused by degraded retrieval feeding the checklist different evidence — **not** the
`outline_agent.py:310` literal-substring grounding gate (that hypothesis is withdrawn). No gap-detector
bug to fix.

**One real (minor) finding:** the harness smoke budget (6 turns / 420 s) is too tight now that GPU
retrieval is slower — the gap was detected and search fired, but "budget exhausted before this gap was
ever searched." A harness-budget tuning item, not a pipeline defect.
