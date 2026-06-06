# FX-13 (#1125) diff-gate — ITER 1 of 5

```
HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## Output schema (REQUIRED — reply with EXACTLY this YAML, nothing else)

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

## Scope
P2 telemetry/diversity correctness — pure string fix; no grounding/strict_verify/4-role change. Diff:
`.codex/I-ready-017/fx13_codex_diff.patch` (vs FL-05 verified tip `b43939d5`).

## Bug — confirmed §-1.1 on the REAL held trace
`_domain_of` did `netloc.lower().lstrip("www.")`. `str.lstrip` strips any leading char in the SET
{w, .}, NOT the literal prefix. Over the held drb_72 trace's 145 URLs, **2 domains corrupted**:
`wol.iza.org → ol.iza.org` (a REAL labor-economics source, and not even a www. host) and
`www.weforum.org → eforum.org`. The domain feeds `_domain_of(cand.url)` (`:2757`) source-diversity
dedup, so two real sources were mis-bucketed. Full §-1.1: `outputs/audits/I-ready-017/fx13_s11_audit.md`.

## Fix
`lstrip("www.")` → `removeprefix("www.")` (Python 3.9+; repo 3.13) in ALL 3 identical instances:
`live_retriever.py:1901` (production), `scripts/compare_live_vs_pg_lb_sa_02.py:32`,
`scripts/run_honest_on_prerebuild_corpus.py:81`.

## Evidence
- §-1.1 on REAL held trace: 2/145 corrupted (wol.iza.org, weforum) — above.
- Offline smoke `test_fx13_domain_of_iready017.py` → 4 passed: who.int/washington.edu un-corrupted;
  `wwwhost.example.com` NOT over-stripped; subdomains/plain hosts unchanged; bad URL → ''.
- Regression: `test_live_retriever_rerank` (8) + `test_fx15b_host_filter` (5) green.

## Also checked (clean)
Other retrieval `lstrip(...)`: `qualitative_conflict_detector.py:279` (`lstrip(" :,")`),
`tier_classifier.py:624` (`lstrip("\"'([ ")`) are LEGITIMATE leading-punctuation char-set strips —
not prefix bugs, left as-is.

## Question
Is the removeprefix fix correct + complete across all 3 instances, and the other lstrip calls
correctly left alone? Anything blocking APPROVE?
