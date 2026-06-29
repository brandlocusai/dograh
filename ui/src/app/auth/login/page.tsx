"use client";

import Link from "next/link";
import Script from "next/script";
import { useEffect, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

export default function LoginPage() {
  const [email, setEmail] = useState("");
  const [loading, setLoading] = useState(false);
  const [sent, setSent] = useState(false);

  const handleMagicLinkSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setSent(false);

    try {
      const backendUrl = process.env.NEXT_PUBLIC_BACKEND_URL || "http://localhost:8000";
      const res = await fetch(`${backendUrl}/api/v1/auth/magic-link`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email }),
      });

      if (!res.ok) {
        const data = await res.json();
        toast.error(data.detail || "Failed to send magic link");
        return;
      }

      setSent(true);
      toast.success("Magic link sent! Check your email.");
    } catch {
      toast.error("An error occurred. Please try again.");
    } finally {
      setLoading(false);
    }
  };

  const handleGoogleLogin = async (response: any) => {
    setLoading(true);
    try {
      const backendUrl = process.env.NEXT_PUBLIC_BACKEND_URL || "http://localhost:8000";
      const res = await fetch(`${backendUrl}/api/v1/auth/google`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ id_token: response.credential }),
      });

      const data = await res.json();
      if (!res.ok) {
        toast.error(data.detail || "Google login failed");
        return;
      }

      // Set httpOnly cookies via server route
      await fetch("/api/auth/session", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ token: data.token, user: data.user }),
      });

      window.location.href = "/after-sign-in";
    } catch {
      toast.error("Google login failed. Please try again.");
    } finally {
      setLoading(false);
    }
  };

  const initializeGoogle = () => {
    const googleClientId = process.env.NEXT_PUBLIC_GOOGLE_CLIENT_ID;
    if (!googleClientId) {
      console.warn("NEXT_PUBLIC_GOOGLE_CLIENT_ID is not configured");
      return;
    }

    if (typeof window !== "undefined" && (window as any).google) {
      try {
        (window as any).google.accounts.id.initialize({
          client_id: googleClientId,
          callback: handleGoogleLogin,
        });
        (window as any).google.accounts.id.renderButton(
          document.getElementById("google-signin-button"),
          { theme: "outline", size: "large", width: 380 }
        );
      } catch (err) {
        console.error("Failed to initialize Google Sign-In:", err);
      }
    }
  };

  useEffect(() => {
    initializeGoogle();
  }, []);

  return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-background p-4">
      <Script
        src="https://accounts.google.com/gsi/client"
        onLoad={initializeGoogle}
        strategy="lazyOnload"
      />
      <div className="mb-6 text-center">
        <Link href="/" className="text-3xl font-extrabold tracking-tight hover:opacity-85 transition-opacity">
          VCalls Ai
        </Link>
      </div>
      <Card className="w-full max-w-md">
        <CardHeader className="text-center">
          <CardTitle className="text-2xl">Sign in</CardTitle>
          <CardDescription>Sign in to your account without a password</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="space-y-4">
            {!process.env.NEXT_PUBLIC_GOOGLE_CLIENT_ID ? (
              <Button variant="outline" className="w-full opacity-70 cursor-not-allowed" disabled>
                <svg className="mr-2 h-4 w-4" viewBox="0 0 24 24">
                  <path
                    d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"
                    fill="#4285F4"
                  />
                  <path
                    d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"
                    fill="#34A853"
                  />
                  <path
                    d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.06H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.94l2.85-2.22.81-.63z"
                    fill="#FBBC05"
                  />
                  <path
                    d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.06l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"
                    fill="#EA4335"
                  />
                </svg>
                Sign in with Google (Set client ID in .env)
              </Button>
            ) : (
              <div className="flex justify-center w-full">
                <div id="google-signin-button" className="w-full flex justify-center" />
              </div>
            )}

            <div className="relative my-4">
              <div className="absolute inset-0 flex items-center">
                <span className="w-full border-t" />
              </div>
              <div className="relative flex justify-center text-xs uppercase">
                <span className="bg-background px-2 text-muted-foreground">Or continue with email</span>
              </div>
            </div>

            {sent ? (
              <div className="rounded-lg border border-emerald-200 bg-emerald-50 p-4 text-center text-sm text-emerald-800 dark:border-emerald-900/30 dark:bg-emerald-950/20 dark:text-emerald-400">
                <p className="font-semibold">Check your inbox!</p>
                <p className="mt-1">We sent a secure sign-in link to <strong>{email}</strong>.</p>
                <Button
                  variant="link"
                  className="mt-2 text-xs text-emerald-700 hover:text-emerald-800 dark:text-emerald-500"
                  onClick={() => setSent(false)}
                >
                  Resend email
                </Button>
              </div>
            ) : (
              <form onSubmit={handleMagicLinkSubmit} className="space-y-4">
                <div className="space-y-2">
                  <Label htmlFor="email">Email</Label>
                  <Input
                    id="email"
                    type="email"
                    placeholder="you@example.com"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    required
                    disabled={loading}
                  />
                </div>
                <Button type="submit" className="w-full" disabled={loading}>
                  {loading ? "Sending link..." : "Send Magic Link"}
                </Button>
              </form>
            )}
          </div>
          <p className="mt-6 text-center text-sm text-muted-foreground">
            Don&apos;t have an account?{" "}
            <Link href="/auth/signup" className="text-primary underline-offset-4 hover:underline">
              Sign up
            </Link>
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
