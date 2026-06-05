# Brief — I-ready-013 (#1080): Analyst Synthesis unverified user-facing surface (clinical-safety, §-1.1)

```
HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## HARD CONSTRAINTS (operator-locked, NOT consultable)
- **The benchmark/clinical shipping path MUST ship ONLY span-verified prose.** No un-span-verified interpretive layer in the §-1.1 / BEAT-BOTH faithfulness path. This is the whole point of the fix.
- **Faithfulness invariants UNCHANGED**: strict_verify, 4-role D8, provenance tokens, two-family. This change only controls WHICH synthesis layer ships; it does not touch the verification machinery.
- **Flag-gated + flag-OFF byte-identical** where a flag is introduced. The LOCKED 5-question DRB-EN benchmark behavior change (dropping the unverified layer) is the INTENDED effect, not a regression — but it must be a clean, reviewed change.

## The finding (F15, Codex-found) — CONFIRMED BY GROUND TRUTH (not paper)
POLARIS ships a two-layer report: (1) the span-verified multi-section prose (audit-grade), then (2) an
"Analyst Synthesis" interpretive layer (`src/polaris_graph/generator/analyst_synthesis.py`, ~1500-3000
words) appended to `report.md` at `run_honest_sweep_r3.py:4237-4244` with a disclosure header. **Layer 2
is NOT span-verified / NOT 4-role-gated** — it's the unverified interpretive layer by design.

**Why it is LIVE in the benchmark (verified, file:line):**
- The unverified analyst block runs iff `not partial_mode AND research_plan is None AND PG_SWEEP_ANALYST_SYNTHESIS=1` (`multi_section_generator.py:5093-5098` + `analyst_synthesis.py:441`).
- `PG_USE_RESEARCH_PLANNER` defaults **"0"** (`run_honest_sweep_r3.py:2021-2025`) → `_research_plan = None`.
- `PG_SWEEP_ANALYST_SYNTHESIS` defaults **"1"** (`analyst_synthesis.py:441`).
- **Gate-B (`run_gate_b.py`) sets NEITHER flag** → the benchmark runs planner-OFF with the unverified
  analyst block ACTIVE → **the locked DRB-EN benchmark currently appends ~1500-3000 words of
  un-span-verified interpretive prose to every report.md.**

**§-1.1 risk:** in a clinical context, even hedged/disclosed interpretive commentary that is NOT
span-verified can contain a fabricated dose / contraindication / population a reader acts on. It ALSO
undermines the BEAT-BOTH faithfulness claim (a §-1.1 line-by-line audit of report.md would flag
unverified claims in the analyst section as UNSUPPORTED). Severity P1 (clinical/launch surface).

**Important honest nuance — a VERIFIED replacement already exists (planner-ON only):** when
`PG_USE_RESEARCH_PLANNER=1`, the planner outline includes a VERIFIED "Integrative" cross-cutting
synthesis section (`multi_section_generator.py:99` + `:5086-5092`, I-meta-005 Phase 6 #990) that is
strict_verify'd (emits [ev_XXX], ungrounded sentences DROPPED, counts toward verified_words), AND the
unverified analyst block is AUTO-DEMOTED. So a verified synthesis layer is already built — it just
isn't active in the benchmark (planner-off).

## Proposed fix (route the granularity to you)

**DECISION 1 — primary approach (my lean: A):**
- **(A) Make the clinical/benchmark path ship ONLY span-verified prose** — disable the unverified
  analyst block there. Gate-B sets `PG_SWEEP_ANALYST_SYNTHESIS=0` (in its force-flags slate), AND the
  clinical domain forces it off in `run_one_query` (so any clinical run, not just Gate-B, drops the
  unverified layer). Report ships the verified multi-section prose only. Minimal diff, §-1.1-safe,
  flag-gated; the unverified two-layer feature stays available for non-clinical length-gap use behind
  the existing default-ON flag. **My lean** — faithfulness is the wedge; "length is liability in
  clinical"; this cleanly makes the BEAT-BOTH report 100% span-verified.
- **(B) Activate the VERIFIED Integrative replacement in the benchmark** (Gate-B sets
  `PG_USE_RESEARCH_PLANNER=1`) → verified Integrative synthesis ships + unverified block auto-demotes.
  Richer (keeps a synthesis layer, fully verified) BUT turning the planner ON reshapes the whole
  benchmark outline — a much larger behavioral change to the LOCKED 5-question benchmark that needs its
  own validation; risky to bundle here.
- **(C) Verify the analyst synthesis in place** (NLI/entailment pass dropping unverified sentences) —
  new code, heavier, and the 4-role/strict_verify path already does this for real sections; redundant.

My recommendation: **ship (A) now** (the §-1.1-safe minimal fix that guarantees the benchmark/clinical
report is fully span-verified), and treat **(B)** — planner-on verified-Integrative in the benchmark —
as a separate, larger, independently-validated follow-up (it is the richer long-term answer but not a
1-issue change). Your call on A vs B vs C, and on whether the clinical-domain force-off (not just
Gate-B) is in scope here.

**DECISION 2 — UI path (api/intake → web report):** does the same unverified layer reach the
pipeline-B UI report surface, and should this fix cover it now or defer? (My lean: the benchmark/
clinical run path is the priority + the §-1.1 surface; the UI consumes the same report.md producer so
(A)'s clinical force-off covers it, but confirm.)

## Smoke (offline, $0, deterministic)
- Flag/mode matrix at the generator boundary: assert that with the clinical force-off / Gate-B slate,
  the unverified analyst block does NOT run (the `research_plan is None AND PG_SWEEP_ANALYST_SYNTHESIS`
  gate evaluates false) → `analyst_synthesis_text == ""` → report.md has NO Analyst Synthesis section.
- OFF-mode default (non-clinical, flag unset) byte-identical: the unverified block still runs (feature
  preserved for non-clinical length use).
- Gate-B slate asserts `PG_SWEEP_ANALYST_SYNTHESIS=0` is set (the benchmark ships only verified prose).
- No faithfulness machinery touched (strict_verify / 4-role / provenance imports unchanged).

## Files I have ALSO checked
- `multi_section_generator.py:5093-5098` — the exact demote gate (`research_plan is None`).
- `run_honest_sweep_r3.py:2021-2025` — `PG_USE_RESEARCH_PLANNER` default "0"; `:4237-4244` — the
  report.md append site for the unverified layer.
- `analyst_synthesis.py:441` — `PG_SWEEP_ANALYST_SYNTHESIS` default "1"; the existing scrub guardrails
  (no [#ev] tokens, fail-closed negation-safety drop).
- `run_gate_b.py` — sets NEITHER flag (the root cause the benchmark ships the unverified layer).
- `multi_section_generator.py:99,5086-5092` — the VERIFIED Integrative section (#990), planner-on only.

## Output schema (required)
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
fix_choice: A_force_off | B_verified_integrative | C_verify_in_place | other
clinical_force_off_in_scope: yes | no
cover_ui_path_now: yes | defer
```
