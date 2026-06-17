import {
  AGENT_TYPES,
  isSolanaNetwork,
  type AgentInput,
  type AgentType,
  type ComputeType,
  type ProviderStatus,
  type SolanaNetwork
} from "@bitagents/shared";
import { PublicKey } from "@solana/web3.js";

export function requireString(value: unknown, field: string, maxLength = 180): string {
  if (typeof value !== "string" || value.trim().length === 0) {
    throw new Error(`${field} is required.`);
  }

  const trimmed = value.trim();
  if (trimmed.length > maxLength) {
    throw new Error(`${field} is too long.`);
  }

  return trimmed;
}

export function optionalString(value: unknown, field: string, maxLength = 180): string | undefined {
  if (value === undefined || value === null || (typeof value === "string" && value.trim().length === 0)) {
    return undefined;
  }
  return requireString(value, field, maxLength);
}

export function requirePublicKey(value: unknown, field: string): string {
  const address = requireString(value, field, 80);
  try {
    return new PublicKey(address).toBase58();
  } catch {
    throw new Error(`${field} must be a valid Solana public key.`);
  }
}

export function parseAgentType(value: unknown): AgentType {
  if (typeof value !== "string" || !AGENT_TYPES.includes(value as AgentType)) {
    throw new Error("agent type is invalid.");
  }

  return value as AgentType;
}

export function parseNetwork(value: unknown): SolanaNetwork {
  if (typeof value === "string" && isSolanaNetwork(value)) {
    return value;
  }
  return "devnet";
}

export function parseAgentInput(type: AgentType, raw: unknown): AgentInput {
  const input = (raw ?? {}) as Record<string, unknown>;

  if (type === "wallet_watcher") {
    return { walletAddress: requirePublicKey(input.walletAddress, "wallet address") };
  }

  // token_research and market_research both take a free-text query.
  return { query: requireString(input.query, "query", 120) };
}

export function parseComputeType(value: unknown): ComputeType {
  if (value === "CPU" || value === "GPU_SIMULATED" || value === "LLM") {
    return value;
  }

  throw new Error("compute type must be CPU, GPU_SIMULATED, or LLM.");
}

export function parseProviderStatus(value: unknown): ProviderStatus {
  if (value === "online" || value === "offline") {
    return value;
  }

  throw new Error("provider status must be online or offline.");
}

export function parsePriceSol(value: unknown): number {
  const price = Number(value);
  if (!Number.isFinite(price) || price < 0 || price > 5) {
    throw new Error("price per task must be between 0 and 5 SOL.");
  }
  return Number(price.toFixed(6));
}
