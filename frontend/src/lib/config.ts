import { DEFAULT_TASK_PRICE_SOL, type SolanaNetwork } from "@bitagents/shared";

export interface PublicConfig {
  treasuryWallet: string;
  treasuryConfigured: boolean;
  defaultNetwork: SolanaNetwork;
  taskFeeSol: number;
  devnetRpc: string;
  mainnetRpc: string;
  bitagentsMint: string;
  bitagentsSymbol: string;
  enableMainnetDca: boolean;
  enableAgentWalletMode: boolean;
}

export const FALLBACK_CONFIG: PublicConfig = {
  treasuryWallet: "",
  treasuryConfigured: false,
  defaultNetwork: "mainnet",
  taskFeeSol: DEFAULT_TASK_PRICE_SOL,
  devnetRpc: "https://api.devnet.solana.com",
  // Keyless, browser-CORS-friendly mainnet RPC (the public mainnet-beta endpoint
  // 403s browser requests). Overridable via NEXT_PUBLIC_MAINNET_RPC.
  mainnetRpc: "https://solana-rpc.publicnode.com",
  bitagentsMint: "iu3A7azWTm3zQSk81SUC1JctB4zPYnxLmcmqq71EASY",
  bitagentsSymbol: "BITAGENTS",
  enableMainnetDca: true,
  enableAgentWalletMode: false
};

export function rpcUrlFor(config: PublicConfig, network: SolanaNetwork): string {
  return network === "mainnet" ? config.mainnetRpc : config.devnetRpc;
}
