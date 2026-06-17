"use client";

import { ConnectionProvider, WalletProvider } from "@solana/wallet-adapter-react";
import { WalletModalProvider } from "@solana/wallet-adapter-react-ui";
import { PhantomWalletAdapter } from "@solana/wallet-adapter-phantom";
import { useMemo, type ComponentType, type ReactNode } from "react";
import { NetworkProvider, useNetwork } from "@/components/NetworkProvider";

type ConnectionProviderProps = { endpoint: string; children: ReactNode };
type WalletProviderProps = { wallets: PhantomWalletAdapter[]; autoConnect?: boolean; children: ReactNode };
type WalletModalProviderProps = { children: ReactNode };

const WalletConnectionProvider = ConnectionProvider as unknown as ComponentType<ConnectionProviderProps>;
const WalletRootProvider = WalletProvider as unknown as ComponentType<WalletProviderProps>;
const WalletModalRootProvider = WalletModalProvider as unknown as ComponentType<WalletModalProviderProps>;

// The wallet adapter connection follows the selected network so Mainnet Safe
// Mode can sign real Jupiter Recurring orders while Devnet Demo Mode stays on
// devnet. Remounting on endpoint change (via key) keeps the connection in sync.
function WalletLayer({ children }: { children: ReactNode }) {
  const { rpcUrl } = useNetwork();
  const wallets = useMemo(() => [new PhantomWalletAdapter()], []);

  return (
    <WalletConnectionProvider endpoint={rpcUrl} key={rpcUrl}>
      <WalletRootProvider wallets={wallets} autoConnect>
        <WalletModalRootProvider>{children}</WalletModalRootProvider>
      </WalletRootProvider>
    </WalletConnectionProvider>
  );
}

export function SolanaProviders({ children }: { children: ReactNode }) {
  return (
    <NetworkProvider>
      <WalletLayer>{children}</WalletLayer>
    </NetworkProvider>
  );
}
