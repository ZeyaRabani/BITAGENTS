// =====================================================================
// BITAGENTS shared types and helpers
// Used by the Next.js frontend (browser + server) and the optional worker.
// Keep this file free of Node-only imports so it can be bundled for the
// browser. Real computation lives in server-only modules.
// =====================================================================

export const TASK_STATUSES = [
  "created",
  "paid",
  "assigned",
  "computing",
  "completed",
  "failed"
] as const;

export type TaskStatus = (typeof TASK_STATUSES)[number];

export const AGENT_TYPES = [
  "wallet_watcher",
  "token_research",
  "market_research"
] as const;

export type AgentType = (typeof AGENT_TYPES)[number];

export const SOLANA_NETWORKS = ["devnet", "mainnet"] as const;
export type SolanaNetwork = (typeof SOLANA_NETWORKS)[number];

export type ComputeType = "CPU" | "GPU_SIMULATED" | "LLM";
export type ProviderStatus = "online" | "offline";

export type ComputeEngine = "deterministic" | "ollama" | "openai" | "anthropic";

export interface StatusEvent {
  status: TaskStatus;
  at: string;
  note?: string;
}

export interface ComputeProvider {
  id: string;
  name: string;
  walletAddress: string;
  computeType: ComputeType;
  pricePerTaskSol: number;
  status: ProviderStatus;
  tasksCompleted: number;
  reputation: number;
  endpoint?: string;
  registrationSignature?: string;
  registrationMessage?: string;
  createdAt: string;
  updatedAt: string;
}

// ---------------------------------------------------------------------
// Agent inputs
// ---------------------------------------------------------------------

export interface WalletWatcherInput {
  walletAddress: string;
}

export interface TokenResearchInput {
  query: string;
}

export interface MarketResearchInput {
  query: string;
}

export type AgentInput = WalletWatcherInput | TokenResearchInput | MarketResearchInput;

// ---------------------------------------------------------------------
// Shared compute metadata attached to every result
// ---------------------------------------------------------------------

export interface ComputeMeta {
  computedAt: string;
  runtimeMs: number;
  resultHash: string;
  engine: ComputeEngine;
  network: SolanaNetwork;
  rpcUrl: string;
}

// ---------------------------------------------------------------------
// Agent results
// ---------------------------------------------------------------------

export interface WalletSignatureSummary {
  signature: string;
  slot: number;
  blockTime: number | null;
  err: boolean;
}

export interface WalletWatcherResult extends ComputeMeta {
  type: "wallet_watcher";
  walletAddress: string;
  solBalance: number;
  tokenAccountsCount: number;
  latestSignatures: WalletSignatureSummary[];
  summary: string;
  riskNotes: string[];
}

export interface TokenResearchResult extends ComputeMeta {
  type: "token_research";
  query: string;
  mintAddress: string | null;
  resolvedFromMint: boolean;
  overview: string;
  onchain: {
    supply: number | null;
    decimals: number | null;
    holdersNote: string;
    liquidityNote: string;
    mintAuthorityActive: boolean | null;
    freezeAuthorityActive: boolean | null;
  };
  risks: string[];
  bullCase: string[];
  bearCase: string[];
  disclaimer: string;
}

export interface MarketResearchResult extends ComputeMeta {
  type: "market_research";
  query: string;
  meaning: string;
  useCases: string[];
  risks: string[];
  opportunities: string[];
  thingsToMonitor: string[];
  sentimentScore: number;
  disclaimer: string;
}

export type AgentResult = WalletWatcherResult | TokenResearchResult | MarketResearchResult;

// ---------------------------------------------------------------------
// Tasks
// ---------------------------------------------------------------------

export interface AgentTask {
  id: string;
  type: AgentType;
  input: AgentInput;
  network: SolanaNetwork;
  requesterWallet: string | null;
  free: boolean;
  status: TaskStatus;
  priceSol: number;
  assignedProviderId?: string;
  assignedProviderWallet?: string;
  assignedProviderName?: string;
  paymentSignature?: string;
  runtimeMs?: number;
  result?: AgentResult;
  error?: string;
  createdAt: string;
  updatedAt: string;
  history: StatusEvent[];
}

export interface BitagentsDb {
  providers: ComputeProvider[];
  tasks: AgentTask[];
}

// ---------------------------------------------------------------------
// Labels and ordering
// ---------------------------------------------------------------------

export const AGENT_LABELS: Record<AgentType, string> = {
  wallet_watcher: "Wallet Watcher Agent",
  token_research: "Token Research Agent",
  market_research: "Market Research Agent"
};

