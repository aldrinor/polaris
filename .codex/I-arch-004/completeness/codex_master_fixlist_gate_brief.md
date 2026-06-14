# CODEX GATE — A3 master fix-list COMPLETENESS + SOUNDNESS

```
HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## YOUR ROLE
You are the COMPLETENESS + SOUNDNESS gate for the master fix-list at
`.codex/I-arch-004/A3_master_fix_list.md` (23 fixes F01-F23 + meta-defects M1-M7).
5 Claude auditors reported candidate GAPS and SPEC-ERRORS. I (Claude) have
independently verified each against live code. **You VERIFY my dispositions and
do a bounded fresh scan — you do NOT rubber-stamp.** Codex is the only gate.

## GROUND-TRUTH SOURCES (all real, all checked)
- Master list: `.codex/I-arch-004/A3_master_fix_list.md`
- Ledger: `.codex/I-arch-004/combined_dual_sourced_ledger.md`
- Prior completeness verdict: `.codex/I-arch-004/completeness/codex_completeness_verdict.txt` (already `MATERIAL_GAPS_REMAIN`)
- Code root: `C:\POLARIS` — canonical files: `scripts/run_honest_sweep_r3.py`,
  `scripts/dr_benchmark/run_gate_b.py`, `src/providers/llm_provider.py`,
  `src/polaris_graph/llm/openrouter_client.py`,
  `src/polaris_graph/retrieval/live_retriever.py`,
  `src/polaris_graph/generator/multi_section_generator.py`,
  `src/polaris_graph/roles/{role_pipeline.py,native_gate_b_inputs.py}`,
  `src/polaris_graph/report_redactor.py`, `src/polaris_graph/provenance_generator.py`

## MY VERIFIED EVIDENCE (you confirm/refute each against the code)

### CONFIRMED GAPS (real chokepoint, NO [F##] in master list)

**G1 — B7 PG_LIVE_MAX_EV_TO_GEN 20-row default (no F##).** LIVE at
`run_honest_sweep_r3.py:4758` `max_ev = int(os.getenv("PG_LIVE_MAX_EV_TO_GEN","20"))`.
grep of A3_master_fix_list.md = ZERO hits for MAX_EV / B7 / "evidence rows". NOT in
F19 (token caps), F18 (concurrency), F23 (catch-all lists 12/12/40 breadth, not this).
**SEVERITY NUANCE (I checked the slate, the auditor's two framings conflict):** the
Gate-B slate at `run_gate_b.py:498` sets `PG_LIVE_MAX_EV_TO_GEN=1500` AND
`run_gate_b.py:548` sets `PG_CAPPED_FINDING_DEDUP=1`. So on the CANONICAL cert run the
cap is 1500, not 20 — B7 is LATENT for the cert run and bites only direct/bypass/OFF-mode
callers (`run_honest_on_prerebuild_corpus.py:148`, `run_live_honest_cycle.py:245` both
read default 20). Real §-1.3 silent-downgrade hazard for non-slate callers; NOT an active
cert-run starvation. My disposition: CONFIRMED GAP, P1 (latent, fail-loud-on-low-default
candidate). Confirm or correct the severity.

**G2 — Per-query exception boundary missing in Gate-B `--all` loop.** LIVE at
`run_gate_b.py:1778-1780`: `summary = asyncio.run(run_gate_b_query(...))` with NO
try/except. Any exception escaping ONE query aborts ALL remaining 5-Q cert queries.
No `PG_ABORT_ON_QUERY_ERROR` knob exists. NOT covered by F01 (fixes the deterministic
cross-query semaphore RuntimeError — a DIFFERENT crash class) or F04 (resume-after-crash
durability). My disposition: CONFIRMED GAP, P1.

**G3 — Atom-refusal validator strict-mode escape.** Per
`run_honest_sweep_r3.py` atom_refusal_validator import path under `PG_ATOM_REFUSAL_MODE=strict`:
skips empty atom catalogs + swallows validator exceptions; only total_words recomputed on
replacement, not verified/refused totals. No F covers it (F05/F06 = Judge + Sentinel in
roles/, a different gate). My disposition: CONFIRMED GAP, P2 (faithfulness-adjacent fail-open).
VERIFY the line + behavior.

**G4 — Required-entity coverage ledger fail-soft.** `run_honest_sweep_r3.py:8061-8072`
(DEFAULT OFF, Gate-B forces on): any ledger/render/write exception removes required-entity
gap disclosure without holding the report. No F covers it (F11 = clinical.yaml completeness
gate, a different surface). My disposition: CONFIRMED GAP, P2. VERIFY.

**G5 — Distiller MAP N+1 (C7 throughput).** `PG_DISTILL_MICROBATCH_SIZE` read but never
exercised (`evidence_distiller.py` _mb defaults size 1) → one LLM call per source per
section. F18 = "bounded concurrent pools" (does not microbatch the MAP); F21 only threads
research_question. C7's real fix (actually exercise microbatching) is absent. My
disposition: CONFIRMED GAP, P2. VERIFY.

**G6 — M-44 primary-study injection bare cap.** `multi_section_generator.py:4546`
`max_ev_per_section: int = 20` is a bare function-signature default that does NOT read
`PG_MAX_EV_PER_SECTION` — while the main resolver at `:1202` uses
`int(os.getenv("PG_MAX_EV_PER_SECTION","30"))` and the slate sets 40. Narrow injection-path
residual, not in F19 (token caps, not per-section evidence cap). My disposition: CONFIRMED
GAP, P3. VERIFY both line numbers.

**G7 — D4 frey_osborne grounded on ORA landing/abstract page, not paper body.** Ledger D4
(P3, weight-not-drop). No F##; F14's <1000-char min-body gate does NOT catch a >1000-char
abstract/landing page that still lacks the body grounding methods. My disposition: CONFIRMED
GAP, P3 (§-1.3 weighting item).

**G8 — Malformed provenance token survives into shipped sentence** (claim 05-004): parser
leaves invalid bracketed text `[ev_brynjolfsson_genai_at_work]` inside a kept sentence when a
valid #ev token co-exists (parsed evidence_ids only ['ev_433']). A citation marker resolving
to no real evidence id. Not in F01-F23 (F23 lists hardcoded tokens, never the provenance-PARSER
tolerance of invalid bracketed text; distinct from F10's verified-count). Source:
`deadrun_forensic/codex_cross_audit.txt:25`. My disposition: CONFIRMED GAP, P2 (span-grounding
integrity). VERIFY against the forensic + a spot-check of the provenance parser.

**G9 — Generator hard-pinned `allow_fallbacks=false` cannot escape a mid-call stall.** The
runaway empty-completion (268e2f24, 473.5s zero-content) could NOT fail over mid-call. F02
adds empty-stream fail/retry but never specifies the retry routes to a DIFFERENT provider, and
a same-provider retry into the hard pin can re-stall. Source: `deadrun_forensic/claude_prep_verification.txt:36-39`.
My disposition: CONFIRMED — but I frame this as a SPEC-ERROR on F02's acceptance (see S-F02 below),
not a wholly separate gap. Confirm whether you'd file it as a gap or an F02 acceptance defect.

### SPEC-ERRORS (existing F has wrong scope / inadequate acceptance)

**S-F03 (HIGHEST PRIORITY — harness-layer faithfulness relaxation).** F03 declares status
`abort_excessive_gap (or partial)` and accepts only the MANIFEST status. But the cert run is
Gate-B, and `run_gate_b.py:1789` is LIVE:
`if not (status == "success" or str(status).startswith("partial")): overall_rc = 1`
→ ANY `partial*` status exits `rc=0` (green). So F03's `(or partial)` branch ships an
8-of-10-stubbed clinical report as a SUCCESSFUL run at the harness layer. **Correction:** F03
must (a) use a NON-`partial*` status, (b) add the companion fix at `run_gate_b.py:1789` —
default to fail any non-`success` status unless `PG_GATE_B_ALLOW_PARTIAL=1`, (c) accept on the
EXIT CODE (overall_rc != 0), not just the manifest. Re-rate P1. I VERIFIED line 1789 reads exactly
as quoted. Confirm.

**S-F18 (C5 + C7 under-scope).** F18 says "C3-C7 bounded concurrent pools, gates unchanged."
But C5 has a NON-concurrency half: `live_retriever.py:3301` sets `_corpus_truncated=True` then
breaks, returning a partial corpus (`:3530`). I grepped ALL consumers: only `pathB_capture.py:35/42`
+ `pathB_runner.py:209` + `score_run.py:75` read it — all TELEMETRY, NO fail-closed/repair gate.
So a truncated (partial) corpus feeds generation silently — a §-1.3 breadth/recall degradation
BEFORE the faithfulness gates, which F18's "gates unchanged" explicitly excludes. C7's real fix
(microbatch, G5 above) is also not "bounded concurrent pools." **Correction:** add
`PG_CORPUS_TRUNCATION_POLICY` fail-closed/repair as a SEPARATE item, and C7 microbatch as its
own fix. Confirm.

**S-F12 (D12 scoped clinical-only; it's a GLOBAL §-1.3 bug).** F12 houses the doi.org→T4
demotion under Wave-2 clinical with a CLINICAL-ONLY acceptance. But D12 (ledger:117) was ACTIVE
on the WORKFORCE drb_72 run: 50 doi.org sources demoted to T4, `weight_basis=tier_prior` for
803/803. A tier bug is a credibility bug for EVERY question type. **Correction:** add a
domain-independent acceptance (a doi.org-hosted canonical-DOI journal resolves to T1 regardless
of host, verified on the workforce corpus) — not only via the clinical adequacy gate. Confirm.

**S-F07 (file list omits openrouter_client.py).** F07's "fail-loud on blank judge" must live
where `status='ok'` is set on a null-usage/empty-content stream. I confirmed that site is
`openrouter_client.py` (the trace/harness records `status="ok"` — line 172 default param of the
trace-record fn, line 2319 forensic-capture call; D14 = "the harness accepts blank 200s, both a
generate AND a credibility_judge"). F07's file list names only run_honest_sweep_r3.py /
semantic_conflict_detector.py / entailment_judge.py — it OMITS openrouter_client.py, the SAME
file F02 touches. The cross-wave F02/F07 overlap on that shared blank-stream site is invisible to
the serialize discipline (which keys on named files). **Correction:** add openrouter_client.py to
F07's file list + note the F02/F07 serialize overlap. Confirm.

**S-F16 (semaphore mislocated).** F16 cites the global LLM semaphore as
`openrouter_client.py:1595` and "same object as F01." I confirmed `openrouter_client.py:1598-1599`
is only the ACQUIRE site (`from src.providers.llm_provider import get_semaphore; semaphore =
get_semaphore()`). The semaphore is DEFINED in `src/providers/llm_provider.py:79`
(`_LLM_SEMAPHORE`) — the SAME object F01 fixes. "Same object" is TRUE but the fix LOCATION is
mislocated (llm_provider.py, not openrouter_client.py). **Correction:** F16 must cite
llm_provider.py for the cap change; the openrouter line is acquire-only. Confirm.

### PARTIAL-REFUTE (auditor overstated the mechanism)

**R-F05/F10 collision.** Auditor claims F05 and F10 "both touch native_gate_b_inputs.py" so
the serialize-set misses the collision. I grepped: native_gate_b_inputs.py is imported by
required_entity_ledger.py, coverage_binder.py, sweep_integration.py — NOT by report_redactor.py
or provenance_generator.py (F10's fix files per the master-list text). So the "both edit
native_gate_b_inputs.py" mechanical claim is NOT supported. **However** the ordering/gating
dependency is logically real: once F05 lands, many non-VERIFIED verdicts flow into the redactor,
exercising F10's seam hard — so F10 SHOULD land before/with F05. My disposition: REFUTE the
file-collision mechanism; KEEP the within-wave ordering note (F10 before F05) as a lock item.
Confirm.

**A3 'w'-mode log overwrite (auditor severity P2).** Ledger A3 (line 27-30) names the `'w'`-mode
run-LOG overwrite on a deterministic run_dir; the RESUME PATH (line 147) prescribes re-running the
SAME query with the SAME --out-root, which triggers the overwrite. F04 covers checkpoints/resume;
F23 covers atomic FINAL artifacts. Neither explicitly closes the resume-triggered run-LOG overwrite.
My disposition: PARTIAL GAP — atomic-write intent is mostly in F23/F04 but the specific
resume-triggered run-LOG overwrite is unnamed. Confirm whether this needs its own line or a
one-clause addition to F04.

## YOUR TASKS (§-1.1 line-by-line, §-1.3 weight-not-filter)
1. CONFIRM / REFUTE / DUP each item above against the REAL code + ledger (cite file:line).
2. Independently scan the source forensics for any chokepoint with NO [F##] that ALL of us missed
   (a bounded fresh pass — the prior verdict's `biggest_residual_gap` = post-composition/multi-query/
   clinical is `completable_only_by_running`; that structural blind spot stands).
3. CERTIFY: is the master fix-list COMPLETE (every distinct chokepoint mapped) and SOUND (no fix
   RELAXES a faithfulness gate — strict_verify/NLI/4-role/D8/span-grounding — or INTRODUCES a new
   chokepoint)? The one relaxation candidate is F03-as-written + run_gate_b.py:1789 (S-F03).

## OUTPUT — write to `.codex/I-arch-004/completeness/codex_master_fixlist_gate.txt` AND emit:
```yaml
verdict: COMPLETE_AND_SOUND | GAPS_OR_ERRORS_REMAIN
confirmed_gaps: [ {finding, severity, must-add-as: F##} ]
confirmed_spec_errors: [ {fix_id, problem, correction} ]
refuted_or_dup: [ ... ]
faithfulness_safety: <one line: does ANY fix relax a gate or introduce a chokepoint? cite F## or none>
remaining_to_lock: [ <what to edit in the master list before execution> ]
convergence_call: continue | accept_remaining
```
Loose prose verdict is rejected — emit the schema. Verdict is parsed from the LAST `verdict:` line.
