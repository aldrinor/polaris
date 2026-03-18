"""
Pure-Python analysis toolkit for structured evidence data.

Provides statistical summaries, comparison matrices, outlier detection,
agreement scoring, impact ranking, and mini meta-analysis for data points
extracted from research evidence. All functions are synchronous (CPU-bound).

Results return markdown tables and structured dicts for embedding into
research report sections. No LLM calls.
"""

import logging
import math
import os
import re
from collections import defaultdict
from itertools import combinations

import numpy as np
import pandas as pd
from scipy import stats

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# LAW VI: All thresholds from environment variables with sensible defaults
# ---------------------------------------------------------------------------

# Outlier detection: IQR multiplier (standard = 1.5, conservative = 2.0)
_IQR_MULTIPLIER = float(os.getenv("PG_OUTLIER_IQR_MULTIPLIER", "1.5"))

# Outlier detection: Z-score threshold (standard = 3.0, sensitive = 2.0)
_ZSCORE_THRESHOLD = float(os.getenv("PG_OUTLIER_ZSCORE_THRESHOLD", "3.0"))

# Agreement score: minimum statements required for meaningful comparison
_MIN_AGREEMENT_STATEMENTS = int(os.getenv("PG_MIN_AGREEMENT_STATEMENTS", "2"))

# Impact ranking: z-score threshold for "high impact" classification
_HIGH_IMPACT_THRESHOLD = float(os.getenv("PG_HIGH_IMPACT_ZSCORE", "1.5"))

# Meta-analysis: confidence level for interval estimation
_META_CONFIDENCE_LEVEL = float(os.getenv("PG_META_CONFIDENCE_LEVEL", "0.95"))

# Maximum data points to process (prevent runaway computation)
_MAX_DATA_POINTS = int(os.getenv("PG_ANALYSIS_MAX_DATA_POINTS", "10000"))

# Minimum sample size for confidence interval computation
_MIN_CI_SAMPLE_SIZE = int(os.getenv("PG_MIN_CI_SAMPLE_SIZE", "3"))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _safe_float(value) -> float | None:
    """Convert a value to float, handling strings with units and commas.

    Returns None if conversion fails. Strips common unit suffixes like
    '%', 'mg/L', 'ppm', etc. Handles comma-separated thousands.
    """
    if value is None:
        return None
    if isinstance(value, (int, float)):
        if math.isnan(value) or math.isinf(value):
            return None
        return float(value)
    if isinstance(value, str):
        cleaned = value.strip()
        if not cleaned:
            return None
        # Remove common unit suffixes
        cleaned = re.sub(
            r'\s*(mg/[Ll]|ppm|ppb|%|g/[Ll]|ug/[Ll]|kg|mg|g|ml|[Ll]|m[23]?|nm|um|mm|cm)\s*$',
            '',
            cleaned,
        )
        # Remove commas (thousands separators)
        cleaned = cleaned.replace(',', '')
        # Handle ranges like "10-20" by taking the midpoint
        range_match = re.match(r'^(-?\d+\.?\d*)\s*[-\u2013\u2014]\s*(-?\d+\.?\d*)$', cleaned)
        if range_match:
            low = float(range_match.group(1))
            high = float(range_match.group(2))
            return (low + high) / 2.0
        # Handle ">" or "<" prefixes by stripping them
        cleaned = re.sub(r'^[<>~]\s*', '', cleaned)
        try:
            return float(cleaned)
        except (ValueError, TypeError):
            return None
    return None


def _format_number(value: float, precision: int = 2) -> str:
    """Format a number for display, handling large and small values."""
    if abs(value) >= 1000:
        return f"{value:,.{precision}f}"
    if abs(value) < 0.01 and value != 0:
        return f"{value:.{precision}e}"
    return f"{value:.{precision}f}"


def _extract_source_label(source_url: str) -> str:
    """Extract a short label from a URL for table display."""
    if not source_url:
        return "Unknown"
    # Strip protocol and www
    label = re.sub(r'^https?://(www\.)?', '', source_url)
    # Take just the domain
    label = label.split('/')[0]
    # Truncate if too long
    if len(label) > 40:
        label = label[:37] + "..."
    return label


