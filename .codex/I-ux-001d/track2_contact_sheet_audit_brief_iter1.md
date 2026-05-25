# Codex family-template contact-sheet audit — I-ux-001d TRACK 2 (iter 1)

## §0 cap directive (verbatim CLAUDE.md §8.3.1)

```
HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1.
- Same quality bar regardless of iter count.
- "Don't pick bone from egg."
- Verdict APPROVE iff zero P0/P1.
```

## Scope

Per Codex iter-3 sequencing direction (D2 family-contracts strategy + D3 audit-cadence hybrid): "1 family-template contact-sheet audit" covering the 5 family templates that specialize into the 12 page heros.

5 templates audited:
1. **Read-mode** (Inspector / Compare / Audit) — `family_template_0_read_mode_desktop.png` = the existing v6 hero (already iter-3 APPROVED; included for cross-family grammar consistency)
2. **Edit-mode** (Intake / Source Review / Plan review) — `family_template_1_edit_mode_desktop.png` — NEW
3. **Monitor-mode** (Run progress / Dashboard) — `family_template_2_monitor_mode_desktop.png` — NEW
4. **Spatial** (Knowledge graph) — `family_template_3_spatial_desktop.png` — NEW
5. **Marketing-auth** (Home / Sign-in) — `family_template_4_marketing_auth_desktop.png` — NEW

## Family contracts being demonstrated

Per `docs/web/i_ux_001d_route_frame_map.md` taxonomy:

| Template | Contract surfaces |
|---|---|
| Read-mode | Sealed evidence block + provenance two-band strip + signed-bundle pill + per-claim verdict + two-judgment chip-row |
| Edit-mode | Just-ask input + auto-detected domain badge + source-set control + decision rationale strip + gate verdict (Proceed/Amend/Cancel) |
| Monitor-mode | Live SSE stream + depth-visible checklist + per-tier source counter + pipeline-verdict honesty (success / abort_* names) |
| Spatial | Force-directed graph + focal spotlight + navigator rail + BFS expand + PNG/JSON export |
| Marketing-auth | Single-column hero + proof-as-CTA (real verified claim) + ONE primary action + institutional-quiet typography |

## What I want from this audit

1. **Family-contract clarity per template.** Does each template communicate its abstract family grammar (NOT a specific page) clearly enough that the 12 specialized pages can be derived from it without re-litigating the family choices?
2. **Cross-family visual system consistency.** All 5 templates share the same shell (header, footer, brand-red accents, signed-bundle reference, Canadian-hosted chip). Does the system hold across the families?
3. **Per-frame v6 checklist** (12 items, per `docs/web/i_ux_001d_route_frame_map.md`): each template should pass the relevant checklist items. Sealed evidence block (read-mode only); two-judgment separation (read-mode); tri-state signature pill (all); intended-use language (where clinical content shown); no decorative icons; zero-jargon banlist; etc.
4. **Family completeness.** Does each family-contract callout (BRAND-RED text at bottom of each template) actually capture all the surfaces the specialized pages will need? Is anything missing?
5. **Cross-family hierarchy.** When specialized into 12 pages, will the family contracts produce visually consistent siblings (Inspector/Compare/Audit recognizably one family; Intake/Source Review/Plan review another) without becoming repetitive?
6. **TRACK 2 ready to sign off?** If APPROVE → proceed to TRACK 3 (24-frame mega-audit on 12 specialized page hero frames × {desktop + mobile}).

## Output schema (per CLAUDE.md §8.3.9)

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
  family_contract_clarity_per_template: PASS | FAIL_with_detail
  cross_family_visual_system_consistency: PASS | FAIL_with_detail
  per_frame_v6_checklist_coverage: PASS | FAIL_with_detail
  family_completeness: PASS | gaps_listed
  cross_family_hierarchy_visual_consistency: PASS | FAIL_with_detail
```

## Files to `-i` (5 templates, in 0→4 order)

- `web/p2shots/I-ux-001d/family_templates/family_template_0_read_mode_desktop.png`
- `web/p2shots/I-ux-001d/family_templates/family_template_1_edit_mode_desktop.png`
- `web/p2shots/I-ux-001d/family_templates/family_template_2_monitor_mode_desktop.png`
- `web/p2shots/I-ux-001d/family_templates/family_template_3_spatial_desktop.png`
- `web/p2shots/I-ux-001d/family_templates/family_template_4_marketing_auth_desktop.png`
