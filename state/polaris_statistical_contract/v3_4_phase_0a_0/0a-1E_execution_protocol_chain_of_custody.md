# 0a.-1.E — Execution Protocol / Chain of Custody (draft for Codex review)

**Deliverable**: Phase 0a.0 / 0a.-1.E — execution protocol + chain of custody.
**Status**: LOCKED (Codex §-1.1 APPROVE 2026-05-27 "Lock 0a.-1.E" after 3 rounds: 8 build-blocking gaps + 1 schema-consistency fix, all closed; pending operator sign-off).
**Parent**: contract v3.3 §P4.2 (exposure log); depends on D1a + 0a.-1.A + 0a.-1.B + 0a.-1.C-schema + 0a.-1.D (all LOCKED).
**Plan**: `PHASE_0a_0_PLAN.md`. Implements carry-forward redline #3 (mechanical, not policy). The 0a.-1.C CODE + edge-fixture RUN happens AFTER this (custody must govern those artifacts).
**Codex review**: `.codex/I-safety-001b/codex_0a1E_review.txt` + `codex_0a1E_confirm{,2}.txt`.
**Version**: 1 (LOCKED)

**Why this exists**: Codex round-3 (plan) named chain-of-custody as the 5th substrate hole: "Hashing schemas is not enough." 0a.-1.A §2.4 made storage-layer access control BINDING but deferred implementation here. This deliverable locks the mechanical custody layer: immutable hashes, role-scoped storage ACLs wired to a read+write exposure log, tool/code version pins, packet snapshots, randomization seed, replacement/drop rules, and the structural-vs-outcome exposure boundary.

---

## §1. Immutable artifact hashes (append-only)

Every Phase-0a artifact is content-hashed (SHA256) and recorded append-only in `state/data_lineage/hash_registry.jsonl`:

```
{ artifact_id, artifact_type, sha256, recorded_at, recorded_by, supersedes? }
```