def _build_markdown_table(headers: list[str], rows: list[list[str]]) -> str:
    """Build a properly aligned markdown table from headers and rows."""
    if not headers or not rows:
        return ""

    # Compute column widths for alignment
    col_widths = [len(str(h)) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            if i < len(col_widths):
                col_widths[i] = max(col_widths[i], len(str(cell)))

    # Header row
    header_line = "| " + " | ".join(
        str(h).ljust(col_widths[i]) for i, h in enumerate(headers)
    ) + " |"

    # Separator row
    sep_line = "| " + " | ".join(
        "-" * col_widths[i] for i in range(len(headers))
    ) + " |"

    # Data rows
    data_lines = []
    for row in rows:
        padded = list(row) + [""] * (len(headers) - len(row))
        line = "| " + " | ".join(
            str(padded[i]).ljust(col_widths[i]) for i in range(len(headers))
        ) + " |"
        data_lines.append(line)

    return "\n".join([header_line, sep_line] + data_lines)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def statistical_summary(
    data_points: list[dict],
    group_by: str = "source_url",
) -> dict:
    """Aggregate numeric data points across multiple studies.

    Args:
        data_points: List of dicts with keys: label, value (str or float),
            unit, year, source_url, evidence_id.
        group_by: Field to group by. Use "source_url" for per-study or
            "label" for per-metric aggregation.

    Returns:
        Dictionary containing:
            - markdown_table: Formatted markdown table string
            - statistics: Global summary statistics (mean, median, etc.)
            - by_group: Per-group statistics
            - insights: Auto-generated insight strings
    """
    if not data_points:
        logger.warning(
            "[analysis_toolkit] statistical_summary called with empty data_points"
        )
        return {
            "markdown_table": "",
            "statistics": {},
            "by_group": {},
            "insights": ["No data points provided for analysis."],
        }

    # Enforce data point limit
    truncated = data_points[:_MAX_DATA_POINTS]
    if len(data_points) > _MAX_DATA_POINTS:
        logger.warning(
            "[analysis_toolkit] Truncating %d data points to %d",
            len(data_points),
            _MAX_DATA_POINTS,
        )

    # Parse numeric values
    parsed = []
    parse_failures = 0
    for dp in truncated:
        numeric_val = _safe_float(dp.get("value"))
        if numeric_val is not None:
            parsed.append({
                "label": str(dp.get("label", "")),
                "value": numeric_val,
                "unit": str(dp.get("unit", "")),
                "year": str(dp.get("year", "")),
                "source_url": str(dp.get("source_url", "")),
                "evidence_id": str(dp.get("evidence_id", "")),
                "group_key": str(dp.get(group_by, "ungrouped")),
            })
        else:
            parse_failures += 1

    if not parsed:
        return {
            "markdown_table": "",
            "statistics": {},
            "by_group": {},
            "insights": [
                f"All {len(truncated)} data points had non-numeric values "
                f"that could not be parsed."
            ],
        }

    if parse_failures > 0:
        logger.info(
            "[analysis_toolkit] %d/%d data points had non-numeric values (skipped)",
            parse_failures,
            len(truncated),
        )

    values = np.array([p["value"] for p in parsed])

    # Global statistics
    mean_val = float(np.mean(values))
    median_val = float(np.median(values))
    std_val = float(np.std(values, ddof=1)) if len(values) > 1 else 0.0
    min_val = float(np.min(values))
    max_val = float(np.max(values))
    n = len(values)

    # 95% confidence interval using t-distribution
    ci_lower = mean_val
    ci_upper = mean_val
    if n >= _MIN_CI_SAMPLE_SIZE and std_val > 0:
        se = std_val / math.sqrt(n)
        t_crit = stats.t.ppf((1 + _META_CONFIDENCE_LEVEL) / 2, df=n - 1)
        ci_lower = mean_val - t_crit * se
        ci_upper = mean_val + t_crit * se

    global_stats = {
        "mean": round(mean_val, 4),
        "median": round(median_val, 4),
        "std": round(std_val, 4),
        "min": round(min_val, 4),
        "max": round(max_val, 4),
        "n": n,
        "ci_95_lower": round(ci_lower, 4),
        "ci_95_upper": round(ci_upper, 4),
    }

    # Per-group statistics
    groups = defaultdict(list)
    for p in parsed:
        groups[p["group_key"]].append(p["value"])

    by_group = {}
    for group_key, group_values in groups.items():
        gv = np.array(group_values)
        g_mean = float(np.mean(gv))
        g_std = float(np.std(gv, ddof=1)) if len(gv) > 1 else 0.0
        by_group[group_key] = {
            "mean": round(g_mean, 4),
            "median": round(float(np.median(gv)), 4),
            "std": round(g_std, 4),
            "min": round(float(np.min(gv)), 4),
            "max": round(float(np.max(gv)), 4),
            "n": len(gv),
        }

    # Build markdown table
    unit_str = parsed[0]["unit"] if parsed[0]["unit"] else "value"
    headers = ["Group", f"Mean ({unit_str})", "Median", "Std Dev", "Min", "Max", "N"]
    rows = []
    for group_key in sorted(by_group.keys()):
        gs = by_group[group_key]
        display_key = (
            _extract_source_label(group_key) if group_by == "source_url"
            else group_key
        )
        rows.append([
            display_key,
            _format_number(gs["mean"]),
            _format_number(gs["median"]),
            _format_number(gs["std"]),
            _format_number(gs["min"]),
            _format_number(gs["max"]),
            str(gs["n"]),
        ])

    # Add summary row
    rows.append([
        "**Overall**",
        f"**{_format_number(mean_val)}**",
        f"**{_format_number(median_val)}**",
        f"**{_format_number(std_val)}**",
        f"**{_format_number(min_val)}**",
        f"**{_format_number(max_val)}**",
        f"**{n}**",
    ])

    markdown_table = _build_markdown_table(headers, rows)

    # Generate insights
    insights = []
    insights.append(
        f"Values range from {_format_number(min_val)} to {_format_number(max_val)} "
        f"({unit_str}) across {n} data points from {len(groups)} sources."
    )

    if n >= _MIN_CI_SAMPLE_SIZE and std_val > 0:
        insights.append(
            f"The mean is {_format_number(mean_val)} "
            f"(95% CI: {_format_number(ci_lower)} to {_format_number(ci_upper)})."
        )

    cv = (std_val / abs(mean_val) * 100) if mean_val != 0 else 0
    if cv > 50:
        insights.append(
            f"High variability detected (CV = {_format_number(cv)}%). "
            f"Results differ substantially across sources."
        )
    elif cv > 20:
        insights.append(
            f"Moderate variability (CV = {_format_number(cv)}%). "
            f"Some disagreement between sources."
        )
    else:
        insights.append(
            f"Low variability (CV = {_format_number(cv)}%). "
            f"Sources show good agreement."
        )

    if parse_failures > 0:
        insights.append(
            f"Note: {parse_failures} data points had non-numeric values and were excluded."
        )

    return {
        "markdown_table": markdown_table,
        "statistics": global_stats,
        "by_group": by_group,
        "insights": insights,
    }


def build_comparison_table(
    data_points: list[dict],
    row_field: str = "source_url",
    col_field: str = "label",
    value_field: str = "value",
) -> str:
    """Build a markdown pivot/comparison table from structured data.

    Creates a pivot table where rows = studies/sources, columns = metrics,
    and cells = values. Handles missing values with a dash. Appends a
    summary row with mean/range for each column.

    Args:
        data_points: List of dicts with at least the row_field, col_field,
            and value_field keys.
        row_field: Field to use for row grouping (default: source_url).
        col_field: Field to use for column headers (default: label).
        value_field: Field containing the cell values (default: value).

    Returns:
        Markdown table string. Empty string if insufficient data.
    """
    if not data_points:
        return ""

    truncated = data_points[:_MAX_DATA_POINTS]

    # Build pivot structure
    row_keys = []
    col_keys = []
    seen_rows = set()
    seen_cols = set()
    pivot = defaultdict(dict)

    for dp in truncated:
        row_val = str(dp.get(row_field, ""))
        col_val = str(dp.get(col_field, ""))
        cell_val = dp.get(value_field, "")

        if not row_val or not col_val:
            continue

        if row_val not in seen_rows:
            row_keys.append(row_val)
            seen_rows.add(row_val)
        if col_val not in seen_cols:
            col_keys.append(col_val)
            seen_cols.add(col_val)

        # If multiple values for same cell, keep the latest
        pivot[row_val][col_val] = str(cell_val) if cell_val is not None else "\u2014"

    if not row_keys or not col_keys:
        return ""

    # Build headers
    row_header_label = row_field.replace("_", " ").title()
    headers = [row_header_label] + col_keys

    # Build data rows
    rows = []
    for row_key in row_keys:
        display_key = (
            _extract_source_label(row_key) if row_field == "source_url"
            else row_key
        )
        row_data = [display_key]
        for col_key in col_keys:
            cell = pivot[row_key].get(col_key, "\u2014")
            row_data.append(cell)
        rows.append(row_data)

    # Add summary row (mean/range for numeric columns, count for non-numeric)
    summary_row = ["**Summary**"]
    for col_key in col_keys:
        col_values = []
        for row_key in row_keys:
            raw = pivot[row_key].get(col_key)
            if raw is not None:
                numeric = _safe_float(raw)
                if numeric is not None:
                    col_values.append(numeric)

        if col_values:
            col_mean = np.mean(col_values)
            col_min = min(col_values)
            col_max = max(col_values)
            if col_min == col_max:
                summary_row.append(f"**{_format_number(col_mean)}**")
            else:
                summary_row.append(
                    f"**{_format_number(col_mean)}** "
                    f"({_format_number(col_min)}\u2013{_format_number(col_max)})"
                )
        else:
            reporting_count = sum(
                1 for rk in row_keys if col_key in pivot[rk]
            )
            summary_row.append(f"{reporting_count}/{len(row_keys)} reported")

    rows.append(summary_row)

    return _build_markdown_table(headers, rows)


def detect_outliers(
    values: list[float],
    method: str = "iqr",
) -> dict:
    """Detect outliers using IQR or Z-score method.

    Args:
        values: List of numeric values to analyze.
        method: Detection method. One of "iqr" (Interquartile Range)
            or "zscore" (Z-score). Default: "iqr".

    Returns:
        Dictionary with:
            - outlier_indices: Indices of outlier values
            - outlier_values: The outlier values themselves
            - bounds: (lower_bound, upper_bound) tuple
            - method: Method used
    """
    empty_result = {
        "outlier_indices": [],
        "outlier_values": [],
        "bounds": (0.0, 0.0),
        "method": method,
    }

    if not values or len(values) < 3:
        return empty_result

    arr = np.array(values, dtype=float)

    # Remove NaN/inf
    valid_mask = np.isfinite(arr)
    if not np.any(valid_mask):
        return empty_result

    if method == "zscore":
        mean_val = float(np.mean(arr[valid_mask]))
        std_val = float(np.std(arr[valid_mask], ddof=1))

        if std_val == 0:
            return {
                "outlier_indices": [],
                "outlier_values": [],
                "bounds": (mean_val, mean_val),
                "method": method,
            }

        z_scores = np.abs((arr - mean_val) / std_val)
        lower_bound = mean_val - _ZSCORE_THRESHOLD * std_val
        upper_bound = mean_val + _ZSCORE_THRESHOLD * std_val

        outlier_mask = (z_scores > _ZSCORE_THRESHOLD) & valid_mask
    else:
        # IQR method (default)
        q1 = float(np.percentile(arr[valid_mask], 25))
        q3 = float(np.percentile(arr[valid_mask], 75))
        iqr = q3 - q1

        lower_bound = q1 - _IQR_MULTIPLIER * iqr
        upper_bound = q3 + _IQR_MULTIPLIER * iqr

        outlier_mask = ((arr < lower_bound) | (arr > upper_bound)) & valid_mask

    outlier_indices = [int(i) for i in np.where(outlier_mask)[0]]
    outlier_values = [float(arr[i]) for i in outlier_indices]

    return {
        "outlier_indices": outlier_indices,
        "outlier_values": outlier_values,
        "bounds": (round(lower_bound, 4), round(upper_bound, 4)),
        "method": method,
    }


def compute_agreement_score(evidence_statements: list[str]) -> dict:
    """Compute how well evidence sources agree using word overlap Jaccard similarity.

    Performs pairwise comparison of all statements using set-based Jaccard
    similarity on word tokens. High agreement means sources report similar
    information. Low agreement suggests conflicting or complementary evidence.

    Args:
        evidence_statements: List of text statements to compare.

    Returns:
        Dictionary with:
            - agreement_score: Float 0-1 (mean pairwise Jaccard similarity)
            - pairwise_scores: List of all pairwise similarity scores
            - consensus_strength: Human-readable label ("strong", "moderate",
              "weak", "no consensus")
    """
    empty_result = {
        "agreement_score": 0.0,
        "pairwise_scores": [],
        "consensus_strength": "insufficient data",
    }

    if not evidence_statements or len(evidence_statements) < _MIN_AGREEMENT_STATEMENTS:
        return empty_result

    # Tokenize: lowercase, split on non-alphanumeric, remove stopwords
    stopwords = {
        "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
        "have", "has", "had", "do", "does", "did", "will", "would", "could",
        "should", "may", "might", "can", "shall", "to", "of", "in", "for",
        "on", "with", "at", "by", "from", "as", "into", "through", "during",
        "before", "after", "above", "below", "between", "under", "again",
        "further", "then", "once", "and", "but", "or", "nor", "not", "so",
        "yet", "both", "each", "few", "more", "most", "other", "some",
        "such", "no", "only", "own", "same", "than", "too", "very",
        "this", "that", "these", "those", "it", "its", "they", "them",
        "their", "we", "our", "he", "she", "his", "her", "who", "which",
        "what", "when", "where", "how", "all", "any", "if", "also",
    }

    def tokenize(text: str) -> set[str]:
        words = re.findall(r'[a-z0-9]+', text.lower())
        return {w for w in words if w not in stopwords and len(w) > 2}

    token_sets = [tokenize(stmt) for stmt in evidence_statements]

    # Filter out empty token sets
    valid_pairs = [
        (i, j)
        for i, j in combinations(range(len(token_sets)), 2)
        if token_sets[i] and token_sets[j]
    ]

    if not valid_pairs:
        return empty_result

    pairwise_scores = []
    for i, j in valid_pairs:
        intersection = len(token_sets[i] & token_sets[j])
        union = len(token_sets[i] | token_sets[j])
        jaccard = intersection / union if union > 0 else 0.0
        pairwise_scores.append(round(jaccard, 4))

    agreement = float(np.mean(pairwise_scores))

    # Classify consensus strength
    if agreement >= 0.5:
        consensus = "strong"
    elif agreement >= 0.3:
        consensus = "moderate"
    elif agreement >= 0.15:
        consensus = "weak"
    else:
        consensus = "no consensus"

    return {
        "agreement_score": round(agreement, 4),
        "pairwise_scores": pairwise_scores,
        "consensus_strength": consensus,
    }


def rank_evidence_by_impact(data_points: list[dict]) -> list[dict]:
    """Rank data points by how much they deviate from the group mean.

    High-impact data points are outliers that contradict or significantly
    extend the consensus. Each data point receives an impact_score (absolute
    z-score) and an impact_reason explaining why it is notable.

    Args:
        data_points: List of dicts with at least a "value" key. Values
            are parsed to float; non-numeric entries receive impact_score 0.

    Returns:
        Sorted list of data_points (highest impact first) with added
        "impact_score" and "impact_reason" fields. Original dicts are
        not mutated; new dicts are returned.
    """
    if not data_points:
        return []

    truncated = data_points[:_MAX_DATA_POINTS]

    # Parse values
    enriched = []
    numeric_values = []

    for dp in truncated:
        new_dp = dict(dp)
        numeric_val = _safe_float(dp.get("value"))
        new_dp["_parsed_value"] = numeric_val
        if numeric_val is not None:
            numeric_values.append(numeric_val)
        enriched.append(new_dp)

    if not numeric_values:
        # No numeric values: assign zero impact to all
        for dp in enriched:
            dp["impact_score"] = 0.0
            dp["impact_reason"] = "Non-numeric value; could not assess impact."
            dp.pop("_parsed_value", None)
        return enriched

    mean_val = float(np.mean(numeric_values))
    std_val = float(np.std(numeric_values, ddof=1)) if len(numeric_values) > 1 else 0.0

    for dp in enriched:
        parsed = dp.pop("_parsed_value", None)

        if parsed is None:
            dp["impact_score"] = 0.0
            dp["impact_reason"] = "Non-numeric value; could not assess impact."
            continue

        if std_val == 0:
            dp["impact_score"] = 0.0
            dp["impact_reason"] = "All numeric values are identical; no deviation."
            continue

        z = abs(parsed - mean_val) / std_val
        dp["impact_score"] = round(z, 4)

        # Classify the deviation
        direction = "above" if parsed > mean_val else "below"
        deviation_pct = abs(parsed - mean_val) / abs(mean_val) * 100 if mean_val != 0 else 0

        if z >= _HIGH_IMPACT_THRESHOLD:
            dp["impact_reason"] = (
                f"High impact: value {_format_number(parsed)} is "
                f"{_format_number(deviation_pct)}% {direction} the mean "
                f"({_format_number(mean_val)}), z-score = {_format_number(z)}."
            )
        elif z >= 1.0:
            dp["impact_reason"] = (
                f"Moderate impact: value {_format_number(parsed)} is "
                f"{_format_number(deviation_pct)}% {direction} the mean "
                f"({_format_number(mean_val)})."
            )
        else:
            dp["impact_reason"] = (
                f"Low impact: value {_format_number(parsed)} is near the mean "
                f"({_format_number(mean_val)})."
            )

    # Sort by impact_score descending
    enriched.sort(key=lambda dp: dp.get("impact_score", 0.0), reverse=True)

    return enriched


def generate_meta_analysis_summary(data_points: list[dict]) -> str:
    """Generate a mini meta-analysis summary across studies.

    Computes pooled mean weighted by inverse variance, heterogeneity via
    the I-squared statistic approximation, and produces a forest-plot-style
    markdown table showing each study's contribution.

    Args:
        data_points: List of dicts with keys: label (study name), value
            (numeric), unit, source_url, evidence_id. Multiple data points
            from the same source_url are averaged into one study estimate.

    Returns:
        Markdown string containing the forest-plot table and a statistical
        narrative. Empty string if insufficient data.
    """
    if not data_points:
        return ""

    truncated = data_points[:_MAX_DATA_POINTS]

    # Parse and group by source (each source = one "study")
    study_data = defaultdict(list)
    unit_str = ""

    for dp in truncated:
        numeric_val = _safe_float(dp.get("value"))
        if numeric_val is None:
            continue
        source_key = str(dp.get("source_url", dp.get("label", "Unknown")))
        study_data[source_key].append(numeric_val)
        if not unit_str:
            unit_str = str(dp.get("unit", ""))

    if len(study_data) < 2:
        return (
            "Insufficient studies for meta-analysis "
            f"(need >= 2, found {len(study_data)})."
        )

    # Compute per-study mean and standard error
    studies = []
    for source_key, vals in study_data.items():
        arr = np.array(vals)
        study_mean = float(np.mean(arr))
        study_n = len(vals)
        # Standard error: use within-study std if n > 1, else estimate from
        # overall data spread
        if study_n > 1:
            study_se = float(np.std(arr, ddof=1) / math.sqrt(study_n))
        else:
            study_se = None  # Will be imputed below
        studies.append({
            "source": source_key,
            "label": _extract_source_label(source_key),
            "mean": study_mean,
            "se": study_se,
            "n": study_n,
        })

    # Impute SE for single-observation studies using median SE of others
    known_ses = [s["se"] for s in studies if s["se"] is not None and s["se"] > 0]
    if known_ses:
        imputed_se = float(np.median(known_ses))
    else:
        # All studies have single observations; use pooled std estimate
        all_means = [s["mean"] for s in studies]
        imputed_se = float(np.std(all_means, ddof=1) / math.sqrt(len(all_means)))
        if imputed_se == 0:
            imputed_se = 1.0  # Prevent division by zero

    for study in studies:
        if study["se"] is None or study["se"] == 0:
            study["se"] = imputed_se

    # Inverse-variance weighting
    weights = []
    for study in studies:
        w = 1.0 / (study["se"] ** 2) if study["se"] > 0 else 0.0
        study["weight"] = w
        weights.append(w)

    total_weight = sum(weights)
    if total_weight == 0:
        return "Cannot compute pooled estimate (all weights are zero)."

    # Normalize weights to percentages
    for study in studies:
        study["weight_pct"] = (study["weight"] / total_weight) * 100

    # Pooled mean (fixed-effects)
    pooled_mean = sum(s["mean"] * s["weight"] for s in studies) / total_weight
    pooled_se = math.sqrt(1.0 / total_weight) if total_weight > 0 else 0.0

    # Confidence interval
    alpha = 1 - _META_CONFIDENCE_LEVEL
    z_crit = stats.norm.ppf(1 - alpha / 2)
    pooled_ci_lower = pooled_mean - z_crit * pooled_se
    pooled_ci_upper = pooled_mean + z_crit * pooled_se

    # Heterogeneity: Cochran's Q and I-squared
    q_stat = sum(
        s["weight"] * (s["mean"] - pooled_mean) ** 2 for s in studies
    )
    df = len(studies) - 1
    i_squared = max(0.0, (q_stat - df) / q_stat * 100) if q_stat > 0 else 0.0

    # Per-study CI for forest plot
    for study in studies:
        ci_half = z_crit * study["se"]
        study["ci_lower"] = study["mean"] - ci_half
        study["ci_upper"] = study["mean"] + ci_half

    # Sort by weight descending
    studies.sort(key=lambda s: s["weight_pct"], reverse=True)

    # Build forest-plot-style markdown table
    unit_label = f" ({unit_str})" if unit_str else ""
    headers = [
        "Study",
        f"Estimate{unit_label}",
        "95% CI",
        "Weight (%)",
        "N",
    ]

    rows = []
    for study in studies:
        rows.append([
            study["label"],
            _format_number(study["mean"]),
            f"{_format_number(study['ci_lower'])} \u2013 {_format_number(study['ci_upper'])}",
            _format_number(study["weight_pct"], 1),
            str(study["n"]),
        ])

    # Pooled row
    rows.append([
        "**Pooled estimate**",
        f"**{_format_number(pooled_mean)}**",
        f"**{_format_number(pooled_ci_lower)} \u2013 {_format_number(pooled_ci_upper)}**",
        "**100.0**",
        f"**{sum(s['n'] for s in studies)}**",
    ])

    table = _build_markdown_table(headers, rows)

    # Statistical narrative
    lines = [
        table,
        "",
        f"**Pooled estimate (fixed-effects):** "
        f"{_format_number(pooled_mean)}{unit_label} "
        f"(95% CI: {_format_number(pooled_ci_lower)} to "
        f"{_format_number(pooled_ci_upper)})",
        "",
    ]

    # Heterogeneity interpretation
    if i_squared < 25:
        het_label = "low"
    elif i_squared < 50:
        het_label = "moderate"
    elif i_squared < 75:
        het_label = "substantial"
    else:
        het_label = "considerable"

    lines.append(
        f"**Heterogeneity:** Q = {_format_number(q_stat)}, "
        f"df = {df}, I\u00b2 = {_format_number(i_squared, 1)}% ({het_label})"
    )

    if i_squared >= 50:
        lines.append(
            f"Note: {het_label} heterogeneity (I\u00b2 = "
            f"{_format_number(i_squared, 1)}%) suggests results vary "
            f"substantially across studies. A random-effects model may be "
            f"more appropriate."
        )

    lines.append(
        f"\n*Based on {len(studies)} studies with "
        f"{sum(s['n'] for s in studies)} total observations.*"
    )

    return "\n".join(lines)
