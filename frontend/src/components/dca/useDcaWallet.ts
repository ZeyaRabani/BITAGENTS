"use client";

import { useWallet } from "@solana/wallet-adapter-react";
import { Keypair } from "@solana/web3.js";
import { useEffect, useState } from "react";

const DEMO_KEY = "bitagents.dca.demoWallet";

function loadDemoWallet(): string {
  const existing = window.localStorage.getItem(DEMO_KEY);
  if (existing) return existing;
  // A throwaway, valid base58 pubkey so Devnet Demo Mode can run end-to-end
  // without a browser wallet. No private key is kept — only the address, used
  // to group demo plans under "My Plans".
  const address = Keypair.generate().publicKey.toBase58();
  window.localStorage.setItem(DEMO_KEY, address);
  return address;
}

export interface DcaWallet {
  /** The wallet address used for plans: real wallet if connected, else a demo address. */
  address: string | null;
  connected: boolean;
  /** True when falling back to the generated demo address (no real wallet). */
  isDemo: boolean;
}

export function useDcaWallet(): DcaWallet {
  const { publicKey, connected } = useWallet();
  const [demo, setDemo] = useState<string | null>(null);

  useEffect(() => {
    if (!connected) setDemo(loadDemoWallet());
  }, [connected]);

  if (connected && publicKey) {
    return { address: publicKey.toBase58(), connected: true, isDemo: false };
  }
  return { address: demo, connected: false, isDemo: true };
}
