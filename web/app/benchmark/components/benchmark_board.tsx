"use client";

import { useEffect, useState } from "react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import {
  ALL_BENCHMARK_DIMENSIONS,
  BENCHMARK_DIMENSION_LABELS,
  getBenchmarkHealth,
  getBenchmarkScoreboard,
  type BenchmarkDimension,
  type BenchmarkScoreboard,
} from "@/lib/api";

type BoardState =
  | { kind: "loading_health" }
  | { kind: "no_results_dir" }
  | { kind: "no_benchmarks"; results_root: string }
  | { kind: "benchmark_list"; available: string[] }
  | { kind: "loading_scoreboard"; benchmark_id: string }
  | { kind: "loaded"; benchmark_id: string; scoreboard: BenchmarkScoreboard }
  | { kind: "error"; message: string };

function format_pct(v: number | null | undefined): string {
  if (v === null || v === undefined) return "N/A";
  return `${Math.round(v * 100)}%`;
}

function tone_class(
  score: number | null,
  peers: (number | null)[],
): string {
  if (score === null) return "text-muted-foreground italic";
  const populated = peers.filter((p): p is number => p !== null);
  if (populated.length === 0) return "";
  const max_peer = Math.max(...populated);
  if (score > max_peer) {
    return "text-emerald-700 dark:text-emerald-300 font-semibold";
  }
  if (score < max_peer) return "text-muted-foreground";
  return "";
}

export function BenchmarkBoard() {
  const [state, setState] = useState<BoardState>({ kind: "loading_health" });

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const health = await getBenchmarkHealth();
        if (cancelled) return;
        if (health.results_root === null) {
          setState({ kind: "no_results_dir" });
          return;
        }
        if (health.available_benchmarks.length === 0) {
          setState({
            kind: "no_benchmarks",
            results_root: health.results_root,
          });
          return;
        }
        setState({
          kind: "benchmark_list",
          available: health.available_benchmarks,
        });
      } catch (err) {
        if (cancelled) return;
        const msg = err instanceof Error ? err.message : "Unknown error";
        setState({ kind: "error", message: msg });
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  async function load_benchmark(benchmark_id: string) {
    setState({ kind: "loading_scoreboard", benchmark_id });
    try {
      const scoreboard = await getBenchmarkScoreboard(benchmark_id);
      setState({ kind: "loaded", benchmark_id, scoreboard });
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Unknown error";
      setState({ kind: "error", message: msg });
    }
  }

  if (state.kind === "loading_health") {
    return (
      <Card data-testid="benchmark-loading">
        <CardContent>Loading benchmark catalog…</CardContent>
      </Card>
    );
  }

  if (state.kind === "no_results_dir") {
    return (
      <Card
        data-testid="benchmark-no-results-dir"
        className="border-amber-500/40 bg-amber-500/5"
      >
        <CardContent className="text-amber-700 dark:text-amber-300">
          <strong className="block">Benchmark results not configured</strong>
          POLARIS_BENCHMARK_RESULTS_DIR is not set in the live server&rsquo;s
          environment. Run{" "}
          <code className="bg-muted rounded px-1">
            scripts/run_benchmark.py
          </code>{" "}
          first, then point the server at the results directory.
        </CardContent>
      </Card>
    );
  }

  if (state.kind === "no_benchmarks") {
    return (
      <Card
        data-testid="benchmark-empty"
        className="border-amber-500/40 bg-amber-500/5"
      >
        <CardContent className="text-amber-700 dark:text-amber-300">
          <strong className="block">No benchmark results yet</strong>
          The results directory is configured (
          <code>{state.results_root}</code>) but no benchmark subdirs
          contain a scoreboard.json. Run{" "}
          <code className="bg-muted rounded px-1">
            scripts/run_benchmark.py
          </code>
          .
        </CardContent>
      </Card>
    );
  }

  if (state.kind === "error") {
    return (
      <Card
        data-testid="benchmark-error"
        className="border-rose-500/40 bg-rose-500/5"
      >
        <CardContent className="text-rose-700 dark:text-rose-300">
          {state.message}
        </CardContent>
      </Card>
    );
  }

  if (state.kind === "benchmark_list") {
    return (
      <Card data-testid="benchmark-list">
        <CardHeader>
          <CardTitle className="text-lg">Available benchmarks</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-2">
          {state.available.map((bench_id) => (
            <button
              key={bench_id}
              type="button"
              onClick={() => load_benchmark(bench_id)}
              data-testid={`benchmark-link-${bench_id}`}
              className="border-border bg-background hover:bg-muted text-foreground rounded-lg border px-4 py-2 text-left text-sm transition-colors"
            >
              {bench_id}
            </button>
          ))}
        </CardContent>
      </Card>
    );
  }

  if (state.kind === "loading_scoreboard") {
    return (
      <Card data-testid="benchmark-loading-scoreboard">
        <CardContent>
          Loading scoreboard for <code>{state.benchmark_id}</code>…
        </CardContent>
      </Card>
    );
  }

  // state.kind === "loaded"
  const sb = state.scoreboard;
  return (
    <div data-testid="benchmark-board" className="flex flex-col gap-4">
      <Card>
        <CardHeader className="flex flex-row items-center justify-between gap-3">
          <CardTitle className="text-lg">{sb.benchmark_id}</CardTitle>
          <span className="text-muted-foreground text-xs">
            {sb.aggregate.n_questions} questions · {ALL_BENCHMARK_DIMENSIONS.length} dimensions
          </span>
        </CardHeader>
        <CardContent>
          <p className="text-sm" data-testid="benchmark-tally">
            POLARIS won{" "}
            <span className="text-emerald-700 dark:text-emerald-300 font-semibold">
              {sb.polaris_wins}
            </span>{" "}
            per-question per-dimension comparisons; commercial DR products
            won {sb.external_wins}; {sb.ties} ties.
          </p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Aggregate means</CardTitle>
        </CardHeader>
        <CardContent>
          <table className="w-full border-collapse text-sm">
            <thead>
              <tr className="border-border border-b">
                <th className="py-2 text-left">Dimension</th>
                <th className="py-2 text-right">POLARIS</th>
                <th className="py-2 text-right">ChatGPT DR</th>
                <th className="py-2 text-right">Gemini DR</th>
              </tr>
            </thead>
            <tbody>
              {ALL_BENCHMARK_DIMENSIONS.map((dim) => {
                const p = sb.aggregate.polaris_mean[dim];
                const c = sb.aggregate.chatgpt_mean[dim];
                const g = sb.aggregate.gemini_mean[dim];
                return (
                  <tr
                    key={dim}
                    data-testid={`agg-row-${dim}`}
                    className="border-border border-b"
                  >
                    <td className="py-2">{BENCHMARK_DIMENSION_LABELS[dim]}</td>
                    <td className={cn("py-2 text-right font-mono", tone_class(p, [c, g]))}>
                      {format_pct(p)}
                    </td>
                    <td className={cn("py-2 text-right font-mono", tone_class(c, [p, g]))}>
                      {format_pct(c)}
                    </td>
                    <td className={cn("py-2 text-right font-mono", tone_class(g, [p, c]))}>
                      {format_pct(g)}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </CardContent>
      </Card>
    </div>
  );
}
