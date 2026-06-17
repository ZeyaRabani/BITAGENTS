"use client";

import { useNetwork } from "@/components/NetworkProvider";
import { cn } from "@/lib/utils";

export function NetworkToggle({ className }: { className?: string }) {
  const { network, setNetwork, mainnetDcaEnabled } = useNetwork();

  return (
    <div
      className={cn(
        "pixel-corners inline-flex border border-border bg-surface-2 p-0.5 font-mono text-[11px] uppercase tracking-[0.08em]",
        className
      )}
    >
      <button
        type="button"
        onClick={() => setNetwork("devnet")}
        className={cn(
          "px-2.5 py-1 transition",
          network === "devnet" ? "bg-signal text-primary-foreground" : "text-muted-foreground hover:text-foreground"
        )}
      >
        Devnet Demo
      </button>
      <button
        type="button"
        disabled={!mainnetDcaEnabled}
        title={mainnetDcaEnabled ? undefined : "Mainnet Safe Mode is disabled on this deployment (ENABLE_MAINNET_DCA=false)."}
        onClick={() => mainnetDcaEnabled && setNetwork("mainnet")}
        className={cn(
          "px-2.5 py-1 transition",
          network === "mainnet" ? "bg-foreground text-background" : "text-muted-foreground hover:text-foreground",
          !mainnetDcaEnabled && "cursor-not-allowed opacity-40 hover:text-muted-foreground"
        )}
      >
        Mainnet Safe
      </button>
    </div>
  );
}
