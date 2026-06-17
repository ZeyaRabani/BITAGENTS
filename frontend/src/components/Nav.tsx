"use client";

import { ArrowUpRight, Menu, X } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";
import { Logo } from "@/components/Logo";
import { NetworkToggle } from "@/components/NetworkToggle";
import { WalletButton } from "@/components/WalletButton";
import { cn } from "@/lib/utils";

const LINKS = [
  { href: "/agents", label: "Agents" },
  { href: "/compute", label: "Compute" },
  { href: "/tasks", label: "Tasks" },
  { href: "/utility", label: "Utility" }
];

export function Nav({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);

  return (
    <div className="flex min-h-screen flex-col">
      <header className="sticky top-0 z-40 border-b border-border bg-background/85 backdrop-blur">
        <div className="mx-auto flex max-w-6xl items-center justify-between gap-4 px-4 py-3 sm:px-6">
          <Link href="/" className="flex items-center gap-2.5">
            <Logo className="h-8 w-auto" />
            <span className="font-display text-base font-bold uppercase tracking-[0.18em] text-foreground">
              BIT<span className="text-signal">AGENTS</span>
            </span>
          </Link>

          <nav className="hidden items-center gap-7 md:flex">
            {LINKS.map(({ href, label }) => {
              const active = pathname === href || pathname.startsWith(`${href}/`);
              return (
                <Link
                  key={href}
                  href={href}
                  className={cn(
                    "font-mono text-xs uppercase tracking-[0.14em] transition",
                    active ? "text-signal" : "text-muted-foreground hover:text-foreground"
                  )}
                >
                  {label}
                </Link>
              );
            })}
          </nav>

          <div className="flex items-center gap-2">
            <NetworkToggle className="hidden sm:inline-flex" />
            <div className="hidden sm:block">
              <WalletButton />
            </div>
            <Link
              href="/app"
              className="pixel-corners hidden items-center gap-1.5 bg-signal px-3.5 py-2 font-mono text-xs font-semibold uppercase tracking-[0.08em] text-primary-foreground transition hover:bg-signal-soft sm:inline-flex"
            >
              Launch App <ArrowUpRight size={14} />
            </Link>
            <button
              type="button"
              onClick={() => setOpen((value) => !value)}
              className="pixel-corners inline-flex h-9 w-9 items-center justify-center border border-border bg-surface-2 text-foreground md:hidden"
              aria-label="Toggle menu"
            >
              {open ? <X size={16} /> : <Menu size={16} />}
            </button>
          </div>
        </div>

        {open ? (
          <div className="border-t border-border bg-surface md:hidden">
            <div className="mx-auto flex max-w-6xl flex-col gap-1 px-4 py-3">
              {LINKS.map(({ href, label }) => (
                <Link
                  key={href}
                  href={href}
                  onClick={() => setOpen(false)}
                  className="px-2 py-2 font-mono text-sm uppercase tracking-[0.12em] text-muted-foreground hover:text-foreground"
                >
                  {label}
                </Link>
              ))}
              <div className="flex flex-wrap items-center gap-2 px-2 pt-2">
                <NetworkToggle />
                <WalletButton />
              </div>
              <Link
                href="/app"
                onClick={() => setOpen(false)}
                className="pixel-corners mt-2 inline-flex items-center justify-center gap-1.5 bg-signal px-3.5 py-2.5 font-mono text-xs font-semibold uppercase tracking-[0.08em] text-primary-foreground"
              >
                Launch App <ArrowUpRight size={14} />
              </Link>
            </div>
          </div>
        ) : null}
      </header>

      <div className="flex-1">{children}</div>

      <SiteFooter />
    </div>
  );
}

function SiteFooter() {
  return (
    <footer className="border-t border-border bg-surface/60">
      <div className="mx-auto flex max-w-6xl flex-col gap-4 px-4 py-8 sm:flex-row sm:items-center sm:justify-between sm:px-6">
        <div className="flex items-center gap-2.5">
          <Logo className="h-7 w-auto" />
          <span className="font-display text-sm font-bold uppercase tracking-[0.18em] text-foreground">
            BIT<span className="text-signal">AGENTS</span>
          </span>
        </div>
        <p className="max-w-md font-mono text-[11px] leading-relaxed text-muted-foreground">
          Run crypto AI agents without setup. Devnet demo for payments; mainnet used read-only. Research and educational
          tools only — not financial advice.
        </p>
        <div className="flex flex-wrap gap-4 font-mono text-[11px] uppercase tracking-[0.12em] text-muted-foreground">
          <Link href="/agents" className="hover:text-foreground">
            Agents
          </Link>
          <Link href="/compute" className="hover:text-foreground">
            Compute
          </Link>
          <Link href="/utility" className="hover:text-foreground">
            Utility
          </Link>
        </div>
      </div>
    </footer>
  );
}
