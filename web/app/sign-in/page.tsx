"use client";

import { Suspense, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";

import { login } from "@/lib/auth";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";

/**
 * I-cd-014 (GH#610): same-origin validation for `?next=` redirect.
 *
 * Rejects:
 *   - non-string / empty values
 *   - URL parse failures
 *   - URLs that, when parsed against `window.location.origin`, resolve to
 *     a different origin (protocol-relative `//evil.com`, absolute
 *     `http://...`, backslash-as-separator `/\evil.com` — all caught by
 *     the URL parser).
 *   - fragment-only / hash-only navigation (e.g. `#frag`) — these are
 *     same-origin but offer no real navigation, so we fall back to `/`.
 *
 * Returns the validated `pathname + search + hash` or `"/"`.
 */
function safeNextPath(next: string | null): string {
  if (!next) return "/";
  if (typeof window === "undefined") return "/";
  try {
    const parsed = new URL(next, window.location.origin);
    if (parsed.origin !== window.location.origin) return "/";
    // Reject fragment-only / hash-only / empty pathname — they leave the
    // user on the sign-in route with just a fragment appended.
    if (!parsed.pathname || parsed.pathname === "/sign-in") return "/";
    return parsed.pathname + parsed.search + parsed.hash;
  } catch {
    return "/";
  }
}

/**
 * I-cd-014 (GH#610): Next.js App Router requires `useSearchParams()` users
 * to be wrapped in a Suspense boundary (or the route opts into dynamic
 * rendering). Wrapping the form here is the lighter-weight choice and
 * matches the existing repo convention.
 */
export default function SignInPage() {
  return (
    <Suspense fallback={<SignInPageFallback />}>
      <SignInPageContent />
    </Suspense>
  );
}

function SignInPageFallback() {
  return (
    <div className="bg-muted/40 flex min-h-screen flex-col items-center justify-center px-6 py-12">
      <div
        className="text-muted-foreground text-sm"
        data-testid="sign-in-loading"
      >
        Loading sign-in…
      </div>
    </div>
  );
}

function SignInPageContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setPending(true);
    const result = await login(username.trim(), password);
    setPending(false);
    if (result.ok) {
      const next = safeNextPath(searchParams.get("next"));
      router.push(next);
      router.refresh();
    } else {
      setError(result.error ?? "Sign-in failed.");
    }
  }

  return (
    <div className="bg-muted/40 flex min-h-screen flex-col items-center justify-center px-6 py-12">
      <div className="flex w-full max-w-sm flex-col gap-6">
        <div className="flex flex-col gap-1 text-center">
          <span className="text-muted-foreground text-xs font-medium tracking-widest uppercase">
            POLARIS Canada
          </span>
          <span className="text-foreground text-base font-semibold">
            Sovereign Deep Research
          </span>
        </div>

        <Card>
          <form onSubmit={handleSubmit} data-testid="sign-in-form">
            <CardHeader>
              <CardTitle>Sign in</CardTitle>
              <CardDescription>
                Enter your POLARIS reviewer credentials.
              </CardDescription>
            </CardHeader>
            <CardContent className="flex flex-col gap-4">
              <div className="flex flex-col gap-2">
                <label
                  htmlFor="username"
                  className="text-foreground text-sm font-medium"
                >
                  Username
                </label>
                <Input
                  id="username"
                  name="username"
                  type="text"
                  placeholder="reviewer"
                  autoComplete="username"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  required
                />
              </div>
              <div className="flex flex-col gap-2">
                <label
                  htmlFor="password"
                  className="text-foreground text-sm font-medium"
                >
                  Password
                </label>
                <Input
                  id="password"
                  name="password"
                  type="password"
                  placeholder="••••••••"
                  autoComplete="current-password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                />
              </div>
              {error ? (
                <p
                  role="alert"
                  data-testid="sign-in-error"
                  className="text-destructive text-sm font-medium"
                >
                  {error}
                </p>
              ) : null}
            </CardContent>
            <CardFooter className="flex flex-col gap-3">
              <Button
                type="submit"
                data-testid="sign-in-submit"
                className="w-full"
                disabled={pending || !username || !password}
              >
                {pending ? "Signing in…" : "Continue"}
              </Button>
              <Button
                type="button"
                variant="ghost"
                className="w-full"
                nativeButton={false}
                render={<Link href="/" />}
              >
                Back to home
              </Button>
            </CardFooter>
          </form>
        </Card>
      </div>
    </div>
  );
}
