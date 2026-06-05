# Codex DIFF-gate — I-ready-013 (#1080): clinical/benchmark verified-only surface (clinical-safety, §-1.1)

```
HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## REVIEW ONLY — DO NOT MODIFY ANY FILE
Return ONLY the YAML verdict. **Do NOT edit/create source or test files, do NOT write a patch.** You
are the independent reviewer of an already-committed diff; author and reviewer must stay separate.

## What this is
The committed diff for #1080 (brief-gate already APPROVE'd: fix A_force_off). Patch:
`.codex/I-ready-013/codex_diff.patch`. Branch `bot/I-ready-013-analyst-synthesis-verified`, HEAD diff
commit `d08b09eb`. Files: `multi_section_generator.py`, `run_honest_sweep_r3.py`, `run_gate_b.py`, the
Gate-B slate test, + two verified-only test files.

## The fix
The benchmark + any clinical run appended ~1500-3000 words of un-span-verified Analyst Synthesis to
report.md (planner default-off + `PG_SWEEP_ANALYST_SYNTHESIS` default-on + Gate-B set neither). Now:
- `generate_multi_section_report` gains `suppress_analyst_synthesis: bool = False` + an explicit
  `analyst_synth_enabled` (`PG_SWEEP_ANALYST_SYNTHESIS`) check, both ANDed into the analyst-block gate.
- `run_one_query` sets `_clinical_verified_only_surface = (domain == "clinical")` and passes it as the
  suppressor (covers pipeline-B UI via `_infer_domain` medical/health/pharma -> clinical).
- Gate-B slate sets `PG_SWEEP_ANALYST_SYNTHESIS=0` via a force-EXACT mechanism + a fail-closed
  preflight that aborts if it is on.

## Verify (§-1.1 — this is the faithfulness surface)
1. **Faithfulness machinery UNCHANGED** — strict_verify / 4-role D8 / provenance / two-family NOT
   touched; this only gates WHICH synthesis layer ships, never the verification.
2. **Clinical/benchmark provably ships verified-only** — with the Gate-B slate or any clinical domain,
   the analyst-block gate evaluates false → no unverified layer in report.md; the preflight blocks a
   benchmark run if the flag is somehow on.
3. **No OVER-suppression (the regression risk)** — non-clinical / off-mode default (param omitted, flag
   on, planner off) keeps the legacy unverified layer BYTE-IDENTICAL. Confirm the default is False and a
   non-clinical domain does not trip the force-off.
4. **Gate-B mechanism correctness** — force-EXACT sets the flag to "0" (not "1"); the preflight aborts
   loudly; the slate test is kept in sync.
5. **UI path** — `_infer_domain` maps medical-family apps to "clinical"; a non-medical app is NOT
   coerced to clinical.

## Smoke evidence (offline, $0)
- 24 verified-only tests green (5 source-pin + 19 Claude-authored behavioral/negative incl. suppress-
  wins, env-kill, NON-clinical-PRESERVED-byte-identical, default-param, domain matrix, UI).
- Full `tests/dr_benchmark/` suite 272 passed. py_compile clean.

## Provenance (full disclosure)
The initial implementation was produced by the brief-review codex-exec agent (it over-stepped into
editing). I (Claude) reviewed it line-by-line, verified faithfulness-safety + correct scoping, authored
the behavioral/negative tests, and committed it as the diff under review. You are the fresh independent
reviewer — please review it on its merits regardless of origin.

## Output schema (required)
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
faithfulness_machinery_untouched: yes | no
non_clinical_byte_identical: yes | no
```
