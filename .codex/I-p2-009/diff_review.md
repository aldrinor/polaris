# Codex DESIGN+DIFF review — I-p2-009 (#748): sovereignty proof panel

HARD ITERATION CAP: 5. iter 1. APPROVE iff zero P0/P1 (code + design rubric, HONESTY is P0-critical). Final line MERGE AUTHORIZED if mergeable. Canonical-diff-sha256 `25f29ee57ac239ec08c73e985b49d1b7bfd18665f524c31c2ef8c0c4829b51b4`. web/ only.

## Design-audit note
Display panel; visual renders in-context on report/audit pages (#759) + sovereignty integration (#762). Audit code + rubric honesty/a11y here.

## Diff
- NEW web/components/sovereignty/sovereignty_panel.tsx. (a) Sovereign processing: exact honest shell wording (Canadian, logged egress, no external AI vendor). (b) Two-family: generator+evaluator model NAMES always; "Verified" badge ONLY when familySegregationPassed===true, "Not verified" when false, nothing when undefined — never inferred from names. (c) Signed bundle: bundle_id/schema/polaris/created (only when present); "Cryptographically signed" ONLY when signature passed, else "Integrity-hashed · N files sha256 (tamper-evident)" when fileCount present, else nothing.

## Review focus (rubric: provability/HONESTY = P0, a11y, visual)
1. HONESTY (P0/P1): any overclaim? "Cryptographically signed" gated on a real signature? two-family "Verified" gated on the real field? "no external AI vendor" not "air-gapped"? no fabricated counts/hashes (fileCount/values only from props)?
2. Renders only present fields (every field guarded)?
3. tokens/a11y (ShieldCheck/BadgeCheck aria-hidden, AA). Any P0/P1.

## Output schema
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
merge_decision: MERGE AUTHORIZED | DO NOT MERGE
```