export const AGENT_DESCRIPTIONS: Record<AgentType, string> = {
  wallet_watcher:
    "Inspect any Solana wallet: SOL balance, token accounts, recent activity, plus an AI summary and behavior notes.",
  token_research:
    "Produce a structured research report for a token mint or project, with on-chain notes, bull/bear cases, and risks.",
  market_research:
    "Turn a keyword, ticker, or narrative into a structured research brief: meaning, use cases, risks, and opportunities."
};

export const STATUS_LABELS: Record<TaskStatus, string> = {
  created: "Created",
  paid: "Paid",
  assigned: "Assigned",
  computing: "Computing",
  completed: "Completed",
  failed: "Failed"
};

export const STATUS_ORDER: TaskStatus[] = [
  "created",
  "paid",
  "assigned",
  "computing",
  "completed"
];

export const DEFAULT_TASK_PRICE_SOL = 0.001;
export const LAMPORTS_PER_SOL_NUMBER = 1_000_000_000;

// ---------------------------------------------------------------------
// Guards and helpers
// ---------------------------------------------------------------------

export function isAgentType(value: string): value is AgentType {
  return (AGENT_TYPES as readonly string[]).includes(value);
}

export function isTaskStatus(value: string): value is TaskStatus {
  return (TASK_STATUSES as readonly string[]).includes(value);
}

export function isSolanaNetwork(value: string): value is SolanaNetwork {
  return (SOLANA_NETWORKS as readonly string[]).includes(value);
}

export function solToLamports(sol: number): number {
  return Math.max(0, Math.round(sol * LAMPORTS_PER_SOL_NUMBER));
}

export function lamportsToSol(lamports: number): number {
  return lamports / LAMPORTS_PER_SOL_NUMBER;
}

export function makeExplorerTxUrl(signature: string, network: SolanaNetwork = "devnet"): string {
  const cluster = network === "mainnet" ? "mainnet-beta" : "devnet";
  return `https://explorer.solana.com/tx/${signature}?cluster=${cluster}`;
}

export function makeExplorerAddressUrl(address: string, network: SolanaNetwork = "devnet"): string {
  const cluster = network === "mainnet" ? "mainnet-beta" : "devnet";
  return `https://explorer.solana.com/address/${address}?cluster=${cluster}`;
}

export function shortAddress(address: string): string {
  if (address.length <= 12) {
    return address;
  }
  return `${address.slice(0, 4)}...${address.slice(-4)}`;
}

export function nowIso(): string {
  return new Date().toISOString();
}

export function networkLabel(network: SolanaNetwork): string {
  return network === "mainnet" ? "Mainnet Read Mode" : "Devnet Demo Mode";
}

export function taskInputLabel(task: Pick<AgentTask, "type" | "input">): string {
  if (task.type === "wallet_watcher" && "walletAddress" in task.input) {
    return task.input.walletAddress;
  }

  if ((task.type === "token_research" || task.type === "market_research") && "query" in task.input) {
    return task.input.query;
  }

  return "Unknown input";
}

// =====================================================================
// BITAGENTS DCA Agent
// The primary product: turn a natural-language instruction into a safe
// recurring on-chain buy plan. Everything below is pure (browser-safe) so it
// can be shared between the parser, the UI, the API routes, and tests.
// =====================================================================

export const WSOL_MINT = "So11111111111111111111111111111111111111112";
export const USDC_MINT = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v";
export const USDT_MINT = "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB";

export interface TokenInfo {
  symbol: string;
  mint: string;
  decimals: number;
  aliases: string[];
}

// Base registry of well-known tokens. The BITAGENTS token is injected at
// runtime from NEXT_PUBLIC_BITAGENTS_MINT so it stays deploy-configurable.
export const KNOWN_TOKENS: TokenInfo[] = [
  { symbol: "SOL", mint: WSOL_MINT, decimals: 9, aliases: ["sol", "solana", "wsol", "wrapped sol"] },
  { symbol: "USDC", mint: USDC_MINT, decimals: 6, aliases: ["usdc", "usd coin"] },
  { symbol: "USDT", mint: USDT_MINT, decimals: 6, aliases: ["usdt", "tether"] }
];

export const DCA_EXECUTION_MODES = ["jupiter_recurring", "agent_wallet", "devnet_demo"] as const;
export type DcaExecutionMode = (typeof DCA_EXECUTION_MODES)[number];

export const DCA_PLAN_STATUSES = [
  "draft",
  "needs_confirmation",
  "creating",
  "active",
  "completed",
  "cancelled",
  "failed"
] as const;
export type DcaPlanStatus = (typeof DCA_PLAN_STATUSES)[number];

