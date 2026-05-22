# Codex review — I-p2-036 (#795): real canonical demo bundle (replaces placeholder fabricated proof)

HARD ITERATION CAP: 5. iter 1. Canonical-diff-sha256 `4484e8a8b8ade15cf4ad4ee5af8d0a47e330687ab12d2ecfc22f6d674bef0422`. web/ + scripts/ only. MERGE AUTHORIZED if mergeable. APPROVE iff zero P0/P1.

## Context (§-1.1 clinical-safety-critical)
The shipped demo bundle (v1_canonical_success, loaded by the live inspector) had PLACEHOLDER source text: claim "Tirzepatide is a dual GIP..." cited a span that was 'Full text body placeholder...' — i.e. the demo CENTERPIECE showed FABRICATED proof (the lethal trust-trap POLARIS exists to prevent). #795.

## What this does
- scripts/build_canonical_demo_bundle.py: maps the REAL run outputs/honest_sweep_r3/clinical/clinical_tirzepatide_t2dm (verification_details.json kept-sentences + tokens{evidence_id,start,end}; evidence_pool.json direct_quote = real fetched source text) into the v1.0 bundle format.
- §-1.1 GATE: strips inline [#ev:...] provenance tokens from the sentence (else token digits pollute the check), then a claim ships ONLY if every numeric token in it appears in the cited real source span. 1 claim dropped (numbers not in span).
- Output: 8 verified sentences / 4 sections / 4 real sources (NEJM, Lancet...). NO manifest.yaml.asc (operator chose skip-signature → inspector renders signaturePresent=false honestly). Old placeholder source/README/.asc deleted.

## Independent §-1.1 re-verification (I ran it): all 9 shipped provenance spans VERIFIED — every claim number present in its real source span. e.g. "−0.15 pp (95% CI −0.28 to −0.03), −0.39, −0.45" ↔ ev_006[8800:9300] real NEJM SURPASS-2 text.

## Files ALSO checked clean: web/lib/inspector_bundle_loader.ts (loads this path; manifest schema unchanged — content_type set {scope_decision,evidence_pool,verified_report,metadata,reasoning_trace,source_snapshot}); inspector renders verified_report.sections[].verified_sentences[].{sentence_text,provenance_tokens}; .gitignore !canonical_bundles exception keeps jsonl tracked.

## Review focus
1. §-1.1 HONESTY: is the gate sound (could any shipped claim's span NOT support it)? Token-strip correct? Any fabricated-proof risk remaining?
2. Schema: does the bundle match what inspector_bundle_loader.ts expects (manifest files[], evidence_pool.sources[].{source_id,full_text}, verified_report shape)? metadata.json has path=metadata.json content_type=metadata?
3. Are the 4 real sources safe to ship public (real published clinical abstracts/quotes; no secrets)? Signature-absent honest? Any P0/P1.

## Output schema
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
merge_decision: MERGE AUTHORIZED | DO NOT MERGE
```
