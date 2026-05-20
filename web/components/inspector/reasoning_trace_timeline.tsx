// I-cd-013a (GH#609) — Reasoning trace timeline (one card per JSONL record).
"use client";

import { useState } from "react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { ReasoningTraceRecord } from "@/lib/signed_bundle";

interface ReasoningTraceTimelineProps {
  records: ReasoningTraceRecord[];
}

export function ReasoningTraceTimeline({
  records,
}: ReasoningTraceTimelineProps) {
  return (
    <Card data-testid="reasoning-trace-timeline">
      <CardHeader>
        <CardTitle>Reasoning trace ({records.length} calls)</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        {records.length === 0 ? (
          <p className="border-border text-muted-foreground rounded-md border border-dashed p-4 text-center">
            No reasoning trace records.
          </p>
        ) : (
          records.map((r) => <TraceRecordCard key={r.call_id} record={r} />)
        )}
      </CardContent>
    </Card>
  );
}

function TraceRecordCard({ record }: { record: ReasoningTraceRecord }) {
  const [expanded, setExpanded] = useState(false);
  return (
    <div
      className="border-border rounded-md border p-3"
      data-testid="reasoning-trace-record"
      data-call-id={record.call_id}
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2 text-sm">
          <span className="text-muted-foreground font-mono text-xs">
            {record.call_id}
          </span>
          <span className="bg-muted rounded-md px-2 py-0.5 text-xs">
            {record.call_type}
          </span>
          <span className="text-muted-foreground text-xs">
            {record.section}
          </span>
        </div>
        <div className="flex items-center gap-2 text-xs">
          <span
            data-testid="reasoning-status"
            data-status={record.status}
            className="bg-muted/60 rounded-md px-2 py-0.5 font-mono"
          >
            {record.status}
          </span>
          <span className="bg-muted/60 rounded-md px-2 py-0.5 font-mono">
            {record.content_source}
          </span>
        </div>
      </div>
      <div className="text-muted-foreground mt-2 grid grid-cols-3 gap-2 text-xs">
        <span>input: {record.input_tokens}</span>
        <span>output: {record.output_tokens}</span>
        <span>reasoning: {record.reasoning_tokens}</span>
      </div>
      <button
        type="button"
        className="focus-visible:ring-ring mt-2 inline-flex items-center gap-1 text-xs underline-offset-2 hover:underline focus-visible:ring-2 focus-visible:outline-none"
        onClick={() => setExpanded((v) => !v)}
        data-testid="toggle-trace-content"
      >
        {expanded ? "Hide" : "Show"} content + reasoning
      </button>
      {expanded && (
        <div className="mt-2 space-y-2">
          <section>
            <p className="text-muted-foreground text-xs font-medium tracking-wide uppercase">
              Reasoning text
            </p>
            <pre className="bg-muted rounded-md p-2 text-xs whitespace-pre-wrap">
              {record.reasoning_text}
            </pre>
          </section>
          <section>
            <p className="text-muted-foreground text-xs font-medium tracking-wide uppercase">
              Content text
            </p>
            <pre className="bg-muted rounded-md p-2 text-xs whitespace-pre-wrap">
              {record.content_text}
            </pre>
          </section>
        </div>
      )}
    </div>
  );
}
