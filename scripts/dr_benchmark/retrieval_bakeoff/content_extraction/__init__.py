"""content_extraction retrieval-bakeoff layer (I-ret-002, GH #1294).

Per-LAYER isolation bake-off for the content-extraction stage of the POLARIS
retrieval pipeline. This package scores deterministic extractors (Trafilatura,
MinerU-HTML, Resiliparse, jusText, readability, union) against labeled gold main
bodies using the WebMainBench OFFICIAL ROUGE-N F1 scorer (general axis) plus a
clinical TEDS table-fidelity subset. ReaderLM-v2 is benched ONLY as a
yardstick (generative -> never content-of-record).

Faithfulness engine (strict_verify / NLI / 4-role / provenance) is NEVER
touched by this layer: it scores extractor OUTPUT vs labeled reference only.
"""
