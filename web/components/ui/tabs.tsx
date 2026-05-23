// I-cd-013a (GH#609) — Tabs primitive wrapping @base-ui/react/tabs.
//
// Used by web/app/inspector/[runId]/inspector_view.tsx and any
// downstream route that needs a tabbed layout. Each TabsContent
// carries a `data-tab` attribute so Playwright e2e can assert tab
// state explicitly per the Codex iter-2 P2 #3 directive.
"use client";

import { Tabs as BaseTabs } from "@base-ui/react/tabs";
import { forwardRef, type ComponentPropsWithoutRef } from "react";

import { cn } from "@/lib/utils";

export const Tabs = BaseTabs.Root;

export const TabsList = forwardRef<
  HTMLDivElement,
  ComponentPropsWithoutRef<typeof BaseTabs.List>
>(({ className, ...props }, ref) => (
  <BaseTabs.List
    ref={ref}
    className={cn(
      "border-border bg-muted text-muted-foreground inline-flex h-10 items-center justify-start gap-1 rounded-md border p-1",
      className,
    )}
    {...props}
  />
));
TabsList.displayName = "TabsList";

export const TabsTrigger = forwardRef<
  HTMLButtonElement,
  ComponentPropsWithoutRef<typeof BaseTabs.Tab>
>(({ className, ...props }, ref) => (
  <BaseTabs.Tab
    ref={ref}
    className={cn(
      "ring-offset-background inline-flex items-center justify-center rounded-sm px-3 py-1.5 text-sm font-medium whitespace-nowrap transition-all",
      // I-p2-026 (#765): explicit inactive text color. The inherited
      // text-muted-foreground on the bg-muted strip fails WCAG 2.2 AA
      // contrast (axe serious); text-foreground/70 clears 4.5:1 while still
      // reading lighter than the selected tab.
      "text-foreground/70",
      "focus-visible:ring-ring focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:outline-none",
      "data-[selected]:bg-background data-[selected]:text-foreground data-[selected]:shadow-sm",
      "hover:bg-background/60",
      "disabled:pointer-events-none disabled:opacity-50",
      className,
    )}
    {...props}
  />
));
TabsTrigger.displayName = "TabsTrigger";

export const TabsContent = forwardRef<
  HTMLDivElement,
  ComponentPropsWithoutRef<typeof BaseTabs.Panel> & { tabId: string }
>(({ className, tabId, ...props }, ref) => (
  <BaseTabs.Panel
    ref={ref}
    data-tab={tabId}
    className={cn(
      "ring-offset-background focus-visible:ring-ring mt-4 focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:outline-none",
      className,
    )}
    {...props}
  />
));
TabsContent.displayName = "TabsContent";
