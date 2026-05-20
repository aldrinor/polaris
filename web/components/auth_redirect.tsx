// I-cd-014 (GH#610) — `<AuthRedirect>` UX-only client component.
//
// SECURITY FRAMING (binding):
// This component is a UX convenience that redirects unauthenticated
// browsers to /sign-in?next=<current-path>. It is **NOT** an authorization
// boundary. The JWT lives in client-side sessionStorage which is fully
// controllable by the browser; any user can spoof a value.
//
// Real authorization lives at the API layer via FastAPI's `require_auth`
// dependency (`src/polaris_v6/api/auth.py`). Server components MUST NOT
// load protected data from local fs/db on the page render path; they MUST
// fetch from the FastAPI backend with `Authorization: Bearer <jwt>`
// headers (real-data wiring at I-B-08).
//
// Used by route pages to redirect to /sign-in when a JWT is missing. Do
// not rely on this for security-sensitive data exposure.
"use client";

import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";

import { isAuthenticated } from "@/lib/auth";

interface AuthRedirectProps {
  children: ReactNode;
}

export function AuthRedirect({ children }: AuthRedirectProps) {
  const router = useRouter();
  const pathname = usePathname();
  // Synchronous initial check via lazy `useState` initializer. On the
  // very first render in the browser this resolves true|false from
  // sessionStorage immediately — no flash of protected content
  // (Codex diff iter-1 P2 #1). SSR returns `null` (window undefined)
  // so the first SSR pass renders no children; the client takes over.
  const [authState] = useState<"authed" | "redirect" | "ssr">(() => {
    if (typeof window === "undefined") return "ssr";
    return isAuthenticated() ? "authed" : "redirect";
  });

  useEffect(() => {
    if (authState !== "redirect") return;
    const next = encodeURIComponent(pathname ?? "/");
    router.replace(`/sign-in?next=${next}`);
  }, [authState, pathname, router]);

  // SSR / not-yet-checked / about-to-redirect: render nothing rather
  // than flash protected UI.
  if (authState !== "authed") return null;
  return <>{children}</>;
}
