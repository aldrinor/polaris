# Codex family-template contact-sheet audit — I-ux-001d TRACK 2 (iter 2)

## §0 cap directive (verbatim CLAUDE.md §8.3.1)

```
HARD ITERATION CAP: 5 per document. This is iter 2 of 5.
- Front-load ALL real findings in iter 1.
- Same quality bar regardless of iter count.
- "Don't pick bone from egg."
- Verdict APPROVE iff zero P0/P1.
```

## What changed since iter 1

iter 1 verdict: REQUEST_CHANGES, 0 P0, 3 P1, 4 P2, 2 P3, `convergence_call: continue`, `track_2_ready_to_signoff: no`. All P1+P2 addressed in rebuild:

| iter-1 finding | severity | fix in iter-2 rebuild |
|---|---|---|
| Intended-use language missing on clinical-content frames | P1 | added amber INTENDED USE strip (y=808) to all 4 templates |
| Edit-mode `Cancel` substitutes for refusal | P1 | replaced with `Refuse to answer` (magenta-red border) — POLARIS abstention |
| Monitor-mode exposes `abort_*` raw tokens in product copy | P1 | humanized to `corpus not adequate / no claim verified / corpus declined` |
| Tri-state signature under-demonstrated | P2 | monitor-mode footer shows all 3 states |
| Monitor-mode lacks live event stream contract | P2 | added live event-stream strip with timestamps + source decisions + rejects |
| Spatial lacks expand/export controls | P2 | added Expand / PNG / zoom controls on graph canvas |
| Edit-mode lacks source-set control surface | P2 | added concrete source-set chips row |
| Red annotation lines compete with UI / implementation jargon | P3 | rebuilt as single muted slate line, SSE/BFS removed from product copy |
| Canadian-hosted chip status dot semantic ambiguity | P3 | left as-is — the dot is semantic (green = active), kept consistent with existing v6 pattern |

## What to audit now

Same 5 templates at the same paths (4 newly rebuilt):
- `web/p2shots/I-ux-001d/family_templates/family_template_0_read_mode_desktop.png` (= v6 hero; unchanged)
- `web/p2shots/I-ux-001d/family_templates/family_template_1_edit_mode_desktop.png` (refuse + source-set chips + intended-use strip + muted callout)
- `web/p2shots/I-ux-001d/family_templates/family_template_2_monitor_mode_desktop.png` (humanized abort + tri-state sig + SSE stream + intended-use strip + muted callout)
- `web/p2shots/I-ux-001d/family_templates/family_template_3_spatial_desktop.png` (expand/export/zoom controls + intended-use strip + muted callout)
- `web/p2shots/I-ux-001d/family_templates/family_template_4_marketing_auth_desktop.png` (intended-use strip + muted callout)

## Iter-2 specific check

1. **All 3 P1 fixes accepted?** Intended-use language clear on clinical frames? Refuse-to-answer reads as POLARIS abstention not user cancel? Monitor-mode free of `abort_*` raw tokens?
2. **Tri-state signature now readable in monitor-mode footer?**
3. **Live event-stream strip conveys monitor-mode SSE contract?**
4. **Spatial controls visible and well-positioned?**
5. **Edit-mode source-set chips communicate the source-set control?**
6. **De-emphasized callouts — still informative but not visually competing?**
7. **TRACK 2 ready to sign off?**

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
  p1_intended_use_fix: PASS | FAIL_with_detail
  p1_refuse_not_cancel_fix: PASS | FAIL_with_detail
  p1_abort_token_humanization_fix: PASS | FAIL_with_detail
  p2_tri_state_signature: PASS | FAIL_with_detail
  p2_sse_event_stream: PASS | FAIL_with_detail
  p2_spatial_controls: PASS | FAIL_with_detail
  p2_source_set_chips: PASS | FAIL_with_detail
  p3_callout_de_emphasis: PASS | FAIL_with_detail
```
