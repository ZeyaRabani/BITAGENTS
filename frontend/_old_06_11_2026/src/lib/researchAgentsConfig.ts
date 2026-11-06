export type ResearchAgentSlug =
  | "whale-tracking"
  | "token-research"
  | "wallet-monitoring"
  | "due-diligence";

export type ResearchAgentConfig = {
  slug: ResearchAgentSlug;
  name: string;
  tagline: string;
  description: string;
  model: string;
  cluster: string;
  assistantLabel: string;
  examplePrompts: readonly string[];
};

export const RESEARCH_AGENTS: Record<ResearchAgentSlug, ResearchAgentConfig> = {
  "whale-tracking": {
    slug: "whale-tracking",
    name: "Whale Tracking Agent",
    tagline: "Wallet intel · copy-trade research",
    description:
      "Track Solana wallet addresses, monitor smart-money activity, maintain watchlists, and research copy-trade opportunities.",
    model: "meta-llama/llama-3.1-8b-instruct",
    cluster: "mainnet",
    assistantLabel: "Whale Agent",
    examplePrompts: [
      "List curated whale wallets",
      "Analyze wallet 5Q544fKrFoe6tsEbD7S8EmxGTJYAKtTVhAW5Q5pge4j1",
      "Add a wallet to my watchlist",
      "Preview copy trade for a whale buying BONK",
    ],
  },
  "token-research": {
    slug: "token-research",
    name: "Token Research Agent",
    tagline: "On-chain RPC · Jupiter · Meteora",
    description:
      "Research any Solana token using on-chain RPC data, Jupiter prices, and Meteora pool metrics.",
    model: "meta-llama/llama-3.1-8b-instruct",
    cluster: "mainnet",
    assistantLabel: "Research Agent",
    examplePrompts: [
      "Search for WIF on EASY Screener",
      "Give me a research brief on JUP",
      "Compare BONK and WIF",
      "What are the risks for this mint?",
    ],
  },
  "wallet-monitoring": {
    slug: "wallet-monitoring",
    name: "Wallet Monitoring Agent",
    tagline: "Portfolio snapshot · trade ideas",
    description:
      "On-chain wallet analysis for any Solana address — SOL balance, SPL holdings, recent activity, and informational trade suggestions. Results cached 15 minutes.",
    model: "meta-llama/llama-3.1-8b-instruct",
    cluster: "mainnet",
    assistantLabel: "Wallet Agent",
    examplePrompts: [
      "Analyze my connected wallet",
      "Analyze wallet 5Q544fKrFoe6tsEbD7S8EmxGTJYAKtTVhAW5Q5pge4j1",
      "What tokens does this wallet hold?",
      "Suggest trades for my portfolio",
    ],
  },
  "due-diligence": {
    slug: "due-diligence",
    name: "Due Diligence Agent",
    tagline: "Mint authority · risk score",
    description:
      "On-chain due diligence for any Solana token — authorities, holder concentration, liquidity, and graded risk score. Shares a 15-minute cache with Token Research.",
    model: "meta-llama/llama-3.1-8b-instruct",
    cluster: "mainnet",
    assistantLabel: "Diligence Agent",
    examplePrompts: [
      "Run due diligence on BITAGENTS: iu3A7azWTm3zQSk81SUC1JctB4zPYnxLmcmqq71EASY",
      "Check mint and freeze authority for JUP",
      "Show top holders and concentration risk",
      "Is this token safe to buy?",
    ],
  },
};

export function getResearchAgentConfig(slug: string): ResearchAgentConfig | undefined {
  return RESEARCH_AGENTS[slug as ResearchAgentSlug];
}
