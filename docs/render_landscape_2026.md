# Render & Output Landscape 2025/2026 (I-render-001)

**Status:** research deliverable, operator-requested 2026-06-24. Section "render / output" of the standard
pipeline-section review (`docs/standard_process_pipeline_section_review.md`), joining retrieval
(`docs/retrieval_landscape_2026.md`), fetch/extraction (`docs/fetch_extraction_landscape_2026.md`),
consolidation (`docs/consolidation_landscape_2026.md`), credibility-tier (`docs/credibility_tier_landscape_2026.md`),
composition (`docs/composition_landscape_2026.md`), and verify-models (`docs/verify_models_landscape_2026.md`) docs.
**Method:** deep research — frontier searches fanned across two families (citation/bibliography FORMATTING and
verifiable/signed OUTPUT PACKAGING); every candidate primary-source verified (year + arXiv/GitHub/spec URL +
license); then a "is anything newer right now?" recency re-check; then every current-stack claim grounded against
the actual POLARIS repo (files read, not assumed).
**Scope (precise):** the FINAL pipeline stage — assembling the verified, consolidated, composed report into the
delivered artifact: `report.md` assembly, CITATION + BIBLIOGRAPHY formatting (numbered/author-year, dedup,
ordering, reference resolution), and the signed evidence bundle / manifest / export (PDF/HTML). Citation
INSERTION/FORMATTING is in scope; citation **VERIFICATION is FROZEN and OUT of scope** — strict_verify / NLI
entailment / 4-role D8 / provenance span-grounding / the SURE-RAG relevance gate / junk-sole-citation drop /
retention guard are the faithfulness ENGINE and are not touched here. The render layer only RESOLVES,
NUMBERS, ORDERS, DEDUPLICATES, and PACKAGES what the engine already verified.

---

## 0. The one-paragraph answer

The render frontier cleaves into two families, and they sit at very different distances from the current floor.
**Family 1 — citation/bibliography FORMATTING** (CSL/citeproc, Hayagriva, Typst, BibTeX): POLARIS's bespoke
`[#ev:id:start-end]` → `[N]` numbered-citation resolver in `resolve_provenance_to_citations` already satisfies the
mechanical-correctness contract (every in-text marker resolves to exactly one bibliography row, deterministic
first-cite ordering, dedup via `ev_to_num`), so CSL is an **interoperability ADD, not a fix** — worth adopting
only as an EXPORT format (CSL-JSON out, so a reviewer can re-style to Vancouver/APA), never as the in-pipeline
citation engine. **Family 2 — verifiable/signed OUTPUT PACKAGING** is where the genuine frontier value is, and it
is the higher-leverage axis by far. POLARIS's signed-bundle floor is a **single GPG key + `manifest.yaml` +
per-file SHA256 + a presence-only conformance check** (`audit_bundle/`), and conformance layer #3 explicitly
DEFERS the cryptographic `gpg --verify` to "operator-side tooling." The 2025/2026 frontier upgrade is a
standardized **attestation envelope + transparency receipt**: in-toto/DSSE statements (the vendor-neutral signed-
statement envelope), a Sigstore **Rekor v2** append-only transparency log (GA 2025, and — critically — **self-
hostable**, which is what makes it sovereign-compatible), and an IETF **SCITT** transparent-statement receipt
(draft-22, 2025-10, Standards Track) so a third party can verify the bundle was logged at a point in time without
trusting POLARIS's own clock. The single governing question for every candidate is one line, exactly parallel to
composition's Class-A/Class-B split: **does it run on self-hosted / offline-keyed / air-gapped infrastructure, or
does its value come from a hosted public-good service POLARIS cannot use without leaking to a public log and
depending on non-sovereign infra?** Public Fulcio/Rekor and the C2PA public Trust List FAIL that test (yardsticks
only); self-hosted Rekor, offline Ed25519/minisign keyed signing, a SCITT receipt from a sovereign transparency
service, and an RO-Crate JSON-LD provenance wrapper PASS it. The single highest-value, lowest-risk adoptable is
**a DSSE/in-toto attestation envelope around the existing manifest + a self-hosted transparency-log receipt** —
it upgrades the GPG-presence floor to a verifiable, append-only, third-party-checkable proof without changing one
byte of the faithfulness engine or the rendered prose.

---

## 1. What POLARIS has today (verified in the repo, not assumed)

The render FLOW (verified by reading the files): `kept_sentences (post-verify SentenceVerification objects) →
resolve_provenance_to_citations (strip [#ev:...] tokens, assign [N] numbers, build biblio rows, dedup, order) →
honest_pipeline assembles report.md (# title + body + ## Methods + ## Bibliography) + bibliography.json + manifest.json
→ build_audit_bundle (manifest.yaml + per-file SHA256 + GPG .asc → audit_<id>.tar.gz) → check_bundle_conformance
(12-layer shape verifier)`.

