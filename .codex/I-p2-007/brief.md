# Codex BRIEF review — I-p2-007 (#746): Proof Replay split-view (CENTERPIECE component)

HARD ITERATION CAP: 5 per document. This is iter 2 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — reserve P0/P1 for real execution risks; cosmetics → P2/P3.
- If iter 5 returns REQUEST_CHANGES, force-APPROVE on non-P0/P1; do not bank for iter 6.
- Surface held-back findings now.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

## Task
The Proof Replay split-view — POLARIS's CENTERPIECE differentiator: click a verified claim → see the EXACT cited source span. A reusable component (#756 page wires it to a real run).

## Verified current state (grounded)
- Data: `VerifiedReportSectionShape { section_id, section_title?, verified_sentences[] }`; `VerifiedSentenceShape { section_id, sentence_text, provenance_tokens: string[], verifier_pass: boolean }` (inspector_bundle_loader.ts:58-70). Verdict here is BINARY verifier_pass (the 7-verdict vocab is the separate §-1.1 audit layer — do NOT invent richer per-sentence verdicts).
- Reuse: resolveSpan (web/lib/evidence_span.ts #743), SourceCard (#745), VerdictChip (#744), CitationChip (#743).
- The current verified_report_sections.tsx only TOGGLES raw tokens (no click→span). The #734 branch built click→span INLINE + unmerged; #746 supersedes it as the proper reusable component using the now-shared resolveSpan.
- #742 tokens; G-RESP responsive matrix.

## Acceptance criteria (diff implements; brief reviews the plan)
1. `web/components/proof_replay/proof_replay.tsx`: props = sections (VerifiedReportSectionShape[]) + evidencePool. Split view: LEFT = claim list (verified sentences, grouped by section, selectable, keyboard-navigable, each shows a VERIFIED/unverified chip from verifier_pass); RIGHT = the selected claim's proof — for each provenance_token, resolveSpan → SourceCard + the EXACT span quote (honest fallback when resolveSpan quote=null; NO synthetic proof).
2. Selection: clicking/Enter on a claim selects it; selected state visible + announced (aria-current/aria-selected); default = first claim selected (or none with a prompt).
3. Responsive (G-RESP): two-pane on desktop, STACKED (list above proof) ≤768; no horizontal scroll; 400% reflow.
4. a11y: list = keyboard-navigable (roving tabindex or buttons), proof pane labeled (aria-live or aria-labelledby tied to the selected claim), focus-visible.
5. Honest: verifier_pass→VERIFIED chip; unverified shown honestly; unresolved span → honest fallback. Frontier-Minimal, Canada-red selected accent.

## Files I have ALSO checked and they're clean
- web/lib/inspector_bundle_loader.ts (the shapes), web/lib/evidence_span.ts (#743 resolver), web/components/source/source_card.tsx (#745), web/components/verdict/verdict_chip.tsx (#744), web/components/citation/citation_chip.tsx (#743), web/components/inspector/verified_report_sections.tsx (the old toggle-only render this supersedes).

## Review focus
1. Split-view interaction model sound (selection state, keyboard nav, default selection)? Any a11y gap (list semantics, the proof pane as a live/labelled region)?
2. resolveSpan reuse correct; honest fallback on null quote (no synthetic proof)?
3. Responsive stack ≤768 + 400% reflow plan; the dense split-view at mobile.
4. Does it correctly NOT invent verdicts beyond verifier_pass? Any P0/P1.

## Output schema
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
```

---
## iter-2 corrections (all iter-1 findings folded)
- **P1 (null guards before SourceCard):** the proof pane MUST guard: if resolveSpan(token)===null → honest "Unresolvable provenance token" note (skip SourceCard); if span.source===null → honest "Source not in this bundle" note (skip SourceCard); only render SourceCard when span.source is non-null. A malformed token NEVER crashes the centerpiece — it shows the honest fallback.
- **P2 (verifier_pass=false):** render a NEUTRAL "Unverified" badge (muted token), NOT a VerdictChip value (UNSUPPORTED/PARTIAL imply the richer §-1.1 audit verdicts which this binary field is not). verifier_pass=true → VERIFIED (VerdictChip or a verified badge).
- **P2 (empty provenance_tokens):** if a selected claim has provenance_tokens.length===0 → honest note "No provenance tokens recorded for this claim" (proof pane never blank).
- **P2 (coherent a11y):** the claim list uses a SINGLE coherent pattern — buttons with `aria-current="true"` on the selected one (not aria-selected mixed onto plain buttons); roving focus / standard tab order; the proof pane is `aria-live="polite"` + labelled by the selected claim.
Re-confirm APPROVE or list only true remaining P0/P1.
