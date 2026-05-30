# M3b build spec — Gate-B seam + transport no-leak + native annotations + offline seam test (I-meta-002 PR-9/M3b) — NO SPEND, NO NETWORK

The M3 DESIGN was APPROVED by Codex iter 2 (`.codex/I-meta-002-pr9-m3/codex_brief_verdict_iter2.txt`).
M3a (the native input builder `src/polaris_graph/roles/native_gate_b_inputs.py`) is committed
(30d5d733, diff-gate APPROVE iter 2). M3b wires it into the production path. NO real network, NO spend
anywhere; the offline seam test uses an INJECTED fake RoleTransport.

## Locked constraints (from the approved design)
- NATIVE-ONLY, NEVER the gold rubric. The seam + caller must NEVER read `outputs/dr_benchmark/`.
- NO MONEY / NO NETWORK in this PR. The seam test injects a fake transport; nothing deploys to Vast.
- D8 is the SINGLE binding gate. The seam must not introduce a second gate (the existing branch at
  run_honest_sweep_r3.py ~3139-3220 already overrides manifest release_allowed/status from D8 — reuse it).
- Fail-closed everywhere.
- snake_case; explicit imports; named constants; no except:pass; no unittest.mock in src/; no network in tests.
- Do NOT mutate the frozen claim_audit_scorer.py or the runtime lock (do NOT promote). Do NOT change M3a's
  builder logic (it is committed + APPROVE'd) — only CALL it.
- 200-LOC cap: keep production-code additions tight. The clinical.yaml annotation is data (not logic).
  If the diff approaches the cap, flag it for the diff-gate (M3a was accepted at ~213 logic lines).

## Pieces to build

### 1. Seam B in run_one_query (scripts/run_honest_sweep_r3.py) — builder WINS (Codex P2 #1)
READ run_one_query signature (~1206-1226) and the guarded 4-role branch (~3139-3220) first.
- Add a new keyword param to run_one_query: `four_role_input_builder=None` (default None →
  backward-compatible; existing callers + tests unaffected).
- In the guarded branch (when `PG_FOUR_ROLE_MODE` on AND `four_role_transport is not None`): if
  `four_role_input_builder is not None`, call it AFTER generation to PRODUCE the inputs+audit bundle —
  the BUILDER WINS over any directly-passed `four_role_inputs`. Pass it what M3a's
  `build_native_gate_b_inputs` needs: `multi`, the resolved scope `_template`, `q["slug"]`,
  `q["domain"]`, the run's resolved `evidence_lookup` (see piece 3), `model_slugs` (from the lock /
  the 3 verifier slugs), and `d8_config` (load_d8_policy_config). Use `bundle.inputs` for
  run_four_role_evaluation. If BOTH builder and four_role_inputs are None → the existing fail-closed
  raise stands. If only `four_role_inputs` is passed (static, e.g. a unit test) and no builder → use it
  as-is (builder precedence only applies when a builder is provided).
