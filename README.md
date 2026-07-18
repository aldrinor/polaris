# Deep Cove Research

**An autonomous deep-research agent that turns many sources into one long-form report — where every claim traces back to a verifiable citation.**

The differentiator is *faithfulness*: a built-in verifier re-grounds and repairs each sentence against its source evidence instead of hallucinating. Think of it as a research analyst that never makes up a fact.

> Named after Deep Cove, North Vancouver — a deep, quiet inlet.
> **Internal codename:** *Polaris*. You will still see `polaris_*` packages, `PG_*` env flags, and `/workspace/POLARIS` paths throughout the code — that is the engine's codename, not the product name. De-branding of internal identifiers is deliberate and gradual so it never destabilizes the running pipeline.

## What it does

```
PROMPT
 └─ PLANNING GATE      compile a typed research contract from the prompt
 └─ RETRIEVAL          contract-scoped fetch + credibility tiering (web + academic)
 └─ COMPOSE            outline → per-section drafts (the LLM writes the report)
 └─ VERIFY / DEDUP     per-sentence faithfulness check → repair-and-re-bind, not drop
 └─ RENDER             clean report body (audit chrome lives in a sidecar)
 └─ SCORE              RACE / DeepResearch-Bench
```

## Status

Active research. Current focus: the faithfulness verifier (**repair-not-drop**) and closing the
gap to the champion RACE baseline. See `research/PIPELINE_DESIGN.md` for the authoritative design,
evidence, and locked fix plan.

## License

Proprietary — all rights reserved (pending).
