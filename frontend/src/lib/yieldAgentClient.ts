import { mapApiActions, type AgentAction } from "@/lib/dcaAgentClient";

export type YieldChatResponse = {
  reply: string;
  session_id: string;
  actions: { tool: string; args: Record<string, unknown>; result: string }[];
};

export type YieldHealth = {
  status: string;
  agent: string;
  model?: string;
  pricing?: string;
  platform_fee_rate?: number;
  auth_required?: boolean;
  live_routing?: string;
};

/** 0.5% platform fee charged on top of invest capital. */
export const YIELD_PLATFORM_FEE_RATE = 0.005;

export function yieldPlatformFee(capital: number): number {
  if (!Number.isFinite(capital) || capital <= 0) return 0;
  return Math.round(capital * YIELD_PLATFORM_FEE_RATE * 1e12) / 1e12;
}

export function yieldInvestTotalCost(capital: number): number {
  if (!Number.isFinite(capital) || capital <= 0) return 0;
  return Math.round((capital + yieldPlatformFee(capital)) * 1e12) / 1e12;
}

export type YieldVenue = {
  protocol_id?: string;
  protocol_name?: string;
  symbol?: string;
  mint?: string;
  apy?: number | null;
  tvl_usd?: number | null;
  executable?: boolean;
  yield_type?: string;
  kind?: string;
  project?: string;
};

export type YieldPosition = {
  id: string;
  protocol_id: string;
  protocol_name: string;
  symbol: string;
  amount: number;
  entry_apy?: number | null;
  status: string;
  explorer_url?: string | null;
};

export type YieldDashboard = {
  yields?: {
    executable_venues?: YieldVenue[];
    markets?: YieldVenue[];
    lending_compare?: YieldVenue[];
    best_executable?: YieldVenue | null;
    note?: string;
  };
  positions?: YieldPosition[];
  mandate?: {
    auto_rebalance?: boolean;
    min_apy_gain?: number;
    idle_reserve_sol?: number;
  } | null;
  balances?: {
    balances?: Array<{ token: string; available: number; deposited: number }>;
  };
};

export async function fetchYieldHealth(): Promise<YieldHealth | null> {
  try {
    const res = await fetch("/api/agents/yield/health", { cache: "no-store" });
    if (!res.ok) return null;
    return (await res.json()) as YieldHealth;
  } catch {
    return null;
  }
}

export async function fetchYieldDashboard(authToken: string): Promise<YieldDashboard | null> {
  try {
    const res = await fetch("/api/agents/yield/dashboard", {
      cache: "no-store",
      headers: { Authorization: `Bearer ${authToken}` },
    });
    if (!res.ok) return null;
    return (await res.json()) as YieldDashboard;
  } catch {
    return null;
  }
}

export type YieldInvestResult = {
  status: string;
  message?: string;
  error?: string;
  signature?: string;
  explorer_url?: string;
  asset?: string;
  duration_days?: number;
};

function readInvestError(data: { detail?: unknown; error?: unknown }): string {
  const detail = data.detail;
  if (typeof detail === "string" && detail.trim()) return detail;
  if (Array.isArray(detail)) {
    const parts = detail
      .map((item) => {
        if (typeof item === "string") return item;
        if (item && typeof item === "object" && "msg" in item) {
          return String((item as { msg: unknown }).msg);
        }
        return "";
      })
      .filter(Boolean);
    if (parts.length) return parts.join("; ");
  }
  if (detail && typeof detail === "object") return JSON.stringify(detail);
  if (typeof data.error === "string" && data.error.trim()) return data.error;
  if (data.error) return JSON.stringify(data.error);
  return "Invest failed";
}

export async function investYieldCapital(
  authToken: string,
  body: {
    asset: string;
    capital: number;
    duration_days: number;
    yield_type: string;
    skip_deposit_ledger?: boolean;
    force_protocol?: string;
  }
): Promise<YieldInvestResult> {
  const res = await fetch("/api/agents/yield/invest", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${authToken}`,
    },
    body: JSON.stringify(body),
  });
  const data = (await res.json()) as YieldInvestResult & { detail?: unknown };
  if (!res.ok) {
    throw new Error(readInvestError(data));
  }
  if (data.error) {
    throw new Error(data.error);
  }
  return data;
}

export async function sendYieldAgentMessage(
  message: string,
  authToken: string,
  sessionId?: string,
  history?: { role: "user" | "assistant"; content: string }[]
): Promise<YieldChatResponse> {
  const res = await fetch("/api/agents/yield/chat", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${authToken}`,
    },
    body: JSON.stringify({ message, session_id: sessionId, history }),
  });
  const data = await res.json();
  if (!res.ok) {
    const detail = typeof data.detail === "string" ? data.detail : data.error ?? "Request failed";
    throw new Error(detail);
  }
  return data as YieldChatResponse;
}

export function mapYieldActions(actions: YieldChatResponse["actions"]): AgentAction[] {
  return mapApiActions(actions);
}

export const YIELD_TYPES = [
  { id: "any", label: "Any" },
  { id: "lending", label: "Lending" },
  { id: "liquidity_vault", label: "Liquidity vault" },
  { id: "jlp", label: "JLP" },
] as const;

export const YIELD_TYPE_HELP: Record<(typeof YIELD_TYPES)[number]["id"], string> = {
  any: "Any ranks Kamino, Jupiter, and Save, then deposits into the best match. Kamino uses its API. Jupiter buys JLP. Save deposits into SOL lending. Fee is 0.5% of capital on top (0.1 SOL invest needs 0.1005 SOL idle, plus a little for gas).",
  lending:
    "Lending ranks Kamino and Save SOL markets and deposits into the one with the better rate. Fee is 0.5% of capital on top of the invest amount.",
  liquidity_vault:
    "Liquidity vault deposits SOL into the best Kamino vault through the Kamino API (https://api.kamino.finance). Fee is 0.5% of capital on top of the invest amount.",
  jlp: "JLP sends deposited SOL from your Circle wallet through Jupiter into JLP, Jupiter's liquidity pool token. Fee is 0.5% of capital on top of the invest amount.",
};

export const YIELD_EXAMPLE_PROMPTS = [
  "Compare lending yields for SOL",
  "Invest 0.1 SOL in Jupiter JLP for 30 days",
  "Invest 0.05 SOL in Save for 2 days",
  "Find the best Kamino liquidity vault for 90 days",
] as const;
