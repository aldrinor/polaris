// I-cd-022 (#612): pathname-aware AppShell gate. On `/`, suppress BOTH
// the AppShell header AND its <main> wrapper so the home route can
// provide its own header (with the same primary nav) + its own <main>.
// This avoids G1 (double header) + G6 (nested main) landmark violations.
//
// Tiny "use client" boundary so the otherwise server-rendered AppShell
// can still wrap every non-home route on the server.
"use client";

import { usePathname } from "next/navigation";

import { AppShell } from "@/components/app_shell";

interface AppShellGateProps {
  children: React.ReactNode;
}

export function AppShellGate({ children }: AppShellGateProps) {
  const pathname = usePathname();
  // Home owns its own header + main; render children bare on `/`.
  if (pathname === "/") {
    return <>{children}</>;
  }
  return <AppShell>{children}</AppShell>;
}
