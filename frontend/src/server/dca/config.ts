import type { SolanaNetwork } from "@bitagents/shared";

// Default BITAGENTS mint (real, routeable on Jupiter via Meteora DAMM v2).
// Kept configurable through NEXT_PUBLIC_BITAGENTS_MINT for other deployments.
const DEFAULT_BITAGENTS_MINT = "iu3A7azWTm3zQSk81SUC1JctB4zPYnxLmcmqq71EASY";
const DEFAULT_BITAGENTS_SYMBOL = "BITAGENTS";

function clean(value: string | undefined): string | undefined {
  const trimmed = value?.trim();
  if (!trimmed || trimmed.includes("REPLACE")) return undefined;
  return trimmed;
}

function bool(value: string | undefined, fallback = false): boolean {
  const trimmed = value?.trim().toLowerCase();
  if (trimmed === undefined || trimmed === "") return fallback;
  return trimmed === "true" || trimmed === "1" || trimmed === "yes" || trimmed === "on";
}

function num(value: string | undefined, fallback: number): number {
  const parsed = Number(clean(value));
  return Number.isFinite(parsed) ? parsed : fallback;
}

export interface AgentWalletCaps {
  maxTotalSol: number;
  maxOrders: number;
  minIntervalSeconds: number;
  encryptionKey?: string;
  allowedUsers: string[];
}

export interface DcaServerConfig {
  bitagentsMint: string;
  bitagentsSymbol: string;
  defaultNetwork: SolanaNetwork;
  enableMainnetDca: boolean;
  enableAgentWalletMode: boolean;
  jupiterBaseUrl: string;
  jupiterApiKey?: string;
  cronSecret?: string;
  agentWallet: AgentWalletCaps;
}

export function dcaConfig(): DcaServerConfig {
  const jupiterApiKey = clean(process.env.JUPITER_API_KEY);
  // Free "lite" host needs no key; the pro host requires x-api-key.
  const jupiterBaseUrl =
    clean(process.env.JUPITER_API_BASE) ?? (jupiterApiKey ? "https://api.jup.ag" : "https://lite-api.jup.ag");

  // Mainnet is the default network for this deployment. Set
  // NEXT_PUBLIC_DEFAULT_NETWORK=devnet to fall back to Devnet Demo Mode.
  const defaultNetwork: SolanaNetwork =
    clean(process.env.NEXT_PUBLIC_DEFAULT_NETWORK) === "devnet" ? "devnet" : "mainnet";

  return {
    bitagentsMint: clean(process.env.NEXT_PUBLIC_BITAGENTS_MINT) ?? DEFAULT_BITAGENTS_MINT,
    bitagentsSymbol: clean(process.env.NEXT_PUBLIC_BITAGENTS_SYMBOL) ?? DEFAULT_BITAGENTS_SYMBOL,
    defaultNetwork,
    enableMainnetDca: bool(process.env.NEXT_PUBLIC_ENABLE_MAINNET_DCA, true),
    enableAgentWalletMode:
      bool(process.env.ENABLE_AGENT_WALLET_MODE, false) ||
      bool(process.env.NEXT_PUBLIC_ENABLE_AGENT_WALLET_MODE, false),
    jupiterBaseUrl: jupiterBaseUrl.replace(/\/$/, ""),
    jupiterApiKey,
    cronSecret: clean(process.env.CRON_SECRET),
    agentWallet: {
      maxTotalSol: num(process.env.MAX_AGENT_WALLET_TOTAL_SOL, 0.05),
      maxOrders: num(process.env.MAX_AGENT_WALLET_ORDERS, 5),
      minIntervalSeconds: num(process.env.MIN_INTERVAL_SECONDS, 60),
      encryptionKey: clean(process.env.AGENT_WALLET_ENCRYPTION_KEY),
      allowedUsers: (clean(process.env.AGENT_WALLET_ALLOWED_USERS) ?? "")
        .split(",")
        .map((entry) => entry.trim())
        .filter(Boolean)
    }
  };
}

export function jupiterRecurringBase(config: DcaServerConfig): string {
  return `${config.jupiterBaseUrl}/recurring/v1`;
}

export function jupiterHeaders(config: DcaServerConfig): Record<string, string> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (config.jupiterApiKey) {
    headers["x-api-key"] = config.jupiterApiKey;
  }
  return headers;
}
