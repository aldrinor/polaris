# embedder_late_interaction — two-family adjudication side files

The SCORED labels for this layer's fixture live HERE, NOT in `build_fixture.py`. Keyword
proposals (from `scripts/relevance_scorer_bakeoff.py` LABEL_SETS) only PROPOSE candidate rows;
the scored label is set ONLY by an independent two-family (Claude + Codex) adjudication with an
operator sample spot-check (brief §7, iter-2 P1). A row/pair with no record here is EXCLUDED
from scoring — never silently scored against a string-pattern label.

## `axis_a_adjudication.jsonl` — one JSON object per line

```json
{"key": "axis_a::drb_78_parkinsons_dbs::<evidence_id>", "label": "pos", "source": "claude+codex+operator_spotcheck"}
```

- `key`   = `axis_a::<slug>::<evidence_id>` (must match the row's evidence_id in the snapshot).
- `label` = `"pos"` (on-topic for that question) | `"neg"` (off-topic) — set by adjudication.
- `source`= free text recording the two-family + operator provenance (for audit).

Only rows whose `label` ∈ {`pos`,`neg`} become `scored=True`. The keyword `proposed_label`
is retained for audit but is NOT the scored label.

## `axis_b_adjudication.jsonl` — one JSON object per line

```json
{"key": "axis_b::drb_78_parkinsons_dbs::<claim_id>::<support_evidence_id>", "supports": true, "source": "claude+codex"}
```

- `key`      = `axis_b::<slug>::<claim_id>::<supporting_evidence_id>`.
- `supports` = `true` iff the two families CONFIRM the supporting source actually supports the
  claim via non-lexical (reasoning) evidence. Only `supports: true` pairs become `adjudicated`.

The candidate pairs (which the adjudicators review) are pre-screened to lexical overlap
< `PG_EMBED_AXISB_OVERLAP_CEILING` (0.10), so the adjudication is over genuinely non-lexical
support relations — the late-interaction edge the metric measures.
