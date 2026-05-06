"use client";

import { useEffect, useRef } from "react";
import { Dialog as DialogPrimitive } from "@base-ui/react/dialog";

import { Button } from "@/components/ui/button";

const MAX_SAMPLE_LEN = 80;

export type DisambiguationCluster = {
  cluster_id: number;
  label: string;
  sample_snippets: string[];
};

export type DisambiguationModalProps = {
  open: boolean;
  clusters: DisambiguationCluster[];
  onSelectCluster: (cluster_id: number) => void;
  onCancel: () => void;
};

function previewSnippets(snippets: string[]): string {
  const joined = snippets.slice(0, 2).join(" · ");
  return joined.length > MAX_SAMPLE_LEN
    ? joined.slice(0, MAX_SAMPLE_LEN - 1) + "…"
    : joined;
}

export function DisambiguationModal({
  open,
  clusters,
  onSelectCluster,
  onCancel,
}: DisambiguationModalProps) {
  const is_cancelled_ref = useRef(false);
  useEffect(() => {
    if (open) is_cancelled_ref.current = false;
  }, [open]);
  const handleCancel = () => {
    if (is_cancelled_ref.current) return;
    is_cancelled_ref.current = true;
    onCancel();
  };
  return (
    <DialogPrimitive.Root
      open={open}
      onOpenChange={(next_open) => {
        if (!next_open) handleCancel();
      }}
    >
      <DialogPrimitive.Portal>
        <DialogPrimitive.Backdrop className="fixed inset-0 z-50 bg-black/20 transition-opacity duration-150 data-ending-style:opacity-0 data-starting-style:opacity-0 supports-backdrop-filter:backdrop-blur-xs" />
        <DialogPrimitive.Popup
          data-slot="disambiguation-modal"
          className="bg-popover text-popover-foreground fixed top-1/2 left-1/2 z-50 flex w-full max-w-lg -translate-x-1/2 -translate-y-1/2 flex-col gap-4 rounded-xl border p-6 shadow-lg transition duration-200 ease-in-out data-ending-style:scale-95 data-ending-style:opacity-0 data-starting-style:scale-95 data-starting-style:opacity-0"
        >
          <div className="flex flex-col gap-1">
            <DialogPrimitive.Title className="text-foreground text-lg font-semibold">
              Did you mean…
            </DialogPrimitive.Title>
            <DialogPrimitive.Description className="text-muted-foreground text-sm">
              We found multiple meanings. Pick one to focus the search.
            </DialogPrimitive.Description>
          </div>
          {clusters.length > 0 && (
            <ul className="flex flex-col gap-3">
              {clusters.map((c) => (
                <li key={c.cluster_id}>
                  <button
                    type="button"
                    data-testid={`disambiguation-cluster-${c.cluster_id}`}
                    aria-label={`Pick ${c.label}`}
                    onClick={() => onSelectCluster(c.cluster_id)}
                    className="border-border bg-muted/30 hover:bg-muted/60 flex w-full flex-col gap-1 rounded-lg border p-3 text-left focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:outline-none"
                  >
                    <span className="text-foreground text-sm font-semibold">
                      {c.label}
                    </span>
                    <span className="text-muted-foreground text-xs">
                      {previewSnippets(c.sample_snippets)}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
          <div className="flex justify-end gap-2 pt-2">
            <DialogPrimitive.Close
              render={
                <Button variant="outline" onClick={handleCancel}>
                  Cancel
                </Button>
              }
            />
          </div>
        </DialogPrimitive.Popup>
      </DialogPrimitive.Portal>
    </DialogPrimitive.Root>
  );
}
