import Link from "next/link";

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

export default function SignInPage() {
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
          <CardHeader>
            <CardTitle>Sign in</CardTitle>
            <CardDescription>
              Authentication is a placeholder for Phase 0. Single sign-on wires
              up in Phase 2.
            </CardDescription>
          </CardHeader>
          <CardContent className="flex flex-col gap-4">
            <div className="flex flex-col gap-2">
              <label
                htmlFor="email"
                className="text-foreground text-sm font-medium"
              >
                Email
              </label>
              <Input
                id="email"
                type="email"
                placeholder="name@canada.ca"
                autoComplete="email"
                disabled
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
                type="password"
                placeholder="••••••••"
                autoComplete="current-password"
                disabled
              />
            </div>
          </CardContent>
          <CardFooter className="flex flex-col gap-3">
            <Button className="w-full" disabled>
              Continue
            </Button>
            <Button
              variant="ghost"
              className="w-full"
              nativeButton={false}
              render={<Link href="/" />}
            >
              Back to dashboard
            </Button>
          </CardFooter>
        </Card>

        <p className="text-muted-foreground text-center text-xs">
          POLARIS v6.2 — Phase 0 scaffold
        </p>
      </div>
    </div>
  );
}
