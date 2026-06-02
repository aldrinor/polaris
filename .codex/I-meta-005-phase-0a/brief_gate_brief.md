HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding. Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — reserve P0/P1 for real execution risks; classify the rest P2/P3.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

# Codex BRIEF gate — Phase 0a (#983) source-authority model implementation brief

Review .codex/I-meta-005-phase-0a/brief.md (READ IT) — the implementation contract for the field-agnostic
source-authority model that replaces tier_classifier.py's named-host frozensets, behind PG_USE_AUTHORITY_MODEL
(default OFF, shadow). It is the build contract; gate it for ACCEPTANCE-CRITERIA CORRECTNESS before any code.
Output the §8.3.9 YAML verdict FIRST.

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

## What to verify (this is a BRIEF gate — is the plan correct + buildable + safe, not the code)
1. **Drop-in safety (wedge protection):** the brief claims a 3-line dispatcher at tier_classifier.py:1069, body renamed
   `_classify_source_tier_rules` byte-identical, ClassificationResult extended ADDITIVELY (4 new fields default None),
   and that the adequacy gate + evidence selector are driven 100% by the T1-T7 string so new fields are inert in 0a.
   VERIFY this is actually true (read tier_classifier.py:1069 + the consumers live_retriever.py:1789-1811, the
   adequacy gate, evidence_selector) — if a consumer reads anything but the tier string, the "wedge can't regress"
   claim is false → P0/P1.
2. **The OpenAlex wiring gap (the load-bearing finding):** brief says OpenAlexWork carries only 8 fields and does NOT
   fetch cited_by_count / summary_stats / is_core / is_in_doaj / apc_prices / ROR, and the /works query has no
   `select=`. CONFIRM (read openalex_client.py:50-59,70-115). Is the brief's plan (extend select= + dataclass +
   sqlite cache schema, OR degrade to LOW confidence when absent) sound? Web-verify the exact OpenAlex field paths
   (the brief routes 5 items to you for web-verify: is_peer_reviewed absence, summary_stats on /sources, ROR path+enum,
   PSL canonical gov-ccTLD coverage, select= nested syntax).
3. **The 4-part calibrated authority contract** is the acceptance gate (no code literals / zero-host grep / per-source
   honest LOW confidence / adversarial thin-field) — is it correctly specified + mechanically checkable?
4. **The heavy offline smoke plan (operator-mandated)** S1-S6: is it genuinely heavy + sufficient? Esp. S2 (>=95%
   clinical reproduction with hard-fail on T1<->T6 inversion) and the fixture caveat (dumps store OUTPUT not full
   INPUT signals → re-fetch OpenAlex once + freeze; reject url+title re-derivation as string-presence laundering).
   Is the no-laundering caveat correct + enforced?
5. **Scope discipline:** 0a does NOT remove tier_classifier, does NOT wire authority fields into any gate, default OFF.
   Is the scope correctly bounded (no scope creep, no premature removal that could regress the wedge)?
6. **File/folder management:** single new package src/polaris_graph/authority/ + config/authority/ versioned data +
   tests — no sprawl. Reasonable?

APPROVE iff the drop-in is genuinely wedge-safe, the OpenAlex-gap plan is sound, the 4-part contract + heavy smoke are
correctly specified, and scope is bounded. Front-load every real finding now (5-cap).
