export type FibSetup = {
  side: "long" | "short";
  bias: string;
  entry: number;
  stop: number;
  take_profit: number;
  risk: number;
  reward: number;
  risk_reward: string;
  fib_entry: number;
  reason: string;
  prior?: Record<string, unknown>;
  levels?: Record<string, number>;
};

export type FibFill = {
  status: string;
  date: string;
  side: string;
  entry: number;
  exit?: number | null;
  exit_reason?: string | null;
  pnl_r: number;
  pnl_usd?: number;
};

export type FibInspect = {
  symbol: string;
  yahoo_symbol: string;
  prior_day: Record<string, number | string>;
  latest_day: Record<string, number | string>;
  setup: FibSetup;
  note?: string;
};

export type FibPaperResult = {
  mode: "paper";
  symbol: string;
  prior_day: Record<string, number | string>;
  latest_day: Record<string, number | string>;
  setup: FibSetup;
  fill: FibFill;
  book: {
    cash_usd: number;
    realized_pnl_usd: number;
    open: unknown;
    trades: unknown[];
  };
  note?: string;
};

export type FibBacktestResult = {
  mode: "backtest";
  symbol: string;
  yahoo_symbol: string;
  params: Record<string, unknown>;
  summary: {
    trades: number;
    skips: number;
    wins: number;
    losses: number;
    flats: number;
    win_rate_pct: number;
    avg_r: number;
    total_pnl_usd: number;
    expectancy_r: number;
  };
  trades: Array<{
    setup_date: string;
    trade_date: string;
    side: string;
    entry: number;
    stop: number;
    take_profit: number;
    exit: number;
    exit_reason: string;
    pnl_r: number;
    pnl_usd: number;
  }>;
  note?: string;
};

async function call<T>(
  path: string,
  options: { method?: "GET" | "POST"; body?: unknown; token: string }
): Promise<T> {
  const res = await fetch(`/api/agents/fib-ohlc${path}`, {
    method: options.method ?? "GET",
    cache: "no-store",
    headers: {
      Authorization: `Bearer ${options.token}`,
      ...(options.body !== undefined ? { "Content-Type": "application/json" } : {}),
    },
    body: options.body !== undefined ? JSON.stringify(options.body) : undefined,
  });
  const data = (await res.json().catch(() => ({}))) as Record<string, unknown>;
  if (!res.ok) {
    throw new Error(String(data.detail || data.error || `HTTP ${res.status}`));
  }
  return data as T;
}

export const fibOhlcApi = {
  inspect: (token: string, asset: string, lookbackDays = 120) =>
    call<FibInspect>(`/inspect?asset=${encodeURIComponent(asset)}&lookback_days=${lookbackDays}`, {
      token,
    }),
  paper: (token: string, body: { asset: string; lookback_days?: number; notional_usd?: number }) =>
    call<FibPaperResult>("/paper", { method: "POST", body, token }),
  backtest: (token: string, body: { asset: string; lookback_days?: number; notional_usd?: number }) =>
    call<FibBacktestResult>("/backtest", { method: "POST", body, token }),
  book: (token: string) => call<{ cash_usd: number; realized_pnl_usd: number; trades: unknown[] }>("/book", { token }),
};
