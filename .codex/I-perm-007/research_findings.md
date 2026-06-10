# I-perm-007 (#1201) — Features not delivering: quantified no-op + hard-PDF extraction

Durable copy of the StructuredOutput deliverable. Evidence base: saved beatboth8
(`outputs/audits/beatboth8/`). See StructuredOutput call for the authoritative version.

## Confirmed on saved data
- drb_75 quantified NO-OP = `spec_validation_rejected` (Writer dict failed build_quantified_spec); 2251 garbage numbers extracted, 0 survived.
- drb_76 quantified NO-OP = `no_spec_returned` from a TRUNCATED reasoning-model response (p2_run.log 12:50:31: content=370 chars, 1000/1000 out, 912 reasoning — budget burned on reasoning, empty JSON). NOT a clean Writer decline.
- Extractor pollution: manifest `quantified_analysis.conflicts` shows value=10.1038 (DOI prefix), label="coli](https://pure.knaw.nl/..." unit="%" — DOIs/altmetric-URLs/citation-fragments parsed as clinical numbers (evidence_extractor.py:31-73 regex on raw `direct_quote` markdown, L117).
- Hard-PDF loss: 904 `doi.org` + 124 mdpi + 72 OUP + 71 Wiley + Lancet/JAMA/Cell/Science URLs hit "ALL access methods exhausted"; Zyte browserHtml returns paywall stubs (66 doi.org "unusable"). docling NOT in requirements.txt (dead branch); only PyMuPDF + trafilatura installed.

## Root unification
Same cruft (DOIs, affiliation headers, altmetric URLs, nav) pollutes BOTH the numeric extractor (quantified no-op) AND span-binding (MASTER_FIX_PLAN B4 off-target spans). Structure-aware extraction is the shared spine.

## Migration spine
1. GROBID + grobid-quantities (CPU Java services, no GPU) as PDF→TEI structure + measurement/unit extraction, replacing regex-on-markdown.
2. Schema-constrained LLM spec_provider with reasoning-budget headroom + 1 retry + relaxed `_matches_datapoint` (ev_id+value+unit; drop byte-exact label/context).
3. openFDA/DailyMed structured-label API client (named fast-follow at domain_backends.py:642) — bypass hard clinical PDFs entirely.
4. Zyte browserHtml geolocation + actions config before declaring a source lost; else honest unreachable disclosure (I-perm-001 ALWAYS-RELEASE).
