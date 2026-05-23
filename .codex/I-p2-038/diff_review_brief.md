# Codex DIFF + DESIGN review — I-p2-038 (#821): top-tier visual overhaul. Iter 2 of 5.

HARD ITERATION CAP: 5 per document. This is iter 2 of 5.
- Front-load ALL real findings. Reserve P0/P1 for real execution/honesty risks.
- If iter 5 returns REQUEST_CHANGES, force-APPROVE on remaining non-P0/P1.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

Canonical-diff-sha256 `fa11460351276f8bfc4f4ef565b9f20115d9fbf7c083c4b57797e7bb0ef4f59c`. Operator: "Codex decide when to merge" — your
verdict is the merge gate. APPROVE → MERGE AUTHORIZED (autonomous merge).

## Iter-1 P1 (CI format_check) — FIXED
`prettier --write` (pinned local version) applied to all 4 changed files;
`npx prettier --check app/components/proof_showcase.tsx components/proof_replay/
proof_replay.tsx lib/evidence_span.ts app/intake/page.tsx` → "All matched files
use Prettier code style!" (exit 0, LF). The web_ci format_check (prettier --check
on Linux/LF) will pass for these files. Logic unchanged since iter-1.

## Recap (unchanged from iter-1, all VISUALLY VERIFIED on local build)
- evidence_span.ts: spanInContext — `span` === fullText.slice(start,end) (exact,
  faithful); before/after real adjacent text snapped to word boundaries; null on
  invalid bounds (no synthetic text).
- proof_showcase.tsx (home) + proof_replay.tsx (centerpiece): exact cited span
  HIGHLIGHTED (<mark>) in real source context; honest caption; falls back to raw
  quote if no context.
- intake/page.tsx: killed internal jargon → user-facing copy.

## Review focus
1. Confirm the format fix resolves the only iter-1 finding.
2. Any NEW issue (honesty: <mark> always === exact span? design/a11y of <mark>?).
3. Merge decision.

## Output schema
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
merge_decision: MERGE AUTHORIZED | DO NOT MERGE
```
