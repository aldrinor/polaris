// I-p2-038 (#821): auth-aware Sign in / Sign out for the AppShell header.
// Before this, AppShell (every non-home route) had NO auth affordance at all —
// an unauthenticated reviewer who navigated off the home page had no way to
// sign in, and a signed-in reviewer had no way to sign out anywhere.
//
// Auth state lives in sessionStorage (not React state), so we read it via
// useSyncExternalStore: SSR-safe (getServerSnapshot returns the unauthenticated
// "Sign in" view, matching the first client paint → no hydration mismatch) and
// without a setState-in-effect (which the react-hooks/set-state-in-effect lint
// rule forbids — see #805).
"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useSyncExternalStore } from "react";

import { Button } from "@/components/ui/button";
import { clearToken, isAuthenticated } from "@/lib/auth";

// Cross-tab auth changes fire a `storage` event; same-tab sign-in/out re-mounts
// the shell on navigation, so the snapshot is re-read either way.
function subscribe(onChange: () => void): () => void {
  if (typeof window === "undefined") return () => {};
  window.addEventListener("storage", onChange);
  return () => window.removeEventListener("storage", onChange);
}

export function AuthButton() {
  const router = useRouter();
  const authed = useSyncExternalStore(
    subscribe,
    () => isAuthenticated(), // client: real auth state (boolean — stable by value)
    () => false, // server / first hydration paint: always "Sign in"
  );

  if (authed) {
    return (
      <Button
        variant="ghost"
        data-testid="appshell-sign-out"
        onClick={() => {
          clearToken();
          router.push("/");
        }}
      >
        Sign out
      </Button>
    );
  }

  return (
    <Button
      variant="outline"
      nativeButton={false}
      render={
        <Link href="/sign-in" data-testid="appshell-sign-in-link">
          Sign in
        </Link>
      }
    />
  );
}
