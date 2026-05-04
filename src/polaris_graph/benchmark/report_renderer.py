"""Report renderer — emit scoreboard.json + report.html + summary.md.

Per `.codex/slices/slice_005/architecture_proposal.md` §"report_renderer".

Three artifacts produced from a Scoreboard:

  scoreboard.json — machine-readable; matches Scoreboard schema
  report.html     — per-question table + aggregate bars (operator demo)
  summary.md      — one-paragraph TL;DR for Carney's office

These three files together form the gift's evidence pack for the demo.
"""

from __future__ import annotations

import html
import json
from pathlib import Path

from polaris_graph.benchmark.beat_both_scorer import Scoreboard
from polaris_graph.benchmark.dimension_scorers import ALL_DIMENSIONS, DimensionName


_DIM_LABEL: dict[DimensionName, str] = {
    "sourcing_tier_mix": "Sourcing tier mix",
    "numeric_grounding": "Numeric grounding",
    "provenance_density": "Provenance density",
    "refusal_correctness": "Refusal correctness",
    "coverage_completeness": "Coverage completeness",
    "latency": "Latency",
    "auditability": "Auditability",
}


def _format_score(v: float | None) -> str:
    if v is None:
        return "N/A"
    return f"{v:.2f}"


def _format_pct(v: float | None) -> str:
    if v is None:
        return "N/A"
    return f"{v * 100:.0f}%"


# ---------------------------------------------------------------------------
# scoreboard.json
# ---------------------------------------------------------------------------

def render_scoreboard_json(scoreboard: Scoreboard) -> bytes:
    """Canonical JSON serialization (sort_keys=True, UTF-8 bytes)."""
    payload = scoreboard.model_dump(mode="json")
    return json.dumps(
        payload,
        sort_keys=True,
        ensure_ascii=False,
        indent=2,
    ).encode("utf-8")


# ---------------------------------------------------------------------------
# summary.md
# ---------------------------------------------------------------------------

def render_summary_md(scoreboard: Scoreboard) -> str:
    """One-paragraph TL;DR + table of aggregate means."""
    n = scoreboard.aggregate.n_questions
    p_wins = scoreboard.polaris_wins
    e_wins = scoreboard.external_wins
    ties = scoreboard.ties

    # Identify POLARIS top-3 dimensions vs best external
    diffs: list[tuple[str, float]] = []
    for dim in ALL_DIMENSIONS:
        p = scoreboard.aggregate.polaris_mean.get(dim)
        c = scoreboard.aggregate.chatgpt_mean.get(dim)
        g = scoreboard.aggregate.gemini_mean.get(dim)
        externals = [v for v in (c, g) if v is not None]
        if p is None or not externals:
            continue
        diffs.append((dim, p - max(externals)))
    diffs.sort(key=lambda x: x[1], reverse=True)
    top3 = diffs[:3]

    top3_text = (
        ", ".join(
            f"{_DIM_LABEL[dim]} (+{delta:.2f})" for dim, delta in top3
        )
        if top3
        else "no head-to-head dimension data"
    )

    md = (
        f"# POLARIS BEAT-BOTH benchmark — {scoreboard.benchmark_id}\n\n"
        f"**Run:** {scoreboard.ran_at_utc.isoformat()}\n\n"
        f"## TL;DR\n\n"
        f"Across {n} clinical questions and 7 dimensions, POLARIS won "
        f"{p_wins} per-question per-dimension comparisons; commercial "
        f"deep-research products won {e_wins}; {ties} ties.\n\n"
        f"POLARIS's strongest dimensions vs. best commercial competitor: "
        f"{top3_text}.\n\n"
        f"## Aggregate means\n\n"
        f"| Dimension | POLARIS | ChatGPT DR | Gemini DR |\n"
        f"|---|---:|---:|---:|\n"
    )
    for dim in ALL_DIMENSIONS:
        p = scoreboard.aggregate.polaris_mean.get(dim)
        c = scoreboard.aggregate.chatgpt_mean.get(dim)
        g = scoreboard.aggregate.gemini_mean.get(dim)
        md += (
            f"| {_DIM_LABEL[dim]} | {_format_score(p)} | "
            f"{_format_score(c)} | {_format_score(g)} |\n"
        )
    return md


# ---------------------------------------------------------------------------
# report.html
# ---------------------------------------------------------------------------

