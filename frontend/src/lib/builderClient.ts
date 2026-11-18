// Browser client for the agent builder. Every call goes through the Next.js
// proxy under /api/builder, which adds the internal key server-side.

export type BuildStatus = "draft" | "building" | "ready" | "failed";

export type BuilderSpec = {
  name: string;
  description: string;
  strategy: {
    template: string;
    params: {
      symbols: string[];
      per_symbol_usd: number;
      buy_threshold?: number;
      sell_threshold?: number;
      lookback_days?: number;
      trigger_symbol?: string;
      trigger_pct?: number;
      window_minutes?: number;
    };
    schedule_minutes: number;
  };
  app: { brief: string; skill: string };
  limits: BuilderLimits;
};

export type BuilderLimits = {
  quote: string;
  max_trade_usd: number;
  max_daily_usd: number;
  slippage_bps: number;
};

export type BuildStep = {
  step: string;
  seconds: number;
  exit_code: number;
  tail: string;
};

export type BuilderBuild = {
  stage?: string;
  steps?: BuildStep[];
  artifact?: { path: string; bytes: number; sha256: string };
  installed?: { path: string; target: string } | null;
  install_note?: string;
  /** Set when the agent was published to a shared hosted Aomi app, not compiled locally. */
  hosted?: { app: string; note: string };
  error?: string;
  files?: string[];
  started_at?: number;
  finished_at?: number;
};

/** paper: runs are simulated on mainnet against a paper balance. live: runs are staged for the agent wallet to sign. */
export type AgentMode = "paper" | "live";

export type BuilderAgent = {
  id: string;
  /** Absent only on responses from a backend older than paper mode. */
  mode?: AgentMode;
  owner_wallet: string;
  prompt: string;
  spec: BuilderSpec;
  spec_sha: string;
  compose_meta?: { model?: string; llm_passes?: number; repaired_errors?: string[] } | null;
  app_name: string;
  build_status: BuildStatus;
  build?: BuilderBuild | null;
  created_at: string;
  updated_at: string;
};

export type BuilderTemplate = {
  name: string;
  title: string;
  summary: string;
  params_schema: unknown;
};

export type SignalToken =
  | {
      symbol: string;
      mint: string;
      decimals: number;
      name: string;
      usd_price: number | null;
      icon: string | null;
      error?: undefined;
    }
  | { error: string };

export type AnalystOpinion = {
  analyst: string;
  domain: string;
  signal: string;
  confidence: number;
  score: number;
  reasoning: string;
};

export type BuilderSignal = {
  symbol: string;
  price: number | null;
  bars?: number;
  action: "buy" | "sell" | "hold";
  composite_score?: number;
  confidence?: number;
  kind?: "trigger" | "basket";
  change_pct?: number | null;
  threshold_pct?: number;
  window_minutes?: number;
  fired?: boolean;
  signal_counts?: { bullish: number; bearish: number; neutral: number };
  analysts?: AnalystOpinion[];
  headlines?: string[];
  data_source?: string;
  as_of?: string;
  token?: SignalToken | null;
};

export type BuilderHolding = {
  mint: string;
  symbol: string;
  amount: number;
  decimals: number;
  value_usd: number | null;
};

/** The agent's paper book. These are not on-chain funds. */
export type PaperBook = {
  start_usd: number;
  cash_usd: number;
  equity_usd: number;
  holdings: BuilderHolding[];
};

/** One wallet's paper balance for an agent, valued at current prices. */
export type PerformanceBook = PaperBook & {
  wallet: string;
  pnl_usd: number;
  updated_at: string | null;
  /** False when a holding could not be priced, so equity is understated. */
  priced: boolean;
};

/** Result of simulating the real swap on Solana mainnet. Never broadcast. */
export type OrderSimulation = {
  ok: boolean;
  backend: string;
  slot: number | null;
  error: unknown | null;
  units_consumed: number | null;
  tx_bytes: number;
  lent_in_simulation: { input_raw: number; sol: number };
  in_spent_raw: number;
  out_received_raw: number;
  logs_tail: string[];
};

