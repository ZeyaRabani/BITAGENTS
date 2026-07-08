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
  liveAgents: "2",
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
    tagline: "Recurring buys · OpenRouter-powered",
    pricePerTask: "0.5% / tx",
    runs: "-",
    volumeSol: "-",
    rating: 4.9,
    iconId: "swap",
    available: true,
    model: "meta-llama/llama-3.3-70b-instruct",
    cluster: "mainnet",
  },
  {
    id: "kickstart-copilot",
    slug: "kickstart-copilot",
    name: "EasyA Analysis Agent",
    category: "Research",
    description:
      "Solana token analysis via EASY Screener. Deposit SOL for one-time Jupiter market/limit buys (0.1% fee).",
    tagline: "Analysis · Jupiter trading",
    rating: 4.9,
    iconId: "search",
    available: false,
    model: "meta-llama/llama-3.3-70b-instruct",
    cluster: "mainnet",
  },
  // {
  //   id: "custom",
  //   slug: "custom",
  //   name: "Create Your Own Agent",
  //   category: "Automation",
  //   description:
  //     "Build your own AI agent with a custom system prompt. Chat with it right away - no code required.",
  //   tagline: "Your prompt · your agent",
  //   rating: 5.0,
  //   iconId: "bot",
  //   available: true,
  // },
  {
    id: "wallet-watcher",
    slug: "wallet-watcher",
    name: "Wallet Watcher",
    category: "Monitor",
    description: "Track wallet flows, token balances, and notable on-chain activity in real time.",
    tagline: "Balance alerts · flow tracking · wallet intel",
    rating: 4.9,
    iconId: "wallet",
    available: false,
  },
  {
    id: "research",
    slug: "research",
    name: "Research Agent",
    category: "Research",
    description:
      "Summarize on-chain data, social sentiment, and protocol fundamentals into concise research briefs.",
    tagline: "On-chain research · sentiment · briefs",
    rating: 4.8,
    iconId: "search",
    available: false,
  },
  {
    id: "alert-monitor",
    slug: "alert-monitor",
    name: "Alert Monitor",
    category: "Alerts",
    description: "Configure price, volume, and wallet triggers with instant notifications.",
    tagline: "Price alerts · volume spikes · custom triggers",
    rating: 4.7,
    iconId: "bell",
    available: false,
  },
  {
    id: "data-scraper",
    slug: "data-scraper",
    name: "Data Scraper",
    category: "Automation",
    description: "Pull structured data from protocols, APIs, and on-chain programs on a schedule.",
    tagline: "Scheduled pulls · structured output · API ready",
    rating: 4.9,
    iconId: "bot",
    available: false,
  },
  {
    id: "portfolio-tracker",
    slug: "portfolio-tracker",
    name: "Portfolio Tracker",
    category: "Monitor",
    description: "Aggregate holdings, PnL, and exposure across wallets and protocols.",
    tagline: "Multi-wallet · PnL · exposure",
    rating: 4.6,
    iconId: "radar",
    available: false,
  },
];

export function getAgentBySlug(slug: string): MarketplaceAgent | undefined {
  return FEATURED_AGENTS.find((agent) => agent.slug === slug);
}

export const DCA_QUICK_ACTIONS = [
  "List my DCA plans",
  "Analyze SOL for DCA timing",
  "Execute plan dry run",
] as const;
