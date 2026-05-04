"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import type {
  IntakeAmbiguityAxis,
  IntakeScopeDecision,
  IntakeStatus,
} from "@/lib/api";

const STATUS_LABEL: Record<IntakeStatus, string> = {
  in_scope: "In scope — ready to research",
  ambiguous_needs_clarification: "Ambiguous — clarification needed",
  out_of_scope: "Out of scope for POLARIS clinical research",
  refused: "Refused — instruction-override attempt detected",
};

const STATUS_TONE: Record<IntakeStatus, string> = {
  in_scope:
    "border-emerald-500/40 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300",
  ambiguous_needs_clarification:
    "border-amber-500/40 bg-amber-500/10 text-amber-700 dark:text-amber-300",
  out_of_scope:
    "border-slate-500/40 bg-slate-500/10 text-slate-700 dark:text-slate-300",
  refused:
    "border-rose-500/40 bg-rose-500/10 text-rose-700 dark:text-rose-300",
};

function StatusBadge({ status }: { status: IntakeStatus }) {
  return (
    <span
      data-testid="scope-status-badge"
      className={cn(
        "inline-flex items-center gap-2 rounded-full border px-3 py-1",
        "text-xs font-medium tracking-wide",
        STATUS_TONE[status],
      )}
    >
      <span aria-hidden="true">●</span>
      {STATUS_LABEL[status]}
    </span>
  );
}

function AxisRow({ axis }: { axis: IntakeAmbiguityAxis }) {
  return (
    <li
      data-testid={`axis-row-${axis.axis}`}
      className="border-border flex flex-col gap-1.5 rounded-md border p-3"
    >
      <div className="flex items-baseline justify-between">
        <span className="text-foreground text-sm font-medium capitalize">
          {axis.axis}
        </span>
        <span
          className={cn(
            "rounded-full px-2 py-0.5 text-[10px] font-medium tracking-widest uppercase",
            axis.needs_clarification
              ? "bg-amber-500/15 text-amber-700 dark:text-amber-300"
              : "bg-emerald-500/15 text-emerald-700 dark:text-emerald-300",
          )}
        >
          {axis.needs_clarification ? "ambiguous" : "clear"}
        </span>
      </div>
      <ul className="text-muted-foreground flex flex-wrap gap-1.5 text-xs">
        {axis.plausible_interpretations.map((interp) => (
          <li
            key={interp}
            className="border-border bg-muted/40 rounded border px-1.5 py-0.5"
          >
            {interp}
          </li>
        ))}
      </ul>
    </li>
  );
}

export function ScopeDecisionView({
  decision,
}: {
  decision: IntakeScopeDecision;
}) {
  return (
    <Card data-testid="scope-decision-view" className="flex flex-col gap-3">
      <CardHeader className="flex flex-row items-center justify-between gap-3">
        <CardTitle className="text-lg">Scope decision</CardTitle>
        <StatusBadge status={decision.status} />
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <dl className="grid grid-cols-2 gap-x-6 gap-y-2 text-sm">
          <dt className="text-muted-foreground">Scope class</dt>
          <dd
            data-testid="scope-class-value"
            className="text-foreground font-medium"
          >
            {decision.scope_class ?? "—"}
          </dd>

          <dt className="text-muted-foreground">Latency</dt>
          <dd
            data-testid="scope-latency-value"
            className="text-foreground font-medium"
          >
            {decision.latency_ms} ms
          </dd>

          <dt className="text-muted-foreground">Decision id</dt>
          <dd className="text-foreground truncate font-mono text-xs">
            {decision.decision_id}
          </dd>

          <dt className="text-muted-foreground">Decided at</dt>
          <dd className="text-foreground font-mono text-xs">
            {decision.decided_at_utc}
          </dd>
        </dl>

        {decision.ambiguity_axes.length ? (
          <section className="flex flex-col gap-2">
            <h3 className="text-foreground text-sm font-medium">
              PICO axes
            </h3>
            <ul className="grid grid-cols-1 gap-2 sm:grid-cols-3">
              {decision.ambiguity_axes.map((axis) => (
                <AxisRow key={axis.axis} axis={axis} />
              ))}
            </ul>
          </section>
        ) : null}

        {decision.clarifications_needed.length ? (
          <section className="flex flex-col gap-1">
            <h3 className="text-foreground text-sm font-medium">
              Clarifications needed
            </h3>
            <ul className="text-muted-foreground list-disc pl-5 text-sm">
              {decision.clarifications_needed.map((c, idx) => (
                <li key={idx} data-testid="clarification-item">
                  {c}
                </li>
              ))}
            </ul>
          </section>
        ) : null}
      </CardContent>
    </Card>
  );
}
