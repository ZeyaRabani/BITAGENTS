export type LaunchedAgent = {
  id: string;
  name: string;
  ticker: string;
  avatarSeed: string;
  creator: string;
  description: string;
  status: "LIVE" | "BONDING" | "TESTING";
  ageDays: number;
  runs: number;
  volumeUsd: number;
  feesUsd: number;
  category: "Trading" | "Research" | "Monitoring" | "Utility";
};

export const LAUNCHED_AGENTS: LaunchedAgent[] = [
  {
    id: "dca-agent",
    name: "DCA Agent",
    ticker: "DCA",
    avatarSeed: "dca",
    creator: "bitagents",
    description: "Recurring Jupiter buys on autopilot — set an interval, a budget, and let it run.",
    status: "LIVE",
    ageDays: 62,
    runs: 4180,
    volumeUsd: 214500,
    feesUsd: 1072,
    category: "Trading",
  },
  {
    id: "hedge-fund",
    name: "Hedge Fund Agent",
    ticker: "HFND",
    avatarSeed: "hedgefund",
    creator: "bitagents",
    description: "18-analyst Covenant framework proposes strategies, you confirm, it trades live on Jupiter.",
    status: "LIVE",
    ageDays: 19,
    runs: 340,
    volumeUsd: 88200,
    feesUsd: 990,
    category: "Trading",
  },
  {
    id: "volume-agent",
    name: "Volume Agent",
    ticker: "VOL",
    avatarSeed: "volume",
    creator: "bitagents",
    description: "Wash-free liquidity cycling through Meteora DLMM pools for real on-chain volume.",
    status: "LIVE",
    ageDays: 45,
    runs: 2210,
    volumeUsd: 512300,
    feesUsd: 1380,
    category: "Trading",
  },
  {
    id: "whale-tracking",
    name: "Whale Tracking Agent",
    ticker: "WHALE",
    avatarSeed: "whale",
    creator: "bitagents",
    description: "Watch top wallets, get alerted on their moves, research the trades before you copy them.",
    status: "LIVE",
    ageDays: 71,
    runs: 6040,
    volumeUsd: 0,
    feesUsd: 0,
    category: "Monitoring",
  },
  {
    id: "kickstart-copilot",
    name: "EasyA Analysis Agent",
    ticker: "EZA",
    avatarSeed: "easya",
    creator: "souleixbt",
    description: "Research copilot for EasyA Kickstart launches, with optional low-fee execution.",
    status: "LIVE",
    ageDays: 38,
    runs: 1560,
    volumeUsd: 61200,
    feesUsd: 61,
    category: "Research",
  },
  {
    id: "token-research",
    name: "Token Research Agent",
    ticker: "TKR",
    avatarSeed: "tokenresearch",
    creator: "bitagents",
    description: "Fundamentals, holder distribution, and risk flags on any Solana token in seconds.",
    status: "LIVE",
    ageDays: 71,
    runs: 3920,
    volumeUsd: 0,
    feesUsd: 0,
    category: "Research",
  },
  {
    id: "due-diligence",
    name: "Due Diligence Agent",
    ticker: "DD",
    avatarSeed: "diligence",
    creator: "bitagents",
    description: "Deep-dive contract, team, and liquidity checks before you ape into anything.",
    status: "LIVE",
    ageDays: 71,
    runs: 1180,
    volumeUsd: 0,
    feesUsd: 0,
    category: "Research",
  },
  {
    id: "wallet-monitoring",
    name: "Wallet Monitoring Agent",
    ticker: "WMON",
    avatarSeed: "walletmon",
    creator: "bitagents",
    description: "Free real-time alerts on any wallet — deposits, withdrawals, new token activity.",
    status: "LIVE",
    ageDays: 71,
    runs: 8410,
    volumeUsd: 0,
    feesUsd: 0,
    category: "Monitoring",
  },
  {
    id: "yield-scout",
    name: "Yield Scout",
    ticker: "YIELD",
    avatarSeed: "yieldscout",
    creator: "0xharshal",
    description: "Community-built agent scanning Solana lending markets for the best risk-adjusted APY.",
    status: "BONDING",
    ageDays: 3,
    runs: 84,
    volumeUsd: 4100,
    feesUsd: 12,
    category: "Research",
  },
  {
    id: "nft-sniper",
    name: "Floor Sniper",
    ticker: "SNIPE",
    avatarSeed: "floorsniper",
    creator: "jaymar",
    description: "Watches NFT floor prices across marketplaces and executes buys under a target threshold.",
    status: "TESTING",
    ageDays: 1,
    runs: 6,
    volumeUsd: 0,
    feesUsd: 0,
    category: "Trading",
  },
];

export function formatUsd(value: number): string {
  if (value >= 1000) return `$${(value / 1000).toFixed(1)}K`;
  return `$${value.toFixed(0)}`;
}
