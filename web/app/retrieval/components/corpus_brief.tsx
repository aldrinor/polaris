"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import {
  countSourcesByTier,
  sortSourcesByTier,
  type EvidencePool,
  type RetrievalSourceTier,
} from "@/lib/api";

const TIER_LABEL: Record<RetrievalSourceTier, string> = {
  T1: "T1 — Regulatory + Cochrane",
  T2: "T2 — Peer-reviewed primary",
  T3: "T3 — Registries + agencies",
};

const TIER_TONE: Record<RetrievalSourceTier, string> = {
  T1: "border-emerald-500/40 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300",
  T2: "border-sky-500/40 bg-sky-500/10 text-sky-700 dark:text-sky-300",
  T3: "border-amber-500/40 bg-amber-500/10 text-amber-700 dark:text-amber-300",
};

function TierBadge({
  tier,
  count,
  required,
}: {
  tier: RetrievalSourceTier;
  count: number;
  required: number;
}) {
  const ok = count >= required;
  return (
    <span
      data-testid={`tier-badge-${tier}`}
      className={cn(
        "inline-flex items-center gap-2 rounded-full border px-3 py-1 text-xs font-medium",
        TIER_TONE[tier],
      )}
    >
      <span aria-hidden="true">{ok ? "●" : "◌"}</span>
      <span>{TIER_LABEL[tier]}</span>
      <span className="font-mono">
        {count} / {required}
      </span>
    </span>
  );
}

export function CorpusBrief({ pool }: { pool: EvidencePool }) {
  const sorted = sortSourcesByTier(pool.sources);
  const adequate = pool.adequacy.is_adequate;

  return (
    <Card data-testid="corpus-brief" className="flex flex-col gap-3">
      <CardHeader className="flex flex-row items-center justify-between gap-3">
        <CardTitle className="text-lg">Corpus brief</CardTitle>
        <span
          data-testid="adequacy-badge"
          className={cn(
            "rounded-full border px-3 py-1 text-xs font-medium",
            adequate
              ? "border-emerald-500/40 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300"
              : "border-rose-500/40 bg-rose-500/10 text-rose-700 dark:text-rose-300",
          )}
        >
          {adequate ? "Adequate" : "Inadequate"}
        </span>
      </CardHeader>

      <CardContent className="flex flex-col gap-4">
        <div className="flex flex-wrap gap-2">
          {(["T1", "T2", "T3"] as RetrievalSourceTier[]).map((tier) => (
            <TierBadge
              key={tier}
              tier={tier}
              count={countSourcesByTier(pool, tier)}
              required={pool.adequacy.min_required_per_tier[tier] ?? 0}
            />
          ))}
        </div>

        {pool.adequacy.failure_reason ? (
          <p
            data-testid="adequacy-failure-reason"
            className="border-rose-500/40 bg-rose-500/5 text-rose-700 dark:text-rose-300 rounded-md border px-3 py-2 text-sm"
          >
            {pool.adequacy.failure_reason}
          </p>
        ) : null}

        <dl className="grid grid-cols-2 gap-x-6 gap-y-1 text-sm">
          <dt className="text-muted-foreground">Sources retrieved</dt>
          <dd className="text-foreground font-medium">
            {pool.sources.length}
          </dd>
          <dt className="text-muted-foreground">Queries executed</dt>
          <dd className="text-foreground font-medium">
            {pool.queries_executed.length}
          </dd>
          <dt className="text-muted-foreground">Latency</dt>
          <dd className="text-foreground font-medium">{pool.latency_ms} ms</dd>
          <dt className="text-muted-foreground">Cost</dt>
          <dd className="text-foreground font-medium">
            ${pool.cost_usd.toFixed(4)}
          </dd>
        </dl>

        <section className="flex flex-col gap-2">
          <h3 className="text-foreground text-sm font-medium">
            Sources ({sorted.length})
          </h3>
          <ul className="flex flex-col gap-2">
            {sorted.map((source) => (
              <li
                key={source.source_id}
                data-testid="source-item"
                className="border-border flex flex-col gap-1 rounded-md border p-3"
              >
                <div className="flex items-center justify-between gap-3">
                  <span
                    className={cn(
                      "rounded px-1.5 py-0.5 text-[10px] font-medium tracking-widest uppercase",
                      TIER_TONE[source.tier],
                    )}
                  >
                    {source.tier}
                  </span>
                  <span className="text-muted-foreground font-mono text-xs">
                    {source.domain}
                  </span>
                </div>
                <a
                  href={source.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-foreground hover:text-foreground/80 text-sm font-medium underline-offset-2 hover:underline"
                >
                  {source.title}
                </a>
                {source.snippet ? (
                  <p className="text-muted-foreground text-xs">
                    {source.snippet}
                  </p>
                ) : null}
              </li>
            ))}
          </ul>
        </section>
      </CardContent>
    </Card>
  );
}
