import type {
  DcaExecution,
  DcaExecutionMode,
  DcaPlan,
  SolanaNetwork
} from "@bitagents/shared";
import { apiFetch } from "@/lib/api";

export type ParseResponse =
  | { ok: true; plan: DcaPlan; engine: "llm" | "deterministic"; parsed: unknown }
  | { ok: false; clarification?: string; error?: string; engine?: string };

export interface CreatePlanRequest {
  plan: DcaPlan;
  walletAddress: string;
  network: SolanaNetwork;
  executionMode?: DcaExecutionMode;
}

export type CreatePlanResponse =
  | { ok: true; plan: DcaPlan; mode: "devnet_demo" }
  | { ok: true; plan: DcaPlan; mode: "agent_wallet"; depositAddress: string }
  | { ok: true; plan: DcaPlan; mode: "jupiter_recurring"; transaction: string; requestId: string }
  | { ok: false; jupiterError?: string; minOrder?: boolean; plan?: DcaPlan; error?: string; clarification?: string };

export interface ExecuteResponse {
  ok: boolean;
  plan?: DcaPlan;
  signature?: string | null;
  orderAccount?: string | null;
  explorerUrl?: string | null;
  error?: string;
}

export type CancelResponse =
  | { ok: true; plan: DcaPlan }
  | { ok: true; needsSignature: true; transaction: string; requestId: string }
  | { ok: false; error: string };

export interface PlanDetail {
  plan: DcaPlan;
  executions: DcaExecution[];
}

export interface MarketBuyQuote {
  inputSymbol: string;
  outputSymbol: string;
  inputMint: string;
  outputMint: string;
  inputAmountUi: number;
  outputAmountUi: number;
  priceImpactPct: number | null;
  slippageBps: number;
}

export type MarketBuyResponse =
  | { ok: true; transaction: string; lastValidBlockHeight: number | null; quote: MarketBuyQuote }
  | { ok: false; error: string };

export async function marketBuy(input: {
  walletAddress: string;
  network: SolanaNetwork;
  outputMint: string;
  inputMint?: string;
  amountUi: number;
  slippageBps?: number;
}): Promise<MarketBuyResponse> {
  return apiFetch<MarketBuyResponse>("/api/dca/buy", {
    method: "POST",
    body: JSON.stringify(input)
  });
}

export async function parseDcaMessage(input: {
  message: string;
  walletAddress?: string;
  network: SolanaNetwork;
  executionMode?: DcaExecutionMode;
}): Promise<ParseResponse> {
  return apiFetch<ParseResponse>("/api/dca/parse", {
    method: "POST",
    body: JSON.stringify(input)
  });
}

export async function createDcaPlan(input: CreatePlanRequest): Promise<CreatePlanResponse> {
  return apiFetch<CreatePlanResponse>("/api/dca/plans", {
    method: "POST",
    body: JSON.stringify(input)
  });
}

export async function listDcaPlans(wallet: string): Promise<DcaPlan[]> {
  const data = await apiFetch<{ plans: DcaPlan[] }>(`/api/dca/plans?wallet=${encodeURIComponent(wallet)}`);
  return data.plans;
}

export async function getDcaPlan(id: string): Promise<PlanDetail> {
  return apiFetch<PlanDetail>(`/api/dca/plans/${id}`);
}

export async function executeDcaPlan(
  id: string,
  body: { signedTransaction: string; requestId: string }
): Promise<ExecuteResponse> {
  return apiFetch<ExecuteResponse>(`/api/dca/plans/${id}/execute`, {
    method: "POST",
    body: JSON.stringify(body)
  });
}

export async function cancelDcaPlan(id: string, body?: { signature?: string }): Promise<CancelResponse> {
  return apiFetch<CancelResponse>(`/api/dca/plans/${id}/cancel`, {
    method: "POST",
    body: JSON.stringify(body ?? {})
  });
}
