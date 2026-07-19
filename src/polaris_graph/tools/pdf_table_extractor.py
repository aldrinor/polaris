"""GAP-2: PDF table extraction using pdfplumber.

Extracts tables from academic PDFs as structured data (list of dicts).
Tables are a critical data source in academic papers that text extraction misses.

Requires: pdfplumber (installed via package_installer if needed)
"""

import logging
import os
from pathlib import Path
from typing import Optional
from src.polaris_graph.settings import resolve

logger = logging.getLogger("polaris_graph")

_MAX_PAGES = int(resolve("PG_PDF_TABLE_MAX_PAGES"))
_MIN_ROWS = int(resolve("PG_PDF_TABLE_MIN_ROWS"))
_MIN_COLS = int(resolve("PG_PDF_TABLE_MIN_COLS"))


def _ensure_pdfplumber():
    """Ensure pdfplumber is available, install if needed."""
    try:
        import pdfplumber
        return pdfplumber
    except ImportError:
        from src.polaris_graph.tools.package_installer import safe_install
        result = safe_install(["pdfplumber"])
        if result["installed"] or result["already_installed"]:
            import pdfplumber
            return pdfplumber
        raise ImportError(
            f"pdfplumber not available and install failed: {result.get('errors', [])}"
        )


def extract_tables_from_pdf(
    pdf_path: str,
    max_pages: int = _MAX_PAGES,
) -> list[dict]:
    """Extract all tables from a PDF file.

    Args:
        pdf_path: Path to PDF file.
        max_pages: Maximum pages to scan.

    Returns:
        List of table dicts:
        [
            {
                "page": int,
                "table_index": int,
                "headers": [str],
                "rows": [[str]],
                "markdown": str,
                "row_count": int,
                "col_count": int,
            },
            ...
        ]
    """
    pdfplumber = _ensure_pdfplumber()

    path = Path(pdf_path)
    if not path.exists():
        logger.warning("[pdf_tables] File not found: %s", pdf_path)
        return []

    tables = []
    try:
        with pdfplumber.open(path) as pdf:
            pages_to_scan = min(len(pdf.pages), max_pages)
            for page_num in range(pages_to_scan):
                page = pdf.pages[page_num]
                page_tables = page.extract_tables() or []

                for table_idx, raw_table in enumerate(page_tables):
                    if not raw_table or len(raw_table) < _MIN_ROWS:
                        continue

                    # First row as headers
                    headers = [str(cell or "").strip() for cell in raw_table[0]]
                    if len(headers) < _MIN_COLS:
                        continue

                    # Remaining rows as data
                    rows = []
                    for row in raw_table[1:]:
                        cleaned = [str(cell or "").strip() for cell in row]
                        if any(cleaned):  # Skip completely empty rows
                            rows.append(cleaned)

                    if not rows:
                        continue

                    # Build markdown table
                    markdown = _table_to_markdown(headers, rows)

                    tables.append({
                        "page": page_num + 1,
                        "table_index": table_idx,
                        "headers": headers,
                        "rows": rows,
                        "markdown": markdown,
                        "row_count": len(rows),
                        "col_count": len(headers),
                    })

        logger.info(
            "[pdf_tables] Extracted %d tables from %s (%d pages scanned)",
            len(tables), path.name, pages_to_scan,
        )
    except Exception as exc:
        logger.warning("[pdf_tables] Failed to extract from %s: %s", pdf_path, str(exc)[:200])

    return tables


def extract_tables_from_bytes(
    pdf_bytes: bytes,
    filename: str = "document.pdf",
    max_pages: int = _MAX_PAGES,
) -> list[dict]:
    """Extract tables from in-memory PDF bytes.

    Useful when PDF content is fetched from a URL and not saved to disk.
    """
    import tempfile

    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp.write(pdf_bytes)
        tmp_path = tmp.name

    try:
        return extract_tables_from_pdf(tmp_path, max_pages)
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


def tables_to_structured_data(tables: list[dict]) -> list[dict]:
    """Convert extracted tables to StructuredDataPoint-compatible dicts.

    Scans table cells for numeric values and creates data points.
    """
    data_points = []

    for table in tables:
        headers = table["headers"]
        for row in table["rows"]:
            for col_idx, cell in enumerate(row):
                # Try to extract numeric value
                value = _extract_numeric(cell)
                if value is not None:
                    label = headers[col_idx] if col_idx < len(headers) else f"column_{col_idx}"
                    # Use first column as context (usually row label)
                    context = row[0] if row else ""

                    data_points.append({
                        "data_type": "measurement",
                        "label": label,
                        "value": str(value),
                        "unit": _guess_unit(cell, label),
                        "year": "",
                        "context": context,
                        "source": f"PDF table page {table['page']}",
                    })

    return data_points


def _table_to_markdown(headers: list[str], rows: list[list[str]]) -> str:
    """Convert table to markdown format."""
    lines = []
    lines.append("| " + " | ".join(headers) + " |")
    lines.append("| " + " | ".join(["---"] * len(headers)) + " |")
    for row in rows:
        # Pad row to header length
        padded = row + [""] * (len(headers) - len(row))
        lines.append("| " + " | ".join(padded[:len(headers)]) + " |")
    return "\n".join(lines)


def _extract_numeric(text: str) -> Optional[float]:
    """Try to extract a numeric value from a table cell."""
    import re
    if not text:
        return None
    # Remove common prefixes/suffixes
    cleaned = text.strip().strip("$%\u00b1~\u2248><")
    # Try direct float conversion
    try:
        return float(cleaned.replace(",", ""))
    except ValueError:
        pass
    # Try regex for first number
    match = re.search(r'[-+]?\d+\.?\d*', cleaned)
    if match:
        try:
            return float(match.group())
        except ValueError:
            pass
    return None


def _guess_unit(cell_text: str, header_text: str) -> str:
    """Guess the unit from cell or header text."""
    combined = f"{cell_text} {header_text}".lower()
    unit_patterns = [
        ("%", "%"), ("mg/l", "mg/L"), ("mg/g", "mg/g"), ("ppm", "ppm"),
        ("\u03bcg", "\u03bcg"), ("nm", "nm"), ("mm", "mm"), ("cm", "cm"),
        ("kg", "kg"), ("mpa", "MPa"), ("gpa", "GPa"),
        ("\u00b0c", "\u00b0C"), ("k", "K"), ("hz", "Hz"),
        ("$", "USD"), ("\u20ac", "EUR"),
    ]
    for pattern, unit in unit_patterns:
        if pattern in combined:
            return unit
    return ""
