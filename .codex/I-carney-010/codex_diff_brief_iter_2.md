HARD ITERATION CAP: 5 per document. This is iter 2 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

# I-carney-010 diff iter 2 — Codex iter-1 P1 + P2 fixes

## Iter-1 verdict recap

Iter-1 returned `verdict: REQUEST_CHANGES` with 1 P1 + 3 P2. All P1 + the
2 doc-P2 are fixed in commit (this diff). P2-1 deferred as a follow-up task
(Codex explicitly said docs disclosure is enough to not block).

## P1-1 (continuing) — README "No US company anywhere" contradiction ✅ RESOLVED

**Iter-1:** `infra/vexxhost/README.md:8` said "**No US company anywhere in
the runtime path.**" immediately after making Serper (US) a required search
provider — a direct contradiction.

**Fix:** Replaced with scoped language:
> **Sovereignty posture:** the LLM inference path and the generated report
> data run on Canadian / non-US infrastructure (Vexxhost orchestrator + OVH
> H200 inference). Serper web search is the one disclosed US exception in
> the runtime path — see §4 of `docs/transparency.md` for the rationale and
> what Serper does/does not see.

## P2-2 — transparency.md §4 understated what Serper sees ✅ RESOLVED

**Iter-1:** the disclosure framed Serper exposure as just "keyword → URL/
snippet" and omitted that Serper logs request metadata.

**Fix:** added an explicit paragraph to `docs/transparency.md` §4:
> What Serper receives: the search query string itself, plus the normal
> request metadata any HTTP API call carries — the API account/key, source
> IP, timestamp, and user-agent — which Serper's privacy policy
> (serper.dev/privacy) describes it logging as system/access activity. What
> Serper does NOT receive: the uploaded corpus, the evidence pool, the
> generated report, or any operator-entered content.

## P2-3 — README asserted unverified legal entity ✅ RESOLVED

**Iter-1:** `infra/vexxhost/README.md:134` said `US (Serper / thatware LLC)`
— "thatware LLC" was an unverified entity name (effectively a fabrication).
Codex noted Serper's Terms specify UK governing law.

**Fix:** dropped the unverified entity name. Now:
> US-based search API (legal entity not independently verified; Serper's
> Terms at serper.dev/terms specify the governing law)

Honest, no overclaim — states what is known (US-based service) and
explicitly flags what is NOT independently verified (the entity + the
governing-law jurisdiction, deferring to Serper's own Terms).

## P2-1 (deferred — follow-up task created, NOT in this diff)

**Iter-1:** `/transparency` JSON exposes `google.serper.dev` as a bare
allowlist host, not flagged as a US disclosed-exception provider. A
machine-readable `provider_jurisdiction` / `egress_providers` field would
improve automated auditability.

**Disposition:** Codex iter-1 explicitly said "Docs are enough to avoid
blocking." Deferred to a follow-up task (TaskCreate #320) — adding the JSON
field is a `src/polaris_v6/api/transparency.py` change + test, out of scope
for this docs/config revert. The docs disclosure (transparency.md §4 +
README + runbook + egress_allowlist header) is the human-readable surface;
the machine-readable field is an enhancement, not a correctness fix.

## Diff

`.codex/I-carney-010/codex_diff.patch` — refreshed, canonical-diff-sha256
trailer updated. Still config + docs ONLY, zero `src/` change.

## Direct question iter 2

1. P1-1 + P2-2 + P2-3 resolved as above. P2-1 deferred per your own
   "docs are enough to avoid blocking." Anything else blocking APPROVE?

## Output schema

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
p3_cosmetic: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```
