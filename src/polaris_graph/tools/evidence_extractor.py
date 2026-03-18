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

logger = logging.getLogger("polaris_graph")

_MAX_EVIDENCE = int(os.getenv("PG_EXTRACT_MAX_EVIDENCE", "500"))


# ---------------------------------------------------------------------------
# Numeric value extraction patterns
# ---------------------------------------------------------------------------

# Patterns ordered by specificity (most specific first)
_EXTRACTION_PATTERNS = [
    # Percentage ranges: "78-93%", "78% to 93%"
    (r'(\d+\.?\d*)\s*(?:%|percent)\s*(?:to|-)\s*(\d+\.?\d*)\s*(?:%|percent)',
     "range", "%"),
    # Concentrations: "20 ng/L", "100 mg/L", "10 ppt", "70 ppb"
    (r'(\d+[,\d]*\.?\d*)\s*(ng/[Ll]|ug/[Ll]|mg/[Ll]|ppt|ppb|ppm)',
     "concentration", None),
    # Currency: "$15/m3", "$1.548 billion", "$45 million"
    (r'\$\s*(\d+[,\d]*\.?\d*)\s*(billion|million|thousand|/m3|/ton|/kg)?',
     "cost", "USD"),
    # Percentages: "95.2%", "67 percent"
    (r'(\d+\.?\d*)\s*(?:%|percent)',
     "percentage", "%"),
    # Force/pressure: "12.4 N/mm", "3.5 MPa", "0.8 kPa", "25 N/m"
    (r'(\d+\.?\d*)\s*(N/mm2?|N/m2?|MPa|kPa|GPa|Pa|kN|N/cm2?|psi|bar)',
     "force", None),
    # Polymer/materials: "0.85 mol/L", "42 wt%", "94.2 mol%"
    (r'(\d+\.?\d*)\s*(mol/[Ll]|mol%|wt%|vol%|g/mol|kDa|Da)',
     "material_property", None),
    # Angles and geometry: "90 degrees", "180°", "45-degree"
    (r'(\d+\.?\d*)\s*(?:degrees?|°)\s*(?:C|Celsius|F|Fahrenheit)?',
     "angle_or_temp", None),
    # Measurements with units: "100 mg/g", "24 months", "1.7 mgd"
    (r'(\d+\.?\d*)\s*(mg/g|mg/kg|m[23]|mgd|kWh|MWh|tons?|kg|g/[Ll]|months?|years?|hours?|days?|nm|[uμ]m|mm|cm|m/s)',
     "measurement", None),
    # Area/volume: "342 m2/g", "1.5 cm3/g", "50 mL"
    (r'(\d+\.?\d*)\s*(m2/g|cm2/g|cm3/g|mL|[Ll]|m2)',
     "surface_property", None),
    # Plain large numbers: "110 million", "9 billion"
    (r'(\d+[,\d]*\.?\d*)\s*(million|billion|trillion)',
     "quantity", None),
    # Temperature: "500°C", "700 K"
    (r'(\d+\.?\d*)\s*(?:°[CF]|K\b)',
     "temperature", None),
    # pH values: "pH 5.0", "pH 3.0"
    (r'pH\s*(\d+\.?\d*)',
     "pH", "pH"),
    # Rates/ratios: "R2=0.998", "k=0.045 min-1"
    (r'(?:R2?|k|Kd|Ka)\s*[=:]\s*(\d+\.?\d*)\s*(min-1|s-1|h-1|L/g|L/mol)?',
     "rate_constant", None),
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

    for ev_id, ev in evidence_store.items():
        if processed >= max_evidence:
            break
        if ev.get("type") == "analysis":  # Skip analysis results
            continue

        statement = ev.get("statement", "")
        if not statement or len(statement) < 20:
            continue

        processed += 1
        source_url = ev.get("source_url", "")
        source_title = ev.get("source_title", "")
        year = str(ev.get("year", ""))

        # Try each pattern
        for pattern, data_type, default_unit in _EXTRACTION_PATTERNS:
            matches = re.finditer(pattern, statement, re.IGNORECASE)
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

                # Handle multipliers
                if unit and unit.lower() in ("billion", "million", "thousand"):
                    multipliers = {"billion": 1e9, "million": 1e6, "thousand": 1e3}
                    value *= multipliers.get(unit.lower(), 1)
                    unit = "USD" if "$" in statement[:match.start() + 20] else ""

                # Build context label from surrounding text
                start = max(0, match.start() - 40)
                end = min(len(statement), match.end() + 40)
                context = statement[start:end].strip()

                # Generate a descriptive label
                label = _generate_label(statement, match, data_type)

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
    """Generate a descriptive label from the statement context around the match."""
    # Take 5-8 words before the number as the label
    prefix = statement[:match.start()].strip()
    words = prefix.split()[-8:]
    if words:
        label = " ".join(words).strip(".,;:()[]")
        # Capitalize first word
        if label:
            label = label[0].upper() + label[1:]
        return label[:80]
    return f"{data_type}_{match.start()}"


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
