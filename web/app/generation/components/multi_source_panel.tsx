"use client";

import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import {
  type EvidencePool,
  type RetrievalSource,
  type RetrievalSourceTier,
} from "@/lib/api";
import type { ParsedToken } from "@/lib/provenance_tokens";

const TIER_TONE: Record<RetrievalSourceTier, string> = {
  T1: "border-emerald-500/40 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300",
  T2: "border-amber-500/40 bg-amber-500/10 text-amber-700 dark:text-amber-300",
  T3: "border-sky-500/40 bg-sky-500/10 text-sky-700 dark:text-sky-300",
};

function groupTokensBySource(
  tokens: ParsedToken[],
): Map<string, ParsedToken[]> {
  const grouped = new Map<string, ParsedToken[]>();
  for (const tok of tokens) {
    const list = grouped.get(tok.source_id) ?? [];
    list.push(tok);
    grouped.set(tok.source_id, list);
  }
  return grouped;
}

function SourceRow({
  source_id,
  source,
  tokens,
}: {
  source_id: string;
  source: RetrievalSource | undefined;
  tokens: ParsedToken[];
}) {
  if (!source) {
    return (
      <div
        data-testid={`multi-source-pane-missing-${source_id}`}
        className="rounded border border-rose-500/40 p-2 text-xs text-rose-700 dark:text-rose-300"
      >
        Source not found in evidence pool: <code>{source_id}</code>
      </div>
    );
  }
  const text = source.full_text ?? source.snippet ?? "";
  return (
    <div
      data-testid={`multi-source-pane-source-${source_id}`}
      className="border-border flex flex-col gap-1 rounded border p-2 text-xs"
    >
      <div className="flex items-center justify-between gap-2">
        <a
          href={source.url}
          target="_blank"
          rel="noopener noreferrer"
          className="text-blue-700 underline dark:text-blue-300"
          title={source.url}
        >
          <code>{source.source_id}</code> · {source.domain}
        </a>
        <span
          data-testid={`multi-source-pane-tier-${source_id}`}
          className={`rounded-full border px-2 py-0.5 text-[10px] tracking-widest uppercase ${TIER_TONE[source.tier]}`}
        >
          {source.tier}
        </span>
      </div>
      <p className="text-muted-foreground">
        <strong className="text-foreground">{source.title}</strong>
        {source.publication_date ? <> · {source.publication_date}</> : null}
      </p>
      <div className="flex flex-col gap-1">
        {tokens.map((tok, j) => {
          const out_of_range =
            tok.start >= text.length || tok.end > text.length;
          if (out_of_range) {
            return (
              <p
                key={j}
                data-testid={`multi-source-pane-span-out-of-range-${source_id}-${j}`}
                className="text-rose-700 dark:text-rose-300"
              >
                (span out of range: {tok.start}-{tok.end} of {text.length})
              </p>
            );
          }
          const span = text.slice(tok.start, tok.end);
          return (
            <blockquote
              key={j}
              data-testid={`multi-source-pane-span-${source_id}-${j}`}
              className="border-l-2 border-yellow-400 bg-yellow-50 px-2 py-1 italic dark:bg-yellow-900/20"
            >
              {span || "(empty span)"}
            </blockquote>
          );
        })}
      </div>
    </div>
  );
}

export function MultiSourcePanel({
  open,
  onOpenChange,
  tokens,
  pool,
  sentence_text,
}: {
  open: boolean;
  onOpenChange: (next: boolean) => void;
  tokens: ParsedToken[];
  pool: EvidencePool | null;
  sentence_text: string;
}) {
  const grouped = groupTokensBySource(tokens);
  const distinct_count = grouped.size;
  const sources_by_id = new Map<string, RetrievalSource>();
  if (pool) {
    for (const s of pool.sources) sources_by_id.set(s.source_id, s);
  }
  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent
        data-testid="multi-source-pane"
        side="right"
        className="data-[side=right]:w-full data-[side=right]:sm:w-2/5 data-[side=right]:sm:max-w-none"
      >
        <SheetHeader>
          <SheetTitle data-testid="multi-source-pane-title">
            Multi-source claim — {distinct_count} sources
          </SheetTitle>
          <SheetDescription>
            All distinct sources cited by this claim. Each row shows the cited
            span(s) drawn from that source.
          </SheetDescription>
        </SheetHeader>
        <div className="px-4 pb-4 text-sm">
          <p
            data-testid="multi-source-pane-sentence"
            className="text-muted-foreground border-border mb-3 rounded border bg-blue-500/5 p-2 text-xs"
          >
            {sentence_text}
          </p>
          <div className="flex flex-col gap-2">
            {Array.from(grouped.entries()).map(([source_id, toks]) => (
              <SourceRow
                key={source_id}
                source_id={source_id}
                source={sources_by_id.get(source_id)}
                tokens={toks}
              />
            ))}
          </div>
        </div>
      </SheetContent>
    </Sheet>
  );
}