export type PaperFill = { tokens: number; usd: number; price_usd: number | null };

export type BuilderOrder = {
  index: number;
  side: string;
  symbol: string;
  token_symbol: string;
  mint: string;
  usd: number;
  reason: string;
  /** Live mode, built runs: instructions for the agent wallet to stage and sign. */
  stage?: { description?: string; kind?: string; instructions?: unknown[]; address_lookup_tables?: unknown[] };
  /** Paper mode, built runs. */
  simulation?: OrderSimulation;
  /** Paper mode, when the simulated fill was booked to the paper balance. */
  paper_fill?: PaperFill;
  build_error?: string;
};

export type EvaluationWallet = {
  address: string;
  /** null in paper mode: the balances below are then the paper book. */
  sol: number | null;
  cash_usd: number;
  quote: string;
  holdings?: BuilderHolding[];
  spent_today_usd: number;
  note?: string;
};

export type BuilderEvaluation = {
  run_id: string;
  agent?: unknown;
  strategy?: unknown;
  mode?: AgentMode;
  paper?: PaperBook | null;
  wallet?: EvaluationWallet;
  limits?: BuilderLimits;
  notes?: string[];
  signals?: BuilderSignal[];
  orders?: BuilderOrder[];
};

export type BuilderRun = {
  id: string;
  wallet: string;
  caller: string;
  built: boolean;
  decision?: {
    mode?: AgentMode;
    signals?: BuilderSignal[];
    notes?: string[];
    wallet?: EvaluationWallet;
    paper?: PaperBook | null;
  } | null;
  orders?: BuilderOrder[] | null;
  error?: string | null;
  created_at: string;
};

export type AomiState = {
  connected: boolean;
  reason?: string;
  app?: string;
  /** On-chain balances of the agent wallet, in both modes. */
  wallet?: { address: string; sol: number; cash_usd: number } | null;
  lane?: string;
  mode?: AgentMode;
  /** Paper mode only, once the agent wallet exists. */
  paper?: PaperBook;
  /** Set when agents run on a hosted Aomi: the wallet and chat live there, not on this site. */
  hosted?: { app: string; chat_url: string; prompt: string; schedule_prompt?: string };
};

export type ChatEvent = {
  type: string;
  tool?: string;
  summary?: string;
  /** Raw tool result text. The server cuts it at 6000 characters, so it may not parse. */
  result?: string | null;
  signature?: string;
};

export type ChatResponse = {
  session_id: string;
  reply: string;
  events?: ChatEvent[];
};

export class BuilderApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.name = "BuilderApiError";
    this.status = status;
  }
}

/** Turn a FastAPI error body into the text the server sent. */
function detailText(data: unknown, status: number): string {
  if (data && typeof data === "object") {
    const record = data as Record<string, unknown>;
    const detail = record.detail ?? record.error ?? record.reason;
    if (typeof detail === "string" && detail) return detail;
    if (Array.isArray(detail)) {
      // Pydantic validation errors: [{loc, msg, type}]
      const parts = detail.map((item) => {
        if (item && typeof item === "object") {
          const entry = item as { loc?: unknown[]; msg?: unknown };
          const where = Array.isArray(entry.loc) ? entry.loc.slice(1).join(".") : "";
          const msg = typeof entry.msg === "string" ? entry.msg : JSON.stringify(item);
          return where ? `${where}: ${msg}` : msg;
        }
        return String(item);
      });
      if (parts.length) return parts.join("; ");
    }
    if (detail != null) return JSON.stringify(detail);
  }
  return `HTTP ${status}`;
}

