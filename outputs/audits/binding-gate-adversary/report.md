# Binding-gate independent adversary pass (P7)

An Opus agent that did not implement P1-P6 treated graph JSON, corpus rows, metadata receipts,
bindings, expression nodes, cached contracts, and source policy as attacker-controlled inputs and
tried to make one fabricated attribution slip through the real production chain.

- **seed:** `0xb1ade`
- **total attacks run:** 1295
- **attack families:** 7

## Attacks by family

| family | attacks | bypasses |
|---|---:|---:|
| foreign_doi_relabel | 155 | 0 |
| generic_title_collision | 124 | 0 |
| glyph_laundering | 126 | 0 |
| json_tampering | 6 | 0 |
| policy_laundering | 167 | 0 |
| structural_fuzz | 700 | 0 |
| unknown_enum | 17 | 0 |

## Minimized failures

None. Every attack — hand-built minimized case and seeded structural mutation — failed closed.
No regression fixture was required, because no bypass was reproduced.

## Regression test added

`tests/test_binding_gate_adversary.py` — this file. It is now part of the P7 gate and the final
release sequence, so every attack family re-runs on every future change to the binding gate.

## Terminal result

```text
admitted fabricated attributions: 0
unknown-enum admissions:          0
tampered graphs loaded:           0
policy-laundering successes:      0
```