- AUDIT PERSISTENCE (Codex P2 #2): the SEAM (not the builder) writes `bundle.audit_map` to
  `run_dir / "four_role_claim_audit.json"` (json, sorted keys) so every claim_id is traceable
  alongside the run. The builder does NO file I/O.
- The existing manifest override (release_allowed/status from D8) is unchanged — verify it still fires.

### 2. M1 transport no-leak amendment (Codex key_handling_ruling = hard_require)
READ `src/polaris_graph/roles/openai_compatible_transport.py` `role_endpoint` + how it builds the
Authorization header. AMEND (narrowly) so the 3 SELF-HOST verifier roles (mirror/sentinel/judge):
- use ONLY `PG_<ROLE>_API_KEY`; NEVER fall back to `OPENROUTER_API_KEY`.
- when `PG_<ROLE>_API_KEY` is empty/unset → OMIT the Authorization header ENTIRELY (do NOT send
  `Authorization: Bearer ` with an empty value — Codex P2 #3). Keyless self-host vLLM is valid.
- Mirror M2's probe behavior exactly. Add/extend transport tests: per-role key set → `Bearer <key>`;
  unset → NO Authorization header AND `OPENROUTER_API_KEY` (even if present in env) is NOT used.
  (The generator path is unchanged — it is excluded from this transport and stays on OpenRouter.)

### 3. Evidence-record normalization (LOAD-BEARING — surfaced by M3a build)
M3a's `_claim_covers_entity` matches a claim's evidence record canonical id (doi/pmid/url) EXACTLY
against the entity's doi/pmid/url_pattern. But the frozen `EvidenceDocument` (role_transport.py) has
only `doc_id`+`text`, and the raw `evidence_pool.json` row carries only `source_url` (no doi/pmid/url
keys). So M3b must build the `evidence_lookup` the builder consumes: a deterministic mapping
`evidence_id -> {text, doi?, pmid?, url?}` derived from the run's actual evidence pool. Rules
(deterministic, native, no network):
- `url` = the record's `source_url` (verbatim, full canonical URL — not a fragment).
- `doi` = extracted from source_url/text by a deterministic DOI regex (`10.\d{4,9}/[-._;()/:A-Za-z0-9]+`)
  if present, else absent.
- `pmid` = extracted deterministically (e.g. a pubmed URL `/pubmed/<id>` or an explicit PMID token) if
  present, else absent.
- text = the evidence text (fail closed: empty text is already raised by the builder).
READ where run_one_query holds the evidence pool / corpus rows (the object the generator used —
the same evidence_id space as ProvenanceToken.evidence_id) so the lookup keys match the tokens.
Put this normalization in a small helper (in native_gate_b_inputs.py is fine since it's input-prep, OR
a tiny adjacent helper) — but do NOT change M3a's coverage/severity logic.

### 4. Gate-B production caller
A caller (a function, e.g. in a new `scripts/dr_benchmark/run_gate_b.py` or a guarded helper) that:
- constructs `OpenAICompatibleRoleTransport` for the 3 verifier roles (M1),
- sets `PG_FOUR_ROLE_MODE=1`,
- passes `four_role_transport` + `four_role_input_builder` (a closure over M3a's
  build_native_gate_b_inputs + the evidence normalization) into run_one_query,
- is NOT invoked by any test against a live endpoint (Gate-B live run is the later canary). The caller
  is wiring only; the offline test exercises the seam with a FAKE transport.

### 5. Native annotations on the existing clinical_tirzepatide_t2dm contract
In `config/scope_templates/clinical.yaml`, ADD to each `per_query_report_contract.clinical_tirzepatide_t2dm.required_entities[*]`:
- `severity: S0|S1|S2|S3` (pre-registered, native, derived from the entity's clinical role — NOT from
  any rubric/competitor source).
- when `severity: S0`: a valid `s0_category` (one of d8 s0_must_cover_categories: contraindications,
  dosing_limits, black_box_warnings, pregnancy_renal_hepatic_cautions, regulatory_status) AND a
  non-empty `coverage_content_requirements` list of NON-BLANK deterministic tokens/phrases (per the
  M3a validator — blank/empty will raise). Keep these minimal + defensible.
This is a non-benchmark contract; it is contamination-free to annotate. Do NOT annotate any benchmark
slug (those are the separate pre-registered prereq).

### 6. ONE offline seam test
`tests/dr_benchmark/test_gate_b_seam.py` (or tests/roles): drive run_one_query's 4-role branch (or the
seam path directly) with PG_FOUR_ROLE_MODE=1 + an INJECTED FAKE RoleTransport (returns canned
role responses, NO network) + the M3a builder over a FIXTURE-or-the-annotated-tirzepatide contract,
and assert: the D8 decision flows into `manifest['release_allowed']` + `manifest['status']`
(four_role_released/four_role_held), `four_role_claim_audit.json` is written to run_dir, builder-wins
precedence holds, and NO network/spend. Keep it hermetic (monkeypatch env, fake transport, tmp run_dir).

## Verify
python -c "import scripts.run_honest_sweep_r3" ; python -c "import src.polaris_graph.roles.openai_compatible_transport" ;
python -m pytest tests/roles tests/dr_benchmark tests/architecture -q ;
python -m scripts.architecture.verify_lock --consistency ;
python -m scripts.dr_benchmark.gate_a_dry_run
Report files changed + results + confirm no network/spend. Do NOT commit.
