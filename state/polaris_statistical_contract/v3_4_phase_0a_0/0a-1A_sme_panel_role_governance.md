# 0a.-1.A — Judge-Panel + Oracle Role Governance (human-free)

**Deliverable**: Phase 0a.0 / 0a.-1.A — construction/adjudication role governance.
**Status**: HUMAN-FREE CONVERSION (I-safety-001c / #922, per amendment §8). Original SME-panel version (Codex APPROVE 2026-05-27, 3 rounds) preserved in git history; this supersedes it under the operator HARD CONSTRAINT (no human SMEs, ever; only API budget).
**Parent**: contract v3.3 (human-free amended) + `human_free_amendment/AMENDMENT_human_free_validation.md`; depends on D1a (6 validation domains).
**Codex review**: original SME trail in `.codex/I-safety-001b/codex_0a1A_*`; human-free conversion review in `human_free_amendment/codex_trail/`.
**Version**: 2 (human-free)

**What changed (SME → machine)**: the former human roles (constructor / adjudicator / tiebreaker / human panel) are replaced. Fabrication STATUS is now a **mechanical oracle** (deterministic mutation; never judged). SEVERITY is adjudicated by a **cross-family LLM judge panel** (≥3 lineages) + a **deterministic hazard scaffold**, with escalation to operator + Codex (NO human SME). There is NO recruitment, NO credentials, NO human COI.

---

## §1. Role taxonomy (machine roles)

| Role | Responsibility | Constraints |
|---|---|---|
| **Constructor** (deterministic/LLM pipeline) | Builds a claim+evidence-packet scenario; injects fabrications by **deterministic mutation** per the 0a.-1.B taxonomy; emits the sealed `constructor_intent` (the mechanical STATUS label — what was injected) | Constructor model-family MUST be disjoint from the judge-panel families AND the verifier family (anti-circularity, amendment §4) |
| **Mechanical oracle** | The fabrication STATUS label itself — KNOWN because the constructor injected it; deterministic, NOT a judgment | NEVER LLM-judged. Status is computed from `constructor_intent` + structured-field/exact-span proof (Gate E1) |
| **Severity judge panel** (≥3 cross-family LLMs) | Blinded first-pass SEVERITY label per item; produces the agreement object (Gate E2) | ≥3 distinct model lineages (e.g. GPT/Codex + Claude + Qwen); each blind to verifier outputs/rationales/scores and to the others' first-pass labels and to `constructor_intent` |
| **Deterministic hazard scaffold** | Assigns a presumptive risk band from source-field + mutation-type where rules decide (dose/contraindication/boxed-warning/withdrawal/...) | "dose changed" → S0-CANDIDATE, never auto-S0 (severity-laundering guard, amendment §2/§7) |
| **Escalation (§-1.1)** | Resolves persistent judge disagreement on severity | operator + Codex line-by-line vs cited evidence + **deterministic rule**. NO human SME. If rules + Codex cannot resolve, the item drops to exploratory (it does not get a human label) |

**Family-disjointness invariant (replaces human role-disjointness; amendment §4)**: across a `blinding_unit_id` (claims sharing construction intent / fabrication pattern / evidence packet / batch),
`constructor_family ∉ judge_panel_families` AND `verifier_family ∉ judge_panel_families` AND the ≥3 `judge_panel_families` are pairwise distinct.
Rationale: shared lineage = shared blind spot. The disjointness scope is the `blinding_unit_id` (MAY equal a single claim; the manifest declares which).

## §2. Mechanical enforcement (deterministic, blocking — not policy prose)

### §2.1 `assignment_manifest` (hash-pinned, append-only)

```json
{
  "claim_id": "<id>",
  "blinding_unit_id": "<id | == claim_id>",
  "constructor_instance": {"family": "<lineage>", "model": "<slug>", "version": "<snapshot>", "decoding": "<settings>"},
  "judge_instances": [
    {"family": "<lineage>", "model": "<slug>", "version": "<snapshot>", "decoding": "<settings>", "prompt_hash": "<sha256>"},
    {"family": "<lineage>", "model": "<slug>", "version": "<snapshot>", "decoding": "<settings>", "prompt_hash": "<sha256>"},
    {"family": "<lineage>", "model": "<slug>", "version": "<snapshot>", "decoding": "<settings>", "prompt_hash": "<sha256>"}
  ],
  "verifier_family": "<lineage>",
  "assigned_at": "<utc>",
  "assignment_seed": "<pinned randomization seed ref>",
  "row_status": "live | superseded"
}
```

### §2.2 Family-disjointness + independence validator (deterministic, blocking)

A Python validator (`validate_judge_independence`) runs over `assignment_manifest` + `judge_registry` (§7) + `exposure_log` and REJECTS (non-zero exit, blocks the run) any row where, across the row's `blinding_unit_id`:
- `constructor_instance.family ∈ judge_panel_families`, OR
- `verifier_family ∈ judge_panel_families`, OR
- `len(distinct judge_panel_families) < 3`, OR
- duplicate family within `judge_instances`, OR
- more than one `live` assignment row for the same `claim_id`, OR
- any judge/constructor instance absent from the locked `judge_registry`, OR
- any judge instance is `active == false` or version-unfrozen, OR
- any judge instance is not eligible for the claim's domain (§3), OR
- the claim's entity/topic IDs are unresolved (fail-closed; see §4), OR
- a leakage hit: a judge instance's prompt/exemplars/RAG/memory contains gold-set or Phase-0a content (per contract §P3.4 items 32-41), OR
- exposure-log contamination: a judge's exposure log shows a disqualifying prior read (verifier output/rationale/score, `constructor_intent`, or another judge's first-pass for that blinding unit).

