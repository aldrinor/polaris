# Codex hero-motion visual audit — I-ux-001d TRACK 1 sub-track A (iter 2)

## §0 cap directive (verbatim CLAUDE.md §8.3.1)

```
HARD ITERATION CAP: 5 per document. This is iter 2 of 5.
- Front-load ALL real findings in iter 1.
- Same quality bar regardless of iter count.
- "Don't pick bone from egg."
- Verdict APPROVE iff zero P0/P1.
```

## What changed since iter 1

Iter 1 verdict: REQUEST_CHANGES, 0 P0, 2 P1, 3 P2, 1 P3.

| iter-1 finding | severity | fix applied in iter-2 rebuild |
|---|---|---|
| Rest state wrong: challenged-sentence styling at t=0 | P1 | stripped row fill/stroke; hid numeric marker + active-status; reverted text to muted slate |
| Beat 6 missing at t=700 (Limits disclosure not visible) | P1 | rebuilt t=700 as 6th motion frame with all blocks visible incl Limits disclosure |
| Spatial/temporal mismatch (proof-panel hole at t=400) | P2 | swapped Y: Evidence strength y=315, Source (climax) y=460 — reveal order matches spatial order |
| Beat 1 claim echo lacks 'Challenged sentence' label | P2 | added 'CHALLENGED SENTENCE' uppercase Inter Medium 10/4% slate label above claim echo (hidden t=0, visible t=120+) |
| t=700 missing annotation bar | P2 | t=700 now has same 24px bar + top-right mark as others |
| Ladder labels small/low-contrast (P3) | P3 | carry forward to scale-up; not addressed |

## What to audit now

Same 6 frames at the same paths (overwritten with new renders, new node IDs 23:*):
- `web/p2shots/I-ux-001d/motion/hero_first_reveal_pre_desktop_t0.png` (95014 bytes; rest state cleaned)
- `web/p2shots/I-ux-001d/motion/hero_first_reveal_start_desktop_t120.png` (117487 bytes)
- `web/p2shots/I-ux-001d/motion/hero_first_reveal_mid_desktop_t250.png` (129883 bytes)
- `web/p2shots/I-ux-001d/motion/hero_first_reveal_near_end_desktop_t400.png` (139374 bytes; Evidence strength above Source position)
- `web/p2shots/I-ux-001d/motion/hero_first_reveal_end_desktop_t600.png` (162723 bytes; Source above Signature position)
- `web/p2shots/I-ux-001d/motion/hero_first_reveal_final_static_desktop_t700.png` (166847 bytes; now has annotation + Limits disclosure)

## Iter-2 specific check

1. **P1 fixes accepted?** t=0 rest state + t=700 Beat-6 disclosure visible?
2. **Spatial-temporal reorder accepted?** Evidence strength → Source flow now reads cleanly?
3. **Challenged-sentence label visible at t=120+?** The label is slate-on-cream, 10px Inter Medium with 4% tracking. Is it readable, or too subtle?
4. **Source as climax preserved?** Even though Evidence strength now reveals first (Beat 3 at t=400), does Source still feel like THE proof-object climax when it appears at t=600?
5. **New issues introduced by the fix?** Any visual regression from iter 1 to iter 2?
6. **Ready to scale to all 8 scenes × full+reduced × desktop+mobile?**

## Output schema

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
p3: [...]
convergence_call: continue | accept_remaining
ready_to_scale_to_all_scenes: yes | no | with_caveats
specific_check_responses:
  rest_state_at_t0: PASS | FAIL_with_detail
  beat6_disclosure_at_t700: PASS | FAIL_with_detail
  spatial_reorder_accepted: PASS | FAIL_with_detail
  challenged_label_readability: PASS | needs_tightening
  source_as_climax_preserved: PASS | FAIL_with_detail
  iter1_to_iter2_regression: [...]
```

Files to `-i`: same 6 PNGs above.
