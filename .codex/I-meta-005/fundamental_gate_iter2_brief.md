HARD ITERATION CAP: 5 per document. This is iter 2 of 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

# Codex gate iter 2 — fundamental re-architecture plan, the iter-1 OVERCLAIMS corrections applied

iter 1 = OVERCLAIMS (direction right, wedge preserved, gap-9-is-rewire confirmed, phase plan sound, thin-field risk
real — but the source model overclaimed universality + the grep-gate wasn't a proof). All corrections now applied to
docs/polaris_fundamental_rearchitecture_plan.md (READ §2 + §2's gates). Output YAML verdict FIRST.

```yaml
verdict: APPROVE | REQUEST_CHANGES
corrections_landed: [...]
remaining_issues: [...]
honest_one_line: "<for the operator>"
```

## The 4 iter-1 corrections — confirm each landed:
1. **OpenAlex `is_peer_reviewed`** removed; peer-review now INFERRED from `is_core` + venue `type` + Crossref
   peer-review metadata (signal A). Confirm no `is_peer_reviewed` flag is claimed.
2. **PSL downgraded** from "government-authority grammar" to a DNS-suffix PRE-FILTER; ROR institution-type is now the
   load-bearing official-source signal (it resolves canada.ca/bundesbank.de/rbi.org.in which PSL misses); issuer-
   self-description backstops (signal B). Confirm PSL is no longer claimed as the authority grammar.
3. **Over-fit gate** replaced with a CALIBRATED AUTHORITY CONTRACT (4 parts): no literal hosts/suffixes/platform-
   strings in CODE (PSL/ROR/OpenAlex/junk-patterns loaded as VERSIONED EXTERNAL DATA); zero-host grep over code only;
   explicit `authority_confidence` per source (thin-field → LOW-CONFIDENCE, not mislabeled); adversarial thin-field
   fixtures. Confirm the grep is no longer claimed as sufficient proof.
4. The band-aid risks Codex flagged (medium.com/@ + linkedin.com/pulse literals, PSL suffix literals) are now covered
   by "no literals in code, load as versioned data."

## Your ruling
APPROVE iff the 4 corrections landed cleanly (universality no longer overclaimed; grep replaced by the calibrated
contract; data-not-code for all source knowledge) and no new P0/P1. This commits to docs/ + opens the build issue on APPROVE.
