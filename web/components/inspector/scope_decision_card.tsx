// I-cd-013a (GH#609) — Renders the ScopeDecision content.
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

interface ScopeDecisionAxis {
  axis_name: string;
  plausible_interpretations: string[];
  needs_clarification: boolean;
}

interface ScopeDecisionShape {
  status: string;
  scope_class: string | null;
  ambiguity_axes: ScopeDecisionAxis[];
  clarifications_needed: string[];
  decision_id: string;
  decided_at_utc: string;
  latency_ms: number;
  provenance: Record<string, string>;
}

function asScopeDecision(value: unknown): ScopeDecisionShape {
  return value as ScopeDecisionShape;
}

export function ScopeDecisionCard({ value }: { value: unknown }) {
  const d = asScopeDecision(value);
  return (
    <Card data-testid="scope-decision-card">
      <CardHeader>
        <CardTitle>Scope decision</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4 text-sm">
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <KV label="Status" value={d.status} />
          <KV label="Scope class" value={d.scope_class ?? "(not assigned)"} />
          <KV label="Decision ID" value={d.decision_id} mono />
          <KV label="Latency (ms)" value={String(d.latency_ms)} />
        </div>
        {d.ambiguity_axes.length > 0 && (
          <section>
            <h3 className="text-muted-foreground mb-2 text-xs font-semibold tracking-wide uppercase">
              Ambiguity axes
            </h3>
            <ul className="space-y-2">
              {d.ambiguity_axes.map((a) => (
                <li
                  key={a.axis_name}
                  className="border-border bg-muted/30 rounded-md border p-3"
                >
                  <p className="font-medium">{a.axis_name}</p>
                  {a.plausible_interpretations.length > 0 && (
                    <ul className="text-muted-foreground mt-1 ml-4 list-disc text-xs">
                      {a.plausible_interpretations.map((i) => (
                        <li key={i}>{i}</li>
                      ))}
                    </ul>
                  )}
                </li>
              ))}
            </ul>
          </section>
        )}
        {d.clarifications_needed.length > 0 && (
          <section>
            <h3 className="text-muted-foreground mb-2 text-xs font-semibold tracking-wide uppercase">
              Clarifications needed
            </h3>
            <ul className="ml-4 list-disc text-sm">
              {d.clarifications_needed.map((c) => (
                <li key={c}>{c}</li>
              ))}
            </ul>
          </section>
        )}
      </CardContent>
    </Card>
  );
}

function KV({
  label,
  value,
  mono = false,
}: {
  label: string;
  value: string;
  mono?: boolean;
}) {
  return (
    <div>
      <p className="text-muted-foreground text-xs tracking-wide uppercase">
        {label}
      </p>
      <p className={mono ? "font-mono text-sm" : "text-sm"}>{value}</p>
    </div>
  );
}
