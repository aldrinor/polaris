"""Deterministic raw-artifact fixtures for the machine-metadata salvage tests (Sol P5).

Every fixture is a RAW artifact (PDF/HTML/JATS bytes) plus the requested identity (a tiny Work-shaped
object). No fixture uses the task-72 subject; identifiers and titles are invented per domain so the
tests can be metamorphosed across medicine/law/economics/CS by swapping the identity table alone.

The generated PDFs are built with PyMuPDF/fitz at call time — nothing binary is committed.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

import fitz  # PyMuPDF


@dataclass
class W:
    """A Work-shaped identity: exactly the fields identity_receipts + derive_binding_core read."""
    id: str = 'work:fixture'
    title: str = ''
    authors: list = field(default_factory=list)
    year: int | None = 2021
    venue: str | None = 'Some Journal'
    doi: str | None = None
    kind: str = 'study'


#: A generic, identity-free body. Readable words, but no byline, no DOI, no title match -> UNRESOLVED
#: when derive_binding_core sees it alone. This is the state salvage must start from.
GENERIC_BODY = ('This document presents an analysis of the observed phenomena and reports the '
                'associated measurements across several conditions. ' * 12)


def make_pdf(body: str = GENERIC_BODY, *, info: dict | None = None, xmp: str | None = None) -> bytes:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), body[:1500])
    if info:
        doc.set_metadata(info)
    if xmp:
        doc.set_xml_metadata(xmp)
    return doc.tobytes()


def xmp_packet(*, title: str = '', creator: str = '', doi: str = '') -> str:
    parts = ['<?xpacket begin="" id="W5M0MpCehiHzreSzNTczkc9d"?>',
             '<x:xmpmeta xmlns:x="adobe:ns:meta/">',
             '<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"'
             ' xmlns:dc="http://purl.org/dc/elements/1.1/"'
             ' xmlns:prism="http://prismstandard.org/namespaces/basic/2.0/">',
             '<rdf:Description>']
    if title:
        parts.append(f'<dc:title><rdf:Alt><rdf:li xml:lang="x-default">{title}'
                     '</rdf:li></rdf:Alt></dc:title>')
    if creator:
        parts.append(f'<dc:creator><rdf:Seq><rdf:li>{creator}</rdf:li></rdf:Seq></dc:creator>')
    if doi:
        parts.append(f'<prism:doi>{doi}</prism:doi>')
    parts += ['</rdf:Description>', '</rdf:RDF>', '</x:xmpmeta>', '<?xpacket end="w"?>']
    return ''.join(parts)


def html_head(metas: list[tuple[str, str]], body: str = GENERIC_BODY) -> bytes:
    tags = ''.join(f'<meta name="{n}" content="{c}">' for n, c in metas)
    return (f'<!doctype html><html><head><title>page</title>{tags}</head>'
            f'<body><article>{body}</article></body></html>').encode('utf-8')


def jats(*, doi: str = '', title: str = '', surname: str = '', body: str = GENERIC_BODY) -> bytes:
    ids = f'<article-id pub-id-type="doi">{doi}</article-id>' if doi else ''
    tg = f'<title-group><article-title>{title or "Untitled"}</article-title></title-group>'
    cg = (f'<contrib-group><contrib contrib-type="author"><name><surname>{surname}</surname>'
          '<given-names>A.</given-names></name></contrib></contrib-group>') if surname else ''
    return (f'<?xml version="1.0"?><!DOCTYPE article PUBLIC "-//NLM//DTD JATS">'
            f'<article><front><article-meta>{ids}{tg}{cg}</article-meta></front>'
            f'<body><p>{body}</p></body></article>').encode('utf-8')


# ── FOUR UNRELATED WORK IDENTITIES, one per domain. Structure identical; only identifiers differ. ──
DOMAINS: dict[str, W] = {
    'medicine': W(id='work:med', title='Longitudinal Cohort Outcomes In Adult Sepsis Care',
                  authors=['Okafor'], doi='10.1001/med.demo.4417', venue='Clinical Journal'),
    'law':      W(id='work:law', title='Doctrine Of Foreseeability In Modern Tort Liability',
                  authors=['Vasquez'], doi='10.2139/law.demo.8823', venue='Law Review'),
    'economics': W(id='work:econ', title='Wage Dispersion And Regional Labor Mobility Estimates',
                   authors=['Lindqvist'], doi='10.3386/econ.demo.2051', venue='Economics Journal'),
    'cs':       W(id='work:cs', title='Sparse Attention Kernels For Long Context Inference',
                  authors=['Nakamura'], doi='10.48550/cs.demo.1907', venue='CS Proceedings'),
}


def promoting_fixtures() -> list[dict]:
    """The six fixtures that MUST promote — one per admissible container/field shape."""
    d = DOMAINS['medicine']
    out = []
    # 1. PDF Info exact DOI (in a standard Info string field)
    out.append(dict(name='pdf_info_doi', media='pdf', work=d,
                    raw=make_pdf(info={'title': 'cover', 'subject': f'doi:{d.doi}'})))
    # 2. PDF XMP title + author
    out.append(dict(name='pdf_xmp_title_author', media='pdf', work=d,
                    raw=make_pdf(xmp=xmp_packet(title=d.title, creator='Ada Okafor'))))
    # 3. HTML citation_doi
    out.append(dict(name='html_citation_doi', media='html', work=d,
                    raw=html_head([('citation_doi', d.doi)])))
    # 4. HTML DC.title + DC.creator
    out.append(dict(name='html_dc_title_creator', media='html', work=d,
                    raw=html_head([('DC.title', d.title), ('DC.creator', 'Okafor, Ada')])))
    # 5. JATS article DOI
    out.append(dict(name='jats_article_doi', media='jats', work=d,
                    raw=jats(doi=d.doi, title='some title')))
    # 6. JATS title + contributor
    out.append(dict(name='jats_title_contrib', media='jats', work=d,
                    raw=jats(title=d.title, surname='Okafor')))
    return out


def non_promoting_fixtures() -> list[dict]:
    """Fixtures that MUST NOT promote (no positive self-metadata, or a conflicting self-identifier)."""
    d = DOMAINS['medicine']
    out = []
    # 7. target DOI only in references/body — NOT in any self-metadata field
    body = GENERIC_BODY + f' References: [1] Prior work, doi:{d.doi}.'
    out.append(dict(name='doi_only_in_references', media='html', work=d,
                    raw=html_head([('citation_title', 'An Unrelated Generic Report')], body=body),
                    expect='no_receipt'))
    # 8. target author only in body prose
    body2 = f'By some editor. Written up by Ada Okafor in the body. ' + GENERIC_BODY
    out.append(dict(name='author_only_in_body', media='html', work=d,
                    raw=html_head([('citation_title', 'An Unrelated Generic Report')], body=body2),
                    expect='no_receipt'))
    # 9. generic self-title, NO author
    out.append(dict(name='title_without_author', media='html', work=d,
                    raw=html_head([('DC.title', d.title)]), expect='no_receipt'))
    # 10. target AND foreign self-DOIs -> conflict
    out.append(dict(name='target_and_foreign_doi', media='html', work=d,
                    raw=html_head([('citation_doi', d.doi),
                                   ('DC.identifier', 'doi:10.9999/foreign.stranger.0001')]),
                    expect='conflict'))
    return out
