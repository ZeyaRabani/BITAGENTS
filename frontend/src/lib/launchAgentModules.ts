export type LaunchModule = {
  id: string;
  name: string;
  category: "data" | "wallet" | "trading" | "infra";
  description: string;
};

/** Capabilities / connectors available when composing a new agent (frontend catalog). */
export const LAUNCH_MODULES: LaunchModule[] = [
  {
    id: "web_search",
    name: "Web Search",
    category: "data",
    description: "Search the open web for live context and sources.",
  },
  {
    id: "yahoo_news",
    name: "Yahoo News",
    category: "data",
    description: "Headlines and market news via Yahoo Finance.",
  },
  {
    id: "yahoo_market",
    name: "Yahoo Market Data",
    category: "data",
    description: "Realtime and historical prices, quotes, and charts.",
  },
  {
    id: "token_research",
    name: "Token Research",
    category: "data",
    description: "Token overview, health scores, and risk signals.",
  },
  {
    id: "whale_tracking",
    name: "Whale Tracking",
    category: "data",
    description: "Monitor large wallet moves and flow alerts.",
  },
  {
    id: "user_wallet",
    name: "User Wallet",
    category: "wallet",
    description: "Read balances and act with the signed-in user wallet.",
  },
  {
    id: "agent_wallet",
    name: "Agent Wallet",
    category: "wallet",
    description: "Provisioned per-user agent wallet for deposits and spends.",
  },
  {
    id: "jupiter_swaps",
    name: "Jupiter Swaps",
    category: "trading",
    description: "Execute Solana swaps through Jupiter routing.",
  },
  {
    id: "dca_scheduler",
    name: "DCA Scheduler",
    category: "trading",
    description: "Recurring buys and plan management on a timer.",
  },
  {
    id: "limit_orders",
    name: "Limit / Stop Orders",
    category: "trading",
    description: "Conditional buys and sells at price or market-cap targets.",
  },
  {
    id: "volume_campaigns",
    name: "Volume Campaigns",
    category: "trading",
    description: "Timed buy/sell cycles for token volume programs.",
  },
  {
    id: "solana_rpc",
    name: "Solana RPC",
    category: "infra",
    description: "On-chain reads, confirmations, and tx submission.",
  },
  {
    id: "easya_screener",
    name: "EasyA Screener",
    category: "data",
    description: "Kickstart token analytics and launch-token context.",
  },
];

export const LAUNCH_COST_SOL = 1;
