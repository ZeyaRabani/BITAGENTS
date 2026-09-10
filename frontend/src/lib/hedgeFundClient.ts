import { mapApiActions, type AgentAction } from "@/lib/dcaAgentClient";

export type HedgeFundChatResponse = {
  reply: string;
  session_id: string;
  actions: { tool: string; args: Record<string, unknown>; result: string }[];
};

export type HedgeFundHealth = {
  status: string;
  agent: string;
  model: string;
  fee_model?: string;
  management_fee_annual_pct?: number;
  performance_fee_pct?: number;
  management_fee_on_start_pct?: number;
  performance_fee_on_profit_pct?: number;
  pricing?: string;
  auth_required: boolean;
  paper_trading?: boolean;
  live_trading?: boolean;
  deposits_required?: boolean;
  trading_wallet?: string | null;
  trading_wallet_configured?: boolean;
  max_strategy_usdc?: number;
  min_horizon_days?: number;
  allowed_deposit_tokens?: string[];
  monitor_interval_seconds?: number;
};

export type HedgeFundFeeStructure = {
  name: string;
  management_fee_annual_pct: number;
  performance_fee_pct: number;
  traditional_2_20: { management_pct: number; performance_pct: number };
  description: string;
  example_100k_12mo: {
    management_fee_usd: number;
    performance_fee_usd: number;
    total_fees_usd: number;
    net_profit_after_fees_usd: number;
  };
};

export type PaperPosition = {
  id?: string;
  symbol: string;
  side?: string;
  units: number;
  avg_entry_usd?: number;
  mark_price_usd?: number;
  market_value_usd?: number;
  unrealized_pnl_usd?: number;
  strategy_id?: string;
};

export type PaperStrategy = {
  id: string;
  name: string;
  mode: string;
  status: string;
  symbols: string[];
  horizon_days?: number;
  horizon_label?: string;
  trading_mode?: string;
  rules?: {
    take_profit_pct?: number;
    stop_loss_pct?: number;
    notes?: string;
    objective?: string;
    horizon_days?: number;
    trading_mode?: string;
    funding_token?: string;
    mint_map?: Record<string, string>;
    solana_assets?: {
      symbol?: string;
      display_symbol?: string;
      mint?: string;
      is_xstock?: boolean;
    }[];
    liquidation_mint?: string;
    capital_usd?: number;
    last_error?: string;
    deploy_errors?: { symbol?: string; error?: string }[];
    partial_deploy_refunded?: boolean;
    liquidation_txs?: {
      signature?: string;
      explorer_url?: string;
      symbol?: string;
      side?: string;
    }[];
    swapped_to_usdc?: boolean;
  };
  created_by?: string;
  updated_at?: string;
};

export type PaperDecision = {
  id?: string;
  strategy_id?: string;
  symbol?: string;
  action?: string;
  rationale?: string;
  created_at?: string;
  signals?: Record<string, unknown>[];
  decision_graph?: Record<string, unknown>;
};

export type PaperTrade = {
  id?: string;
  strategy_id?: string;
  symbol?: string;
  side?: string;
  notional_usd?: number;
  price_usd?: number;
  created_at?: string;
  reason?: string;
  mint?: string;
  signature?: string;
  explorer_url?: string;
  fee_usd?: number;
};

export type StrategyBlock = {
  strategy: PaperStrategy;
  trading_mode?: string;
  positions: PaperPosition[];
  sleeve_value_usd?: number;
  trades: PaperTrade[];
  live_trades?: PaperTrade[];
  decisions: PaperDecision[];
  symbols: string[];
  horizon_days?: number;
  horizon_label?: string;
  closed?: boolean;
  realized_pnl_usd?: number;
  realized_pnl_pct?: number;
  liquidation_proceeds_usd?: number | null;
  capital_usd?: number | null;
  perf_fee_usd?: number | null;
  liquidation_txs?: {
    signature?: string;
    explorer_url?: string;
    symbol?: string;
    side?: string;
  }[];
};

export type FailedStrategy = PaperStrategy & {
  last_error?: string;
  deploy_errors?: { symbol?: string; error?: string }[];
};

export type PaperDashboard = {
  mode: string;
  live_trading?: boolean;
  paper_trading?: boolean;
  monitor_interval_seconds: number;
  last_market_refresh_at?: string | null;
  governance?: string;
  llm_required?: boolean;
  portfolio: {
    cash_usd?: number;
    equity_usd?: number;
    pnl_usd?: number;
    pnl_pct?: number;
    positions?: PaperPosition[];
    portfolio?: Record<string, unknown>;
  };
  strategies: PaperStrategy[];
  failed_strategies?: FailedStrategy[];
  by_strategy?: StrategyBlock[];
  overlapping_assets?: Record<string, string[]>;
  decisions: PaperDecision[];
  trades: PaperTrade[];
  live_trades?: PaperTrade[];
  backtests?: Record<string, unknown>[];
  market?: { symbol: string; price_usd?: number; change_24h_pct?: number }[];
  news?: { symbol?: string; title?: string; publisher?: string }[];
};

