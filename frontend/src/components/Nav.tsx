"use client";

import { WalletMultiButton } from "@solana/wallet-adapter-react-ui";
import { ArrowUpRight } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";

const appLinks = [
  { href: "/launch", label: "Launchpad", match: (path: string) => path.startsWith("/launch") },
  { href: "/agents", label: "Marketplace", match: (path: string) => path.startsWith("/agents") },
];

const marketingLinks = [
  { href: "/agents", label: "Agents" },
  { href: "/#how", label: "How It Works" },
  { href: "https://gitbook.bitagents.app/", label: "Gitbook", external: true },
];

const navLinkBase =
  "px-3 py-1.5 text-xs font-mono uppercase tracking-[0.14em] transition border-2";

function appLinkClass(active: boolean) {
  return active
    ? `${navLinkBase} border-signal bg-surface/60 text-signal`
    : `${navLinkBase} border-transparent text-muted-foreground hover:border-grid hover:bg-surface/40 hover:text-foreground`;
}

export function Nav({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const isPublicPage = pathname === "/" || pathname === "/coming-soon";

  return (
    <div className="min-h-screen bg-background">
      <header
        className={`sticky top-0 z-30 bg-background/80 backdrop-blur ${isPublicPage ? "" : "border-b-2 border-grid"}`}
      >
        <div className="mx-auto flex max-w-7xl items-center justify-between gap-3 px-6 py-6 sm:gap-6 sm:px-8 sm:py-8">
          <Link href="/" className="min-w-0 shrink">
            <Wordmark compact />
          </Link>

          {isPublicPage ? (
            <>
              <nav className="hidden items-center gap-7 whitespace-nowrap text-lg font-mono uppercase tracking-[0.1em] text-muted-foreground md:flex">
                {marketingLinks.map(({ href, label, external }) =>
                  external ? (
                    <a key={href} href={href} target="_blank" rel="noreferrer" className="transition hover:text-foreground">
                      {label}
                    </a>
                  ) : (
                    <Link key={href} href={href} className="transition hover:text-foreground">
                      {label}
                    </Link>
                  )
                )}
              </nav>
              <Link
                href="/agents"
                className="inline-flex shrink-0 items-center justify-center gap-2 bg-signal px-4 py-2.5 text-lg font-mono font-semibold uppercase tracking-[0.08em] text-primary-foreground transition hover:opacity-90 sm:px-5 sm:text-xl"
              >
                Launch App <ArrowUpRight size={22} />
              </Link>
            </>
          ) : (
            <div className="flex shrink-0 items-center gap-2 sm:gap-3">
              <nav className="hidden items-center gap-2 md:flex">
                {appLinks.map(({ href, label, match }) => (
                  <Link key={href} href={href} className={appLinkClass(match(pathname))}>
                    {label}
                  </Link>
                ))}
              </nav>
              <WalletMultiButton className="wallet-adapter-button-trigger max-w-[min(100vw-10rem,220px)]!" />
            </div>
          )}
        </div>

        {!isPublicPage && (
          <div className="mx-auto flex max-w-7xl items-center gap-2 overflow-x-auto px-4 pb-3 md:hidden">
            {appLinks.map(({ href, label, match }) => (
              <Link key={href} href={href} className={`min-w-fit ${appLinkClass(match(pathname))}`}>
                {label}
              </Link>
            ))}
          </div>
        )}
      </header>
      <main>{children}</main>
    </div>
  );
}

export function Wordmark({ compact = false }: { compact?: boolean }) {
  const width = compact ? 200 : 390;

  return (
    <img
      src="/bit-agents-logo-transparent.png"
      alt="BIT Agents"
      width={width}
      height={Math.round(width * 0.8)}
      className={
        compact
          ? "block h-[7.875rem] w-auto object-contain object-left sm:h-[10.875rem] md:h-[15.75rem]"
          : "block h-auto max-w-full object-contain object-left"
      }
      style={compact ? undefined : { width: "min(390px, 100%)" }}
    />
  );
}