export const DCA_EXECUTION_STATUSES = ["pending", "success", "failed", "skipped"] as const;
export type DcaExecutionStatus = (typeof DCA_EXECUTION_STATUSES)[number];

export const DCA_PLAN_STATUS_LABELS: Record<DcaPlanStatus, string> = {
  draft: "Draft",
  needs_confirmation: "Needs confirmation",
  creating: "Creating",
  active: "Active",
  completed: "Completed",
  cancelled: "Cancelled",
  failed: "Failed"
};

export const EXECUTION_MODE_LABELS: Record<DcaExecutionMode, string> = {
  jupiter_recurring: "Jupiter Recurring (mainnet)",
  agent_wallet: "Experimental Agent Wallet",
  devnet_demo: "Devnet Demo (simulated)"
};

// The exact plan schema requested in the product spec, plus additive
// bookkeeping fields used to track execution progress.
export interface DcaPlan {
  id: string;
  userWallet: string;
  inputMint: string;
  outputMint: string;
  inputSymbol: string;
  outputSymbol: string;
  inputDecimals: number;
  outputDecimals: number;
  totalInputAmountUi: number;
  perOrderAmountUi: number;
  numberOfOrders: number;
  intervalSeconds: number;
  startAt: number | null;
  slippageBps: number;
  estimatedDurationSeconds: number;
  network: SolanaNetwork;
  executionMode: DcaExecutionMode;
  status: DcaPlanStatus;
  warnings: string[];
  createdAt: string;
  updatedAt: string;
  // Execution bookkeeping
  ordersExecuted: number;
  spentInputUi: number;
  receivedOutputUi: number;
  lastExecutedAt: string | null;
  nextExecutionAt: string | null;
  jupiterOrderAccount: string | null;
  jupiterRequestId: string | null;
  createSignature: string | null;
  cancelSignature: string | null;
  agentWalletAddress: string | null;
  error: string | null;
}

export interface DcaExecution {
  id: string;
  planId: string;
  orderIndex: number;
  status: DcaExecutionStatus;
  network: SolanaNetwork;
  executionMode: DcaExecutionMode;
  simulated: boolean;
  inputAmountUi: number;
  outputAmountUi: number | null;
  priceUsd: number | null;
  signature: string | null;
  runtimeMs: number;
  resultHash: string;
  note: string;
  scheduledFor: string;
  executedAt: string;
}

export interface DcaChatMessage {
  id: string;
  role: "user" | "agent";
  text: string;
  planId?: string;
  createdAt: string;
}

// ---------------------------------------------------------------------
// DCA math + parsing helpers (pure)
// ---------------------------------------------------------------------

const INTERVAL_UNIT_SECONDS: Record<string, number> = {
  second: 1,
  sec: 1,
  s: 1,
  minute: 60,
  min: 60,
  m: 60,
  hour: 3600,
  hr: 3600,
  h: 3600,
  day: 86_400,
  d: 86_400,
  week: 604_800,
  wk: 604_800,
  w: 604_800
};

/**
 * Parse a human interval phrase into seconds.
 * Supports "10 minutes", "every 10 min", "1 hour", "hourly", "daily",
 * "every day", "30s", "1h", "2 weeks". Returns null when nothing matches.
 */
export function parseIntervalToSeconds(input: string): number | null {
  const text = input.toLowerCase().trim();
  if (!text) return null;

  const named: Record<string, number> = {
    secondly: 1,
    minutely: 60,
    hourly: 3600,
    daily: 86_400,
    weekly: 604_800,
    "every second": 1,
    "every minute": 60,
    "every hour": 3600,
    "every day": 86_400,
    "every week": 604_800
  };
  for (const [phrase, seconds] of Object.entries(named)) {
    if (text.includes(phrase)) return seconds;
  }

  // "every 10 minutes", "10 min", "1h", "30 s", "2 weeks", and bare units
  // like "day" / "hour" (an implied count of 1, e.g. from "every day").
  const match = text.match(
    /(?:every\s+)?(\d+(?:\.\d+)?)?\s*(seconds?|secs?|s|minutes?|mins?|m|hours?|hrs?|h|days?|d|weeks?|wks?|w)\b/
  );
  if (!match) return null;
  const value = match[1] ? Number(match[1]) : 1;
  const unitRaw = match[2];
  const unit =
    unitRaw.replace(/s$/, "") === ""
      ? unitRaw
      : unitRaw.startsWith("sec")
        ? "sec"
        : unitRaw.startsWith("min")
          ? "min"
          : unitRaw.startsWith("hour") || unitRaw.startsWith("hr")
            ? "hour"
            : unitRaw.startsWith("day")
              ? "day"
              : unitRaw.startsWith("week") || unitRaw.startsWith("wk")
                ? "week"
                : unitRaw;
  const seconds = INTERVAL_UNIT_SECONDS[unit] ?? INTERVAL_UNIT_SECONDS[unitRaw];
  if (!seconds || !Number.isFinite(value) || value <= 0) return null;
  return Math.round(value * seconds);
}

