"""Self-driven numeric extraction from raw evidence statements.

When PG_STRUCTURED_DATA_EXTRACTION is disabled (or returns nothing),
this module extracts numbers, percentages, costs, concentrations, and
measurements directly from evidence statement text using regex patterns.

No LLM calls. Pure Python. Fast.

This is the bridge between raw text evidence and the analysis toolkit:
  raw statements → extract_numbers_from_evidence() → data_points → analysis tools
"""

import logging
import os
import re
from typing import Optional

from src.polaris_graph.tools.numeric_sanitizer import (
    is_structural_identifier_number,
    numeric_sanitizer_enabled,
)

logger = logging.getLogger("polaris_graph")

_MAX_EVIDENCE = int(os.getenv("PG_EXTRACT_MAX_EVIDENCE", "500"))


# ---------------------------------------------------------------------------
# Numeric value extraction patterns
# ---------------------------------------------------------------------------

# Patterns ordered by specificity (most specific first).
# IMPORTANT: Each tuple is (regex, data_type, default_unit, flags).
# flags=0 means use IGNORECASE from the caller. flags=re.NOFLAG means
# case-sensitive (needed for Pa vs "parts", Da vs "days").
_EXTRACTION_PATTERNS = [
    # Percentage ranges: "78-93%", "78% to 93%"
    (r'(\d+\.?\d*)\s*(?:%|percent)\s*(?:to|-)\s*(\d+\.?\d*)\s*(?:%|percent)',
     "range", "%", 0),
    # Concentrations: "20 ng/L", "100 mg/L", "10 ppt", "70 ppb"
    # Must come BEFORE force/material to prevent "ppt" → "Pa" misclassification
    (r'(\d+[,\d]*\.?\d*)\s*(ng/[Ll]|ug/[Ll]|μg/[Ll]|mg/[Ll]|ppt|ppb|ppm)',
     "concentration", None, 0),
    # Currency: "$15/m3", "$1.548 billion", "$45 million"
    (r'\$\s*(\d+[,\d]*\.?\d*)\s*(billion|million|thousand|/m3|/ton|/kg)?',
     "cost", "USD", 0),
    # Percentages: "95.2%", "67 percent"
    (r'(\d+\.?\d*)\s*(?:%|percent)',
     "percentage", "%", 0),
    # Force/pressure: "12.4 N/mm", "3.5 MPa" — CASE-SENSITIVE to avoid
    # "Pa" matching "parts" or "pages". Requires uppercase P in Pa.
    (r'(\d+\.?\d*)\s*(N/mm2?|N/m2?|MPa|kPa|GPa|Pa\b|kN|N/cm2?|psi|bar)',
     "force", None, re.NOFLAG),
    # Polymer/materials: "0.85 mol/L", "42 wt%" — CASE-SENSITIVE for Da
    # to avoid "days" → "Da" (Dalton) misclassification
    (r'(\d+\.?\d*)\s*(mol/[Ll]|mol%|wt%|vol%|g/mol|kDa|Da\b)',
     "material_property", None, re.NOFLAG),
    # Measurements with units: "100 mg/g", "24 months", "1.7 mgd", "152 days"
    # This MUST come before surface_property to prevent "L" in "ng/L" → "L"
    (r'(\d+\.?\d*)\s*(mg/g|mg/kg|m[23]|mgd|kWh|MWh|tons?|kg|g/[Ll]|months?|years?|hours?|days?|nm|[uμ]m|mm|cm|m/s)',
     "measurement", None, 0),
    # Area/volume: "342 m2/g", "1.5 cm3/g", "50 mL" — NOT bare "L"
    # Removed bare [Ll] to prevent "4 ng/L" → "4 L" misclassification
    (r'(\d+\.?\d*)\s*(m2/g|cm2/g|cm3/g|mL\b|m2\b)',
     "surface_property", None, 0),
    # Plain large numbers: "110 million", "9 billion"
    (r'(\d+[,\d]*\.?\d*)\s*(million|billion|trillion)',
     "quantity", None, 0),
    # Temperature: "500°C", "700 K", "90 degrees C"
    (r'(\d+\.?\d*)\s*(?:°[CF]|degrees?\s*[CF]|K\b)',
     "temperature", None, 0),
    # pH values: "pH 5.0", "pH 3.0"
    (r'pH\s*(\d+\.?\d*)',
     "pH", "pH", 0),
    # Rates/ratios: "R2=0.998", "k=0.045 min-1"
    (r'(?:R2?|k|Kd|Ka)\s*[=:]\s*(\d+\.?\d*)\s*(min-1|s-1|h-1|L/g|L/mol)?',
     "rate_constant", None, 0),
]


def _clean_number(raw: str) -> Optional[float]:
    """Convert a raw number string to float."""
    try:
        cleaned = raw.replace(",", "").strip()
        return float(cleaned)
    except (ValueError, TypeError):
        return None


