# Wave-3a VALIDATION — READY, blocked ONLY on the VM being down (2026-07-06 ~07:5x)

## Build state: COMPLETE + dual-gated + pushed (branch bot/I-wire-001-integration)
Operator's explicit build list is DONE:
- 14 flags wired ON (U4 ec0f090e) — dual-approved; SLATE-PURITY verified so the paid preflight will NOT die at startup.
- synth-primary corroborated-basket routing (U1 e357f357).
- ~10 per-module fire markers (U2 087aeba9).
- fail-loud activation canary (U3 f0c9058f) — reads the real marker sink (Fable caught+fixed a transport P0).
- 2 dead-check fixes: M6 'anchored'→'candidate' (U4) + numeric silent-swallow→warning (U2).
Offline-validated: flags activate, preflight passes, OFF byte-identical, ~200 tests green across the units.

## The remaining step (operator's "quick run to know if it works") — BLOCKED on VM
Heavy runs (incl. a checkpoint resume — it reloads Qwen3 embedder/reranker/NLI + GLM) run on the VM ONLY, never local.
- VM ssh2.vast.ai:37450 = Connection refused (instance stopped/expired).
- No vast CLI on PATH here; cannot restart/rent autonomously (paid + no tooling).

## To run it the moment a VM is up (resume from a banked SOURCE checkpoint):
1. On the VM: `cd /path/to/POLARIS && git fetch && git checkout bot/I-wire-001-integration && git pull`
2. Set the activation env (the 14 flags are already in the gate-B slate, so gate-B applies them; ALSO arm the canary):
   `export PG_ACTIVATION_CANARY=1`
3. Resume the checkpoint (skips re-fetch; re-runs generation+verify+render with the ACTIVATED modules), e.g.:
   `python scripts/dr_benchmark/run_gate_b.py --resume <run_dir_with_corpus_snapshot> --smoke-scale`
   (or the standard gate-B invocation pointed at a banked corpus_snapshot).
4. ACCEPTANCE: the activation canary must be GREEN (overall_rc=0) — every activated module's `[activation]` marker PRESENT + healthy bools + no old/degrade marker. Then §-1.1 read the run_log `[activation]` lines + the rendered report.
5. If GREEN → optionally a fresh front-half + deeptrace_self_score → rendered_report_acceptance_harness → paid DeepTRACE + DRB-II.
6. If the canary FIRES (rc=1) → it names which module did NOT fire / which old path fired → fix → re-gate → re-run (the wall doing its job — no wasted full run).

## Still to build offline (do NOT need the VM; in progress / next):
- U5 harden: numeric-comparator arm-default clinical-safety (a missing/unknown arm must not license a false comparison) + residual 2d/2b-wiring P2/P3.
- 3b archive (AFTER validation per the locked activate→validate→archive sequence): 2 proven-dead functions + the dormant §-1.3-banned scope hard-DROP branch.
