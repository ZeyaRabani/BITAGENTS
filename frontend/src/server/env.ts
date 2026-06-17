import type { SolanaNetwork } from "@bitagents/shared";

const DEFAULT_DEVNET_RPC = "https://api.devnet.solana.com";
const DEFAULT_MAINNET_RPC = "https://api.mainnet-beta.solana.com";

function clean(value: string | undefined): string | undefined {
  const trimmed = value?.trim();
  if (!trimmed || trimmed.includes("REPLACE")) {
    return undefined;
  }
  return trimmed;
}

export function devnetRpcUrl(): string {
  return clean(process.env.NEXT_PUBLIC_DEVNET_RPC) ?? clean(process.env.SOLANA_RPC_URL) ?? DEFAULT_DEVNET_RPC;
}

export function mainnetRpcUrl(): string {
  return clean(process.env.NEXT_PUBLIC_MAINNET_RPC) ?? DEFAULT_MAINNET_RPC;
}

export function rpcUrlForNetwork(network: SolanaNetwork): string {
  return network === "mainnet" ? mainnetRpcUrl() : devnetRpcUrl();
}

export function treasuryWalletAddress(): string | undefined {
  return (
    clean(process.env.TREASURY_WALLET) ??
    clean(process.env.NEXT_PUBLIC_TREASURY_WALLET) ??
    clean(process.env.NEXT_PUBLIC_TREASURY_PUBLIC_KEY)
  );
}
