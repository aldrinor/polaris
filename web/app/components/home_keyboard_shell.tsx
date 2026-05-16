"use client";

import { useEffect, useState, type ReactNode } from "react";

import { CommandPalette } from "./command_palette";

type Template = {
  id: string;
  name: string;
  summary: string;
  sample_question: string;
  out_of_scope: string;
  active: boolean;
};

type Props = { templates: Template[]; children: ReactNode };

/**
 * Landing-page keyboard shell — Cmd/Ctrl-K opens the template command
 * palette. I-rdy-014 (#510): the brand/sign-in header was removed from
 * here; `GlobalNav` (mounted in app/layout.tsx) is now the single header,
 * so this shell only provides the keyboard affordance + palette mount.
 */
export function HomeKeyboardShell({ templates, children }: Props) {
  const [palette_open, set_palette_open] = useState(false);

  useEffect(() => {
    function on_keydown(event: KeyboardEvent) {
      if ((event.metaKey || event.ctrlKey) && event.key === "k") {
        event.preventDefault();
        event.stopPropagation();
        set_palette_open((p) => !p);
      }
    }
    window.addEventListener("keydown", on_keydown);
    return () => window.removeEventListener("keydown", on_keydown);
  }, []);

  return (
    <>
      {children}
      <CommandPalette
        open={palette_open}
        onOpenChange={set_palette_open}
        templates={templates}
      />
    </>
  );
}
