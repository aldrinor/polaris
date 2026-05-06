"use client";

import Link from "next/link";
import { useEffect, useRef, useState, type ReactNode } from "react";

import { Button } from "@/components/ui/button";

import { CommandPalette } from "./command_palette";

type Template = {
  id: string;
  name: string;
  summary: string;
  sample_question: string;
  out_of_scope: string;
  active: boolean;
};

type Props = { templates: Template[]; signInHref: string; children: ReactNode };

export function HomeKeyboardShell({ templates, signInHref, children }: Props) {
  const [palette_open, set_palette_open] = useState(false);
  const sign_in_link_ref = useRef<HTMLAnchorElement>(null);

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
      <header className="border-border bg-background border-b">
        <div className="mx-auto flex w-full max-w-6xl items-center justify-between px-6 py-4">
          <div className="flex flex-col">
            <span className="text-muted-foreground text-xs font-medium tracking-widest uppercase">POLARIS Canada</span>
            <span className="text-foreground text-base font-semibold">Sovereign Deep Research</span>
          </div>
          <Button variant="default" nativeButton={false} render={<Link ref={sign_in_link_ref} data-testid="header-sign-in-link" href={signInHref} />}>
            Sign in
          </Button>
        </div>
      </header>
      {children}
      <CommandPalette open={palette_open} onOpenChange={set_palette_open} templates={templates} signInLinkRef={sign_in_link_ref} />
    </>
  );
}
