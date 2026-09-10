import type { LucideIcon } from "lucide-react";
import {
  ArrowLeftRight,
  Bell,
  Bot,
  Radar,
  Search,
  Wallet,
} from "lucide-react";

export type AgentCategory = "Monitor" | "Research" | "Alerts" | "Automation" | "Trading";

export type AgentIconId =
  | "wallet"
  | "search"
  | "bell"
  | "bot"
  | "radar"
  | "swap";

export const AGENT_ICONS: Record<AgentIconId, LucideIcon> = {
  wallet: Wallet,
  search: Search,
  bell: Bell,
  bot: Bot,
  radar: Radar,
  swap: ArrowLeftRight,
};

export type MarketplaceAgent = {
  id: string;
  slug: string;
  name: string;
  category: AgentCategory;
  description: string;
  tagline: string;
  pricePerTask?: string;
  runs?: string;
  volumeSol?: string;
  rating: number;
  iconId: AgentIconId;
  available: boolean;
  model?: string;
  cluster?: string;
};

export const MARKETPLACE_STATS = {
  liveAgents: "8",
  tasks24h: "102",
  activeBuilders: "22",
  uptime30d: "99.2%",
};

export const AGENT_CATEGORIES: { name: AgentCategory; count: number }[] = [
  { name: "Monitor", count: 12 },
  { name: "Research", count: 9 },
  { name: "Alerts", count: 7 },
  { name: "Automation", count: 11 },
  { name: "Trading", count: 9 },
];

export const FEATURED_AGENTS: MarketplaceAgent[] = [
  {
    id: "dca",
    slug: "dca",
    name: "DCA Agent",
    category: "Trading",
    description: "Set up dollar-cost averaging on Solana. Schedule recurring token buys, preview Jupiter quotes, and manage plans from natural language.",
    tagline: "Recurring buys · hosted LLM",
    pricePerTask: "0.5% / tx",
    runs: "-",
    volumeSol: "-",
    rating: 4.9,
    iconId: "swap",
    available: true,
    model: "meta-llama/llama-3.1-8b-instruct",
    cluster: "mainnet",
  },
  {
    id: "kickstart-copilot",
    slug: "kickstart-copilot",
    name: "EasyA Analysis Agent",
    category: "Research",
    description:
      "Solana token analysis - live price, liquidity, holders, health scores, risk checks, and comparisons.",
    tagline: "Token analysis",
    rating: 4.9,
    iconId: "search",
    available: true,
    model: "meta-llama/llama-3.1-8b-instruct",
    cluster: "mainnet",
  },
  {
    id: "volume",
    slug: "volume",
    name: "Volume Agent",
    category: "Trading",
    description:
      "Run volume campaigns on tokens that already trade. Deposit SOL, pick a pair, and schedule buy/sell cycles through Jupiter — same path as BITAGENTS Volume.",
    tagline: "Jupiter volume · no pool setup",
    pricePerTask: "0.25% / leg",
    runs: "-",
    volumeSol: "-",
    rating: 4.8,
    iconId: "swap",
    available: true,
    model: "meta-llama/llama-3.1-8b-instruct",
    cluster: "mainnet",
  },
  {
    id: "volume2",
    slug: "volume2",
    name: "BITAGENTS Volume",
    category: "Trading",
    description:
      "One-click BITAGENTS volume campaigns. Deposit SOL, pick Quick / Standard / Full day — no token fields or Meteora setup.",
    tagline: "BITAGENTS presets · simple",
    pricePerTask: "0.25% / leg",
    runs: "-",
    volumeSol: "-",
    rating: 4.8,
    iconId: "swap",
    available: true,
    model: "meta-llama/llama-3.1-8b-instruct",
    cluster: "mainnet",
  },
  {
    id: "whale-tracking",
    slug: "whale-tracking",
    name: "Whale Tracking Agent",
    category: "Trading",
    description:
      "Track Solana wallet addresses, monitor smart-money activity, maintain watchlists, and research copy-trade opportunities.",
    tagline: "Wallet intel · copy-trade research",
    rating: 4.8,
    iconId: "radar",
    available: true,
    model: "meta-llama/llama-3.1-8b-instruct",
    cluster: "mainnet",
  },
  {
    id: "token-research",
    slug: "token-research",
    name: "Token Research Agent",
    category: "Research",
    description:
      "Research any Solana token using on-chain RPC data, Jupiter prices, and Meteora pool metrics.",
    tagline: "On-chain RPC · Jupiter · Meteora",
    rating: 4.8,
    iconId: "search",
    available: true,
    model: "meta-llama/llama-3.1-8b-instruct",
    cluster: "mainnet",
  },
  {
    id: "wallet-monitoring",
    slug: "wallet-monitoring",
    name: "Wallet Monitoring Agent",
    category: "Monitor",
    description:
      "Monitor your connected wallet — SOL balance, SPL holdings, recent activity, and informational trade suggestions.",
    tagline: "Portfolio snapshot · trade ideas",
    rating: 4.9,
    iconId: "wallet",
    available: true,
    model: "meta-llama/llama-3.1-8b-instruct",
    cluster: "mainnet",
  },
  {
    id: "due-diligence",
    slug: "due-diligence",
    name: "Due Diligence Agent",
    category: "Research",
    description:
      "Due diligence on tokens and SPL mints — mint/freeze authorities, holder concentration, liquidity, and graded risk.",
    tagline: "Mint authority · risk score",
    rating: 4.7,
    iconId: "bot",
    available: true,
    model: "meta-llama/llama-3.1-8b-instruct",
    cluster: "mainnet",
  }
  ,
  {
    id: "hedge-fund",
    slug: "hedge-fund",
    name: "Hedge Fund Agent",
    category: "Trading",
    description:
      "Deposit SOL, run live Jupiter strategy sleeves (USD notional), and liquidate back to SOL with 1% start / 10% profit fees. Paper mode still available.",
    tagline: "Automated strategies · risk-managed",
    pricePerTask: "1% Fee & 10% Profit",
    runs: "-",
    volumeSol: "-",
    rating: 4.9,
    iconId: "bot",
    available: true,
    model: "meta-llama/llama-3.1-8b-instruct",
    cluster: "mainnet",
  }
];

export function getAgentBySlug(slug: string): MarketplaceAgent | undefined {
  return FEATURED_AGENTS.find((agent) => agent.slug === slug);
}

export const DCA_QUICK_ACTIONS = [
  "List my DCA plans",
  "Analyze SOL for DCA timing",
  "Execute plan dry run",
] as const;

export const VOLUME_QUICK_ACTIONS = [
  "List my volume campaigns",
  "Check DLMM pool status",
  "How does pool creation work?",
] as const;
