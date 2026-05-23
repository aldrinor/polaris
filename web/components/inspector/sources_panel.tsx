// I-cd-013a (GH#609) — Source snapshots panel (full-text UTF-8 viewer).
"use client";

import { useState } from "react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

interface SourcesPanelProps {
  sources: Record<string, string>;
}

export function SourcesPanel({ sources }: SourcesPanelProps) {
  const paths = Object.keys(sources).sort();
  const [active, setActive] = useState<string | null>(paths[0] ?? null);

  return (
    <Card data-testid="sources-panel">
      <CardHeader>
        <CardTitle>Source snapshots ({paths.length})</CardTitle>
      </CardHeader>
      <CardContent>
        {paths.length === 0 ? (
          <p className="border-border text-muted-foreground rounded-md border border-dashed p-4 text-center">
            No source snapshots in this bundle.
          </p>
        ) : (
          <div className="grid grid-cols-1 gap-4 md:grid-cols-[minmax(200px,1fr)_3fr]">
            <ul className="border-border space-y-1 border-r pr-3">
              {paths.map((p) => (
                <li key={p}>
                  <button
                    type="button"
                    onClick={() => setActive(p)}
                    data-testid="source-tab"
                    data-source-path={p}
                    data-active={active === p}
                    className={`hover:bg-muted w-full rounded-sm px-2 py-1 text-left font-mono text-xs ${
                      active === p
                        ? "bg-muted text-foreground"
                        : "text-muted-foreground"
                    }`}
                  >
                    {p}
                  </button>
                </li>
              ))}
            </ul>
            {/* I-p2-026 (#765): the scrollable snapshot region needs keyboard
                access (axe scrollable-region-focusable / WCAG 2.1.1). */}
            <pre
              className="bg-muted focus-visible:ring-ring max-h-[400px] overflow-auto rounded-md p-3 text-xs whitespace-pre-wrap focus-visible:ring-2 focus-visible:outline-none"
              data-testid="source-content"
              data-source-path={active}
              tabIndex={0}
              role="region"
              aria-label="Source snapshot content"
            >
              {active ? sources[active] : ""}
            </pre>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