| Render stage | Current POLARIS implementation | Verified location |
|---|---|---|
| Token → numbered citation | `[#ev:<id>:<start>-<end>]` provenance tokens stripped; each distinct evidence_id assigned a 1-based `[N]` via `ev_to_num` on first-cite order; markers `"".join(f"[{n}]")` appended per sentence | `generator/provenance_generator.py:3654` (`resolve_provenance_to_citations_with_count`), `:3790` (`_num_for`), `:4092` |
| Bibliography rows | `{num, evidence_id, url, tier, statement[:300]}` per cited source; OPTIONAL basket enrichment (supporting members + weights + N verified independent origins + refuter cluster refs) when `baskets`+`cluster_id_by_evidence` passed | `provenance_generator.py:3790-3812` (`_num_for`), `_basket_for_biblio` |
| Dedup / ordering | A repeated evidence_id reuses its existing `[N]` (no duplicate biblio row); numbering is deterministic in FIRST-CITE order; `_files_unique_paths` validator forbids duplicate bundle paths | `provenance_generator.py:3790`; `audit_bundle/bundle_schema.py:170` |
| Degenerate-fragment drop at render | Resolver drops bare-punctuation+citation residue (`.[4]`) below the `_RESOLVE_MIN_CONTENT_WORDS=3` / `_RESOLVE_MIN_PROSE_CHARS=15` floor; F31 drops a sentence whose ONLY grounding was a bogus `[ev_slug]` marker | `provenance_generator.py:512-513, :3818-3892` |
| report.md assembly | `# Research report: <q>` + rendered body + `## Methods` (PRISMA-style disclosures, tier distribution, models, retrieval date, contradictions) + `## Bibliography` (`[N] statement — url (tier T)`) | `honest_pipeline.py:296-371` |
| bibliography.json | `json.dumps(biblio, indent=2, sort_keys=True)` — deterministic, sorted-keys | `honest_pipeline.py:372-375` |
| manifest.json (run-level) | `{run_id, domain, research_question, protocol_sha256, artifacts{...}, summary{counts}}` — the per-run pointer/summary, NOT the signed bundle manifest | `honest_pipeline.py:393-421` |
| Signed audit bundle | `manifest.yaml` (frozen-v1.0 `BundleManifest`: FK chain + per-`FileEntry` SHA256/size/content_type) + GPG-signed `manifest.yaml.asc` + content files, packed into `audit_<bundle_id>.tar.gz`; **refuses to ship unsigned** (`_default_sign_fn` raises) | `audit_bundle/bundle_builder.py:73-160`, `bundle_schema.py:136-188` |
| GPG signer | Detached ASCII-armored signature over the serialized manifest YAML | `audit_bundle/gpg_signer.py`, `manifest_builder.py` |
| Bundle conformance | 12-layer shape verifier: manifest parses; version==1.0; **signature PRESENCE only (defers `gpg --verify`)**; 6 required content types; path-traversal guard; per-file existence+SHA256+size; typed-JSON content parse; JSONL reasoning-trace parse | `audit_bundle/conformance.py:101-318` |
| EvidenceContract (pre-gen) | Operator-declared expectation contract (entities/claims/jurisdictions/tier-minimums) bound to the question, validated for internal consistency | `evidence_contract/schema.py:62-99` |
| Post-run artifact / API | `polaris_v6/api/bundle.py` GET endpoint + `artifact_to_evidence_contract.py` bridge + `web/lib/signed_bundle.ts` frontend mirror | `polaris_v6/api/bundle.py` |

**The crown-jewel constraint, verified.** The render layer NEVER resurrects a dropped sentence — "the basket is
assembled AFTER strict_verify; a dropped sentence never reaches this resolver, so no basket label can resurrect
it" (`provenance_generator.py:3752-3755`), and "the faithfulness engine runs UPSTREAM and is untouched"
(`:3683-3685`). The bundle builder REFUSES to ship unsigned (`_default_sign_fn` raises `NotImplementedError`,
`bundle_builder.py:59-70`), per LAW II. This is the render-layer invariant: it resolves/numbers/orders/packages,
it does not verify and does not relax.

**Three corrections to the naive "just bolt on CSL + Sigstore" framing, grounded in the repo:**

1. **The `[N]` resolver already satisfies mechanical correctness — CSL is interop, not a fix.** Every distinct
   evidence_id gets exactly one number, repeats reuse it, ordering is deterministic, no orphan biblio row is
   emitted (a row is only appended inside `_num_for`, which is only called for a surviving cited sentence). A
   CSL/citeproc engine would not make this MORE correct; it would only make the output RE-STYLEABLE
   (Vancouver/APA/AMA) and interoperable with reference managers. That is an EXPORT-format ADD (§6 ADD-3),
   not a render-engine replacement.
2. **The signed-bundle floor is a single GPG key + presence-only verify — this is the real frontier gap.** The
   bundle is cryptographically signed, which is already ahead of most deep-research tools (which ship nothing
   signed). But it uses one long-lived GPG key, the manifest is bespoke (not a standard attestation envelope),
   and conformance check #3 is PRESENCE-only. The frontier upgrade is a standard DSSE/in-toto envelope + a
   transparency-log receipt so verification is third-party and append-only, not "trust our key + our clock."
3. **Sovereignty is the adoption gate, not a footnote.** The two best-known frontier tools — Sigstore's public
   Fulcio/Rekor and C2PA's public Trust List — depend on HOSTED public-good infrastructure and (Rekor public)
   a PUBLIC transparency log. A sovereign clinical pipeline cannot leak run metadata to a public log or depend
   on a non-sovereign CA. The adoptable forms are the SELF-HOSTED / OFFLINE-KEYED variants of the same
   standards (§4).

---

## 2. The two adoptability gates (this is the crux)

Every render-frontier candidate is decided by two gates, in order:

- **Gate A — IS IT THE RENDER SURFACE OR THE FROZEN ENGINE?** Citation INSERTION/FORMATTING, bibliography
  styling, manifest/bundle packaging, signing, and export are RENDER (in scope). Citation VERIFICATION /
  relevance / entailment / span-grounding is the ENGINE (frozen, out). A candidate that decides whether a
  citation is *correct / supported / relevant* has crossed into the engine and is a yardstick at most — never an
  adoptable here. (The 2025/2026 LLM-citation-verification line — CiteCheck, "Cited but Not Verified", reference-
  hallucination detectors — is exactly this: it is engine work, positioned in §3 as context, never crowned here.)

- **Gate B — IS IT SOVEREIGN-DEPLOYABLE?** Self-hosted / offline-keyed / air-gapped → ADOPTABLE. Dependent on a
  hosted public-good service or a public transparency log or a non-sovereign CA → YARDSTICK only. This is the
  render analogue of composition's Class-A/Class-B split: it decides adoptability before any feature merit.
  Sigstore is adoptable ONLY in its self-hosted form (Rekor v2 + private Fulcio or keyed signing); C2PA is a
  yardstick until a sovereign cert chain exists; RO-Crate / in-toto-envelope / minisign / SCITT-with-a-sovereign-
  service all PASS.

The isolation axis (§5) tests Gate-A-passing, Gate-B-passing mechanisms on a FIXED composed-report fixture; a
Gate-A-failing or Gate-B-failing method can only ever enter the bake-off as a yardstick.

---

## 3. The 2025/2026 render frontier (primary-source verified)

Open-source-first (sovereignty). Year + URL + license per candidate. **G = which gate decides it.**

