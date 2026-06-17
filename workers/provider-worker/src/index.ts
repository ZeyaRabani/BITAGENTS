import { shortAddress, type ComputeProvider, type ComputeType, type ProviderStatus } from "@bitagents/shared";
import { PublicKey } from "@solana/web3.js";
import dotenv from "dotenv";
import path from "node:path";

dotenv.config({ path: path.resolve(process.cwd(), "../../.env") });
dotenv.config({ path: path.resolve(process.cwd(), "../../.env.local"), override: true });
dotenv.config({ override: true });

// Optional remote compute provider.
//
// Agent computation runs server-side inside the Next.js app (frontend/src/server/agents),
// so this worker is NOT required to run the demo. It exists to demonstrate a remote
// provider joining the marketplace: it registers a provider profile and keeps it online
// with a periodic heartbeat against the public /api/providers endpoint.

const apiBaseUrl = (process.env.API_BASE_URL ?? "http://localhost:3000").replace(/\/$/, "");
const heartbeatMs = Number(process.env.HEARTBEAT_INTERVAL_MS ?? 30000);
const providerWallet = normalizeProviderWallet(process.env.PROVIDER_WALLET);
const providerName = process.env.PROVIDER_NAME ?? "remote-worker-01";
const computeType = normalizeComputeType(process.env.PROVIDER_COMPUTE_TYPE);
const pricePerTaskSol = normalizePrice(process.env.PROVIDER_PRICE_SOL);
const endpoint = process.env.PROVIDER_ENDPOINT?.trim() || undefined;
const status: ProviderStatus = "online";

function normalizeProviderWallet(value: string | undefined) {
  if (!value || value.includes("REPLACE")) {
    return "";
  }
  try {
    return new PublicKey(value).toBase58();
  } catch {
    console.error(`Invalid PROVIDER_WALLET: ${value}`);
    return "";
  }
}

function normalizeComputeType(value: string | undefined): ComputeType {
  if (value === "GPU_SIMULATED" || value === "LLM") {
    return value;
  }
  return "CPU";
}

function normalizePrice(value: string | undefined): number {
  const parsed = Number(value);
  if (!Number.isFinite(parsed) || parsed < 0) {
    return 0.001;
  }
  return parsed;
}

function hasErrorMessage(value: unknown): value is { error: string } {
  return (
    typeof value === "object" &&
    value !== null &&
    "error" in value &&
    typeof (value as { error?: unknown }).error === "string"
  );
}

async function apiFetch<T>(pathName: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${apiBaseUrl}${pathName}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {})
    }
  });
  const payload = (await response.json().catch(() => null)) as unknown;
  if (!response.ok) {
    throw new Error(hasErrorMessage(payload) ? payload.error : response.statusText);
  }
  return payload as T;
}

async function heartbeat() {
  if (!providerWallet) {
    console.log("Set PROVIDER_WALLET in .env.local to register this worker as a provider.");
    return;
  }
  try {
    const { provider } = await apiFetch<{ provider: ComputeProvider }>("/api/providers", {
      method: "POST",
      body: JSON.stringify({
        walletAddress: providerWallet,
        name: providerName,
        computeType,
        pricePerTaskSol,
        status,
        endpoint
      })
    });
    console.log(
      `[worker ${shortAddress(providerWallet)}] online — ${provider.computeType} @ ${provider.pricePerTaskSol} SOL, ${provider.tasksCompleted} tasks, rep ${provider.reputation}`
    );
  } catch (error) {
    console.error(`[worker] heartbeat failed: ${(error as Error).message}`);
  }
}

console.log("BITAGENTS provider worker starting (optional remote provider)");
console.log(`API: ${apiBaseUrl}`);
console.log(`Provider wallet: ${providerWallet ? shortAddress(providerWallet) : "not configured"}`);

void heartbeat();
const interval = setInterval(() => void heartbeat(), Number.isFinite(heartbeatMs) ? heartbeatMs : 30000);

process.on("SIGINT", () => {
  clearInterval(interval);
  process.exit(0);
});

process.on("SIGTERM", () => {
  clearInterval(interval);
  process.exit(0);
});
