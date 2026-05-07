"use client";

type Props = { ids: string[] };

export function SelectedDocsIndicator({ ids }: Props) {
  return (
    <div className="border-border bg-muted/10 flex flex-col gap-1 rounded-lg border p-3 text-sm">
      <span className="text-muted-foreground text-xs font-medium tracking-widest uppercase">
        Selected docs
      </span>
      <output
        data-testid="selected-doc-ids"
        className="text-foreground text-xs"
      >
        {ids.length === 0 ? "(none)" : ids.join(",")}
      </output>
    </div>
  );
}