### Family 1 — Citation / bibliography FORMATTING (in scope; mostly interop ADDs, not fixes)

| Method | Year | Primary source | License | Gate | Role / why |
|---|---|---|---|---|---|
| **CSL 1.0.2 + CSL-JSON** | 2021-10 (1.0.2); styles repo actively maintained 2025 | docs.citationstyles.org/en/stable/specification.html ; github.com/citation-style-language/{schema,styles} | schema CC-BY-SA; styles CC-BY-SA; 10,000+ styles | A pass / B pass | **The interop standard.** Citation Style Language + CSL-JSON item metadata; 10,000+ free styles. ADOPT as an EXPORT format only (emit `bibliography.csl.json`, let a reviewer re-style), NOT the in-pipeline engine. Incumbent FLOOR for "how the world formats citations." |
| **citeproc-js** | maintained 2025 (Juris-M/Zotero) | github.com/Juris-M/citeproc-js | CPAL-1.0 (verify) / MIT-ish | A pass / B pass | The reference JS CSL processor; defined CSL-JSON. Yardstick for citation-rendering correctness; a JS runtime in a Python+sovereign pipeline is a poor fit — pattern/metric only. |
| **citeproc-rs** | active (Zotero), WASM-capable | github.com/zotero/citeproc-rs | MPL-2.0 (verify) | A pass / B pass | Rust rewrite of citeproc-js, WASM bindings, full CSL test-suite harness. **Honest status: still WIP / not feature-complete vs citeproc-js** — do not crown. If CSL export is ever wanted as a LINKED engine (not just a static export), this is the sovereign-friendly (Rust, offline) candidate to re-check at adoption time. |
| **Hayagriva** | active 2025 (Typst) | github.com/typst/hayagriva | Apache-2.0 / MIT (verify) | A pass / B pass | Rust bibliography engine behind Typst; supports all 2,600+ CSL styles; library + CLI; own YAML format. **The strongest sovereign citation-formatting candidate** (Rust, offline, Apache/MIT) IF POLARIS ever wants styled output. Still an interop ADD, not a correctness fix. |
| **Typst** | active 2025 | github.com/typst/typst ; typst.app/docs | Apache-2.0 | A pass / B pass | Modern structured typesetting; deterministic, scriptable, reproducible PDF; native bibliography via Hayagriva. Yardstick/option for a STYLED PDF EXPORT (§6 ADD-3) — far more reproducible than WeasyPrint HTML→PDF. |
| **BibTeX / biblatex** | incumbent | ctan.org | LPPL | A pass / B pass | The academic incumbent FLOOR. Yardstick only — LaTeX toolchain is heavy and non-sovereign-relevant; CSL-JSON is the modern interchange. |
| **Pandoc + citeproc** | maintained 2025 | github.com/jgm/pandoc | GPL-2.0+ | A pass / B pass | Universal document converter with built-in CSL citeproc; a Markdown→styled-PDF/HTML path. Option for the EXPORT step; GPL license = keep as a separate CLI tool, never linked into the sovereign binary. |

### Family 2 — Verifiable / signed OUTPUT PACKAGING (in scope; THE high-value frontier)

| Method | Year | Primary source | License | Gate | Role / why |
|---|---|---|---|---|---|
| **in-toto Attestation + DSSE** | spec active 2025; SLSA-recommended | github.com/in-toto/attestation | Apache-2.0 | A pass / **B pass** | **LEAD adoptable (envelope).** The vendor-neutral signed-statement format: a DSSE (Dead Simple Signing Envelope) wrapping a typed `subject + predicate` statement. The right standard envelope to wrap POLARIS's existing manifest in — replaces the bespoke `manifest.yaml.asc` shape with a standard, tool-verifiable one, WITHOUT changing what is signed (the per-file SHA256 set). Offline-keyable → sovereign. |
| **SLSA Provenance v1** | v1.0/1.1 stable 2025 | slsa.dev/spec/v1.1 ; github.com/in-toto/attestation/blob/main/spec/predicates/provenance.md | CC-BY-4.0 | A pass / B pass | The build-provenance PREDICATE type carried inside an in-toto attestation (where/when/how an artifact was produced). Pattern: model the POLARIS run as the "build" (inputs = corpus_snapshot + models + config; output = report.md + bundle) so provenance is expressed in a standard, reviewer-recognized schema. Adopt the PREDICATE PATTERN, not a build-system. |
| **Sigstore Rekor v2** | **GA 2025** | blog.sigstore.dev/rekor-v2-ga ; github.com/sigstore/rekor | Apache-2.0 | A pass / **B pass IFF self-hosted** | **Transparency-log adoptable — sovereign ONLY when self-hosted.** Append-only Merkle transparency log; v2 is tile-based, cheaper to self-host, CDN-cacheable, with witnessing integrated. **The public Rekor instance is a PUBLIC log → Gate-B FAIL for a sovereign clinical pipeline.** A SELF-HOSTED Rekor (private, on-prem) gives the append-only "this bundle existed at time T, log can't be rewritten" guarantee without leaking. The single biggest verifiability upgrade over the GPG floor. |
| **Sigstore cosign** | active 2025 | github.com/sigstore/cosign | Apache-2.0 | A pass / B pass (keyed mode) | Signs+logs artifacts; can use **keyed** signing (`cosign sign --key`) WITHOUT the public Fulcio keyless flow → sovereign. The signing CLI that pairs with self-hosted Rekor. Keyless/Fulcio mode = Gate-B FAIL (depends on public OIDC+CA). |
| **IETF SCITT** | **draft-22, 2025-10**, Standards Track | datatracker.ietf.org/doc/draft-ietf-scitt-architecture/ | IETF | A pass / **B pass IFF sovereign service** | **Transparent-statement RECEIPT standard.** A transparency service registers a signed statement (notarization), checks a policy, records it on an append-only ledger, and issues a verifiable RECEIPT. A reviewer verifies the receipt offline. **Still a DRAFT (not RFC)** — adopt the receipt PATTERN, watch for RFC. Sovereign IFF the transparency service is self-run. The standards-track sibling to Rekor; the two converge on "append-only signed-statement transparency." |
| **C2PA / Content Credentials 2.4** | **2.4, April 2026** | spec.c2pa.org/specifications/specifications/2.4 | spec open; needs X.509 cert | A pass / **B FAIL (today)** | **Document-embedded provenance — yardstick until a sovereign cert exists.** 2.4 adds embedding signed manifests into **PDF and HTML** (Appendix A) — the dream of "the exported report.pdf CARRIES its own signed provenance." But it requires **X.509 certs with the `c2pa-kp-claimSigning` EKU** and references the public **C2PA Trust List** → Gate-B FAIL for a sovereign pipeline today. Watch: a self-signed/private-CA C2PA chain would flip it to adoptable for embedding provenance INTO the delivered PDF. |
| **RO-Crate 1.2** | **1.2 stable LTS, 2025-06-04** | researchobject.org/ro-crate/specification/1.2 ; galaxyproject.org/news/2025-06-04 | Apache-2.0 / CC-BY | A pass / **B pass** | **Research-object packaging adoptable.** A lightweight JSON-LD (schema.org) metadata document packaging files + provenance (people, orgs, licensing, workflow runs, sources) as a portable, machine-readable crate. The natural sovereign WRAPPER to describe the bundle's contents + provenance graph in a standard reviewers/archives recognize. Pairs with (does not replace) the signed manifest. |
| **W3C PROV-O** | W3C REC (incumbent) | w3.org/TR/prov-o/ | W3C | A pass / B pass | The provenance ONTOLOGY (Entity/Activity/Agent, `wasDerivedFrom`, `wasGeneratedBy`). The vocabulary RO-Crate and a provenance graph express the "claim ← evidence ← source ← run" chain in. Pattern/vocabulary, not a tool. |
| **W3C Verifiable Credentials 2.0 + VC Data Integrity 1.0** | **W3C REC, 2025-05-15** | w3.org/news/2025/the-verifiable-credentials-2-0-family... ; w3.org/TR/vc-data-integrity/ | W3C | A pass / B pass | **NEW 2025 REC family** (VCDM 2.0, VC Data Integrity 1.0, EdDSA/ECDSA cryptosuites, JOSE/COSE securing). A way to express "POLARIS asserts this report meets contract X, signed" as a verifiable credential — heavier than DSSE/in-toto for artifact integrity; relevant if the deliverable must be an institution-verifiable CREDENTIAL, not just a signed file. Watch as the credential frontier; envelope-first (in-toto) is the lighter adopt. |
| **minisign / signify** | active 2025 | github.com/jedisct1/minisign | ISC / public-domain | A pass / **B pass** | **Sovereign offline-signing primitive.** Ed25519 detached signatures, dead-simple, no keyserver/identity infra, air-gap-friendly. The modern, low-complexity alternative to GPG for the OFFLINE keyed-signing case (PGP is "absurdly complex, crufty old crypto"). Candidate to REPLACE or COMPLEMENT the GPG signer if GPG key management is a pain — same trust model (one trusted public key), simpler crypto. Interoperates signify↔minisign. |