export function formatDuration(seconds: number): string {
  if (!Number.isFinite(seconds) || seconds <= 0) return "0m";
  const days = Math.floor(seconds / 86_400);
  const hours = Math.floor((seconds % 86_400) / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  const parts: string[] = [];
  if (days) parts.push(`${days}d`);
  if (hours) parts.push(`${hours}h`);
  if (minutes) parts.push(`${minutes}m`);
  if (!parts.length) parts.push(`${seconds}s`);
  return parts.join(" ");
}

export function formatInterval(seconds: number): string {
  return formatDuration(seconds);
}

// Jupiter defines "total time to complete" as numberOfOrders * interval.
export function estimateDurationSeconds(numberOfOrders: number, intervalSeconds: number): number {
  return Math.max(0, Math.round(numberOfOrders * intervalSeconds));
}

export function computePerOrderAmount(totalInputAmountUi: number, numberOfOrders: number): number {
  if (numberOfOrders <= 0) return 0;
  return totalInputAmountUi / numberOfOrders;
}

export function uiAmountToRawAmount(uiAmount: number, decimals: number): number {
  return Math.round(uiAmount * 10 ** decimals);
}

export function rawAmountToUiAmount(rawAmount: number, decimals: number): number {
  return rawAmount / 10 ** decimals;
}

const BASE58_RE = /^[1-9A-HJ-NP-Za-km-z]{32,44}$/;

/** Lightweight base58 pubkey shape check (no curve validation). */
export function looksLikeMintAddress(value: string): boolean {
  return BASE58_RE.test(value.trim());
}

export interface DcaValidation {
  errors: string[];
  warnings: string[];
}

export const DCA_RISK_WARNINGS: string[] = [
  "This is not financial advice. You choose the token and all parameters.",
  "The agent only automates the instruction you give it — it never picks tokens for you.",
  "Small or new tokens can be illiquid; slippage may cause worse execution.",
  "Recurring buys can fail due to liquidity, routing, or minimum-order limits.",
  "Mainnet orders move real funds and require your wallet signature.",
  "Dollar-cost averaging does not guarantee profit and tokens can lose value."
];

/**
 * Validate a (possibly partial) DCA plan. Pure so it runs in the UI, the API,
 * and tests identically.
 */
export function validateDcaPlan(plan: Partial<DcaPlan>): DcaValidation {
  const errors: string[] = [];
  const warnings: string[] = [];

  if (!plan.outputMint || !looksLikeMintAddress(plan.outputMint)) {
    errors.push("Output token mint is missing or invalid.");
  }
  if (!plan.inputMint || !looksLikeMintAddress(plan.inputMint)) {
    errors.push("Input token mint is missing or invalid.");
  }
  if (plan.inputMint && plan.outputMint && plan.inputMint === plan.outputMint) {
    errors.push("Input and output tokens must be different.");
  }
  if (!plan.totalInputAmountUi || plan.totalInputAmountUi <= 0) {
    errors.push("Total budget must be greater than zero.");
  }
  if (!plan.numberOfOrders || plan.numberOfOrders < 1) {
    errors.push("Number of buys must be at least 1.");
  }
  if (plan.numberOfOrders && plan.numberOfOrders > 2000) {
    warnings.push("Very large number of buys — consider fewer, larger orders.");
  }
  if (!plan.intervalSeconds || plan.intervalSeconds < 1) {
    errors.push("Interval must be at least 1 second.");
  }
  if (plan.slippageBps != null && (plan.slippageBps < 0 || plan.slippageBps > 5000)) {
    warnings.push("Slippage looks unusual (outside 0–50%).");
  }
  if (plan.perOrderAmountUi != null && plan.perOrderAmountUi <= 0) {
    errors.push("Per-buy amount must be greater than zero.");
  }

  return { errors, warnings };
}

// Jupiter Recurring enforces a minimum USDC value per order (≈ 50 USDC at the
// time of writing). Used to warn before a likely-rejected mainnet order.
export const JUPITER_MIN_ORDER_USD = 50;
export const JUPITER_RECURRING_FEE_BPS = 10; // 0.1%

export function dcaPlanProgress(plan: Pick<DcaPlan, "ordersExecuted" | "numberOfOrders">): number {
  if (plan.numberOfOrders <= 0) return 0;
  return Math.min(1, plan.ordersExecuted / plan.numberOfOrders);
}
