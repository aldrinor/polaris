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