def extract_numbers_from_evidence(
    evidence_store: dict,
    max_evidence: int = _MAX_EVIDENCE,
) -> list[dict]:
    """Extract numeric data points from raw evidence statements.

    Scans each evidence statement for numbers with units, percentages,
    concentrations, costs, and measurements. Returns structured data
    points compatible with the analysis toolkit.

    Args:
        evidence_store: Dict of evidence_id → evidence dict.
        max_evidence: Max evidence to process.

    Returns:
        List of data point dicts with keys:
        data_type, label, value, unit, year, context, evidence_id, source_url
    """
    data_points = []
    processed = 0
    # I-perm-007 (#1201): read the sanitizer flag ONCE (default OFF -> byte-identical).
    _sanitize_numbers = numeric_sanitizer_enabled()

    for ev_id, ev in evidence_store.items():
        if processed >= max_evidence:
            break
        if ev.get("type") == "analysis":  # Skip analysis results
            continue

        # I-run11-010 (#1056, D3): scan the FULL cited span (`direct_quote`, ~1k+ chars), not the
        # ~71-char `statement` summary — the numbers live in the quote, so scanning `statement`
        # extracted 0 data points and the phase-7 quantified differentiator never fired. Precedence
        # mirrors provenance_generator.py (direct_quote -> statement -> ""). Match offsets index into
        # this string, so context + label below ALSO use it (passing `statement` would mis-offset).
        text_to_scan = ev.get("direct_quote") or ev.get("statement") or ""
        if not text_to_scan or len(text_to_scan) < 20:
            continue

        processed += 1
        source_url = ev.get("source_url", "")
        source_title = ev.get("source_title", "")
        year = str(ev.get("year", ""))

        # Try each pattern (per-pattern flags for case sensitivity)
        for pattern, data_type, default_unit, flags in _EXTRACTION_PATTERNS:
            re_flags = re.IGNORECASE if flags == 0 else flags
            matches = re.finditer(pattern, text_to_scan, re_flags)
            for match in matches:
                groups = match.groups()
                value_str = groups[0]
                unit = default_unit

                # Extract unit from capture group if pattern has one
                if len(groups) > 1 and groups[1] and not default_unit:
                    unit = groups[1]

                value = _clean_number(value_str)
                if value is None:
                    continue

                # I-perm-007 (#1201): drop a number EMBEDDED in a structural identifier
                # (DOI/URL/accession) — cruft parsed as clinical data (e.g. the DOI prefix
                # `10.1038` extracted as a percent). Default OFF -> byte-identical; keeps a clean
                # number that merely has a trailing citation URL in a later token.
                if _sanitize_numbers and is_structural_identifier_number(
                    text_to_scan, match.start(), match.end()
                ):
                    continue

                # Handle multipliers
                if unit and unit.lower() in ("billion", "million", "thousand"):
                    multipliers = {"billion": 1e9, "million": 1e6, "thousand": 1e3}
                    value *= multipliers.get(unit.lower(), 1)
                    unit = "USD" if "$" in text_to_scan[:match.start() + 20] else ""

                # Build context label from surrounding text
                start = max(0, match.start() - 40)
                end = min(len(text_to_scan), match.end() + 40)
                context = text_to_scan[start:end].strip()

                # Generate a descriptive label (capped at 80 chars, so a long quote stays concise)
                label = _generate_label(text_to_scan, match, data_type)

                data_points.append({
                    "data_type": data_type,
                    "label": label,
                    "value": str(value),
                    "unit": unit or "",
                    "year": year,
                    "context": context,
                    "evidence_id": ev_id,
                    "source_url": source_url,
                    "source_title": source_title,
                })

    # Deduplicate by (label, value, source_url)
    seen = set()
    deduped = []
    for dp in data_points:
        key = (dp["label"], dp["value"], dp["source_url"])
        if key not in seen:
            seen.add(key)
            deduped.append(dp)

    logger.info(
        "[evidence_extractor] Extracted %d data points from %d evidence (%d after dedup)",
        len(data_points), processed, len(deduped),
    )

    return deduped


def _generate_label(statement: str, match: re.Match, data_type: str) -> str:
    """Generate a descriptive label from the statement context around the match.

    Tries words BEFORE the number first. If prefix is too short (e.g. "$9
    billion"), falls back to words AFTER the number. Never returns generic
    "cost_0" labels — those break citation matching audits.
    """
    # Take 5-8 words before the number as the label
    prefix = statement[:match.start()].strip()
    prefix_words = prefix.split()[-8:]
    if len(prefix_words) >= 2:
        label = " ".join(prefix_words).strip(".,;:()[]")
        if label:
            label = label[0].upper() + label[1:]
        return label[:80]

    # Fallback: words AFTER the number (for "$9 billion allocated for PFAS")
    suffix = statement[match.end():].strip()
    suffix_words = suffix.split()[:8]
    if suffix_words:
        # Combine any prefix words with suffix
        all_words = prefix_words + suffix_words
        label = " ".join(all_words).strip(".,;:()[]")
        if label:
            label = label[0].upper() + label[1:]
        return label[:80]

    # Last resort: use the matched value + type
    value_str = match.group(0)[:30]
    return f"{data_type}: {value_str}"


def summarize_extracted_data(data_points: list[dict]) -> str:
    """Generate a markdown summary of extracted data for LLM context.

    This helps the code executor understand what data is available
    without seeing all 500+ data points.
    """
    if not data_points:
        return "No numeric data extracted from evidence."

    # Group by data_type
    by_type: dict[str, list] = {}
    for dp in data_points:
        dt = dp.get("data_type", "unknown")
        by_type.setdefault(dt, []).append(dp)

    lines = [f"**Extracted Data Summary:** {len(data_points)} data points\n"]
    for dtype, items in sorted(by_type.items()):
        lines.append(f"- **{dtype}** ({len(items)} values):")
        # Show first 3 examples
        for item in items[:3]:
            lines.append(f"  - {item['label']}: {item['value']} {item.get('unit', '')}")
        if len(items) > 3:
            lines.append(f"  - ... and {len(items) - 3} more")

    # Group by unit
    units = set(dp.get("unit", "") for dp in data_points if dp.get("unit"))
    if units:
        lines.append(f"\n**Units found:** {', '.join(sorted(units))}")

    # Source count
    sources = set(dp.get("source_url", "") for dp in data_points if dp.get("source_url"))
    lines.append(f"**From {len(sources)} sources**")

    return "\n".join(lines)
