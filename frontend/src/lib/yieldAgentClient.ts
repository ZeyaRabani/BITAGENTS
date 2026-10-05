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

export async function investYieldCapital(
  authToken: string,
  body: { asset: string; capital: number; duration_days: number; yield_type: string }
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

export const YIELD_TYPES = [
  { id: "any", label: "Any" },
  { id: "lending", label: "Lending" },
  { id: "liquidity_vault", label: "Liquidity vault" },
  { id: "jlp", label: "JLP" },
  { id: "insurance", label: "Insurance fund" },
] as const;

export const YIELD_TYPE_HELP: Record<(typeof YIELD_TYPES)[number]["id"], string> = {
  any: "Any ranks Kamino, Jupiter, MarginFi, Drift, and Save. If Kamino wins, the agent deposits through the Kamino API. If JLP wins, it swaps through Jupiter. Save is ranked only. MarginFi and Drift have no deposit API, so those winners stay idle.",
  lending:
    "Lending ranks Kamino, Save, MarginFi, and Drift SOL markets. A Kamino winner is deposited through https://api.kamino.finance. Save is ranked from its public API and is not deposited. MarginFi and Drift have no deposit API.",
  liquidity_vault:
    "Liquidity vault deposits SOL into the best Kamino vault through the Kamino API (https://api.kamino.finance).",
  jlp: "JLP sends deposited SOL from your Circle wallet through Jupiter into JLP, Jupiter's liquidity pool token.",
  insurance:
    "Insurance looks at Drift's insurance fund. Drift does not publish a deposit API (https://docs.drift.trade/developers/data-api), so the balance stays idle.",
};

export const YIELD_EXAMPLE_PROMPTS = [
  "Compare lending yields for SOL",
  "Invest 0.1 SOL in Jupiter JLP for 30 days",
  "Find the best Kamino liquidity vault for 90 days",
  "Unwind my position back to SOL",
] as const;