### Faithfulness-engine context (OUT of scope — positioned, never crowned here)

| Item | Year | Primary source | Role |
|---|---|---|---|
| "Cited but Not Verified" (source-attribution parsing/eval) | 2026-05 | arXiv:2605.06635 | ENGINE work (citation verification), not render. Context: the field is converging on "an inline citation that doesn't resolve/support is a defect" — which POLARIS's frozen engine already enforces. |
| CiteCheck (retrieval-grounded citation-hallucination detection) | 2026-05 | arXiv:2605.27700 | ENGINE work — yardstick for the frozen verifier, not a render adoptable. |
| "From Agent Traces to Trust" (provenance survey: SUPPORT/DERIVE/CONTRADICT relations) | 2026-06 | arXiv:2606.04990 | The typed-provenance VOCABULARY (SUPPORT/DERIVE/DEPEND-ON/CONTRADICT) is a useful pattern for what the RO-Crate/PROV-O graph should encode about the rendered report. Pattern-inspiration for the provenance WRAPPER, not the engine. |
| "Attesting LLM Pipelines: Enforcing Verifiable Training and Release Claims" | 2026-03 | arXiv:2603.28988 | On-point for the SIGNED-RELEASE-CLAIM idea: attest "this pipeline produced this output under these locked models/config." Directly supports the in-toto/SLSA-predicate ADD (model the run as a build, attest the release claim). |

---

## 4. The sovereignty gate (the load-bearing decision — exactly parallel to composition's Class-A trap)

The single most important render lesson is repo-and-mission-grounded: **POLARIS is a sovereign clinical pipeline,
so the frontier's most famous verifiability tools are adoptable ONLY in their self-hosted / offline-keyed forms.**

- **Sigstore public flow (Fulcio + public Rekor) = Gate-B FAIL.** Keyless signing mints a short-lived cert from a
  public CA via public OIDC, and logs to a PUBLIC transparency log. A sovereign clinical pipeline cannot (a)
  depend on a non-sovereign CA being up, nor (b) publish run/bundle metadata to a public log. **The adoptable
  form is self-hosted Rekor v2 + `cosign sign --key` (keyed) OR plain offline Ed25519/minisign** — same
  append-only-transparency guarantee, zero public leakage. Rekor v2's tile-based, cheap-to-self-host design
  (GA 2025) is precisely what makes this practical now; it was not before.
- **C2PA = Gate-B FAIL today.** Embedding signed provenance INTO the delivered `report.pdf`/`.html` (2.4,
  April 2026) is the most attractive single feature in the whole landscape — but it mandates X.509 certs with a
  C2PA-specific EKU and a public Trust List. Until a sovereign/private-CA C2PA chain is stood up, it is a
  yardstick. (Watch item: this is the one frontier feature worth re-checking every quarter.)
- **The adoptable sovereign stack (all Gate-B pass):** in-toto/DSSE envelope (Apache-2.0, offline-keyable) +
  self-hosted Rekor v2 receipt (or SCITT receipt from a self-run service) + RO-Crate 1.2 JSON-LD provenance
  wrapper + minisign/Ed25519 as the offline-signing primitive. None leaks; all run air-gapped; all are
  reviewer-/archive-recognized standards rather than a bespoke shape.

