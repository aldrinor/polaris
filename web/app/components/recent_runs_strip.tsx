"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { authHeader } from "@/lib/auth";

// I-cd-ui-001 (#704): home recent-runs strip. Consumes the GET /api/v6/runs
// list endpoint (#705). The home is PUBLIC and the runs endpoint is
// auth-gated (bearer token), so this MUST degrade to null on 401 / any
// failure / empty — never an error and never a /sign-in redirect (that is
// why it uses authHeader() directly, not authFetch which redirects).

type RunRow = {
  run_id: string;
  template: string;
  question: string;
  finished_at: string | null;
};

function formatFinished(value: string | null): string | null {
  if (!value) return null;
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return null; // tolerate malformed finished_at
  return d.toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
  });
}

export function RecentRunsStrip() {
  const [runs, setRuns] = useState<RunRow[]>([]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await fetch("/api/v6/runs?status=completed&limit=5", {
          headers: authHeader(),
        });
        if (!res.ok) return; // 401 (logged-out) or any non-ok → render nothing
        const data: unknown = await res.json();
        if (!cancelled && Array.isArray(data)) {
          setRuns(data as RunRow[]);
        }
      } catch {
        // network / parse failure → render nothing
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  if (runs.length === 0) return null;

  return (
    <section
      aria-labelledby="recent_runs_heading"
      className="flex flex-col gap-3"
    >
      <h2
        id="recent_runs_heading"
        className="text-muted-foreground text-xs font-medium tracking-widest uppercase"
      >
        Recent verifications
      </h2>
      <div className="flex flex-wrap gap-2" data-testid="recent-runs-strip">
        {runs.map((run) => {
          const finished = formatFinished(run.finished_at);
          return (
            <Link
              key={run.run_id}
              href={`/runs/${run.run_id}`}
              data-testid={`recent-run-${run.run_id}`}
              className="border-border bg-card hover:border-primary/40 focus-visible:ring-ring group flex max-w-xs flex-col gap-1 rounded-lg border px-3 py-2 transition-colors focus-visible:ring-2 focus-visible:outline-none"
            >
              <span className="text-primary text-[10px] font-semibold tracking-widest uppercase">
                {run.template}
                {finished ? (
                  <span className="text-muted-foreground font-normal">
                    {" · "}
                    {finished}
                  </span>
                ) : null}
              </span>
              <span className="text-foreground line-clamp-2 text-sm">
                {run.question}
              </span>
            </Link>
          );
        })}
      </div>
    </section>
  );
}
