"use client";

import type { ReactNode } from "react";
import { useWallet } from "@solana/wallet-adapter-react";
import type { BuildStatus } from "@/lib/builderClient";

export const LABEL = "font-mono text-[10px] uppercase tracking-[0.22em] text-muted-foreground";
export const BTN_PRIMARY =
  "bg-signal px-5 py-3 font-mono text-xs font-semibold uppercase tracking-[0.14em] text-primary-foreground transition hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-40";
export const BTN_GHOST =
  "border border-grid px-2.5 py-1.5 font-mono text-[10px] uppercase tracking-[0.12em] text-muted-foreground transition hover:border-signal hover:text-foreground disabled:cursor-not-allowed disabled:opacity-40";
/** Ghost button for literal text (file names, example briefs): no uppercase transform. */
export const BTN_GHOST_PLAIN =
  "border border-grid px-2.5 py-1.5 font-mono text-[10px] tracking-[0.06em] text-muted-foreground transition hover:border-signal hover:text-foreground disabled:cursor-not-allowed disabled:opacity-40";
export const INPUT =
  "border border-grid bg-background px-4 py-3 font-mono text-sm text-foreground outline-none transition placeholder:text-muted-foreground focus:border-signal disabled:opacity-50";
export const CODE_BOX =
  "overflow-auto border border-grid bg-background p-3 font-mono text-[11px] leading-relaxed text-muted-foreground whitespace-pre";

export function Notice({ tone = "info", children }: { tone?: "info" | "warn"; children: ReactNode }) {
  return (
    <div
      className={`whitespace-pre-wrap break-words px-4 py-3 font-mono text-xs ${
        tone === "warn"
          ? "border border-warn/40 bg-warn/10 text-warn"
          : "border border-grid bg-surface/40 text-muted-foreground"
      }`}
    >
      {children}
    </div>
  );
}

export function StatusBadge({ status }: { status: BuildStatus | string }) {
  const tone =
    status === "ready"
      ? "border-signal/50 text-signal"
      : status === "failed"
        ? "border-warn/50 text-warn"
        : "border-grid text-muted-foreground";
  return (
    <span
      className={`inline-flex items-center gap-1.5 border px-2 py-0.5 font-mono text-[10px] font-semibold uppercase tracking-[0.14em] ${tone}`}
    >
      {status === "building" && <span className="h-1.5 w-1.5 animate-pulse-dot bg-signal" />}
      {status}
    </span>
  );
}

export function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="min-w-0">
      <div className="font-mono text-[9px] uppercase tracking-[0.16em] text-muted-foreground">{label}</div>
      <div className="mt-1 break-words font-mono text-xs text-foreground">{children}</div>
    </div>
  );
}

/** Same notices the other agent consoles show around wallet connect + sign-in. */
export function WalletGate({
  authBusy,
  authError,
  isAuthenticated,
  purpose,
}: {
  authBusy: boolean;
  authError: string | null;
  isAuthenticated: boolean;
  purpose: string;
}) {
  const { publicKey } = useWallet();
  if (isAuthenticated) return null;
  return (
    <div className="space-y-3">
      {authError && <Notice tone="warn">Wallet sign-in: {authError}</Notice>}
      {!publicKey && <Notice>Connect your wallet above to {purpose}.</Notice>}
      {publicKey && authBusy && <Notice>Approve the wallet sign-in message to authenticate.</Notice>}
      {publicKey && !authBusy && !authError && (
        <Notice>Approve the wallet sign-in prompt to {purpose}.</Notice>
      )}
    </div>
  );
}
