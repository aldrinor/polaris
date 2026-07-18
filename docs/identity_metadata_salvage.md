# Machine-metadata identity salvage (Sol P5)

## What this is

A manifestation whose **rendered** bytes cannot establish identity is `UNRESOLVED_BINDING` — for
example a PDF whose title page is pure `(cid:NN)` glyph codes, or an HTML page whose readable body
mentions the requested authors only in its references. It is not a stranger's paper; it is an
**unreadable** one, and it stays a lead.

Salvage looks in the one place such a file may still positively identify itself: its
**machine-readable self-metadata**. Each recovered claim is stored as an `IdentityReceipt` — a named
container, a named field, a byte/char offset, a verbatim match, and a normalized value — and is
**revalidated against the raw artifact** every time the graph loads. A verified receipt is fed to
`event_ledger.derive_binding_core()`, which **re-derives** the semantic binding. Salvage never assigns
a verdict itself.

## Where it looks (self-metadata only)

| Media | Container | Fields |
|---|---|---|
| PDF (PyMuPDF/fitz) | `pdf_info`, `pdf_xmp` | DOI (Info string fields / `prism:doi` / `dc:identifier`), title (`title` / `dc:title`), author (`author`/`creator` / `dc:creator`) |
| HTML | `html_head` (`<head>` only) | `citation_doi` / `DC.identifier`, `citation_title` / `DC.title`, `citation_author` / `DC.creator` |
| JATS | `jats_front` (`<front><article-meta>` only) | `<article-id pub-id-type="doi">`, `<article-title>`, `<contrib contrib-type="author"><surname>` |

The rendered body, references, and `<back>` are **never** inspected.

## Promotion rule (positive proof only)

A manifestation is promoted only when one of these holds:

1. an **exact requested DOI** is present in a permitted self-identifier field; or
2. an **exact normalized requested title** *and* **at least one requested author** are present in
   permitted self-identity fields.

DOI normalization parses DOI URI/prefix forms, percent-decodes, case-folds, and strips terminal
citation punctuation. Title normalization applies NFKC, entity decoding, case-folding,
punctuation-to-space, and whitespace collapse; the title match is **exact** after normalization (no
fuzzy threshold). Author matching compares a requested surname to a structured surname **token** —
never a substring.

**Conflict:** if self-identifier fields contain both the target and a foreign DOI, the manifestation
stays `UNRESOLVED_BINDING` with `IDENTITY_METADATA_CONFLICT`. Title/author evidence cannot override a
conflicting self-identifier. Absence of metadata changes nothing.

## OCR status

```
IMAGE_OCR_IDENTITY_RECEIPT: BLOCKED
reason: no installed/revalidatable OCR backend; tesseract unavailable and no sudo
effect: residual glyph-header manifestations remain LEAD_ONLY
```

There is no OCR path. An `OCR`-typed receipt supplied through JSON is refused as an unsupported
receipt type, and the graph fails closed.

## Expected cohort measurement (audit counts, not thresholds)

```
initial unresolved: 155
machine-metadata promotions: ~67
residual unresolved leads: ~88
OCR promotions: 0
```

These are regression observations of the recorded corpus. No production rule reads them.
