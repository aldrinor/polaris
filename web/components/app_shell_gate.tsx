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

// Chromeless routes own their full viewport (no app header/nav):
//  - `/`        : home owns its own header + main.
//  - `/sign-in` : institutional full-screen auth (I-p2-021 #760); the primary
//                 nav is auth-gated anyway, so it must not show pre-login.
const CHROMELESS_ROUTES = new Set(["/", "/sign-in"]);

export function AppShellGate({ children }: AppShellGateProps) {
  const pathname = usePathname();
  if (CHROMELESS_ROUTES.has(pathname)) {
    return <>{children}</>;
  }
  return <AppShell>{children}</AppShell>;
}
