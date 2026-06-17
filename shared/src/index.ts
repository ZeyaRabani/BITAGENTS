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
