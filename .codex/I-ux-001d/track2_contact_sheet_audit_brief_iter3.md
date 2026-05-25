# Codex family-template contact-sheet audit — I-ux-001d TRACK 2 (iter 3)

## §0 cap directive (verbatim CLAUDE.md §8.3.1)

```
HARD ITERATION CAP: 5 per document. This is iter 3 of 5.
- Front-load ALL real findings in iter 1.
- Same quality bar regardless of iter count.
- "Don't pick bone from egg."
- Verdict APPROVE iff zero P0/P1.
```

## What changed since iter 2

iter 2: REQUEST_CHANGES, 0 P0, 2 P1, 0 P2, 0 P3. All other findings PASS. The 2 P1s fixed:

| iter-2 P1 | fix in iter-3 rebuild |
|---|---|
| Read-mode lacks intended-use strip | Cloned v6 hero into family-templates page; added amber INTENDED USE strip (y=808) + template-annotation bar |
| Edit-mode refuse-button not legible (collapsed to tiny "DETECTED · DOMAIN · SOURCE" pill) | Rebuilt rationale block from scratch with 3 distinct horizontal buttons: Proceed (green, 160w) · Amend plan (ghost, 160w) · Refuse to answer (magenta-bordered, 200w) |

## What to audit now

Same 5 templates, all should now show intended-use strip + edit-mode shows complete rationale + 3 buttons:
- `web/p2shots/I-ux-001d/family_templates/family_template_0_read_mode_desktop.png` (NEW iter-3: v6 hero clone WITH intended-use strip)
- `web/p2shots/I-ux-001d/family_templates/family_template_1_edit_mode_desktop.png` (NEW iter-3: rationale block + 3 buttons restored)
- `web/p2shots/I-ux-001d/family_templates/family_template_2_monitor_mode_desktop.png` (unchanged since iter-2; PASS)
- `web/p2shots/I-ux-001d/family_templates/family_template_3_spatial_desktop.png` (unchanged since iter-2; PASS)
- `web/p2shots/I-ux-001d/family_templates/family_template_4_marketing_auth_desktop.png` (unchanged since iter-2; PASS)

## Iter-3 specific check

1. **P1 read-mode intended-use NOW visible?**
2. **P1 edit-mode refuse-to-answer button NOW visible and reads as POLARIS abstention?**
3. **TRACK 2 ready to sign off?**

## Output schema

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
p3: [...]
convergence_call: continue | accept_remaining
track_2_ready_to_signoff: yes | no | with_caveats
specific_check_responses:
  p1_read_mode_intended_use_fix: PASS | FAIL_with_detail
  p1_refuse_button_legibility_fix: PASS | FAIL_with_detail
```
