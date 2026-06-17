"use client";

import dynamic from "next/dynamic";

export const WalletButton = dynamic(
  async () => (await import("@solana/wallet-adapter-react-ui")).WalletMultiButton,
  {
    ssr: false,
    loading: () => (
      <span className="pixel-corners inline-flex h-9 items-center border border-border bg-surface-2 px-4 font-mono text-xs uppercase tracking-[0.08em] text-muted-foreground">
        Wallet
      </span>
    )
  }
);
