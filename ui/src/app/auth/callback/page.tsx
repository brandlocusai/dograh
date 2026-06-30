"use client";

import { Loader2 } from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useRef, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

function CallbackContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [error, setError] = useState<string | null>(null);
  const verifyStarted = useRef(false);

  useEffect(() => {
    const token = searchParams.get("token");
    if (!token) {
      setError("No token found in the URL. Please request a new magic link.");
      return;
    }

    if (verifyStarted.current) return;
    verifyStarted.current = true;

    const verifyToken = async () => {
      try {
        const backendUrl = process.env.NEXT_PUBLIC_BACKEND_URL || "";
        const res = await fetch(`${backendUrl}/api/v1/auth/magic-link/verify`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({ token }),
        });

        const data = await res.json();

        if (!res.ok) {
          setError(data.detail || "Verification failed. The link may have expired.");
          return;
        }

        // Set session cookies on the Next.js server
        const sessionRes = await fetch("/api/auth/session", {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({ token: data.token, user: data.user }),
        });

        if (!sessionRes.ok) {
          setError("Failed to establish session. Please try again.");
          return;
        }

        toast.success("Signed in successfully!");
        router.push("/after-sign-in");
      } catch (err) {
        console.error("Verification error:", err);
        setError("An error occurred while verifying the link. Please try again.");
      }
    };

    verifyToken();
  }, [searchParams, router]);

  if (error) {
    return (
      <Card className="w-full max-w-md">
        <CardHeader className="text-center">
          <CardTitle className="text-2xl text-destructive">Sign-in Failed</CardTitle>
          <CardDescription>We couldn&apos;t verify your sign-in link</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4 text-center">
          <div className="rounded-lg border border-destructive/20 bg-destructive/10 p-4 text-sm text-destructive">
            {error}
          </div>
          <Button asChild className="w-full">
            <Link href="/auth/login">Return to Login</Link>
          </Button>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card className="w-full max-w-md">
      <CardContent className="flex flex-col items-center justify-center py-12 space-y-4">
        <Loader2 className="h-8 w-8 animate-spin text-primary" />
        <p className="text-sm font-medium text-muted-foreground">Verifying your sign-in link...</p>
      </CardContent>
    </Card>
  );
}

export default function CallbackPage() {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-background p-4">
      <div className="mb-6 text-center">
        <Link href="/" className="text-3xl font-extrabold tracking-tight hover:opacity-85 transition-opacity">
          VCalls Ai
        </Link>
      </div>
      <Suspense
        fallback={
          <Card className="w-full max-w-md">
            <CardContent className="flex flex-col items-center justify-center py-12 space-y-4">
              <Loader2 className="h-8 w-8 animate-spin text-primary" />
              <p className="text-sm font-medium text-muted-foreground">Loading...</p>
            </CardContent>
          </Card>
        }
      >
        <CallbackContent />
      </Suspense>
    </div>
  );
}
