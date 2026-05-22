"use client";

import Link from "next/link";
import { useEffect, useRef, useState, type ReactNode } from "react";

import { Button } from "@/components/ui/button";
import { PrimaryNav } from "@/components/primary_nav";

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

// I-cd-022 (#612): the home header carries the same nav as AppShell (G1:
// "global header nav present and identical"). I-p2-029 (#768): that nav is now
// the single shared source @/lib/nav (no more duplicated const), role-aware via
// navForRole (presentation-only).

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
      <header className="border-border bg-background relative border-b">
        <div className="mx-auto flex w-full max-w-7xl items-center justify-between gap-6 px-6 py-3">
          <Link
            href="/"
            className="text-foreground font-mono text-sm font-semibold tracking-tight"
          >
            POLARIS · Canada
          </Link>
          <PrimaryNav />
          {/* I-ui-010 (#730): sovereign mark — honest wording (no air-gap
              overclaim). */}
          <span
            className="text-muted-foreground border-border mr-2 ml-auto hidden rounded-full border px-2.5 py-1 text-xs lg:inline-flex"
            title="Canadian AI processing · public-source retrieval via logged Canadian egress · no external AI vendor"
          >
            ⬡ Canadian AI · no external AI vendor
          </span>
          <Button
            variant="outline"
            nativeButton={false}
            render={
              <Link
                ref={sign_in_link_ref}
                data-testid="header-sign-in-link"
                href={signInHref}
              />
            }
          >
            Sign in
          </Button>
        </div>
      </header>
      {children}
      <CommandPalette
        open={palette_open}
        onOpenChange={set_palette_open}
        templates={templates}
        signInLinkRef={sign_in_link_ref}
      />
    </>
  );
}
