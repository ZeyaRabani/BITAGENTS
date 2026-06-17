"use client";

import { ConnectionProvider, WalletProvider } from "@solana/wallet-adapter-react";
import { WalletModalProvider } from "@solana/wallet-adapter-react-ui";
import { PhantomWalletAdapter } from "@solana/wallet-adapter-phantom";
import { useMemo, type ComponentType, type ReactNode } from "react";
import { NetworkProvider } from "@/components/NetworkProvider";

type ConnectionProviderProps = { endpoint: string; children: ReactNode };
type WalletProviderProps = { wallets: PhantomWalletAdapter[]; autoConnect?: boolean; children: ReactNode };
type WalletModalProviderProps = { children: ReactNode };

const WalletConnectionProvider = ConnectionProvider as unknown as ComponentType<ConnectionProviderProps>;
const WalletRootProvider = WalletProvider as unknown as ComponentType<WalletProviderProps>;
const WalletModalRootProvider = WalletModalProvider as unknown as ComponentType<WalletModalProviderProps>;

// Payments and signed transactions always run on devnet for safety, so the
// wallet adapter connection points at the devnet RPC. The selected read
// network (Mainnet Read Mode / Devnet Demo Mode) only affects server-side
// data reads and is tracked separately by NetworkProvider.
export function SolanaProviders({ children }: { children: ReactNode }) {
  const endpoint =
    process.env.NEXT_PUBLIC_DEVNET_RPC?.trim() ||
    process.env.NEXT_PUBLIC_SOLANA_RPC_URL?.trim() ||
    "https://api.devnet.solana.com";
  const wallets = useMemo(() => [new PhantomWalletAdapter()], []);

  return (
    <WalletConnectionProvider endpoint={endpoint}>
      <WalletRootProvider wallets={wallets} autoConnect>
        <WalletModalRootProvider>
          <NetworkProvider>{children}</NetworkProvider>
        </WalletModalRootProvider>
      </WalletRootProvider>
    </WalletConnectionProvider>
  );
}