async function call<T>(
  path: string,
  options: { method?: "GET" | "POST"; body?: unknown; token?: string | null; signal?: AbortSignal } = {}
): Promise<T> {
  const headers: Record<string, string> = {};
  if (options.token) headers.Authorization = `Bearer ${options.token}`;
  if (options.body !== undefined) headers["Content-Type"] = "application/json";

  let res: Response;
  try {
    res = await fetch(`/api/builder${path}`, {
      method: options.method ?? "GET",
      cache: "no-store",
      headers,
      body: options.body !== undefined ? JSON.stringify(options.body) : undefined,
      signal: options.signal,
    });
  } catch (err) {
    if (err instanceof DOMException && err.name === "AbortError") throw err;
    throw new BuilderApiError(0, err instanceof Error ? err.message : "Network request failed");
  }

  const text = await res.text();
  let data: unknown = null;
  if (text.trim()) {
    try {
      data = JSON.parse(text);
    } catch {
      throw new BuilderApiError(res.status, `HTTP ${res.status}: ${text.trim().slice(0, 240)}`);
    }
  }
  if (!res.ok) {
    throw new BuilderApiError(res.status, detailText(data, res.status));
  }
  return data as T;
}

const agentPath = (id: string) => `/agents/${encodeURIComponent(id)}`;

export const builderApi = {
  templates: () => call<{ templates: BuilderTemplate[] }>("/templates"),
  compose: (prompt: string, token: string) =>
    call<BuilderAgent>("/agents", { method: "POST", body: { prompt }, token }),
  listMine: (token: string, signal?: AbortSignal) =>
    call<{ agents: BuilderAgent[] }>("/agents", { token, signal }),
  get: (id: string, signal?: AbortSignal) => call<BuilderAgent>(agentPath(id), { signal }),
  compile: (id: string, token: string) =>
    call<BuilderAgent>(`${agentPath(id)}/compile`, { method: "POST", token }),
  setAgentMode: (id: string, mode: AgentMode, token: string) =>
    call<BuilderAgent>(`${agentPath(id)}/mode`, { method: "POST", body: { mode }, token }),
  source: (id: string, signal?: AbortSignal) =>
    call<{ files: Record<string, string> }>(`${agentPath(id)}/source`, { signal }),
  performance: (id: string, signal?: AbortSignal) =>
    call<{ books: PerformanceBook[] }>(`${agentPath(id)}/performance`, { signal }),
  runs: (id: string, signal?: AbortSignal) =>
    call<{ runs: BuilderRun[] }>(`${agentPath(id)}/runs`, { signal }),
  preview: (id: string, wallet: string, token: string) =>
    call<BuilderEvaluation>(`${agentPath(id)}/preview`, { method: "POST", body: { wallet }, token }),
  aomi: (id: string, token: string, signal?: AbortSignal) =>
    call<AomiState>(`${agentPath(id)}/aomi`, { token, signal }),
  createAomiWallet: (id: string, token: string) =>
    call<AomiState>(`${agentPath(id)}/aomi/wallet`, { method: "POST", token }),
  chat: (id: string, body: { message: string; session_id?: string }, token: string) =>
    call<ChatResponse>(`${agentPath(id)}/chat`, { method: "POST", body, token }),
};

export function errorText(err: unknown): string {
  if (err instanceof BuilderApiError) {
    return err.status ? `${err.message} (HTTP ${err.status})` : err.message;
  }
  return err instanceof Error ? err.message : String(err);
}

export function isAbort(err: unknown): boolean {
  return err instanceof DOMException && err.name === "AbortError";
}

// ---- display formatting (no values are invented here) ----

export function shortAddress(address: string | null | undefined): string {
  if (!address) return "-";
  return address.length > 12 ? `${address.slice(0, 4)}…${address.slice(-4)}` : address;
}

export function formatUsd(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return "-";
  return `$${value.toLocaleString("en-US", { maximumFractionDigits: 2 })}`;
}

/** Token amounts: up to 6 decimals, no trailing zeros. */
export function formatAmount(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return "-";
  return value.toLocaleString("en-US", { maximumFractionDigits: 6 });
}

export function formatScore(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return "-";
  return `${value > 0 ? "+" : ""}${value.toFixed(4)}`;
}

export function formatBytes(bytes: number | null | undefined): string {
  if (bytes == null) return "-";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
}

export function formatTime(iso: string | null | undefined): string {
  if (!iso) return "-";
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? iso : date.toLocaleString();
}

export function baseName(path: string): string {
  const parts = path.split(/[\\/]/);
  return parts[parts.length - 1] || path;
}
