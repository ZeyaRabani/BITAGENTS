import { AGENT_DESCRIPTIONS, AGENT_LABELS, type AgentType } from "@bitagents/shared";
import { Eye, LineChart, Search, type LucideIcon } from "lucide-react";

export interface AgentMeta {
  type: AgentType;
  label: string;
  description: string;
  icon: LucideIcon;
  inputField: "walletAddress" | "query";
  inputLabel: string;
  placeholder: string;
  example: string;
  outputs: string[];
}

export const AGENTS: AgentMeta[] = [
  {
    type: "wallet_watcher",
    label: AGENT_LABELS.wallet_watcher,
    description: AGENT_DESCRIPTIONS.wallet_watcher,
    icon: Eye,
    inputField: "walletAddress",
    inputLabel: "Solana wallet address",
    placeholder: "Enter a Solana wallet address",
    example: "So11111111111111111111111111111111111111112",
    outputs: ["SOL balance", "Token account count", "Latest 5 signatures", "AI summary", "Risk notes"]
  },
  {
    type: "token_research",
    label: AGENT_LABELS.token_research,
    description: AGENT_DESCRIPTIONS.token_research,
    icon: Search,
    inputField: "query",
    inputLabel: "Token mint address or project name",
    placeholder: "Mint address or project name",
    example: "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
    outputs: ["On-chain overview", "Authorities & supply", "Bull / bear case", "Risks", "Disclaimer"]
  },
  {
    type: "market_research",
    label: AGENT_LABELS.market_research,
    description: AGENT_DESCRIPTIONS.market_research,
    icon: LineChart,
    inputField: "query",
    inputLabel: "Keyword, ticker, or narrative",
    placeholder: "e.g. DePIN, restaking, RWA, SOL",
    example: "DePIN",
    outputs: ["Definition", "Use cases", "Opportunities", "Risks", "What to monitor"]
  }
];

export function agentMeta(type: AgentType): AgentMeta {
  const found = AGENTS.find((agent) => agent.type === type);
  if (!found) {
    throw new Error(`Unknown agent type: ${type}`);
  }
  return found;
}
