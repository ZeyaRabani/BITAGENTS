"use client";

import Link from "next/link";
import { FormEvent, useState } from "react";

const INTEREST_OPTIONS = [
  {
    value: "make_agent",
    label: "I'm a trader who wants to make an Agent",
  },
  {
    value: "use_marketplace",
    label: "I'm a trader who wants to use an Agent from the Marketplace",
  },
  {
    value: "both",
    label: "Both",
  },
] as const;

type InterestValue = (typeof INTEREST_OPTIONS)[number]["value"];

export default function SignupPage() {
  const [email, setEmail] = useState("");
  const [telegram, setTelegram] = useState("");
  const [twitter, setTwitter] = useState("");
  const [interest, setInterest] = useState<InterestValue | "">("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [doneMessage, setDoneMessage] = useState<string | null>(null);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setDoneMessage(null);

    const emailTrimmed = email.trim();
    if (!emailTrimmed) {
      setError("Email is required.");
      return;
    }
    if (!interest) {
      setError("Please select how you want to use BIT Agents.");
      return;
    }

    setBusy(true);
    try {
      const res = await fetch("/api/signup", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          email: emailTrimmed,
          telegram: telegram.trim() || undefined,
          twitter: twitter.trim() || undefined,
          interest,
          notify_when_ready: true,
        }),
      });
      const data = (await res.json().catch(() => ({}))) as {
        error?: string;
        message?: string;
      };
      if (!res.ok) {
        throw new Error(data.error || `Signup failed (${res.status})`);
      }
      setDoneMessage(
        data.message ||
          "You're on the list. We'll notify you once all features are shipped."
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Signup failed.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="relative overflow-hidden border-b border-grid">
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_at_top,_rgba(245,239,230,0.06),_transparent_55%)]"
      />
      <div className="relative mx-auto grid max-w-7xl gap-12 px-6 py-14 lg:grid-cols-[1.05fr_0.95fr] lg:items-start">
        <div>
          <div className="font-mono text-[10px] uppercase tracking-[0.22em] text-signal">
            Early access
          </div>
          <h1 className="mt-4 font-display text-4xl font-bold leading-[0.95] tracking-tight md:text-5xl lg:text-6xl">
            Sign up for BIT Agents
          </h1>
          <p className="mt-6 max-w-xl text-base leading-relaxed text-muted-foreground md:text-lg">
            Tell us how you want to use the marketplace. Once the remaining
            features ship, we will notify you at the email you provide.
          </p>
          <p className="mt-8 font-mono text-[11px] uppercase tracking-[0.16em] text-muted-foreground">
            Already exploring?{" "}
            <Link href="/agents" className="text-signal underline-offset-4 hover:underline">
              Open the marketplace
            </Link>
          </p>
        </div>

        <div className="border border-grid bg-surface/50 p-6 md:p-8">
          {doneMessage ? (
            <div className="space-y-4">
              <div className="font-mono text-[10px] uppercase tracking-[0.18em] text-signal">
                You&apos;re in
              </div>
              <p className="text-base leading-relaxed text-foreground">{doneMessage}</p>
              <button
                type="button"
                onClick={() => {
                  setDoneMessage(null);
                  setEmail("");
                  setTelegram("");
                  setTwitter("");
                  setInterest("");
                }}
                className="border border-grid px-4 py-2 font-mono text-[11px] uppercase tracking-[0.14em] text-muted-foreground transition hover:border-signal hover:text-foreground"
              >
                Submit another
              </button>
            </div>
          ) : (
            <form onSubmit={onSubmit} className="space-y-5">
              <label className="grid gap-2">
                <span className="font-mono text-[10px] uppercase tracking-[0.16em] text-muted-foreground">
                  Email <span className="text-signal">*</span>
                </span>
                <input
                  type="email"
                  required
                  autoComplete="email"
                  value={email}
                  onChange={(event) => setEmail(event.target.value)}
                  disabled={busy}
                  placeholder="you@example.com"
                  className="border border-grid bg-background px-3 py-3 text-sm text-foreground outline-none transition placeholder:text-muted-foreground/60 focus:border-signal disabled:opacity-50"
                />
              </label>

              <label className="grid gap-2">
                <span className="font-mono text-[10px] uppercase tracking-[0.16em] text-muted-foreground">
                  Telegram <span className="text-muted-foreground/70">(optional)</span>
                </span>
                <input
                  type="text"
                  autoComplete="off"
                  value={telegram}
                  onChange={(event) => setTelegram(event.target.value)}
                  disabled={busy}
                  placeholder="@username"
                  className="border border-grid bg-background px-3 py-3 text-sm text-foreground outline-none transition placeholder:text-muted-foreground/60 focus:border-signal disabled:opacity-50"
                />
              </label>

              <label className="grid gap-2">
                <span className="font-mono text-[10px] uppercase tracking-[0.16em] text-muted-foreground">
                  Twitter / X <span className="text-muted-foreground/70">(optional)</span>
                </span>
                <input
                  type="text"
                  autoComplete="off"
                  value={twitter}
                  onChange={(event) => setTwitter(event.target.value)}
                  disabled={busy}
                  placeholder="@handle"
                  className="border border-grid bg-background px-3 py-3 text-sm text-foreground outline-none transition placeholder:text-muted-foreground/60 focus:border-signal disabled:opacity-50"
                />
              </label>

              <label className="grid gap-2">
                <span className="font-mono text-[10px] uppercase tracking-[0.16em] text-muted-foreground">
                  I am… <span className="text-signal">*</span>
                </span>
                <select
                  required
                  value={interest}
                  onChange={(event) => setInterest(event.target.value as InterestValue | "")}
                  disabled={busy}
                  className="border border-grid bg-background px-3 py-3 text-sm text-foreground outline-none transition focus:border-signal disabled:opacity-50"
                >
                  <option value="" disabled>
                    Select one
                  </option>
                  {INTEREST_OPTIONS.map((option) => (
                    <option key={option.value} value={option.value}>
                      {option.label}
                    </option>
                  ))}
                </select>
              </label>

              <p className="font-mono text-[11px] leading-relaxed text-muted-foreground">
                We will email you when the remaining features are ready. No spam.
              </p>

              {error ? (
                <div className="border border-warn/40 bg-warn/10 px-3 py-2 font-mono text-xs text-warn">
                  {error}
                </div>
              ) : null}

              <button
                type="submit"
                disabled={busy}
                className="inline-flex w-full items-center justify-center bg-signal px-5 py-3 font-mono text-sm font-semibold uppercase tracking-[0.14em] text-primary-foreground transition hover:opacity-90 disabled:opacity-50"
              >
                {busy ? "Saving…" : "Notify me"}
              </button>
            </form>
          )}
        </div>
      </div>
    </section>
  );
}