This is the render analogue of composition's binding rule: just as a Class-A free-generation body writer is
auto-rejected because it violates the provenance gate by construction, a hosted-public-service signing/transparency
tool is auto-rejected because it violates sovereignty by construction. The merit of the FEATURE is irrelevant
until Gate B passes. (Cross-ref the standing rule `feedback_avoidable_vs_structural_review_miss`: a recommendation
that adopts a public-log/public-CA tool for a sovereign pipeline is an AVOIDABLE miss, not a structural one.)

---

## 5. The isolation axis (render CORRECTNESS + bundle VERIFIABILITY on a FIXED composed-report fixture — NOT e2e)

**Hold retrieval + consolidation + composition + the faithfulness engine FIXED.** Bank a fixed composed-report
fixture = the OUTPUT of composition: a list of already-verified `SentenceVerification` objects carrying
`[#ev:...]` tokens + an `evidence_pool` + (optionally) baskets. Run the render layer on the SAME input. This
isolates render: it does NOT re-retrieve, NOT re-rank, NOT re-compose, NOT re-verify. The axis is a TEST LIST
(mechanical assertions), not prose:

**(a) Citation resolution correctness** (the core mechanical contract):
- Every in-text `[N]` resolves to exactly one bibliography row (`num` ↔ `evidence_id` bijection).
- No DANGLING reference: no `[N]` whose `evidence_id` is absent from the biblio list. **(Guaranteed today —
  every `[N]` comes from `_num_for`, which is what appends the row.)**
- No ORPHAN biblio row: every emitted biblio row is cited by ≥1 rendered sentence. **This is a REAL test that
  can FAIL today, NOT an assumed guarantee** — `_num_for` appends the biblio row at FIRST citation
  (`provenance_generator.py:4022, :4072`), but the **junk-sole-citation drop fires AFTER that append** and
  `continue`s the sentence out (`:4083-4090`, default-ON via `PG_COMPOSE_REQUIRE_ADEQUATE_TIER`). So a source
  cited ONLY by junk-only-dropped sentences leaves an orphan row whose `[N]` never appears in the body. (The
  degenerate-fragment `:4892` and F31 `:4866` drops `continue` BEFORE `_num_for`, so those paths are clean — the
  asymmetry is specifically the junk-only drop.) See FIX-7.
- No DUPLICATE: a repeated evidence_id reuses its `[N]` (one row per source).
- Numbering is contiguous `1..N` in FIRST-CITE order (deterministic ordering).

**(b) Determinism / reproducibility** (the LANDMINE — flagged explicitly):
- RE-RENDER the SAME fixture twice → `report.md` body + `bibliography.json` are BYTE-IDENTICAL.
- **CAVEAT (the landmine a self-test will miss):** `BundleManifest.bundle_created_at_utc` defaults to
  `datetime.now()` and `bundle_id` to `uuid4()` — both NONDETERMINISTIC. A byte-reproducibility test of the
  BUNDLE must INJECT a fixed clock + fixed bundle_id, OR scope the reproducibility claim to "content-file SHA256s
  are stable" (the report.md/bibliography.json/source files), NOT the manifest header. **Decision to state in the
  bake-off:** bundle reproducibility is hash-consistency-at-verify (the SHA256 set re-verifies), NOT full
  byte-reproducibility of the manifest, unless a deterministic-id/clock mode is added. (This is the exact class of
  miss the §-1.4 "committed ≠ behaviorally proven" discipline catches.)

**(c) Bundle verifiability** (the signed-output contract):
- `build_audit_bundle(...)` → extract → `check_bundle_conformance(extracted_dir)` returns `valid=True`.
- TAMPER TEST (fail-loud): flip one content byte after signing → conformance flips to `valid=False` with
  `SHA256_MISMATCH`; flip a manifest field → schema/version error; remove the `.asc` → `MISSING_SIGNATURE`.
- The unsigned-refusal holds: calling `build_audit_bundle` without a `sign_fn` raises (never ships unsigned).
- **Frontier-delta assertions** (what a candidate must improve): a DSSE/in-toto envelope re-verifies with a
  standard verifier (`cosign verify-blob` keyed, or a DSSE checker) on the SAME byte set; a self-hosted Rekor
  receipt re-verifies the inclusion proof offline; the tamper test still flips it to fail.

**(d) Format-fidelity** (citation styling, if a CSL export ADD is in the bake-off):
- A CSL-JSON export of the bibliography round-trips through citeproc-rs/Hayagriva to a styled list whose entry
  COUNT and source identity match the `[N]` set (no entry added/dropped by styling). Styling NEVER changes which
  sources are cited — only their textual rendering.

**Clinical slice.** On a banked clinical composed-report fixture, render must: preserve the contradiction-
disclosure block verbatim (the `## Contradiction disclosures` / Methods polarity is byte-faithful — no styling pass
flips "not recommended"); never drop a cited safety source from the bibliography; keep the per-claim
basket/weight disclosure rows intact in the biblio when baskets are present. A dropped safety citation or a
flipped disclosure polarity at render is an automatic fail regardless of (a)–(d).

**Behavioral acceptance (§-1.4):** the effect must APPEAR in the real rendered output + bundle on the banked
fixture and FAIL LOUD if it does not — not "green tests," not "Codex approved the diff." The standalone bake-off
SELECTS the mechanism; the integrated POLARIS run DECIDES; a §-1.1 line-by-line audit of the winning output +
a real `gpg --verify`/`cosign verify` of a real bundle is required before any LOCK.

---

## 6. KEEP vs ADD vs FIX against current POLARIS

**The render layer is mechanically correct and already cryptographically signed — genuinely ahead of deep-research
tools that ship nothing signed. Gaps are concentrated in (i) verification STANDARDIZATION + transparency and (ii)
optional interop EXPORT, not in correctness.**

### KEEP (verified present and correct — render-surface, faithfulness-preserving)
- **`[#ev:...]` → `[N]` numbered-citation resolver** (`resolve_provenance_to_citations`). Bijective, dedup'd,
  deterministic first-cite ordering, no dangling `[N]` (every marker comes from `_num_for`). The core mechanical
  contract is met; keep. **Caveat (not a structural guarantee):** orphan-row-freedom is NOT guaranteed because
  the junk-sole-citation drop returns AFTER `_num_for` already appended the row (`:4083-4090`) — see FIX-7.
