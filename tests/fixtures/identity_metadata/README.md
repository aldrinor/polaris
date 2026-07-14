# identity_metadata fixtures (Sol P5)

`build_fixtures.py` generates the raw artifacts (PDF via PyMuPDF/fitz, HTML, JATS) used by
`tests/test_identity_metadata_salvage.py`. Nothing binary is committed — every artifact is built
deterministically at test time.

Fixture families:

- **promoting** (6): PDF Info DOI, PDF XMP title+author, HTML `citation_doi`, HTML `DC.title`+`DC.creator`,
  JATS `article-id[doi]`, JATS `article-title`+`contrib` surname. Each must promote its manifestation
  out of `UNRESOLVED_BINDING`.
- **non-promoting** (4): target DOI only in references, target author only in body, generic self-title
  with no author, and target+foreign self-DOIs (conflict). None promote.
- **loader/refusal** (3, built inline in the test): tampered raw artifact, tampered receipt offsets,
  unsupported OCR receipt. All refuse the graph at load.

`DOMAINS` holds four unrelated Work identities (medicine / law / economics / CS) with identical
structure and different identifiers, so the metamorphic test swaps identity without touching any
extraction or production code.
