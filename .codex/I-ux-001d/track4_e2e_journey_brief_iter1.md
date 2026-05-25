# Codex e2e click-through journey audit — I-ux-001d TRACK 4 (iter 1)

## §0 cap (verbatim CLAUDE.md §8.3.1)
HARD ITERATION CAP: 5. APPROVE iff zero P0/P1.

## Scope
TRACK 3 LOCKED iter-4 APPROVE on 12 desktop page specializations. TRACK 4 audits the e2e narrative coherence when these are stitched into the **demo critical-path journey**, in the order PM Carney's office will walk through:

1. **/home** — operator lands, sees proof-as-CTA hero (real verified clinical claim)
2. **/intake** — types the research question in plain English
3. **/source_review** — POLARIS proposes the corpus, operator approves/amends/refuses
4. **/plan** — POLARIS proposes the section plan, operator approves/amends/refuses
5. **/runs/[runId]** — operator monitors live event stream + depth-checklist
6. **/inspector/[runId]** — operator reads the verified brief (the CENTERPIECE), claims their proof
7. **/compare** — operator does a follow-up comparison (claim-anchored)
8. **/runs/[runId]/graph** — operator explores the knowledge graph (compounding snowball)

## What I want from this audit

1. **Journey coherence.** Does each step lead naturally to the next? Are the entry/exit affordances on each page consistent with where the previous/next page expects to come from/go to?
2. **Proof-as-hero through-line.** Does the verification/proof story carry across all 8 pages, or does it disappear in the middle and only reappear at Inspector?
3. **Trust gates visible at every step.** At each page, can the operator see what's verified, what's not yet, what was declined, what was refused? (Intended-use strip visible everywhere is the floor.)
4. **PM Carney's office angle.** A PM's office reviewer is a non-clinical sophisticated reader. Do the 8 pages tell a story that justifies investment in POLARIS without requiring the reviewer to be a physician?
5. **Frontier comparison.** Compared to Perplexity Spaces, ChatGPT Deep Research, Gemini Deep Research, Elicit/Consensus/Scite/OpenEvidence/FutureHouse — does this journey beat them on the proof axis? Where does it still leak?
6. **TRACK 4 ready to sign off?** If APPROVE → TRACK 5 (only if flagged, which it isn't post-track-3-iter-4) → sign-off → handoff to I-ux-001c.

## Output schema

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
p3: [...]
convergence_call: continue | accept_remaining
track_4_ready_to_signoff: yes | no | with_caveats
specific_check_responses:
  journey_coherence: PASS | FAIL_with_detail
  proof_as_hero_through_line: PASS | FAIL_with_detail
  trust_gates_visible_per_step: PASS | FAIL_with_detail
  pm_office_angle: PASS | FAIL_with_detail
  frontier_comparison: notes_summary
```
