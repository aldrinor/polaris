"use client";

// I-ux-001c (#878) sub-PR 2: minimal client shell that mounts the global
// CommandPalette on Home + binds Ctrl+K + provides the focus-restore target
// the palette returns focus to on close.
//
// EXTRACTED from `web/app/components/home_keyboard_shell.tsx` (now deleted).
// Drops the marketing-header chrome (`PrimaryNav`, sovereign mark, brand
// link), templates grid, and search bar — the v6 hero is the hero. What
// stays:
//   - <CommandPalette> mount
//   - Ctrl+K / Meta+K toggle handler
//   - <Link data-testid="header-sign-in-link"> (focus-restore target the
//     palette focuses on close; rendered as a small absolutely-positioned
//     top-right affordance so the marketing hero is uncluttered)
//
// AppShellGate marks `/` as chromeless, so this shell adds NO chrome —
// just the palette behavior + the sign-in escape hatch.
//
// Codex iter-4 P3 footnote: the 3 command_palette*.spec.ts files
// (command_palette.spec.ts, command_palette_adversarial.spec.ts,
// command_palette_suggest.spec.ts) verified passing unchanged once this
// shell wraps the home page — palette + sign-in-link selectors preserved.

import Link from "next/link";
import { useEffect, useRef, useState, type ReactNode } from "react";

import { CommandPalette } from "@/app/components/command_palette";

type Template = {
  id: string;
  name: string;
  summary: string;
  sample_question: string;
  out_of_scope: string;
  active: boolean;
};

interface HomePaletteShellProps {
  /** Template list passed to the CommandPalette (Ctrl+K search corpus).
   * Same shape as the legacy HomeKeyboardShell prop. */
  templates: Template[];
  /** Sign-in URL the focus-restore link points at. */
  signInHref: string;
  children: ReactNode;
}

export function HomePaletteShell({
  templates,
  signInHref,
  children,
}: HomePaletteShellProps) {
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
      {/* Minimal top-right sign-in affordance. The hero is the hero — this is
          a small, low-contrast escape hatch (and the testid target the
          command palette restores focus to on close). */}
      <div className="pointer-events-none absolute top-3 right-4 z-10 sm:top-5 sm:right-6">
        <Link
          ref={sign_in_link_ref}
          data-testid="header-sign-in-link"
          href={signInHref}
          className="text-muted-foreground hover:text-foreground focus-visible:ring-ring/70 pointer-events-auto inline-flex items-center rounded-full border border-transparent px-3 py-1 text-xs font-medium underline-offset-4 hover:underline focus-visible:ring-2 focus-visible:outline-none"
        >
          Sign in
        </Link>
      </div>

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
