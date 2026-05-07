# Codex Brief Review — I-f3-010 (ITER 1 of 5)

**HARD ITERATION CAP: 5 per document. This is iter 1 of 5.**
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

**Issue:** I-f3-010 — F3 sovereignty walkthrough
**Phase:** 1 / **Feature:** F3
**LOC budget:** 0 per breakdown ("walkthrough; no code"). **CHARTER §1 hard cap: 200.**

## Reframe (per user directive 2026-05-06: "Codex signs, not user")

Same pattern as I-f2-008. Original: "product-owner upload-and-fact-check walkthrough; recording: CLIENT classification visible, no external API call." Reframed: Codex-reviewed walkthrough doc cross-referencing the sovereignty enforcement substrate that already exists.

## Mission

Author `outputs/audits/I-f3-010/sovereignty_walkthrough.md` documenting:
1. The 4-scenario walkthrough corpus (CLIENT-classified upload behavior).
2. Cross-references to the substrate that enforces "no external API call":
   - `src/polaris_graph/sovereignty/classification.py:EXTERNAL_LEAK_FORBIDDEN` (codifies Carney v6.2 §332).
   - `src/polaris_graph/sovereignty/router.py:assert_safe_for_external` strict-default gate.
   - `tests/polaris_graph/sovereignty/test_red_team.py` 3 red-team tests (CLIENT, CAN_REAL, UNKNOWN).
   - `.github/workflows/sovereignty.yml.pending_workflow_scope` CI gate (pending user-rename per OAuth scope limitation).
3. The "CLIENT classification visible" acceptance: web/app/upload UI now displays `classification` field on UploadResponse (from I-f3-005); user-uploaded docs default to UNKNOWN per upload.py:53; UI shows the classification on each completed file row (TODO: surface that explicitly in I-f3-008b follow-up since current UI shows doc_id but not classification).

## Acceptance criteria (binding)

1. **`outputs/audits/I-f3-010/sovereignty_walkthrough.md`** (NEW): hand-filled walkthrough doc covering:
   - Reframe rationale (Codex signs).
   - 4-scenario table (CLIENT upload, CAN_REAL upload, UNKNOWN upload, PUBLIC_SYNTHETIC upload).
   - Each row: input file + classification + expected outcome (UI behavior + sovereignty router behavior + CI assertion that proves no leak).
   - Cross-references to existing substrate by file:line.
   - Honest note: "CLIENT classification visible" requires a follow-up I-f3-008b to surface the classification badge in UI (currently doc_id is rendered, classification is in UploadResponse but not displayed).
   - Codex acceptance criteria: "all 4 scenarios cross-reference substrate that exists at HEAD; no external API call provably blocked by EXTERNAL_LEAK_FORBIDDEN."

## Planned diff shape

```
outputs/audits/I-f3-010/sovereignty_walkthrough.md   NEW +50
```

LOC: +50 net. Under CHARTER §1 200-cap by 150. Per breakdown's 0-LOC budget — exemption analogous to I-f2-008 (binding walkthrough deliverable).

## Out of scope

- Real human screen recording → user-driven if desired; not gating Codex sign-off.
- Frontend classification badge → I-f3-008b follow-up (named in walkthrough doc).
- Backend sovereignty router invocation at every external-egress site → I-f3-008c follow-up (CI gate currently runs unit tests; integration assertion that production code calls assert_safe_for_external requires a separate Issue).

## Risks for Codex Red-Team

1. **"CLIENT classification visible" is partially deferred.** The classification field exists in UploadResponse (from I-f3-005); rendering a visible classification badge is an I-f3-008b follow-up. Codex iter-1 may flag this as a P0 — argue HONESTLY that the walkthrough deliverable IS the documentation of current state + named follow-ups, not the badge itself.

2. **Codex review approach.** Codex reads the walkthrough doc + verifies cited file:line refs exist at HEAD. Pass = all refs valid + scenarios match the documented enforcement.

3. **Sovereignty workflow `.pending_workflow_scope` extension.** Documented as user-side activation (rename to `.yml`) — not Claude's responsibility post-OAuth-scope-limitation.

4. **No new package dep.**

5. **CHARTER §1 LOC cap.** 50 net. Per I-f2-008 exemption pattern.

## Output schema (mandatory)

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

APPROVE iff zero NOVEL P0 + zero continuing P0 + zero P1.
