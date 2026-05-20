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
import { useEffect, useRef, type ReactNode } from "react";

import { isAuthenticated } from "@/lib/auth";

interface AuthRedirectProps {
  children: ReactNode;
}

export function AuthRedirect({ children }: AuthRedirectProps) {
  const router = useRouter();
  const pathname = usePathname();
  // Hydration-safe: SSR returns true (children render); the effect below
  // performs the client-only auth check + redirect when needed.
  const checked = useRef(false);

  useEffect(() => {
    if (checked.current) return;
    checked.current = true;
    if (isAuthenticated()) return;
    const next = encodeURIComponent(pathname ?? "/");
    router.replace(`/sign-in?next=${next}`);
  }, [pathname, router]);

  return <>{children}</>;
}
