# Codex VISUAL audit — I-p2-059 (#865) Audit & export — FRONTIER bar — iter 2 of 5

You have VISION. iter-1 (desktop A / mobile B): P1 = mobile gate-ledger detail column clipped (the
abort reason + threshold weren't fully readable on a compliance surface); P2 = mobile manifest hid
bytes/SHA.

## Fix applied (this iter)
- Both tables are now RESPONSIVE: the dense table on sm+ (hidden < sm), and on mobile a STACKED
  CARD per row. Gate ledger mobile cards show gate name + status pill + the FULL detail wrapping
  (abort_no_verified_sections, "0% span-verified · threshold 40%", full lineage). Manifest mobile
  cards show file path + type/bytes + the FULL SHA-256 (the integrity proof) wrapping — nothing
  clipped. Desktop unchanged.

## Real-data note (not a defect)
Still the REAL canonical ABORT bundle → gate FAIL/FAIL/PASS is the honest, correct story (gates
caught unverified claims). Do not flag.

## Attached
1. audit_desktop  2. audit_mobile

## Output schema (required)
```yaml
verdict: APPROVE | REQUEST_CHANGES
per_screen_grades: { desktop: "", mobile: "" }
novel_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
```
APPROVE iff zero P0/P1 (compliance detail fully readable on both).