_HTML_HEAD = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>POLARIS BEAT-BOTH Scoreboard</title>
<style>
  body { font-family: system-ui, -apple-system, sans-serif; max-width: 1200px;
         margin: 2em auto; padding: 0 1em; color: #222; }
  h1 { border-bottom: 2px solid #333; padding-bottom: 0.2em; }
  .meta { color: #666; font-size: 0.9em; }
  table { border-collapse: collapse; width: 100%; margin: 1em 0; }
  th, td { border: 1px solid #ddd; padding: 0.5em; text-align: left; }
  th { background: #f5f5f5; }
  td.score { text-align: right; font-variant-numeric: tabular-nums; }
  .winner { font-weight: bold; color: #2a7d2a; }
  .loser { color: #888; }
  .na { color: #aaa; font-style: italic; }
  .question-row { background: #fafafa; }
  .system-polaris { background: #e6f4ea; }
  .system-chatgpt { background: #fef7e0; }
  .system-gemini { background: #e8f0fe; }
  .summary-box { background: #f0f0f0; padding: 1em; border-radius: 6px;
                  margin: 1em 0; }
</style>
</head>
<body>
"""


def _highlight_class(score: float | None, peers: list[float | None]) -> str:
    """CSS class for a score cell based on win/lose vs peers."""
    if score is None:
        return "na"
    populated_peers = [p for p in peers if p is not None]
    if not populated_peers:
        return ""
    if score > max(populated_peers):
        return "winner"
    if score < max(populated_peers):
        return "loser"
    return ""


def render_report_html(scoreboard: Scoreboard) -> str:
    """Operator-friendly HTML scoreboard."""
    out = [_HTML_HEAD]
    out.append(
        f"<h1>POLARIS BEAT-BOTH — {html.escape(scoreboard.benchmark_id)}</h1>"
    )
    out.append(
        f"<p class='meta'>Ran at {html.escape(scoreboard.ran_at_utc.isoformat())} "
        f"&middot; {scoreboard.aggregate.n_questions} questions &middot; "
        f"{len(ALL_DIMENSIONS)} dimensions</p>"
    )

    # Summary box
    out.append("<div class='summary-box'>")
    out.append(
        f"<strong>Per-question per-dimension comparisons:</strong> "
        f"POLARIS won <strong>{scoreboard.polaris_wins}</strong>; "
        f"commercial DR products won <strong>{scoreboard.external_wins}</strong>; "
        f"<strong>{scoreboard.ties}</strong> ties."
    )
    out.append("</div>")

    # Aggregate table
    out.append("<h2>Aggregate means</h2><table>")
    out.append(
        "<tr><th>Dimension</th><th>POLARIS</th><th>ChatGPT DR</th>"
        "<th>Gemini DR</th></tr>"
    )
    for dim in ALL_DIMENSIONS:
        p = scoreboard.aggregate.polaris_mean.get(dim)
        c = scoreboard.aggregate.chatgpt_mean.get(dim)
        g = scoreboard.aggregate.gemini_mean.get(dim)
        out.append("<tr>")
        out.append(f"<td>{html.escape(_DIM_LABEL[dim])}</td>")
        out.append(
            f"<td class='score {_highlight_class(p, [c, g])}'>{_format_pct(p)}</td>"
        )
        out.append(
            f"<td class='score {_highlight_class(c, [p, g])}'>{_format_pct(c)}</td>"
        )
        out.append(
            f"<td class='score {_highlight_class(g, [p, c])}'>{_format_pct(g)}</td>"
        )
        out.append("</tr>")
    out.append("</table>")

    # Per-question detail
    out.append("<h2>Per-question scores</h2>")
    for q in scoreboard.per_question:
        bait_marker = " (refusal bait)" if q.is_refusal_bait else ""
        out.append(
            f"<h3>{html.escape(q.question_id)}{html.escape(bait_marker)}</h3>"
        )
        out.append(f"<p><em>{html.escape(q.question_text)}</em></p>")
        out.append("<table>")
        out.append(
            "<tr><th>Dimension</th><th>POLARIS</th><th>ChatGPT DR</th>"
            "<th>Gemini DR</th></tr>"
        )
        for dim in ALL_DIMENSIONS:
            p = q.polaris.by_dimension.get(dim)
            c = q.chatgpt.by_dimension.get(dim)
            g = q.gemini.by_dimension.get(dim)
            out.append("<tr>")
            out.append(f"<td>{html.escape(_DIM_LABEL[dim])}</td>")
            out.append(
                f"<td class='score {_highlight_class(p, [c, g])}'>{_format_pct(p)}</td>"
            )
            out.append(
                f"<td class='score {_highlight_class(c, [p, g])}'>{_format_pct(c)}</td>"
            )
            out.append(
                f"<td class='score {_highlight_class(g, [p, c])}'>{_format_pct(g)}</td>"
            )
            out.append("</tr>")
        out.append("</table>")

    out.append("</body></html>")
    return "\n".join(out)


# ---------------------------------------------------------------------------
# Combined renderer
# ---------------------------------------------------------------------------

def render_report(scoreboard: Scoreboard, output_dir: Path) -> dict[str, Path]:
    """Write all 3 artifacts to output_dir. Returns {kind: path} mapping."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    files: dict[str, Path] = {}

    json_path = output_dir / "scoreboard.json"
    json_path.write_bytes(render_scoreboard_json(scoreboard))
    files["scoreboard.json"] = json_path

    md_path = output_dir / "summary.md"
    md_path.write_text(render_summary_md(scoreboard), encoding="utf-8")
    files["summary.md"] = md_path

    html_path = output_dir / "report.html"
    html_path.write_text(render_report_html(scoreboard), encoding="utf-8")
    files["report.html"] = html_path

    return files
