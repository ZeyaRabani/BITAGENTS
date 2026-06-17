import { DEFAULT_TASK_PRICE_SOL, type SolanaNetwork } from "@bitagents/shared";

export interface PublicConfig {
  treasuryWallet: string;
  treasuryConfigured: boolean;
  defaultNetwork: SolanaNetwork;
  taskFeeSol: number;
  devnetRpc: string;
  mainnetRpc: string;
}

export const FALLBACK_CONFIG: PublicConfig = {
  treasuryWallet: "",
  treasuryConfigured: false,
  defaultNetwork: "devnet",
  taskFeeSol: DEFAULT_TASK_PRICE_SOL,
  devnetRpc: "https://api.devnet.solana.com",
  mainnetRpc: "https://api.mainnet-beta.solana.com"
};

export function rpcUrlFor(config: PublicConfig, network: SolanaNetwork): string {
  return network === "mainnet" ? config.mainnetRpc : config.devnetRpc;
}
