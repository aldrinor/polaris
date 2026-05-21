"use client";

import Link from "next/link";
import { useEffect, useRef, useState, type ReactNode } from "react";

import { NavLink } from "@/components/nav_link";
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

// I-cd-022 (#612): primary nav now lives in the home header too, so /
// matches the global app-shell nav (G1: "global header/sidebar nav is
// present and identical"). When AppShell is suppressed on `/` via
// AppShellGate, the home page's <header> is THE app shell for this route.
const PRIMARY_NAV: ReadonlyArray<{ href: string; label: string }> = [
  { href: "/", label: "Home" },
  { href: "/intake", label: "Intake" },
  { href: "/dashboard", label: "Dashboard" },
  { href: "/upload", label: "Upload" },
  { href: "/benchmark", label: "Benchmark" },
  { href: "/compare", label: "Compare" },
  { href: "/contracts", label: "Contracts" },
  { href: "/pin_replay", label: "Pin Replay" },
  { href: "/memory", label: "Memory" },
];

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
        <div className="mx-auto flex w-full max-w-7xl items-center justify-between gap-6 px-6 py-3">
          <Link
            href="/"
            className="text-foreground font-mono text-sm font-semibold tracking-tight"
          >
            POLARIS · Canada
          </Link>
          <nav className="flex items-center gap-1" aria-label="Primary">
            {PRIMARY_NAV.map((item) => (
              <NavLink key={item.href} href={item.href}>
                {item.label}
              </NavLink>
            ))}
          </nav>
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
