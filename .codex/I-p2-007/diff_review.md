# Codex DESIGN+DIFF review — I-p2-007 (#746): Proof Replay split-view (CENTERPIECE)

HARD ITERATION CAP: 5. iter 2 (iter-1 P1 token-string-filter + P2 stale-selection + a11y-label fixed). APPROVE iff zero P0/P1 (code + design rubric, esp. HONESTY + a11y). Final line MERGE AUTHORIZED if mergeable. Canonical-diff-sha256 `294b59c19f8d305915e13db910881153125d0e584472a583fc5e8a24b8efe7f3`. web/ only.

## Design-audit note
The identical click→span interaction was screenshot-verified earlier this session on the #734 branch (production standalone harness, real fixture); #746 is the clean reusable extraction using the shared resolveSpan. The full PAGE screenshot audit happens at #756 (which wires this to a real run). Audit code + rubric honesty/a11y here.

## Diff
- NEW web/components/proof_replay/proof_replay.tsx: split-view. LEFT = role=list of buttons (claims grouped by section, line-clamp-2, verified dot, aria-current selection, focus-visible /70). RIGHT = aria-live="polite" proof pane. flatten() builds claims; default selects first. ProofPane: verifier_pass→VerdictChip VERIFIED else neutral UnverifiedBadge; per token resolveSpan → null token / null source / empty tokens / null quote ALL show honest notes; only renders SourceCard when span.source non-null + the exact quote in a blockquote.
- Composes #743 resolveSpan, #745 SourceCard, #744 VerdictChip.

## Review focus (rubric: provability/HONESTY, a11y, responsive, code)
1. HONESTY: every degenerate case (malformed token, missing source, empty tokens, null quote) shows an honest note, NEVER synthetic proof or a crash? (brief iter-1 P1)
2. a11y: list semantics + aria-current (not mixed aria-selected); proof pane aria-live; keyboard nav + focus-visible; selected accent.
3. Responsive: md:grid-cols-2 → stacked ≤768; the dense split at mobile + 400% reflow.
4. verifier_pass binary not over-mapped to richer verdicts? Any P0/P1.

## Output schema
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
merge_decision: MERGE AUTHORIZED | DO NOT MERGE
```
