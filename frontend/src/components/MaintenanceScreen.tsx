"use client";

import { useEffect, useState } from "react";
import { Logo } from "@/components/Logo";
import {
  MAINTENANCE_LABEL_IST,
  isMaintenanceWindow,
  maintenanceEndsAt,
  msUntilMaintenanceEnd,
} from "@/lib/maintenanceWindow";

function formatRemaining(ms: number): string {
  const totalSec = Math.max(0, Math.ceil(ms / 1000));
  const m = Math.floor(totalSec / 60);
  const s = totalSec % 60;
  return `${m}:${s.toString().padStart(2, "0")}`;
}

export function MaintenanceScreen() {
  const [remainingMs, setRemainingMs] = useState(() => msUntilMaintenanceEnd());
  const [active, setActive] = useState(() => isMaintenanceWindow());

  useEffect(() => {
    const tick = () => {
      const on = isMaintenanceWindow();
      setActive(on);
      setRemainingMs(msUntilMaintenanceEnd());
      if (!on) {
        window.location.href = "/";
      }
    };
    tick();
    const id = window.setInterval(tick, 1000);
    return () => window.clearInterval(id);
  }, []);

  const endsLocal = maintenanceEndsAt().toLocaleTimeString(undefined, {
    hour: "numeric",
    minute: "2-digit",
    timeZoneName: "short",
  });

  return (
    <div className="relative flex min-h-[calc(100vh-4rem)] flex-col items-center justify-center overflow-hidden px-4 py-16">
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0 opacity-[0.35]"
        style={{
          backgroundImage:
            "linear-gradient(to right, var(--grid) 1px, transparent 1px), linear-gradient(to bottom, var(--grid) 1px, transparent 1px)",
          backgroundSize: "48px 48px",
          maskImage: "radial-gradient(ellipse 70% 60% at 50% 40%, black 20%, transparent 75%)",
        }}
      />
      <div
        aria-hidden
        className="pointer-events-none absolute -top-24 left-1/2 h-72 w-[36rem] -translate-x-1/2 rounded-full bg-signal/15 blur-3xl"
      />

      <div className="relative z-10 mx-auto flex w-full max-w-xl flex-col items-center text-center">
        <Logo className="h-14 w-auto sm:h-16" />

        <p className="mt-10 font-mono text-[10px] uppercase tracking-[0.28em] text-signal">
          Scheduled maintenance
        </p>

        <h1 className="mt-4 font-display text-3xl font-bold tracking-tight text-foreground sm:text-4xl">
          BIT Agents is briefly offline
        </h1>

        <p className="mt-4 max-w-md text-sm leading-relaxed text-muted-foreground sm:text-base">
          We&apos;re running a short ledger migration so deposits, DCA, EasyA, and Hedge Fund
          stay consistent. Agents are paused until about 2:30 PM IST — we&apos;ll be back soon.
        </p>

        <div className="mt-10 w-full border border-grid bg-surface/60 px-6 py-5 backdrop-blur">
          <div className="font-mono text-[10px] uppercase tracking-[0.2em] text-muted-foreground">
            Window
          </div>
          <div className="mt-2 font-display text-lg font-semibold text-foreground">
            {MAINTENANCE_LABEL_IST}
          </div>
          <div className="mt-1 font-mono text-xs text-muted-foreground">
            Expected back around {endsLocal}
          </div>

          {active ? (
            <div className="mt-6 border-t border-grid pt-5">
              <div className="font-mono text-[10px] uppercase tracking-[0.2em] text-signal">
                Time remaining
              </div>
              <div className="mt-2 font-display text-4xl font-bold tabular-nums tracking-tight text-foreground">
                {formatRemaining(remainingMs)}
              </div>
            </div>
          ) : null}
        </div>

        <p className="mt-8 font-mono text-[10px] uppercase tracking-[0.16em] text-muted-foreground">
          No action needed · Your balances are safe
        </p>
      </div>
    </div>
  );
}
