// I-ux-001c sub-PR 3 (GH #884): `Textarea` wrapper.
//
// Codex iter-3 P1: web/components/ui/textarea.tsx didn't exist; sub-PR 3
// adds it. Mirrors input.tsx's structure + style tokens, but uses a styled
// NATIVE `<textarea>` because `@base-ui/react/textarea` is not exported
// by the installed @base-ui/react version. This is the second option Codex
// offered ("specify a native styled `<textarea>`"). Consistent with how the
// shadcn-ui project ships its Textarea (native textarea, design-token
// classes only) — no behavioral departure from input.tsx.
import * as React from "react";

import { cn } from "@/lib/utils";

function Textarea({
  className,
  ...props
}: React.ComponentProps<"textarea">) {
  return (
    <textarea
      data-slot="textarea"
      className={cn(
        "border-input placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-ring/70 disabled:bg-input/50 aria-invalid:border-destructive aria-invalid:ring-destructive/20 dark:bg-input/30 dark:disabled:bg-input/80 dark:aria-invalid:border-destructive/50 dark:aria-invalid:ring-destructive/40 field-sizing-content min-h-16 w-full min-w-0 resize-y rounded-lg border bg-transparent px-3 py-2 text-base transition-colors outline-none focus-visible:ring-3 disabled:pointer-events-none disabled:cursor-not-allowed disabled:opacity-50 aria-invalid:ring-3 md:text-sm",
        className,
      )}
      {...props}
    />
  );
}

export { Textarea };
