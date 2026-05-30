RULE NOW — emit the YAML verdict block FIRST. VERIFY each claim below by READING the cited files
(this is a §-1.1 line-by-line verification, not a rubber-stamp). Do NOT trust my summary — check the code.

HARD ITERATION CAP: 5. This is iter 1 of 5. Front-load all findings. Reserve REFUTED for claims the code
actually contradicts.

## Output schema (emit FIRST)
```yaml
verdict: APPROVE | REQUEST_CHANGES
claim_verdicts:
  C1_depth_cap_and_unwired_deepener: CONFIRMED | PARTIAL | REFUTED
  C1_no_clinical_backend: CONFIRMED | PARTIAL | REFUTED
  C2_retrieval_tracking_presence_only: CONFIRMED | PARTIAL | REFUTED
  C4_contradiction_numeric_only: CONFIRMED | PARTIAL | REFUTED
  C4_four_role_gate_off_by_default: CONFIRMED | PARTIAL | REFUTED
  C5_citation_leak_ev_token: CONFIRMED | PARTIAL | REFUTED
  C6_kg_write_only_dead_reuse: CONFIRMED | PARTIAL | REFUTED
fix_list_priority_correct: yes | no
p0_corrections: [...]   # any claim that is materially wrong AND would misdirect the fix work
notes: [...]
```

# Codex verification — Q1 capability-readiness audit (#941). VERIFY the load-bearing claims that drive the pre-Q1 fix list. NO SPEND.

A Claude Codex Workflow (6 grounded agents) audited POLARIS Q1 capability vs frontier DR (Gemini 3.1 Pro
DR, ChatGPT 5.5 Pro DR). The full report is `.codex/I-meta-002-q1c/capability_audit_report.md`. Before
we file fix issues + tell the operator Q1 is "READY-WITH-GAPS", VERIFY these load-bearing claims by
reading the actual code. Each, if true, drives real work — so confirm or refute precisely.

## Claims to verify (read the files)
1. **C1 — depth cap + unwired deepener.** `scripts/run_honest_sweep_r3.py` defaults
   `PG_SWEEP_FETCH_CAP=20` (≈line 1591-1593) so the launch sweep tops out ~20 sources/question. AND the
   real depth engines — `src/polaris_graph/agents/evidence_deepener.py` (150-cap citation snowball) and
   the agentic searcher in `src/polaris_graph/state.py`/`searcher.py` (12-round/~96-query, STORM) — are
   wired ONLY into `src/polaris_graph/graph.py` (Pipeline B), with ZERO references in
   `run_honest_sweep_r3.py`. VERIFY: grep `run_honest_sweep_r3.py` for `deepen_evidence|evidence_deepener|
   execute_searches|agentic` → should be zero. Confirm the cap and the non-wiring.
2. **C1 — no clinical backend.** `src/polaris_graph/retrieval/domain_backends.py` (~line 370-385) has NO
   clinical branch (comment "clinical: rely on generic Serper + S2"); no PubMed/ClinicalTrials.gov/Cochrane.
3. **C2 — retrieval tracking is presence-only.** `src/polaris_graph/benchmark/pathB_capture.py:142-151`
   `record_retrieval_attempt` stores only backend NAME strings in a set (no per-call query/return-count/
   URL ledger), vs the per-call `reasoning_trace.jsonl` LLM roles get.
4. **C4 — contradiction detector is numeric-regex only.** `src/polaris_graph/retrieval/
   contradiction_detector.py` (~575-651) extracts (subject,predicate,value,unit) and flags numeric gaps
   only; qualitative/directional conflicts (contraindication present-vs-absent etc.) are invisible. It IS
   wired unconditionally into the sweep (`run_honest_sweep_r3.py:~2075-2087`).
5. **C4 — 4-role gate off by default.** `run_honest_sweep_r3.py:~3214-3240` fires the 4-role seam ONLY
   when `PG_FOUR_ROLE_MODE` truthy AND a transport is injected; default sweep runs the legacy evaluator path.
6. **C5 — citation-integrity leak.** `src/polaris_graph/generator/analyst_synthesis.py:~107` scrub regex
   `\[#ev:[^\]]*\]` matches only the `[#ev:...]` form, NOT bare `[ev_NNN]`, so a dangling `[ev_012]` can
   leak into the published report. (Check the regex; the leaked-artifact claim is from one run's report.md.)
7. **C6 — KG is write-only (dead reuse).** `src/polaris_graph/memory/verified_claim_graph.py`
   `query_related_claims`/`find_contradictions` are referenced ONLY by the store + its test — grep `src/`
   → nothing reads the reuse pool back into generation; the only writer
   (`roles/sweep_integration.py` run_four_role_evaluation) writes then closes. So zero runtime snowball reuse.

## Also rule on
- Is the Tier-A fix list priority correct (deepener-wiring + fetch-cap raise + qualitative-conflict path
  as the top 3)? Any claim materially wrong that would misdirect the work?

APPROVE iff the load-bearing claims are CONFIRMED (or PARTIAL with the core true) and the fix priority is
sound. REQUEST_CHANGES with `p0_corrections` if any claim is REFUTED in a way that changes the fix work.