- **Degenerate-fragment + bogus-marker drop at render** (F10/F31). Keeps `.[4]` residue and `[ev_slug]`-only
  sentences out of the shipped report; keep.
- **Deterministic `bibliography.json`** (`sort_keys=True`). Keep.
- **Frozen-v1.0 `BundleManifest` + per-file SHA256 + unsigned-refusal** (`audit_bundle/`). The signed-bundle
  spine; keep the schema freeze discipline (the bump cascade) and the LAW-II refuse-to-ship-unsigned sentinel.
- **12-layer `check_bundle_conformance` shape verifier** (incl. path-traversal guard + reasoning-trace filename
  pin). Keep; extend (FIX-1) to optionally do cryptographic verify.
- **basket-carrying bibliography enrichment** (supporting members + weights + independent-origin count). The
  surface that makes the corroboration visible in the deliverable; keep.

### ADD / FIX (priority order — all advisory; the frozen faithfulness engine is never relaxed)
1. **DSSE/in-toto attestation envelope + self-hosted transparency-log receipt (the biggest genuine ADD).** Wrap
   the existing `manifest.yaml` (the per-file SHA256 set) in a standard DSSE/in-toto `subject+predicate`
   statement (SLSA-provenance predicate: inputs = corpus_snapshot+models+config, output = report.md+bundle),
   sign it offline (keep GPG or move to Ed25519/cosign-keyed), and register it with a SELF-HOSTED Rekor v2 (or a
   self-run SCITT service) to get an append-only, third-party-verifiable receipt. Upgrades the GPG-presence floor
   to "verifiable, append-only, no-trust-our-clock" WITHOUT changing what is signed or one byte of prose.
   Sovereign by construction (offline keys + self-hosted log). *(Primary: in-toto/attestation; Rekor v2 GA 2025;
   SCITT draft-22; arXiv:2603.28988 for the release-claim attestation pattern.)*
2. **FIX conformance check #3 to do REAL cryptographic verification (close the presence-only gap).** Today layer
   #3 only checks the `.asc` is present+non-empty and DEFERS `gpg --verify` to "operator tooling" — so a
   structurally-conformant-but-cryptographically-INVALID bundle passes `valid=True`. ADD an optional verify mode
   (`check_bundle_conformance(..., verify_signature=True)`) that runs the actual `gpg --verify` / DSSE / cosign
   verify and a FULL re-hash, so the emitter's own check matches what a reviewer runs. This is a §-1.4
   "committed ≠ verified" close: the presence-only check is exactly the kind of silent no-op the discipline warns
   about. Faithfulness-neutral (bundle integrity, not claim verification).
3. **CSL-JSON bibliography EXPORT (interop ADD, NOT a fix — say so).** Emit `bibliography.csl.json` alongside
   `bibliography.json` so a reviewer can re-style to Vancouver/APA/AMA via Hayagriva/citeproc-rs and import into a
   reference manager. The bespoke `[N]` already satisfies mechanical correctness, so CSL is interoperability, not
   correctness — additive export only, never the in-pipeline citation engine.
4. **RO-Crate 1.2 JSON-LD provenance wrapper around the bundle (standards-recognized packaging ADD).** Describe
   the bundle's files + the "claim ← evidence ← source ← run" provenance graph (PROV-O / the SUPPORT-DERIVE
   typed relations from arXiv:2606.04990) as a portable schema.org JSON-LD crate, so archives/reviewers ingest
   the deliverable with a standard tool. Pairs with (does not replace) the signed manifest. Sovereign (offline
   JSON-LD).
5. **Reproducibility mode for the bundle (close the determinism landmine §5b).** Add a deterministic-id + fixed-
   clock mode (inject `bundle_id` + `bundle_created_at_utc`) so a bundle is byte-reproducible from the same
   inputs, OR explicitly document that the reproducibility guarantee is "content-file SHA256 set is stable," not
   the manifest header. State the chosen guarantee; do not leave it implicit.
6. **Styled PDF export via Typst+Hayagriva as a sovereign reproducible alternative to WeasyPrint (optional).**
   If a styled PDF deliverable is wanted, Typst (Apache-2.0, deterministic, native Hayagriva bibliography) is a
   more reproducible, more sovereign path than HTML→WeasyPrint. Export-step option, not a pipeline change.
7. **FIX the orphan-biblio-row asymmetry (repo-grounded defect found auditing the resolver §5a).** `_num_for`
   appends a biblio row at first citation (`provenance_generator.py:4022, :4072`), but the default-ON
   junk-sole-citation drop `continue`s a sentence out AFTER that append (`:4083-4090`), so a source cited only by
   junk-only-dropped sentences leaves an orphan row whose `[N]` never appears in the body. (Dangling-`[N]`-freedom
   is fine — every `[N]` comes from `_num_for`; only the row→body direction breaks.) Fix surgically: either DEFER
   `_num_for`/row-append until AFTER all drop gates (assign numbers from the final surviving cite set), or PRUNE
   biblio rows whose `num` never appears in the rendered body at the end of the loop. Render-surface only;
   faithfulness-neutral (a dropped sentence stays dropped — this only removes its now-uncited bibliography entry).

### DO NOT add
- **Sigstore public keyless flow (Fulcio + public Rekor)** as the signer — Gate-B FAIL (non-sovereign CA +
  PUBLIC transparency log). Only the self-hosted Rekor + keyed-cosign / offline-Ed25519 form is adoptable.
- **C2PA document-embedded provenance with the public Trust List / mandated EKU certs** — Gate-B FAIL today.
  Yardstick + quarterly watch item until a sovereign private-CA C2PA chain exists.
- **citeproc-js (JS runtime) linked into the sovereign Python binary** — wrong runtime; use Rust (Hayagriva/
  citeproc-rs) or a static CSL-JSON export instead.
- **Any render change that re-numbers/re-orders citations non-deterministically, drops a cited source from the
  bibliography, or styles the contradiction/safety disclosure in a way that could flip polarity** — violates the
  mechanical-correctness + clinical-slice contract.
