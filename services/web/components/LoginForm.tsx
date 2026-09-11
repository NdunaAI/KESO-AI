"use client";

import { useState } from "react";
import Image from "next/image";
import { login, type UserProfile } from "@/lib/api";
import { LockIcon, MailIcon } from "@/components/icons";

export function LoginForm({ onSuccess }: { onSuccess: (profile: UserProfile) => void }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!email.trim() || !password || isSubmitting) return;
    setError(null);
    setIsSubmitting(true);
    try {
      const profile = await login(email.trim(), password);
      onSuccess(profile);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong. Please try again.");
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <div className="flex h-screen items-center justify-center bg-keso-page px-4">
      <div className="w-full max-w-[380px] rounded-2xl border border-keso-border bg-white p-8 shadow-[0_1px_3px_rgba(42,42,56,0.06)]">
        <div className="mb-8 flex flex-col items-center gap-4">
          <Image src="/kuhle-logo.png" alt="Kuhle Solutions and Development Services" width={140} height={48} priority />
          <div className="flex items-baseline gap-2">
            <span className="text-[19px] font-bold tracking-tight text-keso-ink">KESO Assistant</span>
            <span className="text-[19px] leading-none">🤖</span>
          </div>
        </div>

        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
          <label className="flex flex-col gap-1.5">
            <span className="text-[12.5px] font-semibold text-keso-ink-muted">Email</span>
            <div className="flex items-center gap-2 rounded-[10px] border border-keso-border bg-keso-surface px-3 py-2.5 focus-within:border-keso-indigo">
              <MailIcon className="shrink-0 text-keso-ink-faint" />
              <input
                type="email"
                autoComplete="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="you@keso.org"
                className="w-full bg-transparent text-sm text-keso-ink placeholder:text-keso-ink-faint focus:outline-none"
              />
            </div>
          </label>

          <label className="flex flex-col gap-1.5">
            <span className="text-[12.5px] font-semibold text-keso-ink-muted">Password</span>
            <div className="flex items-center gap-2 rounded-[10px] border border-keso-border bg-keso-surface px-3 py-2.5 focus-within:border-keso-indigo">
              <LockIcon className="shrink-0 text-keso-ink-faint" />
              <input
                type="password"
                autoComplete="current-password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••••"
                className="w-full bg-transparent text-sm text-keso-ink placeholder:text-keso-ink-faint focus:outline-none"
              />
            </div>
          </label>

          {error && (
            <div className="rounded-lg border border-keso-orange/30 bg-keso-orange-tint px-3 py-2 text-[12.5px] text-keso-orange-dark">
              {error}
            </div>
          )}

          <button
            type="submit"
            disabled={isSubmitting || !email.trim() || !password}
            className="mt-1 flex items-center justify-center rounded-chip bg-keso-orange px-4 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-keso-orange-dark disabled:cursor-not-allowed disabled:opacity-50"
          >
            {isSubmitting ? "Signing in…" : "Sign in"}
          </button>
        </form>

        <p className="mt-6 text-center text-[11.5px] leading-relaxed text-keso-ink-faint">
          Accounts are provisioned by your KESO administrator. Contact them if you don&apos;t have credentials.
        </p>
      </div>
    </div>
  );
}
