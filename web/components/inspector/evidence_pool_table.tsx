// I-cd-013a (GH#609) — Sources table + adequacy verdict.
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

interface SourceShape {
  source_id: string;
  url: string;
  domain: string;
  tier: string;
  title: string;
  authors: string[];
  snippet: string;
}

interface AdequacyShape {
  is_adequate: boolean;
  failure_reason: string | null;
  sources_per_tier: Record<string, number>;
  min_required_per_tier: Record<string, number>;
}

interface EvidencePoolShape {
  pool_id: string;
  decision_id: string;
  sources: SourceShape[];
  adequacy: AdequacyShape;
  queries_executed: string[];
  cost_usd: number;
  latency_ms: number;
}

function asPool(value: unknown): EvidencePoolShape {
  return value as EvidencePoolShape;
}

export function EvidencePoolTable({ value }: { value: unknown }) {
  const p = asPool(value);
  return (
    <Card data-testid="evidence-pool-table">
      <CardHeader>
        <CardTitle>Evidence pool ({p.sources.length} sources)</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4 text-sm">
        <AdequacyBadge adequacy={p.adequacy} />
        {p.sources.length === 0 ? (
          <p className="border-border text-muted-foreground rounded-md border border-dashed p-4 text-center">
            No sources captured for this run.
          </p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left">
              <thead className="border-border text-muted-foreground border-b text-xs tracking-wide uppercase">
                <tr>
                  <th className="px-2 py-2">Tier</th>
                  <th className="px-2 py-2">Domain</th>
                  <th className="px-2 py-2">Title</th>
                  <th className="px-2 py-2">Snippet</th>
                </tr>
              </thead>
              <tbody>
                {p.sources.map((s) => (
                  <tr
                    key={s.source_id}
                    className="border-border border-b last:border-0"
                  >
                    <td className="px-2 py-2 align-top">
                      <span className="bg-muted inline-flex items-center rounded-md px-2 py-0.5 text-xs font-medium">
                        {s.tier}
                      </span>
                    </td>
                    <td className="px-2 py-2 align-top font-mono text-xs">
                      {s.domain}
                    </td>
                    <td className="px-2 py-2 align-top">
                      <a
                        href={s.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="hover:text-foreground underline"
                      >
                        {s.title}
                      </a>
                    </td>
                    <td className="text-muted-foreground px-2 py-2 align-top text-xs">
                      {s.snippet}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function AdequacyBadge({ adequacy }: { adequacy: AdequacyShape }) {
  return (
    <div
      data-testid="adequacy-badge"
      data-state={adequacy.is_adequate ? "adequate" : "inadequate"}
      className="border-border bg-muted/40 rounded-md border p-3"
    >
      <div className="flex items-center justify-between">
        <p className="font-medium">Adequacy</p>
        <span
          className={
            adequacy.is_adequate
              ? "rounded-md bg-emerald-100 px-2 py-0.5 text-xs font-medium text-emerald-900 dark:bg-emerald-950 dark:text-emerald-200"
              : "rounded-md bg-amber-100 px-2 py-0.5 text-xs font-medium text-amber-900 dark:bg-amber-950 dark:text-amber-200"
          }
        >
          {adequacy.is_adequate ? "Adequate" : "Inadequate"}
        </span>
      </div>
      {adequacy.failure_reason && (
        <p className="text-muted-foreground mt-2 text-xs">
          {adequacy.failure_reason}
        </p>
      )}
    </div>
  );
}
