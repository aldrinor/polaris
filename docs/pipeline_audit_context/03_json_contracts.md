# JSON contracts — pipeline A

What each pipeline-A run writes to `outputs/<sweep>/<slug>/`.
Extracted from a real manifest as of 2026-04-18.

## `manifest.json` — the pipeline verdict

```jsonc
{
  // Run identity
  "run_id": "r6v_clinical_tirzepatide_t2dm_20260417T22...",
  "slug": "clinical_tirzepatide_t2dm",
  "domain": "clinical",
  "question": "What is the efficacy and safety of tirzepatide ...",

  // Pipeline verdict
  "status": "success" | "abort_scope_rejected" | "abort_corpus_inadequate"
           | "abort_corpus_approval_denied" | "abort_no_verified_sections"
           | "error_*",
  "error": "<optional error message>",

  // Corpus adequacy gate output
  "adequacy": {
    "decision": "accept" | "abort",
    "evidence_rows": 18,
    "findings": [
      {"name": "total_sources", "observed": 20, "ok": true, "severity": "ok", "threshold": 6},
      {"name": "t1_count", "observed": 0, "ok": false, "severity": "critical", "threshold": 1},
      // ... 7 named thresholds
    ],
    "notes": ["Corpus fails 3 critical threshold(s): ..."],
    "thresholds": { ... }
  },

  // Corpus composition + approval
  "corpus": {
    "count": 20,
    "tier_fractions": {"T1": 0.0, "T2": 0.0, "T3": 0.05, "T5": 0.5, ...},
    "material_deviation": true,
    "approved": false,
    "approval_note": "..."
  },

  // Generator output stats
  "generator": {
    "outline_sections": ["Findings", "Safety", "Limitations"],
    "sections_total": 3,
    "sections_dropped": 0,
    "sentences_verified": 42,
    "sentences_dropped": 3,
    "model": "deepseek/deepseek-v3.2-exp",
    "input_tokens": ...,
    "output_tokens": ...
  },

  // Evaluator output (when status=success)
  "evaluator": {
    "rule_pass": true,
    "qwen_scores": {
      "groundedness": 0.88,
      "comprehensiveness": 0.72,
      "citation_accuracy": 0.95,
      "hedging": 0.80
    },
    "model": "qwen/qwen3-8b"
  },

  // Contradictions detected in the corpus
  "contradictions_count": 2,

  // Cost + budget
  "cost_usd": 0.83,
  "pg_max_cost_per_run": 5.00
}
```

## `report.md` — two shapes

### Shape 1: `status=success` (actual research report)

```
# Research report: <question>

## <Section title>

<Prose with numbered citations [1][2][3] ...>

## Limitations

<Limitations paragraph, no citations>

## Methods

<Methods section — pipeline description>

## Bibliography

1. <url1> — <tier> — <source statement excerpt>
2. <url2> — ...
```

### Shape 2: `status=abort_*` (pipeline-verdict artifact)

```
# Research report: <question>

## Pipeline verdict

DeepSeek V3.2-Exp generated N section(s), but EVERY section failed
Phase-4 strict_verify: the cited evidence did not support the claims,
or the generator did not emit provenance tokens.

### Per-section verdict

- **<title>** — verified=0, dropped=12, regen_attempted=True, error='...'
- ...

### Suggested next steps

- Widen retrieval so the generator has anchor evidence to cite.
- Tune the generator prompt for stricter citation discipline.
- Abort and refine the research question.
```

Downstream consumers MUST distinguish these shapes by checking
`manifest.status`, NOT by looking at `report.md` existence.

## `corpus_approval.json`

```jsonc
{
  "approved": false,
  "material_deviation": true,
  "tier_distribution": {"T1": 0.0, "T2": 0.0, ...},
  "expected_distribution": [
    {"tier": "T1", "min_fraction": 0.3, "max_fraction": 0.6},
    ...
  ],
  "note": "<operator-supplied rationale for approval>",
  "note_is_substantive": false,
  "timestamp": "2026-04-18T13:..."
}
```

## `contradictions.json`

```jsonc
[
  {
    "subject": "semaglutide",
    "predicate": "weight loss %",
    "values": [
      {"value": 14.9, "unit": "%", "evidence_id": "ev_001"},
      {"value": 15.0, "unit": "%", "evidence_id": "ev_002"},
      {"value": 13.8, "unit": "%", "evidence_id": "ev_003"}
    ],
    "relative_difference": 0.079,
    "severity": "medium"
  },
  ...
]
```

## `protocol.json`

The scope template used for this run, verbatim from
`config/scope_templates/<domain>.yaml`.

## `bibliography.json`

```jsonc
[
  {
    "num": 1,
    "evidence_id": "ev_001",
    "url": "https://...",
    "tier": "T1",
    "statement": "<up to 300 chars of the source statement>"
  },
  ...
]
```

Cross-section deduplicated: the same evidence_id → same num across
all sections.

## `live_corpus_dump.json`

Per-evidence detail used by the generator + verifier — evidence_id,
source_url, tier, statement, direct_quote, timestamp, etc.

## `qwen_judge_output.json`

Raw Qwen3-8B judge output (rationale + scores).

## `run_log.txt`

Human-readable log of the run. Each line prefixed with `[tag]` (e.g.,
`[scope]`, `[retrieval]`, `[generation]`, `[verify]`, `[ABORT]`).

---

## Audit questions

- Is there a JSON schema file that documents this contract? (Currently
  no — the contract is the code.)
- Are any fields dropped or renamed across runs? (Would break downstream
  consumers.)
- Does `manifest.status` cover every exit point, or are there code
  paths that write report.md without updating manifest.status?
- Is `timestamp` in each file ISO 8601 UTC? Any timezone mixing?
