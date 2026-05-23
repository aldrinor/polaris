// I-p2-038 (#821): auth-aware Sign in / Sign out for the AppShell header.
// Before this, AppShell (every non-home route) had NO auth affordance at all —
// an unauthenticated reviewer who navigated off the home page had no way to
// sign in, and a signed-in reviewer had no way to sign out anywhere.
//
// Hydration-safe: the server render and the FIRST client render both show the
// unauthenticated "Sign in" link (the token lives in sessionStorage, which the
// server can't see). Only AFTER mount do we read the real auth state and, if
// signed in, swap to "Sign out". This avoids a server/client markup mismatch.
"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { clearToken, isAuthenticated } from "@/lib/auth";

export function AuthButton() {
  const router = useRouter();
  const [authed, setAuthed] = useState(false);

  useEffect(() => {
    setAuthed(isAuthenticated());
  }, []);

  if (authed) {
    return (
      <Button
        variant="ghost"
        data-testid="appshell-sign-out"
        onClick={() => {
          clearToken();
          setAuthed(false);
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
