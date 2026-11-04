export const JUPITER_TRADE = {
  slug: "jupiter-trade",
  name: "Jupiter Trade Agent",
  tagline: "Confirm · 24h paper · Jupiter spot",
  description:
    "Bring or request a strategy. Agent restates understanding for your confirm, runs ≥24h paper on Jupiter spot prices, then only goes live after you approve. Platform fee 0.1% per live trade. Jupiter Perps are not used yet.",
  model: "meta-llama/llama-3.3-70b-instruct",
  cluster: "mainnet",
  assistantLabel: "Trade Agent",
  platformFeePct: 0.1,
  examplePrompts: [
    "Propose MACD Classic on BONK with 1 SOL",
    "List RSI and Supertrend templates",
    "Confirm understanding jt…",
    "Show paper trades and hours remaining",
    "Confirm live jt… after paper is ready",
  ],
} as const;
