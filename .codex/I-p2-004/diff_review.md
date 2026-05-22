# Codex DESIGN+DIFF review — I-p2-004 (#743): citation chip + resolver

HARD ITERATION CAP: 5. iter 4 (iter-3 P1: touch via pointerType on pointerdown). APPROVE iff zero P0/P1 (code + design rubric). Final line MERGE AUTHORIZED if mergeable. Canonical-diff-sha256 `404155feae6f322fe53fbc903a01c2f6225110ac9db3b6a75b673566d45c5456`. web/ only.

## Design-audit note (component, no standalone page)
The chip has no page yet → its VISUAL renders in context on the report/Proof-Replay page (#756), where it'll get the full screenshot design audit. Here, audit: code correctness, the resolver no-synthetic-proof contract, and the chip's a11y/token usage from the code.

## Diff
- NEW web/lib/evidence_span.ts: resolveSpan(token, evidencePool) — parseProvenanceToken → sources.find(s=>s.source_id===id) (ARRAY) → full_text.slice(start,end) ONLY when source+full_text present AND 0<=start<=end<=len; else quote=null (honest, no clamp).
- NEW web/components/citation/citation_chip.tsx: base-ui Tooltip (hover+focus+touch+Esc), chip = tier-dot (--tier-1/2/3) + mono id/index, min 24px target, focus-visible ring /70; source card shows EXACT untruncated quote (max-h scroll) OR honest "span not renderable" fallback; Canada-red --primary url link.

## Review focus (rubric: provability/honesty, a11y, visual, code)
1. resolveSpan contract: array lookup + ALL null-guards correct (no synthetic partial proof)? matches the #756 inspector's future reuse?
2. chip a11y: hover AND focus AND touch open; 24px target; focus-visible; aria-label; no color-only (tier dot + text).
3. exact span untruncated (NOT the evidence-tooltip 240-char truncation)?
4. Any P0/P1 (incl. base-ui Tooltip needing a Provider ancestor at the consuming page — flag if so).

## Output schema
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
merge_decision: MERGE AUTHORIZED | DO NOT MERGE
```
