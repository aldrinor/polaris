HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding.
- Reserve P0/P1 for real execution risks; classify non-blockers as P2/P3/cosmetic.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

# Codex diff gate — I-deepfix-001 Wave C WS-9 part (a): D6 contradiction-count coherence

Review the diff `.codex/I-deepfix-001/ws9_d6a_diff.patch` (one file, scripts/run_honest_sweep_r3.py). Read the touched region for context. Repo root C:/POLARIS, read-only.

## The defect (D6, drb_72)
The contradiction disclosure printed `len(renderable_contradictions)` (which EXCLUDES records screened as `possible_metric_mismatch`) while `manifest.contradictions_found = len(contradictions)` (ALL records). So the report said "1" while the manifest said "3" — an incoherent count. In the extreme (all records withheld) the disclosure rendered NOTHING while the manifest still counted them.

## The fix (verify it does exactly this, nothing more)
In `run_one_query` (the SAME function that later sets `manifest.contradictions_found = len(contradictions)` at ~:14604), the disclosure now:
1. computes `_d6_total_detected = len(contradictions)` and `_d6_withheld = total - len(renderable)`;
2. appends a sentence to the framing paragraph disclosing the withheld count + "Total detected: N" (only when withheld > 0);
3. adds an `elif _d6_total_detected > 0:` branch so the all-withheld case still discloses the total (never silently omits it).

## Confirm
1. FAITHFULNESS-NEUTRAL: this is honest REPORTING only — no verdict, gate, threshold, or detector-logic change. The `possible_metric_mismatch` records STILL stay in `contradictions.json` (§-1.3 no-drop); nothing is dropped or added to the actual contradiction set.
2. COHERENCE: `_d6_total_detected` (= len(contradictions)) is the SAME variable/scope as `manifest.contradictions_found` (both in `run_one_query`), so the disclosed total now MATCHES the manifest. Confirm no off-by-one and that the withheld math (`total - renderable`) is correct.
3. NO REGRESSION: the existing per-flag enumeration for the renderable subset is unchanged; the new `elif` only fires when renderable is empty but total>0.
4. Is there any case where the new text prints a MISLEADING number (e.g. double-counts, or discloses a record it shouldn't)?

## Output schema (REQUIRED)
```yaml
verdict: APPROVE | REQUEST_CHANGES
faithfulness_neutral_reporting_only: true | false
disclosed_total_matches_manifest: true | false
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
```