- **Treating CSL adoption as a correctness FIX** — it is interop only; crowning it would misframe the gap (the
  real gap is verification standardization + transparency, not citation styling).
- **Any external Sigstore/C2PA/SCITT RUNTIME pulled in as a hosted dependency** — patterns + self-hosted/offline
  forms only; the deliverable must verify air-gapped.

---

## 7. The render bake-off candidate list (the next step)

Open-source-first (sovereignty). **Acceptance is behavioral (§5), not a vendor badge:** run each candidate on the
banked composed-report fixture, hold everything upstream FIXED, measure citation-resolution correctness /
determinism / bundle-verifiability / format-fidelity + the clinical slice + a REAL crypto verify of a real bundle.
The standalone test selects; the integrated POLARIS run decides; a §-1.1 audit gates the LOCK.

**Floor (the control arm):** current POLARIS `[N]` resolver + GPG-signed `BundleManifest` bundle +
12-layer conformance. Always in the bake-off — never bake-off only the new candidates.

**Signing / transparency mechanism (Family 2, the real adoptable contest):**
- DSSE/in-toto envelope + self-hosted Rekor v2 receipt — **lead candidate** (in-toto/attestation; Rekor v2 GA 2025)
- DSSE/in-toto envelope + self-run SCITT receipt (SCITT draft-22) — standards-track sibling; watch RFC
- Current GPG-signed bespoke `manifest.yaml.asc` (the floor)
- minisign/Ed25519 offline signer (jedisct1/minisign) — simpler-crypto replacement for the GPG signer

**Conformance / verification (FIX-2):**
- Current presence-only `check_bundle_conformance` (floor)
- Verify-enabled mode (real `gpg --verify` / DSSE / cosign verify-blob + full re-hash)

**Citation / bibliography EXPORT (Family 1, interop ADD):**
- Current `[N]` resolver + `bibliography.json` (floor)
- CSL-JSON export → Hayagriva/citeproc-rs styling (Hayagriva Apache/MIT; citeproc-rs MPL-2.0) — interop only

**Provenance packaging:**
- RO-Crate 1.2 JSON-LD wrapper (researchobject.org, 2025-06-04 LTS)
- W3C PROV-O / typed-provenance relations (arXiv:2606.04990) as the graph vocabulary

**Document-embedded provenance (yardstick / quarterly watch):**
- C2PA 2.4 PDF/HTML manifest embedding (spec.c2pa.org 2.4, April 2026) — re-check when a sovereign cert chain exists
- W3C Verifiable Credentials 2.0 family (W3C REC 2025-05-15) — if the deliverable must be an institution-
  verifiable credential

**Yardsticks-to-beat (Gate-B FAIL / engine / non-adoptable as-is):**
- Sigstore public keyless (Fulcio+public Rekor), public C2PA Trust List, citeproc-js JS runtime, the LLM-citation-
  verification line (CiteCheck / "Cited but Not Verified" — engine, not render). Bench against these; never adopt
  their non-sovereign/engine form.

**Benchmarks (per `standard_process_pipeline_section_review.md`):** render primarily affects the FAITHFULNESS-
PRESENTATION axis (DeepTRACE: every citation must resolve to a real bibliography entry — a dangling/duplicate ref
is a render defect that LOOKS like a faithfulness defect) without touching coverage (DeepResearch Bench II). The
signed-bundle verifiability is POLARIS's differentiator, not a public-leaderboard metric; the bake-off measures it
mechanically (§5c), not against a vendor score.

---

## 8. Honest uncertainty + license flags (verify before adoption)

### Uncertainty
- **The signed-bundle ADD is a PATTERN recommendation, not yet run on POLARIS.** in-toto/DSSE + self-hosted
  Rekor v2 is the strongest adoptable on standards-merit + sovereignty grounds, but it has not been wired into
  `audit_bundle/`. Frontier-tech rule: pattern-inspiration until a self-hosted Rekor + DSSE envelope is stood up
  and a real bundle re-verifies offline on the banked fixture.
- **SCITT is a DRAFT (draft-22, 2025-10), not an RFC.** Adopt the receipt PATTERN, not a frozen wire format;
  re-check RFC status before locking to its exact CBOR/COSE shapes.