Artifact types (Codex round-1 #2 — complete result-affecting set): all 8 manifests (0a.-1.C) incl. roster + assignment manifests + source-exception records + D8 allocation manifests; each locked deliverable doc; each scope template; the microtopic ontology (D4); the SME template set (D6); the prompt-family enumeration (D5); the literal JSON Schema files + schema-validator code; the relation-builder code; the randomizer / D8 allocation + min-cost-matching code; the role-disjointness validator code; the admissibility classifier/tier code + **pinned classifier version + deny-list config** (0a.-1.D); the URL param-strip / canonicalization config; the canonicalizer code; the packet renderer + source-fetch/snapshot code; the consensus/tiebreak/panel label-resolution code; the IRR/agreement (AC1/Krippendorff) computation code; the Gate A/B/D/E analysis runners; the bootstrap/CI + ICC/GLMM/surrogate-analysis code; every rendered packet snapshot; the calibration fixture; each edge fixture; and the hash/exposure/replacement **registry schemas themselves**.

Append-only: a superseding artifact records `supersedes` pointing at the prior hash; the prior row is never deleted (audit trail).

## §2. Code version pins (NOT just schemas — Codex plan redline)

Hash-pinned, with the exact version/commit that produced each result:

| Code | Pinned because |
|---|---|
| relation-builder (0a.-1.C) | determinism — a code change alters P/N/DEFF |
| randomizer (D8 allocation) | the pinned seed only reproduces under the pinned randomizer code |
| role-disjointness validator (0a.-1.A §2.2) | the enforcement IS the code |
| admissibility validator (0a.-1.D §3.1) | the allowlist enforcement IS the code |
| packet renderer | "what the SME saw" is reproducible only under the pinned renderer |
| adjudication UI/CLI (0a.-1.A §2.3) | a tool change mid-construction is a confound |
| canonicalizer (0a.-1.D §2.3) | alias resolution determinism |

Each code artifact's hash + version is in `state/data_lineage/code_pins.json`. A code change requires a contract §P4 Category-2 (analysis-preserving) or higher amendment.

## §3. Randomization seed (master + derived child streams — Codex round-1 #1)

ONE master seed in `state/data_lineage/master_seed.txt`. But a single REUSED stream across independent procedures risks stream coupling / repeated identical sequences. So each stochastic procedure draws from a NAMED, DOMAIN-SEPARATED child stream derived from the master:

```
child_seed(name) = HMAC-SHA256(master_seed, name)
  names: "D8-allocation", "GateB-bootstrap", "GateD-bootstrap",
         "GateE-bootstrap", "ICC-surrogate-bootstrap", "replacement-draw", ...
```

Reproducibility: master_seed + pinned randomizer code + the named-stream derivation reproduce the exact allocation + each CI independently. Master-seed or derivation change = contract §P4 amendment. The name list is hash-pinned alongside the master seed.

## §4. Role-scoped storage ACLs (0a.-1.A §2.4 — the 4th enforcement surface)

Direct storage/object access is role-scoped at the storage layer (object ACLs / signed access tokens), NOT only at the UI:

| Artifact | Read access |
|---|---|
| `construction_manifest` | design team (structural) |
| `constructor_intent_labels` (sealed) | NO ONE during construction/adjudication; unsealed only post-gate for analysis |
| `blinded_adjudication_labels` | the assigned adjudicator for their OWN first-pass only (until sealed); analysis team post-IRR |
| `consensus_gold_labels` | OUTCOME-gated — sealed until the gate's outcome-exposure point |
| `severity_stratum_manifest` (0a.-1.C §1.4b) | builder + design team ONLY — and these roles are MECHANICALLY DISJOINT from adjudicators (§4.1) because stratum is answer-bearing |
| packet internals / renderer output | the assigned first-pass adjudicator, the assigned tiebreaker, and authorized panel SMEs — for THEIR assigned claims only (Codex round-1 #4) |

### §4.1 Severity-stratum is answer-bearing (Codex round-1 #3)

`severity_stratum_manifest` exposes claim-level SUPPORTED/S0/S1/S2 — that IS (part of) the adjudication answer. Therefore:
- The builder/design-team role (which reads severity strata to scope P) is **mechanically disjoint** from ALL adjudication roles (constructor / first-pass adjudicator / tiebreaker / panel) for every blinding unit. An actor in the builder/design role cannot hold any adjudication role.
- The 0a.-1.A §2.2 validator is EXTENDED: it disqualifies any SME from first-pass/tiebreak/panel on a blinding unit if their exposure log shows a `severity_stratum` read for that unit (added to the existing constructor-intent / consensus / other-first-pass disqualifying reads).

Every access path (UI, CLI, direct storage, notebook, dashboard, export, CI) is wired to the §6 exposure log AND gated by the §9 deny-by-default broker. The 0a.-1.A §2.2 validator excludes any SME whose exposure log shows a disqualifying read.

## §5. Packet snapshots (full rendered, not just renderer hash — Codex plan redline)

For each packet, store the FULL, SELF-CONTAINED rendered snapshot + content hash, NOT only the renderer code hash. Self-contained means (Codex round-1 #5): final HTML/text, the cited spans, embedded assets/CSS/fonts (or their content hashes), the render parameters, AND a screenshot/PDF if visual rendering is decision-relevant. If the snapshot HTML still depends on EXTERNAL assets or live browser/client rendering, the gap is NOT closed — the snapshot must be inlined/frozen so it renders identically offline. Snapshots in `state/data_lineage/packet_snapshots/` (custody-controlled, role-scoped per §4).

## §6. Exposure log (reads AND writes — contract §P4.2)

Automatic, append-only, attached to ALL access channels (Codex round-1 #6 — expanded): UI, CLI, direct storage/object-store + CDN signed-URL access logs, notebooks, dashboards, stdout, exports/downloads, CI logs, screenshots, **temp files, browser/download/cache artifacts, backups/replicas, data-warehouse/BI copies, crash/trace/observability logs, ticket/chat/email attachments, and LLM/agent prompts/transcripts**. Manual self-report is NOT sufficient.

```
{ ts, actor (sme_id|process), action: enum[read,write],
  decision: enum[allow,deny], deny_reason?,    # broker decision (§9)
  artifact_id, exposure_class: enum[structural, outcome],   # contract §P4.2 split
  blinding_unit_id?, gate? }
```

Amendment eligibility (§P4) is driven by `decision=allow` reads of outcome-class artifacts (an actual exposure). `decision=deny` rows are broker audit events (an attempt that was blocked) — they do NOT count as exposure but ARE retained for audit.

Lives at `state/data_lineage/exposure_log.jsonl`. The `exposure_class` imports the COMPLETE contract §P4.2 event map (not examples):
- **structural**: Phase-0a pilot cluster size/P/N; final gold-set DEFF + per-stratum P/N/degree/relation-table-hash; canary customer count + m_i distribution + concentration; the 4 surrogate-ICC values; canary observed prevalence; eligibility-failure counts; per-cell denominator counts; domain/stratum/cell denominator + eligibility distributions; per-stratum severity-label distributions (the severity_stratum_manifest); missingness/prevalence/completeness audit; **`retrieved_source_count` + `target_packet_source_count` (D3 §3 — pre-outcome production-retrieval/downselect counts; structural diagnostic, not label-derived)**.
- **outcome**: per-stratum/cell/domain miss counts; severity-distribution AMONG MISSES; customer-distribution of affected reports; inter-rater agreement coefficient VALUES; **under-rating confusion matrices**; **retrieval recall numerators (P1)**; **extraction recall numerators (P2)**.

Amendment eligibility (§P4) is determined by this log, not by argument.

## §7. Calibration fixture (independent of gold set)

The SME-calibration claim set (0a.-1.A §3 / contract §7.1) is constructed independently of the gold-set holdout, hashed, and custody-controlled. Calibration claims are NEVER in the gold set (contract §P3 contamination). Hash in `hash_registry.jsonl`.

## §8. Replacement / drop rules (pre-registered — Codex plan redline)

Pre-registered handling (NOT ad-hoc). All reallocation occurs PRE-OUTCOME, from the SAME D8 cell, using the NEXT deterministic allocation draw (the `replacement-draw` child seed §3), and WITHOUT reading any verifier outcome or agreement coefficient (Codex round-1 #7):

- **Malformed claim**: a claim failing schema validation is dropped + logged + replaced from the same (domain × complexity × evidence-bin × severity × fab-type) cell via the next deterministic D8 draw, preserving the planned distribution.
- **Source 404 / unfetchable** — distinguish pre-SME vs post-SME:
  - PRE-SME (no rendered snapshot shown yet): re-snapshot from archive (§5 / 0a.-1.D archive_snapshot_url); if irrecoverable, reconstruct the packet and re-allocate (logged).
  - POST-SME (a rendered snapshot was already shown to an adjudicator): the packet MUST NOT be silently reconstructed — that would change what was adjudicated. The claim is quarantined; any replacement is a NEW claim via the next draw, and the original's labels are retained as-is (or invalidated explicitly), logged.
- **SME drop-out**: PENDING assignments re-assigned to a role-disjoint qualified SME (0a.-1.A); COMPLETED first-pass labels retained for IRR (already sealed).
- **Builder-run rejection** (fail-closed, 0a.-1.C §2.3): SAFE ONLY IF the failed run emits ONLY validation errors — P/N/DEFF must NOT be visible before the fix (else reruns become structural tuning). The offending row is fixed + re-validated; the run re-executed; both runs hashed.

All replacements/drops logged in `state/data_lineage/replacement_log.jsonl` with reason + cell + timestamp + draw-index. A replacement must preserve the D8 planned per-cell distribution (no silent distribution drift) and must not be informed by any outcome.

## §9. Exposure boundaries — deny-by-default access broker (Codex round-1 #8)

Logs RECORD; they do NOT DENY. The boundary needs an explicit **deny-by-default access broker** (or equivalent IAM/storage policy):

- Outcome-class artifacts (per §6 outcome list) for a gate are BLOCKED from read until the gate's registered `outcome_exposure_point` is reached (the gate's pre-registered analysis is authorized to run).
- EVERY access path — direct storage/object-store, exports/downloads, notebooks, CI jobs, dashboards, BI/warehouse copies, backups — MUST go through the broker (or an equivalent enforced IAM policy that denies by default). A path that bypasses the broker is a custody violation.
- The broker emits to the §6 exposure log on every allow AND every deny.
- Structural artifacts (stratum, denominators, DEFF, surrogate-ICC, concentration) are broker-allowed pre-outcome for the design/builder role (which is role-disjoint from adjudicators per §4.1).

The boundary is mechanical (deny-by-default broker + ACL + exposure_class + the 0a.-1.A validator's disqualifying-read check), NOT honor-system.

## §10. Definition of done (0a.-1.E)

Locked: immutable hash registry, code version pins, master seed, role-scoped storage ACLs, full packet snapshots, read+write exposure log with structural/outcome class, calibration fixture custody, pre-registered replacement/drop rules, mechanical exposure boundaries. Codex §-1.1 APPROVE. Operator sign-off.

After 0a.-1.E locks, the 0a.-1.C CODE half runs UNDER this custody (relation-builder + validators coded, hashed per §2, edge fixtures hashed per §1, the dry-run RUN executed and its output hashed) — only then does the dry-run count as evidence.

## §11. Dependencies + forward notes

- Needs D1a + 0a.-1.A + 0a.-1.B + 0a.-1.C-schema + 0a.-1.D (all LOCKED) ✓.
- Governs the 0a.-1.C CODE half (next), D6 SME templates, D5 prompt families, D8 allocation, and all gate executions.
- The `state/data_lineage/` directory (hash_registry, code_pins, master_seed, packet_snapshots, exposure_log, replacement_log, schemas) is created as part of the 0a.-1.C code half under this custody (this spec half does not create the literal files).
