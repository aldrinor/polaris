# Compose-fix wheel progress

- 2026-07-11 (Opus): Proved + landed the compose OFF-LOOP fix on the AUTHORITATIVE path. A/B via a
  real 2-section heartbeat probe (scripts/_hb_probe_run.py, cap-primary 2): CONTROL (to_thread inlined
  = pre-fix) => phase2_max_concurrent=1, max event-loop gap=301.47s (froze minutes), sections serial,
  wall=486.7s. TREATMENT (fix) => phase2_max_concurrent=2 (two off-loop worker threads, phase-2
  overlapping), max loop-gap=0.55s (<2s bar), wall=269.6s. Localized + offloaded FOUR sync-on-loop
  NLI-verify hot spots (each revealed as the next heartbeat freeze): _compose_section_per_basket
  (multi_section_generator.py:5477/5525), _repair_untokened_draft (:5589), sentence_repair re-verify
  (sentence_repair.py:519), coherence re-verify (section_polish.py:283). strict_verify tail (:5681) was
  already offloaded. All offloads are faithfulness-BYTE-IDENTICAL (same verifier, same verdicts, only
  the executing thread changes). Landed env knobs proven read: PG_SIDE_JUDGE_MAX_CONCURRENCY=16
  (resolve_max_concurrency()==16), PG_PARALLEL_VERIFY=8 (_parallel_verify_workers()==8),
  PG_ENTAILMENT_TOTAL_DEADLINE_RETRIES=1. Dropped the DEAD section_polish coherence-workers constants
  from the prior interrupted run (defined, never referenced).

- 2026-07-11 (Opus, round 2): Closed the gate's remaining risk + took the concurrency proof to SCALE.
  (1) RECORD/REPLAY A/B (scripts/_replay_ab.sh + _replay_compare.py + shim in _hb_probe_run.py) —
  certifies kept/dropped VERDICT-SET IDENTITY between a serial control and the concurrent worker-thread
  treatment at ZERO LLM cost. One record pass captures every NLI-judge (verdict,reason) + writer draft
  by CONTENT hash; two replays return them deterministically: CONTROL (PG_MAX_PARALLEL_SECTIONS=1 +
  to_thread inlined) vs TREATMENT (PG_MAX_PARALLEL_SECTIONS=2 + real to_thread). Judge is a pure fn of
  (sentence,span) so content-keyed replay is race-free => any serial-vs-concurrent diff would be a real
  shared-state race. MEASURED: record judge_keys=20/writer_keys=7/divergent=0; both replays 23 judge +
  8 writer calls, 0 miss; section 0 verified=1 dropped=1 (a real KEEP and a real DROP) IDENTICAL sha
  both arms; assembled_report_md byte-identical (sha df569cee). VERDICT-SET IDENTITY: PASS.
  (2) FULL-CORPUS render launched on THIS worktree (launch_compose_fullcorpus.sh — note the committed
  launch_compose_gear_iter5.sh cds to /workspace/compose_wt, a SEPARATE worktree pinned PRE-FIX at
  eff82fb, so it would NOT exercise the fix) at PG_MAX_PARALLEL_SECTIONS=4 with the heartbeat probe.
  MEASURED at scale: achieved compose concurrency = 4 (PHASE2 ENTER concurrent=1->2->3->4, all
  off_loop_thread=True) — FOUR sections' phase-2 interleaving, up from pre-fix 1.0. Zero HB FREEZE
  during phase-2 (only a single 2.7s gap at startup, 82s BEFORE the first phase-2 entry, vs the pre-fix
  301s phase-2 freeze). Full-corpus wall pending (residual section 4 = 274 baskets is the long pole).