The validator is hash-pinned (per 0a.-1.E custody) alongside the relation-builder/randomizer hashes.

### §2.3 Judge invocation enforcement — POSITIVE authorization

The judge-invocation harness does NOT merely block forbidden inputs; it POSITIVELY AUTHORIZES and constructs each judge call deterministically:
- **First-pass severity call**: permitted ONLY for an `judge_instance` listed for that claim; the call is constructed from the frozen judge prompt (`prompt_hash`) + the blinded packet; NO verifier output, NO `constructor_intent`, NO sibling-judge label is included in the context.
- **Escalation**: operator + Codex + the deterministic rule; no human-SME label path exists.
- Every judge call (input context hash + output) is logged to the exposure log (per 0a.-1.E), reads included.

### §2.4 Controlled artifact / access layer (4th enforcement surface)

UI/prompt-level hiding is insufficient if a judge process can reach packet internals, `constructor_intent`, verifier outputs, or sibling labels OUTSIDE the harness. Binding:
- Storage/object access to construction-intent, first-pass-judge, consensus, verifier-output, and packet-internal artifacts MUST be role-scoped at the storage layer (object ACLs / tokens), not only at the harness.
- Any access path is wired to the exposure log (reads + writes).
- The §2.2 validator excludes any judge instance whose exposure log shows a disqualifying read.
- 0a.-1.E implements the storage-layer ACLs + exposure-log wiring; 0a.-1.A names it BINDING here.

## §3. Per-domain judge eligibility (replaces human credential floors)

There are NO human credentials. A judge instance is eligible for a domain iff it meets the deterministic eligibility profile. Each profile maps to registry-verifiable, hash-pinned fields (not free-text):

| Domain | Judge eligibility profile | Registry-verifiable fields |
|---|---|---|
| `clinical` | ≥3 distinct frontier lineages on the panel; each a current top-tier instruction model; deterministic hazard scaffold MANDATORY for treatment/pharmacotherapy/device items (structured-field rules auto-flag dose/contraindication/boxed-warning); structured clinical source (label/registry) REQUIRED for confirmatory status | `family`, `model_slug`, `version_snapshot`, `decoding`, `prompt_hash`, `hazard_scaffold_pin` |
| `due_diligence` | ≥3 distinct lineages; entity grounding via 0a.-1.D registry IDs | `family`, `model_slug`, `version_snapshot`, `decoding`, `prompt_hash` |
| `policy` | ≥3 distinct lineages; source grounding to dated/structured policy artifacts | same |
| `tech` | ≥3 distinct lineages; standards/spec grounding | same |
| `ai_sovereignty` | ≥3 distinct lineages; source grounding to governance/standards artifacts | same |
| `canada_us` | ≥3 distinct lineages; cross-border source grounding | same |

**Clinical adjudication-path rule (human-free)**: for treatment/pharmacotherapy/device claims, the **deterministic hazard scaffold MUST be in the severity path** (it auto-flags dose/contraindication/boxed-warning fields as S0-candidate) AND the confirmatory STATUS label MUST be grounded in a structured clinical source (drug label / trial registry) per Gate E1. There is no MD/PharmD human requirement; the safety comes from mechanical status + structured-field hazard rules + the cross-family panel, with the honest claim-license caveat (NOT clinical/expert validation; amendment §6).

**Panel-size math (human-free)**: the per-claim minimum is **≥3 distinct judge families** (the severity panel). There is no constructor-vs-adjudicator headcount (the constructor is a pipeline, family-disjoint from the panel). The deterministic hazard scaffold + the mechanical oracle do the rest. No roster TARGET of human SMEs — the "roster" is the frozen `judge_registry` (§7).

## §4. Independence / anti-contamination screen (replaces human COI; mechanically enumerable)

Human COI does not exist. The analogue is judge INDEPENDENCE + leakage control:

1. The `judge_registry` records per instance: `{family, model_slug, version_snapshot, decoding, prompt_hash, training_lineage_id, provider_opt_out_ref}`.
2. Each claim carries resolved `entity_ids[]` + `microtopic_tags[]` (from 0a.-1.C construction_manifest) — used for stratification + leakage checks, not human COI.
3. The §2.2 validator enforces: family-disjointness (constructor/verifier/judges all distinct lineages); NO shared exemplars/rationales/RAG/memory across constructor, verifier, and judge prompts (contract §P3.4); frozen versions + decoding; provider-side training/retention opt-out documented (`state/provider_opt_outs/`).
4. **Fails closed** if a judge instance's lineage cannot be established as disjoint, or its leakage status is unresolved.
5. Entity-ID resolution depends on 0a.-1.D (canonical entity identity) for `entity_ids` and D4 (microtopic ontology) for `microtopic_tags`. Until both exist, stratification/leakage checks run fail-closed.

