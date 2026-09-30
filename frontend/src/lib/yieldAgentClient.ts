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
  auth_required?: boolean;
  live_routing?: string;
};

export type YieldVenue = {
  protocol_id?: string;
  protocol_name?: string;
  symbol?: string;
  mint?: string;
  apy?: number | null;
  tvl_usd?: number | null;
  executable?: boolean;
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

export async function investYieldCapital(
  authToken: string,
  body: { asset: string; capital: number; duration_days: number }
): Promise<YieldInvestResult> {
  const res = await fetch("/api/agents/yield/invest", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${authToken}`,
    },
    body: JSON.stringify(body),
  });
  const data = (await res.json()) as YieldInvestResult & { detail?: string };
  if (!res.ok) {
    const detail = typeof data.detail === "string" ? data.detail : data.error ?? "Invest failed";
    throw new Error(detail);
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

export const YIELD_EXAMPLE_PROMPTS = [
  "Compare Solana yield protocols",
  "Invest 0.1 SOL for 30 days in the best protocol",
  "Rebalance if something pays more",
  "Unwind my position back to SOL",
] as const;
