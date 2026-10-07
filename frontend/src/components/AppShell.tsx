import Link from "next/link";
import type { ReactNode } from "react";
import { Logo } from "@/components/Logo";

const NAV = [
  { to: "/agents", label: "Agents" },
  { to: "/analytics", label: "Analytics" },
];

export function AppShell({ title, subtitle, children }: { title: string; subtitle?: string; children: ReactNode }) {
  return (
    <div className="min-h-screen text-foreground">
      <div className="mx-auto max-w-7xl px-4 py-8 sm:px-6 sm:py-10">
        <div className="mb-8 flex flex-col items-start justify-between gap-2 border-b-2 border-grid pb-6 md:flex-row md:items-end">
          <div>
            <h1 className="font-display text-4xl leading-[0.98] tracking-tight md:text-5xl">{title}</h1>
            {subtitle && <p className="mt-3 max-w-xl text-sm font-medium text-muted-foreground">{subtitle}</p>}
          </div>
        </div>
        {children}
      </div>
    </div>
  );
}

export function Panel({ title, action, children, className = "" }: { title?: string; action?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <div className={`border-2 border-grid bg-surface/40 ${className}`}>
      {title && (
        <div className="flex items-center justify-between border-b-2 border-grid px-4 py-2.5">
          <span className="font-mono text-[10px] uppercase tracking-[0.22em] text-muted-foreground">{title}</span>
          {action}
        </div>
      )}
      <div className="p-4">{children}</div>
    </div>
  );
}

export function Stat({ label, value, accent }: { label: string; value: string; accent?: "signal" | "warn" }) {
  return (
    <div className="border-2 border-grid bg-surface/40 p-4">
      <div className="font-mono text-[10px] uppercase tracking-[0.22em] text-muted-foreground">{label}</div>
      <div className={`mt-2 font-display text-2xl tabular-nums ${accent === "signal" ? "text-signal" : accent === "warn" ? "text-warn" : ""}`}>{value}</div>
    </div>
  );
}