## §5. Blinding / isolation protocol (label-symmetric construction; judge isolation)

Hiding labels is insufficient if packet CURATION leaks intent. v2 requires **label-symmetric packet construction** AND **judge isolation**:

- Same deterministic packet builder + same source-selection rules for fabricated and non-fabricated (matched-control) claims.
- Same facet generation (neutral, deterministic, uniform — no spotlighting of the mutated clause).
- No packet metadata revealing the mutation (no "injected here" markers, no asymmetric annotation).
- Each judge sees: claim text + neutral facet views + rendered evidence packet + cited spans.
- Each judge does NOT see: `constructor_intent` (the mechanical status), the deterministic hazard band, verifier outputs/rationales/scores, or sibling judges' first-pass labels.
- Cross-family judge agreement (Gate E2) is computed on first-pass blinded SEVERITY labels ONLY.
- Fabrication STATUS is NOT judged — it comes from the mechanical oracle (Gate E1), so judge isolation cannot affect it.

## §6. Severity tiebreak workflow (per-field majority across ≥3 judges; deterministic escalation)

Severity is the only judged field (status is mechanical). The judged object is `severity ∈ {S0,S1,S2,SUPPORTED-control}` (SUPPORTED is a mechanical-status class, included for matched controls):

1. ≥3 cross-family judges label severity first-pass (blinded).
2. Deterministic hazard scaffold emits its presumptive band (S0-candidate etc.) independently.
3. **Reconciliation**: per the pre-registered rule — majority of the ≥3 judges sets the panel severity; the hazard scaffold can ESCALATE (e.g. a structured dose mutation forces ≥ S0-candidate review) but never DOWNGRADE below the rule's floor.
4. If judges lack a majority on an ordinal split (e.g. S1/S2/S0 three-way) → escalation: operator + Codex line-by-line + deterministic rule. **Severity is NOT median/averaged** — ordinal disagreement escalates. If escalation cannot resolve deterministically, the item drops to **exploratory** (no human label is invented).
5. Consensus severity written to `llm_consensus_severity_labels` (0a.-1.C); first-pass labels retained in `llm_first_pass_severity_labels` for the Gate E2 agreement coefficient.

## §7. Judge registry (frozen; the "roster" analogue — NO recruitment)

```json
{
  "judge_instance_id": "<stable id>",
  "family": "<training lineage>",
  "model_slug": "<provider model>",
  "version_snapshot": "<frozen snapshot id>",
  "decoding": {"temperature": 0, "top_p": 1, "...": "frozen"},
  "prompt_hash": "<sha256 of the frozen judge prompt>",
  "domains_eligible": ["<domain>", ...],
  "training_lineage_id": "<for family-disjointness checks>",
  "provider_opt_out_ref": "<state/provider_opt_outs/...>",
  "frozen_by": "<custodian script + code-pin>",
  "frozen_at": "<utc>",
  "active": true
}
```

The registry is FROZEN (model snapshots + prompts + decoding) before any gold-set judging; provider-side silent model updates invalidate the affected cycle (contract §P3.4). There is NO human recruitment — assembling the registry = selecting + freezing ≥3 cross-family model instances per domain. The framework (this deliverable) governs the registry schema + the validators that consume it.

---

## §8. Dependencies + ordering notes

- Needs D1a (6 domains) — DONE.
- 0a.-1.B (severity rubric + mechanical fabrication oracle) precedes judge prompt-freezing (the judges apply the rubric) — but this GOVERNANCE framework can lock first.
- `assignment_manifest` + `judge_registry` schemas feed 0a.-1.C (integrated metadata) and 0a.-1.E (custody/exposure log).
- The family-disjointness validator + judge-invocation enforcement are hash-pinned in 0a.-1.E.

## §9. Definition of done (0a.-1.A, human-free)

Framework locked: machine role taxonomy (constructor pipeline / mechanical oracle / ≥3 cross-family severity judges / deterministic hazard scaffold / operator+Codex+rule escalation), family-disjointness invariant + validator spec, judge-invocation positive-authorization rules, per-domain judge-eligibility profiles, independence/anti-leakage screen, label-symmetric + judge-isolation blinding, severity tiebreak (per-field majority + deterministic escalation, drop-to-exploratory if unresolved), judge_registry + assignment_manifest schemas. ZERO human dependency (no recruitment / credentials / human COI / human panel). Codex §-1.1 APPROVE. Hash-pin. Operator sign-off.

Deferred (NOT human procurement — model-side setup): selecting + freezing the ≥3 cross-family judge instances per domain into the `judge_registry`.