async function authFetch(path: string, authToken: string, init?: RequestInit) {
  const res = await fetch(path, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${authToken}`,
      ...(init?.headers || {}),
    },
    cache: "no-store",
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const detail =
      typeof data.detail === "string" ? data.detail : data.error ?? "Request failed";
    throw new Error(detail);
  }
  return data;
}

export async function fetchHedgeFundHealth(): Promise<HedgeFundHealth | null> {
  try {
    const res = await fetch("/api/agents/hedge-fund/health", { cache: "no-store" });
    if (!res.ok) return null;
    return (await res.json()) as HedgeFundHealth;
  } catch {
    return null;
  }
}

export async function fetchHedgeFundFees(): Promise<HedgeFundFeeStructure | null> {
  try {
    const res = await fetch("/api/agents/hedge-fund/fees", { cache: "no-store" });
    if (!res.ok) return null;
    return (await res.json()) as HedgeFundFeeStructure;
  } catch {
    return null;
  }
}

const CHAT_TIMEOUT_MS = 170_000;

export async function sendHedgeFundMessage(
  message: string,
  authToken: string,
  sessionId?: string,
  history?: { role: "user" | "assistant"; content: string }[]
): Promise<HedgeFundChatResponse> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), CHAT_TIMEOUT_MS);
  let res: Response;
  try {
    res = await fetch("/api/agents/hedge-fund/chat", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${authToken}`,
      },
      body: JSON.stringify({ message, session_id: sessionId, history }),
      signal: controller.signal,
    });
  } catch (err) {
    if (err instanceof DOMException && err.name === "AbortError") {
      throw new Error(
        "Still working on-chain (Jupiter swaps can take a while) — the strategy is being processed in " +
          "the background. Check the Strategies list below in a bit instead of resending."
      );
    }
    throw err;
  } finally {
    clearTimeout(timer);
  }

  const data = await res.json();
  if (!res.ok) {
    const detail = typeof data.detail === "string" ? data.detail : data.error ?? "Request failed";
    throw new Error(detail);
  }

  return data as HedgeFundChatResponse;
}

export async function fetchPaperDashboard(authToken: string): Promise<PaperDashboard> {
  return (await authFetch("/api/agents/hedge-fund/paper/dashboard", authToken)) as PaperDashboard;
}

export async function createPaperStrategy(
  authToken: string,
  body: {
    tokens?: string[];
    name?: string;
    mode?: string;
    take_profit_pct?: number;
    stop_loss_pct?: number;
    capital_usd?: number;
    notes?: string;
    horizon_days?: number | null;
    trading_mode?: string;
    funding_token?: string;
    mint_overrides?: Record<string, string>;
  }
) {
  return authFetch("/api/agents/hedge-fund/paper/strategies", authToken, {
    method: "POST",
    body: JSON.stringify({ trading_mode: "live", funding_token: "SOL", ...body }),
  });
}

export async function updatePaperStrategy(
  authToken: string,
  strategyId: string,
  body: {
    take_profit_pct?: number;
    stop_loss_pct?: number;
    tokens?: string[];
    name?: string;
    status?: string;
    notes?: string;
    horizon_days?: number | null;
    add_capital_usd?: number;
  }
) {
  return authFetch(`/api/agents/hedge-fund/paper/strategies/${encodeURIComponent(strategyId)}`, authToken, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

export async function runPaperMonitor(authToken: string, force = false) {
  const qs = force ? "?force=true" : "";
  return authFetch(`/api/agents/hedge-fund/paper/monitor${qs}`, authToken, { method: "POST" });
}

export async function runPaperBacktest(
  authToken: string,
  body: { period?: string; strategy_id?: string; tokens?: string[]; capital_usd?: number }
) {
  return authFetch("/api/agents/hedge-fund/paper/backtest", authToken, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function confirmPaperStrategy(
  authToken: string,
  strategyId: string,
  body?: {
    capital_usd?: number;
    horizon_days?: number | null;
    funding_token?: string;
    mint_overrides?: Record<string, string>;
  }
) {
  return authFetch(
    `/api/agents/hedge-fund/paper/strategies/${encodeURIComponent(strategyId)}/confirm`,
    authToken,
    { method: "POST", body: JSON.stringify(body || {}) }
  );
}

export async function retryPaperStrategy(
  authToken: string,
  strategyId: string,
  body?: { replace?: Record<string, string>; mint_overrides?: Record<string, string> }
) {
  return authFetch(
    `/api/agents/hedge-fund/paper/strategies/${encodeURIComponent(strategyId)}/retry`,
    authToken,
    { method: "POST", body: JSON.stringify(body || {}) }
  );
}

export async function fetchLiveTrades(authToken: string, strategyId: string) {
  return authFetch(
    `/api/agents/hedge-fund/paper/strategies/${encodeURIComponent(strategyId)}/live-trades`,
    authToken
  );
}

export async function fetchStrategyLivePnl(authToken: string, strategyId: string) {
  return authFetch(
    `/api/agents/hedge-fund/paper/strategies/${encodeURIComponent(strategyId)}/pnl`,
    authToken
  );
}

export async function liquidatePaperStrategy(authToken: string, strategyId: string) {
  return authFetch(
    `/api/agents/hedge-fund/paper/strategies/${encodeURIComponent(strategyId)}/liquidate`,
    authToken,
    { method: "POST" }
  );
}

export async function dismissPaperStrategy(authToken: string, strategyId: string) {
  return authFetch(
    `/api/agents/hedge-fund/paper/strategies/${encodeURIComponent(strategyId)}/dismiss`,
    authToken,
    { method: "POST" }
  );
}

export async function addPaperStrategyCapital(
  authToken: string,
  strategyId: string,
  capitalUsd: number
) {
  return authFetch(
    `/api/agents/hedge-fund/paper/strategies/${encodeURIComponent(strategyId)}/add-capital`,
    authToken,
    { method: "POST", body: JSON.stringify({ capital_usd: capitalUsd }) }
  );
}

export async function analyzePaperAsset(
  authToken: string,
  symbol: string,
  equityUsd = 100
) {
  return authFetch("/api/agents/hedge-fund/paper/analyze", authToken, {
    method: "POST",
    body: JSON.stringify({ symbol, equity_usd: equityUsd }),
  });
}

export function mapHedgeFundActions(actions: HedgeFundChatResponse["actions"]): AgentAction[] {
  return mapApiActions(actions);
}
