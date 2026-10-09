import type { ReactNode } from "react";

export function AppShell({
  title,
  subtitle,
  children,
}: {
  title: string;
  subtitle?: string;
  children: ReactNode;
}) {
  return (
    <div className="relative min-h-screen text-foreground">
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0 -z-10 bg-[radial-gradient(ellipse_70%_40%_at_50%_-5%,rgba(255,107,74,0.1),transparent_50%),linear-gradient(180deg,#05060a_0%,#0b0d14_45%,#12151f_100%)]"
      />
      <div className="mx-auto max-w-7xl px-4 py-8 sm:px-6 sm:py-10">
        <div className="mb-8 flex flex-col items-start justify-between gap-2 border-b border-grid/70 pb-6 md:flex-row md:items-end">
          <div>
            <h1 className="font-display text-3xl font-bold leading-tight md:text-4xl">{title}</h1>
            {subtitle && <p className="mt-2 max-w-2xl text-sm text-muted-foreground">{subtitle}</p>}
          </div>
        </div>
        {children}
      </div>
    </div>
  );
}

export function Panel({
  title,
  action,
  children,
  className = "",
}: {
  title?: string;
  action?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <div className={`overflow-hidden rounded-2xl border border-grid bg-surface/40 ${className}`}>
      {title && (
        <div className="flex items-center justify-between border-b border-grid px-4 py-2.5">
          <span className="font-mono text-[10px] uppercase tracking-[0.22em] text-muted-foreground">
            {title}
          </span>
          {action}
        </div>
      )}
      <div className="p-4">{children}</div>
    </div>
  );
}

export function Stat({
  label,
  value,
  accent,
}: {
  label: string;
  value: string;
  accent?: "signal" | "warn";
}) {
  return (
    <div className="rounded-2xl border border-grid bg-surface/40 p-4">
      <div className="font-mono text-[10px] uppercase tracking-[0.22em] text-muted-foreground">
        {label}
      </div>
      <div
        className={`mt-2 font-display text-2xl font-bold tabular-nums ${
          accent === "signal" ? "text-signal" : accent === "warn" ? "text-warn" : ""
        }`}
      >
        {value}
      </div>
    </div>
  );
}
