"""Slice 005 BEAT-BOTH benchmark CLI.

Runs the live POLARIS chain against N benchmark questions, loads
manually-exported ChatGPT/Gemini DR outputs, scores all 3 systems on 7
dimensions, and emits scoreboard.json + summary.md + report.html.

Usage:
    python scripts/run_benchmark.py \
        --config config/benchmark/clinical_n10.json \
        --polaris-url http://127.0.0.1:8000 \
        --chatgpt-dir external_outputs/chatgpt/ \
        --gemini-dir external_outputs/gemini/ \
        --output benchmark_results/clinical_n10_$(date +%Y%m%d)/

Per `.codex/slices/slice_005/architecture_proposal.md` §"scripts/".

Prerequisites:
- POLARIS FastAPI app running on --polaris-url with all 4 slices mounted
- SERPER_API_KEY + OPENROUTER_API_KEY set in env (so retrieval +
  generation work end-to-end against real backends)
- Manually-exported ChatGPT/Gemini outputs as .txt files named
  {question_id}.txt in --chatgpt-dir / --gemini-dir (missing files OK)
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from polaris_graph.benchmark.beat_both_scorer import run_benchmark
from polaris_graph.benchmark.benchmark_config import load_config
from polaris_graph.benchmark.external_loader import load_external_outputs
from polaris_graph.benchmark.polaris_runner import run_polaris_against
from polaris_graph.benchmark.report_renderer import render_report


_LOG = logging.getLogger(__name__)


def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Run POLARIS BEAT-BOTH benchmark"
    )
    p.add_argument(
        "--config",
        required=True,
        type=Path,
        help="Path to benchmark config JSON (e.g. config/benchmark/clinical_n10.json)",
    )
    p.add_argument(
        "--polaris-url",
        default="http://127.0.0.1:8000",
        help="POLARIS FastAPI base URL (default: http://127.0.0.1:8000)",
    )
    p.add_argument(
        "--chatgpt-dir",
        type=Path,
        default=None,
        help="Directory of ChatGPT DR .txt outputs (optional)",
    )
    p.add_argument(
        "--gemini-dir",
        type=Path,
        default=None,
        help="Directory of Gemini DR .txt outputs (optional)",
    )
    p.add_argument(
        "--output",
        required=True,
        type=Path,
        help="Output directory for scoreboard.json + summary.md + report.html",
    )
    p.add_argument(
        "--skip-polaris",
        action="store_true",
        help=(
            "Skip the POLARIS run (use stub PolarisRunResult per question). "
            "Useful for re-scoring with fresh external outputs without "
            "re-running the chain."
        ),
    )
    p.add_argument(
        "-v", "--verbose",
        action="count", default=0,
        help="Increase log verbosity (-v=INFO, -vv=DEBUG)",
    )
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv if argv is not None else sys.argv[1:])
    log_level = logging.WARNING
    if args.verbose >= 2:
        log_level = logging.DEBUG
    elif args.verbose >= 1:
        log_level = logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    _LOG.info("loading benchmark config from %s", args.config)
    config = load_config(args.config)
    _LOG.info(
        "config loaded: benchmark_id=%s, %d questions",
        config.benchmark_id, len(config.questions),
    )

    if args.skip_polaris:
        _LOG.warning("--skip-polaris set; polaris_results will be empty")
        polaris_results = {}
    else:
        _LOG.info("running POLARIS chain against %s", args.polaris_url)
        polaris_results = run_polaris_against(
            config, args.polaris_url
        )
        succeeded = sum(1 for r in polaris_results.values() if r.succeeded())
        _LOG.info(
            "POLARIS: %d/%d questions succeeded",
            succeeded, len(polaris_results),
        )

    _LOG.info("loading ChatGPT outputs from %s", args.chatgpt_dir)
    chatgpt_report = load_external_outputs(
        "chatgpt", args.chatgpt_dir, config.question_ids()
    )
    _LOG.info(
        "ChatGPT: %d/%d questions covered",
        len(chatgpt_report.loaded), len(config.question_ids()),
    )

    _LOG.info("loading Gemini outputs from %s", args.gemini_dir)
    gemini_report = load_external_outputs(
        "gemini", args.gemini_dir, config.question_ids()
    )
    _LOG.info(
        "Gemini: %d/%d questions covered",
        len(gemini_report.loaded), len(config.question_ids()),
    )

    _LOG.info("scoring %d questions across 7 dimensions", len(config.questions))
    scoreboard = run_benchmark(
        config=config,
        polaris_results=polaris_results,
        chatgpt_outputs=chatgpt_report.loaded,
        gemini_outputs=gemini_report.loaded,
    )
    _LOG.info(
        "scoreboard: polaris_wins=%d external_wins=%d ties=%d",
        scoreboard.polaris_wins,
        scoreboard.external_wins,
        scoreboard.ties,
    )

    _LOG.info("rendering report to %s", args.output)
    files = render_report(scoreboard, args.output)
    for kind, path in files.items():
        _LOG.info("  wrote %s -> %s (%d bytes)", kind, path, path.stat().st_size)

    print(f"\n=== POLARIS BEAT-BOTH benchmark complete ===")
    print(f"Benchmark: {scoreboard.benchmark_id}")
    print(f"Questions: {scoreboard.aggregate.n_questions}")
    print(
        f"POLARIS wins: {scoreboard.polaris_wins} | "
        f"External wins: {scoreboard.external_wins} | "
        f"Ties: {scoreboard.ties}"
    )
    print(f"Output: {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
