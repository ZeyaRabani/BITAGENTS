import type { SolanaNetwork } from "@bitagents/shared";
import { Keypair } from "@solana/web3.js";
import bs58 from "bs58";
import { createCipheriv, createDecipheriv, createHash, randomBytes } from "node:crypto";
import { dcaConfig, type AgentWalletCaps } from "./config";
import { getAgentWallet, saveAgentWallet, type StoredAgentWallet } from "./store";

// ---------------------------------------------------------------------
// EXPERIMENTAL Agent Wallet Mode — DISABLED by default.
//
// This is the only mode where the server holds a key that can move funds. It
// is gated behind ENABLE_AGENT_WALLET_MODE, an explicit user opt-in, hard caps,
// an admin allowlist, and at-rest encryption of the secret key. It is intended
// for a private beta with tiny amounts only. Private keys are NEVER logged.
// ---------------------------------------------------------------------

export interface AgentWalletGate {
  enabled: boolean;
  reason?: string;
  caps: AgentWalletCaps;
}

export function agentWalletGate(userWallet: string, network: SolanaNetwork): AgentWalletGate {
  const config = dcaConfig();
  const caps = config.agentWallet;

  if (!config.enableAgentWalletMode) {
    return { enabled: false, reason: "Experimental Agent Wallet Mode is disabled on this deployment.", caps };
  }
  if (!caps.encryptionKey) {
    return { enabled: false, reason: "AGENT_WALLET_ENCRYPTION_KEY is not configured.", caps };
  }
  if (network === "mainnet" && caps.allowedUsers.length === 0) {
    return {
      enabled: false,
      reason: "Mainnet agent wallet mode requires an explicit AGENT_WALLET_ALLOWED_USERS allowlist.",
      caps
    };
  }
  if (caps.allowedUsers.length > 0 && !caps.allowedUsers.includes(userWallet)) {
    return { enabled: false, reason: "This wallet is not on the agent wallet allowlist.", caps };
  }
  return { enabled: true, caps };
}

export interface CapValidation {
  ok: boolean;
  error?: string;
}

export function validateAgentWalletCaps(
  totalSol: number,
  numberOfOrders: number,
  intervalSeconds: number,
  caps: AgentWalletCaps
): CapValidation {
  if (totalSol > caps.maxTotalSol) {
    return { ok: false, error: `Total exceeds the agent-wallet cap of ${caps.maxTotalSol} SOL.` };
  }
  if (numberOfOrders > caps.maxOrders) {
    return { ok: false, error: `Number of buys exceeds the agent-wallet cap of ${caps.maxOrders}.` };
  }
  if (intervalSeconds < caps.minIntervalSeconds) {
    return { ok: false, error: `Interval must be at least ${caps.minIntervalSeconds}s in agent-wallet mode.` };
  }
  return { ok: true };
}

function encryptionKey(): Buffer {
  const secret = dcaConfig().agentWallet.encryptionKey;
  if (!secret) throw new Error("AGENT_WALLET_ENCRYPTION_KEY is not configured.");
  return createHash("sha256").update(secret).digest();
}

export function encryptSecret(plaintext: string): string {
  const iv = randomBytes(12);
  const cipher = createCipheriv("aes-256-gcm", encryptionKey(), iv);
  const ciphertext = Buffer.concat([cipher.update(plaintext, "utf8"), cipher.final()]);
  const tag = cipher.getAuthTag();
  return `${iv.toString("base64")}:${tag.toString("base64")}:${ciphertext.toString("base64")}`;
}

export function decryptSecret(payload: string): string {
  const [ivB64, tagB64, dataB64] = payload.split(":");
  const decipher = createDecipheriv("aes-256-gcm", encryptionKey(), Buffer.from(ivB64, "base64"));
  decipher.setAuthTag(Buffer.from(tagB64, "base64"));
  return Buffer.concat([decipher.update(Buffer.from(dataB64, "base64")), decipher.final()]).toString("utf8");
}

/** Create (or return existing) encrypted agent wallet for a user. */
export async function ensureAgentWallet(
  userWallet: string,
  network: SolanaNetwork
): Promise<StoredAgentWallet> {
  const existing = await getAgentWallet(userWallet);
  if (existing) return existing;

  const keypair = Keypair.generate();
  const stored: StoredAgentWallet = {
    userWallet,
    publicKey: keypair.publicKey.toBase58(),
    encryptedSecret: encryptSecret(bs58.encode(keypair.secretKey)),
    network,
    createdAt: new Date().toISOString()
  };
  await saveAgentWallet(stored);
  return stored;
}

export function loadKeypair(stored: StoredAgentWallet): Keypair {
  return Keypair.fromSecretKey(bs58.decode(decryptSecret(stored.encryptedSecret)));
}
