import type { SolanaNetwork } from "@bitagents/shared";

const DEFAULT_DEVNET_RPC = "https://api.devnet.solana.com";
// Solana's public mainnet-beta endpoint returns 403 ("Access forbidden") for
// browser-origin requests, which breaks client-side signing (fetching a
// blockhash, sending swaps). PublicNode is a free, keyless RPC that allows
// browser CORS + websockets, so it works from the dapp. Override with
// NEXT_PUBLIC_MAINNET_RPC to point at a dedicated provider in production.
const DEFAULT_MAINNET_RPC = "https://solana-rpc.publicnode.com";

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