- **citeproc-rs is WIP / not feature-complete vs citeproc-js.** Do not crown it; if linked CSL styling is ever
  wanted, re-verify its CSL test-suite pass rate at adoption time. Hayagriva (Typst's engine, 2,600+ styles) is
  the more mature sovereign Rust option.
- **C2PA document-embedding is the single most attractive feature but Gate-B FAILS today.** The sovereignty
  blocker (mandated EKU certs + public Trust List) is real; whether a private-CA C2PA chain is practical for a
  clinical pipeline is an open question worth a dedicated spike. Quarterly recency re-check warranted — this is
  the fastest-moving frontier item.
- **The reproducibility guarantee is currently IMPLICIT.** `bundle_created_at_utc`/`bundle_id` are
  nondeterministic; whether full bundle byte-reproducibility is even a goal (vs SHA256-set stability) must be
  decided, not assumed (§5b).

### License flags
- **in-toto/attestation, SLSA, Sigstore (cosign/Rekor), Typst, Hayagriva, RO-Crate:** Apache-2.0 (+ MIT for some
  Hayagriva deps) — **OSS-deployable, sovereign-friendly.** Verify each repo LICENSE before code reuse; adopt
  self-hosted/offline forms only.
- **minisign/signify:** ISC / public-domain — clean.
- **CSL schema + styles:** CC-BY-SA; **citeproc-rs:** MPL-2.0; **citeproc-js:** CPAL-1.0 (verify) — used as
  export-format/metric, low-risk; do NOT link citeproc-js JS into the sovereign binary.
- **Pandoc:** GPL-2.0+ — keep as a SEPARATE CLI tool (GPL), never linked into the sovereign binary.
- **C2PA spec:** open spec, but signing REQUIRES X.509 certs + the public Trust List → not adoptable until a
  sovereign cert chain exists. **W3C VC 2.0 / PROV-O / VC Data Integrity:** W3C REC, open — standards/vocabulary,
  no runtime lock-in.
- **Clean to use as PATTERN/standard (no hosted dependency pulled into the sovereign binary):** all Family-2
  adoptables in their self-hosted/offline form. The deliverable must verify air-gapped.

Verified current-POLARIS files: `generator/provenance_generator.py` (`resolve_provenance_to_citations*`,
`_num_for`, F10/F31 render drops), `honest_pipeline.py` (report.md/bibliography.json/manifest.json assembly),
`audit_bundle/{bundle_builder,bundle_schema,conformance,gpg_signer,manifest_builder}.py` (signed bundle),
`evidence_contract/schema.py` (pre-gen contract), `polaris_v6/api/bundle.py` (post-run API).

---

## 9. Recency audit (2026-06-24) — is this 2025/2026 frontier, or did old methods sneak in?

Operator challenge: "Are these the 2025/2026 best way, not old old methods?" Re-checked at research time; every
candidate date-verified against its primary source; reject pre-2024 unless it is the genuine incumbent floor.

**Verdict: frontier-current.** The pre-2025 items present are the genuine incumbent FLOORs (GPG signing,
CSL 1.0.2 / citeproc-js 2021, BibTeX, W3C PROV-O) and are labeled as such; none is crowned as the current
adoptable. The adoptable contest is led by the **2025 GA + 2025/2026 standards cohort**: Sigstore Rekor v2 (GA
2025), in-toto/SLSA attestations (active 2025), RO-Crate 1.2 (2025-06-04 LTS), W3C VC 2.0 family (REC 2025-05-15),
IETF SCITT draft-22 (2025-10), and C2PA 2.4 (April 2026).

| Method | Year | Status in this report |
|---|---|---|
| GPG / OpenPGP signing | incumbent | Floor (the current signer); candidate to simplify via minisign |
| CSL 1.0.2 / citeproc-js | 2021 | Interop FLOOR; export ADD only, not a fix |
| BibTeX / biblatex | incumbent | Academic floor; yardstick only |
| W3C PROV-O | W3C REC | Provenance vocabulary (incumbent) |
| in-toto / SLSA attestation | active 2025 | **LEAD adoptable (DSSE envelope + SLSA predicate)** |
| Sigstore Rekor v2 | **GA 2025** | Transparency-log adoptable — sovereign IFF self-hosted |
| RO-Crate 1.2 | **2025-06-04 LTS** | Provenance-packaging adoptable (JSON-LD) |
| W3C VC 2.0 family | **REC 2025-05-15** | Credential frontier; envelope-first is the lighter adopt |
| citeproc-rs / Hayagriva | active 2025 | Sovereign Rust CSL formatting (Hayagriva mature; citeproc-rs WIP) |
| Typst | active 2025 | Reproducible styled-PDF export option |
| IETF SCITT | **draft-22, 2025-10** | Receipt PATTERN; watch RFC |
| C2PA 2.4 | **April 2026** | Document-embedded provenance — yardstick (Gate-B FAIL today), quarterly watch |
| LLM-citation-verification line (CiteCheck etc.) | 2026 | ENGINE context, never crowned as render |

**What the recency pass says we should keep watching (the field moves monthly):** the verifiable-output frontier
is converging on the triad **standard signed-statement envelope (in-toto/DSSE) + append-only transparency
(Rekor v2 / SCITT) + portable provenance packaging (RO-Crate/VC)**. The single fastest-moving watch item is
**C2PA document-embedding** (the only path to "the report.pdf carries its own signed provenance"), gated entirely
on a sovereign cert chain. A fresh "is anything newer?" search — especially on SCITT RFC status and a
sovereign-C2PA path — should run again at bake-off time.

---

## 10. Primary sources (2025/2026)
- in-toto Attestation Framework + DSSE — github.com/in-toto/attestation (LEAD envelope adoptable, Apache-2.0)
- SLSA Provenance v1 — slsa.dev/spec/v1.1 ; github.com/in-toto/attestation/blob/main/spec/predicates/provenance.md
- Sigstore Rekor v2 (GA 2025) — blog.sigstore.dev/rekor-v2-ga ; github.com/sigstore/rekor (self-hosted transparency log)
- Sigstore cosign — github.com/sigstore/cosign (keyed signing = sovereign; keyless = Gate-B FAIL)
- IETF SCITT — datatracker.ietf.org/doc/draft-ietf-scitt-architecture/ (draft-22, 2025-10, Standards Track; receipt pattern)
- C2PA / Content Credentials 2.4 — spec.c2pa.org/specifications/specifications/2.4 (April 2026; PDF/HTML embed; Gate-B FAIL today)
- RO-Crate 1.2 — researchobject.org/ro-crate/specification/1.2 ; galaxyproject.org/news/2025-06-04 (2025-06-04 LTS, JSON-LD)
- W3C Verifiable Credentials 2.0 family — w3.org/news/2025/the-verifiable-credentials-2-0-family... ; w3.org/TR/vc-data-integrity/ (REC 2025-05-15)
- W3C PROV-O — w3.org/TR/prov-o/ (provenance vocabulary)
- CSL 1.0.2 + CSL-JSON — docs.citationstyles.org/en/stable/specification.html ; github.com/citation-style-language/styles (interop export)
- citeproc-rs — github.com/zotero/citeproc-rs (Rust/WASM CSL, MPL-2.0, WIP)
- Hayagriva — github.com/typst/hayagriva (Rust bibliography, 2,600+ CSL styles, Apache/MIT)
- Typst — github.com/typst/typst (reproducible styled PDF, Apache-2.0)
- minisign — github.com/jedisct1/minisign (Ed25519 offline signing, ISC)
- "Attesting LLM Pipelines: Enforcing Verifiable Training and Release Claims" — arXiv:2603.28988 (release-claim attestation pattern)
- "From Agent Traces to Trust" (provenance survey) — arXiv:2606.04990 (typed-provenance vocabulary for the wrapper)
- ENGINE context (out of scope): "Cited but Not Verified" arXiv:2605.06635 ; CiteCheck arXiv:2605.27700
- Cross-ref: composition (citation INSERTION) — `docs/composition_landscape_2026.md` ; verify (citation VERIFICATION) — `docs/verify_models_landscape_2026.md`
