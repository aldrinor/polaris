# Codex 12-page mega-audit — I-ux-001d TRACK 3 (iter 2)

## §0 cap (verbatim CLAUDE.md §8.3.1)
HARD ITERATION CAP: 5. This is iter 2 of 5. APPROVE iff zero P0/P1.

## What changed
iter 1: REQUEST_CHANGES, 0 P0, 1 P1, 3 P2, 2 P3.

| iter-1 finding | fix |
|---|---|
| P1 page-12 /transparency H1/para collision + card clipping | H1 40px, para y=180, card 200h w/ 22px line-height, CTA y=520 |
| P2 page-10 /sign-in prose institution list | Replaced with 5 row buttons + relabeled CTA |
| P2 page-08 /kg low density | 8 secondary nodes + edges + 3px green SELECTED PATH trail + label |
| P2 page-09 /audit too similar to Inspector | Proof panel replaced with 12-field manifest disclosure + 4 export buttons |

## Audit now
Same 12 frames; 4 rebuilt (08, 09, 10, 12); 8 unchanged from iter-1 PASS.

## Specific check
1. P1 transparency: H1 + para readable now without collision?
2. P2 sign-in: reads as auth chooser?
3. P2 kg: feels explorable, not static?
4. P2 audit: clearly distinct from Inspector?
5. TRACK 3 ready to sign off?

## Schema
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
p3: [...]
convergence_call: continue | accept_remaining
track_3_ready_to_signoff: yes | no | with_caveats
specific_check_responses:
  p1_transparency_layout: PASS | FAIL_with_detail
  p2_signin_chooser: PASS | FAIL_with_detail
  p2_kg_density: PASS | FAIL_with_detail
  p2_audit_identity: PASS | FAIL_with_detail
```
