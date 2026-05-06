"use client";

import { Dialog as DialogPrimitive } from "@base-ui/react/dialog";
import { useRouter } from "next/navigation";
import { useState, type RefObject } from "react";

import { cn } from "@/lib/utils";

type Template = {
  id: string;
  name: string;
  summary: string;
  sample_question: string;
  out_of_scope: string;
  active: boolean;
};

type CommandPaletteProps = {
  open: boolean;
  onOpenChange: (next: boolean) => void;
  templates: Template[];
  signInLinkRef: RefObject<HTMLAnchorElement | null>;
};

export function CommandPalette({ open, onOpenChange, templates, signInLinkRef }: CommandPaletteProps) {
  const router = useRouter();
  const [search, set_search] = useState("");
  const [active_index, set_active_index] = useState(0);

  const filtered = templates.filter((t) => {
    if (!search) return true;
    const q = search.toLowerCase();
    return t.name.toLowerCase().includes(q) || t.summary.toLowerCase().includes(q) || t.sample_question.toLowerCase().includes(q);
  });

  const clamped = filtered.length === 0 ? 0 : Math.max(0, Math.min(active_index, filtered.length - 1));

  function handle_key(event: React.KeyboardEvent) {
    if (event.key === "ArrowDown") {
      event.preventDefault();
      set_active_index((p) => Math.min(p + 1, filtered.length - 1));
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      set_active_index((p) => Math.max(p - 1, 0));
    } else if (event.key === "Enter") {
      event.preventDefault();
      const tpl = filtered[clamped];
      if (tpl?.active) {
        router.push(`/intake?template=${tpl.id}`);
        onOpenChange(false);
      }
    }
  }

  return (
    <DialogPrimitive.Root
      open={open}
      onOpenChange={(next) => {
        onOpenChange(next);
        if (!next) requestAnimationFrame(() => signInLinkRef.current?.focus());
      }}
    >
      <DialogPrimitive.Portal>
        <DialogPrimitive.Backdrop className="fixed inset-0 z-50 bg-black/20" />
        <DialogPrimitive.Popup
          data-testid="command-palette"
          onKeyDown={handle_key}
          className="bg-popover text-popover-foreground fixed top-1/4 left-1/2 z-50 flex w-full max-w-xl -translate-x-1/2 flex-col gap-2 rounded-xl border p-4 shadow-lg"
        >
          <DialogPrimitive.Title className="sr-only">Search templates</DialogPrimitive.Title>
          <input
            data-testid="command-palette-input"
            autoFocus
            value={search}
            onChange={(e) => set_search(e.target.value)}
            placeholder="Search templates..."
            className="border-border focus:ring-ring rounded-md border px-3 py-2 text-sm focus:outline-none focus:ring-2"
          />
          <ul className="max-h-80 overflow-y-auto" role="listbox">
            {filtered.map((t, i) => (
              <li
                key={t.id}
                data-testid={`palette-item-${t.id}`}
                data-active={i === clamped ? "true" : undefined}
                aria-disabled={!t.active || undefined}
                className={cn("rounded-md px-3 py-2 text-sm", i === clamped && "bg-accent", !t.active && "text-muted-foreground")}
              >
                <span className="font-medium">{t.name}</span>
                {!t.active ? <span className="ml-2 text-xs uppercase">(coming soon)</span> : null}
              </li>
            ))}
          </ul>
        </DialogPrimitive.Popup>
      </DialogPrimitive.Portal>
    </DialogPrimitive.Root>
  );
}
